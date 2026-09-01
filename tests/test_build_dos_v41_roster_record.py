from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v41_roster_record import (  # noqa: E402
    PROFESSION_COUNT,
    PROFESSION_MESSAGE_BASE,
    ROSTER_GENDER_MESSAGE_BASE,
    VBASE_GENDER_SOURCE_PATCH,
    VPCMK_GENDER_SOURCE_PATCH,
)


class RosterRecordV41Tests(unittest.TestCase):
    def test_gender_lookup_uses_existing_ascii_mf_table(self) -> None:
        self.assertEqual(455, ROSTER_GENDER_MESSAGE_BASE)
        self.assertEqual(bytes.fromhex("05 8C 00"), VBASE_GENDER_SOURCE_PATCH.expected)
        self.assertEqual(bytes.fromhex("05 C7 01"), VBASE_GENDER_SOURCE_PATCH.replacement)
        self.assertEqual(bytes.fromhex("05 8C 00"), VPCMK_GENDER_SOURCE_PATCH.expected)
        self.assertEqual(bytes.fromhex("05 C7 01"), VPCMK_GENDER_SOURCE_PATCH.replacement)

    def test_profession_prefix_contract_is_one_korean_glyph(self) -> None:
        self.assertEqual(120, PROFESSION_MESSAGE_BASE)
        self.assertEqual(14, PROFESSION_COUNT)

    def test_patch_sizes_are_strictly_fixed(self) -> None:
        for patch in (VBASE_GENDER_SOURCE_PATCH, VPCMK_GENDER_SOURCE_PATCH):
            self.assertEqual(len(patch.expected), len(patch.replacement))
            self.assertEqual(3, len(patch.replacement))


if __name__ == "__main__":
    unittest.main()
