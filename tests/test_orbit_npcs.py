# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The residents (Orbit 1.2): characters who are not players. Their data (in
# English), schedules and walking the map on a fixed clock, the night
# traveller, talking and asking about topics with live answers, unknown and
# locked topics, affinity from talking, topics, gifts and favours, the
# shopkeepers' discount, idle lines that keep quiet while players talk,
# greetings, the honesty rules (never listed as players), and the database's
# migration to schema 8.

import datetime
import json
import os
import random
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_store  # noqa: E402
import orbit_world  # noqa: E402
from tests.test_orbit_economy import _old_database  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, cmd, join, make_game, world  # noqa: E402,F401

UTC = datetime.timezone.utc


def text(game, conn, words):
    game.receive(conn, {"t": "cmd", "c": "text", "a": words})
    return [m for m in conn.sent if m.get("sound") != "achievement"][-1]


def place(game, conn, room):
    conn.session.char["location"] = room
    conn.session.visited.add(room)


def at(clock, hour, minute=0, day=25):
    clock.now = datetime.datetime(2026, 9, day, hour, minute, tzinfo=UTC).timestamp()


def said_by(conn, name):
    return [m for m in conn.sent if m.get("actor") == name and m["k"] in ("say", "emote")]


def memory(game, conn, nid):
    return game.store.npc_memory(nid, conn.session.char["id"])


# ------------------------------------------------------------
# The data
# ------------------------------------------------------------

def test_every_resident_speaks_english_and_can_walk_their_day(world):
    npcs = world.npcs["npcs"]
    assert 10 <= len(npcs) <= 14
    assert {d["kind"] for d in npcs.values()} == {"talker", "resident"}
    worlds = {world.world_of(r) for d in npcs.values() for _h, r in d["schedule"] if r}
    assert {"station", "bazaar", "pixel", "evergrove"} <= worlds          # spread over the worlds
    for nid, d in npcs.items():
        assert 1 <= d["voice"] <= 10 and d["topics"] and d["greet"]["en"] and d["unknown"]["en"]
        for field in ("names", "role", "desc", "greet", "greet_known", "greet_friend", "unknown"):
            assert set(d[field]) == {"en"}, (nid, field)                  # English only
        assert all(set(line) - {"kind", "room"} == {"en"} for line in d["idle"]), nid
        for tid, topic in d["topics"].items():
            assert set(topic["names"]) == {"en"} and (topic.get("favour") or set(topic["say"]) == {"en"}), \
                (nid, tid)
        for _h, room in d["schedule"]:
            if room:
                assert world.npc_route(d["home"], room) is not None, (nid, room)
    voices = [d["voice"] for d in npcs.values() if world.world_of(d["home"]) == "station"]
    assert len(set(voices)) >= 9                                          # they sound apart


def test_a_broken_resident_is_refused(world):
    for change in (lambda n: n["npcs"]["jali"].update(voice=12),
                   lambda n: n["npcs"]["jali"]["greet"]["en"].clear(),                  # no lines
                   lambda n: n["npcs"]["jali"]["topics"]["coffee"].update(say={"id": ["Kopi es."]}),
                   lambda n: n["npcs"]["jali"]["desc"].update(en=""),                   # an empty line
                   lambda n: n["npcs"]["jali"].update(names={"id": ["bang jali"]}),     # no English names
                   lambda n: n["npcs"]["jali"]["topics"]["jukebox"]["names"].pop("en"),
                   lambda n: n["npcs"]["jali"]["favours"][0].update(ask={"id": "Bawakan cabai."}),
                   lambda n: n["npcs"]["jali"].update(schedule=[[0, "nowhere"]]),
                   lambda n: n["npcs"]["jali"]["topics"]["gossip"].update(live="weather"),
                   lambda n: n["npcs"]["harsa"]["favours"][0].update(needs={"unobtainium": 1}),
                   lambda n: n["npcs"]["gino"].update(schedule=[[6, "hull_walk"]])):
        npcs = json.loads(json.dumps(world.npcs))
        change(npcs)
        with pytest.raises(orbit_world.WorldError):
            orbit_world.World(world.data, world.economy, npcs)


# ------------------------------------------------------------
# Honesty: residents are never players
# ------------------------------------------------------------

def test_residents_are_named_apart_from_players(make_game):
    game = make_game()
    tono = join(game, "Tono")
    assert "Residents here: Captain Mateo, the ferry's pilot." in tono.sent[1]["text"]
    assert "Nobody else is here" not in tono.sent[1]["text"]
    who = cmd(game, tono, "who")
    assert who["text"].startswith("1 online:") and "Mateo" not in who["text"]
    look = cmd(game, tono, "look", a="Mateo")["text"]
    assert look.startswith("Captain Mateo, the ferry's pilot.") and "not a player" in look
    assert cmd(game, tono, "whisper", to="Mateo", a="hi")["text"] == \
        "Captain Mateo is a resident, not a player: talk to Captain Mateo where you find them."
    assert cmd(game, tono, "status")["text"].endswith("1 online.") or "1" in cmd(game, tono, "status")["text"]
    refused = FakeConn()
    game.hello(refused, {"t": "hello", "v": 1, "lang": "en", "name": "Jali", "job": "pilot", "secret": "j" * 64})
    assert refused.sent[0]["code"] == "name_reserved"                  # the id is still theirs


def test_a_player_cant_take_a_residents_name(make_game):
    game = make_game()
    for name in ("Rocco", "Mateo", "Amara", "Fern"):
        refused = FakeConn()
        game.hello(refused, {"t": "hello", "v": 1, "lang": "en", "name": name, "job": "pilot",
                             "secret": "r" * 64})
        assert refused.sent[0].get("code") == "name_reserved", name


def test_the_residents_list_says_where_everyone_is(make_game):
    game = make_game()
    tono = join(game, "Tono", lang="id")                  # an old client's "id" is English too
    reply = text(game, tono, "residents")["text"]
    assert reply.startswith("The residents, who aren't players: Rocco, the Cantina's bartender, in the Cantina;")
    assert "Soren, a traveller who comes only at night, off duty for now" in reply
    assert reply.endswith("Talk to them where they are: talk to, and a name.")
    assert text(game, tono, "penduduk")["text"] == \
        "I don't understand \"penduduk\". Type help for the commands."


# ------------------------------------------------------------
# Talking
# ------------------------------------------------------------

def test_talking_greets_you_in_the_residents_voice_and_lists_the_topics(make_game):
    game = make_game()
    tono = join(game, "Tono")
    budi = join(game, "Budi")
    tono.clear()
    cmd(game, tono, "talk", to="Mateo")
    greeting, topics = tono.sent[-2], tono.sent[-1]
    assert greeting["k"] == "say" and greeting["actor"] == "Captain Mateo" and greeting["voice"] == 5
    assert greeting["text"] == f"Captain Mateo says: {greeting['words']}"
    assert greeting["words"] in game.world.npcs["npcs"]["bayu"]["greet"]["en"]
    assert topics["text"].startswith("You can ask Captain Mateo about: ferry, worlds, customs, wombat and favour.")
    assert "Say ask Mateo about, and a topic." in topics["text"]
    assert budi.sent[-1]["text"] == "Tono chats with Captain Mateo."
    tono.clear()
    text(game, tono, "talk to Captain Mateo")                     # the whole name, typed
    assert tono.sent[-2]["actor"] == "Captain Mateo"
    tono.clear()
    text(game, tono, "talk to bayu")                              # the id still finds him
    assert tono.sent[-2]["actor"] == "Captain Mateo"


def test_asking_about_topics(make_game):
    game = make_game()
    tono = join(game, "Tono", lang="id")                  # an old client's "id" is English too
    reply = text(game, tono, "ask Mateo about the ferry")
    assert reply["actor"] == "Captain Mateo" and reply["words"].startswith("The Starling leaves in ")
    assert reply["words"].endswith("Say ferry to, and a world.")
    assert text(game, tono, "ask Captain Mateo about customs")["words"].startswith(
        "Customs search the Gate most, the ferry less")
    assert text(game, tono, "ask Mateo customs")["words"].startswith("Customs search")       # without "about"
    assert text(game, tono, "ask Mateo about the wombat")["words"].startswith("The little Wombat flies miners")
    unknown = text(game, tono, "ask Mateo about a curry recipe")
    assert unknown["words"] in ("I know routes, not riddles. Ask me about the ferry or the worlds.",
                                "Couldn't tell you. But I could fly you somewhere that knows.")
    assert text(game, tono, "tanya Bayu tentang feri")["text"] == \
        "I don't understand \"tanya Bayu tentang feri\". Type help for the commands."


def test_talking_by_the_old_ways_of_saying_it(make_game):
    game = make_game()
    tono = join(game, "Tono")
    tono.clear()
    cmd(game, tono, "say", a="to Mateo")                    # "say to Mateo" from an older client
    assert tono.sent[-2]["actor"] == "Captain Mateo" and tono.sent[-1]["text"].startswith("You can ask")
    tono.clear()
    cmd(game, tono, "say", a="to be honest")                # just words
    assert tono.sent[-1]["k"] == "said"
    tono.clear()
    cmd(game, tono, "say", a="hi to Mateo")                 # "say hi to Mateo"
    assert tono.sent[-2]["text"] == "You greet Captain Mateo." and tono.sent[-1]["actor"] == "Captain Mateo"
    assert text(game, tono, "hello Mateo")["actor"] == "Captain Mateo"
    assert tono.sent[-2]["text"] == "You greet Captain Mateo."
    assert text(game, tono, "good morning Mateo")["actor"] == "Captain Mateo"
    assert text(game, tono, "greet Mateo")["actor"] == "Captain Mateo"
    assert text(game, tono, "halo Bayu")["text"] == "I don't understand \"halo Bayu\". Type help for the commands."


def test_nobody_to_talk_to_or_somebody_elsewhere(make_game, clock):
    game = make_game()
    tono = join(game, "Tono")
    place(game, tono, "service")
    assert cmd(game, tono, "talk")["text"].startswith("There's nobody here to talk to.")
    assert cmd(game, tono, "talk", to="Rocco")["text"] == "Rocco isn't here. You might find Rocco in the Cantina."
    assert cmd(game, tono, "talk", to="Soren")["text"] == "Soren is off duty now. Try again later."
    budi = join(game, "Budi")
    place(game, budi, "service")
    assert cmd(game, tono, "talk", to="Budi")["text"].startswith("Budi is a player")


def test_live_answers(make_game, clock):
    game = make_game()
    tono = join(game, "Tono")
    join(game, "Budi")
    join(game, "Ani")
    place(game, tono, "cantina")
    game.npc_rng = random.Random(1)
    assert cmd(game, tono, "ask", to="Rocco", a="who")["words"] == \
        "3 people are about on the station right now, Ani and Budi among them."
    game.start_event("double_xp")
    assert "for another 60 minutes" in cmd(game, tono, "ask", to="Rocco", a="events")["words"]
    game.market.overrides["coffee"] = {"price": 30.0, "until": clock() + 600}
    market = cmd(game, tono, "ask", to="Rocco", a="market")["words"]
    assert "sack of coffee is dear right now" in market
    tono.session.char["credits"] = 99999
    game._save(tono.session)
    game.npc_rng.choice = lambda seq: seq[0]
    assert "Tono has more credits" in cmd(game, tono, "ask", to="Rocco", a="gossip")["words"]
    place(game, tono, "engineering")
    assert cmd(game, tono, "ask", to="Oskar", a="my progress")["words"] == \
        "You're level 1, a trainee pilot. 60 more XP and you'll be level 2. Keep your hands busy."
    place(game, tono, "gear_shop")
    special = cmd(game, tono, "ask", to="Felix", a="special")["words"]
    tid = game.special_of("gear")
    assert f"Today's special is the {game.world.things[tid]['one']['en']}, just " \
           f"{game.price_of(tono.session.char, tid, 'gear')} credits." in special
    place(game, tono, "pet_shop")
    assert cmd(game, tono, "ask", to="Priya", a="my pet")["words"].startswith("You don't have a pet yet!")
    place(game, tono, "dock")
    assert "The Starling leaves in" in cmd(game, tono, "ask", to="Mateo", a="ferry")["words"]


def test_the_night_traveller(make_game, clock):
    at(clock, 18, 50)
    game = make_game()
    tono = join(game, "Tono")
    place(game, tono, "observation")
    assert game.npcs["kelana"]["room"] is None
    at(clock, 19, 0, )
    for _ in range(3):
        clock.advance(15)
        game.tick()
    assert game.npcs["kelana"]["room"] == "observation"
    assert "A figure in a dusty cloak is suddenly at the rail" in tono.texts("arrive")[-1]
    assert cmd(game, tono, "ask", to="Soren", a="the time")["words"].startswith(
        "It's 19:00 by the station's clock, at night.")
    assert cmd(game, tono, "ask", to="Soren", a="the hunt")["words"].startswith("No song is being sought")
    at(clock, 5, 0, day=26)
    for _ in range(3):
        clock.advance(15)
        game.tick()
    assert game.npcs["kelana"]["room"] is None
    assert tono.texts("leave")[-1] == "When you look again, the traveller in the dusty cloak is gone."


# ------------------------------------------------------------
# Schedules and walking
# ------------------------------------------------------------

def test_residents_keep_their_daily_schedule(make_game, clock):
    game = make_game()                                       # 12:30 station time
    assert game.npcs["gino"]["room"] == "cargo" and game.npcs["tari"]["room"] == "pavilion"
    assert game.npcs["laras"]["room"] == "food_court" and game.npcs["jali"]["room"] == "cantina"
    at(clock, 3, 0)
    early = make_game()
    assert early.npcs["gino"]["room"] is None and early.npcs["laras"]["room"] == "reading_room"   # 1.6: reading


def test_a_resident_walks_to_the_next_place_and_both_rooms_hear_it(make_game, clock):
    game = make_game()
    watcher = join(game, "Tono")
    place(game, watcher, "cargo")
    path = game.world.npc_route("cargo", "cantina")
    at(clock, 17, 0)
    rooms = []
    for _ in range(60):
        clock.advance(15)
        game.tick()
        rooms.append(game.npcs["gino"]["room"])
        if rooms[-1] == "cantina":
            break
    assert [r for i, r in enumerate(rooms) if i == 0 or r != rooms[i - 1]] == [room for _d, room in path]
    left = [m for m in watcher.events("leave") if m.get("actor") == "Gino"]
    assert left and left[0]["dir"] == path[0][0] and left[0]["text"].startswith("Gino heads")
    budi = join(game, "Budi")
    place(game, budi, "cantina")
    at(clock, 21, 0)
    clock.advance(1)
    for _ in range(60):
        clock.advance(15)
        game.tick()
        if game.npcs["gino"]["room"] is None:
            break
    assert game.npcs["gino"]["room"] is None
    assert any(m.get("actor") == "Gino" for m in budi.events("leave"))


# ------------------------------------------------------------
# Memory and affinity
# ------------------------------------------------------------

def test_talking_every_day_and_new_topics_bring_you_closer(make_game, clock):
    game = make_game()
    tono = join(game, "Tono")
    cmd(game, tono, "talk", to="Mateo")
    cmd(game, tono, "talk", to="Mateo")
    assert memory(game, tono, "bayu")["affinity"] == 1 and memory(game, tono, "bayu")["talks"] == 2
    cmd(game, tono, "ask", to="Mateo", a="ferry")
    cmd(game, tono, "ask", to="Mateo", a="ferry")
    cmd(game, tono, "ask", to="Mateo", a="customs")
    assert memory(game, tono, "bayu")["affinity"] == 3
    clock.advance(86400)
    cmd(game, tono, "greet", to="Mateo")
    assert memory(game, tono, "bayu")["affinity"] == 4
    clock.advance(86400)
    tono.clear()
    cmd(game, tono, "emote", e="wave", to="Mateo")
    assert memory(game, tono, "bayu")["affinity"] == 5
    assert "Captain Mateo now counts you as an acquaintance." in tono.texts("info")
    assert [m for m in tono.sent if m.get("sound") == "npc_warm"]
    assert "Captain Mateo knows you as an acquaintance." in cmd(game, tono, "look", a="Mateo")["text"]
    assert "Residents who know you: Captain Mateo (an acquaintance)." in cmd(game, tono, "profile")["text"]


def test_gestures_at_a_resident_are_answered(make_game):
    game = make_game()
    tono = join(game, "Tono")
    budi = join(game, "Budi")
    tono.clear()
    cmd(game, tono, "emote", e="hug", to="Mateo")
    assert tono.texts("emote")[-2:] == ["You hug Captain Mateo.", "Captain Mateo returns the hug warmly."]
    assert budi.texts("emote")[-2:] == ["Tono hugs Captain Mateo.", "Captain Mateo returns Tono's hug warmly."]
    assert tono.sent[-1]["emote"] == "hug" and tono.sent[-1]["actor"] == "Captain Mateo"


def test_gifts_once_a_day_and_more_for_what_they_like(make_game, clock):
    game = make_game()
    tono = join(game, "Tono")
    char = tono.session.char
    char["inventory"].update({"coffee": 3, "iron": 1, "compass": 1})
    cmd(game, tono, "give", to="Mateo", n=1, item="coffee")
    assert tono.sent[-2]["text"] == "You give 1 sack of coffee to Captain Mateo."
    assert tono.sent[-1]["words"].startswith("Oh! This is exactly what I like.")
    assert memory(game, tono, "bayu")["affinity"] == 4 and char["inventory"]["coffee"] == 2
    clock.advance(2)
    cmd(game, tono, "give", to="Mateo", n=1, item="iron")
    assert tono.sent[-1]["words"].startswith("Another one?") and memory(game, tono, "bayu")["affinity"] == 4
    clock.advance(86400)
    cmd(game, tono, "give", to="Captain", n=1, item="Mateo coffee")       # "give Captain Mateo coffee"
    assert said_by(tono, "Captain Mateo")[-1]["words"].startswith("Oh! This is exactly")
    assert tono.sent[-1]["text"] == "Captain Mateo now counts you as an acquaintance."
    assert cmd(game, tono, "give", to="Mateo", n=1, item="compass")["text"] == \
        "Captain Mateo can't accept compasses: those stay with you."
    assert cmd(game, tono, "give", to="Mateo", n=50, item="credits")["words"].startswith("Keep your credits")


def test_a_favour_asked_brought_and_rewarded(make_game, clock):
    game = make_game()
    tono = join(game, "Tono")
    char = tono.session.char
    place(game, tono, "engineering")
    cmd(game, tono, "ask", to="Oskar", a="work")
    assert tono.sent[-2]["words"].startswith("The pump housings need patching.")
    assert tono.sent[-1]["text"] == "Oskar is waiting for 3 pieces of scrap metal. When you have them, " \
                                    "give them to Oskar."
    char["inventory"]["scrap"] = 2
    assert cmd(game, tono, "give", to="Oskar", n=2, item="scrap")["text"] == \
        "Oskar needs 3 pieces of scrap metal, all at once."
    char["inventory"]["scrap"] = 4
    credits, xp = char["credits"], char["xp"]
    cmd(game, tono, "give", to="Oskar", n=3, item="scrap")
    assert char["credits"] == credits + 40 and char["xp"] == xp + 15 and char["inventory"]["scrap"] == 1
    assert "Good scrap. Good hands." in [m.get("words") for m in tono.events("say")][-1]
    assert memory(game, tono, "harsa")["favours"] == 1 and memory(game, tono, "harsa")["affinity"] == 7
    clock.advance(2)
    cmd(game, tono, "ask", to="Oskar", a="work")
    assert tono.sent[-2]["words"].startswith("The console's memory is failing.")    # the next one: min 5
    game.store.save_npc_memory(dict(memory(game, tono, "harsa"), state={"done": {"scrap": game.today(),
                                                                                  "circuits": game.today()}}))
    cmd(game, tono, "ask", to="Oskar", a="work")
    assert tono.sent[-1]["words"].startswith("You've done enough for me today")
    clock.advance(86400)
    text(game, tono, "ask Oskar about work")
    assert tono.sent[-2]["words"].startswith("The pump housings")


def test_topics_and_errands_that_need_a_friend(make_game, clock):
    game = make_game()
    tono = join(game, "Tono")
    place(game, tono, "cantina")
    assert cmd(game, tono, "ask", to="Rocco", a="secret")["words"] == \
        "Ask me that again when we know each other a little better, Tono."
    talk = [m["text"] for m in (cmd(game, tono, "talk", to="Rocco"),)][0]
    assert "Get to know Rocco better, and there will be more to talk about." in talk
    game.store.save_npc_memory(dict(memory(game, tono, "jali"), affinity=15))
    assert cmd(game, tono, "ask", to="Rocco", a="secret")["words"].startswith("Alright, for you.")
    cmd(game, tono, "ask", to="Rocco", a="favour")
    assert tono.sent[-2]["words"].startswith("My chilli sauce jar is empty")
    assert tono.sent[-1]["text"] == "Rocco is waiting for 3 bags of chillies. When you have them, give them to Rocco."


def test_a_shopkeeper_gives_friends_a_small_discount(make_game):
    game = make_game()
    tono = join(game, "Tono")
    place(game, tono, "gear_shop")
    char = tono.session.char
    before = game.price_of(char, "scanner", "gear")
    game.store.save_npc_memory(dict(memory(game, tono, "tegar"), affinity=15, first_met=1.0))
    assert game.price_of(char, "scanner", "gear") == round(before * 0.95) or \
        abs(game.price_of(char, "scanner", "gear") - before * 0.95) <= 1
    listing = cmd(game, tono, "list", a="devices")["text"]
    assert listing.endswith("Felix gives you a friend's price: 5 percent off.")
    game.store.save_npc_memory(dict(memory(game, tono, "tegar"), affinity=30))
    assert abs(game.price_of(char, "scanner", "gear") - before * 0.9) <= 1
    assert game.price_of(char, "headlamp", "general") == game.price_of(join(game, "Budi").session.char,
                                                                      "headlamp", "general")


# ------------------------------------------------------------
# Idle lines and greetings
# ------------------------------------------------------------

def test_idle_lines_are_rare_and_never_while_players_talk(make_game, clock):
    game = make_game()
    tono = join(game, "Tono")
    place(game, tono, "cantina")
    for _ in range(40):                                    # ten minutes
        clock.advance(15)
        game.tick()
    lines = said_by(tono, "Rocco")
    assert 1 <= len(lines) <= 4
    tono.clear()
    for _ in range(40):
        clock.advance(15)
        if _ % 4 == 0:
            cmd(game, tono, "say", a="still here")          # a minute apart
        game.tick()
    assert not said_by(tono, "Rocco")


def test_idle_lines_fit_the_room(make_game, clock):
    game = make_game()
    at(clock, 7, 0)
    game = make_game()
    tono = join(game, "Tono")
    place(game, tono, "dock")
    for _ in range(120):
        clock.advance(15)
        game.tick()
    gino = [m["text"] for m in said_by(tono, "Gino")]
    assert gino and all("pancake" not in line and "tower" not in line for line in gino)


def test_a_resident_who_knows_you_says_hello_when_you_walk_in(make_game, clock):
    game = make_game()
    tono = join(game, "Tono")
    game.store.save_npc_memory(dict(memory(game, tono, "jali"), affinity=15, first_met=1.0))
    game.npc_rng.random = lambda: 0.0
    walked = []
    place(game, tono, "promenade_west")
    tono.clear()
    cmd(game, tono, "move", d="w")
    walked = said_by(tono, "Rocco")
    assert walked and "Tono" in walked[-1]["words"]
    cmd(game, tono, "move", d="e")
    tono.clear()
    cmd(game, tono, "move", d="w")
    assert not said_by(tono, "Rocco")                      # not again so soon


@pytest.mark.parametrize("topic, lang, start", [
    ("people", "en", "People: the simulation has residents"), ("residents", "id", "People: the simulation has residents"),
    ("pets", "en", "Pets: Whiskers & Widgets"), ("tricks", "id", "Pets: Whiskers & Widgets"),
    ("family", "en", "Family: partner with Sam"), ("baby", "id", "Family: partner with Sam"),
    ("weddings", "en", "Weddings: buy a ring"), ("propose", "id", "Weddings: buy a ring"),
])
def test_help_comes_in_groups(make_game, topic, lang, start):
    game = make_game()
    conn = join(game, "Ani", lang=lang)                   # an old client's "id" is English too
    assert cmd(game, conn, "help", a=topic)["text"].startswith(start)
    assert "Life: help pets, help family, help weddings." in cmd(game, conn, "help")["text"]
    assert text(game, conn, "help " + topic)["text"].startswith(start)


def test_help_in_indonesian_gets_the_english_hint(make_game):
    game = make_game()
    conn = join(game, "Ani", lang="id")
    assert text(game, conn, "bantuan hewan")["text"] == \
        "I don't understand \"bantuan hewan\". Type help for the commands."
    assert cmd(game, conn, "help", a="keluarga")["text"].startswith("Help, by group.")   # the general help


def test_returning_players_hear_what_is_new_once(make_game):
    game = make_game()
    ani = join(game, "Ani")
    assert "New in Orbit" not in ani.sent[1]["text"]                   # new characters start knowing
    ani.session.char["stats"]["seen_version"] = "1.1"
    cmd(game, ani, "bye")
    back = join(game, "Ani")
    assert "New in Orbit 1.2: the simulation has residents who aren't players" in back.sent[1]["text"]
    assert "New in Orbit 1.3: the station's goods are traded at four markets now" in back.sent[1]["text"]
    assert "it's a whole simulation now" not in back.sent[1]["text"]
    cmd(game, back, "bye")
    third = join(game, "Ani")
    assert "New in Orbit" not in third.sent[1]["text"]
    third.session.char["stats"]["seen_version"] = "1.2"         # from 1.2: only 1.3's note
    cmd(game, third, "bye")
    again = join(game, "Ani")
    assert "New in Orbit 1.3:" in again.sent[1]["text"] and "New in Orbit 1.2" not in again.sent[1]["text"]
    again.session.char["stats"].pop("seen_version")              # from 1.0: every note
    cmd(game, again, "bye")
    first = join(game, "Ani").sent[1]["text"]
    assert first.index("it's a whole simulation now") < first.index("New in Orbit 1.2") < first.index("New in Orbit 1.3")


# ------------------------------------------------------------
# The database
# ------------------------------------------------------------

def test_what_they_remember_is_kept(tmp_path, make_game, clock):
    path = str(tmp_path / "orbit.db")
    game = make_game(path)
    tono = join(game, "Tono")
    cmd(game, tono, "talk", to="Mateo")
    game.store.close()
    again = make_game(path)
    tono = join(again, "Tono")
    assert memory(again, tono, "bayu")["affinity"] == 1 and memory(again, tono, "bayu")["talks"] == 1


def test_a_version_7_database_gets_the_new_tables(tmp_path, clock, monkeypatch):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    with monkeypatch.context() as m:
        m.setattr(orbit_store, "SCHEMA_VERSION", 7)
        m.setattr(orbit_store.Store, "_migrate_8", lambda self: None)
        orbit_store.Store(path, clock=clock, iterations=1000, durable=False).close()
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7
    assert not db.execute("SELECT name FROM sqlite_master WHERE name IN "
                          "('npc_memory', 'partnerships', 'weddings', 'wedding_guests')").fetchall()
    db.execute("UPDATE characters SET stats = ? WHERE name_key = 'quilafly'", (json.dumps({"duels_won": 4}),))
    db.execute("INSERT INTO companions (kind, name, stats, state, created) VALUES ('cat_pet', 'Oyen', '{}', '{}', 1)")
    db.execute("INSERT INTO companion_owners (companion_id, char_id, since) VALUES (1, 1, 1)")
    db.commit()
    db.close()
    store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert store.version() == orbit_store.SCHEMA_VERSION == 8 and store.migrated_from == 7
    quila = store.by_name("quilafly")
    assert quila["credits"] == 1234 and quila["duels_won"] == 4
    assert store.top("duels_won", 1) == [("Quilafly", 4)]
    assert [c["name"] for c in store.companions_of(quila["id"])] == ["Oyen"]
    memory_row = store.npc_memory("jali", quila["id"])
    memory_row["affinity"] = 3
    store.save_npc_memory(memory_row)
    assert store.npc_memory("jali", quila["id"])["affinity"] == 3
    store.close()
    backup = sqlite3.connect(path + ".before-v8.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 7
    backup.close()


def test_the_configuration_names_the_residents_file(tmp_path):
    import orbit_server
    bundled = os.path.join(SERVER_DIR, "npcs.json")
    assert os.path.normpath(orbit_server.load_config(None)["npcs"]) == os.path.normpath(bundled)
    with open(bundled, encoding="utf-8") as f:
        data = json.load(f)
    data["npcs"]["jali"]["role"]["en"] = "the night bartender"
    (tmp_path / "residents.json").write_text(json.dumps(data), encoding="utf-8")
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"database": ":memory:", "npcs": "residents.json",
                                "game": {"events_enabled": False}}), encoding="utf-8")
    config = orbit_server.load_config(str(path))
    assert os.path.normpath(config["npcs"]) == str(tmp_path / "residents.json")
    server = orbit_server.OrbitServer(config)
    try:
        assert server.game.world.npcs["npcs"]["jali"]["role"]["en"] == "the night bartender"
    finally:
        server.store.close()
