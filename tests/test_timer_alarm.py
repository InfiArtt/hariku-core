# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Timer & Alarm extension: reading alarms and durations in
# Indonesian and English (and German where core.when knows it), the schedule
# and repeats, saving and catching up after Hariku was closed, ringing (a fake
# player, fake key readings and a fake clock), Aruna's answers through a fake
# Aruna built on core.commands.decide, the sentences in both languages, the
# Morning Briefing, and registering with Hariku. Nothing plays a sound, reads
# the real keyboard, speaks or opens a window.

import datetime
import json
import os
import sys
import types
import wave

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "timer_alarm")
NOW = datetime.datetime(2026, 9, 25, 10, 40, 25)          # a Friday
PACKS = ["id", "en"]


def _modules():
    if EXT_DIR not in sys.path:
        sys.path.insert(0, EXT_DIR)
    import timer_alarm_app
    import timer_alarm_intents
    import timer_alarm_parse
    import timer_alarm_ring
    import timer_alarm_store
    import timer_alarm_system
    import timer_alarm_text
    return types.SimpleNamespace(app=timer_alarm_app, intents=timer_alarm_intents,
                                 parse=timer_alarm_parse, ring=timer_alarm_ring,
                                 store=timer_alarm_store, system=timer_alarm_system,
                                 text=timer_alarm_text)


@pytest.fixture(scope="module")
def ta():
    return _modules()


@pytest.fixture
def lang(monkeypatch, ta):
    """Switch the UI language; the core's day and month names and this
    extension's messages are loaded (another test may have cleared them)."""
    from core import i18n
    saved = {d: i18n._language_cache.get(d) for d in ("core", "timer_alarm")}
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    i18n._load_domain("timer_alarm", os.path.join(EXT_DIR, "locales"))

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("en")
    yield set_lang
    for domain, data in saved.items():
        if data is None:
            i18n._language_cache.pop(domain, None)
        else:
            i18n._language_cache[domain] = data


def at(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")


# ------------------------------------------------------------
# Durations
# ------------------------------------------------------------

@pytest.mark.parametrize("text, seconds, label", [
    ("10 menit", 600, ""),
    ("mie 3 menit", 180, "mie"),
    ("for 1 hour 30 minutes", 5400, ""),
    ("setengah jam", 1800, ""),
    ("90 detik", 90, ""),
    ("lima menit teh", 300, "teh"),
    ("satu setengah jam", 5400, ""),
    ("an hour and a half", 5400, ""),
    ("1,5 jam", 5400, ""),
    ("1.5 jam", 5400, ""),
    ("dua puluh lima menit", 1500, ""),
    ("tiga belas menit", 780, ""),
    ("seratus detik", 100, ""),
    ("half an hour", 1800, ""),
    ("a quarter of an hour", 900, ""),
    ("three quarters of an hour", 2700, ""),
    ("twenty-five minutes", 1500, ""),
    ("two hours and a half", 9000, ""),
    ("1 jam 30", 5400, ""),                   # a bare number after hours is minutes
    ("2 menit 30 detik", 150, ""),
    ("2 menit 30", 150, ""),
    ("1 jam setengah", 5400, ""),
    ("sejam", 3600, ""),
    ("semenit", 60, ""),
    ("5m", 300, ""),
    ("1h30m", 5400, ""),
    ("10 menit untuk mie", 600, "mie"),
    ("for the pasta 10 minutes", 600, "pasta"),
    ("two eggs 10 minutes", 600, "two eggs"),
    ("10 menit lagi", 600, ""),
    ("Teh Hijau 4 menit", 240, "Teh Hijau"),  # the label as typed
])
def test_durations(ta, text, seconds, label):
    found = ta.parse.parse_duration(text, PACKS)
    assert found is not None, text
    assert (found.seconds, found.label) == (seconds, label)


def test_durations_in_a_pack_language(ta):
    found = ta.parse.parse_duration("zehn Minuten", ["de", "en", "id"])
    assert found.seconds == 600
    assert ta.parse.parse_duration("eine halbe Stunde", ["de", "en", "id"]).seconds == 1800


@pytest.mark.parametrize("text", ["mie", "90", "jam 5", "", "timer", "a timer"])
def test_no_duration(ta, text):
    assert ta.parse.parse_duration(text, PACKS) is None


# ------------------------------------------------------------
# Alarms: dates, times, the ambiguous hour, labels
# ------------------------------------------------------------

ALARMS = [
    # (now, text, wake, due, label, recurrence)
    ("2026-09-25 10:40", "tomorrow at 2 for gang war", False, "2026-09-26 02:00", "gang war", "none"),
    ("2026-09-25 10:40", "besok jam 2 gang war", False, "2026-09-26 02:00", "gang war", "none"),
    ("2026-09-25 10:40", "besok jam 2 siang gang war", False, "2026-09-26 14:00", "gang war", "none"),
    ("2026-09-25 10:40", "besok jam 3 rapat", False, "2026-09-26 03:00", "rapat", "none"),
    # No day: the next one to come.
    ("2026-09-25 10:40", "jam 2", False, "2026-09-25 14:00", "", "none"),
    ("2026-09-25 10:40", "at 2", False, "2026-09-25 14:00", "", "none"),
    ("2026-09-25 22:00", "jam 2", False, "2026-09-26 02:00", "", "none"),
    ("2026-09-25 01:00", "jam 2", False, "2026-09-25 02:00", "", "none"),
    ("2026-09-25 10:40", "for 6", False, "2026-09-25 18:00", "", "none"),
    ("2026-09-25 10:40", "6", False, "2026-09-25 18:00", "", "none"),
    ("2026-09-25 13:00", "jam 12", False, "2026-09-26 00:00", "", "none"),
    # Today said: the first still ahead.
    ("2026-09-25 10:40", "hari ini jam 2", False, "2026-09-25 14:00", "", "none"),
    ("2026-09-25 10:40", "hari ini jam 10", False, "2026-09-25 22:00", "", "none"),
    ("2026-09-25 10:40", "besok jam 12", False, "2026-09-26 12:00", "", "none"),
    ("2026-09-25 10:40", "for 6:30 tomorrow", False, "2026-09-26 06:30", "", "none"),
    # Parts of the day and 24-hour times.
    ("2026-09-25 10:40", "jam 5 pagi", False, "2026-09-26 05:00", "", "none"),
    ("2026-09-25 10:40", "jam delapan pagi", False, "2026-09-26 08:00", "", "none"),
    ("2026-09-25 10:40", "lima pagi", False, "2026-09-26 05:00", "", "none"),
    ("2026-09-25 10:40", "jam 2 dini hari", False, "2026-09-26 02:00", "", "none"),
    ("2026-09-25 10:40", "jam 5 subuh", False, "2026-09-26 05:00", "", "none"),
    ("2026-09-25 10:40", "jam 7 malam minum obat", False, "2026-09-25 19:00", "minum obat", "none"),
    ("2026-09-25 10:40", "jam 7 malam hari", False, "2026-09-25 19:00", "", "none"),
    ("2026-09-25 10:40", "at 2 pm", False, "2026-09-25 14:00", "", "none"),
    ("2026-09-25 10:40", "tomorrow 5 am run", False, "2026-09-26 05:00", "run", "none"),
    ("2026-09-25 10:40", "jam 14.30", False, "2026-09-25 14:30", "", "none"),
    ("2026-09-25 10:40", "jam 00.30", False, "2026-09-26 00:30", "", "none"),
    # Waking up is in the morning.
    ("2026-09-25 10:40", "jam 4.30", True, "2026-09-26 04:30", "", "none"),
    ("2026-09-25 10:40", "at 6", True, "2026-09-26 06:00", "", "none"),
    ("2026-09-25 03:00", "jam 6", True, "2026-09-25 06:00", "", "none"),
    ("2026-09-25 10:40", "at 6 for work", True, "2026-09-26 06:00", "work", "none"),
    # Repeats: the first such hour on the day.
    ("2026-09-25 10:40", "setiap hari jam 5 sholat subuh", False, "2026-09-26 05:00", "sholat subuh",
     "daily"),
    ("2026-09-25 03:00", "setiap hari jam 5", False, "2026-09-25 05:00", "", "daily"),
    ("2026-09-25 10:40", "every day at 5", False, "2026-09-26 05:00", "", "daily"),
    ("2026-09-25 10:40", "tiap Senin jam 7 olahraga", False, "2026-09-28 07:00", "olahraga", "weekly"),
    ("2026-09-25 10:40", "tiap tanggal 31 jam 7 bayar", False, "2026-10-31 07:00", "bayar", "monthly"),
    # In a while.
    ("2026-09-25 10:40", "30 menit lagi", False, "2026-09-25 11:10", "", "none"),
    ("2026-09-25 10:40", "in 30 minutes", False, "2026-09-25 11:10", "", "none"),
    ("2026-09-25 10:40", "10 menit", False, "2026-09-25 10:50", "", "none"),
    ("2026-09-25 10:40", "untuk jam 6 buat masak", False, "2026-09-25 18:00", "masak", "none"),
]


@pytest.mark.parametrize("now, text, wake, due, label, recurrence", ALARMS)
def test_alarms(ta, now, text, wake, due, label, recurrence):
    parsed = ta.parse.parse_alarm(text, at(now) + datetime.timedelta(seconds=25), PACKS, "id",
                                  wake=wake)
    assert parsed.ok, (text, parsed.problem)
    assert parsed.due == at(due), text
    assert parsed.label == label
    assert parsed.recurrence == recurrence


def test_the_users_sentence(ta):
    """ "set alarm tomorrow at 2 for gang war": 2 is 02:00, the first 2
    o'clock of tomorrow; the label is what's left after "for"."""
    parsed = ta.parse.parse_alarm("tomorrow at 2 for gang war", NOW, PACKS, "en")
    assert parsed.due == at("2026-09-26 02:00") and parsed.label == "gang war"
    assert parsed.ambiguous and parsed.date_said and not parsed.passed_today


def test_german_where_core_when_knows_it(ta):
    parsed = ta.parse.parse_alarm("morgen um 7 Uhr", NOW, ["en", "id", "de"], "en")
    assert parsed.due == at("2026-09-26 07:00")


def test_monthly_alarm_keeps_its_day(ta):
    parsed = ta.parse.parse_alarm("tiap tanggal 31 jam 7 bayar", NOW, PACKS, "id")
    assert parsed.anchor_day == 31


@pytest.mark.parametrize("text, problem", [
    ("gang war", "no_time"),
    ("besok pagi", "no_time"),           # a part of the day is not a time: not guessed
    ("besok", "no_time"),
    ("", "no_time"),
    ("hari ini jam 8 pagi", "in_past"),
    ("tiap jam", "unsupported_repeat"),
    ("tanggal 31 Februari jam 7", "invalid_date"),
])
def test_alarm_problems(ta, text, problem):
    parsed = ta.parse.parse_alarm(text, NOW, PACKS, "id")
    assert not parsed.ok and parsed.problem == problem


def test_what_was_heard_is_kept_for_the_question(ta):
    parsed = ta.parse.parse_alarm("besok pagi", NOW, PACKS, "id")
    assert parsed.recognised == ["besok", "pagi"]


def test_a_passed_time_without_a_day_is_tomorrow_and_says_so(ta):
    parsed = ta.parse.parse_alarm("jam 8 pagi", NOW, PACKS, "id")
    assert parsed.due == at("2026-09-26 08:00") and parsed.passed_today
    # Before dawn, tomorrow is what everyone means: no note.
    assert not ta.parse.parse_alarm("jam 2 pagi", NOW, PACKS, "id").passed_today
    # A day was said: no note either.
    assert not ta.parse.parse_alarm("besok jam 8 pagi", NOW, PACKS, "id").passed_today


def test_a_correction_keeps_the_day_and_label(ta):
    first = ta.parse.parse_alarm("besok jam 2 gang war", NOW, PACKS, "id")
    fix = ta.parse.parse_time_fix("jam 2 siang", NOW, PACKS, "id")
    merged = ta.parse.merge_fix(first.components, fix)
    parsed = ta.parse.alarm_from_components(merged, NOW, label=first.label)
    assert parsed.due == at("2026-09-26 14:00") and parsed.label == "gang war"
    # Only a time or date is a correction.
    assert ta.parse.parse_time_fix("jam berapa", NOW, PACKS, "id") is None
    assert ta.parse.parse_time_fix("briefing pagi", NOW, PACKS, "id") is None
    assert ta.parse.parse_time_fix("at 2 pm", NOW, PACKS, "en")["meridiem"] == "pm"


# ------------------------------------------------------------
# Names: which alarm or timer
# ------------------------------------------------------------

def test_query(ta):
    q = ta.parse.Query("the tea timer")
    assert (q.name, q.kind, q.all) == ("tea", "timer", False)
    assert ta.parse.Query("semua timer").all and ta.parse.Query("all").all
    assert ta.parse.Query("sisa timer mie").asks
    assert ta.parse.Query("the 05:00").rest == "05:00"


def test_match_items(ta):
    now = NOW
    items = [ta.store.make_timer(180, "mie", now), ta.store.make_timer(600, "", now),
             ta.store.make_alarm(at("2026-09-26 05:00"), "", now=now),
             ta.store.make_alarm(at("2026-09-26 02:00"), "gang war", now=now)]
    match = lambda text: [i["label"] or i["kind"] for i in ta.parse.match_items(text, items, now, PACKS, "id")]
    assert match("mie") == ["mie"]
    assert match("mi") == ["mie"]                      # misheard
    assert match("gang war") == ["gang war"]
    assert match("10 menit") == ["timer"]              # a timer by its length
    assert match("jam 5") == ["alarm"]                 # an alarm by its time
    assert match("05:00") == ["alarm"]
    assert match("teh") == []


# ------------------------------------------------------------
# The schedule, repeats, saving
# ------------------------------------------------------------

def test_items_survive_saving(ta):
    store = ta.store
    schedule = store.Schedule()
    alarm = store.make_alarm(at("2026-10-31 07:00"), "bayar", "monthly", 1, 31, now=NOW)
    timer = store.make_timer(180, "mie", now=NOW)
    schedule.add(alarm)
    schedule.add(timer)
    schedule.add_missed(store.make_timer(60, "", now=NOW), "closed")
    data = json.loads(json.dumps(schedule.to_data()))          # really JSON
    again = store.Schedule.from_data(data)
    assert [i["id"] for i in again.items] == [alarm["id"], timer["id"]]
    assert again.items[0]["due"] == at("2026-10-31 07:00") and again.items[0]["anchor_day"] == 31
    assert again.items[1]["due"] == NOW.replace(microsecond=0) + datetime.timedelta(seconds=180)
    assert again.items[1]["seconds"] == 180 and again.missed[0]["reason"] == "closed"


def test_bad_data_is_ignored(ta):
    schedule = ta.store.Schedule.from_data({
        "items": [{"kind": "alarm", "due": "not a date"}, {"kind": "bomb", "due": "2026-09-26T02:00:00"},
                  "junk", {"kind": "timer", "due": "2026-09-25T11:00:00", "seconds": True},
                  {"kind": "alarm", "due": "2026-09-26T02:00:00", "recurrence": "hourly"}],
        "missed": [None, {"item": {}}],
        "settings": {"alarm_sound": "C:\\evil.wav", "timer_sound": "windows:Ring03.wav",
                     "ring_minutes": 7, "snooze_minutes": 10}})
    assert [i["kind"] for i in schedule.items] == ["timer", "alarm"]
    assert schedule.items[1]["recurrence"] == "none"
    assert schedule.settings == {"alarm_sound": "windows:Alarm01.wav",
                                 "timer_sound": "windows:Ring03.wav", "ring_minutes": 3,
                                 "snooze_minutes": 10}
    assert ta.store.Schedule.from_data(None).items == []


@pytest.mark.parametrize("value, ok", [
    ("windows:Alarm01.wav", True), ("windows:Ring10.wav", True), ("tone:timer", True),
    ("windows:Alarm11.wav", False), ("windows:..\\Alarm01.wav", False),
    ("windows:Alarm1.wav", False), ("C:\\Windows\\Media\\Alarm01.wav", False), (None, False),
])
def test_sound_choices_are_names_only(ta, value, ok):
    assert ta.store.is_sound_choice(value) is ok


def test_next_occurrence(ta):
    store = ta.store
    daily = store.make_alarm(at("2026-09-26 05:00"), "", "daily", now=NOW)
    assert store.next_occurrence(daily, at("2026-09-26 05:00")) == at("2026-09-27 05:00")
    assert store.next_occurrence(daily, at("2026-12-01 06:00")) == at("2026-12-02 05:00")
    fortnight = store.make_alarm(at("2026-09-25 18:00"), "", "weekly", 2, now=NOW)
    assert store.next_occurrence(fortnight, at("2026-09-25 18:00")) == at("2026-10-09 18:00")
    monthly = store.make_alarm(at("2027-01-31 07:00"), "", "monthly", 1, 31, now=NOW)
    assert store.next_occurrence(monthly, at("2027-01-31 07:00")) == at("2027-02-28 07:00")
    monthly["due"] = at("2027-02-28 07:00")
    assert store.next_occurrence(monthly, at("2027-02-28 07:00")) == at("2027-03-31 07:00")
    leap = store.make_alarm(at("2028-02-29 07:00"), "", "yearly", now=NOW)
    assert store.next_occurrence(leap, at("2028-02-29 07:00")) == at("2029-02-28 07:00")


def test_pop_due(ta):
    store = ta.store
    schedule = store.Schedule()
    once = store.make_alarm(at("2026-09-25 10:40"), "once", now=NOW)
    daily = store.make_alarm(at("2026-09-25 10:40"), "daily", "daily", now=NOW)
    later = store.make_timer(600, "", now=NOW)
    for item in (once, daily, later):
        schedule.add(item)
    fired = schedule.pop_due(NOW)
    assert sorted(i["label"] for i in fired) == ["daily", "once"]
    assert [i["label"] for i in schedule.items] == ["daily", ""]      # the one-off is gone
    assert schedule.get(daily["id"])["due"] == at("2026-09-26 10:40")


def test_start_up_catch_up(ta):
    store = ta.store
    schedule = store.Schedule()
    just = store.make_alarm(at("2026-09-25 10:39"), "just now", now=NOW)
    old = store.make_alarm(at("2026-09-25 02:00"), "gang war", now=NOW)
    tea = store.make_timer(60, "tea", now=NOW - datetime.timedelta(hours=1))
    daily = store.make_alarm(at("2026-09-24 05:00"), "subuh", "daily", now=NOW)
    for item in (just, old, tea, daily):
        schedule.add(item)
    to_ring = store.start_up(schedule, NOW, ring_seconds=180)
    assert [i["label"] for i in to_ring] == ["just now"]
    assert sorted(m["item"]["label"] for m in schedule.missed) == ["gang war", "subuh", "tea"]
    assert all(m["reason"] == "closed" for m in schedule.missed)
    assert [i["label"] for i in schedule.items] == ["subuh"]           # timers and one-offs dropped
    assert schedule.items[0]["due"] == at("2026-09-26 05:00")


# ------------------------------------------------------------
# Ringing
# ------------------------------------------------------------

class FakeClock:
    def __init__(self, now=NOW):
        self.wall = now
        self.mono = 1000.0

    def advance(self, seconds):
        self.wall += datetime.timedelta(seconds=seconds)
        self.mono += seconds


class FakeInput:
    """GetLastInputInfo, GetAsyncKeyState and GetCursorPos, faked."""

    def __init__(self):
        self.tick = 500
        self.held = False
        self.pos = (10, 10)

    def press(self):
        self.tick += 1

    def move_mouse(self):
        self.tick += 1
        self.pos = (self.pos[0] + 5, self.pos[1])

    def readers(self):
        return (lambda: self.tick, lambda: self.held, lambda: self.pos)


@pytest.fixture
def ringer(ta):
    clock = FakeClock()
    keys = FakeInput()
    log = []
    watch = ta.ring.InputWatch(*keys.readers(), lambda: clock.mono)
    r = ta.ring.Ringer(lambda p: log.append(("play", p)), lambda p: log.append(("stop", p)),
                       lambda t: log.append(("say", t)),
                       lambda items: "alarm.wav" if any(i["kind"] == "alarm" for i in items)
                       else "timer.wav",
                       lambda items: "+".join(i["label"] for i in items), watch)
    return types.SimpleNamespace(r=r, clock=clock, keys=keys, log=log)


def _item(ta, label, kind="alarm"):
    if kind == "timer":
        return ta.store.make_timer(60, label, now=NOW)
    return ta.store.make_alarm(NOW, label, now=NOW)


def test_ring_plays_and_speaks_every_ten_seconds(ta, ringer):
    ringer.r.start([_item(ta, "gang war")], ringer.clock.mono, 180)
    assert ringer.log == [("play", "alarm.wav"), ("say", "gang war")]
    for _ in range(9):
        ringer.clock.advance(1)
        assert ringer.r.tick(ringer.clock.mono) is None
    assert len(ringer.log) == 2
    ringer.clock.advance(1)
    ringer.r.tick(ringer.clock.mono)
    assert ringer.log[2:] == [("play", "alarm.wav"), ("say", "gang war")]


def test_a_key_stops_the_ring(ta, ringer):
    ringer.r.start([_item(ta, "gang war")], ringer.clock.mono, 180)
    ringer.clock.advance(0.5)
    ringer.keys.press()                          # still the key that was down: ignored
    assert ringer.r.tick(ringer.clock.mono) is None
    ringer.clock.advance(2)
    ringer.keys.press()
    reason, items = ringer.r.tick(ringer.clock.mono)
    assert reason == "key" and [i["label"] for i in items] == ["gang war"]
    assert ringer.log[-1] == ("stop", "alarm.wav") and not ringer.r.ringing
    assert [i["label"] for i in ringer.r.recently_stopped(ringer.clock.mono)] == ["gang war"]
    ringer.clock.advance(121)
    assert ringer.r.recently_stopped(ringer.clock.mono) == []


def test_mouse_movement_and_typing_at_the_start_dont_stop_it(ta, ringer):
    ringer.r.start([_item(ta, "gang war")], ringer.clock.mono, 180)
    ringer.clock.advance(2)
    ringer.keys.move_mouse()
    assert ringer.r.tick(ringer.clock.mono) is None
    ringer.keys.held = True                      # typing when it started: 3 seconds of grace
    ringer.clock.advance(0.5)
    ringer.keys.press()
    assert ringer.r.tick(ringer.clock.mono) is None
    ringer.clock.advance(1)
    ringer.keys.press()
    assert ringer.r.tick(ringer.clock.mono)[0] == "key"


def test_a_ring_nobody_stops_times_out(ta, ringer):
    ringer.r.start([_item(ta, "gang war")], ringer.clock.mono, 60)
    outcome = None
    for _ in range(61):
        ringer.clock.advance(1)
        outcome = ringer.r.tick(ringer.clock.mono) or outcome
    assert outcome[0] == "timeout"
    assert sum(1 for kind, _ in ringer.log if kind == "play") == 6      # 0, 10, ... 50 s
    assert ringer.r.recently_stopped(ringer.clock.mono) == []           # can't be snoozed


def test_items_ring_together_with_the_alarm_sound(ta, ringer):
    ringer.r.start([_item(ta, "mie", "timer")], ringer.clock.mono, 180)
    ringer.clock.advance(3)
    ringer.r.start([_item(ta, "gang war")], ringer.clock.mono, 180)
    assert ringer.log[-3:] == [("stop", "timer.wav"), ("play", "alarm.wav"), ("say", "mie+gang war")]
    reason, items = ringer.r.stop(ringer.clock.mono)
    assert reason == "command" and len(items) == 2 and ringer.log[-1] == ("stop", "alarm.wav")
    assert ringer.r.stop(ringer.clock.mono) is None


# ------------------------------------------------------------
# The app: ticking, saving, catching up, missed rings, snoozing
# ------------------------------------------------------------

class Harness:
    def __init__(self, ta, data=None, clock=None):
        self.ta = ta
        self.clock = clock or FakeClock()
        self.keys = FakeInput()
        self.data = data if data is not None else {}
        self.saves = 0
        self.log = []
        self.key_stops = []
        self.app = ta.app.TimerAlarm(
            load=lambda: json.loads(json.dumps(self.data)), save=self._save,
            now=lambda: self.clock.wall, clock=lambda: self.clock.mono,
            play=lambda p: self.log.append(("play", p)), stop=lambda p: self.log.append(("stop", p)),
            say=lambda t: self.log.append(("say", t)), input_readers=self.keys.readers(),
            packs=lambda: PACKS, language=lambda: "en", sound_path=lambda choice, kind: choice,
            on_key_stop=self.key_stops.append)

    def _save(self, data):
        self.data = json.loads(json.dumps(data))
        self.saves += 1
        return True

    def said(self):
        return [t for kind, t in self.log if kind == "say"]

    def run(self, seconds, step=0.25):
        for _ in range(int(seconds / step)):
            self.clock.advance(step)
            self.app.tick()


def test_an_alarm_rings_and_is_gone(ta, lang):
    h = Harness(ta)
    h.app.start()
    parsed = ta.parse.parse_alarm("in 1 minute tea", NOW, PACKS, "en")
    item, added = h.app.add_alarm(parsed)
    assert added and h.data["items"][0]["label"] == "tea"
    h.run(30)                                       # 10:40:55, due at 10:41:00
    assert not h.app.ringing
    h.run(6)
    assert h.app.ringing and h.log[0] == ("play", "windows:Alarm01.wav")
    assert h.said() == ["Alarm: tea."]
    assert h.data["items"] == []                   # saved without it
    h.clock.advance(3)
    h.keys.press()
    h.app.tick()
    assert not h.app.ringing and [i["label"] for i in h.key_stops[0]] == ["tea"]


def test_a_timer_uses_the_timer_sound_and_is_dropped(ta, lang):
    h = Harness(ta)
    h.app.start()
    h.app.set_settings({"timer_sound": "windows:Ring06.wav"})
    h.app.add_timer(90, "mie")
    h.run(91)
    assert h.log[0] == ("play", "windows:Ring06.wav")
    assert h.said() == ['The timer "mie" is done.']
    assert h.app.schedule.items == [] and h.data["items"] == []


def test_a_missed_ring_is_said_once_when_the_user_is_back(ta, lang):
    h = Harness(ta)
    h.app.start()
    h.app.set_settings({"ring_minutes": 1})
    h.app.add_alarm(ta.parse.parse_alarm("at 11:00 gym", NOW, PACKS, "en"))
    h.run((at("2026-09-25 11:00") - NOW).total_seconds() + 61, step=1)
    assert not h.app.ringing
    assert h.data["missed"][0]["item"]["label"] == "gym"
    rings = len(h.said())
    h.run(30, step=1)
    assert len(h.said()) == rings                  # nobody is there: nothing more
    h.keys.press()
    h.app.tick()
    assert h.said()[-1] == 'You missed the alarm "gym" at 11:00.'
    h.keys.press()
    h.run(5)
    assert h.said()[-1] == 'You missed the alarm "gym" at 11:00.' and len(h.said()) == rings + 1
    assert h.data["missed"] == []


def test_catch_up_after_hariku_was_closed(ta, lang):
    first = Harness(ta, clock=FakeClock(at("2026-09-25 00:30")))
    first.app.start()
    first.app.add_alarm(ta.parse.parse_alarm("jam 2 gang war", first.clock.wall, PACKS, "id"))
    first.app.add_timer(60, "tea")
    first.app.add_alarm(ta.parse.parse_alarm("in 3 hours", first.clock.wall, PACKS, "en"))
    # Hariku is closed; it starts again at 10:40, and one alarm is only just due.
    data = first.data
    data["items"].append(ta.store.item_to_data(ta.store.make_alarm(at("2026-09-25 10:39"), "now",
                                                                   now=NOW)))
    again = Harness(ta, data=data, clock=FakeClock(NOW))
    to_ring = again.app.start()
    assert [i["label"] for i in to_ring] == ["now"]
    assert again.data["items"] == []
    message = again.app.startup_text()
    assert message == ('While Hariku was closed, the timer "tea" finished at 00:31. '
                       'While Hariku was closed, the alarm "gang war" was due at 02:00. '
                       'While Hariku was closed, the 03:30 alarm was due at 03:30.')
    assert again.app.startup_text() == "" and again.data["missed"] == []      # said once
    again.app.tick()
    assert again.app.ringing and again.said() == ["Alarm: now."]


def test_a_repeating_alarm_rings_every_day(ta, lang):
    h = Harness(ta, clock=FakeClock(at("2026-09-25 04:59")))
    h.app.start()
    h.app.add_alarm(ta.parse.parse_alarm("setiap hari jam 5 sholat subuh", h.clock.wall, PACKS, "id"))
    h.run(61, step=1)
    assert h.said() == ["Alarm: sholat subuh."]
    assert h.data["items"][0]["due"] == "2026-09-26T05:00:00"


def test_the_computer_slept_through_it(ta, lang):
    h = Harness(ta)
    h.app.start()
    h.app.add_timer(60, "tea")
    h.clock.advance(3 * 3600)                     # asleep
    h.app.tick()
    assert not h.app.ringing and h.data["missed"][0]["item"]["label"] == "tea"
    h.keys.press()
    h.app.tick()
    assert h.said() == ['You missed the timer "tea"; it finished at 10:41.']


def test_snooze(ta, lang):
    h = Harness(ta)
    h.app.start()
    h.app.add_timer(60, "tea")
    h.run(61)
    items, seconds, until = h.app.snooze()
    assert [i["label"] for i in items] == ["tea"] and seconds == 300 and not h.app.ringing
    assert until == h.clock.wall.replace(microsecond=0) + datetime.timedelta(minutes=5)
    assert [i["label"] for i in h.app.schedule.timers()] == ["tea"]
    h.run(301)
    assert h.app.ringing
    # A key stopped it; "tunda" right after still snoozes it, for 10 minutes.
    h.clock.advance(2)
    h.keys.press()
    h.app.tick()
    items, seconds, _until = h.app.snooze(600)
    assert [i["label"] for i in items] == ["tea"] and seconds == 600
    assert h.app.snooze() == ([], 300, None)          # nothing more to snooze


def test_snoozing_a_repeating_alarm_keeps_the_repeat(ta, lang):
    h = Harness(ta, clock=FakeClock(at("2026-09-25 04:59")))
    h.app.start()
    h.app.add_alarm(ta.parse.parse_alarm("setiap hari jam 5 subuh", h.clock.wall, PACKS, "id"))
    h.run(61, step=1)
    snoozed_at = h.clock.wall.replace(microsecond=0)
    h.app.snooze()
    alarms = h.app.schedule.alarms()
    assert [(a["due"], a["recurrence"]) for a in alarms] == [
        (snoozed_at + datetime.timedelta(minutes=5), "none"), (at("2026-09-26 05:00"), "daily")]
    assert alarms[0]["id"] != alarms[1]["id"]


def test_the_same_alarm_twice_is_one(ta, lang):
    h = Harness(ta)
    h.app.start()
    parsed = ta.parse.parse_alarm("besok jam 2 gang war", NOW, PACKS, "id")
    assert h.app.add_alarm(parsed)[1] is True
    assert h.app.add_alarm(parsed)[1] is False
    assert len(h.app.schedule.items) == 1


# ------------------------------------------------------------
# Sentences
# ------------------------------------------------------------

def test_readback_in_both_languages(ta, lang):
    parsed = ta.parse.parse_alarm("besok jam 2 gang war", NOW, PACKS, "id")
    lang("id")
    assert ta.text.readback(parsed, NOW) == \
        "Alarm gang war, besok, Sabtu 26 September, jam 02.00 dini hari. Pasang?"
    lang("en")
    assert ta.text.readback(parsed, NOW) == \
        'Alarm "gang war", tomorrow, Saturday 26 September, at 2:00 AM. Set it?'


def test_readback_notes_and_repeats(ta, lang):
    lang("id")
    parsed = ta.parse.parse_alarm("jam 5 pagi", NOW, PACKS, "id")
    assert ta.text.readback(parsed, NOW) == ("Alarm, besok, Sabtu 26 September, jam 05.00 pagi. "
                                             "Hari ini jam itu sudah lewat, jadi besok. Pasang?")
    parsed = ta.parse.parse_alarm("setiap hari jam 5 sholat subuh", NOW, PACKS, "id")
    assert ta.text.readback(parsed, NOW) == ("Alarm sholat subuh, besok, Sabtu 26 September, "
                                             "jam 05.00 pagi, setiap hari. Pasang?")
    lang("en")
    parsed = ta.parse.parse_alarm("tiap Senin jam 7 olahraga", NOW, PACKS, "id")
    assert ta.text.readback(parsed, NOW) == ('Alarm "olahraga", Monday 28 September, at 7:00 AM, '
                                             'every Monday. Set it?')
    parsed = ta.parse.parse_alarm("5 Januari jam 9", NOW, PACKS, "id")
    assert ta.text.readback(parsed, NOW) == "Alarm, Tuesday 5 January 2027, at 9:00 AM. Set it?"


@pytest.mark.parametrize("clock, id_text, en_text", [
    ("00:00", "00.00 tengah malam", "12:00 midnight"),
    ("00:30", "00.30 dini hari", "12:30 AM"),
    ("02:00", "02.00 dini hari", "2:00 AM"),
    ("03:59", "03.59 dini hari", "3:59 AM"),
    ("04:00", "04.00 pagi", "4:00 AM"),
    ("10:59", "10.59 pagi", "10:59 AM"),
    ("11:00", "11.00 siang", "11:00 AM"),
    ("12:00", "12.00 siang", "12:00 noon"),
    ("14:59", "14.59 siang", "2:59 PM"),
    ("15:00", "15.00 sore", "3:00 PM"),
    ("17:59", "17.59 sore", "5:59 PM"),
    ("18:00", "18.00 malam", "6:00 PM"),
    ("23:59", "23.59 malam", "11:59 PM"),
])
def test_every_time_says_its_part_of_the_day(ta, lang, clock, id_text, en_text):
    moment = at(f"2026-09-25 {clock}")
    lang("id")
    assert ta.text.clock_spoken(moment) == id_text
    lang("en")
    assert ta.text.clock_spoken(moment) == en_text


def test_durations_spoken(ta, lang):
    lang("id")
    assert ta.text.duration_text(5400) == "1 jam 30 menit"
    assert ta.text.duration_text(90) == "1 menit 30 detik"
    assert ta.text.left_text(135.2, precise=True) == "2 menit 16 detik"
    assert ta.text.left_text(20) == "kurang dari semenit"
    lang("en")
    assert ta.text.duration_text(3600) == "1 hour"
    assert ta.text.duration_text(7260) == "2 hours 1 minute"
    assert ta.text.duration_text(1) == "1 second"
    assert ta.text.left_text(15 * 3600 + 19 * 60 + 35) == "15 hours 20 minutes"


def test_ring_and_stop_sentences(ta, lang):
    alarm = ta.store.make_alarm(at("2026-09-26 02:00"), "gang war", now=NOW)
    plain = ta.store.make_alarm(at("2026-09-26 05:00"), "", now=NOW)
    mie = ta.store.make_timer(180, "mie", now=NOW)
    three = ta.store.make_timer(180, "", now=NOW)
    lang("id")
    assert ta.text.ring_text([alarm]) == "Alarm: gang war."
    assert ta.text.ring_text([mie]) == "Timer mie selesai."
    assert ta.text.ring_text([plain, three]) == "Alarm, jam 05.00. Timer 3 menit selesai."
    assert ta.text.stopped_text([alarm, mie]) == "Alarm gang war dan timer mie dimatikan."
    lang("en")
    assert ta.text.ring_text([alarm]) == "Alarm: gang war."
    assert ta.text.ring_text([three]) == "The timer for 3 minutes is done."
    assert ta.text.stopped_text([alarm]) == 'Stopped the alarm "gang war".'


def test_timer_started(ta, lang):
    lang("id")
    assert ta.text.timer_started(ta.store.make_timer(180, "mie", now=NOW)) == \
        "Timer mie, 3 menit, mulai."
    assert ta.text.timer_started(ta.store.make_timer(600, "", now=NOW)) == "Timer 10 menit, mulai."
    lang("en")
    assert ta.text.timer_started(ta.store.make_timer(180, "tea", now=NOW)) == \
        'Timer "tea", 3 minutes, started.'


def test_briefing_sentence(ta, lang):
    schedule = ta.store.Schedule()
    schedule.add(ta.store.make_alarm(at("2026-09-25 14:00"), "gang war", now=NOW))
    schedule.add(ta.store.make_alarm(at("2026-09-26 05:00"), "tomorrow", now=NOW))
    schedule.add(ta.store.make_alarm(at("2026-09-25 09:00"), "earlier", now=NOW))   # already rung
    today = schedule.todays_alarms(NOW)
    lang("en")
    assert ta.text.briefing_sentence(today) == "You have an alarm at 14:00: gang war."
    lang("id")
    assert ta.text.briefing_sentence(today) == "Kamu punya alarm jam 14.00: gang war."
    schedule.add(ta.store.make_alarm(at("2026-09-25 20:30"), "", now=NOW))
    assert ta.text.briefing_sentence(schedule.todays_alarms(NOW)) == \
        "Kamu punya 2 alarm hari ini: jam 14.00, gang war; 20.30."
    assert ta.text.briefing_sentence([]) == ""


# ------------------------------------------------------------
# Aruna: a fake one on top of core.commands.decide
# ------------------------------------------------------------

class FakeAruna:
    """What ui/command_bar.py does with a text, without the window: a
    question waits for yes or no, intents are asked in turn, then commands."""

    def __init__(self, ta, assistant, now):
        import core.commands
        from core import when
        self.c = core.commands
        self.assistant = assistant
        self.said = []
        self.pending = None
        names = {"stop": "Stop the ringing alarm or timer", "snooze": "Snooze the alarm",
                 "time_left": "Say the time left on your timers",
                 "list": "List your alarms and timers", "cancel_timer": "Cancel a timer",
                 "cancel_all_timers": "Cancel all timers", "cancel_alarm": "Delete an alarm"}
        self.actions = {f"Timer and Alarm.{n}": types.SimpleNamespace(description=d)
                        for n, d in names.items()}
        # A few of Hariku's own, to see that nothing is taken from them.
        for action_id in ("Hariku Core.speak_time", "Hariku Core.stop_voice",
                          "Morning Briefing.evening_summary", "Weather.speak_current_weather"):
            self.actions[action_id] = types.SimpleNamespace(description=action_id)
        methods = {"stop": "stop", "snooze": "snooze", "time_left": "time_left",
                   "list": "list_all", "cancel_timer": "cancel_timer",
                   "cancel_all_timers": "cancel_all_timers", "cancel_alarm": "cancel_alarm"}
        self.methods = {f"Timer and Alarm.{n}": m for n, m in methods.items()}
        self.aliases = dict(ta.intents.ALIASES)
        handlers = {"alarm": "on_alarm", "wake": "on_wake", "timer": "on_timer",
                    "cancel": "on_cancel", "stop": "on_stop", "left": "on_time_left",
                    "snooze": "on_snooze", "fix": "on_fix"}
        self.intents = [self.c.Intent(f"Timer and Alarm.{n}", ta.intents.PATTERNS[n],
                                      getattr(assistant, h)) for n, h in handlers.items()]
        self.parse = lambda text: when.parse(text, now=now(), language="id", packs=PACKS)
        self.ran = []

    def commands(self):
        found = []
        for action_id, action in self.actions.items():
            name = action_id.split(".", 1)[1]
            aliases = list(self.c.BUILTIN_ALIASES.get(action_id, [])) + self.aliases.get(name, [])
            found.append(self.c.Command(action_id, action.description, aliases))
        return found

    def send(self, text):
        text = " ".join(text.split())
        if self.pending is not None:
            reply = "yes" if not text else self.c.answer(text)
            pending, self.pending = self.pending, None
            if reply == "yes":
                return self._show(self.c.Reply.of(pending.confirm()))
            if reply == "no":
                if pending.cancel:
                    pending.cancel()
                return self._say("OK, cancelled.")
        decision = self.c.decide(text, candidates=self.commands(), parse=self.parse,
                                 intent_candidates=self.intents)
        if decision.kind == "intent":
            for found in decision.intents:
                request = self.c.Request(found.text, decision.text, "typed", found.intent.id)
                reply = self.c.Reply.of(found.intent.handler(request))
                if reply is not None:
                    return self._show(reply)
            decision = decision.fallback
        if decision.kind == "run":
            self.ran.append(decision.action_id)
            method = self.methods.get(decision.action_id)
            return self._say(getattr(self.assistant, method)() if method else decision.action_id)
        return self._say(f"<{decision.kind}>")

    def _show(self, reply):
        if reply is None:
            return self._say("")
        if reply.confirm is not None:
            self.pending = reply
        return self._say(reply.say)

    def _say(self, text):
        self.said.append(text)
        return text


@pytest.fixture
def aruna(ta, lang):
    h = Harness(ta)
    h.app.start()
    assistant = ta.intents.Assistant(h.app)
    bar = FakeAruna(ta, assistant, lambda: h.clock.wall)
    assistant._match = lambda text: bar.c.match(text, bar.commands())
    return types.SimpleNamespace(h=h, bar=bar, app=h.app)


def test_aruna_sets_an_alarm_after_asking(aruna, lang):
    lang("id")
    bar = aruna.bar
    assert bar.send("alarm besok jam 2 gang war") == \
        "Alarm gang war, besok, Sabtu 26 September, jam 02.00 dini hari. Pasang?"
    assert aruna.app.schedule.items == []                         # not before the answer
    assert bar.send("pasang") == "Alarm dipasang, 15 jam 20 menit lagi."
    assert [a["label"] for a in aruna.app.schedule.alarms()] == ["gang war"]
    assert aruna.h.data["items"][0]["due"] == "2026-09-26T02:00:00"


def test_aruna_english_and_no(aruna, lang):
    lang("en")
    bar = aruna.bar
    assert bar.send("Set alarm tomorrow at 2 for gang war") == \
        'Alarm "gang war", tomorrow, Saturday 26 September, at 2:00 AM. Set it?'
    assert bar.send("no") == "OK, cancelled."
    assert aruna.app.schedule.items == []
    # Rephrased with the part of the day, the time is right.
    assert bar.send("jam 2 siang") == \
        'Alarm "gang war", tomorrow, Saturday 26 September, at 2:00 PM. Set it?'
    assert bar.send("yes").startswith("Alarm set, ")
    assert aruna.app.schedule.alarms()[0]["due"] == at("2026-09-26 14:00")
    # The correction was used up: "jam 2 siang" now is what it always was.
    assert bar.send("jam 2 siang") == "<reminder>"


def test_aruna_answering_with_a_correction(aruna, lang):
    lang("id")
    bar = aruna.bar
    bar.send("bangunkan aku besok jam 4.30")
    assert bar.send("at 5") == "Alarm, besok, Sabtu 26 September, jam 05.00 pagi. Pasang?"
    assert bar.send("ya").startswith("Alarm dipasang")


def test_aruna_says_what_is_missing(aruna, lang):
    lang("id")
    bar = aruna.bar
    assert bar.send("alarm gang war").startswith("Jam berapa?")
    assert bar.send("jam 7 pagi") == "Alarm gang war, besok, Sabtu 26 September, jam 07.00 pagi. " \
        "Hari ini jam itu sudah lewat, jadi besok. Pasang?"
    assert bar.send("pasang alarm besok pagi").startswith("Aku tangkap besok, pagi")
    assert bar.send("alarm hari ini jam 8 pagi") == "Waktu itu sudah lewat. Sebutkan waktu lain."


def test_aruna_timers(aruna, lang):
    lang("id")
    bar = aruna.bar
    assert bar.send("timer mie 3 menit") == "Timer mie, 3 menit, mulai."
    assert bar.send("timer lima menit teh") == "Timer teh, 5 menit, mulai."
    assert bar.send("hitung mundur 90 detik") == "Timer 1 menit 30 detik, mulai."
    assert bar.send("timer setengah jam") == "Timer 30 menit, mulai."
    assert bar.send("timer mie") == 'Berapa lama? Misalnya: "timer 10 menit".'
    assert len(aruna.app.schedule.timers()) == 4
    aruna.h.clock.advance(30)
    assert bar.send("sisa timer mie") == "Timer mie: sisa 2 menit 30 detik."
    assert bar.send("batalkan timer mie") == "Timer mie dibatalkan."
    assert bar.send("batalkan timer mie") == "Aku tidak menemukan timer mie."
    assert bar.send("batalkan timer").startswith("Timermu: 1 menit 30 detik, sisa 1 menit")
    assert bar.send("batalkan semua timer") == "3 timer dibatalkan."
    assert bar.send("sisa timer") == "Tidak ada timer yang berjalan."


def test_aruna_timers_in_english(aruna, lang):
    lang("en")
    bar = aruna.bar
    assert bar.send("set a timer for 1 hour 30 minutes") == "Timer, 1 hour 30 minutes, started."
    assert bar.send("timer tea 3 minutes") == 'Timer "tea", 3 minutes, started.'
    assert bar.send("how long is left on the tea timer") == 'The timer "tea": 3 minutes left.'
    assert bar.send("cancel the tea timer") == 'Cancelled the timer "tea".'
    assert bar.send("cancel all timers") == "Cancelled 1 timer."


def test_aruna_deletes_an_alarm_after_asking(aruna, lang):
    lang("id")
    bar = aruna.bar
    bar.send("alarm besok jam 2 gang war")
    bar.send("ya")
    assert bar.send("hapus alarm gang war") == "Hapus alarm gang war, besok jam 02.00 dini hari?"
    assert bar.send("tidak") == "OK, cancelled."
    assert len(aruna.app.schedule.alarms()) == 1
    bar.send("hapus alarm gang war")
    assert bar.send("ya") == "Alarm gang war dihapus."
    assert aruna.app.schedule.alarms() == []


def test_aruna_english_alarm_names(aruna, lang):
    lang("en")
    bar = aruna.bar
    assert bar.send("set an alarm for 6") == \
        "Alarm, today, Friday 25 September, at 6:00 PM. Set it?"
    bar.send("yes")
    bar.send("set alarm tomorrow at 2 for football")
    bar.send("set it")
    assert len(aruna.app.schedule.alarms()) == 2
    assert bar.send("how long until the football alarm") == \
        'The alarm "football": tomorrow at 2:00 AM, 15 hours 20 minutes from now.'
    assert bar.send("delete the alarm for football") == \
        'Delete the alarm "football", tomorrow at 2:00 AM?'
    assert bar.send("yes") == 'Deleted the alarm "football".'
    assert bar.send("delete the 18:00 alarm") == "Delete the 18:00 alarm, today at 6:00 PM?"
    assert bar.send("no") == "OK, cancelled."
    assert bar.send("delete all alarms") == "Delete all 1 of your alarms?"
    assert bar.send("yes") == "Deleted 1 alarm."
    assert aruna.app.schedule.alarms() == []


def test_aruna_a_new_command_instead_of_an_answer(aruna, lang):
    lang("id")
    bar = aruna.bar
    bar.send("alarm besok jam 2 gang war")
    # Not "pasang" alone: a new alarm, asked about in turn.
    assert bar.send("pasang alarm jam 6 pagi").startswith("Alarm, besok, Sabtu 26 September, "
                                                          "jam 06.00 pagi.")
    assert bar.send("ya").startswith("Alarm dipasang")
    assert [a["label"] for a in aruna.app.schedule.alarms()] == [""]


def test_aruna_correction_after_an_impossible_date(aruna, lang):
    lang("id")
    bar = aruna.bar
    assert bar.send("alarm tanggal 31 Februari jam 7") == \
        "Tanggal itu tidak ada. Periksa tanggal dan bulannya."
    assert bar.send("jam 8") == "Tanggal itu tidak ada. Periksa tanggal dan bulannya."
    # A new day with the time corrects it ("{text} pagi").
    assert bar.send("28 Februari jam 8 pagi") == \
        "Alarm, Minggu 28 Februari 2027, jam 08.00 pagi. Pasang?"


def test_aruna_list_and_nothing_to_do(aruna, lang):
    lang("id")
    bar = aruna.bar
    assert bar.send("daftar alarm").startswith("Belum ada alarm atau timer.")
    assert bar.send("stop").startswith("Tidak ada yang berbunyi.")
    assert bar.send("tunda") == "Tidak ada yang bisa ditunda."
    bar.send("alarm setiap hari jam 5 sholat subuh")
    bar.send("ya")
    bar.send("timer mie 3 menit")
    assert bar.send("daftar alarm") == ("Alarm: sholat subuh, setiap hari jam 05.00 pagi. "
                                        "Timer: mie, sisa 3 menit.")


def test_aruna_stop_and_snooze_while_ringing(aruna, lang):
    lang("id")
    bar, h = aruna.bar, aruna.h
    bar.send("timer mie 1 menit")
    h.run(61)
    assert aruna.app.ringing
    assert bar.send("tunda 10 menit") == "Timer mie ditunda 10 menit, sampai jam 10.51 pagi."
    assert not aruna.app.ringing
    h.run(601)
    assert aruna.app.ringing
    assert bar.send("stop") == "Timer mie dimatikan."
    assert bar.send("stop") == "Timer mie sudah dimatikan."
    assert aruna.app.schedule.items == []


def test_aruna_leaves_other_commands_alone(aruna, lang):
    lang("id")
    bar = aruna.bar
    bar.send("jam berapa")
    assert bar.ran[-1] == "Hariku Core.speak_time"
    bar.send("ringkasan malam")
    assert bar.ran[-1] == "Morning Briefing.evening_summary"
    bar.send("berhenti bicara")
    assert bar.ran[-1] == "Hariku Core.stop_voice"
    bar.send("alarm list")                          # a command, not an alarm "list"
    assert bar.ran[-1] == "Timer and Alarm.list"
    assert bar.send("ingatkan aku minum obat besok jam 8") == "<reminder>"


# ------------------------------------------------------------
# Registering with Hariku
# ------------------------------------------------------------

@pytest.fixture
def main(ta, monkeypatch, lang):
    import importlib.util
    import core.api
    import core.commands
    import core.hotkeys
    import core.preferences
    monkeypatch.setattr(core.commands, "_intents", {})
    monkeypatch.setattr(core.commands, "_aliases", {})
    monkeypatch.setattr(core.commands, "_titles", {})
    monkeypatch.setattr(core.commands, "_answer_actions", set())
    monkeypatch.setattr(core.preferences, "_panels", {})
    monkeypatch.setattr(core.hotkeys, "actions", {})
    monkeypatch.setattr(core.hotkeys, "keybindings", {})
    timers = []

    class FakeTimer:
        def __init__(self, ms, fn):
            self.ms, self.fn, self.running = ms, fn, True
            timers.append(self)

        def Start(self, ms):
            self.ms = ms

        def Stop(self):
            self.running = False

    monkeypatch.setattr(core.api, "set_interval", lambda ms, fn: FakeTimer(ms, fn))
    spec = importlib.util.spec_from_file_location("hariku_ext.timer_alarm_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from core.events import EventBus
    bus = EventBus()
    h = Harness(ta)
    module.register(bus, app=h.app)
    yield types.SimpleNamespace(module=module, bus=bus, h=h, timers=timers)
    module.teardown()


def test_registering(main):
    import core.commands
    import core.hotkeys
    import core.preferences
    ids = [f"Timer and Alarm.{n}" for n in main.module.ACTIONS]
    assert sorted(core.hotkeys.actions) == sorted(ids)
    assert all(core.hotkeys.actions[i].default_keycode is None for i in ids)   # no default keys
    assert all(core.commands.is_answer_action(i) for i in ids)
    assert "stop" in core.commands.aliases_for("Timer and Alarm.stop")
    assert "tunda" in core.commands.aliases_for("Timer and Alarm.snooze")
    assert sorted(i.id for i in core.commands.intents()) == sorted(
        f"Timer and Alarm.{n}" for n in main.module.INTENTS)
    assert "Timer & Alarm" in core.preferences.get_all_panels()
    assert main.timers and main.timers[0].ms == 1000


def test_registered_intents_answer(main, lang):
    import core.commands
    lang("id")
    found = core.commands.match_intents("timer mie 3 menit")
    assert found[0].intent.id == "Timer and Alarm.timer"
    reply = found[0].intent.handler(core.commands.Request(found[0].text, "timer mie 3 menit"))
    assert reply == "Timer mie, 3 menit, mulai."


def test_the_tick_speeds_up_while_ringing(main, lang):
    main.h.app.add_timer(1, "tea")
    main.h.clock.advance(2)
    main.timers[0].fn()
    assert main.h.app.ringing and main.timers[0].ms == 250
    main.h.app.stop()
    main.timers[0].fn()
    assert main.timers[0].ms == 1000


def test_briefing_through_the_bus(main, lang):
    lang("en")
    main.h.app.add_alarm(main.h.ta.parse.parse_alarm("at 14:00 gang war", NOW, PACKS, "en"))
    lines = []
    main.bus.emit("on_briefing_collect", lines)
    assert lines == ["You have an alarm at 14:00: gang war."]


def test_teardown_removes_what_it_added(main):
    import core.commands
    main.module.teardown()
    assert core.commands.intents() == []
    assert core.commands.aliases_for("Timer and Alarm.stop") == []
    assert not main.timers[0].running
    lines = []
    main.bus.emit("on_briefing_collect", lines)
    assert lines == []


# ------------------------------------------------------------
# Sounds and files
# ------------------------------------------------------------

def test_shipped_tones(ta):
    for name in ta.system.TONES.values():
        with wave.open(os.path.join(EXT_DIR, "sounds", name)) as w:
            assert w.getnchannels() == 1 and w.getframerate() == 44100
            assert 1.0 < w.getnframes() / w.getframerate() < 3.0


def test_sound_path_falls_back_to_the_tone(ta, tmp_path):
    system = ta.system
    (tmp_path / "Alarm01.wav").write_bytes(b"RIFF")
    assert system.sound_path("windows:Alarm01.wav", "alarm", str(tmp_path)) == \
        str(tmp_path / "Alarm01.wav")
    assert system.sound_path("windows:Alarm02.wav", "timer", str(tmp_path)) == \
        system.tone_path("timer")
    assert system.sound_path("windows:..\\evil.wav", "alarm", str(tmp_path)) == \
        system.tone_path("alarm")
    assert system.sound_path("tone:timer", "alarm") == system.tone_path("timer")
    choices = system.available_choices(str(tmp_path))
    assert [c[0] for c in choices] == ["windows:Alarm01.wav", "tone:alarm", "tone:timer"]


def test_default_sounds_differ(ta):
    defaults = ta.store.DEFAULT_SETTINGS
    assert defaults["alarm_sound"] == "windows:Alarm01.wav"
    assert defaults["timer_sound"] != defaults["alarm_sound"]
    assert ta.store.is_sound_choice(defaults["timer_sound"])


def test_locales_have_the_same_keys():
    with open(os.path.join(EXT_DIR, "locales", "en.json"), encoding="utf-8") as f:
        en = json.load(f)["messages"]
    with open(os.path.join(EXT_DIR, "locales", "id.json"), encoding="utf-8") as f:
        indonesian = json.load(f)["messages"]
    assert sorted(en) == sorted(indonesian)


def test_keys_made_at_run_time_exist(ta):
    with open(os.path.join(EXT_DIR, "locales", "en.json"), encoding="utf-8") as f:
        en = json.load(f)["messages"]
    needed = [f"action_{n}" for n in ("stop", "snooze", "time_left", "list", "cancel_timer",
                                      "cancel_all_timers", "cancel_alarm")]
    needed += [f"intent_{n}" for n in ta.intents.PATTERNS]
    needed += ["date", "date_year", "title_alarm_named", "title_alarm_plain", "title_timer_named",
               "title_timer_plain", "dur_hour", "dur_hours", "dur_minute", "dur_minutes",
               "dur_second", "dur_seconds", "closed_alarm", "closed_timer", "missed_alarm",
               "missed_timer", "part_midnight", "part_early", "part_morning", "part_midday",
               "part_afternoon", "part_evening"] + list(ta.text.PROBLEM_KEYS.values())
    assert [k for k in needed if k not in en] == []


def test_official_extension():
    import ast
    for path, name in (("core/extension_manager.py", "_OFFICIAL_EXTENSION_IDS"),
                       ("tools/server/generate_trusted_hashes.py", "OFFICIAL_EXTENSION_IDS")):
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            assert '"timer_alarm"' in f.read(), path
    with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["id"] == "timer_alarm" and manifest["minimum_core_version"] == "2.9"
    assert manifest["version"] == "1.0"
