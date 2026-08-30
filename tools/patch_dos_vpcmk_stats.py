#!/usr/bin/env python3
"""Patch only the character-creation stat editor in baseline VPCMK.OVR.

The Korean stat labels are two 8-pixel glyphs (16 pixels), while the original
three-letter labels occupy 18 pixels.  Moving the shared label/value stream two
pixels right restores the original numeric-column start.  All vertical draw,
arrow, hitbox, and repaint coordinates use one 8-pixel grid.  The bonus number
uses a two-character field so a transition from 10 to 9 erases the old zero.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_dos_v19_baseline import BytePatch, apply_guarded_patches, expect_hash, sha256


BASELINE_SHA256 = "702211c25215eb0e1e3d4a9a0373afa83c15b963ec1912f74a3c1055c878b04e"
OUTPUT_SHA256 = "0f725e136affa55cf0c0cd70f64df9d589d692dbc5e08b34b8479e010aa5d780"

STAT_PATCHES = (
    BytePatch("stat row stride 7->8", 0x19D7, b"\xB8\x07\x00", b"\xB8\x08\x00"),
    BytePatch("stat row base 32->24", 0x19DD, b"\x05\x20\x00", b"\x05\x18\x00"),
    BytePatch("Korean label/value stream X 115->117", 0x19E1, b"\xB8\x73\x00", b"\xB8\x75\x00"),
    BytePatch("bonus numeric field width 1->2", 0x1A5F, b"\xB8\x01\x00", b"\xB8\x02\x00"),
    BytePatch("stat repaint top 35->24", 0x1A89, b"\xB8\x23\x00", b"\xB8\x18\x00"),
    BytePatch("left arrow row stride 6->8", 0x46F6, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("left arrow row base 35->24", 0x46FC, b"\x05\x23\x00", b"\x05\x18\x00"),
    BytePatch("right arrow row stride 6->8", 0x4718, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("right arrow row base 35->24", 0x471E, b"\x05\x23\x00", b"\x05\x18\x00"),
    BytePatch("selected-left hitbox bottom stride 6->8", 0x474F, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("selected-left hitbox bottom 40->31", 0x4755, b"\x05\x28\x00", b"\x05\x1F\x00"),
    BytePatch("selected-left hitbox top stride 6->8", 0x475D, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("selected-left hitbox top 35->24", 0x4763, b"\x05\x23\x00", b"\x05\x18\x00"),
    BytePatch("selected-right hitbox bottom stride 6->8", 0x477C, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("selected-right hitbox bottom 40->31", 0x4782, b"\x05\x28\x00", b"\x05\x1F\x00"),
    BytePatch("selected-right hitbox top stride 6->8", 0x478A, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("selected-right hitbox top 35->24", 0x4790, b"\x05\x23\x00", b"\x05\x18\x00"),
    BytePatch("unselected-row hitbox bottom stride 6->8", 0x47C1, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("unselected-row hitbox bottom 40->31", 0x47C7, b"\x05\x28\x00", b"\x05\x1F\x00"),
    BytePatch("unselected-row hitbox top stride 6->8", 0x47CF, b"\xB8\x06\x00", b"\xB8\x08\x00"),
    BytePatch("unselected-row hitbox top 35->24", 0x47D5, b"\x05\x23\x00", b"\x05\x18\x00"),
    BytePatch("stat input repaint top 35->24", 0x4812, b"\xB8\x23\x00", b"\xB8\x18\x00"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    expect_hash("baseline VPCMK.OVR", source, BASELINE_SHA256)
    output = apply_guarded_patches(source, STAT_PATCHES)
    expect_hash("patched VPCMK.OVR", output, OUTPUT_SHA256)
    if len(output) != 29_885:
        raise AssertionError(f"unexpected VPCMK.OVR size {len(output)}")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "source": str(args.input.resolve()),
        "source_sha256": sha256(source),
        "output": str(args.output.resolve()),
        "output_sha256": sha256(output),
        "size": len(output),
        "size_unchanged": len(output) == len(source),
        "scope": "VPCMK character-creation stat editor only",
        "geometry": {
            "label_and_value": "X=117; Y=24+row*8",
            "numeric_column": "starts at original English column X=133",
            "left_arrow": "X=133; Y=24+row*8",
            "right_arrow": "X=151; Y=24+row*8",
            "hitboxes": "Y=24..31+row*8",
            "bonus": "Y=89; numeric field width=2",
            "repaint": "X=102..168; Y=24..96",
        },
        "patches": [
            {
                "label": patch.label,
                "offset": f"0x{patch.offset:X}",
                "expected": patch.expected.hex(" ").upper(),
                "replacement": patch.replacement.hex(" ").upper(),
            }
            for patch in STAT_PATCHES
        ],
    }
    report_path = args.output.with_suffix(args.output.suffix + ".json")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
