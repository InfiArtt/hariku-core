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
import core.api

class KeyNotifierSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.InitUI()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        config = self._load_config()
        
        # Monitor settings
        self.chk_caps = wx.CheckBox(self, label="Monitor CapsLock")
        self.chk_caps.SetValue(config.get("monitor_capslock", True))
        vbox.Add(self.chk_caps, 0, wx.ALL, 10)
        
        self.chk_num = wx.CheckBox(self, label="Monitor NumLock")
        self.chk_num.SetValue(config.get("monitor_numlock", False))
        vbox.Add(self.chk_num, 0, wx.ALL, 10)
        
        # Sound files: a labelled text field and a Browse button each. (A
        # wx.FilePickerCtrl hides an unlabelled text field inside, which screen
        # readers announce as just "edit".)
        self.fp_on = self._sound_row(vbox, "ON Sound:", "Browse for the ON sound...",
                                     "Select ON Sound", config.get("sound_on", ""))
        self.fp_off = self._sound_row(vbox, "OFF Sound:", "Browse for the OFF sound...",
                                      "Select OFF Sound", config.get("sound_off", ""))

        # Loop Settings
        self.chk_loop = wx.CheckBox(self, label="Enable Looping Sound")
        self.chk_loop.SetValue(config.get("loop_enabled", True))
        vbox.Add(self.chk_loop, 0, wx.ALL, 10)
        
        self.fp_loop = self._sound_row(vbox, "Loop Sound:", "Browse for the loop sound...",
                                       "Select Loop Sound", config.get("sound_loop", ""))
        
        hbox_interval = wx.BoxSizer(wx.HORIZONTAL)
        hbox_interval.Add(wx.StaticText(self, label="Loop Interval (seconds): "), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        interval_val = config.get("loop_interval_sec", 2.0)
        self.spin_interval = wx.SpinCtrlDouble(self, value=str(interval_val), min=2.0, max=60.0, inc=0.5)
        hbox_interval.Add(self.spin_interval, 0, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(hbox_interval, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(vbox)

    def _sound_row(self, vbox, label, browse_label, title, path):
        """A label, the path field it names, then a Browse button. The label is
        created first so screen readers read it with the field."""
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        field = wx.TextCtrl(self, value=path)
        field.SetName(label.rstrip(":"))
        row.Add(field, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        browse = wx.Button(self, label=browse_label)
        browse.Bind(wx.EVT_BUTTON, lambda event: self._browse(field, title))
        row.Add(browse, 0, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(row, 0, wx.EXPAND | wx.ALL, 10)
        return field

    def _browse(self, field, title):
        current = field.GetValue()
        with wx.FileDialog(self, title, defaultDir=os.path.dirname(current),
                           defaultFile=os.path.basename(current),
                           wildcard="Sound files (*.wav;*.mp3)|*.wav;*.mp3",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                field.SetValue(dlg.GetPath())
                field.SetFocus()

    def _load_config(self):
        config = core.api.load_data("key_notifier")
        
        ext_dir = os.path.dirname(os.path.abspath(__file__))
        default_on = os.path.join(ext_dir, "sounds", "on.wav")
        default_off = os.path.join(ext_dir, "sounds", "off.wav")
        default_loop = os.path.join(ext_dir, "sounds", "loop.wav")
        
        if "sound_on" not in config:
            config["sound_on"] = default_on if os.path.exists(default_on) else ""
        if "sound_off" not in config:
            config["sound_off"] = default_off if os.path.exists(default_off) else ""
        if "sound_loop" not in config:
            config["sound_loop"] = default_loop if os.path.exists(default_loop) else ""
            
        return config

    def ApplyChanges(self):
        config = core.api.load_data("key_notifier")
        
        config["monitor_capslock"] = self.chk_caps.GetValue()
        config["monitor_numlock"] = self.chk_num.GetValue()
        config["sound_on"] = self.fp_on.GetValue().strip()
        config["sound_off"] = self.fp_off.GetValue().strip()
        config["loop_enabled"] = self.chk_loop.GetValue()
        config["sound_loop"] = self.fp_loop.GetValue().strip()
        config["loop_interval_sec"] = self.spin_interval.GetValue()
        
        core.api.save_data("key_notifier", config)
