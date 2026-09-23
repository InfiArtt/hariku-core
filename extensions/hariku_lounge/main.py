# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import json
import logging
import threading
import requests
import core.api
import core.preferences
import core.hotkeys
from core.events import bus

logger = logging.getLogger(__name__)

EXTENSION_ID = "hariku_lounge"
DEFAULT_API_URL = "https://infiartt.com"
# Default polling interval in seconds
DEFAULT_POLL_INTERVAL = 1

class LoungePreferencesPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # API URL
        url_sizer = wx.BoxSizer(wx.HORIZONTAL)
        url_label = wx.StaticText(self, label="Lounge API URL:")
        self.url_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        url_sizer.Add(url_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        url_sizer.Add(self.url_input, 1, wx.ALL | wx.EXPAND, 5)
        
        # Polling Interval
        poll_sizer = wx.BoxSizer(wx.HORIZONTAL)
        poll_label = wx.StaticText(self, label="Polling Interval (seconds):")
        self.poll_slider = wx.Slider(self, value=1, minValue=1, maxValue=10, 
                                     style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        poll_sizer.Add(poll_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        poll_sizer.Add(self.poll_slider, 1, wx.ALL | wx.EXPAND, 5)
        
        sizer.Add(url_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(poll_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(sizer)
        
        # Load saved data
        data = core.api.load_data(EXTENSION_ID)
        saved_url = data.get("api_url", DEFAULT_API_URL)
        if "novarealm" in (saved_url or ""):
            saved_url = DEFAULT_API_URL   # migrate off the retired domain
        self.url_input.SetValue(saved_url)
        self.poll_slider.SetValue(data.get("poll_interval", DEFAULT_POLL_INTERVAL))

    def get_data(self):
        return {
            "api_url": self.url_input.GetValue(),
            "poll_interval": self.poll_slider.GetValue()
        }

def apply_settings():
    pass


class HarikuLoungeFrame(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title="Hariku Lounge", size=(600, 450))
        
        self.access_token = None
        self.user_profile = None
        self.last_message_id = 0
        
        # Load API URL and Interval
        data = core.api.load_data(EXTENSION_ID)
        self.api_url = data.get("api_url", DEFAULT_API_URL)
        # Migrate old saved URLs off the retired novarealm.cloud domain.
        if "novarealm" in (self.api_url or ""):
            self.api_url = DEFAULT_API_URL
        self.poll_interval = data.get("poll_interval", DEFAULT_POLL_INTERVAL)
        
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Splitter between chat and online users
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Chat History
        chat_vbox = wx.BoxSizer(wx.VERTICAL)
        chat_label = wx.StaticText(panel, label="Chat History:")
        self.chat_history = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        chat_vbox.Add(chat_label, 0, wx.ALL, 5)
        chat_vbox.Add(self.chat_history, 1, wx.EXPAND | wx.ALL, 5)
        
        # Online Users
        users_vbox = wx.BoxSizer(wx.VERTICAL)
        users_label = wx.StaticText(panel, label="Online Users:")
        self.online_users = wx.ListBox(panel)
        users_vbox.Add(users_label, 0, wx.ALL, 5)
        users_vbox.Add(self.online_users, 1, wx.EXPAND | wx.ALL, 5)
        
        top_sizer.Add(chat_vbox, 3, wx.EXPAND)
        top_sizer.Add(users_vbox, 1, wx.EXPAND)
        
        # Input Area
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.message_input = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.message_input.Bind(wx.EVT_TEXT_ENTER, self.on_send_message)
        self.send_btn = wx.Button(panel, label="Send")
        self.send_btn.Bind(wx.EVT_BUTTON, self.on_send_message)
        
        input_sizer.Add(self.message_input, 1, wx.ALL | wx.EXPAND, 5)
        input_sizer.Add(self.send_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(top_sizer, 1, wx.EXPAND)
        main_sizer.Add(input_sizer, 0, wx.EXPAND)
        
        panel.SetSizer(main_sizer)
        
        # Fetch initial auth data
        self.load_auth()
        
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        # Start Polling Timer
        self.poll_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_poll, self.poll_timer)
        self.poll_timer.Start(self.poll_interval * 1000)

    def load_auth(self):
        acc_data = core.api.load_data("account_manager")
        self.access_token = acc_data.get("access_token")
        self.user_profile = acc_data.get("user_profile")
        
        if not self.access_token:
            self.chat_history.SetValue("Please log in using the Account Manager first.")
            self.message_input.Disable()
            self.send_btn.Disable()
        else:
            self.message_input.Enable()
            self.send_btn.Enable()

    def on_poll(self, event):
        if not self.access_token:
            return
            
        def fetch():
            try:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                resp = requests.get(f"{self.api_url}/api/chat", headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    wx.CallAfter(self.update_ui, data)
            except Exception as e:
                logger.error(f"[Lounge] Poll error: {e}")
                
        threading.Thread(target=fetch, daemon=True).start()

    def update_ui(self, data):
        messages = data.get("messages", [])
        online = data.get("online", [])
        
        # Update online users
        current_users = [u['username'] for u in online]
        self.online_users.Set(current_users)
        
        # Update chat history (only append new messages to avoid cursor jump)
        for msg in messages:
            msg_id = int(msg['id'])
            if msg_id > self.last_message_id:
                time_str = msg['created_at'].split(" ")[1] # Just get the time part
                line = f"[{time_str}] {msg['username']}: {msg['message']}\n"
                self.chat_history.AppendText(line)
                self.last_message_id = msg_id

    def on_send_message(self, event):
        msg = self.message_input.GetValue().strip()
        if not msg or not self.access_token:
            return
            
        self.message_input.SetValue("")
        
        def send():
            try:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                requests.post(f"{self.api_url}/api/chat", data={"message": msg}, headers=headers, timeout=5)
                # Next poll will fetch the message
            except Exception as e:
                logger.error(f"[Lounge] Send error: {e}")
                
        threading.Thread(target=send, daemon=True).start()

    def on_close(self, event):
        self.poll_timer.Stop()
        self.Hide()


# Global instance
_lounge_frame = None

def toggle_lounge():
    global _lounge_frame
    if not _lounge_frame:
        _lounge_frame = HarikuLoungeFrame(None)
    
    if _lounge_frame.IsShown():
        _lounge_frame.Hide()
    else:
        _lounge_frame.load_auth() # Refresh auth just in case
        _lounge_frame.Show()
        _lounge_frame.Raise()
        
def register(event_bus):
    def create_and_apply(parent):
        panel = LoungePreferencesPanel(parent)
        def apply():
            data = panel.get_data()
            core.api.save_data(EXTENSION_ID, data)
            if _lounge_frame:
                _lounge_frame.api_url = data["api_url"]
                _lounge_frame.poll_interval = data["poll_interval"]
                _lounge_frame.poll_timer.Start(data["poll_interval"] * 1000)
        return panel, apply

    # Preferences API: register_panel(category, name, create_func, apply_func).
    # create_func(parent) returns a wx.Panel; apply_func() is called on OK. Since
    # apply needs the panel instance, it is kept in the module global below.
    global _lounge_panel_instance
    _lounge_panel_instance = None
    
    def create_settings_panel(parent):
        global _lounge_panel_instance
        _lounge_panel_instance = LoungePreferencesPanel(parent)
        return _lounge_panel_instance
        
    def apply_settings():
        if _lounge_panel_instance:
            data = _lounge_panel_instance.get_data()
            core.api.save_data(EXTENSION_ID, data)
            if _lounge_frame:
                _lounge_frame.api_url = data["api_url"]
                _lounge_frame.poll_interval = data["poll_interval"]
                _lounge_frame.poll_timer.Start(data["poll_interval"] * 1000)
                
    core.preferences.register_panel("Extensions", "Hariku Lounge", create_settings_panel, apply_settings)
    core.hotkeys.register_action(
        "Hariku Lounge",         # Extension Name
        "toggle",                # Action ID
        "Toggle Hariku Lounge",  # Description
        ord("L"),                # Keycode 'L'
        True,                    # Ctrl
        toggle_lounge,           # Callback
        default_shift=True,      # Shift
        default_global=True      # Global hotkey
    )
