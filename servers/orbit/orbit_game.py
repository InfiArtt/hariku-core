# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The game: joining, commands, talking, and time passing, with no network
code. orbit_server.py hands it connections and messages; the tests hand it
fakes. The rest of the game is in mixins, one file each:

  orbit_nav.py    walking by compass, the way to places, maps, the dark,
                  locks, air outside, the Wombat shuttle, cabins and visits
  orbit_items.py  things: the shops, using, wearing, examining; pets
  orbit_work.py   jobs and their mini-games, XP and levels, missions, the
                  daily bonus
  orbit_econ.py   the markets, the farm, mining and salvage, your profile
  orbit_here.py   "x here": what can be done in this room, and with someone or something
  orbit_social.py postures (sit, lie, sleep, stand), following and leading, exits and
                  peering, gestures in your own words, dice, the time, being away,
                  the rooms' own lines
  orbit_floor.py  things put down, picked up, put on a table, thrown and caught
  orbit_pastimes.py  the jukebox and the fishing pond
  orbit_admin.py  moving a character to another computer; admin commands

A connection ("conn") is anything with send(dict), close(code, reason), a
`lang` (always "en": Orbit is played in English), an `ip_hash` (or None) and a
`session` attribute the game sets. The game answers with messages (see the
protocol in README.md):

  {"t": "welcome", "name", "job", "new", "resumed", "credits", "room", "amb"}
  {"t": "ev", "k": kind, "text": line, ...}      every event, in English
  {"t": "err", "code", "text", "fatal"}          a hello that can't join

An event's "k" (kind) tells the client which sound fits and whose voice
reads it; "sound" (a newer, more specific cue), "dir" (the way you walked),
"voice" (the voice a speaker chose) and other fields are optional, and
Orbit 1.0's client ignores what it doesn't know.

Players stay "link-dead" for a minute after their connection drops, so a
reconnect resumes them quietly. Everything that matters is saved in SQLite
(orbit_store) as it changes; the server decides everything.
"""

import datetime
import logging
import math
import random
import re
import time

import orbit_earth
import orbit_hunt
import orbit_lang
import orbit_npcs
import orbit_safety
import orbit_verbs
import orbit_world
from orbit_admin import AdminMixin
from orbit_casino import CasinoMixin
from orbit_econ import EconomyMixin
from orbit_family import FamilyMixin
from orbit_events import EventsMixin
from orbit_floor import FloorMixin
from orbit_here import HERE_WORDS, HereMixin
from orbit_hunt import HuntMixin
from orbit_arcade import ArcadeMixin, client_version
from orbit_crews import CrewsMixin
from orbit_duels import DuelsMixin
from orbit_items import ItemsMixin
from orbit_lang import pick
from orbit_local import LocalMixin
from orbit_nav import NavMixin
from orbit_npcs import NpcsMixin
from orbit_pastimes import PastimesMixin
from orbit_pets import PetsMixin
from orbit_progress import ProgressMixin
from orbit_social import SocialMixin
from orbit_trade import TradeMixin
from orbit_travel import TravelMixin
from orbit_weddings import WeddingsMixin
from orbit_work import WorkMixin

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
    "work_cooldown": 120,          # scientists and security officers
    "work_fail_cooldown": 30,
    "missions_per_day": 3,
    "say_limit": 300,
    "description_limit": 160,
    "chat_rate": 1.0,             # say, whisper and emote: a second apart on average...
    "chat_burst": 5,              # ...with this many in a quick row
    "shout_seconds": 10,          # a shout at most every 10 seconds
    "econ_rate": 1.0,             # farming, mining, buying, using things: a second apart...
    "econ_burst": 6,              # ...with this many in a quick row
    "max_goods": 20,              # how many goods fit in your bag (a bigger bag: more)
    "ban_ip_days": 7,
    "transfer_minutes": 10,       # a transfer code works this long...
    "transfer_tries": 5,          # ...and an address may get it wrong this often...
    "transfer_window": 900,       # ...in this many seconds
    "reserved_names": ["admin", "administrator", "system", "server", "orbit", "hariku", "aruna",
                       "captain", "kapten", "moderator", "semua", "everyone", "all", "anyone",
                       "someone", "nobody", "you", "kamu", "aku", "saya", "me", "credits",
                       "kredit"],
}

TALK_KINDS = ("say", "whisper", "shout")
# Clients from this version show a reply's lines one by one (the "lines" of an event).
LINES_CLIENT = (1, 6)
# What's new, said once to a returning player: each version's note, and the notes since theirs.
NEWS = (("1.1", "whats_new"), ("1.2", "whats_new_12"), ("1.3", "whats_new_13"), ("1.4", "whats_new_14"),
        ("1.5", "whats_new_15"), ("1.6", "whats_new_16"))
SEEN_VERSION = NEWS[-1][0]


class Session:
    """A character in play (online, or link-dead for a moment)."""

    def __init__(self, char, conn, config, clock):
        self.char = char
        self.conn = conn
        self.lang = getattr(conn, "lang", "en")
        self.dropped_at = None
        self.visited = set()      # rooms seen this session (the first look is the full one)
        self.task = None          # a work mini-game in progress
        self.invites = {}         # who may visit your cabin: name key -> until
        self.invisible = False    # an admin nobody sees
        self.away = False         # the player's window is hidden and they've been quiet
        self.blackjack = None     # a hand at the casino's card table
        self.earned = None        # the achievements they have (read when first needed)
        self.hunt_test = False    # an admin playing the hunt without it counting
        self.arcade = None        # a game at one of Pixel Pier's cabinets
        self.guide = None         # the way being guided, step by step: {"dest", "path"} (orbit_nav)
        self.guide_told = False   # the guide's how-to said once this session
        self.client = (0, 0)      # the client's version ("Hariku Orbit 1.1": (1, 1))
        self.pose = None          # sitting, lying or asleep (orbit_social); None: standing
        self.afk = None           # away from the keyboard: the note left ("" for none); None: here
        self.leader = None        # the name key of the player this one follows (orbit_social)
        self.fishing = None       # a line in the pond (orbit_pastimes)
        self.last_command = None  # what "again" repeats
        self.chat = orbit_safety.TokenBucket(config["chat_rate"], config["chat_burst"], clock)
        self.shout = orbit_safety.TokenBucket(1.0 / max(1, config["shout_seconds"]), 1, clock)
        self.econ = orbit_safety.TokenBucket(config["econ_rate"], config["econ_burst"], clock)

    @property
    def name(self):
        return self.char["name"]

    @property
    def key(self):
        return self.char["name_key"]


MIXINS = (NavMixin, ItemsMixin, WorkMixin, EconomyMixin, CasinoMixin, TradeMixin, ProgressMixin,
          TravelMixin, LocalMixin, EventsMixin, HuntMixin, ArcadeMixin, CrewsMixin, DuelsMixin, NpcsMixin,
          PetsMixin, FamilyMixin, WeddingsMixin, SocialMixin, FloorMixin, PastimesMixin, HereMixin, AdminMixin)


class Game(NavMixin, ItemsMixin, WorkMixin, EconomyMixin, CasinoMixin, TradeMixin, ProgressMixin,
           TravelMixin, LocalMixin, EventsMixin, HuntMixin, ArcadeMixin, CrewsMixin, DuelsMixin, NpcsMixin,
           PetsMixin, FamilyMixin, WeddingsMixin, SocialMixin, FloorMixin, PastimesMixin, HereMixin, AdminMixin):
    def __init__(self, world, store, texts, config=None, word_filter=None, clock=time.time,
                 rng=None):
        self.world = world
        self.econ = world.economy
        self.store = store
        self.texts = texts
        self.config = dict(GAME_DEFAULTS)
        self.config.update(config or {})
        self.filter = word_filter or orbit_safety.WordFilter()
        self.clock = clock
        self.rng = rng or random.Random()
        self.sessions = {}                # name key -> Session
        self.admins = {orbit_safety.name_key(n) for n in self.config["admins"]}
        self.reserved = set(self.config["reserved_names"])
        for loc in world.locations.values():
            for lang in orbit_lang.LANGUAGES:
                self.reserved.update(w for w in loc.get("aliases", {}).get(lang, []) if " " not in w)
        self.reserved.update(world.emotes)
        for nid, npc in ((world.npcs or {}).get("npcs") or {}).items():     # the residents' own names
            self.reserved.add(nid)
            self.reserved.update(orbit_safety.name_key(w) for w in str(npc.get("name") or "").split())
            for lang in orbit_lang.LANGUAGES:
                first = (npc.get("names", {}).get(lang) or [""])[0]
                self.reserved.update(orbit_safety.name_key(w) for w in first.split())
        self.transfer_fails = {}          # address hash -> [times]: wrong transfer codes
        self.offers = {}                  # name key -> the trade offered to them
        self.challenges = {}              # name key -> the coin flip they're challenged to
        self._lottery = None              # the lottery's state (meta "lottery"), when read
        self.init_economy()
        self.init_travel()
        self.init_events()
        self.market.event_factor = self.event_price_factor
        self.init_hunt()
        self.init_crews()
        self.init_duels()
        self.init_family()
        self.init_weddings()
        self.init_npcs()
        self.init_social()
        self.init_floor()
        self.init_pastimes()

    # ------------------------------------------------------------------ helpers

    def now(self):
        return self.clock()

    def render(self, lang, key, **params):
        return self.texts.render(lang, key, **params)

    def _send(self, session, kind, key=None, text=None, brief=None, extra=None, **params):
        """One event to one player. Nothing for a link-dead one. A reply of several lines
        (joined with "\\n") goes as one line in "text" to everyone, and, to a client from 1.6,
        as its lines too ("lines"), to show one by one."""
        conn = session.conn
        if conn is None:
            return
        lang = session.lang
        if text is None:
            text = self.render(lang, key, **params)
        message = {"t": "ev", "k": kind, "text": text}
        if "\n" in text:
            lines = orbit_lang.lines_of(text)
            message["text"] = orbit_lang.one_line(lines)
            if len(lines) > 1 and tuple(session.client) >= LINES_CLIENT:
                message["lines"] = lines
        if brief:
            message["brief"] = self.render(lang, brief, **params)
        if extra:
            message.update(extra)
        conn.send(message)

    def _error(self, session, key, sound=None, **params):
        self._send(session, "error", key, extra={"sound": sound} if sound else None, **params)

    def _info(self, session, key=None, text=None, sound=None, **params):
        self._send(session, "info", key, text=text, extra={"sound": sound} if sound else None, **params)

    def room_of(self, char):
        loc = char["location"]
        if self.world.locations.get(loc, {}).get("private"):
            return f"{loc}:{char['stats'].get('visit') or char['name_key']}"
        return loc

    def _in_room(self, room, exclude=(), visible=False):
        skip = {id(s) for s in exclude}
        return [s for s in self.sessions.values()
                if self.room_of(s.char) == room and id(s) not in skip
                and not (visible and s.invisible)]

    def _to_room(self, room, kind, key, exclude=(), extra=None, **params):
        for other in self._in_room(room, exclude):
            self._send(other, kind, key, extra=extra, **params)

    def _to_all(self, kind, key, exclude=(), extra=None, **params):
        skip = {id(s) for s in exclude}
        for other in list(self.sessions.values()):
            if id(other) not in skip:
                self._send(other, kind, key, extra=extra, **params)

    def _loc(self, char_or_id):
        lid = char_or_id if isinstance(char_or_id, str) else char_or_id["location"]
        return self.world.locations[lid]

    def _where(self, session):
        """What is sent with an event that moves you: the room, its ambience,
        and (for the client's footsteps and echo) its floor and acoustics."""
        lid = session.char["location"]
        loc = self.world.locations[lid]
        return {"room": lid, "amb": self.wedding_ambience(session, lid) or loc["ambience"],
                "floor": loc.get("floor", "metal"), "acoustics": loc.get("acoustics", "room")}

    def _find_session(self, name):
        return self.sessions.get(orbit_safety.name_key(name))

    def _find_near(self, session, name):
        """Another player in the same room, by name or the start of it."""
        wanted = orbit_safety.name_key(name)
        if not wanted:
            return None
        here = self._in_room(self.room_of(session.char), exclude=(session,), visible=True)
        for other in here:
            if other.key == wanted:
                return other
        starts = [o for o in here if o.key.startswith(wanted)]
        return starts[0] if len(starts) == 1 else None

    def _char_by_key(self, key):
        """A character by its name key: the one in play if it is, else from the database."""
        session = self.sessions.get(key)
        return session.char if session else self.store.by_name(key)

    def _duration(self, lang, seconds):
        seconds = max(1, int(math.ceil(seconds)))
        if seconds < 90:
            return self.render(lang, "dur_seconds", n=seconds)
        minutes = int(round(seconds / 60.0))
        if minutes < 120:
            return self.render(lang, "dur_minute" if minutes == 1 else "dur_minutes", n=minutes)
        hours = minutes / 60.0
        if hours >= 48:
            return self.render(lang, "dur_days", n=int(round(hours / 24)))
        return self.render(lang, "dur_hours", n=f"{hours:.1f}".rstrip("0").rstrip("."))

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

    def _slow(self, session):
        """False (and "slow down" said) when the player is too quick with the economy."""
        if session.econ.take():
            return True
        self._error(session, "slow_down")
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
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)
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
        didn't, the connection was told why ({"t": "err"}) and closed. Whatever
        language the client asks for, the game speaks English."""
        lang = orbit_lang.language(message.get("lang"))
        conn.lang = lang
        if message.get("t") != "hello" or message.get("v") != PROTOCOL_VERSION:
            return self._refuse(conn, "version")
        if self.store.ip_banned(getattr(conn, "ip_hash", None)):
            return self._refuse(conn, "banned")
        secret_hash = self.store.hash_secret(message.get("secret"))
        if secret_hash is None:
            return self._refuse(conn, "bad_secret")
        new = False
        if message.get("transfer"):
            char = self._redeem_transfer(conn, message.get("transfer"), secret_hash)
            if char is None:
                return False
        else:
            char = self.store.by_secret_hash(secret_hash)
        if char is None:
            old = self.store.old_secret(secret_hash)
            if old is not None:
                return self._refuse(conn, "revoked" if old[1] == "revoked" else "moved")
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
            char["stats"]["seen_version"] = SEEN_VERSION
            new = True
            logger.info("new character %s (%s)", name, job)
        if char["banned"]:
            return self._refuse(conn, "banned")
        char["location"] = self.world.moved.get(char["location"], char["location"])
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
            session.char["secret_hash"] = char["secret_hash"]
        session.lang = lang
        session.client = client_version(message.get("client"))
        conn.session = session
        char = session.char
        conn.send({"t": "welcome", "v": PROTOCOL_VERSION, "name": char["name"], "job": char["job"],
                   "new": new, "resumed": resumed, "credits": char["credits"],
                   "voice": int(char.get("voice") or 0), **self._where(session)})
        if resumed:
            self._send(session, "room", text=self.render(lang, "welcome_resumed") + "\n"
                       + self.look_text(session, full=False), extra=self._where(session))
            logger.info("%s resumed", char["name"])
            return True
        logger.info("%s joined", char["name"])
        greeting = self.render(lang, "welcome_new" if new else "welcome_back", name=char["name"],
                               job=self.world.job_name(char["job"]))
        notes = self.on_join(session, new)
        session.visited.add(char["location"])
        self._remember_room(char, char["location"])
        text = "\n".join(t for t in [greeting] + notes + [self.look_text(session, full=True)] if t)
        self._send(session, "room", text=text, extra=self._where(session))
        self._save(session)
        if not self._loc(char).get("private"):
            self._to_room(self.room_of(char), "arrive", "arrive_new" if new else "arrive_join",
                          exclude=(session,), extra={"actor": char["name"]}, actor=char["name"])
        self.tell_friends(session)
        return True

    def on_join(self, session, new):
        """Lines said when a character comes back (a landed flight, ripe crops...)."""
        char, lang = session.char, session.lang
        notes = []
        notes.append(self._settle_flight(session, on_join=True))
        notes.append(self.settle_ride(session, on_join=True))
        notes.append(self.settle_air(session, on_join=True))
        notes.append(self.settle_travel(session))
        char["stats"].pop("visit", None)          # guests wake up at home
        seen = char["stats"].get("seen_version")
        if not new and seen != SEEN_VERSION:
            char["stats"]["seen_version"] = SEEN_VERSION
            versions = [version for version, _key in NEWS]
            since = versions.index(seen) + 1 if seen in versions else 0     # from Orbit 1.0: all of it
            notes[0:0] = [self.render(lang, key) for _version, key in NEWS[since:]]
        self.give_starter(char)
        notes.extend(self.grant_by_level(session, quiet=True))
        ripe = self.ripe_plots(char)
        if ripe:
            notes.append(self.render(lang, "farm_ripe_join", n=ripe))
        notes.extend(self.pet_join_notes(session))
        notes.extend(self.family_join_notes(session))
        notes.extend(self.wedding_join_notes(session))
        notes.extend(self.festival_join_notes(session))
        if self.daily_ready(char) and not new:
            notes.append(self.render(lang, "daily_ready"))
        notes.extend(self.check_achievements(session, quiet=True))
        return [n for n in notes if n]

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
        self.arcade_finish(session, "left")
        self._save(session)

    def _remove(self, session, key="leave_quit"):
        self.guide_stop(session)
        self.leave_casino(session)
        self.arcade_finish(session, "left")
        self.forget_offers(session)
        self.forget_crew_invites(session)
        self.forget_duels(session)
        self.forget_family_asks(session)
        self.forget_following(session)
        self.forget_airborne(session)
        session.pose = session.afk = session.fishing = None
        self.sessions.pop(session.key, None)
        self._save(session)
        if not self._loc(session.char).get("private") and not session.invisible:
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
        if session.away and command not in ("away", "bye", "status"):
            session.away = False              # any command: back from being away
        if command not in ("away", "bye", "status", "transfer") and \
                not (command == "text" and self.is_again(message)):
            session.last_command = dict(message)
        try:
            if command != "text":
                self.rouse(session, command)
            handler(self, session, message)
            if self.sessions.get(session.key) is session:
                self.check_achievements(session)
        except Exception:
            logger.exception("the command %r failed", command)
            self._error(session, "oops")

    def run(self, session, message):
        """A command made here (from plain text, or one command calling another)."""
        handler = self.COMMANDS.get(message.get("c"))
        if handler is None:
            self._error(session, "unknown_command")
            return
        self.rouse(session, message.get("c"))
        handler(self, session, message)

    # --- looking --------------------------------------------------------------------

    def _earth(self, lang):
        when = datetime.datetime.fromtimestamp(self.now(), datetime.timezone.utc)
        return orbit_earth.describe(self.world.regions, when,
                                    lambda key, **p: self.render(lang, key, **p))

    def _person(self, lang, other):
        name = other.name
        if other.conn is None:
            return self.render(lang, "person_away", name=name, job=self.world.job_name(other.char["job"]))
        if other.away:
            return self.render(lang, "person_idle", name=name, job=self.world.job_name(other.char["job"]))
        return self.render(lang, "person", name=name, job=self.world.job_name(other.char["job"]))

    def look_text(self, session, full=True):
        """What you see, a line each (the Nova Realm way): the room's name; the first time
        you come, or when you look, its description (and the hints for your job); the exits;
        who is here; and the things to look at."""
        lang, char = session.lang, session.char
        loc = self._loc(char)
        lines = [pick(self.cabin_name(session) or loc["name"], lang)]
        if char["location"] == "shuttle":
            flight = char["stats"].get("flight") or {}
            lines.append(pick(loc["desc"], lang))
            lines.append(self.render(lang, "look_in_flight",
                                     time=self._duration(lang, float(flight.get("arrive", 0)) - self.now())))
            return "\n".join(lines)
        if char["location"] == "kancil":
            ride = char["stats"].get("ride") or {}
            lines.append(pick(loc["desc"], lang))
            lines.append(self.render(lang, "look_in_flight",
                                     time=self._duration(lang, float(ride.get("arrive", 0)) - self.now())))
            return "\n".join(lines)
        if char["location"] == "ship":
            return self.ship_look(session)
        if char["location"] == "ferry":
            trip = char["stats"].get("ferry") or {}
            lines.append(pick(loc["desc"], lang))
            if trip.get("to") in self.world.worlds:
                now = self.now()
                key = "ferry_look_waiting" if now < float(trip.get("depart", 0)) else "ferry_look_moving"
                lines.append(self.render(lang, key, place=self.world.worlds[trip["to"]]["ref"],
                                         wait=self._duration(lang, float(trip.get("depart", 0)) - now),
                                         time=self._duration(lang, float(trip.get("arrive", 0)) - now)))
            others = self._in_room(self.room_of(char), exclude=(session,), visible=True)
            if others:
                lines.append(self.render(lang, "look_people", people=[self._person(lang, o) for o in
                                                                      sorted(others, key=lambda o: o.key)]))
            return "\n".join(lines)
        if self.in_the_dark(char):
            lines.append(self.dark_text(session))
            return "\n".join(line for line in lines if line)
        if full:
            lines.append(pick(loc["desc"], lang))
            if loc.get("earth_view"):
                lines.append(self._earth(lang))
            hints = loc.get("hints", {})
            for hint in (hints.get(char["job"]), hints.get("all")):
                if hint:
                    lines.append(pick(hint, lang))
            lines.extend(self.cabin_lines(session))
            lines.extend(self.crew_hangar_lines(session))
        lines.append(self.exits_text(session))
        if loc.get("airless"):
            lines.append(self.air_text(session))
        others = sorted(self._in_room(self.room_of(char), exclude=(session,), visible=True), key=lambda o: o.key)
        residents = self.residents_text(session)
        if others:
            lines.append(self.render(lang, "look_people", people=[self._person(lang, o) for o in others]))
            lines.extend(self.pose_line(lang, o) for o in others)       # "Maya is sitting on a bar stool."
        elif full and not loc.get("private") and not residents:
            lines.append(self.render(lang, "look_alone"))
        if residents:
            lines.append(residents)
        lines.append(self.wedding_decor(session))
        lines.append(self.hunt_mark(session))
        lines.append(self.floor_text(lang, self.room_of(char)))
        if full and loc.get("objects"):
            things = [o["names"][lang][0] for o in loc["objects"].values()]
            lines.append(self.render(lang, "look_objects", things=things))
        mine = self.pose_of(session)
        if mine:
            key = {"sit": "pose_you_sitting", "lie": "pose_you_lying", "sleep": "pose_you_asleep"}[mine["kind"]]
            lines.append(self.render(lang, key, at=self.pose_at(session, mine)))
        return "\n".join(line for line in lines if line)

    def cmd_look(self, session, message):
        target = self._arg(message)
        lang = session.lang
        if not target or orbit_safety.name_key(target) in ("around", "here", "room"):
            session.visited.add(session.char["location"])
            self._send(session, "room", text=self.look_text(session, full=True),
                       extra=self._where(session))
            return
        if orbit_hunt.normalize(target) in orbit_hunt.LOOK_FOR_CLUES:
            self.cmd_investigate(session, message)          # "look for clues" (both clients send look)
            return
        d = self.world.find_direction(target, lang)
        if d:
            self.peek(session, d)
            return
        dark = self.in_the_dark(session.char)
        other = None if dark else self._find_near(session, target)
        if other is not None:
            self._send(session, "info", text=self.player_text(lang, other))
            return
        nid = None if dark else self.npc_here(session, target)
        if nid is not None:
            self._send(session, "info", text=self.npc_look_text(session, nid))
            return
        companion = None if dark else self.companion_look(session, target)
        if companion:
            self._send(session, "info", text=companion)
            return
        oid, obj = self.world.find_object(session.char["location"], target)
        if obj is not None:
            if dark:
                self._error(session, "too_dark_to_see")
                return
            if obj.get("worlds"):
                self.cmd_worlds(session, {})
                return
            if obj.get("arcade"):
                (self.cmd_high_scores if obj["arcade"] == "scores" else self.cmd_arcade)(session, {})
                return
            if obj.get("markets"):
                self.markets_sign(session)
                return
            if obj.get("earth"):
                text = self._earth(lang)
            elif obj.get("farm"):
                text = self.farm_text(session)
            elif obj.get("lanterns"):
                text = pick(obj["desc"], lang) + " " + self.render(lang, "lanterns_today",
                                                                   n=self.lanterns_today())
            else:
                text = pick(obj["desc"], lang)
            self._send(session, "info", text=text or self.render(lang, "look_nothing_special"))
            return
        creature, _here = self.creature_here(session.char, target)
        if creature is not None and not dark:
            self._send(session, "info", text=pick(self.econ["creatures"][creature]["desc"], lang))
            return
        if orbit_safety.name_key(target) in ("me", "myself", "self"):
            description = session.char["description"] or self.render(lang, "describe_none")
            self._send(session, "info", "look_self", rank=self.rank_name(session.char),
                       description=description)
            return
        pile = None if dark else self._pile_named(self.room_of(session.char), target, anywhere=True)
        if pile is not None:                     # something put down here (orbit_floor)
            thing = self.world.things[pile["id"]]
            self._info(session, text="\n".join([pick(thing.get("desc") or thing["one"], lang),
                                                self.render(lang, "floor_look", things=self._count_of(
                                                    pile["id"], pile["n"]), name=pile.get("by_name") or "?")]))
            return
        if self.examine(session, target):
            return
        parsed = orbit_verbs.parse(target, lang, self.world.find_direction)
        if parsed is not None and parsed.get("c") not in ("move", "help"):
            self.run(session, parsed)
            return
        if self._find_session(target) is not None:
            self._error(session, "not_here", name=self._find_session(target).name)
            return
        there = self.object_elsewhere(session.char, target)
        if there is not None:
            self._error(session, "look_what_there", what=target, place=self.world.locations[there]["in"])
            return
        self._error(session, "look_what", what=target)

    def object_elsewhere(self, char, text):
        """The room (on this world, and open to anyone) where a thing to look at by this name is: "read
        logbook" away from the Reading Room says where the books are. None if there's none."""
        index = getattr(self, "_object_rooms", None)
        if index is None:
            index = self._object_rooms = {}
            for lid, loc in self.world.locations.items():
                if any(loc.get(flag) for flag in ("hidden", "secret", "private", "dark", "crew_room")):
                    continue
                for obj in (loc.get("objects") or {}).values():
                    for name in obj["names"]["en"]:
                        index.setdefault(orbit_world.strip_articles(name), []).append(lid)
        here = self.world.world_of(char["location"])
        rooms = [lid for lid in index.get(orbit_world.strip_articles(text), []) if lid != char["location"]]
        rooms = [lid for lid in rooms if self.world.world_of(lid) == here]
        return rooms[0] if len(rooms) == 1 else None

    def player_text(self, lang, other):
        char = other.char
        description = char["description"] or self.render(lang, "look_player_plain")
        parts = [self.render(lang, "look_player", name=other.name, rank=self.rank_name(char))]
        parts.extend(self.appearance(lang, char))
        parts.append(description)
        parts.append(self.pose_line(lang, other))
        return "\n".join(p for p in parts if p)

    # --- talking --------------------------------------------------------------------

    def _voice_extra(self, session, words=None, actor=True):
        """The optional fields of a line someone says: who ("actor"), the voice
        they chose, and the words alone (so a client can read the name in one
        voice and the words in another)."""
        extra = {"actor": session.name} if actor else {}
        if int(session.char.get("voice") or 0) > 0:
            extra["voice"] = int(session.char["voice"])
        if words is not None:
            extra["words"] = words
        return extra

    def _said_to_resident(self, session, text):
        """ "say to Rocco" reaches the server as saying "to Rocco", and "say hi to Rocco" as
        saying "hi to Rocco" (older clients read "say" first): the resident's command."""
        words = [w.strip(".,!?;:") for w in str(text or "").split()]
        low = [w.lower() for w in words]
        if len(words) >= 2 and low[0] in orbit_npcs.TALK_PREFIXES:
            nid = self.npc_here(session, " ".join(words[1:]))
            if nid is not None:
                return {"c": "talk", "to": " ".join(words[1:])}
        for size in (2, 1):
            if len(words) > size + 1 and " ".join(low[:size]) in orbit_npcs.GREETING_WORDS and \
                    low[size] == "to":
                nid = self.npc_here(session, " ".join(words[size + 1:]))
                if nid is not None:
                    return {"c": "greet", "to": " ".join(words[size + 1:])}
        return None

    def _greeting_to_resident(self, session, text):
        """ "hello Rocco", "good morning Amara": a greeting to a resident here."""
        words = [w.strip(".,!?;:") for w in str(text or "").split()]
        low = [w.lower() for w in words]
        for size in (2, 1):
            if len(words) > size and " ".join(low[:size]) in orbit_npcs.GREETING_WORDS:
                rest = words[size:]
                if rest and rest[0].lower() == "to":
                    rest = rest[1:]
                if rest and self.npc_here(session, " ".join(rest)) is not None:
                    return {"c": "greet", "to": " ".join(rest)}
        return None

    def cmd_say(self, session, message):
        resident = self._said_to_resident(session, self._arg(message))
        if resident is not None:
            self.run(session, resident)
            return
        words = self._chat_text(session, self._arg(message))
        if words is None:
            return
        room = self.room_of(session.char)
        self.note_room_chat(session)
        others = self._in_room(room, exclude=(session,))
        for other in others:
            self._send(other, "say", "say_other", extra=self._voice_extra(session, words), actor=session.name,
                       words=words)
        mine = self._voice_extra(session, words, actor=False)
        if [o for o in others if not o.invisible]:
            self._send(session, "said", "say_self", brief="brief_said", words=words, extra=mine)
        else:
            self._send(session, "said", "say_alone", brief="brief_said_alone", words=words, extra=mine)

    def cmd_whisper(self, session, message):
        name = self._arg(message, "to", 40)
        target = self._find_session(name) if name else None
        if target is None and orbit_safety.name_key(name) == "crew" and self.crew_of(session.char)[0]:
            self.cmd_crew_say(session, message)             # "tell crew ...": the crew
            return
        if target is None or (target.invisible and not self.is_admin(session)):
            resident = self.find_npc(name) if name else None
            if resident is not None:
                self._error(session, "npc_whisper", name=self.npc_name(resident))
                return
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
        self._send(target, "whisper", "whisper_other", extra=self._voice_extra(session, words),
                   actor=session.name, words=words)
        self._send(session, "whispered", "whisper_self", brief="brief_whispered", name=target.name,
                   words=words, extra=dict(self._voice_extra(session, words, actor=False), to=target.name))
        if target.afk is not None:
            self._info(session, "whisper_afk_note" if target.afk else "whisper_afk", name=target.name,
                       note=target.afk)

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
                self._send(other, "shout", "shout_other", extra=self._voice_extra(session, words),
                           actor=session.name, words=words)
        self._send(session, "shouted", "shout_self", brief="brief_shouted", words=words,
                   extra=self._voice_extra(session, words, actor=False))

    def cmd_emote(self, session, message):
        emote = self.world.emotes.get(self._arg(message, "e", 20))
        if emote is None:
            self._error(session, "no_emote")
            return
        if self._muted(session):
            return
        target_name = self._arg(message, "to", 40)
        target = None
        eid = self._arg(message, "e", 20)
        if target_name:
            target = self._find_near(session, target_name)
            if target is None:
                resident = self.npc_here(session, target_name)
                if resident is not None:
                    if not session.chat.take():
                        self._error(session, "slow_down")
                        return
                    self.note_room_chat(session)
                    self.npc_emote_at(session, resident, eid, emote)
                    return
                if self.emote_at_companion(session, target_name, eid, emote):
                    return
                self._error(session, "not_here", name=target_name)
                return
        if not session.chat.take():
            self._error(session, "slow_down")
            return
        self.note_room_chat(session)
        actor = session.name
        room = self.room_of(session.char)
        extra = {"actor": actor, "emote": eid}
        mine = {"emote": eid}
        if emote.get("sound"):
            extra["sound"] = mine["sound"] = emote["sound"]
        if target is None:
            self._send(session, "emote", text=emote[session.lang]["you"], extra=mine)
            for other in self._in_room(room, exclude=(session,)):
                self._send(other, "emote", text=emote[other.lang]["they"].format(actor=actor),
                           extra=extra)
            self.companions_join_in(session, eid)
            self.wedding_emote(session, eid)
            return
        self._send(session, "emote", text=emote[session.lang]["you_at"].format(target=target.name),
                   extra=mine)
        self._send(target, "emote", text=emote[target.lang]["at_you"].format(actor=actor), extra=extra)
        for other in self._in_room(room, exclude=(session, target)):
            self._send(other, "emote", text=emote[other.lang]["they_at"].format(actor=actor,
                                                                               target=target.name),
                       extra=extra)
        self.pet_reacts(target, chance=0.3)

    # --- who, you, your things --------------------------------------------------------

    def _whereabouts(self, lang, other):
        loc_id = other.char["location"]
        if loc_id in ("shuttle", "kancil"):
            return self.render(lang, "who_flying" if loc_id == "shuttle" else "who_kancil")
        if loc_id == "cabin":
            return self.render(lang, "who_cabin")
        return pick(self.world.locations[loc_id]["in"], lang)

    def cmd_who(self, session, message):
        lang = session.lang
        entries = []
        for other in sorted(self.sessions.values(), key=lambda s: s.key):
            if other.invisible and other is not session:
                continue
            entry = self.render(lang, "who_entry", name=other.name,
                                job=self.world.job_name(other.char["job"]),
                                where=self._whereabouts(lang, other))
            if other.conn is None:
                entry += self.render(lang, "who_away_suffix")
            elif other.afk is not None:
                entry += self.render(lang, "who_afk_suffix")
            elif other.away:
                entry += self.render(lang, "who_idle_suffix")
            elif (self.pose_of(other) or {}).get("kind") == "sleep":
                entry += self.render(lang, "who_asleep_suffix")
            entries.append(entry)
        self._send(session, "who", "who", count=len(entries), people="\n".join(entries))

    def _things(self, char):
        """What a character carries, as {"en"} phrases (goods and mission things first)."""
        things = []
        for thing_id, n in sorted(char["inventory"].items(),
                                  key=lambda kv: (self.world.things.get(kv[0], {}).get("type") != "good",
                                                  kv[0])):
            if n <= 0 or thing_id not in self.world.things:
                continue
            things.append(self.world.thing_count(thing_id, n))
        return things

    def cmd_inventory(self, session, message):
        lang, char = session.lang, session.char
        parts = [self.render(lang, "inv_credits", credits=char["credits"],
                             job=self.world.job_name(char["job"]))]
        things = self._things(char)
        parts.append(self.render(lang, "inv_items", items="\n".join(pick(t, lang) for t in things)) if things
                     else self.render(lang, "inv_empty"))
        goods = self._goods_count(char)
        if goods:
            parts.append(self.render(lang, "inv_bag", n=goods, max=self.bag_size(char)))
        worn = self.worn_list(char)
        if worn:
            parts.append(self.render(lang, "inv_worn", things=worn))
        active = self._active_mission(char)
        if active:
            mission = self.world.missions[active]
            parts.append(self.render(lang, "inv_mission", title=self._mission_title(active),
                                     have=char["inventory"].get(mission["item"], 0),
                                     need=mission["count"]))
        self._send(session, "info", text="\n".join(parts))

    def cmd_give(self, session, message):
        char = session.char
        target_name = self._arg(message, "to", 40)
        what = orbit_safety.name_key(self._arg(message, "item", 60)) or "credits"
        if orbit_safety.name_key(target_name) in CREDIT_WORDS and what not in CREDIT_WORDS:
            # "give credits Sam 50" read as giving "Sam" to someone called "credits".
            target_name, what = self._arg(message, "item", 60), "credits"
        target = self._find_near(session, target_name) if target_name else None
        if target is None and target_name:
            if self.give_to_companion(session, target_name, message):
                return                           # "feed Kiki", from an older client: a pet or a child
            resident, item_text = self.npc_for_give(session, target_name, self._arg(message, "item", 60))
            if resident is not None:
                n = self._count(message)
                if n is None:
                    self._error(session, "bad_number")
                    return
                self.npc_receive(session, resident, item_text, n)
                return
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
        if what in CREDIT_WORDS:
            if char["credits"] < n:
                self._error(session, "no_credits", credits=char["credits"])
                return
            char["credits"] -= n
            target.char["credits"] += n
            self.store.save_all([char, target.char])
            self._send(target, "received", "give_credits_other", extra={"actor": session.name},
                       actor=session.name, n=n, credits=target.char["credits"])
            self._send(session, "gave", "give_credits_self", name=target.name, n=n,
                       credits=char["credits"])
            return
        thing = self.world.find_good(what) or self.world.find_item(what) or self.world.find_thing(what)
        if thing is None:
            self._error(session, "no_item", what=what)
            return
        info = self.world.things[thing]
        have = char["inventory"].get(thing, 0)
        if not have:
            self._error(session, "dont_have", thing=info["many"])
            return
        if not self._tradeable(thing):
            self._error(session, "cant_give", thing=info["many"])
            return
        if have < n:
            self._error(session, "not_enough", things=self._count_of(thing, have))
            return
        if info["type"] == "good" and self._goods_count(target.char) + n > self.bag_size(target.char):
            self._error(session, "their_bag_full", name=target.name)
            return
        if info.get("unique") and target.char["inventory"].get(thing):
            self._error(session, "they_have_one", name=target.name)
            return
        self._hand_over(char, target.char, (thing, n))
        self.store.save_all([char, target.char])
        self._send(target, "received", "give_thing_other", extra={"actor": session.name},
                   actor=session.name, things=self._count_of(thing, n))
        self._send(session, "gave", "give_thing_self", name=target.name,
                   things=self._count_of(thing, n))

    def _count_of(self, thing, n):
        return self.world.thing_count(thing, n)

    def _goods_count(self, char):
        """The goods in `char`'s bag, and those they put down that nobody picked up (orbit_floor)."""
        return sum(n for gid, n in char["inventory"].items() if gid in self.world.goods) + \
            self.floor_goods_of(char)

    @staticmethod
    def _take_away(char, thing, n):
        left = char["inventory"].get(thing, 0) - n
        if left > 0:
            char["inventory"][thing] = left
        else:
            char["inventory"].pop(thing, None)

    def cmd_describe(self, session, message):
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

    # --- logging out, being away, the status ------------------------------------------------

    def cmd_bye(self, session, message):
        """The player left on purpose: gone at once, not after the link-dead wait."""
        conn = session.conn
        logger.info("%s logged out", session.name)
        self._remove(session, "leave_bye")
        session.conn = None
        if conn is not None:
            conn.session = None
            conn.close(1000, "bye")

    def cmd_away(self, session, message):
        session.away = bool(message.get("on", True))

    def cmd_status(self, session, message):
        lang, char = session.lang, session.char
        area = self.world.area_of(char["location"])
        place = self.cabin_in(session) or self._loc(char)["in"]
        if char["location"] == "cabin" and not char["stats"].get("visit"):
            place = self.render(lang, "who_cabin")
        online = sum(1 for s in self.sessions.values() if s.conn is not None and not s.invisible)
        text = self.render(lang, "status", name=session.name, place=place, deck=area.get("in", ""), n=online)
        if session.away:
            text += "\n" + self.render(lang, "status_away")
        self._info(session, text=text)

    # --- reading plain text ------------------------------------------------------------

    @staticmethod
    def is_again(message):
        """ "again" or "!": the last command once more."""
        return str(message.get("a") or "").strip().lower() in AGAIN_WORDS

    def again(self, session):
        last = session.last_command
        handler = self.COMMANDS.get(last.get("c")) if last else None
        if handler is None:
            self._error(session, "again_none")
            return
        if last.get("c") != "text":
            self.rouse(session, last.get("c"))
        handler(self, session, dict(last))

    def socials(self):
        """{words: gesture id} of the world's gestures ("high five", "hi5"...), for reading plain text."""
        found = getattr(self, "_socials", None)
        if found is None:
            found = {}
            for eid, emote in self.world.emotes.items():
                for words in [eid] + list(emote.get("words") or []):
                    found[tuple(orbit_world.norm(words).split())] = eid
            self._socials = found
        return found

    def cmd_text(self, session, message):
        text = self._arg(message)
        if not text:
            self._error(session, "unknown_command")
            return
        if self.is_again(message):
            self.again(session)
            return
        if text.startswith(":"):
            self.run(session, {"c": "pose", "a": text[1:]})         # ":waves hello"
            return
        if session.arcade and self.arcade_side(session, text):
            return                              # "left!" while dodging meteors
        parsed = orbit_verbs.parse(text, session.lang, self.world.find_direction, self.socials())
        if parsed is not None:
            if parsed.get("c") == "emote" and parsed.get("to") and self._find_near(session, parsed["to"]) is None \
                    and self.npc_here(session, parsed["to"]) is None and self._find_session(parsed["to"]) is None \
                    and not self.companion_look(session, parsed["to"]):
                parsed = None                   # "cry wolf": not a gesture at anyone
        if parsed is not None:
            self.run(session, parsed)
            return
        greeting = self._greeting_to_resident(session, text)
        if greeting is not None:
            self.run(session, greeting)
            return
        if self._find_near(session, text) or self.world.find_object(session.char["location"], text)[1] or \
                self.npc_here(session, text):
            self.cmd_look(session, {"a": text})
        elif self.world.find_location(text):
            self.cmd_go(session, {"a": text})
        elif self.world.find_thing(text, fuzzy=False) and self.examine(session, text):
            pass
        else:
            near = orbit_verbs.near_miss(text, self.socials())
            if near:
                self._error(session, "unknown_text_near", what=text[:60], cmd=near)
            else:
                self._error(session, "unknown_text", what=text[:60])

    HELP_TOPICS = {
        "moving": ("moving", "move", "movement", "walking", "map", "directions", "navigation", "the way",
                   "guide"),
        "talking": ("talking", "talk", "chat", "chatting", "speech"),
        "work": ("work", "job", "jobs", "missions", "mission", "level", "levels"),
        "money": ("money", "credits", "farm", "farming", "mining", "daily", "market", "markets", "prices"),
        "shops": ("shops", "shop", "shopping", "items", "things", "mall", "trade", "trading", "pawn"),
        "casino": ("casino", "gambling", "dice", "slot", "slots", "blackjack", "lottery"),
        "ships": ("ships", "ship", "travel", "worlds", "planets", "planet", "ferry", "gate", "trade runs"),
        "progress": ("progress", "achievements", "leaderboard", "leaderboards", "score", "scores", "rank"),
        "events": ("events", "event", "party", "parties"),
        "hunt": ("hunt", "the hunt", "riddles", "riddle", "chord", "lost chord"),
        "crews": ("crews", "crew", "team", "guild", "clan"),
        "duels": ("duels", "duel", "duels on", "duels off", "arena", "contest"),
        "arcade": ("arcade", "games", "tokens", "token", "tickets", "prizes", "pixel pier", "high scores"),
        "people": ("people", "residents", "resident", "npc", "npcs", "characters"),
        "social": ("social", "socials", "postures", "posture", "sit", "sitting", "sleep", "emote", "emotes",
                   "gestures", "gesture", "follow", "following", "lead", "roll", "dice roll", "afk", "time",
                   "drop", "put", "throw", "room", "exits", "peer", "jukebox", "fishing", "fish"),
        "pets": ("pets", "pet", "tricks"),
        "family": ("family", "partner", "partners", "children", "child", "adopt", "adoption", "baby",
                   "naming"),
        "weddings": ("weddings", "wedding", "marry", "marriage", "propose", "rings", "venue", "venues"),
        "admin": ("admin",),
    }

    def cmd_help(self, session, message):
        topic = orbit_safety.name_key(self._arg(message, "a", 40))
        if topic in HERE_WORDS:
            self.run(session, {"c": "examine", "a": "here"})   # "help here", "commands here": x here
            return
        for name, words in self.HELP_TOPICS.items():
            if topic in words:
                if name == "admin" and not self.is_admin(session):
                    break
                casino = self.econ["casino"]
                text = self.render(session.lang, f"help_{name}", low=casino["min_bet"], high=casino["max_bet"],
                                   limit=casino["hour_limit"])
                if name == "ships":
                    text += "\n" + self.render(session.lang, "help_worlds_work")
                self._send(session, "info", text=text)
                return
        self._send(session, "info", "help")

    # ------------------------------------------------------------------ time passing

    def tick(self):
        now = self.now()
        self.market.tick(now)
        for session in list(self.sessions.values()):
            self.tick_task(session, now)
            flight = session.char["stats"].get("flight")
            if flight:
                if not flight.get("half_said") and now >= float(flight.get("half", 0)):
                    flight["half_said"] = True
                    self._send(session, "flight", "flight_half")
                if now >= float(flight.get("arrive", 0)):
                    self._settle_flight(session)
                    self.check_achievements(session)
            self.tick_session(session, now)
            if session.conn is None and session.dropped_at is not None and \
                    now - session.dropped_at >= self.config["linkdead_seconds"]:
                logger.info("%s left", session.name)
                self._remove(session)
        self.tick_offers(now)
        self.tick_lottery(now)
        self.tick_ships(now)
        self.tick_events(now)
        self.tick_hunt(now)
        self.tick_crews(now)
        self.tick_duels(now)
        self.tick_npcs(now)
        self.tick_family(now)
        self.tick_weddings(now)
        self.tick_social(now)
        self.tick_floor(now)
        self.tick_economy(now)

    def tick_session(self, session, now):
        """Everything that happens to one player as time passes (rides, air, crops, cards)."""
        self.tick_ride(session, now)
        self.tick_air(session, now)
        self.tick_farm(session, now)
        self.tick_invites(session, now)
        self.tick_casino(session, now)
        self.tick_ferry(session, now)
        self.tick_gig(session, now)
        self.tick_arcade(session, now)
        self.tick_pets(session, now)
        self.tick_fishing(session, now)

    def shutdown(self):
        """The server is stopping: say so, and save everyone."""
        for session in list(self.sessions.values()):
            self._send(session, "system", "server_restart")
            self.leave_casino(session)
            self.arcade_finish(session, "stopped")
            self._save(session)
        self.market.save()
        self.save_economy()


CREDIT_WORDS = {"credit", "credits", "cr", "money", "coins"}
AGAIN_WORDS = {"again", "!"}


def _collect_commands():
    commands = {
        "look": Game.cmd_look, "say": Game.cmd_say, "whisper": Game.cmd_whisper,
        "shout": Game.cmd_shout, "emote": Game.cmd_emote, "who": Game.cmd_who,
        "inventory": Game.cmd_inventory, "give": Game.cmd_give, "describe": Game.cmd_describe,
        "text": Game.cmd_text, "help": Game.cmd_help, "bye": Game.cmd_bye, "away": Game.cmd_away,
        "status": Game.cmd_status,
    }
    for mixin in MIXINS:
        commands.update(mixin.commands())
    return commands


Game.COMMANDS = _collect_commands()

# Kept for the tests and older callers.
REPAIR_MIN, REPAIR_MAX = 3, 6
_ = re
