from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v20_ui_complete import MZ_HEADER_SIZE, OVERLAY_ORIGIN, call_target  # noqa: E402
from build_dos_v25_scene_text import SCENE_FIND_HELPER, scene_find_helper_bytes  # noqa: E402
from build_dos_v26_scene_text import TRAILING_ASCII_HELPER, trailing_ascii_helper_bytes  # noqa: E402
from build_dos_v37_fixed_scene_helpers import (  # noqa: E402
    RELOCATED_FIND_HELPER,
    RELOCATED_TRAILING_HELPER,
    SAFE_CAVE_END,
    SAFE_CAVE_START,
    SCENE_USERS,
    V35_HASHES,
    VMAZE_RUNTIME_END,
)


class FixedSceneHelperRelocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v35 = ROOT / "outputs" / "v35_security_enter_final" / "DSAVANT"
        cls.v37 = ROOT / "outputs" / "v37_fixed_scene_helpers_final" / "DSAVANT"

    def test_no_payload_size_changes(self) -> None:
        for name in V35_HASHES:
            with self.subTest(name=name):
                self.assertEqual((self.v35 / name).stat().st_size, (self.v37 / name).stat().st_size)

    def test_helpers_are_beyond_vmaze_and_inside_verified_cave(self) -> None:
        find = scene_find_helper_bytes()
        trailing = trailing_ascii_helper_bytes()
        self.assertGreaterEqual(RELOCATED_FIND_HELPER, VMAZE_RUNTIME_END)
        self.assertGreaterEqual(RELOCATED_FIND_HELPER, SAFE_CAVE_START)
        self.assertLessEqual(RELOCATED_FIND_HELPER + len(find), SAFE_CAVE_END)
        self.assertGreaterEqual(RELOCATED_TRAILING_HELPER, SAFE_CAVE_START)
        self.assertLessEqual(RELOCATED_TRAILING_HELPER + len(trailing), SAFE_CAVE_END)

    def test_ds_moves_only_the_two_helpers(self) -> None:
        old = (self.v35 / "DS.EXE").read_bytes()
        new = (self.v37 / "DS.EXE").read_bytes()
        allowed: set[int] = set()
        for runtime, helper, expected in (
            (SCENE_FIND_HELPER, scene_find_helper_bytes(), b"\x00"),
            (TRAILING_ASCII_HELPER, trailing_ascii_helper_bytes(), b"\x00"),
            (RELOCATED_FIND_HELPER, scene_find_helper_bytes(), None),
            (RELOCATED_TRAILING_HELPER, trailing_ascii_helper_bytes(), None),
        ):
            start = MZ_HEADER_SIZE + runtime
            if expected is not None:
                self.assertEqual(new[start : start + len(helper)], expected * len(helper))
            else:
                self.assertEqual(old[start : start + len(helper)], b"\x00" * len(helper))
                self.assertEqual(new[start : start + len(helper)], helper)
            allowed.update(range(start, start + len(helper)))
        changed = {i for i, pair in enumerate(zip(old, new)) if pair[0] != pair[1]}
        self.assertEqual(changed, {i for i in allowed if old[i] != new[i]})

    def test_every_scene_call_targets_relocated_helpers(self) -> None:
        for name, spec in SCENE_USERS.items():
            with self.subTest(name=name):
                data = (self.v37 / name).read_bytes()
                for offset in spec["find_calls"]:
                    self.assertEqual(call_target(data, offset, OVERLAY_ORIGIN), RELOCATED_FIND_HELPER)
                self.assertEqual(
                    call_target(data, spec["trailing_site"] + 3, OVERLAY_ORIGIN),
                    RELOCATED_TRAILING_HELPER,
                )

    def test_unrelated_payloads_match_v35(self) -> None:
        for name in V35_HASHES:
            if name == "DS.EXE" or name in SCENE_USERS:
                continue
            with self.subTest(name=name):
                self.assertEqual((self.v35 / name).read_bytes(), (self.v37 / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
