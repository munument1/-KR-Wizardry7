#!/usr/bin/env python3
"""Add artifact-free stat/bonus repainting to the verified v20 UI build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_dos_v19_baseline import BytePatch, apply_guarded_patches, expect_hash, sha256, write_deterministic_zip
from build_dos_v20_ui_complete import MZ_HEADER_SIZE, near_call


STAT_REPAINT_HELPER = 0xF7B0
RECT_FILL_TARGET = 0x3948
VPCMK_STAT_DRAW_TARGET = 0x69F2
VPCMK_ORIGIN = 0x5047

V20_HASHES = {
    "DS.EXE": "fa5ca3c744e1c5be78c3dff5552baf50b96c45d8b14b885b4e12c6413537e804",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "MSG.DBS": "6e316eb669047b4a998694ed3c314879a7e2890c749619d43d0d03e18a8ae4dc",
    "MSG.HDR": "94622ce99f0e442df9823abcc522d72e3c0ef41d066934a4af090211c0a5525d",
    "VBASE.OVR": "5546e63be4fec69655c1080e5c7c25aa5073d50d0ac08b0bfc391b7a9bab7a40",
    "VBFONT0.VGA": "e425f17118abbc2d7599c61f89324ea9162939a97383f35d17c11e90d7cd4750",
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
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
}


def stat_repaint_helper_bytes() -> bytes:
    """Clear X=102..168/Y=32..108, then call VPCMK's normal stat draw."""
    start = STAT_REPAINT_HELPER
    first_call = start + 14
    second_call = start + 26
    return (
        bytes.fromhex(
            "55 89 E5 "       # push bp; mov bp,sp
            "6A 00 "          # color 0 (black)
            "6A 6C "          # bottom 108
            "68 A8 00 "       # right 168
            "6A 20 "          # top 32
            "6A 66 "          # left 102
        )
        + near_call(RECT_FILL_TARGET, first_call)
        + bytes.fromhex("83 C4 0A FF 76 06 FF 76 04")
        + near_call(VPCMK_STAT_DRAW_TARGET, second_call)
        + bytes.fromhex("83 C4 04 89 EC 5D C3")
    )


def inject_stat_repaint_helper(ds_exe: bytes) -> bytes:
    data = bytearray(ds_exe)
    helper = stat_repaint_helper_bytes()
    offset = MZ_HEADER_SIZE + STAT_REPAINT_HELPER
    if data[offset : offset + len(helper)] != b"\x00" * len(helper):
        raise ValueError("resident stat repaint cave is not empty")
    data[offset : offset + len(helper)] = helper
    return bytes(data)


def patch_vpcmk_stat_redraw(vpcmk: bytes) -> bytes:
    runtime_call = VPCMK_ORIGIN + 0x46E2
    return apply_guarded_patches(
        vpcmk,
        (
            BytePatch(
                "stat input redraw through clear-and-redraw helper",
                0x46E2,
                near_call(VPCMK_STAT_DRAW_TARGET, runtime_call),
                near_call(STAT_REPAINT_HELPER, runtime_call),
            ),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v20-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    payloads: dict[str, bytes] = {}
    for name, expected_hash in V20_HASHES.items():
        source = (args.v20_dir / name).read_bytes()
        expect_hash(f"v20 {name}", source, expected_hash)
        if name == "DS.EXE":
            source = inject_stat_repaint_helper(source)
        elif name == "VPCMK.OVR":
            source = patch_vpcmk_stat_redraw(source)
        payloads[f"DSAVANT/{name}"] = source

    report = {
        "format": "Wizardry VII DOS v21 Korean UI + artifact-free stat repaint",
        "change": [
            "clear the complete stat/arrow/bonus rectangle before each interactive redraw",
            "redraw the normal stat labels, values, arrows, and bonus on the clean background",
        ],
        "geometry": {"clear_rectangle": "X=102..168; Y=32..108; color=black"},
        "safety": [
            "stat values, bonus arithmetic, hitboxes, and control flow unchanged",
            "VPCMK overlay size unchanged",
            "36-byte helper placed in the verified empty resident renderer cave",
            "all v20 inputs and patched instruction bytes hash/byte guarded",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    payloads["UI_V21_REPORT.json"] = json.dumps(
        report, ensure_ascii=False, indent=2
    ).encode("utf-8")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
