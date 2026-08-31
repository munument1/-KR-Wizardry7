from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v19_baseline import BytePatch, apply_guarded_patches  # noqa: E402


class GuardedPatchTests(unittest.TestCase):
    def test_applies_same_size_patch(self) -> None:
        source = bytes.fromhex("00 11 22 33 44")
        patches = (BytePatch("fixture", 1, bytes.fromhex("11 22"), bytes.fromhex("AA BB")),)
        self.assertEqual(bytes.fromhex("00 AA BB 33 44"), apply_guarded_patches(source, patches))

    def test_rejects_unexpected_source_bytes(self) -> None:
        patch = BytePatch("fixture", 1, b"\x99", b"\xAA")
        with self.assertRaisesRegex(ValueError, "expected 99, found 11"):
            apply_guarded_patches(b"\x00\x11", (patch,))

    def test_rejects_size_change(self) -> None:
        patch = BytePatch("fixture", 0, b"\x00", b"\x00\x01")
        with self.assertRaisesRegex(ValueError, "changes file size"):
            apply_guarded_patches(b"\x00", (patch,))

    def test_rejects_overlapping_patches(self) -> None:
        patches = (
            BytePatch("first", 0, b"\x00\x01", b"\x10\x11"),
            BytePatch("second", 1, b"\x11\x02", b"\x20\x21"),
        )
        with self.assertRaisesRegex(ValueError, "overlaps"):
            apply_guarded_patches(b"\x00\x01\x02", patches)


if __name__ == "__main__":
    unittest.main()
