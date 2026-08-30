from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from audit_dos_korean_boundaries import load_records  # noqa: E402
from build_dos_messages import encode_translation, huffman_codes  # noqa: E402
from build_dos_v20_ui_complete import MZ_HEADER_SIZE, OVERLAY_ORIGIN, call_target  # noqa: E402
from build_dos_v25_scene_text import (  # noqa: E402
    ORIGINAL_FIND_TARGET,
    SCENE_FIND_CALLS,
    SCENE_FIND_HELPER,
    audit_scene_records,
    glyph_delimiter_collisions,
    korean_aware_find,
    patch_scene_text,
    scene_find_helper_bytes,
)
from patch_dos_message_fixed_codebook import load_codebook  # noqa: E402


class SceneTextPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.game_dir = ROOT / "outputs" / "v24_boundary_audited_final" / "DSAVANT"

    def test_reference_search_ignores_delimiters_inside_korean_glyphs(self) -> None:
        misc, records = load_records(self.game_dir)
        record = next(record for record in records if record.message_id == 31650)
        raw = base64.b64decode(record.raw_base64)
        self.assertGreater(len(glyph_delimiter_collisions(raw)), 0)
        self.assertEqual(raw.index(0x20), 4)  # old byte search split the second glyph
        self.assertEqual(9, korean_aware_find(raw, 0x20))

        codes = huffman_codes(misc)
        codebook = load_codebook(self.game_dir / "korean_codebook.json")
        sample = encode_translation("버려진 사원 다음", codes, codebook)
        literal_space = len(encode_translation("버려진", codes, codebook))
        self.assertEqual(0x20, sample[literal_space])
        self.assertEqual(literal_space, korean_aware_find(sample, 0x20))

    def test_all_four_reported_records_have_embedded_delimiter_payloads(self) -> None:
        report = audit_scene_records(self.game_dir)
        self.assertEqual(757, report["affected_records"])
        self.assertEqual(8797, report["embedded_delimiter_bytes"])
        self.assertTrue(all(report["aletheides_records"].values()))

    def test_helper_fits_empty_resident_cave_and_calls_are_retargeted(self) -> None:
        ds = (self.game_dir / "DS.EXE").read_bytes()
        vbase = (self.game_dir / "VBASE.OVR").read_bytes()
        helper = scene_find_helper_bytes()
        cave = MZ_HEADER_SIZE + SCENE_FIND_HELPER
        self.assertEqual(b"\x00" * len(helper), ds[cave : cave + len(helper)])
        for offset in SCENE_FIND_CALLS:
            self.assertEqual(ORIGINAL_FIND_TARGET, call_target(vbase, offset, OVERLAY_ORIGIN))

        patched_ds, patched_vbase = patch_scene_text(ds, vbase)
        self.assertEqual(len(ds), len(patched_ds))
        self.assertEqual(len(vbase), len(patched_vbase))
        self.assertEqual(helper, patched_ds[cave : cave + len(helper)])
        for offset in SCENE_FIND_CALLS:
            self.assertEqual(SCENE_FIND_HELPER, call_target(patched_vbase, offset, OVERLAY_ORIGIN))


if __name__ == "__main__":
    unittest.main()
