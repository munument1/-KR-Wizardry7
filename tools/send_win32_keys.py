#!/usr/bin/env python3
"""Send keyboard-only Win32 input to a process window for local runtime QA."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import time


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

VK = {
    "ENTER": 0x0D,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "TAB": 0x09,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "NUM2": 0x62,
    "NUM4": 0x64,
    "NUM6": 0x66,
    "NUM8": 0x68,
    "NUMLOCK": 0x90,
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUT_UNION(ctypes.Union):
    _fields_ = (
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", INPUT_UNION))


def find_window(pid: int) -> int:
    user32 = ctypes.windll.user32
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid and user32.IsWindowVisible(hwnd):
            matches.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    if not matches:
        raise RuntimeError(f"no visible window for PID {pid}")
    return matches[0]


def send_key(vk: int) -> None:
    user32 = ctypes.windll.user32
    scan = user32.MapVirtualKeyW(vk, 0)
    extended = KEYEVENTF_EXTENDEDKEY if vk in {0x25, 0x26, 0x27, 0x28} else 0
    down = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | extended, 0, 0),
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            0,
            scan,
            KEYEVENTF_SCANCODE | extended | KEYEVENTF_KEYUP,
            0,
            0,
        ),
    )
    events = (INPUT * 2)(down, up)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    if user32.SendInput(2, events, ctypes.sizeof(INPUT)) != 2:
        raise ctypes.WinError()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("keys", nargs="+", help="ENTER ESC SPACE or arrow keys")
    parser.add_argument("--delay-ms", type=int, default=150)
    args = parser.parse_args()

    hwnd = find_window(args.pid)
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 5)
    # Windows can report zero here even when the target already owns focus.
    # SendInput below is the authoritative success check.
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    for name in args.keys:
        try:
            vk = VK[name.upper()]
        except KeyError as exc:
            raise ValueError(f"unsupported key: {name}") from exc
        send_key(vk)
        time.sleep(max(0, args.delay_ms) / 1000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
