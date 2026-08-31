#!/usr/bin/env python3
"""Move Korean scene-parser helpers from shared overlay space into each user."""

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
# VMNPC.OVR is the largest guarded original overlay.  Keeping every extended
# scene overlay below this size avoids increasing the established overlay arena.
MAX_ORIGINAL_OVERLAY_SIZE = 44921


def localize_scene_helpers(name: str, source: bytes) -> tuple[bytes, dict[str, int]]:
    """Append private helpers and retarget an already-v28-patched parser copy."""
    spec = SCENE_USERS[name]
    find_helper = scene_find_helper_bytes()
    trailing_helper = trailing_ascii_helper_bytes()
    find_target = OVERLAY_ORIGIN + len(source)
    trailing_target = find_target + len(find_helper)
    runtime_end = trailing_target + len(trailing_helper)
    if runtime_end > 0x10000:
        raise ValueError(f"{name} private helpers cross the 16-bit segment boundary")

    data = bytearray(source)
    for offset in spec["find_calls"]:
        actual = call_target(data, offset, OVERLAY_ORIGIN)
        if actual != SCENE_FIND_HELPER:
            raise ValueError(
                f"{name} find call 0x{offset:04X} targets 0x{actual:04X}, "
                f"expected shared helper 0x{SCENE_FIND_HELPER:04X}"
            )
        data[offset : offset + 3] = near_call(find_target, OVERLAY_ORIGIN + offset)

    trailing_call = spec["trailing_site"] + 3
    actual = call_target(data, trailing_call, OVERLAY_ORIGIN)
    if actual != TRAILING_ASCII_HELPER:
        raise ValueError(
            f"{name} trailing call targets 0x{actual:04X}, "
            f"expected shared helper 0x{TRAILING_ASCII_HELPER:04X}"
        )
    data[trailing_call : trailing_call + 3] = near_call(
        trailing_target, OVERLAY_ORIGIN + trailing_call
    )
    data.extend(find_helper)
    data.extend(trailing_helper)
    return bytes(data), {
        "original_size": len(source),
        "extended_size": len(data),
        "find_target": find_target,
        "trailing_target": trailing_target,
        "runtime_end": runtime_end,
    }


def retire_shared_helpers(ds_exe: bytes) -> bytes:
    """Erase the now-unused helpers from the overlay-addressed DS image cave."""
    data = bytearray(ds_exe)
    for runtime, helper, label in (
        (SCENE_FIND_HELPER, scene_find_helper_bytes(), "find"),
        (TRAILING_ASCII_HELPER, trailing_ascii_helper_bytes(), "trailing"),
    ):
        offset = MZ_HEADER_SIZE + runtime
        actual = bytes(data[offset : offset + len(helper)])
        if actual != helper:
            raise ValueError(f"shared {label} helper bytes are not the guarded v35 payload")
        data[offset : offset + len(helper)] = b"\x00" * len(helper)
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
    local_helpers: dict[str, dict[str, int]] = {}
    for name, expected_hash in V35_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v35 {name}", source, expected_hash)
        if name == "DS.EXE":
            source = retire_shared_helpers(source)
        elif name in SCENE_USERS:
            source, local_helpers[name] = localize_scene_helpers(name, source)
        payloads[f"DSAVANT/{name}"] = source

    for name, details in local_helpers.items():
        if details["extended_size"] > MAX_ORIGINAL_OVERLAY_SIZE:
            raise ValueError(f"{name} exceeds the largest original overlay allocation")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    boundary = audit(args.output_dir / "DSAVANT", args.translations, args.original_zip)
    if not boundary["passed"]:
        raise ValueError(f"v36 boundary audit failed: {boundary}")

    report = {
        "format": "Wizardry VII DOS v36 overlay-local Korean scene parsers",
        "root_cause": (
            "v25-v35 placed scene helpers at runtime 0xF7E0/0xF820 inside the "
            "address range occupied by the VMAZE overlay"
        ),
        "changes": [
            "appends a private Korean delimiter and trailing-marker parser to each scene overlay",
            "retargets VBASE, VMAZE, VPCVW, and VTREA only to their own private copies",
            "retires the two unsafe shared helper copies from DS.EXE",
            "retains the v35 security bypass, Korean title, messages, fonts, and save compatibility",
        ],
        "local_helpers": local_helpers,
        "largest_original_overlay_size": MAX_ORIGINAL_OVERLAY_SIZE,
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
    payloads["UI_V36_REPORT.json"] = report_raw
    (args.output_dir / "UI_V36_REPORT.json").write_bytes(report_raw)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
