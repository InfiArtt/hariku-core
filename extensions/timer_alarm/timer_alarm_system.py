# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for Timer & Alarm: reading input (to stop a ring at a key press) and
its sounds. No wx here.

Input: GetLastInputInfo (the tick of the last key or mouse input in this
session), GetAsyncKeyState (is a key held) and GetCursorPos (did the mouse
move). All read-only; no keyboard hook is ever installed.

Sounds: Windows' own alarm and ring sounds (%WINDIR%\\Media\\Alarm01.wav to
Alarm10.wav, Ring01.wav to Ring10.wav), which Hariku can't ship, when they are
on this computer; otherwise two tones made by tools/make_timer_alarm_sounds.py
and shipped in sounds/. They play through core.sounds (MCI, without blocking)
and stop with core.sounds.stop_sound.
"""

import ctypes
import ctypes.wintypes
import os

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
TONES = {"alarm": "timer_alarm_alarm.wav", "timer": "timer_alarm_timer.wav"}
WINDOWS_SOUNDS = [f"Alarm{n:02d}.wav" for n in range(1, 11)] + \
                 [f"Ring{n:02d}.wav" for n in range(1, 11)]


# ------------------------------------------------------------
# Input (read-only)
# ------------------------------------------------------------

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]


_user32_dll = None


def _user32():
    global _user32_dll
    if _user32_dll is None:
        dll = ctypes.WinDLL("user32")       # our own instance: argtypes stay private
        dll.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
        dll.GetLastInputInfo.restype = ctypes.wintypes.BOOL
        dll.GetAsyncKeyState.argtypes = [ctypes.c_int]
        dll.GetAsyncKeyState.restype = ctypes.c_short
        dll.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
        dll.GetCursorPos.restype = ctypes.wintypes.BOOL
        _user32_dll = dll
    return _user32_dll


def last_input_tick():
    """GetTickCount() of the last keyboard or mouse input, or None."""
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if _user32().GetLastInputInfo(ctypes.byref(info)):
            return int(info.dwTime)
    except Exception:
        pass
    return None


def key_down():
    """Whether a keyboard key is held right now (mouse buttons excluded)."""
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


# ------------------------------------------------------------
# Sounds
# ------------------------------------------------------------

def media_dir():
    return os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Media")


def tone_path(kind):
    return os.path.join(EXT_DIR, "sounds", TONES.get(kind, TONES["alarm"]))


def available_choices(folder=None):
    """The sound choices on this computer: ("windows:Alarm01.wav", "Alarm", 1)
    ... then ("tone:alarm", "tone", "alarm") and ("tone:timer", ...)."""
    folder = folder or media_dir()
    choices = []
    for name in WINDOWS_SOUNDS:
        if os.path.isfile(os.path.join(folder, name)):
            family = "Alarm" if name.startswith("Alarm") else "Ring"
            choices.append((f"windows:{name}", family, int(name[len(family):-4])))
    choices.append(("tone:alarm", "tone", "alarm"))
    choices.append(("tone:timer", "tone", "timer"))
    return choices


def sound_path(choice, kind, folder=None):
    """The file a sound choice plays; the shipped tone for `kind` when it is a
    Windows sound this computer doesn't have."""
    if isinstance(choice, str) and choice.startswith("windows:"):
        name = choice[len("windows:"):]
        if name in WINDOWS_SOUNDS:
            path = os.path.join(folder or media_dir(), name)
            if os.path.isfile(path):
                return path
    if choice in ("tone:alarm", "tone:timer"):
        return tone_path(choice[len("tone:"):])
    return tone_path(kind)


def play(path):
    """Start a sound without waiting (core.sounds, MCI)."""
    import core.sounds
    return core.sounds.play_sound(path)


def stop(path):
    import core.sounds
    return core.sounds.stop_sound(path)
