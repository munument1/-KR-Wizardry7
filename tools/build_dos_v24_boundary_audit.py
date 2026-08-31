#!/usr/bin/env python3
"""Package the audited Korean boundary fixes and four skipped translations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_dos_korean_boundaries import audit
from build_dos_v19_baseline import expect_hash, sha256, write_deterministic_zip
from build_dos_v23_party_profession import V22_HASHES, V23_DS_HASH


V23_HASHES = dict(V22_HASHES)
V23_HASHES["DS.EXE"] = V23_DS_HASH

V24_MESSAGE_HASHES = {
    "MSG.HDR": "bf5234b700bb004b05d794006c0a1a55a01705ed76e09735e73381242dc4a897",
    "MSG.DBS": "87929ec524547ccca54fe2627a249c1773a077b196b13bb093d6209cb50ec6d5",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
}

EXPECTED_CHANGED_MESSAGES = {
    "2563": "=<0x02><0x03><0x05>타격",
    "2564": "=<0x03><0x01><0x01>막기",
    "25042": "@그제야 바닥의 재 덩어리와 돌기를",
    "25043": "알아본다...",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v23-dir", type=Path, required=True)
    parser.add_argument("--message-dir", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    payloads: dict[str, bytes] = {}
    for name, expected_hash in V23_HASHES.items():
        source = (args.v23_dir / name).read_bytes()
        expect_hash(f"v23 {name}", source, expected_hash)
        if name in V24_MESSAGE_HASHES:
            source = (args.message_dir / name).read_bytes()
            expect_hash(f"v24 {name}", source, V24_MESSAGE_HASHES[name])
        payloads[f"DSAVANT/{name}"] = source

    message_report = json.loads(
        (args.message_dir / "MESSAGE_PATCH_REPORT.json").read_text(encoding="utf-8")
    )
    actual_changed = {
        message_id: metadata["translation"]
        for message_id, metadata in message_report.get("changed", {}).items()
    }
    if actual_changed != EXPECTED_CHANGED_MESSAGES:
        raise ValueError(f"unexpected changed message set: {actual_changed}")
    if message_report.get("record_start_crossings") != 0:
        raise ValueError("message patch introduced a bank crossing")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    boundary_report = audit(
        args.output_dir / "DSAVANT", args.translations, args.original_zip
    )
    if not boundary_report["passed"]:
        raise ValueError(f"Korean boundary audit failed: {boundary_report}")
    boundary_report_raw = json.dumps(
        boundary_report, ensure_ascii=False, indent=2
    ).encode("utf-8")
    payloads["KOREAN_BOUNDARY_AUDIT.json"] = boundary_report_raw
    (args.output_dir / "KOREAN_BOUNDARY_AUDIT.json").write_bytes(boundary_report_raw)

    report = {
        "format": "Wizardry VII DOS v24 Korean boundary-audited release",
        "changes": [
            "retains the v23 Korean-safe 12-byte party profession boundary",
            "repairs STRIKE and PARRY translations that were #NAME? in the source CSV",
            "repairs the two split 25042/25043 narrative records",
        ],
        "audit": {
            "message_records": boundary_report["record_count"],
            "valid_custom_streams": boundary_report["valid_custom_streams"],
            "message_loader_calls_scanned": boundary_report["binary_scan"]["message_loader_call_total"],
            "fixed_slot_violations": sum(
                len(group["violations"])
                for group in boundary_report["fixed_slots"].values()
            ),
            "source_mismatches": len(boundary_report["source_mismatch_ids"]),
            "issues": boundary_report["issue_count"],
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V24_REPORT.json"] = report_raw
    (args.output_dir / "UI_V24_REPORT.json").write_bytes(report_raw)

    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
