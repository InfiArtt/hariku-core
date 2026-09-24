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

adsb.fi, adsbdb, Open-Meteo, Nominatim and the Google short-link redirect are
stubbed (nothing leaves the machine), speech
is captured through on_before_speak, sounds are recorded instead of played, and
the browser is never opened: the LiveATC addresses are recorded instead.

Run by tests/test_flight_radar_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder so the user's real settings are never touched. Prints one "OK"
line per stage.
"""
import logging
import math
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

# Listen to ATC only records the address it would open.
import webbrowser

opened_urls = []
webbrowser.open = lambda url, *args, **kwargs: opened_urls.append(url) or True

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
SHIFT_L = (ord("L"), False, True, False, False)
PLAIN_T = (ord("T"), False, False, False, False)
SHIFT_T = (ord("T"), False, True, False, False)
assert PLAIN_P not in core.hotkeys.keybindings, "P is already bound by the core"
assert SHIFT_P not in core.hotkeys.keybindings, "Shift+P is already bound by the core"
assert SHIFT_L not in core.hotkeys.keybindings, "Shift+L is already bound by the core"
assert PLAIN_T not in core.hotkeys.keybindings, "T is already bound by the core"
assert SHIFT_T not in core.hotkeys.keybindings, "Shift+T is already bound by the core"

# Replace the network helper before the extension imports its modules.
FR_DIR = os.path.join(ROOT, "extensions", "flight_radar")
sys.path.insert(0, FR_DIR)
import flight_radar_api


HOME_POINT = (-6.21462, 106.84513)   # the exact point the check sets as "Home"


def _at(km, bearing):
    """The point `km` from HOME_POINT on `bearing` (the same sphere as Hariku)."""
    d = km / 6371.0
    lat1, lon1, b = (math.radians(HOME_POINT[0]), math.radians(HOME_POINT[1]),
                     math.radians(bearing))
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(b))
    lon2 = lon1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(lat1),
                             math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)


def _plane(hex_id, callsign, reg, type_code, km, bearing, alt, rate, **extra):
    lat, lon = _at(km, bearing)
    # dst/dir from the service are relative to the rounded point, so Hariku
    # ignores them; these deliberately wrong values prove it.
    plane = {"hex": hex_id, "flight": callsign + " ", "r": reg, "t": type_code, "dst": 99.0,
             "dir": 0.0, "lat": lat, "lon": lon, "alt_baro": alt, "baro_rate": rate,
             "gs": 240.0, "track": 300.0, "squawk": "2345", "category": "A3", "seen": 0.3}
    plane.update(extra)
    return plane


# Synthetic aircraft around the home point in central Jakarta.
AIRCRAFT = {"aircraft": [
    _plane("abc001", "GIA155", "PK-QQA", "B738", 12, 45, 9843, -832),
    _plane("abc002", "CTV991", "PK-QQB", "A320", 4.5, 180, 4921, 1500),
    _plane("abc003", "XQZ357", "PK-QQC", "ZZZ9", 11.05, 90, 2000, 0, desc="DIAMOND DA-62"),
    _plane("abc004", "BTK6339", "PK-QQD", "B739", 18, 95, 7000, -1200),
    _plane("abc005", "AWQ531", "PK-QQE", "A20N", 20, 270, "ground", None),
    _plane("abc006", "XQZ777", "PK-QQF", "B738", 20, 265, 3000, -900, squawk="7700"),
], "now": 1790000000000, "resultCount": 6, "ptime": 2}
ADDRESSES = [
    {"place_id": 1, "lat": "-6.1753924", "lon": "106.8271528",
     "display_name": "Monumen Nasional, Jalan Medan Merdeka, Gambir, Jakarta Pusat, Indonesia"},
    {"place_id": 2, "lat": "-6.9147", "lon": "107.6098",
     "display_name": "Jalan Merdeka, Bandung, Jawa Barat, Indonesia"},
]
PLACES = {"results": [
    {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
     "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"},
    {"name": "Jakarta", "admin1": "West Virginia", "country": "United States",
     "latitude": 38.1, "longitude": -80.2, "timezone": "America/New_York"},
]}


def _airport(town, icao, lat, lon):
    return {"municipality": town, "name": f"{town} Airport", "iata_code": "", "icao_code": icao,
            "latitude": lat, "longitude": lon, "country_name": "Indonesia"}


JAKARTA_AIRPORT = _airport("Jakarta", "WIII", -6.1256, 106.6559)
ROUTES = {
    "GIA155": {"response": {"flightroute": {"origin": _airport("Batam", "WIDD", 1.121, 104.119),
                                            "destination": JAKARTA_AIRPORT}}},
    "BTK6339": {"response": {"flightroute": {
        "origin": _airport("Semarang", "WAHS", -6.9727, 110.3752), "destination": JAKARTA_AIRPORT}}},
}
stub_requests = []
nominatim_agents = []


# A flight to track, 30 km north of home; every other flight is not transmitting.
TRACKED = {"ac": [_plane("abd408", "GIA408", "PK-GPA", "B738", 30, 0, 9843, -832)],
           "msg": "No error"}


def _fake_fetch_json(url, timeout=None, user_agent=None):
    stub_requests.append(url)
    if url.startswith(flight_radar_api.GEOCODING_URL):
        return PLACES
    if url.startswith("https://nominatim.openstreetmap.org/search?"):
        nominatim_agents.append(user_agent)
        return ADDRESSES
    if url.startswith("https://opendata.adsb.fi/api/v2/callsign/"):
        return TRACKED if url.endswith("/GIA408") else {"ac": [], "msg": "No error"}
    if url.startswith("https://opendata.adsb.fi/api/v2/registration/"):
        return {"ac": [], "msg": "No error"}
    if url.startswith("https://opendata.adsb.fi/api/v2/lat/"):
        return AIRCRAFT
    if url.startswith("https://api.adsbdb.com/v0/callsign/"):
        route = ROUTES.get(url.rsplit("/", 1)[1])
        if route is None:
            raise flight_radar_api.FlightError("service", "HTTP 404", status=404)
        return route
    raise AssertionError(f"unexpected URL {url}")


flight_radar_api.fetch_json = _fake_fetch_json

# The short-link redirect: Google's answer is only ever read, never fetched.
import flight_radar_location

short_link_fetches = []
PIN_URL = ("https://www.google.com/maps/place/Home/@-6.2,106.8,17z/data=!4m6!3m5!1s0x0:0x0"
           "!8m2!3d-6.21462!4d106.84513")


def _fake_open_without_redirects(url, timeout):
    short_link_fetches.append(url)
    return 302, PIN_URL


flight_radar_location._open_without_redirects = _fake_open_without_redirects

import core.extension_manager as em
em.load_unpacked_extension(FR_DIR)
assert "flight_radar" in em.LOADED_EXTENSIONS, "Flight Radar extension did not load"
main = em.LOADED_EXTENSIONS["flight_radar"]["module"]
fr_ui = sys.modules["flight_radar_ui"]
fr_text = sys.modules["flight_radar_text"]
assert sys.modules["flight_radar_api"] is flight_radar_api
assert core.hotkeys.keybindings[PLAIN_P][0] == "Flight Radar.speak_nearby"
assert core.hotkeys.keybindings[SHIFT_P][0] == "Flight Radar.show_list"
assert core.hotkeys.keybindings[SHIFT_L][0] == "Flight Radar.listen_atc"
assert core.hotkeys.keybindings[PLAIN_T][0] == "Flight Radar.speak_tracked"
assert core.hotkeys.keybindings[SHIFT_T][0] == "Flight Radar.track_flight"
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


MAYDAY = "Attention: X Q Z 777 is squawking 7 7 0 0, general emergency, 20 kilometres west."
JAKARTA_FEED = "https://www.liveatc.net/hlisten.php?mount=wiii"


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
assert "Address search: © OpenStreetMap contributors" in labels, labels
assert any("rounded to about 1 kilometre" in label for label in labels), labels
assert panel.txt_name.GetValue() == "Home"
assert any(label.startswith("Listen to ATC opens LiveATC's website in your browser")
           and "differ by country" in label for label in labels), labels
assert panel.chk_emergency.GetLabel() == "Watch for emergencies in the background"
assert not panel.chk_emergency.GetValue()

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
for checkbox in (panel.chk_ground, panel.chk_alerts, panel.chk_emergency):
    checked = toggle(checkbox) and checked
panel.list_results.SetSelection(0)
fire(panel.list_results, wx.EVT_LISTBOX, 0)
assert panel.chosen_location()["name"] == "Jakarta"

# Street address: searched only on Enter or the button, never while typing.
panel.txt_address.SetValue("Jl")
wx.Yield()
fire(panel.txt_address, wx.EVT_TEXT_ENTER)
assert spoken[-1] == _("address_too_short"), spoken[-1]
panel.txt_address.SetValue("Jalan Medan Merdeka")
wx.Yield()
assert not nominatim_agents, "typing alone must not search"
panel.txt_address.SetFocus()
wx.Yield()
address_focused = wx.Window.FindFocus() is panel.txt_address
fire(panel.txt_address, wx.EVT_TEXT_ENTER)
assert pump(lambda: panel.list_addresses.GetCount() == 2), "address results never arrived"
assert panel.list_addresses.GetString(0).startswith("Monumen Nasional, Jalan Medan Merdeka")
if address_focused:
    assert wx.Window.FindFocus() is panel.list_addresses, "focus did not move to the addresses"
checked = browse(panel.list_addresses, wx.EVT_LISTBOX) and checked
panel.list_addresses.SetSelection(0)
fire(panel.list_addresses, wx.EVT_LISTBOX, 0)
chosen = panel.chosen_location()
assert chosen["kind"] == "address" and chosen["name"] == "Home", chosen
assert chosen["detail"].startswith("Monumen Nasional"), chosen
mark = len(spoken)
fire(panel.btn_address, wx.EVT_BUTTON)          # the same search again: from memory
# Focus is on the results list, so the answer is spoken rather than focused.
assert pump(lambda: any(s.startswith("2 addresses found") for s in spoken[mark:])), spoken
assert nominatim_agents == [flight_radar_location.NOMINATIM_USER_AGENT], nominatim_agents

# Coordinates or a map link: a wrong paste, then a Google Maps short link.
panel.txt_coords.SetValue("Monas")
fire(panel.txt_coords, wx.EVT_TEXT_ENTER)
assert spoken[-1] == fr_text.location_error_text("not_found"), spoken[-1]
panel.txt_coords.SetValue("https://maps.app.goo.gl/HarikuTest")
panel.txt_coords.SetFocus()
wx.Yield()
coords_focused = wx.Window.FindFocus() is panel.txt_coords
fire(panel.btn_use, wx.EVT_BUTTON)
assert said(_("link_expanding")), spoken
assert pump(lambda: said("Location found: Home, about ")), spoken
assert spoken[-1].endswith("from Jakarta Halim Perdanakusuma airport. Press OK to save it."), spoken
assert short_link_fetches == ["https://maps.app.goo.gl/HarikuTest"], short_link_fetches
assert panel.lbl_point.GetLabel().startswith("Found -6.21462, 106.84513: about "), \
    panel.lbl_point.GetLabel()
if coords_focused:
    assert wx.Window.FindFocus() is panel.txt_coords, "focus moved after Use"
assert panel.chosen_location()["kind"] == "coordinates"
print(f"OK panel_browse ({focus_note(checked)})")

panel.choice_radius.SetSelection(1)
panel.choice_units.SetSelection(0)
panel.chk_alerts.SetValue(False)
prefs.OnApply(None)
saved = core.api.load_data("FlightRadar")
# The exact point is stored here, and only here.
assert saved["location"] == {"name": "Home", "admin1": "", "country": "",
                             "latitude": -6.21462, "longitude": 106.84513,
                             "kind": "coordinates", "detail": ""}, saved
assert saved["radius_km"] == 25 and saved["units"] == "metric" and saved["alerts"] is False, saved
assert saved["emergency_watch"] is False, saved
assert panel.txt_location.GetValue() == "Home: -6.21462, 106.84513"
assert main._poll_timer is None, "polling must stay off while alerts are off"
prefs.Destroy()
wx.Yield()
print("OK panel_apply")

# --- Hotkey actions with a city ---------------------------------------------------
spoken.clear()
assert run_and_close("Flight Radar.speak_nearby") == []
assert spoken[0] == _("checking"), spoken
assert pump(lambda: said(MAYDAY)), spoken
report = spoken[-1]
# An emergency comes first, before anything else.
assert report.startswith(MAYDAY + " Citilink 991, Airbus A320, 4.5 kilometres south, "
                         "1,500 metres, climbing."), report
assert "Garuda Indonesia 155, from Batam to Jakarta, Boeing 737-800, 12 kilometres northeast" in report
assert report.endswith("And 2 more within 25 kilometres."), report
assert run_and_close("Flight Radar.show_list") == ["RadarListDialog"]
spoken.clear()
assert run_and_close("Flight Radar.listen_atc") == []
assert spoken == ["Opening LiveATC for Jakarta Soekarno-Hatta in your browser."], spoken
assert pump(lambda: opened_urls == [JAKARTA_FEED]), opened_urls
print("OK actions")

# --- The list: browse, details (button and Enter), a route arriving, refresh ------
dlg = fr_ui.RadarListDialog(frame, "Home", main.get_settings(), main.list_data,
                            main.refresh, main.leg_for, main.with_routes,
                            listen=main.listen_for_aircraft, emergency_intro=main.emergency_intro)
dlg.Show()
wx.Yield()
rows = [dlg.list_aircraft.GetString(i) for i in range(dlg.list_aircraft.GetCount())]
assert len(rows) == 5, rows
assert rows[0].startswith("Citilink 991") and rows[3].startswith("Batik Air 6339, Boeing 737-900")
assert "from Batam to Jakarta" in rows[2], rows[2]   # cached by the nearby action
assert rows[4].startswith("Emergency: X Q Z 777, Boeing 737-800, 20 kilometres west"), rows[4]
assert sum(r.startswith("Emergency:") for r in rows) == 1
assert "on the ground" not in " ".join(rows)
checked = browse(dlg.list_aircraft, wx.EVT_LISTBOX)
details = dlg.txt_details.GetValue()
assert details.startswith("X Q Z 777. Registration P K Q Q F."), details
assert "Squawk 7 7 0 0, general emergency." in details, details
assert details.endswith("Listen to ATC opens Jakarta Soekarno-Hatta."), details
dlg.list_aircraft.SetSelection(3)
fire(dlg.list_aircraft, wx.EVT_LISTBOX, 3)
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
assert ("Squawk 2 3 4 5, a code assigned by air traffic control to identify this flight. "
        "Listen to ATC opens Jakarta Soekarno-Hatta.") in spoken[-1], spoken[-1]
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

# Listen to ATC for the selected aircraft (Batik Air 6339, descending to Jakarta).
dlg.list_aircraft.SetSelection(3)
spoken.clear()
del opened_urls[:]
if list_focused:
    dlg.list_aircraft.SetFocus()
    wx.Yield()
fire(dlg.btn_listen, wx.EVT_BUTTON)
assert pump(lambda: opened_urls == [JAKARTA_FEED]), opened_urls
assert spoken[-1] == ("Opening LiveATC for Jakarta Soekarno-Hatta in your browser. "
                      "You'll hear the whole frequency, not just this aircraft."), spoken
assert dlg.list_aircraft.GetSelection() == 3, "the selection moved"
if list_focused:
    assert wx.Window.FindFocus() is dlg.list_aircraft, "focus left the list after Listen"

# Refresh: new data, so the emergency is spoken first, then the count.
spoken.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert spoken[0] == _("status_refreshing"), spoken
assert pump(lambda: any("aircraft within 25 kilometres." in s for s in spoken)), spoken
assert spoken[-1] == MAYDAY + " 5 aircraft within 25 kilometres.", spoken
assert dlg.list_aircraft.GetSelection() == 3 and dlg.list_aircraft.GetString(3).startswith("Batik")
assert dlg.lbl_status.GetLabel().startswith("Updated at "), dlg.lbl_status.GetLabel()
dlg.Destroy()
wx.Yield()

# A dialog closed while its refresh is running must not break anything.
dlg = fr_ui.RadarListDialog(frame, "Home", main.get_settings(), main.list_data,
                            main.refresh, main.leg_for, main.with_routes, refresh_now=True,
                            listen=main.listen_for_aircraft, emergency_intro=main.emergency_intro)
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

# --- The list's Track button opens Track a flight, filled in -------------------------
seen_track = {}


def inspect_track_dialog():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, fr_ui.TrackFlightDialog) and w.IsModal():
            seen_track["initial"] = w.txt_flight.GetValue()
            w.EndModal(wx.ID_CANCEL)


dlg = fr_ui.RadarListDialog(frame, "Home", main.get_settings(), main.list_data, main.refresh,
                            main.leg_for, main.with_routes, listen=main.listen_for_aircraft,
                            emergency_intro=main.emergency_intro, track=main.track_from_list)
dlg.Show()
wx.Yield()
dlg.list_aircraft.SetSelection(3)
fire(dlg.list_aircraft, wx.EVT_LISTBOX, 3)
closer = wx.CallLater(400, inspect_track_dialog)
fire(dlg.btn_track, wx.EVT_BUTTON)
closer.Stop()
assert seen_track.get("initial") == "BTK6339", seen_track
dlg.Destroy()
wx.Yield()
print("OK list_track_button")

# --- Overhead alerts ----------------------------------------------------------------
prefs = PreferencesDialog(frame, select_tab="Flight Radar")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel.txt_location.GetValue() == "Home: -6.21462, 106.84513"
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
assert not said("Attention:"), "an emergency already heard was repeated"

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

# --- The emergency watch --------------------------------------------------------------
prefs = PreferencesDialog(frame, select_tab="Flight Radar")
prefs.Show()
wx.Yield()
main._panel.chk_emergency.SetValue(True)
prefs.OnApply(None)
prefs.Destroy()
wx.Yield()
assert core.api.load_data("FlightRadar")["emergency_watch"] is True
assert main._poll_timer is not None, "the emergency watch did not start polling"
spoken.clear()
sounds.clear()
# The same aircraft now squawks 7600: a new emergency, announced in the background.
AIRCRAFT["aircraft"][-1] = dict(AIRCRAFT["aircraft"][-1], squawk="7600")
main._cache = None
main._poll_timer.Stop()
main._poll()
assert pump(lambda: said("Attention: X Q Z 777 is squawking 7 6 0 0")), spoken
assert spoken[-1] == ("Attention: X Q Z 777 is squawking 7 6 0 0, radio failure "
                      "(lost communications), 20 kilometres west."), spoken
assert sounds == ["error.wav"], sounds
assert not said("Overhead:"), "overhead alerts are off"
assert main._poll_timer is not None
main._poll_timer.Stop()
main._poll()
pump(lambda: False, timeout=0.6)
assert sum(s.startswith("Attention:") for s in spoken) == 1, spoken   # once per 30 minutes

prefs = PreferencesDialog(frame, select_tab="Flight Radar")
prefs.Show()
wx.Yield()
main._panel.chk_emergency.SetValue(False)
prefs.OnApply(None)
prefs.Destroy()
wx.Yield()
pump(lambda: not main._poll_running, timeout=2)
assert main._poll_timer is None, "polling did not stop"
print("OK emergency_watch")

# --- Track a flight -------------------------------------------------------------------
spoken.clear()
assert run_and_close("Flight Radar.speak_tracked") == []
assert spoken == [_("track_none")], spoken
assert run_and_close("Flight Radar.track_flight") == ["TrackFlightDialog"]

track = fr_ui.TrackFlightDialog(frame, main.tracked_rows, main.track_flight, main.untrack,
                                main.speak_tracked)
track.Show()
wx.Yield()
assert track.list_tracked.GetString(0) == _("tracked_empty")
track.txt_flight.SetFocus()
wx.Yield()
field_focused = wx.Window.FindFocus() is track.txt_flight
track.txt_flight.SetValue("ZZ 12")
fire(track.txt_flight, wx.EVT_TEXT_ENTER)
assert spoken[-1].startswith("Hariku doesn't know the airline code Z Z."), spoken[-1]
track.txt_flight.SetValue("GA 408")
fire(track.txt_flight, wx.EVT_TEXT_ENTER)
assert said("Looking for Garuda Indonesia 408"), spoken
assert pump(lambda: any("Now tracking it" in s for s in spoken)), spoken
report = spoken[-1]
assert report.startswith("Garuda Indonesia 408, ") and "of Jakarta Soekarno-Hatta" in report, report
assert track.list_tracked.GetCount() == 1
assert track.list_tracked.GetString(0).startswith("Garuda Indonesia 408: "), \
    track.list_tracked.GetString(0)
if field_focused:
    assert wx.Window.FindFocus() is track.txt_flight, "focus moved after Track"
assert core.api.load_data("FlightRadar")["tracked"][0]["id"] == "GIA408"
assert main._poll_timer is not None, "tracking did not start polling"
checked = browse(track.list_tracked, wx.EVT_LISTBOX)
spoken.clear()
fire(track.btn_check, wx.EVT_BUTTON)
assert pump(lambda: any(s.startswith("Garuda Indonesia 408, ") for s in spoken)), spoken
# Stop tracking: Delete on the list (or the button when focus can't be observed).
spoken.clear()
if checked:
    track.list_tracked.SetFocus()
    wx.Yield()
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_DELETE)
    track.GetEventHandler().ProcessEvent(key)
else:
    fire(track.btn_untrack, wx.EVT_BUTTON)
assert spoken[-1] == "Stopped tracking Garuda Indonesia 408.", spoken
assert track.list_tracked.GetString(0) == _("tracked_empty")
assert core.api.load_data("FlightRadar")["tracked"] == []
assert main._poll_timer is None, "polling did not stop"
track.Destroy()
wx.Yield()
print(f"OK track_flight ({focus_note(checked and field_focused)})")

# --- Teardown, and nothing went wrong along the way -----------------------------------
em.unload_all_extensions()
for event_name, handler in main._SUBSCRIPTIONS:
    assert handler not in bus._listeners.get(event_name, []), f"{event_name} still subscribed"
assert main._poll_timer is None and main._fetch_timer is None
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
allowed = ("https://opendata.adsb.fi/", "https://api.adsbdb.com/",
           "https://geocoding-api.open-meteo.com/", "https://nominatim.openstreetmap.org/")
assert all(u.startswith(allowed) for u in stub_requests), stub_requests
# The aircraft service only ever saw the rounded point and the widened radius.
radar_requests = [u for u in stub_requests if "adsb.fi/api/v2/lat/" in u]
assert radar_requests and set(radar_requests) == {
    "https://opendata.adsb.fi/api/v2/lat/-6.21/lon/106.85/dist/15"}, set(radar_requests)
assert len([u for u in stub_requests if "nominatim" in u]) == 1
# Tracking only ever sends the callsign.
flight_requests = [u for u in stub_requests if u.startswith(("https://opendata.adsb.fi/",
                                                               "https://api.adsb.lol/"))
                   and ("/callsign/" in u or "/registration/" in u or "/reg/" in u)]
assert flight_requests and set(flight_requests) == {
    "https://opendata.adsb.fi/api/v2/callsign/GIA408"}, set(flight_requests)
# LiveATC is only ever opened in the browser, never fetched.
assert opened_urls and all(u.startswith("https://www.liveatc.net/") for u in opened_urls)
route_requests = [u for u in stub_requests if "adsbdb" in u]
assert len(route_requests) == len(set(route_requests)), f"routes looked up twice: {route_requests}"
# Routes are kept in memory only: nothing about them reaches the data folder,
# including extensions' storage folders inside it.
for folder, _dirs, files in os.walk(core.api.DATA_DIR):
    for name in files:
        path = os.path.join(folder, name)
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        where = os.path.relpath(path, core.api.DATA_DIR)
        assert "Batam" not in content and "Semarang" not in content, f"route data in {where}"
        assert "PK-QQ" not in content, f"aircraft data in {where}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
