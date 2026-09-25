# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Things you own, and what they do (economy.json "things"):

  devices    compass, mapper, holo mapper, scanner, headlamp (worn: light in
             the dark), beacon, communicator, keycards (open locked doors),
             EVA suit (worn: vacuum) and oxygen tank (more air)
  tools      drills, the turbo thruster, the auto-sprinkler and grow lamp,
             bigger bags, and each job's tools (more pay, lower fees)
  food       iced coffee (more XP for a while), martabak (a shorter break
             after your next shift), crackers (just crunchy)
  seeds, furniture for your cabin, clothes, rings, titles, and pets

  list / daftar         what the shop you're in sells
  buy X / beli X        buy it (the market's goods too, on the Promenade)
  use X / pakai X       use it: drink, eat, place a beacon, wear...
  wear X / pasang X     wear it (headlamp, EVA suit, clothes, a title)
  take off X / lepas X  stop wearing it
  examine X / periksa X what it is and does

A pet is a companion (a table of its own; orbit_pets.py cares for them).
Things stay in the inventory; seeds,
food, furniture, clothes and a brass key can be given or traded to other
players, the rest can't (the pawn shop buys most of it back).

Shop prices move a little each day (economy.json "prices": up to 10 percent
either way), the same for everyone that day, and one thing in each shop is
today's special, cheaper still. The bar, the seed rack and the lottery
booth keep fixed prices, and so do farm plots.
"""

import hashlib
import logging

import orbit_safety
from orbit_lang import pick

logger = logging.getLogger("orbit.game")

TYPE_GROUPS = {"gear": "devices", "tool": "tools", "seed": "seeds", "furniture": "furniture",
               "outfit": "clothes", "title": "titles", "pet": "pets", "consumable": "food",
               "service": "tools", "ship": "ships", "arcade": "tools"}
GROUP_WORDS = {
    "devices": ("devices", "device", "gadgets", "perangkat", "alat elektronik", "gawai"),
    "tools": ("tools", "tool", "alat", "perkakas", "upgrades"),
    "seeds": ("seeds", "seed", "bibit", "benih"),
    "furniture": ("furniture", "perabot", "perabotan", "mebel", "decor", "dekorasi"),
    "clothes": ("clothes", "outfits", "pakaian", "baju", "busana"),
    "titles": ("titles", "title", "gelar"),
    "pets": ("pets", "pet", "peliharaan", "hewan"),
    "food": ("food", "makanan", "minuman", "snacks", "camilan", "drinks"),
    "ships": ("ships", "ship", "kapal", "pesawat", "spaceships"),
}
LIST_GROUP_LIMIT = 12


class ItemsMixin:
    @staticmethod
    def commands():
        return {"list": ItemsMixin.cmd_list, "use": ItemsMixin.cmd_use,
                "unequip": ItemsMixin.cmd_unequip, "open": ItemsMixin.cmd_open,
                "ring": ItemsMixin.cmd_ring, "lantern": ItemsMixin.cmd_lantern}

    # --- what your things do ------------------------------------------------------------------

    def effects(self, char):
        worn = set((char["stats"].get("worn") or {}).values())
        fx = {"light": False, "eva": False, "owns_eva": False, "air": 0, "mapper": 0,
              "access": set(), "drill": 1, "shuttle": 1.0, "sprinkler": False, "grow": 1.0,
              "bag": int(self.config["max_goods"]), "pay": 0.0, "fees": None, "compass": False,
              "scanner": False, "beacon": False, "comm": False}
        for tid, n in char["inventory"].items():
            thing = self.world.things.get(tid)
            if not n or not thing or thing.get("type") not in ("gear", "tool"):
                continue
            effects = thing.get("effects") or {}
            if thing.get("job") and thing["job"] != char["job"]:
                continue
            active = not thing.get("slot") or tid in worn
            if effects.get("eva"):
                fx["owns_eva"] = True
            if not active:
                continue
            fx["light"] = fx["light"] or bool(effects.get("light"))
            fx["eva"] = fx["eva"] or bool(effects.get("eva"))
            fx["air"] += int(effects.get("air", 0))
            fx["mapper"] = max(fx["mapper"], int(effects.get("mapper", 0)))
            fx["access"].update(effects.get("access", []))
            fx["drill"] = max(fx["drill"], int(effects.get("drill", 1)))
            fx["shuttle"] = min(fx["shuttle"], float(effects.get("shuttle", 1.0)))
            fx["sprinkler"] = fx["sprinkler"] or bool(effects.get("sprinkler"))
            fx["grow"] = min(fx["grow"], float(effects.get("grow", 1.0)))
            fx["bag"] = max(fx["bag"], int(effects.get("bag", 0)))
            fx["pay"] = max(fx["pay"], float(effects.get("pay", 0.0)))
            if effects.get("fees") and (fx["fees"] is None or effects["fees"][0] < fx["fees"][0]):
                fx["fees"] = tuple(effects["fees"])
            for flag in ("compass", "scanner", "beacon", "comm"):
                fx[flag] = fx[flag] or bool(effects.get(flag))
        if not fx["eva"]:
            fx["air"] = 0
        return fx

    def bag_size(self, char):
        return self.effects(char)["bag"]

    def owns(self, char, tid):
        return char["inventory"].get(tid, 0) > 0

    def give_thing(self, char, tid, n=1):
        char["inventory"][tid] = char["inventory"].get(tid, 0) + n

    def give_starter(self, char):
        for tid in self.econ.get("starter", []):
            if tid in self.world.things and not char["stats"].get(f"starter_{tid}"):
                char["stats"][f"starter_{tid}"] = True
                if not self.owns(char, tid):
                    self.give_thing(char, tid)

    def worn(self, char):
        worn = char["stats"].get("worn")
        if not isinstance(worn, dict):
            worn = char["stats"]["worn"] = {}
        return worn

    def worn_list(self, char):
        return [self.world.things[tid]["one"] for tid in self.worn(char).values()
                if tid in self.world.things]

    def appearance(self, lang, char):
        """Lines others see when they look at you: title, clothes, pet."""
        lines = []
        worn = self.worn(char)
        title = self.world.things.get(worn.get("title"), {}).get("effects", {}).get("title")
        if title:
            lines.append(self.render(lang, "look_title", title=title))
        wearing = []
        for slot in ("body", "suit", "head", "hand"):
            thing = self.world.things.get(worn.get(slot))
            if thing:
                wearing.append((thing.get("effects") or {}).get("look") or thing["one"])
        if wearing:
            lines.append(self.render(lang, "look_wearing", things=wearing))
        lines.extend(self.pet_lines(lang, char))
        if hasattr(self, "family_lines"):
            lines.extend(self.family_lines(lang, char))
        crew = self.crew_line(lang, char)
        if crew:
            lines.append(crew)
        return lines

    def cabin_lines(self, session):
        host = self.cabin_host(session)
        if host is None:
            return []
        char = self._char_by_key(host)
        if char is None:
            return []
        lines = []
        for tid in sorted(char["inventory"]):
            thing = self.world.things.get(tid)
            if thing and thing.get("type") == "furniture" and char["inventory"][tid] > 0:
                lines.append(pick(thing["effects"]["cabin"], session.lang))
        for comp in self.pets_of(char):
            lines.append(self.render(session.lang, "cabin_pet", pet=comp["name"]))
        return lines

    # --- shops -------------------------------------------------------------------------------

    def shop_here(self, char):
        sid = self._loc(char).get("shop")
        return sid, self.world.shops.get(sid) if sid else None

    def job_level(self, char):
        return self.level_of(int(char.get("xp") or 0))

    def _day_fraction(self, *parts):
        """A number from 0 to 1, the same all day for the same parts."""
        digest = hashlib.sha256(":".join((self.today(),) + parts).encode("utf-8")).digest()
        return int.from_bytes(digest[:6], "big") / float(1 << 48)

    def _wobbles(self, sid):
        shop = self.world.shops.get(sid) if sid else None
        return bool(shop) and not shop.get("fixed")

    def special_of(self, sid):
        """Today's special in shop `sid` (one of the things whose price moves), or None."""
        if not self._wobbles(sid):
            return None
        stock = [tid for tid in self.world.shops[sid].get("stock", [])
                 if not self.world.things[tid].get("service") and self.world.things[tid].get("price")]
        if not stock:
            return None
        return stock[int(self._day_fraction("special", sid) * len(stock)) % len(stock)]

    def shop_currency(self, sid):
        """The thing a shop takes instead of credits (the Prize Counter: prize tickets), or None."""
        shop = self.world.shops.get(sid) if sid else None
        return shop.get("currency") if shop else None

    def price_of(self, char, tid, sid=None):
        """What `tid` costs `char` (in shop `sid`, today): credits, or the shop's currency."""
        thing = self.world.things[tid]
        if self.shop_currency(sid):
            return int(thing.get("tickets") or 0)
        if thing.get("service") == "plot":
            prices = self.econ["farm"]["plot_prices"]
            bought = max(0, self.plot_count(char) - int(self.econ["farm"]["plots"]))
            return int(prices[min(bought, len(prices) - 1)])
        price = int(thing.get("price") or 0)
        if not price or thing.get("service"):
            return price
        friend = 1.0 - self.npc_discount(char, sid)          # the keeper's friends pay a little less
        if not self._wobbles(sid):
            return max(1, int(round(price * self.shop_discount(sid) * friend))) if sid else price
        rules = self.econ.get("prices", {})
        factor = 1 + float(rules.get("wobble", 0)) * (2 * self._day_fraction(sid, tid) - 1)
        if tid == self.special_of(sid):
            factor -= float(rules.get("special", 0))
        return max(1, int(round(price * factor * self.shop_discount(sid) * friend)))

    def entry_text(self, lang, char, tid, sid=None):
        thing = self.world.things[tid]
        notes = []
        if sid and tid == self.special_of(sid):
            notes.append(self.render(lang, "shop_special"))
        if thing.get("unique") and (self.owns(char, tid) or self._has_pet(char, tid)):
            notes.append(self.render(lang, "shop_owned"))
        elif thing.get("level", 1) > self.job_level(char):
            notes.append(self.render(lang, "shop_level", level=thing["level"]))
        if thing.get("job") and thing["job"] != char["job"]:
            notes.append(self.render(lang, "shop_job", job=self.world.job_name(thing["job"])))
        if thing.get("service") == "plot" and self.plot_count(char) >= int(self.econ["farm"]["max_plots"]):
            notes = [self.render(lang, "shop_max")]
        currency = self.shop_currency(sid)
        if currency:
            return self.render(lang, "shop_entry_in", thing=thing["one"],
                               price=self._count_of(currency, self.price_of(char, tid, sid)), notes="".join(notes))
        return self.render(lang, "shop_entry", thing=thing["one"], price=self.price_of(char, tid, sid),
                           notes="".join(notes))

    def cmd_list(self, session, message):
        char, lang = session.char, session.lang
        sid, shop = self.shop_here(char)
        if shop is None:
            if self._loc(char).get("market"):
                self.cmd_prices(session, {"a": self._arg(message)})
                return
            if self._loc(char).get("pawn"):
                self.pawn_list(session)
                return
            self._error(session, "list_where")
            return
        stock = list(shop.get("stock", []))
        wanted = orbit_safety.name_key(self._arg(message, "a", 40))
        group = next((g for g, words in GROUP_WORDS.items() if wanted in words), None)
        if group:
            stock = [tid for tid in stock if TYPE_GROUPS.get(self.world.things[tid]["type"]) == group]
        elif len(stock) > LIST_GROUP_LIMIT:
            counts = {}
            for tid in stock:
                g = TYPE_GROUPS.get(self.world.things[tid]["type"], "tools")
                counts[g] = counts.get(g, 0) + 1
            groups = [self.render(lang, f"group_{g}", n=n) for g, n in counts.items()]
            self._info(session, "shop_groups", shop=shop["name"], groups=groups)
            return
        if not stock:
            self._error(session, "shop_nothing")
            return
        entries = [self.entry_text(lang, char, tid, sid) for tid in stock]
        currency = self.shop_currency(sid)
        if currency:
            self._info(session, "shop_list_in", shop=shop["name"], entries="; ".join(entries),
                       have=self._count_of(currency, int(char["inventory"].get(currency) or 0)))
            return
        text = self.render(lang, "shop_list", shop=shop["name"], entries="; ".join(entries))
        friend = self.npc_discount(char, sid)
        if friend:
            keeper = next((nid for nid, d in self.npc_defs.items() if d.get("shop") == sid), None)
            text += " " + self.render(lang, "shop_friend_price", name=self.npc_name(keeper) if keeper else "?",
                                      pct=int(round(friend * 100)))
        self._info(session, text=text)

    def where_sold(self, tid):
        for lid, loc in self.world.locations.items():
            sid = loc.get("shop")
            if sid and tid in self.world.shops.get(sid, {}).get("stock", []):
                return lid
        return None

    def buy_thing(self, session, tid, n):
        """Buy `n` of a thing from the shop you're in (buy has found it there)."""
        char, lang = session.char, session.lang
        thing = self.world.things[tid]
        unique = thing.get("unique")
        if unique and n != 1:
            n = 1
        if unique and (self.owns(char, tid) or self._has_pet(char, tid)):
            self._error(session, "already_have", thing=thing["one"])
            return
        if thing.get("level", 1) > self.job_level(char):
            self._error(session, "need_level", thing=thing["one"], level=thing["level"])
            return
        if thing.get("service") == "plot" and self.plot_count(char) >= int(self.econ["farm"]["max_plots"]):
            self._error(session, "plots_max", max=self.econ["farm"]["max_plots"])
            return
        if thing.get("service") == "ticket":
            self.buy_tickets(session, n)
            return
        if thing["type"] == "ship":
            sid, _shop = self.shop_here(char)
            self.buy_ship(session, tid, self.price_of(char, tid, sid))
            return
        sid, _shop = self.shop_here(char)
        total = self.price_of(char, tid, sid) * n
        currency = self.shop_currency(sid)
        if currency:
            self._buy_with(session, tid, n, currency, total)
            return
        if total > char["credits"]:
            self._error(session, "buy_poor", total=total, credits=char["credits"])
            return
        self.spend(char, total, "shops")
        extra = None
        if thing.get("service") == "plot":
            char["stats"]["plots"] = self.plot_count(char) + 1
            key = "bought_plot"
        elif thing["type"] == "pet":
            pet = thing["effects"]["pet"]
            self.store.add_companion(tid, pet.get("name", "Bip"), [char["id"]],
                                     stats=self.new_pet_stats(), state={})
            key = "bought_pet"
        else:
            self.give_thing(char, tid, n)
            key = "bought"
            slot = thing.get("slot")
            if slot and slot != "suit" and not self.worn(char).get(slot):
                self.worn(char)[slot] = tid
                key = "bought_worn"
                extra = {"sound": "equip"}
        self._save(session)
        self._send(session, "trade", key, things=self._count_of(tid, n), thing=thing["one"], total=total,
                   credits=char["credits"], extra=extra)

    def _buy_with(self, session, tid, n, currency, total):
        """Buying with something other than credits (prizes for prize tickets)."""
        char = session.char
        thing = self.world.things[tid]
        have = int(char["inventory"].get(currency) or 0)
        if total > have:
            self._error(session, "buy_short", total=self._count_of(currency, total),
                        have=self._count_of(currency, have))
            return
        self._take_away(char, currency, total)
        self.give_thing(char, tid, n)
        self._save(session)
        logger.info("%s got %s for %s %s", session.name, tid, total, currency)
        self._send(session, "trade", "bought_with", things=self._count_of(tid, n), thing=thing["one"],
                   total=self._count_of(currency, total),
                   left=self._count_of(currency, int(char["inventory"].get(currency) or 0)),
                   extra={"sound": "arcade_ticket"})

    # --- using things ------------------------------------------------------------------------

    def find_owned(self, char, text):
        """The id of a thing you own that `text` names (or a pet's name), or None."""
        tid = self.world.find_thing(text)
        if tid and (self.owns(char, tid) or self._has_pet(char, tid)):
            return tid
        key = orbit_safety.name_key(text)
        for comp in self.store.companions_of(char["id"]):
            if orbit_safety.name_key(comp["name"]) == key:
                return comp["kind"]
        return None

    def _has_pet(self, char, tid):
        return self.world.things.get(tid, {}).get("type") == "pet" and \
            any(c["kind"] == tid for c in self.store.companions_of(char["id"]))

    def examine(self, session, text):
        """Describe a thing you own, or one for sale here. False when there's none."""
        char, lang = session.char, session.lang
        tid = self.find_owned(char, text)
        sid, shop = self.shop_here(char)
        if tid is None and shop is not None:
            found = self.world.find_thing(text)
            if found in shop.get("stock", []):
                tid = found
        if tid is None:
            return False
        thing = self.world.things[tid]
        parts = [pick(thing.get("desc") or thing["one"], lang)]
        if tid in self.worn(char).values():
            parts.append(self.render(lang, "examine_worn"))
        elif self.owns(char, tid) and char["inventory"][tid] > 1:
            parts.append(self.render(lang, "examine_count", n=char["inventory"][tid]))
        if shop is not None and tid in shop.get("stock", []):
            currency = self.shop_currency(sid)
            if currency:
                parts.append(self.render(lang, "examine_price_in",
                                         price=self._count_of(currency, self.price_of(char, tid, sid))))
            else:
                parts.append(self.render(lang, "examine_price", price=self.price_of(char, tid, sid)))
        self._info(session, text=" ".join(parts))
        return True

    def cmd_use(self, session, message):
        char, lang = session.char, session.lang
        text = self._arg(message, "item", 80)
        if not text:
            self._error(session, "use_what")
            return
        tid = self.find_owned(char, text)
        if tid is None:
            found = self.world.find_thing(text)
            if found:
                self._error(session, "dont_have", thing=self.world.things[found]["many"])
            else:
                self._error(session, "no_item", what=text)
            return
        thing = self.world.things[tid]
        effects = thing.get("effects") or {}
        if thing.get("slot"):
            self.wear(session, tid)
        elif effects.get("beacon"):
            self.place_beacon(session)
        elif effects.get("compass"):
            self.cmd_compass(session, {})
        elif effects.get("mapper"):
            self.cmd_map(session, {})
        elif effects.get("scanner"):
            self.cmd_scan(session, {})
        elif effects.get("comm"):
            self.cmd_friends(session, {})
        elif effects.get("pet_food"):
            self.cmd_pet(session, {"op": "feed", "a": text})
        elif thing["type"] == "consumable":
            self.consume(session, tid)
        elif thing["type"] == "seed":
            self._info(session, "use_seed", thing=thing["many"])
        elif thing["type"] == "pet":
            self.cmd_pet(session, {"op": "pat"})
        elif effects.get("access"):
            self._info(session, "use_keycard", thing=thing["one"])
        else:
            self._info(session, "use_passive", thing=thing["one"])

    def wear(self, session, tid):
        char = session.char
        thing = self.world.things[tid]
        worn = self.worn(char)
        slot = thing["slot"]
        if worn.get(slot) == tid:
            self._info(session, "already_worn", thing=thing["one"])
            return
        if slot == "suit" and worn.get("suit") and self._loc(char).get("airless"):
            self._error(session, "not_out_here")
            return
        worn[slot] = tid
        self._save(session)
        self._info(session, "worn", thing=thing["one"], sound="equip")

    def cmd_unequip(self, session, message):
        char = session.char
        text = self._arg(message, "item", 80)
        tid = self.find_owned(char, text) if text else None
        worn = self.worn(char)
        slot = next((s for s, t in worn.items() if t == tid), None)
        if tid is None or slot is None:
            self._error(session, "not_wearing", what=text or "?")
            return
        if slot == "suit" and self._loc(char).get("airless"):
            self._error(session, "not_out_here")
            return
        worn.pop(slot, None)
        self._save(session)
        self._info(session, "unworn", thing=self.world.things[tid]["one"], sound="equip")

    def place_beacon(self, session):
        char = session.char
        here = char["location"]
        if self.world.locations[here].get("hidden") or here == "cabin":
            self._error(session, "beacon_not_here")
            return
        char["stats"]["beacon"] = here
        self._save(session)
        self._info(session, "beacon_placed", place=self.world.locations[here]["in"], sound="gadget")

    def consume(self, session, tid):
        char, lang = session.char, session.lang
        thing = self.world.things[tid]
        effects = thing.get("effects") or {}
        self._take_away(char, tid, 1)
        if effects.get("xp_boost"):
            char["stats"]["xp_boost"] = {"factor": float(effects["xp_boost"]),
                                         "until": self.now() + float(effects.get("seconds", 600))}
            key = "used_coffee"
        elif effects.get("cooldown_cut"):
            char["stats"]["cooldown_cut"] = float(effects["cooldown_cut"])
            key = "used_martabak"
        else:
            key = "used_snack"
        self._save(session)
        self._send(session, "info", key, thing=thing["one"],
                   time=self._duration(lang, float(effects.get("seconds", 600))),
                   extra={"sound": "crunch" if key == "used_snack" else "gulp"})
        if not session.invisible:
            self._to_room(self.room_of(char), "emote", f"{key}_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "crunch" if key == "used_snack" else None},
                          actor=session.name, thing=thing["one"])

    def cmd_open(self, session, message):
        char = session.char
        text = self._arg(message)
        oid, obj = self.world.find_object(char["location"], text)
        if obj is None or not obj.get("capsule"):
            self._error(session, "open_nothing", what=text or "?")
            return
        if self.in_the_dark(char):
            self._error(session, "too_dark_to_see")
            return
        if char["stats"].get("capsule"):
            self._info(session, "capsule_empty")
            return
        credits = int(self.econ.get("capsule", {}).get("credits", 0))
        char["stats"]["capsule"] = True
        self.earn(char, credits, "finds")
        self._save(session)
        self._send(session, "paid", "capsule_opened", pay=credits, credits=char["credits"],
                   extra={"sound": "rare"})

    # --- the temple of the Way of Starlight (flavour, optional) ---------------------------------

    def _at_temple(self, session):
        if not self._loc(session.char).get("temple"):
            temple = next((lid for lid, loc in self.world.locations.items() if loc.get("temple")), None)
            self._error(session, "temple_where",
                        where=self.world.locations[temple]["in"] if temple else "?")
            return False
        return True

    def cmd_ring(self, session, message):
        if not self._at_temple(session):
            return
        temple = self.econ.get("temple", {})
        if self._cooldown_left(session.char, "bell") > 0 or not self._slow(session):
            self._error(session, "bell_wait")
            return
        self._set_cooldown(session.char, "bell", float(temple.get("bell_seconds", 10)))
        self._save(session)
        self._send(session, "emote", "bell_you", extra={"sound": "bell"})
        self._to_room(self.room_of(session.char), "emote", "bell_other", exclude=(session,),
                      extra={"actor": session.name, "sound": "bell"}, actor=session.name)

    def lanterns_today(self):
        state = self.store.get_json("lanterns", {}) or {}
        return int(state.get("count", 0)) if state.get("day") == self.today() else 0

    def cmd_lantern(self, session, message):
        char, lang = session.char, session.lang
        if self.wedding_lantern(session):
            return                              # a lantern in the Starlight rite
        if not self._at_temple(session):
            return
        temple = self.econ.get("temple", {})
        festival = self.lantern_rules() or {}
        price = 0 if festival.get("free") else int(temple.get("lantern_price", 3))
        if self._cooldown_left(char, "lantern") > 0 or not self._slow(session):
            self._error(session, "lantern_wait")
            return
        if char["credits"] < price:
            self._error(session, "buy_poor", total=price, credits=char["credits"])
            return
        if price:
            self.spend(char, price, "lanterns")
        gift = int(festival.get("gift") or 0)
        if gift and not char["stats"].get("festival_gift") == self.today():
            char["stats"]["festival_gift"] = self.today()
            self.earn(char, gift, "events")
            self._send(session, "paid", "lantern_festival_gift", n=gift, extra={"sound": "coins"})
        self._set_cooldown(char, "lantern", float(temple.get("lantern_seconds", 30)))
        count = self.lanterns_today() + 1
        self.store.set_json("lanterns", {"day": self.today(), "count": count})
        self._save(session)
        self._send(session, "emote", "lantern_you", price=price, n=count, credits=char["credits"],
                   extra={"sound": "lantern"})
        self._to_room(self.room_of(char), "emote", "lantern_other", exclude=(session,),
                      extra={"actor": session.name, "sound": "lantern"}, actor=session.name, n=count)
        self.festival_lantern(session)
