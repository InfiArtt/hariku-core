# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for the Earthquakes & Tsunami extension:
  * EarthquakePanel - the Preferences page: the disclaimer, the location (city
                      search, or the Weather city, also via "Use the Weather
                      location"), which alerts to give, sounds, the credits.
  * RecentDialog    - recent earthquakes, one sentence per row, newest first,
                      with Details (Enter), Refresh and an optional worldwide
                      (USGS) part.
Selection changes never move keyboard focus. Focus only moves after the user
asks for something (opening the dialog, pressing Search).
"""

import logging
import threading
import time

import wx

import core.ui_scale
from core.i18n import apply_rtl_layout, get_current_language
from core.speech import speak

import earthquake_api as api
import earthquake_text as text
from earthquake_text import _

logger = logging.getLogger(__name__)


def _search_worker(done, search_id, query, language):
    # Worker thread: network only, results go back through wx.CallAfter.
    try:
        places, error = api.search_places(query, language), None
    except api.QuakeError as e:
        places, error = [], e.kind
    except Exception:
        logger.exception("[Earthquakes] City search failed")
        places, error = [], "bad_response"
    wx.CallAfter(done, search_id, query, places, error)


def _labelled(parent, sizer, label, make_control, border=10):
    """A StaticText created right before the control (screen readers take the
    label from the previous window), which also gets the label as its name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, border)
    control = make_control()
    control.SetName(label.rstrip(":"))
    return control


# The page is taller than the Preferences dialog, so it scrolls (and scrolls
# the focused control into view). A plain panel where wx is not the real one.
_PageBase = wx.ScrolledWindow if isinstance(getattr(wx, "ScrolledWindow", None), type) else wx.Panel


class EarthquakePanel(_PageBase):
    """OK saves the search result selected last, or the Weather city after
    "Use the Weather location", or keeps the saved location."""

    def __init__(self, parent, settings, weather_location=None):
        super().__init__(parent)
        self._location = settings.get("location")
        self._weather_location = weather_location
        self._results = []
        self._pending = None     # "place" or "weather"
        self._search_id = 0

        vbox = wx.BoxSizer(wx.VERTICAL)
        # Safety first: shown above everything else.
        self.lbl_disclaimer = wx.StaticText(self, label=_("disclaimer"))
        vbox.Add(self.lbl_disclaimer, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

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
        self.list_results = wx.ListBox(self, size=(-1, 70), style=wx.LB_SINGLE)
        self.list_results.SetName(_("lbl_results").rstrip(":"))
        vbox.Add(self.list_results, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.btn_use_weather = wx.Button(self, label=_("btn_use_weather"))
        vbox.Add(self.btn_use_weather, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.chk_tsunami = wx.CheckBox(self, label=_("chk_tsunami"))
        self.chk_tsunami.SetValue(settings["tsunami_alerts"])
        vbox.Add(self.chk_tsunami, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.chk_nearby = wx.CheckBox(self, label=_("chk_nearby"))
        self.chk_nearby.SetValue(settings["nearby_alerts"])
        vbox.Add(self.chk_nearby, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.choice_distance = _labelled(self, vbox, _("lbl_alert_distance"), lambda: wx.Choice(
            self, choices=[text.km_text(km) for km in api.ALERT_DISTANCES_KM]))
        self.choice_distance.SetSelection(api.ALERT_DISTANCES_KM.index(settings["alert_km"]))
        vbox.Add(self.choice_distance, 0, wx.LEFT | wx.RIGHT, 10)

        self.choice_magnitude = _labelled(self, vbox, _("lbl_min_magnitude"), lambda: wx.Choice(
            self, choices=[text.magnitude_value(m) for m in api.MIN_MAGNITUDES]))
        self.choice_magnitude.SetSelection(api.MIN_MAGNITUDES.index(settings["min_magnitude"]))
        vbox.Add(self.choice_magnitude, 0, wx.LEFT | wx.RIGHT, 10)

        self.chk_felt = wx.CheckBox(self, label=_("chk_felt"))
        self.chk_felt.SetValue(settings["felt_alerts"])
        vbox.Add(self.chk_felt, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.txt_felt_names = _labelled(self, vbox, _("lbl_felt_names"), lambda: wx.TextCtrl(
            self, value=settings.get("felt_names", "")))
        vbox.Add(self.txt_felt_names, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.lbl_felt_note = wx.StaticText(self, label="")
        vbox.Add(self.lbl_felt_note, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.chk_world = wx.CheckBox(self, label=_("chk_world"))
        self.chk_world.SetValue(settings["world_alerts"])
        vbox.Add(self.chk_world, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.chk_sounds = wx.CheckBox(self, label=_("chk_sounds"))
        self.chk_sounds.SetValue(settings["sounds"])
        vbox.Add(self.chk_sounds, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        vbox.Add(wx.StaticText(self, label=_("alerts_note")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        # BMKG's open data asks to be credited; Open-Meteo's too.
        for credit in (_("attribution"), _("attribution_search")):
            vbox.Add(wx.StaticText(self, label=credit), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        vbox.AddSpacer(10)

        self.SetSizer(vbox)
        if hasattr(self, "SetScrollRate"):
            self.SetScrollRate(0, 20)

        self.txt_search.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        self.list_results.Bind(wx.EVT_LISTBOX, self._on_result_selected)
        self.btn_use_weather.Bind(wx.EVT_BUTTON, self._on_use_weather)
        self.set_location(self._location, weather_location)
        core.ui_scale.apply_appearance(self)
        if hasattr(self, "FitInside"):
            self.FitInside()  # after scaling, so large text can still be scrolled to

    def set_location(self, place, weather_location=None):
        self._location = place
        self._weather_location = weather_location
        self.txt_location.ChangeValue(text.location_text(place, weather_location))
        self.lbl_felt_note.SetLabel(text.felt_note(place or weather_location,
                                                   self.txt_felt_names.GetValue()))
        self.Layout()

    def chosen_location(self):
        """The location OK would save (None means the Weather city)."""
        if self._pending == "place":
            sel = self.list_results.GetSelection()
            if 0 <= sel < len(self._results):
                return self._results[sel]
        elif self._pending == "weather":
            return None
        return self._location

    def get_settings(self):
        """Settings to save."""
        return {
            "location": self.chosen_location(),
            "tsunami_alerts": self.chk_tsunami.GetValue(),
            "nearby_alerts": self.chk_nearby.GetValue(),
            "alert_km": api.ALERT_DISTANCES_KM[max(0, self.choice_distance.GetSelection())],
            "min_magnitude": api.MIN_MAGNITUDES[max(0, self.choice_magnitude.GetSelection())],
            "felt_alerts": self.chk_felt.GetValue(),
            "felt_names": self.txt_felt_names.GetValue(),
            "world_alerts": self.chk_world.GetValue(),
            "sounds": self.chk_sounds.GetValue(),
        }

    def _on_result_selected(self, event):
        self._pending = "place"   # state only; focus stays where it is
        event.Skip()

    def _on_use_weather(self, event):
        """Drop this page's own city so the Weather city is used again. Focus
        stays on the button."""
        self._pending = "weather"
        self.list_results.SetSelection(wx.NOT_FOUND)
        # SetValue (not ChangeValue) so Preferences knows there is something to save.
        self.txt_location.SetValue(text.location_text(None, self._weather_location))
        self.lbl_felt_note.SetLabel(text.felt_note(self._weather_location,
                                                   self.txt_felt_names.GetValue()))
        if self._weather_location:
            speak(_("use_weather_done", place=api.place_label(self._weather_location)),
                  interrupt=True)
        else:
            speak(_("use_weather_none"), interrupt=True)

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
                         daemon=True, name="earthquake-search").start()

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
        self._pending = "place"
        # The user pressed Search and is still waiting there: take them to the results.
        if wx.Window.FindFocus() in (self.txt_search, self.btn_search):
            self.list_results.SetFocus()
        elif len(places) == 1:
            speak(_("search_found_one"), interrupt=True)
        else:
            speak(_("search_found", count=len(places)), interrupt=True)


class RecentDialog(wx.Dialog):
    """Recent earthquakes. `get_data()` returns (quakes, updated_at);
    `request_refresh(on_done)` fetches BMKG's lists (and USGS when included)
    and calls on_done(error) on the UI thread, returning False if it could not
    start; `request_world(on_done)` fetches only the USGS part;
    `set_list_world(value)` saves whether USGS is included; `get_location()`
    is the user's location or None."""

    def __init__(self, parent, get_data, request_refresh, get_location, list_world=False,
                 set_list_world=None, request_world=None, refresh_now=False, now=time.time):
        super().__init__(parent, title=_("list_title"), size=(760, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._get_data = get_data
        self._request_refresh = request_refresh
        self._request_world = request_world
        self._get_location = get_location
        self._set_list_world = set_list_world
        self._now = now
        self._loading = refresh_now
        self._announce = False
        self._has_data = False
        self._quakes = []

        vbox = wx.BoxSizer(wx.VERTICAL)
        label = _("list_label")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        # One row per quake, so the screen reader reads a whole sentence per arrow press.
        self.list_quakes = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_quakes.SetName(label.rstrip(":"))
        vbox.Add(self.list_quakes, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        label = _("lbl_details")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.txt_details = wx.TextCtrl(self, size=(-1, 90),
                                       style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.txt_details.SetName(label.rstrip(":"))
        vbox.Add(self.txt_details, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.chk_world = wx.CheckBox(self, label=_("chk_list_world"))
        self.chk_world.SetValue(bool(list_world))
        vbox.Add(self.chk_world, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        self.lbl_status = wx.StaticText(self, label="")
        vbox.Add(self.lbl_status, 0, wx.ALL | wx.EXPAND, 8)
        vbox.Add(wx.StaticText(self, label=_("disclaimer")), 0, wx.LEFT | wx.RIGHT, 8)
        vbox.Add(wx.StaticText(self, label=_("attribution")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_details = wx.Button(self, label=_("btn_details"))
        self.btn_refresh = wx.Button(self, label=_("btn_refresh"))
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label=_("btn_close"))
        self.btn_details.SetDefault()
        buttons.Add(self.btn_details, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_refresh, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_close, 0)
        vbox.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(vbox)
        self.SetEscapeId(wx.ID_CANCEL)
        self.btn_details.Bind(wx.EVT_BUTTON, self._on_details)
        self.btn_refresh.Bind(wx.EVT_BUTTON, self._on_refresh)
        self.chk_world.Bind(wx.EVT_CHECKBOX, self._on_world)
        self.list_quakes.Bind(wx.EVT_LISTBOX, self._on_select)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self._fill()
        self.CentreOnParent()
        self.list_quakes.SetFocus()
        if refresh_now and not self._request_refresh(self._on_refreshed):
            self._loading = False
            self._fill()

    # --- rows -------------------------------------------------------------

    def selected_quake(self):
        sel = self.list_quakes.GetSelection()
        return self._quakes[sel] if 0 <= sel < len(self._quakes) else None

    def _fill(self, error=None):
        quakes, updated_at = self._get_data()
        previous = self.selected_quake()
        sel = self.list_quakes.GetSelection()
        location, now = self._get_location(), self._now()
        self._quakes = list(quakes)
        self._has_data = updated_at is not None
        rows = [text.row_text(q, location, now) for q in self._quakes]
        if not rows:
            rows = [_("list_loading") if self._loading else
                    (_("list_empty") if self._has_data else _("no_data"))]
        self.list_quakes.Set(rows)
        # Keep the same quake selected when it is still listed.
        if previous is not None:
            for i, quake in enumerate(self._quakes):
                if quake["source"] == previous["source"] and quake["id"] == previous["id"]:
                    sel = i
                    break
        self.list_quakes.SetSelection(sel if 0 <= sel < len(rows) else 0)
        status = []
        if error:
            status.append(text.error_text(error))
        if updated_at is not None:
            status.append(_("status_updated", time=text.time_text(updated_at, now)))
        self.lbl_status.SetLabel(" ".join(status))
        self._show_details()
        self.Layout()

    def _show_details(self):
        quake = self.selected_quake()
        self.txt_details.ChangeValue(
            "\n".join(text.details_lines(quake, self._get_location(), self._now()))
            if quake else "")

    # --- events -----------------------------------------------------------

    def _on_select(self, event):
        self._show_details()   # focus stays on the list
        event.Skip()

    def _on_char_hook(self, event):
        if (event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
                and wx.Window.FindFocus() is self.list_quakes):
            self._on_details()
            return
        event.Skip()

    def _on_details(self, event=None):
        quake = self.selected_quake()
        if quake is None:
            sel = self.list_quakes.GetSelection()
            if sel != wx.NOT_FOUND:
                speak(self.list_quakes.GetString(sel), interrupt=True)
            return
        speak(text.details_speech(quake, self._get_location(), self._now()), interrupt=True)

    def _on_refresh(self, event=None):
        self._announce = True
        self.lbl_status.SetLabel(_("status_refreshing"))
        speak(_("status_refreshing"), interrupt=True)
        if not self._request_refresh(self._on_refreshed):
            self._announce = False

    def _on_world(self, event=None):
        value = self.chk_world.GetValue()
        if self._set_list_world is not None:
            self._set_list_world(value)
        self._fill()
        if value and self._request_world is not None:
            self._announce = True
            self._request_world(self._on_refreshed)

    def _on_refreshed(self, error):
        if not self:
            return  # closed while the fetch was running
        had_data = self._has_data
        self._loading = False
        self._fill(error)
        if self._announce or not had_data:
            speak(text.error_text(error) if error else text.list_count_text(len(self._quakes)),
                  interrupt=True)
        self._announce = False
