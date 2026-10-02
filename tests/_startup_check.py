# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the real main window, save General settings, check that Preferences
honours them, and schedule the startup greeting, using real wxPython. (The
Routines extension's dialogs are checked with the official extensions.)

Run by tests/test_startup.py in a separate process, because conftest.py mocks
wx inside the pytest process. The caller points APPDATA at a temporary folder so
the user's real settings are never touched. Prints one "OK" line per stage.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import wx

app = wx.App(False)

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()

from ui.main_window import MainWindow
frame = MainWindow(None, title="startup check")
print("OK main_window")

import core.core_panels
panel = core.core_panels.GeneralSettingsPanel(frame)
panel.chk_high_contrast.SetValue(True)
panel.choice_scale.SetSelection(panel._scale_keys.index("large"))
panel.ApplyChanges()
print("OK apply_settings")


def _descendants(win):
    for child in win.GetChildren():
        yield child
        yield from _descendants(child)


# Preferences must honour the large text + high contrast just saved, on every
# page including extension panels (it used to apply neither).
from ui.preferences_dialog import PreferencesDialog
prefs = PreferencesDialog(frame)
prefs.realize_all()   # pages are built when first shown
texts = [w for w in _descendants(prefs) if isinstance(w, wx.StaticText)]
assert texts, "no text found in Preferences"
for w in texts:
    base = getattr(w, "_hariku_base_pt", None)
    assert base is not None, f"Preferences text {w.GetLabel()!r} was not scaled"
    assert w.GetFont().GetPointSize() == max(6, int(round(base * 1.25))), w.GetLabel()
    assert w.GetBackgroundColour() == wx.Colour(0, 0, 0), w.GetLabel()
prefs.Destroy()
print("OK preferences_appearance")

# The profile the startup greeting below uses.
import core.personal
core.personal.set_profile("Rafli", "Bro", [("kantor", "Jl. Sudirman 1")])

# Hariku's startup greeting, scheduled the way hariku.py does once the window
# is shown: the call returns at once, focus doesn't move, and the greeting and
# the welcome come as one announcement. Speech is captured, not spoken.
import time
from core.events import bus

greetings = []


def _capture_speech(payload):
    greetings.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)
focus_before = wx.Window.FindFocus()
started = time.monotonic()
wx.CallLater(core.personal.STARTUP_GREETING_DELAY_MS,
             core.personal.speak_startup_greeting, "Welcome to Hariku version 2.7.0")
assert time.monotonic() - started < 0.5, "scheduling the greeting held up startup"
loop = wx.GUIEventLoop()
previous_loop = wx.EventLoop.GetActive()
wx.EventLoop.SetActive(loop)
end = time.monotonic() + core.personal.STARTUP_GREETING_DELAY_MS / 1000 + 5
while not greetings and time.monotonic() < end:
    while loop.Pending():
        loop.Dispatch()
    app.ProcessPendingEvents()
    time.sleep(0.02)
wx.EventLoop.SetActive(previous_loop)
bus.unsubscribe("on_before_speak", _capture_speech)
assert len(greetings) == 1, greetings
assert greetings[0].startswith("Good ") and ", Bro. " in greetings[0], greetings
assert greetings[0].endswith("Welcome to Hariku version 2.7.0."), greetings
assert wx.Window.FindFocus() is focus_before, "the greeting moved focus"
print("OK startup_greeting")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
