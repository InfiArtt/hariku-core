# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Orbit's other worlds (stage 3 of Orbit 1.1): every world's map and the
# travel links between them, the Gate, the ferry, players' own ships, each
# world's market and trade runs, customs, and the worlds' own work.

import os
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
from tests.test_orbit_map import give, wear  # noqa: E402
from tests.test_orbit_server import (FakeConn, clock, cmd, join, make_game, walk, world)  # noqa: E402,F401


def char_of(game, name):
    return game.sessions[name.lower()].char


def said(conn):
    return [m for m in conn.sent if m.get("sound") != "achievement"][-1]


def to_world(game, conn, wid, credits=5000):
    """Put a player at a world's port by the Gate (paying for it)."""
    char = conn.session.char
    char["credits"] = max(char["credits"], credits)
    walk(game, conn, game.world.worlds[game.world_here(char)]["gate"])
    cmd(game, conn, "gate", a=wid)
    assert char["location"] == game.world.worlds[wid]["gate"], conn.sent[-3:]


def with_ship(game, conn, model="ship_swiftlet", level=8):
    char = conn.session.char
    char["xp"] = game.xp_for_level(level)
    char["credits"] = 100000
    walk(game, conn, "shipyard")
    bought = cmd(game, conn, "buy", item=game.world.things[model]["names"]["en"][0])
    assert bought["k"] == "trade", bought
    return game.store.ship_of(char["id"])


# ------------------------------------------------------------
# The maps and the links between them
# ------------------------------------------------------------

def test_every_world_has_its_own_map_joined_to_the_others(world):
    assert set(world.worlds) == {"station", "belt", "moon", "karmina", "glasir", "bazaar", "evergrove", "lumina",
                                 "pixel"}
    for wid, info in world.worlds.items():
        rooms = {lid for lid, loc in world.locations.items() if world.world_of(lid) == wid}
        assert info["port"] in rooms and all(info.get(k) in rooms for k in ("ferry", "gate") if info.get(k))
        inside = world.reachable(info["port"], travel=False)
        assert rooms <= inside, (wid, rooms - inside)
        for lid in rooms:                                     # and back from every room
            assert info["port"] in world.reachable(lid, travel=False), (wid, lid)
        if wid not in ("station", "belt"):
            assert 6 <= len(rooms) <= 15, (wid, len(rooms))
            assert world.locations[info["port"]].get("landmark") and world.locations[info["port"]].get("port")
            ambiences = {world.locations[lid]["ambience"] for lid in rooms}
            assert ambiences - {"space", "cantina", "venue", "garden"}, wid       # a sound of its own
        for lid in rooms:
            if world.locations[lid].get("airless"):
                rescue = world.areas[world.locations[lid]["area"]]["rescue"]
                assert world.world_of(rescue) == wid and not world.locations[rescue].get("airless"), lid
    # every world can be reached from the station by the Gate, the ferry or a ship, and back
    places = {lid for lid, loc in world.locations.items() if not loc.get("hidden")}
    assert world.reachable() == places
    for a in world.worlds:
        for b in world.worlds:
            assert world.distance(a, b) == world.distance(b, a) >= 1
    gates = [w for w, info in world.worlds.items() if info.get("gate")]
    ferries = [w for w, info in world.worlds.items() if info.get("ferry")]
    assert set(gates) == set(ferries) == set(world.worlds) - {"belt"}          # the Kancil serves the Belt


def test_the_worlds_are_found_by_their_names(world):
    for text, wid in (("bulan", "moon"), ("the Moon", "moon"), ("planet merah", "karmina"), ("Karmina", "karmina"),
                      ("bulan es", "glasir"), ("pasar apung", "bazaar"), ("drift bazaar", "bazaar"),
                      ("rimba abadi", "evergrove"), ("neon city", "lumina"), ("kota lumina", "lumina"),
                      ("arcade world", "pixel"), ("stasiun", "station"), ("atlantis", None)):
        assert world.find_world(text) == wid, text


def test_a_world_without_a_port_is_refused(world):
    data = dict(world.data)
    data["worlds"] = dict(world.worlds, moon=dict(world.worlds["moon"], port="dock"))
    with pytest.raises(orbit_world.WorldError, match="moon: its port"):
        orbit_world.World(data, world.economy)


# ------------------------------------------------------------
# The Gate and the ferry
# ------------------------------------------------------------

def test_the_gate_is_quick_and_dear(make_game):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    char = char_of(game, "Ani")
    assert cmd(game, ani, "gate", a="karmina")["text"].startswith("The Gate is in the Gate Hall.")
    walk(game, ani, "gate_hall")
    walk(game, budi, "gate_hall")
    char["credits"] = 50
    assert cmd(game, ani, "gate", a="karmina")["text"] == "The Gate charges 85 credits for that, and you have 50."
    assert cmd(game, ani, "gate", a="atlantis")["text"].startswith("The Gate to where? It opens to ")
    char["credits"] = 500
    budi.clear()
    arrived = cmd(game, ani, "gate", a="the red planet")
    assert char["location"] == "karmina_port" and char["credits"] == 500 - 85
    assert arrived["k"] == "moved" and arrived["sound"] == "gate" and arrived["amb"] == "colony"
    assert "Ani steps into the Gate's light and is gone, off to Karmina Colony." in budi.texts("leave")
    assert game.flows["spent"]["gate"] == 85
    # "pergi ke gerbang ke Bulan" (what Orbit 1.0 sends as go) works too
    cmd(game, ani, "go", a="gerbang ke Bulan")
    assert char["location"] == "moon_port"


def test_the_ferry_is_slow_and_cheap(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    char = char_of(game, "Ani")
    cmd(game, ani, "ferry", a="bulan")
    assert char["location"] == "ferry" and char["credits"] == 100 - (5 + 3 * 2)
    trip = char["stats"]["ferry"]
    assert trip["depart"] % 120 == 0 and trip["depart"] - clock.now >= 10 and trip["arrive"] - trip["depart"] == 80
    assert "Feri ke Pangkalan Bulan Tranquility berangkat" in ani.texts("info")[-1]
    assert "berangkat" in cmd(game, ani, "look")["text"]
    assert cmd(game, ani, "move", d="n")["k"] == "error"                          # no walking about
    clock.now = trip["depart"] + 1
    game.tick()
    assert ani.texts("flight")[-1].startswith("Feri bertolak menuju Pangkalan Bulan Tranquility")
    assert cmd(game, ani, "disembark")["text"].startswith("Feri sudah berlayar")
    clock.now = trip["arrive"] + 1
    game.tick()
    assert char["location"] == "moon_port" and "ferry" not in char["stats"]
    # back again, but getting off before it leaves
    cmd(game, ani, "text", a="feri ke stasiun")
    assert char["location"] == "ferry"
    cmd(game, ani, "text", a="turun feri")
    assert char["location"] == "moon_port"


def test_a_ferry_trip_ends_while_you_are_away(tmp_path, make_game, clock):
    path = str(tmp_path / "orbit.db")
    game = make_game(path)
    ani = join(game, "Ani")
    cmd(game, ani, "ferry", a="glasir")
    arrive = char_of(game, "Ani")["stats"]["ferry"]["arrive"]
    cmd(game, ani, "bye")
    game.store.close()
    clock.now = arrive + 60
    game = make_game(path)
    again = join(game, "Ani")
    assert char_of(game, "Ani")["location"] == "glasir_port"
    assert "While you were away, the ferry arrived at Glasir Landing." in again.sent[1]["text"]


# ------------------------------------------------------------
# Ships
# ------------------------------------------------------------

def test_buying_a_ship_boarding_it_and_flying_it(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    char = char_of(game, "Ani")
    assert cmd(game, ani, "embark")["text"].startswith("You don't have a ship.")
    walk(game, ani, "shipyard")
    listed = cmd(game, ani, "list")["text"]
    assert listed.startswith("the Orbit Shipyard") and "Swiftlet shuttle" in listed and "(level 12)" in listed
    assert cmd(game, ani, "buy", item="swiftlet")["text"] == "Swiftlet shuttle needs level 2. Type rank to see yours."
    ship = with_ship(game, ani)
    assert (ship["model"], ship["dock"], ship["fuel"]) == ("ship_swiftlet", "hangar", 24)
    assert "captain" in game.store.achievements_of(char["id"])
    assert cmd(game, ani, "embark")["text"] == "Your ship is docked in the Hangar."
    walk(game, ani, "hangar")
    aboard = cmd(game, ani, "embark")
    assert char["location"] == "ship" and aboard["text"].startswith("You climb aboard your Swiftlet shuttle.")
    assert "Fuel 24 of 24. Hold 0 of 40: empty." in aboard["text"]
    assert cmd(game, ani, "move", d="n")["text"].startswith("You're aboard a ship")
    cmd(game, ani, "name_ship", a="Bintang Timur")
    took_off = cmd(game, ani, "fly", a="the moon")
    assert took_off["k"] == "flight" and took_off["sound"] == "launch"
    assert took_off["text"] == ("Engines on! You lift off for Moon Base Tranquility: 50 seconds of flight, "
                                "using 2 fuel (22 left).")
    ship = game.store.ship_of(char["id"])
    assert ship["dock"] == "" and ship["flight"]["to"] == "moon" and ship["fuel"] == 22
    assert cmd(game, ani, "disembark")["text"].startswith("Still flying: you land in")
    clock.advance(51)
    game.tick()
    landed = [m for m in ani.sent if m.get("k") == "flight"][-1]
    assert landed["text"].startswith("Touchdown: you've landed at Tranquility Port.") and landed["sound"] == "landing"
    assert game.store.ship_of(char["id"])["dock"] == "moon_port"
    cmd(game, ani, "disembark")
    assert char["location"] == "moon_port"
    # refuelling at the Moon's price
    refuelled = cmd(game, ani, "refuel")
    assert refuelled["text"].startswith("You buy 2 fuel for 4 credits: the tank holds 24 of 24.")
    assert cmd(game, ani, "refuel")["text"] == "Your tank is already full (24)."
    assert "Swiftlet shuttle Bintang Timur" in cmd(game, ani, "cargo")["text"]


def test_a_pilot_flies_faster_and_a_ship_lands_without_its_captain(tmp_path, make_game, clock):
    path = str(tmp_path / "orbit.db")
    game = make_game(path)
    ani = join(game, "Ani", "pilot")
    with_ship(game, ani)
    walk(game, ani, "hangar")
    took_off = cmd(game, ani, "fly", a="glasir")                  # at the ship: aboard, and off
    assert "8 fuel" in took_off["text"] and "2 minutes of flight" in took_off["text"]   # 25 x 8 x 0.75 s
    assert game.flying[game.store.ship_of(char_of(game, "Ani")["id"])["id"]] - clock.now == 150
    cmd(game, ani, "bye")
    game.store.close()
    clock.advance(200)
    game = make_game(path)
    game.tick()                                                   # the flight lands by itself
    assert game.store.ship_of(game.store.by_name("ani")["id"])["dock"] == "glasir_port"
    again = join(game, "Ani")
    assert char_of(game, "Ani")["location"] == "ship"
    cmd(game, again, "disembark")
    assert char_of(game, "Ani")["location"] == "glasir_port"


def test_friends_fly_along_when_invited(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    budi = join(game, "Budi")
    with_ship(game, ani)
    walk(game, ani, "hangar")
    walk(game, budi, "hangar")
    cmd(game, ani, "embark")
    assert cmd(game, budi, "embark", to="Ani")["text"].startswith("Ani hasn't invited you aboard.")
    cmd(game, ani, "invite", op="add", to="Budi")
    assert budi.last()["text"].startswith("Ani invites you aboard their ship, in the Hangar.")
    cmd(game, budi, "text", a="naik kapal Ani")
    assert char_of(game, "Budi")["location"] == "ship" and char_of(game, "Budi")["stats"]["visit"] == "ani"
    assert cmd(game, budi, "fly", a="moon")["text"] == "Only the ship's captain can do that."
    cmd(game, ani, "fly", a="moon")
    assert budi.texts("flight")[-1].startswith("Engines on!")
    clock.advance(60)
    game.tick()
    assert budi.texts("flight")[-1].startswith("Touchdown")
    cmd(game, budi, "disembark")
    assert char_of(game, "Budi")["location"] == "moon_port"


def test_trading_in_a_ship_for_a_bigger_one(make_game):
    game = make_game()
    ani = join(game, "Ani")
    old = with_ship(game, ani)
    char = char_of(game, "Ani")
    before = char["credits"]
    price = game.price_of(char, "ship_buffalo", "shipyard")
    upgraded = cmd(game, ani, "buy", item="buffalo")
    assert "less 1250 for your old Swiftlet shuttle" in upgraded["text"]
    assert char["credits"] == before - price + 1250
    ship = game.store.ship_of(char["id"])
    assert (ship["id"], ship["model"], ship["fuel"]) == (old["id"], "ship_buffalo", 60)


def test_the_hold_takes_what_your_bag_cannot(make_game):
    game = make_game()
    ani = join(game, "Ani", "trader")
    ship = with_ship(game, ani)
    char = char_of(game, "Ani")
    to_world(game, ani, "glasir")
    walk(game, ani, "glasir_market")
    cmd(game, ani, "buy", item="ice", n=15)
    assert cmd(game, ani, "buy", item="ice", n=10)["text"] == "Your bag holds at most 20 goods."
    # the ship docked here: the rest goes into its hold
    game.store.save_ship(dict(ship, dock="glasir_port"))
    bought = cmd(game, ani, "buy", item="ice", n=35)
    assert "30 blocks of comet ice went into your ship's hold." in bought["text"]
    assert char["inventory"]["ice"] == 20 and game.store.ship_of(char["id"])["cargo"] == {"ice": 30}
    assert cmd(game, ani, "buy", item="ice", n=20)["text"] == "Your bag and your ship's hold only have room for 10 more."
    sold = cmd(game, ani, "sell", item="ice", n=25)
    assert sold["text"].startswith("You sell 25 blocks of comet ice")
    assert "ice" not in char["inventory"] and game.store.ship_of(char["id"])["cargo"] == {"ice": 25}


def test_loading_and_unloading_the_hold(make_game):
    game = make_game()
    ani = join(game, "Ani")
    with_ship(game, ani)
    char = char_of(game, "Ani")
    for _ in range(5):
        give(game, "ani", "ice")
    walk(game, ani, "hangar")
    assert cmd(game, ani, "load", item="ice", n=2)["text"] == "You're not aboard a ship."
    cmd(game, ani, "embark")
    loaded = cmd(game, ani, "text", a="muat 3 es")
    assert loaded["text"] == "You load 3 blocks of comet ice into the hold: 3 of 40." and loaded["sound"] == "cargo"
    cmd(game, ani, "load", item="", n="all")
    assert "ice" not in char["inventory"] and game.store.ship_of(char["id"])["cargo"] == {"ice": 5}
    unloaded = cmd(game, ani, "unload", item="ice", n=4)
    assert unloaded["text"] == "You unload 4 blocks of comet ice into your bag: 4 of 20."
    assert cmd(game, ani, "unload", item="ice", n=9)["text"] == "The hold only has 1 block of comet ice."


# ------------------------------------------------------------
# Markets, trade runs and customs
# ------------------------------------------------------------

def test_every_world_has_its_own_prices(make_game, clock):
    game = make_game()
    market = game.market
    ice_glasir = market.unit_price("ice", "pilot", "buy", world="glasir")
    ice_karmina = market.unit_price("ice", "pilot", "sell", world="karmina")
    assert ice_karmina > 3 * ice_glasir                                           # a trade run
    before = market.local["glasir"]["ice"]
    market.trade("ice", "buy", 40, "glasir")
    assert market.local["glasir"]["ice"] == pytest.approx(before * 1.01 ** 40)
    assert market.local["karmina"]["ice"] == 1.0 and market.price("ice") == market.goods["ice"]["base"]
    for _ in range(30):                                                          # half an hour or so
        clock.advance(game.config["market_seconds"] + 1)
        market.tick(clock.now)
    assert abs(market.local["glasir"]["ice"] - 1.0) < 0.3
    assert set(game.store.get_json("market_worlds")) == set(game.world.worlds) - {"station"}


def test_prices_are_those_of_the_world_you_are_on(make_game):
    game = make_game()
    ani = join(game, "Ani")
    to_world(game, ani, "karmina")
    walk(game, ani, "kar_market")
    listed = cmd(game, ani, "prices")["text"]
    assert listed.startswith("Prices on Karmina. Market prices in credits")
    assert "Contraband" not in listed
    assert cmd(game, ani, "prices", a="glasir")["text"].startswith("To read the prices Glasir Station from here")
    to_world(game, ani, "bazaar")
    walk(game, ani, "back_alley")
    alley = cmd(game, ani, "prices")["text"]
    assert "Contraband: star orchid" in alley and "coffee" not in alley
    walk(game, ani, "bazaar_lookout")
    assert "Contraband" in cmd(game, ani, "prices")["text"]                    # the whole Bazaar's kinds


def test_customs_find_contraband_or_wave_you_through(make_game, monkeypatch):
    game = make_game()
    ani = join(game, "Ani")
    char = char_of(game, "Ani")
    to_world(game, ani, "bazaar")
    for _ in range(3):
        give(game, "ani", "star_orchid")
    char["credits"] = 1000
    monkeypatch.setattr(game.rng, "random", lambda: 0.99)        # not searched
    cmd(game, ani, "gate", a="karmina")
    assert "A customs officer glances at your bags and waves you through." in ani.texts("info")
    assert char["inventory"]["star_orchid"] == 3
    walk(game, ani, "karmina_port")
    monkeypatch.setattr(game.rng, "random", lambda: 0.0)         # searched
    cmd(game, ani, "gate", a="the moon")
    caught = [m for m in ani.sent if m.get("sound") == "customs"][-1]
    assert caught["text"].startswith("Customs! An officer finds 3 star orchids, takes them, and fines you 120 credits.")
    assert "star_orchid" not in char["inventory"] and game.flows["spent"]["fines"] == 120
    # the Bazaar and Evergrove have no customs at all
    for _ in range(2):
        give(game, "ani", "ghost_chip")
    cmd(game, ani, "gate", a="evergrove")
    assert char["inventory"]["ghost_chip"] == 2


def test_the_hornbill_scanner_bay_halves_the_chance_of_a_search(make_game):
    game = make_game()
    ship = {"model": "ship_hornbill", "cargo": {}}
    rules = game.econ["travel"]["customs"]
    assert game.ship_spec(ship)["scanner"] and rules["scanner_factor"] == 0.5
    assert rules["gate"] > rules["ferry"] > rules["ship"] > 0


# ------------------------------------------------------------
# The way there
# ------------------------------------------------------------

def test_asking_the_way_to_another_world(make_game):
    game = make_game()
    ani = join(game, "Ani")
    options = cmd(game, ani, "way", a="the Red Market")["text"]
    assert options.startswith("That's on another world: Karmina Colony, 6 away. Travel by the Gate in the Gate Hall "
                              "(85 credits, at once), the ferry at the Dock (23 credits, about 4 minutes) and or a "
                              "ship of your own") or "the Gate in the Gate Hall (85 credits, at once)" in options
    assert "Then from Karmina Spaceport, the way to the Red Market: north, then west." in options
    assert cmd(game, ani, "go", a="karmina")["text"].startswith("That's on another world: Karmina Colony")
    worlds = cmd(game, ani, "worlds")["text"]
    assert worlds.startswith("You're on the station. The worlds: the Asteroid Belt,")
    assert "Karmina, the red planet: water ice sells dear" in worlds and "6 away (Gate 85 and ferry 23)" in worlds
    # the Belt is still the Kancil's
    assert cmd(game, ani, "way", a="belt")["text"].startswith("To the Belt Platform")


# ------------------------------------------------------------
# The worlds' own work
# ------------------------------------------------------------

def test_facing_evergroves_creatures(make_game, monkeypatch, clock):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    char = char_of(game, "Ani")
    to_world(game, ani, "evergrove")
    assert cmd(game, ani, "face", a="sprite")["text"] == "Tidak ada makhluk di sini untuk dihadapi."
    walk(game, ani, "grove_wood")
    assert cmd(game, ani, "look", a="peri lumut")["text"].startswith("Peri seukuran ibu jari")
    monkeypatch.setattr(game.rng, "randint", lambda a, b: 3)
    lost = cmd(game, ani, "text", a="hadapi peri lumut")
    assert lost["k"] == "failed" and lost["outcome"] == "lose" and "butuh 6" in lost["text"]
    assert cmd(game, ani, "face", a="peri lumut")["text"].startswith("Makhluk-makhluk itu menjaga jarak")
    clock.advance(21)
    monkeypatch.setattr(game.rng, "randint", lambda a, b: 18)
    won = cmd(game, ani, "face", a="moss sprite")
    assert won["k"] == "paid" and won["sound"] == "creature" and "Kamu mendapat" in won["text"]
    assert char["stats"]["creatures"] == 1 and char["xp"] >= 5
    walk(game, ani, "grove_deep")
    assert cmd(game, ani, "face", a="beetle")["text"].startswith("Terlalu gelap")


def test_courier_gigs_in_lumina_city(make_game, monkeypatch, clock):
    game = make_game()
    ani = join(game, "Ani")
    char = char_of(game, "Ani")
    to_world(game, ani, "lumina")
    assert cmd(game, ani, "gig")["text"].startswith("Gigs are handed out at the Courier Hub.")
    walk(game, ani, "lumina_couriers")
    monkeypatch.setattr(game.rng, "choice", lambda seq: "lumina_skybar")
    taken = cmd(game, ani, "gig")
    assert taken["k"] == "task" and "to the Sky Bar" in taken["text"]
    pay = char["stats"]["gig"]["pay"]
    before = char["credits"]
    walk(game, ani, "lumina_skybar")
    assert char["credits"] == before + pay and "gig" not in char["stats"] and char["stats"]["gigs"] == 1
    assert any(m["text"].startswith("Delivered!") for m in ani.sent if m.get("k") == "paid")
    # too late
    clock.advance(31)
    walk(game, ani, "lumina_couriers")
    cmd(game, ani, "gig")
    clock.advance(1000)
    game.tick()
    assert ani.texts("failed")[-1].startswith("Too late: the parcel for the Sky Bar")


def test_mining_helium_and_collecting_on_other_worlds(make_game, monkeypatch, clock):
    game = make_game()
    ani = join(game, "Ani")
    char = char_of(game, "Ani")
    to_world(game, ani, "moon")
    walk(game, ani, "moon_tunnels")
    monkeypatch.setattr(game, "_pick", lambda table: next(iter(table)))
    mined = cmd(game, ani, "mine")
    assert "helium-3" in mined["text"] and char["inventory"]["helium3"] >= 1
    to_world(game, ani, "karmina")
    walk(game, ani, "kar_farms")
    cmd(game, ani, "collect")
    assert char["inventory"]["red_quinoa"] == 1


def test_globetrotter_after_every_world(make_game):
    game = make_game()
    ani = join(game, "Ani")
    char = char_of(game, "Ani")
    char["stats"]["map"] = [info["port"] for info in game.world.worlds.values()]
    cmd(game, ani, "look")
    assert "globetrotter" in game.store.achievements_of(char["id"])
    assert char["inventory"]["title_globetrotter"] == 1


# ------------------------------------------------------------
# The database
# ------------------------------------------------------------

def test_a_version_2_database_gets_the_ships_table(tmp_path, clock, monkeypatch):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    with monkeypatch.context() as m:
        m.setattr(orbit_store, "SCHEMA_VERSION", 2)
        m.setattr(orbit_store.Store, "_migrate_3", lambda self: None)
        orbit_store.Store(path, clock=clock, iterations=1000, durable=False).close()
    store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert store.version() == orbit_store.SCHEMA_VERSION and store.migrated_from == 2
    ship = store.add_ship(1, "ship_swiftlet", "", "hangar", 24)
    ship["cargo"] = {"ice": 3, "coffee": 0}
    ship["flight"] = {"to": "moon", "arrive": 5.0}
    store.save_ship(ship)
    again = store.ship_of(1)
    assert again["cargo"] == {"ice": 3} and again["flight"]["to"] == "moon"
    assert [s["id"] for s in store.flying_ships()] == [ship["id"]]
    store.close()
    backup = sqlite3.connect(path + f".before-v{orbit_store.SCHEMA_VERSION}.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 2
    backup.close()
    assert isinstance(FakeConn(), FakeConn)
