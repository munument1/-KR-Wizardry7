#!/usr/bin/env python3
"""Build Wizardry VII DOS Korean v0.47 with the full NPC parser core restored.

v0.46 restored slash-delimited matcher/synonym records such as
BYE/GOODBYE/QUIT/FAREWELL and PALUKE/ARMORY, but VMNPC.OVR also loads fixed
canonical grammar tables from message IDs 7000..7146.  The synonym table first
normalizes GOODBYE to BYE, then the classifier compares BYE against canonical
record 7121.  v0.46 left 7121 translated, so the two parser halves no longer
matched.  v0.47 restores both layers of parser logic to original DOS ASCII.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import build_dos_v46_runtime_matchers as v46

V46_ZIP_SHA256 = "6eab1afa94d25c332fb652bcc2d631d7b3018bae440c8c554204bd786f816698"
DEFAULT_RUNTIME_MANIFEST = Path("data/dos_runtime_matchers.json")
DEFAULT_CORE_MANIFEST = Path("data/dos_parser_core_records.json")
EXPECTED_RUNTIME_MATCHERS = 186
EXPECTED_CORE_RECORDS = 64
EXPECTED_COMBINED_RECORDS = 250
CORE_RANGES = (
    (7000, 10), (7030, 7), (7040, 2), (7050, 7),
    (7070, 10), (7090, 11), (7120, 10), (7140, 7),
)
CANONICAL_LINKS = {
    7160: 7120, 7161: 7121, 7162: 7122, 7163: 7123,
    7164: 7125, 7165: 7127, 7166: 7126, 7172: 7128, 7173: 7129,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def first_synonym(source_display: str) -> str:
    return source_display.split("/", 1)[0].strip()


def load_core_manifest(path: Path) -> tuple[dict[int, str], dict[str, object]]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    rows = payload.get("records")
    ranges = payload.get("ranges")
    if not isinstance(rows, list) or not isinstance(ranges, list):
        raise ValueError("parser core manifest requires ranges and records lists")
    declared_ranges = tuple(
        (int(row["start_id"]), int(row["count"]))
        for row in ranges if isinstance(row, dict)
    )
    if declared_ranges != CORE_RANGES:
        raise ValueError(f"parser core ranges changed: {declared_ranges!r}")

    records: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("parser core record must be an object")
        message_id = int(row["message_id"])
        source_display = row["source_display"]
        if not isinstance(source_display, str):
            raise ValueError(f"message {message_id}: source_display must be text")
        try:
            encoded = source_display.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError(f"message {message_id}: parser core must remain ASCII") from exc
        if not encoded or any(value < 0x20 or value > 0x7E for value in encoded):
            raise ValueError(f"message {message_id}: invalid parser-core byte")
        if message_id in records:
            raise ValueError(f"duplicate parser core message ID {message_id}")
        records[message_id] = source_display

    expected_ids = {
        message_id for start_id, count in CORE_RANGES
        for message_id in range(start_id, start_id + count)
    }
    if set(records) != expected_ids or len(records) != EXPECTED_CORE_RECORDS:
        raise ValueError("parser core record IDs/count do not match VMNPC load ranges")
    return records, {
        "path": str(path), "sha256": sha256(raw), "record_count": len(records),
        "ranges": [{"start_id": start, "count": count} for start, count in CORE_RANGES],
    }


def load_combined_logic_records(
    runtime_manifest: Path, core_manifest: Path
) -> tuple[dict[int, str], dict[str, object]]:
    runtime, runtime_meta = v46.load_manifest(runtime_manifest)
    core, core_meta = load_core_manifest(core_manifest)
    if len(runtime) != EXPECTED_RUNTIME_MATCHERS:
        raise ValueError(f"runtime matcher count changed: {len(runtime)}")
    overlap = sorted(set(runtime) & set(core))
    if overlap:
        raise ValueError(f"runtime/core manifests overlap: {overlap}")
    combined = dict(runtime)
    combined.update(core)
    if len(combined) != EXPECTED_COMBINED_RECORDS:
        raise AssertionError("combined parser logic count changed unexpectedly")

    links = []
    for synonym_id, canonical_id in CANONICAL_LINKS.items():
        synonym = runtime[synonym_id]
        canonical = core[canonical_id].strip()
        normalized = first_synonym(synonym)
        if normalized != canonical:
            raise ValueError(
                f"parser link {synonym_id}->{canonical_id}: {normalized!r} != {canonical!r}"
            )
        links.append({
            "synonym_message_id": synonym_id,
            "canonical_message_id": canonical_id,
            "canonical": canonical,
        })
    if core[7121] != "BYE" or runtime[7161] != "BYE/GOODBYE/QUIT/FAREWELL/":
        raise ValueError("BYE parser regression fixtures changed")

    return combined, {
        "runtime_matchers": runtime_meta,
        "parser_core": core_meta,
        "combined_record_count": len(combined),
        "canonical_links": links,
        "bye_pipeline": {
            "typed_input": "BYE",
            "synonym_message_id": 7161,
            "normalized_token": first_synonym(runtime[7161]),
            "canonical_message_id": 7121,
            "canonical_token": core[7121],
            "linked": True,
        },
    }


def annotate_codebook(raw: bytes, metadata: dict[str, object], report: dict[str, object]) -> bytes:
    payload = json.loads(raw.decode("utf-8"))
    payload["parser_core_restore"] = {
        "version": "v0.47",
        "reason": "NPC synonym and canonical grammar tables both remain original DOS ASCII.",
        "runtime_matcher_count": EXPECTED_RUNTIME_MATCHERS,
        "parser_core_count": EXPECTED_CORE_RECORDS,
        "combined_logic_count": EXPECTED_COMBINED_RECORDS,
        "core_manifest_sha256": metadata["parser_core"]["sha256"],
        "changed_logic_count": report["changed_matcher_count"],
        "bye_canonical_message_id": 7121,
        "bye_synonym_message_id": 7161,
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
    parser.add_argument("--v46-dir", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, default=DEFAULT_RUNTIME_MANIFEST)
    parser.add_argument("--core-manifest", type=Path, default=DEFAULT_CORE_MANIFEST)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    source_game = args.v46_dir / "DSAVANT"
    if not source_game.is_dir():
        raise FileNotFoundError(f"v0.46 DSAVANT directory not found: {source_game}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    logic_records, manifest_meta = load_combined_logic_records(
        args.runtime_manifest, args.core_manifest
    )
    hdr_raw = (source_game / "MSG.HDR").read_bytes()
    data_raw = (source_game / "MSG.DBS").read_bytes()
    misc_raw = (source_game / "MISC.HDR").read_bytes()
    new_hdr, new_data, restore_report = v46.restore_runtime_matchers(
        hdr_raw, data_raw, misc_raw, logic_records
    )
    if restore_report["changed_matcher_count"] != EXPECTED_CORE_RECORDS:
        raise ValueError(
            f"v0.47 must change exactly 64 parser-core records; found "
            f"{restore_report['changed_matcher_count']}"
        )
    if restore_report["already_original_matcher_count"] != EXPECTED_RUNTIME_MATCHERS:
        raise ValueError(
            f"v0.46 should already preserve 186 runtime matchers; found "
            f"{restore_report['already_original_matcher_count']}"
        )

    payloads: dict[str, bytes] = {}
    for path in sorted(args.v46_dir.iterdir()):
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
            data = annotate_codebook(data, manifest_meta, restore_report)
        payloads[f"DSAVANT/{path.name}"] = data

    report = {
        "format": "Wizardry VII DOS Korean v0.47 full NPC parser logic restore",
        "base_release": "v0.46",
        "base_zip_sha256": V46_ZIP_SHA256,
        "manifests": manifest_meta,
        "parser_restore": restore_report,
        "regression": manifest_meta["bye_pipeline"],
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
    payloads["UI_V47_REPORT.json"] = json.dumps(
        report, ensure_ascii=False, indent=2
    ).encode("utf-8")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    (args.output_dir / "UI_V47_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
