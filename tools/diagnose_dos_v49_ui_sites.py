#!/usr/bin/env python3
"""Disassemble remaining DOS Korean UI width candidates in gameplay overlays.

This is deliberately diagnostic-only.  It does not patch binaries.  The goal
is to separate visual pixel-width math from logical byte/cell counts before a
v0.49 fix is written.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_16


OVERLAY_ORIGIN = 0x5047
MUL6 = bytes.fromhex("B9 06 00 F7 E9")  # mov cx,6 / imul cx

# Gameplay overlays implicated by the reports: maze/doors, treasure/chests,
# and the shared base overlay used by event/UI paths.
FOCUS = ("VMAZE.OVR", "VTREA.OVR", "VBASE.OVR")


def decode_window(data: bytes, center: int, before: int = 96, after: int = 112) -> list[str]:
    start = max(0, center - before)
    end = min(len(data), center + after)
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    decoder.detail = False
    return [
        f"{ins.address:04X}  {ins.mnemonic:<7} {ins.op_str}".rstrip()
        for ins in decoder.disasm(data[start:end], OVERLAY_ORIGIN + start)
    ]


def call_target(data: bytes, offset: int) -> int | None:
    if offset + 3 > len(data) or data[offset] != 0xE8:
        return None
    displacement = int.from_bytes(data[offset + 1:offset + 3], "little", signed=True)
    return (OVERLAY_ORIGIN + offset + 3 + displacement) & 0xFFFF


def nearby_calls(data: bytes, center: int, radius: int = 96) -> list[tuple[int, int]]:
    start = max(0, center - radius)
    end = min(len(data) - 2, center + radius)
    calls: list[tuple[int, int]] = []
    for offset in range(start, end):
        target = call_target(data, offset)
        if target is not None:
            calls.append((offset, target))
    return calls


def all_mul6(data: bytes) -> list[int]:
    out: list[int] = []
    cursor = 0
    while True:
        offset = data.find(MUL6, cursor)
        if offset < 0:
            return out
        out.append(offset)
        cursor = offset + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dsavant", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    blocks: list[str] = []
    for name in FOCUS:
        path = args.dsavant / name
        data = path.read_bytes()
        offsets = all_mul6(data)
        blocks.append(f"## {name}: {len(offsets)} raw AX*6 sites")
        for offset in offsets:
            runtime = OVERLAY_ORIGIN + offset
            blocks.append(f"\n### file 0x{offset:04X} / runtime 0x{runtime:04X}")
            calls = nearby_calls(data, offset)
            if calls:
                blocks.append("nearby calls: " + ", ".join(
                    f"0x{call_off:04X}->0x{target:04X}" for call_off, target in calls
                ))
            else:
                blocks.append("nearby calls: none")
            blocks.extend(decode_window(data, offset))
        blocks.append("")

    rendered = "\n".join(blocks).rstrip() + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
