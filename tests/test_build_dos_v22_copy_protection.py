from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_messages import decode_translation  # noqa: E402
from build_dos_v22_copy_protection import V21_HASHES, V22_MESSAGE_HASHES  # noqa: E402
from extract_gold_messages import extract_messages, parse_header, sha256  # noqa: E402
from patch_dos_message_fixed_codebook import load_codebook  # noqa: E402


class V22CopyProtectionBuildTests(unittest.TestCase):
    def test_inputs_match_guarded_hashes(self) -> None:
        v21 = ROOT / "outputs" / "v21_stat_repaint_final" / "DSAVANT"
        messages = ROOT / "outputs" / "v22_message_layer_utf8"
        for name, expected in V21_HASHES.items():
            self.assertEqual(expected.upper(), sha256((v21 / name).read_bytes()))
        for name, expected in V22_MESSAGE_HASHES.items():
            self.assertEqual(expected.upper(), sha256((messages / name).read_bytes()))

    def test_built_message_decodes_to_single_ordinal(self) -> None:
        root = ROOT / "outputs" / "v22_message_layer_utf8"
        misc = (root / "MISC.HDR").read_bytes()
        _, entries, _ = parse_header((root / "MSG.HDR").read_bytes(), "dos")
        records = extract_messages((root / "MSG.DBS").read_bytes(), entries, misc)
        record = next(item for item in records if item.message_id == 1052)
        template = decode_translation(
            base64.b64decode(record.raw_base64),
            load_codebook(root / "korean_codebook.json"),
        )
        self.assertEqual("설명서에서 세 번째 단어를 입력하십시오", template.replace("$", "세 번째"))


if __name__ == "__main__":
    unittest.main()
