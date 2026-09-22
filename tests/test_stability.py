# hariku2/tests/test_stability.py
# =============================================================================
# Tests for stability features:
#   - atomic JSON writes + corruption recovery from .bak (core.api)
#   - missed-reminder catch-up decision logic (core.reminders._reminder_due_state)
# =============================================================================

import os
import json
import datetime

import pytest


class TestAtomicWrite:
    def test_roundtrip(self, tmp_data_dir):
        import core.api as api
        api.save_data("StabTest", {"a": 1, "b": [1, 2, 3]})
        assert api.load_data("StabTest") == {"a": 1, "b": [1, 2, 3]}

    def test_backup_holds_previous_copy(self, tmp_data_dir):
        import core.api as api
        api.save_data("StabTest", {"v": 1})
        api.save_data("StabTest", {"v": 2})
        bak = api.get_data_path("StabTest") + ".bak"
        assert os.path.exists(bak)
        with open(bak, encoding="utf-8") as f:
            assert json.load(f) == {"v": 1}       # backup = the previous good copy

    def test_recovery_from_corrupt_main(self, tmp_data_dir):
        import core.api as api
        api.save_data("StabTest", {"good": True})
        api.save_data("StabTest", {"good": "v2"})   # now .bak = {"good": True}
        with open(api.get_data_path("StabTest"), "w", encoding="utf-8") as f:
            f.write("{ this is : not valid json ")   # simulate crash-truncated file
        assert api.load_data("StabTest") == {"good": True}   # recovered from .bak

    def test_missing_main_returns_empty_not_bak(self, tmp_data_dir):
        import core.api as api
        api.save_data("StabTest", {"x": 1})
        api.save_data("StabTest", {"x": 2})          # creates .bak
        os.remove(api.get_data_path("StabTest"))
        # A deliberately-absent main file must NOT be resurrected from .bak.
        assert api.load_data("StabTest") == {}


class TestReminderCatchup:
    NOW = datetime.datetime(2026, 9, 22, 12, 0)

    def _state(self, r):
        from core.reminders import _reminder_due_state
        return _reminder_due_state(r, self.NOW)

    def test_future_is_pending(self):
        assert self._state({"date": "2026-09-22", "time": "13:00"}) == "pending"

    def test_due_now_fires(self):
        assert self._state({"date": "2026-09-22", "time": "12:00"}) == "fire"

    def test_missed_within_24h_fires(self):
        # 10 hours ago -> still within the catch-up window
        assert self._state({"date": "2026-09-22", "time": "02:00"}) == "fire"

    def test_overdue_beyond_window_is_stale(self):
        # 2 days ago -> marked seen silently, no dialog flood
        assert self._state({"date": "2026-09-20", "time": "12:00"}) == "stale"

    def test_done_is_skipped(self):
        assert self._state({"date": "2026-09-22", "time": "02:00", "is_done": True}) == "skip"

    def test_already_notified_is_skipped(self):
        assert self._state({"date": "2026-09-22", "time": "02:00", "notified": True}) == "skip"

    def test_legacy_notified_at_is_skipped(self):
        r = {"date": "2026-09-22", "time": "02:00", "notified_at": "2026-09-22 02:00"}
        assert self._state(r) == "skip"

    def test_bad_datetime_is_skipped(self):
        assert self._state({"date": "not-a-date", "time": "??:??"}) == "skip"
