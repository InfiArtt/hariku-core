# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What Timer & Alarm answers in Aruna (core 2.9's commands with content,
core.commands.add_intent) and what its actions say. No wx here.

  "alarm besok jam 2 gang war"      read back, "Pasang?", set on yes
  "bangunkan aku jam 4.30"          the same, always in the morning
  "jam 2 siang" (after a read-back) corrects that alarm's time and asks again
  "timer mie 3 menit"               starts at once: "Timer mie, 3 menit, mulai."
  "batalkan timer mie"              cancels it; an alarm is asked about first
  "matikan alarm gang war"          stops it when it rings, else as cancel
  "sisa timer mie"                  the time left
  "tunda 10 menit"                  snoozes what rings (or just stopped)

A handler returns None when the words aren't for it (Aruna then tries other
commands), a string to say, or a core.commands.Reply that asks first.
"""

import core.commands
from core.commands import Reply

import timer_alarm_parse as parse
import timer_alarm_text as text
from timer_alarm_text import _


PATTERNS = {
    "alarm": [
        "alarm {text}", "pasang alarm {text}", "setel alarm {text}", "set alarm {text}",
        "atur alarm {text}", "buat alarm {text}", "buatkan alarm {text}", "bikin alarm {text}",
        "tambah alarm {text}", "tambahkan alarm {text}", "alarm baru {text}",
        "nyalakan alarm {text}", "hidupkan alarm {text}", "pasangkan alarm {text}",
        "set an alarm {text}", "set the alarm {text}", "set my alarm {text}",
        "set up an alarm {text}", "add an alarm {text}", "add alarm {text}",
        "create an alarm {text}", "make an alarm {text}", "new alarm {text}",
        "wecker {text}", "stell den wecker {text}", "stelle den wecker {text}",
        "stell einen wecker {text}", "stelle einen wecker {text}",
    ],
    "wake": [
        "bangunkan aku {text}", "bangunkan saya {text}", "bangunkan {text}",
        "bangunin aku {text}", "bangunin saya {text}", "bangunin {text}",
        "wake me up {text}", "wake me {text}", "weck mich {text}", "wecke mich {text}",
    ],
    "timer": [
        "timer {text}", "pasang timer {text}", "setel timer {text}", "set timer {text}",
        "atur timer {text}", "buat timer {text}", "buatkan timer {text}", "bikin timer {text}",
        "mulai timer {text}", "mulai hitung mundur {text}", "nyalakan timer {text}",
        "tambah timer {text}", "timer baru {text}", "hitung mundur {text}",
        "set a timer {text}", "set the timer {text}", "start a timer {text}",
        "start timer {text}", "start the timer {text}", "add a timer {text}",
        "new timer {text}", "countdown {text}", "count down {text}",
        "stell einen timer {text}", "stelle einen timer {text}",
    ],
    "cancel": [
        "batalkan timer {text}", "batalkan alarm {text}", "batal timer {text}",
        "batal alarm {text}", "hapus timer {text}", "hapus alarm {text}",
        "cancel timer {text}", "cancel alarm {text}", "cancel the timer {text}",
        "cancel {text} timer", "cancel {text} alarm", "delete alarm {text}",
        "delete timer {text}", "delete {text} alarm", "delete {text} timer",
        "remove alarm {text}", "remove timer {text}", "remove {text} alarm",
        "remove {text} timer", "batalkan {text} timer", "batalkan {text} alarm",
        "hapus {text} timer", "hapus {text} alarm", "delete the alarm {text}",
        "delete the timer {text}", "remove the alarm {text}", "remove the timer {text}",
        "cancel the alarm {text}",
    ],
    "stop": [
        "matikan timer {text}", "matikan alarm {text}", "hentikan timer {text}",
        "hentikan alarm {text}", "stop timer {text}", "stop alarm {text}",
        "stop {text} timer", "stop {text} alarm", "turn off {text} alarm",
        "turn off the alarm {text}", "turn off alarm {text}", "matikan {text} timer",
        "matikan {text} alarm", "stop the alarm {text}", "stop the timer {text}",
    ],
    "left": [
        "sisa timer {text}", "sisa waktu timer {text}", "sisa waktu {text}",
        "berapa lama lagi timer {text}", "berapa lama lagi alarm {text}",
        "berapa lama lagi {text}", "berapa sisa timer {text}", "berapa sisa waktu {text}",
        "how long is left on {text}", "how long left on {text}",
        "how much time is left on {text}", "how much time left on {text}",
        "time left on {text}", "how long until {text}",
    ],
    "snooze": [
        "tunda {text}", "tunda alarm {text}", "tunda timer {text}", "tunda dulu {text}",
        "snooze {text}", "snooze for {text}", "snooze the alarm {text}",
        "snooze the alarm for {text}", "snooze alarm {text}",
    ],
    # A correction after an alarm's read-back ("jam 2 siang"); only taken while
    # that alarm is waiting for its answer or was just turned down.
    "fix": [
        "jam {text}", "pukul {text}", "at {text}", "{text} pagi", "{text} siang",
        "{text} sore", "{text} malam", "{text} am", "{text} pm", "{text} a.m.",
        "{text} p.m.",
    ],
}

# Hotkey actions (no content), with the other ways people say them.
ALIASES = {
    "stop": [
        "stop", "stop alarm", "stop the alarm", "stop timer", "stop the timer",
        "stop ringing", "turn off the alarm", "i'm awake", "i am awake",
        "matikan alarm", "matikan timer", "hentikan alarm", "hentikan timer", "hentikan",
        "berhenti", "stop alarmnya", "matikan alarmnya", "aku sudah bangun",
    ],
    "snooze": [
        "snooze", "snooze the alarm", "snooze alarm", "tunda", "tunda alarm",
        "tunda alarmnya", "tunda dulu", "tunda timer",
    ],
    "time_left": [
        "sisa timer", "sisa waktu timer", "berapa lama lagi", "berapa lama lagi timer",
        "berapa lama lagi alarm", "timer masih berapa lama", "sisa waktunya",
        "how long is left", "how much time is left", "time left", "how long left",
        "how long until the alarm",
    ],
    "list": [
        "daftar alarm", "daftar timer", "daftar alarm dan timer", "alarm apa saja",
        "alarmku", "timerku", "alarm", "timer", "list alarms", "list my alarms",
        "list timers", "list my timers", "my alarms", "my timers", "what alarms do i have",
    ],
    "cancel_timer": [
        "batalkan timer", "hapus timer", "batal timer", "cancel the timer", "cancel timer",
        "cancel my timer", "delete the timer",
    ],
    "cancel_all_timers": [
        "batalkan semua timer", "hapus semua timer", "cancel all timers", "stop all timers",
        "delete all timers",
    ],
    "cancel_alarm": [
        "hapus alarm", "batalkan alarm", "batal alarm", "delete the alarm", "delete alarm",
        "cancel the alarm", "cancel alarm", "remove the alarm",
    ],
}


class Assistant:
    """The answers, for one TimerAlarm (`app`). `match(text)` is
    core.commands.match (tests pass a fake)."""

    def __init__(self, app, match=None):
        self.app = app
        self._match = match or core.commands.match

    # --- small helpers ------------------------------------------------------------------

    def _now(self):
        return self.app.now()

    def _packs(self):
        return self.app.packs()

    def _is_command(self, full_text):
        """Whether Aruna would run a command for this text anyway ("alarm
        list" is not an alarm): then an intent turns it down."""
        try:
            return self._match(full_text).kind == "run"
        except Exception:
            return False

    def _items(self, kind):
        if kind == "alarm":
            return self.app.schedule.alarms()
        if kind == "timer":
            return self.app.schedule.timers()
        return self.app.schedule.ordered()

    def _find(self, query, kind):
        return parse.match_items(query, self._items(kind), self._now(), self._packs(),
                                 self.app.language())

    # --- setting an alarm -----------------------------------------------------------------

    def on_alarm(self, request):
        return self._alarm(request, wake=False)

    def on_wake(self, request):
        return self._alarm(request, wake=True)

    def _alarm(self, request, wake):
        now = self._now()
        parsed = parse.parse_alarm(request.text, now, self._packs(), self.app.language(),
                                   wake=wake)
        if parsed.problem == "no_time" and not parsed.recognised \
                and self._is_command(request.full_text):
            return None
        return self._ask_alarm(parsed, now)

    def _ask_alarm(self, parsed, now):
        # Kept for a correction ("jam 2 siang") even when this one can't be set.
        self.app.set_draft(parsed.components, parsed.wake, parsed.label)
        if not parsed.ok:
            return text.alarm_problem(parsed)
        return Reply(text.readback(parsed, now), confirm=lambda: self._set_alarm(parsed))

    def _set_alarm(self, parsed):
        now = self._now()
        if parsed.due <= now:
            return _("err_passed_now")
        item, added = self.app.add_alarm(parsed)
        self.app.clear_draft()
        if item is None:
            return _("err_full")
        if not added:
            return _("alarm_exists")
        return text.alarm_set(item, now)

    def on_fix(self, request):
        """ "jam 2 siang" right after an alarm's read-back: that alarm, at
        that time. None when no alarm is waiting or it isn't just a time."""
        draft = self.app.draft()
        if draft is None:
            return None
        now = self._now()
        fix = parse.parse_time_fix(request.full_text, now, self._packs(), self.app.language())
        if fix is None:
            return None
        merged = parse.merge_fix(draft["components"], fix)
        parsed = parse.alarm_from_components(merged, now, wake=draft["wake"],
                                             label=draft["label"])
        return self._ask_alarm(parsed, now)

    # --- timers -----------------------------------------------------------------------------

    def on_timer(self, request):
        found = parse.parse_duration(request.text, self._packs())
        if found is None or found.seconds < 1:
            query = parse.Query(request.text)
            if query.asks:
                return self.time_left_for(request.text, request.full_text)
            if query.cancels:
                return self.cancel_for(request.text, request.full_text, "cancel")
            if self._is_command(request.full_text):
                return None
            fix = parse.parse_time_fix(request.text, self._now(), self._packs(),
                                       self.app.language())
            if fix is not None and fix.get("hour") is not None:
                return _("err_timer_clock")
            return _("err_no_duration")
        if found.seconds > parse.MAX_TIMER_SECONDS:
            return _("err_timer_too_long")
        item = self.app.add_timer(found.seconds, found.label)
        if item is None:
            return _("err_full")
        return text.timer_started(item)

    # --- cancelling and stopping --------------------------------------------------------------

    def on_cancel(self, request):
        return self.cancel_for(request.text, request.full_text, "cancel")

    def on_stop(self, request):
        return self.cancel_for(request.text, request.full_text, "stop")

    def cancel_for(self, said, full_text, verb):
        """ "batalkan timer mie", "stop the tea timer", "hapus alarm gang
        war", "cancel all timers"."""
        query = parse.Query(said)
        kind = parse.Query(full_text).kind or query.kind
        now = self._now()
        if query.all:
            if kind == "alarm":
                alarms = self.app.schedule.alarms()
                if not alarms:
                    return _("no_alarms")
                return Reply(_("ask_delete_all", count=len(alarms)),
                             confirm=lambda: self._delete_all_alarms())
            return self.cancel_all_timers()
        if not query.name:
            return self.unnamed(kind, verb)
        ringing = self.app.ringing_items()
        if ringing and parse.match_items(query, ringing, now, self._packs(), self.app.language()):
            return text.stopped_text(self.app.stop())
        matches = self._find(query, kind)
        if not matches:
            if kind == "alarm":
                return _("alarm_not_found", name=query.name)
            if kind == "timer":
                return _("timer_not_found", name=query.name)
            return _("item_not_found", name=query.name)
        if len(matches) > 1:
            if all(m["kind"] == "timer" for m in matches):
                return text.which_timer(matches, now)
            return text.which_alarm([m for m in matches if m["kind"] == "alarm"], now)
        return self._cancel_item(matches[0], now)

    def _cancel_item(self, item, now):
        if item["kind"] == "timer":
            self.app.remove(item["id"])
            return text.cap(_("msg_cancelled", name=text.name(item)))
        item_id = item["id"]
        return Reply(text.cap(text.ask_delete(item, now)),
                     confirm=lambda: self._delete_alarm(item_id))

    def _delete_alarm(self, item_id):
        item = self.app.remove(item_id)
        if item is None:
            return _("item_gone")
        return text.cap(_("msg_deleted", name=text.name(item)))

    def _delete_all_alarms(self):
        removed = self.app.remove_all("alarm")
        if not removed:
            return _("no_alarms")
        return _("all_alarms_deleted_one") if len(removed) == 1 else \
            _("all_alarms_deleted", count=len(removed))

    def unnamed(self, kind, verb):
        """ "stop the alarm", "batalkan timer" with no name."""
        ringing = self.app.ringing_items()
        if ringing and (kind is None or any(i["kind"] == kind for i in ringing)):
            return text.stopped_text(self.app.stop())
        if verb == "stop":
            return self.stop()
        now = self._now()
        if kind == "alarm":
            alarms = self.app.schedule.alarms()
            if not alarms:
                return _("no_alarms")
            if len(alarms) == 1:
                return self._cancel_item(alarms[0], now)
            return text.which_alarm(alarms, now)
        timers = self.app.schedule.timers()
        if not timers:
            return _("no_timers")
        if len(timers) == 1:
            return self._cancel_item(timers[0], now)
        return text.which_timer(timers, now)

    # --- how long is left --------------------------------------------------------------------

    def on_time_left(self, request):
        return self.time_left_for(request.text, request.full_text)

    def time_left_for(self, said, full_text):
        query = parse.Query(said)
        kind = parse.Query(full_text).kind or query.kind
        now = self._now()
        if not query.name or query.all:
            timers = self.app.schedule.timers()
            alarms = self.app.schedule.alarms()
            if kind == "alarm" or (kind is None and not timers and alarms):
                if not alarms:
                    return _("no_alarms")
                return text.alarm_left(alarms[0], now)
            if not timers:
                return _("no_timers")
            return " ".join(text.timer_left(t, now) for t in timers)
        matches = self._find(query, kind)
        if not matches:
            if kind == "alarm":
                return _("alarm_not_found", name=query.name)
            return _("timer_not_found", name=query.name)
        return " ".join(text.timer_left(m, now) if m["kind"] == "timer" else text.alarm_left(m, now)
                        for m in matches)

    # --- snoozing ------------------------------------------------------------------------------

    def on_snooze(self, request):
        found = parse.parse_duration(request.text, self._packs())
        seconds = None
        if found is not None and 10 <= found.seconds <= parse.MAX_TIMER_SECONDS:
            seconds = found.seconds
        return self.snooze(seconds)

    # --- the actions (no content), and what they say ------------------------------------------

    def stop(self):
        stopped = self.app.stop()
        if stopped:
            return text.stopped_text(stopped)
        recent = self.app.recently_stopped()
        if recent:
            return text.already_stopped_text(recent)
        return _("nothing_ringing")

    def snooze(self, seconds=None):
        items, seconds, until = self.app.snooze(seconds)
        if not items:
            return _("nothing_to_snooze")
        return text.snoozed_text(items, seconds, until)

    def time_left(self):
        return self.time_left_for("", "")

    def list_all(self):
        return text.list_text(self.app.schedule.alarms(), self.app.schedule.timers(),
                              self.app.ringing_items(), self._now())

    def cancel_timer(self):
        return self.unnamed("timer", "cancel")

    def cancel_all_timers(self):
        stopped = [i for i in self.app.ringing_items() if i["kind"] == "timer"]
        if stopped:
            self.app.stop()
        removed = self.app.remove_all("timer")
        count = len(removed) + len(stopped)
        if not count:
            return _("no_timers")
        return _("all_timers_cancelled_one") if count == 1 else \
            _("all_timers_cancelled", count=count)

    def cancel_alarm(self):
        """ "hapus alarm" with no name: an action can't ask, so it says how."""
        alarms = self.app.schedule.alarms()
        if not alarms:
            return _("no_alarms")
        return text.which_alarm(alarms, self._now())
