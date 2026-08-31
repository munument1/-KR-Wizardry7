#!/usr/bin/env python3
"""Package the Korean save/load menu fixed-slot safety pass."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_dos_korean_boundaries import audit
from build_dos_v19_baseline import expect_hash, sha256, write_deterministic_zip


V29_HASHES = {
    "DS.EXE": "6b3e0ebd09e987e31c2a49b8400b669c1af1e0e5b8564bfff6013af37bf1dd2c",
    "korean_codebook.json": "0b9a640ed0859d9afbf4df541d666a7e4ea6be8f9a7e7d5bdb469c8b239b28a9",
    "MISC.HDR": "0c09f9cd7cc1fdf7d6d698eecba5e6f1bbf4e54da0f9d80acaa0c4f19c7bfcd4",
    "MSG.DBS": "87929ec524547ccca54fe2627a249c1773a077b196b13bb093d6209cb50ec6d5",
    "MSG.HDR": "bf5234b700bb004b05d794006c0a1a55a01705ed76e09735e73381242dc4a897",
    "MON63.PIC": "1f8b916f67ee9bd6fe60697c2f24cc8bb35b0e32622214cb3d9ddf1c2a410781",
    "VBASE.OVR": "001b52292d08a1fa222cdde90f0a28209245282eb7ba14042484d7ef3edbc020",
    "VBFONT0.VGA": "e425f17118abbc2d7599c61f89324ea9162939a97383f35d17c11e90d7cd4750",
    "VDOPT.OVR": "b2574cecefcc55f2b42cac509c4428f696da27cfdb558b44082a0b19e516be92",
    "VINIT.OVR": "63a88cc454817c243d3c6023107a86e2c6926dc9a38cd63e773843e1da96b2a6",
    "VMAZE.OVR": "60467283445b52e11b42c6aaccf06e4a42aca3653269b21f673924da2b4328d4",
    "VMELE.OVR": "e56c555e3343fc869aa49fd8419e40a2271ee370de023f7ae8d453afa7a7e8a4",
    "VMEXE.OVR": "8058f9c1ed4d6409c9922969b57aa972864fa396c2d4bb7d353d8a5ec580d3da",
    "VMEXT.OVR": "e9f9f77d1312b370e146e2d4f86edd7dea7cbbf36a10af04168fdfb7f7222029",
    "VMNPC.OVR": "dfedb6b59cb12bc3d79e54f0e163969bd7dfe39b76a12a7d0a9abb02677d7fb1",
    "VPCLV.OVR": "2f83def79e4027ea65eea40b44fac7782a99140f6bbf02c7aa385f93827ab9fd",
    "VPCMK.OVR": "36b50daea346973750a0cc9c9b18c7b222f216cc73662e01e7c1dd1ee52a625f",
    "VPCVW.OVR": "c4117487f7429dd1742bf037d42ecd6e39691eb0482c70fae2ae0a09f3b45d4b",
    "VPOPS.OVR": "cb554c9af7d5e105e96fe89adb654dd80f2daabffe5228bbe7aa2adce02819ee",
    "VTREA.OVR": "e097883c7061cd9273ffda4cb244076277321cef67d7ba0f50b95b6dc12232a5",
}

MESSAGE_HASHES = {
    "MSG.HDR": "eac8d1a6807c421454956723f629baf7e3d3a9c1865dcf685277e759abd15134",
    "MSG.DBS": "11bbf4508009258a80cfc48419ae7800fe5a9ff4217cdeac082c7bd0ffa11c8e",
    "MISC.HDR": V29_HASHES["MISC.HDR"],
    "korean_codebook.json": V29_HASHES["korean_codebook.json"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v29-dir", type=Path, required=True)
    parser.add_argument("--message-dir", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")
    source_dir = args.v29_dir / "DSAVANT"
    payloads: dict[str, bytes] = {}
    for name, expected_hash in V29_HASHES.items():
        source = (source_dir / name).read_bytes()
        expect_hash(f"v29 {name}", source, expected_hash)
        if name in MESSAGE_HASHES:
            source = (args.message_dir / name).read_bytes()
            expect_hash(f"v30 {name}", source, MESSAGE_HASHES[name])
        payloads[f"DSAVANT/{name}"] = source

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    boundary = audit(
        args.output_dir / "DSAVANT", args.translations, args.original_zip
    )
    if not boundary["passed"]:
        raise ValueError(f"v30 boundary audit failed: {boundary}")
    report = {
        "format": "Wizardry VII DOS v30 Korean save/load compatibility",
        "changes": [
            "shortens the title-menu load label to fit its 20-byte record slot",
            "shortens the no-save exit label to fit the pause-menu record slot",
            "shortens the character-save confirmation to avoid modal scratch overflow",
            "keeps the v28 event parser fixes and v29 animated Korean logo unchanged",
        ],
        "translations": {
            "1005": "게임 불러오기",
            "1127": "캐릭터 저장?",
            "1400": "게임 불러오기",
            "2205": "저장 없이 끝",
        },
        "audit": {
            "passed": boundary["passed"],
            "issue_count": boundary["issue_count"],
            "record_count": boundary["record_count"],
            "fixed_slots": boundary["fixed_slots"],
        },
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V30_REPORT.json"] = report_raw
    (args.output_dir / "UI_V30_REPORT.json").write_bytes(report_raw)
    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
