# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Families (economy.json "family"): partners, and children adopted into them.

  partner with Sam                  a proposal; Sam says accept or decline
  partner                           your partnership (and family)
  end partnership                   asks you to be sure...
  confirm end                       ...and ends it, kindly
  adopt                             at the Medbay's family desk: a baby of your own
                                    (partners decide together; one player may too)
  family                            your partner and children, and how the children are
  feed, play with, rest Lily
  read a story to Lily
  ask Lily for help                 once a day, a small thing fetched for you
  bring Lily                        Lily comes along with you
  naming rite Lily                  at the temple, with the keeper: the baby's name

Partnerships need both players to say yes, and ending one needs a second,
clear command; the other partner is told kindly, even if they're away, and
admins can end one for players who can't (end partnership Sam). Weddings
(orbit_weddings.py) take partners further: engaged, then married.

Why one player may adopt alone: many play on their own, and a family in
this game is about looking after someone, not about having a partner. For
partners, adopting is a choice both make: the other is asked and must say
yes; both are then the child's parents, and stay so if the partnership ends.

A child is a companion (like a pet, in the companions table, owned by its
parents), with a voice of its own. It needs food, play and rest, falling
gently in real time; a child left alone grows quiet and a little sad and
asks for you, and is never harmed. Care helps it grow over real days, from
baby to toddler to child; it learns to say simple things, follows the parent
it's with, speaks up now and then, lends a hand (a little more XP from work
while it's happy at your side, and small things fetched once a day), and
gets its name in a naming rite at the temple of the Way of Starlight: a
lantern lit, its name spoken under the dome, and the star bell, once.
Everything here is kept wholesome: partners are partners, and the text
never turns romantic or anything more.
"""

import datetime
import logging

import orbit_safety
from orbit_lang import LANGUAGES, pick

logger = logging.getLogger("orbit.game")

FAMILY_DEFAULTS = {
    "ask_seconds": 120,
    "snub_seconds": 600,
    "partner_cooldown": 86400,
    "confirm_seconds": 60,
    "adopt_price": 300,
    "adopt_level": 3,
    "adopt_days": 3,
    "max_children": 2,
    "decay": {"food": 1.5, "fun": 2.0, "rest": 1.0},
    "start": {"food": 80, "fun": 80, "rest": 80},
    "play": {"fun": 30, "rest": -5, "cooldown": 300},
    "story": {"fun": 15, "rest": 15, "cooldown": 600},
    "rest": {"rest": 45, "cooldown": 1200},
    "full": 95,
    "care_below": 75,
    "sad": 30,
    "happy": 70,
    "stages": [{"care": 0, "days": 0}, {"care": 6, "days": 2}, {"care": 18, "days": 5}],
    "xp_bonus": 0.05,
    "fetch": {"kerupuk": 40, "seed_kangkung": 25, "pet_treat": 20, "iced_coffee": 15},
    "speak_gap": [600, 1200],
    "lines": {},
    "desc": {},
}
NEEDS = ("food", "fun", "rest")
CHILD_WORDS = {"child", "baby", "kid", "my child", "my baby", "my kid", "the baby", "the child", "the kid",
               "little one"}
HELP_WORDS = {"help", "fetch", "errand", "for help", "a hand"}


class FamilyMixin:
    @staticmethod
    def commands():
        return {"partner": FamilyMixin.cmd_partner, "adopt": FamilyMixin.cmd_adopt,
                "family": FamilyMixin.cmd_family, "child": FamilyMixin.cmd_child,
                "naming": FamilyMixin.cmd_naming}

    def init_family(self):
        self.family_asks = {}        # the asked player's key -> {"kind", "from", "from_name", "at", "expires", ...}
        self.rites = []              # naming rites in progress: steps still to be said
        self._child_speak = {}       # child id -> when it may speak up next

    def family_rules(self):
        rules = dict(FAMILY_DEFAULTS)
        rules.update(self.econ.get("family") or {})
        return rules

    # --- partnerships ---------------------------------------------------------------------------

    def partner_of(self, char):
        """(the partnership, the other character's id) or (None, None)."""
        p = self.store.partnership_of(char["id"])
        if p is None:
            return None, None
        return p, (p["b"] if p["a"] == char["id"] else p["a"])

    def _partner_name(self, other_id):
        stored = self.store.by_id(other_id)
        return stored["name"] if stored else "?"

    def cmd_partner(self, session, message):
        op = self._arg(message, "op", 20) or "status"
        name = self._arg(message, "to", 40)
        if op == "ask":
            self._partner_ask(session, name)
        elif op == "end":
            if name and self.is_admin(session) and orbit_safety.name_key(name) != session.key:
                self._admin_partner_end(session, name)
            else:
                self._partner_end(session)
        elif op == "end_confirm":
            self._partner_end_confirm(session)
        else:
            self.cmd_family(session, message)

    def _partner_ask(self, session, name):
        char = session.char
        rules = self.family_rules()
        if self._muted(session):
            return
        target = self._find_session(name) if name else None
        if target is None or target.conn is None or (target.invisible and not self.is_admin(session)):
            self._error(session, "no_player", name=name or "?")
            return
        if target is session:
            self._error(session, "partner_self")
            return
        mine, other = self.partner_of(char)
        if mine is not None:
            self._error(session, "partner_have", name=self._partner_name(other))
            return
        theirs, _o = self.partner_of(target.char)
        if theirs is not None:
            self._error(session, "partner_they_have", name=target.name)
            return
        for who in (char, target.char):
            ended = self.store.last_partnership_end(who["id"])
            if ended and self.now() - ended < float(rules["partner_cooldown"]):
                self._error(session, "partner_too_soon", name=who["name"],
                            time=self._duration(session.lang, ended + float(rules["partner_cooldown"]) - self.now()))
                return
        snub = (char["stats"].get("family_snubs") or {}).get(target.key)
        if snub and float(snub) > self.now():
            self._error(session, "partner_snubbed", name=target.name,
                        time=self._duration(session.lang, float(snub) - self.now()))
            return
        waiting = self.family_asks.get(target.key)
        if waiting and waiting["from"] == session.key:
            self._error(session, "partner_waiting", name=target.name)
            return
        if not self._slow(session):
            return
        now = self.now()
        self.family_asks[target.key] = {"kind": "partner", "from": session.key, "from_name": session.name, "at": now,
                                        "expires": now + float(rules["ask_seconds"])}
        self._send(target, "offer", "partner_asked", extra={"actor": session.name, "ask": "partner", "sound": "offer"},
                   name=session.name, time=self._duration(target.lang, float(rules["ask_seconds"])))
        self._info(session, "partner_ask_sent", name=target.name)

    def accept_family(self, session):
        ask = self.family_asks.pop(session.key, None)
        if ask is None:
            return False
        handler = getattr(self, f"_accept_{ask['kind']}", None)
        if handler is None:
            return False
        handler(session, ask)
        return True

    def decline_family(self, session):
        ask = self.family_asks.pop(session.key, None)
        if ask is None:
            return False
        other = self.sessions.get(ask["from"])
        if other is not None:
            snubs = other.char["stats"].setdefault("family_snubs", {})
            snubs[session.key] = self.now() + float(self.family_rules()["snub_seconds"])
            self._send(other, "system", f"{ask['kind']}_declined", name=session.name)
        self._info(session, f"{ask['kind']}_you_declined", name=ask["from_name"])
        handler = getattr(self, f"_declined_{ask['kind']}", None)
        if handler is not None:
            handler(session, ask)
        return True

    def _accept_partner(self, session, ask):
        other = self.sessions.get(ask["from"])
        if other is None or other.conn is None:
            self._error(session, "partner_gone", name=ask["from_name"])
            return
        for who, name in ((session.char, session.name), (other.char, other.name)):
            if self.partner_of(who)[0] is not None:
                self._error(session, "partner_they_have", name=name)
                return
        self.store.add_partnership(session.char["id"], other.char["id"], "partners", self.now())
        logger.info("%s and %s are partners", other.name, session.name)
        self._send(session, "paid", "partner_formed", name=other.name, extra={"sound": "npc_warm"})
        self._send(other, "paid", "partner_formed", name=session.name, extra={"sound": "npc_warm"})

    def _partner_end(self, session):
        p, other = self.partner_of(session.char)
        if p is None:
            self._error(session, "partner_none")
            return
        session.end_confirm = self.now() + float(self.family_rules()["confirm_seconds"])
        key = {"married": "partner_end_sure_married", "engaged": "partner_end_sure_engaged"}.get(
            p["status"], "partner_end_sure")
        self._info(session, key, name=self._partner_name(other))

    def _partner_end_confirm(self, session):
        until = getattr(session, "end_confirm", 0)
        session.end_confirm = 0
        p, other = self.partner_of(session.char)
        if p is None:
            self._error(session, "partner_none")
            return
        if not until or until < self.now():
            self._error(session, "partner_end_first")
            return
        self.end_partnership(p, by=session.name)
        self._info(session, "partner_ended_you", name=self._partner_name(other))

    def end_partnership(self, p, by, admin=False):
        """A partnership ends: kept as ended, both told kindly (the one away when they come back)."""
        p["status"] = "ended"
        p["ended"] = self.now()
        p["ended_by"] = by
        self.store.save_partnership(p)
        logger.info("a partnership ended (%s)", by)
        cancel = getattr(self, "weddings_partnership_ended", None)
        if cancel is not None:
            cancel(p)
        for char_id, other_id in ((p["a"], p["b"]), (p["b"], p["a"])):
            stored = self.store.by_id(char_id)
            if stored is None or (stored["name"] == by and not admin):
                continue
            session = self.sessions.get(stored["name_key"])
            key = "partner_ended_admin" if admin else "partner_ended_other"
            if session is not None and session.conn is not None:
                self._send(session, "system", key, name=self._partner_name(other_id))
            else:
                char = session.char if session else stored
                char["stats"]["family_note"] = {"key": key, "name": self._partner_name(other_id)}
                self.store.save(char)

    def _admin_partner_end(self, session, name):
        char = self._char_by_key(orbit_safety.name_key(name))
        if char is None:
            self._error(session, "no_character", name=name)
            return
        p, other = self.partner_of(char)
        if p is None:
            self._error(session, "partner_none_for", name=char["name"])
            return
        self.end_partnership(p, by=session.name, admin=True)
        self._log(session, "end partnership", char["name"], self._partner_name(other))
        self._info(session, "partner_ended_by_admin", a=char["name"], b=self._partner_name(other))

    def family_join_notes(self, session):
        """Lines on coming back: a partnership ended while you were away, a child who missed you."""
        notes = []
        note = session.char["stats"].pop("family_note", None)
        if isinstance(note, dict) and note.get("key"):
            notes.append(self.render(session.lang, note["key"], name=note.get("name", "?")))
        for child in self.children_of(session.char):
            if self.child_mood(child) < float(self.family_rules()["sad"]):
                notes.append(self.render(session.lang, "child_missed_you", child=self.child_name(session.lang, child)))
                break
        return notes

    def forget_family_asks(self, session):
        self.family_asks.pop(session.key, None)
        for key, ask in list(self.family_asks.items()):
            if ask["from"] == session.key:
                self.family_asks.pop(key, None)

    def tick_family_asks(self, now):
        for key, ask in list(self.family_asks.items()):
            if now >= ask["expires"]:
                self.family_asks.pop(key, None)
                target, asker = self.sessions.get(key), self.sessions.get(ask["from"])
                if target is not None:
                    self._send(target, "system", "family_ask_expired_you", name=ask["from_name"])
                if asker is not None:
                    self._send(asker, "system", "family_ask_expired", name=target.name if target else "?")

    # --- children ----------------------------------------------------------------------------------

    def children_of(self, char):
        return [c for c in self.store.companions_of(char["id"]) if c["kind"] == "child"]

    def child_name(self, lang, child):
        return child["name"] or self.render(lang, "child_unnamed")

    def child_stage(self, child):
        return int(child.get("stats", {}).get("stage", 0))

    def child_needs(self, child):
        rules = self.family_rules()
        stats = child.setdefault("stats", {})
        needs = stats.get("needs")
        if not isinstance(needs, dict):
            needs = dict(rules["start"], at=self.now())
            stats["needs"] = needs
        hours = max(0.0, (self.now() - float(needs.get("at", self.now()))) / 3600.0)
        return {n: max(0.0, min(100.0, float(needs.get(n, rules["start"][n])) - float(rules["decay"][n]) * hours))
                for n in NEEDS}

    def _set_child_needs(self, child, needs):
        child["stats"]["needs"] = {n: round(max(0.0, min(100.0, needs[n])), 2) for n in NEEDS}
        child["stats"]["needs"]["at"] = self.now()

    def child_mood(self, child):
        needs = self.child_needs(child)
        return int(round(sum(needs.values()) / len(NEEDS)))

    def _child_named(self, char, text):
        """Your child that `text` names (or the only one, for "the baby"), or None."""
        children = self.children_of(char)
        if not children:
            return None
        key = orbit_safety.name_key(text)
        for child in children:
            if child["name"] and orbit_safety.name_key(child["name"]) == key:
                return child
        if key in CHILD_WORDS:
            return children[0]
        return None

    def family_child_care(self, session, op, text):
        """ "feed Lily", "play with Lily", "rest Lily": a child of yours, when named."""
        words = str(text or "").split()
        for n in range(min(3, len(words)), 0, -1):
            child = self._child_named(session.char, " ".join(words[:n]))
            if child is not None:
                self._child_do(session, child, op, " ".join(words[n:]))
                return True
        return False

    def cmd_child(self, session, message):
        op = self._arg(message, "op", 20) or "status"
        text = self._arg(message, "a", 60) or self._arg(message, "to", 60)
        if op == "status":
            self.cmd_family(session, message)
            return
        child = self._child_named(session.char, text) or self._child_named(session.char, text.split()[0] if text
                                                                           else "child")
        if child is None:
            self._error(session, "child_none" if not self.children_of(session.char) else "child_which",
                        children=[self.child_name(session.lang, c) for c in self.children_of(session.char)])
            return
        self._child_do(session, child, op, text)

    def _child_do(self, session, child, op, rest=""):
        handler = {"feed": self._child_feed, "play": self._child_play, "rest": self._child_rest,
                   "story": self._child_story, "fetch": self._child_fetch, "take": self._child_take,
                   "talk": self._child_talk}.get(op)
        if handler is None:
            self.cmd_family(session, {})
            return
        handler(session, child, rest)

    def _child_cooldown(self, child, name):
        return max(0.0, float((child["stats"].get("cool") or {}).get(name, 0)) - self.now())

    def _child_set_cooldown(self, child, name, seconds):
        child["stats"].setdefault("cool", {})[name] = self.now() + float(seconds)

    def _child_food(self, char, stage):
        foods = ["baby_porridge"] if stage == 0 else ["baby_porridge", "martabak", "kerupuk"]
        return next((tid for tid in foods if self.owns(char, tid)), None)

    def _child_feed(self, session, child, rest):
        char, lang = session.char, session.lang
        rules = self.family_rules()
        name = self.child_name(lang, child)
        food = self._child_food(char, self.child_stage(child))
        if food is None:
            self._error(session, "child_no_food" if self.child_stage(child) == 0 else "child_no_snack", child=name)
            return
        needs = self.child_needs(child)
        if needs["food"] >= float(rules["full"]):
            self._info(session, "child_full", child=name)
            return
        if not self._slow(session):
            return
        before = dict(needs)
        needs["food"] += float((self.world.things[food].get("effects") or {}).get("child_food", 30))
        self._set_child_needs(child, needs)
        self._take_away(char, food, 1)
        grew = self._child_care(child, before["food"], session.char)
        self.store.save_companion(child)
        self._save(session)
        self._send(session, "emote", f"child_fed_{self.child_stage(child)}", child=name,
                   thing=self.world.things[food]["one"], extra={"sound": "baby"})
        self._child_grew(session, child, grew)

    def _child_play(self, session, child, rest):
        rules = self.family_rules()
        name = self.child_name(session.lang, child)
        left = self._child_cooldown(child, "play")
        if left > 0:
            self._error(session, "child_play_wait", child=name, time=self._duration(session.lang, left))
            return
        if not self._slow(session):
            return
        needs = self.child_needs(child)
        before = dict(needs)
        needs["fun"] += float(rules["play"]["fun"])
        needs["rest"] += float(rules["play"]["rest"])
        self._set_child_needs(child, needs)
        self._child_set_cooldown(child, "play", rules["play"]["cooldown"])
        grew = self._child_care(child, before["fun"], session.char)
        self.store.save_companion(child)
        self._send(session, "emote", f"child_play_{self.child_stage(child)}", child=name, extra={"sound": "baby"})
        self._to_room(self.room_of(session.char), "emote", "child_play_other", exclude=(session,),
                      extra={"actor": session.name}, actor=session.name, child=name)
        self._child_grew(session, child, grew)

    def _child_story(self, session, child, rest):
        rules = self.family_rules()
        name = self.child_name(session.lang, child)
        left = self._child_cooldown(child, "story")
        if left > 0:
            self._error(session, "child_story_wait", child=name, time=self._duration(session.lang, left))
            return
        needs = self.child_needs(child)
        before = dict(needs)
        needs["fun"] += float(rules["story"]["fun"])
        needs["rest"] += float(rules["story"]["rest"])
        self._set_child_needs(child, needs)
        self._child_set_cooldown(child, "story", rules["story"]["cooldown"])
        grew = self._child_care(child, min(before["fun"], before["rest"]), session.char)
        self.store.save_companion(child)
        self._send(session, "emote", "child_story", child=name, extra={"sound": "baby"})
        self._child_grew(session, child, grew)

    def _child_rest(self, session, child, rest):
        rules = self.family_rules()
        name = self.child_name(session.lang, child)
        needs = self.child_needs(child)
        if self._child_cooldown(child, "rest") > 0 or needs["rest"] >= float(rules["full"]):
            self._info(session, "child_not_sleepy", child=name)
            return
        before = dict(needs)
        needs["rest"] += float(rules["rest"]["rest"])
        self._set_child_needs(child, needs)
        self._child_set_cooldown(child, "rest", rules["rest"]["cooldown"])
        grew = self._child_care(child, before["rest"], session.char)
        self.store.save_companion(child)
        self._send(session, "emote", "child_rested", child=name)
        self._child_grew(session, child, grew)

    def _child_care(self, child, need_before, char):
        """Care for a low need helps a child grow (over real days). The new stage, if it grew."""
        rules = self.family_rules()
        stats = child["stats"]
        stats["with"] = char["id"]
        if need_before < float(rules["care_below"]):
            stats["care"] = int(stats.get("care") or 0) + 1
        stage = self.child_stage(child)
        stages = rules["stages"]
        days = (self.now() - float(stats.get("born") or child.get("created") or self.now())) / 86400.0
        grew = None
        while stage + 1 < len(stages) and int(stats.get("care") or 0) >= int(stages[stage + 1]["care"]) and \
                days >= float(stages[stage + 1]["days"]):
            stage += 1
            grew = stage
        stats["stage"] = stage
        return grew

    def _child_grew(self, session, child, stage):
        """A child grew up a stage: the parents online hear it, and its first new words."""
        if stage is None:
            return
        first = self._child_lines(stage)
        for parent in self._parents_online(child):
            name = self.child_name(parent.lang, child)
            words = self._npc_fill(parent.lang, pick(first[0], parent.lang), {"parent": session.name, "child": name})                 if first else ""
            self._send(parent, "paid", f"child_grew_{stage}", child=name, words=words, extra={"sound": "levelup"})

    def _child_lines(self, stage):
        return (self.family_rules().get("lines") or {}).get(str(stage)) or []

    def _parents_online(self, child):
        owners = {char_id for char_id, _role in self.store.companion_owners(child["id"])}
        return [s for s in self.sessions.values() if s.char["id"] in owners and s.conn is not None]

    def _child_fetch(self, session, child, rest):
        char, lang = session.char, session.lang
        name = self.child_name(lang, child)
        if self.child_stage(child) == 0:
            self._error(session, "child_too_little", child=name)
            return
        if child["stats"].get("fetched") == self.today():
            self._info(session, "child_fetched_today", child=name)
            return
        if self.child_mood(child) < float(self.family_rules()["sad"]):
            self._error(session, "child_sad_help", child=name)
            return
        child["stats"]["fetched"] = self.today()
        table = self.family_rules()["fetch"]
        tid = self._pick(table) if self.child_stage(child) >= 2 else "kerupuk"
        n = 2 if tid.startswith("seed_") else 1
        self.give_thing(char, tid, n)
        self.store.save_companion(child)
        self._save(session)
        self._send(session, "paid", f"child_fetch_{self.child_stage(child)}", child=name,
                   things=self._count_of(tid, n), extra={"sound": "baby"})

    def _child_take(self, session, child, rest):
        child["stats"]["with"] = session.char["id"]
        self.store.save_companion(child)
        self._info(session, "child_with_you", child=self.child_name(session.lang, child))

    def _child_talk(self, session, child, rest):
        """Talking with your child: they answer as a child of their age can."""
        self._child_speaks([session], child, session.name)

    def _child_speaks(self, sessions, child, parent_name):
        lines = self._child_lines(self.child_stage(child))
        if not lines:
            return
        line = lines[self.npc_rng.randrange(len(lines))]
        name_by = {s: self.child_name(s.lang, child) for s in sessions}
        voice = int(child["stats"].get("voice") or 1)
        for other in sessions:
            words = self._npc_fill(other.lang, pick(line, other.lang), {"parent": parent_name, "child": name_by[other]})
            if line.get("kind") == "emote":
                self._send(other, "emote", text=words, extra={"actor": name_by[other], "sound": "baby"})
            else:
                self._send(other, "say", "say_other", extra={"actor": name_by[other], "voice": voice, "words": words},
                           actor=name_by[other], words=words)

    # --- adopting ----------------------------------------------------------------------------------

    def cmd_adopt(self, session, message):
        char, lang = session.char, session.lang
        rules = self.family_rules()
        if not self._loc(char).get("family_desk"):
            desk = next((lid for lid, loc in self.world.locations.items() if loc.get("family_desk")), None)
            self._error(session, "adopt_where", where=self.world.locations[desk]["in"] if desk else "?")
            return
        problem = self._adopt_problem(char, lang)
        if problem:
            self._error(session, problem[0], **problem[1])
            return
        p, other_id = self.partner_of(char)
        if p is not None:
            other = next((s for s in self.sessions.values() if s.char["id"] == other_id and s.conn is not None), None)
            if other is None:
                self._error(session, "adopt_partner_away", name=self._partner_name(other_id))
                return
            problem = self._adopt_problem(other.char, other.lang, partner=True)
            if problem:
                self._error(session, problem[0], **problem[1])
                return
            now = self.now()
            self.family_asks[other.key] = {"kind": "adopt", "from": session.key, "from_name": session.name, "at": now,
                                           "expires": now + float(rules["ask_seconds"])}
            self._send(other, "offer", "adopt_asked", extra={"actor": session.name, "ask": "adopt", "sound": "offer"},
                       name=session.name, price=int(rules["adopt_price"]))
            self._info(session, "adopt_ask_sent", name=other.name)
            return
        self._adopt(session, [char])

    def _adopt_problem(self, char, lang, partner=False):
        rules = self.family_rules()
        if not partner and char["credits"] < int(rules["adopt_price"]):
            return "adopt_poor", {"price": int(rules["adopt_price"]), "credits": char["credits"]}
        if not partner and self.level_of(int(char.get("xp") or 0)) < int(rules["adopt_level"]):
            return "adopt_level", {"level": int(rules["adopt_level"])}
        if len(self.children_of(char)) >= int(rules["max_children"]):
            return "adopt_full", {"name": char["name"], "n": int(rules["max_children"])}
        last = float(char["stats"].get("adopted") or 0)
        wait = last + float(rules["adopt_days"]) * 86400 - self.now()
        if wait > 0:
            return "adopt_wait", {"name": char["name"], "time": self._duration(lang, wait)}
        return None

    def _accept_adopt(self, session, ask):
        other = self.sessions.get(ask["from"])
        if other is None or other.conn is None:
            self._error(session, "partner_gone", name=ask["from_name"])
            return
        p, other_id = self.partner_of(session.char)
        if p is None or other_id != other.char["id"]:
            self._error(session, "partner_none")
            return
        problem = self._adopt_problem(other.char, other.lang) or self._adopt_problem(session.char, session.lang,
                                                                                     partner=True)
        if problem:
            self._error(session, problem[0], **problem[1])
            self._send(other, "error", problem[0], **problem[1])
            return
        self._adopt(other, [other.char, session.char])

    def _adopt(self, session, parents):
        """A baby joins the family: the fee paid by `session`, `parents` its parents."""
        char = session.char
        rules = self.family_rules()
        price = int(rules["adopt_price"])
        with self.store.transaction():
            self.spend(char, price, "adoption")
            stats = {"born": self.now(), "voice": self.rng.randint(1, 10), "stage": 0, "care": 0,
                     "with": char["id"], "needs": dict(rules["start"], at=self.now())}
            comp_id = self.store.add_companion("child", "", [parents[0]["id"]], stats=stats)
            for parent in parents[1:]:
                self.store.add_companion_owner(comp_id, parent["id"], "parent")
            for parent in parents:
                parent["stats"]["adopted"] = self.now()
                self.store.save(parent)
        logger.info("%s adopted a baby", " and ".join(p["name"] for p in parents))
        for parent in parents:
            s = self.sessions.get(parent["name_key"])
            if s is not None:
                others = [p["name"] for p in parents if p is not parent]
                self._send(s, "paid", "adopted_with" if others else "adopted", name=others[0] if others else "",
                           price=price, credits=parent["credits"], extra={"sound": "baby"})

    # --- the naming rite --------------------------------------------------------------------------

    def cmd_naming(self, session, message):
        char, lang = session.char, session.lang
        name = orbit_safety.tidy(self._arg(message, "a", 40), 16)
        if not self._loc(char).get("temple"):
            temple = next((lid for lid, loc in self.world.locations.items() if loc.get("temple")), None)
            self._error(session, "naming_where", where=self.world.locations[temple]["in"] if temple else "?")
            return
        unnamed = [c for c in self.children_of(char) if not c["name"]]
        if not unnamed:
            self._error(session, "naming_nobody" if not self.children_of(char) else "naming_all_named")
            return
        keeper = next((nid for nid, d in self.npc_defs.items() if d.get("home") == char["location"]), None)
        if keeper is None or self.npcs[keeper]["room"] != char["location"]:
            self._error(session, "naming_keeper_away")
            return
        if not name or len(name) < 2 or not all(c.isalpha() or c in " -'" for c in name) or self.filter.contains(name):
            self._error(session, "naming_bad")
            return
        if any(r["room"] == char["location"] for r in self.rites):
            self._error(session, "naming_busy")
            return
        child = unnamed[0]
        child["name"] = name[0].upper() + name[1:]
        child["stats"]["named"] = self.now()
        child["stats"]["with"] = char["id"]
        self.store.save_companion(child)
        logger.info("%s named a child %s", session.name, child["name"])
        now = self.now()
        room = char["location"]
        steps = [(0.0, "say", "rite_welcome", None), (4.0, "emote", "rite_lantern", "lantern"),
                 (8.0, "say", "rite_name", None), (11.0, "emote", "rite_bell", "bell"),
                 (14.0, "info", "rite_done", "npc_warm")]
        self.rites.append({"room": room, "keeper": keeper, "child": child["name"], "parent": session.name,
                           "child_id": child["id"], "steps": [(now + at, kind, key, sound) for at, kind, key, sound in steps]})
        self._send(session, "info", "naming_begins", child=child["name"])
        self.tick_rites(now)

    def tick_rites(self, now):
        for rite in list(self.rites):
            while rite["steps"] and now >= rite["steps"][0][0]:
                _at, kind, key, sound = rite["steps"].pop(0)
                listeners = self._in_room(rite["room"])
                params = {"child": rite["child"], "parent": rite["parent"]}
                if kind == "say":
                    self.npc_say(listeners, rite["keeper"], {lang: self.texts.raw(lang, key) for lang in LANGUAGES},
                                 **params)
                elif kind == "emote":
                    self.npc_emote(listeners, rite["keeper"], {lang: self.texts.raw(lang, key) for lang in LANGUAGES},
                                   extra={"sound": sound}, **params)
                else:
                    for other in listeners:
                        self._send(other, "paid", key, extra={"sound": sound}, **params)
            if not rite["steps"]:
                self.rites.remove(rite)

    # --- how the family looks ----------------------------------------------------------------------

    def family_lines(self, lang, char):
        """What others see when they look at you: your partner, and the child at your side."""
        lines = []
        p, other_id = self.partner_of(char)
        if p is not None:
            lines.append(self.render(lang, f"look_partner_{p['status']}", name=self._partner_name(other_id)))
        for child in self.children_of(char):
            if int(child["stats"].get("with") or 0) == char["id"]:
                lines.append(self.render(lang, "look_child", child=self.child_name(lang, child),
                                         stage=self.render(lang, f"child_stage_{self.child_stage(child)}")))
        return lines

    def _need_words(self, lang, needs):
        words = []
        for need in NEEDS:
            level = "high" if needs[need] >= 70 else "mid" if needs[need] >= 40 else "low"
            words.append(self.render(lang, f"child_{need}_{level}"))
        return words

    def child_status_line(self, lang, child):
        rules = self.family_rules()
        mood = self.child_mood(child)
        key = "child_mood_happy" if mood >= rules["happy"] else "child_mood_sad" if mood < rules["sad"] \
            else "child_mood_ok"
        name = self.child_name(lang, child)
        return self.render(lang, "child_status", child=name,
                           stage=self.render(lang, f"child_stage_{self.child_stage(child)}"),
                           needs=self._need_words(lang, self.child_needs(child)),
                           mood=self.render(lang, key, child=name))

    def cmd_family(self, session, message):
        lang, char = session.lang, session.char
        parts = []
        p, other_id = self.partner_of(char)
        if p is not None:
            since = datetime.datetime.fromtimestamp(float(p["married"] or p["engaged"] or p["since"]),
                                                    datetime.timezone.utc)
            parts.append(self.render(lang, f"family_partner_{p['status']}", name=self._partner_name(other_id),
                                     date=since.strftime("%d-%m-%Y")))
        else:
            parts.append(self.render(lang, "family_no_partner"))
        children = self.children_of(char)
        for child in children:
            parts.append(self.child_status_line(lang, child))
        if not children:
            parts.append(self.render(lang, "family_no_children"))
        self._info(session, text="\n".join(parts))

    def companion_look(self, session, text):
        """ "look Mira", "look Kiki": a child or pet in the room, with a word that it isn't a player."""
        lang = session.lang
        room = self.room_of(session.char)
        for owner in [session] + self._in_room(room, exclude=(session,), visible=True):
            for child in self.children_of(owner.char):
                if child["name"] and orbit_safety.name_key(child["name"]) == orbit_safety.name_key(text) and \
                        int(child["stats"].get("with") or 0) == owner.char["id"]:
                    desc = (self.family_rules().get("desc") or {}).get(str(self.child_stage(child)))
                    return "\n".join(line for line in [
                        self.render(lang, "child_look", child=child["name"], parent=owner.name,
                                    stage=self.render(lang, f"child_stage_{self.child_stage(child)}")),
                        pick(desc, lang) if desc else "",
                        self.child_status_line(lang, child) if owner is session else ""] if line)
            for comp in self.pets_of(owner.char):
                if orbit_safety.name_key(comp["name"]) == orbit_safety.name_key(text):
                    thing = self.world.things[comp["kind"]]
                    parts = [self.render(lang, "pet_look", pet=comp["name"], owner=owner.name,
                                         species=self.pet_kind(comp).get("kind", comp["kind"])),
                             pick(thing.get("desc") or thing["one"], lang)]
                    if owner is session:
                        parts.append(self.pet_status_line(lang, comp))
                    return "\n".join(parts)
        return None

    def family_emote_at(self, session, name, eid, emote):
        """A gesture at a child in the room. False: no child by that name."""
        room = self.room_of(session.char)
        for owner in [session] + self._in_room(room, exclude=(session,), visible=True):
            for child in self.children_of(owner.char):
                if not child["name"] or orbit_safety.name_key(child["name"]) != orbit_safety.name_key(name) or \
                        int(child["stats"].get("with") or 0) != owner.char["id"]:
                    continue
                if not session.chat.take():
                    self._error(session, "slow_down")
                    return True
                self._send(session, "emote", text=emote[session.lang]["you_at"].format(target=child["name"]),
                           extra={"emote": eid})
                for other in self._in_room(room, exclude=(session,)):
                    self._send(other, "emote", text=emote[other.lang]["they_at"].format(actor=session.name,
                                                                                        target=child["name"]),
                               extra={"actor": session.name, "emote": eid})
                for other in self._in_room(room):
                    self._send(other, "emote", "child_react", child=child["name"], actor=session.name,
                               extra={"actor": child["name"], "sound": "baby"})
                return True
        return False

    def family_xp_factor(self, char):
        """A happy child at your side lends a hand: a little more XP from work."""
        for child in self.children_of(char):
            if int(child["stats"].get("with") or 0) == char["id"] and self.child_stage(child) >= 2 and \
                    self.child_mood(child) >= float(self.family_rules()["happy"]):
                return 1.0 + float(self.family_rules()["xp_bonus"])
        return 1.0

    # --- time passing ------------------------------------------------------------------------------

    def tick_family(self, now):
        self.tick_family_asks(now)
        self.tick_rites(now)
        for session in list(self.sessions.values()):
            if session.conn is None or session.away or now < getattr(session, "child_check", 0):
                continue
            session.child_check = now + 30
            room = self.room_of(session.char)
            if now - self.room_chat.get(room, -1e12) < float(self.npc_rules["quiet_seconds"]):
                continue
            for child in self.children_of(session.char):
                if int(child["stats"].get("with") or 0) != session.char["id"] or not child["name"]:
                    continue
                if now < self._child_speak.get(child["id"], 0):
                    continue
                low, high = self.family_rules()["speak_gap"]
                first = child["id"] not in self._child_speak
                self._child_speak[child["id"]] = now + self.npc_rng.uniform(float(low), float(high))
                if first:
                    continue
                if self.child_mood(child) < float(self.family_rules()["sad"]):
                    self._send(session, "info", "child_asks_for_you", child=child["name"], extra={"sound": "baby"})
                    continue
                self._child_speaks(self._listeners(room), child, session.name)
