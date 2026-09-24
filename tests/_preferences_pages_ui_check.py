# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Real wxPython: Preferences builds a page only once the page list has settled
on it, so arrowing through the list stays quick; the other pages are built in
the background while the keyboard is idle; focus never moves while that
happens, and nothing counts as an unsaved change. Prints one "OK" line per
stage. Run by tests/test_preferences_pages_ui.py with APPDATA pointing at a
temporary folder.
"""
import faulthandler
import functools
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
faulthandler.enable()
print = functools.partial(print, flush=True)

import urllib.request


def _blocked_urlopen(*args, **kwargs):
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked_urlopen

import wx

app = wx.App(False)

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()
import core.api
from core.events import bus


def _silence(payload):
    payload["cancel"] = True


bus.subscribe("on_before_speak", _silence)
core.api.save_data("Core", {"onboarding_completed": True, "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad")})
core.api.prompt_yes_no = lambda *args, **kwargs: False

from ui.main_window import MainWindow
frame = MainWindow(None, title="preferences pages check")
print("OK main_window")

import core.core_panels
core.core_panels.register()


def pump(condition, timeout=5.0):
    loop = wx.GUIEventLoop()
    previous = wx.EventLoop.GetActive()
    wx.EventLoop.SetActive(loop)
    try:
        end = time.time() + timeout
        while True:
            while loop.Pending():
                loop.Dispatch()
            app.ProcessPendingEvents()
            if condition():
                return True
            if time.time() > end:
                return False
            time.sleep(0.02)
    finally:
        wx.EventLoop.SetActive(previous)


import ui.preferences_dialog as pd
# Background building checks the keyboard; on CI nobody types, so it is idle.
prefs = pd.PreferencesDialog(frame)
prefs.Show()
book = prefs.treebook
built = lambda: [p["panel"] is not None for p in prefs.panels]
assert built()[book.GetSelection()], "the first page was not built"
assert sum(built()) == 1, built()
tree = book.GetTreeCtrl()
tree.SetFocus()
pump(lambda: wx.Window.FindFocus() is tree, timeout=1.0)
focus_known = wx.Window.FindFocus() is tree
print("OK opened (first page only)")

# Arrowing through five pages quickly builds none of them.
for index in range(1, 6):
    book.SetSelection(index)           # sends the page-changed event, as arrowing does
assert sum(built()) == 1, built()
assert prefs._settle_timer is not None
# Once the list settles, only the page it stopped on is built.
assert pump(lambda: built()[5], timeout=2.0), built()
assert not any(built()[1:5]), built()
print("OK settled page built")

# Tab straight after arrowing builds the page at once.
book.SetSelection(7)
tab = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
tab.SetKeyCode(wx.WXK_TAB)
tab.SetEventObject(prefs)
prefs.GetEventHandler().ProcessEvent(tab)
assert built()[7], "Tab did not build the page"
print("OK tab builds at once")

# The rest are built in the background while nobody types; focus stays put and
# nothing counts as an unsaved change.
if focus_known:
    tree.SetFocus()
    pump(lambda: wx.Window.FindFocus() is tree, timeout=1.0)
assert pump(lambda: all(p["panel"] is not None or p.get("failed") for p in prefs.panels),
            timeout=30.0), built()
if focus_known:
    assert wx.Window.FindFocus() is tree, "background building moved the focus"
assert not prefs.is_dirty, "building pages counted as an unsaved change"
assert not prefs._realizing
print(f"OK background ({'focus checked' if focus_known else 'focus not observable here'})")

prefs.Destroy()
frame.Destroy()
wx.CallAfter(app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
