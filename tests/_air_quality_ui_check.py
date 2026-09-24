# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Air Quality extension through the real loader with real wxPython,
open its settings page inside the real Preferences dialog and its forecast
window, run its hotkey actions, and browse every list the way arrow keys do,
checking focus stays put.

Open-Meteo is stubbed (nothing leaves the machine), speech is captured through
on_before_speak, and sounds are recorded instead of played.

Run by tests/test_air_quality_ui.py in a separate process, because conftest.py
mocks wx inside the pytest process. The caller points APPDATA at a temporary
folder so the user's real settings are never touched. Prints one "OK" line per
stage.
"""
import datetime
import logging
import math
import os
import sys
import threading
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the air quality check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(150, _watchdog)
_timer.daemon = True
_timer.start()

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
    WATCHED = ("hariku_ext.air_quality", "air_quality_", "core.events", "core.hotkeys",
               "core.extension_manager", "ui.preferences_dialog")

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
import core.sounds
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)
sounds = []
core.sounds.play_internal_sound = lambda name: sounds.append(name) or True

from ui.main_window import MainWindow
frame = MainWindow(None, title="air quality check")
print("OK main_window")

PLAIN_U = (ord("U"), False, False, False, False)
SHIFT_U = (ord("U"), False, True, False, False)
assert PLAIN_U not in core.hotkeys.keybindings, "U is already bound by the core"
assert SHIFT_U not in core.hotkeys.keybindings, "Shift+U is already bound by the core"

# Replace the Open-Meteo fetch before the extension imports its helpers.
AIR_DIR = os.path.join(ROOT, "extensions", "air_quality")
sys.path.insert(0, AIR_DIR)
import air_quality_api

# Five days of hourly data from today 00:00 in this computer's time zone, so
# the coming hours exist whenever the check runs.
TODAY = datetime.date.today()
_local_offset = int(datetime.datetime.now().astimezone().utcoffset().total_seconds())
_start = datetime.datetime.combine(TODAY, datetime.time())
HOURS = [(_start + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(5 * 24)]
AIR = {
    "utc_offset_seconds": _local_offset, "timezone": "Asia/Jakarta",
    "current": {"time": datetime.datetime.now().strftime("%Y-%m-%dT%H:00"), "interval": 3600,
                "us_aqi": 231, "pm2_5": 102.4, "pm10": 103.6, "uv_index": 0.0,
                "us_aqi_pm2_5": 190, "us_aqi_pm10": 79, "us_aqi_ozone": 231,
                "us_aqi_nitrogen_dioxide": 53, "us_aqi_carbon_monoxide": 14,
                "us_aqi_sulphur_dioxide": 32},
    "hourly": {
        "time": HOURS,
        "us_aqi": [150 + (i * 7) % 90 for i in range(len(HOURS))],
        "pm2_5": [60.0 + (i * 13) % 150 for i in range(len(HOURS))],
        "uv_index": [max(0.0, round(9 * math.sin(math.pi * ((i % 24) - 6) / 12), 2))
                     for i in range(len(HOURS))],
    },
}
PLACES = {"results": [
    {"name": "Bandung", "admin1": "West Java", "country": "Indonesia",
     "latitude": -6.9175, "longitude": 107.6191, "timezone": "Asia/Jakarta"},
    {"name": "Bandung", "admin1": "Banten", "country": "Indonesia",
     "latitude": -6.2, "longitude": 106.3, "timezone": "Asia/Jakarta"},
]}
JAKARTA = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
           "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"}
stub_requests = []


def _fake_fetch_json(url):
    stub_requests.append(url)
    if url.startswith(air_quality_api.GEOCODING_URL):
        return PLACES
    if url.startswith(air_quality_api.AIR_URL):
        return AIR
    raise AssertionError(f"unexpected URL {url}")


air_quality_api.fetch_json = _fake_fetch_json

import core.extension_manager as em
em.load_unpacked_extension(AIR_DIR)
assert "air_quality" in em.LOADED_EXTENSIONS, "Air Quality did not load"
main = em.LOADED_EXTENSIONS["air_quality"]["module"]
air_ui = sys.modules["air_quality_ui"]
air_text = sys.modules["air_quality_text"]
assert sys.modules["air_quality_api"] is air_quality_api
assert core.hotkeys.keybindings[PLAIN_U][0] == "Air Quality.speak_air"
assert core.hotkeys.keybindings[SHIFT_U][0] == "Air Quality.show_forecast"
print("OK load")


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
            assert wx.Window.FindFocus() is ctrl, f"focus left {ctrl.GetName()} at item {i}"
    return observable


def toggle(checkbox):
    """Tick and untick a checkbox; focus must stay on it."""
    checkbox.SetFocus()
    wx.Yield()
    observable = wx.Window.FindFocus() is checkbox
    for value in (not checkbox.GetValue(), checkbox.GetValue()):
        checkbox.SetValue(value)
        fire(checkbox, wx.EVT_CHECKBOX, int(value))
        if observable:
            assert wx.Window.FindFocus() is checkbox, f"focus left {checkbox.GetLabel()}"
    return observable


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


def said(prefix):
    return any(s.startswith(prefix) for s in spoken)


_ = air_text._
NO_LOCATION = _("no_location")
TIP = _("tip_very_unhealthy")

# --- Without a city: a spoken hint, no window -----------------------------------------
spoken.clear()
assert run_and_close("Air Quality.speak_air") == []
assert run_and_close("Air Quality.show_forecast") == []
assert spoken == [NO_LOCATION, NO_LOCATION], spoken
print("OK no_location_hint")

# --- The main place (Preferences, Places) is the default ---------------------------------
import core.places
core.api.save_data("Weather", {"location": JAKARTA, "units": "metric"})
assert main.get_location() is None, "the Weather city is no longer used by itself"
jakarta_place, = core.places.set_places([{
    "name": "Jakarta", "lat": JAKARTA["latitude"], "lon": JAKARTA["longitude"],
    "label": "Jakarta, Indonesia", "timezone": "Asia/Jakarta", "source": "city",
    "city": "Jakarta", "region": "Jakarta", "country": "Indonesia"}])
assert main.get_location()["name"] == "Jakarta"
spoken.clear()
assert run_and_close("Air Quality.speak_air") == []
assert spoken[0] == _("fetching"), spoken
assert pump(lambda: len(spoken) >= 2), spoken
assert spoken[-1] == ("Jakarta: Air quality index 231, very unhealthy, mostly ozone. "
                      "PM2.5 102, PM10 104 micrograms per cubic metre. UV index 0, low. " + TIP), spoken
assert sounds == [], "no alert while the alert is off"
# Only ever the rounded point (core 2.8): Jakarta is -6.21, 106.85.
air_urls = [u for u in stub_requests if u.startswith(air_quality_api.AIR_URL)]
assert len(air_urls) == 1, air_urls
assert "latitude=-6.21&longitude=106.85&" in air_urls[0], air_urls[0]
print("OK main_place")

# --- Preferences page: the place choice, search, browse, save ---------------------------
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Air Quality")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "Air Quality settings page was not created"
choice = panel.place_choice.ctrl
assert choice.GetName() == "Place", choice.GetName()
assert choice.GetStrings() == ["The main place (Jakarta)", "Jakarta", "Its own place…"], \
    choice.GetStrings()
assert panel.place_choice.key() == "main" and choice.GetSelection() == 0
assert panel.txt_location.GetValue() == _("location_not_set"), panel.txt_location.GetValue()
# The city search is for its own place only: skipped while another place is chosen.
assert not panel.txt_search.IsEnabled() and not panel.btn_search.IsEnabled()
assert not panel.list_results.IsEnabled()
labels = [w.GetLabel() for w in panel.GetChildren() if isinstance(w, wx.StaticText)]
assert "Air quality data: Open-Meteo.com (CAMS)" in labels, labels
assert any("about 40 kilometres across" in label for label in labels), labels
assert any("US AQI" in label and "ISPU" in label for label in labels), labels
assert any("not medical advice" in label for label in labels), labels
assert any("rounded to about 1 kilometre" in label for label in labels), labels
assert not panel.chk_alert.GetValue()
# Arrowing through the places: focus stays; the last one, "Its own place", opens the search.
checked = browse(choice, wx.EVT_CHOICE)
assert panel.place_choice.key() == "own", panel.place_choice.key()
assert panel.txt_search.IsEnabled() and panel.btn_search.IsEnabled()
assert panel.list_results.IsEnabled()

panel.txt_search.SetValue("B")
fire(panel.txt_search, wx.EVT_TEXT_ENTER)
assert spoken[-1] == _("search_too_short"), spoken[-1]

panel.txt_search.SetValue("Bandung")
panel.txt_search.SetFocus()
wx.Yield()
search_focused = wx.Window.FindFocus() is panel.txt_search
fire(panel.txt_search, wx.EVT_TEXT_ENTER)
assert pump(lambda: panel.list_results.GetCount() == 2), "search results never arrived"
assert panel.list_results.GetString(0) == "Bandung, West Java, Indonesia"
if search_focused:
    assert wx.Window.FindFocus() is panel.list_results, "focus did not move to the results"
checked = browse(panel.list_results, wx.EVT_LISTBOX) and checked
checked = toggle(panel.chk_alert) and checked

# Back to the main place and to its own place again: the search follows.
choice.SetSelection(0)
fire(choice, wx.EVT_CHOICE, 0)
assert panel.place_choice.key() == "main" and not panel.txt_search.IsEnabled()
choice.SetSelection(2)
fire(choice, wx.EVT_CHOICE, 2)
assert panel.place_choice.key() == "own" and panel.txt_search.IsEnabled()
panel.list_results.SetSelection(0)
fire(panel.list_results, wx.EVT_LISTBOX, 0)
assert panel.chosen_location()["name"] == "Bandung"
print(f"OK panel_browse ({focus_note(checked)})")

panel.chk_alert.SetValue(True)
spoken.clear()
sounds.clear()
prefs.OnApply(None)
saved = core.api.load_data("AirQuality")
assert saved["place"] == "own", saved
assert saved["location"]["name"] == "Bandung" and saved["location"]["admin1"] == "West Java", saved
assert saved["alert"] is True, saved
assert panel.txt_location.GetValue() == "Bandung, West Java, Indonesia"
assert pump(lambda: main.current_cache() is not None), "the new city was not fetched"
# Very unhealthy air: announced once, with a sound.
assert pump(lambda: said("Air quality alert for Bandung")), spoken
assert spoken[-1] == "Air quality alert for Bandung: index 231, very unhealthy. " + TIP, spoken
assert sounds == ["info.wav"], sounds
assert core.api.load_data("AirQuality")["alert_date"] == TODAY.isoformat()
prefs.Destroy()
wx.Yield()
main._check_alert()
bus.emit("on_app_startup")
pump(lambda: False, timeout=0.3)
assert sum(s.startswith("Air quality alert") for s in spoken) == 1, spoken   # once a day
print("OK panel_apply_alert")

# --- The places change while the page is open: the list follows, the choice stays -------
prefs = PreferencesDialog(frame, select_tab="Air Quality")
prefs.Show()
wx.Yield()
panel = main._panel
choice = panel.place_choice.ctrl
assert panel.place_choice.key() == "own" and panel.txt_search.IsEnabled()
assert panel.txt_location.GetValue() == "Bandung, West Java, Indonesia"
choice.SetFocus()
wx.Yield()
choice_focused = wx.Window.FindFocus() is choice
office = {"name": "Office", "lat": -6.1754, "lon": 106.8272, "label": "", "source": "coordinates"}
core.places.set_places([jakarta_place, office])      # what the Places page does on OK
assert choice.GetStrings() == ["The main place (Jakarta)", "Jakarta", "Office",
                               "Its own place…"], choice.GetStrings()
assert panel.place_choice.key() == "own" and choice.GetSelection() == 3
assert panel.txt_search.IsEnabled()
if choice_focused:
    assert wx.Window.FindFocus() is choice, "focus moved when the places changed"
# Choosing a saved place skips its own search again, and is what OK saves.
choice.SetSelection(2)
fire(choice, wx.EVT_CHOICE, 2)
assert not panel.txt_search.IsEnabled()
before = len(stub_requests)
prefs.OnApply(None)
saved = core.api.load_data("AirQuality")
assert saved["place"] == core.places.get_places()[1]["id"], saved
assert saved["location"]["name"] == "Bandung", "its own city is kept for later"
assert main.get_location()["name"] == "Office"
assert pump(lambda: len(stub_requests) > before), "the chosen place was not fetched"
assert "latitude=-6.18&longitude=106.83&" in stub_requests[-1], stub_requests[-1]
# Back to its own city for the checks below.
panel.place_choice.set_key("own")
panel._update_own()
prefs.OnApply(None)
assert pump(lambda: main.current_cache() is not None and not main._loading)
assert main.get_location()["name"] == "Bandung"
prefs.Destroy()
wx.Yield()
print(f"OK places_changed ({focus_note(choice_focused)})")

# --- Hotkey actions with a city ---------------------------------------------------------
spoken.clear()
assert run_and_close("Air Quality.speak_air") == []
assert spoken and spoken[-1].startswith("Bandung: Air quality index 231, very unhealthy"), spoken
assert run_and_close("Air Quality.show_forecast") == ["AirForecastDialog"]
print("OK actions")

# --- The forecast window: browse both lists, refresh, close during a fetch --------------
dlg = air_ui.AirForecastDialog(frame, main.get_location(), main.current_cache, main.refresh)
dlg.Show()
wx.Yield()
hours = dlg.list_hours.GetStrings()
assert len(hours) == 8, hours
assert hours[0].startswith("Today ") and ": index " in hours[0], hours[0]
assert all(h.endswith(".") for h in hours), hours
days = dlg.list_days.GetStrings()
assert len(days) == 5, days
assert days[0].startswith("Today, ") and ": index up to " in days[0], days[0]
assert days[1].startswith("Tomorrow, "), days[1]
checked = browse(dlg.list_hours, wx.EVT_LISTBOX)
checked = browse(dlg.list_days, wx.EVT_LISTBOX) and checked
dlg.list_days.SetSelection(2)
spoken.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert spoken[0] == _("status_refreshing"), spoken
assert pump(lambda: _("forecast_updated") in spoken), spoken
assert dlg.list_days.GetSelection() == 2, "the selection moved after Refresh"
assert dlg.lbl_status.GetLabel().startswith("Updated at "), dlg.lbl_status.GetLabel()
dlg.Destroy()
wx.Yield()

dlg = air_ui.AirForecastDialog(frame, main.get_location(), main.current_cache, main.refresh,
                               refresh_now=True)
dlg.Destroy()
assert pump(lambda: not main._loading), "fetch never finished"
print(f"OK forecast_browse ({focus_note(checked)})")

# --- Escape closes the forecast window ----------------------------------------------------
state = {}


def press_escape():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, air_ui.AirForecastDialog) and w.IsModal():
            state["found"] = True
            key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
            key.SetKeyCode(wx.WXK_ESCAPE)
            key.SetEventObject(w)
            w.GetEventHandler().ProcessEvent(key)


def force_close():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, wx.Dialog) and w.IsModal():
            state["forced"] = True
            w.EndModal(wx.ID_CANCEL)


escape = wx.CallLater(400, press_escape)
guard = wx.CallLater(3000, force_close)
core.hotkeys.actions["Air Quality.show_forecast"].callback()
guard.Stop()
escape.Stop()
assert state.get("found") and not state.get("forced"), f"Escape did not close the window: {state}"
print("OK escape")

# --- Morning Briefing contribution and the background tick (cache only) -------------------
before = len(stub_requests)
lines = []
bus.emit("on_briefing_collect", lines)
assert lines == ["Air quality in Bandung: index 231, very unhealthy."], lines
bus.emit("on_minute_tick", datetime.datetime.now())
pump(lambda: False, timeout=0.3)
assert len(stub_requests) == before, "the briefing or a fresh cache caused a request"
print("OK briefing")

# --- Teardown, and nothing went wrong along the way ---------------------------------------
em.unload_all_extensions()
for event_name, handler in main._SUBSCRIPTIONS:
    assert handler not in bus._listeners.get(event_name, []), f"{event_name} still subscribed"
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
assert all(u.startswith((air_quality_api.AIR_URL + "?", air_quality_api.GEOCODING_URL + "?"))
           for u in stub_requests), stub_requests
# The Air Quality API only ever gets the place's coordinates, rounded to 2 decimals
# (about 1 km), its time zone and the fields.
for url in stub_requests:
    if url.startswith(air_quality_api.AIR_URL):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert set(query) == {"latitude", "longitude", "current", "hourly", "timezone",
                              "forecast_days"}, url
        for key in ("latitude", "longitude"):
            assert len(query[key][0].split(".")[-1]) == 2, url
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
