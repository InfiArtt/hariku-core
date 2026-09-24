# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What Windows says about input and time, read through ctypes (no wx).

There is no keyboard or mouse hook. GetLastInputInfo returns only the tick
count of the last keyboard or mouse input in the session: never which key,
never which app. Each sample is four cheap calls:

  GetLastInputInfo + GetTickCount    -> seconds since the last input
  GetTickCount64                     -> when the machine booted (wall - uptime)
  QueryUnbiasedInterruptTime         -> seconds the machine has been awake since
                                        boot (sleep and hibernation excluded)

The DLLs are separate WinDLL instances, so the argument and return types set
here never change how Hariku's own ctypes.windll calls behave.
"""

import ctypes
import ctypes.wintypes
import logging
import time

logger = logging.getLogger(__name__)

TICK_WRAP = 1 << 32                  # GetTickCount and dwTime are 32-bit
UNBIASED_UNITS_PER_SECOND = 10_000_000   # QueryUnbiasedInterruptTime counts 100 ns


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]


def idle_ms(tick_now, last_input_tick):
    """Milliseconds since the last input, from two 32-bit tick counts.

    Both counts wrap to 0 every 49.7 days; subtracting modulo 2**32 gives the
    right answer across the wrap. A result in the upper half of the range means
    the input arrived after the tick count was read, so the idle time is 0."""
    diff = (int(tick_now) - int(last_input_tick)) % TICK_WRAP
    return 0 if diff >= TICK_WRAP // 2 else diff


def make_sample(wall, tick64_ms, unbiased_100ns, idle_milliseconds):
    """A sample as the recorder stores it. `awake` is None when Windows could
    not say how long the machine has been awake."""
    wall = float(wall)
    tick = int(tick64_ms)
    return {
        "wall": wall,
        "tick": tick,
        "boot": wall - tick / 1000.0,
        "awake": None if unbiased_100ns is None else unbiased_100ns / UNBIASED_UNITS_PER_SECOND,
        "idle": max(0, int(idle_milliseconds)) / 1000.0,
    }


def _load_dlls():
    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        return None, None
    user32 = win_dll("user32")
    kernel32 = win_dll("kernel32")
    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    user32.GetLastInputInfo.restype = ctypes.wintypes.BOOL
    kernel32.GetTickCount.argtypes = []
    kernel32.GetTickCount.restype = ctypes.wintypes.DWORD
    kernel32.GetTickCount64.argtypes = []
    kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    kernel32.QueryUnbiasedInterruptTime.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
    kernel32.QueryUnbiasedInterruptTime.restype = ctypes.wintypes.BOOL
    return user32, kernel32


class WindowsClock:
    """Reads samples. Tests pass fake `user32` / `kernel32` objects with the
    same four functions, so no logic test depends on the real API."""

    def __init__(self, user32=None, kernel32=None, wall=time.time):
        if user32 is None or kernel32 is None:
            try:
                user32, kernel32 = _load_dlls()
            except (OSError, AttributeError) as e:
                logger.warning(f"[Sleep Pattern] Windows input time unavailable: {e}")
                user32 = kernel32 = None
        self._user32 = user32
        self._kernel32 = kernel32
        self._wall = wall

    @property
    def available(self):
        return self._user32 is not None and self._kernel32 is not None

    def read(self):
        """A sample (see make_sample), or None when Windows can't say."""
        if not self.available:
            return None
        try:
            info = LASTINPUTINFO()
            info.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if not self._user32.GetLastInputInfo(ctypes.byref(info)):
                return None
            # Read the tick after the last input, so it is never older.
            tick32 = self._kernel32.GetTickCount()
            tick64 = self._kernel32.GetTickCount64()
            unbiased = ctypes.c_ulonglong(0)
            ok = self._kernel32.QueryUnbiasedInterruptTime(ctypes.byref(unbiased))
            return make_sample(self._wall(), tick64, unbiased.value if ok else None,
                               idle_ms(tick32, info.dwTime))
        except Exception as e:
            logger.warning(f"[Sleep Pattern] Could not read input time: {e}")
            return None
