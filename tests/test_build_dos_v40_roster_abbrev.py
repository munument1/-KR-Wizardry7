from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v40_roster_abbrev import (  # noqa: E402
    CHAR_ENTRY,
    CHAR_CONTINUATION,
    FONT_INVERSE_TABLE,
    ROSTER_STREAM_HELPER,
    V39_FONT_DISPATCHER_END,
    assemble_roster_stream,
    near_jump,
)


def jump_target(code: bytes, offset: int, origin: int) -> int:
    if code[offset] != 0xE9:
        raise AssertionError(f"expected E9 at {offset:#x}")
    displacement = int.from_bytes(
        code[offset + 1 : offset + 3], "little", signed=True
    )
    return origin + offset + 3 + displacement


HAS_BINUTILS = all(shutil.which(name) for name in ("as", "ld", "objcopy"))


class RosterAbbreviationV40Tests(unittest.TestCase):
    def test_resident_char_entry_jump_targets_helper(self) -> None:
        jump = near_jump(ROSTER_STREAM_HELPER, CHAR_ENTRY)
        self.assertEqual(3, len(jump))
        self.assertEqual(
            ROSTER_STREAM_HELPER,
            jump_target(jump, 0, CHAR_ENTRY),
        )

    @unittest.skipUnless(HAS_BINUTILS, "GNU binutils are required")
    def test_helper_fits_resident_gap(self) -> None:
        helper = assemble_roster_stream()
        self.assertGreaterEqual(ROSTER_STREAM_HELPER, V39_FONT_DISPATCHER_END)
        self.assertLessEqual(
            ROSTER_STREAM_HELPER + len(helper),
            FONT_INVERSE_TABLE,
        )
        self.assertGreater(len(helper), 64)

    @unittest.skipUnless(HAS_BINUTILS, "GNU binutils are required")
    def test_helper_returns_to_original_character_body(self) -> None:
        helper = assemble_roster_stream()
        targets = []
        for offset in range(len(helper) - 2):
            if helper[offset] != 0xE9:
                continue
            targets.append(
                jump_target(helper, offset, ROSTER_STREAM_HELPER)
            )
        self.assertIn(CHAR_CONTINUATION, targets)

    @unittest.skipUnless(HAS_BINUTILS, "GNU binutils are required")
    def test_helper_has_far_return_for_suppressed_escape_bytes(self) -> None:
        helper = assemble_roster_stream()
        self.assertIn(0xCB, helper)  # retf


if __name__ == "__main__":
    unittest.main()
