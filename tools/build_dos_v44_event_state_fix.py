#!/usr/bin/env python3
"""Build Wizardry VII DOS Korean v0.44 from the exact published v0.43 payload.

v0.35 replaced the VBASE security/state routine call at file offset 0x667B
with ``mov ax,1`` so the copy-protection prompt could be accepted by pressing
Enter. Runtime A/B testing showed that removing the call also skips a required
state side effect. The original resident routine writes DS:1008 from DS:59F8
before returning success; without that write the early Jan-Ette encounter can
select the H'Jenn-Ra/T'Rang scene instead.

v0.44 restores only that original three-byte near call. Every other v0.43
payload byte is preserved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_deterministic_zip(path: Path, payloads: dict[str, bytes]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])


V43_VBASE_SHA256 = "c932538ad5174e5c90adf6aeda836730115f17c4f6edeb13176e54ea8612575b"
V44_VBASE_SHA256 = "99fa1b3188cfb3585061ddbe34f136b57939b98250daacb4cec8146cd54db464"
PATCH_OFFSET = 0x667B
V43_BYPASS_BYTES = bytes.fromhex("B8 01 00")
ORIGINAL_CALL_BYTES = bytes.fromhex("E8 4C 73")


def patch_vbase(source: bytes, *, verify_hash: bool = True) -> bytes:
    if verify_hash and sha256(source) != V43_VBASE_SHA256:
        raise ValueError(
            "v0.43 VBASE.OVR hash mismatch: "
            f"expected {V43_VBASE_SHA256}, found {sha256(source)}"
        )
    if len(source) < PATCH_OFFSET + len(V43_BYPASS_BYTES):
        raise ValueError("VBASE.OVR is shorter than the guarded patch site")
    actual = source[PATCH_OFFSET : PATCH_OFFSET + len(V43_BYPASS_BYTES)]
    if actual != V43_BYPASS_BYTES:
        raise ValueError(
            f"VBASE.OVR 0x{PATCH_OFFSET:04X}: expected "
            f"{V43_BYPASS_BYTES.hex(' ')}, found {actual.hex(' ')}"
        )
    output = bytearray(source)
    output[PATCH_OFFSET : PATCH_OFFSET + len(ORIGINAL_CALL_BYTES)] = ORIGINAL_CALL_BYTES
    result = bytes(output)
    if verify_hash and sha256(result) != V44_VBASE_SHA256:
        raise AssertionError(
            "patched VBASE.OVR hash mismatch: "
            f"expected {V44_VBASE_SHA256}, found {sha256(result)}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v43-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    source_game = args.v43_dir / "DSAVANT"
    if not source_game.is_dir():
        raise FileNotFoundError(f"v0.43 DSAVANT directory not found: {source_game}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    source_files = sorted(path for path in source_game.iterdir() if path.is_file())
    if not source_files:
        raise ValueError("v0.43 DSAVANT directory contains no files")

    payloads: dict[str, bytes] = {}
    unchanged_hashes: dict[str, str] = {}
    for path in source_files:
        data = path.read_bytes()
        if path.name == "VBASE.OVR":
            data = patch_vbase(data)
        else:
            unchanged_hashes[path.name] = sha256(data)
        payloads[f"DSAVANT/{path.name}"] = data

    report = {
        "format": "Wizardry VII DOS Korean v0.44 event-state fix",
        "base_release": "v0.43",
        "runtime_confirmation": {
            "core_only_v43_with_stock_overlays": "Jan-Ette normal",
            "v43_core_plus_VMNPC": "Jan-Ette normal",
            "v43_core_plus_VBASE": "H'Jenn-Ra reproduced",
            "v43_VBASE_with_original_call_restored": "Jan-Ette normal",
            "full_v43_with_original_call_restored": "Jan-Ette normal",
        },
        "root_cause": {
            "file": "VBASE.OVR",
            "file_offset": f"0x{PATCH_OFFSET:04X}",
            "v43_bytes": V43_BYPASS_BYTES.hex(" ").upper(),
            "v44_bytes": ORIGINAL_CALL_BYTES.hex(" ").upper(),
            "resident_target": "CS:2A11",
            "required_side_effect": "DS:1008 <- DS:59F8 before successful return",
            "symptom": "early Jan-Ette encounter selected H'Jenn-Ra/T'Rang scene",
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
        "unchanged_payload_count": len(unchanged_hashes),
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V44_REPORT.json"] = report_raw

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    (args.output_dir / "UI_V44_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
