# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the station's markets (servers/orbit/orbit_econ.py): four market
# rooms, each buying and selling its own goods, "prices" and "list" said
# where the goods are traded, and anywhere else the way to the nearest
# market; the Promenade's signpost; a ship's scanner reading another world;
# a database from before the markets moved keeping its prices.

import json
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
from tests.test_orbit_server import FakeConn, clock, cmd, join, make_game, walk, world  # noqa: E402,F401
from tests.test_orbit_worlds import to_world, with_ship  # noqa: E402

STATION_MARKETS = {
    "spice_market": {"coffee", "spices", "kangkung", "chilli", "tomato", "strawberry", "vanilla", "dragonfruit",
                     "moonmelon", "golden_chilli", "red_quinoa", "moonpetal"},
    "ice_depot": {"ice", "helium3", "frostpearl"},
    "mineral_exchange": {"iron", "nickel", "titanium", "platinum", "quantum", "meteorite", "rustsalt",
                         "ember_crystal"},
    "workshop": {"scrap", "circuit", "satchip", "goldfoil", "chips"},
}


def char_of(game, name):
    return game.sessions[name.lower()].char


def give(game, name, **goods):
    inv = char_of(game, name)["inventory"]
    for gid, n in goods.items():
        inv[gid] = inv.get(gid, 0) + n


# ------------------------------------------------------------
# The layout
# ------------------------------------------------------------

def test_the_station_trades_at_four_markets_each_with_its_own_goods(world):
    station = {lid: m for lid, m in world.markets.items() if world.world_of(lid) == "station"}
    assert {lid: m["buys"] for lid, m in station.items()} == STATION_MARKETS
    assert {lid: m["sells"] for lid, m in station.items()} == STATION_MARKETS
    legal = {gid for gid, good in world.goods.items() if good.get("kind", "trade") != "contraband"}
    assert set().union(*STATION_MARKETS.values()) == legal            # every good somewhere, once
    assert "promenade" not in world.markets and world.locations["promenade"]["objects"]["signpost"]["markets"]
    for lid in STATION_MARKETS:
        loc = world.locations[lid]
        assert loc["landmark"] and loc["market"]["about"]["en"]
    # Each market is a real room on the plan: next to the room it belongs with.
    assert world.exits["hydroponics"]["w"]["to"] == "spice_market"
    assert world.exits["dock"]["n"]["to"] == "mineral_exchange"
    assert world.exits["cargo"]["n"]["to"] == "ice_depot"
    assert world.exits["mineral_exchange"]["e"]["to"] == "ice_depot"
    # Other worlds' markets keep their goods; the Belt's old miner only buys ore.
    assert world.markets["belt"]["sells"] == set() and "iron" in world.markets["belt"]["buys"]
    assert world.market_factor("belt", "iron") == 0.75 and world.market_factor("spice_market", "coffee") == 1.0
    assert world.markets["back_alley"]["sells"] == {"star_orchid", "ghost_chip"}


def test_a_good_is_traded_at_one_market_on_each_world(world):
    for change, why in ((lambda d: d["locations"]["cargo"].update(market={"buys": ["coffee"]}), "traded at both"),
                        (lambda d: d["locations"]["cargo"].update(market={"buys": ["unicorn"]}), "unknown"),
                        (lambda d: d["locations"]["cargo"].update(market={"sells": ["ice"], "prices": {"iron": 2}}),
                         "doesn't deal in"),
                        (lambda d: d["locations"]["cargo"].update(market={"buys": []}), "deals in nothing")):
        data = json.loads(json.dumps(world.data))
        change(data)
        with pytest.raises(orbit_world.WorldError, match=why):
            orbit_world.World(data, world.economy, world.npcs)
    # "market": true still means every legal good (a world of one's own may use it).
    data = json.loads(json.dumps(world.data))
    for lid in STATION_MARKETS:
        data["locations"][lid].pop("market")
    data["locations"]["promenade"]["market"] = True
    old = orbit_world.World(data, world.economy, world.npcs)
    assert old.markets["promenade"]["buys"] == set().union(*STATION_MARKETS.values())


# ------------------------------------------------------------
# Listing and trading where you stand
# ------------------------------------------------------------

@pytest.mark.parametrize("lid", sorted(STATION_MARKETS))
def test_each_market_lists_and_trades_only_its_own_goods(make_game, lid):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    char_of(game, "ani")["credits"] = 100_000
    walk(game, ani, lid)
    own = STATION_MARKETS[lid]
    listed = cmd(game, ani, "prices")["text"]
    assert listed.startswith(f"Prices {game.world.locations[lid]['in']['en']}, in credits for one. ")
    assert cmd(game, ani, "list")["text"] == listed                     # list is the same here
    for gid, good in game.world.goods.items():
        assert (f"{good['one']['en']}, buy " in listed) == (gid in own), gid
    mine, other = sorted(own)[0], "coffee" if lid != "spice_market" else "iron"
    bought = cmd(game, ani, "buy", item=game.world.goods[mine]["names"]["en"][0])
    assert bought["k"] == "trade", bought
    sold = cmd(game, ani, "sell", item=game.world.goods[mine]["names"]["en"][0])
    assert sold["k"] == "trade", sold
    word = game.world.goods[other]["names"]["en"][0]
    refused = cmd(game, ani, "buy", item=word)
    assert refused["k"] == "error" and refused["text"].startswith(
        f"You can't buy {game.world.goods[other]['many']['en']} here. Nearest market for {word}: ")
    give(game, "ani", **{other: 1})
    refused = cmd(game, ani, "sell", item=word)
    assert refused["text"].startswith(f"Nobody here buys {game.world.goods[other]['many']['en']}. Nearest market")
    asked = cmd(game, ani, "prices", a=word)
    assert asked["text"].startswith(f"No trade in {word} here. Nearest market for {word}: ")


def test_the_market_list_by_kind_and_by_good(make_game):
    game = make_game()
    ani = join(game, "Ani")
    sari = join(game, "Sari", lang="id")
    for conn in (ani, sari):
        walk(game, conn, "spice_market")
    coffee = cmd(game, ani, "prices", a="coffee")["text"]
    buy = game.market_unit("spice_market", "coffee", char_of(game, "ani"), "buy")
    sell = game.market_unit("spice_market", "coffee", char_of(game, "ani"), "sell")
    assert coffee == (f"Prices at the Spice Market, in credits for one. Trade goods: sack of coffee, buy {buy}, "
                      f"sell {sell}. Traders get better prices, and prices change every few minutes.")
    crops = cmd(game, sari, "prices", a="crops")["text"]          # Sari's client asked for Indonesian: English
    assert crops.startswith("Prices at the Spice Market, in credits for one. Crops: bunch of water spinach, buy ")
    assert "coffee" not in crops
    assert cmd(game, sari, "prices", a="vegetables")["text"] == crops
    ore = cmd(game, sari, "prices", a="ore")["text"]
    assert ore == ("No trade in ore here. Nearest market for ore: the Ice Depot, 2 east, down, west, then north; "
                   "the Mineral Exchange, 2 east, down, west, north, then west.")   # two markets; the slide
    assert cmd(game, sari, "prices", a="bijih")["text"] == "No market sells bijih."      # not a word any more


def test_the_belt_only_buys_ore(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    cmd(game, ani, "board")
    clock.advance(31)
    game.tick()
    listed = cmd(game, ani, "prices")["text"]
    iron = game.market_unit("belt", "iron", char_of(game, "ani"), "sell")
    assert listed.startswith(f"Prices on the Belt Platform, in credits for one. Ore: block of comet ice, sell ")
    assert f"lump of iron ore, sell {iron};" in listed and ", buy " not in listed


# ------------------------------------------------------------
# Away from a market: the nearest one, and the way
# ------------------------------------------------------------

def test_prices_away_from_a_market_point_to_the_nearest(make_game):
    game = make_game()
    ani = join(game, "Ani")
    sari = join(game, "Sari", lang="id")
    for conn in (ani, sari):
        walk(game, conn, "promenade")
    assert cmd(game, sari, "prices", a="coffee")["text"] == (
        "You're not at a market. Nearest market for coffee: the Spice Market, north, then 2 west.")
    assert cmd(game, sari, "prices", a="kopi")["text"] == "No market sells kopi."
    assert cmd(game, ani, "prices", a="coffee")["text"] == (
        "You're not at a market. Nearest market for coffee: the Spice Market, north, then 2 west.")
    assert cmd(game, ani, "prices", a="meteorite")["text"] == (
        "You're not at a market. Nearest market for meteorite: the Mineral Exchange, north, down, west, north, "
        "then west.")
    assert cmd(game, ani, "prices")["text"] == (
        "You're not at a market. Markets near you: the Spice Market (coffee, spices and crops), north, then 2 west; "
        "the Ice Depot (comet ice, helium-3 and frost pearls), north, down, west, then north; the Workshop "
        "(salvage and memory chips), north, down, then 2 east; the Mineral Exchange (ores and meteorites), north, "
        "down, west, north, then west.")
    assert cmd(game, ani, "prices", a="ore")["text"] == (
        "You're not at a market. Nearest market for ore: the Ice Depot, north, down, west, then north; "
        "the Mineral Exchange, north, down, west, north, then west.")
    # Buying and selling away from a market say the same.
    give(game, "ani", iron=2)
    assert cmd(game, ani, "sell", item="iron", n=2)["text"].startswith(
        "You're not at a market. Nearest market for iron: the Mineral Exchange, ")
    assert cmd(game, ani, "buy", item="coffee")["text"].startswith(
        "You're not at a market. Nearest market for coffee: the Spice Market, north, then 2 west.")
    assert cmd(game, ani, "prices", a="unicorns")["text"] == "No market sells unicorns."
    assert cmd(game, ani, "prices", a="mapper")["text"] == "Look for pocket mappers at Star Supply."


def test_the_way_to_the_market_is_the_nearest_one(make_game):
    game = make_game()
    ani = join(game, "Ani")
    assert cmd(game, ani, "way", a="the market")["text"].startswith("To the Mineral Exchange: north.")
    sari = join(game, "Sari", lang="id")
    walk(game, sari, "promenade")
    assert cmd(game, sari, "way", a="market")["text"].startswith("To the Spice Market: north, then 2 west.")


def test_the_promenade_signpost_shows_every_market(make_game):
    game = make_game()
    sari = join(game, "Sari", lang="id")
    walk(game, sari, "promenade")
    look = cmd(game, sari, "look")["text"]
    assert "A signpost in the middle points the way to the station's markets" in look
    sign = cmd(game, sari, "look", a="signpost")["text"]
    assert sign.startswith("The signpost points to the station's markets: the Spice Market (coffee, spices and "
                           "crops), north, then 2 west; ")
    assert "the Ice Depot (comet ice, helium-3 and frost pearls), " in sign
    assert "the Workshop (salvage and memory chips)" in sign


def test_shops_and_the_pawn_list_their_own(make_game):
    game = make_game()
    ani = join(game, "Ani")
    walk(game, ani, "shop")
    listed = cmd(game, ani, "prices")["text"]
    assert listed.startswith("Star Supply sells devices (") and listed == cmd(game, ani, "list")["text"]
    assert cmd(game, ani, "prices", a="seeds")["text"] == cmd(game, ani, "list", a="seeds")["text"]
    mapper = cmd(game, ani, "prices", a="mapper")["text"]
    assert mapper.startswith("Star Supply, prices in credits: pocket mapper, ") and ";" not in mapper
    assert cmd(game, ani, "prices", a="coffee")["text"].startswith(
        "You're not at a market. Nearest market for coffee: the Spice Market, ")
    walk(game, ani, "pawn")
    assert cmd(game, ani, "prices")["text"] == cmd(game, ani, "list")["text"]
    give(game, "ani", mapper=1)
    assert cmd(game, ani, "prices")["text"].startswith("Second Orbit would pay, in credits: pocket mapper, ")


def test_a_market_you_may_not_ask_the_way_to_is_named_by_its_place(make_game):
    game = make_game()
    ani = join(game, "Ani")
    to_world(game, ani, "bazaar")
    walk(game, ani, "bazaar_lookout")
    orchid = cmd(game, ani, "prices", a="star orchid")["text"]
    assert orchid == ("You're not at a market. Nearest market for star orchid: the Back Alley, in the Drift Bazaar.")
    give(game, "ani", holomapper=1)                          # a holo mapper knows the way to every public room
    assert cmd(game, ani, "prices", a="star orchid")["text"].startswith(
        "You're not at a market. Nearest market for star orchid: the Back Alley, south, ")
    to_world(game, ani, "pixel")
    assert cmd(game, ani, "prices")["text"] == "You're not at a market. There's no market on Pixel Pier."
    assert cmd(game, ani, "prices", a="coffee")["text"] == (
        "You're not at a market. There's no market for coffee on Pixel Pier.")


def test_a_ships_scanner_still_reads_another_world(make_game):
    game = make_game()
    ani = join(game, "Ani")
    assert cmd(game, ani, "prices", a="glasir")["text"].startswith("To read the prices Glasir Station from here")
    with_ship(game, ani, "ship_hornbill", level=12)
    walk(game, ani, "hangar")
    cmd(game, ani, "embark")
    report = cmd(game, ani, "prices", a="glasir")
    assert report["text"].startswith("Scanner report from Glasir Station, in credits for one: "
                                     "the Ice Traders' Post: sack of coffee, buy ")
    assert report["sound"] == "scan"
    here = cmd(game, ani, "prices")["text"]                    # aboard, docked on the station: its markets
    assert here.startswith("Scanner report from the station, in credits for one: the Mineral Exchange: ")


def test_the_trader_report_and_the_residents_name_the_market(make_game):
    game = make_game()
    tina = join(game, "Tina", "trader")
    game.market.prices["spices"] = 25 * 0.5
    game.market.prices["chips"] = 60 * 1.5
    assert cmd(game, tina, "work")["text"] == (
        "Market report. Good to buy: jars of spices, 50 percent below the usual price, at the Spice Market. "
        "Good to sell: memory chips, 50 percent above the usual price, in the Workshop.")
    walk(game, tina, "cantina")
    words = cmd(game, tina, "ask", to="Rocco", a="market")["words"]
    assert "at the Spice Market" in words or "in the Workshop" in words


def test_goods_at_the_pawn_shop_and_things_at_a_market(make_game):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", iron=1, mapper=1)
    walk(game, ani, "mineral_exchange")
    assert cmd(game, ani, "sell", item="mapper")["text"] == (
        "Markets buy goods. Things like pocket mappers are bought by Second Orbit, the pawn shop on the Mall Ring.")
    walk(game, ani, "pawn")
    assert cmd(game, ani, "sell", item="iron")["text"].startswith(
        "Goods are sold at a market, not here. Nearest market for iron: the Mineral Exchange, ")


# ------------------------------------------------------------
# A database from before the markets moved
# ------------------------------------------------------------

def test_a_version_8_database_keeps_its_prices_at_the_new_markets(tmp_path, world, clock, make_game):
    path = str(tmp_path / "orbit.db")
    before = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert before.version() == 8
    before.set_json("market", {"prices": {"coffee": 15.5, "iron": 5.0}, "next": 0,
                               "overrides": {"meteorite": {"price": 99.0, "until": clock() + 3600}}})
    before.set_json("market_worlds", {"glasir": {"ice": 1.2}})
    before.close()
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 8
    db.close()
    game = make_game(path)
    assert game.store.version() == orbit_store.SCHEMA_VERSION == 8 and game.store.migrated_from is None
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".bak")]          # nothing to migrate
    assert game.market.prices["coffee"] == 15.5 and game.market.local["glasir"]["ice"] == 1.2
    ani = join(game, "Ani")
    char = char_of(game, "ani")
    walk(game, ani, "promenade")                                # where the old market was
    assert cmd(game, ani, "prices", a="coffee")["text"].startswith("You're not at a market. Nearest market for coffee")
    walk(game, ani, "spice_market")
    fees = game.fees_for(char)
    assert game.market_unit("spice_market", "coffee", char, "sell") == \
        game.market.unit_price("coffee", "pilot", "sell", fees, 1.0, "station")
    char["inventory"]["coffee"] = 2
    total = game.market.quote("coffee", "pilot", "sell", 2)            # from the stored price
    sold = cmd(game, ani, "sell", item="coffee", n=2)
    assert sold["text"].startswith(f"You sell 2 sacks of coffee for {total} credits.")
    walk(game, ani, "mineral_exchange")                         # the admin's price for the hour still holds
    assert f"meteorite shard, buy {game.market.unit_price('meteorite', 'pilot', 'buy')}," in \
        cmd(game, ani, "prices", a="meteorite")["text"]
    assert game.market.price("meteorite") == 99.0
