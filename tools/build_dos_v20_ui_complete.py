#!/usr/bin/env python3
"""Build the comprehensive Wizardry VII DOS Korean UI geometry package.

This pass keeps the runtime-verified v19 character-creation changes, adds a
resident one-argument rendered-width adapter, and redirects only display
coordinate calculations across the resident executable and every overlay.
Logical string lengths used by editors, wrapping, allocation, and popup grid
dimensions remain byte-for-byte unchanged.
"""

from __future__ import annotations

import argparse
import json
import struct
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
from build_dos_v19_ui_final import (
    DS_ROOT_CENTERING_PATCHES,
    VPCMK_FINAL_CENTERING_PATCHES,
)
from build_dos_v19_ui_v2 import (
    VBASE_CENTERING_PATCHES,
    VPCMK_CENTERING_PATCHES,
    VPCMK_STAT_PATCHES,
)


MZ_HEADER_SIZE = 0x200
OVERLAY_ORIGIN = 0x5047
STRLEN_TARGET = 0x4AD7
WIDTH_TARGET = 0x38CA
WIDTH_ADAPTER = 0xF790

ORIGINAL_OVERLAY_HASHES = {
    "VBASE.OVR": "7919a6eddd0f7b65905ad4ab3a301604cccb8bf0f213ebebc190d5d1227104d6",
    "VDOPT.OVR": "0170e78e2766216ce3b20f631377423c655654b2c017096c57900bde3cd973f8",
    "VINIT.OVR": "c1dfd28e8e616070028ac7bd87b5aea5b85d6b6c80224a8a88bbe1774d415e67",
    "VMAZE.OVR": "887fe601d8d8bc16c44eccd83555355e4947c671b9360a478952873c5bf1abf6",
    "VMELE.OVR": "79bbcc667dc833cced3ff8e92b1bf8cc448659bb1d43166f3e770ce83e02b800",
    "VMEXE.OVR": "05655199184e4f499237e03e27a32726e2f22f4d387bbd1317df6af0bbe6cdb0",
    "VMEXT.OVR": "252536e7d9ec4d33a315945b6e17faaa98960ee02b5377afac7ad66490a6587f",
    "VMNPC.OVR": "02d7ca64e7207b71578f83c89d2dfe7519d5e25d4b2decd4681a6706b56b974d",
    "VPCLV.OVR": "429374f8c7c564d9e26a4050c241a4002dc5c73ea57f45610cb83f0866a235e2",
    "VPCMK.OVR": "dd1bcb9a54943163237ff48644c021ea202c36c15858fd7fd71520a5f871d28b",
    "VPCVW.OVR": "8dc7006599844bfd33ae60e11b59f7cedf47d649d84669fdf2546ed15779224d",
    "VPOPS.OVR": "f129f939aee779edb4fe5ce7f798532e631577a2a411b83ccc1c105cad19b4e8",
    "VTREA.OVR": "01cc4d590b3d351a91de40ca2b6da3b91c6a01354639f9a70630ce13234e40a1",
}


# Calls are overlay file offsets, except DS.EXE entries which are resident
# image offsets (the 0x200-byte MZ header is handled by the builder).
FORMULAS = {
    "DS.EXE": {
        "length_times_6": (0x22E7, 0x2348),
        "variable_minus_length_times_6": (0x0E77,),
    },
    "VBASE.OVR": {
        "length_times_6": (0x4211, 0x4C94),
        "constant_minus_length_times_6": (
            0x100B, 0x10C8, 0x635A, 0x63DD, 0x6455, 0x64F3,
        ),
    },
    "VDOPT.OVR": {
        "length_times_6": (0x0592, 0x05AF, 0x28B0),
        "variable_minus_length_times_6": (0x3811,),
    },
    "VINIT.OVR": {"length_times_6": (0x1088,)},
    "VMAZE.OVR": {"length_times_6": (0x0FFD, 0x1019)},
    "VMELE.OVR": {"length_times_6": (0x018F, 0x01AB)},
    "VMEXE.OVR": {
        "length_times_6": (0x03E1, 0x164B),
        "sum_of_lengths": (0x16EF, 0x16F7, 0x1704),
        "sum_final": (0x1704,),
    },
    "VMEXT.OVR": {"length_times_6": (0x0783, 0x079F, 0x15F7)},
    "VMNPC.OVR": {
        "length_times_6": (
            0x0B49, 0x121D, 0x1239, 0x12A3, 0x12C0, 0x133B,
            0x1DE5, 0x1E19, 0x4873, 0x48DA, 0x775A,
        ),
        "variable_minus_length_times_6": (0x1736, 0x190C, 0x1F1F, 0x3C1F),
    },
    "VPCLV.OVR": {
        "length_times_6": (0x05C8, 0x1069, 0x2620, 0x32B1),
        "constant_minus_length_times_6": (0x3C94,),
        "constant_minus_length_right_align": (0x08AA,),
    },
    "VPCVW.OVR": {
        "length_times_6": (
            0x02F0, 0x03E8, 0x109C, 0x1D5A, 0x2BAC, 0x46A3,
            0x6B50, 0x748C, 0x7636, 0x7850, 0x7A7D,
        ),
        "variable_minus_length_times_6": (0x1BB5, 0x1E62, 0x5860),
        "constant_minus_length_right_align": (0x137E,),
    },
    "VPOPS.OVR": {
        "length_times_6": (0x0162, 0x1BCA),
        "variable_minus_length_times_6": (0x1206, 0x2A77),
    },
    "VTREA.OVR": {
        "length_times_6": (
            0x09C4, 0x0EDE, 0x2690, 0x2704, 0x60BE, 0x6132,
            0x682A, 0x6882, 0x79F0, 0x7A3A,
        ),
        "constant_minus_length_times_6": (
            0x2FB9, 0x312E, 0x606E, 0x676A, 0x6D34,
        ),
        "variable_minus_length_times_6": (0x383B,),
        "sum_of_lengths": (0x0FF4, 0x1001, 0x100E),
        "sum_final": (0x100E,),
    },
}


# Explicit exclusions prove that logical length paths were reviewed rather
# than missed by the display-site inventory.
LOGICAL_LENGTH_EXCLUSIONS = {
    "VBASE.OVR": (0x0D54,),          # editable-field pixel extent
    "VPCMK.OVR": (0x0119, 0x268A, 0x6849, 0x6949),  # editors and byte-length checks
    "VPCLV.OVR": (0x39CF,),          # allocation loop accounting
    "VTREA.OVR": (0x764D,),          # popup grid column/character count
}


def near_call(target: int, source: int) -> bytes:
    return b"\xE8" + ((target - (source + 3)) & 0xFFFF).to_bytes(2, "little")


def call_target(data: bytes, offset: int, origin: int) -> int:
    displacement = int.from_bytes(data[offset + 1 : offset + 3], "little", signed=True)
    return (origin + offset + 3 + displacement) & 0xFFFF


def guarded_replace(data: bytearray, offset: int, expected: bytes, replacement: bytes, label: str) -> None:
    if len(expected) != len(replacement):
        raise ValueError(f"size-changing patch rejected: {label}")
    actual = bytes(data[offset : offset + len(expected)])
    if actual != expected:
        raise ValueError(
            f"{label}: unexpected bytes at 0x{offset:04X}: "
            f"expected {expected.hex(' ')}, got {actual.hex(' ')}"
        )
    data[offset : offset + len(replacement)] = replacement


def retarget_display_call(data: bytearray, offset: int, origin: int, label: str) -> None:
    if call_target(data, offset, origin) != STRLEN_TARGET:
        raise ValueError(f"{label}: call at 0x{offset:04X} is not strlen")
    data[offset : offset + 3] = near_call(WIDTH_ADAPTER, origin + offset)


def find_mul6(data: bytearray, call_offset: int, label: str) -> int:
    pattern = bytes.fromhex("B9 06 00 F7 E9")
    start = call_offset + 3
    offset = bytes(data).find(pattern, start, min(len(data), start + 52))
    if offset < 0:
        raise ValueError(f"{label}: no nearby AX*6 sequence")
    return offset


def patch_length_times_6(data: bytearray, offset: int, origin: int, label: str) -> None:
    retarget_display_call(data, offset, origin, label)
    multiply = find_mul6(data, offset, label)
    guarded_replace(data, multiply, bytes.fromhex("B9 06 00 F7 E9"), b"\x90" * 5, label)


def patch_constant_minus_length(data: bytearray, offset: int, origin: int, label: str) -> None:
    retarget_display_call(data, offset, origin, label)
    cursor = offset + 3
    prefix = bytes.fromhex("59 8B C8 B8")
    if bytes(data[cursor : cursor + 4]) != prefix:
        raise ValueError(f"{label}: unexpected constant-centering prefix")
    cells = int.from_bytes(data[cursor + 4 : cursor + 6], "little")
    tail = bytes.fromhex("2B C1 B9 06 00 F7 E9")
    if bytes(data[cursor + 6 : cursor + 13]) != tail:
        raise ValueError(f"{label}: unexpected constant-centering tail")
    data[cursor + 4 : cursor + 6] = (cells * 6).to_bytes(2, "little")
    data[cursor + 8 : cursor + 13] = b"\x90" * 5


def patch_variable_minus_length(data: bytearray, offset: int, origin: int, label: str) -> None:
    retarget_display_call(data, offset, origin, label)
    cursor = offset + 3
    prefix = bytes.fromhex("59 8B C8")
    if bytes(data[cursor : cursor + 3]) != prefix:
        raise ValueError(f"{label}: unexpected variable-centering prefix")
    expected = bytes(data[cursor + 3 : cursor + 13])
    if expected[:2] != bytes.fromhex("8B 46") or expected[3:] != bytes.fromhex("2B C1 B9 06 00 F7 E9"):
        raise ValueError(f"{label}: unexpected variable-centering expression")
    displacement = expected[2]
    replacement = bytes((0x6B, 0x46, displacement, 0x06, 0x2B, 0xC1)) + b"\x90" * 4
    guarded_replace(data, cursor + 3, expected, replacement, label)


def patch_right_align(data: bytearray, offset: int, origin: int, label: str) -> None:
    retarget_display_call(data, offset, origin, label)
    cursor = offset + 3
    if bytes(data[cursor : cursor + 2]) != bytes.fromhex("59 B9"):
        raise ValueError(f"{label}: unexpected right-align prefix")
    cells = int.from_bytes(data[cursor + 2 : cursor + 4], "little")
    expected = bytes(data[cursor + 4 : cursor + 11])
    if expected != bytes.fromhex("2B C8 B8 06 00 F7 E9"):
        raise ValueError(f"{label}: unexpected right-align expression")
    data[cursor + 2 : cursor + 4] = (cells * 6).to_bytes(2, "little")
    data[cursor + 4 : cursor + 11] = bytes.fromhex("2B C8 89 C8 90 90 90")


def patch_formula_set(name: str, source: bytes, origin: int) -> tuple[bytes, int]:
    data = bytearray(source)
    formulas = FORMULAS.get(name, {})
    count = 0
    for offset in formulas.get("length_times_6", ()):
        patch_length_times_6(data, offset, origin, f"{name} display width 0x{offset:04X}")
        count += 1
    for offset in formulas.get("constant_minus_length_times_6", ()):
        patch_constant_minus_length(data, offset, origin, f"{name} centered width 0x{offset:04X}")
        count += 1
    for offset in formulas.get("variable_minus_length_times_6", ()):
        patch_variable_minus_length(data, offset, origin, f"{name} variable centered width 0x{offset:04X}")
        count += 1
    for offset in formulas.get("constant_minus_length_right_align", ()):
        patch_right_align(data, offset, origin, f"{name} right aligned width 0x{offset:04X}")
        count += 1
    for offset in formulas.get("sum_of_lengths", ()):
        retarget_display_call(data, offset, origin, f"{name} summed display width 0x{offset:04X}")
        count += 1
    for offset in formulas.get("sum_final", ()):
        multiply = find_mul6(data, offset, f"{name} summed display total 0x{offset:04X}")
        guarded_replace(
            data, multiply, bytes.fromhex("B9 06 00 F7 E9"), b"\x90" * 5,
            f"{name} summed display total 0x{offset:04X}",
        )
    for offset in LOGICAL_LENGTH_EXCLUSIONS.get(name, ()):
        if call_target(data, offset, origin) != STRLEN_TARGET:
            raise ValueError(f"{name}: logical strlen exclusion changed at 0x{offset:04X}")
    return bytes(data), count


def width_adapter_bytes() -> bytes:
    # cdecl: width_adapter(text) -> resident_width(text, font_index=0)
    start = WIDTH_ADAPTER
    call_offset = start + 8
    return (
        bytes.fromhex("55 89 E5 6A 00 FF 76 04")
        + near_call(WIDTH_TARGET, call_offset)
        + bytes.fromhex("83 C4 04 89 EC 5D C3")
    )


def inject_width_adapter(ds_exe: bytes) -> bytes:
    if ds_exe[:2] != b"MZ" or struct.unpack_from("<H", ds_exe, 8)[0] * 16 != MZ_HEADER_SIZE:
        raise ValueError("unexpected DS.EXE header")
    data = bytearray(ds_exe)
    offset = MZ_HEADER_SIZE + WIDTH_ADAPTER
    adapter = width_adapter_bytes()
    guarded_replace(data, offset, b"\x00" * len(adapter), adapter, "resident width adapter")
    return bytes(data)


VBASE_SECURITY_SPACING_PATCHES = (
    BytePatch("security line 2 baseline 21->23", 0x644E, b"\x15\x00", b"\x17\x00"),
    BytePatch("security line 3 baseline 27->31", 0x64EC, b"\x1B\x00", b"\x1F\x00"),
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

    with zipfile.ZipFile(args.original_zip) as archive:
        originals = {name: read_original(archive, name) for name in ORIGINAL_OVERLAY_HASHES}
    for name, data in originals.items():
        expect_hash(f"original {name}", data, ORIGINAL_OVERLAY_HASHES[name])

    baseline_ds = (args.baseline_dir / "DS.EXE").read_bytes()
    expect_hash("baseline DS.EXE", baseline_ds, BASELINE_HASHES["DS.EXE"])
    ds = apply_guarded_patches(baseline_ds, DS_ROOT_CENTERING_PATCHES)
    ds = inject_width_adapter(ds)
    ds_image, ds_count = patch_formula_set("DS.EXE", ds[MZ_HEADER_SIZE:], 0)
    ds = ds[:MZ_HEADER_SIZE] + ds_image

    baseline_vpcmk = (args.baseline_dir / "VPCMK.OVR").read_bytes()
    expect_hash("baseline VPCMK.OVR", baseline_vpcmk, BASELINE_HASHES["VPCMK.OVR"])
    vpcmk = apply_guarded_patches(
        baseline_vpcmk,
        VPCMK_CENTERING_PATCHES + VPCMK_STAT_PATCHES + VPCMK_FINAL_CENTERING_PATCHES,
    )

    vbase = apply_guarded_patches(originals["VBASE.OVR"], VBASE_CENTERING_PATCHES)
    vbase, vbase_count = patch_formula_set("VBASE.OVR", vbase, OVERLAY_ORIGIN)
    vbase = apply_guarded_patches(vbase, VBASE_SECURITY_SPACING_PATCHES)

    overlay_sources = {
        name: data for name, data in originals.items()
        if name not in {"VBASE.OVR", "VPCMK.OVR", "VPCVW.OVR"}
    }
    baseline_vpcvw = (args.baseline_dir / "VPCVW.OVR").read_bytes()
    expect_hash("baseline VPCVW.OVR", baseline_vpcvw, BASELINE_HASHES["VPCVW.OVR"])
    overlay_sources["VPCVW.OVR"] = baseline_vpcvw

    patched_overlays = {"VBASE.OVR": vbase, "VPCMK.OVR": vpcmk}
    site_counts = {"DS.EXE": ds_count, "VBASE.OVR": vbase_count, "VPCMK.OVR": 13}
    for name, source in sorted(overlay_sources.items()):
        patched, count = patch_formula_set(name, source, OVERLAY_ORIGIN)
        patched_overlays[name] = patched
        site_counts[name] = count

    payloads: dict[str, bytes] = {"DSAVANT/DS.EXE": ds}
    for name in ("MISC.HDR", "MSG.DBS", "MSG.HDR", "VBFONT0.VGA", "korean_codebook.json"):
        data = (args.baseline_dir / name).read_bytes()
        expect_hash(f"baseline {name}", data, BASELINE_HASHES[name])
        payloads[f"DSAVANT/{name}"] = data
    for name, data in patched_overlays.items():
        payloads[f"DSAVANT/{name}"] = data

    report = {
        "format": "Wizardry VII DOS v20 comprehensive Korean UI geometry package",
        "scope": [
            "rendered pixel-width alignment in the resident UI and all 13 overlays",
            "runtime-verified v19 character creation/stat/hitbox geometry",
            "security-clearance body baselines changed from 15/21/27 to 15/23/31",
        ],
        "safety": [
            "all overlay sizes unchanged",
            "one 18-byte adapter placed in the verified empty resident renderer cave",
            "logical strlen paths for input, wrapping, allocation, and popup grids preserved",
            "every source hash and every changed instruction pattern guarded",
        ],
        "display_width_sites": site_counts,
        "display_width_site_total": sum(site_counts.values()),
        "logical_length_exclusions": {
            name: [f"0x{offset:04X}" for offset in offsets]
            for name, offsets in LOGICAL_LENGTH_EXCLUSIONS.items()
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    payloads["UI_COMPLETE_REPORT.json"] = json.dumps(
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
