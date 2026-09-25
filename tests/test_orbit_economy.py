# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for Orbit's economy and progress (servers/orbit), with a fixed clock
# and a seeded random generator: XP, levels, ranks and the keycards levels
# bring; the daily bonus and its streak; the farm and its real-time crops;
# mining and salvage; the scientist's and the security officer's mini-games;
# selling at the market and to the Belt's ore buyer; the voice others hear;
# the economy's totals and the admins' tools; moving a character to another
# computer; and migrating a database from Orbit 1.0.

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

import orbit_admin  # noqa: E402
import orbit_game  # noqa: E402
import orbit_store  # noqa: E402
from tests.test_orbit_map import give, wear  # noqa: E402
from tests.test_orbit_server import (UTC, FakeConn, clock, cmd, join, make_game,  # noqa: E402,F401
                                     secret_of, walk, world)


def char_of(game, name):
    return game.sessions[name.lower()].char


# ------------------------------------------------------------
# Levels and ranks
# ------------------------------------------------------------

def test_levels_grow_further_apart_and_stop_at_the_top(make_game):
    game = make_game()
    assert [game.xp_for_level(n) for n in (1, 2, 3, 4, 5, 10, 20)] == [0, 60, 180, 360, 600, 2700, 11400]
    assert [game.level_of(xp) for xp in (0, 59, 60, 179, 180, 11399, 11400, 10 ** 9)] == \
        [1, 1, 2, 2, 3, 19, 20, 20]


def test_levels_raise_pay_name_ranks_and_hand_out_keycards(make_game):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    session = game.sessions["ani"]
    game.award_xp(session, 60)
    up = [m for m in ani.events("paid") if m.get("sound") == "levelup"][-1]
    assert up["text"] == "Level up! You're level 2 now: trainee engineer. Your pay is up 3 percent."
    assert ani.last()["text"] == "For reaching level 2, you get your crew keycard."
    game.award_xp(session, 120)
    assert "technician keycard" in ani.last()["text"]              # engineers only, at level 3
    assert game.rank_name(session.char) == {"en": "engineer", "id": "insinyur"}
    session.char["xp"] = game.xp_for_level(10)
    assert game.rank_name(session.char)["en"] == "chief engineer"
    assert game.pay(session.char, 100) == 127
    give(game, "ani", "wrench")
    assert game.pay(session.char, 100) == 137                       # the tool: a tenth more
    rank = cmd(game, ani, "rank")["text"]
    assert rank.startswith("Rank: chief engineer. Level 10, 2700 XP; 600 more to level 11. Pay: plus 37 percent.")
    assert rank.endswith("Next rank: master engineer, at level 15.")
    pilot = join(game, "Pip", "pilot")
    game.award_xp(game.sessions["pip"], 180)
    assert "keycard_tech" not in char_of(game, "pip")["inventory"]


def test_the_reactor_core_pays_more_for_one_more_tone(make_game):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    give(game, "ani", "keycard_tech")
    walk(game, ani, "reactor_core")
    codes = cmd(game, ani, "work")["codes"]
    assert len(codes) == 4
    paid = cmd(game, ani, "answer", a=" ".join(map(str, codes)))
    assert "You're paid 50 credits" in paid["text"] and char_of(game, "ani")["xp"] == 12


# ------------------------------------------------------------
# The daily bonus
# ------------------------------------------------------------

def test_the_daily_bonus_grows_with_a_streak_and_resets(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    first = cmd(game, ani, "daily")
    assert first["text"] == "Daily bonus: 40 credits, for a 1-day streak. You have 140." and first["sound"] == "daily"
    again = cmd(game, ani, "daily")
    assert again["k"] == "error" and again["text"].startswith("You've had today's bonus (a 1-day streak).")
    pays = []
    for _day in range(8):
        clock.advance(86400)
        pays.append(int(cmd(game, ani, "daily")["text"].split(": ")[1].split()[0]))
    assert pays == [55, 70, 85, 100, 115, 130, 130, 130]          # capped after a week
    assert char_of(game, "ani")["inventory"]["seed_strawberry"] == 3     # the seventh day's gift
    clock.advance(2 * 86400)                                       # a day missed
    assert cmd(game, ani, "daily")["text"].startswith("Daily bonus: 40 credits, for a 1-day streak.")
    assert game.flows["earned"]["daily"] == 40 + sum(pays) + 40


def test_the_daily_bonus_waits_on_join(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    game.dropped(ani)
    game._remove(game.sessions["ani"])
    back = join(game, "Ani")
    assert "Your daily bonus is waiting: type daily." in back.sent[1]["text"]


# ------------------------------------------------------------
# The farm
# ------------------------------------------------------------

def test_crops_grow_in_real_time_and_ripen_while_you_watch(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "seed_tomato", "seed_tomato", "seed_tomato")
    assert cmd(game, ani, "plant", item="tomat")["text"] == "Farming is done in Hydroponics."
    walk(game, ani, "hydroponics")
    planted = cmd(game, ani, "plant", item="tomato")
    assert planted["text"] == ("You plant crates of tomatoes in 2 plots. They'll be ripe in 60 minutes. "
                               "Water them for a bigger crop.") and planted["sound"] == "plant"
    assert char_of(game, "ani")["inventory"]["seed_tomato"] == 1
    assert cmd(game, ani, "plant", item="tomato")["text"].startswith("All your plots are in use.")
    watered = cmd(game, ani, "water")
    assert watered["text"] == "You water 2 plots. The leaves perk up."
    assert cmd(game, ani, "water")["text"] == "Nothing needs water right now."
    assert cmd(game, ani, "harvest")["text"] == "Nothing's ripe yet. The first crop is ready in 60 minutes."
    farm = cmd(game, ani, "farm")["text"]
    assert farm == ("Your 2 plots: 1, crates of tomatoes, ripe in 60 minutes, watered; "
                    "2, crates of tomatoes, ripe in 60 minutes, watered.")
    clock.advance(3601)
    game.tick()
    ripe = ani.last()
    assert ripe["text"] == "Your crops are ripe in Hydroponics: crates of tomatoes." and ripe["sound"] == "ripe"
    game.tick()
    assert ani.last() is ripe                                     # said once
    plots = [p["yield"] for p in char_of(game, "ani")["stats"]["farm"]]
    harvest = cmd(game, ani, "harvest")
    assert harvest["k"] == "paid" and harvest["sound"] in ("harvest", "rare")
    assert char_of(game, "ani")["inventory"]["tomato"] == sum(plots)
    assert all(5 <= y <= 6 for y in plots)                       # 4 to 5, and one for the water
    assert char_of(game, "ani")["harvested"] == sum(plots)


def test_the_bag_limits_a_harvest_and_the_rest_waits(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "seed_kangkung", "seed_kangkung")
    char_of(game, "ani")["inventory"]["iron"] = 18
    walk(game, ani, "hydroponics")
    cmd(game, ani, "plant", item="kangkung")
    clock.advance(601)
    harvest = cmd(game, ani, "harvest")
    assert harvest["text"] == "You harvest 2 bunches of kangkung. Your bag is full; 2 plots still have a crop waiting."
    char_of(game, "ani")["inventory"].pop("iron")
    assert "bunches of kangkung" in cmd(game, ani, "harvest")["text"]


def test_farm_tools_and_more_plots(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "sprinkler", "grow_lamp", "seed_chilli")
    walk(game, ani, "hydroponics")
    planted = cmd(game, ani, "plant", item="bibit cabai")
    assert planted["text"] == ("You plant bags of chillies in 1 plots, and your sprinkler waters them. "
                               "They'll be ripe in 24 minutes.")
    char_of(game, "ani")["credits"] = 1000
    assert cmd(game, ani, "buy", item="petak")["text"].startswith("You buy one more plot in Hydroponics for 150")
    assert game.plot_count(char_of(game, "ani")) == 3
    give(game, "ani", "seed_moonmelon")
    assert cmd(game, ani, "plant", item="melon bulan")["text"] == "packet of moon melon seeds needs level 8. Type rank to see yours."


def test_a_golden_chilli_now_and_then(make_game, clock, monkeypatch):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "seed_kangkung")
    walk(game, ani, "hydroponics")
    cmd(game, ani, "plant", item="kangkung")
    clock.advance(601)
    monkeypatch.setattr(game.rng, "random", lambda: 0.0)
    harvest = cmd(game, ani, "harvest")
    assert harvest["text"].endswith("Among the leaves, something glints: a golden chilli!") and harvest["sound"] == "rare"
    assert char_of(game, "ani")["inventory"]["golden_chilli"] == 1


# ------------------------------------------------------------
# Mining and salvage
# ------------------------------------------------------------

def _to_belt(game, conn, clock):
    cmd(game, conn, "board")
    clock.advance(31)
    game.tick()
    assert game.sessions[conn.session.key].char["location"] == "belt"


def test_mining_has_a_break_a_bag_and_better_drills(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    assert cmd(game, ani, "mine")["text"] == "Mining is done at the Belt Platform: ride the Kancil from the Dock."
    _to_belt(game, ani, clock)
    mined = cmd(game, ani, "mine")
    assert mined["k"] == "paid" and mined["sound"] in ("mine", "rare") and "Next strike in 25 seconds." in mined["text"]
    assert cmd(game, ani, "mine")["text"].startswith("You've just worked. Take a break: you can work again in 25")
    assert char_of(game, "ani")["mined"] in (1, 2)
    give(game, "ani", "drill_plasma")
    clock.advance(26)
    assert "Next strike in 16 seconds." in cmd(game, ani, "mine")["text"]
    char_of(game, "ani")["inventory"]["scrap"] = 20
    clock.advance(17)
    assert cmd(game, ani, "mine")["text"] == "Your bag holds at most 20 goods."


def test_the_ore_tables_follow_their_weights(make_game):
    game = make_game()
    game.rng = random.Random(1234)
    table = game.econ["mining"]["tables"]["platform"]["1"]
    counts = {}
    for _ in range(4000):
        ore = game._pick(table)
        counts[ore] = counts.get(ore, 0) + 1
    total = sum(table.values())
    for ore, weight in table.items():
        assert abs(counts.get(ore, 0) / 4000 - weight / total) < 0.03, ore
    # Better drills and deeper places find more of the rare ores.
    def rare_share(spot, tier):
        t = game.econ["mining"]["tables"][spot][tier]
        return sum(w for o, w in t.items() if o in ("platinum", "meteorite", "quantum")) / sum(t.values())
    assert rare_share("platform", "1") < rare_share("platform", "3") < rare_share("rim", "3") < rare_share("cave", "3")


def test_the_rim_needs_air_and_the_cave_needs_light(make_game, clock, monkeypatch):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    _to_belt(game, ani, clock)
    assert cmd(game, ani, "move", d="s")["text"].startswith("The airlock won't open")
    give(game, "ani", "eva_suit")
    wear(game, ani, "eva suit")
    assert cmd(game, ani, "move", d="s")["room"] == "belt_rim"
    cmd(game, ani, "move", d="d")
    assert cmd(game, ani, "mine")["text"] == "It's too dark to see the veins. Wear a headlamp."
    give(game, "ani", "headlamp")
    wear(game, ani, "headlamp")
    monkeypatch.setattr(game.rng, "random", lambda: 0.0)          # the luckiest strike there is
    lucky = cmd(game, ani, "mine")
    assert lucky["text"].startswith("You hit a rich vein: 2 lumps of iron ore!")
    assert lucky["text"].endswith("And wedged in the rock, something heavy and old: a brass key!")
    assert lucky["sound"] == "rare" and char_of(game, "ani")["inventory"]["brass_key"] == 1
    clock.advance(200)
    game.tick()
    assert char_of(game, "ani")["location"] == "belt"             # the air ran out: towed to the dome


def test_salvage_outside_the_hull(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    give(game, "ani", "eva_suit")
    wear(game, ani, "eva suit")
    walk(game, ani, "debris_field")
    salvaged = cmd(game, ani, "collect")
    assert salvaged["k"] == "paid" and salvaged["text"].startswith("You pull something out of the nets:")
    assert cmd(game, ani, "collect")["text"].startswith("You've just worked.")
    assert cmd(game, ani, "move", d="n")["room"] == "hull_walk"
    assert cmd(game, ani, "collect")["text"] == "There's nothing to collect here."


def test_selling_everything_and_the_ore_buyer(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", "engineer")
    inv = char_of(game, "ani")["inventory"]
    inv.update({"iron": 4, "titanium": 1, "tomato": 2})
    _to_belt(game, ani, clock)
    assert cmd(game, ani, "sell", item="tomat", n=1)["text"].startswith("Nobody here buys crates of tomatoes.")
    expected = sum(game.market.quote(g, "engineer", "sell", n, factor=0.75) for g, n in (("iron", 4), ("titanium", 1)))
    sold = cmd(game, ani, "sell", item="", n="all")
    assert sold["text"] == f"You sell 4 lumps of iron ore and 1 chunk of titanium for {expected} credits. You now have {100 - 5 + expected}."
    assert inv == {"compass": 1, "tomato": 2}
    assert cmd(game, ani, "buy", item="iron")["text"] == "The market is on the Promenade."


# ------------------------------------------------------------
# The scientist and the security officer
# ------------------------------------------------------------

@pytest.mark.parametrize("difficulty", [1, 2, 3, 4])
def test_the_readings_always_have_one_next_number(difficulty):
    rng = random.Random(difficulty)
    for _ in range(200):
        shown, answer = orbit_game.Game.make_pattern(rng, difficulty)
        assert 4 <= len(shown) <= 5 and answer > shown[-1] > 0


def test_the_scientist_finds_the_next_number(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", "scientist", lang="id")
    walk(game, ani, "science_lab")
    task = cmd(game, ani, "work")
    assert task["k"] == "task" and task["sound"] == "task" and "Berapa angka berikutnya?" in task["text"]
    answer = game.sessions["ani"].task["answer"]
    assert cmd(game, ani, "work")["text"].startswith("Angkanya sekali lagi:")
    paid = cmd(game, ani, "answer", a=str(answer))
    assert paid["k"] == "paid" and "kamu dibayar 50 kredit" in paid["text"]
    clock.advance(121)
    cmd(game, ani, "work")
    wrong = cmd(game, ani, "answer", a=str(game.sessions["ani"].task["answer"] + 1))
    assert wrong["k"] == "failed" and "Coba lagi dalam 30 detik" in wrong["text"]
    clock.advance(31)
    cmd(game, ani, "work")
    clock.advance(46)
    game.tick()
    assert ani.last()["text"].startswith("Terlalu lama: sampelnya keburu kering.")


def test_security_spots_the_smuggler(make_game, clock):
    game = make_game()
    ani = join(game, "Ani", "security")
    walk(game, ani, "cargo")
    task = cmd(game, ani, "work")
    assert task["text"].startswith("You patrol the Cargo Bay and watch the travellers. 1: ")
    assert task["text"].endswith("Which one is the smuggler? Type the number, from 1 to 3.")
    right = game.sessions["ani"].task["answer"]
    people = game.econ["patrol_people"]
    kind, index = game.sessions["ani"].task["lineup"][right - 1]
    assert kind == "suspect" and people["suspect"][index]["en"] in task["text"]
    assert "you're paid 55 credits" in cmd(game, ani, "answer", a=str(right))["text"]
    clock.advance(121)
    cmd(game, ani, "work")
    right = game.sessions["ani"].task["answer"]
    wrong = cmd(game, ani, "answer", a=str(right % 3 + 1))
    assert wrong["text"].startswith(f"Wrong person: the smuggler was number {right},")


# ------------------------------------------------------------
# The voice others hear
# ------------------------------------------------------------

def test_a_chosen_voice_goes_with_your_words(make_game):
    game = make_game()
    ani = join(game, "Ani", lang="id")
    budi = join(game, "Budi")
    shown = cmd(game, ani, "voice")
    assert shown["text"].startswith("Orang lain mendengarmu dengan suara yang dipilih dari namamu.")
    chosen = cmd(game, ani, "voice", a="3")
    assert chosen["voice"] == 3 and chosen["preview"] and chosen["text"].startswith("Beres: orang lain sekarang")
    cmd(game, ani, "say", a="halo")
    assert budi.events("say")[-1] == {"t": "ev", "k": "say", "actor": "Ani", "voice": 3, "text": "Ani says: halo"}
    cmd(game, ani, "whisper", to="Budi", a="psst")
    assert budi.events("whisper")[-1]["voice"] == 3
    assert cmd(game, ani, "voice", a="11")["text"] == "Pilih suara 1 sampai 10, atau acak."
    cmd(game, ani, "voice", a="acak")
    cmd(game, ani, "say", a="lagi")
    assert "voice" not in budi.events("say")[-1]
    cmd(game, ani, "voice", a="7")
    game.dropped(ani)
    game._remove(game.sessions["ani"])
    assert join(game, "Ani").sent[0]["voice"] == 7                 # kept, and told in the welcome


# ------------------------------------------------------------
# Admins and the economy's totals
# ------------------------------------------------------------

def test_admins_grant_take_give_and_see_the_economy(make_game, clock):
    game = make_game()
    boss = join(game, "Rafli")                                   # an admin
    ani = join(game, "Ani")
    cmd(game, boss, "admin", op="grant", to="Ani", n=500)
    assert ani.last()["text"] == "The station's admins give you 500 credits. You now have 600."
    cmd(game, boss, "admin", op="take_credits", to="Ani", n=100)
    assert char_of(game, "ani")["credits"] == 500
    cmd(game, boss, "admin", op="give_item", to="Ani", item="senter", n=1)
    assert char_of(game, "ani")["inventory"]["headlamp"] == 1
    cmd(game, boss, "admin", op="give_item", to="Ani", item="robot")
    assert game.store.companions_of(char_of(game, "ani")["id"])[0]["kind"] == "robot_pet"
    char_of(game, "ani")["streak"] = 5
    cmd(game, boss, "admin", op="reset_streak", to="Ani")
    assert char_of(game, "ani")["streak"] == 0
    cmd(game, boss, "admin", op="set_price", item="kopi", n=99)
    assert game.market.price("coffee") == 99
    clock.advance(3601)
    game.tick()
    assert game.market.price("coffee") != 99                      # an hour, then the market again
    report = cmd(game, boss, "admin", op="economy")["text"]
    assert report.startswith("Economy. Credits in circulation: 600 across 2 characters (average 300, most 500).")
    assert "Earned by source: admin 500." in report and "Spent by sink: admin 100." in report
    actions = [row["action"] for row in game.store.admin_log(20)]
    assert actions[:6] == ["economy", "set_price", "reset_streak", "give_item", "give_item", "take_credits"]
    assert all(row["actor"] == "Rafli" for row in game.store.admin_log(20))


def test_players_cant_use_admin_tools_and_a_grant_is_a_gift(make_game):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    for op in ("economy", "give_item", "take_credits", "set_price", "goto", "invisible", "revoke",
               "transfer_for", "transfers", "admin_log", "reset_streak"):
        assert cmd(game, ani, "admin", op=op, to="Budi", n=5)["text"] == "Only the station's admins can do that."
    cmd(game, ani, "admin", op="grant", to="Budi", n=5)
    assert ani.last()["text"] == "You give Budi 5 credits. You have 95 left."
    assert game.store.admin_log(10) == []


def test_admins_teleport_and_go_invisible(make_game):
    game = make_game()
    boss = join(game, "Rafli")
    ani = join(game, "Ani")
    walk(game, ani, "cantina")
    ani.clear()
    cmd(game, boss, "admin", op="invisible")
    moved = cmd(game, boss, "go", a="Ani")
    assert moved["room"] == "cantina" and moved["text"].startswith("Admin teleport: the Cantina.")
    assert ani.sent == []                                         # nobody saw a thing
    assert "Rafli" not in cmd(game, ani, "who")["text"]
    cmd(game, boss, "go", a="the bridge")
    assert game.sessions["rafli"].char["location"] == "bridge"
    cmd(game, boss, "admin", op="invisible")
    assert "Rafli" in cmd(game, ani, "who")["text"]


# ------------------------------------------------------------
# Moving a character to another computer
# ------------------------------------------------------------

def _transfer_hello(game, code, secret, ip_hash="ipX"):
    conn = FakeConn("en", ip_hash)
    game.hello(conn, {"t": "hello", "v": 1, "lang": "en", "secret": secret, "transfer": code})
    return conn


def test_codes_are_short_unambiguous_and_hashed(make_game):
    game = make_game()
    ani = join(game, "Ani")
    event = cmd(game, ani, "transfer")
    code = event["transfer_code"]
    assert len(code) == 19 and code.count("-") == 3 and event["expires"] == 600
    letters = code.replace("-", "")
    assert not set(letters) & set("IO01") and set(letters) <= set(orbit_admin.CODE_ALPHABET)
    assert event["text"].startswith("Your transfer code: " + ", ".join(" ".join(g) for g in code.split("-")))
    rows = game.store.db.execute("SELECT code_hash FROM transfer_codes").fetchall()
    assert len(rows) == 1 and letters not in rows[0]["code_hash"]
    assert orbit_admin.normalize_code(code.lower().replace("-", " ")) == letters
    assert orbit_admin.normalize_code("ABCD") == "" and orbit_admin.normalize_code("O" * 16) == ""


def test_a_code_moves_the_character_once(make_game, clock):
    game = make_game()
    old = join(game, "Ani")
    char_of(game, "ani")["credits"] = 777
    code = cmd(game, old, "transfer")["transfer_code"]
    new_secret = "b1" * 32
    moved = _transfer_hello(game, code, new_secret)
    assert moved.sent[0]["t"] == "welcome" and moved.sent[0]["name"] == "Ani" and moved.sent[0]["credits"] == 777
    assert old.closed == (orbit_game.CLOSE_REPLACED, "moved")
    assert old.texts("system")[-1].startswith("This character has just been moved to another computer.")
    # The old computer's secret no longer works, and says why.
    game.dropped(moved)
    game._remove(game.sessions["ani"])
    stale = join(game, "Ani")
    assert stale.sent[-1]["code"] == "moved" and stale.sent[-1]["text"].startswith("This character has been moved")
    assert join(game, "Whoever", secret=new_secret).sent[0]["name"] == "Ani"
    # Used once.
    again = _transfer_hello(game, code, "c2" * 32, ip_hash="ipY")
    assert again.sent[-1]["code"] == "transfer_bad"
    kinds = [row["kind"] for row in game.store.recent_transfers()]
    assert kinds == ["moved", "code"]


def test_a_code_expires_and_a_new_one_replaces_the_old(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    first = cmd(game, ani, "transfer")["transfer_code"]
    clock.advance(31)
    second = cmd(game, ani, "transfer")["transfer_code"]
    assert _transfer_hello(game, first, "d3" * 32).sent[-1]["code"] == "transfer_bad"
    clock.advance(601)
    assert _transfer_hello(game, second, "d4" * 32).sent[-1]["code"] == "transfer_bad"


def test_wrong_codes_are_limited_by_address(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    code = cmd(game, ani, "transfer")["transfer_code"]
    for i in range(5):
        assert _transfer_hello(game, "ABCD-EFGH-JKLM-NPQR", f"{i}e" * 32, "ipZ").sent[-1]["code"] == "transfer_bad"
    blocked = _transfer_hello(game, code, "f5" * 32, "ipZ")
    assert blocked.sent[-1]["code"] == "transfer_wait"
    clock.advance(901)                                             # the wait is over, and so is the code
    assert _transfer_hello(game, code, "f6" * 32, "ipZ").sent[-1]["code"] == "transfer_bad"
    code = cmd(game, ani, "transfer")["transfer_code"]
    assert _transfer_hello(game, code, "f7" * 32, "ipZ").sent[0]["t"] == "welcome"


def test_admins_revoke_and_make_codes_for_lost_computers(make_game):
    game = make_game()
    boss = join(game, "Rafli")
    ani = join(game, "Ani")
    cmd(game, boss, "admin", op="revoke", to="Ani")
    assert ani.closed == (orbit_game.CLOSE_REPLACED, "revoked")
    assert "An admin has revoked this computer's access to your character." in ani.texts("system")
    game._remove(game.sessions["ani"])
    refused = join(game, "Ani")
    assert refused.sent[-1]["code"] == "revoked"
    event = cmd(game, boss, "admin", op="transfer_for", to="Ani")
    assert event["text"].startswith("Transfer code for Ani: ") and len(event["transfer_code"]) == 19
    back = _transfer_hello(game, event["transfer_code"], "a7" * 32)
    assert back.sent[0]["name"] == "Ani"
    listing = cmd(game, boss, "admin", op="transfers")["text"]
    assert listing.startswith("Recent transfers: Ani: moved to another computer")
    assert "Ani: revoked" in listing and "(by Rafli)" in listing


# ------------------------------------------------------------
# Migrating Orbit 1.0's database
# ------------------------------------------------------------

def _old_database(path):
    """A database as Orbit 1.0 left it, with two characters."""
    db = sqlite3.connect(path)
    db.executescript(orbit_store.SCHEMA)
    now = datetime.datetime(2026, 9, 25, 12, 0, tzinfo=UTC).timestamp()
    db.execute("INSERT INTO meta (key, value) VALUES ('secret_salt', ?)", ("ab" * 16,))
    db.execute("INSERT INTO meta (key, value) VALUES ('market', ?)", (json.dumps({"prices": {"coffee": 15.5}}),))
    for name, job, credits, location, stats in (
            ("Quilafly", "pilot", 1234, "cantina", {"flights": 3, "missions_done": 2, "cooldowns": {}}),
            ("Budi", "engineer", 50, "engineering", {"repairs": 5, "repair_level": 4})):
        db.execute("INSERT INTO characters (name, name_key, secret_hash, job, credits, location, "
                   "description, inventory, stats, created, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (name, name.lower(), f"hash-{name}", job, credits, location, "hello",
                    json.dumps({"coffee": 2}), json.dumps(stats), now, now))
    db.commit()
    db.close()


def test_an_old_database_is_migrated_and_nothing_is_lost(tmp_path, clock):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert store.version() == orbit_store.SCHEMA_VERSION and store.migrated_from == 0
    assert os.path.exists(path + f".before-v{orbit_store.SCHEMA_VERSION}.bak")
    columns = {row["name"] for row in store.db.execute("PRAGMA table_info(characters)")}
    assert {"voice", "xp", "streak", "last_daily", "mined", "harvested", "casino_net"} <= columns
    tables = {row["name"] for row in store.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"companions", "companion_owners", "transfer_codes", "old_secrets", "transfers", "admin_log",
            "achievements", "lottery_tickets"} <= tables
    quila = store.by_name("quilafly")
    assert (quila["credits"], quila["location"], quila["description"], quila["inventory"]) == \
        (1234, "cantina", "hello", {"coffee": 2})
    assert quila["xp"] == 3 * 20 + 2 * 25 and store.by_name("budi")["xp"] == 5 * 10   # past work counts
    assert quila["stats"]["flights"] == 3 and quila["voice"] == 0 and quila["streak"] == 0
    assert store.get_json("market")["prices"]["coffee"] == 15.5 and store.get_meta("secret_salt") == "ab" * 16
    store.close()
    # The backup is the old database, untouched.
    backup = sqlite3.connect(path + f".before-v{orbit_store.SCHEMA_VERSION}.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 0
    assert backup.execute("SELECT credits FROM characters WHERE name_key = 'quilafly'").fetchone()[0] == 1234
    backup.close()
    # Opening it again: already migrated, no second copy.
    again = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert again.migrated_from is None and again.by_name("quilafly")["xp"] == 110
    again.close()
    assert [f for f in os.listdir(tmp_path) if f.endswith(".bak")] == [f"orbit.db.before-v{orbit_store.SCHEMA_VERSION}.bak"]


def test_a_migrated_character_plays_on(tmp_path, make_game, clock):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    game = make_game(path)
    game.store.db.execute("UPDATE characters SET secret_hash = ? WHERE name_key = 'quilafly'",
                          (game.store.hash_secret(secret_of("Quilafly")),))
    conn = join(game, "Quilafly", lang="id")
    assert conn.sent[0]["name"] == "Quilafly" and conn.sent[0]["credits"] == 1234 and conn.sent[0]["room"] == "cantina"
    room = conn.sent[1]["text"]
    assert room.startswith("Selamat datang kembali, Quilafly. Baru di stasiun: sekarang kamu berjalan dengan arah")
    assert "Kantin." in room and "Jalan keluar: timur, barat." in room
    char = game.sessions["quilafly"].char
    assert char["inventory"]["compass"] == 1 and char["inventory"]["keycard_crew"] == 1   # level 2 already
    assert game.level_of(char["xp"]) == 2
    game.dropped(conn)
    game._remove(game.sessions["quilafly"])
    assert "Baru di stasiun" not in join(game, "Quilafly", lang="id").sent[1]["text"]      # said once


def test_a_trade_between_two_characters_is_all_or_nothing(make_game, monkeypatch):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    real_save = game.store.save
    calls = []

    def failing_save(char):
        calls.append(char["name"])
        if len(calls) == 2:
            raise sqlite3.OperationalError("disk full")
        real_save(char)

    monkeypatch.setattr(game.store, "save", failing_save)
    cmd(game, ani, "give", to="Budi", n=10)
    assert ani.last()["text"] == "Something went wrong on the station's computer. Try again."
    monkeypatch.setattr(game.store, "save", real_save)
    stored = {name: game.store.by_name(name)["credits"] for name in ("ani", "budi")}
    assert stored == {"ani": 100, "budi": 100}                    # neither saved: the transaction rolled back


# ------------------------------------------------------------
# Backups
# ------------------------------------------------------------

def test_a_backup_while_the_server_writes_keeps_the_newest_copies(tmp_path, make_game):
    import orbit_backup
    path = str(tmp_path / "orbit.db")
    game = make_game(path)
    ani = join(game, "Ani")
    char_of(game, "ani")["credits"] = 4321
    game._save(game.sessions["ani"])
    folder = str(tmp_path / "backups")
    made = []
    for day in range(1, 10):
        when = datetime.datetime(2026, 9, day, 4, 30)
        made.append(orbit_backup.backup(path, folder, keep=7, now=when))
        cmd(game, ani, "say", a="still playing")                # the server keeps going
    kept = sorted(os.listdir(folder))
    assert kept == [os.path.basename(p) for p in made[-7:]]
    copy = sqlite3.connect(made[-1])
    assert copy.execute("SELECT credits FROM characters WHERE name_key = 'ani'").fetchone()[0] == 4321
    assert copy.execute("PRAGMA user_version").fetchone()[0] == orbit_store.SCHEMA_VERSION
    copy.close()
    assert orbit_backup.main(["--db", str(tmp_path / "missing.db"), "--dir", folder]) == 1
