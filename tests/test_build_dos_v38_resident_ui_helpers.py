from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v20_ui_complete import (  # noqa: E402
    FORMULAS,
    OVERLAY_ORIGIN,
    WIDTH_ADAPTER,
)
from build_dos_v21_stat_repaint import STAT_REPAINT_HELPER  # noqa: E402
from build_dos_v38_resident_ui_helpers import (  # noqa: E402
    NEW_STAT_REPAINT_HELPER,
    NEW_WIDTH_ADAPTER,
    ROOT_DEAD_TAIL_END,
    compact_stat_repaint_bytes,
    relocated_width_adapter_bytes,
)


class ResidentUiHelperRelocationTests(unittest.TestCase):
    def test_new_helpers_are_below_every_overlay(self) -> None:
        self.assertLess(NEW_WIDTH_ADAPTER, OVERLAY_ORIGIN)
        self.assertLess(NEW_STAT_REPAINT_HELPER, OVERLAY_ORIGIN)
        self.assertLessEqual(
            NEW_STAT_REPAINT_HELPER + len(compact_stat_repaint_bytes()),
            ROOT_DEAD_TAIL_END,
        )

    def test_old_helpers_were_inside_overlay_window(self) -> None:
        self.assertGreaterEqual(WIDTH_ADAPTER, OVERLAY_ORIGIN)
        self.assertGreaterEqual(STAT_REPAINT_HELPER, OVERLAY_ORIGIN)

    def test_compact_layout_fits_replaced_width_function_tail(self) -> None:
        width = relocated_width_adapter_bytes()
        stat = compact_stat_repaint_bytes()
        self.assertEqual(18, len(width))
        self.assertEqual(20, len(stat))
        self.assertEqual(NEW_STAT_REPAINT_HELPER, NEW_WIDTH_ADAPTER + len(width))
        self.assertLessEqual(NEW_STAT_REPAINT_HELPER + len(stat), ROOT_DEAD_TAIL_END)

    def test_save_file_dialog_uses_the_width_adapter_path(self) -> None:
        # VBASE file offsets 0x100B and 0x10C8 are runtime 0x6052/0x610F,
        # inside the 0x5F3E file dialog called by save/load.
        sites = set(FORMULAS["VBASE.OVR"]["constant_minus_length_times_6"])
        self.assertIn(0x100B, sites)
        self.assertIn(0x10C8, sites)


if __name__ == "__main__":
    unittest.main()
