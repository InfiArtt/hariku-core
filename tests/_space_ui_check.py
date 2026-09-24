# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Space extension through the real loader with real wxPython, open its
settings page inside the real Preferences dialog and its launches list, run
every hotkey action, and browse every list and choice the way arrow keys do,
checking focus stays put.

wheretheiss.at, Launch Library and Open-Meteo are stubbed (nothing leaves the
machine), speech is captured through on_before_speak and sounds are recorded
instead of played.

Run by tests/test_space_ui.py in a separate process, because conftest.py
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
    print("TIMEOUT: the space check hung", flush=True)
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
    WATCHED = ("hariku_ext.space", "space_", "core.events", "core.hotkeys",
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
frame = MainWindow(None, title="space check")
print("OK main_window")

PLAIN_A = (ord("A"), False, False, False, False)
assert PLAIN_A not in core.hotkeys.keybindings, "A is already bound by the core"

# Replace the network helper before the extension imports its modules.
SPACE_DIR = os.path.join(ROOT, "extensions", "space")
sys.path.insert(0, SPACE_DIR)
import space_api

UTC = datetime.timezone.utc
NOW = datetime.datetime.now(UTC).replace(second=0, microsecond=0)


def _iso(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


SOON = NOW + datetime.timedelta(hours=3)
LATER = NOW + datetime.timedelta(days=1, hours=2)
VAGUE = NOW + datetime.timedelta(days=40)
LAUNCHES = {"count": 3, "next": None, "previous": None, "results": [
    {"id": "launch-1", "name": "Falcon 9 Block 5 | Starlink Group 10-1",
     "status": {"id": 1, "name": "Go for Launch", "abbrev": "Go"},
     "net": _iso(SOON), "net_precision": {"id": 1, "name": "Minute", "abbrev": "MIN"},
     "window_start": _iso(SOON), "window_end": _iso(SOON + datetime.timedelta(hours=4)),
     "lsp_name": "SpaceX", "mission_type": "Communications", "pad": "Space Launch Complex 40",
     "location": "Cape Canaveral SFS, FL, USA", "orbit": "Low Earth Orbit", "type": "list"},
    {"id": "launch-2", "name": "Long March 8A | Unknown Payload",
     "status": {"id": 1, "name": "Go for Launch", "abbrev": "Go"},
     "net": _iso(LATER), "net_precision": {"id": 2, "name": "Hour", "abbrev": "HR"},
     "window_start": _iso(LATER), "window_end": _iso(LATER + datetime.timedelta(minutes=19)),
     "lsp_name": "China Aerospace Science and Technology Corporation",
     "mission_type": "Unknown", "pad": "Commercial LC-1",
     "location": "Wenchang Space Launch Site, People's Republic of China", "orbit": None,
     "type": "list"},
    {"id": "launch-3", "name": "Vulcan VC4S | USSF-57",
     "status": {"id": 2, "name": "To Be Determined", "abbrev": "TBD"},
     "net": _iso(VAGUE), "net_precision": {"id": 7, "name": "Month", "abbrev": "M"},
     "window_start": _iso(VAGUE), "window_end": _iso(VAGUE),
     "lsp_name": "United Launch Alliance", "mission_type": "Government/Top Secret",
     "pad": "Space Launch Complex 41", "location": "Cape Canaveral SFS, FL, USA",
     "orbit": "Geostationary Orbit", "type": "list"},
]}
ISS = {"name": "iss", "id": 25544, "latitude": -20.5, "longitude": 118.3, "altitude": 434.28,
       "velocity": 27539.4, "visibility": "daylight", "units": "kilometers"}
LAND = {"latitude": "-20.50", "longitude": "118.30", "timezone_id": "Australia/Perth",
        "offset": 8, "country_code": "AU"}
PLACES = {"results": [
    {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
     "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"},
    {"name": "Jakarta", "admin1": "West Virginia", "country": "United States",
     "latitude": 38.1, "longitude": -80.2, "timezone": "America/New_York"},
]}
stub_requests = []


def _fake_fetch_json(url):
    stub_requests.append(url)
    if url == space_api.ISS_URL:
        return dict(ISS)
    if url.startswith("https://api.wheretheiss.at/v1/coordinates/"):
        return dict(LAND)
    if url.startswith(space_api.LAUNCHES_URL):
        return {"results": [dict(item) for item in LAUNCHES["results"]]}
    if url.startswith(space_api.GEOCODING_URL):
        return PLACES
    raise AssertionError(f"unexpected URL {url}")


space_api.fetch_json = _fake_fetch_json

import core.extension_manager as em
em.load_unpacked_extension(SPACE_DIR)
assert "space" in em.LOADED_EXTENSIONS, "Space extension did not load"
main = em.LOADED_EXTENSIONS["space"]["module"]
space_ui = sys.modules["space_ui"]
space_text = sys.modules["space_text"]
assert sys.modules["space_api"] is space_api
assert core.hotkeys.keybindings[PLAIN_A][0] == "Space.where_is_iss"
for action_id in ("Space.show_launches", "Space.sun_and_moon"):
    assert action_id in core.hotkeys.actions
    assert not core.hotkeys.get_current_bindings(action_id), f"{action_id} has a default key"
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


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


def said(prefix):
    return any(s.startswith(prefix) for s in spoken)


_ = space_text._

# --- Without a city: the ISS and the Moon still answer, with a hint -------------
spoken.clear()
assert run_and_close("Space.where_is_iss") == []
assert spoken[0] == _("iss_checking"), spoken
assert pump(lambda: said("The ISS is ")), spoken
assert spoken[-1].startswith("The ISS is over Australia. It is 434 kilometres up"), spoken[-1]
assert spoken[-1].endswith(_("iss_set_location")), spoken[-1]
assert run_and_close("Space.sun_and_moon") == []
assert spoken[-1].startswith("Moon phase: ") and spoken[-1].endswith(_("sun_no_location")), \
    spoken[-1]
print("OK no_location")

# --- The main place (Preferences, Places) is the default -------------------------
import core.places
core.api.save_data("Weather", {"location": {"name": "Bandung", "admin1": "West Java",
                                            "country": "Indonesia", "latitude": -6.9175,
                                            "longitude": 107.6191,
                                            "timezone": "Asia/Jakarta"}, "units": "metric"})
assert main.get_location() is None, "the Weather city is no longer used by itself"
bandung_place, = core.places.set_places([{
    "name": "Bandung", "lat": -6.9175, "lon": 107.6191,
    "label": "Bandung, West Java, Indonesia", "timezone": "Asia/Jakarta", "source": "city",
    "city": "Bandung", "region": "West Java", "country": "Indonesia"}])
assert main.get_location()["name"] == "Bandung"
spoken.clear()
assert run_and_close("Space.sun_and_moon") == []
assert spoken and spoken[-1].startswith("Bandung, ") and "Sunrise at " in spoken[-1], spoken
print("OK main_place_default")

# --- Preferences page: the place choice, search, browse, save ---------------------
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Space")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "Space settings page was not created"
choice = panel.place_choice.ctrl
assert choice.GetName() == "Place", choice.GetName()
assert choice.GetStrings() == ["The main place (Bandung)", "Bandung", "Its own place…"], \
    choice.GetStrings()
assert panel.place_choice.key() == "main" and choice.GetSelection() == 0
assert panel.txt_location.GetValue() == _("location_not_set"), panel.txt_location.GetValue()
# The city search is for its own place only: skipped while another place is chosen.
assert not panel.txt_search.IsEnabled() and not panel.list_results.IsEnabled()
assert panel.choice_lead.GetString(panel.choice_lead.GetSelection()) == "30 minutes"
labels = [w.GetLabel() for w in panel.GetChildren() if isinstance(w, wx.StaticText)]
for credit in ("ISS position: wheretheiss.at", "Launch data: The Space Devs Launch Library 2",
               "City search: Open-Meteo.com"):
    assert credit in labels, labels
assert any("stays on this computer" in label for label in labels), labels
# Arrowing through the places: focus stays; the last one, "Its own place", opens the search.
checked = browse(choice, wx.EVT_CHOICE)
assert panel.place_choice.key() == "own", panel.place_choice.key()
assert panel.txt_search.IsEnabled() and panel.btn_search.IsEnabled()
assert panel.list_results.IsEnabled() and panel.txt_location.IsEnabled()

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
checked = browse(panel.choice_lead, wx.EVT_CHOICE) and checked
# Back to the main place and to its own place again: the search follows.
choice.SetSelection(0)
fire(choice, wx.EVT_CHOICE, 0)
assert panel.place_choice.key() == "main" and not panel.txt_search.IsEnabled()
choice.SetSelection(2)
fire(choice, wx.EVT_CHOICE, 2)
assert panel.place_choice.key() == "own" and panel.txt_search.IsEnabled()
print(f"OK panel_browse ({focus_note(checked)})")

panel.list_results.SetSelection(0)
fire(panel.list_results, wx.EVT_LISTBOX, 0)
panel.choice_lead.SetSelection(0)
prefs.OnApply(None)
saved = core.api.load_data("Space")
assert saved["place"] == "own", saved
assert saved["location"]["name"] == "Jakarta" and saved["location"]["country"] == "Indonesia", saved
assert saved["location"]["timezone"] == "Asia/Jakarta" and saved["lead_minutes"] == 10, saved
assert panel.txt_location.GetValue() == "Jakarta, Indonesia"
prefs.Destroy()
wx.Yield()
print("OK panel_apply")

# --- Hotkey actions with a city ----------------------------------------------------
spoken.clear()
assert run_and_close("Space.where_is_iss") == []
assert pump(lambda: said("The ISS is 2,000 kilometres southeast of you, over Australia.")), spoken
assert run_and_close("Space.sun_and_moon") == []
assert spoken[-1].startswith("Jakarta, ") and "Moon phase: " in spoken[-1], spoken[-1]
assert run_and_close("Space.show_launches") == ["LaunchesDialog"]
assert pump(lambda: not main._launch_loading), "the launch list never arrived"
assert len(main.launch_data()[0]) == 3
print("OK actions")

# --- The launches list: browse, details, Enter, remind, refresh --------------------
tz = space_api.zone_for(main.get_location())


def open_launches(refresh_now=False):
    dlg = space_ui.LaunchesDialog(frame, _("launches_label", place="Jakarta"), main.launch_data,
                                  main.refresh_launches, main.has_reminder, main.toggle_reminder,
                                  lambda: main._settings["lead_minutes"], tz, main._utcnow,
                                  refresh_now=refresh_now)
    dlg.Show()
    wx.Yield()
    return dlg


dlg = open_launches()
rows = [dlg.list_launches.GetString(i) for i in range(dlg.list_launches.GetCount())]
assert len(rows) == 3, rows
assert rows[0].startswith("Falcon 9 Block 5, Starlink Group 10-1, ") and \
    rows[0].endswith(", from Cape Canaveral, status Go"), rows[0]
assert rows[1].startswith("Long March 8A, Unknown Payload, ") and "from Wenchang" in rows[1], rows[1]
assert "date not yet fixed" in rows[2] and rows[2].endswith("status to be determined"), rows[2]
assert dlg.lbl_status.GetLabel().startswith("Updated at "), dlg.lbl_status.GetLabel()
checked = browse(dlg.list_launches, wx.EVT_LISTBOX)
assert dlg.txt_details.GetValue().startswith("Vulcan VC4S, USSF-57. Launch time: "), \
    dlg.txt_details.GetValue()
dlg.list_launches.SetSelection(0)
fire(dlg.list_launches, wx.EVT_LISTBOX, 0)
assert "Launch provider: SpaceX." in dlg.txt_details.GetValue()

spoken.clear()
fire(dlg.btn_details, wx.EVT_BUTTON)
assert spoken and spoken[-1].startswith("Falcon 9 Block 5, Starlink Group 10-1. Launch time: "), spoken
dlg.list_launches.SetFocus()
wx.Yield()
list_focused = wx.Window.FindFocus() is dlg.list_launches
if list_focused:
    dlg.list_launches.SetSelection(1)
    fire(dlg.list_launches, wx.EVT_LISTBOX, 1)
    spoken.clear()
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_RETURN)
    dlg.GetEventHandler().ProcessEvent(key)
    assert said("Long March 8A, Unknown Payload. Launch time: "), spoken
    assert wx.Window.FindFocus() is dlg.list_launches

# Remind me: set on the first launch, refused on the vague one.
dlg.list_launches.SetSelection(0)
fire(dlg.list_launches, wx.EVT_LISTBOX, 0)
spoken.clear()
fire(dlg.btn_remind, wx.EVT_BUTTON)
assert spoken[-1] == ("You'll be reminded 10 minutes before "
                      "Falcon 9 Block 5, Starlink Group 10-1."), spoken
assert dlg.list_launches.GetString(0).endswith(", reminder set"), dlg.list_launches.GetString(0)
assert dlg.list_launches.GetSelection() == 0, "the selection moved"
assert dlg.btn_remind.GetLabel().replace("&", "") == "Cancel reminder"
assert main.has_reminder("launch-1")
if list_focused:
    dlg.list_launches.SetFocus()
    wx.Yield()
    fire(dlg.btn_remind, wx.EVT_BUTTON)      # cancel, then set again
    fire(dlg.btn_remind, wx.EVT_BUTTON)
    assert wx.Window.FindFocus() is dlg.list_launches, "focus left the list after Remind me"
assert main.has_reminder("launch-1")
dlg.list_launches.SetSelection(2)
fire(dlg.list_launches, wx.EVT_LISTBOX, 2)
fire(dlg.btn_remind, wx.EVT_BUTTON)
assert spoken[-1] == ("Vulcan VC4S, USSF-57 has no exact launch time yet, "
                      "so a reminder can't be set."), spoken[-1]
assert not main.has_reminder("launch-3")

# Refresh right after a fetch: the list is up to date, nothing is requested.
requests_before = len(stub_requests)
spoken.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert spoken[-1].startswith("The launch list is up to date;"), spoken
assert len(stub_requests) == requests_before
dlg.Destroy()
wx.Yield()

# An older list is refreshed by the button; then a window closed mid-refresh.
main._launch_state["fetched_at"] -= 20 * 60
dlg = open_launches()
spoken.clear()
fire(dlg.btn_refresh, wx.EVT_BUTTON)
assert spoken[0] == _("status_refreshing"), spoken
assert pump(lambda: _("launches_updated") in spoken), spoken
assert dlg.list_launches.GetString(0).endswith(", reminder set")
dlg.Destroy()
wx.Yield()
main._launch_state["fetched_at"] -= 2 * 3600
dlg = open_launches(refresh_now=True)
dlg.Destroy()
assert pump(lambda: not main._launch_loading), "fetch never finished"
print(f"OK launches_dialog ({focus_note(checked)})")

# --- Escape closes the list ----------------------------------------------------------
state = {}


def press_escape():
    for w in wx.GetTopLevelWindows():
        if isinstance(w, space_ui.LaunchesDialog) and w.IsModal():
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
core.hotkeys.actions["Space.show_launches"].callback()
guard.Stop()
escape.Stop()
assert state.get("found") and not state.get("forced"), f"Escape did not close the list: {state}"
print("OK escape")

# --- The reminder is spoken once on the minute tick ------------------------------------
real_utcnow = main._utcnow
main._utcnow = lambda: SOON - datetime.timedelta(minutes=9, seconds=30)
spoken.clear()
sounds.clear()
bus.emit("on_minute_tick", datetime.datetime.now())
assert spoken == ["Rocket launch in 10 minutes: Falcon 9 Block 5, Starlink Group 10-1, at "
                  f"{space_text.clock(SOON, tz)}, from Cape Canaveral."], spoken
assert sounds == ["info.wav"], sounds
bus.emit("on_minute_tick", datetime.datetime.now())
assert len(spoken) == 1 and len(sounds) == 1, (spoken, sounds)
main._utcnow = real_utcnow
print("OK reminder")

# --- The Morning Briefing sentence -------------------------------------------------------
lines = []
bus.emit("on_briefing_collect", lines)
assert len(lines) == 1 and lines[0].startswith("Sunset at "), lines
today = space_text.local(main._utcnow(), tz).date()
if space_text.local(SOON, tz).date() == today:
    assert "Rocket launch today at " in lines[0], lines
print("OK briefing")

# --- The places change while the page is open; a saved place is chosen ------------------
prefs = PreferencesDialog(frame, select_tab="Space")
prefs.Show()
wx.Yield()
panel = main._panel
choice = panel.place_choice.ctrl
assert panel.place_choice.key() == "own" and choice.GetSelection() == 2, choice.GetSelection()
assert panel.txt_location.GetValue() == "Jakarta, Indonesia", panel.txt_location.GetValue()
assert panel.txt_search.IsEnabled()
choice.SetFocus()
wx.Yield()
choice_focused = wx.Window.FindFocus() is choice
makassar = {"name": "Makassar", "lat": -5.1477, "lon": 119.4327,
            "label": "Makassar, South Sulawesi, Indonesia", "timezone": "Asia/Makassar",
            "source": "city", "city": "Makassar", "region": "South Sulawesi",
            "country": "Indonesia"}
core.places.set_places([bandung_place, makassar])     # what the Places page does on OK
assert choice.GetStrings() == ["The main place (Bandung)", "Bandung", "Makassar",
                               "Its own place…"], choice.GetStrings()
assert panel.place_choice.key() == "own" and choice.GetSelection() == 3
assert panel.txt_search.IsEnabled()
if choice_focused:
    assert wx.Window.FindFocus() is choice, "focus moved when the places changed"
browse(choice, wx.EVT_CHOICE)
# Choosing a saved place skips the city search, and is what OK saves.
makassar_id = core.places.get_places()[1]["id"]
choice.SetSelection(2)
fire(choice, wx.EVT_CHOICE, 2)
assert panel.place_choice.key() == makassar_id, panel.place_choice.key()
assert not panel.txt_search.IsEnabled() and not panel.list_results.IsEnabled()
if choice_focused:
    assert wx.Window.FindFocus() is choice, "focus left the Place list"
prefs.OnApply(None)
saved = core.api.load_data("Space")
assert saved["place"] == makassar_id, saved
assert saved["location"]["name"] == "Jakarta", "its own city is kept for later"
assert panel.txt_location.GetValue() == "Jakarta, Indonesia"
assert main.get_location()["name"] == "Makassar"
# The place's own time zone is used for its times.
assert str(space_api.zone_for(main.get_location())) == "Asia/Makassar"
prefs.Destroy()
wx.Yield()
spoken.clear()
assert run_and_close("Space.sun_and_moon") == []
assert spoken and spoken[-1].startswith("Makassar, ") and "Sunrise at " in spoken[-1], spoken
print(f"OK place_choice ({focus_note(choice_focused)})")

# --- Teardown, and nothing went wrong along the way -----------------------------------
em.unload_all_extensions()
for event_name, handler in main._SUBSCRIPTIONS:
    assert handler not in bus._listeners.get(event_name, []), f"{event_name} still subscribed"
print("OK teardown")

assert not network_attempts, f"real network access attempted: {network_attempts}"
allowed = ("https://api.wheretheiss.at/", "https://ll.thespacedevs.com/",
           "https://geocoding-api.open-meteo.com/")
assert all(u.startswith(allowed) for u in stub_requests), stub_requests
# The user's location (its own city or a saved place) never reaches any service.
for url in stub_requests:
    for fragment in ("-6.2", "106.8", "-6.9", "107.6", "-5.1", "119.4"):
        assert fragment not in url, f"location in {url}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
