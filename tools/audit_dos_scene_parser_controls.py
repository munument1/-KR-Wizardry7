#!/usr/bin/env python3
"""Audit every raw ASCII token used by the DOS cinematic text parser."""

from __future__ import annotations

import argparse
import base64
import json
from collections import Counter, defaultdict
from pathlib import Path

from audit_dos_korean_boundaries import load_records
from build_dos_messages import DEFAULT_ESCAPE
from build_dos_v20_ui_complete import MZ_HEADER_SIZE, OVERLAY_ORIGIN, call_target
from build_dos_v25_scene_text import SCENE_FIND_CALLS, SCENE_FIND_HELPER, scene_find_helper_bytes
from build_dos_v26_scene_text import (
    TRAILING_ASCII_HELPER,
    TRAILING_MARKER_PATCH_OFFSET,
    trailing_ascii_helper_bytes,
)


CONTROL_TABLE_OFFSET = 0x9469
CONTROL_DISPATCH = b"!%&]@#|"
DELIMITER_TOKENS = b" _"
TRAILING_TOKENS = b"$^"
ALL_PARSER_TOKENS = tuple(dict.fromkeys(DELIMITER_TOKENS + TRAILING_TOKENS + CONTROL_DISPATCH))
EXPECTED_TRAILING_PATCH = bytes.fromhex("FF 76 04 E8 70 3A 59 EB 23 90 90")


def glyph_payload_collision_counts(game_dir: Path) -> tuple[Counter[int], dict[int, set[int]]]:
    _, records = load_records(game_dir)
    counts: Counter[int] = Counter()
    message_ids: dict[int, set[int]] = defaultdict(set)
    for record in records:
        raw = base64.b64decode(record.raw_base64)
        index = 0
        while index < len(raw):
            if raw[index] == DEFAULT_ESCAPE and index + 1 < len(raw):
                if raw[index + 1] == DEFAULT_ESCAPE:
                    index += 2
                    continue
                if index + 2 >= len(raw):
                    break
                for value in raw[index + 1 : index + 3]:
                    if value in ALL_PARSER_TOKENS:
                        counts[value] += 1
                        message_ids[value].add(record.message_id)
                index += 3
                continue
            index += 1
    return counts, message_ids


def audit(game_dir: Path) -> dict[str, object]:
    ds = (game_dir / "DS.EXE").read_bytes()
    vbase = (game_dir / "VBASE.OVR").read_bytes()
    dispatch_table = vbase[CONTROL_TABLE_OFFSET : CONTROL_TABLE_OFFSET + len(CONTROL_DISPATCH) + 1]

    find_helper = scene_find_helper_bytes()
    find_start = MZ_HEADER_SIZE + SCENE_FIND_HELPER
    trailing_helper = trailing_ascii_helper_bytes()
    trailing_start = MZ_HEADER_SIZE + TRAILING_ASCII_HELPER
    find_targets = [call_target(vbase, offset, OVERLAY_ORIGIN) for offset in SCENE_FIND_CALLS]
    trailing_patch = vbase[
        TRAILING_MARKER_PATCH_OFFSET : TRAILING_MARKER_PATCH_OFFSET + len(EXPECTED_TRAILING_PATCH)
    ]

    counts, message_ids = glyph_payload_collision_counts(game_dir)
    token_report = {
        chr(value): {
            "glyph_payload_occurrences": counts[value],
            "affected_message_records": len(message_ids[value]),
            "protected_by": (
                "Korean-aware delimiter search"
                if value in DELIMITER_TOKENS
                else "Korean-aware trailing-unit check"
                if value in TRAILING_TOKENS
                else "logical word-start dispatch after Korean-aware splitting"
            ),
        }
        for value in ALL_PARSER_TOKENS
    }

    checks = {
        "control_dispatch_table_exact": dispatch_table == CONTROL_DISPATCH + b"\x00",
        "find_helper_exact": ds[find_start : find_start + len(find_helper)] == find_helper,
        "find_calls_retargeted": find_targets == [SCENE_FIND_HELPER] * len(SCENE_FIND_CALLS),
        "trailing_helper_exact": ds[
            trailing_start : trailing_start + len(trailing_helper)
        ] == trailing_helper,
        "trailing_marker_site_exact": trailing_patch == EXPECTED_TRAILING_PATCH,
        "alphabetic_control_tokens_absent": not any(chr(value).isalpha() for value in ALL_PARSER_TOKENS),
        "all_parser_tokens_exercised": all(counts[value] > 0 for value in ALL_PARSER_TOKENS),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "format": "Wizardry VII DOS cinematic parser full control-token audit",
        "control_dispatch_table": CONTROL_DISPATCH.decode("ascii"),
        "delimiter_tokens": DELIMITER_TOKENS.decode("ascii"),
        "trailing_alignment_tokens": TRAILING_TOKENS.decode("ascii"),
        "alphabetic_control_tokens": [],
        "tokens": token_report,
        "checks": checks,
        "failures": failures,
        "passed": not failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.game_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
