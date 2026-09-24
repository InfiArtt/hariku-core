# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the real main window with real wxPython, press the quick reminder's key
(N) the way the main window passes keys on, type sentences into it, and press
Enter, Save, Escape, Cancel and Edit. Then the reminder dialog: its
"Or type it in one sentence" field with Fill in, the How often field, saving
a monthly reminder, and a date it must refuse. Then Preferences, Reminders.
Checks what is spoken, what is saved to the reminders file, the labels, the
menu, and that focus stays where it is.

The keybindings file starts with the binding the Hariku Assistant extension
saved ("Assistant.quick_reminder": N), so N reaching the core's quick reminder
also checks that it is moved over.

Speech is captured through on_before_speak instead of reaching the screen
reader, message boxes are recorded instead of shown, and urlopen is blocked.

Run by tests/test_quick_reminder_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder so the user's real reminders and settings are never touched.
Prints one "OK" line per stage.
"""
import datetime
import faulthandler
import functools
import json
import logging
import os
import sys
import time
import traceback

# A crash inside wx would otherwise lose everything still buffered.
faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import urllib.request

network_attempts = []


def _blocked_urlopen(*args, **kwargs):
    network_attempts.append(args[0] if args else kwargs)
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked_urlopen

# The binding Hariku Assistant saved, before the quick reminder was in the core.
N_BINDING = {"keycode": ord("N"), "ctrl": False, "shift": False, "alt": False, "win": False,
             "global": False}
_settings = os.path.join(os.environ["APPDATA"], "Hariku2", "settings")
os.makedirs(_settings, exist_ok=True)
with open(os.path.join(_settings, "keybindings.json"), "w", encoding="utf-8") as f:
    json.dump({"Assistant.quick_reminder": [N_BINDING]}, f)

# Exceptions in wx event handlers are printed, not raised; collect them.
problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    WATCHED = ("core.quick_reminder", "core.when", "core.events", "core.hotkeys",
               "core.reminders", "core.core_panels", "ui.quick_reminder_dialog",
               "ui.reminder_dialog", "ui.preferences_dialog", "ui.main_window")

    def emit(self, record):
        if record.name.startswith(self.WATCHED):
            problems.append(f"logged by {record.name}: {record.getMessage()}")


logging.getLogger().addHandler(_ErrorLog(level=logging.ERROR))

import wx

app = wx.App(False)

# Message boxes are recorded, not shown: a native one would wait for a click.
message_boxes = []


def _record_message_box(message, *args, **kwargs):
    message_boxes.append(message)
    return wx.OK


wx.MessageBox = _record_message_box

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()
assert "Assistant.quick_reminder" not in core.hotkeys.saved_config, core.hotkeys.saved_config
assert core.hotkeys.saved_config.get("Hariku Core.quick_reminder") == [N_BINDING], \
    core.hotkeys.saved_config
import core.api
import core.quick_reminder as quick
import core.reminders
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

from ui.main_window import MainWindow
frame = MainWindow(None, title="quick reminder check")
# Minute ticks and the system monitor are not part of this check.
frame.heartbeat_timer.Stop()
frame.monitor_timer.Stop()
import core.core_panels
core.core_panels.register()
print("OK main_window")

import ui.quick_reminder_dialog as qr_ui
from ui.reminder_dialog import AddReminderDialog
_ = quick._

action = core.hotkeys.actions["Hariku Core.quick_reminder"]
assert action.default_keycode == ord("N"), action.default_keycode
assert not (action.default_ctrl or action.default_shift or action.default_alt
            or action.default_win or action.default_global)
assert action.description == "Quick reminder", action.description
assert core.hotkeys.get_current_bindings("Hariku Core.quick_reminder") == \
    [(ord("N"), False, False, False, False, False)]

NOW = datetime.datetime(2026, 9, 24, 10, 40)      # a Thursday
quick._now = lambda: NOW
print("OK action")

# --- The Reminders menu shows the key, and follows it when it moves -------------------------
menubar = frame.GetMenuBar()
titles = [menubar.GetMenuLabelText(i) for i in range(menubar.GetMenuCount())]
assert "Reminders" in titles, titles
assert frame.item_quick_reminder.GetItemLabelText() == "Quick reminder... (N)", \
    frame.item_quick_reminder.GetItemLabelText()
assert frame.item_add_reminder.GetItemLabelText() == "Add reminder... (Enter)"
assert "\t" not in frame.item_quick_reminder.GetItemLabel(), "not a menu accelerator"
saved_bindings = json.loads(json.dumps(core.hotkeys.saved_config))
moved = dict(saved_bindings)
moved["Hariku Core.quick_reminder"] = [dict(N_BINDING, ctrl=True)]
core.hotkeys.apply_new_config(moved)
frame.UpdateReminderMenu()
assert frame.item_quick_reminder.GetItemLabelText() == "Quick reminder... (Ctrl + N)", \
    frame.item_quick_reminder.GetItemLabelText()
assert not core.hotkeys.process_key_event(ord("N"), False, False, False, False)
core.hotkeys.apply_new_config(saved_bindings)
frame.UpdateReminderMenu()
assert frame.item_quick_reminder.GetItemLabelText() == "Quick reminder... (N)"
print("OK menu")


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


def modal(cls):
    for w in wx.GetTopLevelWindows():
        if isinstance(w, cls) and w.IsModal():
            return w
    return None


def fire(ctrl, event_type):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    ctrl.GetEventHandler().ProcessEvent(evt)


def type_text(dlg, text):
    dlg.txt_input.SetValue(text)          # sends EVT_TEXT, as typing does


def press_enter(dlg):
    fire(dlg.txt_input, wx.EVT_TEXT_ENTER)


def press_escape(dlg):
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_ESCAPE)
    key.SetEventObject(dlg)
    dlg.GetEventHandler().ProcessEvent(key)


def _close_stray_dialogs(state):
    for w in wx.GetTopLevelWindows():
        if isinstance(w, wx.Dialog) and w.IsModal():
            state["forced"] = True
            w.EndModal(wx.ID_CANCEL)


def run_modal(start, cls, script, guard_ms=8000):
    """Call start(), which opens a `cls` dialog modally; `script(dlg,
    focus_checked)` runs inside its modal loop. A guard closes whatever is
    still open and fails the stage."""
    state = {"error": None, "forced": False, "ran": False}

    def step():
        dlg = modal(cls)
        if dlg is None:
            state["error"] = f"{cls.__name__} did not open"
            return
        state["ran"] = True
        # Where each dialog starts: the sentence (quick reminder), the title (full).
        start_field = getattr(dlg, "txt_input", None) or getattr(dlg, "txt_title", None)
        observable = start_field is not None and wx.Window.FindFocus() is start_field
        try:
            script(dlg, observable)
        except Exception:
            state["error"] = traceback.format_exc()
            if dlg and dlg.IsModal():
                dlg.EndModal(wx.ID_CANCEL)

    first = wx.CallLater(300, step)
    last = wx.CallLater(guard_ms, _close_stray_dialogs, state)
    result = start()
    first.Stop()
    last.Stop()
    assert state["ran"] or state["error"], "the script never ran"
    assert state["error"] is None, state["error"]
    assert not state["forced"], "a dialog was left open"
    return result


def run_quick_reminder(script, guard_ms=8000):
    """Press N, as the main window passes it on."""
    handled = run_modal(
        lambda: core.hotkeys.process_key_event(ord("N"), False, False, False, False),
        qr_ui.QuickReminderDialog, script, guard_ms)
    assert handled, "N did not reach the quick reminder"


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


def reminders():
    return core.reminders.load_reminders()


BENCHMARK = "ingatkan aku minum obat besok jam 8 pagi, ulangi tiap hari"

# --- The windows' labels: each field right after the label that names it ----------------
NEEDS_LABEL = (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl, wx.ListBox, wx.SpinCtrl)


def _plain(text):
    return " ".join(text.replace("&&", "\0").replace("&", "").replace("\0", "&")
                    .strip().rstrip(":").split())


def check_labels(dlg):
    children = list(dlg.GetChildren())
    for index, ctrl in enumerate(children):
        assert not isinstance(ctrl, (wx.FilePickerCtrl, wx.DirPickerCtrl, wx.SpinCtrlDouble))
        if isinstance(ctrl, NEEDS_LABEL):
            label = children[index - 1]
            assert isinstance(label, wx.StaticText), f"{ctrl.GetName()!r} has no label before it"
            assert _plain(label.GetLabel()) == _plain(ctrl.GetName()), \
                (label.GetLabel(), ctrl.GetName())
    return [type(c).__name__ for c in children]


dlg = qr_ui.QuickReminderDialog(frame)
kinds = check_labels(dlg)
assert kinds == ["StaticText", "TextCtrl", "StaticText", "TextCtrl", "Button", "Button",
                 "Button"], kinds
assert dlg.txt_input.GetName().startswith("What should I remind you about, and when?")
assert "take medicine tomorrow at 8 am, every day" in dlg.txt_input.GetName()
assert dlg.txt_readback.GetName() == "What I understood"
assert dlg.txt_readback.IsMultiLine() and not dlg.txt_readback.IsEditable()
assert dlg.txt_readback.GetValue() == _("qr_readback_hint")
assert dlg.GetEscapeId() == wx.ID_CANCEL
assert dlg.btn_cancel.GetId() == wx.ID_CANCEL
dlg.Destroy()

dlg = AddReminderDialog(frame, "2026-10-05")
kinds = check_labels(dlg)
assert kinds == ["StaticText", "TextCtrl", "Button", "StaticText", "TextCtrl", "StaticText",
                 "TextCtrl", "StaticText", "TextCtrl", "StaticText", "Choice", "StaticText",
                 "Choice", "Button", "Button"], kinds
assert dlg.txt_sentence.GetName() == "Or type it in one sentence"
assert dlg.btn_fill.GetLabelText() == "Fill in"
assert dlg.txt_date.GetValue() == "2026-10-05"
assert dlg.txt_time.GetValue() == "10:41"
assert dlg.choice_recur.GetSelection() == 0
assert dlg.choice_interval.GetName() == "How often"
assert dlg.choice_interval.GetString(1) == "every 2 days"
assert dlg.choice_interval.GetCount() == 30
assert not dlg.choice_interval.IsEnabled(), "How often is only there for a repeat"
assert dlg.GetEscapeId() == wx.ID_CANCEL
dlg.Destroy()
print("OK labels")

# --- N from the main window, then type, Enter, hear, Save ---------------------------------
checks = []


def read_back_then_save(dlg, observable):
    checks.append(observable)
    type_text(dlg, BENCHMARK)
    spoken.clear()
    press_enter(dlg)
    expected = "Minum obat, Friday 25 September 2026, at 08:00, every day. Save?"
    assert spoken == [expected], spoken
    assert dlg.txt_readback.GetValue() == expected
    assert dlg.GetDefaultItem() is dlg.btn_save, "Save is not the default after a read-back"
    if observable:
        assert wx.Window.FindFocus() is dlg.txt_input, "focus left the text field"
    assert reminders() == [], "saved before Save was pressed"
    fire(dlg.btn_save, wx.EVT_BUTTON)


run_quick_reminder(read_back_then_save)
saved = reminders()
assert len(saved) == 1, saved
r = saved[0]
assert (r["title"], r["date"], r["time"], r["recurrence"], r["interval"]) == \
    ("Minum obat", "2026-09-25", "08:00", "daily", 1), r
assert spoken[-1] == "Reminder saved.", spoken
print(f"OK readback_and_save ({focus_note(checks[-1])})")

# --- Enter twice on the same text saves --------------------------------------------------


def enter_twice(dlg, observable):
    checks.append(observable)
    type_text(dlg, "telepon ibu 30 menit lagi")
    spoken.clear()
    press_enter(dlg)
    assert spoken == ["Telepon ibu, Thursday 24 September 2026, at 11:10. Save?"], spoken
    assert len(reminders()) == 1
    press_enter(dlg)


run_quick_reminder(enter_twice)
saved = reminders()
assert len(saved) == 2 and (saved[1]["title"], saved[1]["date"], saved[1]["time"]) == \
    ("Telepon ibu", "2026-09-24", "11:10"), saved
assert spoken[-1] == "Reminder saved."
print(f"OK enter_twice ({focus_note(checks[-1])})")

# --- Escape and Cancel save nothing ----------------------------------------------------------


def escape_after_read_back(dlg, observable):
    type_text(dlg, "rapat besok jam 3")
    press_enter(dlg)
    assert spoken[-1] == "Rapat, Friday 25 September 2026, at 15:00. Save?", spoken
    press_escape(dlg)


def cancel_button(dlg, observable):
    type_text(dlg, "rapat besok jam 3")
    press_enter(dlg)
    fire(dlg.btn_cancel, wx.EVT_BUTTON)


run_quick_reminder(escape_after_read_back)
run_quick_reminder(cancel_button)
assert len(reminders()) == 2, reminders()
print("OK cancel")

# --- Save checks the text as it is now before saving -----------------------------------------


def save_reads_back_first(dlg, observable):
    checks.append(observable)
    type_text(dlg, "rapat besok jam 3")
    spoken.clear()
    fire(dlg.btn_save, wx.EVT_BUTTON)                 # no Enter yet: read back, don't save
    assert spoken == ["Rapat, Friday 25 September 2026, at 15:00. Save?"], spoken
    assert dlg.IsModal() and len(reminders()) == 2
    type_text(dlg, "rapat besok jam 4 sore")          # changed after the read-back
    assert dlg.txt_readback.GetValue() == _("qr_readback_hint")
    fire(dlg.btn_save, wx.EVT_BUTTON)
    assert spoken[-1] == "Rapat, Friday 25 September 2026, at 16:00. Save?", spoken
    assert dlg.IsModal() and len(reminders()) == 2
    if observable:
        assert wx.Window.FindFocus() is dlg.txt_input, "focus moved"
    fire(dlg.btn_save, wx.EVT_BUTTON)


run_quick_reminder(save_reads_back_first)
saved = reminders()
assert len(saved) == 3 and saved[2]["time"] == "16:00", saved
print(f"OK save_checks_first ({focus_note(checks[-1])})")

# --- Nothing recognised: say so, suggest the full dialog, save nothing ----------------------


def nothing_found(dlg, observable):
    type_text(dlg, "minum obat")
    spoken.clear()
    press_enter(dlg)
    assert spoken == [_("qr_rb_nothing_found")], spoken
    assert "full reminder dialog" in spoken[0]
    fire(dlg.btn_save, wx.EVT_BUTTON)
    assert dlg.IsModal(), "closed without anything to save"
    press_enter(dlg)
    assert dlg.IsModal()
    type_text(dlg, "")
    press_enter(dlg)
    assert spoken[-1] == _("qr_empty_input"), spoken
    press_escape(dlg)


run_quick_reminder(nothing_found)
assert len(reminders()) == 3
print("OK nothing_found")

# --- In Indonesian ------------------------------------------------------------------------------
core.i18n._current_language = "id"


def indonesian(dlg, observable):
    assert dlg.GetTitle() == "Pengingat cepat", dlg.GetTitle()
    assert dlg.txt_input.GetName().startswith("Ingatkan tentang apa, dan kapan?")
    type_text(dlg, BENCHMARK)
    spoken.clear()
    press_enter(dlg)
    assert spoken == ["Minum obat, Jumat 25 September 2026, jam 08:00, setiap hari. Simpan?"], \
        spoken
    fire(dlg.btn_save, wx.EVT_BUTTON)


run_quick_reminder(indonesian)
assert len(reminders()) == 4 and spoken[-1] == "Pengingat disimpan.", spoken
core.i18n._current_language = "en"
print("OK indonesian")

# --- Edit in the full reminder dialog: everything carried over ---------------------------------
full = {}


def inspect_full_dialog(save=False):
    dlg = modal(AddReminderDialog)
    if dlg is None:
        full["error"] = "the full reminder dialog did not open"
        return
    focused = wx.Window.FindFocus()
    full.update(date=dlg.txt_date.GetValue(), title=dlg.txt_title.GetValue(),
                time=dlg.txt_time.GetValue(), repeat=dlg.choice_recur.GetSelection(),
                every=dlg.choice_interval.GetStringSelection(),
                every_on=dlg.choice_interval.IsEnabled(),
                # Only checked when the focus is observable inside the dialog.
                focus_checked=focused is not None and wx.GetTopLevelParent(focused) is dlg,
                title_focused=focused is dlg.txt_title)
    if save:
        fire(dlg.btn_ok, wx.EVT_BUTTON)
    else:
        dlg.EndModal(wx.ID_CANCEL)


def edit_with(text, enter_first, save=False):
    def script(dlg, observable):
        type_text(dlg, text)
        if enter_first:
            press_enter(dlg)
        wx.CallLater(500, inspect_full_dialog, save)
        fire(dlg.btn_edit, wx.EVT_BUTTON)
    full.clear()
    run_quick_reminder(script)
    assert pump(lambda: bool(full)), "the full reminder dialog was never checked"
    assert "error" not in full, full
    result = dict(full)
    if result.pop("focus_checked"):
        assert result["title_focused"], "the full dialog didn't start on the title"
    result.pop("title_focused")
    return result


# Edit without Enter works too.
assert edit_with("rapat besok jam 3 sore", enter_first=False) == {
    "date": "2026-09-25", "title": "Rapat", "time": "15:00", "repeat": 0,
    "every": "every day", "every_on": False}
assert edit_with("bayar listrik tiap 3 bulan tanggal 31 jam 9", enter_first=True) == {
    "date": "2026-10-31", "title": "Bayar listrik", "time": "09:00", "repeat": 3,
    "every": "every 3 months", "every_on": True}
assert len(reminders()) == 4, "Edit saved something by itself"
# Saved from the full dialog, the interval is kept.
assert edit_with("minum obat tiap 2 hari jam 8 pagi", enter_first=True, save=True) == {
    "date": "2026-09-25", "title": "Minum obat", "time": "08:00", "repeat": 1,
    "every": "every 2 days", "every_on": True}
saved = reminders()
assert len(saved) == 5, saved
assert (saved[4]["title"], saved[4]["date"], saved[4]["time"], saved[4]["recurrence"],
        saved[4]["interval"]) == ("Minum obat", "2026-09-25", "08:00", "daily", 2), saved[4]
print("OK edit_full_dialog")

# --- The reminder dialog's sentence field and Fill in -----------------------------------------
dlg = AddReminderDialog(frame, "2026-10-05")
dlg.Show()
wx.Yield()
dlg.btn_fill.SetFocus()
wx.Yield()
observable = wx.Window.FindFocus() is dlg.btn_fill

# No date in the sentence: the dialog's own date stays.
dlg.txt_sentence.SetValue("minum obat tiap 2 hari jam 8 pagi")
spoken.clear()
fire(dlg.btn_fill, wx.EVT_BUTTON)
assert spoken == ["Minum obat, Monday 5 October 2026, at 08:00, every 2 days. "
                  "The fields are filled in; check them, then save."], spoken
assert (dlg.txt_title.GetValue(), dlg.txt_date.GetValue(), dlg.txt_time.GetValue()) == \
    ("Minum obat", "2026-10-05", "08:00")
assert dlg.choice_recur.GetSelection() == 1
assert dlg.choice_interval.GetStringSelection() == "every 2 days" and dlg.choice_interval.IsEnabled()
if observable:
    assert wx.Window.FindFocus() is dlg.btn_fill, "Fill in moved the focus"

# Enter in the sentence field fills in too; a date in the sentence wins.
dlg.txt_sentence.SetValue("rapat besok jam 3")
spoken.clear()
fire(dlg.txt_sentence, wx.EVT_TEXT_ENTER)
assert spoken == ["Rapat, Friday 25 September 2026, at 15:00. "
                  "The fields are filled in; check them, then save."], spoken
assert (dlg.txt_title.GetValue(), dlg.txt_date.GetValue(), dlg.txt_time.GetValue()) == \
    ("Rapat", "2026-09-25", "15:00")
assert dlg.choice_recur.GetSelection() == 0 and not dlg.choice_interval.IsEnabled()

# No title in the sentence: the title field keeps its own.
dlg.txt_sentence.SetValue("besok jam 8")
spoken.clear()
fire(dlg.btn_fill, wx.EVT_BUTTON)
assert spoken == ["I filled in Friday 25 September 2026, at 08:00, but not what to remind "
                  "you about. Type it in the title field."], spoken
assert (dlg.txt_title.GetValue(), dlg.txt_time.GetValue()) == ("Rapat", "08:00")

# Nothing about when: nothing changes.
dlg.txt_sentence.SetValue("minum obat")
spoken.clear()
fire(dlg.btn_fill, wx.EVT_BUTTON)
assert spoken == [_("qr_rb_nothing_found_fill")], spoken
assert "fields below" in spoken[0]
assert (dlg.txt_title.GetValue(), dlg.txt_date.GetValue(), dlg.txt_time.GetValue()) == \
    ("Rapat", "2026-09-25", "08:00")
dlg.txt_sentence.SetValue("")
spoken.clear()
fire(dlg.btn_fill, wx.EVT_BUTTON)
assert spoken == [_("rem_msg_empty_sentence")], spoken
if observable:
    assert wx.Window.FindFocus() is dlg.btn_fill, "Fill in moved the focus"

# How often follows the repeat, keeping the number; focus stays on Repeat.
dlg.choice_recur.SetFocus()
wx.Yield()
repeat_focus = wx.Window.FindFocus() is dlg.choice_recur
dlg.choice_interval.SetSelection(2)
dlg.choice_recur.SetSelection(2)
fire(dlg.choice_recur, wx.EVT_CHOICE)
assert dlg.choice_interval.GetString(0) == "every week"
assert dlg.choice_interval.GetStringSelection() == "every 3 weeks"
assert dlg.choice_interval.IsEnabled()
dlg.choice_recur.SetSelection(4)
fire(dlg.choice_recur, wx.EVT_CHOICE)
assert dlg.choice_interval.GetStringSelection() == "every 3 years"
dlg.choice_recur.SetSelection(0)
fire(dlg.choice_recur, wx.EVT_CHOICE)
assert not dlg.choice_interval.IsEnabled()
if repeat_focus:
    assert wx.Window.FindFocus() is dlg.choice_recur, "changing Repeat moved the focus"
assert len(reminders()) == 5, "Fill in saved something by itself"
dlg.Destroy()
wx.Yield()
print(f"OK fill_in ({focus_note(observable)})")

# --- Save a monthly reminder on the 31st from the calendar, and refuse a bad date --------------
assert core.api.set_selected_date("2026-01-31")


def save_monthly(dlg, observable):
    assert dlg.txt_date.GetValue() == "2026-01-31", dlg.txt_date.GetValue()
    dlg.txt_title.SetValue("Rent")
    dlg.txt_time.SetValue("9:00")
    dlg.choice_recur.SetSelection(3)
    fire(dlg.choice_recur, wx.EVT_CHOICE)
    spoken.clear()
    fire(dlg.btn_ok, wx.EVT_BUTTON)


run_modal(frame.OnAddReminder, AddReminderDialog, save_monthly)
saved = reminders()
assert len(saved) == 6, saved
assert (saved[5]["title"], saved[5]["date"], saved[5]["time"], saved[5]["recurrence"],
        saved[5]["interval"], saved[5]["anchor_day"]) == \
    ("Rent", "2026-01-31", "09:00", "monthly", 1, 31), saved[5]
assert spoken == ["Reminder saved."], spoken

refused = {}


def refuse_bad_date(dlg, observable):
    dlg.txt_title.SetValue("Rapat")
    dlg.txt_date.SetValue("2026-02-30")
    message_boxes.clear()
    fire(dlg.btn_ok, wx.EVT_BUTTON)
    refused.update(messages=list(message_boxes), open=dlg.IsModal(),
                   focus=wx.Window.FindFocus() is dlg.txt_date)
    press_escape(dlg)


run_modal(frame.OnAddReminder, AddReminderDialog, refuse_bad_date)
assert refused["messages"] == [_("rem_msg_invalid_date")], refused
assert refused["open"], "the dialog closed on a date that doesn't exist"
assert len(reminders()) == 6, "saved a date that doesn't exist"
print(f"OK full_dialog_save (focus on the date field: {refused['focus']})")

# --- Preferences, Reminders: switch German on ---------------------------------------------------
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Reminders")
prefs.Show()
wx.Yield()
panel = core.core_panels._reminders_panel_instance
assert panel is not None and panel.IsShown(), "the Reminders page was not created"
box = panel.list_languages
assert isinstance(box, wx.CheckListBox), box
assert box.GetName() == _plain(_("prefs_rem_lbl_languages")), box.GetName()
assert [box.GetString(i) for i in range(box.GetCount())] == ["Deutsch"]
assert not box.IsChecked(0)
check_children = [c for c in panel.GetChildren()]
index = check_children.index(box)
assert isinstance(check_children[index - 1], wx.StaticText), "the list has no label before it"
box.SetFocus()
wx.Yield()
observable = wx.Window.FindFocus() is box
box.Check(0, True)
fire(box, wx.EVT_CHECKLISTBOX)
assert prefs.is_dirty, "checking a language didn't count as a change"
if observable:
    assert wx.Window.FindFocus() is box
prefs.OnApply(None)
assert core.api.load_data("Core").get("quick_reminder_languages") == ["de"]
assert quick.active_packs() == ["en", "id", "de"]
prefs.Destroy()
wx.Yield()


def german(dlg, observable):
    type_text(dlg, "morgen halb neun Zahnarzt")
    spoken.clear()
    press_enter(dlg)
    assert spoken == ["Zahnarzt, Friday 25 September 2026, at 08:30. Save?"], spoken
    press_escape(dlg)


run_quick_reminder(german)
print(f"OK preferences ({focus_note(observable)})")

# --- Nothing went wrong along the way -----------------------------------------------------------
assert not network_attempts, f"network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
