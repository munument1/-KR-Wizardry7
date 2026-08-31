from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v19_ui_v2 import (  # noqa: E402
    VBASE_CENTERING_PATCHES,
    VPCMK_CENTERING_PATCHES,
    VPCMK_STAT_PATCHES,
)


class UiV2PatchSpecificationTests(unittest.TestCase):
    def test_expected_number_of_proven_centering_sites(self) -> None:
        self.assertEqual(6, len(VPCMK_CENTERING_PATCHES))
        self.assertEqual(2, len(VBASE_CENTERING_PATCHES))

    def test_all_patches_are_same_size_and_non_overlapping(self) -> None:
        for group in (
            VPCMK_CENTERING_PATCHES + VPCMK_STAT_PATCHES,
            VBASE_CENTERING_PATCHES,
        ):
            occupied: set[int] = set()
            for patch in group:
                self.assertEqual(len(patch.expected), len(patch.replacement), patch.label)
                locations = set(range(patch.offset, patch.offset + len(patch.expected)))
                self.assertFalse(occupied & locations, patch.label)
                occupied |= locations

    def test_skill_geometry_region_is_untouched(self) -> None:
        skill_geometry = range(0x24F0, 0x2840)
        patches = VPCMK_CENTERING_PATCHES + VPCMK_STAT_PATCHES
        self.assertFalse(any(patch.offset in skill_geometry for patch in patches))


if __name__ == "__main__":
    unittest.main()
