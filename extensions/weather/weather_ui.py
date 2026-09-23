# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for the Weather extension:
  * WeatherPanel   - the Preferences page: city search, units, attribution.
  * ForecastDialog - a read-only list with one row per day.
Selection changes never move keyboard focus. Focus only moves after the user
asks for something (opening the dialog, pressing Search).
"""

import logging
import threading

import wx

import core.ui_scale
from core.i18n import apply_rtl_layout, get_current_language
from core.speech import speak

import weather_api
import weather_text
from weather_text import _

logger = logging.getLogger(__name__)


def _search_worker(done, search_id, query, language):
    # Worker thread: network only, results go back through wx.CallAfter.
    try:
        places, error = weather_api.search_places(query, language), None
    except weather_api.WeatherError as e:
        places, error = [], e.kind
    except Exception:
        logger.exception("[Weather] City search failed")
        places, error = [], "bad_response"
    wx.CallAfter(done, search_id, query, places, error)


class WeatherPanel(wx.Panel):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self._location = settings.get("location")
        self._results = []
        self._search_id = 0

        vbox = wx.BoxSizer(wx.VERTICAL)

        label = _("lbl_current_location")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.txt_location = wx.TextCtrl(self, style=wx.TE_READONLY)
        self.txt_location.SetName(label)
        vbox.Add(self.txt_location, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        label = _("lbl_search")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_search = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.txt_search.SetName(label)
        row.Add(self.txt_search, 1, wx.RIGHT, 6)
        self.btn_search = wx.Button(self, label=_("btn_search"))
        row.Add(self.btn_search, 0)
        vbox.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.lbl_results = wx.StaticText(self, label=_("lbl_results"))
        vbox.Add(self.lbl_results, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.list_results = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_results.SetName(_("lbl_results"))
        vbox.Add(self.list_results, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        label = _("lbl_units")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.choice_units = wx.Choice(self, choices=[_("units_metric"), _("units_imperial")])
        self.choice_units.SetName(label)
        self.choice_units.SetSelection(1 if settings.get("units") == "imperial" else 0)
        vbox.Add(self.choice_units, 0, wx.LEFT | wx.RIGHT, 10)

        # Required by Open-Meteo's licence (CC BY 4.0).
        vbox.Add(wx.StaticText(self, label=_("attribution")), 0, wx.ALL, 10)

        self.SetSizer(vbox)

        self.txt_search.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        self.set_location(self._location)
        core.ui_scale.apply_appearance(self)

    def set_location(self, location):
        self._location = location
        self.txt_location.SetValue(weather_api.place_label(location) if location
                                   else _("location_not_set"))

    def get_settings(self):
        """Settings to save: the selected search result (if any) becomes the location."""
        location = self._location
        sel = self.list_results.GetSelection()
        if 0 <= sel < len(self._results):
            location = self._results[sel]
        units = "imperial" if self.choice_units.GetSelection() == 1 else "metric"
        return {"location": location, "units": units}

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
                         daemon=True, name="weather-search").start()

    def _on_search_done(self, search_id, query, places, error):
        if not self or search_id != self._search_id:
            return  # panel closed, or a newer search is running
        if error:
            speak(weather_text.error_text(error), interrupt=True)
            return
        self._results = places
        self.list_results.Set([weather_api.place_label(p) for p in places])
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


class ForecastDialog(wx.Dialog):
    """Read-only daily forecast. `get_cache()` returns the current cache (or None);
    `request_refresh(on_done)` starts a background fetch and calls on_done(error)
    on the UI thread, returning False if it could not start."""

    def __init__(self, parent, location, units, get_cache, request_refresh, refresh_now=False):
        super().__init__(parent, title=_("forecast_title"), size=(620, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._units = units
        self._get_cache = get_cache
        self._request_refresh = request_refresh
        self._loading = refresh_now
        self._announce = False
        self._has_data = False

        vbox = wx.BoxSizer(wx.VERTICAL)
        label = _("forecast_label", place=weather_api.place_label(location),
                  unit=weather_text.unit_name(units))
        vbox.Add(wx.StaticText(self, label=label), 0, wx.ALL, 8)
        # One row per day, so the screen reader reads a whole day per arrow press.
        self.list_days = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_days.SetName(label)
        vbox.Add(self.list_days, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        self.lbl_status = wx.StaticText(self, label="")
        vbox.Add(self.lbl_status, 0, wx.ALL | wx.EXPAND, 8)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_refresh = wx.Button(self, label=_("btn_refresh"))
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label=_("btn_close"))
        self.btn_close.SetDefault()
        buttons.Add(self.btn_refresh, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_close, 0)
        vbox.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(vbox)
        self.SetEscapeId(wx.ID_CANCEL)
        self.btn_refresh.Bind(wx.EVT_BUTTON, self._on_refresh)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self._fill()
        self.CentreOnParent()
        self.list_days.SetFocus()
        if refresh_now and not self._request_refresh(self._on_refreshed):
            self._loading = False
            self._fill()

    def _fill(self, error=None):
        cache = self._get_cache()
        rows = weather_text.forecast_rows(cache["forecast"], self._units) if cache else []
        self._has_data = bool(rows)
        status = []
        if error:
            status.append(weather_text.error_text(error))
        if cache:
            status.append(_("status_updated", time=weather_text.time_text(cache["fetched_at"])))
        if not rows:
            rows = [_("forecast_loading") if self._loading else _("forecast_empty")]
        sel = self.list_days.GetSelection()
        self.list_days.Set(rows)
        self.list_days.SetSelection(sel if 0 <= sel < len(rows) else 0)
        self.lbl_status.SetLabel(" ".join(status))
        self.Layout()

    def _on_refresh(self, event):
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
        if self._announce or not had_data:
            speak(weather_text.error_text(error) if error else _("forecast_updated"),
                  interrupt=True)
        self._announce = False
