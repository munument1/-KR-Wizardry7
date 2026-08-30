#!/usr/bin/env python3
"""Build a v37 diagnostic package with the v20 one-argument width adapter removed.

This is intentionally a diagnostic rollback, not a release candidate.

The v20 geometry pass placed WIDTH_ADAPTER at resident runtime 0xF790.  That
address is inside the overlay load window: VMAZE.OVR and VMNPC.OVR both contain
live bytes at the corresponding file offset.  Once either overlay is loaded,
the adapter body is overwritten, while later/smaller overlays can still retain
calls that target 0xF790.

For the save investigation we therefore restore only the v20 FORMULAS sites to
their original strlen*6 calculations and erase the 18-byte adapter.  Every
other v37 change remains intact, including the v19 FontResident renderer,
Korean messages/font, title picture, scene-parser fixes, save-slot text, and
security Enter bypass.

If this probe can save where stock v37 prints
"Memory unavailable loading picture.", the unsafe v20 adapter is isolated as
the immediate save-path regression.  Visual centering regressions are expected
in this diagnostic build and are not release blockers for the probe itself.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from build_dos_v19_baseline import expect_hash, read_original, sha256, write_deterministic_zip
from build_dos_v20_ui_complete import (
    FORMULAS,
    MZ_HEADER_SIZE,
    OVERLAY_ORIGIN,
    WIDTH_ADAPTER,
    patch_formula_set,
    width_adapter_bytes,
)


V37_HASHES = {
    "DS.EXE": "bb91ff02c2d3591dc21c11a01bef17cb06b97bb34f98fde8d17a0906a9f28136",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "MON63.PIC": "1f8b916f67ee9bd6fe60697c2f24cc8bb35b0e32622214cb3d9ddf1c2a410781",
    "MSG.DBS": "d01b044e5d2481ab26711e89b5fba07b18c7f1b3b9cc541a5e8b865d8d121373",
    "MSG.HDR": "643a73e4f518d55be84abe72579554590af6b2a89403320d623ab30ca39d0455",
    "VBASE.OVR": "9ecb4ed4d07d34649fbc44ec5835e32d774221a02244a10922f0a3d83f8f5eb2",
    "VBFONT0.VGA": "e425f17118abbc2d7599c61f89324ea9162939a97383f35d17c11e90d7cd4750",
    "VDOPT.OVR": "b2574cecefcc55f2b42cac509c4428f696da27cfdb558b44082a0b19e516be92",
    "VINIT.OVR": "63a88cc454817c243d3c6023107a86e2c6926dc9a38cd63e773843e1da96b2a6",
    "VMAZE.OVR": "7a17deb42cde8b6e82d0c4d401114bc4bb04261d5f8f3d24b8cd4456159a520a",
    "VMELE.OVR": "e56c555e3343fc869aa49fd8419e40a2271ee370de023f7ae8d453afa7a7e8a4",
    "VMEXE.OVR": "8058f9c1ed4d6409c9922969b57aa972864fa396c2d4bb7d353d8a5ec580d3da",
    "VMEXT.OVR": "e9f9f77d1312b370e146e2d4f86edd7dea7cbbf36a10af04168fdfb7f7222029",
    "VMNPC.OVR": "dfedb6b59cb12bc3d79e54f0e163969bd7dfe39b76a12a7d0a9abb02677d7fb1",
    "VPCLV.OVR": "2f83def79e4027ea65eea40b44fac7782a99140f6bbf02c7aa385f93827ab9fd",
    "VPCMK.OVR": "36b50daea346973750a0cc9c9b18c7b222f216cc73662e01e7c1dd1ee52a625f",
    "VPCVW.OVR": "d3e7efbbdff13860acdb47c36cf9428d5a6e3533a5b382d57cb6cd327e216197",
    "VPOPS.OVR": "cb554c9af7d5e105e96fe89adb654dd80f2daabffe5228bbe7aa2adce02819ee",
    "VTREA.OVR": "954cba83a89a90fab919ce8af72191d6c6a92d894c516f7fd1303934395ce045",
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
}


def formula_reference(name: str, original: bytes) -> tuple[bytes, bytes, set[int]]:
    """Return original, v20-formula-patched reference, and changed byte indices."""
    if name == "DS.EXE":
        original_view = original[MZ_HEADER_SIZE:]
        patched_view, _ = patch_formula_set(name, original_view, 0)
    else:
        original_view = original
        patched_view, _ = patch_formula_set(name, original_view, OVERLAY_ORIGIN)
    changed = {
        index
        for index, (before, after) in enumerate(zip(original_view, patched_view))
        if before != after
    }
    if not changed:
        raise ValueError(f"{name}: expected v20 formula mutations, found none")
    return original_view, patched_view, changed


def rollback_formula_sites(name: str, current: bytes, original: bytes) -> tuple[bytes, int]:
    original_view, patched_view, changed = formula_reference(name, original)
    output = bytearray(current)
    base = MZ_HEADER_SIZE if name == "DS.EXE" else 0

    for index in sorted(changed):
        current_index = base + index
        actual = output[current_index]
        expected = patched_view[index]
        if actual != expected:
            raise ValueError(
                f"{name}: v37 byte at 0x{current_index:X} no longer matches the "
                f"v20 formula patch (expected {expected:02X}, found {actual:02X})"
            )
        output[current_index] = original_view[index]

    return bytes(output), len(changed)


def erase_width_adapter(ds_exe: bytes) -> bytes:
    output = bytearray(ds_exe)
    adapter = width_adapter_bytes()
    start = MZ_HEADER_SIZE + WIDTH_ADAPTER
    actual = bytes(output[start : start + len(adapter)])
    if actual != adapter:
        raise ValueError(
            "v37 DS.EXE does not contain the guarded v20 width adapter at 0xF790"
        )
    output[start : start + len(adapter)] = b"\x00" * len(adapter)
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v37-dir", type=Path, required=True)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    source_dir = args.v37_dir / "DSAVANT" if (args.v37_dir / "DSAVANT").is_dir() else args.v37_dir
    current: dict[str, bytes] = {}
    for name, expected_hash in V37_HASHES.items():
        data = (source_dir / name).read_bytes()
        expect_hash(f"v37 {name}", data, expected_hash)
        current[name] = data

    with zipfile.ZipFile(args.original_zip) as archive:
        originals = {name: read_original(archive, name) for name in FORMULAS}

    payloads = dict(current)
    changed_counts: dict[str, int] = {}
    for name in FORMULAS:
        rolled_back, count = rollback_formula_sites(name, payloads[name], originals[name])
        payloads[name] = rolled_back
        changed_counts[name] = count

    payloads["DS.EXE"] = erase_width_adapter(payloads["DS.EXE"])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / "DSAVANT" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    report = {
        "format": "Wizardry VII DOS v37 save probe: no v20 width adapter",
        "purpose": (
            "diagnose whether the overlay-overwritten 0xF790 width adapter is the "
            "immediate cause of the save-path VGA picture allocation failure"
        ),
        "changes": [
            "restore every v20 FORMULAS site to its original strlen*6 calculation",
            "erase the 18-byte WIDTH_ADAPTER at resident runtime 0xF790",
            "preserve all unrelated v37 bytes and payload sizes",
        ],
        "expected_probe_regressions": [
            "some Korean UI centering/spacing may temporarily revert to 6px Latin assumptions",
            "this package is for save/load diagnosis only and must not be shipped as a release",
        ],
        "formula_bytes_restored": changed_counts,
        "payloads": {
            f"DSAVANT/{name}": {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    report_name = "SAVE_PROBE_NO_WIDTH_ADAPTER_REPORT.json"
    (args.output_dir / report_name).write_bytes(report_raw)

    zip_payloads = {f"DSAVANT/{name}": data for name, data in payloads.items()}
    zip_payloads[report_name] = report_raw
    write_deterministic_zip(args.zip_output, zip_payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
