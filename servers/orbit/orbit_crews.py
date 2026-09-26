# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Crews: players who band together under a name, with a chat of their own and
a place on the crew board.

    crew                                your crew: its captain, members, motto, points
    crew create Nova                    found one (credits, and a level)
    crew invite Sam                     the captain asks someone in; they
                                        accept or decline (like an offer)
    crew say hello                      to every member online, anywhere
    crew leave                          leave (the captain's place goes to the
                                        longest-serving member; the last one out
                                        ends the crew)
    crew kick Sam                       the captain sends someone off
    crew captain Sam                    hand the captaincy over
    crew motto ...                      the captain's line under the name
    crews                               the crew board: the most points

A crew earns a point for every XP its members earn while in it. Crew chat is
filtered, rate-limited and muted like the rest of the chat, never stored, and
a client can ignore a member there as anywhere; names go through the word
filter; admins can disband a crew (disband crew Nova). Everything is in
the database (crews, crew_members); invitations wait in memory for two
minutes, like trade offers.
"""

import logging
import re

import orbit_safety

logger = logging.getLogger("orbit.game")

CREW_NAME_RE = re.compile(r"^[^\W_][\w' -]*$", re.UNICODE)
ROLES = ("captain", "member")


def crew_key(name):
    """How crew names are told apart: "Morning Star" and "morningstar" are one."""
    return orbit_safety.name_key(name).replace(" ", "")


class CrewsMixin:
    @staticmethod
    def commands():
        return {"crew": CrewsMixin.cmd_crew, "crew_create": CrewsMixin.cmd_crew_create,
                "crew_invite": CrewsMixin.cmd_crew_invite, "crew_say": CrewsMixin.cmd_crew_say,
                "crew_leave": CrewsMixin.cmd_crew_leave, "crew_kick": CrewsMixin.cmd_crew_kick,
                "crew_captain": CrewsMixin.cmd_crew_captain, "crew_motto": CrewsMixin.cmd_crew_motto,
                "crews": CrewsMixin.cmd_crews}

    def init_crews(self):
        self.crew_invites = {}          # the invited player's key -> the invitation

    def crew_rules(self):
        return self.econ.get("crews", {})

    # --- who's in which ------------------------------------------------------------------------

    def crew_of(self, char):
        """(crew row, role) of a character, or (None, None)."""
        found = self.store.crew_of(char["id"])
        return found if found else (None, None)

    def crew_hangar_lines(self, session):
        """The crew board, in the Crew Hangar."""
        if not self._loc(session.char).get("crew_room"):
            return []
        lang = session.lang
        crew, _role = self.crew_of(session.char)
        if crew is None:
            return [self.render(lang, "crew_hangar_no_crew")]
        board = self.store.top_crews(1000)
        place = next((i + 1 for i, row in enumerate(board) if row["name"] == crew["name"]), len(board))
        lines = [self.render(lang, "crew_hangar_board", crew=crew["name"], points=int(crew["points"]), n=place,
                             total=len(board))]
        if crew["motto"]:
            lines.append(self.render(lang, "crew_motto_is", motto=crew["motto"]))
        return lines

    def crew_line(self, lang, char):
        crew, role = self.crew_of(char)
        if crew is None:
            return ""
        return self.render(lang, "crew_look_captain" if role == "captain" else "crew_look", crew=crew["name"])

    def _mine(self, session, captain=False):
        """Your crew (and whether you lead it), or None after saying why not."""
        crew, role = self.crew_of(session.char)
        if crew is None:
            self._error(session, "crew_none")
            return None
        if captain and role != "captain":
            self._error(session, "crew_not_captain")
            return None
        return crew

    def _online_members(self, crew_id):
        members = {row["char_id"] for row in self.store.crew_members(crew_id)}
        return [s for s in self.sessions.values() if s.char["id"] in members and s.conn is not None]

    def _to_crew(self, crew_id, kind, key=None, exclude=(), extra=None, **params):
        for other in self._online_members(crew_id):
            if other not in exclude:
                self._send(other, kind, key, extra=extra, **params)

    # --- looking ---------------------------------------------------------------------------------

    def cmd_crew(self, session, message):
        crew, _role = self.crew_of(session.char)
        lang = session.lang
        if crew is None:
            rules = self.crew_rules()
            self._info(session, "crew_none_how", price=int(rules.get("create_price", 0)),
                       level=int(rules.get("create_level", 1)))
            return
        members = self.store.crew_members(crew["id"])
        online = {s.char["id"] for s in self._online_members(crew["id"])}
        captain = next((m["name"] for m in members if m["role"] == "captain"), "?")
        names = [self.render(lang, "crew_member_online" if m["char_id"] in online else "crew_member", name=m["name"])
                 for m in members]
        text = self.render(lang, "crew_info", crew=crew["name"], captain=captain, n=len(members),
                           members=", ".join(names), points=int(crew["points"]))
        if crew["motto"]:
            text += " " + self.render(lang, "crew_motto_is", motto=crew["motto"])
        self._info(session, text=text)

    def cmd_crews(self, session, message):
        lang = session.lang
        rows = self.store.top_crews(int(self.crew_rules().get("board_size", 5)))
        entries = [self.render(lang, "crew_board_entry", place=i, crew=row["name"], points=int(row["points"]),
                               n=int(row["members"])) for i, row in enumerate(rows, 1)]
        text = self.render(lang, "crew_board", entries="; ".join(entries) or self.render(lang, "board_empty"))
        crew, _role = self.crew_of(session.char)
        if crew is not None:
            text += " " + self.render(lang, "crew_board_yours", crew=crew["name"], points=int(crew["points"]))
        self._info(session, text=text)

    # --- founding -------------------------------------------------------------------------------

    def check_crew_name(self, text):
        """(name, None) or (None, why): "length", "characters", "filtered" or "taken"."""
        rules = self.crew_rules()
        name = " ".join(str(text or "").split())
        if not int(rules.get("name_min", 3)) <= len(name) <= int(rules.get("name_max", 24)):
            return None, "length"
        if not CREW_NAME_RE.match(name):
            return None, "characters"
        if self.filter.contains(name) or any(bad and bad in orbit_safety.fold(name.replace(" ", ""))
                                             for bad in self.filter.words if len(bad) >= 4):
            return None, "filtered"
        if self.store.crew_by_key(crew_key(name)) is not None:
            return None, "taken"
        return name, None

    def cmd_crew_create(self, session, message):
        char = session.char
        rules = self.crew_rules()
        crew, _role = self.crew_of(char)
        if crew is not None:
            self._error(session, "crew_already", crew=crew["name"])
            return
        text = self._arg(message, "a", 60)
        if not text:
            self._error(session, "crew_create_how")
            return
        level = int(rules.get("create_level", 1))
        if self.level_of(int(char.get("xp") or 0)) < level:
            self._error(session, "crew_level", level=level)
            return
        name, why = self.check_crew_name(text)
        if why:
            self._error(session, f"crew_name_{why}", name=" ".join(text.split())[:40],
                        low=int(rules.get("name_min", 3)), high=int(rules.get("name_max", 24)))
            return
        price = int(rules.get("create_price", 0))
        if char["credits"] < price:
            self._error(session, "crew_poor", price=price, credits=char["credits"])
            return
        if not self._slow(session):
            return
        with self.store.transaction():
            self.spend(char, price, "crews")
            self.store.create_crew(name, crew_key(name), char["id"], self.now())
            self._save(session)
        logger.info("%s founded the crew %s", session.name, name)
        self._send(session, "paid", "crew_created", extra={"sound": "crew_join"}, crew=name, price=price,
                   credits=char["credits"])
        self.check_achievements(session)

    # --- joining -------------------------------------------------------------------------------

    def cmd_crew_invite(self, session, message):
        crew = self._mine(session, captain=True)
        if crew is None:
            return
        name = self._arg(message, "to", 40) or self._arg(message, "a", 40)
        target = self._find_session(name) if name else None
        if target is None or target.conn is None or (target.invisible and not self.is_admin(session)):
            self._error(session, "no_player", name=name or "?")
            return
        if target is session:
            self._error(session, "crew_invite_yourself")
            return
        theirs, _role = self.crew_of(target.char)
        if theirs is not None:
            self._error(session, "crew_they_have_one", name=target.name, crew=theirs["name"])
            return
        rules = self.crew_rules()
        if len(self.store.crew_members(crew["id"])) >= int(rules.get("max_members", 12)):
            self._error(session, "crew_full", n=int(rules.get("max_members", 12)))
            return
        waiting = self.crew_invites.get(target.key)
        if waiting and waiting["crew_id"] == crew["id"]:
            self._error(session, "crew_invite_waiting", name=target.name)
            return
        now = self.now()
        self.crew_invites[target.key] = {"from": session.key, "from_name": session.name, "crew_id": crew["id"],
                                         "crew_name": crew["name"], "at": now,
                                         "expires": now + float(rules.get("invite_seconds", 120))}
        self._send(target, "offer", "crew_invited", extra={"actor": session.name, "ask": "crew"},
                   name=session.name, crew=crew["name"])
        self._info(session, "crew_invite_sent", name=target.name, crew=crew["name"])

    def accept_crew_invite(self, session):
        invite = self.crew_invites.pop(session.key, None)
        if invite is None:
            return False
        crew = self.store.crew_by_id(invite["crew_id"])
        mine, _role = self.crew_of(session.char)
        if crew is None:
            self._error(session, "crew_gone", crew=invite["crew_name"])
            return True
        if mine is not None:
            self._error(session, "crew_already", crew=mine["name"])
            return True
        if len(self.store.crew_members(crew["id"])) >= int(self.crew_rules().get("max_members", 12)):
            self._error(session, "crew_full", n=int(self.crew_rules().get("max_members", 12)))
            return True
        self.store.add_crew_member(crew["id"], session.char["id"], "member", self.now())
        logger.info("%s joined the crew %s", session.name, crew["name"])
        self._send(session, "paid", "crew_joined_you", extra={"sound": "crew_join"}, crew=crew["name"])
        self._to_crew(crew["id"], "system", "crew_joined", exclude=(session,), extra={"sound": "crew_join"},
                      name=session.name, crew=crew["name"])
        self.check_achievements(session)
        return True

    def decline_crew_invite(self, session):
        invite = self.crew_invites.pop(session.key, None)
        if invite is None:
            return False
        other = self.sessions.get(invite["from"])
        if other is not None:
            self._send(other, "system", "crew_invite_declined", name=session.name)
        self._info(session, "crew_you_declined", crew=invite["crew_name"])
        return True

    # --- talking ---------------------------------------------------------------------------------

    def cmd_crew_say(self, session, message):
        crew = self._mine(session)
        if crew is None:
            return
        words = self._chat_text(session, self._arg(message))
        if words is None:
            return
        members = self._online_members(crew["id"])
        for other in members:
            if other is not session:
                self._send(other, "crew", "crew_said_other", extra=dict(self._voice_extra(session, words),
                                                                        sound="crew_chat"),
                           crew=crew["name"], actor=session.name, words=words)
        self._send(session, "crew_sent", "crew_said_self", brief="brief_crew", crew=crew["name"], words=words,
                   n=len(members) - 1, extra=self._voice_extra(session, words, actor=False))

    # --- leaving, and the captain's part ----------------------------------------------------------

    def cmd_crew_leave(self, session, message):
        crew = self._mine(session)
        if crew is None:
            return
        self._leave_crew(session.char, crew)
        self._send(session, "system", "crew_left_you", crew=crew["name"])

    def _leave_crew(self, char, crew, kicked=False):
        """Takes `char` out of `crew`; a captain's place passes on; the last one out ends it."""
        with self.store.transaction():
            members = self.store.crew_members(crew["id"])
            me = next((m for m in members if m["char_id"] == char["id"]), None)
            self.store.remove_crew_member(char["id"])
            rest = [m for m in members if m["char_id"] != char["id"]]
            if not rest:
                self.store.delete_crew(crew["id"])
                logger.info("the crew %s is no more", crew["name"])
                return
            heir = None
            if me is not None and me["role"] == "captain":
                heir = min(rest, key=lambda m: (m["joined"], m["char_id"]))
                self.store.set_crew_role(heir["char_id"], "captain")
        logger.info("%s left the crew %s", char["name"], crew["name"])
        self._to_crew(crew["id"], "system", "crew_kicked" if kicked else "crew_left", name=char["name"],
                      crew=crew["name"])
        if heir is not None:
            self._to_crew(crew["id"], "system", "crew_new_captain", name=heir["name"], crew=crew["name"])

    def _member_named(self, session, crew, name):
        key = orbit_safety.name_key(name)
        for member in self.store.crew_members(crew["id"]):
            if orbit_safety.name_key(member["name"]) == key:
                return member
        self._error(session, "crew_no_member", name=name or "?", crew=crew["name"])
        return None

    def cmd_crew_kick(self, session, message):
        crew = self._mine(session, captain=True)
        if crew is None:
            return
        name = self._arg(message, "to", 40) or self._arg(message, "a", 40)
        member = self._member_named(session, crew, name)
        if member is None:
            return
        if member["char_id"] == session.char["id"]:
            self._error(session, "crew_kick_yourself")
            return
        char = self.store.by_id(member["char_id"])
        self._leave_crew(char, crew, kicked=True)
        target = self.sessions.get(char["name_key"])
        if target is not None:
            self._send(target, "system", "crew_kicked_you", crew=crew["name"], name=session.name)
        self._info(session, "crew_kicked_done", name=member["name"])

    def cmd_crew_captain(self, session, message):
        crew = self._mine(session, captain=True)
        if crew is None:
            return
        name = self._arg(message, "to", 40) or self._arg(message, "a", 40)
        member = self._member_named(session, crew, name)
        if member is None:
            return
        if member["char_id"] == session.char["id"]:
            self._error(session, "crew_captain_already")
            return
        with self.store.transaction():
            self.store.set_crew_role(member["char_id"], "captain")
            self.store.set_crew_role(session.char["id"], "member")
        self._to_crew(crew["id"], "system", "crew_new_captain", name=member["name"], crew=crew["name"])

    def cmd_crew_motto(self, session, message):
        crew = self._mine(session, captain=True)
        if crew is None:
            return
        text = orbit_safety.tidy(self._arg(message), int(self.crew_rules().get("motto_max", 80)))
        motto = self.filter.clean(text) if text else ""
        self.store.set_crew_motto(crew["id"], motto)
        self._info(session, "crew_motto_set" if motto else "crew_motto_cleared", motto=motto)

    # --- points ----------------------------------------------------------------------------------

    def crew_points(self, char, xp):
        """XP a member earned counts for their crew."""
        if xp <= 0:
            return
        found = self.store.crew_of(char["id"])
        if found:
            self.store.add_crew_points(found[0]["id"], int(xp))

    # --- time, leaving, admins ---------------------------------------------------------------------

    def tick_crews(self, now):
        for key, invite in list(self.crew_invites.items()):
            if now < invite["expires"]:
                continue
            self.crew_invites.pop(key, None)
            target = self.sessions.get(key)
            if target is not None:
                self._send(target, "system", "crew_invite_expired_you", crew=invite["crew_name"])

    def forget_crew_invites(self, session):
        self.crew_invites.pop(session.key, None)
        for key, invite in list(self.crew_invites.items()):
            if invite["from"] == session.key:
                self.crew_invites.pop(key, None)

    def admin_crew_disband(self, session, message):
        name = self._arg(message, "a", 60)
        crew = self.store.crew_by_key(crew_key(name)) if name else None
        if crew is None:
            self._error(session, "crew_unknown", crew=name or "?")
            return
        online = self._online_members(crew["id"])
        self.store.delete_crew(crew["id"])
        for key, invite in list(self.crew_invites.items()):
            if invite["crew_id"] == crew["id"]:
                self.crew_invites.pop(key, None)
        for other in online:
            if other is not session:
                self._send(other, "system", "crew_disbanded", crew=crew["name"])
        self._log(session, "disband crew", crew["name"])
        self._info(session, "crew_disband_done", crew=crew["name"])
