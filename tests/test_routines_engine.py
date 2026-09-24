# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Routines automation engine (pure trigger logic).
import os
import importlib.util

import pytest

_ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..",
                            "extensions", "routines", "routines_engine.py")


@pytest.fixture(scope="module")
def eng():
    spec = importlib.util.spec_from_file_location("routines_engine", _ENGINE_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CTX = {
    "now_hm": "08:00", "weekday": 0, "date": "2026-09-23",
    "battery": 18, "charging": False, "idle_seconds": 400,
    "active_process": "chrome.exe", "active_title": "Gmail - Inbox",
    "clipboard": "hello world", "online": True,
}


def _ev_ctx(event, event_data=None):
    c = dict(CTX)
    c["event"] = event
    c["event_data"] = event_data
    return c


class TestEventTriggers:
    def test_on_startup(self, eng):
        assert eng.check_all_conditions([{"type": "on_startup", "params": {}}], _ev_ctx("app_startup"))
        assert not eng.check_all_conditions([{"type": "on_startup", "params": {}}], CTX)

    def test_on_date_selected(self, eng):
        assert eng.check_all_conditions([{"type": "on_date_selected", "params": {}}], _ev_ctx("date_selected"))
        assert not eng.check_all_conditions([{"type": "on_date_selected", "params": {}}], _ev_ctx("app_startup"))

    def test_on_reminder_fired_any(self, eng):
        assert eng.check_all_conditions([{"type": "on_reminder_fired", "params": {}}],
                                        _ev_ctx("reminder_fired", {"title": "Standup"}))

    def test_on_reminder_fired_text_filter(self, eng):
        c = _ev_ctx("reminder_fired", {"title": "Standup meeting"})
        assert eng.check_all_conditions([{"type": "on_reminder_fired", "params": {"text": "stand"}}], c)
        assert not eng.check_all_conditions([{"type": "on_reminder_fired", "params": {"text": "lunch"}}], c)

    def test_is_event_routine(self, eng):
        assert eng.is_event_routine({"conditions": [{"type": "on_startup"}]})
        assert not eng.is_event_routine({"conditions": [{"type": "time", "params": {"time": "08:00"}}]})

    def test_event_routine_fires_every_time(self, eng):
        r = {"id": "e1", "enabled": True, "conditions": [{"type": "on_startup", "params": {}}]}
        met = {}
        c = _ev_ctx("app_startup")
        assert eng.should_fire(r, c, met) is True   # event fires
        assert eng.should_fire(r, c, met) is True   # fires again (no rising-edge suppression)
        assert eng.should_fire(r, CTX, met) is False  # not during a non-event evaluate


class TestConditions:
    def test_time_match(self, eng):
        assert eng.check_all_conditions([{"type": "time", "params": {"time": "08:00"}}], CTX)
        assert not eng.check_all_conditions([{"type": "time", "params": {"time": "08:01"}}], CTX)

    def test_and_logic(self, eng):
        conds = [{"type": "time", "params": {"time": "08:00"}},
                 {"type": "battery_below", "params": {"value": 20}}]
        assert eng.check_all_conditions(conds, CTX)
        conds[1]["params"]["value"] = 10   # 18 <= 10 is false
        assert not eng.check_all_conditions(conds, CTX)

    def test_various(self, eng):
        c = eng.check_all_conditions
        assert c([{"type": "is_charging", "params": {"charging": False}}], CTX)
        assert c([{"type": "user_idle", "params": {"minutes": 5}}], CTX)      # 400s >= 300
        assert c([{"type": "app_active", "params": {"process": "chrome"}}], CTX)
        assert c([{"type": "window_title", "params": {"text": "inbox"}}], CTX)
        assert c([{"type": "clipboard_contains", "params": {"text": "world"}}], CTX)
        assert c([{"type": "online", "params": {"online": True}}], CTX)
        assert c([{"type": "day_of_week", "params": {"days": [0, 2]}}], CTX)   # Monday
        assert not c([{"type": "day_of_week", "params": {"days": [5, 6]}}], CTX)

    def test_unknown_type_and_empty(self, eng):
        assert not eng.check_all_conditions([{"type": "nope", "params": {}}], CTX)
        assert not eng.check_all_conditions([], CTX)


class TestNewConditions:
    def test_run_every_never_run(self, eng):
        # No last-fire recorded -> due immediately.
        ctx = {"now_ts": 1000.0, "run_every_last": None}
        assert eng.check_all_conditions(
            [{"type": "run_every", "params": {"minutes": 5}}], ctx)

    def test_run_every_within_interval(self, eng):
        ctx = {"now_ts": 1000.0, "run_every_last": 900.0}  # 100s < 300s
        assert not eng.check_all_conditions(
            [{"type": "run_every", "params": {"minutes": 5}}], ctx)

    def test_run_every_after_interval(self, eng):
        ctx = {"now_ts": 1300.0, "run_every_last": 900.0}  # 400s >= 300s
        assert eng.check_all_conditions(
            [{"type": "run_every", "params": {"minutes": 5}}], ctx)

    def test_run_every_needs_now_ts(self, eng):
        # Missing now_ts (e.g. a bare test ctx) must not crash or fire.
        assert not eng.CONDITION_CHECKERS["run_every"]({"minutes": 5}, {})

    def test_run_every_bad_interval(self, eng):
        ctx = {"now_ts": 1000.0, "run_every_last": None}
        assert not eng.CONDITION_CHECKERS["run_every"]({"minutes": 0}, ctx)

    def test_event_today_any(self, eng):
        ctx = {"reminders_today": [{"title": "Dentist"}]}
        assert eng.CONDITION_CHECKERS["event_today"]({}, ctx)
        assert not eng.CONDITION_CHECKERS["event_today"]({}, {"reminders_today": []})

    def test_event_today_title_filter(self, eng):
        ctx = {"reminders_today": [{"title": "Dentist appointment"},
                                   {"title": "Buy milk"}]}
        assert eng.CONDITION_CHECKERS["event_today"]({"text": "dentist"}, ctx)
        assert not eng.CONDITION_CHECKERS["event_today"]({"text": "gym"}, ctx)

    def test_wifi_ssid(self, eng):
        ctx = {"wifi_ssid": "HomeNet-5G"}
        assert eng.CONDITION_CHECKERS["wifi_ssid"]({"text": "homenet"}, ctx)
        assert not eng.CONDITION_CHECKERS["wifi_ssid"]({"text": "office"}, ctx)
        # Empty filter or missing ssid never matches.
        assert not eng.CONDITION_CHECKERS["wifi_ssid"]({"text": ""}, ctx)
        assert not eng.CONDITION_CHECKERS["wifi_ssid"]({"text": "x"}, {})

    def test_ram_above(self, eng):
        assert eng.CONDITION_CHECKERS["ram_above"]({"value": 80}, {"ram_percent": 85})
        assert not eng.CONDITION_CHECKERS["ram_above"]({"value": 80}, {"ram_percent": 70})
        assert not eng.CONDITION_CHECKERS["ram_above"]({"value": 80}, {"ram_percent": None})

    def test_cpu_above(self, eng):
        assert eng.CONDITION_CHECKERS["cpu_above"]({"value": 50}, {"cpu_percent": 90})
        assert not eng.CONDITION_CHECKERS["cpu_above"]({"value": 50}, {"cpu_percent": 10})
        assert not eng.CONDITION_CHECKERS["cpu_above"]({"value": 50}, {"cpu_percent": None})

    def test_new_conditions_registered(self, eng):
        # Contract: labels/specs stay in lockstep with checkers.
        for t in ("run_every", "event_today", "wifi_ssid", "ram_above", "cpu_above"):
            assert t in eng.CONDITION_CHECKERS
            assert t in dict(eng.CONDITION_LABELS)
            assert t in eng.COND_SPECS

    def test_new_actions_registered(self, eng):
        for t in ("open_app", "open_file", "lock_screen", "set_volume",
                  "copy_to_clipboard", "type_text"):
            assert t in dict(eng.ACTION_LABELS)
            assert t in eng.ACTION_SPECS


class TestPlaceholders:
    def test_simple_tokens(self, eng):
        out = eng.process_placeholders("It's {time} on {date}, battery {battery}%", CTX)
        assert out == "It's 08:00 on 2026-09-23, battery 18%"

    def test_variable(self, eng):
        assert eng.process_placeholders("Hi {var:user}", CTX, {"user": "Rafli"}) == "Hi Rafli"

    def test_none_safe(self, eng):
        assert eng.process_placeholders("", CTX) == ""

    def test_new_tokens(self, eng):
        ctx = dict(CTX)
        ctx.update({"wifi_ssid": "HomeNet", "ram_percent": 42, "cpu_percent": 7,
                    "reminders_today": [{"title": "a"}, {"title": "b"}]})
        out = eng.process_placeholders(
            "wifi {ssid} ram {ram}% cpu {cpu}% events {events}", ctx)
        assert out == "wifi HomeNet ram 42% cpu 7% events 2"

    def test_new_tokens_missing_are_blank(self, eng):
        # Missing metrics collapse to empty strings; events defaults to 0.
        out = eng.process_placeholders("[{ssid}][{ram}][{cpu}][{events}]", CTX)
        assert out == "[][][][0]"


class TestPlaceholdersBothSyntaxes:
    """Routines 1.1: %token% next to the old {token}, the profile, one pass."""

    @pytest.fixture
    def with_profile(self, tmp_data_dir):
        import core.api
        core.api.save_data("Core", {"user_name": "Rafli", "user_nickname": "Bro",
                                    "user_fields": [{"key": "kantor", "value": "Jl. Sudirman 1"}]})

    def test_percent_tokens(self, eng, tmp_data_dir):
        out = eng.process_placeholders(
            "It's %time% on %date%, battery %battery%%, app %app%, clip %clipboard%", CTX)
        assert out == "It's 08:00 on 2026-09-23, battery 18%, app chrome.exe, clip hello world"

    def test_percent_tokens_any_case(self, eng, tmp_data_dir):
        assert eng.process_placeholders("%TIME% %Date%", CTX) == "08:00 2026-09-23"

    def test_new_percent_tokens(self, eng, tmp_data_dir):
        ctx = dict(CTX)
        ctx.update({"wifi_ssid": "HomeNet", "ram_percent": 42, "cpu_percent": 7,
                    "reminders_today": [{"title": "a"}, {"title": "b"}]})
        out = eng.process_placeholders("wifi %ssid% ram %ram%% cpu %cpu%% events %events%", ctx)
        assert out == "wifi HomeNet ram 42% cpu 7% events 2"
        assert eng.process_placeholders("[%ssid%][%ram%][%cpu%][%events%]", CTX) == "[][][][0]"

    def test_missing_battery_is_blank(self, eng, tmp_data_dir):
        ctx = dict(CTX, battery=None)
        assert eng.process_placeholders("[{battery}][%battery%]", ctx) == "[][]"

    def test_both_syntaxes_mixed(self, eng, tmp_data_dir):
        out = eng.process_placeholders("{time} / %time% / {var:user} / %var:user%",
                                       CTX, {"user": "Rafli"})
        assert out == "08:00 / 08:00 / Rafli / Rafli"

    def test_variables(self, eng, tmp_data_dir):
        variables = {"greeting": "Halo", "My Var": "x"}
        assert eng.process_placeholders("%var:greeting% %var:My Var%", CTX, variables) == "Halo x"
        assert eng.process_placeholders("%VAR:GREETING%", CTX, variables) == "Halo"
        # Unknown variables stay as written, in either syntax.
        assert eng.process_placeholders("{var:nope} %var:nope%", CTX, variables) == \
            "{var:nope} %var:nope%"

    def test_profile_tokens(self, eng, with_profile):
        out = eng.process_placeholders(
            "Morning %mynickname% (%MyName%), go to %kantor% at {time}", CTX)
        assert out == "Morning Bro (Rafli), go to Jl. Sudirman 1 at 08:00"

    def test_profile_without_name(self, eng, tmp_data_dir):
        assert eng.process_placeholders("Hi %myname%!", CTX) == "Hi !"

    def test_single_pass(self, eng, with_profile):
        # Inserted values are never expanded again, whatever syntax they contain.
        ctx = dict(CTX, clipboard="%myname% {time} {var:v}")
        assert eng.process_placeholders("%clipboard%", ctx, {"v": "V"}) == "%myname% {time} {var:v}"
        assert eng.process_placeholders("{clipboard}", ctx, {"v": "V"}) == "%myname% {time} {var:v}"
        assert eng.process_placeholders("{var:v}", CTX, {"v": "{time} %time%"}) == "{time} %time%"
        assert eng.process_placeholders("%var:v%", CTX, {"v": "%kantor%"}) == "%kantor%"

    def test_variables_cannot_shadow_tokens(self, eng, tmp_data_dir):
        # Variables live under var:, so a variable named "time" is %var:time%.
        assert eng.process_placeholders("%var:time% %time%", CTX, {"time": "T"}) == "T 08:00"

    def test_unknown_and_bare_percent_untouched(self, eng, tmp_data_dir):
        text = "50% off, 100% done, %APPDATA%\\x, %foo%, {foo}, {Time}"
        assert eng.process_placeholders(text, CTX) == text

    def test_old_routines_unchanged(self, eng, tmp_data_dir):
        # Texts written for Routines 1.0 give the same result as before.
        ctx = dict(CTX, wifi_ssid="HomeNet", ram_percent=42, cpu_percent=7,
                   reminders_today=[{"title": "a"}])
        cases = {
            "Good morning": "Good morning",
            "It's {time} on {date}, battery {battery}%": "It's 08:00 on 2026-09-23, battery 18%",
            "{app} | {clipboard} | {ssid} | {ram}% | {cpu}% | {events}":
                "chrome.exe | hello world | HomeNet | 42% | 7% | 1",
            "Hi {var:user}": "Hi Rafli",
            "{TIME} stays": "{TIME} stays",
        }
        for text, expected in cases.items():
            assert eng.process_placeholders(text, ctx, {"user": "Rafli"}) == expected, text


class TestInsertPlaceholderMenu:
    def test_entries(self, eng):
        entries = eng.placeholder_menu_entries(
            "Rafli", "Bro", [("kantor", "Jl. Sudirman 1"), ("kosong", "")],
            ["greeting", "_routine_depth", "greeting", "", "50%"])
        tokens = [t for t, _label in entries]
        labels = dict(entries)
        assert tokens[:4] == ["%myname%", "%mynickname%", "%kantor%", "%kosong%"]
        assert labels["%myname%"] == "%myname%: your name (Rafli)"
        assert labels["%mynickname%"] == "%mynickname%: what Hariku calls you (Bro)"
        assert labels["%kantor%"] == "%kantor%: your placeholder (Jl. Sudirman 1)"
        assert labels["%kosong%"] == "%kosong%: your placeholder (empty)"
        assert labels["%time%"] == "%time%: current time"
        for token in ("time", "date", "battery", "app", "clipboard", "ssid", "ram", "cpu", "events"):
            assert "%" + token + "%" in labels
        # Internal, empty, duplicate and unusable variable names are left out.
        assert [t for t in tokens if t.startswith("%var:")] == ["%var:greeting%"]
        assert labels["%var:greeting%"] == "%var:greeting%: the variable greeting"

    def test_entries_without_a_profile(self, eng):
        labels = dict(eng.placeholder_menu_entries())
        assert labels["%myname%"] == "%myname%: your name (not set)"
        assert labels["%mynickname%"] == "%mynickname%: what Hariku calls you (not set)"

    def test_nickname_falls_back_to_the_name(self, eng):
        assert dict(eng.placeholder_menu_entries("Rafli", ""))["%mynickname%"] == \
            "%mynickname%: what Hariku calls you (Rafli)"

    def test_long_values_are_shortened(self, eng):
        label = dict(eng.placeholder_menu_entries(fields=[("alamat", "x" * 100)]))["%alamat%"]
        assert len(label) < 80 and label.endswith("…)")

    def test_every_menu_token_expands(self, eng, tmp_data_dir):
        import core.api
        core.api.save_data("Core", {"user_name": "Rafli",
                                    "user_fields": [{"key": "kantor", "value": "K"}]})
        ctx = dict(CTX, wifi_ssid="W", ram_percent=1, cpu_percent=2)
        for token, _label in eng.placeholder_menu_entries("Rafli", "", [("kantor", "K")], ["v"]):
            assert eng.process_placeholders(token, ctx, {"v": "V"}) != token, token

    @pytest.mark.parametrize("value, start, end, expected, caret", [
        ("", 0, 0, "%time%", 6),
        ("Hello ", 6, 6, "Hello %time%", 12),
        ("Hello world", 6, 6, "Hello %time%world", 12),
        ("Hello world", 0, 0, "%time%Hello world", 6),
        ("Hello world", 6, 11, "Hello %time%", 12),        # part selected: replaced
        ("Hello world", 0, 11, "Hello world%time%", 17),   # all selected (Tab): appended
        ("Hi", 5, 9, "Hi%time%", 8),                        # out of range: clamped
    ])
    def test_insert(self, eng, value, start, end, expected, caret):
        assert eng.insert_placeholder(value, start, end, "%time%") == (expected, caret)


class TestShouldFire:
    def _routine(self):
        return {"id": "r1", "enabled": True,
                "conditions": [{"type": "time", "params": {"time": "08:00"}}]}

    def test_rising_edge_fires_once(self, eng):
        r = self._routine()
        met = {}
        assert eng.should_fire(r, CTX, met) is True     # became true -> fire
        assert eng.should_fire(r, CTX, met) is False    # still true -> no re-fire

    def test_refires_after_reset(self, eng):
        r = self._routine()
        met = {}
        assert eng.should_fire(r, CTX, met) is True
        other = dict(CTX); other["now_hm"] = "09:00"     # condition now false
        assert eng.should_fire(r, other, met) is False
        assert eng.should_fire(r, CTX, met) is True      # true again -> fire

    def test_disabled_never_fires(self, eng):
        r = self._routine(); r["enabled"] = False
        assert eng.should_fire(r, CTX, {}) is False


# --- Actions: every text parameter goes through the placeholders ------------------

@pytest.fixture
def actions(tmp_data_dir, monkeypatch):
    import core.api
    import sys
    routines_dir = os.path.join(os.path.dirname(__file__), "..", "extensions", "routines")
    if routines_dir not in sys.path:
        sys.path.insert(0, routines_dir)
    spec = importlib.util.spec_from_file_location(
        "routines_actions_under_test", os.path.join(routines_dir, "routines_actions.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    core.api.save_data("Core", {"user_name": "Rafli", "user_nickname": "Bro",
                                "user_fields": [{"key": "kantor", "value": "Jl. Sudirman 1"}]})
    module.spoken = []
    monkeypatch.setattr(module, "speak", lambda text, interrupt=False: module.spoken.append(text))
    return module


def test_speak_action_fills_in_the_profile(actions):
    actions.ACTION_RUNNERS["tts"]({"text": "Morning %mynickname%, it's %time% ({time})"}, CTX, {})
    assert actions.spoken == ["Morning Bro, it's 08:00 (08:00)"]


def test_play_sound_action_fills_in_placeholders(actions, monkeypatch):
    import core.sounds
    played = []
    monkeypatch.setattr(core.sounds, "play_internal_sound", lambda name: played.append(name))
    actions.ACTION_RUNNERS["play_sound"]({"sound": "%var:s%.wav"}, CTX, {"s": "ding"})
    assert played == ["ding.wav"]


def test_speak_agenda_fills_in_reminder_titles(actions, monkeypatch):
    import core.reminders
    monkeypatch.setattr(core.reminders, "get_reminders_for_date",
                        lambda date: [{"time": "09:00", "title": "Call %myname% at %kantor%"}])
    actions.ACTION_RUNNERS["speak_agenda"]({"date": ""}, CTX, {})
    assert actions.spoken == ["1 reminders. 09:00 Call Rafli at Jl. Sudirman 1"]
