// FramePacingHUDModel.swift — @Observable polling model for the Pacing HUD overlay
// SPDX-License-Identifier: GPL-3.0+

import Foundation

/// `@MainActor @Observable` polling model that backs the in-game Pacing HUD overlay.
///
/// Polls `ARMSX2Bridge.frameTimeHistory()` + `ARMSX2Bridge.audioBufferHealthMs()` every
/// 500 ms (~30 frames at 60 Hz) and publishes the derived readouts the HUD renders. The
/// bridge methods are read-only wrappers (PerformanceMetrics frame-time history + SPU2
/// stream state) and are safe to call on the main thread per RESEARCH §A4.
///
/// Empty state (UI-SPEC E6): `hasData == false` until the first poll completes with at
/// least 30 non-zero frame-time samples; the HUD renders an em-dash for every readout
/// in that state. The audio readout independently renders an em-dash whenever
/// `audioBufferMs < 0` (e.g. when the SPU2 stream-state read path is unavailable).
@MainActor
@Observable
final class FramePacingHUDModel {
    /// Integer frames-per-second derived from the median frame time of the last ~60 samples.
    var fps: Int = 0
    /// Median frame time in milliseconds.
    var frameTimeMs: Float = 0
    /// 1% low frame time in milliseconds (worst frame in the slowest 1% of the window).
    var onePercentLowMs: Float = 0
    /// 0.1% low frame time in milliseconds (worst frame in the slowest 0.1% of the window).
    var pointOnePercentLowMs: Float = 0
    /// SPU2/cubeb output stream buffered audio in milliseconds, or -1 when unavailable.
    var audioBufferMs: Int = -1
    /// False until the first poll completes with enough non-zero frame-time samples.
    /// Drives the em-dash empty state for the FPS / Frame / 1% / 0.1% readouts.
    var hasData: Bool = false

    @ObservationIgnored private var pollTimer: Timer?

    /// Number of recent samples to inspect (≈1 second at 60 Hz). The bridge returns 150;
    /// we look at the freshest `sampleWindow` of those.
    private static let sampleWindow = 60
    /// Minimum non-zero sample count required to publish frame-time-derived readouts.
    /// Below this the HUD stays in em-dash state for the frame-time readouts.
    private static let minSamplesForFrameTime = 30
    /// Polling interval — ~30 frames at 60 Hz, well above the `requestGraphicsApply()`
    /// 120 ms debounce so the timer cannot thrash the GS settings reload (T-4.1-10).
    private static let pollInterval: TimeInterval = 0.5

    func startPolling() {
        guard pollTimer == nil else { return }
        // Fire once immediately so the first readouts appear without the 500 ms wait,
        // then schedule the repeating tick on the main run loop.
        poll()
        let timer = Timer(timeInterval: Self.pollInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.poll() }
        }
        RunLoop.main.add(timer, forMode: .common)
        pollTimer = timer
    }

    func stopPolling() {
        pollTimer?.invalidate()
        pollTimer = nil
    }

    deinit {
        // `Timer.invalidate()` is safe to call from deinit; the model is @MainActor so
        // by the time deinit runs the timer can no longer fire into a stale `self`.
        // `MainActor.assumeIsolated` documents that for the Swift 6 nonisolated-deinit rule.
        MainActor.assumeIsolated {
            pollTimer?.invalidate()
        }
    }

    // MARK: - Polling

    private func poll() {
        let history: [NSNumber] = ARMSX2Bridge.frameTimeHistory()
        let cursor: Int = Int(ARMSX2Bridge.frameTimeHistoryPos())
        let total: Int = history.count
        guard total > 0 else { hasData = false; return }

        // Collect the most recent `sampleWindow` samples before the cursor, wrapping
        // around the ring buffer if the cursor is near the start.
        var recent: [Float] = []
        recent.reserveCapacity(Self.sampleWindow)
        for i in 0..<Self.sampleWindow {
            let idx = ((cursor - 1 - i) % total + total) % total
            let value = history[idx].floatValue
            if value > 0 { recent.append(value) }
        }

        // Below the threshold → em-dash state; do not update frame-time-derived readouts.
        guard recent.count >= Self.minSamplesForFrameTime else {
            hasData = false
            audioBufferMs = Int(ARMSX2Bridge.audioBufferHealthMs())
            return
        }

        // Median frame time of the valid samples. We sort descending so index 0 is the
        // worst (slowest) frame; the median is the middle of the sorted window.
        let sortedDescending = recent.sorted(by: >)
        let median = sortedDescending[sortedDescending.count / 2]

        // 1% / 0.1% lows via the standard "sort + pick index" formula over the valid
        // sample count (RESEARCH §Don't Hand-Roll). For a 60-sample window both indices
        // floor to 0 — the worst sample — which is the expected floor behavior.
        let onePercentIdx = max(0, Int(Double(sortedDescending.count) * 0.01))
        let pointOnePercentIdx = max(0, Int(Double(sortedDescending.count) * 0.001))

        frameTimeMs = median
        fps = median > 0 ? Int((1000.0 / median).rounded()) : 0
        onePercentLowMs = sortedDescending[onePercentIdx]
        pointOnePercentLowMs = sortedDescending[pointOnePercentIdx]
        audioBufferMs = Int(ARMSX2Bridge.audioBufferHealthMs())
        hasData = true
    }
}
