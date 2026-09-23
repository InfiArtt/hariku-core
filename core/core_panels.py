# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import wx
import core.api
from core.i18n import get_translator, get_available_languages, get_current_language, set_language

_ = get_translator("core")

DATE_FORMATS = {
    "Long (Weekday, Day Month Year) - Example: Tuesday, 16 June 2026": "%A, %d %B %Y",
    "Long (Day Month Year) - Example: 16 June 2026": "%d %B %Y",
    "Medium (Wkdy, Day Mon Year) - Example: Tue, 16 Jun 2026": "%a, %d %b %Y",
    "Medium (Day Mon Year) - Example: 16 Jun 2026": "%d %b %Y",
    "Short (DD/MM/YYYY) - Example: 16/06/2026": "%d/%m/%Y",
    "Short (DD-MM-YYYY) - Example: 16-06-2026": "%d-%m-%Y",
    "International (YYYY-MM-DD) - Example: 2026-06-16": "%Y-%m-%d"
}

class GeneralSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.InitUI()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        config = core.api.load_data("Core")
        
        self.chk_startup_sound = wx.CheckBox(self, label=_("lbl_play_startup_sound"))
        self.chk_startup_sound.SetValue(config.get("play_startup_sound", True))
        
        self.chk_interrupt_speech = wx.CheckBox(self, label=_("lbl_interrupt_speech"))
        self.chk_interrupt_speech.SetValue(config.get("interrupt_speech", True))
        
        self.chk_autostart = wx.CheckBox(self, label=_("lbl_autostart"))
        self.chk_autostart.SetValue(config.get("auto_start", False))
        
        vbox.Add(self.chk_startup_sound, 0, wx.ALL, 10)
        vbox.Add(self.chk_interrupt_speech, 0, wx.ALL, 10)
        vbox.Add(self.chk_autostart, 0, wx.ALL, 10)
        
        # Volume Slider
        hbox_vol = wx.BoxSizer(wx.HORIZONTAL)
        lbl_vol = wx.StaticText(self, label=_("lbl_global_volume"))
        self.slider_volume = wx.Slider(self, value=config.get("volume", 100), minValue=0, maxValue=100, 
                                       style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        hbox_vol.Add(lbl_vol, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        hbox_vol.Add(self.slider_volume, 1, wx.EXPAND)
        vbox.Add(hbox_vol, 0, wx.EXPAND | wx.ALL, 10)
        
        hbox_date = wx.BoxSizer(wx.HORIZONTAL)
        lbl_date = wx.StaticText(self, label=_("lbl_date_format"))
        
        self.cb_date_format = wx.ComboBox(self, choices=list(DATE_FORMATS.keys()), style=wx.CB_READONLY)
        
        # Load existing selection
        current_format = config.get("date_format", "%A, %d %B %Y")
        selected_idx = 0
        for i, (key, val) in enumerate(DATE_FORMATS.items()):
            if val == current_format:
                selected_idx = i
                break
                
        if self.cb_date_format.GetCount() > 0:
            self.cb_date_format.SetSelection(selected_idx)
        
        hbox_date.Add(lbl_date, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        hbox_date.Add(self.cb_date_format, 1, wx.EXPAND)
        
        vbox.Add(hbox_date, 0, wx.EXPAND | wx.ALL, 10)
        
        # Language Dropdown
        hbox_lang = wx.BoxSizer(wx.HORIZONTAL)
        lbl_lang = wx.StaticText(self, label=_("lbl_language"))
        
        available_langs = get_available_languages("core")
        self._lang_codes = [l["language_code"] for l in available_langs]
        lang_names = [l["language_name"] for l in available_langs]
        
        self.cb_language = wx.ComboBox(self, choices=lang_names, style=wx.CB_READONLY)
        
        # Select current language
        current_lang = get_current_language()
        if current_lang in self._lang_codes:
            self.cb_language.SetSelection(self._lang_codes.index(current_lang))
        elif self.cb_language.GetCount() > 0:
            self.cb_language.SetSelection(0)
        
        self._original_lang = current_lang
        
        hbox_lang.Add(lbl_lang, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        hbox_lang.Add(self.cb_language, 1, wx.EXPAND)
        vbox.Add(hbox_lang, 0, wx.EXPAND | wx.ALL, 10)
        
        lbl_lang_note = wx.StaticText(self, label=_("lbl_language_restart"))
        lbl_lang_note.SetForegroundColour(wx.Colour(128, 128, 128))
        vbox.Add(lbl_lang_note, 0, wx.LEFT | wx.BOTTOM, 10)
        
        self.rb_close_behavior = wx.RadioBox(self, label=_("lbl_close_behavior"), 
                                             choices=[_("lbl_minimize_tray"), _("lbl_quit_app"), _("lbl_show_exit_options")], 
                                             majorDimension=1, style=wx.RA_SPECIFY_COLS)
        
        close_behavior = config.get("close_behavior", "minimize")
        sel = {"minimize": 0, "quit": 1, "ask": 2}.get(close_behavior, 0)
        self.rb_close_behavior.SetSelection(sel)
        
        vbox.Add(self.rb_close_behavior, 0, wx.ALL | wx.EXPAND, 10)

        # Braille output toggle (Tolk sends to a connected braille display when on)
        self.chk_braille = wx.CheckBox(self, label="Also send output to a Braille display")
        self.chk_braille.SetValue(config.get("braille_output", True))
        vbox.Add(self.chk_braille, 0, wx.ALL, 10)

        # --- Low-vision appearance ---
        hbox_scale = wx.BoxSizer(wx.HORIZONTAL)
        hbox_scale.Add(wx.StaticText(self, label="UI text size:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self._scale_keys = ["normal", "large", "xlarge"]
        self.choice_scale = wx.Choice(self, choices=["Normal", "Large", "Extra Large"])
        _cur_scale = config.get("ui_font_scale", "normal")
        self.choice_scale.SetSelection(self._scale_keys.index(_cur_scale) if _cur_scale in self._scale_keys else 0)
        hbox_scale.Add(self.choice_scale, 0, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(hbox_scale, 0, wx.ALL, 10)

        self.chk_high_contrast = wx.CheckBox(self, label="High contrast (yellow on black). For full effect, also try Windows' built-in High Contrast mode.")
        self.chk_high_contrast.SetValue(config.get("high_contrast", False))
        vbox.Add(self.chk_high_contrast, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # --- Telemetry ---
        box_telemetry = wx.StaticBox(self, label="Public Telemetry Data")
        bsizer_telemetry = wx.StaticBoxSizer(box_telemetry, wx.VERTICAL)
        
        lbl_info = wx.StaticText(box_telemetry, label="Anonymous usage statistics are currently disabled: the previous statistics server was retired and no data is collected or sent. This setting is kept for when telemetry returns.")
        lbl_info.Wrap(500)
        bsizer_telemetry.Add(lbl_info, 0, wx.ALL, 5)
        
        self.chk_telemetry = wx.CheckBox(box_telemetry, label="Share my anonymous usage data publicly")
        self.chk_telemetry.SetValue(config.get("telemetry_enabled", True))
        
        bsizer_telemetry.Add(self.chk_telemetry, 0, wx.ALL, 5)
        vbox.Add(bsizer_telemetry, 0, wx.EXPAND | wx.ALL, 10)
        
        # Updater Button
        self.btn_check_updates = wx.Button(self, label=_("lbl_check_updates"))
        self.btn_check_updates.Bind(wx.EVT_BUTTON, self.on_check_updates)
        vbox.Add(self.btn_check_updates, 0, wx.ALL | wx.CENTER, 10)
        
        from core.events import bus
        bus.emit("on_build_general_settings_panel", self, vbox)
        
        self.SetSizer(vbox)

    def on_check_updates(self, event):
        import core.updater
        import threading
        # Run in the background so the UI doesn't freeze during the internet fetch.
        threading.Thread(target=core.updater.check_for_updates, args=(True,), daemon=True).start()

    def ApplyChanges(self):
        config = core.api.load_data("Core")
        
        config["play_startup_sound"] = self.chk_startup_sound.GetValue()
        config["interrupt_speech"] = self.chk_interrupt_speech.GetValue()
        config["braille_output"] = self.chk_braille.GetValue()
        _ssel = self.choice_scale.GetSelection()
        config["ui_font_scale"] = self._scale_keys[_ssel] if _ssel >= 0 else "normal"
        config["high_contrast"] = self.chk_high_contrast.GetValue()
        config["volume"] = self.slider_volume.GetValue()
        
        autostart = self.chk_autostart.GetValue()
        if config.get("auto_start", False) != autostart:
            config["auto_start"] = autostart
            core.api.set_autostart(autostart)
        
        selected_format_key = self.cb_date_format.GetStringSelection()
        config["date_format"] = DATE_FORMATS.get(selected_format_key, "%A, %d %B %Y")
        
        config["close_behavior"] = {0: "minimize", 1: "quit", 2: "ask"}.get(self.rb_close_behavior.GetSelection(), "minimize")
        config["telemetry_enabled"] = self.chk_telemetry.GetValue()
        
        core.api.save_data("Core", config)

        # Re-apply the low-vision appearance live (font scale + high contrast).
        try:
            import core.ui_scale
            core.ui_scale.apply_appearance(core.api.main_window_instance)
        except Exception:
            pass

        # Handle language change
        lang_idx = self.cb_language.GetSelection()
        if lang_idx >= 0 and lang_idx < len(self._lang_codes):
            new_lang = self._lang_codes[lang_idx]
            if new_lang != self._original_lang:
                new_lang_name = self.cb_language.GetStringSelection()
                set_language(new_lang)
                
                resp = wx.MessageBox(
                    _("restart_language_msg", language=new_lang_name),
                    _("restart_language_title"),
                    wx.YES_NO | wx.ICON_INFORMATION
                )
                if resp == wx.YES:
                    core.api.restart_app()
        
        from core.events import bus
        bus.emit("on_apply_general_settings_panel", self)
        bus.emit("on_core_preferences_updated")

_panel_instance = None
_adv_panel_instance = None

def create_panel(parent):
    global _panel_instance
    _panel_instance = GeneralSettingsPanel(parent)
    return _panel_instance

def apply_general_settings():
    if _panel_instance:
        _panel_instance.ApplyChanges()

class AdvancedSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.InitUI()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        config = core.api.load_data("Core")
        
        # Log Level
        hbox_log = wx.BoxSizer(wx.HORIZONTAL)
        lbl_log = wx.StaticText(self, label=_("lbl_log_level"))
        self.cb_log_level = wx.ComboBox(self, choices=["DISABLED", "INFO", "DEBUG", "WARNING", "ERROR"], style=wx.CB_READONLY)
        
        current_log = config.get("log_level", "INFO").upper()
        idx = self.cb_log_level.FindString(current_log)
        self.cb_log_level.SetSelection(idx if idx != wx.NOT_FOUND else 1)
        
        hbox_log.Add(lbl_log, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        hbox_log.Add(self.cb_log_level, 1, wx.EXPAND)
        vbox.Add(hbox_log, 0, wx.EXPAND | wx.ALL, 10)
        
        # Buttons
        self.btn_data = wx.Button(self, label=_("btn_open_data_folder"))
        self.btn_data.Bind(wx.EVT_BUTTON, self.OnOpenData)
        vbox.Add(self.btn_data, 0, wx.ALL | wx.EXPAND, 5)
        
        self.btn_log = wx.Button(self, label=_("btn_view_log"))
        self.btn_log.Bind(wx.EVT_BUTTON, self.OnViewLog)
        vbox.Add(self.btn_log, 0, wx.ALL | wx.EXPAND, 5)
        
        self.btn_cache = wx.Button(self, label=_("btn_clear_cache"))
        self.btn_cache.Bind(wx.EVT_BUTTON, self.OnClearCache)
        vbox.Add(self.btn_cache, 0, wx.ALL | wx.EXPAND, 5)
        
        self.SetSizer(vbox)
        
    def OnOpenData(self, event):
        core.api.open_data_folder()
        
    def OnViewLog(self, event):
        core.api.open_log_viewer()
        
    def OnClearCache(self, event):
        success = core.api.clear_cache()
        from core.speech import speak
        if success:
            speak(_("msg_cache_cleared"))
            wx.MessageBox(_("msg_cache_cleared"), "Info", wx.OK | wx.ICON_INFORMATION)
        else:
            speak(_("msg_cache_failed"))
            wx.MessageBox(_("msg_cache_failed"), "Error", wx.OK | wx.ICON_ERROR)
            
    def ApplyChanges(self):
        config = core.api.load_data("Core")
        old_level = config.get("log_level", "INFO").upper()
        new_level = self.cb_log_level.GetStringSelection()
        config["log_level"] = new_level
        core.api.save_data("Core", config)
        
        if new_level != old_level:
            import logging
            root_logger = logging.getLogger()
            if new_level == "DISABLED":
                root_logger.handlers = []
                root_logger.addHandler(logging.NullHandler())
                root_logger.setLevel(logging.CRITICAL)
            else:
                try:
                    level_val = getattr(logging, new_level)
                    root_logger.setLevel(level_val)
                except Exception:
                    pass

def create_adv_panel(parent):
    global _adv_panel_instance
    _adv_panel_instance = AdvancedSettingsPanel(parent)
    return _adv_panel_instance

def apply_adv_settings():
    if _adv_panel_instance:
        _adv_panel_instance.ApplyChanges()

# ---------------------------------------------------------------------------
# Extension Settings Panel
# ---------------------------------------------------------------------------
_ext_settings_panel_instance = None

class ExtensionSettingsPanel(wx.Panel):
    _BEHAVIORS = [
        ("notify",      "Notify me when updates are available"),
        ("auto_update", "Update automatically"),
        ("do_nothing",  "Do nothing"),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        import os
        config   = core.api.load_data("Core")
        current  = config.get("extension_update_behavior", "notify")
        self.enable_scratchpad = config.get("enable_scratchpad", False)
        
        default_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scratchpad"))
        self.scratchpad_dir = config.get("scratchpad_dir", "") or default_dir

        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(self, label="When an extension update is available:"),
                 0, wx.ALL, 10)

        self._radios = []
        for value, label in self._BEHAVIORS:
            rb = wx.RadioButton(self, label=label,
                                style=wx.RB_GROUP if value == self._BEHAVIORS[0][0] else 0)
            rb.SetValue(current == value)
            rb._behavior_value = value
            self._radios.append(rb)
            vbox.Add(rb, 0, wx.LEFT | wx.BOTTOM, 15)

        # --- Developer Scratchpad UI ---
        vbox.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 10)
        
        lbl_chk = "Enable Developer Scratchpad Mode. WARNING: Running unpacked/unstable extensions from the scratchpad can cause application crashes and data loss. Use at your own risk."
        self.chk_scratchpad = wx.CheckBox(self, label=lbl_chk)
        self.chk_scratchpad.SetValue(self.enable_scratchpad)
        self.chk_scratchpad.Bind(wx.EVT_CHECKBOX, self.OnToggleScratchpad)
        vbox.Add(self.chk_scratchpad, 0, wx.LEFT | wx.TOP | wx.RIGHT | wx.BOTTOM, 10)
        
        self.scratchpad_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.lbl_dir = wx.StaticText(self, label=f"Current Folder: {self.scratchpad_dir}")
        self.lbl_dir.Wrap(350)
        self.scratchpad_sizer.Add(self.lbl_dir, 0, wx.BOTTOM, 5)
        
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_change = wx.Button(self, label="Change Folder...")
        self.btn_open = wx.Button(self, label="Open Folder")
        
        self.btn_change.Bind(wx.EVT_BUTTON, self.OnChangeFolder)
        self.btn_open.Bind(wx.EVT_BUTTON, self.OnOpenFolder)
        
        btn_sizer.Add(self.btn_change, 0, wx.RIGHT, 10)
        btn_sizer.Add(self.btn_open, 0)
        
        self.scratchpad_sizer.Add(btn_sizer, 0, wx.ALL, 0)
        vbox.Add(self.scratchpad_sizer, 0, wx.LEFT | wx.BOTTOM, 25)

        self._update_scratchpad_ui()
        self.SetSizer(vbox)
        
    def OnToggleScratchpad(self, event):
        self.enable_scratchpad = self.chk_scratchpad.GetValue()
        self._update_scratchpad_ui()
        
    def _update_scratchpad_ui(self):
        if self.enable_scratchpad:
            self.lbl_dir.Enable()
            self.btn_change.Enable()
            self.btn_open.Enable()
        else:
            self.lbl_dir.Disable()
            self.btn_change.Disable()
            self.btn_open.Disable()

    def OnChangeFolder(self, event):
        import os
        dlg = wx.DirDialog(self, "Select Developer Scratchpad Folder", defaultPath=self.scratchpad_dir, style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.scratchpad_dir = dlg.GetPath()
            self.lbl_dir.SetLabel(f"Current Folder: {self.scratchpad_dir}")
            self.Layout()
        dlg.Destroy()
        
    def OnOpenFolder(self, event):
        import os
        if not os.path.exists(self.scratchpad_dir):
            os.makedirs(self.scratchpad_dir, exist_ok=True)
        os.startfile(self.scratchpad_dir)

    def ApplyChanges(self):
        config = core.api.load_data("Core")
        for rb in self._radios:
            if rb.GetValue():
                config["extension_update_behavior"] = rb._behavior_value
                break
                
        old_enable = config.get("enable_scratchpad", False)
        old_dir = config.get("scratchpad_dir", "")
        
        config["enable_scratchpad"] = self.enable_scratchpad
        config["scratchpad_dir"] = self.scratchpad_dir
        
        core.api.save_data("Core", config)
        
        if old_enable != self.enable_scratchpad or old_dir != self.scratchpad_dir:
            resp = core.api.prompt_yes_no(
                "You have changed Developer Scratchpad settings. A restart is required for the changes to take effect.\n\nRestart now?", 
                "Restart Required"
            )
            if resp:
                core.api.restart_app()

def create_ext_settings_panel(parent):
    global _ext_settings_panel_instance
    _ext_settings_panel_instance = ExtensionSettingsPanel(parent)
    return _ext_settings_panel_instance

def apply_ext_settings():
    if _ext_settings_panel_instance:
        _ext_settings_panel_instance.ApplyChanges()

def register():
    import core.preferences
    core.preferences.register_panel("General",             "", create_panel,             apply_general_settings)
    core.preferences.register_panel("Extensions",          "", create_ext_settings_panel, apply_ext_settings)
    core.preferences.register_panel("Advanced",            "", create_adv_panel,          apply_adv_settings)

