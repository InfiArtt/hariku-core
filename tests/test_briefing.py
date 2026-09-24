# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Morning Briefing extension: greeting, date, agenda, the
# "on_briefing_collect" contract, the once-a-day automatic briefing, the evening
# summary and its "on_evening_collect" contract, and the Weather extension's
# contributions.

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


@pytest.mark.parametrize("hour, en, id_", [
    (7, "Good morning, Bro.", "Selamat pagi, Bro."),
    (12, "Good day, Bro.", "Selamat siang, Bro."),
    (16, "Good afternoon, Bro.", "Selamat sore, Bro."),
    (21, "Good evening, Bro.", "Selamat malam, Bro."),
])
def test_greeting_with_a_nickname(core_mod, lang, hour, en, id_):
    assert core_mod.greeting(hour, "Bro") == en
    assert core_mod.greeting(hour, "  Bro  ") == en
    lang("id")
    assert core_mod.greeting(hour, "Bro") == id_


def test_greeting_without_a_nickname(core_mod, lang):
    assert core_mod.greeting(7) == "Good morning."
    assert core_mod.greeting(7, "") == "Good morning."
    assert core_mod.greeting(7, "   ") == "Good morning."
    assert core_mod.greeting(7, None) == "Good morning."
    lang("id")
    assert core_mod.greeting(20, "") == "Selamat malam."


def test_greeting_nickname_keeps_its_own_punctuation(core_mod, lang):
    assert core_mod.greeting(7, "Bro!") == "Good morning, Bro!"
    assert core_mod.greeting(7, "{name}") == "Good morning, {name}."


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


def test_build_briefing_with_a_nickname(core_mod, lang, fresh_event_bus):
    assert core_mod.build_briefing(MORNING, [], None, fresh_event_bus, nickname="Bro")[0] ==         "Good morning, Bro."
    lang("id")
    assert core_mod.build_briefing(MORNING, [], None, fresh_event_bus, nickname="Bro")[0] ==         "Selamat pagi, Bro."


def test_agenda_titles_are_expanded(core_mod, lang, fresh_event_bus):
    reminders = [{"title": "Call %myname%", "time": "09:00"},
                 {"title": "%empty%", "time": "10:00"}]
    expand = {"Call %myname%": "Call Rafli", "%empty%": "  "}.get
    assert core_mod.agenda_sentences(reminders, expand) == [
        "You have 2 reminders today.", "09:00, Call Rafli.", "10:00, Untitled reminder."]
    # Without an expander, titles are read as they are.
    assert core_mod.agenda_sentences(reminders[:1])[1] == "09:00, Call %myname%."
    assert core_mod.build_briefing(MORNING, reminders[:1], None, fresh_event_bus,
                                   expand=expand)[3] == "09:00, Call Rafli."


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


def test_play_briefing_uses_the_profile(bmain, lang, monkeypatch):
    import core.api
    _reminders(monkeypatch, [{"title": "Meet %mynickname% at %kantor% (100% sure)",
                              "time": "10:15", "is_done": False}])
    core.api.save_data("Core", {"user_name": "Rafli", "user_nickname": "Bro",
                                "user_fields": [{"key": "kantor", "value": "Jl. Sudirman 1"}]})
    bmain.play_briefing()
    text = bmain.spoken[0]
    assert text.startswith(("Good morning, Bro.", "Good day, Bro.", "Good afternoon, Bro.",
                            "Good evening, Bro.")), text
    assert "10:15, Meet Bro at Jl. Sudirman 1 (100% sure)." in text


def test_play_briefing_greets_by_name_without_a_nickname(bmain, lang, monkeypatch):
    import core.api
    _reminders(monkeypatch, [])
    core.api.save_data("Core", {"user_name": "Rafli"})
    bmain.play_briefing()
    assert ", Rafli. Today is " in bmain.spoken[0]


def test_play_briefing_without_a_name(bmain, lang, monkeypatch):
    import core.api
    _reminders(monkeypatch, [])
    core.api.save_data("Core", {"user_name": "User"})   # the old wizard's blank name
    bmain.play_briefing()
    assert bmain.spoken[0].split(" Today is ")[0] in (
        "Good morning.", "Good day.", "Good afternoon.", "Good evening.")


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
    assert bmain._on_minute_tick in fresh_event_bus._listeners["on_minute_tick"]
    (args, kwargs), (evening_args, evening_kwargs) = actions
    assert args[:2] == ("Morning Briefing", "play_briefing")
    assert args[3] == ord("B") and args[4] is False and kwargs == {}
    # Shift+B: the evening summary.
    assert evening_args[:2] == ("Morning Briefing", "evening_summary")
    assert evening_args[3] == ord("B") and evening_args[4] is False
    assert evening_args[5] == bmain.play_evening_summary
    assert evening_kwargs == {"default_shift": True}
    assert len(panels) == 1
    bmain.teardown()
    assert bmain._on_app_startup not in fresh_event_bus._listeners["on_app_startup"]
    assert bmain._on_minute_tick not in fresh_event_bus._listeners["on_minute_tick"]


# ------------------------------------------------------------
# Birthday and the greeting (Briefing 1.1)
# ------------------------------------------------------------

def test_greeting_sentences_on_the_birthday(core_mod, lang):
    assert core_mod.greeting_sentences(7, "Bro", birthday=True) == [
        "Good morning, Bro.", "Happy birthday!"]
    assert core_mod.greeting_sentences(7, "", birthday=False) == ["Good morning."]
    lang("id")
    assert core_mod.greeting_sentences(20, "Bro", birthday=True) == [
        "Selamat malam, Bro.", "Selamat ulang tahun!"]


def test_build_briefing_birthday_and_without_greeting(core_mod, lang, fresh_event_bus):
    sentences = core_mod.build_briefing(MORNING, [], None, fresh_event_bus, nickname="Bro",
                                        birthday=True)
    assert sentences[:3] == ["Good morning, Bro.", "Happy birthday!",
                             "Today is Wednesday, 23 September 2026."]
    sentences = core_mod.build_briefing(MORNING, [], None, fresh_event_bus, nickname="Bro",
                                        birthday=True, greet=False)
    assert sentences[0] == "Today is Wednesday, 23 September 2026."


# ------------------------------------------------------------
# Evening summary
# ------------------------------------------------------------

EVENING = datetime.datetime(2026, 9, 23, 20, 15)


def test_evening_today(core_mod, lang):
    assert core_mod.evening_today_sentences([]) == ["You had no reminders today."]
    done = [{"title": "Gym", "time": "06:00", "is_done": True}]
    assert core_mod.evening_today_sentences(done) == ["You finished all of today's reminders."]
    reminders = [
        {"title": "Pay %kantor% rent", "time": "17:00", "is_done": False},
        {"title": "Gym", "time": "06:00", "is_done": True},
        {"title": "Call %myname%", "time": "15:00"},
        "not a reminder",
    ]
    expand = {"Pay %kantor% rent": "Pay office rent", "Call %myname%": "Call Rafli"}.get
    assert core_mod.evening_today_sentences(reminders, expand) == [
        "You finished 1 of 3 reminders today.", "Not done yet:",
        "15:00, Call Rafli.", "17:00, Pay office rent."]
    lang("id")
    assert core_mod.evening_today_sentences(reminders, expand)[:2] == [
        "1 dari 3 pengingat hari ini sudah selesai.", "Belum selesai:"]
    assert core_mod.evening_today_sentences(done) == ["Semua pengingat hari ini sudah selesai."]


def test_evening_today_is_capped(core_mod, lang):
    reminders = [{"title": f"Task {i}", "time": f"{i:02d}:00"} for i in range(13)]
    sentences = core_mod.evening_today_sentences(reminders)
    assert sentences[0] == "You finished 0 of 13 reminders today."
    assert len(sentences) == 2 + core_mod.MAX_AGENDA_ITEMS + 1
    assert sentences[-1] == "And 3 more."


def test_evening_tomorrow(core_mod, lang):
    assert core_mod.evening_tomorrow_sentences([]) == ["You have no reminders tomorrow."]
    one = [{"title": "Dentist %myname%", "time": "09:00"}]
    assert core_mod.evening_tomorrow_sentences(one, {"Dentist %myname%": "Dentist"}.get) == [
        "Tomorrow you have 1 reminder: 09:00, Dentist."]
    many = [{"title": "Lunch", "time": "12:00"}, {"title": "No time"},
            {"title": "Early", "time": "07:30"}, {"title": "Old", "time": "06:00", "is_done": True}]
    assert core_mod.evening_tomorrow_sentences(many) == [
        "Tomorrow you have 3 reminders.", "The first one: 07:30, Early."]
    assert core_mod.evening_tomorrow_sentences([{"title": "Call mom!"}]) == [
        "Tomorrow you have 1 reminder: Call mom!"]
    lang("id")
    assert core_mod.evening_tomorrow_sentences(many) == [
        "Besok ada 3 pengingat.", "Yang pertama: 07:30, Early."]
    assert core_mod.evening_tomorrow_sentences([]) == ["Besok tidak ada pengingat."]


def test_build_evening_order_and_its_own_event(core_mod, lang, fresh_event_bus):
    fresh_event_bus.subscribe("on_briefing_collect", lambda lines: lines.append("Morning only."))
    fresh_event_bus.subscribe("on_evening_collect", lambda lines: lines.append("Tomorrow: fine."))
    fresh_event_bus.subscribe("on_evening_collect", lambda lines: lines.extend([None, "  "]))
    today = [{"title": "Call", "time": "15:00"}]
    tomorrow = [{"title": "Dentist", "time": "09:00"}]
    assert core_mod.EVENING_COLLECT_EVENT == "on_evening_collect"
    assert core_mod.build_evening(EVENING, today, tomorrow, fresh_event_bus, nickname="Bro") == [
        "Good evening, Bro.", "You finished 0 of 1 reminders today.", "Not done yet:",
        "15:00, Call.", "Tomorrow you have 1 reminder: 09:00, Dentist.", "Tomorrow: fine."]
    assert core_mod.build_evening(EVENING, [], [], fresh_event_bus, birthday=True)[:2] == [
        "Good evening.", "Happy birthday!"]


def test_evening_time_setting(core_mod):
    assert core_mod.EVENING_TIMES[0] == "18:00" and core_mod.EVENING_TIMES[-1] == "23:00"
    assert len(core_mod.EVENING_TIMES) == 11
    assert core_mod.evening_time({}) == "20:00"
    assert core_mod.evening_time({"evening_time": "21:30"}) == "21:30"
    assert core_mod.evening_time({"evening_time": "03:00"}) == "20:00"
    assert core_mod.evening_time(None) == "20:00"


@pytest.mark.parametrize("config, hhmm, expected", [
    ({}, "21:00", False),
    ({"evening_auto": False, "evening_time": "20:00"}, "21:00", False),
    ({"evening_auto": True}, "19:59", False),
    ({"evening_auto": True}, "20:00", True),
    ({"evening_auto": True}, "23:59", True),
    ({"evening_auto": True, "evening_time": "22:30"}, "22:00", False),
    ({"evening_auto": True, "last_evening_date": "2026-09-23"}, "21:00", False),
    ({"evening_auto": True, "last_evening_date": "2026-09-22"}, "21:00", True),
    ({"evening_auto": True}, "00:30", False),
])
def test_should_auto_evening(core_mod, config, hhmm, expected):
    hour, minute = map(int, hhmm.split(":"))
    now = datetime.datetime(2026, 9, 23, hour, minute)
    assert core_mod.should_auto_evening(config, now) is expected


def _reminders_by_date(monkeypatch, by_date):
    import core.reminders
    asked = []

    def fake(date_str):
        asked.append(date_str)
        return [dict(r) for r in by_date.get(date_str, [])]

    monkeypatch.setattr(core.reminders, "get_reminders_for_date", fake)
    return asked


def _profile(**extra):
    import core.api
    core.api.save_data("Core", dict({"user_name": "Rafli", "user_nickname": "Bro",
                                     "user_fields": [{"key": "kantor", "value": "Jl. Sudirman 1"}]},
                                    **extra))


def test_evening_summary_action(bmain, lang, monkeypatch):
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    asked = _reminders_by_date(monkeypatch, {
        today.isoformat(): [{"title": "Visit %kantor%", "time": "10:00", "is_done": True},
                            {"title": "Call %myname%", "time": "15:00"}],
        tomorrow.isoformat(): [{"title": "Dentist", "time": "09:00"}],
    })
    _profile()
    bmain._bus.subscribe("on_evening_collect", lambda lines: lines.append("Tomorrow: fine."))
    bmain.play_evening_summary()
    assert asked == [today.isoformat(), tomorrow.isoformat()]
    [text] = bmain.spoken
    assert ", Bro. " in text.split("You finished")[0]
    assert text.endswith("You finished 1 of 2 reminders today. Not done yet: 15:00, Call Rafli. "
                         "Tomorrow you have 1 reminder: 09:00, Dentist. Tomorrow: fine.")


def test_briefing_says_happy_birthday(bmain, lang, monkeypatch):
    today = datetime.date.today()
    _reminders(monkeypatch, [])
    _profile(user_birthday={"day": today.day, "month": today.month, "year": None})
    bmain.play_briefing()
    greeting, rest = bmain.spoken[0].split(" Happy birthday! ")
    assert greeting.endswith(", Bro.") and rest.startswith("Today is ")
    bmain.play_evening_summary()
    assert " Happy birthday! You " in bmain.spoken[1]


def test_auto_briefing_leaves_the_greeting_to_hariku(bmain, lang, monkeypatch):
    import core.api
    _reminders(monkeypatch, [])
    _profile()
    core.api.save_data(bmain.DATA_KEY, {"auto_first_start": True})
    bmain._auto_play()
    # Hariku's startup greeting (on by default) has just said "Good morning, Bro."
    assert bmain.spoken[-1].startswith("Today is ")
    # With the startup greeting off, the briefing greets.
    import core.personal
    core.personal.set_startup_greeting(False)
    core.api.save_data(bmain.DATA_KEY, {"auto_first_start": True})
    bmain._auto_play()
    assert bmain.spoken[-1].startswith("Good ") and ", Bro. Today is " in bmain.spoken[-1]
    # The hotkey always greets.
    core.personal.set_startup_greeting(True)
    bmain.play_briefing()
    assert ", Bro. Today is " in bmain.spoken[-1]


def test_automatic_evening_summary_once_a_day(bmain, lang, monkeypatch):
    import core.api
    _reminders(monkeypatch, [])
    _profile()
    today = datetime.date.today()
    at = lambda h, m: datetime.datetime(today.year, today.month, today.day, h, m)
    bmain._on_minute_tick(at(21, 0))
    assert bmain.spoken == []                               # off by default
    core.api.save_data(bmain.DATA_KEY, {"evening_auto": True, "evening_time": "21:30"})
    bmain._on_minute_tick(at(21, 29))
    assert bmain.spoken == []
    bmain._on_minute_tick(at(21, 30))
    assert len(bmain.spoken) == 1 and "You had no reminders today." in bmain.spoken[0]
    assert core.api.load_data(bmain.DATA_KEY)["last_evening_date"] == today.isoformat()
    bmain._on_minute_tick(at(21, 31))
    bmain._on_minute_tick(at(23, 59))
    assert len(bmain.spoken) == 1                           # once a day
    bmain._active = False
    core.api.save_data(bmain.DATA_KEY, {"evening_auto": True})
    bmain._on_minute_tick(at(22, 0))
    assert len(bmain.spoken) == 1                           # not after teardown


def test_weather_adds_tomorrow_to_the_evening_summary(bmain, lang, monkeypatch):
    weather = _load_main("weather_main_for_evening", WEATHER_DIR)
    import weather_api
    _reminders(monkeypatch, [])
    location = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
                "latitude": -6.2, "longitude": 106.8, "timezone": "Asia/Jakarta"}
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    forecast = {"timezone": "UTC", "utc_offset_seconds": 0,
                "daily": [{"date": today, "code": 2, "high": 30.0, "low": 24.0, "rain_chance": 5},
                          {"date": tomorrow, "code": 61, "high": 31.2, "low": 24.0,
                           "rain_chance": 80}],
                "current": {"time": "", "temperature": 29.6, "feels_like": None,
                            "humidity": None, "wind_speed": None, "code": 2}}
    weather._settings = {"location": location, "units": "metric"}
    weather._cache = weather_api.make_cache(location, forecast)
    bmain._bus.subscribe("on_evening_collect", weather._on_evening_collect)
    bmain.play_evening_summary()
    assert bmain.spoken[0].endswith("You have no reminders tomorrow. Tomorrow: light rain, 31 degrees.")
