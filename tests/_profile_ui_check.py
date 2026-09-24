# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Open Preferences with real wxPython, go to the Profile page, type a name and a
nickname, choose a birthday (an impossible one is refused), turn the startup
greeting off, add, edit and remove placeholders through the real dialog
(including its spoken validation), browse the lists checking focus stays put,
set quiet hours on their own page, press OK and check what was saved.

Speech is captured through on_before_speak instead of reaching the screen
reader. Run by tests/test_profile_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder so the user's real settings are never touched. Prints one "OK"
line per stage.
"""
import logging
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# Nothing here needs the network; any attempt fails and is remembered.
import urllib.request

network_attempts = []


def _blocked_urlopen(*args, **kwargs):
    network_attempts.append(args[0] if args else kwargs)
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked_urlopen

# Exceptions in wx event handlers are printed, not raised; collect them.
problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    WATCHED = ("core.core_panels", "core.personal", "core.events", "core.preferences",
               "ui.preferences_dialog")

    def emit(self, record):
        if record.name.startswith(self.WATCHED):
            problems.append(f"logged by {record.name}: {record.getMessage()}")


logging.getLogger().addHandler(_ErrorLog(level=logging.ERROR))

import wx

app = wx.App(False)

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()
import core.api
import core.personal
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

# "User" is what the first-run wizard saved for a blank name before 2.7. The
# scratchpad folder matches the Extensions page's default, so pressing OK
# doesn't ask to restart.
core.api.save_data("Core", {"user_name": "User", "onboarding_completed": True,
                            "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad")})


def _unexpected_prompt(*args, **kwargs):
    problems.append(f"unexpected Yes/No prompt: {args}")
    return False


core.api.prompt_yes_no = _unexpected_prompt

from ui.main_window import MainWindow
frame = MainWindow(None, title="profile check")
print("OK main_window")

import core.core_panels
core.core_panels.register()
_ = core.i18n.get_translator("core")


def pump(condition, timeout=5.0):
    """Process events until condition() is true or the timeout passes. Runs an
    event loop of its own: wx.Yield() alone never delivers timer events here."""
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


def fire(ctrl, event_type):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    ctrl.GetEventHandler().ProcessEvent(evt)
    wx.Yield()


def open_field_dialog(button, steps, timeout_ms=15000):
    """Press `button`, which opens the modal placeholder dialog, and run each of
    `steps(dialog)` from a timer while it is open. A step that fails, or a
    dialog left open, is recorded and the dialog is cancelled."""
    def find_dialog():
        for w in wx.GetTopLevelWindows():
            if isinstance(w, core.core_panels.ProfileFieldDialog) and w.IsModal():
                return w
        return None

    def run(i):
        dlg = find_dialog()
        if dlg is None:
            problems.append(f"the placeholder dialog was not open for step {i + 1}")
            return
        try:
            steps[i](dlg)
        except Exception:
            problems.append(f"step {i + 1} failed:\n{traceback.format_exc()}")
            dlg.EndModal(wx.ID_CANCEL)
            return
        if i + 1 < len(steps):
            wx.CallLater(300, run, i + 1)

    def rescue():
        dlg = find_dialog()
        if dlg is not None:
            problems.append("the placeholder dialog was left open")
            dlg.EndModal(wx.ID_CANCEL)

    wx.CallLater(400, run, 0)
    guard = wx.CallLater(timeout_ms, rescue)
    fire(button, wx.EVT_BUTTON)
    guard.Stop()


def plain(label):
    return label.replace("\n", " ")


def rows(panel):
    lst = panel.list_fields
    return [(lst.GetItemText(i, 0), lst.GetItemText(i, 1)) for i in range(lst.GetItemCount())]


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


def browse_choice(ctrl):
    """Select every item and fire EVT_CHOICE, as arrow keys do; focus must stay.
    Returns whether focus could be observed here."""
    ctrl.SetFocus()
    pump(lambda: wx.Window.FindFocus() is ctrl, timeout=1.0)
    observable = wx.Window.FindFocus() is ctrl
    for i in range(ctrl.GetCount()):
        ctrl.SetSelection(i)
        evt = wx.CommandEvent(wx.EVT_CHOICE.typeId, ctrl.GetId())
        evt.SetEventObject(ctrl)
        evt.SetInt(i)
        ctrl.GetEventHandler().ProcessEvent(evt)
        wx.Yield()
        if observable:
            assert wx.Window.FindFocus() is ctrl, f"focus left {ctrl.GetName()} at item {i}"
    return observable


from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Profile")
pages = [prefs.treebook.GetPageText(i) for i in range(prefs.treebook.GetPageCount())]
assert "General" in pages and pages[pages.index("General") + 1] == "Profile", pages
assert pages[pages.index("Profile") + 1] == "Quiet Hours", pages
assert pages[prefs.treebook.GetSelection()] == "Profile", pages
panel = core.core_panels._profile_panel_instance
assert panel is not None, "the Profile page was not created"
print("OK profile_page")

state = {"focus": True}


def interact():
    """Everything a user does on the page, run inside the modal Preferences."""
    # The legacy "User" means no name; the labels name every control.
    assert panel.IsShown(), "the Profile page is not showing"
    assert panel.txt_name.GetValue() == "" and panel.txt_nickname.GetValue() == ""
    assert panel.txt_name.GetName() == "Your name"
    assert panel.txt_nickname.GetName() == "What should Hariku call you? (optional)"
    assert panel.list_fields.GetName() == "Your own placeholders"
    assert rows(panel) == []

    panel.txt_name.SetFocus()
    panel.txt_name.SetValue("Rafli")
    panel.txt_nickname.SetValue("Bro")

    # Birthday: named day and month choices and an optional year field.
    assert panel.choice_day.GetName() == "Birthday, day"
    assert panel.choice_month.GetName() == "Birthday, month"
    assert panel.txt_year.GetName() == "Birthday, year (optional)"
    assert panel.choice_day.GetSelection() == 0 and panel.choice_month.GetSelection() == 0
    assert panel.choice_day.GetString(0) == _("profile_not_set") and panel.choice_day.GetCount() == 32
    assert panel.choice_month.GetString(9) == "September" and panel.choice_month.GetCount() == 13
    assert panel.ValidateChanges() is None                    # no birthday is fine
    state["focus"] = browse_choice(panel.choice_month) and state["focus"]
    state["focus"] = browse_choice(panel.choice_day) and state["focus"]
    # An impossible or half-filled birthday is refused before anything is saved.
    panel.choice_day.SetSelection(31)
    panel.choice_month.SetSelection(4)
    message, ctrl = panel.ValidateChanges()
    assert message == _("profile_err_birthday_invalid") and ctrl is panel.choice_day, message
    panel.choice_month.SetSelection(0)
    message, ctrl = panel.ValidateChanges()
    assert message == _("profile_err_birthday_incomplete") and ctrl is panel.choice_month, message
    panel.choice_day.SetSelection(24)
    panel.choice_month.SetSelection(9)
    panel.txt_year.SetValue("19x9")
    message, ctrl = panel.ValidateChanges()
    assert ctrl is panel.txt_year, message
    panel.txt_year.SetValue("1999")
    assert panel.ValidateChanges() is None

    # The startup greeting is on by default; this user turns it off.
    assert panel.chk_greet.GetName() == "Greet me when Hariku starts"
    assert panel.chk_greet.GetValue() is True
    panel.chk_greet.SetValue(False)

    # Add: a reserved name is refused (shown and spoken), then a good one.
    reserved = _("profile_err_key_reserved", token="time")

    def add_bad(dlg):
        assert dlg.GetTitle() == _("profile_dlg_add_title")
        assert dlg.GetEscapeId() == wx.ID_CANCEL
        assert dlg.GetDefaultItem().GetId() == wx.ID_OK
        assert dlg.txt_key.GetName().startswith("Placeholder name")
        assert dlg.txt_value.GetName() == "Value"
        dlg.txt_key.SetValue("time")
        dlg.txt_value.SetValue("x")
        fire(dlg.btn_ok, wx.EVT_BUTTON)

    def add_good(dlg):
        assert dlg.IsModal(), "the dialog closed on a reserved name"
        assert plain(dlg.lbl_error.GetLabel()) == reserved, dlg.lbl_error.GetLabel()
        assert reserved in spoken, spoken
        dlg.txt_key.SetValue("%Kantor%")
        dlg.txt_value.SetValue("Jl. Sudirman 1")
        fire(dlg.btn_ok, wx.EVT_BUTTON)

    open_field_dialog(panel.btn_add, [add_bad, add_good])
    assert rows(panel) == [("%kantor%", "Jl. Sudirman 1")], rows(panel)
    assert panel.selected_index() == 0
    focus_seen = wx.Window.FindFocus()
    if focus_seen is not None and focus_seen.GetTopLevelParent() is prefs:
        assert focus_seen is panel.list_fields, "focus did not return to the list after Add"
    else:
        state["focus"] = False
    assert pump(lambda: _("profile_added", token="kantor") in spoken), spoken
    assert prefs.is_dirty, "adding a placeholder did not mark Preferences as changed"

    def add_second(dlg):
        dlg.txt_key.SetValue("hp")
        dlg.txt_value.SetValue("0812")
        fire(dlg.btn_ok, wx.EVT_BUTTON)

    open_field_dialog(panel.btn_add, [add_second])
    assert rows(panel) == [("%kantor%", "Jl. Sudirman 1"), ("%hp%", "0812")], rows(panel)

    # Arrow through the list: selecting a row never moves focus.
    lst = panel.list_fields
    lst.SetFocus()
    pump(lambda: wx.Window.FindFocus() is lst, timeout=1.0)
    observable = wx.Window.FindFocus() is lst
    state["focus"] = state["focus"] and observable
    selected = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    for i in list(range(lst.GetItemCount())) + [0]:
        lst.SetItemState(i, selected, selected)
        pump(lambda: False, timeout=0.1)
        assert panel.selected_index() == i
        if observable:
            assert wx.Window.FindFocus() is lst, f"focus left the list at row {i}"

    # Edit the first row: a duplicate name is refused, then it is renamed.
    duplicate = _("profile_err_key_duplicate", token="hp")

    def edit_bad(dlg):
        assert dlg.GetTitle() == _("profile_dlg_edit_title")
        assert dlg.txt_key.GetValue() == "kantor" and dlg.txt_value.GetValue() == "Jl. Sudirman 1"
        dlg.txt_key.SetValue("HP")
        fire(dlg.btn_ok, wx.EVT_BUTTON)

    def edit_good(dlg):
        assert plain(dlg.lbl_error.GetLabel()) == duplicate, dlg.lbl_error.GetLabel()
        assert duplicate in spoken, spoken
        dlg.txt_key.SetValue("kantor_baru")
        dlg.txt_value.SetValue("Jl. Thamrin 2")
        fire(dlg.btn_ok, wx.EVT_BUTTON)

    open_field_dialog(panel.btn_edit, [edit_bad, edit_good])
    assert rows(panel) == [("%kantor_baru%", "Jl. Thamrin 2"), ("%hp%", "0812")], rows(panel)
    assert panel.selected_index() == 0
    assert pump(lambda: _("profile_changed", token="kantor_baru") in spoken), spoken

    # Cancel changes nothing.
    open_field_dialog(panel.btn_edit, [lambda dlg: dlg.EndModal(wx.ID_CANCEL)])
    assert rows(panel) == [("%kantor_baru%", "Jl. Thamrin 2"), ("%hp%", "0812")], rows(panel)

    # Remove the second row; focus goes back to the list.
    lst.SetItemState(1, selected, selected)
    fire(panel.btn_remove, wx.EVT_BUTTON)
    assert rows(panel) == [("%kantor_baru%", "Jl. Thamrin 2")], rows(panel)
    assert panel.selected_index() == 0
    if state["focus"]:
        assert wx.Window.FindFocus() is lst, "focus did not return to the list after Remove"
    assert pump(lambda: _("profile_removed", token="hp") in spoken), spoken

    # Nothing is saved before OK.
    assert core.personal.get_name() == ""
    assert core.personal.get_birthday() is None
    print(f"OK profile_edit ({focus_note(state['focus'])})")

    # --- Quiet Hours, a page of its own -------------------------------------
    quiet = core.core_panels._quiet_panel_instance
    assert quiet is not None, "the Quiet Hours page was not created"
    assert quiet.chk_enabled.GetName() == "Turn on quiet hours"
    assert quiet.chk_enabled.GetValue() is False                # off by default
    assert quiet.choice_start.GetName() == "Quiet hours start at"
    assert quiet.choice_end.GetName() == "Quiet hours end at"
    assert quiet.choice_start.GetStringSelection() == "22:00"
    assert quiet.choice_end.GetStringSelection() == "05:00"
    quiet_focus = browse_choice(quiet.choice_end)
    quiet.chk_enabled.SetValue(True)
    quiet.choice_start.SetSelection(quiet._times.index("22:00"))
    quiet.choice_end.SetSelection(quiet._times.index("22:00"))
    message, ctrl = quiet.ValidateChanges()
    assert message == _("profile_err_quiet_same") and ctrl is quiet.choice_end, message
    quiet.choice_end.SetSelection(quiet._times.index("06:30"))
    assert quiet.ValidateChanges() is None
    assert not core.personal.is_quiet_time()                     # not saved yet
    print(f"OK quiet_hours ({focus_note(quiet_focus)})")

    fire(prefs.btn_ok, wx.EVT_BUTTON)   # OK applies every page and closes


def run_interaction():
    try:
        interact()
    except Exception:
        problems.append(f"the Profile page check failed:\n{traceback.format_exc()}")
        prefs.EndModal(wx.ID_CANCEL)


def rescue_prefs():
    if prefs.IsModal():
        problems.append("Preferences was left open")
        prefs.EndModal(wx.ID_CANCEL)


wx.CallLater(500, run_interaction)
prefs_guard = wx.CallLater(90000, rescue_prefs)
result = prefs.ShowModal()
prefs_guard.Stop()
prefs.Destroy()
wx.Yield()
assert not problems, "\n".join(problems)
assert result == wx.ID_OK, result

# --- What OK saved ------------------------------------------------------------
saved = core.api.load_data("Core")
assert saved["user_name"] == "Rafli" and saved["user_nickname"] == "Bro", saved
assert saved["user_fields"] == [{"key": "kantor_baru", "value": "Jl. Thamrin 2"}], saved
assert saved["onboarding_completed"] is True, saved
assert saved["user_birthday"] == {"day": 24, "month": 9, "year": 1999}, saved
assert saved["greet_on_startup"] is False, saved
assert saved["quiet_hours"] == {"enabled": True, "start": "22:00", "end": "06:30"}, saved
assert core.personal.get_nickname() == "Bro"
assert core.personal.expand("%mybirthday%") == "24 September 1999"
assert core.personal.startup_greeting_enabled() is False
assert core.personal.expand("%MYNICKNAME% @ %kantor_baru%, 100%") == "Bro @ Jl. Thamrin 2, 100%"
print("OK profile_saved")

# --- Opening Preferences again shows the saved profile ------------------------
prefs = PreferencesDialog(frame, select_tab="Profile")
prefs.Show()
wx.Yield()
panel = core.core_panels._profile_panel_instance
assert panel.txt_name.GetValue() == "Rafli" and panel.txt_nickname.GetValue() == "Bro"
assert rows(panel) == [("%kantor_baru%", "Jl. Thamrin 2")], rows(panel)
assert panel.choice_day.GetSelection() == 24 and panel.choice_month.GetSelection() == 9
assert panel.txt_year.GetValue() == "1999" and panel.chk_greet.GetValue() is False
quiet = core.core_panels._quiet_panel_instance
assert quiet.chk_enabled.GetValue() is True
assert quiet.choice_end.GetStringSelection() == "06:30"
prefs.Destroy()
wx.Yield()
print("OK profile_reopen")

assert not network_attempts, f"real network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
