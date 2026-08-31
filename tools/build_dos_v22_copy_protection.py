#!/usr/bin/env python3
"""Package v21 UI fixes with the corrected copy-protection ordinal message."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_dos_v19_baseline import expect_hash, sha256, write_deterministic_zip


V21_HASHES = {
    "DS.EXE": "12dba1d6ea9ddf12dea5027498b33864b9e865b6ef3126ddbea520998fe6dc3e",
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "MSG.DBS": "6e316eb669047b4a998694ed3c314879a7e2890c749619d43d0d03e18a8ae4dc",
    "MSG.HDR": "94622ce99f0e442df9823abcc522d72e3c0ef41d066934a4af090211c0a5525d",
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

V22_MESSAGE_HASHES = {
    "MSG.HDR": "94622ce99f0e442df9823abcc522d72e3c0ef41d066934a4af090211c0a5525d",
    "MSG.DBS": "03be9abe1661b3159042824367469bf6085678d94b7306cd870c1ab73767c32f",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v21-dir", type=Path, required=True)
    parser.add_argument("--message-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    payloads: dict[str, bytes] = {}
    for name, expected_hash in V21_HASHES.items():
        source = (args.v21_dir / name).read_bytes()
        expect_hash(f"v21 {name}", source, expected_hash)
        if name in V22_MESSAGE_HASHES:
            source = (args.message_dir / name).read_bytes()
            expect_hash(f"v22 {name}", source, V22_MESSAGE_HASHES[name])
        payloads[f"DSAVANT/{name}"] = source

    patch_report = json.loads(
        (args.message_dir / "MESSAGE_PATCH_REPORT.json").read_text(encoding="utf-8")
    )
    if patch_report.get("record_start_crossings") != 0:
        raise ValueError("message patch report contains unsafe bank crossings")
    if patch_report.get("changed", {}).get("1052", {}).get("translation") != (
        "설명서에서 $ 단어를 입력하십시오"
    ):
        raise ValueError("message patch report does not contain the expected correction")

    report = {
        "format": "Wizardry VII DOS v22 Korean UI + copy-protection wording fix",
        "change": "message 1052 removes the duplicated ordinal suffix",
        "runtime_result": "설명서에서 세 번째 단어를 입력하십시오",
        "preserved": [
            "v21 UI alignment and stat repaint patches",
            "MISC.HDR Huffman tree",
            "Korean codebook and VBFONT0.VGA glyph mapping",
            "all packed message records except 1052",
        ],
        "validation": {
            "decoded_records": patch_report["record_count"],
            "record_start_crossings": patch_report["record_start_crossings"],
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    payloads["UI_V22_REPORT.json"] = json.dumps(
        report, ensure_ascii=False, indent=2
    ).encode("utf-8")

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
