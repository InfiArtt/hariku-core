# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for the Air Quality extension:
  * AirQualityPanel   - the Preferences page: city search (or the Weather
                        city), the unhealthy-air announcement, notes, attribution.
  * AirForecastDialog - two read-only lists: the next hours, and the next days.
Selection changes never move keyboard focus. Focus only moves after the user
asks for something (opening the dialog, pressing Search).
"""

import logging
import threading

import wx

import core.ui_scale
from core.i18n import apply_rtl_layout, get_current_language
from core.speech import speak

import air_quality_api as api
import air_quality_text as text
from air_quality_text import _

logger = logging.getLogger(__name__)


def _search_worker(done, search_id, query, language):
    # Worker thread: network only, results go back through wx.CallAfter.
    try:
        places, error = api.search_places(query, language), None
    except api.AirError as e:
        places, error = [], e.kind
    except Exception:
        logger.exception("[Air Quality] City search failed")
        places, error = [], "bad_response"
    wx.CallAfter(done, search_id, query, places, error)


def _labelled(parent, sizer, label, make_control):
    """A StaticText created right before the control (screen readers take the
    label from the previous window), which also gets the label as its name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
    control = make_control()
    control.SetName(label.rstrip(":"))
    return control


# The page can be taller than the Preferences dialog with large text, so it
# scrolls. A plain panel where wx is not the real one (the unit tests).
_PageBase = wx.ScrolledWindow if isinstance(getattr(wx, "ScrolledWindow", None), type) else wx.Panel


class AirQualityPanel(_PageBase):
    """OK saves the search result selected last, or the Weather city after
    "Use the Weather location", or keeps the saved city."""

    def __init__(self, parent, settings, weather_location=None):
        super().__init__(parent)
        self._location = settings.get("location")
        self._weather_location = weather_location
        self._results = []
        self._pending = None     # "place" or "weather"
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
        self.list_results = wx.ListBox(self, size=(-1, 90), style=wx.LB_SINGLE)
        self.list_results.SetName(_("lbl_results").rstrip(":"))
        vbox.Add(self.list_results, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.btn_use_weather = wx.Button(self, label=_("btn_use_weather"))
        vbox.Add(self.btn_use_weather, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.chk_alert = wx.CheckBox(self, label=_("chk_alert"))
        self.chk_alert.SetValue(bool(settings.get("alert")))
        vbox.Add(self.chk_alert, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        for note in (_("note_index"), _("note_area"), _("note_tips"), _("attribution")):
            vbox.Add(wx.StaticText(self, label=note), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
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

    def _location_text(self, place, weather_location):
        if place:
            return api.place_label(place)
        if weather_location:
            return _("location_from_weather", place=api.place_label(weather_location))
        return _("location_not_set")

    def set_location(self, place, weather_location=None):
        self._location = place
        self._weather_location = weather_location
        self.txt_location.ChangeValue(self._location_text(place, weather_location))

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
        return {"location": self.chosen_location(), "alert": self.chk_alert.GetValue()}

    def _on_result_selected(self, event):
        self._pending = "place"   # state only; focus stays where it is
        event.Skip()

    def _on_use_weather(self, event):
        self._pending = "weather"
        self.list_results.SetSelection(wx.NOT_FOUND)
        # SetValue (not ChangeValue) so Preferences knows there is something to save.
        self.txt_location.SetValue(self._location_text(None, self._weather_location))
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
                         daemon=True, name="air-quality-search").start()

    def _on_search_done(self, search_id, query, places, error):
        if not self or search_id != self._search_id:
            return  # panel closed, or a newer search is running
        if error:
            speak(text.error_text(error), interrupt=True)
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


class AirForecastDialog(wx.Dialog):
    """The next hours and the next days, one sentence per row. `get_cache()`
    returns the current cache (or None); `request_refresh(on_done)` starts a
    background fetch and calls on_done(error) on the UI thread, returning False
    if it could not start."""

    def __init__(self, parent, location, get_cache, request_refresh, refresh_now=False):
        super().__init__(parent, title=_("forecast_title"), size=(680, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._get_cache = get_cache
        self._request_refresh = request_refresh
        self._loading = refresh_now
        self._announce = False
        self._has_data = False
        self._first_row = ""

        vbox = wx.BoxSizer(wx.VERTICAL)
        # One row per hour or day, so the screen reader reads a whole one per arrow press.
        label = _("lbl_hours", place=api.place_label(location))
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.list_hours = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_hours.SetName(label.rstrip(":"))
        vbox.Add(self.list_hours, 3, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        label = _("lbl_days")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.list_days = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_days.SetName(label.rstrip(":"))
        vbox.Add(self.list_days, 2, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

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
        self.list_hours.SetFocus()
        if refresh_now and not self._request_refresh(self._on_refreshed):
            self._loading = False
            self._fill()

    @staticmethod
    def _set_rows(listbox, rows):
        sel = listbox.GetSelection()
        listbox.Set(rows)
        listbox.SetSelection(sel if 0 <= sel < len(rows) else 0)

    def _fill(self, error=None):
        cache = self._get_cache()
        forecast = cache["forecast"] if cache else None
        hours, days = [], []
        if forecast and forecast.get("has_data"):
            hours = text.hour_rows(forecast)
            days = text.day_rows(forecast)
        self._has_data = bool(hours or days)
        status = []
        if error:
            status.append(text.error_text(error))
        if cache:
            status.append(_("status_updated", time=text.time_text(cache["fetched_at"])))
        if forecast and not forecast.get("has_data"):
            empty = _("forecast_no_data")
        elif self._loading and not forecast:
            empty = _("forecast_loading")
        else:
            empty = _("forecast_empty")
        hours = hours or [empty]
        days = days or [empty]
        self._first_row = hours[0]
        self._set_rows(self.list_hours, hours)
        self._set_rows(self.list_days, days)
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
            if error:
                speak(text.error_text(error), interrupt=True)
            else:
                speak(_("forecast_updated") if self._has_data else self._first_row, interrupt=True)
        self._announce = False
