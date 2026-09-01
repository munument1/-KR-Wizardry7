#!/usr/bin/env python3
"""Build Wizardry VII DOS Korean v0.45 from the exact published v0.44 payload.

v0.45 adds Korean item and monster names from SCENARIO.DBS. Fixed-width
SCENARIO name slots are only 16 bytes, and runtime testing showed that the
normal 0x17+rank+rank Korean stream is not safe in every item-name path: some
characters are converted to '?'. The verified v0.45 renderer therefore uses a
SCENARIO-specific compact encoding:

* common Hangul syllables use one-byte direct codes;
* remaining Hangul syllables use F0..F8 + 80..FF safe two-byte pairs;
* translated item/monster slots contain no 0x17 escape bytes.

The SCENARIO/VBFONT assets supplied to this builder are the exact runtime-tested
v0.45 assets. All other v0.44 runtime payload bytes are preserved. The existing
codebook JSON is retained and annotated with SCENARIO metadata only; it is not
consumed by the game at runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

V44_ZIP_SHA256 = "9e1b27e2ebc617a0b4400d656b548fa4d7cd65d9f1df23852ad8b82df1702c1d"
V44_VBASE_SHA256 = "99fa1b3188cfb3585061ddbe34f136b57939b98250daacb4cec8146cd54db464"
V45_SCENARIO_SHA256 = "8ff513e0469dd12b8b175c7a99b43029eba5b04f70b7794627cc644e1fe34875"
V45_VBFONT_SHA256 = "f7d31cb5afe492840d75eec8eafc87975867601772cc2290d08ffc77185aaa2f"
TRANSLATION_CSV_SHA256 = "32322efbf5ccd647e2696a5f029c4098c1ea0427679b3527fdd9aa36832785ae"
ORIGINAL_SCENARIO_SHA256 = "b2cb0722122724d35d379bb10250d0eec51238d9b147c36be12177ef3d2462f6"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_hash(label: str, data: bytes, expected: str) -> None:
    actual = sha256(data)
    if actual != expected:
        raise ValueError(f"{label}: expected SHA-256 {expected}, found {actual}")


def write_deterministic_zip(path: Path, payloads: dict[str, bytes]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 2, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payloads[name])


def annotate_codebook(raw: bytes) -> bytes:
    metadata = json.loads(raw.decode("utf-8"))
    metadata["scenario_compact"] = {
        "format": (
            "SCENARIO fixed-width names: common Hangul uses 1-byte direct codes; "
            "all other Hangul uses F0..F8 + 80..FF safe pairs; "
            "no ESC+rank+rank in item/monster names"
        ),
        "translated_fields": 1568,
        "translated_item_fields": 568,
        "translated_monster_fields": 1000,
        "field_capacity_bytes": 16,
        "source_scenario_sha256": ORIGINAL_SCENARIO_SHA256,
        "patched_scenario_sha256": V45_SCENARIO_SHA256,
        "safe_pair_encoding": {
            "lead_range": "F0-F8",
            "trail_range": "80-FF",
            "glyph_index_formula": "(lead - F0) * 128 + (trail - 80)",
            "item_escape_0x17_fields": 0,
            "monster_escape_0x17_fields": 0,
        },
    }
    return json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v44-dir", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--vbfont", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip-output", type=Path, required=True)
    args = parser.parse_args()

    source_game = args.v44_dir / "DSAVANT"
    if not source_game.is_dir():
        raise FileNotFoundError(f"v0.44 DSAVANT directory not found: {source_game}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {args.output_dir}")

    scenario = args.scenario.read_bytes()
    vbfont = args.vbfont.read_bytes()
    require_hash("v0.45 SCENARIO.DBS", scenario, V45_SCENARIO_SHA256)
    require_hash("v0.45 VBFONT0.VGA", vbfont, V45_VBFONT_SHA256)

    payloads: dict[str, bytes] = {}
    for path in sorted(args.v44_dir.iterdir()):
        if path.is_file() and path.name.startswith("UI_V44_"):
            payloads[path.name] = path.read_bytes()
    for path in sorted(source_game.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if path.name == "VBFONT0.VGA":
            data = vbfont
        elif path.name == "korean_codebook.json":
            data = annotate_codebook(data)
        payloads[f"DSAVANT/{path.name}"] = data

    vbase = payloads.get("DSAVANT/VBASE.OVR")
    if vbase is None:
        raise ValueError("v0.44 payload is missing VBASE.OVR")
    require_hash("inherited v0.44 VBASE.OVR", vbase, V44_VBASE_SHA256)

    payloads["DSAVANT/SCENARIO.DBS"] = scenario

    report = {
        "format": "Wizardry VII DOS Korean v0.45 SCENARIO safe encoding",
        "base_release": "v0.44",
        "runtime_confirmation": {
            "jan_ette_encounter": "normal after v0.44 event-state fix",
            "item_names": "tester confirmed normal after safe-pair conversion",
            "monster_names": "tester confirmed normal with the same safe encoding",
        },
        "scenario": {
            "file": "SCENARIO.DBS",
            "size": len(scenario),
            "sha256": sha256(scenario),
            "translated_item_fields": 568,
            "translated_monster_fields": 1000,
            "field_capacity_bytes": 16,
            "escape_0x17_item_fields": 0,
            "escape_0x17_monster_fields": 0,
        },
        "encoding": {
            "common_hangul": "one-byte direct codes",
            "other_hangul": "F0..F8 + 80..FF safe pair",
            "legacy_escape_in_scenario_names": "not used",
        },
        "renderer": {"file": "VBFONT0.VGA", "sha256": sha256(vbfont)},
        "translation_csv": {"sha256": TRANSLATION_CSV_SHA256},
        "payloads": {
            name: {"size": len(data), "sha256": sha256(data)}
            for name, data in sorted(payloads.items())
        },
    }
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    payloads["UI_V45_REPORT.json"] = report_raw

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    write_deterministic_zip(args.zip_output, payloads)
    report["zip_output"] = str(args.zip_output.resolve())
    report["zip_sha256"] = sha256(args.zip_output.read_bytes())
    (args.output_dir / "UI_V45_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
