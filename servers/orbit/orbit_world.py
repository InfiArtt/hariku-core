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
things in them by what players type ("cantina", "the cantina", "Cantina!").
Every text there is an {"en": ...} dict: Orbit is played in English
(orbit_lang).

world.json
  directions  n, ne, e, se, s, sw, w, nw, u, d: their names and the words for
              them ("u" is up, "d" down)
  areas       the decks and places rooms belong to (Main Deck, Asteroid Belt...),
              each in a world
  worlds      the station and the other worlds of the simulation (the Moon,
              Karmina, Glasir, the Drift Bazaar, Evergrove, Lumina City, Pixel
              Pier, the Asteroid Belt): where ships dock, the ferry stops and
              the Gate opens in each, how far apart they are, their customs,
              fuel and market prices
  locations   the rooms: names, descriptions, ambience, compass exits (an exit
              may be locked, one-way, or lead into vacuum), objects, and flags
              (dark, airless, private, landmark, market, shop...). A market
              buys and sells kinds of goods or single goods (World.markets);
              a good is traded at one market on each world
  shuttles    rooms joined by a timed shuttle ride instead of a door
  moved       old room ids and the rooms that replaced them
  jobs, goods (the markets' goods), items (what missions ask you to carry),
  missions, emotes, earth (what the Observation Deck names)
  events      what happens to everyone now and then (see orbit_events.py)

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

from orbit_lang import LANGUAGES

HERE = os.path.dirname(os.path.abspath(__file__))
LANGS = LANGUAGES                  # ("en",): the language every text of the data has
AMBIENCES = ("vent", "cantina", "engine", "garden", "deck", "space", "belt", "venue", "mall", "casino",
             "gate", "moon", "colony", "ice", "bazaar", "forest", "neon", "arcade")
DIRECTIONS = ("n", "ne", "e", "se", "s", "sw", "w", "nw", "u", "d")
LOCKS = ("crew", "tech", "officer", "brass")
FLOORS = ("metal", "carpet", "grass", "stone", "rock", "suit", "wet", "sand", "snow", "wood", "dust")
ACOUSTICS = ("room", "small", "hall", "hangar", "outside", "cave", "open")
VIAS = ("walk", "lift", "ladder", "slide", "airlock", "door", "gate")
THING_TYPES = ("good", "cargo", "gear", "tool", "seed", "consumable", "furniture", "outfit",
               "title", "pet", "service", "ship", "arcade")
GOOD_KINDS = ("trade", "crop", "ore", "salvage", "contraband")
LEGAL_KINDS = ("trade", "crop", "ore", "salvage")          # what "market": true deals in
_ARTICLES = {"the", "a", "an", "to", "my"}
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


def strip_articles(text):
    """What a name is compared as: lower case, no punctuation, no "the" in front."""
    return _strip_articles(text)


class WorldError(ValueError):
    pass


def _exit(value):
    """An exit as {"to", "lock", "oneway", "msg", "via"}, from "room" or {"to": "room", ...}."""
    if isinstance(value, str):
        return {"to": value, "lock": None, "oneway": False, "msg": None, "via": "walk"}
    return {"to": value.get("to"), "lock": value.get("lock"), "oneway": bool(value.get("oneway")),
            "msg": value.get("msg"), "via": value.get("via") or "walk"}


class World:
    def __init__(self, data, economy=None, npcs=None):
        self.data = data
        self.economy = economy or {}
        self.npcs = npcs or {}
        self.start = data["start"]
        self.locations = data["locations"]
        self.areas = data.get("areas", {})
        self.directions = data["directions"]
        self.shuttles = data.get("shuttles", {})
        self.worlds = data.get("worlds", {})
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
        self.markets, self._market_problems = self._read_markets()
        self._check()
        self._place_names = self._index({lid: loc.get("aliases", {}) for lid, loc in
                                         self.locations.items() if not loc.get("hidden")},
                                        extra=lambda lid: [self.locations[lid]["name"][lang]
                                                           for lang in LANGS])
        self._good_names = self._index({gid: g["names"] for gid, g in self.goods.items()})
        self._world_names = self._index({wid: wd.get("aliases", {}) for wid, wd in self.worlds.items()},
                                        extra=lambda wid: [self.worlds[wid]["name"][lang] for lang in LANGS]
                                        + [self.worlds[wid]["ref"][lang] for lang in LANGS])
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
    def load(cls, path=None, economy_path=None, npcs_path=None):
        path = path or os.path.join(HERE, "world.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        folder = os.path.dirname(os.path.abspath(path))
        economy_path = economy_path or os.path.join(folder, "economy.json")
        if not os.path.exists(economy_path):
            economy_path = os.path.join(HERE, "economy.json")
        with open(economy_path, encoding="utf-8") as f:
            economy = json.load(f)
        npcs_path = npcs_path or os.path.join(folder, "npcs.json")
        if not os.path.exists(npcs_path):
            npcs_path = os.path.join(HERE, "npcs.json")
        with open(npcs_path, encoding="utf-8") as f:
            npcs = json.load(f)
        return cls(data, economy, npcs)

    def _read_markets(self):
        """Every market room's {"buys", "sells"} (sets of good ids), "factor" (for every good
        there, times "prices": a factor for each good) and "about" (what it deals in, in words,
        or None); and the problems found. A market's "buys" and "sells" may name kinds of goods
        ("crop") or goods ("coffee"); "market": true deals in every legal good."""
        markets, problems = {}, []

        def goods_of(lid, words):
            found = set()
            for word in words:
                if word in GOOD_KINDS:
                    found |= {gid for gid, good in self.goods.items() if good.get("kind", "trade") == word}
                elif word in self.goods:
                    found.add(word)
                else:
                    problems.append(f"{lid}: its market names the unknown {word!r}")
            return found

        for lid, loc in self.locations.items():
            spec = loc.get("market")
            if not spec:
                continue
            if spec is True:
                spec = {"buys": list(LEGAL_KINDS), "sells": list(LEGAL_KINDS)}
            if not isinstance(spec, dict):
                problems.append(f"{lid}: a market is true or {{buys, sells, factor, prices, about}}")
                continue
            market = {"buys": goods_of(lid, spec.get("buys") or []), "sells": goods_of(lid, spec.get("sells") or []),
                      "factor": 1.0, "prices": {}, "about": spec.get("about")}
            try:
                market["factor"] = float(spec.get("factor", 1.0))
                market["prices"] = {gid: float(v) for gid, v in (spec.get("prices") or {}).items()}
            except (TypeError, ValueError):
                problems.append(f"{lid}: a market's factor and prices are numbers")
            if market["factor"] <= 0 or any(v <= 0 for v in market["prices"].values()):
                problems.append(f"{lid}: a market's factors are above 0")
            for gid in market["prices"]:
                if gid not in market["buys"] | market["sells"]:
                    problems.append(f"{lid}: its market has a price for {gid!r}, which it doesn't deal in")
            if not market["buys"] | market["sells"]:
                problems.append(f"{lid}: its market deals in nothing")
            about = market["about"]
            if about is not None and not all(isinstance(about.get(lang), str) for lang in LANGS):
                problems.append(f"{lid}: its market's about needs en")
            markets[lid] = market
        # One market for each good on a world: a world's prices are the prices at its market.
        dealer = {}
        for lid, market in markets.items():
            wid = self.world_of(lid)
            for gid in sorted(market["buys"] | market["sells"]):
                other = dealer.get((wid, gid))
                if other:
                    problems.append(f"{gid} is traded at both {other} and {lid}, on the same world")
                dealer[(wid, gid)] = lid
        return markets, problems

    def market_factor(self, lid, gid):
        """How a market's price for `gid` compares to its world's."""
        market = self.markets.get(lid)
        if market is None:
            return 1.0
        return market["factor"] * market["prices"].get(gid, 1.0)

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
                    problems.append(f"{lid}: {field} needs en")
            if loc.get("ambience") not in AMBIENCES:
                problems.append(f"{lid}: unknown ambience {loc.get('ambience')!r}")
            if loc.get("area") not in self.areas:
                problems.append(f"{lid}: unknown area {loc.get('area')!r}")
            if loc.get("floor", "metal") not in FLOORS:
                problems.append(f"{lid}: unknown floor {loc.get('floor')!r}")
            if loc.get("acoustics", "room") not in ACOUSTICS:
                problems.append(f"{lid}: unknown acoustics {loc.get('acoustics')!r}")
            for d, ex in self.exits[lid].items():
                if d not in self.directions:
                    problems.append(f"{lid}: unknown direction {d!r}")
                    continue
                if ex["to"] not in self.locations:
                    problems.append(f"{lid}: exit {d} to unknown {ex['to']!r}")
                    continue
                if ex["lock"] is not None and ex["lock"] not in LOCKS:
                    problems.append(f"{lid}: exit {d} has an unknown lock {ex['lock']!r}")
                if ex["via"] not in VIAS:
                    problems.append(f"{lid}: exit {d} has an unknown way {ex['via']!r}")
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
        problems.extend(self._check_worlds())
        problems.extend(self._check_events())
        problems.extend(self._check_npcs())
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
                    problems.append(f"thing {tid}: {field} needs en")
        for sid, shop in self.shops.items():
            currency = shop.get("currency")
            if currency and currency not in self.things:
                problems.append(f"shop {sid}: unknown currency {currency!r}")
            for tid in shop.get("stock", []):
                if tid not in self.things:
                    problems.append(f"shop {sid}: unknown thing {tid!r}")
                elif not self.things[tid].get("tickets" if currency else "price"):
                    problems.append(f"shop {sid}: {tid} has no price")
        for cid, crop in self.crops.items():
            if crop.get("seed") not in self.things or crop.get("good") not in self.things:
                problems.append(f"crop {cid}: unknown seed or good")
        if problems:
            raise WorldError("; ".join(problems))

    def _check_worlds(self):
        problems = []
        for aid, area in self.areas.items():
            if area.get("world") is not None and area["world"] not in self.worlds:
                problems.append(f"area {aid}: unknown world {area['world']!r}")
            if area.get("rescue") and area["rescue"] not in self.locations:
                problems.append(f"area {aid}: unknown rescue room {area['rescue']!r}")
        for wid, world in self.worlds.items():
            for field in ("name", "ref", "in", "about"):
                if not all(isinstance(world.get(field, {}).get(lang), str) for lang in LANGS):
                    problems.append(f"world {wid}: {field} needs en")
            for field in ("port", "ferry", "gate"):
                lid = world.get(field)
                if field == "port" and lid is None:
                    problems.append(f"world {wid}: needs a port")
                if lid is not None and (lid not in self.locations or self.world_of(lid) != wid):
                    problems.append(f"world {wid}: its {field} {lid!r} is not one of its rooms")
            for gid in world.get("prices", {}):
                if gid not in self.goods:
                    problems.append(f"world {wid}: a price for the unknown good {gid!r}")
        for lid, loc in self.locations.items():
            if self.areas.get(loc.get("area"), {}).get("world") is None and not loc.get("hidden"):
                problems.append(f"{lid}: its area is in no world")
        for gid, good in self.goods.items():
            if good.get("kind", "trade") not in GOOD_KINDS:
                problems.append(f"good {gid}: unknown kind {good.get('kind')!r}")
        problems.extend(self._market_problems)
        for lid in self.markets:
            if self.world_of(lid) is None:
                problems.append(f"{lid}: a market in no world")
        economy = self.economy
        for lid, loc in self.locations.items():
            if loc.get("mine") and loc["mine"] not in economy.get("mining", {}).get("tables", {}):
                problems.append(f"{lid}: no mining table {loc['mine']!r}")
            if loc.get("salvage") and loc["salvage"] not in economy.get("salvage", {}).get("tables", {}):
                problems.append(f"{lid}: no collecting table {loc['salvage']!r}")
            for cid in loc.get("creatures", []):
                if cid not in economy.get("creatures", {}):
                    problems.append(f"{lid}: unknown creature {cid!r}")
        for spot, tables in economy.get("mining", {}).get("tables", {}).items():
            for tier, table in tables.items():
                for gid in table:
                    if gid not in self.goods:
                        problems.append(f"mining {spot}/{tier}: unknown good {gid!r}")
        for spot, table in economy.get("salvage", {}).get("tables", {}).items():
            for gid in table:
                if gid not in self.goods:
                    problems.append(f"collecting {spot}: unknown good {gid!r}")
        for cid, creature in economy.get("creatures", {}).items():
            for gid in creature.get("loot", {}):
                if gid not in self.goods:
                    problems.append(f"creature {cid}: unknown loot {gid!r}")
        for lid in economy.get("gigs", {}).get("to", []):
            if lid not in self.locations:
                problems.append(f"gigs: unknown room {lid!r}")
        return problems

    EVENT_KINDS = ("random", "weekly", "seasonal", "hosted", "custom")
    EVENT_ACTIONS = (None, "collect", "seek", "watch", "join", "gift", "boss")

    def _check_events(self):
        problems = []
        for eid, event in self.data.get("events", {}).items():
            if event.get("kind") not in self.EVENT_KINDS:
                problems.append(f"event {eid}: unknown kind {event.get('kind')!r}")
            if event.get("action") not in self.EVENT_ACTIONS:
                problems.append(f"event {eid}: unknown action {event.get('action')!r}")
            for field in ("name", "about", "start", "end"):
                if not all(isinstance(event.get(field, {}).get(lang), str) for lang in LANGS):
                    problems.append(f"event {eid}: {field} needs en")
            if not float(event.get("duration") or 0) > 0:
                problems.append(f"event {eid}: needs a duration")
            rooms = list(event.get("rooms") or []) + list((event.get("effect") or {}).get("dark") or [])
            for lid in rooms:
                if lid not in self.locations:
                    problems.append(f"event {eid}: unknown room {lid!r}")
            for gid in (event.get("loot") or {}):
                if gid not in self.goods:
                    problems.append(f"event {eid}: unknown loot {gid!r}")
            thing = (event.get("gift") or {}).get("thing")
            if thing and thing not in self.things:
                problems.append(f"event {eid}: unknown gift {thing!r}")
            if event.get("action") in ("collect", "seek", "watch", "boss") and not event.get("rooms"):
                problems.append(f"event {eid}: needs rooms")
            needs = {"collect": ("found",), "seek": ("won", "wrong", "verb"), "watch": ("seen",),
                     "join": ("joined",), "gift": ("joined",), "boss": ("won", "hit", "miss")}
            for field in needs.get(event.get("action"), ()):
                if field not in event:
                    problems.append(f"event {eid}: needs {field}")
        return problems

    NPC_KINDS = ("talker", "resident")
    NPC_LIVE = ("time", "who", "gossip", "market", "event", "progress", "special", "ferry", "lanterns", "festival",
                "hunt", "pet", "arcade", "duels", "tournament", "contraband", "weddings", "tiers")
    NPC_LINES = ("greet", "greet_known", "greet_friend", "unknown")

    def _check_npcs(self):
        problems = []
        seen_names = {}

        def pair(where, value, need_list=True):
            """The English text: a line, or (need_list) a list of at least one line."""
            if not isinstance(value, dict) or not all(lang in value for lang in LANGS):
                problems.append(f"{where}: needs en")
                return
            for lang in LANGS:
                lines = value[lang] if need_list else [value[lang]]
                if not isinstance(lines, list) or not lines:
                    problems.append(f"{where}: needs a list of lines in {lang}")
                elif not all(isinstance(line, str) and line for line in lines):
                    problems.append(f"{where}: a line in {lang} is empty or isn't text")

        for nid, npc in (self.npcs.get("npcs") or {}).items():
            where = f"npc {nid}"
            if not isinstance(npc.get("name"), str) or not npc["name"]:
                problems.append(f"{where}: needs a name")
            if npc.get("kind") not in self.NPC_KINDS:
                problems.append(f"{where}: unknown kind {npc.get('kind')!r}")
            if not isinstance(npc.get("voice"), int) or not 1 <= npc["voice"] <= 10:
                problems.append(f"{where}: the voice is a number from 1 to 10")
            for field in ("role", "desc"):
                pair(f"{where} {field}", npc.get(field), need_list=False)
            for field in ("appear", "vanish"):
                if field in npc:
                    pair(f"{where} {field}", npc[field], need_list=False)
            names = npc.get("names") or {}
            if not all(names.get(lang) for lang in LANGS):
                problems.append(f"{where}: needs names in en")
            # Their own names are theirs alone ("shopkeeper" may be anyone's: it's found in a room).
            own = {_strip_articles(npc.get("name", "")), nid} | {
                _strip_articles(names[lang][0]) for lang in LANGS if names.get(lang)}
            for key in own:
                if key in seen_names and seen_names[key] != nid:
                    problems.append(f"{where}: the name {key!r} is {seen_names[key]}'s too")
                seen_names[key] = nid
            schedule = npc.get("schedule") or []
            hours = [entry[0] for entry in schedule if isinstance(entry, list) and len(entry) == 2]
            if not schedule or len(hours) != len(schedule) or hours != sorted(set(hours)) or \
                    not all(isinstance(h, int) and 0 <= h <= 23 for h in hours):
                problems.append(f"{where}: a schedule is [[hour, room]], by hour")
                continue
            rooms = [room for _h, room in schedule if room is not None]
            home = npc.get("home")
            if home not in self.locations:
                problems.append(f"{where}: unknown home {home!r}")
                continue
            for room in rooms:
                loc = self.locations.get(room)
                if loc is None or loc.get("private") or loc.get("hidden"):
                    problems.append(f"{where}: can't be in {room!r}")
                elif self.npc_route(home, room) is None:
                    problems.append(f"{where}: no walk from {home} to {room}")
            if npc.get("shop") and npc["shop"] not in self.shops:
                problems.append(f"{where}: unknown shop {npc['shop']!r}")
            for tid in npc.get("likes", []):
                if tid not in self.things:
                    problems.append(f"{where}: likes the unknown {tid!r}")
            for field in self.NPC_LINES:
                pair(f"{where} {field}", npc.get(field))
            for i, line in enumerate(npc.get("idle", [])):
                if line.get("kind") not in ("say", "emote"):
                    problems.append(f"{where} idle {i}: say or emote")
                if line.get("room") and line["room"] not in self.locations:
                    problems.append(f"{where} idle {i}: unknown room")
                pair(f"{where} idle {i}", {lang: line.get(lang) for lang in LANGS}, need_list=False)
            topics = npc.get("topics") or {}
            if not topics:
                problems.append(f"{where}: needs topics")
            for tid, topic in topics.items():
                tw = f"{where} topic {tid}"
                if not all(topic.get("names", {}).get(lang) for lang in LANGS):
                    problems.append(f"{tw}: needs names in en")
                if topic.get("favour"):
                    if not npc.get("favours"):
                        problems.append(f"{tw}: no favours to ask")
                    continue
                pair(f"{tw} say", topic.get("say"))
                if topic.get("live") is not None and topic["live"] not in self.NPC_LIVE:
                    problems.append(f"{tw}: unknown live value {topic['live']!r}")
                for case, lines in (topic.get("cases") or {}).items():
                    pair(f"{tw} case {case}", lines)
            for favour in npc.get("favours", []):
                fw = f"{where} favour {favour.get('id')}"
                if favour.get("repeat", "daily") not in ("daily", "once"):
                    problems.append(f"{fw}: repeat daily or once")
                for tid, n in (favour.get("needs") or {}).items():
                    if tid not in self.things or not isinstance(n, int) or n < 1:
                        problems.append(f"{fw}: needs an unknown {tid!r}")
                if len(favour.get("needs") or {}) != 1:
                    problems.append(f"{fw}: needs one kind of thing")
                thing = (favour.get("reward") or {}).get("thing")
                if thing and thing not in self.things:
                    problems.append(f"{fw}: rewards the unknown {thing!r}")
                for field in ("ask", "thanks"):
                    pair(f"{fw} {field}", favour.get(field), need_list=False)
        return problems

    def npc_route(self, start, goal):
        """The walk between two rooms for a resident: doors they have keys to,
        never into vacuum, the dark, the private rooms or a shuttle; or None."""
        def can_pass(_room, ex):
            loc = self.locations[ex["to"]]
            return not (loc.get("airless") or loc.get("dark") or loc.get("private") or loc.get("hidden")
                        or loc.get("secret"))
        path = self.route(start, goal, can_pass=can_pass)
        if path is None or any(how == "shuttle" for how, _room in path):
            return None
        return path

    # --- the worlds ----------------------------------------------------------------------

    def world_of(self, lid):
        """The world a room is in ("station", "moon"...), or None (a ship, the ferry)."""
        loc = self.locations.get(lid)
        if loc is None:
            return None
        return self.areas.get(loc.get("area"), {}).get("world")

    def find_world(self, text):
        return self._lookup(self._world_names, text)

    def distance(self, a, b):
        """How far apart two worlds are (at least 1)."""
        return max(1, abs(int(self.worlds[a]["pos"]) - int(self.worlds[b]["pos"])))

    def travel_rooms(self, wid):
        """The rooms of a world where the ferry stops, the Gate opens and ships dock."""
        world = self.worlds[wid]
        return {lid for lid in (world.get("port"), world.get("ferry"), world.get("gate")) if lid}

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
        # A plural: "crates", "boxes".
        for suffix in ("s", "es"):
            if key.endswith(suffix) and key[:-len(suffix)] in index:
                return index[key[:-len(suffix)]]
        if fuzzy and len(key) >= 4:
            close = difflib.get_close_matches(key, list(index), n=1, cutoff=0.8)
            if close:
                return index[close[0]]
        return None

    def find_location(self, text):
        """A location id for what a player typed ("cantina", "the Cantina"), or None."""
        return self._lookup(self._place_names, text)

    def find_good(self, text):
        return self._lookup(self._good_names, text)

    def find_item(self, text):
        return self._lookup(self._item_names, text)

    def find_thing(self, text, fuzzy=True):
        """Any thing's id (a good, a device, a seed...) for what was typed."""
        return self._lookup(self._thing_names, text, fuzzy)

    def find_object(self, location_id, text, fuzzy=True):
        """(object id, object) in a location for what was typed, or (None, None)."""
        loc = self.locations.get(location_id, {})
        index = self._index({oid: o["names"] for oid, o in loc.get("objects", {}).items()})
        found = self._lookup(index, text, fuzzy)
        return (found, loc["objects"][found]) if found else (None, None)

    def find_direction(self, text, _lang=None):
        """A direction ("n"...) for a word: "n", "north", "ne", "u" or "up"..."""
        key = norm(text)
        if not key:
            return None
        for lang in LANGS:
            if key in self._dir_words[lang]:
                return self._dir_words[lang][key]
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

    def reachable(self, start=None, travel=True):
        """Every room that can be reached from the start (doors and shuttles, and,
        with `travel`, the ferry, the Gate and ships between worlds)."""
        start = start or self.start
        seen = {start}
        queue = collections.deque([start])
        hubs = set()
        for wid in self.worlds:
            hubs |= self.travel_rooms(wid)
        while queue:
            here = queue.popleft()
            nexts = [ex["to"] for _d, ex in self.neighbours(here)]
            partner = self.shuttle_partner(here)
            if partner:
                nexts.append(partner)
            if travel and here in hubs:
                nexts.extend(hubs)
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
        """{"en": "3 sacks of coffee"}."""
        thing = table[thing_id]
        form = thing["one"] if n == 1 else thing["many"]
        return {lang: f"{n} {form[lang]}" for lang in LANGS}

    def thing_count(self, thing_id, n):
        return self.count_of(self.things, thing_id, n)

    def job_name(self, job):
        return self.jobs.get(job, {}).get("name", {lang: job for lang in LANGS})
