#!/usr/bin/env python3
"""Extend the party-panel profession truncation to a Korean-safe boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_dos_v19_baseline import BytePatch, apply_guarded_patches, expect_hash, sha256, write_deterministic_zip
from build_dos_v22_copy_protection import V21_HASHES, V22_MESSAGE_HASHES


V22_HASHES = dict(V21_HASHES)
V22_HASHES.update(V22_MESSAGE_HASHES)

PROFESSION_TRUNCATION_PATCH = BytePatch(
    "party profession truncation 7 bytes -> 12 bytes",
    0x1E62,
    bytes.fromhex("C6 46 CF 00"),  # mov byte ptr [bp-0x31],0; buffer is bp-0x38
    bytes.fromhex("C6 46 D4 00"),  # mov byte ptr [bp-0x2C],0; buffer + 12
)

V23_DS_HASH = "856a1697771525fa458b7ffcace9454146aec745887c781a5666a0f12722865b"


def patch_party_profession(ds_exe: bytes) -> bytes:
    patched = apply_guarded_patches(ds_exe, (PROFESSION_TRUNCATION_PATCH,))
    expect_hash("v23 DS.EXE", patched, V23_DS_HASH)
    return patched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v22-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    payloads: dict[str, bytes] = {}
    for name, expected_hash in V22_HASHES.items():
        source = (args.v22_dir / name).read_bytes()
        expect_hash(f"v22 {name}", source, expected_hash)
        if name == "DS.EXE":
            source = patch_party_profession(source)
        payloads[f"DSAVANT/{name}"] = source

    report = {
        "format": "Wizardry VII DOS v23 Korean UI + party profession fix",
        "change": [
            "party-panel profession buffer truncation moved from byte 7 to byte 12",
            "the new boundary holds every localized profession and never splits a 3-byte Korean glyph",
        ],
        "fixed_examples": ["마법사", "연금술사"],
        "safety": [
            "DS.EXE size and control flow unchanged",
            "only the stack-buffer terminator displacement changed",
            "v22 message, renderer, font, overlay, UI, and save formats unchanged",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    payloads["UI_V23_REPORT.json"] = json.dumps(
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
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
