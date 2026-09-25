# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Orbit extension (extensions/orbit), all on fakes: reading
# commands in Indonesian and English, Aruna's "orbit ..." commands, playing
# (what is shown, played and said, and by whom), each player's own voice, the
# speaking queue, the ambience player (a fake MCI), the connection thread (a
# fake socket), the settings, registering, and the generated sounds. Nothing
# is sent, played, spoken or shown. tests/test_orbit_e2e.py plays against the
# real server on this computer.

import importlib.util
import io
import math
import os
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
    ("", None), ("   ", None),
])
def test_reading_commands_in_both_languages(text, expected):
    assert orbit_parse.parse(text) == expected


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
    assert {args[1] for args, _kw in actions} == {"open", "look", "who", "credits", "connect"}
    for args, kwargs in actions:
        assert args[0] == "Orbit" and args[3] is None and kwargs == {}        # no default keys
    assert core.commands.is_answer_action("Orbit.look") and core.commands.is_answer_action("Orbit.who")
    assert not core.commands.is_answer_action("Orbit.open")                # it opens a window
    assert [i.id for i in core.commands.intents()] == ["Orbit.play"]
    assert "buka orbit" in core.commands.aliases_for("Orbit.open")
    assert panels[0][0] == "Orbit"
    assert omain._on_before_speak in fresh_event_bus._listeners["on_before_speak"]
    omain.teardown()
    assert core.commands.intents() == [] and core.commands.aliases_for("Orbit.open") == []
    assert omain._on_before_speak not in fresh_event_bus._listeners.get("on_before_speak", [])


def test_settings_are_checked(omain):
    s = omain.normalize_settings({"server": "  wss://example.org/orbit/ws ", "name": " Rafli ",
                                  "job": "wizard", "speak": "yes", "ambience_volume": 250,
                                  "voices": False})
    assert s == {"server": "wss://example.org/orbit/ws", "name": "Rafli", "job": "pilot",
                 "speak": True, "voices": False, "ambience": True, "ambience_volume": 100,
                 "sounds": True}
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

    def __init__(self, **settings):
        self.values = {"server": "wss://infiartt.com/orbit/ws", "name": "Rafli", "job": "pilot",
                       "speak": True, "voices": True, "ambience": True, "ambience_volume": 25,
                       "sounds": True}
        self.values.update(settings)
        self.accounts = {}
        self.connections = []
        self.spoken = []
        self.sounds = []
        self.ambiences = []
        self.shown = []
        self.timers = []
        self.window = True
        self.voices_on = True
        self.secrets = 0

    def settings(self):
        return dict(self.values)

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

    def voice_for(self, name):
        if not self.voices_on:
            return None
        return orbit_speech.pick_voice(name, orbit_speech.voices_of(self.VOICES, "id"))

    def show_answer(self, text):
        self.shown.append(text)

    def play(self, name):
        self.sounds.append(name)

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
    assert hello == {"t": "hello", "v": 1, "client": "Hariku Orbit 1.0", "lang": "id",
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
    assert client.status == "Orbit sedang offline. Coba lagi dalam 8 detik."
    assert [t for _w, t in s.spoken].count("Orbit sedang offline. Aku coba terus, ya.") == 1
    assert s.ambiences[-1] == (None, None)
    conn.on_state("online", {})
    conn.on_message({"t": "welcome", "name": "Rafli", "job": "pilot", "resumed": True,
                     "room": "cantina", "amb": "cantina"})
    assert s.spoken[-1] == ("narrator", "Tersambung ke Orbit.") and s.ambiences[-1] == ("cantina", 25)
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
    assert s.spoken[-1] == (sari["id"], "Sari bilang: halo Rafli!") and s.sounds[-1] == "chat"
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
    assert s.sounds[-1] == "chat"
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
    assert s.spoken == [] and len(s.timers) == 4
    s.run_timers()
    assert [x for x in s.sounds if x.startswith("tone")] == ["tone2", "tone4", "tone1"]
    assert s.spoken == [("narrator", "Dengarkan 3 nada penstabil: 2, 4, 1.")]


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
    assert s.ambiences[-1] == (None, None) and s.spoken[-1] == ("narrator", "Sambungan ke Orbit diputus.")


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
    assert client.messages[-1].startswith("Perintah Orbit.") and s.spoken[-1][1].startswith("Perintah Orbit.")
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
    assert speaker.waiting[0][0] == "line 5"


# ------------------------------------------------------------
# Sounds and the ambience
# ------------------------------------------------------------

def test_which_sound_an_event_plays():
    assert orbit_audio.sound_for({"k": "moved"}) == "door"
    assert orbit_audio.sound_for({"k": "whisper", "actor": "Sari"}) == "whisper"
    assert orbit_audio.sound_for({"k": "emote", "actor": "Sari"}) == "chat"
    assert orbit_audio.sound_for({"k": "emote"}) == "sent"
    assert orbit_audio.sound_for({"k": "flight", "sound": "launch"}) == "launch"
    assert orbit_audio.sound_for({"k": "room"}) is None
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
# The sounds
# ------------------------------------------------------------

def _read(name):
    with wave.open(os.path.join(SOUNDS_DIR, name)) as w:
        frames = w.readframes(w.getnframes())
        return (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes(),
                memoryview(frames).cast("h"))


def test_every_sound_played_is_there():
    import orbit_sounds
    names = {name for name, _make in orbit_sounds.SOUNDS}
    needed = set(orbit_audio.SOUND_FOR_KIND.values()) | set(orbit_audio.EXTRA_SOUNDS.values())
    needed |= {f"tone{i}" for i in range(1, 5)} | {f"amb_{a}" for a in orbit_audio.AMBIENCES}
    assert {f"{n}.wav" for n in needed} == names
    assert sorted(os.listdir(SOUNDS_DIR)) == sorted(names)


def test_the_sounds_are_stereo_and_polite():
    import orbit_sounds
    for name, _make in orbit_sounds.SOUNDS:
        channels, width, rate, frames, samples = _read(name)
        assert channels == 2 and width == 2, name
        seconds = frames / rate
        loudest = max(abs(v) for v in samples)
        assert 0.15 * 32767 < loudest < 0.6 * 32767, name
        if name.startswith("amb_"):
            assert rate == orbit_sounds.LOOP_RATE and seconds == orbit_sounds.LOOP_SECONDS, name
        else:
            assert 0.1 <= seconds <= 3.1 and rate == orbit_sounds.RATE, name
            assert abs(samples[0]) < 300 and abs(samples[-1]) < 300, name          # no clicks


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


def test_the_sounds_move_left_to_right():
    for number, louder in ((1, "left"), (2, "left"), (3, "right"), (4, "right")):
        _c, _w, _r, frames, samples = _read(f"tone{number}.wav")
        left, right = _loudness(samples, 0, frames)
        assert (left > right) == (louder == "left"), number
    _c, _w, rate, frames, samples = _read("door.wav")
    early = _loudness(samples, int(0.05 * rate), int(0.2 * rate))
    late = _loudness(samples, int(0.42 * rate), int(0.57 * rate))
    assert early[0] > early[1] and late[1] > late[0]
    _c, _w, rate, frames, samples = _read("whisper.wav")
    left, right = _loudness(samples, 0, frames)
    assert right > 2 * left                          # close to your right ear


@pytest.mark.parametrize("name", ["tone1.wav", "tone4.wav", "chat.wav", "error.wav", "sent.wav",
                                  "mission.wav", "arrive.wav"])
def test_the_sounds_are_what_the_generator_makes(name):
    import orbit_sounds
    make = dict(orbit_sounds.SOUNDS)[name]
    with open(os.path.join(SOUNDS_DIR, name), "rb") as f:
        assert f.read() == make()
