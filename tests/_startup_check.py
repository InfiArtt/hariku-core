# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the real main window, save General settings, and open the Routines
dialogs through their hotkey actions, using real wxPython.

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

# Load Routines through the real loader and run its hotkey actions, which open
# modal dialogs. A timer closes each dialog so the check doesn't block.
import core.extension_manager as em
em.load_unpacked_extension(os.path.join(ROOT, "extensions", "routines"))
assert "routines" in em.LOADED_EXTENSIONS, "Routines extension did not load"


def _run_and_close(action_id, label):
    opened = []

    def close_modal():
        for w in wx.GetTopLevelWindows():
            if isinstance(w, wx.Dialog) and w.IsModal():
                opened.append(type(w).__name__)
                w.EndModal(wx.ID_CANCEL)

    wx.CallLater(1500, close_modal)
    core.hotkeys.actions[action_id].callback()
    assert opened, f"{action_id} did not open a dialog"
    print(f"OK {label} ({opened[0]})")


_run_and_close("Routines.manage_routines", "routines_manage_dialog")
_run_and_close("Routines.view_routines_log", "routines_log_dialog")

# Browsing the Type list with arrow keys fires EVT_CHOICE on every step. Each
# step must rebuild the settings for that type without taking focus away.
routines_ui = sys.modules["routines_ui"]
focus_checked = True
for kind in ("condition", "action"):
    dlg = routines_ui.ItemDialog(frame, kind)
    dlg.Show()
    dlg.choice.SetFocus()
    wx.Yield()
    can_observe_focus = wx.Window.FindFocus() is dlg.choice
    focus_checked = focus_checked and can_observe_focus
    for i in range(dlg.choice.GetCount()):
        dlg.choice.SetSelection(i)
        evt = wx.CommandEvent(wx.EVT_CHOICE.typeId, dlg.choice.GetId())
        evt.SetEventObject(dlg.choice)
        dlg.choice.GetEventHandler().ProcessEvent(evt)
        wx.Yield()
        name = dlg.choice.GetString(i)
        assert dlg._settings_box.GetLabel() == f"Settings for {name}", name
        if can_observe_focus:
            assert wx.Window.FindFocus() is dlg.choice, f"focus left the Type list at {name}"
    dlg.Destroy()
print(f"OK routines_type_browse (focus {'checked' if focus_checked else 'not observable here'})")

# "Insert placeholder…" in the action editor: enabled only for types with a
# text field, lists the profile, and puts the chosen token at the caret of the
# text field last focused, then returns focus there. The popup menu is replaced
# by one that picks an entry, so no real menu opens.
import core.personal
core.personal.set_profile("Rafli", "Bro", [("kantor", "Jl. Sudirman 1")])
engine = routines_ui.engine
dlg = routines_ui.ItemDialog(frame, "action",
                             existing={"type": "notification",
                                       "params": {"title": "Hi", "message": "Hello "}},
                             variables=["greeting"])
dlg.Show()
wx.Yield()
assert dlg.btn_insert is not None and dlg.btn_insert.IsEnabled()
labels = dict(dlg.placeholder_entries())
assert labels["%myname%"] == "%myname%: your name (Rafli)", labels
assert labels["%mynickname%"] == "%mynickname%: what Hariku calls you (Bro)", labels
assert "%kantor%" in labels and "%time%" in labels and "%var:greeting%" in labels, labels

menus = []


def _pick(token_label):
    def show(menu):
        items = menu.GetMenuItems()
        menus.append([item.GetItemLabelText() for item in items])
        for item in items:
            if item.GetItemLabelText().startswith(token_label):
                evt = wx.CommandEvent(wx.EVT_MENU.typeId, item.GetId())
                evt.SetEventObject(menu)
                menu.ProcessEvent(evt)
                return
        raise AssertionError(f"no menu entry for {token_label}")
    return show


def _press(button):
    evt = wx.CommandEvent(wx.EVT_BUTTON.typeId, button.GetId())
    evt.SetEventObject(button)
    button.GetEventHandler().ProcessEvent(evt)
    wx.Yield()


title_ctrl = dlg._field_ctrls["title"][0]
message_ctrl = dlg._field_ctrls["message"][0]
message_ctrl.SetFocus()
wx.Yield()
message_ctrl.SetInsertionPointEnd()
if wx.Window.FindFocus() is not message_ctrl:
    dlg._last_text_key = "message"   # focus can't be observed here; as if it were
dlg._show_menu = _pick("%myname%:")
_press(dlg.btn_insert)
assert menus and menus[-1][0] == "%myname%: your name (Rafli)", menus
assert message_ctrl.GetValue() == "Hello %myname%", message_ctrl.GetValue()
assert title_ctrl.GetValue() == "Hi", title_ctrl.GetValue()
assert message_ctrl.GetInsertionPoint() == len("Hello %myname%")
insert_focus = wx.Window.FindFocus() is message_ctrl

dlg._show_menu = _pick("%time%:")
_press(dlg.btn_insert)
assert message_ctrl.GetValue() == "Hello %myname%%time%", message_ctrl.GetValue()

# A type without text fields disables the button; focus stays on the Type list.
dlg.choice.SetFocus()
wx.Yield()
lock = [t for t, _label in engine.ACTION_LABELS].index("lock_screen")
dlg.choice.SetSelection(lock)
evt = wx.CommandEvent(wx.EVT_CHOICE.typeId, dlg.choice.GetId())
evt.SetEventObject(dlg.choice)
dlg.choice.GetEventHandler().ProcessEvent(evt)
wx.Yield()
assert not dlg.btn_insert.IsEnabled()
assert dlg.target_text_field() is None
item = dlg.get_item()
assert item["type"] == "lock_screen", item
dlg.Destroy()

# Conditions have no placeholders, so no button.
dlg = routines_ui.ItemDialog(frame, "condition")
assert dlg.btn_insert is None
dlg.Destroy()
print(f"OK routines_insert_placeholder (focus {'checked' if insert_focus else 'not observable here'})")

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
