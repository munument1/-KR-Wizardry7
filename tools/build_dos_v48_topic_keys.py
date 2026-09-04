#!/usr/bin/env python3
"""Build Wizardry VII DOS Korean v0.48 with NPC/global topic keys restored.

v0.47 repaired the two parser grammar layers (canonical tokens and synonym
records), but VMNPC.OVR also loads a third layer: the global and per-NPC
knowledge/topic key tables.  Those tables are laid out as one key every five
message IDs; the key is runtime lookup data while key+1..key+4 are display
responses and metadata.  Translating the keys breaks topic lookup.  Paluke's
PRISONER key at 9220, for example, was translated to Korean, so RUMORS could be
lexically recognized yet still fall through to the generic "what?" reply.

v0.48 starts from the exact v0.47 package and restores all parser/runtime logic
records plus all 620 topic keys to their original DOS byte strings.  All
non-protected decoded messages remain byte-identical to v0.47.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import build_dos_v46_runtime_matchers as v46
import build_dos_v47_parser_core as v47

V47_ZIP_SHA256 = "2ddc66df9b813bd46b2781b451adf699d393dff09c9a7bf09b2e1fb8b058cd9c"
DEFAULT_TOPIC_MANIFEST = Path("data/dos_topic_key_records.json")
EXPECTED_TOPIC_KEYS = 620
EXPECTED_PREVIOUS_LOGIC = 250
EXPECTED_ALL_LOGIC = 870
EXPECTED_NEW_TOPIC_CHANGES = 613
EXPECTED_ALREADY_ORIGINAL_TOPIC_KEYS = 7
PALUKE_PRISONER_ID = 9220
PALUKE_PRISONER_SOURCE = " PRISONER%"
PALUKE_RUMOR_RESPONSE_ID = 9221
RUMORS_SYNONYM_ID = 7177
RUMORS_SYNONYM_SOURCE = "WHAT TELL YOU/RUMOR/RUMORS/NEWS/INFO/HINT/HINTS/"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _range_ids(start: int, end: int, step: int) -> set[int]:
    if step <= 0 or end < start or (end - start) % step:
        raise ValueError(f"invalid topic-key range {start}..{end} step {step}")
    return set(range(start, end + 1, step))


def load_topic_manifest(path: Path) -> tuple[dict[int, str], dict[str, object]]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("record_count") != EXPECTED_TOPIC_KEYS:
        raise ValueError("topic-key manifest record_count changed")
    global_range = payload.get("global_range")
    npc_blocks = payload.get("npc_blocks")
    rows = payload.get("records")
    fixtures = payload.get("fixtures")
    if not isinstance(global_range, list) or len(global_range) != 3:
        raise ValueError("topic-key manifest requires one global_range")
    if not isinstance(npc_blocks, list) or not isinstance(rows, list):
        raise ValueError("topic-key manifest requires npc_blocks and records")
    if not isinstance(fixtures, dict):
        raise ValueError("topic-key manifest requires fixtures")

    expected_ids = _range_ids(*(int(v) for v in global_range))
    normalized_blocks: list[list[int]] = []
    for block in npc_blocks:
        if not isinstance(block, list) or len(block) != 3:
            raise ValueError("invalid NPC topic-key block")
        start, end, step = (int(v) for v in block)
        expected_ids.update(_range_ids(start, end, step))
        normalized_blocks.append([start, end, step])

    records: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("topic-key record must be [message_id, source_display]")
        message_id = int(row[0])
        source_display = row[1]
        if not isinstance(source_display, str):
            raise ValueError(f"message {message_id}: source_display must be text")
        if message_id in records:
            raise ValueError(f"duplicate topic-key message ID {message_id}")
        records[message_id] = source_display

    if set(records) != expected_ids or len(records) != EXPECTED_TOPIC_KEYS:
        missing = sorted(expected_ids - set(records))
        extra = sorted(set(records) - expected_ids)
        raise ValueError(
            f"topic-key IDs/count changed: count={len(records)} missing={missing[:8]} extra={extra[:8]}"
        )

    required_fixtures = {
        "global_lore": (8310, '"LORE@'),
        "paluke_armor": (9210, '"ARMOR%'),
        "paluke_prisoner": (PALUKE_PRISONER_ID, PALUKE_PRISONER_SOURCE),
        "dungore_black_market": (9040, "<0x1F>BLACK MARKET%"),
    }
    for name, (message_id, source_display) in required_fixtures.items():
        row = fixtures.get(name)
        if row != [message_id, source_display]:
            raise ValueError(f"topic-key fixture {name} changed: {row!r}")
        if records[message_id] != source_display:
            raise ValueError(f"topic-key record {message_id} disagrees with fixture {name}")

    return records, {
        "path": str(path),
        "sha256": sha256(raw),
        "record_count": len(records),
        "global_range": [int(v) for v in global_range],
        "npc_blocks": normalized_blocks,
        "fixtures": fixtures,
    }


def load_all_logic_records(
    runtime_manifest: Path,
    core_manifest: Path,
    topic_manifest: Path,
) -> tuple[dict[int, str], dict[str, object], set[int], set[int]]:
    previous, previous_meta = v47.load_combined_logic_records(runtime_manifest, core_manifest)
    topics, topic_meta = load_topic_manifest(topic_manifest)
    if len(previous) != EXPECTED_PREVIOUS_LOGIC:
        raise ValueError(f"v0.47 protected logic count changed: {len(previous)}")
    overlap = sorted(set(previous) & set(topics))
    if overlap:
        raise ValueError(f"topic keys overlap previous logic records: {overlap[:8]}")
    combined = dict(previous)
    combined.update(topics)
    if len(combined) != EXPECTED_ALL_LOGIC:
        raise AssertionError("combined protected logic count changed")
    if previous[RUMORS_SYNONYM_ID] != RUMORS_SYNONYM_SOURCE:
        raise ValueError("RUMORS synonym fixture changed")
    if topics[PALUKE_PRISONER_ID] != PALUKE_PRISONER_SOURCE:
        raise ValueError("Paluke PRISONER topic fixture changed")
    return combined, {
        "previous_logic": previous_meta,
        "topic_keys": topic_meta,
        "combined_record_count": len(combined),
    }, set(previous), set(topics)


def annotate_codebook(raw: bytes, meta: dict[str, object], report: dict[str, object]) -> bytes:
    payload = json.loads(raw.decode("utf-8"))
    payload["topic_key_restore"] = {
        "version": "v0.48",
        "reason": (
            "VMNPC knowledge/topic names are runtime lookup keys. Keep keys original DOS ASCII/control bytes; "
            "localize only their response records."
        ),
        "topic_key_count": EXPECTED_TOPIC_KEYS,
        "combined_protected_logic_count": EXPECTED_ALL_LOGIC,
        "topic_manifest_sha256": meta["topic_keys"]["sha256"],
        "newly_restored_topic_keys": report["newly_restored_topic_keys"],
        "paluke_prisoner_message_id": PALUKE_PRISONER_ID,
        "rumors_synonym_message_id": RUMORS_SYNONYM_ID,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def write_deterministic_zip(path: Path, payloads: dict[str, bytes]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v47-dir", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, default=v47.DEFAULT_RUNTIME_MANIFEST)
    parser.add_argument("--core-manifest", type=Path, default=v47.DEFAULT_CORE_MANIFEST)
    parser.add_argument("--topic-manifest", type=Path, default=DEFAULT_TOPIC_MANIFEST)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    source_game = args.v47_dir / "DSAVANT"
    if not source_game.is_dir():
        raise FileNotFoundError(f"v0.47 DSAVANT directory not found: {source_game}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    logic, manifest_meta, previous_ids, topic_ids = load_all_logic_records(
        args.runtime_manifest, args.core_manifest, args.topic_manifest
    )
    hdr_raw = (source_game / "MSG.HDR").read_bytes()
    data_raw = (source_game / "MSG.DBS").read_bytes()
    misc_raw = (source_game / "MISC.HDR").read_bytes()
    new_hdr, new_data, restore_report = v46.restore_runtime_matchers(
        hdr_raw, data_raw, misc_raw, logic
    )

    changed_ids = set(restore_report["changed_matcher_ids"])
    original_ids = set(restore_report["already_original_matcher_ids"])
    changed_topics = changed_ids & topic_ids
    original_topics = original_ids & topic_ids
    changed_previous = changed_ids & previous_ids
    original_previous = original_ids & previous_ids
    if changed_previous:
        raise ValueError(f"v0.47 logic unexpectedly changed in v0.48: {sorted(changed_previous)[:8]}")
    if len(original_previous) != EXPECTED_PREVIOUS_LOGIC:
        raise ValueError(f"expected 250 already-restored v0.47 logic records, found {len(original_previous)}")
    if len(changed_topics) != EXPECTED_NEW_TOPIC_CHANGES:
        raise ValueError(f"expected 613 translated topic keys to restore, found {len(changed_topics)}")
    if len(original_topics) != EXPECTED_ALREADY_ORIGINAL_TOPIC_KEYS:
        raise ValueError(f"expected 7 topic keys already original, found {len(original_topics)}")

    topic_report = {
        "topic_key_count": EXPECTED_TOPIC_KEYS,
        "newly_restored_topic_keys": len(changed_topics),
        "already_original_topic_keys": len(original_topics),
        "previous_logic_preserved": len(original_previous),
        "combined_protected_logic_count": EXPECTED_ALL_LOGIC,
        "decoded_non_protected_changes": restore_report["decoded_non_matcher_changes"],
        "paluke_rumors_pipeline": {
            "typed_input": "RUMORS",
            "synonym_message_id": RUMORS_SYNONYM_ID,
            "synonym_source": RUMORS_SYNONYM_SOURCE,
            "paluke_topic_message_id": PALUKE_PRISONER_ID,
            "paluke_topic_source": PALUKE_PRISONER_SOURCE,
            "response_message_id": PALUKE_RUMOR_RESPONSE_ID,
        },
        "used_data_bytes": restore_report["used_data_bytes"],
        "padded_data_size": restore_report["padded_data_size"],
        "padding_bytes_between_ranges": restore_report["padding_bytes_between_ranges"],
        "msg_hdr_size": restore_report["msg_hdr_size"],
    }

    payloads: dict[str, bytes] = {}
    for path in sorted(args.v47_dir.iterdir()):
        if path.is_file() and path.name.startswith("UI_V") and path.suffix == ".json":
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
            data = annotate_codebook(data, manifest_meta, topic_report)
        payloads[f"DSAVANT/{path.name}"] = data

    report = {
        "format": "Wizardry VII DOS Korean v0.48 NPC/global topic-key restore",
        "base_release": "v0.47",
        "base_zip_sha256": V47_ZIP_SHA256,
        "manifests": manifest_meta,
        "topic_restore": topic_report,
        "preserved": {
            "misc_hdr_sha256": sha256(misc_raw),
            "scenario_dbs_sha256": sha256((source_game / "SCENARIO.DBS").read_bytes()),
            "vbfont0_vga_sha256": sha256((source_game / "VBFONT0.VGA").read_bytes()),
            "vmnpc_ovr_sha256": sha256((source_game / "VMNPC.OVR").read_bytes()),
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    payloads["UI_V48_REPORT.json"] = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    (args.output_dir / "UI_V48_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
