#!/usr/bin/env python3
"""Capture the main window rectangle of a process for local visual QA."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
from pathlib import Path

from PIL import ImageGrab


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd: int, _lparam: int) -> bool:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == args.pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        raise RuntimeError(f"no visible window for PID {args.pid}")
    hwnd = found[0]
    rect = ctypes.wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    image = ImageGrab.grab((rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(args.output.resolve())
    print(rect.left, rect.top, rect.right, rect.bottom)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
