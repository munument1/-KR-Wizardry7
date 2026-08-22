from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from extract_gold_messages import extract_messages, parse_header  # noqa: E402
from extract_gold_scenario_strings import extract  # noqa: E402


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
