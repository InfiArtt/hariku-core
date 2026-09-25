# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Who says what in Orbit: the narrator (Hariku Voice's own voice; the screen
reader only when Hariku Voice can't speak) for the station and your own
actions, and a character voice for each player, you included, when Hariku
Voice has several voices of your language. A line can come in parts: the
speaker's name in the narrator's voice ("Budi:"), then the words in Budi's.

A player's voice is chosen from their name, so Sari always sounds like Sari
(on this computer, with these voices): the voices of the language, sorted,
and the name's SHA-256 picks one. Your own Hariku Voice is left out when
there are enough others. With fewer than two voices everyone is read by the
narrator.

Speaker says lines one after another, and the parts of a line together:
a voice (core.voice.preview, which would cut off whatever Hariku Voice was
saying) only starts once the one before is quiet, so nobody talks over
anybody, and a busy room drops whole old lines, never half of one. A voice
that fails reads its part with the narrator instead. No wx; main.py's
services do the speaking.
"""

import collections
import hashlib
import threading
import time

MAX_WAITING = 12                  # a busy room: older lines are only shown, not read
READER_SECONDS_PER_CHAR = 0.05    # a guess at how long a screen reader takes...
READER_MIN_SECONDS = 0.5
READER_MAX_SECONDS = 8.0          # ...but a player's voice never waits longer than this
POLL_SECONDS = 0.15
MAX_AGE_SECONDS = 600.0


def primary(tag):
    return str(tag or "").replace("_", "-").split("-")[0].strip().lower()


def reader_seconds(text):
    """About how long the screen reader takes to read `text` (the Observation
    Deck's view is long; people often cut the reader short by typing)."""
    return min(READER_MAX_SECONDS, READER_MIN_SECONDS + len(text or "") * READER_SECONDS_PER_CHAR)


def voices_of(voices_by_provider, language):
    """[{"provider", "id", "name", "language"}] of `language` ("id", "en"),
    sorted so the same voices always come in the same order."""
    found = []
    for provider, voices in (voices_by_provider or {}).items():
        for voice in voices or []:
            if primary(voice.get("language")) == language and voice.get("id") is not None:
                found.append(dict(voice, provider=provider))
    return sorted(found, key=lambda v: (str(v["provider"]), str(v["id"])))


def _pool(voices, exclude):
    pool = list(voices or [])
    if exclude and len(pool) > 2:
        pool = [v for v in pool if (v["provider"], v["id"]) != tuple(exclude)] or pool
    return pool


def pool_size(voices, exclude=None):
    """How many voices players are given voices from (pick_voice needs two)."""
    return len(_pool(voices, exclude))


def pick_voice(name, voices, exclude=None, number=None):
    """The voice for player `name` among `voices` (from voices_of), or None
    when there are fewer than two to choose from. `exclude` is (provider,
    voice id) of the narrator's voice, left out when two others remain.
    `number` is the voice the player chose ("my voice 3", 1 to 10): the
    same number is always the same voice here, counting round the voices
    this computer has; without one, the name picks."""
    pool = _pool(voices, exclude)
    if len(pool) < 2:
        return None
    try:
        number = int(number or 0)
    except (TypeError, ValueError):
        number = 0
    if number > 0:
        return pool[(number - 1) % len(pool)]
    digest = hashlib.sha256(str(name or "").casefold().encode("utf-8")).digest()
    return pool[int.from_bytes(digest[:8], "big") % len(pool)]


class VoiceBook:
    """The voices of Hariku Voice's providers that can speak now, listed on a
    worker thread (listing may use the network) and kept for ten minutes."""

    def __init__(self, providers, available, list_voices, clock=time.monotonic,
                 max_age=MAX_AGE_SECONDS):
        self._providers = providers
        self._available = available
        self._list_voices = list_voices
        self._clock = clock
        self._max_age = max_age
        self._lock = threading.Lock()
        self._voices = None
        self._listed_at = 0.0
        self._listing = False

    def cached(self):
        """What was listed, or None when nothing (recent) is known."""
        with self._lock:
            if self._voices is None or self._clock() - self._listed_at > self._max_age:
                return None
            return dict(self._voices)

    def forget(self):
        with self._lock:
            self._voices = None

    def refresh(self):
        """List the voices now (blocks: a worker thread only)."""
        found = {}
        try:
            providers = list(self._providers())
        except Exception:
            providers = []
        for provider in providers:
            try:
                if self._available(provider):
                    found[provider] = list(self._list_voices(provider) or [])
            except Exception:
                continue
        with self._lock:
            self._voices = found
            self._listed_at = self._clock()
            self._listing = False
        return found

    def refresh_in_background(self):
        with self._lock:
            if self._listing:
                return
            self._listing = True
        threading.Thread(target=self.refresh, daemon=True, name="orbit-voice-list").start()


class Speaker:
    """Says lines in order. `services` gives narrator_voice() (Hariku Voice's
    own voice, or None when it can't speak), say(text) -> bool (the fallback
    narrator: True when Hariku Voice speaks it, False when the screen reader
    does), speak_voice(text, voice, on_done) -> bool (on_done(error) from any
    thread), voice_busy(), call_later(seconds, fn) and call_after(fn, *args)."""

    def __init__(self, services, clock=time.monotonic):
        self.services = services
        self.clock = clock
        self.waiting = collections.deque()
        self.reader_until = 0.0
        self.current = None           # the line a player's voice is saying
        self._timer = None

    def say(self, text, voice=None):
        self.say_parts([(text, voice)])

    def say_parts(self, parts):
        """One line in parts, said one right after another: [(text, voice or None)]
        (None: the narrator)."""
        parts = collections.deque((str(text or "").strip(), voice) for text, voice in parts
                                  if str(text or "").strip())
        if not parts:
            return
        if len(self.waiting) >= MAX_WAITING:
            self.waiting.popleft()
        self.waiting.append(parts)
        self._pump()

    def clear(self):
        self.waiting.clear()
        self._cancel_timer()

    def busy(self):
        return bool(self.waiting) or self.current is not None

    def _cancel_timer(self):
        timer, self._timer = self._timer, None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _later(self):
        if self._timer is None:
            self._timer = self.services.call_later(POLL_SECONDS, self._tick)

    def _tick(self):
        self._timer = None
        self._pump()

    def _narrate(self, text):
        if not self.services.say(text):
            start = max(self.clock(), self.reader_until)
            self.reader_until = start + reader_seconds(text)

    def _narrator(self):
        try:
            return self.services.narrator_voice()
        except Exception:
            return None

    def _next(self):
        parts = self.waiting[0]
        part = parts.popleft()
        if not parts:
            self.waiting.popleft()
        return part

    def _pump(self):
        while self.waiting:
            if self.current is not None:
                self._later()             # a voice is still speaking
                return
            text, voice = self.waiting[0][0]
            if voice is None:
                voice = self._narrator()
            if voice is None:
                self._next()
                self._narrate(text)       # the screen reader, when Hariku Voice can't
                continue
            if self.services.voice_busy() or self.clock() < self.reader_until:
                self._later()             # let the one before finish first
                return
            self._next()
            self.current = (text, voice)
            try:
                started = self.services.speak_voice(text, voice, self._voice_done)
            except Exception:
                started = False
            if not started:
                self.current = None
                self._narrate(text)

    def _voice_done(self, error=None):
        self.services.call_after(self._after_voice, error)

    def _after_voice(self, error):
        line, self.current = self.current, None
        if error is not None and line is not None:
            self._narrate(line[0])        # the voice failed: the narrator reads it
        self._pump()
