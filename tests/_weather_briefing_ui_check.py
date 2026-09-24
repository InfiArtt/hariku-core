# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Weather and Morning Briefing extensions through the real loader with
real wxPython, open every window they add, run their hotkey actions, and browse
their lists the way arrow keys do, checking focus stays put. Also the place
Weather uses (core 2.8 Places): the main place, or a city of its own, and the
page following the places while it is open.

Open-Meteo is stubbed (nothing leaves the machine) and speech is captured
through on_before_speak instead of reaching the screen reader.

Run by tests/test_weather_briefing_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder so the user's real settings are never touched. Prints one "OK"
line per stage.
"""
import datetime
import logging
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# Any real request fails, and is remembered so the check can fail on it.
import urllib.request

network_attempts = []


def _blocked_urlopen(*args, **kwargs):
    network_attempts.append(args[0] if args else kwargs)
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked_urlopen

# Exceptions in wx event handlers are printed, not raised; collect them.
problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    WATCHED = ("hariku_ext.weather", "hariku_ext.briefing", "weather_", "briefing_",
               "core.events", "core.hotkeys", "core.extension_manager", "ui.preferences_dialog")

    def emit(self, record):
        if record.name.startswith(self.WATCHED):
            problems.append(f"logged by {record.name}: {record.getMessage()}")


logging.getLogger().addHandler(_ErrorLog(level=logging.ERROR))

import wx

app = wx.App(False)

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()
import core.api
import core.reminders
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

from ui.main_window import MainWindow
frame = MainWindow(None, title="weather and briefing check")
print("OK main_window")

# Replace the Open-Meteo fetch before the extension imports its helpers.
WEATHER_DIR = os.path.join(ROOT, "extensions", "weather")
BRIEFING_DIR = os.path.join(ROOT, "extensions", "briefing")
sys.path.insert(0, WEATHER_DIR)
import weather_api

TODAY = datetime.date.today()
_local_offset = int(datetime.datetime.now().astimezone().utcoffset().total_seconds())
FORECAST = {
    "utc_offset_seconds": _local_offset, "timezone": "Asia/Jakarta",
    "current": {"time": f"{TODAY.isoformat()}T08:15", "temperature_2m": 27.3,
                "relative_humidity_2m": 84, "apparent_temperature": 31.2,
                "weather_code": 61, "wind_speed_10m": 5.4},
    "daily": {"time": [(TODAY + datetime.timedelta(days=i)).isoformat() for i in range(7)],
              "weather_code": [61, 3, 95, 0, 1, 2, 80],
              "temperature_2m_max": [31.0, 32.4, 30.1, 31.5, 32.0, 30.8, 29.9],
              "temperature_2m_min": [24.0, 24.6, 23.8, 24.1, 24.4, 23.9, 23.5],
              "precipitation_probability_max": [80, 10, None, 5, 0, 20, 65]},
}
PLACES = {"results": [
    {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
     "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"},
    {"name": "Jakarta", "admin1": "West Virginia", "country": "United States",
     "latitude": 38.1, "longitude": -80.2, "timezone": "America/New_York"},
]}
stub_requests = []


def _fake_fetch_json(url):
    stub_requests.append(url)
    if url.startswith(weather_api.GEOCODING_URL):
        return PLACES
    if url.startswith(weather_api.FORECAST_URL):
        return FORECAST
    raise AssertionError(f"unexpected URL {url}")


weather_api.fetch_json = _fake_fetch_json

import core.extension_manager as em
em.load_unpacked_extension(WEATHER_DIR)
em.load_unpacked_extension(BRIEFING_DIR)
assert "weather" in em.LOADED_EXTENSIONS, "Weather extension did not load"
assert "briefing" in em.LOADED_EXTENSIONS, "Morning Briefing extension did not load"
weather = em.LOADED_EXTENSIONS["weather"]["module"]
briefing = em.LOADED_EXTENSIONS["briefing"]["module"]
weather_text = sys.modules["weather_text"]
weather_ui = sys.modules["weather_ui"]
assert sys.modules["weather_api"] is weather_api
print("OK load_extensions")


def pump(condition, timeout=5.0):
    """Process events until condition() is true or the timeout passes. Runs an
    event loop of its own: wx.Yield() alone never delivers timer events here."""
    loop = wx.GUIEventLoop()
    previous = wx.EventLoop.GetActive()
    wx.EventLoop.SetActive(loop)
    try:
        end = time.time() + timeout
        while True:
            while loop.Pending():
                loop.Dispatch()
            app.ProcessPendingEvents()
            if condition():
                return True
            if time.time() > end:
                return False
            time.sleep(0.02)
    finally:
        wx.EventLoop.SetActive(previous)


def run_and_close(action_id):
    """Run a hotkey action; close any modal dialog it opens. Returns the dialogs."""
    opened = []

    def close_modal():
        for w in wx.GetTopLevelWindows():
            if isinstance(w, wx.Dialog) and w.IsModal():
                opened.append(type(w).__name__)
                w.EndModal(wx.ID_CANCEL)

    timer = wx.CallLater(700, close_modal)
    core.hotkeys.actions[action_id].callback()
    timer.Stop()
    return opened


def fire(ctrl, event_type, index=None):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    if index is not None:
        evt.SetInt(index)
    ctrl.GetEventHandler().ProcessEvent(evt)
    wx.Yield()


def browse(ctrl, event_type):
    """Select every item and fire its selection event, as arrow keys do. Focus
    must stay on the control. Returns whether focus could be observed here."""
    ctrl.SetFocus()
    wx.Yield()
    observable = wx.Window.FindFocus() is ctrl
    assert ctrl.GetCount() > 0, "nothing to browse"
    for i in range(ctrl.GetCount()):
        ctrl.SetSelection(i)
        fire(ctrl, event_type, i)
        if observable:
            assert wx.Window.FindFocus() is ctrl, f"focus left the list at item {i}"
    return observable


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


_ = weather_text._
NO_LOCATION = _("no_location")

# --- Weather without a city: a spoken hint, no window -------------------------
spoken.clear()
assert run_and_close("Weather.speak_current_weather") == []
assert run_and_close("Weather.show_forecast") == []
assert spoken == [NO_LOCATION, NO_LOCATION], spoken
print("OK weather_no_city_hint")

# --- Preferences page: the place choice, search, browse, save -------------------
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Weather")
prefs.Show()
wx.Yield()
panel = weather._panel
assert panel is not None and panel.IsShown(), "Weather settings page was not created"
choice = panel.place_choice.ctrl
assert choice.GetName() == "Place", choice.GetName()
# No places yet (core 2.8): the main place says where to add one.
assert choice.GetStrings() == ["The main place (none yet: add one in Preferences, Places)",
                               "Its own place\u2026"], choice.GetStrings()
assert panel.place_choice.key() == "main" and choice.GetSelection() == 0
assert panel.txt_location.GetValue() == _("location_not_set")
# The city search is for its own place only: skipped while another place is chosen.
assert not panel.txt_location.IsEnabled() and not panel.txt_search.IsEnabled()
assert not panel.btn_search.IsEnabled() and not panel.list_results.IsEnabled()
labels = [w.GetLabel() for w in panel.GetChildren() if isinstance(w, wx.StaticText)]
assert "Weather data by Open-Meteo.com" in labels, labels
assert any("rounded to about 1 kilometre" in label for label in labels), labels
# Arrowing through the places: focus stays; the last one, "Its own place", opens the search.
checked = browse(choice, wx.EVT_CHOICE)
assert panel.place_choice.key() == "own", panel.place_choice.key()
assert panel.txt_search.IsEnabled() and panel.btn_search.IsEnabled()
assert panel.list_results.IsEnabled()

panel.txt_search.SetValue("J")
fire(panel.txt_search, wx.EVT_TEXT_ENTER)
assert spoken[-1] == _("search_too_short"), spoken[-1]

panel.txt_search.SetValue("Jakarta")
panel.txt_search.SetFocus()
wx.Yield()
search_focused = wx.Window.FindFocus() is panel.txt_search
fire(panel.txt_search, wx.EVT_TEXT_ENTER)
assert pump(lambda: panel.list_results.GetCount() == 2), "search results never arrived"
assert panel.list_results.GetString(0) == "Jakarta, Indonesia"
if search_focused:
    assert wx.Window.FindFocus() is panel.list_results, "focus did not move to the results"
checked = browse(panel.list_results, wx.EVT_LISTBOX) and checked
checked = browse(panel.choice_units, wx.EVT_CHOICE) and checked

# Back to the main place and to its own place again: the search follows.
choice.SetSelection(0)
fire(choice, wx.EVT_CHOICE, 0)
assert panel.place_choice.key() == "main" and not panel.txt_search.IsEnabled()
assert not panel.list_results.IsEnabled()
choice.SetSelection(1)
fire(choice, wx.EVT_CHOICE, 1)
assert panel.place_choice.key() == "own" and panel.txt_search.IsEnabled()
assert panel.list_results.IsEnabled()
print(f"OK weather_panel_browse ({focus_note(checked)})")


def forecast_requests():
    return [u for u in stub_requests if u.startswith(weather_api.FORECAST_URL)]


panel.list_results.SetSelection(0)
panel.choice_units.SetSelection(0)
prefs.OnApply(None)
saved = core.api.load_data("Weather")
assert saved["place"] == "own", saved
assert saved["location"]["name"] == "Jakarta" and saved["location"]["country"] == "Indonesia", saved
assert saved["units"] == "metric"
assert pump(lambda: weather.current_cache() is not None), "forecast was not fetched after saving"
# Only ever the rounded point (core 2.8): Jakarta is -6.21, 106.85.
assert "latitude=-6.21&longitude=106.85&" in forecast_requests()[-1], forecast_requests()
assert panel.txt_location.GetValue() == "Jakarta, Indonesia"
prefs.Destroy()
wx.Yield()
print("OK weather_panel_apply")

# --- The places change while the page is open: the list follows, the choice stays -
import core.places

prefs = PreferencesDialog(frame, select_tab="Weather")
prefs.Show()
wx.Yield()
panel = weather._panel
choice = panel.place_choice.ctrl
assert panel.place_choice.key() == "own" and panel.txt_search.IsEnabled()
assert panel.txt_location.GetValue() == "Jakarta, Indonesia"
choice.SetFocus()
wx.Yield()
choice_focused = wx.Window.FindFocus() is choice
before = len(stub_requests)
core.places.set_places([{                          # what the Places page does on OK
    "name": "Home", "lat": -6.9175, "lon": 107.6191,
    "label": "Bandung, West Java, Indonesia", "timezone": "Asia/Jakarta", "source": "city",
    "city": "Bandung", "region": "West Java", "country": "Indonesia"}])
assert choice.GetStrings() == ["The main place (Home)", "Home", "Its own place\u2026"], \
    choice.GetStrings()
assert panel.place_choice.key() == "own" and choice.GetSelection() == 2
assert panel.txt_search.IsEnabled()
if choice_focused:
    assert wx.Window.FindFocus() is choice, "focus moved when the places changed"
pump(lambda: False, timeout=0.3)
assert len(stub_requests) == before, "its own city is in use: nothing to fetch"
# Choosing the main place skips its own search again, and is what OK saves.
choice.SetSelection(0)
fire(choice, wx.EVT_CHOICE, 0)
assert panel.place_choice.key() == "main" and not panel.txt_search.IsEnabled()
if choice_focused:
    assert wx.Window.FindFocus() is choice, "focus moved when choosing a place"
prefs.OnApply(None)
saved = core.api.load_data("Weather")
assert saved["place"] == "main", saved
assert saved["location"]["name"] == "Jakarta", "its own city is kept for later"
assert weather.get_location()["name"] == "Home"
assert pump(lambda: weather.current_cache() is not None and not weather._loading), \
    "the main place was not fetched"
assert "latitude=-6.92&longitude=107.62&" in forecast_requests()[-1], forecast_requests()
# The place's name is what Weather says and shows.
spoken.clear()
assert run_and_close("Weather.speak_current_weather") == []
assert spoken and spoken[-1].startswith("Home: Light rain, 27 degrees"), spoken
dlg = weather_ui.ForecastDialog(frame, weather.get_location(), weather.get_units(),
                                weather.current_cache, weather.refresh)
assert dlg.list_days.GetName() == "Daily forecast for Home, temperatures in degrees Celsius:", \
    dlg.list_days.GetName()
dlg.Destroy()
wx.Yield()
# Back to its own city for the checks below.
panel.place_choice.set_key("own")
panel._update_own()
prefs.OnApply(None)
assert core.api.load_data("Weather")["place"] == "own"
assert pump(lambda: weather.current_cache() is not None and not weather._loading), \
    "its own city was not fetched again"
assert weather.get_location()["name"] == "Jakarta"
prefs.Destroy()
wx.Yield()
print(f"OK weather_places_changed ({focus_note(choice_focused)})")

# --- Weather actions with a city ------------------------------------------------
spoken.clear()
assert run_and_close("Weather.speak_current_weather") == []
assert spoken and spoken[-1].startswith("Jakarta: Light rain, 27 degrees"), spoken
assert run_and_close("Weather.show_forecast") == ["ForecastDialog"]
print("OK weather_actions")

# --- Forecast window: browse the days, refresh, close during a fetch -------------
dlg = weather_ui.ForecastDialog(frame, weather.get_location(), weather.get_units(),
                                weather.current_cache, weather.refresh)
dlg.Show()
wx.Yield()
assert dlg.list_days.GetCount() == 7, dlg.list_days.GetCount()
assert dlg.list_days.GetString(0).startswith("Today, ")
checked = browse(dlg.list_days, wx.EVT_LISTBOX)
spoken.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert pump(lambda: _("forecast_updated") in spoken), spoken
dlg.Destroy()
wx.Yield()

dlg = weather_ui.ForecastDialog(frame, weather.get_location(), weather.get_units(),
                                weather.current_cache, weather.refresh, refresh_now=True)
dlg.Destroy()
assert pump(lambda: not weather._loading), "fetch never finished"
print(f"OK weather_forecast_browse ({focus_note(checked)})")

# --- Morning Briefing: the action, with a reminder and the weather ---------------
core.reminders.add_reminder("Team meeting", TODAY.isoformat(), "09:00")
spoken.clear()
core.hotkeys.actions["Morning Briefing.play_briefing"].callback()
assert len(spoken) == 1, spoken
text = spoken[0]
assert text.startswith(("Good morning.", "Good day.", "Good afternoon.", "Good evening.")), text
assert "Today is " in text, text
assert "You have 1 reminder today. 09:00, Team meeting." in text, text
assert text.endswith("Weather in Jakarta: Light rain, 27 degrees, high 31, low 24, "
                     "80 percent chance of rain."), text
print("OK briefing_action")

# --- The evening summary (Shift+B), with tomorrow's weather ----------------------
evening = core.hotkeys.actions["Morning Briefing.evening_summary"]
assert evening.default_keycode == ord("B") and evening.default_shift and not evening.default_ctrl
spoken.clear()
evening.callback()
assert len(spoken) == 1, spoken
text = spoken[0]
assert text.startswith(("Good morning.", "Good day.", "Good afternoon.", "Good evening.")), text
assert ("You finished 0 of 1 reminders today. Not done yet: 09:00, Team meeting. "
        "You have no reminders tomorrow. Tomorrow: overcast, 32 degrees.") in text, text
print("OK briefing_evening")

# --- Briefing preferences and the once-a-day automatic briefing ------------------
prefs = PreferencesDialog(frame, select_tab="Morning Briefing")
prefs.Show()
wx.Yield()
bpanel = briefing._panel
assert bpanel is not None and bpanel.IsShown(), "Briefing settings page was not created"
assert bpanel.chk_auto.GetValue() is False
# Minute ticks come from this check only, so the real clock can't start the
# automatic evening summary in between.
frame.heartbeat_timer.Stop()
assert bpanel.chk_evening.GetValue() is False                 # off by default
assert bpanel.choice_evening_time.GetName() == "Time of the evening summary"
assert bpanel.choice_evening_time.GetStringSelection() == "20:00"
checked = browse(bpanel.choice_evening_time, wx.EVT_CHOICE)
bpanel.chk_auto.SetValue(True)
bpanel.chk_evening.SetValue(True)
bpanel.choice_evening_time.SetSelection(bpanel.choice_evening_time.FindString("21:30"))
prefs.OnApply(None)
saved = core.api.load_data("Briefing")
assert saved["auto_first_start"] is True
assert saved["evening_auto"] is True and saved["evening_time"] == "21:30", saved
prefs.Destroy()
wx.Yield()
print(f"OK briefing_evening_settings ({focus_note(checked)})")

# The automatic evening summary plays once when its time has come.
spoken.clear()
late = datetime.datetime.combine(TODAY, datetime.time(21, 29))
bus.emit("on_minute_tick", late)
assert spoken == [], spoken
bus.emit("on_minute_tick", late + datetime.timedelta(minutes=1))
bus.emit("on_minute_tick", late + datetime.timedelta(minutes=2))
assert len(spoken) == 1 and "You finished 0 of 1 reminders today." in spoken[0], spoken
assert core.api.load_data("Briefing")["last_evening_date"] == TODAY.isoformat()
print("OK briefing_evening_auto")

briefing.AUTO_DELAY_MS = 50
spoken.clear()
bus.emit("on_app_startup")
assert pump(lambda: len(spoken) >= 1), "automatic briefing did not play"
assert core.api.load_data("Briefing")["last_auto_date"] == TODAY.isoformat()
bus.emit("on_app_startup")
pump(lambda: False, timeout=0.3)
assert len(spoken) == 1, spoken
print("OK briefing_auto")

# --- Teardown, and nothing went wrong along the way ------------------------------
em.unload_all_extensions()
assert weather._on_minute_tick not in bus._listeners.get("on_minute_tick", [])
assert weather._on_briefing_collect not in bus._listeners.get("on_briefing_collect", [])
assert weather._on_places_changed not in bus._listeners.get("on_places_changed", [])
assert briefing._on_app_startup not in bus._listeners.get("on_app_startup", [])
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
assert all(u.startswith(("https://api.open-meteo.com/", "https://geocoding-api.open-meteo.com/"))
           for u in stub_requests), stub_requests
# Open-Meteo only ever got a point rounded to 2 decimals, about 1 km (core 2.8).
import urllib.parse
for url in forecast_requests():
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    for name in ("latitude", "longitude"):
        assert len(query[name][0].split(".")[1]) == 2, url
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
