# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Pixel Pier's arcade (Orbit 1.1): tokens, the four cabinets (Quick Draw,
# Star Beat, Echo, Meteor Dodge) played through by the clock, prize tickets
# and the Prize Counter, the high score tables and their news, walking away,
# and the database's migration to schema 6.

import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_arcade  # noqa: E402
import orbit_store  # noqa: E402
from tests.test_orbit_economy import _old_database  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, cmd, join, make_game, secret_of, world  # noqa: E402,F401

CABINETS = "pixel_cabinets"


def at_cabinets(game, conn, tokens=10):
    char = conn.session.char
    game._move_to(conn.session, CABINETS, quiet=True)
    if tokens:
        char["inventory"]["arcade_token"] = tokens
    return char


def join_client(game, name, client):
    conn = FakeConn("en")
    game.hello(conn, {"t": "hello", "v": 1, "lang": "en", "name": name, "job": "pilot",
                      "secret": secret_of(name), "client": client})
    return conn


def wait_for(game, conn, clock, found, step=0.25, limit=30.0):
    """Lets time pass (the game ticking) until a message `found` accepts arrives."""
    start = len(conn.sent)
    waited = 0.0
    while waited <= limit:
        for message in conn.sent[start:]:
            if found(message):
                return message
        clock.advance(step)
        waited += step
        game.tick()
    raise AssertionError(f"nothing came: {conn.sent[start:][-3:]}")


def sound(name):
    return lambda m: m.get("sound") == name


def text_has(words):
    return lambda m: words in m.get("text", "")


def answer(game, conn, text):
    """The first thing the game says back (an achievement aside)."""
    start = len(conn.sent)
    game.receive(conn, {"t": "cmd", "c": "answer", "a": text})
    said = [m for m in conn.sent[start:] if m.get("sound") != "achievement"]
    return said[0] if said else None


def tickets(conn):
    return conn.session.char["inventory"].get("arcade_ticket", 0)


# ------------------------------------------------------------
# The numbers
# ------------------------------------------------------------

def test_the_scoring_rules():
    assert orbit_arcade.reaction_points(200, 200, 2000) == 100
    assert orbit_arcade.reaction_points(150, 200, 2000) == 100
    assert orbit_arcade.reaction_points(1100, 200, 2000) == 50
    assert orbit_arcade.reaction_points(2500, 200, 2000) == 0
    gaps = [0.5, 1.0, 0.5]
    assert orbit_arcade.beat_points(gaps, [0, 0.5, 1.5, 2.0], 0.4) == [100, 100, 100]
    assert orbit_arcade.beat_points(gaps, [0, 0.6, 1.6, 2.4], 0.4) == [50, 100, 0]
    assert orbit_arcade.beat_points(gaps, [0, 0.5], 0.4) == [100, 0, 0]          # taps missing
    assert orbit_arcade.tickets_for({"from": 3, "rate": 2, "max": 20}, 8) == 10
    assert orbit_arcade.tickets_for({"from": 3, "rate": 2, "max": 20}, 2) == 0
    assert orbit_arcade.tickets_for({"from": 0, "rate": 0.5, "max": 20}, 100) == 20
    assert orbit_arcade.client_version("Hariku Orbit 1.1") == (1, 1)
    assert orbit_arcade.client_version("Hariku Orbit 1.0") == (1, 0)
    assert orbit_arcade.client_version("Hariku Orbit 2.10") == (2, 10)
    assert orbit_arcade.client_version(None) == orbit_arcade.client_version("some bot 3.0") == (0, 0)


def test_the_arcade_is_set_up_on_pixel_pier(world):
    cabinets = world.locations[CABINETS]
    assert cabinets["arcade"] and cabinets["shop"] == "tokens" and world.world_of(CABINETS) == "pixel"
    assert world.shops["prizes"]["currency"] == "arcade_ticket"
    assert world.locations["pixel_prizes"]["shop"] == "prizes"
    games = world.economy["arcade"]["games"]
    assert set(games) == set(orbit_arcade.GAMES)
    for gid, game in games.items():
        assert game["name"]["en"] and game["name"]["id"] and game["tickets"]["max"] > 0, gid
    for tid in world.shops["prizes"]["stock"]:
        thing = world.things[tid]
        assert thing["tickets"] > 0 and thing.get("pawn") is False and not thing.get("price"), tid
    assert world.things["arcade_ticket"].get("pawn") is False and not world.things["arcade_ticket"].get("price")


# ------------------------------------------------------------
# Tokens, and where you can play
# ------------------------------------------------------------

def test_tokens_from_the_machine_and_what_the_arcade_says(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    char = at_cabinets(game, ani, tokens=0)
    char["credits"] = 100
    bought = cmd(game, ani, "buy", item="token", n=10)
    assert bought["k"] == "trade" and char["credits"] == 50 and char["inventory"]["arcade_token"] == 10
    text = cmd(game, ani, "arcade")["text"]
    assert text.startswith("Pixel Pier's arcade, on Cabinet Row:")
    for name in ("Quick Draw", "Star Beat", "Echo", "Meteor Dodge"):
        assert name in text
    assert "You have 10 tokens (5 credits each" in text and "and 0 prize tickets" in text
    assert "Four of them are lit" in cmd(game, ani, "look")["text"]
    assert "Quick Draw (1 token)" in cmd(game, ani, "look", a="cabinet")["text"]
    assert game.world.things["arcade_token"]["pawn"] is False and not game._tradeable("arcade_token")
    assert not game._tradeable("arcade_ticket")


def test_you_play_at_the_cabinets_with_a_token(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    assert cmd(game, ani, "play", a="echo")["text"] == "The cabinets are on Cabinet Row, on Pixel Pier."
    char = at_cabinets(game, ani, tokens=0)
    assert cmd(game, ani, "play", a="echo")["text"].startswith("That takes 1 token, and you have 0.")
    assert cmd(game, ani, "play", a="chess")["text"] == "Which game? Quick Draw, Star Beat, Echo, Meteor Dodge."
    assert cmd(game, ani, "play", a="")["text"].startswith("Which game?")
    char["inventory"]["arcade_token"] = 2
    started = cmd(game, ani, "play", a="gema")
    assert started["k"] == "task" and started["sound"] == "arcade_start" and started["text"].startswith("Echo!")
    assert char["inventory"]["arcade_token"] == 1 and ani.session.arcade["game"] == "echo"
    assert cmd(game, ani, "play", a="meteor")["text"].startswith("You're already playing Echo.")
    assert cmd(game, ani, "stop_game")["text"].startswith("You stop the game.")
    assert ani.session.arcade is None and char["inventory"]["arcade_token"] == 1
    assert cmd(game, ani, "stop_game")["text"] == "You're not playing anything."


def test_main_street_is_a_place_not_a_game(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    game.receive(ani, {"t": "cmd", "c": "text", "a": "main street"})     # "main" is also "play"
    assert "To the Promenade: " in ani.sent[-1]["text"]


# ------------------------------------------------------------
# The games
# ------------------------------------------------------------

def test_quick_draw(make_game, clock):
    game = make_game()
    ani, budi = join(game, "Ani"), join(game, "Budi")
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="quick draw")
    rounds = []
    # 1: a quick one (half a second)
    wait_for(game, ani, clock, text_has("Round 1 of 5: ready"))
    go = wait_for(game, ani, clock, sound("arcade_go"))
    assert go["text"] == "Now!" and go["k"] == "task"
    clock.advance(0.5)
    hit = answer(game, ani, "5")
    assert hit["text"] == "500 milliseconds: 83 points." and hit["sound"] == "arcade_hit"
    rounds.append(83)
    # 2: too soon
    wait_for(game, ani, clock, text_has("Round 2 of 5: ready"))
    assert answer(game, ani, "5")["text"] == "Too soon! No points this round."
    rounds.append(0)
    # 3: too slow
    wait_for(game, ani, clock, sound("arcade_go"))
    assert wait_for(game, ani, clock, text_has("Too slow!"), step=0.5)
    rounds.append(0)
    # 4: too soon again; 5: a little over a second
    wait_for(game, ani, clock, text_has("Round 4 of 5"))
    assert answer(game, ani, "1")["text"] == "Too soon! No points this round."
    wait_for(game, ani, clock, text_has("Round 5 of 5"))
    wait_for(game, ani, clock, sound("arcade_go"))
    clock.advance(1.1)
    assert answer(game, ani, "1")["text"] == "1100 milliseconds: 50 points."
    over = next(m for m in reversed(ani.sent) if "Game over." in m.get("text", ""))
    assert "Your score: 133 points (on average 800 milliseconds)." in over["text"]
    assert "A new high score" in over["text"] and ani.session.arcade is None
    assert tickets(ani) == 2 + 25                               # 133 * 0.02, and the record's bonus
    assert any("Ani has set a new high score on Quick Draw: 133!" in m.get("text", "") for m in budi.sent)
    assert game.store.arcade_best("quickdraw", ani.session.char["id"]) == 133


def test_star_beat(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="irama bintang")
    rhythm = wait_for(game, ani, clock, lambda m: m.get("beats"))
    beats = rhythm["beats"]
    assert len(beats) == 5 and beats[0] == 1.2 and rhythm["k"] == "task" and "sound" not in rhythm
    gaps = [round(b - a, 3) for a, b in zip(beats, beats[1:])]
    assert set(gaps) == {0.5, 1.0}                                  # short and long, both
    assert rhythm["text"].startswith("Rhythm 1 of 3: 5 beats, the gaps ")
    for gap in [0.0] + gaps:                                        # tapped exactly
        clock.advance(gap)
        answer(game, ani, "5")
    assert "400 of 400 points." in ani.sent[-1]["text"] or any(
        "400 of 400 points." in m.get("text", "") for m in ani.sent[-3:])
    rhythm = wait_for(game, ani, clock, lambda m: m.get("beats"))
    assert len(rhythm["beats"]) == 6
    gaps = [b - a for a, b in zip(rhythm["beats"], rhythm["beats"][1:])]
    for gap in [0.0] + [g * 1.2 for g in gaps]:                     # 20% slow: half the points
        clock.advance(gap)
        answer(game, ani, "5")
    assert any("250 of 500 points." in m.get("text", "") for m in ani.sent[-3:])
    rhythm = wait_for(game, ani, clock, lambda m: m.get("beats"))
    assert len(rhythm["beats"]) == 7
    assert answer(game, ani, "5") is None                          # a tap is heard, not answered
    wait_for(game, ani, clock, text_has("0 of 600 points."), step=1.0)
    over = next(m for m in reversed(ani.sent) if "Game over." in m.get("text", ""))
    assert "Your score: 650 points." in over["text"]
    assert tickets(ani) == 4 + 25


def test_echo(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="echo")
    first = wait_for(game, ani, clock, lambda m: m.get("codes"))
    assert first["k"] == "tones" and len(first["codes"]) == 3 and first["text"] == "3 tones. Type them back."
    codes = first["codes"]
    for n in range(4, 9):
        reply = answer(game, ani, " ".join(map(str, codes)))
        assert reply["text"] == f"Right! Now {n} tones." and reply["codes"][:-1] == codes
        codes = reply["codes"]
    wrong = [5 - c for c in codes]
    said = answer(game, ani, "".join(map(str, wrong)))["text"]
    assert said == "Not quite: they were " + ", ".join(map(str, codes)) + "."
    over = next(m for m in reversed(ani.sent) if "Game over." in m.get("text", ""))
    assert "Your score: 7 tones." in over["text"]
    assert tickets(ani) == 8 + 25


def test_echo_waits_only_so_long(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="echo")
    wait_for(game, ani, clock, lambda m: m.get("codes"))
    late = wait_for(game, ani, clock, text_has("Time's up."), step=1.0)
    assert late["k"] == "failed"
    assert "Your score: 0 tones." in ani.sent[-1]["text"] or any("0 tones" in m.get("text", "") for m in ani.sent)
    assert tickets(ani) == 0 and ani.session.arcade is None


def test_meteor_dodge_by_stereo(make_game, clock):
    game = make_game()
    ani = join_client(game, "Ani", "Hariku Orbit 1.1")
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="meteor dodge")
    dodged = 0
    lives = 3
    while lives:
        meteor = wait_for(game, ani, clock, sound("arcade_meteor"))
        assert meteor["text"] == "Meteor!" and meteor["dir"] in ("w", "e", "n")
        away = {"w": "6", "e": "4", "n": "4"}[meteor["dir"]]
        into = {"w": "4", "e": "6", "n": None}[meteor["dir"]]
        if dodged < 3:
            clock.advance(0.4)
            reply = answer(game, ani, away)
            dodged += 1
            assert reply["text"] == f"Dodged! {dodged} so far." and reply["sound"] == "arcade_whoosh"
        elif into:
            lives -= 1
            reply = answer(game, ani, into)
            assert reply["sound"] == "arcade_crash" and reply["text"].startswith("Wrong way")
        else:
            lives -= 1
            late = wait_for(game, ani, clock, text_has("Too late"))
            assert late["sound"] == "arcade_crash"
    over = next(m for m in reversed(ani.sent) if "Game over." in m.get("text", ""))
    assert "Your score: 3 meteors dodged." in over["text"]


def test_meteor_dodge_tells_older_clients_the_side_and_takes_words(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")                          # no client version: the side is said
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="meteor")
    meteor = wait_for(game, ani, clock, sound("arcade_meteor"))
    side = {"w": "left", "e": "right", "n": "ahead"}[meteor["dir"]]
    assert meteor["text"] == ("Meteor straight ahead!" if side == "ahead" else f"Meteor from the {side}!")
    word = {"w": "kanan", "e": "kiri", "n": "kiri"}[meteor["dir"]]
    game.receive(ani, {"t": "cmd", "c": "text", "a": word})
    assert ani.sent[-1]["text"] == "Dodged! 1 so far."
    meteor = wait_for(game, ani, clock, sound("arcade_meteor"))
    assert answer(game, ani, "9")["text"] == "Step away: 4 to the left, 6 to the right."
    limit = ani.session.arcade["limit"]
    assert limit == pytest.approx(2.9)                               # a little quicker each time


def test_walking_away_or_dropping_ends_the_game(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="echo")
    cmd(game, ani, "move", d="e")
    assert ani.session.arcade is None
    assert any("You walk away from the cabinet: game over." in m.get("text", "") for m in ani.sent[-4:])
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="echo")
    game.dropped(ani)
    assert ani.session is None
    session = game.sessions["ani"]
    assert session.arcade is None
    assert game.store.by_name("ani")["stats"]["arcade_games"] == 2


# ------------------------------------------------------------
# Tickets, prizes, tables
# ------------------------------------------------------------

def test_prizes_for_tickets_at_the_counter(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    char = ani.session.char
    game._move_to(ani.session, "pixel_prizes", quiet=True)
    char["inventory"]["arcade_ticket"] = 45
    credits = char["credits"]
    listed = cmd(game, ani, "list")["text"]
    assert listed.startswith("the Prize Counter, for prize tickets: plush comet, 40 prize tickets;")
    assert "enormous robot, 2500 prize tickets" in listed and listed.endswith("You have 45 prize tickets.")
    assert "Here it takes 100 prize tickets." in cmd(game, ani, "look", a="glow stars")["text"]
    got = cmd(game, ani, "buy", item="plush comet")
    assert got["text"] == "You get 1 plush comet for 40 prize tickets. You have 5 prize tickets left."
    assert char["credits"] == credits and game.owns(char, "plush_comet")
    assert cmd(game, ani, "buy", item="glow stars")["text"] == \
        "That takes 100 prize tickets, and you have 5 prize tickets."
    assert cmd(game, ani, "buy", item="plush comet")["text"].startswith("You already have")
    assert not game._tradeable("plush_comet") and game.world.things["giant_robot"]["pawn"] is False


def test_high_score_tables(make_game, clock):
    game = make_game()
    ani, budi, cici = join(game, "Ani"), join(game, "Budi"), join(game, "Cici")
    ids = {c.session.name: c.session.char["id"] for c in (ani, budi, cici)}
    game.store.save_arcade_score("meteor", ids["Budi"], 12, 100.0)
    game.store.save_arcade_score("meteor", ids["Ani"], 12, 200.0)             # the same, but later
    game.store.save_arcade_score("meteor", ids["Cici"], 20, 300.0)
    game.store.save_arcade_score("meteor", ids["Cici"], 5, 400.0)             # a worse game keeps the best
    assert game.store.arcade_top("meteor") == [("Cici", 20), ("Budi", 12), ("Ani", 12)]
    assert game.store.arcade_best("meteor", ids["Cici"]) == 20
    assert game.store.arcade_best("echo", ids["Cici"]) is None
    table = cmd(game, ani, "high_scores", a="meteor")["text"]
    assert table == "Meteor Dodge: 1. Cici, 20; 2. Budi, 12; 3. Ani, 12. Your best: 12."
    everything = cmd(game, ani, "high_scores")["text"]
    assert everything.startswith("Quick Draw: nobody yet. Star Beat: nobody yet. Echo: nobody yet. Meteor Dodge: 1. ")
    game.receive(ani, {"t": "cmd", "c": "text", "a": "high scores meteor"})
    assert ani.sent[-1]["text"] == table
    game.receive(ani, {"t": "cmd", "c": "text", "a": "skor arkade"})
    assert ani.sent[-1]["text"] == everything
    game._move_to(ani.session, "pixel_scores", quiet=True)
    assert cmd(game, ani, "look", a="wall")["text"] == everything


def test_help_and_the_general_boards(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    assert cmd(game, ani, "help", a="arcade")["text"].startswith("The arcade, on Pixel Pier: buy tokens")
    assert "help arcade" in cmd(game, ani, "help")["text"]
    game.receive(ani, {"t": "cmd", "c": "text", "a": "high scores"})
    assert "Pixel Pier" not in ani.sent[-1]["text"] and "Meteor Dodge" not in ani.sent[-1]["text"]
    game.receive(ani, {"t": "cmd", "c": "text", "a": "leaderboard arcade"})
    assert ani.sent[-1]["text"].startswith("Quick Draw: nobody yet.")


def test_achievements_for_playing(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    at_cabinets(game, ani)
    cmd(game, ani, "play", a="echo")
    cmd(game, ani, "stop_game")
    earned = set(game.store.achievements_of(ani.session.char["id"]))
    assert "player_one" in earned and "high_scorer" not in earned        # a score of 0 is no record


def test_a_version_5_database_gets_the_arcade_table(tmp_path, clock, monkeypatch):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    with monkeypatch.context() as m:
        m.setattr(orbit_store, "SCHEMA_VERSION", 5)
        m.setattr(orbit_store.Store, "_migrate_6", lambda self: None)
        orbit_store.Store(path, clock=clock, iterations=1000, durable=False).close()
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 5
    assert not db.execute("SELECT name FROM sqlite_master WHERE name = 'arcade_scores'").fetchall()
    db.close()
    store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert store.version() == orbit_store.SCHEMA_VERSION and store.migrated_from == 5
    quila = store.by_name("quilafly")
    assert quila["credits"] == 1234
    store.save_arcade_score("echo", quila["id"], 9, 1.0)
    assert store.arcade_top("echo") == [("Quilafly", 9)]
    store.close()
    backup = sqlite3.connect(path + f".before-v{orbit_store.SCHEMA_VERSION}.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 5
    backup.close()
