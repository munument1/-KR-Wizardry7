#!/usr/bin/env python3
"""Build v41 by fixing the malformed localized roster tail at its source.

The Add Character / character-roster record is a fixed 20-byte row.  The DOS
code loads message 140/141 (localized as 남성/여성) and copies only the first
*byte* into the row, then appends '-' and the first three bytes of the
profession message.  Because a Korean glyph is encoded as 0x17 + two ranked
bytes, the row becomes syntactically malformed:

    0x17 '-' 0x17 pair pair NUL

The normal resident string renderer then consumes the '-' and the profession
escape as the missing pair bytes of the gender glyph, so both gender and
profession appear as garbage.  v40 incorrectly targeted the single-character
renderer; this roster is rendered as a normal string, so that patch could not
change the symptom.

v41 keeps the compact one-byte gender field but points the roster-only lookup
at the game's existing ASCII gender table: message 455 begins with 'M' and
message 456 begins with 'F'.  The existing three-byte profession copy then
starts on a clean ESC boundary and renders its first Korean glyph correctly.
No message translations or other screens are changed.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from build_dos_v19_baseline import BytePatch, apply_guarded_patches, expect_hash, sha256, write_deterministic_zip
from build_dos_v38_resident_ui_helpers import V37_HASHES
from extract_gold_messages import extract_messages, parse_header


V39_VBASE_HASH = "c21ff28c56e2290d224d9d4ca0ab3b1d485b4803b1e1b3d036a9afb1ad9c2612"
V39_VPCMK_HASH = "79b32bcf235f460a0c644f164983e9ad98537214bd18748eebb16da61d2df2bf"
V39_VBFONT_HASH = "cadaaaf4c25e9f807cd303770c5291ca3a1311511b9d1ae111439ad64d22dc35"

ROSTER_GENDER_MESSAGE_BASE = 455
PROFESSION_MESSAGE_BASE = 120
PROFESSION_COUNT = 14

VBASE_GENDER_SOURCE_PATCH = BytePatch(
    "VBASE roster gender source 140/141 -> ASCII table 455/456",
    0x5FA3,
    bytes.fromhex("05 8C 00"),
    bytes.fromhex("05 C7 01"),
)
VPCMK_GENDER_SOURCE_PATCH = BytePatch(
    "VPCMK roster gender source 140/141 -> ASCII table 455/456",
    0x6975,
    bytes.fromhex("05 8C 00"),
    bytes.fromhex("05 C7 01"),
)


def verify_roster_message_tables(source_dir: Path) -> dict[str, object]:
    misc = (source_dir / "MISC.HDR").read_bytes()
    _, entries, _ = parse_header((source_dir / "MSG.HDR").read_bytes(), "dos")
    records = extract_messages((source_dir / "MSG.DBS").read_bytes(), entries, misc)
    by_id = {record.message_id: base64.b64decode(record.raw_base64) for record in records}

    male = by_id[ROSTER_GENDER_MESSAGE_BASE]
    female = by_id[ROSTER_GENDER_MESSAGE_BASE + 1]
    if not male.startswith(b"M") or not female.startswith(b"F"):
        raise ValueError(
            "expected message 455/456 to begin with ASCII M/F, found "
            f"{male[:4].hex(' ')} / {female[:4].hex(' ')}"
        )

    profession_prefixes: dict[str, str] = {}
    for message_id in range(PROFESSION_MESSAGE_BASE, PROFESSION_MESSAGE_BASE + PROFESSION_COUNT):
        raw = by_id[message_id]
        if len(raw) < 3 or raw[0] != 0x17:
            raise ValueError(
                f"profession message {message_id} no longer starts with a complete Korean glyph: "
                f"{raw[:6].hex(' ')}"
            )
        profession_prefixes[str(message_id)] = raw[:3].hex(" ").upper()

    return {
        "gender_messages": {
            str(ROSTER_GENDER_MESSAGE_BASE): male[:2].decode("ascii", errors="replace"),
            str(ROSTER_GENDER_MESSAGE_BASE + 1): female[:14].decode("ascii", errors="replace"),
        },
        "profession_prefixes": profession_prefixes,
    }


def patch_roster_file(name: str, source: bytes) -> bytes:
    if name == "VBASE.OVR":
        expect_hash("v39 VBASE.OVR", source, V39_VBASE_HASH)
        return apply_guarded_patches(source, (VBASE_GENDER_SOURCE_PATCH,))
    if name == "VPCMK.OVR":
        expect_hash("v39 VPCMK.OVR", source, V39_VPCMK_HASH)
        return apply_guarded_patches(source, (VPCMK_GENDER_SOURCE_PATCH,))
    if name == "VBFONT0.VGA":
        # v41 deliberately starts from v39, dropping the ineffective v40
        # resident_char experiment entirely.
        expect_hash("v39 VBFONT0.VGA", source, V39_VBFONT_HASH)
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v39-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    source_dir = args.v39_dir / "DSAVANT" if (args.v39_dir / "DSAVANT").is_dir() else args.v39_dir
    message_tables = verify_roster_message_tables(source_dir)

    payloads: dict[str, bytes] = {}
    for name in V37_HASHES:
        source = (source_dir / name).read_bytes()
        payloads[f"DSAVANT/{name}"] = patch_roster_file(name, source)

    report = {
        "format": "Wizardry VII DOS v41 roster record boundary fix",
        "v40_correction": [
            "v40 targeted resident_char, but the affected roster row is rendered through the normal string path",
            "the corruption is already present in the 20-byte row before rendering",
        ],
        "root_cause": [
            "localized gender messages 140/141 begin with Korean escape byte 0x17",
            "the roster constructor copies only one byte of gender, then '-' and three profession bytes",
            "resident_string therefore sees malformed bytes 0x17 '-' 0x17 ... and loses synchronization",
        ],
        "changes": [
            "VBASE roster-only gender lookup base changed from message 140 to 455",
            "VPCMK roster-only gender lookup base changed from message 140 to 455",
            "message 455/456 supply one-byte ASCII M/F without changing the localized sex menu",
            "the existing three-byte profession prefix now begins at a valid Korean escape boundary",
            "v41 is built from exact v0.39 and does not include the ineffective v40 resident_char helper",
        ],
        "expected_roster_suffix": ["M-전", "F-마", "M-사", "F-닌"],
        "message_table_verification": message_tables,
        "invariants": [
            "only three bytes change in VBASE.OVR and three bytes in VPCMK.OVR",
            "all file sizes remain unchanged",
            "MSG.HDR/MSG.DBS/MISC.HDR, translations, codebook, DS.EXE, save format, and VBFONT0 remain v0.39",
        ],
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V41_REPORT.json"] = report_raw

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
