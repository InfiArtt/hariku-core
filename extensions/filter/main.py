# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# ============================================================
# Filter — Calendar Navigation Filter for Hariku V2
# ============================================================
# Port of the V1 filter system. Allows users to filter the
# calendar view so that arrow key navigation (←/→) only stops
# on dates that match the active filter criteria.
#
# Features:
#   - Filter by reminder status: All / Has Reminders Only
#   - Filter by keyword: Only show dates whose reminders
#     contain a specific keyword
#   - Arrow keys automatically skip non-matching dates
#   - Status label shows the active filter at all times
#   - "Filters applied" / "Filters reset" spoken feedback
# ============================================================

import os
import logging
import datetime
import wx

import core.api
import core.hotkeys
from core.events import bus
from core.speech import speak
from core.sounds import play_internal_sound

logger = logging.getLogger(__name__)

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_KEY = "FilterExtension"


# ============================================================
# Active Filters State
# ============================================================

_active_filters = {
    "reminder_status": "all",       # "all" | "has_reminders" | "no_reminders"
    "keyword": "",                  # substring match on reminder titles
}

_filter_active = False  # Quick check flag


def _is_filter_active():
    """Returns True if any filter is active."""
    return (
        _active_filters["reminder_status"] != "all"
        or _active_filters["keyword"].strip() != ""
    )


def _is_date_visible(date_str):
    """
    Check if a date passes the current filter criteria.

    Args:
        date_str: "YYYY-MM-DD" format

    Returns:
        True if the date should be visible, False if it should be skipped.
    """
    if not _is_filter_active():
        return True

    from core.reminders import get_reminders_for_date

    # Use the core API which also fires the on_fetch_agenda event.
    # This automatically includes recurring events injected by gcal_integration!
    day_reminders = get_reminders_for_date(date_str)

    # Reminder status filter
    status = _active_filters["reminder_status"]
    if status == "has_reminders" and not day_reminders:
        return False
    if status == "no_reminders" and day_reminders:
        return False

    # Keyword filter
    keyword = _active_filters["keyword"].strip().lower()
    if keyword:
        if not day_reminders:
            return False
        # At least one reminder must contain the keyword
        match = any(keyword in r.get("title", "").lower() for r in day_reminders)
        if not match:
            return False

    return True


def _find_next_visible_date(start_date_str, direction=1, max_attempts=365):
    """
    From start_date, search in the given direction (+1=forward, -1=backward)
    for the next date that passes the filter.

    Returns:
        "YYYY-MM-DD" string of the found date, or None if nothing found.
    """
    try:
        current = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    for _ in range(max_attempts):
        current += datetime.timedelta(days=direction)
        candidate = current.isoformat()
        if _is_date_visible(candidate):
            return candidate

    return None


# ============================================================
# Filter Dialog (NVDA-friendly)
# ============================================================

class FilterDialog(wx.Dialog):
    """
    Accessible filter dialog. Users configure filter criteria here,
    then Apply to make the calendar navigation skip non-matching dates.
    """

    def __init__(self, parent):
        super().__init__(parent, title="Filter Dates", size=(420, 300))
        self._init_ui()
        self._set_initial_values()
        self.CentreOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ---- Reminder Status Filter ----
        status_box = wx.StaticBox(panel, label="Filter by Reminder Status")
        status_sizer = wx.StaticBoxSizer(status_box, wx.VERTICAL)

        self.rb_status = wx.RadioBox(
            panel,
            label="",
            choices=["All Dates", "Only Dates with Reminders", "Only Empty Dates"],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
        )
        status_sizer.Add(self.rb_status, 0, wx.ALL | wx.EXPAND, 5)
        vbox.Add(status_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # ---- Keyword Filter ----
        keyword_box = wx.StaticBox(panel, label="Filter by Keyword")
        keyword_sizer = wx.StaticBoxSizer(keyword_box, wx.VERTICAL)

        self.txt_keyword = wx.TextCtrl(panel)
        keyword_sizer.Add(
            wx.StaticText(panel, label="Only show dates with reminders containing:"),
            0, wx.ALL, 5,
        )
        keyword_sizer.Add(self.txt_keyword, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        vbox.Add(keyword_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # ---- Buttons ----
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_apply = wx.Button(panel, label="&Apply")
        self.btn_apply.SetDefault()
        self.btn_reset = wx.Button(panel, label="&Reset")
        self.btn_close = wx.Button(panel, wx.ID_CANCEL, label="&Close")

        btn_row.Add(self.btn_apply, 0)
        btn_row.Add(self.btn_reset, 0, wx.LEFT, 5)
        btn_row.Add(self.btn_close, 0, wx.LEFT, 5)
        vbox.Add(btn_row, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(vbox)

        self.btn_apply.Bind(wx.EVT_BUTTON, self._on_apply)
        self.btn_reset.Bind(wx.EVT_BUTTON, self._on_reset)

    def _set_initial_values(self):
        # Reminder status
        status = _active_filters["reminder_status"]
        if status == "has_reminders":
            self.rb_status.SetSelection(1)
        elif status == "no_reminders":
            self.rb_status.SetSelection(2)
        else:
            self.rb_status.SetSelection(0)

        # Keyword
        self.txt_keyword.SetValue(_active_filters.get("keyword", ""))

    def _on_apply(self, event):
        global _filter_active

        idx = self.rb_status.GetSelection()
        _active_filters["reminder_status"] = ["all", "has_reminders", "no_reminders"][idx]
        _active_filters["keyword"] = self.txt_keyword.GetValue().strip()
        _filter_active = _is_filter_active()

        self.EndModal(wx.ID_OK)

    def _on_reset(self, event):
        global _filter_active

        _active_filters["reminder_status"] = "all"
        _active_filters["keyword"] = ""
        _filter_active = False

        self._set_initial_values()
        speak("Filters reset.", interrupt=True)
        play_internal_sound("info.wav")


# ============================================================
# Navigation Override
# ============================================================

def _on_date_changed(date_str):
    """
    Intercept date changes. If a filter is active and the new date
    doesn't match, automatically jump to the next matching date.
    """
    if not _is_filter_active():
        return

    if _is_date_visible(date_str):
        return

    # The date doesn't match the filter — find the nearest visible one.
    # Determine direction based on whether user went forward or backward.
    # We'll try forward first (more natural), then backward.
    next_date = _find_next_visible_date(date_str, direction=1, max_attempts=365)
    if not next_date:
        next_date = _find_next_visible_date(date_str, direction=-1, max_attempts=365)

    if next_date:
        # Small delay to avoid recursion (this function subscribes to on_date_changed)
        wx.CallAfter(core.api.set_selected_date, next_date)
    else:
        speak("No further dates match the current filter.", interrupt=True)


def _get_filter_status_text():
    """Build a human-readable summary of the active filter."""
    if not _is_filter_active():
        return "No filter active"

    parts = []
    status = _active_filters["reminder_status"]
    if status == "has_reminders":
        parts.append("Dates with reminders only")
    elif status == "no_reminders":
        parts.append("Empty dates only")

    keyword = _active_filters["keyword"]
    if keyword:
        parts.append(f'Keyword: "{keyword}"')

    return " | ".join(parts)


# ============================================================
# Hotkey Callbacks
# ============================================================

def _open_filter_dialog(tap_count=1):
    """
    Open the filter dialog.
    Tap 1: Open filter dialog
    Tap 2: Quick toggle — if filter is active, reset it; if not, show dialog
    """
    global _filter_active

    if tap_count >= 2:
        if _is_filter_active():
            _active_filters["reminder_status"] = "all"
            _active_filters["keyword"] = ""
            _filter_active = False
            speak("Filters reset.", interrupt=True)
            play_internal_sound("info.wav")
        else:
            speak("No filter is active.", interrupt=True)
        return

    parent = core.api.main_window_instance
    dlg = FilterDialog(parent)

    if dlg.ShowModal() == wx.ID_OK:
        if _is_filter_active():
            speak(f"Filters applied. {_get_filter_status_text()}", interrupt=True)
            play_internal_sound("button.wav")

            # If current date is hidden by filter, jump to nearest visible
            current = core.api.get_selected_date()
            if current and not _is_date_visible(current):
                speak("Current date is hidden by filter. Finding nearest match...", interrupt=True)
                found = _find_next_visible_date(current, 1, 35)
                if not found:
                    found = _find_next_visible_date(current, -1, 35)
                if found:
                    core.api.set_selected_date(found)
                else:
                    speak("No dates nearby match the filter.", interrupt=True)
        else:
            speak("Filters reset.", interrupt=True)
            play_internal_sound("info.wav")

    dlg.Destroy()


def _announce_filter_status():
    """Read the current filter status aloud."""
    speak(_get_filter_status_text(), interrupt=True)


# ============================================================
# Lifecycle: register()
# ============================================================

def register(bus):
    logger.info("[Filter] Filter extension loaded.")

    # Subscribe to date changes for auto-skip navigation
    bus.subscribe("on_date_changed", _on_date_changed)

    # Hotkeys
    core.hotkeys.register_action(
        "Filter", "open_filter",
        "Open Filter dialog (tap twice to reset filters)",
        ord("F"), False, _open_filter_dialog,
        default_shift=True,
    )

    core.hotkeys.register_action(
        "Filter", "announce_status",
        "Announce current filter status",
        None, False, _announce_filter_status,
    )
