# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Ringing: the sound and the spoken text, again every REPEAT_SECONDS, until a key
is pressed, the user says stop or snooze, or the ring length is over. No wx
and no Windows calls here: the player, the speech and the input readings are
passed in, so tests drive it with fakes and a fake clock (tick(now) is called
a few times a second by main.py's timer).

Key presses are noticed the way Hariku Voice's "stop when I press a key" does:
GetLastInputInfo changes, the mouse didn't just move, and it isn't the first
moment of the ring (a key held or pressed as it starts doesn't stop it). No
keyboard hook, ever.
"""

REPEAT_SECONDS = 10.0        # sound and speech again after this long
GRACE_SECONDS = 1.5          # input this soon after the ring starts doesn't stop it...
HELD_GRACE_SECONDS = 3.0     # ...nor a key held down (typing) this soon
MOUSE_MOVE_SECONDS = 0.3     # input this soon after the pointer moved is the mouse
RECENT_SECONDS = 120.0       # a ring stopped by a key can still be snoozed this long


class InputWatch:
    """Has a key been pressed since reset()? `last_input()` is GetLastInputInfo's
    tick (None when unknown), `key_down()` whether a keyboard key is held,
    `cursor()` the mouse position, `clock()` seconds (monotonic)."""

    def __init__(self, last_input, key_down, cursor, clock):
        self._last_input = last_input
        self._key_down = key_down
        self._cursor = cursor
        self._clock = clock
        self.reset()

    def reset(self):
        self._baseline = self._safe(self._last_input)
        self._position = self._safe(self._cursor)
        self._start = self._clock()
        self._moved_at = float("-inf")

    @staticmethod
    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default

    def key_pressed(self, grace=0.0, held_grace=0.0):
        now = self._clock()
        tick = self._safe(self._last_input)
        position = self._safe(self._cursor)
        if position != self._position:
            self._position = position
            self._moved_at = now
        if tick is None or tick == self._baseline:
            return False
        elapsed = now - self._start
        held = bool(self._safe(self._key_down, False))
        if elapsed < grace or (held and elapsed < held_grace):
            self._baseline = tick
            return False
        if not held and now - self._moved_at < MOUSE_MOVE_SECONDS:
            self._baseline = tick        # the mouse moved; that isn't a key press
            return False
        return True


class Ringer:
    """Rings a set of items. `play(path)` / `stop(path)` play and stop a
    sound without blocking, `say(text)` speaks, `sound_for(items)` and
    `text_for(items)` choose what, `watch` is an InputWatch."""

    def __init__(self, play, stop, say, sound_for, text_for, watch):
        self._play = play
        self._stop_sound = stop
        self._say = say
        self._sound_for = sound_for
        self._text_for = text_for
        self._watch = watch
        self.items = []
        self._sound = None
        self._next_cycle = None
        self._ends = None
        self._started = None
        self.recent = []
        self._recent_at = None

    @property
    def ringing(self):
        return bool(self.items)

    def start(self, items, now, ring_seconds):
        """Ring these items (with any already ringing) from `now` for
        `ring_seconds`; the sound and the text start at once."""
        items = [i for i in items if i["id"] not in {r["id"] for r in self.items}]
        if not items:
            return
        if not self.items:
            self._watch.reset()
            self._started = now
        self.items.extend(items)
        self._ends = now + max(10.0, float(ring_seconds))
        self._cycle(now)

    def _cycle(self, now):
        path = self._sound_for(self.items)
        if self._sound and self._sound != path:
            self._safe_stop(self._sound)
        self._sound = path
        try:
            self._play(path)
        except Exception:
            pass
        try:
            self._say(self._text_for(self.items))
        except Exception:
            pass
        self._next_cycle = now + REPEAT_SECONDS

    def _safe_stop(self, path):
        try:
            self._stop_sound(path)
        except Exception:
            pass

    def tick(self, now):
        """Called a few times a second. Returns ("key", items) when a key
        stopped the ring, ("timeout", items) when nobody did, else None."""
        if not self.items:
            return None
        if self._watch.key_pressed(GRACE_SECONDS, HELD_GRACE_SECONDS):
            return self._end("key", now)
        if now >= self._ends:
            return self._end("timeout", now)
        if now >= self._next_cycle:
            self._cycle(now)
        return None

    def stop(self, now, reason="command"):
        """Stop ringing (the Stop action, Aruna's "stop", a snooze). Returns
        (reason, items) or None when nothing rang."""
        if not self.items:
            return None
        return self._end(reason, now)

    def _end(self, reason, now):
        items, self.items = self.items, []
        if self._sound:
            self._safe_stop(self._sound)
        self._sound = None
        self._next_cycle = self._ends = self._started = None
        if reason in ("key", "command"):
            self.recent, self._recent_at = list(items), now
        else:
            self.recent, self._recent_at = [], None
        return reason, items

    def recently_stopped(self, now):
        """What a key (or "stop") silenced in the last RECENT_SECONDS: "tunda"
        right after still snoozes it."""
        if self.recent and self._recent_at is not None and now - self._recent_at <= RECENT_SECONDS:
            return list(self.recent)
        return []

    def forget_recent(self):
        self.recent, self._recent_at = [], None

    def shutdown(self):
        if self._sound:
            self._safe_stop(self._sound)
        self._sound = None
        self.items = []
