# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Following the files you change in the Dropbox folder until Dropbox has them.

The folder watcher reports a change; once the file has been quiet for a
moment, its details on Dropbox (files/get_metadata) are compared with the
file's: the same size and a "client_modified" time within 2 seconds of the
file's own (the desktop app sets it to the file's time). File contents are
never read or hashed, and online-only files are left alone.

  * Already the same, and Dropbox got it after the change: it synced at once.
  * Already the same, but Dropbox had it before the change: the desktop app
    downloaded it (someone else's work, told elsewhere): nothing to say.
  * Different or not there yet: it is syncing. It is checked again after 3,
    5, 10, 15, then every 20 seconds, and the remote feed (the long poll)
    says so at once when Dropbox gets it.
  * Still not there 3 minutes after the last change: one gentle warning.

What happens is gathered for a moment and told together (a Flush): files
that started syncing, files that synced, files that are late, and whether
everything is up to date. The wording is dropbox_text's. No wx here; the
clock and Dropbox are passed in, so tests drive it by hand.
"""

import collections
import os
import threading
import time

import dropbox_api
import dropbox_paths as paths

DEBOUNCE = 1.5            # quiet seconds after the last change before the first check
GROUP_SECONDS = 1.0       # news this close together is told together
HOLD_SECONDS = 8.0        # ...waiting at most this long for more
RETELL_SECONDS = 20.0     # files joining this soon after the last "syncing" news aren't told again
RECHECKS = (3.0, 5.0, 10.0, 15.0, 20.0)   # between checks of a syncing file; then the last
STUCK_SECONDS = 180.0     # not synced this long after the last change: say so, once
LATE_RECHECK = 60.0       # then check it this often
GIVE_UP_SECONDS = 1800.0  # and stop following it after this long
ERROR_RETRY = 15.0        # Dropbox didn't answer: try again after this long
MTIME_TOLERANCE = 2.0     # client_modified vs the file's time (FAT keeps 2-second times)
UPLOAD_TOLERANCE = 1.5    # Dropbox's time of the version vs when the change was seen
MAX_CALLS_PER_TICK = 8
BATCH_FROM = 4            # this many files due in one folder: list the folder once
MAX_TRACKED = 2000

WAITING, PENDING = "waiting", "pending"


def in_sync(info, meta, tolerance=MTIME_TOLERANCE):
    """Whether Dropbox's `meta` is the version of the file `info` describes."""
    if info is None or not isinstance(meta, dict) or meta.get(".tag") != "file":
        return False
    try:
        if int(meta.get("size", -1)) != info.size:
            return False
    except (TypeError, ValueError):
        return False
    client = dropbox_api.parse_time(meta.get("client_modified"))
    return client is not None and abs(client - info.mtime) <= tolerance


def uploaded_after(meta, seen_at, offset=0.0, tolerance=UPLOAD_TOLERANCE):
    """Whether Dropbox got this version after the change was seen here (our
    upload) rather than before (a download). `seen_at` is this computer's
    clock; `offset` is how far Dropbox's clock is ahead of it."""
    server = dropbox_api.parse_time((meta or {}).get("server_modified"))
    if server is None:
        return True
    return server >= seen_at + offset - tolerance


class Tracked:
    __slots__ = ("local", "key", "dropbox", "name", "first_seen", "last_change", "due", "state",
                 "checks", "warned", "reached")

    def __init__(self, local, dropbox_path, now):
        self.local = local
        self.key = local.casefold()
        self.dropbox = dropbox_path
        self.name = paths.name_of(local)
        self.first_seen = now
        self.last_change = now
        self.due = now + DEBOUNCE
        self.state = WAITING
        self.checks = 0
        self.warned = False
        self.reached = False      # the last check got an answer from Dropbox

    def __repr__(self):
        return f"Tracked({self.name!r}, {self.state})"


class Flush:
    """What to tell now.
      new         names that joined this round of syncing (syncing, or synced at once)
      synced      names that synced
      stuck       names still not synced a few minutes on
      up_to_date  nothing is left to sync
      session     every name synced or syncing since the last "up to date"
      remaining   how many are still syncing
      retold      `new` came soon after the last "syncing" news (a big copy):
                  not worth telling again
    """

    def __init__(self, new=(), synced=(), stuck=(), up_to_date=False, session=(), remaining=0,
                 retold=False):
        self.new = list(new)
        self.synced = list(synced)
        self.stuck = list(stuck)
        self.up_to_date = up_to_date
        self.session = list(session)
        self.remaining = remaining
        self.retold = retold

    def __repr__(self):
        return (f"Flush(new={self.new}, synced={self.synced}, stuck={self.stuck}, "
                f"up_to_date={self.up_to_date}, session={self.session}, "
                f"remaining={self.remaining}, retold={self.retold})")


class SyncTracker:
    """`root` is the Dropbox folder. `source` answers metadata(path) (a dict,
    or None when Dropbox has nothing there), folder(path) (its entries) and
    server_offset(); the first two raise dropbox_api.DropboxError when
    Dropbox can't be asked. local_events() and server_saw() may be called
    from any thread; tick() from one thread only (it asks Dropbox)."""

    def __init__(self, root, source, stat=paths.file_info, clock=time.time,
                 ignored=paths.marked_ignored):
        self.root = root
        self.source = source
        self.stat = stat
        self.clock = clock
        self.ignored = ignored
        self._inbox = collections.deque()
        self._server = collections.deque()
        self._tracked = {}              # Tracked.key -> Tracked
        self._session = {}              # Tracked.key -> name, in order
        self._session_synced = 0
        self._last_new_told = None
        self._new, self._synced, self._stuck = [], [], []     # [(key, name)]
        self._out_first = None
        self._out_last = None
        self._snapshot_lock = threading.Lock()
        self._snapshot = {"pending": [], "stuck": []}

    # --- what comes in (any thread) ---------------------------------------------------

    def local_events(self, events, now=None):
        """[(action, path relative to the Dropbox folder)] from the watcher."""
        now = self.clock() if now is None else now
        for action, relative in events:
            self._inbox.append((action, relative, now))

    def server_saw(self, entries):
        """Entries Dropbox reported changed (the remote feed): a file still
        syncing may be done."""
        for entry in entries or ():
            if isinstance(entry, dict) and entry.get(".tag") == "file":
                self._server.append(entry)

    # --- status (any thread) ----------------------------------------------------------

    def status(self):
        """{"pending": [names syncing], "stuck": [names late]}."""
        with self._snapshot_lock:
            return {k: list(v) for k, v in self._snapshot.items()}

    def _update_snapshot(self):
        pending = [t for t in self._tracked.values() if t.state == PENDING]
        with self._snapshot_lock:
            self._snapshot = {"pending": [t.name for t in pending],
                              "stuck": [t.name for t in pending if t.warned]}

    # --- the work (one thread) --------------------------------------------------------

    def tick(self, now=None):
        """Handle what came in, check the files that are due, and return a
        Flush when there is something to tell (else None)."""
        now = self.clock() if now is None else now
        self._take_events()
        self._take_server(now)
        self._check_due(now)
        self._watch_late(now)
        flush = self._flush(now)
        self._update_snapshot()
        return flush

    def _take_events(self):
        while self._inbox:
            action, relative, when = self._inbox.popleft()
            if action == "overflow" or paths.ignored_relative(relative):
                continue
            local = os.path.join(self.root, relative)
            tracked = self._tracked.get(local.casefold())
            if action in ("removed", "renamed_from"):
                if tracked is not None:
                    self._drop(tracked)
                continue
            if tracked is not None:
                tracked.last_change = when
                tracked.due = when + DEBOUNCE
                tracked.warned = False
                continue
            if len(self._tracked) >= MAX_TRACKED:
                continue
            dropbox_path = paths.to_dropbox(local, self.root)
            if not dropbox_path:
                continue
            tracked = Tracked(local, dropbox_path, when)
            self._tracked[tracked.key] = tracked

    def _take_server(self, now):
        if not self._server:
            return
        by_path = {}
        while self._server:
            entry = self._server.popleft()
            for field in ("path_display", "path_lower"):
                if entry.get(field):
                    by_path[paths.key(entry[field])] = entry
        for tracked in list(self._tracked.values()):
            if tracked.state != PENDING:
                continue            # a first check tells a download from an upload itself
            entry = by_path.get(paths.key(tracked.dropbox))
            if entry is not None and in_sync(self.stat(tracked.local), entry):
                self._synced_now(tracked, now)

    def _check_due(self, now):
        due = sorted((t for t in self._tracked.values() if t.due <= now), key=lambda t: t.due)
        if not due:
            return
        groups = collections.OrderedDict()
        for tracked in due:
            groups.setdefault(paths.key(paths.parent_path(tracked.dropbox)), []).append(tracked)
        calls = 0
        for group in groups.values():
            if calls >= MAX_CALLS_PER_TICK:
                break
            if len(group) >= BATCH_FROM:
                calls += 1
                self._check_folder(group, now)
                continue
            for tracked in group:
                if calls >= MAX_CALLS_PER_TICK:
                    break
                info = self._precheck(tracked, now)
                if info is None:
                    continue
                calls += 1
                try:
                    meta = self.source.metadata(tracked.dropbox)
                except dropbox_api.DropboxError as e:
                    self._unanswered(tracked, now, e)
                    continue
                self._judge(tracked, now, meta, info)

    def _check_folder(self, group, now):
        """Many files due in one folder: one listing of it answers them all."""
        try:
            entries = self.source.folder(paths.parent_path(group[0].dropbox))
        except dropbox_api.DropboxError as e:
            for tracked in group:
                self._unanswered(tracked, now, e)
            return
        listed = {}
        for entry in entries or ():
            if isinstance(entry, dict):
                for field in ("path_display", "path_lower"):
                    if entry.get(field):
                        listed[paths.key(entry[field])] = entry
        for tracked in group:
            info = self._precheck(tracked, now)
            if info is not None:
                self._judge(tracked, now, listed.get(paths.key(tracked.dropbox)), info)

    def _precheck(self, tracked, now):
        """The file's details if Dropbox still needs asking about it; None
        when it has been dealt with (gone, a folder, online-only, ignored)."""
        info = self.stat(tracked.local)
        if info is None or info.is_dir:
            self._drop(tracked)
            return None
        if tracked.state == WAITING:
            if info.online_only or info.temporary or self.ignored(tracked.local, self.root):
                self._drop(tracked)
                return None
        elif info.online_only:
            # Dropbox only makes a file online-only once the cloud has it.
            self._synced_now(tracked, now)
            return None
        return info

    def _unanswered(self, tracked, now, error):
        tracked.reached = False
        wait = ERROR_RETRY
        if getattr(error, "kind", "") == "rate":
            wait = max(wait, float(getattr(error, "retry_after", 0) or 0))
        tracked.due = now + wait

    def _judge(self, tracked, now, meta, info):
        tracked.reached = True
        synced = in_sync(info, meta)
        if tracked.state == WAITING:
            if synced:
                if uploaded_after(meta, tracked.first_seen, self.source.server_offset()):
                    self._join(tracked, now)
                    self._synced_now(tracked, now)
                else:
                    self._drop(tracked)          # the desktop app downloaded it
                return
            tracked.state = PENDING
            tracked.checks = 1
            tracked.due = now + RECHECKS[0]
            self._join(tracked, now)
            return
        if synced:
            self._synced_now(tracked, now)
            return
        tracked.checks += 1
        if tracked.warned:
            tracked.due = now + LATE_RECHECK
        else:
            tracked.due = now + RECHECKS[min(tracked.checks - 1, len(RECHECKS) - 1)]

    def _watch_late(self, now):
        for tracked in list(self._tracked.values()):
            if tracked.state != PENDING:
                continue
            quiet = now - tracked.last_change
            if quiet >= GIVE_UP_SECONDS:
                self._drop(tracked)
            elif quiet >= STUCK_SECONDS and not tracked.warned and tracked.reached:
                tracked.warned = True
                tracked.due = max(tracked.due, now + LATE_RECHECK)
                self._note(self._stuck, tracked, now)

    # --- bookkeeping ------------------------------------------------------------------

    def _join(self, tracked, now):
        self._session.setdefault(tracked.key, tracked.name)
        self._note(self._new, tracked, now)

    def _synced_now(self, tracked, now):
        self._tracked.pop(tracked.key, None)
        self._session.setdefault(tracked.key, tracked.name)
        self._session_synced += 1
        self._note(self._synced, tracked, now)

    def _drop(self, tracked):
        self._tracked.pop(tracked.key, None)
        if tracked.state == PENDING and tracked.key in self._session:
            del self._session[tracked.key]
            for bucket in (self._new, self._stuck):
                bucket[:] = [item for item in bucket if item[0] != tracked.key]

    def _note(self, bucket, tracked, now):
        if all(k != tracked.key for k, _name in bucket):
            bucket.append((tracked.key, tracked.name))
        if self._out_first is None:
            self._out_first = now
        self._out_last = now

    def _flush(self, now):
        waiting = any(t.state == WAITING for t in self._tracked.values())
        pending = sum(1 for t in self._tracked.values() if t.state == PENDING)
        if not (self._new or self._synced or self._stuck):
            self._out_first = self._out_last = None
            if not self._tracked and self._session:
                # The last files syncing went away (deleted, or given up on).
                done = self._session_synced > 0
                session = list(self._session.values())
                self._reset_session()
                return Flush(up_to_date=True, session=session) if done else None
            return None
        if now - self._out_first < HOLD_SECONDS:
            if now - self._out_last < GROUP_SECONDS:
                return None              # more may be coming
            if waiting:
                return None              # a file still being checked may be part of this
        up_to_date = not self._tracked
        retold = False
        if self._new:
            retold = self._last_new_told is not None and \
                now - self._last_new_told < RETELL_SECONDS
            self._last_new_told = now
        flush = Flush([n for _k, n in self._new], [n for _k, n in self._synced],
                      [n for _k, n in self._stuck], up_to_date, list(self._session.values()),
                      pending, retold)
        self._new, self._synced, self._stuck = [], [], []
        self._out_first = self._out_last = None
        if up_to_date:
            self._reset_session()
        return flush

    def _reset_session(self):
        self._session = {}
        self._session_synced = 0
        self._last_new_told = None

    def clear(self):
        """Forget everything (Dropbox was turned off)."""
        self._inbox.clear()
        self._server.clear()
        self._tracked.clear()
        self._reset_session()
        self._new, self._synced, self._stuck = [], [], []
        self._out_first = self._out_last = None
        self._update_snapshot()
