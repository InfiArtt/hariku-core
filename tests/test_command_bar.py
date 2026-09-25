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
# extension takes Ctrl+Alt+Backspace, and no new code installs a keyboard hook.

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


def make_bar(cb, voiced=False, language="id", keep_open=False, sounds=False, say=None):
    """A bar on fakes. Most tests check the bar that closes before an action
    runs (keep_open=False) without sounds; the core 2.8 tests turn them on."""
    import core.commands
    candidates = core.commands.commands(real_actions(language))
    said, ran = [], []

    def say_it(text):
        said.append(text)
        if say is not None:
            say(text)
        return voiced

    bar = cb.CommandBar(None, previous=4242,
                        decide=lambda text: core.commands.decide(text, candidates,
                                                                 parse=parse_reminder),
                        run=ran.append, say=say_it)
    bar.txt_input, bar.txt_result, bar.txt_status = FakeText(), FakeText(), FakeText()
    bar.btn_listen = FakeButton()
    bar.said, bar.ran = said, ran
    bar._keep_open, bar._sounds = keep_open, sounds
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
# Core 2.8: staying open after an answer, "thinking", sounds
# ------------------------------------------------------------

def speak_as_the_action(text):
    """What an action's core.speech.speak() does first."""
    from core.events import bus
    bus.emit("on_before_speak", {"text": text, "interrupt": True, "cancel": False})


def test_an_answer_keeps_the_bar_open_and_shows_it(cb):
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "gempa terbaru")
    assert bar.ran == ["Earthquakes.speak_latest"]
    assert not bar._closed and cb.current_bar() is bar and cb.focus == []
    assert bar.txt_status.value == "Aruna sedang berpikir..."
    assert bar.txt_input.selected                    # typing replaces the last command
    speak_as_the_action("M 5,2, 30 km barat daya Ambon.")
    speak_as_the_action("Tidak berpotensi tsunami.")
    assert bar.txt_result.value == "M 5,2, 30 km barat daya Ambon.\nTidak berpotensi tsunami."
    assert bar.last_said == bar.txt_result.value
    assert bar.txt_status.value.startswith("Aruna sudah menjawab.")
    bar._end_answer()
    speak_as_the_action("Something else Hariku says later.")
    assert "later" not in bar.txt_result.value      # no longer waiting for an answer
    bar.close()


def test_the_bars_own_words_are_not_an_answer(cb):
    bar = make_bar(cb, keep_open=True, say=speak_as_the_action)
    type_and_enter(bar, "jam berapa")
    assert bar.ran == ["Hariku Core.speak_time"] and bar._awaiting is not None
    bar.say("Maksudnya: ...?")                        # e.g. a question in between
    assert bar._awaiting.lines == []
    bar.close()


def test_every_new_message_stops_waiting_for_the_last_answer(cb):
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "gempa terbaru")
    first = bar._awaiting
    type_and_enter(bar, "cuaca hari ini")
    assert bar.ran == ["Earthquakes.speak_latest", "Weather.speak_current_weather"]
    assert bar._awaiting is not first
    bar.close()


def test_no_answer_in_time_says_it_ran(cb):
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "gempa terbaru")
    bar._answer_timeout(bar._awaiting)
    assert bar.txt_result.value == "Selesai: Ucapkan gempa terkini dari BMKG."
    assert bar._awaiting is None and not bar._closed
    bar.close()


def test_an_answer_that_opens_a_window_after_all_closes_the_bar(cb, monkeypatch):
    bar = make_bar(cb, keep_open=True)
    class NewWindow:                                 # hashable, as wx windows are
        def IsShown(self):
            return True

    new_window = NewWindow()
    windows = [bar]
    monkeypatch.setattr(cb.wx, "GetTopLevelWindows", lambda: list(windows))
    monkeypatch.setattr(bar, "_run", lambda action_id: windows.append(new_window))
    type_and_enter(bar, "gempa terbaru")
    assert bar._closed and cb.current_bar() is None
    assert cb.focus == []                            # focus stays with the new window


def test_other_actions_still_close_the_bar_first(cb):
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "daftar gempa terbaru")
    assert bar.ran == ["Earthquakes.show_recent"]
    assert bar._closed and cb.focus == [4242]


def test_a_saved_reminder_keeps_the_bar_open(cb):
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "ingatkan aku minum obat besok jam 8")
    bar._on_enter(None)
    assert [r.title for r in cb.saved] == ["Minum obat"]
    assert not bar._closed and cb.focus == [] and not bar._busy
    assert bar.txt_input.value == "" and bar.txt_status.value.startswith("Aruna sudah menjawab.")
    bar.close()


def test_a_question_says_how_to_answer(cb):
    bar = make_bar(cb)
    type_and_enter(bar, "Tua-tahari ini.")
    assert bar.said[-1].startswith("Maksudnya:")
    assert bar.txt_status.value.startswith("Aruna bertanya: Enter atau \"ya\"")
    bar.close()


@pytest.fixture
def sounds(cb, monkeypatch):
    played = []
    monkeypatch.setattr(cb.core.sounds, "play_internal_sound", played.append)
    from unittest.mock import MagicMock

    def call_later(ms, fn, *args):
        # The answer's sound (waiting for the send sound) comes at once; the
        # long waits for an answer never do here.
        if ms <= cb.REPLY_AFTER_SEND_MS:
            fn(*args)
        return MagicMock()

    monkeypatch.setattr(cb.wx, "CallLater", call_later)
    return played


def test_a_typed_message_and_its_answer_have_sounds(cb, sounds):
    bar = make_bar(cb, sounds=True)
    type_and_enter(bar, "blablabla")                 # not understood: Aruna answers at once
    assert sounds == ["aruna_send.wav", "aruna_reply.wav"]
    sounds.clear()
    bar = make_bar(cb, sounds=True, keep_open=True)
    type_and_enter(bar, "gempa terbaru")
    assert sounds == ["aruna_send.wav"]              # the action hasn't answered yet
    speak_as_the_action("M 5,2.")
    assert sounds == ["aruna_send.wav", "aruna_reply.wav"]
    speak_as_the_action("More of the same answer.")
    assert sounds.count("aruna_reply.wav") == 1
    bar.close()


def test_a_spoken_message_has_no_send_sound(cb, sounds):
    listener = FakeListener().register()
    bar = make_bar(cb, sounds=True)
    bar.start_listening()
    listener.started[0]("text", "blablabla")
    assert sounds == ["aruna_reply.wav"]             # Voice Control has its own tones


def test_sounds_off(cb, sounds):
    bar = make_bar(cb, sounds=False)
    type_and_enter(bar, "blablabla")
    assert sounds == []


def test_settings_default_on_and_are_saved(tmp_data_dir):
    import core.api
    import core.commands
    assert core.commands.bar_settings() == {"keep_open": True, "sounds": True}
    core.commands.save_bar_settings(False, True)
    assert core.api.load_data("Core")["aruna_keep_open"] is False
    assert core.commands.bar_settings() == {"keep_open": False, "sounds": True}


def test_answer_actions(monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_answer_actions", set())
    assert core.commands.is_answer_action("Hariku Core.speak_time")
    assert core.commands.is_answer_action("Earthquakes.speak_latest")
    assert not core.commands.is_answer_action("Earthquakes.show_recent")
    assert not core.commands.is_answer_action("Cockpit.airport_weather")   # opens a window
    core.commands.add_answer_actions("Observatory.next_asteroid")
    core.commands.add_answer_actions(["Tide.speak_tide", ""])
    assert core.commands.is_answer_action("Observatory.next_asteroid")
    assert core.commands.is_answer_action("Tide.speak_tide")


def test_answer_actions_exist_as_registered_actions():
    """Every id in ANSWER_ACTIONS is one the core or a bundled extension registers."""
    import core.commands
    ids = set(core.commands.BUILTIN_ALIASES)
    missing = sorted(a for a in core.commands.ANSWER_ACTIONS if a not in ids)
    assert not missing, missing


def test_arunas_sounds_ship_with_hariku():
    import wave
    for name in ("aruna_send.wav", "aruna_reply.wav"):
        with wave.open(os.path.join(ROOT, "sounds", name)) as w:
            assert w.getframerate() == 44100 and w.getnchannels() == 1
            assert 0.05 < w.getnframes() / w.getframerate() < 0.8


# ------------------------------------------------------------
# Core 2.9: commands with content (intents)
# ------------------------------------------------------------

@pytest.fixture
def intents(cb, monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    got = []

    def add(patterns, reply, intent_id="Notes.add"):
        def handler(request):
            got.append(request)
            return reply(request) if callable(reply) else reply
        core.commands.add_intent(intent_id, patterns, handler, title="Notes")
    add.got = got
    return add


def test_an_intent_says_its_answer(cb, intents):
    intents(["catat {text}"], lambda r: f"Dicatat: {r.text}.")
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "Catat: beli Gula Aren.")
    request = intents.got[0]
    assert (request.text, request.full_text, request.source, request.intent_id) == (
        "beli Gula Aren", "Catat: beli Gula Aren.", "typed", "Notes.add")
    assert bar.said == ["Dicatat: beli Gula Aren."] and not bar._closed
    assert bar.txt_status.value.startswith("Aruna sudah menjawab.")
    assert cb.routes == ["command"]              # what it says later comes in Hariku Voice
    bar.close()


def test_an_intent_answer_closes_the_bar_without_keep_open(cb, intents):
    intents(["catat {text}"], "Dicatat.")
    bar = make_bar(cb, keep_open=False)
    type_and_enter(bar, "catat beli gula")
    assert bar.said == ["Dicatat."] and bar._closed and cb.focus == [4242]


def test_an_intent_asks_first(cb, intents):
    done, dropped = [], []
    import core.commands
    intents(["catat {text}"], lambda r: core.commands.Reply(
        f"Catat \"{r.text}\"?", confirm=lambda: done.append(r.text) or "Sudah dicatat.",
        cancel=lambda: dropped.append(r.text)))
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "catat beli gula")
    assert bar.said == ['Catat "beli gula"?'] and bar._pending.kind == "intent"
    assert bar.txt_status.value.startswith("Aruna bertanya")
    assert done == []
    bar._on_enter(None)                            # Enter again: yes
    assert done == ["beli gula"] and bar.said[-1] == "Sudah dicatat."
    assert bar.txt_input.value == "" and not bar._closed
    type_and_enter(bar, "catat beli kopi")
    bar.submit("tidak", source="voice")
    assert dropped == ["beli kopi"] and bar.said[-1] == "Oke, batal."
    bar.close()


def test_an_intent_answers_later(cb, intents):
    import core.commands
    intents(["putar {text}"], core.commands.Reply("Mencari Elshinta...", wait=True),
            intent_id="Radio.play")
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "putar Elshinta")
    assert bar.said == ["Mencari Elshinta..."] and bar._awaiting is not None
    assert bar.txt_status.value == "Aruna sedang berpikir..."
    speak_as_the_action("Elshinta FM diputar.")
    assert bar.txt_result.value == "Elshinta FM diputar."
    assert bar.txt_status.value.startswith("Aruna sudah menjawab.")
    bar.close()


def test_an_intent_acts_after_the_bar_closed(cb, intents, monkeypatch):
    import core.commands
    order = []
    monkeypatch.setattr(cb, "set_foreground", lambda hwnd: order.append(("focus", hwnd)) or True)
    intents(["ketik {text}"], lambda r: core.commands.Reply(
        then=lambda: order.append(("type", r.text))), intent_id="Dictation.type")
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "ketik Halo, apa kabar?")
    assert bar._closed and order == [("focus", 4242), ("type", "Halo, apa kabar?")]


def test_an_intent_can_turn_the_text_down(cb, intents):
    # "gempa terbaru" matches "gempa {text}", but the handler doesn't want it:
    # the command runs as before.
    intents(["gempa {text}"], None, intent_id="Quakes.near")
    bar = make_bar(cb)
    type_and_enter(bar, "gempa terbaru")
    assert [r.text for r in intents.got] == ["terbaru"]
    assert bar.ran == ["Earthquakes.speak_latest"] and bar._closed


def test_a_failing_intent_says_so(cb, intents):
    def boom(request):
        raise RuntimeError("no notes file")
    intents(["catat {text}"], boom)
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "catat beli gula")
    assert bar.said == ["Perintah itu tidak berhasil."] and not bar._closed
    bar.close()


def test_a_spoken_intent_says_where_it_came_from(cb, intents):
    intents(["catat {text}"], "Dicatat.")
    bar = make_bar(cb, keep_open=True)
    bar.submit("Catat beli gula.", source="voice")
    assert intents.got[0].source == "voice" and intents.got[0].text == "beli gula"
    bar.close()


# ------------------------------------------------------------
# Core 2.9: answers told in steps (hold_answer, show_answer)
# ------------------------------------------------------------

@pytest.fixture
def hold(cb, monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_hold", {"until": 0.0})
    monkeypatch.setattr(core.commands, "_answer_sink", None)
    return core.commands


def test_a_held_answer_keeps_growing_across_its_pauses(cb, intents, hold):
    intents(["terbang ke {text}"], hold.Reply(wait=True), intent_id="Trip.go")
    bar = make_bar(cb, keep_open=True)
    type_and_enter(bar, "terbang ke Tokyo")
    answer = bar._awaiting
    hold.hold_answer(30)
    speak_as_the_action("Penerbangan dari Batam ke Tokyo.")
    bar._gathered(answer, 1)                         # the engines roar: a long pause
    assert bar._awaiting is answer
    bar._answer_timeout(answer)
    assert bar._awaiting is answer
    speak_as_the_action("Selamat datang di Tokyo, Jepang.")
    assert bar.txt_result.value == ("Penerbangan dari Batam ke Tokyo.\n"
                                    "Selamat datang di Tokyo, Jepang.")
    hold.hold_answer(0)
    bar._gathered(answer, 2)
    assert bar._awaiting is None                    # the hold is over: the answer ends
    bar.close()


def test_held_speech_starts_an_answer_quietly(cb, hold, sounds):
    bar = make_bar(cb, keep_open=True, sounds=True)
    speak_as_the_action("Not held: not shown.")
    assert bar._awaiting is None and bar.txt_result.value == ""
    hold.hold_answer(30)
    speak_as_the_action("Kamu mendengarkan J-Wave dari Tokyo.")
    assert bar._awaiting is not None and bar._awaiting.passive
    assert bar.txt_result.value == "Kamu mendengarkan J-Wave dari Tokyo."
    assert sounds == []                              # nobody asked: no "answered" sound
    type_and_enter(bar, "gempa terbaru")             # a new command starts a new answer
    assert bar._awaiting is not None and not bar._awaiting.passive
    bar.close()


def test_show_answer_adds_an_unspoken_line(cb, intents, hold):
    intents(["terbang ke {text}"], hold.Reply(wait=True), intent_id="Trip.go")
    bar = make_bar(cb, keep_open=True)
    assert hold.show_answer("Konbanwa!") is False    # no answer waiting, none held
    type_and_enter(bar, "terbang ke Tokyo")
    assert hold.show_answer("Konbanwa! (こんばんは！)") is True
    assert bar.txt_result.value == "Konbanwa! (こんばんは！)"
    assert bar.said == []                            # shown, never spoken
    bar.close()
    assert hold.show_answer("After closing.") is False


# ------------------------------------------------------------
# Core 2.9: Aruna in the background (the wake phrase)
# ------------------------------------------------------------

def background_bar(cb, **kwargs):
    bar = make_bar(cb, **kwargs)
    bar._background = True
    return bar


def test_in_the_background_aruna_closes_once_it_has_answered(cb):
    bar = background_bar(cb, keep_open=True)
    bar.submit("blablabla", source="voice")          # not understood: answered at once
    assert bar.said == ["Maaf, aku tidak paham."] and not bar._closed
    bar._finish_background()                         # BACKGROUND_CLOSE_MS later
    assert bar._closed and cb.focus == []            # the focus never left the user's window


def test_in_the_background_a_question_keeps_it_open(cb):
    bar = background_bar(cb)
    bar.submit("Tua-tahari ini.", source="voice")    # "Did you mean ...?"
    bar._finish_background()
    assert not bar._closed and bar._pending is not None
    bar.submit("ya", source="voice")
    assert bar.ran == ["Weather.speak_current_weather"] and bar._closed and cb.focus == []


def test_in_the_background_it_waits_for_an_answer_to_come(cb):
    bar = background_bar(cb, keep_open=True)
    bar.submit("gempa terbaru", source="voice")
    bar._finish_background()
    assert not bar._closed                           # still waiting for the answer
    speak_as_the_action("M 5,2, 30 km barat daya Ambon.")
    bar._end_answer()                                # ANSWER_GATHER_MS later
    bar._finish_background()
    assert bar._closed and bar.txt_result.value == "M 5,2, 30 km barat daya Ambon."


def test_in_the_background_hearing_nothing_ends_it(cb):
    listener = FakeListener().register()
    bar = background_bar(cb)
    bar.start_listening()
    listener.started[0]("stopped")
    bar._finish_background()
    assert bar._closed


def test_switching_to_the_bar_makes_it_a_normal_one(cb):
    bar = background_bar(cb, keep_open=True)
    event = types.SimpleNamespace(GetActive=lambda: True, Skip=lambda: None)
    bar._on_activate(event)
    assert bar._background is False
    bar.submit("blablabla")
    bar._finish_background()
    assert not bar._closed
    bar = background_bar(cb)
    cb.bring_to_front(bar)
    assert bar._background is False
    bar.close()


def test_open_in_the_background(cb, monkeypatch):
    import core.commands
    shown, fronted, listened = [], [], []
    monkeypatch.setattr(cb, "bring_to_front", lambda bar: fronted.append(bar))
    monkeypatch.setattr(cb.CommandBar, "ShowWithoutActivating",
                        lambda self: shown.append(self), raising=False)
    monkeypatch.setattr(cb.CommandBar, "_auto_listen",
                        lambda self: listened.append(self), raising=False)
    assert cb.CAN_OPEN_IN_BACKGROUND is True
    candidates = core.commands.commands(real_actions("id"))
    bar = cb.open_command_bar(background=True, decide=lambda text: core.commands.decide(
        text, candidates, parse=parse_reminder), run=lambda action_id: None,
        say=lambda text: False)
    assert bar._background and shown == [bar] and listened == [bar] and fronted == []
    assert cb.open_command_bar(background=True) is bar and fronted == []   # already open
    assert cb.open_command_bar() is bar and fronted == [bar]               # the hotkey
    bar.close()


def test_in_the_background_a_held_answer_is_heard_out_then_it_closes(cb, intents, hold):
    # "bawa aku ke Tokyo" by the wake phrase: Aruna stays while the trip is
    # told, then closes by itself; the trip itself goes on without it.
    intents(["bawa aku ke {text}"], hold.Reply(wait=True), intent_id="Trip.go")
    bar = background_bar(cb, keep_open=True)
    bar.submit("bawa aku ke Tokyo", source="voice")
    hold.hold_answer(30)
    speak_as_the_action("Penerbangan dari Batam ke Tokyo.")
    bar._finish_background()                         # BACKGROUND_CLOSE_MS after answering
    assert not bar._closed                           # the flight is still being told
    bar._gathered(bar._awaiting, 1)
    speak_as_the_action("Selamat datang di Tokyo, Jepang.")
    hold.hold_answer(0)
    bar._gathered(bar._awaiting, 2)                  # the hold is over: the answer ends
    bar._finish_background()
    assert bar._closed and cb.focus == []
    assert bar.txt_result.value.endswith("Selamat datang di Tokyo, Jepang.")


# ------------------------------------------------------------
# The hotkey: RegisterHotKey through core.hotkeys, no hook, no clash
# ------------------------------------------------------------

@pytest.fixture
def hotkeys(tmp_path, monkeypatch):
    import core.api
    import core.hotkeys as hk
    wx = sys.modules["wx"]
    for name, value in (("MOD_NONE", 0), ("MOD_ALT", 1), ("MOD_CONTROL", 2), ("MOD_SHIFT", 4),
                        ("MOD_WIN", 8), ("WXK_BACK", 8), ("WXK_SPACE", 32)):
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


def test_ctrl_alt_backspace_is_a_global_registerhotkey(hotkeys):
    import ui.command_bar as cb
    opened = []
    cb.register_hotkey(lambda: opened.append(True))
    action = hotkeys.actions["Hariku Core.command_bar"]
    assert (action.default_keycode, action.default_ctrl, action.default_alt,
            action.default_shift, action.default_win, action.default_global) == \
        (8, True, True, False, False, True)
    assert hotkeys.window.registered == [(100, 2 | 1, 8)]      # MOD_CONTROL | MOD_ALT, Backspace
    hotkeys.process_global_hotkey(100)
    assert opened == [True]
    assert cb.hotkey_label() == "Ctrl + Alt + Backspace"


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
    assert any("Ctrl + Alt + Backspace" in r.getMessage() and "taken" in r.getMessage()
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
            '                                 wx.WXK_BACK, True, callback or toggle_command_bar,\n'
            '                                 default_alt=True, default_global=True)') in bar


def test_no_bundled_extension_takes_ctrl_alt_backspace():
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
                        if "WXK_BACK" in ast.dump(node) and "alt" in ast.unparse(node).lower():
                            found.append(f"{folder}/{name}")
    assert found == []


def test_no_other_core_default_is_ctrl_alt_backspace():
    with open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8") as f:
        source = f.read()
    assert "WXK_BACK, True" not in source       # the command bar registers it in command_bar.py


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


def test_the_old_default_key_moves_to_the_new_one(hotkeys):
    old = {"keycode": 32, "ctrl": True, "shift": False, "alt": True, "win": False, "global": True}
    config = {"Hariku Core.command_bar": [dict(old)]}
    assert hotkeys.migrate_changed_defaults(config) is True
    assert config == {}                       # the new default (Ctrl+Alt+Backspace) applies
    chosen = {"Hariku Core.command_bar": [dict(old, keycode=ord("K"))]}
    assert hotkeys.migrate_changed_defaults(chosen) is False
    assert chosen["Hariku Core.command_bar"][0]["keycode"] == ord("K")   # the user's own key stays


def test_loading_saved_keys_applies_the_move(hotkeys, tmp_path):
    import json
    path = tmp_path / "keybindings.json"
    path.write_text(json.dumps({"Hariku Core.command_bar": [
        {"keycode": 32, "ctrl": True, "shift": False, "alt": True, "win": False, "global": True}],
        "Hariku Core.quick_reminder": [{"keycode": 78, "ctrl": False, "shift": False,
                                        "alt": False, "win": False, "global": False}]}))
    hotkeys.load_keybindings()
    assert "Hariku Core.command_bar" not in hotkeys.saved_config
    assert "Hariku Core.quick_reminder" in hotkeys.saved_config
    assert "Hariku Core.command_bar" not in json.loads(path.read_text())
