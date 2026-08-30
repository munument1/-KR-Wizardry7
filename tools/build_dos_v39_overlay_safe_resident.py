#!/usr/bin/env python3
"""Build v39 with every persistent helper outside the overlay load window.

v37 still contains four root-CS helper bodies inside the 0x5047+ overlay area:

- v20 WIDTH_ADAPTER at 0xF790
- v21 STAT_REPAINT_HELPER at 0xF7B0
- v37 scene-find helper at 0xFDB0
- v37 trailing-ASCII helper at 0xFDF0

VMAZE overwrites the first two and VMNPC overwrites all four relevant high
addresses. v39 removes that architecture entirely:

- a compact dual one-argument adapter and stat repaint helper live in the dead
  tail immediately after the v19 root width trampoline, below 0x5047;
- scene parsing lives in the already resident VBFONT0 segment at 0x0AF0, before
  the inverse table at 0x0D00;
- the existing safe root width trampoline at 0x38CA becomes the common gateway.

No executable helper remains in the overlay window. File sizes and save format
remain unchanged.
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
from build_dos_v25_scene_text import scene_find_helper_bytes
from build_dos_v26_scene_text import trailing_ascii_helper_bytes
from build_dos_v37_fixed_scene_helpers import (
    RELOCATED_FIND_HELPER,
    RELOCATED_TRAILING_HELPER,
    SCENE_USERS,
)
from build_dos_v38_resident_ui_helpers import V37_HASHES


ROOT_WIDTH_ADAPTER = 0x38F4
ROOT_TRAILING_ADAPTER = 0x38F8
ROOT_COMMON_ENTRY = 0x38FB
ROOT_STAT_REPAINT = 0x390C
ROOT_SAFE_END = 0x3921

# Exact v37 bytes in the original rendered-width routine tail. v19 replaces
# 0x38CA..0x38F3; these 45 following bytes are unreachable before the next root
# function at 0x3921.
ROOT_DEAD_TAIL_EXPECTED = bytes.fromhex(
    "89 46 FE 33 C9 8B 76 04 BB 10 00 32 E4 8A 04 0A C0 74 12 D1 E0 "
    "03 D8 33 C0 26 8A 47 01 03 C8 03 4E FE 46 EB E3 8B C1 5E 07 "
    "8B E5 5D C3"
)

FONT_WIDTH_ENTRY = 0x0A30
FONT_WIDTH_CONTINUATION = 0x0A33
FONT_DISPATCHER = 0x0AF0
FONT_INVERSE_TABLE = 0x0D00
FONT_WIDTH_ENTRY_EXPECTED = bytes.fromhex("55 89 E5")

# Assembled from src/dos_v39/font_dispatch.S at text address 0x0AF0.
FONT_DISPATCHER_BYTES = bytes.fromhex(
    "55 89 E5 8B 46 08 83 F8 20 74 0D 83 F8 5F 74 08 3D 00 01 74 39 "
    "E9 2B FF 56 53 FC 8B 76 06 31 DB AC 84 C0 74 1C 3C 17 75 10 "
    "AC 3C 17 74 06 46 83 C3 03 EB EC 83 C3 02 EB E7 3A 46 08 74 "
    "08 43 EB DF B8 FF FF EB 02 89 D8 5B 5E 89 EC 5D CB 56 53 FC "
    "8B 76 06 31 DB AC 84 C0 74 19 3C 17 75 0F AC 3C 17 74 05 46 "
    "31 DB EB ED BB 17 00 EB E8 30 E4 89 C3 EB E2 89 D8 5B 5E 89 "
    "EC 5D CB"
)


def near_jump(target: int, source: int) -> bytes:
    displacement = target - (source + 3)
    if not -0x8000 <= displacement <= 0x7FFF:
        raise ValueError("near jump target out of range")
    return b"\xE9" + (displacement & 0xFFFF).to_bytes(2, "little")


def root_helper_block() -> bytes:
    """44-byte width/trailing adapter + stat tail-call block."""
    common_call = ROOT_COMMON_ENTRY + 7
    stat_call = ROOT_STAT_REPAINT + 11
    stat_jump = ROOT_STAT_REPAINT + 17
    block = (
        bytes.fromhex("31 C0 EB 03")               # width: AX=0; jmp common
        + bytes.fromhex("B8 00 01")                # trailing: AX=0x0100
        + bytes.fromhex("55 89 E5 50 FF 76 04")    # common frame + args
        + near_call(WIDTH_TARGET, common_call)
        + bytes.fromhex("83 C4 04 89 EC 5D C3")
        + bytes.fromhex("6A 00 6A 6C 68 A8 00 6A 20 6A 66")
        + near_call(RECT_FILL_TARGET, stat_call)
        + bytes.fromhex("83 C4 0A")
        + near_jump(VPCMK_STAT_DRAW_TARGET, stat_jump)
    )
    if len(block) != 44:
        raise AssertionError(f"root helper block size changed: {len(block)}")
    return block


def font_width_dispatch_jump() -> bytes:
    return near_jump(FONT_DISPATCHER, FONT_WIDTH_ENTRY)


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
                f"{name} 0x{offset:04X}: expected width target "
                f"0x{WIDTH_ADAPTER:04X}, found 0x{actual:04X}"
            )
        image[offset : offset + 3] = near_call(
            ROOT_WIDTH_ADAPTER, origin + offset
        )
        count += 1
    if name == "DS.EXE":
        data[MZ_HEADER_SIZE:] = image
    return bytes(data), count


def patch_root_helpers(ds_exe: bytes) -> bytes:
    data = bytearray(ds_exe)
    image = bytearray(data[MZ_HEADER_SIZE:])

    old_helpers = (
        (WIDTH_ADAPTER, width_adapter_bytes(), "v20 width adapter"),
        (STAT_REPAINT_HELPER, stat_repaint_helper_bytes(), "v21 stat repaint"),
        (RELOCATED_FIND_HELPER, scene_find_helper_bytes(), "v37 scene find"),
        (
            RELOCATED_TRAILING_HELPER,
            trailing_ascii_helper_bytes(),
            "v37 trailing ASCII",
        ),
    )
    for runtime, helper, label in old_helpers:
        actual = bytes(image[runtime : runtime + len(helper)])
        if actual != helper:
            raise ValueError(f"{label} bytes do not match v37 at 0x{runtime:04X}")
        image[runtime : runtime + len(helper)] = b"\x00" * len(helper)

    actual_tail = bytes(
        image[ROOT_WIDTH_ADAPTER : ROOT_WIDTH_ADAPTER + len(ROOT_DEAD_TAIL_EXPECTED)]
    )
    if actual_tail != ROOT_DEAD_TAIL_EXPECTED:
        raise ValueError("root width dead tail no longer matches guarded v37 bytes")

    block = root_helper_block()
    if ROOT_WIDTH_ADAPTER + len(block) > ROOT_SAFE_END:
        raise AssertionError("root helper block exceeds pre-overlay resident range")
    image[ROOT_WIDTH_ADAPTER : ROOT_WIDTH_ADAPTER + len(block)] = block

    data[MZ_HEADER_SIZE:] = image
    return bytes(data)


def patch_font_resident(vbfont0: bytes) -> bytes:
    data = bytearray(vbfont0)
    if len(data) < FONT_INVERSE_TABLE:
        raise ValueError("VBFONT0.VGA is too small for the v19 resident layout")
    actual_entry = bytes(data[FONT_WIDTH_ENTRY : FONT_WIDTH_ENTRY + 3])
    if actual_entry != FONT_WIDTH_ENTRY_EXPECTED:
        raise ValueError(
            "VBFONT0 resident_width entry does not match v19 bytes: "
            f"{actual_entry.hex(' ')}"
        )
    destination = bytes(
        data[FONT_DISPATCHER : FONT_DISPATCHER + len(FONT_DISPATCHER_BYTES)]
    )
    if destination != b"\x00" * len(FONT_DISPATCHER_BYTES):
        raise ValueError("VBFONT0 0x0AF0 resident dispatcher area is not empty")
    if FONT_DISPATCHER + len(FONT_DISPATCHER_BYTES) > FONT_INVERSE_TABLE:
        raise AssertionError("font dispatcher overlaps the inverse table")

    data[FONT_WIDTH_ENTRY : FONT_WIDTH_ENTRY + 3] = font_width_dispatch_jump()
    data[FONT_DISPATCHER : FONT_DISPATCHER + len(FONT_DISPATCHER_BYTES)] = (
        FONT_DISPATCHER_BYTES
    )
    return bytes(data)


def retarget_stat_call(vpcmk: bytes) -> bytes:
    data = bytearray(vpcmk)
    offset = 0x46E2
    actual = call_target(data, offset, VPCMK_ORIGIN)
    if actual != STAT_REPAINT_HELPER:
        raise ValueError(
            f"VPCMK stat redraw expected 0x{STAT_REPAINT_HELPER:04X}, "
            f"found 0x{actual:04X}"
        )
    data[offset : offset + 3] = near_call(
        ROOT_STAT_REPAINT, VPCMK_ORIGIN + offset
    )
    return bytes(data)


def retarget_scene_user(name: str, source: bytes) -> tuple[bytes, int, int]:
    spec = SCENE_USERS[name]
    data = bytearray(source)
    find_count = 0
    for offset in spec["find_calls"]:
        actual = call_target(data, offset, OVERLAY_ORIGIN)
        if actual != RELOCATED_FIND_HELPER:
            raise ValueError(
                f"{name} find 0x{offset:04X}: expected "
                f"0x{RELOCATED_FIND_HELPER:04X}, found 0x{actual:04X}"
            )
        # Existing arguments are already find(text, targetByte), exactly the
        # same two-word shape as width(text, fontIndex). The FontResident
        # dispatcher treats 0x20/0x5F as find operations.
        data[offset : offset + 3] = near_call(WIDTH_TARGET, OVERLAY_ORIGIN + offset)
        find_count += 1

    trailing_call = spec["trailing_site"] + 3
    actual = call_target(data, trailing_call, OVERLAY_ORIGIN)
    if actual != RELOCATED_TRAILING_HELPER:
        raise ValueError(
            f"{name} trailing: expected 0x{RELOCATED_TRAILING_HELPER:04X}, "
            f"found 0x{actual:04X}"
        )
    data[trailing_call : trailing_call + 3] = near_call(
        ROOT_TRAILING_ADAPTER, OVERLAY_ORIGIN + trailing_call
    )
    return bytes(data), find_count, 1


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
    formula_counts: dict[str, int] = {}
    scene_counts: dict[str, dict[str, int]] = {}

    for name, expected_hash in V37_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v37 {name}", source, expected_hash)

        if name == "DS.EXE":
            source = patch_root_helpers(source)
            source, count = retarget_formula_calls(name, source)
            formula_counts[name] = count
        elif name == "VBFONT0.VGA":
            source = patch_font_resident(source)
        else:
            if name in FORMULAS:
                source, count = retarget_formula_calls(name, source)
                formula_counts[name] = count
            if name == "VPCMK.OVR":
                source = retarget_stat_call(source)
            if name in SCENE_USERS:
                source, find_count, trailing_count = retarget_scene_user(name, source)
                scene_counts[name] = {
                    "find_calls": find_count,
                    "trailing_calls": trailing_count,
                }

        payloads[f"DSAVANT/{name}"] = source

    report = {
        "format": "Wizardry VII DOS v39 overlay-safe resident architecture",
        "root_cause": [
            "persistent helpers were placed inside the 0x5047+ overlay window",
            "VMAZE overwrote 0xF790/0xF7B0 and VMNPC also overwrote 0xFDB0/0xFDF0",
        ],
        "changes": [
            "move UI width adapter to root 0x38F4",
            "add trailing-scene adapter at root 0x38F8",
            "move compact stat repaint helper to root 0x390C",
            "route scene find calls directly through safe root width hook 0x38CA",
            "add find/trailing dispatcher to resident VBFONT0 at 0x0AF0",
            "erase all four obsolete high-address helper bodies",
        ],
        "layout": {
            "overlay_origin": f"0x{OVERLAY_ORIGIN:04X}",
            "root_width_hook": f"0x{WIDTH_TARGET:04X}",
            "root_width_adapter": f"0x{ROOT_WIDTH_ADAPTER:04X}",
            "root_trailing_adapter": f"0x{ROOT_TRAILING_ADAPTER:04X}",
            "root_stat_repaint": f"0x{ROOT_STAT_REPAINT:04X}",
            "font_dispatcher": f"0x{FONT_DISPATCHER:04X}",
            "font_dispatcher_end": f"0x{FONT_DISPATCHER + len(FONT_DISPATCHER_BYTES):04X}",
            "font_inverse_table": f"0x{FONT_INVERSE_TABLE:04X}",
        },
        "formula_retargets": formula_counts,
        "scene_retargets": scene_counts,
        "invariants": [
            "all persistent root helpers end below overlay origin 0x5047",
            "font dispatcher ends before inverse table 0x0D00",
            "DS.EXE, VBFONT0.VGA, and every OVR retain their original v37 file sizes",
            "save-file structure and save routine body are untouched",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V39_REPORT.json"] = report_raw

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
