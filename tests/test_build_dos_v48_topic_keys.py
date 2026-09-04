from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_dos_v48_topic_keys as v48  # noqa: E402


class TopicKeyV48Tests(unittest.TestCase):
    def test_topic_manifest_shape_and_paluke_fixtures(self):
        keys, metadata = v48.load_topic_manifest(ROOT / "data/dos_topic_key_records.json")
        self.assertEqual(metadata["record_count"], 620)
        self.assertEqual(len(keys), 620)
        self.assertEqual(keys[8310], '"LORE@')
        self.assertEqual(keys[9040], "<0x1F>BLACK MARKET%")
        self.assertEqual(keys[9210], '"ARMOR%')
        self.assertEqual(keys[9220], " PRISONER%")

        global_start, global_end, global_step = metadata["global_range"]
        self.assertEqual((global_start, global_end, global_step), (8000, 8330, 5))
        self.assertEqual(len(range(global_start, global_end + 1, global_step)), 67)

    def test_all_logic_layers_are_disjoint_and_complete(self):
        combined, metadata, previous_ids, topic_ids = v48.load_all_logic_records(
            ROOT / "data/dos_runtime_matchers.json",
            ROOT / "data/dos_parser_core_records.json",
            ROOT / "data/dos_topic_key_records.json",
        )
        self.assertEqual(len(previous_ids), 250)
        self.assertEqual(len(topic_ids), 620)
        self.assertFalse(previous_ids & topic_ids)
        self.assertEqual(len(combined), 870)
        self.assertEqual(metadata["combined_record_count"], 870)

        self.assertEqual(
            combined[7177],
            "WHAT TELL YOU/RUMOR/RUMORS/NEWS/INFO/HINT/HINTS/",
        )
        self.assertEqual(combined[9220], " PRISONER%")
        self.assertEqual(combined[15180], "<0x02>PALUKE/<0x02>ARMORY/")

    def test_topic_key_blocks_use_stride_five(self):
        keys, metadata = v48.load_topic_manifest(ROOT / "data/dos_topic_key_records.json")
        expected = set(range(8000, 8330 + 1, 5))
        for start, end, step in metadata["npc_blocks"]:
            self.assertEqual(step, 5)
            expected.update(range(start, end + 1, step))
        self.assertEqual(set(keys), expected)
        self.assertEqual(len(expected), 620)


if __name__ == "__main__":
    unittest.main()
