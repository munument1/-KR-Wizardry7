from __future__ import annotations

import base64
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from extract_gold_messages import (  # noqa: E402
    detect_header_format,
    decode_huffman,
    extract_messages,
    parse_header,
)
from extract_gold_scenario_strings import extract  # noqa: E402
from build_dos_messages import (  # noqa: E402
    build_unicode_codebook,
    decode_translation,
    encode_huffman,
    encode_translation,
    huffman_codes,
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
