# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Moving a character to another computer, and the admins' commands.

A character lives on the computer that made it: that computer keeps a
random secret, and the server only a hash of it. "transfer code" (or
Preferences, Orbit, "Move my character to another computer") asks the
server for a one-time code: 16 letters from an alphabet without I and O,
in four groups, good for 10 minutes and once; only its keyed hash is kept,
and asking again replaces it. The other computer sends the code with a new
secret of its own: the character's secret becomes the new one, and the old
computer's stops working (it is told why), so a character is moved, never
copied. An address that gets codes wrong 5 times in 15 minutes waits.

Admins (config "admins") can also: grant or take credits, give any thing,
see the economy, set a market price for a while, reset a daily streak, go
to any place or player, become invisible, see recent transfers, revoke a
character's secret (a stolen computer), make a transfer code for someone
who lost theirs, and read the admins' log. Everything an admin does is
logged, in the server's log and in the database.
"""

import logging
import secrets

import orbit_safety
from orbit_lang import pick

logger = logging.getLogger("orbit.game")

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"      # no I, no O
CODE_LENGTH = 16
CLOSE_REPLACED = 4001
CLOSE_KICKED = 4000
CLOSE_BANNED = 4003


def new_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(text):
    """What was typed or pasted, as the 16 letters (or "" when it can't be a code)."""
    letters = "".join(c for c in str(text or "").upper() if c.isalpha())
    if len(letters) != CODE_LENGTH or any(c not in CODE_ALPHABET for c in letters):
        return ""
    return letters


def show_code(code):
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def spell_code(code):
    """Letter by letter, so a voice reads each one: "A B C D, E F G H..."."""
    return ", ".join(" ".join(code[i:i + 4]) for i in range(0, len(code), 4))


class AdminMixin:
    @staticmethod
    def commands():
        return {"admin": AdminMixin.cmd_admin, "transfer": AdminMixin.cmd_transfer}

    # --- moving a character ---------------------------------------------------------------

    def _code_for(self, char, by=""):
        code = new_code()
        minutes = int(self.config["transfer_minutes"])
        self.store.set_transfer_code(char["id"], self.store.hash_code(code), self.now() + minutes * 60, by)
        self.store.log_transfer(char, "code", by)
        logger.info("transfer code made for %s%s", char["name"], f" by admin {by}" if by else "")
        return code

    def cmd_transfer(self, session, message):
        char, lang = session.char, session.lang
        if not self._check_cooldown(session, "transfer_code"):
            return
        self._set_cooldown(char, "transfer_code", 30)
        code = self._code_for(char)
        minutes = int(self.config["transfer_minutes"])
        self._send(session, "info", "transfer_code", code=spell_code(code), minutes=minutes,
                   extra={"transfer_code": show_code(code), "expires": minutes * 60, "sound": "gadget"})

    def _transfer_blocked(self, ip_hash):
        window = float(self.config["transfer_window"])
        now = self.now()
        tries = [t for t in self.transfer_fails.get(ip_hash or "?", []) if now - t < window]
        self.transfer_fails[ip_hash or "?"] = tries
        return len(tries) >= int(self.config["transfer_tries"])

    def _redeem_transfer(self, conn, typed, secret_hash):
        """The character a hello's transfer code moves here (its secret becomes
        this computer's), or None (the connection was told why)."""
        ip_hash = getattr(conn, "ip_hash", None)
        if self._transfer_blocked(ip_hash):
            self._refuse(conn, "transfer_wait")
            return None
        code = normalize_code(typed)
        char_id = self.store.take_transfer_code(self.store.hash_code(code)) if code else None
        char = self.store.by_id(char_id) if char_id is not None else None
        if char is None:
            self.transfer_fails.setdefault(ip_hash or "?", []).append(self.now())
            self._refuse(conn, "transfer_bad")
            return None
        if self.store.by_secret_hash(secret_hash) is not None:
            self._refuse(conn, "bad_secret")
            return None
        session = self.sessions.get(char["name_key"])
        if session is not None:
            char = session.char
            old = session.conn
            if old is not None and old is not conn:
                self._send(session, "system", "moved_away")
                old.session = None
                old.close(CLOSE_REPLACED, "moved")
                session.conn = None
                session.dropped_at = self.now()
        self.store.replace_secret(char, secret_hash, "moved")
        self.store.log_transfer(char, "moved")
        logger.info("%s moved to another computer", char["name"])
        return char

    # --- admin ----------------------------------------------------------------------

    def _log(self, session, action, target="", detail=""):
        logger.info("admin %s: %s %s %s", session.name, action, target, detail)
        self.store.log_admin(session.name, action, target, detail)

    def cmd_admin(self, session, message):
        op = self._arg(message, "op", 20)
        if not self.is_admin(session):
            if op == "grant" and self._count(message, default=None) is not None:
                # "beri kredit Budi 50" from a player: a gift, not a grant.
                self.cmd_give(session, {"to": self._arg(message, "to", 40), "n": message.get("n"),
                                        "item": "credits"})
                return
            self._error(session, "not_admin")
            return
        handler = {"announce": self._admin_announce, "economy": self._admin_economy,
                   "set_price": self._admin_set_price, "goto": lambda s, m: self.admin_goto(s, self._arg(m)),
                   "invisible": self._admin_invisible, "transfers": self._admin_transfers,
                   "admin_log": self._admin_log}.get(op)
        if handler is not None:
            handler(session, message)
            return
        name = self._arg(message, "to", 40)
        target = self._find_session(name)
        char = target.char if target else self.store.by_name(orbit_safety.name_key(name))
        if char is None:
            self._error(session, "no_player", name=name or "?")
            return
        handler = {"mute": self._admin_mute, "unmute": self._admin_unmute, "kick": self._admin_kick,
                   "ban": self._admin_ban, "unban": self._admin_unban, "grant": self._admin_grant,
                   "take_credits": self._admin_take, "give_item": self._admin_give_item,
                   "reset_streak": self._admin_reset_streak, "revoke": self._admin_revoke,
                   "transfer_for": self._admin_transfer_for}.get(op)
        if handler is None:
            self._error(session, "unknown_command")
            return
        done = handler(session, message, char, target)
        if done:
            self._send(session, "info", text=done)

    def _admin_announce(self, session, message):
        text = orbit_safety.tidy(self._arg(message), self.config["say_limit"])
        if not text:
            self._error(session, "say_what")
            return
        for other in list(self.sessions.values()):
            self._send(other, "announce", "announce", words=text)
        self._log(session, "announce", "", text)

    def _admin_mute(self, session, message, char, target):
        lang = session.lang
        minutes = self._count(message, default=10, high=24 * 60) or 10
        char["muted_until"] = self.now() + minutes * 60
        self._save(char)
        if target:
            self._send(target, "system", "muted_you", time=self._duration(target.lang, minutes * 60))
        self._log(session, "mute", char["name"], f"{minutes} min")
        return self.render(lang, "admin_muted", name=char["name"], time=self._duration(lang, minutes * 60))

    def _admin_unmute(self, session, message, char, target):
        char["muted_until"] = 0
        self._save(char)
        if target:
            self._send(target, "system", "unmuted_you")
        self._log(session, "unmute", char["name"])
        return self.render(session.lang, "admin_unmuted", name=char["name"])

    def _admin_kick(self, session, message, char, target):
        if target is None or target.conn is None:
            self._error(session, "player_away", name=char["name"])
            return None
        self._kick(target, "kicked_you", CLOSE_KICKED)
        self._log(session, "kick", char["name"])
        return self.render(session.lang, "admin_kicked", name=char["name"])

    def _admin_ban(self, session, message, char, target):
        char["banned"] = 1
        if target is not None and target.conn is not None:
            ip_hash = getattr(target.conn, "ip_hash", None)
            if ip_hash:
                self.store.ban_ip(ip_hash, self.config["ban_ip_days"] * 86400)
                char["stats"]["ban_ip"] = ip_hash
        self._save(char)
        if target is not None:
            self._kick(target, "banned_you", CLOSE_BANNED)
        self._log(session, "ban", char["name"])
        return self.render(session.lang, "admin_banned", name=char["name"])

    def _admin_unban(self, session, message, char, target):
        char["banned"] = 0
        ip_hash = char["stats"].pop("ban_ip", None)
        if ip_hash:
            self.store.unban_ip(ip_hash)
        self._save(char)
        self._log(session, "unban", char["name"])
        return self.render(session.lang, "admin_unbanned", name=char["name"])

    def _admin_grant(self, session, message, char, target):
        n = self._count(message, default=None, high=10_000_000)
        if n is None:
            self._error(session, "bad_number")
            return None
        self.earn(char, n, "admin")
        self._save(char)
        if target:
            self._send(target, "received", "granted_you", n=n, credits=char["credits"])
        self._log(session, "grant", char["name"], n)
        return self.render(session.lang, "admin_granted", name=char["name"], n=n, credits=char["credits"])

    def _admin_take(self, session, message, char, target):
        n = self._count(message, default=None, high=10_000_000)
        if n is None:
            self._error(session, "bad_number")
            return None
        n = min(n, int(char["credits"]))
        self.spend(char, n, "admin")
        self._save(char)
        if target:
            self._send(target, "system", "taken_you", n=n, credits=char["credits"])
        self._log(session, "take_credits", char["name"], n)
        return self.render(session.lang, "admin_taken", name=char["name"], n=n, credits=char["credits"])

    def _admin_give_item(self, session, message, char, target):
        text = self._arg(message, "item", 60)
        tid = self.world.find_thing(text) if text else None
        if tid is None:
            self._error(session, "no_item", what=text or "?")
            return None
        thing = self.world.things[tid]
        n = self._count(message, default=1, high=100) or 1
        if thing["type"] == "pet":
            self.store.add_companion(tid, thing["effects"]["pet"].get("name", "Bip"), [char["id"]])
        elif thing.get("service") == "plot":
            char["stats"]["plots"] = min(int(self.econ["farm"]["max_plots"]), self.plot_count(char) + n)
        else:
            self.give_thing(char, tid, 1 if thing.get("unique") else n)
        self._save(char)
        if target:
            self._send(target, "received", "given_you", things=self._count_of(tid, n))
        self._log(session, "give_item", char["name"], f"{tid} x{n}")
        return self.render(session.lang, "admin_gave", name=char["name"], things=self._count_of(tid, n))

    def _admin_reset_streak(self, session, message, char, target):
        char["streak"] = 0
        char["last_daily"] = ""
        self._save(char)
        self._log(session, "reset_streak", char["name"])
        return self.render(session.lang, "admin_streak_reset", name=char["name"])

    def _admin_revoke(self, session, message, char, target):
        self.store.revoke_secret(char)
        self.store.log_transfer(char, "revoked", session.name)
        if target is not None and target.conn is not None:
            self._send(target, "system", "revoked_you")
            conn = target.conn
            target.conn = None
            target.dropped_at = self.now()
            conn.session = None
            conn.close(CLOSE_REPLACED, "revoked")
        self._log(session, "revoke", char["name"])
        return self.render(session.lang, "admin_revoked", name=char["name"])

    def _admin_transfer_for(self, session, message, char, target):
        code = self._code_for(char, by=session.name)
        self._log(session, "transfer_code", char["name"])
        self._send(session, "info", "admin_transfer_code", name=char["name"], code=spell_code(code),
                   minutes=int(self.config["transfer_minutes"]),
                   extra={"transfer_code": show_code(code), "expires": int(self.config["transfer_minutes"]) * 60})
        return None

    def _admin_economy(self, session, message):
        lang = session.lang
        total, count, top = self.store.total_credits()
        earned = self.flows["earned"]
        spent = self.flows["spent"]

        def listing(flows):
            items = sorted(flows.items(), key=lambda kv: -kv[1])
            return ", ".join(f"{name} {amount}" for name, amount in items) or "-"

        richest = ", ".join(f"{name} {value}" for name, value in self.store.top("credits", 3)) or "-"
        index = sum(self.market.price(g) / good["base"] for g, good in self.world.goods.items())
        index = int(round(100 * index / max(1, len(self.world.goods))))
        self._send(session, "info", "admin_economy", total=total, count=count,
                   average=int(round(total / count)) if count else 0, top=top, richest=richest,
                   earned=listing(earned), spent=listing(spent),
                   net=sum(earned.values()) - sum(spent.values()), index=index)
        self._log(session, "economy")

    def _admin_set_price(self, session, message):
        text = self._arg(message, "item", 60)
        good = self.world.find_good(text) if text else None
        n = self._count(message, default=None, high=100_000)
        if good is None or n is None:
            self._error(session, "admin_set_price_how")
            return
        self.market.overrides[good] = {"price": float(n), "until": self.now() + 3600}
        self.market.save()
        self._log(session, "set_price", good, n)
        self._send(session, "info", "admin_price_set", thing=self.world.goods[good]["one"], n=n)

    def _admin_invisible(self, session, message):
        session.invisible = not session.invisible
        self._log(session, "invisible", "", "on" if session.invisible else "off")
        self._send(session, "info", "admin_invisible_on" if session.invisible else "admin_invisible_off")

    def _admin_transfers(self, session, message):
        lang = session.lang
        rows = self.store.recent_transfers(10)
        if not rows:
            self._send(session, "info", "admin_transfers_none")
            return
        entries = [self.render(lang, f"transfer_kind_{row['kind']}", name=row["name"], by=row["by"] or "-",
                               time=self._ago(lang, row["time"])) for row in rows]
        self._send(session, "info", "admin_transfers", entries="; ".join(entries))
        self._log(session, "transfers")

    def _admin_log(self, session, message):
        lang = session.lang
        rows = self.store.admin_log(10)
        entries = [f"{self._ago(lang, row['time'])}: {row['actor']} {row['action']} {row['target']} "
                   f"{row['detail']}".strip() for row in rows]
        self._send(session, "info", "admin_log", entries="; ".join(entries) or "-")

    def _ago(self, lang, when):
        return self.render(lang, "ago", time=self._duration(lang, max(1, self.now() - float(when))))

    def admin_goto(self, session, text):
        lang = session.lang
        target = self._find_session(text)
        if target is not None and target is not session:
            dest = target.char["location"]
            if dest in ("shuttle", "kancil"):
                self._error(session, "admin_goto_flying", name=target.name)
                return
            host = (target.char["stats"].get("visit") or target.key) if dest == "cabin" else None
        else:
            dest = self.find_place(session, text)
            host = None
            if dest in (None, "?beacon"):
                self._error(session, "no_place", what=text)
                return
        self._log(session, "goto", dest)
        self._move_to(session, dest, message={l: self.render(l, "admin_teleport") for l in ("en", "id")},
                      host=host)

    def _kick(self, target, key, code):
        self._send(target, "system", key)
        conn = target.conn
        target.conn = None
        if conn is not None:
            conn.session = None
            conn.close(code, key)
        self._remove(target, "leave_bye")


_ = pick
