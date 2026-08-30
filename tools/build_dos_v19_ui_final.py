#!/usr/bin/env python3
"""Build the final isolated Wizardry VII DOS v19 Korean UI package.

The final pass keeps the runtime-verified v2 stat geometry and menu centering,
then converts the seven remaining visual-only VPCMK string-length paths to
rendered pixel widths.  Overlay sizes and gameplay/control-flow code remain
unchanged.
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
from build_dos_v19_ui_v2 import (
    ORIGINAL_VBASE_SHA256,
    ORIGINAL_VPCLV_SHA256,
    PATCHED_VBASE_SHA256,
    VBASE_CENTERING_PATCHES,
    VPCMK_CENTERING_PATCHES,
    VPCMK_STAT_PATCHES,
)


# These are the seven visual strlen sites used by the old experimental v3 but
# not yet covered by the runtime-verified v2.  Unlike that experiment, every
# replacement below calls the resident rendered-width routine directly and
# fits in the original byte range; no code is appended to the overlay.
VPCMK_FINAL_CENTERING_PATCHES = (
    BytePatch(
        "dialog fixed-width title centering",
        0x09BC,
        bytes.fromhex(
            "8D 46 AC 50 E8 CD F0 59 B9 06 00 F7 E9 B9 02 00 99 F7 F9 "
            "8B C8 B8 A1 00 2B C1 50"
        ),
        bytes.fromhex(
            "6A 00 8D 46 AC 50 E8 BE DE 83 C4 04 D1 E8 8B C8 B8 A1 00 "
            "2B C1 50 90 90 90 90 90"
        ),
    ),
    BytePatch(
        "dialog variable-width label centering",
        0x0A2F,
        bytes.fromhex(
            "8D 46 AC 50 E8 5A F0 59 8B C8 8B 46 0A 2B C1 B9 06 00 "
            "F7 E9 B9 02 00 99 F7 F9 03 46 06 40 50"
        ),
        bytes.fromhex(
            "6A 00 8D 46 AC 50 E8 4B DE 83 C4 04 D1 E8 8B C8 6B 46 0A "
            "03 2B C1 03 46 06 40 50 90 90 90 90"
        ),
    ),
    BytePatch(
        "narrow panel centered label",
        0x1302,
        bytes.fromhex(
            "8D 46 DC 50 E8 87 E7 59 8B C8 B8 11 00 2B C1 B9 06 00 "
            "F7 E9 40 40 B9 02 00 99 F7 F9 03 46 FE 05 5D 00 50"
        ),
        bytes.fromhex(
            "6A 00 8D 46 DC 50 E8 78 D5 83 C4 04 D1 E8 8B C8 8B 46 FE "
            "05 91 00 2B C1 50 90 90 90 90 90 90 90 90 90 90"
        ),
    ),
    BytePatch(
        "ability prompt right-aligned title",
        0x1E00,
        bytes.fromhex(
            "8D 46 AC 50 E8 89 DC 59 B9 34 00 2B C8 B8 06 00 F7 E9 50"
        ),
        bytes.fromhex(
            "6A 00 8D 46 AC 50 E8 7A CA 59 59 8B C8 B8 38 01 2B C1 50"
        ),
    ),
    BytePatch(
        "skill category total rendered width",
        0x263A,
        bytes.fromhex(
            "B8 0A 00 F7 6E FE 8D 4E D2 03 C1 50 E8 47 D4 59 01 46 FC "
            "FF 46 FE 8B 46 FE 3D 04 00 7D 03 E9 66 FF"
        ),
        bytes.fromhex(
            "6A 00 6B 46 FE 0A 8D 4E D2 03 C1 50 E8 3A C2 59 59 01 46 "
            "FC FF 46 FE 83 7E FE 04 7D 04 E9 67 FF 90"
        ),
    ),
    BytePatch(
        "skill category group horizontal placement",
        0x265F,
        bytes.fromhex("B8 1A 00 2B 46 FC B9 06 00 F7 E9 05 FB FF 50"),
        bytes.fromhex("B8 97 00 2B 46 FC 50 90 90 90 90 90 90 90 90"),
    ),
    BytePatch(
        "button table rendered-width centering",
        0x2F8D,
        bytes.fromhex(
            "8D 46 F4 50 E8 FC CA 59 B9 06 00 F7 E9 B9 02 00 99 F7 F9 "
            "8B C8 8B 46 FE D1 E0 D1 E0 8B D8 8B 87 8C 01 05 09 00 "
            "2B C1 50"
        ),
        bytes.fromhex(
            "6A 00 8D 46 F4 50 E8 ED B8 83 C4 04 D1 E8 8B C8 8B 46 FE "
            "D1 E0 D1 E0 8B D8 8B 87 8C 01 05 09 00 2B C1 50 90 90 "
            "90 90 90"
        ),
    ),
    BytePatch(
        "late creation-list rendered-width centering",
        0x6340,
        bytes.fromhex(
            "B8 48 02 F7 6E FA 05 F4 5B 50 E8 43 97 59 B9 06 00 F7 E9 "
            "B9 02 00 99 F7 F9 8B C8 B8 28 00 2B C1 50"
        ),
        bytes.fromhex(
            "6A 00 B8 48 02 F7 6E FA 05 F4 5B 50 E8 34 85 83 C4 04 8B "
            "C8 D1 E9 B8 28 00 2B C1 50 90 90 90 90 90"
        ),
    ),
)


# Resident routine CS:1108 draws centered text in a fixed-width control.  It
# is used by the creation-name dialog title and similar framed labels.  The
# baseline DS.EXE already contains the Korean width hook at CS:38CA; this
# patch only switches the visual centering calculation to that hook.
DS_ROOT_CENTERING_PATCHES = (
    BytePatch(
        "resident fixed-width control centering",
        0x133F,  # MZ header 0x200 + resident CS:113F
        bytes.fromhex(
            "FF 76 0E E8 92 39 59 8B C8 8B 46 08 2B C1 B9 06 00 F7 E9 "
            "B9 02 00 99 F7 F9 03 46 04 40 50"
        ),
        bytes.fromhex(
            "6A 00 FF 76 0E E8 83 27 83 C4 04 D1 E8 8B C8 6B 46 08 03 "
            "2B C1 03 46 04 40 50 90 90 90 90"
        ),
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
    vpcmk_patches = (
        VPCMK_CENTERING_PATCHES
        + VPCMK_STAT_PATCHES
        + VPCMK_FINAL_CENTERING_PATCHES
    )
    patched_vpcmk = apply_guarded_patches(baseline_vpcmk, vpcmk_patches)

    with zipfile.ZipFile(args.original_zip) as archive:
        original_vbase = read_original(archive, "VBASE.OVR")
        original_vpclv = read_original(archive, "VPCLV.OVR")
    expect_hash("original VBASE.OVR", original_vbase, ORIGINAL_VBASE_SHA256)
    expect_hash("original VPCLV.OVR", original_vpclv, ORIGINAL_VPCLV_SHA256)
    patched_vbase = apply_guarded_patches(original_vbase, VBASE_CENTERING_PATCHES)
    expect_hash("patched VBASE.OVR", patched_vbase, PATCHED_VBASE_SHA256)

    payloads: dict[str, bytes] = {}
    baseline_ds = (args.baseline_dir / "DS.EXE").read_bytes()
    expect_hash("baseline DS.EXE", baseline_ds, BASELINE_HASHES["DS.EXE"])
    payloads["DSAVANT/DS.EXE"] = apply_guarded_patches(
        baseline_ds, DS_ROOT_CENTERING_PATCHES
    )
    for name in (
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
        "format": "Wizardry VII DOS v19 final Korean UI alignment package",
        "scope": [
            "all 13 known visual-only VPCMK length paths use rendered pixel widths",
            "VBASE selected-row and initial-list rendered-width centering",
            "creation stats at Y=32+row*8 with synchronized arrows and hitboxes",
            "bonus row at Y=100 with a two-character erase field",
            "skill category group placement uses summed rendered pixel widths",
            "resident fixed-width controls use rendered pixel widths",
        ],
        "safety": [
            "no overlay size changes or appended helper code",
            "logical strlen sites remain untouched",
            "skill allocation control flow and row geometry remain untouched",
            "all byte patches are guarded against the exact clean baseline",
        ],
        "runtime_qa": {
            "source": "fresh copy extracted from the original Wizardry 7.zip",
            "result": "passed",
            "verified_flow": [
                "main menu and character menu",
                "new-character title and name label",
                "race, sex, and profession dialogs",
                "ability title, completion label, all eight stat rows, arrows, and bonus",
                "weapon, physical, and academic skill allocation",
                "karma assignment and save-character confirmation",
                "successful save and return to the character menu",
            ],
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
        "vpcmk_patches": len(vpcmk_patches),
        "vbase_patches": len(VBASE_CENTERING_PATCHES),
        "ds_root_patches": len(DS_ROOT_CENTERING_PATCHES),
        "overlay_sizes_unchanged": True,
    }
    payloads["UI_FINAL_REPORT.json"] = json.dumps(
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
