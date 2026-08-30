#!/usr/bin/env python3
"""Render Wizardry VII tiled PIC frames with palette index 255 transparent."""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw


def load_palette(path: Path) -> list[int]:
    raw = path.read_bytes()
    if len(raw) != 768 or max(raw) > 63:
        raise ValueError(f"invalid 6-bit VGA palette: {path}")
    return [round(value * 255 / 63) for value in raw]


def frame_starts(data: bytes) -> list[int]:
    if len(data) < 10 or struct.unpack_from("<I", data, 0)[0] != len(data) - 4:
        raise ValueError("not a Wizardry VII PIC container")
    count = struct.unpack_from("<H", data, 4)[0]
    starts = []
    for index in range(count):
        offset, segment = struct.unpack_from("<HH", data, 6 + index * 4)
        starts.append(4 + segment * 16 + offset)
    if starts != sorted(starts) or starts[0] != 6 + count * 4:
        raise ValueError("invalid PIC frame descriptor table")
    return starts


def decode_frame(data: bytes, start: int, palette: list[int]) -> Image.Image:
    pixel_offset, width_tiles, height_tiles = struct.unpack_from("<HBB", data, start)
    width, height = width_tiles * 8, height_tiles * 8
    mask_size = (width_tiles * height_tiles + 7) // 8
    mask = data[start + 4 : start + 4 + mask_size]
    cursor = start + pixel_offset
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = out.load()
    for tile_index in range(width_tiles * height_tiles):
        if not (mask[tile_index // 8] & (1 << (tile_index & 7))):
            continue
        if cursor + 64 > len(data):
            raise ValueError("truncated PIC tile payload")
        tile_x = (tile_index % width_tiles) * 8
        tile_y = (tile_index // width_tiles) * 8
        tile = data[cursor : cursor + 64]
        cursor += 64
        for yy in range(8):
            for xx in range(8):
                index = tile[yy * 8 + xx]
                if index != 255:
                    base = index * 3
                    pixels[tile_x + xx, tile_y + yy] = (
                        palette[base], palette[base + 1], palette[base + 2], 255
                    )
    return out


def make_sheet(frames: list[Image.Image], columns: int = 6) -> Image.Image:
    cell_w = max(image.width for image in frames) + 12
    cell_h = max(image.height for image in frames) + 24
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows), "#202020")
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(frames):
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        checker = Image.new("RGB", frame.size, "#101010")
        sheet.paste(checker, (x + 6, y + 18))
        sheet.paste(frame, (x + 6, y + 18), frame)
        draw.text((x + 6, y + 3), str(index + 1), fill="white")
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pic", type=Path)
    parser.add_argument("--palette", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.pic.read_bytes()
    palette = load_palette(args.palette)
    frames = [decode_frame(data, start, palette) for start in frame_starts(data)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    make_sheet(frames).save(args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
