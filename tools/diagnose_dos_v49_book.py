#!/usr/bin/env python3
"""Statically validate v0.48 DOS message records for the reported book crash.

The check is intentionally broad: it proves the MSG bank-walk invariant,
Huffman-decodes every referenced record, validates the Korean escape stream,
and reports unusually large records for later runtime correlation.  It does
not claim that every book uses MSG.DBS; a clean report narrows the crash to a
book/item-specific overlay or destination-buffer path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_dos_messages import DEFAULT_ESCAPE, find_record_start_crossings
from extract_gold_messages import extract_messages, parse_header


def validate_escape_stream(raw: bytes, escape: int = DEFAULT_ESCAPE) -> list[str]:
    errors: list[str] = []
    cursor = 0
    while cursor < len(raw):
        value = raw[cursor]
        cursor += 1
        if value != escape:
            continue
        if cursor >= len(raw):
            errors.append("terminal escape byte")
            break
        if raw[cursor] == escape:
            cursor += 1
            continue
        if cursor + 1 >= len(raw):
            errors.append("truncated Korean escape pair")
            break
        cursor += 2
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dsavant", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    hdr = (args.dsavant / "MSG.HDR").read_bytes()
    dbs = (args.dsavant / "MSG.DBS").read_bytes()
    misc = (args.dsavant / "MISC.HDR").read_bytes()

    declared, entries, trailer_slots = parse_header(hdr, "dos")
    crossings = find_record_start_crossings(dbs, entries)

    decode_error: str | None = None
    records = []
    try:
        records = extract_messages(dbs, entries, huffman_table=misc)
    except Exception as exc:  # diagnostic should preserve the exact first failure
        decode_error = f"{type(exc).__name__}: {exc}"

    malformed: list[dict[str, object]] = []
    lengths: list[dict[str, object]] = []
    escaped_records = 0
    if decode_error is None:
        for record in records:
            raw = __import__("base64").b64decode(record.raw_base64)
            errors = validate_escape_stream(raw)
            if DEFAULT_ESCAPE in raw:
                escaped_records += 1
            if errors:
                malformed.append({
                    "message_id": record.message_id,
                    "range_index": record.range_index,
                    "decoded_length": len(raw),
                    "errors": errors,
                    "raw_hex": record.raw_hex,
                })
            lengths.append({
                "message_id": record.message_id,
                "range_index": record.range_index,
                "decoded_length": len(raw),
                "packed_length": record.record_length,
                "bank": record.bank,
                "bank_offset": record.bank_offset,
                "preview": record.source_display[:180],
            })

    lengths.sort(key=lambda row: (row["decoded_length"], row["packed_length"]), reverse=True)
    report = {
        "declared_ranges": declared,
        "trailer_zero_slots": trailer_slots,
        "message_count": len(records),
        "decode_error": decode_error,
        "record_start_crossings": [
            {
                "range_index": item[0],
                "message_id": item[1],
                "entry_bank": item[2],
                "actual_bank": item[3],
            }
            for item in crossings
        ],
        "malformed_escape_records": malformed,
        "records_containing_escape": escaped_records,
        "top_longest_decoded_records": lengths[:40],
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    # Make structural regressions fail CI while keeping long-record findings
    # informational until correlated with a reproducible book.
    if decode_error or crossings or malformed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
