# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
"Press any key to skip the flight", without a keyboard hook: like Hariku
Voice's "stop when I press a key" (core/voice.py), the last input time
(GetLastInputInfo) is compared with the time the flight began. The key that
started the trip (its release, or a key still held down) and plain mouse
movement don't count. No wx.
"""

import ctypes
import ctypes.wintypes
import time

GRACE_SECONDS = 0.8         # input right after the flight begins (the Enter being released)
HELD_GRACE_SECONDS = 3.0    # a key still held down from starting the trip
MOUSE_MOVE_SECONDS = 0.3    # input this soon after the pointer moved is the mouse


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]


_user32_dll = None


def _user32():
    global _user32_dll
    if _user32_dll is None:
        dll = ctypes.WinDLL("user32")      # our own instance: argtypes stay private
        dll.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
        dll.GetLastInputInfo.restype = ctypes.wintypes.BOOL
        dll.GetAsyncKeyState.argtypes = [ctypes.c_int]
        dll.GetAsyncKeyState.restype = ctypes.c_short
        dll.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
        dll.GetCursorPos.restype = ctypes.wintypes.BOOL
        _user32_dll = dll
    return _user32_dll


def last_input_tick():
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if _user32().GetLastInputInfo(ctypes.byref(info)):
            return info.dwTime
    except Exception:
        pass
    return None


def any_key_down():
    try:
        state = _user32().GetAsyncKeyState
        return any(state(vk) & 0x8000 for vk in range(0x08, 0xFF))
    except Exception:
        return False


def cursor_pos():
    try:
        point = ctypes.wintypes.POINT()
        if _user32().GetCursorPos(ctypes.byref(point)):
            return (point.x, point.y)
    except Exception:
        pass
    return None


class KeyWatch:
    """pressed() is True once a key was pressed after the watch began."""

    def __init__(self, last_input=last_input_tick, keys_down=any_key_down, cursor=cursor_pos,
                 clock=time.monotonic):
        self._last_input = last_input
        self._keys_down = keys_down
        self._cursor = cursor
        self._clock = clock
        self._start = clock()
        self._baseline = last_input()
        self._position = cursor()
        self._moved_at = float("-inf")

    def pressed(self):
        now = self._clock()
        position = self._cursor()
        if position != self._position:
            self._position = position
            self._moved_at = now
        tick = self._last_input()
        if tick is None or tick == self._baseline:
            return False
        elapsed = now - self._start
        held = self._keys_down()
        if elapsed < GRACE_SECONDS or (held and elapsed < HELD_GRACE_SECONDS):
            self._baseline = tick
            return False
        if not held and now - self._moved_at < MOUSE_MOVE_SECONDS:
            self._baseline = tick
            return False
        return True
