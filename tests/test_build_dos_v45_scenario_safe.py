from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_dos_v45_scenario_safe.py"
spec = importlib.util.spec_from_file_location("v45", MODULE_PATH)
v45 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(v45)


class V45ScenarioSafeTests(unittest.TestCase):
    def test_verified_runtime_asset_hashes_are_pinned(self) -> None:
        self.assertEqual(
            v45.V45_SCENARIO_SHA256,
            "8ff513e0469dd12b8b175c7a99b43029eba5b04f70b7794627cc644e1fe34875",
        )
        self.assertEqual(
            v45.V45_VBFONT_SHA256,
            "f7d31cb5afe492840d75eec8eafc87975867601772cc2290d08ffc77185aaa2f",
        )
        self.assertEqual(
            v45.V45_CODEBOOK_SHA256,
            "376d10c1031f1bc7ee125905b72675f14cfae604caa1dacbaf2001b732bce477",
        )

    def test_v44_event_state_fix_is_required_base(self) -> None:
        self.assertEqual(
            v45.V44_VBASE_SHA256,
            "99fa1b3188cfb3585061ddbe34f136b57939b98250daacb4cec8146cd54db464",
        )

    def test_hash_guard_rejects_wrong_data(self) -> None:
        with self.assertRaises(ValueError):
            v45.require_hash("bad", b"x", "0" * 64)


if __name__ == "__main__":
    unittest.main()
