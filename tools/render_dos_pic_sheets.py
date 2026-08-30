#!/usr/bin/env python3
"""Render Wizardry VII PIC animation frames and a labeled contact sheet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoder-root", type=Path, required=True)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("pics", nargs="+")
    args = parser.parse_args()
    sys.path.insert(0, str(args.decoder_root))
    from bane.data.pic_decoder import decode_pic_frames

    for name in args.pics:
        source = args.game_dir / name
        frames = decode_pic_frames(source.read_bytes())
        if not frames:
            raise ValueError(f"no frames decoded from {source}")
        frame_images: list[Image.Image] = []
        frame_dir = args.output_dir / source.stem
        frame_dir.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(frames):
            image = Image.frombytes(
                "RGBA",
                (frame.width, frame.height),
                frame.to_rgba_bytes(transparent_index=15),
            )
            image.save(frame_dir / f"frame_{index:02d}.png")
            frame_images.append(image)

        cell_width = max(image.width for image in frame_images) + 12
        cell_height = max(image.height for image in frame_images) + 28
        columns = 5
        rows = (len(frame_images) + columns - 1) // columns
        sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), (32, 32, 32))
        draw = ImageDraw.Draw(sheet)
        for index, image in enumerate(frame_images):
            x = (index % columns) * cell_width + 6
            y = (index // columns) * cell_height + 20
            checker = Image.new("RGB", image.size, (0, 96, 96))
            checker.paste(image, mask=image.getchannel("A"))
            sheet.paste(checker, (x, y))
            draw.text((x, y - 16), f"{index}: {image.width}x{image.height}", fill=(255, 255, 255))
        sheet_path = args.output_dir / f"{source.stem}_sheet.png"
        sheet.save(sheet_path)
        print(f"{source.name}: {len(frames)} frames -> {sheet_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
