# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import os
import core.constants

class AboutDialog(wx.Dialog):
    def __init__(self, parent):
        from core.i18n import get_translator
        self._translator = get_translator("core")
        
        super().__init__(parent, title=self._translator("menu_about"), size=(600, 450), 
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._init_ui()
        self.CentreOnParent()
        
    def _init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.text_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        font = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.text_ctrl.SetFont(font)
        
        self._populate_info()
        
        vbox.Add(self.text_ctrl, 1, wx.EXPAND | wx.ALL, 10)
        
        hbox_docs = wx.BoxSizer(wx.HORIZONTAL)
        
        btn_license = wx.Button(self, label=self._translator("btn_license", default="License"))
        btn_license.Bind(wx.EVT_BUTTON, self._on_license)
        hbox_docs.Add(btn_license, 0, wx.RIGHT, 10)
        
        btn_contrib = wx.Button(self, label=self._translator("btn_contributors", default="Contributors"))
        btn_contrib.Bind(wx.EVT_BUTTON, self._on_contributors)
        hbox_docs.Add(btn_contrib, 0, wx.RIGHT, 10)
        
        btn_close = wx.Button(self, wx.ID_CANCEL, label=self._translator("ext_btn_close", default="Close"))
        hbox_docs.Add(btn_close, 0)
        
        vbox.Add(hbox_docs, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        
        self.SetSizer(vbox)

    def _populate_info(self):
        import sys
        import platform
        import wx
        from core.i18n import get_language_manifest
        
        try:
            import cytolk
            tolk_ver = cytolk.__version__ if hasattr(cytolk, '__version__') else "Available"
        except ImportError:
            tolk_ver = "Not Available"
            
        manifest = get_language_manifest("core") or {}
        lang_name = manifest.get("language_name", "Unknown")
        translator = manifest.get("translator", "Unknown")
        
        arch = "64-bit" if sys.maxsize > 2**32 else "32-bit"
        
        lines = [
            f"Hariku V2",
            f"Version: {core.constants.CORE_VERSION}",
            f"Copyright (c) 2026 Rafli",
            f"",
            f"--- System Information ---",
            f"OS: {platform.platform()} ({arch})",
            f"Python Version: {sys.version.split(' ')[0]}",
            f"wxPython Version: {wx.version()}",
            f"Tolk (Screen Reader) Engine: {tolk_ver}",
            f"",
            f"--- Localization ---",
            f"Loaded Language: {lang_name}",
            f"Translator: {translator}",
            f"",
            f"Hariku is an accessible productivity and calendar application.",
            f"Press 'License' or 'Contributors' below for more details."
        ]
        
        self.text_ctrl.SetValue("\n".join(lines))

    def _on_license(self, event):
        from ui.document_viewer import show_document
        show_document(self, self._translator("btn_license", default="License"), "license.txt")
        
    def _on_contributors(self, event):
        from ui.document_viewer import show_document
        show_document(self, self._translator("btn_contributors", default="Contributors"), "contributors.txt")

def show_about(parent):
    dlg = AboutDialog(parent)
    dlg.ShowModal()
    dlg.Destroy()
