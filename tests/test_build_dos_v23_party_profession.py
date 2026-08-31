from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_messages import decode_translation, encode_translation, huffman_codes  # noqa: E402
from build_dos_v23_party_profession import (  # noqa: E402
    PROFESSION_TRUNCATION_PATCH,
    V23_DS_HASH,
    patch_party_profession,
)
from extract_gold_messages import extract_messages, parse_header, sha256  # noqa: E402
from patch_dos_message_fixed_codebook import load_codebook  # noqa: E402


class V23PartyProfessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = ROOT / "outputs" / "v22_copy_protection_final" / "DSAVANT"

    def test_patch_changes_only_the_terminator_boundary(self) -> None:
        source = (self.root / "DS.EXE").read_bytes()
        patched = patch_party_profession(source)
        offset = PROFESSION_TRUNCATION_PATCH.offset
        changed = [i for i, (before, after) in enumerate(zip(source, patched)) if before != after]
        self.assertEqual([offset + 2], changed)
        self.assertEqual(PROFESSION_TRUNCATION_PATCH.replacement, patched[offset:offset + 4])
        self.assertEqual(V23_DS_HASH.upper(), sha256(patched))
        self.assertEqual(len(source), len(patched))

    def test_every_localized_profession_fits_twelve_byte_boundary(self) -> None:
        misc = (self.root / "MISC.HDR").read_bytes()
        _, entries, _ = parse_header((self.root / "MSG.HDR").read_bytes(), "dos")
        records = {r.message_id: r for r in extract_messages((self.root / "MSG.DBS").read_bytes(), entries, misc)}
        codebook = load_codebook(self.root / "korean_codebook.json")
        codes = huffman_codes(misc)
        expected = {
            120: "전사", 121: "마법사", 122: "사제", 123: "도적",
            124: "레인저", 125: "연금술사", 126: "바드", 127: "사이오닉",
            128: "발키리", 129: "비숍", 130: "로드", 131: "사무라이",
            132: "몽크", 133: "닌자",
        }
        for message_id, text in expected.items():
            raw = base64.b64decode(records[message_id].raw_base64)
            self.assertEqual(text, decode_translation(raw, codebook))
            self.assertEqual(raw, encode_translation(text, codes, codebook))
            self.assertLessEqual(len(raw), 12, (message_id, text, len(raw)))
            self.assertEqual(0, len(raw) % 3, (message_id, text, len(raw)))


if __name__ == "__main__":
    unittest.main()
