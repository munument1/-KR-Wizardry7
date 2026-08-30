#!/usr/bin/env python3
"""Build Korean-safe cinematic word splitting and trailing-marker handling."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from audit_dos_korean_boundaries import load_records
from build_dos_messages import DEFAULT_ESCAPE
from build_dos_v19_baseline import BytePatch, apply_guarded_patches, expect_hash, sha256, write_deterministic_zip
from build_dos_v20_ui_complete import MZ_HEADER_SIZE, OVERLAY_ORIGIN, near_call
from build_dos_v25_scene_text import (
    SCENE_FIND_CALLS,
    SCENE_FIND_HELPER,
    V24_HASHES,
    audit_scene_records,
    patch_scene_text,
    scene_find_helper_bytes,
)
from patch_dos_korean_renderer import Assembler16


TRAILING_ASCII_HELPER = 0xF820
TRAILING_MARKER_PATCH_OFFSET = 0x6D63
TRAILING_MARKER_COMPARE_RUNTIME = 0xBDD6
TRAILING_MARKERS = (0x24, 0x5E)  # '$' centered and '^' left-aligned


def trailing_ascii_byte(raw: bytes) -> int:
    """Return the final logical byte only when it is an ASCII/literal unit."""
    index = 0
    trailing = 0
    while index < len(raw) and raw[index]:
        value = raw[index]
        if value == DEFAULT_ESCAPE and index + 1 < len(raw):
            if raw[index + 1] == DEFAULT_ESCAPE:
                trailing = DEFAULT_ESCAPE
                index += 2
            else:
                trailing = 0
                index += 3
        else:
            trailing = value
            index += 1
    return trailing


def trailing_ascii_helper_bytes() -> bytes:
    """cdecl trailing_ascii(text) -> final ASCII byte, or zero for Korean."""
    asm = Assembler16(TRAILING_ASCII_HELPER)
    asm.emit(0x55, 0x89, 0xE5, 0x56, 0x53, 0xFC)
    asm.emit(0x8B, 0x76, 0x04, 0x31, 0xDB)  # si=text; bx=last logical ASCII
    asm.label("loop")
    asm.emit(0xAC, 0x08, 0xC0)
    asm.j8(0x74, "done")
    asm.emit(0x3C, DEFAULT_ESCAPE)
    asm.j8(0x75, "ascii")
    asm.emit(0xAC, 0x3C, DEFAULT_ESCAPE)
    asm.j8(0x74, "literal_escape")
    asm.emit(0x46, 0x31, 0xDB)  # skip second rank byte; Korean is not a marker
    asm.j8(0xEB, "loop")
    asm.label("literal_escape")
    asm.emit(0xBB, DEFAULT_ESCAPE, 0x00)
    asm.j8(0xEB, "loop")
    asm.label("ascii")
    asm.emit(0x30, 0xE4, 0x89, 0xC3)
    asm.j8(0xEB, "loop")
    asm.label("done")
    asm.emit(0x89, 0xD8, 0x5B, 0x5E, 0x89, 0xEC, 0x5D, 0xC3)
    return asm.finish()


def short_jump(source_runtime: int, target_runtime: int) -> bytes:
    displacement = target_runtime - (source_runtime + 2)
    if not -128 <= displacement <= 127:
        raise ValueError("short jump target is out of range")
    return bytes((0xEB, displacement & 0xFF))


def patch_scene_text_v26(ds_exe: bytes, vbase: bytes) -> tuple[bytes, bytes]:
    ds_v25, vbase_v25 = patch_scene_text(ds_exe, vbase)
    helper = trailing_ascii_helper_bytes()
    ds = bytearray(ds_v25)
    helper_offset = MZ_HEADER_SIZE + TRAILING_ASCII_HELPER
    if ds[helper_offset : helper_offset + len(helper)] != b"\x00" * len(helper):
        raise ValueError("resident trailing-ASCII helper cave is not empty")
    ds[helper_offset : helper_offset + len(helper)] = helper

    call_offset = TRAILING_MARKER_PATCH_OFFSET + 3
    jump_offset = call_offset + 4
    replacement = (
        bytes.fromhex("FF 76 04")
        + near_call(TRAILING_ASCII_HELPER, OVERLAY_ORIGIN + call_offset)
        + bytes.fromhex("59")
        + short_jump(OVERLAY_ORIGIN + jump_offset, TRAILING_MARKER_COMPARE_RUNTIME)
        + bytes.fromhex("90 90")
    )
    patch = BytePatch(
        "cinematic trailing marker recognizes only standalone ASCII",
        TRAILING_MARKER_PATCH_OFFSET,
        bytes.fromhex("8B 5E 04 8B F0 8A 00 2A E4 EB 21"),
        replacement,
    )
    return bytes(ds), apply_guarded_patches(vbase_v25, (patch,))


def audit_trailing_marker_collisions(game_dir: Path) -> dict[str, object]:
    _, records = load_records(game_dir)
    affected: dict[int, int] = {}
    examples: list[dict[str, int]] = []
    for record in records:
        raw = base64.b64decode(record.raw_base64)
        for word in raw.replace(b"_", b" ").split(b" "):
            if word and word[-1] in TRAILING_MARKERS and trailing_ascii_byte(word) == 0:
                affected[record.message_id] = affected.get(record.message_id, 0) + 1
                if len(examples) < 12:
                    examples.append(
                        {"message_id": record.message_id, "payload_byte": word[-1]}
                    )
    return {
        "affected_records": len(affected),
        "affected_words": sum(affected.values()),
        "reported_intro_records": {
            str(message_id): affected.get(message_id, 0)
            for message_id in (15000, 15002, 15003, 15004)
        },
        "aletheides_records": {
            str(message_id): affected.get(message_id, 0)
            for message_id in range(31650, 31654)
        },
        "examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v24-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    source_dir = args.v24_dir / "DSAVANT" if (args.v24_dir / "DSAVANT").is_dir() else args.v24_dir
    sources: dict[str, bytes] = {}
    for name, expected_hash in V24_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v24 {name}", source, expected_hash)
        sources[name] = source

    sources["DS.EXE"], sources["VBASE.OVR"] = patch_scene_text_v26(
        sources["DS.EXE"], sources["VBASE.OVR"]
    )
    payloads = {f"DSAVANT/{name}": data for name, data in sources.items()}
    report = {
        "format": "Wizardry VII DOS v26 Korean cinematic parser fix",
        "changes": [
            "retains Korean-aware cinematic space and underscore searches",
            "treats $ and ^ as alignment markers only when they are standalone ASCII bytes",
            "preserves Korean glyphs whose final rank byte equals an alignment marker",
        ],
        "delimiter_audit": audit_scene_records(source_dir),
        "trailing_marker_audit": audit_trailing_marker_collisions(source_dir),
        "patch": {
            "find_helper": f"0x{SCENE_FIND_HELPER:04X}",
            "trailing_ascii_helper": f"0x{TRAILING_ASCII_HELPER:04X}",
            "retargeted_find_calls": [f"0x{offset:04X}" for offset in SCENE_FIND_CALLS],
            "trailing_marker_site": f"0x{TRAILING_MARKER_PATCH_OFFSET:04X}",
        },
        "safety": [
            "all v24 inputs and all patched bytes are guarded",
            "DS.EXE and VBASE.OVR sizes are unchanged",
            "message data, font mapping, saves, and gameplay logic are unchanged",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V26_REPORT.json"] = report_raw
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
