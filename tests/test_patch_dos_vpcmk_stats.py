from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from patch_dos_vpcmk_stats import STAT_PATCHES  # noqa: E402


class StatPatchSpecificationTests(unittest.TestCase):
    def test_patches_are_same_size_and_non_overlapping(self) -> None:
        occupied: set[int] = set()
        for patch in STAT_PATCHES:
            self.assertEqual(len(patch.expected), len(patch.replacement), patch.label)
            locations = set(range(patch.offset, patch.offset + len(patch.expected)))
            self.assertFalse(occupied & locations, patch.label)
            occupied |= locations

    def test_skill_layout_region_is_untouched(self) -> None:
        skill_region = range(0x24F0, 0x2840)
        self.assertFalse(
            any(patch.offset in skill_region for patch in STAT_PATCHES),
            "stat-only patch must not alter creation skill geometry",
        )


if __name__ == "__main__":
    unittest.main()
