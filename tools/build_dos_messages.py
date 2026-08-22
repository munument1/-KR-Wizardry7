#!/usr/bin/env python3
"""Build Wizardry 7 DOS MSG.HDR/MSG.DBS from a translated CSV.

The DOS executable can only Huffman-decode the 122 byte values present in
MISC.HDR.  Korean and other unsupported Unicode characters are therefore
converted to a reversible three-byte stream::

    ESCAPE, code_a, code_b

Literal ESCAPE bytes are doubled.  ``korean_codebook.json`` records the
Unicode-to-pair mapping required by the future DOS text-rendering patch.
Untranslated records retain their original packed bytes exactly.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
from collections import Counter
from pathlib import Path

from extract_gold_messages import (
    BANK_SIZE,
    HEADER_ENTRIES,
    MessageRecord,
    RangeEntry,
    display_bytes,
    extract_messages,
    parse_header,
)


DEFAULT_ESCAPE = 0x17
BYTE_TOKEN = re.compile(r"<0x([0-9A-Fa-f]{2})>")


def huffman_codes(table_data: bytes) -> dict[int, tuple[int, ...]]:
    """Return leaf byte -> MSB-first bit tuple for a signed-int16 tree."""
    if len(table_data) % 2:
        raise ValueError("MISC.HDR must contain signed 16-bit values")
    table = struct.unpack(f"<{len(table_data) // 2}h", table_data)
    codes: dict[int, tuple[int, ...]] = {}
    visiting: set[int] = set()

    def walk(node: int, prefix: tuple[int, ...]) -> None:
        if node in visiting:
            raise ValueError(f"MISC.HDR contains a cycle at node {node}")
        if node * 2 + 1 >= len(table):
            raise ValueError(f"MISC.HDR node {node} is outside the table")
        visiting.add(node)
        for bit in (0, 1):
            value = table[node * 2 + bit]
            path = prefix + (bit,)
            if value < 0:
                walk(-value, path)
            else:
                if value in codes:
                    raise ValueError(f"duplicate Huffman leaf 0x{value:02X}")
                codes[value] = path
        visiting.remove(node)

    walk(0, ())
    return codes


def encode_huffman(raw: bytes, codes: dict[int, tuple[int, ...]]) -> bytes:
    """Encode decoded bytes as one DOS packed payload (without outer length)."""
    if len(raw) > 0xFF:
        raise ValueError(f"decoded record is {len(raw)} bytes; maximum is 255")
    output = bytearray((len(raw),))
    current = 0
    bit_count = 0
    for value in raw:
        try:
            bits = codes[value]
        except KeyError as exc:
            raise ValueError(f"byte 0x{value:02X} is absent from MISC.HDR") from exc
        for bit in bits:
            current = (current << 1) | bit
            bit_count += 1
            if bit_count == 8:
                output.append(current)
                current = 0
                bit_count = 0
    if bit_count:
        output.append(current << (8 - bit_count))
    if len(output) > 0xFF:
        raise ValueError(f"packed record is {len(output)} bytes; maximum is 255")
    return bytes(output)


def iter_translation_units(text: str) -> list[int | str]:
    """Parse CSV display notation into literal byte integers and characters."""
    units: list[int | str] = []
    cursor = 0
    while cursor < len(text):
        match = BYTE_TOKEN.match(text, cursor)
        if match:
            units.append(int(match.group(1), 16))
            cursor = match.end()
        else:
            units.append(text[cursor])
            cursor += 1
    return units


def build_unicode_codebook(
    texts: list[str],
    codes: dict[int, tuple[int, ...]],
    escape: int = DEFAULT_ESCAPE,
) -> dict[str, tuple[int, int]]:
    """Assign frequent unsupported characters to the cheapest byte pairs."""
    if escape not in codes:
        raise ValueError(f"escape byte 0x{escape:02X} is absent from MISC.HDR")
    frequencies: Counter[str] = Counter()
    for text in texts:
        for unit in iter_translation_units(text):
            if isinstance(unit, str) and (ord(unit) > 0x7F or ord(unit) not in codes):
                frequencies[unit] += 1

    alphabet = sorted(
        (value for value in codes if value != escape),
        key=lambda value: (len(codes[value]), value),
    )
    pairs = sorted(
        ((left, right) for left in alphabet for right in alphabet),
        key=lambda pair: (
            len(codes[pair[0]]) + len(codes[pair[1]]),
            pair[0],
            pair[1],
        ),
    )
    if len(frequencies) > len(pairs):
        raise ValueError(
            f"{len(frequencies)} custom characters exceed {len(pairs)} code pairs"
        )
    ordered_chars = sorted(frequencies, key=lambda char: (-frequencies[char], ord(char)))
    return {char: pairs[index] for index, char in enumerate(ordered_chars)}


def encode_translation(
    text: str,
    codes: dict[int, tuple[int, ...]],
    codebook: dict[str, tuple[int, int]],
    escape: int = DEFAULT_ESCAPE,
) -> bytes:
    output = bytearray()
    for unit in iter_translation_units(text):
        if isinstance(unit, int):
            value = unit
        elif ord(unit) <= 0x7F and ord(unit) in codes:
            value = ord(unit)
        else:
            try:
                left, right = codebook[unit]
            except KeyError as exc:
                raise ValueError(f"character {unit!r} is absent from the codebook") from exc
            output.extend((escape, left, right))
            continue
        if value not in codes:
            raise ValueError(f"literal byte 0x{value:02X} is absent from MISC.HDR")
        if value == escape:
            output.extend((escape, escape))
        else:
            output.append(value)
    if len(output) > 0xFF:
        raise ValueError(f"encoded translation is {len(output)} bytes; maximum is 255")
    return bytes(output)


def decode_translation(
    raw: bytes,
    codebook: dict[str, tuple[int, int]],
    escape: int = DEFAULT_ESCAPE,
) -> str:
    """Decode the custom stream for tests and renderer-fixture generation."""
    reverse = {pair: char for char, pair in codebook.items()}
    output: list[str] = []
    cursor = 0
    while cursor < len(raw):
        value = raw[cursor]
        cursor += 1
        if value != escape:
            output.append(chr(value))
            continue
        if cursor >= len(raw):
            raise ValueError("custom stream ends after escape byte")
        if raw[cursor] == escape:
            output.append(chr(escape))
            cursor += 1
            continue
        if cursor + 1 >= len(raw):
            raise ValueError("custom stream ends inside a character pair")
        pair = (raw[cursor], raw[cursor + 1])
        cursor += 2
        try:
            output.append(reverse[pair])
        except KeyError as exc:
            raise ValueError(f"unknown custom pair {pair!r}") from exc
    return "".join(output)


def read_translations(path: Path) -> dict[int, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"message_id", "translation"}
    if not rows and not required.issubset(set(rows[0]) if rows else set()):
        raise ValueError("translation CSV is empty")
    translations: dict[int, dict[str, str]] = {}
    for row in rows:
        if not required.issubset(row):
            raise ValueError("translation CSV requires message_id and translation columns")
        message_id = int(row["message_id"])
        if message_id in translations:
            raise ValueError(f"duplicate translation message_id {message_id}")
        translations[message_id] = row
    return translations


def build_files(
    hdr_raw: bytes,
    data_raw: bytes,
    misc_raw: bytes,
    translations: dict[int, dict[str, str]],
    escape: int = DEFAULT_ESCAPE,
) -> tuple[bytes, bytes, dict]:
    declared, entries, sentinel_count = parse_header(hdr_raw, "dos")
    records = extract_messages(data_raw, entries, misc_raw)
    by_range: dict[int, list[MessageRecord]] = {}
    for record in records:
        by_range.setdefault(record.range_index, []).append(record)

    applicable: dict[int, str] = {}
    mismatched: list[int] = []
    missing_ids: list[int] = []
    record_by_id = {record.message_id: record for record in records}
    for message_id, row in translations.items():
        translation = row.get("translation", "")
        if not translation:
            continue
        record = record_by_id.get(message_id)
        if record is None:
            missing_ids.append(message_id)
            continue
        expected = row.get("source_text", "")
        if expected and expected != record.source_display:
            mismatched.append(message_id)
            continue
        applicable[message_id] = translation

    codes = huffman_codes(misc_raw)
    codebook = build_unicode_codebook(list(applicable.values()), codes, escape)
    output_data = bytearray()
    output_entries: list[RangeEntry] = []
    translated_ids: list[int] = []

    for entry in entries:
        absolute = len(output_data)
        bank, bank_offset = divmod(absolute, BANK_SIZE)
        if bank > 0xFF:
            raise ValueError("rebuilt MSG.DBS exceeds the DOS 8-bit bank field")
        output_entries.append(
            RangeEntry(entry.range_index, entry.start_id, bank_offset, entry.id_span, bank)
        )
        for record in by_range[entry.range_index]:
            translation = applicable.get(record.message_id)
            if translation is None:
                packed = bytes.fromhex(record.packed_hex)
            else:
                raw = encode_translation(translation, codes, codebook, escape)
                packed = encode_huffman(raw, codes)
                translated_ids.append(record.message_id)
            if len(packed) > 0xFF:
                raise ValueError(f"message {record.message_id}: packed record exceeds 255 bytes")
            output_data.append(len(packed))
            output_data.extend(packed)

    used_data_bytes = len(output_data)
    maximum_size = 256 * BANK_SIZE
    if used_data_bytes > maximum_size:
        raise ValueError(
            f"rebuilt MSG.DBS is {used_data_bytes} bytes; DOS limit is {maximum_size}"
        )
    output_data.extend(bytes(maximum_size - used_data_bytes))

    entry_struct = HEADER_ENTRIES["dos"]
    output_header = bytearray(struct.pack("<H", declared))
    for entry in output_entries:
        output_header.extend(
            entry_struct.pack(entry.start_id, entry.bank_offset, entry.id_span, entry.bank)
        )
    output_header.extend(bytes(sentinel_count * entry_struct.size))

    report = {
        "translated_record_count": len(translated_ids),
        "custom_character_count": len(codebook),
        "source_mismatch_ids": sorted(mismatched),
        "missing_message_ids": sorted(missing_ids),
        "escape_byte": f"0x{escape:02X}",
        "used_data_bytes": used_data_bytes,
        "padded_data_size": len(output_data),
        "codebook": {
            char: {"codepoint": f"U+{ord(char):04X}", "bytes": f"{pair[0]:02X} {pair[1]:02X}"}
            for char, pair in codebook.items()
        },
    }
    return bytes(output_header), bytes(output_data), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hdr", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--misc", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--escape", type=lambda value: int(value, 0), default=DEFAULT_ESCAPE)
    args = parser.parse_args()

    output_header, output_data, report = build_files(
        args.hdr.read_bytes(),
        args.data.read_bytes(),
        args.misc.read_bytes(),
        read_translations(args.translations),
        args.escape,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "MSG.HDR").write_bytes(output_header)
    (args.output_dir / "MSG.DBS").write_bytes(output_data)
    (args.output_dir / "korean_codebook.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "codebook"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
