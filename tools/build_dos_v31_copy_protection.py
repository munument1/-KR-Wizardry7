#!/usr/bin/env python3
"""Package the ASCII copy-protection answer restoration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_dos_korean_boundaries import audit
from build_dos_v19_baseline import expect_hash, sha256, write_deterministic_zip
from build_dos_v30_save_compat import MESSAGE_HASHES as V30_MESSAGE_HASHES
from build_dos_v30_save_compat import V29_HASHES


V30_HASHES = {**V29_HASHES, **V30_MESSAGE_HASHES}
V31_MESSAGE_HASHES = {
    "MSG.HDR": "643a73e4f518d55be84abe72579554590af6b2a89403320d623ab30ca39d0455",
    "MSG.DBS": "d01b044e5d2481ab26711e89b5fba07b18c7f1b3b9cc541a5e8b865d8d121373",
    "MISC.HDR": V30_HASHES["MISC.HDR"],
    "korean_codebook.json": V30_HASHES["korean_codebook.json"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v30-dir", type=Path, required=True)
    parser.add_argument("--message-dir", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    source_dir = args.v30_dir / "DSAVANT"
    payloads: dict[str, bytes] = {}
    for name, expected_hash in V30_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v30 {name}", source, expected_hash)
        if name in V31_MESSAGE_HASHES:
            source = (args.message_dir / name).read_bytes()
            expect_hash(f"v31 {name}", source, V31_MESSAGE_HASHES[name])
        payloads[f"DSAVANT/{name}"] = source

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    boundary = audit(args.output_dir / "DSAVANT", args.translations, args.original_zip)
    if not boundary["passed"]:
        raise ValueError(f"v31 boundary audit failed: {boundary}")

    report = {
        "format": "Wizardry VII DOS v31 Korean copy-protection compatibility",
        "changes": [
            "restores copy-protection records 2500-2574 to their original ASCII answers",
            "preserves the four v30 fixed-slot save/load label corrections",
            "keeps all executable, overlay, renderer, font, scene-parser, and logo files unchanged",
        ],
        "root_cause": (
            "translated answer words could not be entered or matched by the ASCII input routine, "
            "blocking save/load before file I/O"
        ),
        "answer_range": {"first": 2500, "last": 2574, "count": 75},
        "audit": {
            "passed": boundary["passed"],
            "issue_count": boundary["issue_count"],
            "record_count": boundary["record_count"],
            "fixed_slots": boundary["fixed_slots"],
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V31_REPORT.json"] = report_raw
    (args.output_dir / "UI_V31_REPORT.json").write_bytes(report_raw)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
