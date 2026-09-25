# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Pixel Pier's arcade: four cabinets on Cabinet Row, played with tokens (from
the change machine there, for credits), winning prize tickets for the Prize
Counter, with a high score table for each game on the High Score Wall.

    arcade / arkade                 the cabinets, your tokens and tickets
    play quick draw / main adu cepat   start a game (it takes a token)
    (a number)                      the game's input: both clients send
                                    numbers alone as "answer"
    stop game / berhenti main       end your game now (it counts as it is)
    high scores [game] / skor arkade   the tables

The games, all played by ear:

  Quick Draw (reaction): five rounds; after "ready", wait for the beep, then
    type any number at once. Points by how quickly (0.2 seconds or less: 100,
    2 seconds or more: none); typing too soon scores nothing.
  Star Beat (rhythm): listen to a rhythm (short and long gaps), then tap it
    back, a number and Enter for each beat. Points by how closely each gap
    you tap matches; three rounds, longer each time. Only the gaps between
    your taps count, so the network's delay doesn't.
  Echo (memory): repeat the tones (1 to 4, low to high) as numbers; one more
    each time; the score is the longest you repeated.
  Meteor Dodge (stereo): a meteor comes from the left, the right or straight
    ahead; step away from it (4 left, 6 right; ahead: either) before it hits,
    a little quicker each time; three hits end it; the score is how many you
    dodged. Clients that can't place a sound (Orbit 1.0) are told the side.

Everything is timed on the server, as commands arrive. Tickets can't be
sold, traded or pawned, and neither can the prizes: the arcade only takes
credits out of the economy. A new best on a game's table is announced to
everyone and pays a few tickets more.
"""

import logging
import re

import orbit_safety
from orbit_lang import pick

logger = logging.getLogger("orbit.game")

TOKEN = "arcade_token"
TICKET = "arcade_ticket"
GAMES = ("quickdraw", "starbeat", "echo", "meteor")
INTRO_SECONDS = 3.0           # between the game's welcome and its first round
PAUSE_SECONDS = 2.0           # between rounds
SIDES = {"w": "left", "e": "right", "n": "ahead"}
DODGE_WORDS = {"4": "w", "left": "w", "kiri": "w", "l": "w", "6": "e", "right": "e", "kanan": "e", "r": "e"}


def client_version(name):
    """(major, minor) of the client that said hello ("Hariku Orbit 1.1"), or (0, 0)."""
    text = str(name or "")
    found = re.search(r"(\d+)\.(\d+)", text)
    if not found or "orbit" not in text.lower():
        return (0, 0)
    return (int(found.group(1)), int(found.group(2)))


def tickets_for(rules, score):
    """Prize tickets for a score: (score - from) * rate, at most max."""
    rules = rules or {}
    won = int(max(0, score - float(rules.get("from", 0))) * float(rules.get("rate", 0)))
    return max(0, min(int(rules.get("max", 0)), won))


def beat_points(gaps, taps, tolerance):
    """Star Beat: for each gap of the rhythm, 100 points when the gap between
    your taps matches it, none when it's off by `tolerance` (a fraction) or more."""
    points = []
    for i, gap in enumerate(gaps):
        if i + 1 >= len(taps):
            points.append(0)
            continue
        tapped = taps[i + 1] - taps[i]
        error = abs(tapped - gap) / gap
        points.append(int(round(100 * max(0.0, 1.0 - error / tolerance))))
    return points


def reaction_points(ms, best_ms, worst_ms):
    """Quick Draw: 100 points at best_ms or quicker, none at worst_ms or slower."""
    span = max(1.0, float(worst_ms) - float(best_ms))
    return int(round(100 * max(0.0, min(1.0, (float(worst_ms) - ms) / span))))


class ArcadeMixin:
    @staticmethod
    def commands():
        return {"arcade": ArcadeMixin.cmd_arcade, "play": ArcadeMixin.cmd_play,
                "stop_game": ArcadeMixin.cmd_stop_game, "high_scores": ArcadeMixin.cmd_high_scores}

    # --- what there is ---------------------------------------------------------------------

    def arcade_rules(self):
        return self.econ.get("arcade", {})

    def arcade_game(self, gid):
        return self.arcade_rules().get("games", {}).get(gid)

    def find_arcade_game(self, text):
        key = orbit_safety.name_key(text)
        if not key:
            return None
        for gid in GAMES:
            game = self.arcade_game(gid) or {}
            names = [gid] + [n for lang in ("en", "id") for n in (game.get("names") or {}).get(lang, [])]
            if key in {orbit_safety.name_key(n) for n in names}:
                return gid
        for gid in GAMES:                  # "meteor" for Meteor Dodge
            game = self.arcade_game(gid) or {}
            names = [n for lang in ("en", "id") for n in (game.get("names") or {}).get(lang, [])]
            if any(orbit_safety.name_key(n).startswith(key) for n in names if len(key) >= 4):
                return gid
        return None

    def at_cabinets(self, char):
        return bool(self._loc(char).get("arcade"))

    def _count_owned(self, char, tid):
        return int(char["inventory"].get(tid) or 0)

    def cmd_arcade(self, session, message):
        char, lang = session.char, session.lang
        entries = []
        for gid in GAMES:
            game = self.arcade_game(gid)
            entries.append(self.render(lang, "arcade_entry", game=game["name"], how=game["desc"],
                                       tokens=int(game.get("tokens", 1))))
        place = next((loc["ref"] for loc in self.world.locations.values() if loc.get("arcade")), None)
        self._info(session, "arcade_list", entries=" ".join(entries), place=place or "",
                   tokens=self._count_owned(char, TOKEN), tickets=self._count_owned(char, TICKET),
                   price=int(self.world.things[TOKEN].get("price") or 0))

    # --- playing ----------------------------------------------------------------------------

    def cmd_play(self, session, message):
        char, lang = session.char, session.lang
        text = self._arg(message, "a", 40)
        gid = self.find_arcade_game(text) if text else None
        raw = self._arg(message, "raw", 80)
        if gid is None and raw and self.world.find_location(raw):
            self.cmd_go(session, {"a": raw})            # "main street": a place
            return
        if gid is None:
            if text and self.world.find_thing(text):
                self._error(session, "arcade_not_a_game", what=text)
            else:
                self._error(session, "arcade_which", games=", ".join(
                    pick(self.arcade_game(g)["name"], lang) for g in GAMES))
            return
        if not self.at_cabinets(char):
            place = next((loc["ref"] for loc in self.world.locations.values() if loc.get("arcade")), None)
            self._error(session, "arcade_where", place=place)
            return
        if session.arcade:
            self._error(session, "arcade_busy", game=self.arcade_game(session.arcade["game"])["name"])
            return
        game = self.arcade_game(gid)
        cost = int(game.get("tokens", 1))
        have = self._count_owned(char, TOKEN)
        if have < cost:
            self._error(session, "arcade_no_tokens", n=cost, have=have,
                         price=int(self.world.things[TOKEN].get("price") or 0))
            return
        if not self._slow(session):
            return
        self._take_away(char, TOKEN, cost)
        self._save(session)
        now = self.now()
        session.arcade = {"game": gid, "started": now, "phase": "intro", "next_at": now + INTRO_SECONDS,
                          "score": 0, "round": 0}
        logger.info("%s plays %s", session.name, gid)
        self._send(session, "task", f"arcade_intro_{gid}", extra={"sound": "arcade_start"},
                   game=game["name"], tokens=self._count_owned(char, TOKEN))

    def cmd_stop_game(self, session, message):
        if not session.arcade:
            self._error(session, "arcade_not_playing")
            return
        self.arcade_finish(session, "stopped")

    def arcade_answer(self, session, text):
        """A number (or a side) typed while playing: what it means in the game."""
        state = session.arcade
        if not self.at_cabinets(session.char):
            self.arcade_finish(session, "left")
            return
        handler = getattr(self, "_answer_" + state["game"])
        handler(session, state, str(text or "").strip().lower(), self.now())

    def arcade_side(self, session, text):
        """Meteor Dodge's words ("left", "kanan"), read before anything else while it's on."""
        state = session.arcade
        if not state or state["game"] != "meteor":
            return False
        key = orbit_safety.name_key(text)
        if key not in DODGE_WORDS:
            return False
        self.arcade_answer(session, key)
        return True

    def tick_arcade(self, session, now):
        state = session.arcade
        if not state:
            return
        if not self.at_cabinets(session.char):
            self.arcade_finish(session, "left")
            return
        getattr(self, "_tick_" + state["game"])(session, state, now)

    def arcade_left(self, session):
        """`session` moved: a game in progress ends where the player left it."""
        if session.arcade and not self.at_cabinets(session.char):
            self.arcade_finish(session, "left")

    def _between(self, session):
        self._error(session, "arcade_wait")

    # --- Quick Draw -----------------------------------------------------------------------------

    def _tick_quickdraw(self, session, state, now):
        game = self.arcade_game("quickdraw")
        if state["phase"] in ("intro", "pause") and now >= state["next_at"]:
            state["round"] += 1
            low, high = game.get("wait", [2, 5])
            state.update(phase="wait", go_at=now + self.rng.uniform(float(low), float(high)))
            self._send(session, "info", "arcade_qd_ready", extra={"sound": "arcade_ready"},
                       n=state["round"], total=int(game["rounds"]))
        elif state["phase"] == "wait" and now >= state["go_at"]:
            state.update(phase="go", go_sent=now)
            self._send(session, "task", "arcade_qd_go", extra={"sound": "arcade_go"})
        elif state["phase"] == "go" and (now - state["go_sent"]) * 1000 >= float(game["worst_ms"]):
            self._quickdraw_round(session, state, now, None)

    def _answer_quickdraw(self, session, state, text, now):
        if state["phase"] == "wait":
            state.setdefault("results", []).append(0)
            self._send(session, "failed", "arcade_qd_soon", extra={"sound": "fail"})
            self._next_round(session, state, now, int(self.arcade_game("quickdraw")["rounds"]))
        elif state["phase"] == "go":
            self._quickdraw_round(session, state, now, (now - state["go_sent"]) * 1000)
        else:
            self._between(session)

    def _quickdraw_round(self, session, state, now, ms):
        game = self.arcade_game("quickdraw")
        if ms is None:
            points = 0
            self._send(session, "failed", "arcade_qd_slow", extra={"sound": "fail"})
        else:
            points = reaction_points(ms, game["best_ms"], game["worst_ms"])
            state.setdefault("times", []).append(ms)
            self._send(session, "paid", "arcade_qd_time", extra={"sound": "arcade_hit"},
                       ms=int(round(ms)), points=points)
        state.setdefault("results", []).append(points)
        state["score"] = sum(state["results"])
        self._next_round(session, state, now, int(game["rounds"]))

    def _next_round(self, session, state, now, rounds):
        if len(state.get("results", [])) >= rounds:
            self.arcade_finish(session, "done")
            return
        state.update(phase="pause", next_at=now + PAUSE_SECONDS)

    # --- Star Beat --------------------------------------------------------------------------------

    def _tick_starbeat(self, session, state, now):
        game = self.arcade_game("starbeat")
        rounds = list(game["rounds"])
        if state["phase"] in ("intro", "pause") and now >= state["next_at"]:
            beats = int(rounds[state["round"]])
            state["round"] += 1
            short, long_ = float(game["short"]), float(game["long"])
            gaps = [self.rng.choice((short, long_)) for _ in range(beats - 1)]
            if len(set(gaps)) == 1:                     # always some of each
                gaps[self.rng.randrange(len(gaps))] = long_ if gaps[0] == short else short
            lead = float(game["lead"])
            offsets = [lead]
            for gap in gaps:
                offsets.append(offsets[-1] + gap)
            state.update(phase="tap", gaps=gaps, taps=[],
                         deadline=now + offsets[-1] + float(game["tap_seconds"]))
            lang = session.lang
            pattern = ", ".join(self.render(lang, "arcade_sb_short" if g == short else "arcade_sb_long")
                                for g in gaps)
            self._send(session, "task", "arcade_sb_round", extra={"beats": [round(o, 3) for o in offsets]},
                       n=state["round"], total=len(rounds), beats=beats, pattern=pattern)
        elif state["phase"] == "tap" and now >= state["deadline"]:
            self._starbeat_round(session, state, now)

    def _answer_starbeat(self, session, state, text, now):
        if state["phase"] != "tap":
            self._between(session)
            return
        state["taps"].append(now)
        if len(state["taps"]) >= len(state["gaps"]) + 1:
            self._starbeat_round(session, state, now)

    def _starbeat_round(self, session, state, now):
        game = self.arcade_game("starbeat")
        points = beat_points(state["gaps"], state["taps"], float(game["tolerance"]))
        state.setdefault("results", []).append(sum(points))
        state["score"] = sum(state["results"])
        self._send(session, "paid" if sum(points) else "failed", "arcade_sb_result",
                   extra={"sound": "arcade_hit" if sum(points) else "fail"},
                   points=sum(points), max=100 * len(points))
        self._next_round(session, state, now, len(game["rounds"]))

    # --- Echo ---------------------------------------------------------------------------------------

    def _echo_send(self, session, state, now, key):
        game = self.arcade_game("echo")
        seq = state["seq"]
        state.update(phase="answer", deadline=now + float(game["seconds"]) + float(game["per_tone"]) * len(seq))
        self._send(session, "tones", key, extra={"codes": list(seq)}, n=len(seq))

    def _tick_echo(self, session, state, now):
        game = self.arcade_game("echo")
        if state["phase"] == "intro" and now >= state["next_at"]:
            state["seq"] = [self.rng.randint(1, 4) for _ in range(int(game["start"]))]
            self._echo_send(session, state, now, "arcade_echo_first")
        elif state["phase"] == "answer" and now >= state["deadline"]:
            self._send(session, "failed", "arcade_echo_late", extra={"sound": "fail"},
                       codes=", ".join(map(str, state["seq"])))
            self.arcade_finish(session, "done")

    def _answer_echo(self, session, state, text, now):
        if state["phase"] != "answer":
            self._between(session)
            return
        game = self.arcade_game("echo")
        digits = [int(d) for d in re.findall(r"[1-4]", text)]
        if digits != state["seq"]:
            self._send(session, "failed", "arcade_echo_wrong", extra={"sound": "fail"},
                       codes=", ".join(map(str, state["seq"])))
            self.arcade_finish(session, "done")
            return
        state["score"] = len(state["seq"])
        if len(state["seq"]) >= int(game["max"]):
            self.arcade_finish(session, "done")
            return
        state["seq"].append(self.rng.randint(1, 4))
        self._echo_send(session, state, now, "arcade_echo_next")

    # --- Meteor Dodge -------------------------------------------------------------------------------

    def _tick_meteor(self, session, state, now):
        game = self.arcade_game("meteor")
        if state["phase"] in ("intro", "pause") and now >= state["next_at"]:
            state.setdefault("lives", int(game["lives"]))
            side = self.rng.choice(("w", "e", "n"))
            limit = max(float(game["fastest"]), float(game["limit"]) - float(game["faster"]) * state["score"])
            state.update(phase="incoming", side=side, sent_at=now, limit=limit)
            state["round"] += 1
            stereo = getattr(session, "client", (0, 0)) >= (1, 1)
            key = "arcade_meteor" if stereo else f"arcade_meteor_{SIDES[side]}"
            self._send(session, "task", key, extra={"sound": "arcade_meteor", "dir": side})
        elif state["phase"] == "incoming" and now > state["sent_at"] + state["limit"] + 0.25:
            self._meteor_hit(session, state, now, "arcade_meteor_late")

    def _answer_meteor(self, session, state, text, now):
        if state["phase"] != "incoming":
            self._between(session)
            return
        step = DODGE_WORDS.get(orbit_safety.name_key(text))
        if step is None:
            self._error(session, "arcade_meteor_how")
            return
        if now - state["sent_at"] > state["limit"]:
            self._meteor_hit(session, state, now, "arcade_meteor_late")
        elif step == state["side"]:
            self._meteor_hit(session, state, now, "arcade_meteor_into")
        else:
            state["score"] += 1
            state.update(phase="pause", next_at=now + self._meteor_pause())
            self._send(session, "paid", "arcade_meteor_dodged", extra={"sound": "arcade_whoosh"},
                       n=state["score"])

    def _meteor_pause(self):
        low, high = self.arcade_game("meteor").get("pause", [1, 2])
        return self.rng.uniform(float(low), float(high))

    def _meteor_hit(self, session, state, now, key):
        state["lives"] = int(state.get("lives", 1)) - 1
        self._send(session, "failed", key, extra={"sound": "arcade_crash"}, lives=max(0, state["lives"]))
        if state["lives"] <= 0:
            self.arcade_finish(session, "done")
            return
        state.update(phase="pause", next_at=now + self._meteor_pause())

    # --- the end: the score, tickets, the table ------------------------------------------------------

    def arcade_finish(self, session, why):
        state = session.arcade
        if not state:
            return
        session.arcade = None
        char, lang = session.char, session.lang
        gid = state["game"]
        game = self.arcade_game(gid)
        score = int(state.get("score", 0))
        tickets = tickets_for(game.get("tickets"), score)
        best, top = self.store.arcade_best(gid, char["id"]), self.store.arcade_top(gid, 1)
        record = score > 0 and (not top or score > top[0][1])
        if record:
            tickets += int(self.arcade_rules().get("record_bonus", 0))
        with self.store.transaction():
            self.store.save_arcade_score(gid, char["id"], score, self.now())
            if tickets:
                self.give_thing(char, TICKET, tickets)
            stats = char["stats"]
            stats["arcade_games"] = int(stats.get("arcade_games") or 0) + 1
            if record:
                stats["arcade_records"] = int(stats.get("arcade_records") or 0) + 1
            self._save(session)
        logger.info("%s scored %s at %s", session.name, score, gid)
        parts = [self.render(lang, f"arcade_over_{why}"),
                 self.render(lang, f"arcade_score_{gid}", score=score, ms=self._average_ms(state))]
        if record:
            parts.append(self.render(lang, "arcade_record"))
        elif best is not None and score > best:
            parts.append(self.render(lang, "arcade_best", before=best))
        parts.append(self.render(lang, "arcade_tickets", n=tickets, total=self._count_owned(char, TICKET))
                     if tickets else self.render(lang, "arcade_no_tickets"))
        self._send(session, "paid" if tickets else "info", text=" ".join(parts),
                   extra={"sound": "arcade_ticket" if tickets else "arcade_over"})
        if record:
            self._to_all("announce", "arcade_record_news", exclude=(session,), extra={"sound": "achievement"},
                         name=session.name, game=game["name"], score=score)
        self.check_achievements(session)

    @staticmethod
    def _average_ms(state):
        times = state.get("times") or []
        return int(round(sum(times) / len(times))) if times else 0

    # --- the tables --------------------------------------------------------------------------------

    def cmd_high_scores(self, session, message):
        lang = session.lang
        text = self._arg(message, "a", 40)
        gid = self.find_arcade_game(text) if text else None
        if text and gid is None:
            self._error(session, "arcade_which", games=", ".join(
                pick(self.arcade_game(g)["name"], lang) for g in GAMES))
            return
        size = int(self.arcade_rules().get("table_size", 5))
        tables = []
        for g in [gid] if gid else GAMES:
            rows = self.store.arcade_top(g, size if gid else 3)
            entries = "; ".join(self.render(lang, "arcade_table_entry", place=i, name=name, score=score)
                                for i, (name, score) in enumerate(rows, 1)) or self.render(lang, "board_empty")
            tables.append(self.render(lang, "arcade_table", game=self.arcade_game(g)["name"], entries=entries))
        mine = []
        if gid:
            best = self.store.arcade_best(gid, session.char["id"])
            if best is not None:
                mine.append(self.render(lang, "arcade_your_best", score=best))
        self._info(session, text=" ".join(tables + mine))
