from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v20_ui_complete import OVERLAY_ORIGIN, WIDTH_TARGET, call_target  # noqa: E402
from build_dos_v21_stat_repaint import RECT_FILL_TARGET, VPCMK_STAT_DRAW_TARGET  # noqa: E402
from build_dos_v39_overlay_safe_resident import (  # noqa: E402
    FONT_DISPATCHER,
    FONT_DISPATCHER_BYTES,
    FONT_INVERSE_TABLE,
    FONT_WIDTH_CONTINUATION,
    FONT_WIDTH_ENTRY,
    ROOT_COMMON_ENTRY,
    ROOT_SAFE_END,
    ROOT_STAT_REPAINT,
    ROOT_TRAILING_ADAPTER,
    ROOT_WIDTH_ADAPTER,
    font_width_dispatch_jump,
    root_helper_block,
)


def jump_target(code: bytes, offset: int, origin: int) -> int:
    if code[offset] != 0xE9:
        raise AssertionError(f"expected E9 at {offset:#x}")
    disp = int.from_bytes(code[offset + 1 : offset + 3], "little", signed=True)
    return origin + offset + 3 + disp


class OverlaySafeResidentV39Tests(unittest.TestCase):
    def test_all_root_helpers_are_below_overlay_origin(self) -> None:
        block = root_helper_block()
        self.assertEqual(44, len(block))
        self.assertLessEqual(ROOT_WIDTH_ADAPTER + len(block), ROOT_SAFE_END)
        self.assertLess(ROOT_SAFE_END, OVERLAY_ORIGIN)
        self.assertEqual(ROOT_WIDTH_ADAPTER + 4, ROOT_TRAILING_ADAPTER)
        self.assertEqual(ROOT_WIDTH_ADAPTER + 7, ROOT_COMMON_ENTRY)
        self.assertEqual(ROOT_WIDTH_ADAPTER + 24, ROOT_STAT_REPAINT)

    def test_dual_adapter_calls_safe_root_width_hook(self) -> None:
        block = root_helper_block()
        call_offset = (ROOT_COMMON_ENTRY - ROOT_WIDTH_ADAPTER) + 7
        self.assertEqual(
            WIDTH_TARGET,
            call_target(block, call_offset, ROOT_WIDTH_ADAPTER),
        )
        self.assertEqual(bytes.fromhex("31 C0 EB 03"), block[:4])
        self.assertEqual(bytes.fromhex("B8 00 01"), block[4:7])

    def test_stat_tail_call_targets_are_exact(self) -> None:
        block = root_helper_block()
        stat_offset = ROOT_STAT_REPAINT - ROOT_WIDTH_ADAPTER
        rect_call = stat_offset + 11
        stat_jump = stat_offset + 17
        self.assertEqual(
            RECT_FILL_TARGET,
            call_target(block, rect_call, ROOT_WIDTH_ADAPTER),
        )
        self.assertEqual(
            VPCMK_STAT_DRAW_TARGET,
            jump_target(block, stat_jump, ROOT_WIDTH_ADAPTER),
        )

    def test_font_dispatcher_fits_before_inverse_table(self) -> None:
        self.assertEqual(124, len(FONT_DISPATCHER_BYTES))
        self.assertGreaterEqual(FONT_DISPATCHER, 0x0AF0)
        self.assertLessEqual(
            FONT_DISPATCHER + len(FONT_DISPATCHER_BYTES),
            FONT_INVERSE_TABLE,
        )

    def test_width_entry_jumps_to_font_dispatcher(self) -> None:
        jump = font_width_dispatch_jump()
        self.assertEqual(3, len(jump))
        self.assertEqual(FONT_DISPATCHER, jump_target(jump, 0, FONT_WIDTH_ENTRY))
        # The dispatcher falls back to the original width body immediately
        # after the replaced push-bp/mov-bp,sp prologue.
        self.assertEqual(0x0A33, FONT_WIDTH_CONTINUATION)

    def test_dispatcher_contains_all_three_operation_guards(self) -> None:
        # cmp ax,0x20 / cmp ax,0x5F / cmp ax,0x0100
        self.assertIn(bytes.fromhex("83 F8 20"), FONT_DISPATCHER_BYTES[:24])
        self.assertIn(bytes.fromhex("83 F8 5F"), FONT_DISPATCHER_BYTES[:24])
        self.assertIn(bytes.fromhex("3D 00 01"), FONT_DISPATCHER_BYTES[:24])
        self.assertEqual(0xCB, FONT_DISPATCHER_BYTES[-1])  # retf


if __name__ == "__main__":
    unittest.main()
