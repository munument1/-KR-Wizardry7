from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from audit_dos_korean_boundaries import audit  # noqa: E402


class KoreanBoundaryAuditTests(unittest.TestCase):
    def test_v30_save_compatible_release_passes(self) -> None:
        audit_dir = ROOT / "outputs" / "v30_save_compat_final" / "DSAVANT"
        report = audit(
            audit_dir,
            ROOT / "outputs" / "dos_translation" / "messages.csv",
            Path(r"D:\Wizardry 7.zip"),
        )
        self.assertTrue(report["passed"], report)
        self.assertEqual(0, report["issue_count"])
        self.assertEqual(11019, report["valid_custom_streams"])
        self.assertEqual([], report["source_mismatch_ids"])


if __name__ == "__main__":
    unittest.main()
