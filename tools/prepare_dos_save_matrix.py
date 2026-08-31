#!/usr/bin/env python3
"""Prepare isolated Wizardry VII save-regression runtime variants."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile


SECURITY_VERIFY_OFFSET = 0x667B
SECURITY_VERIFY_CALL = bytes.fromhex("E8 4C 73")
SECURITY_FORCE_SUCCESS = bytes.fromhex("B8 01 00")
ASCII_DATA_FILES = {"MISC.HDR", "MSG.DBS", "MSG.HDR", "VBFONT0.VGA"}


def named_build(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("build must use NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in name):
        raise argparse.ArgumentTypeError(f"invalid build name: {name!r}")
    return name, Path(raw_path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_security(vbase_path: Path) -> None:
    data = bytearray(vbase_path.read_bytes())
    actual = bytes(data[SECURITY_VERIFY_OFFSET : SECURITY_VERIFY_OFFSET + 3])
    if actual != SECURITY_VERIFY_CALL:
        raise ValueError(
            f"unexpected original verifier bytes at 0x{SECURITY_VERIFY_OFFSET:04X}: "
            f"{actual.hex(' ')}"
        )
    data[SECURITY_VERIFY_OFFSET : SECURITY_VERIFY_OFFSET + 3] = SECURITY_FORCE_SUCCESS
    vbase_path.write_bytes(data)


def extract_original(original_zip: Path, target: Path) -> None:
    target.mkdir(parents=True)
    resolved_target = target.resolve()
    with ZipFile(original_zip) as archive:
        for member in archive.infolist():
            destination = (target / member.filename).resolve()
            if resolved_target not in destination.parents and destination != resolved_target:
                raise ValueError(f"archive path escapes output directory: {member.filename}")
        archive.extractall(target)


def overlay_payloads(source: Path, destination: Path, excluded: set[str] | None = None) -> None:
    excluded = excluded or set()
    for item in source.iterdir():
        if not item.is_file() or item.name in excluded or item.suffix.lower() == ".json":
            continue
        shutil.copy2(item, destination / item.name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--v37-dir", type=Path, required=True)
    parser.add_argument("--savegame", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--build",
        action="append",
        default=[],
        type=named_build,
        metavar="NAME=PATH",
        help="add a historical payload directory as an isolated runtime variant",
    )
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    base = args.output_dir / "_base_original"
    extract_original(args.original_zip, base)
    base_game = base / "DSAVANT"
    v37_game = args.v37_dir / "DSAVANT" if (args.v37_dir / "DSAVANT").is_dir() else args.v37_dir

    variants: dict[str, Path] = {}
    variant_names = [
        "original_security",
        "original_bigfont",
        "v37_ascii",
        "v37_full",
        *(name for name, _ in args.build),
    ]
    if len(variant_names) != len(set(variant_names)):
        raise ValueError("variant names must be unique")
    for name in variant_names:
        root = args.output_dir / name
        shutil.copytree(base, root)
        game = root / "DSAVANT"
        shutil.copy2(args.savegame, game / "SAVEGAME.DBS")
        shutil.copy2(args.scenario, game / "SCENARIO.HDR")
        variants[name] = game

    patch_security(variants["original_security"] / "VBASE.OVR")

    patch_security(variants["original_bigfont"] / "VBASE.OVR")
    shutil.copy2(v37_game / "VBFONT0.VGA", variants["original_bigfont"] / "VBFONT0.VGA")

    overlay_payloads(v37_game, variants["v37_ascii"], ASCII_DATA_FILES)
    overlay_payloads(v37_game, variants["v37_full"])

    for name, source in args.build:
        payload_dir = source / "DSAVANT" if (source / "DSAVANT").is_dir() else source
        if not payload_dir.is_dir():
            raise FileNotFoundError(f"build payload directory not found: {payload_dir}")
        overlay_payloads(payload_dir, variants[name])

    report = {
        "variants": {
            name: {
                file: {
                    "size": (game / file).stat().st_size,
                    "sha256": sha256(game / file),
                }
                for file in (
                    "DS.EXE",
                    "VBASE.OVR",
                    "VBFONT0.VGA",
                    "MSG.DBS",
                    "MISC.HDR",
                    "SAVEGAME.DBS",
                    "SCENARIO.HDR",
                )
            }
            for name, game in variants.items()
        }
    }
    (args.output_dir / "matrix_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
