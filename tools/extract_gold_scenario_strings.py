#!/usr/bin/env python3
"""Extract fixed-width item and monster names from Wizardry 7 Gold SCENARIO.GLD."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


ITEM_TABLE_OFFSET = 0x0380
ITEM_RECORD_SIZE = 0x48
ITEM_COUNT = 600
ITEM_NAME_SIZE = 16

MONSTER_NAME_OFFSET = 0x37040
MONSTER_RECORD_SIZE = 0xE8
MONSTER_COUNT = 250
MONSTER_NAME_SIZE = 16
MONSTER_VARIANTS = ("singular", "plural", "generic_singular", "generic_plural")


@dataclass(frozen=True)
class ScenarioString:
    category: str
    record_index: int
    variant: str
    absolute_offset: int
    capacity: int
    source_text: str
    raw_slot_base64: str
    raw_slot_hex: str


def decode_slot(slot: bytes, *, label: str) -> str:
    payload = slot.split(b"\x00", 1)[0]
    if any(value < 0x20 or value > 0x7E for value in payload):
        raise ValueError(f"{label} contains a non-printable byte: {payload.hex(' ')}")
    return payload.decode("ascii")


def make_record(
    *, category: str, record_index: int, variant: str, offset: int, capacity: int, data: bytes
) -> ScenarioString:
    slot = data[offset : offset + capacity]
    if len(slot) != capacity:
        raise ValueError(f"{category} {record_index} {variant}: slot exceeds SCENARIO.GLD")
    text = decode_slot(slot, label=f"{category} {record_index} {variant}")
    return ScenarioString(
        category=category,
        record_index=record_index,
        variant=variant,
        absolute_offset=offset,
        capacity=capacity,
        source_text=text,
        raw_slot_base64=base64.b64encode(slot).decode("ascii"),
        raw_slot_hex=slot.hex(" ").upper(),
    )


def extract(data: bytes) -> list[ScenarioString]:
    if data[ITEM_TABLE_OFFSET : ITEM_TABLE_OFFSET + 11] != b"BROKEN/ITEM":
        raise ValueError("item table anchor BROKEN/ITEM was not found at 0x380")
    if data[MONSTER_NAME_OFFSET : MONSTER_NAME_OFFSET + 11] != b"DANDIPHOOT\x00":
        raise ValueError("monster table anchor DANDIPHOOT was not found at 0x37040")

    records: list[ScenarioString] = []
    for index in range(ITEM_COUNT):
        offset = ITEM_TABLE_OFFSET + index * ITEM_RECORD_SIZE
        records.append(
            make_record(
                category="item",
                record_index=index,
                variant="name",
                offset=offset,
                capacity=ITEM_NAME_SIZE,
                data=data,
            )
        )

    for index in range(MONSTER_COUNT):
        record_offset = MONSTER_NAME_OFFSET + index * MONSTER_RECORD_SIZE
        for variant_index, variant in enumerate(MONSTER_VARIANTS):
            records.append(
                make_record(
                    category="monster",
                    record_index=index,
                    variant=variant,
                    offset=record_offset + variant_index * MONSTER_NAME_SIZE,
                    capacity=MONSTER_NAME_SIZE,
                    data=data,
                )
            )
    return records


def write_csv(path: Path, records: list[ScenarioString]) -> None:
    fields = [
        "category",
        "record_index",
        "variant",
        "absolute_offset",
        "capacity",
        "source_text",
        "translation",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel")
        writer.writeheader()
        for record in records:
            row = asdict(record)
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    data = args.scenario.read_bytes()
    records = extract(data)
    metadata = {
        "format": "Wizardry 7 Gold SCENARIO.GLD fixed-width strings",
        "source_file": args.scenario.name,
        "source_size": len(data),
        "source_sha256": hashlib.sha256(data).hexdigest().upper(),
        "item_record_count": ITEM_COUNT,
        "nonempty_item_name_count": sum(
            bool(record.source_text) for record in records if record.category == "item"
        ),
        "monster_record_count": MONSTER_COUNT,
        "monster_name_slot_count": MONSTER_COUNT * len(MONSTER_VARIANTS),
        "nonempty_monster_name_slot_count": sum(
            bool(record.source_text) for record in records if record.category == "monster"
        ),
        "fixed_width_warning": "Each slot is exactly 16 bytes including any NUL padding.",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "scenario_strings.json").write_text(
        json.dumps(
            {"metadata": metadata, "records": [asdict(record) for record in records]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )
    write_csv(args.output_dir / "scenario_strings_for_translation.csv", records)
    (args.output_dir / "extraction_report.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
