# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The server's replies line by line (Orbit 1.5): a reply with several parts
# (a room, your things, who is online, the prices, the events, help...) goes
# to a client from 1.6 as its lines ("lines"), to show one by one in the
# Messages box, and to every client as one line ("text"), the way the older
# clients (1.0 to 1.5) always had it; short replies stay one line for all.

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_game  # noqa: E402
import orbit_lang  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, cmd, join, make_game, secret_of, walk, world  # noqa: E402,F401

NEW_CLIENT = "Hariku Orbit 1.6"
OLD_CLIENTS = (None, "Hariku Orbit 1.0", "Hariku Orbit 1.4", "Hariku Orbit 1.5")


def join_as(game, name, client, job="pilot"):
    conn = FakeConn("en")
    hello = {"t": "hello", "v": 1, "lang": "en", "name": name, "job": job, "secret": secret_of(name)}
    if client:
        hello["client"] = client
    game.hello(conn, hello)
    return conn


# ------------------------------------------------------------
# Lines, and one line
# ------------------------------------------------------------

@pytest.mark.parametrize("lines, said", [
    (["2 online:", "Sam the pilot, at the Dock", "Kim the trader, in the Cantina"],
     "2 online: Sam the pilot, at the Dock; Kim the trader, in the Cantina."),
    (["Cantina", "The bar hums.", "Exits: north, west."], "Cantina. The bar hums. Exits: north, west."),
    (["Prices here.", "Crops:", "tomato, buy 5", "chilli, buy 3", "Ore:", "iron, sell 9", "Prices move."],
     "Prices here. Crops: tomato, buy 5; chilli, buy 3. Ore: iron, sell 9. Prices move."),
    (["Rafli the pilot (disconnected)", "Sari the pilot"], "Rafli the pilot (disconnected); Sari the pilot."),
    (['Motto: "To the stars!"', "Next."], 'Motto: "To the stars!" Next.'),
    (["  one  ", "", "two"], "one; two."),
    ([], ""),
])
def test_lines_read_as_one_line_the_way_orbit_always_said_them(lines, said):
    assert orbit_lang.one_line(lines) == said


def test_the_lines_of_a_reply():
    assert orbit_lang.lines_of("Dock\n\n  The ring  hums.\nExits: north.\n") == ["Dock", "The ring hums.",
                                                                              "Exits: north."]
    assert orbit_lang.ends_sentence("Exits: north.") and orbit_lang.ends_sentence("Here you can:")
    assert not orbit_lang.ends_sentence("Sam (away)") and not orbit_lang.ends_sentence("Cantina")


# ------------------------------------------------------------
# What each client gets
# ------------------------------------------------------------

def _reply(game, conn, command):
    before = len(conn.sent)
    game.receive(conn, dict(command, t="cmd"))
    said = [m for m in conn.sent[before:] if m.get("t") == "ev" and m.get("sound") != "achievement"]
    return said[-1]


# (where to stand, the command, what its lines start with)
MULTI = [
    ("dock", {"c": "look"}, ["Dock", "The docking ring hums"]),
    ("dock", {"c": "inventory"}, ["You have 100 credits. Job: pilot.", "You carry:", "1 compass"]),
    ("dock", {"c": "who"}, ["5 online:", "Newcomer the pilot, at the Dock"]),
    ("dock", {"c": "status"}, ["Connected as "]),
    ("dock", {"c": "profile"}, ["Newcomer, "]),
    ("dock", {"c": "rank"}, ["Rank: "]),
    ("dock", {"c": "help"}, ["Help, by group.", "The station: help moving, help talking, help people, help social "
                                                "(the room: exits, sit, follow, gestures, drop and get)."]),
    ("dock", {"c": "help", "a": "money"}, ["Money: daily gives a bonus once a day, bigger with a streak."]),
    ("dock", {"c": "events"}, []),
    ("dock", {"c": "missions"}, ["Today's missions:"]),
    ("dock", {"c": "worlds"}, ["You're on the station. The worlds:"]),
    ("dock", {"c": "residents"}, ["The residents, who aren't players:"]),
    ("dock", {"c": "map"}, ["You're at the Dock, on the Lower Deck.", "Around you:"]),
    ("spice_market", {"c": "prices"}, ["Prices at the Spice Market, in credits for one."]),
    ("promenade_east", {"c": "look", "a": "north"}, None),                  # a short reply: one line
    ("cantina", {"c": "list"}, ["the Cantina bar, prices in credits:"]),
    ("shop", {"c": "list", "a": "devices"}, ["Star Supply, prices in credits:", "pocket mapper, "]),
    ("hydroponics", {"c": "farm"}, ["Your 2 plots:", "1, empty", "2, empty"]),
    ("casino", {"c": "casino"}, ["The Casino Corner.", "Dice: "]),
]


@pytest.mark.parametrize("room, command, first", MULTI)
def test_a_new_client_gets_the_lines_and_every_client_the_same_line(make_game, room, command, first):
    game = make_game()
    new = join_as(game, "Newcomer", NEW_CLIENT)
    olds = [join_as(game, f"Oldtimer{i}", client) for i, client in enumerate(OLD_CLIENTS)]
    for conn in [new] + olds:
        conn.session.char["location"] = room
    got = _reply(game, new, command)
    if first is None:
        assert "lines" not in got and "\n" not in got["text"]
        return
    assert got["lines"][:len(first)] == first or all(a.startswith(b) for a, b in zip(got["lines"], first)), \
        got["lines"]
    assert len(got["lines"]) > 1 and all(line and "\n" not in line for line in got["lines"])
    assert got["text"] == orbit_lang.one_line(got["lines"]) and "\n" not in got["text"]
    for conn in olds:
        old = _reply(game, conn, command)
        assert "lines" not in old and "\n" not in old["text"]
        if command["c"] not in ("look", "status", "profile", "rank", "inventory"):     # not about who asks
            assert old["text"] == got["text"]              # the same, only in one line


def test_look_goes_line_by_line_the_nova_realm_way(make_game):
    game = make_game()
    rafli = join_as(game, "Rafli", NEW_CLIENT)
    join_as(game, "Sari", None)
    walk(game, rafli, "cantina")
    look = _reply(game, rafli, {"c": "look"})
    lines = look["lines"]
    assert lines[0] == "Cantina"                                            # the room's name, alone
    assert lines[1].startswith("The Cantina") or len(lines[1]) > 40        # its description
    exits = next(i for i, line in enumerate(lines) if line.startswith("Exits: "))
    residents = [i for i, line in enumerate(lines) if line.startswith("Residents here: ")]
    things = next(i for i, line in enumerate(lines) if line.startswith("Things to look at: "))
    assert 1 < exits < things and all(exits < i < things for i in residents)
    assert look["text"].startswith("Cantina. ") and "Exits: " in look["text"]
    # Walking: the step first, then the room (the name, the exits; the description the first time).
    moved = _reply(game, rafli, {"c": "move", "d": "e"})
    assert moved["k"] == "moved" and moved["lines"][0].startswith("You walk east to ")
    assert moved["lines"][1] == "West Promenade" and moved["lines"][2].startswith("Exits: ")
    assert moved["text"].startswith("You walk east to the West Promenade. West Promenade. Exits: ")


def test_joining_and_reconnecting_come_in_lines_too(make_game):
    game = make_game()
    new = join_as(game, "Rafli", NEW_CLIENT)
    first = new.sent[1]
    assert first["k"] == "room" and first["lines"][0].startswith("Welcome to Orbit, Rafli!")
    assert "Dock" in first["lines"] and any(line.startswith("Exits: ") for line in first["lines"])
    game.dropped(new)
    again = join_as(game, "Rafli", NEW_CLIENT)
    assert again.sent[1]["lines"][:2] == ["Reconnected.", "Dock"]
    assert again.sent[1]["text"].startswith("Reconnected. Dock. ")
    old = join_as(game, "Sari", "Hariku Orbit 1.5")
    assert "lines" not in old.sent[1] and old.sent[1]["text"].startswith("Welcome to Orbit, Sari!")


def test_short_replies_and_what_people_say_stay_one_line(make_game):
    game = make_game()
    new = join_as(game, "Rafli", NEW_CLIENT)
    other = join_as(game, "Sari", NEW_CLIENT)
    for command in ({"c": "say", "a": "hello there"}, {"c": "emote", "e": "wave"}, {"c": "daily"},
                    {"c": "look", "a": "dragon"}, {"c": "text", "a": "flibber"}):
        got = _reply(game, new, command)
        assert "lines" not in got and "\n" not in got["text"], got
    heard = other.events("say")[-1]
    assert heard["text"] == "Rafli says: hello there" and "lines" not in heard


def test_the_lines_client_is_1_6():
    assert orbit_game.LINES_CLIENT == (1, 6)
