# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Walking the station by compass, like a MUD: n, s, e, w, ne, nw, se, sw, up
and down (in Indonesian utara, selatan, timur, barat, timur laut, barat laut,
tenggara, barat daya, naik, turun; "u" is utara in Indonesian and up in
English). There is no teleporting: "go to the cantina" walks there only when
the Cantina is next door, and otherwise tells you the way.

  look            the room, and its exits: "Exits: north, southwest, down."
  way to X        the steps from here: "south, south, west". Anyone can ask
                  the way to a few landmarks (the Dock, the Promenade, the
                  Cantina, Star Supply, the lifts), their own workplace, their
                  cabin and their beacon; a mapper knows every room you have
                  been to, and a holo mapper every public room
  map             this deck in words; more with a mapper
  where am I      the room, the deck and the exits
  compass         the way you last walked, and the deck
  scan            who is in the rooms around you (a scanner)
  locate Sari     where a player is, and the way (a communicator)

Some rooms are dark (the maintenance tunnels, the Crystal Cave): without a
worn headlamp you only feel the way you came in. Some doors are locked (a
keycard opens them). Outside the hull and on the Asteroid Surface there is
no air: an EVA suit only, with a few minutes of air, a warning before it
runs out, and a tow back to the airlock (a small fee) if it does. The Kancil
shuttle flies between the Dock and the Asteroid Belt. Your cabin is private;
invite someone and they may visit.
"""

import orbit_safety
from orbit_lang import pick

LONG_ROUTE = 8               # a route of this many steps (in three runs or more) also says how many


def route_groups(path):
    """[(how, n)]: a route's steps with runs of the same direction together
    (the Kancil is always a run of its own)."""
    groups = []
    for how, _room in path:
        if groups and groups[-1][0] == how and how != "shuttle":
            groups[-1][1] += 1
        else:
            groups.append([how, 1])
    return [(how, n) for how, n in groups]


class NavMixin:
    @staticmethod
    def commands():
        return {"move": NavMixin.cmd_move, "go": NavMixin.cmd_go, "way": NavMixin.cmd_way,
                "map": NavMixin.cmd_map, "where": NavMixin.cmd_where,
                "compass": NavMixin.cmd_compass, "scan": NavMixin.cmd_scan,
                "locate": NavMixin.cmd_locate, "friends": NavMixin.cmd_friends,
                "board": NavMixin.cmd_board, "invite": NavMixin.cmd_invite,
                "visit": NavMixin.cmd_visit}

    # --- what you can see and pass -------------------------------------------------------

    def has_light(self, char):
        return bool(self.effects(char)["light"])

    def in_the_dark(self, char):
        dark = bool(self._loc(char).get("dark")) or self.event_dark(char["location"])
        return dark and not self.has_light(char)

    def has_access(self, char, lock):
        return lock is None or lock in self.effects(char)["access"]

    def can_pass(self, char, room, ex, wearing_only=False):
        """Whether `char` could go through this exit (a door it can open;
        vacuum only with an EVA suit, worn or at least owned)."""
        if not self.has_access(char, ex.get("lock")):
            return False
        dest = self.world.locations[ex["to"]]
        if dest.get("airless") and not self.world.locations[room].get("airless"):
            fx = self.effects(char)
            return bool(fx["eva"]) if wearing_only else bool(fx["eva"] or fx["owns_eva"])
        return True

    def dir_word(self, lang, d):
        return pick(self.world.dir_name(d), lang)

    def exits_text(self, session):
        lang, char = session.lang, session.char
        here = char["location"]
        entries = []
        for d, ex in self.world.neighbours(here):
            word = self.dir_word(lang, d)
            if ex.get("lock") and not self.has_access(char, ex["lock"]):
                word = self.render(lang, "exit_locked", dir=word)
            elif self.world.locations[ex["to"]].get("airless") and not self._loc(char).get("airless"):
                word = self.render(lang, "exit_vacuum", dir=word)
            elif ex.get("oneway"):
                word = self.render(lang, "exit_oneway", dir=word)
            entries.append(word)
        if self.world.shuttle_partner(here):
            entries.append(self.render(lang, "exit_kancil"))
        if not entries:
            return ""
        return self.render(lang, "look_exits", exits=", ".join(entries))

    def dark_text(self, session):
        lang = session.lang
        back = session.char["stats"].get("back")
        if back and back in self.world.exits.get(session.char["location"], {}):
            return self.render(lang, "dark_room", dir=self.dir_word(lang, back))
        return self.render(lang, "dark_room_lost")

    def peek(self, session, d):
        """ "look north": the next room's name and who is there."""
        lang, char = session.lang, session.char
        if self.in_the_dark(char):
            self._error(session, "too_dark_to_see")
            return
        ex = self.world.exits.get(char["location"], {}).get(d)
        if ex is None:
            self._error(session, "no_exit_there", dir=self.dir_word(lang, d),
                        exits=self._exit_words(session), sound="bump")
            return
        dest = self.world.locations[ex["to"]]
        if dest.get("private"):
            self._info(session, "peek_private", dir=self.dir_word(lang, d), place=dest["ref"])
            return
        people = [o.name for o in self._in_room(ex["to"], visible=True)]
        key = "peek_people" if people else "peek_empty"
        self._info(session, key, dir=self.dir_word(lang, d), place=dest["ref"], people=people)

    def _exit_words(self, session):
        lang = session.lang
        if self.in_the_dark(session.char):
            back = session.char["stats"].get("back")
            return self.dir_word(lang, back) if back else "?"
        words = [self.dir_word(lang, d) for d, _ex in self.world.neighbours(session.char["location"])]
        return ", ".join(words) if words else self.render(lang, "no_exits")

    # --- walking ---------------------------------------------------------------------------

    def _remember_room(self, char, lid):
        if self.world.locations[lid].get("hidden"):
            return
        known = char["stats"].setdefault("map", [])
        if lid not in known:
            known.append(lid)

    def in_transit(self, session):
        loc = session.char["location"]
        if loc in ("shuttle", "kancil", "ferry", "ship"):
            self._error(session, {"shuttle": "in_flight", "kancil": "in_kancil", "ferry": "in_ferry",
                                  "ship": "in_ship"}[loc])
            return True
        return False

    def cmd_move(self, session, message):
        d = message.get("d")
        if d not in self.world.directions:
            d = self.world.find_direction(self._arg(message, "d", 20), session.lang)
        if d is None:
            self._error(session, "go_where")
            return
        self.walk(session, d)

    def walk(self, session, d):
        if self.in_transit(session):
            return
        char, lang = session.char, session.lang
        here = char["location"]
        ex = self.world.exits.get(here, {}).get(d)
        if ex is None:
            if self.in_the_dark(char):
                self._error(session, "bump_dark", dir=self.dir_word(lang, d),
                            back=self._exit_words(session), sound="bump")
            else:
                self._error(session, "no_exit", dir=self.dir_word(lang, d),
                            exits=self._exit_words(session), sound="bump")
            return
        if not self.has_access(char, ex.get("lock")):
            self._error(session, f"locked_{ex['lock']}", dir=self.dir_word(lang, d), sound="locked")
            return
        dest = ex["to"]
        dest_loc = self.world.locations[dest]
        host = None
        if dest_loc.get("crew_room"):
            crew, _role = self.crew_of(char)
            if crew is None:
                self._error(session, "crew_hangar_none", sound="locked")
                return
            host = f"crew{crew['id']}"                        # the crew's own room, all its members'
        here_airless = bool(self._loc(char).get("airless"))
        if dest_loc.get("airless") and not here_airless:
            if not self.effects(char)["eva"]:
                self._error(session, "need_eva", sound="locked")
                return
            self._start_air(char, here)
        self._move_to(session, dest, d, message=ex.get("msg"), via=ex.get("via"), host=host)
        if here_airless and not dest_loc.get("airless"):
            char["stats"].pop("eva", None)
            self._save(session)
            self._info(session, "air_refilled", sound="air")

    def _move_to(self, session, dest, d=None, message=None, sound=None, quiet=False, host=None,
                 via=None):
        """Put the player in `dest` (came `d`), telling both rooms; `host`:
        the cabin's owner when visiting one."""
        char, lang = session.char, session.lang
        old_room = self.room_of(char)
        old_loc = self._loc(char)
        came_from = old_loc
        char["location"] = dest
        if (dest in ("cabin", "ship") or self.world.locations[dest].get("crew_room")) and host:
            char["stats"]["visit"] = host
        else:
            char["stats"].pop("visit", None)
        new_room = self.room_of(char)
        new_loc = self.world.locations[dest]
        back = self.world.directions[d]["back"] if d in self.world.directions else None
        char["stats"]["back"] = back
        if d in self.world.directions:
            char["stats"]["heading"] = d
        self._remember_room(char, dest)
        self._save(session)
        if not quiet and not session.invisible:
            self._announce_leave(session, old_room, old_loc, new_loc, d, host)
            self._announce_arrive(session, new_room, came_from, new_loc, back)
        first = dest not in session.visited
        session.visited.add(dest)
        if message:
            line = pick(message, lang).format(place=pick(new_loc["ref"], lang))
        elif d in ("u", "d"):
            line = self.render(lang, "moved_up" if d == "u" else "moved_down", place=new_loc["ref"])
        elif d in self.world.directions:
            line = self.render(lang, "moved_dir", dir=self.dir_word(lang, d), place=new_loc["ref"])
        else:
            line = self.render(lang, "moved", place=new_loc["ref"])
        extra = dict(self._where(session))
        if d in self.world.directions:
            extra["dir"] = d
        if via and via != "walk":
            extra["via"] = via
        if sound:
            extra["sound"] = sound
        self._send(session, "moved", text=f"{line} {self.look_text(session, full=first)}", extra=extra)
        self.pet_follows(session)
        self.gig_arrived(session)
        self.arcade_left(session)
        self.npc_notice(session)

    def _announce_leave(self, session, old_room, old_loc, new_loc, d, host):
        name = session.name
        extra = {"actor": name}
        if old_loc.get("private"):
            self._to_room(old_room, "leave", "leave_cabin", exclude=(session,), extra=extra, actor=name)
            return
        if new_loc.get("private") and new_loc is self.world.locations.get("cabin"):
            if host and host != session.key:
                host_char = self._char_by_key(host)
                self._to_room(old_room, "leave", "leave_to_visit", exclude=(session,), extra=extra,
                              actor=name, name=host_char["name"] if host_char else host)
            else:
                self._to_room(old_room, "leave", "leave_to_cabin", exclude=(session,), extra=extra,
                              actor=name)
            return
        if new_loc.get("private") or d not in self.world.directions:
            self._to_room(old_room, "leave", "leave_to", exclude=(session,), extra=extra, actor=name,
                          place=new_loc["ref"])
            return
        extra = dict(extra, dir=d)
        for other in self._in_room(old_room, exclude=(session,)):
            key = {"u": "leave_up", "d": "leave_down"}.get(d, "leave_dir")
            self._send(other, "leave", key, extra=extra, actor=name,
                       dir=self.dir_word(other.lang, d), place=new_loc["ref"])

    def _announce_arrive(self, session, new_room, came_from, new_loc, back):
        name = session.name
        extra = {"actor": name}
        if new_loc.get("private"):
            self._to_room(new_room, "arrive", "arrive_visit", exclude=(session,), extra=extra, actor=name)
            return
        if came_from.get("private"):
            self._to_room(new_room, "arrive", "arrive_from_cabin", exclude=(session,), extra=extra,
                          actor=name)
            return
        if back is None:
            self._to_room(new_room, "arrive", "arrive_from", exclude=(session,), extra=extra,
                          actor=name, place=came_from["ref"])
            return
        extra = dict(extra, dir=back)
        for other in self._in_room(new_room, exclude=(session,)):
            # They came from `back` as seen from this room: up from below is "u".
            key = {"u": "arrive_down", "d": "arrive_up"}.get(back, "arrive_dir")
            self._send(other, "arrive", key, extra=extra, actor=name,
                       dir=self.dir_word(other.lang, back), place=came_from["ref"])

    def cmd_go(self, session, message):
        text = self._arg(message)
        if not text:
            self._error(session, "go_where")
            return
        d = self.world.find_direction(text, session.lang)
        if d:
            self.walk(session, d)
            return
        if self.in_transit(session):
            return
        if self.is_admin(session):
            self.admin_goto(session, text)
            return
        if self.go_travel(session, text):
            return
        if self.in_transit(session):
            return
        char = session.char
        dest = self.find_place(session, text)
        if dest is None:
            if self._find_session(text) is not None:
                self._error(session, "go_player", name=self._find_session(text).name)
            else:
                self._error(session, "no_place", what=text)
            return
        if dest == char["location"] and not char["stats"].get("visit"):
            self._info(session, "already_here", place=self._loc(dest)["ref"])
            return
        for d, ex in self.world.neighbours(char["location"]):
            if ex["to"] == dest and self.can_pass(char, char["location"], ex, wearing_only=True):
                self.walk(session, d)
                return
        self.way_to(session, dest, walking_note=True)

    def find_place(self, session, text):
        key = orbit_safety.name_key(text)
        if key in ("suar", "beacon", "my beacon", "suarku", "penanda"):
            return session.char["stats"].get("beacon") or "?beacon"
        return self.world.find_location(text)

    # --- the way, the map ------------------------------------------------------------------

    def guide_rooms(self, char):
        """Rooms `char` may ask the way to (see the module notes)."""
        rooms = {lid for lid, loc in self.world.locations.items() if loc.get("landmark")}
        rooms.add("cabin")
        work = self.world.jobs.get(char["job"], {}).get("workplace")
        if work:
            rooms.add(work)
        if char["stats"].get("beacon") in self.world.locations:
            rooms.add(char["stats"]["beacon"])
        level = self.effects(char)["mapper"]
        if level >= 1:
            rooms.update(char["stats"].get("map") or [])
        if level >= 2:
            rooms.update(lid for lid, loc in self.world.locations.items()
                         if not loc.get("secret") and not loc.get("hidden"))
        return rooms

    def route_for(self, char, dest, start=None):
        return self.world.route(start or char["location"], dest,
                                can_pass=lambda room, ex: self.can_pass(char, room, ex))

    def group_text(self, lang, how, n):
        """One run of a route: "east", "2 east", "up 3 levels", "ride the Kancil"."""
        if how == "shuttle":
            return self.render(lang, "step_kancil")
        word = self.dir_word(lang, how)
        if n == 1:
            return word
        key = {"u": "step_up_many", "d": "step_down_many"}.get(how, "step_many")
        return self.render(lang, key, n=n, dir=word)

    def join_steps(self, lang, parts):
        """ "a", "a, then b" / "a lalu b", "a, b, then c" / "a, b, lalu c"."""
        if len(parts) <= 1:
            return "".join(parts)
        if len(parts) == 2:
            return self.render(lang, "route_two", a=parts[0], b=parts[1])
        return self.render(lang, "route_many", rest=", ".join(parts[:-1]), last=parts[-1])

    def steps_text(self, lang, path):
        """A route, compact: "2 east, south, up, north, then 2 west" (and how many steps
        when it's long)."""
        groups = route_groups(path)
        text = self.join_steps(lang, [self.group_text(lang, how, n) for how, n in groups])
        if len(path) >= LONG_ROUTE and len(groups) > 2:
            text = self.render(lang, "route_long", steps=text, n=len(path))
        return text

    def cmd_way(self, session, message):
        text = self._arg(message)
        if not text:
            self._error(session, "way_where")
            return
        dest = self.find_place(session, text)
        if dest == "?beacon":
            self._error(session, "no_beacon")
            return
        if dest is None:
            wid = self.world.find_world(text)
            if wid and wid != self.world_here(session.char):
                self.travel_options(session, wid)
                return
            if self._find_session(text) is not None:
                self._error(session, "way_player", name=self._find_session(text).name)
            else:
                self._error(session, "no_place", what=text)
            return
        wid = self.world.world_of(dest)
        if wid and wid != self.world_here(session.char) and \
                self.world.route(session.char["location"], dest) is None:
            self.travel_options(session, wid, dest)
            return
        self.way_to(session, dest)

    def way_to(self, session, dest, walking_note=False):
        char, lang = session.char, session.lang
        if self.in_transit(session):
            return
        place = self.world.locations[dest]["ref"]
        if dest not in self.guide_rooms(char) and not self.is_admin(session):
            self._error(session, "way_unknown", place=place)
            return
        if dest == char["location"] and not char["stats"].get("visit"):
            self._info(session, "already_here", place=place)
            return
        start = char["location"]
        path = self.route_for(char, dest)
        if path is None:
            self._error(session, "no_way_access", place=place)
            return
        key = "way_walk" if walking_note else "way"
        self._info(session, key, place=place, steps=self.steps_text(lang, path), n=len(path))

    def cmd_map(self, session, message):
        char, lang = session.char, session.lang
        if self.in_transit(session):
            return
        here = char["location"]
        level = self.effects(char)["mapper"]
        if self.in_the_dark(char) and not level:
            self._error(session, "too_dark_to_see")
            return
        area = self.world.area_of(here)
        parts = [self.render(lang, "map_here", place=self.cabin_in(session) or self._loc(char)["in"],
                             deck=area.get("in", ""))]
        near = []
        for d, ex in self.world.neighbours(here):
            near.append(self.render(lang, "map_near", dir=self.dir_word(lang, d),
                                    place=self.world.locations[ex["to"]]["ref"]))
        if near:
            parts.append(self.render(lang, "map_around", places="; ".join(near)))
        if level >= 1:
            area_id = self._loc(char).get("area")
            known = set(char["stats"].get("map") or [])
            if level >= 2:
                known = {lid for lid, loc in self.world.locations.items()
                         if not loc.get("secret") and not loc.get("hidden")}
            neighbours = {ex["to"] for _d, ex in self.world.neighbours(here)}
            others = []
            for lid in sorted(known):
                loc = self.world.locations[lid]
                if lid == here or lid in neighbours or loc.get("area") != area_id or loc.get("hidden"):
                    continue
                heading = self.world.heading(here, lid)
                if heading:
                    others.append(self.render(lang, "map_far", place=loc["ref"],
                                              dir=self.dir_word(lang, heading)))
                else:
                    others.append(pick(loc["ref"], lang))
            if others:
                parts.append(self.render(lang, "map_known", places="; ".join(others)))
            elif level == 1:
                parts.append(self.render(lang, "map_known_none"))
        if level >= 2:
            decks = []
            for aid, info in self.world.areas.items():
                if aid in ("transit", area_id) or not info.get("about"):
                    continue
                decks.append(self.render(lang, "map_deck", deck=info["name"], about=info["about"]))
            parts.append(self.render(lang, "map_decks", decks="; ".join(decks)))
        elif level == 0:
            parts.append(self.render(lang, "map_no_mapper"))
        self._info(session, text=" ".join(parts), sound="gadget" if level else None)

    def cmd_where(self, session, message):
        char, lang = session.char, session.lang
        if char["location"] in ("shuttle", "kancil"):
            self._info(session, text=self.look_text(session, full=False))
            return
        area = self.world.area_of(char["location"])
        name = self.cabin_name(session) or self._loc(char)["name"]
        exits = self.dark_text(session) if self.in_the_dark(char) else self.exits_text(session)
        self._info(session, "where", place=name, deck=area.get("in", ""), exits=exits)

    def cmd_compass(self, session, message):
        char, lang = session.char, session.lang
        if not self.effects(char)["compass"]:
            self._error(session, "no_compass")
            return
        area = self.world.area_of(char["location"])
        heading = char["stats"].get("heading")
        if heading in self.world.directions:
            self._info(session, "compass", dir=self.dir_word(lang, heading), deck=area.get("in", ""),
                       sound="gadget")
        else:
            self._info(session, "compass_still", deck=area.get("in", ""), sound="gadget")

    def cmd_scan(self, session, message):
        char, lang = session.char, session.lang
        if not self.effects(char)["scanner"]:
            self._error(session, "no_scanner")
            return
        if self.in_transit(session) or not self._slow(session):
            return
        found = []
        for d, ex in self.world.neighbours(char["location"]):
            if self.world.locations[ex["to"]].get("private"):
                continue
            people = sorted(o.name for o in self._in_room(ex["to"], visible=True))
            if people:
                found.append(self.render(lang, "scan_room", dir=self.dir_word(lang, d),
                                         place=self.world.locations[ex["to"]]["ref"], people=people))
        if found:
            self._info(session, "scan", rooms="; ".join(found), sound="scan")
        else:
            self._info(session, "scan_nobody", sound="scan")

    def cmd_locate(self, session, message):
        char, lang = session.char, session.lang
        if not self.effects(char)["comm"] and not self.is_admin(session):
            self._error(session, "no_comm")
            return
        name = self._arg(message, "to", 40)
        target = self._find_session(name) if name else None
        if target is None or (target.invisible and not self.is_admin(session)):
            self._error(session, "no_player", name=name or "?")
            return
        if target is session:
            self.cmd_where(session, {})
            return
        where = target.char["location"]
        if where in ("shuttle", "kancil"):
            self._info(session, "locate_flying", name=target.name, sound="gadget")
            return
        area = self.world.area_of(where)
        dest = "cabins_hall" if where == "cabin" else where
        place = self.world.locations[where]["in"] if where != "cabin" else self.render(lang, "their_cabin")
        path = self.route_for(char, dest)
        if path is None:
            self._info(session, "locate_noway", name=target.name, place=place, deck=area.get("in", ""),
                       sound="gadget")
        elif not path:
            self._info(session, "locate_here", name=target.name, place=place, sound="gadget")
        else:
            self._info(session, "locate", name=target.name, place=place, deck=area.get("in", ""),
                       steps=self.steps_text(lang, path), sound="gadget")

    def cmd_friends(self, session, message):
        char, lang = session.char, session.lang
        friends = char["stats"].setdefault("friends", [])
        op = self._arg(message, "op", 10)
        name = self._arg(message, "to", 40)
        if op in ("add", "remove"):
            key = orbit_safety.name_key(name)
            other = self._char_by_key(key) if key else None
            if other is None:
                self._error(session, "no_character", name=name or "?")
                return
            if op == "add":
                if key == session.key:
                    self._error(session, "friend_self")
                    return
                if key not in friends:
                    if len(friends) >= 50:
                        self._error(session, "friends_full")
                        return
                    friends.append(key)
                self._save(session)
                self._info(session, "friend_added", name=other["name"])
            else:
                if key in friends:
                    friends.remove(key)
                self._save(session)
                self._info(session, "friend_removed", name=other["name"])
            return
        if not friends:
            self._info(session, "friends_none")
            return
        online, offline = [], []
        for key in friends:
            other = self.sessions.get(key)
            if other is not None and other.conn is not None and not other.invisible:
                online.append(other.name)
            else:
                stored = self.store.by_name(key)
                if stored is not None:
                    offline.append(stored["name"])
        note = "" if self.effects(char)["comm"] else self.render(lang, "friends_no_comm")
        self._info(session, "friends", online=online or [self.render(lang, "nobody")],
                   offline=offline or [self.render(lang, "nobody")], note=note)

    def tell_friends(self, session):
        """A player came in: those who count them as a friend, and wear a communicator, hear it."""
        if session.invisible:
            return
        for other in list(self.sessions.values()):
            if other is session or other.conn is None:
                continue
            if session.key in (other.char["stats"].get("friends") or []) and \
                    self.effects(other.char)["comm"]:
                self._send(other, "arrive", "friend_online", extra={"actor": session.name, "sound": "gadget"},
                           name=session.name)

    # --- the Kancil ---------------------------------------------------------------------

    def ride_seconds(self, char):
        kancil = self.econ["kancil"]
        seconds = float(kancil["seconds"]) * self.effects(char)["shuttle"]
        if char["job"] == "pilot":
            seconds *= float(kancil["pilot_factor"])
        return max(float(kancil["min_seconds"]), seconds)

    def cmd_board(self, session, message):
        if self.in_transit(session):
            return
        char, lang = session.char, session.lang
        here = char["location"]
        dest = self.world.shuttle_partner(here)
        if dest is None:
            self._error(session, "board_where")
            return
        fare = 0 if (char["job"] == "pilot" or here != "dock") else int(self.econ["kancil"]["fare"])
        if char["credits"] < fare:
            self._error(session, "board_poor", fare=fare, credits=char["credits"])
            return
        if fare:
            self.spend(char, fare, "fares")
        seconds = self.ride_seconds(char)
        char["stats"]["ride"] = {"to": dest, "from": here, "arrive": self.now() + seconds}
        old_room = self.room_of(char)
        char["location"] = "kancil"
        self._save(session)
        if not session.invisible:
            self._to_room(old_room, "leave", "kancil_depart_other", exclude=(session,),
                          extra={"actor": session.name}, actor=session.name)
        key = "kancil_depart_fare" if fare else "kancil_depart"
        self._send(session, "flight", key, place=self.world.locations[dest]["ref"], fare=fare,
                   credits=char["credits"], time=self._duration(lang, seconds),
                   extra=dict(self._where(session), sound="launch"))

    def tick_ride(self, session, now):
        ride = session.char["stats"].get("ride")
        if ride and now >= float(ride.get("arrive", 0)):
            self.settle_ride(session)

    def settle_ride(self, session, on_join=False):
        char = session.char
        ride = char["stats"].get("ride")
        if not ride:
            if char["location"] == "kancil":
                char["location"] = "dock"
            return ""
        if self.now() < float(ride.get("arrive", 0)):
            return ""
        dest = ride.get("to") if ride.get("to") in self.world.locations else "dock"
        char["stats"].pop("ride", None)
        if on_join:
            char["location"] = dest
            self._remember_room(char, dest)
            return self.render(session.lang, "kancil_landed_away", place=self.world.locations[dest]["ref"])
        char["location"] = "kancil"
        self._move_to(session, dest, message={lang: self.render(lang, "kancil_landed") for lang in ("en", "id")},
                      sound="landing", quiet=True)
        if not session.invisible:
            self._to_room(self.room_of(char), "arrive", "kancil_arrive_other", exclude=(session,),
                          extra={"actor": session.name}, actor=session.name)
        return ""

    # --- air outside ------------------------------------------------------------------------

    def _rescue_room(self, from_room):
        """Where the tow drone brings you: the airlock you went out by, or the
        one of the area you're in (world.json: an area's "rescue")."""
        loc = self.world.locations.get(from_room, {})
        if loc.get("rescue") and not loc.get("airless"):
            return from_room
        rescue = self.world.areas.get(loc.get("area"), {}).get("rescue")
        return rescue if rescue in self.world.locations else self.world.start

    def _start_air(self, char, from_room):
        air = self.effects(char)["air"]
        char["stats"]["eva"] = {"until": self.now() + air, "rescue": self._rescue_room(from_room),
                                "warned": 0}

    def air_left(self, char):
        eva = char["stats"].get("eva")
        if not eva:
            return None
        return max(0.0, float(eva.get("until", 0)) - self.now())

    def air_text(self, session):
        left = self.air_left(session.char)
        if left is None:
            return ""
        return self.render(session.lang, "air_left", time=self._duration(session.lang, left))

    def tick_air(self, session, now):
        char = session.char
        eva = char["stats"].get("eva")
        if not eva:
            return
        left = float(eva.get("until", 0)) - now
        if left <= 0:
            self._rescue(session)
            return
        warnings = sorted(self.econ["eva"]["warn"], reverse=True)
        warned = int(eva.get("warned", 0))
        while warned < len(warnings) and left <= warnings[warned]:
            warned += 1
            eva["warned"] = warned
            self._send(session, "system", "air_warning", time=self._duration(session.lang, left),
                       extra={"sound": "air"})

    def _rescue(self, session, on_join=False):
        char = session.char
        eva = char["stats"].pop("eva", {}) or {}
        dest = eva.get("rescue") if eva.get("rescue") in self.world.locations else self.world.start
        fee = min(char["credits"], int(self.econ["eva"]["rescue_fee"]))
        if fee:
            self.spend(char, fee, "rescues")
        if on_join:
            char["location"] = dest
            self._save(char)
            return self.render(session.lang, "air_rescued_away", place=self.world.locations[dest]["ref"],
                               fee=fee)
        self._move_to(session, dest, message=None, sound="rescue")
        self._send(session, "failed", "air_rescued", place=self.world.locations[dest]["ref"], fee=fee,
                   credits=char["credits"], extra={"sound": "rescue"})
        return ""

    def settle_air(self, session, on_join=False):
        char = session.char
        if not char["stats"].get("eva"):
            if self._loc(char).get("airless"):
                char["stats"]["eva"] = {"until": self.now(), "rescue": self._rescue_room(char["location"]),
                                        "warned": 9}
            else:
                return ""
        if self.air_left(char) <= 0:
            return self._rescue(session, on_join=on_join)
        return ""

    # --- cabins and guests ---------------------------------------------------------------------

    def cabin_host(self, session):
        """The name key of the cabin you're in (yours, or the one you visit), or None."""
        if session.char["location"] != "cabin":
            return None
        return session.char["stats"].get("visit") or session.key

    def cabin_in(self, session):
        host = self.cabin_host(session)
        if host is None or host == session.key:
            return None
        char = self._char_by_key(host)
        name = char["name"] if char else host
        return {lang: self.render(lang, "cabin_in", name=name) for lang in ("en", "id")}

    def cabin_name(self, session):
        host = self.cabin_host(session)
        if host is None or host == session.key:
            return None
        char = self._char_by_key(host)
        name = char["name"] if char else host
        return {lang: self.render(lang, "cabin_of", name=name) for lang in ("en", "id")}

    def cmd_invite(self, session, message):
        op = self._arg(message, "op", 10) or "add"
        name = self._arg(message, "to", 40)
        target = self._find_session(name) if name else None
        if op == "remove":
            key = orbit_safety.name_key(name)
            session.invites.pop(key, None)
            guest = self.sessions.get(key)
            if guest is not None and guest.char["location"] == "cabin" and \
                    guest.char["stats"].get("visit") == session.key:
                self._send(guest, "system", "visit_ended", name=session.name)
                self._move_to(guest, "cabins_hall", "n")
            elif guest is not None and guest.char["location"] == "ship" and \
                    guest.char["stats"].get("visit") == session.key:
                ship = self.ship_of(session.char)
                if ship is not None and ship.get("dock"):
                    self._send(guest, "system", "ship_visit_ended", name=session.name)
                    self._move_to(guest, ship["dock"])
            self._info(session, "uninvited", name=guest.name if guest else name or "?")
            return
        if target is None or target.conn is None or target.invisible:
            self._error(session, "no_player", name=name or "?")
            return
        if target is session:
            self._error(session, "invite_self")
            return
        if not self._slow(session):
            return
        session.invites[target.key] = self.now() + 600
        ship = self.ship_of(session.char) if session.char["location"] == "ship" and \
            not session.char["stats"].get("visit") else None
        if ship is not None:
            where = self.world.locations[ship["dock"]]["in"] if ship.get("dock") else \
                self.world.worlds[ship["flight"]["to"]]["in"]
            self._send(target, "offer", "invited_you_ship", actor=session.name, where=where,
                       extra={"actor": session.name, "ask": True, "sound": "offer"})
            self._info(session, "invited_ship", name=target.name)
            return
        self._send(target, "offer", "invited_you", extra={"actor": session.name, "ask": True, "sound": "offer"},
                   actor=session.name)
        self._info(session, "invited", name=target.name)

    def tick_invites(self, session, now):
        for key, until in list(session.invites.items()):
            if now > until:
                session.invites.pop(key, None)

    def cmd_visit(self, session, message):
        char = session.char
        name = self._arg(message, "to", 40)
        host = self._find_session(name) if name else None
        if host is None:
            self._error(session, "no_player", name=name or "?")
            return
        if host is session:
            self.cmd_go(session, {"a": "cabin"})
            return
        until = host.invites.get(session.key)
        if (not until or until < self.now()) and not self.party_of(host.key):
            self._error(session, "not_invited", name=host.name)
            return
        if char["location"] != "cabins_hall":
            self._error(session, "visit_where")
            return
        d = next((d for d, ex in self.world.neighbours("cabins_hall") if ex["to"] == "cabin"), None)
        self._move_to(session, "cabin", d, host=host.key)
