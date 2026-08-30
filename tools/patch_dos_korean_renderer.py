#!/usr/bin/env python3
"""Patch Wizardry 7 DOS DS.EXE with a Korean VBFONT slot renderer.

The patch targets the known GOG DOS build (resident image offsets 0x3895 and
0x38CA).  Custom characters are encoded as ESCAPE + two ranked bytes by
``build_dos_messages.py``.  The hook copies a pre-rendered Korean glyph into
VBFONT slot 127, then calls the game's original character renderer.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from build_dos_messages import DEFAULT_ESCAPE, huffman_codes


MZ_HEADER_SIZE = 0x200
STRING_FUNCTION = 0x3895
WIDTH_FUNCTION = 0x38CA
ORIGINAL_DRAW = 0x3877
CAVE_START = 0x5055
CAVE_END = 0xFF62
FONT_SEGMENTS = {0: 0x364A, 2: 0x364E, 3: 0x3650}
RESERVED_GLYPH = 127


class Assembler16:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.data = bytearray()
        self.labels: dict[str, int] = {}
        self.rel8: list[tuple[int, str]] = []
        self.rel16: list[tuple[int, str]] = []
        self.abs16: list[tuple[int, str]] = []

    @property
    def address(self) -> int:
        return self.origin + len(self.data)

    def emit(self, *values: int) -> None:
        self.data.extend(value & 0xFF for value in values)

    def word(self, value: int) -> None:
        self.data.extend(struct.pack("<H", value & 0xFFFF))

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate assembler label {name}")
        self.labels[name] = self.address

    def j8(self, opcode: int, label: str) -> None:
        self.emit(opcode, 0)
        self.rel8.append((len(self.data) - 1, label))

    def j16(self, opcode: int, label: str) -> None:
        self.emit(opcode, 0, 0)
        self.rel16.append((len(self.data) - 2, label))

    def call_absolute(self, address: int) -> None:
        self.emit(0xE8)
        displacement = address - (self.address + 2)
        self.word(displacement)

    def word_label(self, label: str) -> None:
        self.abs16.append((len(self.data), label))
        self.word(0)

    def finish(self) -> bytes:
        for offset, label in self.rel8:
            target = self.labels[label]
            displacement = target - (self.origin + offset + 1)
            if not -128 <= displacement <= 127:
                raise ValueError(f"short branch to {label} is {displacement} bytes")
            self.data[offset] = displacement & 0xFF
        for offset, label in self.rel16:
            target = self.labels[label]
            displacement = target - (self.origin + offset + 2)
            struct.pack_into("<h", self.data, offset, displacement)
        for offset, label in self.abs16:
            struct.pack_into("<H", self.data, offset, self.labels[label])
        return bytes(self.data)


def bitmap_from_ttf(character: str, font: ImageFont.FreeTypeFont, width: int, height: int) -> bytes:
    canvas = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(canvas)
    box = draw.textbbox((0, 0), character, font=font)
    x = (width - (box[2] - box[0])) // 2 - box[0]
    y = (height - (box[3] - box[1])) // 2 - box[1]
    draw.text((x, y), character, font=font, fill=255)
    row_bytes = (width + 7) // 8
    result = bytearray(row_bytes * height)
    for y_pos in range(height):
        for x_pos in range(width):
            if canvas.getpixel((x_pos, y_pos)) >= 128:
                result[y_pos * row_bytes + x_pos // 8] |= 0x80 >> (x_pos & 7)
    return bytes(result)


def resize_1bpp(source: bytes, width: int, height: int) -> bytes:
    image = Image.new("1", (8, 8))
    for y_pos, row in enumerate(source):
        for x_pos in range(8):
            image.putpixel((x_pos, y_pos), 255 if row & (0x80 >> x_pos) else 0)
    resized = image.resize((width, height), Image.Resampling.NEAREST)
    result = bytearray(height)
    for y_pos in range(height):
        for x_pos in range(width):
            if resized.getpixel((x_pos, y_pos)):
                result[y_pos] |= 0x80 >> x_pos
    return bytes(result)


def build_glyph_table(
    codebook: dict[str, dict[str, str]],
    ranks: dict[int, int],
    glyph_map: dict[str, int],
    font_8x8: bytes,
    font_6x6: bytes,
    ttf_path: Path,
) -> tuple[bytes, int]:
    ordered: dict[int, str] = {}
    alphabet_size = len(ranks)
    for character, metadata in codebook.items():
        left_hex, right_hex = metadata["bytes"].split()
        index = ranks[int(left_hex, 16)] * alphabet_size + ranks[int(right_hex, 16)]
        ordered[index] = character
    if sorted(ordered) != list(range(len(ordered))):
        raise ValueError("codebook pairs are not a dense rectangular rank sequence")

    small_ttf = ImageFont.truetype(str(ttf_path), 7)
    large_ttf = ImageFont.truetype(str(ttf_path), 14)
    result = bytearray()
    for index in range(len(ordered)):
        character = ordered[index]
        mapped = glyph_map.get(character)
        if mapped is None:
            glyph_8 = bitmap_from_ttf(character, small_ttf, 8, 8)
            glyph_6 = bitmap_from_ttf(character, small_ttf, 6, 6)
        else:
            glyph_8 = font_8x8[mapped * 8:(mapped + 1) * 8]
            glyph_6 = font_6x6[mapped * 6:(mapped + 1) * 6]
        glyph_12x14 = bitmap_from_ttf(character, large_ttf, 12, 14)
        glyph_7x4 = resize_1bpp(glyph_8, 7, 4)
        result.extend(glyph_6)
        result.extend(glyph_12x14)
        result.extend(glyph_7x4)
    return bytes(result), len(ordered)


def emit_renderer(asm: Assembler16, alphabet_size: int, glyph_count: int) -> None:
    asm.label("string_hook")
    # The original wrapper establishes ES=DS before entering the video driver.
    # It also reloads SI for every character because the far driver call is free
    # to clobber it.  Preserve the additional registers used by this decoder so
    # callers observe the same register contract as the original wrapper.
    asm.emit(0x55, 0x89, 0xE5, 0xFC)  # push bp; mov bp,sp; cld
    asm.emit(0x56, 0x53, 0x51, 0x52, 0x1E, 0x06)  # save si/bx/cx/dx/ds/es
    asm.emit(0x8C, 0xD8, 0x8E, 0xC0)  # mov ax,ds; mov es,ax
    asm.emit(0x8B, 0x76, 0x04)  # mov si,[bp+4]
    asm.label("string_loop")
    asm.emit(0xAC, 0x08, 0xC0)  # lodsb; or al,al
    asm.j8(0x74, "string_done")
    asm.emit(0x3C, DEFAULT_ESCAPE)
    asm.j8(0x75, "draw_character")
    asm.emit(0xAC, 0x3C, DEFAULT_ESCAPE)  # first ranked byte or escaped literal
    asm.j8(0x74, "draw_character")
    asm.emit(0x30, 0xE4, 0x89, 0xC3)  # xor ah,ah; mov bx,ax
    asm.emit(0x2E, 0x8A, 0x87)  # mov al,cs:[bx+rank_table]
    asm.word_label("rank_table")
    asm.emit(0x3C, 0xFF)
    asm.j8(0x74, "invalid_character")
    asm.emit(0x30, 0xE4, 0x89, 0xC2, 0xAC, 0x30, 0xE4, 0x89, 0xC3)
    asm.emit(0x2E, 0x8A, 0x87)
    asm.word_label("rank_table")
    asm.emit(0x3C, 0xFF)
    asm.j8(0x74, "invalid_character")
    asm.emit(0x30, 0xE4, 0x89, 0xC3, 0x89, 0xD0, 0xB9)
    asm.word(alphabet_size)
    asm.emit(0xF7, 0xE1, 0x01, 0xD8, 0x3D)
    asm.word(glyph_count)
    asm.j8(0x73, "invalid_character")
    asm.emit(0x8B, 0x5E, 0x06, 0x83, 0xFB, 0x00)
    asm.j8(0x74, "supported_font")
    asm.emit(0x83, 0xFB, 0x02)
    asm.j8(0x74, "supported_font")
    asm.emit(0x83, 0xFB, 0x03)
    asm.j8(0x75, "invalid_character")
    asm.label("supported_font")
    asm.j16(0xE8, "copy_glyph")
    asm.emit(0xB8, RESERVED_GLYPH, 0x00)
    asm.j8(0xEB, "draw_character")
    asm.label("invalid_character")
    asm.emit(0xB8, ord("?"), 0x00)
    asm.label("draw_character")
    asm.emit(0x56)  # video driver may clobber si
    asm.emit(0xFF, 0x76, 0x06, 0x50)
    asm.call_absolute(ORIGINAL_DRAW)
    asm.emit(0x83, 0xC4, 0x04, 0x5E)
    asm.j16(0xE9, "string_loop")
    asm.label("string_done")
    asm.emit(0x30, 0xC0)  # preserve the original function's zero return value
    asm.emit(0x07, 0x1F, 0x5A, 0x59, 0x5B, 0x5E, 0x89, 0xEC, 0x5D, 0xC3)

    asm.label("copy_glyph")
    asm.emit(0x50, 0x53, 0x51, 0x52, 0x56, 0x57, 0x1E, 0x06)
    asm.emit(0x89, 0xC2, 0x89, 0xC6, 0xD1, 0xE0, 0x89, 0xC3)
    asm.emit(0xD1, 0xE0, 0x01, 0xC3, 0xD1, 0xE0, 0xD1, 0xE0, 0xD1, 0xE0)
    asm.emit(0x01, 0xC3, 0x89, 0xDE, 0x81, 0xC6)
    asm.word_label("glyph_table")  # si = glyph_table + index * 38
    asm.emit(0x0E, 0x1F, 0x8B, 0x5E, 0x06)  # ds=cs; bx=font index
    asm.emit(0x83, 0xFB, 0x00)
    asm.j8(0x74, "copy_font0")
    asm.emit(0x83, 0xFB, 0x02)
    asm.j8(0x74, "copy_font2")
    asm.j8(0xEB, "copy_font3")

    asm.label("copy_font0")
    asm.emit(0x2E, 0xA1)
    asm.word(FONT_SEGMENTS[0])
    asm.emit(0x8E, 0xC0, 0xBF, 0x0A, 0x04, 0xB9, 0x06, 0x00, 0xF3, 0xA4)
    asm.emit(0x26, 0xC6, 0x06, 0x0F, 0x01, 0x06)
    asm.j8(0xEB, "copy_done")

    asm.label("copy_font2")
    asm.emit(0x83, 0xC6, 0x06, 0x2E, 0xA1)
    asm.word(FONT_SEGMENTS[2])
    asm.emit(0x8E, 0xC0, 0xBF, 0xF4, 0x0E, 0xB9, 0x1C, 0x00, 0xF3, 0xA4)
    asm.emit(0x83, 0xEE, 0x1C, 0xBF, 0xF4, 0x1C, 0xB9, 0x1C, 0x00, 0xF3, 0xA4)
    asm.emit(0x26, 0xC6, 0x06, 0x0F, 0x01, 0x0C)
    asm.j8(0xEB, "copy_done")

    asm.label("copy_font3")
    asm.emit(0x83, 0xC6, 0x22, 0x2E, 0xA1)
    asm.word(FONT_SEGMENTS[3])
    asm.emit(0x8E, 0xC0, 0xBF, 0x0C, 0x03, 0xB9, 0x04, 0x00, 0xF3, 0xA4)
    asm.emit(0x26, 0xC6, 0x06, 0x0F, 0x01, 0x07)
    asm.label("copy_done")
    asm.emit(0x07, 0x1F, 0x5F, 0x5E, 0x5A, 0x59, 0x5B, 0x58, 0xC3)


def emit_width_hook(asm: Assembler16) -> None:
    asm.label("width_hook")
    asm.emit(0x55, 0x89, 0xE5, 0xFC, 0x06, 0x56, 0x53, 0x52)
    asm.emit(0x8B, 0x5E, 0x06, 0xD1, 0xE3, 0x2E, 0x8B, 0x87, 0x4A, 0x36)
    asm.emit(0x09, 0xC0)
    asm.j8(0x74, "width_no_font")
    asm.emit(0x8E, 0xC0, 0x31, 0xD2, 0x8B, 0x76, 0x04)
    asm.label("width_loop")
    asm.emit(0xAC, 0x08, 0xC0)
    asm.j8(0x74, "width_done")
    asm.emit(0x3C, DEFAULT_ESCAPE)
    asm.j8(0x75, "width_ascii")
    asm.emit(0xAC, 0x3C, DEFAULT_ESCAPE)
    asm.j8(0x74, "width_ascii")
    asm.emit(0x46, 0xB0, RESERVED_GLYPH)  # skip second rank byte; use slot 127
    asm.label("width_ascii")
    asm.emit(0x30, 0xE4, 0xD1, 0xE0, 0x89, 0xC3)
    asm.emit(0x26, 0x8A, 0x87, 0x11, 0x00, 0x30, 0xE4, 0x01, 0xC2)
    asm.emit(0x26, 0xA0, 0x07, 0x00, 0x98, 0x01, 0xC2)
    asm.j8(0xEB, "width_loop")
    asm.label("width_done")
    asm.emit(0x89, 0xD0)
    asm.j8(0xEB, "width_return")
    asm.label("width_no_font")
    asm.emit(0xB8, 0xFF, 0xFF)
    asm.label("width_return")
    asm.emit(0x5A, 0x5B, 0x5E, 0x07, 0x89, 0xEC, 0x5D, 0xC3)


def patch_jump(image: bytearray, source: int, target: int, expected: bytes) -> None:
    if image[source:source + len(expected)] != expected:
        actual = image[source:source + len(expected)].hex(" ")
        raise ValueError(f"unexpected bytes at image 0x{source:04X}: {actual}")
    displacement = target - (source + 3)
    image[source:source + 3] = b"\xE9" + struct.pack("<h", displacement)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--misc", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    parser.add_argument("--glyph-map", type=Path, required=True)
    parser.add_argument("--font-8x8", type=Path, required=True)
    parser.add_argument("--font-6x6", type=Path, required=True)
    parser.add_argument("--ttf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.codebook.read_text(encoding="utf-8"))
    codes = huffman_codes(args.misc.read_bytes())
    alphabet = sorted(
        (value for value in codes if value != DEFAULT_ESCAPE),
        key=lambda value: (len(codes[value]), value),
    )
    ranks = {value: index for index, value in enumerate(alphabet)}
    rank_table = bytes(ranks.get(value, 0xFF) for value in range(256))
    glyphs, glyph_count = build_glyph_table(
        report["codebook"],
        ranks,
        json.loads(args.glyph_map.read_text(encoding="utf-8")),
        args.font_8x8.read_bytes(),
        args.font_6x6.read_bytes(),
        args.ttf,
    )

    asm = Assembler16(CAVE_START)
    emit_renderer(asm, len(alphabet), glyph_count)
    emit_width_hook(asm)
    asm.label("rank_table")
    asm.data.extend(rank_table)
    asm.label("glyph_table")
    asm.data.extend(glyphs)
    payload = asm.finish()
    if CAVE_START + len(payload) > CAVE_END:
        raise ValueError(
            f"renderer payload ends at 0x{CAVE_START + len(payload):04X}, "
            f"beyond cave end 0x{CAVE_END:04X}"
        )

    raw = args.exe.read_bytes()
    if raw[:2] != b"MZ":
        raise ValueError("DS.EXE is not an MZ executable")
    header_paragraphs = struct.unpack_from("<H", raw, 8)[0]
    if header_paragraphs * 16 != MZ_HEADER_SIZE:
        raise ValueError("unexpected DS.EXE MZ header size")
    image = bytearray(raw[MZ_HEADER_SIZE:])
    patch_jump(image, STRING_FUNCTION, asm.labels["string_hook"], b"\x55\x8B\xEC")
    patch_jump(image, WIDTH_FUNCTION, asm.labels["width_hook"], b"\x55\x8B\xEC")
    if any(image[CAVE_START:CAVE_START + len(payload)]):
        raise ValueError("DS.EXE injection cave is not empty")
    image[CAVE_START:CAVE_START + len(payload)] = payload

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw[:MZ_HEADER_SIZE] + image)
    manifest = {
        "output": str(args.output),
        "glyph_count": glyph_count,
        "alphabet_size": len(alphabet),
        "payload_start": f"0x{CAVE_START:04X}",
        "payload_end": f"0x{CAVE_START + len(payload):04X}",
        "cave_remaining": CAVE_END - (CAVE_START + len(payload)),
        "string_hook": f"0x{asm.labels['string_hook']:04X}",
        "width_hook": f"0x{asm.labels['width_hook']:04X}",
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
