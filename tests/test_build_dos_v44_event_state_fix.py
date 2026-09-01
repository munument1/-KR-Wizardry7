from __future__ import annotations

import unittest

from tools.build_dos_v44_event_state_fix import (
    ORIGINAL_CALL_BYTES,
    PATCH_OFFSET,
    V43_BYPASS_BYTES,
    patch_vbase,
)


class V44EventStateFixTests(unittest.TestCase):
    def test_patch_restores_only_guarded_three_bytes(self) -> None:
        source = bytearray(b"\xAA" * (PATCH_OFFSET + 16))
        source[PATCH_OFFSET : PATCH_OFFSET + 3] = V43_BYPASS_BYTES
        output = patch_vbase(bytes(source), verify_hash=False)
        self.assertEqual(output[PATCH_OFFSET : PATCH_OFFSET + 3], ORIGINAL_CALL_BYTES)
        self.assertEqual(output[:PATCH_OFFSET], source[:PATCH_OFFSET])
        self.assertEqual(output[PATCH_OFFSET + 3 :], source[PATCH_OFFSET + 3 :])

    def test_patch_rejects_unexpected_site(self) -> None:
        source = b"\xAA" * (PATCH_OFFSET + 16)
        with self.assertRaisesRegex(ValueError, "expected"):
            patch_vbase(source, verify_hash=False)

    def test_patch_preserves_file_size(self) -> None:
        source = bytearray(b"\x00" * (PATCH_OFFSET + 64))
        source[PATCH_OFFSET : PATCH_OFFSET + 3] = V43_BYPASS_BYTES
        output = patch_vbase(bytes(source), verify_hash=False)
        self.assertEqual(len(output), len(source))


if __name__ == "__main__":
    unittest.main()
