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
