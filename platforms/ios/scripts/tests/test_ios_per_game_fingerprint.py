"""Wave 0 guard: per-game Frame Pacing fingerprint extension (D-12 + Pitfall 3).

Scaffolded here, enforced starting in Plan 03. The literal per-game Frame
Pacing keys (`perGameFramePacingPreset`, `perGameAdaptiveResolution`) are
added to PerGameSettingsPanel.swift in Plan 03; this guard turns green at
that point and prevents later regressions.
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class TestIosPerGameFingerprint(unittest.TestCase):
    PANEL = ROOT / "platforms/ios/app/src/main/swift/Views/PerGameSettingsPanel.swift"

    def setUp(self):
        self.assertTrue(
            self.PANEL.exists(),
            "PerGameSettingsPanel.swift missing — repo root resolution is wrong",
        )
        self.src = self.PANEL.read_text(encoding="utf-8")

    def test_per_game_fingerprint_contains_new_keys(self):
        """D-12: perGameFingerprint() body must contain the two new literal tokens."""
        # Find perGameFingerprint() body.
        match = re.search(
            r"func\s+perGameFingerprint\s*\(\s*\)\s*->\s*String\s*\{(?P<body>.*?)^\s{4}\}",
            self.src,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(
            match,
            msg="perGameFingerprint() function is missing",
        )
        body = match.group("body")
        self.assertIn(
            "perGameFramePacingPreset",
            body,
            msg="perGameFingerprint missing perGameFramePacingPreset token (D-12 / Pitfall 3)",
        )
        self.assertIn(
            "perGameAdaptiveResolution",
            body,
            msg="perGameFingerprint missing perGameAdaptiveResolution token (D-12 / Pitfall 3)",
        )


if __name__ == "__main__":
    unittest.main()
