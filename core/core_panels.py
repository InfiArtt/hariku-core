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
import core.personal
import core.ui_scale
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

# ---------------------------------------------------------------------------
# Profile Panel: the user's name, nickname and own %placeholders% (core.personal)
# ---------------------------------------------------------------------------
_profile_panel_instance = None

# Speak a result a moment after a dialog closes, so the screen reader's focus
# announcement doesn't cut it off.
_ANNOUNCE_DELAY_MS = 300


def _speak(message, interrupt=False):
    from core.speech import speak
    speak(message, interrupt=interrupt)


def _announce(message):
    wx.CallLater(_ANNOUNCE_DELAY_MS, _speak, message)


def _plain_label(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def _labeled(parent, sizer, label, make, proportion=0):
    """A label, then the control it names, which gets the same accessible name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
    ctrl = make()
    ctrl.SetName(_plain_label(label))
    sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
    return ctrl


class ProfileFieldDialog(wx.Dialog):
    """Adds or edits one of the user's own placeholders. Invalid input is shown
    and spoken; the dialog stays open with focus on the field to fix."""

    def __init__(self, parent, title, key="", value="", taken=()):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.result = None
        self._taken = list(taken)
        root = wx.BoxSizer(wx.VERTICAL)
        self.txt_key = _labeled(self, root, _("profile_lbl_key"),
                                lambda: wx.TextCtrl(self, value=key))
        self.txt_value = _labeled(self, root, _("profile_lbl_value"),
                                  lambda: wx.TextCtrl(self, value=value))
        self.lbl_error = wx.StaticText(self, label="")
        root.Add(self.lbl_error, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        buttons = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(self, wx.ID_OK, _("prefs_btn_ok"))
        self.btn_ok.SetDefault()
        self.btn_ok.Bind(wx.EVT_BUTTON, self._on_ok)
        buttons.AddButton(self.btn_ok)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL, _("prefs_btn_cancel")))
        buttons.Realize()
        root.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(root)
        self.SetEscapeId(wx.ID_CANCEL)

        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.Fit()
        width, height = self.GetSize()
        self.SetMinSize((width, height))
        self.SetSize((max(width, 420), height))
        self.CentreOnParent()
        self.txt_key.SetFocus()
        self.txt_key.SelectAll()

    def _on_ok(self, event=None):
        try:
            key = core.personal.check_key(self.txt_key.GetValue(), self._taken)
            value = core.personal.check_value(self.txt_value.GetValue())
        except core.personal.ProfileError as e:
            self._show_error(str(e), self.txt_value if e.field == "value" else self.txt_key)
            return
        self.result = (key, value)
        self.EndModal(wx.ID_OK)

    def _show_error(self, message, ctrl):
        width = self.GetSize().width
        self.lbl_error.SetLabel(message)
        self.lbl_error.Wrap(max(200, self.GetClientSize().width - 20))
        self.Fit()   # room for the message, keeping the width the user gave it
        self.SetSize((max(width, self.GetSize().width), self.GetSize().height))
        self.Layout()
        ctrl.SetFocus()
        ctrl.SelectAll()
        # After the focus move, so the reader's announcement of the field doesn't swallow it.
        wx.CallLater(100, _speak, message, True)


def ask_profile_field(parent, title, key="", value="", taken=()):
    """Show the placeholder dialog; the checked (key, value), or None if cancelled."""
    dlg = ProfileFieldDialog(parent, title, key, value, taken)
    try:
        return dlg.result if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()


class ProfileSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        profile = core.personal.get_profile()
        self._fields = list(profile["fields"])   # [(key, value)], saved on OK/Apply
        vbox = wx.BoxSizer(wx.VERTICAL)

        lbl_help = wx.StaticText(self, label=_("profile_help"))
        lbl_help.Wrap(500)
        vbox.Add(lbl_help, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.txt_name = _labeled(self, vbox, _("profile_lbl_name"),
                                 lambda: wx.TextCtrl(self, value=profile["name"]))
        self.txt_name.SetMaxLength(core.personal.MAX_VALUE_LENGTH)
        self.txt_nickname = _labeled(self, vbox, _("profile_lbl_nickname"),
                                     lambda: wx.TextCtrl(self, value=profile["nickname"]))
        self.txt_nickname.SetMaxLength(core.personal.MAX_VALUE_LENGTH)

        self.list_fields = _labeled(
            self, vbox, _("profile_lbl_fields"),
            lambda: wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN),
            proportion=1)
        self.list_fields.InsertColumn(0, _("profile_col_placeholder"), width=180)
        self.list_fields.InsertColumn(1, _("profile_col_value"), width=320)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add = wx.Button(self, label=_("profile_btn_add"))
        self.btn_edit = wx.Button(self, label=_("profile_btn_edit"))
        self.btn_remove = wx.Button(self, label=_("profile_btn_remove"))
        for btn, handler in ((self.btn_add, self.on_add), (self.btn_edit, self.on_edit),
                             (self.btn_remove, self.on_remove)):
            btn.Bind(wx.EVT_BUTTON, handler)
            hbox.Add(btn, 0, wx.RIGHT, 5)
        vbox.Add(hbox, 0, wx.ALL, 10)
        self.SetSizer(vbox)

        # Enter edits and Delete removes; selecting a row never moves focus.
        self.list_fields.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_edit)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self._refresh(0)

    def _refresh(self, select=None):
        self.list_fields.DeleteAllItems()
        for i, (key, value) in enumerate(self._fields):
            self.list_fields.InsertItem(i, f"%{key}%")
            self.list_fields.SetItem(i, 1, value)
        if self._fields and select is not None:
            select = max(0, min(select, len(self._fields) - 1))
            state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
            self.list_fields.SetItemState(select, state, state)
            self.list_fields.EnsureVisible(select)

    def selected_index(self):
        index = self.list_fields.GetFirstSelected()
        return index if 0 <= index < len(self._fields) else -1

    def _mark_dirty(self):
        top = wx.GetTopLevelParent(self)
        if top is not None and hasattr(top, "is_dirty"):
            top.is_dirty = True

    def _changed(self, index, message):
        self._refresh(index)
        self._mark_dirty()
        if self._fields:
            self.list_fields.SetFocus()
        else:
            self.btn_add.SetFocus()
        _announce(message)

    def _on_char_hook(self, event):
        if wx.Window.FindFocus() is self.list_fields and not event.HasAnyModifiers():
            code = event.GetKeyCode()
            if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                self.on_edit()
                return
            if code in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
                self.on_remove()
                return
        event.Skip()

    def on_add(self, event=None):
        result = ask_profile_field(self, _("profile_dlg_add_title"),
                                   taken=[key for key, value in self._fields])
        if result is None:
            return
        self._fields.append(result)
        self._changed(len(self._fields) - 1, _("profile_added", token=result[0]))

    def on_edit(self, event=None):
        index = self.selected_index()
        if index < 0:
            _speak(_("profile_nothing_selected"), True)
            return
        key, value = self._fields[index]
        taken = [k for i, (k, v) in enumerate(self._fields) if i != index]
        result = ask_profile_field(self, _("profile_dlg_edit_title"), key, value, taken)
        if result is None:
            return
        self._fields[index] = result
        self._changed(index, _("profile_changed", token=result[0]))

    def on_remove(self, event=None):
        index = self.selected_index()
        if index < 0:
            _speak(_("profile_nothing_selected"), True)
            return
        key = self._fields.pop(index)[0]
        self._changed(index, _("profile_removed", token=key))

    def ApplyChanges(self):
        try:
            core.personal.set_profile(self.txt_name.GetValue(), self.txt_nickname.GetValue(),
                                      self._fields)
        except core.personal.ProfileError as e:
            wx.MessageBox(str(e), _("error"), wx.OK | wx.ICON_ERROR, self)


def create_profile_panel(parent):
    global _profile_panel_instance
    _profile_panel_instance = ProfileSettingsPanel(parent)
    return _profile_panel_instance


def apply_profile_settings():
    if _profile_panel_instance:
        try:
            _profile_panel_instance.ApplyChanges()
        except RuntimeError:
            pass  # panel already destroyed

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
    core.preferences.register_panel(_("prefs_tab_profile"), "", create_profile_panel,    apply_profile_settings)
    core.preferences.register_panel("Extensions",          "", create_ext_settings_panel, apply_ext_settings)
    core.preferences.register_panel("Advanced",            "", create_adv_panel,          apply_adv_settings)

