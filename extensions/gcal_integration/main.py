# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# ============================================================
# Google Calendar Reader — Hariku V2 Extension
# ============================================================
# One-way sync: reads events from Google Calendar via private
# iCal (.ics) URL. Local edits/additions are stored in a local
# JSON file and are NOT synced back to Google.
# ============================================================

import os
import logging
import json
import wx
import urllib.request
import ssl
from datetime import datetime

import core.api
import core.hotkeys
import core.preferences
from core.events import bus
from core.speech import speak
from core.sounds import play_internal_sound

logger = logging.getLogger(__name__)

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_KEY = "GCalIntegration"

# ============================================================
# Internal State
# ============================================================

_google_events = []       # Parsed from .ics (cached in memory)
_history_cache = {}
_sync_timer = None        # wx.Timer for periodic sync


# ============================================================
# Local Data Management
# ============================================================

def _load_local_data():
    """Load local events and hidden IDs from JSON storage."""
    data = core.api.load_data(DATA_KEY)
    return {
        "events": data.get("events", []),
        "hidden_ids": data.get("hidden_ids", []),
    }


def _save_local_data(local):
    """Persist local events and hidden IDs."""
    core.api.save_data(DATA_KEY, local)


def _add_local_event(event_dict):
    """Add an event to local storage."""
    local = _load_local_data()
    local["events"].append(event_dict)
    _save_local_data(local)
    logger.info(f"[GCal] Added local event: {event_dict.get('summary')}")


def _delete_event(event_id, silent=False):
    """
    Delete an event. If it's a local event, remove it entirely.
    If it's from Google, add its ID to the hidden list.
    """
    local = _load_local_data()

    # Extract base ID if it's a recurring instance (e.g., _r0)
    base_id = event_id.rsplit("_r", 1)[0] if "_r" in event_id else event_id

    # Try removing from local events
    original_len = len(local["events"])
    local["events"] = [e for e in local["events"] if e.get("id") not in (event_id, base_id)]

    if len(local["events"]) < original_len:
        # It was a local event — simply removed
        _save_local_data(local)
        if not silent:
            speak("Event deleted.", interrupt=True)
        return

    # Must be a Google event — hide it
    if event_id not in local["hidden_ids"]:
        local["hidden_ids"].append(event_id)
        _save_local_data(local)
    if not silent:
        speak("Event hidden from view. Note: it still exists in your Google Calendar.", interrupt=True)


def _update_local_event(event_id, updated_dict):
    """Update an existing local event by ID."""
    local = _load_local_data()
    for i, ev in enumerate(local["events"]):
        if ev.get("id") == event_id:
            local["events"][i] = updated_dict
            _save_local_data(local)
            return True
    return False


# ============================================================
# Google Calendar Sync
# ============================================================

# Over 120 countries and religious holidays supported by Google Calendar
# Mapped to their Google Calendar ID prefixes.
HOLIDAY_CALENDARS = {
    "None": "",
    "Christian Holidays": "en.christian",
    "Islamic Holidays": "en.islamic",
    "Jewish Holidays": "en.jewish",
    "Orthodox Holidays": "en.orthodox",
    "Afghanistan": "en.af",
    "Albania": "en.al",
    "Algeria": "en.dz",
    "Argentina": "en.ar",
    "Australia": "en.australian",
    "Austria": "en.austrian",
    "Bahrain": "en.bh",
    "Bangladesh": "en.bd",
    "Belgium": "en.be",
    "Bolivia": "en.bo",
    "Bosnia and Herzegovina": "en.ba",
    "Brazil": "en.brazilian",
    "Brunei": "en.bn",
    "Bulgaria": "en.bg",
    "Cambodia": "en.kh",
    "Canada": "en.canadian",
    "Chile": "en.cl",
    "China": "en.chinese",
    "Colombia": "en.co",
    "Costa Rica": "en.cr",
    "Croatia": "en.hr",
    "Czech Republic": "en.cz",
    "Denmark": "en.danish",
    "Dominican Republic": "en.do",
    "Ecuador": "en.ec",
    "Egypt": "en.eg",
    "El Salvador": "en.sv",
    "Estonia": "en.ee",
    "Finland": "en.fi",
    "France": "en.french",
    "Germany": "en.german",
    "Ghana": "en.gh",
    "Greece": "en.gr",
    "Guatemala": "en.gt",
    "Honduras": "en.hn",
    "Hong Kong": "en.hong_kong",
    "Hungary": "en.hu",
    "Iceland": "en.is",
    "India": "en.indian",
    "Indonesia": "id.indonesian", # Indonesian language holidays
    "Iran": "en.ir",
    "Iraq": "en.iq",
    "Ireland": "en.irish",
    "Israel": "en.israeli",
    "Italy": "en.italian",
    "Japan": "en.japanese",
    "Jordan": "en.jo",
    "Kazakhstan": "en.kz",
    "Kenya": "en.ke",
    "Kuwait": "en.kw",
    "Latvia": "en.lv",
    "Lebanon": "en.lb",
    "Lithuania": "en.lt",
    "Luxembourg": "en.lu",
    "Malaysia": "en.malaysia",
    "Mexico": "en.mexican",
    "Morocco": "en.ma",
    "Myanmar (Burma)": "en.mm",
    "Nepal": "en.np",
    "Netherlands": "en.dutch",
    "New Zealand": "en.new_zealand",
    "Nicaragua": "en.ni",
    "Nigeria": "en.ng",
    "North Macedonia": "en.mk",
    "Norway": "en.no",
    "Oman": "en.om",
    "Pakistan": "en.pk",
    "Panama": "en.pa",
    "Paraguay": "en.py",
    "Peru": "en.pe",
    "Philippines": "en.philippines",
    "Poland": "en.polish",
    "Portugal": "en.portuguese",
    "Puerto Rico": "en.pr",
    "Qatar": "en.qa",
    "Romania": "en.ro",
    "Russia": "en.russian",
    "Saudi Arabia": "en.saudi_arabian",
    "Senegal": "en.sn",
    "Serbia": "en.rs",
    "Singapore": "en.singapore",
    "Slovakia": "en.sk",
    "Slovenia": "en.si",
    "South Africa": "en.sa",
    "South Korea": "en.south_korea",
    "Spain": "en.spain",
    "Sri Lanka": "en.lk",
    "Sweden": "en.swedish",
    "Switzerland": "en.swiss",
    "Taiwan": "en.taiwan",
    "Tanzania": "en.tz",
    "Thailand": "en.thai",
    "Tunisia": "en.tn",
    "Turkey": "en.turkish",
    "Uganda": "en.ug",
    "Ukraine": "en.ua",
    "United Arab Emirates": "en.ae",
    "United Kingdom": "en.uk",
    "United States": "en.usa",
    "Uruguay": "en.uy",
    "Venezuela": "en.ve",
    "Vietnam": "en.vietnamese",
    "Zimbabwe": "en.zw"
}

def _get_ics_urls():
    """Get a list of .ics URLs from user config."""
    config = core.api.load_data(DATA_KEY)
    urls = []
    
    # Private URL
    private = config.get("ics_url", "").strip()
    if private:
        urls.append(private)
        
    # Public Holiday URL
    holiday = config.get("holiday_calendar", "None")
    if holiday in HOLIDAY_CALENDARS and HOLIDAY_CALENDARS[holiday]:
        prefix = HOLIDAY_CALENDARS[holiday]
        # Construct the full Google Calendar public ICS URL
        url = f"https://calendar.google.com/calendar/ical/{prefix}%23holiday%40group.v.calendar.google.com/public/basic.ics"
        urls.append(url)
        
    return urls


def _sync_google_calendar():
    """
    Download and parse the .ics file and historical data in a background thread.
    Updates the in-memory _google_events and _history_cache.
    """
    urls = _get_ics_urls()
    config = core.api.load_data(DATA_KEY)
    hist_country = config.get("history_country", "ID").strip()
    year = datetime.now().year

    def _fetch():
        from gcal_ics_parser import fetch_and_parse
        all_events = []
        if urls:
            for url in urls:
                try:
                    events = fetch_and_parse(url)
                    all_events.extend(events)
                except Exception as e:
                    logger.error(f"[GCal] Error fetching {url}: {e}")
                    
        # Fetch historical data
        history_data = {}
        if hist_country:
            # Holiday/history data snapshot on GitHub Pages (was hariku.novarealm.cloud).
            # NOTE: proper TLS verification (no more CERT_NONE bypass).
            url = f"https://infiartt.github.io/hariku/languages/data/{hist_country}.json"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Hariku/2.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        history_data = json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                logger.error(f"[GCal] Error fetching history from {url}: {e}")

        return all_events, history_data

    def _on_done(result):
        global _google_events, _history_cache
        events, history_data = result
        if events is not None:
            _google_events = events
        if history_data is not None:
            _history_cache = history_data
            
        # Save to persistent cache
        core.api.save_data("GCalIntegration_Cache", {"events": _google_events, "history": _history_cache})
        logger.info(f"[GCal] Synced {len(_google_events)} events and history for {year}.")

    core.api.run_thread(_fetch, _on_done)


# ============================================================
# Event Merging & Querying
# ============================================================

def _get_all_events_for_date(date_str):
    """
    Merge Google events + local events for the given date,
    excluding any hidden IDs.

    Returns a sorted list of event dicts.
    """
    from gcal_ics_parser import get_events_for_date

    local = _load_local_data()
    hidden_ids = set(local.get("hidden_ids", []))

    # Google events for this date (with recurrence expansion)
    google_for_date = get_events_for_date(_google_events, date_str)

    # Local events for this date
    local_for_date = get_events_for_date(local.get("events", []), date_str)

    # Merge and filter hidden
    merged = []
    for ev in google_for_date + local_for_date:
        # Skip hidden events (check both exact ID and base ID for recurrences)
        ev_id = ev.get("id", "")
        base_id = ev_id.rsplit("_r", 1)[0] if "_r" in ev_id else ev_id
        if ev_id in hidden_ids or base_id in hidden_ids:
            continue
        merged.append(ev)

    # Sort: all-day first, then by start_time
    def sort_key(e):
        if e.get("all_day"):
            return "0_" + e.get("start_time", "")
        return "1_" + e.get("start_time", "")

    merged.sort(key=sort_key)
    return merged


def _format_event_for_speech(ev):
    """Format a single event dict into a spoken string."""
    parts = []

    # Time
    if ev.get("all_day"):
        parts.append("All day:")
    else:
        start = ev.get("start_time", "")
        if len(start) >= 16:
            parts.append(start[11:16])

    # Title
    parts.append(ev.get("summary", "Untitled"))

    # Location
    loc = ev.get("location", "")
    if loc:
        parts.append(f"at {loc}")

    # Source indicator
    if ev.get("is_local"):
        parts.append("(local)")

    return " ".join(parts)


# ============================================================
# Event Handlers
# ============================================================

def _on_enter_pressed(payload):
    """
    Override the default Enter key behavior.
    Opens our full EventEditorDialog instead of the basic
    AddReminderDialog.
    """
    date_str = payload.get("date")
    if not date_str:
        return

    payload["handled"] = True  # Prevent default dialog

    from gcal_dialogs import EventEditorDialog

    parent = core.api.main_window_instance
    dlg = EventEditorDialog(parent, date_str)

    if dlg.ShowModal() == wx.ID_OK:
        result = dlg.get_result()
        if result:
            _add_local_event(result)
            speak(f"Event saved: {result.get('summary', '')}", interrupt=True)
            play_internal_sound("info.wav")

    dlg.Destroy()


def _on_fetch_agenda(payload):
    """
    Inject Google Calendar + local events into the agenda view.
    This runs when the user presses Space on a date.
    """
    date_str = payload.get("date")
    if not date_str:
        return

    merged = _get_all_events_for_date(date_str)

    for ev in merged:
        # Convert to the reminder format that agenda_dialog expects
        time_part = ""
        if not ev.get("all_day"):
            start = ev.get("start_time", "")
            if len(start) >= 16:
                time_part = start[11:16]

        title = ev.get("summary", "Untitled")
        loc = ev.get("location", "")
        if loc:
            title += f" at {loc}"

        source_tag = " [GCal]" if not ev.get("is_local") else " [Local]"
        title += source_tag

        reminder_item = {
            "id": ev.get("id", ""),
            "title": title,
            "date": date_str,
            "time": time_part,
            "is_done": False,
        }
        payload["reminders"].append(reminder_item)


def _read_events_for_today(tap_count=1):
    """
    Hotkey callback: read events for the currently selected date.
    Tap 1: read event count and first event
    Tap 2: read all events
    """
    date_str = core.api.get_selected_date()
    if not date_str:
        speak("No date selected.", interrupt=True)
        return

    events = _get_all_events_for_date(date_str)

    if not events:
        speak("No events for this date.", interrupt=True)
        return

    if tap_count == 1:
        count = len(events)
        first = _format_event_for_speech(events[0])
        speak(f"{count} event{'s' if count != 1 else ''}. Next: {first}", interrupt=True)
    else:
        # Read all events
        lines = []
        for ev in events:
            lines.append(_format_event_for_speech(ev))
        speak(". ".join(lines), interrupt=True)


def _delete_selected_event():
    """
    Hotkey callback: show a list of events for today and let
    the user choose one to delete/hide.
    """
    date_str = core.api.get_selected_date()
    if not date_str:
        speak("No date selected.", interrupt=True)
        return

    events = _get_all_events_for_date(date_str)

    if not events:
        speak("No events to delete for this date.", interrupt=True)
        return

    # Show a choice dialog
    choices = []
    for ev in events:
        label = _format_event_for_speech(ev)
        choices.append(label)

    parent = core.api.main_window_instance
    dlg = wx.SingleChoiceDialog(
        parent,
        "Select an event to delete:",
        "Delete Event",
        choices,
    )

    if dlg.ShowModal() == wx.ID_OK:
        idx = dlg.GetSelection()
        if 0 <= idx < len(events):
            _delete_event(events[idx].get("id", ""))

    dlg.Destroy()


def _edit_selected_event():
    """
    Hotkey callback: show a list of local events for today and
    let the user choose one to edit.
    """
    date_str = core.api.get_selected_date()
    if not date_str:
        speak("No date selected.", interrupt=True)
        return

    events = _get_all_events_for_date(date_str)
    # Filter to only local events (Google events can't be edited)
    editable = [e for e in events if e.get("is_local")]

    if not editable:
        speak("No editable events for this date. Only local events can be edited.", interrupt=True)
        return

    choices = [_format_event_for_speech(ev) for ev in editable]

    parent = core.api.main_window_instance
    dlg = wx.SingleChoiceDialog(
        parent,
        "Select an event to edit:",
        "Edit Event",
        choices,
    )

    if dlg.ShowModal() == wx.ID_OK:
        idx = dlg.GetSelection()
        if 0 <= idx < len(editable):
            selected = editable[idx]
            from gcal_dialogs import EventEditorDialog
            edit_dlg = EventEditorDialog(parent, date_str, event_data=selected)
            if edit_dlg.ShowModal() == wx.ID_OK:
                result = edit_dlg.get_result()
                if result:
                    _update_local_event(selected["id"], result)
                    speak(f"Event updated: {result.get('summary', '')}", interrupt=True)
            edit_dlg.Destroy()

    dlg.Destroy()


def _force_sync():
    """Hotkey callback: manually trigger a sync from Google."""
    urls = _get_ics_urls()
    if not urls:
        speak("Please configure a Google Calendar URL in settings first.", interrupt=True)
        return
    speak("Syncing with Google Calendar...", interrupt=True)
    _sync_google_calendar()


def _import_v1_events(evt=None):
    """Import events from Hariku V1."""
    import os
    import json
    import uuid
    v1_path = os.path.expandvars(r"%APPDATA%\inflinity\hariku\user_events.json")
    if not os.path.exists(v1_path):
        core.api.show_message("Import V1", "Hariku V1 data file not found at:\n" + v1_path)
        return

    try:
        with open(v1_path, "r", encoding="utf-8") as f:
            v1_data = json.load(f)
    except Exception as e:
        logger.error(f"[GCal] Error reading V1 data: {e}")
        core.api.show_message("Import V1", "Error reading V1 data file.")
        return

    local = _load_local_data()
    count = 0

    # Import specific events
    for date_str, ev in v1_data.get("specific", {}).items():
        event_dict = {
            "id": f"v1_specific_{uuid.uuid4().hex[:8]}",
            "summary": ev.get("name", "V1 Event"),
            "start_time": f"{date_str}T00:00:00",
            "all_day": True,
            "is_local": True
        }
        local["events"].append(event_dict)
        count += 1

    # Import recurring events
    year = datetime.now().year
    for mm_dd, ev in v1_data.get("recurring", {}).items():
        event_dict = {
            "id": f"v1_recurring_{uuid.uuid4().hex[:8]}",
            "summary": ev.get("name", "V1 Event"),
            "start_time": f"{year}-{mm_dd}T00:00:00",
            "all_day": True,
            "is_local": True,
            "recurrence": "FREQ=YEARLY"
        }
        local["events"].append(event_dict)
        count += 1

    _save_local_data(local)
    core.api.show_message("Import V1", f"Successfully imported {count} events from Hariku V1!")


# ============================================================
# Settings Panel
# ============================================================

class GCalSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        vbox = wx.BoxSizer(wx.VERTICAL)

        config = core.api.load_data(DATA_KEY)

        warn = wx.StaticText(
            self,
            label=(
                "Note: This is a one-way integration. Events added or edited "
                "in Hariku are saved locally only and will NOT sync back to "
                "Google Calendar."
            ),
        )
        warn.Wrap(400)
        vbox.Add(warn, 0, wx.ALL, 10)

        vbox.Add(
            wx.StaticText(self, label="Private iCal URL (.ics):"),
            0, wx.LEFT | wx.TOP, 10,
        )
        self.txt_url = wx.TextCtrl(self, value=config.get("ics_url", ""))
        vbox.Add(self.txt_url, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        help_text = wx.StaticText(
            self,
            label=(
                "To find this URL: Open Google Calendar on the web → "
                "Settings → select your calendar → Integrate Calendar → "
                "copy 'Secret address in iCal format'."
            ),
        )
        help_text.Wrap(400)
        vbox.Add(help_text, 0, wx.ALL, 10)

        vbox.Add(
            wx.StaticText(self, label="Historical Data Country Code (e.g. ID, US):"),
            0, wx.LEFT | wx.TOP, 10,
        )
        self.txt_hist = wx.TextCtrl(self, value=config.get("history_country", "ID"))
        vbox.Add(self.txt_hist, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        vbox.Add(
            wx.StaticText(self, label="Public Holidays Calendar:"),
            0, wx.LEFT | wx.TOP, 10,
        )
        self.choices = list(HOLIDAY_CALENDARS.keys())
        self.cb_holidays = wx.Choice(self, choices=self.choices)
        
        current_holiday = config.get("holiday_calendar", "None")
        if current_holiday in self.choices:
            self.cb_holidays.SetSelection(self.choices.index(current_holiday))
        else:
            self.cb_holidays.SetSelection(0)
            
        vbox.Add(self.cb_holidays, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        vbox.AddSpacer(15)
        btn_import = wx.Button(self, label="Import Events from Hariku V1")
        btn_import.Bind(wx.EVT_BUTTON, _import_v1_events)
        vbox.Add(btn_import, 0, wx.ALL | wx.CENTER, 10)

        self.SetSizer(vbox)

    def ApplyChanges(self):
        config = core.api.load_data(DATA_KEY)
        
        # Sanitize URL by removing all newlines/carriage returns and trimming spaces
        raw_url = self.txt_url.GetValue()
        new_url = raw_url.replace("\n", "").replace("\r", "").strip()
        
        new_holiday = self.cb_holidays.GetStringSelection()
        new_hist = self.txt_hist.GetValue().strip().upper()
        
        old_url = config.get("ics_url", "")
        old_holiday = config.get("holiday_calendar", "None")
        old_hist = config.get("history_country", "ID")
        
        config["ics_url"] = new_url
        config["holiday_calendar"] = new_holiday
        config["history_country"] = new_hist
        
        core.api.save_data(DATA_KEY, config)
        
        # If any URL changed, trigger a new sync
        if (new_url != old_url or new_holiday != old_holiday or new_hist != old_hist):
            _sync_google_calendar()


_panel_instance = None


def _create_panel(parent):
    global _panel_instance
    _panel_instance = GCalSettingsPanel(parent)
    return _panel_instance


def _apply_panel():
    if _panel_instance:
        _panel_instance.ApplyChanges()


def _show_historical_info():
    """Hotkey callback: Show historical info for the selected date."""
    date_str = core.api.get_selected_date()
    if not date_str:
        return
        
    events = _get_all_events_for_date(date_str)
    if not events:
        speak("No historical info available for this date.", interrupt=True)
        return
        
    # Check if there is history for this date in the cache
    specific_events = _history_cache.get("specific_date_events", {})
    recurring_events = _history_cache.get("recurring_events", {})
    
    date_parts = date_str.split("-")
    mm_dd = f"{date_parts[1]}-{date_parts[2]}"
    
    history_text = ""
    # Check specific dates first (e.g. 2026-05-02)
    if date_str in specific_events:
        history_text = specific_events[date_str].get("history", "").strip()
        
    # Then check recurring dates (e.g. 05-02) if not found
    if not history_text and mm_dd in recurring_events:
        history_text = recurring_events[mm_dd].get("history", "").strip()
        
    if history_text:
        event_name = events[0].get("summary", "Event")
        html = f"<html><body><h1>History for: {event_name}</h1><p>{history_text}</p></body></html>"
        core.api.show_html_view(html, title="Historical Information", width=600, height=400)
    else:
        speak("No historical info available for this date.", interrupt=True)

def _on_agenda_item_deleted(event_id):
    """Callback when an item is deleted via the main Agenda UI."""
    _delete_event(event_id, silent=True)

# ============================================================
# Lifecycle: register()
# ============================================================

def register(bus):
    logger.info("[GCal] Google Calendar Reader extension loaded.")

    # --- Subscribe to lifecycle events ---
    bus.subscribe("on_app_startup", _on_app_startup)
    bus.subscribe("on_enter_pressed", _on_enter_pressed)
    bus.subscribe("on_fetch_agenda", _on_fetch_agenda)
    bus.subscribe("on_agenda_item_deleted", _on_agenda_item_deleted)

    # --- Register hotkeys ---
    core.hotkeys.register_action(
        "Google Calendar", "read_events",
        "Read events for selected date (tap twice for all)",
        ord("C"), False, _read_events_for_today,
        default_shift=True,
    )
    
    core.hotkeys.register_action(
        "Google Calendar", "show_history",
        "View Historical Context",
        ord("I"), False, _show_historical_info,
    )

    core.hotkeys.register_action(
        "Google Calendar", "add_event",
        "Add a new event",
        ord("A"), False, lambda: _on_enter_pressed({"date": core.api.get_selected_date(), "handled": False}),
        default_shift=True,
    )

    core.hotkeys.register_action(
        "Google Calendar", "edit_event",
        "Edit a local event",
        ord("E"), False, _edit_selected_event,
        default_shift=True,
    )

    core.hotkeys.register_action(
        "Google Calendar", "delete_event",
        "Delete or hide an event",
        None, False, _delete_selected_event,
    )

    core.hotkeys.register_action(
        "Google Calendar", "sync_now",
        "Sync with Google Calendar now",
        None, False, _force_sync,
    )

    # --- Register settings panel ---
    core.preferences.register_panel(
        "Google Calendar", "", _create_panel, _apply_panel
    )


def _on_app_startup():
    """Run initial sync when Hariku starts."""
    global _sync_timer, _google_events, _history_cache

    # Load cache immediately so events are available before sync finishes
    cached = core.api.load_data("GCalIntegration_Cache")
    if cached:
        _google_events = cached.get("events", [])
        _history_cache = cached.get("history", {})

    urls = _get_ics_urls()
    if urls:
        # Initial sync after 3 seconds (let the UI settle)
        wx.CallLater(3000, _sync_google_calendar)

        # Periodic sync every 60 minutes
        _sync_timer = core.api.set_interval(3600000, _sync_google_calendar)

    logger.info("[GCal] Startup complete.")


def teardown():
    """Called when the extension is unloaded."""
    global _sync_timer
    if _sync_timer:
        try:
            _sync_timer.Stop()
        except Exception:
            pass
    logger.info("[GCal] Extension unloaded.")
