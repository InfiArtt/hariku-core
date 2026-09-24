# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Earthquakes & Tsunami extension through the real loader with real
wxPython, open its settings page inside the real Preferences dialog and its
recent list, run its hotkey actions and background alerts, and browse every
list, choice and checkbox the way arrow keys do, checking focus stays put.

BMKG, USGS and Open-Meteo are stubbed (nothing leaves the machine), speech is
captured through on_before_speak, and sounds are recorded instead of played.

Run by tests/test_earthquake_ui.py in a separate process, because conftest.py
mocks wx inside the pytest process. The caller points APPDATA at a temporary
folder so the user's real settings are never touched. Prints one "OK" line
per stage.
"""
import datetime
import logging
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the earthquake check hung", flush=True)
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
    WATCHED = ("hariku_ext.earthquake", "earthquake_", "core.events", "core.hotkeys",
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

heard = []      # (text, interrupt)


def _capture_speech(payload):
    heard.append((payload["text"], payload["interrupt"]))
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)
sounds = []
core.sounds.play_internal_sound = lambda name: sounds.append(name) or True

from ui.main_window import MainWindow
frame = MainWindow(None, title="earthquake check")
print("OK main_window")

G = ord("G")
PLAIN_G = (G, False, False, False, False)
SHIFT_G = (G, False, True, False, False)
assert PLAIN_G not in core.hotkeys.keybindings, "G is already bound by the core"
assert SHIFT_G not in core.hotkeys.keybindings, "Shift+G is already bound by the core"

# --- Stubbed BMKG, USGS and Open-Meteo (times relative to now) ------------------
EQ_DIR = os.path.join(ROOT, "extensions", "earthquake")
sys.path.insert(0, EQ_DIR)
import earthquake_api

UTC = datetime.timezone.utc
NOW = datetime.datetime.now(UTC).replace(microsecond=0)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def _gempa(when, **fields):
    """A BMKG entry in the verified autogempa.json shape, `when` in UTC."""
    local = when + datetime.timedelta(hours=7)
    entry = {"Tanggal": f"{local.day:02d} {_MONTHS[local.month - 1]} {local.year}",
             "Jam": local.strftime("%H:%M:%S") + " WIB",
             "DateTime": when.strftime("%Y-%m-%dT%H:%M:%S+00:00")}
    entry.update(fields)
    return entry


NEAR = _gempa(NOW - datetime.timedelta(minutes=2), Coordinates="-8.21,120.61",
              Lintang="8.21 LS", Bujur="120.61 BT", Magnitude="4.7", Kedalaman="9 km",
              Wilayah="Pusat gempa berada di laut 48 km utara Ruteng-Manggarai",
              Potensi="Gempa ini dirasakan untuk diteruskan pada masyarakat",
              Dirasakan="II - III Kab. Manggarai", Shakemap="x.mmi.jpg")
TSUNAMI = _gempa(NOW - datetime.timedelta(minutes=1), Coordinates="-9.50,112.80",
                 Lintang="9.50 LS", Bujur="112.80 BT", Magnitude="7.1", Kedalaman="10 km",
                 Wilayah="Pusat gempa berada di laut 150 km BaratDaya Jember",
                 Potensi="Berpotensi tsunami untuk diteruskan pada masyarakat",
                 Dirasakan="", Shakemap="y.mmi.jpg")
TERKINI = {"Infogempa": {"gempa": [
    _gempa(NOW - datetime.timedelta(days=2), Coordinates="4.74,125.30", Lintang="4.74 LU",
           Bujur="125.30 BT", Magnitude="5.2", Kedalaman="10 km",
           Wilayah="127 km BaratLaut TAHUNA-KEP.SANGIHE-SULUT", Potensi="Tidak berpotensi tsunami"),
    _gempa(NOW - datetime.timedelta(days=9), Coordinates="-8.42,109.02", Lintang="8.42 LS",
           Bujur="109.02 BT", Magnitude="5.4", Kedalaman="10 km",
           Wilayah="77 km Tenggara CILACAP-JATENG", Potensi="Tidak berpotensi tsunami"),
]}}
DIRASAKAN = {"Infogempa": {"gempa": [
    {k: v for k, v in NEAR.items() if k not in ("Potensi", "Shakemap")},
    _gempa(NOW - datetime.timedelta(days=3), Coordinates="-5.82,122.84", Lintang="5.82 LS",
           Bujur="122.84 BT", Magnitude="3.9", Kedalaman="14 km",
           Wilayah="Pusat gempa berada di laut 32 km selatan Buton", Dirasakan="III Kab. Buton"),
]}}


def _feature(ident, mag, place, when, lon, lat, depth, tsunami=0):
    return {"type": "Feature", "id": ident,
            "properties": {"mag": mag, "place": place, "time": int(when.timestamp() * 1000),
                           "tsunami": tsunami, "title": f"M {mag} - {place}", "type": "earthquake"},
            "geometry": {"type": "Point", "coordinates": [lon, lat, depth]}}


USGS = {"type": "FeatureCollection", "features": [
    _feature("us7000japan", 6.8, "120 km S of Hachijo-jima, Japan",
             NOW - datetime.timedelta(minutes=5), 139.7, 32.0, 35.0, tsunami=1),
    _feature("us6000fiji", 4.6, "Fiji region", NOW - datetime.timedelta(hours=1), 178.0, -17.9, 550.0),
]}
PLACES = {"results": [
    {"name": "Ruteng", "admin1": "East Nusa Tenggara", "admin2": "Kabupaten Manggarai",
     "country": "Indonesia", "latitude": -8.6136, "longitude": 120.4721, "timezone": "Asia/Makassar"},
    {"name": "Ruteng", "admin1": "Somewhere", "country": "Elsewhere",
     "latitude": 1.0, "longitude": 2.0},
]}
RESPONSES = {earthquake_api.AUTOGEMPA_URL: {"Infogempa": {"gempa": NEAR}},
             earthquake_api.TERKINI_URL: TERKINI, earthquake_api.DIRASAKAN_URL: DIRASAKAN,
             earthquake_api.USGS_DAY_URL: USGS, earthquake_api.USGS_HOUR_URL: USGS}
stub_requests = []


def _fake_fetch_json(url):
    stub_requests.append(url)
    if url.startswith(earthquake_api.GEOCODING_URL):
        return PLACES
    if url in RESPONSES:
        return RESPONSES[url]
    raise AssertionError(f"unexpected URL {url}")


earthquake_api.fetch_json = _fake_fetch_json

import core.extension_manager as em
em.load_unpacked_extension(EQ_DIR)
assert "earthquake" in em.LOADED_EXTENSIONS, "Earthquakes extension did not load"
main = em.LOADED_EXTENSIONS["earthquake"]["module"]
eq_ui = sys.modules["earthquake_ui"]
eq_text = sys.modules["earthquake_text"]
assert sys.modules["earthquake_api"] is earthquake_api
assert core.hotkeys.keybindings[PLAIN_G][0] == "Earthquakes.speak_latest"
assert core.hotkeys.keybindings[SHIFT_G][0] == "Earthquakes.show_recent"
# Tsunami alerts are on by default, so the BMKG poll is scheduled; the check
# drives it by hand instead.
assert main._poll_timer is not None, "the tsunami watch did not start"
main._poll_timer.Stop()
main._poll_timer = None
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


def idle():
    """No request in flight or waiting."""
    return main._running is None and not main._queue


def stop_polls():
    for name in ("_poll_timer", "_world_timer"):
        timer = getattr(main, name)
        if timer is not None:
            timer.Stop()
            setattr(main, name, None)


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


def texts():
    return [t for t, _interrupt in heard]


def said(prefix):
    return any(t.startswith(prefix) for t in texts())


_ = eq_text._
DISCLAIMER = ("Hariku is not an official warning system. "
              "Always follow BMKG and your local authorities.")
ATTRIBUTION = ("Earthquake data: BMKG (Badan Meteorologi, Klimatologi, dan Geofisika) "
               "and USGS")
assert _("disclaimer") == DISCLAIMER and _("attribution") == ATTRIBUTION

# The main place (Preferences, Places) is the default location; the Weather
# city is no longer used by itself. The place is called "Rumah" by the user,
# in the town of Ruteng: distances name the place, felt reports look for the town.
import core.places
core.api.save_data("Weather", {"location": {"name": "Ruteng", "admin1": "East Nusa Tenggara",
                                            "country": "Indonesia", "latitude": -8.6136,
                                            "longitude": 120.4721}, "units": "metric"})
assert main.get_location() is None, "the Weather city is no longer used by itself"
rumah_place, = core.places.set_places([{
    "name": "Rumah", "lat": -8.6136, "lon": 120.4721,
    "label": "Ruteng, East Nusa Tenggara, Indonesia", "timezone": "Asia/Makassar",
    "source": "city", "city": "Ruteng", "region": "East Nusa Tenggara", "country": "Indonesia"}])
assert main.get_location()["name"] == "Rumah" and main.get_location()["city"] == "Ruteng"

# --- G: the latest earthquake, spoken; no window -------------------------------
heard.clear()
assert run_and_close("Earthquakes.speak_latest") == []
assert texts()[0] == _("checking"), heard
assert pump(lambda: said("Latest earthquake according to BMKG")), heard
report, interrupt = heard[-1]
assert interrupt, "the report should interrupt"
assert report.startswith("Latest earthquake according to BMKG: magnitude 4.7, depth 9 kilometres, "
                         "Pusat gempa berada di laut 48 km utara Ruteng-Manggarai. "
                         "47 kilometres north of Rumah. Time: "), report
assert report.endswith("Felt, on the MMI scale: II - III Kab. Manggarai. "
                       "BMKG says: Gempa ini dirasakan untuk diteruskan pada masyarakat."), report
assert sounds == [], sounds
assert pump(idle)
print("OK latest_action")

# --- A tsunami-potential quake: announced first, urgent, with its own sound -----
heard.clear()
RESPONSES[earthquake_api.AUTOGEMPA_URL] = {"Infogempa": {"gempa": TSUNAMI}}
main._poll()
assert pump(lambda: said("Tsunami potential, according to BMKG.")), heard
alert, interrupt = heard[-1]
assert interrupt is True, "a tsunami alert must interrupt"
assert alert.startswith("Tsunami potential, according to BMKG. BMKG says: Berpotensi tsunami "
                        "untuk diteruskan pada masyarakat. Earthquake: magnitude 7.1"), alert
assert "850 kilometres west of Rumah" in alert, alert
assert alert.endswith(DISCLAIMER), "the first alert of the session carries the disclaimer"
assert sounds == ["error.wav"], sounds
assert pump(lambda: not main._poll_running and main._poll_timer is not None)
stop_polls()
main._poll()                               # the same quake again: not repeated
assert pump(lambda: not main._poll_running)
pump(lambda: False, timeout=0.3)
assert len(heard) == 1, heard
stop_polls()
print("OK tsunami_alert")

# --- Preferences page: disclaimer, credits, the place choice, search, browse, save --
from ui.preferences_dialog import PreferencesDialog

FELT_NOTE = "Felt alerts look for these names in BMKG's felt reports: {}."
OWN = "Its own place…"

prefs = PreferencesDialog(frame, select_tab="Earthquakes")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "Earthquakes settings page was not created"
choice = panel.place_choice.ctrl
assert choice.GetName() == "Place", choice.GetName()
assert choice.GetStrings() == ["The main place (Rumah)", "Rumah", OWN], choice.GetStrings()
assert panel.place_choice.key() == "main" and choice.GetSelection() == 0
assert panel.txt_location.GetValue() == _("location_not_set"), panel.txt_location.GetValue()
# The city search is for its own place only: skipped while another place is chosen.
assert not panel.txt_search.IsEnabled() and not panel.btn_search.IsEnabled()
assert not panel.list_results.IsEnabled() and not panel.txt_location.IsEnabled()
labels = [w.GetLabel() for w in panel.GetChildren() if isinstance(w, wx.StaticText)]
assert DISCLAIMER in labels, labels
assert ATTRIBUTION in labels, labels
# Felt reports are searched for the main place's town, never its name ("Rumah").
assert panel.lbl_felt_note.GetLabel() == FELT_NOTE.format("Ruteng"), panel.lbl_felt_note.GetLabel()
assert panel.chk_tsunami.GetValue() is True
assert not panel.chk_nearby.GetValue() and not panel.chk_felt.GetValue()
assert not panel.chk_world.GetValue() and panel.chk_sounds.GetValue()
assert panel.choice_distance.GetString(panel.choice_distance.GetSelection()) == "300 kilometres"
assert panel.choice_magnitude.GetString(panel.choice_magnitude.GetSelection()) == "4.0"
assert panel.choice_distance.GetCount() == 4 and panel.choice_magnitude.GetCount() == 7

# Arrowing through the places: focus stays; the last one, "Its own place", opens the search.
checked = browse(choice, wx.EVT_CHOICE)
assert panel.place_choice.key() == "own", panel.place_choice.key()
assert panel.txt_search.IsEnabled() and panel.btn_search.IsEnabled()
assert panel.list_results.IsEnabled() and panel.txt_location.IsEnabled()
assert panel.lbl_felt_note.GetLabel() == _("felt_note_none"), panel.lbl_felt_note.GetLabel()

panel.txt_search.SetValue("R")
fire(panel.txt_search, wx.EVT_TEXT_ENTER)
assert texts()[-1] == _("search_too_short"), heard[-1]

panel.txt_search.SetValue("Ruteng")
panel.txt_search.SetFocus()
wx.Yield()
search_focused = wx.Window.FindFocus() is panel.txt_search
fire(panel.txt_search, wx.EVT_TEXT_ENTER)
assert pump(lambda: panel.list_results.GetCount() == 2), "search results never arrived"
assert panel.list_results.GetString(0) == "Ruteng, East Nusa Tenggara, Indonesia"
if search_focused:
    assert wx.Window.FindFocus() is panel.list_results, "focus did not move to the results"
checked = browse(panel.list_results, wx.EVT_LISTBOX) and checked
for choice_ctrl in (panel.choice_distance, panel.choice_magnitude):
    checked = browse(choice_ctrl, wx.EVT_CHOICE) and checked
for checkbox in (panel.chk_tsunami, panel.chk_nearby, panel.chk_felt, panel.chk_world,
                 panel.chk_sounds):
    checked = toggle(checkbox) and checked

# Back to the main place and to its own place again: the search and the felt note follow.
choice.SetSelection(0)
fire(choice, wx.EVT_CHOICE, 0)
assert panel.place_choice.key() == "main" and not panel.txt_search.IsEnabled()
assert panel.lbl_felt_note.GetLabel() == FELT_NOTE.format("Ruteng"), panel.lbl_felt_note.GetLabel()
choice.SetSelection(2)
fire(choice, wx.EVT_CHOICE, 2)
assert panel.place_choice.key() == "own" and panel.txt_search.IsEnabled()
panel.list_results.SetSelection(0)
fire(panel.list_results, wx.EVT_LISTBOX, 0)
assert panel.chosen_location()["admin2"] == "Kabupaten Manggarai", panel.chosen_location()
assert panel.lbl_felt_note.GetLabel() == FELT_NOTE.format("Ruteng, Manggarai"), \
    panel.lbl_felt_note.GetLabel()
print(f"OK panel_browse ({focus_note(checked)})")

panel.list_results.SetSelection(0)
panel.choice_distance.SetSelection(1)
panel.choice_magnitude.SetSelection(2)
panel.chk_nearby.SetValue(True)
panel.chk_felt.SetValue(True)
panel.txt_felt_names.SetValue("Kota Bima")
prefs.OnApply(None)
saved = core.api.load_data("Earthquake")
assert saved["place"] == "own", saved
assert saved["location"]["name"] == "Ruteng" and saved["location"]["admin2"] == "Kabupaten Manggarai", saved
assert saved["tsunami_alerts"] is True and saved["nearby_alerts"] is True, saved
assert saved["felt_alerts"] is True and saved["world_alerts"] is False, saved
assert saved["alert_km"] == 300 and saved["min_magnitude"] == 4.0, saved
assert saved["felt_names"] == "Kota Bima", saved
assert main.get_location()["name"] == "Ruteng" and "place_id" not in main.get_location()
assert panel.txt_location.GetValue() == "Ruteng, East Nusa Tenggara, Indonesia"
assert panel.lbl_felt_note.GetLabel() == FELT_NOTE.format("Ruteng, Manggarai, Bima"), \
    panel.lbl_felt_note.GetLabel()
prefs.Destroy()
wx.Yield()
stop_polls()

# Back to the main place: choose it, then OK keeps its own city for later.
prefs = PreferencesDialog(frame, select_tab="Earthquakes")
prefs.Show()
wx.Yield()
panel = main._panel
choice = panel.place_choice.ctrl
assert panel.place_choice.key() == "own" and choice.GetSelection() == 2
assert panel.txt_location.GetValue() == "Ruteng, East Nusa Tenggara, Indonesia"
assert panel.txt_search.IsEnabled()
choice.SetSelection(0)
fire(choice, wx.EVT_CHOICE, 0)
assert not panel.txt_search.IsEnabled()
assert panel.lbl_felt_note.GetLabel() == FELT_NOTE.format("Ruteng, Bima"), \
    panel.lbl_felt_note.GetLabel()
prefs.OnApply(None)
saved = core.api.load_data("Earthquake")
assert saved["place"] == "main" and saved["nearby_alerts"] is True, saved
assert saved["location"]["name"] == "Ruteng", "its own city is kept for later"
assert main.get_location()["name"] == "Rumah"      # the main place
assert panel.txt_location.GetValue() == "Ruteng, East Nusa Tenggara, Indonesia"
assert panel.lbl_felt_note.GetLabel() == FELT_NOTE.format("Ruteng, Bima"), \
    panel.lbl_felt_note.GetLabel()
prefs.Destroy()
wx.Yield()
stop_polls()
print("OK panel_apply")

# --- The places change while the page is open: the list follows, the choice stays -----
prefs = PreferencesDialog(frame, select_tab="Earthquakes")
prefs.Show()
wx.Yield()
panel = main._panel
choice = panel.place_choice.ctrl
assert panel.place_choice.key() == "main" and not panel.txt_search.IsEnabled()
choice.SetFocus()
wx.Yield()
choice_focused = wx.Window.FindFocus() is choice
office = {"name": "Kantor", "lat": -8.66, "lon": 121.05, "label": "", "source": "coordinates"}
core.places.set_places([rumah_place, office])      # what the Places page does on OK
assert choice.GetStrings() == ["The main place (Rumah)", "Rumah", "Kantor", OWN], \
    choice.GetStrings()
assert panel.place_choice.key() == "main" and choice.GetSelection() == 0
if choice_focused:
    assert wx.Window.FindFocus() is choice, "focus moved when the places changed"
# Choosing a saved place is what OK saves. Pasted coordinates have no town, so
# only the names typed in are looked for.
choice.SetSelection(2)
fire(choice, wx.EVT_CHOICE, 2)
assert panel.place_choice.key() == core.places.get_places()[1]["id"]
assert not panel.txt_search.IsEnabled()
assert panel.lbl_felt_note.GetLabel() == FELT_NOTE.format("Bima"), panel.lbl_felt_note.GetLabel()
if choice_focused:
    assert wx.Window.FindFocus() is choice, "focus moved when a place was chosen"
prefs.OnApply(None)
saved = core.api.load_data("Earthquake")
assert saved["place"] == core.places.get_places()[1]["id"], saved
assert saved["location"]["name"] == "Ruteng", "its own city is kept for later"
assert main.get_location()["name"] == "Kantor"
# Back to the main place for the checks below.
choice.SetSelection(0)
fire(choice, wx.EVT_CHOICE, 0)
prefs.OnApply(None)
assert core.api.load_data("Earthquake")["place"] == "main"
assert main.get_location()["name"] == "Rumah"
prefs.Destroy()
wx.Yield()
stop_polls()
print(f"OK places_changed ({focus_note(choice_focused)})")

# --- Shift+G opens the list; Escape closes it -----------------------------------
assert run_and_close("Earthquakes.show_recent") == ["RecentDialog"]
assert pump(idle), "the list's fetch never finished"
state = {}


def press_escape():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, eq_ui.RecentDialog) and w.IsModal():
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
core.hotkeys.actions["Earthquakes.show_recent"].callback()
guard.Stop()
escape.Stop()
assert state.get("found") and not state.get("forced"), f"Escape did not close the list: {state}"
assert pump(idle)
print("OK recent_action")

# --- The list: rows, browse, details (button and Enter), worldwide, refresh ------
dlg = eq_ui.RecentDialog(frame, main.list_data, main.refresh_list, main.get_location,
                         list_world=False, set_list_world=main.set_list_world,
                         request_world=main.refresh_world, now=main._wall)
dlg.Show()
wx.Yield()
rows = [dlg.list_quakes.GetString(i) for i in range(dlg.list_quakes.GetCount())]
assert len(rows) == 5, rows
assert rows[0].startswith("Tsunami potential, according to BMKG. Magnitude 7.1"), rows[0]
assert rows[1].startswith("Magnitude 4.7, Pusat gempa berada di laut 48 km utara Ruteng-Manggarai, "
                          "depth 9 kilometres, "), rows[1]
assert rows[1].endswith("47 kilometres north of Rumah. Felt: II - III Kab. Manggarai."), rows[1]
assert rows[2].startswith("Magnitude 5.2, 127 km BaratLaut TAHUNA"), rows[2]
assert not any("USGS" in r for r in rows), rows
assert dlg.lbl_status.GetLabel().startswith("Last updated "), dlg.lbl_status.GetLabel()
checked = browse(dlg.list_quakes, wx.EVT_LISTBOX)
dlg.list_quakes.SetSelection(1)
fire(dlg.list_quakes, wx.EVT_LISTBOX, 1)
details = dlg.txt_details.GetValue()
assert details.startswith("Magnitude: 4.7\n"), details
assert "Coordinates: 8.21 LS, 120.61 BT" in details and details.endswith("Source: BMKG"), details

heard.clear()
dlg.list_quakes.SetFocus()
wx.Yield()
list_focused = wx.Window.FindFocus() is dlg.list_quakes
fire(dlg.btn_details, wx.EVT_BUTTON)
assert texts()[-1].startswith("Magnitude: 4.7. Time: "), heard
assert "BMKG says: Gempa ini dirasakan untuk diteruskan pada masyarakat." in texts()[-1]
assert dlg.list_quakes.GetSelection() == 1, "the selection moved"
if list_focused:
    dlg.list_quakes.SetSelection(0)
    heard.clear()
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_RETURN)
    dlg.GetEventHandler().ProcessEvent(key)
    assert texts() and texts()[-1].startswith("Tsunami potential, according to BMKG. "
                                              "Magnitude: 7.1."), heard
    assert wx.Window.FindFocus() is dlg.list_quakes, "focus left the list after Enter"

# Worldwide: ticking the box fetches USGS and adds its rows; focus stays.
dlg.chk_world.SetFocus()
wx.Yield()
world_focused = wx.Window.FindFocus() is dlg.chk_world
heard.clear()
dlg.chk_world.SetValue(True)
fire(dlg.chk_world, wx.EVT_CHECKBOX, 1)
assert pump(lambda: any("USGS" in dlg.list_quakes.GetString(i)
                        for i in range(dlg.list_quakes.GetCount()))), "USGS rows never arrived"
assert pump(lambda: said("6 earthquakes listed.")), heard
assert core.api.load_data("Earthquake")["list_world"] is True
rows = [dlg.list_quakes.GetString(i) for i in range(dlg.list_quakes.GetCount())]
usgs_rows = [r for r in rows if r.endswith("Source: USGS.")]
assert len(usgs_rows) == 1 and rows.index(usgs_rows[0]) == 2, rows   # newest first
assert usgs_rows[0].startswith("Magnitude 6.8, 120 km S of Hachijo-jima, Japan"), usgs_rows
assert not any("Fiji" in r for r in rows), "USGS quakes below magnitude 5 are not listed"
if world_focused:
    assert wx.Window.FindFocus() is dlg.chk_world, "focus left the worldwide checkbox"
checked = toggle(dlg.chk_world) and checked     # off and on again: still included
assert pump(idle)
assert dlg.chk_world.GetValue() and core.api.load_data("Earthquake")["list_world"] is True

heard.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert texts()[0] == _("status_refreshing"), heard
assert pump(lambda: said("6 earthquakes listed.")), heard
dlg.Destroy()
wx.Yield()

# A list closed while its refresh is running must not break anything.
dlg = eq_ui.RecentDialog(frame, main.list_data, main.refresh_list, main.get_location,
                         refresh_now=True, now=main._wall)
dlg.Destroy()
assert pump(idle), "fetch never finished"
print(f"OK list_dialog ({focus_note(checked)})")

# --- Nearby and felt alerts (now on), once each ---------------------------------
heard.clear()
sounds.clear()
nearer = _gempa(NOW - datetime.timedelta(seconds=30), Coordinates="-8.40,120.50",
                Lintang="8.40 LS", Bujur="120.50 BT", Magnitude="4.2", Kedalaman="12 km",
                Wilayah="Pusat gempa berada di darat 20 km utara Ruteng",
                Potensi="Tidak berpotensi tsunami", Dirasakan="III Ruteng")
RESPONSES[earthquake_api.AUTOGEMPA_URL] = {"Infogempa": {"gempa": nearer}}
main._poll()
assert pump(lambda: said("Earthquake near you, according to BMKG: magnitude 4.2")), heard
alert, interrupt = heard[-1]
assert interrupt is False and not alert.endswith(DISCLAIMER), alert   # disclaimer said already
assert alert.endswith("BMKG says: Tidak berpotensi tsunami."), alert
assert sounds == ["info.wav"], sounds
assert pump(lambda: not main._poll_running)
stop_polls()
main._poll()
assert pump(lambda: not main._poll_running)
pump(lambda: False, timeout=0.3)
assert sum(t.startswith("Earthquake near you") for t in texts()) == 1, heard
stop_polls()
print("OK nearby_alert")

# --- Worldwide alerts (opt-in) ----------------------------------------------------
main._save_settings({"world_alerts": True})
assert main._world_timer is not None, "worldwide polling did not start"
heard.clear()
sounds.clear()
main._world_timer.Stop()
main._world_timer = None
main._world_poll()
assert pump(lambda: said("Strong earthquake, according to USGS: magnitude 6.8")), heard
assert "The flag alone does not mean a tsunami was generated." in texts()[-1]
assert sounds == ["info.wav"], sounds
main._save_settings({"world_alerts": False})
assert pump(lambda: not main._world_running)
assert main._world_timer is None, "worldwide polling did not stop"
stop_polls()
print("OK world_alert")

# --- Morning Briefing contribution, from the cache -------------------------------
lines = []
bus.emit("on_briefing_collect", lines)
assert len(lines) == 1, lines
assert lines[0].startswith("Earthquake near you in the last 24 hours, according to BMKG: "
                           "magnitude 4.2, "), lines
print("OK briefing")

# --- Teardown, and nothing went wrong along the way ------------------------------
assert pump(idle)
em.unload_all_extensions()
for event_name, handler in main._SUBSCRIPTIONS:
    assert handler not in bus._listeners.get(event_name, []), event_name
assert main._poll_timer is None and main._world_timer is None and not main._active
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
allowed = ("https://data.bmkg.go.id/DataMKG/TEWS/", "https://earthquake.usgs.gov/earthquakes/feed/",
           "https://geocoding-api.open-meteo.com/")
assert all(u.startswith(allowed) for u in stub_requests), stub_requests
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
