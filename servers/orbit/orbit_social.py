# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Being in a room with others, the way the Nova Realm did it (since 1.6):

  sit, sit on the sofa, stand, stand up, lie down, lie on the lawn, sleep,
  wake, wake Maya
        postures. Where the room has furniture (bar stools, benches, a bunk,
        the lawn: an object's "seat" in world.json, or a sofa or hammock in
        your cabin) you sit or lie on it; otherwise on the floor or the
        ground. The room sees it happen ("Maya sits down on a bar stool.")
        and whoever looks sees it ("Maya is sitting on a bar stool.").
        Walking stands you up first ("You stand up and walk north...").
        Asleep, a command that does something wakes you first (looking,
        who, help and the like don't); "wake" wakes you and gets you up;
        others can wake you ("wake Maya"). "stand" is blackjack's only
        while you're playing a hand.
  follow Maya, lead Maya; stop following, stop leading (also unfollow, disband)
        after the other says yes (accept or decline, like an offer), the one
        who follows walks where the leader walks, a step behind ("You follow
        Sam north to the Promenade."). Walking off on your own, a door you
        can't pass, a private room or the leader leaving ends it.
  emote waves hello, :waves hello
        a gesture in your own words, after your name ("Maya waves hello.")
  kiss, wink, giggle, poke Maya, high five Maya...
        more gestures (world.json "emotes"), with and without someone
  roll, roll a die, roll 2d6, roll d20
        dice for the room to see, from the server's own generator (fair),
        and written to the server's log
  time  the station's time (UTC), and the local time on another world
  afk, afk making tea (also brb)
        away from the keyboard: others see it when they look and in who, and
        a whisper to you says so; any command brings you back
  exits, ex
        a line for each way out, with where it leads (in compass order:
        north, northeast, east... up, down), locked doors, vacuum, one-way
        exits, the dark
  peer north
        a glimpse of the next room: its name, the start of its description,
        who is there and what lies about

The rooms have lives of their own: now and then a line (world.json "ambient":
the jukebox changes its song, a cargo drone hums past), rare, never while
players there are talking, paced like the residents' idle lines and sharing
their gap, so a room never chatters.

Postures, following and being away live in the session (memory): logging
out ends them, a reconnect within the link-dead minute keeps them, a restart
forgets them. Nothing here is saved in the database.
"""

import datetime
import logging
import re

import orbit_safety
import orbit_world
from orbit_lang import pick

logger = logging.getLogger("orbit.game")

POSES = ("sit", "lie", "sleep")
# What doesn't wake a sleeper: looking and asking, never doing.
PASSIVE_COMMANDS = {"look", "examine", "who", "inventory", "help", "status", "away", "time", "exits", "where",
                    "map", "compass", "friends", "residents", "events", "profile", "rank", "achievements",
                    "leaderboard", "crews", "hunt_board", "high_scores", "wake", "sleep", "sit", "lie", "stand",
                    "stand_up", "afk", "again", "bye", "peer"}
# Where you sit or lie when a room has no furniture for it: by the room's floor.
FLOOR_AT = {"grass": "at_grass", "sand": "at_sand", "snow": "at_snow", "dust": "at_dust", "rock": "at_ground",
            "suit": "at_ground"}
SEAT_WORDS = {"down", "on", "in", "at", "onto", "upon", "by", "back", "up", "into"}
FLOOR_WORDS = {"floor", "ground", "the floor", "the ground", "grass", "the grass", "sand", "snow", "dust"}
FOLLOW_SECONDS = 60           # an ask to follow or lead waits this long for an answer
MAX_DICE, MAX_SIDES = 10, 100
DICE_RE = re.compile(r"^(\d*)d(\d+)$")
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
DAY_PARTS = ((5, "part_night"), (8, "part_early"), (12, "part_morning"), (17, "part_afternoon"),
             (21, "part_evening"), (24, "part_night"))
UNFOLLOW = {"stop following", "unfollow", "stop", "none", "nobody", "off"}


class SocialMixin:
    @staticmethod
    def commands():
        return {"sit": SocialMixin.cmd_sit, "lie": SocialMixin.cmd_lie, "sleep": SocialMixin.cmd_sleep,
                "wake": SocialMixin.cmd_wake, "stand_up": SocialMixin.cmd_stand_up, "stand": SocialMixin.cmd_stand,
                "follow": SocialMixin.cmd_follow, "lead": SocialMixin.cmd_lead,
                "pose": SocialMixin.cmd_pose, "roll": SocialMixin.cmd_roll, "time": SocialMixin.cmd_time,
                "afk": SocialMixin.cmd_afk, "exits": SocialMixin.cmd_exits, "peer": SocialMixin.cmd_peer}

    def init_social(self):
        self.follow_asks = {}           # the asked player's key -> {"kind": follow or lead, "from", "at", ...}
        self.ambient_next = {}          # room -> when it may say a line of its own next
        self.ambient_last = {}          # room -> the line it said last (never twice in a row)

    # --- postures ------------------------------------------------------------------------------

    def pose_of(self, session):
        """How `session` rests here ({"kind": sit, lie or sleep, "on": a seat's id or None, "room"}),
        or None: standing. A pose belongs to the room it was taken in."""
        pose = session.pose
        if pose and pose.get("room") != self.room_of(session.char):
            session.pose = pose = None
        return pose

    def seats_here(self, session):
        """{id: (names, seat)}: what can be sat or lain on here (world.json objects with a "seat",
        and in a cabin, its owner's furniture that has one)."""
        seats = {}
        for oid, obj in (self._loc(session.char).get("objects") or {}).items():
            if obj.get("seat"):
                seats[oid] = (obj["names"]["en"], obj["seat"])
        host = self.cabin_host(session)
        owner = self._char_by_key(host) if host else None
        if owner is not None:
            for tid in sorted(owner["inventory"]):
                thing = self.world.things.get(tid) or {}
                seat = (thing.get("effects") or {}).get("seat")
                if seat and owner["inventory"][tid] > 0:
                    seats[tid] = ((thing.get("names") or {}).get("en") or [pick(thing["one"])], seat)
        return seats

    def _seat_named(self, seats, text):
        index = self.world._index({sid: {"en": names} for sid, (names, _seat) in seats.items()})
        return self.world._lookup(index, text)

    def _floor_at(self, session, kind):
        """ "on the floor", "on the grass", or the room's own words ("in a passenger seat")."""
        loc = self._loc(session.char)
        own = loc.get("lie_at" if kind != "sit" else "sit_at") or loc.get("sit_at")
        if own:
            return pick(own)
        return self.render(session.lang, FLOOR_AT.get(loc.get("floor", "metal"), "at_floor"))

    def _seat_at(self, seat, kind):
        if kind != "sit" and seat.get("lie_at"):
            return pick(seat["lie_at"])
        return pick(seat.get("at") or {"en": ""})

    def pose_at(self, session, pose):
        """Where a pose is: "on a bar stool", "on the floor"."""
        seats = self.seats_here(session)
        if pose.get("on") in seats:
            return self._seat_at(seats[pose["on"]][1], pose["kind"])
        return self._floor_at(session, pose["kind"])

    def _on_seat(self, room, sid, but=None):
        return [s for s in self._in_room(room) if s is not but and s.pose and s.pose.get("room") == room
                and s.pose.get("on") == sid]

    def pose_line(self, lang, other):
        """ "Maya is sitting on a bar stool." for a look, or ""."""
        pose = self.pose_of(other)
        lines = []
        if pose:
            key = {"sit": "pose_sitting", "lie": "pose_lying", "sleep": "pose_asleep"}[pose["kind"]]
            lines.append(self.render(lang, key, name=other.name, at=self.pose_at(other, pose)))
        if other.afk is not None:
            lines.append(self.render(lang, "pose_afk_note" if other.afk else "pose_afk", name=other.name,
                                     note=other.afk))
        return "\n".join(lines)

    def cmd_sit(self, session, message):
        self.take_pose(session, "sit", self._arg(message, "a", 80))

    def cmd_lie(self, session, message):
        self.take_pose(session, "lie", self._arg(message, "a", 80))

    def cmd_sleep(self, session, message):
        self.take_pose(session, "sleep", self._arg(message, "a", 80))

    @staticmethod
    def _seat_allows(seat, want):
        return bool(seat.get("lie")) if want == "lie" else seat.get("sit", True) is not False

    def _free_seat(self, session, seats, want, room):
        """The first furniture here that takes this pose and has room, or None (the floor)."""
        for sid, (_names, seat) in seats.items():
            if self._seat_allows(seat, want) and len(self._on_seat(room, sid, but=session)) < int(seat.get("n", 1)):
                return sid
        return None

    def take_pose(self, session, kind, text=""):
        """Sit, lie down or fall asleep: on the furniture named, or the best free place here."""
        char = session.char
        words = [w for w in str(text or "").split() if w.lower().strip(".,!") not in SEAT_WORDS]
        text = " ".join(words)
        pose = self.pose_of(session)
        seats = self.seats_here(session)
        room = self.room_of(char)
        want = "lie" if kind == "sleep" else kind
        if text and orbit_world.strip_articles(text) in FLOOR_WORDS:
            sid = None
        elif text:
            sid = self._seat_named(seats, text)
            if sid is None:
                _oid, obj = self.world.find_object(char["location"], text)
                person = self._find_near(session, text)
                if obj is not None:
                    self._error(session, f"{want}_cant", thing=f"the {obj['names']['en'][0]}")
                elif person is not None:
                    self._error(session, f"{want}_on_person", name=person.name)
                else:
                    self._error(session, f"{want}_none", what=bare(text))
                return
        elif pose and pose.get("on") in seats and self._seat_allows(seats[pose["on"]][1], want):
            sid = pose["on"]                                     # lie down where you sit, sleep where you lie
        else:
            sid = self._free_seat(session, seats, want, room)
        if sid is not None:
            seat = seats[sid][1]
            if not self._seat_allows(seat, want):
                self._error(session, f"{want}_cant", thing=self._seat_at(seat, "sit").split(" ", 1)[-1])
                return
            taken = not (pose and pose.get("on") == sid)
            if taken and len(self._on_seat(room, sid, but=session)) >= int(seat.get("n", 1)):
                if seat.get("full"):
                    self._send(session, "error", text=pick(seat["full"]))
                else:
                    self._error(session, "seat_full", at=self._seat_at(seat, want))
                return
        at = self._seat_at(seats[sid][1], kind) if sid is not None else self._floor_at(session, kind)
        if pose and pose["kind"] == kind and pose.get("on") == sid:
            self._error(session, f"already_{kind}", at=at)
            return
        was_sleeping = pose is not None and pose["kind"] == "sleep"
        session.pose = {"kind": kind, "on": sid, "room": room}
        key = kind
        if kind == "sleep" and not (pose and pose["kind"] == "lie" and pose.get("on") == sid):
            key = "sleep_down"                                   # lie down first, then sleep
        elif kind != "sleep" and was_sleeping:
            key = f"{kind}_woke"
        self._send(session, "info", f"{key}_you", at=at, extra={"sound": "equip"})
        if not session.invisible:
            self._to_room(room, "emote", f"{key}_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "equip"}, actor=session.name, at=at)
        if kind == "sleep":
            self.stop_following(session, quiet=False)

    def stand_up(self, session, quiet=False):
        """Get up (from a seat, the floor, or sleep). Returns the pose you were in, or None."""
        pose = self.pose_of(session)
        if pose is None:
            return None
        session.pose = None
        if quiet:
            return pose
        key = "stand_woke" if pose["kind"] == "sleep" else "stand"
        self._send(session, "info", f"{key}_you", extra={"sound": "equip"})
        if not session.invisible:
            self._to_room(self.room_of(session.char), "emote", f"{key}_other", exclude=(session,),
                          extra={"actor": session.name, "sound": "equip"}, actor=session.name)
        return pose

    def cmd_stand_up(self, session, message):
        if self.stand_up(session) is None:
            self._error(session, "stand_already")

    def cmd_stand(self, session, message):
        """ "stand": blackjack's, while you're playing a hand; otherwise getting up."""
        if session.blackjack:
            self._finish_hand(session)
            return
        self.cmd_stand_up(session, message)

    def cmd_wake(self, session, message):
        """ "wake": wake up and get to your feet; "wake Maya": wake someone who's asleep here."""
        name = self._arg(message, "a", 40)
        if name and orbit_safety.name_key(name) not in ("up", "me", "myself"):
            other = self._find_near(session, name)
            if other is None:
                self._error(session, "not_here", name=name)
                return
            pose = self.pose_of(other)
            if other is session:
                name = ""
            elif pose is None or pose["kind"] != "sleep":
                self._error(session, "wake_not_asleep", name=other.name)
                return
            else:
                if not session.chat.take():
                    self._error(session, "slow_down")
                    return
                pose["kind"] = "lie"
                self._send(other, "emote", "wake_them", actor=session.name,
                           extra={"actor": session.name, "sound": "emote"})
                self._send(session, "emote", "wake_you_them", name=other.name, extra={"sound": "emote"})
                for watcher in self._in_room(self.room_of(session.char), exclude=(session, other)):
                    self._send(watcher, "emote", "wake_room", actor=session.name, name=other.name,
                               extra={"actor": session.name, "sound": "emote"})
                return
        pose = self.pose_of(session)
        if pose is None or pose["kind"] != "sleep":
            self._error(session, "wake_already")
            return
        self.stand_up(session)

    def rouse(self, session, command):
        """Before a command: a sleeper who does something wakes up first (still lying there); being
        away from the keyboard ends."""
        if session.afk is not None and command not in ("afk", "away", "status", "bye"):
            self.back_from_afk(session)
        pose = self.pose_of(session)
        walking = command in ("move", "go")                     # walking wakes you itself, on the way
        if pose and pose["kind"] == "sleep" and command not in PASSIVE_COMMANDS and not walking:
            pose["kind"] = "lie"
            self._send(session, "info", "woke_you", extra={"sound": "equip"})
            if not session.invisible:
                self._to_room(self.room_of(session.char), "emote", "woke_other", exclude=(session,),
                              extra={"actor": session.name}, actor=session.name)

    # --- following and leading -------------------------------------------------------------------

    def followers_of(self, session):
        return sorted((s for s in self.sessions.values() if s.leader == session.key), key=lambda s: s.key)

    def cmd_follow(self, session, message):
        """ "follow Maya" (Maya is asked), "stop following"/"unfollow" (from the verbs: op stop)."""
        name = self._arg(message, "to", 40) or self._arg(message, "a", 40)
        if message.get("op") == "stop" or orbit_safety.name_key(name) in UNFOLLOW:
            if not self.stop_following(session):
                self._error(session, "follow_none")
            return
        self._ask_to_go_along(session, name, "follow")

    def cmd_lead(self, session, message):
        """ "lead Maya" (Maya is asked), "stop leading" (op stop), "disband" (op disband: both)."""
        op = message.get("op")
        name = self._arg(message, "to", 40) or self._arg(message, "a", 40)
        if op in ("stop", "disband"):
            led = self.stop_leading(session)
            followed = self.stop_following(session) if op == "disband" else False
            if not led and not followed:
                self._error(session, "lead_none" if op == "stop" else "group_none")
            return
        self._ask_to_go_along(session, name, "lead")

    def _ask_to_go_along(self, session, name, kind):
        if not name:
            self._error(session, f"{kind}_whom")
            return
        if orbit_safety.name_key(name) in (session.key, "me", "myself"):
            self._error(session, f"{kind}_self")
            return
        other = self._find_near(session, name)
        if other is None:
            known = self._find_session(name)
            self._error(session, "not_here", name=known.name if known and not known.invisible else name)
            return
        if other is session:
            self._error(session, f"{kind}_self")
            return
        follower, leader = (session, other) if kind == "follow" else (other, session)
        if follower.leader == leader.key:
            self._error(session, "follow_already" if kind == "follow" else "lead_already",
                        name=leader.name if kind == "follow" else follower.name)
            return
        if leader.leader is not None:
            self._error(session, "follow_busy" if kind == "follow" else "lead_following",
                        name=self._name_of(leader.leader) if kind != "follow" else leader.name)
            return
        if self.followers_of(follower):
            self._error(session, "follow_leading" if kind == "follow" else "lead_leader", name=follower.name)
            return
        if other.conn is None:
            self._error(session, "player_away", name=other.name)
            return
        if not self._slow(session):
            return
        now = self.now()
        self.follow_asks[other.key] = {"kind": kind, "from": session.key, "from_name": session.name, "at": now,
                                       "expires": now + FOLLOW_SECONDS}
        self._send(other, "offer", f"{kind}_ask_them", actor=session.name,
                   extra={"actor": session.name, "ask": True, "sound": "offer"})
        self._info(session, f"{kind}_asked", name=other.name)

    def _name_of(self, key):
        other = self.sessions.get(key)
        return other.name if other else key

    def accept_follow(self, session):
        ask = self.follow_asks.pop(session.key, None)
        if ask is None:
            return False
        other = self.sessions.get(ask["from"])
        if other is None or other.conn is None or self.room_of(other.char) != self.room_of(session.char):
            self._error(session, "follow_gone_ask", name=ask["from_name"])
            return True
        follower, leader = (other, session) if ask["kind"] == "follow" else (session, other)
        if leader.leader is not None or self.followers_of(follower):
            self._error(session, "follow_cant_now")
            return True
        self.stop_following(follower, quiet=True)
        follower.leader = leader.key
        self._send(follower, "info", "follow_now_you", name=leader.name, extra={"sound": "npc_warm"})
        self._send(leader, "info", "follow_now_leader", name=follower.name, extra={"sound": "npc_warm"})
        if not follower.invisible:
            for watcher in self._in_room(self.room_of(leader.char), exclude=(follower, leader), visible=False):
                self._send(watcher, "emote", "follow_now_room", actor=follower.name, name=leader.name,
                           extra={"actor": follower.name})
        return True

    def decline_follow(self, session):
        ask = self.follow_asks.pop(session.key, None)
        if ask is None:
            return False
        other = self.sessions.get(ask["from"])
        if other is not None:
            self._send(other, "system", f"{ask['kind']}_declined", name=session.name)
        self._info(session, "follow_you_declined", name=ask["from_name"])
        return True

    def stop_following(self, session, quiet=False, key="follow_stop"):
        """`session` stops following its leader. Returns whether it was following anyone."""
        leader_key, session.leader = session.leader, None
        if leader_key is None:
            return False
        leader = self.sessions.get(leader_key)
        name = leader.name if leader else leader_key
        if not quiet:
            self._info(session, f"{key}_you", name=name)
        if leader is not None and leader.conn is not None and not quiet:
            self._send(leader, "system", "follow_stop_leader", name=session.name)
        return True

    def stop_leading(self, session, key="lead_stop"):
        followers = self.followers_of(session)
        for follower in followers:
            follower.leader = None
            self._send(follower, "system", f"{key}_them", name=session.name)
        if followers and key == "lead_stop":
            self._info(session, "lead_stop_you", names=[f.name for f in followers])
        return bool(followers)

    def forget_following(self, session):
        """`session` leaves the game: whoever follows them stops, and they stop following."""
        self.follow_asks.pop(session.key, None)
        for key, ask in list(self.follow_asks.items()):
            if ask["from"] == session.key:
                self.follow_asks.pop(key, None)
        self.stop_leading(session, key="lead_gone")
        self.stop_following(session, quiet=True)

    def followers_walk(self, leader, old_room, d, dest):
        """The leader walked `d` from `old_room`: those following a step behind go too."""
        moved = []
        for follower in self.followers_of(leader):
            if self.room_of(follower.char) != old_room:
                self.stop_following(follower)                 # already parted: the ferry, a ship...
                continue
            if follower.conn is None:
                continue
            if self.world.locations[dest].get("private") or self.world.locations[dest].get("crew_room"):
                self.stop_following(follower, quiet=True)
                self._info(follower, "follow_private", name=leader.name, dir=self.dir_word(follower.lang, d))
                continue
            if self.walk(follower, d, leader=leader):
                moved.append(follower)
            else:
                self.stop_following(follower, quiet=True)
                self._info(follower, "follow_lost", name=leader.name, dir=self.dir_word(follower.lang, d))
        if moved:
            self._info(leader, "followed_one" if len(moved) == 1 else "followed_many", names=[m.name for m in moved])

    def tick_social(self, now):
        for key, ask in list(self.follow_asks.items()):
            if now < ask["expires"]:
                continue
            self.follow_asks.pop(key, None)
            asker = self.sessions.get(ask["from"])
            if asker is not None:
                self._send(asker, "system", "follow_expired", name=self._name_of(key))
        self.tick_ambience(now)

    # --- gestures in your own words, and dice -----------------------------------------------------

    @staticmethod
    def pose_text(name, text):
        """ "Maya waves hello." from "waves hello": a capital where it matters, a full stop at the end."""
        text = " ".join(str(text or "").split())
        if not text:
            return ""
        if text[-1] not in ".!?)\"'":
            text += "."
        joiner = "" if text[0] in ",'" else " "
        return f"{name}{joiner}{text}"

    def cmd_pose(self, session, message):
        """ "emote waves hello", ":waves hello": the room reads "Maya waves hello."."""
        text = self._arg(message, "a", self.config["say_limit"])
        if not text.strip(" :"):
            self._error(session, "pose_what")
            return
        words = self._chat_text(session, text.lstrip(": "))
        if words is None:
            return
        line = self.pose_text(session.name, words)
        self.note_room_chat(session)
        self._send(session, "emote", text=line)
        for other in self._in_room(self.room_of(session.char), exclude=(session,)):
            self._send(other, "emote", text=line, extra={"actor": session.name})

    def cmd_roll(self, session, message):
        """ "roll", "roll a die", "roll 2d6", "roll d20": fair dice, for the room to see and the log."""
        text = orbit_safety.name_key(self._arg(message, "a", 40))
        count, sides = self._dice(text)
        if count is None:
            self._error(session, "roll_how", most=MAX_DICE, sides=MAX_SIDES)
            return
        if self._muted(session):
            return
        if not session.chat.take():
            self._error(session, "slow_down")
            return
        rolls = [self.rng.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        key = ("dice_one" if count == 1 else "dice_many") + ("_d6" if sides == 6 else "")
        dice = self.render(session.lang, key, n=count, sides=sides)
        logger.info("%s rolled %s: %s", session.name, f"{count}d{sides}", rolls)
        self.note_room_chat(session)
        one = count == 1
        self._send(session, "emote", "roll_you_one" if one else "roll_you", dice=dice, rolls=[str(r) for r in rolls],
                   total=total, extra={"sound": "dice"})
        for other in self._in_room(self.room_of(session.char), exclude=(session,)):
            other_dice = self.render(other.lang, key, n=count, sides=sides)
            self._send(other, "emote", "roll_other_one" if one else "roll_other", actor=session.name, dice=other_dice,
                       rolls=[str(r) for r in rolls], total=total, extra={"actor": session.name, "sound": "dice"})

    @staticmethod
    def _dice(text):
        """(how many, how many sides) from "", "a die", "dice", "2d6", "d20", "3 dice", or (None, None)."""
        words = [w for w in text.split() if w not in ("the", "some", "of")]
        if not words or words in (["dice"], ["die"]):
            return (2 if words == ["dice"] or not words else 1), 6
        if len(words) == 2 and words[1] in ("die", "dice", "d6") and (words[0].isdigit() or words[0] in NUMBER_WORDS):
            count = int(words[0]) if words[0].isdigit() else NUMBER_WORDS[words[0]]
            return (count, 6) if 1 <= count <= MAX_DICE else (None, None)
        if len(words) == 1:
            m = DICE_RE.match(words[0])
            if m:
                count = int(m.group(1) or 1)
                sides = int(m.group(2))
                if 1 <= count <= MAX_DICE and 2 <= sides <= MAX_SIDES:
                    return count, sides
        return None, None

    # --- the time ----------------------------------------------------------------------------------

    def cmd_time(self, session, message):
        lang = session.lang
        now = datetime.datetime.fromtimestamp(self.now(), datetime.timezone.utc)
        lines = [self.render(lang, "time_station", time=now.strftime("%H:%M"),
                             day=f"{now.strftime('%A')} {now.day} {now.strftime('%B %Y')}")]
        wid = self.world_here(session.char)
        world = self.world.worlds.get(wid) if wid else None
        day = (world or {}).get("day")
        if world and day and wid != "station":
            hours = float(day["hours"])
            local = ((self.now() / 3600.0 + float(day.get("offset", 0))) % hours) / hours * 24.0
            hour, minute = int(local), int((local % 1) * 60)
            part = next(key for until, key in DAY_PARTS if hour < until)
            whole = int(hours)
            length = self.render(lang, "day_length", hours=whole, minutes=int(round((hours - whole) * 60))) \
                if abs(hours - whole) > 0.01 else self.render(lang, "day_hours", hours=whole)
            lines.append(self.render(lang, "time_world", world=world["name"], time=f"{hour:02d}:{minute:02d}",
                                     part=self.render(lang, part), length=length))
        elif wid == "station":
            lines.append(self.render(lang, "time_orbit"))
        self._info(session, text="\n".join(lines))
        if not session.invisible:
            self._to_room(self.room_of(session.char), "emote", "time_other", exclude=(session,),
                          extra={"actor": session.name}, actor=session.name)

    # --- away from the keyboard ------------------------------------------------------------------

    def cmd_afk(self, session, message):
        note = orbit_safety.tidy(self._arg(message, "a", 80), 80)
        if note:
            if self._muted(session):
                note = ""
            else:
                note = self.filter.clean(note)
        session.afk = note
        self._info(session, "afk_you_note" if note else "afk_you", note=note)
        if not session.invisible:
            self._to_room(self.room_of(session.char), "emote", "afk_other_note" if note else "afk_other",
                          exclude=(session,), extra={"actor": session.name}, actor=session.name, note=note)

    def back_from_afk(self, session):
        session.afk = None
        self._info(session, "afk_back_you")
        if not session.invisible:
            self._to_room(self.room_of(session.char), "emote", "afk_back_other", exclude=(session,),
                          extra={"actor": session.name}, actor=session.name)

    # --- the ways out, and a glimpse of the next room ---------------------------------------------------

    def cmd_exits(self, session, message):
        """ "exits": a line each, "North: the Promenade", in compass order (the Nova Realm's)."""
        if self.in_transit(session):
            return
        char, lang = session.char, session.lang
        if self.in_the_dark(char):
            back = char["stats"].get("back")
            if back and back in self.world.exits.get(char["location"], {}):
                self._info(session, "exits_dark", dir=self.dir_word(lang, back))
            else:
                self._info(session, "exits_dark_lost")
            return
        here = char["location"]
        known = set(char["stats"].get("map") or [])
        lines = []
        for d, ex in self.world.neighbours(here):
            dest = self.world.locations[ex["to"]]
            word = self.dir_word(lang, d)
            word = word[:1].upper() + word[1:]
            if dest.get("secret") and ex["to"] not in known:
                lines.append(self.render(lang, "exits_unknown", dir=word))
                continue
            notes = []
            if ex.get("lock") and not self.has_access(char, ex["lock"]):
                notes.append(self.render(lang, "exit_note_locked"))
            if dest.get("airless") and not self._loc(char).get("airless"):
                notes.append(self.render(lang, "exit_note_vacuum"))
            if ex.get("oneway"):
                notes.append(self.render(lang, "exit_note_oneway"))
            if dest.get("dark"):
                notes.append(self.render(lang, "exit_note_dark"))
            if dest.get("crew_room"):
                notes.append(self.render(lang, "exit_note_crew"))
            elif dest.get("private"):
                notes.append(self.render(lang, "exit_note_private"))
            place = pick(dest["ref"], lang)
            entry = self.render(lang, "exits_entry", dir=word, place=place)
            if notes:
                entry += f" ({', '.join(notes)})"
            lines.append(entry)
        partner = self.world.shuttle_partner(here)
        if partner:
            lines.append(self.render(lang, "exits_kancil", place=self.world.locations[partner]["ref"]))
        if not lines:
            self._info(session, "exits_none")
            return
        title = self.render(lang, "exits_title", place=self.cabin_in(session) or self._loc(char)["ref"])
        self._info(session, text="\n".join([title] + lines))

    def cmd_peer(self, session, message):
        """ "peer north": the next room's name, the start of its description, who's there."""
        char, lang = session.char, session.lang
        text = self._arg(message, "a", 20)
        d = self.world.find_direction(text) if text else None
        if d is None:
            self._error(session, "peer_what")
            return
        if self.in_transit(session):
            return
        if self.in_the_dark(char):
            self._error(session, "too_dark_to_see")
            return
        ex = self.world.exits.get(char["location"], {}).get(d)
        if ex is None:
            self._error(session, "no_exit_there", dir=self.dir_word(lang, d), exits=self._exit_words(session),
                        sound="bump")
            return
        dest = self.world.locations[ex["to"]]
        if not session.invisible:
            self._to_room(self.room_of(char), "emote", "peer_other", exclude=(session,),
                          extra={"actor": session.name}, actor=session.name, dir=self.dir_word(lang, d))
        lines = [self.render(lang, "peer_you", dir=self.dir_word(lang, d))]
        if dest.get("private") or dest.get("crew_room"):
            lines.append(self.render(lang, "peek_private", dir=self.dir_word(lang, d), place=dest["ref"]))
            self._info(session, text="\n".join(lines))
            return
        if dest.get("dark") or self.event_dark(ex["to"]):
            lines.append(self.render(lang, "peer_dark", dir=self.dir_word(lang, d)))
            self._info(session, text="\n".join(lines))
            return
        lines.append(pick(dest["name"], lang))
        lines.append(first_sentence(pick(dest["desc"], lang)))
        people = sorted(self._in_room(ex["to"], visible=True), key=lambda o: o.key)
        if people:
            lines.append(self.render(lang, "peer_people", people=[self._peer_person(lang, o) for o in people]))
        residents = [self.npc_name(nid) for nid in sorted(self.npcs_in(ex["to"]), key=self.npc_name)]
        if residents:
            lines.append(self.render(lang, "peer_residents", people=residents))
        if not people and not residents:
            lines.append(self.render(lang, "peer_nobody"))
        lying = self.floor_text(lang, ex["to"])
        if lying:
            lines.append(lying)
        self._info(session, text="\n".join(lines))

    def _peer_person(self, lang, other):
        pose = self.pose_of(other)
        if pose is None:
            return other.name
        key = {"sit": "peer_sitting", "lie": "peer_lying", "sleep": "peer_asleep"}[pose["kind"]]
        return self.render(lang, key, name=other.name)

    # --- the rooms' own lives ------------------------------------------------------------------------

    def tick_ambience(self, now):
        rules = self.npc_rules
        low, high = rules["idle_gap"]
        for lid, loc in self.world.locations.items():
            lines = (loc.get("ambient") or {}).get("en")
            if not lines:
                continue
            due = self.ambient_next.get(lid)
            if due is None:
                self.ambient_next[lid] = now + self.npc_rng.uniform(float(low), float(high))
                continue
            if now < due:
                continue
            self.ambient_next[lid] = now + self.npc_rng.uniform(float(low), float(high))
            listeners = self._listeners(lid)
            if not listeners or self.world.locations[lid].get("private"):
                continue
            if now - self.room_chat.get(lid, -1e12) < float(rules["quiet_seconds"]):
                continue
            if now - self.room_idle.get(lid, -1e12) < float(rules["room_gap"]):
                continue
            choices = list(range(len(lines)))
            if len(choices) > 1 and self.ambient_last.get(lid) in choices:
                choices.remove(self.ambient_last[lid])
            index = self.npc_rng.choice(choices)
            self.ambient_last[lid] = index
            self.room_idle[lid] = now
            line = self.ambient_line(lid, lines[index])
            for other in listeners:
                self._send(other, "info", text=line, extra={"ambient": True})

    def ambient_line(self, lid, line):
        """A room's line, with what it knows filled in (the song on the jukebox)."""
        if "{song}" not in str(line):
            return str(line)
        song = self.jukebox_song(lid)
        return str(line).replace("{song}", pick(song["name"]) if song else self.render("en", "jukebox_nothing"))


def bare(text):
    """ "the sofa" -> "sofa": a name without "the", "a" or "an" in front, as typed otherwise."""
    words = str(text or "").split()
    while len(words) > 1 and words[0].lower() in ("the", "a", "an", "my"):
        words = words[1:]
    return " ".join(words)


def first_sentence(text):
    """The first sentence of a description: a glimpse, not the whole room."""
    text = " ".join(str(text or "").split())
    m = re.search(r"[.!?](\s|$)", text)
    return text[:m.end()].strip() if m else text
