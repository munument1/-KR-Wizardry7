from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v35_security_enter import (  # noqa: E402
    SECURITY_COMPARE_PATCH,
    V31_HASHES,
    V35_VBASE_HASH,
)


class SecurityEnterPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v31 = ROOT / "outputs" / "v31_copy_protection_final" / "DSAVANT"
        cls.v35 = ROOT / "outputs" / "v35_security_enter_final" / "DSAVANT"

    def test_patch_is_same_size_and_guarded(self) -> None:
        patch = SECURITY_COMPARE_PATCH
        self.assertEqual(len(patch.expected), len(patch.replacement))
        source = (self.v31 / "VBASE.OVR").read_bytes()
        self.assertEqual(
            patch.expected,
            source[patch.offset : patch.offset + len(patch.expected)],
        )

    def test_v35_changes_only_security_verifier_call(self) -> None:
        source = (self.v31 / "VBASE.OVR").read_bytes()
        result = (self.v35 / "VBASE.OVR").read_bytes()
        patch = SECURITY_COMPARE_PATCH
        self.assertEqual(len(source), len(result))
        self.assertEqual(source[: patch.offset], result[: patch.offset])
        self.assertEqual(
            patch.replacement,
            result[patch.offset : patch.offset + len(patch.replacement)],
        )
        end = patch.offset + len(patch.expected)
        self.assertEqual(source[end:], result[end:])
        self.assertEqual(V35_VBASE_HASH, hashlib.sha256(result).hexdigest())

    def test_all_other_payloads_match_v31(self) -> None:
        for name in V31_HASHES:
            if name == "VBASE.OVR":
                continue
            with self.subTest(name=name):
                self.assertEqual((self.v31 / name).read_bytes(), (self.v35 / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
