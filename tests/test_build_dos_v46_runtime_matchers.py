from __future__ import annotations

import base64
import struct
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_dos_v46_runtime_matchers as v46  # noqa: E402
from build_dos_messages import (  # noqa: E402
    build_huffman_tree,
    encode_huffman,
    huffman_codes,
    serialize_huffman_tree,
)
from extract_gold_messages import HEADER_ENTRIES, RangeEntry, extract_messages, parse_header  # noqa: E402


class RuntimeMatcherV46Tests(unittest.TestCase):
    def test_matcher_detector_accepts_logic_tables_not_display_prose(self):
        self.assertTrue(v46.looks_like_runtime_matcher_source("HI/HELLO/HAIL/"))
        self.assertTrue(
            v46.looks_like_runtime_matcher_source(
                "<0x02>PALUKE/<0x02>ARMORY/"
            )
        )
        self.assertTrue(
            v46.looks_like_runtime_matcher_source("<0x08>088:53/<0x08>88:53/")
        )
        self.assertFalse(
            v46.looks_like_runtime_matcher_source(
                "Features: EYE-PATCH/RIGHT,CHROMA POWERGLOVE &"
            )
        )
        self.assertFalse(v46.looks_like_runtime_matcher_source("Paluke's Armory"))

    def test_manifest_contains_new_city_and_global_grammar(self):
        manifest = ROOT / "data/dos_runtime_matchers.json"
        matchers, metadata = v46.load_manifest(manifest)
        self.assertEqual(metadata["record_count"], 186)
        self.assertEqual(matchers[15180], "<0x02>PALUKE/<0x02>ARMORY/")
        self.assertEqual(matchers[7160], "HI/HELLO/HAIL/")
        self.assertEqual(matchers[7162], "YES/SURE/OK/YEA/YEAH/")
        self.assertEqual(matchers[15470], "<0x02>BLACK MARKET/")
        self.assertEqual(
            matchers[24880],
            "<0x03>SPAWNING/<0x03>PIT/<0x02>FORFEIT/<0x02>FORFIET/",
        )

    def test_restore_changes_only_manifest_record(self):
        source = b"\x02PALUKE/\x02ARMORY/"
        broken = b"\x02BAD/\x02NO/"
        untouched = b"VISIBLE TEXT"
        alphabet = sorted(set(source + broken + untouched))
        frequencies = Counter(source + broken + untouched)
        misc = serialize_huffman_tree(build_huffman_tree(frequencies, alphabet))
        codes = huffman_codes(misc)

        packed_a = encode_huffman(broken, codes)
        packed_b = encode_huffman(untouched, codes)
        data = bytearray()
        data.append(len(packed_a))
        data.extend(packed_a)
        data.append(len(packed_b))
        data.extend(packed_b)
        data.extend(bytes(v46.MAX_DOS_DATA_SIZE - len(data)))

        entry = RangeEntry(0, 15180, 0, 1, 0)
        header = struct.pack("<H", 1) + HEADER_ENTRIES["dos"].pack(
            entry.start_id, entry.bank_offset, entry.id_span, entry.bank
        )

        new_header, new_data, report = v46.restore_runtime_matchers(
            header,
            bytes(data),
            misc,
            {15180: "<0x02>PALUKE/<0x02>ARMORY/"},
        )
        self.assertEqual(report["changed_matcher_ids"], [15180])
        self.assertEqual(report["decoded_non_matcher_changes"], 0)

        _, entries, _ = parse_header(new_header, "dos")
        records = extract_messages(new_data, entries, misc)
        decoded = {
            record.message_id: base64.b64decode(record.raw_base64)
            for record in records
        }
        self.assertEqual(decoded[15180], source)
        self.assertEqual(decoded[15181], untouched)


if __name__ == "__main__":
    unittest.main()
