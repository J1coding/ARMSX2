"""Wave 0 forbidden-symbol check for the Adaptive Resolution controller (Item 9):
no JIT/VM/EmuConfig.Cpu/vtlb/NominalScalar contact. Also asserts the controller
writes through the existing ARMSX2Bridge.setINIFloat("EmuCore/GS",
"upscale_multiplier", ...) path (T-4.1-16 mitigation), and that the D-04
tuning constants are present verbatim.
"""
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


class TestIosFramePacingDynamicRes(unittest.TestCase):
    CONTROLLER = (
        REPO_ROOT
        / "platforms/ios/app/src/main/swift/Models/FrameTimeDynamicResolutionController.swift"
    )
    SETTINGS_STORE = (
        REPO_ROOT
        / "platforms/ios/app/src/main/swift/Models/SettingsStore.swift"
    )

    def setUp(self):
        self.assertTrue(
            self.CONTROLLER.exists(),
            "FrameTimeDynamicResolutionController.swift missing — repo root resolution is wrong",
        )
        self.assertTrue(
            self.SETTINGS_STORE.exists(),
            "SettingsStore.swift missing — repo root resolution is wrong",
        )
        self.controller_src = self.CONTROLLER.read_text(encoding="utf-8")
        self.settings_src = self.SETTINGS_STORE.read_text(encoding="utf-8")

    def test_no_forbidden_symbols_in_controller(self):
        """T-4.1-16 mitigation: the controller must not touch the frozen JIT ABI
        surface or any of the prohibited symbols. The bridge enforces the cross-
        thread hop; Swift literally cannot reach EmuConfig.GS.UpscaleMultiplier
        (Pitfall 4 — structurally prevented).
        """
        forbidden = re.compile(
            r"EmuConfig\.GS\.UpscaleMultiplier"
            r"|EmuConfig\.Cpu"
            r"|iPSX2_"
            r"|DarwinMisc::JitMode"
            r"|vtlb"
            r"|NominalScalar"
            r"|setVSyncMode"
        )
        self.assertNotRegex(
            self.controller_src,
            forbidden,
            "Adaptive Resolution controller must not reference JIT/VM/CPU/vtlb/"
            "NominalScalar/setVSyncMode symbols (T-4.1-16 + Pitfall 4).",
        )

    def test_controller_writes_through_bridge(self):
        """T-4.1-16 mitigation: writes funnel through the existing
        ARMSX2Bridge.setINIFloat("EmuCore/GS", "upscale_multiplier", ...) path
        which clamps to [0.25, 8.0] and hops to the CPU/GS thread via the
        existing ARMSX2ApplyLiveFloatSetting hop. No new bridge code required.
        """
        self.assertIn(
            'ARMSX2Bridge.setINIFloat("EmuCore/GS", "upscale_multiplier"',
            self.controller_src,
            "Controller must write through the existing bridge path "
            "(Pitfall 4 structural prevention).",
        )

    def test_step_size_and_clamps(self):
        """D-04 verbatim tuning: 0.25 step size; min clamp 1.0 (native PS2 —
        never below); max clamp = `maxMultiplier` (D-03 — captured from the
        user's currently-configured UpscaleMultiplier at enable time).
        """
        self.assertIn("0.25", self.controller_src, "Step size literal 0.25 missing")
        self.assertTrue(
            ("1.0" in self.controller_src) or ("max(1.0" in self.controller_src),
            "Min clamp literal 1.0 / max(1.0 missing",
        )
        self.assertIn(
            "maxMultiplier",
            self.controller_src,
            "maxMultiplier (D-03 ceiling) identifier missing",
        )

    def test_hysteresis_thresholds(self):
        """D-04 verbatim hysteresis: smoothed-average > 22 ms → reduce one step;
        < 14 ms → increase one step toward the ceiling.
        """
        self.assertIn(
            "22",
            self.controller_src,
            "Reduce threshold (22 ms) literal missing",
        )
        self.assertIn(
            "14",
            self.controller_src,
            "Increase threshold (14 ms) literal missing",
        )

    def test_min_interval(self):
        """D-04 verbatim: minimum interval between resolution changes is 500 ms.
        The literal can appear as either `0.5` (TimeInterval in seconds) or
        `500` (milliseconds in a comment / docstring).
        """
        self.assertTrue(
            ("0.5" in self.controller_src) or ("500" in self.controller_src),
            "Min interval literal (0.5 s or 500 ms) missing",
        )

    def test_smoothing_window(self):
        """D-04 verbatim: smoothed average over the last 60 samples (~1 second
        at 60 Hz).
        """
        self.assertIn(
            "60",
            self.controller_src,
            "Smoothing-window sample count (60) literal missing",
        )

    def test_opt_in_default(self):
        """Item 9 + Q3 LOCKED: Adaptive Resolution is opt-in (default false).
        Either the Setting<Bool> default is false, OR the var declaration has
        `= false` initialization.
        """
        # Find the _adaptiveResolutionEnabledConfig Setting<Bool>(...) literal.
        setting_match = re.search(
            r"_adaptiveResolutionEnabledConfig\s*=\s*Setting<Bool>\s*\("
            r"[^)]*default:\s*(?P<default>false|true)",
            self.settings_src,
            re.DOTALL,
        )
        # Find the var adaptiveResolutionEnabled: Bool ... = ... declaration.
        var_match = re.search(
            r"var\s+adaptiveResolutionEnabled\s*:\s*Bool\s*(?::\s*[^=]+)?\s*=\s*"
            r"(?P<value>false|true)",
            self.settings_src,
        )
        setting_default = setting_match.group("default") if setting_match else None
        var_default = var_match.group("value") if var_match else None
        self.assertTrue(
            setting_default == "false" or var_default == "false",
            "Adaptive Resolution must default to false (Item 9 opt-in). "
            f"Observed Setting<Bool> default={setting_default!r}, "
            f"var default={var_default!r}.",
        )


if __name__ == "__main__":
    unittest.main()
