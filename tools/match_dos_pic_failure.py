#!/usr/bin/env python3
"""Match a VGA PICFAIL diagnostic line to local Wizardry VII .PIC files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LINE_RE = re.compile(
    r"PICFAIL\s+S=(?P<slot>[0-9A-Fa-f]{4})\s+SZ=(?P<size>[0-9A-Fa-f]{8})\s+P=(?P<pool>[0-9A-Fa-f]{4})"
)


def parse_line(line: str) -> tuple[int, int, int]:
    match = LINE_RE.search(line)
    if not match:
        raise ValueError("expected: PICFAIL S=ssss SZ=zzzzzzzz P=pppp")
    return tuple(int(match.group(name), 16) for name in ("slot", "size", "pool"))


def find_matches(game_dir: Path, payload_size: int) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for path in sorted(game_dir.glob("*.PIC")):
        data = path.read_bytes()
        if len(data) < 4:
            continue
        declared = int.from_bytes(data[:4], "little")
        if declared == payload_size:
            matches.append(
                {
                    "name": path.name,
                    "file_size": len(data),
                    "declared_payload_size": declared,
                    "declared_payload_hex": f"{declared:08X}",
                    "file_size_matches_header_plus_4": len(data) == declared + 4,
                    "paragraphs": (declared + 15) >> 4,
                }
            )
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--line", required=True, help="PICFAIL line copied from DOSBox")
    args = parser.parse_args()

    slot, size, pool = parse_line(args.line)
    matches = find_matches(args.game_dir, size)
    report = {
        "slot": slot,
        "slot_hex": f"{slot:04X}",
        "payload_size": size,
        "payload_size_hex": f"{size:08X}",
        "post_allocation_pool": pool,
        "post_allocation_pool_hex": f"{pool:04X}",
        "pool_limit_hex": "4180",
        "overflow_paragraphs": max(0, pool - 0x4180),
        "matches": matches,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
