from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_dos_v20_ui_complete import MZ_HEADER_SIZE, OVERLAY_ORIGIN, call_target  # noqa: E402
from build_dos_v25_scene_text import SCENE_FIND_HELPER, scene_find_helper_bytes  # noqa: E402
from build_dos_v26_scene_text import TRAILING_ASCII_HELPER, trailing_ascii_helper_bytes  # noqa: E402
from build_dos_v36_local_scene_helpers import (  # noqa: E402
    MAX_ORIGINAL_OVERLAY_SIZE,
    SCENE_USERS,
    V35_HASHES,
)


class LocalSceneHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v35 = ROOT / "outputs" / "v35_security_enter_final" / "DSAVANT"
        cls.v36 = ROOT / "outputs" / "v36_local_scene_helpers_final" / "DSAVANT"

    def test_each_parser_uses_its_appended_private_helpers(self) -> None:
        find = scene_find_helper_bytes()
        trailing = trailing_ascii_helper_bytes()
        for name, spec in SCENE_USERS.items():
            with self.subTest(name=name):
                old = (self.v35 / name).read_bytes()
                new = (self.v36 / name).read_bytes()
                find_target = OVERLAY_ORIGIN + len(old)
                trailing_target = find_target + len(find)
                self.assertEqual(new[len(old) : len(old) + len(find)], find)
                self.assertEqual(new[len(old) + len(find) :], trailing)
                self.assertLessEqual(len(new), MAX_ORIGINAL_OVERLAY_SIZE)
                self.assertLessEqual(OVERLAY_ORIGIN + len(new), 0x10000)
                for offset in spec["find_calls"]:
                    self.assertEqual(call_target(new, offset, OVERLAY_ORIGIN), find_target)
                self.assertEqual(
                    call_target(new, spec["trailing_site"] + 3, OVERLAY_ORIGIN),
                    trailing_target,
                )

    def test_overlay_prefixes_change_only_at_call_operands(self) -> None:
        for name, spec in SCENE_USERS.items():
            old = (self.v35 / name).read_bytes()
            new = (self.v36 / name).read_bytes()[: len(old)]
            changed = {i for i, pair in enumerate(zip(old, new)) if pair[0] != pair[1]}
            allowed: set[int] = set()
            for offset in spec["find_calls"]:
                allowed.update((offset + 1, offset + 2))
            trailing_call = spec["trailing_site"] + 3
            allowed.update((trailing_call + 1, trailing_call + 2))
            self.assertTrue(changed)
            self.assertTrue(changed <= allowed, (name, sorted(changed - allowed)))

    def test_shared_helpers_are_retired_and_only_those_ds_bytes_change(self) -> None:
        old = (self.v35 / "DS.EXE").read_bytes()
        new = (self.v36 / "DS.EXE").read_bytes()
        self.assertEqual(len(old), len(new))
        allowed: set[int] = set()
        for runtime, helper in (
            (SCENE_FIND_HELPER, scene_find_helper_bytes()),
            (TRAILING_ASCII_HELPER, trailing_ascii_helper_bytes()),
        ):
            start = MZ_HEADER_SIZE + runtime
            self.assertEqual(old[start : start + len(helper)], helper)
            self.assertEqual(new[start : start + len(helper)], b"\x00" * len(helper))
            allowed.update(range(start, start + len(helper)))
        changed = {i for i, pair in enumerate(zip(old, new)) if pair[0] != pair[1]}
        self.assertEqual(changed, {i for i in allowed if old[i] != 0})

    def test_every_other_payload_is_byte_identical_to_v35(self) -> None:
        for name in V35_HASHES:
            if name == "DS.EXE" or name in SCENE_USERS:
                continue
            with self.subTest(name=name):
                self.assertEqual((self.v35 / name).read_bytes(), (self.v36 / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
