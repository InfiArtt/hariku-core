# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for the Space extension:
  * SpacePanel     - the Preferences page: the place (one from Preferences,
                     Places, or its own city, found with the city search),
                     the reminder lead time, notes and credits.
  * LaunchesDialog - the next rocket launches, one sentence per row, with
                     Details (Enter), Refresh and Remind me.
Selection changes never move keyboard focus. Focus only moves after the user
asks for something (opening the dialog, pressing Search).
"""

import logging
import threading

import wx

import core.places
import core.ui_scale
from core.i18n import apply_rtl_layout, get_current_language
from core.places_ui import PlaceChoice
from core.speech import speak

import space_api as api
import space_text as text
from space_text import _

logger = logging.getLogger(__name__)


def _search_worker(done, search_id, query, language):
    # Worker thread: network only, results go back through wx.CallAfter.
    try:
        places, error = api.search_places(query, language), None
    except api.SpaceError as e:
        places, error = [], e.kind
    except Exception:
        logger.exception("[Space] City search failed")
        places, error = [], "bad_response"
    wx.CallAfter(done, search_id, query, places, error)


def _labelled(parent, sizer, label, make_control):
    """A StaticText created right before the control (screen readers take the
    label from the previous window), which also gets the label as its name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
    control = make_control()
    control.SetName(label.rstrip(":"))
    return control


def lead_choice_text(minutes):
    return text.duration_text(minutes)


class SpacePanel(wx.Panel):
    """OK saves which place to use ("Place:"), and as its own city the
    search result selected last, or keeps the saved one. The city search is
    only available while "Its own place" is chosen."""

    def __init__(self, parent, settings):
        super().__init__(parent)
        self._location = settings.get("location")
        self._results = []
        self._pending = None     # "place" after a search result was selected
        self._search_id = 0

        vbox = wx.BoxSizer(wx.VERTICAL)
        choice = (core.places.normalize_choice(settings.get("place"))
                  or core.places.initial_choice(self._location))
        self.place_choice = PlaceChoice(self, vbox, choice, own=True,
                                        on_change=lambda key: self._update_own())

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

        self.choice_lead = _labelled(self, vbox, _("lbl_lead"), lambda: wx.Choice(
            self, choices=[lead_choice_text(m) for m in api.LEAD_CHOICES]))
        self.choice_lead.SetSelection(api.LEAD_CHOICES.index(settings.get("lead_minutes",
                                                                          api.DEFAULT_LEAD)))
        vbox.Add(self.choice_lead, 0, wx.LEFT | wx.RIGHT, 10)

        for note in (_("offline_note"), _("privacy_note")):
            vbox.Add(wx.StaticText(self, label=note), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        # Credits the data sources (Open-Meteo's licence asks for it).
        for credit in (_("attribution_iss"), _("attribution_launches"), _("attribution_search")):
            vbox.Add(wx.StaticText(self, label=credit), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        vbox.AddSpacer(10)
        self.SetSizer(vbox)

        self.txt_search.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        self.list_results.Bind(wx.EVT_LISTBOX, self._on_result_selected)
        self.set_location(self._location)
        self._update_own()
        core.ui_scale.apply_appearance(self)

    def set_location(self, place):
        """Show the saved city of its own (after OK)."""
        self._location = place
        self._pending = None
        self.txt_location.ChangeValue(api.place_label(place) if place else _("location_not_set"))

    def _update_own(self):
        """The city search is for "Its own place" only; other choices skip it."""
        own = self.place_choice.is_own()
        for ctrl in (self.txt_location, self.txt_search, self.btn_search, self.list_results):
            ctrl.Enable(own)

    def refresh_places(self):
        """The places changed (Preferences, Places): list them again."""
        self.place_choice.refresh()
        self._update_own()

    def chosen_location(self):
        """Its own city, as OK would save it."""
        if self._pending == "place":
            sel = self.list_results.GetSelection()
            if 0 <= sel < len(self._results):
                return self._results[sel]
        return self._location

    def get_settings(self):
        """Settings to save."""
        lead = api.LEAD_CHOICES[max(0, self.choice_lead.GetSelection())]
        return {"place": self.place_choice.key(), "location": self.chosen_location(),
                "lead_minutes": lead}

    def _on_result_selected(self, event):
        self._pending = "place"   # state only; focus stays where it is
        event.Skip()

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
                         daemon=True, name="space-search").start()

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


class LaunchesDialog(wx.Dialog):
    """The next rocket launches.

    `get_data()` returns (launches to show, launch state); `request_refresh(
    on_done, explicit)` returns (status, message): status "started" means
    on_done(error) runs on the UI thread later, otherwise `message` says why
    nothing was fetched. `has_reminder(launch_id)`; `toggle_reminder(launch)`
    returns the text to speak; `lead_minutes()`; `tz` is the display time zone
    and `now()` the current aware time."""

    def __init__(self, parent, label, get_data, request_refresh, has_reminder, toggle_reminder,
                 lead_minutes, tz, now, refresh_now=False):
        super().__init__(parent, title=_("launches_title"), size=(720, 480),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._get_data = get_data
        self._request_refresh = request_refresh
        self._has_reminder = has_reminder
        self._toggle_reminder = toggle_reminder
        self._lead_minutes = lead_minutes
        self._tz = tz
        self._now = now
        self._loading = refresh_now
        self._announce = False
        self._has_data = False
        self._launches = []

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        # One row per launch, so the screen reader reads a whole sentence per arrow press.
        self.list_launches = wx.ListBox(self, style=wx.LB_SINGLE)
        self.list_launches.SetName(label.rstrip(":"))
        vbox.Add(self.list_launches, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        details_label = _("lbl_details")
        vbox.Add(wx.StaticText(self, label=details_label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.txt_details = wx.TextCtrl(self, size=(-1, 90), style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.txt_details.SetName(details_label.rstrip(":"))
        vbox.Add(self.txt_details, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.lbl_status = wx.StaticText(self, label="")
        vbox.Add(self.lbl_status, 0, wx.ALL | wx.EXPAND, 8)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_details = wx.Button(self, label=_("btn_details"))
        self.btn_refresh = wx.Button(self, label=_("btn_refresh"))
        self.btn_remind = wx.Button(self, label=_("btn_remind"))
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label=_("btn_close"))
        self.btn_details.SetDefault()
        for button in (self.btn_details, self.btn_refresh, self.btn_remind):
            buttons.Add(button, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_close, 0)
        vbox.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(vbox)
        self.SetEscapeId(wx.ID_CANCEL)
        self.btn_details.Bind(wx.EVT_BUTTON, self._on_details)
        self.btn_refresh.Bind(wx.EVT_BUTTON, self._on_refresh)
        self.btn_remind.Bind(wx.EVT_BUTTON, self._on_remind)
        self.list_launches.Bind(wx.EVT_LISTBOX, self._on_select)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self._fill()
        self.CentreOnParent()
        self.list_launches.SetFocus()
        if refresh_now:
            status, _message = self._request_refresh(self._on_refreshed, False)
            if status != "started":
                self._loading = False
                self._fill()

    # --- rows -------------------------------------------------------------

    def selected_launch(self):
        sel = self.list_launches.GetSelection()
        return self._launches[sel] if 0 <= sel < len(self._launches) else None

    def _row(self, launch):
        return text.launch_row(launch, self._tz, self._now(), self._has_reminder(launch["id"]))

    def _fill(self, error=None):
        launches, state = self._get_data()
        previous = self.selected_launch()
        sel = self.list_launches.GetSelection()
        self._launches = list(launches)
        self._has_data = bool(state and state.get("fetched_at"))
        rows = [self._row(launch) for launch in self._launches]
        if not rows:
            if self._loading:
                rows = [_("launches_loading")]
            elif self._has_data:
                rows = [_("launches_empty")]
            else:
                rows = [_("launches_no_data")]
        self.list_launches.Set(rows)
        # Keep the same launch selected when it is still listed.
        if previous is not None:
            for i, launch in enumerate(self._launches):
                if launch["id"] == previous["id"]:
                    sel = i
                    break
        self.list_launches.SetSelection(sel if 0 <= sel < len(rows) else 0)
        status = []
        if error:
            status.append(text.launch_error_text(error))
        if self._has_data:
            status.append(_("status_updated", time=text.time_of(state["fetched_at"])))
        self.lbl_status.SetLabel(" ".join(status))
        self._show_details()
        self.Layout()

    def _refresh_rows(self):
        """Rewrite rows whose text changed (a reminder was set), keeping the selection."""
        sel = self.list_launches.GetSelection()
        for i, launch in enumerate(self._launches):
            row = self._row(launch)
            if i < self.list_launches.GetCount() and self.list_launches.GetString(i) != row:
                self.list_launches.SetString(i, row)
        if sel != wx.NOT_FOUND and self.list_launches.GetSelection() != sel:
            self.list_launches.SetSelection(sel)

    def _details_text(self, launch):
        lead = self._lead_minutes() if self._has_reminder(launch["id"]) else None
        return text.launch_details(launch, self._tz, self._now(), lead)

    def _show_details(self):
        launch = self.selected_launch()
        self.txt_details.ChangeValue(self._details_text(launch) if launch else "")
        reminded = launch is not None and self._has_reminder(launch["id"])
        self.btn_remind.SetLabel(_("btn_unremind") if reminded else _("btn_remind"))
        self.btn_remind.Enable(launch is not None)

    # --- events -----------------------------------------------------------

    def _on_select(self, event):
        self._show_details()   # state only; focus stays on the list
        event.Skip()

    def _on_char_hook(self, event):
        if (event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
                and wx.Window.FindFocus() is self.list_launches):
            self._on_details()
            return
        event.Skip()

    def _on_details(self, event=None):
        launch = self.selected_launch()
        if launch is None:
            sel = self.list_launches.GetSelection()
            if sel != wx.NOT_FOUND:
                speak(self.list_launches.GetString(sel), interrupt=True)
            return
        speak(self._details_text(launch), interrupt=True)

    def _on_remind(self, event=None):
        launch = self.selected_launch()
        if launch is None:
            return
        speak(self._toggle_reminder(launch), interrupt=True)
        self._refresh_rows()
        self._show_details()

    def _on_refresh(self, event=None):
        status, message = self._request_refresh(self._on_refreshed, True)
        if status == "started":
            self._announce = True
            self.lbl_status.SetLabel(_("status_refreshing"))
            speak(_("status_refreshing"), interrupt=True)
        elif message:
            speak(message, interrupt=True)

    def _on_refreshed(self, error):
        if not self:
            return  # closed while the fetch was running
        had_data = self._has_data
        self._loading = False
        self._fill(error)
        if self._announce or not had_data:
            speak(text.launch_error_text(error) if error else _("launches_updated"), interrupt=True)
        self._announce = False
