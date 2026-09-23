# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load Clipboard History through the real loader with real wxPython, feed it
clipboard changes (through the bus and through the main window's own
once-a-second poll), open the history with its hotkey, browse, filter, pin,
delete, clear and copy, and check that focus stays on the list while browsing.

The real clipboard is never touched: core.api.get_clipboard/set_clipboard are
replaced by a fake before the main window starts polling, and the
password-manager check is replaced after one read-only call of the real one.

Run by tests/test_clipboard_history_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder. Prints one "OK" line per stage.
"""
import json
import logging
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
EXT_DIR = os.path.join(ROOT, "extensions", "clipboard_history")


def _watchdog():
    print("TIMEOUT: the clipboard history check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(180, _watchdog)
_timer.daemon = True
_timer.start()

# Exceptions in wx event handlers are printed, not raised; collect them.
problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    WATCHED = ("hariku_ext.clipboard_history", "clipboard_history_", "core.api",
               "core.events", "core.hotkeys", "core.extension_manager", "ui.preferences_dialog")

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
from core.events import bus

# A fake clipboard, in place before the main window starts polling it.
fake_clipboard = {"text": ""}
set_calls = []


def _fake_set_clipboard(value):
    set_calls.append(value)
    fake_clipboard["text"] = value
    return True


core.api.get_clipboard = lambda: fake_clipboard["text"]
core.api.set_clipboard = _fake_set_clipboard

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

from ui.main_window import MainWindow
frame = MainWindow(None, title="clipboard history check")
print("OK main_window")

V = ord("V")
PLAIN_V = (V, False, False, False, False)
SHIFT_V = (V, False, True, False, False)
assert PLAIN_V not in core.hotkeys.keybindings, "V is already bound by the core"
assert SHIFT_V not in core.hotkeys.keybindings, "Shift+V is already bound by the core"

import core.extension_manager as em
em.load_unpacked_extension(EXT_DIR)
assert "clipboard_history" in em.LOADED_EXTENSIONS, "Clipboard History did not load"
main = em.LOADED_EXTENSIONS["clipboard_history"]["module"]
cui = sys.modules["clipboard_history_ui"]
store = sys.modules["clipboard_history_store"]
cguard = sys.modules["clipboard_history_guard"]
assert core.hotkeys.keybindings[PLAIN_V][0] == "Clipboard History.open_history"
assert core.hotkeys.keybindings[SHIFT_V][0] == "Clipboard History.speak_last"
print("OK load")

# The real check only looks at the clipboard; then a controllable fake takes over.
real_guard = main._guard
assert isinstance(real_guard, cguard.WindowsClipboard) and real_guard.available
assert real_guard.is_private() in (True, False)


class FakeGuard:
    private = False

    def is_private(self):
        return self.private


fake_guard = FakeGuard()
main._guard = fake_guard
print("OK guard")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
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


def wait_for_speech(text, since=0, timeout=3.0):
    assert pump(lambda: text in spoken[since:], timeout), f"never spoke {text!r}; spoke {spoken[-5:]}"


def modal_dialogs():
    return [w for w in wx.GetTopLevelWindows() if isinstance(w, wx.Dialog) and w.IsModal()]


def while_modal(action, work, label):
    """Call action(), which shows a modal dialog; work(dialog) runs inside it and
    must close it. A dialog left open fails the check instead of hanging it."""
    errors, seen = [], []
    state = {"returned": False}

    def guard(dlg):
        if not state["returned"]:
            errors.append(AssertionError(f"{label}: dialog was left open"))
            dlg.EndModal(wx.ID_CANCEL)

    def step(tries=0):
        dialogs = modal_dialogs()
        if not dialogs:
            if tries < 50:
                wx.CallLater(100, step, tries + 1)
            else:
                errors.append(AssertionError(f"{label}: no dialog opened"))
            return
        dlg = dialogs[-1]
        seen.append(type(dlg).__name__)
        try:
            work(dlg)
        except Exception as e:
            errors.append(e)
            if dlg.IsModal():
                dlg.EndModal(wx.ID_CANCEL)
            return
        wx.CallLater(1500, guard, dlg)

    wx.CallLater(200, step)
    action()
    state["returned"] = True
    if errors:
        raise errors[0]
    assert seen, f"{label}: no dialog opened"
    return seen[0]


def fire(ctrl, event_type, index=None):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    if index is not None:
        evt.SetInt(index)
    ctrl.GetEventHandler().ProcessEvent(evt)
    wx.Yield()


def press(dlg, keycode):
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(keycode)
    key.SetEventObject(dlg)
    dlg.GetEventHandler().ProcessEvent(key)


def focus_is(ctrl):
    return wx.Window.FindFocus() is ctrl


def focus_stays_on(ctrl, message):
    """Assert focus is on ctrl. FindFocus() is None while another desktop window
    has the foreground, which is not a finding: returns False then (not
    observable). Focus on any other window of ours fails."""
    now = wx.Window.FindFocus()
    if now is None:
        return False
    assert now is ctrl, f"{message}: focus is on {type(now).__name__} {now.GetName()!r}"
    return True


def browse(ctrl, event_type, after_each=None):
    """Select every item and fire its selection event, as arrow keys do. Focus
    must stay on the control. Returns whether focus could be observed here
    (it can't while another desktop window is in the foreground)."""
    ctrl.SetFocus()
    wx.Yield()
    observable = focus_is(ctrl)
    assert ctrl.GetCount() > 0, "nothing to browse"
    for i in range(ctrl.GetCount()):
        ctrl.SetSelection(i)
        fire(ctrl, event_type, i)
        if after_each:
            after_each(i)
        if observable:
            now = wx.Window.FindFocus()
            if now is None:
                observable = False
                continue
            assert now is ctrl, f"focus left the list at item {i} for {type(now).__name__}"
    return observable


def row_index(listbox, text):
    for i in range(listbox.GetCount()):
        if text in listbox.GetString(i):
            return i
    raise AssertionError(f"no row containing {text!r}")


def copy(value):
    bus.emit("on_clipboard_changed", value)


def texts():
    return [i["text"] for i in main._history.items]


def saved_texts():
    assert main._writer.flush(5), "the save did not finish"
    path = store.items_path()
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return [i["text"] for i in json.load(f)["items"]]


focus_checked = []
_ = sys.modules["clipboard_history_text"]._

# --------------------------------------------------------------------------- #
# Recording
# --------------------------------------------------------------------------- #
# Through the main window's real poll of the (fake) clipboard.
fake_clipboard["text"] = "Poll: copied in another app"
assert pump(lambda: "Poll: copied in another app" in texts(), 4), "the poll was not recorded"

copy("Meeting at 10:00 in room 4")
copy("Line one\nLine two\nLine three")
copy("")
copy("   \r\n ")
copy("Line one\nLine two\nLine three")
copy("x" * (store.MAX_TEXT_BYTES + 1))
fake_guard.private = True
copy("hunter2 from a password manager")
fake_guard.private = False
main.apply_settings(dict(main.get_settings(), paused=True))
copy("copied while paused")
main.apply_settings(dict(main.get_settings(), paused=False))
copy("https://example.com/report")
assert texts() == ["https://example.com/report", "Line one\nLine two\nLine three",
                   "Meeting at 10:00 in room 4", "Poll: copied in another app"], texts()
assert saved_texts() is None, "history written to disk while Remember is off"
print("OK record")

spoken.clear()
assert core.hotkeys.process_key_event(*SHIFT_V)
assert spoken == ["https://example.com/report"], spoken
print("OK speak_last")


# --------------------------------------------------------------------------- #
# The hotkey opens the dialog; Escape closes it
# --------------------------------------------------------------------------- #
def check_open(dlg):
    assert isinstance(dlg, cui.HistoryDialog), type(dlg).__name__
    assert dlg.GetTitle() == "Clipboard history", dlg.GetTitle()
    assert dlg.list.GetCount() == 4
    assert dlg.list.GetSelection() == 0, "the last copy should be selected"
    assert dlg.txt_full.GetValue() == "https://example.com/report"
    dlg.EndModal(wx.ID_CANCEL)


assert while_modal(lambda: core.hotkeys.process_key_event(*PLAIN_V), check_open,
                   "open") == "HistoryDialog"
assert main._dialog is None
print("OK hotkey")

state = {}


def press_escape():
    for w in modal_dialogs():
        if isinstance(w, cui.HistoryDialog):
            state["found"] = True
            press(w, wx.WXK_ESCAPE)


def force_close():
    for w in modal_dialogs():
        state["forced"] = True
        w.EndModal(wx.ID_CANCEL)


escape = wx.CallLater(400, press_escape)
closer = wx.CallLater(3000, force_close)
core.hotkeys.actions["Clipboard History.open_history"].callback()
closer.Stop()
escape.Stop()
assert state.get("found") and not state.get("forced"), f"Escape did not close the history: {state}"
print("OK escape")

# --------------------------------------------------------------------------- #
# Browsing: the full text follows the selection, focus stays on the list
# --------------------------------------------------------------------------- #
dlg = cui.HistoryDialog(frame, main.DialogActions)
dlg.Show()
pump(lambda: False, 0.1)
rows = [dlg.list.GetString(i) for i in range(dlg.list.GetCount())]
assert rows == ["https://example.com/report, just now",
                "Line one / Line two / Line three, just now",
                "Meeting at 10:00 in room 4, just now",
                "Poll: copied in another app, just now"], rows
assert dlg.lbl_list.GetLabel() == "&Items (4):" and dlg.list.GetName() == "Items (4)"
assert dlg.txt_filter.GetName() == "Filter" and dlg.txt_full.GetName() == "Full text"
items = list(main._history.items)


def full_text_follows(i):
    assert dlg.txt_full.GetValue() == items[i]["text"], (i, dlg.txt_full.GetValue())


focus_checked.append(browse(dlg.list, wx.EVT_LISTBOX, full_text_follows))
print("OK browse")

# --------------------------------------------------------------------------- #
# Filter
# --------------------------------------------------------------------------- #
dlg.txt_filter.SetFocus()
wx.Yield()
filter_focused = focus_is(dlg.txt_filter)
mark = len(spoken)
dlg.txt_filter.SetValue("LINE two")
assert dlg.list.GetCount() == 1 and dlg.list.GetString(0).startswith("Line one / Line two")
assert dlg.lbl_list.GetLabel() == "&Items (1 of 4):", dlg.lbl_list.GetLabel()
assert dlg.txt_full.GetValue() == "Line one\nLine two\nLine three"
wait_for_speech("1 item", since=mark)
if filter_focused:
    filter_focused = focus_stays_on(dlg.txt_filter, "filtering moved focus")

dlg.txt_filter.SetValue("no such text")
assert dlg.list.GetString(0) == "No items match the filter."
assert dlg.selected_item() is None and dlg.txt_full.GetValue() == ""
mark = len(spoken)
dlg.on_copy()
assert spoken[mark:] == ["No item is selected."], spoken[mark:]

dlg.txt_filter.SetValue("room meeting")
assert dlg.list.GetCount() == 1 and dlg.list.GetString(0).startswith("Meeting at 10:00")
dlg.txt_filter.SetFocus()
wx.Yield()
fire(dlg.txt_filter, wx.EVT_TEXT_ENTER)
if filter_focused:
    filter_focused = focus_stays_on(dlg.list, "Enter in the filter box should move to the list")
dlg.txt_filter.SetValue("")
assert dlg.list.GetCount() == 4 and dlg.lbl_list.GetLabel() == "&Items (4):"
assert dlg.list.GetStringSelection().startswith("Meeting at 10:00"), "selection kept"
print(f"OK filter ({'focus checked' if filter_focused else 'focus not observable here'})")

# --------------------------------------------------------------------------- #
# Pin
# --------------------------------------------------------------------------- #
dlg.list.SetSelection(row_index(dlg.list, "Meeting at 10:00"))
fire(dlg.list, wx.EVT_LISTBOX, dlg.list.GetSelection())
assert dlg.btn_pin.GetLabel() == "&Pin"
mark = len(spoken)
fire(dlg.btn_pin, wx.EVT_BUTTON)
assert spoken[mark:] == ["Pinned."], spoken[mark:]
assert dlg.list.GetString(0) == "Pinned: Meeting at 10:00 in room 4, just now", dlg.list.GetString(0)
assert dlg.list.GetSelection() == 0 and dlg.btn_pin.GetLabel() == "Un&pin"
assert saved_texts() == ["Meeting at 10:00 in room 4"], "only the pinned item is saved"
assert not os.path.exists(store.items_path() + ".bak")
focus_checked.append(browse(dlg.list, wx.EVT_LISTBOX))

dlg.list.SetSelection(row_index(dlg.list, "https://example.com"))
fire(dlg.btn_pin, wx.EVT_BUTTON)
assert dlg.list.GetString(0).startswith("Pinned: https://example.com")
fire(dlg.btn_pin, wx.EVT_BUTTON)
assert spoken[-1] == "Unpinned."
assert dlg.list.GetString(1) == "https://example.com/report, just now"
assert dlg.list.GetSelection() == 1
print("OK pin")

# --------------------------------------------------------------------------- #
# Delete (key and button) and Clear all
# --------------------------------------------------------------------------- #
confirms = []
answers = []
cui._confirm = lambda parent, message, title: confirms.append(message) or answers.pop(0)

dlg.list.SetSelection(row_index(dlg.list, "Poll: copied"))
dlg.list.SetFocus()
wx.Yield()
mark = len(spoken)
if focus_is(dlg.list):
    press(dlg, wx.WXK_DELETE)
else:
    dlg.on_delete()
wait_for_speech("Deleted.", since=mark)
assert "Poll: copied in another app" not in texts()
assert dlg.list.GetCount() == 3
assert not confirms, "an unpinned item is deleted without asking"
focus_checked.append(focus_stays_on(dlg.list, "focus should stay on the list after deleting"))

dlg.list.SetSelection(0)
answers.append(False)
fire(dlg.btn_delete, wx.EVT_BUTTON)
assert confirms and "Meeting at 10:00 in room 4" in confirms[-1]
assert "Meeting at 10:00 in room 4" in texts(), "a pinned item was deleted without a yes"

answers.append(True)
mark = len(spoken)
fire(dlg.btn_clear, wx.EVT_BUTTON)
assert "(2 in all)" in confirms[-1], confirms[-1]
wait_for_speech("History cleared. Pinned items kept: 1.", since=mark)
assert texts() == ["Meeting at 10:00 in room 4"]
assert dlg.list.GetCount() == 1
mark = len(spoken)
fire(dlg.btn_clear, wx.EVT_BUTTON)
assert spoken[mark:] == ["There is nothing to clear. Pinned items are kept."], spoken[mark:]
dlg.Destroy()
wx.Yield()
print("OK delete_clear")

# --------------------------------------------------------------------------- #
# Copy: Enter on the list, through the hotkey; our own change is not recorded
# --------------------------------------------------------------------------- #
copy("Second copy for pasting")
copy("Third copy")
assert texts() == ["Meeting at 10:00 in room 4", "Third copy", "Second copy for pasting"]
before = [(i["id"], i["time"]) for i in main._history.items]
copy_state = {}


def do_copy(d):
    d.list.SetSelection(row_index(d.list, "Second copy for pasting"))
    fire(d.list, wx.EVT_LISTBOX, d.list.GetSelection())
    assert d.txt_full.GetValue() == "Second copy for pasting"
    d.list.SetFocus()
    wx.Yield()
    if focus_is(d.list):
        copy_state["enter"] = True
        press(d, wx.WXK_RETURN)
    else:
        fire(d.btn_copy, wx.EVT_BUTTON)


mark = len(spoken)
while_modal(lambda: core.hotkeys.process_key_event(*PLAIN_V), do_copy, "copy")
assert set_calls == ["Second copy for pasting"], set_calls
wait_for_speech("Copied. Press Control+V to paste.", since=mark)
assert not modal_dialogs(), "the dialog should close after copying"
# The main window's poll sees the change Hariku made; it must not count as a copy.
assert pump(lambda: frame._last_clipboard == "Second copy for pasting", 4), "poll never ran"
assert pump(lambda: main._ignore is None, 2), "the copy-back was never seen"
assert [(i["id"], i["time"]) for i in main._history.items] == before, texts()
print(f"OK copy ({'Enter key' if copy_state.get('enter') else 'Copy button'})")

# --------------------------------------------------------------------------- #
# Preferences page
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Clipboard History")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "the settings page was not created"
assert panel.choice_size.GetStringSelection() == "50 items"
assert not panel.chk_remember.GetValue() and not panel.chk_paused.GetValue()
assert "password managers" in panel.txt_privacy.GetValue()
assert panel.choice_size.GetName() == "History size" and panel.txt_privacy.GetName() == "Privacy"
focus_checked.append(browse(panel.choice_size, wx.EVT_CHOICE))
panel.choice_size.SetSelection(1)

panel.chk_remember.SetValue(True)
prefs.OnApply(None)
assert saved_texts() == ["Meeting at 10:00 in room 4", "Third copy", "Second copy for pasting"]
assert core.api.load_data("ClipboardHistory") == {"limit": 50, "remember": True, "paused": False}

panel.chk_remember.SetValue(False)
prefs.OnApply(None)
# Deleted at once: no waiting for the writer here.
with open(store.items_path(), encoding="utf-8") as f:
    assert [i["text"] for i in json.load(f)["items"]] == ["Meeting at 10:00 in room 4"]
assert not os.path.exists(store.items_path() + ".bak")
assert "Third copy" not in open(store.items_path(), encoding="utf-8").read()

panel.choice_size.SetSelection(0)
panel.chk_paused.SetValue(True)
prefs.OnApply(None)
assert main.get_settings() == {"limit": 25, "remember": False, "paused": True}
copy("not while paused")
assert "not while paused" not in texts()
prefs.Destroy()
wx.Yield()

paused_dlg = cui.HistoryDialog(frame, main.DialogActions)
assert paused_dlg.GetTitle() == "Clipboard history (recording paused)", paused_dlg.GetTitle()
paused_dlg.Destroy()
main.apply_settings(dict(main.get_settings(), paused=False))
print("OK settings")

# --------------------------------------------------------------------------- #
# Teardown, and nothing went wrong along the way
# --------------------------------------------------------------------------- #
em.unload_all_extensions()
assert main._on_clipboard_changed not in bus._listeners.get("on_clipboard_changed", [])
copy("after unload")
assert "after unload" not in texts()
print("OK teardown")

assert not problems, "\n".join(problems)
print("OK no_errors")
print(f"OK focus ({'checked' if focus_checked and all(focus_checked) else 'not observable here'})")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
