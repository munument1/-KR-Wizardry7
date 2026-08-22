#!/usr/bin/env python3
"""Render sample text from a fixed-size 1bpp Hangul tile font."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--glyph-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--text", default="생성 검토 삭제 이름 바꾸기 초상화 나가기")
    parser.add_argument("--width", type=int, default=8)
    parser.add_argument("--height", type=int, default=8)
    parser.add_argument("--scale", type=int, default=8)
    args = parser.parse_args()

    glyph_map = json.loads(args.glyph_map.read_text(encoding="utf-8"))
    data = args.bin.read_bytes()
    row_bytes = (args.width + 7) // 8
    glyph_bytes = row_bytes * args.height
    cell_width = args.width + 1
    canvas = Image.new("RGB", (len(args.text) * cell_width + 1, args.height + 2), "#101522")
    pixels = canvas.load()

    for position, character in enumerate(args.text):
        if character == " ":
            continue
        index = glyph_map.get(character)
        if index is None:
            continue
        base = index * glyph_bytes
        for y in range(args.height):
            for x in range(args.width):
                byte = data[base + y * row_bytes + x // 8]
                if byte & (0x80 >> (x & 7)):
                    pixels[position * cell_width + x + 1, y + 1] = (245, 245, 235)

    canvas = canvas.resize(
        (canvas.width * args.scale, canvas.height * args.scale),
        Image.Resampling.NEAREST,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
