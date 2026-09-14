#!/usr/bin/env python3
"""Build Wizardry VII DOS Korean v0.49 with a safe readable-text buffer.

The item READ path in VPCVW.OVR decodes each readable-book message into an
86-byte stack buffer at BP-0x56.  The stock English Book of Fables records fit,
but Korean ESC+rank+rank encoding expands several records beyond the buffer;
message 21606 is the first overflowing Book of Fables record and 21633 reaches
111 decoded bytes.  The DOS message decoder also writes a two-byte terminator,
so these records overwrite the caller frame and eventually crash while reading.

v0.49 enlarges only this VPCVW readable-text scratch buffer from 86 to 127
bytes, the largest size addressable with the existing signed disp8 LEA.  All
v0.48 messages and gameplay data remain byte-identical.
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
        raise ValueError(
            f"v0.48 VPCVW.OVR hash mismatch: {sha256(raw)}"
        )
    patched = apply_guarded_patches(raw, VPCVW_PATCHES)
    if sha256(patched) != V49_VPCVW_SHA256:
        raise AssertionError(f"unexpected v0.49 VPCVW hash: {sha256(patched)}")
    return patched


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

    audit = audit_read_buffer(source_game)
    source_vpcvw = (source_game / "VPCVW.OVR").read_bytes()
    patched_vpcvw = patch_vpcvw(source_vpcvw)

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
        elif path.name == "korean_codebook.json":
            data = annotate_codebook(data, audit)
        payloads[f"DSAVANT/{path.name}"] = data

    changed_offsets = [
        index
        for index, (before, after) in enumerate(zip(source_vpcvw, patched_vpcvw))
        if before != after
    ]
    report = {
        "format": "Wizardry VII DOS Korean v0.49 readable-text stack buffer fix",
        "base_release": "v0.48",
        "base_zip_sha256": V48_ZIP_SHA256,
        "read_buffer_audit": audit,
        "patch": {
            "target": "VPCVW.OVR",
            "source_sha256": V48_VPCVW_SHA256,
            "output_sha256": V49_VPCVW_SHA256,
            "changed_byte_offsets": [f"0x{offset:04X}" for offset in changed_offsets],
            "changed_byte_count": len(changed_offsets),
            "stack_frame_patch_offset": "0x3C7B",
            "buffer_reference_offsets": ["0x3CA5", "0x3CB9"],
        },
        "preserved": {
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
