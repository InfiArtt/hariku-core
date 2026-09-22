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
        
        # Sound file pickers
        # ON Sound
        hbox_on = wx.BoxSizer(wx.HORIZONTAL)
        hbox_on.Add(wx.StaticText(self, label="ON Sound: "), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.fp_on = wx.FilePickerCtrl(self, message="Select ON Sound", wildcard="Sound files (*.wav;*.mp3)|*.wav;*.mp3", path=config.get("sound_on", ""))
        hbox_on.Add(self.fp_on, 1, wx.EXPAND)
        vbox.Add(hbox_on, 0, wx.EXPAND | wx.ALL, 10)
        
        # OFF Sound
        hbox_off = wx.BoxSizer(wx.HORIZONTAL)
        hbox_off.Add(wx.StaticText(self, label="OFF Sound: "), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.fp_off = wx.FilePickerCtrl(self, message="Select OFF Sound", wildcard="Sound files (*.wav;*.mp3)|*.wav;*.mp3", path=config.get("sound_off", ""))
        hbox_off.Add(self.fp_off, 1, wx.EXPAND)
        vbox.Add(hbox_off, 0, wx.EXPAND | wx.ALL, 10)
        
        # Loop Settings
        self.chk_loop = wx.CheckBox(self, label="Enable Looping Sound")
        self.chk_loop.SetValue(config.get("loop_enabled", True))
        vbox.Add(self.chk_loop, 0, wx.ALL, 10)
        
        hbox_loop_snd = wx.BoxSizer(wx.HORIZONTAL)
        hbox_loop_snd.Add(wx.StaticText(self, label="Loop Sound: "), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.fp_loop = wx.FilePickerCtrl(self, message="Select Loop Sound", wildcard="Sound files (*.wav;*.mp3)|*.wav;*.mp3", path=config.get("sound_loop", ""))
        hbox_loop_snd.Add(self.fp_loop, 1, wx.EXPAND)
        vbox.Add(hbox_loop_snd, 0, wx.EXPAND | wx.ALL, 10)
        
        hbox_interval = wx.BoxSizer(wx.HORIZONTAL)
        hbox_interval.Add(wx.StaticText(self, label="Loop Interval (seconds): "), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        interval_val = config.get("loop_interval_sec", 2.0)
        self.spin_interval = wx.SpinCtrlDouble(self, value=str(interval_val), min=2.0, max=60.0, inc=0.5)
        hbox_interval.Add(self.spin_interval, 0, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(hbox_interval, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(vbox)

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
        config["sound_on"] = self.fp_on.GetPath()
        config["sound_off"] = self.fp_off.GetPath()
        config["loop_enabled"] = self.chk_loop.GetValue()
        config["sound_loop"] = self.fp_loop.GetPath()
        config["loop_interval_sec"] = self.spin_interval.GetValue()
        
        core.api.save_data("key_notifier", config)
