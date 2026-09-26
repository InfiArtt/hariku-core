# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# "x here" (servers/orbit/orbit_here.py): what can be done in the room you're
# in, and "x" and a name, what can be done with a player, a resident or a
# thing. Every command "x here" lists, in every room of every world, is typed
# the way a player would (through client 1.6's reader) and must not be
# refused for the place: the list comes from the same checks the commands
# make, so it can't drift. Also: the words that ask for it from every client,
# the dark, the events, a mission, a ship and the ferry.

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
EXT_DIR = os.path.join(ROOT, "extensions", "orbit")
for folder in (SERVER_DIR, EXT_DIR):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import orbit_parse  # noqa: E402
import orbit_verbs  # noqa: E402
import orbit_world  # noqa: E402
from tests import orbit_parse_1_0, orbit_parse_1_4  # noqa: E402
from tests.test_orbit_server import FakeConn, clock, cmd, join, make_game, secret_of, world  # noqa: E402,F401

# The answers that mean "not here" (or "not a command"): none may come from a listed command.
WRONG_PLACE = {
    "unknown_command", "unknown_text", "look_what", "no_place", "not_here", "list_where", "shop_nothing",
    "not_at_market", "market_buys_nothing", "market_not_here", "market_doesnt_sell", "market_doesnt_buy", "sold_at",
    "no_good", "sell_at_pawn", "farm_where", "mine_where", "collect_nothing", "too_dark_to_mine", "too_dark_to_see",
    "casino_where", "challenge_who", "temple_where", "naming_where", "adopt_where", "wedding_book_where",
    "wedding_flowers_when", "board_where", "gig_where", "face_nothing", "face_which", "arcade_where", "gate_where",
    "gate_none_here", "gate_to_where", "ferry_where", "ferry_none_here", "ferry_to_where", "ferry_under_way",
    "work_where", "refuel_where", "ship_elsewhere", "their_ship_not_here", "not_aboard", "not_captain", "no_ship",
    "fly_where", "already_aboard", "in_flight", "in_kancil", "in_ferry", "in_ship", "duel_where", "duel_not_here",
    "duel_how", "event_nothing_to_watch", "event_join_where", "event_nothing_to_join", "party_where", "visit_where",
    "not_invited", "npc_nobody", "npc_elsewhere", "npc_whom", "open_nothing", "take_where", "take_no",
    "take_nothing", "complete_where", "complete_missing", "mission_none", "crew_hangar_none", "crew_none",
    "no_player", "no_item", "go_where", "way_where", "way_unknown",
}
NEW_CLIENT = "Hariku Orbit 1.6"


def join_new(game, name, job="pilot"):
    conn = FakeConn("en")
    game.hello(conn, {"t": "hello", "v": 1, "lang": "en", "name": name, "job": job, "secret": secret_of(name),
                      "client": NEW_CLIENT})
    return conn


@pytest.fixture
def spied(make_game):
    """A game that notes the key of every error it says."""
    game = make_game()
    errors = []
    send = game._send

    def noting(session, kind, key=None, *args, **kwargs):
        if kind == "error":
            errors.append(key)
        return send(session, kind, key, *args, **kwargs)

    game._send = noting
    return game, errors


def typed(game, conn, words):
    """What a player gets for typing `words` (read by the current client): the new events."""
    parsed = orbit_parse.parse(words)
    assert parsed is not None and "local" not in parsed, (words, parsed)
    before = len(conn.sent)
    game.receive(conn, dict(parsed, t="cmd"))
    return conn.sent[before:]


def asked(game, conn, words):
    """The same words sent as plain text, which the server reads itself (from any client)."""
    before = len(conn.sent)
    game.receive(conn, {"t": "cmd", "c": "text", "a": words})
    return conn.sent[before:]


def ready(game, conn, level=12):
    char = conn.session.char
    char["xp"] = game.xp_for_level(level)
    char["credits"] = 100000
    return char


def reset(game, conn, room):
    """Back in `room`, as a player who just walked in (nothing under way)."""
    session = conn.session
    char = session.char
    for key in ("flight", "ride", "ferry", "eva", "gig", "visit"):
        char["stats"].pop(key, None)
    char["stats"]["cooldowns"] = {}
    char["location"] = room
    char["credits"] = 100000
    session.task = session.arcade = session.blackjack = session.guide = None
    game.leave_casino(session)
    game.forget_duels(session)


ROOMS = sorted(lid for lid, loc in orbit_world.World.load().locations.items() if not loc.get("hidden"))


def last_said(messages):
    return [m for m in messages if m.get("sound") != "achievement"][-1]


@pytest.mark.parametrize("room", ROOMS)
def test_every_command_listed_here_works_here(spied, room):
    game, errors = spied
    ani = join_new(game, "Ani")
    maya = join_new(game, "Maya", "trader")
    char = ready(game, ani)
    ready(game, maya)
    if game.world.locations[room].get("crew_room"):
        assert cmd(game, ani, "crew_create", a="Starfinch")["text"].startswith("You found the crew")
    if game.world.locations[room].get("dark"):
        char["inventory"]["headlamp"] = 1
        game.worn(char)["head"] = "headlamp"
    if room == game.world.worlds["station"]["port"]:
        game.store.add_ship(char["id"], "ship_swiftlet", "", room, 20.0)
    for conn in (ani, maya):
        reset(game, conn, room)
    entries = game.here_actions(ani.session)
    shown = last_said(typed(game, ani, "x here"))
    lines = shown["lines"]
    assert lines[0].startswith("Here ") and lines[0].endswith(" you can:") and lines[-1] == \
        "Type help for everything else.", lines
    assert len(lines) == len(entries) + 2 or (not entries and len(lines) == 3)
    for (command, _key, _params), line in zip(entries, lines[1:]):
        assert line.startswith(f"{command}: "), (line, command)
    for command, key, _params in entries:
        reset(game, ani, room)
        reset(game, maya, room)
        errors.clear()
        answer = typed(game, ani, command)
        assert answer, (room, command)
        wrong = [e for e in errors if e in WRONG_PLACE]
        assert not wrong, (room, command, key, wrong, [m.get("text") for m in answer][-2:])


def test_a_command_where_it_doesnt_work_would_be_caught(spied):
    game, errors = spied
    ani = join_new(game, "Ani")
    ani.session.char["location"] = "cantina"
    for command, key in (("mine", "mine_where"), ("plant tomato", "farm_where"), ("prices coffee", None),
                         ("gig", "gig_where"), ("dice 50 high", "casino_where")):
        errors.clear()
        typed(game, ani, command)
        assert key is None or key in errors, (command, errors)
        assert command.split()[0] not in [e[0].split()[0] for e in game.here_actions(ani.session)]


def test_rooms_say_what_they_offer(spied):
    game, _errors = spied
    ani = join_new(game, "Ani")
    join_new(game, "Maya", "trader")

    def listed(room):
        for conn in game.sessions.values():
            conn.char["location"] = room
        return last_said(typed(game, ani, "x here"))["lines"]

    cantina = listed("cantina")
    assert cantina[0] == "Here in the Cantina you can:"
    assert "list: what the Cantina bar sells, and the prices" in cantina
    assert "buy iced coffee: buy from the Cantina bar" in cantina
    assert "talk to Rocco: hear what Rocco can tell you about" in cantina
    assert any(line.startswith("ask Rocco about gossip: ") for line in cantina)
    assert cantina[-1] == "Type help for everything else."
    assert not any(line.startswith(("look: ", "inventory: ", "who: ", "say ")) for line in cantina)
    market = listed("spice_market")
    assert market[1:4] == ["prices: what this market buys and sells, and its prices",
                           "buy 2 coffee: buy goods from this market", "sell 2 coffee: sell your goods to this market"]
    farm = [line.split(": ")[0] for line in listed("hydroponics")]
    assert {"farm", "plant water spinach", "water", "harvest", "list"} <= set(farm)
    assert {"casino", "dice 50 high", "slots 50", "blackjack 50", "challenge Maya 50", "lottery"} <= \
        {line.split(": ")[0] for line in listed("casino")}
    dock = [line.split(": ")[0] for line in listed("dock")]
    assert {"ride the Wombat", "ferry to the Moon", "worlds", "work", "talk to Mateo"} <= set(dock)
    assert {"gate to the Moon", "worlds"} <= {line.split(": ")[0] for line in listed("gate_hall")}
    assert {"mine", "prices", "ride the Wombat"} <= {line.split(": ")[0] for line in listed("belt")}
    assert {"collect"} <= {line.split(": ")[0] for line in listed("kar_farms")}
    assert {"face moss sprite"} <= {line.split(": ")[0] for line in listed("grove_wood")}
    assert {"gig"} <= {line.split(": ")[0] for line in listed("lumina_couriers")}
    assert {"arcade", "play quick draw", "arcade scores", "buy arcade token"} <= \
        {line.split(": ")[0] for line in listed("pixel_cabinets")}
    assert {"ring the bell", "light a lantern", "wedding schedule"} <= \
        {line.split(": ")[0] for line in listed("star_hall")}
    assert "adopt" in {line.split(": ")[0] for line in listed("medbay")}
    jeweller = {line.split(": ")[0] for line in listed("jeweller")}
    assert {"book wedding jasmine pavilion simple neutral 14:00", "wedding schedule", "buy silver band"} <= jeweller
    assert {"duel Maya 20", "duels"} <= {line.split(": ")[0] for line in listed("gym")}
    pawn = [line.split(": ")[0] for line in listed("pawn")]
    assert "list" in pawn and not any(c.startswith("sell ") for c in pawn)     # nothing of yours it would buy
    ani.session.char["inventory"]["headlamp"] = 1
    assert "sell headlamp" in [line.split(": ")[0] for line in listed("pawn")]
    assert "sell headlamp: sell it here" in last_said(typed(game, ani, "x headlamp"))["lines"]
    assert "open capsule" in {line.split(": ")[0] for line in listed("secret")}
    # Your cabin: a party, and a friend to invite.
    assert {"host a party", "invite Maya"} <= {line.split(": ")[0] for line in listed("cabin")}


def test_the_dark_hides_the_room_and_a_headlamp_shows_it(spied):
    game, _errors = spied
    ani = join_new(game, "Ani")
    ani.session.char["location"] = "belt_cave"
    dark = last_said(typed(game, ani, "x here"))
    assert dark["lines"] == ["It's too dark here to make anything out. A headlamp, worn, would show you the room.",
                             "Type help for everything else."]
    ani.session.char["inventory"]["headlamp"] = 1
    game.worn(ani.session.char)["head"] = "headlamp"
    lit = last_said(typed(game, ani, "x here"))["lines"]
    assert lit[0] == "Here in the Crystal Cave you can:" and "mine: dig for ore; a better drill finds richer rock" in lit


def test_job_mission_and_events_are_listed_where_they_happen(spied, clock):
    game, errors = spied
    ani = join_new(game, "Ani", "engineer")
    char = ready(game, ani)
    for room in ("engineering", "reactor_core"):
        char["location"] = room
        assert "work: your shift here (engineer)" in last_said(typed(game, ani, "x here"))["lines"]
    char["location"] = "dock"                                   # not an engineer's workplace
    assert not any(line.startswith("work:") for line in last_said(typed(game, ani, "x here"))["lines"])
    # A mission: take where it starts, complete where it ends.
    mid = game.board()[0]
    mission = game.world.missions[mid]
    game._mission_state(char)["active"] = mid
    char["location"] = mission["from"]
    take = [e for e in game.here_actions(ani.session) if e[1] == "here_take"]
    assert take, game.here_actions(ani.session)
    errors.clear()
    typed(game, ani, take[0][0])
    assert char["inventory"].get(mission["item"]) == mission["count"] and not errors
    char["location"] = mission["to"]
    complete = [e for e in game.here_actions(ani.session) if e[1] == "here_complete"]
    assert complete == [("complete", "here_complete", {})]
    typed(game, ani, "complete")
    assert not errors and not game._active_mission(char)
    # Events held in a room: gathering, a view, taking part, the drone.
    for eid, room, command in (("meteor_shower", "observation", "collect"), ("comet_flyby", "observation", "watch"),
                               ("dust_storm", "kar_shelter", "join"), ("drone_boss", "dock", "fix drone")):
        row = game.start_event(eid, quiet=True)
        char["location"] = room
        commands = [e[0] for e in game.here_actions(ani.session)]
        assert command in commands, (eid, commands)
        errors.clear()
        typed(game, ani, command)
        assert not [e for e in errors if e in WRONG_PLACE], (eid, errors)
        game.end_event(row)
        char["location"] = room
        assert command not in [e[0] for e in game.here_actions(ani.session)]


def test_aboard_a_ship_and_the_ferry(spied, clock):
    game, errors = spied
    ani = join_new(game, "Ani")
    char = ready(game, ani)
    game.store.add_ship(char["id"], "ship_swiftlet", "", "hangar", 20.0)
    char["location"] = "hangar"
    assert {"embark", "refuel", "worlds"} <= {e[0] for e in game.here_actions(ani.session)}
    typed(game, ani, "embark")
    assert char["location"] == "ship"
    aboard = [e[0] for e in game.here_actions(ani.session)]
    assert aboard[0].startswith("fly to ") and {"refuel", "load all", "unload all", "cargo", "disembark"} <= \
        set(aboard)
    for command in aboard:
        if command.startswith("fly to"):
            continue                                        # it would leave: tried last
        errors.clear()
        typed(game, ani, command)
        char["location"] = "ship"
        assert not [e for e in errors if e in WRONG_PLACE], (command, errors)
    typed(game, ani, "disembark")
    char["location"] = "dock"
    typed(game, ani, "ferry to the Moon")
    assert char["location"] == "ferry"
    assert [e[0] for e in game.here_actions(ani.session)] == ["disembark"]
    typed(game, ani, "disembark")
    assert char["location"] == "dock"


# ------------------------------------------------------------
# x and a name
# ------------------------------------------------------------

def test_x_a_resident(spied):
    game, errors = spied
    ani = join_new(game, "Ani")
    ani.session.char["location"] = "cantina"
    got = last_said(typed(game, ani, "x Rocco"))
    lines = got["lines"]
    assert lines[0] == "With Rocco you can:"
    commands = [line.split(": ")[0] for line in lines[1:]]
    assert commands[:3] == ["talk to Rocco", "ask Rocco about gossip", "greet Rocco"]
    assert {"give Rocco strawberry", "wave to Rocco", "list", "look at Rocco"} <= set(commands)
    ask = next(line for line in lines if line.startswith("ask Rocco about gossip: "))
    assert "who's around" in ask and "jukebox" in ask
    for command in commands:
        errors.clear()
        typed(game, ani, command)
        assert not [e for e in errors if e in WRONG_PLACE], (command, errors)
    assert last_said(typed(game, ani, "x Oskar"))["text"] == "Oskar isn't here. You might find Oskar in Engineering."
    join_new(game, "Maya")                                      # at the Dock
    assert last_said(typed(game, ani, "x Maya"))["text"] == "Maya isn't here."
    assert last_said(typed(game, ani, "x dragon"))["text"] == "You don't see dragon here."


def test_x_a_player(spied):
    game, errors = spied
    ani = join_new(game, "Ani")
    maya = join_new(game, "Maya", "trader")
    for conn in (ani, maya):
        ready(game, conn)
        conn.session.char["location"] = "casino"
    lines = last_said(typed(game, ani, "x Maya"))["lines"]
    assert lines[0] == "With Maya you can:"
    commands = [line.split(": ")[0] for line in lines[1:]]
    assert {"look at Maya", "whisper Maya hello", "give Maya 10 credits", "wave at Maya", "profile Maya",
            "add friend Maya", "invite Maya", "challenge Maya 50", "partner with Maya"} <= set(commands)
    assert not any(c.startswith("duel ") for c in commands)          # the casino isn't a contest zone
    for command in commands:
        errors.clear()
        typed(game, ani, command)
        assert not [e for e in errors if e in WRONG_PLACE], (command, errors)
    ani.session.char["location"] = maya.session.char["location"] = "gym"
    assert "duel Maya 20" in [line.split(": ")[0] for line in last_said(typed(game, ani, "x maya"))["lines"]]


def test_x_things_you_carry_here_and_for_sale(spied):
    game, errors = spied
    ani = join_new(game, "Ani")
    char = ready(game, ani)
    char["inventory"].update({"headlamp": 1, "iced_coffee": 2, "seed_tomato": 3, "coffee": 4})
    char["location"] = "spice_market"
    lamp = last_said(typed(game, ani, "x headlamp"))["lines"]
    assert lamp == ["With your headlamp you can:", "look at headlamp: what it is", "wear headlamp: wear it"]
    game.worn(char)["head"] = "headlamp"
    assert "remove headlamp: take it off" in last_said(typed(game, ani, "x headlamp"))["lines"]
    drink = last_said(typed(game, ani, "x iced coffee"))["lines"]
    assert drink[0] == "With your iced coffee you can:" and "use iced coffee: eat or drink it" in drink
    seeds = last_said(typed(game, ani, "x tomato seeds"))["lines"]
    assert "way to Hydroponics: the farm, where it can be planted" in seeds
    coffee = last_said(typed(game, ani, "x coffee"))["lines"]
    assert "sell 4 coffee: sell it here" in coffee                        # the Spice Market buys it
    for command in [line.split(": ")[0] for line in lamp + drink + seeds + coffee if ": " in line and
                    not line.startswith("With ")]:
        errors.clear()
        typed(game, ani, command)
        char["location"] = "spice_market"
        assert not [e for e in errors if e in WRONG_PLACE], (command, errors)
    char["location"] = "hydroponics"
    assert "plant tomato: sow it on your empty plots" in last_said(typed(game, ani, "x tomato seeds"))["lines"]
    char["location"] = "shop"
    mapper = last_said(typed(game, ani, "x mapper"))["lines"]
    assert mapper[0] == "With the pocket mapper you can:" and mapper[1] == "buy mapper: buy it here"
    assert last_said(typed(game, ani, "x jukebox"))["text"] == "You don't see jukebox here."
    char["location"] = "cantina"
    assert last_said(typed(game, ani, "x jukebox"))["lines"] == ["With the jukebox you can:",
                                                         "look at jukebox: what it is",
                                                         "jukebox: the songs on the jukebox; a coin plays one "
                                                         "for the room"]
    me = last_said(typed(game, ani, "x me"))["lines"]
    assert me[0] == "For yourself you can:" and "inventory: your credits and things" in me


def test_x_alone_and_the_words_for_it(spied):
    game, _errors = spied
    ani = join_new(game, "Ani")
    usage = last_said(asked(game, ani, "x"))
    assert usage["text"].startswith("Type x here for what you can do in this room") and "lines" not in usage
    for words in ("x here", "examine here", "commands here", "help here", "x room", "examine", "what can I do here",
                  "what can I do?"):
        got = last_said(asked(game, ani, words))
        assert got["k"] == "info" and got["text"].startswith(("Here at the Dock you can:", "Type x here")), words
    assert game.run(ani.session, {"c": "help", "a": "here"}) is None and \
        ani.last()["text"].startswith("Here at the Dock you can:")         # "help here" from clients 1.1 to 1.5
    for words in ("what can I do here", "what can i do here?", "what can I do"):
        assert orbit_verbs.parse(words) == {"c": "examine", "a": "here"}
    assert orbit_verbs.parse("what can I do with Rocco") == {"c": "examine", "a": "Rocco"}
    assert orbit_verbs.parse("x Maya") == {"c": "examine", "a": "Maya"}
    # look is still look.
    assert last_said(typed(game, ani, "look"))["lines"][0] == "Dock"
    assert last_said(typed(game, ani, "look at shuttle"))["text"].startswith("The Dove is a stubby cargo shuttle")


@pytest.mark.parametrize("reader", [orbit_parse_1_0.parse, orbit_parse_1_4.parse])
def test_older_clients_reach_x_here_too(make_game, reader):
    game = make_game()
    conn = join(game, "Tono", "engineer")
    for words in ("x here", "what can I do here", "x Mateo"):
        parsed = reader(words)
        assert parsed == {"c": "text", "a": words}              # they send it as it is
        game.receive(conn, dict(parsed, t="cmd"))
        answer = conn.last()
        assert answer["k"] == "info" and "\n" not in answer["text"] and "lines" not in answer
    assert conn.last()["text"].startswith("With Captain Mateo you can: talk to Mateo: ")
    game.receive(conn, {"t": "cmd", "c": "text", "a": "x here"})
    assert conn.last()["text"].startswith("Here at the Dock you can: ride the Wombat: the shuttle to the Belt "
                                          "Platform; ferry to the Moon: ")
    assert conn.last()["text"].endswith(". Type help for everything else.")
