# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Events: things that happen to everyone (world.json "events"), from the tick.

An event has a kind (when it happens) and an action or an effect (what it
does). Kinds:

  random    now and then while someone is online: one every 30 to 60
            minutes (sooner the more are online; config game.events_*),
            never two big ones at once, each with a cooldown of its own
  weekly    at fixed UTC times (config game.events_weekly)
  seasonal  on a day of the year (the station's birthday on 25 September,
            New Year, the Lantern Festival on the hundredth day)
  hosted    a player's party ("adakan pesta"), at most once in two hours
  custom    an admin's announcement at a time they choose

Actions: collect (in the event's rooms, "collect" finds things), seek (a
runaway robot or a stowaway hidden in one room: "listen" or each "search"
says which way; the first to "catch" or "search" in the right room wins),
watch (a view to "watch" from, once each), join (be in a room and "join",
or open a gift), boss (everyone "fixes" a runaway drone together; its
strength grows with the players online, and rewards with how much each
helped). Effects, while it lasts: work pay for a job, XP, shop discounts,
rooms gone dark, one world's prices for one kind of goods, the casino's
jackpots, courier pay, free temple lanterns.

Every event is announced to everyone with a sound of its own ("announce"
events with an "event" field, so a client can let players hear fewer), and
so is its end and who won or helped. "events" / "acara" lists what's on
and what's coming (with the times as UTC timestamps for the client to show
in local time); "join" / "ikut" takes part where that's needed.

All of it is in the database: the events table (every event that runs or
is scheduled, its state and outcome) and event_players (who took part, and
how much), and meta "events" for the pacing (the next random event, each
event's last time, which scheduled ones have run), so a restart carries on.
"""

import datetime
import logging

import orbit_safety
from orbit_lang import pick

logger = logging.getLogger("orbit.game")

EVENT_DEFAULTS = {
    "events_enabled": True,        # all of them (False: only what admins start or schedule)
    "events_random": True,
    "events_seasonal": True,
    "events_min_gap": 1800,        # seconds between random events, at the least...
    "events_max_gap": 3600,        # ...and at the most, with one player online
    "events_crowd_factor": 0.1,    # each extra player online makes the gap this much shorter...
    "events_min_factor": 0.5,      # ...down to this fraction of it
    "events_party_cooldown": 7200,
    "events_weekly": [             # UTC: weekday 0 is Monday
        {"event": "trading_fair", "weekday": 5, "hour": 14, "minute": 0},
        {"event": "jackpot_night", "weekday": 4, "hour": 13, "minute": 0},
        {"event": "night_rush", "weekday": 2, "hour": 13, "minute": 0},
    ],
}
DATE_FORMATS = ("%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%Y/%m/%d %H:%M")


class EventsMixin:
    @staticmethod
    def commands():
        return {"events": EventsMixin.cmd_events, "join": EventsMixin.cmd_join,
                "listen": EventsMixin.cmd_listen, "catch": EventsMixin.cmd_catch,
                "search": EventsMixin.cmd_search, "watch": EventsMixin.cmd_watch,
                "party": EventsMixin.cmd_party}

    def init_events(self):
        for key, value in EVENT_DEFAULTS.items():
            self.config.setdefault(key, value)
        self.events_def = self.world.data.get("events", {})
        state = self.store.get_json("events", {}) or {}
        self.events_state = {"next": float(state.get("next") or 0), "last": dict(state.get("last") or {}),
                             "done": dict(state.get("done") or {})}
        self.active = {row["id"]: row for row in self.store.events_with("active")}

    def _save_events_state(self):
        self.store.set_json("events", self.events_state)

    # --- what's on ------------------------------------------------------------------------

    def active_of(self, eid):
        return next((row for row in self.active.values() if row["event"] == eid), None)

    def effect(self, name, default=None):
        """The combined value of an effect while events with it are on (None: none)."""
        found = default
        for row in self.active.values():
            value = self.events_def.get(row["event"], {}).get("effect", {}).get(name)
            if value is None and name == "prices" and row["state"].get("prices"):
                value = row["state"]["prices"]
            if value is not None:
                found = value if found is None else found
        return found

    def work_pay_factor(self, char):
        factor = 1.0
        for row in self.active.values():
            by_job = self.events_def.get(row["event"], {}).get("effect", {}).get("work_pay") or {}
            factor *= float(by_job.get(char["job"], 1.0))
        return factor

    def xp_factor(self):
        factor = 1.0
        for row in self.active.values():
            factor *= float(self.events_def.get(row["event"], {}).get("effect", {}).get("xp", 1.0))
        return factor

    def shop_discount(self, sid):
        factor = 1.0
        for row in self.active.values():
            discount = self.events_def.get(row["event"], {}).get("effect", {}).get("discount") or {}
            factor *= float(discount.get(sid, 1.0))
        return factor

    def event_dark(self, lid):
        return any(lid in (self.events_def.get(row["event"], {}).get("effect", {}).get("dark") or [])
                   for row in self.active.values())

    def event_price_factor(self, wid, gid):
        factor = 1.0
        kind = self.world.goods.get(gid, {}).get("kind", "trade")
        for row in self.active.values():
            boom = row["state"].get("market")
            if boom and boom.get("world") == wid and boom.get("kind") == kind:
                factor *= float(boom["factor"])
        return factor

    def simple_factor(self, name):
        factor = 1.0
        for row in self.active.values():
            factor *= float(self.events_def.get(row["event"], {}).get("effect", {}).get(name, 1.0))
        return factor

    def lantern_rules(self):
        for row in self.active.values():
            lantern = self.events_def.get(row["event"], {}).get("effect", {}).get("lantern")
            if lantern:
                return lantern
        return None

    # --- starting and ending --------------------------------------------------------------

    def _event_text(self, lang, eid, field, row=None):
        """An event's line, its {placeholders} filled from the row's state."""
        text = pick(self.events_def[eid][field], lang)
        params = dict((row or {}).get("state", {}).get("params") or {})
        if row and row.get("host"):
            host = self._char_by_key(row["host"])
            params.setdefault("name", host["name"] if host else row["host"])
        if row and row.get("message"):
            params.setdefault("message", row["message"])
        values = {k: pick(v, lang) for k, v in params.items()}
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return text

    def announce_event(self, row, field, key=None, **params):
        eid = row["event"]
        sound = self.events_def[eid].get("sound", "event_start") if field == "start" else "event_end"
        for session in list(self.sessions.values()):
            text = self._event_text(session.lang, eid, field, row) if key is None else \
                self.render(session.lang, key, **params)
            if text:
                self._send(session, "announce", text=text, extra={"sound": sound, "event": eid})

    def start_event(self, eid, now=None, host=None, message="", ends=None, starts=None, quiet=False):
        """Starts an event now (or schedules a custom one for `starts`). Returns its row."""
        now = self.now() if now is None else now
        definition = self.events_def[eid]
        state = {}
        if definition.get("action") == "seek":
            state["target"] = self.rng.choice(definition["rooms"])
        if definition.get("action") == "boss":
            online = max(1, self.online_count())
            hp = int(definition["hp_base"]) + int(definition["hp_per_player"]) * online
            state.update(hp=hp, max_hp=hp)
        if "prices" in definition.get("effect", {}):
            world = self.rng.choice([w for w in self.world.worlds if w not in ("station", "belt")])
            kind = self.rng.choice(["trade", "crop", "ore"])
            state["market"] = {"world": world, "kind": kind, "factor": float(definition["effect"]["prices"])}
            state["params"] = {"place": self.world.worlds[world]["ref"], "kind": self._kind_name(kind)}
        begins = starts if starts is not None else now
        row = self.store.add_event(eid, begins, ends if ends is not None else begins + float(definition["duration"]),
                                   state, "scheduled" if starts is not None and starts > now else "active",
                                   host or "", message)
        if row["status"] == "active":
            self.active[row["id"]] = row
            self.events_state["last"][eid] = now
            self._save_events_state()
            logger.info("event %s started", eid)
            if not quiet:
                self.announce_event(row, "start")
        return row

    def _kind_name(self, kind):
        return {"trade": {"en": "trade goods", "id": "barang dagangan"},
                "crop": {"en": "crops", "id": "hasil panen"},
                "ore": {"en": "ore", "id": "bijih"}}[kind]

    def end_event(self, row, outcome="done"):
        self.active.pop(row["id"], None)
        row["status"] = outcome
        eid = row["event"]
        definition = self.events_def.get(eid, {})
        if definition.get("action") == "boss" and outcome == "done":
            self._boss_rewards(row, won=False)
        self.store.save_event(row)
        logger.info("event %s ended (%s)", eid, outcome)
        if outcome == "done" and definition.get("end"):
            self.announce_event(row, "end")

    def tick_events(self, now):
        for row in list(self.active.values()):
            if now >= float(row["ends"]):
                self.end_event(row)
        for row in self.store.events_with("scheduled"):
            if now >= float(row["starts"]):
                row["status"] = "active"
                self.store.save_event(row)
                self.active[row["id"]] = row
                self.announce_event(row, "start")
        self._tick_calendar(now)
        self._tick_random(now)

    def _tick_calendar(self, now):
        if not self.config.get("events_enabled", True):
            return
        when = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
        for eid, definition in self.events_def.items():
            if definition.get("kind") != "seasonal" or self.active_of(eid) or \
                    not self.config.get("events_seasonal", True):
                continue
            today = when.strftime("%m-%d") == definition.get("date") or \
                when.timetuple().tm_yday == definition.get("day_of_year")
            key = f"{eid}@{when.year}"
            if today and not self.events_state["done"].get(key):
                self.events_state["done"][key] = True
                midnight = when.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
                self.start_event(eid, now, ends=midnight.timestamp())
        for entry in self.config.get("events_weekly") or []:
            eid = entry.get("event")
            if eid not in self.events_def or self.active_of(eid):
                continue
            start = self.weekly_start(entry, now, upcoming=False)
            ends = start + float(self.events_def[eid]["duration"])
            key = f"{eid}@{datetime.datetime.fromtimestamp(start, datetime.timezone.utc):%Y-%m-%d}"
            if start <= now < ends and not self.events_state["done"].get(key):
                self.events_state["done"][key] = True
                self.start_event(eid, now, ends=ends)

    def weekly_start(self, entry, now, upcoming=True):
        """This week's start of a weekly event (or, `upcoming`, the next one not yet over)."""
        when = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
        start = when.replace(hour=int(entry.get("hour", 0)), minute=int(entry.get("minute", 0)), second=0,
                             microsecond=0)
        start += datetime.timedelta(days=(int(entry.get("weekday", 0)) - start.weekday()) % 7)
        if start.timestamp() > now:
            last = start - datetime.timedelta(days=7)
            if not upcoming or last.timestamp() + float(self.events_def[entry["event"]]["duration"]) > now:
                start = last
        if upcoming and start.timestamp() + float(self.events_def[entry["event"]]["duration"]) <= now:
            start += datetime.timedelta(days=7)
        return start.timestamp()

    def _tick_random(self, now):
        if not self.config.get("events_enabled", True) or not self.config.get("events_random", True):
            return
        online = sum(1 for s in self.sessions.values() if s.conn is not None and not s.invisible)
        state = self.events_state
        if online < 1:
            return
        if not state["next"]:
            state["next"] = now + self._gap(online)
            self._save_events_state()
            return
        if now < state["next"]:
            return
        state["next"] = now + self._gap(online)
        big_on = any(self.events_def.get(r["event"], {}).get("big") for r in self.active.values())
        choices = {}
        for eid, definition in self.events_def.items():
            if definition.get("kind") != "random" or self.active_of(eid):
                continue
            if big_on and definition.get("big"):
                continue
            if online < int(definition.get("min_online", 1)):
                continue
            if now - float(state["last"].get(eid, 0)) < float(definition.get("cooldown", 0)):
                continue
            choices[eid] = float(definition.get("weight", 1))
        self._save_events_state()
        if choices:
            self.start_event(self._pick(choices), now)

    def _gap(self, online):
        factor = max(float(self.config["events_min_factor"]),
                     1.0 - float(self.config["events_crowd_factor"]) * (online - 1))
        return self.rng.uniform(float(self.config["events_min_gap"]), float(self.config["events_max_gap"])) * factor

    # --- taking part ------------------------------------------------------------------------

    def events_here(self, char, action):
        """Active events with `action` that happen where `char` is."""
        found = []
        for row in self.active.values():
            definition = self.events_def.get(row["event"], {})
            if definition.get("action") != action:
                continue
            rooms = definition.get("rooms")
            if rooms is None or char["location"] in rooms:
                found.append((row, definition))
        return found

    def _reward(self, session, row, credits, xp=0, thing=None):
        char = session.char
        if credits:
            self.earn(char, credits, "events")
        if thing:
            self.give_thing(char, thing, 1)
        self.store.add_event_points(row["id"], char["id"], 1, self.now())
        char["stats"]["events"] = int(char["stats"].get("events") or 0) + (
            0 if self.store.event_points(row["id"], char["id"]) > 1 else 1)
        self._save(session)
        if xp:
            self.award_xp(session, int(xp))

    def event_collect(self, session):
        """ "collect" during a collecting event where you are. True when it was one."""
        found = self.events_here(session.char, "collect")
        if not found:
            return False
        row, definition = found[0]
        char, lang = session.char, session.lang
        taken = self.store.event_points(row["id"], char["id"])
        if taken >= int(definition.get("per_player", 5)):
            self._error(session, "event_enough", event=definition["name"])
            return True
        left = self._cooldown_left(char, "event")
        if left > 0 or not self._slow(session):
            if left > 0:
                self._error(session, "event_wait", time=self._duration(lang, left))
            return True
        self._set_cooldown(char, "event", 8.0)
        if definition.get("loot"):
            if self._goods_count(char) >= self.bag_size(char):
                self._error(session, "bag_full", max=self.bag_size(char))
                return True
            gid = self._pick(definition["loot"])
            self._reward(session, row, 0, thing=gid)
            text = pick(definition["found"], lang).format(things=pick(self._count_of(gid, 1), lang))
        else:
            low, high = definition.get("credits", [5, 10])
            n = self.rng.randint(int(low), int(high))
            self._reward(session, row, n)
            text = pick(definition["found"], lang).format(n=n)
        self._send(session, "paid", text=text, extra={"sound": "coins"})
        return True

    def cmd_watch(self, session, message):
        found = self.events_here(session.char, "watch")
        if not found:
            self._error(session, "event_nothing_to_watch")
            return
        row, definition = found[0]
        char, lang = session.char, session.lang
        if self.store.event_points(row["id"], char["id"]):
            self._error(session, "event_seen")
            return
        n = int(definition.get("credits", [0, 0])[0])
        self._reward(session, row, n, xp=definition.get("xp", 0))
        self._send(session, "paid", text=pick(definition["seen"], lang).format(n=n),
                   extra={"sound": definition.get("sound", "event_start")})

    def cmd_join(self, session, message):
        char, lang = session.char, session.lang
        done = False
        for row in list(self.active.values()):
            definition = self.events_def.get(row["event"], {})
            if definition.get("action") not in ("join", "gift"):
                continue
            rooms = definition.get("rooms")
            if rooms and char["location"] not in rooms:
                continue
            if self.store.event_points(row["id"], char["id"]):
                continue
            gift = definition.get("gift") or {}
            n = int(gift.get("credits") or definition.get("credits", [0, 0])[0])
            self._reward(session, row, n, xp=definition.get("xp", 0), thing=gift.get("thing"))
            self._send(session, "paid", text=pick(definition["joined"], lang).format(n=n),
                       extra={"sound": definition.get("sound", "event_party")})
            done = True
        if done:
            return
        for row in self.active.values():                  # somewhere else, or already in
            definition = self.events_def.get(row["event"], {})
            if definition.get("action") in ("join", "gift"):
                rooms = definition.get("rooms")
                if self.store.event_points(row["id"], char["id"]):
                    self._error(session, "event_joined_already", event=definition["name"])
                else:
                    self._error(session, "event_join_where", event=definition["name"],
                                where=self.world.locations[rooms[0]]["in"])
                return
        self._error(session, "event_nothing_to_join")

    # --- hide and seek ---------------------------------------------------------------------

    def _seek_event(self, session, verb):
        for row in self.active.values():
            definition = self.events_def.get(row["event"], {})
            if definition.get("action") == "seek" and (verb is None or definition.get("verb") == verb):
                return row, definition
        return None, None

    def _clue(self, lang, here, target):
        """Which way the target is from `here`: a compass direction on the same deck, else up or down."""
        world = self.world
        if world.world_of(here) != world.world_of(target):
            return self.render(lang, "event_clue_far")
        a, b = world.locations[here], world.locations[target]
        if a["area"] == b["area"]:
            d = world.heading(here, target)
            return self.render(lang, "event_clue_dir", dir=self.dir_word(lang, d)) if d else ""
        deck_a = world.areas[a["area"]].get("deck")
        deck_b = world.areas[b["area"]].get("deck")
        if deck_a is not None and deck_b is not None and deck_a != deck_b:
            return self.render(lang, "event_clue_deck", deck=world.areas[b["area"]]["name"])
        return self.render(lang, "event_clue_elsewhere", deck=world.areas[b["area"]]["name"])

    def cmd_listen(self, session, message):
        row, definition = self._seek_event(session, "catch")
        if row is None:
            self._error(session, "event_nothing_to_hear")
            return
        char, lang = session.char, session.lang
        target = row["state"]["target"]
        if char["location"] == target:
            self._info(session, "event_clue_here", sound=definition.get("clue_sound"))
            return
        d = self.world.heading(char["location"], target) if \
            self.world.locations[char["location"]]["area"] == self.world.locations[target]["area"] else None
        extra = {"sound": definition.get("clue_sound", "robot_beep")}
        if d:
            extra["dir"] = d
        self._send(session, "info", text=self._clue(lang, char["location"], target), extra=extra)

    def cmd_catch(self, session, message):
        self._seek(session, "catch")

    def cmd_search(self, session, message):
        self._seek(session, "search")

    def _seek(self, session, verb):
        row, definition = self._seek_event(session, verb)
        if row is None:
            self._error(session, "event_nothing_to_" + verb)
            return
        char, lang = session.char, session.lang
        left = self._cooldown_left(char, "event")
        if left > 0:
            self._error(session, "event_wait", time=self._duration(lang, left))
            return
        if not self._slow(session):
            return
        target = row["state"]["target"]
        if char["location"] != target:
            self._set_cooldown(char, "event", 3.0)
            text = pick(definition["wrong"], lang)
            if verb == "search":
                text += " " + self._clue(lang, char["location"], target)
            self._send(session, "failed", text=text)
            return
        prize = int(definition["prize"] * float((definition.get("job_bonus") or {}).get(char["job"], 1.0)))
        self._reward(session, row, prize, xp=definition.get("xp", 0))
        self.active.pop(row["id"], None)
        row["status"] = "won"
        row["state"]["winner"] = session.name
        self.store.save_event(row)
        for other in list(self.sessions.values()):
            self._send(other, "announce", text=pick(definition["won"], other.lang).format(name=session.name, n=prize),
                       extra={"sound": "event_end", "event": row["event"]})
        logger.info("event %s won by %s", row["event"], session.name)

    # --- the co-op drone -------------------------------------------------------------------

    def event_fix(self, session):
        """ "fix drone" (or "work", from Orbit 1.0) where a boss is: True when it was one."""
        found = self.events_here(session.char, "boss")
        if not found:
            return False
        row, definition = found[0]
        char, lang = session.char, session.lang
        left = self._cooldown_left(char, "event")
        if left > 0:
            self._error(session, "event_wait", time=self._duration(lang, left))
            return True
        if not self._slow(session):
            return True
        self._set_cooldown(char, "event", 8.0)
        rules = self.econ.get("creature_rules", {})
        roll = self.rng.randint(1, int(rules.get("die", 20)))
        bonus = int(self.level_of(int(char.get("xp") or 0)) * float(rules.get("level_bonus", 0.5)))
        if roll + bonus < 8:
            self.store.add_event_points(row["id"], char["id"], 0, self.now())
            self._send(session, "failed", text=pick(definition["miss"], lang), extra={"sound": "fail"})
            return True
        damage = 2 if roll >= 15 else 1
        row["state"]["hp"] = max(0, int(row["state"]["hp"]) - damage)
        self.store.add_event_points(row["id"], char["id"], damage, self.now())
        self.store.save_event(row)
        self._send(session, "paid", text=pick(definition["hit"], lang).format(left=row["state"]["hp"]),
                   extra={"sound": "event_boss"})
        if row["state"]["hp"] <= 0:
            self.active.pop(row["id"], None)
            row["status"] = "won"
            self.store.save_event(row)
            self._boss_rewards(row, won=True)
        return True

    def _boss_rewards(self, row, won):
        definition = self.events_def[row["event"]]
        players = self.store.event_players(row["id"])
        rewards = []
        for char_id, points in players:
            if won:
                credits = min(int(definition["reward_max"]),
                              int(definition["reward_base"]) + int(definition["reward_per_point"]) * int(points))
            else:
                credits = int(definition.get("consolation", 0))
            stored = self.store.by_id(char_id)
            if stored is None:
                continue
            session = self.sessions.get(stored["name_key"])
            char = session.char if session else stored
            self.earn(char, credits, "events")
            char["stats"]["events"] = int(char["stats"].get("events") or 0) + 1
            self.store.save(char)
            if session is not None and won:
                self.award_xp(session, int(definition.get("xp", 0)))
            rewards.append((char["name"], credits, points))
        if won:
            rewards.sort(key=lambda r: -r[2])
            for other in list(self.sessions.values()):
                listed = [self.render(other.lang, "event_reward", name=name, n=n) for name, n, _p in rewards]
                self._send(other, "announce", text=pick(definition["won"], other.lang).format(
                    rewards=self.texts.join(other.lang, listed) or "-"),
                    extra={"sound": "event_end", "event": row["event"]})

    # --- parties ------------------------------------------------------------------------------

    def cmd_party(self, session, message):
        char = session.char
        if char["location"] != "cabin" or char["stats"].get("visit"):
            self._error(session, "party_where")
            return
        if self._muted(session):
            return
        left = self._cooldown_left(char, "party")
        if left > 0:
            self._error(session, "party_wait", time=self._duration(session.lang, left))
            return
        self._set_cooldown(char, "party", float(self.config["events_party_cooldown"]))
        self._save(session)
        self.start_event("party", host=session.key)

    def party_of(self, host_key):
        return any(row["event"] == "party" and row.get("host") == host_key for row in self.active.values())

    # --- admins ---------------------------------------------------------------------------------

    def find_event(self, text):
        """An event id for what an admin typed ("meteor shower", "hujan meteor", "meteor_shower")."""
        key = orbit_safety.name_key(text).replace("_", " ")
        if not key:
            return None
        for eid, definition in self.events_def.items():
            names = {eid.replace("_", " ")} | {orbit_safety.name_key(definition["name"][lang]) for lang in ("en", "id")}
            if key in names:
                return eid
        for eid, definition in self.events_def.items():
            names = [eid.replace("_", " ")] + [orbit_safety.name_key(definition["name"][lang]) for lang in ("en", "id")]
            if any(key in name for name in names):
                return eid
        return None

    def admin_event_start(self, session, text):
        eid = self.find_event(text)
        startable = [e for e, d in self.events_def.items() if d.get("kind") not in ("hosted", "custom")]
        if eid is None or eid not in startable:
            self._error(session, "event_unknown", events=", ".join(startable))
            return
        if self.active_of(eid):
            self._error(session, "event_already_on", event=self.events_def[eid]["name"])
            return
        self.start_event(eid)
        self._log(session, "start event", eid)
        self._info(session, "event_started", event=self.events_def[eid]["name"])

    def admin_event_stop(self, session, text):
        rows = list(self.active.values()) + self.store.events_with("scheduled")
        if text:
            eid = self.find_event(text)
            key = orbit_safety.name_key(text)
            rows = [r for r in rows
                    if r["event"] == eid or (r["message"] and key in orbit_safety.name_key(r["message"]))]
        if not rows:
            self._error(session, "event_none_to_stop")
            return
        row = sorted(rows, key=lambda r: -float(r["starts"]))[0]
        if row["status"] == "scheduled":
            row["status"] = "cancelled"
            self.store.save_event(row)
        else:
            self.end_event(row, "cancelled")
            for other in list(self.sessions.values()):
                self._send(other, "announce", "event_cancelled_all", event=self._event_label(other.lang, row),
                           extra={"sound": "event_end", "event": row["event"]})
        self._log(session, "stop event", row["event"], row.get("message") or "")
        self._info(session, "event_stopped", event=self._event_label(session.lang, row))

    def admin_event_schedule(self, session, text):
        """ "2026-09-27 14:00 Race night!" (UTC), or "30 Race night!" (in 30 minutes)."""
        words = str(text or "").split()
        starts, message = None, ""
        if len(words) >= 3:
            for fmt in DATE_FORMATS:
                try:
                    when = datetime.datetime.strptime(" ".join(words[:2]), fmt)
                except ValueError:
                    continue
                starts = when.replace(tzinfo=datetime.timezone.utc).timestamp()
                message = " ".join(words[2:])
                break
        if starts is None and len(words) >= 2 and words[0].isdigit():
            starts = self.now() + 60 * int(words[0])
            message = " ".join(words[1:])
        message = orbit_safety.tidy(message, 200)
        if starts is None or not message or starts < self.now() - 60:
            self._error(session, "event_schedule_how")
            return
        row = self.start_event("custom", message=message, starts=max(starts, self.now()))
        self._log(session, "schedule event", "custom", message)
        when = datetime.datetime.fromtimestamp(float(row["starts"]), datetime.timezone.utc)
        self._info(session, "event_scheduled", message=message, when=when.strftime("%Y-%m-%d %H:%M"))

    def _event_label(self, lang, row):
        if row["event"] == "custom":
            return row.get("message") or pick(self.events_def["custom"]["name"], lang)
        return pick(self.events_def[row["event"]]["name"], lang)

    # --- listing --------------------------------------------------------------------------------

    def cmd_events(self, session, message):
        lang = session.lang
        now = self.now()
        on = []
        for row in sorted(self.active.values(), key=lambda r: r["ends"]):
            definition = self.events_def.get(row["event"], {})
            name = self._event_text(lang, row["event"], "start", row) if row["event"] == "custom" else \
                pick(definition["name"], lang)
            if row["event"] == "party":
                host = self._char_by_key(row["host"])
                name = self.render(lang, "event_party_name", name=host["name"] if host else row["host"])
            on.append(self.render(lang, "event_on", name=name, about=definition["about"],
                                  time=self._duration(lang, float(row["ends"]) - now)))
        coming, schedule = [], []
        for entry in self.config.get("events_weekly") or []:
            eid = entry.get("event")
            if eid not in self.events_def or self.active_of(eid):
                continue
            start = self.weekly_start(entry, now)
            coming.append((start, pick(self.events_def[eid]["name"], lang), eid))
        for row in self.store.events_with("scheduled"):
            coming.append((float(row["starts"]), row["message"] or pick(self.events_def["custom"]["name"], lang),
                           "custom"))
        for eid, definition in self.events_def.items():
            if definition.get("kind") == "seasonal" and not self.active_of(eid):
                start = self.next_seasonal(definition, now)
                if start is not None and start <= now:
                    # Its day has begun (next_seasonal gives today's start, for
                    # the tick that starts it): what's coming is next year's.
                    start = self.next_seasonal(definition, start + 86400)
                if start is not None and start - now < 40 * 86400:
                    coming.append((start, pick(definition["name"], lang), eid))
        coming.sort()
        entries = []
        for start, name, eid in coming[:6]:
            when = datetime.datetime.fromtimestamp(start, datetime.timezone.utc)
            entries.append(self.render(lang, "event_coming", name=name,
                                       day=self.render(lang, f"weekday_{when.weekday()}"),
                                       date=when.strftime("%d-%m"), hour=when.strftime("%H:%M")))
            schedule.append({"event": eid, "name": name, "at": start})
        text = self.render(lang, "events_on", entries="; ".join(on)) if on else self.render(lang, "events_none")
        if entries:
            text += " " + self.render(lang, "events_coming", entries="; ".join(entries))
        self._send(session, "info", text=text, extra={"schedule": schedule})

    def next_event(self, now):
        """(start, event id) of the next weekly or seasonal event that isn't on now, or None."""
        coming = []
        for entry in self.config.get("events_weekly") or []:
            eid = entry.get("event")
            if eid in self.events_def and not self.active_of(eid):
                coming.append((self.weekly_start(entry, now), eid))
        for eid, definition in self.events_def.items():
            if definition.get("kind") == "seasonal" and not self.active_of(eid):
                start = self.next_seasonal(definition, now)
                if start is not None and start <= now:
                    start = self.next_seasonal(definition, start + 86400)
                if start is not None:
                    coming.append((start, eid))
        coming = [c for c in coming if c[0] > now]
        return min(coming) if coming else None

    def next_seasonal(self, definition, now):
        when = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
        for year in (when.year, when.year + 1):
            if definition.get("date"):
                month, day = (int(x) for x in definition["date"].split("-"))
                start = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
            elif definition.get("day_of_year"):
                start = datetime.datetime(year, 1, 1, tzinfo=datetime.timezone.utc) + \
                    datetime.timedelta(days=int(definition["day_of_year"]) - 1)
            else:
                return None
            if start.timestamp() + 86400 > now:
                return start.timestamp()
        return None

