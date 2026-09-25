# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What the other worlds have to do besides trading (the Moon's helium tunnels,
Karmina's farming domes and Glasir's ice use "mine" and "collect"):

  face moss sprite / hadapi peri lumut   Evergrove's creatures: a test of
                                         wits, never a fight. A roll of the
                                         die plus half your level against the
                                         creature's difficulty: win, and it
                                         leaves you a moonpetal or an ember
                                         crystal; lose, and it only laughs.
  gig / gig                              Lumina City's Courier Hub: carry a
                                         parcel to the room it names, walking
                                         by compass, before the time is up.

economy.json "creatures", "creature_rules" and "gigs" hold the numbers.
"""

import logging

import orbit_safety
from orbit_lang import pick

logger = logging.getLogger("orbit.game")


class LocalMixin:
    @staticmethod
    def commands():
        return {"face": LocalMixin.cmd_face, "gig": LocalMixin.cmd_gig}

    # --- Evergrove's creatures ------------------------------------------------------------

    def creature_here(self, char, text):
        loc = self._loc(char)
        creatures = self.econ.get("creatures", {})
        here = [cid for cid in loc.get("creatures", []) if cid in creatures]
        if not here:
            return None, here
        if not text:
            return (here[0] if len(here) == 1 else None), here
        key = orbit_safety.name_key(text)
        for cid in here:
            names = creatures[cid]["names"]
            if key in {orbit_safety.name_key(n) for lang in ("en", "id") for n in names[lang]}:
                return cid, here
        return None, here

    def cmd_face(self, session, message):
        char, lang = session.char, session.lang
        creature_id, here = self.creature_here(char, self._arg(message, "a", 40))
        creatures = self.econ.get("creatures", {})
        if not here:
            self._error(session, "face_nothing")
            return
        if creature_id is None:
            self._error(session, "face_which", creatures=[creatures[c]["one"] for c in here])
            return
        if self.in_the_dark(char):
            self._error(session, "too_dark_to_see")
            return
        left = self._cooldown_left(char, "face")
        if left > 0:
            self._error(session, "face_wait", time=self._duration(lang, left))
            return
        if not self._slow(session):
            return
        rules = self.econ.get("creature_rules", {})
        creature = creatures[creature_id]
        roll = self.rng.randint(1, int(rules.get("die", 20)))
        bonus = int(self.level_of(int(char.get("xp") or 0)) * float(rules.get("level_bonus", 0.5)))
        self._set_cooldown(char, "face", float(rules.get("cooldown", 20)))
        won = roll + bonus >= int(creature["difficulty"])
        extra = {"sound": "creature", "outcome": "win" if won else "lose"}
        if not won:
            self._save(session)
            self._send(session, "failed", text=pick(creature["lose"], lang) + " " +
                       self.render(lang, "face_lost", roll=roll, bonus=bonus, need=creature["difficulty"]),
                       extra=extra)
            return
        loot = self._pick(creature["loot"])
        n = int(creature.get("n", 1))
        space = self.bag_size(char) - self._goods_count(char)
        n = min(n, space)
        parts = [pick(creature["win"], lang)]
        if n > 0:
            self.give_thing(char, loot, n)
            parts.append(self.render(lang, "face_won", things=self._count_of(loot, n), roll=roll, bonus=bonus))
        else:
            parts.append(self.render(lang, "face_won_full"))
        char["stats"]["creatures"] = int(char["stats"].get("creatures") or 0) + 1
        found = self.maybe_find_pet(session, "face")
        if found:
            parts.append(found)
        self._save(session)
        self._send(session, "paid", text=" ".join(parts), extra=extra)
        self.award_xp(session, int(creature.get("xp", 5)))

    # --- Lumina City's courier gigs -------------------------------------------------------

    def cmd_gig(self, session, message):
        char, lang = session.char, session.lang
        rules = self.econ.get("gigs", {})
        gig = char["stats"].get("gig")
        if gig:
            self._info(session, "gig_current", place=self.world.locations[gig["to"]]["ref"],
                       time=self._duration(lang, float(gig["until"]) - self.now()), pay=gig["pay"])
            return
        if not self._loc(char).get("gigs"):
            hub = next((lid for lid, loc in self.world.locations.items() if loc.get("gigs")), None)
            self._error(session, "gig_where", where=self.world.locations[hub]["in"] if hub else "?")
            return
        left = self._cooldown_left(char, "gig")
        if left > 0:
            self._error(session, "gig_wait", time=self._duration(lang, left))
            return
        if not self._slow(session):
            return
        choices = [lid for lid in rules.get("to", []) if lid != char["location"]]
        dest = self.rng.choice(choices)
        path = self.world.route(char["location"], dest) or []
        steps = max(1, len(path))
        seconds = float(rules["seconds_base"]) + float(rules["seconds_per_step"]) * steps
        pay = self.pay(char, int(rules["pay"]) + int(rules["pay_per_step"]) * steps)
        pay = int(pay * self.simple_factor("gig_pay"))                  # the night rush
        char["stats"]["gig"] = {"to": dest, "until": self.now() + seconds, "pay": pay}
        self._save(session)
        self._send(session, "task", "gig_taken", place=self.world.locations[dest]["ref"],
                   time=self._duration(lang, seconds), pay=pay, extra={"sound": "task"})

    def gig_arrived(self, session):
        """Called after every move: the parcel delivered when you reach its room."""
        char = session.char
        gig = char["stats"].get("gig")
        if not gig or char["location"] != gig["to"]:
            return
        char["stats"].pop("gig", None)
        rules = self.econ.get("gigs", {})
        self.earn(char, int(gig["pay"]), "gigs")
        char["stats"]["gigs"] = int(char["stats"].get("gigs") or 0) + 1
        self._set_cooldown(char, "gig", float(rules.get("cooldown", 30)))
        self._save(session)
        self._send(session, "paid", "gig_done", pay=gig["pay"], credits=char["credits"],
                   extra={"sound": "success"})
        self.award_xp(session, int(rules.get("xp", 8)))

    def tick_gig(self, session, now):
        gig = session.char["stats"].get("gig")
        if gig and now > float(gig["until"]):
            session.char["stats"].pop("gig", None)
            self._set_cooldown(session.char, "gig", float(self.econ.get("gigs", {}).get("cooldown", 30)))
            self._save(session)
            self._send(session, "failed", "gig_late", place=self.world.locations[gig["to"]]["ref"])
