from __future__ import annotations

import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MESSAGES = ROOT / "outputs" / "dos_translation" / "messages.csv"


class CopyProtectionAnswerTests(unittest.TestCase):
    def test_answers_remain_ascii_and_match_original(self) -> None:
        with MESSAGES.open(encoding="utf-8", newline="") as handle:
            rows = {
                int(row[0]): row
                for row in csv.reader(handle)
                if row and row[0].isdigit() and 2500 <= int(row[0]) <= 2574
            }

        self.assertEqual(set(range(2500, 2575)), set(rows))
        for message_id, row in rows.items():
            with self.subTest(message_id=message_id):
                self.assertEqual(row[1], row[2])
                row[2].encode("ascii")


if __name__ == "__main__":
    unittest.main()
