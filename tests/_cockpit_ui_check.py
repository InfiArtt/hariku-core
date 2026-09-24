# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Cockpit extension (and Sound Themes) through the real loader with
real wxPython, open Cockpit's settings inside the real Preferences dialog, add
favourite airports with a faked aviationweather.gov, turn Captain mode on
(answering its offers from a timer), install the sound theme, run both hotkey
actions, open the Airport weather window and arrow through it checking focus
stays put, then check the Briefing, the evening summary, %airportweather% and
the cockpit greeting, and turn Captain mode off again.

aviationweather.gov is faked (nothing leaves the machine; urlopen is blocked
and any attempt fails the check), speech is captured through on_before_speak,
and sounds are recorded instead of played. Run by tests/test_cockpit_ui.py in
a separate process with APPDATA pointing at a temporary folder. Prints one
"OK" line per stage.
"""
import datetime
import logging
import os
import sys
import threading
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the cockpit check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(170, _watchdog)
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
    WATCHED = ("hariku_ext.cockpit", "cockpit_", "hariku_ext.sound_themes", "sound_themes_",
               "core.events", "core.hotkeys", "core.extension_manager", "core.personal",
               "core.sounds", "ui.preferences_dialog")

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
import core.personal
import core.sounds
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)
sounds = []
core.sounds.play_internal_sound = lambda name: sounds.append(name) or True
core.sounds.play_sound = lambda path: sounds.append(path) or True
# The scratchpad folder matches the Extensions page's default, so Apply
# doesn't ask to restart.
core.api.save_data("Core", {"onboarding_completed": True, "user_name": "Rafli",
                            "user_nickname": "Bro", "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad")})

from ui.main_window import MainWindow
frame = MainWindow(None, title="cockpit check")
print("OK main_window")

PLAIN_Q = (ord("Q"), False, False, False, False)
SHIFT_Q = (ord("Q"), False, True, False, False)
assert PLAIN_Q not in core.hotkeys.keybindings, "Q is already bound by the core"
assert SHIFT_Q not in core.hotkeys.keybindings, "Shift+Q is already bound by the core"

# --- A fake aviationweather.gov, around the real "now" ---------------------------------
COCKPIT_DIR = os.path.join(ROOT, "extensions", "cockpit")
THEMES_DIR = os.path.join(ROOT, "extensions", "sound_themes")
sys.path.insert(0, COCKPIT_DIR)
import cockpit_api

NOW = datetime.datetime.now(datetime.timezone.utc)
OBS = (NOW - datetime.timedelta(minutes=10)).replace(second=0, microsecond=0)
STAMP = OBS.strftime("%d%H%MZ")


def _metar(icao, name, body, lat, lon):
    return {"icaoId": icao, "obsTime": int(OBS.timestamp()), "name": name,
            "rawOb": f"METAR {icao} {STAMP} {body}", "lat": lat, "lon": lon}


METARS = {
    "WIDD": _metar("WIDD", "Batam/Hang Nadim, RI, ID", "20006KT 7000 FEW014 30/25 Q1013 NOSIG",
                   1.121, 104.119),
    "WIII": _metar("WIII", "Jakarta/Hatta Intl, JB, ID",
                   "04011KT 360V060 7000 FEW020 33/24 Q1012 NOSIG", -6.125, 106.659),
    "WSSS": _metar("WSSS", "Singapore/Changi Intl, 4, SG",
                   "18005KT 150V210 9999 FEW018 BKN150 31/25 Q1013 NOSIG", 1.368, 103.982),
}
VALID_FROM = (NOW - datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
VALID_TO = VALID_FROM + datetime.timedelta(hours=42)


def _taf(icao, name):
    head = f"TAF {icao} {VALID_FROM.strftime('%d%H')}00Z " \
           f"{VALID_FROM.strftime('%d%H')}/{VALID_TO.strftime('%d%H')}"
    return {"icaoId": icao, "name": name, "issueTime": VALID_FROM.isoformat().replace("+00:00", "Z"),
            "validTimeFrom": int(VALID_FROM.timestamp()), "validTimeTo": int(VALID_TO.timestamp()),
            "rawTAF": f"{head} 13006KT 7000 SCT020 TEMPO "
                      f"{VALID_FROM.strftime('%d%H')}/{(VALID_FROM + datetime.timedelta(hours=4)).strftime('%d%H')}"
                      f" 4000 TSRA FEW015CB"}


TAFS = {"WIDD": _taf("WIDD", "Batam/Hang Nadim"), "WIII": _taf("WIII", "Jakarta/Hatta Intl")}
BATAM = {"name": "Batam", "admin1": "Riau Islands", "country": "Indonesia",
         "latitude": 1.14937, "longitude": 104.02491, "timezone": "Asia/Jakarta"}
stub_requests = []


def _fake_fetch_json(url):
    stub_requests.append(url)
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(parts.query)
    ids = query.get("ids", [""])[0].split(",")
    if parts.path.endswith("/metar") and "bbox" in query:
        return [dict(m) for m in METARS.values()]
    if parts.path.endswith("/metar"):
        return [dict(METARS[i]) for i in ids if i in METARS]
    if parts.path.endswith("/taf"):
        return [dict(TAFS[i]) for i in ids if i in TAFS]
    if parts.path.endswith("/stationinfo"):
        return []
    raise AssertionError(f"unexpected URL {url}")


cockpit_api.fetch_json = _fake_fetch_json

import core.extension_manager as em
em.load_unpacked_extension(THEMES_DIR)
em.load_unpacked_extension(COCKPIT_DIR)
assert "cockpit" in em.LOADED_EXTENSIONS, "Cockpit did not load"
assert "sound_themes" in em.LOADED_EXTENSIONS, "Sound Themes did not load"
main = em.LOADED_EXTENSIONS["cockpit"]["module"]
cockpit_ui = sys.modules["cockpit_ui"]
cockpit_text = sys.modules["cockpit_text"]
assert sys.modules["cockpit_api"] is cockpit_api
assert core.hotkeys.keybindings[PLAIN_Q][0] == "Cockpit.pilot_weather"
assert core.hotkeys.keybindings[SHIFT_Q][0] == "Cockpit.airport_weather"
assert core.personal.is_placeholder_registered("airportweather")
_ = cockpit_text._
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


# Captain mode's offers are answered "Yes" from a timer, as a user would.
offers = []


def _answer_offers():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, cockpit_ui.YesNoDialog) and w.IsModal():
            offers.append(w.lbl_message.GetLabel())
            assert w.GetEscapeId() == wx.ID_NO and w.GetDefaultItem() is w.btn_yes
            w.EndModal(wx.ID_YES)


offer_timer = wx.Timer()
offer_timer.Bind(wx.EVT_TIMER, lambda e: _answer_offers())

# --- No airport and no city: spoken hints ------------------------------------------------
spoken.clear()
assert run_and_close("Cockpit.pilot_weather") == []
assert spoken == [_("no_airport")], spoken
assert run_and_close("Cockpit.airport_weather") == ["AirportWeatherDialog"]
assert stub_requests == [], stub_requests
print("OK no_airport_hint")

# --- The main place (Preferences, Places): the nearest airport, said which ------------
import core.places
core.api.save_data("Weather", {"location": BATAM, "units": "metric"})
spoken.clear()
assert run_and_close("Cockpit.pilot_weather") == []
assert spoken == [_("no_airport")], "the Weather city is no longer used by itself"
assert stub_requests == [], stub_requests
batam_place, = core.places.set_places([{
    "name": "Batam", "lat": BATAM["latitude"], "lon": BATAM["longitude"],
    "label": "Batam, Riau Islands, Indonesia", "timezone": "Asia/Jakarta", "source": "city",
    "city": "Batam", "region": "Riau Islands", "country": "Indonesia"}])
assert stub_requests == [], "Captain mode is off: nothing is looked up in the background"
spoken.clear()
assert run_and_close("Cockpit.pilot_weather") == []
assert spoken[0] == "Looking for the airport nearest to Batam...", spoken
assert pump(lambda: len(spoken) >= 2), spoken
assert spoken[1].startswith("No favourite airports yet, so Hariku uses Batam Hang Nadim, W I D D, "
                            "the nearest airport with a weather report to Batam."), spoken
assert "bbox=0.1%2C103.0%2C2.1%2C105.0" in stub_requests[-1], stub_requests
# Only the rounded place is kept with the airport found for it.
assert core.api.load_data("Cockpit")["auto"]["for"] == {"name": "Batam", "latitude": 1.15,
                                                        "longitude": 104.02}
print("OK nearest")

# --- Preferences: favourites, Captain mode, the sound theme ---------------------------------
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Cockpit")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "Cockpit settings page was not created"
labels = [w.GetLabel() for w in panel.GetChildren() if isinstance(w, wx.StaticText)]
assert "Aviation weather: NOAA Aviation Weather Center (aviationweather.gov)" in labels, labels
assert "For information only, not for flight planning." in labels, labels
assert panel.list_airports.GetName() == "Favourite airports (the first one is your default)"
assert panel.txt_code.GetName() == "ICAO code of an airport to add (press Enter to add)"
assert panel.list_airports.GetStrings() == [
    "No favourite airports yet. Hariku uses Batam Hang Nadim, W I D D, nearest to Batam."], \
    panel.list_airports.GetStrings()
assert not panel.chk_captain.GetValue()
# The place for the nearest airport: the main place or a saved one (no place of its own).
place_choice = panel.place_choice.ctrl
assert place_choice.GetName() == "Place, for the nearest airport when you have no favourites", \
    place_choice.GetName()
assert place_choice.GetStrings() == ["The main place (Batam)", "Batam"], place_choice.GetStrings()
assert panel.place_choice.key() == "main"
place_focus = browse(place_choice, wx.EVT_CHOICE)
place_choice.SetSelection(0)
fire(place_choice, wx.EVT_CHOICE, 0)
assert panel.place_choice.key() == "main"

panel.txt_code.SetValue("WI")
fire(panel.txt_code, wx.EVT_TEXT_ENTER)
assert spoken[-1] == _("err_not_icao"), spoken[-1]
panel.txt_code.SetValue("widd")
panel.txt_code.SetFocus()
wx.Yield()
code_focused = wx.Window.FindFocus() is panel.txt_code
fire(panel.txt_code, wx.EVT_TEXT_ENTER)
assert pump(lambda: said("Added Batam Hang Nadim")), spoken
assert panel.list_airports.GetStrings() == ["Batam Hang Nadim, W I D D, default"], \
    panel.list_airports.GetStrings()
assert panel.txt_code.GetValue() == ""
if code_focused:
    assert wx.Window.FindFocus() is panel.txt_code, "focus left the code field after adding"
panel.txt_code.SetValue("WIII")
fire(panel.btn_add, wx.EVT_BUTTON)
assert pump(lambda: said("Added Jakarta Hatta International")), spoken
assert [a["icao"] for a in core.api.load_data("Cockpit")["favourites"]] == ["WIDD", "WIII"]
checked = browse(panel.list_airports, wx.EVT_LISTBOX) and place_focus
checked = toggle(panel.chk_raw) and checked
checked = toggle(panel.chk_briefing) and checked
panel.list_airports.SetSelection(1)
fire(panel.btn_default, wx.EVT_BUTTON)
assert spoken[-1] == "Jakarta Hatta International is now your default airport.", spoken[-1]
assert panel.list_airports.GetString(0) == "Jakarta Hatta International, W I I I, default"
panel.list_airports.SetSelection(1)
fire(panel.btn_default, wx.EVT_BUTTON)
assert panel.list_airports.GetString(0) == "Batam Hang Nadim, W I D D, default"
print(f"OK panel_favourites ({focus_note(checked)})")

# The sound theme, written into Sound Themes' folder in its format.
spoken.clear()
fire(panel.btn_sound_theme, wx.EVT_BUTTON)
assert pump(lambda: said("The Cockpit sound theme is installed.")), spoken
themes_store = sys.modules["sound_themes_store"]
assert "Cockpit" in themes_store.list_themes(), themes_store.list_themes()
assert sorted(themes_store.custom_sounds("Cockpit")) == [
    "confirm.wav", "error.wav", "info.wav", "penClick.wav", "reminder.wav", "start.wav"]
assert core.sounds.get_theme_dir() is None     # installed, not switched on
print("OK sound_theme")

# Captain mode: saved on Apply, with the two offers answered Yes.
captain_focus = toggle(panel.chk_captain)       # ticking alone asks nothing
assert offers == [], offers
panel.chk_captain.SetValue(True)
offer_timer.Start(200)
prefs.OnApply(None)
assert pump(lambda: len(offers) >= 2, timeout=8), offers
offer_timer.Stop()
assert offers[0].startswith("Shall Hariku call you Captain?"), offers
assert offers[1].startswith("Set a cockpit greeting for when Hariku starts?"), offers
saved = core.api.load_data("Cockpit")
assert saved["captain"] is True and saved["raw"] is False and saved["briefing"] is False, saved
assert saved["place"] == "main", saved
assert core.personal.get_title() == "Captain"
assert core.personal.get_custom_greeting()["text"] == _("cockpit_greeting")
# The Profile page, built in the same session, doesn't undo what Captain mode set.
prefs.realize_all()
prefs.OnApply(None)
assert core.personal.get_title() == "Captain"
prefs.Destroy()
wx.Yield()
print(f"OK captain_on ({focus_note(captain_focus)})")

# --- Hotkey actions ------------------------------------------------------------------------
spoken.clear()
assert run_and_close("Cockpit.pilot_weather") == []
assert pump(lambda: said("Batam Hang Nadim, Whiskey India Delta Delta, at ")), spoken
assert "Flight category: marginal V F R" in spoken[-1], spoken[-1]
assert run_and_close("Cockpit.airport_weather") == ["AirportWeatherDialog"]
print("OK actions")

# --- The Airport weather window --------------------------------------------------------------
dlg = cockpit_ui.AirportWeatherDialog(frame, main.WindowActions)
dlg.Show()
wx.Yield()
assert pump(lambda: not main.is_loading()), "the refresh never finished"
rows = dlg.list_airports.GetStrings()
assert len(rows) == 2 and rows[0].startswith("Batam Hang Nadim, Whiskey India Delta Delta, "
                                             "default: a few clouds, 30 degrees"), rows
assert dlg.list_airports.GetName() == "Your airports"
report = dlg.txt_report.GetValue()
assert "Wind from 200 degrees at 6 knots." in report and "Forecast (TAF)" in report, report
assert dlg.txt_raw.GetValue().startswith("METAR WIDD "), dlg.txt_raw.GetValue()
checked = browse(dlg.list_airports, wx.EVT_LISTBOX)
dlg.list_airports.SetSelection(1)
fire(dlg.list_airports, wx.EVT_LISTBOX, 1)
assert "Wind from 40 degrees at 11 knots" in dlg.txt_report.GetValue()
spoken.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert spoken == [_("up_to_date")], spoken
assert dlg.list_airports.GetSelection() == 1, "the selection moved after Refresh"

# Add an airport through the real dialog, typed from a timer.
cockpit_ui_state = {}


def _type_code():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, cockpit_ui.AddAirportDialog) and w.IsModal():
            cockpit_ui_state["name"] = w.txt_code.GetName()
            w.txt_code.SetValue("wsss")
            w.EndModal(wx.ID_OK)


wx.CallLater(400, _type_code)
fire(dlg.btn_add, wx.EVT_BUTTON)
assert cockpit_ui_state.get("name", "").startswith("ICAO code of the airport"), cockpit_ui_state
assert pump(lambda: said("Added Singapore Changi International")), spoken
assert len(dlg.list_airports.GetStrings()) == 3
dlg.Destroy()
wx.Yield()
print(f"OK window_browse ({focus_note(checked)})")

# --- Escape closes the window -------------------------------------------------------------------
state = {}


def press_escape():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, cockpit_ui.AirportWeatherDialog) and w.IsModal():
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
core.hotkeys.actions["Cockpit.airport_weather"].callback()
guard.Stop()
escape.Stop()
assert state.get("found") and not state.get("forced"), f"Escape did not close the window: {state}"
print("OK escape")

# --- The Briefing, the evening summary, %airportweather% and the greeting ----------------------
before = len(stub_requests)
lines = []
bus.emit("on_briefing_collect", lines)
assert any(line.startswith("It's ") and " Zulu. Hang Nadim: wind from 200 degrees" in line
           for line in lines), lines
lines = []
bus.emit("on_evening_collect", lines)
assert any(line.startswith("Tomorrow morning at Hang Nadim: ") for line in lines), lines
assert core.personal.expand("%airportweather%").startswith("Hang Nadim: wind from 200 degrees")
greeting = core.personal.startup_speech("Welcome to Hariku.", boot=True)
assert greeting.startswith("Welcome aboard, Captain Bro. Welcome to your cockpit."), greeting
assert "Hang Nadim: wind from 200 degrees" in greeting and "%" not in greeting, greeting
bus.emit("on_minute_tick", datetime.datetime.now())
pump(lambda: False, timeout=0.3)
assert len(stub_requests) == before, "the Briefing or a fresh cache caused a request"
print("OK briefing")

# --- Captain mode off: its offers take back the title and the greeting --------------------------
offers.clear()
offer_timer.Start(200)
main.apply_settings({"captain": False})
offer_timer.Stop()
assert offers == ["Captain mode is off. Remove the title Captain?",
                  "Remove the cockpit greeting too, so Hariku greets you as usual?"], offers
assert core.personal.get_title() == "" and core.personal.get_custom_greeting()["text"] == ""
print("OK captain_off")

# --- Teardown, and nothing went wrong along the way ------------------------------------------------
em.unload_all_extensions()
for event_name, handler in main._SUBSCRIPTIONS:
    assert handler not in bus._listeners.get(event_name, []), f"{event_name} still subscribed"
assert not core.personal.is_placeholder_registered("airportweather")
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
# aviationweather.gov only ever gets airport codes, or a box around the place.
for url in stub_requests:
    parts = urllib.parse.urlsplit(url)
    assert parts.netloc == "aviationweather.gov", url
    keys = set(urllib.parse.parse_qs(parts.query))
    assert keys in ({"ids", "format"}, {"bbox", "format"}), url
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
