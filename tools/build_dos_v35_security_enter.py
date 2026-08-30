#!/usr/bin/env python3
"""Package v31 with Enter-only copy-protection acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_dos_korean_boundaries import audit
from build_dos_v19_baseline import (
    BytePatch,
    apply_guarded_patches,
    expect_hash,
    sha256,
    write_deterministic_zip,
)
from build_dos_v31_copy_protection import V30_HASHES, V31_MESSAGE_HASHES


V31_HASHES = {**V30_HASHES, **V31_MESSAGE_HASHES}
SECURITY_COMPARE_PATCH = BytePatch(
    "security verifier returns success after preserving the input-buffer copy",
    0x667B,
    bytes.fromhex("E8 4C 73"),
    bytes.fromhex("B8 01 00"),
)
V35_VBASE_HASH = "2c0b7b06d4ca44ab7a63b2fd9e20288f7d38a10ca1a73a31c044210d9ca7d229"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v31-dir", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    source_dir = args.v31_dir / "DSAVANT"
    payloads: dict[str, bytes] = {}
    for name, expected_hash in V31_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v31 {name}", source, expected_hash)
        if name == "VBASE.OVR":
            source = apply_guarded_patches(source, (SECURITY_COMPARE_PATCH,))
            expect_hash("v35 VBASE.OVR", source, V35_VBASE_HASH)
        payloads[f"DSAVANT/{name}"] = source

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    boundary = audit(args.output_dir / "DSAVANT", args.translations, args.original_zip)
    if not boundary["passed"]:
        raise ValueError(f"v35 boundary audit failed: {boundary}")

    report = {
        "format": "Wizardry VII DOS v35 Korean Enter-only security clearance",
        "changes": [
            "retains all 75 original ASCII copy-protection answers and question metadata",
            "preserves the answer-input buffer copy, then replaces only the verifier call with success",
            "allows an empty answer: press Enter once at the security-clearance prompt",
            "keeps save/load file I/O code and every other v31 payload unchanged",
        ],
        "patch": {
            "file": "VBASE.OVR",
            "offset": SECURITY_COMPARE_PATCH.offset,
            "old_hex": SECURITY_COMPARE_PATCH.expected.hex(" ").upper(),
            "new_hex": SECURITY_COMPARE_PATCH.replacement.hex(" ").upper(),
        },
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
    payloads["UI_V35_REPORT.json"] = report_raw
    (args.output_dir / "UI_V35_REPORT.json").write_bytes(report_raw)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
