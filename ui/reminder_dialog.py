# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import core.reminders
import datetime
from core.i18n import get_translator

_ = get_translator("core")

class AddReminderDialog(wx.Dialog):
    def __init__(self, parent, date_str):
        super().__init__(parent, title=_("dlg_reminder_title"), size=(400, 320))
        self.date_str = date_str
        self.InitUI()
        self.CentreOnParent()
        import core.ui_scale
        core.ui_scale.apply_appearance(self)
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl_date = wx.StaticText(self, label=_("rem_lbl_date", date=self.date_str))
        lbl_date.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(lbl_date, 0, wx.ALL, 10)
        
        vbox.Add(wx.StaticText(self, label=_("rem_lbl_title")), 0, wx.LEFT | wx.RIGHT, 10)
        self.txt_title = wx.TextCtrl(self)
        vbox.Add(self.txt_title, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        vbox.Add(wx.StaticText(self, label=_("rem_lbl_time")), 0, wx.LEFT | wx.RIGHT, 10)
        
        # Default time is current time + 1 min
        now = datetime.datetime.now()
        default_time = (now + datetime.timedelta(minutes=1)).strftime("%H:%M")
        
        self.txt_time = wx.TextCtrl(self, value=default_time)
        vbox.Add(self.txt_time, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        vbox.Add(wx.StaticText(self, label=_("rem_lbl_repeat")), 0, wx.LEFT | wx.RIGHT, 10)
        self._recur_values = ["none", "daily", "weekly", "monthly", "yearly"]
        recur_labels = [
            _("rem_repeat_none"), _("rem_repeat_daily"), _("rem_repeat_weekly"),
            _("rem_repeat_monthly"), _("rem_repeat_yearly"),
        ]
        self.choice_recur = wx.Choice(self, choices=recur_labels)
        self.choice_recur.SetSelection(0)
        vbox.Add(self.choice_recur, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        hbox = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, label=_("rem_btn_save"))
        btn_ok.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("rem_btn_cancel"))
        hbox.AddButton(btn_ok)
        hbox.AddButton(btn_cancel)
        hbox.Realize()
        
        vbox.Add(hbox, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        self.SetSizer(vbox)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        
        btn_ok.Bind(wx.EVT_BUTTON, self.OnSave)
        
    def OnSave(self, event):
        title = self.txt_title.GetValue().strip()
        time_str = self.txt_time.GetValue().strip()
        
        if not title:
            wx.MessageBox(_("rem_msg_empty_title"), _("error"), wx.ICON_ERROR)
            return
            
        try:
            datetime.datetime.strptime(time_str, "%H:%M")
        except ValueError:
            wx.MessageBox(_("rem_msg_invalid_time"), _("error"), wx.ICON_ERROR)
            return
            
        sel = self.choice_recur.GetSelection()
        recurrence = self._recur_values[sel] if sel >= 0 else "none"
        core.reminders.add_reminder(title, self.date_str, time_str, recurrence=recurrence)
        from core.speech import speak
        speak(_("rem_msg_saved"))
        self.EndModal(wx.ID_OK)
