# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load Orbit through the real loader with real wxPython, against the real
Orbit server started on this computer (127.0.0.1, a port the system picks),
and play: the Preferences page (its labels and their order, Connect, the
status line, what is read aloud, the window's closing and logging out,
toggling without the focus moving, a transfer code, Apply), the game window
("Open Orbit": the Messages list and the Command field with their labels
first, the Settings button, walking by compass, Enter sends, another
player's words arrive without the focus or the selection moving, Up brings
back the last command, Escape hides it and stays connected), Aruna ("orbit
who", "orbit say ..."), with what is said landing in Last result, and
closing the window when the setting says to leave Orbit. Finally unloading.

Sounds, voices and the ambience are fakes (nothing is played or recorded),
speech is captured through on_before_speak and cancelled, and every
connection except to 127.0.0.1 fails. Run by tests/test_orbit_ui.py in a
separate process (conftest.py mocks wx in the pytest process) with APPDATA
pointing at a temporary folder. Prints one "OK" line per stage. Never run it
on a computer someone is using: it opens windows.
"""
import faulthandler
import functools
import logging
import os
import socket
import sys
import threading
import time
import types

faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")


def _watchdog():
    print("TIMEOUT: the Orbit check hung", flush=True)
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
_real_create_connection = socket.create_connection


def _local_only(address, *args, **kwargs):
    if address[0] not in ("127.0.0.1", "localhost", "::1"):
        network_attempts.append(address)
        raise OSError("only this computer in the UI check")
    return _real_create_connection(address, *args, **kwargs)


socket.create_connection = _local_only

problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    WATCHED = ("hariku_ext.orbit", "orbit", "core.commands", "core.voice",
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
import core.sounds
from core.events import bus

core.api.save_data("Core", {"onboarding_completed": True, "language": "en",
                            "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad"),
                            "aruna_keep_open": True, "aruna_sounds": False})
core.i18n.init("en")
core.sounds.play_sound = lambda path: True          # nothing is played

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

# The real server, on this computer, with its data in the temporary APPDATA.
sys.path.insert(0, SERVER_DIR)
import orbit_server  # noqa: E402
import orbit_ws  # noqa: E402

server_config = orbit_server.load_config(None, {
    "port": 0, "database": os.path.join(os.environ.get("APPDATA", "."), "orbit-check.db"),
    "hash_iterations": 1000, "tick_seconds": 0.1})
server = orbit_server.ServerThread(server_config).start()
URL = f"ws://127.0.0.1:{server.port}/orbit/ws"

from ui.main_window import MainWindow
frame = MainWindow(None, title="orbit check")
frame.heartbeat_timer.Stop()
frame.monitor_timer.Stop()
print("OK main_window")

import ui.command_bar as cb

focus_calls = []
cb.set_foreground = lambda hwnd: focus_calls.append(hwnd) or True
PREVIOUS = frame.GetHandle()
cb.foreground_window = lambda: PREVIOUS

# --------------------------------------------------------------------------- #
# Loading: actions without keys, "orbit ..." for Aruna, a Preferences page
# --------------------------------------------------------------------------- #
import core.extension_manager as em
import core.preferences
em.load_unpacked_extension(EXT_DIR)
assert "orbit" in em.LOADED_EXTENSIONS, f"Orbit did not load: {em.LOAD_ERRORS}"
main = em.LOADED_EXTENSIONS["orbit"]["module"]
ui = sys.modules["orbit_ui"]
for name, *_rest in main.ACTIONS:
    action = core.hotkeys.actions[f"Orbit.{name}"]
    assert action.default_keycode is None, f"Orbit.{name} has a default key"
assert core.commands.is_answer_action("Orbit.who") and not core.commands.is_answer_action("Orbit.open")
assert "Orbit.play" in {i.id for i in core.commands.intents()}
assert "Orbit" in core.preferences.get_all_panels()
print("OK load")


# --------------------------------------------------------------------------- #
# Fakes: sounds, voices, the ambience
# --------------------------------------------------------------------------- #
services = main._services
sounds, ambiences, voiced = [], [], []
services.play = lambda name, pan=0.0, acoustics=None: sounds.append(name) or True
settings_opened = []
services.open_settings = lambda: settings_opened.append(1)
reminders = []
services.add_reminder = lambda title, when: reminders.append((title, when)) or True
services.ambience = lambda name, volume: ambiences.append((name, volume))


def _fake_voice(text, voice, on_done):
    voiced.append((voice["id"], text))
    threading.Timer(0.05, on_done, [None]).start()
    return True


services.speak_voice = _fake_voice
services.voice_busy = lambda: False
VOICES = [{"id": "en-US-AvaNeural", "name": "Ava", "language": "en-US", "provider": "edge"},
          {"id": "en-GB-RyanNeural", "name": "Ryan", "language": "en-GB", "provider": "edge"}]
voice_module = sys.modules["orbit_speech"]
services.voice_for = lambda name, number=None: voice_module.pick_voice(name, VOICES, number=number)
services.voice_count = lambda: len(VOICES)
services.narrator_voice = lambda: None             # the narrator: core.voice.announce, captured below
services.voices = types.SimpleNamespace(refresh_in_background=lambda: None, forget=lambda: None,
                                        cached=lambda: {})
voice_module.READER_SECONDS_PER_CHAR = 0.001      # a quick "screen reader"
voice_module.READER_MIN_SECONDS = 0.05
main._settings.update({"server": URL, "name": "Rafli", "job": "pilot"})
main._save_settings()
print("OK fakes")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
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


def fire(ctrl, event_type):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    ctrl.GetEventHandler().ProcessEvent(evt)


def press_key(ctrl, code, hook=False):
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK if hook else wx.wxEVT_KEY_DOWN)
    key.SetKeyCode(code)
    key.SetEventObject(ctrl)
    target = ctrl.GetTopLevelParent() if hook else ctrl
    target.GetEventHandler().ProcessEvent(key)


def check_labels(parent, where):
    children = [c for c in parent.GetChildren() if not isinstance(c, wx.TopLevelWindow)]
    for index, child in enumerate(children):
        if isinstance(child, (wx.FilePickerCtrl, wx.DirPickerCtrl, wx.SpinCtrlDouble)):
            raise AssertionError(f"{where}: {type(child).__name__} is not allowed")
        if isinstance(child, (wx.TextCtrl, wx.Choice, wx.ListBox, wx.Slider)):
            if isinstance(child, wx.TextCtrl) and child.IsMultiLine() and not child.IsEditable():
                continue
            label = children[index - 1] if index else None
            assert isinstance(label, wx.StaticText), \
                f"{where}: {type(child).__name__} {child.GetName()!r} has no label before it"
            assert child.GetName() == ui._plain(label.GetLabel()), (where, child.GetName(),
                                                                     label.GetLabel())
    return [type(c).__name__ for c in children]


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


# --------------------------------------------------------------------------- #
# The Preferences page: Connect, the status line, Apply
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Orbit")
prefs.Show()
wx.Yield()
page = main._panel
assert page is not None and page.IsShown(), "the page was not created"
kinds = check_labels(page, "Preferences")
assert kinds == (["StaticText", "TextCtrl", "StaticText", "TextCtrl", "StaticText", "Choice",
                  "StaticText", "Button", "StaticText", "TextCtrl", "StaticText", "Choice",
                  "CheckBox", "CheckBox", "CheckBox", "CheckBox", "StaticText"]
                 + ["CheckBox"] * 7
                 + ["StaticText", "Choice", "StaticText", "Choice", "StaticText", "Choice", "CheckBox",
                    "CheckBox", "StaticText", "Slider", "CheckBox", "StaticText", "Slider", "CheckBox",
                    "StaticText", "TextCtrl", "StaticText", "Button", "StaticText", "TextCtrl",
                    "StaticText", "TextCtrl", "Button", "StaticText", "StaticText", "StaticText"]), kinds
assert page.ch_background.GetName() == "While the Orbit window is closed, read"
assert page.ch_reader.GetName() == "Read with"
assert page.ch_reader.GetStringSelection() == \
    "Mixed: talk and announcements in Hariku Voice, the rest by NVDA"
assert page.ch_close.GetStringSelection() == "Stay connected in the background"
assert page.txt_transfer.GetName() == "Transfer code" and not page.txt_transfer.IsEditable()
assert not page.btn_transfer.IsEnabled()                   # only while connected
assert page.txt_server.GetValue() == URL and page.txt_name.GetValue() == "Rafli"
assert page.txt_status.GetValue() == "Not connected." and page.btn_connect.GetLabel() == "&Connect"
assert page.txt_name.GetName() == "Character name (for your first visit)"
page.btn_connect.SetFocus()
wx.Yield()
observable = wx.Window.FindFocus() is page.btn_connect
fire(page.btn_connect, wx.EVT_BUTTON)
assert pump(lambda: page.txt_status.GetValue() == "Connected to Orbit as Rafli, Pilot.", 10), \
    page.txt_status.GetValue()
assert page.btn_connect.GetLabel() == "&Leave Orbit"
assert pump(lambda: page.btn_transfer.IsEnabled())
fire(page.btn_transfer, wx.EVT_BUTTON)
assert pump(lambda: len(page.txt_transfer.GetValue()) == 19, 10), page.txt_transfer.GetValue()
page.chk_speak.SetValue(False)
fire(page.chk_speak, wx.EVT_CHECKBOX)
assert not page.chk_read["read_say"].IsEnabled() and not page.chk_voices.IsEnabled()
assert not page.chk_speak_own.IsEnabled() and not page.chk_speak_names.IsEnabled()
page.chk_speak.SetValue(True)
fire(page.chk_speak, wx.EVT_CHECKBOX)
assert page.chk_speak_own.IsEnabled() and page.chk_speak_own.GetValue() and page.chk_speak_names.GetValue()
assert page.chk_speak_own.GetLabel() == "Spea&k my own lines in my character voice"
assert page.chk_speak_names.GetLabel() == "Say the speaker's name &before their words"
page.chk_speak_names.SetValue(False)
page.chk_read["read_moves"].SetValue(False)
page.txt_ignored.ChangeValue("Budi, Tono")
assert any(s == "Connected to Orbit." for s in spoken), spoken[-5:]
if observable:
    assert wx.Window.FindFocus() is page.btn_connect, "connecting moved the focus"
page.chk_ambience.SetValue(False)
fire(page.chk_ambience, wx.EVT_CHECKBOX)
assert not page.sld_volume.IsEnabled()
page.chk_ambience.SetValue(True)
fire(page.chk_ambience, wx.EVT_CHECKBOX)
page.sld_volume.SetValue(40)
prefs.OnApply(None)
saved = core.api.load_data("Orbit")
assert (saved["server"], saved["name"], saved["ambience_volume"], saved["ambience"]) == \
    (URL, "Rafli", 40, True), saved
assert (saved["read_moves"], saved["ignored"], saved["background"], saved["close_action"]) == \
    (False, ["Budi", "Tono"], "important", "stay"), saved
assert (saved["speak_own"], saved["speak_names"]) == (True, False), saved
account = core.api.load_data("OrbitAccounts")[URL]
assert account["joined"] and account["name"] == "Rafli" and len(account["secret"]) == 64
prefs.Destroy()
wx.Yield()
print(f"OK page ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# The game window
# --------------------------------------------------------------------------- #
core.hotkeys.actions["Orbit.open"].callback()
assert pump(lambda: main._frame is not None and main._frame.IsShown())
window = main._frame
panel = window.GetChildren()[0]
kinds = check_labels(panel, "the Orbit window")
assert kinds == ["StaticText", "ListBox", "StaticText", "TextCtrl", "Button", "Button", "Button", "Button",
                 "StaticText", "TextCtrl"], kinds
assert window.GetTitle() == "Orbit: Connected", window.GetTitle()
fire(window.btn_settings, wx.EVT_BUTTON)
assert settings_opened == [1]
assert window.btn_remind.GetLabel() == "&Remind me of the next event"
fire(window.btn_remind, wx.EVT_BUTTON)                   # asks the server what's coming, then sets one
assert pump(lambda: reminders, 10), main._client.messages[-3:]
assert reminders[0][0].startswith("Orbit: ")
assert window.txt_messages.GetName() == "Messages" and window.txt_command.GetName() == "Command"
assert window.txt_messages.IsEditable() is False and window.txt_messages.IsMultiLine()
assert len(window.lines()) == len(main._client.messages) > 0
focus_ok = pump(lambda: wx.Window.FindFocus() is window.txt_command, timeout=1.0)
assert pump(lambda: ambiences and ambiences[-1] == ("vent", 40)), ambiences[-3:]

def typed(text, expect):
    count = len(window.lines())
    window.txt_command.SetValue(text)
    fire(window.txt_command, wx.EVT_TEXT_ENTER)
    assert window.txt_command.GetValue() == ""
    assert pump(lambda: any(expect in line for line in window.lines()[count:])), \
        (text, window.lines()[-3:])


typed("go to the cantina", "The way to the Cantina: east, east, south, up, north, west, west.")
for step, place in (("e", "the Cargo Bay"), ("e", "the Service Corridor"), ("s", "the Lower Lift Lobby")):
    typed(step, f"to {place}.")
typed("up", "You go up to the Main Lift Lobby.")
for step, place in (("n", "the Promenade"), ("w", "the West Promenade"), ("w", "the Cantina")):
    typed(step, f"to {place}.")
assert "step_metal" in sounds and "lift_up" in sounds and ambiences[-1] == ("cantina", 40)
if focus_ok:
    assert wx.Window.FindFocus() is window.txt_command, "sending moved the focus"
press_key(window.txt_command, wx.WXK_UP)
assert window.txt_command.GetValue() == "w"
window.txt_command.ChangeValue("")
print(f"OK window ({focus_note(focus_ok)})")

# --------------------------------------------------------------------------- #
# Another player: their words arrive without the focus or the selection moving
# --------------------------------------------------------------------------- #
# Reading the Messages box: a new line keeps the reading place and the focus.
window.txt_messages.SetFocus()
reading = pump(lambda: wx.Window.FindFocus() is window.txt_messages, timeout=1.0)
window.txt_messages.SetSelection(0, 0)
sari = orbit_ws.WebSocketClient.connect(URL)
sari.send_json({"t": "hello", "v": 1, "lang": "en", "name": "Sari", "job": "engineer",
                "secret": "5a" * 32})
for step in ("e", "e", "s", "u", "n", "w", "w"):
    sari.send_json({"t": "cmd", "c": "move", "d": step})
sari.send_json({"t": "cmd", "c": "say", "a": "hello Rafli!"})
assert pump(lambda: window.lines()[-1] == "Sari says: hello Rafli!", 10), window.lines()[-3:]
if reading:
    assert window.txt_messages.GetSelection() == (0, 0), "a message moved the reading place"
    assert wx.Window.FindFocus() is window.txt_messages, "a message moved the focus"
window.txt_command.SetFocus()
assert pump(lambda: voiced and voiced[-1][1] == "hello Rafli!", 15), voiced[-3:]    # the words alone
assert voiced[-1][0] == voice_module.pick_voice("Sari", VOICES)["id"]
assert "say" in sounds and "arrive" in sounds
print("OK other_player")

# --------------------------------------------------------------------------- #
# Aruna: "orbit ..." typed into the real command bar
# --------------------------------------------------------------------------- #
core.hotkeys.actions["Hariku Core.command_bar"].callback()
assert pump(lambda: cb.current_bar() is not None), "Aruna did not open"
bar = cb.current_bar()
spoken.clear()
bar.txt_input.SetValue("orbit who")
fire(bar.txt_input, wx.EVT_TEXT_ENTER)
assert pump(lambda: "2 online: Rafli the pilot, in the Cantina; Sari the engineer, in the Cantina."
            in bar.txt_result.GetValue(), 10), (bar.txt_result.GetValue(), spoken[-3:])
bar.txt_input.SetValue("orbit say hi from Aruna")
fire(bar.txt_input, wx.EVT_TEXT_ENTER)
assert pump(lambda: "Sent." in bar.txt_result.GetValue(), 10), bar.txt_result.GetValue()


def sari_heard(text, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        message = sari.recv_json(timeout=0.2)
        if message and message.get("text") == text:
            return True
    return False


assert sari_heard("Rafli says: hi from Aruna"), "Sari didn't hear what was said through Aruna"
key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
key.SetKeyCode(wx.WXK_ESCAPE)
key.SetEventObject(bar.txt_input)
bar.GetEventHandler().ProcessEvent(key)
assert pump(lambda: cb.current_bar() is None), "Escape did not close Aruna"
print("OK aruna")

# --------------------------------------------------------------------------- #
# Escape hides the window; the game goes on
# --------------------------------------------------------------------------- #
window.show_and_focus()
wx.Yield()
press_key(window.txt_command, wx.WXK_ESCAPE, hook=True)
assert pump(lambda: not window.IsShown()), "Escape did not hide the window"
assert pump(lambda: ambiences[-1] == (None, None)), ambiences[-3:]
assert main._client.online()
# The hint waits its turn: Orbit says one line after another, and the answer
# to "who" from Aruna may still be being said.
assert pump(lambda: any(line.startswith("Orbit stays connected.") for line in spoken), 10), \
    spoken[-3:]
print("OK escape")

# --------------------------------------------------------------------------- #
# Closing the window when the setting says to leave Orbit
# --------------------------------------------------------------------------- #
main._settings["close_action"] = "leave"
window.show_and_focus()
wx.Yield()
window.Close()
assert pump(lambda: not window.IsShown()), "closing did not hide the window"
assert pump(lambda: not main._client.online() and main._client.conn is None), main._client.status
assert pump(lambda: server.call(lambda: server.server.game.online_count()) == 1, 10)   # Sari only
assert window.GetTitle() == "Orbit: Left", window.GetTitle()
print("OK leave")

# --------------------------------------------------------------------------- #
# Unloading
# --------------------------------------------------------------------------- #
sari.close()
em.unload_all_extensions()
assert not any(i.id.startswith("Orbit.") for i in core.commands.intents())
assert core.commands.aliases_for("Orbit.open") == []
assert main._frame is None
assert pump(lambda: server.call(lambda: server.server.game.online_count()) == 0, 10)
print("OK teardown")

server.stop()
assert not network_attempts, f"network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.RemoveIcon()
frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
