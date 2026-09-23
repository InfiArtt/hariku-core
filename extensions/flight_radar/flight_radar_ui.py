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
  * FlightRadarPanel - the Preferences page: city search, radius, units,
                       ground traffic, overhead alerts, the emergency watch,
                       a note on Listen to ATC, attribution.
  * RadarListDialog  - every aircraft in range, one sentence per row, nearest
                       first, with Details (Enter), Refresh and Listen to ATC.
Selection changes never move keyboard focus. Focus only moves after the user
asks for something (opening the dialog, pressing Search). Rows that change
after a refresh or a route lookup keep the current selection.
"""

import logging
import threading

import wx

import core.ui_scale
from core.i18n import apply_rtl_layout, get_current_language
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


def _labelled(parent, sizer, label, make_control):
    """A StaticText created right before the control (screen readers take the
    label from the previous window), which also gets the label as its name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
    control = make_control()
    control.SetName(label.rstrip(":"))
    return control


class FlightRadarPanel(wx.Panel):
    def __init__(self, parent, settings, weather_location=None):
        super().__init__(parent)
        self._location = settings.get("location")
        self._weather_location = weather_location
        self._results = []
        self._search_id = 0

        vbox = wx.BoxSizer(wx.VERTICAL)

        self.txt_location = _labelled(self, vbox, _("lbl_current_location"),
                                      lambda: wx.TextCtrl(self, style=wx.TE_READONLY))
        vbox.Add(self.txt_location, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_search = _labelled(self, vbox, _("lbl_search"),
                                    lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER))
        row.Add(self.txt_search, 1, wx.RIGHT, 6)
        self.btn_search = wx.Button(self, label=_("btn_search"))
        row.Add(self.btn_search, 0)
        vbox.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.lbl_results = wx.StaticText(self, label=_("lbl_results"))
        vbox.Add(self.lbl_results, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.list_results = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_results.SetName(_("lbl_results").rstrip(":"))
        vbox.Add(self.list_results, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

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

        # Credits the data sources (adsbdb's terms ask for the route credit).
        vbox.Add(wx.StaticText(self, label=_("attribution")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        vbox.Add(wx.StaticText(self, label=_("attribution_routes")), 0, wx.ALL, 10)

        self.SetSizer(vbox)

        self.txt_search.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        self.set_location(self._location, weather_location)
        core.ui_scale.apply_appearance(self)

    def set_location(self, location, weather_location=None):
        self._location = location
        self._weather_location = weather_location
        if location:
            value = api.place_label(location)
        elif weather_location:
            value = _("location_from_weather", place=api.place_label(weather_location))
        else:
            value = _("location_not_set")
        self.txt_location.ChangeValue(value)

    def get_settings(self):
        """Settings to save: the selected search result (if any) becomes the location."""
        location = self._location
        sel = self.list_results.GetSelection()
        if 0 <= sel < len(self._results):
            location = self._results[sel]
        return {
            "location": location,
            "radius_km": api.RADIUS_CHOICES_KM[max(0, self.choice_radius.GetSelection())],
            "units": "aviation" if self.choice_units.GetSelection() == 1 else "metric",
            "include_ground": self.chk_ground.GetValue(),
            "alerts": self.chk_alerts.GetValue(),
            "alert_km": api.ALERT_CHOICES_KM[max(0, self.choice_alert.GetSelection())],
            "emergency_watch": self.chk_emergency.GetValue(),
        }

    def _on_search(self, event):
        query = self.txt_search.GetValue().strip()
        if len(query) < 2:
            speak(_("search_too_short"), interrupt=True)
            return
        self._search_id += 1
        language = "id" if get_current_language() == "id" else "en"
        speak(_("searching", query=query), interrupt=True)
        threading.Thread(target=_search_worker,
                         args=(self._on_search_done, self._search_id, query, language),
                         daemon=True, name="flight-radar-search").start()

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
        # The user pressed Search and is still waiting there: take them to the results.
        if wx.Window.FindFocus() in (self.txt_search, self.btn_search):
            self.list_results.SetFocus()
        elif len(places) == 1:
            speak(_("search_found_one"), interrupt=True)
        else:
            speak(_("search_found", count=len(places)), interrupt=True)


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
                 listen=None, emergency_intro=None):
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
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label=_("btn_close"))
        self.btn_details.SetDefault()
        buttons.Add(self.btn_details, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_refresh, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_listen, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_close, 0)
        vbox.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(vbox)
        self.SetEscapeId(wx.ID_CANCEL)
        self.btn_details.Bind(wx.EVT_BUTTON, self._on_details)
        self.btn_refresh.Bind(wx.EVT_BUTTON, self._on_refresh)
        self.btn_listen.Bind(wx.EVT_BUTTON, self._on_listen)
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
