# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Tests for recurring-reminder logic in core.reminders:
#   _next_occurrence  — re-arm to the next future slot (skips missed ones)
#   _recurring_hits   — does a recurring reminder fall on a given date (agenda)
# =============================================================================

import datetime
import pytest


class TestNextOccurrence:
    NOW = datetime.datetime(2026, 9, 23, 12, 0)  # Wed 2026-09-23 12:00

    def _next(self, date, rec, interval=1, time="09:00"):
        from core.reminders import _next_occurrence
        return _next_occurrence(date, time, rec, interval, self.NOW)

    def test_daily_overdue_jumps_to_next_future_day(self):
        # due yesterday 09:00 -> next future daily slot is tomorrow (24th)
        assert self._next("2026-09-22", "daily") == "2026-09-24"

    def test_daily_due_today_advances_to_tomorrow(self):
        # 09:00 today already passed (now 12:00) -> next is the 24th
        assert self._next("2026-09-23", "daily") == "2026-09-24"

    def test_daily_interval_two(self):
        assert self._next("2026-09-21", "daily", interval=2) == "2026-09-25"

    def test_weekly_keeps_weekday(self):
        nxt = self._next("2026-09-16", "weekly")  # Wed two weeks ago
        d = datetime.date.fromisoformat(nxt)
        assert d.weekday() == 2 and d > self.NOW.date()   # still a Wednesday, future

    def test_monthly_clamps_month_end(self):
        # Jan 31 monthly, now is Sep -> lands on a valid clamped day-of-month
        nxt = self._next("2026-01-31", "monthly")
        assert datetime.date.fromisoformat(nxt) > self.NOW.date()

    def test_yearly(self):
        assert self._next("2020-09-23", "yearly") == "2027-09-23"

    def test_none_returns_same(self):
        assert self._next("2026-09-22", "none") == "2026-09-22"

    def test_monthly_overdue_lands_on_the_anchor_day(self):
        # From 31 January, missed every month since: September has 30 days.
        assert self._next("2026-01-31", "monthly") == "2026-09-30"


def _chain(date, rec, anchor, steps, interval=1, time="09:00"):
    """The dates a reminder re-arms to, one fired occurrence after another."""
    from core.reminders import _next_occurrence
    dates = []
    for _ in range(steps):
        fired = datetime.datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        date = _next_occurrence(date, time, rec, interval, fired, anchor=anchor)
        dates.append(date)
    return dates


class TestAnchorDay:
    """[Monthly fix] A monthly reminder on the 31st used to slide to the 28th
    after February and stay there; it keeps its day now."""

    def test_monthly_31st_keeps_its_day(self):
        assert _chain("2026-01-31", "monthly", 31, 4) == \
            ["2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]

    def test_monthly_30th_through_february_of_a_leap_year(self):
        assert _chain("2028-01-30", "monthly", 30, 3) == ["2028-02-29", "2028-03-30", "2028-04-30"]

    def test_monthly_every_two_months(self):
        assert _chain("2026-01-31", "monthly", 31, 3, interval=2) == \
            ["2026-03-31", "2026-05-31", "2026-07-31"]
        assert _chain("2025-12-31", "monthly", 31, 2, interval=2) == ["2026-02-28", "2026-04-30"]

    def test_yearly_29_february(self):
        assert _chain("2028-02-29", "yearly", 29, 4) == \
            ["2029-02-28", "2030-02-28", "2031-02-28", "2032-02-29"]

    def test_yearly_every_two_years(self):
        assert _chain("2028-02-29", "yearly", 29, 2, interval=2) == ["2030-02-28", "2032-02-29"]

    def test_the_anchor_defaults_to_the_stored_day(self):
        from core.reminders import _next_occurrence
        now = datetime.datetime(2026, 1, 31, 12, 0)
        assert _next_occurrence("2026-01-31", "09:00", "monthly", 1, now) == "2026-02-28"
        # Without the anchor, a reminder already on the 28th stays on the 28th.
        now = datetime.datetime(2026, 2, 28, 12, 0)
        assert _next_occurrence("2026-02-28", "09:00", "monthly", 1, now) == "2026-03-28"
        assert _next_occurrence("2026-02-28", "09:00", "monthly", 1, now, anchor=31) == "2026-03-31"

    def test_missed_occurrences_are_skipped(self):
        from core.reminders import _next_occurrence
        now = datetime.datetime(2026, 11, 15, 8, 0)
        # Stored on 28 February with its anchor, missed until mid-November.
        assert _next_occurrence("2026-02-28", "09:00", "monthly", 1, now, anchor=31) == "2026-11-30"
        assert _next_occurrence("2026-02-28", "09:00", "monthly", 2, now, anchor=31) == "2026-12-31"
        assert _next_occurrence("2026-02-28", "09:00", "monthly", 3, now, anchor=31) == "2026-11-30"
        # Daily and weekly with intervals, several missed.
        assert _next_occurrence("2026-11-01", "09:00", "daily", 3, now) == "2026-11-16"
        assert _next_occurrence("2026-10-01", "09:00", "weekly", 2, now) == "2026-11-26"
        assert _next_occurrence("2020-02-29", "09:00", "yearly", 1, now, anchor=29) == "2027-02-28"

    def test_later_on_the_same_day_is_still_to_come(self):
        from core.reminders import _next_occurrence
        now = datetime.datetime(2026, 3, 31, 8, 0)
        assert _next_occurrence("2026-03-31", "09:00", "monthly", 1, now, anchor=31) == "2026-03-31"

    def test_a_bad_anchor_is_ignored(self):
        from core.reminders import _next_occurrence
        now = datetime.datetime(2026, 1, 31, 12, 0)
        for anchor in (0, 32, "31", None):
            assert _next_occurrence("2026-01-31", "09:00", "monthly", 1, now,
                                    anchor=anchor) == "2026-02-28"

    def test_anchor_day_of_a_reminder(self):
        from core.reminders import anchor_day
        assert anchor_day({"date": "2026-02-28", "anchor_day": 31}) == 31
        assert anchor_day({"date": "2026-02-28"}) == 28          # saved before 2.7
        assert anchor_day({"date": "2026-02-28", "anchor_day": True}) == 28
        assert anchor_day({"date": "2026-02-28", "anchor_day": 40}) == 28
        assert anchor_day({"date": "nope"}) is None

    def test_rearm_stores_the_anchor_of_an_old_reminder(self):
        from core.reminders import _rearm
        r = {"date": "2026-01-31", "time": "09:00", "recurrence": "monthly", "interval": 1,
             "notified_at": "x"}
        _rearm(r, datetime.datetime(2026, 1, 31, 9, 0))
        assert (r["date"], r["anchor_day"], r["notified"]) == ("2026-02-28", 31, False)
        assert "notified_at" not in r
        _rearm(r, datetime.datetime(2026, 2, 28, 9, 0))
        assert r["date"] == "2026-03-31"

    def test_rearm_keeps_daily_reminders_as_they_were(self):
        from core.reminders import _rearm
        r = {"date": "2026-01-31", "time": "09:00", "recurrence": "daily", "interval": 2}
        _rearm(r, datetime.datetime(2026, 1, 31, 9, 0))
        assert r["date"] == "2026-02-02" and "anchor_day" not in r


class TestAnchorStoredAndUsed:
    def _file(self, tmp_data_dir, monkeypatch):
        import core.reminders as rem
        import os
        monkeypatch.setattr(rem, "REMINDERS_FILE", os.path.join(tmp_data_dir, "reminders.json"))
        return rem

    def test_add_reminder_stores_the_anchor(self, tmp_data_dir, monkeypatch):
        rem = self._file(tmp_data_dir, monkeypatch)
        rem.add_reminder("Rent", "2026-01-31", "09:00", recurrence="monthly")
        rem.add_reminder("Leap", "2028-02-29", "09:00", recurrence="yearly", interval=1)
        rem.add_reminder("Pills", "2026-01-31", "09:00", recurrence="daily")
        rent, leap, pills = rem.load_reminders()
        assert rent["anchor_day"] == 31 and leap["anchor_day"] == 29
        assert "anchor_day" not in pills

    def test_snooze_keeps_the_anchor(self, tmp_data_dir, monkeypatch):
        import core.speech
        rem = self._file(tmp_data_dir, monkeypatch)
        monkeypatch.setattr(core.speech, "speak", lambda *a, **k: None)
        rem.save_reminders([{"id": "a", "title": "Rent", "date": "2026-01-31", "time": "09:00",
                             "is_done": False, "recurrence": "monthly", "interval": 1}])
        rem.snooze_reminder("a", 5)
        (r,) = rem.load_reminders()
        assert r["anchor_day"] == 31 and r["date"] != "2026-01-31"

    def test_agenda_shows_the_anchor_day(self, tmp_data_dir, monkeypatch, fresh_event_bus):
        rem = self._file(tmp_data_dir, monkeypatch)
        monkeypatch.setattr(rem, "bus", fresh_event_bus)   # no extension adds items
        rem.save_reminders([{"id": "a", "title": "Rent", "date": "2026-02-28", "time": "09:00",
                             "is_done": False, "recurrence": "monthly", "interval": 1,
                             "anchor_day": 31}])
        assert [r["title"] for r in rem.get_reminders_for_date("2026-03-31")] == ["Rent"]
        assert rem.get_reminders_for_date("2026-03-28") == []
        assert [r["title"] for r in rem.get_reminders_for_date("2026-04-30")] == ["Rent"]


class TestRecurringHits:
    def _hit(self, base, rec, target, interval=1):
        from core.reminders import _recurring_hits
        return _recurring_hits({"date": base, "recurrence": rec, "interval": interval}, target)

    def test_daily_every_day(self):
        assert self._hit("2026-09-23", "daily", "2026-09-25") is True

    def test_daily_interval_two_skips_odd(self):
        assert self._hit("2026-09-23", "daily", "2026-09-25", interval=2) is True
        assert self._hit("2026-09-23", "daily", "2026-09-24", interval=2) is False

    def test_weekly_same_weekday(self):
        assert self._hit("2026-09-23", "weekly", "2026-09-30") is True    # +7
        assert self._hit("2026-09-23", "weekly", "2026-09-29") is False

    def test_monthly_same_dom(self):
        assert self._hit("2026-01-15", "monthly", "2026-02-15") is True
        assert self._hit("2026-01-15", "monthly", "2026-02-16") is False

    def test_monthly_clamped_end(self):
        # Jan 31 monthly should hit Feb 28 (clamped)
        assert self._hit("2026-01-31", "monthly", "2026-02-28") is True
        # ... and then the 31st again, not the 28th.
        assert self._hit("2026-01-31", "monthly", "2026-03-31") is True
        assert self._hit("2026-01-31", "monthly", "2026-03-28") is False

    def test_monthly_uses_the_stored_anchor(self):
        from core.reminders import _recurring_hits
        r = {"date": "2026-02-28", "recurrence": "monthly", "interval": 1, "anchor_day": 31}
        assert _recurring_hits(r, "2026-03-31") is True
        assert _recurring_hits(r, "2026-03-28") is False
        assert _recurring_hits(r, "2026-04-30") is True

    def test_yearly_29_february(self):
        from core.reminders import _recurring_hits
        r = {"date": "2029-02-28", "recurrence": "yearly", "interval": 1, "anchor_day": 29}
        assert _recurring_hits(r, "2032-02-29") is True
        assert _recurring_hits(r, "2032-02-28") is False
        assert _recurring_hits(r, "2030-02-28") is True

    def test_yearly(self):
        assert self._hit("2026-03-01", "yearly", "2027-03-01") is True
        assert self._hit("2026-03-01", "yearly", "2027-03-02") is False

    def test_same_date_is_not_a_recurring_hit(self):
        # exact date is handled by the direct match, not _recurring_hits
        assert self._hit("2026-09-23", "daily", "2026-09-23") is False

    def test_none_never_hits(self):
        assert self._hit("2026-09-23", "none", "2026-09-24") is False


class TestAddReminderRecurrence:
    def test_stores_recurrence_and_interval(self, tmp_data_dir, monkeypatch):
        import core.reminders as rem
        import os
        monkeypatch.setattr(rem, "REMINDERS_FILE", os.path.join(tmp_data_dir, "reminders.json"))
        rem.add_reminder("Standup", "2026-09-23", "09:00", recurrence="weekly", interval=1)
        loaded = rem.load_reminders()
        assert loaded[-1]["recurrence"] == "weekly"
        assert loaded[-1]["interval"] == 1

    def test_bad_recurrence_falls_back_to_none(self, tmp_data_dir, monkeypatch):
        import core.reminders as rem
        import os
        monkeypatch.setattr(rem, "REMINDERS_FILE", os.path.join(tmp_data_dir, "reminders.json"))
        rem.add_reminder("X", "2026-09-23", "09:00", recurrence="hourly")
        assert rem.load_reminders()[-1]["recurrence"] == "none"
