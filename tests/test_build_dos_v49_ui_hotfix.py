from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_dos_v49_ui_hotfix as v49


def synthetic_vtrea() -> bytes:
    data = bytearray(b"\x90" * 0x9000)
    for offset in v49.VARIABLE_CENTER_SITES:
        data[offset:offset + 3] = v49.near_call(v49.STRLEN_TARGET, v49.OVERLAY_ORIGIN + offset)
        data[offset + 3:offset + 16] = bytes.fromhex(
            "59 8B C8 8B 46 0C 2B C1 B9 06 00 F7 E9"
        )
    for offset in v49.HALF_WIDTH_SITES:
        data[offset:offset + 3] = v49.near_call(v49.STRLEN_TARGET, v49.OVERLAY_ORIGIN + offset)
        data[offset + 3:offset + 9] = bytes.fromhex("59 B9 06 00 F7 E9")
    offset = v49.LOGICAL_SITE_MUST_REMAIN
    data[offset:offset + 3] = v49.near_call(v49.STRLEN_TARGET, v49.OVERLAY_ORIGIN + offset)
    return bytes(data)


def test_patch_vtrea_retargets_only_display_width_math() -> None:
    source = synthetic_vtrea()
    patched, report = v49.patch_vtrea(source)

    assert len(report) == 4
    assert len(patched) == len(source)
    assert v49.call_target(patched, v49.LOGICAL_SITE_MUST_REMAIN) == v49.STRLEN_TARGET

    for offset in v49.VARIABLE_CENTER_SITES:
        assert v49.call_target(patched, offset) == v49.WIDTH_ADAPTER
        assert patched[offset + 3:offset + 16] == bytes.fromhex(
            "59 8B C8 6B 46 0C 06 2B C1 90 90 90 90"
        )

    for offset in v49.HALF_WIDTH_SITES:
        assert v49.call_target(patched, offset) == v49.WIDTH_ADAPTER
        assert patched[offset + 3:offset + 9] == bytes.fromhex("59 90 90 90 90 90")


def test_near_call_wraps_like_16_bit_dos_code() -> None:
    # Upper-half overlay call sites must wrap their target in the 16-bit code
    # segment; this is the audit bug that hid these VTREA helpers previously.
    data = bytearray(b"\x90" * 0x9000)
    offset = 0x8C46
    data[offset:offset + 3] = v49.near_call(v49.STRLEN_TARGET, v49.OVERLAY_ORIGIN + offset)
    assert v49.call_target(bytes(data), offset) == v49.STRLEN_TARGET
