# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Orbit's mall, casino, trading, pawn shop, achievements and leaderboards
# (the server; stage 2 of Orbit 1.1). The odds are computed exactly from
# economy.json, so a change there that gives the players the edge fails here.

import datetime
import functools
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "servers", "orbit")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import orbit_casino  # noqa: E402
import orbit_store  # noqa: E402
from tests.test_orbit_economy import _old_database  # noqa: E402
from tests.test_orbit_map import give, wear  # noqa: E402
from tests.test_orbit_server import (UTC, FakeConn, clock, cmd, join, make_game,  # noqa: E402,F401
                                     secret_of, walk, world)


def at(game, name, place, credits=1000, lang="en", job="pilot"):
    conn = join(game, name, job, lang)
    walk(game, conn, place)
    game.sessions[name.lower()].char["credits"] = credits
    conn.clear()
    return conn


def said(conn):
    """The last thing a player was told, an achievement aside."""
    return [m for m in conn.sent if m.get("sound") != "achievement"][-1]


def char_of(game, name):
    return game.sessions[name.lower()].char


def feed(monkeypatch, obj, name, values):
    """obj.name() returns `values` one after another."""
    values = list(values)
    monkeypatch.setattr(obj, name, lambda *a, **k: values.pop(0))


# ------------------------------------------------------------
# The odds
# ------------------------------------------------------------

def _dice_return(casino, choice):
    rules = casino["dice"]
    multiple = rules["seven" if choice == "seven" else "high_low"]
    wins = sum(1 for a in range(1, 7) for b in range(1, 7) if orbit_casino.dice_wins(choice, a + b))
    return wins / 36 * multiple


def _slots_return(slots):
    weights = slots["symbols"]
    total = float(sum(weights.values()))
    back = 0.0
    for a in weights:
        for b in weights:
            for c in weights:
                p = weights[a] * weights[b] * weights[c] / total ** 3
                back += p * orbit_casino.slot_payout([a, b, c], slots)
    return back


def _blackjack_return(rules):
    """The return of blackjack with perfect hit-or-stand play (an endless deck,
    the dealer peeks for blackjack and stands on 17), computed exactly."""
    ranks, p = range(1, 14), 1 / 13.0

    def value(cards):
        return orbit_casino.card_value(list(cards))

    @functools.lru_cache(None)
    def dealer(cards):
        v = value(cards)
        if v > 21:
            return ((22, 1.0),)
        if v >= rules["dealer_stands"]:
            return ((v, 1.0),)
        out = {}
        for r in ranks:
            for k, q in dealer(tuple(sorted(cards + (min(r, 10),)))):
                out[k] = out.get(k, 0) + q * p
        return tuple(out.items())

    back = 0.0
    for up in ranks:
        final, weight = {}, 0.0
        for hole in ranks:
            cards = tuple(sorted((min(up, 10), min(hole, 10))))
            if value(cards) == 21:
                continue
            weight += p
            for k, q in dealer(cards):
                final[k] = final.get(k, 0) + q * p
        final = {k: q / weight for k, q in final.items()}

        @functools.lru_cache(None)
        def play(cards):
            v = value(cards)
            if v > 21:
                return 0.0
            stand = sum(q * (rules["win"] if k == 22 or k < v else 1.0 if k == v else 0.0)
                        for k, q in final.items())
            if v == 21:
                return stand
            return max(stand, sum(p * play(tuple(sorted(cards + (min(r, 10),)))) for r in ranks))

        for hole in ranks:
            dealer_natural = value((min(up, 10), min(hole, 10))) == 21
            for a in ranks:
                for b in ranks:
                    cards = tuple(sorted((min(a, 10), min(b, 10))))
                    if value(cards) == 21:
                        back += p ** 4 * (1.0 if dealer_natural else rules["natural"])
                    elif not dealer_natural:
                        back += p ** 4 * play(cards)
    return back


def test_the_house_always_keeps_an_edge(world):
    casino = world.economy["casino"]
    for choice in ("high", "low", "seven"):
        assert 0.85 < _dice_return(casino, choice) < 0.97, choice          # 4 to 15 percent to the house
    assert _dice_return(casino, "high") == pytest.approx(15 / 36 * 2.3)
    assert 0.85 < _slots_return(casino["slots"]) < 0.97
    assert 0.9 < _blackjack_return(casino["blackjack"]) < 0.99              # even played perfectly
    assert 0 < casino["coinflip"]["fee"] < 0.2 and 0 < casino["lottery"]["house"] < 0.5
    assert casino["min_bet"] < casino["max_bet"] <= casino["hour_limit"] and casino["cooldown"] > 0


def test_cards_count_like_blackjack():
    assert orbit_casino.card_value([1, 13]) == 21 and orbit_casino.card_value([1, 1, 9]) == 21
    assert orbit_casino.card_value([1, 5, 10]) == 16 and orbit_casino.card_value([12, 11, 2]) == 22
    assert orbit_casino.slot_payout(["orbit"] * 3, {"three": {"orbit": 200}, "two": {}, "pair": 1}) == 200
    assert orbit_casino.slot_payout(["star", "orbit", "orbit"],
                                    {"three": {}, "two": {"orbit": 6}, "pair": 1}) == 6
    assert orbit_casino.slot_payout(["star", "moon", "star"], {"three": {}, "two": {"orbit": 6}, "pair": 1}) == 1
    assert orbit_casino.slot_payout(["star", "moon", "comet"], {"three": {}, "two": {}, "pair": 1}) == 0


# ------------------------------------------------------------
# Playing
# ------------------------------------------------------------

def test_dice_pay_by_the_rules_and_the_net_is_kept(make_game, monkeypatch, clock):
    game = make_game()
    ani = at(game, "Ani", "casino")
    feed(monkeypatch, game.rng, "randint", [5, 6, 1, 2, 3, 4])
    won = cmd(game, ani, "dice", a="high", n=100)
    assert won["k"] == "paid" and won["sound"] == "dice" and won["outcome"] == "win"
    assert won["text"] == "You bet 100 on high. The dice roll 5 and 6: 11. You win 230 credits! You have 1130."
    clock.advance(3)
    lost = cmd(game, ani, "dice", a="big", n=100)                  # "big" is a bet on high
    assert lost["k"] == "failed" and lost["outcome"] == "lose" and lost["text"].endswith("You lose. You have 1030.")
    clock.advance(3)
    seven = cmd(game, ani, "dice", a="7", n=10)
    assert "3 and 4: 7. You win 55 credits!" in seven["text"]
    char = char_of(game, "Ani")
    assert char["casino_net"] == 130 - 100 + 45 and game.store.by_name("ani")["casino_net"] == 75
    assert game.flows["spent"]["casino_bets"] == 210 and game.flows["earned"]["casino_wins"] == 285


def test_bets_have_limits(make_game, monkeypatch, clock):
    game = make_game()
    budi = join(game, "Budi")
    assert cmd(game, budi, "dice", a="high", n=50)["text"] == \
        "Games of chance are played in the Casino Corner, west of the Cantina."
    ani = at(game, "Ani", "casino", credits=300)
    assert cmd(game, ani, "dice", a="purple", n=50)["text"].startswith("Choose high, low or seven")
    assert cmd(game, ani, "slots")["text"].startswith("Say how much to bet, from 5 to 500 credits")
    assert cmd(game, ani, "slots", n=1000)["text"] == "Bets are from 5 to 500 credits."
    assert cmd(game, ani, "slots", n=400)["text"] == "You only have 300 credits."
    cmd(game, ani, "slots", n=10)
    assert cmd(game, ani, "slots", n=10)["text"] == "The dealer is still clearing the table. Wait a moment."
    clock.advance(3)
    assert cmd(game, ani, "slots", n=10)["k"] in ("paid", "failed")
    char = char_of(game, "Ani")
    char["credits"] = 100000
    char["stats"]["casino_bets"] = [[clock.now - 600, 4990]]
    clock.advance(3)
    assert cmd(game, ani, "slots", n=20)["text"].startswith("That's enough for this hour")
    clock.advance(3000)                                    # the bets of an hour ago drop out
    assert cmd(game, ani, "slots", n=20)["k"] in ("paid", "failed")
    assert len(char["stats"]["casino_bets"]) == 1          # kept a minute at a time


def test_slots_spin_three_reels_and_a_jackpot_is_news(make_game, monkeypatch, clock):
    game = make_game()
    ani = at(game, "Ani", "casino")
    budi = join(game, "Budi")
    feed(monkeypatch, game, "_pick", ["star", "moon", "star"])
    even = cmd(game, ani, "slots", n=20)
    assert even["reels"] == ["star", "moon", "star"] and even["outcome"] == "push" and even["sound"] == "reel_spin"
    assert even["text"] == "star, moon, star. A pair: you get your bet back. You have 1000."
    clock.advance(3)
    feed(monkeypatch, game, "_pick", ["orbit", "orbit", "orbit"])
    budi.clear()
    jackpot = cmd(game, ani, "slots", n=10)
    assert jackpot["outcome"] == "jackpot" and jackpot["text"].startswith("Orbit, Orbit, Orbit: JACKPOT!")
    assert char_of(game, "Ani")["credits"] == 1000 - 10 + 2000
    news = budi.texts("announce")
    assert "Big win at the casino: Ani just won 2000 credits!" in news
    assert "Ani earns the achievement Jackpot!, the first on the station!" in news
    earned = [m for m in ani.sent if m.get("sound") == "achievement"]
    assert earned and earned[0]["text"].startswith("Achievement unlocked: Jackpot!")


def test_blackjack_hit_stand_bust_naturals_and_the_dealer_peeks(make_game, monkeypatch, clock):
    game = make_game()
    ani = at(game, "Ani", "casino")
    char = char_of(game, "Ani")
    # stand on 17 against 18
    feed(monkeypatch, game, "_card", [10, 7, 10, 8])
    start = cmd(game, ani, "blackjack", n=100)
    assert start["k"] == "task" and start["sound"] == "deal"
    assert start["text"] == ("Blackjack for 100 credits. Your cards: 10 and 7, 17. The dealer shows 10. "
                             "Hit or stand?")
    assert cmd(game, ani, "blackjack", n=100)["text"].startswith("You're playing blackjack for 100 credits.")
    lost = cmd(game, ani, "stand")
    assert lost["text"] == "You have 17, the dealer has 18 (10 and 8). You lose. You have 900."
    assert cmd(game, ani, "stand")["text"] == "You're already standing."      # no hand: the posture (1.6)
    assert cmd(game, ani, "hit")["text"].startswith("You're not playing blackjack.")
    # hit and bust
    clock.advance(3)
    feed(monkeypatch, game, "_card", [10, 6, 9, 7, 10])
    cmd(game, ani, "blackjack", n=100)
    assert cmd(game, ani, "hit")["text"] == "Your cards: 10, 6 and 10, 26. Bust! You lose. You have 800."
    # hit, then the dealer draws and busts ("take a card" is a hit at the table)
    clock.advance(3)
    feed(monkeypatch, game, "_card", [5, 6, 10, 6, 9, 10])
    cmd(game, ani, "blackjack", n=100)
    assert cmd(game, ani, "take", item="a card")["text"] == "You draw 9: 20. Hit or stand?"
    won = cmd(game, ani, "stand")
    assert won["text"] == "You have 20. The dealer's cards: 10, 6 and 10, 26, bust! You win 200 credits. You have 900."
    # a natural pays 3 to 2, and is an achievement
    clock.advance(3)
    feed(monkeypatch, game, "_card", [1, 13, 9, 9])
    natural = cmd(game, ani, "blackjack", n=100)
    assert natural["text"] == "Blackjack! ace and king. You win 250 credits! You have 1050."
    assert any(m.get("sound") == "achievement" and "Natural" in m["text"] for m in ani.sent)
    # the dealer's blackjack ends the hand at once
    clock.advance(3)
    feed(monkeypatch, game, "_card", [10, 6, 1, 12])
    peek = cmd(game, ani, "blackjack", n=100)
    assert peek["text"].startswith("Your cards: 10 and 6, 16. The dealer has blackjack (ace and queen). You lose.")
    assert game.sessions["ani"].blackjack is None
    assert char["casino_net"] == -100 - 100 + 100 + 150 - 100          # the achievement isn't casino money


def test_an_unfinished_hand_is_played_out(make_game, monkeypatch, clock):
    game = make_game()
    ani = at(game, "Ani", "casino")
    feed(monkeypatch, game, "_card", [10, 9, 10, 7])
    cmd(game, ani, "blackjack", n=100)
    clock.advance(61)
    game.tick()
    assert "You took too long, so the dealer plays your hand as it stands." in ani.texts("system")
    assert ani.events()[-1]["text"] == "You have 19, the dealer has 17 (10 and 7). You win 200 credits! You have 1100."
    # leaving mid-hand: the hand is stood, the winnings kept
    clock.advance(3)
    feed(monkeypatch, game, "_card", [10, 9, 10, 7])
    cmd(game, ani, "blackjack", n=100)
    cmd(game, ani, "bye")
    assert game.store.by_name("ani")["credits"] == 1200


def test_a_coin_flip_between_two_players(make_game, monkeypatch, clock):
    game = make_game()
    ani = at(game, "Ani", "casino")
    budi = at(game, "Budi", "casino", credits=500, lang="id")   # an older client's "id": English all the same
    assert cmd(game, ani, "challenge", to="Nobody", n=50)["text"].startswith("Challenge whom?")
    assert cmd(game, ani, "challenge", to="Budi", n=5)["text"] == "A coin flip is for 10 to 1000 credits each."
    sent = cmd(game, ani, "text", a="challenge Budi 100")
    assert sent["text"] == "You challenge Budi to a coin flip for 100 credits each. Waiting for an answer."
    ask = budi.last()
    assert ask["k"] == "offer" and ask["ask"] is True and ask["actor"] == "Ani"
    assert ask["text"].startswith("Ani challenges you to a coin flip for 100 credits each.")
    monkeypatch.setattr(game.rng, "random", lambda: 0.9)        # the challenger wins
    cmd(game, budi, "text", a="accept")
    assert ani.last()["text"] == ("The coin spins... you win! You take 190 credits from the flip with Budi "
                                  "(the house keeps 10). You have 1090.")
    assert budi.last()["text"] == "The coin spins... Ani wins. You lose 100 credits. You have 400."
    assert (char_of(game, "Ani")["casino_net"], char_of(game, "Budi")["casino_net"]) == (90, -100)
    assert game.store.by_name("budi")["credits"] == 400
    # declined, and run out of time
    clock.advance(3)
    cmd(game, ani, "challenge", to="Budi", n=50)
    assert cmd(game, budi, "decline")["text"] == "You decline Ani's coin flip."
    assert ani.last()["text"] == "Budi declines your coin flip."
    clock.advance(3)
    cmd(game, ani, "challenge", to="Budi", n=50)
    clock.advance(61)
    game.tick()
    assert ani.last()["text"] == "Budi didn't answer your coin flip in time."
    assert cmd(game, budi, "accept")["text"].startswith("Which mission?")   # nothing waiting: missions


def test_the_weekly_lottery(make_game, monkeypatch, clock):
    game = make_game()
    ani = at(game, "Ani", "casino")
    budi = at(game, "Budi", "casino")
    bought = cmd(game, ani, "buy", item="tickets", n=3)
    assert bought["text"] == ("You buy 3 lottery tickets for 30 credits: 3 this week. The pot is 24 credits. "
                              "You have 970.") and bought["sound"] == "lottery"
    cmd(game, budi, "buy", item="ticket", n=1)
    info = cmd(game, ani, "lottery")["text"]
    assert info.startswith("The weekly lottery: the pot is 32 credits, and you have 3 tickets. The draw is on "
                           "Sunday at 12:00 UTC, in 47.5 hours.")
    assert cmd(game, ani, "buy", item="ticket", n=48)["text"] == \
        "You can hold at most 50 tickets a week, and you have 3."
    # the draw, on Sunday at noon (UTC); Budi has left the station by then
    cmd(game, budi, "bye")
    draw = datetime.datetime(2026, 9, 27, 12, 0, tzinfo=UTC).timestamp()
    clock.now = draw - 1
    game.tick()
    assert not ani.texts("announce")
    clock.now = draw + 1
    monkeypatch.setattr(game.rng, "random", lambda: 0.9)        # the fourth ticket: Budi's
    game.tick()
    assert "The weekly lottery is drawn: Budi wins 32 credits! Congratulations!" in ani.texts("announce")
    stored = game.store.by_name("budi")
    assert stored["credits"] == 1000 - 10 + 32 and stored["inventory"].get("title_lucky") == 1
    assert "lucky_draw" in game.store.achievements_of(stored["id"])
    state = game.store.get_json("lottery")
    assert state["draw"] == draw + 7 * 86400 and state["carry"] == 0
    assert "you have 0 tickets" in cmd(game, ani, "lottery")["text"]
    # a week without tickets carries the pot over (and nothing is said)
    clock.now = draw + 7 * 86400 + 5
    game.tick()
    assert game.store.get_json("lottery")["draw"] == draw + 14 * 86400


# ------------------------------------------------------------
# Trading
# ------------------------------------------------------------

def test_trading_is_all_or_nothing(make_game, monkeypatch, clock):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi", lang="id")                  # an older client's "id": English all the same
    for _ in range(3):
        give(game, "ani", "iron")
    give(game, "ani", "batik_shirt", "keycard_crew")
    char_of(game, "Budi")["credits"] = 500
    wear(game, ani, "rocket-print shirt")
    assert cmd(game, ani, "offer", to="Budi", a="crew keycard for 10 credits")["text"] == \
        "crew keycards can't be traded."
    assert cmd(game, ani, "offer", to="Budi", a="3 iron")["text"].startswith("Say what you give and what you want")
    assert cmd(game, ani, "offer", to="Budi", a="9 iron for 5 credits")["text"] == \
        "Ani doesn't have 9 lumps of iron ore."
    assert cmd(game, ani, "offer", to="Nobody", a="3 iron for 5 credits")["text"] == \
        "Nobody isn't on the station right now."
    sent = cmd(game, ani, "text", a="offer Budi 3 iron for 200 credits")
    assert sent["text"] == "You offer Budi 3 lumps of iron ore for 200 credits. Waiting for an answer."
    ask = budi.last()
    assert ask["k"] == "offer" and ask["ask"] is True and ask["actor"] == "Ani"
    assert ask["text"] == "Ani offers you 3 lumps of iron ore for 200 credits. Type accept or decline (within 2 minutes)."
    cmd(game, budi, "text", a="accept")
    assert said(ani)["text"] == ("Deal! You trade with Budi: you give 3 lumps of iron ore and get 200 credits. "
                                  "You have 300 credits.")
    assert said(budi)["sound"] == "trade"
    a, b = char_of(game, "Ani"), char_of(game, "Budi")
    assert "iron" not in a["inventory"] and b["inventory"]["iron"] == 3 and b["credits"] == 300 + 25
    assert game.store.by_name("budi")["inventory"]["iron"] == 3 and game.store.by_name("ani")["credits"] == 300 + 25
    assert a["stats"]["trades"] == 1 and b["stats"]["trades"] == 1
    assert "handshake" in game.store.achievements_of(a["id"]) and "handshake" in game.store.achievements_of(b["id"])
    # a worn shirt changes hands and comes off; if saving fails, nothing moves
    clock.advance(5)
    cmd(game, ani, "offer", to="Budi", a="rocket-print shirt for 50 credits")

    def broken(chars):
        raise OSError("disk full")
    monkeypatch.setattr(game.store, "save_all", broken)
    before = (dict(a["inventory"]), a["credits"], dict(b["inventory"]), b["credits"], dict(a["stats"]["worn"]))
    assert cmd(game, budi, "accept")["text"] == "Something went wrong, so nothing changed hands."
    assert (dict(a["inventory"]), a["credits"], dict(b["inventory"]), b["credits"], dict(a["stats"]["worn"])) == before
    monkeypatch.undo()
    clock.advance(5)
    cmd(game, ani, "offer", to="Budi", a="rocket-print shirt for 50 credits")
    cmd(game, budi, "accept")
    assert b["inventory"]["batik_shirt"] == 1 and "batik_shirt" not in a["inventory"]
    assert a["stats"]["worn"] == {}


def test_offers_can_be_declined_taken_back_and_run_out(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    give(game, "ani", "kerupuk")
    cmd(game, ani, "offer", to="Budi", a="prawn crackers for 5 credits")
    assert cmd(game, budi, "decline")["text"] == "You decline Ani's offer."
    assert ani.last()["text"] == "Budi declines your offer."
    assert cmd(game, budi, "decline")["text"] == "There's nothing to decline."
    clock.advance(5)
    cmd(game, ani, "offer", to="Budi", a="prawn crackers for 5 credits")
    assert cmd(game, ani, "cancel_offer")["text"] == "You take back your offer to Budi."
    assert budi.last()["text"] == "Ani takes back the offer."
    assert cmd(game, ani, "cancel_offer")["text"] == "You have no offer waiting."
    clock.advance(5)
    cmd(game, ani, "offer", to="Budi", a="prawn crackers for 5 credits")
    clock.advance(121)
    game.tick()
    assert ani.last()["text"] == "Budi didn't answer your offer in time."
    assert budi.last()["text"] == "The offer from Ani has run out of time."
    clock.advance(5)
    cmd(game, ani, "offer", to="Budi", a="prawn crackers for 5 credits")
    cmd(game, ani, "bye")
    assert "Ani takes back the offer." in budi.texts("system")
    assert cmd(game, budi, "accept")["text"].startswith("Which mission?")


def test_the_pawn_shop_buys_things_back(make_game):
    game = make_game()
    ani = at(game, "Ani", "pawn", credits=0)
    give(game, "ani", "headlamp", "iron")
    wear(game, ani, "headlamp")
    listed = cmd(game, ani, "list")["text"]
    assert listed == "Second Orbit would pay, in credits: headlamp, 48. Type sell and the thing's name."
    assert cmd(game, ani, "sell", item="compass")["text"] == "The owner won't buy compasses."
    assert cmd(game, ani, "sell", item="iron")["text"].startswith(
        "Goods are sold at a market, not here. Nearest market for iron: the Mineral Exchange, north, east, south, "
        "down 3 levels,")
    sold = cmd(game, ani, "sell", item="headlamp")
    assert sold["text"] == "You sell 1 headlamp to Second Orbit for 48 credits. You have 48."
    char = char_of(game, "Ani")
    assert "headlamp" not in char["inventory"] and char["stats"]["worn"] == {}
    assert game.flows["earned"]["pawn"] == 48


# ------------------------------------------------------------
# Achievements and leaderboards
# ------------------------------------------------------------

def test_achievements_are_earned_once_and_the_big_ones_are_news(make_game, clock):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    walk(game, ani, "pet_shop")                           # ten rooms
    earned = [m for m in ani.sent if m.get("sound") == "achievement"]
    assert [m["text"] for m in earned] == ["Achievement unlocked: Finding Your Feet (visit 10 rooms). You get 25 credits."]
    assert earned[0]["k"] == "paid"
    char = char_of(game, "Ani")
    assert char["credits"] == 125 and game.store.achievements_of(char["id"]) == ["first_steps"]
    walk(game, ani, "dock")
    assert len([m for m in ani.sent if m.get("sound") == "achievement"]) == 1       # only once
    # level 10 is news for the whole station, and the first one says so
    char["xp"] = game.xp_for_level(10)
    budi.clear()
    cmd(game, ani, "look")
    assert "Ani earns the achievement Chief, the first on the station!" in budi.texts("announce")
    mine = [m["text"] for m in ani.sent if m.get("sound") == "achievement"]
    assert "Achievement unlocked: Chief (reach level 10). You get 300 credits. You're the first on the station to " \
           "earn it!" in mine
    assert "Achievement unlocked: Getting There (reach level 5). You get 100 credits." in mine
    listed = cmd(game, ani, "achievements")["text"]
    total = len(game.econ["achievements"])
    assert listed.startswith(f"Your achievements, 3 of {total}: Finding Your Feet; Getting There; Chief.")
    assert "Closest: Living Legend, reach level 20: 10 of 20;" in listed
    assert "Closest: " in listed
    assert cmd(game, budi, "achievements", to="Ani")["text"].startswith(f"Ani's achievements, 3 of {total}:")
    char_of(game, "Budi")["xp"] = game.xp_for_level(10)
    ani.clear()
    cmd(game, budi, "look")
    assert "Budi earns the achievement Chief!" in ani.texts("announce")


def test_what_was_done_before_counts_quietly(tmp_path, make_game, clock):
    path = str(tmp_path / "orbit.db")
    game = make_game(path)
    ani = join(game, "Ani")
    char = char_of(game, "Ani")
    char["mined"], char["harvested"] = 600, 3
    cmd(game, ani, "bye")
    game.store.close()
    game = make_game(path)
    budi = join(game, "Budi")
    budi.clear()
    ani = join(game, "Ani")
    welcome = ani.sent[1]["text"]
    assert "Achievement unlocked: Rockhound" in welcome and "Achievement unlocked: Deep Digger" in welcome
    assert "Achievement unlocked: First Harvest" in welcome
    assert not budi.texts("announce")                    # not news: it happened long ago
    assert char_of(game, "Ani")["inventory"]["title_digger"] == 1


def test_leaderboards_leave_the_admins_out(make_game):
    game = make_game()
    rafli = join(game, "Rafli")
    char_of(game, "Rafli")["credits"] = 10 ** 9
    conns = {}
    for name, credits, mined in (("Ani", 500, 3), ("Budi", 900, 40), ("Cici", 300, 12)):
        conns[name] = join(game, name, lang="id" if name == "Cici" else "en")
        char_of(game, name).update(credits=credits, mined=mined)
        game._save(game.sessions[name.lower()])
    game._save(game.sessions["rafli"])
    board = cmd(game, conns["Ani"], "leaderboard", a="richest")["text"]
    assert board == "Leaderboard, richest: 1. Budi, 900; 2. Ani, 500; 3. Cici, 300. You're number 2."
    miners = cmd(game, conns["Cici"], "text", a="leaderboard miners")["text"]     # Cici's older client said "id"
    assert miners == "Leaderboard, miners: 1. Budi, 40; 2. Cici, 12; 3. Ani, 3. You're number 2."
    assert cmd(game, conns["Cici"], "text", a="papan skor penambang")["text"] == \
        "I don't understand \"papan skor penambang\". Type help for the commands."
    summary = cmd(game, conns["Ani"], "leaderboard")["text"]
    assert summary.startswith("Leaders: richest, Budi (900); level, ") and "miners, Budi (40)" in summary
    assert cmd(game, conns["Ani"], "leaderboard", a="purple")["text"].startswith("There's no such leaderboard.")
    assert "You're number" not in cmd(game, rafli, "leaderboard", a="rich")["text"]


# ------------------------------------------------------------
# The database
# ------------------------------------------------------------

def test_a_version_1_database_moves_to_the_current_version(tmp_path, clock, monkeypatch):
    path = str(tmp_path / "orbit.db")
    _old_database(path)
    with monkeypatch.context() as m:                          # as Orbit 1.1's first stage left it
        m.setattr(orbit_store, "SCHEMA_VERSION", 1)
        m.setattr(orbit_store.Store, "_migrate_2", lambda self: None)
        store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
        assert store.version() == 1
        store.close()
    os.remove(path + ".before-v1.bak")
    store = orbit_store.Store(path, clock=clock, iterations=1000, durable=False)
    assert store.version() == orbit_store.SCHEMA_VERSION and store.migrated_from == 1
    columns = {row["name"] for row in store.db.execute("PRAGMA table_info(characters)")}
    assert "casino_net" in columns and store.by_name("quilafly")["casino_net"] == 0
    assert store.by_name("quilafly")["xp"] == 3 * 20 + 2 * 25                 # kept from version 1
    assert store.add_achievement(1, "first_steps") and not store.add_achievement(1, "first_steps")
    store.add_tickets("2026-09-27", 1, 2)
    store.add_tickets("2026-09-27", 1, 3)
    assert store.tickets("2026-09-27", 1) == 5 and store.lottery_entries("2026-09-27") == [(1, 5)]
    store.close()
    backup = sqlite3.connect(path + f".before-v{orbit_store.SCHEMA_VERSION}.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
    backup.close()


def test_a_trade_offer_to_someone_link_dead_waits_for_them(make_game):
    game = make_game()
    ani = join(game, "Ani")
    budi = join(game, "Budi")
    give(game, "ani", "kerupuk")
    game.dropped(budi)
    assert cmd(game, ani, "offer", to="Budi", a="prawn crackers for 5 credits")["text"] == \
        "Budi isn't on the station right now."
    assert isinstance(FakeConn(), FakeConn)
