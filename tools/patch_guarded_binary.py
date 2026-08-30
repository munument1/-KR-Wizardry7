#!/usr/bin/env python3
"""Apply one same-size, guarded byte patch to a binary file copy."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--offset", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--expect", required=True, help="expected hexadecimal bytes")
    parser.add_argument("--replace", required=True, help="replacement hexadecimal bytes")
    args = parser.parse_args()

    expected = bytes.fromhex(args.expect)
    replacement = bytes.fromhex(args.replace)
    if len(expected) != len(replacement):
        raise ValueError("expected and replacement byte counts differ")
    data = bytearray(args.source.read_bytes())
    actual = bytes(data[args.offset : args.offset + len(expected)])
    if actual != expected:
        raise ValueError(
            f"guard failed at 0x{args.offset:X}: expected {expected.hex(' ')}, "
            f"found {actual.hex(' ')}"
        )
    data[args.offset : args.offset + len(replacement)] = replacement
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"patched {args.output} at 0x{args.offset:X}: {expected.hex(' ')} -> {replacement.hex(' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
