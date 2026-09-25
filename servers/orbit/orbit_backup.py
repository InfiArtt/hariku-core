#!/usr/bin/env python3
# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
A copy of Orbit's database, safe to make while the server runs, keeping the
newest few.

    python3 orbit_backup.py --db ~/orbit/orbit.db --dir ~/orbit/backups --keep 7

SQLite's online backup copies a consistent snapshot even while the server
writes (it waits for a write in progress, and it reads the WAL too). Each
copy is checked (PRAGMA quick_check) before the oldest ones are removed, so
a bad copy never pushes out a good one. orbit-backup.service and
orbit-backup.timer run it once a day as a systemd user timer (see README.md).
Standard library only.
"""

import argparse
import datetime
import os
import sqlite3
import sys

PREFIX = "orbit-"
SUFFIX = ".db"


def backup(db_path, folder, keep=7, now=None):
    """Copy `db_path` into `folder` and keep the newest `keep` copies. Returns the new file."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(db_path)
    os.makedirs(folder, exist_ok=True)
    now = now or datetime.datetime.now()
    name = f"{PREFIX}{now.strftime('%Y%m%d-%H%M%S')}{SUFFIX}"
    target = os.path.join(folder, name)
    partial = target + ".part"
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        copy = sqlite3.connect(partial)
        try:
            source.backup(copy)
            result = copy.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            copy.close()
    finally:
        source.close()
    if result != "ok":
        os.remove(partial)
        raise RuntimeError(f"the copy failed its check: {result}")
    os.replace(partial, target)
    copies = sorted(f for f in os.listdir(folder) if f.startswith(PREFIX) and f.endswith(SUFFIX))
    for old in copies[:-max(1, int(keep))]:
        os.remove(os.path.join(folder, old))
    return target


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Back up Orbit's database while the server runs.")
    parser.add_argument("--db", default=os.path.join(here, "orbit.db"), help="the database (orbit.db)")
    parser.add_argument("--dir", default=os.path.join(here, "backups"), help="where the copies go")
    parser.add_argument("--keep", type=int, default=7, help="how many copies to keep (7)")
    args = parser.parse_args(argv)
    try:
        path = backup(args.db, args.dir, args.keep)
    except (OSError, sqlite3.Error, RuntimeError) as e:
        print(f"Orbit backup failed: {e}", file=sys.stderr)
        return 1
    print(f"Orbit backup: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
