# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for the Cockpit extension:
  * CockpitPanel         - the Preferences page: Captain mode and the sound
                           theme, the favourite airports, the place for the
                           nearest airport, reading options, notes.
  * AirportWeatherDialog - the airports (one sentence each), the selected
                           one's decoded METAR and TAF, and the raw codes.
  * AddAirportDialog     - asks for an ICAO code.
  * YesNoDialog          - Captain mode's offers (Yes is the default button).

Every label is created right before the control it names (screen readers name
a control after the static text created just before it). Selecting in a list
never moves focus; focus only moves when a dialog opens.
"""

import wx

import core.ui_scale
from core.i18n import apply_rtl_layout
from core.places_ui import PlaceChoice
from core.speech import speak

import cockpit_api as api
import cockpit_metar as metar
import cockpit_text as text
from cockpit_text import _


ANNOUNCE_DELAY_MS = 300   # after a dialog closes, so the focus announcement doesn't cut it off
_BORDER = 10


def _plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def _labeled(parent, sizer, label, make, proportion=0):
    """A label, then the control it names, with the same accessible name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return ctrl


def _note(parent, sizer, label, width=520):
    static = wx.StaticText(parent, label=label)
    static.Wrap(width)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    return static


def _announce(message):
    wx.CallLater(ANNOUNCE_DELAY_MS, speak, message, True)


def _appearance(window):
    try:
        core.ui_scale.apply_appearance(window)
    except Exception:
        pass


def add_result_message(airport, problem, has_report, code):
    """What to say after trying to add airport `code`."""
    spelled = text.spell(metar.normalize_icao(code) or code)
    if problem is None:
        name = text.names(airport)[0]
        return _("added" if has_report else "added_no_report", name=name,
                 code=text.spell(airport["icao"]))
    if problem == "not_icao":
        return _("err_not_icao")
    if problem == "already":
        return _("err_already", name=text.names(airport)[0])
    if problem == "too_many":
        return _("err_too_many", count=api.MAX_FAVOURITES)
    if problem == "unknown":
        return _("err_unknown_airport", code=spelled)
    return text.error_text(problem)


# ------------------------------------------------------------
# Small dialogs
# ------------------------------------------------------------

class YesNoDialog(wx.Dialog):
    """A question with Yes (the default, also Enter) and No (also Escape)."""

    def __init__(self, parent, title, message):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE)
        root = wx.BoxSizer(wx.VERTICAL)
        self.lbl_message = wx.StaticText(self, label=message)
        self.lbl_message.Wrap(460)
        root.Add(self.lbl_message, 0, wx.ALL, _BORDER)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_yes = wx.Button(self, wx.ID_YES, _("btn_yes"))
        self.btn_no = wx.Button(self, wx.ID_NO, _("btn_no"))
        buttons.Add(self.btn_yes, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_no, 0)
        root.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.btn_yes.SetDefault()
        self.SetAffirmativeId(wx.ID_YES)
        self.SetEscapeId(wx.ID_NO)
        for btn in (self.btn_yes, self.btn_no):
            btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(e.GetId()))
        apply_rtl_layout(self)
        _appearance(self)
        self.Fit()
        self.CentreOnParent()
        self.btn_yes.SetFocus()


def ask_yes_no(parent, title, message):
    dlg = YesNoDialog(parent, title, message)
    try:
        return dlg.ShowModal() == wx.ID_YES
    finally:
        dlg.Destroy()


class AddAirportDialog(wx.Dialog):
    """Asks for an ICAO code; OK (Enter) and Cancel (Escape)."""

    def __init__(self, parent):
        super().__init__(parent, title=_("add_title"), style=wx.DEFAULT_DIALOG_STYLE)
        root = wx.BoxSizer(wx.VERTICAL)
        self.txt_code = _labeled(self, root, _("lbl_icao"), lambda: wx.TextCtrl(self))
        self.txt_code.SetMaxLength(4)
        buttons = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(self, wx.ID_OK, _("btn_ok"))
        self.btn_ok.SetDefault()
        buttons.AddButton(self.btn_ok)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL, _("btn_cancel")))
        buttons.Realize()
        root.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.SetEscapeId(wx.ID_CANCEL)
        apply_rtl_layout(self)
        _appearance(self)
        self.Fit()
        self.SetSize((max(self.GetSize().width, 440), self.GetSize().height))
        self.CentreOnParent()
        self.txt_code.SetFocus()


def ask_icao(parent):
    """The code typed, or None if cancelled (replaced in checks)."""
    dlg = AddAirportDialog(parent)
    try:
        return dlg.txt_code.GetValue() if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()


# ------------------------------------------------------------
# Preferences page
# ------------------------------------------------------------

# The page can be taller than Preferences with large text, so it scrolls. A
# plain panel where wx is not the real one (the unit tests).
_PageBase = wx.ScrolledWindow if isinstance(getattr(wx, "ScrolledWindow", None), type) else wx.Panel


class CockpitPanel(_PageBase):
    """Captain mode and the reading options are saved on OK; the favourite
    airports and the sound theme act at once (their buttons say what they do)."""

    def __init__(self, parent, settings, actions, install_theme):
        super().__init__(parent)
        self._actions = actions
        self._install_theme = install_theme
        self._rows = []           # the airport dict behind each row
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.chk_captain = wx.CheckBox(self, label=_("chk_captain"))
        self.chk_captain.SetValue(bool(settings.get("captain")))
        vbox.Add(self.chk_captain, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        self.btn_sound_theme = wx.Button(self, label=_("btn_sound_theme"))
        vbox.Add(self.btn_sound_theme, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        _note(self, vbox, _("note_captain"))

        self.list_airports = _labeled(self, vbox, _("lbl_favourites"),
                                      lambda: wx.ListBox(self, size=(-1, 110), style=wx.LB_SINGLE))
        label = _("lbl_add_code")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_code = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.txt_code.SetName(_plain(label))
        self.txt_code.SetMaxLength(4)
        row.Add(self.txt_code, 1, wx.RIGHT, 6)
        self.btn_add = wx.Button(self, label=_("btn_add_code"))
        row.Add(self.btn_add, 0)
        vbox.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_remove = wx.Button(self, label=_("btn_remove"))
        self.btn_default = wx.Button(self, label=_("btn_default"))
        buttons.Add(self.btn_remove, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_default, 0)
        vbox.Add(buttons, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)

        # Without favourites, the nearest airport to this place (core 2.8).
        # Cockpit has no place of its own: its airports are.
        self.place_choice = PlaceChoice(self, vbox, settings.get("place"), own=False,
                                        label=_("lbl_place"), border=_BORDER)

        self.chk_raw = wx.CheckBox(self, label=_("chk_raw"))
        self.chk_raw.SetValue(bool(settings.get("raw")))
        vbox.Add(self.chk_raw, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        self.chk_briefing = wx.CheckBox(self, label=_("chk_briefing"))
        self.chk_briefing.SetValue(bool(settings.get("briefing")))
        vbox.Add(self.chk_briefing, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)

        for note in (_("attribution"), _("disclaimer"), _("note_privacy")):
            _note(self, vbox, note)
        vbox.AddSpacer(_BORDER)
        self.SetSizer(vbox)

        self.btn_sound_theme.Bind(wx.EVT_BUTTON, self.on_sound_theme)
        self.txt_code.Bind(wx.EVT_TEXT_ENTER, self.on_add)
        self.btn_add.Bind(wx.EVT_BUTTON, self.on_add)
        self.btn_remove.Bind(wx.EVT_BUTTON, self.on_remove)
        self.btn_default.Bind(wx.EVT_BUTTON, self.on_make_default)
        self.refresh()
        if hasattr(self, "SetScrollRate"):
            self.SetScrollRate(0, 20)
            _appearance(self)
            self.FitInside()   # after scaling, so large text can still be scrolled to

    # -- data -> controls ---------------------------------------------------- #
    def _row_text(self, airport, index):
        full, _short = text.names(airport)
        if airport.get("auto"):
            return _("row_nearest_only", name=f"{full}, {text.spell(airport['icao'])}",
                     city=airport.get("city", ""))
        row = f"{full}, {text.spell(airport['icao'])}"
        return row + _("row_default") if index == 0 else row

    def refresh(self, select_icao=None):
        previous = self.list_airports.GetSelection()
        self._rows = self._actions.airports()
        rows = [self._row_text(a, i) for i, a in enumerate(self._rows)]
        self.list_airports.Set(rows or [_("list_empty")])
        index = next((i for i, a in enumerate(self._rows) if a["icao"] == select_icao), None)
        if index is None:
            index = previous if 0 <= previous < len(rows) else 0
        self.list_airports.SetSelection(index)

    def selected_airport(self):
        index = self.list_airports.GetSelection()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def get_settings(self):
        return {"captain": self.chk_captain.GetValue(), "raw": self.chk_raw.GetValue(),
                "briefing": self.chk_briefing.GetValue(), "place": self.place_choice.key()}

    def refresh_places(self):
        """The places changed (Preferences, Places): list them again."""
        self.place_choice.refresh()

    # -- actions ------------------------------------------------------------- #
    def on_add(self, event=None):
        code = self.txt_code.GetValue().strip()
        icao = metar.normalize_icao(code)
        if not icao:
            speak(_("err_not_icao"), interrupt=True)
            return
        speak(_("checking", code=text.spell(icao)), interrupt=True)
        self._actions.add(icao, lambda airport, problem, has_report:
                          self._on_added(icao, airport, problem, has_report))

    def _on_added(self, code, airport, problem, has_report):
        if not self:
            return   # Preferences closed while checking
        if problem is None:
            self.txt_code.ChangeValue("")
            self.refresh(select_icao=airport["icao"])
        speak(add_result_message(airport, problem, has_report, code), interrupt=True)

    def on_remove(self, event=None):
        airport = self.selected_airport()
        if airport is None:
            speak(_("nothing_selected"), interrupt=True)
        elif airport.get("auto"):
            speak(_("auto_not_removable", city=airport.get("city", "")), interrupt=True)
        elif self._actions.remove(airport["icao"]):
            self.refresh()
            speak(_("removed", name=text.names(airport)[0]), interrupt=True)

    def on_make_default(self, event=None):
        airport = self.selected_airport()
        if airport is None:
            speak(_("nothing_selected"), interrupt=True)
            return
        name = text.names(airport)[0]
        if self._actions.make_default(airport["icao"]):
            self.refresh(select_icao=airport["icao"])
            speak(_("made_default", name=name), interrupt=True)
        else:
            speak(_("already_default", name=name), interrupt=True)

    def on_sound_theme(self, event=None):
        if self._install_theme(self._on_theme_done):
            speak(_("theme_installing"), interrupt=True)

    def _on_theme_done(self, message):
        speak(message, interrupt=True)


# ------------------------------------------------------------
# The Airport weather window
# ------------------------------------------------------------

class AirportWeatherDialog(wx.Dialog):
    """`actions` is main.WindowActions: airports(), metar(icao), taf(icao),
    refresh(callback), add(code, callback), remove(icao), make_default(icao)..."""

    def __init__(self, parent, actions):
        super().__init__(parent, title=_("dlg_title"), size=(720, 580),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._actions = actions
        self._rows = []
        self._announce_refresh = False
        vbox = wx.BoxSizer(wx.VERTICAL)

        # One sentence per airport, so each arrow press reads a whole one.
        self.list_airports = _labeled(self, vbox, _("lbl_airports"),
                                      lambda: wx.ListBox(self, style=wx.LB_SINGLE), proportion=2)
        self.txt_report = _labeled(self, vbox, _("lbl_report"), lambda: wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY), proportion=4)
        self.txt_raw = _labeled(self, vbox, _("lbl_raw"), lambda: wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY), proportion=1)
        self.lbl_status = wx.StaticText(self, label="")
        vbox.Add(self.lbl_status, 0, wx.ALL | wx.EXPAND, _BORDER)

        buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_refresh = wx.Button(self, label=_("btn_refresh"))
        self.btn_add = wx.Button(self, label=_("btn_add"))
        self.btn_remove = wx.Button(self, label=_("btn_remove"))
        self.btn_default = wx.Button(self, label=_("btn_default"))
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label=_("btn_close"))
        for btn in (self.btn_refresh, self.btn_add, self.btn_remove, self.btn_default,
                    self.btn_close):
            buttons.Add(btn, 0, wx.RIGHT | wx.BOTTOM, 6)
        vbox.Add(buttons, 0, wx.LEFT | wx.RIGHT, _BORDER)
        self.SetSizer(vbox)
        self.btn_close.SetDefault()
        self.SetEscapeId(wx.ID_CANCEL)

        self.list_airports.Bind(wx.EVT_LISTBOX, self._on_selected)
        self.btn_refresh.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.btn_add.Bind(wx.EVT_BUTTON, self.on_add)
        self.btn_remove.Bind(wx.EVT_BUTTON, self.on_remove)
        self.btn_default.Bind(wx.EVT_BUTTON, self.on_make_default)

        apply_rtl_layout(self)
        _appearance(self)
        loading = self._actions.refresh(self._on_refreshed)
        self.fill()
        if loading:
            self.lbl_status.SetLabel(_("status_refreshing"))
        self.CentreOnParent()
        self.list_airports.SetFocus()

    # -- data -> controls ---------------------------------------------------- #
    def fill(self, select_icao=None, error=None):
        previous = self.list_airports.GetSelection()
        self._rows = self._actions.airports()
        default = self._actions.default_icao()
        captain = self._actions.captain()
        loading = self._actions.loading()
        rows = [text.airport_row(a, self._actions.metar(a["icao"]), a["icao"] == default,
                                 loading and not self._actions.no_metar(a["icao"]), captain)
                for a in self._rows]
        self.list_airports.Set(rows or [_("list_empty")])
        index = next((i for i, a in enumerate(self._rows) if a["icao"] == select_icao), None)
        if index is None:
            index = previous if 0 <= previous < len(rows) else 0
        self.list_airports.SetSelection(index)
        self._show_selected()
        status = [text.error_text(error)] if error else []
        times = [e["fetched_at"] for e in (self._actions.metar(a["icao"]) for a in self._rows) if e]
        if times:
            status.append(_("status_updated", time=text.time_text(max(times))))
        self.lbl_status.SetLabel(" ".join(status))
        self.Layout()

    def selected_airport(self):
        index = self.list_airports.GetSelection()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def _show_selected(self):
        airport = self.selected_airport()
        if airport is None:
            self.txt_report.ChangeValue("")
            self.txt_raw.ChangeValue("")
            return
        captain = self._actions.captain()
        loading = self._actions.loading()
        entry = self._actions.metar(airport["icao"])
        taf = self._actions.taf(airport["icao"])
        lines, raw = [], []
        if entry:
            lines += text.metar_lines(airport, entry["report"], captain)
            raw.append(entry["report"]["raw"])
        else:
            name = text.names(airport)[0]
            lines.append(_("report_loading") if loading and not self._actions.no_metar(
                airport["icao"]) else _("no_report", name=name))
        lines.append("")
        if taf:
            lines += text.taf_lines(taf["report"], captain)
            raw.append(taf["report"]["raw"])
        elif not loading:
            lines.append(_("taf_none"))
        self.txt_report.ChangeValue("\n".join(lines).strip())
        self.txt_raw.ChangeValue("\n".join(raw))

    def _on_selected(self, event):
        self._show_selected()     # the fields only; focus stays on the list
        event.Skip()

    # -- actions ------------------------------------------------------------- #
    def _on_refreshed(self, error):
        if not self:
            return   # closed while fetching
        had_rows = bool(self._rows)
        self.fill(error=error)
        if self._announce_refresh or not had_rows:
            speak(text.error_text(error) if error else _("refreshed"), interrupt=True)
        self._announce_refresh = False

    def on_refresh(self, event=None):
        if self._actions.refresh(self._on_refreshed):
            self._announce_refresh = True
            self.lbl_status.SetLabel(_("status_refreshing"))
            speak(_("status_refreshing"), interrupt=True)
        else:
            speak(_("up_to_date"), interrupt=True)

    def on_add(self, event=None):
        code = ask_icao(self)
        if code is None:
            return
        icao = metar.normalize_icao(code)
        if not icao:
            _announce(_("err_not_icao"))
            return
        _announce(_("checking", code=text.spell(icao)))
        self._actions.add(icao, lambda airport, problem, has_report:
                          self._on_added(icao, airport, problem, has_report))

    def _on_added(self, code, airport, problem, has_report):
        if not self:
            return
        if problem is None:
            self.fill(select_icao=airport["icao"])
            self._actions.refresh(self._on_refreshed)   # its TAF
        speak(add_result_message(airport, problem, has_report, code), interrupt=True)

    def on_remove(self, event=None):
        airport = self.selected_airport()
        if airport is None:
            speak(_("nothing_selected"), interrupt=True)
        elif airport.get("auto"):
            speak(_("auto_not_removable", city=airport.get("city", "")), interrupt=True)
        elif self._actions.remove(airport["icao"]):
            self.fill()
            speak(_("removed", name=text.names(airport)[0]), interrupt=True)

    def on_make_default(self, event=None):
        airport = self.selected_airport()
        if airport is None:
            speak(_("nothing_selected"), interrupt=True)
            return
        name = text.names(airport)[0]
        if self._actions.make_default(airport["icao"]):
            self.fill(select_icao=airport["icao"])
            speak(_("made_default", name=name), interrupt=True)
        else:
            speak(_("already_default", name=name), interrupt=True)
