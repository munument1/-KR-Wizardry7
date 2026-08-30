#!/usr/bin/env python3
"""Render raw Wizardry VII 320x200 indexed VGA screens as PNG previews."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


WIDTH = 320
HEIGHT = 200


def render(screen_path: Path, palette_path: Path, output_path: Path) -> None:
    pixels = screen_path.read_bytes()
    if len(pixels) != WIDTH * HEIGHT:
        raise ValueError(f"{screen_path} is {len(pixels)} bytes, expected {WIDTH * HEIGHT}")
    palette_6bit = palette_path.read_bytes()
    if len(palette_6bit) != 256 * 3 or max(palette_6bit) > 63:
        raise ValueError(f"{palette_path} is not a 256-color 6-bit VGA palette")
    palette_8bit = bytes(round(value * 255 / 63) for value in palette_6bit)
    image = Image.frombytes("P", (WIDTH, HEIGHT), pixels)
    image.putpalette(palette_8bit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("screens", nargs="+")
    args = parser.parse_args()
    palette = args.game_dir / "PALETTE.DEF"
    for name in args.screens:
        source = args.game_dir / name
        target = args.output_dir / f"{source.stem}.png"
        render(source, palette, target)
        print(target.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
