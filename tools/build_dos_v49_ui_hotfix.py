#!/usr/bin/env python3
"""Build a targeted Wizardry VII DOS v0.49 gameplay UI hotfix.

The v0.48 upper-half VTREA menu helpers still centered text with byte strlen
multiplied by six.  Korean glyphs use a three-byte escape sequence, so long
button labels were shifted far to the left.  This pass changes only four
proven display-coordinate call sites to the resident rendered-width adapter.
Logical length paths (notably VTREA 0x764D) are deliberately untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

OVERLAY_ORIGIN = 0x5047
STRLEN_TARGET = 0x4AD7
WIDTH_ADAPTER = 0x38F4

V48_VTREA_SHA256 = "663b0a905737c214cdd89a4b1d2f2d6a979d63bfab76fecc716df5851eb0b8da"
V48_DS_SHA256 = "54fa02f1e91b3086f2f8283fcbed07d21da8a86285be72c08806f23833b2d112"
PATCHED_VTREA_SHA256 = "23cb96744b68998fddb1c8bf5b1fa61f9eca18f492f58318f324861b0217570a"

VARIABLE_CENTER_SITES = (0x8356, 0x8603)
HALF_WIDTH_SITES = (0x84FB, 0x8C46)
LOGICAL_SITE_MUST_REMAIN = 0x764D


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def near_call(target: int, source: int) -> bytes:
    return b"\xE8" + ((target - (source + 3)) & 0xFFFF).to_bytes(2, "little")


def call_target(data: bytes, offset: int) -> int:
    if data[offset] != 0xE8:
        raise ValueError(f"expected CALL at 0x{offset:04X}")
    displacement = int.from_bytes(data[offset + 1:offset + 3], "little", signed=True)
    return (OVERLAY_ORIGIN + offset + 3 + displacement) & 0xFFFF


def guarded_replace(data: bytearray, offset: int, expected: bytes, replacement: bytes, label: str) -> None:
    if len(expected) != len(replacement):
        raise ValueError(f"size-changing patch rejected: {label}")
    actual = bytes(data[offset:offset + len(expected)])
    if actual != expected:
        raise ValueError(
            f"{label}: unexpected bytes at 0x{offset:04X}: "
            f"expected {expected.hex(' ')}, got {actual.hex(' ')}"
        )
    data[offset:offset + len(replacement)] = replacement


def retarget_width_call(data: bytearray, offset: int, label: str) -> None:
    target = call_target(data, offset)
    if target != STRLEN_TARGET:
        raise ValueError(f"{label}: call targets 0x{target:04X}, not strlen 0x{STRLEN_TARGET:04X}")
    data[offset:offset + 3] = near_call(WIDTH_ADAPTER, OVERLAY_ORIGIN + offset)


def patch_vtrea(source: bytes) -> tuple[bytes, list[dict[str, object]]]:
    data = bytearray(source)
    report: list[dict[str, object]] = []

    # (cell_width - strlen(text))*6 / 2  -> (cell_width*6 - rendered_width(text))/2
    for offset in VARIABLE_CENTER_SITES:
        label = f"VTREA variable button centering 0x{offset:04X}"
        retarget_width_call(data, offset, label)
        cursor = offset + 3
        guarded_replace(
            data,
            cursor,
            bytes.fromhex("59 8B C8 8B 46 0C 2B C1 B9 06 00 F7 E9"),
            bytes.fromhex("59 8B C8 6B 46 0C 06 2B C1 90 90 90 90"),
            label,
        )
        report.append({"offset": offset, "kind": "variable_center", "width_call": WIDTH_ADAPTER})

    # strlen(text)*6 / 2 -> rendered_width(text)/2
    for offset in HALF_WIDTH_SITES:
        label = f"VTREA half rendered width 0x{offset:04X}"
        retarget_width_call(data, offset, label)
        cursor = offset + 3
        guarded_replace(
            data,
            cursor,
            bytes.fromhex("59 B9 06 00 F7 E9"),
            bytes.fromhex("59 90 90 90 90 90"),
            label,
        )
        report.append({"offset": offset, "kind": "half_rendered_width", "width_call": WIDTH_ADAPTER})

    # Guard the nearby logical/grid-count path against accidental broad fixes.
    if call_target(data, LOGICAL_SITE_MUST_REMAIN) != STRLEN_TARGET:
        raise ValueError("VTREA logical strlen at 0x764D was unexpectedly modified")

    patched = bytes(data)
    if len(patched) != len(source):
        raise AssertionError("VTREA size changed")
    return patched, report


def write_deterministic_zip(path: Path, root: Path) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(p for p in root.rglob("*") if p.is_file()):
            name = file.relative_to(root).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, file.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v48-dir", type=Path, required=True, help="extracted v0.48 package root")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    game = args.v48_dir / "DSAVANT"
    vtrea_path = game / "VTREA.OVR"
    ds_path = game / "DS.EXE"
    if not vtrea_path.is_file() or not ds_path.is_file():
        raise FileNotFoundError("v0.48 DSAVANT/VTREA.OVR or DS.EXE missing")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    source_vtrea = vtrea_path.read_bytes()
    source_ds = ds_path.read_bytes()
    if sha256(source_vtrea) != V48_VTREA_SHA256:
        raise ValueError("VTREA.OVR is not the exact published v0.48 file")
    if sha256(source_ds) != V48_DS_SHA256:
        raise ValueError("DS.EXE is not the exact published v0.48 file")

    patched_vtrea, patches = patch_vtrea(source_vtrea)
    if sha256(patched_vtrea) != PATCHED_VTREA_SHA256:
        raise AssertionError("patched VTREA hash differs from reviewed hotfix")

    shutil.copytree(args.v48_dir, args.output_dir)
    output_game = args.output_dir / "DSAVANT"
    (output_game / "VTREA.OVR").write_bytes(patched_vtrea)

    report = {
        "format": "Wizardry VII DOS Korean v0.49 UI hotfix test",
        "base_release": "v0.48",
        "reason": "Korean gameplay button labels used byte strlen * 6 for centering in late VTREA helpers",
        "source_vtrea_sha256": V48_VTREA_SHA256,
        "patched_vtrea_sha256": PATCHED_VTREA_SHA256,
        "patched_sites": patches,
        "preserved_logical_strlen_site": f"0x{LOGICAL_SITE_MUST_REMAIN:04X}",
        "book_crash_status": "not fixed by this UI-only build; message-bank and Korean escape structure validated separately",
    }
    (args.output_dir / "UI_V49_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    write_deterministic_zip(args.zip_output, args.output_dir)
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
