#!/usr/bin/env python3
"""Extract Wizardry 7 Gold messages without modifying the game files.

MSG.HDR layout (little-endian):
    u16 range_count
    range_count * [u16 start_id, u16 bank_offset, u8 id_span, u16 bank]
    optional all-zero 7-byte sentinel entries

MSG.GLD is split into logical 1024-byte banks. Each referenced message is a
one-byte length followed by that many raw text bytes. Records may cross a bank
boundary, so bounds checks are against the complete GLD file.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import struct
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


BANK_SIZE = 1024
HEADER_ENTRY = struct.Struct("<HHBH")


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
    bank: int
    bank_offset: int
    absolute_offset: int
    record_length: int
    source_text: str
    source_display: str
    raw_base64: str
    raw_hex: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def display_bytes(raw: bytes) -> str:
    """Return a single-line, reversible-friendly view for translation work."""
    out: list[str] = []
    for value in raw:
        if 0x20 <= value <= 0x7E:
            out.append(chr(value))
        else:
            out.append(f"<0x{value:02X}>")
    return "".join(out)


def decode_source(raw: bytes) -> str:
    """Decode printable Western text while preserving byte values losslessly."""
    return raw.decode("latin-1")


def parse_header(raw: bytes) -> tuple[int, list[RangeEntry], int]:
    if len(raw) < 2:
        raise ValueError("MSG.HDR is shorter than its 2-byte range count")

    declared_count = struct.unpack_from("<H", raw, 0)[0]
    required_size = 2 + declared_count * HEADER_ENTRY.size
    if len(raw) < required_size:
        raise ValueError(
            f"MSG.HDR declares {declared_count} ranges but is only {len(raw)} bytes"
        )

    entries: list[RangeEntry] = []
    cursor = 2
    for index in range(declared_count):
        start_id, bank_offset, id_span, bank = HEADER_ENTRY.unpack_from(raw, cursor)
        entries.append(
            RangeEntry(
                range_index=index,
                start_id=start_id,
                bank_offset=bank_offset,
                id_span=id_span,
                bank=bank,
            )
        )
        cursor += HEADER_ENTRY.size

    trailer = raw[cursor:]
    if len(trailer) % HEADER_ENTRY.size:
        raise ValueError(
            f"MSG.HDR has an unexpected {len(trailer)}-byte trailer"
        )
    if any(trailer):
        raise ValueError("MSG.HDR trailer contains non-zero data")

    return declared_count, entries, len(trailer) // HEADER_ENTRY.size


def extract_messages(gld: bytes, entries: list[RangeEntry]) -> list[MessageRecord]:
    records: list[MessageRecord] = []
    bank_count = (len(gld) + BANK_SIZE - 1) // BANK_SIZE

    for entry in entries:
        if entry.bank >= bank_count:
            raise ValueError(
                f"range {entry.range_index}: bank {entry.bank} is outside {bank_count} banks"
            )
        if entry.bank_offset >= BANK_SIZE:
            raise ValueError(
                f"range {entry.range_index}: bank offset {entry.bank_offset} >= {BANK_SIZE}"
            )

        cursor = entry.bank * BANK_SIZE + entry.bank_offset
        for delta in range(entry.id_span + 1):
            message_id = entry.start_id + delta
            if cursor >= len(gld):
                raise ValueError(
                    f"message {message_id}: record offset {cursor} is outside MSG.GLD"
                )

            record_length = gld[cursor]
            raw_start = cursor + 1
            raw_end = raw_start + record_length
            if raw_end > len(gld):
                raise ValueError(
                    f"message {message_id}: {record_length}-byte record exceeds MSG.GLD"
                )

            payload = gld[raw_start:raw_end]
            records.append(
                MessageRecord(
                    range_index=entry.range_index,
                    message_id=message_id,
                    bank=cursor // BANK_SIZE,
                    bank_offset=cursor % BANK_SIZE,
                    absolute_offset=cursor,
                    record_length=record_length,
                    source_text=decode_source(payload),
                    source_display=display_bytes(payload),
                    raw_base64=base64.b64encode(payload).decode("ascii"),
                    raw_hex=payload.hex(" ").upper(),
                )
            )
            cursor = raw_end

    return records


def write_json(path: Path, records: list[MessageRecord], metadata: dict) -> None:
    payload = {
        "metadata": metadata,
        "records": [asdict(record) for record in records],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, records: list[MessageRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def write_csv(path: Path, records: list[MessageRecord]) -> None:
    fields = [
        "message_id",
        "range_index",
        "bank",
        "bank_offset",
        "absolute_offset",
        "record_length",
        "source_text",
        "translation",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "message_id": record.message_id,
                    "range_index": record.range_index,
                    "bank": record.bank,
                    "bank_offset": record.bank_offset,
                    "absolute_offset": record.absolute_offset,
                    "record_length": record.record_length,
                    "source_text": record.source_display,
                    "translation": "",
                    "notes": "",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hdr", type=Path, required=True, help="Path to MSG.HDR")
    parser.add_argument("--gld", type=Path, required=True, help="Path to MSG.GLD")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    hdr = args.hdr.read_bytes()
    gld = args.gld.read_bytes()
    declared_count, entries, sentinel_count = parse_header(hdr)
    records = extract_messages(gld, entries)

    duplicate_ids = sorted(
        message_id
        for message_id, count in Counter(r.message_id for r in records).items()
        if count > 1
    )
    metadata = {
        "format": "Wizardry 7 Gold MSG.HDR/MSG.GLD",
        "header_file": args.hdr.name,
        "header_size": len(hdr),
        "header_sha256": sha256(hdr),
        "data_file": args.gld.name,
        "data_size": len(gld),
        "data_sha256": sha256(gld),
        "bank_size": BANK_SIZE,
        "bank_count": len(gld) // BANK_SIZE,
        "declared_range_count": declared_count,
        "zero_sentinel_count": sentinel_count,
        "message_record_count": len(records),
        "nonempty_record_count": sum(bool(r.record_length) for r in records),
        "duplicate_message_ids": duplicate_ids,
        "control_byte_notation": "Non-printable bytes are shown as <0xNN> in CSV source_text.",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "messages.json", records, metadata)
    write_jsonl(args.output_dir / "messages.jsonl", records)
    write_csv(args.output_dir / "messages_for_translation.csv", records)
    (args.output_dir / "extraction_report.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
