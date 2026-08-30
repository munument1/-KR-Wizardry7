from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v20_ui_complete import MZ_HEADER_SIZE, call_target  # noqa: E402
from build_dos_v21_stat_repaint import (  # noqa: E402
    RECT_FILL_TARGET,
    STAT_REPAINT_HELPER,
    VPCMK_ORIGIN,
    VPCMK_STAT_DRAW_TARGET,
    stat_repaint_helper_bytes,
)


BUILD = ROOT / "outputs" / "v21_stat_repaint_final" / "DSAVANT"


class StatRepaintPatchSpecificationTests(unittest.TestCase):
    def test_helper_is_locked_and_calls_only_fill_then_normal_draw(self) -> None:
        image = (BUILD / "DS.EXE").read_bytes()[MZ_HEADER_SIZE:]
        helper = stat_repaint_helper_bytes()
        self.assertEqual(36, len(helper))
        self.assertEqual(helper, image[STAT_REPAINT_HELPER : STAT_REPAINT_HELPER + 36])
        self.assertEqual(RECT_FILL_TARGET, call_target(image, STAT_REPAINT_HELPER + 14, 0))
        self.assertEqual(VPCMK_STAT_DRAW_TARGET, call_target(image, STAT_REPAINT_HELPER + 26, 0))

    def test_clear_rectangle_and_color_are_exact(self) -> None:
        helper = stat_repaint_helper_bytes()
        self.assertEqual(
            bytes.fromhex("6A 00 6A 6C 68 A8 00 6A 20 6A 66"),
            helper[3:14],
        )

    def test_interactive_redraw_routes_through_helper(self) -> None:
        vpcmk = (BUILD / "VPCMK.OVR").read_bytes()
        self.assertEqual(
            STAT_REPAINT_HELPER,
            call_target(vpcmk, 0x46E2, VPCMK_ORIGIN),
        )

    def test_output_hashes_and_overlay_size_are_locked(self) -> None:
        ds = (BUILD / "DS.EXE").read_bytes()
        vpcmk = (BUILD / "VPCMK.OVR").read_bytes()
        self.assertEqual(
            "12dba1d6ea9ddf12dea5027498b33864b9e865b6ef3126ddbea520998fe6dc3e",
            hashlib.sha256(ds).hexdigest(),
        )
        self.assertEqual(
            "36b50daea346973750a0cc9c9b18c7b222f216cc73662e01e7c1dd1ee52a625f",
            hashlib.sha256(vpcmk).hexdigest(),
        )
        self.assertEqual(29_885, len(vpcmk))


if __name__ == "__main__":
    unittest.main()
