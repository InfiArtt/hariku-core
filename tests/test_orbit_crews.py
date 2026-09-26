# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Crews (Orbit 1.1): founding one, names and their filter, invitations
# answered like offers, crew chat and its moderation, leaving and the
# captain's place, kicking, the motto, points from XP, the board, admins
# disbanding a crew, and the database's migration to schema 7.

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_store  # noqa: E402
from tests.test_orbit_economy import _old_database  # noqa: E402
from tests.test_orbit_server import clock, cmd, join, make_game, world  # noqa: E402,F401


def ready(game, conn, level=3, credits=1000):
    char = conn.session.char
    char["xp"] = game.xp_for_level(level)
    char["credits"] = credits
    return char


def text(game, conn, words):
    game.receive(conn, {"t": "cmd", "c": "text", "a": words})
    return [m for m in conn.sent if m.get("sound") != "achievement"][-1]


def found(game, clock, name="Nova", captain="Ani"):
    conn = join(game, captain)
    ready(game, conn)
    reply = cmd(game, conn, "crew_create", a=name)
    assert reply["text"].startswith(f"You found the crew {name}"), reply
    clock.advance(2)
    return conn


def invite_in(game, clock, captain, conn):
    cmd(game, captain, "crew_invite", to=conn.session.name)
    reply = cmd(game, conn, "accept")
    assert reply["text"].startswith("Welcome aboard"), reply
    clock.advance(2)


# ------------------------------------------------------------
# Founding
# ------------------------------------------------------------

def test_founding_a_crew(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    char = ready(game, ani, level=1)
    assert cmd(game, ani, "crew")["text"].startswith("You're not in a crew. Found one with crew create")
    assert cmd(game, ani, "crew_create", a="Nova")["text"] == "You can found a crew from level 3."
    ready(game, ani, credits=100)
    assert cmd(game, ani, "crew_create", a="Nova")["text"] == \
        "Founding a crew costs 500 credits, and you have 100."
    char["credits"] = 800
    assert cmd(game, ani, "crew_create", a="")["text"] == "Name it: crew create and the name."
    assert cmd(game, ani, "crew_create", a="Ab")["text"] == "A crew's name is 3 to 24 characters."
    assert cmd(game, ani, "crew_create", a="<script>")["text"].startswith("A crew's name is letters")
    made = cmd(game, ani, "crew_create", a="  Nova   Prime ")
    assert made["text"].startswith("You found the crew Nova Prime, with yourself as its captain (500 credits;")
    assert made["sound"] == "crew_join" and char["credits"] == 300 + 25       # and the Crewmate achievement
    assert game.flows["spent"]["crews"] == 500
    crew, role = game.store.crew_of(char["id"])
    assert (crew["name"], crew["name_key"], role) == ("Nova Prime", "novaprime", "captain")
    assert cmd(game, ani, "crew_create", a="Other")["text"] == "You're already in the crew Nova Prime."
    info = cmd(game, ani, "crew")["text"]
    assert info == "The crew Nova Prime: captain Ani; 1 members: Ani (online). 0 points."
    assert "crewmate" in set(game.store.achievements_of(char["id"]))
    # the name is taken, whatever its spaces and case
    budi = join(game, "Budi")
    ready(game, budi)
    assert cmd(game, budi, "crew_create", a="nova prime")["text"] == "There's already a crew called nova prime."
    assert cmd(game, budi, "crew_create", a="NovaPrime")["text"] == "There's already a crew called NovaPrime."


def test_crew_names_go_through_the_word_filter(make_game, clock, monkeypatch):
    game = make_game()
    ani = join(game, "Ani")
    ready(game, ani)
    bad = next(w for w in game.filter.words if len(w) >= 4)
    assert cmd(game, ani, "crew_create", a=f"The {bad} Crew")["text"] == "That name isn't allowed."
    assert game.store.crew_of(ani.session.char["id"]) is None


# ------------------------------------------------------------
# Joining
# ------------------------------------------------------------

def test_invitations_are_answered_like_offers(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi, cici = join(game, "Budi"), join(game, "Cici")
    assert cmd(game, budi, "crew_invite", to="Cici")["text"] == "You're not in a crew."
    assert cmd(game, ani, "crew_invite", to="Nobody")["k"] == "error"
    assert cmd(game, ani, "crew_invite", to="Budi")["text"] == "You invite Budi to the crew Nova."
    ask = budi.sent[-1]
    assert ask["k"] == "offer" and ask["ask"] == "crew" and ask["actor"] == "Ani"
    assert ask["text"] == "Ani invites you to join the crew Nova. Type accept or decline."
    assert cmd(game, ani, "crew_invite", to="Budi")["text"] == "Budi hasn't answered your invitation yet."
    joined = cmd(game, budi, "accept")
    assert joined["text"].startswith("Welcome aboard: you're in the crew Nova.")
    assert any(m.get("text") == "Budi joins the crew Nova!" for m in ani.sent)
    assert game.store.crew_of(budi.session.char["id"])[1] == "member"
    # declining
    cmd(game, ani, "crew_invite", to="Cici")
    assert cmd(game, cici, "decline")["text"] == "You decline the invitation to Nova."
    assert ani.sent[-1]["text"] == "Cici declines your invitation."
    # the natural sentence, from either client
    assert text(game, ani, "invite Cici to the crew")["text"] == "You invite Cici to the crew Nova."
    clock.advance(121)
    game.tick()
    assert cici.sent[-1]["text"] == "The invitation to Nova has run out."
    assert cmd(game, cici, "accept")["k"] == "error"


def test_the_newest_ask_is_the_one_answered(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi, cici = join(game, "Budi"), join(game, "Cici")
    cici.session.char["credits"] = 500
    for conn in (budi, cici):
        game._move_to(conn.session, "casino", quiet=True)
    cmd(game, cici, "challenge", to="Budi", n=10)
    clock.advance(1)
    cmd(game, ani, "crew_invite", to="Budi")
    assert cmd(game, budi, "decline")["text"] == "You decline the invitation to Nova."
    assert game.challenges.get("budi")                    # the older ask still waits


def test_a_crew_has_room_for_twelve(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    for i in range(11):
        conn = join(game, f"Mate{i}x")
        invite_in(game, clock, ani, conn)
    join(game, "Extra")
    assert cmd(game, ani, "crew_invite", to="Extra")["text"] == "A crew has at most 12 members."


# ------------------------------------------------------------
# Talking
# ------------------------------------------------------------

def test_crew_chat_reaches_the_crew_anywhere_and_no_one_else(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi, cici = join(game, "Budi"), join(game, "Cici")
    invite_in(game, clock, ani, budi)
    game._move_to(budi.session, "engineering", quiet=True)
    budi.session.char["voice"] = 4
    sent = cmd(game, budi, "crew_say", a="  hello   everyone ")
    assert sent["k"] == "crew_sent" and sent["text"] == "You tell the crew Nova: hello everyone"
    assert sent["words"] == "hello everyone" and sent["voice"] == 4 and sent["brief"] == "Told the crew."
    heard = ani.sent[-1]
    assert heard["k"] == "crew" and heard["actor"] == "Budi" and heard["sound"] == "crew_chat"
    assert heard["text"] == "Budi, to the crew Nova: hello everyone" and heard["words"] == "hello everyone"
    assert not any(m.get("k") == "crew" for m in cici.sent)
    assert text(game, ani, "crew say ready!")["text"] == "You tell the crew Nova: ready!"
    assert budi.sent[-1]["text"] == "Ani, to the crew Nova: ready!"
    assert cmd(game, cici, "crew_say", a="hi")["text"] == "You're not in a crew."
    # "tell crew ...": both clients send it as a whisper to "crew"
    cmd(game, ani, "whisper", to="crew", a="by whisper")
    assert budi.sent[-1]["text"] == "Ani, to the crew Nova: by whisper"
    assert cmd(game, cici, "whisper", to="crew", a="hi")["text"] == "Nobody called crew is on the station."
    # the old Indonesian "kru" is nobody now, even to a crew's member
    assert cmd(game, ani, "whisper", to="kru", a="hi")["text"] == "Nobody called kru is on the station."


def test_crew_chat_is_moderated_like_any_chat(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi = join(game, "Budi")
    invite_in(game, clock, ani, budi)
    bad = next(w for w in game.filter.words if len(w) >= 4)
    cmd(game, budi, "crew_say", a=f"you {bad}")
    assert bad not in ani.sent[-1]["text"]
    rafli = join(game, "Rafli")
    cmd(game, rafli, "admin", op="mute", to="Budi", n=5)
    before = len(ani.sent)
    assert cmd(game, budi, "crew_say", a="hello")["k"] == "error"
    assert len(ani.sent) == before
    for _ in range(20):
        cmd(game, ani, "crew_say", a="spam")
    assert cmd(game, ani, "crew_say", a="spam")["text"] == "Easy, not so fast! Wait a moment."


# ------------------------------------------------------------
# Leaving, the captain, the motto
# ------------------------------------------------------------

def test_leaving_passes_the_captaincy_on_and_the_last_one_out_ends_it(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi, cici = join(game, "Budi"), join(game, "Cici")
    invite_in(game, clock, ani, budi)
    invite_in(game, clock, ani, cici)
    assert cmd(game, ani, "crew_leave")["text"] == "You leave the crew Nova."
    assert any(m.get("text") == "Budi is now the captain of the crew Nova." for m in cici.sent)
    assert game.store.crew_of(budi.session.char["id"])[1] == "captain"
    assert cmd(game, cici, "crew_leave")["text"] == "You leave the crew Nova."
    assert cmd(game, budi, "crew_leave")["text"] == "You leave the crew Nova."
    assert game.store.crew_by_key("nova") is None
    ready(game, ani)
    assert text(game, ani, "crew create Nova")["text"].startswith("You found the crew Nova")


def test_the_captain_kicks_hands_over_and_sets_the_motto(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi, cici = join(game, "Budi"), join(game, "Cici")
    invite_in(game, clock, ani, budi)
    invite_in(game, clock, ani, cici)
    assert cmd(game, budi, "crew_kick", to="Cici")["text"] == "Only your crew's captain can do that."
    assert cmd(game, ani, "crew_kick", to="Dedi")["text"] == "Dedi isn't in the crew Nova."
    assert cmd(game, ani, "crew_kick", to="Ani")["text"] == "To leave, type crew leave."
    assert cmd(game, ani, "crew_kick", to="cici")["text"] == "Cici is off the crew."
    assert cici.sent[-1]["text"] == "Ani has taken you off the crew Nova."
    assert game.store.crew_of(cici.session.char["id"]) is None
    assert cmd(game, ani, "crew_motto", a="To the stars!")["text"] == "The crew's motto is now: To the stars!"
    assert cmd(game, budi, "crew")["text"].endswith("Motto: To the stars!")
    cmd(game, ani, "crew_captain", to="Budi")
    assert budi.sent[-1]["text"] == "Budi is now the captain of the crew Nova."
    assert game.store.crew_of(ani.session.char["id"])[1] == "member"
    assert cmd(game, ani, "crew_motto", a="x")["text"] == "Only your crew's captain can do that."
    assert cmd(game, budi, "crew_motto", a="")["text"] == "The crew has no motto now."
    # others see the crew when they look at you
    game._move_to(cici.session, budi.session.char["location"], quiet=True)
    assert "Captain of the crew Nova." in cmd(game, cici, "look", a="Budi")["text"]
    assert "Crew: Nova." in cmd(game, cici, "profile", to="Ani")["text"]


# ------------------------------------------------------------
# Points and the board
# ------------------------------------------------------------

def test_members_xp_are_the_crews_points_and_the_board(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi = join(game, "Budi")
    invite_in(game, clock, ani, budi)
    game.award_xp(ani.session, 30)
    game.award_xp(budi.session, 12)
    cici = found(game, clock, "Comet", "Cici")
    game.award_xp(cici.session, 50)
    assert game.store.crew_by_key("nova")["points"] == 42
    board = cmd(game, budi, "crews")["text"]
    assert board == ("The crews with the most points: 1. Comet, 50 points, 1 members; 2. Nova, 42 points, "
                     "2 members. Yours, Nova: 42 points.")
    assert text(game, budi, "crew board")["text"] == board
    dedi = join(game, "Dedi")
    game.award_xp(dedi.session, 99)                         # no crew: no points anywhere
    assert game.store.crew_by_key("comet")["points"] == 50


# ------------------------------------------------------------
# Admins, leaving the game, the database
# ------------------------------------------------------------

def test_admins_can_disband_a_crew(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi = join(game, "Budi")
    invite_in(game, clock, ani, budi)
    rafli = join(game, "Rafli")
    assert cmd(game, ani, "admin", op="crew_disband", a="Nova")["text"] == "Only the station's admins can do that."
    assert cmd(game, rafli, "admin", op="crew_disband", a="Nope")["text"] == "There's no crew called Nope."
    assert text(game, rafli, "disband crew Nova")["text"] == "The crew Nova is disbanded."
    assert budi.sent[-1]["text"] == "The station's admins have disbanded the crew Nova."
    assert game.store.crew_of(ani.session.char["id"]) is None and game.store.crew_by_key("nova") is None
    assert "disband crew" in {row["action"] for row in game.store.admin_log(10)}


def test_invitations_end_when_a_player_leaves(make_game, clock):
    game = make_game()
    ani = found(game, clock)
    budi = join(game, "Budi")
    cmd(game, ani, "crew_invite", to="Budi")
    cmd(game, ani, "bye")
    assert "budi" not in game.crew_invites
    assert cmd(game, budi, "accept")["k"] == "error"


def test_a_version_6_database_gets_the_crew_tables(tmp_path, clock, monkeypatch):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    with monkeypatch.context() as m:
        m.setattr(orbit_store, "SCHEMA_VERSION", 6)
        m.setattr(orbit_store.Store, "_migrate_7", lambda self: None)
        orbit_store.Store(path, clock=clock, iterations=1000, durable=False).close()
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 6
    assert not db.execute("SELECT name FROM sqlite_master WHERE name IN ('crews', 'crew_members')").fetchall()
    db.close()
    store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert store.version() == orbit_store.SCHEMA_VERSION and store.migrated_from == 6
    quila = store.by_name("quilafly")
    assert quila["credits"] == 1234
    crew_id = store.create_crew("Nova", "nova", quila["id"], 1.0)
    assert store.crew_of(quila["id"])[0]["id"] == crew_id
    store.close()
    backup = sqlite3.connect(path + f".before-v{orbit_store.SCHEMA_VERSION}.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 6
    backup.close()
