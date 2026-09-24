# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for the Flight Radar extension:
  * FlightRadarPanel - the Preferences page: the place (one from Preferences,
                       Places, or its own: city search, street-address search,
                       or pasted coordinates / map link, with a name), radius,
                       units, ground traffic, overhead alerts, the emergency
                       watch, notes, credits.
  * RadarListDialog  - every aircraft in range, one sentence per row, nearest
                       first, with Details (Enter), Refresh, Listen to ATC
                       and Track.
  * TrackFlightDialog - type a flight number to find and track it; the
                       tracked flights, with Stop tracking and Check now.
Selection changes never move keyboard focus. Focus only moves after the user
asks for something (opening the dialog, pressing Search). Rows that change
after a refresh or a route lookup keep the current selection.
"""

import logging
import threading

import wx

import core.place_search as location
import core.places
import core.ui_scale
from core.i18n import apply_rtl_layout, get_current_language
from core.places_ui import PlaceChoice
from core.speech import speak

import flight_radar_api as api
import flight_radar_text as text
from flight_radar_text import _

logger = logging.getLogger(__name__)


def _search_worker(done, search_id, query, language):
    # Worker thread: network only, results go back through wx.CallAfter.
    try:
        places, error = api.search_places(query, language), None
    except api.FlightError as e:
        places, error = [], e.kind
    except Exception:
        logger.exception("[Flight Radar] City search failed")
        places, error = [], "bad_response"
    wx.CallAfter(done, search_id, query, places, error)


def address_location(found):
    """A core address search result (core.place_search) as a radar location."""
    return {"name": found["name"], "admin1": "", "country": "",
            "latitude": found["latitude"], "longitude": found["longitude"],
            "kind": "address", "detail": found["label"]}


def _address_worker(done, search_id, query, language):
    # Worker thread: Nominatim, paced and cached for all of Hariku by core.place_search.
    try:
        places = [address_location(p) for p in location.search_addresses(query, language)]
        error = None
    except location.LocationError as e:
        places, error = [], e.kind
    except Exception:
        logger.exception("[Flight Radar] Address search failed")
        places, error = [], "address_failed"
    wx.CallAfter(done, search_id, query, places, error)


def _link_worker(done, link_id, url):
    # Worker thread: expands a Google Maps short link (those hosts only).
    point, error = None, None
    try:
        point = location.resolve_short_link(url)
    except location.LocationError as e:
        error = e.kind
    except Exception:
        logger.exception("[Flight Radar] Short link failed")
        error = "link_failed"
    wx.CallAfter(done, link_id, point, error)


def _start(target, *args):
    threading.Thread(target=target, args=args, daemon=True, name="flight-radar-settings").start()


def _labelled(parent, sizer, label, make_control):
    """A StaticText created right before the control (screen readers take the
    label from the previous window), which also gets the label as its name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
    control = make_control()
    control.SetName(label.rstrip(":"))
    return control


# The page is taller than the Preferences dialog, so it scrolls (and scrolls
# the focused control into view). A plain panel where wx is not the real one.
_PageBase = wx.ScrolledWindow if isinstance(getattr(wx, "ScrolledWindow", None), type) else wx.Panel


class FlightRadarPanel(_PageBase):
    """OK saves which place to use ("Place:") and, as its own place, whatever
    the user chose last: a city or address result (the one selected in its
    list) or pasted coordinates. Those are only available while "Its own
    place" is chosen."""

    def __init__(self, parent, settings):
        super().__init__(parent)
        self._location = settings.get("location")
        self._results = []       # cities
        self._addresses = []
        self._point = None       # (latitude, longitude) from the last Use
        self._pending = None     # "city", "address" or "coordinates"
        self._search_id = self._address_id = self._link_id = 0

        vbox = wx.BoxSizer(wx.VERTICAL)

        choice = (core.places.normalize_choice(settings.get("place"))
                  or core.places.initial_choice(self._location))
        self.place_choice = PlaceChoice(self, vbox, choice, own=True,
                                        on_change=lambda key: self._update_own())

        self.txt_location = _labelled(self, vbox, _("lbl_current_location"),
                                      lambda: wx.TextCtrl(self, style=wx.TE_READONLY))
        vbox.Add(self.txt_location, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # 1. City search (Open-Meteo)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_search = _labelled(self, vbox, _("lbl_search"),
                                    lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER))
        row.Add(self.txt_search, 1, wx.RIGHT, 6)
        self.btn_search = wx.Button(self, label=_("btn_search"))
        row.Add(self.btn_search, 0)
        vbox.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.lbl_results = wx.StaticText(self, label=_("lbl_results"))
        vbox.Add(self.lbl_results, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.list_results = wx.ListBox(self, size=(-1, 70), style=wx.LB_SINGLE)
        self.list_results.SetName(_("lbl_results").rstrip(":"))
        vbox.Add(self.list_results, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # 2. Street address search (Nominatim)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_address = _labelled(self, vbox, _("lbl_address"),
                                     lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER))
        row.Add(self.txt_address, 1, wx.RIGHT, 6)
        self.btn_address = wx.Button(self, label=_("btn_address"))
        row.Add(self.btn_address, 0)
        vbox.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.lbl_addresses = wx.StaticText(self, label=_("lbl_addresses"))
        vbox.Add(self.lbl_addresses, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.list_addresses = wx.ListBox(self, size=(-1, 70), style=wx.LB_SINGLE)
        self.list_addresses.SetName(_("lbl_addresses").rstrip(":"))
        vbox.Add(self.list_addresses, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # 3. Coordinates or a map link
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_coords = _labelled(self, vbox, _("lbl_coordinates"),
                                    lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER))
        row.Add(self.txt_coords, 1, wx.RIGHT, 6)
        self.btn_use = wx.Button(self, label=_("btn_use"))
        row.Add(self.btn_use, 0)
        vbox.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.lbl_point = wx.StaticText(self, label="")
        vbox.Add(self.lbl_point, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        exact = self._location and self._location.get("kind", "city") != "city"
        self.txt_name = _labelled(self, vbox, _("lbl_place_name"), lambda: wx.TextCtrl(
            self, value=self._location["name"] if exact else _("default_place_name")))
        vbox.Add(self.txt_name, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        vbox.Add(wx.StaticText(self, label=_("privacy_note")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.choice_radius = _labelled(self, vbox, _("lbl_radius"), lambda: wx.Choice(
            self, choices=[text.distance_choice(km) for km in api.RADIUS_CHOICES_KM]))
        self.choice_radius.SetSelection(api.RADIUS_CHOICES_KM.index(settings["radius_km"]))
        vbox.Add(self.choice_radius, 0, wx.LEFT | wx.RIGHT, 10)

        self.choice_units = _labelled(self, vbox, _("lbl_units"), lambda: wx.Choice(
            self, choices=[_("units_metric"), _("units_aviation")]))
        self.choice_units.SetSelection(1 if settings["units"] == "aviation" else 0)
        vbox.Add(self.choice_units, 0, wx.LEFT | wx.RIGHT, 10)

        self.chk_ground = wx.CheckBox(self, label=_("chk_include_ground"))
        self.chk_ground.SetValue(settings["include_ground"])
        vbox.Add(self.chk_ground, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.chk_alerts = wx.CheckBox(self, label=_("chk_alerts"))
        self.chk_alerts.SetValue(settings["alerts"])
        vbox.Add(self.chk_alerts, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.choice_alert = _labelled(self, vbox, _("lbl_alert_distance"), lambda: wx.Choice(
            self, choices=[text.distance_choice(km) for km in api.ALERT_CHOICES_KM]))
        self.choice_alert.SetSelection(api.ALERT_CHOICES_KM.index(settings["alert_km"]))
        vbox.Add(self.choice_alert, 0, wx.LEFT | wx.RIGHT, 10)

        self.chk_emergency = wx.CheckBox(self, label=_("chk_emergency_watch"))
        self.chk_emergency.SetValue(settings["emergency_watch"])
        vbox.Add(self.chk_emergency, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        vbox.Add(wx.StaticText(self, label=_("alerts_note")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        vbox.Add(wx.StaticText(self, label=_("atc_note")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # Credits the data sources (adsbdb's terms and OpenStreetMap's licence ask for it).
        for credit in (_("attribution"), _("attribution_routes"), _("attribution_address")):
            vbox.Add(wx.StaticText(self, label=credit), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        vbox.AddSpacer(10)

        self.SetSizer(vbox)
        if hasattr(self, "SetScrollRate"):
            self.SetScrollRate(0, 20)

        self.txt_search.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        self.list_results.Bind(wx.EVT_LISTBOX, self._on_city_selected)
        self.txt_address.Bind(wx.EVT_TEXT_ENTER, self._on_address_search)
        self.btn_address.Bind(wx.EVT_BUTTON, self._on_address_search)
        self.list_addresses.Bind(wx.EVT_LISTBOX, self._on_address_selected)
        self.txt_coords.Bind(wx.EVT_TEXT_ENTER, self._on_use)
        self.btn_use.Bind(wx.EVT_BUTTON, self._on_use)
        self.set_location(self._location)
        self._update_own()
        core.ui_scale.apply_appearance(self)
        if hasattr(self, "FitInside"):
            self.FitInside()  # after scaling, so large text can still be scrolled to

    def set_location(self, place):
        """Show the saved place of its own (after OK)."""
        self._location = place
        self.txt_location.ChangeValue(text.location_text(place) if place
                                      else _("location_not_set"))

    def _own_controls(self):
        return (self.txt_location, self.txt_search, self.btn_search, self.list_results,
                self.txt_address, self.btn_address, self.list_addresses, self.txt_coords,
                self.btn_use, self.txt_name)

    def _update_own(self):
        """Finding a place of its own is for "Its own place" only; other
        choices skip those controls."""
        own = self.place_choice.is_own()
        for ctrl in self._own_controls():
            ctrl.Enable(own)

    def refresh_places(self):
        """The places changed (Preferences, Places): list them again."""
        self.place_choice.refresh()
        self._update_own()

    def _place_name(self):
        return self.txt_name.GetValue().strip()[:100] or _("default_place_name")

    def _units(self):
        return "aviation" if self.choice_units.GetSelection() == 1 else "metric"

    def chosen_location(self):
        """Its own place, as OK would save it."""
        if self._pending == "city":
            sel = self.list_results.GetSelection()
            if 0 <= sel < len(self._results):
                return self._results[sel]
        elif self._pending == "address":
            sel = self.list_addresses.GetSelection()
            if 0 <= sel < len(self._addresses):
                return dict(self._addresses[sel], name=self._place_name())
        elif self._pending == "coordinates" and self._point:
            return {"name": self._place_name(), "admin1": "", "country": "",
                    "latitude": self._point[0], "longitude": self._point[1],
                    "kind": "coordinates", "detail": ""}
        if self._location and self._location.get("kind", "city") != "city":
            return dict(self._location, name=self._place_name())  # renamed, perhaps
        return self._location

    def get_settings(self):
        """Settings to save."""
        return {
            "place": self.place_choice.key(),
            "location": self.chosen_location(),
            "radius_km": api.RADIUS_CHOICES_KM[max(0, self.choice_radius.GetSelection())],
            "units": self._units(),
            "include_ground": self.chk_ground.GetValue(),
            "alerts": self.chk_alerts.GetValue(),
            "alert_km": api.ALERT_CHOICES_KM[max(0, self.choice_alert.GetSelection())],
            "emergency_watch": self.chk_emergency.GetValue(),
        }

    # --- city search --------------------------------------------------------

    def _on_city_selected(self, event):
        self._pending = "city"   # state only; focus stays where it is
        event.Skip()

    def _on_search(self, event):
        query = self.txt_search.GetValue().strip()
        if len(query) < 2:
            speak(_("search_too_short"), interrupt=True)
            return
        self._search_id += 1
        language = "id" if get_current_language() == "id" else "en"
        speak(_("searching", query=query), interrupt=True)
        _start(_search_worker, self._on_search_done, self._search_id, query, language)

    def _on_search_done(self, search_id, query, places, error):
        if not self or search_id != self._search_id:
            return  # panel closed, or a newer search is running
        if error:
            speak(_("err_search"), interrupt=True)
            return
        self._results = places
        self.list_results.Set([api.place_label(p) for p in places])
        if not places:
            self.lbl_results.SetLabel(_("lbl_results"))
            self.Layout()
            speak(_("search_none", query=query), interrupt=True)
            return
        self.lbl_results.SetLabel(_("lbl_results_count", count=len(places)))
        self.Layout()
        self.list_results.SetSelection(0)
        self._pending = "city"
        # The user pressed Search and is still waiting there: take them to the results.
        if wx.Window.FindFocus() in (self.txt_search, self.btn_search):
            self.list_results.SetFocus()
        elif len(places) == 1:
            speak(_("search_found_one"), interrupt=True)
        else:
            speak(_("search_found", count=len(places)), interrupt=True)

    # --- address search -----------------------------------------------------

    def _on_address_selected(self, event):
        self._pending = "address"
        event.Skip()

    def _on_address_search(self, event):
        # Only on Enter or the button: Nominatim forbids search-as-you-type.
        query = " ".join(self.txt_address.GetValue().split())
        if len(query) < 3:
            speak(_("address_too_short"), interrupt=True)
            return
        self._address_id += 1
        language = "id" if get_current_language() == "id" else "en"
        speak(_("address_searching", query=query), interrupt=True)
        _start(_address_worker, self._on_address_done, self._address_id, query, language)

    def _on_address_done(self, search_id, query, places, error):
        if not self or search_id != self._address_id:
            return
        if error:
            speak(text.location_error_text(error), interrupt=True)
            return
        self._addresses = places
        self.list_addresses.Set([p["detail"] for p in places])
        if not places:
            self.lbl_addresses.SetLabel(_("lbl_addresses"))
            self.Layout()
            speak(_("address_none", query=query), interrupt=True)
            return
        self.lbl_addresses.SetLabel(_("lbl_addresses_count", count=len(places)))
        self.Layout()
        self.list_addresses.SetSelection(0)
        self._pending = "address"
        if wx.Window.FindFocus() in (self.txt_address, self.btn_address):
            self.list_addresses.SetFocus()
        else:
            speak(_("address_found", count=len(places)), interrupt=True)

    # --- coordinates and map links ------------------------------------------

    def _on_use(self, event):
        try:
            found = location.parse_location_text(self.txt_coords.GetValue())
        except location.LocationError as e:
            speak(text.location_error_text(e.kind), interrupt=True)
            return
        if found["kind"] == "short_link":
            self._link_id += 1
            speak(_("link_expanding"), interrupt=True)
            _start(_link_worker, self._on_link_done, self._link_id, found["url"])
            return
        self._use_point(found["latitude"], found["longitude"])

    def _on_link_done(self, link_id, point, error):
        if not self or link_id != self._link_id:
            return
        if error:
            speak(text.location_error_text(error), interrupt=True)
            return
        self._use_point(*point)

    def _use_point(self, latitude, longitude):
        self._point = (latitude, longitude)
        self._pending = "coordinates"
        hint = text.near_airport_hint(latitude, longitude, self._units())
        self.lbl_point.SetLabel(_("point_found", lat=f"{latitude:.5f}", lon=f"{longitude:.5f}",
                                  hint=hint))
        self.Layout()
        speak(_("coords_found", place=self._place_name(), hint=hint), interrupt=True)


class RadarListDialog(wx.Dialog):
    """Every aircraft in range. `get_data()` returns (aircraft, cache);
    `request_refresh(on_done)` starts a background fetch and calls on_done(error)
    on the UI thread, returning False if it could not start. `leg_for(plane)`
    gives a cached route leg; `with_routes(aircraft, callback)` looks routes up
    and then calls callback() on the UI thread. `listen(plane)` opens LiveATC
    for an aircraft (None: for the city); `emergency_intro(aircraft)` returns
    the emergencies to speak first when new data arrives."""

    def __init__(self, parent, place, settings, get_data, request_refresh,
                 leg_for=None, with_routes=None, refresh_now=False,
                 listen=None, emergency_intro=None, track=None):
        super().__init__(parent, title=_("list_title"), size=(720, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._units = settings["units"]
        self._radius_km = settings["radius_km"]
        self._include_ground = settings["include_ground"]
        self._get_data = get_data
        self._request_refresh = request_refresh
        self._leg_for = leg_for or (lambda plane: None)
        self._with_routes = with_routes or (lambda aircraft, callback: callback())
        self._listen = listen
        self._track = track
        self._emergency_intro = emergency_intro or (
            lambda aircraft: text.emergency_text(aircraft, self._units))
        self._loading = refresh_now
        self._announce = False
        self._has_data = False
        self._aircraft = []

        vbox = wx.BoxSizer(wx.VERTICAL)
        label = _("list_label", radius=text.distance_text(self._radius_km, self._units), place=place)
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        # One row per aircraft, so the screen reader reads a whole sentence per arrow press.
        self.list_aircraft = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_aircraft.SetName(label.rstrip(":"))
        vbox.Add(self.list_aircraft, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        label = _("lbl_details")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.txt_details = wx.TextCtrl(self, size=(-1, 70),
                                       style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.txt_details.SetName(label.rstrip(":"))
        vbox.Add(self.txt_details, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.lbl_status = wx.StaticText(self, label="")
        vbox.Add(self.lbl_status, 0, wx.ALL | wx.EXPAND, 8)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_details = wx.Button(self, label=_("btn_details"))
        self.btn_refresh = wx.Button(self, label=_("btn_refresh"))
        self.btn_listen = wx.Button(self, label=_("btn_listen_atc"))
        self.btn_track = wx.Button(self, label=_("btn_track_selected"))
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label=_("btn_close"))
        self.btn_details.SetDefault()
        buttons.Add(self.btn_details, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_refresh, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_listen, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_track, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_close, 0)
        vbox.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(vbox)
        self.SetEscapeId(wx.ID_CANCEL)
        self.btn_details.Bind(wx.EVT_BUTTON, self._on_details)
        self.btn_refresh.Bind(wx.EVT_BUTTON, self._on_refresh)
        self.btn_listen.Bind(wx.EVT_BUTTON, self._on_listen)
        self.btn_track.Bind(wx.EVT_BUTTON, self._on_track)
        self.list_aircraft.Bind(wx.EVT_LISTBOX, self._on_select)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self._fill()
        self.CentreOnParent()
        self.list_aircraft.SetFocus()
        if refresh_now and not self._request_refresh(self._on_refreshed):
            self._loading = False
            self._fill()

    # --- rows -------------------------------------------------------------

    def _row(self, plane):
        return text.aircraft_sentence(plane, self._units, self._leg_for(plane))

    def selected_aircraft(self):
        sel = self.list_aircraft.GetSelection()
        return self._aircraft[sel] if 0 <= sel < len(self._aircraft) else None

    def _fill(self, error=None):
        aircraft, cache = self._get_data()
        previous = self.selected_aircraft()
        sel = self.list_aircraft.GetSelection()
        self._aircraft = list(aircraft)
        self._has_data = cache is not None
        rows = [self._row(p) for p in self._aircraft]
        if not rows:
            if self._loading:
                rows = [_("list_loading")]
            elif cache is not None:
                rows = [text.none_text(self._radius_km, self._units, self._include_ground)]
            else:
                rows = [_("list_no_data")]
        self.list_aircraft.Set(rows)
        # Keep the same aircraft selected when it is still in range.
        if previous is not None:
            for i, plane in enumerate(self._aircraft):
                if plane["id"] == previous["id"]:
                    sel = i
                    break
        self.list_aircraft.SetSelection(sel if 0 <= sel < len(rows) else 0)
        status = []
        if error:
            status.append(text.error_text(error))
        if cache is not None:
            status.append(_("status_updated", time=text.time_text(cache["fetched_wall"]),
                            source=cache["source"]))
        self.lbl_status.SetLabel(" ".join(status))
        self._show_details()
        self.Layout()

    def _refresh_rows(self):
        """Rewrite rows whose text changed (a route arrived), keeping the selection."""
        sel = self.list_aircraft.GetSelection()
        for i, plane in enumerate(self._aircraft):
            row = self._row(plane)
            if i < self.list_aircraft.GetCount() and self.list_aircraft.GetString(i) != row:
                self.list_aircraft.SetString(i, row)
        if sel != wx.NOT_FOUND and self.list_aircraft.GetSelection() != sel:
            self.list_aircraft.SetSelection(sel)

    def _show_details(self):
        plane = self.selected_aircraft()
        self.txt_details.ChangeValue(
            text.details_text(plane, self._units, self._leg_for(plane)) if plane else "")

    # --- events -----------------------------------------------------------

    def _on_select(self, event):
        self._show_details()
        event.Skip()

    def _on_char_hook(self, event):
        if (event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
                and wx.Window.FindFocus() is self.list_aircraft):
            self._on_details()
            return
        event.Skip()

    def _on_details(self, event=None):
        plane = self.selected_aircraft()
        if plane is None:
            sel = self.list_aircraft.GetSelection()
            if sel != wx.NOT_FOUND:
                speak(self.list_aircraft.GetString(sel), interrupt=True)
            return
        self._with_routes([plane], lambda: self._speak_details(plane))

    def _speak_details(self, plane):
        if not self:
            return  # closed while the route was looked up
        self._refresh_rows()
        self._show_details()
        speak(text.details_text(plane, self._units, self._leg_for(plane)), interrupt=True)

    def _on_track(self, event=None):
        if self._track is not None:
            self._track(self.selected_aircraft())

    def _on_listen(self, event=None):
        if self._listen is None:
            return
        plane = self.selected_aircraft()
        if plane is None:
            self._listen(None)
            return
        self._with_routes([plane], lambda: self._listen_to(plane))

    def _listen_to(self, plane):
        if not self:
            return  # closed while the route was looked up
        self._refresh_rows()
        self._show_details()
        self._listen(plane)

    def _on_refresh(self, event=None):
        self._announce = True
        self.lbl_status.SetLabel(_("status_refreshing"))
        speak(_("status_refreshing"), interrupt=True)
        if not self._request_refresh(self._on_refreshed):
            self._announce = False

    def _on_refreshed(self, error):
        if not self:
            return  # closed while the fetch was running
        had_data = self._has_data
        self._loading = False
        self._fill(error)
        # New data: any emergency is spoken before anything else.
        urgent = "" if error else self._emergency_intro(self._aircraft)
        if self._announce or not had_data:
            summary = (text.error_text(error) if error else
                       text.count_text(len(self._aircraft), self._radius_km, self._units,
                                       self._include_ground))
            speak(" ".join(p for p in (urgent, summary) if p), interrupt=True)
        elif urgent:
            speak(urgent, interrupt=True)
        self._announce = False


class TrackFlightDialog(wx.Dialog):
    """Track a flight. `get_rows()` returns [(key, row)] for the tracked
    flights; `track(typed, on_result)` looks a flight up, says where it is and
    tracks it; `untrack(key)` stops; `check_all(on_done)` looks them all up and
    says where they are. Focus stays where the user put it."""

    def __init__(self, parent, get_rows, track, untrack, check_all, initial=""):
        super().__init__(parent, title=_("track_title"), size=(660, 440),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._get_rows = get_rows
        self._track = track
        self._untrack = untrack
        self._check_all = check_all
        self._keys = []

        vbox = wx.BoxSizer(wx.VERTICAL)
        label = _("lbl_track_input")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_flight = wx.TextCtrl(self, value=initial, style=wx.TE_PROCESS_ENTER)
        self.txt_flight.SetName(label.rstrip(":"))
        row.Add(self.txt_flight, 1, wx.RIGHT, 6)
        self.btn_track = wx.Button(self, label=_("btn_track"))
        row.Add(self.btn_track, 0)
        vbox.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        label = _("lbl_tracked", count=api.TRACK_LIMIT)
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.list_tracked = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_tracked.SetName(label.rstrip(":"))
        vbox.Add(self.list_tracked, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        vbox.Add(wx.StaticText(self, label=_("track_note")), 0, wx.ALL, 8)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_untrack = wx.Button(self, label=_("btn_untrack"))
        self.btn_check = wx.Button(self, label=_("btn_check_now"))
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label=_("btn_close"))
        self.btn_track.SetDefault()
        for button in (self.btn_untrack, self.btn_check):
            buttons.Add(button, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_close, 0)
        vbox.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(vbox)
        self.SetEscapeId(wx.ID_CANCEL)
        self.txt_flight.Bind(wx.EVT_TEXT_ENTER, self._on_track)
        self.btn_track.Bind(wx.EVT_BUTTON, self._on_track)
        self.btn_untrack.Bind(wx.EVT_BUTTON, self._on_untrack)
        self.btn_check.Bind(wx.EVT_BUTTON, self._on_check)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self._fill()
        self.CentreOnParent()
        self.txt_flight.SetFocus()
        self.txt_flight.SetInsertionPointEnd()

    def _fill(self):
        rows = self._get_rows()
        self._keys = [key for key, _row in rows]
        sel = self.list_tracked.GetSelection()
        self.list_tracked.Set([row for _key, row in rows] or [_("tracked_empty")])
        count = self.list_tracked.GetCount()
        self.list_tracked.SetSelection(min(sel, count - 1) if sel != wx.NOT_FOUND else 0)
        self.Layout()

    def selected_key(self):
        sel = self.list_tracked.GetSelection()
        return self._keys[sel] if 0 <= sel < len(self._keys) else None

    def _refilled(self):
        if self:
            self._fill()

    def _on_track(self, event=None):
        self._track(self.txt_flight.GetValue(), self._refilled)

    def _on_untrack(self, event=None):
        key = self.selected_key()
        if key is None:
            speak(_("tracked_empty"), interrupt=True)
            return
        self._untrack(key)
        self._fill()

    def _on_check(self, event=None):
        self._check_all(self._refilled)

    def _on_char_hook(self, event):
        if (event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE)
                and wx.Window.FindFocus() is self.list_tracked):
            self._on_untrack()
            return
        event.Skip()
