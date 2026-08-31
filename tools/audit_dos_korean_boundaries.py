#!/usr/bin/env python3
"""Audit DOS message paths for Korean three-byte boundary hazards."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import zipfile
from pathlib import Path

from build_dos_messages import decode_translation, encode_translation, huffman_codes
from extract_gold_messages import extract_messages, parse_header
from patch_dos_message_fixed_codebook import load_codebook


MESSAGE_LOADER = 0x0582
FIXED_SLOTS = {
    "main_menu_text": (range(1000, 1009), 19),
    "pause_menu_text": (range(2200, 2206), 19),
    "party_professions": (range(120, 134), 12),
    "creation_stat_labels": (range(204, 212), 9),
    "skill_categories": (range(600, 605), 19),
    "skill_names": (range(5500, 5535), 19),
}


def loader_calls(data: bytes, origin: int) -> list[int]:
    return [
        offset
        for offset in range(len(data) - 2)
        if data[offset] == 0xE8
        and (
            origin
            + offset
            + 3
            + int.from_bytes(data[offset + 1 : offset + 3], "little", signed=True)
        )
        & 0xFFFF
        == MESSAGE_LOADER
    ]


def nearest_stack_destination(data: bytes, call: int) -> int | None:
    destination = None
    for offset in range(max(0, call - 32), call):
        if data[offset : offset + 2] == b"\x8D\x46":
            destination = int.from_bytes(
                data[offset + 2 : offset + 3], "little", signed=True
            )
        elif data[offset : offset + 2] == b"\x8D\x86":
            destination = int.from_bytes(
                data[offset + 2 : offset + 4], "little", signed=True
            )
    return destination


def forced_terminators(
    data: bytes, origin: int, file_bias: int
) -> list[dict[str, int]]:
    results: list[dict[str, int]] = []
    for call in loader_calls(data, origin):
        destination = nearest_stack_destination(data, call)
        if destination is None:
            continue
        for offset in range(call + 3, min(len(data) - 4, call + 28)):
            written = None
            if data[offset : offset + 2] == b"\xC6\x46" and data[offset + 3] == 0:
                written = int.from_bytes(
                    data[offset + 2 : offset + 3], "little", signed=True
                )
            elif data[offset : offset + 2] == b"\xC6\x86" and data[offset + 4] == 0:
                written = int.from_bytes(
                    data[offset + 2 : offset + 4], "little", signed=True
                )
            if written is not None and 0 <= written - destination <= 80:
                results.append(
                    {
                        "message_call_file_offset": call + file_bias,
                        "terminator_file_offset": offset + file_bias,
                        "buffer_offset": written - destination,
                    }
                )
    return results


def load_records(directory: Path):
    misc = (directory / "MISC.HDR").read_bytes()
    _, entries, _ = parse_header((directory / "MSG.HDR").read_bytes(), "dos")
    return misc, extract_messages((directory / "MSG.DBS").read_bytes(), entries, misc)


def audit(
    game_dir: Path, translations_path: Path, original_zip: Path
) -> dict:
    misc, records = load_records(game_dir)
    records_by_id = {record.message_id: record for record in records}
    codebook = load_codebook(game_dir / "korean_codebook.json")
    codes = huffman_codes(misc)

    invalid_streams = []
    for record in records:
        try:
            decode_translation(base64.b64decode(record.raw_base64), codebook)
        except ValueError as exc:
            invalid_streams.append({"message_id": record.message_id, "error": str(exc)})

    with translations_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    translation_rows = {int(row["message_id"]): row for row in rows}
    unencodable = []
    for message_id, row in translation_rows.items():
        translation = row.get("translation", "")
        if not translation:
            continue
        try:
            encode_translation(translation, codes, codebook)
        except ValueError as exc:
            unencodable.append({"message_id": message_id, "error": str(exc)})

    fixed_slots = {}
    fixed_slot_violations = []
    for name, (message_ids, capacity) in FIXED_SLOTS.items():
        lengths = {
            message_id: len(base64.b64decode(records_by_id[message_id].raw_base64))
            for message_id in message_ids
        }
        violations = [
            {"message_id": message_id, "length": length, "capacity": capacity}
            for message_id, length in lengths.items()
            if length > capacity
        ]
        fixed_slot_violations.extend({"group": name, **item} for item in violations)
        fixed_slots[name] = {
            "capacity_excluding_nul": capacity,
            "maximum_encoded_bytes": max(lengths.values()),
            "violations": violations,
        }

    with zipfile.ZipFile(original_zip) as archive:
        original_hdr = archive.read("DSAVANT/MSG.HDR")
        original_data = archive.read("DSAVANT/MSG.DBS")
        original_misc = archive.read("DSAVANT/MISC.HDR")
    _, original_entries, _ = parse_header(original_hdr, "dos")
    original_records = extract_messages(original_data, original_entries, original_misc)
    source_mismatches = []
    untranslated_escape_controls = []
    for record in original_records:
        row = translation_rows.get(record.message_id)
        if not row or not row.get("translation"):
            applicable = False
        else:
            expected = row.get("source_text", "")
            applicable = not expected or expected == record.source_display
            if not applicable:
                source_mismatches.append(record.message_id)
        raw = base64.b64decode(record.raw_base64)
        if 0x17 in raw and not applicable:
            untranslated_escape_controls.append(record.message_id)

    binaries = {}
    total_loader_calls = 0
    terminators = []
    for path in sorted(game_dir.iterdir()):
        if path.name == "DS.EXE":
            data = path.read_bytes()[0x200:]
            origin, bias = 0, 0x200
        elif path.suffix.upper() == ".OVR":
            data = path.read_bytes()
            origin, bias = 0x5047, 0
        else:
            continue
        calls = loader_calls(data, origin)
        found = forced_terminators(data, origin, bias)
        total_loader_calls += len(calls)
        binaries[path.name] = {
            "message_loader_calls": len(calls),
            "forced_terminators": found,
        }
        terminators.extend({"file": path.name, **item} for item in found)

    expected_terminators = [
        {
            "file": "DS.EXE",
            "message_call_file_offset": 0x1E5C,
            "terminator_file_offset": 0x1E62,
            "buffer_offset": 12,
        }
    ]
    terminator_mismatch = terminators != expected_terminators

    fixed_draw_checks = {
        "VBASE_profession_abbreviation_bytes": (
            game_dir / "VBASE.OVR"
        ).read_bytes()[0x5FFF:0x6002].hex(" ").upper(),
        "VPCMK_profession_abbreviation_bytes": (
            game_dir / "VPCMK.OVR"
        ).read_bytes()[0x69D1:0x69D4].hex(" ").upper(),
        "VPCVW_ascii_table_lengths": {
            str(message_id): len(base64.b64decode(records_by_id[message_id].raw_base64))
            for message_id in (454, 455, 456)
        },
    }
    fixed_draw_safe = (
        fixed_draw_checks["VBASE_profession_abbreviation_bytes"] == "3D 03 00"
        and fixed_draw_checks["VPCMK_profession_abbreviation_bytes"] == "3D 03 00"
        and fixed_draw_checks["VPCVW_ascii_table_lengths"]
        == {"454": 11, "455": 2, "456": 14}
        and all(
            value < 0x80
            for message_id in (454, 455, 456)
            for value in base64.b64decode(records_by_id[message_id].raw_base64)
        )
    )

    issue_count = sum(
        (
            len(invalid_streams),
            len(unencodable),
            len(fixed_slot_violations),
            len(source_mismatches),
            len(untranslated_escape_controls),
            int(terminator_mismatch),
            int(not fixed_draw_safe),
        )
    )
    return {
        "format": "Wizardry VII DOS Korean three-byte boundary audit",
        "record_count": len(records),
        "translation_count": sum(bool(row.get("translation")) for row in rows),
        "valid_custom_streams": len(records) - len(invalid_streams),
        "invalid_custom_streams": invalid_streams,
        "unencodable_translations": unencodable,
        "fixed_slots": fixed_slots,
        "source_mismatch_ids": source_mismatches,
        "untranslated_original_escape_control_ids": untranslated_escape_controls,
        "binary_scan": {
            "files": binaries,
            "message_loader_call_total": total_loader_calls,
            "forced_terminators": terminators,
            "expected_forced_terminators": expected_terminators,
            "fixed_draw_checks": fixed_draw_checks,
        },
        "issue_count": issue_count,
        "passed": issue_count == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.game_dir, args.translations, args.original_zip)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
