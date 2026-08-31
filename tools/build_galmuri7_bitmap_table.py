#!/usr/bin/env python3
"""Build a compact 7x7 Hangul bitmap table from Galmuri7.kbitx.

The output is indexed directly by Unicode Hangul syllable code point:

    offset = (codepoint - 0xAC00) * 7

Each row byte uses bits 7..1 for the seven pixels (bit 7 is the leftmost
pixel); bit 0 remains clear. Unsupported syllables are seven zero bytes.

Galmuri is distributed under the SIL Open Font License 1.1. This tool does
not vendor the upstream font; pass an official Galmuri7.kbitx source file.
"""

from __future__ import annotations

import argparse
import base64
import json
import xml.etree.ElementTree as ET
from pathlib import Path


HANGUL_FIRST = 0xAC00
HANGUL_LAST = 0xD7A3
GLYPH_HEIGHT = 7
GLYPH_WIDTH = 7


def decode_no_padding(value: str) -> bytes:
    value += "=" * ((4 - len(value) % 4) % 4)
    return base64.b64decode(value)


def read_uleb128(data: bytes, cursor: int) -> tuple[int, int]:
    value = 0
    shift = 0
    for _ in range(5):
        current = data[cursor]
        cursor += 1
        value |= (current & 0x7F) << shift
        if not current & 0x80:
            return value, cursor
        shift += 7
    raise ValueError("ULEB128 value is too long")


def decode_bitmap(encoded: str) -> list[list[int]]:
    data = decode_no_padding(encoded)
    cursor = 0
    height, cursor = read_uleb128(data, cursor)
    width, cursor = read_uleb128(data, cursor)
    repeat_count = 0
    repeat_color: int | None = None
    bitmap: list[list[int]] = []

    for _ in range(height):
        row: list[int] = []
        for _ in range(width):
            if repeat_count <= 0:
                control = data[cursor]
                cursor += 1
                repeat_count = control & 0x1F
                if control & 0x20:
                    repeat_count <<= 5
                color_type = control & 0xC0
                if color_type == 0x00:
                    repeat_color = 0x00
                elif color_type == 0x40:
                    repeat_color = 0xFF
                elif color_type == 0x80:
                    repeat_color = data[cursor]
                    cursor += 1
                else:
                    repeat_color = None
            repeat_count -= 1
            if repeat_color is None:
                color = data[cursor]
                cursor += 1
            else:
                color = repeat_color
            row.append(color)
        bitmap.append(row)
    return bitmap


def to_7x7_rows(bitmap: list[list[int]]) -> bytes:
    """Convert a Galmuri7 monochrome bitmap to seven 1bpp row bytes."""
    if len(bitmap) > GLYPH_HEIGHT:
        raise ValueError(f"bitmap height {len(bitmap)} exceeds {GLYPH_HEIGHT}")
    if any(len(row) > GLYPH_WIDTH for row in bitmap):
        raise ValueError("bitmap width exceeds seven pixels")

    output = bytearray(GLYPH_HEIGHT)
    # Galmuri7 Hangul uses a seven-pixel cell. Keep it top-aligned so the
    # Korean glyph baseline is one pixel above the converted 6x6 Latin font.
    for y, source_row in enumerate(bitmap):
        row_value = 0
        for x, color in enumerate(source_row):
            if color >= 0x80:
                row_value |= 1 << (7 - x)
        output[y] = row_value
    return bytes(output)


def build_table(source: Path) -> tuple[bytes, dict]:
    table = bytearray((HANGUL_LAST - HANGUL_FIRST + 1) * GLYPH_HEIGHT)
    supported = 0
    multiplication_rows: bytes | None = None

    for _event, element in ET.iterparse(source, events=("end",)):
        if element.tag != "g":
            continue
        codepoint_text = element.get("u")
        data_text = element.get("d")
        if codepoint_text is None or data_text is None:
            element.clear()
            continue
        codepoint = int(codepoint_text)
        if HANGUL_FIRST <= codepoint <= HANGUL_LAST or codepoint == 0x00D7:
            bitmap = decode_bitmap(data_text)
            rows = to_7x7_rows(bitmap)
            if HANGUL_FIRST <= codepoint <= HANGUL_LAST:
                offset = (codepoint - HANGUL_FIRST) * GLYPH_HEIGHT
                table[offset : offset + GLYPH_HEIGHT] = rows
                supported += 1
            else:
                multiplication_rows = rows
        element.clear()

    metadata = {
        "source": source.name,
        "hangul_first": f"U+{HANGUL_FIRST:04X}",
        "hangul_last": f"U+{HANGUL_LAST:04X}",
        "glyph_width": GLYPH_WIDTH,
        "glyph_height": GLYPH_HEIGHT,
        "hangul_supported": supported,
        "table_bytes": len(table),
        "multiplication_sign_rows_hex": (
            multiplication_rows.hex().upper() if multiplication_rows is not None else None
        ),
    }
    return bytes(table), metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()

    table, metadata = build_table(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(table)
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
