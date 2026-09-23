# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Flight Radar extension through the real loader with real wxPython,
open its settings page inside the real Preferences dialog and its list dialog,
run its hotkey actions, and browse every list and choice the way arrow keys
do, checking focus stays put.

adsb.fi, adsbdb and Open-Meteo are stubbed (nothing leaves the machine), speech
is captured through on_before_speak and sounds are recorded instead of played.

Run by tests/test_flight_radar_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder so the user's real settings are never touched. Prints one "OK"
line per stage.
"""
import logging
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the flight radar check hung", flush=True)
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
    WATCHED = ("hariku_ext.flight_radar", "flight_radar_", "core.events", "core.hotkeys",
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
frame = MainWindow(None, title="flight radar check")
print("OK main_window")

P = ord("P")
PLAIN_P = (P, False, False, False, False)
SHIFT_P = (P, False, True, False, False)
assert PLAIN_P not in core.hotkeys.keybindings, "P is already bound by the core"
assert SHIFT_P not in core.hotkeys.keybindings, "Shift+P is already bound by the core"

# Replace the network helper before the extension imports its modules.
FR_DIR = os.path.join(ROOT, "extensions", "flight_radar")
sys.path.insert(0, FR_DIR)
import flight_radar_api


def _plane(hex_id, callsign, reg, type_code, dst, direction, lat, lon, alt, rate, **extra):
    plane = {"hex": hex_id, "flight": callsign + " ", "r": reg, "t": type_code, "dst": dst,
             "dir": direction, "lat": lat, "lon": lon, "alt_baro": alt, "baro_rate": rate,
             "gs": 240.0, "track": 300.0, "squawk": "2345", "category": "A3", "seen": 0.3}
    plane.update(extra)
    return plane


# Synthetic aircraft around central Jakarta.
AIRCRAFT = {"aircraft": [
    _plane("abc001", "GIA155", "PK-QQA", "B738", 6.48, 45.0, -6.154, 106.906, 9843, -832),
    _plane("abc002", "CTV991", "PK-QQB", "A320", 2.43, 180.0, -6.2556, 106.845, 4921, 1500),
    _plane("abc003", "XQZ357", "PK-QQC", "ZZZ9", 5.97, 90.0, -6.2146, 106.945, 2000, 0,
           desc="DIAMOND DA-62"),
    _plane("abc004", "BTK6339", "PK-QQD", "B739", 9.72, 95.0, -6.229, 107.008, 7000, -1200),
    _plane("abc005", "AWQ531", "PK-QQE", "A20N", 10.8, 270.0, -6.2146, 106.65, "ground", None),
], "now": 1790000000000, "resultCount": 5, "ptime": 2}
PLACES = {"results": [
    {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
     "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"},
    {"name": "Jakarta", "admin1": "West Virginia", "country": "United States",
     "latitude": 38.1, "longitude": -80.2, "timezone": "America/New_York"},
]}


def _airport(town, lat, lon):
    return {"municipality": town, "name": f"{town} Airport", "iata_code": "", "icao_code": "",
            "latitude": lat, "longitude": lon, "country_name": "Indonesia"}


JAKARTA_AIRPORT = _airport("Jakarta", -6.1256, 106.6559)
ROUTES = {
    "GIA155": {"response": {"flightroute": {"origin": _airport("Batam", 1.121, 104.119),
                                            "destination": JAKARTA_AIRPORT}}},
    "BTK6339": {"response": {"flightroute": {"origin": _airport("Semarang", -6.9727, 110.3752),
                                             "destination": JAKARTA_AIRPORT}}},
}
stub_requests = []


def _fake_fetch_json(url, timeout=None):
    stub_requests.append(url)
    if url.startswith(flight_radar_api.GEOCODING_URL):
        return PLACES
    if url.startswith("https://opendata.adsb.fi/api/v2/lat/"):
        return AIRCRAFT
    if url.startswith("https://api.adsbdb.com/v0/callsign/"):
        route = ROUTES.get(url.rsplit("/", 1)[1])
        if route is None:
            raise flight_radar_api.FlightError("service", "HTTP 404", status=404)
        return route
    raise AssertionError(f"unexpected URL {url}")


flight_radar_api.fetch_json = _fake_fetch_json

import core.extension_manager as em
em.load_unpacked_extension(FR_DIR)
assert "flight_radar" in em.LOADED_EXTENSIONS, "Flight Radar extension did not load"
main = em.LOADED_EXTENSIONS["flight_radar"]["module"]
fr_ui = sys.modules["flight_radar_ui"]
fr_text = sys.modules["flight_radar_text"]
assert sys.modules["flight_radar_api"] is flight_radar_api
assert core.hotkeys.keybindings[PLAIN_P][0] == "Flight Radar.speak_nearby"
assert core.hotkeys.keybindings[SHIFT_P][0] == "Flight Radar.show_list"
# Shorter pacing so the check runs quickly; the rules themselves are unit-tested.
main._gate.min_gap = 0.3
main._routes.min_gap = 0.05
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


_ = fr_text._
NO_LOCATION = _("no_location")

# --- Without a city: a spoken hint, no window ----------------------------------
spoken.clear()
assert run_and_close("Flight Radar.speak_nearby") == []
assert run_and_close("Flight Radar.show_list") == []
assert spoken == [NO_LOCATION, NO_LOCATION], spoken
print("OK no_location_hint")

# --- The Weather city is offered as the default ----------------------------------
core.api.save_data("Weather", {"location": {"name": "Bandung", "admin1": "West Java",
                                            "country": "Indonesia", "latitude": -6.9175,
                                            "longitude": 107.6191}, "units": "metric"})
assert main.get_location()["name"] == "Bandung"
print("OK weather_default")

# --- Preferences page: search, browse, save -------------------------------------
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Flight Radar")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "Flight Radar settings page was not created"
assert panel.txt_location.GetValue() == "Bandung, West Java, Indonesia (from the Weather settings)", \
    panel.txt_location.GetValue()
assert panel.choice_radius.GetString(panel.choice_radius.GetSelection()) == \
    "25 kilometres (13 nautical miles)"
assert panel.choice_alert.GetString(panel.choice_alert.GetSelection()) == \
    "5 kilometres (2.7 nautical miles)"
assert not panel.chk_alerts.GetValue() and not panel.chk_ground.GetValue()
labels = [w.GetLabel() for w in panel.GetChildren() if isinstance(w, wx.StaticText)]
assert "Aircraft data: adsb.fi and adsb.lol" in labels, labels
assert "Flight routes: adsbdb.com (route data by David Taylor and Jim Mason)" in labels, labels

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
checked = browse(panel.list_results, wx.EVT_LISTBOX)
for choice in (panel.choice_radius, panel.choice_units, panel.choice_alert):
    checked = browse(choice, wx.EVT_CHOICE) and checked
for checkbox in (panel.chk_ground, panel.chk_alerts):
    checked = toggle(checkbox) and checked
print(f"OK panel_browse ({focus_note(checked)})")

panel.list_results.SetSelection(0)
panel.choice_radius.SetSelection(1)
panel.choice_units.SetSelection(0)
panel.chk_alerts.SetValue(False)
prefs.OnApply(None)
saved = core.api.load_data("FlightRadar")
assert saved["location"]["name"] == "Jakarta" and saved["location"]["country"] == "Indonesia", saved
assert saved["radius_km"] == 25 and saved["units"] == "metric" and saved["alerts"] is False, saved
assert panel.txt_location.GetValue() == "Jakarta, Indonesia"
assert main._poll_timer is None, "polling must stay off while alerts are off"
prefs.Destroy()
wx.Yield()
print("OK panel_apply")

# --- Hotkey actions with a city ---------------------------------------------------
spoken.clear()
assert run_and_close("Flight Radar.speak_nearby") == []
assert spoken[0] == _("checking"), spoken
assert pump(lambda: said("Citilink 991")), spoken
report = spoken[-1]
assert report.startswith("Citilink 991, Airbus A320, 4.5 kilometres south, 1,500 metres, climbing."), report
assert "Garuda Indonesia 155, from Batam to Jakarta, Boeing 737-800, 12 kilometres northeast" in report
assert report.endswith("And 1 more within 25 kilometres."), report
assert run_and_close("Flight Radar.show_list") == ["RadarListDialog"]
print("OK actions")

# --- The list: browse, details (button and Enter), a route arriving, refresh ------
dlg = fr_ui.RadarListDialog(frame, "Jakarta, Indonesia", main.get_settings(), main.list_data,
                            main.refresh, main.leg_for, main.with_routes)
dlg.Show()
wx.Yield()
rows = [dlg.list_aircraft.GetString(i) for i in range(dlg.list_aircraft.GetCount())]
assert len(rows) == 4, rows
assert rows[0].startswith("Citilink 991") and rows[3].startswith("Batik Air 6339, Boeing 737-900")
assert "from Batam to Jakarta" in rows[2], rows[2]   # cached by the nearby action
assert "on the ground" not in " ".join(rows)
checked = browse(dlg.list_aircraft, wx.EVT_LISTBOX)
assert dlg.txt_details.GetValue().startswith("Batik Air 6339. Registration P K Q Q D."), \
    dlg.txt_details.GetValue()

spoken.clear()
dlg.list_aircraft.SetFocus()
wx.Yield()
list_focused = wx.Window.FindFocus() is dlg.list_aircraft
fire(dlg.btn_details, wx.EVT_BUTTON)          # BTK6339 is selected; its route is looked up
assert pump(lambda: said("Batik Air 6339")), spoken
assert spoken[-1].startswith("Batik Air 6339, from Semarang to Jakarta. Registration P K Q Q D. "
                             "Type Boeing 737-900."), spoken[-1]
assert dlg.list_aircraft.GetSelection() == 3, "the selection moved"
assert "from Semarang to Jakarta" in dlg.list_aircraft.GetString(3)
if list_focused:
    assert wx.Window.FindFocus() is dlg.list_aircraft, "focus left the list after Details"

if list_focused:
    dlg.list_aircraft.SetSelection(0)
    spoken.clear()
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_RETURN)
    dlg.GetEventHandler().ProcessEvent(key)
    assert pump(lambda: said("Citilink 991. Registration")), spoken
    assert wx.Window.FindFocus() is dlg.list_aircraft

dlg.list_aircraft.SetSelection(3)
spoken.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert spoken[0] == _("status_refreshing"), spoken
assert pump(lambda: "4 aircraft within 25 kilometres." in spoken), spoken
assert dlg.list_aircraft.GetSelection() == 3 and dlg.list_aircraft.GetString(3).startswith("Batik")
assert dlg.lbl_status.GetLabel().startswith("Updated at "), dlg.lbl_status.GetLabel()
dlg.Destroy()
wx.Yield()

# A dialog closed while its refresh is running must not break anything.
dlg = fr_ui.RadarListDialog(frame, "Jakarta, Indonesia", main.get_settings(), main.list_data,
                            main.refresh, main.leg_for, main.with_routes, refresh_now=True)
dlg.Destroy()
assert pump(lambda: not main._loading and main._fetch_timer is None), "fetch never finished"
print(f"OK list_dialog ({focus_note(checked)})")

# --- Escape closes the list ----------------------------------------------------------
state = {}


def press_escape():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, fr_ui.RadarListDialog) and w.IsModal():
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
core.hotkeys.actions["Flight Radar.show_list"].callback()
guard.Stop()
escape.Stop()
assert state.get("found") and not state.get("forced"), f"Escape did not close the list: {state}"
print("OK escape")

# --- Overhead alerts ----------------------------------------------------------------
prefs = PreferencesDialog(frame, select_tab="Flight Radar")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel.txt_location.GetValue() == "Jakarta, Indonesia"
panel.chk_alerts.SetValue(True)
prefs.OnApply(None)
prefs.Destroy()
wx.Yield()
assert main._poll_timer is not None, "polling did not start"
spoken.clear()
sounds.clear()
main._poll_timer.Stop()
main._poll()                                  # rather than waiting for the timer
assert pump(lambda: said("Overhead: Citilink 991")), spoken
assert sounds == ["info.wav"], sounds
assert main._poll_timer is not None, "the next poll was not scheduled"
main._poll_timer.Stop()
main._poll()
pump(lambda: False, timeout=0.6)
assert sum(s.startswith("Overhead:") for s in spoken) == 1, spoken   # once per aircraft

prefs = PreferencesDialog(frame, select_tab="Flight Radar")
prefs.Show()
wx.Yield()
main._panel.chk_alerts.SetValue(False)
prefs.OnApply(None)
prefs.Destroy()
wx.Yield()
pump(lambda: not main._poll_running, timeout=2)
assert main._poll_timer is None, "polling did not stop"
print("OK alerts")

# --- Teardown, and nothing went wrong along the way -----------------------------------
em.unload_all_extensions()
for event_name, handler in main._SUBSCRIPTIONS:
    assert handler not in bus._listeners.get(event_name, []), f"{event_name} still subscribed"
assert main._poll_timer is None and main._fetch_timer is None
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
allowed = ("https://opendata.adsb.fi/", "https://api.adsbdb.com/",
           "https://geocoding-api.open-meteo.com/")
assert all(u.startswith(allowed) for u in stub_requests), stub_requests
route_requests = [u for u in stub_requests if "adsbdb" in u]
assert len(route_requests) == len(set(route_requests)), f"routes looked up twice: {route_requests}"
# Routes are kept in memory only: nothing about them reaches the data folder.
for name in os.listdir(core.api.DATA_DIR):
    with open(os.path.join(core.api.DATA_DIR, name), encoding="utf-8", errors="replace") as f:
        content = f.read()
    assert "Batam" not in content and "Semarang" not in content, f"route data in {name}"
    assert "PK-QQ" not in content, f"aircraft data in {name}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
