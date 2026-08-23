from __future__ import annotations

import base64
import struct
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from extract_gold_messages import (  # noqa: E402
    detect_header_format,
    decode_huffman,
    extract_messages,
    MessageRecord,
    parse_header,
    RangeEntry,
)
from extract_gold_scenario_strings import extract  # noqa: E402
from build_dos_messages import (  # noqa: E402
    build_huffman_tree,
    build_unicode_codebook,
    decode_translation,
    encode_huffman,
    encode_translation,
    find_record_start_crossings,
    huffman_codes,
    pack_message_ranges,
    serialize_huffman_tree,
)


class GoldMessageExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hdr = (ROOT / "original" / "MSG.HDR").read_bytes()
        cls.gld = (ROOT / "original" / "MSG.GLD").read_bytes()

    def test_header_and_record_counts(self) -> None:
        declared, entries, sentinels = parse_header(self.hdr)
        records = extract_messages(self.gld, entries)
        self.assertEqual(1998, declared)
        self.assertEqual(3, sentinels)
        self.assertEqual(11018, len(records))
        self.assertEqual(len(records), len({record.message_id for record in records}))

    def test_known_first_records(self) -> None:
        _, entries, _ = parse_header(self.hdr)
        records = extract_messages(self.gld, entries)
        by_id = {record.message_id: record for record in records}
        self.assertEqual("HUMAN", by_id[100].source_text)
        self.assertEqual("FIGHTER", by_id[120].source_text)
        self.assertEqual(
            base64.b64decode(by_id[100].raw_base64), self.gld[1:6]
        )

    def test_dos_six_byte_header_layout(self) -> None:
        entries = [
            struct.pack("<HHBB", 100, 0, 1, 0),
            struct.pack("<HHBB", 200, 7, 0, 1),
        ]
        hdr = struct.pack("<H", len(entries)) + b"".join(entries) + bytes(12)
        self.assertEqual("dos", detect_header_format(hdr))
        declared, parsed, sentinels = parse_header(hdr)
        self.assertEqual(2, declared)
        self.assertEqual(2, sentinels)
        self.assertEqual((100, 0, 1, 0), (
            parsed[0].start_id,
            parsed[0].bank_offset,
            parsed[0].id_span,
            parsed[0].bank,
        ))

    def test_known_dos_huffman_record(self) -> None:
        # Tree: 0 -> A, 10 -> B, 11 -> C. Bitstream 01011 yields ABC.
        misc = struct.pack("<hhhh", ord("A"), -1, ord("B"), ord("C"))
        self.assertEqual(b"ABC", decode_huffman(bytes((3, 0x58)), misc))

    def test_dos_huffman_round_trip(self) -> None:
        misc = struct.pack("<hhhh", ord("A"), -1, ord("B"), ord("C"))
        codes = huffman_codes(misc)
        packed = encode_huffman(b"ABC", codes)
        self.assertEqual(b"ABC", decode_huffman(packed, misc))

    def test_custom_korean_codec_round_trip(self) -> None:
        # Leaves include escape 0x17 plus ASCII A/B/C.
        misc = struct.pack(
            "<hhhhhh",
            0x17,
            -1,
            ord("A"),
            -2,
            ord("B"),
            ord("C"),
        )
        codes = huffman_codes(misc)
        codebook = build_unicode_codebook(["근력 A"], codes)
        raw = encode_translation("근력A<0x17>", codes, codebook)
        self.assertEqual("근력A\x17", decode_translation(raw, codebook))
        self.assertEqual(raw, decode_huffman(encode_huffman(raw, codes), misc))

    def test_retrained_huffman_tree_round_trip(self) -> None:
        frequencies = {ord("A"): 20, ord("B"): 5, ord("C"): 1}
        misc = serialize_huffman_tree(
            build_huffman_tree(Counter(frequencies), sorted(frequencies))
        )
        codes = huffman_codes(misc)
        raw = b"AAAABAC"
        self.assertEqual(raw, decode_huffman(encode_huffman(raw, codes), misc))

    def test_range_packing_aligns_subindex_starts_to_bank(self) -> None:
        def record(range_index: int, message_id: int) -> MessageRecord:
            return MessageRecord(
                range_index=range_index,
                message_id=message_id,
                bank=0,
                bank_offset=0,
                absolute_offset=0,
                record_length=0,
                source_text="",
                source_display="",
                raw_base64="",
                raw_hex="",
            )

        first = [record(0, message_id) for message_id in range(100, 104)]
        second = [record(1, 200)]
        entries = [
            RangeEntry(0, 100, 0, 3, 0),
            RangeEntry(1, 200, 0, 0, 0),
        ]
        packed_by_id = {
            **{message_id: bytes(254) for message_id in range(100, 104)},
            200: b"XXXX",
        }
        data, output_entries, padding = pack_message_ranges(
            entries,
            {0: first, 1: second},
            packed_by_id,
        )
        self.assertEqual(4, padding)
        self.assertEqual((0, 0), (output_entries[0].bank, output_entries[0].bank_offset))
        self.assertEqual((1, 0), (output_entries[1].bank, output_entries[1].bank_offset))
        self.assertEqual([], find_record_start_crossings(data, output_entries))

    def test_range_packing_rejects_range_larger_than_one_bank(self) -> None:
        records = [
            MessageRecord(
                range_index=0,
                message_id=message_id,
                bank=0,
                bank_offset=0,
                absolute_offset=0,
                record_length=0,
                source_text="",
                source_display="",
                raw_base64="",
                raw_hex="",
            )
            for message_id in range(100, 105)
        ]
        with self.assertRaisesRegex(ValueError, "cannot fit"):
            pack_message_ranges(
                [RangeEntry(0, 100, 0, 4, 0)],
                {0: records},
                {message_id: bytes(255) for message_id in range(100, 105)},
            )


class GoldScenarioExtractionTests(unittest.TestCase):
    def test_fixed_width_tables(self) -> None:
        data = (ROOT / "original" / "SCENARIO.GLD").read_bytes()
        records = extract(data)
        items = [record for record in records if record.category == "item"]
        monsters = [record for record in records if record.category == "monster"]
        self.assertEqual(600, len(items))
        self.assertEqual(1000, len(monsters))
        self.assertEqual("BROKEN/ITEM", items[0].source_text)
        self.assertEqual("DANDIPHOOT", monsters[0].source_text)


if __name__ == "__main__":
    unittest.main()
