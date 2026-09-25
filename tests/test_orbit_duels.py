# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Duels (Orbit 1.1): only in the contest zones, both players agree, a small
# stake, quick-draw rounds played by the clock, false starts, forfeits,
# draws, the cooldowns, declining and refusing duels, mutes and admins.

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from tests.test_orbit_arcade import answer, wait_for  # noqa: E402
from tests.test_orbit_server import clock, cmd, join, make_game, world  # noqa: E402,F401

ARENA = "gym"


def two_in_the_ring(game, credits=500):
    ani, budi = join(game, "Ani"), join(game, "Budi")
    for conn in (ani, budi):
        game._move_to(conn.session, ARENA, quiet=True)
        conn.session.char["credits"] = credits
    return ani, budi


def texts(conn, since=0):
    return [m.get("text", "") for m in conn.sent[since:]]


def start(game, clock, ani, budi, stake=50):
    assert cmd(game, ani, "duel", to="Budi", n=stake)["k"] == "info"
    begun = cmd(game, budi, "accept")
    assert begun["k"] == "announce" and "face each other" in begun["text"], begun
    return begun


def round_to(game, conn, clock, ms=400):
    wait_for(game, conn, clock, lambda m: m.get("text") == "Draw!")
    clock.advance(ms / 1000.0)
    return answer(game, conn, "7")


def test_the_contest_zones(world):
    arenas = [lid for lid, loc in world.locations.items() if loc.get("arena")]
    assert set(arenas) == {"gym", "pixel_stage"}
    assert all(not world.locations[lid].get("private") for lid in arenas)


def test_a_duel_from_challenge_to_prize(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    cici = join(game, "Cici")
    game._move_to(cici.session, ARENA, quiet=True)
    sent = cmd(game, ani, "duel", to="Budi", n=50)
    assert sent["text"] == "You challenge Budi to a duel for 50 credits each."
    ask = budi.sent[-1]
    assert ask["k"] == "offer" and ask["ask"] == "duel" and ask["actor"] == "Ani" and ask["sound"] == "duel_start"
    assert ask["text"] == "Ani challenges you to a quick-draw duel for 50 credits each. Type accept or decline."
    assert cmd(game, ani, "duel", to="Budi", n=50)["text"] == "Budi hasn't answered your challenge yet."
    begun = cmd(game, budi, "accept")
    assert begun["text"].startswith("Ani and Budi face each other for a quick-draw duel, 50 credits each!")
    assert any("face each other" in t for t in texts(cici))                    # the room sees it
    assert ani.session.char["credits"] == budi.session.char["credits"] == 450
    # round 1 to Budi, round 2 to Ani, round 3 to Budi
    assert wait_for(game, ani, clock, lambda m: m.get("text") == "Round 1: ready...")["sound"] == "arcade_ready"
    reply = round_to(game, budi, clock, ms=350)
    assert reply["text"] == "Budi draws first, in 350 milliseconds! Ani 0, Budi 1."
    assert ani.sent[-1]["text"] == reply["text"]
    round_to(game, ani, clock)
    won = round_to(game, budi, clock)
    assert won["text"] == "Budi draws first, in 400 milliseconds! Ani 1, Budi 2."
    end = [t for t in texts(cici) if "wins the duel" in t]
    assert end == ["Budi wins the duel against Ani, 2 to 1, and takes 95 credits!"]
    assert budi.session.char["credits"] == 450 + 95 + 20 and ani.session.char["credits"] == 450   # and Duelist
    assert budi.session.char["stats"]["duels_won"] == 1 and ani.session.char["stats"]["duels_lost"] == 1
    assert game.flows["spent"]["duels"] == 100 and game.flows["earned"]["duels"] == 95
    assert "duelist" in set(game.store.achievements_of(budi.session.char["id"]))
    assert not game.duels
    # a breather before the next one
    assert cmd(game, ani, "duel", to="Budi")["text"].startswith("Catch your breath first:")
    assert cmd(game, budi, "duels")["text"].startswith("Duels: you've won 1 and lost 0.")


def test_drawing_too_soon_loses_the_round(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    start(game, clock, ani, budi, stake=0)
    wait_for(game, ani, clock, lambda m: m.get("text") == "Round 1: ready...")
    early = answer(game, ani, "1")
    assert early["text"] == "Ani drew too soon: the round goes to Budi. Ani 0, Budi 1."
    wait_for(game, ani, clock, lambda m: m.get("text") == "Round 2: ready...")
    early = answer(game, ani, "1")
    assert early["text"] == "Ani drew too soon: the round goes to Budi. Ani 0, Budi 2."
    assert "Budi wins the duel against Ani, 2 to 0!" in texts(ani)
    assert ani.session.char["credits"] == 500 and budi.session.char["credits"] == 500 + 20    # no stake, no fee


def test_walking_out_is_a_forfeit(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    start(game, clock, ani, budi, stake=20)
    cmd(game, ani, "move", d=next(iter(game.world.exits[ARENA])))
    game.tick()
    assert "Ani walks out of the duel: Budi wins, and takes 38 credits." in texts(budi)
    assert "Ani walks out of the duel: Budi wins, and takes 38 credits." in texts(ani)       # told where they went
    assert budi.session.char["credits"] == 480 + 38 + 20 and not game.duels


def test_leaving_the_game_is_a_forfeit_too(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    start(game, clock, ani, budi, stake=10)
    cmd(game, ani, "bye")
    assert "Ani walks out of the duel: Budi wins, and takes 19 credits." in texts(budi)
    assert not game.duels


def test_nobody_drawing_and_a_draw(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    start(game, clock, ani, budi, stake=30)
    for _ in range(5):
        wait_for(game, ani, clock, lambda m: m.get("text") == "Draw!")
        wait_for(game, ani, clock, lambda m: m.get("text") == "Nobody drew. Again.")
    assert "The duel of Ani and Budi ends even: the stakes go back." in texts(ani)
    assert ani.session.char["credits"] == budi.session.char["credits"] == 500
    assert "duels_won" not in ani.session.char["stats"]


def test_where_and_whom_you_can_challenge(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game, credits=40)
    game._move_to(ani.session, "dock", quiet=True)
    assert cmd(game, ani, "duel", to="Budi")["text"].startswith("Duels are fought only in the contest zones: the "
                                                                "Zero-G Gym")
    game._move_to(ani.session, ARENA, quiet=True)
    assert cmd(game, ani, "duel", to="Cici")["text"] == "Cici isn't here."
    assert cmd(game, ani, "duel", to="Ani")["text"] == "You'd only draw against yourself."
    assert cmd(game, ani, "duel", to="Budi", n=500)["text"] == "A stake is 0 to 100 credits."
    assert cmd(game, ani, "duel", to="Budi", n=50)["text"] == "A stake of 50 credits, and you have 40."
    assert cmd(game, ani, "duel")["text"].startswith("Who?")
    # Budi can't pay when it's time to
    ani.session.char["credits"] = 100
    cmd(game, ani, "duel", to="Budi", n=50)
    assert cmd(game, budi, "accept")["text"] == "Budi can't cover the stake of 50 credits."
    assert ani.session.char["credits"] == 100 and not game.duels


def test_declining_refusing_and_muting(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    cmd(game, ani, "duel", to="Budi")
    assert cmd(game, budi, "decline")["text"] == "You decline Ani's duel."
    assert ani.sent[-1]["text"] == "Budi declines your duel."
    assert cmd(game, ani, "duel", to="Budi")["text"].startswith("Budi declined you not long ago. Try again in")
    clock.advance(301)
    assert cmd(game, budi, "duels", op="off")["text"].startswith("You refuse all duels now.")
    assert cmd(game, ani, "duel", to="Budi")["text"] == "Budi doesn't take duels."
    cmd(game, budi, "duels", op="on")
    cmd(game, ani, "duel", to="Budi")
    clock.advance(61)
    game.tick()
    assert budi.sent[-1]["text"] == "Ani's challenge has run out." and ani.sent[-1]["text"] == \
        "Budi didn't answer your challenge."
    rafli = join(game, "Rafli")
    cmd(game, rafli, "admin", op="mute", to="Ani", n=5)
    assert cmd(game, ani, "duel", to="Budi")["text"].startswith("You're muted")


def test_admins_can_stop_a_duel(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    rafli = join(game, "Rafli")
    start(game, clock, ani, budi, stake=40)
    assert cmd(game, rafli, "admin", op="duel_stop", to="Cici")["text"] == "Cici isn't in a duel."
    assert cmd(game, rafli, "admin", op="duel_stop", to="Budi")["text"] == "The duel of Ani and Budi is stopped."
    assert "The station's admins stop the duel of Ani and Budi: the stakes go back." in texts(ani)
    assert ani.session.char["credits"] == budi.session.char["credits"] == 500 and not game.duels
    assert "stop duel" in {row["action"] for row in game.store.admin_log(10)}


def test_a_duel_and_the_arcade_dont_mix(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    start(game, clock, ani, budi, stake=0)
    cici = join(game, "Cici")
    game._move_to(cici.session, ARENA, quiet=True)
    assert cmd(game, cici, "duel", to="Ani")["text"] == "Ani is busy with a game right now."


def test_the_phrases(make_game, clock):
    game = make_game()
    ani, budi = two_in_the_ring(game)
    game.receive(ani, {"t": "cmd", "c": "text", "a": "tantang duel Budi 25"})
    assert ani.sent[-1]["text"] == "You challenge Budi to a duel for 25 credits each."
    game.receive(budi, {"t": "cmd", "c": "text", "a": "matikan duel"})
    assert budi.sent[-1]["text"].startswith("You refuse all duels now.")
    game.receive(budi, {"t": "cmd", "c": "text", "a": "duels on"})
    assert budi.sent[-1]["text"] == "You take duels again."
