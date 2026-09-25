# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Timer & Alarm's state: the schedule, what is ringing, what was missed, and
saving. No wx here: main.py passes in the clock, the sound player, speech,
the input readings and core.api's load/save, and calls tick() a few times a
second from a wx timer on the UI thread (everything here runs on that thread).

    start()          load, and sort out what came due while Hariku was closed
    tick()           ring what is due; notice a key press, a ring that ran out,
                     and the user coming back after a missed ring
    add_alarm/add_timer/remove/cancel_timers/stop/snooze
"""

import datetime
import time

import timer_alarm_store as store
import timer_alarm_text as text
from timer_alarm_ring import InputWatch, Ringer

DRAFT_SECONDS = 120.0         # "jam 2 siang" still corrects the last alarm this long


class TimerAlarm:
    def __init__(self, load=None, save=None, now=None, clock=None, play=None, stop=None,
                 say=None, input_readers=None, packs=None, language=None, sound_path=None,
                 on_key_stop=None):
        self._load = load or (lambda: {})
        self._save = save or (lambda data: True)
        self.now = now or datetime.datetime.now
        self.clock = clock or time.monotonic
        self._say = say or (lambda text_: None)
        self.packs = packs or (lambda: None)
        self.language = language or (lambda: "en")
        self._sound_path = sound_path or (lambda choice, kind: choice)
        self.on_key_stop = on_key_stop
        readers = input_readers or (lambda: None, lambda: False, lambda: None)
        self.schedule = store.Schedule()
        self.ringer = Ringer(play or (lambda path: None), stop or (lambda path: None), self._say,
                             self._sound_for, text.ring_text, InputWatch(*readers, self.clock))
        self._missed_watch = InputWatch(*readers, self.clock)
        self._missed_waiting = False
        self._to_ring = []
        self._draft = None
        self._draft_at = None

    # --- settings and saving ----------------------------------------------------------

    @property
    def settings(self):
        return dict(self.schedule.settings)

    @property
    def ring_seconds(self):
        return self.schedule.settings["ring_minutes"] * 60

    @property
    def snooze_seconds(self):
        return self.schedule.settings["snooze_minutes"] * 60

    def set_settings(self, settings):
        self.schedule.settings = store.normalize_settings(settings)
        self.save()

    def save(self):
        try:
            return bool(self._save(self.schedule.to_data()))
        except Exception:
            return False

    def sound_path(self, kind):
        return self._sound_path(self.schedule.settings[f"{kind}_sound"], kind)

    def _sound_for(self, items):
        kind = "alarm" if any(i["kind"] == "alarm" for i in items) else "timer"
        return self.sound_path(kind)

    # --- starting -----------------------------------------------------------------------

    def start(self):
        """Load the schedule. Items that came due while Hariku was closed ring
        at the first tick if they are within the ring length; older ones are
        told once (startup_text). Returns what will ring."""
        try:
            data = self._load()
        except Exception:
            data = {}
        self.schedule = store.Schedule.from_data(data)
        missed = len(self.schedule.missed)
        self._to_ring = store.start_up(self.schedule, self.now(), self.ring_seconds)
        if self._to_ring or len(self.schedule.missed) != missed:
            self.save()
        return list(self._to_ring)

    def startup_text(self):
        """ "While Hariku was closed, ..." and missed rings not yet told, said
        once: they are forgotten afterwards."""
        missed = self.schedule.take_missed()
        if not missed:
            return ""
        self._missed_waiting = False
        self.save()
        now = self.now()
        return " ".join(text.missed_text(entry, now) for entry in missed)

    # --- the tick -----------------------------------------------------------------------

    def tick(self):
        """Returns the ring's outcome, ("key", items) or ("timeout", items), when
        it ended in this tick, else None."""
        now, mono = self.now(), self.clock()
        outcome = self.ringer.tick(mono)
        if outcome is not None:
            reason, items = outcome
            if reason == "timeout":
                for item in items:
                    self.schedule.add_missed(item, "missed")
                self._arm_missed()
                self.save()
            elif reason == "key" and self.on_key_stop is not None:
                try:
                    self.on_key_stop(items)
                except Exception:
                    pass
        fired = self._to_ring + self.schedule.pop_due(now)
        self._to_ring = []
        if fired:
            to_ring, late = [], []
            for item in fired:
                (to_ring if (now - item["due"]).total_seconds() <= self.ring_seconds
                 else late).append(item)
            for item in late:                      # the computer was asleep
                self.schedule.add_missed(item, "missed")
            if late:
                self._arm_missed()
            self.save()
            if to_ring:
                self.ringer.start(to_ring, mono, self.ring_seconds)
        if self._missed_waiting and not self.ringer.ringing and self._missed_watch.key_pressed():
            self._missed_waiting = False
            message = self.startup_text()
            if message:
                self._say(message)
        return outcome

    def _arm_missed(self):
        """Say the missed rings at the next key press."""
        if not self._missed_waiting:
            self._missed_watch.reset()
        self._missed_waiting = True

    @property
    def ringing(self):
        return self.ringer.ringing

    def ringing_items(self):
        return list(self.ringer.items)

    # --- changing the schedule ------------------------------------------------------------

    def add_alarm(self, parsed):
        """(item, added): the new alarm, or the same one already there (added
        False); (None, False) when the list is full."""
        existing = self.schedule.find_same_alarm(parsed.due, parsed.label, parsed.recurrence)
        if existing is not None:
            return existing, False
        item = store.make_alarm(parsed.due, parsed.label, parsed.recurrence, parsed.interval,
                                parsed.anchor_day, now=self.now())
        if not self.schedule.add(item):
            return None, False
        self.save()
        return item, True

    def add_timer(self, seconds, label=""):
        item = store.make_timer(seconds, label, now=self.now())
        if not self.schedule.add(item):
            return None
        self.save()
        return item

    def remove(self, item_id):
        item = self.schedule.remove(item_id)
        if item is not None:
            self.save()
        return item

    def remove_all(self, kind):
        removed = [i for i in self.schedule.items if i["kind"] == kind]
        for item in removed:
            self.schedule.items.remove(item)
        if removed:
            self.save()
        return sorted(removed, key=lambda i: i["due"])

    def stop(self, reason="command"):
        """Stop what rings; returns what was stopped ([] when nothing rang)."""
        outcome = self.ringer.stop(self.clock(), reason)
        return outcome[1] if outcome else []

    def recently_stopped(self):
        return self.ringer.recently_stopped(self.clock())

    def snooze(self, seconds=None):
        """Snooze what rings, or what a key stopped a moment ago: each rings
        again after `seconds` (default: the snooze setting). Returns (items,
        seconds, until); items is [] when there was nothing to snooze."""
        seconds = int(seconds or self.snooze_seconds)
        items = self.stop("snooze") or self.ringer.recently_stopped(self.clock())
        self.ringer.forget_recent()
        if not items:
            return [], seconds, None
        until = self.now().replace(microsecond=0) + datetime.timedelta(seconds=seconds)
        for item in items:
            again = {key: value for key, value in item.items()
                     if key not in ("start", "anchor_day")}
            again.update(id=store.new_id(), due=until, recurrence="none", interval=1)
            self.schedule.add(again)
        self.save()
        return items, seconds, until

    # --- a question about an alarm, still open to corrections ------------------------------

    def set_draft(self, components, wake=False, label=""):
        self._draft = {"components": dict(components), "wake": wake, "label": label}
        self._draft_at = self.clock()

    def draft(self):
        if self._draft is not None and self.clock() - self._draft_at <= DRAFT_SECONDS:
            return self._draft
        return None

    def clear_draft(self):
        self._draft = self._draft_at = None

    # --- ending -------------------------------------------------------------------------

    def shutdown(self):
        self.ringer.shutdown()
        self.save()
