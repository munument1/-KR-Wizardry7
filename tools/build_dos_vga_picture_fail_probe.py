#!/usr/bin/env python3
"""Build a one-shot VGA.DRV diagnostic for the v37 save failure.

The stock VGA driver aborts at runtime 0x2357 when its picture-memory cursor
would reach/exceed 0x4180. At that point the loader still has the failed
picture slot, the 32-bit payload length read from the PIC header, and the
post-allocation pool cursor in memory.

This probe changes only the fatal path. Instead of the stock message it prints

    PICFAIL S=ssss SZ=zzzzzzzz P=pppp

in hexadecimal and exits exactly as the stock fatal path does. S is the
picture slot, SZ is the first little-endian dword in the PIC file (the payload
length; file size is SZ+4), and P is the post-allocation paragraph cursor.

Purchased binaries are never written to the repository. Supply a local stock
GOG VGA.DRV and install the generated file only for the diagnostic run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


STOCK_VGA_SHA256 = "f064349ce5dc694b26ed58615262d1bad893e59971bf259c0a74bdea9ee27a70"
STOCK_VGA_SIZE = 18616
COM_ORIGIN = 0x100

# Stock runtime 0x2357: E9 94 00 -> runtime 0x23EE (normal fatal printer).
FATAL_BRANCH_RUNTIME = 0x2357
FATAL_BRANCH_FILE = FATAL_BRANCH_RUNTIME - COM_ORIGIN
FATAL_BRANCH_EXPECTED = bytes.fromhex("E9 94 00")
FATAL_BRANCH_PATCHED = bytes.fromhex("E9 52 00")  # -> runtime 0x23AC

# Runtime 0x23AC..0x2427 is the two stock fatal printers + their strings.
# The replacement is assembled at VMA 0x23AC. It is 123 bytes, uses only
# 8086-compatible instructions, and leaves one byte for NOP padding.
DIAG_RUNTIME = 0x23AC
DIAG_FILE = DIAG_RUNTIME - COM_ORIGIN
DIAG_REGION_SIZE = 0x2428 - DIAG_RUNTIME
DIAG_BYTES = bytes.fromhex(
    "8C C8 8E D8 BF 0D 24 31 C0 8A 46 0E E8 25 00 BF "
    "15 24 8B 46 FA E8 1C 00 8B 46 FC E8 16 00 BF 20 "
    "24 2E A1 AC 0C E8 0C 00 BA 01 24 B4 09 CD 21 B8 "
    "01 4C CD 21 B9 04 00 D1 C0 D1 C0 D1 C0 D1 C0 88 "
    "C2 80 E2 0F 80 FA 09 76 03 80 C2 07 80 C2 30 88 "
    "15 47 E2 E3 C3 0D 0A 50 49 43 46 41 49 4C 20 53 "
    "3D 30 30 30 30 20 53 5A 3D 30 30 30 30 30 30 30 "
    "30 20 50 3D 30 30 30 30 0D 0A 24"
)

STOCK_DIAG_REGION_PREFIX = bytes.fromhex(
    "8B 46 0E BB 0A 00 F7 F3 2E 08 06 DE 23 2E 08 16 DF 23 "
    "8C C8 8E D8 BA CE 23 B4 09 CD 21 B8 01 4C CD 21"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_vga(data: bytes) -> bytes:
    if len(data) != STOCK_VGA_SIZE:
        raise ValueError(f"unexpected VGA.DRV size {len(data)}")
    if data[FATAL_BRANCH_FILE : FATAL_BRANCH_FILE + 3] != FATAL_BRANCH_EXPECTED:
        raise ValueError("VGA.DRV fatal branch bytes do not match the stock driver")
    if data[DIAG_FILE : DIAG_FILE + len(STOCK_DIAG_REGION_PREFIX)] != STOCK_DIAG_REGION_PREFIX:
        raise ValueError("VGA.DRV fatal diagnostic region does not match the stock driver")
    if len(DIAG_BYTES) > DIAG_REGION_SIZE:
        raise AssertionError("diagnostic code exceeds the stock fatal region")

    out = bytearray(data)
    out[FATAL_BRANCH_FILE : FATAL_BRANCH_FILE + 3] = FATAL_BRANCH_PATCHED
    out[DIAG_FILE : DIAG_FILE + DIAG_REGION_SIZE] = DIAG_BYTES + b"\x90" * (
        DIAG_REGION_SIZE - len(DIAG_BYTES)
    )
    if len(out) != len(data):
        raise AssertionError("probe changed VGA.DRV size")
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="stock local VGA.DRV")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.read_bytes()
    actual_hash = sha256(source)
    if actual_hash != STOCK_VGA_SHA256:
        raise ValueError(
            f"stock VGA.DRV hash mismatch: expected {STOCK_VGA_SHA256}, found {actual_hash}"
        )
    patched = patch_vga(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.write_bytes(patched)

    print(
        json.dumps(
            {
                "format": "Wizardry VII DOS VGA picture-failure probe",
                "input_sha256": actual_hash,
                "output": str(args.output.resolve()),
                "output_sha256": sha256(patched),
                "size": len(patched),
                "fatal_branch_runtime": "0x2357",
                "diagnostic_runtime": "0x23AC",
                "expected_output": "PICFAIL S=ssss SZ=zzzzzzzz P=pppp",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
