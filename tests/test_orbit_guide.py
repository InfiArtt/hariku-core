# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for Orbit's way-finding (servers/orbit/orbit_nav.py): the compact
# route ("2 east, south, up, north, then 2 west"), in both languages; the
# guide that follows it step by step (the next step, a detour and the way
# again, arriving, stopping it, and logging out and travel ending it); and
# routes and the guide past locked doors, through the dark, down one-way
# exits and out into vacuum.

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_nav  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, cmd, join, make_game, walk, world  # noqa: E402,F401
from tests.test_orbit_worlds import with_ship  # noqa: E402


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
    assert ani.session.guide is None                     # a player moves: locate doesn't guide


# ------------------------------------------------------------
# The guide, step by step
# ------------------------------------------------------------

def step(game, conn, d):
    """Walk one step; the guide's line after it (None when it said nothing)."""
    before = len(conn.sent)
    cmd(game, conn, "move", d=d)
    after = conn.sent[before:]
    assert after and after[0]["k"] == "moved", after
    lines = [m for m in after[1:] if m.get("k") == "info"]
    return lines[0] if lines else None


def test_the_way_guides_you_step_by_step_to_arrival(make_game):
    game = make_game()
    ani = join(game, "Ani")
    way = cmd(game, ani, "way", a="cantina")
    assert way["k"] == "info" and way["text"] == ("To the Cantina: 2 east, south, up, north, then 2 west. "
                                                  "I'll guide you step by step; type stop guide to stop.")
    said = [step(game, ani, d)["text"] for d in ("e", "e", "s", "u", "n", "w")]
    assert said == ["Then east.", "Then south.", "Then up.", "Then north.", "Then 2 west.", "Then west."]
    arrived = step(game, ani, "w")
    assert arrived == {"t": "ev", "k": "info", "text": "You've arrived at the Cantina.", "sound": "gadget_arrived"}
    assert ani.session.guide is None
    assert step(game, ani, "e") is None                                # the guide has ended
    # The how-to comes once a session.
    assert cmd(game, ani, "way", a="dock")["text"] == "To the Dock: north, east, down, then 2 west."   # the slide


def test_the_guide_in_indonesian_from_the_old_clients_text(make_game):
    game = make_game()
    sari = join(game, "Sari", lang="id")
    game.receive(sari, {"t": "cmd", "c": "text", "a": "pandu ke kantin"})       # what 1.0 to 1.3 send
    assert sari.last()["text"] == ("Ke Kantin: 2 timur, selatan, naik, utara, lalu 2 barat. "
                                   "Aku akan memandumu langkah demi langkah; ketik berhenti pandu untuk berhenti.")
    assert [step(game, sari, d)["text"] for d in ("e", "e", "s", "u", "n", "w")] == \
        ["Lalu timur.", "Lalu selatan.", "Lalu naik.", "Lalu utara.", "Lalu 2 barat.", "Lalu barat."]
    assert step(game, sari, "w")["text"] == "Sampai di Kantin."


def test_a_detour_finds_the_way_again(make_game):
    game = make_game()
    ani = join(game, "Ani")
    cmd(game, ani, "way", a="cantina")
    assert step(game, ani, "e")["text"] == "Then east."
    assert step(game, ani, "n")["text"] == "Off the route. From here: south."          # into the Ice Depot
    assert ani.session.guide["path"][0] == ("s", "cargo")
    assert step(game, ani, "s")["text"] == "Then east."                                # back on it
    assert step(game, ani, "w")["text"] == "Off the route. From here: 2 east."         # back at the Dock
    for d in ("e", "e", "s", "u", "n", "w"):
        step(game, ani, d)
    assert step(game, ani, "w")["text"] == "You've arrived at the Cantina."


def test_asking_the_guide_and_stopping_it(make_game):
    game = make_game()
    ani = join(game, "Ani")
    sari = join(game, "Sari", lang="id")
    assert cmd(game, ani, "guide", op="stop")["text"] == "You're not being guided anywhere."
    assert cmd(game, ani, "guide")["text"] == (
        "Guide you where? Type guide me to and a place, like guide me to the cantina.")
    assert cmd(game, ani, "guide", a="the cantina")["text"].startswith("To the Cantina: 2 east, south,")
    step(game, ani, "e")
    assert cmd(game, ani, "guide")["text"] == "Guiding you to the Cantina: east, south, up, north, then 2 west."
    assert cmd(game, ani, "guide", op="stop")["text"] == "Stopped guiding you to the Cantina."
    assert step(game, ani, "e") is None
    walk(game, sari, "cargo")
    game.receive(sari, {"t": "cmd", "c": "text", "a": "pandu aku ke dermaga"})
    assert sari.last()["text"].startswith("Ke Dermaga: barat. Aku akan memandumu")
    game.receive(sari, {"t": "cmd", "c": "text", "a": "status pandu"})
    assert sari.last()["text"] == "Memandu ke Dermaga: barat."
    game.receive(sari, {"t": "cmd", "c": "text", "a": "berhenti pandu"})
    assert sari.last()["text"] == "Berhenti memandu ke Dermaga."
    game.receive(sari, {"t": "cmd", "c": "text", "a": "stop guide"})
    assert sari.last()["text"] == "Kamu sedang tidak dipandu ke mana pun."


def test_a_new_way_replaces_the_old_and_go_to_guides_too(make_game):
    game = make_game()
    ani = join(game, "Ani")
    cmd(game, ani, "way", a="cantina")
    assert cmd(game, ani, "go", a="the workshop")["text"].startswith(
        "You walk the station one direction at a time. To the Workshop: 4 east.")
    assert ani.session.guide["dest"] == "workshop"
    assert [step(game, ani, "e")["text"] for _ in range(3)] == ["Then 3 east.", "Then 2 east.", "Then east."]
    assert step(game, ani, "e")["text"] == "You've arrived at the Workshop."


def test_logging_out_ends_the_guide_a_dropped_connection_does_not(make_game):
    game = make_game()
    ani = join(game, "Ani")
    cmd(game, ani, "way", a="cantina")
    game.dropped(ani)                                     # the connection drops: back within the minute
    again = join(game, "Ani")
    assert again.session.guide is not None and step(game, again, "e")["text"] == "Then east."
    cmd(game, again, "bye")                               # logging out ends it
    back = join(game, "Ani")
    assert back.session.guide is None and step(game, back, "e") is None


def test_the_gate_and_the_ferry_end_the_guide(make_game):
    game = make_game()
    ani = join(game, "Ani")
    ani.session.char["credits"] = 5000
    walk(game, ani, "gate_hall")
    cmd(game, ani, "way", a="dock")
    cmd(game, ani, "gate", a="karmina")
    assert game.world.world_of(ani.session.char["location"]) == "karmina" and ani.session.guide is None
    budi = join(game, "Budi")
    budi.session.char["credits"] = 5000
    cmd(game, budi, "way", a="cantina")
    cmd(game, budi, "ferry", a="moon")
    assert budi.session.char["location"] == "ferry" and budi.session.guide is None


def test_a_ship_ends_the_guide(make_game):
    game = make_game()
    ani = join(game, "Ani")
    with_ship(game, ani)
    walk(game, ani, "hangar")
    cmd(game, ani, "way", a="cantina")
    cmd(game, ani, "embark")
    assert ani.session.char["location"] == "ship" and ani.session.guide is None
    cmd(game, ani, "disembark")
    assert step(game, ani, "e") is None


def test_the_guide_arrives_in_a_room_of_ones_own(make_game, clock):
    from tests.test_orbit_crews import found
    game = make_game()
    ani = found(game, clock)                             # a crew's captain: the Crew Hangar is theirs
    give(game, "ani", "holomapper")
    assert cmd(game, ani, "way", a="crew hangar")["text"].startswith("To the Crew Hangar: west, then north.")
    step(game, ani, "w")
    assert step(game, ani, "n")["text"] == "You've arrived at the Crew Hangar."
    walk(game, ani, "cabins_hall")
    cmd(game, ani, "way", a="my cabin")
    assert step(game, ani, "s")["text"] == "You've arrived at your cabin."


def test_a_teleport_to_another_world_loses_the_way(make_game):
    game = make_game()
    rafli = join(game, "Rafli")                          # an admin
    cmd(game, rafli, "way", a="workshop")
    cmd(game, rafli, "go", a="the lunar exchange")
    assert rafli.last()["text"] == "You can't get to the Workshop from here now, so the guide stops."
    assert rafli.session.guide is None


# ------------------------------------------------------------
# Keycards, the dark, one-way exits and vacuum
# ------------------------------------------------------------

def test_routes_use_only_the_doors_you_can_open(make_game):
    game = make_game()
    ani = join(game, "Ani")
    walk(game, ani, "service")
    cmd(game, ani, "way", a="cantina")
    assert ani.session.guide["path"] == [("s", "lift_lower"), ("u", "lift_main"), ("n", "promenade"),
                                         ("w", "promenade_west"), ("w", "cantina")]
    give(game, "ani", "keycard_crew")                   # the maintenance tunnels: a shortcut
    assert cmd(game, ani, "way", a="cantina")["text"] == "To the Cantina: southwest, up, north, then west."
    give(game, "ani", "holomapper")
    assert cmd(game, ani, "way", a="captain's quarters")["text"].startswith("You can't get to the Captain's")


def test_the_guide_leads_you_through_the_dark(make_game):
    game = make_game()
    ani = join(game, "Ani")
    walk(game, ani, "service")
    give(game, "ani", "keycard_crew")
    cmd(game, ani, "way", a="cantina")
    before = len(ani.sent)
    cmd(game, ani, "move", d="sw")
    moved, guided = ani.sent[before], ani.sent[before + 1]
    assert "pitch dark" in moved["text"]                  # no headlamp: you can't see the way on...
    assert guided["text"] == "Then up."                   # ...but the guide knows it
    assert step(game, ani, "s")["text"] == "Off the route. From here: north."     # deeper into the tunnels
    assert step(game, ani, "n")["text"] == "Then up."
    assert step(game, ani, "u")["text"] == "Then north."


def test_one_way_exits_are_only_taken_their_way(make_game):
    game = make_game()
    ani = join(game, "Ani")
    walk(game, ani, "park")
    assert cmd(game, ani, "way", a="service corridor")["k"] == "error"      # not a landmark
    give(game, "ani", "holomapper")
    assert cmd(game, ani, "way", a="service corridor")["text"].startswith("To the Service Corridor: down.")
    assert step(game, ani, "d")["text"] == "You've arrived at the Service Corridor."        # the slide
    assert cmd(game, ani, "way", a="park")["text"] == "To the Sky Park: south, up, then 2 north."   # not up it
    assert step(game, ani, "s")["text"] == "Then up."


def test_the_guide_says_when_a_suit_is_needed_next(make_game):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "holomapper", "eva_suit")          # owned, not worn: the way goes out all the same
    assert cmd(game, ani, "way", a="debris field")["text"].startswith("To the Debris Field: 3 south.")
    assert step(game, ani, "s")["text"] == "Then 2 south (wear your EVA suit first)."
    refused = cmd(game, ani, "move", d="s")
    assert refused["k"] == "error" and ani.session.guide is not None
    cmd(game, ani, "use", item="eva suit", equip=True)
    assert step(game, ani, "s")["text"] == "Then south."
    assert step(game, ani, "s")["text"] == "You've arrived at the Debris Field."


def test_the_kancil_is_a_step_of_the_way(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    walk(game, ani, "cargo")
    cmd(game, ani, "way", a="belt")
    assert step(game, ani, "w")["text"] == "Then ride the Kancil."
    cmd(game, ani, "board")
    clock.advance(31)
    game.tick()
    assert ani.session.char["location"] == "belt"
    assert [m["text"] for m in ani.sent if m.get("k") == "info"][-1] == "You've arrived at the Belt Platform."
