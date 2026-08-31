#!/usr/bin/env python3
"""Rebuild the verified Wizardry VII DOS v19 Korean baseline package.

Purchased game files are read from a user-supplied pristine GOG archive and
are never stored in the repository.  The synchronized message/font assets are
read from an existing verified localization directory.  Every source hash,
patch-site byte sequence, output size, and final payload hash is guarded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BytePatch:
    label: str
    offset: int
    expected: bytes
    replacement: bytes


ORIGINAL_HASHES = {
    "DS.EXE": "14a94f85cb4ef4df08566ed165dddc88c363aa816360c6509b84f079866a43db",
    "VPCMK.OVR": "dd1bcb9a54943163237ff48644c021ea202c36c15858fd7fd71520a5f871d28b",
    "VPCVW.OVR": "8dc7006599844bfd33ae60e11b59f7cedf47d649d84669fdf2546ed15779224d",
}

BASELINE_HASHES = {
    "DS.EXE": "10200dbc8ca3bd3af3d486cfbc37961fc9c21ff6908d1f5d6474fac2424a184c",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "MSG.DBS": "6e316eb669047b4a998694ed3c314879a7e2890c749619d43d0d03e18a8ae4dc",
    "MSG.HDR": "94622ce99f0e442df9823abcc522d72e3c0ef41d066934a4af090211c0a5525d",
    "VBFONT0.VGA": "e425f17118abbc2d7599c61f89324ea9162939a97383f35d17c11e90d7cd4750",
    "VPCMK.OVR": "702211c25215eb0e1e3d4a9a0373afa83c15b963ec1912f74a3c1055c878b04e",
    "VPCVW.OVR": "473f2d703e7a9f608f63e69a153fbdbd31ddfb86ff55d6743f2d59f51d457a83",
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
}

DS_PATCHES = (
    BytePatch("allocate 80-byte second font stride", 0x38FD, b"\xFE", b"\xFC"),
    BytePatch(
        "v19 character trampoline",
        0x3A77,
        bytes.fromhex(
            "55 8B EC FC 8B 46 06 BB 4A 36 D1 E0 03 D8 2E 8B 07 0B C0 "
            "74 05 2E FF 1E B3 2D 8B E5 5D"
        ),
        bytes.fromhex(
            "2E A1 4A 36 85 C0 74 14 89 E3 FF 77 04 FF 77 02 0E 68 90 "
            "38 50 68 10 09 CB 83 C4 04 C3"
        ),
    ),
    BytePatch(
        "v19 string trampoline",
        0x3A95,
        bytes.fromhex(
            "55 8B EC FC 83 EC 04 56 06 1E 8C D8 8E C0 8B 76 04 89 76 "
            "FE 8B 76 FE 83 46 FE 01 33 C0 AC 0A C0 74 0C FF 76 06 50"
        ),
        bytes.fromhex(
            "55 89 E5 83 EC 04 2E A1 4A 36 85 C0 74 14 C7 46 FC 37 09 "
            "89 46 FE FF 76 06 FF 76 04 FF 5E FC 83 C4 04 89 EC 5D C3"
        ),
    ),
    BytePatch(
        "v19 rendered-width trampoline",
        0x3ACA,
        bytes.fromhex(
            "55 8B EC FC 83 EC 02 06 56 8C D8 8E C0 B9 FF FF 8B 46 06 "
            "BB 4A 36 D1 E0 03 D8 2E 8B 07 0B C0 74 2E 8E C0 33 DB 26 "
            "8A 47 07 98"
        ),
        bytes.fromhex(
            "55 89 E5 83 EC 04 2E A1 4A 36 85 C0 74 16 C7 46 FC 30 0A "
            "89 46 FE FF 76 06 FF 76 04 FF 5E FC 83 C4 04 EB 02 31 C0 "
            "89 EC 5D C3"
        ),
    ),
)

VPCMK_PATCHES = (
    BytePatch("expand character-modal stack frame", 0x0ABB, b"\xB8\xC8\xFF", b"\xB8\xA0\xFF"),
    *(BytePatch(f"relocate modal scratch buffer {offset:#06x}", offset, b"\x8D\x46\xCA", b"\x8D\x46\xA0")
      for offset in (0x0B22, 0x0B2F, 0x0B52, 0x0B61, 0x0B84, 0x0B94)),
    BytePatch("creation stat row stride 6->7", 0x19D7, b"\xB8\x06\x00", b"\xB8\x07\x00"),
    BytePatch("creation stat row base 35->32", 0x19DD, b"\x05\x23\x00", b"\x05\x20\x00"),
)

VPCVW_PATCHES = (
    BytePatch("review stat row stride 6->7", 0x12B3, b"\xB8\x06\x00", b"\xB8\x07\x00"),
    BytePatch("review stat row base 35->32", 0x12B9, b"\x05\x23\x00", b"\x05\x20\x00"),
)

PATCHES_BY_FILE = {
    "DS.EXE": DS_PATCHES,
    "VPCMK.OVR": VPCMK_PATCHES,
    "VPCVW.OVR": VPCVW_PATCHES,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expect_hash(label: str, data: bytes, expected: str) -> None:
    actual = sha256(data)
    if actual != expected:
        raise ValueError(f"{label}: expected SHA-256 {expected}, found {actual}")


def apply_guarded_patches(data: bytes, patches: tuple[BytePatch, ...]) -> bytes:
    output = bytearray(data)
    occupied: set[int] = set()
    for patch in patches:
        if len(patch.expected) != len(patch.replacement):
            raise ValueError(f"{patch.label}: patch changes file size")
        locations = set(range(patch.offset, patch.offset + len(patch.expected)))
        if occupied & locations:
            raise ValueError(f"{patch.label}: patch overlaps an earlier patch")
        occupied |= locations
        actual = bytes(output[patch.offset:patch.offset + len(patch.expected)])
        if actual != patch.expected:
            raise ValueError(
                f"{patch.label} at 0x{patch.offset:X}: expected "
                f"{patch.expected.hex(' ')}, found {actual.hex(' ')}"
            )
        output[patch.offset:patch.offset + len(patch.replacement)] = patch.replacement
    if len(output) != len(data):
        raise AssertionError("guarded patches changed the file size")
    return bytes(output)


def read_original(archive: zipfile.ZipFile, name: str) -> bytes:
    candidates = [entry for entry in archive.namelist() if entry.replace("\\", "/").upper().endswith(f"/DSAVANT/{name}".upper())]
    if not candidates:
        direct = f"DSAVANT/{name}"
        candidates = [entry for entry in archive.namelist() if entry.replace("\\", "/").upper() == direct.upper()]
    if len(candidates) != 1:
        raise ValueError(f"expected one DSAVANT/{name} entry, found {candidates}")
    return archive.read(candidates[0])


def write_deterministic_zip(path: Path, payloads: dict[str, bytes]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--localized-assets-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    payloads: dict[str, bytes] = {}
    patch_report: dict[str, list[dict[str, object]]] = {}
    with zipfile.ZipFile(args.original_zip) as archive:
        for name, patches in PATCHES_BY_FILE.items():
            source = read_original(archive, name)
            expect_hash(f"original {name}", source, ORIGINAL_HASHES[name])
            payloads[name] = apply_guarded_patches(source, patches)
            patch_report[name] = [
                {
                    "label": patch.label,
                    "offset": f"0x{patch.offset:X}",
                    "expected": patch.expected.hex(" ").upper(),
                    "replacement": patch.replacement.hex(" ").upper(),
                }
                for patch in patches
            ]

    localized_names = set(BASELINE_HASHES) - set(PATCHES_BY_FILE)
    for name in localized_names:
        data = (args.localized_assets_dir / name).read_bytes()
        expect_hash(f"localized asset {name}", data, BASELINE_HASHES[name])
        payloads[name] = data

    for name, data in payloads.items():
        expect_hash(f"baseline output {name}", data, BASELINE_HASHES[name])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (args.output_dir / name).write_bytes(data)

    report = {
        "format": "Wizardry VII DOS v19 clean Korean baseline",
        "original_zip": str(args.original_zip.resolve()),
        "localized_assets_dir": str(args.localized_assets_dir.resolve()),
        "payloads": {
            name: {"size": len(payloads[name]), "sha256": sha256(payloads[name])}
            for name in sorted(payloads)
        },
        "patches": patch_report,
        "all_baseline_hashes_match": True,
    }
    report_path = args.output_dir.parent / f"{args.output_dir.name}_BUILD_REPORT.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    if args.zip_output:
        write_deterministic_zip(args.zip_output, payloads)
        report["zip_output"] = str(args.zip_output.resolve())
        report["zip_sha256"] = sha256(args.zip_output.read_bytes())
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
