from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_messages import encode_translation, huffman_codes  # noqa: E402
from patch_dos_message_fixed_codebook import load_codebook  # noqa: E402


class DosSaveMenuSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        game = ROOT / "outputs" / "v29_reference_logo_final" / "DSAVANT"
        cls.codes = huffman_codes((game / "MISC.HDR").read_bytes())
        cls.codebook = load_codebook(game / "korean_codebook.json")
        with (ROOT / "outputs" / "dos_translation" / "messages.csv").open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            cls.rows = {int(row["message_id"]): row for row in csv.DictReader(stream)}

    def encoded_length(self, message_id: int) -> int:
        return len(
            encode_translation(
                self.rows[message_id]["translation"], self.codes, self.codebook
            )
        )

    def test_main_and_pause_menu_items_fit_twenty_byte_slots(self) -> None:
        for message_id in (*range(1000, 1009), *range(2200, 2206)):
            with self.subTest(message_id=message_id):
                self.assertLessEqual(self.encoded_length(message_id), 19)

    def test_save_related_replacements_are_concise(self) -> None:
        expected = {
            1005: "게임 불러오기",
            1127: "캐릭터 저장?",
            1400: "게임 불러오기",
            2205: "저장 없이 끝",
        }
        self.assertEqual(
            expected,
            {message_id: self.rows[message_id]["translation"] for message_id in expected},
        )


if __name__ == "__main__":
    unittest.main()
