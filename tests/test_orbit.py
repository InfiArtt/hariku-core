# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Orbit extension (extensions/orbit), all on fakes: reading
# commands in Indonesian and English (and the client's own: quick settings,
# the ignore list, leaving, the status), Aruna's "orbit ..." commands,
# playing (what is shown, played and said, and by whom; what the settings
# leave unread; what is heard with the window closed; players you ignore),
# each player's own voice and the voice they chose, the speaking queue,
# closing the window, leaving, being away and logged out by itself, the
# status, moving a character to another computer, the ambience player (a
# fake MCI), the connection thread (a fake socket), the settings,
# registering, the cues and where they come from, the mixer that finds and
# places them, and the generated sounds. Nothing is sent, played, spoken or
# shown. tests/test_orbit_e2e.py plays against the real server on this computer.

import importlib.util
import io
import math
import os
import random
import sys
import threading
import time
import types
import wave

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
SOUNDS_DIR = os.path.join(EXT_DIR, "sounds")
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

import orbit_audio  # noqa: E402
import orbit_net  # noqa: E402
import orbit_parse  # noqa: E402
import orbit_play  # noqa: E402
import orbit_speech  # noqa: E402
import orbit_ws  # noqa: E402


@pytest.fixture
def lang(monkeypatch):
    """Switch Hariku's language (Orbit's own words follow it)."""
    from core import i18n

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("id")
    return set_lang


# ------------------------------------------------------------
# Reading commands
# ------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("pergi ke kantin", {"c": "go", "a": "kantin"}),
    ("go to the cantina", {"c": "go", "a": "the cantina"}),
    ("ke dek observasi", {"c": "go", "a": "dek observasi"}),
    ("pulang", {"c": "go", "a": "kabin"}),
    ("masuk kabin", {"c": "go", "a": "kabin"}),
    ("bilang halo semua!", {"c": "say", "a": "halo semua!"}),
    ("say Hi, how are you?", {"c": "say", "a": "Hi, how are you?"}),
    ("'apa kabar", {"c": "say", "a": "apa kabar"}),
    ("bisik Sari ketemu di dek", {"c": "whisper", "to": "Sari", "a": "ketemu di dek"}),
    ("berbisik ke Sari: nanti ya", {"c": "whisper", "to": "Sari", "a": "nanti ya"}),
    ("whisper to Budi meet me at the dock", {"c": "whisper", "to": "Budi",
                                             "a": "meet me at the dock"}),
    ("tell Budi hi", {"c": "whisper", "to": "Budi", "a": "hi"}),
    ("teriak ada yang mau ke bulan?", {"c": "shout", "a": "ada yang mau ke bulan?"}),
    ("senyum", {"c": "emote", "e": "smile"}),
    ("senyum ke Sari", {"c": "emote", "e": "smile", "to": "Sari"}),
    ("wave at Budi", {"c": "emote", "e": "wave", "to": "Budi"}),
    ("angkat bahu", {"c": "emote", "e": "shrug"}),
    ("tepuk tangan", {"c": "emote", "e": "clap"}),
    ("wkwkwk", {"c": "emote", "e": "laugh"}),
    ("peluk Sari", {"c": "emote", "e": "hug", "to": "Sari"}),
    ("senyum itu ibadah ya", {"c": "text", "a": "senyum itu ibadah ya"}),
    ("siapa online", {"c": "who"}),
    ("who is online", {"c": "who"}),
    ("lihat", {"c": "look"}),
    ("lihat sekitar", {"c": "look"}),
    ("lihat Sari", {"c": "look", "a": "Sari"}),
    ("look at the reactor", {"c": "look", "a": "the reactor"}),
    ("cek kredit", {"c": "inventory"}),
    ("tas", {"c": "inventory"}),
    ("i", {"c": "inventory"}),
    ("i think so", {"c": "text", "a": "i think so"}),
    ("beri Sari 50 kredit", {"c": "give", "to": "Sari", "n": 50, "item": "kredit"}),
    ("kasih ke Sari 2 kopi", {"c": "give", "to": "Sari", "n": 2, "item": "kopi"}),
    ("give 50 credits to Sari", {"c": "give", "to": "Sari", "n": 50, "item": "credits"}),
    ("bayar Budi 20", {"c": "give", "to": "Budi", "n": 20, "item": "credits"}),
    ("kerja", {"c": "work"}),
    ("perbaiki reaktor", {"c": "work"}),
    ("perbaiki 3142", {"c": "answer", "a": "3142"}),
    ("3, 1, 4, 2", {"c": "answer", "a": "3, 1, 4, 2"}),
    ("misi", {"c": "missions"}),
    ("misi 2", {"c": "accept", "n": 2}),
    ("ambil misi 1", {"c": "accept", "n": 1}),
    ("accept 3", {"c": "accept", "n": 3}),
    ("ambil 3 peti", {"c": "take", "item": "peti", "n": 3}),
    ("pick up crates", {"c": "take", "item": "crates"}),
    ("selesaikan misi", {"c": "complete"}),
    ("batalkan misi", {"c": "abandon"}),
    ("harga", {"c": "prices"}),
    ("beli 2 kopi", {"c": "buy", "item": "kopi", "n": 2}),
    ("jual semua kopi", {"c": "sell", "item": "kopi", "n": "all"}),
    ("sell all coffee", {"c": "sell", "item": "coffee", "n": "all"}),
    ("deskripsi aku pilot dari Batam", {"c": "describe", "a": "pilot dari Batam"}),
    ("describe me", {"c": "describe", "a": ""}),
    ("bantuan", {"local": "help"}),
    ("help", {"local": "help"}),
    ("sambungkan", {"local": "connect"}),
    ("putuskan", {"local": "disconnect"}),
    ("ulangi", {"local": "repeat"}),
    ("kantin", {"c": "text", "a": "kantin"}),
    ("orbit pergi ke dermaga", {"c": "go", "a": "dermaga"}),
    ("tolong orbit siapa online", {"c": "who"}),
    ("mute Budi 5", {"c": "admin", "op": "mute", "to": "Budi", "n": 5}),
    ("umumkan server restart jam 9", {"c": "admin", "op": "announce", "a": "server restart jam 9"}),
    ("suara pemain mati", {"local": "set", "key": "voices", "value": False}),
    ("nyalakan suara pemain", {"local": "set", "key": "voices", "value": True}),
    ("voices off", {"local": "set", "key": "voices", "value": False}),
    ("bacakan pesan mati", {"local": "set", "key": "speak", "value": False}),
    ("speech on", {"local": "set", "key": "speak", "value": True}),
    ("ambience mati", {"local": "set", "key": "ambience", "value": False}),
    ("suasana nyala", {"local": "set", "key": "ambience", "value": True}),
    ("suara efek mati", {"local": "set", "key": "sounds", "value": False}),
    ("turn off sounds", {"local": "set", "key": "sounds", "value": False}),
    ("other sounds off", {"local": "set", "key": "other_sounds", "value": False}),
    ("volume efek 40", {"local": "set", "key": "effects_volume", "value": 40}),
    ("ambience volume 250", {"local": "set", "key": "ambience_volume", "value": 100}),
    ("pengaturan", {"local": "settings"}), ("settings", {"local": "settings"}),
    ("abaikan Budi", {"local": "ignore", "name": "Budi"}),
    ("ignore Budi", {"local": "ignore", "name": "Budi"}),
    ("dengar lagi Budi", {"local": "unignore", "name": "Budi"}),
    ("unignore Budi", {"local": "unignore", "name": "Budi"}),
    ("daftar abaikan", {"local": "ignored"}),
    ("keluar", {"local": "disconnect"}), ("orbit keluar", {"local": "disconnect"}),
    ("quit", {"local": "disconnect"}),
    ("status", {"local": "status"}), ("status orbit", {"local": "status"}),
    ("bantuan kasino", {"local": "help", "topic": "kasino"}),
    ("help settings", {"local": "help", "topic": "settings"}),
    ("harga panen", {"c": "prices", "a": "panen"}),
    ("s", {"c": "text", "a": "s"}), ("u", {"c": "text", "a": "u"}), ("barat daya", {"c": "text", "a": "barat daya"}),
    ("beri kredit Budi 50", {"c": "text", "a": "beri kredit Budi 50"}),
    ("ambil kredit Budi 50", {"c": "text", "a": "ambil kredit Budi 50"}),
    ("take off headlamp", {"c": "text", "a": "take off headlamp"}),
    ("board the Kancil", {"c": "text", "a": "board the Kancil"}),
    ("transfer code", {"c": "text", "a": "transfer code"}),
    ("nyalakan lentera", {"c": "text", "a": "nyalakan lentera"}),
    ("", None), ("   ", None),
])
def test_reading_commands_in_both_languages(text, expected):
    assert orbit_parse.parse(text) == expected


def test_both_languages_have_the_same_words_and_placeholders():
    import json
    import string
    texts = {}
    for code in ("en", "id"):
        with open(os.path.join(EXT_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            texts[code] = json.load(f)["messages"]
    assert set(texts["en"]) == set(texts["id"])

    def fields(text):
        return {name for _l, name, _s, _c in string.Formatter().parse(text) if name}

    for key, line in texts["en"].items():
        assert fields(line) == fields(texts["id"][key]), key


# ------------------------------------------------------------
# main.py: Aruna, registering, settings
# ------------------------------------------------------------

@pytest.fixture
def omain(monkeypatch, tmp_data_dir, lang):
    spec = importlib.util.spec_from_file_location("orbit_main_under_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    try:
        module.teardown()
    except Exception:
        pass


@pytest.mark.parametrize("text, slot", [
    ("orbit pergi ke kantin", "pergi ke kantin"),
    ("Aruna, orbit bilang halo semua!", "bilang halo semua!"),
    ("tolong orbit siapa online", "siapa online"),
    ("orbit bisik Sari ketemu di dek", "bisik Sari ketemu di dek"),
    ("orbit lihat sekitar", "lihat sekitar"),
    ("orbit go to the cantina", "go to the cantina"),
])
def test_orbit_sentences_reach_the_game(omain, monkeypatch, text, slot):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    core.commands.add_intent(omain.PLAY_INTENT, list(omain.PLAY_PATTERNS), omain._on_play_intent)
    found = core.commands.match_intents(text)
    assert found and found[0].intent.id == "Orbit.play" and found[0].text == slot
    asked, held = [], []
    monkeypatch.setattr(core.commands, "hold_answer", held.append)
    monkeypatch.setattr(omain, "_client", types.SimpleNamespace(
        submit=lambda text, source: asked.append((text, source)), online=lambda: True))
    reply = found[0].intent.handler(core.commands.Request(found[0].text, text))
    assert isinstance(reply, core.commands.Reply) and reply.wait and not reply.say
    assert asked == [(slot, "aruna")]          # run once Aruna waits (wx.CallAfter)
    assert held == []


def test_aruna_waits_longer_while_orbit_connects(omain, monkeypatch):
    import core.commands
    held = []
    monkeypatch.setattr(core.commands, "hold_answer", held.append)
    monkeypatch.setattr(omain, "_client", types.SimpleNamespace(
        submit=lambda text, source: None, online=lambda: False))
    reply = omain._on_play_intent(core.commands.Request("siapa online", "orbit siapa online"))
    assert reply.wait and held == [omain.CONNECT_HOLD_SECONDS]


def test_not_for_orbit(omain, monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    core.commands.add_intent(omain.PLAY_INTENT, list(omain.PLAY_PATTERNS), omain._on_play_intent)
    assert core.commands.match_intents("orbit") == []
    assert core.commands.match_intents("pergi ke kantin") == []
    monkeypatch.setattr(omain, "_client", types.SimpleNamespace(submit=lambda *a: None,
                                                                online=lambda: True))
    request = core.commands.Request
    assert omain._on_play_intent(request("   ", "orbit")) is None
    assert omain._on_play_intent(request("x" * 400, "orbit ...")) is None
    reply = omain._on_play_intent(request("buka", "orbit buka"))
    assert reply.then is omain.open_window


def _commands(omain):
    import core.commands
    candidates = []
    for name, description, _title, _callback, aliases, _answers in omain.ACTIONS:
        candidates.append(core.commands.Command(f"Orbit.{name}", omain._(description), list(aliases)))
    for action_id, description in (("Hariku Core.speak_time", "Ucapkan waktu"),
                                   ("World Trip.where_am_i", "Di mana aku sekarang")):
        candidates.append(core.commands.Command(action_id, description,
                                                core.commands.aliases_for(action_id)))
    return candidates


@pytest.mark.parametrize("text, action", [
    ("orbit", "Orbit.open"), ("buka orbit", "Orbit.open"), ("open orbit", "Orbit.open"),
    ("main orbit", "Orbit.open"),
])
def test_what_aruna_runs(omain, text, action):
    import core.commands
    found = core.commands.match(text, _commands(omain))
    assert found.kind == "run" and found.best.id == action, found


def test_a_sentence_with_orbit_is_a_command_with_content(omain, monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    intent = core.commands.add_intent(omain.PLAY_INTENT, list(omain.PLAY_PATTERNS),
                                      omain._on_play_intent)
    decision = core.commands.decide("orbit bilang besok ketemu jam 9", _commands(omain),
                                    parse=lambda text: None, intent_candidates=[intent])
    assert decision.kind == "intent" and decision.intents[0].text == "bilang besok ketemu jam 9"


def test_register_and_teardown(omain, fresh_event_bus, monkeypatch):
    import core.commands
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel", lambda *args: panels.append(args))
    monkeypatch.setattr(core.commands, "_intents", {})
    monkeypatch.setattr(core.commands, "_answer_actions", set())
    omain.register(fresh_event_bus)
    assert {args[1] for args, _kw in actions} == {"open", "look", "who", "credits", "connect", "status",
                                                  "leave", "daily", "harvest", "profile"}
    for args, kwargs in actions:
        assert args[0] == "Orbit" and args[3] is None and kwargs == {}        # no default keys
    assert core.commands.is_answer_action("Orbit.look") and core.commands.is_answer_action("Orbit.who")
    assert not core.commands.is_answer_action("Orbit.open")                # it opens a window
    assert [i.id for i in core.commands.intents()] == ["Orbit.play"]
    assert "buka orbit" in core.commands.aliases_for("Orbit.open")
    assert "orbit keluar" in core.commands.aliases_for("Orbit.leave")
    assert "orbit status" in core.commands.aliases_for("Orbit.status")
    assert panels[0][0] == "Orbit"
    assert omain._on_before_speak in fresh_event_bus._listeners["on_before_speak"]
    omain.teardown()
    assert core.commands.intents() == [] and core.commands.aliases_for("Orbit.open") == []
    assert omain._on_before_speak not in fresh_event_bus._listeners.get("on_before_speak", [])


def test_settings_are_checked(omain):
    s = omain.normalize_settings({"server": "  wss://example.org/orbit/ws ", "name": " Rafli ",
                                  "job": "wizard", "speak": "yes", "ambience_volume": 250,
                                  "voices": False, "read_shout": False, "background": "loud",
                                  "close_action": "leave", "auto_logout": 45, "effects_volume": -5,
                                  "ignored": ["Budi", " budi ", "", 7, "Sari"]})
    assert s == {"server": "wss://example.org/orbit/ws", "name": "Rafli", "job": "pilot",
                 "speak": True, "voices": False, "speak_own": True, "speak_names": True,
                 "ambience": True, "ambience_volume": 100,
                 "sounds": True, "effects_volume": 0, "other_sounds": True,
                 "read_say": True, "read_whisper": True, "read_shout": False, "read_moves": True,
                 "read_money": True, "read_announce": True, "background": "important",
                 "close_action": "leave", "auto_logout": 30, "autoconnect": False,
                 "ignored": ["Budi", "Sari"], "close_hints": 0}
    assert omain.normalize_settings("broken") == omain.DEFAULT_SETTINGS
    assert omain.DEFAULT_SETTINGS["server"] == "wss://infiartt.com/orbit/ws"


def test_the_services_save_accounts_per_server(omain):
    services = omain.Services()
    assert services.account("wss://a.example/orbit/ws") is None
    services.save_account("wss://a.example/orbit/ws", {"secret": "s1", "name": "Rafli"})
    services.save_account("wss://b.example/orbit/ws", {"secret": "s2", "name": "Rafli"})
    assert services.account("wss://a.example/orbit/ws")["secret"] == "s1"
    assert services.account("wss://b.example/orbit/ws")["secret"] == "s2"
    secret = services.new_secret()
    assert len(secret) == 64 and secret != services.new_secret()


# ------------------------------------------------------------
# Playing, with a fake connection
# ------------------------------------------------------------

class FakeConnection:
    def __init__(self, url, hello, on_message, on_state):
        self.url = url
        self.hello = hello
        self.on_message = on_message
        self.on_state = on_state
        self.sent = []
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self, wait=0):
        self.stopped = True

    def running(self):
        return self.started and not self.stopped

    def send(self, message):
        self.sent.append(message)
        return True

    # the server's side
    def welcome(self, name="Rafli", job="pilot", **extra):
        self.on_state("online", {})
        message = {"t": "welcome", "name": name, "job": job, "new": True, "resumed": False,
                   "room": "dock", "amb": "vent"}
        message.update(extra)
        self.on_message(message)

    def event(self, kind, text, **extra):
        message = {"t": "ev", "k": kind, "text": text}
        message.update(extra)
        self.on_message(message)


class FakeServices:
    VOICES = {"edge": [{"id": "id-ID-ArdiNeural", "name": "Ardi", "language": "id-ID"},
                       {"id": "id-ID-GadisNeural", "name": "Gadis", "language": "id-ID"}],
              "windows": [{"id": "andika", "name": "Andika", "language": "id-ID"},
                          {"id": "zira", "name": "Zira", "language": "en-US"}]}
    # The cues these fakes can play (step_grass has no file: it falls back).
    FILES = {"door", "arrive", "leave", "say", "whisper", "shout", "emote", "emote_wave", "sent",
             "announce", "success", "coins", "fail", "error", "mission", "task", "offer",
             "step_metal", "lift_up", "lift_down", "levelup", "tone1", "tone2", "tone3", "tone4"}

    def __init__(self, **settings):
        self.values = {"server": "wss://infiartt.com/orbit/ws", "name": "Rafli", "job": "pilot",
                       "speak": True, "voices": True, "speak_own": True, "speak_names": True,
                       "ambience": True, "ambience_volume": 25,
                       "sounds": True, "effects_volume": 100, "other_sounds": True,
                       "read_say": True, "read_whisper": True, "read_shout": True,
                       "read_moves": True, "read_money": True, "read_announce": True,
                       "background": "important", "close_action": "stay", "auto_logout": 30,
                       "autoconnect": False, "ignored": [], "close_hints": 0}
        self.values.update(settings)
        self.accounts = {}
        self.connections = []
        self.spoken = []
        self.sounds = []
        self.placed = []
        self.ambiences = []
        self.shown = []
        self.timers = []
        self.window = True
        self.voices_on = True
        self.secrets = 0
        self.settings_opened = 0
        self.key = "Ctrl + Shift + O"
        self.narrator = None

    def settings(self):
        return dict(self.values)

    def set_setting(self, key, value):
        self.values[key] = value

    def open_settings(self):
        self.settings_opened += 1

    def open_key(self):
        return self.key

    def language(self):
        return "id"

    def account(self, url):
        return dict(self.accounts[url]) if url in self.accounts else None

    def save_account(self, url, account):
        self.accounts[url] = dict(account)

    def new_secret(self):
        self.secrets += 1
        return f"{self.secrets:064x}"

    def connect(self, url, hello, on_message, on_state):
        conn = FakeConnection(url, hello, on_message, on_state)
        self.connections.append(conn)
        return conn

    def call_later(self, seconds, fn):
        timer = types.SimpleNamespace(seconds=seconds, fn=fn, cancelled=False)
        timer.cancel = lambda: setattr(timer, "cancelled", True)
        self.timers.append(timer)
        return timer

    def run_timers(self):
        while self.timers:
            timers, self.timers = self.timers, []
            for timer in sorted(timers, key=lambda t: t.seconds):
                if not timer.cancelled:
                    timer.fn()

    def call_after(self, fn, *args):
        fn(*args)

    def say(self, text):
        self.spoken.append(("narrator", text))
        return True

    def speak_voice(self, text, voice, on_done):
        self.spoken.append((voice["id"], text))
        on_done(None)
        return True

    def voice_busy(self):
        return False

    def narrator_voice(self):
        return self.narrator                     # None: the narrator is say() above

    def voice_count(self):
        if not self.voices_on:
            return 1
        return orbit_speech.pool_size(orbit_speech.voices_of(self.VOICES, "id"))

    def voice_for(self, name, number=None):
        if not self.voices_on:
            return None
        return orbit_speech.pick_voice(name, orbit_speech.voices_of(self.VOICES, "id"), number=number)

    def show_answer(self, text):
        self.shown.append(text)

    def play(self, name, pan=0.0, acoustics=None):
        if name not in self.FILES:
            return False
        self.sounds.append(name)
        self.placed.append((name, pan, acoustics))
        return True

    def ambience(self, name, volume):
        self.ambiences.append((name, volume))

    def window_open(self):
        return self.window


@pytest.fixture
def play(lang):
    services = FakeServices()
    client = orbit_play.OrbitClient(services)
    return types.SimpleNamespace(services=services, client=client)


def _online(play, **welcome):
    play.client.connect()
    conn = play.services.connections[-1]
    conn.welcome(**welcome)
    return conn


def test_the_first_join_makes_a_secret_for_that_server_only(play):
    s, client = play.services, play.client
    assert client.connect()
    conn = s.connections[-1]
    hello = conn.hello()
    assert hello == {"t": "hello", "v": 1, "client": "Hariku Orbit 1.1", "lang": "id",
                     "secret": "0" * 63 + "1", "name": "Rafli", "job": "pilot"}
    assert s.accounts[s.values["server"]]["joined"] is False
    conn.welcome(name="Rafli")
    assert s.accounts[s.values["server"]] == {"secret": "0" * 63 + "1", "name": "Rafli",
                                              "job": "pilot", "joined": True}
    # Again: the same secret; a changed name no longer matters.
    s.values["name"] = "Somebody"
    client.connect()
    assert s.connections[-1].hello()["secret"] == "0" * 63 + "1"
    assert s.connections[-2].stopped
    # Another server gets another secret.
    client.connect("ws://127.0.0.1:7340/orbit/ws")
    assert s.connections[-1].hello()["secret"] == "0" * 63 + "2"


def test_before_the_first_welcome_the_name_can_still_change(play):
    s, client = play.services, play.client
    client.connect()
    s.connections[-1].on_state("failed", {"t": "err", "code": "name_taken",
                                         "text": "Sudah ada yang bernama Rafli di stasiun."})
    assert client.status == "Sudah ada yang bernama Rafli di stasiun."
    assert ("narrator", "Sudah ada yang bernama Rafli di stasiun.") in s.spoken
    client.connect(name="Rafli2", job="engineer")
    hello = s.connections[-1].hello()
    assert (hello["name"], hello["job"], hello["secret"]) == ("Rafli2", "engineer", "0" * 63 + "1")


@pytest.mark.parametrize("url, ok", [
    ("wss://infiartt.com/orbit/ws", True), ("ws://127.0.0.1:7340/orbit/ws", True),
    ("ws://localhost:7340/orbit/ws", True), ("ws://infiartt.com/orbit/ws", False),
    ("https://infiartt.com/orbit/ws", False), ("", False),
])
def test_only_encrypted_addresses_leave_this_computer(play, url, ok):
    assert play.client.connect(url) is ok
    if not ok:
        assert play.client.status.startswith("Alamat server harus diawali wss://")
        assert play.services.connections == []


def test_no_name_no_join(play):
    play.services.values["name"] = "  "
    assert play.client.connect() is False
    assert play.client.status.startswith("Pilih dulu nama karakter")


def test_what_the_connection_says(play):
    s, client = play.services, play.client
    client.connect()
    conn = s.connections[-1]
    conn.on_state("connecting", {"attempt": 0})
    assert client.status == "Menyambung ke Orbit..." and s.spoken == [("narrator", "Menyambung ke Orbit...")]
    conn.welcome()
    assert client.status == "Tersambung ke Orbit sebagai Rafli, Pilot."
    assert s.spoken[-1] == ("narrator", "Tersambung ke Orbit.") and s.ambiences[-1] == ("vent", 25)
    conn.on_state("offline", {"reason": "lost", "retry_in": 4.2})
    conn.on_state("connecting", {"attempt": 1})
    conn.on_state("offline", {"reason": "lost", "retry_in": 8.1})
    assert client.status == "Terputus, menyambung lagi dalam 8 detik..." and client.title_state == "Terputus"
    assert [t for _w, t in s.spoken].count("Orbit sedang offline. Aku coba terus, ya.") == 1
    assert s.ambiences[-1] == (None, None)
    conn.on_state("online", {})
    conn.on_message({"t": "welcome", "name": "Rafli", "job": "pilot", "resumed": True,
                     "room": "cantina", "amb": "cantina"})
    assert s.spoken[-1] == ("narrator", "Tersambung lagi.") and s.ambiences[-1] == ("cantina", 25)
    conn.on_state("failed", {"code": "kicked"})
    assert client.status == "Admin mengeluarkanmu dari stasiun. Sambungkan lagi nanti."
    assert client.conn is None


def test_messages_from_an_old_connection_are_ignored(play):
    s, client = play.services, play.client
    client.connect()
    old = s.connections[-1]
    client.connect("ws://127.0.0.1:1/orbit/ws")
    old.event("say", "Hantu bilang: boo", actor="Hantu")
    assert client.messages == []


def test_events_are_shown_played_and_said(play):
    s, client = play.services, play.client
    conn = _online(play)
    s.spoken.clear()
    conn.event("moved", "Kamu berjalan ke Kantin. Kantin.", room="cantina", amb="cantina")
    assert s.sounds[-1] == "door" and s.ambiences[-1] == ("cantina", 25)
    assert s.spoken[-1] == ("narrator", "Kamu berjalan ke Kantin. Kantin.")
    conn.event("said", "Kamu bilang: halo semua", brief="Terkirim.")
    assert client.messages[-1] == "Kamu bilang: halo semua" and s.spoken[-1] == ("narrator", "Terkirim.")
    assert s.sounds[-1] == "sent"
    conn.event("say", "Sari bilang: halo Rafli!", actor="Sari")
    sari = orbit_speech.pick_voice("Sari", orbit_speech.voices_of(FakeServices.VOICES, "id"))
    assert s.spoken[-1] == (sari["id"], "Sari bilang: halo Rafli!") and s.sounds[-1] == "say"
    conn.event("whisper", "Budi berbisik padamu: psst", actor="Budi")
    assert s.sounds[-1] == "whisper" and s.spoken[-1][0] != "narrator"
    conn.event("emote", "Sari tersenyum padamu.", actor="Sari")
    assert s.spoken[-1] == ("narrator", "Sari tersenyum padamu.")        # gestures: the narrator
    conn.event("arrive", "Budi datang dari Promenade.", actor="Budi")
    conn.event("paid", "Kamu dibayar 40 kredit.")
    conn.event("error", "Budi tidak ada di sini.")
    assert s.sounds[-3:] == ["arrive", "success", "error"]
    assert client.messages[-1] == "Budi tidak ada di sini."


def test_your_own_name_is_never_read_in_a_player_voice(play):
    s = play.services
    conn = _online(play, name="Rafli")
    conn.event("shout", "Rafli berteriak: tes", actor="Rafli")
    assert s.spoken[-1] == ("narrator", "Rafli berteriak: tes")


def test_one_voice_for_everyone_when_the_setting_is_off(play):
    s = play.services
    s.values["voices"] = False
    conn = _online(play)
    conn.event("say", "Sari bilang: halo", actor="Sari")
    assert s.spoken[-1] == ("narrator", "Sari bilang: halo")


def test_quiet_unless_aruna_asked(play):
    s, client = play.services, play.client
    s.values["speak"] = False
    conn = _online(play)
    count = len(s.spoken)
    conn.event("say", "Sari bilang: halo", actor="Sari")
    assert len(s.spoken) == count and client.messages[-1] == "Sari bilang: halo"
    assert s.sounds[-1] == "say"
    client.submit("orbit siapa online", "aruna")
    assert conn.sent[-1] == {"t": "cmd", "c": "who"}
    conn.event("who", "2 orang online: Rafli si pilot, di Dermaga; Sari si pilot, di Dermaga.")
    assert s.spoken[-1][1].startswith("2 orang online")
    conn.event("say", "Sari bilang: aku di sini", actor="Sari")
    assert s.spoken[-1] == (orbit_speech.pick_voice(
        "Sari", orbit_speech.voices_of(FakeServices.VOICES, "id"))["id"], "Sari bilang: aku di sini")
    assert s.shown == ["Sari bilang: aku di sini"]          # Aruna's Last result gets it too
    client.aruna_until = 0
    conn.event("say", "Sari bilang: sudah?", actor="Sari")
    assert s.spoken[-1][1] != "Sari bilang: sudah?"


def test_the_reactor_tones_play_before_the_line_is_read(play):
    s = play.services
    conn = _online(play)
    s.spoken.clear()
    conn.event("tones", "Dengarkan 3 nada penstabil: 2, 4, 1.", codes=[2, 4, 1])
    assert s.spoken == [] and len([t for t in s.timers if t.fn != play.client._tick]) == 4
    s.timers = [t for t in s.timers if t.fn != play.client._tick]
    s.run_timers()
    assert [x for x in s.sounds if x.startswith("tone")] == ["tone2", "tone4", "tone1"]
    assert s.spoken == [("narrator", "Dengarkan 3 nada penstabil: 2, 4, 1.")]


def test_the_slot_reels_stop_left_middle_right_before_the_result_is_read(play):
    s = play.services
    s.FILES = FakeServices.FILES | {"reel_spin", "reel_stop", "push", "dice", "win", "cards", "deal"}
    conn = _online(play)
    s.spoken.clear()
    s.placed.clear()
    s.timers = []
    conn.event("failed", "bintang, bulan, bintang. Sepasang: taruhanmu kembali.", sound="reel_spin",
               reels=["star", "moon", "star"], outcome="push")
    assert s.placed == [("reel_spin", 0.0, None)] and s.spoken == []
    assert sorted(round(t.seconds, 2) for t in s.timers) == [0.9, 1.3, 1.7, 2.0, 2.0]
    s.run_timers()
    assert [p[:2] for p in s.placed[1:]] == [("reel_stop", -0.75), ("reel_stop", 0.0), ("reel_stop", 0.75),
                                             ("push", 0.0)]
    assert s.spoken == [("narrator", "bintang, bulan, bintang. Sepasang: taruhanmu kembali.")]
    # the dice land, then you hear whether you won, then the words
    s.placed.clear()
    conn.event("paid", "Dadu keluar 5 dan 6: 11. Kamu menang 230 kredit!", sound="dice", outcome="win")
    assert s.placed[0][0] == "dice" and [round(t.seconds, 2) for t in s.timers] == [1.2, 1.2]
    s.run_timers()
    assert s.placed[-1][0] == "win" and s.spoken[-1][1].startswith("Dadu keluar 5 dan 6")
    # with the sounds off, nothing waits
    s.values["sounds"] = False
    conn.event("task", "Blackjack dengan taruhan 50 kredit.", sound="deal")
    assert not s.timers and s.spoken[-1][1] == "Blackjack dengan taruhan 50 kredit."


def test_new_floors_and_places_have_their_sounds():
    assert orbit_audio.cues_for({"k": "moved", "dir": "e", "floor": "wood"})[0][:2] == ("step_wood", 0.75)
    assert orbit_audio.cues_for({"k": "moved", "dir": "w", "floor": "snow"})[0][:2] == ("step_snow", -0.75)
    assert orbit_audio.cues_for({"k": "moved", "dir": "n", "floor": "lava"})[0][0] == "step_metal"
    assert {"mall", "casino"} <= set(orbit_audio.AMBIENCES)
    assert orbit_audio.timed_cues({"k": "paid", "sound": "coinflip", "outcome": "win"}) == \
        ([(0.9, "win", 0.0)], 0.9)
    assert orbit_audio.timed_cues({"k": "paid", "text": "x"}) == ([], 0.0)


def test_sounds_can_be_turned_off(play):
    s = play.services
    s.values["sounds"] = False
    conn = _online(play)
    conn.event("moved", "Kamu berjalan ke Kantin.", room="cantina", amb="cantina")
    conn.event("tones", "Dengarkan: 1.", codes=[1])
    assert s.sounds == [] and s.spoken[-1] == ("narrator", "Dengarkan: 1.")


def test_the_ambience_follows_the_room_the_window_and_the_settings(play):
    s, client = play.services, play.client
    conn = _online(play)
    assert s.ambiences[-1] == ("vent", 25)
    s.window = False
    client.update_ambience()
    assert s.ambiences[-1] == (None, None)
    s.window = True
    s.values["ambience_volume"] = 60
    conn.event("moved", "Ruang Mesin.", room="engineering", amb="engine")
    assert s.ambiences[-1] == ("engine", 60)
    s.values["ambience"] = False
    client.update_ambience()
    assert s.ambiences[-1] == (None, None)
    s.values["ambience"] = True
    client.disconnect()
    assert s.ambiences[-1] == (None, None) and s.spoken[-1] == ("narrator", "Kamu keluar dari Orbit.")


def test_commands_are_sent_or_wait_for_the_connection(play):
    s, client = play.services, play.client
    assert client.submit("   ") == "empty"
    assert client.submit("pergi ke kantin") == "queued"         # connects first
    conn = s.connections[-1]
    assert conn.sent == [{"t": "cmd", "c": "go", "a": "kantin"}]
    conn.welcome()
    assert client.submit("bilang halo") == "sent"
    assert conn.sent[-1] == {"t": "cmd", "c": "say", "a": "halo"}


def test_orbits_own_commands(play):
    s, client = play.services, play.client
    assert client.submit("ulangi") == "local"
    assert s.spoken[-1] == ("narrator", "Belum ada pesan.")
    client.submit("bantuan")
    assert client.messages[-1].startswith("Bantuan Orbit.") and s.spoken[-1][1].startswith("Bantuan Orbit.")
    client.submit("sambungkan")
    assert s.connections and s.connections[-1].started
    s.connections[-1].welcome()
    client.submit("sambungkan")
    assert s.spoken[-1] == ("narrator", "Tersambung ke Orbit sebagai Rafli, Pilot.")
    s.connections[-1].event("say", "Sari bilang: hai", actor="Sari")
    client.submit("ulangi")
    assert s.spoken[-1] == ("narrator", "Sari bilang: hai")
    client.submit("putuskan")
    assert s.connections[-1].stopped and client.status == "Belum tersambung."


def test_the_messages_keep_the_last_500(play):
    client = play.client
    notes = []
    client.add_listener(lambda event, value: notes.append((event, value)))
    for i in range(505):
        client.add_line(f"line {i}")
    assert len(client.messages) == 455 and client.messages[0] == "line 50"
    assert ("trim", 50) in notes

    def gone(event, value):
        raise RuntimeError("the window is gone")

    client.add_listener(gone)
    client.add_line("still fine")
    assert gone not in client.listeners


# ------------------------------------------------------------
# Who speaks
# ------------------------------------------------------------

def test_each_player_keeps_a_voice_of_their_own():
    voices = orbit_speech.voices_of(FakeServices.VOICES, "id")
    assert [v["id"] for v in voices] == ["id-ID-ArdiNeural", "id-ID-GadisNeural", "andika"]
    assert orbit_speech.voices_of(FakeServices.VOICES, "en") == [
        dict(FakeServices.VOICES["windows"][1], provider="windows")]
    names = ["Sari", "Budi", "Tono", "Ayu", "Rafli", "Dewi", "Joko", "Maya"]
    picked = {n: orbit_speech.pick_voice(n, voices)["id"] for n in names}
    assert picked["Sari"] == orbit_speech.pick_voice("sari", voices)["id"]
    assert len(set(picked.values())) >= 2                    # not everyone sounds the same
    # The narrator's own voice is left for the narrator when there are others.
    narrator = ("edge", "id-ID-ArdiNeural")
    assert all(orbit_speech.pick_voice(n, voices, exclude=narrator)["id"] != "id-ID-ArdiNeural"
               for n in names)
    assert orbit_speech.pick_voice("Sari", voices[:1]) is None       # one voice: the narrator
    assert orbit_speech.pick_voice("Sari", voices[:2], exclude=("edge", "id-ID-ArdiNeural"))


def test_the_same_voices_in_any_order_give_the_same_choice():
    voices = orbit_speech.voices_of(FakeServices.VOICES, "id")
    shuffled = orbit_speech.voices_of({"windows": FakeServices.VOICES["windows"],
                                       "edge": list(reversed(FakeServices.VOICES["edge"]))}, "id")
    for name in ("Sari", "Budi", "Rafli"):
        assert orbit_speech.pick_voice(name, voices) == orbit_speech.pick_voice(name, shuffled)


def test_the_voice_book_lists_in_the_background_and_keeps_it():
    now = [0.0]
    calls = []

    def list_voices(provider):
        calls.append(provider)
        if provider == "broken":
            raise OSError("offline")
        return FakeServices.VOICES.get(provider, [])

    book = orbit_speech.VoiceBook(lambda: ["edge", "broken", "windows", "piper"],
                                  lambda p: p != "piper", list_voices, clock=lambda: now[0])
    assert book.cached() is None
    found = book.refresh()
    assert set(found) == {"edge", "windows"} and calls == ["edge", "broken", "windows"]
    assert book.cached() == found
    now[0] = 601
    assert book.cached() is None
    book.forget()


class SpeakerServices:
    def __init__(self):
        self.log = []
        self.busy = False
        self.pending = []
        self.voiced = True
        self.fail = False
        self.timers = []

    def say(self, text):
        self.log.append(("narrator", text))
        return self.voiced

    def speak_voice(self, text, voice, on_done):
        if self.fail:
            on_done(RuntimeError("the voice failed"))
            return True
        self.log.append((voice, text))
        self.pending.append(on_done)
        return True

    def voice_busy(self):
        return self.busy

    def call_later(self, seconds, fn):
        timer = types.SimpleNamespace(fn=fn, cancel=lambda: None)
        self.timers.append(timer)
        return timer

    def call_after(self, fn, *args):
        fn(*args)

    def tick(self):
        timers, self.timers = self.timers, []
        for timer in timers:
            timer.fn()


def test_nobody_talks_over_anybody():
    services = SpeakerServices()
    now = [0.0]
    speaker = orbit_speech.Speaker(services, clock=lambda: now[0])
    speaker.say("Kamu berjalan ke Kantin.")
    speaker.say("Sari bilang: halo", voice="gadis")
    speaker.say("Budi datang.")
    assert services.log == [("narrator", "Kamu berjalan ke Kantin."), ("gadis", "Sari bilang: halo")]
    services.tick()
    assert len(services.log) == 2                   # the narrator waits for Sari's voice
    services.pending.pop()(None)
    assert services.log[-1] == ("narrator", "Budi datang.") and not speaker.busy()
    # A player's voice waits while Hariku Voice is busy...
    services.busy = True
    speaker.say("Budi bilang: hai", voice="ardi")
    assert services.log[-1] == ("narrator", "Budi datang.")
    services.busy = False
    services.tick()
    assert services.log[-1] == ("ardi", "Budi bilang: hai")
    services.pending.pop()(None)
    # ...and while the screen reader is probably still reading.
    services.voiced = False
    speaker.say("Satu kalimat panjang dari stasiun untuk dibaca.")
    speaker.say("Sari bilang: nah", voice="gadis")
    assert services.log[-1][0] == "narrator"
    now[0] += 10
    services.tick()
    assert services.log[-1] == ("gadis", "Sari bilang: nah")


def test_a_voice_that_fails_is_read_by_the_narrator():
    services = SpeakerServices()
    services.fail = True
    speaker = orbit_speech.Speaker(services)
    speaker.say("Sari bilang: halo", voice="gadis")
    assert services.log == [("narrator", "Sari bilang: halo")]


def test_a_busy_room_drops_the_oldest_waiting_lines():
    services = SpeakerServices()
    speaker = orbit_speech.Speaker(services)
    speaker.say("first", voice="gadis")
    for i in range(orbit_speech.MAX_WAITING + 5):
        speaker.say(f"line {i}")
    assert len(speaker.waiting) == orbit_speech.MAX_WAITING
    assert speaker.waiting[0][0] == ("line 5", None)


# ------------------------------------------------------------
# Sounds and the ambience
# ------------------------------------------------------------

def test_which_cues_an_event_plays_and_from_where():
    cues = orbit_audio.cues_for
    assert cues({"k": "moved", "dir": "w", "floor": "grass", "acoustics": "open"}) == [
        ("step_grass", -0.75, "open", "door")]
    assert cues({"k": "moved", "dir": "e"}) == [("step_metal", 0.75, None, "door")]
    assert cues({"k": "moved", "dir": "u", "via": "lift"}) == [("lift_up", 0.0, None, "door")]
    assert cues({"k": "moved", "dir": "d", "via": "lift"})[0][0] == "lift_down"
    assert cues({"k": "moved", "dir": "s", "via": "door", "acoustics": "small"}) == [
        ("door", 0.0, "small", None), ("step_metal", 0.0, "small", "door")]
    assert cues({"k": "moved"}) == [("door", 0.0, None, None)]                    # an old server
    assert cues({"k": "moved", "sound": "landing", "dir": "e"}) == [("landing", 0.0, None, "door")]
    assert cues({"k": "arrive", "dir": "nw", "acoustics": "hall"}) == [("arrive", -0.5, "hall", None)]
    assert cues({"k": "leave", "dir": "e"}) == [("leave", 0.75, None, None)]
    assert cues({"k": "emote", "emote": "clap", "actor": "Sari"}) == [("emote_clap", 0.0, None, "emote")]
    assert cues({"k": "emote"}) == [("emote", 0.0, None, "emote")]
    assert cues({"k": "paid", "sound": "levelup"}) == [("levelup", 0.0, None, "success")]
    assert cues({"k": "whisper", "actor": "Sari"}) == [("whisper", 0.0, None, None)]
    assert cues({"k": "room"}) == []
    assert orbit_audio.sound_for({"k": "flight", "sound": "launch"}) == "launch"
    assert orbit_audio.tone_names([1, "4", 9, "x", 2]) == ["tone1", "tone4", "tone2"]


class FakeMci:
    def __init__(self, mode="playing"):
        self.commands = []
        self.mode = mode
        self.fail = False

    def __call__(self, command):
        if self.fail:
            raise OSError(263, "MCI error 263")
        self.commands.append(command)
        if command.startswith("status"):
            return self.mode
        return ""

    def volumes(self):
        return [int(c.rsplit(" ", 1)[1]) for c in self.commands if c.startswith("setaudio")]


def _player(mci, speaking=lambda: False):
    now = [100.0]
    player = orbit_audio.AmbiencePlayer(mci=mci, pump=lambda: None, is_speaking=speaking,
                                        clock=lambda: now[0])
    return player, now


def _steps(player, now, count, dt=0.05):
    for _i in range(count):
        now[0] += dt
        player.step(now[0])


def test_the_ambience_fades_in_loops_and_hushes():
    mci = FakeMci()
    speaking = [False]
    player, now = _player(mci, lambda: speaking[0])
    player.apply("play", ("C:/sounds/amb_vent.wav", 30))
    _steps(player, now, 1)
    assert mci.commands[0] == 'open "C:/sounds/amb_vent.wav" type mpegvideo alias hariku_orbit_ambience'
    assert "play hariku_orbit_ambience repeat" in mci.commands
    _steps(player, now, 20)
    assert mci.volumes()[-1] == 300 and mci.volumes() == sorted(mci.volumes())       # faded in
    player.apply("hush", 2.0)
    _steps(player, now, 10)
    assert mci.volumes()[-1] == 0                  # quiet while the screen reader reads
    _steps(player, now, 40)
    assert mci.volumes()[-1] == 300
    speaking[0] = True
    _steps(player, now, 10)
    assert mci.volumes()[-1] == 0                  # and while Hariku Voice speaks
    speaking[0] = False
    player.apply("volume", 10)
    _steps(player, now, 20)
    assert mci.volumes()[-1] == 100


def test_the_ambience_fades_out_before_changing_place():
    mci = FakeMci()
    player, now = _player(mci)
    player.apply("play", ("vent.wav", 50))
    _steps(player, now, 20)
    player.apply("play", ("cantina.wav", 50))
    _steps(player, now, 30)
    opened = [c for c in mci.commands if c.startswith("open")]
    assert opened == ['open "vent.wav" type mpegvideo alias hariku_orbit_ambience',
                      'open "cantina.wav" type mpegvideo alias hariku_orbit_ambience']
    close_at = mci.commands.index("close hariku_orbit_ambience")
    before = [int(c.rsplit(" ", 1)[1]) for c in mci.commands[:close_at] if c.startswith("setaudio")]
    assert before[-1] == 0                          # faded out first
    player.apply("play", (None, None))
    _steps(player, now, 30)
    assert mci.commands[-1] == "close hariku_orbit_ambience" and player.playing is None


def test_a_device_that_does_not_repeat_is_restarted():
    mci = FakeMci(mode="stopped")
    player, now = _player(mci)
    player.apply("play", ("vent.wav", 50))
    _steps(player, now, 3, dt=0.6)
    assert "seek hariku_orbit_ambience to start" in mci.commands


def test_no_ambience_where_mci_fails():
    mci = FakeMci()
    mci.fail = True
    player, now = _player(mci)
    player.apply("play", ("vent.wav", 50))
    _steps(player, now, 5)
    assert player.broken and player.playing is None


def test_nothing_piles_up_while_no_loop_plays():
    # Every line Hariku says hushes the ambience; with the window closed there
    # is no loop and no thread, and those calls must not queue up forever.
    player = orbit_audio.AmbiencePlayer(mci=FakeMci(), pump=lambda: None)
    for _i in range(100):
        player.hush(1.0)
        player.stop()
        player.set_volume(10)
    assert player._commands.qsize() == 0 and player._thread is None and player.volume == 10


def test_the_ambience_thread_starts_and_stops():
    mci = FakeMci()
    player = orbit_audio.AmbiencePlayer(mci=mci, pump=lambda: None)
    player.play("vent.wav", 20)
    end = time.monotonic() + 3
    while not any(c.startswith("open") for c in mci.commands) and time.monotonic() < end:
        time.sleep(0.02)
    assert any(c.startswith("open") for c in mci.commands)
    player.shutdown(wait=2)
    assert mci.commands[-1] == "close hariku_orbit_ambience"


# ------------------------------------------------------------
# The connection thread, with a fake socket
# ------------------------------------------------------------

class FakeClient:
    """Stands for orbit_ws.WebSocketClient: a script of what comes in."""

    def __init__(self, incoming, drop_after=None):
        self.incoming = list(incoming)
        self.sent = []
        self.pings = 0
        self.closed = None
        self.last_received = time.monotonic()
        self.drop_after = drop_after

    def send_json(self, message):
        self.sent.append(message)

    def recv(self, timeout=None):
        if self.incoming:
            item = self.incoming.pop(0)
            if isinstance(item, Exception):
                raise item
            self.last_received = time.monotonic()
            return item
        if self.drop_after is not None:
            raise orbit_ws.ConnectionClosed(orbit_ws.CLOSE_ABNORMAL, "lost")
        time.sleep(min(timeout or 0.01, 0.01))
        return None

    def ping(self):
        self.pings += 1

    def close(self, code=1000, reason="", wait=1.0):
        self.closed = code


def _connection(clients, **kwargs):
    events = []
    made = []
    lock = threading.Lock()

    def connect(url):
        with lock:
            client = clients.pop(0) if clients else None
        if client is None:
            raise OSError("refused")
        made.append(client)
        return client

    hellos = []

    def hello():
        hellos.append(1)
        return {"t": "hello", "n": len(hellos)}

    conn = orbit_net.Connection("wss://example.org/orbit/ws", hello,
                                lambda m: events.append(("message", m)),
                                lambda s, i: events.append(("state", s, i)),
                                connect=connect, backoff=(0.01, 0.02), **kwargs)
    return conn, events, made, hellos


def _wait(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


WELCOME = '{"t": "welcome", "name": "Rafli"}'


def test_the_connection_says_hello_flushes_and_delivers():
    client = FakeClient([WELCOME, '{"t": "ev", "k": "room", "text": "Dermaga."}', "not json"])
    conn, events, made, _hellos = _connection([client])
    conn.send({"t": "cmd", "c": "look"})               # before connecting: waits
    conn.start()
    assert _wait(lambda: ("message", {"t": "ev", "k": "room", "text": "Dermaga."}) in events)
    assert client.sent[0] == {"t": "hello", "n": 1} and client.sent[1] == {"t": "cmd", "c": "look"}
    states = [e[1] for e in events if e[0] == "state"]
    assert states[:2] == ["connecting", "online"]
    conn.send({"t": "cmd", "c": "who"})
    assert _wait(lambda: {"t": "cmd", "c": "who"} in client.sent)
    conn.stop()
    assert client.closed == 1000 and events[-1] == ("state", "stopped", None)
    assert conn.send({"t": "cmd"}) is False


def test_the_connection_comes_back_by_itself():
    first = FakeClient([WELCOME], drop_after=True)
    second = FakeClient([WELCOME])
    conn, events, made, hellos = _connection([None, first, second])
    # (None: the first attempt is refused outright)
    conn.start()
    assert _wait(lambda: len(made) == 2 and [e[1] for e in events if e[0] == "state"].count("online") == 2)
    offline = [e[2] for e in events if e[0] == "state" and e[1] == "offline"]
    assert len(offline) == 2 and all(o["retry_in"] > 0 for o in offline)
    assert len(hellos) == 2          # no hello without a connection
    conn.stop()


def test_a_refused_hello_is_not_retried():
    client = FakeClient(['{"t": "err", "code": "name_taken", "text": "Taken.", "fatal": true}'])
    conn, events, made, _hellos = _connection([client, FakeClient([WELCOME])])
    conn.start()
    assert _wait(lambda: any(e[0] == "state" and e[1] == "failed" for e in events))
    assert _wait(lambda: not conn._thread.is_alive())
    assert len(made) == 1 and events[-1][2]["code"] == "name_taken"


def test_kicked_or_replaced_connections_stay_closed():
    client = FakeClient([WELCOME, orbit_ws.ConnectionClosed(4001, "replaced")])
    conn, events, made, _hellos = _connection([client, FakeClient([WELCOME])])
    conn.start()
    assert _wait(lambda: any(e[0] == "state" and e[1] == "failed" for e in events))
    assert events[-1] == ("state", "failed", {"code": "replaced"}) and len(made) == 1


def test_old_commands_are_not_sent_late(monkeypatch):
    monkeypatch.setattr(orbit_net, "QUEUE_MAX_AGE", 0.05)
    client = FakeClient([WELCOME])
    conn, events, made, _hellos = _connection([client])
    conn.send({"t": "cmd", "c": "say", "a": "stale"})
    time.sleep(0.1)
    conn.send({"t": "cmd", "c": "say", "a": "fresh"})
    conn.start()
    assert _wait(lambda: {"t": "cmd", "c": "say", "a": "fresh"} in client.sent)
    assert {"t": "cmd", "c": "say", "a": "stale"} not in client.sent
    conn.stop()


# ------------------------------------------------------------
# Settings from the game, what is read, and who is heard
# ------------------------------------------------------------

def test_quick_settings_from_the_game(play):
    s, client = play.services, play.client
    conn = _online(play)
    assert conn.sent == []
    assert client.submit("suara pemain mati") == "local"
    assert s.values["voices"] is False and s.spoken[-1] == ("narrator", "Suara pemain mati: semua dibacakan suaramu yang biasa.")
    client.submit("bacakan pesan mati")
    assert s.values["speak"] is False
    assert s.spoken[-1] == ("narrator", "Pesan tidak dibacakan sekarang; tetap masuk daftar Pesan.")   # said anyway
    client.submit("volume efek 40")
    assert s.values["effects_volume"] == 40 and client.messages[-1] == "Volume efek 40 persen."
    client.submit("ambience mati")
    assert s.values["ambience"] is False and s.ambiences[-1] == (None, None)
    client.submit("pengaturan")
    assert s.settings_opened == 1
    assert conn.sent == []                                   # none of it went to the server


def test_what_is_read_can_be_narrowed(play):
    s, client = play.services, play.client
    s.values.update(read_say=False, read_moves=False, read_money=False)
    conn = _online(play)
    count = len(s.spoken)
    conn.event("say", "Sari bilang: halo", actor="Sari")
    conn.event("emote", "Sari tersenyum.", actor="Sari", emote="smile")
    conn.event("arrive", "Budi datang dari arah barat, dari Dermaga.", actor="Budi", dir="w")
    conn.event("paid", "Kamu dibayar 40 kredit.")
    assert len(s.spoken) == count                           # not read...
    assert client.messages[-4:] == ["Sari bilang: halo", "Sari tersenyum.",
                                    "Budi datang dari arah barat, dari Dermaga.", "Kamu dibayar 40 kredit."]
    assert s.sounds[-4:] == ["say", "emote", "arrive", "success"]               # ...but heard
    conn.event("whisper", "Budi berbisik padamu: psst", actor="Budi")
    conn.event("emote", "Kamu tersenyum.", emote="smile")   # your own gesture: always
    assert s.spoken[-1] == ("narrator", "Kamu tersenyum.") and s.spoken[-2][1] == "Budi berbisik padamu: psst"
    client.submit("orbit siapa online", "aruna")
    conn.event("say", "Sari bilang: aku di sini", actor="Sari")
    assert s.spoken[-1][1] == "Sari bilang: aku di sini"   # Aruna asked: everything is read


def test_with_the_window_closed_only_what_matters_is_heard(play):
    s, client = play.services, play.client
    conn = _online(play, name="Rafli")
    s.window = False
    s.spoken.clear()
    s.sounds.clear()
    conn.event("say", "Sari bilang: halo semua", actor="Sari")
    conn.event("arrive", "Budi datang.", actor="Budi", dir="n")
    assert s.spoken == [] and s.sounds == []                # quiet, and shown
    assert client.messages[-1] == "Budi datang."
    conn.event("say", "Sari bilang: Rafli, ke kantin yuk", actor="Sari")
    conn.event("whisper", "Budi berbisik padamu: psst", actor="Budi")
    conn.event("announce", "Pengumuman dari Anjungan: server restart jam 9")
    assert [line for _who, line in s.spoken] == ["Sari bilang: Rafli, ke kantin yuk",
                                                  "Budi berbisik padamu: psst",
                                                  "Pengumuman dari Anjungan: server restart jam 9"]
    assert s.sounds == ["say", "whisper", "announce"]
    s.values["background"] = "none"
    conn.event("whisper", "Budi berbisik padamu: halo?", actor="Budi")
    assert len(s.spoken) == 3 and len(s.sounds) == 3
    s.values["background"] = "all"
    conn.event("say", "Sari bilang: dadah", actor="Sari")
    assert s.spoken[-1][1] == "Sari bilang: dadah"


def test_ignored_players_are_neither_shown_nor_heard(play):
    s, client = play.services, play.client
    conn = _online(play)
    client.submit("abaikan Budi")
    assert s.values["ignored"] == ["Budi"] and client.messages[-1].startswith("Mengabaikan Budi")
    lines = len(client.messages)
    conn.event("say", "Budi bilang: hoi", actor="Budi")
    conn.event("shout", "Budi berteriak: HOI", actor="Budi")
    conn.event("emote", "Budi melambai padamu.", actor="budi", emote="wave")
    conn.event("offer", "Budi mengundangmu ke kabinnya.", actor="Budi", ask=True)
    assert len(client.messages) == lines
    conn.event("arrive", "Budi datang.", actor="Budi")      # where they are still shows
    assert client.messages[-1] == "Budi datang."
    client.submit("dengar lagi budi")
    assert s.values["ignored"] == []
    conn.event("say", "Budi bilang: maaf", actor="Budi")
    assert client.messages[-1] == "Budi bilang: maaf"


def test_other_players_sounds_can_be_turned_off(play):
    s = play.services
    s.values["other_sounds"] = False
    conn = _online(play)
    s.sounds.clear()
    conn.event("say", "Sari bilang: halo", actor="Sari")
    conn.event("arrive", "Budi datang.", actor="Budi", dir="w")
    conn.event("whisper", "Budi berbisik padamu: psst", actor="Budi")
    conn.event("paid", "Kamu dibayar.")
    assert s.sounds == ["whisper", "success"]


def test_cues_come_from_their_side_with_a_fallback(play):
    s = play.services
    conn = _online(play)
    s.placed.clear()
    conn.event("moved", "Kamu berjalan ke barat.", dir="w", floor="metal", acoustics="hall", room="x", amb="vent")
    conn.event("moved", "Kamu berjalan ke timur.", dir="e", floor="grass", room="y", amb="garden")
    conn.event("arrive", "Budi datang dari arah timur.", actor="Budi", dir="e")
    conn.event("paid", "Naik level!", sound="levelup")
    conn.event("paid", "Kamu memanen.", sound="harvest")
    assert s.placed == [("step_metal", -0.75, "hall"), ("door", 0.75, "hall"), ("arrive", 0.75, "hall"),
                        ("levelup", 0.0, None), ("success", 0.0, None)]


def test_a_chosen_voice_and_its_preview(play):
    s = play.services
    conn = _online(play, name="Rafli")
    voices = orbit_speech.voices_of(FakeServices.VOICES, "id")
    conn.event("say", "Sari bilang: halo", actor="Sari", voice=2)
    assert s.spoken[-1] == (voices[1]["id"], "Sari bilang: halo")
    conn.event("say", "Budi bilang: halo", actor="Budi", voice=5)
    assert s.spoken[-1] == (voices[(5 - 1) % 3]["id"], "Budi bilang: halo")
    conn.event("info", "Beres: orang lain sekarang mendengarmu dengan suara 3.", voice=3, preview=True)
    assert s.spoken[-1] == (voices[2]["id"], "Beres: orang lain sekarang mendengarmu dengan suara 3.")


def test_a_players_name_and_their_words_come_in_two_voices(play):
    s = play.services
    conn = _online(play, name="Rafli")
    voices = orbit_speech.voices_of(FakeServices.VOICES, "id")
    sari = orbit_speech.pick_voice("Sari", voices)["id"]
    s.spoken.clear()
    conn.event("say", "Sari bilang: halo semua", actor="Sari", words="halo semua")
    assert s.spoken == [("narrator", "Sari:"), (sari, "halo semua")]
    conn.event("whisper", "Sari berbisik padamu: nanti ya", actor="Sari", words="nanti ya", voice=2)
    assert s.spoken[-2:] == [("narrator", "Sari berbisik:"), (voices[1]["id"], "nanti ya")]
    conn.event("shout", "Sari berteriak ke seluruh stasiun: ke Bulan!", actor="Sari", words="ke Bulan!")
    assert s.spoken[-2:] == [("narrator", "Sari berteriak:"), (sari, "ke Bulan!")]
    assert play.client.messages[-1] == "Sari berteriak ke seluruh stasiun: ke Bulan!"   # the whole line
    s.values["speak_names"] = False
    conn.event("say", "Sari bilang: tanpa nama", actor="Sari", words="tanpa nama")
    assert s.spoken[-1] == (sari, "tanpa nama") and s.spoken[-2] != ("narrator", "Sari:")
    # an older server (no "words"): the whole line in the speaker's voice, as before
    conn.event("say", "Sari bilang: server lama", actor="Sari")
    assert s.spoken[-1] == (sari, "Sari bilang: server lama")


def test_your_own_lines_are_spoken_in_your_character_voice(play):
    s = play.services
    conn = _online(play, name="Rafli")
    voices = orbit_speech.voices_of(FakeServices.VOICES, "id")
    s.spoken.clear()
    conn.event("said", "Kamu bilang: halo Sari", brief="Terkirim.", words="halo Sari", voice=3)
    assert s.spoken == [(voices[2]["id"], "halo Sari")]
    conn.event("said", "Kamu bilang: tanpa nomor", brief="Terkirim.", words="tanpa nomor")
    assert s.spoken[-1] == (orbit_speech.pick_voice("Rafli", voices)["id"], "tanpa nomor")
    conn.event("whispered", "Kamu berbisik ke Sari: nanti ya", brief="Dibisikkan ke Sari.", words="nanti ya",
               to="Sari", voice=3)
    assert s.spoken[-2:] == [("narrator", "Ke Sari:"), (voices[2]["id"], "nanti ya")]
    conn.event("shouted", "Kamu berteriak: halo!", brief="Diteriakkan.", words="halo!", voice=3)
    assert s.spoken[-1] == (voices[2]["id"], "halo!")
    conn.event("emote", "Kamu tersenyum.", emote="smile")
    assert s.spoken[-1] == ("narrator", "Kamu tersenyum.")                  # gestures: the narrator
    play.client.aruna_until = float("inf")                                  # said through Aruna
    conn.event("said", "Kamu bilang: dari Aruna", brief="Terkirim.", words="dari Aruna", voice=3)
    assert s.spoken[-1] == (voices[2]["id"], "dari Aruna") and s.shown[-1] == "Terkirim."
    play.client.aruna_until = 0
    # the setting off: only the short confirmation, as before
    play.client.submit("kata-kataku mati")
    assert s.values["speak_own"] is False and s.spoken[-1] == ("narrator", "Kata-katamu sendiri hanya dikonfirmasi.")
    conn.event("said", "Kamu bilang: halo lagi", brief="Terkirim.", words="halo lagi", voice=3)
    assert s.spoken[-1] == ("narrator", "Terkirim.")
    play.client.submit("my lines on")
    assert s.values["speak_own"] is True
    play.client.submit("nama pemain mati")
    assert s.values["speak_names"] is False and s.spoken[-1][1] == "Hanya kata-kata pemain yang diucapkan, tanpa namanya."


def test_with_too_few_voices_everyone_is_read_by_the_narrator_and_you_are_told_once(play):
    s = play.services
    s.voices_on = False                          # Hariku Voice has only one voice of this language
    conn = _online(play, name="Rafli")
    s.spoken.clear()
    conn.event("say", "Sari bilang: halo", actor="Sari", words="halo")
    hint = ("narrator", "Hariku Voice punya kurang dari dua suara bahasamu, jadi semua pemain terdengar sama. "
                        "Agar tiap pemain punya suara sendiri, pasang Edge Voices atau Piper Voices dari Toko Ekstensi.")
    assert s.spoken == [hint, ("narrator", "Sari bilang: halo")]
    assert hint[1] in play.client.messages
    conn.event("said", "Kamu bilang: hai", brief="Terkirim.", words="hai")
    conn.event("say", "Sari bilang: lagi", actor="Sari", words="lagi")
    assert s.spoken[2:] == [("narrator", "hai"), ("narrator", "Sari bilang: lagi")]      # told once
    # players' voices turned off: no hint needed, the narrator reads
    s.values["voices"] = False
    play.client.voices_hint_said = False
    conn.event("say", "Sari bilang: tanpa suara", actor="Sari", words="tanpa suara")
    assert s.spoken[-1] == ("narrator", "Sari bilang: tanpa suara") and hint not in s.spoken[4:]


def test_the_narrator_is_hariku_voice_when_it_can_speak(play):
    s = play.services
    s.narrator = {"provider": "windows", "id": "andika"}
    conn = _online(play, name="Rafli")
    s.spoken.clear()
    conn.event("room", "Kantin. Meja-meja bundar.")
    conn.event("say", "Sari bilang: halo", actor="Sari", words="halo")
    sari = orbit_speech.pick_voice("Sari", orbit_speech.voices_of(FakeServices.VOICES, "id"))["id"]
    assert s.spoken == [("andika", "Kantin. Meja-meja bundar."), ("andika", "Sari:"), (sari, "halo")]


def test_a_busy_room_drops_whole_lines_never_half_of_one():
    services = SpeakerServices()
    speaker = orbit_speech.Speaker(services)
    speaker.say("first", voice="gadis")                  # still speaking
    for i in range(orbit_speech.MAX_WAITING + 3):
        speaker.say_parts([("Sari:", None), (f"line {i}", "gadis")])
    assert len(speaker.waiting) == orbit_speech.MAX_WAITING
    assert list(speaker.waiting[0]) == [("Sari:", None), ("line 3", "gadis")]
    while services.pending:
        services.pending.pop(0)(None)
    spoken = [text for _who, text in services.log]
    assert spoken[:3] == ["first", "Sari:", "line 3"] and spoken[-2:] == ["Sari:", f"line {orbit_speech.MAX_WAITING + 2}"]


def test_numbered_voices_are_the_same_on_every_turn():
    voices = orbit_speech.voices_of(FakeServices.VOICES, "id")
    assert [orbit_speech.pick_voice("anyone", voices, number=n)["id"] for n in (1, 2, 3, 4)] == \
        ["id-ID-ArdiNeural", "id-ID-GadisNeural", "andika", "id-ID-ArdiNeural"]
    assert orbit_speech.pick_voice("Sari", voices, number=0) == orbit_speech.pick_voice("Sari", voices)
    assert orbit_speech.pick_voice("Sari", voices[:1], number=2) is None
    narrator = ("edge", "id-ID-ArdiNeural")
    assert orbit_speech.pick_voice("x", voices, exclude=narrator, number=1)["id"] == "id-ID-GadisNeural"


# ------------------------------------------------------------
# Closing, leaving, being away, the status
# ------------------------------------------------------------

def test_closing_the_window_stays_connected_and_says_how_to_come_back(play):
    s, client = play.services, play.client
    conn = _online(play)
    for _i in range(3):
        assert client.window_closing() is False
        assert s.spoken[-1] == ("narrator", "Orbit tetap tersambung. Buka lagi dengan Ctrl + Shift + O, "
                                            "atau bilang ke Aruna: buka orbit. Untuk keluar, ketik keluar.")
    client.window_closing()
    assert s.spoken[-1] == ("narrator", "Orbit di latar belakang.") and s.values["close_hints"] == 3
    assert not conn.stopped and client.online()
    s.values.update(close_hints=0)
    s.key = ""
    client.window_closing()
    assert "bilang ke Aruna: buka orbit" in s.spoken[-1][1] and "dengan ," not in s.spoken[-1][1]


def test_closing_the_window_can_leave_orbit(play):
    s, client = play.services, play.client
    s.values["close_action"] = "leave"
    conn = _online(play)
    assert client.window_closing() is True
    assert conn.sent[-1] == {"t": "cmd", "c": "bye"} and conn.stopped
    assert client.status == "Belum tersambung." and client.title_state == "Keluar"


def test_leaving_says_goodbye_to_the_server(play):
    s, client = play.services, play.client
    conn = _online(play)
    client.submit("keluar")
    assert conn.sent == [{"t": "cmd", "c": "bye"}] and conn.stopped
    assert s.spoken[-1] == ("narrator", "Kamu keluar dari Orbit.")
    conn = _online(play)
    client.shutdown()                                         # Hariku is closing
    assert conn.sent[-1] == {"t": "cmd", "c": "bye"} and conn.stopped
    client.connect()
    offline = s.connections[-1]
    client.disconnect()                                       # never online: nothing to say goodbye to
    assert offline.sent == []


def test_away_then_logged_out_when_idle_with_the_window_closed(play):
    s = play.services
    now = [1000.0]
    client = orbit_play.OrbitClient(s, clock=lambda: now[0])
    client.connect()
    conn = s.connections[-1]
    conn.welcome()
    assert any(t.fn == client._tick for t in s.timers)
    now[0] += 400
    client.check_idle()
    assert client.away is False                               # the window is open
    s.window = False
    client.check_idle()
    assert client.away is True and conn.sent[-1] == {"t": "cmd", "c": "away", "on": True}
    client.check_idle()
    assert conn.sent.count({"t": "cmd", "c": "away", "on": True}) == 1
    client.submit("lihat")
    assert client.away is False and conn.sent[-1] == {"t": "cmd", "c": "look"}
    now[0] += 30 * 60
    client.check_idle()
    assert "Kamu otomatis keluar dari Orbit karena lama tidak aktif." in [t for _w, t in s.spoken]
    assert conn.sent[-1] == {"t": "cmd", "c": "bye"} and client.conn is None
    s.values["auto_logout"] = 0                               # never
    client.connect()
    s.connections[-1].welcome()
    now[0] += 10 * 3600
    client.check_idle()
    assert client.online()


def test_the_status_everywhere(play):
    s, client = play.services, play.client
    assert client.submit("status") == "local"
    assert s.spoken[-1] == ("narrator", "Belum tersambung.")
    conn = _online(play)
    client.submit("orbit status", "aruna")
    assert conn.sent[-1] == {"t": "cmd", "c": "status"}
    assert client.title_state == "Tersambung"
    conn.on_state("offline", {"reason": "lost", "retry_in": 8})
    assert client.title_state == "Terputus"
    client.submit("status")
    assert s.spoken[-1] == ("narrator", "Terputus, menyambung lagi dalam 8 detik...")


# ------------------------------------------------------------
# Moving a character to another computer
# ------------------------------------------------------------

def test_a_transfer_code_is_asked_for_shown_and_used(play):
    s, client = play.services, play.client
    notes = []
    client.add_listener(lambda event, value: notes.append((event, value)))
    assert client.request_transfer_code() is False            # not connected
    conn = _online(play)
    assert client.request_transfer_code() is True and conn.sent[-1] == {"t": "cmd", "c": "transfer"}
    conn.event("info", "Kode pindahmu: A B C D, ...", transfer_code="ABCD-EFGH-JKLM-NPQR", expires=600)
    assert client.transfer_code == "ABCD-EFGH-JKLM-NPQR" and ("transfer", "ABCD-EFGH-JKLM-NPQR") in notes
    # The other computer.
    other = FakeServices()
    elsewhere = orbit_play.OrbitClient(other)
    assert elsewhere.redeem_transfer("abcd efgh jklm npq") is False     # 15 letters
    assert other.connections == []
    assert elsewhere.redeem_transfer("abcd-efgh-jklm-npqr") is True
    hello = other.connections[-1].hello()
    assert hello == {"t": "hello", "v": 1, "client": "Hariku Orbit 1.1", "lang": "id",
                     "secret": "0" * 63 + "1", "transfer": "ABCDEFGHJKLMNPQR"}
    other.connections[-1].welcome(name="Rafli")
    account = other.accounts["wss://infiartt.com/orbit/ws"]
    assert account == {"secret": "0" * 63 + "1", "name": "Rafli", "job": "pilot", "joined": True}
    assert "transfer" not in other.connections[-1].hello()    # reconnecting uses the new secret


def test_a_refused_transfer_keeps_the_old_character(play):
    s, client = play.services, play.client
    _online(play)
    old = dict(s.accounts[s.values["server"]])
    client.redeem_transfer("ABCD-EFGH-JKLM-NPQR")
    s.connections[-1].on_state("failed", {"t": "err", "code": "transfer_bad",
                                          "text": "Kode pindah itu tidak berlaku."})
    assert s.accounts[s.values["server"]] == old
    assert client.status == "Kode pindah itu tidak berlaku."


# ------------------------------------------------------------
# The mixer: finding cues, and placing them
# ------------------------------------------------------------

import orbit_mix  # noqa: E402


def _tone_wav(path, seconds=0.2, rate=8000, channels=1, amp=12000):
    import struct as _struct
    n = int(seconds * rate)
    frames = []
    for i in range(n):
        v = int(amp * math.sin(2 * math.pi * 440 * i / rate))
        frames.extend([v] * channels)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(_struct.pack("<%dh" % len(frames), *frames))


def test_the_mixer_finds_cues_in_order_with_variants_and_fallbacks(tmp_path):
    mine, theme, builtin = tmp_path / "mine", tmp_path / "theme", tmp_path / "builtin"
    for folder in (mine, theme, builtin):
        folder.mkdir()
    for name in ("step_metal_1.wav", "step_metal_2.wav", "emote.wav", "bell.wav"):
        _tone_wav(builtin / name)
    _tone_wav(theme / "bell.wav")
    _tone_wav(mine / "step_metal.wav")
    mixer = orbit_mix.Mixer(lambda: [str(mine), str(theme), str(builtin)], str(tmp_path / "cache"),
                            rng=random.Random(3))
    assert mixer.variants("step_metal") == [str(mine / "step_metal.wav")]     # yours come first
    assert mixer.variants("bell") == [str(theme / "bell.wav")]                # then the theme's
    assert mixer.variants("emote_clap") == [str(builtin / "emote.wav")]       # a shorter name
    (mine / "step_metal.wav").unlink()
    assert mixer.variants("step_metal") == [str(builtin / "step_metal_1.wav"), str(builtin / "step_metal_2.wav")]
    picked = {mixer.render("step_metal") for _ in range(20)}
    assert picked == set(mixer.variants("step_metal"))                        # variants, at random
    assert mixer.variants("nothing") == [] and mixer.render("nothing") is None
    assert mixer.variants("../secret") == [] and mixer.variants("Bell") == []


def test_the_mixer_places_sounds_left_and_right_and_in_rooms(tmp_path):
    _tone_wav(tmp_path / "tick.wav")
    mixer = orbit_mix.Mixer(lambda: [str(tmp_path)], str(tmp_path / "cache"), rng=random.Random(1))
    source = str(tmp_path / "tick.wav")
    assert mixer.render("tick") == source                                     # nothing to change
    left = mixer.render("tick", pan=-0.75)
    right = mixer.render("tick", pan=0.75)

    def loudness(path):
        channels, _rate, samples = orbit_mix.read_wav(path)
        assert channels == 2
        l = math.sqrt(sum(v * v for v in samples[0::2]) / (len(samples) / 2))
        r = math.sqrt(sum(v * v for v in samples[1::2]) / (len(samples) / 2))
        return l, r

    l, r = loudness(left)
    assert l > 2 * r
    l, r = loudness(right)
    assert r > 2 * l
    quiet = loudness(mixer.render("tick", volume=0.3))
    assert 0.25 * 12000 / math.sqrt(2) < quiet[0] < 0.35 * 12000 / math.sqrt(2)
    hall = mixer.render("tick", acoustics="hall")
    with wave.open(hall) as w, wave.open(source) as dry:
        assert w.getnframes() > dry.getnframes() * 1.5                        # the echo rings on
    assert mixer.render("tick", pan=-0.75) == left                            # made once, kept
    first = open(left, "rb").read()
    other = orbit_mix.Mixer(lambda: [str(tmp_path)], str(tmp_path / "cache2"), rng=random.Random(9))
    assert open(other.render("tick", pan=-0.75), "rb").read() == first        # the same every time


# ------------------------------------------------------------
# The sounds
# ------------------------------------------------------------

def _read(name):
    with wave.open(os.path.join(SOUNDS_DIR, name)) as w:
        frames = w.readframes(w.getnframes())
        return (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes(),
                memoryview(frames).cast("h"))


def _server_cues():
    """Every cue the server names in an event's "sound", and the gestures it knows."""
    import json
    import re
    server = os.path.join(ROOT, "servers", "orbit")
    found = set()
    for name in os.listdir(server):
        if name.endswith(".py"):
            with open(os.path.join(server, name), encoding="utf-8") as f:
                text = f.read()
            for m in re.finditer(r'sound(?:"\s*:\s*|=)"([a-z_]+)"(?:\s+if\s+.*?\s+else\s+"([a-z_]+)")?', text):
                found.update(w for w in m.groups() if w and not w.endswith("_"))
    found.update({"pet_robot", "pet_cat"})
    with open(os.path.join(server, "world.json"), encoding="utf-8") as f:
        world = json.load(f)
    found.update(f"emote_{e}" for e in world["emotes"])
    found.update(f"step_{loc.get('floor', 'metal')}" for loc in world["locations"].values())
    return found


def _wavs():
    return sorted(n for n in os.listdir(SOUNDS_DIR) if n.endswith(".wav"))


def test_every_cue_has_a_sound():
    import orbit_sounds
    assert _wavs() == orbit_sounds.FILES
    assert not {name for name, _make in orbit_sounds.SOUNDS} & set(orbit_sounds.RECORDED)
    mixer = orbit_mix.Mixer(lambda: [SOUNDS_DIR], SOUNDS_DIR)
    needed = set(orbit_audio.KIND_CUES.values()) | {"arrive", "leave", "door", "emote"}
    needed |= {f"step_{floor}" for floor in orbit_audio.FLOORS}
    needed |= {cue for pair in orbit_audio.VIA_CUES.values() for cue in pair}
    needed |= {f"tone{i}" for i in range(1, 5)} | {f"amb_{a}" for a in orbit_audio.AMBIENCES}
    needed |= _server_cues()
    assert {"levelup", "harvest", "mine", "rare", "bump", "locked", "air", "rescue", "bell",
            "lantern", "gulp", "crunch", "emote_clap", "step_grass"} <= needed      # the list is real
    missing = sorted(cue for cue in needed if not mixer.variants(cue))
    assert not missing, missing
    assert not sorted(needed - set(orbit_sounds.CUES))        # each its own file, not a fallback


def test_the_sounds_are_polite_and_positional_ones_are_mono():
    import orbit_sounds
    for name in orbit_sounds.FILES:
        channels, width, rate, frames, samples = _read(name)
        assert channels in (1, 2) and width == 2, name
        seconds = frames / rate
        loudest = max(abs(v) for v in samples)
        assert 0.15 * 32767 < loudest < 0.6 * 32767, name
        if name.startswith("amb_"):
            assert channels == 2 and rate in (orbit_sounds.LOOP_RATE, orbit_sounds.SMALL_LOOP_RATE), name
            assert seconds == orbit_sounds.LOOP_SECONDS, name
        else:
            assert 0.1 <= seconds <= 3.3 and rate == orbit_sounds.RATE, name
            step = channels
            assert abs(samples[0]) < 300 and abs(samples[-1]) < 300, name            # no clicks
            assert abs(samples[step - 1]) < 300, name
    for cue in ("step_metal_1", "arrive", "leave", "emote_clap_1", "door_1", "bump_1", "ladder_1"):
        assert _read(cue + ".wav")[0] == 1, cue          # placed by the mixer at play time


def test_the_recorded_sounds_are_mono_22khz_16_bit_and_credited():
    import orbit_sounds
    assert len(orbit_sounds.RECORDED) >= 60
    for name in orbit_sounds.RECORDED:
        with wave.open(os.path.join(SOUNDS_DIR, name), "rb") as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == \
                (1, 2, 22050, "NONE"), name
            assert w.getnframes() >= 0.1 * 22050, name
    with open(os.path.join(SOUNDS_DIR, "LICENSE-kenney.txt"), encoding="utf-8") as f:
        licence = f.read()
    for words in ("Kenney", "www.kenney.nl", "CC0", "creativecommons.org/publicdomain/zero/1.0",
                  "Casino Audio", "Impact Sounds", "RPG Audio", "Sci-fi Sounds", "Interface Sounds"):
        assert words in licence, words
    with open(os.path.join(ROOT, "servers", "orbit", "README.md"), encoding="utf-8") as f:
        readme = f.read()
    assert "Kenney" in readme and "CC0" in readme
    packs = {src.split("/")[0] for src in orbit_sounds.recorded_sources()}
    assert packs == {"casino-audio", "impact-sounds", "rpg-audio", "sci-fi-sounds", "interface-sounds"}


@pytest.mark.skipif(not os.environ.get("ORBIT_KENNEY_WAV"), reason="needs the converted Kenney packs")
def test_the_recorded_sounds_are_what_the_recipes_make():
    import orbit_sounds
    for name in orbit_sounds.RECORDED:
        with open(os.path.join(SOUNDS_DIR, name), "rb") as f:
            assert f.read() == orbit_sounds.recorded_bytes(name, os.environ["ORBIT_KENNEY_WAV"]), name


def test_variants_really_differ():
    import orbit_sounds
    groups = {}
    for name in orbit_sounds.FILES:
        stem = name[:-4]
        if stem.split("_")[-1].isdigit():
            groups.setdefault(stem.rpartition("_")[0], []).append(name)
    assert {"step_metal", "step_grass", "step_wood", "coins", "emote_clap", "mine", "dice", "cards"} <= set(groups)
    for cue, names in groups.items():
        datas = [open(os.path.join(SOUNDS_DIR, n), "rb").read() for n in names]
        assert len(set(datas)) == len(datas), cue


def test_the_ambience_loops_have_no_seam():
    import orbit_sounds
    for name in (n for n, _m in orbit_sounds.SOUNDS if n.startswith("amb_")):
        _channels, _width, _rate, _frames, samples = _read(name)
        for channel in (0, 1):
            wave_ = samples[channel::2]
            steps = [abs(wave_[i + 1] - wave_[i]) for i in range(len(wave_) - 1)]
            typical = sorted(steps)[int(len(steps) * 0.99)]
            assert abs(wave_[0] - wave_[-1]) <= typical, name


def _loudness(samples, start, end):
    left = samples[2 * start:2 * end:2]
    right = samples[2 * start + 1:2 * end:2]
    return (math.sqrt(sum(v * v for v in left) / len(left)),
            math.sqrt(sum(v * v for v in right) / len(right)))


def test_the_stereo_sounds_move_where_they_should():
    for number, louder in ((1, "left"), (2, "left"), (3, "right"), (4, "right")):
        _c, _w, _r, frames, samples = _read(f"tone{number}.wav")
        left, right = _loudness(samples, 0, frames)
        assert (left > right) == (louder == "left"), number
    _c, _w, rate, frames, samples = _read("whisper.wav")
    left, right = _loudness(samples, 0, frames)
    assert right > 2 * left                          # close to your right ear
    _c, _w, rate, frames, samples = _read("bell.wav")
    first = _loudness(samples, int(0.02 * rate), int(0.3 * rate))
    last = _loudness(samples, int(0.92 * rate), int(1.2 * rate))
    assert first[0] > first[1] and last[1] > last[0]  # the bell's tones drift left to right


def test_the_sound_set_stays_small():
    import orbit_sounds
    total = sum(os.path.getsize(os.path.join(SOUNDS_DIR, n)) for n in os.listdir(SOUNDS_DIR))
    assert total < 10 * 1024 * 1024, total
    recorded = sum(os.path.getsize(os.path.join(SOUNDS_DIR, n)) for n in orbit_sounds.RECORDED)
    assert recorded <= 3 * 1024 * 1024, recorded          # the recordings' budget


@pytest.mark.parametrize("name", ["tone1.wav", "tone4.wav", "emote.wav", "whisper.wav", "shout_1.wav",
                                  "levelup.wav", "achievement.wav", "step_rock_2.wav", "crunch_1.wav",
                                  "announce.wav"])
def test_the_sounds_are_what_the_generator_makes(name):
    import orbit_sounds
    make = dict(orbit_sounds.SOUNDS)[name]
    with open(os.path.join(SOUNDS_DIR, name), "rb") as f:
        assert f.read() == make()
