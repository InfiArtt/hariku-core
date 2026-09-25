# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Orbit server (servers/orbit), without a network: the WebSocket
# codec and handshake, names and the word filter, rate limits, the texts in
# both languages, the station (world.json), the view from the Observation
# Deck, saving (SQLite; secrets only hashed), and the game itself through fake
# connections with a fake clock: joining and resuming, looking and moving,
# talking, jobs, missions, the market, admin commands and a restart.
# tests/test_orbit_e2e.py plays the same over real sockets on this computer.

import datetime
import json
import os
import random
import sqlite3
import struct
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_earth  # noqa: E402
import orbit_game  # noqa: E402
import orbit_lang  # noqa: E402
import orbit_safety  # noqa: E402
import orbit_store  # noqa: E402
import orbit_world  # noqa: E402
import orbit_ws as ws  # noqa: E402

UTC = datetime.timezone.utc


# ------------------------------------------------------------
# The WebSocket codec and handshake
# ------------------------------------------------------------

def test_the_extension_carries_the_same_websocket_module():
    # Line endings aside: the server's files are checked out with LF everywhere.
    with open(os.path.join(SERVER_DIR, "orbit_ws.py"), "rb") as a, \
            open(os.path.join(EXT_DIR, "orbit_ws.py"), "rb") as b:
        assert a.read().replace(b"\r\n", b"\n") == b.read().replace(b"\r\n", b"\n"), \
            "copy servers/orbit/orbit_ws.py to extensions/orbit/"


def test_accept_key_is_the_rfc_example():
    assert ws.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


@pytest.mark.parametrize("size", [0, 1, 125, 126, 65535, 65536, 70000])
def test_frames_round_trip_at_every_length_encoding(size):
    payload = ("é" * size)[:size] if size < 1000 else "x" * size
    frame = ws.encode_frame(ws.OP_TEXT, payload, mask=True)
    server = ws.FrameDecoder(expect_masked=True, max_message=100_000)
    assert server.feed(frame) == [(ws.OP_TEXT, payload)]
    client = ws.FrameDecoder(expect_masked=False, max_message=100_000)
    assert client.feed(ws.encode_frame(ws.OP_TEXT, payload)) == [(ws.OP_TEXT, payload)]


def test_masking_hides_the_payload_and_unmasks():
    frame = ws.encode_frame(ws.OP_TEXT, "halo semua", mask=True)
    assert b"halo semua" not in frame and frame[1] & 0x80
    assert ws.apply_mask(ws.apply_mask(b"abcdef", b"\x01\x02\x03\x04"), b"\x01\x02\x03\x04") == b"abcdef"


def test_fragments_are_joined_and_control_frames_may_come_between():
    decoder = ws.FrameDecoder(expect_masked=True)
    data = (ws.encode_frame(ws.OP_TEXT, "hal", mask=True, fin=False)
            + ws.encode_frame(ws.OP_PING, b"?", mask=True)
            + ws.encode_frame(ws.OP_CONT, "o ", mask=True, fin=False)
            + ws.encode_frame(ws.OP_CONT, "semua", mask=True))
    # One byte at a time, as a slow network might deliver it.
    out = []
    for i in range(len(data)):
        out.extend(decoder.feed(data[i:i + 1]))
    assert out == [(ws.OP_PING, b"?"), (ws.OP_TEXT, "halo semua")]


def _raw_frame(first, second, rest=b""):
    return bytes([first, second]) + rest


@pytest.mark.parametrize("data, code", [
    (ws.encode_frame(ws.OP_TEXT, "x"), ws.CLOSE_PROTOCOL),                        # unmasked from a client
    (_raw_frame(0xC1, 0x80, b"\0\0\0\0"), ws.CLOSE_PROTOCOL),                     # RSV1 set
    (_raw_frame(0x83, 0x80, b"\0\0\0\0"), ws.CLOSE_PROTOCOL),                     # opcode 3
    (_raw_frame(0x89, 0x80 | 126, b"\0\x80" + b"\0" * 4), ws.CLOSE_PROTOCOL),     # ping > 125
    (_raw_frame(0x09, 0x80, b"\0\0\0\0"), ws.CLOSE_PROTOCOL),                     # fragmented ping
    (ws.encode_frame(ws.OP_CONT, "x", mask=True), ws.CLOSE_PROTOCOL),              # nothing to continue
    (ws.encode_frame(ws.OP_TEXT, "a", mask=True, fin=False)
     + ws.encode_frame(ws.OP_TEXT, "b", mask=True), ws.CLOSE_PROTOCOL),            # new before the end
    (ws.encode_frame(ws.OP_TEXT, "x" * 5000, mask=True), ws.CLOSE_TOO_BIG),
    (ws.encode_frame(ws.OP_TEXT, b"\xff\xfe", mask=True), ws.CLOSE_BAD_DATA),
    (_raw_frame(0x81, 0x80 | 127, b"\x80" + b"\0" * 7 + b"\0" * 4), ws.CLOSE_PROTOCOL),
])
def test_the_decoder_refuses_what_breaks_the_rules(data, code):
    decoder = ws.FrameDecoder(expect_masked=True, max_message=4096)
    with pytest.raises(ws.ProtocolError) as caught:
        decoder.feed(data)
    assert caught.value.code == code


def test_fragments_together_may_not_exceed_the_limit():
    decoder = ws.FrameDecoder(expect_masked=True, max_message=100)
    decoder.feed(ws.encode_frame(ws.OP_TEXT, "x" * 60, mask=True, fin=False))
    with pytest.raises(ws.ProtocolError) as caught:
        decoder.feed(ws.encode_frame(ws.OP_CONT, "x" * 60, mask=True))
    assert caught.value.code == ws.CLOSE_TOO_BIG


def test_a_server_refuses_to_see_masked_frames_from_a_server():
    with pytest.raises(ws.ProtocolError):
        ws.FrameDecoder(expect_masked=False).feed(ws.encode_frame(ws.OP_TEXT, "x", mask=True))


def test_close_frames():
    assert ws.parse_close(ws.close_payload(1000, "bye")) == (1000, "bye")
    assert ws.parse_close(b"") == (ws.CLOSE_NO_STATUS, "")
    assert ws.parse_close(ws.close_payload(4003, "banned")) == (4003, "banned")
    long_reason = ws.close_payload(1000, "é" * 100)
    assert len(long_reason) <= 125 and ws.parse_close(long_reason)[1]      # cut on a character
    for bad in (b"\x03", struct.pack("!H", 999), struct.pack("!H", 1005), struct.pack("!H", 2999)):
        with pytest.raises(ws.ProtocolError):
            ws.parse_close(bad)
    with pytest.raises(ValueError):
        ws.encode_frame(ws.OP_CLOSE, b"x" * 200)


def _request(**changes):
    headers = {"host": "infiartt.com", "upgrade": "websocket", "connection": "keep-alive, Upgrade",
               "sec-websocket-key": "dGhlIHNhbXBsZSBub25jZQ==", "sec-websocket-version": "13"}
    headers.update(changes)
    return {k: v for k, v in headers.items() if v is not None}


def test_the_opening_handshake_both_ways():
    key = ws.make_key()
    raw = ws.client_request("infiartt.com", 443, "/orbit/ws", key, secure=True,
                            headers={"User-Agent": "test"})
    head, rest = ws.split_head(raw)
    start, headers = ws.parse_head(head)
    assert rest == b"" and headers["host"] == "infiartt.com"
    assert ws.check_request(start, headers) == ("/orbit/ws", key)
    head, _rest = ws.split_head(ws.server_response(key))
    start, answer = ws.parse_head(head)
    ws.check_response(start, answer, key)
    with pytest.raises(ws.HandshakeError):
        ws.check_response(start, answer, ws.make_key())
    assert b"Host: example.org:8080" in ws.client_request("example.org", 8080, "/", key)


@pytest.mark.parametrize("start, changes, status", [
    ("GET /orbit/ws HTTP/1.1", {"sec-websocket-version": "8"}, 426),
    ("GET /orbit/ws HTTP/1.1", {"upgrade": None}, 426),
    ("GET /orbit/ws HTTP/1.1", {"connection": "keep-alive"}, 400),
    ("GET /orbit/ws HTTP/1.1", {"sec-websocket-key": "short"}, 400),
    ("POST /orbit/ws HTTP/1.1", {}, 405),
    ("GET /orbit/ws HTTP/1.0", {}, 505),
])
def test_bad_requests_are_refused_with_their_status(start, changes, status):
    with pytest.raises(ws.HandshakeError) as caught:
        ws.check_request(start, _request(**changes))
    assert caught.value.status == status


def test_heads_have_a_size_limit():
    assert ws.split_head(b"GET / HTTP/1.1\r\n") is None
    with pytest.raises(ws.HandshakeError) as caught:
        ws.split_head(b"x" * (ws.MAX_HEAD + 10))
    assert caught.value.status == 431
    assert ws.http_response(426).startswith(b"HTTP/1.1 426 Upgrade Required")
    assert b"Sec-WebSocket-Version: 13" in ws.http_response(426)


def test_addresses():
    assert ws.parse_url("wss://infiartt.com/orbit/ws") == (True, "infiartt.com", 443, "/orbit/ws")
    assert ws.parse_url("ws://127.0.0.1:7340/orbit/ws?x=1") == (False, "127.0.0.1", 7340,
                                                                "/orbit/ws?x=1")
    for bad in ("https://infiartt.com/orbit/ws", "infiartt.com", "wss://:80/", "wss://h:99999/"):
        with pytest.raises(ValueError):
            ws.parse_url(bad)
    assert ws.is_local("localhost") and ws.is_local("[::1]") and not ws.is_local("infiartt.com")


def test_the_client_never_sends_unencrypted_to_another_computer(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection",
                        lambda *a, **k: pytest.fail("no connection should be made"))
    with pytest.raises(ws.WebSocketError):
        ws.WebSocketClient.connect("ws://infiartt.com/orbit/ws")


# ------------------------------------------------------------
# Names, the word filter, tidy text, rate limits
# ------------------------------------------------------------

def _filter():
    return orbit_safety.WordFilter(orbit_safety.load_words(os.path.join(SERVER_DIR, "words.json")))


@pytest.mark.parametrize("name, result", [
    ("rafli", ("Rafli", None)), ("InfiArtt", ("InfiArtt", None)), ("Sari99", ("Sari99", None)),
    ("Al", (None, "length")), ("A" * 21, (None, "length")), ("9lives", (None, "characters")),
    ("Sari Dewi", (None, "characters")), ("Budi!", (None, "characters")),
    ("anjing", (None, "filtered")), ("ANJ1NG", (None, "filtered")), ("xxfuckxx", (None, "filtered")),
    ("Admin", (None, "reserved")), ("kantin", (None, "reserved")),
])
def test_names(name, result):
    assert orbit_safety.check_name(name, _filter(), {"admin", "kantin"}) == result


def test_the_filter_masks_whole_words_and_look_alikes():
    f = _filter()
    assert f.clean("kamu anjing ya") == "kamu ****** ya"
    assert f.clean("dasar 4nj1ng!") == "dasar ******!"
    assert f.clean("oh fuuuuck") == "oh " + "*" * len("fuuuuck")
    assert f.clean("Scunthorpe and Anjingan-free") == "Scunthorpe and Anjingan-free"
    assert not f.contains("selamat pagi semua") and f.contains("BANGSAT")


def test_tidy_text():
    assert orbit_safety.tidy("  halo \n\t semua‮!  ", 100) == "halo semua !"
    assert orbit_safety.tidy("x" * 50, 10) == "x" * 10


def test_token_bucket():
    now = [0.0]
    bucket = orbit_safety.TokenBucket(rate=1.0, burst=3, clock=lambda: now[0])
    assert [bucket.take() for _ in range(4)] == [True, True, True, False]
    assert bucket.wait_seconds() == pytest.approx(1.0)
    now[0] = 1.5
    assert bucket.take() and not bucket.take()


# ------------------------------------------------------------
# Texts and the station
# ------------------------------------------------------------

def test_both_languages_say_everything_with_the_same_placeholders():
    with open(os.path.join(SERVER_DIR, "texts.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert set(data["en"]) == set(data["id"])
    for key in data["en"]:
        assert orbit_lang.placeholders(data["en"][key]) == orbit_lang.placeholders(data["id"][key]), key


def test_no_line_uses_a_name_the_game_needs_itself():
    # Game._send(session, kind, key, text, brief, extra, **values): a value
    # named like one of those would be taken for it.
    with open(os.path.join(SERVER_DIR, "texts.json"), encoding="utf-8") as f:
        data = json.load(f)
    clashes = {"session", "kind", "key", "text", "brief", "extra", "lang", "sound"}
    for key, line in data["en"].items():
        assert not orbit_lang.placeholders(line) & clashes, key


def test_values_in_several_languages_and_lists():
    texts = orbit_lang.Texts()
    place = {"en": "the Cantina", "id": "Kantin"}
    assert texts.render("id", "leave_to", actor="Sari", place=place) == "Sari pergi ke Kantin."
    assert texts.render("en", "leave_to", actor="Sari", place=place) == "Sari heads to the Cantina."
    assert texts.join("en", ["a", "b", "c"]) == "a, b and c"
    assert texts.join("id", ["a", "b", "c"]) == "a, b, dan c"
    assert texts.render("fr-FR", "say_what") == "Say what?"         # anything else is English
    assert orbit_lang.language("id-ID") == "id"


@pytest.fixture(scope="module")
def world():
    return orbit_world.World.load()


def test_the_station_is_complete_and_connected(world):
    places = {lid for lid, loc in world.locations.items() if not loc.get("hidden")}
    assert len(places) >= 10
    assert world.reachable() == places
    for lid in places:
        loc = world.locations[lid]
        assert loc["objects"], lid
        for lang in ("en", "id"):
            assert loc["desc"][lang] and loc["name"][lang] and loc["in"][lang]
    assert world.locations["cabin"]["private"] and world.locations["observation"]["earth_view"]
    assert {world.locations[l]["ambience"] for l in places} == set(orbit_world.AMBIENCES)
    assert set(world.jobs) == {"pilot", "engineer", "trader", "scientist", "security"}


@pytest.mark.parametrize("text, place", [
    ("kantin", "cantina"), ("the Cantina", "cantina"), ("CANTINA!", "cantina"),
    ("dek observasi", "observation"), ("obs deck", "observation"), ("ruang mesin", "engineering"),
    ("engine room", "engineering"), ("kabinku", "cabin"), ("my cabin", "cabin"),
    ("gudang", "cargo"), ("kantim", "cantina"), ("Klinik", "medbay"), ("anjungan", "bridge"),
    ("atlantis", None), ("", None), ("shuttle", None),
])
def test_places_by_their_names_in_either_language(world, text, place):
    assert world.find_location(text) == place


def test_routes_and_goods(world):
    no_keys = lambda room, ex: ex["lock"] is None           # noqa: E731
    assert world.route("dock", "promenade", no_keys) == [
        ("e", "cargo"), ("e", "service"), ("s", "lift_lower"), ("u", "lift_main"), ("n", "promenade")]
    # With a crew keycard, the maintenance tunnels are a shortcut.
    assert [room for _d, room in world.route("dock", "cantina")] == [
        "cargo", "service", "maint_1", "cabins_hall", "promenade_west", "cantina"]
    assert world.route("cargo", "cargo") == []
    assert world.route("promenade", "belt")[-1] == ("shuttle", "belt")
    assert world.find_good("kopi") == "coffee" and world.find_good("sacks of coffee") == "coffee"
    assert world.find_item("peti") == "crate" and world.find_item("crates") == "crate"
    assert world.count_of(world.goods, "coffee", 2) == {"en": "2 sacks of coffee", "id": "2 karung kopi"}


def test_a_broken_world_is_refused(world):
    for change in (lambda d: d["locations"]["dock"]["exits"].update(n="nowhere"),
                   lambda d: d["locations"]["dock"]["exits"].update(n="cantina"),        # no way back
                   lambda d: d["locations"]["dock"]["exits"].update(up="cargo"),          # no such direction
                   lambda d: d["locations"]["dock"].update(area="moon")):
        data = json.loads(json.dumps(world.data))
        change(data)
        with pytest.raises(orbit_world.WorldError):
            orbit_world.World(data, world.economy)


# ------------------------------------------------------------
# The view from the Observation Deck
# ------------------------------------------------------------

def test_the_sun_is_where_it_should_be():
    lat, lon = orbit_earth.sun_position(datetime.datetime(2026, 3, 20, 12, 7, tzinfo=UTC))
    assert abs(lat) < 1.5 and abs(lon) < 3
    lat, _lon = orbit_earth.sun_position(datetime.datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
    assert 23.0 < lat < 23.5
    _lat, lon = orbit_earth.sun_position(datetime.datetime(2026, 9, 25, 5, 0, tzinfo=UTC))
    assert 101 < lon < 105          # 12:00 WIB, and the sun is a little early in September


def test_day_and_night_over_java():
    java = (-6.8, 110.0)
    evening = datetime.datetime(2026, 9, 25, 12, 30, tzinfo=UTC)       # 19:30 in Batam
    assert orbit_earth.phase(*java, evening) == "night"
    assert orbit_earth.phase(*java, datetime.datetime(2026, 9, 25, 4, 0, tzinfo=UTC)) == "day"
    assert orbit_earth.phase(*java, datetime.datetime(2026, 9, 24, 22, 30, tzinfo=UTC)) == "dawn"
    assert orbit_earth.phase(*java, datetime.datetime(2026, 9, 25, 10, 30, tzinfo=UTC)) == "dusk"
    assert orbit_earth.phase(*java, datetime.datetime(2026, 9, 25, 11, 0, tzinfo=UTC)) == "night"


def test_the_station_goes_round():
    a = orbit_earth.station_point(datetime.datetime(2026, 9, 25, 12, 0, tzinfo=UTC))
    b = orbit_earth.station_point(datetime.datetime(2026, 9, 25, 12, 10, tzinfo=UTC))
    assert a != b and all(abs(p[0]) <= orbit_earth.INCLINATION + 0.01 for p in (a, b))
    assert 3000 < orbit_earth.distance_km(a, b) < 6000        # about 28,000 km/h


def test_the_view_names_indonesia_at_night(world):
    texts = orbit_lang.Texts()
    when = datetime.datetime(2026, 9, 25, 12, 30, tzinfo=UTC)
    en = orbit_earth.describe(world.regions, when, lambda key, **p: texts.render("en", key, **p))
    idn = orbit_earth.describe(world.regions, when, lambda key, **p: texts.render("id", key, **p))
    assert "Indonesia is at night: Java's lights glitter" in en
    assert "Di Indonesia sedang malam: lampu-lampu Jawa berkilau" in idn
    assert "The sun stands high over" in en
    noon = datetime.datetime(2026, 9, 25, 5, 0, tzinfo=UTC)
    en = orbit_earth.describe(world.regions, noon, lambda key, **p: texts.render("en", key, **p))
    assert "Indonesia" in en and "at night" not in en.split("Indonesia")[1][:20]


# ------------------------------------------------------------
# Saving
# ------------------------------------------------------------

def test_secrets_are_only_ever_stored_hashed(tmp_path):
    path = str(tmp_path / "orbit.db")
    store = orbit_store.Store(path, iterations=1000, durable=False)
    secret = "ab" * 32
    digest = store.hash_secret(secret)
    char = store.create("Rafli", "rafli", digest, "pilot", 100, "dock")
    assert store.by_secret_hash(store.hash_secret(secret))["id"] == char["id"]
    assert store.hash_secret("short") is None and store.hash_secret("x" * 40 + "!") is None
    store.close()
    with open(path, "rb") as f:
        assert secret.encode() not in f.read()
    rows = sqlite3.connect(path).execute("SELECT * FROM characters").fetchall()
    assert not any(secret in str(value) for row in rows for value in row)
    other = orbit_store.Store(str(tmp_path / "other.db"), iterations=1000, durable=False)
    assert other.hash_secret(secret) != digest          # each server has its own salt


def test_characters_and_bans_are_kept(tmp_path):
    path = str(tmp_path / "orbit.db")
    store = orbit_store.Store(path, iterations=1000, durable=False)
    char = store.create("Sari", "sari", store.hash_secret("c" * 64), "engineer", 100, "dock")
    char["credits"] = 250
    char["inventory"] = {"coffee": 2}
    char["stats"]["repairs"] = 3
    store.save(char)
    ip = store.ip_hash("203.0.113.9")
    assert ip and "203.0.113.9" not in ip
    store.ban_ip(ip, 60)
    store.close()
    again = orbit_store.Store(path, iterations=1000, durable=False)
    loaded = again.by_name("sari")
    assert (loaded["credits"], loaded["inventory"], loaded["stats"]["repairs"]) == (250, {"coffee": 2}, 3)
    assert again.ip_banned(ip) and not again.ip_banned(again.ip_hash("198.51.100.1"))


# ------------------------------------------------------------
# The game, through fake connections
# ------------------------------------------------------------

class StrictTexts(orbit_lang.Texts):
    """Fails the test when the game asks for a line that doesn't exist."""

    def raw(self, lang, key):
        assert key in self.data["en"], f"no text for {key!r}"
        return super().raw(lang, key)


class FakeConn:
    _next_ip = [0]

    def __init__(self, lang="en", ip_hash=None):
        self.lang = lang
        FakeConn._next_ip[0] += 1
        self.ip_hash = ip_hash or f"ip{FakeConn._next_ip[0]}"
        self.session = None
        self.sent = []
        self.closed = None

    def send(self, message):
        assert self.closed is None, "sent after closing"
        json.dumps(message)                 # everything sent must be JSON
        self.sent.append(message)

    def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    def events(self, kind=None):
        return [m for m in self.sent if m.get("t") == "ev" and (kind is None or m["k"] == kind)]

    def texts(self, kind=None):
        return [m["text"] for m in self.events(kind)]

    def last(self):
        return self.sent[-1]

    def clear(self):
        self.sent.clear()


class Clock:
    def __init__(self, start=datetime.datetime(2026, 9, 25, 12, 30, tzinfo=UTC).timestamp()):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(orbit_safety.time, "monotonic", c)     # the chat limits
    return c


@pytest.fixture
def make_game(tmp_path, world, clock):
    stores = []

    def make(path=None, **config):
        # In memory unless the test restarts the server from a file.
        store = orbit_store.Store(path or ":memory:", clock=clock, iterations=1000, durable=False)
        stores.append(store)
        settings = {"admins": ["Rafli"]}
        settings.update(config)
        game = orbit_game.Game(world, store, StrictTexts(), settings, _filter(), clock=clock,
                               rng=random.Random(7))
        return game

    yield make
    for store in stores:
        try:
            store.close()
        except Exception:
            pass


def secret_of(name):
    return (name.lower() * 64)[:64]


def join(game, name, job="pilot", lang="en", secret=None, ip_hash=None):
    conn = FakeConn(lang, ip_hash)
    game.hello(conn, {"t": "hello", "v": 1, "lang": lang, "name": name, "job": job,
                      "secret": secret or secret_of(name)})
    return conn


def cmd(game, conn, c, **fields):
    game.receive(conn, dict(t="cmd", c=c, **fields))
    return conn.sent[-1] if conn.sent else None


def walk(game, conn, dest):
    """Walk a player to `dest` by compass, the way they would type it; the last event."""
    path = game.route_for(conn.session.char, dest)
    assert path is not None, f"no way to {dest}"
    last = None
    for how, _room in path:
        assert how != "shuttle", "a walk, not a ride"
        before = len(conn.sent)
        cmd(game, conn, "move", d=how)
        moved = [m for m in conn.sent[before:] if m.get("k") == "moved"]
        assert moved, conn.sent[before:]
        last = moved[-1]
    return last


def test_joining_welcomes_you_and_tells_the_room(make_game):
    game = make_game()
    rafli = join(game, "rafli", "pilot", "id")
    welcome = rafli.sent[0]
    assert welcome["t"] == "welcome" and welcome["name"] == "Rafli" and welcome["new"]
    assert welcome["room"] == "dock" and welcome["amb"] == "vent" and welcome["credits"] == 100
    first = rafli.sent[1]
    assert first["k"] == "room" and first["text"].startswith("Selamat datang di Orbit, Rafli!")
    assert "Dermaga." in first["text"] and "Pilot: ketik kerja" in first["text"]
    assert "Jalan keluar: timur, selatan, naik kancil." in first["text"]
    sari = join(game, "Sari", "engineer", "en")
    assert rafli.last()["k"] == "arrive" and rafli.last()["actor"] == "Sari"
    assert rafli.last()["text"] == "Sari baru pertama kali masuk ke stasiun. Sapa, yuk!"
    assert "Here: Rafli the pilot." in sari.sent[1]["text"]
    assert game.sessions["rafli"].char["inventory"] == {"compass": 1}        # everyone starts with one


def test_a_known_secret_resumes_the_character_quietly(make_game, clock):
    game = make_game()
    rafli = join(game, "Rafli", "pilot", "id")
    sari = join(game, "Sari", "engineer")
    game.dropped(rafli)
    sari.clear()
    again = join(game, "SomeoneElse", "trader", "id", secret=secret_of("Rafli"))
    welcome = again.sent[0]
    assert welcome["name"] == "Rafli" and welcome["job"] == "pilot" and welcome["resumed"]
    assert again.sent[1]["text"].startswith("Tersambung lagi.")
    assert sari.sent == []                    # no leave, no arrive: it was only a moment
    # A second connection with the same secret replaces the first.
    third = join(game, "Rafli", secret=secret_of("Rafli"))
    assert again.closed == (orbit_game.CLOSE_REPLACED, "replaced") and third.sent[0]["resumed"]


def test_a_dropped_player_leaves_after_a_minute(make_game, clock):
    game = make_game()
    rafli = join(game, "Rafli")
    sari = join(game, "Sari")
    game.dropped(rafli)
    clock.advance(30)
    game.tick()
    assert sari.texts("leave") == []
    cmd(game, sari, "who")
    assert "Rafli the pilot, at the Dock (disconnected)" in sari.last()["text"]
    clock.advance(31)
    game.tick()
    assert sari.texts("leave") == ["Rafli has lost the connection and leaves for now."]
    assert game.online_count() == 1


@pytest.mark.parametrize("hello, code", [
    ({"v": 2}, "version"),
    ({"secret": "short"}, "bad_secret"),
    ({"name": "x"}, "name_length"),
    ({"name": "Admin"}, "name_reserved"),
    ({"name": "Kantin"}, "name_reserved"),
    ({"name": "Bangsat"}, "name_filtered"),
    ({"job": "wizard"}, "bad_job"),
])
def test_hellos_that_cant_join(make_game, hello, code):
    game = make_game()
    conn = FakeConn("id")
    message = {"t": "hello", "v": 1, "lang": "id", "name": "Budi", "job": "pilot", "secret": "e" * 64}
    message.update(hello)
    assert game.hello(conn, message) is False
    err = conn.sent[-1]
    assert err["t"] == "err" and err["code"] == code and err["fatal"] and conn.closed
    assert err["text"] and "_" not in err["text"].split()[0]


def test_names_are_unique_whatever_the_case(make_game):
    game = make_game()
    join(game, "Sari")
    other = join(game, "SARI", secret="f" * 64)
    assert other.sent[-1]["code"] == "name_taken" and "SARI" in other.sent[-1]["text"]


def test_looking_around_at_people_and_things(make_game):
    game = make_game()
    rafli = join(game, "Rafli")
    sari = join(game, "Sari", "engineer")
    cmd(game, sari, "describe", a="A tall engineer with a red scarf.")
    cmd(game, rafli, "look")
    text = rafli.last()["text"]
    assert text.startswith("Dock. The docking ring hums") and "Here: Sari the engineer." in text
    assert "Exits: east, south, ride the Kancil." in text and "Things to look at: shuttle" in text
    cmd(game, rafli, "look", a="sari")
    assert rafli.last()["text"] == "Sari, trainee engineer. A tall engineer with a red scarf."
    cmd(game, rafli, "look", a="the shuttle")
    assert rafli.last()["text"].startswith("The Merpati is a stubby cargo shuttle")
    cmd(game, rafli, "look", a="dragon")
    assert rafli.last() == {"t": "ev", "k": "error", "text": "You don't see dragon here."}
    assert cmd(game, rafli, "look", a="east")["text"] == "To the east: the Cargo Bay. Nobody is there."
    walk(game, rafli, "observation")
    cmd(game, rafli, "look", a="bumi")
    assert "Indonesia is at night: Java's lights" in rafli.last()["text"]


def test_walking_tells_both_rooms_which_way(make_game):
    game = make_game()
    rafli = join(game, "Rafli", lang="id")
    sari = join(game, "Sari", lang="en")
    budi = join(game, "Budi")
    cmd(game, budi, "move", d="e")                  # the Cargo Bay
    sari.clear()
    budi.clear()
    moved = cmd(game, rafli, "move", d="e")
    assert moved["k"] == "moved" and moved["room"] == "cargo" and moved["dir"] == "e"
    assert moved["text"].startswith("Kamu berjalan ke timur, ke Gudang Kargo. Gudang Kargo. Ruang besar")
    assert sari.events("leave") == [{"t": "ev", "k": "leave", "actor": "Rafli",
                                     "text": "Rafli heads east, to the Cargo Bay."}]
    assert budi.texts("arrive") == ["Rafli comes in from the west, from the Dock."]
    cmd(game, rafli, "move", d="w")
    again = cmd(game, rafli, "move", d="e")
    assert "Ruang besar" not in again["text"] and "Di sini ada Budi si pilot." in again["text"]
    # A wall says which ways there are; the lift goes up and down.
    bump = cmd(game, rafli, "move", d="n")
    assert bump == {"t": "ev", "k": "error", "sound": "bump",
                    "text": "Tidak bisa ke utara dari sini. Jalan keluar: timur, barat."}
    cmd(game, rafli, "move", d="e")
    cmd(game, rafli, "move", d="s")
    up = cmd(game, rafli, "move", d="u")
    assert up["text"].startswith("Kamu naik ke Lobi Lift Utama.") and up["dir"] == "u"
    assert cmd(game, rafli, "go", a="atlantis")["text"] == "Tidak ada tempat bernama atlantis di stasiun."


def test_no_teleporting_only_the_way(make_game):
    game = make_game()
    rafli = join(game, "Tono", lang="id")                  # not an admin: admins may teleport
    way = cmd(game, rafli, "go", a="kantin")
    assert way["k"] == "info" and way["text"] == (
        "Kamu berjalan di stasiun satu arah demi satu arah. Arah ke Kantin: "
        "timur, timur, selatan, naik, utara, barat, barat.")
    assert game.sessions["tono"].char["location"] == "dock"
    walk(game, rafli, "promenade_west")
    moved = cmd(game, rafli, "go", a="kantin")              # next door: that's a walk
    assert moved["k"] == "moved" and moved["room"] == "cantina"
    assert cmd(game, rafli, "go", a="kantin")["text"] == "Kamu sudah di sini."


def test_cabins_are_private(make_game):
    game = make_game()
    rafli = join(game, "Rafli")
    sari = join(game, "Sari")
    walk(game, rafli, "cabins_hall")
    walk(game, sari, "cabins_hall")
    rafli.clear()
    sari.clear()
    cmd(game, rafli, "move", d="s")
    assert sari.texts("leave") == ["Rafli goes into their cabin."]
    cmd(game, sari, "move", d="s")
    assert rafli.texts("arrive") == []
    cmd(game, sari, "say", a="halo?")
    assert sari.last()["brief"] == "Nobody else is here to hear it." and not rafli.events("say")
    cmd(game, sari, "who")
    assert "Rafli the pilot, in their cabin" in sari.last()["text"]


def test_talking_in_each_listeners_language(make_game):
    game = make_game()
    rafli = join(game, "Rafli", lang="id")
    sari = join(game, "Sari", lang="en")
    said = cmd(game, rafli, "say", a="halo Sari, apa kabar?")
    assert said == {"t": "ev", "k": "said", "text": "Kamu bilang: halo Sari, apa kabar?",
                    "brief": "Terkirim."}
    assert sari.events("say")[-1] == {"t": "ev", "k": "say", "actor": "Rafli",
                                      "text": "Rafli says: halo Sari, apa kabar?"}
    cmd(game, sari, "whisper", to="rafli", a="meet me on the deck")
    assert rafli.events("whisper")[-1]["text"] == "Sari berbisik padamu: meet me on the deck"
    assert sari.last()["brief"] == "Whispered to Rafli."
    cmd(game, sari, "whisper", to="Sari", a="hmm")
    assert sari.last()["k"] == "error"
    cmd(game, rafli, "shout", a="ada yang mau ke Bulan?")
    assert sari.texts("shout") == ["Rafli shouts across the station: ada yang mau ke Bulan?"]
    cmd(game, rafli, "shout", a="lagi!")
    assert rafli.last()["text"].startswith("Suaramu perlu istirahat")
    cmd(game, sari, "emote", e="wave", to="raf")
    assert rafli.texts("emote") == ["Sari melambai padamu."] and sari.last()["text"] == "You wave at Rafli."
    cmd(game, sari, "emote", e="moonwalk")
    assert sari.last()["k"] == "error"
    cmd(game, rafli, "say", a="dasar anjing")
    assert sari.texts("say")[-1] == "Rafli says: dasar ******"


def test_chat_has_a_rate_limit(make_game, clock):
    game = make_game()
    rafli = join(game, "Rafli")
    join(game, "Sari")
    kinds = [cmd(game, rafli, "say", a=f"hi {i}")["k"] for i in range(6)]
    assert kinds == ["said"] * 5 + ["error"]
    assert rafli.last()["text"] == "Easy, not so fast! Wait a moment."
    clock.advance(2)
    assert cmd(game, rafli, "say", a="ok now")["k"] == "said"


def test_admins_mute_kick_ban_and_announce(make_game, clock):
    game = make_game()
    rafli = join(game, "Rafli", lang="id")        # an admin (the config)
    sari = join(game, "Sari")
    budi = join(game, "Budi")
    cmd(game, sari, "admin", op="kick", to="Budi")
    assert sari.last()["text"] == "Only the station's admins can do that."
    cmd(game, rafli, "admin", op="mute", to="sari", n=5)
    assert rafli.last()["text"] == "Sari dibisukan selama 5 menit."
    assert sari.texts("system") == ["An admin has muted you for 5 minutes."]
    cmd(game, sari, "say", a="hello?")
    assert sari.last()["text"] == "You're muted for 5 minutes more."
    cmd(game, rafli, "admin", op="unmute", to="Sari")
    assert cmd(game, sari, "say", a="thanks")["k"] == "said"
    cmd(game, rafli, "admin", op="announce", a="Server restarts at 21:00")
    assert budi.events("announce")[-1]["text"] == "Announcement from the Bridge: Server restarts at 21:00"
    cmd(game, rafli, "admin", op="kick", to="Budi")
    assert budi.closed == (orbit_game.CLOSE_KICKED, "kicked_you") and "Budi" not in str(game.sessions)
    assert sari.texts("leave")[-1] == "Budi logs out."
    cmd(game, rafli, "admin", op="ban", to="Sari")
    assert sari.closed[0] == orbit_game.CLOSE_BANNED
    back = join(game, "Sari")
    assert back.sent[-1]["code"] == "banned"
    elsewhere = join(game, "Sari2", secret="9" * 64, ip_hash=sari.ip_hash)
    assert elsewhere.sent[-1]["code"] == "banned"          # the address is banned for a while
    cmd(game, rafli, "admin", op="unban", to="Sari")
    assert join(game, "Sari").sent[0]["t"] == "welcome"
    actions = [row["action"] for row in game.store.admin_log(20)]
    assert {"mute", "unmute", "announce", "kick", "ban", "unban"} <= set(actions)


def test_who_inventory_and_giving(make_game):
    game = make_game()
    rafli = join(game, "Rafli", lang="id")
    sari = join(game, "Sari")
    cmd(game, rafli, "who")
    assert rafli.last()["text"] == ("2 orang online: Rafli si pilot, di Dermaga; "
                                    "Sari si pilot, di Dermaga.")
    cmd(game, rafli, "give", to="Sari", n=30, item="kredit")
    assert rafli.last() == {"t": "ev", "k": "gave",
                            "text": "Kamu memberi Sari 30 kredit. Sisa kreditmu 70."}
    assert sari.events("received")[-1]["text"] == "Rafli gives you 30 credits. You now have 130."
    cmd(game, rafli, "give", to="Sari", n=500)
    assert rafli.last()["text"] == "Kreditmu cuma 70."
    cmd(game, rafli, "give", to="Budi", n=1)
    assert rafli.last()["text"] == "Budi tidak ada di sini."
    cmd(game, rafli, "give", to="Sari", n=1, item="kopi")
    assert rafli.last()["text"] == "Kamu tidak punya karung kopi."
    cmd(game, rafli, "give", to="Sari", n=1, item="kompas")
    assert rafli.last()["text"] == "kompas tidak bisa diberikan."
    # An older client reads "beri kredit Sari 5" as giving "kredit" a "sari".
    cmd(game, rafli, "give", to="kredit", n=5, item="sari")
    assert rafli.last()["text"] == "Kamu memberi Sari 5 kredit. Sisa kreditmu 65."
    cmd(game, sari, "inventory")
    assert sari.last()["text"] == "You have 135 credits. Job: pilot. You carry 1 compass."


def test_the_engineers_reactor(make_game, clock):
    game = make_game()
    sari = join(game, "Sari", "engineer")
    cmd(game, sari, "work")
    assert sari.last()["text"] == "You work in Engineering: go there first."
    walk(game, sari, "engineering")
    tones = cmd(game, sari, "work")
    codes = tones["codes"]
    assert tones["k"] == "tones" and len(codes) == 3 and all(1 <= c <= 4 for c in codes)
    assert ", ".join(map(str, codes)) in tones["text"]
    wrong = [5 - c for c in codes]
    failed = cmd(game, sari, "answer", a=" ".join(map(str, wrong)))
    assert failed["k"] == "failed" and "Try again in 30 seconds" in failed["text"]
    assert cmd(game, sari, "work")["text"].startswith("You've just worked. Take a break")
    clock.advance(31)
    codes = cmd(game, sari, "work")["codes"]
    paid = cmd(game, sari, "answer", a="".join(map(str, codes)))
    assert paid["k"] == "paid" and "You're paid 40 credits; you have 140." in paid["text"]
    assert game.sessions["sari"].char["xp"] == 10
    clock.advance(121)
    assert len(cmd(game, sari, "work")["codes"]) == 4        # a longer sequence next time
    clock.advance(60)
    game.tick()
    assert sari.last()["k"] == "failed" and sari.last()["text"].startswith("Too slow")
    assert cmd(game, sari, "answer", a="1234")["text"] == "There's nothing to answer right now."


def test_the_pilots_cargo_run(make_game, clock):
    game = make_game(flight_seconds=60)
    rafli = join(game, "Rafli", "pilot", "id")
    sari = join(game, "Sari")
    flight = cmd(game, rafli, "work")
    assert flight["k"] == "flight" and flight["room"] == "shuttle" and flight["sound"] == "launch"
    assert sari.texts("leave") == ["Rafli climbs into the Merpati, and the shuttle undocks for the Moon."]
    assert cmd(game, rafli, "go", a="kantin")["text"] == "Kamu sedang menerbangkan Merpati! Tunggu sampai mendarat."
    assert cmd(game, rafli, "move", d="e")["text"] == "Kamu sedang menerbangkan Merpati! Tunggu sampai mendarat."
    cmd(game, rafli, "whisper", to="Sari", a="otw bulan")
    assert sari.texts("whisper") == ["Rafli whispers to you: otw bulan"]
    clock.advance(31)
    game.tick()
    assert rafli.last()["text"].startswith("Sudah setengah jalan.")
    clock.advance(30)
    game.tick()
    paid = [m for m in rafli.events("paid")][-1]
    assert paid["room"] == "dock" and paid["sound"] == "landing"
    assert paid["text"].startswith("Mendarat di Pangkalan Bulan Tranquility.")
    assert game.sessions["rafli"].char["credits"] > 100 and game.sessions["rafli"].char["xp"] == 20
    assert sari.texts("arrive") == ["The Merpati docks with a clunk, and Rafli climbs out."]
    assert cmd(game, rafli, "work")["text"].startswith("Kamu baru saja kerja.")


def test_a_cargo_run_lands_even_while_you_are_away(make_game, clock):
    game = make_game(flight_seconds=60)
    rafli = join(game, "Rafli", "pilot", "en")
    cmd(game, rafli, "work")
    game.dropped(rafli)
    clock.advance(61)
    game.tick()                              # link-dead: paid and landed, nobody to tell
    clock.advance(100)
    game.tick()                              # gone
    assert "rafli" not in game.sessions
    back = join(game, "Rafli")
    assert back.sent[0]["room"] == "dock" and back.sent[0]["credits"] > 100


def test_trading_on_the_promenade(make_game, clock):
    game = make_game()
    tina = join(game, "Tina", "trader")
    rafli = join(game, "Rafli", "pilot")
    cmd(game, tina, "buy", item="kopi", n=2)
    assert tina.last()["text"] == "The market is on the Promenade."
    prices = cmd(game, tina, "prices")["text"]
    assert prices.startswith("Market prices in credits, for one each, at your trader's rates: Trade goods:")
    assert "; Crops: " in prices and "; Ore: " in prices and "; Salvage: " in prices
    ores = cmd(game, tina, "prices", a="bijih")["text"]
    assert "Ore: " in ores and "Crops" not in ores and "iron ore" in ores
    for conn in (tina, rafli):
        walk(game, conn, "promenade")
    price_before = game.market.prices["coffee"]
    total = game.market.quote("coffee", "trader", "buy", 2)
    bought = cmd(game, tina, "buy", item="kopi", n=2)
    assert bought["text"] == f"You buy 2 sacks of coffee for {total} credits. You have {100 - total} left."
    assert game.market.prices["coffee"] > price_before
    # No profit from buying and selling at once, even for a trader.
    sold = cmd(game, tina, "sell", item="coffee", n="all")
    assert sold["k"] == "trade" and game.sessions["tina"].char["credits"] < 100
    # Traders pay less than everyone else.
    assert game.market.unit_price("chips", "trader", "buy") < game.market.unit_price("chips", "pilot", "buy")
    assert cmd(game, rafli, "buy", item="meteorite", n=5)["text"].startswith("That costs")
    assert cmd(game, rafli, "sell", item="ice")["text"] == "You don't have any blocks of comet ice to sell."
    assert cmd(game, rafli, "buy", item="unicorns")["text"] == "The market doesn't sell unicorns."
    game.sessions["rafli"].char["credits"] = 10_000
    assert cmd(game, rafli, "buy", item="ice", n=20)["k"] == "trade"
    assert cmd(game, rafli, "buy", item="ice", n=1)["text"] == "Your bag holds at most 20 goods."


def test_prices_drift_within_bounds_and_are_kept(make_game, clock, tmp_path):
    path = str(tmp_path / "market.db")
    game = make_game(path)
    start = dict(game.market.prices)
    for _ in range(30):
        clock.advance(181)
        game.tick()
    assert game.market.prices != start
    for gid, good in game.world.goods.items():
        assert 0.4 * good["base"] <= game.market.prices[gid] <= 2.5 * good["base"]
    again = make_game(path)
    assert again.market.prices == pytest.approx(game.market.prices)


def test_the_trader_report(make_game):
    game = make_game()
    tina = join(game, "Tina", "trader", "id")
    game.market.prices["coffee"] = 12 * 0.7
    game.market.prices["chips"] = 60 * 1.4
    report = cmd(game, tina, "work")["text"]
    assert report == ("Laporan pasar. Bagus dibeli: karung kopi, 30 persen di bawah harga biasa. "
                      "Bagus dijual: chip memori, 40 persen di atas harga biasa.")
    budi = join(game, "Budi", "scientist")
    assert cmd(game, budi, "work")["text"] == "You work in the Science Lab: go there first."


def test_missions_from_the_board(make_game, clock):
    game = make_game()
    rafli = join(game, "Rafli", "pilot", "en")
    board = game.board()
    assert len(board) == 3 and len(set(board)) == 3 and game.board() == board
    text = cmd(game, rafli, "missions")["text"]
    assert text.startswith("Today's missions: 1: bring ") and text.endswith("Type accept and a number.")
    mid = board[0]
    mission = game.world.missions[mid]
    cmd(game, rafli, "accept", n=1)
    assert rafli.last()["k"] == "mission" and rafli.last()["text"].startswith("Mission accepted: bring")
    assert cmd(game, rafli, "accept", n=2)["text"].startswith("You're already on a mission")
    item_word = game.world.items[mission["item"]]["names"]["en"][0]
    if mission["from"] != "dock":
        assert cmd(game, rafli, "take", item=item_word)["text"].startswith("You'll find")
        walk(game, rafli, mission["from"])
    taken = cmd(game, rafli, "take", item=item_word)
    assert taken["k"] == "mission" and f"({mission['count']} of {mission['count']})" in taken["text"]
    assert cmd(game, rafli, "take", item=item_word)["text"].startswith("You have all you need")
    if mission["to"] != mission["from"]:
        assert cmd(game, rafli, "complete")["text"].startswith("Deliver it to")
    walk(game, rafli, mission["to"])
    done = cmd(game, rafli, "complete")
    assert done["k"] == "paid" and f"You're paid {mission['reward']} credits" in done["text"]
    assert game.sessions["rafli"].char["credits"] == 100 + mission["reward"]
    assert game.sessions["rafli"].char["xp"] == 25
    assert "(done)" in cmd(game, rafli, "missions")["text"]
    assert cmd(game, rafli, "accept", n=1)["text"] == "You've done that one today. Try another."
    cmd(game, rafli, "accept", n=2)
    assert cmd(game, rafli, "abandon")["text"].startswith("Mission dropped:")
    assert cmd(game, rafli, "complete")["text"].startswith("You're not on a mission.")
    assert cmd(game, rafli, "take", item="coffee")["text"].startswith("Goods like that are bought")
    clock.advance(86400)
    assert "(done)" not in cmd(game, rafli, "missions")["text"]       # a new day, a new board


def test_a_mission_can_give_a_thing(make_game, monkeypatch):
    game = make_game()
    monkeypatch.setattr(game, "board", lambda day=None: ["mail_comms", "medkit_gym", "crates_cantina"])
    rafli = join(game, "Rafli")
    assert "(plus beacon)" in cmd(game, rafli, "missions")["text"]
    cmd(game, rafli, "accept", n=1)
    cmd(game, rafli, "take", item="mailbag")
    walk(game, rafli, "comms")
    done = cmd(game, rafli, "complete")
    assert done["text"].endswith("You also get: beacon.")
    assert game.sessions["rafli"].char["inventory"]["beacon"] == 1


def test_a_plain_word_is_guessed(make_game):
    game = make_game()
    rafli = join(game, "Tono", lang="id")
    join(game, "Sari")
    assert cmd(game, rafli, "text", a="kantin")["text"].startswith("Kamu berjalan di stasiun satu arah")
    assert cmd(game, rafli, "text", a="Sari")["text"].startswith("Sari, pilot magang.")
    assert cmd(game, rafli, "text", a="t")["room"] == "cargo"            # "t" is timur
    assert cmd(game, rafli, "text", a="blah blah")["text"] == ('Aku tidak paham "blah blah". '
                                                               'Ketik bantuan untuk daftar perintah.')


def test_odd_messages(make_game):
    game = make_game()
    rafli = join(game, "Rafli")
    assert cmd(game, rafli, "fly_away")["text"] == "The station's computer doesn't know that command."
    count = len(rafli.sent)
    game.receive(rafli, "not a dict")
    game.receive(rafli, {"t": "chat"})
    game.receive(FakeConn(), {"t": "cmd", "c": "look"})      # never joined
    assert len(rafli.sent) == count
    assert cmd(game, rafli, "give", to="Rafli", n=1)["text"] == "Rafli isn't here."
    assert cmd(game, rafli, "say", a="   ")["text"] == "Say what?"
    assert cmd(game, rafli, "describe", a="")["text"].startswith("You haven't described yourself")
    assert cmd(game, rafli, "move", d="sideways")["text"].startswith("Go where?")


def test_everything_survives_a_restart(make_game, clock, tmp_path):
    path = str(tmp_path / "restart.db")
    game = make_game(path)
    rafli = join(game, "Rafli", "pilot", "id")
    walk(game, rafli, "cantina")
    cmd(game, rafli, "describe", a="Pilot dari Batam, suka kopi.")
    game.sessions["rafli"].char["credits"] = 321
    game._save(game.sessions["rafli"])
    game.shutdown()
    assert rafli.last()["k"] == "system" and "dimulai ulang" in rafli.last()["text"]
    game.store.close()
    again = make_game(path)
    back = join(again, "Rafli", lang="id")
    assert (back.sent[0]["credits"], back.sent[0]["room"], back.sent[0]["new"]) == (321, "cantina", False)
    assert back.sent[1]["text"].startswith("Selamat datang kembali, Rafli.")
    other = join(again, "Sari")
    walk(again, other, "cantina")
    cmd(again, other, "look", a="Rafli")
    assert other.last()["text"] == "Rafli, trainee pilot. Pilot dari Batam, suka kopi."


def test_logging_out_on_purpose_is_immediate(make_game, clock):
    game = make_game()
    rafli = join(game, "Rafli")
    sari = join(game, "Sari", lang="id")
    cmd(game, rafli, "move", d="e")
    sari.clear()
    game.receive(rafli, {"t": "cmd", "c": "bye"})
    assert "rafli" not in game.sessions and rafli.closed == (1000, "bye")
    game.dropped(rafli)                                   # the socket closing after it: nothing more
    assert sari.texts("leave") == []                       # Sari is at the Dock; Rafli left from the Cargo Bay
    back = join(game, "Rafli")
    assert back.sent[0]["room"] == "cargo" and not back.sent[0]["resumed"]
    cmd(game, sari, "move", d="e")
    game.receive(back, {"t": "cmd", "c": "bye"})
    assert sari.texts("leave")[-1] == "Rafli keluar dari Orbit."


def test_away_is_shown_until_the_next_command(make_game):
    game = make_game()
    rafli = join(game, "Rafli")
    sari = join(game, "Sari")
    game.receive(rafli, {"t": "cmd", "c": "away", "on": True})
    assert rafli.last()["k"] != "error"                   # nothing to say to the one who's away
    assert "Rafli the pilot, at the Dock (away)" in cmd(game, sari, "who")["text"]
    assert "Here: Rafli the pilot (away)." in cmd(game, sari, "look")["text"]
    cmd(game, rafli, "look")
    assert "(away)" not in cmd(game, sari, "who")["text"]


def test_the_status_line(make_game):
    game = make_game()
    rafli = join(game, "Rafli", lang="id")
    join(game, "Sari")
    assert cmd(game, rafli, "status")["text"] == "Tersambung sebagai Rafli, di Dermaga, di Dek Bawah. 2 orang online."
    assert cmd(game, rafli, "text", a="status orbit")["text"].startswith("Tersambung sebagai Rafli")
