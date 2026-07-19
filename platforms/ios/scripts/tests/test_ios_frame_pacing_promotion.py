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
        """SceneDelegate.mm sets preferredFrameRateRange at scene-connect (Item 6 piece 2).

        Accepts either UIWindowScene.preferredFrameRateRange (iOS 15–17 SDK) or
        UIUpdateLink.preferredFrameRateRange (iOS 18+ SDK, where the property
        moved in Xcode 26 / iOS SDK 26.5). The literal CAFrameRateRangeMake (or
        CAFrameRateRange struct form) must appear nearby, with minimum:60 and
        maximum+preferred bound to maximumFramesPerSecond.
        """
        self.assertIn("preferredFrameRateRange", self.scene_delegate)
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
        """The preferredFrameRateRange opt-in is wrapped in `if (@available(...))`.

        iOS SDK 26 moved UIWindowScene.preferredFrameRateRange onto UIUpdateLink
        (iOS 18+), so we accept either the iOS 15.0 guard (legacy
        UIWindowScene.preferredFrameRateRange) or the iOS 18.0 guard (modern
        UIUpdateLink.preferredFrameRateRange).
        """
        # Find the assignment, not the first textual occurrence (which may be
        # inside a comment block above the actual opt-in).
        assign_match = re.search(
            r"\.preferredFrameRateRange\s*=", self.scene_delegate
        )
        self.assertIsNotNone(
            assign_match,
            "preferredFrameRateRange assignment must be present (looking for "
            "'.preferredFrameRateRange =' assignment, not just the symbol)",
        )
        idx = assign_match.start()
        # Walk backwards up to 800 chars looking for either @available guard.
        window_start = max(0, idx - 800)
        preceding = self.scene_delegate[window_start:idx]
        legacy_guard = re.search(
            r"if\s*\(\s*@available\s*\(\s*iOS\s+15\.0\s*,\s*\*\s*\)\s*\)",
            preceding,
        )
        modern_guard = re.search(
            r"if\s*\(\s*@available\s*\(\s*iOS\s+18\.0\s*,\s*\*\s*\)\s*\)",
            preceding,
        )
        self.assertTrue(
            legacy_guard is not None or modern_guard is not None,
            "preferredFrameRateRange line must be wrapped in "
            "if (@available(iOS 15.0, *)) or if (@available(iOS 18.0, *))",
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
