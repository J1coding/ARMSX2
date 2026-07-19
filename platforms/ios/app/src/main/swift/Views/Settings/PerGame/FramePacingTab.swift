// FramePacingTab.swift — per-game Frame Pacing overrides (mirrors global FramePacingSettingsView with Use-Global tags)
// SPDX-License-Identifier: GPL-3.0+

import SwiftUI

struct FramePacingTab: View {
    @Binding var enabled: Bool
    let settings: SettingsStore

    // Per-game Frame Pacing-specific keys (D-10).
    @Binding var perGameFramePacingPreset: Int
    @Binding var perGameAdaptiveResolution: Int

    // Per-game individual-control bindings shared with GraphicsTab / AudioTab.
    // They live on PerGameSettingsPanel; this tab surfaces them under the
    // Frame Pacing banner alongside the preset + adaptive keys.
    @Binding var perGameVsyncQueue: Int
    @Binding var perGameSyncToHostRefresh: Int
    @Binding var perGameBufferMS: Int
    @Binding var perGameOutputLatencyMS: Int

    // The Reset dialog state lives on PerGameSettingsPanel so the destructive
    // action can reset every per-game Frame Pacing key at once. This binding
    // triggers the parent's .confirmationDialog.
    @Binding var showResetConfirmation: Bool

    var body: some View {
        PerGameTab(title: settings.localized("Frame Pacing")) {
            if showsCustomDirtyCaption {
                Text(settings.localized("You've changed individual settings. Pick a preset to return to its values."))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section {
                Picker(settings.localized("Preset"), selection: $perGameFramePacingPreset) {
                    Text(settings.localized("Use Global")).tag(-1)
                    ForEach(FramePacingPreset.allCases) { preset in
                        Text(settings.localized(preset.label)).tag(preset.rawValue)
                    }
                }
                .disabled(!enabled)

                Text(settings.localized("Global preset:") + " " + settings.localized(settings.framePacingPreset.label))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } header: {
                Text(settings.localized("Preset"))
            }

            Section {
                Picker(settings.localized("VSync Queue Size"), selection: $perGameVsyncQueue) {
                    Text(settings.localized("Use Global")).tag(-1)
                    ForEach([2, 3, 4, 5, 6, 8, 10, 12, 16], id: \.self) { Text("\($0)").tag($0) }
                }
                .disabled(!enabled)

                Picker(settings.localized("Sync to Host Refresh"), selection: $perGameSyncToHostRefresh) {
                    Text(settings.localized("Use Global")).tag(-1)
                    Text(settings.localized("Off")).tag(0)
                    Text(settings.localized("On")).tag(1)
                }
                .disabled(!enabled)
                Text(settings.localized("Sync to Host Refresh needs a restart to take effect."))
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Picker(settings.localized("Buffer Size"), selection: $perGameBufferMS) {
                    Text(settings.localized("Use Global")).tag(-1)
                    ForEach([10, 25, 50, 75, 100, 150, 200], id: \.self) { Text("\($0) ms").tag($0) }
                }
                .disabled(!enabled)

                Picker(settings.localized("Output Latency"), selection: $perGameOutputLatencyMS) {
                    Text(settings.localized("Use Global")).tag(-1)
                    ForEach([5, 10, 20, 30, 50, 100, 200], id: \.self) { Text("\($0) ms").tag($0) }
                }
                .disabled(!enabled)
            } header: {
                Text(settings.localized("Individual Settings"))
            }

            Section {
                Picker(settings.localized("Adaptive Resolution"), selection: $perGameAdaptiveResolution) {
                    Text(settings.localized("Use Global")).tag(-1)
                    Text(settings.localized("Off")).tag(0)
                    Text(settings.localized("On")).tag(1)
                }
                .disabled(!enabled)

                Text(settings.localized("Lowers internal resolution when frame time spikes, then raises it when things settle. Useful for heavy games; can flicker briefly on step changes. Off by default."))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if perGameAdaptiveResolution == 1 {
                    Text(settings.localized("Some games object to mid-session resolution changes. Turn this off if you see flicker or texture glitches."))
                        .font(.caption)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } header: {
                Text(settings.localized("Adaptive Resolution"))
            }

            Section {
                Button(role: .destructive) {
                    showResetConfirmation = true
                } label: {
                    Text(settings.localized("Reset Per-Game Frame Pacing"))
                }
                .disabled(!enabled)
            }
        }
    }

    /// UI-SPEC E8 partial-state caption. Surface the Q6 dirty caption when this
    /// game has overridden any individual control while the preset is still Use
    /// Global, OR when the preset itself is Custom (case 4).
    private var showsCustomDirtyCaption: Bool {
        if perGameFramePacingPreset == FramePacingPreset.custom.rawValue { return true }
        if perGameFramePacingPreset != -1 { return false }
        return perGameVsyncQueue != -1
            || perGameSyncToHostRefresh != -1
            || perGameBufferMS != -1
            || perGameOutputLatencyMS != -1
            || perGameAdaptiveResolution != -1
    }
}
