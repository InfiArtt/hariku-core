# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The game: joining, commands, jobs, missions, the market and admin, with no
network code. orbit_server.py hands it connections and messages; the tests
hand it fakes.

A connection ("conn") is anything with send(dict), close(code, reason), a
`lang` ("en"/"id"), an `ip_hash` (or None) and a `session` attribute the game
sets. The game answers with messages (see PROTOCOL.md in the README):

  {"t": "welcome", "name", "job", "new", "resumed", "credits", "room", "amb"}
  {"t": "ev", "k": kind, "text": line, ...}      every event, in the reader's language
  {"t": "err", "code", "text", "fatal"}          a hello that can't join

An event's "k" (kind) tells the client which sound fits and whose voice
reads it: "room", "moved", "arrive", "leave", "say"/"said", "whisper"/
"whispered", "shout"/"shouted", "emote", "who", "info", "error", "tones",
"paid", "failed", "received", "gave", "mission", "trade", "flight",
"announce", "system". Some carry "actor" (who did it), "brief" (a short line
for your own actions), "room" and "amb" (where you are now and its
ambience), "codes" (the reactor's tones).

Players stay "link-dead" for a minute after their connection drops, so a
reconnect resumes them quietly. Everything that matters (credits, items,
place, cooldowns, a cargo run in progress) is saved as it changes.
"""

import datetime
import logging
import math
import random
import re
import time

import orbit_earth
import orbit_lang
import orbit_safety
from orbit_lang import pick

logger = logging.getLogger("orbit.game")

PROTOCOL_VERSION = 1
MAX_ARG = 500

CLOSE_KICKED = 4000
CLOSE_REPLACED = 4001
CLOSE_BANNED = 4003

GAME_DEFAULTS = {
    "admins": [],
    "start_credits": 100,
    "linkdead_seconds": 60,
    "market_seconds": 180,
    "flight_seconds": 60,
    "pilot_cooldown": 300,
    "engineer_cooldown": 120,
    "engineer_fail_cooldown": 30,
    "missions_per_day": 3,
    "say_limit": 300,
    "description_limit": 160,
    "chat_rate": 1.0,             # say, whisper and emote: a second apart on average...
    "chat_burst": 5,              # ...with this many in a quick row
    "shout_seconds": 10,          # a shout at most every 10 seconds
    "max_goods": 20,              # how many goods fit in your bag
    "ban_ip_days": 7,
    "reserved_names": ["admin", "administrator", "system", "server", "orbit", "hariku", "aruna",
                       "captain", "kapten", "moderator", "semua", "everyone", "all", "anyone",
                       "someone", "nobody", "you", "kamu", "aku", "saya", "me", "credits",
                       "kredit"],
}

JOBS_WITH_WORK = ("engineer", "pilot", "trader")
REPAIR_MIN, REPAIR_MAX = 3, 6
TRADE_FEES = {"trader": (0.02, 0.04)}    # (added when buying, taken when selling)
PUBLIC_FEES = (0.10, 0.12)
PRICE_IMPACT = 0.02                     # each unit bought or sold moves the price this much
CREDIT_WORDS = {"credit", "credits", "kredit", "cr", "uang", "duit", "money", "coins"}


class Session:
    """A character in play (online, or link-dead for a moment)."""

    def __init__(self, char, conn, config, clock):
        self.char = char
        self.conn = conn
        self.lang = getattr(conn, "lang", "en")
        self.dropped_at = None
        self.visited = set()
        self.task = None          # the reactor repair in progress
        self.chat = orbit_safety.TokenBucket(config["chat_rate"], config["chat_burst"], clock)
        self.shout = orbit_safety.TokenBucket(1.0 / max(1, config["shout_seconds"]), 1, clock)

    @property
    def name(self):
        return self.char["name"]

    @property
    def key(self):
        return self.char["name_key"]


class Market:
    """The Promenade's prices: they drift every few minutes, back towards
    each good's usual price, and move a little with every unit traded."""

    def __init__(self, goods, store, rng, clock, period):
        self.goods = goods
        self.store = store
        self.rng = rng
        self.clock = clock
        self.period = period
        state = store.get_json("market", {}) or {}
        prices = state.get("prices") if isinstance(state.get("prices"), dict) else {}
        self.prices = {}
        for gid, good in goods.items():
            try:
                self.prices[gid] = self._clamp(gid, float(prices.get(gid, good["base"])))
            except (TypeError, ValueError):
                self.prices[gid] = float(good["base"])
        self.next_drift = float(state.get("next", 0) or 0)

    def _clamp(self, gid, price):
        base = self.goods[gid]["base"]
        return max(0.4 * base, min(2.5 * base, price))

    def save(self):
        self.store.set_json("market", {"prices": self.prices, "next": self.next_drift})

    def tick(self, now):
        if now < self.next_drift:
            return False
        for gid, good in self.goods.items():
            price = self.prices[gid]
            price += 0.15 * (good["base"] - price)
            price *= math.exp(self.rng.gauss(0.0, good.get("volatility", 0.06)))
            self.prices[gid] = self._clamp(gid, price)
        self.next_drift = now + self.period
        self.save()
        return True

    @staticmethod
    def fees(job):
        return TRADE_FEES.get(job, PUBLIC_FEES)

    @classmethod
    def _unit(cls, price, job, side):
        # Buying rounds up and selling down, so buying and selling back at
        # once always loses a little: prices must move to make a profit.
        fee, spread = cls.fees(job)
        if side == "buy":
            return max(1, int(math.ceil(price * (1 + fee) - 1e-9)))
        return max(1, int(math.floor(price * (1 - spread) + 1e-9)))

    def unit_price(self, gid, job, side):
        return self._unit(self.prices[gid], job, side)

    def quote(self, gid, job, side, n):
        """The total for `n` units, the price moving with each one."""
        price, total = self.prices[gid], 0
        for _ in range(n):
            total += self._unit(price, job, side)
            price *= (1 + PRICE_IMPACT) if side == "buy" else (1 - PRICE_IMPACT)
        return total

    def trade(self, gid, side, n):
        factor = (1 + PRICE_IMPACT) if side == "buy" else (1 - PRICE_IMPACT)
        self.prices[gid] = self._clamp(gid, self.prices[gid] * factor ** n)
        self.save()


class Game:
    def __init__(self, world, store, texts, config=None, word_filter=None, clock=time.time,
                 rng=None):
        self.world = world
        self.store = store
        self.texts = texts
        self.config = dict(GAME_DEFAULTS)
        self.config.update(config or {})
        self.filter = word_filter or orbit_safety.WordFilter()
        self.clock = clock
        self.rng = rng or random.Random()
        self.sessions = {}                # name key -> Session
        self.admins = {orbit_safety.name_key(n) for n in self.config["admins"]}
        self.market = Market(world.goods, store, self.rng, clock, self.config["market_seconds"])
        self.reserved = set(self.config["reserved_names"])
        for loc in world.locations.values():
            for lang in orbit_lang.LANGUAGES:
                self.reserved.update(w for w in loc.get("aliases", {}).get(lang, []) if " " not in w)
        self.reserved.update(world.emotes)

    # ------------------------------------------------------------------ helpers

    def now(self):
        return self.clock()

    def render(self, lang, key, **params):
        return self.texts.render(lang, key, **params)

    def _send(self, session, kind, key=None, text=None, brief=None, extra=None, **params):
        """One event to one player, in their language. Nothing for a link-dead one."""
        conn = session.conn
        if conn is None:
            return
        lang = session.lang
        if text is None:
            text = self.render(lang, key, **params)
        message = {"t": "ev", "k": kind, "text": text}
        if brief:
            message["brief"] = self.render(lang, brief, **params)
        if extra:
            message.update(extra)
        conn.send(message)

    def _error(self, session, key, **params):
        self._send(session, "error", key, **params)

    def room_of(self, char):
        loc = char["location"]
        if self.world.locations.get(loc, {}).get("private"):
            return f"{loc}:{char['name_key']}"
        return loc

    def _in_room(self, room, exclude=()):
        skip = {id(s) for s in exclude}
        return [s for s in self.sessions.values()
                if self.room_of(s.char) == room and id(s) not in skip]

    def _to_room(self, room, kind, key, exclude=(), extra=None, **params):
        for other in self._in_room(room, exclude):
            self._send(other, kind, key, extra=extra, **params)

    def _loc(self, char_or_id):
        lid = char_or_id if isinstance(char_or_id, str) else char_or_id["location"]
        return self.world.locations[lid]

    def _where(self, session):
        """What is sent with an event that moves you: the room and its ambience."""
        lid = session.char["location"]
        return {"room": lid, "amb": self.world.locations[lid]["ambience"]}

    def _find_session(self, name):
        return self.sessions.get(orbit_safety.name_key(name))

    def _find_near(self, session, name):
        """Another player in the same room, by name or the start of it."""
        wanted = orbit_safety.name_key(name)
        if not wanted:
            return None
        here = self._in_room(self.room_of(session.char), exclude=(session,))
        for other in here:
            if other.key == wanted:
                return other
        starts = [o for o in here if o.key.startswith(wanted)]
        return starts[0] if len(starts) == 1 else None

    def _duration(self, lang, seconds):
        seconds = max(1, int(math.ceil(seconds)))
        if seconds < 90:
            return self.render(lang, "dur_seconds", n=seconds)
        minutes = int(round(seconds / 60.0))
        return self.render(lang, "dur_minute" if minutes == 1 else "dur_minutes", n=minutes)

    def _save(self, session_or_char):
        char = session_or_char.char if isinstance(session_or_char, Session) else session_or_char
        self.store.save(char)

    def _cooldown_left(self, char, name):
        until = char["stats"].get("cooldowns", {}).get(name, 0)
        return max(0.0, float(until) - self.now())

    def _set_cooldown(self, char, name, seconds):
        char["stats"].setdefault("cooldowns", {})[name] = self.now() + seconds

    def _muted(self, session):
        left = float(session.char.get("muted_until") or 0) - self.now()
        if left > 0:
            self._error(session, "muted", time=self._duration(session.lang, left))
            return True
        return False

    def _chat_text(self, session, text, limit=None):
        """Filtered, tidy text to say, or None (and the reason told)."""
        if self._muted(session):
            return None
        text = orbit_safety.tidy(text, limit or self.config["say_limit"])
        if not text:
            self._error(session, "say_what")
            return None
        if not session.chat.take():
            self._error(session, "slow_down")
            return None
        return self.filter.clean(text)

    @staticmethod
    def _arg(message, name="a", limit=MAX_ARG):
        value = message.get(name)
        if not isinstance(value, str):
            return ""
        return value.strip()[:limit]

    @staticmethod
    def _count(message, default=1, low=1, high=1_000_000):
        value = message.get("n")
        if value in (None, ""):
            return default
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return n if low <= n <= high else None

    def is_admin(self, session):
        return session.key in self.admins

    def online_count(self):
        return sum(1 for s in self.sessions.values() if s.conn is not None)

    def today(self):
        return datetime.datetime.fromtimestamp(self.now(), datetime.timezone.utc).strftime("%Y-%m-%d")

    # ------------------------------------------------------------------ joining

    def hello(self, conn, message):
        """A new connection's first message. Returns whether it joined; when it
        didn't, the connection was told why ({"t": "err"}) and closed."""
        lang = orbit_lang.language(message.get("lang"))
        conn.lang = lang
        if message.get("t") != "hello" or message.get("v") != PROTOCOL_VERSION:
            return self._refuse(conn, "version")
        if self.store.ip_banned(getattr(conn, "ip_hash", None)):
            return self._refuse(conn, "banned")
        secret_hash = self.store.hash_secret(message.get("secret"))
        if secret_hash is None:
            return self._refuse(conn, "bad_secret")
        char = self.store.by_secret_hash(secret_hash)
        new = False
        if char is None:
            name, why = orbit_safety.check_name(message.get("name"), self.filter, self.reserved)
            if why:
                return self._refuse(conn, f"name_{why}")
            key = orbit_safety.name_key(name)
            if self.store.by_name(key) is not None:
                return self._refuse(conn, "name_taken", name=name)
            job = message.get("job")
            if job not in self.world.jobs:
                return self._refuse(conn, "bad_job")
            char = self.store.create(name, key, secret_hash, job, self.config["start_credits"],
                                     self.world.start)
            new = True
            logger.info("new character %s (%s)", name, job)
        if char["banned"]:
            return self._refuse(conn, "banned")
        if char["location"] not in self.world.locations:
            char["location"] = self.world.start

        session = self.sessions.get(char["name_key"])
        resumed = session is not None
        if session is None:
            session = Session(char, conn, self.config, self.clock)
            self.sessions[session.key] = session
        else:
            old = session.conn
            if old is not None and old is not conn:
                self._send(session, "system", "replaced")
                old.session = None
                old.close(CLOSE_REPLACED, "replaced")
            session.conn = conn
            session.dropped_at = None
        session.lang = lang
        conn.session = session
        char = session.char
        conn.send({"t": "welcome", "v": PROTOCOL_VERSION, "name": char["name"], "job": char["job"],
                   "new": new, "resumed": resumed, "credits": char["credits"], **self._where(session)})
        if resumed:
            self._send(session, "room", text=self.render(lang, "welcome_resumed") + " "
                       + self.look_text(session, full=False), extra=self._where(session))
            logger.info("%s resumed", char["name"])
            return True
        logger.info("%s joined", char["name"])
        greeting = self.render(lang, "welcome_new" if new else "welcome_back", name=char["name"],
                               job=self.world.job_name(char["job"]))
        settled = self._settle_flight(session, on_join=True)
        session.visited.add(char["location"])
        text = " ".join(t for t in (greeting, settled, self.look_text(session, full=True)) if t)
        self._send(session, "room", text=text, extra=self._where(session))
        if not self._loc(char).get("private"):
            self._to_room(self.room_of(char), "arrive", "arrive_new" if new else "arrive_join",
                          exclude=(session,), extra={"actor": char["name"]}, actor=char["name"])
        return True

    def _refuse(self, conn, code, **params):
        lang = getattr(conn, "lang", "en")
        conn.send({"t": "err", "code": code, "fatal": True,
                   "text": self.render(lang, f"err_{code}", **params)})
        conn.close(CLOSE_BANNED if code == "banned" else 1008, code)
        return False

    def dropped(self, conn):
        """The connection went away. The character stays for a moment (link-dead)."""
        session = getattr(conn, "session", None)
        conn.session = None
        if session is None or session.conn is not conn:
            return
        session.conn = None
        session.dropped_at = self.now()
        session.task = None
        self._save(session)

    def _remove(self, session, key="leave_quit"):
        self.sessions.pop(session.key, None)
        self._save(session)
        if not self._loc(session.char).get("private"):
            self._to_room(self.room_of(session.char), "leave", key, exclude=(session,),
                          extra={"actor": session.name}, actor=session.name)

    # ------------------------------------------------------------------ commands

    def receive(self, conn, message):
        session = getattr(conn, "session", None)
        if session is None or not isinstance(message, dict):
            return
        if message.get("t") != "cmd":
            return
        command = message.get("c")
        handler = self.COMMANDS.get(command) if isinstance(command, str) else None
        if handler is None:
            self._error(session, "unknown_command")
            return
        try:
            handler(self, session, message)
        except Exception:
            logger.exception("the command %r failed", command)
            self._error(session, "oops")

    # --- looking --------------------------------------------------------------------

    def _earth(self, lang):
        when = datetime.datetime.fromtimestamp(self.now(), datetime.timezone.utc)
        return orbit_earth.describe(self.world.regions, when,
                                    lambda key, **p: self.render(lang, key, **p))

    def _person(self, lang, other):
        name = other.name
        if other.conn is None:
            return self.render(lang, "person_away", name=name, job=self.world.job_name(other.char["job"]))
        return self.render(lang, "person", name=name, job=self.world.job_name(other.char["job"]))

    def look_text(self, session, full=True):
        lang, char = session.lang, session.char
        loc = self._loc(char)
        parts = [f"{pick(loc['name'], lang)}."]
        if char["location"] == "shuttle":
            flight = char["stats"].get("flight") or {}
            parts.append(pick(loc["desc"], lang))
            parts.append(self.render(lang, "look_in_flight",
                                     time=self._duration(lang, float(flight.get("arrive", 0)) - self.now())))
            return " ".join(parts)
        if full:
            parts.append(pick(loc["desc"], lang))
            if loc.get("earth_view"):
                parts.append(self._earth(lang))
            hints = loc.get("hints", {})
            hint = hints.get(char["job"]) or hints.get("all")
            if hint:
                parts.append(pick(hint, lang))
        others = self._in_room(self.room_of(char), exclude=(session,))
        if others:
            parts.append(self.render(lang, "look_people",
                                     people=[self._person(lang, o) for o in sorted(others, key=lambda o: o.key)]))
        elif full and not loc.get("private"):
            parts.append(self.render(lang, "look_alone"))
        exits = [self.world.locations[e]["name"] for e in loc.get("exits", [])]
        if exits:
            parts.append(self.render(lang, "look_exits", exits=exits))
        if full and loc.get("objects"):
            things = [o["names"][lang][0] for o in loc["objects"].values()]
            parts.append(self.render(lang, "look_objects", things=things))
        return " ".join(p for p in parts if p)

    def cmd_look(self, session, message):
        target = self._arg(message)
        lang = session.lang
        if not target or orbit_safety.name_key(target) in ("around", "sekitar", "here", "sini",
                                                             "room", "ruangan"):
            session.visited.add(session.char["location"])
            self._send(session, "room", text=self.look_text(session, full=True),
                       extra=self._where(session))
            return
        other = self._find_near(session, target)
        if other is not None:
            description = other.char["description"] or self.render(lang, "look_player_plain")
            self._send(session, "info", "look_player", name=other.name,
                       job=self.world.job_name(other.char["job"]), description=description)
            return
        oid, obj = self.world.find_object(session.char["location"], target)
        if obj is not None:
            text = self._earth(lang) if obj.get("earth") else pick(obj["desc"], lang)
            self._send(session, "info", text=text or self.render(lang, "look_nothing_special"))
            return
        if orbit_safety.name_key(target) in ("me", "myself", "aku", "diriku", "saya", "self"):
            description = session.char["description"] or self.render(lang, "describe_none")
            self._send(session, "info", "look_self", job=self.world.job_name(session.char["job"]),
                       description=description)
            return
        if self._find_session(target) is not None:
            self._error(session, "not_here", name=self._find_session(target).name)
            return
        self._error(session, "look_what", what=target)

    # --- moving ---------------------------------------------------------------------

    def cmd_go(self, session, message):
        char = session.char
        if char["location"] == "shuttle":
            self._error(session, "in_flight")
            return
        text = self._arg(message)
        if not text:
            self._error(session, "go_where")
            return
        dest = self.world.find_location(text)
        if dest is None:
            self._error(session, "no_place", what=text)
            return
        if dest == char["location"]:
            self._send(session, "info", "already_here", place=self._loc(dest)["ref"])
            return
        path = self.world.route(char["location"], dest)
        if not path:
            self._error(session, "no_way")
            return
        self._move(session, path)

    def _move(self, session, path):
        char, lang = session.char, session.lang
        dest = path[-1]
        old_room = self.room_of(char)
        old_private = self._loc(char).get("private")
        came_from = self.world.locations[path[-2]] if len(path) > 1 else self._loc(char)
        char["location"] = dest
        self._save(session)
        new_loc = self._loc(dest)
        if not old_private:
            key = "leave_to_cabin" if new_loc.get("private") else "leave_to"
            self._to_room(old_room, "leave", key, exclude=(session,), extra={"actor": session.name},
                          actor=session.name, place=new_loc["ref"])
        if not new_loc.get("private"):
            key = "arrive_from_cabin" if came_from.get("private") else "arrive_from"
            self._to_room(self.room_of(char), "arrive", key, exclude=(session,),
                          extra={"actor": session.name}, actor=session.name, place=came_from["ref"])
        via = [self.world.locations[p]["ref"] for p in path[1:-1]]
        line = self.render(lang, "moved_via" if via else "moved", place=new_loc["ref"], via=via)
        first = dest not in session.visited
        session.visited.add(dest)
        self._send(session, "moved", text=f"{line} {self.look_text(session, full=first)}",
                   extra=self._where(session))

    # --- talking --------------------------------------------------------------------

    def cmd_say(self, session, message):
        words = self._chat_text(session, self._arg(message))
        if words is None:
            return
        room = self.room_of(session.char)
        others = self._in_room(room, exclude=(session,))
        for other in others:
            self._send(other, "say", "say_other", extra={"actor": session.name}, actor=session.name,
                       words=words)
        if others:
            self._send(session, "said", "say_self", brief="brief_said", words=words)
        else:
            self._send(session, "said", "say_alone", brief="brief_said_alone", words=words)

    def cmd_whisper(self, session, message):
        name = self._arg(message, "to", 40)
        target = self._find_session(name) if name else None
        if target is None:
            self._error(session, "no_player", name=name or "?")
            return
        if target is session:
            self._error(session, "whisper_yourself")
            return
        if target.conn is None:
            self._error(session, "player_away", name=target.name)
            return
        words = self._chat_text(session, self._arg(message))
        if words is None:
            return
        self._send(target, "whisper", "whisper_other", extra={"actor": session.name},
                   actor=session.name, words=words)
        self._send(session, "whispered", "whisper_self", brief="brief_whispered", name=target.name,
                   words=words)

    def cmd_shout(self, session, message):
        if self._muted(session):
            return
        text = orbit_safety.tidy(self._arg(message), self.config["say_limit"])
        if not text:
            self._error(session, "say_what")
            return
        if not session.shout.take():
            self._error(session, "shout_wait", time=self._duration(session.lang,
                                                                   session.shout.wait_seconds()))
            return
        words = self.filter.clean(text)
        for other in list(self.sessions.values()):
            if other is not session:
                self._send(other, "shout", "shout_other", extra={"actor": session.name},
                           actor=session.name, words=words)
        self._send(session, "shouted", "shout_self", brief="brief_shouted", words=words)

    def cmd_emote(self, session, message):
        emote = self.world.emotes.get(self._arg(message, "e", 20))
        if emote is None:
            self._error(session, "no_emote")
            return
        if self._muted(session):
            return
        target_name = self._arg(message, "to", 40)
        target = None
        if target_name:
            target = self._find_near(session, target_name)
            if target is None:
                self._error(session, "not_here", name=target_name)
                return
        if not session.chat.take():
            self._error(session, "slow_down")
            return
        actor = session.name
        room = self.room_of(session.char)
        extra = {"actor": actor}
        if target is None:
            self._send(session, "emote", text=emote[session.lang]["you"])
            for other in self._in_room(room, exclude=(session,)):
                self._send(other, "emote", text=emote[other.lang]["they"].format(actor=actor),
                           extra=extra)
            return
        self._send(session, "emote", text=emote[session.lang]["you_at"].format(target=target.name))
        self._send(target, "emote", text=emote[target.lang]["at_you"].format(actor=actor), extra=extra)
        for other in self._in_room(room, exclude=(session, target)):
            self._send(other, "emote", text=emote[other.lang]["they_at"].format(actor=actor,
                                                                               target=target.name),
                       extra=extra)

    # --- who, you, your things --------------------------------------------------------

    def _whereabouts(self, lang, other):
        loc_id = other.char["location"]
        if loc_id == "shuttle":
            return self.render(lang, "who_flying")
        if loc_id == "cabin":
            return self.render(lang, "who_cabin")
        return pick(self.world.locations[loc_id]["in"], lang)

    def cmd_who(self, session, message):
        lang = session.lang
        entries = []
        for other in sorted(self.sessions.values(), key=lambda s: s.key):
            entry = self.render(lang, "who_entry", name=other.name,
                                job=self.world.job_name(other.char["job"]),
                                where=self._whereabouts(lang, other))
            if other.conn is None:
                entry += self.render(lang, "who_away_suffix")
            entries.append(entry)
        self._send(session, "who", "who", count=len(entries), people="; ".join(entries))

    def _things(self, char):
        """What a character carries, as {"en","id"} phrases."""
        things = []
        for thing_id, n in sorted(char["inventory"].items()):
            if n <= 0:
                continue
            if thing_id in self.world.goods:
                things.append(self.world.count_of(self.world.goods, thing_id, n))
            elif thing_id in self.world.items:
                things.append(self.world.count_of(self.world.items, thing_id, n))
        return things

    def cmd_inventory(self, session, message):
        lang, char = session.lang, session.char
        parts = [self.render(lang, "inv_credits", credits=char["credits"],
                             job=self.world.job_name(char["job"]))]
        things = self._things(char)
        parts.append(self.render(lang, "inv_items", items=things) if things
                     else self.render(lang, "inv_empty"))
        active = self._active_mission(char)
        if active:
            mission = self.world.missions[active]
            parts.append(self.render(lang, "inv_mission", title=self._mission_title(active),
                                     have=char["inventory"].get(mission["item"], 0),
                                     need=mission["count"]))
        self._send(session, "info", text=" ".join(parts))

    def cmd_give(self, session, message):
        char, lang = session.char, session.lang
        target_name = self._arg(message, "to", 40)
        target = self._find_near(session, target_name) if target_name else None
        if target is None:
            self._error(session, "not_here", name=target_name or "?")
            return
        if target is session:
            self._error(session, "give_self")
            return
        n = self._count(message)
        if n is None:
            self._error(session, "bad_number")
            return
        what = orbit_safety.name_key(self._arg(message, "item", 60)) or "credits"
        if what in CREDIT_WORDS:
            if char["credits"] < n:
                self._error(session, "no_credits", credits=char["credits"])
                return
            char["credits"] -= n
            target.char["credits"] += n
            self._save(session)
            self._save(target)
            self._send(target, "received", "give_credits_other", extra={"actor": session.name},
                       actor=session.name, n=n, credits=target.char["credits"])
            self._send(session, "gave", "give_credits_self", name=target.name, n=n,
                       credits=char["credits"])
            return
        thing = self.world.find_good(what) or self.world.find_item(what)
        if thing is None:
            self._error(session, "no_item", what=what)
            return
        have = char["inventory"].get(thing, 0)
        table = self.world.goods if thing in self.world.goods else self.world.items
        if not have:
            self._error(session, "dont_have", thing=table[thing]["many"])
            return
        if have < n:
            self._error(session, "not_enough", things=self._count_of(thing, have))
            return
        if thing in self.world.goods and self._goods_count(target.char) + n > self.config["max_goods"]:
            self._error(session, "their_bag_full", name=target.name)
            return
        self._take_away(char, thing, n)
        target.char["inventory"][thing] = target.char["inventory"].get(thing, 0) + n
        self._save(session)
        self._save(target)
        self._send(target, "received", "give_thing_other", extra={"actor": session.name},
                   actor=session.name, things=self._count_of(thing, n))
        self._send(session, "gave", "give_thing_self", name=target.name,
                   things=self._count_of(thing, n))

    def _count_of(self, thing, n):
        table = self.world.goods if thing in self.world.goods else self.world.items
        return self.world.count_of(table, thing, n)

    def _goods_count(self, char):
        return sum(n for gid, n in char["inventory"].items() if gid in self.world.goods)

    @staticmethod
    def _take_away(char, thing, n):
        left = char["inventory"].get(thing, 0) - n
        if left > 0:
            char["inventory"][thing] = left
        else:
            char["inventory"].pop(thing, None)

    def cmd_describe(self, session, message):
        lang = session.lang
        text = orbit_safety.tidy(self._arg(message), self.config["description_limit"])
        if not text:
            current = session.char["description"]
            self._send(session, "info", "describe_show" if current else "describe_none",
                       description=current)
            return
        if self._muted(session):
            return
        session.char["description"] = self.filter.clean(text)
        self._save(session)
        self._send(session, "info", "describe_set", description=session.char["description"])

    # --- jobs -----------------------------------------------------------------------

    def cmd_work(self, session, message):
        char, lang = session.char, session.lang
        job = char["job"]
        if char["location"] == "shuttle":
            self._error(session, "in_flight")
            return
        if job == "engineer":
            self._work_repair(session)
        elif job == "pilot":
            self._work_flight(session)
        elif job == "trader":
            self._work_trade(session)
        else:
            self._send(session, "info", "work_none", job=self.world.job_name(job))

    def _work_place(self, session, place):
        if session.char["location"] != place:
            self._error(session, "work_where", where=self.world.locations[place]["in"])
            return False
        return True

    def _check_cooldown(self, session, name):
        left = self._cooldown_left(session.char, name)
        if left > 0:
            self._error(session, "work_cooldown", time=self._duration(session.lang, left))
            return False
        return True

    def _work_repair(self, session):
        if not self._work_place(session, "engineering"):
            return
        stats = session.char["stats"]
        if session.task:
            codes = session.task["codes"]
            self._send(session, "tones", "repair_again", codes=", ".join(map(str, codes)),
                       extra={"codes": codes})
            return
        if not self._check_cooldown(session, "repair"):
            return
        level = max(REPAIR_MIN, min(REPAIR_MAX, int(stats.get("repair_level", REPAIR_MIN))))
        codes = [self.rng.randint(1, 4) for _ in range(level)]
        session.task = {"codes": codes, "deadline": self.now() + 20 + 4 * level}
        self._send(session, "tones", "repair_start", n=level, codes=", ".join(map(str, codes)),
                   extra={"codes": codes})

    def cmd_answer(self, session, message):
        task = session.task
        if not task:
            self._error(session, "answer_nothing")
            return
        digits = [int(d) for d in re.findall(r"\d", self._arg(message, "a", 60))]
        char, lang = session.char, session.lang
        stats = char["stats"]
        level = len(task["codes"])
        session.task = None
        if digits == task["codes"]:
            pay = 10 + 10 * level
            char["credits"] += pay
            stats["repair_level"] = min(REPAIR_MAX, level + 1)
            stats["repairs"] = int(stats.get("repairs", 0)) + 1
            self._set_cooldown(char, "repair", self.config["engineer_cooldown"])
            self._save(session)
            self._send(session, "paid", "repair_ok", pay=pay, credits=char["credits"],
                       time=self._duration(lang, self.config["engineer_cooldown"]))
        else:
            stats["repair_level"] = max(REPAIR_MIN, level - 1)
            self._set_cooldown(char, "repair", self.config["engineer_fail_cooldown"])
            self._save(session)
            self._send(session, "failed", "repair_wrong", codes=", ".join(map(str, task["codes"])),
                       time=self._duration(lang, self.config["engineer_fail_cooldown"]))

    def _work_flight(self, session):
        if not self._work_place(session, "dock"):
            return
        if not self._check_cooldown(session, "flight"):
            return
        char = session.char
        now = self.now()
        seconds = self.config["flight_seconds"]
        char["stats"]["flight"] = {"arrive": now + seconds, "half": now + seconds / 2.0,
                                   "half_said": False}
        dock_room = self.room_of(char)
        char["location"] = "shuttle"
        self._save(session)
        self._to_room(dock_room, "leave", "flight_depart_other", exclude=(session,),
                      extra={"actor": session.name}, actor=session.name)
        self._send(session, "flight", "flight_depart", time=self._duration(session.lang, seconds),
                   extra=dict(self._where(session), sound="launch"))

    def _settle_flight(self, session, on_join=False):
        """Land a cargo run that has arrived: pay, and back to the Dock. Returns
        the line said when this happened while the player was away."""
        char = session.char
        flight = char["stats"].get("flight")
        if not flight:
            if char["location"] == "shuttle":
                char["location"] = "dock"
            return ""
        if self.now() < float(flight.get("arrive", 0)):
            return ""
        pay = 70 + self.rng.randint(0, 30)
        char["credits"] += pay
        char["stats"].pop("flight", None)
        char["stats"]["flights"] = int(char["stats"].get("flights", 0)) + 1
        char["location"] = "dock"
        self._set_cooldown(char, "flight", self.config["pilot_cooldown"])
        self._save(session)
        lang = session.lang
        if on_join:
            return self.render(lang, "flight_settled", pay=pay, credits=char["credits"])
        self._send(session, "paid", text=self.render(lang, "flight_arrive", pay=pay,
                                                     credits=char["credits"],
                                                     time=self._duration(lang, self.config["pilot_cooldown"]))
                   + " " + self.look_text(session, full=False),
                   extra=dict(self._where(session), sound="landing"))
        self._to_room(self.room_of(char), "arrive", "flight_back_other", exclude=(session,),
                      extra={"actor": session.name}, actor=session.name)
        return ""

    def _work_trade(self, session):
        lang = session.lang
        ratios = {gid: self.market.prices[gid] / good["base"] for gid, good in self.world.goods.items()}
        cheap = min(ratios, key=ratios.get)
        dear = max(ratios, key=ratios.get)
        parts = [self.render(lang, "trader_intro")]
        if ratios[cheap] < 0.97:
            parts.append(self.render(lang, "trader_cheap", good=self.world.goods[cheap]["many"],
                                     pct=int(round((1 - ratios[cheap]) * 100))))
        if ratios[dear] > 1.03:
            parts.append(self.render(lang, "trader_dear", good=self.world.goods[dear]["many"],
                                     pct=int(round((ratios[dear] - 1) * 100))))
        if len(parts) == 1:
            parts.append(self.render(lang, "trader_calm"))
        self._send(session, "info", text=" ".join(parts))

    # --- the market -----------------------------------------------------------------

    def _at_market(self, session):
        if not self._loc(session.char).get("market"):
            market = next(lid for lid, loc in self.world.locations.items() if loc.get("market"))
            self._error(session, "market_where", where=self.world.locations[market]["in"])
            return False
        return True

    def cmd_prices(self, session, message):
        lang, job = session.lang, session.char["job"]
        entries = []
        for gid, good in self.world.goods.items():
            entries.append(self.render(lang, "price_entry", good=good["one"],
                                       buy=self.market.unit_price(gid, job, "buy"),
                                       sell=self.market.unit_price(gid, job, "sell")))
        key = "prices_trader" if job == "trader" else "prices"
        self._send(session, "info", key, entries="; ".join(entries))

    def _good_and_count(self, session, message, allow_all=False):
        good = self.world.find_good(self._arg(message, "item", 60))
        if good is None:
            self._error(session, "no_good", what=self._arg(message, "item", 60) or "?")
            return None, None
        if allow_all and message.get("n") == "all":
            return good, session.char["inventory"].get(good, 0) or None
        n = self._count(message, high=self.config["max_goods"])
        if n is None:
            self._error(session, "bad_number")
        return good, n

    def cmd_buy(self, session, message):
        if not self._at_market(session):
            return
        good, n = self._good_and_count(session, message)
        if n is None:
            return
        char, lang = session.char, session.lang
        if self._goods_count(char) + n > self.config["max_goods"]:
            self._error(session, "bag_full", max=self.config["max_goods"])
            return
        total = self.market.quote(good, char["job"], "buy", n)
        if total > char["credits"]:
            self._error(session, "buy_poor", total=total, credits=char["credits"])
            return
        char["credits"] -= total
        char["inventory"][good] = char["inventory"].get(good, 0) + n
        self.market.trade(good, "buy", n)
        self._save(session)
        self._send(session, "trade", "buy_ok", things=self._count_of(good, n), total=total,
                   credits=char["credits"])

    def cmd_sell(self, session, message):
        if not self._at_market(session):
            return
        good, n = self._good_and_count(session, message, allow_all=True)
        if good is None:
            return
        char = session.char
        have = char["inventory"].get(good, 0)
        if not have:
            self._error(session, "sell_none", thing=self.world.goods[good]["many"])
            return
        if n is None:
            return
        if n > have:
            self._error(session, "not_enough", things=self._count_of(good, have))
            return
        total = self.market.quote(good, char["job"], "sell", n)
        char["credits"] += total
        self._take_away(char, good, n)
        self.market.trade(good, "sell", n)
        self._save(session)
        self._send(session, "trade", "sell_ok", things=self._count_of(good, n), total=total,
                   credits=char["credits"])

    # --- missions -------------------------------------------------------------------

    def board(self, day=None):
        """Today's missions (ids), the same for everyone."""
        day = day or self.today()
        ids = sorted(self.world.missions)
        rng = random.Random(f"{day}:{self.store.get_meta('secret_salt', '')}")
        rng.shuffle(ids)
        return ids[:max(1, int(self.config["missions_per_day"]))]

    def _mission_state(self, char):
        state = char["stats"].get("missions")
        if not isinstance(state, dict):
            state = {}
        today = self.today()
        if state.get("day") != today:
            state = {"day": today, "done": [], "active": state.get("active")}
        char["stats"]["missions"] = state
        return state

    def _active_mission(self, char):
        active = self._mission_state(char).get("active")
        return active if active in self.world.missions else None

    def _mission_title(self, mid):
        m = self.world.missions[mid]
        return {lang: self.render(lang, "mission_title",
                                  things=pick(self.world.count_of(self.world.items, m["item"], m["count"]), lang),
                                  source=pick(self.world.locations[m["from"]]["ref"], lang),
                                  dest=pick(self.world.locations[m["to"]]["ref"], lang))
                for lang in orbit_lang.LANGUAGES}

    def cmd_missions(self, session, message):
        lang = session.lang
        state = self._mission_state(session.char)
        entries = []
        for number, mid in enumerate(self.board(), 1):
            mark = ""
            if mid == state.get("active"):
                mark = self.render(lang, "mission_mark_active")
            elif mid in state.get("done", []):
                mark = self.render(lang, "mission_mark_done")
            entries.append(self.render(lang, "mission_entry", number=number,
                                       title=self._mission_title(mid),
                                       reward=self.world.missions[mid]["reward"], mark=mark))
        self._send(session, "info", "missions_board", entries="; ".join(entries))

    def cmd_accept(self, session, message):
        board = self.board()
        n = self._count(message, default=None, high=len(board))
        if n is None:
            self._error(session, "mission_number", count=len(board))
            return
        state = self._mission_state(session.char)
        mid = board[n - 1]
        if state.get("active"):
            self._error(session, "mission_busy", title=self._mission_title(state["active"]))
            return
        if mid in state.get("done", []):
            self._error(session, "mission_done_already")
            return
        state["active"] = mid
        self._save(session)
        m = self.world.missions[mid]
        self._send(session, "mission", "mission_accepted", title=self._mission_title(mid),
                   where=self.world.locations[m["from"]]["in"])

    def cmd_take(self, session, message):
        char = session.char
        text = self._arg(message, "item", 60) or self._arg(message)
        item = self.world.find_item(text)
        if item is None:
            if self.world.find_good(text):
                self._error(session, "take_buy")
            else:
                self._error(session, "take_nothing", what=text or "?")
            return
        active = self._active_mission(char)
        mission = self.world.missions.get(active) if active else None
        if mission is None or mission["item"] != item:
            self._error(session, "take_no", thing=self.world.items[item]["many"])
            return
        if char["location"] != mission["from"]:
            self._error(session, "take_where", thing=self.world.items[item]["many"],
                        where=self.world.locations[mission["from"]]["in"])
            return
        have = char["inventory"].get(item, 0)
        need = mission["count"] - have
        if need <= 0:
            self._error(session, "take_enough", place=self.world.locations[mission["to"]]["ref"])
            return
        n = self._count(message, default=need, high=100) or need
        n = min(n, need)
        char["inventory"][item] = have + n
        self._save(session)
        self._send(session, "mission", "take_ok", things=self._count_of(item, n), have=have + n,
                   need=mission["count"], place=self.world.locations[mission["to"]]["ref"])

    def cmd_complete(self, session, message):
        char = session.char
        active = self._active_mission(char)
        if not active:
            self._error(session, "mission_none")
            return
        mission = self.world.missions[active]
        if char["location"] != mission["to"]:
            self._error(session, "complete_where", place=self.world.locations[mission["to"]]["ref"])
            return
        have = char["inventory"].get(mission["item"], 0)
        if have < mission["count"]:
            self._error(session, "complete_missing", have=have, need=mission["count"],
                        where=self.world.locations[mission["from"]]["in"])
            return
        self._take_away(char, mission["item"], mission["count"])
        state = self._mission_state(char)
        state["active"] = None
        state.setdefault("done", []).append(active)
        char["stats"]["missions_done"] = int(char["stats"].get("missions_done", 0)) + 1
        char["credits"] += mission["reward"]
        self._save(session)
        self._send(session, "paid", "mission_complete", title=self._mission_title(active),
                   pay=mission["reward"], credits=char["credits"])

    def cmd_abandon(self, session, message):
        char = session.char
        active = self._active_mission(char)
        if not active:
            self._error(session, "mission_none")
            return
        char["inventory"].pop(self.world.missions[active]["item"], None)
        self._mission_state(char)["active"] = None
        self._save(session)
        self._send(session, "mission", "mission_abandoned", title=self._mission_title(active))

    # --- guessing what a plain word meant ----------------------------------------------

    def cmd_text(self, session, message):
        text = self._arg(message)
        if not text:
            self._error(session, "unknown_command")
            return
        if self.world.find_location(text):
            self.cmd_go(session, {"a": text})
        elif self._find_near(session, text) or self.world.find_object(session.char["location"], text)[1]:
            self.cmd_look(session, {"a": text})
        else:
            self._error(session, "unknown_text", what=text[:60])

    def cmd_help(self, session, message):
        self._send(session, "info", "help")

    # --- admin ----------------------------------------------------------------------

    def cmd_admin(self, session, message):
        if not self.is_admin(session):
            self._error(session, "not_admin")
            return
        op = self._arg(message, "op", 20)
        if op == "announce":
            text = orbit_safety.tidy(self._arg(message), self.config["say_limit"])
            if not text:
                self._error(session, "say_what")
                return
            for other in list(self.sessions.values()):
                self._send(other, "announce", "announce", words=text)
            logger.info("admin %s: announce", session.name)
            return
        name = self._arg(message, "to", 40)
        target = self._find_session(name)
        char = target.char if target else self.store.by_name(orbit_safety.name_key(name))
        if char is None:
            self._error(session, "no_player", name=name or "?")
            return
        lang = session.lang
        if op == "mute":
            minutes = self._count(message, default=10, high=24 * 60) or 10
            char["muted_until"] = self.now() + minutes * 60
            self._save(char)
            if target:
                self._send(target, "system", "muted_you", time=self._duration(target.lang, minutes * 60))
            done = self.render(lang, "admin_muted", name=char["name"],
                               time=self._duration(lang, minutes * 60))
        elif op == "unmute":
            char["muted_until"] = 0
            self._save(char)
            if target:
                self._send(target, "system", "unmuted_you")
            done = self.render(lang, "admin_unmuted", name=char["name"])
        elif op == "kick":
            if target is None or target.conn is None:
                self._error(session, "player_away", name=char["name"])
                return
            self._kick(target, "kicked_you", CLOSE_KICKED)
            done = self.render(lang, "admin_kicked", name=char["name"])
        elif op == "ban":
            char["banned"] = 1
            if target is not None and target.conn is not None:
                ip_hash = getattr(target.conn, "ip_hash", None)
                if ip_hash:
                    self.store.ban_ip(ip_hash, self.config["ban_ip_days"] * 86400)
                    char["stats"]["ban_ip"] = ip_hash
            self._save(char)
            if target is not None:
                self._kick(target, "banned_you", CLOSE_BANNED)
            done = self.render(lang, "admin_banned", name=char["name"])
        elif op == "unban":
            char["banned"] = 0
            ip_hash = char["stats"].pop("ban_ip", None)
            if ip_hash:
                self.store.unban_ip(ip_hash)
            self._save(char)
            done = self.render(lang, "admin_unbanned", name=char["name"])
        else:
            self._error(session, "unknown_command")
            return
        logger.info("admin %s: %s %s", session.name, op, char["name"])
        self._send(session, "info", text=done)

    def _kick(self, target, key, code):
        self._send(target, "system", key)
        conn = target.conn
        target.conn = None
        if conn is not None:
            conn.session = None
            conn.close(code, key)
        self._remove(target)

    COMMANDS = {
        "look": cmd_look, "go": cmd_go, "say": cmd_say, "whisper": cmd_whisper,
        "shout": cmd_shout, "emote": cmd_emote, "who": cmd_who, "inventory": cmd_inventory,
        "give": cmd_give, "describe": cmd_describe, "work": cmd_work, "answer": cmd_answer,
        "prices": cmd_prices, "buy": cmd_buy, "sell": cmd_sell, "missions": cmd_missions,
        "accept": cmd_accept, "take": cmd_take, "complete": cmd_complete,
        "abandon": cmd_abandon, "text": cmd_text, "help": cmd_help, "admin": cmd_admin,
    }

    # ------------------------------------------------------------------ time passing

    def tick(self):
        now = self.now()
        self.market.tick(now)
        for session in list(self.sessions.values()):
            task = session.task
            if task and now > task["deadline"]:
                session.task = None
                session.char["stats"]["repair_level"] = max(
                    REPAIR_MIN, int(session.char["stats"].get("repair_level", REPAIR_MIN)) - 1)
                self._set_cooldown(session.char, "repair", self.config["engineer_fail_cooldown"])
                self._save(session)
                self._send(session, "failed", "repair_late",
                           time=self._duration(session.lang, self.config["engineer_fail_cooldown"]))
            flight = session.char["stats"].get("flight")
            if flight:
                if not flight.get("half_said") and now >= float(flight.get("half", 0)):
                    flight["half_said"] = True
                    self._send(session, "flight", "flight_half")
                if now >= float(flight.get("arrive", 0)):
                    self._settle_flight(session)
            if session.conn is None and session.dropped_at is not None and \
                    now - session.dropped_at >= self.config["linkdead_seconds"]:
                logger.info("%s left", session.name)
                self._remove(session)

    def shutdown(self):
        """The server is stopping: say so, and save everyone."""
        for session in list(self.sessions.values()):
            self._send(session, "system", "server_restart")
            self._save(session)
        self.market.save()
