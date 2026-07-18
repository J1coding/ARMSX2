// SettingsStore+FramePacing.swift — frame pacing preset table + new-default migration
// SPDX-License-Identifier: GPL-3.0+

import Foundation

extension SettingsStore {
    /// D-01 preset value table (locked in 04.1-CONTEXT.md). The apply switch in
    /// SettingsStore.applyFramePacingPreset(_:) reads from here for the actual
    /// Setting<T> writes; Plan 02's per-preset details sheet reads from here for
    /// the human-readable value summary.
    struct FramePacingPresetValues: Sendable {
        let vsyncQueueSize: Int
        let audioOutputLatencyMs: Int
        let audioBufferMs: Int
        let targetFPS: Int
        let syncToHostRefresh: Bool
        let frameLimiterEnabled: Bool
    }

    static let framePacingPresetTable: [FramePacingPreset: FramePacingPresetValues] = [
        .optimal:      .init(vsyncQueueSize: 4, audioOutputLatencyMs: 15, audioBufferMs:  50, targetFPS: 60, syncToHostRefresh: false, frameLimiterEnabled: true),
        .smooth:       .init(vsyncQueueSize: 8, audioOutputLatencyMs: 20, audioBufferMs:  75, targetFPS: 60, syncToHostRefresh: false, frameLimiterEnabled: true),
        .lowLatency:   .init(vsyncQueueSize: 2, audioOutputLatencyMs: 10, audioBufferMs:  30, targetFPS: 60, syncToHostRefresh: false, frameLimiterEnabled: true),
        .batterySaver: .init(vsyncQueueSize: 8, audioOutputLatencyMs: 30, audioBufferMs: 100, targetFPS: 45, syncToHostRefresh: false, frameLimiterEnabled: true),
    ]

    /// D-02 migration: smart-detect whether to apply the new Optimal default.
    ///
    /// PCSX2 v1.0 defaults (the comparator):
    ///   VsyncQueueSize=8, OutputLatencyMS=20, BufferMS=50, targetFPS=60,
    ///   syncToHostRefresh=false, frameLimiterEnabled=true.
    ///
    /// - All six equal defaults → fresh install on defaults. Set the preset INI
    ///   key to .optimal and apply the D-01 Optimal table.
    /// - Any differs → returning customized user. Set the preset INI key to
    ///   .custom and PRESERVE the user's values (do not call apply — that would
    ///   overwrite their tuning).
    /// Either way, write the migration flag true unconditionally so this runs
    /// exactly once per install.
    static func migrateFramePacingOptimalDefaultV1() {
        let migrated = ARMSX2Bridge.getINIBool("ARMSX2iOS/Migrations", key: "FramePacingOptimalDefaultV1", defaultValue: false)
        if migrated { return }

        // PCSX2 v1.0 default values double as the smart-detect comparator: if
        // the user hasn't overridden any of them, this is a fresh install (or a
        // returning user who happens to agree with v1.0); both get Optimal.
        let vsyncQueueSize = Int(ARMSX2Bridge.getINIInt("EmuCore/GS", key: "VsyncQueueSize", defaultValue: 8))
        let outputLatencyMs = Int(ARMSX2Bridge.getINIInt("SPU2/Output", key: "OutputLatencyMS", defaultValue: 20))
        let bufferMs = Int(ARMSX2Bridge.getINIInt("SPU2/Output", key: "BufferMS", defaultValue: 50))
        let nominalScalar = ARMSX2Bridge.getINIFloat("Framerate", key: "NominalScalar", defaultValue: 1.0)
        let syncToHostRefresh = ARMSX2Bridge.getINIBool("EmuCore/GS", key: "SyncToHostRefreshRate", defaultValue: false)

        // Derive frameLimiterEnabled + targetFPS from NominalScalar the same way
        // init does. NominalScalar 1.0 ↔ frameLimiterEnabled=true + targetFPS=60
        // on a 59.94 Hz NTSC base. Any other scalar counts as customized.
        let limiterEnabled = (nominalScalar > 0.05 && nominalScalar < 10.0)
        let targetFPS = Int((nominalScalar * 59.94).rounded())

        let allDefaults =
            vsyncQueueSize == 8 &&
            outputLatencyMs == 20 &&
            bufferMs == 50 &&
            syncToHostRefresh == false &&
            limiterEnabled == true &&
            targetFPS == 60

        if allDefaults {
            ARMSX2Bridge.setINIInt("ARMSX2iOS/FramePacing", key: "Preset", value: Int32(FramePacingPreset.optimal.rawValue))
            NSLog("[ARMSX2 iOS Settings] Frame Pacing migration: applying Optimal preset")
            SettingsStore.shared.applyFramePacingPreset(.optimal)
        } else {
            ARMSX2Bridge.setINIInt("ARMSX2iOS/FramePacing", key: "Preset", value: Int32(FramePacingPreset.custom.rawValue))
            NSLog("[ARMSX2 iOS Settings] Frame Pacing migration: preserving user values as Custom")
        }

        ARMSX2Bridge.setINIBool("ARMSX2iOS/Migrations", key: "FramePacingOptimalDefaultV1", value: true)
    }
}
