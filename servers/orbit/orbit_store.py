# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Orbit's saved state, in SQLite: characters, bans and a few server values
(the market's prices, the salt for secrets).

What is kept for a character: its name, job, credits, items, where it is, the
short description its player wrote, cooldowns and missions (a small JSON
"stats" field), when it was made and last seen, and whether it is banned or
muted. Its player's secret is never stored: only a PBKDF2-SHA256 hash of it,
with a salt made once for this server, so a leaked database can't be used to
log in. Chat is never stored here.

Everything is written at once (autocommit), from the server's one thread.
"""

import hashlib
import json
import os
import sqlite3
import time

HASH_ITERATIONS = 60_000
SECRET_MIN_LENGTH = 32          # hex characters: 128 bits at least

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    secret_hash TEXT NOT NULL UNIQUE,
    job TEXT NOT NULL,
    credits INTEGER NOT NULL DEFAULT 0,
    location TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    inventory TEXT NOT NULL DEFAULT '{}',
    stats TEXT NOT NULL DEFAULT '{}',
    banned INTEGER NOT NULL DEFAULT 0,
    muted_until REAL NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ip_bans (
    ip_hash TEXT PRIMARY KEY,
    until REAL NOT NULL
);
"""

FIELDS = ("id", "name", "name_key", "secret_hash", "job", "credits", "location", "description",
          "inventory", "stats", "banned", "muted_until", "created", "last_seen")
JSON_FIELDS = ("inventory", "stats")


class Character(dict):
    """A character's row as a dict; inventory and stats are dicts."""

    @property
    def key(self):
        return self["name_key"]


class Store:
    def __init__(self, path, clock=time.time, iterations=HASH_ITERATIONS, durable=True):
        """`durable`: wait for the disk after each write (WAL, synchronous
        NORMAL: a power cut loses at most the last moments). Tests pass False."""
        self.path = path
        self.clock = clock
        self.iterations = int(iterations)
        if path != ":memory:":
            folder = os.path.dirname(os.path.abspath(path))
            os.makedirs(folder, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(f"PRAGMA synchronous={'NORMAL' if durable else 'OFF'}")
        self.db.executescript(SCHEMA)
        self._salt = self.get_meta("secret_salt")
        if not self._salt:
            self._salt = os.urandom(16).hex()
            self.set_meta("secret_salt", self._salt)

    def close(self):
        self.db.close()

    # --- server values ----------------------------------------------------------------

    def get_meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key, value):
        self.db.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))

    def get_json(self, key, default=None):
        raw = self.get_meta(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except ValueError:
            return default

    def set_json(self, key, value):
        self.set_meta(key, json.dumps(value, separators=(",", ":")))

    # --- secrets ----------------------------------------------------------------------

    def hash_secret(self, secret):
        """The stored form of a player's secret (PBKDF2-SHA256 with this
        server's salt), or None for something that isn't a proper secret."""
        secret = str(secret or "")
        if len(secret) < SECRET_MIN_LENGTH or len(secret) > 256 or not secret.isalnum():
            return None
        digest = hashlib.pbkdf2_hmac("sha256", secret.encode("ascii"), bytes.fromhex(self._salt),
                                     self.iterations)
        return digest.hex()

    # --- characters -------------------------------------------------------------------

    @staticmethod
    def _character(row):
        if row is None:
            return None
        char = Character({name: row[name] for name in FIELDS})
        for name in JSON_FIELDS:
            try:
                value = json.loads(char[name] or "{}")
            except ValueError:
                value = {}
            char[name] = value if isinstance(value, dict) else {}
        return char

    def by_secret_hash(self, secret_hash):
        row = self.db.execute("SELECT * FROM characters WHERE secret_hash = ?",
                              (secret_hash,)).fetchone()
        return self._character(row)

    def by_name(self, name_key):
        row = self.db.execute("SELECT * FROM characters WHERE name_key = ?",
                              (name_key,)).fetchone()
        return self._character(row)

    def create(self, name, name_key, secret_hash, job, credits, location):
        now = self.clock()
        cursor = self.db.execute(
            "INSERT INTO characters (name, name_key, secret_hash, job, credits, location, "
            "created, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, name_key, secret_hash, job, int(credits), location, now, now))
        return self.by_name(name_key) if cursor.lastrowid else None

    def save(self, char):
        char["last_seen"] = self.clock()
        self.db.execute(
            "UPDATE characters SET job = ?, credits = ?, location = ?, description = ?, "
            "inventory = ?, stats = ?, banned = ?, muted_until = ?, last_seen = ? WHERE id = ?",
            (char["job"], int(char["credits"]), char["location"], char["description"],
             json.dumps(char["inventory"], separators=(",", ":")),
             json.dumps(char["stats"], separators=(",", ":")),
             int(bool(char["banned"])), float(char["muted_until"]), char["last_seen"], char["id"]))

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM characters").fetchone()[0]

    # --- bans by address (only a hash of it is kept) ------------------------------------

    def ban_ip(self, ip_hash, seconds):
        if ip_hash:
            self.db.execute("INSERT INTO ip_bans (ip_hash, until) VALUES (?, ?) ON CONFLICT(ip_hash) "
                            "DO UPDATE SET until = excluded.until", (ip_hash, self.clock() + seconds))

    def unban_ip(self, ip_hash):
        self.db.execute("DELETE FROM ip_bans WHERE ip_hash = ?", (ip_hash,))

    def ip_banned(self, ip_hash):
        if not ip_hash:
            return False
        row = self.db.execute("SELECT until FROM ip_bans WHERE ip_hash = ?", (ip_hash,)).fetchone()
        return bool(row) and row["until"] > self.clock()

    def ip_hash(self, ip):
        """The only form of an address ever kept (for a ban): a salted hash."""
        if not ip:
            return None
        return hashlib.sha256(f"{self._salt}:{ip}".encode("utf-8")).hexdigest()[:32]
