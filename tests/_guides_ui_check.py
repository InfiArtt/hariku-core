# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build Help, Extension guides... (ui/guides_dialog.py) with real wxPython: the
label comes right before the list, Enter and Open open the selected guide and
the list stays open, Escape closes it, an empty list says so, and the real
list shows this repo's extensions with a guide, in the Hariku language.

Opening a guide is a fake: no browser opens. Speech is captured through
on_before_speak and urlopen is blocked, so nothing leaves the machine and
nothing is spoken.

Run by tests/test_guides_ui.py in a separate process, because conftest.py
mocks wx inside the pytest process. The caller points APPDATA at a temporary
folder. Prints one "OK" line per stage. Never run it on a computer someone is
using: it opens windows.
"""
import faulthandler
import functools
import logging
import os
import sys
import threading
import time

faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the guides check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(90, _watchdog)
_timer.daemon = True
_timer.start()

import urllib.request


def _blocked_urlopen(*args, **kwargs):
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked_urlopen

problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook
threading.excepthook = lambda args: problems.append(
    f"thread {args.thread.name}: {args.exc_type.__name__}: {args.exc_value}")


class _ErrorLog(logging.Handler):
    def emit(self, record):
        if record.name.startswith(("ui.guides_dialog", "core.guides")):
            problems.append(f"logged by {record.name}: {record.getMessage()}")


logging.getLogger().addHandler(_ErrorLog(level=logging.ERROR))

import wx

app = wx.App(False)

import core.api
import core.i18n
core.api.save_data("Core", {"onboarding_completed": True, "language": "en"})
core.i18n.init()
import core.extension_manager as manager
import core.guides
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

# Never a browser: opening a guide is recorded instead.
browsed = []
core.guides._startfile = lambda path: browsed.append(path)
manager.SYSTEM_EXTENSIONS_DIR = os.path.join(ROOT, "extensions")


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


def press(button):
    evt = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
    evt.SetEventObject(button)
    button.GetEventHandler().ProcessEvent(evt)


def key(window, code):
    evt = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    evt.SetKeyCode(code)
    window.GetEventHandler().ProcessEvent(evt)


from ui.guides_dialog import GuidesDialog

frame = wx.Frame(None, title="Guides check")
frame.Show()

# --- The label, the list, the buttons ---------------------------------------------------------
opened = []
dlg = GuidesDialog(frame, guides=[("orbit", "Orbit"), ("weather", "Weather")],
                   opener=lambda ext_id: opened.append(ext_id) or True)
dlg.Show()
pump(lambda: dlg.IsShown(), 2)
assert dlg.GetTitle() == "Extension guides"
children = list(dlg.GetChildren())
index = children.index(dlg.list)
label = children[index - 1]
assert isinstance(label, wx.StaticText) and label.GetLabel() == "Extensions with a guide:", \
    label.GetLabel()
assert index == 0 + 1, "the label must be the first control, right before the list"
assert [dlg.list.GetString(i) for i in range(dlg.list.GetCount())] == ["Orbit", "Weather"]
assert dlg.list.GetSelection() == 0
assert dlg.btn_open.GetLabel() == "&Open" and dlg.btn_open.IsEnabled()
assert dlg.btn_close.GetLabel() == "Close"
assert children.index(dlg.btn_open) > index and children.index(dlg.btn_close) > index
assert dlg.GetEscapeId() == wx.ID_CLOSE
assert pump(lambda: dlg.list.HasFocus(), 3), "the list should have the focus"
print("OK labels")

# --- Enter opens the selected guide; the list stays open -------------------------------------
dlg.list.SetSelection(1)
key(dlg, wx.WXK_RETURN)
assert opened == ["weather"], opened
assert dlg.IsShown() and dlg.list.HasFocus()
key(dlg, wx.WXK_NUMPAD_ENTER)
assert opened == ["weather", "weather"], opened
print("OK enter")

# --- Open does the same; Enter elsewhere is left alone ---------------------------------------
dlg.list.SetSelection(0)
press(dlg.btn_open)
assert opened[-1] == "orbit", opened
dlg.btn_close.SetFocus()
pump(lambda: dlg.btn_close.HasFocus(), 2)
count = len(opened)
key(dlg, wx.WXK_RETURN)
assert len(opened) == count, "Enter on Close must not open a guide"
print("OK open_button")

dlg.Destroy()

# --- An empty list says so ------------------------------------------------------------------
dlg = GuidesDialog(frame, guides=[], opener=lambda ext_id: opened.append(ext_id))
dlg.Show()
pump(lambda: dlg.IsShown(), 2)
children = list(dlg.GetChildren())
label = children[children.index(dlg.list) - 1]
assert label.GetLabel() == "No installed extension has a guide yet.", label.GetLabel()
assert dlg.list.GetCount() == 0 and not dlg.btn_open.IsEnabled()
count = len(opened)
key(dlg, wx.WXK_RETURN)
assert len(opened) == count
dlg.Destroy()
print("OK empty")

# --- The real list: this repo's guides, and a real (fake-browser) open -----------------------
dlg = GuidesDialog(frame)
dlg.Show()
pump(lambda: dlg.IsShown(), 2)
names = [dlg.list.GetString(i) for i in range(dlg.list.GetCount())]
assert len(names) >= 30 and "Orbit" in names and "Weather" in names, names
assert names == sorted(names, key=str.casefold), names
dlg.list.SetSelection(names.index("Orbit"))
press(dlg.btn_open)
assert pump(lambda: browsed, 2), "the guide was never opened"
assert browsed[0].endswith("orbit-en.html") and os.path.isfile(browsed[0]), browsed
with open(browsed[0], encoding="utf-8") as f:
    page = f.read()
assert '<html lang="en">' in page and "<h1>Orbit</h1>" in page and "<h2>" in page
dlg.Destroy()
print("OK real_list")

# --- In Indonesian --------------------------------------------------------------------------
assert core.i18n.use_language("id")
dlg = GuidesDialog(frame)
dlg.Show()
pump(lambda: dlg.IsShown(), 2)
children = list(dlg.GetChildren())
assert children[children.index(dlg.list) - 1].GetLabel() == "Ekstensi yang punya panduan:"
names = [dlg.list.GetString(i) for i in range(dlg.list.GetCount())]
assert "Kalkulator & Konversi" in names and "Keliling Dunia" in names, names
dlg.Destroy()
print("OK indonesian")

pump(lambda: False, 0.3)
assert not problems, problems
assert not spoken, spoken
print("OK no_errors")

frame.Destroy()
pump(lambda: False, 0.3)
print("OK shutdown")
_timer.cancel()
os._exit(0)
