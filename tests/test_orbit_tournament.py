# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# What Orbit 1.1 left for 1.2: the duels' leaderboard, the weekly duel
# tournament on Pixel Pier's Tournament Stage (wins there count, the most
# take the prizes, the arcade's host follows it), and the Crew Hangar, a
# room each crew has to itself.

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_events  # noqa: E402
from tests.test_orbit_duels import round_to  # noqa: E402
from tests.test_orbit_server import clock, cmd, join, make_game, world  # noqa: E402,F401

UTC = datetime.timezone.utc


def text(game, conn, words):
    game.receive(conn, {"t": "cmd", "c": "text", "a": words})
    return [m for m in conn.sent if m.get("sound") != "achievement"][-1]


def duel(game, clock, winner, loser, room):
    """A duel in `room` that `winner` wins, two rounds to none; then the rest after it."""
    for conn in (winner, loser):
        game._move_to(conn.session, room, quiet=True)
    cmd(game, winner, "duel", to=loser.session.name)
    cmd(game, loser, "accept")
    round_to(game, winner, clock)
    round_to(game, winner, clock)
    clock.advance(61)


def test_the_duels_leaderboard(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    duel(game, clock, ani, budi, "gym")
    duel(game, clock, ani, budi, "gym")
    duel(game, clock, budi, ani, "gym")
    board = text(game, ani, "leaderboard duels")["text"]
    assert board.startswith("Leaderboard, duels: 1. Ani, 2; 2. Budi, 1.") and board.endswith("You're number 1.")
    assert game.store.by_name("ani")["duels_won"] == 2
    assert "duels" in cmd(game, ani, "leaderboard")["text"]
    game._move_to(ani.session, "pixel_stage", quiet=True)
    assert cmd(game, ani, "ask", to="Dario", a="duels")["words"].startswith("The fastest hand on the board is Ani, "
                                                                          "with 2 duels won.")


def test_the_weekly_tournament(make_game, clock):
    assert {"event": "tournament", "weekday": 6, "hour": 15, "minute": 0} in \
        orbit_events.EVENT_DEFAULTS["events_weekly"]
    game = make_game()
    ani, budi, ceri = join(game, "Ani"), join(game, "Budi"), join(game, "Ceri", lang="id")
    game._move_to(ani.session, "pixel_stage", quiet=True)
    assert cmd(game, ani, "ask", to="Dario", a="tournament")["words"] == \
        "Next tournament: Sunday at 15:00, station time, right here. The most duels won takes the prize."
    game.start_event("tournament")
    assert cmd(game, ani, "ask", to="Dario", a="tournament")["words"] == \
        "The tournament is on, for another 2 hours, and nobody has won a duel yet! Step up!"
    duel(game, clock, ani, budi, "pixel_stage")
    assert "Ani wins a tournament duel: 1 so far." in ani.texts()
    duel(game, clock, ani, budi, "pixel_stage")
    duel(game, clock, budi, ani, "pixel_stage")
    duel(game, clock, budi, ani, "gym")                                    # not on the stage: doesn't count
    game._move_to(ani.session, "pixel_stage", quiet=True)
    leads = cmd(game, ani, "ask", to="Dario", a="tournament")["words"]
    assert leads.startswith("The tournament is on, for another 1") and "Ani leads with 2 wins." in leads
    credits = (ani.session.char["credits"], budi.session.char["credits"])
    clock.advance(7200)
    game.tick()
    results = [m for m in ceri.sent if m.get("event") == "tournament"][-1]
    assert results["event"] == "tournament" and results["text"] == \
        ("The duel tournament's results: 1. Ani, duels won: 2, 500 credits; 2. Budi, duels won: 1, 200 credits. "
         "Congratulations!")
    assert ani.session.char["credits"] == credits[0] + 500 and budi.session.char["credits"] == credits[1] + 200
    assert ani.session.char["inventory"]["title_champion"] == 1
    assert "title_champion" not in budi.session.char["inventory"]


def test_admins_start_a_tournament_by_its_name(make_game):
    game = make_game()
    rafli = join(game, "Rafli", lang="id")
    assert cmd(game, rafli, "text", a="mulai acara turnamen")["text"].startswith("I don't understand")
    assert not game.active_of("tournament")
    cmd(game, rafli, "text", a="start event tournament")
    assert game.active_of("tournament")
    game.end_event(game.active_of("tournament"))
    cmd(game, rafli, "text", a="start event tournament")
    assert game.active_of("tournament")


def test_a_tournament_without_winners(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    game.start_event("tournament")
    clock.advance(7201)
    game.tick()
    assert "The tournament ended without a single duel won. Next week, then!" in ani.texts()


def test_the_crew_hangar_is_the_crews_own(make_game, clock):
    game = make_game()
    ani, budi, ceri = join(game, "Ani"), join(game, "Budi"), join(game, "Ceri")
    for conn in (ani, budi):
        conn.session.char.update(credits=1000, xp=game.xp_for_level(3))
    cmd(game, ani, "crew_create", a="Nova")
    clock.advance(2)
    cmd(game, budi, "crew_create", a="Comet")
    clock.advance(2)
    for conn in (ani, budi, ceri):
        game._move_to(conn.session, "hangar", quiet=True)
    assert cmd(game, ceri, "move", d="n")["text"].startswith("That door opens only for crews.")
    inside = cmd(game, ani, "move", d="n")
    assert inside["room"] == "crew_hangar" and "The crew board glows: Nova, 0 points" in inside["text"]
    cmd(game, budi, "move", d="n")
    assert game.room_of(ani.session.char) != game.room_of(budi.session.char)     # each crew its own room
    assert "Budi" not in cmd(game, ani, "look")["text"]
    dani = join(game, "Dani")
    game._move_to(dani.session, "hangar", quiet=True)
    cmd(game, ani, "crew_invite", to="Dani")
    cmd(game, dani, "accept")
    clock.advance(2)
    ani.clear()
    cmd(game, dani, "move", d="n")
    assert game.room_of(dani.session.char) == game.room_of(ani.session.char)
    assert ani.sent[-1]["k"] == "arrive" and ani.sent[-1]["actor"] == "Dani"
    assert "Here: Dani the pilot." in cmd(game, ani, "look")["text"]
    assert cmd(game, dani, "move", d="s")["room"] == "hangar"
