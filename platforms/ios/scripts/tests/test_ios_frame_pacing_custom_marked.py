"""Wave 0 guard: markFramePacingCustom() wired into all six individual didSets (EMU-04-2 / gap #1).

The OSD sibling (markOsdCustom) is wired at 14 sites inside SettingsStore.swift
(lines ~1164-1303). The Frame Pacing equivalent (markFramePacingCustom) was
defined at SettingsStore.swift:2299 but was never called from any of the six
individual frame-pacing didSets — so editing any individual control silently
drifted the preset metadata away from the underlying INI values and the
UI-SPEC Q6 LOCKED caption never appeared. This guard pins the wiring so the
regression cannot recur.

Closes gap #1 from 04.1-VERIFICATION.md (CR-01 BLOCKER).
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class TestIosFramePacingCustomMarked(unittest.TestCase):
    SETTING_STORE = ROOT / "platforms/ios/app/src/main/swift/Models/SettingsStore.swift"

    # The six individual frame-pacing controls whose didSet must call
    # markFramePacingCustom() to flip the preset to .custom (Q6 caption).
    INDIVIDUAL_PROPERTIES = (
        "frameLimiterEnabled",
        "targetFPS",
        "audioBufferMs",
        "audioOutputLatencyMs",
        "vsyncQueueSize",
        "syncToHostRefresh",
    )

    def setUp(self):
        self.assertTrue(
            self.SETTING_STORE.exists(),
            "SettingsStore.swift missing — repo root resolution is wrong",
        )
        self.src = self.SETTING_STORE.read_text(encoding="utf-8")

    def test_mark_frame_pacing_custom_defined_once(self):
        """The helper definition exists exactly once."""
        count = self.src.count("func markFramePacingCustom")
        self.assertEqual(
            count,
            1,
            msg=f"expected exactly 1 'func markFramePacingCustom' definition, found {count}",
        )

    def test_mark_frame_pacing_custom_called_at_least_six_times(self):
        """At least six call sites (the definition line is 'func markFramePacingCustom'
        so it does not contain the 'markFramePacingCustom()' call token)."""
        count = self.src.count("markFramePacingCustom()")
        self.assertGreaterEqual(
            count,
            6,
            msg=f"expected >= 6 call sites of markFramePacingCustom(), found {count}",
        )

    def test_mark_frame_pacing_custom_total_occurrences_at_least_seven(self):
        """Total occurrences: 1 def + >= 6 call sites = >= 7 (the headline guard)."""
        count = self.src.count("markFramePacingCustom")
        self.assertGreaterEqual(
            count,
            7,
            msg=(
                f"expected >= 7 total occurrences of 'markFramePacingCustom' "
                f"(1 def + >= 6 calls); found {count}"
            ),
        )

    def test_each_individual_didset_body_contains_call(self):
        """For each of the six individual frame-pacing properties, the didSet body
        must contain the literal token 'markFramePacingCustom' — mirrors the OSD
        pattern at SettingsStore.swift:1164-1303 (the last line of each osd didSet
        is markOsdCustom())."""
        for name in self.INDIVIDUAL_PROPERTIES:
            body = self._extract_didset_body(name)
            if body is None:
                # Fall back to a windowed scan: find `var <name>:` then look
                # forward up to 15 lines for the literal token. This catches
                # single-line didSets and unusual formatting the regex misses.
                self.assertTrue(
                    self._windowed_contains(name, "markFramePacingCustom", window=15),
                    msg=(
                        f"{name} didSet body could not be isolated by regex AND "
                        f"windowed scan found no 'markFramePacingCustom' within 15 lines"
                    ),
                )
                continue
            self.assertIn(
                "markFramePacingCustom",
                body,
                msg=f"{name} didSet missing markFramePacingCustom call",
            )

    # ── Helpers ──

    def _extract_didset_body(self, prop_name: str):
        """Isolate the didSet body of `var <prop_name>: <type> ... { didSet { ... } }`.

        Returns the body text (without the surrounding braces), or None if the
        regex cannot isolate it. The closing-brace-at-column-8 pattern mirrors
        the regex idiom in test_ios_frame_pacing_presets.py.
        """
        # Multi-line stored property with explicit didSet block. Capture from
        # `var <prop_name>` through the matching `didSet { ... }` block. The
        # closing `}` of didSet appears at column 8 inside the source.
        pattern = (
            r"var\s+" + re.escape(prop_name) + r"\s*:\s*[^\n{]*\{[^{]*?didSet\s*\{"
            r"(?P<body>.*?)^\s{8}\}"
        )
        match = re.search(pattern, self.src, re.DOTALL | re.MULTILINE)
        if match:
            return match.group("body")
        # Alternative single-line form: `var <prop_name> ... { didSet { ... } }`
        # where the entire didSet fits on one line.
        single = re.search(
            r"var\s+" + re.escape(prop_name) + r"\s*:\s*[^\n{]*\{[^{]*?didSet\s*\{(?P<body>[^}]*)\}",
            self.src,
        )
        if single:
            return single.group("body")
        return None

    def _windowed_contains(self, prop_name: str, token: str, window: int = 15) -> bool:
        """Find the first line matching `var <prop_name>:` and scan forward up to
        `window` lines for the literal token. Used as a fallback when the didSet
        body cannot be cleanly isolated by regex."""
        lines = self.src.splitlines()
        for idx, line in enumerate(lines):
            if re.search(rf"var\s+{re.escape(prop_name)}\s*:", line):
                end = min(idx + window, len(lines))
                for scan in lines[idx:end]:
                    if token in scan:
                        return True
                return False
        return False


if __name__ == "__main__":
    unittest.main()
