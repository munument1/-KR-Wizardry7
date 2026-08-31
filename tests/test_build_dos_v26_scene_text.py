from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from audit_dos_korean_boundaries import load_records  # noqa: E402
from build_dos_v20_ui_complete import MZ_HEADER_SIZE, OVERLAY_ORIGIN, call_target  # noqa: E402
from build_dos_v25_scene_text import SCENE_FIND_CALLS, SCENE_FIND_HELPER  # noqa: E402
from build_dos_v26_scene_text import (  # noqa: E402
    TRAILING_ASCII_HELPER,
    TRAILING_MARKER_PATCH_OFFSET,
    audit_trailing_marker_collisions,
    patch_scene_text_v26,
    trailing_ascii_byte,
    trailing_ascii_helper_bytes,
)


class SceneTextV26PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.game_dir = ROOT / "outputs" / "v24_boundary_audited_final" / "DSAVANT"

    def test_reported_intro_words_end_in_embedded_alignment_bytes(self) -> None:
        _, records = load_records(self.game_dir)
        for message_id in (15000, 15002):
            record = next(record for record in records if record.message_id == message_id)
            raw = base64.b64decode(record.raw_base64)
            affected = [
                word for word in raw.replace(b"_", b" ").split(b" ")
                if word and word[-1] in (0x24, 0x5E) and trailing_ascii_byte(word) == 0
            ]
            self.assertTrue(affected, message_id)
        self.assertEqual(0x24, trailing_ascii_byte(b"center$"))
        self.assertEqual(0x5E, trailing_ascii_byte(b"left^"))

    def test_collision_audit_locks_the_second_failure_class(self) -> None:
        report = audit_trailing_marker_collisions(self.game_dir)
        self.assertEqual(95, report["affected_records"])
        self.assertEqual(95, report["affected_words"])
        self.assertEqual(1, report["reported_intro_records"]["15000"])
        self.assertEqual(1, report["reported_intro_records"]["15002"])

    def test_v26_injects_both_helpers_and_patches_all_three_sites(self) -> None:
        ds = (self.game_dir / "DS.EXE").read_bytes()
        vbase = (self.game_dir / "VBASE.OVR").read_bytes()
        patched_ds, patched_vbase = patch_scene_text_v26(ds, vbase)
        self.assertEqual(len(ds), len(patched_ds))
        self.assertEqual(len(vbase), len(patched_vbase))
        helper = trailing_ascii_helper_bytes()
        start = MZ_HEADER_SIZE + TRAILING_ASCII_HELPER
        self.assertEqual(helper, patched_ds[start : start + len(helper)])
        for offset in SCENE_FIND_CALLS:
            self.assertEqual(SCENE_FIND_HELPER, call_target(patched_vbase, offset, OVERLAY_ORIGIN))
        self.assertNotEqual(
            vbase[TRAILING_MARKER_PATCH_OFFSET : TRAILING_MARKER_PATCH_OFFSET + 11],
            patched_vbase[TRAILING_MARKER_PATCH_OFFSET : TRAILING_MARKER_PATCH_OFFSET + 11],
        )


if __name__ == "__main__":
    unittest.main()
