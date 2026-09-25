# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Achievements and the leaderboards.

An achievement (economy.json "achievements") is earned when a number about
you reaches a mark: rooms walked, shifts worked, level, crops, ore, the
daily streak, furniture, credits held, and a few lucky moments. It's kept
in the database, pays its credits (and sometimes a title) once, and the
big ones are news for the whole station ("... and the first on the
station!"). Earned the moment it happens: after each command, and when a
flight lands or the lottery is drawn. What you had already done before
1.1 counts too, quietly, the next time you come in.

The leaderboards rank everyone (admins aside) by credits, level, ore mined,
crops harvested, the daily streak and what they won or lost at the casino.
"""

import logging

import orbit_safety

logger = logging.getLogger("orbit.game")

BOARDS = {
    "rich": ("credits", ("rich", "richest", "credits", "money", "wealth", "kaya", "terkaya", "kredit",
                         "uang", "harta")),
    "level": ("xp", ("level", "levels", "xp", "experience", "pengalaman", "tertinggi")),
    "miner": ("mined", ("miner", "miners", "mining", "mined", "ore", "tambang", "penambang", "bijih")),
    "farmer": ("harvested", ("farmer", "farmers", "farming", "farm", "harvest", "crops", "petani", "panen",
                             "kebun", "tani")),
    "streak": ("streak", ("streak", "daily", "harian", "rajin", "beruntun")),
    "casino": ("casino_net", ("casino", "luck", "lucky", "gambler", "kasino", "hoki", "beruntung", "judi")),
}
BOARD_SIZE = 5
SHIFT_STATS = ("repairs", "flights", "analyses", "patrols")


class ProgressMixin:
    @staticmethod
    def commands():
        return {"achievements": ProgressMixin.cmd_achievements,
                "leaderboard": ProgressMixin.cmd_leaderboard}

    # --- achievements ------------------------------------------------------------------------

    def public_rooms(self):
        return {lid for lid, loc in self.world.locations.items()
                if not (loc.get("private") or loc.get("secret") or loc.get("hidden"))}

    def achievement_value(self, char, stat):
        """Where a character is on an achievement's number."""
        stats = char["stats"]
        if stat == "rooms":
            return len(set(stats.get("map") or []) & self.public_rooms())
        if stat == "shifts":
            return sum(int(stats.get(name) or 0) for name in SHIFT_STATS)
        if stat == "missions":
            return int(stats.get("missions_done") or 0)
        if stat == "level":
            return self.level_of(int(char.get("xp") or 0))
        if stat in ("harvested", "mined", "streak", "credits"):
            return int(char.get(stat) or 0)
        if stat == "furniture":
            return sum(n for tid, n in char["inventory"].items()
                       if self.world.things.get(tid, {}).get("type") == "furniture" and n > 0)
        if stat == "capsule":
            return 1 if stats.get("capsule") else 0
        if stat == "worlds":
            return len({self.world.world_of(lid) for lid in stats.get("map") or []} & set(self.world.worlds))
        if stat == "ship":
            return 1 if stats.get("ship") else 0
        return int(stats.get(stat) or 0)

    def achievement_goal(self, achievement):
        at = achievement["at"]
        if at == "all":
            return len(self.world.worlds) if achievement["stat"] == "worlds" else len(self.public_rooms())
        return int(at)

    @staticmethod
    def _title(achievement):
        return {"en": achievement["en"], "id": achievement["id"]}

    def _earned(self, session):
        if session.earned is None:
            session.earned = set(self.store.achievements_of(session.char["id"]))
        return session.earned

    def check_achievements(self, session, stat=None, quiet=False):
        """Awards whatever `session` has just reached (only achievements about `stat`,
        when given). Quiet: nothing is said, and the texts are returned instead."""
        if session is None or session.char.get("id") is None:
            return []
        earned = self._earned(session)
        notes = []
        for aid, achievement in self.econ.get("achievements", {}).items():
            if aid in earned or (stat and achievement["stat"] != stat):
                continue
            if self.achievement_value(session.char, achievement["stat"]) < self.achievement_goal(achievement):
                continue
            earned.add(aid)
            text = self._award(session.char, aid, session=session, announce=not quiet)
            if text is None:
                continue
            if quiet:
                notes.append(text)
            else:
                self._send(session, "paid", text=text, extra={"sound": "achievement"})
        return notes

    def award_offline(self, char, aid):
        """An achievement for someone who isn't in play (the lottery's winner)."""
        self._award(char, aid)

    def _award(self, char, aid, session=None, announce=True):
        """Keeps it, pays it, tells the station. The player's own text (None if they had it)."""
        achievement = self.econ["achievements"][aid]
        with self.store.transaction():
            if not self.store.add_achievement(char["id"], aid):
                return None
            credits = int(achievement.get("credits") or 0)
            if credits:
                self.earn(char, credits, "achievements")
            thing = achievement.get("thing")
            if thing and not self.owns(char, thing):
                self.give_thing(char, thing)
            self.store.save(char)
        first = self.store.achievement_count(aid) == 1
        logger.info("%s earned the achievement %s", char["name"], aid)
        title = self._title(achievement)
        if achievement.get("station") and announce:
            self._to_all("announce", "achievement_first" if first else "achievement_station",
                         exclude=(session,) if session else (), extra={"sound": "achievement"},
                         name=char["name"], title=title)
        lang = session.lang if session else "en"
        rewards = []
        if credits:
            rewards.append(self.render(lang, "achievement_credits", n=credits))
        if thing:
            rewards.append(self.world.things[thing]["one"])
        text = self.render(lang, "achievement_you", title=title, desc=achievement.get("desc", ""))
        if rewards:
            text += " " + self.render(lang, "achievement_reward", things=rewards)
        if first and achievement.get("station"):
            text += " " + self.render(lang, "achievement_you_first")
        return text

    def cmd_achievements(self, session, message):
        lang, char = session.lang, session.char
        name = self._arg(message, "to", 40)
        if name and orbit_safety.name_key(name) not in (session.key, "me", "aku", "saya"):
            other = self._char_by_key(orbit_safety.name_key(name))
            online = self.sessions.get(orbit_safety.name_key(name))
            if other is None or (online is not None and online.invisible and not self.is_admin(session)):
                self._error(session, "no_character", name=name)
                return
            got = self.store.achievements_of(other["id"])
            titles = [self._title(self.econ["achievements"][a]) for a in got if a in self.econ["achievements"]]
            self._info(session, "achievements_other" if titles else "achievements_other_none",
                       name=other["name"], n=len(titles), total=len(self.econ["achievements"]), titles=titles)
            return
        earned = self._earned(session)
        table = self.econ.get("achievements", {})
        titles = [self._title(table[a]) for a in self.store.achievements_of(char["id"]) if a in table]
        parts = [self.render(lang, "achievements" if titles else "achievements_none", n=len(titles),
                             total=len(table), titles=titles)]
        nearest = []
        for aid, achievement in table.items():
            if aid in earned:
                continue
            goal = self.achievement_goal(achievement)
            have = min(goal, self.achievement_value(char, achievement["stat"]))
            nearest.append((-(have / goal if goal else 0), aid, have, goal))
        nearest.sort()
        entries = [self.render(lang, "achievement_next", title=self._title(table[aid]),
                               desc=table[aid].get("desc", ""), have=have, goal=goal)
                   for _ratio, aid, have, goal in nearest[:3]]
        if entries:
            parts.append(self.render(lang, "achievements_next", entries="; ".join(entries)))
        self._info(session, text=" ".join(parts))

    # --- leaderboards ------------------------------------------------------------------------

    def board_for(self, text):
        word = orbit_safety.name_key(text)
        for board, (_column, words) in BOARDS.items():
            if word == board or word in words:
                return board
        return None

    def board_entries(self, board, limit=BOARD_SIZE):
        column = BOARDS[board][0]
        rows = self.store.top(column, limit, exclude=self.admins)
        if board == "level":
            return [(name, self.level_of(value)) for name, value in rows]
        return rows

    def cmd_leaderboard(self, session, message):
        lang, char = session.lang, session.char
        text = self._arg(message, "a", 40)
        board = self.board_for(text) if text else None
        if text and board is None and (self.find_arcade_game(text) or
                                       orbit_safety.name_key(text) in ("arcade", "arkade")):
            self.cmd_high_scores(session, {"a": "" if orbit_safety.name_key(text) in ("arcade", "arkade")
                                           else text})       # "high scores meteor": the arcade's table
            return
        if text and board is None:
            self._error(session, "board_unknown", boards=[self.render(lang, f"board_{b}") for b in BOARDS])
            return
        if board is None:
            leaders = []
            for b in BOARDS:
                rows = self.board_entries(b, 1)
                if rows and rows[0][1] > 0:
                    leaders.append(self.render(lang, "board_leader", board=self.render(lang, f"board_{b}"),
                                               name=rows[0][0], value=rows[0][1]))
            self._info(session, "boards", leaders="; ".join(leaders) or self.render(lang, "board_empty"),
                       boards=[self.render(lang, f"board_{b}") for b in BOARDS])
            return
        rows = self.board_entries(board)
        entries = [self.render(lang, "board_entry", n=i + 1, name=name, value=value)
                   for i, (name, value) in enumerate(rows)]
        text = self.render(lang, "board", board=self.render(lang, f"board_{board}"),
                           entries="; ".join(entries) or self.render(lang, "board_empty"))
        if session.key not in self.admins:
            self._save(session)
            rank = self.store.rank_of(BOARDS[board][0], char["id"], exclude=self.admins)
            if rank:
                text += " " + self.render(lang, "board_you", n=rank)
        self._info(session, text=text)
