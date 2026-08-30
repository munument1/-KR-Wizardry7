from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v19_baseline import apply_guarded_patches  # noqa: E402
from build_dos_v19_ui_final import (  # noqa: E402
    DS_ROOT_CENTERING_PATCHES,
    VPCMK_FINAL_CENTERING_PATCHES,
)
from build_dos_v19_ui_v2 import (  # noqa: E402
    VPCMK_CENTERING_PATCHES,
    VPCMK_STAT_PATCHES,
)


BASELINE = ROOT / "outputs" / "v19_clean_baseline_rebuilt_20260830" / "VPCMK.OVR"
EXPECTED_FINAL_VPCMK_SHA256 = "d27b6e1f961a9e1aef10d0d2d0127da940c5e36e663a5aeee33365b2747a5d60"
EXPECTED_FINAL_DS_SHA256 = "bf2590602236e19694e48d35464d6f0edaaab9e8d8e74c1da4e2e962c1ffc217"


class UiFinalPatchSpecificationTests(unittest.TestCase):
    def test_all_final_patches_are_same_size_and_non_overlapping(self) -> None:
        patches = (
            VPCMK_CENTERING_PATCHES
            + VPCMK_STAT_PATCHES
            + VPCMK_FINAL_CENTERING_PATCHES
        )
        occupied: set[int] = set()
        for patch in patches:
            self.assertEqual(len(patch.expected), len(patch.replacement), patch.label)
            locations = set(range(patch.offset, patch.offset + len(patch.expected)))
            self.assertFalse(occupied & locations, patch.label)
            occupied |= locations

    def test_final_overlay_hash_and_size_are_locked(self) -> None:
        source = BASELINE.read_bytes()
        patched = apply_guarded_patches(
            source,
            VPCMK_CENTERING_PATCHES
            + VPCMK_STAT_PATCHES
            + VPCMK_FINAL_CENTERING_PATCHES,
        )
        self.assertEqual(len(source), len(patched))
        self.assertEqual(EXPECTED_FINAL_VPCMK_SHA256, hashlib.sha256(patched).hexdigest())

    def test_resident_centering_patch_hash_and_size_are_locked(self) -> None:
        source = (
            ROOT / "outputs" / "v19_clean_baseline_rebuilt_20260830" / "DS.EXE"
        ).read_bytes()
        patched = apply_guarded_patches(source, DS_ROOT_CENTERING_PATCHES)
        self.assertEqual(len(source), len(patched))
        self.assertEqual(EXPECTED_FINAL_DS_SHA256, hashlib.sha256(patched).hexdigest())

    def test_only_visual_skill_width_path_is_touched(self) -> None:
        skill_range = range(0x24F0, 0x2840)
        skill_patches = [
            patch
            for patch in VPCMK_FINAL_CENTERING_PATCHES
            if patch.offset in skill_range
        ]
        self.assertEqual(
            [0x263A, 0x265F],
            [patch.offset for patch in skill_patches],
        )

    def test_skill_loop_branch_destinations_are_preserved(self) -> None:
        loop_patch = next(
            patch for patch in VPCMK_FINAL_CENTERING_PATCHES if patch.offset == 0x263A
        )
        data = loop_patch.replacement
        jge = data.index(b"\x7d")
        self.assertEqual(0x265B, loop_patch.offset + jge + 2 + data[jge + 1])
        jump = data.index(b"\xe9", jge + 2)
        displacement = int.from_bytes(data[jump + 1 : jump + 3], "little", signed=True)
        self.assertEqual(0x25C1, loop_patch.offset + jump + 3 + displacement)

    def test_logical_strlen_calls_are_untouched(self) -> None:
        source = BASELINE.read_bytes()
        patched = apply_guarded_patches(source, VPCMK_FINAL_CENTERING_PATCHES)
        for call_offset in (0x0119, 0x268A, 0x6849, 0x6949):
            self.assertEqual(
                source[call_offset : call_offset + 3],
                patched[call_offset : call_offset + 3],
            )


if __name__ == "__main__":
    unittest.main()
