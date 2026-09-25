# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for Orbit's way-finding (servers/orbit/orbit_nav.py): the compact
# route ("2 east, south, up, north, then 2 west"), in both languages, and
# routes past locked doors, through the dark and down one-way exits.

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_nav  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, cmd, join, make_game, walk, world  # noqa: E402,F401


def give(game, name, *things):
    char = game.sessions[name].char
    for tid in things:
        char["inventory"][tid] = char["inventory"].get(tid, 0) + 1


def path_of(*hows):
    return [(how, f"room{i}") for i, how in enumerate(hows)]


# ------------------------------------------------------------
# The compact route
# ------------------------------------------------------------

def test_runs_of_the_same_direction_are_grouped():
    assert orbit_nav.route_groups([]) == []
    assert orbit_nav.route_groups(path_of("e", "e", "s", "u", "n", "w", "w")) == [
        ("e", 2), ("s", 1), ("u", 1), ("n", 1), ("w", 2)]
    assert orbit_nav.route_groups(path_of("e", "w", "e")) == [("e", 1), ("w", 1), ("e", 1)]
    assert orbit_nav.route_groups(path_of("shuttle")) == [("shuttle", 1)]


@pytest.mark.parametrize("hows, en, idn", [
    (("e",), "east", "timur"),
    (("e", "e"), "2 east", "2 timur"),
    (("sw", "sw", "sw", "sw"), "4 southwest", "4 barat daya"),
    (("n", "w", "w"), "north, then 2 west", "utara lalu 2 barat"),
    (("e", "e", "s", "u", "n", "w", "w"), "2 east, south, up, north, then 2 west",
     "2 timur, selatan, naik, utara, lalu 2 barat"),
    (("u",), "up", "naik"),
    (("u", "u", "u"), "up 3 levels", "naik 3 tingkat"),
    (("d", "d"), "down 2 levels", "turun 2 tingkat"),
    (("s", "d", "d", "n"), "south, down 2 levels, then north", "selatan, turun 2 tingkat, lalu utara"),
    (("w", "shuttle"), "west, then ride the Kancil", "barat lalu naik kancil"),
    (("e",) * 12, "12 east", "12 timur"),                                     # long, but one run
    (("e", "e", "s", "u", "u", "u", "n", "n"), "2 east, south, up 3 levels, then 2 north (8 steps)",
     "2 timur, selatan, naik 3 tingkat, lalu 2 utara (8 langkah)"),
    (("e", "e", "e", "e", "n", "n", "n", "n"), "4 east, then 4 north", "4 timur lalu 4 utara"),
])
def test_a_route_is_said_compactly_in_both_languages(make_game, hows, en, idn):
    game = make_game()
    assert game.steps_text("en", path_of(*hows)) == en
    assert game.steps_text("id", path_of(*hows)) == idn


def test_the_way_is_compact_on_the_station(make_game):
    game = make_game()
    ani = join(game, "Ani")
    sari = join(game, "Sari", lang="id")
    assert cmd(game, ani, "way", a="cantina")["text"].startswith(
        "To the Cantina: 2 east, south, up, north, then 2 west.")
    assert cmd(game, sari, "way", a="kantin")["text"].startswith(
        "Ke Kantin: 2 timur, selatan, naik, utara, lalu 2 barat.")
    walk(game, ani, "promenade")
    assert cmd(game, ani, "way", a="belt")["text"].startswith(
        "To the Belt Platform: north, down, 2 west, then ride the Kancil.")     # the slide
    give(game, "ani", "holomapper")
    walk(game, ani, "dock")
    food = cmd(game, ani, "way", a="food court")["text"]
    assert food.startswith("To the Food Court: 2 east, south, up 3 levels, then 2 north (8 steps).")


def test_locate_says_the_way_compactly(make_game):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    give(game, "ani", "communicator")
    walk(game, budi, "cantina")
    assert cmd(game, ani, "locate", to="Budi")["text"] == (
        "Budi is in the Cantina, on the Main Deck. The way: 2 east, south, up, north, then 2 west.")
