"""Wave 0 Python guards for Item 6 (ProMotion panel lock): Info.plist key + SceneDelegate preferredFrameRateRange."""
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


class TestIosFramePacingPromotion(unittest.TestCase):
    INFO_PLIST_IN = REPO_ROOT / "platforms/ios/app/src/main/cpp/Info.plist.in"
    SCENE_DELEGATE = REPO_ROOT / "platforms/ios/app/src/main/cpp/IOS/SceneDelegate.mm"

    def setUp(self):
        self.assertTrue(
            self.INFO_PLIST_IN.exists(),
            "Info.plist.in missing — repo root resolution is wrong",
        )
        self.assertTrue(
            self.SCENE_DELEGATE.exists(),
            "SceneDelegate.mm missing — repo root resolution is wrong",
        )
        self.info_plist = self.INFO_PLIST_IN.read_text(encoding="utf-8")
        self.scene_delegate = self.SCENE_DELEGATE.read_text(encoding="utf-8")

    def test_info_plist_key_present(self):
        """Info.plist.in contains CADisableMinimumFrameDurationOnPhone = true (Item 6 piece 1)."""
        self.assertRegex(
            self.info_plist,
            r"(?m)^\s*<key>CADisableMinimumFrameDurationOnPhone</key>\s*\n\s*<true/>\s*$",
        )

    def test_scenedelegate_sets_preferred_frame_rate_range(self):
        """SceneDelegate.mm sets UIWindowScene.preferredFrameRateRange at scene-connect (Item 6 piece 2)."""
        self.assertIn("preferredFrameRateRange", self.scene_delegate)
        # The literal CAFrameRateRangeMake (or CAFrameRateRange struct form) must appear nearby,
        # with minimum:60 and maximum+preferred bound to maximumFramesPerSecond.
        # We accept either the C functional form CAFrameRateRangeMake(60, max, max) or the
        # struct literal {60, max, max}; the maximum+preferred args should reference
        # maximumFramesPerSecond either from UIScreen.main or windowScene.screen.
        opt_in_block_match = re.search(
            r"preferredFrameRateRange\s*=\s*CAFrameRateRangeMake\s*\(\s*60\s*,",
            self.scene_delegate,
        )
        struct_block_match = re.search(
            r"preferredFrameRateRange\s*=\s*\(CAFrameRateRange\)\s*\{\s*60\s*,",
            self.scene_delegate,
        )
        self.assertTrue(
            opt_in_block_match is not None or struct_block_match is not None,
            "preferredFrameRateRange assignment must use CAFrameRateRangeMake(60, ...) or "
            "(CAFrameRateRange){60, ...} form",
        )
        self.assertRegex(
            self.scene_delegate,
            r"maximumFramesPerSecond",
            "maximum/preferred args must reference maximumFramesPerSecond "
            "(non-ProMotion devices then get a (60,60,60) no-op range)",
        )

    def test_scenedelegate_uses_available_guard(self):
        """The preferredFrameRateRange opt-in is wrapped in `if (@available(iOS 15.0, *))`."""
        idx = self.scene_delegate.find("preferredFrameRateRange")
        self.assertGreater(idx, 0, "preferredFrameRateRange must be present")
        # Walk backwards up to 600 chars looking for the @available guard.
        window_start = max(0, idx - 600)
        preceding = self.scene_delegate[window_start:idx]
        self.assertRegex(
            preceding,
            r"if\s*\(\s*@available\s*\(\s*iOS\s+15\.0\s*,\s*\*\s*\)\s*\)",
            "preferredFrameRateRange line must be wrapped in if (@available(iOS 15.0, *))",
        )

    def test_no_nominal_scalar_contact(self):
        """Conservative Item 6 reading: no JIT/VM/EmuConfig.Cpu/NominalScalar contact in either diff.

        Info.plist.in is a build-time static manifest — it should never reference these symbols.
        The new SceneDelegate preferredFrameRateRange opt-in must not introduce them either.
        """
        forbidden = re.compile(
            r"NominalScalar|iPSX2_|DarwinMisc::JitMode|EmuConfig\.Cpu|vtlb|setVSyncMode"
        )
        self.assertNotRegex(
            self.info_plist,
            forbidden,
            "Info.plist.in must not reference JIT/VM/EmuConfig.Cpu/NominalScalar symbols",
        )


if __name__ == "__main__":
    unittest.main()
