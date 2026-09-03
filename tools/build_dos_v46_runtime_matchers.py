#!/usr/bin/env python3
"""Build Wizardry VII DOS Korean v0.46 with original runtime matcher tables.

The Korean translation corpus historically localized slash-delimited input
matcher records such as ``PALUKE/ARMORY/`` and ``YES/SURE/OK/``.  Those records
are not display prose: the DOS event/NPC parser compares player input against
those ASCII tokens.  Localizing them makes valid English answers impossible and
can block progression (for example, the New City gate at message 15180).

v0.46 starts from the exact v0.45 package and restores only the manifest-listed
matcher records to their original decoded DOS bytes.  Every non-manifest record
keeps its v0.45 decoded byte stream exactly.  The current v0.45 MISC.HDR Huffman
tree and renderer/codebook are retained; MSG.HDR/MSG.DBS are simply repacked
with the restored records.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import zipfile
from collections import defaultdict
from pathlib import Path

from build_dos_messages import (
    MAX_DOS_DATA_SIZE,
    encode_huffman,
    huffman_codes,
    iter_translation_units,
)
from extract_gold_messages import BANK_SIZE, HEADER_ENTRIES, RangeEntry, extract_messages, parse_header

V45_ZIP_SHA256 = "c619cb206ab03c27e4d163881ef7425f98b6dc3ccf1ad20b35c7fd45a9b72ab9"
DEFAULT_MANIFEST = Path("data/dos_runtime_matchers.json")
NEW_CITY_GATE_MESSAGE_ID = 15180
NEW_CITY_GATE_SOURCE = "<0x02>PALUKE/<0x02>ARMORY/"

CONTROL_TOKEN_RE = re.compile(r"<0x[0-9A-Fa-f]{2}>")
MATCHER_ALLOWED_ASCII = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 /'-.+@:_$^&#!%?(),"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def looks_like_runtime_matcher_source(source_display: str) -> bool:
    """Conservative detector for original DOS slash-delimited matcher data."""
    if "/" not in source_display:
        return False
    cleaned = CONTROL_TOKEN_RE.sub("", source_display)
    letters = "".join(ch for ch in cleaned if ch.isalpha())
    if letters and letters != letters.upper():
        return False
    segments = [segment for segment in cleaned.split("/") if segment.strip()]
    if not (cleaned.endswith("/") or len(segments) >= 2):
        return False
    if not (source_display.startswith("<0x") or len(segments) >= 2):
        return False
    return all(ch in MATCHER_ALLOWED_ASCII for ch in cleaned)


def display_to_raw(source_display: str, codes: dict[int, tuple[int, ...]]) -> bytes:
    """Convert reversible <0xNN> display notation back to original DOS bytes."""
    output = bytearray()
    for unit in iter_translation_units(source_display):
        if isinstance(unit, int):
            value = unit
        else:
            cp = ord(unit)
            if cp > 0xFF:
                raise ValueError(f"matcher source contains non-byte character {unit!r}")
            value = cp
        if value not in codes:
            raise ValueError(
                f"matcher source byte 0x{value:02X} is absent from current MISC.HDR"
            )
        output.append(value)
    return bytes(output)


def load_manifest(path: Path) -> tuple[dict[int, str], dict[str, object]]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    rows = payload.get("records")
    if not isinstance(rows, list) or not rows:
        raise ValueError("runtime matcher manifest has no records")

    matchers: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("runtime matcher manifest record must be an object")
        message_id = int(row["message_id"])
        source_display = row["source_display"]
        if not isinstance(source_display, str):
            raise ValueError(f"message {message_id}: source_display must be text")
        if message_id in matchers:
            raise ValueError(f"duplicate runtime matcher message ID {message_id}")
        if not looks_like_runtime_matcher_source(source_display):
            raise ValueError(
                f"message {message_id}: source text no longer matches matcher invariant: "
                f"{source_display!r}"
            )
        matchers[message_id] = source_display

    if matchers.get(NEW_CITY_GATE_MESSAGE_ID) != NEW_CITY_GATE_SOURCE:
        raise ValueError("manifest does not contain the canonical New City gate matcher")

    metadata = {
        "path": str(path),
        "sha256": sha256(raw),
        "record_count": len(matchers),
    }
    return matchers, metadata


def pack_runtime_ranges(
    entries: list[RangeEntry],
    records_by_range: dict[int, list[object]],
    packed_by_id: dict[int, bytes],
) -> tuple[bytes, list[RangeEntry], int]:
    """Pack DOS ranges while allowing only the final payload to cross a bank.

    DS.EXE walks subindices by reading each preceding one-byte record length from
    the bank named by MSG.HDR. Therefore every record *start* in a range must
    remain in the entry bank, but the final payload itself may extend into the
    following bank. This matches the original DOS layout and is less restrictive
    than the older conservative whole-range packer.
    """
    output = bytearray()
    output_entries: list[RangeEntry] = []
    padding_bytes = 0

    for entry in entries:
        records = sorted(
            records_by_range.get(entry.range_index, []),
            key=lambda record: record.message_id,
        )
        expected_count = entry.id_span + 1
        if len(records) != expected_count:
            raise ValueError(
                f"range {entry.range_index}: expected {expected_count} records, "
                f"found {len(records)}"
            )
        sizes = [1 + len(packed_by_id[record.message_id]) for record in records]
        prefix_before_final = sum(sizes[:-1])
        if prefix_before_final >= BANK_SIZE:
            raise ValueError(
                f"range {entry.range_index}: preceding record starts consume "
                f"{prefix_before_final} bytes; cannot fit in one DOS bank"
            )

        current_offset = len(output) % BANK_SIZE
        if current_offset + prefix_before_final >= BANK_SIZE:
            gap = BANK_SIZE - current_offset
            output.extend(bytes(gap))
            padding_bytes += gap

        absolute = len(output)
        bank, bank_offset = divmod(absolute, BANK_SIZE)
        if bank > 0xFF:
            raise ValueError(f"range {entry.range_index}: bank {bank} exceeds DOS u8")
        output_entries.append(
            RangeEntry(entry.range_index, entry.start_id, bank_offset, entry.id_span, bank)
        )

        for record in records:
            record_start = len(output)
            if record_start // BANK_SIZE != bank:
                raise AssertionError(
                    f"range {entry.range_index}: record {record.message_id} starts "
                    f"in bank {record_start // BANK_SIZE}, expected {bank}"
                )
            packed = packed_by_id[record.message_id]
            output.append(len(packed))
            output.extend(packed)

    if len(output) > MAX_DOS_DATA_SIZE:
        raise ValueError(
            f"rebuilt MSG.DBS is {len(output)} bytes; DOS limit is {MAX_DOS_DATA_SIZE}"
        )
    return bytes(output), output_entries, padding_bytes


def restore_runtime_matchers(
    hdr_raw: bytes,
    data_raw: bytes,
    misc_raw: bytes,
    matchers: dict[int, str],
) -> tuple[bytes, bytes, dict[str, object]]:
    declared, entries, sentinel_count = parse_header(hdr_raw, "dos")
    records = extract_messages(data_raw, entries, misc_raw)
    by_id = {record.message_id: record for record in records}
    missing = sorted(set(matchers) - set(by_id))
    if missing:
        raise ValueError(f"matcher IDs absent from v0.45 message bank: {missing[:16]}")

    current_raw = {
        record.message_id: base64.b64decode(record.raw_base64) for record in records
    }
    codes = huffman_codes(misc_raw)
    restored_raw = {
        message_id: display_to_raw(source_display, codes)
        for message_id, source_display in matchers.items()
    }

    packed_by_id: dict[int, bytes] = {}
    records_by_range: dict[int, list[object]] = defaultdict(list)
    changed_ids: list[int] = []
    already_original_ids: list[int] = []

    for record in records:
        records_by_range[record.range_index].append(record)
        raw = restored_raw.get(record.message_id, current_raw[record.message_id])
        if record.message_id in restored_raw:
            if raw == current_raw[record.message_id]:
                already_original_ids.append(record.message_id)
            else:
                changed_ids.append(record.message_id)
        packed_by_id[record.message_id] = encode_huffman(raw, codes)

    rebuilt_data, rebuilt_entries, padding = pack_runtime_ranges(
        entries,
        records_by_range,
        packed_by_id,
    )
    used_data_bytes = len(rebuilt_data)
    rebuilt_data += bytes(MAX_DOS_DATA_SIZE - used_data_bytes)

    entry_struct = HEADER_ENTRIES["dos"]
    rebuilt_header = bytearray(struct.pack("<H", declared))
    for entry in rebuilt_entries:
        rebuilt_header.extend(
            entry_struct.pack(entry.start_id, entry.bank_offset, entry.id_span, entry.bank)
        )
    rebuilt_header.extend(bytes(sentinel_count * entry_struct.size))
    rebuilt_header = bytes(rebuilt_header)
    if len(rebuilt_header) != len(hdr_raw):
        raise AssertionError(
            f"MSG.HDR size changed: {len(hdr_raw)} -> {len(rebuilt_header)}"
        )

    verify_declared, verify_entries, verify_sentinels = parse_header(rebuilt_header, "dos")
    if (verify_declared, verify_sentinels) != (declared, sentinel_count):
        raise AssertionError("MSG.HDR range/sentinel structure changed unexpectedly")
    verified = extract_messages(rebuilt_data, verify_entries, misc_raw)
    verified_raw = {
        record.message_id: base64.b64decode(record.raw_base64) for record in verified
    }
    unexpected_changes: list[int] = []
    matcher_failures: list[int] = []
    for message_id, before in current_raw.items():
        after = verified_raw[message_id]
        expected = restored_raw.get(message_id, before)
        if after != expected:
            if message_id in restored_raw:
                matcher_failures.append(message_id)
            else:
                unexpected_changes.append(message_id)
    if matcher_failures or unexpected_changes:
        raise AssertionError(
            "decoded message verification failed: "
            f"matcher_failures={matcher_failures[:8]} "
            f"unexpected_changes={unexpected_changes[:8]}"
        )

    new_city_raw = verified_raw[NEW_CITY_GATE_MESSAGE_ID]
    expected_new_city = restored_raw[NEW_CITY_GATE_MESSAGE_ID]
    if new_city_raw != expected_new_city:
        raise AssertionError("New City gate matcher was not restored")

    return rebuilt_header, rebuilt_data, {
        "manifest_record_count": len(matchers),
        "changed_matcher_count": len(changed_ids),
        "already_original_matcher_count": len(already_original_ids),
        "changed_matcher_ids": changed_ids,
        "already_original_matcher_ids": already_original_ids,
        "decoded_non_matcher_changes": 0,
        "used_data_bytes": used_data_bytes,
        "padded_data_size": len(rebuilt_data),
        "padding_bytes_between_ranges": padding,
        "msg_hdr_size": len(rebuilt_header),
        "new_city_gate": {
            "message_id": NEW_CITY_GATE_MESSAGE_ID,
            "source_display": NEW_CITY_GATE_SOURCE,
            "restored_raw_hex": new_city_raw.hex(" ").upper(),
        },
    }


def annotate_codebook(raw: bytes, manifest_meta: dict[str, object], report: dict[str, object]) -> bytes:
    metadata = json.loads(raw.decode("utf-8"))
    metadata["runtime_matcher_restore"] = {
        "version": "v0.46",
        "reason": (
            "Slash-delimited NPC/event input matcher records are logic data. "
            "They remain original DOS ASCII so typed answers continue to match."
        ),
        "manifest_sha256": manifest_meta["sha256"],
        "manifest_record_count": manifest_meta["record_count"],
        "changed_matcher_count": report["changed_matcher_count"],
        "new_city_gate_message_id": NEW_CITY_GATE_MESSAGE_ID,
    }
    return json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")


def write_deterministic_zip(path: Path, payloads: dict[str, bytes]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 3, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v45-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    source_game = args.v45_dir / "DSAVANT"
    if not source_game.is_dir():
        raise FileNotFoundError(f"v0.45 DSAVANT directory not found: {source_game}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    matchers, manifest_meta = load_manifest(args.manifest)
    hdr_raw = (source_game / "MSG.HDR").read_bytes()
    data_raw = (source_game / "MSG.DBS").read_bytes()
    misc_raw = (source_game / "MISC.HDR").read_bytes()
    new_hdr, new_data, matcher_report = restore_runtime_matchers(
        hdr_raw, data_raw, misc_raw, matchers
    )

    payloads: dict[str, bytes] = {}
    for path in sorted(args.v45_dir.iterdir()):
        if path.is_file() and path.name.startswith("UI_V45_"):
            payloads[path.name] = path.read_bytes()
    for path in sorted(source_game.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if path.name == "MSG.HDR":
            data = new_hdr
        elif path.name == "MSG.DBS":
            data = new_data
        elif path.name == "korean_codebook.json":
            data = annotate_codebook(data, manifest_meta, matcher_report)
        payloads[f"DSAVANT/{path.name}"] = data

    report = {
        "format": "Wizardry VII DOS Korean v0.46 runtime matcher restore",
        "base_release": "v0.45",
        "base_zip_sha256": V45_ZIP_SHA256,
        "manifest": manifest_meta,
        "matcher_restore": matcher_report,
        "preserved": {
            "misc_hdr_sha256": sha256(misc_raw),
            "scenario_dbs_sha256": sha256((source_game / "SCENARIO.DBS").read_bytes()),
            "vbfont0_vga_sha256": sha256((source_game / "VBFONT0.VGA").read_bytes()),
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V46_REPORT.json"] = report_raw

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    (args.output_dir / "UI_V46_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
