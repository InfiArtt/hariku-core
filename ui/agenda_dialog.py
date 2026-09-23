# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import datetime
from core.speech import speak
from core.sounds import play_internal_sound
from core.i18n import get_translator

_ = get_translator("core")

class AgendaDialog(wx.Dialog):
    def __init__(self, parent, date_str, reminders):
        super().__init__(parent, title=_("dlg_agenda_title", date=date_str), size=(400, 300))
        self.reminders = reminders
        self.date_str = date_str
        
        self.InitUI()
        self.CentreOnParent()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        if not self.reminders:
            text = wx.StaticText(self, label=_("agenda_lbl_no_reminders"))
            font = text.GetFont()
            font.SetPointSize(12)
            text.SetFont(font)
            vbox.Add(text, 1, wx.ALL | wx.ALIGN_CENTER, 20)
            speak(_("agenda_lbl_no_reminders"))
        else:
            label = wx.StaticText(self, label=_("agenda_lbl_has_reminders", count=len(self.reminders)))
            vbox.Add(label, 0, wx.ALL, 10)
            
            self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
            self.list_ctrl.InsertColumn(0, _("agenda_col_time"), width=80)
            self.list_ctrl.InsertColumn(1, _("agenda_col_title"), width=250)
            
            # Sort by time
            self.reminders.sort(key=lambda x: x['time'])
            
            for idx, r in enumerate(self.reminders):
                time_str = r['time']
                title_str = r['title']
                status = _("agenda_status_done") if r.get('is_done') else ""
                
                self.list_ctrl.InsertItem(idx, time_str)
                self.list_ctrl.SetItem(idx, 1, title_str + status)
                
            vbox.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 10)
            
            speak(_("agenda_speak_viewing", date=self.date_str))
            
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_delete = wx.Button(self, label=_("agenda_btn_delete"))
        self.btn_delete.Disable()
        if self.reminders:
            self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self.list_ctrl)
            self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected, self.list_ctrl)
            self.Bind(wx.EVT_BUTTON, self.OnDelete, self.btn_delete)
            self.list_ctrl.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
            hbox.Add(self.btn_delete, 0, wx.RIGHT, 10)
            
        btn_close = wx.Button(self, wx.ID_OK, _("agenda_btn_close"))
        btn_close.SetDefault()
        hbox.Add(btn_close, 0)
        
        vbox.Add(hbox, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        
        self.SetSizer(vbox)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)

    def OnItemSelected(self, event):
        sel = self.list_ctrl.GetFirstSelected()
        if sel != -1:
            rem = self.reminders[sel]
            if rem.get("readonly", False):
                self.btn_delete.Disable()
            else:
                self.btn_delete.Enable()

    def OnItemDeselected(self, event):
        self.btn_delete.Disable()
        
    def OnKeyDown(self, event):
        if event.GetKeyCode() == wx.WXK_DELETE:
            self.OnDelete(None)
        else:
            event.Skip()

    def OnDelete(self, event):
        sel = self.list_ctrl.GetFirstSelected()
        if sel != -1:
            rem = self.reminders[sel]
            if rem.get("readonly", False):
                from core.speech import speak
                speak("This item is managed by an extension and cannot be deleted from here.", interrupt=True)
                return
                
            resp = wx.MessageBox(_("agenda_msg_delete_confirm", title=rem['title']), _("agenda_title_delete"), wx.YES_NO | wx.ICON_QUESTION)
            if resp == wx.YES:
                from core.reminders import delete_reminder
                delete_reminder(rem['id'])
                
                # Remove from the UI
                self.list_ctrl.DeleteItem(sel)
                del self.reminders[sel]
                
                if not self.reminders:
                    self.EndModal(wx.ID_OK)
                else:
                    # Select the previous or first item
                    new_sel = min(sel, len(self.reminders) - 1)
                    if new_sel >= 0:
                        self.list_ctrl.Select(new_sel)

def show_agenda(parent, date_str, reminders):
    play_internal_sound("info.wav")
    dlg = AgendaDialog(parent, date_str, reminders)
    dlg.ShowModal()
    dlg.Destroy()
