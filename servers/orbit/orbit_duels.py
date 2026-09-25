# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Duels: a quick-draw contest between two players, only in the contest zones
(rooms marked "arena": the Zero-G Gym, Pixel Pier's Tournament Stage).

    duel Budi / duel Budi 50 / tantang duel Budi 50
                            challenge someone in the same arena, for a small
                            stake each (none, or up to duel "max_stake")
    accept / decline        (theirs to answer, like an offer; it runs out)
    (a number)              draw! the first to type a number after the beep
                            wins the round; before it, the round is lost
    duels off / duels on    refuse every challenge (or take them again)

Best of three rounds (at most five, a round nobody answers is played
again). The winner takes both stakes, less a small fee; a draw gives them
back. Walking out, leaving or losing the connection is a forfeit. The room
hears the duel start and end. Both players need a moment before the next
duel, and a player who was declined waits longer before challenging the
same person again; muted players can't challenge, and admins can stop a
duel (stakes back). Only the duel in progress lives in memory; what's kept
is each player's wins and losses (in their stats) and the credits.
"""

import logging

from orbit_lang import pick

logger = logging.getLogger("orbit.game")


class DuelsMixin:
    @staticmethod
    def commands():
        return {"duel": DuelsMixin.cmd_duel, "duels": DuelsMixin.cmd_duels}

    def init_duels(self):
        self.duel_asks = {}         # the challenged player's key -> the challenge
        self.duels = {}             # player key -> the duel they're in (both keys, the same dict)
        self._next_duel = 1

    def duel_rules(self):
        return self.econ.get("duels", {})

    def in_arena(self, char):
        return bool(self._loc(char).get("arena"))

    def arena_names(self, lang):
        return ", ".join(pick(loc["ref"], lang) for loc in self.world.locations.values() if loc.get("arena"))

    # --- challenging ------------------------------------------------------------------------------

    def cmd_duels(self, session, message):
        """duels on / duels off (and, with nothing, whether they're on)."""
        stats = session.char["stats"]
        op = self._arg(message, "op", 10)
        if op in ("on", "off"):
            if op == "off":
                stats["no_duels"] = True
            else:
                stats.pop("no_duels", None)
            self._save(session)
            self._info(session, "duels_off" if op == "off" else "duels_on")
            return
        self._info(session, "duels_status_off" if stats.get("no_duels") else "duels_status_on",
                   won=int(stats.get("duels_won") or 0), lost=int(stats.get("duels_lost") or 0),
                   places=self.arena_names(session.lang))

    def cmd_duel(self, session, message):
        char, lang = session.char, session.lang
        rules = self.duel_rules()
        if self._muted(session):
            return
        if not self.in_arena(char):
            self._error(session, "duel_where", places=self.arena_names(lang))
            return
        name = self._arg(message, "to", 40)
        target = self._find_session(name) if name else None
        if not name:
            self._error(session, "duel_how")
            return
        if target is None or target.conn is None or target.invisible or \
                target.char["location"] != char["location"]:
            self._error(session, "duel_not_here", name=name)
            return
        if target is session:
            self._error(session, "duel_yourself")
            return
        stake = self._count(message, default=0, low=0, high=int(rules.get("max_stake", 100)))
        if stake is None:
            self._error(session, "duel_stake", max=int(rules.get("max_stake", 100)))
            return
        if session.key in self.duels or target.key in self.duels or session.arcade or target.arcade:
            self._error(session, "duel_busy", name=target.name if target.key in self.duels or target.arcade
                        else session.name)
            return
        if target.char["stats"].get("no_duels"):
            self._error(session, "duel_refused", name=target.name)
            return
        left = self._cooldown_left(char, "duel")
        if left > 0:
            self._error(session, "duel_rest", time=self._duration(lang, left))
            return
        snub = char["stats"].get("duel_snubs", {}).get(target.key)
        if snub and float(snub) > self.now():
            self._error(session, "duel_snubbed", name=target.name,
                        time=self._duration(lang, float(snub) - self.now()))
            return
        if char["credits"] < stake:
            self._error(session, "duel_poor", stake=stake, credits=char["credits"])
            return
        waiting = self.duel_asks.get(target.key)
        if waiting and waiting["from"] == session.key:
            self._error(session, "duel_waiting", name=target.name)
            return
        now = self.now()
        self.duel_asks[target.key] = {"from": session.key, "from_name": session.name, "stake": stake,
                                      "room": char["location"], "at": now,
                                      "expires": now + float(rules.get("ask_seconds", 60))}
        self._send(target, "offer", "duel_challenged" if stake else "duel_challenged_free",
                   extra={"actor": session.name, "ask": "duel", "sound": "duel_start"},
                   name=session.name, stake=stake)
        self._info(session, "duel_sent" if stake else "duel_sent_free", name=target.name, stake=stake)

    def accept_duel(self, session):
        ask = self.duel_asks.pop(session.key, None)
        if ask is None:
            return False
        other = self.sessions.get(ask["from"])
        if other is None or other.conn is None or other.char["location"] != ask["room"] or \
                session.char["location"] != ask["room"]:
            self._error(session, "duel_gone", name=ask["from_name"])
            return True
        if session.key in self.duels or other.key in self.duels or session.arcade or other.arcade:
            self._error(session, "duel_busy", name=other.name)
            return True
        stake = int(ask["stake"])
        for payer in (session, other):
            if payer.char["credits"] < stake:
                self._error(session, "duel_cant_pay", name=payer.name, stake=stake)
                if payer is not session:
                    self._send(other, "error", "duel_cant_pay", name=payer.name, stake=stake)
                return True
        with self.store.transaction():
            for payer in (session, other):
                if stake:
                    self.spend(payer.char, stake, "duels")
                self._save(payer)
        duel = {"id": self._next_duel, "a": other.key, "b": session.key, "names": {other.key: other.name,
                                                                                     session.key: session.name},
                "stake": stake, "room": ask["room"], "wins": {other.key: 0, session.key: 0}, "rounds": 0,
                "phase": "intro", "next_at": self.now() + 2.0}
        self._next_duel += 1
        self.duels[other.key] = self.duels[session.key] = duel
        logger.info("%s and %s duel for %s", other.name, session.name, stake)
        self._to_room(ask["room"], "announce", "duel_begins" if stake else "duel_begins_free",
                      extra={"sound": "duel_start"}, a=other.name, b=session.name, stake=stake)
        return True

    def decline_duel(self, session):
        ask = self.duel_asks.pop(session.key, None)
        if ask is None:
            return False
        other = self.sessions.get(ask["from"])
        if other is not None:
            snubs = other.char["stats"].setdefault("duel_snubs", {})
            snubs[session.key] = self.now() + float(self.duel_rules().get("declined_seconds", 300))
            self._send(other, "system", "duel_declined", name=session.name)
        self._info(session, "duel_you_declined", name=ask["from_name"])
        return True

    # --- the duel ----------------------------------------------------------------------------------

    def _duelists(self, duel):
        return [self.sessions.get(duel["a"]), self.sessions.get(duel["b"])]

    def _to_duelists(self, duel, kind, key, extra=None, **params):
        for player in self._duelists(duel):
            if player is not None:
                self._send(player, kind, key, extra=extra, **params)

    def tick_duels(self, now):
        for ask_key, ask in list(self.duel_asks.items()):
            if now >= ask["expires"]:
                self.duel_asks.pop(ask_key, None)
                target, challenger = self.sessions.get(ask_key), self.sessions.get(ask["from"])
                if target is not None:
                    self._send(target, "system", "duel_expired_you", name=ask["from_name"])
                if challenger is not None:
                    self._send(challenger, "system", "duel_expired", name=target.name if target else "?")
        seen = set()
        for duel in list(self.duels.values()):
            if duel["id"] in seen:
                continue
            seen.add(duel["id"])
            self._tick_duel(duel, now)

    def _tick_duel(self, duel, now):
        rules = self.duel_rules()
        a, b = self._duelists(duel)
        for player, other in ((a, b), (b, a)):
            if player is None or player.conn is None or player.char["location"] != duel["room"]:
                self._end_duel(duel, winner=other, why="forfeit", loser=player)
                return
        if duel["phase"] in ("intro", "pause") and now >= duel["next_at"]:
            duel["rounds"] += 1
            low, high = rules.get("wait", [2, 5])
            duel.update(phase="wait", go_at=now + self.rng.uniform(float(low), float(high)))
            self._to_duelists(duel, "info", "duel_ready", extra={"sound": "arcade_ready"}, n=duel["rounds"])
        elif duel["phase"] == "wait" and now >= duel["go_at"]:
            duel.update(phase="go", go_sent=now)
            self._to_duelists(duel, "task", "duel_draw", extra={"sound": "arcade_go"})
        elif duel["phase"] == "go" and now - duel["go_sent"] >= float(rules.get("draw_seconds", 3)):
            self._to_duelists(duel, "info", "duel_nobody")
            self._next_duel_round(duel, now)

    def duel_answer(self, session):
        """A number typed while duelling: a draw (or a false start)."""
        duel = self.duels.get(session.key)
        if duel is None:
            return False
        now = self.now()
        other = self.sessions.get(duel["b"] if session.key == duel["a"] else duel["a"])
        if duel["phase"] == "wait":
            self._round_to(duel, other, now, "duel_too_soon", loser=session)
        elif duel["phase"] == "go":
            self._round_to(duel, session, now, "duel_round", ms=int(round((now - duel["go_sent"]) * 1000)))
        else:
            self._error(session, "arcade_wait")
        return True

    def _round_to(self, duel, winner, now, key, loser=None, **params):
        if winner is not None:
            duel["wins"][winner.key] += 1
        a_name, b_name = duel["names"][duel["a"]], duel["names"][duel["b"]]
        self._to_duelists(duel, "info", key, extra={"sound": "arcade_hit"}, name=winner.name if winner else "?",
                          loser=loser.name if loser else "?", a=a_name, b=b_name,
                          wins_a=duel["wins"][duel["a"]], wins_b=duel["wins"][duel["b"]], **params)
        self._next_duel_round(duel, now)

    def _next_duel_round(self, duel, now):
        rules = self.duel_rules()
        need = int(rules.get("wins", 2))
        leader = max(duel["wins"], key=lambda k: duel["wins"][k])
        other_key = duel["b"] if leader == duel["a"] else duel["a"]
        if duel["wins"][leader] >= need:
            self._end_duel(duel, winner=self.sessions.get(leader), loser=self.sessions.get(other_key), why="won")
            return
        if duel["rounds"] >= int(rules.get("max_rounds", 5)):
            if duel["wins"][leader] > duel["wins"][other_key]:
                self._end_duel(duel, winner=self.sessions.get(leader), loser=self.sessions.get(other_key),
                               why="won")
            else:
                self._end_duel(duel, winner=None, why="draw")
            return
        duel.update(phase="pause", next_at=now + 2.0)

    def _end_duel(self, duel, winner, why, loser=None):
        for key in (duel["a"], duel["b"]):
            if self.duels.get(key) is duel:
                self.duels.pop(key, None)
        rules = self.duel_rules()
        stake = int(duel["stake"])
        pot = 2 * stake
        prize = int(pot * (1 - float(rules.get("fee", 0.05)))) if winner is not None else 0
        players = [p for p in self._duelists(duel) if p is not None]
        with self.store.transaction():
            if winner is None or why == "stopped":
                for player in players:
                    if stake:
                        self.earn(player.char, stake, "duels")
            elif prize:
                self.earn(winner.char, prize, "duels")
            for player in players:
                stats = player.char["stats"]
                if winner is not None and why != "stopped":
                    field = "duels_won" if player is winner else "duels_lost"
                    stats[field] = int(stats.get(field) or 0) + 1
                self._set_cooldown(player.char, "duel", float(rules.get("rest_seconds", 60)))
                self._save(player)
        if why == "stopped":
            logger.info("the duel of %s and %s was stopped", *duel["names"].values())
            self._to_room(duel["room"], "announce", "duel_stopped", a=duel["names"][duel["a"]],
                          b=duel["names"][duel["b"]])
            self._tell_away(duel, players, "duel_stopped", a=duel["names"][duel["a"]], b=duel["names"][duel["b"]])
            return
        if winner is None:
            self._to_room(duel["room"], "announce", "duel_draw_end", a=duel["names"][duel["a"]],
                          b=duel["names"][duel["b"]], stake=stake)
            return
        loser_name = duel["names"][duel["b"] if winner.key == duel["a"] else duel["a"]]
        logger.info("%s won the duel against %s (%s)", winner.name, loser_name, why)
        key = ("duel_won_forfeit" if why == "forfeit" else "duel_won") + ("" if prize else "_free")
        params = dict(name=winner.name, loser=loser_name, prize=prize, wins=duel["wins"][winner.key],
                      losses=duel["wins"][duel["b"] if winner.key == duel["a"] else duel["a"]])
        self._to_room(duel["room"], "announce", key, extra={"sound": "win"}, **params)
        self._tell_away(duel, players, key, **params)
        self.check_achievements(winner)

    def _tell_away(self, duel, players, key, **params):
        """A duellist who walked out still hears how it ended."""
        for player in players:
            if player.conn is not None and player.char["location"] != duel["room"]:
                self._send(player, "system", key, **params)

    # --- leaving, admins ---------------------------------------------------------------------------

    def forget_duels(self, session):
        """`session` left the game: its challenges are off, and a duel is forfeit (the tick settles it)."""
        self.duel_asks.pop(session.key, None)
        for key, ask in list(self.duel_asks.items()):
            if ask["from"] == session.key:
                self.duel_asks.pop(key, None)
        duel = self.duels.get(session.key)
        if duel is not None:
            other = self.sessions.get(duel["b"] if session.key == duel["a"] else duel["a"])
            self._end_duel(duel, winner=other, why="forfeit", loser=session)

    def admin_duel_stop(self, session, message):
        name = self._arg(message, "to", 40) or self._arg(message, "a", 40)
        target = self._find_session(name) if name else None
        duel = self.duels.get(target.key) if target else None
        if duel is None:
            self._error(session, "duel_none_for", name=name or "?")
            return
        self._end_duel(duel, winner=None, why="stopped")
        self._log(session, "stop duel", target.name)
        self._info(session, "duel_stop_done", a=duel["names"][duel["a"]], b=duel["names"][duel["b"]])
