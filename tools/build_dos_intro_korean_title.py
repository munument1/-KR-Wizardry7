#!/usr/bin/env python3
"""Build a palette-safe Korean Wizardry VII title screen and blank PIC frames."""

from __future__ import annotations

import argparse
import shutil
import struct
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH = 320
HEIGHT = 200
LOGO_WIDTH = 216
LOGO_HEIGHT = 88


def load_palette(path: Path) -> list[tuple[int, int, int]]:
    raw = path.read_bytes()
    if len(raw) != 768 or max(raw) > 63:
        raise ValueError(f"invalid 6-bit VGA palette: {path}")
    return [tuple(round(raw[i + j] * 255 / 63) for j in range(3)) for i in range(0, 768, 3)]


def nearest_index(rgb: tuple[int, int, int], palette: list[tuple[int, int, int]]) -> int:
    return min(
        range(256),
        key=lambda i: sum((palette[i][c] - rgb[c]) ** 2 for c in range(3)),
    )


def fit_font(font_path: Path, text: str, max_width: int, start_size: int) -> ImageFont.FreeTypeFont:
    for size in range(start_size, 7, -1):
        font = ImageFont.truetype(str(font_path), size=size)
        box = font.getbbox(text, stroke_width=0)
        if box[2] - box[0] <= max_width:
            return font
    raise ValueError(f"cannot fit title text: {text}")


def centered_mask(text: str, font: ImageFont.FreeTypeFont, y: int, stroke: int = 0) -> Image.Image:
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(mask)
    box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    x = (WIDTH - (box[2] - box[0])) // 2 - box[0]
    draw.text((x, y - box[1]), text, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    return mask


def paste_masked_index(
    pixels: bytearray,
    mask: Image.Image,
    color_index: int,
    *,
    offset: tuple[int, int] = (0, 0),
) -> None:
    if offset != (0, 0):
        shifted = Image.new("L", mask.size, 0)
        shifted.paste(mask, offset)
        mask = shifted
    data = mask.tobytes()
    for i, alpha in enumerate(data):
        if alpha >= 128:
            pixels[i] = color_index


def add_metal_text(
    pixels: bytearray,
    palette: list[tuple[int, int, int]],
    text: str,
    font: ImageFont.FreeTypeFont,
    y: int,
) -> None:
    core = centered_mask(text, font, y)
    outline = core.filter(ImageFilter.MaxFilter(5))
    thin_outline = core.filter(ImageFilter.MaxFilter(3))

    dark = nearest_index((16, 16, 24), palette)
    mid_dark = nearest_index((58, 58, 70), palette)
    edge = nearest_index((118, 118, 132), palette)
    bright = nearest_index((236, 236, 244), palette)
    mid = nearest_index((166, 166, 178), palette)
    low = nearest_index((92, 92, 106), palette)

    # Seven-pixel down-left extrusion, matching the original DOS logo silhouette.
    for depth in range(7, 0, -1):
        paste_masked_index(pixels, outline, dark if depth > 3 else mid_dark, offset=(-depth, depth))
    paste_masked_index(pixels, outline, dark)
    paste_masked_index(pixels, thin_outline, edge)

    mask_data = core.tobytes()
    bbox = core.getbbox()
    if not bbox:
        return
    top, bottom = bbox[1], bbox[3]
    span = max(1, bottom - top)
    for yy in range(top, bottom):
        rel = (yy - top) / span
        if rel < 0.18:
            idx = bright
        elif rel < 0.48:
            idx = mid
        elif rel < 0.72:
            idx = bright
        else:
            idx = low
        row = yy * WIDTH
        for xx in range(WIDTH):
            if mask_data[row + xx] >= 128:
                pixels[row + xx] = idx


def build_screen(game_dir: Path, output: Path, font_path: Path) -> None:
    source = game_dir / "TIT2SCRN.VGA"
    pixels = bytearray(source.read_bytes())
    if len(pixels) != WIDTH * HEIGHT:
        raise ValueError(f"unexpected screen size: {source}")
    palette = load_palette(game_dir / "PALETTE.DEF")

    first = fit_font(font_path, "위저드리 7", 250, 34)
    second = fit_font(font_path, "다크 서번트", 250, 31)
    add_metal_text(pixels, palette, "위저드리 7", first, 7)
    add_metal_text(pixels, palette, "다크 서번트", second, 48)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(pixels)


def sprite_mask(text: str, font: ImageFont.FreeTypeFont, y: int) -> Image.Image:
    mask = Image.new("L", (LOGO_WIDTH, LOGO_HEIGHT), 0)
    draw = ImageDraw.Draw(mask)
    box = draw.textbbox((0, 0), text, font=font)
    x = (LOGO_WIDTH - (box[2] - box[0])) // 2 - box[0]
    draw.text((x, y - box[1]), text, font=font, fill=255)
    return mask


def paint_sprite_mask(
    pixels: bytearray,
    mask: Image.Image,
    color_index: int,
    *,
    offset: tuple[int, int] = (0, 0),
) -> None:
    if offset != (0, 0):
        shifted = Image.new("L", mask.size, 0)
        shifted.paste(mask, offset)
        mask = shifted
    for index, alpha in enumerate(mask.tobytes()):
        if alpha >= 128:
            pixels[index] = color_index


def add_sprite_metal_text(
    pixels: bytearray,
    palette: list[tuple[int, int, int]],
    text: str,
    font: ImageFont.FreeTypeFont,
    y: int,
) -> None:
    core = sprite_mask(text, font, y)
    outline = core.filter(ImageFilter.MaxFilter(5))
    thin_outline = core.filter(ImageFilter.MaxFilter(3))
    dark = nearest_index((12, 12, 20), palette)
    mid_dark = nearest_index((48, 48, 62), palette)
    edge = nearest_index((112, 112, 128), palette)
    bright = nearest_index((244, 244, 250), palette)
    mid = nearest_index((158, 158, 174), palette)
    low = nearest_index((78, 78, 94), palette)

    for depth in range(6, 0, -1):
        paint_sprite_mask(
            pixels,
            outline,
            dark if depth > 3 else mid_dark,
            offset=(-depth, depth),
        )
    paint_sprite_mask(pixels, outline, dark)
    paint_sprite_mask(pixels, thin_outline, edge)

    bbox = core.getbbox()
    if not bbox:
        return
    mask_data = core.tobytes()
    top, bottom = bbox[1], bbox[3]
    span = max(1, bottom - top)
    for yy in range(top, bottom):
        rel = (yy - top) / span
        if rel < 0.18:
            color = bright
        elif rel < 0.48:
            color = mid
        elif rel < 0.70:
            color = bright
        else:
            color = low
        row = yy * LOGO_WIDTH
        for xx in range(LOGO_WIDTH):
            if mask_data[row + xx] >= 128:
                pixels[row + xx] = color


def encode_single_pic_frame(pixels: bytes, width: int, height: int) -> bytes:
    if width % 8 or height % 8 or len(pixels) != width * height:
        raise ValueError("PIC frame must use complete 8x8 tiles")
    width_tiles, height_tiles = width // 8, height // 8
    tile_count = width_tiles * height_tiles
    mask = bytearray((tile_count + 7) // 8)
    tile_payload = bytearray()
    for tile_index in range(tile_count):
        tile_x = (tile_index % width_tiles) * 8
        tile_y = (tile_index // width_tiles) * 8
        tile = bytearray()
        for yy in range(8):
            start = (tile_y + yy) * width + tile_x
            tile.extend(pixels[start : start + 8])
        if any(value != 255 for value in tile):
            mask[tile_index // 8] |= 1 << (tile_index & 7)
            tile_payload.extend(tile)
    pixel_offset = 4 + len(mask)
    frame = struct.pack("<HBB", pixel_offset, width_tiles, height_tiles) + mask + tile_payload
    payload = struct.pack("<HHH", 1, 6, 0) + frame
    return struct.pack("<I", len(payload)) + payload


def build_animated_logo(game_dir: Path, output: Path, font_path: Path) -> None:
    palette = load_palette(game_dir / "PALETTE.DEF")
    pixels = bytearray([255]) * (LOGO_WIDTH * LOGO_HEIGHT)
    first = fit_font(font_path, "위저드리 7", 200, 34)
    second = fit_font(font_path, "다크 서번트", 200, 31)
    add_sprite_metal_text(pixels, palette, "위저드리 7", first, 2)
    add_sprite_metal_text(pixels, palette, "다크 서번트", second, 45)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encode_single_pic_frame(pixels, LOGO_WIDTH, LOGO_HEIGHT))


def _large_neutral_components(image: Image.Image) -> Image.Image:
    """Select the large silver glyph regions while rejecting stars/background."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    values = list(rgb.getdata())
    seed = bytearray(width * height)
    for index, (red, green, blue) in enumerate(values):
        high, low = max(red, green, blue), min(red, green, blue)
        if high >= 42 and high - low <= 38:
            seed[index] = 1

    keep = bytearray(width * height)
    seen = bytearray(width * height)
    for start, selected in enumerate(seed):
        if not selected or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        component: list[int] = []
        min_x = max_x = start % width
        min_y = max_y = start // width
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for neighbor in (index - 1, index + 1, index - width, index + width):
                if neighbor < 0 or neighbor >= len(seed) or seen[neighbor] or not seed[neighbor]:
                    continue
                nx, ny = neighbor % width, neighbor // width
                if abs(nx - x) + abs(ny - y) != 1:
                    continue
                seen[neighbor] = 1
                queue.append(neighbor)
        if len(component) >= 300 and max_x - min_x >= 12 and max_y - min_y >= 12:
            for index in component:
                keep[index] = 255
    return Image.frombytes("L", (width, height), bytes(keep))


def _remove_small_mask_components(mask: Image.Image, minimum_area: int) -> Image.Image:
    width, height = mask.size
    selected = bytearray(1 if value >= 80 else 0 for value in mask.tobytes())
    seen = bytearray(width * height)
    keep = bytearray(width * height)
    for start, value in enumerate(selected):
        if not value or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        component: list[int] = []
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            for neighbor in (index - 1, index + 1, index - width, index + width):
                if neighbor < 0 or neighbor >= len(selected) or seen[neighbor] or not selected[neighbor]:
                    continue
                nx, ny = neighbor % width, neighbor // width
                if abs(nx - x) + abs(ny - y) != 1:
                    continue
                seen[neighbor] = 1
                queue.append(neighbor)
        if len(component) >= minimum_area:
            for index in component:
                keep[index] = 255
    return Image.frombytes("L", mask.size, bytes(keep))


def build_animated_logo_from_image(
    game_dir: Path, source_image: Path, output: Path
) -> None:
    """Extract the supplied silver Korean logo and encode it as MON63.PIC."""
    source = Image.open(source_image).convert("RGB")
    width, height = source.size
    # The provided artwork places the two-line logo in this normalized upper band.
    crop_box = (
        round(width * 0.22),
        round(height * 0.035),
        round(width * 0.81),
        round(height * 0.44),
    )
    crop = source.crop(crop_box)
    seed = _large_neutral_components(crop)
    # Retain the dark bevel/shadow immediately surrounding the selected silver.
    near_logo = seed.filter(ImageFilter.MaxFilter(11))
    luminance = crop.convert("L")
    alpha = Image.new("L", crop.size, 0)
    alpha_pixels = bytearray(alpha.tobytes())
    crop_colors = list(crop.getdata())
    for index, (near, light, color) in enumerate(
        zip(near_logo.tobytes(), luminance.tobytes(), crop_colors)
    ):
        if near and light >= 7 and max(color) - min(color) <= 45:
            alpha_pixels[index] = 255
    alpha = Image.frombytes("L", crop.size, bytes(alpha_pixels))
    bbox = alpha.getbbox()
    if not bbox:
        raise ValueError(f"could not isolate logo from {source_image}")
    rgba = crop.crop(bbox).convert("RGBA")
    rgba.putalpha(alpha.crop(bbox))

    scale = min((LOGO_WIDTH - 4) / rgba.width, (LOGO_HEIGHT - 4) / rgba.height)
    resized = rgba.resize(
        (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (LOGO_WIDTH, LOGO_HEIGHT), (0, 0, 0, 0))
    canvas.alpha_composite(
        resized,
        ((LOGO_WIDTH - resized.width) // 2, (LOGO_HEIGHT - resized.height) // 2),
    )
    canvas.putalpha(_remove_small_mask_components(canvas.getchannel("A"), 6))

    palette = load_palette(game_dir / "PALETTE.DEF")
    pixels = bytearray([255]) * (LOGO_WIDTH * LOGO_HEIGHT)
    for index, (red, green, blue, alpha_value) in enumerate(canvas.getdata()):
        if alpha_value >= 80:
            pixels[index] = nearest_index((red, green, blue), palette)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encode_single_pic_frame(pixels, LOGO_WIDTH, LOGO_HEIGHT))


def blank_video_frames(source: Path, output: Path) -> None:
    data = bytearray(source.read_bytes())
    if len(data) < 10 or struct.unpack_from("<I", data, 0)[0] != len(data) - 4:
        raise ValueError(f"unexpected VIDEO container: {source}")
    frame_count = struct.unpack_from("<H", data, 4)[0]
    starts: list[int] = []
    for index in range(frame_count):
        offset, segment = struct.unpack_from("<HH", data, 6 + index * 4)
        starts.append(4 + segment * 16 + offset)
    if starts != sorted(starts) or starts[0] != 6 + frame_count * 4:
        raise ValueError("unexpected VIDEO frame pointers")
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(data)
        if end - start < 4:
            raise ValueError("truncated VIDEO frame")
        # A frame starts with:
        #   uint16 pixel_data_offset; uint8 width_in_tiles; uint8 height_in_tiles
        # followed by one presence bit per 8x8 tile.  Clearing only that bitmap
        # is the driver's native transparent/no-op representation.  Preserve the
        # dimensions and pixel payload so every descriptor and far pointer stays
        # valid.
        width_tiles = data[start + 2]
        height_tiles = data[start + 3]
        mask_size = (width_tiles * height_tiles + 7) // 8
        mask_end = start + 4 + mask_size
        if mask_end > end:
            raise ValueError(f"truncated VIDEO tile mask in frame {index}")
        data[start + 4 : mask_end] = b"\x00" * mask_size
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--font",
        type=Path,
        default=Path(r"C:\Windows\Fonts\malgunbd.ttf"),
    )
    parser.add_argument(
        "--blank-video",
        action="append",
        default=None,
        help="VIDEO*.PIC file to turn into native no-op frames; repeatable",
    )
    parser.add_argument(
        "--static-fallback",
        action="store_true",
        help="also bake the Korean logo into TIT2SCRN.VGA",
    )
    parser.add_argument(
        "--logo-image",
        type=Path,
        help="extract the animated logo from a supplied raster artwork",
    )
    args = parser.parse_args()
    if args.static_fallback:
        build_screen(args.game_dir, args.output_dir / "TIT2SCRN.VGA", args.font)
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.game_dir / "TIT2SCRN.VGA", args.output_dir / "TIT2SCRN.VGA")
    if args.logo_image:
        build_animated_logo_from_image(
            args.game_dir, args.logo_image, args.output_dir / "MON63.PIC"
        )
    else:
        build_animated_logo(args.game_dir, args.output_dir / "MON63.PIC", args.font)
    blank_names = args.blank_video or []
    for name in blank_names:
        blank_video_frames(args.game_dir / name, args.output_dir / name)
    print((args.output_dir / "TIT2SCRN.VGA").resolve())
    print((args.output_dir / "MON63.PIC").resolve())
    for name in blank_names:
        print((args.output_dir / name).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
