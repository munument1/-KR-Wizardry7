#!/usr/bin/env python3
"""List direct x86 call/jump references to PE virtual addresses."""

from __future__ import annotations

import argparse
from pathlib import Path

import capstone
import pefile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("targets", nargs="+", type=lambda value: int(value, 0))
    args = parser.parse_args()

    pe = pefile.PE(str(args.exe), fast_load=True)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    targets = set(args.targets)

    file_bytes = args.exe.read_bytes()
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:  # IMAGE_SCN_MEM_EXECUTE
            continue
        start = pe.OPTIONAL_HEADER.ImageBase + section.VirtualAddress
        offset = section.PointerToRawData
        code = file_bytes[offset : offset + section.SizeOfRawData]
        for instruction in decoder.disasm(code, start):
            if instruction.mnemonic not in {"call", "jmp"}:
                continue
            try:
                target = int(instruction.op_str, 0)
            except ValueError:
                continue
            if target in targets:
                print(
                    f"{instruction.address:08X}  {instruction.mnemonic:<4} "
                    f"{target:08X}"
                )


if __name__ == "__main__":
    main()
