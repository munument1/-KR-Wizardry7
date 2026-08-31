#!/usr/bin/env python3
"""Create a verified Wizardry 7 DOS EXE copy with one INT 3 breakpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--image-offset", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--expect", type=lambda value: int(value, 0))
    parser.add_argument(
        "--expect-hex", help="space-separated expected bytes, e.g. '55 8B'"
    )
    parser.add_argument(
        "--patch-hex", default="CC", help="space-separated replacement bytes"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.exe.read_bytes()
    if source[:2] != b"MZ":
        raise ValueError("input is not an MZ executable")
    header_size = struct.unpack_from("<H", source, 8)[0] * 16
    file_offset = header_size + args.image_offset
    if file_offset >= len(source):
        raise ValueError(f"image offset 0x{args.image_offset:X} is outside the EXE")
    if args.expect_hex:
        expected = bytes.fromhex(args.expect_hex)
    elif args.expect is not None:
        expected = bytes((args.expect,))
    else:
        raise ValueError("supply --expect or --expect-hex")
    replacement = bytes.fromhex(args.patch_hex)
    if len(expected) != len(replacement):
        raise ValueError("expected and replacement byte counts differ")
    actual = source[file_offset:file_offset + len(expected)]
    if actual != expected:
        raise ValueError(
            f"expected {expected.hex(' ').upper()} at file offset 0x{file_offset:X}, "
            f"found {actual.hex(' ').upper()}"
        )

    patched = bytearray(source)
    patched[file_offset:file_offset + len(replacement)] = replacement
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    manifest = {
        "source": str(args.exe),
        "source_sha256": sha256(source),
        "output": str(args.output),
        "output_sha256": sha256(patched),
        "mz_header_size": header_size,
        "image_offset": args.image_offset,
        "file_offset": file_offset,
        "original_bytes": actual.hex(" ").upper(),
        "patched_bytes": replacement.hex(" ").upper(),
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
