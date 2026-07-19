// FramePacingHUDOverlay.swift — SwiftUI overlay rendering live frame-time + audio readouts
// SPDX-License-Identifier: GPL-3.0+

import SwiftUI

/// SwiftUI overlay that floats over `MetalGameView` and renders the Pacing HUD strip:
/// five live readouts (FPS / Frame / 1% / 0.1% / Audio) plus the verbatim QMENU-01
/// footer warning. The overlay is gated behind the existing `osdShowFrameTimes` toggle
/// at the call site (per Plan 04 Task 2 — see `GameScreenView`); casual users see only
/// the game.
///
/// Design references (UI-SPEC):
/// - Q4 LOCKED readout labels + formats (FPS integer; Frame/1%/0.1% `XX.X ms`; Audio `XX ms`).
/// - E6 empty state — em-dash for every readout until the model publishes data.
/// - §Color reserved-for — the audio readout flips to `OverlayTheme.warm` below 10 ms
///   (imminent underrun caution); never used elsewhere on the HUD.
/// - §Typography — numerics use `.font(.body.monospacedDigit())` to prevent jitter as
///   the values stream; labels use the Caption role.
/// - QMENU-01 footer warning verbatim — `Diagnostics can disrupt gameplay. Turn off if
///   you see stutter.`
///
/// The overlay uses `OverlayTheme` tokens for the backing panel (it sits over a Metal
/// game surface, not inside a SwiftUI Form) — never system semantic colors.
struct FramePacingHUDOverlay: View {
    @Bindable var model: FramePacingHUDModel

    private static let audioCautionThresholdMs: Int = 10

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            readoutStrip
            footer
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(
            OverlayTheme.card.opacity(0.85)
                .inset(by: 0.5)
        )
        .background(OverlayFrostBackground())
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(OverlayTheme.cardTopHighlight, lineWidth: 1)
        )
        .shadow(color: OverlayTheme.cardShadow, radius: 4, x: 0, y: 2)
        .padding(.horizontal, 16)
        .padding(.top, 16)
        .frame(maxWidth: .infinity, alignment: .top)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
    }

    // MARK: - Readout strip

    private var readoutStrip: some View {
        HStack(alignment: .top, spacing: 12) {
            readoutCell(label: "FPS", value: fpsText)
            readoutCell(label: "Frame", value: frameText)
            readoutCell(label: "1%", value: onePercentText)
            readoutCell(label: "0.1%", value: pointOnePercentText)
            readoutCell(label: "Audio", value: audioText, valueColor: audioColor)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func readoutCell(
        label: String,
        value: String,
        valueColor: Color = OverlayTheme.textPrimary
    ) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label)
                .font(.footnote)
                .foregroundStyle(OverlayTheme.textSecondary)
            Text(value)
                .font(.body.monospacedDigit())
                .foregroundStyle(valueColor)
                .lineLimit(1)
                .truncationMode(.tail)
        }
    }

    // MARK: - Footer

    private var footer: some View {
        Text("Diagnostics can disrupt gameplay. Turn off if you see stutter.")
            .font(.footnote)
            .foregroundStyle(OverlayTheme.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Value formatters (UI-SPEC Q4 LOCKED)

    private var fpsText: String {
        model.hasData ? "\(model.fps)" : "—"
    }

    private var frameText: String {
        model.hasData ? String(format: "%.1f ms", model.frameTimeMs) : "—"
    }

    private var onePercentText: String {
        model.hasData ? String(format: "%.1f ms", model.onePercentLowMs) : "—"
    }

    private var pointOnePercentText: String {
        model.hasData ? String(format: "%.1f ms", model.pointOnePercentLowMs) : "—"
    }

    private var audioText: String {
        // The audio readout has its own em-dash state — independent of the frame-time
        // `hasData` flag — so a missing SPU2 read path (audioBufferMs < 0) renders an
        // em-dash even when the rest of the HUD is populated.
        guard model.audioBufferMs >= 0 else { return "—" }
        return "\(model.audioBufferMs) ms"
    }

    private var audioColor: Color {
        // Per UI-SPEC §Color reserved-for: the audio readout flips to caution orange
        // when buffer health drops below the safe minimum (imminent underrun).
        guard model.audioBufferMs >= 0, model.audioBufferMs < Self.audioCautionThresholdMs else {
            return OverlayTheme.textPrimary
        }
        return OverlayTheme.warm
    }

    // MARK: - Accessibility

    private var accessibilityLabel: String {
        var parts: [String] = []
        if model.hasData {
            parts.append("FPS \(model.fps)")
            parts.append(String(format: "Frame %.1f ms", model.frameTimeMs))
            parts.append(String(format: "1%% low %.1f ms", model.onePercentLowMs))
            parts.append(String(format: "0.1%% low %.1f ms", model.pointOnePercentLowMs))
        } else {
            parts.append("Frame pacing warming up")
        }
        if model.audioBufferMs >= 0 {
            parts.append("Audio buffer \(model.audioBufferMs) ms")
        }
        return "Pacing HUD: " + parts.joined(separator: ", ")
    }
}
