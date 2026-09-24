# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for Sleep Pattern:
  * SettingsPanel - the Preferences page.
  * HistoryDialog - a summary, one row per night (newest first), and Details,
                    This wasn't sleep (Undo on a marked night), Clear all
                    history and Close.
  * DetailsDialog - everything known about one night, read-only.
Every control has a StaticText label right before it and the same accessible
name. Selection changes never move keyboard focus (they fire on every arrow
press); focus only moves after an explicit action.
"""

import wx

import core.ui_scale
from core.i18n import apply_rtl_layout
from core.speech import speak

import sleep_tracker_store as store
import sleep_tracker_text as text
from sleep_tracker_text import _

_BORDER = 8
ANNOUNCE_DELAY_MS = 300      # speak after the screen reader's focus announcement


def _plain(label):
    return label.replace("&", "").strip().rstrip(":").strip()


def _labeled(parent, sizer, label, make, proportion=0):
    """A label, then the control it names, which gets the same accessible name."""
    static = wx.StaticText(parent, label=label)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return static, ctrl


def _check(parent, sizer, label, value):
    ctrl = wx.CheckBox(parent, label=label)
    ctrl.SetName(_plain(label))
    ctrl.SetValue(bool(value))
    sizer.Add(ctrl, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    return ctrl


def _button(parent, sizer, label, handler, button_id=wx.ID_ANY):
    btn = wx.Button(parent, button_id, label)
    if handler:
        btn.Bind(wx.EVT_BUTTON, handler)
    sizer.Add(btn, 0, wx.RIGHT | wx.TOP, 4)
    return btn


def _confirm(parent, message, title):
    style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING
    return wx.MessageBox(message, title, style, parent) == wx.YES


def announce(message, delay=ANNOUNCE_DELAY_MS):
    """Speak a moment later, so a focus change does not cut the message off."""
    wx.CallLater(delay, speak, message)


def _select(choice, values, value):
    choice.SetSelection(values.index(value) if value in values else 0)


def _selected(choice, values, default):
    index = choice.GetSelection()
    return values[index] if 0 <= index < len(values) else default


# The page can be taller than the Preferences dialog with large text, so it
# scrolls. A plain panel where wx is not the real one (the tests).
_PageBase = wx.ScrolledWindow if isinstance(getattr(wx, "ScrolledWindow", None), type) else wx.Panel


class SettingsPanel(_PageBase):
    """`clear_history()` deletes the recorded history (after a confirmation here)."""

    def __init__(self, parent, settings, clear_history):
        super().__init__(parent)
        self._clear_history = clear_history
        root = wx.BoxSizer(wx.VERTICAL)

        self.chk_enabled = _check(self, root, _("chk_enabled"), settings["enabled"])
        self.choice_bedtime = _labeled(self, root, _("lbl_bedtime"), lambda: wx.Choice(
            self, choices=[text.clock(m) for m in store.BEDTIME_CHOICES]))[1]
        _select(self.choice_bedtime, store.BEDTIME_CHOICES, settings["bedtime"])
        self.choice_min_sleep = _labeled(self, root, _("lbl_min_sleep"), lambda: wx.Choice(
            self, choices=[text.duration(m) for m in store.MIN_SLEEP_CHOICES]))[1]
        _select(self.choice_min_sleep, store.MIN_SLEEP_CHOICES, settings["min_sleep"])
        self.choice_ignore = _labeled(self, root, _("lbl_ignore"), lambda: wx.Choice(
            self, choices=[_("ignore_none")] + [_("ignore_up_to", duration=text.duration(m, exact=True))
                                                for m in store.IGNORE_CHOICES[1:]]))[1]
        _select(self.choice_ignore, store.IGNORE_CHOICES, settings["ignore_activity"])

        self.chk_nudge = _check(self, root, _("chk_nudge"), settings["nudge"])
        self.chk_nudge_sound = _check(self, root, _("chk_nudge_sound"), settings["nudge_sound"])

        # A read-only field rather than a StaticText, so Tab reaches it.
        about = "\n\n".join((_("privacy_note"), _("estimate_note"), _("how_note")))
        self.txt_about = _labeled(self, root, _("lbl_about"), lambda: wx.TextCtrl(
            self, value=about, size=(-1, 130), style=wx.TE_MULTILINE | wx.TE_READONLY),
            proportion=1)[1]

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_clear = _button(self, row, _("btn_clear_history"), self._on_clear)
        root.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, _BORDER)

        self.SetSizer(root)
        if hasattr(self, "SetScrollRate"):
            self.SetScrollRate(0, 20)
        core.ui_scale.apply_appearance(self)
        if hasattr(self, "FitInside"):
            self.FitInside()

    def get_settings(self):
        return {
            "enabled": bool(self.chk_enabled.GetValue()),
            "bedtime": _selected(self.choice_bedtime, store.BEDTIME_CHOICES, 0),
            "min_sleep": _selected(self.choice_min_sleep, store.MIN_SLEEP_CHOICES, 180),
            "ignore_activity": _selected(self.choice_ignore, store.IGNORE_CHOICES, 10),
            "nudge": bool(self.chk_nudge.GetValue()),
            "nudge_sound": bool(self.chk_nudge_sound.GetValue()),
        }

    def _on_clear(self, event=None):
        if not _confirm(self, _("confirm_clear"), _("confirm_clear_title")):
            return
        self._clear_history()
        speak(_("cleared"))


class DetailsDialog(wx.Dialog):
    def __init__(self, parent, details):
        super().__init__(parent, title=_("details_title"), size=(560, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        root = wx.BoxSizer(wx.VERTICAL)
        self.txt_details = _labeled(self, root, _("lbl_details"), lambda: wx.TextCtrl(
            self, value=details, style=wx.TE_MULTILINE | wx.TE_READONLY), proportion=1)[1]
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_close = _button(self, buttons, _("btn_close"), None, wx.ID_CANCEL)
        self.btn_close.SetDefault()
        root.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, _BORDER)
        self.SetSizer(root)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.Layout()
        self.CentreOnParent()
        self.txt_details.SetFocus()

    def _on_char_hook(self, event):
        # Enter closes too; the text is read-only, so it has no other use there.
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not event.HasAnyModifiers():
            if self.IsModal():
                self.EndModal(wx.ID_CANCEL)
            else:
                self.Hide()
            return
        event.Skip()


class HistoryDialog(wx.Dialog):
    """`actions` is main.py's HistoryActions: rows() -> [(night, text, mark)]
    where mark is "mark", "undo" or None; summary(); details(night);
    mark(night); undo(night); clear()."""

    def __init__(self, parent, actions):
        super().__init__(parent, title=_("history_title"), size=(720, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._actions = actions
        self._rows = []
        root = wx.BoxSizer(wx.VERTICAL)

        self.txt_summary = _labeled(self, root, _("lbl_summary"), lambda: wx.TextCtrl(
            self, size=(-1, 70), style=wx.TE_MULTILINE | wx.TE_READONLY))[1]
        self.list = _labeled(self, root, _("lbl_nights"), lambda: wx.ListBox(
            self, style=wx.LB_SINGLE), proportion=1)[1]

        buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_details = _button(self, buttons, _("btn_details"), self.on_details)
        self.btn_mark = _button(self, buttons, _("btn_not_sleep"), self.on_mark)
        self.btn_clear = _button(self, buttons, _("btn_clear"), self.on_clear)
        self.btn_close = _button(self, buttons, _("btn_close"), None, wx.ID_CANCEL)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.SetMinSize((480, 400))
        self.SetEscapeId(wx.ID_CANCEL)

        self.list.Bind(wx.EVT_LISTBOX, self._on_select)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_details)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        self.refresh(select_index=0)
        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.Layout()
        self.CentreOnParent()
        self.list.SetFocus()

    # -- data -> controls -------------------------------------------------
    def refresh(self, select_night=None, select_index=None):
        """Rebuild the rows, keeping the selected night selected. Never moves focus."""
        target = select_night or self.selected_night()
        self._rows = list(self._actions.rows())
        self.txt_summary.ChangeValue(self._actions.summary())
        self.list.Set([row[1] for row in self._rows] or [_("empty_rows")])
        nights = [row[0] for row in self._rows]
        index = nights.index(target) if target in nights else (select_index or 0)
        self.list.SetSelection(max(0, min(index, self.list.GetCount() - 1)))
        self._update_mark_button()

    def selected_row(self):
        index = self.list.GetSelection()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def selected_night(self):
        row = self.selected_row()
        return row[0] if row else None

    def _update_mark_button(self):
        row = self.selected_row()
        label = _("btn_undo") if row and row[2] == "undo" else _("btn_not_sleep")
        if self.btn_mark.GetLabel() != label:
            self.btn_mark.SetLabel(label)
            self.Layout()

    # -- events -----------------------------------------------------------
    def _on_select(self, event=None):
        # Fires on every arrow press: update the button only, focus stays put.
        self._update_mark_button()

    def _on_char_hook(self, event):
        if (wx.Window.FindFocus() is self.list and not event.HasAnyModifiers()
                and event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)):
            self.on_details()
            return
        event.Skip()

    def _selected_or_say(self):
        row = self.selected_row()
        if row is None:
            speak(_("nothing_selected"))
        return row

    def on_details(self, event=None):
        row = self._selected_or_say()
        if row is None:
            return
        dlg = DetailsDialog(self, self._actions.details(row[0]))
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        if self:
            self.list.SetFocus()

    def on_mark(self, event=None):
        row = self._selected_or_say()
        if row is None:
            return
        night, _row_text, mark = row
        if mark == "undo":
            done, message = self._actions.undo(night), _("unmarked")
        elif mark == "mark":
            done, message = self._actions.mark(night), _("marked")
        else:
            speak(_("nothing_to_mark"))
            return
        self.refresh(select_night=night)
        speak(message if done else _("nothing_to_mark"))

    def on_clear(self, event=None):
        if not self._rows:
            speak(_("nothing_to_clear"))
            return
        if not _confirm(self, _("confirm_clear"), _("confirm_clear_title")):
            return
        self._actions.clear()
        self.refresh(select_index=0)
        self.list.SetFocus()
        announce(_("cleared"))
