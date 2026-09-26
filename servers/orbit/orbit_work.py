# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Jobs, levels, missions and the daily bonus.

Every job has a short mini-game, played with "work" at its workplace:

  engineer   repeat the reactor's tones (Engineering; the Reactor Core pays
             a quarter more for one more tone)
  pilot      fly a cargo run to the Moon (the Dock)
  trader     a market report, anywhere
  scientist  find the next number in a row of readings (the Science Lab)
  security   spot the smuggler among the travellers (the Cargo Bay)

Work and missions give XP. Levels (economy.json "levels") raise pay a little
each, name your rank ("senior pilot") and hand out keycards; a job's tools
raise its pay too. The daily bonus grows with a streak of days in a row.
"""

import datetime
import logging
import random
import re

import orbit_safety
import orbit_travel
from orbit_lang import LANGUAGES, pick

logger = logging.getLogger("orbit.game")

REPAIR_MIN, REPAIR_MAX = 3, 6
CARD_WORDS = {"card", "a card", "cards", "another card"}
# Where each job's work is done (a trader's market report: anywhere).
WORK_PLACES = {"engineer": ("engineering", "reactor_core"), "pilot": ("dock",), "scientist": ("science_lab",),
               "security": ("cargo",)}


class WorkMixin:
    @staticmethod
    def commands():
        return {"work": WorkMixin.cmd_work, "answer": WorkMixin.cmd_answer,
                "missions": WorkMixin.cmd_missions, "accept": WorkMixin.cmd_accept,
                "take": WorkMixin.cmd_take, "complete": WorkMixin.cmd_complete,
                "abandon": WorkMixin.cmd_abandon, "daily": WorkMixin.cmd_daily,
                "rank": WorkMixin.cmd_rank}

    # --- XP and levels ----------------------------------------------------------------------

    def xp_for_level(self, level):
        """The XP a character needs to reach `level`."""
        step = int(self.econ["levels"]["xp_step"])
        return step * level * (level - 1) // 2

    def level_of(self, xp):
        top = int(self.econ["levels"]["max"])
        level = 1
        while level < top and xp >= self.xp_for_level(level + 1):
            level += 1
        return level

    def rank_name(self, char):
        level = self.level_of(int(char.get("xp") or 0))
        rank = self.econ["ranks"][0]
        for entry in self.econ["ranks"]:
            if level >= entry["level"]:
                rank = entry
        job = self.world.job_name(char["job"])
        return {lang: rank[lang].format(job=pick(job, lang)) for lang in LANGUAGES}

    def pay_factor(self, char):
        level = self.level_of(int(char.get("xp") or 0))
        return 1.0 + float(self.econ["levels"]["pay_per_level"]) * (level - 1) + self.effects(char)["pay"]

    def pay(self, char, base):
        return int(round(base * self.pay_factor(char) * self.work_pay_factor(char)))

    def award_xp(self, session, amount):
        """Add XP (more while an iced coffee works); say so if a level was reached."""
        char, lang = session.char, session.lang
        boost = char["stats"].get("xp_boost")
        if boost and float(boost.get("until", 0)) > self.now():
            amount = int(round(amount * float(boost.get("factor", 1.0))))
        elif boost:
            char["stats"].pop("xp_boost", None)
        amount = int(round(amount * self.xp_factor() * self.family_xp_factor(char)))
        before = self.level_of(int(char.get("xp") or 0))
        char["xp"] = int(char.get("xp") or 0) + amount
        self.crew_points(char, amount)
        after = self.level_of(char["xp"])
        if after > before:
            self._send(session, "paid", "level_up", level=after, rank=self.rank_name(char),
                       pct=int(round((self.pay_factor(char) - 1) * 100)), extra={"sound": "levelup"})
            for line in self.grant_by_level(session):
                self._send(session, "paid", text=line, extra={"sound": "equip"})
        return amount

    def grant_by_level(self, session, quiet=False):
        """Things every level brings (keycards): given once. Returns the lines to say."""
        char, lang = session.char, session.lang
        level = self.level_of(int(char.get("xp") or 0))
        lines = []
        for grant in self.econ.get("grants", []):
            tid = grant["thing"]
            if level < grant["level"] or (grant.get("job") and grant["job"] != char["job"]):
                continue
            if self.owns(char, tid) or char["stats"].get(f"granted_{tid}"):
                continue
            char["stats"][f"granted_{tid}"] = True
            self.give_thing(char, tid)
            lines.append(self.render(lang, "granted", thing=self.world.things[tid]["one"], level=grant["level"]))
        return lines

    def cmd_rank(self, session, message):
        char, lang = session.char, session.lang
        xp = int(char.get("xp") or 0)
        level = self.level_of(xp)
        pct = int(round((self.pay_factor(char) - 1) * 100))
        if level >= int(self.econ["levels"]["max"]):
            self._info(session, "rank_max", rank=self.rank_name(char), level=level, xp=xp, pct=pct)
            return
        need = self.xp_for_level(level + 1) - xp
        nxt = next((r for r in self.econ["ranks"] if r["level"] > level), None)
        next_rank = ""
        if nxt:
            job = pick(self.world.job_name(char["job"]), lang)
            next_rank = self.render(lang, "rank_next", rank=nxt[lang].format(job=job), level=nxt["level"])
        self._info(session, "rank", rank=self.rank_name(char), level=level, xp=xp, need=need,
                   next=level + 1, pct=pct, next_rank=next_rank)

    # --- work -----------------------------------------------------------------------------

    def cmd_work(self, session, message):
        char = session.char
        job = char["job"]
        if self.in_transit(session):
            return
        if self.event_fix(session):              # the runaway drone, when it's here
            return
        if job == "engineer":
            self._work_repair(session)
        elif job == "pilot":
            self._work_flight(session)
        elif job == "trader":
            self._work_trade(session)
        elif job == "scientist":
            self._work_science(session)
        elif job == "security":
            self._work_patrol(session)
        else:
            self._send(session, "info", "work_none", job=self.world.job_name(job))

    @staticmethod
    def work_places(job):
        """The rooms where `job` works (WORK_PLACES), or None: anywhere."""
        return WORK_PLACES.get(job)

    def _work_place(self, session):
        places = self.work_places(session.char["job"])
        if places is not None and session.char["location"] not in places:
            self._error(session, "work_where", where=self.world.locations[places[0]]["in"])
            return False
        return True

    def _check_cooldown(self, session, name):
        left = self._cooldown_left(session.char, name)
        if left > 0:
            self._error(session, "work_cooldown", time=self._duration(session.lang, left))
            return False
        return True

    def _rest(self, char, name, seconds):
        """A break after work (a martabak halves the next one). Returns its length."""
        cut = char["stats"].pop("cooldown_cut", None)
        if cut:
            seconds = seconds * float(cut)
        self._set_cooldown(char, name, seconds)
        return seconds

    def _pending_task(self, session, kind):
        task = session.task
        if task and task.get("kind") == kind:
            return task
        return None

    def _work_repair(self, session):
        if not self._work_place(session):
            return
        stats = session.char["stats"]
        task = self._pending_task(session, "repair")
        if task:
            codes = task["codes"]
            self._send(session, "tones", "repair_again", codes=", ".join(map(str, codes)),
                       extra={"codes": codes})
            return
        if not self._check_cooldown(session, "repair"):
            return
        level = max(REPAIR_MIN, min(REPAIR_MAX, int(stats.get("repair_level", REPAIR_MIN))))
        core = session.char["location"] == "reactor_core"
        length = level + (1 if core else 0)
        codes = [self.rng.randint(1, 4) for _ in range(length)]
        session.task = {"kind": "repair", "codes": codes, "level": level, "core": core,
                        "deadline": self.now() + 20 + 4 * length}
        self._send(session, "tones", "repair_start", n=length, codes=", ".join(map(str, codes)),
                   extra={"codes": codes})

    def cmd_answer(self, session, message):
        if self.duel_answer(session):
            return
        if session.arcade:
            self.arcade_answer(session, self._arg(message, "a", 60))
            return
        task = session.task
        if not task:
            self._error(session, "answer_nothing")
            return
        kind = task.get("kind", "repair")
        if kind == "repair":
            self._answer_repair(session, task, self._arg(message, "a", 60))
        elif kind == "science":
            self._answer_science(session, task, self._arg(message, "a", 60))
        elif kind == "patrol":
            self._answer_patrol(session, task, self._arg(message, "a", 60))

    def _answer_repair(self, session, task, text):
        digits = [int(d) for d in re.findall(r"\d", text)]
        char, lang = session.char, session.lang
        stats = char["stats"]
        level = int(task.get("level", len(task["codes"])))
        session.task = None
        if digits == task["codes"]:
            work = self.econ["work"]["repair"]
            base = int(work["pay_base"]) + int(work["pay_tone"]) * level
            if task.get("core"):
                base = base * (1 + float(work["core_bonus"]))
            pay = self.pay(char, base)
            self.earn(char, pay, "work")
            stats["repair_level"] = min(REPAIR_MAX, level + 1)
            stats["repairs"] = int(stats.get("repairs", 0)) + 1
            rest = self._rest(char, "repair", self.config["engineer_cooldown"])
            self._save(session)
            self._send(session, "paid", "repair_ok", pay=pay, credits=char["credits"],
                       time=self._duration(lang, rest))
            xp = self.econ["xp"]
            self.award_xp(session, int(xp["repair"]) + int(xp["repair_tone"]) * (len(task["codes"]) - REPAIR_MIN))
            self._save(session)
        else:
            stats["repair_level"] = max(REPAIR_MIN, level - 1)
            self._set_cooldown(char, "repair", self.config["engineer_fail_cooldown"])
            self._save(session)
            self._send(session, "failed", "repair_wrong", codes=", ".join(map(str, task["codes"])),
                       time=self._duration(lang, self.config["engineer_fail_cooldown"]))

    def tick_task(self, session, now):
        task = session.task
        if not task or now <= task["deadline"]:
            return
        session.task = None
        char, lang = session.char, session.lang
        if task.get("kind", "repair") == "repair":
            char["stats"]["repair_level"] = max(
                REPAIR_MIN, int(char["stats"].get("repair_level", REPAIR_MIN)) - 1)
            self._set_cooldown(char, "repair", self.config["engineer_fail_cooldown"])
            self._save(session)
            self._send(session, "failed", "repair_late",
                       time=self._duration(lang, self.config["engineer_fail_cooldown"]))
            return
        self._set_cooldown(char, task["kind"], self.config["work_fail_cooldown"])
        self._save(session)
        self._send(session, "failed", f"{task['kind']}_late",
                   time=self._duration(lang, self.config["work_fail_cooldown"]))

    # --- the pilot ---------------------------------------------------------------------------

    def _work_flight(self, session):
        if not self._work_place(session):
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
        if not session.invisible:
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
        work = self.econ["work"]["flight"]
        pay = self.pay(char, int(work["pay_min"]) + self.rng.randint(0, int(work["pay_max"]) - int(work["pay_min"])))
        self.earn(char, pay, "work")
        char["stats"].pop("flight", None)
        char["stats"]["flights"] = int(char["stats"].get("flights", 0)) + 1
        char["location"] = "dock"
        rest = self._rest(char, "flight", self.config["pilot_cooldown"])
        char["xp"] = int(char.get("xp") or 0)
        lang = session.lang
        if on_join:
            char["xp"] += int(self.econ["xp"]["flight"])
            self._save(session)
            return self.render(lang, "flight_settled", pay=pay, credits=char["credits"])
        self._save(session)
        self._send(session, "paid", text=self.render(lang, "flight_arrive", pay=pay,
                                                     credits=char["credits"],
                                                     time=self._duration(lang, rest))
                   + "\n" + self.look_text(session, full=False),
                   extra=dict(self._where(session), sound="landing"))
        if not session.invisible:
            self._to_room(self.room_of(char), "arrive", "flight_back_other", exclude=(session,),
                          extra={"actor": session.name}, actor=session.name)
        self.award_xp(session, int(self.econ["xp"]["flight"]))
        self._save(session)
        return ""

    # --- the trader ---------------------------------------------------------------------------

    def station_market_in(self, gid):
        """Where on the station `gid` is traded ("at the Spice Market"), for a report."""
        for lid, market in self.world.markets.items():
            if self.world.world_of(lid) == "station" and gid in market["buys"] | market["sells"]:
                return self.world.locations[lid]["in"]
        return self.world.worlds["station"]["in"]

    def _work_trade(self, session):
        """The trader's work, anywhere: a market report (the station's prices, and where they
        are paid), not a counter."""
        lang = session.lang
        ratios = {gid: self.market.prices[gid] / good["base"] for gid, good in self.world.goods.items()
                  if good.get("kind", "trade") == "trade"}
        cheap = min(ratios, key=ratios.get)
        dear = max(ratios, key=ratios.get)
        parts = [self.render(lang, "trader_intro")]
        if ratios[cheap] < 0.97:
            parts.append(self.render(lang, "trader_cheap", good=self.world.goods[cheap]["many"],
                                     pct=int(round((1 - ratios[cheap]) * 100)), where=self.station_market_in(cheap)))
        if ratios[dear] > 1.03:
            parts.append(self.render(lang, "trader_dear", good=self.world.goods[dear]["many"],
                                     pct=int(round((ratios[dear] - 1) * 100)), where=self.station_market_in(dear)))
        if len(parts) == 1:
            parts.append(self.render(lang, "trader_calm"))
        self._send(session, "info", text="\n".join(parts))

    # --- the scientist ---------------------------------------------------------------------------

    def difficulty(self, char):
        return 1 + (self.level_of(int(char.get("xp") or 0)) - 1) // 4

    @staticmethod
    def make_pattern(rng, difficulty):
        """(the readings shown, the next one) for a scientist's analysis."""
        kinds = ["add", "square"]
        if difficulty >= 2:
            kinds += ["double", "alternate"]
        if difficulty >= 3:
            kinds += ["fib", "growing"]
        kind = rng.choice(kinds)
        if kind == "add":
            a, d = rng.randint(1, 20), rng.randint(2, 6 + difficulty * 2)
            seq = [a + i * d for i in range(6)]
        elif kind == "square":
            n = rng.randint(1, 6)
            seq = [(n + i) ** 2 for i in range(5)]
        elif kind == "double":
            a, r = rng.randint(1, 5), rng.choice((2, 3))
            seq = [a * r ** i for i in range(5)]
        elif kind == "alternate":
            a, d1, d2 = rng.randint(1, 9), rng.randint(2, 9), rng.randint(2, 9)
            seq = [a]
            for i in range(5):
                seq.append(seq[-1] + (d1 if i % 2 == 0 else d2))
        elif kind == "fib":
            a, b = rng.randint(1, 5), rng.randint(1, 5)
            seq = [a, b]
            while len(seq) < 6:
                seq.append(seq[-1] + seq[-2])
        else:
            a, k = rng.randint(1, 10), rng.randint(1, 3)
            seq = [a]
            for i in range(5):
                seq.append(seq[-1] + k + i)
        return seq[:-1], seq[-1]

    def _work_science(self, session):
        if not self._work_place(session):
            return
        task = self._pending_task(session, "science")
        if task:
            self._send(session, "task", "science_again", readings=", ".join(map(str, task["shown"])),
                       extra={"sound": "task"})
            return
        if not self._check_cooldown(session, "science"):
            return
        shown, answer = self.make_pattern(self.rng, self.difficulty(session.char))
        seconds = int(self.econ["work"]["science"]["seconds"])
        session.task = {"kind": "science", "shown": shown, "answer": answer,
                        "deadline": self.now() + seconds}
        self._send(session, "task", "science_start", readings=", ".join(map(str, shown)),
                   time=self._duration(session.lang, seconds), extra={"sound": "task"})

    def _answer_science(self, session, task, text):
        char, lang = session.char, session.lang
        numbers = [int(n) for n in re.findall(r"-?\d+", text)]
        session.task = None
        if numbers and numbers[0] == task["answer"]:
            pay = self.pay(char, int(self.econ["work"]["science"]["pay"]) + 5 * self.difficulty(char))
            self.earn(char, pay, "work")
            char["stats"]["analyses"] = int(char["stats"].get("analyses", 0)) + 1
            rest = self._rest(char, "science", self.config["work_cooldown"])
            self._save(session)
            self._send(session, "paid", "science_ok", pay=pay, credits=char["credits"],
                       time=self._duration(lang, rest))
            self.award_xp(session, int(self.econ["xp"]["science"]))
            self._save(session)
        else:
            self._set_cooldown(char, "science", self.config["work_fail_cooldown"])
            self._save(session)
            self._send(session, "failed", "science_wrong", answer=task["answer"],
                       time=self._duration(lang, self.config["work_fail_cooldown"]))

    # --- security ---------------------------------------------------------------------------

    def _work_patrol(self, session):
        if not self._work_place(session):
            return
        lang = session.lang
        task = self._pending_task(session, "patrol")
        if task:
            self._send(session, "task", text=self._lineup_text(lang, task), extra={"sound": "task"})
            return
        if not self._check_cooldown(session, "patrol"):
            return
        level = self.level_of(int(session.char.get("xp") or 0))
        count = 3 if level < 5 else 4 if level < 12 else 5
        people = self.econ["patrol_people"]
        crowd = self.rng.sample(range(len(people["innocent"])), count - 1)
        suspect = self.rng.randrange(len(people["suspect"]))
        where = self.rng.randrange(count)
        lineup = [("innocent", i) for i in crowd]
        lineup.insert(where, ("suspect", suspect))
        seconds = int(self.econ["work"]["patrol"]["seconds"])
        session.task = {"kind": "patrol", "lineup": lineup, "answer": where + 1,
                        "deadline": self.now() + seconds}
        self._send(session, "task", text=self._lineup_text(lang, session.task), extra={"sound": "task"})

    def _lineup_text(self, lang, task):
        people = self.econ["patrol_people"]
        entries = [f"{n}: {people[kind][i][lang]}" for n, (kind, i) in enumerate(task["lineup"], 1)]
        return self.render(lang, "patrol_start", people="; ".join(entries), count=len(entries))

    def _answer_patrol(self, session, task, text):
        char, lang = session.char, session.lang
        numbers = [int(n) for n in re.findall(r"\d+", text)]
        session.task = None
        work = self.econ["work"]["patrol"]
        if numbers and numbers[0] == task["answer"]:
            pay = self.pay(char, int(work["pay"]) + int(work["pay_person"]) * len(task["lineup"]))
            self.earn(char, pay, "work")
            char["stats"]["patrols"] = int(char["stats"].get("patrols", 0)) + 1
            rest = self._rest(char, "patrol", self.config["work_cooldown"])
            self._save(session)
            self._send(session, "paid", "patrol_ok", pay=pay, credits=char["credits"],
                       time=self._duration(lang, rest))
            self.award_xp(session, int(self.econ["xp"]["patrol"]))
            self._save(session)
        else:
            self._set_cooldown(char, "patrol", self.config["work_fail_cooldown"])
            self._save(session)
            self._send(session, "failed", "patrol_wrong", answer=task["answer"],
                       time=self._duration(lang, self.config["work_fail_cooldown"]))

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
                for lang in LANGUAGES}

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
            mission = self.world.missions[mid]
            gift = ""
            if mission.get("gives"):
                gift = self.render(lang, "mission_gift", thing=self.world.things[mission["gives"]]["one"])
            entries.append(self.render(lang, "mission_entry", number=number,
                                       title=self._mission_title(mid),
                                       reward=mission["reward"], mark=gift + mark))
        self._send(session, "info", "missions_board", entries="\n".join(entries))

    def cmd_accept(self, session, message):
        if message.get("n") in (None, "") and self.accept_pending(session):
            return
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
        if session.blackjack and orbit_safety.name_key(text) in CARD_WORDS:
            self.run(session, {"c": "hit"})          # "take a card" at the card table
            return
        words = text.split()
        if words and words[-1].lower() in ("along", "with"):
            words = words[:-1]
        child = self._child_named(char, " ".join(words)) if words else None
        if child is not None:
            self.run(session, {"c": "child", "op": "take", "a": " ".join(words)})   # "take Lily along"
            return
        if orbit_safety.name_key(text) in ("gig", "a gig", "parcel", "a parcel"):
            self.run(session, {"c": "gig"})          # "take a gig" (read by a client as take)
            return
        ferry = orbit_travel._after(text, orbit_travel.FERRY_WORDS)
        if ferry is not None:
            self.run(session, {"c": "ferry", "a": ferry})    # "take the ferry to the Moon" (Orbit 1.0: take)
            return
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
        char, lang = session.char, session.lang
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
        self.earn(char, mission["reward"], "missions")
        text = self.render(lang, "mission_complete", title=self._mission_title(active),
                           pay=mission["reward"], credits=char["credits"])
        if mission.get("gives") in self.world.things:
            tid = mission["gives"]
            thing = self.world.things[tid]
            if not (thing.get("unique") and self.owns(char, tid)):
                self.give_thing(char, tid)
                text += " " + self.render(lang, "mission_gift_got", thing=thing["one"])
        self._save(session)
        self._send(session, "paid", text=text)
        self.award_xp(session, int(self.econ["xp"]["mission"]))
        self._save(session)

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

    # --- the daily bonus ---------------------------------------------------------------------

    def daily_ready(self, char):
        return char.get("last_daily") != self.today()

    def cmd_daily(self, session, message):
        char, lang = session.char, session.lang
        today = self.today()
        if char.get("last_daily") == today:
            now = datetime.datetime.fromtimestamp(self.now(), datetime.timezone.utc)
            midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            self._error(session, "daily_done", time=self._duration(lang, (midnight - now).total_seconds()),
                        streak=char.get("streak", 0))
            return
        yesterday = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
        streak = int(char.get("streak") or 0) + 1 if char.get("last_daily") == yesterday else 1
        daily = self.econ["daily"]
        bonus = int(daily["base"]) + int(daily["step"]) * (min(streak, int(daily["cap"])) - 1)
        char["streak"] = streak
        char["last_daily"] = today
        self.earn(char, bonus, "daily")
        text = self.render(lang, "daily_paid", pay=bonus, credits=char["credits"], streak=streak)
        week = daily.get("week_bonus")
        if week and streak % 7 == 0 and week.get("thing") in self.world.things:
            self.give_thing(char, week["thing"], int(week.get("n", 1)))
            text += " " + self.render(lang, "daily_week", things=self._count_of(week["thing"], int(week.get("n", 1))))
        self._save(session)
        self._send(session, "paid", text=text, extra={"sound": "daily"})
