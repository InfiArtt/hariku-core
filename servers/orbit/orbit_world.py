# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The station: world.json and economy.json read and checked, and finding
things in them by what players type, in either language ("kantin", "the
cantina", "Kantin!").

world.json
  directions  n, ne, e, se, s, sw, w, nw, u, d: their names and the words for
              them in both languages ("u" is north in Indonesian, up in English)
  areas       the decks and places rooms belong to (Main Deck, Asteroid Belt...)
  locations   the rooms: names, descriptions, ambience, compass exits (an exit
              may be locked, one-way, or lead into vacuum), objects, and flags
              (dark, airless, private, landmark, market, shop...)
  shuttles    rooms joined by a timed shuttle ride instead of a door
  moved       old room ids and the rooms that replaced them
  jobs, goods (the markets' goods), items (what missions ask you to carry),
  missions, emotes, earth (what the Observation Deck names)

economy.json (the balance: levels, the daily bonus, crops, mining, the shops'
things and their effects...). See README.md.

Every thing a character can own (a good, a mission item, a device, a seed,
a sofa...) has one id, unique across both files: World.things.
"""

import collections
import difflib
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LANGS = ("en", "id")
AMBIENCES = ("vent", "cantina", "engine", "garden", "deck", "space", "belt", "venue")
DIRECTIONS = ("n", "ne", "e", "se", "s", "sw", "w", "nw", "u", "d")
LOCKS = ("crew", "tech", "officer", "brass")
THING_TYPES = ("good", "cargo", "gear", "tool", "seed", "consumable", "furniture", "outfit",
               "title", "pet", "service")
_ARTICLES = {"the", "a", "an", "to", "ke", "di", "my", "ku"}
_NOT_WORD = re.compile(r"[^\w\s]")


def norm(text):
    """Lower case, no accents or punctuation, single spaces."""
    text = unicodedata.normalize("NFKD", str(text or "")).casefold()
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(_NOT_WORD.sub(" ", text.replace("'", "")).split())


def _strip_articles(text):
    words = norm(text).split()
    while len(words) > 1 and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


class WorldError(ValueError):
    pass


def _exit(value):
    """An exit as {"to", "lock", "oneway", "msg"}, from "room" or {"to": "room", ...}."""
    if isinstance(value, str):
        return {"to": value, "lock": None, "oneway": False, "msg": None}
    return {"to": value.get("to"), "lock": value.get("lock"), "oneway": bool(value.get("oneway")),
            "msg": value.get("msg")}


class World:
    def __init__(self, data, economy=None):
        self.data = data
        self.economy = economy or {}
        self.start = data["start"]
        self.locations = data["locations"]
        self.areas = data.get("areas", {})
        self.directions = data["directions"]
        self.shuttles = data.get("shuttles", {})
        self.moved = data.get("moved", {})
        self.jobs = data["jobs"]
        self.goods = data["goods"]
        self.items = data["items"]
        self.missions = data["missions"]
        self.emotes = data["emotes"]
        self.regions = data["earth"]["regions"]
        self.exits = {lid: {d: _exit(v) for d, v in (loc.get("exits") or {}).items()}
                      for lid, loc in self.locations.items()}
        self.things = self._things()
        self.crops = self.economy.get("crops", {})
        self.shops = self.economy.get("shops", {})
        self._check()
        self._place_names = self._index({lid: loc.get("aliases", {}) for lid, loc in
                                         self.locations.items() if not loc.get("hidden")},
                                        extra=lambda lid: [self.locations[lid]["name"][lang]
                                                           for lang in LANGS])
        self._good_names = self._index({gid: g["names"] for gid, g in self.goods.items()})
        self._item_names = self._index({iid: i["names"] for iid, i in self.items.items()})
        self._thing_names = self._index({tid: t.get("names", {}) for tid, t in self.things.items()},
                                        extra=lambda tid: [self.things[tid]["one"][lang]
                                                           for lang in LANGS]
                                        + [self.things[tid]["many"][lang] for lang in LANGS])
        self._dir_words = {lang: {} for lang in LANGS}
        for d, info in self.directions.items():
            for lang in LANGS:
                for word in info["words"][lang]:
                    self._dir_words[lang][norm(word)] = d

    @classmethod
    def load(cls, path=None, economy_path=None):
        path = path or os.path.join(HERE, "world.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        economy_path = economy_path or os.path.join(os.path.dirname(os.path.abspath(path)),
                                                    "economy.json")
        if not os.path.exists(economy_path):
            economy_path = os.path.join(HERE, "economy.json")
        with open(economy_path, encoding="utf-8") as f:
            economy = json.load(f)
        return cls(data, economy)

    def _things(self):
        things = {}
        for gid, good in self.goods.items():
            things[gid] = dict(good, type="good", tradeable=True)
        for iid, item in self.items.items():
            things[iid] = dict(item, type="cargo", tradeable=False)
        for tid, thing in (self.economy.get("things") or {}).items():
            things[tid] = dict(thing)
        return things

    # --- checks ------------------------------------------------------------------------

    def _check(self):
        problems = []
        if self.start not in self.locations:
            problems.append(f"the start {self.start!r} is not a location")
        if set(self.directions) != set(DIRECTIONS):
            problems.append("directions must be exactly " + ", ".join(DIRECTIONS))
        for d, info in self.directions.items():
            if info.get("back") not in self.directions or self.directions[info["back"]].get("back") != d:
                problems.append(f"direction {d}: its way back is wrong")
            for lang in LANGS:
                if not info.get("name", {}).get(lang) or not info.get("words", {}).get(lang):
                    problems.append(f"direction {d}: needs a name and words in {lang}")
        for lid, loc in self.locations.items():
            for field in ("name", "ref", "in", "desc"):
                if not all(isinstance(loc.get(field, {}).get(lang), str) for lang in LANGS):
                    problems.append(f"{lid}: {field} needs en and id")
            if loc.get("ambience") not in AMBIENCES:
                problems.append(f"{lid}: unknown ambience {loc.get('ambience')!r}")
            if loc.get("area") not in self.areas:
                problems.append(f"{lid}: unknown area {loc.get('area')!r}")
            for d, ex in self.exits[lid].items():
                if d not in self.directions:
                    problems.append(f"{lid}: unknown direction {d!r}")
                    continue
                if ex["to"] not in self.locations:
                    problems.append(f"{lid}: exit {d} to unknown {ex['to']!r}")
                    continue
                if ex["lock"] is not None and ex["lock"] not in LOCKS:
                    problems.append(f"{lid}: exit {d} has an unknown lock {ex['lock']!r}")
                back = self.exits[ex["to"]].get(self.directions[d]["back"])
                if not ex["oneway"] and (back is None or back["to"] != lid):
                    problems.append(f"{lid} -> {d} -> {ex['to']} has no way back")
            if loc.get("job") and loc["job"] not in self.jobs:
                problems.append(f"{lid}: unknown job {loc['job']!r}")
            if loc.get("shop") and loc["shop"] not in self.shops:
                problems.append(f"{lid}: unknown shop {loc['shop']!r}")
        for a, b in self.shuttles.get("links", []):
            if a not in self.locations or b not in self.locations:
                problems.append(f"shuttle link {a} - {b}: unknown room")
        for old, new in self.moved.items():
            if new not in self.locations:
                problems.append(f"moved {old} -> unknown {new}")
        for mid, mission in self.missions.items():
            if mission["item"] not in self.items:
                problems.append(f"mission {mid}: unknown item")
            for field in ("from", "to"):
                if mission[field] not in self.locations:
                    problems.append(f"mission {mid}: unknown {field}")
            if mission.get("gives") and mission["gives"] not in self.things:
                problems.append(f"mission {mid}: gives an unknown thing")
        for eid, emote in self.emotes.items():
            for lang in LANGS:
                if set(emote.get(lang, {})) != {"you", "they", "you_at", "they_at", "at_you"}:
                    problems.append(f"emote {eid}: {lang} lines incomplete")
        ids = list(self.goods) + list(self.items) + list(self.economy.get("things") or {})
        for tid in {t for t in ids if ids.count(t) > 1}:
            problems.append(f"the id {tid!r} is used twice")
        for tid, thing in self.things.items():
            if thing.get("type") not in THING_TYPES:
                problems.append(f"thing {tid}: unknown type {thing.get('type')!r}")
            for field in ("one", "many"):
                if not all(isinstance(thing.get(field, {}).get(lang), str) for lang in LANGS):
                    problems.append(f"thing {tid}: {field} needs en and id")
        for sid, shop in self.shops.items():
            for tid in shop.get("stock", []):
                if tid not in self.things:
                    problems.append(f"shop {sid}: unknown thing {tid!r}")
                elif not self.things[tid].get("price"):
                    problems.append(f"shop {sid}: {tid} has no price")
        for cid, crop in self.crops.items():
            if crop.get("seed") not in self.things or crop.get("good") not in self.things:
                problems.append(f"crop {cid}: unknown seed or good")
        if problems:
            raise WorldError("; ".join(problems))

    # --- finding by name -----------------------------------------------------------------

    @staticmethod
    def _index(names_by_id, extra=None):
        index = {}
        for thing_id, names in names_by_id.items():
            words = []
            for lang in LANGS:
                words.extend(names.get(lang, []))
            if extra:
                words.extend(extra(thing_id))
            words.append(thing_id)
            for word in words:
                key = _strip_articles(word)
                if key:
                    index.setdefault(key, thing_id)
        return index

    @staticmethod
    def _lookup(index, text, fuzzy=True):
        key = _strip_articles(text)
        if not key:
            return None
        if key in index:
            return index[key]
        # A plural or a possessive: "crates", "kantinnya".
        for suffix in ("s", "es", "nya", "ku", "mu"):
            if key.endswith(suffix) and key[:-len(suffix)] in index:
                return index[key[:-len(suffix)]]
        if fuzzy and len(key) >= 4:
            close = difflib.get_close_matches(key, list(index), n=1, cutoff=0.8)
            if close:
                return index[close[0]]
        return None

    def find_location(self, text):
        """A location id for what a player typed ("kantin", "the cantina"), or None."""
        return self._lookup(self._place_names, text)

    def find_good(self, text):
        return self._lookup(self._good_names, text)

    def find_item(self, text):
        return self._lookup(self._item_names, text)

    def find_thing(self, text, fuzzy=True):
        """Any thing's id (a good, a device, a seed...) for what was typed."""
        return self._lookup(self._thing_names, text, fuzzy)

    def find_object(self, location_id, text):
        """(object id, object) in a location for what was typed, or (None, None)."""
        loc = self.locations.get(location_id, {})
        index = self._index({oid: o["names"] for oid, o in loc.get("objects", {}).items()})
        found = self._lookup(index, text)
        return (found, loc["objects"][found]) if found else (None, None)

    def find_direction(self, text, lang="en"):
        """A direction ("n"...) for a word, the player's own language first:
        "u" is north (utara) in Indonesian and up in English."""
        key = norm(text)
        if not key:
            return None
        other = "en" if lang == "id" else "id"
        for table in (self._dir_words.get(lang, {}), self._dir_words[other]):
            if key in table:
                return table[key]
        return None

    def dir_name(self, d):
        return self.directions[d]["name"]

    # --- the map ----------------------------------------------------------------------

    def neighbours(self, lid):
        """[(direction, exit)] of a room, in compass order."""
        exits = self.exits.get(lid, {})
        return [(d, exits[d]) for d in DIRECTIONS if d in exits]

    def shuttle_partner(self, lid):
        for a, b in self.shuttles.get("links", []):
            if lid == a:
                return b
            if lid == b:
                return a
        return None

    def route(self, start, goal, can_pass=None):
        """The steps from `start` to `goal`: [(direction or "shuttle", room)],
        or None when there's no way. `can_pass(room, exit)` may refuse exits
        (a locked door, vacuum)."""
        if start == goal:
            return []
        previous = {start: None}
        queue = collections.deque([start])
        while queue:
            here = queue.popleft()
            steps = [(d, ex["to"], ex) for d, ex in self.neighbours(here)]
            partner = self.shuttle_partner(here)
            if partner:
                steps.append(("shuttle", partner, None))
            for d, nxt, ex in steps:
                if nxt in previous:
                    continue
                if can_pass is not None and ex is not None and not can_pass(here, ex):
                    continue
                previous[nxt] = (here, d)
                if nxt == goal:
                    path = []
                    node = goal
                    while previous[node] is not None:
                        before, how = previous[node]
                        path.append((how, node))
                        node = before
                    return path[::-1]
                queue.append(nxt)
        return None

    def reachable(self, start=None):
        """Every room that can be reached from the start (doors and shuttles)."""
        start = start or self.start
        seen = {start}
        queue = collections.deque([start])
        while queue:
            here = queue.popleft()
            nexts = [ex["to"] for _d, ex in self.neighbours(here)]
            partner = self.shuttle_partner(here)
            if partner:
                nexts.append(partner)
            for nxt in nexts:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def area_of(self, lid):
        return self.areas.get(self.locations[lid].get("area"), {})

    def at(self, lid):
        """(x, y, z) of a room on its area's plan."""
        at = list(self.locations[lid].get("at") or [0, 0])
        while len(at) < 3:
            at.append(0)
        return tuple(at[:3])

    def heading(self, from_id, to_id):
        """The compass direction from one room to another on the same plan, or None."""
        x1, y1, _z1 = self.at(from_id)
        x2, y2, _z2 = self.at(to_id)
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return None
        sx = (dx > 0) - (dx < 0)
        sy = (dy > 0) - (dy < 0)
        if abs(dx) > 2 * abs(dy):
            sy = 0
        elif abs(dy) > 2 * abs(dx):
            sx = 0
        for d, info in self.directions.items():
            if info.get("dx", 0) == sx and info.get("dy", 0) == sy and not info.get("dz"):
                return d
        return None

    # --- names in sentences -------------------------------------------------------------

    def count_of(self, table, thing_id, n):
        """{"en": "3 sacks of coffee", "id": "3 karung kopi"}."""
        thing = table[thing_id]
        form = thing["one"] if n == 1 else thing["many"]
        return {lang: f"{n} {form[lang]}" for lang in LANGS}

    def thing_count(self, thing_id, n):
        return self.count_of(self.things, thing_id, n)

    def job_name(self, job):
        return self.jobs.get(job, {}).get("name", {"en": job, "id": job})
