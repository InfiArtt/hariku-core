# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the real main window with real wxPython and use the command bar
(Ctrl+Alt+Backspace) through its action, as the global hotkey would: check its
labels and focus, type "gempa terbaru" and press Enter (the earthquake action
runs after the bar has closed and focus went back), a close call with its
"Did you mean …?" answered by Escape and then by Enter, a reminder read back
and saved with Enter again, an action that opens a dialog (the bar is gone
before it opens), the hotkey pressed again without Voice Control and with a
fake one (what it "hears" runs), and Escape closing the bar.

The actions are fakes named like the real ones (the earthquake extension
needs the network). Giving the focus back to the previous window is recorded
instead of done, speech is captured through on_before_speak, and urlopen is
blocked. Nothing is recorded from a microphone.

Run by tests/test_command_bar_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder. Prints one "OK" line per stage. Never run it on a computer
someone is using: it opens windows.
"""
import faulthandler
import functools
import logging
import os
import sys
import threading
import time
import traceback

faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the command bar check hung", flush=True)
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
    WATCHED = ("core.commands", "core.voice", "core.speech", "core.hotkeys",
               "core.quick_reminder", "core.reminders", "ui.command_bar", "ui.main_window")

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
import core.reminders
from core.events import bus

# The first stages check the bar that closes before every action (as in core
# 2.7); "Keep Aruna open" and Aruna's sounds (core 2.8) are checked at the end.
core.api.save_data("Core", {"onboarding_completed": True, "language": "en",
                            "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad"),
                            "aruna_keep_open": False, "aruna_sounds": False})

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

from ui.main_window import MainWindow
frame = MainWindow(None, title="command bar check")
frame.heartbeat_timer.Stop()
frame.monitor_timer.Stop()
print("OK main_window")

import ui.command_bar as cb

# Giving the focus back is recorded, not done: on a CI runner the "previous
# window" is whatever happens to be in front.
focus_calls = []
cb.set_foreground = lambda hwnd: focus_calls.append(hwnd) or True
PREVIOUS = frame.GetHandle()
cb.foreground_window = lambda: PREVIOUS

# --- The action and the menu ------------------------------------------------------------------
action = core.hotkeys.actions["Hariku Core.command_bar"]
assert (action.default_keycode, action.default_ctrl, action.default_alt, action.default_shift,
        action.default_win, action.default_global) == (wx.WXK_BACK, True, True, False, False,
                                                       True)
assert action.description == "Open Aruna: type or say a command", action.description
assert cb.hotkey_label() == "Ctrl + Alt + Backspace", cb.hotkey_label()
assert frame.item_command_bar.GetItemLabelText() == "Aruna... (Ctrl + Alt + Backspace)", \
    frame.item_command_bar.GetItemLabelText()
assert "Hariku Core.speak_time" in core.hotkeys.actions
print("OK action")

# --- Fake actions named like the real ones ------------------------------------------------------
ran = []


def speak_latest():
    ran.append(("Earthquakes.speak_latest", cb.current_bar() is None))
    core.speech.speak("M 5.2, 30 km southwest of Ambon.")


opened_dialogs = []


def show_recent():
    ran.append(("Earthquakes.show_recent", cb.current_bar() is None))
    dlg = wx.Dialog(frame, title="Recent earthquakes")
    wx.CallLater(400, lambda: opened_dialogs.append(dlg.IsShown()) or dlg.EndModal(wx.ID_OK))
    dlg.ShowModal()
    dlg.Destroy()


import core.speech
core.hotkeys.register_action("Earthquakes", "speak_latest",
                             "Speak the latest earthquake from BMKG", None, False, speak_latest)
core.hotkeys.register_action("Earthquakes", "show_recent",
                             "Open the list of recent earthquakes", None, False, show_recent)
core.hotkeys.register_action("Weather", "speak_current_weather", "Speak the current weather",
                             None, False, lambda: ran.append(("Weather", True)))


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
    bar.txt_input.SetValue(text)          # sends EVT_TEXT, as typing does


def press_enter(bar):
    fire(bar.txt_input, wx.EVT_TEXT_ENTER)


def press_escape(bar):
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_ESCAPE)
    key.SetEventObject(bar.txt_input)
    bar.GetEventHandler().ProcessEvent(key)


def press_hotkey():
    """What RegisterHotKey's WM_HOTKEY leads to: the action's callback."""
    core.hotkeys.actions["Hariku Core.command_bar"].callback()


def open_bar():
    press_hotkey()
    assert pump(lambda: cb.current_bar() is not None), "the command bar did not open"
    bar = cb.current_bar()
    pump(lambda: wx.Window.FindFocus() is bar.txt_input, timeout=1.0)
    return bar, wx.Window.FindFocus() is bar.txt_input


def plain(label):
    return " ".join(label.replace("&&", "\0").replace("&", "").replace("\0", "&")
                    .strip().rstrip(":").split())


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


# --- The bar: labels, focus, always on top ------------------------------------------------------
bar, focus_ok = open_bar()
assert bar.GetTitle() == "Aruna", bar.GetTitle()
assert bar.GetWindowStyleFlag() & wx.STAY_ON_TOP
# Nobody's owned window: an owned one would show on the main window's virtual
# desktop and bring the hidden main window along.
assert bar.GetWindowStyleFlag() & wx.DIALOG_NO_PARENT and bar.GetParent() is None
children = list(bar.GetChildren())
kinds = [type(c).__name__ for c in children]
assert kinds == ["StaticText", "TextCtrl", "StaticText", "TextCtrl", "StaticText", "TextCtrl",
                 "Button", "Button"], kinds
for index, child in enumerate(children):
    if isinstance(child, wx.TextCtrl):
        assert isinstance(children[index - 1], wx.StaticText)
        assert child.GetName() == plain(children[index - 1].GetLabel()), child.GetName()
assert bar.txt_input.GetName() == "Say or type a command"
assert bar.txt_result.GetName() == "Last result"
assert bar.txt_result.IsMultiLine() and not bar.txt_result.IsEditable()
assert not bar.txt_status.IsEditable()
assert not bar.btn_listen.IsShown(), "Listen shows without Voice Control"
assert "Voice Control" in bar.txt_status.GetValue()
if focus_ok:
    assert wx.Window.FindFocus() is bar.txt_input
print(f"OK bar ({focus_note(focus_ok)})")

# --- A command: the bar closes, focus goes back, then the action runs ---------------------------
spoken.clear()
type_text(bar, "gempa terbaru")
press_enter(bar)
assert pump(lambda: ran), "the earthquake action did not run"
assert ran == [("Earthquakes.speak_latest", True)], ran          # the bar was already gone
assert cb.current_bar() is None
assert focus_calls == [PREVIOUS], focus_calls
assert pump(lambda: "M 5.2, 30 km southwest of Ambon." in spoken), spoken
print("OK command")

# --- A close call: Escape says no and keeps the bar; Enter again says yes ------------------------
ran.clear()
focus_calls.clear()
bar, focus_ok = open_bar()
spoken.clear()
type_text(bar, "Tua-tahari ini.")
press_enter(bar)
assert spoken == ["Did you mean: Speak the current weather?"], spoken
assert bar.txt_result.GetValue() == spoken[-1]
press_escape(bar)
assert spoken[-1] == "OK, cancelled." and cb.current_bar() is bar and not ran
press_enter(bar)                          # asks again
assert spoken[-1] == "Did you mean: Speak the current weather?"
press_enter(bar)                          # Enter again: yes
assert pump(lambda: ran), "the weather action did not run"
assert ran == [("Weather", True)] and cb.current_bar() is None
print(f"OK did_you_mean ({focus_note(focus_ok)})")

# --- A reminder: read back, Enter again saves ---------------------------------------------------
ran.clear()
bar, focus_ok = open_bar()
spoken.clear()
type_text(bar, "remind me to take medicine tomorrow at 8 am")
press_enter(bar)
assert spoken and spoken[-1].startswith("Take medicine, ") and spoken[-1].endswith("Save?"), \
    spoken
assert core.reminders.load_reminders() == []
if focus_ok:
    assert wx.Window.FindFocus() is bar.txt_input, "the read-back moved focus"
press_enter(bar)
assert pump(lambda: cb.current_bar() is None), "the bar stayed open after saving"
saved = core.reminders.load_reminders()
assert [(r["title"], r["time"]) for r in saved] == [("Take medicine", "08:00")], saved
assert "Reminder saved." in spoken, spoken
print(f"OK reminder ({focus_note(focus_ok)})")

# --- An action that opens a dialog opens it as usual, after the bar has closed -------------------
ran.clear()
bar, _focus = open_bar()
type_text(bar, "recent earthquakes")
press_enter(bar)
assert pump(lambda: opened_dialogs, timeout=8.0), "the dialog did not open"
assert ran == [("Earthquakes.show_recent", True)] and opened_dialogs == [True]
print("OK dialog_action")

# --- The hotkey again: without Voice Control it says how to get it -------------------------------
bar, _focus = open_bar()
spoken.clear()
press_hotkey()
assert spoken and spoken[-1].startswith("Voice Control isn't installed"), spoken
assert cb.current_bar() is bar
print("OK no_voice_control")

# --- With a (fake) recogniser: the hotkey listens, what is heard runs ----------------------------
listening = []


def fake_start(on_event):
    listening.append(on_event)

    def hear():
        on_event("listening", None)
        on_event("recognising", None)
        on_event("text", "Gampak terbaru.")      # as whisper tiny heard "gempa terbaru"

    wx.CallLater(200, hear)
    return True


core.commands.register_listener(fake_start, lambda discard=False: None, lambda: True,
                                lambda: False, name="Fake")
bar.Destroy()
cb._bar = None
ran.clear()
bar, _focus = open_bar()
assert bar.btn_listen.IsShown()
press_hotkey()                                   # pressed again: listen
assert listening, "the hotkey did not start listening"
assert pump(lambda: ran), "what was heard did not run"
assert ran == [("Earthquakes.speak_latest", True)], ran
core.commands.unregister_listener()
print("OK voice")

# --- Escape closes the bar and gives the focus back -----------------------------------------------
focus_calls.clear()
bar, _focus = open_bar()
type_text(bar, "something")
press_escape(bar)
assert pump(lambda: cb.current_bar() is None), "Escape did not close the bar"
assert focus_calls == [PREVIOUS], focus_calls
print("OK escape")

# --- "What time is it" is answered ---------------------------------------------------------------
bar, _focus = open_bar()
spoken.clear()
type_text(bar, "what time is it")
press_enter(bar)
assert pump(lambda: any(s.startswith("It's ") for s in spoken)), spoken
print("OK time")

# --- Core 2.8: Aruna stays open after an answer, says it's thinking, plays its sounds ------------
import core.sounds
played = []
core.sounds.play_internal_sound = played.append
core.commands.save_bar_settings(True, True)
cb.current_bar() and cb.current_bar().close(restore=False)
ran.clear()
focus_calls.clear()
bar, focus_ok = open_bar()
spoken.clear()
type_text(bar, "gempa terbaru")
press_enter(bar)
assert bar.txt_status.GetValue() == "Aruna is thinking...", bar.txt_status.GetValue()
assert pump(lambda: ran), "the earthquake action did not run"
assert ran == [("Earthquakes.speak_latest", False)], ran         # the bar was still open
assert pump(lambda: bar.txt_result.GetValue() == "M 5.2, 30 km southwest of Ambon."),     bar.txt_result.GetValue()
assert cb.current_bar() is bar and focus_calls == []
assert bar.txt_status.GetValue().startswith("Aruna answered."), bar.txt_status.GetValue()
assert pump(lambda: played == ["aruna_send.wav", "aruna_reply.wav"]), played
if focus_ok:
    assert wx.Window.FindFocus() is bar.txt_input, "the answer moved focus"
# The next command replaces the last one; one that opens a window still closes the bar.
assert bar.txt_input.GetStringSelection() == "gempa terbaru"
type_text(bar, "recent earthquakes")
opened_dialogs.clear()
press_enter(bar)
assert pump(lambda: opened_dialogs, timeout=8.0), "the dialog did not open"
assert ("Earthquakes.show_recent", True) in ran and cb.current_bar() is None
# A saved reminder keeps it open too.
bar, focus_ok = open_bar()
type_text(bar, "remind me to drink water tomorrow at 9 am")
press_enter(bar)
press_enter(bar)
assert pump(lambda: any(r["title"] == "Drink water" for r in core.reminders.load_reminders()))
pump(lambda: False, timeout=0.3)
assert cb.current_bar() is bar and bar.txt_input.GetValue() == ""
assert bar.txt_status.GetValue().startswith("Aruna answered.")
press_escape(bar)
assert pump(lambda: cb.current_bar() is None), "Escape did not close the bar"
print(f"OK keep_open ({focus_note(focus_ok)})")

# --- Hariku hidden in the tray: Aruna opens alone, the main window stays hidden --------------------
frame.Show()
pump(lambda: frame.IsShown(), timeout=2.0)
frame.Hide()                                  # what "Minimize to tray" does
pump(lambda: not frame.IsShown(), timeout=2.0)
bar, _focus = open_bar()
pump(lambda: False, timeout=0.5)
assert bar.IsShown() and not frame.IsShown(), "opening Aruna showed the hidden main window"
type_text(bar, "what time is it")
press_enter(bar)
pump(lambda: False, timeout=0.5)
assert not frame.IsShown(), "a command showed the hidden main window"
press_escape(bar)
assert pump(lambda: cb.current_bar() is None)
assert not frame.IsShown()
print("OK hidden_main_window")

# --- Core 2.9: a command with content, asked about, then done; one that acts after closing --------
noted, typed_into = [], []
core.commands.add_intent(
    "Notes.add", ["catat {text}", "note {text}"],
    lambda request: core.commands.Reply(f"Note \"{request.text}\"?",
                                        confirm=lambda: noted.append(request.text) or "Noted."),
    title="Notes")
core.commands.add_intent(
    "Dictation.type", ["type {text}"],
    lambda request: core.commands.Reply(then=lambda: typed_into.append(
        (request.text, cb.current_bar() is None))), title="Dictation")
focus_calls.clear()
bar, focus_ok = open_bar()
spoken.clear()
type_text(bar, "Note: buy Palm Sugar.")
press_enter(bar)
assert spoken[-1] == 'Note "buy Palm Sugar"?', spoken
assert bar.txt_status.GetValue().startswith("Aruna asks"), bar.txt_status.GetValue()
if focus_ok:
    assert wx.Window.FindFocus() is bar.txt_input, "the question moved focus"
press_enter(bar)                                   # Enter again: yes
assert pump(lambda: noted == ["buy Palm Sugar"]), noted
assert pump(lambda: spoken[-1] == "Noted."), spoken
assert cb.current_bar() is bar and bar.txt_input.GetValue() == ""
type_text(bar, "type Hello there")
press_enter(bar)
assert pump(lambda: typed_into), "the intent's then() did not run"
assert typed_into == [("Hello there", True)], typed_into      # after the bar had closed
assert focus_calls == [PREVIOUS], focus_calls
core.commands.remove_intent("Notes.add")
core.commands.remove_intent("Dictation.type")
print(f"OK intents ({focus_note(focus_ok)})")

# --- Core 2.9: in the background (the wake phrase): no focus taken, closes by itself --------------
focus_calls.clear()
frame.Show()
frame.Raise()
pump(lambda: False, timeout=0.3)
bar = cb.open_command_bar(background=True, listen=False)
pump(lambda: bar.IsShown(), timeout=2.0)
assert bar.IsShown() and bar._background and not bar.IsActive(), "Aruna took the focus"
spoken.clear()
bar.submit("what time is it", source="voice")
assert pump(lambda: any(s.startswith("It's ") for s in spoken), timeout=5), spoken
assert pump(lambda: cb.current_bar() is None, timeout=8), "Aruna didn't close by itself"
assert focus_calls == [], focus_calls                    # nothing to give the focus back to
frame.Hide()
pump(lambda: not frame.IsShown(), timeout=2.0)
print("OK background")

# --- Nothing went wrong along the way -------------------------------------------------------------
assert not network_attempts, f"network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
