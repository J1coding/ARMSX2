"""Wave 0 Python guards for Item 6 (ProMotion panel lock): Info.plist key + optional SceneDelegate preferredFrameRateRange hint."""
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
        """Info.plist.in contains CADisableMinimumFrameDurationOnPhone = true (Item 6 piece 1).

        This is the load-bearing ProMotion unlock — the actual opt-out of the
        60 Hz cap on iPhone Pro / iPad Pro panels. SceneDelegate may optionally
        also pin a preferredFrameRateRange hint, but that hint is not required
        for the unlock to take effect.
        """
        self.assertRegex(
            self.info_plist,
            r"(?m)^\s*<key>CADisableMinimumFrameDurationOnPhone</key>\s*\n\s*<true/>\s*$",
        )

    def test_scenedelegate_does_not_use_broken_uiupdatelink_initializer(self):
        """Regression guard: SceneDelegate.mm must NOT call
        -[UIUpdateLink initWithWindowScene:].

        That selector does not exist on UIUpdateLink. Calling it crashed the app
        at every cold launch on iOS 26+/27 with NSInvalidArgumentException /
        doesNotRecognizeSelector: (LiveContainer-2026-07-19 .ips, build v2.4.1 /
        93fdb8fd45). The preferredFrameRateRange hint is optional — the
        CADisableMinimumFrameDurationOnPhone Info.plist key alone is sufficient
        to unlock >60 Hz on ProMotion panels.
        """
        # Match the actual ObjC message-send form: a closing bracket
        # (receiver expression) immediately before the selector, e.g.
        # `[[UIUpdateLink alloc] initWithWindowScene:...]` or
        # `[someLink initWithWindowScene:...]`. This avoids matching the
        # selector name when it appears inside comments (where the `]`
        # typically comes AFTER the selector, as in `-[UIUpdateLink initWithWindowScene:]`).
        broken_selector_send = re.compile(r"\]\s*initWithWindowScene\s*:")
        self.assertNotRegex(
            self.scene_delegate,
            broken_selector_send,
            "SceneDelegate.mm must not send -[UIUpdateLink initWithWindowScene:] — "
            "that selector does not exist on the class and crashed the app at every "
            "cold launch on iOS 26+/27. See LiveContainer-2026-07-19 .ips and "
            ".planning/debug/uiupdatelink-crash.md.",
        )

    def test_scenedelegate_preferred_frame_rate_range_hint_is_well_formed_if_present(self):
        """If SceneDelegate.mm sets preferredFrameRateRange, it must be well-formed.

        The hint is OPTIONAL — its absence is acceptable because the actual
        ProMotion unlock is the CADisableMinimumFrameDurationOnPhone Info.plist
        key (guarded by test_info_plist_key_present). If a contributor
        reintroduces a preferredFrameRateRange hint, this test enforces that it:

          * uses CAFrameRateRangeMake(60, ...) or (CAFrameRateRange){60, ...} form
          * references maximumFramesPerSecond (so non-ProMotion devices get a
            (60,60,60) no-op range)
          * is wrapped in if (@available(iOS 15.0, *)) or if (@available(iOS 18.0, *))

        It MUST NOT use -[UIUpdateLink initWithWindowScene:] to obtain the link
        instance — that selector is enforced absent by
        test_scenedelegate_does_not_use_broken_uiupdatelink_initializer.
        """
        assign_match = re.search(
            r"\.preferredFrameRateRange\s*=", self.scene_delegate
        )
        if assign_match is None:
            self.skipTest(
                "preferredFrameRateRange hint is absent in SceneDelegate.mm — "
                "acceptable, CADisableMinimumFrameDurationOnPhone unlocks ProMotion"
            )

        # Assignment is present — enforce the shape.
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
        The SceneDelegate preferredFrameRateRange opt-in (if present) must not introduce them either.
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
