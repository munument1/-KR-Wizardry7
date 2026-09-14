from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_dos_v49_read_buffer as v49  # noqa: E402


class ReadBufferV49Tests(unittest.TestCase):
    def test_patch_moves_only_frame_and_two_buffer_references(self):
        raw = bytearray(0x3CC0)
        for patch in v49.VPCVW_PATCHES:
            raw[patch.offset : patch.offset + len(patch.expected)] = patch.expected
        before = bytes(raw)
        after = v49.apply_guarded_patches(before, v49.VPCVW_PATCHES)
        differences = [
            index for index, (left, right) in enumerate(zip(before, after))
            if left != right
        ]
        self.assertEqual(differences, [0x3C7C, 0x3CA7, 0x3CBB])
        self.assertEqual(after[0x3C7B:0x3C7E], bytes.fromhex("B8 81 FF"))
        self.assertEqual(after[0x3CA5:0x3CA8], bytes.fromhex("8D 46 81"))
        self.assertEqual(after[0x3CB9:0x3CBC], bytes.fromhex("8D 46 81"))

    def test_new_capacity_covers_published_korean_corpus(self):
        self.assertEqual(v49.OLD_BUFFER_BYTES, 86)
        self.assertEqual(v49.NEW_BUFFER_BYTES, 127)
        self.assertEqual(v49.DECODER_TERMINATOR_BYTES, 2)
        self.assertGreater(v49.EXPECTED_BOOK_MAX_DECODED + 2, v49.OLD_BUFFER_BYTES)
        self.assertLessEqual(v49.EXPECTED_CORPUS_MAX_DECODED + 2, v49.NEW_BUFFER_BYTES)
        self.assertEqual(v49.EXPECTED_FIRST_OLD_OVERFLOW, 21606)
        self.assertEqual(v49.EXPECTED_BOOK_MAX_ID, 21633)


if __name__ == "__main__":
    unittest.main()
