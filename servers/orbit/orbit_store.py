# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Orbit's saved state, in SQLite: every character and everything that changes
while playing, in one file. world.json and economy.json are only read.

What is kept for a character: its name, job, credits, things (inventory),
where it is, the short description its player wrote, XP, the daily streak,
the voice others hear it in, what it mined and harvested, and a JSON "stats"
field for the rest of its play state (cooldowns, missions, farm plots, worn
things, the map it knows, air left outside, a shuttle ride in progress...);
when it was made and last seen, and whether it is banned or muted. Its
player's secret is never stored: only a PBKDF2-SHA256 hash of it, with a
salt made once for this server, so a leaked database can't be used to log in.
Chat is never stored here.

Other tables: companions (a pet, and later other companions, with its
owners), ships (each player's own: its model and name, where it's docked or
where it's flying, its fuel and cargo), events (each one that ran or is
scheduled, its state and how it ended) and who took part in them, the
hunt's progress (each character's stage in each season, its tries and its
wait after a wrong answer), achievements, lottery tickets,
transfer codes (only a hash, for 10 minutes), secrets that no longer work (moved to another computer, or revoked
by an admin, so the old computer is told why), the transfers log, the
admins' log, bans by address (a salted hash), and "meta" for server values
(the market's prices, each world's market, the economy's totals, the
lottery's pot, the salt). Since Orbit 1.2 (schema 8): what each resident
remembers of each character (npc_memory: affinity, talks, gifts, favours,
small notes), partnerships between two characters, weddings (their hall,
tier, ceremony, time, what was paid, their progress and the memory kept
afterwards) and their guests (invited, answered, came).

The schema has a version (PRAGMA user_version). An older file is migrated
by itself when the server starts, in one transaction, after a copy of it is
saved next to it (orbit.db.before-v8.bak); columns and tables are only ever
added, never dropped.

Everything is written at once (autocommit, or one transaction for things
that must change together), from the server's one thread.
"""

import contextlib
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time

logger = logging.getLogger("orbit.store")

HASH_ITERATIONS = 60_000
SECRET_MIN_LENGTH = 32          # hex characters: 128 bits at least
SCHEMA_VERSION = 8

# The schema of Orbit 1.0 (version 0). Migrations add to it.
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

# Version 1 (Orbit 1.1): levels, the daily bonus, voices, leaderboard
# counters; companions; moving a character to another computer; the admins' log.
V1_COLUMNS = (
    ("voice", "INTEGER NOT NULL DEFAULT 0"),
    ("xp", "INTEGER NOT NULL DEFAULT 0"),
    ("streak", "INTEGER NOT NULL DEFAULT 0"),
    ("last_daily", "TEXT NOT NULL DEFAULT ''"),
    ("mined", "INTEGER NOT NULL DEFAULT 0"),
    ("harvested", "INTEGER NOT NULL DEFAULT 0"),
)
V1_TABLES = """
CREATE TABLE IF NOT EXISTS companions (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    stats TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT '{}',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS companion_owners (
    companion_id INTEGER NOT NULL,
    char_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner',
    since REAL NOT NULL,
    PRIMARY KEY (companion_id, char_id)
);
CREATE INDEX IF NOT EXISTS companion_owners_char ON companion_owners (char_id);
CREATE TABLE IF NOT EXISTS transfer_codes (
    char_id INTEGER PRIMARY KEY,
    code_hash TEXT NOT NULL UNIQUE,
    expires REAL NOT NULL,
    created REAL NOT NULL,
    issued_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS old_secrets (
    secret_hash TEXT PRIMARY KEY,
    char_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    time REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY,
    char_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    by TEXT NOT NULL DEFAULT '',
    time REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_log (
    id INTEGER PRIMARY KEY,
    time REAL NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
"""

# Version 2 (Orbit 1.1, the casino and achievements).
V2_COLUMNS = (
    ("casino_net", "INTEGER NOT NULL DEFAULT 0"),
)
V2_TABLES = """
CREATE TABLE IF NOT EXISTS achievements (
    char_id INTEGER NOT NULL,
    achievement TEXT NOT NULL,
    earned REAL NOT NULL,
    PRIMARY KEY (char_id, achievement)
);
CREATE INDEX IF NOT EXISTS achievements_by_name ON achievements (achievement);
CREATE TABLE IF NOT EXISTS lottery_tickets (
    week TEXT NOT NULL,
    char_id INTEGER NOT NULL,
    tickets INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (week, char_id)
);
"""

# Version 3 (Orbit 1.1, ships and the other worlds).
V3_TABLES = """
CREATE TABLE IF NOT EXISTS ships (
    id INTEGER PRIMARY KEY,
    owner INTEGER NOT NULL UNIQUE,
    model TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    dock TEXT NOT NULL DEFAULT '',
    fuel REAL NOT NULL DEFAULT 0,
    cargo TEXT NOT NULL DEFAULT '{}',
    flight TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
"""

# Version 4 (Orbit 1.1, events).
V4_TABLES = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    event TEXT NOT NULL,
    starts REAL NOT NULL,
    ends REAL NOT NULL,
    status TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT '{}',
    host TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_status ON events (status);
CREATE TABLE IF NOT EXISTS event_players (
    event_id INTEGER NOT NULL,
    char_id INTEGER NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    last REAL NOT NULL,
    PRIMARY KEY (event_id, char_id)
);
"""

# Version 5 (Orbit 1.1, the hunt).
V5_TABLES = """
CREATE TABLE IF NOT EXISTS hunt_progress (
    season TEXT NOT NULL,
    char_id INTEGER NOT NULL,
    stage INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    wrong INTEGER NOT NULL DEFAULT 0,
    cooldown REAL NOT NULL DEFAULT 0,
    finished REAL NOT NULL DEFAULT 0,
    place INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season, char_id)
);
"""

V6_TABLES = """
CREATE TABLE IF NOT EXISTS arcade_scores (
    game TEXT NOT NULL,
    char_id INTEGER NOT NULL,
    best INTEGER NOT NULL DEFAULT 0,
    plays INTEGER NOT NULL DEFAULT 0,
    last REAL NOT NULL DEFAULT 0,
    best_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (game, char_id)
);
CREATE INDEX IF NOT EXISTS arcade_scores_best ON arcade_scores (game, best DESC, best_at);
"""

V7_TABLES = """
CREATE TABLE IF NOT EXISTS crews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    motto TEXT NOT NULL DEFAULT '',
    founded REAL NOT NULL DEFAULT 0,
    points INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS crew_members (
    char_id INTEGER PRIMARY KEY,
    crew_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    joined REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS crew_members_crew ON crew_members (crew_id);
"""

# Version 8 (Orbit 1.2): what the station's residents remember of each
# player; partnerships, weddings and their guests; duels won, as a column
# for the leaderboard (it is also in the stats).
V8_COLUMNS = (
    ("duels_won", "INTEGER NOT NULL DEFAULT 0"),
)
V8_TABLES = """
CREATE TABLE IF NOT EXISTS npc_memory (
    npc TEXT NOT NULL,
    char_id INTEGER NOT NULL,
    affinity INTEGER NOT NULL DEFAULT 0,
    talks INTEGER NOT NULL DEFAULT 0,
    gifts INTEGER NOT NULL DEFAULT 0,
    favours INTEGER NOT NULL DEFAULT 0,
    first_met REAL NOT NULL DEFAULT 0,
    last_met REAL NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (npc, char_id)
);
CREATE INDEX IF NOT EXISTS npc_memory_char ON npc_memory (char_id);
CREATE TABLE IF NOT EXISTS partnerships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a INTEGER NOT NULL,
    b INTEGER NOT NULL,
    status TEXT NOT NULL,
    since REAL NOT NULL,
    engaged REAL NOT NULL DEFAULT 0,
    married REAL NOT NULL DEFAULT 0,
    ended REAL NOT NULL DEFAULT 0,
    ended_by TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS partnerships_a ON partnerships (a, status);
CREATE INDEX IF NOT EXISTS partnerships_b ON partnerships (b, status);
CREATE TABLE IF NOT EXISTS weddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partnership INTEGER NOT NULL,
    venue TEXT NOT NULL,
    tier TEXT NOT NULL,
    style TEXT NOT NULL,
    starts REAL NOT NULL,
    ends REAL NOT NULL,
    status TEXT NOT NULL,
    booked_by INTEGER NOT NULL,
    paid INTEGER NOT NULL DEFAULT 0,
    refunded INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT '{}',
    memory TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS weddings_by_status ON weddings (status, starts);
CREATE TABLE IF NOT EXISTS wedding_guests (
    wedding INTEGER NOT NULL,
    char_id INTEGER NOT NULL,
    rsvp TEXT NOT NULL DEFAULT 'invited',
    invited REAL NOT NULL,
    told INTEGER NOT NULL DEFAULT 0,
    attended INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (wedding, char_id)
);
CREATE INDEX IF NOT EXISTS wedding_guests_char ON wedding_guests (char_id);
"""

BASE_FIELDS = ("id", "name", "name_key", "secret_hash", "job", "credits", "location", "description",
               "inventory", "stats", "banned", "muted_until", "created", "last_seen")
FIELDS = BASE_FIELDS + tuple(name for name, _decl in V1_COLUMNS + V2_COLUMNS + V8_COLUMNS)
JSON_FIELDS = ("inventory", "stats")
INT_FIELDS = ("voice", "xp", "streak", "mined", "harvested", "casino_net", "duels_won")
BOARD_COLUMNS = ("credits", "xp", "mined", "harvested", "streak", "casino_net", "duels_won")
ACTIVE_PARTNERSHIP = ("partners", "engaged", "married")


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
        self._depth = 0
        if path != ":memory:":
            folder = os.path.dirname(os.path.abspath(path))
            os.makedirs(folder, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(f"PRAGMA synchronous={'NORMAL' if durable else 'OFF'}")
        had_data = self._table_exists("characters")
        self.db.executescript(SCHEMA)
        self.migrated_from = None
        self._migrate(had_data)
        self._salt = self.get_meta("secret_salt")
        if not self._salt:
            self._salt = os.urandom(16).hex()
            self.set_meta("secret_salt", self._salt)

    def close(self):
        self.db.close()

    # --- the schema's version ------------------------------------------------------------

    def _table_exists(self, name):
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                               (name,)).fetchone() is not None

    def version(self):
        return self.db.execute("PRAGMA user_version").fetchone()[0]

    def _columns(self, table):
        return {row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")}

    def _migrate(self, had_data):
        version = self.version()
        if version >= SCHEMA_VERSION:
            return
        if had_data and self.path != ":memory:":
            self._backup_before(version)
        with self.transaction():
            if version < 1:
                self._migrate_1()
            if version < 2:
                self._migrate_2()
            if version < 3:
                self._migrate_3()
            if version < 4:
                self._migrate_4()
            if version < 5:
                self._migrate_5()
            if version < 6:
                self._migrate_6()
            if version < 7:
                self._migrate_7()
            if version < 8:
                self._migrate_8()
            self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        if had_data:
            self.migrated_from = version
            logger.info("the database was migrated from version %s to %s", version, SCHEMA_VERSION)

    def _backup_before(self, version):
        target = f"{self.path}.before-v{SCHEMA_VERSION}.bak"
        if os.path.exists(target):
            target = f"{self.path}.before-v{SCHEMA_VERSION}-{int(self.clock())}.bak"
        copy = sqlite3.connect(target)
        try:
            self.db.backup(copy)
        finally:
            copy.close()
        logger.info("saved a copy of the version %s database as %s", version, target)

    def _migrate_1(self):
        have = self._columns("characters")
        for name, decl in V1_COLUMNS:
            if name not in have:
                self.db.execute(f"ALTER TABLE characters ADD COLUMN {name} {decl}")
        for statement in V1_TABLES.split(";"):
            if statement.strip():
                self.db.execute(statement)
        # Work done before levels existed counts towards them.
        rows = self.db.execute("SELECT id, stats FROM characters").fetchall()
        for row in rows:
            try:
                stats = json.loads(row["stats"] or "{}")
            except ValueError:
                stats = {}
            if not isinstance(stats, dict):
                continue
            xp = 0
            for field, points in (("repairs", 10), ("flights", 20), ("missions_done", 25)):
                try:
                    xp += max(0, int(stats.get(field, 0))) * points
                except (TypeError, ValueError):
                    pass
            if xp:
                self.db.execute("UPDATE characters SET xp = ? WHERE id = ? AND xp = 0", (xp, row["id"]))

    def _migrate_2(self):
        have = self._columns("characters")
        for name, decl in V2_COLUMNS:
            if name not in have:
                self.db.execute(f"ALTER TABLE characters ADD COLUMN {name} {decl}")
        for statement in V2_TABLES.split(";"):
            if statement.strip():
                self.db.execute(statement)

    def _migrate_3(self):
        for statement in V3_TABLES.split(";"):
            if statement.strip():
                self.db.execute(statement)

    def _migrate_4(self):
        for statement in V4_TABLES.split(";"):
            if statement.strip():
                self.db.execute(statement)

    def _migrate_5(self):
        for statement in V5_TABLES.split(";"):
            if statement.strip():
                self.db.execute(statement)

    def _migrate_6(self):
        for statement in V6_TABLES.split(";"):
            if statement.strip():
                self.db.execute(statement)

    def _migrate_7(self):
        for statement in V7_TABLES.split(";"):
            if statement.strip():
                self.db.execute(statement)

    def _migrate_8(self):
        have = self._columns("characters")
        for name, decl in V8_COLUMNS:
            if name not in have:
                self.db.execute(f"ALTER TABLE characters ADD COLUMN {name} {decl}")
        for statement in V8_TABLES.split(";"):
            if statement.strip():
                self.db.execute(statement)
        # Duels won so far (kept in the stats since 1.1) count on the new board.
        for row in self.db.execute("SELECT id, stats FROM characters").fetchall():
            try:
                stats = json.loads(row["stats"] or "{}")
                won = max(0, int(stats.get("duels_won") or 0)) if isinstance(stats, dict) else 0
            except (ValueError, TypeError):
                won = 0
            if won:
                self.db.execute("UPDATE characters SET duels_won = ? WHERE id = ? AND duels_won = 0",
                                (won, row["id"]))

    @contextlib.contextmanager
    def transaction(self):
        """Everything inside happens together or not at all (nested: the outer one counts)."""
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        self.db.execute("BEGIN IMMEDIATE")
        self._depth = 1
        try:
            yield
        except BaseException:
            self._depth = 0
            self.db.execute("ROLLBACK")
            raise
        self._depth = 0
        self.db.execute("COMMIT")

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

    def hash_code(self, code):
        """The stored form of a transfer code (it lives ten minutes, and has
        about 70 bits: a keyed hash is enough)."""
        return hmac.new(bytes.fromhex(self._salt), f"transfer:{code}".encode("utf-8"),
                        hashlib.sha256).hexdigest()

    # --- characters -------------------------------------------------------------------

    @staticmethod
    def _character(row):
        if row is None:
            return None
        keys = row.keys()
        char = Character({name: row[name] for name in FIELDS if name in keys})
        for name in JSON_FIELDS:
            try:
                value = json.loads(char[name] or "{}")
            except ValueError:
                value = {}
            char[name] = value if isinstance(value, dict) else {}
        for name in INT_FIELDS:
            char[name] = int(char.get(name) or 0)
        char["last_daily"] = str(char.get("last_daily") or "")
        return char

    def by_secret_hash(self, secret_hash):
        row = self.db.execute("SELECT * FROM characters WHERE secret_hash = ?",
                              (secret_hash,)).fetchone()
        return self._character(row)

    def by_name(self, name_key):
        row = self.db.execute("SELECT * FROM characters WHERE name_key = ?",
                              (name_key,)).fetchone()
        return self._character(row)

    def by_id(self, char_id):
        row = self.db.execute("SELECT * FROM characters WHERE id = ?", (char_id,)).fetchone()
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
        try:
            char["duels_won"] = max(0, int(char["stats"].get("duels_won") or 0))
        except (TypeError, ValueError):
            char["duels_won"] = 0
        self.db.execute(
            "UPDATE characters SET job = ?, credits = ?, location = ?, description = ?, "
            "inventory = ?, stats = ?, banned = ?, muted_until = ?, last_seen = ?, voice = ?, "
            "xp = ?, streak = ?, last_daily = ?, mined = ?, harvested = ?, casino_net = ?, duels_won = ? "
            "WHERE id = ?",
            (char["job"], int(char["credits"]), char["location"], char["description"],
             json.dumps(char["inventory"], separators=(",", ":")),
             json.dumps(char["stats"], separators=(",", ":")),
             int(bool(char["banned"])), float(char["muted_until"]), char["last_seen"],
             int(char.get("voice") or 0), int(char.get("xp") or 0), int(char.get("streak") or 0),
             str(char.get("last_daily") or ""), int(char.get("mined") or 0),
             int(char.get("harvested") or 0), int(char.get("casino_net") or 0), char["duels_won"],
             char["id"]))

    def save_all(self, chars):
        """Several characters at once: all saved, or none (a trade)."""
        with self.transaction():
            for char in chars:
                self.save(char)

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM characters").fetchone()[0]

    def total_credits(self):
        row = self.db.execute("SELECT COALESCE(SUM(credits), 0) AS total, COUNT(*) AS n, "
                              "COALESCE(MAX(credits), 0) AS top FROM characters "
                              "WHERE banned = 0").fetchone()
        return int(row["total"]), int(row["n"]), int(row["top"])

    @staticmethod
    def _without(exclude):
        """(" AND name_key NOT IN (?, ?)", keys): characters left off a leaderboard."""
        keys = sorted(exclude or ())
        if not keys:
            return "", ()
        return f" AND name_key NOT IN ({', '.join('?' for _k in keys)})", tuple(keys)

    def top(self, column, limit=5, exclude=()):
        """[(name, value)] with the highest `column` (a leaderboard), leaving out
        the characters whose name keys are in `exclude` (the admins)."""
        if column not in BOARD_COLUMNS:
            raise ValueError(column)
        skip, keys = self._without(exclude)
        rows = self.db.execute(f"SELECT name, {column} AS value FROM characters WHERE banned = 0{skip} "
                               f"ORDER BY {column} DESC, name_key LIMIT ?", keys + (int(limit),)).fetchall()
        return [(row["name"], int(row["value"])) for row in rows]

    def rank_of(self, column, char_id, exclude=()):
        """1 for the highest `column`, and so on."""
        if column not in BOARD_COLUMNS:
            raise ValueError(column)
        row = self.db.execute(f"SELECT {column} AS value FROM characters WHERE id = ?",
                              (char_id,)).fetchone()
        if row is None:
            return None
        skip, keys = self._without(exclude)
        higher = self.db.execute(f"SELECT COUNT(*) FROM characters WHERE banned = 0 AND "
                                 f"{column} > ?{skip}", (row["value"],) + keys).fetchone()[0]
        return higher + 1

    # --- achievements --------------------------------------------------------------------

    def add_achievement(self, char_id, achievement):
        """True when it's new for this character (and now kept)."""
        cursor = self.db.execute("INSERT OR IGNORE INTO achievements (char_id, achievement, earned) "
                                 "VALUES (?, ?, ?)", (char_id, achievement, self.clock()))
        return cursor.rowcount == 1

    def achievements_of(self, char_id):
        rows = self.db.execute("SELECT achievement FROM achievements WHERE char_id = ? ORDER BY earned, rowid",
                               (char_id,)).fetchall()
        return [row["achievement"] for row in rows]

    def achievement_count(self, achievement):
        return self.db.execute("SELECT COUNT(*) FROM achievements WHERE achievement = ?",
                               (achievement,)).fetchone()[0]

    # --- the lottery -----------------------------------------------------------------------

    def add_tickets(self, week, char_id, n):
        self.db.execute("INSERT INTO lottery_tickets (week, char_id, tickets) VALUES (?, ?, ?) "
                        "ON CONFLICT(week, char_id) DO UPDATE SET tickets = tickets + excluded.tickets",
                        (week, char_id, int(n)))

    def tickets(self, week, char_id):
        row = self.db.execute("SELECT tickets FROM lottery_tickets WHERE week = ? AND char_id = ?",
                              (week, char_id)).fetchone()
        return int(row["tickets"]) if row else 0

    def lottery_entries(self, week):
        """[(char_id, tickets)] of a week's draw, in a fixed order."""
        rows = self.db.execute("SELECT char_id, tickets FROM lottery_tickets WHERE week = ? AND tickets > 0 "
                               "ORDER BY char_id", (week,)).fetchall()
        return [(row["char_id"], int(row["tickets"])) for row in rows]

    # --- moving a character to another computer ---------------------------------------------

    def set_transfer_code(self, char_id, code_hash, expires, by=""):
        """The one live code of a character (a new one replaces the old)."""
        self.db.execute("INSERT INTO transfer_codes (char_id, code_hash, expires, created, issued_by) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(char_id) DO UPDATE SET "
                        "code_hash = excluded.code_hash, expires = excluded.expires, "
                        "created = excluded.created, issued_by = excluded.issued_by",
                        (char_id, code_hash, float(expires), self.clock(), by))

    def take_transfer_code(self, code_hash):
        """The character a live code belongs to (the code is used up), or None."""
        now = self.clock()
        self.db.execute("DELETE FROM transfer_codes WHERE expires <= ?", (now,))
        row = self.db.execute("SELECT char_id FROM transfer_codes WHERE code_hash = ?",
                              (code_hash,)).fetchone()
        if row is None:
            return None
        self.db.execute("DELETE FROM transfer_codes WHERE char_id = ?", (row["char_id"],))
        return row["char_id"]

    def has_transfer_code(self, char_id):
        row = self.db.execute("SELECT expires FROM transfer_codes WHERE char_id = ?",
                              (char_id,)).fetchone()
        return bool(row) and row["expires"] > self.clock()

    def replace_secret(self, char, new_hash, reason):
        """The character's secret changes; the old one is remembered as
        `reason` ("moved", "revoked") so its computer can be told."""
        old = char["secret_hash"]
        with self.transaction():
            if old and not old.startswith("revoked:"):
                self.db.execute("INSERT OR REPLACE INTO old_secrets (secret_hash, char_id, reason, time) "
                                "VALUES (?, ?, ?, ?)", (old, char["id"], reason, self.clock()))
            self.db.execute("UPDATE characters SET secret_hash = ? WHERE id = ?", (new_hash, char["id"]))
        char["secret_hash"] = new_hash

    def revoke_secret(self, char):
        """No computer can play the character until a transfer code is used."""
        self.replace_secret(char, "revoked:" + os.urandom(16).hex(), "revoked")

    def old_secret(self, secret_hash):
        """(char_id, reason) for a secret that no longer works, or None."""
        row = self.db.execute("SELECT char_id, reason FROM old_secrets WHERE secret_hash = ?",
                              (secret_hash,)).fetchone()
        return (row["char_id"], row["reason"]) if row else None

    def log_transfer(self, char, kind, by=""):
        self.db.execute("INSERT INTO transfers (char_id, name, kind, by, time) VALUES (?, ?, ?, ?, ?)",
                        (char["id"], char["name"], kind, by, self.clock()))

    def recent_transfers(self, limit=10):
        rows = self.db.execute("SELECT name, kind, by, time FROM transfers ORDER BY id DESC LIMIT ?",
                               (int(limit),)).fetchall()
        return [dict(row) for row in rows]

    # --- the admins' log ---------------------------------------------------------------

    def log_admin(self, actor, action, target="", detail=""):
        self.db.execute("INSERT INTO admin_log (time, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
                        (self.clock(), actor, action, target, str(detail)[:500]))

    def admin_log(self, limit=20):
        rows = self.db.execute("SELECT time, actor, action, target, detail FROM admin_log "
                               "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]

    # --- companions (a pet today; care, growth and families later) -------------------------

    @staticmethod
    def _companion(row):
        comp = dict(row)
        for name in ("stats", "state"):
            try:
                value = json.loads(comp.get(name) or "{}")
            except ValueError:
                value = {}
            comp[name] = value if isinstance(value, dict) else {}
        return comp

    def add_companion(self, kind, name, owner_ids, stats=None, state=None):
        now = self.clock()
        with self.transaction():
            cursor = self.db.execute(
                "INSERT INTO companions (kind, name, stats, state, created) VALUES (?, ?, ?, ?, ?)",
                (kind, name, json.dumps(stats or {}), json.dumps(state or {}), now))
            comp_id = cursor.lastrowid
            for char_id in owner_ids:
                self.db.execute("INSERT INTO companion_owners (companion_id, char_id, since) VALUES (?, ?, ?)",
                                (comp_id, char_id, now))
        return comp_id

    def companions_of(self, char_id):
        rows = self.db.execute(
            "SELECT c.* FROM companions c JOIN companion_owners o ON o.companion_id = c.id "
            "WHERE o.char_id = ? ORDER BY c.id", (char_id,)).fetchall()
        return [self._companion(row) for row in rows]

    def save_companion(self, comp):
        self.db.execute("UPDATE companions SET name = ?, stats = ?, state = ? WHERE id = ?",
                        (comp["name"], json.dumps(comp.get("stats") or {}),
                         json.dumps(comp.get("state") or {}), comp["id"]))

    def companion_by_id(self, comp_id):
        row = self.db.execute("SELECT * FROM companions WHERE id = ?", (comp_id,)).fetchone()
        return self._companion(row) if row else None

    def companion_owners(self, comp_id):
        """[(char_id, role)] of a companion, the first to have it first."""
        rows = self.db.execute("SELECT char_id, role FROM companion_owners WHERE companion_id = ? "
                               "ORDER BY since, char_id", (comp_id,)).fetchall()
        return [(row["char_id"], row["role"]) for row in rows]

    def add_companion_owner(self, comp_id, char_id, role="owner"):
        self.db.execute("INSERT OR IGNORE INTO companion_owners (companion_id, char_id, role, since) "
                        "VALUES (?, ?, ?, ?)", (comp_id, char_id, role, self.clock()))

    # --- what the station's residents remember ------------------------------------------

    def npc_memory(self, npc, char_id):
        """What resident `npc` remembers of a character (all zeros for a stranger)."""
        row = self.db.execute("SELECT * FROM npc_memory WHERE npc = ? AND char_id = ?", (npc, char_id)).fetchone()
        if row is None:
            return {"npc": npc, "char_id": char_id, "affinity": 0, "talks": 0, "gifts": 0, "favours": 0,
                    "first_met": 0.0, "last_met": 0.0, "state": {}}
        memory = dict(row)
        try:
            state = json.loads(memory.get("state") or "{}")
        except ValueError:
            state = {}
        memory["state"] = state if isinstance(state, dict) else {}
        return memory

    def save_npc_memory(self, memory):
        self.db.execute(
            "INSERT INTO npc_memory (npc, char_id, affinity, talks, gifts, favours, first_met, last_met, state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(npc, char_id) DO UPDATE SET "
            "affinity = excluded.affinity, talks = excluded.talks, gifts = excluded.gifts, "
            "favours = excluded.favours, first_met = excluded.first_met, last_met = excluded.last_met, "
            "state = excluded.state",
            (memory["npc"], memory["char_id"], int(memory["affinity"]), int(memory["talks"]), int(memory["gifts"]),
             int(memory["favours"]), float(memory["first_met"]), float(memory["last_met"]),
             json.dumps(memory.get("state") or {}, separators=(",", ":"))))

    def npc_memories_of(self, char_id):
        """[memory] of every resident who has met a character, the fondest first."""
        rows = self.db.execute("SELECT npc FROM npc_memory WHERE char_id = ? ORDER BY affinity DESC, npc",
                               (char_id,)).fetchall()
        return [self.npc_memory(row["npc"], char_id) for row in rows]

    # --- partnerships -------------------------------------------------------------------

    def partnership_of(self, char_id):
        """A character's partnership that hasn't ended (partners, engaged or married), or None."""
        row = self.db.execute(
            "SELECT * FROM partnerships WHERE (a = ? OR b = ?) AND status IN ('partners', 'engaged', 'married') "
            "ORDER BY id DESC LIMIT 1", (char_id, char_id)).fetchone()
        return dict(row) if row else None

    def partnership_by_id(self, pid):
        row = self.db.execute("SELECT * FROM partnerships WHERE id = ?", (pid,)).fetchone()
        return dict(row) if row else None

    def add_partnership(self, a, b, status, when):
        a, b = sorted((int(a), int(b)))
        cursor = self.db.execute("INSERT INTO partnerships (a, b, status, since, engaged) VALUES (?, ?, ?, ?, ?)",
                                 (a, b, status, float(when), float(when) if status == "engaged" else 0.0))
        return self.partnership_by_id(cursor.lastrowid)

    def save_partnership(self, p):
        self.db.execute("UPDATE partnerships SET status = ?, engaged = ?, married = ?, ended = ?, ended_by = ? "
                        "WHERE id = ?", (p["status"], float(p["engaged"]), float(p["married"]), float(p["ended"]),
                                         p.get("ended_by") or "", p["id"]))

    def last_partnership_end(self, char_id):
        row = self.db.execute("SELECT MAX(ended) AS t FROM partnerships WHERE (a = ? OR b = ?) AND status = 'ended'",
                              (char_id, char_id)).fetchone()
        return float(row["t"] or 0)

    # --- weddings -------------------------------------------------------------------------

    @staticmethod
    def _wedding(row):
        if row is None:
            return None
        wedding = dict(row)
        for name, empty in (("state", {}), ("memory", {})):
            try:
                value = json.loads(wedding.get(name) or "{}")
            except ValueError:
                value = {}
            wedding[name] = value if isinstance(value, dict) else dict(empty)
        return wedding

    def add_wedding(self, partnership, venue, tier, style, starts, ends, booked_by, paid):
        cursor = self.db.execute(
            "INSERT INTO weddings (partnership, venue, tier, style, starts, ends, status, booked_by, paid, created) "
            "VALUES (?, ?, ?, ?, ?, ?, 'booked', ?, ?, ?)",
            (partnership, venue, tier, style, float(starts), float(ends), booked_by, int(paid), self.clock()))
        return self.wedding_by_id(cursor.lastrowid)

    def wedding_by_id(self, wid):
        return self._wedding(self.db.execute("SELECT * FROM weddings WHERE id = ?", (wid,)).fetchone())

    def save_wedding(self, wedding):
        self.db.execute("UPDATE weddings SET venue = ?, tier = ?, style = ?, starts = ?, ends = ?, status = ?, "
                        "paid = ?, refunded = ?, state = ?, memory = ? WHERE id = ?",
                        (wedding["venue"], wedding["tier"], wedding["style"], float(wedding["starts"]),
                         float(wedding["ends"]), wedding["status"], int(wedding["paid"]), int(wedding["refunded"]),
                         json.dumps(wedding.get("state") or {}, separators=(",", ":")),
                         json.dumps(wedding.get("memory") or {}, separators=(",", ":")) if wedding.get("memory")
                         else "", wedding["id"]))

    def weddings_with(self, statuses):
        marks = ", ".join("?" for _s in statuses)
        rows = self.db.execute(f"SELECT * FROM weddings WHERE status IN ({marks}) ORDER BY starts, id",
                               tuple(statuses)).fetchall()
        return [self._wedding(row) for row in rows]

    def celebrations(self, since, venue=None):
        """Weddings under way, or done and still in their reception (it ends at `ends`) after `since`."""
        where = "(status = 'ceremony' OR (status = 'done' AND ends > ?))"
        args = (float(since),)
        if venue is not None:
            where += " AND venue = ?"
            args += (venue,)
        rows = self.db.execute(f"SELECT * FROM weddings WHERE {where} ORDER BY starts, id", args).fetchall()
        return [self._wedding(row) for row in rows]

    def weddings_of_partnership(self, pid, statuses=None):
        if statuses:
            marks = ", ".join("?" for _s in statuses)
            rows = self.db.execute(f"SELECT * FROM weddings WHERE partnership = ? AND status IN ({marks}) "
                                   "ORDER BY starts, id", (pid,) + tuple(statuses)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM weddings WHERE partnership = ? ORDER BY starts, id",
                                   (pid,)).fetchall()
        return [self._wedding(row) for row in rows]

    def weddings_in(self, venue, start, end, statuses):
        """Weddings at `venue` whose time overlaps [start, end)."""
        marks = ", ".join("?" for _s in statuses)
        rows = self.db.execute(f"SELECT * FROM weddings WHERE venue = ? AND status IN ({marks}) AND starts < ? "
                               "AND ends > ? ORDER BY starts", (venue,) + tuple(statuses) + (float(end), float(start))
                               ).fetchall()
        return [self._wedding(row) for row in rows]

    def last_wedding_of(self, char_id):
        """When a character's last wedding took place (0: never)."""
        row = self.db.execute(
            "SELECT MAX(w.starts) AS t FROM weddings w JOIN partnerships p ON p.id = w.partnership "
            "WHERE (p.a = ? OR p.b = ?) AND w.status = 'done'", (char_id, char_id)).fetchone()
        return float(row["t"] or 0)

    def memories_of(self, char_id):
        """Weddings a character married in, or went to as a guest: [(wedding, "couple" or "guest")]."""
        rows = self.db.execute(
            "SELECT w.*, CASE WHEN p.a = ? OR p.b = ? THEN 'couple' ELSE 'guest' END AS was FROM weddings w "
            "JOIN partnerships p ON p.id = w.partnership LEFT JOIN wedding_guests g ON g.wedding = w.id "
            "AND g.char_id = ? WHERE w.status = 'done' AND (p.a = ? OR p.b = ? OR g.attended = 1) "
            "ORDER BY w.starts DESC", (char_id,) * 5).fetchall()
        found = []
        for row in rows:
            was = row["was"]
            found.append((self._wedding(row), was))
        return found

    def add_guest(self, wedding_id, char_id, when):
        """True when newly invited."""
        cursor = self.db.execute("INSERT OR IGNORE INTO wedding_guests (wedding, char_id, invited) VALUES (?, ?, ?)",
                                 (wedding_id, char_id, float(when)))
        return cursor.rowcount == 1

    def set_guest(self, wedding_id, char_id, **fields):
        allowed = {"rsvp", "told", "attended"}
        sets = [(k, v) for k, v in fields.items() if k in allowed]
        if not sets:
            return
        self.db.execute(f"UPDATE wedding_guests SET {', '.join(f'{k} = ?' for k, _v in sets)} "
                        "WHERE wedding = ? AND char_id = ?", tuple(v for _k, v in sets) + (wedding_id, char_id))

    def guests_of(self, wedding_id):
        """[{char_id, name, rsvp, told, attended}] of a wedding, by when they were invited."""
        rows = self.db.execute(
            "SELECT g.char_id, c.name, c.name_key, g.rsvp, g.told, g.attended FROM wedding_guests g "
            "JOIN characters c ON c.id = g.char_id WHERE g.wedding = ? ORDER BY g.invited, c.name_key",
            (wedding_id,)).fetchall()
        return [dict(row) for row in rows]

    def invitations_of(self, char_id, statuses=("booked", "waiting", "ceremony")):
        """[(wedding, rsvp, told)] a character is invited to that are still to come."""
        marks = ", ".join("?" for _s in statuses)
        rows = self.db.execute(
            f"SELECT w.*, g.rsvp AS guest_rsvp, g.told AS guest_told FROM wedding_guests g "
            f"JOIN weddings w ON w.id = g.wedding WHERE g.char_id = ? AND w.status IN ({marks}) "
            "ORDER BY w.starts", (char_id,) + tuple(statuses)).fetchall()
        return [(self._wedding(row), row["guest_rsvp"], int(row["guest_told"])) for row in rows]

    # --- ships ------------------------------------------------------------------------------

    @staticmethod
    def _ship(row):
        ship = dict(row)
        for name, empty in (("cargo", {}), ("flight", None)):
            try:
                value = json.loads(ship.get(name) or "null")
            except ValueError:
                value = None
            ship[name] = value if isinstance(value, dict) else empty
        return ship

    def add_ship(self, owner_id, model, name, dock, fuel):
        cursor = self.db.execute("INSERT INTO ships (owner, model, name, dock, fuel, cargo, flight, created) "
                                 "VALUES (?, ?, ?, ?, ?, '{}', '', ?)",
                                 (owner_id, model, name, dock, float(fuel), self.clock()))
        return self.ship_by_id(cursor.lastrowid)

    def ship_by_id(self, ship_id):
        row = self.db.execute("SELECT * FROM ships WHERE id = ?", (ship_id,)).fetchone()
        return self._ship(row) if row else None

    def ship_of(self, owner_id):
        """A character's own ship, or None."""
        row = self.db.execute("SELECT * FROM ships WHERE owner = ?", (owner_id,)).fetchone()
        return self._ship(row) if row else None

    def save_ship(self, ship):
        self.db.execute("UPDATE ships SET model = ?, name = ?, dock = ?, fuel = ?, cargo = ?, flight = ? "
                        "WHERE id = ?",
                        (ship["model"], ship.get("name") or "", ship.get("dock") or "", float(ship.get("fuel") or 0),
                         json.dumps({k: int(v) for k, v in (ship.get("cargo") or {}).items() if int(v) > 0}),
                         json.dumps(ship["flight"]) if ship.get("flight") else "", ship["id"]))

    def flying_ships(self):
        rows = self.db.execute("SELECT * FROM ships WHERE flight != ''").fetchall()
        return [self._ship(row) for row in rows]

    # --- events -----------------------------------------------------------------------------

    @staticmethod
    def _event(row):
        event = dict(row)
        try:
            state = json.loads(event.get("state") or "{}")
        except ValueError:
            state = {}
        event["state"] = state if isinstance(state, dict) else {}
        return event

    def add_event(self, event, starts, ends, state, status, host="", message=""):
        cursor = self.db.execute(
            "INSERT INTO events (event, starts, ends, status, state, host, message, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event, float(starts), float(ends), status, json.dumps(state or {}), host or "", message or "",
             self.clock()))
        return self._event(self.db.execute("SELECT * FROM events WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def save_event(self, event):
        self.db.execute("UPDATE events SET starts = ?, ends = ?, status = ?, state = ?, host = ?, message = ? "
                        "WHERE id = ?",
                        (float(event["starts"]), float(event["ends"]), event["status"],
                         json.dumps(event.get("state") or {}), event.get("host") or "", event.get("message") or "",
                         event["id"]))

    def events_with(self, status):
        rows = self.db.execute("SELECT * FROM events WHERE status = ? ORDER BY starts, id", (status,)).fetchall()
        return [self._event(row) for row in rows]

    def add_event_points(self, event_id, char_id, points, when):
        self.db.execute("INSERT INTO event_players (event_id, char_id, points, last) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(event_id, char_id) DO UPDATE SET points = points + excluded.points, "
                        "last = excluded.last", (event_id, char_id, int(points), float(when)))

    def event_points(self, event_id, char_id):
        """How much a character took part in an event (0: not at all; a row with 0 points counts as 1)."""
        row = self.db.execute("SELECT points FROM event_players WHERE event_id = ? AND char_id = ?",
                              (event_id, char_id)).fetchone()
        return max(1, int(row["points"])) if row else 0

    def event_players(self, event_id):
        """[(char_id, points)] of everyone who took part, the most first."""
        rows = self.db.execute("SELECT char_id, points FROM event_players WHERE event_id = ? "
                               "ORDER BY points DESC, char_id", (event_id,)).fetchall()
        return [(row["char_id"], int(row["points"])) for row in rows]

    # --- the hunt -----------------------------------------------------------------------------

    def hunt_progress(self, season, char_id):
        row = self.db.execute("SELECT stage, attempts, wrong, cooldown, finished, place FROM hunt_progress "
                              "WHERE season = ? AND char_id = ?", (str(season), char_id)).fetchone()
        if row is None:
            return {"stage": 0, "attempts": 0, "wrong": 0, "cooldown": 0.0, "finished": 0.0, "place": 0}
        return dict(row)

    def save_hunt_progress(self, season, char_id, progress):
        self.db.execute(
            "INSERT INTO hunt_progress (season, char_id, stage, attempts, wrong, cooldown, finished, place) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(season, char_id) DO UPDATE SET stage = excluded.stage, "
            "attempts = excluded.attempts, wrong = excluded.wrong, cooldown = excluded.cooldown, "
            "finished = excluded.finished, place = excluded.place",
            (str(season), char_id, int(progress["stage"]), int(progress["attempts"]), int(progress["wrong"]),
             float(progress["cooldown"]), float(progress["finished"]), int(progress["place"])))

    def hunt_board(self, season, limit=10, exclude=()):
        """[(name, stage, finished, place)]: the finishers by place, then the furthest."""
        skip, keys = self._without(exclude)
        skip = skip.replace("name_key", "c.name_key")
        rows = self.db.execute(
            "SELECT c.name, h.stage, h.finished, h.place FROM hunt_progress h JOIN characters c ON c.id = h.char_id "
            f"WHERE h.season = ? AND c.banned = 0 AND (h.stage > 0 OR h.finished > 0){skip} "
            "ORDER BY h.finished = 0, h.place, h.stage DESC, c.name_key LIMIT ?",
            (str(season),) + keys + (int(limit),)).fetchall()
        return [(row["name"], int(row["stage"]), float(row["finished"]), int(row["place"])) for row in rows]

    def hunt_players(self, season):
        rows = self.db.execute(
            "SELECT c.name, h.* FROM hunt_progress h JOIN characters c ON c.id = h.char_id WHERE h.season = ? "
            "ORDER BY h.stage DESC, c.name_key", (str(season),)).fetchall()
        return [dict(row) for row in rows]

    # --- the arcade's high scores ---------------------------------------------------------

    def arcade_best(self, game, char_id):
        """A character's best score at a game, or None if they never played it."""
        row = self.db.execute("SELECT best FROM arcade_scores WHERE game = ? AND char_id = ?",
                              (game, char_id)).fetchone()
        return int(row["best"]) if row else None

    def save_arcade_score(self, game, char_id, score, when):
        """One more game played; the best kept (and when it was first reached)."""
        self.db.execute(
            "INSERT INTO arcade_scores (game, char_id, best, plays, last, best_at) VALUES (?, ?, ?, 1, ?, ?) "
            "ON CONFLICT(game, char_id) DO UPDATE SET plays = plays + 1, last = excluded.last, "
            "best_at = CASE WHEN excluded.best > best THEN excluded.best_at ELSE best_at END, "
            "best = MAX(best, excluded.best)",
            (game, char_id, int(score), float(when), float(when)))

    def arcade_top(self, game, limit=5):
        """[(name, best)]: the game's table, the earliest to reach a score first."""
        rows = self.db.execute(
            "SELECT c.name, a.best FROM arcade_scores a JOIN characters c ON c.id = a.char_id "
            "WHERE a.game = ? AND a.best > 0 AND c.banned = 0 ORDER BY a.best DESC, a.best_at, c.name_key LIMIT ?",
            (game, int(limit))).fetchall()
        return [(row["name"], int(row["best"])) for row in rows]

    # --- crews ------------------------------------------------------------------------------

    def create_crew(self, name, name_key, captain_id, when):
        with self.transaction():
            cur = self.db.execute("INSERT INTO crews (name, name_key, founded) VALUES (?, ?, ?)",
                                  (name, name_key, float(when)))
            self.add_crew_member(cur.lastrowid, captain_id, "captain", when)
        return cur.lastrowid

    def crew_by_id(self, crew_id):
        row = self.db.execute("SELECT * FROM crews WHERE id = ?", (crew_id,)).fetchone()
        return dict(row) if row else None

    def crew_by_key(self, name_key):
        row = self.db.execute("SELECT * FROM crews WHERE name_key = ?", (name_key,)).fetchone()
        return dict(row) if row else None

    def crew_of(self, char_id):
        """(the crew, the character's role in it), or None."""
        row = self.db.execute("SELECT c.*, m.role FROM crew_members m JOIN crews c ON c.id = m.crew_id "
                              "WHERE m.char_id = ?", (char_id,)).fetchone()
        if row is None:
            return None
        crew = dict(row)
        return crew, crew.pop("role")

    def crew_members(self, crew_id):
        """[{name, char_id, role, joined}], the captain first, then by when they joined."""
        rows = self.db.execute(
            "SELECT c.name, m.char_id, m.role, m.joined FROM crew_members m JOIN characters c ON c.id = m.char_id "
            "WHERE m.crew_id = ? ORDER BY m.role = 'captain' DESC, m.joined, m.char_id", (crew_id,)).fetchall()
        return [dict(row) for row in rows]

    def add_crew_member(self, crew_id, char_id, role, when):
        self.db.execute("INSERT INTO crew_members (char_id, crew_id, role, joined) VALUES (?, ?, ?, ?)",
                        (char_id, crew_id, role, float(when)))

    def remove_crew_member(self, char_id):
        self.db.execute("DELETE FROM crew_members WHERE char_id = ?", (char_id,))

    def set_crew_role(self, char_id, role):
        self.db.execute("UPDATE crew_members SET role = ? WHERE char_id = ?", (role, char_id))

    def set_crew_motto(self, crew_id, motto):
        self.db.execute("UPDATE crews SET motto = ? WHERE id = ?", (motto, crew_id))

    def add_crew_points(self, crew_id, points):
        self.db.execute("UPDATE crews SET points = points + ? WHERE id = ?", (int(points), crew_id))

    def delete_crew(self, crew_id):
        """A crew that ended (its last member left, or an admin disbanded it)."""
        with self.transaction():
            self.db.execute("DELETE FROM crew_members WHERE crew_id = ?", (crew_id,))
            self.db.execute("DELETE FROM crews WHERE id = ?", (crew_id,))

    def top_crews(self, limit=5):
        rows = self.db.execute(
            "SELECT c.name, c.points, COUNT(m.char_id) AS members FROM crews c "
            "JOIN crew_members m ON m.crew_id = c.id GROUP BY c.id "
            "ORDER BY c.points DESC, members DESC, c.founded LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]

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
