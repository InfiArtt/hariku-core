# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load Sleep Pattern through the real loader with real wxPython, give it ten
nights of made-up history, run both hotkey actions, open the history (browse,
Details, This wasn't sleep, Undo, Clear all) and its Preferences page inside
the real Preferences dialog, and check that focus stays on a list while
browsing it.

The real Windows clock is read once (read-only: the last input time and the
uptime), then a fake clock takes over, so the check never depends on who is
touching the keyboard. Speech is captured through on_before_speak, and the
reminder sound is captured instead of played.

Run by tests/test_sleep_tracker_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder so the user's real data is never touched. Prints one "OK"
line per stage.
"""
import datetime
import logging
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
EXT_DIR = os.path.join(ROOT, "extensions", "sleep_tracker")


def _watchdog():
    print("TIMEOUT: the sleep pattern check hung", flush=True)
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
    WATCHED = ("hariku_ext.sleep_tracker", "sleep_tracker_", "core.api", "core.events",
               "core.hotkeys", "core.extension_manager", "ui.preferences_dialog")

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

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

from ui.main_window import MainWindow
frame = MainWindow(None, title="sleep pattern check")
print("OK main_window")

Z = ord("Z")
SHIFT_Z = (Z, False, True, False, False)
PLAIN_Z = (Z, False, False, False, False)
assert PLAIN_Z not in core.hotkeys.keybindings, "Z is already bound by the core"
assert SHIFT_Z not in core.hotkeys.keybindings, "Shift+Z is already bound by the core"

import core.extension_manager as em
em.load_unpacked_extension(EXT_DIR)
assert "sleep_tracker" in em.LOADED_EXTENSIONS, "Sleep Pattern did not load"
main = em.LOADED_EXTENSIONS["sleep_tracker"]["module"]
store = sys.modules["sleep_tracker_store"]
system = sys.modules["sleep_tracker_system"]
text = sys.modules["sleep_tracker_text"]
sui = sys.modules["sleep_tracker_ui"]
assert core.hotkeys.keybindings[SHIFT_Z][0] == "Sleep Pattern.history"
assert core.hotkeys.keybindings[PLAIN_Z][0] == "Sleep Pattern.last_night"
print("OK load")

# The real clock: read-only calls, no hook.
real_clock = main._clock
assert isinstance(real_clock, system.WindowsClock) and real_clock.available
reading = real_clock.read()
assert reading is not None, "GetLastInputInfo / GetTickCount64 failed"
assert reading["idle"] >= 0 and reading["boot"] < reading["wall"], reading
assert reading["awake"] is None or 0 <= reading["awake"] <= reading["wall"] - reading["boot"] + 5
print("OK real_clock")

# From here on: a fixed "now" (today at 12:00) and a fake clock.
TODAY = datetime.date.today()
NOW = datetime.datetime.combine(TODAY, datetime.time(12, 0))
MINUTE = datetime.timedelta(minutes=1)


def at(day, clock):
    hour, minute = map(int, clock.split(":"))
    return datetime.datetime.combine(TODAY + datetime.timedelta(days=day), datetime.time(hour, minute))


class FakeClock:
    def __init__(self, when):
        self.when = when
        self.boot = when - datetime.timedelta(days=12)
        self.idle = 5.0

    def read(self):
        wall = self.when.timestamp()
        uptime = wall - self.boot.timestamp()
        return system.make_sample(wall, uptime * 1000, uptime * 1e7, self.idle * 1000)


fake_clock = FakeClock(NOW)
main._clock = fake_clock
main._now = lambda: NOW
sounds = []
main._play_sound = sounds.append


def fill(rec, start, end, state):
    t = start
    while t < end:
        rec.days.setdefault(t.date(), bytearray(1440))[t.hour * 60 + t.minute] = state
        t += MINUTE


def history():
    """Eleven nights: today's 23:30-07:10; yesterday's 01:15-07:40 and a nap;
    a daytime sleep after staying up; a night Hariku wasn't running; five
    00:00-07:00; one with no break; and the oldest, half known."""
    rec = store.Recorder()
    fill(rec, at(-10, "06:00"), NOW, store.ACTIVE)
    fill(rec, at(-1, "23:30"), at(0, "07:10"), store.INACTIVE)
    fill(rec, at(-1, "01:15"), at(-1, "07:40"), store.INACTIVE)
    fill(rec, at(-1, "14:00"), at(-1, "15:40"), store.INACTIVE)
    fill(rec, at(-2, "10:05"), at(-2, "14:10"), store.INACTIVE)
    fill(rec, at(-4, "21:00"), at(-3, "09:00"), store.UNKNOWN)
    for day in range(-8, -3):
        fill(rec, at(day, "00:00"), at(day, "07:00"), store.INACTIVE)
    return rec


main._recorder = history()
main._nights.clear()
_ = text._
print("OK history")


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


def wait_for_speech(message, since=0, timeout=3.0):
    assert pump(lambda: message in spoken[since:], timeout), \
        f"never spoke {message!r}; spoke {spoken[-5:]}"


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


def press(window, keycode):
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(keycode)
    key.SetEventObject(window)
    window.GetEventHandler().ProcessEvent(key)


def focus_is(ctrl):
    return wx.Window.FindFocus() is ctrl


def focus_stays_on(ctrl, message):
    """Assert focus is on ctrl. FindFocus() is None while another desktop window
    has the foreground, which is not a finding: returns False then."""
    now = wx.Window.FindFocus()
    if now is None:
        return False
    assert now is ctrl, f"{message}: focus is on {type(now).__name__} {now.GetName()!r}"
    return True


def browse(ctrl, event_type, after_each=None):
    """Select every item and fire its selection event, as arrow keys do. Focus
    must stay on the control. Returns whether focus could be observed here."""
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


focus_checked = []

# --------------------------------------------------------------------------- #
# Last night's sleep (Z) and the Morning Briefing sentence
# --------------------------------------------------------------------------- #
spoken.clear()
core.hotkeys.actions["Sleep Pattern.last_night"].callback()
assert len(spoken) == 1, spoken
assert spoken[0] == ("You probably slept from 23:30 to 07:10, about 7 hours 40 minutes. "
                     "1 hour 15 minutes more than your 7-day average."), spoken[0]
lines = []
bus.emit("on_briefing_collect", lines)
assert lines == ["Last night you slept about 7 hours 40 minutes, from 23:30 to 07:10."], lines
print("OK last_night")

# --------------------------------------------------------------------------- #
# Shift+Z opens the history; Escape closes it
# --------------------------------------------------------------------------- #
FIRST_ROW = (f"{text.night_label(TODAY)}: You probably slept from 23:30 to 07:10, "
             f"about 7 hours 40 minutes.")


def check_open(dlg):
    assert isinstance(dlg, sui.HistoryDialog), type(dlg).__name__
    assert dlg.GetTitle() == "Sleep history", dlg.GetTitle()
    assert dlg.list.GetCount() == 11, dlg.list.GetCount()
    assert dlg.list.GetSelection() == 0
    assert dlg.list.GetString(0) == FIRST_ROW, dlg.list.GetString(0)
    summary = dlg.txt_summary.GetValue()
    assert summary.startswith("Last 7 nights: ") and "You stayed up late 2 nights this week." in summary, summary
    dlg.EndModal(wx.ID_CANCEL)


assert while_modal(lambda: core.hotkeys.process_key_event(*SHIFT_Z), check_open,
                   "open") == "HistoryDialog"
assert main._dialog is None
print("OK hotkey")

state = {}


def press_escape():
    for w in modal_dialogs():
        if isinstance(w, sui.HistoryDialog):
            state["found"] = True
            press(w, wx.WXK_ESCAPE)


def force_close():
    for w in modal_dialogs():
        state["forced"] = True
        w.EndModal(wx.ID_CANCEL)


escape = wx.CallLater(400, press_escape)
closer = wx.CallLater(3000, force_close)
core.hotkeys.actions["Sleep Pattern.history"].callback()
closer.Stop()
escape.Stop()
assert state.get("found") and not state.get("forced"), f"Escape did not close the history: {state}"
print("OK escape")

# --------------------------------------------------------------------------- #
# Browsing: one full sentence per night, the button follows, focus stays put
# --------------------------------------------------------------------------- #
dlg = sui.HistoryDialog(frame, main.HistoryActions)
dlg.Show()
pump(lambda: False, 0.1)
rows = [dlg.list.GetString(i) for i in range(dlg.list.GetCount())]
assert rows[1].endswith("You stayed up until 01:15. You also napped from 14:00 to 15:40."), rows[1]
assert rows[2].endswith("You stayed up all night, then probably slept from 10:05 to 14:10, "
                        "about 4 hours 5 minutes."), rows[2]
assert rows[3].endswith(": Not enough data."), rows[3]
assert dlg.list.GetName() == "Nights, newest first" and dlg.txt_summary.GetName() == "Summary"
NOT_SLEEP, UNDO = _("btn_not_sleep"), _("btn_undo")


def button_follows(i):
    assert dlg.btn_mark.GetLabel() == NOT_SLEEP, (i, dlg.btn_mark.GetLabel())


focus_checked.append(browse(dlg.list, wx.EVT_LISTBOX, button_follows))
print("OK browse")

# --------------------------------------------------------------------------- #
# Details: Enter on the list opens it, Enter closes it, focus comes back
# --------------------------------------------------------------------------- #
dlg.list.SetSelection(1)
fire(dlg.list, wx.EVT_LISTBOX, 1)
dlg.list.SetFocus()
wx.Yield()
details_state = {}


def open_details():
    if focus_is(dlg.list):
        details_state["enter"] = True
        press(dlg, wx.WXK_RETURN)
    else:
        dlg.on_details()


def check_details(d):
    assert isinstance(d, sui.DetailsDialog), type(d).__name__
    value = d.txt_details.GetValue()
    assert value.startswith(text.night_label(TODAY - datetime.timedelta(days=1))), value
    assert "Stayed up late: yes, until 01:15. Your bedtime is 00:00." in value, value
    assert "Nap from 14:00 to 15:40, about 1 hour 40 minutes." in value, value
    assert value.endswith("This is an estimate from computer use, not a medical measurement.")
    assert d.txt_details.GetName() == "Details"
    press(d, wx.WXK_RETURN)


assert while_modal(open_details, check_details, "details") == "DetailsDialog"
focus_checked.append(focus_stays_on(dlg.list, "focus should return to the list after Details"))
print(f"OK details ({'Enter key' if details_state.get('enter') else 'Details button'})")

# --------------------------------------------------------------------------- #
# This wasn't sleep, then Undo
# --------------------------------------------------------------------------- #
dlg.list.SetSelection(0)
fire(dlg.list, wx.EVT_LISTBOX, 0)
before_summary = dlg.txt_summary.GetValue()
mark = len(spoken)
fire(dlg.btn_mark, wx.EVT_BUTTON)
assert spoken[mark:] == [_("marked")], spoken[mark:]
assert dlg.list.GetSelection() == 0
assert dlg.list.GetString(0).endswith("You marked 23:30 to 07:10 as not sleep."), dlg.list.GetString(0)
assert dlg.btn_mark.GetLabel() == UNDO
assert dlg.txt_summary.GetValue() != before_summary
saved = core.api.load_data(main.DATA_KEY)["corrections"]
assert len(saved) == 1 and saved[0]["night"] == TODAY.isoformat(), saved
spoken.clear()
core.hotkeys.actions["Sleep Pattern.last_night"].callback()
assert spoken[-1].startswith("You probably slept from 01:15 to 07:40"), spoken[-1]

mark = len(spoken)
fire(dlg.btn_mark, wx.EVT_BUTTON)
assert spoken[mark:] == [_("unmarked")], spoken[mark:]
assert dlg.list.GetString(0) == FIRST_ROW and dlg.btn_mark.GetLabel() == NOT_SLEEP
assert core.api.load_data(main.DATA_KEY)["corrections"] == []
assert dlg.txt_summary.GetValue() == before_summary
focus_checked.append(browse(dlg.list, wx.EVT_LISTBOX))
print("OK mark_undo")

# --------------------------------------------------------------------------- #
# Preferences page
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

confirms, answers = [], []
sui._confirm = lambda parent, message, title: confirms.append(message) or answers.pop(0)

prefs = PreferencesDialog(frame, select_tab="Sleep Pattern")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "the settings page was not created"
assert panel.chk_enabled.GetValue() and not panel.chk_nudge.GetValue()
assert panel.chk_nudge_sound.GetValue()
assert panel.choice_bedtime.GetStringSelection() == "00:00"
assert panel.choice_min_sleep.GetStringSelection() == "3 hours"
assert panel.choice_ignore.GetStringSelection() == "Up to 10 minutes"
assert panel.choice_bedtime.GetName() == "Bedtime (going to sleep later counts as staying up late)"
assert panel.txt_about.GetName() == "About sleep tracking"
about = panel.txt_about.GetValue()
assert "never what you typed or which apps you used" in about and "not a medical measurement" in about
for choice in (panel.choice_bedtime, panel.choice_min_sleep, panel.choice_ignore):
    focus_checked.append(browse(choice, wx.EVT_CHOICE))

panel.choice_bedtime.SetSelection(store.BEDTIME_CHOICES.index(60))
panel.choice_min_sleep.SetSelection(0)
panel.choice_ignore.SetSelection(1)
panel.chk_nudge.SetValue(True)
prefs.OnApply(None)
assert main.get_settings() == {"enabled": True, "bedtime": 60, "min_sleep": 120,
                               "ignore_activity": 5, "nudge": True, "nudge_sound": True}
saved = core.api.load_data(main.DATA_KEY)
assert saved["bedtime"] == 60 and saved["nudge"] is True
prefs.Destroy()
wx.Yield()
print("OK settings")

# --------------------------------------------------------------------------- #
# The minute tick through the bus, and the late-night reminder
# --------------------------------------------------------------------------- #
fake_clock.when = NOW + MINUTE
mark = len(spoken)
bus.emit("on_minute_tick", fake_clock.when)
assert main._recorder.state_at(NOW) == store.ACTIVE
assert spoken[mark:] == [] and sounds == []                  # midday: no reminder

fake_clock.when = at(1, "01:31")       # bedtime 01:00 + 30 minutes, still typing
mark = len(spoken)
bus.emit("on_minute_tick", fake_clock.when)
assert spoken[mark:] == ["It's 01:31. Don't forget to rest."], spoken[mark:]
assert sounds == ["info.wav"], sounds
fake_clock.when += MINUTE
bus.emit("on_minute_tick", fake_clock.when)
assert len(spoken) == mark + 1, "the reminder came twice in one night"
print("OK tick_and_reminder")

# --------------------------------------------------------------------------- #
# Clear all history (No, then Yes)
# --------------------------------------------------------------------------- #
answers.append(False)
fire(dlg.btn_clear, wx.EVT_BUTTON)
assert confirms and "Delete all sleep history?" in confirms[-1]
assert dlg.list.GetCount() == 11, "history cleared without a yes"
answers.append(True)
mark = len(spoken)
fire(dlg.btn_clear, wx.EVT_BUTTON)
wait_for_speech(_("cleared"), since=mark)
assert dlg.list.GetCount() == 1 and dlg.list.GetString(0) == _("empty_rows")
assert dlg.txt_summary.GetValue() == _("summary_empty")
assert core.api.load_data(main.ACTIVITY_KEY)["days"] == {}
focus_checked.append(focus_stays_on(dlg.list, "focus should stay on the list after clearing"))
mark = len(spoken)
fire(dlg.btn_mark, wx.EVT_BUTTON)
assert spoken[mark:] == [_("nothing_selected")], spoken[mark:]
fire(dlg.btn_clear, wx.EVT_BUTTON)
assert spoken[-1] == _("nothing_to_clear"), spoken[-1]
dlg.Destroy()
wx.Yield()
print("OK clear")

# --------------------------------------------------------------------------- #
# Teardown, and nothing went wrong along the way
# --------------------------------------------------------------------------- #
em.unload_all_extensions()
assert main._on_minute_tick not in bus._listeners.get("on_minute_tick", [])
assert main._on_briefing_collect not in bus._listeners.get("on_briefing_collect", [])
assert core.api.load_data(main.ACTIVITY_KEY)["last"]["final"] is True
lines = []
bus.emit("on_briefing_collect", lines)
assert lines == []
print("OK teardown")

assert not problems, "\n".join(problems)
print("OK no_errors")
print(f"OK focus ({'checked' if focus_checked and all(focus_checked) else 'not observable here'})")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
