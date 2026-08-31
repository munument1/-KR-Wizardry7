from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v20_ui_complete import OVERLAY_ORIGIN, call_target  # noqa: E402
from build_dos_v25_scene_text import SCENE_FIND_HELPER  # noqa: E402
from build_dos_v28_all_scene_text import (  # noqa: E402
    ORIGINAL_TRAILING,
    PARSER_COPIES,
    audit_parser_copies,
    patch_parser_copy,
    trailing_replacement,
)


class AllSceneTextParserPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.game_dir = ROOT / "outputs" / "v26_scene_text_final" / "DSAVANT"

    def test_every_duplicate_parser_copy_is_patched(self) -> None:
        patched = {}
        for name, spec in PARSER_COPIES.items():
            source = (self.game_dir / name).read_bytes()
            result = patch_parser_copy(name, source)
            self.assertEqual(len(source), len(result), name)
            for offset in spec["find_calls"]:
                self.assertEqual(SCENE_FIND_HELPER, call_target(result, offset, OVERLAY_ORIGIN))
            site = spec["trailing_site"]
            self.assertEqual(trailing_replacement(site), result[site : site + len(ORIGINAL_TRAILING)])
            patched[name] = result
        self.assertTrue(audit_parser_copies(patched)["passed"])

    def test_original_sites_are_exact_and_guarded(self) -> None:
        for name, spec in PARSER_COPIES.items():
            source = (self.game_dir / name).read_bytes()
            site = spec["trailing_site"]
            self.assertEqual(ORIGINAL_TRAILING, source[site : site + len(ORIGINAL_TRAILING)], name)


if __name__ == "__main__":
    unittest.main()
