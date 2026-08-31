#!/usr/bin/env python3
"""Repair MSG.HDR/MSG.DBS bank placement without changing decoded messages.

This is useful for an already translated DOS message layer whose Huffman
payloads are known-good.  It preserves MISC.HDR and every packed record byte,
then repacks complete MSG.HDR ranges so the DOS subindex walker never crosses
the current 0x400-byte bank while reading preceding record lengths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from build_dos_messages import (
    BANK_SIZE,
    MAX_DOS_DATA_SIZE,
    find_record_start_crossings,
    pack_message_ranges,
)
from extract_gold_messages import MessageRecord, extract_messages, parse_header


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hdr", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--misc", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    header = args.hdr.read_bytes()
    data = args.data.read_bytes()
    misc = args.misc.read_bytes()
    declared, entries, sentinel_count = parse_header(header, "dos")
    records = extract_messages(data, entries, misc)
    records_by_range: dict[int, list[MessageRecord]] = {}
    for record in records:
        records_by_range.setdefault(record.range_index, []).append(record)
    packed_by_id = {
        record.message_id: bytes.fromhex(record.packed_hex) for record in records
    }

    rebuilt_data, rebuilt_entries, padding_bytes = pack_message_ranges(
        entries,
        records_by_range,
        packed_by_id,
    )
    entry_struct = struct.Struct("<HHBB")
    rebuilt_header = bytearray(struct.pack("<H", declared))
    for entry in rebuilt_entries:
        rebuilt_header.extend(
            entry_struct.pack(
                entry.start_id,
                entry.bank_offset,
                entry.id_span,
                entry.bank,
            )
        )
    rebuilt_header.extend(bytes(sentinel_count * entry_struct.size))
    if len(rebuilt_header) != len(header):
        raise ValueError(
            f"rebuilt MSG.HDR is {len(rebuilt_header)} bytes; expected {len(header)}"
        )

    rebuilt_data_padded = rebuilt_data + bytes(MAX_DOS_DATA_SIZE - len(rebuilt_data))
    violations = find_record_start_crossings(rebuilt_data_padded, rebuilt_entries)
    if violations:
        raise AssertionError(f"repacked data still has {len(violations)} crossings")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "MSG.HDR").write_bytes(bytes(rebuilt_header))
    (args.output_dir / "MSG.DBS").write_bytes(rebuilt_data_padded)
    (args.output_dir / "MISC.HDR").write_bytes(misc)
    report = {
        "source": {
            "msg_hdr_sha256": sha256(header),
            "msg_dbs_sha256": sha256(data),
            "misc_hdr_sha256": sha256(misc),
        },
        "output": {
            "msg_hdr_sha256": sha256(bytes(rebuilt_header)),
            "msg_dbs_sha256": sha256(rebuilt_data_padded),
            "misc_hdr_sha256": sha256(misc),
        },
        "declared_range_count": declared,
        "record_count": len(records),
        "used_data_bytes": len(rebuilt_data),
        "used_bank_count": (len(rebuilt_data) + BANK_SIZE - 1) // BANK_SIZE,
        "padding_bytes_between_ranges": padding_bytes,
        "record_start_crossings": len(violations),
        "decoded_payloads_preserved": True,
    }
    (args.output_dir / "REPACK_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
