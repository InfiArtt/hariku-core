# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Players who haven't updated Orbit keep playing: every command that came
# after Orbit 1.0 must reach the server's right handler from what the 1.0
# client sends for it (its command reader is frozen in orbit_parse_1_0.py;
# anything it doesn't know goes as plain text), and from what the current
# client sends. The new event fields (dir, sound, voice...) are optional, so
# the old client only misses the new sounds.

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

import orbit_parse  # noqa: E402
from tests import orbit_parse_1_0  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, join, make_game, world  # noqa: E402,F401

# (what a player types, their language, the handler that must end up running)
PHRASEBOOK = [
    ("s", "id", "move"), ("u", "id", "move"), ("utara", "id", "move"), ("barat daya", "id", "move"),
    ("naik", "id", "move"), ("turun", "id", "move"), ("tl", "id", "move"),
    ("n", "en", "move"), ("north", "en", "move"), ("southwest", "en", "move"), ("up", "en", "move"),
    ("pergi ke utara", "id", "go"), ("go north", "en", "go"), ("ke timur", "id", "go"),
    ("pergi ke kantin", "id", "go"), ("go to the cantina", "en", "go"),
    ("arah ke kantin", "id", "way"), ("way to the cantina", "en", "way"),
    ("peta", "id", "map"), ("map", "en", "map"), ("di mana aku", "id", "where"), ("where am i", "en", "where"),
    ("kompas", "id", "compass"), ("compass", "en", "compass"), ("pindai", "id", "scan"), ("scan", "en", "scan"),
    ("lacak Sari", "id", "locate"), ("locate Sari", "en", "locate"), ("where is Sari", "en", "locate"),
    ("naik kancil", "id", "board"), ("ride the Kancil", "en", "board"),
    ("lihat utara", "id", "look"), ("look north", "en", "look"),
    ("harian", "id", "daily"), ("daily", "en", "daily"), ("profil", "id", "profile"),
    ("profile Sari", "en", "profile"), ("peringkat", "id", "rank"), ("rank", "en", "rank"),
    ("tanam tomat", "id", "plant"), ("plant tomato", "en", "plant"), ("panen", "id", "harvest"),
    ("harvest", "en", "harvest"), ("siram", "id", "water"), ("water", "en", "water"),
    ("lahan", "id", "farm"), ("plots", "en", "farm"), ("tambang", "id", "mine"), ("mine", "en", "mine"),
    ("kumpulkan", "id", "collect"), ("collect", "en", "collect"),
    ("daftar", "id", "list"), ("list", "en", "list"), ("daftar alat", "id", "list"),
    ("beli senter", "id", "buy"), ("buy headlamp", "en", "buy"), ("jual semua bijih", "id", "sell"),
    ("sell all ore", "en", "sell"),
    ("pakai senter", "id", "use"), ("use headlamp", "en", "use"), ("wear headlamp", "en", "use"),
    ("pasang suar", "id", "use"), ("place beacon", "en", "use"), ("minum es kopi", "id", "use"),
    ("eat martabak", "en", "use"), ("lepas senter", "id", "unequip"), ("remove headlamp", "en", "unequip"),
    ("periksa senter", "id", "look"), ("examine headlamp", "en", "look"),
    ("buka kapsul", "id", "open"), ("open capsule", "en", "open"),
    ("bunyikan lonceng", "id", "ring"), ("ring bell", "en", "ring"),
    ("nyalakan lentera", "id", "lantern"), ("light lantern", "en", "lantern"),
    ("baca prasasti", "id", "look"), ("read plaque", "en", "look"),
    ("undang Budi", "id", "invite"), ("invite Budi", "en", "invite"),
    ("kunjungi Budi", "id", "visit"), ("visit Budi", "en", "visit"),
    ("tambah teman Budi", "id", "friends"), ("add friend Budi", "en", "friends"), ("teman", "id", "friends"),
    ("suaraku 3", "id", "voice"), ("my voice 3", "en", "voice"),
    ("kode pindah", "id", "transfer"), ("move my character", "en", "transfer"),
    ("elus", "id", "pet"), ("pat", "en", "pet"), ("namai Kiki", "id", "pet"),
    ("ekonomi", "id", "admin"), ("economy", "en", "admin"), ("grant Budi 5", "en", "admin"),
    ("atur harga kopi 20", "id", "admin"), ("cabut akses Budi", "id", "admin"),
]


def _reader(name):
    return {"1.0": orbit_parse_1_0.parse, "now": orbit_parse.parse}[name]


@pytest.fixture
def spy(make_game):
    game = make_game()
    calls = []

    def wrap(name, fn):
        def run(self, session, message):
            calls.append(name)
            return fn(self, session, message)
        return run

    game.COMMANDS = {name: wrap(name, fn) for name, fn in type(game).COMMANDS.items()}
    return game, calls


@pytest.mark.parametrize("client", ["1.0", "now"])
@pytest.mark.parametrize("text, lang, handler", PHRASEBOOK)
def test_every_new_command_reaches_the_server(spy, client, text, lang, handler):
    game, calls = spy
    conn = join(game, "Tono", "engineer", lang)
    parsed = _reader(client)(text)
    assert parsed is not None and "local" not in parsed, parsed
    calls.clear()
    game.receive(conn, dict(parsed, t="cmd"))
    assert calls and calls[-1] == handler, (text, parsed, calls)
    assert conn.sent[-1]["t"] == "ev" and conn.sent[-1]["text"]
    assert "oops" not in conn.sent[-1]["text"] and conn.sent[-1]["text"] != \
        "The station's computer doesn't know that command."


def test_the_old_client_ignores_what_it_doesnt_know(make_game):
    """Everything the server sends is JSON with a kind and a text; the new
    fields are extra keys, which Orbit 1.0 simply doesn't read."""
    game = make_game()
    conn = join(game, "Tono", "engineer")
    for command in ({"c": "move", "d": "e"}, {"c": "look", "a": "north"}, {"c": "text", "a": "harian"},
                    {"c": "voice", "a": "2"}, {"c": "text", "a": "peta"}):
        game.receive(conn, dict(command, t="cmd"))
    for message in conn.sent[1:]:
        assert message["t"] == "ev" and isinstance(message["k"], str) and isinstance(message["text"], str)
        assert set(message) <= {"t", "k", "text", "brief", "actor", "room", "amb", "codes", "sound", "floor", "acoustics", "via",
                                "dir", "voice", "preview", "ask", "transfer_code", "expires"}
