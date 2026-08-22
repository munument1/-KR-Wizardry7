#!/usr/bin/env python3
"""Disassemble a PE32 virtual-address range with Capstone."""

from __future__ import annotations

import argparse
from pathlib import Path

import capstone
import pefile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("address", type=lambda value: int(value, 0))
    parser.add_argument("size", type=lambda value: int(value, 0))
    args = parser.parse_args()

    pe = pefile.PE(str(args.exe), fast_load=True)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    rva = args.address - image_base
    file_offset = pe.get_offset_from_rva(rva)

    with args.exe.open("rb") as stream:
        stream.seek(file_offset)
        code = stream.read(args.size)

    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    decoder.detail = False
    for instruction in decoder.disasm(code, args.address):
        raw = instruction.bytes.hex(" ").ljust(23)
        print(
            f"{instruction.address:08X}  {raw}  "
            f"{instruction.mnemonic:<8} {instruction.op_str}"
        )


if __name__ == "__main__":
    main()
