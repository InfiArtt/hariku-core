# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load Timer & Alarm through the real loader with real wxPython, then use it
through the real Aruna (the command bar): set an alarm after its read-back,
start a timer, ask the time left, list them, let the timer ring (a fake ring:
the clock, the key readings and the sound player are fakes) and stop it by
telling Aruna "stop", stop the next one with a (fake) key press and snooze it,
then open its Preferences page inside the real Preferences dialog: the labels
and their order, the rows, browsing without the focus moving, Test (the
player is a fake), Remove with Delete (after asking), Stop ringing, and Apply.
Also the Morning Briefing sentence and unloading.

Speech is captured through on_before_speak and cancelled; nothing is played,
no key is pressed and nothing is recorded. Run by tests/test_timer_alarm_ui.py
in a separate process (conftest.py mocks wx in the pytest process) with
APPDATA pointing at a temporary folder. Prints one "OK" line per stage. Never
run it on a computer someone is using: it opens windows.
"""
import datetime
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
EXT_DIR = os.path.join(ROOT, "extensions", "timer_alarm")


def _watchdog():
    print("TIMEOUT: the timer and alarm check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(200, _watchdog)
_timer.daemon = True
_timer.start()

import urllib.request

network_attempts = []


def _blocked_urlopen(*args, **kwargs):
    network_attempts.append(args[0] if args else kwargs)
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked_urlopen

problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    WATCHED = ("hariku_ext.timer_alarm", "timer_alarm_", "core.commands", "core.voice",
               "core.speech", "core.hotkeys", "core.extension_manager", "ui.command_bar",
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
import core.commands
from core.events import bus

core.api.save_data("Core", {"onboarding_completed": True, "language": "en",
                            "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad"),
                            "aruna_keep_open": True, "aruna_sounds": False})
core.i18n.init("en")

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

from ui.main_window import MainWindow
frame = MainWindow(None, title="timer and alarm check")
frame.heartbeat_timer.Stop()
frame.monitor_timer.Stop()
print("OK main_window")

import ui.command_bar as cb

focus_calls = []
cb.set_foreground = lambda hwnd: focus_calls.append(hwnd) or True
PREVIOUS = frame.GetHandle()
cb.foreground_window = lambda: PREVIOUS

# --------------------------------------------------------------------------- #
# Loading: actions without default keys, commands with content
# --------------------------------------------------------------------------- #
import core.extension_manager as em
em.load_unpacked_extension(EXT_DIR)
assert "timer_alarm" in em.LOADED_EXTENSIONS, f"Timer & Alarm did not load: {em.LOAD_ERRORS}"
main = em.LOADED_EXTENSIONS["timer_alarm"]["module"]
parse = sys.modules["timer_alarm_parse"]
intents = sys.modules["timer_alarm_intents"]
store = sys.modules["timer_alarm_store"]
ACTION_IDS = [f"Timer and Alarm.{name}" for name in main.ACTIONS]
for action_id in ACTION_IDS:
    action = core.hotkeys.actions[action_id]
    assert action.default_keycode is None, f"{action_id} has a default key"
    assert core.commands.is_answer_action(action_id), action_id
assert {i.id for i in core.commands.intents()} >= {f"Timer and Alarm.{n}" for n in main.INTENTS}
assert main._timer is not None and main._timer.IsRunning()
print("OK load")


# --------------------------------------------------------------------------- #
# A fake world: the clock, the key readings, the sound player
# --------------------------------------------------------------------------- #
class World:
    def __init__(self):
        self.wall = datetime.datetime(2026, 9, 25, 10, 40)      # a Friday
        self.mono = 5000.0
        self.tick = 100
        self.held = False
        self.pos = (1, 1)

    def advance(self, seconds):
        self.wall += datetime.timedelta(seconds=seconds)
        self.mono += seconds

    def press_key(self):
        self.tick += 1

    def readers(self):
        return (lambda: self.tick, lambda: self.held, lambda: self.pos)


world = World()
plays, stops = [], []
main._app.shutdown()
main._app = main.make_app(now=lambda: world.wall, clock=lambda: world.mono,
                          play=plays.append, stop=stops.append,
                          input_readers=world.readers())
main._app.start()
main._assistant = intents.Assistant(main._app)
test_plays, test_stops = [], []
main.PageActions.play = staticmethod(test_plays.append)
main.PageActions.stop_sound = staticmethod(test_stops.append)
print("OK fakes")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def pump(condition, timeout=5.0):
    """Process events until condition() is true or the timeout passes."""
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


def type_text(bar, text):
    bar.txt_input.SetValue(text)


def press_enter(bar):
    fire(bar.txt_input, wx.EVT_TEXT_ENTER)


def press_escape(bar):
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_ESCAPE)
    key.SetEventObject(bar.txt_input)
    bar.GetEventHandler().ProcessEvent(key)


def open_bar():
    core.hotkeys.actions["Hariku Core.command_bar"].callback()
    assert pump(lambda: cb.current_bar() is not None), "Aruna did not open"
    bar = cb.current_bar()
    pump(lambda: wx.Window.FindFocus() is bar.txt_input, timeout=1.0)
    return bar, wx.Window.FindFocus() is bar.txt_input


def close_bar(bar):
    press_escape(bar)
    assert pump(lambda: cb.current_bar() is None), "Escape did not close Aruna"


def say_to(bar, text, expect, timeout=3.0):
    """Type a command, press Enter, and wait until `expect` (a string, or a
    function of the last thing said) is said."""
    mark = len(spoken)
    type_text(bar, text)
    press_enter(bar)
    check = expect if callable(expect) else (lambda said: said == expect)
    ok = pump(lambda: any(check(s) for s in spoken[mark:]), timeout)
    assert ok, f"{text!r}: expected {expect!r}, Aruna said {spoken[mark:]}"
    return spoken[mark:]


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


def top_windows():
    return {w for w in wx.GetTopLevelWindows() if w.IsShown()}


# --------------------------------------------------------------------------- #
# An alarm: read back with the day, the date and the part of the day, set on yes
# --------------------------------------------------------------------------- #
bar, focus_ok = open_bar()
say_to(bar, "set alarm tomorrow at 2 for gang war",
       'Alarm "gang war", tomorrow, Saturday 26 September, at 2:00 AM. Set it?')
assert bar.txt_status.GetValue().startswith("Aruna asks"), bar.txt_status.GetValue()
assert main._app.schedule.items == [], "set before the answer"
if focus_ok:
    assert wx.Window.FindFocus() is bar.txt_input, "the question moved focus"
mark = len(spoken)
press_enter(bar)                                        # Enter again: yes
assert pump(lambda: "Alarm set, 15 hours 20 minutes from now." in spoken[mark:]), spoken[mark:]
saved = core.api.load_data(store.DATA_KEY)["items"]
assert [(i["label"], i["due"]) for i in saved] == [("gang war", "2026-09-26T02:00:00")], saved
assert cb.current_bar() is bar, "Aruna closed after the answer"
print(f"OK alarm ({focus_note(focus_ok)})")

# "No", then the time said again with its part of the day.
say_to(bar, "alarm besok jam 7 olahraga",
       'Alarm "olahraga", tomorrow, Saturday 26 September, at 7:00 AM. Set it?')
say_to(bar, "no", "OK, cancelled.")
say_to(bar, "jam 7 malam", 'Alarm "olahraga", tomorrow, Saturday 26 September, at 7:00 PM. '
                           'Set it?')
say_to(bar, "pasang", lambda s: s.startswith("Alarm set, "))
assert [a["due"] for a in main._app.schedule.alarms()][-1] == datetime.datetime(2026, 9, 26, 19, 0)
print("OK correction")

# --------------------------------------------------------------------------- #
# Timers, the time left, the list
# --------------------------------------------------------------------------- #
say_to(bar, "timer tea 3 minutes", 'Timer "tea", 3 minutes, started.')
say_to(bar, "how long is left on the tea timer", 'The timer "tea": 3 minutes left.')
say_to(bar, "list my alarms",
       'Alarms: "gang war", tomorrow at 2:00 AM; "olahraga", tomorrow at 7:00 PM. '
       'Timers: "tea", 3 minutes left.')
assert cb.current_bar() is bar
print("OK timer")

# --------------------------------------------------------------------------- #
# The timer rings: sound and speech, no window, the focus stays; "stop" stops it
# --------------------------------------------------------------------------- #
close_bar(bar)
before = top_windows()
main_shown = frame.IsShown()
mark = len(spoken)
world.advance(181)
assert pump(lambda: main._app.ringing, timeout=3.0), "the timer did not ring"
assert pump(lambda: 'The timer "tea" is done.' in spoken[mark:]), spoken[mark:]
assert plays and plays[-1] == main._app.sound_path("timer"), plays
assert pump(lambda: main._timer_ms == main.RING_TICK_MS), "the tick did not speed up"
assert top_windows() <= before, "ringing opened a window"
assert frame.IsShown() == main_shown, "ringing showed the main window"
print("OK ring")

bar, _focus = open_bar()                          # the hotkey isn't a key press here
assert main._app.ringing
say_to(bar, "stop", 'Stopped the timer "tea".')
assert not main._app.ringing and stops and stops[-1] == plays[-1]
say_to(bar, "stop", 'Already stopped: the timer "tea".')
assert main._app.schedule.timers() == []
assert pump(lambda: main._timer_ms == main.TICK_MS), "the tick did not slow down"
print("OK stop")

# --------------------------------------------------------------------------- #
# A key stops the next ring; "snooze" right after still snoozes it
# --------------------------------------------------------------------------- #
say_to(bar, "timer 1 minute", "Timer, 1 minute, started.")
close_bar(bar)
world.advance(61)
assert pump(lambda: main._app.ringing, timeout=3.0), "the second timer did not ring"
world.advance(3)
world.press_key()
mark = len(spoken)
assert pump(lambda: not main._app.ringing, timeout=3.0), "a key press did not stop it"
assert pump(lambda: "Stopped the timer for 1 minute." in spoken[mark:], timeout=3.0), \
    spoken[mark:]
bar, _focus = open_bar()
say_to(bar, "snooze", lambda s: s.startswith("Snoozed the timer for 1 minute for 5 minutes, "
                                             "until "))
assert [t["seconds"] for t in main._app.schedule.timers()] == [60]
say_to(bar, "snooze", "There is nothing to snooze.")
close_bar(bar)
print("OK key_and_snooze")

# --------------------------------------------------------------------------- #
# The Preferences page
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Timer & Alarm")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "the page was not created"
tui = sys.modules["timer_alarm_ui"]
kinds = [type(c).__name__ for c in panel.GetChildren()]
assert kinds == ["StaticText", "ListCtrl", "Button", "Button", "StaticText", "Choice", "Button",
                 "StaticText", "Choice", "Button", "StaticText", "Choice", "StaticText", "Choice",
                 "StaticText", "TextCtrl"], kinds
children = list(panel.GetChildren())
for index, child in enumerate(children):
    if isinstance(child, (wx.ListCtrl, wx.Choice, wx.TextCtrl)):
        label = children[index - 1]
        assert isinstance(label, wx.StaticText), f"{type(child).__name__} has no label before it"
        assert child.GetName() == tui._plain(label.GetLabel()), (child.GetName(), label.GetLabel())
assert panel.list.GetName() == "Alarms and timers"
assert panel.choice_alarm_sound.GetName() == "Alarm sound"
assert panel.choice_timer_sound.GetName() == "Timer sound"
assert panel.choice_ring.GetStringSelection() == "3 minutes"
assert panel.choice_snooze.GetStringSelection() == "5 minutes"
assert not panel.txt_about.IsEditable() and "any key" in panel.txt_about.GetValue()
rows = [tuple(panel.list.GetItemText(i, col) for col in range(3))
        for i in range(panel.list.GetItemCount())]
assert rows[0] == ('Alarm "gang war"', "tomorrow, Saturday 26 September, 2:00 AM", "No"), rows
assert rows[1][0] == 'Alarm "olahraga"' and rows[2][0] == "Timer", rows
assert rows[2][1].endswith("left, until 10:49") or "left, until" in rows[2][1], rows
print("OK page")

# Browsing the list and the choices never moves the focus.
focus_checked = []
panel.list.SetFocus()
wx.Yield()
observable = wx.Window.FindFocus() is panel.list
for i in range(panel.list.GetItemCount()):
    panel.list.Select(i)
    panel.list.Focus(i)
    wx.Yield()
    now = wx.Window.FindFocus()
    if observable and now is not None:
        assert now is panel.list, f"focus left the list at row {i}"
focus_checked.append(observable)
for choice in (panel.choice_alarm_sound, panel.choice_ring):
    choice.SetFocus()
    wx.Yield()
    seen = wx.Window.FindFocus() is choice
    for i in range(choice.GetCount()):
        choice.SetSelection(i)
        fire(choice, wx.EVT_CHOICE)
        now = wx.Window.FindFocus()
        if seen and now is not None:
            assert now is choice, "focus left a choice"
    focus_checked.append(seen)
print(f"OK browse ({focus_note(all(focus_checked))})")

# Test plays three seconds, then stops (the player is a fake).
tones = [i for i, c in enumerate(panel._choices) if c[0] == "tone:alarm"]
panel.choice_alarm_sound.SetSelection(tones[0])
fire(panel.btn_test_alarm, wx.EVT_BUTTON)
assert test_plays == [os.path.join(EXT_DIR, "sounds", "timer_alarm_alarm.wav")], test_plays
assert pump(lambda: test_stops == test_plays, timeout=5.0), test_stops
print("OK test_sound")


class _Key:
    def __init__(self, code):
        self.code = code
        self.skipped = False

    def GetKeyCode(self):
        return self.code

    def Skip(self):
        self.skipped = True


confirms, answers = [], [False, True]
tui._confirm = lambda parent, message, title: confirms.append(message) or answers.pop(0)
panel.list.Select(0)
panel.list.Focus(0)
panel._on_list_key(_Key(wx.WXK_DELETE))           # Delete, answered No
assert confirms == ['Remove Alarm "gang war"?'], confirms
assert len(main._app.schedule.alarms()) == 2
mark = len(spoken)
panel._on_list_key(_Key(wx.WXK_DELETE))           # Delete, answered Yes
assert pump(lambda: "Removed." in spoken[mark:]), spoken[mark:]
assert [a["label"] for a in main._app.schedule.alarms()] == ["olahraga"]
assert [i["label"] for i in core.api.load_data(store.DATA_KEY)["items"] if i["kind"] == "alarm"] \
    == ["olahraga"]
assert panel.list.GetItemText(0, 0) == 'Alarm "olahraga"'
other = _Key(ord("A"))
panel._on_list_key(other)
assert other.skipped
mark = len(spoken)
fire(panel.btn_stop, wx.EVT_BUTTON)
assert spoken[mark:] and spoken[mark].startswith("Nothing is ringing."), spoken[mark:]
print("OK remove")

panel.choice_ring.SetSelection(store.RING_CHOICES.index(5))
panel.choice_snooze.SetSelection(store.SNOOZE_CHOICES.index(10))
panel.choice_timer_sound.SetSelection([c[0] for c in panel._choices].index("tone:timer"))
prefs.OnApply(None)
settings = core.api.load_data(store.DATA_KEY)["settings"]
assert settings == {"alarm_sound": "tone:alarm", "timer_sound": "tone:timer", "ring_minutes": 5,
                    "snooze_minutes": 10}, settings
assert main._app.ring_seconds == 300
prefs.Destroy()
wx.Yield()
print("OK apply")

# --------------------------------------------------------------------------- #
# The Morning Briefing, and unloading
# --------------------------------------------------------------------------- #
main._app.add_alarm(parse.parse_alarm("at 14:00 gym", world.wall, ["en", "id"], "en"))
lines = []
bus.emit("on_briefing_collect", lines)
assert lines == ["You have an alarm at 14:00: gym."], lines
print("OK briefing")

timer = main._timer
em.unload_all_extensions()
assert not any(i.id.startswith("Timer and Alarm.") for i in core.commands.intents())
assert not timer.IsRunning()
lines = []
bus.emit("on_briefing_collect", lines)
assert lines == []
print("OK teardown")

assert not network_attempts, f"network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
