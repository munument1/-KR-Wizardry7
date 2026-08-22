#!/usr/bin/env python3
"""Import the finished Wizardry 7 Gold translation workbook into release CSVs.

Only translation text plus stable record identifiers and source CRC32 values are
written. English source text from the purchased game is not copied into the repo.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTROL_RE = re.compile(r"<0x([0-9A-Fa-f]{2})>")
PRESERVE_SYMBOLS = "$^%@#*/"
NORMALIZE_UNSUPPORTED = {"×": "x", "퉷": "퉤"}


def column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        raise ValueError(f"invalid cell reference: {cell_ref}")
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - 64
    return value - 1


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    result: list[str] = []
    for item in root.findall(f"{{{MAIN_NS}}}si"):
        result.append("".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")))
    return result


def sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    result: dict[str, str] = {}
    sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
    if sheets is None:
        return result
    for sheet in sheets:
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
        result[name] = "xl/" + targets[rel_id].lstrip("/")
    return result


def read_sheet(archive: zipfile.ZipFile, path: str, strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(archive.read(path))
    sheet_data = root.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is None:
        return []
    sparse_rows: list[dict[int, str]] = []
    max_col = -1
    for row in sheet_data.findall(f"{{{MAIN_NS}}}row"):
        values: dict[int, str] = {}
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            index = column_index(cell.attrib["r"])
            max_col = max(max_col, index)
            cell_type = cell.attrib.get("t")
            value_node = cell.find(f"{{{MAIN_NS}}}v")
            if cell_type == "s" and value_node is not None:
                value = strings[int(value_node.text or "0")]
            elif cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
            elif value_node is not None:
                value = value_node.text or ""
            else:
                value = ""
            values[index] = value
        sparse_rows.append(values)
    width = max_col + 1
    return [[values.get(index, "") for index in range(width)] for values in sparse_rows]


def rows_as_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    headers = rows[0]
    return [
        {header: (row[index] if index < len(row) else "") for index, header in enumerate(headers) if header}
        for row in rows[1:]
    ]


def decode_source_display(text: str) -> bytes:
    output = bytearray()
    index = 0
    while index < len(text):
        match = CONTROL_RE.match(text, index)
        if match:
            output.append(int(match.group(1), 16))
            index = match.end()
            continue
        char = text[index]
        if ord(char) > 0x7F:
            raise ValueError(f"source display contains non-ASCII literal {char!r}")
        output.append(ord(char))
        index += 1
    return bytes(output)


def encode_game_text(text: str) -> bytes:
    output = bytearray()
    index = 0
    while index < len(text):
        match = CONTROL_RE.match(text, index)
        if match:
            output.append(int(match.group(1), 16))
            index = match.end()
            continue
        char = text[index]
        if ord(char) < 0x80:
            output.append(ord(char))
            index += 1
            continue
        try:
            encoded = char.encode("euc_kr")
        except UnicodeEncodeError as exc:
            raise ValueError(f"unsupported character {char!r} U+{ord(char):04X}") from exc
        if len(encoded) != 2 or not (0xB0 <= encoded[0] <= 0xC8 and 0xA1 <= encoded[1] <= 0xFE):
            raise ValueError(f"character is outside KS X 1001 Hangul: {char!r} U+{ord(char):04X}")
        glyph_index = (encoded[0] - 0xB0) * 94 + (encoded[1] - 0xA1)
        output.extend((0x80 + glyph_index // 96, 0xA0 + glyph_index % 96))
        index += 1
    return bytes(output)


def normalized(text: str) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []
    for source, replacement in NORMALIZE_UNSUPPORTED.items():
        if source in text:
            count = text.count(source)
            text = text.replace(source, replacement)
            changes.extend([(source, replacement)] * count)
    return text, changes


def validate_preserved(source: str, translation: str, label: str) -> None:
    source_tokens = [token.upper() for token in CONTROL_RE.findall(source)]
    translated_tokens = [token.upper() for token in CONTROL_RE.findall(translation)]
    if source_tokens != translated_tokens:
        raise ValueError(f"{label}: control-code sequence changed")
    for symbol in PRESERVE_SYMBOLS:
        if source.count(symbol) != translation.count(symbol):
            raise ValueError(f"{label}: preserved symbol {symbol!r} count changed")


def source_crc32(source: str) -> str:
    return f"{zlib.crc32(decode_source_display(source)) & 0xFFFFFFFF:08X}"


def write_messages(rows: list[dict[str, str]], output: Path) -> dict:
    fieldnames = ["range_index", "message_id", "source_crc32", "translation"]
    emitted: list[dict[str, str]] = []
    normalization_changes: list[dict[str, str]] = []
    translated_nonempty = 0
    max_encoded = 0
    for row in rows:
        source = row.get("source_text", "")
        translation = row.get("translation", "")
        if source and not translation:
            raise ValueError(f"message {row.get('message_id')}: non-empty source is untranslated")
        if translation:
            translation, changes = normalized(translation)
            for before, after in changes:
                normalization_changes.append({"message_id": row["message_id"], "from": before, "to": after})
            validate_preserved(source, translation, f"message {row['message_id']}")
            encoded = encode_game_text(translation)
            if len(encoded) > 255:
                raise ValueError(f"message {row['message_id']}: {len(encoded)} encoded bytes > 255")
            max_encoded = max(max_encoded, len(encoded))
            if source:
                translated_nonempty += 1
        emitted.append(
            {
                "range_index": row["range_index"],
                "message_id": row["message_id"],
                "source_crc32": source_crc32(source),
                "translation": translation,
            }
        )
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(emitted)
    return {
        "rows": len(emitted),
        "translated_nonempty": translated_nonempty,
        "max_encoded_bytes": max_encoded,
        "normalization_changes": normalization_changes,
    }


def write_scenario(rows: list[dict[str, str]], output: Path) -> dict:
    fieldnames = ["category", "record_index", "variant", "source_crc32", "translation"]
    emitted: list[dict[str, str]] = []
    translated_nonempty = 0
    max_encoded = 0
    for row in rows:
        source = row.get("source_text", "")
        translation = row.get("translation", "")
        if source and not translation:
            raise ValueError(
                f"scenario {row.get('category')} {row.get('record_index')} {row.get('variant')}: untranslated"
            )
        if translation:
            translation, changes = normalized(translation)
            if changes:
                raise ValueError("unexpected Scenario normalization; review workbook")
            validate_preserved(source, translation, f"scenario {row['record_index']} {row['variant']}")
            encoded = encode_game_text(translation)
            capacity = int(row["capacity"])
            if len(encoded) > capacity:
                raise ValueError(
                    f"scenario {row['record_index']} {row['variant']}: {len(encoded)} encoded bytes > {capacity}"
                )
            max_encoded = max(max_encoded, len(encoded))
            if source:
                translated_nonempty += 1
        emitted.append(
            {
                "category": row["category"],
                "record_index": row["record_index"],
                "variant": row["variant"],
                "source_crc32": source_crc32(source),
                "translation": translation,
            }
        )
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(emitted)
    return {
        "rows": len(emitted),
        "translated_nonempty": translated_nonempty,
        "max_encoded_bytes": max_encoded,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("translations"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    workbook_bytes = args.workbook.read_bytes()
    with zipfile.ZipFile(args.workbook) as archive:
        strings = shared_strings(archive)
        paths = sheet_paths(archive)
        messages = rows_as_dicts(read_sheet(archive, paths["Messages"], strings))
        scenario = rows_as_dicts(read_sheet(archive, paths["Scenario"], strings))

    message_report = write_messages(messages, args.output_dir / "messages_ko.csv")
    scenario_report = write_scenario(scenario, args.output_dir / "scenario_ko.csv")
    manifest = {
        "format": "Wizardry 7 Gold Korean translation payload v1",
        "source_workbook_sha256": hashlib.sha256(workbook_bytes).hexdigest().upper(),
        "messages": message_report,
        "scenario": scenario_report,
        "encoding": {
            "hangul": "KS X 1001 2350 glyphs mapped to custom lead 0x80-0x98 / trail 0xA0-0xFF",
            "control_tokens": "<0xNN> is emitted as the literal byte NN",
        },
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    payload_path = args.output_dir / "wizardry7_ko_payload.zip"
    with zipfile.ZipFile(payload_path, "w", zipfile.ZIP_LZMA) as archive:
        archive.write(args.output_dir / "messages_ko.csv", "messages_ko.csv")
        archive.write(args.output_dir / "scenario_ko.csv", "scenario_ko.csv")
        archive.write(manifest_path, "manifest.json")
    manifest["payload_zip_sha256"] = hashlib.sha256(payload_path.read_bytes()).hexdigest().upper()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
