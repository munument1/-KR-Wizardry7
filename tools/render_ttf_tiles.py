#!/usr/bin/env python3
"""Rasterize mapped TTF glyphs into fixed-size 1bpp tiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ttf", type=Path, required=True)
    parser.add_argument("--glyph-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tile-width", type=int, default=8)
    parser.add_argument("--tile-height", type=int, default=8)
    parser.add_argument("--font-size", type=int, default=8)
    parser.add_argument("--offset-x", type=int, default=0)
    parser.add_argument("--offset-y", type=int, default=0)
    parser.add_argument("--threshold", type=int, default=128)
    args = parser.parse_args()

    glyph_map = json.loads(args.glyph_map.read_text(encoding="utf-8"))
    glyph_count = max(glyph_map.values()) + 1
    by_index = {index: character for character, index in glyph_map.items()}
    font = ImageFont.truetype(str(args.ttf), args.font_size)
    row_bytes = (args.tile_width + 7) // 8
    result = bytearray(glyph_count * args.tile_height * row_bytes)

    for index in range(glyph_count):
        character = by_index[index]
        canvas = Image.new("L", (args.tile_width, args.tile_height), 0)
        draw = ImageDraw.Draw(canvas)
        bbox = draw.textbbox((0, 0), character, font=font)
        glyph_width = bbox[2] - bbox[0]
        glyph_height = bbox[3] - bbox[1]
        x = (args.tile_width - glyph_width) // 2 - bbox[0] + args.offset_x
        y = (args.tile_height - glyph_height) // 2 - bbox[1] + args.offset_y
        draw.text((x, y), character, font=font, fill=255)
        pixels = canvas.load()
        base = index * args.tile_height * row_bytes
        for tile_y in range(args.tile_height):
            for tile_x in range(args.tile_width):
                if pixels[tile_x, tile_y] >= args.threshold:
                    result[base + tile_y * row_bytes + tile_x // 8] |= 0x80 >> (tile_x & 7)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    print(args.output)


if __name__ == "__main__":
    main()
