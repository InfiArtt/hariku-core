# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The Casino Corner, behind the Cantina. Credits are only for playing: they
have no real-money value, can't be bought, and can't be cashed out.

  dice 50 high / low / seven   two dice: 8 to 12, 2 to 6, or exactly 7
  slots 20                     three reels of stars, moons, comets, planets,
                               rockets and the golden Orbit
  blackjack 50, hit, stand     against the robot dealer (who stands on 17)
  challenge Sam 50             a coin flip between two players who both agree
  lottery, buy ticket 5        the weekly draw (Sundays, 12:00 UTC)

Every game keeps a house edge (economy.json "casino": about 4 to 8 percent),
so the casino takes credits out of the station over time. Bets are between
a minimum and a maximum, at most so many credits an hour, with a few seconds
between games; a big win is news for the whole station. What a player won
or lost in all is kept for the casino's leaderboard.
"""

import datetime
import logging
import math

import orbit_safety

logger = logging.getLogger("orbit.game")

CARDS = ("ace", "2", "3", "4", "5", "6", "7", "8", "9", "10", "jack", "queen", "king")
SLOT_NAMES = {"star": "star", "moon": "moon", "comet": "comet", "planet": "planet", "rocket": "rocket",
              "orbit": "Orbit"}
DICE_BETS = {"high": ("high", "big", "over"),
             "low": ("low", "small", "under"),
             "seven": ("seven", "7")}


def times(x):
    """2.3 as "2.3"."""
    return f"{float(x):g}"


def pays(bet, multiple):
    """`bet` times `multiple`, in whole credits (rounded down, as a casino would)."""
    return int(math.floor(bet * float(multiple) + 1e-9))


def dice_wins(choice, total):
    """Whether two dice totalling `total` win a bet on "high" (8-12), "low" (2-6) or "seven"."""
    return (choice == "high" and total >= 8) or (choice == "low" and total <= 6) or \
        (choice == "seven" and total == 7)


def card_value(cards):
    """The best blackjack total of `cards` (ranks 1-13; aces count 1 or 11)."""
    total = sum(min(10, c) for c in cards)
    if 1 in cards and total + 10 <= 21:
        total += 10
    return total


def slot_payout(reels, table):
    """What three reels pay, as a multiple of the bet (0 when nothing)."""
    if reels[0] == reels[1] == reels[2]:
        return float(table["three"].get(reels[0], 0))
    best = 0.0
    for symbol, pays in table["two"].items():
        if reels.count(symbol) == 2:
            best = max(best, float(pays))
    if not best and any(reels.count(s) == 2 for s in reels):
        best = float(table.get("pair", 0))
    return best


class CasinoMixin:
    @staticmethod
    def commands():
        return {"casino": CasinoMixin.cmd_casino, "dice": CasinoMixin.cmd_dice,
                "slots": CasinoMixin.cmd_slots, "blackjack": CasinoMixin.cmd_blackjack,
                "hit": CasinoMixin.cmd_hit, "stand": CasinoMixin.cmd_stand,
                "challenge": CasinoMixin.cmd_challenge, "lottery": CasinoMixin.cmd_lottery}

    # --- betting -------------------------------------------------------------------------

    def casino_here(self, char):
        """Whether `char` is in the Casino Corner (the room whose shop is the casino's)."""
        return self._loc(char).get("shop") == "casino"

    def _at_casino(self, session):
        if self.casino_here(session.char):
            return True
        casino = next((lid for lid, l in self.world.locations.items() if l.get("shop") == "casino"), None)
        self._error(session, "casino_where", where=self.world.locations[casino]["in"] if casino else "?")
        return False

    def _hour_bets(self, char):
        """What `char` bet in the last hour (kept a minute at a time: [[minute, total]...])."""
        now = self.now()
        bets = [b for b in char["stats"].get("casino_bets") or [] if now - float(b[0]) < 3600]
        char["stats"]["casino_bets"] = bets
        return sum(int(b[1]) for b in bets)

    def _note_bet(self, char, amount):
        minute = float(int(self.now() // 60) * 60)
        bets = char["stats"].setdefault("casino_bets", [])
        if bets and float(bets[-1][0]) == minute:
            bets[-1][1] = int(bets[-1][1]) + amount
        else:
            bets.append([minute, amount])

    def _can_bet(self, session, amount):
        """True when `amount` may be bet now (and the reason is said when not)."""
        char = session.char
        casino = self.econ["casino"]
        if amount is None:
            self._error(session, "casino_bet_how", low=casino["min_bet"], high=casino["max_bet"])
            return False
        if not casino["min_bet"] <= amount <= casino["max_bet"]:
            self._error(session, "casino_bet_range", low=casino["min_bet"], high=casino["max_bet"])
            return False
        if amount > char["credits"]:
            self._error(session, "no_credits", credits=char["credits"])
            return False
        if self._hour_bets(char) + amount > int(casino["hour_limit"]):
            self._error(session, "casino_hour_limit", limit=casino["hour_limit"])
            return False
        if self._cooldown_left(char, "casino") > 0:
            self._error(session, "casino_wait")
            return False
        return self._slow(session)

    def _take_bet(self, char, amount):
        self.spend(char, amount, "casino_bets")
        self._note_bet(char, amount)
        self._set_cooldown(char, "casino", float(self.econ["casino"]["cooldown"]))

    def _pay_out(self, session, bet, payout):
        """The house pays (or not); winnings and losses are counted for the leaderboard."""
        char = session.char
        if payout:
            self.earn(char, payout, "casino_wins")
        char["casino_net"] = int(char.get("casino_net") or 0) + payout - bet
        self._save(session)
        if payout - bet >= int(self.econ["casino"]["big_win"]):
            self._to_all("announce", "casino_big_win", exclude=(session,),
                         extra={"sound": "jackpot"}, name=session.name, n=payout)

    def cmd_casino(self, session, message):
        """The games and the rules; from anywhere else, the way to the casino."""
        if not self.casino_here(session.char):
            casino_id = next((lid for lid, l in self.world.locations.items() if l.get("shop") == "casino"), None)
            if casino_id:
                self.cmd_go(session, {"a": casino_id})
                return
        casino = self.econ["casino"]
        self._send(session, "info", "casino_menu", low=casino["min_bet"], high=casino["max_bet"],
                   limit=casino["hour_limit"], dice=times(casino["dice"]["high_low"]),
                   seven=times(casino["dice"]["seven"]), price=casino["lottery"]["price"])

    # --- dice --------------------------------------------------------------------------------

    def cmd_dice(self, session, message):
        if not self._at_casino(session):
            return
        char = session.char
        words = orbit_safety.name_key(self._arg(message, "a", 20))
        choice = next((k for k, names in DICE_BETS.items() if words in names), None)
        amount = self._count(message, default=None, high=10_000_000)
        if choice is None:
            self._error(session, "dice_how")
            return
        if not self._can_bet(session, amount):
            return
        self._take_bet(char, amount)
        a, b = self.rng.randint(1, 6), self.rng.randint(1, 6)
        total = a + b
        won = dice_wins(choice, total)
        multiple = self.econ["casino"]["dice"]["seven" if choice == "seven" else "high_low"]
        payout = pays(amount, multiple) if won else 0
        self._pay_out(session, amount, payout)
        key = "dice_won" if won else "dice_lost"
        self._send(session, "paid" if won else "failed", key, n=amount,
                   choice=self.render(session.lang, f"dice_{choice}"),
                   a=a, b=b, total=total, pay=payout, credits=char["credits"],
                   extra={"sound": "dice", "outcome": "win" if won else "lose"})

    # --- slots --------------------------------------------------------------------------------

    def cmd_slots(self, session, message):
        if not self._at_casino(session):
            return
        char = session.char
        amount = self._count(message, default=None, high=10_000_000)
        if not self._can_bet(session, amount):
            return
        self._take_bet(char, amount)
        table = self.econ["casino"]["slots"]
        reels = [self._pick(table["symbols"]) for _ in range(3)]
        multiple = slot_payout(reels, table)
        if reels[0] == reels[1] == reels[2]:
            multiple *= self.simple_factor("jackpot")        # jackpot night
        payout = pays(amount, multiple)
        jackpot = reels == ["orbit"] * 3
        if jackpot:
            key, outcome = "slots_jackpot", "jackpot"
            char["stats"]["jackpots"] = int(char["stats"].get("jackpots", 0)) + 1
        elif payout > amount:
            key, outcome = "slots_won", "win"
        elif payout == amount:
            key, outcome = "slots_even", "push"
        else:
            key, outcome = "slots_lost", "lose"
        self._pay_out(session, amount, payout)
        names = [SLOT_NAMES[r] for r in reels]
        self._send(session, "paid" if payout > amount else "failed", key,
                   first=names[0], second=names[1], third=names[2], pay=payout, credits=char["credits"],
                   extra={"sound": "reel_spin", "reels": reels, "outcome": outcome})

    # --- blackjack ------------------------------------------------------------------------------

    def _card(self):
        return self.rng.randint(1, 13)

    def _cards_text(self, lang, cards):
        return self.texts.join(lang, [CARDS[c - 1] for c in cards])

    def cmd_blackjack(self, session, message):
        if not self._at_casino(session):
            return
        char = session.char
        if session.blackjack:
            self._hand_text(session, "bj_hand")
            return
        amount = self._count(message, default=None, high=10_000_000)
        if not self._can_bet(session, amount):
            return
        self._take_bet(char, amount)
        seconds = float(self.econ["casino"]["blackjack"]["seconds"])
        hand = {"bet": amount, "player": [self._card(), self._card()],
                "dealer": [self._card(), self._card()], "deadline": self.now() + seconds}
        session.blackjack = hand
        self._save(session)
        if card_value(hand["player"]) == 21:
            char["stats"]["naturals"] = int(char["stats"].get("naturals", 0)) + 1
            self._finish_hand(session, natural=True)
            return
        if card_value(hand["dealer"]) == 21:
            self._finish_hand(session)          # the dealer peeks: a blackjack ends the hand
            return
        self._hand_text(session, "bj_start")

    def _hand_text(self, session, key):
        lang = session.lang
        hand = session.blackjack
        self._send(session, "task", key, cards=self._cards_text(lang, hand["player"]),
                   total=card_value(hand["player"]), up=self._cards_text(lang, hand["dealer"][:1]),
                   n=hand["bet"], extra={"sound": "deal" if key == "bj_start" else "cards"})

    def cmd_hit(self, session, message):
        hand = session.blackjack
        if not hand:
            self._error(session, "bj_none")
            return
        hand["player"].append(self._card())
        total = card_value(hand["player"])
        if total > 21:
            self._finish_hand(session, bust=True)
        elif total == 21:
            self._finish_hand(session)
        else:
            self._send(session, "task", "bj_hit", card=self._cards_text(session.lang, hand["player"][-1:]),
                       total=total, extra={"sound": "cards"})

    def cmd_stand(self, session, message):
        if not session.blackjack:
            self._error(session, "bj_none")
            return
        self._finish_hand(session)

    def _finish_hand(self, session, natural=False, bust=False):
        char, lang = session.char, session.lang
        hand, session.blackjack = session.blackjack, None
        rules = self.econ["casino"]["blackjack"]
        bet = hand["bet"]
        player = card_value(hand["player"])
        dealer_cards = list(hand["dealer"])
        if not bust and not natural:
            while card_value(dealer_cards) < int(rules["dealer_stands"]):
                dealer_cards.append(self._card())
        dealer = card_value(dealer_cards)
        dealer_natural = card_value(hand["dealer"]) == 21
        if bust:
            payout, key = 0, "bj_bust"
        elif natural:
            payout, key = (bet, "bj_push") if dealer_natural else (pays(bet, rules["natural"]), "bj_natural")
        elif dealer_natural and len(hand["player"]) == 2:
            payout, key = 0, "bj_dealer_natural"
        elif dealer > 21:
            payout, key = pays(bet, rules["win"]), "bj_dealer_bust"
        elif player > dealer:
            payout, key = pays(bet, rules["win"]), "bj_won"
        elif player == dealer:
            payout, key = bet, "bj_push"
        else:
            payout, key = 0, "bj_lost"
        self._pay_out(session, bet, payout)
        outcome = "win" if payout > bet else "push" if payout == bet else "lose"
        self._send(session, "paid" if payout > bet else "failed", key,
                   cards=self._cards_text(lang, hand["player"]), total=player,
                   dealer_cards=self._cards_text(lang, dealer_cards), dealer=dealer,
                   pay=payout, credits=char["credits"], extra={"sound": "cards", "outcome": outcome})

    def leave_casino(self, session):
        """`session` is leaving: an open hand is played out (standing), so the bet isn't lost."""
        if session.blackjack:
            self._finish_hand(session)

    def tick_casino(self, session, now):
        hand = session.blackjack
        if hand and now > hand["deadline"]:
            self._send(session, "system", "bj_timeout")
            self._finish_hand(session)
        challenge = self.challenges.get(session.key)
        if challenge and now > challenge["expires"]:
            self.challenges.pop(session.key, None)
            self._send(session, "system", "challenge_expired_you", name=challenge["from_name"])
            challenger = self.sessions.get(challenge["from"])
            if challenger is not None:
                self._send(challenger, "system", "challenge_expired", name=session.name)

    # --- a coin flip between two players --------------------------------------------------------

    def cmd_challenge(self, session, message):
        if not self._at_casino(session):
            return
        rules = self.econ["casino"]["coinflip"]
        name = self._arg(message, "to", 40)
        target = self._find_near(session, name) if name else None
        if target is None or target is session:
            self._error(session, "challenge_who")
            return
        stake = self._count(message, default=None, high=10_000_000)
        if stake is None or not rules["min"] <= stake <= rules["max"]:
            self._error(session, "challenge_range", low=rules["min"], high=rules["max"])
            return
        if stake > session.char["credits"]:
            self._error(session, "no_credits", credits=session.char["credits"])
            return
        if self._hour_bets(session.char) + stake > int(self.econ["casino"]["hour_limit"]):
            self._error(session, "casino_hour_limit", limit=self.econ["casino"]["hour_limit"])
            return
        if target.key in self.challenges:
            self._error(session, "challenge_busy", name=target.name)
            return
        if not self._slow(session):
            return
        self.challenges[target.key] = {"from": session.key, "from_name": session.name, "stake": stake,
                                       "expires": self.now() + float(rules["seconds"]), "at": self.now()}
        self._send(target, "offer", "challenge_you", n=stake, actor=session.name, seconds=int(rules["seconds"]),
                   extra={"actor": session.name, "ask": True, "sound": "offer"})
        self._info(session, "challenge_sent", name=target.name, n=stake)

    def accept_challenge(self, session):
        challenge = self.challenges.pop(session.key, None)
        if challenge is None:
            return False
        rules = self.econ["casino"]["coinflip"]
        other = self.sessions.get(challenge["from"])
        stake = int(challenge["stake"])
        if other is None or other.conn is None or self.room_of(other.char) != self.room_of(session.char):
            self._error(session, "challenge_gone", name=challenge["from_name"])
            return True
        for player in (session, other):
            if player.char["credits"] < stake:
                self._error(session, "challenge_poor", name=player.name)
                self._send(other, "error", "challenge_poor", name=player.name)
                return True
        winner, loser = (session, other) if self.rng.random() < 0.5 else (other, session)
        fee = int(round(2 * stake * float(rules["fee"])))
        with self.store.transaction():
            for player in (session, other):
                self._take_bet(player.char, stake)
            self.earn(winner.char, 2 * stake - fee, "casino_wins")
            winner.char["casino_net"] = int(winner.char.get("casino_net") or 0) + stake - fee
            loser.char["casino_net"] = int(loser.char.get("casino_net") or 0) - stake
            self.store.save_all([winner.char, loser.char])
        for player in (winner, loser):
            key = "coinflip_won" if player is winner else "coinflip_lost"
            opponent = loser if player is winner else winner
            self._send(player, "paid" if player is winner else "failed", key, name=opponent.name,
                       n=stake, pay=2 * stake - fee, fee=fee, credits=player.char["credits"],
                       extra={"sound": "coinflip", "outcome": "win" if player is winner else "lose"})
        self._to_room(self.room_of(session.char), "info", "coinflip_other", exclude=(session, other),
                      winner=winner.name, loser=loser.name, n=stake)
        return True

    def decline_challenge(self, session):
        challenge = self.challenges.pop(session.key, None)
        if challenge is None:
            return False
        other = self.sessions.get(challenge["from"])
        if other is not None:
            self._send(other, "system", "challenge_declined", name=session.name)
        self._info(session, "challenge_you_declined", name=challenge["from_name"])
        return True

    # --- the weekly lottery ------------------------------------------------------------------------

    def lottery_draw_time(self, after=None):
        """The next draw after `after` (a timestamp): the weekday and hour in economy.json (UTC)."""
        rules = self.econ["casino"]["lottery"]
        now = datetime.datetime.fromtimestamp(after if after is not None else self.now(), datetime.timezone.utc)
        day = now.replace(hour=int(rules["hour"]), minute=0, second=0, microsecond=0)
        day += datetime.timedelta(days=(int(rules["weekday"]) - day.weekday()) % 7)
        if day <= now:
            day += datetime.timedelta(days=7)
        return day.timestamp()

    def lottery_state(self):
        """{"draw": the next draw's time, "carry": credits carried over}, kept in meta."""
        if self._lottery is None:
            state = self.store.get_json("lottery", {}) or {}
            if not state.get("draw"):
                state = {"draw": self.lottery_draw_time(), "carry": int(state.get("carry", 0))}
                self.store.set_json("lottery", state)
            self._lottery = state
        return self._lottery

    def _set_lottery(self, state):
        self.store.set_json("lottery", state)
        self._lottery = state

    @staticmethod
    def _draw_key(draw):
        return datetime.datetime.fromtimestamp(float(draw), datetime.timezone.utc).strftime("%Y-%m-%d")

    def lottery_pot(self, state=None):
        state = state or self.lottery_state()
        rules = self.econ["casino"]["lottery"]
        sold = sum(n for _cid, n in self.store.lottery_entries(self._draw_key(state["draw"])))
        return int(state.get("carry", 0)) + int(sold * int(rules["price"]) * (1 - float(rules["house"])))

    def cmd_lottery(self, session, message):
        state = self.lottery_state()
        rules = self.econ["casino"]["lottery"]
        mine = self.store.tickets(self._draw_key(state["draw"]), session.char["id"])
        when = datetime.datetime.fromtimestamp(float(state["draw"]), datetime.timezone.utc)
        self._send(session, "info", "lottery", pot=self.lottery_pot(state), tickets=mine,
                   time=self._duration(session.lang, float(state["draw"]) - self.now()),
                   day=self.render(session.lang, f"weekday_{when.weekday()}"), hour=when.strftime("%H:%M"),
                   price=rules["price"], max=rules["max_tickets"])

    def buy_tickets(self, session, n):
        char = session.char
        rules = self.econ["casino"]["lottery"]
        state = self.lottery_state()
        key = self._draw_key(state["draw"])
        have = self.store.tickets(key, char["id"])
        if have + n > int(rules["max_tickets"]):
            self._error(session, "lottery_max", max=rules["max_tickets"], have=have)
            return
        total = n * int(rules["price"])
        if total > char["credits"]:
            self._error(session, "buy_poor", total=total, credits=char["credits"])
            return
        with self.store.transaction():
            self.spend(char, total, "lottery")
            self.store.add_tickets(key, char["id"], n)
            self._save(session)
        self._send(session, "trade", "lottery_bought", n=n, total=total, tickets=have + n,
                   pot=self.lottery_pot(state), credits=char["credits"], extra={"sound": "lottery"})

    def tick_lottery(self, now):
        """The weekly draw, when its time has come (after a long pause, just once)."""
        state = self.lottery_state()
        if now < float(state["draw"]):
            return
        key = self._draw_key(state["draw"])
        entries = self.store.lottery_entries(key)
        pot = self.lottery_pot(state)
        next_state = {"draw": self.lottery_draw_time(max(now, float(state["draw"]) + 1)), "carry": 0}
        winner_id = None
        if entries:
            roll = self.rng.random() * sum(n for _cid, n in entries)
            winner_id = entries[-1][0]
            for cid, n in entries:
                roll -= n
                if roll < 0:
                    winner_id = cid
                    break
        stored = self.store.by_id(winner_id) if winner_id is not None else None
        if stored is None or stored.get("banned"):
            next_state["carry"] = pot
            self._set_lottery(next_state)
            if entries:
                logger.info("the lottery of %s: no winner, %s carried over", key, pot)
            return
        session = self.sessions.get(stored["name_key"])
        char = session.char if session else stored
        with self.store.transaction():
            self.earn(char, pot, "lottery_prizes")
            char["stats"]["lotteries"] = int(char["stats"].get("lotteries", 0)) + 1
            self.store.save(char)
            self._set_lottery(next_state)
        logger.info("the lottery of %s: %s wins %s", key, char["name"], pot)
        self._to_all("announce", "lottery_won", extra={"sound": "lottery_draw"}, name=char["name"], n=pot)
        if session is not None:
            self.check_achievements(session, "lotteries")
        elif "lucky_draw" in self.econ.get("achievements", {}):
            self.award_offline(char, "lucky_draw")
