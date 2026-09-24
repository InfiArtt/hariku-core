# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Edge Voices' files in %APPDATA%\\Hariku2\\voice_cache\\edge:

  <sha256>.mp3  speech already synthesized, named by a hash of the voice, the
                rate and the text, so a phrase said again (the greeting) plays
                at once and without the internet. Least recently used files go
                first once the folder is over its limit (30 MB).
  voices.json   the voice list, used for 7 days, and longer when offline.
"""
import hashlib
import json
import os
import time

AUDIO_SUFFIX = ".mp3"
VOICE_LIST_FILE = "voices.json"
DEFAULT_LIMIT_BYTES = 30 * 1024 * 1024


def _write_atomically(path, data):
    temporary = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temporary, "wb") as f:
            f.write(data)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


class AudioCache:
    def __init__(self, directory, limit_bytes=DEFAULT_LIMIT_BYTES):
        self.directory = directory
        self.limit_bytes = limit_bytes

    @staticmethod
    def key(voice, rate, text):
        blob = json.dumps([voice, rate, text], ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def path(self, key):
        return os.path.join(self.directory, key + AUDIO_SUFFIX)

    def get(self, key):
        """The cached file for `key`, marked as just used; None if absent."""
        path = self.path(key)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return None
        try:
            os.utime(path, None)
        except OSError:
            pass
        return path

    def put(self, key, data):
        """Save `data` under `key`, then trim the cache; returns the file."""
        os.makedirs(self.directory, exist_ok=True)
        path = self.path(key)
        _write_atomically(path, bytes(data))
        self.evict(keep=path)
        return path

    def entries(self):
        """[(last used, size, path)] of the cached audio, oldest first."""
        found = []
        try:
            names = os.listdir(self.directory)
        except OSError:
            return found
        for name in names:
            if not name.endswith(AUDIO_SUFFIX):
                continue
            path = os.path.join(self.directory, name)
            try:
                info = os.stat(path)
            except OSError:
                continue
            found.append((info.st_mtime, info.st_size, path))
        found.sort()
        return found

    def size(self):
        return sum(size for _mtime, size, _path in self.entries())

    def evict(self, keep=None):
        """Remove the least recently used files until the cache fits its limit.
        `keep` (the file about to play) and files in use are left alone."""
        entries = self.entries()
        total = sum(size for _mtime, size, _path in entries)
        for _mtime, size, path in entries:
            if total <= self.limit_bytes:
                break
            if keep and os.path.normcase(path) == os.path.normcase(keep):
                continue
            try:
                os.remove(path)
                total -= size
            except OSError:
                pass        # playing right now; it goes next time
        return total


def load_voice_list(directory, max_age=None, now=None):
    """The saved voice list if it is at most `max_age` seconds old (any age
    when None), else None."""
    path = os.path.join(directory, VOICE_LIST_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("voices"), list):
        return None
    saved_at = data.get("saved_at")
    if not isinstance(saved_at, (int, float)):
        return None
    now = time.time() if now is None else now
    if max_age is not None and not (0 <= now - saved_at <= max_age):
        return None
    return [v for v in data["voices"] if isinstance(v, dict) and isinstance(v.get("id"), str)]


def save_voice_list(directory, voices, now=None):
    os.makedirs(directory, exist_ok=True)
    data = {"saved_at": time.time() if now is None else now, "voices": list(voices)}
    _write_atomically(os.path.join(directory, VOICE_LIST_FILE),
                      json.dumps(data, ensure_ascii=False).encode("utf-8"))
