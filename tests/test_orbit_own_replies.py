# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# A reply to your own command is always read aloud. The "Read aloud" filters of
# Orbit's Preferences (others' chat, arrivals, gifts, the station's news) once
# muted your own buys, sales, pay and finds too, when "work and money" was off.
# Here a real server answers a player's own commands (buying, selling, the farm,
# mining, giving, trading, the pawn shop, the casino, the daily bonus, an event's
# find, dropping and picking things up, sitting down...), and every reply goes
# through the client with every filter off, read by NVDA alone or mixed: each
# one must be spoken. What another player does to you stays filtered.

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
for folder in (SERVER_DIR, EXT_DIR):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import orbit_parse  # noqa: E402
import orbit_play  # noqa: E402
from tests.test_orbit import FakeServices  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, make_game, secret_of, world  # noqa: E402,F401

CLIENT = orbit_play.CLIENT_NAME
READ_OFF = {key: False for key in ("read_say", "read_whisper", "read_shout", "read_moves", "read_money",
                                   "read_announce", "read_events")}


def join_new(game, name, job="pilot"):
    conn = FakeConn("en")
    game.hello(conn, {"t": "hello", "v": 1, "lang": "en", "name": name, "job": job, "secret": secret_of(name),
                      "client": CLIENT})
    return conn


def typed(game, conn, words):
    parsed = orbit_parse.parse(words)
    assert parsed is not None and "local" not in parsed, (words, parsed)
    before = len(conn.sent)
    game.receive(conn, dict(parsed, t="cmd"))
    return [m for m in conn.sent[before:] if m.get("t") == "ev"]


def own_replies(make_game, clock):
    """[(what was typed, the event)]: every reply a player got to their own commands."""
    game = make_game()
    ani = join_new(game, "Ani", "trader")
    maya = join_new(game, "Maya", "engineer")
    char = ani.session.char
    char["xp"] = game.xp_for_level(12)
    char["credits"] = 50000
    maya.session.char["credits"] = 5000
    replies = []

    def at(room, *commands):
        for conn in (ani, maya):
            conn.session.char["location"] = room
            conn.session.char["stats"]["cooldowns"] = {}
        for words in commands:
            char["stats"]["cooldowns"] = {}
            clock.advance(5)
            got = typed(game, ani, words)
            assert got, words
            replies.extend((words, m) for m in got)

    at("cantina", "buy iced coffee", "buy 2 stuffed pancake", "drink iced coffee", "eat stuffed pancake",
       "give Maya 10 credits", "give Maya 1 stuffed pancake", "daily")
    at("spice_market", "buy 3 coffee", "sell 1 coffee")
    at("hydroponics", "buy 2 water spinach seeds", "plant water spinach", "water")
    clock.advance(3600)
    at("hydroponics", "harvest")
    at("belt", "mine", "mine")
    char["inventory"]["lava_lamp"] = 1
    at("pawn", "sell lava lamp")
    at("casino", "dice 50 high", "slots 50", "blackjack 50")
    if ani.session.blackjack:
        at("casino", "stand")
    at("casino", "lottery", "buy 2 tickets")
    # A trade: Ani offers, Maya accepts; then Maya offers and Ani accepts.
    at("cantina", "offer Maya 1 coffee for 20 credits")
    game.receive(maya, {"t": "cmd", "c": "accept"})
    maya.session.char["inventory"]["kerupuk"] = 2
    game.receive(maya, {"t": "cmd", "c": "text", "a": "offer Ani 1 prawn crackers for 5 credits"})
    at("cantina", "accept")
    # An event's find: a meteor shower, collected at the Observation Deck.
    game.receive(game_admin(game), {"t": "cmd", "c": "admin", "op": "event_start", "a": "meteor shower"})
    at("observation", "collect")
    # 1.6: the room and its things, the jukebox, the new food, the pond.
    char["inventory"]["coffee"] = char["inventory"].get("coffee", 0) + 2
    at("cantina", "sit", "stand", "drop 1 coffee", "get coffee", "put 1 coffee on the bar", "get coffee from the bar",
       "jukebox 3", "buy hot chocolate", "drink hot chocolate", "exits", "time", "roll")
    at("willow_nook", "fish")
    before = len(ani.sent)
    clock.advance(31)
    game.tick()                                          # the tug on the line
    replies.extend(("(a tug)", m) for m in ani.sent[before:] if m.get("t") == "ev")
    at("willow_nook", "reel")
    return game, ani, replies


def game_admin(game):
    return join_new(game, "Rafli")        # an admin in the tests' configuration


@pytest.mark.parametrize("reader", ["nvda", "mixed"])
def test_every_reply_to_your_own_command_is_read_with_every_filter_off(make_game, clock, reader):
    _game, ani, replies = own_replies(make_game, clock)
    kinds = {m["k"] for _words, m in replies}
    assert {"trade", "paid", "gave", "info"} <= kinds, kinds          # the kinds the filters used to catch
    services = FakeServices(reader=reader, **READ_OFF)
    client = orbit_play.OrbitClient(services)
    client.connect()
    conn = services.connections[-1]
    conn.welcome(name="Ani")
    checked = 0
    for words, message in replies:
        if message.get("actor") not in (None, "Ani"):
            continue                                  # someone else's doing (a resident's greeting)
        services.spoken.clear()
        services.timers = []
        conn.on_message(message)
        services.run_timers()
        said = " ".join(text for _voice, text in services.spoken)
        wanted = [str(message.get("brief") or message["text"]), message["text"]] + list(message.get("lines") or [])
        assert said and any(w in said for w in wanted), (reader, words, message, services.spoken)
        checked += 1
    assert checked >= 25


def test_what_others_do_to_you_can_still_be_left_unread(make_game, clock):
    game = make_game()
    ani = join_new(game, "Ani")
    maya = join_new(game, "Maya")
    maya.session.char["credits"] = 500
    game.receive(maya, {"t": "cmd", "c": "give", "to": "Ani", "n": 10, "item": "credits"})
    gift = [m for m in ani.sent if m.get("k") == "received"][-1]
    assert gift["actor"] == "Maya"
    services = FakeServices(reader="nvda", **READ_OFF)
    client = orbit_play.OrbitClient(services)
    client.connect()
    conn = services.connections[-1]
    conn.welcome(name="Ani")
    services.spoken.clear()
    conn.on_message(gift)
    assert services.spoken == [] and client.messages[-1] == gift["text"]       # shown, not read
    services.values["read_money"] = True
    conn.on_message(gift)
    assert services.spoken == [("reader", gift["text"])]
