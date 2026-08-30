#!/usr/bin/env python3
"""Build the isolated Wizardry VII DOS v19 UI-alignment test package.

This pass contains only stat-editor geometry and previously runtime-verified
pixel-width centering sites in VPCMK/VBASE.  Skill geometry and flow control
are intentionally untouched.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from build_dos_v19_baseline import (
    BASELINE_HASHES,
    BytePatch,
    apply_guarded_patches,
    expect_hash,
    read_original,
    sha256,
    write_deterministic_zip,
)


ORIGINAL_VBASE_SHA256 = "7919a6eddd0f7b65905ad4ab3a301604cccb8bf0f213ebebc190d5d1227104d6"
ORIGINAL_VPCLV_SHA256 = "429374f8c7c564d9e26a4050c241a4002dc5c73ea57f45610cb83f0866a235e2"
PATCHED_VBASE_SHA256 = "b16c23a3ab1033fe4ef202dfd01cda65efa326f72c7882c5eaf02d6f6c1417b2"

VPCMK_CENTERING_PATCHES = (
    BytePatch(
        "modal/button centering path 1",
        0x0357,
        bytes.fromhex("FF 76 04 E8 33 F7 59 8B C8 8B 46 0C 2B C1 B9 06 00 F7 E9 B9 02 00 99 F7 F9"),
        bytes.fromhex("6A 00 FF 76 04 E8 24 E5 83 C4 04 8B C8 D1 E9 8B 46 0C BA 03 00 F7 EA 2B C1"),
    ),
    BytePatch(
        "modal/button centering path 2",
        0x04FA,
        bytes.fromhex("8D 86 5A FE 50 E8 8E F5 59 B9 06 00 F7 E9"),
        bytes.fromhex("31 C0 50 8D 86 5A FE 50 E8 7E E3 83 C4 04"),
    ),
    BytePatch(
        "modal/button centering path 3",
        0x05FA,
        bytes.fromhex("B8 14 00 F7 6E FE 8D 8E AA FE 03 C1 50 E8 86 F4 59 8B C8 8B 46 0C 2B C1 B9 06 00 F7 E9 B9 02 00 99 F7 F9"),
        bytes.fromhex("6A 00 B8 14 00 F7 6E FE 8D 8E AA FE 03 C1 50 E8 77 E2 83 C4 04 8B C8 D1 E9 8B 46 0C BA 03 00 F7 EA 2B C1"),
    ),
    BytePatch(
        "creation-screen centered label path 1",
        0x1B7B,
        bytes.fromhex("B8 48 02 F7 6E 04 05 F4 5B 50 E8 08 DF 59 B9 06 00 F7 E9 B9 02 00 99 F7 F9 8B C8 B8 28 00 2B C1 50"),
        bytes.fromhex("6A 00 B8 48 02 F7 6E 04 05 F4 5B 50 E8 F9 CC 83 C4 04 8B C8 D1 E9 B8 28 00 2B C1 50 90 90 90 90 90"),
    ),
    BytePatch(
        "creation-screen centered label path 2",
        0x20B6,
        bytes.fromhex("FF 76 04 E8 D4 D9 59 B9 06 00 F7 E9 B9 02 00 99 F7 F9 8B C8 B8 A0 00 2B C1 50"),
        bytes.fromhex("6A 00 FF 76 04 E8 C5 C7 83 C4 04 8B C8 D1 E9 B8 A0 00 2B C1 50 90 90 90 90 90"),
    ),
    BytePatch(
        "creation-screen centered label path 3",
        0x2901,
        bytes.fromhex("B8 14 00 F7 6E FE 05 10 96 50 E8 82 D1 59 8B C8 B8 09 00 2B C1 B9 06 00 F7 E9 B9 02 00 99 F7 F9 03 46 FA 40 50"),
        bytes.fromhex("6A 00 B8 14 00 F7 6E FE 05 10 96 50 E8 73 BF 83 C4 04 8B C8 D1 E9 8B 46 FA 05 1C 00 2B C1 50 90 90 90 90 90 90"),
    ),
)

VPCMK_STAT_PATCHES = (
    BytePatch("stat row stride 7->8", 0x19D7, b"\xB8\x07\x00", b"\xB8\x08\x00"),
    BytePatch("Korean label/value stream X 115->117", 0x19E1, b"\xB8\x73\x00", b"\xB8\x75\x00"),
    BytePatch("bonus row Y 89->100", 0x1A3F, b"\xB8\x59\x00", b"\xB8\x64\x00"),
    BytePatch("bonus numeric field width 1->2", 0x1A5F, b"\xB8\x01\x00", b"\xB8\x02\x00"),
    BytePatch("stat repaint bottom 96->108", 0x1A81, b"\xB8\x60\x00", b"\xB8\x6C\x00"),
    BytePatch("stat repaint top 35->32", 0x1A89, b"\xB8\x23\x00", b"\xB8\x20\x00"),
    BytePatch("left arrow row stride 6->8", 0x46F6, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("left arrow row base 35->32", 0x46FC, b"\x05\x23\x00", b"\x05\x20\x00"),
    BytePatch("right arrow row stride 6->8", 0x4718, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("right arrow row base 35->32", 0x471E, b"\x05\x23\x00", b"\x05\x20\x00"),
    BytePatch("selected-left hitbox bottom stride 6->8", 0x474F, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("selected-left hitbox bottom 40->39", 0x4755, b"\x05\x28\x00", b"\x05\x27\x00"),
    BytePatch("selected-left hitbox top stride 6->8", 0x475D, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("selected-left hitbox top 35->32", 0x4763, b"\x05\x23\x00", b"\x05\x20\x00"),
    BytePatch("selected-right hitbox bottom stride 6->8", 0x477C, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("selected-right hitbox bottom 40->39", 0x4782, b"\x05\x28\x00", b"\x05\x27\x00"),
    BytePatch("selected-right hitbox top stride 6->8", 0x478A, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("selected-right hitbox top 35->32", 0x4790, b"\x05\x23\x00", b"\x05\x20\x00"),
    BytePatch("unselected-row hitbox bottom stride 6->8", 0x47C1, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("unselected-row hitbox bottom 40->39", 0x47C7, b"\x05\x28\x00", b"\x05\x27\x00"),
    BytePatch("unselected-row hitbox top stride 6->8", 0x47CF, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("unselected-row hitbox top 35->32", 0x47D5, b"\x05\x23\x00", b"\x05\x20\x00"),
    BytePatch("stat input repaint bottom 96->108", 0x480A, b"\xB8\x60\x00", b"\xB8\x6C\x00"),
    BytePatch("stat input repaint top 35->32", 0x4812, b"\xB8\x23\x00", b"\xB8\x20\x00"),
)

VBASE_CENTERING_PATCHES = (
    BytePatch(
        "selected character-menu row centering",
        0x0147,
        bytes.fromhex("FF 76 04 E8 43 F9 59 8B C8 8B 46 0C 2B C1 B9 06 00 F7 E9 B9 02 00 99 F7 F9"),
        bytes.fromhex("6A 00 FF 76 04 E8 34 E7 83 C4 04 8B C8 D1 E9 8B 46 0C BA 03 00 F7 EA 2B C1"),
    ),
    BytePatch(
        "initial full character-menu list centering",
        0x0310,
        bytes.fromhex("B8 14 00 F7 6E FE 8D 8E AE FE 03 C1 50 E8 70 F7 59 8B C8 8B 46 0A 2B C1 B9 06 00 F7 E9 B9 02 00 99 F7 F9"),
        bytes.fromhex("6A 00 B8 14 00 F7 6E FE 8D 8E AE FE 03 C1 50 E8 61 E5 83 C4 04 8B C8 D1 E9 8B 46 0A BA 03 00 F7 EA 2B C1"),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    baseline_vpcmk = (args.baseline_dir / "VPCMK.OVR").read_bytes()
    expect_hash("baseline VPCMK.OVR", baseline_vpcmk, BASELINE_HASHES["VPCMK.OVR"])
    vpcmk_patches = VPCMK_CENTERING_PATCHES + VPCMK_STAT_PATCHES
    patched_vpcmk = apply_guarded_patches(baseline_vpcmk, vpcmk_patches)

    with zipfile.ZipFile(args.original_zip) as archive:
        original_vbase = read_original(archive, "VBASE.OVR")
        original_vpclv = read_original(archive, "VPCLV.OVR")
    expect_hash("original VBASE.OVR", original_vbase, ORIGINAL_VBASE_SHA256)
    expect_hash("original VPCLV.OVR", original_vpclv, ORIGINAL_VPCLV_SHA256)
    patched_vbase = apply_guarded_patches(original_vbase, VBASE_CENTERING_PATCHES)
    expect_hash("patched VBASE.OVR", patched_vbase, PATCHED_VBASE_SHA256)

    payloads: dict[str, bytes] = {}
    for name in (
        "DS.EXE",
        "MISC.HDR",
        "MSG.DBS",
        "MSG.HDR",
        "VBFONT0.VGA",
        "VPCVW.OVR",
        "korean_codebook.json",
    ):
        data = (args.baseline_dir / name).read_bytes()
        expect_hash(f"baseline {name}", data, BASELINE_HASHES[name])
        payloads[f"DSAVANT/{name}"] = data
    payloads["DSAVANT/VPCMK.OVR"] = patched_vpcmk
    payloads["DSAVANT/VBASE.OVR"] = patched_vbase
    payloads["DSAVANT/VPCLV.OVR"] = original_vpclv

    report = {
        "format": "Wizardry VII DOS v19 isolated UI alignment test v2",
        "scope": [
            "VPCMK six runtime-verified rendered-width centering sites",
            "VBASE selected-row and initial-list rendered-width centering sites",
            "VPCMK creation stats at Y=32+row*8 with synchronized arrows/hitboxes",
            "bonus row Y=100 with two-character numeric erase field",
        ],
        "excluded": [
            "skill row geometry",
            "skill-allocation flow control",
            "VPCVW/VPCLV layout experiments",
            "global strlen or literal-6 replacements",
        ],
        "geometry": {
            "stat_label_and_value": "X=117; Y=32+row*8",
            "stat_numeric_column": "X=133, matching the original English layout",
            "stat_arrows": "X=133/151; Y=32+row*8",
            "stat_hitboxes": "Y=32..39+row*8",
            "bonus": "Y=100; numeric field width=2",
            "stat_repaint": "X=102..168; Y=32..108",
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
        "vpcmk_patches": len(vpcmk_patches),
        "vbase_patches": len(VBASE_CENTERING_PATCHES),
        "overlay_sizes_unchanged": True,
    }
    report_bytes = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V2_REPORT.json"] = report_bytes

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
