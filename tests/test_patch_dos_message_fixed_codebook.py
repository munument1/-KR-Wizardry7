from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_messages import decode_translation  # noqa: E402
from extract_gold_messages import extract_messages, parse_header  # noqa: E402
from patch_dos_message_fixed_codebook import (  # noqa: E402
    build_patched_files,
    load_codebook,
)


class FixedCodebookMessagePatchTests(unittest.TestCase):
    def test_copy_protection_ordinal_is_not_duplicated(self) -> None:
        source = ROOT / "outputs" / "v21_stat_repaint_final" / "DSAVANT"
        codebook_path = source / "korean_codebook.json"
        codebook = load_codebook(codebook_path)
        misc = (source / "MISC.HDR").read_bytes()
        header, data, report = build_patched_files(
            (source / "MSG.HDR").read_bytes(),
            (source / "MSG.DBS").read_bytes(),
            misc,
            codebook,
            {1052: "설명서에서 $ 단어를 입력하십시오"},
        )
        _, entries, _ = parse_header(header, "dos")
        records = extract_messages(data, entries, misc)
        record = next(item for item in records if item.message_id == 1052)
        decoded = decode_translation(
            __import__("base64").b64decode(record.raw_base64), codebook
        )
        self.assertEqual("설명서에서 $ 단어를 입력하십시오", decoded)
        self.assertEqual("설명서에서 세 번째 단어를 입력하십시오", decoded.replace("$", "세 번째"))
        self.assertNotIn("번째번째", decoded.replace("$", "세 번째"))
        self.assertEqual(0, report["record_start_crossings"])
        self.assertTrue(report["huffman_tree_preserved"])

    def test_csv_source_contains_corrected_template(self) -> None:
        rows = (ROOT / "outputs" / "dos_translation" / "messages.csv").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn(
            "1052,MANUAL AND ENTER THE $ WORD,설명서에서 $ 단어를 입력하십시오",
            rows,
        )
        self.assertNotIn("설명서에서 $번째 단어", rows)


if __name__ == "__main__":
    unittest.main()
