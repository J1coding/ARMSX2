#!/usr/bin/env python3
"""
Regression guard: MetalFX must be compile-guarded out for iOS Simulator builds.

The iOS Simulator SDK does NOT ship MetalFX.framework. Building for iphonesimulator
while eagerly `#include <MetalFX/MetalFX.h>` fails with "MetalFX/MetalFX.h file not found".

This test enforces three invariants that together make sim builds possible:

1. GSDeviceMTL.h must gate `#include <MetalFX/MetalFX.h>` behind a
   PCSX2_HAS_METALFX macro that is 0 on sim, 1 elsewhere.
2. ARMSX2Bridge.mm must gate `#import <MetalFX/MetalFX.h>` behind
   `#if !TARGET_OS_SIMULATOR` (or equivalent macro).
3. pcsx2/CMakeLists.txt must NOT emit `-weak_framework MetalFX` for sim builds
   (gated on ARMSX2_REAL_DEVICE OR non-iOS).

Run from repo root:
    python3 platforms/ios/scripts/tests/test_ios_metal_fx_sim_guard.py
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

GS_DEVICE_MTL_H = REPO_ROOT / "pcsx2" / "GS" / "Renderers" / "Metal" / "GSDeviceMTL.h"
ARMSX2_BRIDGE_MM = REPO_ROOT / "platforms" / "ios" / "app" / "src" / "main" / "cpp" / "ARMSX2Bridge.mm"
PCSX2_CMAKE = REPO_ROOT / "pcsx2" / "CMakeLists.txt"


class MetalFXSimGuardTests(unittest.TestCase):
    """Verify MetalFX is properly compile-guarded for iOS Simulator builds."""

    def test_gsdevicemtl_header_defines_pcsx2_has_metalfx_macro(self) -> None:
        """GSDeviceMTL.h must define PCSX2_HAS_METALFX (0 on sim, 1 elsewhere)."""
        self.assertTrue(GS_DEVICE_MTL_H.is_file(), f"missing: {GS_DEVICE_MTL_H}")
        src = GS_DEVICE_MTL_H.read_text()
        # Macro definition block. The exact formatting may vary; we just require
        # both branches to exist with the correct values.
        self.assertIn("#define PCSX2_HAS_METALFX 0", src,
                      "PCSX2_HAS_METALFX 0 branch missing in GSDeviceMTL.h")
        self.assertIn("#define PCSX2_HAS_METALFX 1", src,
                      "PCSX2_HAS_METALFX 1 branch missing in GSDeviceMTL.h")

    def test_gsdevicemtl_metalfx_include_is_gated(self) -> None:
        """`#include <MetalFX/MetalFX.h>` must not appear unconditionally in GSDeviceMTL.h."""
        src = GS_DEVICE_MTL_H.read_text()
        # Every occurrence of the MetalFX include must be inside an active
        # guard that excludes the iOS Simulator. We accept any of:
        #   (a) `#if PCSX2_HAS_METALFX` ... include ...
        #   (b) `#if !TARGET_OS_SIMULATOR` ... include ...
        #   (c) `#if TARGET_OS_SIMULATOR` ... #else ... include ...  (i.e. include
        #       is in the non-sim branch)
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if re.match(r'\s*#include\s*<MetalFX/MetalFX\.h>', line):
                context = "\n".join(lines[max(0, i - 12):i])
                direct_guard = re.search(
                    r'#if\s+PCSX2_HAS_METALFX|#if\s*!\s*TARGET_OS_SIMULATOR', context)
                else_branch = re.search(
                    r'#if\s+TARGET_OS_SIMULATOR.*#else', context, re.DOTALL)
                self.assertTrue(
                    direct_guard or else_branch,
                    f"<MetalFX/MetalFX.h> include at {GS_DEVICE_MTL_H.name}:{i+1} "
                    f"is not gated by PCSX2_HAS_METALFX / !TARGET_OS_SIMULATOR / "
                    f"#else-after-#if-TARGET_OS_SIMULATOR")

    def test_gsdevicemtl_metalfx_member_is_guarded(self) -> None:
        """The m_mfx_spatial MetalFX handle must be #if'd behind PCSX2_HAS_METALFX."""
        src = GS_DEVICE_MTL_H.read_text()
        # The typed declaration `MRCOwned<id<MTLFXSpatialScaler>> m_mfx_spatial`
        # must appear inside a `#if PCSX2_HAS_METALFX` block.
        idx = src.find("id<MTLFXSpatialScaler>> m_mfx_spatial")
        self.assertGreater(idx, -1, "MTLFXSpatialScaler typed member not found")
        # Find the nearest preceding #if
        preceding = src[:idx]
        last_if_match = None
        for m in re.finditer(r'#if\s+PCSX2_HAS_METALFX', preceding):
            last_if_match = m
        self.assertIsNotNone(last_if_match,
                             "MTLFXSpatialScaler member declaration is not inside "
                             "#if PCSX2_HAS_METALFX")

    def test_armsx2_bridge_metalfx_import_is_gated(self) -> None:
        """`#import <MetalFX/MetalFX.h>` in ARMSX2Bridge.mm must be gated to !TARGET_OS_SIMULATOR."""
        self.assertTrue(ARMSX2_BRIDGE_MM.is_file(), f"missing: {ARMSX2_BRIDGE_MM}")
        src = ARMSX2_BRIDGE_MM.read_text()
        # The MetalFX import must appear, AND must be inside an active
        # `#if !TARGET_OS_SIMULATOR` (or equivalent) guard.
        lines = src.splitlines()
        metal_fx_import_lines = [i for i, ln in enumerate(lines)
                                 if re.match(r'\s*#\s*import\s*<MetalFX/MetalFX\.h>', ln)]
        self.assertTrue(metal_fx_import_lines,
                        "ARMSX2Bridge.mm is missing `#import <MetalFX/MetalFX.h>` — "
                        "did you delete the device-side import?")
        for i in metal_fx_import_lines:
            context = "\n".join(lines[max(0, i - 8):i])
            self.assertTrue(
                re.search(r'#if\s*!\s*TARGET_OS_SIMULATOR', context),
                f"#import <MetalFX/MetalFX.h> at {ARMSX2_BRIDGE_MM.name}:{i+1} "
                f"is not gated by `#if !TARGET_OS_SIMULATOR`")

    def test_cmake_weak_framework_metalfx_is_skipped_for_sim(self) -> None:
        """`-weak_framework MetalFX` must be skipped when ARMSX2_REAL_DEVICE=OFF for iOS."""
        self.assertTrue(PCSX2_CMAKE.is_file(), f"missing: {PCSX2_CMAKE}")
        src = PCSX2_CMAKE.read_text()
        # The `target_link_options(PCSX2_FLAGS INTERFACE "SHELL:-weak_framework MetalFX")`
        # call must be wrapped in a conditional that excludes iOS-sim builds.
        # Match the call and look at the preceding ~6 lines for an `if(...)`
        # that references ARMSX2_REAL_DEVICE.
        lines = src.splitlines()
        target_idx = None
        for i, ln in enumerate(lines):
            if "target_link_options" in ln and "MetalFX" in ln:
                target_idx = i
                break
        self.assertIsNotNone(target_idx,
                             "target_link_options ... MetalFX call not found in pcsx2/CMakeLists.txt")
        preceding = "\n".join(lines[max(0, target_idx - 6):target_idx])
        self.assertIn("ARMSX2_REAL_DEVICE", preceding,
                      "`-weak_framework MetalFX` target_link_options call is not gated "
                      "on ARMSX2_REAL_DEVICE — sim builds will fail with "
                      "'framework MetalFX not found'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
