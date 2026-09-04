from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_dos_v46_runtime_matchers as v46  # noqa: E402
import build_dos_v47_parser_core as v47  # noqa: E402


class ParserCoreV47Tests(unittest.TestCase):
    def test_core_manifest_matches_vmnpc_fixed_load_ranges(self):
        records, metadata = v47.load_core_manifest(ROOT / "data/dos_parser_core_records.json")
        self.assertEqual(metadata["record_count"], 64)
        self.assertEqual(records[7000], "TELL")
        self.assertEqual(records[7120], "HI")
        self.assertEqual(records[7121], "BYE")
        self.assertEqual(records[7122], "YES")
        self.assertEqual(records[7123], "NO")
        self.assertEqual(records[7146], "SOME")

    def test_v46_detector_missed_non_slash_canonical_parser_records(self):
        self.assertTrue(v46.looks_like_runtime_matcher_source("BYE/GOODBYE/QUIT/FAREWELL/"))
        self.assertFalse(v46.looks_like_runtime_matcher_source("BYE"))
        self.assertFalse(v46.looks_like_runtime_matcher_source("YES"))
        self.assertFalse(v46.looks_like_runtime_matcher_source("TELL"))

    def test_synonym_and_canonical_tables_link_again(self):
        combined, metadata = v47.load_combined_logic_records(
            ROOT / "data/dos_runtime_matchers.json",
            ROOT / "data/dos_parser_core_records.json",
        )
        self.assertEqual(metadata["combined_record_count"], 250)
        self.assertEqual(combined[7161], "BYE/GOODBYE/QUIT/FAREWELL/")
        self.assertEqual(combined[7121], "BYE")
        self.assertEqual(metadata["bye_pipeline"]["normalized_token"], "BYE")
        self.assertEqual(metadata["bye_pipeline"]["canonical_token"], "BYE")
        self.assertTrue(metadata["bye_pipeline"]["linked"])
        for link in metadata["canonical_links"]:
            synonym = combined[link["synonym_message_id"]]
            canonical = combined[link["canonical_message_id"]].strip()
            self.assertEqual(v47.first_synonym(synonym), canonical)


if __name__ == "__main__":
    unittest.main()
