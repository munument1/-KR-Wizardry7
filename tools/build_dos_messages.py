#!/usr/bin/env python3
"""Build Wizardry 7 DOS MSG.HDR/MSG.DBS from a translated CSV.

The DOS executable can only Huffman-decode the 122 byte values present in
MISC.HDR.  Korean and other unsupported Unicode characters are therefore
converted to a reversible three-byte stream::

    ESCAPE, code_a, code_b

Literal ESCAPE bytes are doubled.  ``korean_codebook.json`` records the
Unicode-to-pair mapping required by the DOS text-rendering patch.

The original English Huffman tree cannot fit the larger Korean byte stream in
the DOS 256 KiB message address space.  The builder therefore retrains the
tree, writes a replacement ``MISC.HDR``, and re-encodes every record.
"""

from __future__ import annotations

import argparse
import base64
import csv
import heapq
import itertools
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
MAX_DOS_BANKS = 0x100
MAX_DOS_DATA_SIZE = MAX_DOS_BANKS * BANK_SIZE
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


HuffmanNode = int | tuple["HuffmanNode", "HuffmanNode"]


def build_huffman_tree(
    frequencies: Counter[int], alphabet: list[int]
) -> HuffmanNode:
    """Build a deterministic Huffman tree while retaining every DOS leaf."""
    if len(alphabet) < 2:
        raise ValueError("Huffman alphabet requires at least two byte values")
    order = itertools.count()
    heap: list[tuple[int, int, HuffmanNode]] = []
    for value in sorted(alphabet):
        heapq.heappush(heap, (max(1, frequencies[value]), next(order), value))
    while len(heap) > 1:
        left_weight, _, left = heapq.heappop(heap)
        right_weight, _, right = heapq.heappop(heap)
        heapq.heappush(
            heap,
            (left_weight + right_weight, next(order), (left, right)),
        )
    return heap[0][2]


def serialize_huffman_tree(tree: HuffmanNode) -> bytes:
    """Serialize a tree to the signed-int16 node format used by MISC.HDR."""
    nodes: list[tuple[int, int] | None] = []

    def add(node: HuffmanNode) -> int:
        if isinstance(node, int):
            return node
        index = len(nodes)
        nodes.append(None)
        left = add(node[0])
        right = add(node[1])
        nodes[index] = (left, right)
        return -index

    add(tree)
    values = [value for node in nodes for value in node]  # type: ignore[union-attr]
    return struct.pack(f"<{len(values)}h", *values)


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
    # Keep pairs in a rectangular rank order.  The DOS renderer can then
    # recover the glyph index with rank(left) * len(alphabet) + rank(right)
    # using one 256-byte inverse-rank table instead of a large pair lookup.
    pairs = [(left, right) for left in alphabet for right in alphabet]
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


def pack_message_ranges(
    entries: list[RangeEntry],
    records_by_range: dict[int, list[MessageRecord]],
    packed_by_id: dict[int, bytes],
    maximum_size: int = MAX_DOS_DATA_SIZE,
) -> tuple[bytes, list[RangeEntry], int]:
    """Pack complete MSG.HDR ranges without crossing a bank with record starts.

    DS.EXE walks preceding subindices by adding ``1 + record_length`` to an
    offset in the currently loaded 0x400-byte bank.  It can handle the final
    payload crossing a bank, but it cannot load a new bank while walking the
    preceding record length bytes.  Keep each complete range in one bank; an
    unreferenced zero-filled gap is inserted before a range when necessary.
    """
    output = bytearray()
    output_entries: list[RangeEntry] = []
    padding_bytes = 0

    for entry in entries:
        records = records_by_range.get(entry.range_index, [])
        expected_count = entry.id_span + 1
        if len(records) != expected_count:
            raise ValueError(
                f"range {entry.range_index}: expected {expected_count} records, "
                f"found {len(records)}"
            )
        records = sorted(records, key=lambda record: record.message_id)
        expected_ids = list(range(entry.start_id, entry.start_id + expected_count))
        actual_ids = [record.message_id for record in records]
        if actual_ids != expected_ids:
            raise ValueError(
                f"range {entry.range_index}: message IDs {actual_ids[:3]}.."
                f"{actual_ids[-3:]} do not match {expected_ids[:3]}.."
                f"{expected_ids[-3:]}"
            )

        packed_records: list[tuple[MessageRecord, bytes]] = []
        group_size = 0
        for record in records:
            try:
                packed = packed_by_id[record.message_id]
            except KeyError as exc:
                raise ValueError(
                    f"range {entry.range_index}: missing packed record "
                    f"{record.message_id}"
                ) from exc
            if len(packed) > 0xFF:
                raise ValueError(
                    f"message {record.message_id}: packed record exceeds 255 bytes"
                )
            packed_records.append((record, packed))
            group_size += 1 + len(packed)

        # A conservative whole-range placement is intentional.  The original
        # game permits only the final payload of a range to cross a bank; a
        # range larger than one bank cannot be represented safely by this
        # builder without splitting its HDR entry.
        if group_size > BANK_SIZE:
            raise ValueError(
                f"range {entry.range_index} ({entry.start_id}.."
                f"{entry.start_id + entry.id_span}) occupies {group_size} bytes; "
                f"it cannot fit in one DOS {BANK_SIZE}-byte bank"
            )

        current_offset = len(output) % BANK_SIZE
        if current_offset and current_offset + group_size > BANK_SIZE:
            gap = BANK_SIZE - current_offset
            output.extend(bytes(gap))
            padding_bytes += gap
        absolute = len(output)
        bank, bank_offset = divmod(absolute, BANK_SIZE)
        if bank >= MAX_DOS_BANKS:
            raise ValueError(
                f"range {entry.range_index}: bank {bank} exceeds the DOS 8-bit bank field"
            )
        output_entries.append(
            RangeEntry(entry.range_index, entry.start_id, bank_offset, entry.id_span, bank)
        )

        range_start = len(output)
        for record, packed in packed_records:
            record_start = len(output)
            if record_start // BANK_SIZE != bank:
                raise AssertionError(
                    f"range {entry.range_index}: record {record.message_id} "
                    "starts outside its MSG.HDR bank"
                )
            output.append(len(packed))
            output.extend(packed)
        if len(output) - range_start != group_size:
            raise AssertionError(
                f"range {entry.range_index}: packed size accounting mismatch"
            )

    if len(output) > maximum_size:
        raise ValueError(
            f"rebuilt MSG.DBS is {len(output)} bytes; DOS limit is {maximum_size}"
        )
    return bytes(output), output_entries, padding_bytes


def find_record_start_crossings(
    data: bytes, entries: list[RangeEntry]
) -> list[tuple[int, int, int, int]]:
    """Return ranges whose subindex record starts leave the entry bank.

    This verifier intentionally models the DOS walk instead of merely parsing
    records against the complete file.  Each tuple is
    ``(range_index, message_id, entry_bank, actual_bank)``.
    """
    violations: list[tuple[int, int, int, int]] = []
    for entry in entries:
        cursor = entry.bank * BANK_SIZE + entry.bank_offset
        for delta in range(entry.id_span + 1):
            actual_bank = cursor // BANK_SIZE
            if actual_bank != entry.bank:
                violations.append(
                    (entry.range_index, entry.start_id + delta, entry.bank, actual_bank)
                )
            if cursor >= len(data):
                break
            cursor += 1 + data[cursor]
    return violations


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
    huffman_iterations: int = 8,
) -> tuple[bytes, bytes, bytes, dict]:
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

    if huffman_iterations < 1:
        raise ValueError("huffman_iterations must be at least 1")

    original_codes = huffman_codes(misc_raw)
    alphabet = sorted(original_codes)
    raw_by_id = {
        record.message_id: base64.b64decode(record.raw_base64) for record in records
    }
    codes = original_codes
    codebook: dict[str, tuple[int, int]] = {}
    encoded_by_id: dict[int, bytes] = {}
    output_misc = misc_raw
    for _ in range(huffman_iterations):
        codebook = build_unicode_codebook(list(applicable.values()), codes, escape)
        encoded_by_id = {
            record.message_id: (
                encode_translation(applicable[record.message_id], codes, codebook, escape)
                if record.message_id in applicable
                else raw_by_id[record.message_id]
            )
            for record in records
        }
        frequencies: Counter[int] = Counter(
            value for raw in encoded_by_id.values() for value in raw
        )
        output_misc = serialize_huffman_tree(
            build_huffman_tree(frequencies, alphabet)
        )
        codes = huffman_codes(output_misc)

    packed_by_id: dict[int, bytes] = {}
    encoded_lengths: dict[int, int] = {}
    for record in records:
        packed = encode_huffman(encoded_by_id[record.message_id], codes)
        packed_by_id[record.message_id] = packed
        encoded_lengths[record.message_id] = len(packed)

    output_data, output_entries, padding_bytes = pack_message_ranges(
        entries,
        by_range,
        packed_by_id,
    )
    translated_ids: list[int] = []

    for record in records:
        if record.message_id in applicable:
            translated_ids.append(record.message_id)

    used_data_bytes = len(output_data)
    output_data = output_data + bytes(MAX_DOS_DATA_SIZE - used_data_bytes)

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
        "huffman_iterations": huffman_iterations,
        "original_data_bytes": sum(
            1 + len(bytes.fromhex(record.packed_hex)) for record in records
        ),
        "used_data_bytes": used_data_bytes,
        "padding_bytes_between_ranges": padding_bytes,
        "used_bank_count": (used_data_bytes + BANK_SIZE - 1) // BANK_SIZE,
        "record_start_crossings": len(
            find_record_start_crossings(output_data, output_entries)
        ),
        "padded_data_size": len(output_data),
        "max_packed_record_bytes": max(encoded_lengths.values(), default=0),
        "max_decoded_record_bytes": max(
            (len(encoded_by_id[record.message_id]) for record in records),
            default=0,
        ),
        "codebook": {
            char: {"codepoint": f"U+{ord(char):04X}", "bytes": f"{pair[0]:02X} {pair[1]:02X}"}
            for char, pair in codebook.items()
        },
    }
    return bytes(output_header), bytes(output_data), output_misc, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hdr", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--misc", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--escape", type=lambda value: int(value, 0), default=DEFAULT_ESCAPE)
    parser.add_argument("--huffman-iterations", type=int, default=8)
    args = parser.parse_args()

    output_header, output_data, output_misc, report = build_files(
        args.hdr.read_bytes(),
        args.data.read_bytes(),
        args.misc.read_bytes(),
        read_translations(args.translations),
        args.escape,
        args.huffman_iterations,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "MSG.HDR").write_bytes(output_header)
    (args.output_dir / "MSG.DBS").write_bytes(output_data)
    (args.output_dir / "MISC.HDR").write_bytes(output_misc)
    (args.output_dir / "korean_codebook.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "codebook"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
