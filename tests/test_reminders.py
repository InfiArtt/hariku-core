# hariku2/tests/test_reminders.py
# =============================================================================
# Tests for core.reminders — CRUD operations for reminders
# Uses tmp_data_dir to mock file I/O safely.
# =============================================================================

import pytest


@pytest.fixture(autouse=True)
def setup_reminders_dir(tmp_data_dir):
    """Ensure the reminders directory exists in the mocked data dir and clear state."""
    import os
    import core.api
    import core.reminders
    reminders_dir = os.path.dirname(core.reminders.REMINDERS_FILE)
    os.makedirs(reminders_dir, exist_ok=True)
    if os.path.exists(core.reminders.REMINDERS_FILE):
        os.remove(core.reminders.REMINDERS_FILE)
    # Reset in-memory cache
    core.reminders.REMINDERS = []


class TestRemindersCRUD:
    """Tests for adding, fetching, and deleting reminders."""

    def test_add_and_get_reminders(self):
        from core.reminders import add_reminder, get_reminders_for_date
        
        add_reminder("Test Meeting", "2026-07-12", "14:00")
        add_reminder("Another Meeting", "2026-07-12", "15:00")
        add_reminder("Tomorrow", "2026-07-13", "09:00")
        
        # Should only get reminders for the requested date
        today = get_reminders_for_date("2026-07-12")
        assert len(today) == 2
        assert today[0]["title"] == "Test Meeting"
        assert today[0]["time"] == "14:00"
        
        tomorrow = get_reminders_for_date("2026-07-13")
        assert len(tomorrow) == 1
        
        empty = get_reminders_for_date("2026-07-14")
        assert len(empty) == 0

    def test_delete_reminder(self):
        from core.reminders import add_reminder, get_reminders_for_date, delete_reminder
        
        add_reminder("Test Meeting", "2026-07-12", "14:00")
        today = get_reminders_for_date("2026-07-12")
        assert len(today) == 1
        
        rem_id = today[0]["id"]
        delete_reminder(rem_id)
        
        today_after = get_reminders_for_date("2026-07-12")
        assert len(today_after) == 0

    def test_mark_as_done(self):
        from core.reminders import add_reminder, get_reminders_for_date, mark_as_done
        
        add_reminder("Test Meeting", "2026-07-12", "14:00")
        today = get_reminders_for_date("2026-07-12")
        rem_id = today[0]["id"]
        
        assert not today[0].get("is_done", False)
        
        mark_as_done(rem_id)
        
        today_after = get_reminders_for_date("2026-07-12")
        assert today_after[0]["is_done"] is True
