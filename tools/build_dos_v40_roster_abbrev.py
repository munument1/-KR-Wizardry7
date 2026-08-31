#!/usr/bin/env python3
"""Build v40 with Korean-safe race/profession abbreviations in character rosters.

The DOS Add Character roster abbreviates race/profession text by drawing the
first three *bytes* through the single-character renderer.  A localized Korean
glyph is also three bytes (0x17 + ranked pair), so v39 displays those bytes as
three unrelated symbols.  v40 keeps the original three-byte roster loops and
adds a tiny resident stream decoder to the character-render entry instead.

Ordinary ASCII character calls are unchanged.  Only an ESC + pair sequence
arriving over three consecutive character-render calls is coalesced into one
slot-127 Korean glyph.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from build_dos_v19_baseline import expect_hash, sha256, write_deterministic_zip
from build_dos_v38_resident_ui_helpers import V37_HASHES


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "dos_v40" / "roster_char_stream.S"

CHAR_ENTRY = 0x0910
CHAR_CONTINUATION = 0x0913
ROSTER_STREAM_HELPER = 0x0B70
FONT_INVERSE_TABLE = 0x0D00
V39_FONT_DISPATCHER_END = 0x0B6C
CHAR_ENTRY_EXPECTED = bytes.fromhex("55 89 E5")
V39_VBFONT_HASH = "cadaaaf4c25e9f807cd303770c5291ca3a1311511b9d1ae111439ad64d22dc35"


def near_jump(target: int, source: int) -> bytes:
    displacement = target - (source + 3)
    if not -0x8000 <= displacement <= 0x7FFF:
        raise ValueError("near jump target out of range")
    return b"\xE9" + (displacement & 0xFFFF).to_bytes(2, "little")


def assemble_roster_stream(source: Path = SOURCE) -> bytes:
    if not source.is_file():
        raise FileNotFoundError(source)
    required = ("as", "ld", "objcopy")
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            "GNU binutils are required to assemble the v40 resident helper: "
            + ", ".join(missing)
        )

    with tempfile.TemporaryDirectory(prefix="wiz7_v40_") as temp_name:
        temp = Path(temp_name)
        obj = temp / "roster_char_stream.o"
        elf = temp / "roster_char_stream.elf"
        raw = temp / "roster_char_stream.bin"
        subprocess.run(
            ["as", "--32", "-o", str(obj), str(source)],
            check=True,
        )
        subprocess.run(
            [
                "ld",
                "-m",
                "elf_i386",
                "-Ttext",
                f"0x{ROSTER_STREAM_HELPER:X}",
                "-e",
                "roster_char_stream",
                "-o",
                str(elf),
                str(obj),
            ],
            check=True,
        )
        subprocess.run(
            ["objcopy", "-O", "binary", "-j", ".text", str(elf), str(raw)],
            check=True,
        )
        helper = raw.read_bytes()

    if not helper:
        raise ValueError("assembled v40 roster helper is empty")
    if ROSTER_STREAM_HELPER < V39_FONT_DISPATCHER_END:
        raise AssertionError("v40 helper overlaps the v39 resident dispatcher")
    if ROSTER_STREAM_HELPER + len(helper) > FONT_INVERSE_TABLE:
        raise ValueError(
            "v40 roster helper overlaps the resident inverse table: "
            f"0x{ROSTER_STREAM_HELPER + len(helper):04X} > 0x{FONT_INVERSE_TABLE:04X}"
        )
    return helper


def patch_font_resident(vbfont0: bytes, helper: bytes) -> bytes:
    expect_hash("v39 VBFONT0.VGA", vbfont0, V39_VBFONT_HASH)
    data = bytearray(vbfont0)

    actual_entry = bytes(data[CHAR_ENTRY : CHAR_ENTRY + 3])
    if actual_entry != CHAR_ENTRY_EXPECTED:
        raise ValueError(
            "resident_char entry no longer matches v39: "
            f"expected {CHAR_ENTRY_EXPECTED.hex(' ')}, got {actual_entry.hex(' ')}"
        )

    destination = bytes(
        data[ROSTER_STREAM_HELPER : ROSTER_STREAM_HELPER + len(helper)]
    )
    if destination != b"\x00" * len(helper):
        raise ValueError("v40 resident helper destination is not empty")

    data[CHAR_ENTRY : CHAR_ENTRY + 3] = near_jump(
        ROSTER_STREAM_HELPER, CHAR_ENTRY
    )
    data[ROSTER_STREAM_HELPER : ROSTER_STREAM_HELPER + len(helper)] = helper
    return bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v39-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    source_dir = (
        args.v39_dir / "DSAVANT"
        if (args.v39_dir / "DSAVANT").is_dir()
        else args.v39_dir
    )
    helper = assemble_roster_stream()

    payloads: dict[str, bytes] = {}
    for name in V37_HASHES:
        source = (source_dir / name).read_bytes()
        if name == "VBFONT0.VGA":
            source = patch_font_resident(source, helper)
        payloads[f"DSAVANT/{name}"] = source

    report = {
        "format": "Wizardry VII DOS v40 Korean roster abbreviation fix",
        "root_cause": [
            "Add Character race/profession abbreviations draw three bytes one at a time",
            "one Korean glyph is encoded as 0x17 plus two ranked bytes",
            "v39 therefore rendered the encoded bytes as unrelated symbols",
        ],
        "changes": [
            "redirect resident_char entry 0x0910 to a helper at VBFONT0 0x0B70",
            "coalesce consecutive ESC/rank/rank character calls into one Korean slot-127 glyph",
            "resume the original resident_char body at 0x0913 for ordinary ASCII and the decoded glyph",
            "leave the original three-byte race/profession abbreviation loops unchanged",
        ],
        "layout": {
            "resident_char_entry": f"0x{CHAR_ENTRY:04X}",
            "resident_char_continuation": f"0x{CHAR_CONTINUATION:04X}",
            "v39_dispatcher_end": f"0x{V39_FONT_DISPATCHER_END:04X}",
            "roster_stream_helper": f"0x{ROSTER_STREAM_HELPER:04X}",
            "roster_stream_helper_end": f"0x{ROSTER_STREAM_HELPER + len(helper):04X}",
            "font_inverse_table": f"0x{FONT_INVERSE_TABLE:04X}",
        },
        "helper": {
            "size": len(helper),
            "sha256": sha256(helper),
        },
        "invariants": [
            "VBFONT0.VGA file size is unchanged",
            "v39 width/scene dispatcher at 0x0AF0..0x0B6B is untouched",
            "inverse table at 0x0D00 and glyph table at 0x0E00 are untouched",
            "DS.EXE, OVR files, message banks, codebook, save format, and overlay sizes are unchanged",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V40_REPORT.json"] = report_raw

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
