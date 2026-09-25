# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load Calculator & Converter through the real loader with real wxPython and
ask the real Aruna (the command bar): "25 x 4" and "times two" answered in
Last result with the bar still open, "2 feet in inches", a currency whose
rates come in on a worker thread ("Aruna is thinking...", then the answer),
and "copy the result". Then its Preferences page inside the real Preferences
dialog: the labels and their order (each label right before its control),
the choices, toggling without the focus moving, and Apply. Finally unloading.

The rates are a fake (nothing is fetched), the clipboard is a fake, speech is
captured through on_before_speak and cancelled. Run by
tests/test_calculator_ui.py in a separate process (conftest.py mocks wx in the
pytest process) with APPDATA pointing at a temporary folder. Prints one "OK"
line per stage. Never run it on a computer someone is using: it opens windows.
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
EXT_DIR = os.path.join(ROOT, "extensions", "calculator")


def _watchdog():
    print("TIMEOUT: the calculator check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(150, _watchdog)
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
    WATCHED = ("hariku_ext.calculator", "calculator_", "core.commands", "core.voice",
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
frame = MainWindow(None, title="calculator check")
frame.heartbeat_timer.Stop()
frame.monitor_timer.Stop()
print("OK main_window")

import ui.command_bar as cb

focus_calls = []
cb.set_foreground = lambda hwnd: focus_calls.append(hwnd) or True
PREVIOUS = frame.GetHandle()
cb.foreground_window = lambda: PREVIOUS

# --------------------------------------------------------------------------- #
# Loading: actions without keys that only answer, a command with content, a page
# --------------------------------------------------------------------------- #
import core.extension_manager as em
import core.preferences
em.load_unpacked_extension(EXT_DIR)
assert "calculator" in em.LOADED_EXTENSIONS, f"Calculator did not load: {em.LOAD_ERRORS}"
main = em.LOADED_EXTENSIONS["calculator"]["module"]
money = sys.modules["calculator_money"]
for name in ("copy_result", "last_result", "random_number", "flip_coin", "roll_die"):
    action_id = f"Calculator.{name}"
    action = core.hotkeys.actions[action_id]
    assert action.default_keycode is None, f"{action_id} has a default key"
    assert core.commands.is_answer_action(action_id), action_id
[intent] = [i for i in core.commands.intents() if i.id == "Calculator.calculate"]
assert intent.matcher is not None and intent.patterns == []
assert "Calculator & Converter" in core.preferences.get_all_panels()
print("OK load")

# --------------------------------------------------------------------------- #
# Fakes: the rates (after a moment, on the worker thread) and the clipboard
# --------------------------------------------------------------------------- #
ROWS = [{"date": "2026-09-25", "base": "EUR", "quote": "IDR", "rate": 20405},
        {"date": "2026-09-25", "base": "EUR", "quote": "USD", "rate": 1.1394}]
fetches = []


def _fake_fetch():
    fetches.append(threading.current_thread().name)
    time.sleep(0.4)
    import datetime
    return money.parse_rates(ROWS, datetime.datetime.now())


copied = []
main._calculator.rates = money.RateBook(fetch=_fake_fetch)
main._calculator._copy = copied.append
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


def result(bar):
    return bar.txt_result.GetValue()


def ask(bar, text, in_result, timeout=10.0):
    """Type a command, press Enter, wait until Last result holds `in_result`."""
    bar.txt_input.SetValue(text)
    fire(bar.txt_input, wx.EVT_TEXT_ENTER)
    ok = pump(lambda: in_result in result(bar), timeout)
    assert ok, f"{text!r}: Last result has no {in_result!r}: {result(bar)!r} (said {spoken[-5:]})"


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


# --------------------------------------------------------------------------- #
# Sums and units: answered at once, Aruna stays open
# --------------------------------------------------------------------------- #
bar, focus_ok = open_bar()
ask(bar, "25 x 4", "25 times 4 = 100.")
assert cb.current_bar() is bar and focus_calls == []
ask(bar, "times two", "100 times 2 = 200.")
ask(bar, "2 feet in inches", "2 feet = 24 inches.")
ask(bar, "what's 15% of 80", "15% of 80 = 12.")
if focus_ok:
    assert wx.Window.FindFocus() is bar.txt_input, "an answer moved the focus"
print(f"OK sums ({focus_note(focus_ok)})")

# --------------------------------------------------------------------------- #
# A currency: the rates come on a worker thread while Aruna is thinking
# --------------------------------------------------------------------------- #
bar.txt_input.SetValue("100 dollars to rupiah")
fire(bar.txt_input, wx.EVT_TEXT_ENTER)
assert bar.txt_status.GetValue() == "Aruna is thinking...", bar.txt_status.GetValue()
assert pump(lambda: "100 US dollars = 1,790,855 rupiah, at the rates of 25 September"
            in result(bar), timeout=10.0), (result(bar), spoken[-5:])
assert fetches and fetches[0] != threading.main_thread().name, fetches
ask(bar, "50 dollars to rupiah", "50 US dollars = 895,427 rupiah")
assert len(fetches) == 1, fetches                         # fresh: no second fetch
print("OK currency")

ask(bar, "copy the result", "Copied: 895,427.")
assert copied == ["895,427"], copied
assert cb.current_bar() is bar
press_escape(bar)
assert pump(lambda: cb.current_bar() is None), "Escape did not close Aruna"
print("OK copy")

# --------------------------------------------------------------------------- #
# The Preferences page
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Calculator & Converter")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "the page was not created"
ui = sys.modules["calculator_ui"]
children = list(panel.GetChildren())
kinds = [type(c).__name__ for c in children]
assert kinds == ["StaticText", "Choice", "StaticText", "Choice", "StaticText", "Choice",
                 "CheckBox", "StaticText", "StaticText"], kinds
for index, child in enumerate(children):
    if isinstance(child, wx.Choice):
        label = children[index - 1]
        assert isinstance(label, wx.StaticText), f"{type(child).__name__} has no label before it"
        assert child.GetName() == ui._plain(label.GetLabel()), (child.GetName(), label.GetLabel())
assert [c.GetLabel() for c in children if isinstance(c, wx.StaticText)][:3] == \
    ["Home currency:", "Decimal places:", "Data sizes (KB, MB, GB):"]
assert panel.cho_home.GetString(panel.cho_home.GetSelection()).startswith("Automatic")
assert panel.cho_decimals.GetCount() == 8
assert panel.cho_data.GetSelection() == 0 and not panel.chk_copy.GetValue()
labels = [c.GetLabel() for c in children if isinstance(c, wx.StaticText)]
assert any("frankfurter.dev" in label for label in labels), labels

panel.cho_home.SetFocus()
wx.Yield()
observable = wx.Window.FindFocus() is panel.cho_home
homes = [value for value, _label in panel._homes]
panel.cho_home.SetSelection(homes.index("SGD"))
fire(panel.cho_home, wx.EVT_CHOICE)
panel.cho_decimals.SetSelection(3)                        # "2"
panel.cho_data.SetSelection(1)                            # 1000 per step
panel.chk_copy.SetValue(True)
fire(panel.chk_copy, wx.EVT_CHECKBOX)
if observable:
    assert wx.Window.FindFocus() is panel.cho_home, "focus moved"
prefs.OnApply(None)
saved = core.api.load_data("Calculator")
assert saved == {"home": "SGD", "decimals": 2, "data": 1000, "auto_copy": True}, saved
assert main._calculator.settings == saved and main._calculator.home() == "SGD"
prefs.Destroy()
wx.Yield()
print(f"OK page ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# Unloading
# --------------------------------------------------------------------------- #
em.unload_all_extensions()
assert not any(i.id.startswith("Calculator.") for i in core.commands.intents())
assert core.commands.aliases_for("Calculator.copy_result") == []
print("OK teardown")

assert not network_attempts, f"network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

# The tray icon goes before the frame, or wx can crash while tearing down.
frame.tb_icon.RemoveIcon()
frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
