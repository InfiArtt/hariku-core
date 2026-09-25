# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Orbit end to end, over real sockets on this computer only (127.0.0.1, a port
# the system picks): the real server (servers/orbit) on a thread, and two
# players using the extension's own client (its WebSocket code, its
# connection thread with reconnecting, its command parser and OrbitClient),
# with fake speech, sounds and ambience. They join, walk, talk, whisper, work,
# give credits, and one of them loses the connection and comes back. Also:
# the health check over plain HTTP, a name that is taken, raw protocol abuse,
# and the server started as a program (python orbit_server.py). Nothing leaves
# this computer.

import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
for folder in (SERVER_DIR, EXT_DIR):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import orbit_mix  # noqa: E402
import orbit_net  # noqa: E402
import orbit_play  # noqa: E402
import orbit_server  # noqa: E402
import orbit_speech  # noqa: E402
import orbit_ws as ws  # noqa: E402

VOICES = [{"id": "id-ID-ArdiNeural", "name": "Ardi", "language": "id-ID"},
          {"id": "id-ID-GadisNeural", "name": "Gadis", "language": "id-ID"},
          {"id": "id-ID-Andika", "name": "Andika", "language": "id-ID"}]


@pytest.fixture(autouse=True)
def only_this_computer(monkeypatch):
    real = socket.create_connection

    def local_only(address, *args, **kwargs):
        assert address[0] in ("127.0.0.1", "localhost", "::1"), f"network access to {address}"
        return real(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", local_only)


@pytest.fixture
def indonesian(monkeypatch):
    """Hariku in Indonesian: Orbit's own words too."""
    from core import i18n
    monkeypatch.setattr(i18n, "_current_language", "id")


@pytest.fixture
def server(tmp_path):
    config = orbit_server.load_config(None, {
        "port": 0, "database": str(tmp_path / "orbit.db"), "hash_iterations": 1000,
        "tick_seconds": 0.05, "rate": 50.0, "burst": 50,
        "game": {"admins": ["Rafli"], "flight_seconds": 0.6, "linkdead_seconds": 30,
                 "engineer_cooldown": 1, "pilot_cooldown": 1}})
    thread = orbit_server.ServerThread(config).start()
    yield thread
    thread.stop()


class Loop:
    """The players' "UI thread": the test's own, running what the client
    asks for with call_after and call_later."""

    def __init__(self):
        self.soon = queue.Queue()
        self.timers = []
        self.lock = threading.Lock()

    def after(self, fn, *args):
        self.soon.put((fn, args))

    def later(self, seconds, fn):
        timer = {"due": time.monotonic() + seconds, "fn": fn, "cancelled": False}
        with self.lock:
            self.timers.append(timer)
        return type("Timer", (), {"cancel": lambda self_: timer.update(cancelled=True)})()

    def run_until(self, condition, timeout=8.0):
        end = time.monotonic() + timeout
        while True:
            while True:
                try:
                    fn, args = self.soon.get_nowait()
                except queue.Empty:
                    break
                fn(*args)
            now = time.monotonic()
            with self.lock:
                due = [t for t in self.timers if t["due"] <= now]
                self.timers = [t for t in self.timers if t["due"] > now]
            for timer in due:
                if not timer["cancelled"]:
                    timer["fn"]()
            if condition():
                return True
            if now > end:
                return False
            time.sleep(0.01)


class Services:
    """What a player's OrbitClient uses: the real connection, fake everything else."""

    def __init__(self, loop, url, name, job, language="id"):
        self.loop = loop
        self.lang = language
        self.values = {"server": url, "name": name, "job": job, "speak": True, "voices": True,
                       "ambience": True, "ambience_volume": 25, "sounds": True, "effects_volume": 100,
                       "other_sounds": True, "background": "important", "close_action": "stay",
                       "auto_logout": 30, "ignored": [], "close_hints": 0}
        self.mixer = orbit_mix.Mixer(lambda: [os.path.join(EXT_DIR, "sounds")], "")
        self.accounts = {}
        self.spoken = []            # (who, text): "narrator" or a voice id
        self.sounds = []
        self.ambiences = []
        self.shown = []

    def settings(self):
        return dict(self.values)

    def set_setting(self, key, value):
        self.values[key] = value

    def open_settings(self):
        pass

    def open_key(self):
        return ""

    def language(self):
        return self.lang

    def account(self, url):
        return dict(self.accounts[url]) if url in self.accounts else None

    def save_account(self, url, account):
        self.accounts[url] = dict(account)

    def new_secret(self):
        return os.urandom(32).hex()

    def connect(self, url, hello, on_message, on_state):
        return orbit_net.Connection(url, hello, on_message, on_state, backoff=(0.1, 0.2, 0.4))

    def call_later(self, seconds, fn):
        return self.loop.later(seconds, fn)

    def call_after(self, fn, *args):
        self.loop.after(fn, *args)

    def say(self, text):
        self.spoken.append(("narrator", text))
        return True                                  # as if Hariku Voice said it

    def speak_voice(self, text, voice, on_done):
        self.spoken.append((voice["id"], text))
        threading.Timer(0.01, on_done, [None]).start()
        return True

    def voice_busy(self):
        return False

    def voice_for(self, name, number=None):
        return orbit_speech.pick_voice(name, orbit_speech.voices_of({"edge": VOICES}, self.lang), number=number)

    def show_answer(self, text):
        self.shown.append(text)

    def play(self, name, pan=0.0, acoustics=None):
        if not self.mixer.variants(name):
            return False
        self.sounds.append(name)
        return True

    def ambience(self, name, volume):
        self.ambiences.append(name)

    def window_open(self):
        return True


class Player:
    def __init__(self, loop, url, name, job, language="id"):
        self.loop = loop
        self.services = Services(loop, url, name, job, language)
        self.client = orbit_play.OrbitClient(self.services)

    def said(self, text, since=0):
        return any(text in line for line in self.client.messages[since:])

    def heard(self, text):
        return any(text in line for _who, line in self.services.spoken)

    def wait_for(self, text, timeout=8.0, since=0):
        assert self.loop.run_until(lambda: self.said(text, since), timeout), \
            f"{self.client.me or self.services.values['name']} never got {text!r}: {self.client.messages[-6:]}"

    def do(self, text, expect, source="window"):
        """Send a command and wait for a new line with `expect` in it; that line."""
        since = len(self.client.messages)
        self.client.submit(text, source)
        self.wait_for(expect, since=since)
        return next(line for line in self.client.messages[since:] if expect in line)

    def voice_of(self, line):
        return [who for who, said in self.services.spoken if line in said]


def _connection_of(server, name):
    for conn in list(server.server.connections):
        if conn.session is not None and conn.session.name == name:
            return conn
    return None


def test_two_players_on_the_station(server, indonesian):
    url = f"ws://127.0.0.1:{server.port}/orbit/ws"
    loop = Loop()
    rafli = Player(loop, url, "Rafli", "pilot")
    sari = Player(loop, url, "Sari", "engineer")

    # Joining.
    rafli.client.connect()
    assert loop.run_until(rafli.client.online), rafli.client.status
    rafli.wait_for("Selamat datang di Orbit, Rafli!")
    assert rafli.client.status == "Tersambung ke Orbit sebagai Rafli, Pilot."
    assert rafli.heard("Tersambung ke Orbit.") and rafli.services.ambiences[-1] == "vent"
    sari.client.connect()
    assert loop.run_until(sari.client.online)
    rafli.wait_for("Sari baru pertama kali masuk ke stasiun. Sapa, yuk!")
    assert "arrive" in rafli.services.sounds
    secret = rafli.services.accounts[url]["secret"]
    assert len(secret) == 64 and rafli.services.accounts[url]["joined"]

    # Walking by compass: both rooms are told which way.
    rafli.do("t", "Kamu berjalan ke timur, ke Gudang Kargo.")
    assert rafli.services.ambiences[-1] == "vent" and rafli.services.sounds[-1] == "step_metal"
    sari.wait_for("Rafli pergi ke timur, ke Gudang Kargo.")
    sari.do("timur", "Kamu berjalan ke timur, ke Gudang Kargo.")
    rafli.wait_for("Sari datang dari arah barat, dari Dermaga.")
    assert "Kamu berjalan di stasiun satu arah demi satu arah." in sari.do("pergi ke kantin", "Arah ke Kantin:")

    # Talking: the others hear it in the speaker's own voice; you, briefly.
    rafli.do("bilang halo Sari, selamat datang!", "Kamu bilang: halo Sari, selamat datang!")
    sari.wait_for("Rafli bilang: halo Sari, selamat datang!")
    rafli_voice = orbit_speech.pick_voice("Rafli", orbit_speech.voices_of({"edge": VOICES}, "id"))
    assert loop.run_until(lambda: sari.voice_of("Rafli bilang: halo Sari"))
    assert sari.voice_of("Rafli bilang: halo Sari") == [rafli_voice["id"]]
    assert rafli.heard("Terkirim.") and not rafli.heard("Kamu bilang: halo Sari")
    assert "sent" in rafli.services.sounds and "say" in sari.services.sounds

    sari.do("bisik Rafli ketemu di dek observasi ya", "Kamu berbisik ke Rafli: ketemu di dek")
    rafli.wait_for("Sari berbisik padamu: ketemu di dek observasi ya")
    assert "whisper" in rafli.services.sounds
    sari_voice = orbit_speech.pick_voice("Sari", orbit_speech.voices_of({"edge": VOICES}, "id"))
    assert loop.run_until(lambda: rafli.voice_of("Sari berbisik padamu"))
    assert rafli.voice_of("Sari berbisik padamu") == [sari_voice["id"]]
    sari.do("senyum ke Rafli", "Kamu tersenyum pada Rafli.")
    rafli.wait_for("Sari tersenyum padamu.")
    rafli.do("siapa online", "2 orang online: Rafli si pilot, di Gudang Kargo; Sari si insinyur, di Gudang Kargo.")

    # Work: the engineer repeats the reactor's tones...
    sari.do("t", "Kamu berjalan ke timur, ke Koridor Servis.")
    sari.do("t", "Ruang Mesin.")
    assert sari.services.ambiences[-1] == "engine"
    sari.do("kerja", "Dengarkan 3 nada penstabil")
    codes = re.search(r"nada penstabil: ([\d, ]+)\.", sari.client.messages[-1]).group(1)
    assert loop.run_until(lambda: sum(s.startswith("tone") for s in sari.services.sounds) == 3)
    sari.do(codes.replace(",", ""), "Kamu dibayar 40 kredit; kreditmu 140.")
    assert "success" in sari.services.sounds
    # ...and the pilot flies a cargo run to the Moon.
    rafli.do("b", "Kamu berjalan ke barat, ke Dermaga.")
    rafli.do("kerja", "Penjepit dilepas.")
    assert "launch" in rafli.services.sounds and rafli.services.ambiences[-1] == "engine"
    rafli.wait_for("Mendarat di Pangkalan Bulan Tranquility.")
    assert "landing" in rafli.services.sounds and rafli.services.ambiences[-1] == "vent"
    # Things that came later work for every client: they go as plain text.
    rafli.do("harian", "Bonus harian: 40 kredit")

    # Giving credits.
    sari.do("b", "Kamu berjalan ke barat, ke Koridor Servis.")
    sari.do("b", "Kamu berjalan ke barat, ke Gudang Kargo.")
    sari.do("b", "Kamu berjalan ke barat, ke Dermaga.")
    sari.do("beri Rafli 20 kredit", "Kamu memberi Rafli 20 kredit. Sisa kreditmu 120.")
    rafli.wait_for("Sari memberimu 20 kredit.")
    assert rafli.services.sounds[-1] == "coins"
    bag = rafli.do("tas", "Pekerjaan: pilot.")
    credits = int(re.search(r"Kreditmu (\d+)\.", bag).group(1))
    assert credits > 160

    # The connection drops: Rafli comes back by himself, as himself, and
    # nobody else notices anything.
    sari_lines = len(sari.client.messages)
    server.call(lambda: _connection_of(server, "Rafli").writer.transport.abort())
    assert loop.run_until(lambda: rafli.heard("Orbit sedang offline. Aku coba terus, ya."))
    assert loop.run_until(lambda: rafli.client.online() and rafli.said("Tersambung lagi."))
    assert loop.run_until(lambda: rafli.heard("Tersambung lagi."))
    assert rafli.services.accounts[url]["secret"] == secret
    rafli.do("tas", f"Kreditmu {credits}.")
    assert not any("Rafli" in line for line in sari.client.messages[sari_lines:])

    # Commands from Aruna are always answered aloud.
    rafli.services.values["speak"] = False
    rafli.client.submit("orbit lihat sekitar", "aruna")
    assert loop.run_until(lambda: rafli.heard("Dermaga. Cincin dermaga"))

    # Leaving: goodbye to the server, and Sari hears it at once (no minute's wait).
    sari_lines = len(sari.client.messages)
    rafli.client.submit("keluar")
    assert rafli.client.status == "Belum tersambung." and rafli.services.ambiences[-1] is None
    sari.wait_for("Rafli keluar dari Orbit.", since=sari_lines)
    sari.client.shutdown()


def test_a_taken_name_is_refused_and_not_retried(server):
    url = f"ws://127.0.0.1:{server.port}/orbit/ws"
    loop = Loop()
    first = Player(loop, url, "Budi", "trader")
    first.client.connect()
    assert loop.run_until(first.client.online)
    second = Player(loop, url, "budi", "pilot", language="en")
    second.client.connect()
    assert loop.run_until(lambda: second.client.state == "failed")
    assert second.client.status == "Someone on the station is already called Budi. Please choose another name."
    assert second.heard("already called Budi") and second.client.conn is None
    # Another name, the same account: joins.
    second.services.values["name"] = "Budi2"
    second.client.connect()
    assert loop.run_until(second.client.online)
    assert second.client.me == "Budi2"
    first.client.shutdown()
    second.client.shutdown()


def test_the_health_check_and_the_short_paths(server):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/orbit/health", timeout=5) as r:
        health = json.loads(r.read())
    assert health["ok"] and health["service"] == "orbit" and health["online"] == 0
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/health", timeout=5) as r:
        assert json.loads(r.read())["ok"]
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/secret", timeout=5)
    assert caught.value.code == 404
    client = ws.WebSocketClient.connect(f"ws://127.0.0.1:{server.port}/ws")
    client.send_json({"t": "hello", "v": 1, "lang": "en", "name": "Tono", "job": "scientist",
                      "secret": "7" * 64})
    assert client.recv_json(timeout=5)["t"] == "welcome"
    client.close()


def test_the_server_refuses_browsers_and_broken_clients(server):
    port = server.port

    def raw(request):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(request)
            return s.recv(4096)

    key = ws.make_key()
    upgrade = (f"GET /orbit/ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n")
    assert raw((upgrade + "Origin: https://evil.example\r\n\r\n").encode()).startswith(b"HTTP/1.1 403")
    assert raw(upgrade.replace("13", "8").encode() + b"\r\n").startswith(b"HTTP/1.1 426")
    # Joined clients must mask their frames and speak text.
    client = ws.WebSocketClient.connect(f"ws://127.0.0.1:{port}/orbit/ws")
    client._sock.sendall(ws.encode_frame(ws.OP_TEXT, '{"t":"hello"}', mask=False))
    with pytest.raises(ws.ConnectionClosed) as caught:
        while True:
            client.recv(timeout=5)
    assert caught.value.code == ws.CLOSE_PROTOCOL
    # A message before the hello closes the connection.
    client = ws.WebSocketClient.connect(f"ws://127.0.0.1:{port}/orbit/ws")
    client.send_json({"t": "cmd", "c": "look"})
    with pytest.raises(ws.ConnectionClosed) as caught:
        while True:
            client.recv(timeout=5)
    assert caught.value.code == ws.CLOSE_POLICY


def test_flooding_is_slowed_then_cut_off(tmp_path):
    config = orbit_server.load_config(None, {
        "port": 0, "database": str(tmp_path / "flood.db"), "hash_iterations": 1000,
        "rate": 2.0, "burst": 4, "abuse_limit": 10})
    with orbit_server.ServerThread(config) as srv:
        client = ws.WebSocketClient.connect(f"ws://127.0.0.1:{srv.port}/orbit/ws")
        client.send_json({"t": "hello", "v": 1, "lang": "en", "name": "Spammy", "job": "pilot",
                          "secret": "5" * 64})
        for _i in range(30):
            client.send_json({"t": "cmd", "c": "who"})
        texts, closed = [], None
        try:
            while True:
                message = client.recv_json(timeout=5)
                if message is None:
                    break
                texts.append(message.get("text", ""))
        except ws.ConnectionClosed as e:
            closed = e.code
        assert "Easy, not so fast! Wait a moment." in texts
        assert closed == ws.CLOSE_POLICY


def test_the_server_runs_as_a_program(tmp_path):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    process = subprocess.Popen(
        [sys.executable, os.path.join(SERVER_DIR, "orbit_server.py"), "--port", "0",
         "--db", str(tmp_path / "program.db")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", env=env)
    try:
        port = None
        lines = queue.Queue()
        threading.Thread(target=lambda: [lines.put(l) for l in process.stdout], daemon=True).start()
        end = time.monotonic() + 15
        while port is None and time.monotonic() < end:
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                continue
            found = re.search(r"listening on 127\.0\.0\.1:(\d+)", line)
            if found:
                port = int(found.group(1))
        assert port, "the server did not say where it listens"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/orbit/health", timeout=5) as r:
            assert json.loads(r.read())["ok"]
        client = ws.WebSocketClient.connect(f"ws://127.0.0.1:{port}/orbit/ws")
        client.send_json({"t": "hello", "v": 1, "lang": "id", "name": "Rafli", "job": "pilot",
                          "secret": "a1" * 32})
        assert client.recv_json(timeout=10)["name"] == "Rafli"
        client.close()
    finally:
        process.terminate()
        process.wait(10)
