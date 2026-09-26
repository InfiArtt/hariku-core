# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Pets (economy.json "pets", and each kind's "pet" in its thing): a little
robot, an orange space cat, a robot cat, a space fox, a glow jellyfish and
a mini drone, from Whiskers & Widgets on the Mall Ring; the fox, the
jellyfish and the drone also turn up, rarely, out on the worlds.

  pet status                       how they are: fed, played with, rested
  feed Kiki                        pet food or a treat (the pet shop sells both)
  play with Kiki
  rest Kiki
  pat                              a pat, and a little joy
  teach trick sit                  a lesson (a few make a trick)
  trick sit                        show a trick off
  name pet Kiki, rename Kiki to Momo

A pet's needs (food, fun, rest) fall slowly in real time, a few points an
hour, and gently: a pet left alone grows sad and quiet (no more tricks or
reactions) but never comes to harm, and a meal, some play and a nap always
cheer it up. Caring for a need that was low counts towards growing up:
little, then young (tricks), then grown (its last trick). Pets follow their
owner everywhere (others see them when they look at you), react to your
gestures and to others' gestures at you, and have sounds of their own. A
pet is a companion (orbit_store), its state in the companion's stats.
"""

import logging

import orbit_safety
from orbit_lang import LANGUAGES, pick

logger = logging.getLogger("orbit.game")

PET_DEFAULTS = {
    "decay": {"food": 3.0, "fun": 4.0, "rest": 2.0},     # points an hour
    "start": {"food": 80, "fun": 80, "rest": 80},
    "play": {"fun": 30, "rest": -8, "cooldown": 300},
    "rest": {"rest": 45, "cooldown": 1200},
    "pat_fun": 4,
    "full": 95,                     # a pet this well fed won't eat
    "tired": 15,                    # too tired to play
    "care_below": 75,               # a need met below this is care that helps a pet grow
    "stages": [{"care": 0, "days": 0}, {"care": 8, "days": 2}, {"care": 25, "days": 7}],
    "lessons": 3, "lesson_cooldown": 300, "lesson_rest": 10, "lesson_mood": 40,
    "sad": 30, "happy": 70,
    "nudge_seconds": 3600, "nudge_below": 25,
    "finds": [],
}
NEEDS = ("food", "fun", "rest")
TRICK_WORDS = {"trick", "tricks", "the"}
RENAME_WORDS = ("to", "as")
JOIN_IN = {"dance": "pet_join_dance", "clap": "pet_join_clap", "cheer": "pet_join_cheer",
           "laugh": "pet_join_laugh", "sigh": "pet_join_sigh", "wave": "pet_join_wave", "hug": "pet_join_hug"}


class PetsMixin:
    @staticmethod
    def commands():
        return {"pet": PetsMixin.cmd_pet}

    # --- what a pet is ------------------------------------------------------------------------

    def pet_rules(self):
        rules = dict(PET_DEFAULTS)
        rules.update(self.econ.get("pets") or {})
        return rules

    def pets_of(self, char):
        return [c for c in self.store.companions_of(char["id"])
                if self.world.things.get(c["kind"], {}).get("type") == "pet"]

    def pet_kind(self, comp):
        return (self.world.things.get(comp["kind"], {}).get("effects") or {}).get("pet") or {}

    def pet_sound(self, comp):
        return self.pet_kind(comp).get("sound") or "pet_" + comp["kind"].split("_")[0]

    def new_pet_stats(self, **more):
        """A new pet's stats: when it came, and its needs as they start."""
        return dict({"since": self.now(), "needs": dict(self.pet_rules()["start"], at=self.now())}, **more)

    def pet_needs(self, comp):
        """Food, fun and rest now (0 to 100), fallen since they were last set."""
        rules = self.pet_rules()
        stats = comp.setdefault("stats", {})
        needs = stats.get("needs")
        if not isinstance(needs, dict):
            # A pet from before 1.2: its needs start today, as if it were new.
            needs = dict(rules["start"], at=self.now())
            stats["needs"] = needs
            if comp.get("id") is not None:
                self.store.save_companion(comp)
        hours = max(0.0, (self.now() - float(needs.get("at", self.now()))) / 3600.0)
        return {need: max(0.0, min(100.0, float(needs.get(need, rules["start"][need]))
                                   - float(rules["decay"][need]) * hours)) for need in NEEDS}

    def _set_needs(self, comp, needs):
        comp["stats"]["needs"] = {need: round(max(0.0, min(100.0, needs[need])), 2) for need in NEEDS}
        comp["stats"]["needs"]["at"] = self.now()

    def pet_mood(self, comp):
        needs = self.pet_needs(comp)
        return int(round(sum(needs.values()) / len(NEEDS)))

    def pet_sad(self, comp):
        return self.pet_mood(comp) < float(self.pet_rules()["sad"])

    def pet_stage(self, comp):
        return int(comp.get("stats", {}).get("stage", 0))

    def pet_label(self, lang, comp):
        """ "Kiki, your young space fox"."""
        return self.render(lang, "pet_label", pet=comp["name"], stage=self.render(lang, f"pet_stage_{self.pet_stage(comp)}"),
                           species=self.pet_kind(comp).get("kind", comp["kind"]))

    # --- finding the pet you mean -------------------------------------------------------------

    def _pet_for(self, session, text):
        """(your pet that `text` names, or your first; the words left). None after saying why."""
        pets = self.pets_of(session.char)
        if not pets:
            self._error(session, "no_pet")
            return None, text
        words = str(text or "").split()
        for n in range(min(3, len(words)), 0, -1):
            name = " ".join(words[:n])
            comp = self._pet_named(pets, name)
            if comp is not None:
                return comp, " ".join(words[n:])
        return pets[0], text

    def _pet_named(self, pets, name):
        key = orbit_safety.name_key(name)
        if not key:
            return None
        for comp in pets:
            if orbit_safety.name_key(comp["name"]) == key:
                return comp
        tid = self.world.find_thing(name, fuzzy=False)
        if tid is None and key in ("pet", "my pet", "the pet"):
            return pets[0]
        return next((c for c in pets if c["kind"] == tid), None)

    # --- the command ----------------------------------------------------------------------------

    def cmd_pet(self, session, message):
        op = self._arg(message, "op", 10) or "pat"
        text = self._arg(message, "a", 80)
        family = getattr(self, "family_child_care", None)
        if op in ("feed", "play", "rest") and family and family(session, op, text):
            return                                     # a child of yours, by name
        handler = {"pat": self._pet_pat, "name": self._pet_name, "status": self._pet_status,
                   "feed": self._pet_feed, "play": self._pet_play, "rest": self._pet_rest,
                   "teach": self._pet_teach, "trick": self._pet_trick}.get(op, self._pet_pat)
        handler(session, text, message)

    def _pet_pat(self, session, text, message):
        comp, _rest = self._pet_for(session, text)
        if comp is None or not self._slow(session):
            return
        char = session.char
        needs = self.pet_needs(comp)
        needs["fun"] += float(self.pet_rules()["pat_fun"])
        self._set_needs(comp, needs)
        self.store.save_companion(comp)
        self._send(session, "emote", "pet_pat", pet=comp["name"])
        self._to_room(self.room_of(char), "emote", "pet_pat_other", exclude=(session,),
                      extra={"actor": session.name}, actor=session.name, pet=comp["name"])
        self.pet_reacts(session, chance=1.0, comp=comp)

    def _pet_name(self, session, text, message):
        pets = self.pets_of(session.char)
        if not pets:
            self._error(session, "no_pet")
            return
        words = text.split()
        comp, name = pets[0], text
        low = [w.lower() for w in words]
        sep = next((i for i, w in enumerate(low) if i > 0 and w in RENAME_WORDS), None)
        if sep is not None:
            found = self._pet_named(pets, " ".join(words[:sep]))
            if found is not None:
                comp, name = found, " ".join(words[sep + 1:])
        elif len(pets) > 1 and len(words) >= 2:
            found = self._pet_named(pets, words[0])
            if found is not None:
                comp, name = found, " ".join(words[1:])
        name = orbit_safety.tidy(name, 16)
        if not name or not all(c.isalnum() or c == " " for c in name) or self.filter.contains(name):
            self._error(session, "pet_name_bad")
            return
        comp["name"] = name
        self.store.save_companion(comp)
        self._info(session, "pet_named", pet=name)

    def _need_word(self, lang, need, value):
        level = "high" if value >= 70 else "mid" if value >= 40 else "low"
        return self.render(lang, f"pet_{need}_{level}")

    def pet_status_line(self, lang, comp):
        needs = self.pet_needs(comp)
        mood = self.pet_mood(comp)
        rules = self.pet_rules()
        mood_key = "pet_mood_happy" if mood >= rules["happy"] else "pet_mood_sad" if mood < rules["sad"] else "pet_mood_ok"
        parts = [self.render(lang, "pet_status", pet=self.pet_label(lang, comp),
                             needs=[self._need_word(lang, need, needs[need]) for need in NEEDS],
                             mood=self.render(lang, mood_key, pet=comp["name"]))]
        tricks = self.pet_kind(comp).get("tricks") or {}
        learned = [tricks[t]["names"][lang][0] for t in comp["stats"].get("tricks", []) if t in tricks]
        if learned:
            parts.append(self.render(lang, "pet_tricks_known", tricks=learned))
        lessons = comp["stats"].get("lessons") or {}
        learning = [self.render(lang, "pet_learning", trick=tricks[t]["names"][lang][0], n=int(n),
                                total=int(rules["lessons"]))
                    for t, n in lessons.items() if t in tricks and t not in comp["stats"].get("tricks", [])]
        if learning:
            parts.append(self.render(lang, "pet_learning_list", entries=learning))
        return "\n".join(parts)

    def _pet_status(self, session, text, message):
        pets = self.pets_of(session.char)
        if not pets:
            self._error(session, "no_pet")
            return
        if text:
            comp = self._pet_named(pets, text)
            pets = [comp] if comp is not None else pets
        self._info(session, text="\n".join(self.pet_status_line(session.lang, comp) for comp in pets))

    # --- care --------------------------------------------------------------------------------

    def _pet_food(self, char, text):
        """The pet food you'd use: the one named, else plain food, else a treat."""
        if text:
            tid = self.world.find_thing(text)
            if tid and (self.world.things[tid].get("effects") or {}).get("pet_food") and self.owns(char, tid):
                return tid
        for tid in ("pet_food", "pet_treat"):
            if self.owns(char, tid):
                return tid
        return None

    def _pet_feed(self, session, text, message):
        comp, rest = self._pet_for(session, text)
        if comp is None:
            return
        char, lang = session.char, session.lang
        food = self._pet_food(char, rest or text)
        if food is None:
            self._error(session, "pet_no_food", pet=comp["name"])
            return
        rules = self.pet_rules()
        needs = self.pet_needs(comp)
        if needs["food"] >= float(rules["full"]):
            self._info(session, "pet_full", pet=comp["name"])
            return
        if not self._slow(session):
            return
        effects = self.world.things[food].get("effects") or {}
        before = dict(needs)
        needs["food"] += float(effects.get("pet_food", 0))
        needs["fun"] += float(effects.get("pet_fun", 0))
        self._set_needs(comp, needs)
        self._take_away(char, food, 1)
        grew = self._pet_care(session, comp, before["food"])
        self.store.save_companion(comp)
        self._save(session)
        eat = self.pet_kind(comp).get("eat")
        line = pick(eat, lang).format(pet=comp["name"]) if eat else self.render(lang, "pet_ate", pet=comp["name"])
        self._send(session, "emote", text=self.render(lang, "pet_fed", thing=self.world.things[food]["one"],
                                                      pet=comp["name"]) + " " + line,
                   extra={"sound": self.pet_sound(comp)})
        self._to_room(self.room_of(char), "emote", "pet_fed_other", exclude=(session,),
                      extra={"actor": session.name}, actor=session.name, pet=comp["name"])
        self._pet_grew(session, comp, grew)

    def _pet_cooldown(self, comp, name):
        return max(0.0, float((comp["stats"].get("cool") or {}).get(name, 0)) - self.now())

    def _pet_set_cooldown(self, comp, name, seconds):
        comp["stats"].setdefault("cool", {})[name] = self.now() + float(seconds)

    def _pet_play(self, session, text, message):
        comp, _rest = self._pet_for(session, text)
        if comp is None:
            return
        rules = self.pet_rules()
        needs = self.pet_needs(comp)
        left = self._pet_cooldown(comp, "play")
        if left > 0:
            self._error(session, "pet_play_wait", pet=comp["name"], time=self._duration(session.lang, left))
            return
        if not self._slow(session):
            return
        before = dict(needs)
        gentle = needs["rest"] < float(rules["tired"])           # too tired to run about: a cuddle
        needs["fun"] += float(rules["play"]["fun"]) / (2.0 if gentle else 1.0)
        if not gentle:
            needs["rest"] += float(rules["play"]["rest"])
        self._set_needs(comp, needs)
        self._pet_set_cooldown(comp, "play", rules["play"]["cooldown"])
        grew = self._pet_care(session, comp, before["fun"])
        self.store.save_companion(comp)
        key = "pet_play_gentle" if gentle else "pet_play_cheered" if before["fun"] < float(rules["sad"]) \
            else "pet_play"
        self._send(session, "emote", key, pet=comp["name"], extra={"sound": self.pet_sound(comp)})
        self._to_room(self.room_of(session.char), "emote", "pet_play_other", exclude=(session,),
                      extra={"actor": session.name, "sound": self.pet_sound(comp)}, actor=session.name,
                      pet=comp["name"])
        self._pet_grew(session, comp, grew)

    def _pet_rest(self, session, text, message):
        comp, _rest = self._pet_for(session, text)
        if comp is None:
            return
        rules = self.pet_rules()
        needs = self.pet_needs(comp)
        left = self._pet_cooldown(comp, "rest")
        if left > 0 or needs["rest"] >= float(rules["full"]):
            self._info(session, "pet_not_sleepy", pet=comp["name"])
            return
        before = dict(needs)
        needs["rest"] += float(rules["rest"]["rest"])
        self._set_needs(comp, needs)
        self._pet_set_cooldown(comp, "rest", rules["rest"]["cooldown"])
        grew = self._pet_care(session, comp, before["rest"])
        self.store.save_companion(comp)
        self._send(session, "emote", "pet_rested", pet=comp["name"])
        self._pet_grew(session, comp, grew)

    def _pet_care(self, session, comp, need_before):
        """A need met while it was low: a point towards growing up. Returns the new stage, if any."""
        rules = self.pet_rules()
        stats = comp["stats"]
        if need_before < float(rules["care_below"]):
            stats["care"] = int(stats.get("care") or 0) + 1
        stage = self.pet_stage(comp)
        stages = rules["stages"]
        days = (self.now() - float(stats.get("since") or comp.get("created") or self.now())) / 86400.0
        grew = None
        while stage + 1 < len(stages) and int(stats.get("care") or 0) >= int(stages[stage + 1]["care"]) and \
                days >= float(stages[stage + 1]["days"]):
            stage += 1
            grew = stage
        stats["stage"] = stage
        return grew

    def _pet_grew(self, session, comp, stage):
        if stage is None:
            return
        self._send(session, "paid", "pet_grew", pet=comp["name"], stage=self.render(session.lang, f"pet_stage_{stage}"),
                   extra={"sound": "levelup"})

    # --- tricks -------------------------------------------------------------------------------

    def _trick_named(self, comp, text):
        tricks = self.pet_kind(comp).get("tricks") or {}
        words = [w for w in orbit_safety.name_key(text).split() if w not in TRICK_WORDS]
        key = " ".join(words)
        if not key:
            return None
        for tid, trick in tricks.items():
            names = {orbit_safety.name_key(n) for lang in LANGUAGES for n in trick["names"][lang]} | {tid}
            if key in names:
                return tid
        return None

    def _tricks_list(self, lang, comp):
        tricks = self.pet_kind(comp).get("tricks") or {}
        return [tricks[t]["names"][lang][0] for t in tricks]

    def _pet_teach(self, session, text, message):
        comp, rest = self._pet_for(session, text)
        if comp is None:
            return
        lang = session.lang
        rules = self.pet_rules()
        tid = self._trick_named(comp, rest) or self._trick_named(comp, text)
        if tid is None:
            self._error(session, "pet_teach_what", pet=comp["name"], tricks=self._tricks_list(lang, comp))
            return
        trick = self.pet_kind(comp)["tricks"][tid]
        stats = comp["stats"]
        if tid in stats.get("tricks", []):
            self._info(session, "pet_knows_trick", pet=comp["name"], trick=trick["names"][lang][0])
            return
        if self.pet_stage(comp) < int(trick.get("stage", 1)):
            self._error(session, "pet_too_young", pet=comp["name"], trick=trick["names"][lang][0],
                        stage=self.render(lang, f"pet_stage_{int(trick.get('stage', 1))}"))
            return
        left = self._pet_cooldown(comp, "lesson")
        if left > 0:
            self._error(session, "pet_lesson_wait", pet=comp["name"], time=self._duration(lang, left))
            return
        needs = self.pet_needs(comp)
        if self.pet_mood(comp) < float(rules["lesson_mood"]) or needs["rest"] < float(rules["tired"]):
            self._error(session, "pet_lesson_mood", pet=comp["name"])
            return
        if not self._slow(session):
            return
        needs["rest"] -= float(rules["lesson_rest"])
        needs["fun"] += 5
        self._set_needs(comp, needs)
        self._pet_set_cooldown(comp, "lesson", rules["lesson_cooldown"])
        lessons = stats.setdefault("lessons", {})
        success = self.rng.random() < max(0.5, self.pet_mood(comp) / 100.0)
        if success:
            lessons[tid] = int(lessons.get(tid, 0)) + 1
        done = int(lessons.get(tid, 0)) >= int(rules["lessons"])
        if done:
            stats.setdefault("tricks", []).append(tid)
            lessons.pop(tid, None)
        self.store.save_companion(comp)
        name = trick["names"][lang][0]
        if done:
            self._send(session, "paid", "pet_learned", pet=comp["name"], trick=name,
                       extra={"sound": "pet_trick"})
        elif success:
            self._send(session, "info", "pet_lesson", pet=comp["name"], trick=name, n=lessons[tid],
                       total=int(rules["lessons"]), extra={"sound": self.pet_sound(comp)})
        else:
            self._send(session, "info", "pet_lesson_missed", pet=comp["name"], trick=name)

    def _pet_trick(self, session, text, message):
        comp, rest = self._pet_for(session, text)
        if comp is None:
            return
        lang = session.lang
        known = comp["stats"].get("tricks", [])
        if not rest.strip() and not self._trick_named(comp, text):
            tricks = self.pet_kind(comp).get("tricks") or {}
            if known:
                self._info(session, "pet_tricks_known", tricks=[tricks[t]["names"][lang][0] for t in known if t in tricks])
            else:
                self._info(session, "pet_no_tricks", pet=comp["name"], tricks=self._tricks_list(lang, comp))
            return
        tid = self._trick_named(comp, rest) or self._trick_named(comp, text)
        if tid is None or tid not in known:
            self._error(session, "pet_trick_unknown", pet=comp["name"])
            return
        if self.pet_sad(comp):
            self._error(session, "pet_trick_sad", pet=comp["name"])
            return
        if not session.chat.take():
            self._error(session, "slow_down")
            return
        trick = self.pet_kind(comp)["tricks"][tid]
        for other in self._in_room(self.room_of(session.char)):
            line = pick(trick["do"], other.lang).format(pet=comp["name"], owner=session.name)
            self._send(other, "emote", text=line, extra={"actor": session.name, "sound": "pet_trick"})

    # --- following and reacting ----------------------------------------------------------------

    def pet_reacts(self, session, chance=0.3, comp=None):
        """A pet of `session`'s player reacts, for everyone in the room to see (a sad pet stays quiet)."""
        if session is None or session.invisible:
            return
        pets = [comp] if comp is not None else self.pets_of(session.char)
        if not pets or self.rng.random() >= chance:
            return
        comp = pets[0]
        if self.pet_sad(comp):
            return
        reactions = self.pet_kind(comp).get("reactions")
        if not reactions:
            return
        index = self.rng.randrange(len(reactions["en"]))
        for other in self._in_room(self.room_of(session.char)):
            line = reactions[other.lang][index].format(pet=comp["name"], owner=session.name)
            self._send(other, "emote", text=line, extra={"sound": self.pet_sound(comp)})

    def pet_follows(self, session):
        """A pet walks in with its owner, now and then."""
        self.pet_reacts(session, chance=0.15)

    def companions_join_in(self, session, eid):
        """Your pet joins in a gesture of yours, now and then (never a sad one)."""
        if session.invisible or eid not in JOIN_IN:
            return
        pets = self.pets_of(session.char)
        if not pets or self.rng.random() >= 0.35 or self.pet_sad(pets[0]):
            return
        comp = pets[0]
        self._to_room(self.room_of(session.char), "emote", JOIN_IN[eid], extra={"sound": self.pet_sound(comp)},
                      pet=comp["name"], owner=session.name)

    def emote_at_companion(self, session, name, eid, emote):
        """A gesture at a pet in the room (yours or another player's). False: no pet by that name."""
        room = self.room_of(session.char)
        for owner in [session] + self._in_room(room, exclude=(session,), visible=True):
            comp = self._pet_named(self.pets_of(owner.char), name) if orbit_safety.name_key(name) not in (
                "pet", "the pet") or owner is session else None
            if comp is None:
                continue
            if not session.chat.take():
                self._error(session, "slow_down")
                return True
            self.note_room_chat(session)
            self._send(session, "emote", text=emote[session.lang]["you_at"].format(target=comp["name"]),
                       extra={"emote": eid})
            for other in self._in_room(room, exclude=(session,)):
                self._send(other, "emote", text=emote[other.lang]["they_at"].format(actor=session.name,
                                                                                    target=comp["name"]),
                           extra={"actor": session.name, "emote": eid})
            if owner is session and eid in ("hug", "smile", "wave", "cheer", "clap"):
                needs = self.pet_needs(comp)
                needs["fun"] += float(self.pet_rules()["pat_fun"])
                self._set_needs(comp, needs)
                self.store.save_companion(comp)
            self.pet_reacts(owner, chance=1.0, comp=comp)
            return True
        family = getattr(self, "family_emote_at", None)
        return bool(family and family(session, name, eid, emote))

    def give_to_companion(self, session, name, message):
        """ "give food Kiki": read as giving "food" something (Kiki): feeding Kiki."""
        if orbit_safety.name_key(name) not in ("food", "pet food"):
            return False
        item = self._arg(message, "item", 60)
        if orbit_safety.name_key(item) in ("credits", "credit"):
            item = ""
        self.run(session, {"c": "pet", "op": "feed", "a": item})
        return True

    # --- the look of it ------------------------------------------------------------------------

    def pet_lines(self, lang, char):
        """What others see of your pets when they look at you."""
        lines = []
        for comp in self.pets_of(char):
            lines.append(self.render(lang, "look_pet", pet=comp["name"], species=self.pet_kind(comp).get("kind", comp["kind"])))
            if self.pet_sad(comp):
                lines.append(self.render(lang, "look_pet_sad", pet=comp["name"]))
        return lines

    # --- time passing -----------------------------------------------------------------------------

    def tick_pets(self, session, now):
        """Once a minute: a pet whose need is very low nudges its owner, at most once an hour."""
        if session.conn is None or session.away or now < getattr(session, "pet_check", 0):
            return
        session.pet_check = now + 60
        rules = self.pet_rules()
        for comp in self.pets_of(session.char):
            needs = self.pet_needs(comp)
            low = min(NEEDS, key=lambda n: needs[n])
            if needs[low] >= float(rules["nudge_below"]):
                continue
            if now - float(comp["stats"].get("nudged") or 0) < float(rules["nudge_seconds"]):
                continue
            comp["stats"]["nudged"] = now
            self.store.save_companion(comp)
            self._send(session, "info", f"pet_nudge_{low}", pet=comp["name"], extra={"sound": self.pet_sound(comp)})
            return

    def pet_join_notes(self, session):
        """A line on coming back: a pet that missed you."""
        notes = []
        for comp in self.pets_of(session.char):
            needs = self.pet_needs(comp)
            if min(needs.values()) < float(self.pet_rules()["nudge_below"]):
                notes.append(self.render(session.lang, "pet_missed_you", pet=comp["name"]))
        return notes[:1]

    def maybe_find_pet(self, session, action):
        """Out on the worlds, now and then, a pet chooses you. The line to add, or ""."""
        char = session.char
        for find in self.pet_rules().get("finds") or []:
            if find.get("room") != char["location"] or find.get("on") != action:
                continue
            kind = find.get("kind")
            if kind not in self.world.things or self._has_pet(char, kind):
                continue
            if self.rng.random() >= float(find.get("chance", 0)):
                continue
            pet = self.world.things[kind]["effects"]["pet"]
            self.store.add_companion(kind, pet.get("name", "Bip"), [char["id"]], stats=self.new_pet_stats(found=True))
            logger.info("%s found a %s", session.name, kind)
            char["stats"]["pets_found"] = int(char["stats"].get("pets_found") or 0) + 1
            return self.render(session.lang, "pet_found", species=pet["kind"], pet=pet.get("name", "Bip"))
        return ""
