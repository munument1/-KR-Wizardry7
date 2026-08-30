#!/usr/bin/env python3
"""Patch selected DOS messages while preserving the installed Korean codebook.

Unlike ``build_dos_messages.py``, this utility does not retrain the Huffman
tree or reassign Korean character pairs.  Unchanged records retain their
packed bytes, changed records are encoded with the supplied MISC.HDR and
codebook, and complete ranges are repacked on safe 0x400-byte boundaries.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from build_dos_messages import (
    MAX_DOS_DATA_SIZE,
    encode_huffman,
    encode_translation,
    find_record_start_crossings,
    huffman_codes,
    pack_message_ranges,
    read_translations,
)
from extract_gold_messages import HEADER_ENTRIES, extract_messages, parse_header, sha256


def load_codebook(path: Path) -> dict[str, tuple[int, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("codebook")
    if not isinstance(entries, dict):
        raise ValueError("codebook JSON does not contain a codebook object")

    result: dict[str, tuple[int, int]] = {}
    for char, metadata in entries.items():
        encoded = metadata.get("bytes") if isinstance(metadata, dict) else metadata
        if not isinstance(encoded, str):
            raise ValueError(f"codebook entry {char!r} has no byte pair")
        parts = encoded.split()
        if len(parts) != 2:
            raise ValueError(f"codebook entry {char!r} is not a two-byte pair")
        result[char] = (int(parts[0], 16), int(parts[1], 16))
    return result


def build_patched_files(
    hdr: bytes,
    data: bytes,
    misc: bytes,
    codebook: dict[str, tuple[int, int]],
    replacements: dict[int, str],
) -> tuple[bytes, bytes, dict]:
    declared, entries, sentinel_count = parse_header(hdr, "dos")
    records = extract_messages(data, entries, misc)
    record_by_id = {record.message_id: record for record in records}
    unknown = sorted(set(replacements) - set(record_by_id))
    if unknown:
        raise ValueError(f"unknown message IDs: {unknown}")

    codes = huffman_codes(misc)
    packed_by_id = {
        record.message_id: bytes.fromhex(record.packed_hex) for record in records
    }
    changed: dict[str, dict[str, object]] = {}
    for message_id, translation in sorted(replacements.items()):
        raw = encode_translation(translation, codes, codebook)
        packed = encode_huffman(raw, codes)
        old_packed = packed_by_id[message_id]
        packed_by_id[message_id] = packed
        changed[str(message_id)] = {
            "translation": translation,
            "old_packed_bytes": len(old_packed),
            "new_packed_bytes": len(packed),
        }

    records_by_range: dict[int, list] = {}
    for record in records:
        records_by_range.setdefault(record.range_index, []).append(record)
    rebuilt_data, rebuilt_entries, padding = pack_message_ranges(
        entries, records_by_range, packed_by_id
    )
    used_data_bytes = len(rebuilt_data)
    rebuilt_data += bytes(MAX_DOS_DATA_SIZE - used_data_bytes)

    entry_struct = HEADER_ENTRIES["dos"]
    rebuilt_header = bytearray(struct.pack("<H", declared))
    for entry in rebuilt_entries:
        rebuilt_header.extend(
            entry_struct.pack(
                entry.start_id, entry.bank_offset, entry.id_span, entry.bank
            )
        )
    rebuilt_header.extend(bytes(sentinel_count * entry_struct.size))
    if len(rebuilt_header) != len(hdr):
        raise AssertionError("rebuilt MSG.HDR size changed")

    violations = find_record_start_crossings(rebuilt_data, rebuilt_entries)
    if violations:
        raise AssertionError(f"rebuilt message layer has {len(violations)} crossings")

    # Decode every rebuilt record.  This catches malformed lengths, Huffman
    # payloads, header offsets, and unsafe range packing before installation.
    verified_records = extract_messages(rebuilt_data, rebuilt_entries, misc)
    if len(verified_records) != len(records):
        raise AssertionError("rebuilt record count changed")

    report = {
        "format": "Wizardry VII DOS fixed-codebook message patch",
        "record_count": len(verified_records),
        "changed": changed,
        "huffman_tree_preserved": True,
        "codebook_preserved": True,
        "unchanged_packed_records_preserved": True,
        "used_data_bytes": used_data_bytes,
        "padding_bytes_between_ranges": padding,
        "record_start_crossings": 0,
        "hashes": {
            "MSG.HDR": sha256(bytes(rebuilt_header)),
            "MSG.DBS": sha256(rebuilt_data),
            "MISC.HDR": sha256(misc),
        },
    }
    return bytes(rebuilt_header), rebuilt_data, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hdr", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--misc", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    parser.add_argument(
        "--message-id",
        type=int,
        action="append",
        required=True,
        help="message ID to patch; repeat when using --translations",
    )
    translation_source = parser.add_mutually_exclusive_group(required=True)
    translation_source.add_argument("--translation")
    translation_source.add_argument(
        "--translations",
        type=Path,
        help="UTF-8 CSV; use the translation column for --message-id",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    hdr = args.hdr.read_bytes()
    data = args.data.read_bytes()
    misc = args.misc.read_bytes()
    codebook_raw = args.codebook.read_bytes()
    replacements: dict[int, str] = {}
    if args.translations is not None:
        rows = read_translations(args.translations)
        for message_id in args.message_id:
            try:
                translation = rows[message_id]["translation"]
            except KeyError as exc:
                raise ValueError(
                    f"message {message_id} has no translation in {args.translations}"
                ) from exc
            if not translation:
                raise ValueError(f"message {message_id} has an empty translation")
            replacements[message_id] = translation
    else:
        if len(args.message_id) != 1:
            raise ValueError("--translation supports exactly one --message-id")
        replacements[args.message_id[0]] = args.translation

    output_header, output_data, report = build_patched_files(
        hdr,
        data,
        misc,
        load_codebook(args.codebook),
        replacements,
    )

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "MSG.HDR").write_bytes(output_header)
    (args.output_dir / "MSG.DBS").write_bytes(output_data)
    (args.output_dir / "MISC.HDR").write_bytes(misc)
    (args.output_dir / "korean_codebook.json").write_bytes(codebook_raw)
    (args.output_dir / "MESSAGE_PATCH_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
