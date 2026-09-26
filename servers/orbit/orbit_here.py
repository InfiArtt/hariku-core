# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
"x here": what you can do in the room you're in, and "x" and a name: what
you can do with someone or something, a line each (the way examine works
in the Nova Realm).

  x here, examine here, what can I do here, commands here, help here
        "Here in the Cantina you can:", then one command a line with a short
        hint ("list: what the Cantina bar sells, and the prices"), then
        "Type help for everything else."
  x Rocco, x Maya, x headlamp, x jukebox, what can I do with Rocco
        "With Rocco you can:", then one command a line
  x me  what you can do about yourself
  x     how it's used

What's listed comes from the room (world.json: its market, shop, farm,
mining, salvage, the casino, the arcade, the temple, the desks, the Gate, the
ferry, the Wombat, the creatures, the courier gigs), the residents and
players in it, the events on here, your job, your mission, your ship and
your cabin, through the same checks the commands make (market_here,
shop_here, farm_here, mine_here, casino_here, ferry_here...): a line is
there only where its command works. tests/test_orbit_here.py types each
line's command in every kind of room and checks it isn't refused for the
place. What works everywhere (look, inventory, who, say...) is left to help.

An entry is (the command as a player types it, the key of its hint in
texts.json, the hint's values); the lines are "command: hint".
"""

import orbit_safety
from orbit_lang import pick

HERE_WORDS = {"here", "room", "this room", "around", "this place", "the room", "place"}
SELF_WORDS = {"me", "myself", "self", "yourself"}
BET = 50                    # the stake in the casino's examples (within the casino's limits)
DUEL_STAKE = 20


class HereMixin:
    @staticmethod
    def commands():
        return {"examine": HereMixin.cmd_examine}

    # --- the command -----------------------------------------------------------------------

    def cmd_examine(self, session, message):
        """ "x here", "x Rocco", "x" (see the module notes)."""
        text = self._arg(message, "a", 80)
        key = orbit_safety.name_key(text)
        if not key:
            self._info(session, "here_usage")
            return
        if key in HERE_WORDS:
            self._info(session, text=self.here_text(session))
            return
        found = self.examine_target(session, text)
        if found is None:
            player, resident = self._find_session(text), self.find_npc(text)
            if player is not None and not player.invisible:
                self._error(session, "not_here", name=player.name)
            elif resident is not None and self.npcs[resident]["room"] is not None:
                self._error(session, "npc_elsewhere", name=self.npc_name(resident),
                            where=self.world.locations[self.npcs[resident]["room"]]["in"])
            else:
                self._error(session, "look_what", what=text)
            return
        title, entries = found
        self._info(session, text="\n".join([title] + self._entry_lines(session, entries)))

    def _entry_lines(self, session, entries):
        lang = session.lang
        return [self.render(lang, "here_line", cmd=cmd, what=self.render(lang, key, **params))
                for cmd, key, params in entries]

    def here_text(self, session):
        """ "x here", as lines: the title, a command a line, and where to find the rest."""
        lang, char = session.lang, session.char
        if self.in_the_dark(char):
            return "\n".join([self.render(lang, "here_dark"), self.render(lang, "here_end")])
        place = self.cabin_in(session) or self._loc(char)["in"]
        lines = [self.render(lang, "here_title", place=place)]
        lines.extend(self._entry_lines(session, self.here_actions(session)) or [self.render(lang, "here_nothing")])
        lines.append(self.render(lang, "here_end"))
        return "\n".join(lines)

    # --- what can be done here ----------------------------------------------------------------

    def here_actions(self, session):
        """[(command, hint key, hint values)]: what can be done in this room (in the dark,
        nothing)."""
        if self.in_the_dark(session.char):
            return []
        entries = []
        for part in (self._here_travel, self._here_market, self._here_shop, self._here_pawn, self._here_farm,
                     self._here_digging, self._here_casino, self._here_arcade, self._here_temple,
                     self._here_desks, self._here_contests, self._here_crew, self._here_work,
                     self._here_mission, self._here_cabin, self._here_social, self._here_events,
                     self._here_residents, self._here_things):
            entries.extend(part(session))
        return entries

    def _others_here(self, session):
        """The other players you can see here, by name."""
        return sorted(self._in_room(self.room_of(session.char), exclude=(session,), visible=True),
                      key=lambda o: o.key)

    def thing_word(self, tid):
        """What players call a thing: its first name ("mapper"), else its name ("pocket mapper")."""
        thing = self.world.things[tid]
        names = (thing.get("names") or {}).get("en") or []
        return names[0] if names else pick(thing["one"])

    def _here_travel(self, session):
        char = session.char
        entries = []
        here = char["location"]
        partner = self.world.shuttle_partner(here)
        if partner:
            entries.append((self.render(session.lang, "step_kancil"), "here_board",
                            {"place": self.world.locations[partner]["ref"]}))
        ferry = self.ferry_here(char)
        if ferry:
            dest = next((w for w, wd in self.world.worlds.items() if w != ferry and wd.get("ferry")), None)
            if dest:
                entries.append((f"ferry to {pick(self.world.worlds[dest]['name'])}", "here_ferry", {}))
        gate = self.gate_here(char)
        if gate:
            dest = next((w for w, wd in self.world.worlds.items() if w != gate and wd.get("gate")), None)
            if dest:
                entries.append((f"gate to {pick(self.world.worlds[dest]['name'])}", "here_gate", {}))
        if ferry or gate or here in self.world.travel_rooms(self.world.world_of(here) or "station"):
            entries.append(("worlds", "here_worlds", {}))
        if self.ship_docked_at(char) is not None:
            entries.append(("embark", "here_embark", {}))
            entries.append(("refuel", "here_refuel", {}))
        if here == "ship":
            entries.extend(self._here_aboard(session))
        if here == "ferry" and self.now() < float((char["stats"].get("ferry") or {}).get("depart", 0)):
            entries.append(("disembark", "here_disembark_ferry", {}))
        return entries

    def _here_aboard(self, session):
        char = session.char
        ship = self.ship_aboard(char)
        visiting = char["stats"].get("visit") not in (None, session.key)
        if ship is None:
            return []
        if visiting:
            return [] if ship.get("flight") else [("disembark", "here_disembark", {})]
        entries = []
        if not ship.get("flight"):
            here = self.ship_world(ship)
            dest = next((w for w in self.world.worlds if w != here), None)
            if dest:
                entries.append((f"fly to {pick(self.world.worlds[dest]['name'])}", "here_fly", {}))
            entries.append(("refuel", "here_refuel", {}))
        good = next((g for g in sorted(char["inventory"]) if g in self.world.goods and char["inventory"][g] > 0),
                    None)
        entries.append((f"load all {self.good_word(good)['en']}" if good else "load all", "here_load", {}))
        entries.append(("unload all", "here_unload", {}))
        entries.append(("cargo", "here_cargo", {}))
        if not ship.get("flight"):
            entries.append(("disembark", "here_disembark", {}))
        return entries

    def _here_market(self, session):
        market = self.market_here(session.char)
        if market is None:
            return []
        entries = [("prices", "here_prices", {})]
        sells = next((g for g in self.world.goods if g in market["sells"]), None)
        if sells:
            entries.append((f"buy 2 {self.good_word(sells)['en']}", "here_market_buy", {}))
        buys = next((g for g in self.world.goods if g in market["buys"]), None)
        if buys:
            entries.append((f"sell 2 {self.good_word(buys)['en']}", "here_market_sell", {}))
        return entries

    def _here_shop(self, session):
        sid, shop = self.shop_here(session.char)
        if shop is None or not shop.get("stock"):
            return []
        first = shop["stock"][0]
        return [("list", "here_list", {"shop": shop["name"]}),
                (f"buy {self.thing_word(first)}", "here_buy", {"shop": shop["name"]})]

    def _here_pawn(self, session):
        char = session.char
        if not self.pawn_here(char):
            return []
        entries = [("list", "here_pawn_list", {})]
        owned = next((t for t in sorted(char["inventory"]) if char["inventory"][t] > 0 and self.pawn_value(t)), None)
        if owned:
            entries.append((f"sell {self.thing_word(owned)}", "here_pawn_sell", {}))
        return entries

    def _here_farm(self, session):
        char = session.char
        if not self.farm_here(char):
            return []
        crops = [c for c, crop in self.world.crops.items() if self.owns(char, crop["seed"])] or \
            [c for c, crop in self.world.crops.items() if int(crop.get("level", 1)) <= self.job_level(char)]
        entries = [("farm", "here_farm", {})]
        if crops:
            entries.append((f"plant {self.good_word(self.world.crops[crops[0]]['good'])['en']}", "here_plant", {}))
        entries.append(("water", "here_water", {}))
        entries.append(("harvest", "here_harvest", {}))
        return entries

    def _here_digging(self, session):
        char = session.char
        entries = []
        if self.mine_here(char):
            entries.append(("mine", "here_mine", {}))
        if self.salvage_here(char):
            entries.append(("collect", "here_collect", {}))
        for cid in self.creature_here(char, "")[1]:
            creature = self.econ["creatures"][cid]
            entries.append((f"face {creature['names']['en'][0]}", "here_face", {"creature": creature["one"]}))
        if self.gig_hub_here(char):
            entries.append(("gig", "here_gig", {}))
        return entries

    def _here_casino(self, session):
        if not self.casino_here(session.char):
            return []
        casino = self.econ["casino"]
        bet = max(int(casino["min_bet"]), min(int(casino["max_bet"]), BET))
        entries = [("casino", "here_casino", {}), (f"dice {bet} high", "here_dice", {}),
                   (f"slots {bet}", "here_slots", {}), (f"blackjack {bet}", "here_blackjack", {})]
        others = self._others_here(session)
        if others:
            flip = casino["coinflip"]
            stake = max(int(flip["min"]), min(int(flip["max"]), BET))
            entries.append((f"challenge {others[0].name} {stake}", "here_challenge", {"name": others[0].name}))
        entries.append(("lottery", "here_lottery", {}))
        return entries

    def _here_arcade(self, session):
        if not self.at_cabinets(session.char):
            return []
        game = self.arcade_game("quickdraw") or {}
        name = ((game.get("names") or {}).get("en") or ["quick draw"])[0]
        return [("arcade", "here_arcade", {}), (f"play {name}", "here_play", {}),
                ("arcade scores", "here_scores", {})]

    def _here_temple(self, session):
        char = session.char
        if not self.temple_here(char):
            return []
        entries = [("ring the bell", "here_ring", {}), ("light a lantern", "here_lantern", {})]
        if any(not c["name"] for c in self.children_of(char)):
            entries.append(("naming rite Lily", "here_naming", {}))
        return entries

    def _here_desks(self, session):
        char = session.char
        entries = []
        if self.family_desk_here(char):
            entries.append(("adopt", "here_adopt", {}))
        if self.wedding_desk_here(char):
            venue = self.venues()[0] if self.venues() else None
            hall = (self.world.locations[venue].get("aliases", {}).get("en") or [""])[0] if venue else ""
            tier = next(iter(self.wedding_rules().get("tiers") or {"simple": {}}))
            entries.append((f"book wedding {hall} {tier} neutral 14:00".replace("  ", " "), "here_book", {}))
        if self.wedding_desk_here(char) or self._loc(char).get("venue"):
            entries.append(("wedding schedule", "here_weddings", {}))
        if self._celebrating(self.room_of(char)) is not None:
            entries.append(("throw flowers", "here_flowers", {}))
        return entries

    def _here_contests(self, session):
        if not self.in_arena(session.char):
            return []
        entries = []
        others = self._others_here(session)
        if others:
            stake = min(DUEL_STAKE, int(self.duel_rules().get("max_stake", 100)))
            entries.append((f"duel {others[0].name} {stake}", "here_duel", {"name": others[0].name}))
        entries.append(("duels", "here_duels", {}))
        return entries

    def _here_crew(self, session):
        if not self.crew_room_here(session.char) or self.crew_of(session.char)[0] is None:
            return []
        return [("crew", "here_crew", {}), ("crew say hello", "here_crew_say", {}), ("crews", "here_crews", {})]

    def _here_work(self, session):
        char = session.char
        places = self.work_places(char["job"])
        if places is None or char["location"] not in places:
            return []
        return [("work", "here_work", {"job": self.world.job_name(char["job"])})]

    def _here_mission(self, session):
        char = session.char
        active = self._active_mission(char)
        if not active:
            return []
        mission = self.world.missions[active]
        have = char["inventory"].get(mission["item"], 0)
        entries = []
        if char["location"] == mission["from"] and have < mission["count"]:
            item = self.world.items[mission["item"]]
            entries.append((f"take {item['names']['en'][0]}", "here_take", {"things": item["many"]}))
        if char["location"] == mission["to"] and have >= mission["count"]:
            entries.append(("complete", "here_complete", {}))
        return entries

    def _here_cabin(self, session):
        char = session.char
        entries = []
        if self.party_here(char):
            entries.append(("host a party", "here_party", {}))
            friend = next((o for o in sorted(self.sessions.values(), key=lambda s: s.key)
                           if o is not session and o.conn is not None and not o.invisible), None)
            if friend is not None:
                entries.append((f"invite {friend.name}", "here_invite", {"name": friend.name}))
        if self.visit_here(char):
            for host in sorted(self.sessions.values(), key=lambda s: s.key):
                if host is not session and host.conn is not None and self.may_visit(session, host):
                    entries.append((f"visit {host.name}", "here_visit", {"name": host.name}))
        for obj in (self._loc(char).get("objects") or {}).values():
            if obj.get("capsule"):
                entries.append((f"open {obj['names']['en'][0]}", "here_open", {}))
        return entries

    def _here_social(self, session):
        """Furniture to sit or lie on, what lies about, something to put things on, the jukebox, the pond."""
        char = session.char
        entries = []
        seats = self.seats_here(session)
        sit = next((s for s, (_names, seat) in seats.items() if self._seat_allows(seat, "sit")), None)
        lie = next((s for s, (_names, seat) in seats.items() if self._seat_allows(seat, "lie")), None)
        if sit is not None:
            entries.append((f"sit on {seats[sit][0][0]}", "here_sit", {"at": self._seat_at(seats[sit][1], "sit")}))
        if lie is not None:
            entries.append((f"lie on {seats[lie][0][0]}", "here_lie", {"at": self._seat_at(seats[lie][1], "lie")}))
        room = self.room_of(char)
        piles = self.floor.get(room) or []
        if piles and not self.in_the_dark(char):
            entries.append((f"get {self.thing_word(piles[0]['id'])}", "here_get",
                            {"things": [self._count_of(p["id"], p["n"]) for p in piles]}))
        holders = self._holders(char["location"]) if not self._loc(char).get("airless") else {}
        mine = next((t for t in sorted(char["inventory"]) if char["inventory"][t] > 0 and self._tradeable(t)
                     and t not in self.worn(char).values()), None)
        if holders and mine:
            oid, obj = next(iter(holders.items()))
            at = self._holder_words(obj)
            entries.append((f"put {self.thing_word(mine)} {at.split(' ', 1)[0]} {obj['names']['en'][0]}", "here_put",
                            {"at": at}))
        books = [obj["names"]["en"][0] for obj in (self._loc(char).get("objects") or {}).values()
                 if obj.get("readable")]
        if books:
            entries.append((f"read {books[0]}", "here_read", {"things": books}))
        if self.jukebox_here(char):
            entries.append(("jukebox", "here_jukebox", {}))
        if self.fish_here(char):
            entries.append(("fish", "here_fish", {}))
        return entries

    def _here_events(self, session):
        """The events on in this room: what they scattered, a view, a gathering held here, the drone
        (an event on everywhere, like the station's birthday gift, is left to "events")."""
        char = session.char
        entries = []
        for action, cmd, key in (("collect", "collect", "here_event_collect"), ("watch", "watch", "here_event_watch"),
                                 ("join", "join", "here_event_join"), ("gift", "join", "here_event_join"),
                                 ("boss", "fix drone", "here_fix")):
            for _row, definition in self.events_here(char, action):
                if definition.get("rooms") and cmd not in {e[0] for e in entries}:   # held here, not everywhere
                    entries.append((cmd, key, {"event": definition["name"]}))
        return entries

    def _here_residents(self, session):
        entries = []
        for nid in sorted(self.npcs_in(self.room_of(session.char)), key=self.npc_name):
            short = self.npc_short(nid)
            entries.append((f"talk to {short}", "here_talk", {"name": self.npc_name(nid)}))
            topic = self._first_topic(session, nid)
            if topic:
                entries.append((f"ask {short} about {topic}", "here_ask", {"name": self.npc_name(nid)}))
        return entries

    def _first_topic(self, session, nid):
        memory = self.store.npc_memory(nid, session.char["id"])
        open_, _locked = self._topics_open(nid, memory)
        talkable = [t for t in open_ if not self.npc_defs[nid]["topics"][t].get("favour")] or open_
        return self._topic_label(nid, talkable[0], session.lang) if talkable else None

    def _here_things(self, session):
        char = session.char
        objects = [o["names"]["en"][0] for o in (self._loc(char).get("objects") or {}).values()]
        entries = []
        if objects:
            entries.append((f"look at {objects[0]}", "here_look" if len(objects) > 1 else "here_look_one",
                            {"things": objects}))
        residents = sorted(self.npcs_in(self.room_of(char)), key=self.npc_name)
        others = self._others_here(session)
        example = self.npc_short(residents[0]) if residents else others[0].name if others else \
            objects[0] if objects else None
        if example:
            entries.append((f"x {example}", "here_x", {}))
        return entries

    # --- what can be done with someone or something ---------------------------------------------

    def examine_target(self, session, text):
        """(title, entries) for "x" and a name, or None when there's nothing by that name."""
        lang, char = session.lang, session.char
        key = orbit_safety.name_key(text)
        if key in SELF_WORDS:
            return self.render(lang, "here_with_self"), self._self_actions(session)
        dark = self.in_the_dark(char)
        if not dark:
            other = self._find_near(session, text)
            if other is not None:
                return self.render(lang, "here_with", name=other.name), self._player_actions(session, other)
            nid = self.npc_here(session, text)
            if nid is not None:
                return self.render(lang, "here_with", name=self.npc_name(nid)), self._resident_actions(session, nid)
            found = self._companion_actions(session, text)
            if found is not None:
                return found
            found = self._object_named(session, text, fuzzy=False) or self._pile_actions(session, text)
            if found is not None:
                return found
            creature, _here = self.creature_here(char, text)
            if creature is not None:
                info = self.econ["creatures"][creature]
                word = info["names"]["en"][0]
                return self.render(lang, "here_with", name=f"the {word}"), [
                    (f"face {word}", "here_t_face", {}), (f"look at {word}", "here_t_look_thing", {})]
        tid = self.find_owned(char, text)
        if tid is not None and self.world.things[tid].get("type") != "pet":
            return self.render(lang, "here_with_yours", thing=self.world.things[tid]["one"]), \
                self._owned_actions(session, tid)
        sid, shop = self.shop_here(char)
        found = self.world.find_thing(text)
        if shop is not None and found in shop.get("stock", []):
            word = self.thing_word(found)
            return self.render(lang, "here_with", name=f"the {pick(self.world.things[found]['one'])}"), [
                (f"buy {word}", "here_t_buy", {}), (f"look at {word}", "here_t_look_thing", {})]
        market = self.market_here(char)
        gid = self.world.find_good(text)
        if market is not None and gid is not None and gid in market["buys"] | market["sells"]:
            word = self.good_word(gid)["en"]
            entries = []
            if gid in market["sells"]:
                entries.append((f"buy 2 {word}", "here_t_buy", {}))
            if gid in market["buys"]:
                entries.append((f"sell 2 {word}", "here_t_sell", {}))
            entries.append((f"prices {word}", "here_t_prices", {}))
            return self.render(lang, "here_with", name=word), entries
        found = None if dark else self._object_named(session, text, fuzzy=True)     # "x jukeboxes"
        if found is not None:
            return found
        lid = self.world.find_location(text)
        if lid is not None and lid != char["location"] and not self.world.locations[lid].get("hidden"):
            name = self.world.locations[lid]["name"]
            return self.render(lang, "here_with", name=self.world.locations[lid]["ref"]), [
                (f"way to {pick(name)}", "here_t_way", {}), (f"guide me to {pick(name)}", "here_t_guide", {})]
        return None

    def _object_named(self, session, text, fuzzy):
        """(title, entries) for a thing in the room that `text` names, or None."""
        _oid, obj = self.world.find_object(session.char["location"], text, fuzzy)
        if obj is None:
            return None
        return self.render(session.lang, "here_with", name=f"the {obj['names']['en'][0]}"), \
            self._object_actions(session, obj)

    def _self_actions(self, session):
        return [("profile", "here_t_profile_self", {}), ("inventory", "here_t_inventory", {}),
                ("rank", "here_t_rank", {}), ("describe me a tall pilot with a red scarf", "here_t_describe", {}),
                ("my voice 3", "here_t_voice", {}), ("achievements", "here_t_achievements", {})]

    def _player_actions(self, session, other):
        char, name = session.char, other.name
        entries = [(f"look at {name}", "here_t_look_player", {}), (f"whisper {name} hello", "here_t_whisper", {}),
                   (f"give {name} 10 credits", "here_t_give", {}), (f"wave at {name}", "here_t_gesture", {}),
                   (f"offer {name} 2 coffee for 30 credits", "here_t_offer", {}),
                   (f"profile {name}", "here_t_profile", {})]
        if other.key in (char["stats"].get("friends") or []):
            entries.append((f"remove friend {name}", "here_t_friend_remove", {}))
        else:
            entries.append((f"add friend {name}", "here_t_friend_add", {}))
        entries.append((f"invite {name}", "here_t_invite", {}))
        if other.leader is None and session.leader is None and not self.followers_of(session):
            entries.append((f"follow {name}", "here_t_follow", {"name": name}))
        if (self.pose_of(other) or {}).get("kind") == "sleep":
            entries.append((f"wake {name}", "here_t_wake", {}))
        if self.casino_here(char):
            flip = self.econ["casino"]["coinflip"]
            entries.append((f"challenge {name} {max(int(flip['min']), min(int(flip['max']), BET))}",
                            "here_challenge", {"name": name}))
        if self.in_arena(char):
            entries.append((f"duel {name} {min(DUEL_STAKE, int(self.duel_rules().get('max_stake', 100)))}",
                            "here_duel", {"name": name}))
        crew, role = self.crew_of(char)
        if crew is not None and role == "captain" and self.crew_of(other.char)[0] is None:
            entries.append((f"crew invite {name}", "here_t_crew_invite", {}))
        mine, partner_id = self.partner_of(char)
        theirs, _other = self.partner_of(other.char)
        if mine is None and theirs is None:
            entries.append((f"partner with {name}", "here_t_partner", {}))
        elif mine is not None and partner_id == other.char["id"] and mine["status"] == "partners" and \
                self._best_ring(char):
            entries.append((f"propose to {name}", "here_t_propose", {}))
        wedding = self.upcoming_wedding(char)
        if wedding is not None and partner_id != other.char["id"]:
            entries.append((f"invite {name} to the wedding", "here_t_wedding_invite", {}))
        return entries

    def _resident_actions(self, session, nid):
        short = self.npc_short(nid)
        d = self.npc_defs[nid]
        memory = self.store.npc_memory(nid, session.char["id"])
        open_, _locked = self._topics_open(nid, memory)
        topics = [self._topic_label(nid, t, session.lang) for t in open_]
        entries = [(f"talk to {short}", "here_t_talk", {})]
        if topics:
            entries.append((f"ask {short} about {topics[0]}", "here_t_ask", {"topics": topics}))
        entries.append((f"greet {short}", "here_t_greet", {}))
        likes = [t for t in d.get("likes", []) if t in self.world.things]
        if likes:
            entries.append((f"give {short} {self.thing_word(likes[0])}", "here_t_gift", {}))
        entries.append((f"wave to {short}", "here_t_gesture", {}))
        sid, shop = self.shop_here(session.char)
        if shop is not None and d.get("shop") == sid:
            entries.append(("list", "here_t_shop", {"name": self.npc_name(nid)}))
        entries.append((f"look at {short}", "here_t_look_resident", {}))
        return entries

    def _companion_actions(self, session, text):
        """(title, entries) for your pet or child here that `text` names, or someone else's; else None."""
        lang, char = session.lang, session.char
        key = orbit_safety.name_key(text)
        for child in self.children_of(char):
            if child["name"] and orbit_safety.name_key(child["name"]) == key:
                name = child["name"]
                return self.render(lang, "here_with", name=name), [
                    (f"feed {name}", "here_t_feed", {}), (f"play with {name}", "here_t_play", {}),
                    (f"rest {name}", "here_t_rest", {}), (f"read a story to {name}", "here_t_story", {}),
                    (f"bring {name}", "here_t_bring", {}), (f"ask {name} for help", "here_t_fetch", {}),
                    ("family", "here_t_family", {})]
        for comp in self.pets_of(char):
            if orbit_safety.name_key(comp["name"]) == key:
                name = comp["name"]
                return self.render(lang, "here_with", name=name), [
                    (f"feed {name}", "here_t_pet_feed", {}), (f"play with {name}", "here_t_play", {}),
                    (f"rest {name}", "here_t_rest", {}), ("pat", "here_t_pat", {}),
                    (f"pet status {name}", "here_t_pet_status", {}), ("teach trick sit", "here_t_teach", {}),
                    (f"look at {name}", "here_t_look_thing", {})]
        for owner in self._others_here(session):
            names = [c["name"] for c in self.children_of(owner.char) if c["name"]] + \
                [c["name"] for c in self.pets_of(owner.char)]
            for name in names:
                if orbit_safety.name_key(name) == key:
                    return self.render(lang, "here_with", name=name), [
                        (f"look at {name}", "here_t_look_thing", {}), (f"wave to {name}", "here_t_gesture", {})]
        return None

    def _object_actions(self, session, obj):
        word = obj["names"]["en"][0]
        entries = [(f"look at {word}", "here_t_look_thing", {})]
        seat = obj.get("seat")
        if seat and self._seat_allows(seat, "sit"):
            entries.append((f"sit on {word}", "here_t_sit", {}))
        if seat and self._seat_allows(seat, "lie"):
            entries.append((f"lie on {word}", "here_t_lie", {}))
        if obj.get("readable"):
            entries.append((f"read {word}", "here_t_read", {}))
        if obj.get("jukebox"):
            entries.append(("jukebox", "here_jukebox", {}))
        if obj.get("fishing"):
            entries.append(("fish", "here_fish", {}))
        if obj.get("capsule"):
            entries.append((f"open {word}", "here_open", {}))
        if obj.get("farm") and self.farm_here(session.char):
            entries.extend(e for e in self._here_farm(session) if e[0] != "farm")
        if obj.get("lanterns") and self.temple_here(session.char):
            entries.append(("light a lantern", "here_lantern", {}))
        if obj.get("worlds"):
            entries.append(("worlds", "here_worlds", {}))
        if obj.get("markets"):
            entries.append(("prices", "here_t_markets", {}))
        if obj.get("arcade") and self.at_cabinets(session.char):
            entries.extend(e for e in self._here_arcade(session) if e[0] != "arcade")
        return entries

    def _owned_actions(self, session, tid):
        char = session.char
        thing = self.world.things[tid]
        effects = thing.get("effects") or {}
        word = self.thing_word(tid)
        entries = [(f"look at {word}", "here_t_look_thing", {})]
        if thing.get("slot"):
            if tid in self.worn(char).values():
                entries.append((f"remove {word}", "here_t_remove", {}))
            else:
                entries.append((f"wear {word}", "here_t_wear", {}))
        elif effects.get("beacon"):
            entries.append(("place beacon", "here_t_beacon", {}))
        elif effects.get("compass"):
            entries.append(("compass", "here_t_compass", {}))
        elif effects.get("mapper"):
            entries.append(("map", "here_t_map", {}))
        elif effects.get("scanner"):
            entries.append(("scan", "here_t_scan", {}))
        elif effects.get("comm"):
            entries.append(("friends", "here_t_friends", {}))
        elif effects.get("pet_food"):
            entries.append(("feed pet", "here_t_feed_pet", {}))
        elif thing["type"] == "consumable":
            entries.append((f"use {word}", "here_t_eat", {}))
        others = self._others_here(session)
        if effects.get("ring") and others:
            entries.append((f"propose to {others[0].name}", "here_t_ring", {"name": others[0].name}))
        crop = next((c for c in self.world.crops.values() if c["seed"] == tid), None)
        if crop is not None:
            if self.farm_here(char):
                entries.append((f"plant {self.good_word(crop['good'])['en']}", "here_t_plant", {}))
            else:
                farm = next((lid for lid, loc in self.world.locations.items() if loc.get("farm")), None)
                if farm:
                    entries.append((f"way to {pick(self.world.locations[farm]['name'])}", "here_t_plant_there", {}))
        if tid == "arcade_token" and self.at_cabinets(char):
            entries.extend(e for e in self._here_arcade(session) if e[0].startswith("play "))
        if tid in self.world.goods:
            market = self.market_here(char)
            if market is not None and tid in market["buys"]:
                entries.append((f"sell {char['inventory'].get(tid, 1)} {word}", "here_t_sell", {}))
            else:
                entries.append((f"prices {word}", "here_t_sell_where", {}))
        elif self.pawn_value(tid) and self.pawn_here(char):
            entries.append((f"sell {word}", "here_t_sell", {}))
        if others and self._tradeable(tid):
            entries.append((f"give {others[0].name} 1 {word}", "here_t_give_thing", {"name": others[0].name}))
        return entries

    def _pile_actions(self, session, text):
        """(title, entries) for something put down here that `text` names, or None."""
        pile = self._pile_named(self.room_of(session.char), text, anywhere=True)
        if pile is None:
            return None
        word = self.thing_word(pile["id"])
        return self.render(session.lang, "here_with", name=f"the {pick(self.world.things[pile['id']]['one'])}"), [
            (f"get {word}", "here_t_get", {}), (f"look at {word}", "here_t_look_thing", {})]
