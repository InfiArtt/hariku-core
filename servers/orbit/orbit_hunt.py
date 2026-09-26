# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The Lost Chord: a season-long hunt for the prize the simulation's founder
hid, one riddle after another, for the whole server.

A season is a file on the server (config.json "hunt", e.g.
private/season1.hunt.json), never in this repository: the riddles, where
their clues are and what unlocks them are the whole game, and the repository
is public. Its answers are not in it either, only keyed hashes: HMAC-SHA256
with the season's own secret salt of "<season>:<stage>:<answer>", the answer
normalized (lower case, no accents, only letters and digits, so "3 1 4" and
"314" are the same). orbit_hunt_tool.py turns an authoring file (the same,
with the answers in plain text) into that file. hunt.example.json here is a
tiny, obviously fake season for trying it out and for the tests.

The game is played in English, so its English texts are the ones said (a
season file may have other languages beside them: they're left alone), and
an answer counts when its hash is one of the stage's, in whatever language
the season's author accepted it.

    hunt                          your stage and its riddle (and any hints the
                                  admins released)
    investigate                   look for a clue where you are: some show only
                                  with a thing (a scanner, a headlamp worn) or
                                  at certain station hours (UTC), and some are
                                  tones to listen to
    solve ...                     answer your stage's riddle
    hunt board                    who has come how far, and the rival

A wrong answer makes you wait before the next try, twice as long each time
(config "hunt_wrong_base" to "hunt_wrong_max"), so guessing doesn't pay; every
try is also rate-limited. The first to finish wins the big prize and a title
of their own, the next ones smaller prizes, and the whole station hears it.
A rival, the Meridian Grey company, "finds" a note of its own every so often
(the season file's "rival") and says so, but it never finishes. Admins know
the answers, so they don't count on the board or for prizes unless
config "hunt_admins_compete" says so; "hunt test" lets an admin play the
season without counting at all. Everyone's progress is in the database
(hunt_progress), per season; the season's own state (the rival, the hints
released, how many finished) in meta "hunt".
"""

import datetime
import hashlib
import hmac
import json
import logging
import secrets
import unicodedata

from orbit_lang import LANGUAGES, pick

logger = logging.getLogger("orbit.game")

HUNT_DEFAULTS = {
    "hunt_path": "",
    "hunt_admins_compete": False,
    "hunt_wrong_base": 60,            # seconds to wait after the first wrong answer...
    "hunt_wrong_max": 86400,          # ...doubling each time, up to a day
}
LANGS = LANGUAGES
MAX_TONES = 32
# "look for clues" (and the like): both clients send it as look, so look passes it on.
LOOK_FOR_CLUES = {"forclues", "foraclue", "forclue", "fortheclue", "forhints", "forahint"}


class HuntError(ValueError):
    pass


def normalize(text):
    """What an answer is compared as: lower case, no accents, only letters and digits."""
    text = unicodedata.normalize("NFKD", str(text or "")).casefold()
    return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def answer_hash(salt, season, stage, text):
    return hmac.new(bytes.fromhex(salt), f"{season}:{stage}:{normalize(text)}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _texts(value):
    """A text of the season: {"en": ...} (other languages beside it are allowed, and unused)."""
    return isinstance(value, dict) and all(isinstance(value.get(lang), str) and value[lang] for lang in LANGS)


def validate(hunt, world, plain=False):
    """Problems with a season (a list; empty when it's fine). `plain`: an authoring
    file, whose stages have "accept" (the answers in plain text) instead of hashes."""
    problems = []
    if not isinstance(hunt, dict):
        return ["a season is a JSON object"]
    if not str(hunt.get("season") or "").strip():
        problems.append("the season needs a name or number")
    if not _texts(hunt.get("title")) or not _texts(hunt.get("intro")):
        problems.append("the season needs a title and an intro in en")
    salt = hunt.get("salt")
    if not plain or salt is not None:
        try:
            if len(bytes.fromhex(str(salt))) < 16:
                raise ValueError
        except ValueError:
            problems.append("the salt must be at least 32 hexadecimal characters")
    stages = hunt.get("stages")
    if not isinstance(stages, list) or not 1 <= len(stages) <= 9:
        return problems + ["a season has 1 to 9 stages"]
    ids = set()
    for n, stage in enumerate(stages, 1):
        sid = str(stage.get("id") or "")
        where = f"stage {n} ({sid})"
        if not sid or sid in ids:
            problems.append(f"{where}: needs an id of its own")
        ids.add(sid)
        if not _texts(stage.get("riddle")) or not _texts(stage.get("found")):
            problems.append(f"{where}: needs a riddle and a found text in en")
        if plain:
            if not stage.get("accept") or not all(normalize(a) for a in stage["accept"]):
                problems.append(f"{where}: needs the answers it accepts")
        else:
            if "accept" in stage:
                problems.append(f"{where}: plain answers must never be on the server; build it with the tool")
            hashes = stage.get("answers")
            if not hashes or not all(isinstance(h, str) and len(h) == 64 for h in hashes):
                problems.append(f"{where}: needs its answers' hashes")
        for c, clue in enumerate(stage.get("clues") or [], 1):
            at = f"{where}, clue {c}"
            if clue.get("room") not in world.locations:
                problems.append(f"{at}: unknown room {clue.get('room')!r}")
            if not _texts(clue.get("text")):
                problems.append(f"{at}: needs a text in en")
            needs = clue.get("requires") or {}
            for key in ("thing", "worn"):
                if needs.get(key) and needs[key] not in world.things:
                    problems.append(f"{at}: unknown thing {needs[key]!r}")
            hours = needs.get("hours")
            if hours is not None and not (isinstance(hours, list) and len(hours) == 2
                                          and all(isinstance(h, int) and 0 <= h <= 23 for h in hours)):
                problems.append(f"{at}: hours are [from, to], UTC, 0 to 23")
            tones = clue.get("tones")
            if tones is not None and not (isinstance(tones, list) and 1 <= len(tones) <= MAX_TONES
                                          and all(t in (1, 2, 3, 4) for t in tones)):
                problems.append(f"{at}: tones are 1 to {MAX_TONES} of the four notes 1-4")
        if not stage.get("clues"):
            problems.append(f"{where}: needs at least one clue")
        for h, hint in enumerate(stage.get("hints") or [], 1):
            if not _texts(hint):
                problems.append(f"{where}, hint {h}: needs en")
    prize = hunt.get("prize") or {}
    if not isinstance(prize.get("first"), int) or prize["first"] < 0:
        problems.append("the prize needs a first prize in credits")
    for key in ("title",):
        if prize.get(key) and prize[key] not in world.things:
            problems.append(f"the prize's {key} {prize[key]!r} is not a thing")
    rival = hunt.get("rival")
    if rival is not None and (not _texts(rival.get("name")) or not float(rival.get("hours") or 0) > 0):
        problems.append("the rival needs a name in en, and hours between its finds")
    return problems


def build(authoring, world, salt=None):
    """A server file from an authoring file: the answers hashed with a secret salt."""
    problems = validate(authoring, world, plain=True)
    if problems:
        raise HuntError("; ".join(problems))
    hunt = json.loads(json.dumps(authoring))
    hunt["salt"] = salt or hunt.get("salt") or secrets.token_hex(32)
    for stage in hunt["stages"]:
        accepted = stage.pop("accept")
        stage["answers"] = sorted({answer_hash(hunt["salt"], hunt["season"], stage["id"], a) for a in accepted})
    problems = validate(hunt, world)
    if problems:
        raise HuntError("; ".join(problems))
    return hunt


def load(path, world):
    with open(path, encoding="utf-8") as f:
        hunt = json.load(f)
    problems = validate(hunt, world)
    if problems:
        raise HuntError(f"{path}: " + "; ".join(problems))
    return hunt


class HuntMixin:
    @staticmethod
    def commands():
        return {"hunt": HuntMixin.cmd_hunt, "investigate": HuntMixin.cmd_investigate,
                "solve": HuntMixin.cmd_solve, "hunt_board": HuntMixin.cmd_hunt_board}

    def init_hunt(self):
        for key, value in HUNT_DEFAULTS.items():
            self.config.setdefault(key, value)
        self.hunt = None
        self.load_hunt()

    def load_hunt(self):
        """Reads the season file (config "hunt_path"). Returns the season, or None
        (a broken file leaves the season already running as it was)."""
        path = self.config.get("hunt_path")
        if not path:
            return None
        try:
            hunt = load(path, self.world)
        except (OSError, ValueError) as e:
            logger.error("the hunt could not be loaded: %s", e)
            return None
        self.hunt = hunt
        state = self.hunt_state()
        if str(state.get("season")) != str(hunt["season"]):
            rival = hunt.get("rival")
            state = {"season": hunt["season"], "started": self.now(), "rival": 0, "hints": {}, "finishers": 0,
                     "rival_next": self.now() + float(rival["hours"]) * 3600 if rival else 0}
            self.store.set_json("hunt", state)
            logger.info("the hunt's season %s begins", hunt["season"])
        return hunt

    def hunt_state(self):
        return self.store.get_json("hunt", {}) or {}

    def _save_hunt_state(self, state):
        self.store.set_json("hunt", state)

    # --- who counts ----------------------------------------------------------------------

    def hunt_counts(self, session):
        """Whether a player counts on the board and for prizes."""
        if getattr(session, "hunt_test", False):
            return False
        return not self.is_admin(session) or bool(self.config.get("hunt_admins_compete"))

    def hunt_key(self, session):
        season = str(self.hunt["season"])
        return f"test:{season}" if getattr(session, "hunt_test", False) else season

    def _progress(self, session):
        return self.store.hunt_progress(self.hunt_key(session), session.char["id"])

    # --- playing -----------------------------------------------------------------------------

    def _no_hunt(self, session):
        if self.hunt is None:
            self._error(session, "hunt_none")
            return True
        return False

    def _stage_text(self, lang, n):
        stage = self.hunt["stages"][n]
        parts = [self.render(lang, "hunt_stage", n=n + 1, total=len(self.hunt["stages"])), pick(stage["riddle"], lang)]
        released = int(self.hunt_state().get("hints", {}).get(stage["id"], 0))
        for hint in (stage.get("hints") or [])[:released]:
            parts.append(self.render(lang, "hunt_hint", hint=hint))
        return " ".join(parts)

    def cmd_hunt(self, session, message):
        if self._no_hunt(session):
            return
        lang = session.lang
        progress = self._progress(session)
        parts = [pick(self.hunt["title"], lang) + "."]
        if progress["finished"]:
            parts.append(self.render(lang, "hunt_done", place=progress["place"] or "-"))
        else:
            if progress["stage"] == 0:
                parts.append(pick(self.hunt["intro"], lang))
            parts.append(self._stage_text(lang, progress["stage"]))
            left = float(progress["cooldown"]) - self.now()
            if left > 0:
                parts.append(self.render(lang, "hunt_wait_note", time=self._duration(lang, left)))
        if getattr(session, "hunt_test", False):
            parts.append(self.render(lang, "hunt_test_note"))
        self._info(session, text=" ".join(parts))

    def _clue_visible(self, char, clue):
        needs = clue.get("requires") or {}
        if needs.get("thing") and not self.owns(char, needs["thing"]):
            return False
        if needs.get("worn") and needs["worn"] not in self.worn(char).values():
            return False
        hours = needs.get("hours")
        if hours:
            hour = datetime.datetime.fromtimestamp(self.now(), datetime.timezone.utc).hour
            start, end = hours
            if not (start <= hour < end if start < end else hour >= start or hour < end):
                return False
        return True

    def hunt_clues_here(self, session, visible_only=True):
        """The clues of your current stage in the room you're in."""
        if self.hunt is None or session.char["location"] in ("ship", "ferry", "shuttle", "kancil"):
            return []
        progress = self._progress(session)
        if progress["finished"] or progress["stage"] >= len(self.hunt["stages"]):
            return []
        stage = self.hunt["stages"][progress["stage"]]
        here = [c for c in stage.get("clues") or [] if c["room"] == session.char["location"]]
        return [c for c in here if self._clue_visible(session.char, c)] if visible_only else here

    def hunt_mark(self, session):
        """A line for the room's description when a clue for you is here."""
        if self.hunt is not None and not self.in_the_dark(session.char) and self.hunt_clues_here(session):
            return self.render(session.lang, "hunt_mark")
        return ""

    def cmd_investigate(self, session, message):
        if self._no_hunt(session):
            return
        lang = session.lang
        if self.in_the_dark(session.char):
            self._error(session, "too_dark_to_see")
            return
        if not self._slow(session):
            return
        clues = self.hunt_clues_here(session)
        if not clues:
            hidden = self.hunt_clues_here(session, visible_only=False)
            self._info(session, "hunt_almost" if hidden else "hunt_nothing")
            return
        for clue in clues:
            extra = {"sound": "hunt_clue"}
            if clue.get("tones"):
                extra["codes"] = list(clue["tones"])
            self._send(session, "task", text=pick(clue["text"], lang), extra=extra)

    def cmd_solve(self, session, message):
        if self._no_hunt(session):
            return
        char, lang = session.char, session.lang
        text = self._arg(message, "a", 200)
        if not normalize(text):
            self._error(session, "hunt_solve_how")
            return
        key = self.hunt_key(session)
        progress = self.store.hunt_progress(key, char["id"])
        if progress["finished"]:
            self._info(session, "hunt_done", place=progress["place"] or "-")
            return
        left = float(progress["cooldown"]) - self.now()
        if left > 0:
            self._error(session, "hunt_wait", time=self._duration(lang, left))
            return
        if not self._slow(session):
            return
        stage = self.hunt["stages"][progress["stage"]]
        progress["attempts"] += 1
        tried = answer_hash(self.hunt["salt"], self.hunt["season"], stage["id"], text)
        if not any(hmac.compare_digest(tried, h) for h in stage["answers"]):
            progress["wrong"] += 1
            wait = min(float(self.config["hunt_wrong_max"]),
                       float(self.config["hunt_wrong_base"]) * 2 ** (progress["wrong"] - 1))
            progress["cooldown"] = self.now() + wait
            self.store.save_hunt_progress(key, char["id"], progress)
            logger.info("hunt: %s tried stage %s (wrong, %s)", session.name, stage["id"], progress["wrong"])
            self._send(session, "failed", "hunt_wrong", time=self._duration(lang, wait), extra={"sound": "fail"})
            return
        progress["stage"] += 1
        progress["wrong"] = 0
        progress["cooldown"] = 0
        n = progress["stage"]
        total = len(self.hunt["stages"])
        counts = self.hunt_counts(session)
        logger.info("hunt: %s solved stage %s", session.name, stage["id"])
        found = pick(stage["found"], lang)
        if n < total:
            self.store.save_hunt_progress(key, char["id"], progress)
            self._send(session, "paid", text=found + " " + self._stage_text(lang, n), extra={"sound": "hunt_found"})
            if counts:
                self._to_all("announce", "hunt_progress_news", exclude=(session,), extra={"sound": "hunt_clue"},
                             name=session.name, n=n, total=total)
            return
        progress["finished"] = self.now()
        prize = self.hunt.get("prize") or {}
        credits, title = 0, None
        if counts:
            state = self.hunt_state()
            state["finishers"] = int(state.get("finishers", 0)) + 1
            progress["place"] = state["finishers"]
            self._save_hunt_state(state)
            others = list(prize.get("others") or [])
            if progress["place"] == 1:
                credits, title = int(prize["first"]), prize.get("title")
            elif progress["place"] - 2 < len(others):
                credits = int(others[progress["place"] - 2])
            else:
                credits = int(prize.get("rest", 0))
        with self.store.transaction():
            self.store.save_hunt_progress(key, char["id"], progress)
            if credits:
                self.earn(char, credits, "hunt")
            if title and not self.owns(char, title):
                self.give_thing(char, title)
            char["stats"]["hunts"] = int(char["stats"].get("hunts") or 0) + (1 if counts else 0)
            self._save(session)
        reward = self.render(lang, "hunt_prize", n=credits) if credits else ""
        if title:
            reward += " " + self.render(lang, "hunt_title", thing=self.world.things[title]["one"])
        self._send(session, "paid", text=" ".join(p for p in (found, self.render(lang, "hunt_finished"), reward) if p),
                   extra={"sound": "jackpot"})
        if counts:
            key_news = "hunt_winner_news" if progress["place"] == 1 else "hunt_finisher_news"
            self._to_all("announce", key_news, exclude=(session,), extra={"sound": "achievement"},
                         name=session.name, place=progress["place"], title=self.hunt["title"])

    def cmd_hunt_board(self, session, message):
        if self._no_hunt(session):
            return
        lang = session.lang
        exclude = set() if self.config.get("hunt_admins_compete") else set(self.admins)
        rows = self.store.hunt_board(str(self.hunt["season"]), 10, exclude)
        total = len(self.hunt["stages"])
        entries = []
        for name, stage, finished, place in rows:
            if finished:
                entries.append(self.render(lang, "hunt_board_done", name=name, place=place))
            else:
                entries.append(self.render(lang, "hunt_board_entry", name=name, n=stage, total=total))
        rival = self.hunt.get("rival")
        text = self.render(lang, "hunt_board", title=self.hunt["title"],
                           entries="; ".join(entries) or self.render(lang, "board_empty"))
        if rival:
            text += " " + self.render(lang, "hunt_board_rival", name=rival["name"],
                                      n=int(self.hunt_state().get("rival", 0)), total=total)
        self._info(session, text=text)

    # --- time passing: the rival -----------------------------------------------------------------

    def tick_hunt(self, now):
        if self.hunt is None or not self.hunt.get("rival"):
            return
        state = self.hunt_state()
        total = len(self.hunt["stages"])
        if int(state.get("rival", 0)) >= total - 1 or now < float(state.get("rival_next") or 0):
            return
        state["rival"] = int(state.get("rival", 0)) + 1
        state["rival_next"] = now + float(self.hunt["rival"]["hours"]) * 3600
        self._save_hunt_state(state)
        self._to_all("announce", "hunt_rival_news", extra={"sound": "hunt_rival"}, name=self.hunt["rival"]["name"],
                     n=state["rival"], total=total)

    # --- admins ---------------------------------------------------------------------------------

    def admin_hunt_status(self, session, message):
        if self._no_hunt(session):
            return
        lang = session.lang
        now = self.now()
        rows = self.store.hunt_players(str(self.hunt["season"]))
        entries = []
        for row in rows:
            wait = float(row["cooldown"]) - now
            entries.append(self.render(lang, "hunt_status_entry", name=row["name"], n=row["stage"],
                                       attempts=row["attempts"], wrong=row["wrong"],
                                       wait=self._duration(lang, wait) if wait > 0 else "-"))
        state = self.hunt_state()
        self._info(session, "hunt_status", season=self.hunt["season"], n=len(rows),
                   finishers=state.get("finishers", 0), rival=state.get("rival", 0),
                   entries="; ".join(entries) or "-")

    def admin_new_season(self, session, message):
        before = str(self.hunt["season"]) if self.hunt else None
        hunt = self.load_hunt()
        if hunt is None:
            self._error(session, "hunt_load_failed")
            return
        self._log(session, "hunt season", str(hunt["season"]))
        if str(hunt["season"]) == before:
            self._info(session, "hunt_reloaded", season=hunt["season"])
            return
        self._info(session, "hunt_new_season", season=hunt["season"])
        self._to_all("announce", "hunt_season_news", exclude=(session,), extra={"sound": "event_start"},
                     title=hunt["title"])

    def admin_release_hint(self, session, message):
        if self._no_hunt(session):
            return
        n = self._count(message, default=None, high=len(self.hunt["stages"]))
        if n is None:
            self._error(session, "hunt_hint_how", total=len(self.hunt["stages"]))
            return
        stage = self.hunt["stages"][n - 1]
        hints = stage.get("hints") or []
        state = self.hunt_state()
        released = int(state.setdefault("hints", {}).get(stage["id"], 0))
        if released >= len(hints):
            self._error(session, "hunt_no_more_hints", n=n)
            return
        state["hints"][stage["id"]] = released + 1
        self._save_hunt_state(state)
        self._log(session, "hunt hint", f"stage {n}", str(released + 1))
        self._to_all("announce", "hunt_hint_news", extra={"sound": "hunt_clue"}, n=n, hint=hints[released])

    def admin_hunt_test(self, session, message):
        session.hunt_test = not getattr(session, "hunt_test", False)
        self._log(session, "hunt test", "on" if session.hunt_test else "off")
        self._info(session, "hunt_test_on" if session.hunt_test else "hunt_test_off")
