# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Weddings (economy.json "weddings"): festive, and only ever with both
players' yes.

  propose to Sam                           with a ring from Starglint Jewellers, in the same room;
                                           Sam says accept (engaged) or decline (the ring stays yours)
  book wedding pavilion grand neutral 14:00
                                           at the jeweller's wedding desk: a hall, a tier, a ceremony
                                           and a time (station time, UTC; "tomorrow 14:00", "2026-10-03 14:00")
  wedding                                  yours: when, where, who's coming
  invite Sam to the wedding
  rsvp yes, rsvp no                        a guest's answer (and "invitations")
  wedding schedule                         the weddings to come
  cancel wedding                           money back if early enough
  throw flowers                            (and cheer, clap) as a guest
  vow ...                                  your own words, in the ceremony
  join the lights, yes, sign               in the ceremony
  read memory                              the memory of your wedding (or one you went to)

The halls are the rooms marked "venue" in world.json (the Star Dome Hall,
the Jasmine Pavilion, the castle's Great Hall in Evergrove), one wedding an
hour each. The tiers (simple, grand, luxurious) cost more and give more:
richer decorations, music, the celebration's ambience for clients that have
it, and fireworks for the whole station.

Two ceremonies. The Starlight rite of the Way of Starlight, led by the
temple's keeper: each partner lights a lantern, the two lights are brought
together into one, a moment of silence, the vows the two write themselves,
and the star bell three times. Or a neutral ceremony, led by the jeweller
as the station's registrar: the vows, each partner's yes, and their
signatures in the register. Neither borrows words, names or symbols from
any real faith's rites.

The ceremony waits for both partners at the hall, a little while; without
them it is missed. A "no" stops it kindly. Afterwards: the station hears
the news, the couple get a title and a keepsake, and a memory of the day is
kept (who came, their vows, the flowers and cheers), which the couple and
their guests can read. A character can marry again only after a while;
cancelling early gives the money back, admins can cancel any wedding (all
of it back). Everything is in the database (weddings, wedding_guests), so a
restart carries on.
"""

import datetime
import logging
import re

import orbit_safety
from orbit_lang import LANGUAGES, pick

logger = logging.getLogger("orbit.game")

WEDDING_DEFAULTS = {
    "tiers": {"simple": {"price": 1000, "guests": 10}, "grand": {"price": 4000, "guests": 30, "ambience": True},
              "luxurious": {"price": 10000, "guests": 60, "ambience": True, "fireworks": True}},
    "slot_minutes": 60, "length_minutes": 45, "lead_minutes": 10, "ahead_days": 14, "remind_minutes": 10,
    "wait_minutes": 20, "cooldown_days": 7, "refund": [[86400, 1.0], [3600, 0.5]], "missed_refund": 0.5,
    "ask_seconds": 120, "snub_seconds": 600, "vow_limit": 300, "vow_seconds": 180, "lantern_seconds": 90,
    "join_seconds": 60, "consent_seconds": 180, "sign_seconds": 180, "flowers_seconds": 15,
    "officiants": {"starlight": "sekar", "neutral": "safira"},
    "titles": {"starlight": "title_starlit", "neutral": "title_wedded"},
    "keepsakes": {"starlight": "keepsake_lantern", "neutral": "keepsake_star"},
}
TIER_WORDS = {"simple": ("simple", "basic", "small"), "grand": ("grand", "big"),
              "luxurious": ("luxurious", "luxury", "deluxe", "lux")}
STYLE_WORDS = {"starlight": ("starlight", "way of starlight", "the way of starlight", "starlight rite",
                             "lantern", "lanterns"),
               "neutral": ("neutral", "civil", "registrar")}
TOMORROW = ("tomorrow",)
UPCOMING = ("booked", "waiting", "ceremony")
_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_TIME = re.compile(r"(\d{1,2})[:.](\d{2})")


class WeddingsMixin:
    @staticmethod
    def commands():
        return {"wedding": WeddingsMixin.cmd_wedding}

    def init_weddings(self):
        self._rsvp_note = set()

    def wedding_rules(self):
        rules = dict(WEDDING_DEFAULTS)
        rules.update(self.econ.get("weddings") or {})
        return rules

    def venues(self):
        return [lid for lid, loc in self.world.locations.items() if loc.get("venue")]

    def _tier_name(self, lang, tier):
        return self.render(lang, f"wedding_tier_{tier}")

    def _style_name(self, lang, style):
        return self.render(lang, f"wedding_style_{style}")

    def _when_text(self, lang, at):
        when = datetime.datetime.fromtimestamp(float(at), datetime.timezone.utc)
        return self.render(lang, "wedding_when", day=self.render(lang, f"weekday_{when.weekday()}"),
                           date=when.strftime("%d-%m-%Y"), hour=when.strftime("%H:%M"))

    def _couple(self, wedding):
        p = self.store.partnership_by_id(wedding["partnership"])
        return p, (p["a"], p["b"]) if p else (None, None)

    def _is_couple(self, char, wedding):
        _p, ids = self._couple(wedding)
        return char["id"] in ids

    def upcoming_wedding(self, char):
        """Your wedding still to come (booked, waiting or under way), or None."""
        p, _other = self.partner_of(char)
        if p is None:
            return None
        found = self.store.weddings_of_partnership(p["id"], UPCOMING)
        return found[0] if found else None

    def wedding_in(self, room, statuses=("ceremony",)):
        for wedding in self.store.weddings_with(list(statuses)):
            if wedding["venue"] == room:
                return wedding
        return None

    def _celebrating(self, room):
        """A wedding being celebrated in `room` now (the ceremony, or the reception after), or None."""
        if not self.world.locations.get(room, {}).get("venue"):
            return None
        found = self.store.celebrations(self.now(), venue=room)
        return found[0] if found else None

    # --- the command --------------------------------------------------------------------------

    def cmd_wedding(self, session, message):
        op = self._arg(message, "op", 20) or "status"
        handler = {"status": self._wedding_status, "book": self._wedding_book, "cancel": self._wedding_cancel,
                   "schedule": self._wedding_schedule, "invite": self._wedding_invite,
                   "invitations": self._wedding_invitations, "rsvp_yes": self._wedding_rsvp,
                   "rsvp_no": self._wedding_rsvp, "flowers": self._wedding_flowers, "vow": self._wedding_vow,
                   "join": self._wedding_join, "yes": self._wedding_yes, "no": self._wedding_no,
                   "sign": self._wedding_sign, "memory": self._wedding_memory, "propose": self._wedding_propose
                   }.get(op, self._wedding_status)
        handler(session, message)

    # --- proposing ------------------------------------------------------------------------------

    def _best_ring(self, char, text=""):
        if text:
            tid = self.world.find_thing(text)
            if tid and (self.world.things[tid].get("effects") or {}).get("ring") and self.owns(char, tid):
                return tid
        rings = [(int((self.world.things[t].get("effects") or {}).get("ring", 0)), t) for t, n in char["inventory"].items()
                 if n and (self.world.things.get(t, {}).get("effects") or {}).get("ring")]
        return max(rings)[1] if rings else None

    def _wedding_propose(self, session, message):
        char = session.char
        rules = self.wedding_rules()
        if self._muted(session):
            return
        words = self._arg(message, "to", 80).split()
        name = words[0] if words else ""
        rest = " ".join(w for w in words[1:] if w.lower() not in ("with", "using", "a", "the"))
        target = self._find_near(session, name) if name else None
        if target is None:
            other = self._find_session(name) if name else None
            self._error(session, "propose_not_here" if other else "not_here", name=other.name if other else name or "?")
            return
        if target is session:
            self._error(session, "partner_self")
            return
        ring = self._best_ring(char, rest)
        if ring is None:
            self._error(session, "propose_no_ring")
            return
        mine, other_id = self.partner_of(char)
        if mine is not None and other_id != target.char["id"]:
            self._error(session, "partner_have", name=self._partner_name(other_id))
            return
        if mine is not None and mine["status"] in ("engaged", "married"):
            self._error(session, f"propose_already_{mine['status']}", name=target.name)
            return
        theirs, their_other = self.partner_of(target.char)
        if theirs is not None and their_other != char["id"]:
            self._error(session, "partner_they_have", name=target.name)
            return
        for who in (char, target.char):
            last = self.store.last_wedding_of(who["id"])
            wait = last + float(rules["cooldown_days"]) * 86400 - self.now()
            if last and wait > 0:
                self._error(session, "wedding_cooldown", name=who["name"], time=self._duration(session.lang, wait))
                return
        snub = (char["stats"].get("family_snubs") or {}).get(target.key)
        if snub and float(snub) > self.now():
            self._error(session, "partner_snubbed", name=target.name,
                        time=self._duration(session.lang, float(snub) - self.now()))
            return
        if not self._slow(session):
            return
        now = self.now()
        self.family_asks[target.key] = {"kind": "ring", "from": session.key, "from_name": session.name, "at": now,
                                        "expires": now + float(rules["ask_seconds"]), "ring": ring,
                                        "room": char["location"]}
        self._send(target, "offer", "propose_asked", extra={"actor": session.name, "ask": "ring", "sound": "ring"},
                   name=session.name, ring=self.world.things[ring]["one"])
        self._info(session, "propose_sent", name=target.name, ring=self.world.things[ring]["one"])
        for other in self._in_room(self.room_of(char), exclude=(session, target)):
            self._send(other, "emote", "propose_other", extra={"actor": session.name, "sound": "ring"},
                       actor=session.name, name=target.name)

    def _accept_ring(self, session, ask):
        other = self.sessions.get(ask["from"])
        if other is None or other.conn is None or other.char["location"] != session.char["location"]:
            self._error(session, "partner_gone", name=ask["from_name"])
            return
        ring = ask["ring"]
        if not self.owns(other.char, ring):
            self._error(session, "propose_ring_gone", name=other.name)
            return
        mine, other_id = self.partner_of(session.char)
        if mine is not None and other_id != other.char["id"]:
            self._error(session, "partner_have", name=self._partner_name(other_id))
            return
        now = self.now()
        with self.store.transaction():
            self._hand_over(other.char, session.char, (ring, 1))
            self.worn(session.char)["hand"] = ring
            p, _o = self.partner_of(other.char)
            if p is None:
                self.store.add_partnership(session.char["id"], other.char["id"], "engaged", now)
            else:
                p["status"], p["engaged"] = "engaged", now
                self.store.save_partnership(p)
            self.store.save_all([other.char, session.char])
        logger.info("%s and %s are engaged", other.name, session.name)
        thing = self.world.things[ring]["one"]
        self._send(session, "paid", "propose_yes_you", name=other.name, ring=thing, extra={"sound": "ring"})
        self._send(other, "paid", "propose_yes_them", name=session.name, ring=thing, extra={"sound": "ring"})
        for watcher in self._in_room(self.room_of(session.char), exclude=(session, other)):
            self._send(watcher, "emote", "propose_yes_other", extra={"sound": "emote_cheer"}, a=other.name,
                       b=session.name, ring=thing)

    # --- booking ----------------------------------------------------------------------------------

    def parse_booking(self, text, now):
        """{"venue", "tier", "style", "starts"} from what was typed (each None when missing), and a
        problem key when the time can't be read."""
        norm = " ".join(str(text or "").lower().split())
        found = {"venue": None, "tier": None, "style": None, "starts": None}
        problem = None
        day = None
        m = _DATE.search(norm)
        if m:
            try:
                day = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                problem = "wedding_bad_time"
            norm = norm[:m.start()] + " " + norm[m.end():]
        t = _TIME.search(norm)
        tomorrow = any(w in norm.split() for w in TOMORROW)
        if t:
            hour, minute = int(t.group(1)), int(t.group(2))
            norm = norm[:t.start()] + " " + norm[t.end():]
            if hour > 23 or minute > 59:
                problem = "wedding_bad_time"
            elif problem is None:
                today = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).date()
                base = day or (today + datetime.timedelta(days=1) if tomorrow else today)
                starts = datetime.datetime(base.year, base.month, base.day, hour, minute,
                                           tzinfo=datetime.timezone.utc).timestamp()
                if day is None and not tomorrow and starts <= now:
                    starts += 86400
                found["starts"] = starts
        words = [w for w in norm.split() if w not in TOMORROW and w not in ("at", "on", "the")]
        rest = " ".join(words)
        for style, phrases in STYLE_WORDS.items():
            for phrase in sorted(phrases, key=len, reverse=True):
                if f" {phrase} " in f" {rest} ":
                    found["style"] = style
                    rest = f" {rest} ".replace(f" {phrase} ", " ").strip()
                    break
            if found["style"]:
                break
        kept = []
        for word in rest.split():
            tier = next((tr for tr, names in TIER_WORDS.items() if word in names), None)
            if tier and not found["tier"]:
                found["tier"] = tier
            else:
                kept.append(word)
        venue = self.world.find_location(" ".join(kept)) if kept else None
        if venue in self.venues():
            found["venue"] = venue
        return found, problem

    def _wedding_book(self, session, message):
        char, lang = session.char, session.lang
        rules = self.wedding_rules()
        if not self._loc(char).get("wedding_desk"):
            desk = next((lid for lid, loc in self.world.locations.items() if loc.get("wedding_desk")), None)
            self._error(session, "wedding_book_where", where=self.world.locations[desk]["in"] if desk else "?")
            return
        p, other_id = self.partner_of(char)
        if p is None or p["status"] != "engaged":
            self._error(session, "wedding_not_engaged" if p is None or p["status"] == "partners"
                        else "wedding_already_married")
            return
        if self.store.weddings_of_partnership(p["id"], UPCOMING):
            self._error(session, "wedding_already_booked")
            return
        for char_id in (p["a"], p["b"]):
            last = self.store.last_wedding_of(char_id)
            wait = last + float(rules["cooldown_days"]) * 86400 - self.now()
            if last and wait > 0:
                self._error(session, "wedding_cooldown", name=self._partner_name(char_id), time=self._duration(lang, wait))
                return
        now = self.now()
        found, problem = self.parse_booking(self._arg(message, "a", 200), now)
        tiers = rules["tiers"]
        if problem or not all(found.values()):
            self._error(session, problem or "wedding_book_how",
                        venues=[self.world.locations[v]["ref"] for v in self.venues()],
                        tiers=[self.render(lang, "wedding_tier_price", tier=self._tier_name(lang, t),
                                           price=int(tiers[t]["price"])) for t in tiers])
            return
        starts = found["starts"]
        if starts < now + float(rules["lead_minutes"]) * 60 or starts > now + float(rules["ahead_days"]) * 86400:
            self._error(session, "wedding_time_range", lead=int(rules["lead_minutes"]), days=int(rules["ahead_days"]))
            return
        slot = float(rules["slot_minutes"]) * 60
        clash = [w for w in self.store.weddings_with(list(UPCOMING))
                 if w["venue"] == found["venue"] and abs(float(w["starts"]) - starts) < slot]
        if clash:
            self._error(session, "wedding_venue_taken", place=self.world.locations[found["venue"]]["ref"],
                        when=self._when_text(lang, clash[0]["starts"]))
            return
        price = int(tiers[found["tier"]]["price"])
        if char["credits"] < price:
            self._error(session, "buy_poor", total=price, credits=char["credits"])
            return
        with self.store.transaction():
            self.spend(char, price, "weddings")
            self._save(session)
            wedding = self.store.add_wedding(p["id"], found["venue"], found["tier"], found["style"], starts,
                                             starts + float(rules["length_minutes"]) * 60, char["id"], price)
        logger.info("%s booked a wedding at %s", session.name, found["venue"])
        params = dict(place=self.world.locations[found["venue"]]["ref"], when=self._when_text(lang, starts),
                      tier=self._tier_name(lang, found["tier"]), style=self._style_name(lang, found["style"]),
                      price=price, credits=char["credits"])
        self._send(session, "paid", "wedding_booked", extra={"sound": "register"}, **params)
        stored = self.store.by_id(other_id)
        partner = self.sessions.get(stored["name_key"]) if stored else None
        if partner is not None and partner.conn is not None:
            self._send(partner, "system", "wedding_booked_partner", name=session.name,
                       place=self.world.locations[found["venue"]]["ref"], when=self._when_text(partner.lang, starts),
                       tier=self._tier_name(partner.lang, found["tier"]),
                       style=self._style_name(partner.lang, found["style"]))
        return wedding

    def _refund_share(self, wedding, now):
        before = float(wedding["starts"]) - now
        for seconds, share in self.wedding_rules()["refund"]:
            if before >= float(seconds):
                return float(share)
        return 0.0

    def _wedding_cancel(self, session, message):
        name = self._arg(message, "to", 40)
        if name and self.is_admin(session):
            self._admin_wedding_cancel(session, name)
            return
        wedding = self.upcoming_wedding(session.char)
        if wedding is None or wedding["status"] != "booked":
            self._error(session, "wedding_none_to_cancel")
            return
        share = self._refund_share(wedding, self.now())
        refund = self.cancel_wedding(wedding, share, "cancelled")
        self._info(session, "wedding_cancelled_you", n=refund)

    def cancel_wedding(self, wedding, share, status, notify=True):
        """Ends a wedding that hasn't happened: `share` of what was paid goes back to whoever paid."""
        refund = int(round(int(wedding["paid"]) * share))
        payer = self._char_by_key(self.store.by_id(wedding["booked_by"])["name_key"]) \
            if self.store.by_id(wedding["booked_by"]) else None
        with self.store.transaction():
            if refund and payer is not None:
                self.earn(payer, refund, "weddings")
                self.store.save(payer)
            wedding["status"] = status
            wedding["refunded"] = refund
            self.store.save_wedding(wedding)
        logger.info("the wedding %s was %s (%s back)", wedding["id"], status, refund)
        if notify:
            a, b = self._couple_names(wedding)
            for guest in self.store.guests_of(wedding["id"]):
                s = self.sessions.get(guest["name_key"])
                if s is not None and s.conn is not None:
                    self._send(s, "system", "wedding_cancelled_guest", a=a, b=b)
            _p, ids = self._couple(wedding)
            for char_id in ids:
                stored = self.store.by_id(char_id)
                s = self.sessions.get(stored["name_key"]) if stored else None
                if s is not None and s.conn is not None:
                    self._send(s, "system", f"wedding_{status}_couple", n=refund)
        return refund

    def weddings_partnership_ended(self, p):
        """A partnership ended: a wedding still to come is cancelled (money back as if cancelled now)."""
        for wedding in self.store.weddings_of_partnership(p["id"], UPCOMING):
            self.cancel_wedding(wedding, self._refund_share(wedding, self.now()), "cancelled", notify=False)

    def _admin_wedding_cancel(self, session, name):
        char = self._char_by_key(orbit_safety.name_key(name))
        wedding = self.upcoming_wedding(char) if char else None
        if wedding is None:
            self._error(session, "wedding_none_for", name=name)
            return
        refund = self.cancel_wedding(wedding, 1.0, "cancelled")
        self._log(session, "cancel wedding", char["name"], refund)
        self._info(session, "wedding_admin_cancelled", name=char["name"], n=refund)

    # --- what's on ---------------------------------------------------------------------------------

    def _wedding_status(self, session, message):
        char, lang = session.char, session.lang
        p, other_id = self.partner_of(char)
        wedding = self.upcoming_wedding(char)
        if wedding is not None:
            guests = self.store.guests_of(wedding["id"])
            coming = [g["name"] for g in guests if g["rsvp"] == "yes"]
            self._info(session, "wedding_yours", name=self._partner_name(other_id),
                       place=self.world.locations[wedding["venue"]]["ref"], when=self._when_text(lang, wedding["starts"]),
                       tier=self._tier_name(lang, wedding["tier"]), style=self._style_name(lang, wedding["style"]),
                       invited=len(guests), coming=coming or [self.render(lang, "nobody")],
                       left=self._duration(lang, max(1, float(wedding["starts"]) - self.now())))
            return
        if p is None:
            self._info(session, "wedding_how_propose")
        elif p["status"] == "partners":
            self._info(session, "wedding_how_propose_partner", name=self._partner_name(other_id))
        elif p["status"] == "engaged":
            self._info(session, "wedding_how_book", name=self._partner_name(other_id))
        else:
            self._info(session, "wedding_married", name=self._partner_name(other_id))

    def _wedding_schedule(self, session, message):
        lang = session.lang
        now = self.now()
        entries = []
        for wedding in self.store.weddings_with(list(UPCOMING)):
            if float(wedding["starts"]) + 3600 < now:
                continue
            a, b = self._couple_names(wedding)
            entries.append(self.render(lang, "wedding_schedule_entry", a=a, b=b,
                                       place=self.world.locations[wedding["venue"]]["ref"],
                                       when=self._when_text(lang, wedding["starts"])))
        if not entries:
            self._info(session, "wedding_schedule_none")
            return
        self._info(session, "wedding_schedule", entries="\n".join(entries[:10]))

    # --- guests ---------------------------------------------------------------------------------------

    def _wedding_invite(self, session, message):
        char, lang = session.char, session.lang
        wedding = self.upcoming_wedding(char)
        if wedding is None:
            self._error(session, "wedding_none_to_invite")
            return
        name = self._arg(message, "to", 40)
        guest = self._char_by_key(orbit_safety.name_key(name)) if name else None
        if guest is None:
            self._error(session, "no_character", name=name or "?")
            return
        if self._is_couple(guest, wedding):
            self._error(session, "wedding_invite_couple")
            return
        limit = int(self.wedding_rules()["tiers"][wedding["tier"]].get("guests", 10))
        if len(self.store.guests_of(wedding["id"])) >= limit:
            self._error(session, "wedding_invite_full", n=limit)
            return
        if not self._slow(session):
            return
        if not self.store.add_guest(wedding["id"], guest["id"], self.now()):
            self._info(session, "wedding_invite_again", name=guest["name"])
            return
        self._info(session, "wedding_invite_sent", name=guest["name"])
        target = self.sessions.get(guest["name_key"])
        if target is not None and target.conn is not None:
            self._tell_invitation(target, wedding)

    def _tell_invitation(self, session, wedding):
        a, b = self._couple_names(wedding)
        self._send(session, "offer", "wedding_invited", extra={"sound": "offer", "event": "wedding"}, a=a, b=b,
                   place=self.world.locations[wedding["venue"]]["ref"], when=self._when_text(session.lang, wedding["starts"]))
        self.store.set_guest(wedding["id"], session.char["id"], told=1)

    def wedding_join_notes(self, session):
        """Invitations that came while you were away, told when you come back."""
        notes = []
        for wedding, _rsvp, told in self.store.invitations_of(session.char["id"]):
            if not told and wedding["status"] == "booked":
                a, b = self._couple_names(wedding)
                notes.append(self.render(session.lang, "wedding_invited", a=a, b=b,
                                         place=self.world.locations[wedding["venue"]]["ref"],
                                         when=self._when_text(session.lang, wedding["starts"])))
                self.store.set_guest(wedding["id"], session.char["id"], told=1)
        return notes

    def _invitation_for(self, session, name):
        invitations = [(w, r) for w, r, _t in self.store.invitations_of(session.char["id"]) if w["status"] == "booked"]
        if name:
            key = orbit_safety.name_key(name)
            invitations = [(w, r) for w, r in invitations
                           if key in {orbit_safety.name_key(n) for n in self._couple_names(w)}]
        return invitations[0] if invitations else (None, None)

    def _wedding_rsvp(self, session, message):
        yes = self._arg(message, "op", 20) == "rsvp_yes"
        wedding, _rsvp = self._invitation_for(session, self._arg(message, "to", 40))
        if wedding is None:
            self._error(session, "wedding_no_invitation")
            return
        self.store.set_guest(wedding["id"], session.char["id"], rsvp="yes" if yes else "no", told=1)
        a, b = self._couple_names(wedding)
        self._info(session, "wedding_rsvp_yes" if yes else "wedding_rsvp_no", a=a, b=b,
                   place=self.world.locations[wedding["venue"]]["ref"], when=self._when_text(session.lang, wedding["starts"]))
        _p, ids = self._couple(wedding)
        for char_id in ids:
            stored = self.store.by_id(char_id)
            s = self.sessions.get(stored["name_key"]) if stored else None
            if s is not None and s.conn is not None:
                self._send(s, "system", "wedding_rsvp_told_yes" if yes else "wedding_rsvp_told_no", name=session.name)

    def _wedding_invitations(self, session, message):
        lang = session.lang
        entries = []
        for wedding, rsvp, _told in self.store.invitations_of(session.char["id"]):
            if wedding["status"] != "booked":
                continue
            a, b = self._couple_names(wedding)
            entries.append(self.render(lang, "wedding_invitation_entry", a=a, b=b,
                                       place=self.world.locations[wedding["venue"]]["ref"],
                                       when=self._when_text(lang, wedding["starts"]),
                                       rsvp=self.render(lang, f"wedding_rsvp_is_{rsvp}")))
        if not entries:
            self._info(session, "wedding_invitations_none")
            return
        self._info(session, "wedding_invitations", entries="\n".join(entries))

    def _wedding_flowers(self, session, message):
        wedding = self._celebrating(self.room_of(session.char))
        if wedding is None:
            self._error(session, "wedding_flowers_when")
            return
        left = self._cooldown_left(session.char, "flowers")
        if left > 0 or not session.chat.take():
            self._error(session, "slow_down")
            return
        self._set_cooldown(session.char, "flowers", float(self.wedding_rules()["flowers_seconds"]))
        a, b = self._couple_names(wedding)
        wedding["state"]["flowers"] = int(wedding["state"].get("flowers") or 0) + 1
        self.store.save_wedding(wedding)
        self.note_room_chat(session)
        self._send(session, "emote", "wedding_flowers_you", a=a, b=b, extra={"sound": "flowers"})
        self._to_room(self.room_of(session.char), "emote", "wedding_flowers_other", exclude=(session,),
                      extra={"actor": session.name, "sound": "flowers"}, actor=session.name, a=a, b=b)

    def wedding_emote(self, session, eid):
        """A cheer or a clap at a wedding counts in its memory."""
        if eid not in ("cheer", "clap"):
            return
        wedding = self._celebrating(self.room_of(session.char))
        if wedding is not None:
            wedding["state"]["cheers"] = int(wedding["state"].get("cheers") or 0) + 1
            self.store.save_wedding(wedding)

    # --- the ceremony ---------------------------------------------------------------------------------

    def ceremony_room_for(self, nid, now):
        """Where an officiant must be now: at the hall from a little before a wedding they lead."""
        rules = self.wedding_rules()
        if nid not in rules["officiants"].values():
            return None
        before = float(rules["remind_minutes"]) * 60
        for wedding in self.store.weddings_with(list(UPCOMING)):
            if rules["officiants"].get(wedding["style"]) != nid:
                continue
            if float(wedding["starts"]) - before <= now:
                return wedding["venue"]
        return None

    def _officiant(self, wedding):
        return self.wedding_rules()["officiants"][wedding["style"]]

    def _hall(self, wedding):
        return self._in_room(wedding["venue"])

    def _couple_here(self, wedding):
        _p, ids = self._couple(wedding)
        here = {s.char["id"]: s for s in self._in_room(wedding["venue"]) if s.conn is not None}
        return [here.get(char_id) for char_id in ids]

    def _say(self, wedding, key, **params):
        a, b = self._couple_names(wedding)
        self.npc_say(self._hall(wedding), self._officiant(wedding),
                     {lang: self.texts.raw(lang, key) for lang in LANGUAGES}, a=a, b=b, **params)

    def _hall_emote(self, wedding, key, sound=None, **params):
        a, b = self._couple_names(wedding)
        for other in self._hall(wedding):
            self._send(other, "emote", key, extra={"sound": sound} if sound else None, a=a, b=b, **params)

    def _to_couple_and_guests(self, wedding, key, sound="offer"):
        a, b = self._couple_names(wedding)
        place = self.world.locations[wedding["venue"]]["ref"]
        _p, ids = self._couple(wedding)
        told = set()
        for char_id in ids:
            stored = self.store.by_id(char_id)
            s = self.sessions.get(stored["name_key"]) if stored else None
            if s is not None and s.conn is not None:
                self._send(s, "system", f"{key}_couple", a=a, b=b, place=place, extra={"sound": sound, "event": "wedding"})
                told.add(s.key)
        for guest in self.store.guests_of(wedding["id"]):
            s = self.sessions.get(guest["name_key"])
            if s is not None and s.conn is not None and s.key not in told and guest["rsvp"] != "no":
                self._send(s, "system", f"{key}_guest", a=a, b=b, place=place, extra={"sound": sound, "event": "wedding"})

    def tick_weddings(self, now):
        rules = self.wedding_rules()
        for wedding in self.store.weddings_with(list(UPCOMING)):
            state = wedding["state"]
            starts = float(wedding["starts"])
            if wedding["status"] == "booked":
                if not state.get("reminded") and now >= starts - float(rules["remind_minutes"]) * 60:
                    state["reminded"] = True
                    self.store.save_wedding(wedding)
                    self._to_couple_and_guests(wedding, "wedding_soon")
                if now >= starts:
                    wedding["status"] = "waiting"
                    self.store.save_wedding(wedding)
                    self._to_couple_and_guests(wedding, "wedding_now", sound="event_party")
            if wedding["status"] == "waiting":
                couple = self._couple_here(wedding)
                if all(couple):
                    self._start_ceremony(wedding, now)
                elif now >= starts + float(rules["wait_minutes"]) * 60:
                    self.cancel_wedding(wedding, float(rules["missed_refund"]), "missed")
            if wedding["status"] == "ceremony":
                self._tick_ceremony(wedding, now)
        for wedding in self.store.celebrations(now - 300):
            until = float(wedding["ends"])
            if wedding["status"] == "done" and not wedding["state"].get("closed") and now >= until:
                wedding["state"]["closed"] = True
                self.store.save_wedding(wedding)
                for other in self._hall(wedding):
                    self._send(other, "info", "wedding_reception_over", extra=self._where(other))

    def _start_ceremony(self, wedding, now):
        nid = self._officiant(wedding)
        if self.npcs[nid]["room"] != wedding["venue"]:
            old = self.npcs[nid]["room"]
            if old is not None:
                self._npc_vanish(nid, old)
            self.npcs[nid]["room"] = wedding["venue"]
            self._npc_appear(nid, wedding["venue"])
        wedding["status"] = "ceremony"
        wedding["state"].update(step="open", at=now, lit=[], vows={}, yes=[], signed=[], attended=[])
        self.store.save_wedding(wedding)
        a, b = self._couple_names(wedding)
        for other in self._hall(wedding):
            extra = dict(self._where(other), sound="wedding_music")
            self._send(other, "info", f"wedding_decor_{wedding['tier']}", extra=extra, a=a, b=b)
        logger.info("the wedding of %s and %s begins", a, b)

    def _next(self, wedding, step, now, delay=0.0):
        wedding["state"].update(step=step, at=now + delay, prompted=False)
        self.store.save_wedding(wedding)

    def _tick_ceremony(self, wedding, now):
        state = wedding["state"]
        rules = self.wedding_rules()
        if now < float(state.get("at", 0)):
            return
        couple = self._couple_here(wedding)
        for s in self._hall(wedding):
            if s.char["id"] not in state.setdefault("attended", []) and not self._is_couple(s.char, wedding):
                state["attended"].append(s.char["id"])
        if not all(couple):
            if now - float(state.get("away_since") or now) >= float(rules["wait_minutes"]) * 60:
                self._stop_ceremony(wedding, "stopped", float(rules["missed_refund"]))
                return
            if not state.get("away_since"):
                state["away_since"] = now
                self.store.save_wedding(wedding)
                self._hall_emote(wedding, "wedding_paused")
            return
        if state.get("away_since"):
            state.pop("away_since", None)
            self._hall_emote(wedding, "wedding_resumed")
        step = state.get("step")
        getattr(self, f"_step_{wedding['style']}")(wedding, step, now, couple)

    def _step_starlight(self, wedding, step, now, couple):
        state = wedding["state"]
        rules = self.wedding_rules()
        a_s, b_s = couple
        if step == "open":
            self._say(wedding, "sl_open")
            self._next(wedding, "gather", now, 6)
        elif step == "gather":
            self._say(wedding, "sl_gather")
            self._next(wedding, "lanterns", now, 6)
        elif step == "lanterns":
            if not state.get("prompted"):
                state["prompted"] = True
                state["since"] = now
                self.store.save_wedding(wedding)
                self._say(wedding, "sl_lanterns")
                return
            if len(state.get("lit", [])) >= 2 or now - float(state["since"]) >= float(rules["lantern_seconds"]):
                for s in (a_s, b_s):
                    if s.char["id"] not in state["lit"]:
                        state["lit"].append(s.char["id"])
                        self._hall_emote(wedding, "sl_lantern_helped", "lantern", name=s.name,
                                         keeper=self.npc_name(self._officiant(wedding)))
                self._next(wedding, "join", now, 3)
        elif step == "join":
            if not state.get("prompted"):
                state["prompted"] = True
                state["since"] = now
                self.store.save_wedding(wedding)
                self._say(wedding, "sl_join")
                return
            if state.get("joined") or now - float(state["since"]) >= float(rules["join_seconds"]):
                if not state.get("joined"):
                    self._join_lights(wedding, None)
                self._next(wedding, "silence", now, 4)
        elif step == "silence":
            self._hall_emote(wedding, "sl_silence")
            self._next(wedding, "vows", now, 10)
        elif step == "vows":
            self._vows_step(wedding, now, couple, "sl_vows", "bell")
        elif step == "bell":
            rung = int(state.get("rung") or 0) + 1
            state["rung"] = rung
            self._hall_emote(wedding, f"sl_bell_{rung}", "bell")
            if rung >= 3:
                self._next(wedding, "close", now, 4)
            else:
                self._next(wedding, "bell", now, 3)
        elif step == "close":
            self._say(wedding, "sl_close")
            self._finish(wedding, now)

    def _step_neutral(self, wedding, step, now, couple):
        state = wedding["state"]
        rules = self.wedding_rules()
        if step == "open":
            self._say(wedding, "nt_open")
            self._next(wedding, "vows", now, 6)
        elif step == "vows":
            self._vows_step(wedding, now, couple, "nt_vows", "consent")
        elif step == "consent":
            for s in couple:
                if s.char["id"] in state["yes"]:
                    continue
                if not state.get("prompted") or state.get("asking") != s.char["id"]:
                    other = couple[1] if s is couple[0] else couple[0]
                    state.update(prompted=True, asking=s.char["id"], since=now)
                    self.store.save_wedding(wedding)
                    self._say(wedding, "nt_ask", name=s.name, other=other.name)
                elif now - float(state["since"]) >= float(rules["consent_seconds"]):
                    self._stop_ceremony(wedding, "stopped", float(rules["missed_refund"]))
                return
            self._next(wedding, "sign", now, 3)
        elif step == "sign":
            if not state.get("prompted"):
                state.update(prompted=True, since=now)
                self.store.save_wedding(wedding)
                self._say(wedding, "nt_sign")
                return
            if len(state["signed"]) >= 2:
                self._next(wedding, "close", now, 3)
            elif now - float(state["since"]) >= float(rules["sign_seconds"]):
                self._stop_ceremony(wedding, "stopped", float(rules["missed_refund"]))
        elif step == "close":
            self._say(wedding, "nt_close")
            self._finish(wedding, now)

    def _vows_step(self, wedding, now, couple, key, then):
        state = wedding["state"]
        if not state.get("prompted"):
            state.update(prompted=True, since=now)
            self.store.save_wedding(wedding)
            self._say(wedding, key)
            for s in couple:
                self._send(s, "info", "wedding_vow_how")
            return
        if len(state["vows"]) >= 2 or now - float(state["since"]) >= float(self.wedding_rules()["vow_seconds"]):
            for s in couple:
                if str(s.char["id"]) not in state["vows"]:
                    self._hall_emote(wedding, "wedding_vow_silent", name=s.name)
            self._next(wedding, then, now, 3)

    def _stop_ceremony(self, wedding, status, share):
        self._hall_emote(wedding, f"wedding_{status}_hall")
        self.cancel_wedding(wedding, share, status)
        for other in self._hall(wedding):
            self._send(other, "info", "wedding_reception_over", extra=self._where(other))

    def _join_lights(self, wedding, session):
        """The two lanterns' lights brought together into one (by the couple, or the keeper's hands)."""
        state = wedding["state"]
        state["joined"] = True
        self.store.save_wedding(wedding)
        self._hall_emote(wedding, "sl_joined", "lanterns_join")

    def _my_ceremony(self, session, step=None):
        """The ceremony you're getting married in, here and now (at `step`), or None."""
        wedding = self.wedding_in(self.room_of(session.char))
        if wedding is None or not self._is_couple(session.char, wedding):
            return None
        if step is not None and wedding["state"].get("step") not in ((step,) if isinstance(step, str) else step):
            return None
        return wedding

    def wedding_lantern(self, session):
        """ "light lantern" in the Starlight rite: your lantern. True when it was that."""
        wedding = self._my_ceremony(session, "lanterns")
        if wedding is None or wedding["style"] != "starlight":
            return False
        lit = wedding["state"].setdefault("lit", [])
        if session.char["id"] in lit:
            self._info(session, "sl_lantern_already")
            return True
        lit.append(session.char["id"])
        self.store.save_wedding(wedding)
        self._hall_emote(wedding, "sl_lantern_lit", "lantern", name=session.name)
        return True

    def _wedding_join(self, session, message):
        wedding = self._my_ceremony(session, "join")
        if wedding is None or wedding["style"] != "starlight" or not wedding["state"].get("prompted"):
            self._error(session, "wedding_not_now")
            return
        if not wedding["state"].get("joined"):
            self._join_lights(wedding, session)

    def _wedding_vow(self, session, message):
        wedding = self._my_ceremony(session, "vows")
        if wedding is None or not wedding["state"].get("prompted"):
            self._error(session, "wedding_not_now")
            return
        words = self._chat_text(session, self._arg(message, "a", 400), limit=int(self.wedding_rules()["vow_limit"]))
        if words is None:
            return
        vows = wedding["state"].setdefault("vows", {})
        vows[str(session.char["id"])] = words
        self.store.save_wedding(wedding)
        for other in self._hall(wedding):
            if other is session:
                self._send(session, "said", "wedding_vow_you", words=words,
                           extra=self._voice_extra(session, words, actor=False))
            else:
                self._send(other, "say", "wedding_vow_other", extra=self._voice_extra(session, words),
                           actor=session.name, words=words)

    def _wedding_yes(self, session, message):
        wedding = self._my_ceremony(session, "consent")
        state = wedding["state"] if wedding else {}
        if wedding is None or state.get("asking") != session.char["id"]:
            if wedding is None and self.accept_pending(session):     # a plain "yes" to what waits for you
                return
            self._error(session, "wedding_not_now")
            return
        state["yes"].append(session.char["id"])
        state["prompted"] = False
        self.store.save_wedding(wedding)
        self._hall_emote(wedding, "nt_said_yes", name=session.name)
        self._tick_ceremony(wedding, self.now())

    def _wedding_no(self, session, message):
        wedding = self._my_ceremony(session, "consent")
        if wedding is None or wedding["state"].get("asking") != session.char["id"]:
            waiting = self._asks(session) if wedding is None else []
            if waiting and waiting[-1][2](session):                  # a plain "no" to what waits for you
                return
            self._error(session, "wedding_not_now")
            return
        self._say(wedding, "nt_no")
        self._stop_ceremony(wedding, "stopped", 1.0)

    def _wedding_sign(self, session, message):
        wedding = self._my_ceremony(session, "sign")
        if wedding is None or not wedding["state"].get("prompted"):
            self._error(session, "wedding_not_now")
            return
        signed = wedding["state"]["signed"]
        if session.char["id"] not in signed:
            signed.append(session.char["id"])
            self.store.save_wedding(wedding)
            self._hall_emote(wedding, "nt_signed", "register", name=session.name)

    def _finish(self, wedding, now):
        """Married: titles, keepsakes, the news for the station, and the memory of the day."""
        rules = self.wedding_rules()
        p, ids = self._couple(wedding)
        a, b = self._couple_names(wedding)
        tier = rules["tiers"][wedding["tier"]]
        state = wedding["state"]
        attended = []
        with self.store.transaction():
            p["status"], p["married"] = "married", now
            self.store.save_partnership(p)
            for char_id in ids:
                char = self._char_by_key(self.store.by_id(char_id)["name_key"])
                for tid in (rules["titles"][wedding["style"]], rules["keepsakes"][wedding["style"]]):
                    if tid in self.world.things and not self.owns(char, tid):
                        self.give_thing(char, tid)
                char["stats"]["weddings"] = int(char["stats"].get("weddings") or 0) + 1
                self.store.save(char)
            for char_id in state.get("attended", []):
                self.store.add_guest(wedding["id"], char_id, now)
                self.store.set_guest(wedding["id"], char_id, attended=1)
                stored = self.store.by_id(char_id)
                if stored:
                    attended.append(stored["name"])
            vows = {}
            for char_id in ids:
                stored = self.store.by_id(char_id)
                if stored:
                    vows[stored["name"]] = state.get("vows", {}).get(str(char_id), "")
            wedding["memory"] = {"a": a, "b": b, "venue": wedding["venue"], "tier": wedding["tier"],
                                 "style": wedding["style"], "at": float(wedding["starts"]), "guests": attended,
                                 "vows": vows}
            wedding["status"] = "done"
            wedding["ends"] = max(float(wedding["ends"]), now + 600)       # the reception: at least ten minutes
            self.store.save_wedding(wedding)
        logger.info("%s and %s are married", a, b)
        place = self.world.locations[wedding["venue"]]["ref"]
        if tier.get("fireworks"):
            self._hall_emote(wedding, "wedding_fireworks", "fireworks")
        for other in list(self.sessions.values()):
            self._send(other, "announce", "wedding_announce", a=a, b=b, place=place,
                       extra={"sound": "fireworks" if tier.get("fireworks") else "event_party", "event": "wedding"})
        for char_id in ids:
            stored = self.store.by_id(char_id)
            s = self.sessions.get(stored["name_key"]) if stored else None
            if s is not None:
                title = self.world.things.get(rules["titles"][wedding["style"]], {}).get("one", "")
                keepsake = self.world.things.get(rules["keepsakes"][wedding["style"]], {}).get("one", "")
                self._send(s, "paid", "wedding_gifts", title=title, keepsake=keepsake, extra={"sound": "achievement"})
                self.check_achievements(s)

    # --- memories ------------------------------------------------------------------------------------

    def memory_text(self, lang, wedding):
        memory = wedding.get("memory") or {}
        state = wedding.get("state") or {}
        when = datetime.datetime.fromtimestamp(float(memory.get("at", wedding["starts"])), datetime.timezone.utc)
        parts = [self.render(lang, "wedding_memory", a=memory.get("a", "?"), b=memory.get("b", "?"),
                             date=when.strftime("%d-%m-%Y"), hour=when.strftime("%H:%M"),
                             place=self.world.locations.get(memory.get("venue"), {}).get("ref", "?"),
                             tier=self._tier_name(lang, memory.get("tier", "simple")),
                             style=self._style_name(lang, memory.get("style", "neutral")))]
        guests = memory.get("guests") or []
        parts.append(self.render(lang, "wedding_memory_guests", guests=guests) if guests
                     else self.render(lang, "wedding_memory_no_guests"))
        for name, words in (memory.get("vows") or {}).items():
            parts.append(self.render(lang, "wedding_memory_vow", name=name, words=words) if words
                         else self.render(lang, "wedding_memory_silent", name=name))
        parts.append(self.render(lang, "wedding_memory_joy", flowers=int(state.get("flowers") or 0),
                                 cheers=int(state.get("cheers") or 0)))
        return "\n".join(parts)

    def _wedding_memory(self, session, message):
        lang = session.lang
        name = orbit_safety.name_key(self._arg(message, "a", 40) or self._arg(message, "to", 40))
        memories = self.store.memories_of(session.char["id"])
        if name:
            memories = [(w, was) for w, was in memories
                        if name in {orbit_safety.name_key(n) for n in self._couple_names(w)}]
        if not memories:
            self._error(session, "wedding_memory_none")
            return
        self._info(session, text=self.memory_text(lang, memories[0][0]), sound="npc_warm")

    # --- the look of a celebration ----------------------------------------------------------------

    def wedding_decor(self, session):
        """A line for the hall's description while a wedding is celebrated there."""
        wedding = self._celebrating(self.room_of(session.char))
        if wedding is None:
            return ""
        a, b = self._couple_names(wedding)
        return self.render(session.lang, f"wedding_look_{wedding['tier']}", a=a, b=b)

    def wedding_ambience(self, session, lid):
        """The celebration's ambience for a client that has it (1.2 and later), or None."""
        if tuple(session.client) < (1, 2) or not self.world.locations.get(lid, {}).get("venue"):
            return None
        wedding = self._celebrating(lid)
        if wedding is None or not self.wedding_rules()["tiers"][wedding["tier"]].get("ambience"):
            return None
        return "wedding"
