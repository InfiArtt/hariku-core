# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import sys
import os
import json
import traceback
import urllib.request

import core.api
import core.constants
import core.endpoints
from core.speech import speak

class CrashDialog(wx.Dialog):
    def __init__(self, parent, exc_type, exc_value, exc_traceback):
        from core.i18n import get_translator
        self._ = get_translator("core")
        
        super().__init__(parent, title="Hariku - Fatal Error", size=(650, 500), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.STAY_ON_TOP)
        self.exc_type = exc_type
        self.exc_value = exc_value
        self.exc_traceback = exc_traceback
        self.traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        self._init_ui()
        self.CentreOnParent()
        
    def _init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl_title = wx.StaticText(self, label="Oops! Hariku encountered a fatal error.")
        lbl_title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(lbl_title, 0, wx.ALL, 10)
        
        lbl_desc = wx.StaticText(self, label="The application cannot continue and must be closed. To help us fix this issue, you can send this crash report directly to the developer.")
        lbl_desc.Wrap(600)
        vbox.Add(lbl_desc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Readonly TextCtrl for NVDA
        self.txt_traceback = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.txt_traceback.SetFont(font)
        
        error_display = f"Type: {self.exc_type.__name__}\nMessage: {str(self.exc_value)}\n\nTraceback:\n{self.traceback_text}"
        self.txt_traceback.SetValue(error_display)
        vbox.Add(self.txt_traceback, 1, wx.EXPAND | wx.ALL, 10)
        
        # Preferences for future crashes
        lbl_pref = wx.StaticText(self, label="How should we handle future crash reports?")
        lbl_pref.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(lbl_pref, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        
        self.rb_ask = wx.RadioButton(self, label="Ask me every time a crash happens", style=wx.RB_GROUP)
        self.rb_auto = wx.RadioButton(self, label="Automatically send crash reports in the background")
        self.rb_never = wx.RadioButton(self, label="Do not ask and do not send anything")
        
        config = core.api.load_data("Core")
        behavior = config.get("crash_report_behavior", "ask")
        if behavior == "auto":
            self.rb_auto.SetValue(True)
        elif behavior == "never":
            self.rb_never.SetValue(True)
        else:
            self.rb_ask.SetValue(True)
            
        vbox.Add(self.rb_ask, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        vbox.Add(self.rb_auto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
        vbox.Add(self.rb_never, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_send = wx.Button(self, label="Send Report && Close")
        self.btn_close = wx.Button(self, label="Close Without Sending")

        self.btn_send.Bind(wx.EVT_BUTTON, self.OnSend)
        self.btn_close.Bind(wx.EVT_BUTTON, self.OnClose)
        
        hbox.Add(self.btn_send, 0, wx.RIGHT, 10)
        hbox.Add(self.btn_close, 0)
        
        vbox.Add(hbox, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(vbox)
        
    def _save_behavior(self):
        config = core.api.load_data("Core")
        if self.rb_auto.GetValue():
            config["crash_report_behavior"] = "auto"
        elif self.rb_never.GetValue():
            config["crash_report_behavior"] = "never"
        else:
            config["crash_report_behavior"] = "ask"
        core.api.save_data("Core", config)
        
    def OnSend(self, event):
        self._save_behavior()
        self.btn_send.Disable()
        self.btn_close.Disable()
        self.btn_send.SetLabel("Sending...")

        # Run upload in a background thread so the UI does not freeze.
        import threading
        threading.Thread(target=self._upload_report, daemon=True).start()

    def OnClose(self, event):
        self._save_behavior()
        self.EndModal(wx.ID_CANCEL)

    def _upload_report(self):
        import platform

        config = core.api.load_data("Core")
        lang = config.get("language", "en")

        payload = {
            "app_version": core.constants.CORE_VERSION,
            "os_info": platform.platform(),
            "language": lang,
            "error_type": self.exc_type.__name__,
            "error_message": str(self.exc_value),
            "traceback": self.traceback_text
        }

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(core.endpoints.CRASH_REPORT_URL, data=data,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                pass
        except Exception:
            # Silent fail if the network is down during a crash.
            pass

        wx.CallAfter(self.EndModal, wx.ID_OK)
