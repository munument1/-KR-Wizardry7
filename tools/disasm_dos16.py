"""Disassemble a raw 16-bit DOS code range with Capstone."""

from __future__ import annotations

import argparse
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_16, Cs


def number(value: str) -> int:
    return int(value, 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--offset", type=number, required=True)
    parser.add_argument("--length", type=number, required=True)
    parser.add_argument("--origin", type=number)
    args = parser.parse_args()

    data = args.path.read_bytes()[args.offset : args.offset + args.length]
    origin = args.offset if args.origin is None else args.origin
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    for instruction in decoder.disasm(data, origin):
        encoded = instruction.bytes.hex(" ").ljust(23)
        print(
            f"{instruction.address:04X}  {encoded}  "
            f"{instruction.mnemonic:<7} {instruction.op_str}"
        )


if __name__ == "__main__":
    main()
