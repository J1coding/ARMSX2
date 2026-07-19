"""Wave 0 guard: per-game preset Picker cascades the D-01 row (EMU-04-3 / gap #2).

The save handler at PerGameSettingsPanel.swift:savePerGameCompatibility wrote
ONLY the `ARMSX2iOS/FramePacing/Preset=N` metadata key. The PCSX2 core does
not consume that metadata key — it reads the canonical individual keys
(`EmuCore/GS/VsyncQueueSize`, `SPU2/Output/OutputLatencyMS`,
`SPU2/Output/BufferMS`, `EmuCore/GS/SyncToHostRefreshRate`). Picking a named
preset per-game was therefore silently ignored at runtime.

This guard pins the cascade: when a named preset (raw value 0...3) is picked
per-game, the save handler must ALSO write the D-01 row's four cascadeable
individual per-game keys, sourced from SettingsStore.framePacingPresetTable.
The .custom branch (raw 4) and Use Global (-1) skip the cascade — only the
four named presets cascade.

Closes gap #2 from 04.1-VERIFICATION.md (CR-02 BLOCKER).
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class TestIosPerGamePresetCascade(unittest.TestCase):
    PANEL = ROOT / "platforms/ios/app/src/main/swift/Views/PerGameSettingsPanel.swift"

    # The four cascadeable per-game section/key pairs (Int x3, Bool x1). Float
    # keys (frameLimiterEnabled, targetFPS) are deliberately excluded — the
    # per-game bridge has no Float variant (Plan 03 Rule 4 deferral).
    CASCADE_INT_PAIRS = (
        '"EmuCore/GS", "VsyncQueueSize"',
        '"SPU2/Output", "OutputLatencyMS"',
        '"SPU2/Output", "BufferMS"',
    )
    CASCADE_BOOL_PAIRS = (
        '"EmuCore/GS", "SyncToHostRefreshRate"',
    )

    def setUp(self):
        self.assertTrue(
            self.PANEL.exists(),
            "PerGameSettingsPanel.swift missing — repo root resolution is wrong",
        )
        self.src = self.PANEL.read_text(encoding="utf-8")

    def test_save_handler_writes_named_preset_metadata_key(self):
        """Sanity (pre-existing behavior, locks the anchor): the save handler
        writes the `ARMSX2iOS/FramePacing` `Preset` metadata key. Without this,
        the cascade branch added in Plan 07 has nothing to gate on."""
        body = self._save_body()
        self.assertIsNotNone(body, msg="savePerGameCompatibility() body could not be isolated")
        self.assertIn(
            '"ARMSX2iOS/FramePacing", "Preset"',
            body,
            msg="save handler missing the ARMSX2iOS/FramePacing Preset metadata write",
        )

    def test_save_handler_cascades_named_preset_individual_keys(self):
        """The cascade must read the D-01 row from SettingsStore.framePacingPresetTable
        and write the four cascadeable per-game individual keys. Asserting
        `framePacingPresetTable` is present in the save body proves the cascade
        reads the locked source-of-truth (not hardcoded literal values), and
        asserting each of the four section/key pairs proves all four writes
        are present."""
        body = self._save_body()
        self.assertIsNotNone(body, msg="savePerGameCompatibility() body could not be isolated")
        # Cascade must reference the D-01 source-of-truth.
        self.assertIn(
            "framePacingPresetTable",
            body,
            msg=(
                "save handler does not reference SettingsStore.framePacingTable — "
                "the cascade is not reading the D-01 source-of-truth (gap #2 not closed)"
            ),
        )
        # All four cascadeable section/key pairs must be referenced.
        for pair in self.CASCADE_INT_PAIRS + self.CASCADE_BOOL_PAIRS:
            self.assertIn(
                pair,
                body,
                msg=f"save handler missing cascade write for section/key {pair}",
            )

    def test_save_handler_gates_cascade_on_named_presets_only(self):
        """The cascade must be gated so that raw value 4 (.custom) and -1 (Use
        Global) skip the four cascade writes. Acceptable evidence: an explicit
        numeric comparison (`!= 4`, `<= 3`, `range(0...3)`), OR — preferred —
        a `FramePacingPreset(rawValue: perGameFramePacingPreset)` lookup that
        returns nil for raw values outside 0...3 (Use Global=-1 fails the
        constructor; .custom=4 succeeds the constructor but
        framePacingPresetTable[.custom] returns nil). The table-lookup form is
        the natural gate because it excludes both branches with one check.

        This test first verifies the cascade is present (framePacingPresetTable
        referenced), then verifies it is gated. Without the cascade, the gate
        check is meaningless — and a pre-existing `!= -1` (Use Global) branch
        must NOT be confused for a cascade gate."""
        body = self._save_body()
        self.assertIsNotNone(body, msg="savePerGameCompatibility() body could not be isolated")
        # The cascade must exist before we can verify its gate. The bare
        # perGameFramePacingPreset != -1 (Use Global) check that exists in the
        # unwired save body is NOT a cascade gate — it only gates the metadata
        # write. The cascade gate must be structurally distinct.
        self.assertIn(
            "framePacingPresetTable",
            body,
            msg=(
                "cannot verify cascade gate — save handler has no "
                "framePacingPresetTable reference (cascade not wired)"
            ),
        )
        # Preferred form: FramePacingPreset(rawValue:) constructor — naturally
        # excludes raw -1 (Use Global) AND, combined with the table lookup,
        # raw 4 (.custom) because the table has no .custom entry.
        raw_value_gate = re.search(
            r"FramePacingPreset\s*\(\s*rawValue\s*:\s*perGameFramePacingPreset\s*\)",
            body,
        )
        if raw_value_gate:
            return
        # Alternative form: explicit numeric comparison that bounds the cascade
        # to named presets only (excludes .custom=4 and/or Use Global=-1).
        numeric_gate = re.search(
            r"perGameFramePacingPreset\s*(!=|<=|<|==)\s*(0|3|4)",
            body,
        )
        if numeric_gate:
            return
        # Or an explicit FramePacingPreset.<case> reference inside a comparison.
        case_gate = re.search(
            r"perGameFramePacingPreset\s*(!=|<=|<|==)\s*FramePacingPreset\.\w+",
            body,
        )
        if case_gate:
            return
        self.fail(
            msg=(
                "cascade is present (framePacingPresetTable referenced) but no "
                "gate excluding .custom (raw 4) was found — need "
                "FramePacingPreset(rawValue:) OR a numeric != 4 / <= 3 check"
            ),
        )

    # ── Helpers ──

    def _save_body(self):
        """Isolate the savePerGameCompatibility() function body. Mirrors the
        perGameFingerprint regex idiom from test_ios_per_game_fingerprint.py
        but scoped to a void function (no return type annotation)."""
        # First try with the common private/static/nonisolated func modifiers.
        match = re.search(
            r"func\s+savePerGameCompatibility\s*\([^)]*\)\s*\{(?P<body>.*?)^\s{4}\}",
            self.src,
            re.DOTALL | re.MULTILINE,
        )
        if match:
            return match.group("body")
        return None


if __name__ == "__main__":
    unittest.main()
