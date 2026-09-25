# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for Orbit's map and things (servers/orbit): the map itself (every exit
# has its way back, every room can be reached, the compass agrees with the
# plan, the words for directions in both languages), walking by compass,
# "u" in Indonesian and English, the way to places and the mapper, the map,
# where am I, the compass, dark rooms and the headlamp, locked doors and
# keycards, vacuum, the EVA suit and the air that runs out, the Kancil
# shuttle, the scanner, the communicator and friends, the beacon, cabins and
# guests, the shops, using, wearing and examining things, food, pets (a
# companion in its own table), the time capsule and the temple. The server
# parser for plain text is tested here too.

import collections
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_verbs  # noqa: E402
import orbit_world  # noqa: E402
from tests.test_orbit_server import (FakeConn, clock, cmd, join, make_game, walk,  # noqa: E402,F401
                                     world)


def give(game, name, *things):
    char = game.sessions[name].char
    for tid in things:
        char["inventory"][tid] = char["inventory"].get(tid, 0) + 1


def wear(game, conn, thing):
    event = cmd(game, conn, "use", item=thing, equip=True)
    assert event["k"] == "info" and event.get("sound") == "equip", event
    return event


# ------------------------------------------------------------
# The map itself
# ------------------------------------------------------------

def test_every_exit_leads_somewhere_and_back(world):
    for lid, exits in world.exits.items():
        for d, ex in exits.items():
            assert d in orbit_world.DIRECTIONS, (lid, d)
            assert ex["to"] in world.locations, (lid, d, ex["to"])
            if ex["oneway"]:
                continue
            back = world.exits[ex["to"]].get(world.directions[d]["back"])
            assert back is not None and back["to"] == lid, f"{lid} {d} -> {ex['to']} has no way back"
    oneways = [(lid, d) for lid, exits in world.exits.items() for d, ex in exits.items() if ex["oneway"]]
    assert oneways == [("park", "d")]                      # the slide: marked, and only that


def test_every_room_can_be_reached_and_left(world):
    places = {lid for lid, loc in world.locations.items() if not loc.get("hidden")}
    assert 30 <= len(places) <= 150
    assert world.reachable() == places
    for lid in places:
        assert world.reachable(lid) >= {world.start}, f"stuck in {lid}"


def test_the_compass_agrees_with_the_plan(world):
    for lid, exits in world.exits.items():
        for d, ex in exits.items():
            info = world.directions[d]
            if d in ("u", "d") or world.locations[lid]["area"] != world.locations[ex["to"]]["area"]:
                continue
            x1, y1, z1 = world.at(lid)
            x2, y2, z2 = world.at(ex["to"])
            assert z1 == z2, (lid, d)
            assert ((x2 > x1) - (x2 < x1), (y2 > y1) - (y2 < y1)) == (info["dx"], info["dy"]), (lid, d)
    rooms_at = collections.Counter((world.locations[lid]["area"],) + world.at(lid)
                                   for lid in world.locations if not world.locations[lid].get("hidden"))
    assert max(rooms_at.values()) == 1                      # no two rooms in one spot


def test_the_words_for_directions_in_both_languages(world):
    for d, info in world.directions.items():
        for lang in ("en", "id"):
            assert info["name"][lang] and info["words"][lang], (d, lang)
            for word in info["words"][lang]:
                assert world.find_direction(word, lang) == d, (word, lang)
        assert world.directions[info["back"]]["back"] == d
    assert world.find_direction("u", "id") == "n" and world.find_direction("u", "en") == "u"
    assert world.find_direction("s", "id") == "s" == world.find_direction("s", "en")
    assert world.find_direction("barat daya", "en") == "sw" and world.find_direction("NE", "id") == "ne"
    assert world.find_direction("naik", "en") == "u" and world.find_direction("d", "id") == "d"
    assert world.find_direction("kantin", "id") is None


def test_the_places_everyone_needs_are_open_to_everyone(world):
    def no_keys(room, ex):
        return ex["lock"] is None and not world.locations[ex["to"]].get("airless")

    must = {lid for lid, loc in world.locations.items() if loc.get("landmark")}
    must |= {job["workplace"] for job in world.jobs.values()}
    must |= {m[f] for m in world.missions.values() for f in ("from", "to")}
    must |= {lid for lid, loc in world.locations.items() if loc.get("shop") or loc.get("farm")}
    must |= set(world.markets)
    for lid in must:
        wid = world.world_of(lid)
        start = world.start if wid in ("station", "belt") else world.worlds[wid]["port"]
        assert world.route(start, lid, no_keys) is not None, lid
    locks = {ex["lock"] for exits in world.exits.values() for ex in exits.values() if ex["lock"]}
    keys = {a for t in world.things.values() for a in (t.get("effects") or {}).get("access", [])}
    assert locks <= keys
    for lid, loc in world.locations.items():
        if loc.get("airless"):
            rescue = world.areas[loc["area"]].get("rescue")
            assert rescue and world.locations[rescue].get("rescue") and not world.locations[rescue].get("airless"), lid
    venues = {lid for lid, loc in world.locations.items() if loc.get("venue")}
    assert venues == {"star_hall", "pavilion", "grove_hall"} and world.locations["star_hall"].get("temple")


def test_a_map_that_breaks_the_rules_is_refused(world):
    import json
    for change in (lambda d: d["locations"]["park"]["exits"].update(d="service"),       # one-way, unmarked
                   lambda d: d["locations"]["cargo"]["exits"].update(s={"to": "dock", "lock": "gold"}),
                   lambda d: d["directions"]["n"]["words"].update(id=[]),
                   lambda d: d["shuttles"]["links"].append(["dock", "mars"])):
        data = json.loads(json.dumps(world.data))
        change(data)
        with pytest.raises(orbit_world.WorldError):
            orbit_world.World(data, world.economy)


# ------------------------------------------------------------
# The server reading plain text
# ------------------------------------------------------------

@pytest.mark.parametrize("text, lang, expected", [
    ("s", "id", {"c": "move", "d": "s"}),
    ("u", "id", {"c": "move", "d": "n"}),
    ("u", "en", {"c": "move", "d": "u"}),
    ("barat daya", "id", {"c": "move", "d": "sw"}),
    ("go north", "en", {"c": "move", "d": "n"}),
    ("naik", "id", {"c": "move", "d": "u"}),
    ("naik lift", "id", {"c": "move", "d": "u"}),
    ("naik kancil", "id", {"c": "board"}),
    ("ride the Kancil", "en", {"c": "board"}),
    ("arah ke kantin", "id", {"c": "way", "a": "kantin"}),
    ("way to the cantina", "en", {"c": "way", "a": "the cantina"}),
    ("pandu ke kantin", "id", {"c": "guide", "a": "kantin"}),
    ("pandu aku ke kantin", "id", {"c": "guide", "a": "kantin"}),
    ("guide me to the cantina", "en", {"c": "guide", "a": "the cantina"}),
    ("guide", "en", {"c": "guide"}),
    ("status pandu", "id", {"c": "guide"}),
    ("berhenti pandu", "id", {"c": "guide", "op": "stop"}),
    ("stop guide", "en", {"c": "guide", "op": "stop"}),
    ("stop guiding me", "en", {"c": "guide", "op": "stop"}),
    ("pandu", "id", None),                                   # Pandu is a name too
    ("arah", "id", {"c": "compass"}),
    ("peta", "id", {"c": "map"}),
    ("di mana aku", "id", {"c": "where"}),
    ("where am I", "en", {"c": "where"}),
    ("di mana Sari", "id", {"c": "locate", "to": "Sari"}),
    ("lacak Sari", "id", {"c": "locate", "to": "Sari"}),
    ("pindai", "id", {"c": "scan"}),
    ("tambah teman Sari", "id", {"c": "friends", "op": "add", "to": "Sari"}),
    ("undang Budi", "id", {"c": "invite", "op": "add", "to": "Budi"}),
    ("kunjungi Rafli", "id", {"c": "visit", "to": "Rafli"}),
    ("pakai senter", "id", {"c": "use", "item": "senter"}),
    ("pasang suar", "id", {"c": "use", "item": "suar", "equip": True}),
    ("take off headlamp", "en", {"c": "unequip", "item": "headlamp"}),
    ("daftar alat", "id", {"c": "list", "a": "alat"}),
    ("toko", "id", {"c": "list", "a": ""}),
    ("buka kapsul", "id", {"c": "open", "a": "kapsul"}),
    ("bunyikan lonceng", "id", {"c": "ring"}),
    ("light a lantern", "en", {"c": "lantern"}),
    ("baca prasasti", "id", {"c": "look", "a": "prasasti"}),
    ("harian", "id", {"c": "daily"}),
    ("profil Sari", "id", {"c": "profile", "to": "Sari"}),
    ("peringkat", "id", {"c": "rank"}),
    ("tanam 2 tomat", "id", {"c": "plant", "item": "tomat", "n": 2}),
    ("panen", "id", {"c": "harvest"}),
    ("siram", "id", {"c": "water"}),
    ("lahan", "id", {"c": "farm"}),
    ("tambang", "id", {"c": "mine"}),
    ("kumpulkan", "id", {"c": "collect"}),
    ("suaraku 3", "id", {"c": "voice", "a": "3"}),
    ("my voice auto", "en", {"c": "voice", "a": "auto"}),
    ("kode pindah", "id", {"c": "transfer"}),
    ("elus", "id", {"c": "pet", "op": "pat"}),
    ("namai Bip Bop", "id", {"c": "pet", "op": "name", "a": "Bip Bop"}),
    ("bantuan toko", "id", {"c": "help", "a": "toko"}),
    ("beri kredit Budi 500", "id", {"c": "admin", "op": "grant", "to": "Budi", "n": 500}),
    ("ambil kredit Budi 50", "id", {"c": "admin", "op": "take_credits", "to": "Budi", "n": 50}),
    ("beri item Budi senter 2", "id", {"c": "admin", "op": "give_item", "to": "Budi", "item": "senter", "n": 2}),
    ("atur harga kopi 20", "id", {"c": "admin", "op": "set_price", "item": "kopi", "n": 20}),
    ("reset harian Budi", "id", {"c": "admin", "op": "reset_streak", "to": "Budi"}),
    ("cabut akses Budi", "id", {"c": "admin", "op": "revoke", "to": "Budi"}),
    ("kode pindah untuk Budi", "id", {"c": "admin", "op": "transfer_for", "to": "Budi"}),
    ("ekonomi", "id", {"c": "admin", "op": "economy"}),
    ("goto the bridge", "en", {"c": "admin", "op": "goto", "a": "the bridge"}),
    ("hello there", "en", None),
    ("", "en", None),
])
def test_the_server_reads_plain_text(world, text, lang, expected):
    assert orbit_verbs.parse(text, lang, world.find_direction) == expected


# ------------------------------------------------------------
# Walking
# ------------------------------------------------------------

def test_u_is_north_in_indonesian_and_up_in_english(make_game):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    ben = join(game, "Ben", lang="en")
    for conn in (ani, ben):
        walk(game, conn, "lift_main")
    assert cmd(game, ani, "text", a="u")["room"] == "promenade"
    assert cmd(game, ben, "text", a="u")["room"] == "lift_upper"
    assert cmd(game, ani, "text", a="naik")["k"] == "error"        # the Promenade has no way up
    assert cmd(game, ben, "text", a="north")["room"] == "command"


def test_look_lists_the_exits_short_and_the_same_every_time(make_game):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    walk(game, ani, "service")
    text = cmd(game, ani, "look")["text"]
    assert "Jalan keluar: timur, selatan, barat daya (terkunci), barat." in text
    assert cmd(game, ani, "move", d="sw") == {
        "t": "ev", "k": "error", "sound": "locked", "text": "Pintu ke barat daya terkunci: butuh kartu kru."}
    give(game, "ani", "keycard_crew")
    assert "barat daya (terkunci)" not in cmd(game, ani, "look")["text"]


def test_the_way_needs_a_mapper_beyond_the_landmarks(make_game):
    game = make_game()
    tono = join(game, "Tono", "scientist")
    assert cmd(game, tono, "way", a="promenade")["text"] == (
        "To the Promenade: 2 east, south, up, then north. I'll guide you step by step; type stop guide to stop.")
    assert cmd(game, tono, "way", a="science lab")["text"].startswith("To the Science Lab:")   # workplace
    assert cmd(game, tono, "way", a="my cabin")["text"].startswith("To your cabin:")
    unknown = cmd(game, tono, "way", a="archive")
    assert unknown["k"] == "error" and unknown["text"].startswith("You don't know the way to the Station Archive yet.")
    walk(game, tono, "archive")                             # been there, but no mapper yet
    walk(game, tono, "dock")
    assert cmd(game, tono, "way", a="archive")["k"] == "error"
    give(game, "tono", "mapper")
    assert cmd(game, tono, "way", a="archive")["text"].startswith("To the Station Archive: 2 east, south, up 2 levels")
    assert cmd(game, tono, "way", a="gym")["k"] == "error"           # never been there
    give(game, "tono", "holomapper")
    assert cmd(game, tono, "way", a="gym")["text"].startswith("To the Zero-G Gym:")
    assert cmd(game, tono, "way", a="time capsule room")["k"] == "error"      # secret: no map shows it
    assert cmd(game, tono, "way", a="captain's quarters")["text"].startswith("You can't get to")
    assert cmd(game, tono, "way", a="the belt")["text"].endswith("ride the Kancil.")


def test_the_map_where_am_i_and_the_compass(make_game):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    walk(game, ani, "promenade_west")
    text = cmd(game, ani, "map")["text"]
    assert text.startswith("Kamu di Promenade Barat, di Dek Utama. Di sekitarmu: utara, Kebun Hidroponik; "
                           "timur, Promenade; selatan, Lorong Kabin Kru; barat, Kantin.")
    assert text.endswith("Pemeta bisa memberi tahu lebih banyak.")
    give(game, "ani", "mapper")
    assert "Tempat lain yang kamu tahu di sini: Lobi Lift Utama di arah tenggara." in cmd(game, ani, "map")["text"]
    give(game, "ani", "holomapper")
    full = cmd(game, ani, "map")["text"]
    assert "Toko Bintang di arah timur" in full and "Di tempat lain: Dek Atas: komando dan sains" in full
    where = cmd(game, ani, "where")["text"]
    assert where == "Promenade Barat, di Dek Utama. Jalan keluar: utara, timur, selatan, barat."
    compass = cmd(game, ani, "compass")
    assert compass["text"] == "Kompasmu: kamu sedang menghadap ke barat, di Dek Utama." and compass["sound"] == "gadget"


def test_dark_tunnels_need_a_worn_headlamp(make_game):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "keycard_crew")
    walk(game, ani, "service")
    dark = cmd(game, ani, "move", d="sw")
    assert "It's pitch dark. You can feel your way back: northeast." in dark["text"]
    assert "Exits" not in dark["text"] and "Pipes" not in dark["text"]
    bump = cmd(game, ani, "move", d="w")
    assert bump["text"] == "You bump into something in the dark. The way back: northeast." and bump["sound"] == "bump"
    assert cmd(game, ani, "look", a="pipes")["text"].startswith("It's too dark to see.")
    assert cmd(game, ani, "move", d="s")["room"] == "maint_2"      # you can still feel your way
    give(game, "ani", "headlamp")
    assert "pitch dark" in cmd(game, ani, "look")["text"]          # owned, but not worn
    wear(game, ani, "headlamp")
    lit = cmd(game, ani, "look")["text"]
    assert "cleaning bot" in lit and "Exits: north, east." in lit


def test_the_brass_key_opens_the_time_capsule_room_once(make_game):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "keycard_crew", "headlamp")
    wear(game, ani, "headlamp")
    walk(game, ani, "maint_3")
    assert cmd(game, ani, "move", d="s")["text"].startswith("The little round door to the south")
    give(game, "ani", "brass_key")
    walk(game, ani, "secret")
    opened = cmd(game, ani, "open", a="capsule")
    assert opened["k"] == "paid" and "300" in opened["text"] and game.sessions["ani"].char["credits"] == 400
    assert cmd(game, ani, "open", a="capsule")["text"].startswith("You've already opened the capsule.")


def test_vacuum_needs_a_worn_suit_and_the_air_runs_out_safely(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    walk(game, ani, "airlock")
    assert cmd(game, ani, "move", d="s")["text"].startswith("The airlock won't open")
    give(game, "ani", "eva_suit")
    assert cmd(game, ani, "move", d="s")["text"].startswith("The airlock won't open")     # carried, not worn
    wear(game, ani, "EVA suit")
    out = cmd(game, ani, "move", d="s")
    assert out["room"] == "hull_walk" and out["amb"] == "space" and "Air left: 3 minutes." in out["text"]
    assert cmd(game, ani, "unequip", item="eva suit")["text"] == "Not out here: you'd have no air!"
    clock.advance(121)
    game.tick()
    assert ani.last()["text"] == "Your suit beeps: 59 seconds of air left. Head back inside."
    assert ani.last()["sound"] == "air"
    clock.advance(40)
    game.tick()
    assert ani.last()["text"].startswith("Your suit beeps: 19 seconds")
    clock.advance(20)
    game.tick()
    rescued = ani.last()
    assert rescued["k"] == "failed" and rescued["sound"] == "rescue"
    assert rescued["text"] == ("Your air ran out, and the station's tow drone brought you back to the Airlock. "
                               "The tow costs 20 credits; you have 80.")
    assert game.sessions["ani"].char["location"] == "airlock" and "eva" not in game.sessions["ani"].char["stats"]
    # An oxygen tank: three more minutes; walking back in refills.
    give(game, "ani", "oxygen_tank")
    assert "Air left: 6 minutes." in cmd(game, ani, "move", d="s")["text"]
    back = cmd(game, ani, "move", d="n")
    assert back["text"] == "You're back in the air. Your suit's tanks refill." and back["sound"] == "air"


def test_the_air_runs_out_while_you_are_away_too(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "eva_suit")
    wear(game, ani, "eva suit")
    walk(game, ani, "debris_field")
    game.dropped(ani)
    clock.advance(500)
    game.tick()                          # the tow happens while nobody is connected
    game.tick()
    assert "ani" not in game.sessions or game.sessions["ani"].char["location"] == "airlock"
    back = join(game, "Ani")
    assert back.sent[0]["room"] == "airlock"


def test_the_kancil_flies_to_the_belt_and_back(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    budi = join(game, "Budi")
    board = cmd(game, ani, "board")
    assert board["k"] == "flight" and board["sound"] == "launch" and board["room"] == "kancil"
    assert board["text"].startswith("You pay the 5 credit fare (you have 95 left)") and "about 30 seconds" in board["text"]
    assert budi.texts("leave")[-1] == "Ani boards the Kancil, and it pulls away."
    assert cmd(game, ani, "move", d="e")["text"] == "You're aboard the Kancil! Wait until it lands."
    clock.advance(31)
    game.tick()
    landed = ani.last()
    assert landed["k"] == "moved" and landed["room"] == "belt" and landed["amb"] == "belt"
    assert landed["sound"] == "landing" and landed["text"].startswith("The Kancil touches down at the Belt Platform.")
    back = cmd(game, ani, "board")
    assert back["text"].startswith("You buckle in") and game.sessions["ani"].char["credits"] == 95   # free back
    pilot = join(game, "Pip", "pilot")
    give(game, "pip", "thruster")
    assert "about 8 seconds" in cmd(game, pilot, "board")["text"]          # free, fast, and faster
    assert game.sessions["pip"].char["credits"] == 100
    assert cmd(game, budi, "move", d="e")["room"] == "cargo"
    assert cmd(game, budi, "board")["text"] == "The Kancil flies from the Dock and from the Belt Platform."


def test_the_scanner_the_communicator_and_friends(make_game):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    cmd(game, budi, "move", d="e")
    assert cmd(game, ani, "scan")["text"] == "You need a scanner for that. Star Supply sells them."
    give(game, "ani", "scanner")
    scan = cmd(game, ani, "scan")
    assert scan["text"] == "Scanner: east, the Cargo Bay: Budi." and scan["sound"] == "scan"
    assert cmd(game, ani, "locate", to="Budi")["text"].startswith("You need a communicator")
    give(game, "ani", "communicator")
    assert cmd(game, ani, "locate", to="Budi")["text"] == "Budi is in the Cargo Bay, on the Lower Deck. The way: east."
    cmd(game, ani, "friends", op="add", to="budi")
    assert cmd(game, ani, "friends")["text"] == "Friends online: Budi. Offline: nobody."
    game.dropped(budi)
    game._remove(game.sessions["budi"])
    budi = join(game, "Budi")
    assert ani.last()["text"] == "Your communicator chirps: Budi has logged in."


def test_a_beacon_leads_you_back(make_game):
    game = make_game()
    ani = join(game, "Ani")
    assert cmd(game, ani, "way", a="beacon")["text"].startswith("You haven't placed a beacon.")
    give(game, "ani", "beacon")
    walk(game, ani, "workshop")
    placed = cmd(game, ani, "use", item="beacon", equip=True)
    assert placed["text"].startswith("You place your beacon in the Workshop") and placed["sound"] == "gadget"
    walk(game, ani, "dock")
    assert cmd(game, ani, "way", a="suar")["text"].startswith("To the Workshop: 4 east. I'll guide you")


def test_cabin_guests_by_invitation(make_game):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    give(game, "ani", "sofa", "lava_lamp")
    for conn in (ani, budi):
        walk(game, conn, "cabins_hall")
    cmd(game, ani, "move", d="s")
    assert cmd(game, budi, "visit", to="Ani")["text"] == "Ani hasn't invited you. Ask them to type invite and your name."
    cmd(game, ani, "invite", to="Budi")
    invite = budi.last()
    assert invite["k"] == "offer" and invite["ask"] and invite["actor"] == "Ani"
    visit = cmd(game, budi, "visit", to="Ani")
    assert visit["room"] == "cabin" and visit["text"].startswith("You walk south to your cabin. Ani's cabin.")
    assert "A rattan sofa with plump cushions" in visit["text"] and "A lava lamp glows" in visit["text"]
    assert ani.last()["text"] == "Budi comes in."
    cmd(game, budi, "say", a="nice place!")
    assert ani.texts("say")[-1] == "Budi says: nice place!"
    cmd(game, ani, "invite", op="remove", to="Budi")
    assert game.sessions["budi"].char["location"] == "cabins_hall"
    assert "Ani has asked you to leave their cabin." in budi.texts("system")


def test_the_shop_sells_things_with_levels_and_limits(make_game):
    game = make_game()
    ani = join(game, "Ani")
    char = game.sessions["ani"].char
    assert cmd(game, ani, "list")["text"].startswith("There's no shop here.")
    walk(game, ani, "shop")
    groups = cmd(game, ani, "list")["text"]
    assert groups.startswith("Star Supply sells devices (3), tools (2), food (2) and seeds (7).")
    devices = cmd(game, ani, "list", a="perangkat")["text"]
    mapper = game.price_of(char, "mapper", "general")
    assert f"pocket mapper, {mapper}" in devices and "holo mapper" not in devices
    headlamp = game.price_of(char, "headlamp", "general")
    char["credits"] = 1000
    bought = cmd(game, ani, "buy", item="headlamp")
    assert bought["text"] == f"You buy 1 headlamp for {headlamp} credits, and put it on. You have {1000 - headlamp} left."
    assert char["stats"]["worn"] == {"head": "headlamp"}
    assert cmd(game, ani, "buy", item="headlamp")["text"] == "You already have one: headlamp."
    assert f"headlamp, {headlamp} (you have it)" in cmd(game, ani, "list", a="devices")["text"]
    assert cmd(game, ani, "buy", item="plot")["text"].startswith("You buy one more plot in Hydroponics for 150")
    assert cmd(game, ani, "buy", item="plot")["text"].startswith("You buy one more plot in Hydroponics for 250")
    walk(game, ani, "gear_shop")
    gear = cmd(game, ani, "list")["text"]
    assert gear.startswith("Gearworks sells devices (")
    assert cmd(game, ani, "buy", item="holo mapper")["text"] == "holo mapper needs level 4. Type rank to see yours."
    holo = game.price_of(char, "holomapper", "gear")
    assert f"holo mapper, {holo}" in cmd(game, ani, "list", a="devices")["text"]
    examine = cmd(game, ani, "look", a="scanner")["text"]
    assert examine.startswith("Sweeps the rooms around you")
    assert examine.endswith(f"Price here: {game.price_of(char, 'scanner', 'gear')} credits.")
    walk(game, ani, "promenade")
    assert cmd(game, ani, "buy", item="mapper")["text"] == "Look for pocket mappers at Star Supply."


def test_prices_move_a_little_each_day_and_each_shop_has_a_special(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    char = game.sessions["ani"].char
    rules = game.econ["prices"]
    seen = {}
    for _day in range(6):
        for sid, shop in game.world.shops.items():
            special = game.special_of(sid)
            for tid in shop["stock"]:
                base = int(game.world.things[tid].get("tickets" if shop.get("currency") else "price") or 0)
                price = game.price_of(char, tid, sid)
                if shop.get("fixed") or game.world.things[tid].get("service"):
                    assert tid == "plot" or price == base, (sid, tid)
                    continue
                cut = rules["special"] if tid == special else 0
                low = base * (1 - rules["wobble"] - cut)
                high = base * (1 + rules["wobble"] - cut)
                assert low - 1 <= price <= high + 1, (sid, tid, base, price)
                assert price == game.price_of(char, tid, sid)          # the same all day
                seen.setdefault((sid, tid), set()).add(price)
            assert (special is None) == bool(shop.get("fixed")), sid
            assert special is None or special in shop["stock"]
        clock.advance(86400)
    assert sum(1 for prices in seen.values() if len(prices) > 1) > len(seen) // 2    # they do move
    walk(game, ani, "shop")
    special = game.special_of("general")
    listed = "".join(cmd(game, ani, "list", a=group)["text"] for group in ("devices", "seeds", "tools", "food"))
    assert listed.count("(today's special)") == 1
    name = game.world.things[special]["one"]["en"]
    assert f"{name}, {game.price_of(char, special, 'general')} (today's special)" in listed


def test_using_and_wearing_things(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    budi = join(game, "Budi")
    give(game, "ani", "iced_coffee", "martabak", "kerupuk", "batik_shirt", "title_explorer")
    crunch = cmd(game, ani, "use", item="kerupuk")
    assert crunch["text"] == "Crunch, crunch, crunch. Very satisfying." and crunch["sound"] == "crunch"
    assert budi.texts("emote")[-1] == "Ani crunches loudly on prawn crackers."
    assert "kerupuk" not in game.sessions["ani"].char["inventory"]
    wear(game, ani, "batik shirt")
    wear(game, ani, "explorer")
    looked = cmd(game, budi, "look", a="Ani")["text"]
    assert looked == ("Ani, trainee engineer. Title: Explorer. Wearing a batik shirt with tiny rockets "
                      "in its pattern. Nothing unusual about them.")
    assert cmd(game, ani, "unequip", item="batik shirt")["text"] == "You take off your batik shirt."
    cmd(game, ani, "use", item="iced coffee")
    cmd(game, ani, "use", item="martabak")
    walk(game, ani, "engineering")
    codes = cmd(game, ani, "work")["codes"]
    paid = cmd(game, ani, "answer", a="".join(map(str, codes)))
    assert "Next shift in 60 seconds." in paid["text"]                  # the martabak halved the break
    assert game.sessions["ani"].char["xp"] == 15                        # the coffee: 10 XP and half again
    clock.advance(601)
    assert game.award_xp(game.sessions["ani"], 10) == 10                # the coffee wore off


def test_a_pet_is_a_companion_of_its_own(make_game, monkeypatch):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    game.sessions["ani"].char["credits"] = 2000
    walk(game, ani, "pet_shop")
    price = game.price_of(game.sessions["ani"].char, "robot_pet", "pets")
    adopted = cmd(game, ani, "buy", item="little robot")
    assert adopted["text"].startswith(f"You adopt your new friend, little robot, for {price} credits!")
    assert abs(price - 600) <= 600 * 0.3
    pets = game.store.companions_of(game.sessions["ani"].char["id"])
    assert [(p["kind"], p["name"]) for p in pets] == [("robot_pet", "Bip")]
    assert cmd(game, ani, "buy", item="robot")["text"].startswith("You already have one")
    assert cmd(game, ani, "pet", op="name", a="Kiki")["text"] == "Your pet's name is Kiki now."
    walk(game, ani, "dock")
    monkeypatch.setattr(game.rng, "random", lambda: 0.0)
    budi.clear()
    cmd(game, ani, "pet", op="pat")
    assert budi.texts("emote")[-2:] == ["Ani pats Kiki.", budi.texts("emote")[-1]]
    assert "Kiki" in budi.texts("emote")[-1]
    assert "With them: Kiki the little robot." in cmd(game, budi, "look", a="Ani")["text"]


def test_the_temple_bell_plaque_and_lanterns(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    budi = join(game, "Budi")
    assert cmd(game, ani, "ring")["text"].startswith("Itu dilakukan di kuil Jalan Cahaya Bintang")
    for conn in (ani, budi):
        walk(game, conn, "star_hall")
    rung = cmd(game, ani, "ring")
    assert rung["sound"] == "bell" and rung["text"].startswith("Kamu membunyikan lonceng bintang.")
    assert budi.last()["text"] == "Ani rings the star bell. Three soft tones float across the dome."
    assert cmd(game, ani, "ring")["text"] == "Loncengnya masih bergetar. Biarkan sebentar."
    plaque = cmd(game, ani, "text", a="baca prasasti")["text"]
    assert plaque.startswith("JALAN CAHAYA BINTANG.") and plaque.count(".") >= 6
    lit = cmd(game, ani, "lantern")
    assert lit["sound"] == "lantern" and "1 lentera dinyalakan di sini hari ini" in lit["text"]
    assert game.sessions["ani"].char["credits"] == 97
    assert budi.last()["text"] == "Ani quietly lights a star lantern. 1 lanterns glow here today."
    clock.advance(31)
    cmd(game, budi, "lantern")
    assert "2 lanterns have been lit here today." in cmd(game, budi, "look", a="lanterns")["text"]
    assert game.flows["spent"]["lanterns"] == 6
