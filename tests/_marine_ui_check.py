# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Sea Conditions extension through the real loader with real wxPython,
open its settings page inside the real Preferences dialog and its forecast
window, run its hotkey actions, and browse every list and choice the way arrow
keys do, checking focus stays put.

Open-Meteo is stubbed (nothing leaves the machine), speech is captured through
on_before_speak, and sounds are recorded instead of played.

Run by tests/test_marine_ui.py in a separate process, because conftest.py
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
    print("TIMEOUT: the sea conditions check hung", flush=True)
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
    WATCHED = ("hariku_ext.marine", "marine_", "core.events", "core.hotkeys",
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
frame = MainWindow(None, title="sea conditions check")
print("OK main_window")

PLAIN_O = (ord("O"), False, False, False, False)
SHIFT_O = (ord("O"), False, True, False, False)
assert PLAIN_O not in core.hotkeys.keybindings, "O is already bound by the core"
assert SHIFT_O not in core.hotkeys.keybindings, "Shift+O is already bound by the core"

# Replace the Open-Meteo fetch before the extension imports its helpers.
MARINE_DIR = os.path.join(ROOT, "extensions", "marine")
sys.path.insert(0, MARINE_DIR)
import marine_api

# Sea data around the real "now", in this computer's time zone, so the tides
# ahead exist whenever the check runs: a 12.42-hour tide from yesterday on.
TODAY = datetime.date.today()
_local_offset = int(datetime.datetime.now().astimezone().utcoffset().total_seconds())
_start = datetime.datetime.combine(TODAY - datetime.timedelta(days=1), datetime.time())
HOURS = [(_start + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(8 * 24)]
LEVELS = [round(0.5 + 0.6 * math.cos(2 * math.pi * (i - 5.3) / 12.42), 2) for i in range(len(HOURS))]
DATES = [(TODAY + datetime.timedelta(days=d)).isoformat() for d in range(-1, 7)]
MARINE = {
    "utc_offset_seconds": _local_offset, "timezone": "Asia/Jakarta",
    "current": {"time": datetime.datetime.now().strftime("%Y-%m-%dT%H:00"), "interval": 900,
                "wave_height": 1.42, "wave_direction": 225, "wave_period": 12.2,
                "swell_wave_height": 1.1, "sea_surface_temperature": 28.6},
    "hourly": {"time": HOURS, "sea_level_height_msl": LEVELS},
    "daily": {"time": DATES, "wave_height_max": [1.5, 1.8, 1.6, 1.2, 1.0, 0.9, 1.1, 1.3],
              "wave_direction_dominant": [225] * 8, "wave_period_max": [12.5] * 8,
              "swell_wave_height_max": [1.2] * 8},
}
# Bandung is inland: the Marine API answers with nulls.
INLAND = {
    "utc_offset_seconds": _local_offset, "timezone": "Asia/Jakarta",
    "current": {"time": MARINE["current"]["time"], "interval": 900, "wave_height": None,
                "wave_direction": None, "wave_period": None, "swell_wave_height": None,
                "sea_surface_temperature": None},
    "hourly": {"time": HOURS, "sea_level_height_msl": [None] * len(HOURS)},
    "daily": {"time": DATES, "wave_height_max": [None] * 8, "wave_direction_dominant": [None] * 8,
              "wave_period_max": [None] * 8, "swell_wave_height_max": [None] * 8},
}
PLACES = {"results": [
    {"name": "Pelabuhan Ratu", "admin1": "West Java", "country": "Indonesia",
     "latitude": -6.9869, "longitude": 106.5463, "timezone": "Asia/Jakarta"},
    {"name": "Pelabuhan Ratu", "admin1": "Lampung", "country": "Indonesia",
     "latitude": -5.45, "longitude": 105.27, "timezone": "Asia/Jakarta"},
]}
BANDUNG = {"name": "Bandung", "admin1": "West Java", "country": "Indonesia",
           "latitude": -6.9175, "longitude": 107.6191, "timezone": "Asia/Jakarta"}
stub_requests = []


def _fake_fetch_json(url):
    stub_requests.append(url)
    if url.startswith(marine_api.GEOCODING_URL):
        return PLACES
    if url.startswith(marine_api.MARINE_URL):
        # Only ever the rounded point (core 2.8): Bandung is -6.92, 107.62.
        return INLAND if "latitude=-6.92&" in url else MARINE
    raise AssertionError(f"unexpected URL {url}")


marine_api.fetch_json = _fake_fetch_json

import core.extension_manager as em
em.load_unpacked_extension(MARINE_DIR)
assert "marine" in em.LOADED_EXTENSIONS, "Sea Conditions did not load"
main = em.LOADED_EXTENSIONS["marine"]["module"]
marine_ui = sys.modules["marine_ui"]
marine_text = sys.modules["marine_text"]
assert sys.modules["marine_api"] is marine_api
assert core.hotkeys.keybindings[PLAIN_O][0] == "Sea Conditions.speak_sea"
assert core.hotkeys.keybindings[SHIFT_O][0] == "Sea Conditions.show_forecast"
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


_ = marine_text._
NO_LOCATION = _("no_location")

# --- Without a place: a spoken hint, no window --------------------------------------
spoken.clear()
assert run_and_close("Sea Conditions.speak_sea") == []
assert run_and_close("Sea Conditions.show_forecast") == []
assert spoken == [NO_LOCATION, NO_LOCATION], spoken
print("OK no_location_hint")

# --- The main place (Preferences, Places) is the default; an inland one has no sea data --
import core.places
core.api.save_data("Weather", {"location": BANDUNG, "units": "metric"})
assert main.get_location() is None, "the Weather city is no longer used by itself"
bandung_place, = core.places.set_places([{
    "name": "Bandung", "lat": BANDUNG["latitude"], "lon": BANDUNG["longitude"],
    "label": "Bandung, West Java, Indonesia", "timezone": "Asia/Jakarta", "source": "city",
    "city": "Bandung", "region": "West Java", "country": "Indonesia"}])
assert main.get_location()["name"] == "Bandung"
spoken.clear()
assert run_and_close("Sea Conditions.speak_sea") == []
assert spoken[0] == _("fetching"), spoken
assert pump(lambda: len(spoken) >= 2), spoken
assert spoken[-1] == ("No sea data for Bandung. Choose a beach or port in Preferences, "
                      "Sea Conditions."), spoken
dlg = marine_ui.SeaForecastDialog(frame, main.get_location(), main.current_cache, main.refresh)
dlg.Show()
wx.Yield()
assert dlg.list_days.GetStrings() == [_("forecast_no_data")], dlg.list_days.GetStrings()
assert dlg.list_tides.GetStrings() == [_("tides_empty")], dlg.list_tides.GetStrings()
dlg.Destroy()
wx.Yield()
print("OK main_place_inland")

# --- Preferences page: the place choice, search, browse, save -------------------------
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Sea Conditions")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "Sea Conditions settings page was not created"
choice = panel.place_choice.ctrl
assert choice.GetName() == "Place", choice.GetName()
assert choice.GetStrings() == ["The main place (Bandung)", "Bandung", "Its own place\u2026"], \
    choice.GetStrings()
assert panel.place_choice.key() == "main" and choice.GetSelection() == 0
assert panel.txt_location.GetValue() == _("location_not_set"), panel.txt_location.GetValue()
# The place search is for its own place only: skipped while another place is chosen.
assert not panel.txt_search.IsEnabled() and not panel.list_results.IsEnabled()
labels = [w.GetLabel() for w in panel.GetChildren() if isinstance(w, wx.StaticText)]
assert "Data: Open-Meteo.com" in labels, labels
assert any("roughly 5 to 25 kilometres across" in label for label in labels), labels
assert any("navigation or safety at sea" in label for label in labels), labels
assert any("rounded to about 1 kilometre" in label for label in labels), labels
assert not panel.chk_alert.GetValue()
# Arrowing through the places: focus stays; the last one, "Its own place", opens the search.
checked = browse(choice, wx.EVT_CHOICE)
assert panel.place_choice.key() == "own", panel.place_choice.key()
assert panel.txt_search.IsEnabled() and panel.btn_search.IsEnabled()
assert panel.list_results.IsEnabled()
assert panel.choice_height.GetString(panel.choice_height.GetSelection()) == "2.5 metres, rough"

panel.txt_search.SetValue("P")
fire(panel.txt_search, wx.EVT_TEXT_ENTER)
assert spoken[-1] == _("search_too_short"), spoken[-1]

panel.txt_search.SetValue("Pelabuhan Ratu")
panel.txt_search.SetFocus()
wx.Yield()
search_focused = wx.Window.FindFocus() is panel.txt_search
fire(panel.txt_search, wx.EVT_TEXT_ENTER)
assert pump(lambda: panel.list_results.GetCount() == 2), "search results never arrived"
assert panel.list_results.GetString(0) == "Pelabuhan Ratu, West Java, Indonesia"
if search_focused:
    assert wx.Window.FindFocus() is panel.list_results, "focus did not move to the results"
checked = browse(panel.list_results, wx.EVT_LISTBOX) and checked
checked = browse(panel.choice_height, wx.EVT_CHOICE) and checked
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
assert panel.chosen_location()["name"] == "Pelabuhan Ratu"
print(f"OK panel_browse ({focus_note(checked)})")

panel.choice_height.SetSelection(0)          # 1 metre
panel.chk_alert.SetValue(True)
spoken.clear()
sounds.clear()
prefs.OnApply(None)
saved = core.api.load_data("Marine")
assert saved["place"] == "own", saved
assert saved["location"]["name"] == "Pelabuhan Ratu" and saved["location"]["admin1"] == "West Java", saved
assert saved["alert"] is True and saved["alert_height"] == 1.0, saved
assert panel.txt_location.GetValue() == "Pelabuhan Ratu, West Java, Indonesia"
assert pump(lambda: main.current_cache() is not None), "the new place was not fetched"
# Today's waves reach 1.8 metres: announced once, with a sound.
assert pump(lambda: said("Sea alert for Pelabuhan Ratu")), spoken
assert spoken[-1] == "Sea alert for Pelabuhan Ratu: waves up to 1.8 metres today, moderate.", spoken
assert sounds == ["info.wav"], sounds
assert core.api.load_data("Marine")["alert_date"] == TODAY.isoformat()
prefs.Destroy()
wx.Yield()
main._check_alert()
bus.emit("on_app_startup")
pump(lambda: False, timeout=0.3)
assert sum(s.startswith("Sea alert") for s in spoken) == 1, spoken   # once a day
print("OK panel_apply_alert")

# --- The places change while the page is open: the list follows, the choice stays -----
prefs = PreferencesDialog(frame, select_tab="Sea Conditions")
prefs.Show()
wx.Yield()
panel = main._panel
choice = panel.place_choice.ctrl
assert panel.place_choice.key() == "own" and panel.txt_search.IsEnabled()
assert panel.txt_location.GetValue() == "Pelabuhan Ratu, West Java, Indonesia"
choice.SetFocus()
wx.Yield()
choice_focused = wx.Window.FindFocus() is choice
beach = {"name": "Pantai Pangandaran", "lat": -7.7, "lon": 108.65, "label": "", "source": "coordinates"}
core.places.set_places([bandung_place, beach])      # what the Places page does on OK
assert choice.GetStrings() == ["The main place (Bandung)", "Bandung", "Pantai Pangandaran",
                               "Its own place\u2026"], choice.GetStrings()
assert panel.place_choice.key() == "own" and choice.GetSelection() == 3
if choice_focused:
    assert wx.Window.FindFocus() is choice, "focus moved when the places changed"
# Choosing a saved place skips its own search again, and is what OK saves.
choice.SetSelection(2)
fire(choice, wx.EVT_CHOICE, 2)
assert not panel.txt_search.IsEnabled()
before = len(stub_requests)
prefs.OnApply(None)
saved = core.api.load_data("Marine")
assert saved["place"] == core.places.get_places()[1]["id"], saved
assert saved["location"]["name"] == "Pelabuhan Ratu", "its own place is kept for later"
assert main.get_location()["name"] == "Pantai Pangandaran"
assert pump(lambda: len(stub_requests) > before), "the chosen place was not fetched"
assert "latitude=-7.70&longitude=108.65" in stub_requests[-1], stub_requests[-1]
# Back to its own place for the checks below.
panel.place_choice.set_key("own")
panel._update_own()
prefs.OnApply(None)
assert pump(lambda: main.current_cache() is not None and not main._loading)
assert main.get_location()["name"] == "Pelabuhan Ratu"
prefs.Destroy()
wx.Yield()
print(f"OK places_changed ({focus_note(choice_focused)})")

# --- Hotkey actions with a place ------------------------------------------------------
spoken.clear()
assert run_and_close("Sea Conditions.speak_sea") == []
report = spoken[-1] if spoken else ""
assert report.startswith("Pelabuhan Ratu: Waves 1.4 metres, moderate, from the southwest, "
                         "period 12 seconds. Swell 1.1 metres. Sea temperature 29 degrees. "
                         "The tide is "), spoken
assert "high tide " in report and "low tide " in report, report
assert run_and_close("Sea Conditions.show_forecast") == ["SeaForecastDialog"]
print("OK actions")

# --- The forecast window: browse both lists, refresh, close during a fetch ------------
dlg = marine_ui.SeaForecastDialog(frame, main.get_location(), main.current_cache, main.refresh)
dlg.Show()
wx.Yield()
days = dlg.list_days.GetStrings()
assert len(days) == 7, days
assert days[0].startswith("Today, ") and "waves up to 1.8 metres, moderate" in days[0], days[0]
assert days[1].startswith("Tomorrow, ") and "; tides: " in days[1], days[1]
tides = dlg.list_tides.GetStrings()
assert len(tides) >= 10, tides
assert all(t.startswith(("High tide ", "Low tide ")) and t.endswith("mean sea level.")
           for t in tides), tides
checked = browse(dlg.list_days, wx.EVT_LISTBOX)
checked = browse(dlg.list_tides, wx.EVT_LISTBOX) and checked
dlg.list_tides.SetSelection(3)
spoken.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert spoken[0] == _("status_refreshing"), spoken
assert pump(lambda: _("forecast_updated") in spoken), spoken
assert dlg.list_tides.GetSelection() == 3, "the selection moved after Refresh"
assert dlg.lbl_status.GetLabel().startswith("Updated at "), dlg.lbl_status.GetLabel()
dlg.Destroy()
wx.Yield()

dlg = marine_ui.SeaForecastDialog(frame, main.get_location(), main.current_cache, main.refresh,
                                  refresh_now=True)
dlg.Destroy()
assert pump(lambda: not main._loading), "fetch never finished"
print(f"OK forecast_browse ({focus_note(checked)})")

# --- Escape closes the forecast window --------------------------------------------------
state = {}


def press_escape():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, marine_ui.SeaForecastDialog) and w.IsModal():
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
core.hotkeys.actions["Sea Conditions.show_forecast"].callback()
guard.Stop()
escape.Stop()
assert state.get("found") and not state.get("forced"), f"Escape did not close the window: {state}"
print("OK escape")

# --- Morning Briefing contribution and the background tick (cache only) ----------------
before = len(stub_requests)
lines = []
bus.emit("on_briefing_collect", lines)
assert len(lines) == 1, lines
assert lines[0].startswith("Sea at Pelabuhan Ratu: waves 1.4 metres, moderate, next high tide "), lines
bus.emit("on_minute_tick", datetime.datetime.now())
pump(lambda: False, timeout=0.3)
assert len(stub_requests) == before, "the briefing or a fresh cache caused a request"
print("OK briefing")

# --- Teardown, and nothing went wrong along the way -------------------------------------
em.unload_all_extensions()
for event_name, handler in main._SUBSCRIPTIONS:
    assert handler not in bus._listeners.get(event_name, []), f"{event_name} still subscribed"
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
assert all(u.startswith((marine_api.MARINE_URL + "?", marine_api.GEOCODING_URL + "?"))
           for u in stub_requests), stub_requests
# The Marine API only ever gets the place's coordinates, its time zone and the fields.
for url in stub_requests:
    if url.startswith(marine_api.MARINE_URL):
        keys = set(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))
        assert keys == {"latitude", "longitude", "current", "hourly", "daily", "timezone",
                        "past_days", "forecast_days"}, url
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
