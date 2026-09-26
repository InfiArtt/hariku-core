# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Orbit extension (extensions/orbit), all on fakes: reading
# commands in English, Orbit being played in English (and the client's own: quick settings,
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
    """Switch Hariku's language. Orbit's own words stay English: it's played in English."""
    from core import i18n

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("id")
    return set_lang


# ------------------------------------------------------------
# Reading commands
# ------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("go to the cantina", {"c": "go", "a": "the cantina"}),
    ("walk to the observation deck", {"c": "go", "a": "the observation deck"}),
    ("go home", {"c": "go", "a": "home"}),
    ("enter cabin", {"c": "go", "a": "cabin"}),
    ("say hello everyone!", {"c": "say", "a": "hello everyone!"}),
    ("say Hi, how are you?", {"c": "say", "a": "Hi, how are you?"}),
    ("'how are you", {"c": "say", "a": "how are you"}),
    ("whisper Sari see you on deck", {"c": "whisper", "to": "Sari", "a": "see you on deck"}),
    ("whisper to Sari: later", {"c": "whisper", "to": "Sari", "a": "later"}),
    ("whisper to Budi meet me at the dock", {"c": "whisper", "to": "Budi",
                                             "a": "meet me at the dock"}),
    ("tell Budi hi", {"c": "whisper", "to": "Budi", "a": "hi"}),
    ("shout anyone going to the moon?", {"c": "shout", "a": "anyone going to the moon?"}),
    ("yell hello", {"c": "shout", "a": "hello"}),
    ("smile", {"c": "emote", "e": "smile"}),
    ("smile at Sari", {"c": "emote", "e": "smile", "to": "Sari"}),
    ("wave at Budi", {"c": "emote", "e": "wave", "to": "Budi"}),
    ("shrug", {"c": "emote", "e": "shrug"}),
    ("clap", {"c": "emote", "e": "clap"}),
    ("applaud", {"c": "emote", "e": "clap"}),
    ("hahaha", {"c": "emote", "e": "laugh"}),
    ("lol", {"c": "emote", "e": "laugh"}),
    ("hug Sari", {"c": "emote", "e": "hug", "to": "Sari"}),
    ("smile if you are happy", {"c": "text", "a": "smile if you are happy"}),
    ("who is online", {"c": "who"}),
    ("who", {"c": "who"}),
    ("look", {"c": "look"}),
    ("look around", {"c": "look"}),
    ("look at Sari", {"c": "look", "a": "Sari"}),
    ("look at the reactor", {"c": "look", "a": "the reactor"}),
    ("inspect headlamp", {"c": "look", "a": "headlamp"}),
    ("examine headlamp", {"c": "examine", "a": "headlamp"}),
    ("x here", {"c": "examine", "a": "here"}), ("examine here", {"c": "examine", "a": "here"}),
    ("commands here", {"c": "examine", "a": "here"}), ("x Rocco", {"c": "examine", "a": "Rocco"}),
    ("x", {"c": "examine", "a": ""}), ("orbit x here", {"c": "examine", "a": "here"}),
    ("what can I do here", {"c": "text", "a": "what can I do here"}),       # the server reads it
    ("commands", {"local": "help"}),
    ("check credits", {"c": "inventory"}),
    ("inventory", {"c": "inventory"}),
    ("i", {"c": "inventory"}),
    ("i think so", {"c": "text", "a": "i think so"}),
    ("give Sari 50 credits", {"c": "give", "to": "Sari", "n": 50, "item": "credits"}),
    ("give to Sari 2 coffee", {"c": "give", "to": "Sari", "n": 2, "item": "coffee"}),
    ("give 50 credits to Sari", {"c": "give", "to": "Sari", "n": 50, "item": "credits"}),
    ("pay Budi 20", {"c": "give", "to": "Budi", "n": 20, "item": "credits"}),
    ("work", {"c": "work"}),
    ("repair the reactor", {"c": "work"}),
    ("repair 3142", {"c": "answer", "a": "3142"}),
    ("3, 1, 4, 2", {"c": "answer", "a": "3, 1, 4, 2"}),
    ("missions", {"c": "missions"}),
    ("board 2", {"c": "accept", "n": 2}),
    ("accept mission 1", {"c": "accept", "n": 1}),
    ("accept 3", {"c": "accept", "n": 3}),
    ("take 3 crates", {"c": "take", "item": "crates", "n": 3}),
    ("pick up crates", {"c": "take", "item": "crates"}),
    ("complete mission", {"c": "complete"}),
    ("abandon mission", {"c": "abandon"}),
    ("prices", {"c": "prices"}),
    ("buy 2 coffee", {"c": "buy", "item": "coffee", "n": 2}),
    ("sell all coffee", {"c": "sell", "item": "coffee", "n": "all"}),
    ("describe me a pilot from the coast", {"c": "describe", "a": "a pilot from the coast"}),
    ("describe me", {"c": "describe", "a": ""}),
    ("help", {"local": "help"}),
    ("?", {"local": "help"}),
    ("connect", {"local": "connect"}),
    ("disconnect", {"local": "disconnect"}),
    ("repeat", {"local": "repeat"}), ("again", {"c": "text", "a": "again"}), ("!", {"c": "text", "a": "again"}),
    ("cantina", {"c": "text", "a": "cantina"}),
    ("orbit go to the dock", {"c": "go", "a": "the dock"}),
    ("please orbit who is online", {"c": "who"}),
    ("mute Budi 5", {"c": "admin", "op": "mute", "to": "Budi", "n": 5}),
    ("announce server restart at 9", {"c": "admin", "op": "announce", "a": "server restart at 9"}),
    ("voices off", {"local": "set", "key": "voices", "value": False}),
    ("turn on voices", {"local": "set", "key": "voices", "value": True}),
    ("player voices on", {"local": "set", "key": "voices", "value": True}),
    ("speech off", {"local": "set", "key": "speak", "value": False}),
    ("speech on", {"local": "set", "key": "speak", "value": True}),
    ("my lines off", {"local": "set", "key": "speak_own", "value": False}),
    ("names on", {"local": "set", "key": "speak_names", "value": True}),
    ("ambience off", {"local": "set", "key": "ambience", "value": False}),
    ("ambience on", {"local": "set", "key": "ambience", "value": True}),
    ("sounds off", {"local": "set", "key": "sounds", "value": False}),
    ("turn off sounds", {"local": "set", "key": "sounds", "value": False}),
    ("other sounds off", {"local": "set", "key": "other_sounds", "value": False}),
    ("effects volume 40", {"local": "set", "key": "effects_volume", "value": 40}),
    ("ambience volume 250", {"local": "set", "key": "ambience_volume", "value": 100}),
    ("reader nvda", {"local": "set", "key": "reader", "value": "nvda"}),
    ("reader mixed", {"local": "set", "key": "reader", "value": "mixed"}),
    ("all voices", {"local": "set", "key": "reader", "value": "voices"}),
    ("preferences", {"local": "settings"}), ("settings", {"local": "settings"}),
    ("ignore Budi", {"local": "ignore", "name": "Budi"}),
    ("stop ignoring Budi", {"local": "unignore", "name": "Budi"}),
    ("unignore Budi", {"local": "unignore", "name": "Budi"}),
    ("ignored", {"local": "ignored"}), ("ignore list", {"local": "ignored"}),
    ("logout", {"local": "disconnect"}), ("orbit quit", {"local": "disconnect"}),
    ("quit", {"local": "disconnect"}), ("leave orbit", {"local": "disconnect"}),
    ("status", {"local": "status"}), ("orbit status", {"local": "status"}),
    ("help casino", {"local": "help", "topic": "casino"}),
    ("help settings", {"local": "help", "topic": "settings"}),
    ("prices crops", {"c": "prices", "a": "crops"}),
    ("remind me of the meteor shower", {"local": "remind", "name": "the meteor shower"}),
    ("s", {"c": "text", "a": "s"}), ("u", {"c": "text", "a": "u"}), ("d", {"c": "text", "a": "d"}),
    ("southwest", {"c": "text", "a": "southwest"}),
    ("take credits Budi 50", {"c": "text", "a": "take credits Budi 50"}),
    ("give item Budi headlamp", {"c": "text", "a": "give item Budi headlamp"}),
    ("take off headlamp", {"c": "text", "a": "take off headlamp"}),
    ("board the Wombat", {"c": "text", "a": "board the Wombat"}),
    ("fly to Karmina", {"c": "text", "a": "fly to Karmina"}),
    ("transfer code", {"c": "text", "a": "transfer code"}),
    ("light lantern", {"c": "text", "a": "light lantern"}),
    ("talk to Rocco", {"c": "text", "a": "talk to Rocco"}),
    ("feed Kiki", {"c": "text", "a": "feed Kiki"}),
    ("say hi to Rocco", {"c": "text", "a": "say hi to Rocco"}),
    ("ask Rocco about gossip", {"c": "text", "a": "ask Rocco about gossip"}),
    ("propose to Budi", {"c": "text", "a": "propose to Budi"}),
    ("pet status", {"c": "text", "a": "pet status"}),
    ("hug Mira", {"c": "emote", "e": "hug", "to": "Mira"}),
    ("", None), ("   ", None),
])
def test_reading_commands(text, expected):
    assert orbit_parse.parse(text) == expected


@pytest.mark.parametrize("text", [
    "pergi ke kantin", "bilang halo semua", "bisik Sari ketemu di dek", "senyum", "siapa online", "lihat",
    "tas", "beri Sari 50 kredit", "kerja", "misi", "harga", "beli 2 kopi", "harian", "bantuan", "sambungkan",
    "putuskan", "keluar", "ulangi", "suara pemain mati", "abaikan Budi", "pengaturan", "wkwkwk",
])
def test_indonesian_is_not_read_it_goes_to_the_server_as_it_is(text):
    # Orbit is played in English: the server answers these with its help hint.
    assert orbit_parse.parse(text) == {"c": "text", "a": text}
    assert orbit_parse.parse("orbit " + text) == {"c": "text", "a": text}


def test_orbits_words_are_english_only_and_cover_every_key(lang):
    import json
    import string
    import orbit_text
    locales = os.path.join(EXT_DIR, "locales")
    assert sorted(os.listdir(locales)) == ["en.json"]           # no other language
    with open(os.path.join(locales, "en.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert data["manifest"]["language_code"] == "en"
    texts = data["messages"]
    for key, line in texts.items():
        assert isinstance(line, str) and line.strip(), key
        for _l, name, _s, _c in string.Formatter().parse(line):
            assert name is None or name.isidentifier(), (key, name)
    # Hariku in Indonesian (the lang fixture): Orbit's own words fall back to English.
    assert orbit_text._("say_connected") == texts["say_connected"] == "Connected to Orbit."
    assert orbit_text._("status_online", name="Rafli", job="Pilot") == "Connected to Orbit as Rafli, Pilot."
    assert orbit_text.LANGUAGE == "en"


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
    ("orbit north", "north"),
    ("Aruna, orbit say hello everyone!", "say hello everyone!"),
    ("please orbit who is online", "who is online"),
    ("orbit whisper Sari see you on deck", "whisper Sari see you on deck"),
    ("orbit look around", "look around"),
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
    reply = omain._on_play_intent(core.commands.Request("who is online", "orbit who is online"))
    assert reply.wait and held == [omain.CONNECT_HOLD_SECONDS]


def test_not_for_orbit(omain, monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    core.commands.add_intent(omain.PLAY_INTENT, list(omain.PLAY_PATTERNS), omain._on_play_intent)
    assert core.commands.match_intents("orbit") == []
    assert core.commands.match_intents("go to the cantina") == []
    monkeypatch.setattr(omain, "_client", types.SimpleNamespace(submit=lambda *a: None,
                                                                online=lambda: True))
    request = core.commands.Request
    assert omain._on_play_intent(request("   ", "orbit")) is None
    assert omain._on_play_intent(request("x" * 400, "orbit ...")) is None
    reply = omain._on_play_intent(request("open", "orbit open"))
    assert reply.then is omain.open_window
    assert omain._on_play_intent(request("play", "orbit play")).then is omain.open_window


def _commands(omain):
    import core.commands
    candidates = []
    for name, description, _title, _callback, aliases, _answers in omain.ACTIONS:
        candidates.append(core.commands.Command(f"Orbit.{name}", omain._(description), list(aliases)))
    for action_id, description in (("Hariku Core.speak_time", "Speak the time"),
                                   ("World Trip.where_am_i", "Where am I now")):
        candidates.append(core.commands.Command(action_id, description,
                                                core.commands.aliases_for(action_id)))
    return candidates


@pytest.mark.parametrize("text, action", [
    ("orbit", "Orbit.open"), ("open orbit", "Orbit.open"), ("play orbit", "Orbit.open"),
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
    decision = core.commands.decide("orbit say see you tomorrow at 9", _commands(omain),
                                    parse=lambda text: None, intent_candidates=[intent])
    assert decision.kind == "intent" and decision.intents[0].text == "say see you tomorrow at 9"


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
    assert {args[1] for args, _kw in actions} == {"open", "look", "who", "credits", "connect", "disconnect",
                                                  "status", "leave", "daily", "harvest", "profile"}
    for args, kwargs in actions:
        assert args[0] == "Orbit" and args[3] is None and kwargs == {}        # no default keys
    assert core.commands.is_answer_action("Orbit.look") and core.commands.is_answer_action("Orbit.who")
    assert not core.commands.is_answer_action("Orbit.open")                # it opens a window
    assert [i.id for i in core.commands.intents()] == ["Orbit.play"]
    assert "open orbit" in core.commands.aliases_for("Orbit.open")
    assert "orbit quit" in core.commands.aliases_for("Orbit.leave")
    assert "orbit status" in core.commands.aliases_for("Orbit.status")
    assert "orbit connect" in core.commands.aliases_for("Orbit.connect")
    assert "orbit disconnect" not in core.commands.aliases_for("Orbit.connect")
    assert "orbit disconnect" in core.commands.aliases_for("Orbit.disconnect")
    assert panels[0][0] == "Orbit"
    # The ambience plays on under the screen reader: Orbit doesn't listen to what Hariku says.
    assert not fresh_event_bus._listeners.get("on_before_speak") and not hasattr(omain, "_on_before_speak")
    assert omain._on_unload in fresh_event_bus._listeners["on_unload"]
    omain.teardown()
    assert core.commands.intents() == [] and core.commands.aliases_for("Orbit.open") == []
    assert omain._on_unload not in fresh_event_bus._listeners.get("on_unload", [])


def test_screen_reader_speech_leaves_the_ambience_alone(omain, fresh_event_bus, monkeypatch):
    """Client 1.6: NVDA reads over the room's sound, as in VIPMud; only Hariku Voice dips it."""
    import core.commands
    import core.hotkeys
    import core.preferences
    import core.voice
    monkeypatch.setattr(core.hotkeys, "register_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(core.preferences, "register_panel", lambda *args: None)
    monkeypatch.setattr(core.commands, "_intents", {})
    monkeypatch.setattr(core.commands, "_answer_actions", set())
    speaking = [False]
    monkeypatch.setattr(core.voice, "is_speaking", lambda: speaking[0])
    omain.register(fresh_event_bus)
    player = omain._services.ambience_player
    player._clock = lambda: 100.0
    player.apply("play", ("vent.wav", 40))
    player.playing = player.wanted
    for text in ("Cantina. Exits: east, west.", "Rafli says: hello", "x" * 400):
        fresh_event_bus.emit("on_before_speak", {"text": text, "interrupt": False, "cancel": False})
        assert player.target(100.0) == 400.0                  # the screen reader: no change
    speaking[0] = True                                         # Hariku Voice (a player's voice)
    assert player.target(100.0) == 400.0 * orbit_audio.DUCK_LEVEL
    speaking[0] = False
    assert player.target(100.0) == 400.0
    player.playing = None
    omain.teardown()


def test_connect_only_connects_and_disconnect_only_disconnects(omain, play):
    s, client = play.services, play.client
    omain._client = client
    omain._disconnect()                                   # not connected: it says so
    assert s.connections == [] and s.spoken[-1] == ("narrator", "Not connected.")
    omain._connect()                                      # "orbit connect"
    assert len(s.connections) == 1
    s.connections[-1].welcome()
    assert client.online()
    omain._connect()                                      # said again: still connected, not a toggle
    assert len(s.connections) == 1 and client.online() and not s.connections[-1].stopped
    omain._disconnect()                                   # "orbit disconnect"
    assert not client.online() and s.connections[-1].stopped
    omain._connect()
    assert len(s.connections) == 2
    actions = {name: aliases for name, _d, _t, _fn, aliases, _a in omain.ACTIONS}
    assert "orbit disconnect" not in actions["connect"]
    assert set(actions["disconnect"]) == {"orbit disconnect"}
    assert "orbit quit" in actions["leave"]
    # Every phrase Aruna knows for Orbit is English.
    phrases = [p for aliases in actions.values() for p in aliases]
    assert "orbit look" in actions["look"] and "orbit credits" in actions["credits"]
    for word in ("buka", "lihat", "siapa", "kredit", "keluar", "harian", "panen", "profil", "sambungkan",
                 "putuskan"):
        assert not [p for p in phrases if word in p.split()], word


def test_settings_are_checked(omain):
    s = omain.normalize_settings({"server": "  wss://example.org/orbit/ws ", "name": " Rafli ",
                                  "job": "wizard", "speak": "yes", "ambience_volume": 250,
                                  "voices": False, "read_shout": False, "background": "loud",
                                  "close_action": "leave", "auto_logout": 45, "effects_volume": -5,
                                  "ignored": ["Budi", " budi ", "", 7, "Sari"], "reader": "loud"})
    assert s == {"server": "wss://example.org/orbit/ws", "name": "Rafli", "job": "pilot",
                 "reader": "mixed", "speak": True, "voices": False, "speak_own": True, "speak_names": True,
                 "ambience": True, "ambience_volume": 100,
                 "sounds": True, "effects_volume": 0, "other_sounds": True,
                 "read_say": True, "read_whisper": True, "read_shout": False, "read_moves": True,
                 "read_money": True, "read_announce": True, "read_events": True, "background": "important",
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
    VOICES = {"edge": [{"id": "en-GB-Alpha", "name": "Alpha", "language": "en-GB"},
                       {"id": "en-US-Bravo", "name": "Bravo", "language": "en-US"}],
              "windows": [{"id": "charlie", "name": "Charlie", "language": "en-AU"},
                          {"id": "dewi", "name": "Dewi", "language": "id-ID"}]}
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
                       "read_moves": True, "read_money": True, "read_announce": True, "read_events": True,
                       "background": "important", "close_action": "stay", "auto_logout": 30,
                       "autoconnect": False, "ignored": [], "close_hints": 0,
                       "reader": "voices"}      # tests of other readers set it
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
        self.reminders = []

    def settings(self):
        return dict(self.values)

    def set_setting(self, key, value):
        self.values[key] = value

    def open_settings(self):
        self.settings_opened += 1

    def open_key(self):
        return self.key

    def language(self):
        return "en"

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

    def read(self, text):
        self.spoken.append(("reader", text))    # the screen reader, straight away

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
        return orbit_speech.pool_size(orbit_speech.voices_of(self.VOICES, "en"))

    def voice_for(self, name, number=None):
        if not self.voices_on:
            return None
        return orbit_speech.pick_voice(name, orbit_speech.voices_of(self.VOICES, "en"), number=number)

    def show_answer(self, text):
        self.shown.append(text)

    def add_reminder(self, title, when):
        self.reminders.append((title, when))
        return True

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
    assert hello == {"t": "hello", "v": 1, "client": "Hariku Orbit 1.7", "lang": "en",
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
                                         "text": "Someone on the station is already called Rafli. Please choose another name."})
    assert client.status == "Someone on the station is already called Rafli. Please choose another name."
    assert ("narrator", "Someone on the station is already called Rafli. Please choose another name.") in s.spoken
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
        assert play.client.status.startswith("The server address must start with wss://")
        assert play.services.connections == []


def test_no_name_no_join(play):
    play.services.values["name"] = "  "
    assert play.client.connect() is False
    assert play.client.status.startswith("Choose a character name")


def test_what_the_connection_says(play):
    s, client = play.services, play.client
    client.connect()
    conn = s.connections[-1]
    conn.on_state("connecting", {"attempt": 0})
    assert client.status == "Connecting to Orbit..." and s.spoken == [("narrator", "Connecting to Orbit...")]
    conn.welcome()
    assert client.status == "Connected to Orbit as Rafli, Pilot."
    assert s.spoken[-1] == ("narrator", "Connected to Orbit.") and s.ambiences[-1] == ("vent", 25)
    conn.on_state("offline", {"reason": "lost", "retry_in": 4.2})
    conn.on_state("connecting", {"attempt": 1})
    conn.on_state("offline", {"reason": "lost", "retry_in": 8.1})
    assert client.status == "Disconnected, reconnecting in 8 seconds..." and client.title_state == "Disconnected"
    assert [t for _w, t in s.spoken].count("Orbit is offline. I'll keep trying.") == 1
    assert s.ambiences[-1] == (None, None)
    conn.on_state("online", {})
    conn.on_message({"t": "welcome", "name": "Rafli", "job": "pilot", "resumed": True,
                     "room": "cantina", "amb": "cantina"})
    assert s.spoken[-1] == ("narrator", "Reconnected.") and s.ambiences[-1] == ("cantina", 25)
    conn.on_state("failed", {"code": "kicked"})
    assert client.status == "An admin sent you off the station. Connect again later."
    assert client.conn is None


def test_messages_from_an_old_connection_are_ignored(play):
    s, client = play.services, play.client
    client.connect()
    old = s.connections[-1]
    client.connect("ws://127.0.0.1:1/orbit/ws")
    old.event("say", "Ghost says: boo", actor="Ghost")
    assert client.messages == []


def test_events_are_shown_played_and_said(play):
    s, client = play.services, play.client
    conn = _online(play)
    s.spoken.clear()
    conn.event("moved", "You walk to the Cantina. Cantina.", room="cantina", amb="cantina")
    assert s.sounds[-1] == "door" and s.ambiences[-1] == ("cantina", 25)
    assert s.spoken[-1] == ("narrator", "You walk to the Cantina. Cantina.")
    conn.event("said", "You say: hello everyone", brief="Sent.")
    assert client.messages[-1] == "You say: hello everyone" and s.spoken[-1] == ("narrator", "Sent.")
    assert s.sounds[-1] == "sent"
    conn.event("say", "Sari says: hello Rafli!", actor="Sari")
    sari = orbit_speech.pick_voice("Sari", orbit_speech.voices_of(FakeServices.VOICES, "en"))
    assert s.spoken[-1] == (sari["id"], "Sari says: hello Rafli!") and s.sounds[-1] == "say"
    conn.event("whisper", "Budi whispers to you: psst", actor="Budi")
    assert s.sounds[-1] == "whisper" and s.spoken[-1][0] != "narrator"
    conn.event("emote", "Sari smiles at you.", actor="Sari")
    assert s.spoken[-1] == ("narrator", "Sari smiles at you.")        # gestures: the narrator
    conn.event("arrive", "Budi comes in from the Promenade.", actor="Budi")
    conn.event("paid", "You're paid 40 credits.")
    conn.event("error", "Budi isn't here.")
    assert s.sounds[-3:] == ["arrive", "success", "error"]
    assert client.messages[-1] == "Budi isn't here."


def test_your_own_name_is_never_read_in_a_player_voice(play):
    s = play.services
    conn = _online(play, name="Rafli")
    conn.event("shout", "Rafli shouts: test", actor="Rafli")
    assert s.spoken[-1] == ("narrator", "Rafli shouts: test")


def test_one_voice_for_everyone_when_the_setting_is_off(play):
    s = play.services
    s.values["voices"] = False
    conn = _online(play)
    conn.event("say", "Sari says: hello", actor="Sari")
    assert s.spoken[-1] == ("narrator", "Sari says: hello")


def test_quiet_unless_aruna_asked(play):
    s, client = play.services, play.client
    s.values["speak"] = False
    conn = _online(play)
    count = len(s.spoken)
    conn.event("say", "Sari says: hello", actor="Sari")
    assert len(s.spoken) == count and client.messages[-1] == "Sari says: hello"
    assert s.sounds[-1] == "say"
    client.submit("orbit who is online", "aruna")
    assert conn.sent[-1] == {"t": "cmd", "c": "who"}
    conn.event("who", "2 online: Rafli the pilot, at the Dock; Sari the pilot, at the Dock.")
    assert s.spoken[-1][1].startswith("2 online")
    conn.event("say", "Sari says: I'm here", actor="Sari")
    assert s.spoken[-1] == (orbit_speech.pick_voice(
        "Sari", orbit_speech.voices_of(FakeServices.VOICES, "en"))["id"], "Sari says: I'm here")
    assert s.shown == ["Sari says: I'm here"]          # Aruna's Last result gets it too
    client.aruna_until = 0
    conn.event("say", "Sari says: done?", actor="Sari")
    assert s.spoken[-1][1] != "Sari says: done?"


def test_the_reactor_tones_play_before_the_line_is_read(play):
    s = play.services
    conn = _online(play)
    s.spoken.clear()
    conn.event("tones", "Listen to the 3 stabiliser tones: 2, 4, 1.", codes=[2, 4, 1])
    assert s.spoken == [] and len([t for t in s.timers if t.fn != play.client._tick]) == 4
    s.timers = [t for t in s.timers if t.fn != play.client._tick]
    s.run_timers()
    assert [x for x in s.sounds if x.startswith("tone")] == ["tone2", "tone4", "tone1"]
    assert s.spoken == [("narrator", "Listen to the 3 stabiliser tones: 2, 4, 1.")]


def test_the_slot_reels_stop_left_middle_right_before_the_result_is_read(play):
    s = play.services
    s.FILES = FakeServices.FILES | {"reel_spin", "reel_stop", "push", "dice", "win", "cards", "deal"}
    conn = _online(play)
    s.spoken.clear()
    s.placed.clear()
    s.timers = []
    conn.event("failed", "star, moon, star. A pair: you get your bet back.", sound="reel_spin",
               reels=["star", "moon", "star"], outcome="push")
    assert s.placed == [("reel_spin", 0.0, None)] and s.spoken == []
    assert sorted(round(t.seconds, 2) for t in s.timers) == [0.9, 1.3, 1.7, 2.0, 2.0]
    s.run_timers()
    assert [p[:2] for p in s.placed[1:]] == [("reel_stop", -0.75), ("reel_stop", 0.0), ("reel_stop", 0.75),
                                             ("push", 0.0)]
    assert s.spoken == [("narrator", "star, moon, star. A pair: you get your bet back.")]
    # the dice land, then you hear whether you won, then the words
    s.placed.clear()
    conn.event("paid", "The dice roll 5 and 6: 11. You win 230 credits!", sound="dice", outcome="win")
    assert s.placed[0][0] == "dice" and [round(t.seconds, 2) for t in s.timers] == [1.2, 1.2]
    s.run_timers()
    assert s.placed[-1][0] == "win" and s.spoken[-1][1].startswith("The dice roll 5 and 6")
    # with the sounds off, nothing waits
    s.values["sounds"] = False
    conn.event("task", "Blackjack for 50 credits.", sound="deal")
    assert not s.timers and s.spoken[-1][1] == "Blackjack for 50 credits."


def test_new_floors_and_places_have_their_sounds():
    assert orbit_audio.cues_for({"k": "moved", "dir": "e", "floor": "wood"})[0][:2] == ("step_wood", 0.75)
    assert orbit_audio.cues_for({"k": "moved", "dir": "w", "floor": "snow"})[0][:2] == ("step_snow", -0.75)
    assert orbit_audio.cues_for({"k": "moved", "dir": "n", "floor": "lava"})[0][0] == "step_metal"
    assert {"mall", "casino"} <= set(orbit_audio.AMBIENCES)
    assert orbit_audio.timed_cues({"k": "paid", "sound": "coinflip", "outcome": "win"}) == \
        ([(0.9, "win", 0.0)], 0.9)
    assert orbit_audio.timed_cues({"k": "paid", "text": "x"}) == ([], 0.0)


def test_the_arcade_places_meteors_and_plays_rhythms(play):
    cues = orbit_audio.cues_for
    assert cues({"k": "task", "sound": "arcade_meteor", "dir": "w"}) == [("arcade_meteor", -0.75, None, "task")]
    assert cues({"k": "task", "sound": "arcade_meteor", "dir": "e"})[0][1] == 0.75
    assert cues({"k": "task", "sound": "arcade_meteor", "dir": "n"})[0][1] == 0.0
    assert cues({"k": "info", "sound": "robot_beep", "dir": "sw"})[0][:2] == ("robot_beep", -0.5)
    beats = orbit_audio.timed_cues({"k": "task", "beats": [1.2, 1.7, 2.7]})
    assert beats == ([(1.2, "arcade_beat", 0.0), (1.7, "arcade_beat", 0.0), (2.7, "arcade_beat", 0.0)], 2.7)
    assert orbit_audio.timed_cues({"k": "task", "beats": [1, "x", -2, True, 99]}) == ([(1.0, "arcade_beat", 0.0)], 1.0)
    assert orbit_audio.timed_cues({"k": "task", "beats": list(range(40))}) == ([], 0.0)
    assert orbit_audio.timed_cues({"k": "task", "beats": "1,2"}) == ([], 0.0)
    # the rhythm first, then the words
    s = play.services
    s.FILES = FakeServices.FILES | {"task", "arcade_beat", "arcade_meteor"}
    conn = _online(play)
    s.spoken.clear()
    s.placed.clear()
    s.timers = []
    conn.event("task", "Rhythm 1 of 3: 3 beats.", beats=[1.2, 1.7, 2.7])
    assert s.placed == [("task", 0.0, None)] and s.spoken == []
    assert sorted(round(t.seconds, 2) for t in s.timers) == [1.2, 1.7, 2.7, 2.7]
    s.run_timers()
    assert [p[0] for p in s.placed[1:]] == ["arcade_beat"] * 3
    assert s.spoken == [("narrator", "Rhythm 1 of 3: 3 beats.")]
    conn.event("task", "Meteor!", sound="arcade_meteor", dir="e")
    assert s.placed[-1] == ("arcade_meteor", 0.75, None)


def test_event_news_can_be_left_unread(play):
    s = play.services
    conn = _online(play)
    conn.event("announce", "A meteor shower sweeps past the station!", event="meteor_shower", sound="event_meteor")
    assert s.spoken[-1] == ("narrator", "A meteor shower sweeps past the station!")
    s.values["read_events"] = False
    conn.event("announce", "A comet flies by!", event="comet_flyby")
    assert s.spoken[-1][1] != "A comet flies by!" and play.client.messages[-1] == "A comet flies by!"
    conn.event("announce", "An announcement from the admins.")                    # station news: still read
    assert s.spoken[-1] == ("narrator", "An announcement from the admins.")


def test_remind_me_sets_a_hariku_reminder_five_minutes_before(play):
    import datetime
    s, client = play.services, play.client
    conn = _online(play)
    now = datetime.datetime(2026, 9, 25, 12, 30, tzinfo=datetime.timezone.utc).timestamp()
    client.wall_clock = lambda: now
    client.submit("remind me")
    assert conn.sent[-1] == {"t": "cmd", "c": "events"} and not s.reminders    # asks what's coming first
    fair = now + 3600
    conn.event("info", "Coming: ...", schedule=[{"event": "jackpot_night", "name": "Jackpot night",
                                                     "at": now + 120},
                                                    {"event": "trading_fair", "name": "Trading fair",
                                                     "at": fair}])
    assert s.spoken[-1][1] == "Jackpot night starts in less than five minutes: no need for a reminder!"
    client.submit("remind me about trading fair")                              # by name; the list is known now
    title, when = s.reminders[-1]
    assert title == "Orbit: Trading fair" and when == datetime.datetime.fromtimestamp(fair - 300)
    assert s.spoken[-1][1].startswith("A Hariku reminder is set for ")
    client.submit("remind me about the eclipse")
    assert s.spoken[-1][1] == "No coming event is called the eclipse. Type events to hear what's coming."
    assert orbit_parse.parse("remind me about trading fair") == {"local": "remind", "name": "trading fair"}


def test_sounds_can_be_turned_off(play):
    s = play.services
    s.values["sounds"] = False
    conn = _online(play)
    conn.event("moved", "You walk to the Cantina.", room="cantina", amb="cantina")
    conn.event("tones", "Listen: 1.", codes=[1])
    assert s.sounds == [] and s.spoken[-1] == ("narrator", "Listen: 1.")


def test_the_ambience_follows_the_room_the_window_and_the_settings(play):
    s, client = play.services, play.client
    conn = _online(play)
    assert s.ambiences[-1] == ("vent", 25)
    s.window = False
    client.update_ambience()
    assert s.ambiences[-1] == (None, None)
    s.window = True
    s.values["ambience_volume"] = 60
    conn.event("moved", "Engineering.", room="engineering", amb="engine")
    assert s.ambiences[-1] == ("engine", 60)
    s.values["ambience"] = False
    client.update_ambience()
    assert s.ambiences[-1] == (None, None)
    s.values["ambience"] = True
    client.disconnect()
    assert s.ambiences[-1] == (None, None) and s.spoken[-1] == ("narrator", "You've left Orbit.")


def test_commands_are_sent_or_wait_for_the_connection(play):
    s, client = play.services, play.client
    assert client.submit("   ") == "empty"
    assert client.submit("go to the cantina") == "queued"         # connects first
    conn = s.connections[-1]
    assert conn.sent == [{"t": "cmd", "c": "go", "a": "the cantina"}]
    conn.welcome()
    assert client.submit("say hello") == "sent"
    assert conn.sent[-1] == {"t": "cmd", "c": "say", "a": "hello"}


def test_orbits_own_commands(play):
    s, client = play.services, play.client
    assert client.submit("repeat") == "local"
    assert s.spoken[-1] == ("narrator", "Nothing has been said yet.")
    client.submit("help")
    assert client.messages[-1].startswith("Orbit's help.") and s.spoken[-1][1].startswith("Orbit's help.")
    client.submit("connect")
    assert s.connections and s.connections[-1].started
    s.connections[-1].welcome()
    client.submit("connect")
    assert s.spoken[-1] == ("narrator", "Connected to Orbit as Rafli, Pilot.")
    s.connections[-1].event("say", "Sari says: hi", actor="Sari")
    client.submit("repeat")
    assert s.spoken[-1] == ("narrator", "Sari says: hi")
    client.submit("disconnect")
    assert s.connections[-1].stopped and client.status == "Not connected."


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


LOOK_LINES = ["Cantina", "Round tables bolted to the floor, and a jukebox.", "Exits: east, west.",
              "Here: Maya the trader.", "Residents here: Rocco, the Cantina's bartender."]
LOOK_TEXT = ("Cantina. Round tables bolted to the floor, and a jukebox. Exits: east, west. Here: Maya the trader. "
             "Residents here: Rocco, the Cantina's bartender.")


def test_a_reply_in_lines_is_shown_a_line_each_and_read_whole(play):
    s, client = play.services, play.client
    s.values["reader"] = "nvda"
    conn = _online(play)
    notes = []
    client.add_listener(lambda event, value: notes.append((event, value)))
    s.spoken.clear()
    conn.event("room", LOOK_TEXT, lines=LOOK_LINES, room="cantina", amb="cantina")
    assert client.messages[-5:] == LOOK_LINES                          # the arrow keys read them one by one
    assert [v for e, v in notes if e == "message"] == LOOK_LINES      # the window gets a line each
    assert s.spoken == [("reader", LOOK_TEXT)]                         # NVDA reads it once, whole
    client.submit("repeat")
    assert s.spoken[-1] == ("reader", LOOK_TEXT)                       # "repeat": the whole reply again
    # An older server's one line, a one-line reply, and lines that aren't lines: the text, as a line.
    for extra in ({}, {"lines": ["Sent."]}, {"lines": "Cantina\nExits"}, {"lines": ["a", 3]}):
        conn.event("info", "One line.", **extra)
        assert client.messages[-1] == "One line." and client.messages[-2] != "a"
    # From Aruna: the answer is the reply said whole, once.
    s.spoken.clear()
    client.submit("look", "aruna")
    conn.event("room", LOOK_TEXT, lines=LOOK_LINES)
    assert s.spoken == [("narrator", LOOK_TEXT)] and client.messages[-5:] == LOOK_LINES


def test_trimming_counts_every_line_of_a_long_reply(play):
    client = play.client
    notes = []
    client.add_listener(lambda event, value: notes.append((event, value)))
    for i in range(490):
        client.add_line(f"line {i}")
    client.add_lines([f"part {i}" for i in range(30)], "the whole reply")
    assert len(client.messages) == 470 and client.messages[0] == "line 50" and client.messages[-1] == "part 29"
    assert notes[-1] == ("trim", 50) and client.last_message == "the whole reply"
    client.add_lines([f"big {i}" for i in range(180)])                 # 650 lines: three trims at once
    assert notes[-1] == ("trim", 150) and len(client.messages) == 500 and client.messages[-1] == "big 179"
    client.add_lines([f"huge {i}" for i in range(1000)])               # a runaway reply: at most 200 of it
    assert client.messages[-1] == "huge 199" and len(client.messages) <= orbit_play.MAX_MESSAGES
    # What the window was told adds up to what the client keeps.
    shown = sum(1 for e, _v in notes if e == "message")
    trimmed = sum(v for e, v in notes if e == "trim")
    assert shown - trimmed == len(client.messages)


# ------------------------------------------------------------
# Who speaks
# ------------------------------------------------------------

def test_each_player_keeps_a_voice_of_their_own():
    voices = orbit_speech.voices_of(FakeServices.VOICES, "en")
    assert [v["id"] for v in voices] == ["en-GB-Alpha", "en-US-Bravo", "charlie"]
    assert orbit_speech.voices_of(FakeServices.VOICES, "id") == [
        dict(FakeServices.VOICES["windows"][1], provider="windows")]
    names = ["Sari", "Budi", "Tono", "Ayu", "Rafli", "Dewi", "Joko", "Maya"]
    picked = {n: orbit_speech.pick_voice(n, voices)["id"] for n in names}
    assert picked["Sari"] == orbit_speech.pick_voice("sari", voices)["id"]
    assert len(set(picked.values())) >= 2                    # not everyone sounds the same
    # The narrator's own voice is left for the narrator when there are others.
    narrator = ("edge", "en-GB-Alpha")
    assert all(orbit_speech.pick_voice(n, voices, exclude=narrator)["id"] != "en-GB-Alpha"
               for n in names)
    assert orbit_speech.pick_voice("Sari", voices[:1]) is None       # one voice: the narrator
    assert orbit_speech.pick_voice("Sari", voices[:2], exclude=("edge", "en-GB-Alpha"))


def test_the_same_voices_in_any_order_give_the_same_choice():
    voices = orbit_speech.voices_of(FakeServices.VOICES, "en")
    shuffled = orbit_speech.voices_of({"windows": FakeServices.VOICES["windows"],
                                       "edge": list(reversed(FakeServices.VOICES["edge"]))}, "en")
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
    speaker.say("You walk to the Cantina.")
    speaker.say("Sari says: hello", voice="bravo")
    speaker.say("Budi comes in.")
    assert services.log == [("narrator", "You walk to the Cantina."), ("bravo", "Sari says: hello")]
    services.tick()
    assert len(services.log) == 2                   # the narrator waits for Sari's voice
    services.pending.pop()(None)
    assert services.log[-1] == ("narrator", "Budi comes in.") and not speaker.busy()
    # A player's voice waits while Hariku Voice is busy...
    services.busy = True
    speaker.say("Budi says: hi", voice="alpha")
    assert services.log[-1] == ("narrator", "Budi comes in.")
    services.busy = False
    services.tick()
    assert services.log[-1] == ("alpha", "Budi says: hi")
    services.pending.pop()(None)
    # ...and while the screen reader is probably still reading.
    services.voiced = False
    speaker.say("One long sentence from the station to read.")
    speaker.say("Sari says: well", voice="bravo")
    assert services.log[-1][0] == "narrator"
    now[0] += 10
    services.tick()
    assert services.log[-1] == ("bravo", "Sari says: well")


def test_a_voice_that_fails_is_read_by_the_narrator():
    services = SpeakerServices()
    services.fail = True
    speaker = orbit_speech.Speaker(services)
    speaker.say("Sari says: hello", voice="bravo")
    assert services.log == [("narrator", "Sari says: hello")]


def test_a_busy_room_drops_the_oldest_waiting_lines():
    services = SpeakerServices()
    speaker = orbit_speech.Speaker(services)
    speaker.say("first", voice="bravo")
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


def test_the_ambience_fades_in_loops_and_dips_under_hariku_voice():
    mci = FakeMci()
    speaking = [False]
    player, now = _player(mci, lambda: speaking[0])
    player.apply("play", ("C:/sounds/amb_vent.wav", 30))
    _steps(player, now, 1)
    assert mci.commands[0] == 'open "C:/sounds/amb_vent.wav" type mpegvideo alias hariku_orbit_ambience'
    assert "play hariku_orbit_ambience repeat" in mci.commands
    _steps(player, now, 20)
    assert mci.volumes()[-1] == 300 and mci.volumes() == sorted(mci.volumes())       # faded in
    assert not hasattr(player, "hush")             # the screen reader never hushes it
    speaking[0] = True
    _steps(player, now, 10)
    assert mci.volumes()[-1] == 90 and min(mci.volumes()[-10:]) == 90     # a dip under Hariku Voice, not silence
    speaking[0] = False
    _steps(player, now, 10)
    assert mci.volumes()[-1] == 300                # and back
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
    # With the window closed there is no loop and no thread, and the calls
    # made meanwhile must not queue up forever.
    player = orbit_audio.AmbiencePlayer(mci=FakeMci(), pump=lambda: None)
    for _i in range(100):
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
    client = FakeClient([WELCOME, '{"t": "ev", "k": "room", "text": "Dock."}', "not json"])
    conn, events, made, _hellos = _connection([client])
    conn.send({"t": "cmd", "c": "look"})               # before connecting: waits
    conn.start()
    assert _wait(lambda: ("message", {"t": "ev", "k": "room", "text": "Dock."}) in events)
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
    # Old enough to drop, with time to spare for the fresh one on a busy test machine.
    monkeypatch.setattr(orbit_net, "QUEUE_MAX_AGE", 0.5)
    client = FakeClient([WELCOME])
    conn, events, made, _hellos = _connection([client])
    conn.send({"t": "cmd", "c": "say", "a": "stale"})
    time.sleep(0.7)
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
    assert client.submit("voices off") == "local"
    assert s.values["voices"] is False and s.spoken[-1] == ("narrator", "Players' voices off: everyone is read by your usual voice.")
    client.submit("speech off")
    assert s.values["speak"] is False
    assert s.spoken[-1] == ("narrator", "Messages aren't read aloud now; they still go to the Messages box.")   # said anyway
    client.submit("effects volume 40")
    assert s.values["effects_volume"] == 40 and client.messages[-1] == "Effects volume 40 percent."
    client.submit("ambience off")
    assert s.values["ambience"] is False and s.ambiences[-1] == (None, None)
    client.submit("settings")
    assert s.settings_opened == 1
    assert conn.sent == []                                   # none of it went to the server


def test_what_is_read_can_be_narrowed(play):
    s, client = play.services, play.client
    s.values.update(read_say=False, read_moves=False, read_money=False)
    conn = _online(play)
    count = len(s.spoken)
    conn.event("say", "Sari says: hello", actor="Sari")
    conn.event("emote", "Sari smiles.", actor="Sari", emote="smile")
    conn.event("arrive", "Budi arrives from the west.", actor="Budi", dir="w")
    conn.event("received", "Budi gives you 5 credits.", actor="Budi")
    assert len(s.spoken) == count                           # not read...
    assert client.messages[-4:] == ["Sari says: hello", "Sari smiles.",
                                    "Budi arrives from the west.", "Budi gives you 5 credits."]
    assert s.sounds[-4:] == ["say", "emote", "arrive", "coins"]               # ...but heard
    conn.event("whisper", "Budi whispers to you: psst", actor="Budi")
    conn.event("emote", "You smile.", emote="smile")   # your own gesture: always
    assert s.spoken[-1] == ("narrator", "You smile.") and s.spoken[-2][1] == "Budi whispers to you: psst"
    # A reply to your own command is always read: you were paid, you bought, you sold.
    conn.event("paid", "You're paid 40 credits.")
    conn.event("trade", "You buy an iced coffee for 15 credits. You have 85 credits.", brief="Bought.")
    conn.event("gave", "You give Budi 5 credits.", actor="Rafli")
    assert [t for _v, t in s.spoken[-3:]] == ["You're paid 40 credits.", "Bought.", "You give Budi 5 credits."]
    client.submit("orbit who is online", "aruna")
    conn.event("say", "Sari says: I'm here", actor="Sari")
    assert s.spoken[-1][1] == "Sari says: I'm here"   # Aruna asked: everything is read


ALL_READ_OFF = {key: False for key in ("read_say", "read_whisper", "read_shout", "read_moves", "read_money",
                                        "read_announce", "read_events")}


@pytest.mark.parametrize("reader", ["mixed", "nvda", "voices"])
@pytest.mark.parametrize("kind", ["paid", "failed", "received", "gave", "trade", "info", "error", "emote",
                                  "mission", "task", "flight", "room", "moved", "system", "who", "tones"])
def test_a_reply_to_your_own_command_is_read_whatever_the_filters(play, reader, kind):
    s, client = play.services, play.client
    s.values.update(ALL_READ_OFF, reader=reader)
    conn = _online(play)
    s.spoken.clear()
    s.timers = []                                       # not the client's own tick
    conn.event(kind, "You get 3 sacks of coffee.", sound="coins")
    s.run_timers()
    assert [t for _v, t in s.spoken] == ["You get 3 sacks of coffee."], (reader, kind, s.spoken)
    s.spoken.clear()
    conn.event(kind, "Sam gives you 3 sacks of coffee.", actor="Sam")            # what others do: filtered
    s.run_timers()
    filtered = orbit_play.READ_KINDS.get(kind) is not None
    assert (s.spoken == []) == filtered, (reader, kind, s.spoken)


def test_lines_are_read_in_the_order_they_came_even_behind_a_wait(play):
    s = play.services
    s.FILES = FakeServices.FILES | {"dice", "win"}
    s.values["reader"] = "nvda"
    conn = _online(play)
    s.spoken.clear()
    s.timers = []
    conn.event("paid", "The dice roll 5 and 6: 11. You win 230 credits!", sound="dice", outcome="win")
    conn.event("paid", "Achievement: High Roller.", sound="achievement")         # came right after
    conn.event("info", "Rocco raises an eyebrow.")
    assert s.spoken == []                               # all wait for the dice to land
    s.run_timers()
    assert [t for _v, t in s.spoken] == ["The dice roll 5 and 6: 11. You win 230 credits!",
                                         "Achievement: High Roller.", "Rocco raises an eyebrow."]
    conn.event("info", "Nothing waits now.")
    assert s.spoken[-1] == ("reader", "Nothing waits now.")


def test_with_the_window_closed_only_what_matters_is_heard(play):
    s, client = play.services, play.client
    conn = _online(play, name="Rafli")
    s.window = False
    s.spoken.clear()
    s.sounds.clear()
    conn.event("say", "Sari says: hello everyone", actor="Sari")
    conn.event("arrive", "Budi comes in.", actor="Budi", dir="n")
    assert s.spoken == [] and s.sounds == []                # quiet, and shown
    assert client.messages[-1] == "Budi comes in."
    conn.event("say", "Sari says: Rafli, to the cantina?", actor="Sari")
    conn.event("whisper", "Budi whispers to you: psst", actor="Budi")
    conn.event("announce", "Announcement from the Bridge: server restart at 9")
    assert [line for _who, line in s.spoken] == ["Sari says: Rafli, to the cantina?",
                                                  "Budi whispers to you: psst",
                                                  "Announcement from the Bridge: server restart at 9"]
    assert s.sounds == ["say", "whisper", "announce"]
    s.values["background"] = "none"
    conn.event("whisper", "Budi whispers to you: hello?", actor="Budi")
    assert len(s.spoken) == 3 and len(s.sounds) == 3
    s.values["background"] = "all"
    conn.event("say", "Sari says: bye", actor="Sari")
    assert s.spoken[-1][1] == "Sari says: bye"


def test_ignored_players_are_neither_shown_nor_heard(play):
    s, client = play.services, play.client
    conn = _online(play)
    client.submit("ignore Budi")
    assert s.values["ignored"] == ["Budi"] and client.messages[-1].startswith("Ignoring Budi")
    lines = len(client.messages)
    conn.event("say", "Budi says: hey", actor="Budi")
    conn.event("shout", "Budi shouts: HEY", actor="Budi")
    conn.event("emote", "Budi waves at you.", actor="budi", emote="wave")
    conn.event("offer", "Budi invites you to their cabin.", actor="Budi", ask=True)
    assert len(client.messages) == lines
    conn.event("arrive", "Budi comes in.", actor="Budi")      # where they are still shows
    assert client.messages[-1] == "Budi comes in."
    client.submit("unignore budi")
    assert s.values["ignored"] == []
    conn.event("say", "Budi says: sorry", actor="Budi")
    assert client.messages[-1] == "Budi says: sorry"


def test_other_players_sounds_can_be_turned_off(play):
    s = play.services
    s.values["other_sounds"] = False
    conn = _online(play)
    s.sounds.clear()
    conn.event("say", "Sari says: hello", actor="Sari")
    conn.event("arrive", "Budi comes in.", actor="Budi", dir="w")
    conn.event("whisper", "Budi whispers to you: psst", actor="Budi")
    conn.event("paid", "You're paid.")
    assert s.sounds == ["whisper", "success"]


def test_cues_come_from_their_side_with_a_fallback(play):
    s = play.services
    conn = _online(play)
    s.placed.clear()
    conn.event("moved", "You walk west.", dir="w", floor="metal", acoustics="hall", room="x", amb="vent")
    conn.event("moved", "You walk east.", dir="e", floor="grass", room="y", amb="garden")
    conn.event("arrive", "Budi comes in from the east.", actor="Budi", dir="e")
    conn.event("paid", "Level up!", sound="levelup")
    conn.event("paid", "You harvest.", sound="harvest")
    assert s.placed == [("step_metal", -0.75, "hall"), ("door", 0.75, "hall"), ("arrive", 0.75, "hall"),
                        ("levelup", 0.0, None), ("success", 0.0, None)]


def test_a_chosen_voice_and_its_preview(play):
    s = play.services
    conn = _online(play, name="Rafli")
    voices = orbit_speech.voices_of(FakeServices.VOICES, "en")
    conn.event("say", "Sari says: hello", actor="Sari", voice=2)
    assert s.spoken[-1] == (voices[1]["id"], "Sari says: hello")
    conn.event("say", "Budi says: hello", actor="Budi", voice=5)
    assert s.spoken[-1] == (voices[(5 - 1) % 3]["id"], "Budi says: hello")
    conn.event("info", "Done: others now hear you in voice 3.", voice=3, preview=True)
    assert s.spoken[-1] == (voices[2]["id"], "Done: others now hear you in voice 3.")


def test_a_players_name_and_their_words_come_in_two_voices(play):
    s = play.services
    conn = _online(play, name="Rafli")
    voices = orbit_speech.voices_of(FakeServices.VOICES, "en")
    sari = orbit_speech.pick_voice("Sari", voices)["id"]
    s.spoken.clear()
    conn.event("say", "Sari says: hello everyone", actor="Sari", words="hello everyone")
    assert s.spoken == [("narrator", "Sari:"), (sari, "hello everyone")]
    conn.event("whisper", "Sari whispers to you: later", actor="Sari", words="later", voice=2)
    assert s.spoken[-2:] == [("narrator", "Sari, whispering:"), (voices[1]["id"], "later")]
    conn.event("shout", "Sari shouts across the station: to the Moon!", actor="Sari", words="to the Moon!")
    assert s.spoken[-2:] == [("narrator", "Sari, shouting:"), (sari, "to the Moon!")]
    assert play.client.messages[-1] == "Sari shouts across the station: to the Moon!"   # the whole line
    s.values["speak_names"] = False
    conn.event("say", "Sari says: no name", actor="Sari", words="no name")
    assert s.spoken[-1] == (sari, "no name") and s.spoken[-2] != ("narrator", "Sari:")
    # an older server (no "words"): the whole line in the speaker's voice, as before
    conn.event("say", "Sari says: old server", actor="Sari")
    assert s.spoken[-1] == (sari, "Sari says: old server")


def test_crew_chat_is_voiced_ignorable_and_heard_in_the_background(play):
    s = play.services
    conn = _online(play, name="Rafli")
    voices = orbit_speech.voices_of(FakeServices.VOICES, "en")
    sari = orbit_speech.pick_voice("Sari", voices)["id"]
    s.spoken.clear()
    conn.event("crew", "Sari, to the crew Nova: meet on deck", actor="Sari", words="meet on deck",
               sound="crew_chat")
    assert s.spoken == [("narrator", "Sari, to the crew:"), (sari, "meet on deck")]
    conn.event("crew_sent", "You tell the crew Nova: ready", brief="Told the crew.", words="ready", voice=3)
    assert s.spoken[-1] == (voices[2]["id"], "ready")
    assert orbit_audio.cues_for({"k": "crew", "sound": "crew_chat"}) == [("crew_chat", 0.0, None, "whisper")]
    assert orbit_audio.cues_for({"k": "crew_sent"}) == [("sent", 0.0, None, None)]
    # ignored players are ignored here too; the "whispers" setting covers crew chat
    s.values["ignored"] = ["sari"]
    before = len(s.spoken)
    conn.event("crew", "Sari, to the crew Nova: hello", actor="Sari", words="hello")
    assert len(s.spoken) == before
    s.values["ignored"] = []
    s.values["read_whisper"] = False
    conn.event("crew", "Sari, to the crew Nova: hello", actor="Sari", words="hello")
    assert len(s.spoken) == before
    s.values["read_whisper"] = True
    # with the window closed, crew chat is still heard ("whispers, my name and events")
    s.window = False
    conn.event("crew", "Sari, to the crew Nova: hear me?", actor="Sari", words="hear me?")
    assert s.spoken[-1] == (sari, "hear me?")


def test_your_own_lines_are_spoken_in_your_character_voice(play):
    s = play.services
    conn = _online(play, name="Rafli")
    voices = orbit_speech.voices_of(FakeServices.VOICES, "en")
    s.spoken.clear()
    conn.event("said", "You say: hello Sari", brief="Sent.", words="hello Sari", voice=3)
    assert s.spoken == [(voices[2]["id"], "hello Sari")]
    conn.event("said", "You say: no number", brief="Sent.", words="no number")
    assert s.spoken[-1] == (orbit_speech.pick_voice("Rafli", voices)["id"], "no number")
    conn.event("whispered", "You whisper to Sari: later", brief="Whispered to Sari.", words="later",
               to="Sari", voice=3)
    assert s.spoken[-2:] == [("narrator", "To Sari:"), (voices[2]["id"], "later")]
    conn.event("shouted", "You shout: hello!", brief="Shouted.", words="hello!", voice=3)
    assert s.spoken[-1] == (voices[2]["id"], "hello!")
    conn.event("emote", "You smile.", emote="smile")
    assert s.spoken[-1] == ("narrator", "You smile.")                  # gestures: the narrator
    play.client.aruna_until = float("inf")                                  # said through Aruna
    conn.event("said", "You say: from Aruna", brief="Sent.", words="from Aruna", voice=3)
    assert s.spoken[-1] == (voices[2]["id"], "from Aruna") and s.shown[-1] == "Sent."
    play.client.aruna_until = 0
    # the setting off: only the short confirmation, as before
    play.client.submit("my lines off")
    assert s.values["speak_own"] is False and s.spoken[-1] == ("narrator", "Your own lines are only confirmed.")
    conn.event("said", "You say: hello again", brief="Sent.", words="hello again", voice=3)
    assert s.spoken[-1] == ("narrator", "Sent.")
    play.client.submit("my lines on")
    assert s.values["speak_own"] is True
    play.client.submit("names off")
    assert s.values["speak_names"] is False and s.spoken[-1][1] == "Only players' words are said, without their names."


def test_with_too_few_voices_everyone_is_read_by_the_narrator_and_you_are_told_once(play):
    s = play.services
    s.voices_on = False                          # Hariku Voice has only one English voice
    conn = _online(play, name="Rafli")
    s.spoken.clear()
    conn.event("say", "Sari says: hello", actor="Sari", words="hello")
    hint = ("narrator", "Hariku Voice has fewer than two English voices, so every player sounds the same. "
                        "For voices of their own, get Edge Voices or Piper Voices from the Extension Store.")
    assert s.spoken == [hint, ("narrator", "Sari says: hello")]
    assert hint[1] in play.client.messages
    conn.event("said", "You say: hi", brief="Sent.", words="hi")
    conn.event("say", "Sari says: again", actor="Sari", words="again")
    assert s.spoken[2:] == [("narrator", "hi"), ("narrator", "Sari says: again")]      # told once
    # players' voices turned off: no hint needed, the narrator reads
    s.values["voices"] = False
    play.client.voices_hint_said = False
    conn.event("say", "Sari says: no voice", actor="Sari", words="no voice")
    assert s.spoken[-1] == ("narrator", "Sari says: no voice") and hint not in s.spoken[4:]


def test_the_narrator_is_hariku_voice_when_it_can_speak(play):
    s = play.services
    s.narrator = {"provider": "windows", "id": "charlie"}
    conn = _online(play, name="Rafli")
    s.spoken.clear()
    conn.event("room", "Cantina. Round tables.")
    conn.event("say", "Sari says: hello", actor="Sari", words="hello")
    sari = orbit_speech.pick_voice("Sari", orbit_speech.voices_of(FakeServices.VOICES, "en"))["id"]
    assert s.spoken == [("charlie", "Cantina. Round tables."), ("charlie", "Sari:"), (sari, "hello")]


def test_a_busy_room_drops_whole_lines_never_half_of_one():
    services = SpeakerServices()
    speaker = orbit_speech.Speaker(services)
    speaker.say("first", voice="bravo")                  # still speaking
    for i in range(orbit_speech.MAX_WAITING + 3):
        speaker.say_parts([("Sari:", None), (f"line {i}", "bravo")])
    assert len(speaker.waiting) == orbit_speech.MAX_WAITING
    assert list(speaker.waiting[0]) == [("Sari:", None), ("line 3", "bravo")]
    while services.pending:
        services.pending.pop(0)(None)
    spoken = [text for _who, text in services.log]
    assert spoken[:3] == ["first", "Sari:", "line 3"] and spoken[-2:] == ["Sari:", f"line {orbit_speech.MAX_WAITING + 2}"]


def test_numbered_voices_are_the_same_on_every_turn():
    voices = orbit_speech.voices_of(FakeServices.VOICES, "en")
    assert [orbit_speech.pick_voice("anyone", voices, number=n)["id"] for n in (1, 2, 3, 4)] == \
        ["en-GB-Alpha", "en-US-Bravo", "charlie", "en-GB-Alpha"]
    assert orbit_speech.pick_voice("Sari", voices, number=0) == orbit_speech.pick_voice("Sari", voices)
    assert orbit_speech.pick_voice("Sari", voices[:1], number=2) is None
    narrator = ("edge", "en-GB-Alpha")
    assert orbit_speech.pick_voice("x", voices, exclude=narrator, number=1)["id"] == "en-US-Bravo"


# ------------------------------------------------------------
# Closing, leaving, being away, the status
# ------------------------------------------------------------

def test_closing_the_window_stays_connected_and_says_how_to_come_back(play):
    s, client = play.services, play.client
    conn = _online(play)
    for _i in range(3):
        assert client.window_closing() is False
        assert s.spoken[-1] == ("narrator", "Orbit stays connected. Open it again with Ctrl + Shift + O, "
                                            "or tell Aruna: open orbit. To leave, type quit.")
    client.window_closing()
    assert s.spoken[-1] == ("narrator", "Orbit in the background.") and s.values["close_hints"] == 3
    assert not conn.stopped and client.online()
    s.values.update(close_hints=0)
    s.key = ""
    client.window_closing()
    assert "by telling Aruna: open orbit" in s.spoken[-1][1] and "with ," not in s.spoken[-1][1]


def test_closing_the_window_can_leave_orbit(play):
    s, client = play.services, play.client
    s.values["close_action"] = "leave"
    conn = _online(play)
    assert client.window_closing() is True
    assert conn.sent[-1] == {"t": "cmd", "c": "bye"} and conn.stopped
    assert client.status == "Not connected." and client.title_state == "Left"


def test_leaving_says_goodbye_to_the_server(play):
    s, client = play.services, play.client
    conn = _online(play)
    client.submit("quit")
    assert conn.sent == [{"t": "cmd", "c": "bye"}] and conn.stopped
    assert s.spoken[-1] == ("narrator", "You've left Orbit.")
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
    client.submit("look")
    assert client.away is False and conn.sent[-1] == {"t": "cmd", "c": "look"}
    now[0] += 30 * 60
    client.check_idle()
    assert "You've been logged out of Orbit because you were away for a long time." in [t for _w, t in s.spoken]
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
    assert s.spoken[-1] == ("narrator", "Not connected.")
    conn = _online(play)
    client.submit("orbit status", "aruna")
    assert conn.sent[-1] == {"t": "cmd", "c": "status"}
    assert client.title_state == "Connected"
    conn.on_state("offline", {"reason": "lost", "retry_in": 8})
    assert client.title_state == "Disconnected"
    client.submit("status")
    assert s.spoken[-1] == ("narrator", "Disconnected, reconnecting in 8 seconds...")


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
    conn.event("info", "Your transfer code: A B C D, ...", transfer_code="ABCD-EFGH-JKLM-NPQR", expires=600)
    assert client.transfer_code == "ABCD-EFGH-JKLM-NPQR" and ("transfer", "ABCD-EFGH-JKLM-NPQR") in notes
    # The other computer.
    other = FakeServices()
    elsewhere = orbit_play.OrbitClient(other)
    assert elsewhere.redeem_transfer("abcd efgh jklm npq") is False     # 15 letters
    assert other.connections == []
    assert elsewhere.redeem_transfer("abcd-efgh-jklm-npqr") is True
    hello = other.connections[-1].hello()
    assert hello == {"t": "hello", "v": 1, "client": "Hariku Orbit 1.7", "lang": "en",
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
                                          "text": "That transfer code doesn't work."})
    assert s.accounts[s.values["server"]] == old
    assert client.status == "That transfer code doesn't work."


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
    with open(os.path.join(server, "economy.json"), encoding="utf-8") as f:
        economy = json.load(f)
    found.update(t["effects"]["pet"]["sound"] for t in economy["things"].values()
                 if (t.get("effects") or {}).get("pet"))             # each kind of pet's own
    with open(os.path.join(server, "world.json"), encoding="utf-8") as f:
        world = json.load(f)
    found.update(e.get("sound") or f"emote_{eid}" for eid, e in world["emotes"].items())   # 1.6's reuse cues
    for event in world.get("events", {}).values():
        found.update(event[k] for k in ("sound", "clue_sound") if event.get(k))
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
    assert total < 11 * 1024 * 1024, total
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


# --------------------------------------------------------------------------- #
# Who reads the game: NVDA straight away, Hariku Voice for talk (1.3)
# --------------------------------------------------------------------------- #

def test_mixed_reading_gives_talk_to_voices_and_the_rest_to_the_screen_reader(play):
    s, client = play.services, play.client
    s.values["reader"] = "mixed"
    conn = _online(play)
    s.spoken.clear()
    conn.event("moved", "You walk to the Cantina. Cantina. Exits: north, southwest.",
               room="cantina", amb="cantina")
    assert s.spoken[-1] == ("reader", "You walk to the Cantina. Cantina. Exits: north, southwest.")
    s.spoken.clear()
    conn.event("say", "Sari says: hello Rafli!", actor="Sari", words="hello Rafli!")
    assert s.spoken[0] == ("narrator", "Sari:") or s.spoken[0][0] not in ("reader",)
    assert all(who != "reader" for who, _line in s.spoken)          # a voice, not NVDA
    s.spoken.clear()
    conn.event("announce", "Announcement: server restart at 3.", words="server restart at 3.")
    assert s.spoken and all(who != "reader" for who, _line in s.spoken)
    assert client.messages[-1] == "Announcement: server restart at 3."


def test_nvda_reading_reads_everything_at_once_and_whole(play):
    s = play.services
    s.values["reader"] = "nvda"
    conn = _online(play)
    s.spoken.clear()
    conn.event("say", "Sari says: hello Rafli!", actor="Sari", words="hello Rafli!")
    conn.event("moved", "You walk to the Observation Deck.", room="observation")
    assert s.spoken == [("reader", "Sari says: hello Rafli!"), ("reader", "You walk to the Observation Deck.")]


def test_the_reader_can_be_changed_from_the_game(play):
    assert orbit_parse.parse("reader nvda") == {"local": "set", "key": "reader", "value": "nvda"}
    assert orbit_parse.parse("reader mixed") == {"local": "set", "key": "reader", "value": "mixed"}
    assert orbit_parse.parse("reader voices") == {"local": "set", "key": "reader", "value": "voices"}
    s, client = play.services, play.client
    conn = _online(play)
    assert client.submit("reader nvda") == "local"
    assert s.values["reader"] == "nvda" and s.spoken[-1] == ("reader", "NVDA reads everything.")
    assert conn.sent == []
