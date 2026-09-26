# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Things put down in a room (since 1.6), the Nova Realm way:

  drop 2 coffee, put down coffee    on the floor
  put coffee on the table           in or on something that holds things
                                    (world.json: an object's "holds", how many)
  get coffee, take coffee, pick up coffee, get coffee from the table
                                    anyone in the room may pick them up
  throw crackers to Maya            it flies for a few seconds: "catch" grabs it
                                    (anyone in the room; the first wins); nobody
                                    does, and it lands on the floor
  look                              "On the floor: 2 sacks of coffee." and
                                    "On the table: an iced coffee."

Only what may be given away can be put down (goods, food, seeds, furniture,
clothes; not what you wear, devices, keycards, titles, pets or mission
cargo), and never in vacuum or aboard a ship, the ferry or a shuttle. No
litter and no abuse: a room holds at most FLOOR_ROOM things (a pile of the
same thing from the same player is one), a player may have at most
FLOOR_PLAYER piles lying about, and a pile left FLOOR_SECONDS is swept up by
a cleaning drone and given back to whoever put it down (online or not). Goods
on the floor still count in your bag until someone else picks them up, so
dropping is never a way round the bag's size. It's all saved as it changes
(the meta "floor", in the same transaction as the character), so a restart
keeps it: nothing is lost, nothing is made.
"""

import logging

import orbit_safety
import orbit_world
from orbit_lang import pick
from orbit_social import bare

logger = logging.getLogger("orbit.game")

FLOOR_ROOM = 12               # piles in one room, floor and holders together
FLOOR_PLAYER = 6              # piles of one player's lying about the station
FLOOR_SECONDS = 1800          # a pile left this long goes back to whoever put it down
THROW_SECONDS = 5             # how long a thrown thing flies before it lands
FROM_WORDS = ("from", "off", "out of", "on", "in")
PUT_WORDS = ("in", "on", "into", "onto", "inside")
ALL_WORDS = ("all", "everything")


class FloorMixin:
    @staticmethod
    def commands():
        return {"drop": FloorMixin.cmd_drop, "put": FloorMixin.cmd_put, "throw": FloorMixin.cmd_throw,
                "undress": FloorMixin.cmd_undress}

    def init_floor(self):
        stored = self.store.get_json("floor", {}) or {}
        self.floor = {room: [dict(p) for p in piles if isinstance(p, dict) and p.get("id") in self.world.things]
                      for room, piles in stored.items() if isinstance(piles, list)}
        self.airborne = {}            # room -> {"id", "n", "by", "by_name", "to", "lands"}

    # --- what lies where ------------------------------------------------------------------------

    def piles_here(self, room, on=None):
        return [p for p in self.floor.get(room, []) if p.get("on") == on]

    def floor_goods_of(self, char):
        """Goods `char` put down that nobody has picked up: they still take room in the bag."""
        key = char.get("name_key")
        return sum(int(p["n"]) for piles in self.floor.values() for p in piles
                   if p.get("by") == key and p["id"] in self.world.goods)

    def _save_floor(self, *chars):
        with self.store.transaction():
            for char in chars:
                self.store.save(char)
            self.store.set_json("floor", {room: piles for room, piles in self.floor.items() if piles})

    def _holders(self, lid):
        """{object id: object} of the things in this room that hold things."""
        return {oid: obj for oid, obj in (self.world.locations[lid].get("objects") or {}).items()
                if obj.get("holds")}

    def _holder_words(self, obj):
        return pick(obj.get("holds_at") or {"en": f"on the {obj['names']['en'][0]}"})

    def floor_text(self, lang, room):
        """ "On the floor: 2 sacks of coffee." and a line for each holder with something on it."""
        lid = room.split(":", 1)[0]
        lines = []
        floor = self.piles_here(room)
        if floor:
            lines.append(self.render(lang, "floor_lying", things=[self._count_of(p["id"], p["n"]) for p in floor]))
        for oid, obj in self._holders(lid).items():
            piles = self.piles_here(room, oid)
            if piles:
                at = self._holder_words(obj)
                lines.append(self.render(lang, "floor_on", at=at[:1].upper() + at[1:],
                                         things=[self._count_of(p["id"], p["n"]) for p in piles]))
        flying = self.airborne.get(room)
        if flying:
            lines.append(self.render(lang, "floor_flying", thing=self.world.things[flying["id"]]["one"]))
        return "\n".join(lines)

    def _pile_named(self, room, text, on=None, anywhere=False):
        """The pile here that `text` names (on the floor, or on a holder; `anywhere`: either)."""
        piles = [p for p in self.floor.get(room, []) if anywhere or p.get("on") == on]
        if not piles:
            return None
        tid = self.world.find_thing(text)
        found = [p for p in piles if p["id"] == tid]
        if not found:
            index = self.world._index({str(i): self.world.things[p["id"]].get("names") or {}
                                       for i, p in enumerate(piles)},
                                      extra=lambda i: [self.world.things[piles[int(i)]["id"]]["one"]["en"],
                                                       self.world.things[piles[int(i)]["id"]]["many"]["en"]])
            hit = self.world._lookup(index, text)
            found = [piles[int(hit)]] if hit is not None else []
        return found[0] if found else None

    # --- putting things down ---------------------------------------------------------------------

    def _can_put_down_here(self, session):
        loc = self._loc(session.char)
        if session.char["location"] in ("shuttle", "kancil", "ferry", "ship") or loc.get("hidden"):
            self._error(session, "drop_not_aboard")
            return False
        if loc.get("airless"):
            self._error(session, "drop_not_vacuum")
            return False
        return True

    def _what_to_put(self, session, text, default_n=1):
        """(thing id, how many) from "2 coffee", "all coffee", "coffee"; None after saying why not."""
        char = session.char
        words = str(text or "").split()
        n = None
        rest = []
        for word in words:
            low = word.lower().strip(".,!")
            if n is None and low.isdigit():
                n = int(low)
            elif n is None and low in ALL_WORDS:
                n = "all"
            elif low not in ("a", "an", "some", "my", "the"):
                rest.append(word)
        name = " ".join(rest)
        if not name:
            self._error(session, "drop_what")
            return None
        tid = self.find_owned(char, name)
        if tid is None or not self.owns(char, tid):
            found = self.world.find_thing(name)
            if found:
                self._error(session, "dont_have", thing=self.world.things[found]["many"])
            else:
                self._error(session, "no_item", what=name)
            return None
        have = int(char["inventory"].get(tid, 0))
        n = have if n == "all" else (n if n is not None else default_n)
        if n < 1:
            self._error(session, "bad_number")
            return None
        if tid in self.worn(char).values():
            self._error(session, "drop_worn", thing=self.world.things[tid]["one"])
            return None
        if not self._tradeable(tid):
            self._error(session, "drop_cant", thing=self.world.things[tid]["many"])
            return None
        if have < n:
            self._error(session, "not_enough", things=self._count_of(tid, have))
            return None
        return tid, n

    def _room_for_pile(self, session, room, tid, on):
        """Whether one more pile of `tid` fits here, and this player may leave one more."""
        mine = [p for piles in self.floor.values() for p in piles if p.get("by") == session.key]
        same = next((p for p in self.floor.get(room, []) if p["id"] == tid and p.get("by") == session.key
                     and p.get("on") == on), None)
        if same is not None:
            return True
        if len(self.floor.get(room, [])) >= FLOOR_ROOM:
            self._error(session, "drop_room_full")
            return False
        if len(mine) >= FLOOR_PLAYER:
            self._error(session, "drop_too_many", n=FLOOR_PLAYER)
            return False
        return True

    def _lay(self, session, room, tid, n, on=None):
        piles = self.floor.setdefault(room, [])
        same = next((p for p in piles if p["id"] == tid and p.get("by") == session.key and p.get("on") == on), None)
        if same is not None:
            same["n"] = int(same["n"]) + n
            same["at"] = self.now()
        else:
            piles.append({"id": tid, "n": n, "by": session.key, "by_name": session.name, "at": self.now(), "on": on})
        self._take_away(session.char, tid, n)

    def cmd_drop(self, session, message):
        """ "drop 2 coffee", "put down the coffee"."""
        if not self._can_put_down_here(session):
            return
        found = self._what_to_put(session, self._arg(message, "item", 80) or self._arg(message, "a", 80))
        if found is None or not self._slow(session):
            return
        tid, n = found
        room = self.room_of(session.char)
        if not self._room_for_pile(session, room, tid, None):
            return
        self._lay(session, room, tid, n)
        self._save_floor(session.char)
        things = self._count_of(tid, n)
        self._send(session, "info", "drop_you", things=things, extra={"sound": "bump"})
        if not session.invisible:
            self._to_room(room, "emote", "drop_other", exclude=(session,), extra={"actor": session.name,
                                                                                  "sound": "bump"},
                          actor=session.name, things=things)

    def cmd_put(self, session, message):
        """ "put coffee on the table", "put 2 coffee in the crate"; "put coffee" alone: drop it."""
        text = self._arg(message, "a", 120)
        words = text.split()
        low = [w.lower() for w in words]
        at = next((i for i, w in enumerate(low) if w in PUT_WORDS and i > 0), None)
        if at is None:
            if low and low[0] == "down":
                words = words[1:]
            self.cmd_drop(session, {"item": " ".join(words)})
            return
        what, where = " ".join(words[:at]), " ".join(words[at + 1:])
        if not self._can_put_down_here(session):
            return
        oid, obj = self.world.find_object(session.char["location"], where) if where else (None, None)
        if obj is None:
            if orbit_world.strip_articles(where) in ("floor", "ground"):
                self.cmd_drop(session, {"item": what})
                return
            self._error(session, "put_where", what=bare(where) or "?")
            return
        if not obj.get("holds"):
            self._error(session, "put_cant", thing=f"the {obj['names']['en'][0]}")
            return
        found = self._what_to_put(session, what)
        if found is None or not self._slow(session):
            return
        tid, n = found
        room = self.room_of(session.char)
        held = sum(1 for _p in self.piles_here(room, oid))
        if held >= int(obj["holds"]) and not any(p["id"] == tid and p.get("by") == session.key
                                                 for p in self.piles_here(room, oid)):
            self._error(session, "put_full", at=self._holder_words(obj))
            return
        if not self._room_for_pile(session, room, tid, oid):
            return
        self._lay(session, room, tid, n, on=oid)
        self._save_floor(session.char)
        things = self._count_of(tid, n)
        at_words = self._holder_words(obj)
        self._send(session, "info", "put_you", things=things, at=at_words, extra={"sound": "bump"})
        if not session.invisible:
            self._to_room(room, "emote", "put_other", exclude=(session,), extra={"actor": session.name,
                                                                                 "sound": "bump"},
                          actor=session.name, things=things, at=at_words)

    # --- picking things up --------------------------------------------------------------------

    def pick_up(self, session, text, n_wanted=None):
        """ "get coffee", "get 2 coffee from the table": True when `text` named something lying here
        (and it was picked up, or why not was said); False: nothing here by that name."""
        room = self.room_of(session.char)
        if not self.floor.get(room):
            return False
        words = str(text or "").split()
        low = [w.lower() for w in words]
        on = None
        holder = None
        for i, w in enumerate(low):
            if w in ("from", "off") and i > 0:
                where = " ".join(words[i + 1:])
                oid, obj = self.world.find_object(session.char["location"], where)
                if obj is not None and obj.get("holds"):
                    on, holder = oid, obj
                    words = words[:i]
                    break
        n = n_wanted
        rest = []
        for word in words:
            w = word.lower().strip(".,!")
            if n is None and w.isdigit():
                n = int(w)
            elif n is None and w in ALL_WORDS:
                n = "all"
            else:
                rest.append(word)
        name = " ".join(rest)
        if not name:
            return False
        pile = self._pile_named(room, name, on=on, anywhere=holder is None)
        if pile is None:
            return False
        if self.in_the_dark(session.char):
            self._error(session, "too_dark_to_see")
            return True
        if not self._slow(session):
            return True
        tid = pile["id"]
        have = int(pile["n"])
        n = have if n in (None, "all") else max(1, min(int(n), have))      # "get coffee": the whole pile
        char = session.char
        thing = self.world.things[tid]
        mine = pile.get("by") == session.key
        if tid in self.world.goods and not mine and self._goods_count(char) + n > self.bag_size(char):
            self._error(session, "bag_full", max=self.bag_size(char))
            return True
        if thing.get("unique") and self.owns(char, tid):
            self._error(session, "already_have", thing=thing["one"])
            return True
        pile["n"] = have - n
        if pile["n"] <= 0:
            self.floor[room].remove(pile)
        self.give_thing(char, tid, n)
        self._save_floor(char)
        things = self._count_of(tid, n)
        at_words = None
        if pile.get("on"):                       # "on the bar" -> "from the bar"
            at_words = "from " + self._holder_words(self._holders(char["location"])[pile["on"]]).split(" ", 1)[-1]
        self._send(session, "info", "get_you_from" if at_words else "get_you", things=things, at=at_words,
                   extra={"sound": "equip"})
        if not session.invisible:
            self._to_room(room, "emote", "get_other_from" if at_words else "get_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "equip"}, actor=session.name, things=things,
                          at=at_words)
        if not mine:
            logger.info("%s picked up %s %s put down by %s", session.name, n, tid, pile.get("by_name"))
        return True

    # --- throwing and catching --------------------------------------------------------------------

    def cmd_throw(self, session, message):
        """ "throw crackers to Maya": it flies a few seconds; "catch" grabs it."""
        text = self._arg(message, "a", 120)
        words = text.split()
        low = [w.lower() for w in words]
        at = max((i for i, w in enumerate(low) if w in ("to", "at") and i > 0), default=None)
        if at is None or at == len(words) - 1:
            self._error(session, "throw_how")
            return
        name = " ".join(words[at + 1:])
        target = session if orbit_safety.name_key(name) in (session.key, "me", "myself") else \
            self._find_near(session, name)
        if target is None or target is session:
            self._error(session, "throw_self" if target is session else "not_here", name=" ".join(words[at + 1:]))
            return
        if not self._can_put_down_here(session):
            return
        room = self.room_of(session.char)
        if room in self.airborne:
            self._error(session, "throw_busy")
            return
        found = self._what_to_put(session, " ".join(words[:at]))
        if found is None or not self._slow(session):
            return
        tid, _n = found
        self._take_away(session.char, tid, 1)
        self.airborne[room] = {"id": tid, "n": 1, "by": session.key, "by_name": session.name, "to": target.key,
                               "lands": self.now() + THROW_SECONDS}
        self._save(session)
        thing = self.world.things[tid]["one"]
        self._send(session, "info", "throw_you", thing=thing, name=target.name, extra={"sound": "arcade_whoosh"})
        self._send(target, "emote", "throw_them", actor=session.name, thing=thing,
                   extra={"actor": session.name, "sound": "arcade_whoosh"})
        for other in self._in_room(room, exclude=(session, target)):
            self._send(other, "emote", "throw_room", actor=session.name, thing=thing, name=target.name,
                       extra={"actor": session.name, "sound": "arcade_whoosh"})

    def catch_thrown(self, session):
        """ "catch": something flying here is caught. False when nothing flies here."""
        room = self.room_of(session.char)
        flying = self.airborne.get(room)
        if flying is None:
            return False
        char = session.char
        tid = flying["id"]
        thing = self.world.things[tid]
        if tid in self.world.goods and flying["by"] != session.key and \
                self._goods_count(char) + 1 > self.bag_size(char):
            self._error(session, "bag_full", max=self.bag_size(char))
            return True
        self.airborne.pop(room, None)
        self.give_thing(char, tid, 1)
        self._save(session)
        self._send(session, "info", "catch_you", thing=thing["one"], extra={"sound": "equip"})
        if not session.invisible:
            self._to_room(room, "emote", "catch_other", exclude=(session,), extra={"actor": session.name,
                                                                                   "sound": "equip"},
                          actor=session.name, thing=thing["one"])
        return True

    def _land(self, room, flying):
        """Nobody caught it: it lands on the floor, the thrower's pile (or back in their hands)."""
        thrower = self.sessions.get(flying["by"])
        tid = flying["id"]
        piles = self.floor.setdefault(room, [])
        if len(piles) >= FLOOR_ROOM:
            owner = thrower.char if thrower else self.store.by_name(flying["by"])
            if owner is not None:
                self.give_thing(owner, tid, 1)
                self.store.save(owner)
            return
        same = next((p for p in piles if p["id"] == tid and p.get("by") == flying["by"] and not p.get("on")), None)
        if same:
            same["n"] = int(same["n"]) + 1
            same["at"] = self.now()
        else:
            piles.append({"id": tid, "n": 1, "by": flying["by"], "by_name": flying["by_name"], "at": self.now(),
                          "on": None})
        self.store.set_json("floor", {r: p for r, p in self.floor.items() if p})
        for other in self._in_room(room):
            self._send(other, "info", "throw_landed", thing=self.world.things[tid]["one"], extra={"sound": "bump"})

    # --- time passing: landing, and the cleaning drone ------------------------------------------------

    def tick_floor(self, now):
        for room, flying in list(self.airborne.items()):
            if now >= flying["lands"]:
                self.airborne.pop(room, None)
                self._land(room, flying)
        swept = False
        for room, piles in list(self.floor.items()):
            for pile in list(piles):
                if now - float(pile.get("at", now)) < FLOOR_SECONDS:
                    continue
                piles.remove(pile)
                swept = True
                self._give_back(pile)
            if not piles:
                self.floor.pop(room, None)
        if swept:
            self.store.set_json("floor", {r: p for r, p in self.floor.items() if p})

    def _give_back(self, pile):
        owner_session = self.sessions.get(pile.get("by"))
        owner = owner_session.char if owner_session else self.store.by_name(pile.get("by"))
        if owner is None:
            return
        self.give_thing(owner, pile["id"], int(pile["n"]))
        self.store.save(owner)
        if owner_session is not None:
            self._send(owner_session, "received", "floor_swept", things=self._count_of(pile["id"], int(pile["n"])),
                       extra={"sound": "gadget"})

    def forget_airborne(self, session):
        """Leaving the game: a thing you threw that nobody caught comes back to you."""
        for room, flying in list(self.airborne.items()):
            if flying["by"] == session.key:
                self.airborne.pop(room, None)
                self.give_thing(session.char, flying["id"], 1)

    # --- clothes --------------------------------------------------------------------------------------

    def cmd_undress(self, session, message):
        """ "undress": take off your clothes, title and hat (never the suit out in vacuum)."""
        char = session.char
        worn = self.worn(char)
        off = [slot for slot, tid in worn.items() if tid in self.world.things and
               self.world.things[tid].get("type") in ("outfit", "title")]
        if not off:
            self._error(session, "undress_nothing")
            return
        things = [self.world.things[worn[slot]]["one"] for slot in off]
        for slot in off:
            worn.pop(slot, None)
        self._save(session)
        self._info(session, "undressed", things=things, sound="equip")
