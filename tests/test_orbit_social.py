# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Orbit 1.6: the room and the people in it, the Nova Realm way (servers/orbit/
# orbit_social.py, orbit_floor.py, orbit_pastimes.py). The ways out (exits, ex)
# a line each; sitting, lying down, sleeping and standing on the rooms'
# furniture, and what the room sees; walking stands you up; "stand" is
# blackjack's only in a hand; following and leading, with a yes; peering next
# door; the new gestures, your own emote, dice, the time, being away; things
# put down, picked up, put on a table, thrown and caught, with their limits;
# the room's own lines; the jukebox and the pond; "again", and a near miss
# answered with "did you mean". Every client reaches them (1.0, 1.4 and 1.6 as
# plain text), and the new content is checked: rooms described, furniture well
# formed, fishing earning less than mining.

import collections
import logging
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
for folder in (SERVER_DIR, EXT_DIR):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import orbit_floor  # noqa: E402
import orbit_parse  # noqa: E402
import orbit_play  # noqa: E402
import orbit_social  # noqa: E402
import orbit_world  # noqa: E402
from tests import orbit_parse_1_0, orbit_parse_1_4, orbit_parse_1_6  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, make_game, secret_of, walk, world  # noqa: E402,F401

CLIENT = orbit_play.CLIENT_NAME


def join_new(game, name, job="pilot", client=CLIENT):
    conn = FakeConn("en")
    game.hello(conn, {"t": "hello", "v": 1, "lang": "en", "name": name, "job": job, "secret": secret_of(name),
                      "client": client})
    return conn


def typed(game, conn, words, reader=orbit_parse.parse):
    """What `conn` gets for typing `words` (the current client unless said): the new events."""
    parsed = reader(words)
    assert parsed is not None and "local" not in parsed, (words, parsed)
    before = len(conn.sent)
    game.receive(conn, dict(parsed, t="cmd"))
    return [m for m in conn.sent[before:] if m.get("t") == "ev"]


def said(game, conn, words):
    """The last line `conn` got for typing `words` (an achievement it happened to earn aside)."""
    got = [m for m in typed(game, conn, words) if m.get("sound") != "achievement"]
    return got[-1]


def put(game, *conns, room):
    for conn in conns:
        conn.session.char["location"] = room


def since(conn, count):
    return [m.get("text") for m in conn.sent[count:] if m.get("t") == "ev"]


@pytest.fixture
def three(make_game):
    game = make_game()
    ani, maya, sam = join_new(game, "Ani"), join_new(game, "Maya"), join_new(game, "Sam")
    put(game, ani, maya, sam, room="cantina")
    for conn in (ani, maya, sam):
        conn.session.char["credits"] = 1000
    return game, ani, maya, sam


# ------------------------------------------------------------
# The ways out
# ------------------------------------------------------------

def test_exits_a_line_each_in_compass_order_with_where_they_lead(make_game):
    game = make_game()
    ani = join_new(game, "Ani")
    put(game, ani, room="service")
    got = said(game, ani, "exits")
    assert got["lines"] == ["Exits from the Service Corridor:", "East: Engineering", "South: the Lower Lift Lobby",
                            "Southwest: the Maintenance Junction (locked, dark)", "West: the Cargo Bay"]
    assert got["text"] == ("Exits from the Service Corridor: East: Engineering; South: the Lower Lift Lobby; "
                           "Southwest: the Maintenance Junction (locked, dark); West: the Cargo Bay.")
    assert said(game, ani, "ex")["lines"] == got["lines"]                        # the short word
    for room, line in (("park", "Down: the Service Corridor (one way)"),
                       ("airlock", "South: the Hull Walkway (vacuum: an EVA suit)"),
                       ("cabins_hall", "South: your cabin (private)"),
                       ("hangar", "North: the Crew Hangar (crew only)"),
                       ("dock", "Ride the Wombat: to the Belt Platform")):
        put(game, ani, room=room)
        assert line in said(game, ani, "exits")["lines"], room
    ani.session.char["inventory"]["keycard_crew"] = 1
    put(game, ani, room="service")
    assert "Southwest: the Maintenance Junction (dark)" in said(game, ani, "exits")["lines"]


def test_exits_in_the_dark_and_the_way_nobody_has_found(make_game):
    game = make_game()
    ani = join_new(game, "Ani")
    char = ani.session.char
    char["inventory"].update(keycard_crew=1)
    walk(game, ani, "maint_1")
    assert said(game, ani, "exits")["text"] == "It's too dark to see the exits. You can feel your way back: northeast."
    char["location"], char["stats"]["back"] = "maint_3", None
    assert said(game, ani, "exits")["text"] == \
        "It's too dark to see the exits, and you can't tell which way you came in."
    char["inventory"]["headlamp"] = 1
    game.worn(char)["head"] = "headlamp"
    assert "South: a way you haven't explored yet" in said(game, ani, "exits")["lines"]
    char["stats"]["map"].append("secret")
    assert "South: the Time Capsule Room (locked)" in said(game, ani, "exits")["lines"]   # a brass key opens it


def test_exits_reach_the_server_from_every_client_and_old_ones_get_one_line(make_game):
    game = make_game()
    old = join_new(game, "Olda", client="Hariku Orbit 1.5")
    for reader in (orbit_parse_1_0.parse, orbit_parse_1_4.parse, orbit_parse_1_6.parse, orbit_parse.parse):
        for words in ("exits", "ex"):
            got = [m for m in typed(game, old, words, reader) if m["k"] == "info"][-1]
            assert got["text"].startswith("Exits from the Dock: North: the Mineral Exchange; ") and "lines" not in got


# ------------------------------------------------------------
# Sitting, lying down, sleeping, standing
# ------------------------------------------------------------

def test_sitting_on_the_furniture_the_room_sees_it_and_a_look_shows_it(three):
    game, ani, maya, sam = three
    count = len(maya.sent)
    got = said(game, ani, "sit")
    assert got["text"] == "You sit down on a bar stool." and got["k"] == "info" and got["sound"] == "equip"
    assert since(maya, count) == ["Ani sits down on a bar stool."]
    assert maya.sent[-1]["actor"] == "Ani" and maya.sent[-1]["k"] == "emote"
    lines = said(game, maya, "look")["lines"]
    assert "Here: Ani the pilot and Sam the pilot." in lines and "Ani is sitting on a bar stool." in lines
    assert said(game, ani, "sit")["text"] == "You're already sitting on a bar stool."
    assert said(game, ani, "look")["lines"][-1] == "You're sitting on a bar stool."
    assert "Ani is sitting on a bar stool." in said(game, maya, "look at Ani")["lines"]
    count = len(maya.sent)
    assert said(game, ani, "stand")["text"] == "You stand up."
    assert since(maya, count) == ["Ani stands up."]
    assert said(game, ani, "stand up")["text"] == "You're already standing."
    assert said(game, ani, "get up")["text"] == "You're already standing."          # the client reads it as take


def test_the_named_seat_the_floor_and_what_cant_be_sat_on(three):
    game, ani, maya, _sam = three
    assert said(game, ani, "sit on the booth")["text"] == "You sit down in the corner booth."
    assert said(game, ani, "lie on the booth")["text"] == "You lie down along the booth's bench."
    assert said(game, ani, "lie on a bar stool")["text"] == "You can't lie down on a bar stool."
    assert said(game, ani, "sit on the jukebox")["text"] == "You can't sit on the jukebox."
    assert said(game, ani, "sit on the sofa")["text"] == "There's no sofa here to sit on."
    assert said(game, ani, "sit on Maya")["text"] == "You can't sit on Maya!"
    assert said(game, ani, "sit on the floor")["text"] == "You sit down on the floor."
    put(game, ani, room="park")
    assert said(game, ani, "lie down")["text"] == "You lie down on the lawn in the sun lamps."
    put(game, ani, room="kar_flats")                                     # no furniture: the ground's own words
    assert said(game, ani, "sit")["text"] == "You sit down on the sand."
    put(game, ani, room="ferry")
    assert said(game, ani, "sit")["text"] == "You sit down on a bench seat by a porthole."


def test_a_seat_holds_so_many(make_game):
    game = make_game()
    people = [join_new(game, name) for name in ("Ana", "Bea", "Cid", "Dot")]
    put(game, *people, room="reading_room")
    assert said(game, people[0], "sit in armchair")["text"] == "You sit down in an armchair under the lamp."
    assert said(game, people[1], "sit on armchairs")["text"] == "You sit down in an armchair under the lamp."
    assert said(game, people[2], "sit in an armchair")["text"] == "Both armchairs are taken."
    assert said(game, people[2], "sit")["text"] == "You sit down on the floor."       # the only seats are full


def test_lying_down_sleeping_and_waking(three):
    game, ani, maya, sam = three
    count = len(maya.sent)
    assert said(game, ani, "sleep")["text"] == \
        "You lie down along the booth's bench, close your eyes and drift off to sleep."
    assert since(maya, count) == ["Ani lies down along the booth's bench and falls asleep."]
    assert "Ani is asleep along the booth's bench." in said(game, maya, "look")["lines"]
    assert "Ani the pilot, in the Cantina (asleep)" in said(game, maya, "who")["lines"]
    assert said(game, ani, "sleep")["text"] == "You're already asleep along the booth's bench."
    said(game, ani, "look")                                                     # looking doesn't wake you
    assert game.pose_of(ani.session)["kind"] == "sleep"
    # Someone wakes you gently; you stay lying there.
    count, sam_count = len(ani.sent), len(sam.sent)
    assert said(game, maya, "wake Ani")["text"] == "You gently wake Ani."
    assert since(ani, count) == ["Maya gently wakes you."] and since(sam, sam_count) == ["Maya gently wakes Ani."]
    assert game.pose_of(ani.session)["kind"] == "lie"
    assert said(game, maya, "wake Ani")["text"] == "Ani isn't asleep."
    # Doing something wakes a sleeper first.
    said(game, ani, "sleep")
    count = len(maya.sent)
    got = typed(game, ani, "say good morning")
    assert [m["text"] for m in got] == ["You wake up.", "You say: good morning"]
    assert since(maya, count) == ["Ani wakes up.", "Ani says: good morning"]
    said(game, ani, "sleep")
    assert said(game, ani, "wake")["text"] == "You wake up and get to your feet."
    assert game.pose_of(ani.session) is None
    assert said(game, ani, "wake")["text"] == "You're not asleep. Type stand to get up."


def test_walking_stands_you_up_first_and_both_rooms_hear_it(three):
    game, ani, maya, sam = three
    walk(game, maya, "promenade_west")
    said(game, ani, "sit")
    count, sam_count = len(ani.sent), len(sam.sent)
    moved = said(game, ani, "e")
    assert moved["k"] == "moved" and moved["lines"][0] == "You stand up and walk east to the West Promenade."
    assert since(sam, sam_count) == ["Ani gets up.", "Ani heads east, to the West Promenade."]
    assert maya.sent[-1]["text"] == "Ani arrives from the west." and maya.sent[-1]["dir"] == "w"
    assert game.pose_of(ani.session) is None and len(ani.sent) > count
    said(game, ani, "sleep")
    moved = said(game, ani, "w")
    assert moved["lines"][:2] == ["You wake up and get to your feet.", "You walk west to the Cantina."]
    said(game, ani, "sit")
    assert said(game, ani, "u")["text"].startswith("You can't go up from here.")      # a wall: still sitting
    assert game.pose_of(ani.session)["kind"] == "sit"


def test_stand_is_blackjacks_only_in_a_hand(three, monkeypatch):
    game, ani, _maya, _sam = three
    put(game, ani, room="casino")
    for reader in (orbit_parse_1_0.parse, orbit_parse_1_4.parse, orbit_parse_1_6.parse, orbit_parse.parse):
        said(game, ani, "sit")
        got = typed(game, ani, "stand", reader)
        assert got[-1]["text"] == "You stand up.", reader                           # no hand: the posture
    cards = iter([10, 7, 10, 8])
    monkeypatch.setattr(game, "_card", lambda: next(cards))
    said(game, ani, "sit on a stool")
    assert said(game, ani, "blackjack 50")["text"].startswith("Blackjack for 50 credits.")
    got = typed(game, ani, "stand")
    assert got[-1]["text"] == "You have 17, the dealer has 18 (10 and 8). You lose. You have 950."
    assert game.pose_of(ani.session)["kind"] == "sit"                               # still on the stool
    assert said(game, ani, "stand up")["text"] == "You stand up."


# ------------------------------------------------------------
# Following and leading
# ------------------------------------------------------------

def test_follow_with_a_yes_and_walk_a_step_behind(three):
    game, ani, maya, sam = three
    walk(game, sam, "promenade_west")
    assert said(game, ani, "follow Maya")["text"] == "You ask Maya if you may follow them."
    ask = maya.sent[-1]
    assert ask["text"] == "Ani would like to follow you. Type accept or decline." and ask["ask"] and ask["k"] == "offer"
    assert said(game, maya, "accept")["text"] == "Ani is following you now. Type stop leading to go on alone."
    assert ani.sent[-1]["text"].startswith("You're following Maya now")
    count_a, count_s = len(ani.sent), len(sam.sent)
    moved = said(game, maya, "e")
    assert moved["k"] == "info" and moved["text"] == "Ani follows you."
    mine = [m for m in ani.sent[count_a:] if m["k"] == "moved"][0]
    assert mine["lines"][0] == "You follow Maya east to the West Promenade." and mine["room"] == "promenade_west"
    assert since(sam, count_s) == ["Maya arrives from the west.", "Ani arrives, following Maya."]
    assert game.room_of(ani.session.char) == "promenade_west"
    # Walking off on your own ends it.
    count = len(maya.sent)
    typed(game, ani, "n")
    assert ani.sent[-2]["text"] == "You stop following Maya." or "You stop following Maya." in since(ani, count_a)
    assert "Ani stops following you." in since(maya, count)
    assert ani.session.leader is None


def test_lead_decline_expiry_and_stopping(three, clock):
    game, ani, maya, sam = three
    assert said(game, ani, "lead Maya")["text"] == "You offer to lead Maya."
    assert maya.sent[-1]["text"] == "Ani offers to lead you. Type accept or decline."
    said(game, maya, "decline")
    assert ani.sent[-1]["text"] == "Maya would rather go their own way."
    said(game, ani, "lead Maya")
    clock.advance(orbit_social.FOLLOW_SECONDS + 1)
    game.tick()
    assert ani.sent[-1]["text"] == "Maya didn't answer." and not game.follow_asks
    said(game, ani, "lead Sam")
    said(game, sam, "accept")
    assert sam.session.leader == "ani"
    assert said(game, sam, "lead Maya")["text"] == "You're following Ani: stop following first."
    assert said(game, maya, "follow Sam")["text"] == "Sam is following someone already."
    assert said(game, ani, "follow Maya")["text"] == "People are following you: stop leading first."
    assert said(game, ani, "stop leading")["text"] == "You stop leading Sam."
    assert sam.sent[-1]["text"] == "Ani stops leading you. You're on your own again."
    assert said(game, ani, "stop leading")["text"] == "Nobody is following you."
    assert said(game, sam, "unfollow")["text"] == "You're not following anyone."
    said(game, ani, "lead Sam")
    said(game, sam, "accept")
    assert said(game, sam, "disband")["text"] == "You stop following Ani."
    assert said(game, ani, "follow Ani")["text"] == "You can't follow yourself."
    assert said(game, ani, "follow Zed")["text"] == "Zed isn't here."


def test_a_leader_through_a_door_the_follower_cant_pass_or_leaving(make_game):
    game = make_game()
    ani, maya = join_new(game, "Ani"), join_new(game, "Maya")
    put(game, ani, maya, room="service")
    ani.session.char["inventory"].update(keycard_crew=1, headlamp=1)
    said(game, maya, "follow Ani")
    said(game, ani, "accept")
    said(game, ani, "sw")                                      # a crew door Maya has no keycard for
    assert game.room_of(maya.session.char) == "service" and maya.session.leader is None
    assert maya.sent[-1]["text"] == "Ani goes southwest, where you can't follow; you stop following."
    said(game, ani, "ne")
    said(game, maya, "follow Ani")
    said(game, ani, "accept")
    count = len(maya.sent)
    game.receive(ani, {"t": "cmd", "c": "bye"})
    assert maya.session.leader is None and "Ani has gone, so you stop following." in since(maya, count)


# ------------------------------------------------------------
# Peering next door
# ------------------------------------------------------------

def test_peer_glimpses_the_next_room_and_who_is_there(three):
    game, ani, maya, sam = three
    walk(game, sam, "promenade_west")
    said(game, sam, "sit")
    count = len(maya.sent)
    got = said(game, ani, "peer east")
    assert got["lines"][0] == "You peer east." and got["lines"][1] == "West Promenade"
    assert got["lines"][2].startswith("The quieter end of the Promenade")
    assert "There: Sam, sitting." in got["lines"]
    assert since(maya, count) == ["Ani peers east."]
    assert said(game, ani, "peer north")["text"] == "There's nothing to the north. Exits: east, west."
    assert said(game, ani, "peer")["text"] == "Peer which way? For example: peer north."
    put(game, ani, room="cabins_hall")
    assert said(game, ani, "peer south")["lines"][1] == "To the south: your cabin, behind a private door."
    ani.session.char["inventory"]["keycard_crew"] = 1
    assert said(game, ani, "peer down")["lines"][1] == "It's too dark to make anything out to the down."


# ------------------------------------------------------------
# Gestures, your own emote, dice, the time, being away
# ------------------------------------------------------------

def test_the_new_gestures_with_and_without_someone(three):
    game, ani, maya, sam = three
    count_m, count_s = len(maya.sent), len(sam.sent)
    got = said(game, ani, "kiss Maya")
    assert got["text"] == "You kiss Maya on the cheek." and got["emote"] == "kiss" and got["sound"] == "emote_hug"
    assert since(maya, count_m) == ["Ani kisses you on the cheek."]
    assert since(sam, count_s) == ["Ani kisses Maya on the cheek."] and sam.sent[-1]["sound"] == "emote_hug"
    for words, line in (("wink", "You wink."), ("wink at Sam", "You wink at Sam."),
                        ("high five Maya", "You high five Maya!"), ("hi5 Sam", "You high five Sam!"),
                        ("thank you", "You say thank you."), ("thanks Maya", "You thank Maya."),
                        ("giggle", "You giggle."), ("shake hands with Sam", "You shake hands with Sam."),
                        ("poke Maya", "You poke Maya."), ("yawn", "You yawn widely."),
                        ("salute", "You salute smartly.")):
        game.sessions["ani"].chat.tokens = 5
        assert said(game, ani, words)["text"] == line, words
    assert said(game, ani, "cry wolf")["text"].startswith('I don\'t understand "cry wolf".')   # a sentence
    assert said(game, ani, "wink at Budi")["text"].startswith('I don\'t understand')
    game.sessions["ani"].chat.tokens = 5
    got = typed(game, ani, "high five Rocco")                                   # a resident answers
    assert [m["text"] for m in got] == ["You high five Rocco!", "Rocco high fives you back, with a satisfying smack!"]


def test_every_gesture_is_complete_and_residents_answer_each(world):
    texts = __import__("orbit_lang").Texts()
    for eid, emote in world.emotes.items():
        assert set(emote["en"]) == {"you", "they", "you_at", "they_at", "at_you"}, eid
        assert texts.has(f"npc_react_{eid}") and texts.has(f"npc_react_{eid}_other"), eid
    assert len(world.emotes) >= 25


def test_emote_in_your_own_words(three):
    game, ani, maya, _sam = three
    count = len(maya.sent)
    got = said(game, ani, "emote waves at everyone")
    assert got["text"] == "Ani waves at everyone." and got["k"] == "emote"
    assert since(maya, count) == ["Ani waves at everyone."] and maya.sent[-1]["actor"] == "Ani"
    game.sessions["ani"].chat.tokens = 5
    assert said(game, ani, ":grins!")["text"] == "Ani grins!"
    assert said(game, ani, "emote")["text"] == "Emote what? For example: emote waves hello, or :waves hello."


def test_dice_for_the_room_fair_and_in_the_log(three, caplog):
    game, ani, maya, _sam = three
    caplog.set_level(logging.INFO, logger="orbit.game")
    for words, dice in (("roll", "2 dice"), ("roll 3d6", "3 dice"), ("roll d20", "a 20-sided die"),
                        ("roll a die", "a die"), ("roll 2d10", "2 dice of 10 sides")):
        game.sessions["ani"].chat.tokens = 5
        count = len(maya.sent)
        got = said(game, ani, words)
        assert got["text"].startswith(f"You roll {dice}: ") and got["sound"] == "dice", words
        assert since(maya, count)[-1].startswith(f"Ani rolls {dice}: ")
    assert "Ani rolled 1d6" in caplog.text and "Ani rolled 2d6" in caplog.text
    assert said(game, ani, "roll 50d6")["text"].startswith("Roll how?")
    rolls = collections.Counter()
    for _ in range(600):
        count, sides = game._dice("d6")
        rolls[game.rng.randint(1, sides)] += 1
    assert set(rolls) == {1, 2, 3, 4, 5, 6} and min(rolls.values()) > 60
    put(game, ani, room="casino")                          # a bet: the casino's dice
    assert "You bet 20 on low" in said(game, ani, "roll 20 low")["text"]


def test_the_time_on_the_station_and_on_another_world(make_game, clock):
    game = make_game()
    ani = join_new(game, "Ani")
    got = said(game, ani, "time")
    assert got["lines"][0] == "Station time: 12:30 UTC, Friday 25 September 2026."
    put(game, ani, room="kar_plaza")
    local = said(game, ani, "time")["lines"][1]
    assert local.startswith("Local time on Karmina: ") and "A day there lasts 24 hours 39 minutes." in local


def test_away_from_the_keyboard(three):
    game, ani, maya, _sam = three
    count = len(maya.sent)
    assert said(game, ani, "afk making tea")["text"] == \
        "You're away from the keyboard: making tea. Any command brings you back."
    assert since(maya, count) == ["Ani steps away from the keyboard: making tea."]
    assert "Ani the pilot, in the Cantina (away from the keyboard)" in said(game, maya, "who")["lines"]
    assert "Ani is away from the keyboard: making tea." in said(game, maya, "look")["lines"]
    assert said(game, maya, "whisper Ani back soon?")["text"] == \
        "Ani is away from the keyboard (making tea), and may answer later."
    count = len(maya.sent)
    got = typed(game, ani, "look")
    assert got[0]["text"] == "Welcome back." and since(maya, count) == ["Ani is back."]
    assert ani.session.afk is None


# ------------------------------------------------------------
# Things put down, picked up, thrown and caught
# ------------------------------------------------------------

def test_drop_look_and_pick_up(three):
    game, ani, maya, sam = three
    ani.session.char["inventory"]["coffee"] = 3
    count = len(maya.sent)
    got = said(game, ani, "drop 2 coffee")
    assert got["text"] == "You drop 2 sacks of coffee." and got["sound"] == "bump"
    assert since(maya, count) == ["Ani drops 2 sacks of coffee."]
    assert "On the floor: 2 sacks of coffee." in said(game, maya, "look")["lines"]
    looked = said(game, maya, "look at coffee")["lines"]
    assert looked[-1] == "2 sacks of coffee, put down here by Ani. get picks it up."
    assert "get coffee: pick up what lies here: 2 sacks of coffee" in said(game, maya, "x here")["lines"]
    count = len(sam.sent)
    for reader in (orbit_parse_1_0.parse, orbit_parse.parse):
        assert reader("pick up coffee")["c"] == "take"
    got = said(game, maya, "pick up 1 coffee")
    assert got["text"] == "You pick up 1 sack of coffee."
    assert since(sam, count) == ["Maya picks up 1 sack of coffee."]
    assert said(game, sam, "take coffee")["text"] == "You pick up 1 sack of coffee."
    assert game.floor.get("cantina") in (None, [])
    assert maya.session.char["inventory"]["coffee"] == 1 and ani.session.char["inventory"]["coffee"] == 1
    assert said(game, ani, "put down coffee")["text"] == "You drop 1 sack of coffee."


def test_what_cant_be_put_down_and_where(three):
    game, ani, _maya, _sam = three
    char = ani.session.char
    assert said(game, ani, "drop compass")["text"].endswith("can't be put down: they're yours alone.")
    char["inventory"]["batik_shirt"] = 1
    game.worn(char)["body"] = "batik_shirt"
    assert said(game, ani, "drop rocket-print shirt")["text"] == \
        "You're wearing the rocket-print shirt: take it off first."
    char["inventory"]["coffee"] = 1
    put(game, ani, room="ferry")
    assert said(game, ani, "drop coffee")["text"].startswith("Better not")
    put(game, ani, room="hull_walk")
    assert said(game, ani, "drop coffee")["text"] == "Not out here: it would drift off into space."


def test_the_litter_limits(make_game):
    game = make_game()
    ani, maya = join_new(game, "Ani"), join_new(game, "Maya")
    ani.session.char["inventory"].update({g: 1 for g in ("coffee", "spices", "tomato", "chilli", "iron",
                                                         "nickel", "scrap")})
    for good in ("coffee", "spices", "tomato", "chilli", "iron", "nickel"):
        ani.session.econ.tokens = 6
        assert said(game, ani, f"drop {good}")["text"].startswith("You drop "), good
    ani.session.econ.tokens = 6
    assert said(game, ani, "drop scrap")["text"] == \
        "You already have 6 piles of things lying about the station. Pick some up first."
    maya.session.char["inventory"].update(kerupuk=20)
    for n in range(orbit_floor.FLOOR_ROOM - orbit_floor.FLOOR_PLAYER):
        game.floor["dock"].append({"id": "kerupuk", "n": 1, "by": f"someone{n}", "by_name": "Someone",
                                   "at": game.now(), "on": None})
    maya.session.econ.tokens = 6
    assert said(game, maya, "drop crackers")["text"] == "There's no room to put anything else down here."


def test_goods_on_the_floor_still_count_in_your_bag(make_game):
    game = make_game()
    ani = join_new(game, "Ani")
    bag = game.bag_size(ani.session.char)
    ani.session.char["inventory"]["coffee"] = bag
    said(game, ani, "drop 10 coffee")
    assert game._goods_count(ani.session.char) == bag                # dropped, but not a way round the bag
    put(game, ani, room="spice_market")
    assert said(game, ani, "buy 1 coffee")["text"] == f"Your bag holds at most {bag} goods."


def test_put_on_a_table_and_take_it_back(three):
    game, ani, maya, _sam = three
    ani.session.char["inventory"]["iced_coffee"] = 2
    count = len(maya.sent)
    assert said(game, ani, "put iced coffee on the bar")["text"] == "You put 1 iced coffee on the bar."
    assert since(maya, count) == ["Ani puts 1 iced coffee on the bar."]
    assert "On the bar: 1 iced coffee." in said(game, maya, "look")["lines"]
    assert said(game, ani, "put iced coffee on the jukebox")["text"] == "You can't put things on the jukebox."
    assert said(game, ani, "put iced coffee on the moon")["text"] == "There's no moon here to put things on."
    assert said(game, ani, "put iced coffee")["text"] == "You drop 1 iced coffee."                # no holder: dropped
    assert said(game, maya, "get iced coffee from the bar")["text"] == "You take 1 iced coffee from the bar."
    assert "Ani" not in said(game, maya, "look")["text"].split("Things to look at")[0].split("Here:")[0]


def test_things_left_lying_go_back_to_their_owner_and_survive_a_restart(make_game, clock, tmp_path):
    path = str(tmp_path / "floor.db")
    game = make_game(path)
    ani, maya = join_new(game, "Ani"), join_new(game, "Maya")
    ani.session.char["inventory"].update(coffee=2, kerupuk=1)
    said(game, ani, "drop 2 coffee")
    said(game, maya, "sit")
    game.receive(ani, {"t": "cmd", "c": "bye"})
    game.shutdown()
    again = make_game(path)                                          # a restart: still on the floor
    maya = join_new(again, "Maya")
    assert "On the floor: 2 sacks of coffee." in said(again, maya, "look")["lines"]
    assert again.pose_of(maya.session) is None                      # postures aren't kept
    clock.advance(orbit_floor.FLOOR_SECONDS + 1)
    again.tick()
    assert not again.floor
    assert again.store.by_name("ani")["inventory"]["coffee"] == 2   # back with Ani, who was away
    ani = join_new(again, "Ani")
    said(again, ani, "drop crackers")
    clock.advance(orbit_floor.FLOOR_SECONDS + 1)
    again.tick()
    assert ani.sent[-1]["text"] == \
        "A cleaning drone hums up and hands back what you left lying about: 1 bag of prawn crackers."


def test_throw_and_catch(three, clock):
    game, ani, maya, sam = three
    ani.session.char["inventory"]["kerupuk"] = 2
    count_m, count_s = len(maya.sent), len(sam.sent)
    assert said(game, ani, "throw prawn crackers to Maya")["text"] == \
        "You throw the bag of prawn crackers to Maya."
    assert since(maya, count_m) == ["Ani throws the bag of prawn crackers to you! Type catch, quick!"]
    assert since(sam, count_s) == ["Ani throws the bag of prawn crackers to Maya! Anyone could catch it."]
    assert said(game, sam, "catch")["text"] == "You catch the bag of prawn crackers!"      # anyone may
    assert maya.sent[-1]["text"] == "Sam catches the bag of prawn crackers."
    assert said(game, maya, "catch")["text"].startswith("There's nothing")                  # nothing flies now
    said(game, ani, "throw crackers to Maya")
    clock.advance(orbit_floor.THROW_SECONDS + 1)
    game.tick()
    assert maya.sent[-1]["text"] == "Nobody catches it: the bag of prawn crackers lands on the floor."
    assert "On the floor: 1 bag of prawn crackers." in said(game, maya, "look")["lines"]
    assert said(game, ani, "throw crackers to Ani")["text"].startswith("You can't throw things to yourself")


def test_undress(three):
    game, ani, _maya, _sam = three
    char = ani.session.char
    char["inventory"]["batik_shirt"] = 1
    game.worn(char)["body"] = "batik_shirt"
    assert said(game, ani, "undress")["text"] == "You take off rocket-print shirt."
    assert said(game, ani, "undress")["text"] == "You're not wearing any clothes or titles to take off."


# ------------------------------------------------------------
# Again, and the near misses
# ------------------------------------------------------------

def test_again_repeats_the_last_command_and_near_misses_get_a_hint(three):
    game, ani, _maya, _sam = three
    assert said(game, ani, "again")["text"] == "There's no command to repeat yet."
    said(game, ani, "exits")
    assert said(game, ani, "again")["text"].startswith("Exits from the Cantina: ")
    assert said(game, ani, "!")["text"].startswith("Exits from the Cantina: ")
    ani.session.char["inventory"]["kerupuk"] = 3
    said(game, ani, "drop crackers")
    ani.session.econ.tokens = 6
    assert said(game, ani, "again")["text"] == "You drop 1 bag of prawn crackers."
    assert orbit_parse_1_6.parse("again") == {"local": "repeat"}           # an older client: the last message
    put(game, ani, room="dock")
    for word, meant in (("exist", "exits"), ("jukbox", "jukebox"), ("inventori", "inventory")):
        assert said(game, ani, word)["text"] == \
            f'I don\'t understand "{word}". Did you mean {meant}? Type help for the commands.', word
    assert said(game, ani, "flibber")["text"] == 'I don\'t understand "flibber". Type help for the commands.'


# The new commands from every client: 1.0, 1.4 and 1.6 send them as plain text.
PHRASEBOOK_16 = [
    ("exits", "exits"), ("ex", "exits"), ("sit", "sit"), ("sit on the bar stool", "sit"), ("lie down", "lie"),
    ("sleep", "sleep"), ("wake", "wake"), ("stand up", "stand_up"), ("peer east", "peer"), ("follow Sari", "follow"),
    ("lead Sari", "lead"), ("stop following", "follow"), ("emote waves", "pose"), ("roll 2d6", "roll"),
    ("time", "time"), ("afk", "afk"), ("drop coffee", "drop"), ("put coffee on the bar", "put"),
    ("throw coffee to Sari", "throw"), ("kiss Sari", "emote"), ("high five Sari", "emote"), ("jukebox", "jukebox"),
    ("fish", "fish"), ("undress", "undress"),
]


@pytest.mark.parametrize("reader", [orbit_parse_1_0.parse, orbit_parse_1_4.parse, orbit_parse_1_6.parse,
                                    orbit_parse.parse])
@pytest.mark.parametrize("text, handler", PHRASEBOOK_16)
def test_every_client_reaches_the_new_commands(make_game, reader, text, handler):
    game = make_game()
    calls = []

    def wrap(name, fn):
        def run(self, session, message):
            calls.append(name)
            return fn(self, session, message)
        return run

    game.COMMANDS = {name: wrap(name, fn) for name, fn in type(game).COMMANDS.items()}
    tono, sari = join_new(game, "Tono"), join_new(game, "Sari")
    put(game, tono, sari, room="cantina")
    tono.session.char["inventory"]["coffee"] = 2
    parsed = reader(text)
    assert parsed is not None and "local" not in parsed, parsed
    game.receive(tono, dict(parsed, t="cmd"))
    assert handler in calls, (text, parsed, calls)
    last = tono.sent[-1]
    assert last["t"] == "ev" and last["text"] and "understand" not in last["text"], last


# ------------------------------------------------------------
# The rooms' own lives, the jukebox and the pond
# ------------------------------------------------------------

def test_a_room_says_a_line_of_its_own_now_and_then_never_mid_chat(make_game, clock):
    game = make_game()
    ani = join_new(game, "Ani")
    put(game, ani, room="willow_nook")
    lines = game.world.locations["willow_nook"]["ambient"]["en"]
    heard = []
    for _ in range(12):
        clock.advance(1000)
        count = len(ani.sent)
        game.tick()
        heard.extend(m["text"] for m in ani.sent[count:] if m.get("ambient"))
    assert heard and set(heard) <= set(lines)
    assert all(a != b for a, b in zip(heard, heard[1:]))                  # never the same line twice running
    typed(game, ani, "say hello")
    game.ambient_next["willow_nook"] = game.now()
    count = len(ani.sent)
    game.tick()
    assert not [m for m in ani.sent[count:] if m.get("ambient")]          # players talked a moment ago


def test_the_jukebox_plays_for_the_room(three, clock):
    game, ani, maya, _sam = three
    songs = said(game, ani, "jukebox")["lines"]
    assert songs[0].startswith("The jukebox: 2 credits a song.") and songs[1] == "1. Moonlight Swing"
    count = len(maya.sent)
    got = said(game, ani, "jukebox 2")
    assert got["k"] == "paid" and got["text"].startswith("You drop 2 credits in the jukebox and pick Neon Horizon.")
    assert ani.session.char["credits"] == 998
    assert since(maya, count)[-1].startswith("Ani drops a coin in the jukebox and picks Neon Horizon.")
    assert said(game, maya, "pick song moonlight")["text"].startswith("Neon Horizon is still playing")
    clock.advance(61)
    assert said(game, maya, "play song moonlight")["text"].startswith("You drop 2 credits in the jukebox and pick "
                                                                        "Moonlight Swing.")
    assert said(game, maya, "jukebox 99")["text"].startswith("The jukebox has no song called 99.")
    assert game.ambient_line("cantina", "The jukebox plays {song}.") == "The jukebox plays Moonlight Swing."
    put(game, ani, room="dock")
    assert said(game, ani, "jukebox")["text"] == "The jukebox is in the Cantina."
    assert said(game, ani, "look at jukebox")["text"] == "The jukebox is in the Cantina."
    assert said(game, ani, "read logbook")["text"] == "You don't see logbook here. There's one in the Reading Room."
    assert said(game, ani, "look at the willow")["text"] == \
        "You don't see the willow here. There's one in Willow Nook."
    assert said(game, ani, "look at bench")["text"] == "You don't see bench here."          # many: none named


def test_fishing_at_the_pond(make_game, clock):
    game = make_game()
    ani, maya = join_new(game, "Ani"), join_new(game, "Maya")
    assert said(game, ani, "fish")["text"] == "There's nowhere to fish here. The pond is in Willow Nook."
    put(game, ani, maya, room="willow_nook")
    assert said(game, ani, "reel")["text"].startswith("Your line isn't in the water.")
    count = len(maya.sent)
    assert said(game, ani, "cast a line")["text"].startswith("You borrow a rod from the rack")
    assert since(maya, count) == ["Ani casts a line into the pond."]
    assert said(game, ani, "fish")["text"].startswith("Your line is already in the water.")
    assert said(game, ani, "reel")["text"].startswith("Nothing was biting yet")          # too early
    clock.advance(5)
    caught = 0
    for _ in range(20):
        ani.session.econ.tokens = 6
        said(game, ani, "fish")
        count = len(ani.sent)
        clock.advance(31)
        game.tick()
        assert "A tug on the line! Type reel, quick!" in since(ani, count)
        got = said(game, ani, "reel in")
        assert got["k"] == "paid", got
        caught += 1
        clock.advance(4)
    fish = sum(ani.session.char["inventory"].get(f, 0) for f in ("perch", "carp", "trout"))
    assert fish <= caught and fish >= caught - 3
    said(game, ani, "fish")
    count = len(ani.sent)
    clock.advance(31)
    game.tick()
    clock.advance(6)
    game.tick()
    assert "The line goes slack: it got away. Type fish to cast again." in since(ani, count)
    ani.session.char["stats"]["fished"] = [game.today(), 30]
    clock.advance(4)
    assert said(game, ani, "fish")["text"].startswith("You've caught 30 fish today")
    put(game, ani, room="spice_market")
    if fish:
        assert said(game, ani, "sell all fish")["k"] == "trade"


def test_fishing_earns_less_than_mining(world):
    econ = world.economy
    rules = econ["fishing"]
    fish = rules["fish"]
    total = sum(f["chance"] for f in fish.values())
    per_fish = sum(world.goods[fid]["base"] * f["chance"] / total for fid, f in fish.items() if not f.get("release"))
    seconds = sum(rules["wait"]) / 2 + 1.5 + rules["cooldown"]
    mining = econ["mining"]["tables"]["platform"]["1"]
    weight = sum(mining.values())
    per_strike = sum(world.goods[g]["base"] * w / weight for g, w in mining.items())
    assert per_fish / seconds < per_strike / econ["mining"]["cooldown"]["1"]
    assert rules["daily"] * max(world.goods[fid]["base"] for fid in fish if fid in world.goods) < 500


def test_the_new_food_is_eaten_with_its_own_words(three):
    game, ani, maya, _sam = three
    assert said(game, ani, "buy hot chocolate")["text"].startswith("You buy 1 mug of hot chocolate")
    count = len(maya.sent)
    got = said(game, ani, "drink hot chocolate")
    assert got["text"].startswith("You sip the hot chocolate.") and got["sound"] == "gulp"
    assert since(maya, count) == ["Ani sips a mug of hot chocolate."]
    for room, sid in (("bazaar_cafe", "tea_house"), ("lumina_boulevard", "noodle_stall"),
                      ("glasir_lodge", "lodge_kitchen"), ("food_court", "food")):
        put(game, ani, room=room)
        assert game.shop_here(ani.session.char)[0] == sid
        stock = game.world.shops[sid]["stock"]
        listed = said(game, ani, "list")
        assert listed["k"] == "info" and game.world.things[stock[-1]]["one"]["en"] in listed["text"], room


# ------------------------------------------------------------
# The content
# ------------------------------------------------------------

def test_every_room_has_things_to_look_at_and_the_furniture_is_well_made(world):
    for lid, loc in world.locations.items():
        if loc.get("hidden"):
            continue
        objects = loc.get("objects") or {}
        assert len(objects) >= 2, lid
        for oid, obj in objects.items():
            live = any(obj.get(k) for k in ("markets", "worlds", "arcade", "earth", "farm"))   # said live
            assert obj["names"]["en"] and (live or len(obj["desc"]["en"]) > 30), (lid, oid)
            seat = obj.get("seat")
            if seat:
                assert int(seat["n"]) >= 1 and seat["at"]["en"].split()[0] in ("on", "in", "at", "by", "under",
                                                                               "cross-legged", "among"), (lid, oid)
            if obj.get("holds"):
                assert int(obj["holds"]) >= 1 and obj["holds_at"]["en"].split()[0] in ("on", "in"), (lid, oid)
        for line in (loc.get("ambient") or {}).get("en", []):
            assert isinstance(line, str) and line.endswith((".", "!")), (lid, line)
    seats = sum(1 for loc in world.locations.values() for o in (loc.get("objects") or {}).values() if o.get("seat"))
    assert seats >= 40
    assert sum(1 for loc in world.locations.values() if loc.get("ambient")) >= 25


def test_the_new_rooms_are_on_the_map_both_ways(world):
    for lid, back in (("willow_nook", "park"), ("crew_lounge", "cabins_hall"), ("reading_room", "archive"),
                      ("gallery", "gate_hall"), ("terrace", "food_court")):
        assert lid in world.reachable()
        assert world.route(world.start, lid) and world.route(lid, world.start), lid
        assert any(ex["to"] == back for _d, ex in world.neighbours(lid))


def test_whats_new_in_1_6_once(make_game):
    game = make_game()
    rafli = join_new(game, "Rafli")
    game.sessions["rafli"].char["stats"]["seen_version"] = "1.5"
    game.receive(rafli, {"t": "cmd", "c": "bye"})
    text = join_new(game, "Rafli").sent[1]["text"]
    assert "New in Orbit 1.6: sit, lie down, sleep and stand" in text and "New in Orbit 1.5" not in text
    game.receive(game.sessions["rafli"].conn, {"t": "cmd", "c": "bye"})
    assert "New in Orbit" not in join_new(game, "Rafli").sent[1]["text"]


def test_help_social(make_game):
    game = make_game()
    ani = join_new(game, "Ani")
    game.receive(ani, {"t": "cmd", "c": "help", "a": "social"})         # the client passes the topic on
    assert orbit_parse.parse("help social") == {"local": "help", "topic": "social"}
    lines = ani.sent[-1]["lines"]
    assert lines[0].startswith("The room and its people: exits (or ex)") and any("again (or !)" in l for l in lines)
    assert orbit_world.strip_articles("the floor") in orbit_social.FLOOR_WORDS
