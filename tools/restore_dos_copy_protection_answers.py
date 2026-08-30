"""Restore ASCII copy-protection answers in the DOS translation CSV."""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path


FIRST_ANSWER_ID = 2500
LAST_ANSWER_ID = 2574


def rewrite_line(line: str) -> tuple[str, bool]:
    newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    content = line[: -len(newline)] if newline else line
    row = next(csv.reader([content]))
    if len(row) != 3:
        return line, False
    try:
        message_id = int(row[0])
    except ValueError:
        return line, False
    if not FIRST_ANSWER_ID <= message_id <= LAST_ANSWER_ID:
        return line, False
    if row[2] == row[1]:
        return line, False

    row[2] = row[1]
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator=newline or "\n").writerow(row)
    return output.getvalue(), True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    original = args.path.read_text(encoding="utf-8", newline="")
    rewritten: list[str] = []
    changed = 0
    seen: set[int] = set()
    for line in original.splitlines(keepends=True):
        row = next(csv.reader([line.rstrip("\r\n")]))
        if row and row[0].isdigit():
            message_id = int(row[0])
            if FIRST_ANSWER_ID <= message_id <= LAST_ANSWER_ID:
                seen.add(message_id)
        result, did_change = rewrite_line(line)
        rewritten.append(result)
        changed += int(did_change)

    expected = set(range(FIRST_ANSWER_ID, LAST_ANSWER_ID + 1))
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ValueError(f"copy-protection answer range mismatch: missing={missing}, extra={extra}")

    args.path.write_text("".join(rewritten), encoding="utf-8", newline="")
    print(f"restored {changed} copy-protection answers in {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
