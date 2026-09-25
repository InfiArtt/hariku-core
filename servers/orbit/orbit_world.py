# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The station: world.json read and checked, and finding things in it by what
players type, in either language ("kantin", "the cantina", "Kantin!").

  locations  where you can be: names, descriptions, ambience, exits, objects
  jobs       pilot, engineer, trader, scientist, security
  goods      what the Promenade's market sells (base prices)
  items      what missions ask you to carry
  missions   the templates the daily board picks from
  emotes     smile, wave... and their lines
  earth      the regions the Observation Deck names
"""

import collections
import difflib
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LANGS = ("en", "id")
AMBIENCES = ("vent", "cantina", "engine", "garden", "deck")
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


class World:
    def __init__(self, data):
        self.data = data
        self.start = data["start"]
        self.locations = data["locations"]
        self.jobs = data["jobs"]
        self.goods = data["goods"]
        self.items = data["items"]
        self.missions = data["missions"]
        self.emotes = data["emotes"]
        self.regions = data["earth"]["regions"]
        self._check()
        self._place_names = self._index({lid: loc.get("aliases", {}) for lid, loc in
                                         self.locations.items() if not loc.get("hidden")},
                                        extra=lambda lid: [self.locations[lid]["name"][lang]
                                                           for lang in LANGS])
        self._good_names = self._index({gid: g["names"] for gid, g in self.goods.items()})
        self._item_names = self._index({iid: i["names"] for iid, i in self.items.items()})

    @classmethod
    def load(cls, path=None):
        with open(path or os.path.join(HERE, "world.json"), encoding="utf-8") as f:
            return cls(json.load(f))

    # --- checks ------------------------------------------------------------------------

    def _check(self):
        problems = []
        if self.start not in self.locations:
            problems.append(f"the start {self.start!r} is not a location")
        for lid, loc in self.locations.items():
            for field in ("name", "ref", "in", "desc"):
                if not all(isinstance(loc.get(field, {}).get(lang), str) for lang in LANGS):
                    problems.append(f"{lid}: {field} needs en and id")
            if loc.get("ambience") not in AMBIENCES:
                problems.append(f"{lid}: unknown ambience {loc.get('ambience')!r}")
            for exit_id in loc.get("exits", []):
                if exit_id not in self.locations:
                    problems.append(f"{lid}: exit to unknown {exit_id!r}")
                elif lid not in self.locations[exit_id].get("exits", []):
                    problems.append(f"{lid} -> {exit_id} has no way back")
            if loc.get("job") and loc["job"] not in self.jobs:
                problems.append(f"{lid}: unknown job {loc['job']!r}")
        for mid, mission in self.missions.items():
            if mission["item"] not in self.items:
                problems.append(f"mission {mid}: unknown item")
            for field in ("from", "to"):
                if mission[field] not in self.locations:
                    problems.append(f"mission {mid}: unknown {field}")
        for eid, emote in self.emotes.items():
            for lang in LANGS:
                if set(emote.get(lang, {})) != {"you", "they", "you_at", "they_at", "at_you"}:
                    problems.append(f"emote {eid}: {lang} lines incomplete")
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

    def find_object(self, location_id, text):
        """(object id, object) in a location for what was typed, or (None, None)."""
        loc = self.locations.get(location_id, {})
        index = self._index({oid: o["names"] for oid, o in loc.get("objects", {}).items()})
        found = self._lookup(index, text)
        return (found, loc["objects"][found]) if found else (None, None)

    # --- the map ----------------------------------------------------------------------

    def route(self, start, goal):
        """The locations walked through from `start` to `goal`, both
        included, or None when there's no way."""
        if start == goal:
            return [start]
        previous = {start: None}
        queue = collections.deque([start])
        while queue:
            here = queue.popleft()
            for nxt in self.locations[here].get("exits", []):
                if nxt in previous:
                    continue
                previous[nxt] = here
                if nxt == goal:
                    path = [goal]
                    while previous[path[-1]] is not None:
                        path.append(previous[path[-1]])
                    return path[::-1]
                queue.append(nxt)
        return None

    def reachable(self):
        """Every location a player can walk to from the start."""
        seen = {self.start}
        queue = collections.deque([self.start])
        while queue:
            for nxt in self.locations[queue.popleft()].get("exits", []):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    # --- names in sentences -------------------------------------------------------------

    def count_of(self, table, thing_id, n):
        """{"en": "3 sacks of coffee", "id": "3 karung kopi"}."""
        thing = table[thing_id]
        form = thing["one"] if n == 1 else thing["many"]
        return {lang: f"{n} {form[lang]}" for lang in LANGS}

    def job_name(self, job):
        return self.jobs.get(job, {}).get("name", {"en": job, "id": job})
