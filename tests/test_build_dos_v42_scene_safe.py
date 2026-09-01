from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v42_scene_safe import (  # noqa: E402
    DEFAULT_ESCAPE,
    JAN_ETTE_MESSAGE_RANGE,
    SCENE_RANK_RESERVED,
    SCENE_RANK_RESERVED_SET,
    build_safe_unicode_codebook,
    count_reserved_rank_payloads,
    decode_localized_display,
    safe_rank_alphabet,
)


class SceneSafeV42Tests(unittest.TestCase):
    def test_reserved_set_covers_raw_scene_commands_but_keeps_space(self) -> None:
        self.assertEqual(b"!%&]@#|", SCENE_RANK_RESERVED)
        self.assertNotIn(0x20, SCENE_RANK_RESERVED_SET)
        self.assertNotIn(DEFAULT_ESCAPE, SCENE_RANK_RESERVED_SET)

    def test_safe_rank_alphabet_filters_structural_bytes(self) -> None:
        values = [0x17, 0x20, 0x21, 0x25, 0x26, 0x2E, 0x40, 0x5D, 0x5F, 0x7C]
        codes = {value: (0,) * (1 + index % 3) for index, value in enumerate(values)}
        alphabet = safe_rank_alphabet(codes)
        self.assertIn(0x20, alphabet)
        self.assertIn(0x2E, alphabet)
        self.assertIn(0x5F, alphabet)
        self.assertNotIn(0x17, alphabet)
        self.assertFalse(SCENE_RANK_RESERVED_SET.intersection(alphabet))

    def test_safe_codebook_never_assigns_reserved_pair_bytes(self) -> None:
        values = [0x17, 0x20, 0x21, 0x25, 0x26, 0x2E, 0x30, 0x31, 0x32, 0x40, 0x5D, 0x5F, 0x7C]
        codes = {value: (0,) * (1 + index % 4) for index, value in enumerate(values)}
        codebook, alphabet = build_safe_unicode_codebook(
            ["가나다라마바사아자차카타파하"], codes
        )
        self.assertGreaterEqual(len(alphabet) ** 2, len(codebook))
        for pair in codebook.values():
            self.assertFalse(SCENE_RANK_RESERVED_SET.intersection(pair))

    def test_collision_counter_looks_only_inside_korean_pairs(self) -> None:
        raw = bytes(
            [
                ord("!"),
                DEFAULT_ESCAPE,
                0x20,
                ord("!"),
                DEFAULT_ESCAPE,
                DEFAULT_ESCAPE,
                DEFAULT_ESCAPE,
                0x2E,
                0x30,
            ]
        )
        self.assertEqual(1, count_reserved_rank_payloads(raw))

    def test_old_stream_decodes_korean_without_losing_literal_controls(self) -> None:
        codebook = {"가": (0x20, 0x21)}
        raw = bytes([DEFAULT_ESCAPE, 0x20, 0x21, ord("%"), 0x0A])
        self.assertEqual("가%<0x0A>", decode_localized_display(raw, codebook))

    def test_jan_ette_regression_range_is_pinned(self) -> None:
        self.assertEqual(29600, JAN_ETTE_MESSAGE_RANGE.start)
        self.assertEqual(29757, JAN_ETTE_MESSAGE_RANGE.stop)


if __name__ == "__main__":
    unittest.main()
