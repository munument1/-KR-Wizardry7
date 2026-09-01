from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_dos_v43_parser_neutral as v43  # noqa: E402
from extract_gold_messages import RangeEntry  # noqa: E402


class DummyRecord:
    def __init__(self, range_index: int, message_id: int):
        self.range_index = range_index
        self.message_id = message_id


class ParserNeutralV43Tests(unittest.TestCase):
    def test_reserved_set_covers_every_known_parser_token(self):
        self.assertEqual(v43.FULL_PARSER_RESERVED, b" _$^!%&]@#|")
        self.assertEqual(
            v43.FULL_PARSER_RESERVED_SET,
            frozenset(b" _$^!%&]@#|"),
        )

    def test_rank_alphabet_filters_all_structural_bytes(self):
        codes = {value: (0,) for value in range(0x20, 0x7F)}
        codes[v43.DEFAULT_ESCAPE] = (1,)
        alphabet = v43.parser_neutral_rank_alphabet(codes)
        self.assertNotIn(v43.DEFAULT_ESCAPE, alphabet)
        for token in v43.FULL_PARSER_RESERVED:
            self.assertNotIn(token, alphabet)
        self.assertIn(ord("A"), alphabet)

    def test_collision_counter_ignores_literal_controls(self):
        raw = b"A_$^!%&]@#|" + bytes(
            [v43.DEFAULT_ESCAPE, ord("_"), ord("$")]
        ) + b"Z"
        counts = v43.rank_payload_token_counts(raw)
        self.assertEqual(counts[ord("_")], 1)
        self.assertEqual(counts[ord("$")], 1)
        self.assertEqual(sum(counts.values()), 2)

    def test_collision_counter_skips_literal_escape(self):
        raw = bytes(
            [v43.DEFAULT_ESCAPE, v43.DEFAULT_ESCAPE]
        ) + bytes([v43.DEFAULT_ESCAPE, ord("A"), ord("B")])
        self.assertEqual(sum(v43.rank_payload_token_counts(raw).values()), 0)

    def test_padding_split_can_recover_bank_tail(self):
        # Four valid 225-byte records consume 900 bytes in the first range.
        # A following 200-byte range moves wholly to the next bank.  Splitting
        # the second range lets its first 100-byte record use the tail.
        entries = [
            RangeEntry(0, 100, 0, 3, 0),
            RangeEntry(1, 200, 0, 1, 0),
        ]
        records = [
            DummyRecord(0, 100), DummyRecord(0, 101),
            DummyRecord(0, 102), DummyRecord(0, 103),
            DummyRecord(1, 200), DummyRecord(1, 201),
        ]
        packed = {
            100: bytes(224), 101: bytes(224),
            102: bytes(224), 103: bytes(224),
            200: bytes(99), 201: bytes(99),
        }
        initial = v43._initial_segments(entries, records)
        self.assertEqual(v43._layout_size(initial, packed), 1224)
        split = [initial[0], (1, (200,)), (1, (201,))]
        self.assertEqual(v43._layout_size(split, packed), 1124)
        data, out_entries, padding = v43.pack_segments(split, packed)
        self.assertEqual(len(data), 1124)
        self.assertEqual(padding, 24)
        self.assertEqual(
            [(entry.start_id, entry.id_span) for entry in out_entries],
            [(100, 3), (200, 0), (201, 0)],
        )

    def test_jan_ette_regression_range_is_pinned(self):
        self.assertEqual(v43.JAN_ETTE_MESSAGE_RANGE.start, 29600)
        self.assertEqual(v43.JAN_ETTE_MESSAGE_RANGE.stop - 1, 29756)


if __name__ == "__main__":
    unittest.main()
