#!/usr/bin/env python3
"""Protect Korean glyphs in Wizardry VII's cinematic word wrapper."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from audit_dos_korean_boundaries import load_records
from build_dos_messages import DEFAULT_ESCAPE
from build_dos_v19_baseline import (
    BytePatch,
    apply_guarded_patches,
    expect_hash,
    sha256,
    write_deterministic_zip,
)
from build_dos_v20_ui_complete import MZ_HEADER_SIZE, OVERLAY_ORIGIN, near_call
from patch_dos_korean_renderer import Assembler16


V24_HASHES = {
    "DS.EXE": "856a1697771525fa458b7ffcace9454146aec745887c781a5666a0f12722865b",
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "MSG.DBS": "87929ec524547ccca54fe2627a249c1773a077b196b13bb093d6209cb50ec6d5",
    "MSG.HDR": "bf5234b700bb004b05d794006c0a1a55a01705ed76e09735e73381242dc4a897",
    "VBASE.OVR": "5546e63be4fec69655c1080e5c7c25aa5073d50d0ac08b0bfc391b7a9bab7a40",
    "VBFONT0.VGA": "e425f17118abbc2d7599c61f89324ea9162939a97383f35d17c11e90d7cd4750",
    "VDOPT.OVR": "b2574cecefcc55f2b42cac509c4428f696da27cfdb558b44082a0b19e516be92",
    "VINIT.OVR": "63a88cc454817c243d3c6023107a86e2c6926dc9a38cd63e773843e1da96b2a6",
    "VMAZE.OVR": "252d4c7e205db120c75f6547ab5772d8ebd89a8d0e1a700d58781afbeced1197",
    "VMELE.OVR": "e56c555e3343fc869aa49fd8419e40a2271ee370de023f7ae8d453afa7a7e8a4",
    "VMEXE.OVR": "8058f9c1ed4d6409c9922969b57aa972864fa396c2d4bb7d353d8a5ec580d3da",
    "VMEXT.OVR": "e9f9f77d1312b370e146e2d4f86edd7dea7cbbf36a10af04168fdfb7f7222029",
    "VMNPC.OVR": "dfedb6b59cb12bc3d79e54f0e163969bd7dfe39b76a12a7d0a9abb02677d7fb1",
    "VPCLV.OVR": "2f83def79e4027ea65eea40b44fac7782a99140f6bbf02c7aa385f93827ab9fd",
    "VPCMK.OVR": "36b50daea346973750a0cc9c9b18c7b222f216cc73662e01e7c1dd1ee52a625f",
    "VPCVW.OVR": "db39bbe3f33131f6cb8d89866ab17f623f34f95bf83bbac91a20e1fb47f084f7",
    "VPOPS.OVR": "cb554c9af7d5e105e96fe89adb654dd80f2daabffe5228bbe7aa2adce02819ee",
    "VTREA.OVR": "95c08e2ba6d414cf0be25865da04c520dfc55d858815d52ebacb4418fd1cb305",
}

SCENE_FIND_HELPER = 0xF7E0
ORIGINAL_FIND_TARGET = 0x3E91
SCENE_FIND_CALLS = (0x6F23, 0x6F40)
SCENE_MESSAGE_RANGE = range(28000, 32000)
DELIMITERS = (0x20, 0x5F)


def korean_aware_find(raw: bytes, target: int) -> int:
    """Return a byte index without treating Korean payload bytes as delimiters."""
    index = 0
    while index < len(raw) and raw[index]:
        value = raw[index]
        if value == DEFAULT_ESCAPE and index + 1 < len(raw):
            if raw[index + 1] == DEFAULT_ESCAPE:
                index += 2
            else:
                index += 3
            continue
        if value == target:
            return index
        index += 1
    return -1


def glyph_delimiter_collisions(raw: bytes) -> list[dict[str, int]]:
    collisions: list[dict[str, int]] = []
    index = 0
    while index < len(raw):
        if raw[index] == DEFAULT_ESCAPE and index + 1 < len(raw):
            if raw[index + 1] == DEFAULT_ESCAPE:
                index += 2
                continue
            if index + 2 >= len(raw):
                break
            for payload_offset in (1, 2):
                if raw[index + payload_offset] in DELIMITERS:
                    collisions.append(
                        {
                            "glyph_offset": index,
                            "payload_offset": payload_offset,
                            "delimiter": raw[index + payload_offset],
                        }
                    )
            index += 3
            continue
        index += 1
    return collisions


def scene_find_helper_bytes() -> bytes:
    """cdecl find(text, byte) -> index or -1, skipping custom glyph payloads."""
    asm = Assembler16(SCENE_FIND_HELPER)
    asm.emit(0x55, 0x89, 0xE5, 0x56, 0x53, 0xFC)  # frame; save si/bx; cld
    asm.emit(0x8B, 0x76, 0x04, 0x31, 0xDB)  # si=text; bx=byte index
    asm.label("loop")
    asm.emit(0xAC, 0x08, 0xC0)  # lodsb; test al,al
    asm.j8(0x74, "not_found")
    asm.emit(0x3C, DEFAULT_ESCAPE)
    asm.j8(0x75, "compare")
    asm.emit(0xAC, 0x3C, DEFAULT_ESCAPE)  # escaped literal or first rank byte
    asm.j8(0x74, "escaped_literal")
    asm.emit(0x46, 0x83, 0xC3, 0x03)  # skip second rank byte; index += 3
    asm.j8(0xEB, "loop")
    asm.label("escaped_literal")
    asm.emit(0x83, 0xC3, 0x02)
    asm.j8(0xEB, "loop")
    asm.label("compare")
    asm.emit(0x3A, 0x46, 0x06)
    asm.j8(0x74, "found")
    asm.emit(0x43)
    asm.j8(0xEB, "loop")
    asm.label("not_found")
    asm.emit(0xB8, 0xFF, 0xFF)
    asm.j8(0xEB, "done")
    asm.label("found")
    asm.emit(0x89, 0xD8)
    asm.label("done")
    asm.emit(0x5B, 0x5E, 0x89, 0xEC, 0x5D, 0xC3)
    return asm.finish()


def patch_scene_text(ds_exe: bytes, vbase: bytes) -> tuple[bytes, bytes]:
    helper = scene_find_helper_bytes()
    ds = bytearray(ds_exe)
    helper_offset = MZ_HEADER_SIZE + SCENE_FIND_HELPER
    if ds[helper_offset : helper_offset + len(helper)] != b"\x00" * len(helper):
        raise ValueError("resident scene-find helper cave is not empty")
    ds[helper_offset : helper_offset + len(helper)] = helper

    patches = tuple(
        BytePatch(
            f"cinematic delimiter search {offset:#06x}",
            offset,
            near_call(ORIGINAL_FIND_TARGET, OVERLAY_ORIGIN + offset),
            near_call(SCENE_FIND_HELPER, OVERLAY_ORIGIN + offset),
        )
        for offset in SCENE_FIND_CALLS
    )
    return bytes(ds), apply_guarded_patches(vbase, patches)


def audit_scene_records(game_dir: Path) -> dict[str, object]:
    _, records = load_records(game_dir)
    affected: dict[int, int] = {}
    for record in records:
        if record.message_id not in SCENE_MESSAGE_RANGE:
            continue
        raw = base64.b64decode(record.raw_base64)
        collisions = glyph_delimiter_collisions(raw)
        if collisions:
            affected[record.message_id] = len(collisions)
    return {
        "scene_range": [SCENE_MESSAGE_RANGE.start, SCENE_MESSAGE_RANGE.stop - 1],
        "affected_records": len(affected),
        "embedded_delimiter_bytes": sum(affected.values()),
        "first_affected_id": min(affected) if affected else None,
        "last_affected_id": max(affected) if affected else None,
        "aletheides_records": {
            str(message_id): affected.get(message_id, 0)
            for message_id in range(31650, 31654)
        },
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

    patched_ds, patched_vbase = patch_scene_text(sources["DS.EXE"], sources["VBASE.OVR"])
    sources["DS.EXE"] = patched_ds
    sources["VBASE.OVR"] = patched_vbase
    payloads = {f"DSAVANT/{name}": data for name, data in sources.items()}

    scene_audit = audit_scene_records(source_dir)
    report = {
        "format": "Wizardry VII DOS v25 Korean cinematic text fix",
        "change": [
            "cinematic word wrapping now skips complete ESC+rank+rank Korean glyphs",
            "embedded 0x20/0x5F glyph payload bytes are no longer mistaken for spaces or underscores",
        ],
        "scene_audit": scene_audit,
        "patch": {
            "helper_runtime_offset": f"0x{SCENE_FIND_HELPER:04X}",
            "helper_size": len(scene_find_helper_bytes()),
            "retargeted_vbase_calls": [f"0x{offset:04X}" for offset in SCENE_FIND_CALLS],
        },
        "safety": [
            "all v24 inputs are SHA-256 guarded",
            "DS.EXE and VBASE.OVR sizes are unchanged",
            "only the two cinematic delimiter searches are redirected",
            "message data, font mapping, save data, and gameplay logic are unchanged",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V25_REPORT.json"] = report_raw

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
