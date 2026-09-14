#!/usr/bin/env python3
"""Build Wizardry VII DOS Korean v0.49 with both reviewed runtime hotfixes.

v0.49 fixes two independent Korean-runtime problems on top of the exact
published v0.48 package:

1. The item READ path in VPCVW.OVR decodes translated book text into an
   86-byte stack buffer. Korean ESC+rank+rank encoding expands some records
   beyond the 84-byte safe payload (after the decoder terminator), corrupting
   the caller frame and crashing while reading Book of Fables.
2. Four late VTREA.OVR gameplay-choice helpers center labels with byte strlen
   multiplied by six. Korean glyphs occupy three encoded bytes, so the code
   overestimates their visual width and shifts labels left outside buttons.

The READ buffer is enlarged to 127 bytes, and only the four proven VTREA
coordinate-only sites are redirected to the existing rendered-width adapter.
Logical string-length paths are deliberately left unchanged.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zipfile
from pathlib import Path

from build_dos_v19_baseline import BytePatch, apply_guarded_patches
from extract_gold_messages import extract_messages, parse_header

V48_ZIP_SHA256 = "a0990467c94e1c19bd4ad7432b4895b026accd1056bb983e3110d621ae5e3ba8"

# READ-buffer patch (VPCVW.OVR)
V48_VPCVW_SHA256 = "3e7930fad44ae846a24ab28f2905d1c9d7b3b5d8ebb5bbf815cbd5c49e505ea9"
V49_VPCVW_SHA256 = "4878ef941364e0d91e37e857a2c07946b648729849e178e7e7be7ac02a9216ee"
OLD_BUFFER_BYTES = 0x56
NEW_BUFFER_BYTES = 0x7F
DECODER_TERMINATOR_BYTES = 2
BOOK_START_ID = 21600
BOOK_END_ID = 21655
EXPECTED_FIRST_OLD_OVERFLOW = 21606
EXPECTED_BOOK_MAX_ID = 21633
EXPECTED_BOOK_MAX_DECODED = 111
EXPECTED_CORPUS_MAX_DECODED = 122

VPCVW_PATCHES = (
    BytePatch(
        "expand READ text stack frame 86->127",
        0x3C7B,
        bytes.fromhex("B8 AA FF"),
        bytes.fromhex("B8 81 FF"),
    ),
    BytePatch(
        "relocate READ message buffer decode target",
        0x3CA5,
        bytes.fromhex("8D 46 AA"),
        bytes.fromhex("8D 46 81"),
    ),
    BytePatch(
        "relocate READ message buffer parser target",
        0x3CB9,
        bytes.fromhex("8D 46 AA"),
        bytes.fromhex("8D 46 81"),
    ),
)

# Gameplay-choice centering patch (VTREA.OVR)
OVERLAY_ORIGIN = 0x5047
STRLEN_TARGET = 0x4AD7
WIDTH_ADAPTER = 0x38F4
V48_VTREA_SHA256 = "663b0a905737c214cdd89a4b1d2f2d6a979d63bfab76fecc716df5851eb0b8da"
V49_VTREA_SHA256 = "23cb96744b68998fddb1c8bf5b1fa61f9eca18f492f58318f324861b0217570a"
V48_DS_SHA256 = "54fa02f1e91b3086f2f8283fcbed07d21da8a86285be72c08806f23833b2d112"
VARIABLE_CENTER_SITES = (0x8356, 0x8603)
HALF_WIDTH_SITES = (0x84FB, 0x8C46)
LOGICAL_SITE_MUST_REMAIN = 0x764D


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decoded_lengths(game: Path) -> dict[int, int]:
    hdr = (game / "MSG.HDR").read_bytes()
    data = (game / "MSG.DBS").read_bytes()
    misc = (game / "MISC.HDR").read_bytes()
    _, entries, _ = parse_header(hdr, "dos")
    return {
        record.message_id: len(base64.b64decode(record.raw_base64))
        for record in extract_messages(data, entries, misc)
    }


def audit_read_buffer(game: Path) -> dict[str, object]:
    lengths = decoded_lengths(game)
    missing = [message_id for message_id in range(BOOK_START_ID, BOOK_END_ID + 1) if message_id not in lengths]
    if missing:
        raise ValueError(f"Book of Fables messages missing: {missing[:8]}")

    book = {message_id: lengths[message_id] for message_id in range(BOOK_START_ID, BOOK_END_ID + 1)}
    old_capacity = OLD_BUFFER_BYTES - DECODER_TERMINATOR_BYTES
    new_capacity = NEW_BUFFER_BYTES - DECODER_TERMINATOR_BYTES
    old_overflows = [message_id for message_id, size in book.items() if size > old_capacity]
    new_overflows = [message_id for message_id, size in lengths.items() if size > new_capacity]
    book_max_id = max(book, key=book.get)
    corpus_max_id = max(lengths, key=lengths.get)

    if not old_overflows or old_overflows[0] != EXPECTED_FIRST_OLD_OVERFLOW:
        raise ValueError(f"unexpected first Book overflow: {old_overflows[:1]}")
    if (book_max_id, book[book_max_id]) != (EXPECTED_BOOK_MAX_ID, EXPECTED_BOOK_MAX_DECODED):
        raise ValueError(
            f"unexpected Book maximum: id={book_max_id} decoded={book[book_max_id]}"
        )
    if lengths[corpus_max_id] != EXPECTED_CORPUS_MAX_DECODED:
        raise ValueError(
            f"unexpected corpus maximum: id={corpus_max_id} decoded={lengths[corpus_max_id]}"
        )
    if new_overflows:
        raise ValueError(
            f"127-byte READ buffer is still too small for messages: {new_overflows[:8]}"
        )

    return {
        "book_message_range": [BOOK_START_ID, BOOK_END_ID],
        "old_buffer_bytes": OLD_BUFFER_BYTES,
        "old_safe_decoded_bytes": old_capacity,
        "old_overflow_ids": old_overflows,
        "first_old_overflow_id": old_overflows[0],
        "book_max_message_id": book_max_id,
        "book_max_decoded_bytes": book[book_max_id],
        "new_buffer_bytes": NEW_BUFFER_BYTES,
        "new_safe_decoded_bytes": new_capacity,
        "new_overflow_count_entire_message_bank": len(new_overflows),
        "corpus_max_message_id": corpus_max_id,
        "corpus_max_decoded_bytes": lengths[corpus_max_id],
        "decoder_terminator_bytes": DECODER_TERMINATOR_BYTES,
    }


def patch_vpcvw(raw: bytes) -> bytes:
    if sha256(raw) != V48_VPCVW_SHA256:
        raise ValueError(f"v0.48 VPCVW.OVR hash mismatch: {sha256(raw)}")
    patched = apply_guarded_patches(raw, VPCVW_PATCHES)
    if sha256(patched) != V49_VPCVW_SHA256:
        raise AssertionError(f"unexpected v0.49 VPCVW hash: {sha256(patched)}")
    return patched


def near_call(target: int, source: int) -> bytes:
    return b"\xE8" + ((target - (source + 3)) & 0xFFFF).to_bytes(2, "little")


def call_target(data: bytes, offset: int) -> int:
    if data[offset] != 0xE8:
        raise ValueError(f"expected CALL at 0x{offset:04X}")
    displacement = int.from_bytes(data[offset + 1 : offset + 3], "little", signed=True)
    return (OVERLAY_ORIGIN + offset + 3 + displacement) & 0xFFFF


def guarded_replace(data: bytearray, offset: int, expected: bytes, replacement: bytes, label: str) -> None:
    if len(expected) != len(replacement):
        raise ValueError(f"size-changing patch rejected: {label}")
    actual = bytes(data[offset : offset + len(expected)])
    if actual != expected:
        raise ValueError(
            f"{label}: unexpected bytes at 0x{offset:04X}: "
            f"expected {expected.hex(' ')}, got {actual.hex(' ')}"
        )
    data[offset : offset + len(replacement)] = replacement


def retarget_width_call(data: bytearray, offset: int, label: str) -> None:
    target = call_target(data, offset)
    if target != STRLEN_TARGET:
        raise ValueError(f"{label}: call targets 0x{target:04X}, not strlen 0x{STRLEN_TARGET:04X}")
    data[offset : offset + 3] = near_call(WIDTH_ADAPTER, OVERLAY_ORIGIN + offset)


def patch_vtrea(raw: bytes) -> tuple[bytes, list[dict[str, object]]]:
    if sha256(raw) != V48_VTREA_SHA256:
        raise ValueError(f"v0.48 VTREA.OVR hash mismatch: {sha256(raw)}")

    data = bytearray(raw)
    report: list[dict[str, object]] = []

    # (cell_width - strlen(text))*6 / 2 -> (cell_width*6 - rendered_width(text))/2
    for offset in VARIABLE_CENTER_SITES:
        label = f"VTREA variable button centering 0x{offset:04X}"
        retarget_width_call(data, offset, label)
        guarded_replace(
            data,
            offset + 3,
            bytes.fromhex("59 8B C8 8B 46 0C 2B C1 B9 06 00 F7 E9"),
            bytes.fromhex("59 8B C8 6B 46 0C 06 2B C1 90 90 90 90"),
            label,
        )
        report.append({"offset": f"0x{offset:04X}", "kind": "variable_center", "width_call": f"0x{WIDTH_ADAPTER:04X}"})

    # strlen(text)*6 / 2 -> rendered_width(text)/2
    for offset in HALF_WIDTH_SITES:
        label = f"VTREA half rendered width 0x{offset:04X}"
        retarget_width_call(data, offset, label)
        guarded_replace(
            data,
            offset + 3,
            bytes.fromhex("59 B9 06 00 F7 E9"),
            bytes.fromhex("59 90 90 90 90 90"),
            label,
        )
        report.append({"offset": f"0x{offset:04X}", "kind": "half_rendered_width", "width_call": f"0x{WIDTH_ADAPTER:04X}"})

    if call_target(data, LOGICAL_SITE_MUST_REMAIN) != STRLEN_TARGET:
        raise ValueError("VTREA logical strlen at 0x764D was unexpectedly modified")

    patched = bytes(data)
    if len(patched) != len(raw):
        raise AssertionError("VTREA size changed")
    if sha256(patched) != V49_VTREA_SHA256:
        raise AssertionError(f"unexpected v0.49 VTREA hash: {sha256(patched)}")
    return patched, report


def annotate_codebook(raw: bytes, audit: dict[str, object]) -> bytes:
    payload = json.loads(raw.decode("utf-8"))
    payload["read_buffer_fix"] = {
        "version": "v0.49",
        "reason": "VPCVW READ decoded-message buffer expanded to prevent Korean book-text stack overflow.",
        "old_buffer_bytes": OLD_BUFFER_BYTES,
        "new_buffer_bytes": NEW_BUFFER_BYTES,
        "book_of_fables_range": [BOOK_START_ID, BOOK_END_ID],
        "first_old_overflow_id": audit["first_old_overflow_id"],
        "book_max_decoded_bytes": audit["book_max_decoded_bytes"],
        "corpus_max_decoded_bytes": audit["corpus_max_decoded_bytes"],
    }
    payload["gameplay_choice_centering_fix"] = {
        "version": "v0.49",
        "reason": "Four VTREA display-only helpers used byte strlen * 6 instead of rendered Korean pixel width.",
        "rendered_width_adapter": f"0x{WIDTH_ADAPTER:04X}",
        "patched_sites": [f"0x{offset:04X}" for offset in (*VARIABLE_CENTER_SITES, *HALF_WIDTH_SITES)],
        "preserved_logical_strlen_site": f"0x{LOGICAL_SITE_MUST_REMAIN:04X}",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def write_deterministic_zip(path: Path, payloads: dict[str, bytes]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v48-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    source_game = args.v48_dir / "DSAVANT"
    if not source_game.is_dir():
        raise FileNotFoundError(f"v0.48 DSAVANT directory not found: {source_game}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    if sha256((source_game / "DS.EXE").read_bytes()) != V48_DS_SHA256:
        raise ValueError("DS.EXE is not the exact published v0.48 file required by the width adapter")

    audit = audit_read_buffer(source_game)
    source_vpcvw = (source_game / "VPCVW.OVR").read_bytes()
    source_vtrea = (source_game / "VTREA.OVR").read_bytes()
    patched_vpcvw = patch_vpcvw(source_vpcvw)
    patched_vtrea, ui_sites = patch_vtrea(source_vtrea)

    payloads: dict[str, bytes] = {}
    for path in sorted(args.v48_dir.iterdir()):
        if path.is_file() and path.name.startswith("UI_V") and path.suffix == ".json":
            payloads[path.name] = path.read_bytes()
    for path in sorted(source_game.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if path.name == "VPCVW.OVR":
            data = patched_vpcvw
        elif path.name == "VTREA.OVR":
            data = patched_vtrea
        elif path.name == "korean_codebook.json":
            data = annotate_codebook(data, audit)
        payloads[f"DSAVANT/{path.name}"] = data

    vpcvw_changed_offsets = [
        index
        for index, (before, after) in enumerate(zip(source_vpcvw, patched_vpcvw))
        if before != after
    ]
    vtrea_changed_offsets = [
        index
        for index, (before, after) in enumerate(zip(source_vtrea, patched_vtrea))
        if before != after
    ]

    report = {
        "format": "Wizardry VII DOS Korean v0.49 combined runtime hotfix",
        "base_release": "v0.48",
        "base_zip_sha256": V48_ZIP_SHA256,
        "read_buffer_audit": audit,
        "patch": {
            "target": "VPCVW.OVR",
            "source_sha256": V48_VPCVW_SHA256,
            "output_sha256": V49_VPCVW_SHA256,
            "changed_byte_offsets": [f"0x{offset:04X}" for offset in vpcvw_changed_offsets],
            "changed_byte_count": len(vpcvw_changed_offsets),
            "stack_frame_patch_offset": "0x3C7B",
            "buffer_reference_offsets": ["0x3CA5", "0x3CB9"],
        },
        "ui_patch": {
            "target": "VTREA.OVR",
            "source_sha256": V48_VTREA_SHA256,
            "output_sha256": V49_VTREA_SHA256,
            "changed_byte_offsets": [f"0x{offset:04X}" for offset in vtrea_changed_offsets],
            "changed_byte_count": len(vtrea_changed_offsets),
            "patched_sites": ui_sites,
            "rendered_width_adapter": f"0x{WIDTH_ADAPTER:04X}",
            "preserved_logical_strlen_site": f"0x{LOGICAL_SITE_MUST_REMAIN:04X}",
        },
        "preserved": {
            "ds_exe_sha256": sha256((source_game / "DS.EXE").read_bytes()),
            "msg_hdr_sha256": sha256((source_game / "MSG.HDR").read_bytes()),
            "msg_dbs_sha256": sha256((source_game / "MSG.DBS").read_bytes()),
            "misc_hdr_sha256": sha256((source_game / "MISC.HDR").read_bytes()),
            "scenario_dbs_sha256": sha256((source_game / "SCENARIO.DBS").read_bytes()),
            "vbfont0_vga_sha256": sha256((source_game / "VBFONT0.VGA").read_bytes()),
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    payloads["UI_V49_REPORT.json"] = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    (args.output_dir / "UI_V49_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
