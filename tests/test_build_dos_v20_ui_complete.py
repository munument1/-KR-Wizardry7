from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v20_ui_complete import (  # noqa: E402
    FORMULAS,
    LOGICAL_LENGTH_EXCLUSIONS,
    MZ_HEADER_SIZE,
    OVERLAY_ORIGIN,
    STRLEN_TARGET,
    WIDTH_ADAPTER,
    WIDTH_TARGET,
    call_target,
    width_adapter_bytes,
)


BUILD = ROOT / "outputs" / "v20_ui_complete_build" / "DSAVANT"
EXPECTED_HASHES = {
    "DS.EXE": "fa5ca3c744e1c5be78c3dff5552baf50b96c45d8b14b885b4e12c6413537e804",
    "VBASE.OVR": "5546e63be4fec69655c1080e5c7c25aa5073d50d0ac08b0bfc391b7a9bab7a40",
    "VDOPT.OVR": "b2574cecefcc55f2b42cac509c4428f696da27cfdb558b44082a0b19e516be92",
    "VINIT.OVR": "63a88cc454817c243d3c6023107a86e2c6926dc9a38cd63e773843e1da96b2a6",
    "VMAZE.OVR": "252d4c7e205db120c75f6547ab5772d8ebd89a8d0e1a700d58781afbeced1197",
    "VMELE.OVR": "e56c555e3343fc869aa49fd8419e40a2271ee370de023f7ae8d453afa7a7e8a4",
    "VMEXE.OVR": "8058f9c1ed4d6409c9922969b57aa972864fa396c2d4bb7d353d8a5ec580d3da",
    "VMEXT.OVR": "e9f9f77d1312b370e146e2d4f86edd7dea7cbbf36a10af04168fdfb7f7222029",
    "VMNPC.OVR": "dfedb6b59cb12bc3d79e54f0e163969bd7dfe39b76a12a7d0a9abb02677d7fb1",
    "VPCLV.OVR": "2f83def79e4027ea65eea40b44fac7782a99140f6bbf02c7aa385f93827ab9fd",
    "VPCMK.OVR": "d27b6e1f961a9e1aef10d0d2d0127da940c5e36e663a5aeee33365b2747a5d60",
    "VPCVW.OVR": "db39bbe3f33131f6cb8d89866ab17f623f34f95bf83bbac91a20e1fb47f084f7",
    "VPOPS.OVR": "cb554c9af7d5e105e96fe89adb654dd80f2daabffe5228bbe7aa2adce02819ee",
    "VTREA.OVR": "95c08e2ba6d414cf0be25865da04c520dfc55d858815d52ebacb4418fd1cb305",
}


class UiCompletePatchSpecificationTests(unittest.TestCase):
    def test_all_payload_hashes_are_locked(self) -> None:
        for name, expected in EXPECTED_HASHES.items():
            actual = hashlib.sha256((BUILD / name).read_bytes()).hexdigest()
            self.assertEqual(expected, actual, name)

    def test_all_display_calls_use_resident_pixel_width_adapter(self) -> None:
        for name, formulas in FORMULAS.items():
            raw = (BUILD / name).read_bytes()
            data = raw[MZ_HEADER_SIZE:] if name == "DS.EXE" else raw
            origin = 0 if name == "DS.EXE" else OVERLAY_ORIGIN
            offsets = {
                offset
                for kind, sites in formulas.items()
                if kind != "sum_final"
                for offset in sites
            }
            for offset in offsets:
                self.assertEqual(
                    WIDTH_ADAPTER,
                    call_target(data, offset, origin),
                    f"{name} 0x{offset:04X}",
                )

    def test_reviewed_logical_lengths_still_call_strlen(self) -> None:
        for name, offsets in LOGICAL_LENGTH_EXCLUSIONS.items():
            data = (BUILD / name).read_bytes()
            for offset in offsets:
                self.assertEqual(
                    STRLEN_TARGET,
                    call_target(data, offset, OVERLAY_ORIGIN),
                    f"{name} 0x{offset:04X}",
                )

    def test_adapter_is_in_verified_resident_cave_and_calls_width_hook(self) -> None:
        raw = (BUILD / "DS.EXE").read_bytes()
        adapter = width_adapter_bytes()
        start = MZ_HEADER_SIZE + WIDTH_ADAPTER
        self.assertEqual(adapter, raw[start : start + len(adapter)])
        self.assertEqual(WIDTH_TARGET, call_target(adapter, 8, WIDTH_ADAPTER))
        self.assertEqual(18, len(adapter))

    def test_security_body_uses_eight_pixel_baseline_stride(self) -> None:
        data = (BUILD / "VBASE.OVR").read_bytes()
        self.assertEqual(bytes.fromhex("17 00"), data[0x644E:0x6450])
        self.assertEqual(bytes.fromhex("1F 00"), data[0x64EC:0x64EE])


if __name__ == "__main__":
    unittest.main()
