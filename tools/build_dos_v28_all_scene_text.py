#!/usr/bin/env python3
"""Patch every duplicated cinematic/event text parser for Korean glyph units."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_dos_v19_baseline import BytePatch, apply_guarded_patches, expect_hash, sha256, write_deterministic_zip
from build_dos_v20_ui_complete import OVERLAY_ORIGIN, call_target, near_call
from build_dos_v25_scene_text import ORIGINAL_FIND_TARGET, SCENE_FIND_HELPER, V24_HASHES
from build_dos_v26_scene_text import TRAILING_ASCII_HELPER


V26_HASHES = {
    **V24_HASHES,
    "DS.EXE": "6b3e0ebd09e987e31c2a49b8400b669c1af1e0e5b8564bfff6013af37bf1dd2c",
    "VBASE.OVR": "001b52292d08a1fa222cdde90f0a28209245282eb7ba14042484d7ef3edbc020",
}

# VBASE owns the opening/cinematic copy and was fixed in v26.  These are the
# three byte-for-byte parser families used by field events and other views.
PARSER_COPIES = {
    "VMAZE.OVR": {
        "find_calls": (0x6EBE, 0x6EDB),
        "trailing_site": 0x6C53,
    },
    "VPCVW.OVR": {
        "find_calls": (0x3C25, 0x3C42),
        "trailing_site": 0x3AF0,
    },
    "VTREA.OVR": {
        "find_calls": (0x0D31, 0x0D4E),
        "trailing_site": 0x0AB3,
    },
}

ORIGINAL_TRAILING = bytes.fromhex("8B 5E 04 8B F0 8A 00 2A E4 EB 21")


def short_jump(source_runtime: int, target_runtime: int) -> bytes:
    displacement = target_runtime - (source_runtime + 2)
    if not -128 <= displacement <= 127:
        raise ValueError("short jump target is out of range")
    return bytes((0xEB, displacement & 0xFF))


def trailing_replacement(site: int) -> bytes:
    call_offset = site + 3
    jump_offset = call_offset + 4
    compare_runtime = OVERLAY_ORIGIN + site + 0x2C
    return (
        bytes.fromhex("FF 76 04")
        + near_call(TRAILING_ASCII_HELPER, OVERLAY_ORIGIN + call_offset)
        + bytes.fromhex("59")
        + short_jump(OVERLAY_ORIGIN + jump_offset, compare_runtime)
        + bytes.fromhex("90 90")
    )


def patch_parser_copy(name: str, source: bytes) -> bytes:
    spec = PARSER_COPIES[name]
    patches = [
        BytePatch(
            f"{name} Korean-aware delimiter search {offset:#06x}",
            offset,
            near_call(ORIGINAL_FIND_TARGET, OVERLAY_ORIGIN + offset),
            near_call(SCENE_FIND_HELPER, OVERLAY_ORIGIN + offset),
        )
        for offset in spec["find_calls"]
    ]
    site = spec["trailing_site"]
    patches.append(
        BytePatch(
            f"{name} standalone ASCII alignment marker",
            site,
            ORIGINAL_TRAILING,
            trailing_replacement(site),
        )
    )
    return apply_guarded_patches(source, tuple(patches))


def audit_parser_copies(payloads: dict[str, bytes]) -> dict[str, object]:
    copies: dict[str, object] = {}
    for name, spec in PARSER_COPIES.items():
        data = payloads[name]
        find_targets = [
            call_target(data, offset, OVERLAY_ORIGIN) for offset in spec["find_calls"]
        ]
        site = spec["trailing_site"]
        trailing = data[site : site + len(ORIGINAL_TRAILING)]
        copies[name] = {
            "find_calls": [f"0x{offset:04X}" for offset in spec["find_calls"]],
            "find_targets": [f"0x{target:04X}" for target in find_targets],
            "find_safe": find_targets == [SCENE_FIND_HELPER] * len(find_targets),
            "trailing_site": f"0x{site:04X}",
            "trailing_safe": trailing == trailing_replacement(site),
        }
    passed = all(
        copy["find_safe"] and copy["trailing_safe"] for copy in copies.values()
    )
    return {"copies": copies, "passed": passed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v26-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    parser.add_argument("--intro-logo", type=Path)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")
    source_dir = args.v26_dir / "DSAVANT" if (args.v26_dir / "DSAVANT").is_dir() else args.v26_dir
    sources: dict[str, bytes] = {}
    for name, expected_hash in V26_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v26 {name}", source, expected_hash)
        sources[name] = source

    for name in PARSER_COPIES:
        sources[name] = patch_parser_copy(name, sources[name])

    payloads = {f"DSAVANT/{name}": data for name, data in sources.items()}
    if args.intro_logo:
        payloads["DSAVANT/MON63.PIC"] = args.intro_logo.read_bytes()
    parser_audit = audit_parser_copies(sources)
    if not parser_audit["passed"]:
        raise RuntimeError("parser-copy audit failed")
    report = {
        "format": "Wizardry VII DOS v28 all event-text parser fix",
        "changes": [
            "retains the v26 Korean-safe opening/cinematic parser",
            "patches the duplicated VMAZE field-event parser used by the landing scene",
            "patches the matching VPCVW and VTREA parser copies for later game screens",
            "preserves the animated Korean title logo when supplied",
        ],
        "parser_audit": parser_audit,
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V28_REPORT.json"] = report_raw
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
