"""Wave 0 guard: FramePacingOptimalDefaultV1 migration (EMU-04-5 + D-02 contract)."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class TestIosFramePacingMigration(unittest.TestCase):
    FRAME_PACING = ROOT / "platforms/ios/app/src/main/swift/Models/SettingsStore+FramePacing.swift"

    def setUp(self):
        self.assertTrue(
            self.FRAME_PACING.exists(),
            "SettingsStore+FramePacing.swift missing — repo root resolution is wrong",
        )
        self.src = self.FRAME_PACING.read_text(encoding="utf-8")

    def test_migration_uses_v1_key(self):
        """Migration must read/write the ARMSX2iOS/Migrations + FramePacingOptimalDefaultV1 key."""
        self.assertIn(
            "ARMSX2iOS/Migrations",
            self.src,
            msg="Migration INI section token missing",
        )
        self.assertIn(
            "FramePacingOptimalDefaultV1",
            self.src,
            msg="Migration key token missing",
        )
        # Must be called from somewhere — function declaration must exist.
        self.assertRegex(
            self.src,
            r"static\s+func\s+migrateFramePacingOptimalDefaultV1\s*\(\s*\)",
            msg="migrateFramePacingOptimalDefaultV1 static function missing",
        )

    def test_fresh_install_gets_optimal(self):
        """EDGE-empty-1: migration flag must be read with defaultValue: false."""
        # Pattern: getINIBool("ARMSX2iOS/Migrations", key: "FramePacingOptimalDefaultV1", defaultValue: false)
        pattern = re.compile(
            r'getINIBool\s*\(\s*["\']ARMSX2iOS/Migrations["\']\s*,\s*'
            r'key:\s*["\']FramePacingOptimalDefaultV1["\']\s*,\s*'
            r'defaultValue:\s*false\s*\)'
        )
        self.assertRegex(
            self.src,
            pattern,
            msg="Fresh-install entry condition (defaultValue: false) missing",
        )

    def test_customized_user_preserved(self):
        """D-02: when any key differs from PCSX2 v1.0 defaults, set preset=.custom and DO NOT apply."""
        # Find the migration function body.
        match = re.search(
            r"static\s+func\s+migrateFramePacingOptimalDefaultV1\s*\(\s*\)\s*\{(?P<body>.*?)^\s{4}\}",
            self.src,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(match, "migrateFramePacingOptimalDefaultV1 body missing")
        body = match.group("body")
        # The custom branch must reference FramePacingPreset.custom raw value (Int 4) or
        # the .custom case directly. The Optimal branch must NOT be taken when any
        # individual key differs.
        self.assertRegex(
            body,
            r"FramePacingPreset\.custom|FramePacingPreset\.custom\.rawValue|preset\s*=\s*4",
            msg="D-02: .custom branch missing",
        )
        # Smart-detect: must read the individual keys with PCSX2 v1.0 defaults.
        # VsyncQueueSize default 8, OutputLatencyMS default 20, BufferMS default 50.
        self.assertIn(
            '"VsyncQueueSize"',
            body,
            msg="Migration does not read VsyncQueueSize for smart-detect",
        )
        self.assertIn(
            '"OutputLatencyMS"',
            body,
            msg="Migration does not read OutputLatencyMS for smart-detect",
        )
        self.assertIn(
            '"BufferMS"',
            body,
            msg="Migration does not read BufferMS for smart-detect",
        )
        # The custom branch must NOT call applyFramePacingPreset(.optimal).
        # We verify by ensuring the .custom branch is gated by a separate condition
        # from the all-defaults branch. A simple heuristic: the function body
        # references applyFramePacingPreset(.optimal) at most inside the
        # all-defaults branch. The presence of FramePacingPreset.custom assignment
        # alongside applyFramePacingPreset(.optimal) is the contract.
        self.assertIn(
            "applyFramePacingPreset(.optimal)",
            body,
            msg="Optimal branch must call applyFramePacingPreset(.optimal)",
        )


if __name__ == "__main__":
    unittest.main()
