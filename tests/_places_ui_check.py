# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Open Preferences with real wxPython, go to the Places page (core 2.8) and use
it the way a screen-reader user does: add a place through the real Add Place
dialog with an address search (Nominatim, stubbed), add one from pasted
coordinates and one from a city search and a Google Maps short link (both
stubbed), check the dialog's spoken validation, rename a place, make another
one the main place, arrow through the list checking focus stays put, use
Enter and Delete on the list, remove a place, press Apply, and check what was
saved and announced.

Nothing leaves the machine: core.place_search's fetch and the short-link
request are replaced, and any real request fails and is remembered. Speech is
captured through on_before_speak. Run by tests/test_places_ui.py in a separate
process, because conftest.py mocks wx inside the pytest process. The caller
points APPDATA at a temporary folder so the user's real settings are never
touched. Prints one "OK" line per stage.
"""
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
    print("TIMEOUT: the places check hung", flush=True)
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
    WATCHED = ("core.places", "core.place_search", "core.core_panels", "core.events",
               "core.preferences", "ui.preferences_dialog")

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
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)
changes = []
bus.subscribe("on_places_changed", lambda *args, **kwargs: changes.append(args))

# The scratchpad folder matches the Extensions page's default, so Apply
# doesn't ask to restart.
core.api.save_data("Core", {"onboarding_completed": True, "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad")})


def _unexpected_prompt(*args, **kwargs):
    problems.append(f"unexpected Yes/No prompt: {args}")
    return False


core.api.prompt_yes_no = _unexpected_prompt

# --- Stubbed services: Nominatim, Open-Meteo's city search, the short link -------------
import core.place_search

ADDRESSES = [
    {"lat": "1.1301", "lon": "104.0529",
     "display_name": "Jalan Raja Ali Haji, Sungai Jodoh, Batam, Kepulauan Riau, Indonesia",
     "address": {"road": "Jalan Raja Ali Haji", "suburb": "Sungai Jodoh", "city": "Batam",
                 "state": "Kepulauan Riau", "country": "Indonesia"}},
    {"lat": "1.0452", "lon": "103.9713",
     "display_name": "Jalan Raja Ali Haji, Tanjung Uncang, Batam, Kepulauan Riau, Indonesia",
     "address": {"road": "Jalan Raja Ali Haji", "city": "Batam", "state": "Kepulauan Riau",
                 "country": "Indonesia"}},
]
CITIES = {"results": [
    {"name": "Makassar", "admin1": "South Sulawesi", "country": "Indonesia",
     "latitude": -5.1477, "longitude": 119.4327, "timezone": "Asia/Makassar"}]}
PIN_URL = ("https://www.google.com/maps/place/Mama/@-5.13,119.42,17z/data=!4m6!3m5!1s0x0:0x0"
           "!8m2!3d-5.135!4d119.423")
stub_requests = []
nominatim_agents = []
short_link_fetches = []


def _fake_fetch_json(url, timeout=None, user_agent=None):
    stub_requests.append(url)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    if url.startswith(core.place_search.NOMINATIM_URL + "?"):
        nominatim_agents.append(user_agent)
        return ADDRESSES if query["q"] == ["Jalan Raja Ali Haji"] else []
    if url.startswith(core.place_search.GEOCODING_URL + "?"):
        return CITIES if query["name"] == ["Makassar"] else {}
    raise AssertionError(f"unexpected URL {url}")


def _fake_open_without_redirects(url, timeout):
    short_link_fetches.append(url)
    return 302, PIN_URL


core.place_search.fetch_json = _fake_fetch_json
core.place_search._open_without_redirects = _fake_open_without_redirects

from ui.main_window import MainWindow
frame = MainWindow(None, title="places check")
print("OK main_window")

import core.core_panels
import core.places
import core.places_ui as places_ui
core.core_panels.register()
_ = core.i18n.get_translator("core")


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


def fire(ctrl, event_type, index=None):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    if index is not None:
        evt.SetInt(index)
    ctrl.GetEventHandler().ProcessEvent(evt)
    wx.Yield()


def focus_on(ctrl):
    ctrl.SetFocus()
    pump(lambda: wx.Window.FindFocus() is ctrl, timeout=1.0)
    return wx.Window.FindFocus() is ctrl


def browse(ctrl, event_type):
    """Select every item and fire its selection event, as arrow keys do. Focus
    must stay on the control. Returns whether focus could be observed here."""
    observable = focus_on(ctrl)
    assert ctrl.GetCount() > 0, "nothing to browse"
    for i in range(ctrl.GetCount()):
        ctrl.SetSelection(i)
        fire(ctrl, event_type, i)
        if observable:
            assert wx.Window.FindFocus() is ctrl, f"focus left {ctrl.GetName()} at item {i}"
    return observable


def browse_list(lst):
    """Select every row of a report list, as arrow keys do; focus must stay."""
    observable = focus_on(lst)
    state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    for i in range(lst.GetItemCount()):
        lst.SetItemState(i, state, state)
        wx.Yield()
        if observable:
            assert wx.Window.FindFocus() is lst, f"focus left the list at row {i}"
    return observable


def said(text):
    return text in spoken


def rows(panel):
    lst = panel.list_places
    return [(lst.GetItemText(i, 0), lst.GetItemText(i, 1)) for i in range(lst.GetItemCount())]


def select_row(panel, index):
    state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    panel.list_places.SetItemState(index, state, state)
    wx.Yield()
    assert panel.selected_index() == index, panel.selected_index()


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


NEEDS_LABEL = (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl, wx.ListBox)


def plain(text):
    return " ".join(text.replace("&&", "\0").replace("&", "").replace("\0", "&")
                    .strip().rstrip(":").split())


def check_labels(window):
    """Every input control comes right after the label that names it (screen
    readers take a control's name from the static text created just before it)."""
    children = [c for c in window.GetChildren() if not isinstance(c, wx.TopLevelWindow)]
    for index, ctrl in enumerate(children):
        if isinstance(ctrl, NEEDS_LABEL):
            before = children[index - 1] if index else None
            assert isinstance(before, wx.StaticText), (
                f"{type(ctrl).__name__} {ctrl.GetName()!r} comes after "
                f"{type(before).__name__}, not a label")
            assert plain(before.GetLabel()) == plain(ctrl.GetName()), (
                f"{ctrl.GetName()!r} comes after the label {before.GetLabel()!r}")


def driven(steps):
    """A stand-in for the page's _ask: the real Add/Edit Place dialog, shown
    (not modal), driven by steps(dialog), then OK. Returns the place, or None
    when steps() returns False (Cancel)."""
    def ask(title, place=None, taken=()):
        dlg = places_ui.PlaceDialog(panel, title, place, taken)
        dlg.Show()
        wx.Yield()
        try:
            return dlg.result if steps(dlg) else None
        finally:
            dlg.Destroy()
            wx.Yield()
    return ask


from ui.preferences_dialog import PreferencesDialog

# --- The page: after Profile, empty at first --------------------------------------------
prefs = PreferencesDialog(frame, select_tab="Places")
prefs.Show()
wx.Yield()
pages = [prefs.treebook.GetPageText(i) for i in range(prefs.treebook.GetPageCount())]
assert pages[pages.index("Profile") + 1] == "Places", pages
assert pages[prefs.treebook.GetSelection()] == "Places", pages
panel = places_ui._panel_instance
assert panel is not None and panel.IsShown(), "the Places page was not created"
check_labels(panel)
assert panel.list_places.GetName() == "Your places", panel.list_places.GetName()
assert panel.txt_main.GetName() == "Main place", panel.txt_main.GetName()
assert rows(panel) == [] and panel.txt_main.GetValue() == _("places_main_none")
labels = [w.GetLabel() for w in panel.GetChildren() if isinstance(w, wx.StaticText)]
assert any("rounded to about 1 kilometre" in label for label in labels), labels
assert [panel.list_places.GetColumn(i).GetText() for i in range(2)] == ["Name", "Where"]
print("OK places_page")

# --- Add "Rumah" with an address search --------------------------------------------------
dialog_focus = {"checked": True}


def add_home(dlg):
    assert dlg.GetTitle() == _("places_dlg_add_title"), dlg.GetTitle()
    assert dlg.GetEscapeId() == wx.ID_CANCEL and dlg.GetDefaultItem().GetId() == wx.ID_OK
    check_labels(dlg)
    assert dlg.txt_name.GetName() == "Name (for example Home, Office or Mum's house)"
    assert dlg.txt_address.GetName() == "Find an address (press Enter to search)"
    assert dlg.list_addresses.GetName() == "Addresses found"
    assert dlg.txt_city.GetName() == "Find a city (press Enter to search)"
    assert dlg.list_cities.GetName() == "Cities found"
    assert dlg.txt_coords.GetName() == "Paste coordinates or a map link (press Enter to use)"
    assert dlg.txt_point.GetName() == "Chosen point"
    assert dlg.txt_point.GetValue() == _("places_point_none")
    name_focus = wx.Window.FindFocus() is dlg.txt_name

    # OK without a name, then without a point: shown, spoken, focus on the field to fix.
    assert not dlg.accept()
    assert dlg.lbl_error.GetLabel() == _("places_err_name_empty"), dlg.lbl_error.GetLabel()
    assert pump(lambda: said(_("places_err_name_empty")), timeout=2), spoken
    if name_focus:
        assert wx.Window.FindFocus() is dlg.txt_name, "focus did not go to the name"
    dlg.txt_name.SetValue("Rumah")
    assert not dlg.accept()
    assert dlg.lbl_error.GetLabel() == _("places_err_no_point"), dlg.lbl_error.GetLabel()
    assert pump(lambda: said(_("places_err_no_point")), timeout=2), spoken

    # The address: too short; typing alone never searches; Enter does.
    dlg.txt_address.SetValue("Jl")
    fire(dlg.txt_address, wx.EVT_TEXT_ENTER)
    assert spoken[-1] == _("places_address_too_short", count=3), spoken[-1]
    dlg.txt_address.SetValue("Jalan  Raja Ali Haji")
    wx.Yield()
    assert nominatim_agents == [], "typing alone must not search"
    address_focus = focus_on(dlg.txt_address)
    fire(dlg.txt_address, wx.EVT_TEXT_ENTER)
    assert said(_("places_address_searching", query="Jalan Raja Ali Haji")), spoken
    assert pump(lambda: dlg.list_addresses.GetCount() == 2), "address results never arrived"
    assert dlg.lbl_addresses.GetLabel() == _("places_lbl_addresses_count", count=2)
    if address_focus:
        assert wx.Window.FindFocus() is dlg.list_addresses, "focus did not move to the results"
    # Arrowing through the results: focus stays, the chosen point follows.
    checked = browse(dlg.list_addresses, wx.EVT_LISTBOX)
    assert dlg.txt_point.GetValue() == ("Jalan Raja Ali Haji, Tanjung Uncang, Batam, Kepulauan "
                                        "Riau, Indonesia (1.0452, 103.9713)"), dlg.txt_point.GetValue()
    dlg.list_addresses.SetSelection(0)
    fire(dlg.list_addresses, wx.EVT_LISTBOX, 0)
    assert dlg.txt_point.GetValue() == ("Jalan Raja Ali Haji, Sungai Jodoh, Batam, Kepulauan "
                                        "Riau, Indonesia (1.1301, 104.0529)"), dlg.txt_point.GetValue()

    # Nothing found is said clearly; the point chosen before stays.
    dlg.txt_address.SetValue("Jalan Tidak Ada")
    fire(dlg.btn_address, wx.EVT_BUTTON)
    assert pump(lambda: said(_("places_address_none", query="Jalan Tidak Ada")), timeout=6), spoken
    assert dlg.list_addresses.GetCount() == 0
    assert dlg.lbl_addresses.GetLabel() == _("places_lbl_addresses_none")
    assert dlg.txt_point.GetValue().startswith("Jalan Raja Ali Haji, Sungai Jodoh")
    dialog_focus["checked"] = checked and address_focus and dialog_focus["checked"]
    assert dlg.accept(), dlg.lbl_error.GetLabel()
    return True


panel._ask = driven(add_home)
fire(panel.btn_add, wx.EVT_BUTTON)
assert pump(lambda: said("Added Rumah. It is your main place.")), spoken
assert rows(panel) == [("Rumah (main)", "Jalan Raja Ali Haji, Sungai Jodoh, Batam, Kepulauan "
                        "Riau, Indonesia (1.1301, 104.0529)")], rows(panel)
assert panel.txt_main.GetValue().startswith("Rumah: Jalan Raja Ali Haji"), panel.txt_main.GetValue()
assert prefs.is_dirty, "Preferences doesn't know there is something to save"
assert nominatim_agents == [core.place_search.NOMINATIM_USER_AGENT] * 2, nominatim_agents
assert "github.com/InfiArtt/hariku-core" in nominatim_agents[0]
assert all("addressdetails=1" in u for u in stub_requests if "nominatim" in u), stub_requests
assert core.places.get_places() == [], "nothing is saved before OK or Apply"
print(f"OK add_by_address ({focus_note(dialog_focus['checked'])})")

# --- Add "Kantor" from pasted coordinates (a taken name is refused) -----------------------


def add_office(dlg):
    check_labels(dlg)
    dlg.txt_name.SetValue("rumah")
    dlg.txt_coords.SetValue("Monas")
    fire(dlg.btn_use, wx.EVT_BUTTON)
    assert spoken[-1] == places_ui.error_text("not_found"), spoken[-1]
    dlg.txt_coords.SetValue("1.1452, 104.0132")
    coords_focus = focus_on(dlg.txt_coords)
    fire(dlg.txt_coords, wx.EVT_TEXT_ENTER)
    assert spoken[-1] == _("places_point_found", point="1.1452, 104.0132"), spoken[-1]
    assert dlg.txt_point.GetValue() == "1.1452, 104.0132"
    if coords_focus:
        assert wx.Window.FindFocus() is dlg.txt_coords, "focus moved after Use"
    assert not dlg.accept()
    assert dlg.lbl_error.GetLabel() == _("places_err_name_duplicate", name="rumah")
    dlg.txt_name.SetValue("Kantor")
    assert dlg.accept(), dlg.lbl_error.GetLabel()
    return True


panel._ask = driven(add_office)
fire(panel.btn_add, wx.EVT_BUTTON)
assert pump(lambda: said("Added Kantor.")), spoken
assert rows(panel)[1] == ("Kantor", "1.1452, 104.0132"), rows(panel)
print("OK add_by_coordinates")

# --- Add "Rumah Mama": a city search, then a short link, then the city again -------------


def add_mum(dlg):
    dlg.txt_name.SetValue("Rumah Mama")
    dlg.txt_city.SetValue("M")
    fire(dlg.txt_city, wx.EVT_TEXT_ENTER)
    assert spoken[-1] == _("places_city_too_short", count=2), spoken[-1]
    dlg.txt_city.SetValue("Nowhere")
    fire(dlg.btn_city, wx.EVT_BUTTON)
    assert pump(lambda: said(_("places_city_none", query="Nowhere"))), spoken
    assert dlg.lbl_cities.GetLabel() == _("places_lbl_cities_none")
    dlg.txt_city.SetValue("Makassar")
    fire(dlg.btn_city, wx.EVT_BUTTON)
    assert pump(lambda: dlg.list_cities.GetCount() == 1), "city results never arrived"
    assert dlg.list_cities.GetString(0) == "Makassar, South Sulawesi, Indonesia"
    assert dlg.txt_point.GetValue() == "Makassar, South Sulawesi, Indonesia (-5.1477, 119.4327)"
    # A short link is only opened when Use is pressed.
    dlg.txt_coords.SetValue("https://maps.app.goo.gl/HarikuMama")
    wx.Yield()
    assert short_link_fetches == []
    fire(dlg.btn_use, wx.EVT_BUTTON)
    assert said(_("places_link_expanding")), spoken
    assert pump(lambda: said(_("places_point_found", point="-5.1350, 119.4230"))), spoken
    assert short_link_fetches == ["https://maps.app.goo.gl/HarikuMama"], short_link_fetches
    assert dlg.txt_point.GetValue() == "-5.1350, 119.4230"
    # The last choice wins: the city again.
    dlg.list_cities.SetSelection(0)
    fire(dlg.list_cities, wx.EVT_LISTBOX, 0)
    assert dlg.accept(), dlg.lbl_error.GetLabel()
    assert dlg.result["timezone"] == "Asia/Makassar" and dlg.result["source"] == "city"
    return True


panel._ask = driven(add_mum)
fire(panel.btn_add, wx.EVT_BUTTON)
assert pump(lambda: said("Added Rumah Mama.")), spoken
assert [name for name, _where in rows(panel)] == ["Rumah (main)", "Kantor", "Rumah Mama"]
print("OK add_by_city_and_link")

# --- Rename, make main, arrow through, Enter and Delete, remove ---------------------------


def rename_office(dlg):
    assert dlg.GetTitle() == _("places_dlg_edit_title")
    assert dlg.txt_name.GetValue() == "Kantor"
    assert dlg.txt_point.GetValue() == "1.1452, 104.0132"     # where it is, kept
    dlg.txt_name.SetValue("Kantor Pusat")
    assert dlg.accept(), dlg.lbl_error.GetLabel()
    return True


office_id = panel.places()[1]["id"]
select_row(panel, 1)
panel._ask = driven(rename_office)
fire(panel.btn_edit, wx.EVT_BUTTON)
assert pump(lambda: said("Changed Kantor Pusat.")), spoken
assert panel.places()[1]["id"] == office_id and rows(panel)[1][0] == "Kantor Pusat"

select_row(panel, 1)
main_focus = focus_on(panel.btn_main)
fire(panel.btn_main, wx.EVT_BUTTON)
assert pump(lambda: said("Kantor Pusat is now the main place.")), spoken
assert [name for name, _where in rows(panel)] == ["Rumah", "Kantor Pusat (main)", "Rumah Mama"]
assert panel.txt_main.GetValue() == "Kantor Pusat: 1.1452, 104.0132", panel.txt_main.GetValue()
if main_focus:
    assert wx.Window.FindFocus() is panel.btn_main, "focus moved after Make main"

list_focus = browse_list(panel.list_places)
if list_focus:
    # Enter edits the selected place (cancelled here); Delete asks before removing.
    asked = []
    panel._ask = lambda title, place=None, taken=(): asked.append((title, place["name"])) and None
    select_row(panel, 0)
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_RETURN)
    panel.GetEventHandler().ProcessEvent(key)
    assert asked == [(_("places_dlg_edit_title"), "Rumah")], asked
    confirms = []
    panel._confirm = lambda message: confirms.append(message) and False
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_DELETE)
    panel.GetEventHandler().ProcessEvent(key)
    assert confirms == [_("places_remove_confirm", name="Rumah")], confirms
    assert len(rows(panel)) == 3, "removed without the user's yes"

confirms = []
panel._confirm = lambda message: confirms.append(message) or True
select_row(panel, 2)
fire(panel.btn_remove, wx.EVT_BUTTON)
assert confirms == [_("places_remove_confirm", name="Rumah Mama")], confirms
assert pump(lambda: said("Removed Rumah Mama.")), spoken
assert [name for name, _where in rows(panel)] == ["Rumah", "Kantor Pusat (main)"]
if list_focus:
    assert wx.Window.FindFocus() is panel.list_places, "focus did not return to the list"
assert core.places.get_places() == [] and changes == [], "saved before OK or Apply"
print(f"OK edit_main_remove ({focus_note(list_focus and main_focus)})")

# --- Apply: saved and announced once ---------------------------------------------------------
prefs.OnApply(None)
saved = core.places.get_places()
assert [p["name"] for p in saved] == ["Rumah", "Kantor Pusat"], saved
assert core.places.get_main()["id"] == office_id
home = saved[0]
assert (home["lat"], home["lon"], home["source"], home["city"]) == (1.1301, 104.0529,
                                                                    "address", "Batam"), home
assert home["timezone"] is None and saved[1]["source"] == "coordinates"
assert len(changes) == 1, changes
prefs.OnApply(None)                                   # nothing changed: nothing announced
assert len(changes) == 1, changes
stored = core.api.load_data("Places")
assert stored["main"] == office_id and stored["migrated"] is True, stored
prefs.Destroy()
wx.Yield()
print("OK saved")

# --- Opening Preferences again shows them ----------------------------------------------------
prefs = PreferencesDialog(frame, select_tab="Places")
prefs.Show()
wx.Yield()
panel = places_ui._panel_instance
assert [name for name, _where in rows(panel)] == ["Rumah", "Kantor Pusat (main)"], rows(panel)
assert panel.txt_main.GetValue() == "Kantor Pusat: 1.1452, 104.0132"
assert not panel.is_changed()
prefs.Destroy()
wx.Yield()
print("OK reopen")

assert not network_attempts, f"real network access attempted: {network_attempts}"
assert all(u.startswith((core.place_search.NOMINATIM_URL + "?",
                         core.place_search.GEOCODING_URL + "?")) for u in stub_requests), \
    stub_requests
assert len([u for u in stub_requests if "nominatim" in u]) == 2, stub_requests
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.RemoveIcon()
frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
