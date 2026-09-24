# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The command bar (ui/command_bar.py) without a window: conftest.py mocks wx,
# so the bar's logic runs on fakes. Focus changes, key state, speech routing,
# saving and the microphone are all replaced; nothing is shown, spoken or
# recorded. The real window is checked in CI by tests/_command_bar_ui_check.py.
# Also: the global hotkey goes through RegisterHotKey (mocked here), no bundled
# extension takes Ctrl+Alt+Space, and no new code installs a keyboard hook.

import logging
import os
import sys
import threading
import time
import types

import pytest

from tests.test_commands import NOW, parse_reminder, real_actions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeText:
    def __init__(self, value=""):
        self.value = value
        self.selected = False

    def GetValue(self):
        return self.value

    def ChangeValue(self, value):
        self.value = value

    SetValue = ChangeValue

    def SelectAll(self):
        self.selected = True

    def SetInsertionPointEnd(self):
        pass

    def SetFocus(self):
        pass


class FakeButton:
    def __init__(self):
        self.label = ""

    def SetLabel(self, label):
        self.label = label

    def Show(self, show=True):
        pass


class FakeEvent:
    def __init__(self, keycode, modifiers=False):
        self.keycode = keycode
        self.modifiers = modifiers
        self.skipped = False

    def GetKeyCode(self):
        return self.keycode

    def HasAnyModifiers(self):
        return self.modifiers

    def Skip(self):
        self.skipped = True


class FakeListener:
    def __init__(self, available=True, listen_on_open=False, start_ok=True):
        self.available = available
        self.open = listen_on_open
        self.start_ok = start_ok
        self.started = []
        self.stopped = []

    def start(self, on_event):
        self.started.append(on_event)
        if not self.start_ok:
            on_event("error", "no model")
        return self.start_ok

    def stop(self, discard=False):
        self.stopped.append(discard)

    def register(self):
        import core.commands
        core.commands.register_listener(self.start, self.stop, lambda: self.available,
                                        lambda: self.open, name="Fake")
        return self


@pytest.fixture
def indonesian(monkeypatch):
    from core import i18n
    had, old = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    monkeypatch.setattr(i18n, "_current_language", "id")
    yield
    if had:
        i18n._language_cache["core"] = old
    else:
        i18n._language_cache.pop("core", None)


@pytest.fixture
def cb(monkeypatch, tmp_data_dir, indonesian):
    """ui.command_bar with focus, keys, routing and saving replaced."""
    import core.commands
    import core.quick_reminder
    import ui.command_bar as cb
    focus = []
    routes = []
    saved = []
    from unittest.mock import MagicMock
    # conftest's wx.BoxSizer is the MagicMock class, so BoxSizer(wx.VERTICAL)
    # would be a mock specced on the number 0.
    monkeypatch.setattr(cb.wx, "BoxSizer", lambda *args, **kwargs: MagicMock())
    # CommandBar subclasses the mocked wx.Dialog (MagicMock); its unknown
    # attributes must be plain mocks, not new CommandBars.
    monkeypatch.setattr(cb.CommandBar, "_get_child_mock",
                        lambda self, **kwargs: MagicMock(**kwargs), raising=False)
    monkeypatch.setattr(cb, "_keys_down", lambda: False)
    monkeypatch.setattr(cb, "set_foreground", lambda hwnd: focus.append(hwnd) or True)
    monkeypatch.setattr(cb, "foreground_window", lambda: 4242)
    monkeypatch.setattr(cb, "_user32", lambda: types.SimpleNamespace(
        SetForegroundWindow=lambda hwnd: True))
    monkeypatch.setattr(cb.core.voice, "route_speech",
                        lambda kind, seconds=20: routes.append(kind) or True)
    monkeypatch.setattr(core.quick_reminder, "save_result",
                        lambda result: saved.append(result) or True)
    monkeypatch.setattr(core.quick_reminder, "parse_text", parse_reminder)
    monkeypatch.setattr(cb, "_bar", None)
    cb.focus, cb.routes, cb.saved = focus, routes, saved
    core.commands.unregister_listener()
    yield cb
    core.commands.unregister_listener()
    core.commands.set_fallback(None)


def make_bar(cb, voiced=False, language="id"):
    import core.commands
    candidates = core.commands.commands(real_actions(language))
    said, ran = [], []

    def say(text):
        said.append(text)
        return voiced

    bar = cb.CommandBar(None, previous=4242,
                        decide=lambda text: core.commands.decide(text, candidates,
                                                                 parse=parse_reminder),
                        run=ran.append, say=say)
    bar.txt_input, bar.txt_result, bar.txt_status = FakeText(), FakeText(), FakeText()
    bar.btn_listen = FakeButton()
    bar.said, bar.ran = said, ran
    cb._bar = bar
    return bar


def type_and_enter(bar, text):
    bar.txt_input.ChangeValue(text)
    bar._on_enter(None)


# ------------------------------------------------------------
# Typing
# ------------------------------------------------------------

def test_a_clear_command_closes_the_bar_then_runs(cb):
    bar = make_bar(cb)
    type_and_enter(bar, "gempa terbaru")
    assert bar.ran == ["Earthquakes.speak_latest"]
    assert bar._closed and cb.current_bar() is None
    assert cb.focus == [4242]              # focus went back to the previous window
    assert bar.said == []                  # the action answers for itself


def test_misrecognitions_run_or_ask(cb):
    bar = make_bar(cb)
    bar.submit("Pasawat di dekat sini.", source="voice")
    assert bar.ran == ["Flight Radar.speak_nearby"]
    bar = make_bar(cb)
    bar.submit("Tua-tahari ini.", source="voice")
    assert bar.ran == [] and bar.said == ["Maksudnya: Ucapkan cuaca saat ini?"]
    assert bar.txt_result.value == bar.said[-1]
    bar.submit("Ya.", source="voice")
    assert bar.ran == ["Weather.speak_current_weather"]


def test_did_you_mean_enter_again_is_yes(cb):
    bar = make_bar(cb)
    type_and_enter(bar, "Tua-tahari ini.")
    assert bar._pending is not None and bar.ran == []
    bar._on_enter(None)                    # the same text: yes
    assert bar.ran == ["Weather.speak_current_weather"]


def test_did_you_mean_no_keeps_the_bar_open(cb):
    bar = make_bar(cb)
    type_and_enter(bar, "Tua-tahari ini.")
    bar.submit("tidak", source="voice")
    assert bar.ran == [] and not bar._closed
    assert bar.said[-1] == "Oke, batal." and bar.txt_input.selected
    assert bar._pending is None


def test_escape_answers_no_then_closes(cb):
    import wx
    bar = make_bar(cb)
    type_and_enter(bar, "Tua-tahari ini.")
    bar._on_char_hook(FakeEvent(wx.WXK_ESCAPE))
    assert not bar._closed and bar._pending is None and bar.said[-1] == "Oke, batal."
    bar._on_char_hook(FakeEvent(wx.WXK_ESCAPE))
    assert bar._closed and cb.focus == [4242] and bar.ran == []


def test_other_keys_pass_through(cb):
    bar = make_bar(cb)
    event = FakeEvent("a key")
    bar._on_char_hook(event)
    assert event.skipped and not bar._closed


def test_not_understood_and_empty(cb):
    bar = make_bar(cb)
    type_and_enter(bar, "asdf qwerty")
    assert bar.said == ["Maaf, aku tidak paham."] and not bar._closed
    type_and_enter(bar, "   ")
    assert bar.said[-1].startswith("Ketik atau ucapkan perintah")


def test_a_new_command_replaces_a_question(cb):
    bar = make_bar(cb)
    type_and_enter(bar, "Tua-tahari ini.")
    type_and_enter(bar, "jam berapa")
    assert bar.ran == ["Hariku Core.speak_time"]


# ------------------------------------------------------------
# Reminders
# ------------------------------------------------------------

def test_reminder_read_back_then_enter_saves(cb):
    bar = make_bar(cb)
    type_and_enter(bar, "ingatkan aku minum obat besok jam 8")
    assert bar.said[-1].startswith("Minum obat, Jumat 25 September 2026, jam 08:00.")
    assert bar.said[-1].endswith("Simpan?")
    assert cb.saved == [] and not bar._closed
    bar._on_enter(None)
    assert [r.title for r in cb.saved] == ["Minum obat"]
    assert cb.routes == ["command"]        # "Reminder saved." comes in Hariku Voice
    assert bar._closed and cb.focus == [4242]


@pytest.mark.parametrize("answer", ["ya", "Simpan.", "yes", "Iya, simpan"])
def test_reminder_saved_by_voice(cb, answer):
    bar = make_bar(cb)
    bar.submit("minum obat besok jam 8", source="voice")
    bar.submit(answer, source="voice")
    assert len(cb.saved) == 1 and bar._closed


@pytest.mark.parametrize("answer", ["tidak", "batal", "no", "cancel"])
def test_reminder_cancelled(cb, answer):
    bar = make_bar(cb)
    bar.submit("minum obat besok jam 8", source="voice")
    bar.submit(answer, source="voice")
    assert cb.saved == [] and not bar._closed and bar.said[-1] == "Oke, batal."


def test_a_reminder_that_cannot_be_saved_is_explained(cb):
    bar = make_bar(cb)
    type_and_enter(bar, "besok jam 8")
    assert "tapi belum tahu apa yang perlu diingatkan" in bar.said[-1]
    assert bar._pending is None


def test_a_failed_save_says_so(cb, monkeypatch):
    import core.quick_reminder
    monkeypatch.setattr(core.quick_reminder, "save_result", lambda result: False)
    bar = make_bar(cb)
    type_and_enter(bar, "minum obat besok jam 8")
    bar._on_enter(None)
    assert not bar._closed and bar.said[-1] == "Pengingatnya tidak bisa disimpan."


def test_offer_the_quick_reminder(cb, monkeypatch):
    import core.commands
    import ui.quick_reminder_dialog
    opened = []
    monkeypatch.setattr(ui.quick_reminder_dialog, "open_quick_reminder",
                        lambda parent=None, text="": opened.append(text))
    result = types.SimpleNamespace(trigger="", recognised=[], title="Rapat", ok=False,
                                   unparsed=["jam"], components={})
    bar = make_bar(cb)
    bar._decide = lambda text: core.commands.decide(text, [], parse=lambda t: result)
    type_and_enter(bar, "rapat jam")
    assert bar.said[-1] == "Aku tidak paham perintah itu. Buka sebagai pengingat cepat?"
    bar._on_enter(None)
    assert opened == ["rapat jam"] and bar._closed
    assert cb.focus == []                  # the quick reminder takes the focus itself


# ------------------------------------------------------------
# Listening
# ------------------------------------------------------------

def test_hotkey_again_listens_and_stops(cb):
    listener = FakeListener().register()
    bar = cb.open_command_bar(listen=False)
    bar.txt_input, bar.txt_result, bar.txt_status = FakeText(), FakeText(), FakeText()
    bar.btn_listen = FakeButton()
    assert cb.toggle_command_bar() is bar and len(listener.started) == 1
    assert bar._listening
    cb.toggle_command_bar()
    assert listener.stopped == [False]     # stop and recognise what was heard


def test_enter_while_listening_stops(cb):
    listener = FakeListener().register()
    bar = make_bar(cb)
    bar.start_listening()
    bar._on_enter(None)
    assert listener.stopped == [False]


def test_heard_text_is_handled_like_typing(cb):
    listener = FakeListener().register()
    bar = make_bar(cb)
    bar.start_listening()
    on_event = listener.started[0]
    on_event("listening")
    assert bar.txt_status.value.startswith("Mendengarkan")
    on_event("recognising")
    assert bar.txt_status.value == "Mengenali ucapanmu..."
    on_event("text", "  Gempa terbaru.  ")
    assert bar.txt_input.value == "Gempa terbaru."
    assert bar.ran == ["Earthquakes.speak_latest"]


def test_listener_errors_are_said(cb):
    listener = FakeListener().register()
    bar = make_bar(cb)
    bar.start_listening()
    listener.started[0]("error", "Mikrofon tidak ditemukan.")
    assert bar.said[-1] == "Mikrofon tidak ditemukan." and not bar._listening


def test_a_listener_that_cannot_start(cb):
    FakeListener(start_ok=False).register()
    bar = make_bar(cb)
    assert bar.start_listening() is False
    assert not bar._listening and bar.said[-1] == "no model"


def test_events_of_an_old_session_are_ignored(cb):
    listener = FakeListener().register()
    bar = make_bar(cb)
    bar.start_listening()
    old = listener.started[0]
    bar.stop_listening(discard=True)       # Escape while listening, say
    assert listener.stopped == [True]
    old("text", "gempa terbaru")
    assert bar.ran == []


def test_without_voice_control_the_hotkey_says_how_to_get_it(cb):
    bar = cb.open_command_bar()
    bar.txt_input, bar.txt_result, bar.txt_status = FakeText(), FakeText(), FakeText()
    said = []
    bar._say_fn = lambda text: said.append(text)
    cb.toggle_command_bar()
    assert said and said[0].startswith("Voice Control belum terpasang")
    assert bar.start_listening() is False


def test_listening_as_the_bar_opens(cb, monkeypatch):
    listener = FakeListener(listen_on_open=True).register()
    monkeypatch.setattr(cb.wx, "CallLater", lambda ms, fn, *args: fn(*args))
    cb.open_command_bar()
    assert len(listener.started) == 1
    cb.current_bar().close()
    listener.open = False
    cb.open_command_bar()
    assert len(listener.started) == 1
    listener.open, listener.available = True, False
    cb.current_bar().close()
    cb.open_command_bar()
    assert len(listener.started) == 1      # nothing to listen with yet


def test_a_question_asked_by_voice_listens_for_the_answer(cb, monkeypatch):
    listener = FakeListener().register()
    monkeypatch.setattr(cb.wx, "CallLater", lambda ms, fn, *args: fn(*args))
    monkeypatch.setattr(cb.core.voice, "is_speaking", lambda: False)
    bar = make_bar(cb, voiced=True)
    bar.submit("Tua-tahari ini.", source="voice")
    assert len(listener.started) == 1      # after the question was said
    listener.started[0]("text", "ya")
    assert bar.ran == ["Weather.speak_current_weather"]


def test_a_typed_question_does_not_listen(cb, monkeypatch):
    listener = FakeListener().register()
    monkeypatch.setattr(cb.wx, "CallLater", lambda ms, fn, *args: fn(*args))
    bar = make_bar(cb, voiced=True)
    type_and_enter(bar, "Tua-tahari ini.")
    assert listener.started == []


def test_the_bar_closes_when_hariku_quits(cb):
    from core.events import bus
    assert cb.close_command_bar in bus._listeners["on_unload"]
    listener = FakeListener().register()
    bar = make_bar(cb)
    bar.start_listening()
    cb.close_command_bar()
    assert bar._closed and cb.current_bar() is None
    assert cb.focus == [] and listener.stopped == [True]
    cb.close_command_bar()                 # nothing open: nothing happens


def test_closing_while_listening_discards(cb):
    listener = FakeListener().register()
    bar = make_bar(cb)
    bar.start_listening()
    bar.close()
    assert listener.stopped == [True] and cb.focus == [4242]


# ------------------------------------------------------------
# Running an action, the fallback
# ------------------------------------------------------------

def test_run_command_routes_speech_first(monkeypatch):
    import core.commands
    import core.voice
    import ui.command_bar as cb
    order = []
    monkeypatch.setattr(core.voice, "route_speech", lambda kind, seconds=20: order.append(kind))
    monkeypatch.setattr(core.commands, "run_action",
                        lambda action_id: order.append(action_id) or True)
    assert cb.run_command("Weather.speak_current_weather") is True
    assert order == ["command", "Weather.speak_current_weather"]
    said = []
    monkeypatch.setattr(core.commands, "run_action", lambda action_id: False)
    monkeypatch.setattr(core.voice, "announce", lambda text, kind, interrupt=True:
                        said.append(kind))
    assert cb.run_command("Gone.away") is False and said == ["command"]


def test_the_fallback_is_only_ever_asked_about(cb, monkeypatch):
    import core.commands
    everything = core.commands.commands(real_actions("id"))
    monkeypatch.setattr(core.commands, "commands", lambda actions=None: everything)
    core.commands.set_fallback(lambda text, commands: "Weather.speak_current_weather")
    bar = make_bar(cb)
    type_and_enter(bar, "apakah nanti hujan")
    deadline = time.monotonic() + 5
    while not bar.said and time.monotonic() < deadline:
        time.sleep(0.01)
    assert bar.said == ["Maksudnya: Ucapkan cuaca saat ini?"] and bar.ran == []


# ------------------------------------------------------------
# The hotkey: RegisterHotKey through core.hotkeys, no hook, no clash
# ------------------------------------------------------------

@pytest.fixture
def hotkeys(tmp_path, monkeypatch):
    import core.api
    import core.hotkeys as hk
    wx = sys.modules["wx"]
    for name, value in (("MOD_NONE", 0), ("MOD_ALT", 1), ("MOD_CONTROL", 2), ("MOD_SHIFT", 4),
                        ("MOD_WIN", 8), ("WXK_SPACE", 32)):
        monkeypatch.setattr(wx, name, value, raising=False)
    monkeypatch.setattr(hk, "KEYBINDINGS_FILE", str(tmp_path / "keybindings.json"))
    monkeypatch.setattr(hk, "saved_config", {})
    monkeypatch.setattr(hk, "actions", {})
    monkeypatch.setattr(hk, "keybindings", {})
    monkeypatch.setattr(hk, "_registered_hotkeys", {})
    window = types.SimpleNamespace(registered=[], unregistered=[], accept=True)
    window.RegisterHotKey = lambda hid, mods, key: window.registered.append((hid, mods, key)) \
        or window.accept
    window.UnregisterHotKey = lambda hid: window.unregistered.append(hid) or True
    monkeypatch.setattr(core.api, "main_window_instance", window)
    hk.window = window
    return hk


def test_ctrl_alt_space_is_a_global_registerhotkey(hotkeys):
    import ui.command_bar as cb
    opened = []
    cb.register_hotkey(lambda: opened.append(True))
    action = hotkeys.actions["Hariku Core.command_bar"]
    assert (action.default_keycode, action.default_ctrl, action.default_alt,
            action.default_shift, action.default_win, action.default_global) == \
        (32, True, True, False, False, True)
    assert hotkeys.window.registered == [(100, 2 | 1, 32)]     # MOD_CONTROL | MOD_ALT, Space
    hotkeys.process_global_hotkey(100)
    assert opened == [True]
    assert cb.hotkey_label() == "Ctrl + Alt + Space"


def test_the_command_bar_key_can_be_moved(hotkeys):
    import ui.command_bar as cb
    cb.register_hotkey(lambda: None)
    moved = {"Hariku Core.command_bar": [{"keycode": ord("K"), "ctrl": True, "shift": True,
                                          "alt": False, "win": False, "global": True}]}
    hotkeys.apply_new_config(moved)
    assert hotkeys.window.registered[-1] == (100, 2 | 4, ord("K"))
    assert cb.hotkey_label() == "Ctrl + Shift + K"


def test_a_taken_key_is_logged(hotkeys, caplog):
    import ui.command_bar as cb
    hotkeys.window.accept = False
    caplog.set_level(logging.WARNING, logger="core.hotkeys")
    cb.register_hotkey(lambda: None)
    assert any("Ctrl + Alt + Space" in r.getMessage() and "taken" in r.getMessage()
               for r in caplog.records)
    assert hotkeys._registered_hotkeys == {}


def test_main_window_registers_the_command_bar():
    with open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8") as f:
        source = f.read()
    assert "register_hotkey(self.OnCommandBar)" in source
    assert "toggle_command_bar()" in source
    with open(os.path.join(ROOT, "ui", "command_bar.py"), encoding="utf-8") as f:
        bar = f.read()
    assert ('core.hotkeys.register_action("Hariku Core", ACTION_NAME, _("nav_command_bar"),\n'
            '                                 wx.WXK_SPACE, True, callback or toggle_command_bar,\n'
            '                                 default_alt=True, default_global=True)') in bar


def test_no_bundled_extension_takes_ctrl_alt_space():
    import ast
    found = []
    for folder in sorted(os.listdir(os.path.join(ROOT, "extensions"))):
        path = os.path.join(ROOT, "extensions", folder)
        if not os.path.isdir(path) or folder == "voice_control":
            continue
        for dirpath, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ("lib", "__pycache__")]
            for name in files:
                if not name.endswith(".py"):
                    continue
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr == "register_action"):
                        if "WXK_SPACE" in ast.dump(node) or "ord(' ')" in ast.unparse(node):
                            found.append(f"{folder}/{name}")
    assert found == []


def test_no_other_core_default_is_ctrl_alt_space():
    with open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8") as f:
        source = f.read()
    assert "WXK_SPACE, True" not in source      # the command bar registers it in command_bar.py


NEW_CODE = [os.path.join("core", "commands.py"), os.path.join("core", "voice.py"),
            os.path.join("core", "speech.py"), os.path.join("core", "hotkeys.py"),
            os.path.join("ui", "command_bar.py"), os.path.join("ui", "main_window.py")]
NEW_CODE += [os.path.join("extensions", "voice_control", name)
             for name in sorted(os.listdir(os.path.join(ROOT, "extensions", "voice_control")))
             if name.endswith(".py")]


@pytest.mark.parametrize("path", NEW_CODE)
def test_no_keyboard_hook(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        source = f.read()
    for forbidden in ("SetWindowsHookEx", "WH_KEYBOARD", "WH_KEYBOARD_LL", "keyboard.hook",
                      "pynput"):
        assert forbidden not in source, f"{path} mentions {forbidden}"


def test_voice_control_is_official():
    import core.extension_manager
    assert "voice_control" in core.extension_manager._OFFICIAL_EXTENSION_IDS
    with open(os.path.join(ROOT, "tools", "server", "generate_trusted_hashes.py"),
              encoding="utf-8") as f:
        assert '"voice_control",' in f.read()
