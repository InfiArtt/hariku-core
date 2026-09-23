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
