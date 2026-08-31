from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from audit_dos_scene_parser_controls import (  # noqa: E402
    ALL_PARSER_TOKENS,
    CONTROL_DISPATCH,
    audit,
)


class SceneParserControlAuditTests(unittest.TestCase):
    def test_live_equivalent_v26_passes_every_control_path(self) -> None:
        game_dir = ROOT / "outputs" / "v26_scene_text_final" / "DSAVANT"
        report = audit(game_dir)
        self.assertTrue(report["passed"], report["failures"])
        self.assertTrue(all(report["checks"].values()))

    def test_parser_table_has_no_alphabetic_controls_and_every_token_collides(self) -> None:
        self.assertEqual(b"!%&]@#|", CONTROL_DISPATCH)
        self.assertFalse(any(chr(value).isalpha() for value in ALL_PARSER_TOKENS))
        game_dir = ROOT / "outputs" / "v26_scene_text_final" / "DSAVANT"
        report = audit(game_dir)
        self.assertTrue(
            all(item["glyph_payload_occurrences"] > 0 for item in report["tokens"].values())
        )


if __name__ == "__main__":
    unittest.main()
