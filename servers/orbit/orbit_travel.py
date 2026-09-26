# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Travel between the worlds of the simulation (world.json "worlds"): the
station, the Moon, Karmina, Glasir, the Drift Bazaar, Evergrove, Lumina City,
Pixel Pier and the Asteroid Belt. Three ways, from quick and dear to slow and
cheap (economy.json "travel"):

  gate to Karmina                             the Gate: at once, for a fee
  ferry to Karmina                            the public ferry Starling: it
                                              leaves every two minutes, and
                                              is slow, for a small ticket
  your own ship                               bought at the Shipyard; it docks
                                              in the Hangar (other worlds: at
                                              their port)
    embark (Sam)                              go aboard (a friend's ship, when
                                              invited)
    fly to Karmina                            from aboard: a timed trip, fuel
    disembark                                 step off where it has docked
    refuel (10)                               at a port; each world's price
    load 20 ice, unload                       between your bag and the hold
    cargo, my ship                            the hold, the fuel, where it is
    name ship ...
  worlds                                      where you can go, and the fares

A ship is kept in the database (the ships table): its model, name, where it
is docked or where it's flying, its fuel and its cargo; a flight lands on
time even if its captain has logged out. Customs: arriving on a world that
checks cargo (the station, the Moon, Karmina, Glasir, Lumina City...), a
traveller carrying contraband may be searched: the chance depends on how
they came (the Gate scans everyone, the ferry often, a ship now and then,
less with a Hornbill's scanner bay), and a find is confiscated with a fine.
"""

import logging
import math

import orbit_safety
from orbit_lang import LANGUAGES, pick

logger = logging.getLogger("orbit.game")

GATE_WORDS = ("gate", "the gate", "portal", "the portal", "gate hall")
FERRY_WORDS = ("ferry", "the ferry", "starling", "the starling")
TO_WORDS = ("to", "for", "into")
SHIP_WORDS = {"ship", "my ship", "the ship", "my own ship"}
SHIP_NAME_LIMIT = 24


def _after(text, words):
    """ "the gate to Karmina" -> "Karmina" when `text` starts with one of `words` (else None)."""
    norm = " ".join(str(text or "").split())
    low = norm.lower()
    for word in sorted(words, key=len, reverse=True):
        if low == word:
            return ""
        if low.startswith(word + " "):
            rest = norm[len(word):].strip()
            for to in TO_WORDS:
                if rest.lower().startswith(to + " "):
                    return rest[len(to):].strip()
            return rest
    return None


class TravelMixin:
    @staticmethod
    def commands():
        return {"worlds": TravelMixin.cmd_worlds, "gate": TravelMixin.cmd_gate,
                "ferry": TravelMixin.cmd_ferry, "embark": TravelMixin.cmd_embark,
                "disembark": TravelMixin.cmd_disembark, "fly": TravelMixin.cmd_fly,
                "refuel": TravelMixin.cmd_refuel, "load": TravelMixin.cmd_load,
                "unload": TravelMixin.cmd_unload, "cargo": TravelMixin.cmd_cargo,
                "name_ship": TravelMixin.cmd_name_ship}

    def init_travel(self):
        self.flying = {s["id"]: float(s["flight"].get("arrive", 0)) for s in self.store.flying_ships()}

    @property
    def travel(self):
        return self.econ["travel"]

    # --- where you are ---------------------------------------------------------------------

    def world_here(self, char):
        """The world a character is in (on a ship: where it's docked, or flying from)."""
        loc = char["location"]
        world = self.world.world_of(loc)
        if world:
            return world
        if loc == "ship":
            ship = self.ship_aboard(char)
            if ship:
                return self.ship_world(ship) or ship["flight"].get("from")
        if loc == "ferry":
            return (char["stats"].get("ferry") or {}).get("from")
        return None

    def world_name(self, wid, field="name"):
        return self.world.worlds[wid][field]

    # --- ships --------------------------------------------------------------------------------

    def ship_of(self, char):
        return self.store.ship_of(char["id"]) if char.get("id") is not None else None

    def ship_spec(self, ship):
        return self.world.things[ship["model"]]["effects"]["ship"]

    def ship_world(self, ship):
        return self.world.world_of(ship["dock"]) if ship.get("dock") else None

    def ship_title(self, ship):
        """ "the Swiftlet shuttle Morning Star"."""
        model = self.world.things[ship["model"]]["one"]
        name = ship.get("name") or ""
        return {lang: (f"{model[lang]} {name}".strip()) for lang in LANGUAGES}

    def ship_aboard(self, char):
        """The ship a character is aboard (their own, or the one they visit)."""
        if char["location"] != "ship":
            return None
        host = char["stats"].get("visit")
        if host and host != char["name_key"]:
            owner = self._char_by_key(host)
            return self.store.ship_of(owner["id"]) if owner else None
        return self.ship_of(char)

    def own_ship_aboard(self, session):
        """Your ship when you're aboard it as its captain (else None, and why is said)."""
        char = session.char
        if char["location"] != "ship":
            self._error(session, "not_aboard")
            return None
        host = char["stats"].get("visit")
        if host and host != session.key:
            self._error(session, "not_captain")
            return None
        ship = self.ship_of(char)
        if ship is None:
            self._error(session, "no_ship")
        return ship

    def ship_room(self, owner_key):
        return f"ship:{owner_key}"

    def aboard(self, owner_key):
        return self._in_room(self.ship_room(owner_key))

    def hold_count(self, ship):
        return sum(int(n) for n in (ship.get("cargo") or {}).values())

    def hold_space(self, ship):
        return int(self.ship_spec(ship)["cargo"]) - self.hold_count(ship)

    def ship_docked_here(self, char):
        """Your own ship when it's docked on the world you're on (for buying into its hold)."""
        ship = self.ship_of(char)
        if ship and not ship.get("flight") and self.ship_world(ship) == self.world_here(char):
            return ship
        return None

    def buy_ship(self, session, tid, price):
        """Buying at the Shipyard: a new ship (trading in the old one)."""
        char = session.char
        old = self.ship_of(char)
        credit = 0
        if old is not None:
            if old["model"] == tid:
                self._error(session, "already_have", thing=self.world.things[tid]["one"])
                return
            if old.get("flight"):
                self._error(session, "ship_flying_now")
                return
            if self.hold_count(old):
                self._error(session, "ship_hold_not_empty")
                return
            list_price = int(self.world.things[old["model"]].get("price") or 0)
            credit = int(list_price * float(self.travel["ship"]["trade_in"]))
        cost = price - credit
        if cost > char["credits"]:
            self._error(session, "buy_poor", total=cost, credits=char["credits"])
            return
        spec = self.world.things[tid]["effects"]["ship"]
        port = self.world.worlds["station"]["port"]
        with self.store.transaction():
            if cost >= 0:
                self.spend(char, cost, "ships")
            else:
                self.earn(char, -cost, "trade_ins")
            if old is None:
                ship = self.store.add_ship(char["id"], tid, "", port, spec["tank"])
            else:
                for guest in self.aboard(session.key):
                    self._move_to(guest, old["dock"] or port, message=self._both("ship_replaced_off"))
                ship = dict(old, model=tid, dock=port, fuel=float(spec["tank"]), flight=None)
                self.store.save_ship(ship)
            char["stats"]["ship"] = True
            self._save(session)
        key = "bought_ship_trade_in" if old is not None else "bought_ship"
        self._send(session, "trade", key, thing=self.world.things[tid]["one"], total=price, credit=credit,
                   old=self.world.things[old["model"]]["one"] if old else "", credits=char["credits"],
                   place=self.world.locations[port]["ref"], extra={"sound": "register"})

    def _both(self, key, **params):
        """A line for _move_to (which fills in {place}: braces escaped)."""
        return {lang: self.render(lang, key, **params).replace("{", "{{").replace("}", "}}")
                for lang in LANGUAGES}

    def cmd_embark(self, session, message):
        char = session.char
        if char["location"] in ("ship", "ferry", "shuttle", "kancil"):
            self._error(session, "already_aboard")
            return
        name = self._arg(message, "to", 40)
        if name and orbit_safety.name_key(name) not in (session.key, "my", "ship", "my ship"):
            owner_session = self._find_session(name)
            owner = owner_session.char if owner_session else self._char_by_key(orbit_safety.name_key(name))
            ship = self.store.ship_of(owner["id"]) if owner else None
            if ship is None or ship.get("dock") != char["location"]:
                self._error(session, "their_ship_not_here", name=owner["name"] if owner else name)
                return
            until = owner_session.invites.get(session.key, 0) if owner_session else 0
            if until < self.now():
                self._error(session, "ship_not_invited", name=owner["name"])
                return
            self.guide_stop(session)                         # aboard: travel, not a walk
            self._move_to(session, "ship", host=owner["name_key"],
                          message=self._both("embark_guest", name=owner["name"]), sound="door")
            return
        ship = self.ship_of(char)
        if ship is None:
            self._error(session, "no_ship")
            return
        if ship.get("flight"):
            self._error(session, "ship_flying_away")
            return
        if ship.get("dock") != char["location"]:
            self._error(session, "ship_elsewhere", where=self.world.locations[ship["dock"]]["in"])
            return
        self.guide_stop(session)
        self._move_to(session, "ship", message=self._both("embark_own", ship=self.ship_title(ship)), sound="door")

    def cmd_disembark(self, session, message):
        char = session.char
        if char["location"] == "ferry":
            self.leave_ferry(session)
            return
        if char["location"] != "ship":
            self._error(session, "not_aboard")
            return
        ship = self.ship_aboard(char)
        if ship is None:
            self._move_to(session, self.world.worlds["station"]["port"])
            return
        if ship.get("flight"):
            self._error(session, "still_flying", time=self._duration(session.lang,
                                                                      float(ship["flight"]["arrive"]) - self.now()))
            return
        self._move_to(session, ship["dock"], message=self._both("disembarked"), sound="door")

    def flight_seconds(self, char, ship, distance):
        rules = self.travel["ship"]
        seconds = float(rules["seconds_per"]) * distance / float(self.ship_spec(ship)["speed"])
        if char["job"] == "pilot":
            seconds *= float(rules["pilot_factor"])
        return max(float(rules["min_seconds"]), seconds)

    def fuel_for(self, ship, distance):
        return int(math.ceil(distance * float(self.ship_spec(ship)["burn"]) - 1e-9))

    def target_world(self, text):
        """The world a player names (or the world of a room they name), or None."""
        wid = self.world.find_world(text)
        if wid is None:
            lid = self.world.find_location(text)
            wid = self.world.world_of(lid) if lid else None
        return wid

    def cmd_fly(self, session, message):
        char, lang = session.char, session.lang
        text = self._arg(message, "a", 60)
        dest = self.target_world(text) if text else None
        if char["location"] != "ship":
            ship = self.ship_of(char)
            if dest and ship and ship.get("dock") == char["location"] and not ship.get("flight"):
                self.cmd_embark(session, {})                   # at your ship: aboard, and off you go
                if char["location"] != "ship":
                    return
            else:
                if char["location"] == self.world.jobs["pilot"]["workplace"] and char["job"] == "pilot" and \
                        dest in (None, "moon"):
                    self.run(session, {"c": "work"})           # "fly to the Moon" at the Dock: the cargo run
                elif dest and dest != self.world_here(char):
                    self.travel_options(session, dest)
                else:
                    self._error(session, "fly_where")
                return
        ship = self.own_ship_aboard(session)
        if ship is None:
            return
        if ship.get("flight"):
            left = float(ship["flight"]["arrive"]) - self.now()
            self._error(session, "still_flying", time=self._duration(lang, left))
            return
        if dest is None:
            self._error(session, "fly_where")
            return
        here = self.ship_world(ship)
        if dest == here:
            self._error(session, "fly_already", place=self.world_name(dest, "in"))
            return
        distance = self.world.distance(here, dest)
        fuel = self.fuel_for(ship, distance)
        if float(ship["fuel"]) < fuel:
            self._error(session, "fly_no_fuel", need=fuel, have=int(ship["fuel"]),
                        place=self.world_name(dest, "ref"))
            return
        seconds = self.flight_seconds(char, ship, distance)
        now = self.now()
        ship["fuel"] = float(ship["fuel"]) - fuel
        ship["flight"] = {"from": here, "to": dest, "depart": now, "arrive": now + seconds}
        ship["dock"] = ""
        self.store.save_ship(ship)
        self.flying[ship["id"]] = now + seconds
        port = self.world.worlds[here]["port"]
        if not session.invisible:
            self._to_room(port, "info", "ship_departs_other", extra={"sound": "launch"}, actor=session.name,
                          ship=self.ship_title(ship))
        for person in self.aboard(session.key):
            self._send(person, "flight", "ship_takeoff", place=self.world_name(dest, "ref"),
                       time=self._duration(person.lang, seconds), fuel=fuel, left=int(ship["fuel"]),
                       extra={"sound": "launch"})
        logger.info("%s flies to %s", session.name, dest)

    def tick_ships(self, now):
        for ship_id, arrive in list(self.flying.items()):
            if now >= arrive:
                self.flying.pop(ship_id, None)
                ship = self.store.ship_by_id(ship_id)
                if ship and ship.get("flight"):
                    self.land_ship(ship)

    def land_ship(self, ship):
        dest = ship["flight"].get("to")
        if dest not in self.world.worlds:
            dest = "station"
        ship["dock"] = self.world.worlds[dest]["port"]
        ship["flight"] = None
        self.store.save_ship(ship)
        owner = self.store.by_id(ship["owner"])
        if owner is None:
            return
        port = self.world.locations[ship["dock"]]
        for person in self.aboard(owner["name_key"]):
            self._send(person, "flight", "ship_landed", place=port["ref"], extra=dict(self._where(person),
                                                                                     sound="landing"))
            self.customs(person, "ship", dest, ship if person.key == owner["name_key"] else None)
        logger.info("%s's ship landed at %s", owner["name"], dest)

    def cmd_refuel(self, session, message):
        char = session.char
        ship = self.ship_of(char)
        if ship is None:
            self._error(session, "no_ship")
            return
        if ship.get("flight"):
            self._error(session, "ship_flying_now")
            return
        aboard_own = char["location"] == "ship" and not char["stats"].get("visit")
        if not aboard_own and ship.get("dock") != char["location"]:
            self._error(session, "refuel_where", where=self.world.locations[ship["dock"]]["in"])
            return
        tank = float(self.ship_spec(ship)["tank"])
        room = int(math.floor(tank - float(ship["fuel"]) + 1e-9))
        if room <= 0:
            self._error(session, "refuel_full", tank=int(tank))
            return
        n = self._count(message, default=room, high=100000)
        if n is None:
            self._error(session, "bad_number")
            return
        n = min(n, room)
        price = int(self.world.worlds[self.ship_world(ship)]["fuel"])
        if n * price > char["credits"]:
            n = char["credits"] // price
            if n <= 0:
                self._error(session, "refuel_poor", price=price, credits=char["credits"])
                return
        with self.store.transaction():
            self.spend(char, n * price, "fuel")
            ship["fuel"] = float(ship["fuel"]) + n
            self.store.save_ship(ship)
            self._save(session)
        self._send(session, "trade", "refueled", n=n, total=n * price, fuel=int(ship["fuel"]), tank=int(tank),
                   credits=char["credits"], extra={"sound": "refuel"})

    def _goods_arg(self, session, message):
        text = self._arg(message, "item", 60)
        gid = self.world.find_good(text) if text else None
        if gid is None:
            self._error(session, "no_good", what=text or "?")
        return gid

    def cmd_load(self, session, message):
        ship = self.own_ship_aboard(session)
        if ship is None:
            return
        char = session.char
        if message.get("n") == "all" and not self._arg(message, "item"):
            goods = {g: n for g, n in char["inventory"].items() if g in self.world.goods and n > 0}
        else:
            gid = self._goods_arg(session, message)
            if gid is None:
                return
            have = char["inventory"].get(gid, 0)
            n = have if message.get("n") == "all" else self._count(message, high=100000)
            if n is None or not have or n > have:
                self._error(session, "not_enough", things=self._count_of(gid, have))
                return
            goods = {gid: n}
        space = self.hold_space(ship)
        moved = []
        for gid, n in goods.items():
            n = min(n, space)
            if n <= 0:
                break
            self._take_away(char, gid, n)
            ship["cargo"][gid] = int(ship["cargo"].get(gid, 0)) + n
            space -= n
            moved.append(self._count_of(gid, n))
        if not moved:
            self._error(session, "hold_full", max=self.ship_spec(ship)["cargo"])
            return
        with self.store.transaction():
            self.store.save_ship(ship)
            self._save(session)
        self._send(session, "info", "loaded", things=moved, n=self.hold_count(ship),
                   max=self.ship_spec(ship)["cargo"], extra={"sound": "cargo"})

    def cmd_unload(self, session, message):
        ship = self.own_ship_aboard(session)
        if ship is None:
            return
        char = session.char
        cargo = ship["cargo"]
        if message.get("n") == "all" and not self._arg(message, "item"):
            goods = dict(cargo)
        else:
            gid = self._goods_arg(session, message)
            if gid is None:
                return
            have = int(cargo.get(gid, 0))
            n = have if message.get("n") == "all" else self._count(message, high=100000)
            if n is None or not have or n > have:
                self._error(session, "hold_not_enough", things=self._count_of(gid, have))
                return
            goods = {gid: n}
        space = self.bag_size(char) - self._goods_count(char)
        moved = []
        for gid, n in goods.items():
            n = min(int(n), space)
            if n <= 0:
                break
            cargo[gid] = int(cargo.get(gid, 0)) - n
            if cargo[gid] <= 0:
                cargo.pop(gid, None)
            self.give_thing(char, gid, n)
            space -= n
            moved.append(self._count_of(gid, n))
        if not moved:
            self._error(session, "bag_full", max=self.bag_size(char))
            return
        with self.store.transaction():
            self.store.save_ship(ship)
            self._save(session)
        self._send(session, "info", "unloaded", things=moved, n=self._goods_count(char), max=self.bag_size(char),
                   extra={"sound": "cargo"})

    def ship_status(self, lang, ship):
        spec = self.ship_spec(ship)
        if ship.get("flight"):
            where = self.render(lang, "ship_where_flying", place=self.world_name(ship["flight"]["to"], "ref"),
                                time=self._duration(lang, float(ship["flight"]["arrive"]) - self.now()))
        else:
            where = self.render(lang, "ship_where_docked", place=self.world.locations[ship["dock"]]["in"])
        cargo = [self._count_of(g, n) for g, n in sorted((ship.get("cargo") or {}).items()) if n > 0]
        return self.render(lang, "ship_status", ship=self.ship_title(ship), where=where,
                           fuel=int(ship["fuel"]), tank=int(spec["tank"]), n=self.hold_count(ship),
                           max=int(spec["cargo"]),
                           cargo=cargo or self.render(lang, "hold_empty"))

    def cmd_cargo(self, session, message):
        ship = self.ship_aboard(session.char) or self.ship_of(session.char)
        if ship is None:
            self._error(session, "no_ship")
            return
        self._info(session, text=self.ship_status(session.lang, ship))

    def cmd_name_ship(self, session, message):
        ship = self.ship_of(session.char)
        if ship is None:
            self._error(session, "no_ship")
            return
        if self._muted(session):
            return
        name = orbit_safety.tidy(self._arg(message, "a", 60), SHIP_NAME_LIMIT)
        if not name:
            self._error(session, "name_ship_how")
            return
        ship["name"] = self.filter.clean(name)
        self.store.save_ship(ship)
        self._info(session, "ship_named", ship=self.ship_title(ship))

    def ship_look(self, session):
        """What you see aboard a ship."""
        lang, char = session.lang, session.char
        ship = self.ship_aboard(char)
        if ship is None:
            return pick(self._loc(char)["desc"], lang)
        host = char["stats"].get("visit")
        owner = self.store.by_id(ship["owner"])
        whose = self.render(lang, "ship_yours") if not host or host == session.key else \
            self.render(lang, "ship_theirs", name=owner["name"] if owner else "?")
        parts = [self.render(lang, "ship_look", ship=self.ship_title(ship), whose=whose),
                 pick(self._loc(char)["desc"], lang), self.ship_status(lang, ship)]
        others = self._in_room(self.room_of(char), exclude=(session,), visible=True)
        if others:
            parts.append(self.render(lang, "look_people",
                                     people=[self._person(lang, o) for o in sorted(others, key=lambda o: o.key)]))
        parts.append(self.render(lang, "ship_hint" if ship.get("flight") else "ship_hint_docked"))
        return "\n".join(parts)

    # --- the ferry ------------------------------------------------------------------------------

    def ferry_fare(self, a, b):
        rules = self.travel["ferry"]
        return int(rules["ticket_base"]) + int(rules["ticket_per"]) * self.world.distance(a, b)

    def ferry_seconds(self, a, b):
        rules = self.travel["ferry"]
        return max(float(rules["min_seconds"]), float(rules["seconds_per"]) * self.world.distance(a, b))

    def next_ferry(self, now):
        rules = self.travel["ferry"]
        every = float(rules["every"])
        return math.ceil((now + float(rules["board_before"])) / every) * every

    def ferry_here(self, char):
        """The world whose ferry stop `char` stands at (the ferry leaves from here), or None."""
        here = self.world.world_of(char["location"])
        if here is None or self.world.worlds[here].get("ferry") != char["location"]:
            return None
        return here

    def gate_here(self, char):
        """The world whose Gate `char` stands at, or None."""
        here = self.world.world_of(char["location"])
        if here is None or self.world.worlds[here].get("gate") != char["location"]:
            return None
        return here

    def ship_docked_at(self, char):
        """Your own ship when it's docked in the room you stand in (embark, refuel), or None."""
        ship = self.ship_of(char)
        if ship is None or ship.get("flight") or ship.get("dock") != char["location"]:
            return None
        return ship

    def cmd_ferry(self, session, message):
        char, lang = session.char, session.lang
        here = self.world.world_of(char["location"])
        if char["location"] == "ferry":
            self._error(session, "already_aboard")
            return
        text = self._arg(message, "a", 60)
        dest = self.target_world(text) if text else None
        if self.ferry_here(char) is None:
            stop = self.world.worlds.get(here, {}).get("ferry") if here else None
            if stop:
                self._error(session, "ferry_where", where=self.world.locations[stop]["in"])
            else:
                self._error(session, "ferry_none_here")
            return
        if dest is None or not self.world.worlds[dest].get("ferry"):
            self._error(session, "ferry_to_where", worlds=self.ferry_worlds(lang, here))
            return
        if dest == here:
            self._error(session, "fly_already", place=self.world_name(dest, "in"))
            return
        fare = self.ferry_fare(here, dest)
        if fare > char["credits"]:
            self._error(session, "board_poor", fare=fare, credits=char["credits"])
            return
        now = self.now()
        depart = self.next_ferry(now)
        arrive = depart + self.ferry_seconds(here, dest)
        self.spend(char, fare, "fares")
        char["stats"]["ferry"] = {"from": here, "to": dest, "depart": depart, "arrive": arrive}
        self.guide_stop(session)
        self._move_to(session, "ferry", message=self._both("ferry_boarded", fare=fare), sound="ferry")
        self._send(session, "info", "ferry_times", place=self.world_name(dest, "ref"),
                   wait=self._duration(lang, depart - now), time=self._duration(lang, arrive - depart))

    def ferry_worlds(self, lang, here):
        return [self.render(lang, "ferry_entry", place=self.world_name(w, "name"), fare=self.ferry_fare(here, w))
                for w, wd in self.world.worlds.items() if w != here and wd.get("ferry")]

    def leave_ferry(self, session):
        trip = session.char["stats"].get("ferry") or {}
        if self.now() >= float(trip.get("depart", 0)):
            self._error(session, "ferry_under_way")
            return
        origin = self.world.worlds.get(trip.get("from") or "station", {}).get("ferry") or "dock"
        session.char["stats"].pop("ferry", None)
        self._move_to(session, origin, message=self._both("ferry_left"))

    def tick_ferry(self, session, now):
        trip = session.char["stats"].get("ferry")
        if not trip or session.char["location"] != "ferry":
            return
        if not trip.get("said_depart") and now >= float(trip["depart"]):
            trip["said_depart"] = True
            self._send(session, "flight", "ferry_departs", place=self.world_name(trip["to"], "ref"),
                       time=self._duration(session.lang, float(trip["arrive"]) - now), extra={"sound": "launch"})
        if now >= float(trip["arrive"]):
            self.settle_ferry(session)

    def settle_ferry(self, session, on_join=False):
        char = session.char
        trip = char["stats"].get("ferry")
        if not trip:
            if char["location"] == "ferry":
                char["location"] = self.world.worlds["station"]["ferry"]
            return ""
        if self.now() < float(trip.get("arrive", 0)):
            return ""
        dest = trip.get("to") if trip.get("to") in self.world.worlds else "station"
        room = self.world.worlds[dest].get("ferry") or self.world.worlds[dest]["port"]
        char["stats"].pop("ferry", None)
        if on_join:
            char["location"] = room
            self._remember_room(char, room)
            return self.render(session.lang, "ferry_arrived_away", place=self.world.locations[room]["ref"])
        self._move_to(session, room, message=self._both("ferry_arrived"), sound="landing")
        self.customs(session, "ferry", dest)
        return ""

    # --- the Gate -----------------------------------------------------------------------------

    def gate_fee(self, a, b):
        rules = self.travel["gate"]
        return int(rules["fee_base"]) + int(rules["fee_per"]) * self.world.distance(a, b)

    def cmd_gate(self, session, message):
        char, lang = session.char, session.lang
        here = self.world.world_of(char["location"])
        text = self._arg(message, "a", 60)
        dest = self.target_world(text) if text else None
        gate = self.world.worlds.get(here, {}).get("gate") if here else None
        if self.gate_here(char) is None:
            if gate:
                self._error(session, "gate_where", where=self.world.locations[gate]["in"])
            else:
                self._error(session, "gate_none_here")
            return
        if dest is None or not self.world.worlds[dest].get("gate"):
            self._error(session, "gate_to_where", worlds=self.gate_worlds(lang, here))
            return
        if dest == here:
            self._error(session, "fly_already", place=self.world_name(dest, "in"))
            return
        fee = self.gate_fee(here, dest)
        if fee > char["credits"]:
            self._error(session, "gate_poor", fee=fee, credits=char["credits"])
            return
        if not self._slow(session):
            return
        self.spend(char, fee, "gate")
        self.guide_stop(session)
        target = self.world.worlds[dest]["gate"]
        if not session.invisible:
            self._to_room(self.room_of(char), "leave", "gate_leave_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "gate"}, actor=session.name,
                          place=self.world_name(dest, "ref"))
        self._move_to(session, target, message=self._both("gate_arrived", fee=fee), sound="gate", quiet=True)
        if not session.invisible:
            self._to_room(self.room_of(char), "arrive", "gate_arrive_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "gate"}, actor=session.name)
        self.customs(session, "gate", dest)

    def gate_worlds(self, lang, here):
        return [self.render(lang, "ferry_entry", place=self.world_name(w, "name"), fare=self.gate_fee(here, w))
                for w, wd in self.world.worlds.items() if w != here and wd.get("gate")]

    # --- customs ---------------------------------------------------------------------------------

    def contraband_of(self, inventory):
        return {g: int(n) for g, n in (inventory or {}).items()
                if int(n) > 0 and self.world.goods.get(g, {}).get("kind") == "contraband"}

    def customs(self, session, way, wid, ship=None):
        """A traveller arrives on `wid` by `way` ("gate", "ferry", "ship"): maybe a search."""
        char = session.char
        found = self.contraband_of(char["inventory"])
        in_hold = self.contraband_of(ship.get("cargo")) if ship else {}
        if not found and not in_hold:
            return
        rules = self.travel["customs"]
        chance = float(rules.get(way, 0)) * float(self.world.worlds[wid].get("customs", 0))
        if ship and self.ship_spec(ship).get("scanner"):
            chance *= float(rules["scanner_factor"])
        if chance <= 0 or self.rng.random() >= chance:
            if chance > 0:
                self._send(session, "info", "customs_passed", extra={"sound": "customs"})
            return
        seized = dict(found)
        for gid, n in in_hold.items():
            seized[gid] = seized.get(gid, 0) + n
        value = sum(int(self.world.goods[g]["base"]) * n for g, n in seized.items())
        fine = min(int(char["credits"]), int(value * float(rules["fine"])))
        with self.store.transaction():
            for gid, n in found.items():
                self._take_away(char, gid, n)
            if ship:
                for gid in in_hold:
                    ship["cargo"].pop(gid, None)
                self.store.save_ship(ship)
            if fine:
                self.spend(char, fine, "fines")
            self._save(session)
        logger.info("customs took %s from %s on %s", seized, session.name, wid)
        self._send(session, "failed", "customs_caught", things=[self._count_of(g, n) for g, n in seized.items()],
                   fine=fine, credits=char["credits"], extra={"sound": "customs"})

    # --- how to get there -------------------------------------------------------------------------

    def travel_options(self, session, dest, room=None):
        """How to reach world `dest` (and then `room` in it) from where you are."""
        char, lang = session.char, session.lang
        here = self.world_here(char) or "station"
        info = self.world.worlds[dest]
        ways = []
        mine = self.world.worlds.get(here, {})
        if mine.get("gate") and info.get("gate"):
            ways.append(self.render(lang, "way_gate", where=self.world.locations[mine["gate"]]["in"],
                                    fee=self.gate_fee(here, dest)))
        if mine.get("ferry") and info.get("ferry"):
            ways.append(self.render(lang, "way_ferry", where=self.world.locations[mine["ferry"]]["in"],
                                    fare=self.ferry_fare(here, dest),
                                    time=self._duration(lang, self.ferry_seconds(here, dest))))
        ship = self.ship_of(char)
        if ship is not None:
            distance = self.world.distance(self.ship_world(ship) or here, dest)
            where = self.world.locations[ship["dock"]]["in"] if ship.get("dock") else \
                self.render(lang, "ship_in_flight")
            ways.append(self.render(lang, "way_ship", where=where, fuel=self.fuel_for(ship, distance)))
        else:
            ways.append(self.render(lang, "way_no_ship"))
        text = self.render(lang, "travel_options", place=info["ref"], dist=self.world.distance(here, dest),
                           ways=ways)
        if room and room != info.get("port"):
            start = info.get("gate") or info["port"]
            path = self.world.route(start, room)
            if path:
                text += " " + self.render(lang, "travel_then", place=self.world.locations[start]["ref"],
                                          steps=self.steps_text(lang, path),
                                          target=self.world.locations[room]["ref"])
        self._info(session, text=text)

    def cmd_worlds(self, session, message):
        char, lang = session.char, session.lang
        here = self.world_here(char) or "station"
        entries = []
        for wid, info in self.world.worlds.items():
            if wid == here:
                continue
            fares = []
            if info.get("gate") and self.world.worlds[here].get("gate"):
                fares.append(self.render(lang, "worlds_gate", fee=self.gate_fee(here, wid)))
            if info.get("ferry") and self.world.worlds[here].get("ferry"):
                fares.append(self.render(lang, "worlds_ferry", fare=self.ferry_fare(here, wid)))
            entries.append(self.render(lang, "worlds_entry", place=info["name"], about=info["about"],
                                       dist=self.world.distance(here, wid), fares=fares))
        self._info(session, "worlds", here=self.world_name(here, "in"), entries="\n".join(entries))

    def go_travel(self, session, text):
        """ "go to Karmina", "the gate to the Moon", "ferry to Glasir" through cmd_go
        (Orbit 1.0 sends those as go). True when handled."""
        for words, command in ((GATE_WORDS, "gate"), (FERRY_WORDS, "ferry")):
            rest = _after(text, words)
            if rest is not None:
                self.run(session, {"c": command, "a": rest})
                return True
        char = session.char
        if orbit_safety.name_key(text) in SHIP_WORDS:
            self.run(session, {"c": "embark"})
            return True
        lid = self.find_place(session, text)
        wid = self.world.find_world(text)
        here = self.world_here(char)
        if lid and lid != "?beacon" and self.world.world_of(lid):
            if self.world.world_of(lid) == here or self.world.route(char["location"], lid) is not None:
                return False
            wid = self.world.world_of(lid)
        if wid is None or wid == here:
            return False
        ship = self.ship_aboard(char)
        if ship is not None and char["location"] == "ship" and not char["stats"].get("visit"):
            self.run(session, {"c": "fly", "a": text})
            return True
        self.travel_options(session, wid, lid)
        return True

    # --- joining again ---------------------------------------------------------------------------

    def settle_travel(self, session):
        """Coming back: off a ferry that has arrived, off a friend's ship."""
        char = session.char
        note = ""
        if char["location"] == "ferry":
            note = self.settle_ferry(session, on_join=True)
        elif char["location"] == "ship":
            host = char["stats"].get("visit")
            if host and host != char["name_key"]:
                ship = self.ship_aboard(char)
                if ship is None:
                    char["location"] = self.world.worlds["station"]["port"]
                elif ship.get("flight"):
                    char["location"] = self.world.worlds[ship["flight"]["to"]]["port"]
                else:
                    char["location"] = ship["dock"]
                char["stats"].pop("visit", None)
            elif self.ship_of(char) is None:
                char["location"] = self.world.worlds["station"]["port"]
        return note
