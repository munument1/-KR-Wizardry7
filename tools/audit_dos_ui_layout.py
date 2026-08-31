#!/usr/bin/env python3
"""Inventory Wizardry VII DOS UI length and six-pixel layout operations."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_16


OVERLAY_ORIGIN = 0x5047
STRLEN_TARGET = 0x4AD7


def disassembly_context(data: bytes, offset: int, origin: int) -> list[str]:
    """Return a best-effort 16-bit instruction window around *offset*."""
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    best_before = []
    for start in range(max(0, offset - 28), offset + 1):
        decoded = list(decoder.disasm(data[start : offset + 3], origin + start))
        if decoded and decoded[-1].address == origin + offset:
            best_before = decoded
            break
    after = list(decoder.disasm(data[offset + 3 : offset + 51], origin + offset + 3))
    instructions = best_before[-8:] + after[:12]
    return [
        f"{instruction.address:04X}: {instruction.mnemonic} {instruction.op_str}".rstrip()
        for instruction in instructions
    ]


def near_call_target(data: bytes, offset: int, origin: int) -> int:
    displacement = int.from_bytes(data[offset + 1 : offset + 3], "little", signed=True)
    return origin + offset + 3 + displacement


def classify_strlen_site(data: bytes, offset: int) -> str:
    before = data[max(0, offset - 16) : offset]
    after = data[offset + 3 : offset + 48]
    visual_multiply = (
        b"\xb9\x06\x00\xf7\xe9" in after
        or b"\xb8\x06\x00\xf7\xe9" in after
    )
    logical_markers = (
        b"\x3d\x00\x00" in after[:12]
        or b"\x85\xc0" in after[:12]
        or b"\x48\x89" in after[:12]
        or b"\x48\x3b" in after[:12]
    )
    if visual_multiply:
        return "visual_cell_width"
    if logical_markers:
        return "logical_length"
    if before.endswith((b"\xff\x76\x04", b"\x8d\x46\xf4\x50")):
        return "likely_logical"
    return "review"


def formula_after_strlen(data: bytes, offset: int) -> str:
    after = data[offset + 3 : offset + 56]
    patterns = (
        (bytes.fromhex("59 B9 06 00 F7 E9"), "length_times_6"),
        (bytes.fromhex("59 8B C8 B8"), "constant_minus_length_times_6"),
        (bytes.fromhex("59 8B C8 8B 46"), "variable_minus_length_times_6"),
        (bytes.fromhex("59 B9"), "constant_minus_length_right_align"),
        (bytes.fromhex("59 50"), "sum_of_lengths"),
        (bytes.fromhex("59 8B C8 58 03 C1"), "sum_of_lengths"),
        (bytes.fromhex("59 01 46"), "logical_input_extent"),
    )
    for pattern, label in patterns:
        if after.startswith(pattern):
            return label
    return "other"


def overlay_report(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    strlen_sites = []
    for offset in range(len(data) - 2):
        if data[offset] != 0xE8:
            continue
        if near_call_target(data, offset, OVERLAY_ORIGIN) != STRLEN_TARGET:
            continue
        strlen_sites.append(
            {
                "offset": f"0x{offset:04X}",
                "classification": classify_strlen_site(data, offset),
                "formula": formula_after_strlen(data, offset),
                "before": data[max(0, offset - 12) : offset].hex(" "),
                "after": data[offset + 3 : offset + 35].hex(" "),
                "disassembly": disassembly_context(data, offset, OVERLAY_ORIGIN),
            }
        )

    six_pixel_patterns = []
    patterns = {
        "imul_ax_by_6": bytes.fromhex("B9 06 00 F7 E9"),
        "row_stride_ax_6": bytes.fromhex("B8 06 00 F7 6E"),
    }
    for label, pattern in patterns.items():
        start = 0
        while True:
            offset = data.find(pattern, start)
            if offset < 0:
                break
            six_pixel_patterns.append({"offset": f"0x{offset:04X}", "kind": label})
            start = offset + 1

    return {
        "file": path.name,
        "size": len(data),
        "strlen_sites": strlen_sites,
        "six_pixel_patterns": six_pixel_patterns,
    }


def resident_report(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if raw[:2] != b"MZ":
        raise ValueError(f"not an MZ executable: {path}")
    header_size = struct.unpack_from("<H", raw, 8)[0] * 16
    image = raw[header_size:]
    strlen_sites = []
    for offset in range(len(image) - 2):
        if image[offset] != 0xE8:
            continue
        if near_call_target(image, offset, 0) != STRLEN_TARGET:
            continue
        strlen_sites.append(
            {
                "offset": f"0x{offset:04X}",
                "file_offset": f"0x{header_size + offset:04X}",
                "classification": classify_strlen_site(image, offset),
                "formula": formula_after_strlen(image, offset),
                "before": image[max(0, offset - 12) : offset].hex(" "),
                "after": image[offset + 3 : offset + 35].hex(" "),
                "disassembly": disassembly_context(image, offset, 0),
            }
        )
    return {
        "file": path.name,
        "size": len(raw),
        "mz_header_size": header_size,
        "strlen_sites": strlen_sites,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dsavant", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    reports = [resident_report(args.dsavant / "DS.EXE")]
    reports.extend(overlay_report(path) for path in sorted(args.dsavant.glob("*.OVR")))
    reports = [report for report in reports if report.get("strlen_sites")]
    rendered = json.dumps(reports, ensure_ascii=False, indent=2)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
