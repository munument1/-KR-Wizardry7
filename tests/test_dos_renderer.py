from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from patch_dos_korean_renderer import (  # noqa: E402
    Assembler16,
    CAVE_START,
    emit_renderer,
)


class DosRendererAssemblyTests(unittest.TestCase):
    def test_string_hook_preserves_driver_clobbered_state(self) -> None:
        asm = Assembler16(CAVE_START)
        emit_renderer(asm, alphabet_size=121, glyph_count=1110)
        asm.label("rank_table")
        asm.data.extend(bytes(256))
        asm.label("glyph_table")
        payload = asm.finish()

        # Original wrapper contract: establish ES=DS and preserve all registers
        # added by the decoder (SI/BX/CX/DX/DS/ES).
        self.assertTrue(
            payload.startswith(
                bytes.fromhex("55 89 E5 FC 56 53 51 52 1E 06 8C D8 8E C0")
            )
        )
        # SI must survive the far video-driver wrapper call for the next byte.
        draw = asm.labels["draw_character"] - CAVE_START
        self.assertEqual(0x56, payload[draw])
        self.assertIn(bytes.fromhex("83 C4 04 5E"), payload[draw:draw + 16])

        done = asm.labels["string_done"] - CAVE_START
        self.assertEqual(
            bytes.fromhex("30 C0 07 1F 5A 59 5B 5E 89 EC 5D C3"),
            payload[done:done + 12],
        )


if __name__ == "__main__":
    unittest.main()
