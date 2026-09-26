# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Small pastimes (since 1.6), with the economy's numbers in economy.json:

  jukebox, jukebox 3, pick song Moonlight Swing
        the Cantina's jukebox: the songs, and a coin (jukebox.price) plays
        one for the whole room; the room's own lines mention it afterwards.
        One song a room every jukebox.gap seconds.
  fish, cast a line; reel
        the pond in Willow Nook, north of the Sky Park: cast, wait for a
        tug (fishing.wait seconds), then reel within fishing.window seconds.
        A perch, a carp or a trout goes in your bag (goods of the kind
        "fish", sold at the Spice Market); a golden koi is let go, for XP.
        At most fishing.daily fish a day, so it's a pastime, not a mine
        (tests/test_orbit_social.py checks it earns less than mining).
        Walking away ends it; it lives in the session.
"""

import orbit_safety
from orbit_lang import pick


class PastimesMixin:
    @staticmethod
    def commands():
        return {"jukebox": PastimesMixin.cmd_jukebox, "fish": PastimesMixin.cmd_fish,
                "reel": PastimesMixin.cmd_reel}

    def init_pastimes(self):
        self.jukebox_now = {}           # room -> (song index, when it started)

    # --- the jukebox -------------------------------------------------------------------------------

    def jukebox_rules(self):
        return self.econ.get("jukebox") or {}

    def jukebox_here(self, char):
        return any(obj.get("jukebox") for obj in (self._loc(char).get("objects") or {}).values())

    def jukebox_song(self, room):
        """The song playing in `room` (for its own lines and a look at the jukebox), or None."""
        now = self.jukebox_now.get(room)
        songs = self.jukebox_rules().get("songs") or []
        if now is None or not songs:
            return None
        return songs[now[0] % len(songs)]

    def cmd_jukebox(self, session, message):
        char, lang = session.char, session.lang
        rules = self.jukebox_rules()
        songs = rules.get("songs") or []
        if not self.jukebox_here(char) or not songs:
            where = next((lid for lid, loc in self.world.locations.items()
                          if any(o.get("jukebox") for o in (loc.get("objects") or {}).values())), None)
            self._error(session, "jukebox_where", where=self.world.locations[where]["in"] if where else "?")
            return
        wanted = self._arg(message, "a", 60)
        key = orbit_safety.name_key(wanted)
        price = int(rules.get("price", 2))
        if not key or key in ("list", "songs", "menu"):
            entries = [self.render(lang, "jukebox_entry", n=i + 1, song=song["name"]) for i, song in enumerate(songs)]
            playing = self.jukebox_song(self.room_of(char))
            text = self.render(lang, "jukebox_list", price=price, songs="\n".join(entries))
            if playing:
                text += "\n" + self.render(lang, "jukebox_playing", song=playing["name"])
            self._info(session, text=text)
            return
        index = None
        if key.isdigit() and 1 <= int(key) <= len(songs):
            index = int(key) - 1
        else:
            for i, song in enumerate(songs):
                names = [orbit_safety.name_key(n) for n in [pick(song["name"])] + list(song.get("words") or [])]
                if key in names or any(n.startswith(key) for n in names if len(key) >= 4):
                    index = i
                    break
        if index is None:
            self._error(session, "jukebox_unknown", what=wanted, n=len(songs))
            return
        room = self.room_of(char)
        started = self.jukebox_now.get(room)
        gap = float(rules.get("gap", 60))
        if started and self.now() - started[1] < gap:
            self._error(session, "jukebox_busy", song=songs[started[0]]["name"],
                        time=self._duration(lang, gap - (self.now() - started[1])))
            return
        if char["credits"] < price:
            self._error(session, "buy_poor", total=price, credits=char["credits"])
            return
        if not self._slow(session):
            return
        self.spend(char, price, "shops")
        self._save(session)
        self.jukebox_now[room] = (index, self.now())
        self.note_room_chat(session)
        song = songs[index]
        self._send(session, "paid", "jukebox_you", song=song["name"], line=song["line"], price=price,
                   credits=char["credits"], extra={"sound": "coins"})
        if not session.invisible:
            self._to_room(room, "emote", "jukebox_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "coins"}, actor=session.name, song=song["name"],
                          line=song["line"])

    # --- the fishing pond ----------------------------------------------------------------------------

    def fishing_rules(self):
        return self.econ.get("fishing") or {}

    def fish_here(self, char):
        return any(obj.get("fishing") for obj in (self._loc(char).get("objects") or {}).values())

    def _fish_today(self, char):
        day, n = (char["stats"].get("fished") or ["", 0])[:2]
        return int(n) if day == self.today() else 0

    def cmd_fish(self, session, message):
        char, lang = session.char, session.lang
        rules = self.fishing_rules()
        if not self.fish_here(char) or not rules:
            pond = next((lid for lid, loc in self.world.locations.items()
                         if any(o.get("fishing") for o in (loc.get("objects") or {}).values())), None)
            self._error(session, "fish_where", where=self.world.locations[pond]["in"] if pond else "?")
            return
        if session.fishing:
            self._error(session, "fish_already")
            return
        if self._fish_today(char) >= int(rules.get("daily", 30)):
            self._error(session, "fish_enough", n=int(rules.get("daily", 30)))
            return
        left = self._cooldown_left(char, "fish")
        if left > 0:
            self._error(session, "fish_wait", time=self._duration(lang, left))
            return
        if not self._slow(session):
            return
        low, high = rules.get("wait", [8, 22])
        session.fishing = {"bite": self.now() + self.rng.uniform(float(low), float(high)), "until": None,
                           "room": self.room_of(char)}
        self._send(session, "info", "fish_cast", extra={"sound": "water"})
        if not session.invisible:
            self._to_room(self.room_of(char), "emote", "fish_cast_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "water"}, actor=session.name)

    def cmd_reel(self, session, message):
        char, lang = session.char, session.lang
        fishing = session.fishing
        rules = self.fishing_rules()
        if not fishing:
            self._error(session, "reel_nothing")
            return
        session.fishing = None
        self._set_cooldown(char, "fish", float(rules.get("cooldown", 3)))
        if fishing.get("until") is None:
            self._send(session, "failed", "reel_early", extra={"sound": "fail"})
            return
        fish = self._pick({fid: float(spec.get("chance", 1)) for fid, spec in rules["fish"].items()})
        spec = rules["fish"][fish]
        low, high = spec.get("kg", [0.5, 2.0])
        kg = round(self.rng.uniform(float(low), float(high)), 1)
        best = dict(char["stats"].get("fish_best") or {})
        record = kg > float(best.get(fish, 0))
        if record:
            best[fish] = kg
            char["stats"]["fish_best"] = best
        day, n = self.today(), self._fish_today(char) + 1
        char["stats"]["fished"] = [day, n]
        room = self.room_of(char)
        if spec.get("release"):
            xp = self.award_xp(session, int(spec.get("xp", 10)))
            self._save(session)
            self._send(session, "paid", "fish_koi", kg=kg, xp=xp, extra={"sound": "rare"})
            if not session.invisible:
                self._to_room(room, "emote", "fish_koi_other", exclude=(session,),
                              extra={"actor": session.name, "sound": "rare"}, actor=session.name)
            return
        if self._goods_count(char) + 1 > self.bag_size(char):
            self._save(session)
            self._send(session, "failed", "fish_bag_full", fish=self.world.things[fish]["one"],
                       max=self.bag_size(char))
            return
        self.give_thing(char, fish, 1)
        self._save(session)
        key = "fish_caught_best" if record and len(best) and n > 1 else "fish_caught"
        self._send(session, "paid", key, fish=self.world.things[fish]["one"], kg=kg, n=n,
                   daily=int(rules.get("daily", 30)), extra={"sound": "harvest"})
        if not session.invisible:
            self._to_room(room, "emote", "fish_caught_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "harvest"}, actor=session.name,
                          fish=self.world.things[fish]["one"])

    def tick_fishing(self, session, now):
        fishing = session.fishing
        if not fishing:
            return
        if fishing.get("room") != self.room_of(session.char):
            session.fishing = None                    # walked away: the line comes in by itself
            return
        if fishing.get("until") is None and now >= float(fishing["bite"]):
            fishing["until"] = now + float(self.fishing_rules().get("window", 5))
            self._send(session, "task", "fish_bite", extra={"sound": "task"})
        elif fishing.get("until") is not None and now > float(fishing["until"]):
            session.fishing = None
            self._set_cooldown(session.char, "fish", float(self.fishing_rules().get("cooldown", 3)))
            self._send(session, "failed", "fish_got_away", extra={"sound": "fail"})

