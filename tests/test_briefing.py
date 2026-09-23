# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Morning Briefing extension: greeting, date, agenda, the
# "on_briefing_collect" contract, the once-a-day automatic briefing, and the
# Weather extension's contribution.

import datetime
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEFING_DIR = os.path.join(ROOT, "extensions", "briefing")
WEATHER_DIR = os.path.join(ROOT, "extensions", "weather")

MORNING = datetime.datetime(2026, 9, 23, 7, 30)  # a Wednesday


def _load_main(name, ext_dir):
    if ext_dir not in sys.path:
        sys.path.insert(0, ext_dir)
    spec = importlib.util.spec_from_file_location(name, os.path.join(ext_dir, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def core_mod():
    if BRIEFING_DIR not in sys.path:
        sys.path.insert(0, BRIEFING_DIR)
    import briefing_core
    return briefing_core


@pytest.fixture
def lang(monkeypatch, core_mod):
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


@pytest.fixture
def bmain(monkeypatch, tmp_data_dir, core_mod, fresh_event_bus):
    module = _load_main("briefing_main_under_test", BRIEFING_DIR)
    spoken = []
    monkeypatch.setattr(module, "speak", lambda msg, interrupt=False: spoken.append(msg))
    module._bus = fresh_event_bus
    module._active = True
    module.spoken = spoken
    yield module
    module._active = False


def _reminders(monkeypatch, items):
    import core.reminders
    asked = []

    def fake(date_str):
        asked.append(date_str)
        return [dict(r) for r in items]

    monkeypatch.setattr(core.reminders, "get_reminders_for_date", fake)
    return asked


def test_locales_have_the_same_keys():
    keys = {}
    for code in ("en", "id"):
        with open(os.path.join(BRIEFING_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            keys[code] = set(json.load(f)["messages"])
    assert keys["en"] == keys["id"]


# ------------------------------------------------------------
# Greeting
# ------------------------------------------------------------

@pytest.mark.parametrize("hour, key", [
    (0, "greet_evening"), (3, "greet_evening"), (4, "greet_morning"), (10, "greet_morning"),
    (11, "greet_midday"), (14, "greet_midday"), (15, "greet_afternoon"),
    (17, "greet_afternoon"), (18, "greet_evening"), (23, "greet_evening"),
])
def test_greeting_by_hour(core_mod, hour, key):
    assert core_mod.greeting_key(hour) == key


def test_greeting_text(core_mod, lang):
    assert [core_mod._(core_mod.greeting_key(h)) for h in (7, 12, 16, 20)] == [
        "Good morning.", "Good day.", "Good afternoon.", "Good evening."]
    lang("id")
    assert [core_mod._(core_mod.greeting_key(h)) for h in (7, 12, 16, 20)] == [
        "Selamat pagi.", "Selamat siang.", "Selamat sore.", "Selamat malam."]


# ------------------------------------------------------------
# Agenda
# ------------------------------------------------------------

def test_agenda_empty_and_all_done(core_mod, lang):
    assert core_mod.agenda_sentences([]) == ["You have no reminders today."]
    assert core_mod.agenda_sentences(None) == ["You have no reminders today."]
    done = [{"title": "Gym", "time": "06:00", "is_done": True}]
    assert core_mod.agenda_sentences(done) == ["All of today's reminders are done."]


def test_agenda_lists_pending_reminders_by_time(core_mod, lang):
    reminders = [
        {"title": "Lunch with  Budi", "time": "12:30", "is_done": False},
        {"title": "Gym", "time": "06:00", "is_done": True},
        {"title": "Stand-up meeting", "time": "09:00"},
        {"title": "Call mom!", "time": ""},
        "not a reminder",
    ]
    assert core_mod.agenda_sentences(reminders) == [
        "You have 3 reminders today.",
        "09:00, Stand-up meeting.",
        "12:30, Lunch with Budi.",
        "Call mom!",
    ]
    lang("id")
    assert core_mod.agenda_sentences(reminders[:1]) == ["Ada 1 pengingat hari ini.", "12:30, Lunch with Budi."]


def test_long_agenda_is_capped(core_mod, lang):
    reminders = [{"title": f"Task {i}", "time": f"{i:02d}:00"} for i in range(14)]
    sentences = core_mod.agenda_sentences(reminders)
    assert sentences[0] == "You have 14 reminders today."
    assert len(sentences) == 1 + core_mod.MAX_AGENDA_ITEMS + 1
    assert sentences[-1] == "And 4 more."


def test_untitled_reminder(core_mod, lang):
    assert core_mod.agenda_sentences([{"title": "  ", "time": "08:00"}])[1] == "08:00, Untitled reminder."


# ------------------------------------------------------------
# The collect-event contract
# ------------------------------------------------------------

def test_collect_event_contract(core_mod, fresh_event_bus):
    received = []

    def first(lines):
        received.append(lines)
        lines.append("First extension says hi.")

    def junk(lines):
        lines.extend([42, None, "   ", "  Two   spaces  "])

    def broken(lines):
        raise RuntimeError("a broken extension")

    def last(lines):
        lines.append("Last one.")

    for handler in (first, junk, broken, last):
        fresh_event_bus.subscribe(core_mod.COLLECT_EVENT, handler)

    assert core_mod.COLLECT_EVENT == "on_briefing_collect"
    assert core_mod.collect_contributions(fresh_event_bus) == [
        "First extension says hi.", "Two spaces", "Last one."]
    core_mod.collect_contributions(fresh_event_bus)
    assert received[0] is not received[1]  # a new list every time


def test_no_subscribers_means_no_contributions(core_mod, fresh_event_bus):
    assert core_mod.collect_contributions(fresh_event_bus) == []


def test_build_briefing_order_and_date_format(core_mod, lang, fresh_event_bus):
    fresh_event_bus.subscribe("on_briefing_collect", lambda lines: lines.append("Extra news."))
    reminders = [{"title": "Stand-up", "time": "09:00"}]
    assert core_mod.build_briefing(MORNING, reminders, "%d/%m/%Y", fresh_event_bus) == [
        "Good morning.", "Today is 23/09/2026.", "You have 1 reminder today.",
        "09:00, Stand-up.", "Extra news."]
    assert core_mod.build_briefing(MORNING, [], None, fresh_event_bus)[1] == (
        "Today is Wednesday, 23 September 2026.")
    lang("id")
    assert core_mod.build_briefing(MORNING, [], "%A, %d %B %Y", fresh_event_bus)[:3] == [
        "Selamat pagi.", "Hari ini Rabu, 23 September 2026.", "Tidak ada pengingat hari ini."]


# ------------------------------------------------------------
# Automatic briefing
# ------------------------------------------------------------

@pytest.mark.parametrize("config, expected", [
    ({}, False),
    (None, False),
    ("garbage", False),
    ({"auto_first_start": False}, False),
    ({"auto_first_start": True}, True),
    ({"auto_first_start": True, "last_auto_date": "2026-09-22"}, True),
    ({"auto_first_start": True, "last_auto_date": "2026-09-23"}, False),
])
def test_should_auto_play(core_mod, config, expected):
    assert core_mod.should_auto_play(config, "2026-09-23") is expected


def test_auto_briefing_plays_once_a_day(bmain, lang, monkeypatch):
    import core.api
    _reminders(monkeypatch, [])
    scheduled = []

    class FakeCallLater:
        def __init__(self, ms, fn, *args):
            scheduled.append(fn)

        def Stop(self):
            pass

    monkeypatch.setattr(bmain.wx, "CallLater", FakeCallLater)

    bmain._on_app_startup()
    assert scheduled == []                      # off by default

    core.api.save_data(bmain.DATA_KEY, {"auto_first_start": True})
    bmain._on_app_startup()
    assert len(scheduled) == 1
    scheduled[0]()
    assert len(bmain.spoken) == 1
    assert core.api.load_data(bmain.DATA_KEY)["last_auto_date"] == datetime.date.today().isoformat()

    bmain._on_app_startup()                     # second start the same day
    assert len(scheduled) == 1 and len(bmain.spoken) == 1


def test_teardown_cancels_a_pending_auto_briefing(bmain, monkeypatch):
    import core.api
    stopped = []

    class FakeCallLater:
        def __init__(self, ms, fn, *args):
            self.fn = fn

        def Stop(self):
            stopped.append(True)

    monkeypatch.setattr(bmain.wx, "CallLater", FakeCallLater)
    core.api.save_data(bmain.DATA_KEY, {"auto_first_start": True})
    bmain._on_app_startup()
    timer = bmain._auto_timer
    bmain.teardown()
    assert stopped == [True] and bmain._auto_timer is None
    timer.fn()                                  # a late tick does nothing
    assert bmain.spoken == []


# ------------------------------------------------------------
# The hotkey action
# ------------------------------------------------------------

def test_play_briefing_speaks_everything_once(bmain, lang, monkeypatch):
    import core.api
    asked = _reminders(monkeypatch, [{"title": "Dentist", "time": "10:15", "is_done": False}])
    core.api.save_data("Core", {"date_format": "%d-%m-%Y"})
    bmain._bus.subscribe("on_briefing_collect", lambda lines: lines.append("Weather is fine."))

    bmain.play_briefing()
    assert asked == [datetime.date.today().isoformat()]
    assert len(bmain.spoken) == 1
    text = bmain.spoken[0]
    assert f"Today is {datetime.date.today().strftime('%d-%m-%Y')}." in text
    assert text.endswith("You have 1 reminder today. 10:15, Dentist. Weather is fine.")


def test_briefing_survives_a_reminder_error(bmain, lang, monkeypatch):
    import core.reminders

    def broken(date_str):
        raise OSError("disk unplugged")

    monkeypatch.setattr(core.reminders, "get_reminders_for_date", broken)
    bmain.play_briefing()
    assert "You have no reminders today." in bmain.spoken[0]


def test_weather_contributes_to_the_briefing(bmain, lang, monkeypatch):
    weather = _load_main("weather_main_for_briefing", WEATHER_DIR)
    import weather_api
    _reminders(monkeypatch, [])
    location = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
                "latitude": -6.2, "longitude": 106.8, "timezone": "Asia/Jakarta"}
    forecast = {"timezone": "Asia/Jakarta", "utc_offset_seconds": 25200, "daily": [],
                "current": {"time": "", "temperature": 29.6, "feels_like": None,
                            "humidity": None, "wind_speed": None, "code": 2}}
    weather._settings = {"location": location, "units": "metric"}
    weather._cache = weather_api.make_cache(location, forecast)
    bmain._bus.subscribe("on_briefing_collect", weather._on_briefing_collect)

    bmain.play_briefing()
    assert bmain.spoken[0].endswith(
        "You have no reminders today. Weather in Jakarta: Partly cloudy, 30 degrees.")


def test_register_and_teardown(bmain, fresh_event_bus, monkeypatch):
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *args, **kwargs: panels.append(args))
    bmain.register(fresh_event_bus)
    assert bmain._on_app_startup in fresh_event_bus._listeners["on_app_startup"]
    (args, kwargs), = actions
    assert args[:2] == ("Morning Briefing", "play_briefing")
    assert args[3] == ord("B") and args[4] is False and kwargs == {}
    assert len(panels) == 1
    bmain.teardown()
    assert bmain._on_app_startup not in fresh_event_bus._listeners["on_app_startup"]
