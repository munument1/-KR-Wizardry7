from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build_dos_vga_picture_fail_probe import (
    DIAG_BYTES,
    DIAG_FILE,
    DIAG_REGION_SIZE,
    FATAL_BRANCH_EXPECTED,
    FATAL_BRANCH_FILE,
    FATAL_BRANCH_PATCHED,
    STOCK_DIAG_REGION_PREFIX,
    STOCK_VGA_SIZE,
    patch_vga,
)
from tools.match_dos_pic_failure import find_matches, parse_line


class VgaPictureFailProbeTests(unittest.TestCase):
    def test_probe_fits_stock_fatal_region_and_preserves_size(self) -> None:
        self.assertEqual(len(DIAG_BYTES), 123)
        self.assertEqual(DIAG_REGION_SIZE, 124)
        data = bytearray(STOCK_VGA_SIZE)
        data[FATAL_BRANCH_FILE : FATAL_BRANCH_FILE + 3] = FATAL_BRANCH_EXPECTED
        data[DIAG_FILE : DIAG_FILE + len(STOCK_DIAG_REGION_PREFIX)] = STOCK_DIAG_REGION_PREFIX

        patched = patch_vga(bytes(data))
        self.assertEqual(len(patched), STOCK_VGA_SIZE)
        self.assertEqual(
            patched[FATAL_BRANCH_FILE : FATAL_BRANCH_FILE + 3],
            FATAL_BRANCH_PATCHED,
        )
        self.assertEqual(patched[DIAG_FILE : DIAG_FILE + len(DIAG_BYTES)], DIAG_BYTES)
        self.assertEqual(patched[DIAG_FILE + len(DIAG_BYTES)], 0x90)

    def test_picfail_line_and_header_match(self) -> None:
        slot, size, pool = parse_line("PICFAIL S=0003 SZ=000028A0 P=4201")
        self.assertEqual((slot, size, pool), (3, 0x28A0, 0x4201))

        with tempfile.TemporaryDirectory() as directory:
            game_dir = Path(directory)
            (game_dir / "MON00.PIC").write_bytes((0x28A0).to_bytes(4, "little") + b"X" * 0x28A0)
            (game_dir / "OTHER.PIC").write_bytes((0x1234).to_bytes(4, "little") + b"Y" * 0x1234)
            matches = find_matches(game_dir, size)

        self.assertEqual([entry["name"] for entry in matches], ["MON00.PIC"])
        self.assertEqual(matches[0]["file_size"], 0x28A4)
        self.assertTrue(matches[0]["file_size_matches_header_plus_4"])


if __name__ == "__main__":
    unittest.main()
