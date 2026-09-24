# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The reminder dialog (Enter on a date, or Edit in the quick reminder): title,
date, time, repeat and how often. At the top, "Or type it in one sentence"
with Fill in reads a sentence with core.when and fills the fields, saying what
it understood.

Every label is created right before the control it names: screen readers
name a control after the static text just before it, and SetName() doesn't
change that. Focus only moves when the dialog opens, and to a field the user
has to correct after Save.
"""

import datetime

import wx

import core.quick_reminder as quick
import core.reminders
import core.ui_scale
from core.core_panels import _labeled, _labeled_row
from core.i18n import apply_rtl_layout, get_translator
from core.speech import speak

_ = get_translator("core")

REPEATS = quick.REPEATS


class AddReminderDialog(wx.Dialog):
    """`date_str` ("YYYY-MM-DD") is the date the dialog starts with.
    `prefill` is (title, date, time, recurrence, interval); anything None or
    empty keeps the dialog's default."""

    def __init__(self, parent, date_str, prefill=None, say=None):
        super().__init__(parent, title=_("dlg_reminder_title"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.date_str = date_str
        self._say = say or (lambda text: speak(text, interrupt=True))
        self._interval_max = quick.MAX_INTERVAL
        self.InitUI()
        if prefill:
            self.apply_prefill(prefill)
        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.CentreOnParent()
        # The title first, as always; the sentence field is above it (Shift+Tab).
        self.txt_title.SetFocus()

    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Optional: the whole reminder in one sentence, then Fill in.
        self.txt_sentence = _labeled(self, vbox, _("rem_lbl_sentence"),
                                     lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER,
                                                         size=(420, -1)))
        self.btn_fill = wx.Button(self, label=_("rem_btn_fill"))
        vbox.Add(self.btn_fill, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.txt_title = _labeled(self, vbox, _("rem_lbl_title"), lambda: wx.TextCtrl(self))
        self.txt_date = _labeled(self, vbox, _("rem_lbl_date_field"),
                                 lambda: wx.TextCtrl(self, value=self.date_str or ""))
        # Default time is current time + 1 min
        default_time = (quick._now() + datetime.timedelta(minutes=1)).strftime("%H:%M")
        self.txt_time = _labeled(self, vbox, _("rem_lbl_time"),
                                 lambda: wx.TextCtrl(self, value=default_time))

        row = wx.BoxSizer(wx.HORIZONTAL)
        recur_labels = [
            _("rem_repeat_none"), _("rem_repeat_daily"), _("rem_repeat_weekly"),
            _("rem_repeat_monthly"), _("rem_repeat_yearly"),
        ]
        self.choice_recur = _labeled_row(self, row, _("rem_lbl_repeat"),
                                         lambda: wx.Choice(self, choices=recur_labels))
        self.choice_recur.SetSelection(0)
        self.choice_interval = _labeled_row(
            self, row, _("rem_lbl_interval"),
            lambda: wx.Choice(self, choices=quick.interval_choices("daily", self._interval_max)))
        self.choice_interval.SetSelection(0)
        vbox.Add(row, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        hbox = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(self, wx.ID_OK, label=_("rem_btn_save"))
        self.btn_ok.SetDefault()
        self.btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("rem_btn_cancel"))
        hbox.AddButton(self.btn_ok)
        hbox.AddButton(self.btn_cancel)
        hbox.Realize()
        vbox.Add(hbox, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        self.SetSizer(vbox)
        self.SetEscapeId(wx.ID_CANCEL)

        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnSave)
        self.btn_fill.Bind(wx.EVT_BUTTON, self.OnFill)
        self.txt_sentence.Bind(wx.EVT_TEXT_ENTER, self.OnFill)
        self.choice_recur.Bind(wx.EVT_CHOICE, self._on_repeat_changed)
        self._update_interval()

    # --- values -------------------------------------------------------------

    def recurrence(self):
        sel = self.choice_recur.GetSelection()
        return REPEATS[sel] if 0 <= sel < len(REPEATS) else "none"

    def interval(self):
        if self.recurrence() == "none":
            return 1
        return max(1, self.choice_interval.GetSelection() + 1)

    def _update_interval(self, keep=None):
        """Word "How often" for the chosen repeat ("every 2 weeks"), keeping
        the number; it is only there to Tab to when the reminder repeats."""
        recurrence = self.recurrence()
        index = (keep if keep is not None else self.choice_interval.GetSelection() + 1) - 1
        self.choice_interval.Set(quick.interval_choices(
            recurrence if recurrence != "none" else "daily", self._interval_max))
        self.choice_interval.SetSelection(max(0, min(index, self._interval_max - 1)))
        self.choice_interval.Enable(recurrence != "none")

    def _on_repeat_changed(self, event):
        # Only the other field changes; focus stays on Repeat.
        self._update_interval()
        event.Skip()

    def set_values(self, title=None, date=None, time=None, recurrence=None, interval=None):
        """Fill in the fields; None leaves one as it is."""
        if title:
            self.txt_title.SetValue(title)
        if date:
            self.txt_date.SetValue(date)
        if time:
            self.txt_time.SetValue(time)
        if recurrence in REPEATS:
            self.choice_recur.SetSelection(REPEATS.index(recurrence))
        keep = None
        if interval:
            keep = max(1, int(interval))
            self._interval_max = max(self._interval_max, keep)
        self._update_interval(keep)

    def apply_prefill(self, prefill):
        title, date_str, time_str, recurrence, interval = (tuple(prefill) + (None,) * 5)[:5]
        self.set_values(title=title, date=date_str, time=time_str, recurrence=recurrence,
                        interval=interval)

    # --- Fill in ------------------------------------------------------------

    def OnFill(self, event=None):
        """Read the sentence, fill in the fields and say what was understood.
        Focus stays where it is (the button, or the sentence field on Enter)."""
        text = self.txt_sentence.GetValue().strip()
        if not text:
            self._say(_("rem_msg_empty_sentence"))
            return None
        # A sentence without a date keeps the date this dialog is set to.
        result = quick.parse_text(text, default_date=self.txt_date.GetValue())
        values = quick.fill_values(result)
        if values:
            self.set_values(**values)
        self._say(quick.fill_readback(result))
        return result

    # --- Save ---------------------------------------------------------------

    def _refuse(self, message, ctrl):
        wx.MessageBox(message, _("error"), wx.OK | wx.ICON_ERROR, self)
        ctrl.SetFocus()
        ctrl.SelectAll()

    def OnSave(self, event):
        title = self.txt_title.GetValue().strip()
        if not title:
            self._refuse(_("rem_msg_empty_title"), self.txt_title)
            return
        date_str = core.reminders.parse_date_text(self.txt_date.GetValue())
        if not date_str:
            self._refuse(_("rem_msg_invalid_date"), self.txt_date)
            return
        time_str = core.reminders.parse_time_text(self.txt_time.GetValue())
        if not time_str:
            self._refuse(_("rem_msg_invalid_time"), self.txt_time)
            return
        core.reminders.add_reminder(title, date_str, time_str, recurrence=self.recurrence(),
                                    interval=self.interval())
        speak(_("rem_msg_saved"))
        self.EndModal(wx.ID_OK)
