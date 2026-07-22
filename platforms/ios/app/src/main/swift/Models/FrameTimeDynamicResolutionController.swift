// FrameTimeDynamicResolutionController.swift — opt-in adaptive internal resolution driven by frame-time history
// SPDX-License-Identifier: GPL-3.0+

import Foundation

/// `@MainActor @Observable` opt-in controller (Item 9) that adjusts
/// `upscale_multiplier` in 0.25 steps based on PerformanceMetrics frame-time
/// history. Polls every ~30 frames (~500 ms) and applies resolution changes
/// no more often than every 500 ms (D-04). Min clamp is 1.0 (native PS2 —
/// never below, per D-04 + the m_nativeres-hack pitfall); max clamp is the
/// user's currently-configured UpscaleMultiplier at the moment adaptive is
/// enabled (D-03 — there is no separate ceiling constant).
///
/// Writes through the existing
/// `ARMSX2Bridge.setINIFloat("EmuCore/GS", "upscale_multiplier", value)` path.
/// The bridge wrapper clamps to [0.25, 8.0] and hops to the CPU/GS thread via
/// the existing live-float-setting hop — no JIT, VM, recompiler, or fastmem
/// contact (T-4.1-16 mitigated; Pitfall 4 structural prevention: the bridge
/// does not expose the frozen GS upscale field to Swift directly).
///
/// Hysteresis (D-04): smoothed-average frame time over the last 60 samples
/// > 22 ms → reduce one 0.25 step; < 14 ms → increase one 0.25 step toward
/// the ceiling.
///
/// Manual-change tracking (D-05): if the user changes UpscaleMultiplier
/// manually (Graphics tab, Q-Menu, QMENU-01 Test button), the new value
/// becomes the new `maxMultiplier` ceiling — adaptive only rescues from
/// drops below it. The ceiling is never lowered without explicit user action.
///
/// Hardcore RetroAchievements mode (D-06): no special handling. UpscaleMultiplier
/// is freely adjustable in Hardcore (matches existing Graphics tab behavior —
/// it's a graphics setting, not a speed/timing change). The controller's
/// writes go through the same path.
///
/// Per-game override (Plan 06 Task 2 option (a)): `poll()` reads the per-game
/// INI value via `ARMSX2Bridge.hasPerGameINIValueForCurrentGame(...)`; if
/// present, the per-game value overrides the global `enabled` flag for the
/// current game. The controller lifecycle (timer start/stop) tracks the
/// GLOBAL setting; the per-game override is consulted inside each poll so
/// mid-session per-game changes take effect within ~500 ms.
@MainActor
@Observable
final class FrameTimeDynamicResolutionController {
    static let shared = FrameTimeDynamicResolutionController()

    /// Drives the timer start/stop lifecycle. Bound to
    /// `SettingsStore.adaptiveResolutionEnabled`. The per-game override is
    /// read inside `poll()` (option (a) — see class docs).
    var enabled: Bool = false

    // MARK: - Tuning (D-04 verbatim)

    /// Polling interval — ~30 frames at 60 Hz (matches the Pacing HUD cadence
    /// and sits well above the 120 ms `requestGraphicsApply()` debounce).
    private static let pollInterval: TimeInterval = 0.5
    /// Minimum interval between resolution changes (D-04). Prevents texture
    /// cache thrash and GS pipeline stalls (T-4.1-17 mitigation).
    private static let minChangeInterval: TimeInterval = 0.5
    /// Step size — matches EMU-01 fractional steps from Phase 4 (D-04).
    private static let step: Float = 0.25
    /// Min clamp — never below native PS2 (D-04 + the m_nativeres-hack pitfall).
    private static let minMultiplier: Float = 1.0
    /// Smoothing window — last 60 samples (~1 second at 60 Hz) (D-04).
    private static let smoothingWindow: Int = 60
    /// Hysteresis thresholds in milliseconds (D-04 verbatim).
    private static let reduceThresholdMs: Float = 22.0
    private static let increaseThresholdMs: Float = 14.0
    /// Minimum non-zero sample count required to act. Below this the controller
    /// waits (EDGE-empty-3 — empty `PerformanceMetrics::GetFrameTimeHistory()`
    /// before the first ~30 frames land → no action until sufficient samples).
    private static let minSamplesForAction: Int = 60
    /// Window after one of our own writes during which a observed value change
    /// is treated as our echo, not a manual user change (D-05 detection helper).
    private static let ownWriteEchoWindow: TimeInterval = 1.0
    /// A change larger than this multiple of `step` between two polls (outside
    /// the own-write echo window) is treated as a manual user change (D-05).
    private static let manualChangeStepMultiple: Float = 1.5
    /// Per-game INI location (matches Plan 03's perGameAdaptiveResolution key).
    private static let perGameSection = "ARMSX2iOS/FramePacing"
    private static let perGameKey = "DynamicResolution"

    // MARK: - Internal state (not part of the observable surface)

    /// Max clamp — captured from `SettingsStore.shared.upscaleMultiplier` on
    /// enable (D-03). Bumped up if the user raises UpscaleMultiplier manually
    /// (D-05); never lowered without explicit user action.
    @ObservationIgnored private var maxMultiplier: Float = 1.0
    /// Last time the controller wrote `upscale_multiplier`. Used to enforce
    /// `minChangeInterval` (T-4.1-17 mitigation).
    @ObservationIgnored private var lastChangeAt: Date = .distantPast
    /// The value the controller last observed from `SettingsStore.shared.upscaleMultiplier`.
    @ObservationIgnored private var lastObservedMultiplier: Float = 1.0
    /// The value the controller last wrote. Used by the D-05 manual-change
    /// detector: if the observed value moves by more than a single step from
    /// this AND we didn't write recently, the user changed it.
    @ObservationIgnored private var lastWrittenValue: Float = 1.0
    /// Timestamp of the controller's most recent write. Used to suppress the
    /// D-05 manual-change flag for our own echo.
    @ObservationIgnored private var lastWriteAt: Date = .distantPast
    @ObservationIgnored private var pollTimer: Timer?

    private init() {}

    // MARK: - Lifecycle

    /// Called by `SettingsStore.adaptiveResolutionEnabled.didSet` on user
    /// toggle AND by the SettingsStore init body when the persisted INI value
    /// is read back at boot. Transitions are idempotent.
    func setEnabled(_ newValue: Bool) {
        guard newValue != enabled else { return }
        enabled = newValue
        if enabled {
            // D-03: capture the user's currently-configured UpscaleMultiplier
            // as the new max clamp. The controller only rescues from drops
            // below it (D-05).
            let current = SettingsStore.shared.upscaleMultiplier
            maxMultiplier = max(Self.minMultiplier, current)
            lastObservedMultiplier = current
            lastWrittenValue = current
            // Allow immediate action on the first qualifying poll — do not
            // force the user to wait 500 ms after toggling.
            lastChangeAt = .distantPast
            lastWriteAt = .distantPast
            startTimer()
        } else {
            stopTimer()
        }
    }

    private func startTimer() {
        guard pollTimer == nil else { return }
        // Canonical iOS pattern: Timer + common
        // run-loop mode so the tick continues during tracking (e.g. pad drag).
        // The Task { @MainActor in ... } hop preserves actor isolation.
        let timer = Timer(timeInterval: Self.pollInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.poll() }
        }
        RunLoop.main.add(timer, forMode: .common)
        pollTimer = timer
    }

    private func stopTimer() {
        pollTimer?.invalidate()
        pollTimer = nil
    }

    deinit {
        // `Timer.invalidate()` is safe to call from deinit; the controller is
        // @MainActor so by the time deinit runs the timer can no longer fire
        // into a stale self. `MainActor.assumeIsolated` documents that for the
        // Swift 6 nonisolated-deinit rule.
        MainActor.assumeIsolated {
            pollTimer?.invalidate()
        }
    }

    // MARK: - Poll

    private func poll() {
        // Per-game override (Plan 06 Task 2 option (a)). The controller's
        // lifecycle tracks the GLOBAL setting; the per-game value, when
        // present, overrides the global enable for the current game's runtime.
        // Per-game semantics: -1 (absent) → use global; 0 → force off for this
        // game; 1 → force on for this game.
        if ARMSX2Bridge.hasPerGameINIValueForCurrentGame(Self.perGameSection, key: Self.perGameKey) {
            let perGame = ARMSX2Bridge.getPerGameINIBoolForCurrentGame(
                Self.perGameSection,
                key: Self.perGameKey,
                defaultValue: enabled
            )
            guard perGame else { return }
        }

        // EDGE-empty-3: empty PerformanceMetrics::GetFrameTimeHistory() before
        // the first ~30 frames land → no action until sufficient samples.
        let history: [NSNumber] = ARMSX2Bridge.frameTimeHistory()
        let cursor: Int = Int(ARMSX2Bridge.frameTimeHistoryPos())
        let total: Int = history.count
        guard total > 0 else { return }

        // Collect the most recent `smoothingWindow` non-zero samples before
        // the cursor (wrap-around ring-buffer semantics, matching the HUD).
        var samples: [Float] = []
        samples.reserveCapacity(Self.smoothingWindow)
        for i in 0..<Self.smoothingWindow {
            let idx = ((cursor - 1 - i) % total + total) % total
            let value = history[idx].floatValue
            if value > 0 { samples.append(value) }
        }
        guard samples.count >= Self.minSamplesForAction else { return }

        let smoothed: Float = samples.reduce(0, +) / Float(samples.count)

        // D-05 manual-change tracking. If the user changed UpscaleMultiplier
        // manually (the value moved by more than a step-and-a-half from the
        // controller's last write AND we didn't write recently), the new value
        // becomes the new maxMultiplier ceiling — never lower the ceiling
        // without explicit user action.
        let currentMultiplier = SettingsStore.shared.upscaleMultiplier
        let now = Date()
        let insideOwnEchoWindow = now.timeIntervalSince(lastWriteAt) < Self.ownWriteEchoWindow
        let movedByMoreThanOneStep =
            abs(currentMultiplier - lastWrittenValue) > Self.step * Self.manualChangeStepMultiple
        if movedByMoreThanOneStep && !insideOwnEchoWindow {
            maxMultiplier = max(maxMultiplier, currentMultiplier)
        }
        lastObservedMultiplier = currentMultiplier

        // Enforce the 500 ms minimum interval between writes (T-4.1-17).
        let canChange = now.timeIntervalSince(lastChangeAt) >= Self.minChangeInterval

        // Hysteresis (D-04): > 22 ms → reduce one step; < 14 ms → increase one step.
        if smoothed > Self.reduceThresholdMs,
           currentMultiplier > Self.minMultiplier,
           canChange {
            let newValue = max(Self.minMultiplier, currentMultiplier - Self.step)
            guard newValue != currentMultiplier else { return }
            commitChange(newValue: newValue, now: now)
        } else if smoothed < Self.increaseThresholdMs,
                  currentMultiplier < maxMultiplier,
                  canChange {
            let newValue = min(maxMultiplier, currentMultiplier + Self.step)
            guard newValue != currentMultiplier else { return }
            commitChange(newValue: newValue, now: now)
        }
    }

    /// Writes through the existing ARMSX2Bridge path (T-4.1-16 mitigation —
    /// Pitfall 4 structural prevention: the bridge is the only path the
    /// controller uses; the frozen GS upscale field is not exposed to Swift
    /// directly). Also mirrors the value into
    /// SettingsStore.shared.upscaleMultiplier so the Graphics tab reflects
    /// the controller's writes live; the SettingsStore didSet writes the
    /// same INI key via the same bridge path (a benign idempotent overwrite)
    /// and triggers `requestGraphicsApply()` which coalesces the GS pipeline
    /// reload.
    private func commitChange(newValue: Float, now: Date) {
        ARMSX2Bridge.setINIFloat("EmuCore/GS", key: "upscale_multiplier", value: newValue)
        // Mirror into SettingsStore so the Graphics tab / Q-Menu display
        // tracks the controller. The Setting<Float> didSet re-writes the INI
        // key (idempotent) and requests a graphics-apply (debounced 120 ms).
        SettingsStore.shared.upscaleMultiplier = newValue
        lastWrittenValue = newValue
        lastObservedMultiplier = newValue
        lastChangeAt = now
        lastWriteAt = now
    }
}
