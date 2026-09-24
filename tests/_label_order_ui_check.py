# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the real Preferences dialog with the core pages and every bundled
extension's page, and check that each input control on each page comes right
after the label that names it.

Screen readers (through oleacc) name a native control after the static text
created just before it; SetName() does not change what they say. A control
created before its label therefore gets the previous control's label, and
every label after it shifts by one (seen on the Profile page's birthday
boxes). Prints "PROBLEM ..." lines and, when there are none, "OK labels".

Run by tests/test_label_order_ui.py in a separate process with APPDATA
pointing at a temporary folder. The dialog is built but never shown.
"""
import faulthandler
import functools
import logging
import os
import sys
import traceback

# A crash inside wx would otherwise lose everything still buffered.
faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

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

# Close any modal dialog an extension opens while loading, so nothing waits.
def _close_stray_modals():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, wx.Dialog) and w.IsModal():
            print(f"NOTE closed a dialog opened while loading: {w.GetTitle()!r}")
            w.EndModal(wx.ID_CANCEL)


stray_timer = wx.Timer()
stray_timer.Bind(wx.EVT_TIMER, lambda e: _close_stray_modals())
stray_timer.Start(500)

from ui.main_window import MainWindow
frame = MainWindow(None, title="label order check")

import core.core_panels
core.core_panels.register()

import core.extension_manager as em
ext_root = os.path.join(ROOT, "extensions")
for name in sorted(os.listdir(ext_root)):
    path = os.path.join(ext_root, name)
    if name.startswith(".") or not os.path.isfile(os.path.join(path, "manifest.json")):
        continue
    try:
        em.load_unpacked_extension(path)
    except Exception:
        print(f"NOTE {name} did not load:\n{traceback.format_exc()}")
    if name not in em.LOADED_EXTENSIONS:
        print(f"NOTE {name} is not loaded; its page is not checked")

# Controls a screen reader names from a preceding label. Buttons, check boxes
# and radio buttons carry their own text.
NEEDS_LABEL = (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl, wx.ListBox,
               wx.SpinCtrl, wx.Slider, wx.TreeCtrl)
DEFAULT_NAMES = {"text", "choice", "comboBox", "listCtrl", "listBox", "wxSpinCtrl",
                 "wxSpinCtrlDouble", "slider", "treeCtrl", "checkListBox", "panel", ""}


def _plain(text):
    return " ".join(text.replace("&&", "\0").replace("&", "").replace("\0", "&")
                    .strip().rstrip(":").split())


def _is_note(ctrl):
    # A read-only multi-line text shows a note or details; it reads its content.
    return (isinstance(ctrl, wx.TextCtrl) and ctrl.IsMultiLine()
            and not ctrl.IsEditable())


def check(window, page, problems):
    children = [c for c in window.GetChildren() if not isinstance(c, wx.TopLevelWindow)]
    for index, ctrl in enumerate(children):
        if isinstance(ctrl, (wx.FilePickerCtrl, wx.DirPickerCtrl, wx.SpinCtrlDouble)):
            problems.append(f"PROBLEM [{page}] {type(ctrl).__name__} hides an unlabelled text "
                            f"field; use a labelled TextCtrl, SpinCtrl or Choice instead")
            continue
        if isinstance(ctrl, NEEDS_LABEL) and ctrl.IsShown() and not _is_note(ctrl):
            before = children[index - 1] if index else None
            kind = type(ctrl).__name__
            name = ctrl.GetName()
            described = f"{kind} {name!r}" if name not in DEFAULT_NAMES else kind
            if not isinstance(before, wx.StaticText):
                prev = type(before).__name__ if before is not None else "nothing"
                problems.append(f"PROBLEM [{page}] {described} comes after {prev}, not a label")
            elif name not in DEFAULT_NAMES and _plain(before.GetLabel()) != _plain(name):
                problems.append(f"PROBLEM [{page}] {described} comes after the label "
                                f"{_plain(before.GetLabel())!r}")
        if not isinstance(ctrl, (wx.ListCtrl, wx.TreeCtrl)):
            check(ctrl, page, problems)


# How long each page takes to build, to find what makes Preferences slow to open.
import time
import core.preferences
import core.ui_scale
timings = []
for category, items in core.preferences.get_all_panels().items():
    for item in items:
        def timed(parent, _create=item["create"], _name=item["name"] or category):
            start = time.perf_counter()
            try:
                return _create(parent)
            finally:
                timings.append((time.perf_counter() - start, _name))
        item["create"] = timed
_apply_appearance = core.ui_scale.apply_appearance


def _timed_appearance(window):
    start = time.perf_counter()
    try:
        return _apply_appearance(window)
    finally:
        timings.append((time.perf_counter() - start, f"apply_appearance({type(window).__name__})"))


core.ui_scale.apply_appearance = _timed_appearance
import ui.preferences_dialog as _pd
_pd.core.ui_scale.apply_appearance = _timed_appearance
_InputGestures = _pd.InputGesturesPanel


def _timed_input(parent):
    start = time.perf_counter()
    try:
        return _InputGestures(parent)
    finally:
        timings.append((time.perf_counter() - start, "Input Gestures"))


_pd.InputGesturesPanel = _timed_input

from ui.preferences_dialog import PreferencesDialog
problems = []
start = time.perf_counter()
prefs = PreferencesDialog(frame)
print(f"TIMING opening Preferences (first page only) {1000 * (time.perf_counter() - start):.0f} ms")
start = time.perf_counter()
prefs.realize_all()
print(f"TIMING building every other page {1000 * (time.perf_counter() - start):.0f} ms")
for seconds, name in sorted(timings, reverse=True):
    print(f"TIMING {1000 * seconds:7.1f} ms  {name}")
book = prefs.treebook
for i in range(book.GetPageCount()):
    check(book.GetPage(i), book.GetPageText(i), problems)
print(f"checked {book.GetPageCount()} pages")
for line in problems:
    print(line)
if not problems:
    print("OK labels")

stray_timer.Stop()
print("closing")
prefs.Destroy()
em.unload_all_extensions()
print("extensions unloaded")
frame.Destroy()
wx.CallAfter(app.ExitMainLoop)
app.MainLoop()
sys.exit(1 if problems else 0)
