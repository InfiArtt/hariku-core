# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import logging
import core.preferences
import core.ui_scale
from ui.input_gestures_panel import InputGesturesPanel
from core.i18n import get_translator

_ = get_translator("core")

logger = logging.getLogger(__name__)

class PreferencesDialog(wx.Dialog):
    def __init__(self, parent, select_tab=None):
        super().__init__(parent, title=_("dlg_prefs_title"), size=(800, 500))
        
        self.panels = []
        self.select_tab = select_tab
        self.InitUI()
        self.CentreOnParent()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # We use a Treebook to have a left-side navigation
        self.treebook = wx.Treebook(self, style=wx.BK_DEFAULT)
        
        # Note: General Settings is now injected automatically from core.core_panels
        
        # 2. Core Settings (Input Gestures)
        input_panel = InputGesturesPanel(self.treebook)
        self.treebook.AddPage(input_panel, _("prefs_tab_input"))
        self.panels.append({"panel": input_panel, "apply": input_panel.ApplyChanges})
        
        # 2. Extension Settings
        registered = core.preferences.get_all_panels()
        for category, items in registered.items():
            for item in items:
                try:
                    panel_instance = item["create"](self.treebook)
                    page_title = item['name'] if item['name'] else category
                    self.treebook.AddPage(panel_instance, page_title)
                    self.panels.append({"panel": panel_instance, "apply": item["apply"]})
                except Exception as e:
                    logger.error(f"Failed to create settings panel '{item['name']}': {e}")
                
        vbox.Add(self.treebook, 1, wx.EXPAND | wx.ALL, 10)
        
        if self.select_tab:
            for i in range(self.treebook.GetPageCount()):
                if self.select_tab.lower() in self.treebook.GetPageText(i).lower():
                    self.treebook.SetSelection(i)
                    break
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_ok = wx.Button(self, id=wx.ID_OK, label=_("prefs_btn_ok", default="OK"))
        self.btn_apply = wx.Button(self, id=wx.ID_APPLY, label=_("prefs_btn_apply", default="Apply"))
        self.btn_cancel = wx.Button(self, id=wx.ID_CANCEL, label=_("prefs_btn_cancel", default="Cancel"))
        
        hbox.AddStretchSpacer()
        hbox.Add(self.btn_ok, 0, wx.RIGHT, 10)
        hbox.Add(self.btn_cancel, 0, wx.RIGHT, 10)
        hbox.Add(self.btn_apply, 0)
        
        vbox.Add(hbox, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(vbox)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        # Large text and high contrast for every page, including extension panels.
        core.ui_scale.apply_appearance(self)

        self.Bind(wx.EVT_BUTTON, self.OnOK, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self.OnApply, id=wx.ID_APPLY)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnCharHook)
        
        # Track dirty state
        self.is_dirty = False
        self.Bind(wx.EVT_TEXT, self.MarkDirty)
        self.Bind(wx.EVT_CHECKBOX, self.MarkDirty)
        self.Bind(wx.EVT_RADIOBUTTON, self.MarkDirty)
        self.Bind(wx.EVT_COMBOBOX, self.MarkDirty)
        self.Bind(wx.EVT_CHOICE, self.MarkDirty)
        
        # Reset dirty state after initial panel population triggers
        wx.CallAfter(self.ResetDirty)
        
    def MarkDirty(self, event):
        self.is_dirty = True
        event.Skip()
        
    def ResetDirty(self):
        self.is_dirty = False
        
    def OnCharHook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close() # Triggers OnClose (shows prompt if dirty)
        else:
            event.Skip()
            
    def _validate(self):
        """A page with ValidateChanges() returning (message, control) keeps the
        dialog open: its page is shown, the message said, and focus put on the
        control to fix. Nothing is saved."""
        for index, p in enumerate(self.panels):
            check = getattr(p["panel"], "ValidateChanges", None)
            if check is None:
                continue
            try:
                problem = check()
            except Exception as e:
                logger.error(f"Error validating preferences: {e}")
                continue
            if problem:
                message, ctrl = problem
                self.treebook.SetSelection(index)
                wx.MessageBox(message, _("error"), wx.OK | wx.ICON_ERROR, self)
                ctrl.SetFocus()
                return False
        return True

    def OnApply(self, event):
        if not self._validate():
            return False
        for p in self.panels:
            if p["apply"]:
                try:
                    p["apply"]()
                except Exception as e:
                    logger.error(f"Error applying preferences: {e}")
        # A changed text size or contrast setting shows here immediately too.
        core.ui_scale.apply_appearance(self)
        self.Layout()
        self.is_dirty = False
        # Do not close window
        return True

    def OnOK(self, event):
        if self.OnApply(None) is False:
            return   # a page refused its input; the dialog stays open on it
        self.EndModal(wx.ID_OK)
        
    def OnCancel(self, event):
        # Cancel explicitly clicked -> No prompt
        self.EndModal(wx.ID_CANCEL)

    def OnClose(self, event):
        if self.is_dirty:
            dlg = wx.MessageDialog(self, _("dlg_unsaved_msg", default="You have unsaved settings. Do you want to save them before exiting?"), 
                                   _("dlg_unsaved_title", default="Unsaved Settings"), 
                                   wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
            res = dlg.ShowModal()
            if res == wx.ID_YES:
                self.OnOK(None)
            elif res == wx.ID_NO:
                self.EndModal(wx.ID_CANCEL)
            else:
                if event.CanVeto():
                    event.Veto()
                return
        else:
            self.EndModal(wx.ID_CANCEL)
