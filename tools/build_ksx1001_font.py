#!/usr/bin/env python3
"""Build Wizardry 7's 8x8 KS X 1001 Hangul font payload from a BDF font.

The game runtime addresses Hangul glyphs by the EUC-KR/KS X 1001 Wansung
order (B0A1..C8FE), 2,350 syllables total. Each output glyph is eight bytes,
one MSB-first bitmap row per byte.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


GLYPH_COUNT = 2350
GLYPH_BYTES = 8
OUTPUT_SIZE = GLYPH_COUNT * GLYPH_BYTES


@dataclass(frozen=True)
class BdfGlyph:
    width: int
    height: int
    x_offset: int
    y_offset: int
    rows: tuple[int, ...]
    row_bits: int


def parse_bdf(path: Path) -> tuple[dict[int, BdfGlyph], int, int]:
    glyphs: dict[int, BdfGlyph] = {}
    font_ascent: int | None = None
    font_descent: int | None = None

    encoding: int | None = None
    bbx: tuple[int, int, int, int] | None = None
    bitmap_rows: list[str] | None = None

    for raw_line in path.read_text(encoding="ascii", errors="strict").splitlines():
        line = raw_line.strip()
        if line.startswith("FONT_ASCENT "):
            font_ascent = int(line.split()[1])
        elif line.startswith("FONT_DESCENT "):
            font_descent = int(line.split()[1])
        elif line == "STARTCHAR" or line.startswith("STARTCHAR "):
            encoding = None
            bbx = None
            bitmap_rows = None
        elif line.startswith("ENCODING "):
            encoding = int(line.split()[1])
        elif line.startswith("BBX "):
            _, w, h, x, y = line.split()
            bbx = (int(w), int(h), int(x), int(y))
        elif line == "BITMAP":
            bitmap_rows = []
        elif line == "ENDCHAR":
            if encoding is not None and encoding >= 0 and bbx is not None and bitmap_rows is not None:
                width, height, x_offset, y_offset = bbx
                if len(bitmap_rows) != height:
                    raise ValueError(
                        f"U+{encoding:04X}: expected {height} bitmap rows, got {len(bitmap_rows)}"
                    )
                row_bits = ((width + 7) // 8) * 8
                glyphs[encoding] = BdfGlyph(
                    width=width,
                    height=height,
                    x_offset=x_offset,
                    y_offset=y_offset,
                    rows=tuple(int(row, 16) for row in bitmap_rows),
                    row_bits=row_bits,
                )
            bitmap_rows = None
        elif bitmap_rows is not None:
            bitmap_rows.append(line)

    if font_ascent is None or font_descent is None:
        raise ValueError("BDF is missing FONT_ASCENT/FONT_DESCENT")
    if font_ascent + font_descent != 8:
        raise ValueError(
            f"Expected an 8-pixel cell, got ascent={font_ascent} descent={font_descent}"
        )
    return glyphs, font_ascent, font_descent


def render_8x8(glyph: BdfGlyph, ascent: int, descent: int) -> bytes:
    if glyph.width > 8:
        raise ValueError(f"Glyph width {glyph.width} exceeds 8 pixels")

    target_top_y = ascent - 1
    target_bottom_y = -descent
    out = [0] * 8

    # BDF BITMAP rows run top-to-bottom. BBX y_offset is the lower edge relative
    # to the baseline. Convert each set source pixel to the game's 8x8 cell.
    for src_row_index, row_value in enumerate(glyph.rows):
        y = glyph.y_offset + glyph.height - 1 - src_row_index
        if y < target_bottom_y or y > target_top_y:
            continue
        dst_row = target_top_y - y

        for src_x in range(glyph.width):
            bit = 1 << (glyph.row_bits - 1 - src_x)
            if row_value & bit == 0:
                continue
            x = glyph.x_offset + src_x
            if 0 <= x < 8:
                out[dst_row] |= 0x80 >> x

    return bytes(out)


def iter_wansung_syllables():
    count = 0
    for lead in range(0xB0, 0xC9):
        for trail in range(0xA1, 0xFF):
            raw = bytes((lead, trail))
            text = raw.decode("euc_kr")
            if len(text) != 1:
                raise ValueError(f"Unexpected EUC-KR mapping for {raw.hex().upper()}: {text!r}")
            yield lead, trail, text
            count += 1
    if count != GLYPH_COUNT:
        raise AssertionError(f"Internal Wansung count mismatch: {count}")


def build_font(input_bdf: Path, output_bin: Path) -> None:
    glyphs, ascent, descent = parse_bdf(input_bdf)
    payload = bytearray()
    missing: list[str] = []
    blank: list[str] = []

    for lead, trail, char in iter_wansung_syllables():
        glyph = glyphs.get(ord(char))
        if glyph is None:
            missing.append(f"{lead:02X}{trail:02X}=U+{ord(char):04X} {char}")
            continue
        bitmap = render_8x8(glyph, ascent, descent)
        if not any(bitmap):
            blank.append(f"{lead:02X}{trail:02X}=U+{ord(char):04X} {char}")
        payload.extend(bitmap)

    if missing:
        preview = ", ".join(missing[:12])
        raise ValueError(f"BDF is missing {len(missing)} Wansung Hangul glyph(s): {preview}")
    if blank:
        preview = ", ".join(blank[:12])
        raise ValueError(f"BDF produced {len(blank)} blank Wansung Hangul glyph(s): {preview}")
    if len(payload) != OUTPUT_SIZE:
        raise AssertionError(f"Expected {OUTPUT_SIZE} bytes, got {len(payload)}")

    output_bin.parent.mkdir(parents=True, exist_ok=True)
    output_bin.write_bytes(payload)
    print(
        f"Built {output_bin}: glyphs={GLYPH_COUNT} bytes={len(payload)} "
        f"cell=8x8 ascent={ascent} descent={descent}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_bdf", type=Path)
    parser.add_argument("output_bin", type=Path)
    args = parser.parse_args()
    build_font(args.input_bdf, args.output_bin)


if __name__ == "__main__":
    main()
