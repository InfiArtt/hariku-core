# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Money: the markets, the farm, mining and salvage, your profile, and the
economy's totals.

The station's goods are traded at four markets, each dealing in its own:
the Spice Market west of Hydroponics (coffee, spices, crops), the Ice Depot
north of the Cargo Bay (comet ice, helium-3, frost pearls), the Mineral
Exchange north of the Dock (ores, meteorites) and the Workshop's parts
counter (salvage, memory chips). A good is traded at one market on each
world, so a world's prices are its market's. "prices" (harga) and "list"
say what the market you stand in buys and sells, at its prices; anywhere
else, where the nearest market for what you asked about is, and the way.
Prices drift every few minutes back towards each good's usual price and move
a little with every unit traded, so selling a big load at once pays less per
unit. The old miner on the Belt Platform buys ore for three quarters of the
price. Buying costs a fee and selling loses a spread (less for traders, and
less again with a trader's tools), so buying and selling back at once always
loses.

The farm: your own plots in Hydroponics (2 to start, more to buy). Plant
seeds, and they ripen in real time, from ten minutes (kangkung) to a day
(moon melons); water them once while they grow for an extra crop; harvest
what's ripe. You're told when something ripens.

Mining at the Asteroid Belt: "mine" gives a lump of ore now and then (a
break between strikes, shorter with a better drill), richer out on the
Asteroid Surface and richest in the Crystal Cave. Salvage in the Debris Field
outside the hull. Both need room in your bag, and both can turn up a rare
find.

Other worlds' markets (world.json "worlds": "prices") start from the same
prices times the world's own factor for each good (ice is dear on Karmina
and cheap on Glasir), and each world's prices wander on their own and move
with every unit traded there (economy.json "travel": "market"), coming back
towards the usual over the next half hour or so: buying cheap here and
selling dear there is a trade run, and a big load moves both markets.
Contraband sells only in the Drift Bazaar's back alley and Lumina City's
Night Market. With your own ship docked on the same world, what doesn't fit
in your bag goes into its hold, and selling empties the hold too.

Every credit made or spent is counted by where it came from or went (the
admins' "economy" report), in the database's meta table.
"""

import math

import orbit_safety
from orbit_lang import pick

TRADE_FEES = {"trader": (0.02, 0.04)}    # (added when buying, taken when selling)
PUBLIC_FEES = (0.10, 0.12)
PRICE_IMPACT = 0.02                     # each unit bought or sold moves the price this much
KIND_WORDS = {
    "trade": ("trade", "trade goods", "dagang", "barang dagangan", "dagangan"),
    "contraband": ("contraband", "black market", "smuggled", "barang gelap", "selundupan", "gelap"),
    "crop": ("crop", "crops", "panen", "hasil panen", "sayur", "buah", "hasil kebun", "produce"),
    "ore": ("ore", "ores", "bijih", "tambang", "hasil tambang", "rocks", "batuan"),
    "salvage": ("salvage", "rongsok", "rongsokan", "hasil pulung", "junk"),
}
RARE_ORE = {"platinum", "meteorite", "quantum", "goldfoil", "satchip", "frostpearl", "ember_crystal"}
KIND_ORDER = ("trade", "crop", "ore", "salvage", "contraband")
MARKET_WORDS = {"market", "markets", "nearest market", "a market", "pasar", "pasarnya", "pasar terdekat"}
VOICE_STYLES = 10


class Market:
    """The market's prices: they drift every few minutes, back towards
    each good's usual price, and move a little with every unit traded."""

    def __init__(self, goods, store, rng, clock, period, worlds=None, rules=None):
        self.goods = goods
        self.store = store
        self.rng = rng
        self.clock = clock
        self.period = period
        self.worlds = worlds or {}
        self.rules = rules or {"impact": 0.01, "drift": 0.03, "revert": 0.15, "low": 0.6, "high": 1.6}
        local = store.get_json("market_worlds", {}) or {}
        self.local = {}
        for wid in self.worlds:
            if wid == "station":
                continue
            values = local.get(wid) if isinstance(local.get(wid), dict) else {}
            self.local[wid] = {}
            for gid in goods:
                try:
                    self.local[wid][gid] = self._clamp_local(float(values.get(gid, 1.0)))
                except (TypeError, ValueError):
                    self.local[wid][gid] = 1.0
        state = store.get_json("market", {}) or {}
        prices = state.get("prices") if isinstance(state.get("prices"), dict) else {}
        self.prices = {}
        for gid, good in goods.items():
            try:
                self.prices[gid] = self._clamp(gid, float(prices.get(gid, good["base"])))
            except (TypeError, ValueError):
                self.prices[gid] = float(good["base"])
        self.next_drift = float(state.get("next", 0) or 0)
        overrides = state.get("overrides") if isinstance(state.get("overrides"), dict) else {}
        self.overrides = {gid: v for gid, v in overrides.items() if gid in goods}

    def _clamp(self, gid, price):
        base = self.goods[gid]["base"]
        return max(0.4 * base, min(2.5 * base, price))

    def _clamp_local(self, value):
        return max(float(self.rules["low"]), min(float(self.rules["high"]), value))

    def save(self):
        self.store.set_json("market", {"prices": self.prices, "next": self.next_drift,
                                       "overrides": self.overrides})
        self.store.set_json("market_worlds", {wid: {g: round(v, 4) for g, v in goods.items()}
                                              for wid, goods in self.local.items()})

    def local_factor(self, wid, gid):
        """How a world's price for `gid` compares to the station's: its own factor, and where it
        has wandered to."""
        if not wid or wid not in self.local:
            return 1.0
        return float(self.worlds[wid].get("prices", {}).get(gid, 1.0)) * self.local[wid].get(gid, 1.0)

    def price(self, gid):
        override = self.overrides.get(gid)
        if override and float(override.get("until", 0)) > self.clock():
            return float(override["price"])
        return self.prices[gid]

    def tick(self, now):
        expired = [gid for gid, o in self.overrides.items() if float(o.get("until", 0)) <= now]
        for gid in expired:
            self.overrides.pop(gid, None)
        if now < self.next_drift:
            if expired:
                self.save()
            return False
        for gid, good in self.goods.items():
            price = self.prices[gid]
            price += 0.15 * (good["base"] - price)
            price *= math.exp(self.rng.gauss(0.0, good.get("volatility", 0.06)))
            self.prices[gid] = self._clamp(gid, price)
        revert, drift = float(self.rules["revert"]), float(self.rules["drift"])
        for goods in self.local.values():
            for gid, value in goods.items():
                value += revert * (1.0 - value)
                value *= math.exp(self.rng.gauss(0.0, drift))
                goods[gid] = self._clamp_local(value)
        self.next_drift = now + self.period
        self.save()
        return True

    @staticmethod
    def fees(job):
        return TRADE_FEES.get(job, PUBLIC_FEES)

    @classmethod
    def _unit(cls, price, fees, side):
        # Buying rounds up and selling down, so buying and selling back at
        # once always loses a little: prices must move to make a profit.
        fee, spread = fees
        if side == "buy":
            return max(1, int(math.ceil(price * (1 + fee) - 1e-9)))
        return max(1, int(math.floor(price * (1 - spread) + 1e-9)))

    event_factor = None                   # the game's: an event moving one world's prices

    def _event(self, world, gid):
        return self.event_factor(world, gid) if self.event_factor and world else 1.0

    def unit_price(self, gid, job, side, fees=None, factor=1.0, world=None):
        price = self.price(gid) * factor * self.local_factor(world, gid) * self._event(world, gid)
        return self._unit(price, fees or self.fees(job), side)

    def impact(self, world):
        return PRICE_IMPACT if world not in self.local else float(self.rules["impact"])

    def quote(self, gid, job, side, n, fees=None, factor=1.0, world=None):
        """The total for `n` units, the price moving with each one."""
        price, total = self.price(gid) * factor * self.local_factor(world, gid) * self._event(world, gid), 0
        step = self.impact(world)
        for _ in range(n):
            total += self._unit(price, fees or self.fees(job), side)
            price *= (1 + step) if side == "buy" else (1 - step)
        return total

    def trade(self, gid, side, n, world=None):
        """`n` units traded (on `world`: its own prices move; the station's move everyone's)."""
        step = self.impact(world)
        factor = (1 + step) if side == "buy" else (1 - step)
        if world in self.local:
            self.local[world][gid] = self._clamp_local(self.local[world][gid] * factor ** n)
        else:
            self.prices[gid] = self._clamp(gid, self.prices[gid] * factor ** n)
        self.save()


class EconomyMixin:
    @staticmethod
    def commands():
        return {"prices": EconomyMixin.cmd_prices, "buy": EconomyMixin.cmd_buy,
                "sell": EconomyMixin.cmd_sell, "plant": EconomyMixin.cmd_plant,
                "harvest": EconomyMixin.cmd_harvest, "water": EconomyMixin.cmd_water,
                "farm": EconomyMixin.cmd_farm, "mine": EconomyMixin.cmd_mine,
                "collect": EconomyMixin.cmd_collect, "profile": EconomyMixin.cmd_profile,
                "voice": EconomyMixin.cmd_voice}

    # --- the economy's totals ------------------------------------------------------------

    def init_economy(self):
        self.market = Market(self.world.goods, self.store, self.rng, self.clock,
                             self.config["market_seconds"], worlds=self.world.worlds,
                             rules=self.econ.get("travel", {}).get("market"))
        flows = self.store.get_json("economy", {}) or {}
        self.flows = {"earned": dict(flows.get("earned") or {}), "spent": dict(flows.get("spent") or {})}
        self._flows_dirty = False
        self._flows_saved = self.now()

    def earn(self, char, amount, source):
        amount = int(amount)
        char["credits"] = int(char["credits"]) + amount
        self.flows["earned"][source] = int(self.flows["earned"].get(source, 0)) + amount
        self._flows_dirty = True

    def spend(self, char, amount, sink):
        amount = int(amount)
        char["credits"] = int(char["credits"]) - amount
        self.flows["spent"][sink] = int(self.flows["spent"].get(sink, 0)) + amount
        self._flows_dirty = True

    def save_economy(self):
        self.store.set_json("economy", self.flows)
        self._flows_dirty = False
        self._flows_saved = self.now()

    def tick_economy(self, now):
        if self._flows_dirty and now - self._flows_saved >= 30:
            self.save_economy()

    # --- the markets ----------------------------------------------------------------
    #
    # Each market room buys and sells its own goods (world.json: a room's "market"), and
    # the prices are listed where they are paid: "prices" and "list" in a market say what
    # this market deals in, at its prices. Anywhere else they say where the nearest market
    # for what you asked about is, and the way there.

    def market_here(self, char):
        """The market where you stand (World.markets: "buys" and "sells" by good, "factor",
        "prices", "about"), or None."""
        return self.world.markets.get(char["location"])

    def fees_for(self, char):
        return self.effects(char)["fees"] or Market.fees(char["job"])

    def market_unit(self, lid, gid, char, side):
        """One `gid` at market `lid`: what it costs `char` ("buy") or brings them ("sell")."""
        return self.market.unit_price(gid, char["job"], side, self.fees_for(char),
                                      self.world.market_factor(lid, gid), self.world.world_of(lid))

    def market_quote(self, lid, gid, char, side, n):
        return self.market.quote(gid, char["job"], side, n, self.fees_for(char),
                                 self.world.market_factor(lid, gid), self.world.world_of(lid))

    def kind_name(self, kind):
        return {lang: self.render(lang, f"kind_{kind}") for lang in ("en", "id")}

    def good_word(self, gid):
        """A good as a word ("coffee", "kopi"), not a measure of it ("sacks of coffee")."""
        names = self.world.goods[gid]["names"]
        return {lang: names[lang][0] for lang in ("en", "id")}

    def asked_goods(self, text):
        """What a player asks about: (what, goods). `what` names it in both languages (None:
        everything); `goods` is a set of good ids (every good for nothing typed), or None when
        the words name no good and no kind of goods."""
        key = orbit_safety.name_key(text)
        if not key:
            return None, set(self.world.goods)
        for kind, words in KIND_WORDS.items():
            if key in words:
                return self.kind_name(kind), {gid for gid, good in self.world.goods.items()
                                              if good.get("kind", "trade") == kind}
        gid = self.world.find_good(text)
        if gid is not None:
            return self.good_word(gid), {gid}
        return text, None

    def market_about(self, lid):
        """What a market deals in, in words: its "about", or the kinds and goods it trades."""
        market = self.world.markets[lid]
        if market.get("about"):
            return market["about"]
        dealt = market["buys"] | market["sells"]
        words = []
        for kind in KIND_ORDER:
            of_kind = {gid for gid, good in self.world.goods.items() if good.get("kind", "trade") == kind}
            if of_kind and of_kind <= dealt:
                words.append(self.kind_name(kind))
            else:
                words.extend(self.good_word(gid) for gid in self.world.goods if gid in dealt & of_kind)
        return {lang: self.texts.join(lang, words) for lang in ("en", "id")}

    def markets_for(self, char, goods, side=None):
        """[(market room, the route there or None)]: the markets dealing in any of `goods`
        (side "buys": those that buy them from you; "sells": those that sell them), nearest
        first. The markets of the world you're on; with none there, those you can walk (or ride
        the Kancil) to."""
        here = char["location"]
        wid = self.world_here(char)
        found = []
        for lid, market in self.world.markets.items():
            dealt = market[side] if side else market["buys"] | market["sells"]
            if not dealt & goods or lid == here:
                continue
            path = self.route_for(char, lid) if self.world.world_of(here) else None
            same = self.world.world_of(lid) == wid
            if not same and path is None:
                continue
            found.append((0 if same else 1, len(path) if path is not None else 1000, lid, path))
        found.sort(key=lambda entry: entry[:3])
        if found and found[0][0] == 0:
            found = [entry for entry in found if entry[0] == 0]
        return [(lid, path) for _same, _n, lid, path in found]

    def nearest_market(self, char, goods=None):
        found = self.markets_for(char, goods or set(self.world.goods))
        return found[0][0] if found else None

    def market_entries(self, session, found, about=False):
        """ "the Spice Market, west, north, then west" for each (market, route): the way when
        you may ask it (the landmarks, or your mapper), else the deck it's on."""
        char, lang = session.char, session.lang
        known = self.guide_rooms(char)
        entries = []
        for lid, path in found:
            loc = self.world.locations[lid]
            place = pick(loc["ref"], lang)
            if about:
                place = self.render(lang, "market_about", place=place, about=self.market_about(lid))
            if path is not None and (lid in known or self.is_admin(session)):
                way = self.steps_text(lang, path)
            else:
                way = self.world.area_of(lid).get("in", "")
            entries.append(self.render(lang, "market_entry", place=place, way=way))
        return "; ".join(entries)

    def market_pointer(self, session, what=None, goods=None, side=None):
        """Where to go for `goods` (named `what`), from here: "Nearest market for coffee: the
        Spice Market, west, north, then west." With no goods: every market near."""
        char, lang = session.char, session.lang
        everything = goods is None or goods == set(self.world.goods)
        found = self.markets_for(char, goods or set(self.world.goods), side)
        place = self.world.worlds.get(self.world_here(char) or "station", {}).get("in", "")
        if not found:
            if everything:
                return self.render(lang, "prices_none_here", place=place)
            return self.render(lang, "market_none_world", what=what, place=place)
        if everything:
            return self.render(lang, "markets_nearest", markets=self.market_entries(session, found[:6], about=True))
        if len(goods) == 1:
            found = found[:1]
        return self.render(lang, "market_nearest", what=what, markets=self.market_entries(session, found[:4]))

    def markets_sign(self, session):
        """The Promenade's signpost: every market near, what it deals in, and the way."""
        found = self.markets_for(session.char, set(self.world.goods))
        self._info(session, "markets_sign", markets=self.market_entries(session, found, about=True))

    def market_list(self, session, lid, what, goods):
        """What market `lid` buys and sells (of `goods`), at its prices, by kind."""
        char, lang = session.char, session.lang
        market = self.world.markets[lid]
        shown = (market["buys"] | market["sells"]) & goods
        if not shown:
            self._error(session, "market_not_here", what=what,
                        pointer=self.market_pointer(session, what, goods))
            return
        groups = []
        for kind in KIND_ORDER:
            entries = []
            for gid, good in self.world.goods.items():
                if gid not in shown or good.get("kind", "trade") != kind:
                    continue
                buy = self.market_unit(lid, gid, char, "buy") if gid in market["sells"] else None
                sell = self.market_unit(lid, gid, char, "sell") if gid in market["buys"] else None
                key = "price_entry" if buy and sell else "price_entry_buy" if buy else "price_entry_sell"
                entries.append(self.render(lang, key, good=good["one"], buy=buy, sell=sell))
            if entries:
                groups.append(self.render(lang, f"prices_{kind}", entries="; ".join(entries)))
        key = "prices_trader" if char["job"] == "trader" else "prices"
        self._info(session, key, where=self.world.locations[lid]["in"], entries=". ".join(groups))

    def scan_prices(self, session, wid):
        """A Hornbill's scanner bay reads another world's markets (a report: you trade there)."""
        char, lang = session.char, session.lang
        ship = self.ship_aboard(char)
        if ship is None or not self.ship_spec(ship).get("scanner"):
            self._error(session, "prices_remote", place=self.world.worlds[wid]["ref"])
            return
        parts = []
        for lid, market in self.world.markets.items():
            if self.world.world_of(lid) != wid:
                continue
            entries = []
            for gid, good in self.world.goods.items():
                if gid not in market["buys"] | market["sells"]:
                    continue
                buy = self.market_unit(lid, gid, char, "buy") if gid in market["sells"] else None
                sell = self.market_unit(lid, gid, char, "sell") if gid in market["buys"] else None
                key = "price_entry" if buy and sell else "price_entry_buy" if buy else "price_entry_sell"
                entries.append(self.render(lang, key, good=good["one"], buy=buy, sell=sell))
            parts.append(self.render(lang, "scan_market", place=self.world.locations[lid]["ref"],
                                     entries="; ".join(entries)))
        if not parts:
            self._error(session, "prices_none_here", place=self.world.worlds[wid]["in"])
            return
        self._info(session, "prices_scan", place=self.world.worlds[wid]["ref"], markets=" ".join(parts),
                   sound="scan")

    def cmd_prices(self, session, message):
        """ "prices" / "harga": at a market, what it buys and sells here; in a shop, its list; at
        the pawn shop, what it would pay; anywhere else, the way to the nearest market."""
        char = session.char
        text = self._arg(message, "a", 40)
        what, goods = self.asked_goods(text)
        if goods is None:
            wid = self.world.find_world(text)
            if wid is not None:
                self.scan_prices(session, wid)
                return
        here = char["location"]
        if here in self.world.markets:
            if goods is None:
                self._unknown_good(session, text)
                return
            self.market_list(session, here, what, goods)
            return
        sid, shop = self.shop_here(char)
        if shop is not None and not (text and goods):
            tid = self.world.find_thing(text) if text else None
            if tid in shop.get("stock", []):
                self._info(session, "shop_list", shop=shop["name"], entries=self.entry_text(session.lang, char, tid, sid))
            else:
                self.cmd_list(session, {"a": text})
            return
        if self._loc(char).get("pawn") and not (text and goods):
            self.pawn_list(session)
            return
        if goods is None:
            self._unknown_good(session, text)
            return
        ship = self.ship_aboard(char)
        if not text and ship is not None and self.ship_spec(ship).get("scanner") and self.world_here(char):
            self.scan_prices(session, self.world_here(char))
            return
        self._info(session, "not_at_market", pointer=self.market_pointer(session, what, goods))

    def _unknown_good(self, session, text):
        """Words that name no good: a thing sold in a shop says where, else nobody sells it."""
        tid = self.world.find_thing(text)
        place = self.where_sold(tid) if tid is not None and tid not in self.world.goods else None
        if place:
            self._error(session, "sold_at", thing=self.world.things[tid]["many"],
                        place=self.world.locations[place]["ref"])
        else:
            self._error(session, "no_good", what=text or "?")

    def _good_and_count(self, session, message, allow_all=False, high=None):
        good = self.world.find_good(self._arg(message, "item", 60))
        if good is None:
            self._error(session, "no_good", what=self._arg(message, "item", 60) or "?")
            return None, None
        if allow_all and message.get("n") == "all":
            return good, session.char["inventory"].get(good, 0) or None
        n = self._count(message, high=high or self.bag_size(session.char))
        if n is None:
            self._error(session, "bad_number")
        return good, n

    def cmd_buy(self, session, message):
        char = session.char
        text = self._arg(message, "item", 60)
        sid, shop = self.shop_here(char)
        if shop is not None:
            tid = self.world.find_thing(text)
            if tid in shop.get("stock", []):
                ticket = self.world.things[tid].get("service") == "ticket"
                most = int(self.world.things[tid].get("max_buy", 20))
                n = self._count(message, high=int(self.econ["casino"]["lottery"]["max_tickets"]) if ticket else most)
                if n is None:
                    self._error(session, "bad_number")
                    return
                if self._slow(session):
                    self.buy_thing(session, tid, n)
                return
        lid = char["location"]
        here = self.market_here(char)
        good = self.world.find_good(text)
        if here is None or good is None or good not in here["sells"]:
            if good is None:
                self._unknown_good(session, text)
                return
            pointer = self.market_pointer(session, self.good_word(good), {good}, "sells")
            if here is None:
                self._error(session, "not_at_market", pointer=pointer)
            else:
                self._error(session, "market_doesnt_sell", thing=self.world.goods[good]["many"], pointer=pointer)
            return
        ship = self.ship_docked_here(char)
        room = self.bag_size(char) - self._goods_count(char)
        hold = self.hold_space(ship) if ship else 0
        good, n = self._good_and_count(session, message, high=max(self.bag_size(char), room + hold))
        if n is None:
            return
        if n > room + hold:
            if ship:
                self._error(session, "bag_and_hold_full", n=room + hold)
            else:
                self._error(session, "bag_full", max=self.bag_size(char))
            return
        total = self.market_quote(lid, good, char, "buy", n)
        if total > char["credits"]:
            self._error(session, "buy_poor", total=total, credits=char["credits"])
            return
        to_bag = min(n, room)
        with self.store.transaction():
            self.spend(char, total, "market")
            if to_bag:
                char["inventory"][good] = char["inventory"].get(good, 0) + to_bag
            if n > to_bag:
                ship["cargo"][good] = int(ship["cargo"].get(good, 0)) + n - to_bag
                self.store.save_ship(ship)
            self.market.trade(good, "buy", n, self.world.world_of(lid))
            self._save(session)
        text = self.render(session.lang, "buy_ok", things=self._count_of(good, n), total=total,
                           credits=char["credits"])
        if n > to_bag:
            text += " " + self.render(session.lang, "buy_into_hold", things=self._count_of(good, n - to_bag))
        self._send(session, "trade", text=text)

    def cmd_sell(self, session, message):
        char = session.char
        if self._loc(char).get("pawn"):
            self.pawn_sell(session, message)
            return
        lid = char["location"]
        here = self.market_here(char)
        item = self._arg(message, "item", 60)
        text = orbit_safety.name_key(item)
        owned = self.find_owned(char, item) if item else None
        if owned is not None and owned not in self.world.goods and self.pawn_value(owned):
            pawn = next((l for l, loc in self.world.locations.items() if loc.get("pawn")), None)
            self._error(session, "sell_at_pawn", thing=self.world.things[owned]["many"],
                        place=self.world.locations[pawn]["ref"] if pawn else "?")
            return
        what, goods = self.asked_goods(item)
        if here is None or not here["buys"]:
            pointer = self.market_pointer(session, what, goods if item and goods else None, "buys")
            self._error(session, "not_at_market" if here is None else "market_buys_nothing", pointer=pointer)
            return
        buys = here["buys"]
        if message.get("n") == "all" and (not text or any(text in words for words in KIND_WORDS.values())):
            if not goods & buys:
                self._error(session, "market_not_here", what=what,
                            pointer=self.market_pointer(session, what, goods, "buys"))
                return
            self._sell_all(session, goods & buys)
            return
        ship = self.ship_docked_here(char)
        good, n = self._good_and_count(session, message, allow_all=True, high=100000)
        if good is None:
            return
        in_bag = char["inventory"].get(good, 0)
        in_hold = int(ship["cargo"].get(good, 0)) if ship else 0
        have = in_bag + in_hold
        if message.get("n") == "all":
            n = have or None
        if not have:
            self._error(session, "sell_none", thing=self.world.goods[good]["many"])
            return
        if good not in buys:
            self._error(session, "market_doesnt_buy", thing=self.world.goods[good]["many"],
                        pointer=self.market_pointer(session, self.good_word(good), {good}, "buys"))
            return
        if n is None:
            return
        if n > have:
            self._error(session, "not_enough", things=self._count_of(good, have))
            return
        total = self.market_quote(lid, good, char, "sell", n)
        from_bag = min(n, in_bag)
        with self.store.transaction():
            self.earn(char, total, "market")
            if from_bag:
                self._take_away(char, good, from_bag)
            if n > from_bag:
                ship["cargo"][good] = in_hold - (n - from_bag)
                self.store.save_ship(ship)
            self.market.trade(good, "sell", n, self.world.world_of(lid))
            self._save(session)
        self._send(session, "trade", "sell_ok", things=self._count_of(good, n), total=total,
                   credits=char["credits"])

    def _sell_all(self, session, goods):
        """Everything of `goods` in your bag (and your ship's hold, docked on this world), sold here."""
        char = session.char
        lid = char["location"]
        ship = self.ship_docked_here(char)
        hold = ship["cargo"] if ship else {}
        sold, total = [], 0
        with self.store.transaction():
            for gid in sorted(set(char["inventory"]) | set(hold)):
                if gid not in goods:
                    continue
                n = int(char["inventory"].get(gid, 0)) + int(hold.get(gid, 0))
                if n <= 0:
                    continue
                total += self.market_quote(lid, gid, char, "sell", n)
                sold.append(self._count_of(gid, n))
                char["inventory"].pop(gid, None)
                hold.pop(gid, None)
                self.market.trade(gid, "sell", n, self.world.world_of(lid))
            if not sold:
                self._error(session, "sell_all_none")
                return
            self.earn(char, total, "market")
            if ship:
                self.store.save_ship(ship)
            self._save(session)
        self._send(session, "trade", "sell_ok", things=sold, total=total, credits=char["credits"])

    # --- the farm -----------------------------------------------------------------------------

    def plot_count(self, char):
        return int(char["stats"].get("plots") or self.econ["farm"]["plots"])

    def plots(self, char):
        farm = char["stats"].get("farm")
        if not isinstance(farm, list):
            farm = []
        count = self.plot_count(char)
        farm = (farm + [None] * count)[:count]
        char["stats"]["farm"] = farm
        return farm

    def _at_farm(self, session):
        if not self._loc(session.char).get("farm"):
            farm = next(lid for lid, loc in self.world.locations.items() if loc.get("farm"))
            self._error(session, "farm_where", where=self.world.locations[farm]["in"])
            return False
        return True

    def _crop_for(self, text):
        """The crop id a player's words name ("tomat", "bibit tomat")."""
        tid = self.world.find_thing(text)
        if tid is None:
            return None
        for cid, crop in self.world.crops.items():
            if tid in (crop["seed"], crop["good"]):
                return cid
        return None

    def cmd_plant(self, session, message):
        char, lang = session.char, session.lang
        if not self._at_farm(session) or not self._slow(session):
            return
        text = self._arg(message, "item", 60)
        cid = self._crop_for(text) if text else None
        if cid is None:
            seeds = [c for c, crop in self.world.crops.items() if self.owns(char, crop["seed"])]
            if text or len(seeds) != 1:
                self._error(session, "plant_what")
                return
            cid = seeds[0]
        crop = self.world.crops[cid]
        seed = crop["seed"]
        if int(crop.get("level", 1)) > self.job_level(char):
            self._error(session, "need_level", thing=self.world.things[seed]["one"], level=crop["level"])
            return
        have = char["inventory"].get(seed, 0)
        if not have:
            self._error(session, "no_seeds", thing=self.world.things[seed]["many"])
            return
        plots = self.plots(char)
        empty = [i for i, p in enumerate(plots) if p is None]
        if not empty:
            self._error(session, "plots_full")
            return
        wanted = self._count(message, default=len(empty), high=100)
        if wanted is None:
            self._error(session, "bad_number")
            return
        n = min(wanted, have, len(empty))
        fx = self.effects(char)
        grow = float(crop["grow"]) * fx["grow"]
        bonus = int(self.econ["farm"]["water_bonus"]) if fx["sprinkler"] else 0
        for i in empty[:n]:
            plots[i] = {"crop": cid, "ready": self.now() + grow,
                        "yield": self.rng.randint(int(crop["yield"][0]), int(crop["yield"][1])) + bonus,
                        "watered": bool(fx["sprinkler"]), "told": False}
        self._take_away(char, seed, n)
        self._save(session)
        good = self.world.goods[crop["good"]]
        key = "planted_watered" if fx["sprinkler"] else "planted"
        self._send(session, "trade", key, n=n, crop=good["many"], time=self._duration(lang, grow),
                   extra={"sound": "plant"})

    def cmd_water(self, session, message):
        char = session.char
        if not self._at_farm(session) or not self._slow(session):
            return
        now = self.now()
        watered = 0
        for plot in self.plots(char):
            if plot and not plot.get("watered") and float(plot["ready"]) > now:
                plot["watered"] = True
                plot["yield"] = int(plot["yield"]) + int(self.econ["farm"]["water_bonus"])
                watered += 1
        if not watered:
            self._error(session, "water_nothing")
            return
        self._save(session)
        self._send(session, "trade", "watered", n=watered, extra={"sound": "water"})

    def ripe_plots(self, char):
        now = self.now()
        return sum(1 for p in self.plots(char) if p and float(p["ready"]) <= now)

    def cmd_harvest(self, session, message):
        char, lang = session.char, session.lang
        if not self._at_farm(session) or not self._slow(session):
            return
        now = self.now()
        plots = self.plots(char)
        ripe = [i for i, p in enumerate(plots) if p and float(p["ready"]) <= now]
        if not ripe:
            growing = [p for p in plots if p]
            if growing:
                soonest = min(float(p["ready"]) for p in growing)
                self._error(session, "harvest_not_yet", time=self._duration(lang, soonest - now))
            else:
                self._error(session, "harvest_nothing")
            return
        space = self.bag_size(char) - self._goods_count(char)
        if space <= 0:
            self._error(session, "bag_full", max=self.bag_size(char))
            return
        got = {}
        golden = 0
        for i in ripe:
            plot = plots[i]
            crop = self.world.crops.get(plot["crop"])
            if crop is None:
                plots[i] = None
                continue
            n = min(int(plot["yield"]), space)
            if n <= 0:
                break
            got[crop["good"]] = got.get(crop["good"], 0) + n
            space -= n
            plot["yield"] = int(plot["yield"]) - n
            if plot["yield"] <= 0:
                plots[i] = None
                if space > 0 and self.rng.random() < float(self.econ["farm"]["golden_chance"]):
                    golden += 1
                    space -= 1
        if golden:
            got["golden_chilli"] = got.get("golden_chilli", 0) + golden
            char["stats"]["golden"] = int(char["stats"].get("golden") or 0) + golden
        total = sum(got.values())
        for gid, n in got.items():
            self.give_thing(char, gid, n)
        char["harvested"] = int(char.get("harvested") or 0) + total
        self._save(session)
        things = [self._count_of(gid, n) for gid, n in got.items()]
        left = sum(1 for p in plots if p and float(p["ready"]) <= now)
        text = self.render(lang, "harvested", things=things, total=total)
        if left:
            text += " " + self.render(lang, "harvest_left", n=left)
        if golden:
            text += " " + self.render(lang, "harvest_golden")
        self._send(session, "paid", text=text, extra={"sound": "rare" if golden else "harvest"})

    def farm_text(self, session):
        char, lang = session.char, session.lang
        now = self.now()
        entries = []
        for number, plot in enumerate(self.plots(char), 1):
            if plot is None:
                entries.append(self.render(lang, "plot_empty", number=number))
                continue
            crop = self.world.crops.get(plot["crop"])
            name = self.world.goods[crop["good"]]["many"] if crop else "?"
            watered = self.render(lang, "plot_watered") if plot.get("watered") else ""
            if float(plot["ready"]) <= now:
                entries.append(self.render(lang, "plot_ripe", number=number, crop=name))
            else:
                entries.append(self.render(lang, "plot_growing", number=number, crop=name,
                                           time=self._duration(lang, float(plot["ready"]) - now),
                                           watered=watered))
        return self.render(lang, "farm", n=len(entries), plots="; ".join(entries))

    def cmd_farm(self, session, message):
        self._info(session, text=self.farm_text(session))

    def tick_farm(self, session, now):
        if session.conn is None:
            return
        ripe = []
        for plot in self.plots(session.char):
            if plot and not plot.get("told") and float(plot["ready"]) <= now:
                plot["told"] = True
                crop = self.world.crops.get(plot["crop"])
                if crop and crop["good"] not in ripe:
                    ripe.append(crop["good"])
        if ripe:
            self._save(session)
            self._send(session, "mission", "farm_ripe", crops=[self.world.goods[g]["many"] for g in ripe],
                       extra={"sound": "ripe"})

    # --- mining and salvage ---------------------------------------------------------------------

    def _pick(self, table):
        total = sum(table.values())
        roll = self.rng.random() * total
        for gid, weight in table.items():
            roll -= weight
            if roll < 0:
                return gid
        return next(iter(table))

    def cmd_mine(self, session, message):
        char, lang = session.char, session.lang
        spot = self._loc(char).get("mine")
        if not spot:
            belt = next(lid for lid, loc in self.world.locations.items() if loc.get("mine"))
            self._error(session, "mine_where", where=self.world.locations[belt]["ref"])
            return
        if self.in_the_dark(char):
            self._error(session, "too_dark_to_mine")
            return
        mining = self.econ["mining"]
        tier = str(self.effects(char)["drill"])
        if not self._check_cooldown(session, "mine") or not self._slow(session):
            return
        if self._goods_count(char) >= self.bag_size(char):
            self._error(session, "bag_full", max=self.bag_size(char))
            return
        table = mining["tables"][spot].get(tier) or mining["tables"][spot]["1"]
        ore = self._pick(table)
        n = 2 if self.rng.random() < float(mining["vein_chance"]) else 1
        n = min(n, self.bag_size(char) - self._goods_count(char))
        self.give_thing(char, ore, n)
        char["mined"] = int(char.get("mined") or 0) + n
        if ore == "quantum":
            char["stats"]["quantum"] = int(char["stats"].get("quantum") or 0) + n
        self._set_cooldown(char, "mine", float(mining["cooldown"][tier]))
        key_found = self._rare_key(char, float((mining.get("key_chance") or {}).get(spot, 0)))
        self._save(session)
        text = self.render(lang, "mined_vein" if n > 1 else "mined", things=self._count_of(ore, n),
                           time=self._duration(lang, float(mining["cooldown"][tier])))
        if key_found:
            text += " " + self.render(lang, "found_key")
        rare = ore in RARE_ORE or key_found
        self._send(session, "paid", text=text, extra={"sound": "rare" if rare else "mine"})

    def _rare_key(self, char, chance):
        if chance and not self.owns(char, "brass_key") and self.rng.random() < chance:
            self.give_thing(char, "brass_key")
            return True
        return False

    def cmd_collect(self, session, message):
        char, lang = session.char, session.lang
        if self.events_here(char, "collect"):
            self.event_collect(session)
            return
        spot = self._loc(char).get("salvage")
        if not spot:
            self._error(session, "collect_nothing")
            return
        if self.in_the_dark(char):
            self._error(session, "too_dark_to_see")
            return
        salvage = self.econ["salvage"]
        if not self._check_cooldown(session, "salvage") or not self._slow(session):
            return
        if self._goods_count(char) >= self.bag_size(char):
            self._error(session, "bag_full", max=self.bag_size(char))
            return
        thing = self._pick(salvage["tables"][spot])
        self.give_thing(char, thing, 1)
        self._set_cooldown(char, "salvage", float(salvage["cooldown"]))
        key_found = self._rare_key(char, float(salvage.get("key_chance", 0)))
        text = self.render(lang, "salvaged", things=self._count_of(thing, 1),
                           time=self._duration(lang, float(salvage["cooldown"])))
        if key_found:
            text += " " + self.render(lang, "found_key")
        found = self.maybe_find_pet(session, "collect")
        if found:
            text += " " + found
            key_found = True
        self._save(session)
        self._send(session, "paid", text=text,
                   extra={"sound": "rare" if thing in RARE_ORE or key_found else "mine"})

    # --- you -------------------------------------------------------------------------------

    def cmd_profile(self, session, message):
        lang = session.lang
        name = self._arg(message, "to", 40)
        if name and orbit_safety.name_key(name) not in (session.key, "me", "aku", "saya"):
            char = self._char_by_key(orbit_safety.name_key(name))
            other = self.sessions.get(orbit_safety.name_key(name))
            if char is None or (other is not None and other.invisible and not self.is_admin(session)):
                self._error(session, "no_character", name=name)
                return
            parts = [self.render(lang, "profile_other", name=char["name"], rank=self.rank_name(char),
                                 level=self.level_of(int(char.get("xp") or 0)),
                                 mined=char.get("mined", 0), harvested=char.get("harvested", 0))]
            parts.extend(self.appearance(lang, char))
            self._info(session, text=" ".join(parts))
            return
        char = session.char
        xp = int(char.get("xp") or 0)
        known = len([r for r in char["stats"].get("map") or [] if r in self.world.locations])
        total = len([lid for lid, loc in self.world.locations.items() if not loc.get("hidden")])
        parts = [self.render(lang, "profile", name=char["name"], rank=self.rank_name(char),
                             level=self.level_of(xp), xp=xp, credits=char["credits"],
                             streak=char.get("streak", 0), mined=char.get("mined", 0),
                             harvested=char.get("harvested", 0), plots=self.plot_count(char),
                             bag=self.bag_size(char), known=known, total=total)]
        parts.extend(self.appearance(lang, char))
        table = self.econ.get("achievements", {})
        if table:
            have = len([a for a in self.store.achievements_of(char["id"]) if a in table])
            parts.append(self.render(lang, "profile_achievements", n=have, total=len(table)))
        residents = self.npc_friends(lang, char)
        if residents:
            parts.append(residents)
        voice = int(char.get("voice") or 0)
        parts.append(self.render(lang, "profile_voice_n", n=voice) if voice
                     else self.render(lang, "profile_voice_auto"))
        self._info(session, text=" ".join(parts))

    def cmd_voice(self, session, message):
        char = session.char
        text = orbit_safety.name_key(self._arg(message, "a", 20))
        if not text:
            voice = int(char.get("voice") or 0)
            self._info(session, "voice_is_n" if voice else "voice_is_auto", n=voice, max=VOICE_STYLES)
            return
        if text in ("auto", "acak", "otomatis", "random", "0", "default", "biasa"):
            voice = 0
        else:
            try:
                voice = int(text)
            except ValueError:
                voice = -1
            if not 1 <= voice <= VOICE_STYLES:
                self._error(session, "voice_range", max=VOICE_STYLES)
                return
        char["voice"] = voice
        self._save(session)
        extra = {"preview": True, "voice": voice}
        self._send(session, "info", "voice_set_n" if voice else "voice_set_auto", n=voice, extra=extra)
