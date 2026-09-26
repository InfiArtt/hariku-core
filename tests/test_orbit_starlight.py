# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The Way of Starlight in Orbit 1.2: the Lantern Festival's lanterns count
# towards a goal (a few from each player), half way and the goal are news for
# everyone, and reaching it is a gift for everyone on the station, those who
# come later that day too, once; the keeper speaks of it. (The naming rite
# is in test_orbit_family.py, the Starlight wedding in test_orbit_weddings.py.)

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from tests.test_orbit_server import clock, cmd, join, make_game, world  # noqa: E402,F401


def light_round(game, clock, players):
    for conn in players:
        cmd(game, conn, "lantern")
    clock.advance(31)


def test_the_festival_goal_is_a_gift_for_everyone(make_game, clock):
    game = make_game()
    goal = game.festival_rules()["goal"]
    assert (goal, game.festival_rules()["cap"]) == (30, 5)
    players = [join(game, name) for name in ("Ani", "Budi", "Ceri", "Dani", "Eka", "Fajar")]
    far = join(game, "Gita", lang="id")                       # somewhere else on the station
    for conn in players:
        conn.session.char["location"] = "star_hall"
    game.start_event("lantern_festival")
    row = game.active_of("lantern_festival")
    light_round(game, clock, players)
    assert players[0].session.char["credits"] == 100 + 25       # free, and the day's thank-you
    assert "Your lantern counts for the festival: 1 of 30 glow now." in players[0].texts()
    assert cmd(game, players[0], "ask", to="Amara", a="festival")["words"].startswith(
        "The Lantern Festival is today! 6 of 30 lanterns are lit so far.")
    light_round(game, clock, players)
    light_round(game, clock, players)
    halfway = [m for m in far.sent if m.get("event") == "lantern_festival"]
    assert [m["text"] for m in halfway][1:] == ["The Lantern Festival is half way there: 15 of 30 lanterns glow "
                                            "in the Star Dome Hall."]
    credits = far.session.char["credits"]
    light_round(game, clock, players)
    light_round(game, clock, players)
    goal_news = [m for m in far.sent if m.get("event") == "lantern_festival"][-1]
    assert goal_news["text"].startswith("The Star Dome Hall glows with 30 lanterns: the Lantern Festival's goal "
                                        "is reached!")
    assert far.session.char["credits"] == credits + 60
    assert far.session.char["inventory"]["lantern_charm"] == 1
    assert far.texts()[-1] == "Your share of the festival's gift: 60 credits and a festival lantern charm. " \
                              f"You have {credits + 60} credits."
    assert game.store.get_json("lanterns")["count"] == 30
    assert game.store.event_points(row["id"], players[0].session.char["id"]) == 5
    cmd(game, players[0], "lantern")
    assert players[0].sent[-1]["text"].startswith("Your lanterns already count for the festival")
    before = players[1].session.char["credits"]
    clock.advance(31)
    cmd(game, players[1], "lantern")
    assert players[1].session.char["credits"] == before                     # the gift comes once
    late = join(game, "Ina")      # (Hana is a resident now: the name is taken)
    assert late.session.char["credits"] == 100 + 60 and late.session.char["inventory"]["lantern_charm"] == 1
    cmd(game, late, "bye")
    again = join(game, "Ina")
    assert again.session.char["credits"] == 160
    assert cmd(game, players[0], "ask", to="Amara", a="lanterns")["words"] == \
        "The festival's goal is reached: 30 lanterns glow tonight. What a sight."


def test_no_festival_no_goal(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    ani.session.char["location"] = "star_hall"
    cmd(game, ani, "lantern")
    assert not [m for m in ani.sent if "festival" in m.get("text", "").lower()]
    assert ani.session.char["credits"] == 97
    reply = cmd(game, ani, "ask", to="Amara", a="festival")["words"]
    assert reply.startswith("The Lantern Festival comes on the hundredth day of the year, 10-04-2027.")
