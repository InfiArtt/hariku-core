# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Action runners for Routines. Each runner takes (params, ctx, variables) and
# performs a side effect. Register a new action here + add its ACTION_SPECS entry
# in engine.py. Text params support placeholders via engine.process_placeholders.
# Every runner is wrapped by runtime._run_actions in try/except, so a failure is
# logged (and shown in the log viewer), never crashing the app.
import logging
import os
import shlex
import subprocess
import time
import webbrowser

import core.api
from core.speech import speak

import routines_engine as engine

logger = logging.getLogger(__name__)


def _expand(text, ctx, variables):
    return engine.process_placeholders(text, ctx, variables)


def _hidden_startupinfo():
    """A STARTUPINFO that hides any console window a launched process might pop."""
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    except Exception:
        return None


def _a_tts(p, ctx, variables):
    speak(_expand(p.get("text", ""), ctx, variables), interrupt=False)


def _a_notification(p, ctx, variables):
    core.api.show_toast(_expand(p.get("title", "Routine"), ctx, variables),
                        _expand(p.get("message", ""), ctx, variables))


def _a_open_url(p, ctx, variables):
    url = _expand(p.get("url", ""), ctx, variables).strip()
    if url.startswith("http://") or url.startswith("https://"):
        webbrowser.open(url)
    else:
        logger.warning(f"[Routines] refusing to open non-http URL: {url!r}")


def _a_play_sound(p, ctx, variables):
    import core.sounds
    core.sounds.play_internal_sound(_expand(p.get("sound", "move.wav"), ctx, variables))


def _a_set_variable(p, ctx, variables):
    name = (p.get("name") or "").strip()
    if name:
        variables[name] = _expand(p.get("value", ""), ctx, variables)


def _a_delay(p, ctx, variables):
    try:
        time.sleep(min(max(0, float(p.get("seconds", 1))), 60))
    except (TypeError, ValueError):
        pass


def _a_open_app(p, ctx, variables):
    """Launch a program or run a shell-style command line (user's own machine).
    Placeholders are expanded first, then Windows variables such as %TEMP%. NOT arbitrary piped shell — the string is
    split into argv and executed directly, with os.startfile as a fallback for
    plain paths and URIs (e.g. spotify:)."""
    cmd = os.path.expandvars(_expand(p.get("path", ""), ctx, variables)).strip()
    if not cmd:
        return
    try:
        subprocess.Popen(shlex.split(cmd), startupinfo=_hidden_startupinfo())
        logger.info(f"[Routines] launched: {cmd!r}")
    except FileNotFoundError:
        os.startfile(cmd)  # noqa: S606 - user-provided path/URI on their own PC
        logger.info(f"[Routines] opened via startfile: {cmd!r}")


def _a_open_file(p, ctx, variables):
    """Open a file with its default handler. Placeholders, then Windows
    variables such as %USERPROFILE%, are expanded first."""
    path = os.path.expandvars(_expand(p.get("path", ""), ctx, variables)).strip()
    if not path:
        return
    os.startfile(path)  # noqa: S606 - user-selected file on their own PC
    logger.info(f"[Routines] opened file: {path!r}")


def _a_lock_screen(p, ctx, variables):
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    logger.info("[Routines] locked the workstation.")


def _a_set_volume(p, ctx, variables):
    """Set the system master volume to 0-100."""
    try:
        level = int(p.get("level", 50))
    except (TypeError, ValueError):
        return
    level = max(0, min(100, level))
    try:
        import core.sounds
        if hasattr(core.sounds, "set_global_volume"):
            core.sounds.set_global_volume(level)
            return
        if hasattr(core.sounds, "apply_system_volume"):
            core.sounds.apply_system_volume(level)
            return
    except Exception as e:
        logger.warning(f"[Routines] core.sounds volume failed, using ctypes: {e}")
    import ctypes
    word = int((level / 100.0) * 0xFFFF)
    packed = (word & 0xFFFF) | ((word & 0xFFFF) << 16)
    ctypes.windll.winmm.waveOutSetVolume(0, packed)


def _a_copy_to_clipboard(p, ctx, variables):
    text = _expand(p.get("text", ""), ctx, variables)
    core.api.set_clipboard(text)


def _a_type_text(p, ctx, variables):
    """Type a string into whatever field currently has focus, using the Win32
    SendInput API with Unicode key events (no third-party dependency). '\\n' is
    sent as Enter. This is user-driven automation of their own keyboard."""
    text = _expand(p.get("text", ""), ctx, variables)
    if not text:
        return
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = wintypes.WPARAM
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    VK_RETURN = 0x0D

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR))

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR))

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD))

    class _IUNION(ctypes.Union):
        _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))

    class INPUT(ctypes.Structure):
        _fields_ = (("type", wintypes.DWORD), ("u", _IUNION))

    send = ctypes.windll.user32.SendInput
    size = ctypes.sizeof(INPUT)

    def _emit(events):
        arr = (INPUT * len(events))(*events)
        send(len(events), arr, size)

    def _unicode_events(code_unit):
        down = INPUT(type=INPUT_KEYBOARD,
                     u=_IUNION(ki=KEYBDINPUT(0, code_unit, KEYEVENTF_UNICODE, 0, 0)))
        up = INPUT(type=INPUT_KEYBOARD,
                   u=_IUNION(ki=KEYBDINPUT(0, code_unit,
                                           KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)))
        return [down, up]

    def _vk_events(vk):
        down = INPUT(type=INPUT_KEYBOARD, u=_IUNION(ki=KEYBDINPUT(vk, 0, 0, 0, 0)))
        up = INPUT(type=INPUT_KEYBOARD,
                   u=_IUNION(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)))
        return [down, up]

    time.sleep(0.15)  # let focus settle before typing
    for ch in text.replace("\r\n", "\n").replace("\r", "\n"):
        if ch == "\n":
            _emit(_vk_events(VK_RETURN))
            continue
        # Encode as UTF-16-LE so astral chars (emoji) send as surrogate pairs.
        for unit in _utf16_units(ch):
            _emit(_unicode_events(unit))
    logger.info(f"[Routines] typed {len(text)} chars into the focused field.")


def _utf16_units(ch):
    """Split a single character into its UTF-16-LE code units (usually one,
    two for astral-plane characters like emoji)."""
    data = ch.encode("utf-16-le")
    return [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]


# --- Hariku-native actions (deep app integration, iOS-Shortcuts style) --------

def _a_add_reminder(p, ctx, variables):
    """Create a Hariku reminder. Date/time blank => today / 09:00."""
    import core.reminders
    title = _expand(p.get("title", ""), ctx, variables).strip()
    if not title:
        return
    date = _expand(p.get("date", ""), ctx, variables).strip() or ctx.get("date", "")
    tm = _expand(p.get("time", ""), ctx, variables).strip() or "09:00"
    core.reminders.add_reminder(title, date, tm)
    logger.info(f"[Routines] added reminder {title!r} on {date} {tm}")


def _a_goto_date(p, ctx, variables):
    """Move the calendar selection to a date (blank => today)."""
    date = _expand(p.get("date", ""), ctx, variables).strip() or ctx.get("date", "")
    if date:
        core.api.set_selected_date(date)


def _a_speak_agenda(p, ctx, variables):
    """Speak the reminders for a day (blank => today), with the profile's
    %placeholders% in their titles filled in."""
    import core.personal
    import core.reminders
    date = _expand(p.get("date", ""), ctx, variables).strip() or ctx.get("date", "")
    items = core.reminders.get_reminders_for_date(date) or []
    if not items:
        speak(f"No reminders for {date}.", interrupt=True)
        return
    parts = [(f"{r.get('time', '')} {core.personal.expand(r.get('title', ''))}").strip()
             for r in items]
    speak(f"{len(items)} reminders. " + ". ".join(parts), interrupt=True)


def _a_run_routine(p, ctx, variables):
    """Run another routine's actions by name (chaining, like iOS 'Run Shortcut').
    Runs inline with a depth guard so routines that reference each other can't
    loop forever."""
    name = _expand(p.get("name", ""), ctx, variables).strip().lower()
    if not name:
        return
    depth = int(variables.get("_routine_depth", 0) or 0)
    if depth >= 5:
        logger.warning("[Routines] run_routine depth limit reached; stopping to avoid a loop.")
        return
    import routines_runtime as runtime
    target = next((r for r in runtime.load_routines()
                   if (r.get("name", "").strip().lower() == name)), None)
    if not target:
        logger.warning(f"[Routines] run_routine: no routine named {name!r}")
        return
    child_vars = dict(variables)
    child_vars["_routine_depth"] = depth + 1
    for action in target.get("actions", []):
        fn = ACTION_RUNNERS.get(action.get("type"))
        if not fn:
            continue
        try:
            fn(action.get("params", {}), ctx, child_vars)
        except Exception as e:
            logger.error(f"[Routines] chained action '{action.get('type')}' failed: {e}")


ACTION_RUNNERS = {
    "tts": _a_tts,
    "notification": _a_notification,
    "open_url": _a_open_url,
    "play_sound": _a_play_sound,
    "set_variable": _a_set_variable,
    "delay": _a_delay,
    "open_app": _a_open_app,
    "open_file": _a_open_file,
    "lock_screen": _a_lock_screen,
    "set_volume": _a_set_volume,
    "copy_to_clipboard": _a_copy_to_clipboard,
    "type_text": _a_type_text,
    "add_reminder": _a_add_reminder,
    "goto_date": _a_goto_date,
    "speak_agenda": _a_speak_agenda,
    "run_routine": _a_run_routine,
}
