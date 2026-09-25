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

The Promenade's market buys and sells every good (trade goods, crops, ore,
salvage); prices drift every few minutes back towards each good's usual
price and move a little with every unit traded, so selling a big load at
once pays less per unit. The old miner on the Belt Platform buys ore for
three quarters of the price. Buying costs a fee and selling loses a spread
(less for traders, and less again with a trader's tools), so buying and
selling back at once always loses.

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
LEGAL_KINDS = ("trade", "crop", "ore", "salvage")
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

    # --- the market -----------------------------------------------------------------

    def market_here(self, char):
        """(what it buys, what it sells, the price factor) where you are, or None."""
        market = self._loc(char).get("market")
        if not market:
            return None
        if market is True:
            kinds = set(LEGAL_KINDS)
            return kinds, kinds, 1.0
        return set(market.get("buys", [])), set(market.get("sells", [])), float(market.get("factor", 1.0))

    def fees_for(self, char):
        return self.effects(char)["fees"] or Market.fees(char["job"])

    def _market_where(self, session, side="sells"):
        """Where the nearest market that `side` ("sells" or "buys") is: on this world, else the
        station's Promenade."""
        wid = self.world_here(session.char)
        markets = [lid for lid, loc in self.world.locations.items()
                   if loc.get("market") and self.world.world_of(lid) == wid
                   and (loc["market"] is True or loc["market"].get(side))] if wid else []
        market = markets[0] if markets else next(lid for lid, loc in self.world.locations.items()
                                                 if loc.get("market") is True)
        self._error(session, "market_where", where=self.world.locations[market]["in"])

    def world_market_kinds(self, wid):
        """The kinds of goods a world's markets deal in (buying or selling)."""
        kinds = set()
        for lid, loc in self.world.locations.items():
            market = loc.get("market")
            if not market or self.world.world_of(lid) != wid:
                continue
            if market is True:
                kinds |= set(LEGAL_KINDS)
            else:
                kinds |= set(market.get("buys", [])) | set(market.get("sells", []))
        return kinds

    def cmd_prices(self, session, message):
        char, lang = session.char, session.lang
        fees = self.fees_for(char)
        text = self._arg(message, "a", 40)
        wanted = orbit_safety.name_key(text)
        wid = self.world_here(char) or "station"
        named = self.world.find_world(text) if text and not any(wanted in w for w in KIND_WORDS.values()) else None
        if named and named != wid:
            ship = self.ship_aboard(char)
            if ship is None or not self.ship_spec(ship).get("scanner"):
                self._error(session, "prices_remote", place=self.world.worlds[named]["ref"])
                return
            wid, wanted = named, ""
        here = self.market_here(char) if wid == self.world_here(char) else None
        dealt = (here[0] | here[1]) if here else self.world_market_kinds(wid)
        if not dealt:
            self._error(session, "prices_none_here", place=self.world.worlds[wid]["in"])
            return
        kinds = [k for k, words in KIND_WORDS.items() if wanted in words and k in dealt] or \
            [k for k in KIND_WORDS if k in dealt]
        factor = here[2] if here else 1.0
        groups = []
        for kind in kinds:
            entries = []
            for gid, good in self.world.goods.items():
                if good.get("kind", "trade") != kind:
                    continue
                entries.append(self.render(lang, "price_entry", good=good["one"],
                                           buy=self.market.unit_price(gid, char["job"], "buy", fees, factor, wid),
                                           sell=self.market.unit_price(gid, char["job"], "sell", fees, factor, wid)))
            if entries:
                groups.append(self.render(lang, f"prices_{kind}", entries=", ".join(entries)))
        key = "prices_trader" if char["job"] == "trader" else "prices"
        text = self.render(lang, key, entries="; ".join(groups))
        if wid != "station":
            text = self.render(lang, "prices_world", place=self.world.worlds[wid]["in"]) + " " + text
        self._send(session, "info", text=text)

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
        here = self.market_here(char)
        good = self.world.find_good(text)
        if here is None or good is None or self.world.goods[good].get("kind", "trade") not in here[1]:
            tid = self.world.find_thing(text)
            if tid is not None and tid not in self.world.goods:
                place = self.where_sold(tid)
                if place:
                    self._error(session, "sold_at", thing=self.world.things[tid]["many"],
                                place=self.world.locations[place]["ref"])
                    return
            if here is None or not here[1]:
                self._market_where(session)
                return
            if good is None:
                self._error(session, "no_good", what=text or "?")
                return
            self._error(session, "market_doesnt_sell", thing=self.world.goods[good]["many"])
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
        wid = self.world_here(char)
        total = self.market.quote(good, char["job"], "buy", n, self.fees_for(char), here[2], wid)
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
            self.market.trade(good, "buy", n, wid)
            self._save(session)
        text = self.render(session.lang, "buy_ok", things=self._count_of(good, n), total=total,
                           credits=char["credits"])
        if n > to_bag:
            text += " " + self.render(session.lang, "buy_into_hold", things=self._count_of(good, n - to_bag))
        self._send(session, "trade", text=text)

    def cmd_sell(self, session, message):
        char, lang = session.char, session.lang
        if self._loc(char).get("pawn"):
            self.pawn_sell(session, message)
            return
        here = self.market_here(char)
        if here is None or not here[0]:
            self._market_where(session, "buys")
            return
        buys, _sells, factor = here
        text = orbit_safety.name_key(self._arg(message, "item", 60))
        if message.get("n") == "all" and (not text or any(text in w for w in KIND_WORDS.values())):
            kinds = [k for k, words in KIND_WORDS.items() if text in words] or list(buys)
            self._sell_all(session, [k for k in kinds if k in buys])
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
        if self.world.goods[good].get("kind", "trade") not in buys:
            self._error(session, "market_doesnt_buy", thing=self.world.goods[good]["many"])
            return
        if n is None:
            return
        if n > have:
            self._error(session, "not_enough", things=self._count_of(good, have))
            return
        wid = self.world_here(char)
        total = self.market.quote(good, char["job"], "sell", n, self.fees_for(char), factor, wid)
        from_bag = min(n, in_bag)
        with self.store.transaction():
            self.earn(char, total, "market")
            if from_bag:
                self._take_away(char, good, from_bag)
            if n > from_bag:
                ship["cargo"][good] = in_hold - (n - from_bag)
                self.store.save_ship(ship)
            self.market.trade(good, "sell", n, wid)
            self._save(session)
        self._send(session, "trade", "sell_ok", things=self._count_of(good, n), total=total,
                   credits=char["credits"])

    def _sell_all(self, session, kinds):
        char = session.char
        factor = self.market_here(char)[2]
        wid = self.world_here(char)
        ship = self.ship_docked_here(char)
        hold = ship["cargo"] if ship else {}
        sold, total = [], 0
        with self.store.transaction():
            for gid in sorted(set(char["inventory"]) | set(hold)):
                good = self.world.goods.get(gid)
                if not good or good.get("kind", "trade") not in kinds:
                    continue
                n = int(char["inventory"].get(gid, 0)) + int(hold.get(gid, 0))
                if n <= 0:
                    continue
                price = self.market.quote(gid, char["job"], "sell", n, self.fees_for(char), factor, wid)
                total += price
                sold.append(self._count_of(gid, n))
                char["inventory"].pop(gid, None)
                hold.pop(gid, None)
                self.market.trade(gid, "sell", n, wid)
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
