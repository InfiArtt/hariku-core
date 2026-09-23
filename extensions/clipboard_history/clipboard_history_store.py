# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The clipboard history itself (no wx) and how it is kept on disk.

Items are dicts {"id", "text", "time", "pinned"}. The list is kept in display
order: pinned items first, then the rest, newest first within each group.

Two data files, through core.api:
  ClipboardHistory       - settings only, never any copied text
  ClipboardHistoryItems  - saved items: all of them when "Remember history" is
                           on, otherwise only the pinned ones. Deleted when
                           there is nothing to keep.
Writes run on a worker thread (Writer), and the ".bak" copy core.api keeps is
removed after every write, because it would still hold deleted text.
"""

import logging
import os
import threading
import time
import uuid

import core.api

logger = logging.getLogger(__name__)

SETTINGS_KEY = "ClipboardHistory"
ITEMS_KEY = "ClipboardHistoryItems"

MAX_TEXT_BYTES = 100 * 1024
SIZES = (25, 50, 100)
DEFAULT_SIZE = 50
DEFAULT_SETTINGS = {"limit": DEFAULT_SIZE, "remember": False, "paused": False}


# ------------------------------------------------------------
# Rules
# ------------------------------------------------------------

def text_problem(text):
    """Why `text` is not recorded ("empty" or "too_large"), or None."""
    if not isinstance(text, str) or not text:
        return "empty"
    # Checked before strip() so a huge text costs nothing more.
    if len(text) > MAX_TEXT_BYTES:
        return "too_large"
    if len(text) * 4 > MAX_TEXT_BYTES and \
            len(text.encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES:
        return "too_large"
    if not text.strip():
        return "empty"
    return None


def make_item(text, now, pinned=False):
    return {"id": uuid.uuid4().hex, "text": text, "time": float(now), "pinned": bool(pinned)}


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    limit = raw.get("limit")
    return {
        "limit": int(limit) if limit in SIZES and not isinstance(limit, bool) else DEFAULT_SIZE,
        "remember": raw.get("remember") is True,
        "paused": raw.get("paused") is True,
    }


def normalize_items(raw, limit=DEFAULT_SIZE, now=None):
    """Valid items from saved data, in display order, without duplicates."""
    if isinstance(raw, dict):
        raw = raw.get("items")
    if not isinstance(raw, list):
        return []
    now = time.time() if now is None else now
    seen_ids, seen_texts, items = set(), set(), []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        text = entry.get("text")
        if text_problem(text) or text in seen_texts:
            continue
        item_id = entry.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in seen_ids:
            item_id = uuid.uuid4().hex
        stamp = entry.get("time")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) \
                or not 0 <= stamp <= now + 86400:
            stamp = now     # also catches NaN and infinity
        seen_ids.add(item_id)
        seen_texts.add(text)
        items.append({"id": item_id, "text": text, "time": float(stamp),
                      "pinned": entry.get("pinned") is True})
    history = History(limit, items)
    return history.items


def signature(items):
    """Cheap fingerprint of a snapshot, to skip writes that change nothing."""
    return tuple((i["id"], i["pinned"], i["time"]) for i in items)


# ------------------------------------------------------------
# History
# ------------------------------------------------------------

class History:
    def __init__(self, limit=DEFAULT_SIZE, items=None):
        self.limit = limit if limit in SIZES else DEFAULT_SIZE
        items = list(items or [])
        self.items = [i for i in items if i["pinned"]] + [i for i in items if not i["pinned"]]
        # The last recorded copy. Kept explicitly: timestamps can tie (the
        # Windows clock ticks every ~16 ms) or go backwards.
        self._last_id = None
        self.trim()

    def __len__(self):
        return len(self.items)

    def pinned_count(self):
        return sum(1 for i in self.items if i["pinned"])

    def find(self, item_id):
        for item in self.items:
            if item["id"] == item_id:
                return item
        return None

    def find_text(self, text):
        for item in self.items:
            if item["text"] == text:
                return item
        return None

    def latest(self):
        """The most recently copied item, or None."""
        item = self.find(self._last_id) if self._last_id else None
        if item is not None:
            return item
        return max(self.items, key=lambda i: i["time"]) if self.items else None

    def add(self, text, now=None):
        """Record a copy. Returns (item or None, status): "added", "moved" (an
        identical item went to the top), "duplicate" (same as the last copy),
        "empty" or "too_large"."""
        problem = text_problem(text)
        if problem:
            return None, problem
        now = time.time() if now is None else now
        existing = self.find_text(text)
        if existing is not None:
            if existing is self.latest():
                return existing, "duplicate"
            existing["time"] = float(now)
            self._move_to_top(existing)
            self._last_id = existing["id"]
            return existing, "moved"
        item = make_item(text, now)
        self._insert_top(item)
        self._last_id = item["id"]
        self.trim()
        return item, "added"

    def _insert_top(self, item):
        self.items.insert(0 if item["pinned"] else self.pinned_count(), item)

    def _move_to_top(self, item):
        self.items.remove(item)
        self._insert_top(item)

    def toggle_pin(self, item_id):
        """Pin or unpin; the item moves to the top of its new group."""
        item = self.find(item_id)
        if item is None:
            return None
        item["pinned"] = not item["pinned"]
        self._move_to_top(item)
        self.trim()
        return item

    def delete(self, item_id):
        item = self.find(item_id)
        if item is not None:
            self.items.remove(item)
        return item

    def clear(self):
        """Delete every unpinned item. Returns (deleted, pinned kept)."""
        kept = [i for i in self.items if i["pinned"]]
        removed = len(self.items) - len(kept)
        self.items = kept
        return removed, len(kept)

    def set_limit(self, limit):
        self.limit = limit if limit in SIZES else DEFAULT_SIZE
        return self.trim()

    def trim(self):
        """Drop the oldest unpinned items beyond the limit; pinned ones stay.
        Returns how many were dropped."""
        unpinned = [i for i in self.items if not i["pinned"]]
        extra = unpinned[self.limit:]
        if not extra:
            return 0
        drop = {id(i) for i in extra}
        self.items = [i for i in self.items if id(i) not in drop]
        return len(extra)

    def snapshot(self, pinned_only=False):
        """Copies of the items to save (strings are shared, so this is cheap)."""
        return [dict(i) for i in self.items if i["pinned"] or not pinned_only]


# ------------------------------------------------------------
# Disk
# ------------------------------------------------------------

def load_settings():
    return normalize_settings(core.api.load_data(SETTINGS_KEY))


def save_settings(settings):
    return core.api.save_data(SETTINGS_KEY, normalize_settings(settings))


def items_path():
    return core.api.get_data_path(ITEMS_KEY)


def load_items(limit=DEFAULT_SIZE, now=None):
    if not os.path.exists(items_path()):
        return []
    return normalize_items(core.api.load_data(ITEMS_KEY), limit, now)


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(f"[Clipboard History] Could not delete {os.path.basename(path)}: {e}")
        return False
    return True


def remove_backup():
    return _remove(items_path() + ".bak")


def _disk_safe(text):
    # A lone surrogate from the clipboard would make the whole file unwritable.
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return text.encode("utf-8", "surrogatepass").decode("utf-8", "replace")


def write_items(items):
    """Save `items`, or delete the file when there is nothing to keep. Runs on
    the writer thread."""
    if items:
        data = {"version": 1,
                "items": [dict(i, text=_disk_safe(i["text"])) for i in items]}
        ok = core.api.save_data(ITEMS_KEY, data)
    else:
        ok = _remove(items_path())
    return remove_backup() and ok


def _start_daemon(target):
    threading.Thread(target=target, daemon=True, name="clipboard-history-save").start()


class Writer:
    """Runs write(snapshot) on a worker thread, one write at a time; while one
    runs, only the newest pending snapshot is kept."""

    _NOTHING = object()

    def __init__(self, write, start=None):
        self._write = write
        self._start = start or _start_daemon
        self._lock = threading.Lock()
        self._pending = self._NOTHING
        self._running = False
        self._idle = threading.Event()
        self._idle.set()

    def submit(self, snapshot):
        with self._lock:
            self._pending = snapshot
            if self._running:
                return
            self._running = True
            self._idle.clear()
        try:
            self._start(self._run)
        except Exception:
            logger.exception("[Clipboard History] Could not start the save thread")
            with self._lock:
                self._running = False
                self._idle.set()

    def _run(self):
        while True:
            with self._lock:
                snapshot, self._pending = self._pending, self._NOTHING
                if snapshot is self._NOTHING:
                    self._running = False
                    self._idle.set()
                    return
            try:
                self._write(snapshot)
            except Exception:
                logger.exception("[Clipboard History] Saving the history failed")

    def flush(self, timeout=5.0):
        """Wait until every submitted snapshot is written. True if done."""
        return self._idle.wait(timeout)
