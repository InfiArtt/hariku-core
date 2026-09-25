# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Dropbox extension through the real loader with real wxPython: its
Preferences page inside the real Preferences dialog (the labels and their
order, "not set up in this build", connected with the account's name and
email, the Code field that appears for a pasted code, Apply, Disconnect,
nothing moving the focus), then Aruna: "Dropbox status" answered in Last
result, and "copy link" / "copy the link to this" going back to the window
the user was in (not File Explorer: it says so; a pretend File Explorer: the
link is copied and said). Finally unloading.

Dropbox is a fake (no App key, no sign-in, no network), File Explorer's
answer and the clipboard are fakes, speech is captured through
on_before_speak and cancelled. Run by tests/test_dropbox_ui.py in a separate
process (conftest.py mocks wx in the pytest process) with APPDATA pointing
at a temporary folder. Prints one "OK" line per stage. Never run it on a
computer someone is using: it opens windows.
"""
import faulthandler
import functools
import logging
import os
import socket
import sys
import tempfile
import threading
import time
import types

faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
EXT_DIR = os.path.join(ROOT, "extensions", "dropbox")


def _watchdog():
    print("TIMEOUT: the Dropbox check hung", flush=True)
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
    WATCHED = ("hariku_ext.dropbox", "dropbox", "core.commands", "core.voice",
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
played = []
core.sounds.play_sound = lambda path: played.append(path) or True     # nothing is played

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

from ui.main_window import MainWindow
frame = MainWindow(None, title="dropbox check")
frame.heartbeat_timer.Stop()
frame.monitor_timer.Stop()
print("OK main_window")

import ui.command_bar as cb

focus_calls = []
cb.set_foreground = lambda hwnd: focus_calls.append(hwnd) or True
PREVIOUS = frame.GetHandle()
cb.foreground_window = lambda: PREVIOUS

# --------------------------------------------------------------------------- #
# Loading: actions without keys, "copy link to ..." for Aruna, a page
# --------------------------------------------------------------------------- #
import core.extension_manager as em
import core.preferences
em.load_unpacked_extension(EXT_DIR)
assert "dropbox" in em.LOADED_EXTENSIONS, f"Dropbox did not load: {em.LOAD_ERRORS}"
main = em.LOADED_EXTENSIONS["dropbox"]["module"]
engines = sys.modules["dropbox_engine"]
explorer = sys.modules["dropbox_explorer"]
for name, *_rest in main.ACTIONS:
    action = core.hotkeys.actions[f"Dropbox.{name}"]
    assert action.default_keycode is None, f"Dropbox.{name} has a default key"
assert core.commands.is_answer_action("Dropbox.status")
assert not core.commands.is_answer_action("Dropbox.copy_link")
assert "Dropbox.link" in {i.id for i in core.commands.intents()}
assert "Dropbox" in core.preferences.get_all_panels()
engine = main._engine
assert engine.state in (engines.NOT_SET_UP, engines.DISCONNECTED), engine.state
assert engine.client is None and not engine._threads      # nothing runs without a sign-in
print("OK load")


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


def plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


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
            assert child.GetName() == plain(label.GetLabel()), (where, child.GetName(),
                                                                 label.GetLabel())
    return [type(c).__name__ for c in children]


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


PAGE_KINDS = ["StaticText", "TextCtrl", "Button", "StaticText", "TextCtrl", "Button",
              "StaticText", "TextCtrl", "CheckBox", "CheckBox", "CheckBox", "CheckBox",
              "CheckBox", "StaticText", "StaticText"]

# --------------------------------------------------------------------------- #
# The page in a build without an App key
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

engine.app_key = ""
engine.state = engines.NOT_SET_UP
prefs = PreferencesDialog(frame, select_tab="Dropbox")
prefs.Show()
wx.Yield()
page = main._panel
assert page is not None and page.IsShown(), "the page was not created"
assert check_labels(page, "Preferences") == PAGE_KINDS
assert page.txt_account.GetName() == "Dropbox account"
assert page.txt_folder.GetName() == "Dropbox folder on this computer"
assert page.txt_code.GetName() == "Code from Dropbox"
assert page.txt_account.GetValue() == \
    "Dropbox isn't set up in this build of Hariku: it has no Dropbox App key.", \
    page.txt_account.GetValue()
assert not page.btn_connect.IsEnabled() and page.btn_connect.GetLabel() == "&Connect Dropbox"
assert not page.txt_code.IsShown() and not page.lbl_code.IsShown() and not page.btn_code.IsShown()
print("OK page_not_set_up")

# --------------------------------------------------------------------------- #
# Connected (a pretend account): the name and email, Disconnect
# --------------------------------------------------------------------------- #
FOLDER = tempfile.mkdtemp(prefix="Dropbox check ")
with open(os.path.join(FOLDER, "laporan.pdf"), "w", encoding="utf-8") as f:
    f.write("x")
links = []


def _fake_link(path):
    links.append(path)
    return "https://www.dropbox.com/scl/fi/check" + path


fake_client = types.SimpleNamespace(transport=types.SimpleNamespace(closed=False,
                                                                     close=lambda: None),
                                    path_root=None, shared_link=_fake_link,
                                    revoke=lambda: None)


def pretend_connected():
    engine.app_key = "ui-check-key"
    engine.client = fake_client
    engine.account = {"id": "dbid:me", "name": "Rafli", "email": "rafli@example.com",
                      "business": False}
    engine.state = engines.CONNECTED
    engine.folder = FOLDER
    engine.folder_state = engines.FOLDER_OK


pretend_connected()
main._refresh_pages()
assert page.txt_account.GetValue() == "Connected as Rafli (rafli@example.com).", \
    page.txt_account.GetValue()
assert page.btn_connect.GetLabel() == "&Disconnect Dropbox" and page.btn_connect.IsEnabled()
assert page.txt_folder.GetValue() == FOLDER
page.btn_connect.SetFocus()
wx.Yield()
observable = wx.Window.FindFocus() is page.btn_connect
print(f"OK page_connected ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# Signing in with a pasted code: the Code field appears after its label
# --------------------------------------------------------------------------- #
given = []
engine.give_code = given.append
engine.state = engines.CODE_NEEDED
main._refresh_pages()
assert page.txt_code.IsShown() and page.lbl_code.IsShown() and page.btn_code.IsShown()
assert check_labels(page, "Preferences with the Code field") == PAGE_KINDS
assert page.btn_connect.GetLabel() == "Ca&ncel signing in"
assert page.txt_account.GetValue().startswith("Sign in in the browser, then copy the code")
page.txt_code.SetValue("  CODE-123 ")
fire(page.btn_code, wx.EVT_BUTTON)
fire(page.txt_code, wx.EVT_TEXT_ENTER)
assert given == ["CODE-123", "CODE-123"], given
if observable:
    assert wx.Window.FindFocus() is page.btn_connect, "the Code field took the focus"
pretend_connected()
main._refresh_pages()
assert not page.txt_code.IsShown() and page.txt_code.GetValue() == ""
print(f"OK page_code ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# Apply saves what to announce
# --------------------------------------------------------------------------- #
page.checks["others"].SetValue(False)
page.checks["sounds"].SetValue(False)
prefs.OnApply(None)
saved = core.api.load_data("Dropbox")
assert saved["others"] is False and saved["sounds"] is False and saved["progress"] is True, saved
assert main._settings["others"] is False
print("OK apply")

# --------------------------------------------------------------------------- #
# Disconnect
# --------------------------------------------------------------------------- #
disconnected = []


def _fake_disconnect():
    disconnected.append(True)
    engine.client = None
    engine.account = None
    engine.state = engines.DISCONNECTED
    engine.services.changed()


engine.disconnect = _fake_disconnect
spoken.clear()
fire(page.btn_connect, wx.EVT_BUTTON)
assert disconnected == [True]
assert pump(lambda: page.txt_account.GetValue() == "Not connected."), page.txt_account.GetValue()
assert page.btn_connect.GetLabel() == "&Connect Dropbox"
assert "Dropbox disconnected." in spoken, spoken[-3:]
if observable:
    assert wx.Window.FindFocus() is page.btn_connect, "disconnecting moved the focus"
prefs.Destroy()
wx.Yield()
print(f"OK disconnect ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# Aruna: "Dropbox status" answers in Last result
# --------------------------------------------------------------------------- #
pretend_connected()
engine.tracker = types.SimpleNamespace(status=lambda: {"pending": ["laporan.pdf"], "stuck": []},
                                       clear=lambda: None)
core.hotkeys.actions["Hariku Core.command_bar"].callback()
assert pump(lambda: cb.current_bar() is not None), "Aruna did not open"
bar = cb.current_bar()
spoken.clear()
bar.txt_input.SetValue("dropbox status")
fire(bar.txt_input, wx.EVT_TEXT_ENTER)
assert pump(lambda: "Syncing laporan.pdf…" in bar.txt_result.GetValue(), 10), \
    (bar.txt_result.GetValue(), spoken[-3:])
print("OK aruna_status")

# --------------------------------------------------------------------------- #
# Aruna: "copy link" goes back to the window you were in first
# --------------------------------------------------------------------------- #
main.explorer.foreground_window = lambda: PREVIOUS          # Hariku's own window: not Explorer
focus_calls.clear()
spoken.clear()
bar.txt_input.SetValue("copy link")
fire(bar.txt_input, wx.EVT_TEXT_ENTER)
assert pump(lambda: cb.current_bar() is None, 10), "Aruna did not close for copy link"
assert focus_calls == [PREVIOUS], focus_calls
MESSAGE = "Open your Dropbox folder in File Explorer first, then select the file."
assert pump(lambda: MESSAGE in spoken, 10), spoken[-3:]

# "copy the link to this": the same, through the command with content.
core.hotkeys.actions["Hariku Core.command_bar"].callback()
assert pump(lambda: cb.current_bar() is not None), "Aruna did not open again"
bar = cb.current_bar()
spoken.clear()
bar.txt_input.SetValue("copy the link to this")
fire(bar.txt_input, wx.EVT_TEXT_ENTER)
assert pump(lambda: cb.current_bar() is None, 10), "Aruna did not close for this file"
assert pump(lambda: MESSAGE in spoken, 10), spoken[-3:]

# A pretend File Explorer on a file in the Dropbox folder: the link is copied.
explorer.window_class = lambda hwnd: "CabinetWClass"
engine.ask_explorer = lambda hwnd: (os.path.join(FOLDER, "laporan.pdf"), False)
copied = []
main.core.api.set_clipboard = lambda text: copied.append(text) or True
core.hotkeys.actions["Hariku Core.command_bar"].callback()
assert pump(lambda: cb.current_bar() is not None), "Aruna did not open a third time"
bar = cb.current_bar()
spoken.clear()
bar.txt_input.SetValue("copy link")
fire(bar.txt_input, wx.EVT_TEXT_ENTER)
assert pump(lambda: "Link to laporan.pdf copied." in spoken, 10), spoken[-3:]
assert links[-1] == "/laporan.pdf" and copied == ["https://www.dropbox.com/scl/fi/check/laporan.pdf"]
assert cb.current_bar() is None
print("OK aruna_copy_link")

# --------------------------------------------------------------------------- #
# Unloading
# --------------------------------------------------------------------------- #
engine.tracker = None
em.unload_all_extensions()
assert not any(i.id.startswith("Dropbox.") for i in core.commands.intents())
assert core.commands.aliases_for("Dropbox.copy_link") == []
assert main._engine is None
print("OK teardown")

assert not network_attempts, f"network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.RemoveIcon()
frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
