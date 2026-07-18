"""Wave 0 guard: FramePacingPreset enum + apply function structure (EMU-04-2/3/8)."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class TestIosFramePacingPresets(unittest.TestCase):
    SETTING_STORE = ROOT / "platforms/ios/app/src/main/swift/Models/SettingsStore.swift"
    FRAME_PACING = ROOT / "platforms/ios/app/src/main/swift/Models/SettingsStore+FramePacing.swift"

    def setUp(self):
        self.assertTrue(
            self.SETTING_STORE.exists(),
            "SettingsStore.swift missing — repo root resolution is wrong",
        )
        self.src = self.SETTING_STORE.read_text(encoding="utf-8")
        self.frame_pacing_src = (
            self.FRAME_PACING.read_text(encoding="utf-8")
            if self.FRAME_PACING.exists()
            else ""
        )

    def test_preset_table_contains_five_cases(self):
        """The enum must be Int, CaseIterable and expose exactly the five locked cases."""
        self.assertRegex(
            self.src,
            r"enum\s+FramePacingPreset\s*:\s*Int\s*,\s*CaseIterable",
            msg="FramePacingPreset is not declared as Int, CaseIterable",
        )
        for case_name in ("optimal", "smooth", "lowLatency", "batterySaver", "custom"):
            self.assertIn(
                f"case {case_name}",
                self.src,
                msg=f"FramePacingPreset.{case_name} case missing",
            )
        # Five cases total (named cases — the enum may have more lines but the
        # case declarations should number exactly 5).
        case_lines = re.findall(r"(?m)^\s*case\s+(optimal|smooth|lowLatency|batterySaver|custom)\b", self.src)
        case_names = {c for c in case_lines}
        self.assertEqual(
            case_names,
            {"optimal", "smooth", "lowLatency", "batterySaver", "custom"},
            msg=f"FramePacingPreset case set is wrong: {case_names}",
        )

    def test_preset_values_match_D_01(self):
        """D-01 row values must appear in the applyFramePacingPreset switch body."""
        self.assertTrue(
            self.src.count("func applyFramePacingPreset") >= 1,
            "applyFramePacingPreset function is missing",
        )
        # Extract the apply switch body roughly: from func applyFramePacingPreset
        # to the next private func / closing brace at column 0 of the same indent.
        match = re.search(
            r"func\s+applyFramePacingPreset\s*\([^)]*\)\s*\{(?P<body>.*?)^\s{4}\}",
            self.src,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(match, "Could not isolate applyFramePacingPreset body")
        body = match.group("body")

        # D-01 table (locked):
        d01 = {
            "optimal": dict(vsync=4, out=15, buf=50, fps=60, sync=False, limiter=True),
            "smooth": dict(vsync=8, out=20, buf=75, fps=60, sync=False, limiter=True),
            "lowLatency": dict(vsync=2, out=10, buf=30, fps=60, sync=False, limiter=True),
            "batterySaver": dict(vsync=8, out=30, buf=100, fps=45, sync=False, limiter=True),
        }

        for preset_name, expected in d01.items():
            # Pull the case body for this preset.
            case_match = re.search(
                r"case\s+\." + preset_name + r"\s*:\s*(?P<case>.*?)(?=^\s{8}case\s+\.|^\s{4}\})",
                body,
                re.DOTALL | re.MULTILINE,
            )
            self.assertIsNotNone(
                case_match,
                msg=f"applyFramePacingPreset has no case .{preset_name}",
            )
            case_body = case_match.group("case")
            self.assertIn(
                f"vsyncQueueSize = {expected['vsync']}",
                case_body,
                msg=f".{preset_name} VsyncQueueSize mismatch",
            )
            self.assertIn(
                f"audioOutputLatencyMs = {expected['out']}",
                case_body,
                msg=f".{preset_name} OutputLatencyMS mismatch",
            )
            self.assertIn(
                f"audioBufferMs = {expected['buf']}",
                case_body,
                msg=f".{preset_name} BufferMS mismatch",
            )
            self.assertIn(
                f"targetFPS = {expected['fps']}",
                case_body,
                msg=f".{preset_name} targetFPS mismatch",
            )
            self.assertIn(
                f"syncToHostRefresh = {'true' if expected['sync'] else 'false'}",
                case_body,
                msg=f".{preset_name} syncToHostRefresh mismatch",
            )
            self.assertIn(
                f"frameLimiterEnabled = {'true' if expected['limiter'] else 'false'}",
                case_body,
                msg=f".{preset_name} frameLimiterEnabled mismatch",
            )

    def test_does_not_bypass_sanitization(self):
        """No setINIFloat('Framerate', 'NominalScalar', ...) outside applyFrameLimiterSettings()."""
        # Strip applyFrameLimiterSettings() body before greping.
        sanitized = re.sub(
            r"func\s+applyFrameLimiterSettings\s*\(\s*\)\s*\{.*?^\s{4}\}",
            "",
            self.src,
            count=1,
            flags=re.DOTALL | re.MULTILINE,
        )
        combined = sanitized + "\n" + self.frame_pacing_src
        bad_writes = re.findall(
            r'setINIFloat\s*\(\s*["\']Framerate["\']\s*,\s*key:\s*["\']NominalScalar["\']',
            combined,
        )
        self.assertEqual(
            bad_writes,
            [],
            msg="Direct NominalScalar write found outside applyFrameLimiterSettings (bypasses sanitizer)",
        )
        # applyFramePacingPreset must route through Setting<T> writers.
        apply_match = re.search(
            r"func\s+applyFramePacingPreset\s*\([^)]*\)\s*\{(?P<body>.*?)^\s{4}\}",
            self.src,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(match := apply_match, "applyFramePacingPreset missing")
        body = match.group("body")
        self.assertIn("frameLimiterEnabled = ", body, msg="applyFramePacingPreset doesn't set frameLimiterEnabled")
        self.assertIn("targetFPS = ", body, msg="applyFramePacingPreset doesn't set targetFPS")

    def test_audio_values_in_safe_range(self):
        """Every preset's BufferMS ∈ [10, 200] and OutputLatencyMS ∈ [5, 200]."""
        for token, lo, hi in (("audioBufferMs", 10, 200), ("audioOutputLatencyMs", 5, 200)):
            for match in re.finditer(rf"{token}\s*=\s*(\d+)", self.src):
                value = int(match.group(1))
                self.assertGreaterEqual(value, lo, msg=f"{token}={value} below clamp {lo}")
                self.assertLessEqual(value, hi, msg=f"{token}={value} above clamp {hi}")

    def test_preset_overwrites_individual_values(self):
        """EDGE-adjacency: every named-preset case writes ALL six individual controls."""
        match = re.search(
            r"func\s+applyFramePacingPreset\s*\([^)]*\)\s*\{(?P<body>.*?)^\s{4}\}",
            self.src,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(match, "applyFramePacingPreset missing")
        body = match.group("body")
        for preset_name in ("optimal", "smooth", "lowLatency", "batterySaver"):
            case_match = re.search(
                r"case\s+\." + preset_name + r"\s*:\s*(?P<case>.*?)(?=^\s{8}case\s+\.|^\s{4}\})",
                body,
                re.DOTALL | re.MULTILINE,
            )
            self.assertIsNotNone(case_match, msg=f"case .{preset_name} missing in apply body")
            case_body = case_match.group("case")
            for control in (
                "vsyncQueueSize",
                "audioOutputLatencyMs",
                "audioBufferMs",
                "syncToHostRefresh",
                "frameLimiterEnabled",
                "targetFPS",
            ):
                self.assertIn(
                    f"{control} = ",
                    case_body,
                    msg=f".{preset_name} does not overwrite {control} (EDGE-adjacency)",
                )

    def test_preset_write_order_is_deterministic(self):
        """EDGE-ordering: targetFPS assignment must come AFTER frameLimiterEnabled in each case body."""
        match = re.search(
            r"func\s+applyFramePacingPreset\s*\([^)]*\)\s*\{(?P<body>.*?)^\s{4}\}",
            self.src,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(match, "applyFramePacingPreset missing")
        body = match.group("body")
        for preset_name in ("optimal", "smooth", "lowLatency", "batterySaver"):
            case_match = re.search(
                r"case\s+\." + preset_name + r"\s*:\s*(?P<case>.*?)(?=^\s{8}case\s+\.|^\s{4}\})",
                body,
                re.DOTALL | re.MULTILINE,
            )
            self.assertIsNotNone(case_match, msg=f"case .{preset_name} missing")
            case_body = case_match.group("case")
            limiter_idx = case_body.find("frameLimiterEnabled = ")
            fps_idx = case_body.find("targetFPS = ")
            self.assertGreaterEqual(
                limiter_idx,
                0,
                msg=f".{preset_name} missing frameLimiterEnabled assignment",
            )
            self.assertGreaterEqual(
                fps_idx,
                0,
                msg=f".{preset_name} missing targetFPS assignment",
            )
            self.assertGreater(
                fps_idx,
                limiter_idx,
                msg=f".{preset_name} writes targetFPS before frameLimiterEnabled (violates EDGE-ordering)",
            )


if __name__ == "__main__":
    unittest.main()
