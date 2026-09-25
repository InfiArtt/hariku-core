# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What happens on Dropbox's side:

  RemoteFeed     waits for changes with a long poll (files/list_folder/
                 longpoll, which needs no token and returns as soon as
                 something changes), then reads them (list_folder/continue).
                 Its own thread; it backs off after errors and when Dropbox
                 asks it to.
  OthersBuffer   keeps the changes other people made in shared folders for a
                 moment, so a burst is told in one line per person.
  summarize()    turns them into who changed what where (added or changed).
  SharedWatcher  the files and folders shared with you; the first look only
                 remembers what is there, later looks find what is new.

No wx here; Dropbox (a dropbox_api.Client) and the clock are passed in.
"""

import logging
import threading
import time

import dropbox_api
import dropbox_paths as paths

logger = logging.getLogger(__name__)

GROUP_SECONDS = 5.0        # others' changes this close together are told together
MAX_HOLD = 20.0            # ...but no later than this after the first
MAX_BACKOFF = 300.0
REVISION_CHECKS = 3        # files per person asked "is it new?"


def others_changes(entries, own_id):
    """The files other people changed: entries inside shared folders
    (sharing_info.modified_by) whose last change wasn't this account's."""
    found = []
    for entry in entries or ():
        if not isinstance(entry, dict) or entry.get(".tag") != "file":
            continue
        by = (entry.get("sharing_info") or {}).get("modified_by")
        if by and by != own_id:
            found.append(entry)
    return found


class OthersBuffer:
    """Changes by other people, told a moment after the burst ends."""

    def __init__(self):
        self._lock = threading.Lock()
        self._entries = {}           # path key -> entry (the latest change of a file)
        self._first = None
        self._last = None

    def add(self, entries, now):
        if not entries:
            return
        with self._lock:
            for entry in entries:
                self._entries[paths.key(entry.get("path_display") or entry.get("path_lower"))] = entry
            if self._first is None:
                self._first = now
            self._last = now

    def take(self, now):
        """The gathered entries once the burst is over, else []."""
        with self._lock:
            if not self._entries:
                return []
            if now - self._last < GROUP_SECONDS and now - self._first < MAX_HOLD:
                return []
            entries = list(self._entries.values())
            self._entries = {}
            self._first = self._last = None
            return entries

    def clear(self):
        with self._lock:
            self._entries = {}
            self._first = self._last = None


def summarize(entries, name_of, is_new):
    """[{"person", "count", "name", "folder", "added"}], one per person,
    most changes first. `name_of(account_id)` gives a display name ("" when
    unknown); `is_new(path)` whether a file has only one revision (None when
    it can't tell). "folder" is the one folder all of them are in, "" when
    they are at the top, None when they are spread over several."""
    by_person = {}
    for entry in entries:
        by_person.setdefault(entry["sharing_info"]["modified_by"], []).append(entry)
    found = []
    for account_id, group in by_person.items():
        group.sort(key=lambda e: str(e.get("server_modified") or ""))
        folders = {paths.key(paths.parent_path(e.get("path_display") or "")) for e in group}
        folder = paths.parent_name(group[0].get("path_display") or "") if len(folders) == 1 else None
        added = True
        for entry in group[:REVISION_CHECKS]:
            new = is_new(entry.get("path_display") or entry.get("path_lower"))
            if not new:
                added = False
                break
        found.append({"person": name_of(account_id), "count": len(group),
                      "name": group[0].get("name") or paths.name_of(group[0].get("path_display")),
                      "folder": folder, "added": added})
    found.sort(key=lambda item: -item["count"])
    return found


class RemoteFeed:
    """Follows every change in the account. on_entries(entries) is called on
    the feed's thread; on_auth_lost() when the sign-in stopped working."""

    def __init__(self, client, on_entries, on_auth_lost=None, clock=time.monotonic):
        self.client = client
        self.on_entries = on_entries
        self.on_auth_lost = on_auth_lost
        self.clock = clock
        self.cursor = None
        self.failures = 0
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="dropbox-remote")
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.is_set()

    def _run(self):
        while not self._stop.is_set():
            try:
                wait = self.step()
            except Exception:
                logger.exception("[Dropbox] The remote feed failed")
                wait = self._backoff()
            if wait is None:
                return
            if wait > 0 and self._stop.wait(wait):
                return

    def _backoff(self):
        self.failures += 1
        return min(MAX_BACKOFF, 5.0 * (2 ** min(self.failures - 1, 6)))

    def step(self):
        """One round: returns the seconds to wait before the next (0: go on),
        or None to stop for good (the sign-in is gone)."""
        try:
            if self.cursor is None:
                self.cursor = self.client.latest_cursor("", recursive=True)
                self.failures = 0
                return 0
            answer = self.client.longpoll(self.cursor)
            if self._stop.is_set():
                return None
            wait = 0.0
            try:
                wait = float(answer.get("backoff") or 0)
            except (TypeError, ValueError):
                wait = 0.0
            if answer.get("changes"):
                entries, self.cursor = self.client.changes_since(self.cursor)
                if entries and not self._stop.is_set():
                    self.on_entries(entries)
            self.failures = 0
            return wait
        except dropbox_api.DropboxError as e:
            if self._stop.is_set():
                return None
            if e.kind == "auth":
                if self.on_auth_lost is not None:
                    self.on_auth_lost()
                return None
            if e.kind == "api" and "reset" in e.summary:
                self.cursor = None          # Dropbox forgot the cursor: start from now
                return 1.0
            if e.kind == "rate":
                return float(e.retry_after or 60)
            if e.kind != "network":
                logger.warning(f"[Dropbox] The remote feed: {e}")
            return self._backoff()


class SharedWatcher:
    """Files and folders other people shared with this account. `store` has
    load() -> {"account": id, "ids": [...]} or {} and save(dict)."""

    def __init__(self, client, store, own_id):
        self.client = client
        self.store = store
        self.own_id = own_id

    def current(self):
        """{id: {"kind", "name", "owner"}} of everything shared with you now."""
        found = {}
        for entry in self.client.received_files():
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            if (entry.get("access_type") or {}).get(".tag") == "owner":
                continue
            found["file:" + str(entry["id"])] = {
                "kind": "file", "name": entry.get("name") or "",
                "owner": _first(entry.get("owner_display_names"))}
        for entry in self.client.shared_folders():
            if not isinstance(entry, dict) or not entry.get("shared_folder_id"):
                continue
            if (entry.get("access_type") or {}).get(".tag") == "owner":
                continue                    # a folder you shared yourself
            found["folder:" + str(entry["shared_folder_id"])] = {
                "kind": "folder", "name": entry.get("name") or "",
                "owner": _first(entry.get("owner_display_names"))}
        return found

    def poll(self):
        """What was shared since the last look: [{"kind", "name", "owner"}].
        The first look for an account only remembers."""
        now = self.current()
        saved = self.store.load() or {}
        known = set(saved.get("ids") or []) if saved.get("account") == self.own_id else None
        self.store.save({"account": self.own_id, "ids": sorted(now)})
        if known is None:
            return []
        return [now[i] for i in sorted(now) if i not in known]


def _first(names):
    if isinstance(names, list):
        for name in names:
            if isinstance(name, str) and name.strip():
                return name.strip()
    return ""
