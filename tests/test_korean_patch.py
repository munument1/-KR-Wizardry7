from __future__ import annotations

import csv
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_korean_patch import (  # noqa: E402
    HEADER_ENTRY,
    ITEM_TABLE_OFFSET,
    MONSTER_NAME_OFFSET,
    encode_game_text,
    expand_vbfont0,
    extract_messages,
    parse_header,
    patch_scenario,
    rebuild_messages,
)


def crc32(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


class KoreanEncodingTests(unittest.TestCase):
    def test_known_hangul_code(self) -> None:
        self.assertEqual(bytes([0x97, 0xA2]), encode_game_text("한"))

    def test_ascii_and_control_marker(self) -> None:
        self.assertEqual(b"A\x0f" + bytes([0x97, 0xA2]), encode_game_text("A<0x0F>한"))


class MessageRebuildTests(unittest.TestCase):
    def test_rebuild_and_reparse(self) -> None:
        # Two one-record ranges with three zero sentinel entries.
        hdr = bytearray(struct.pack("<H", 2))
        hdr.extend(HEADER_ENTRY.pack(100, 0, 0, 0))
        hdr.extend(HEADER_ENTRY.pack(200, 4, 0, 0))
        hdr.extend(b"\x00" * (3 * HEADER_ENTRY.size))
        gld = bytes([2]) + b"HI" + bytes([0, 1]) + b"X" + b"\x00" * 1018
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "messages.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=["range_index", "message_id", "source_crc32", "translation"]
                )
                writer.writeheader()
                writer.writerow({"range_index": 0, "message_id": 100, "source_crc32": crc32(b"HI"), "translation": "한"})
                writer.writerow({"range_index": 1, "message_id": 200, "source_crc32": crc32(b"X"), "translation": "가"})
            new_hdr, new_gld, report = rebuild_messages(bytes(hdr), gld, csv_path)
        entries, sentinels = parse_header(new_hdr)
        records = extract_messages(new_gld, entries)
        self.assertEqual(3, sentinels)
        self.assertEqual(bytes([0x97, 0xA2]), records[0].raw)
        self.assertEqual(2, report["message_count"])


class ScenarioPatchTests(unittest.TestCase):
    def test_patch_two_slots(self) -> None:
        data = bytearray(MONSTER_NAME_OFFSET + 64)
        data[ITEM_TABLE_OFFSET : ITEM_TABLE_OFFSET + 16] = b"BROKEN/ITEM\x00\x00\x00\x00\x00"
        data[MONSTER_NAME_OFFSET : MONSTER_NAME_OFFSET + 16] = b"DANDIPHOOT\x00\x00\x00\x00\x00\x00"
        rows = []
        # Build all required 1600 payload rows, empty except the two anchors.
        for i in range(600):
            source = b"BROKEN/ITEM" if i == 0 else b""
            rows.append({"category": "item", "record_index": i, "variant": "name", "source_crc32": crc32(source), "translation": "부서진/물건" if i == 0 else ""})
        variants = ("singular", "plural", "generic_singular", "generic_plural")
        for i in range(250):
            for v in variants:
                source = b"DANDIPHOOT" if i == 0 and v == "singular" else b""
                rows.append({"category": "monster", "record_index": i, "variant": v, "source_crc32": crc32(source), "translation": "댄디풋" if source else ""})
        # A complete synthetic SCENARIO must be large enough for all fixed offsets.
        full_size = MONSTER_NAME_OFFSET + 250 * 0xE8
        full = bytearray(full_size)
        full[: len(data)] = data
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "scenario.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["category", "record_index", "variant", "source_crc32", "translation"])
                writer.writeheader(); writer.writerows(rows)
            patched, report = patch_scenario(bytes(full), csv_path)
        self.assertNotEqual(bytes(full[ITEM_TABLE_OFFSET:ITEM_TABLE_OFFSET+16]), patched[ITEM_TABLE_OFFSET:ITEM_TABLE_OFFSET+16])
        self.assertEqual(1600, report["slot_count"])


class VbfontTests(unittest.TestCase):
    def test_expand_vbfont0(self) -> None:
        original = bytearray(1040)
        original[0] = 6; original[1] = 6; original[3] = 1; original[5] = 128
        struct.pack_into("<H", original, 10, 6)
        struct.pack_into("<H", original, 12, 1040)
        struct.pack_into("<H", original, 14, 6)
        expanded = expand_vbfont0(bytes(original))
        self.assertEqual(1296, len(expanded))
        self.assertEqual((8, 8, 128), (expanded[0], expanded[1], expanded[5]))


if __name__ == "__main__":
    unittest.main()
