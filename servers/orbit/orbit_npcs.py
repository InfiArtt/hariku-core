# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The residents: characters who are not players (npcs.json). A bartender who
knows the gossip, an old engineer with errands, the keeper of the Way of
Starlight, a traveller who comes only at night, shopkeepers, the ferry's
pilot, a curious girl, a trader in a back alley, the arcade's host, and
people who simply live here and walk the map on their daily schedules.

  talk to Jali / bicara dengan Jali      their greeting, and what to ask them about
  ask Jali about gossip / tanya Jali tentang gosip
  greet Jali / sapa Jali / halo Jali     and gestures at them: wave to Jali
  give Jali 3 chillies / beri Jali 3 cabai
                                         a gift, or what a favour asked for
  residents / penduduk                   who they are, and where they are now

They are always told apart from players: "who" lists only players, "look"
names them under "Residents here", and looking at one says so. They move
and speak through the same paths as players (arrivals and departures with
their side, their lines in a voice number of their own), so every client
hears them like a player, and Orbit 1.0 reads them as plain lines.

Where they are comes from their schedule and the station's clock (UTC), so
nothing about them needs saving but what they remember of each player
(npc_memory): how fond of them they are (affinity), how often they talked,
gifts, favours, and small notes (the topics heard, a favour asked). Talking
(once a day), a new topic, gifts (once a day, more for a thing they like)
and favours raise the affinity; it opens new topics, a small discount in
their shop, and their special errands. Their idle lines are rare, and never
while players there are talking. They use a random generator of their own,
so they never change what the rest of the game draws.
"""

import datetime
import logging
import random

import orbit_safety
import orbit_world
from orbit_lang import pick

logger = logging.getLogger("orbit.game")
LANGS = ("en", "id")
NPC_DEFAULTS = {
    "walk_seconds": [8, 14],        # a step every so many seconds when walking to the next place
    "idle_gap": [180, 420],         # seconds between one resident's idle lines
    "room_gap": 120,                # at most one idle line a room in this many seconds
    "quiet_seconds": 90,            # none this soon after a player talked or gestured in the room
    "notice_seconds": 1800,         # a resident greets a player they know at most this often...
    "notice_chance": 0.5,           # ...and only now and then
    "affinity": {"talk": 1, "topic": 1, "gift": 2, "liked_gift": 4, "favour": 6, "max": 100},
    "levels": [["stranger", 0], ["acquaintance", 5], ["friend", 15], ["close", 30]],
    "discount": {"friend": 0.05, "close": 0.1},
}
FRIENDLY_EMOTES = ("smile", "wave", "bow", "hug", "cheer", "clap", "nod", "laugh", "dance")
GREETING_WORDS = ("halo", "hai", "hi", "hello", "hey", "hei", "helo", "hallo", "hola", "pagi", "siang", "sore",
                  "malam", "selamat pagi", "selamat siang", "selamat sore", "selamat malam", "good morning",
                  "good afternoon", "good evening", "morning", "evening", "salam", "yo")
ABOUT_WORDS = ("about", "on", "tentang", "soal", "mengenai", "perihal", "masalah", "the")
TALK_PREFIXES = ("dengan", "sama", "ke", "kepada", "pada", "with", "to")


def _keys(names):
    return {orbit_world.strip_articles(n) for n in names if orbit_world.strip_articles(n)}


class NpcsMixin:
    @staticmethod
    def commands():
        return {"talk": NpcsMixin.cmd_talk, "ask": NpcsMixin.cmd_ask, "greet": NpcsMixin.cmd_greet,
                "residents": NpcsMixin.cmd_residents}

    def init_npcs(self):
        data = self.world.npcs or {}
        self.npc_defs = data.get("npcs") or {}
        rules = dict(NPC_DEFAULTS)
        rules.update(data.get("rules") or {})
        self.npc_rules = rules
        self.npc_rng = random.Random(int(self.now()) ^ 0x5EED)
        self._npc_names = {}
        for nid, d in self.npc_defs.items():
            names = [d["name"], nid] + [n for lang in LANGS for n in d.get("names", {}).get(lang, [])]
            self._npc_names[nid] = _keys(names)
        self._npc_topic_names = {
            nid: {tid: _keys(t["names"].get("en", []) + t["names"].get("id", []))
                  for tid, t in d.get("topics", {}).items()}
            for nid, d in self.npc_defs.items()}
        self.room_chat = {}             # room -> when a player last talked or gestured there
        self.room_idle = {}             # room -> when a resident last said an idle line there
        now = self.now()
        low, high = rules["idle_gap"]
        self.npcs = {nid: {"room": self.npc_target(nid, now), "next_step": now,
                           "next_idle": now + self.npc_rng.uniform(low, high), "noticed": {}}
                     for nid in self.npc_defs}
        for nid in self.npc_defs:
            if self.npcs[nid]["room"] is None and self.npc_scheduled(nid, now) is not None:
                self.npcs[nid]["room"] = self.npc_defs[nid]["home"]

    # --- who they are, where they are -------------------------------------------------------

    def npc_name(self, nid):
        return self.npc_defs[nid]["name"]

    def npc_short(self, nid):
        """What players call a resident: "Jali" for Bang Jali."""
        return self.npc_defs[nid]["names"]["en"][0].title()

    def npc_scheduled(self, nid, now):
        """The room a resident's schedule puts them in at `now` (None: off duty)."""
        hour = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).hour
        schedule = self.npc_defs[nid]["schedule"]
        room = schedule[-1][1]
        for start, where in schedule:
            if start <= hour:
                room = where
        return room

    def npc_target(self, nid, now):
        """Where a resident is heading now: a ceremony they lead, else their schedule."""
        ceremony = self.npc_ceremony_room(nid, now)
        return ceremony if ceremony else self.npc_scheduled(nid, now)

    def npc_ceremony_room(self, nid, now):
        """A room a resident must be in for a ceremony (weddings, the naming rite), or None."""
        finder = getattr(self, "ceremony_room_for", None)
        return finder(nid, now) if finder else None

    def npcs_in(self, room):
        return [nid for nid, state in self.npcs.items() if state["room"] == room]

    def _npc_match(self, nids, text, exact_only=False):
        key = orbit_world.strip_articles(text)
        if not key:
            return None
        exact = [nid for nid in nids if key in self._npc_names[nid]]
        if exact:
            return exact[0]
        if len(key) >= 3 and not exact_only:
            starts = [nid for nid in nids if any(name.startswith(key) for name in self._npc_names[nid])]
            if len(starts) == 1:
                return starts[0]
        return None

    def npc_here(self, session, text):
        """A resident in the same room as `session` whose name `text` is, or None."""
        room = self.room_of(session.char)
        return self._npc_match(self.npcs_in(room), text)

    def find_npc(self, text):
        """Any resident by name, wherever they are."""
        return self._npc_match(list(self.npc_defs), text)

    def residents_text(self, session):
        """ "Residents here: Bang Jali, the Cantina's bartender." for the room's description."""
        here = self.npcs_in(self.room_of(session.char))
        if not here:
            return ""
        lang = session.lang
        entries = [self.render(lang, "resident_entry", name=self.npc_name(nid), role=self.npc_defs[nid]["role"])
                   for nid in sorted(here, key=self.npc_name)]
        return self.render(lang, "look_residents", people=entries)

    def npc_look_text(self, session, nid):
        d = self.npc_defs[nid]
        lang = session.lang
        memory = self.store.npc_memory(nid, session.char["id"])
        parts = [self.render(lang, "npc_look", name=d["name"], role=d["role"]), pick(d["desc"], lang),
                 self.render(lang, "npc_is_resident", name=d["name"])]
        if memory["first_met"]:
            parts.append(self.render(lang, "npc_knows_you", name=d["name"],
                                     level=self.render(lang, f"npc_level_{self.npc_level(memory['affinity'])}")))
        return " ".join(parts)

    def npc_where_text(self, lang, nid):
        room = self.npcs[nid]["room"]
        if room is None:
            return self.render(lang, "npc_off_duty_short")
        return pick(self.world.locations[room]["in"], lang)

    def cmd_residents(self, session, message):
        lang = session.lang
        entries = [self.render(lang, "resident_where", name=self.npc_name(nid), role=d["role"],
                               where=self.npc_where_text(lang, nid))
                   for nid, d in self.npc_defs.items()]
        self._info(session, "residents_list", entries="; ".join(entries))

    # --- what they remember ---------------------------------------------------------------------

    def npc_level(self, affinity):
        level = "stranger"
        for name, at in self.npc_rules["levels"]:
            if affinity >= at:
                level = name
        return level

    def _npc_level_at_least(self, affinity, level):
        marks = dict((name, at) for name, at in self.npc_rules["levels"])
        return affinity >= marks.get(level, 0)

    def _npc_meet(self, memory):
        now = self.now()
        if not memory["first_met"]:
            memory["first_met"] = now
        memory["last_met"] = now

    def _npc_add(self, session, nid, memory, points):
        """More (or less) affinity; a player is told when a resident counts them as closer."""
        if not points:
            return
        before = self.npc_level(memory["affinity"])
        memory["affinity"] = max(0, min(int(self.npc_rules["affinity"]["max"]), int(memory["affinity"]) + points))
        after = self.npc_level(memory["affinity"])
        levels = [name for name, _at in self.npc_rules["levels"]]
        if levels.index(after) > levels.index(before):
            self._send(session, "info", "npc_level_up", name=self.npc_name(nid),
                       level=self.render(session.lang, f"npc_level_{after}"), extra={"sound": "npc_warm"})

    def _npc_daily(self, session, nid, memory):
        """Talking to a resident: once a day, a little closer."""
        state = memory["state"]
        today = self.today()
        self._npc_meet(memory)
        if state.get("talk_day") != today:
            state["talk_day"] = today
            self._npc_add(session, nid, memory, int(self.npc_rules["affinity"]["talk"]))

    def npc_discount(self, char, sid):
        """The share a shop's keeper takes off for a friend (0 to 1)."""
        if not sid or char.get("id") is None:
            return 0.0
        best = 0.0
        for nid, d in self.npc_defs.items():
            if d.get("shop") == sid:
                level = self.npc_level(self.store.npc_memory(nid, char["id"])["affinity"])
                best = max(best, float(self.npc_rules["discount"].get(level, 0.0)))
        return best

    def npc_friends(self, lang, char):
        """ "Bang Jali (a friend), Pak Harsa (an acquaintance)" for a profile, or ""."""
        known = [m for m in self.store.npc_memories_of(char["id"]) if m["npc"] in self.npc_defs and m["first_met"]]
        if not known:
            return ""
        entries = [self.render(lang, "npc_friend_entry", name=self.npc_name(m["npc"]),
                               level=self.render(lang, f"npc_level_{self.npc_level(m['affinity'])}"))
                   for m in known[:6]]
        return self.render(lang, "profile_residents", entries=entries)

    # --- speaking ---------------------------------------------------------------------------------

    def _npc_fill(self, lang, template, params):
        values = {}
        for key, value in params.items():
            values[key] = self.texts.join(lang, value) if isinstance(value, (list, tuple)) else pick(value, lang)
        try:
            return str(template).format(**values)
        except (KeyError, IndexError, ValueError):
            return str(template)

    def _npc_variant(self, lines):
        """One of a list of lines, the same one in every language: {"en": ..., "id": ...}."""
        index = self.npc_rng.randrange(len(lines["en"]))
        return {lang: lines[lang][index] for lang in LANGS}

    def npc_say(self, sessions, nid, words, **params):
        """A resident says `words` ({"en", "id"}) to these players, in the resident's own voice."""
        d = self.npc_defs[nid]
        params = dict(params, npc=d["name"])
        for other in sessions:
            text = self._npc_fill(other.lang, pick(words, other.lang), dict(params, name=params.get("name", other.name)))
            self._send(other, "say", "say_other", extra={"actor": d["name"], "voice": int(d["voice"]), "words": text},
                       actor=d["name"], words=text)

    def npc_emote(self, sessions, nid, text, extra=None, **params):
        """A gesture of a resident's, seen by these players."""
        d = self.npc_defs[nid]
        for other in sessions:
            line = self._npc_fill(other.lang, pick(text, other.lang), dict(params, npc=d["name"]))
            self._send(other, "emote", text=line, extra=dict(extra or {}, actor=d["name"]))

    def _npc_words(self, key):
        """A line of texts.json as words a resident says ({"en", "id"})."""
        return {lang: self.texts.raw(lang, key) for lang in LANGS}

    def note_room_chat(self, session):
        """A player talked or gestured here: the residents keep quiet for a while."""
        self.room_chat[self.room_of(session.char)] = self.now()

    # --- finding the one you mean ------------------------------------------------------------------

    def _npc_for(self, session, name):
        """The resident here that `name` means (or the only one here). None after saying why not."""
        lang = session.lang
        here = self.npcs_in(self.room_of(session.char))
        name = orbit_safety.tidy(name, 60)
        if not name:
            if len(here) == 1:
                return here[0]
            if not here:
                self._error(session, "npc_nobody")
            else:
                self._error(session, "npc_whom", people=[self.npc_name(n) for n in sorted(here, key=self.npc_name)])
            return None
        nid = self._npc_match(here, name)
        if nid is not None:
            return nid
        player = self._find_near(session, name)
        if player is not None:
            self._error(session, "npc_is_player", name=player.name)
            return None
        elsewhere = self.find_npc(name)
        if elsewhere is not None:
            if self.npcs[elsewhere]["room"] is None:
                self._error(session, "npc_off_duty", name=self.npc_name(elsewhere))
            else:
                self._error(session, "npc_elsewhere", name=self.npc_name(elsewhere),
                            where=self.world.locations[self.npcs[elsewhere]["room"]]["in"])
            return None
        self._error(session, "not_here", name=name)
        return None

    def _topic_for(self, nid, text, lang):
        """The topic of a resident's that `text` names, or None."""
        words = orbit_world.strip_articles(text).split()
        while len(words) > 1 and words[0] in ABOUT_WORDS:
            words = words[1:]
        key = " ".join(words)
        if not key:
            return None
        topics = self._npc_topic_names[nid]
        for tid, names in topics.items():
            if key in names:
                return tid
        best, size = None, 0
        for tid, names in topics.items():
            for name in names:
                if len(name) >= 3 and (f" {name} " in f" {key} ") and len(name) > size:
                    best, size = tid, len(name)
        if best:
            return best
        if len(key) >= 4:
            for tid, names in topics.items():
                if any(name.startswith(key) for name in names):
                    return tid
        return None

    def _topics_open(self, nid, memory):
        """The topics a resident talks about with this player, and whether more are locked."""
        open_, locked = [], False
        for tid, topic in self.npc_defs[nid].get("topics", {}).items():
            if int(memory["affinity"]) >= int(topic.get("min", 0)):
                open_.append(tid)
            else:
                locked = True
        return open_, locked

    def _topic_label(self, nid, tid, lang):
        return self.npc_defs[nid]["topics"][tid]["names"][lang][0]

    # --- talking ----------------------------------------------------------------------------------

    def _greeting(self, nid, memory):
        d = self.npc_defs[nid]
        affinity = int(memory["affinity"])
        if memory["first_met"] and self._npc_level_at_least(affinity, "friend"):
            return self._npc_variant(d["greet_friend"])
        if memory["first_met"] and self._npc_level_at_least(affinity, "acquaintance"):
            return self._npc_variant(d["greet_known"])
        return self._npc_variant(d["greet"])

    def _your_child(self, session, name, op="talk", text=""):
        """Talking to (or asking for help from) a child of yours: True when it was one."""
        finder = getattr(self, "_child_named", None)
        child = finder(session.char, name) if finder and name else None
        if child is None or not child["name"]:
            return False
        helping = any(w in str(text).lower().split() for w in ("help", "bantuan", "tolong", "fetch", "errand"))
        self.run(session, {"c": "child", "op": "fetch" if op == "ask" and helping else "talk", "a": child["name"]})
        return True

    def cmd_talk(self, session, message):
        if self._your_child(session, self._arg(message, "to", 60) or self._arg(message, "a", 60)):
            return
        nid = self._npc_for(session, self._arg(message, "to", 60) or self._arg(message, "a", 60))
        if nid is None:
            return
        self._npc_conversation(session, nid)

    def _npc_conversation(self, session, nid, others_key="npc_talk_other"):
        lang = session.lang
        memory = self.store.npc_memory(nid, session.char["id"])
        words = self._greeting(nid, memory)
        self._npc_daily(session, nid, memory)
        memory["talks"] = int(memory["talks"]) + 1
        self.store.save_npc_memory(memory)
        self.note_room_chat(session)
        self.npc_say([session], nid, words, name=session.name)
        open_, locked = self._topics_open(nid, memory)
        text = self.render(lang, "npc_topics", name=self.npc_name(nid), short=self.npc_short(nid),
                           topics=[self._topic_label(nid, tid, lang) for tid in open_])
        if locked:
            text += " " + self.render(lang, "npc_topics_more", name=self.npc_name(nid))
        self._info(session, text=text)
        if not session.invisible:
            self._to_room(self.room_of(session.char), "emote", others_key, exclude=(session,),
                          extra={"actor": session.name}, actor=session.name, name=self.npc_name(nid))

    def cmd_greet(self, session, message):
        nid = self._npc_for(session, self._arg(message, "to", 60) or self._arg(message, "a", 60))
        if nid is None:
            return
        memory = self.store.npc_memory(nid, session.char["id"])
        words = self._greeting(nid, memory)
        self._npc_daily(session, nid, memory)
        self.store.save_npc_memory(memory)
        self.note_room_chat(session)
        self._send(session, "emote", "npc_greet_you", name=self.npc_name(nid))
        if not session.invisible:
            self._to_room(self.room_of(session.char), "emote", "npc_greet_other", exclude=(session,),
                          extra={"actor": session.name}, actor=session.name, name=self.npc_name(nid))
        self.npc_say([session], nid, words, name=session.name)

    def cmd_ask(self, session, message):
        name = self._arg(message, "to", 60)
        text = self._arg(message, "a", 200)
        if self._your_child(session, name, "ask", text):
            return
        here = self.npcs_in(self.room_of(session.char))
        nid = None
        if name and self._npc_match(here, name, exact_only=True) is None:
            # "tanya Bang Jali gosip": the name goes on into the words after it
            words = text.split()
            for n in range(min(3, len(words)), 0, -1):
                nid = self._npc_match(here, " ".join([name] + words[:n]), exact_only=True)
                if nid is not None:
                    text = " ".join(words[n:])
                    break
        if nid is None:
            nid = self._npc_for(session, name)          # none named: the only resident here
        if nid is None:
            return
        if not text:
            self._npc_conversation(session, nid)
            return
        lang = session.lang
        d = self.npc_defs[nid]
        memory = self.store.npc_memory(nid, session.char["id"])
        self._npc_daily(session, nid, memory)
        memory["talks"] = int(memory["talks"]) + 1
        self.note_room_chat(session)
        tid = self._topic_for(nid, text, lang)
        if tid is None:
            self.store.save_npc_memory(memory)
            self.npc_say([session], nid, self._npc_variant(d["unknown"]), name=session.name)
            return
        topic = d["topics"][tid]
        if int(memory["affinity"]) < int(topic.get("min", 0)):
            self.store.save_npc_memory(memory)
            self.npc_say([session], nid, self._npc_words("npc_locked_words"), name=session.name)
            return
        if topic.get("favour"):
            self._npc_favour(session, nid, memory)
            return
        heard = memory["state"].setdefault("heard", [])
        if tid not in heard:
            heard.append(tid)
            self._npc_add(session, nid, memory, int(self.npc_rules["affinity"]["topic"]))
        self.store.save_npc_memory(memory)
        case, params = (None, {})
        if topic.get("live"):
            case, params = self.npc_live(session, nid, topic["live"])
        lines = (topic.get("cases") or {}).get(case) if case else None
        self.npc_say([session], nid, self._npc_variant(lines or topic["say"]), **dict(params, name=session.name))

    # --- gestures and gifts ------------------------------------------------------------------------

    def npc_emote_at(self, session, nid, eid, emote):
        """A player's gesture at a resident, and the resident's answer."""
        name = self.npc_name(nid)
        room = self.room_of(session.char)
        self._send(session, "emote", text=emote[session.lang]["you_at"].format(target=name), extra={"emote": eid})
        for other in self._in_room(room, exclude=(session,)):
            self._send(other, "emote", text=emote[other.lang]["they_at"].format(actor=session.name, target=name),
                       extra={"actor": session.name, "emote": eid})
        react = (self.npc_defs[nid].get("react") or {}).get(eid)
        for other in self._in_room(room):
            if react:
                line = self._npc_fill(other.lang, pick(react, other.lang), {"npc": name, "actor": session.name})
            else:
                key = f"npc_react_{eid}" if other is session else f"npc_react_{eid}_other"
                line = self.render(other.lang, key, npc=name, actor=session.name)
            self._send(other, "emote", text=line, extra={"actor": name, "emote": eid})
        if eid in FRIENDLY_EMOTES:
            memory = self.store.npc_memory(nid, session.char["id"])
            self._npc_daily(session, nid, memory)
            self.store.save_npc_memory(memory)

    def npc_for_give(self, session, to, item):
        """(resident, the thing's words) for "give Jali 3 chillies" or "give Bang Jali chillies"."""
        here = self.npcs_in(self.room_of(session.char))
        if not here:
            return None, item
        words = str(item or "").split()
        for n in range(min(3, len(words)), 0, -1):
            nid = self._npc_match(here, " ".join([to] + words[:n]), exact_only=True)
            if nid is not None:
                return nid, " ".join(words[n:])
        return self._npc_match(here, to), item

    def npc_receive(self, session, nid, what, n):
        """ "give Jali 3 chillies": a gift, or what a favour asked for."""
        char, lang = session.char, session.lang
        name = self.npc_name(nid)
        if orbit_safety.name_key(what) in ("credits", "credit", "kredit", "cr", "uang", "duit", "money", "coins", ""):
            self.npc_say([session], nid, self._npc_words("npc_no_credits"), name=session.name)
            return
        tid = self.world.find_good(what) or self.world.find_item(what) or self.world.find_thing(what)
        if tid is None:
            self._error(session, "no_item", what=what)
            return
        info = self.world.things[tid]
        have = int(char["inventory"].get(tid, 0))
        if not have:
            self._error(session, "dont_have", thing=info["many"])
            return
        if not self._tradeable(tid):
            self._error(session, "npc_cant_gift", thing=info["many"], name=name)
            return
        if not self._slow(session):
            return
        memory = self.store.npc_memory(nid, char["id"])
        self._npc_meet(memory)
        favour = self._npc_active_favour(nid, memory)
        if favour is not None and tid in favour["needs"]:
            self._npc_complete(session, nid, memory, favour, tid, n)
            return
        if have < n:
            self._error(session, "not_enough", things=self._count_of(tid, have))
            return
        self._take_away(char, tid, n)
        if not char["inventory"].get(tid):
            for slot in [s for s, t in self.worn(char).items() if t == tid]:
                self.worn(char).pop(slot, None)
        state = memory["state"]
        memory["gifts"] = int(memory["gifts"]) + 1
        rules = self.npc_rules["affinity"]
        if state.get("gift_day") != self.today():
            state["gift_day"] = self.today()
            liked = tid in self.npc_defs[nid].get("likes", [])
            words = self._npc_words("npc_gift_loved" if liked else "npc_gift_thanks")
            points = int(rules["liked_gift"] if liked else rules["gift"])
        else:
            words, points = self._npc_words("npc_gift_again"), 0
        self._save(session)
        self._send(session, "gave", "npc_gave", name=name, things=self._count_of(tid, n))
        self.npc_say([session], nid, words, name=session.name)
        self._npc_add(session, nid, memory, points)
        self.store.save_npc_memory(memory)
        if not session.invisible:
            self._to_room(self.room_of(char), "emote", "npc_gave_other", exclude=(session,),
                          extra={"actor": session.name}, actor=session.name, name=name, things=self._count_of(tid, n))

    # --- favours -----------------------------------------------------------------------------------

    def _npc_favours(self, nid):
        return {f["id"]: f for f in self.npc_defs[nid].get("favours", [])}

    def _npc_active_favour(self, nid, memory):
        active = memory["state"].get("favour")
        if not isinstance(active, dict):
            return None
        return self._npc_favours(nid).get(active.get("id"))

    def _npc_favour(self, session, nid, memory):
        """Asked about a favour: the one they're waiting for, the next they need, or why none."""
        favour = self._npc_active_favour(nid, memory)
        if favour is not None:
            self.store.save_npc_memory(memory)
            self.npc_say([session], nid, favour["ask"], name=session.name)
            self._favour_note(session, nid, favour)
            return
        state = memory["state"]
        done = state.get("done") or {}
        today = self.today()
        offer, locked, done_today = None, False, False
        for f in self.npc_defs[nid].get("favours", []):
            if int(memory["affinity"]) < int(f.get("min", 0)):
                locked = True
                continue
            last = done.get(f["id"])
            if f.get("repeat", "daily") == "once" and last:
                continue
            if f.get("repeat", "daily") == "daily" and last == today:
                done_today = True
                continue
            offer = f
            break
        if offer is None:
            self.store.save_npc_memory(memory)
            key = "npc_favour_done_today" if done_today else "npc_favour_later" if locked else "npc_favour_none"
            self.npc_say([session], nid, self._npc_words(key), name=session.name)
            return
        state["favour"] = {"id": offer["id"], "since": self.now()}
        self.store.save_npc_memory(memory)
        self.npc_say([session], nid, offer["ask"], name=session.name)
        self._favour_note(session, nid, offer)

    def _favour_note(self, session, nid, favour):
        tid, n = next(iter(favour["needs"].items()))
        self._send(session, "mission", "npc_favour_open", name=self.npc_name(nid), things=self._count_of(tid, n))

    def _npc_complete(self, session, nid, memory, favour, tid, n):
        char, lang = session.char, session.lang
        need = int(favour["needs"][tid])
        have = int(char["inventory"].get(tid, 0))
        if have < need or n < need:
            self._error(session, "npc_favour_short", name=self.npc_name(nid), things=self._count_of(tid, need))
            return
        reward = favour.get("reward") or {}
        self._take_away(char, tid, need)
        state = memory["state"]
        state.pop("favour", None)
        state.setdefault("done", {})[favour["id"]] = self.today()
        memory["favours"] = int(memory["favours"]) + 1
        credits = int(reward.get("credits") or 0)
        if credits:
            self.earn(char, credits, "favours")
        thing = reward.get("thing")
        if thing:
            self.give_thing(char, thing, 1)
        self._save(session)
        self.npc_say([session], nid, favour["thanks"], name=session.name)
        gift = self.render(lang, "npc_favour_thing", thing=self.world.things[thing]["one"]) if thing else ""
        self._send(session, "paid", "npc_favour_reward", name=self.npc_name(nid), n=credits, thing=gift,
                   credits=char["credits"], extra={"sound": "mission"})
        self._npc_add(session, nid, memory, int(self.npc_rules["affinity"]["favour"]))
        self.store.save_npc_memory(memory)
        if reward.get("xp"):
            self.award_xp(session, int(reward["xp"]))
        char["stats"]["favours"] = int(char["stats"].get("favours") or 0) + 1
        self._save(session)

    # --- time passing ------------------------------------------------------------------------------

    def tick_npcs(self, now):
        for nid, state in self.npcs.items():
            target = self.npc_target(nid, now)
            if state["room"] != target and now >= state["next_step"]:
                self._npc_step(nid, state, target, now)
        self._npc_idle(now)

    def _npc_step(self, nid, state, target, now):
        d = self.npc_defs[nid]
        low, high = self.npc_rules["walk_seconds"]
        state["next_step"] = now + self.npc_rng.uniform(float(low), float(high))
        room = state["room"]
        if room is None:
            state["room"] = d["home"]
            self._npc_appear(nid, d["home"])
            return
        goal = target if target is not None else d["home"]
        if room == goal:
            if target is None:
                state["room"] = None
                self._npc_vanish(nid, room)
            return
        path = self.world.npc_route(room, goal)
        if not path:
            state["room"] = None
            self._npc_vanish(nid, room)
            state["room"] = goal
            self._npc_appear(nid, goal)
            return
        how, nxt = path[0]
        state["room"] = nxt
        self._npc_walk(nid, room, nxt, how)

    def _npc_walk(self, nid, old, new, d):
        name = self.npc_name(nid)
        back = self.world.directions[d]["back"]
        new_loc, old_loc = self.world.locations[new], self.world.locations[old]
        for other in self._in_room(old):
            key = {"u": "leave_up", "d": "leave_down"}.get(d, "leave_dir")
            self._send(other, "leave", key, extra={"actor": name, "dir": d}, actor=name,
                       dir=self.dir_word(other.lang, d), place=new_loc["ref"])
        for other in self._in_room(new):
            key = {"u": "arrive_down", "d": "arrive_up"}.get(back, "arrive_dir")
            self._send(other, "arrive", key, extra={"actor": name, "dir": back}, actor=name,
                       dir=self.dir_word(other.lang, back), place=old_loc["ref"])

    def _npc_appear(self, nid, room):
        d = self.npc_defs[nid]
        for other in self._in_room(room):
            if d.get("appear"):
                text = self._npc_fill(other.lang, pick(d["appear"], other.lang), {"npc": d["name"]})
                self._send(other, "arrive", text=text, extra={"actor": d["name"]})
            else:
                self._send(other, "arrive", "npc_appear", extra={"actor": d["name"]}, actor=d["name"])

    def _npc_vanish(self, nid, room):
        d = self.npc_defs[nid]
        for other in self._in_room(room):
            if d.get("vanish"):
                text = self._npc_fill(other.lang, pick(d["vanish"], other.lang), {"npc": d["name"]})
                self._send(other, "leave", text=text, extra={"actor": d["name"]})
            else:
                self._send(other, "leave", "npc_vanish", extra={"actor": d["name"]}, actor=d["name"])

    def _listeners(self, room):
        return [s for s in self._in_room(room) if s.conn is not None and not s.away]

    def _npc_idle(self, now):
        rules = self.npc_rules
        for nid, state in self.npcs.items():
            room = state["room"]
            if room is None or now < state["next_idle"]:
                continue
            low, high = rules["idle_gap"]
            state["next_idle"] = now + self.npc_rng.uniform(float(low), float(high))
            listeners = self._listeners(room)
            if not listeners or self.world.locations[room].get("dark"):
                continue
            if now - self.room_chat.get(room, -1e12) < float(rules["quiet_seconds"]):
                continue
            if now - self.room_idle.get(room, -1e12) < float(rules["room_gap"]):
                continue
            lines = [line for line in self.npc_defs[nid].get("idle", []) if line.get("room") in (None, room)]
            if not lines:
                continue
            line = self.npc_rng.choice(lines)
            self.room_idle[room] = now
            words = {lang: line[lang] for lang in LANGS}
            if line["kind"] == "say":
                self.npc_say(listeners, nid, words)
            else:
                self.npc_emote(listeners, nid, words)

    def npc_notice(self, session):
        """A player walks in: a resident who knows them may say hello (now and then, never mid-chat)."""
        if session.invisible or session.conn is None:
            return
        room = self.room_of(session.char)
        here = self.npcs_in(room)
        if not here:
            return
        now = self.now()
        rules = self.npc_rules
        if now - self.room_chat.get(room, -1e12) < float(rules["quiet_seconds"]):
            return
        for nid in here:
            noticed = self.npcs[nid]["noticed"]
            if now - noticed.get(session.key, -1e12) < float(rules["notice_seconds"]):
                continue
            memory = self.store.npc_memory(nid, session.char["id"])
            if not memory["first_met"] or not self._npc_level_at_least(int(memory["affinity"]), "acquaintance"):
                continue
            noticed[session.key] = now
            if self.npc_rng.random() >= float(rules["notice_chance"]):
                continue
            self.npc_say([session], nid, self._greeting(nid, memory), name=session.name)
            return

    # --- what they know right now -----------------------------------------------------------------

    def npc_live(self, session, nid, provider):
        """(case, params) of a topic's live value: what a resident can say about the game right now."""
        handler = getattr(self, f"_live_{provider}", None)
        if handler is None:
            return None, {}
        try:
            return handler(session, nid)
        except Exception:                                   # never let small talk break a command
            logger.exception("a resident's %s answer failed", provider)
            return None, {}

    def _when(self, lang, at):
        when = datetime.datetime.fromtimestamp(at, datetime.timezone.utc)
        return {"day": self.render(lang, f"weekday_{when.weekday()}"), "hour": when.strftime("%H:%M")}

    def _live_time(self, session, nid):
        now = datetime.datetime.fromtimestamp(self.now(), datetime.timezone.utc)
        hour = now.hour
        part = "morning" if 5 <= hour < 11 else "midday" if hour < 15 else "afternoon" if hour < 18 else "night"
        if hour < 5:
            part = "night"
        return None, {"time": now.strftime("%H:%M"),
                      "part": {lang: self.texts.raw(lang, f"time_{part}") for lang in LANGS}}

    def _others_online(self, session):
        return [s for s in self.sessions.values() if s is not session and s.conn is not None and not s.invisible]

    def _live_who(self, session, nid):
        others = sorted(self._others_online(session), key=lambda s: s.key)
        if not others:
            return "alone", {}
        return None, {"n": len(others) + 1, "names": [s.name for s in others[:3]]}

    def _live_gossip(self, session, nid):
        cases = []
        now = self.now()
        for wedding in reversed(self.store.weddings_with(["done"])):
            if now - float(wedding["starts"]) < 7 * 86400:
                a, b = self._couple_names(wedding)
                cases.append(("wedding", {"a": a, "b": b, "place": self.world.locations[wedding["venue"]]["ref"]}))
                break
        for wedding in self.store.weddings_with(["booked"]):
            if float(wedding["starts"]) > now:
                a, b = self._couple_names(wedding)
                cases.append(("next_wedding", dict(self._when_params(wedding["starts"]), a=a, b=b,
                                                   place=self.world.locations[wedding["venue"]]["ref"])))
                break
        rich = self.store.top("credits", 1, exclude=self.admins)
        if rich and rich[0][1] > 0:
            cases.append(("rich", {"rich": rich[0][0]}))
        miner = self.store.top("mined", 1, exclude=self.admins)
        if miner and miner[0][1] > 0:
            cases.append(("miner", {"miner": miner[0][0]}))
        crews = self.store.top_crews(1)
        if crews:
            cases.append(("crew", {"crew": crews[0]["name"]}))
        if not cases:
            return None, {}
        return self.npc_rng.choice(cases)

    def _when_params(self, at):
        return {"day": {lang: self._when(lang, float(at))["day"] for lang in LANGS},
                "hour": datetime.datetime.fromtimestamp(float(at), datetime.timezone.utc).strftime("%H:%M")}

    def _couple_names(self, wedding):
        partnership = self.store.partnership_by_id(wedding["partnership"])
        names = []
        for char_id in (partnership["a"], partnership["b"]) if partnership else ():
            char = self.store.by_id(char_id)
            names.append(char["name"] if char else "?")
        while len(names) < 2:
            names.append("?")
        return names[0], names[1]

    def _live_market(self, session, nid):
        best, gap = None, 0.08
        for gid, good in self.world.goods.items():
            if good.get("kind", "trade") == "contraband" or not good.get("base"):
                continue
            ratio = self.market.price(gid) / float(good["base"])
            if abs(ratio - 1) > gap:
                best, gap = (gid, ratio), abs(ratio - 1)
        if best is None:
            return None, {}
        gid, ratio = best
        price = self.market.unit_price(gid, session.char["job"], "sell" if ratio >= 1 else "buy",
                                       fees=self.fees_for(session.char))
        return ("high" if ratio >= 1 else "low"), {"good": self.world.goods[gid]["one"], "price": int(round(price))}

    def _live_event(self, session, nid):
        now = self.now()
        rows = [r for r in self.active.values() if r["event"] not in ("custom", "party")]
        if rows:
            row = sorted(rows, key=lambda r: r["ends"])[0]
            name = self.events_def[row["event"]]["name"]
            return "on", {"event": name, "time": {lang: self._duration(lang, float(row["ends"]) - now)
                                                  for lang in LANGS}}
        upcoming = self.next_event(now)
        if upcoming:
            start, eid = upcoming
            return "next", dict(self._when_params(start), event=self.events_def[eid]["name"])
        return None, {}

    def _live_progress(self, session, nid):
        char = session.char
        xp = int(char.get("xp") or 0)
        level = self.level_of(xp)
        params = {"level": level, "rank": self.rank_name(char), "next": level + 1,
                  "need": self.xp_for_level(level + 1) - xp}
        if level >= int(self.econ["levels"]["max"]):
            return "max", params
        return None, params

    def _live_special(self, session, nid):
        sid = self.npc_defs[nid].get("shop")
        tid = self.special_of(sid) if sid else None
        if tid is None:
            return "none", {}
        return None, {"thing": self.world.things[tid]["one"], "price": self.price_of(session.char, tid, sid)}

    def _live_ferry(self, session, nid):
        now = self.now()
        depart = self.next_ferry(now)
        return None, {"time": {lang: self._duration(lang, max(1.0, depart - now)) for lang in LANGS}}

    def festival_state(self):
        """(the Lantern Festival's row if it's on, its lanterns, its goal, whether it was reached)."""
        row = self.active_of("lantern_festival") if hasattr(self, "active_of") else None
        goal = int(self.econ.get("temple", {}).get("festival_goal", 50))
        if row is None:
            return None, 0, goal, False
        state = row.get("state") or {}
        return row, int(state.get("lanterns", 0)), goal, bool(state.get("reached"))

    def _live_lanterns(self, session, nid):
        row, lit, goal, reached = self.festival_state()
        if row is not None:
            return ("done" if reached else "festival"), {"n": lit, "goal": goal}
        return None, {"n": self.lanterns_today()}

    def _live_festival(self, session, nid):
        row, lit, goal, reached = self.festival_state()
        if row is not None:
            return ("done" if reached else "on"), {"n": lit, "goal": goal}
        definition = self.events_def.get("lantern_festival")
        start = self.next_seasonal(definition, self.now() + 86400) if definition else None
        day = datetime.datetime.fromtimestamp(start, datetime.timezone.utc) if start else None
        date = {lang: day.strftime("%d-%m-%Y") if day else "-" for lang in LANGS}
        return None, {"day": date, "goal": goal}

    def _live_hunt(self, session, nid):
        if self.hunt is None:
            return None, {}
        progress = self._progress(session)
        stages = self.hunt["stages"]
        if progress["finished"] or progress["stage"] >= len(stages):
            return "done", {}
        stage = stages[progress["stage"]]
        here = self.world.world_of(self.npcs[nid]["room"] or self.npc_defs[nid]["home"])
        rooms = [c["room"] for c in stage.get("clues") or []]
        near = any(self.world.world_of(r) == here for r in rooms)
        return ("near" if near else "far"), {"have": progress["stage"], "total": len(stages)}

    def _live_pet(self, session, nid):
        mood_of = getattr(self, "pet_mood", None)
        pets = self.pets_of(session.char) if hasattr(self, "pets_of") else [
            c for c in self.store.companions_of(session.char["id"])
            if self.world.things.get(c["kind"], {}).get("type") == "pet"]
        if not pets:
            return "none", {}
        pet = pets[0]
        mood = mood_of(pet) if mood_of else 60
        return ("happy" if mood >= 70 else "sad" if mood < 30 else None), {"pet": pet["name"]}

    def _live_arcade(self, session, nid):
        best = []
        for gid in self.econ.get("arcade", {}).get("games", {}):
            top = self.store.arcade_top(gid, 1)
            if top:
                best.append((gid, top[0]))
        if not best:
            return "none", {}
        gid, (name, score) = self.npc_rng.choice(best)
        return None, {"name": name, "score": score, "game": self.arcade_game(gid)["name"]}

    def _live_duels(self, session, nid):
        top = self.store.top("duels_won", 1, exclude=self.admins)
        if not top or top[0][1] <= 0:
            return "none", {}
        return None, {"name": top[0][0], "won": top[0][1]}

    def _live_tournament(self, session, nid):
        finder = getattr(self, "tournament_status", None)
        if finder is None:
            return None, {}
        return finder()

    def _live_contraband(self, session, nid):
        goods = [gid for gid, g in self.world.goods.items() if g.get("kind") == "contraband"]
        if not goods:
            return None, {}
        gid = self.npc_rng.choice(sorted(goods))
        wid = self.world.world_of(self.npcs[nid]["room"] or self.npc_defs[nid]["home"])
        price = self.market.unit_price(gid, session.char["job"], "buy", fees=self.fees_for(session.char), world=wid)
        return None, {"good": self.world.goods[gid]["one"], "price": int(round(price))}

    def _live_weddings(self, session, nid):
        now = self.now()
        for wedding in self.store.weddings_with(["booked"]):
            if float(wedding["starts"]) > now:
                a, b = self._couple_names(wedding)
                return "next", dict(self._when_params(wedding["starts"]), a=a, b=b,
                                    place=self.world.locations[wedding["venue"]]["ref"])
        return None, {}

    def _live_tiers(self, session, nid):
        tiers = self.econ.get("weddings", {}).get("tiers", {})
        return None, {"simple": int(tiers.get("simple", {}).get("price", 0)),
                      "grand": int(tiers.get("grand", {}).get("price", 0)),
                      "lux": int(tiers.get("luxurious", {}).get("price", 0))}
