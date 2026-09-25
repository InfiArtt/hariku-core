# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Trading between players, and the pawn shop.

  offer Budi 3 iron for 200 credits      tawarkan Budi 3 besi untuk 200 kredit
  accept / decline                        terima / tolak
  cancel offer                            batalkan tawaran

An offer waits two minutes (economy.json "trading") for the other player,
who has to be online (anywhere on the station) and say yes. Then both sides
move at once in one database transaction: either both players have what
they promised and everything changes hands, or nothing does (and the
characters in memory are put back as they were). Goods, mission cargo,
seeds, food, furniture and clothes can be traded (and given); devices,
keycards, titles and the like can't.

Second Orbit, the pawn shop on the Mall Ring, buys the things you own (not
goods: those go to the market) for a fraction of their price (economy.json
"pawn"), and "list" there says what it would pay for yours.
"""

import copy
import logging
import re

import orbit_safety

logger = logging.getLogger("orbit.game")

SEPARATORS = ("for", "untuk", "seharga", "dengan", "demi", "ganti")
ARTICLES = {"a", "an", "the", "some", "se", "sebuah", "seekor", "sebiji", "satu"}
_NUMBER_RE = re.compile(r"^\d{1,9}$")


def split_offer(text):
    """ "3 iron for 200 credits" -> ("3 iron", "200 credits"); ("", "") when there's no "for"."""
    words = str(text or "").split()
    for i, word in enumerate(words):
        if word.lower() in SEPARATORS and 0 < i < len(words) - 1:
            return " ".join(words[:i]), " ".join(words[i + 1:])
    return "", ""


class TradeMixin:
    @staticmethod
    def commands():
        return {"offer": TradeMixin.cmd_offer, "decline": TradeMixin.cmd_decline,
                "cancel_offer": TradeMixin.cmd_cancel_offer}

    # --- the two sides of an offer ------------------------------------------------------------

    def _side(self, text):
        """(thing id or "credits", n) for "3 iron", "iron 3", "200 credits", "a headlamp"; or None."""
        n, words = None, []
        for word in str(text or "").split():
            clean = word.strip(".,!?;:").lower()
            if n is None and _NUMBER_RE.match(clean):
                n = int(clean)
            elif clean not in ARTICLES:
                words.append(clean)
        name = " ".join(words)
        if not name:
            return None
        if orbit_safety.name_key(name) in _credit_words():
            return ("credits", n) if n else None
        tid = self.world.find_good(name) or self.world.find_item(name) or self.world.find_thing(name)
        if tid is None:
            return None
        return tid, n or 1

    def _side_text(self, side):
        what, n = side
        if what == "credits":
            return {"en": f"{n} credits", "id": f"{n} kredit"}
        return self._count_of(what, n)

    def _tradeable(self, tid):
        """Goods, mission cargo, furniture and clothes (no level needed), and things marked tradeable."""
        info = self.world.things.get(tid, {})
        if info.get("type") in ("good", "cargo") or info.get("tradeable"):
            return True
        return info.get("type") in ("furniture", "outfit") and not info.get("level") and info.get("pawn") is not False

    def _side_problem(self, owner, receiver, side, back=None):
        """Why `owner` can't hand `side` to `receiver` (a text key and its params), or None.
        `back` is what `receiver` hands over in return (it frees room in their bag)."""
        what, n = side
        if what == "credits":
            if owner["credits"] < n:
                return "trade_poor", {"name": owner["name"], "n": n}
            return None
        info = self.world.things[what]
        if not self._tradeable(what):
            return "cant_trade", {"thing": info["many"]}
        if owner["inventory"].get(what, 0) < n:
            return "trade_missing", {"name": owner["name"], "things": self._count_of(what, n)}
        if info.get("unique") and receiver["inventory"].get(what):
            return "they_have_one", {"name": receiver["name"]}
        if info["type"] == "good":
            freed = back[1] if back and back[0] in self.world.goods else 0
            if self._goods_count(receiver) - freed + n > self.bag_size(receiver):
                return "their_bag_full", {"name": receiver["name"]}
        return None

    def _hand_over(self, owner, receiver, side):
        what, n = side
        if what == "credits":
            owner["credits"] = int(owner["credits"]) - n
            receiver["credits"] = int(receiver["credits"]) + n
            return
        self._take_away(owner, what, n)
        if not owner["inventory"].get(what):
            worn = self.worn(owner)
            for slot in [s for s, t in worn.items() if t == what]:
                worn.pop(slot, None)
        self.give_thing(receiver, what, n)

    # --- offering, accepting ------------------------------------------------------------------

    def cmd_offer(self, session, message):
        char = session.char
        name = self._arg(message, "to", 40)
        give_text, get_text = split_offer(self._arg(message, "a", 200))
        target = self._find_session(name) if name else None
        if target is None or target.conn is None or (target.invisible and not self.is_admin(session)):
            self._error(session, "offer_who" if not name else "not_online", name=name or "?")
            return
        if target is session:
            self._error(session, "give_self")
            return
        give, get = self._side(give_text), self._side(get_text)
        if give is None or get is None:
            self._error(session, "offer_how")
            return
        if give[0] == get[0]:
            self._error(session, "offer_same")
            return
        problem = self._side_problem(char, target.char, give)
        if problem:
            self._error(session, problem[0], **problem[1])
            return
        if not self._slow(session):
            return
        if target.key in self.offers:
            self._error(session, "offer_busy", name=target.name)
            return
        mine = next((k for k, o in self.offers.items() if o["from"] == session.key), None)
        if mine is not None:
            old = self.offers.pop(mine)
            other = self.sessions.get(mine)
            if other is not None:
                self._send(other, "system", "offer_withdrawn", name=session.name)
            logger.info("%s replaced an offer to %s", session.name, old["to_name"])
        seconds = float(self.econ.get("trading", {}).get("seconds", 120))
        self.offers[target.key] = {"from": session.key, "from_name": session.name, "to_name": target.name,
                                   "give": give, "get": get, "expires": self.now() + seconds, "at": self.now()}
        self._send(target, "offer", "offer_you", actor=session.name, give=self._side_text(give),
                   get=self._side_text(get), time=self._duration(target.lang, seconds),
                   extra={"actor": session.name, "ask": True, "sound": "offer"})
        self._info(session, "offer_sent", name=target.name, give=self._side_text(give), get=self._side_text(get))

    def _asks(self, session):
        """What waits for `session`'s yes or no, newest last: [(when, accept, decline)]."""
        waiting = []
        for table, accept, decline in ((self.offers, self.accept_offer, self._decline_offer),
                                       (self.challenges, self.accept_challenge, self.decline_challenge),
                                       (self.crew_invites, self.accept_crew_invite, self.decline_crew_invite)):
            entry = table.get(session.key)
            if entry:
                waiting.append((entry["at"], accept, decline))
        waiting.sort(key=lambda w: w[0])
        return waiting

    def accept_pending(self, session):
        """ "accept" with no number: the newest offer, challenge or invitation waiting for you."""
        waiting = self._asks(session)
        if not waiting:
            return False
        done = waiting[-1][1](session)
        return True if done is None else done

    def accept_offer(self, session):
        offer = self.offers.pop(session.key, None)
        if offer is None:
            return False
        other = self.sessions.get(offer["from"])
        if other is None or other.conn is None:
            self._error(session, "offer_gone", name=offer["from_name"])
            return True
        seller, buyer = other.char, session.char
        give, get = offer["give"], offer["get"]
        problem = self._side_problem(seller, buyer, give, back=get) or \
            self._side_problem(buyer, seller, get, back=give)
        if problem:
            self._error(session, problem[0], **problem[1])
            self._send(other, "error", problem[0], **problem[1])
            return True
        before = [(c, int(c["credits"]), copy.deepcopy(c["inventory"]), copy.deepcopy(c["stats"]))
                  for c in (seller, buyer)]
        try:
            with self.store.transaction():
                self._hand_over(seller, buyer, give)
                self._hand_over(buyer, seller, get)
                for c in (seller, buyer):
                    c["stats"]["trades"] = int(c["stats"].get("trades") or 0) + 1
                self.store.save_all([seller, buyer])
        except Exception:
            for c, credits, inventory, stats in before:
                c["credits"], c["inventory"], c["stats"] = credits, inventory, stats
            logger.exception("a trade between %s and %s failed", other.name, session.name)
            self._error(session, "trade_failed")
            self._send(other, "error", "trade_failed")
            return True
        logger.info("trade: %s gave %s %s for %s", other.name, session.name, give, get)
        self._send(other, "trade", "trade_done", name=session.name, gave=self._side_text(give),
                   got=self._side_text(get), credits=seller["credits"], extra={"sound": "trade"})
        self._send(session, "trade", "trade_done", name=other.name, gave=self._side_text(get),
                   got=self._side_text(give), credits=buyer["credits"], extra={"sound": "trade"})
        self.check_achievements(other, "trades")
        return True

    def cmd_decline(self, session, message):
        waiting = self._asks(session)
        if waiting and waiting[-1][2](session):
            return
        self._error(session, "nothing_to_decline")

    def _decline_offer(self, session):
        offer = self.offers.pop(session.key, None)
        if offer is None:
            return False
        other = self.sessions.get(offer["from"])
        if other is not None:
            self._send(other, "system", "offer_declined", name=session.name)
        self._info(session, "offer_you_declined", name=offer["from_name"])
        return True

    def cmd_cancel_offer(self, session, message):
        for key, offer in list(self.offers.items()):
            if offer["from"] == session.key:
                self.offers.pop(key, None)
                other = self.sessions.get(key)
                if other is not None:
                    self._send(other, "system", "offer_withdrawn", name=session.name)
                self._info(session, "offer_cancelled", name=offer["to_name"])
                return
        for key, challenge in list(self.challenges.items()):
            if challenge["from"] == session.key:
                self.challenges.pop(key, None)
                other = self.sessions.get(key)
                if other is not None:
                    self._send(other, "system", "challenge_withdrawn", name=session.name)
                self._info(session, "offer_cancelled", name=other.name if other else "?")
                return
        self._error(session, "no_offer")

    def tick_offers(self, now):
        for key, offer in list(self.offers.items()):
            if now < offer["expires"]:
                continue
            self.offers.pop(key, None)
            target, other = self.sessions.get(key), self.sessions.get(offer["from"])
            if target is not None:
                self._send(target, "system", "offer_expired_you", name=offer["from_name"])
            if other is not None:
                self._send(other, "system", "offer_expired", name=offer["to_name"])

    def forget_offers(self, session):
        """`session` left: its offers and challenges, and the ones waiting for it, are off."""
        for table, key_name in ((self.offers, "offer_withdrawn"), (self.challenges, "challenge_withdrawn")):
            for key, entry in list(table.items()):
                if key == session.key:
                    table.pop(key, None)
                    other = self.sessions.get(entry["from"])
                    if other is not None:
                        self._send(other, "system", "offer_left", name=session.name)
                elif entry["from"] == session.key:
                    table.pop(key, None)
                    other = self.sessions.get(key)
                    if other is not None:
                        self._send(other, "system", key_name, name=session.name)

    # --- the pawn shop ------------------------------------------------------------------------

    def pawn_value(self, tid):
        """What Second Orbit pays for one `tid` (0: it doesn't buy it)."""
        thing = self.world.things.get(tid)
        if not thing or tid in self.world.goods or thing.get("pawn") is False or thing.get("service"):
            return 0
        if thing.get("type") in ("cargo", "pet"):
            return 0
        return int(int(thing.get("price") or 0) * float(self.econ.get("pawn", {}).get("rate", 0.4)))

    def pawn_list(self, session):
        char, lang = session.char, session.lang
        entries = [self.render(lang, "shop_entry", thing=self.world.things[tid]["one"],
                               price=self.pawn_value(tid), notes="")
                   for tid, n in sorted(char["inventory"].items()) if n > 0 and self.pawn_value(tid)]
        if not entries:
            self._info(session, "pawn_nothing")
            return
        self._info(session, "pawn_list", entries="; ".join(entries))

    def pawn_sell(self, session, message):
        char = session.char
        text = self._arg(message, "item", 60)
        tid = self.find_owned(char, text) if text else None
        if tid is None:
            if text and self.world.find_good(text):
                self._error(session, "pawn_goods")
            else:
                self._error(session, "pawn_what", what=text or "?")
            return
        if tid in self.world.goods:
            self._error(session, "pawn_goods")
            return
        value = self.pawn_value(tid)
        if not value:
            self._error(session, "pawn_no", thing=self.world.things[tid]["many"])
            return
        have = char["inventory"].get(tid, 0)
        n = self._count(message, default=1, high=1000) if message.get("n") != "all" else have
        if n is None or n > have:
            self._error(session, "not_enough", things=self._count_of(tid, have))
            return
        if not self._slow(session):
            return
        worn = self.worn(char)
        if n == have and tid in worn.values():
            if worn.get("suit") == tid and self._loc(char).get("airless"):
                self._error(session, "not_out_here")
                return
            for slot in [s for s, t in worn.items() if t == tid]:
                worn.pop(slot, None)
        self._take_away(char, tid, n)
        self.earn(char, value * n, "pawn")
        self._save(session)
        self._send(session, "trade", "pawn_sold", things=self._count_of(tid, n), total=value * n,
                   credits=char["credits"], extra={"sound": "register"})


def _credit_words():
    return {"credit", "credits", "kredit", "cr", "uang", "duit", "money", "coins"}
