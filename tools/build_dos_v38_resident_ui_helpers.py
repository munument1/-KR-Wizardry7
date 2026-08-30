#!/usr/bin/env python3
"""Relocate v37 UI resident helpers below the overlay load window.

Wizardry VII loads every OVR at runtime origin 0x5047. v20/v21 placed the
one-argument width adapter at 0xF790 and the stat repaint helper at 0xF7B0.
VMAZE and VMNPC overwrite both addresses. In particular, the save file dialog
runs from VBASE after gameplay; VBASE ends at 0xE562, so the stale VMAZE bytes
at 0xF790 survive and the dialog's width call jumps into unrelated VMAZE code.

This build moves only those two UI helpers into the dead tail of the resident
width trampoline (0x38F4..0x3920), retargets their callers, and erases the old
overlay-window copies. v37 scene helpers at 0xFDB0/0xFDF0 are deliberately
left unchanged for a separate VMNPC-safe relocation pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_dos_v19_baseline import expect_hash, sha256, write_deterministic_zip
from build_dos_v20_ui_complete import (
    FORMULAS,
    MZ_HEADER_SIZE,
    OVERLAY_ORIGIN,
    WIDTH_ADAPTER,
    WIDTH_TARGET,
    call_target,
    near_call,
    width_adapter_bytes,
)
from build_dos_v21_stat_repaint import (
    RECT_FILL_TARGET,
    STAT_REPAINT_HELPER,
    VPCMK_ORIGIN,
    VPCMK_STAT_DRAW_TARGET,
    stat_repaint_helper_bytes,
)


V37_HASHES = {
    "DS.EXE": "bb91ff02c2d3591dc21c11a01bef17cb06b97bb34f98fde8d17a0906a9f28136",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "MON63.PIC": "1f8b916f67ee9bd6fe60697c2f24cc8bb35b0e32622214cb3d9ddf1c2a410781",
    "MSG.DBS": "d01b044e5d2481ab26711e89b5fba07b18c7f1b3b9cc541a5e8b865d8d121373",
    "MSG.HDR": "643a73e4f518d55be84abe72579554590af6b2a89403320d623ab30ca39d0455",
    "VBASE.OVR": "9ecb4ed4d07d34649fbc44ec5835e32d774221a02244a10922f0a3d83f8f5eb2",
    "VBFONT0.VGA": "e425f17118abbc2d7599c61f89324ea9162939a97383f35d17c11e90d7cd4750",
    "VDOPT.OVR": "b2574cecefcc55f2b42cac509c4428f696da27cfdb558b44082a0b19e516be92",
    "VINIT.OVR": "63a88cc454817c243d3c6023107a86e2c6926dc9a38cd63e773843e1da96b2a6",
    "VMAZE.OVR": "7a17deb42cde8b6e82d0c4d401114bc4bb04261d5f8f3d24b8cd4456159a520a",
    "VMELE.OVR": "e56c555e3343fc869aa49fd8419e40a2271ee370de023f7ae8d453afa7a7e8a4",
    "VMEXE.OVR": "8058f9c1ed4d6409c9922969b57aa972864fa396c2d4bb7d353d8a5ec580d3da",
    "VMEXT.OVR": "e9f9f77d1312b370e146e2d4f86edd7dea7cbbf36a10af04168fdfb7f7222029",
    "VMNPC.OVR": "dfedb6b59cb12bc3d79e54f0e163969bd7dfe39b76a12a7d0a9abb02677d7fb1",
    "VPCLV.OVR": "2f83def79e4027ea65eea40b44fac7782a99140f6bbf02c7aa385f93827ab9fd",
    "VPCMK.OVR": "36b50daea346973750a0cc9c9b18c7b222f216cc73662e01e7c1dd1ee52a625f",
    "VPCVW.OVR": "d3e7efbbdff13860acdb47c36cf9428d5a6e3533a5b382d57cb6cd327e216197",
    "VPOPS.OVR": "cb554c9af7d5e105e96fe89adb654dd80f2daabffe5228bbe7aa2adce02819ee",
    "VTREA.OVR": "954cba83a89a90fab919ce8af72191d6c6a92d894c516f7fd1303934395ce045",
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
}

NEW_WIDTH_ADAPTER = 0x38F4
NEW_STAT_REPAINT_HELPER = 0x3906
ROOT_DEAD_TAIL_END = 0x3921
ROOT_DEAD_TAIL_EXPECTED = bytes.fromhex(
    "89 46 FE 33 C9 8B 76 04 BB 10 00 32 E4 8A 04 0A C0 74 "
    "12 D1 E0 03 D8 33 C0 26 8A 47 01 03 C8 03 4E FE 46 EB E3 8B"
)


def relocated_width_adapter_bytes() -> bytes:
    start = NEW_WIDTH_ADAPTER
    return (
        bytes.fromhex("55 89 E5 6A 00 FF 76 04")
        + near_call(WIDTH_TARGET, start + 8)
        + bytes.fromhex("83 C4 04 89 EC 5D C3")
    )


def near_jump(target: int, source: int) -> bytes:
    return b"\xE9" + ((target - (source + 3)) & 0xFFFF).to_bytes(2, "little")


def compact_stat_repaint_bytes() -> bytes:
    start = NEW_STAT_REPAINT_HELPER
    # The caller has already pushed VPCMK's two normal stat-draw arguments.
    # Clear the rectangle and tail-jump to the original draw routine so its
    # RET returns directly to the original caller with the same stack layout.
    return (
        bytes.fromhex("6A 00 6A 6C 68 A8 00 6A 20 6A 66")
        + near_call(RECT_FILL_TARGET, start + 11)
        + bytes.fromhex("83 C4 0A")
        + near_jump(VPCMK_STAT_DRAW_TARGET, start + 17)
    )


def formula_call_sites(name: str) -> list[int]:
    formulas = FORMULAS.get(name, {})
    return sorted(
        {
            offset
            for kind, offsets in formulas.items()
            if kind != "sum_final"
            for offset in offsets
        }
    )


def retarget_formula_calls(name: str, source: bytes) -> tuple[bytes, int]:
    data = bytearray(source)
    image = data[MZ_HEADER_SIZE:] if name == "DS.EXE" else data
    origin = 0 if name == "DS.EXE" else OVERLAY_ORIGIN
    count = 0
    for offset in formula_call_sites(name):
        actual = call_target(image, offset, origin)
        if actual != WIDTH_ADAPTER:
            raise ValueError(
                f"{name} 0x{offset:04X}: width call targets 0x{actual:04X}, "
                f"expected 0x{WIDTH_ADAPTER:04X}"
            )
        image[offset : offset + 3] = near_call(
            NEW_WIDTH_ADAPTER, origin + offset
        )
        count += 1
    if name == "DS.EXE":
        data[MZ_HEADER_SIZE:] = image
    return bytes(data), count


def relocate_ds_helpers(source: bytes) -> bytes:
    data = bytearray(source)
    image = bytearray(data[MZ_HEADER_SIZE:])
    old_width = width_adapter_bytes()
    old_stat = stat_repaint_helper_bytes()

    if bytes(image[WIDTH_ADAPTER : WIDTH_ADAPTER + len(old_width)]) != old_width:
        raise ValueError("v37 width adapter bytes do not match")
    if bytes(
        image[STAT_REPAINT_HELPER : STAT_REPAINT_HELPER + len(old_stat)]
    ) != old_stat:
        raise ValueError("v37 stat repaint helper bytes do not match")
    if bytes(
        image[
            NEW_WIDTH_ADAPTER : NEW_WIDTH_ADAPTER + len(ROOT_DEAD_TAIL_EXPECTED)
        ]
    ) != ROOT_DEAD_TAIL_EXPECTED:
        raise ValueError(
            "resident width-function dead tail no longer matches guarded v37 bytes"
        )

    new_width = relocated_width_adapter_bytes()
    new_stat = compact_stat_repaint_bytes()
    if NEW_WIDTH_ADAPTER + len(new_width) != NEW_STAT_REPAINT_HELPER:
        raise AssertionError("relocated width adapter layout changed")
    if NEW_STAT_REPAINT_HELPER + len(new_stat) > ROOT_DEAD_TAIL_END:
        raise AssertionError("relocated stat helper exceeds resident dead tail")

    image[WIDTH_ADAPTER : WIDTH_ADAPTER + len(old_width)] = b"\x00" * len(old_width)
    image[
        STAT_REPAINT_HELPER : STAT_REPAINT_HELPER + len(old_stat)
    ] = b"\x00" * len(old_stat)
    image[
        NEW_WIDTH_ADAPTER : NEW_WIDTH_ADAPTER + len(new_width)
    ] = new_width
    image[
        NEW_STAT_REPAINT_HELPER : NEW_STAT_REPAINT_HELPER + len(new_stat)
    ] = new_stat
    data[MZ_HEADER_SIZE:] = image
    return bytes(data)


def retarget_stat_call(source: bytes) -> bytes:
    data = bytearray(source)
    offset = 0x46E2
    actual = call_target(data, offset, VPCMK_ORIGIN)
    if actual != STAT_REPAINT_HELPER:
        raise ValueError(
            f"VPCMK stat redraw targets 0x{actual:04X}, "
            f"expected 0x{STAT_REPAINT_HELPER:04X}"
        )
    data[offset : offset + 3] = near_call(
        NEW_STAT_REPAINT_HELPER, VPCMK_ORIGIN + offset
    )
    return bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v37-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")
    source_dir = (
        args.v37_dir / "DSAVANT"
        if (args.v37_dir / "DSAVANT").is_dir()
        else args.v37_dir
    )

    payloads: dict[str, bytes] = {}
    retarget_counts: dict[str, int] = {}
    for name, expected_hash in V37_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v37 {name}", source, expected_hash)

        if name == "DS.EXE":
            source = relocate_ds_helpers(source)
            source, count = retarget_formula_calls(name, source)
            retarget_counts[name] = count
        elif name in FORMULAS:
            source, count = retarget_formula_calls(name, source)
            retarget_counts[name] = count

        if name == "VPCMK.OVR":
            source = retarget_stat_call(source)
        payloads[f"DSAVANT/{name}"] = source

    report = {
        "format": "Wizardry VII DOS v38 resident UI helper relocation",
        "root_cause": (
            "v20/v21 UI helpers at 0xF790/0xF7B0 are inside the overlay load "
            "window; VMAZE overwrites them, and VBASE save-file UI later calls "
            "the stale 0xF790 bytes"
        ),
        "changes": [
            "move one-argument width adapter to resident 0x38F4",
            "move stat repaint helper to resident 0x3906 using a compact tail-call implementation",
            "retarget all v20 FORMULAS calls and the VPCMK stat redraw call",
            "erase old 0xF790/0xF7B0 helper bodies",
            "leave v37 scene helpers unchanged for a separate VMNPC-safe pass",
        ],
        "layout": {
            "overlay_origin": "0x5047",
            "new_width_adapter": f"0x{NEW_WIDTH_ADAPTER:04X}",
            "new_stat_repaint": f"0x{NEW_STAT_REPAINT_HELPER:04X}",
            "resident_dead_tail_end": f"0x{ROOT_DEAD_TAIL_END:04X}",
        },
        "retarget_counts": retarget_counts,
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V38_REPORT.json"] = report_raw

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
