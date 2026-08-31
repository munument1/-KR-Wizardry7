from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_messages import decode_translation  # noqa: E402
from build_dos_v24_boundary_audit import EXPECTED_CHANGED_MESSAGES, V24_MESSAGE_HASHES  # noqa: E402
from extract_gold_messages import extract_messages, parse_header, sha256  # noqa: E402
from patch_dos_message_fixed_codebook import load_codebook  # noqa: E402


class V24BoundaryAuditBuildTests(unittest.TestCase):
    def test_message_hashes_are_locked(self) -> None:
        root = ROOT / "outputs" / "v24_audit_message_layer"
        for name, expected in V24_MESSAGE_HASHES.items():
            self.assertEqual(expected.upper(), sha256((root / name).read_bytes()))

    def test_repaired_messages_decode_exactly(self) -> None:
        root = ROOT / "outputs" / "v24_audit_message_layer"
        misc = (root / "MISC.HDR").read_bytes()
        _, entries, _ = parse_header((root / "MSG.HDR").read_bytes(), "dos")
        records = {r.message_id: r for r in extract_messages((root / "MSG.DBS").read_bytes(), entries, misc)}
        codebook = load_codebook(root / "korean_codebook.json")
        for message_id_text, expected in EXPECTED_CHANGED_MESSAGES.items():
            message_id = int(message_id_text)
            decoded = decode_translation(
                base64.b64decode(records[message_id].raw_base64), codebook
            )
            self.assertEqual(expected.replace("<0x02>", "\x02").replace("<0x03>", "\x03").replace("<0x05>", "\x05").replace("<0x01>", "\x01"), decoded)


if __name__ == "__main__":
    unittest.main()
