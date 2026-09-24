# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Sleep Pattern extension: idle time, sampling and gaps, sleep
# detection, corrections, averages, sentences in both languages, the late-night
# reminder and the briefing. The Windows API is never called: every test uses
# fake DLLs or a fake clock, and the real loader is made to fail loudly.

import datetime
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "sleep_tracker")
NIGHT = datetime.date(2026, 9, 23)     # a Wednesday: the night from Tuesday 18:00
MINUTE = datetime.timedelta(minutes=1)
SETTINGS = {"enabled": True, "bedtime": 0, "min_sleep": 180, "ignore_activity": 10,
            "nudge": False, "nudge_sound": True}


def _helpers():
    if EXT_DIR not in sys.path:
        sys.path.insert(0, EXT_DIR)
    import sleep_tracker_analysis
    import sleep_tracker_store
    import sleep_tracker_system
    import sleep_tracker_text
    return sleep_tracker_store, sleep_tracker_analysis, sleep_tracker_system, sleep_tracker_text


@pytest.fixture(scope="module")
def store():
    return _helpers()[0]


@pytest.fixture(scope="module")
def analysis():
    return _helpers()[1]


@pytest.fixture(scope="module")
def system():
    return _helpers()[2]


@pytest.fixture(scope="module")
def text():
    return _helpers()[3]


@pytest.fixture
def lang(monkeypatch, text):
    """Switch the UI language; the core day and month names are loaded too."""
    from core import i18n
    had_core, old_core = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("en")
    yield set_lang
    if had_core:
        i18n._language_cache["core"] = old_core
    else:
        i18n._language_cache.pop("core", None)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def at(day, clock, second=0):
    """Local time "HH:MM" on NIGHT plus `day` days."""
    hour, minute = map(int, clock.split(":"))
    return datetime.datetime.combine(NIGHT + datetime.timedelta(days=day),
                                     datetime.time(hour, minute, second))


def fill(rec, start, end, state):
    """Set the minutes from `start` up to `end` directly."""
    t = start
    while t < end:
        rec.days.setdefault(t.date(), bytearray(1440))[t.hour * 60 + t.minute] = state
        t += MINUTE


def recorder(store, *spans, base=None, start=None, end=None):
    """A record that is active (or `base`) from 06:00 two days before NIGHT to
    06:00 the day after, then each (start, end, state) span on top."""
    rec = store.Recorder()
    fill(rec, start or at(-2, "06:00"), end or at(1, "06:00"),
         store.ACTIVE if base is None else base)
    for span_start, span_end, state in spans:
        fill(rec, span_start, span_end, state)
    return rec


def states(rec, start, end):
    """The minutes from `start` up to `end` as letters: u, i, a."""
    out = []
    t = start
    while t < end:
        out.append("uia"[rec.state_at(t)])
        t += MINUTE
    return "".join(out)


def sample(system, when, idle=0.0, boot=None, asleep=0.0):
    """A sample at local time `when`; the machine booted at `boot` and has
    slept `asleep` seconds since."""
    boot = boot or at(-3, "08:00")
    wall = when.timestamp()
    uptime = wall - boot.timestamp()
    return system.make_sample(wall, uptime * 1000, (uptime - asleep) * 1e7, idle * 1000)


def analyze(analysis, rec, night=NIGHT, now=None, corrections=(), **settings):
    return analysis.Nights().get(rec, night, dict(SETTINGS, **settings), tuple(corrections), now)


def span_of(result):
    return result["main"]["start"], result["main"]["end"]


# ------------------------------------------------------------
# Idle time and the Windows calls (all faked)
# ------------------------------------------------------------

def test_idle_time_from_tick_counts(system):
    assert system.idle_ms(10_000, 4_000) == 6_000
    assert system.idle_ms(4_000, 4_000) == 0


def test_idle_time_across_the_49_day_wrap(system):
    # The tick count wrapped to 500 after the last input at 2**32 - 256.
    assert system.idle_ms(500, 0xFFFFFF00) == 756
    assert system.idle_ms(0, 0xFFFFFFFF) == 1


def test_input_after_the_tick_was_read_means_no_idle_time(system):
    assert system.idle_ms(100, 150) == 0


def test_make_sample(system):
    sample_ = system.make_sample(1_000_000.0, 3_600_000, 30_000_000_000, 90_500)
    assert sample_ == {"wall": 1_000_000.0, "tick": 3_600_000, "boot": 996_400.0,
                       "awake": 3000.0, "idle": 90.5}
    assert system.make_sample(5.0, 1000, None, 0)["awake"] is None


class FakeUser32:
    def __init__(self, last_input, ok=True):
        self.last_input, self.ok, self.calls = last_input, ok, 0

    def GetLastInputInfo(self, ref):
        self.calls += 1
        info = ref._obj
        assert info.cbSize == 8
        info.dwTime = self.last_input
        return 1 if self.ok else 0


class FakeKernel32:
    def __init__(self, tick32, tick64, unbiased, unbiased_ok=True):
        self.tick32, self.tick64, self.unbiased, self.unbiased_ok = tick32, tick64, unbiased, unbiased_ok

    def GetTickCount(self):
        return self.tick32

    def GetTickCount64(self):
        return self.tick64

    def QueryUnbiasedInterruptTime(self, ref):
        ref._obj.value = self.unbiased
        return 1 if self.unbiased_ok else 0


def test_clock_reads_the_four_calls(system, monkeypatch):
    def no_real_dlls():
        raise AssertionError("the real Windows DLLs must not be loaded here")

    monkeypatch.setattr(system, "_load_dlls", no_real_dlls)
    user32 = FakeUser32(last_input=0xFFFFFF00)
    kernel32 = FakeKernel32(tick32=500, tick64=5 * 86400 * 1000, unbiased=4 * 86400 * 10**7)
    clock = system.WindowsClock(user32, kernel32, wall=lambda: 2_000_000.0)
    assert clock.available
    assert clock.read() == {"wall": 2_000_000.0, "tick": 432_000_000, "boot": 1_568_000.0,
                            "awake": 345_600.0, "idle": 0.756}
    assert user32.calls == 1

    kernel32.unbiased_ok = False
    assert clock.read()["awake"] is None
    user32.ok = False
    assert clock.read() is None


def test_clock_survives_api_failures(system):
    class Broken:
        def GetLastInputInfo(self, ref):
            raise OSError("access denied")

    clock = system.WindowsClock(Broken(), FakeKernel32(1, 1, 1), wall=lambda: 1.0)
    assert clock.read() is None
    unavailable = system.WindowsClock.__new__(system.WindowsClock)
    unavailable._user32 = unavailable._kernel32 = None
    assert not unavailable.available and unavailable.read() is None


def test_no_hooks_and_nothing_about_apps_or_keys():
    # Privacy and NVDA: only GetLastInputInfo. No keyboard or mouse hook (one
    # once broke NVDA's modifier key), no global hotkeys, nothing about windows,
    # apps or the clipboard.
    forbidden = ("SetWindowsHookEx", "WH_KEYBOARD", "WH_MOUSE", "RegisterHotKey",
                 "default_global=True", "GetForegroundWindow", "GetWindowText",
                 "get_active_window_info", "on_active_window_changed", "on_clipboard_changed",
                 "GetAsyncKeyState", "GetKeyState")
    for name in os.listdir(EXT_DIR):
        if name.endswith(".py"):
            with open(os.path.join(EXT_DIR, name), encoding="utf-8") as f:
                source = f.read()
            for word in forbidden:
                assert word not in source, f"{name} uses {word}"


# ------------------------------------------------------------
# Sampling
# ------------------------------------------------------------

def test_first_sample_records_only_the_last_minute(store, system):
    rec = store.Recorder()
    rec.add_sample(sample(system, at(0, "10:00", 30), idle=5))
    assert states(rec, at(0, "09:58"), at(0, "10:02")) == "uuau"
    rec = store.Recorder()
    rec.add_sample(sample(system, at(0, "10:00", 30), idle=300))
    assert states(rec, at(0, "09:58"), at(0, "10:02")) == "uiiu"


def test_samples_a_minute_apart_record_every_minute(store, system):
    rec = store.Recorder()
    # Typing, typing, then away for three minutes, then back.
    for i, idle in enumerate((5, 5, 70, 130, 190, 2)):
        rec.add_sample(sample(system, at(0, "10:00", 10) + i * MINUTE, idle=idle))
    assert states(rec, at(0, "10:00"), at(0, "10:06")) == "aaiiia"
    assert rec.last["wall"] == (at(0, "10:05", 10)).timestamp()


def test_a_minute_with_input_stays_active(store, system):
    rec = store.Recorder()
    rec.mark_minute(at(0, "10:00", 20).timestamp(), store.ACTIVE)
    rec.mark(at(0, "09:59").timestamp(), at(0, "10:02").timestamp(), store.INACTIVE)
    assert states(rec, at(0, "09:59"), at(0, "10:03")) == "iaii"


def test_shutdown_and_restart_count_as_not_using_the_computer(store, system):
    rec = store.Recorder()
    rec.add_sample(sample(system, at(-1, "23:50"), idle=5, boot=at(-1, "08:00")))
    # Saved as Hariku closed, then read back the next morning.
    rec = store.Recorder.from_data(json.loads(json.dumps(rec.to_data(final=True))))
    assert rec.last["final"] is True
    rec.add_sample(sample(system, at(0, "07:40", 30), idle=5, boot=at(0, "07:39")))
    assert states(rec, at(-1, "23:49"), at(-1, "23:50")) == "a"
    assert set(states(rec, at(-1, "23:50"), at(0, "07:40"))) == {"i"}
    assert states(rec, at(0, "07:40"), at(0, "07:41")) == "a"
    assert "final" not in rec.last


def test_restart_after_a_periodic_save_leaves_the_unsaved_minutes_unknown(store, system):
    # Hariku was killed (by Windows shutting down, say), so it may have kept
    # running for up to 10 minutes after the last save.
    rec = store.Recorder()
    rec.add_sample(sample(system, at(-1, "23:50"), idle=5, boot=at(-1, "08:00")))
    rec = store.Recorder.from_data(json.loads(json.dumps(rec.to_data())))
    rec.add_sample(sample(system, at(0, "07:40", 30), idle=5, boot=at(0, "07:39")))
    assert states(rec, at(-1, "23:51"), at(0, "00:00")) == "u" * 9
    assert set(states(rec, at(0, "00:00"), at(0, "07:40"))) == {"i"}


def test_machine_sleep_counts_as_inactive(store, system):
    # The lid was closed at 01:00:30 and opened at 07:39:30.
    rec = store.Recorder()
    boot = at(-1, "08:00")
    rec.add_sample(sample(system, at(0, "01:00"), idle=3, boot=boot))
    slept = (at(0, "07:39", 30) - at(0, "01:00", 30)).total_seconds()
    rec.add_sample(sample(system, at(0, "07:40", 30), idle=20, boot=boot, asleep=slept))
    assert states(rec, at(0, "00:59"), at(0, "07:41")) == "a" + "i" * 400 + "a"


def test_hariku_closed_on_an_awake_computer_is_unknown(store, system):
    rec = store.Recorder()
    boot = at(-1, "08:00")
    rec.add_sample(sample(system, at(-1, "22:00"), idle=2, boot=boot))
    # Started again at 08:00; the last input was at 07:30.
    rec.add_sample(sample(system, at(0, "08:00"), idle=1800, boot=boot))
    assert set(states(rec, at(-1, "22:01"), at(0, "07:30"))) == {"u"}
    assert states(rec, at(0, "07:30"), at(0, "07:31")) == "a"
    assert set(states(rec, at(0, "07:31"), at(0, "08:01"))) == {"i"}


def test_no_input_during_a_gap_is_inactive_whatever_the_reason(store, system):
    rec = store.Recorder()
    boot = at(-1, "08:00")
    rec.add_sample(sample(system, at(-1, "22:00"), idle=2, boot=boot))
    rec.add_sample(sample(system, at(0, "08:00"), idle=10 * 3600 + 60, boot=boot))
    assert set(states(rec, at(-1, "22:00"), at(0, "08:01"))) == {"i"}


def test_same_boot_detection(store, system):
    boot = at(-1, "08:00")
    prev = sample(system, at(0, "01:00"), boot=boot)
    assert store.same_boot(prev, sample(system, at(0, "07:00"), boot=boot))
    assert store.same_boot(prev, sample(system, at(0, "07:00"), boot=boot + 2 * MINUTE))
    # A new boot whose uptime is already longer than the old one's.
    assert not store.same_boot(prev, sample(system, at(0, "20:00"), boot=at(0, "02:00")))
    later = dict(prev, tick=prev["tick"] - 1)
    assert not store.same_boot(prev, later)


def test_machine_sleep_seconds(store, system):
    boot = at(-1, "08:00")
    prev = sample(system, at(0, "01:00"), boot=boot)
    now = sample(system, at(0, "02:00"), boot=boot, asleep=1800)
    assert store.machine_sleep_seconds(prev, now) == pytest.approx(1800)
    assert store.machine_sleep_seconds(prev, dict(now, awake=None)) == 0
    assert store.machine_sleep_seconds(prev, dict(now, awake=0.0)) == pytest.approx(3600)


def test_clock_set_back_records_only_the_new_minute(store, system):
    rec = store.Recorder()
    rec.add_sample(sample(system, at(0, "12:00"), idle=2))
    rec.add_sample(sample(system, at(0, "11:00"), idle=2))
    assert states(rec, at(0, "10:59"), at(0, "11:01")) == "ai"
    assert states(rec, at(0, "11:01"), at(0, "11:59")) == "u" * 58


def test_a_very_long_gap_only_fills_the_kept_days(store, system):
    rec = store.Recorder()
    rec.add_sample(sample(system, at(-300, "12:00"), idle=2, boot=at(-301, "08:00")))
    rec.add_sample(sample(system, at(0, "12:00"), idle=2, boot=at(0, "11:00")))
    filled = [d for d in rec.days if d != NIGHT - datetime.timedelta(days=300)]
    assert min(filled) == NIGHT - datetime.timedelta(days=store.KEEP_DAYS)


# ------------------------------------------------------------
# Storage
# ------------------------------------------------------------

def test_day_encoding_round_trip(store):
    minutes = bytearray([1] * 420 + [2] * 15 + [0] * 1005)
    assert store.encode_day(minutes) == "420i15a1005u"
    assert store.decode_day("420i15a1005u") == minutes
    for bad in (None, "", "12x", "1440u1a", "100i", "abc", 42, "0i1440u1i"):
        assert store.decode_day(bad) is None, bad


def test_record_round_trip_and_corrupt_data(store, system):
    rec = recorder(store, (at(0, "01:00"), at(0, "07:00"), store.INACTIVE))
    rec.add_sample(sample(system, at(0, "09:00"), idle=2))
    data = json.loads(json.dumps(rec.to_data()))
    assert set(data) == {"version", "days", "last"}
    again = store.Recorder.from_data(data)
    assert again.days == rec.days and again.last == rec.last and not again.dirty

    data["days"]["2026-99-01"] = "1440u"
    data["days"]["2026-09-01"] = "garbage"
    data["last"] = {"wall": "soon"}
    broken = store.Recorder.from_data(data)
    assert set(broken.days) == set(rec.days) and broken.last is None
    for junk in (None, [], "x", {"days": "x", "last": 5}):
        assert store.Recorder.from_data(junk).days == {}


def test_saving_re_encodes_only_the_days_that_changed(store, system, monkeypatch):
    rec = recorder(store, (at(0, "11:00"), at(0, "13:00"), store.INACTIVE))
    first = rec.to_data()
    calls = []
    real_encode = store.encode_day
    monkeypatch.setattr(store, "encode_day", lambda minutes: calls.append(1) or real_encode(minutes))
    assert rec.to_data() == first and calls == []
    rec.add_sample(sample(system, at(0, "12:00"), idle=2))
    assert rec.to_data()["days"] != first["days"] and len(calls) == 1
    loaded = store.Recorder.from_data(json.loads(json.dumps(first)))
    assert loaded.to_data()["days"] == first["days"] and len(calls) == 1


def test_only_minute_states_are_stored(store, system):
    rec = recorder(store)
    rec.add_sample(sample(system, at(0, "09:00"), idle=2))
    data = rec.to_data()
    assert set(data["last"]) == {"wall", "tick", "boot", "awake", "idle"}
    for text_ in data["days"].values():
        assert set(text_) <= set("0123456789uia")


def test_history_older_than_90_days_is_pruned(store):
    rec = store.Recorder()
    for age in (120, 90, 89, 0):
        fill(rec, at(-age, "10:00"), at(-age, "11:00"), store.ACTIVE)
    rec.days[NIGHT - datetime.timedelta(days=5)] = bytearray(1440)   # nothing known
    data = rec.to_data(NIGHT)
    assert sorted(data["days"]) == [(NIGHT - datetime.timedelta(days=89)).isoformat(),
                                    NIGHT.isoformat()]
    rec = store.Recorder()
    fill(rec, at(-95, "10:00"), at(-95, "11:00"), store.ACTIVE)
    fill(rec, at(0, "10:00"), at(0, "11:00"), store.ACTIVE)
    loaded = store.Recorder.from_data(rec.to_data(), today=NIGHT)
    assert list(loaded.days) == [NIGHT]


def test_settings_survive_corrupt_data(store):
    for raw in (None, "x", [], {}, {"bedtime": 45, "min_sleep": True, "ignore_activity": "10",
                                    "enabled": "yes", "nudge": 1}):
        assert store.normalize_settings(raw) == store.DEFAULT_SETTINGS
    kept = store.normalize_settings({"enabled": False, "bedtime": 1350, "min_sleep": 240,
                                     "ignore_activity": 0, "nudge": True, "nudge_sound": False,
                                     "extra": 1})
    assert kept == {"enabled": False, "bedtime": 1350, "min_sleep": 240, "ignore_activity": 0,
                    "nudge": True, "nudge_sound": False}
    assert store.DEFAULT_SETTINGS["enabled"] is True and store.DEFAULT_SETTINGS["nudge"] is False


def test_corrections_are_validated_and_pruned(store):
    raw = [{"night": "2026-09-23", "start": 10.0, "end": 20.0},
           {"night": "2026-09-23", "start": 20.0, "end": 10.0},
           {"night": "bad", "start": 1, "end": 2},
           {"night": "2026-05-01", "start": 1, "end": 2},
           "junk"]
    assert store.normalize_corrections(raw, NIGHT) == [{"night": "2026-09-23", "start": 10.0,
                                                        "end": 20.0}]
    assert store.corrections_for(store.normalize_corrections(raw), NIGHT) == ((10.0, 20.0),)
    assert store.normalize_corrections(None) == []


# ------------------------------------------------------------
# Sleep detection
# ------------------------------------------------------------

def test_main_sleep_and_staying_up_late(store, analysis):
    rec = recorder(store, (at(0, "01:15"), at(0, "07:40"), store.INACTIVE))
    result = analyze(analysis, rec)
    assert result["status"] == "sleep"
    assert span_of(result) == (at(0, "01:15"), at(0, "07:40"))
    assert result["main"]["asleep"] == 385 and result["main"]["wakeups"] == 0
    assert result["late"] and not result["daytime"] and result["naps"] == []
    assert not analyze(analysis, rec, bedtime=120)["late"]      # bedtime 02:00


def test_asleep_before_bedtime_is_not_late(store, analysis):
    rec = recorder(store, (at(-1, "23:30"), at(0, "07:00"), store.INACTIVE))
    assert not analyze(analysis, rec)["late"]
    assert analyze(analysis, rec, bedtime=1320)["late"]           # bedtime 22:00
    exactly = recorder(store, (at(0, "00:00"), at(0, "07:00"), store.INACTIVE))
    assert not analyze(analysis, exactly)["late"]


def test_brief_activity_is_merged_into_the_sleep(store, analysis):
    rec = recorder(store, (at(0, "00:30"), at(0, "07:00"), store.INACTIVE),
                   (at(0, "03:00"), at(0, "03:05"), store.ACTIVE))
    result = analyze(analysis, rec)
    assert span_of(result) == (at(0, "00:30"), at(0, "07:00"))
    assert result["main"]["asleep"] == 385
    assert (result["main"]["awake"], result["main"]["wakeups"]) == (5, 1)
    # Not ignored: the longer half is the sleep.
    assert span_of(analyze(analysis, rec, ignore_activity=0)) == (at(0, "03:05"), at(0, "07:00"))
    longer = recorder(store, (at(0, "00:30"), at(0, "07:00"), store.INACTIVE),
                      (at(0, "03:00"), at(0, "03:08"), store.ACTIVE))
    assert span_of(analyze(analysis, longer, ignore_activity=5)) == (at(0, "03:08"), at(0, "07:00"))
    assert span_of(analyze(analysis, longer, ignore_activity=10)) == (at(0, "00:30"), at(0, "07:00"))


def test_short_pauses_while_reading_do_not_add_up_to_sleep(store, analysis):
    spans = []
    t = at(-1, "20:00")
    while t < at(0, "08:00"):
        spans.append((t, t + 10 * MINUTE, store.INACTIVE))    # 10 quiet minutes, 2 active
        t += 12 * MINUTE
    result = analyze(analysis, recorder(store, *spans), ignore_activity=15)
    assert result["status"] == "no_sleep" and result["main"] is None


def test_a_short_unknown_stretch_is_bridged_but_never_counted(store, analysis):
    rec = recorder(store, (at(0, "00:00"), at(0, "07:00"), store.INACTIVE),
                   (at(0, "03:00"), at(0, "03:10"), store.UNKNOWN))
    result = analyze(analysis, rec)
    assert span_of(result) == (at(0, "00:00"), at(0, "07:00"))
    assert result["main"]["asleep"] == 410 and result["main"]["unknown"] == 10
    # 20 unknown minutes break the block: the sleep may have ended there.
    rec = recorder(store, (at(0, "00:00"), at(0, "07:00"), store.INACTIVE),
                   (at(0, "03:00"), at(0, "03:20"), store.UNKNOWN))
    assert span_of(analyze(analysis, rec)) == (at(0, "03:20"), at(0, "07:00"))


def test_unknown_time_is_never_sleep(store, analysis):
    assert analyze(analysis, store.Recorder())["status"] == "no_data"
    everything_unknown = recorder(store, base=store.UNKNOWN)
    assert analyze(analysis, everything_unknown)["status"] == "no_data"


def test_main_sleep_and_naps(store, analysis):
    rec = recorder(store, (at(0, "00:00"), at(0, "07:00"), store.INACTIVE),
                   (at(0, "14:00"), at(0, "15:40"), store.INACTIVE),     # a nap
                   (at(0, "16:00"), at(0, "17:00"), store.INACTIVE),     # too short
                   (at(0, "07:30"), at(0, "09:30"), store.INACTIVE))     # starts before 09:00
    result = analyze(analysis, rec)
    assert span_of(result) == (at(0, "00:00"), at(0, "07:00"))
    assert [(n["start"], n["end"], n["asleep"]) for n in result["naps"]] == [
        (at(0, "14:00"), at(0, "15:40"), 100)]


def test_the_longest_block_is_the_main_sleep(store, analysis):
    rec = recorder(store, (at(-1, "22:00"), at(0, "01:10"), store.INACTIVE),
                   (at(0, "02:00"), at(0, "06:30"), store.INACTIVE))
    assert span_of(analyze(analysis, rec)) == (at(0, "02:00"), at(0, "06:30"))


def test_minimum_sleep_setting(store, analysis):
    rec = recorder(store, (at(0, "02:00"), at(0, "04:30"), store.INACTIVE))
    assert analyze(analysis, rec)["status"] == "no_sleep"
    assert span_of(analyze(analysis, rec, min_sleep=120)) == (at(0, "02:00"), at(0, "04:30"))


def test_daytime_sleep_after_staying_up_all_night(store, analysis, text, lang):
    # The user's example: up all night, asleep from about 10:00 to 14:00.
    rec = recorder(store, (at(0, "10:05"), at(0, "14:10"), store.INACTIVE))
    result = analyze(analysis, rec)
    assert result["status"] == "sleep" and result["daytime"] and result["late"]
    assert span_of(result) == (at(0, "10:05"), at(0, "14:10"))
    assert text.last_night_text(result) == (
        "You stayed up all night, then probably slept from 10:05 to 14:10, about 4 hours 5 minutes.")
    lang("id")
    assert text.last_night_text(result) == (
        "Kamu begadang semalaman, lalu mungkin tidur dari 10:05 sampai 14:10, sekitar 4 jam 5 menit.")


def test_a_sleep_across_midnight_is_one_block(store, analysis):
    rec = recorder(store, (at(-1, "22:00"), at(0, "06:00"), store.INACTIVE))
    result = analyze(analysis, rec)
    assert span_of(result) == (at(-1, "22:00"), at(0, "06:00"))
    assert result["main"]["asleep"] == 480


def test_a_sleep_starting_before_18_00_is_seen_whole(store, analysis):
    rec = recorder(store, (at(-1, "17:30"), at(0, "02:00"), store.INACTIVE))
    assert span_of(analyze(analysis, rec)) == (at(-1, "17:30"), at(0, "02:00"))
    # It belongs to the night that holds its midpoint, not the one before.
    assert analyze(analysis, rec, night=NIGHT - datetime.timedelta(days=1))["status"] == "no_sleep"


def test_an_evening_sleep_belongs_to_the_next_night(store, analysis):
    rec = recorder(store, (at(0, "19:00"), at(1, "03:00"), store.INACTIVE),
                   end=at(2, "06:00"))
    assert analyze(analysis, rec)["status"] == "no_sleep"
    later = analyze(analysis, rec, night=NIGHT + datetime.timedelta(days=1))
    assert span_of(later) == (at(0, "19:00"), at(1, "03:00"))


def test_night_of_and_offsets(analysis):
    assert analysis.night_of(at(0, "17:59")) == NIGHT
    assert analysis.night_of(at(0, "18:00")) == NIGHT + datetime.timedelta(days=1)
    assert analysis.night_of(at(0, "00:00")) == NIGHT
    assert analysis.offset_in_night(at(-1, "18:00"), NIGHT) == 0
    assert analysis.offset_in_night(at(0, "01:15"), NIGHT) == 435
    assert analysis.bedtime_offset(0) == 360 and analysis.bedtime_offset(1320) == 240
    assert analysis.clock_minute(435) == 75


def test_not_enough_data_when_hariku_was_not_running(store, analysis, text, lang):
    rec = recorder(store, (at(-1, "21:00"), at(0, "09:00"), store.UNKNOWN),
                   (at(0, "10:00"), at(0, "13:30"), store.INACTIVE))
    result = analyze(analysis, rec)
    assert result["status"] == "no_data" and result["main"] is None
    assert text.last_night_text(result) == (
        "Not enough data for last night: Hariku wasn't running for much of it.")
    lang("id")
    assert text.last_night_text(result).startswith("Data untuk semalam belum cukup")


def test_no_long_break_from_the_computer(store, analysis, text, lang):
    result = analyze(analysis, recorder(store))
    assert result["status"] == "no_sleep"
    assert text.last_night_text(result) == "Hariku found no long break from the computer last night."


def test_days_away_are_not_one_long_sleep(store, analysis, text, lang):
    rec = recorder(store, base=store.INACTIVE, start=at(-3, "20:00"), end=at(2, "10:00"))
    result = analyze(analysis, rec)
    assert result["status"] == "away" and result["main"] is None
    assert "more than 16 hours" in text.last_night_text(result)
    lang("id")
    assert "lebih dari 16 jam" in text.row_text(result)


def test_a_running_night_waits_until_the_sleep_is_over(store, analysis):
    rec = recorder(store, (at(-2, "23:00"), at(-1, "06:30"), store.INACTIVE),
                   (at(0, "01:00"), at(0, "04:01"), store.INACTIVE))
    nights = analysis.Nights()

    def last(now):
        return analysis.last_night(lambda n: nights.get(rec, n, SETTINGS, (), now), now)

    now = at(0, "04:00", 30)      # still asleep (an automatic briefing could run now)
    running = analyze(analysis, rec, now=now)
    assert running["status"] == "ongoing" and running["in_progress"]
    assert last(now)["night"] == NIGHT - datetime.timedelta(days=1)

    fill(rec, at(0, "04:01"), at(0, "07:40"), store.INACTIVE)
    now = at(0, "08:00")
    done = analyze(analysis, rec, now=now)
    assert done["status"] == "sleep" and span_of(done) == (at(0, "01:00"), at(0, "07:40"))
    assert last(now)["night"] == NIGHT


def test_still_up_at_2_am_reports_the_night_before(store, analysis):
    rec = recorder(store, (at(-2, "23:00"), at(-1, "06:30"), store.INACTIVE))
    nights = analysis.Nights()
    now = at(0, "02:00")
    result = analysis.last_night(lambda n: nights.get(rec, n, SETTINGS, (), now), now)
    assert result["night"] == NIGHT - datetime.timedelta(days=1) and result["status"] == "sleep"


# ------------------------------------------------------------
# Corrections
# ------------------------------------------------------------

def _mark(start, end):
    return (start.timestamp(), end.timestamp())


def test_a_film_marked_as_not_sleep(store, analysis):
    rec = recorder(store, (at(-1, "20:00"), at(-1, "23:30"), store.INACTIVE),    # a film
                   (at(0, "00:30"), at(0, "03:40"), store.INACTIVE))
    assert span_of(analyze(analysis, rec)) == (at(-1, "20:00"), at(-1, "23:30"))
    film = _mark(at(-1, "20:00"), at(-1, "23:30"))
    result = analyze(analysis, rec, corrections=[film])
    assert span_of(result) == (at(0, "00:30"), at(0, "03:40"))
    assert [(b["start"], b["end"]) for b in result["corrected"]] == [(at(-1, "20:00"), at(-1, "23:30"))]
    # Matched by overlap: the block may shift a little as data comes in.
    nearby = analyze(analysis, rec, corrections=[_mark(at(-1, "20:05"), at(-1, "23:20"))])
    assert span_of(nearby) == (at(0, "00:30"), at(0, "03:40"))
    both = analyze(analysis, rec, corrections=[film, _mark(at(0, "00:30"), at(0, "03:40"))])
    assert both["status"] == "corrected" and both["main"] is None


def test_corrections_are_left_out_of_the_averages(store, analysis):
    rec = recorder(store, *[(at(-d, "00:00"), at(-d, "07:00"), store.INACTIVE) for d in range(3)],
                   start=at(-4, "06:00"))
    nights = [NIGHT - datetime.timedelta(days=d) for d in range(3)]
    fill(rec, at(0, "06:00"), at(0, "07:00"), store.ACTIVE)          # last night: 6 hours
    results = {n: analyze(analysis, rec, night=n) for n in nights}
    assert analysis.summary(results, NIGHT)["week_average"] == pytest.approx((420 + 420 + 360) / 3)
    mark = _mark(at(0, "00:00"), at(0, "06:00"))
    results[NIGHT] = analyze(analysis, rec, corrections=[mark])
    stats = analysis.summary(results, NIGHT)
    assert stats["week_nights"] == 2 and stats["week_average"] == 420
    assert analysis.compare_to_week(results[NIGHT], results) is None


# ------------------------------------------------------------
# Averages
# ------------------------------------------------------------

def _week(store):
    """Seven nights: three from 23:00 to 06:00, four from 01:00 to 07:00."""
    spans = []
    for d in range(7):
        if d < 3:
            spans.append((at(-d - 1, "23:00"), at(-d, "06:00"), store.INACTIVE))
        else:
            spans.append((at(-d, "01:00"), at(-d, "07:00"), store.INACTIVE))
    return recorder(store, *spans, start=at(-9, "06:00"))


def test_summary_averages_and_late_nights(store, analysis, text, lang):
    rec = _week(store)
    results = {NIGHT - datetime.timedelta(days=d): analyze(analysis, rec, night=NIGHT - datetime.timedelta(days=d))
               for d in range(7)}
    stats = analysis.summary(results, NIGHT)
    assert stats["week_nights"] == stats["month_nights"] == 7
    assert stats["week_average"] == pytest.approx((3 * 420 + 4 * 360) / 7)
    assert stats["bedtime"] == 60         # the median bedtime: 01:00
    assert stats["wake"] == 420           # 07:00
    assert stats["late_nights"] == 4
    assert text.summary_text(stats) == (
        "Last 7 nights: 6 hours 25 minutes of sleep on average, usually from about 01:00 to 07:00. "
        "You stayed up late 4 nights this week. Last 30 nights: 6 hours 25 minutes on average.")
    lang("id")
    assert text.summary_text(stats) == (
        "7 malam terakhir: rata-rata tidur 6 jam 25 menit, biasanya dari sekitar 01:00 sampai 07:00. "
        "Minggu ini kamu begadang 4 malam. 30 malam terakhir: rata-rata 6 jam 25 menit.")


def test_one_all_nighter_does_not_move_the_usual_bedtime(store, analysis):
    spans = [(at(-d, "00:00"), at(-d, "07:00"), store.INACTIVE) for d in range(1, 7)]
    spans.append((at(0, "10:00"), at(0, "15:00"), store.INACTIVE))     # up all night
    rec = recorder(store, *spans, start=at(-9, "06:00"))
    results = {NIGHT - datetime.timedelta(days=d): analyze(analysis, rec, night=NIGHT - datetime.timedelta(days=d))
               for d in range(7)}
    stats = analysis.summary(results, NIGHT)
    assert (stats["bedtime"], stats["wake"]) == (0, 420)
    assert stats["late_nights"] == 1


def test_summary_without_sleep(analysis, text, lang):
    empty = analysis.summary({}, NIGHT)
    assert empty["week_nights"] == 0 and empty["week_average"] is None
    assert text.summary_text(empty).startswith("No sleep recorded yet.")


def test_compare_with_the_week_before(store, analysis, text, lang):
    rec = _week(store)
    results = {NIGHT - datetime.timedelta(days=d): analyze(analysis, rec, night=NIGHT - datetime.timedelta(days=d))
               for d in range(7)}
    # Last night 23:00-06:00 (420); the 6 nights before average (2*420 + 4*360)/6 = 380.
    diff = analysis.compare_to_week(results[NIGHT], results)
    assert diff == pytest.approx(40)
    assert text.compare_sentence(diff) == "40 minutes more than your 7-day average."
    assert text.compare_sentence(-31) == "30 minutes less than your 7-day average."
    assert text.compare_sentence(6) == "About the same as your 7-day average."
    lang("id")
    assert text.compare_sentence(-31) == "30 menit lebih sedikit dari rata-rata 7 hari terakhirmu."
    only_one = {NIGHT: results[NIGHT], NIGHT - datetime.timedelta(days=1): results[NIGHT - datetime.timedelta(days=1)]}
    assert analysis.compare_to_week(results[NIGHT], only_one) is None


def test_results_are_cached_until_something_changes(store, analysis):
    rec = recorder(store, (at(0, "01:00"), at(0, "07:00"), store.INACTIVE))
    nights = analysis.Nights()
    first = nights.get(rec, NIGHT, SETTINGS, (), None)
    assert nights.get(rec, NIGHT, SETTINGS, (), None) is first
    rec.mark_minute(at(0, "03:00").timestamp(), store.ACTIVE)
    second = nights.get(rec, NIGHT, SETTINGS, (), None)
    assert second is not first and second["main"]["wakeups"] == 1
    assert nights.get(rec, NIGHT, dict(SETTINGS, bedtime=120), (), None) is not second
    marked = nights.get(rec, NIGHT, SETTINGS, (_mark(at(0, "01:00"), at(0, "07:00")),), None)
    assert marked["status"] == "corrected"
    rec.clear()
    assert nights.get(rec, NIGHT, SETTINGS, (), None)["status"] == "no_data"


# ------------------------------------------------------------
# Sentences
# ------------------------------------------------------------

def test_durations(text, lang):
    assert text.duration(385) == "6 hours 25 minutes"
    assert text.duration(387) == "6 hours 25 minutes"
    assert text.duration(60) == "1 hour"
    assert text.duration(62) == "1 hour"
    assert text.duration(121) == "2 hours"
    assert text.duration(2) == "5 minutes"
    assert text.duration(1, exact=True) == "1 minute"
    assert text.duration(65, exact=True) == "1 hour 5 minutes"
    lang("id")
    assert text.duration(385) == "6 jam 25 menit"
    assert text.duration(60) == "1 jam"
    assert text.duration(1, exact=True) == "1 menit"


def test_last_night_sentence_in_both_languages(store, analysis, text, lang):
    rec = recorder(store, (at(0, "01:15"), at(0, "07:40"), store.INACTIVE),
                   (at(0, "14:00"), at(0, "15:40"), store.INACTIVE))
    result = analyze(analysis, rec)
    assert text.last_night_text(result, -30) == (
        "You probably slept from 01:15 to 07:40, about 6 hours 25 minutes. "
        "You stayed up until 01:15. You also napped from 14:00 to 15:40. "
        "30 minutes less than your 7-day average.")
    assert text.row_text(result) == (
        "Wednesday 23 September: You probably slept from 01:15 to 07:40, about 6 hours 25 minutes. "
        "You stayed up until 01:15. You also napped from 14:00 to 15:40.")
    assert text.briefing_sentence(result) == (
        "Last night you slept about 6 hours 25 minutes, from 01:15 to 07:40.")
    lang("id")
    assert text.last_night_text(result, -30) == (
        "Kamu mungkin tidur dari 01:15 sampai 07:40, sekitar 6 jam 25 menit. "
        "Kamu begadang sampai 01:15. Kamu juga tidur siang dari 14:00 sampai 15:40. "
        "30 menit lebih sedikit dari rata-rata 7 hari terakhirmu.")
    assert text.row_text(result).startswith("Rabu 23 September: Kamu mungkin tidur dari 01:15")
    assert text.briefing_sentence(result) == (
        "Semalam kamu tidur sekitar 6 jam 25 menit, dari 01:15 sampai 07:40.")


def test_several_naps(store, analysis, text, lang):
    rec = recorder(store, (at(0, "00:00"), at(0, "07:00"), store.INACTIVE),
                   (at(0, "09:30"), at(0, "11:00"), store.INACTIVE),
                   (at(0, "14:00"), at(0, "15:40"), store.INACTIVE))
    sentences = text.sleep_sentences(analyze(analysis, rec))
    assert sentences[-1] == "You also napped 2 times: 09:30 to 11:00, 14:00 to 15:40."


def test_marked_and_other_statuses_as_text(store, analysis, text, lang):
    rec = recorder(store, (at(0, "01:00"), at(0, "07:00"), store.INACTIVE))
    marked = analyze(analysis, rec, corrections=[_mark(at(0, "01:00"), at(0, "07:00"))])
    assert text.last_night_text(marked) == (
        "You marked last night's sleep, 01:00 to 07:00, as not sleep.")
    assert text.row_text(marked) == "Wednesday 23 September: You marked 01:00 to 07:00 as not sleep."
    assert text.row_text(analyze(analysis, store.Recorder())) == (
        "Wednesday 23 September: Not enough data.")
    lang("id")
    assert text.row_text(marked) == (
        "Rabu 23 September: Kamu menandai 01:00 sampai 07:00 sebagai bukan tidur.")


def test_details_text(store, analysis, text, lang):
    rec = recorder(store, (at(0, "00:30"), at(0, "07:00"), store.INACTIVE),
                   (at(0, "03:00"), at(0, "03:04"), store.ACTIVE),
                   (at(0, "05:00"), at(0, "05:10"), store.UNKNOWN),
                   (at(-1, "18:00"), at(-1, "19:00"), store.UNKNOWN))
    lines = text.details_text(analyze(analysis, rec), 12).split("\n")
    assert lines[0] == "Wednesday 23 September"
    assert lines[1].startswith("You probably slept from 00:30 to 07:00, about 6 hours 15 minutes.")
    assert "You used the computer once during this sleep, for 4 minutes." in lines
    assert "No data for 10 minutes inside this sleep." in lines
    assert "Stayed up late: yes, until 00:30. Your bedtime is 00:00." in lines
    assert "10 minutes more than your 7-day average." in lines
    assert "Hariku has data for 22 hours 50 minutes of this night's 24 hours." in lines
    assert lines[-1] == "This is an estimate from computer use, not a medical measurement."


def test_nudge_text(text, lang):
    assert text.nudge_text(at(0, "00:30"), "Budi") == "It's 00:30, Budi. Don't forget to rest."
    assert text.nudge_text(at(0, "00:30"), "  ") == "It's 00:30. Don't forget to rest."
    lang("id")
    assert text.nudge_text(at(0, "00:30"), "Budi") == "Sudah pukul 00:30, Budi. Jangan lupa istirahat."
    assert text.nudge_text(at(0, "00:30")) == "Sudah pukul 00:30. Jangan lupa istirahat."


def test_locales_have_the_same_keys_including_computed_ones():
    keys = {}
    for code in ("en", "id"):
        with open(os.path.join(EXT_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            data = json.load(f)
        keys[code] = set(data["messages"])
        assert data["manifest"]["language_code"] == code
    assert keys["en"] == keys["id"]
    # Keys chosen at run time, which the manifest test can't see.
    for key in ("sleep_day", "sleep_night", "briefing", "briefing_day", "compare_more",
                "compare_less", "nudge", "nudge_name", "summary_late_many"):
        assert key in keys["en"]


def test_manifest():
    with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["id"] == "sleep_tracker" and manifest["name"] == "Sleep Pattern"
    assert manifest["version"] == "1.0" and manifest["minimum_core_version"] == "2.7"


# ------------------------------------------------------------
# The extension (main.py) with a fake clock
# ------------------------------------------------------------

class FakeClock:
    """Stands in for WindowsClock: the test sets the time and the idle time."""

    def __init__(self, system, when):
        self.system = system
        self.when = when
        self.boot = when - datetime.timedelta(hours=2)
        self.idle = 5.0
        self.asleep = 0.0
        self.reads = 0

    def read(self):
        self.reads += 1
        return sample(self.system, self.when, idle=self.idle, boot=self.boot, asleep=self.asleep)


@pytest.fixture
def smain(monkeypatch, tmp_data_dir, store, analysis, system, text, lang):
    """Sleep Pattern's main.py with a fake clock, speech and sounds captured."""
    import core.hotkeys
    import core.preferences
    import core.sounds

    clock = FakeClock(system, at(-1, "21:00"))

    def no_real_api(*_args, **_kwargs):
        raise AssertionError("the real Windows API must not be used in logic tests")

    def no_real_sound(*_args, **_kwargs):
        raise AssertionError("no real sounds in tests")

    monkeypatch.setattr(system, "_load_dlls", no_real_api)
    monkeypatch.setattr(system, "WindowsClock", lambda *a, **k: clock)
    monkeypatch.setattr(core.sounds, "play_internal_sound", no_real_sound)
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *args, **kwargs: panels.append(args))

    spec = importlib.util.spec_from_file_location("sleep_tracker_main_under_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken, sounds = [], []
    monkeypatch.setattr(module, "speak", lambda msg, interrupt=False: spoken.append(msg))
    monkeypatch.setattr(module, "_play_sound", sounds.append)
    monkeypatch.setattr(module, "_now", lambda: clock.when)
    module.clock, module.spoken, module.sounds = clock, spoken, sounds
    module.actions, module.panels = actions, panels
    yield module
    module._active = False


def use(smain, until):
    """Tick once a minute until `until`, using the computer all along."""
    while smain.clock.when < until:
        smain.clock.when += MINUTE
        smain.clock.idle = 5.0
        smain._on_minute_tick(smain.clock.when)


def rest(smain, until):
    """Tick once a minute until `until` without touching the computer."""
    started = smain.clock.when
    while smain.clock.when < until:
        smain.clock.when += MINUTE
        smain.clock.idle = (smain.clock.when - started).total_seconds() + 5
        smain._on_minute_tick(smain.clock.when)


def test_register_and_teardown(smain, fresh_event_bus):
    import core.api
    smain.register(fresh_event_bus)
    for event_name, handler in smain._SUBSCRIPTIONS:
        assert handler in fresh_event_bus._listeners[event_name]
    by_name = {args[1]: (args, kwargs) for args, kwargs in smain.actions}
    assert set(by_name) == {"last_night", "history"}
    last_args, last_kwargs = by_name["last_night"]
    assert last_args[0] == "Sleep Pattern" and last_args[3] == ord("Z") and last_args[4] is False
    assert last_kwargs == {}
    history_args, history_kwargs = by_name["history"]
    assert history_args[3] == ord("Z") and history_args[4] is False
    assert history_kwargs == {"default_shift": True}
    assert len(smain.panels) == 1 and smain.panels[0][0] == "Sleep Pattern"
    assert smain.clock.reads == 1      # the gap since Hariku last ran is filled in at once
    import core.personal
    assert core.personal.is_placeholder_registered("sleep")         # %sleep% (core 2.7)

    smain.clock.when += 5 * MINUTE
    smain.teardown()
    for event_name, handler in smain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    saved = core.api.load_data(smain.ACTIVITY_KEY)
    assert saved["last"]["final"] is True
    assert saved["last"]["wall"] == smain.clock.when.timestamp()     # flushed on the way out
    assert not core.personal.is_placeholder_registered("sleep")


def test_minute_tick_buffers_and_saves_every_10_minutes(smain, fresh_event_bus, monkeypatch):
    import core.api
    smain.register(fresh_event_bus)
    saves = []
    real_save = core.api.save_data
    monkeypatch.setattr(core.api, "save_data",
                        lambda name, data: saves.append(name) or real_save(name, data))

    def no_reading(*_args):
        raise AssertionError("the minute tick must not read from disk")

    monkeypatch.setattr(core.api, "load_data", no_reading)
    use(smain, at(-1, "21:09"))
    assert saves == [] and smain.clock.reads == 10
    assert smain._recorder.dirty
    use(smain, at(-1, "21:10"))
    assert saves == [smain.ACTIVITY_KEY] and not smain._recorder.dirty
    use(smain, at(-1, "21:19"))
    assert saves == [smain.ACTIVITY_KEY]
    assert states(smain._recorder, at(-1, "21:00"), at(-1, "21:18")) == "a" * 18


def test_a_night_with_the_computer_off(smain, fresh_event_bus, text):
    import core.api
    clock = smain.clock
    clock.when, clock.boot = at(-1, "22:30"), at(-1, "08:00")
    smain.register(fresh_event_bus)
    use(smain, at(-1, "23:50"))
    smain.teardown()                        # Hariku closes as Windows shuts down
    assert core.api.load_data(smain.ACTIVITY_KEY)["last"]["final"] is True

    clock.when, clock.boot, clock.idle = at(0, "07:40", 30), at(0, "07:39"), 5.0
    smain.register(fresh_event_bus)
    use(smain, at(0, "09:00"))
    smain.speak_last_night()
    assert smain.spoken[-1] == "You probably slept from 23:50 to 07:40, about 7 hours 50 minutes."

    lines = []
    smain._on_briefing_collect(lines)
    assert lines == ["Last night you slept about 7 hours 50 minutes, from 23:50 to 07:40."]
    assert smain.placeholder_text() == "about 7 hours 50 minutes"        # %sleep%
    clock.when = at(0, "20:00")             # too long ago for the briefing
    smain._on_minute_tick(clock.when)
    lines = []
    smain._on_briefing_collect(lines)
    assert lines == []
    assert smain.placeholder_text() == ""


def test_briefing_says_nothing_without_a_detected_sleep(smain, fresh_event_bus, store):
    smain.clock.when = at(0, "08:00")
    smain.register(fresh_event_bus)
    fill(smain._recorder, at(-2, "12:00"), at(0, "08:00"), store.ACTIVE)   # up all night
    lines = []
    smain._on_briefing_collect(lines)
    assert lines == []
    smain.apply_settings(dict(smain.get_settings(), enabled=False))
    smain._on_briefing_collect(lines)
    assert lines == []


def test_lid_closed_overnight(smain, fresh_event_bus):
    clock = smain.clock
    clock.when = at(-1, "23:00")
    smain.register(fresh_event_bus)
    use(smain, at(0, "01:00"))
    clock.when = at(0, "07:40", 30)         # the timer fires once the lid opens
    clock.asleep = (at(0, "07:40") - at(0, "01:00", 30)).total_seconds()
    clock.idle = 20.0
    smain._on_minute_tick(clock.when)
    use(smain, at(0, "08:30"))
    smain.speak_last_night()
    assert smain.spoken[-1].startswith("You probably slept from 01:00 to 07:40")
    assert "You stayed up until 01:00." in smain.spoken[-1]


def test_late_night_reminder_once_a_night(smain, fresh_event_bus, monkeypatch):
    import core.personal
    monkeypatch.setattr(core.personal, "get_nickname", lambda: "Budi")
    smain.clock.when = at(-1, "23:58")
    smain.register(fresh_event_bus)
    smain.apply_settings(dict(smain.get_settings(), nudge=True))
    use(smain, at(0, "00:29"))
    assert smain.spoken == []
    use(smain, at(0, "00:30"))
    assert smain.spoken == ["It's 00:30, Budi. Don't forget to rest."]
    assert smain.sounds == ["info.wav"]
    use(smain, at(0, "01:30"))
    assert len(smain.spoken) == 1

    smain.teardown()                         # a restart doesn't repeat it
    smain.register(fresh_event_bus)
    use(smain, at(0, "01:40"))
    assert len(smain.spoken) == 1

    # The next night: away from the computer at 00:30, back at 00:45.
    smain.clock.when = at(0, "23:59")
    smain._on_minute_tick(smain.clock.when)
    rest(smain, at(1, "00:44"))
    assert len(smain.spoken) == 1
    use(smain, at(1, "00:45"))
    assert smain.spoken[-1] == "It's 00:45, Budi. Don't forget to rest."
    assert len(smain.spoken) == 2


def test_reminder_without_a_nickname_or_sound(smain, fresh_event_bus, monkeypatch):
    import core
    monkeypatch.delattr(core, "personal")     # a core without the profile
    smain.clock.when = at(-1, "22:00")
    smain.register(fresh_event_bus)
    smain.apply_settings(dict(smain.get_settings(), nudge=True, nudge_sound=False, bedtime=1350))
    use(smain, at(-1, "23:59"))
    assert smain.spoken == ["It's 23:00. Don't forget to rest."]    # bedtime 22:30 + 30 minutes
    assert smain.sounds == []


def test_reminder_is_off_by_default(smain, fresh_event_bus):
    smain.clock.when = at(0, "00:00")
    smain.register(fresh_event_bus)
    use(smain, at(0, "01:00"))
    assert smain.spoken == [] and smain.sounds == []


def test_tracking_off(smain, fresh_event_bus):
    smain.register(fresh_event_bus)
    use(smain, at(-1, "22:00"))
    smain.apply_settings(dict(smain.get_settings(), enabled=False))
    before = {d: bytes(m) for d, m in smain._recorder.days.items()}
    use(smain, at(0, "08:00"))
    assert {d: bytes(m) for d, m in smain._recorder.days.items()} == before
    smain.speak_last_night()
    assert smain.spoken[-1] == "Sleep tracking is off. Turn it on in Preferences, Sleep Pattern."
    # Back on: the time it was off stays unknown.
    smain.apply_settings(dict(smain.get_settings(), enabled=True))
    use(smain, at(0, "08:10"))
    assert set(states(smain._recorder, at(-1, "22:01"), at(0, "07:59"))) == {"u"}


def test_history_actions_mark_undo_and_clear(smain, fresh_event_bus, store, analysis):
    import core.api
    smain.clock.when = at(0, "12:00")
    smain.register(fresh_event_bus)
    smain._recorder = _week(store)
    smain._recorder.last = None
    actions = smain.HistoryActions
    rows = actions.rows()
    assert [r[0] for r in rows][:3] == [NIGHT, NIGHT - datetime.timedelta(days=1),
                                        NIGHT - datetime.timedelta(days=2)]
    assert rows[0][1].startswith("Wednesday 23 September: You probably slept from 23:00 to 06:00")
    assert rows[0][2] == "mark"
    assert actions.summary().startswith("Last 7 nights: 6 hours 25 minutes of sleep on average")

    assert actions.mark(NIGHT)
    rows = actions.rows()
    assert rows[0][2] == "undo" and "You marked 23:00 to 06:00 as not sleep." in rows[0][1]
    saved = core.api.load_data(smain.DATA_KEY)["corrections"]
    assert saved == [{"night": "2026-09-23", "start": at(-1, "23:00").timestamp(),
                      "end": at(0, "06:00").timestamp()}]
    assert actions.summary().startswith("Last 7 nights: 6 hours 20 minutes of sleep on average")
    assert "Marked as not sleep: 23:00 to 06:00." in actions.details(NIGHT)
    assert not actions.mark(NIGHT)          # nothing left to mark there

    assert actions.undo(NIGHT)
    assert actions.rows()[0][2] == "mark" and core.api.load_data(smain.DATA_KEY)["corrections"] == []
    assert not actions.undo(NIGHT)

    actions.clear()
    assert actions.rows() == [] and smain._corrections == []
    assert core.api.load_data(smain.ACTIVITY_KEY)["days"] == {}
    assert actions.summary().startswith("No sleep recorded yet.")


def test_history_skips_the_running_night_until_its_sleep_is_over(smain, fresh_event_bus, store):
    smain.clock.when = at(0, "21:00")        # the next night has just begun
    smain.register(fresh_event_bus)
    smain._recorder = _week(store)
    fill(smain._recorder, at(0, "06:00"), at(0, "21:00"), store.ACTIVE)
    nights = [r[0] for r in smain.HistoryActions.rows()]
    assert nights[0] == NIGHT


def test_saving_prunes_old_days(smain, fresh_event_bus, store):
    import core.api
    smain.clock.when = at(0, "12:00")
    smain.register(fresh_event_bus)
    fill(smain._recorder, at(-100, "10:00"), at(-100, "11:00"), store.ACTIVE)
    smain._save_activity()
    days = core.api.load_data(smain.ACTIVITY_KEY)["days"]
    assert (NIGHT - datetime.timedelta(days=100)).isoformat() not in days
    assert NIGHT.isoformat() in days


def test_corrupt_files_do_not_stop_the_extension(smain, fresh_event_bus):
    import core.api
    for key in (smain.DATA_KEY, smain.ACTIVITY_KEY):
        with open(core.api.get_data_path(key), "w", encoding="utf-8") as f:
            f.write("{not json")
    smain.register(fresh_event_bus)
    assert smain.get_settings() == smain.store.DEFAULT_SETTINGS
    smain.speak_last_night()
    assert smain.spoken[-1].startswith("Not enough data for last night")
