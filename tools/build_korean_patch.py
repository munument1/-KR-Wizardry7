#!/usr/bin/env python3
"""Build Wizardry 7 Gold Korean data files from original GOG files.

The script validates source CRCs against the translation payload, rebuilds
MSG.HDR/MSG.GLD with custom two-byte Hangul, patches the fixed-width names in
SCENARIO.GLD, and expands VBFONT0.VGA from 6x6 to the verified 8x8 container.
It never modifies the input directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import struct
import tempfile
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

BANK_SIZE = 1024
HEADER_ENTRY = struct.Struct("<HHBH")
CONTROL_RE = re.compile(r"<0x([0-9A-Fa-f]{2})>")

ITEM_TABLE_OFFSET = 0x0380
ITEM_RECORD_SIZE = 0x48
ITEM_COUNT = 600
ITEM_NAME_SIZE = 16
MONSTER_NAME_OFFSET = 0x37040
MONSTER_RECORD_SIZE = 0xE8
MONSTER_COUNT = 250
MONSTER_NAME_SIZE = 16
MONSTER_VARIANTS = ("singular", "plural", "generic_singular", "generic_plural")


@dataclass(frozen=True)
class RangeEntry:
    range_index: int
    start_id: int
    bank_offset: int
    id_span: int
    bank: int


@dataclass(frozen=True)
class MessageRecord:
    range_index: int
    message_id: int
    raw: bytes


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def crc32(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


def encode_game_text(text: str) -> bytes:
    output = bytearray()
    index = 0
    while index < len(text):
        match = CONTROL_RE.match(text, index)
        if match:
            output.append(int(match.group(1), 16))
            index = match.end()
            continue
        char = text[index]
        if ord(char) < 0x80:
            output.append(ord(char))
            index += 1
            continue
        try:
            encoded = char.encode("euc_kr")
        except UnicodeEncodeError as exc:
            raise ValueError(f"unsupported character {char!r} U+{ord(char):04X}") from exc
        if len(encoded) != 2 or not (0xB0 <= encoded[0] <= 0xC8 and 0xA1 <= encoded[1] <= 0xFE):
            raise ValueError(f"character is outside KS X 1001 Hangul: {char!r} U+{ord(char):04X}")
        glyph_index = (encoded[0] - 0xB0) * 94 + (encoded[1] - 0xA1)
        output.extend((0x80 + glyph_index // 96, 0xA0 + glyph_index % 96))
        index += 1
    return bytes(output)


def parse_header(raw: bytes) -> tuple[list[RangeEntry], int]:
    if len(raw) < 2:
        raise ValueError("MSG.HDR is too short")
    declared = struct.unpack_from("<H", raw, 0)[0]
    required = 2 + declared * HEADER_ENTRY.size
    if len(raw) < required:
        raise ValueError("MSG.HDR range table is truncated")
    entries: list[RangeEntry] = []
    cursor = 2
    for index in range(declared):
        start_id, bank_offset, id_span, bank = HEADER_ENTRY.unpack_from(raw, cursor)
        if bank_offset >= BANK_SIZE:
            raise ValueError(f"range {index}: invalid bank offset {bank_offset}")
        entries.append(RangeEntry(index, start_id, bank_offset, id_span, bank))
        cursor += HEADER_ENTRY.size
    trailer = raw[cursor:]
    if len(trailer) % HEADER_ENTRY.size or any(trailer):
        raise ValueError("MSG.HDR has an unexpected trailer")
    return entries, len(trailer) // HEADER_ENTRY.size


def extract_messages(gld: bytes, entries: list[RangeEntry]) -> list[MessageRecord]:
    result: list[MessageRecord] = []
    for entry in entries:
        cursor = entry.bank * BANK_SIZE + entry.bank_offset
        for delta in range(entry.id_span + 1):
            if cursor >= len(gld):
                raise ValueError(f"message {entry.start_id + delta}: offset outside MSG.GLD")
            length = gld[cursor]
            end = cursor + 1 + length
            if end > len(gld):
                raise ValueError(f"message {entry.start_id + delta}: record exceeds MSG.GLD")
            result.append(MessageRecord(entry.range_index, entry.start_id + delta, gld[cursor + 1 : end]))
            cursor = end
    return result


def load_message_translations(path: Path) -> dict[tuple[int, int], dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result: dict[tuple[int, int], dict[str, str]] = {}
    for row in rows:
        key = (int(row["range_index"]), int(row["message_id"]))
        if key in result:
            raise ValueError(f"duplicate message translation key {key}")
        result[key] = row
    return result


def rebuild_messages(hdr: bytes, gld: bytes, translation_csv: Path) -> tuple[bytes, bytes, dict]:
    entries, sentinel_count = parse_header(hdr)
    records = extract_messages(gld, entries)
    translations = load_message_translations(translation_csv)
    if len(records) != len(translations):
        raise ValueError(f"message row count mismatch: original={len(records)} translation={len(translations)}")

    by_key = {(record.range_index, record.message_id): record for record in records}
    missing = sorted(set(by_key) - set(translations))
    extra = sorted(set(translations) - set(by_key))
    if missing or extra:
        raise ValueError(f"message key mismatch: missing={missing[:3]} extra={extra[:3]}")

    patched_payloads: dict[tuple[int, int], bytes] = {}
    for key, record in by_key.items():
        row = translations[key]
        if crc32(record.raw) != row["source_crc32"].upper():
            raise ValueError(f"message {key}: source CRC mismatch; wrong game version or translation payload")
        text = row["translation"]
        if record.raw and not text:
            raise ValueError(f"message {key}: missing Korean translation")
        payload = encode_game_text(text) if text else b""
        if len(payload) > 255:
            raise ValueError(f"message {key}: encoded length {len(payload)} exceeds 255")
        patched_payloads[key] = payload

    output_gld = bytearray()
    new_entries: list[RangeEntry] = []
    for entry in entries:
        start_offset = len(output_gld)
        bank = start_offset // BANK_SIZE
        bank_offset = start_offset % BANK_SIZE
        if bank > 0xFFFF:
            raise ValueError("rebuilt MSG.GLD exceeds 16-bit bank index")
        new_entries.append(RangeEntry(entry.range_index, entry.start_id, bank_offset, entry.id_span, bank))
        for delta in range(entry.id_span + 1):
            key = (entry.range_index, entry.start_id + delta)
            payload = patched_payloads[key]
            output_gld.append(len(payload))
            output_gld.extend(payload)
    if len(output_gld) % BANK_SIZE:
        output_gld.extend(b"\x00" * (BANK_SIZE - len(output_gld) % BANK_SIZE))

    output_hdr = bytearray(struct.pack("<H", len(new_entries)))
    for entry in new_entries:
        output_hdr.extend(HEADER_ENTRY.pack(entry.start_id, entry.bank_offset, entry.id_span, entry.bank))
    output_hdr.extend(b"\x00" * (sentinel_count * HEADER_ENTRY.size))

    verify_entries, verify_sentinels = parse_header(bytes(output_hdr))
    verify_records = extract_messages(bytes(output_gld), verify_entries)
    if len(verify_records) != len(records) or verify_sentinels != sentinel_count:
        raise AssertionError("rebuilt MSG verification failed")

    return bytes(output_hdr), bytes(output_gld), {
        "range_count": len(entries),
        "message_count": len(records),
        "sentinel_count": sentinel_count,
        "original_hdr_sha256": sha256(hdr),
        "original_gld_sha256": sha256(gld),
        "patched_hdr_sha256": sha256(bytes(output_hdr)),
        "patched_gld_sha256": sha256(bytes(output_gld)),
        "patched_gld_size": len(output_gld),
    }


def scenario_offset(category: str, index: int, variant: str) -> int:
    if category == "item":
        if not 0 <= index < ITEM_COUNT or variant != "name":
            raise ValueError(f"invalid item key {index} {variant}")
        return ITEM_TABLE_OFFSET + index * ITEM_RECORD_SIZE
    if category == "monster":
        if not 0 <= index < MONSTER_COUNT or variant not in MONSTER_VARIANTS:
            raise ValueError(f"invalid monster key {index} {variant}")
        return MONSTER_NAME_OFFSET + index * MONSTER_RECORD_SIZE + MONSTER_VARIANTS.index(variant) * MONSTER_NAME_SIZE
    raise ValueError(f"unknown scenario category {category!r}")


def patch_scenario(data: bytes, translation_csv: Path) -> tuple[bytes, dict]:
    result = bytearray(data)
    with translation_csv.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != ITEM_COUNT + MONSTER_COUNT * len(MONSTER_VARIANTS):
        raise ValueError(f"unexpected Scenario translation row count: {len(rows)}")

    changed = 0
    for row in rows:
        category = row["category"]
        index = int(row["record_index"])
        variant = row["variant"]
        offset = scenario_offset(category, index, variant)
        size = ITEM_NAME_SIZE if category == "item" else MONSTER_NAME_SIZE
        if offset + size > len(result):
            raise ValueError(f"scenario {category} {index} {variant}: offset outside SCENARIO.GLD")
        slot = bytes(result[offset : offset + size])
        source_payload = slot.split(b"\x00", 1)[0]
        if crc32(source_payload) != row["source_crc32"].upper():
            raise ValueError(f"scenario {category} {index} {variant}: source CRC mismatch")
        text = row["translation"]
        if source_payload and not text:
            raise ValueError(f"scenario {category} {index} {variant}: missing Korean translation")
        encoded = encode_game_text(text) if text else b""
        if len(encoded) > size:
            raise ValueError(f"scenario {category} {index} {variant}: {len(encoded)} bytes > {size}")
        replacement = encoded + b"\x00" * (size - len(encoded))
        if replacement != slot:
            result[offset : offset + size] = replacement
            changed += 1
    return bytes(result), {
        "slot_count": len(rows),
        "changed_slot_count": changed,
        "original_sha256": sha256(data),
        "patched_sha256": sha256(bytes(result)),
    }


def expand_vbfont0(original: bytes) -> bytes:
    if len(original) != 1040 or original[0] != 6 or original[1] != 6 or original[5] != 128:
        raise ValueError("unexpected VBFONT0.VGA layout")
    glyph_count = 128
    table_size = glyph_count * 2
    header_size = 16
    old_bitmap_offset = header_size + table_size
    new_glyph_size = 8
    result = bytearray(header_size + table_size + glyph_count * new_glyph_size)
    result[:old_bitmap_offset] = original[:old_bitmap_offset]
    result[0] = 8
    result[1] = 8
    result[3] = 1
    struct.pack_into("<H", result, 10, new_glyph_size)
    struct.pack_into("<H", result, 12, len(result))
    struct.pack_into("<H", result, 14, new_glyph_size)
    for glyph in range(glyph_count):
        old_base = old_bitmap_offset + glyph * 6
        new_base = old_bitmap_offset + glyph * new_glyph_size
        for y in range(6):
            result[new_base + y + 1] = original[old_base + y] >> 1
    return bytes(result)


def copy_runtime(path: Path | None, output_dir: Path, name: str) -> bool:
    if path is None:
        return False
    if not path.is_file():
        raise ValueError(f"runtime asset not found: {path}")
    shutil.copy2(path, output_dir / name)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dir", type=Path, default=Path("original"))
    parser.add_argument(
        "--translation-dir",
        type=Path,
        default=Path("translations/wizardry7_ko_payload.zip"),
        help="translation directory or packed wizardry7_ko_payload.zip",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/korean_patch"))
    parser.add_argument("--winmm", type=Path, help="prebuilt x86 winmm.dll proxy to include")
    parser.add_argument("--hangul-font", type=Path, help="wizardry7_ksx1001_8x8.bin to include")
    args = parser.parse_args()

    hdr = (args.original_dir / "MSG.HDR").read_bytes()
    gld = (args.original_dir / "MSG.GLD").read_bytes()
    scenario = (args.original_dir / "SCENARIO.GLD").read_bytes()
    vbfont0 = (args.original_dir / "VBFONT0.VGA").read_bytes()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    temp_ctx = None
    translation_dir = args.translation_dir
    if translation_dir.is_file() and translation_dir.suffix.lower() == ".zip":
        temp_ctx = tempfile.TemporaryDirectory()
        extracted = Path(temp_ctx.name)
        with zipfile.ZipFile(translation_dir) as archive:
            archive.extract("messages_ko.csv", extracted)
            archive.extract("scenario_ko.csv", extracted)
        translation_dir = extracted
    elif not translation_dir.is_dir():
        raise ValueError(f"translation payload not found: {translation_dir}")

    try:
        patched_hdr, patched_gld, message_report = rebuild_messages(
            hdr, gld, translation_dir / "messages_ko.csv"
        )
        patched_scenario, scenario_report = patch_scenario(
            scenario, translation_dir / "scenario_ko.csv"
        )
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()
    patched_vbfont0 = expand_vbfont0(vbfont0)

    (args.output_dir / "MSG.HDR").write_bytes(patched_hdr)
    (args.output_dir / "MSG.GLD").write_bytes(patched_gld)
    (args.output_dir / "SCENARIO.GLD").write_bytes(patched_scenario)
    (args.output_dir / "VBFONT0.VGA").write_bytes(patched_vbfont0)

    runtime = {
        "winmm.dll": copy_runtime(args.winmm, args.output_dir, "winmm.dll"),
        "wizardry7_ksx1001_8x8.bin": copy_runtime(
            args.hangul_font, args.output_dir, "wizardry7_ksx1001_8x8.bin"
        ),
    }
    report = {
        "format": "Wizardry 7 Gold Korean patch build v1",
        "messages": message_report,
        "scenario": scenario_report,
        "vbfont0": {
            "original_sha256": sha256(vbfont0),
            "patched_sha256": sha256(patched_vbfont0),
            "patched_size": len(patched_vbfont0),
        },
        "runtime_assets_included": runtime,
        "ready_to_install": all(runtime.values()),
    }
    (args.output_dir / "patch_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
