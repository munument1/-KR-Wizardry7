#!/usr/bin/env python3
"""Relocate Korean scene helpers beyond VMAZE without resizing overlays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_dos_korean_boundaries import audit
from build_dos_v19_baseline import expect_hash, sha256, write_deterministic_zip
from build_dos_v20_ui_complete import MZ_HEADER_SIZE, OVERLAY_ORIGIN, call_target, near_call
from build_dos_v25_scene_text import SCENE_FIND_HELPER, scene_find_helper_bytes
from build_dos_v26_scene_text import TRAILING_ASCII_HELPER, trailing_ascii_helper_bytes
from build_dos_v28_all_scene_text import PARSER_COPIES
from build_dos_v31_copy_protection import V30_HASHES, V31_MESSAGE_HASHES
from build_dos_v35_security_enter import V35_VBASE_HASH


V35_HASHES = {
    **V30_HASHES,
    **V31_MESSAGE_HASHES,
    "VBASE.OVR": V35_VBASE_HASH,
}

VBASE_SPEC = {
    "find_calls": (0x6F23, 0x6F40),
    "trailing_site": 0x6D63,
}
SCENE_USERS = {"VBASE.OVR": VBASE_SPEC, **PARSER_COPIES}

# VMAZE occupies [0x5047, 0xFDAF).  The original DS image contains a verified
# all-zero cave at [0xFDAF, 0xFF62).  Keep one byte of separation and align the
# two helpers for straightforward binary inspection.
VMAZE_RUNTIME_END = 0xFDAF
SAFE_CAVE_START = 0xFDAF
SAFE_CAVE_END = 0xFF62
RELOCATED_FIND_HELPER = 0xFDB0
RELOCATED_TRAILING_HELPER = 0xFDF0


def relocate_ds_helpers(ds_exe: bytes) -> bytes:
    data = bytearray(ds_exe)
    find = scene_find_helper_bytes()
    trailing = trailing_ascii_helper_bytes()

    for old_runtime, helper, label in (
        (SCENE_FIND_HELPER, find, "old find"),
        (TRAILING_ASCII_HELPER, trailing, "old trailing"),
    ):
        offset = MZ_HEADER_SIZE + old_runtime
        if bytes(data[offset : offset + len(helper)]) != helper:
            raise ValueError(f"{label} helper does not match guarded v35 bytes")
        data[offset : offset + len(helper)] = b"\x00" * len(helper)

    for runtime, helper, label in (
        (RELOCATED_FIND_HELPER, find, "relocated find"),
        (RELOCATED_TRAILING_HELPER, trailing, "relocated trailing"),
    ):
        if runtime < SAFE_CAVE_START or runtime + len(helper) > SAFE_CAVE_END:
            raise ValueError(f"{label} helper is outside the verified DS cave")
        offset = MZ_HEADER_SIZE + runtime
        if bytes(data[offset : offset + len(helper)]) != b"\x00" * len(helper):
            raise ValueError(f"{label} helper destination is not empty")
        data[offset : offset + len(helper)] = helper
    return bytes(data)


def retarget_scene_user(name: str, source: bytes) -> bytes:
    spec = SCENE_USERS[name]
    data = bytearray(source)
    for offset in spec["find_calls"]:
        actual = call_target(data, offset, OVERLAY_ORIGIN)
        if actual != SCENE_FIND_HELPER:
            raise ValueError(
                f"{name} find call 0x{offset:04X} targets 0x{actual:04X}, "
                f"expected 0x{SCENE_FIND_HELPER:04X}"
            )
        data[offset : offset + 3] = near_call(
            RELOCATED_FIND_HELPER, OVERLAY_ORIGIN + offset
        )

    trailing_call = spec["trailing_site"] + 3
    actual = call_target(data, trailing_call, OVERLAY_ORIGIN)
    if actual != TRAILING_ASCII_HELPER:
        raise ValueError(
            f"{name} trailing call targets 0x{actual:04X}, "
            f"expected 0x{TRAILING_ASCII_HELPER:04X}"
        )
    data[trailing_call : trailing_call + 3] = near_call(
        RELOCATED_TRAILING_HELPER, OVERLAY_ORIGIN + trailing_call
    )
    return bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v35-dir", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")
    source_dir = args.v35_dir / "DSAVANT" if (args.v35_dir / "DSAVANT").is_dir() else args.v35_dir

    payloads: dict[str, bytes] = {}
    for name, expected_hash in V35_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v35 {name}", source, expected_hash)
        if name == "DS.EXE":
            source = relocate_ds_helpers(source)
        elif name in SCENE_USERS:
            source = retarget_scene_user(name, source)
        payloads[f"DSAVANT/{name}"] = source

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    boundary = audit(args.output_dir / "DSAVANT", args.translations, args.original_zip)
    if not boundary["passed"]:
        raise ValueError(f"v37 boundary audit failed: {boundary}")

    report = {
        "format": "Wizardry VII DOS v37 fixed-size Korean scene parser relocation",
        "root_cause": (
            "the v25-v35 helpers at 0xF7E0/0xF820 were inside VMAZE's "
            "0x5047-0xFDAF runtime interval"
        ),
        "changes": [
            "moves both scene helpers into the verified 0xFDAF-0xFF62 DS cave",
            "retargets all four scene parser copies to 0xFDB0/0xFDF0",
            "preserves the exact byte size of DS.EXE and every overlay",
            "retains all v35 localization, title, security, and save changes",
        ],
        "layout": {
            "vmaze_runtime_end": f"0x{VMAZE_RUNTIME_END:04X}",
            "safe_cave": [f"0x{SAFE_CAVE_START:04X}", f"0x{SAFE_CAVE_END:04X}"],
            "find_helper": f"0x{RELOCATED_FIND_HELPER:04X}",
            "trailing_helper": f"0x{RELOCATED_TRAILING_HELPER:04X}",
        },
        "audit": {
            "passed": boundary["passed"],
            "issue_count": boundary["issue_count"],
            "record_count": boundary["record_count"],
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V37_REPORT.json"] = report_raw
    (args.output_dir / "UI_V37_REPORT.json").write_bytes(report_raw)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
