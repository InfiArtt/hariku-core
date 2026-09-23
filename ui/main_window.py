# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import wx.adv
from core.events import bus
from core.speech import speak
from core.i18n import get_translator, format_date
import core.api
import core.hotkeys
import core.sounds
import core.ui_scale

_ = get_translator("core")

class MainWindow(wx.Frame):
    def __init__(self, parent, title):
        super(MainWindow, self).__init__(parent, title=title, size=(600, 400))
        
        # Register with the API so extensions can access the selected date
        core.api.main_window_instance = self
        self.InitUI()
        self.RegisterCoreHotkeys()
        
        # Apply global hotkeys to the OS
        core.hotkeys.apply_global_hotkeys(self)

        from ui.taskbar_icon import HarikuTaskBarIcon
        self.tb_icon = HarikuTaskBarIcon(self)
        
        # Apply low-vision appearance (font scale + high contrast) if configured.
        core.ui_scale.apply_appearance(self)

        # Notify extensions that the UI is ready
        bus.emit("on_ui_ready", self)
        
    def InitUI(self):
        self.panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        st = wx.StaticText(self.panel, label="Hariku V2 - Core")
        st.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(st, flag=wx.ALL | wx.ALIGN_CENTER, border=10)
        
        # Use GenericCalendarCtrl instead of the native Windows CalendarCtrl so
        # NVDA does not intercept the native "SysMonthCal32" events and instead
        # listens purely to our Tolk output.
        self.calendar = wx.adv.GenericCalendarCtrl(self.panel, wx.ID_ANY, wx.DateTime.Now())

        # Keep the calendar from taking native focus so NVDA does not log the
        # default (numeric) readings, keeping the log clean.
        self.calendar.Bind(wx.EVT_SET_FOCUS, lambda e: self.panel.SetFocus())
        
        vbox.Add(self.calendar, 1, wx.EXPAND | wx.ALL, 10)
        
        self.panel.SetSizer(vbox)
        
        menubar = wx.MenuBar()
        fileMenu = wx.Menu()
        
        prefMenu = wx.Menu()
        prefMenu.Append(wx.ID_PREFERENCES, _("menu_preferences_open"))
        self.Bind(wx.EVT_MENU, self.OnOpenPreferences, id=wx.ID_PREFERENCES)
        
        # Minimize to System Tray
        item_minimize = wx.MenuItem(fileMenu, wx.ID_ANY, _("menu_minimize_to_tray"))
        fileMenu.Append(item_minimize)
        self.Bind(wx.EVT_MENU, lambda e: self.MinimizeToTray(), item_minimize)
        
        fileMenu.AppendSeparator()
        
        # Exit Options submenu
        exitMenu = wx.Menu()
        item_exit       = exitMenu.Append(wx.ID_ANY, _("menu_exit"))
        item_restart    = exitMenu.Append(wx.ID_ANY, _("menu_restart"))
        item_safe_mode  = exitMenu.Append(wx.ID_ANY, _("menu_restart_safe"))
        
        self.Bind(wx.EVT_MENU, lambda e: self.DoQuit(),           item_exit)
        self.Bind(wx.EVT_MENU, lambda e: core.api.restart_app(),  item_restart)
        self.Bind(wx.EVT_MENU, lambda e: core.api.restart_app(safe_mode=True), item_safe_mode)
        
        fileMenu.AppendSubMenu(exitMenu, _("menu_exit_options"))
        
        self.extensionsMenu = wx.Menu()
        ext_manage_item = self.extensionsMenu.Append(wx.ID_ANY, _("menu_manage_extensions"))
        self.Bind(wx.EVT_MENU, self.OnManageExtensions, ext_manage_item)
        self.extensionsMenu.AppendSeparator()
        
        menubar.Append(fileMenu, _("menu_file"))
        menubar.Append(prefMenu, _("menu_preferences"))
        menubar.Append(self.extensionsMenu, _("menu_extensions"))
        
        # --- HELP MENU ---
        helpMenu = wx.Menu()
        
        item_guide   = helpMenu.Append(wx.ID_ANY, _("menu_help_guide"))
        item_whats   = helpMenu.Append(wx.ID_ANY, _("menu_help_whats_new"))
        helpMenu.AppendSeparator()
        
        item_support = helpMenu.Append(wx.ID_ANY, _("menu_help_support"))
        item_report  = helpMenu.Append(wx.ID_ANY, _("menu_help_report"))
        helpMenu.AppendSeparator()
        
        item_welcome = helpMenu.Append(wx.ID_ANY, _("menu_help_welcome"))
        item_update  = helpMenu.Append(wx.ID_ANY, _("menu_help_update"))
        helpMenu.AppendSeparator()
        
        item_about   = helpMenu.Append(wx.ID_ABOUT, _("menu_about"))
        
        menubar.Append(helpMenu, _("menu_help"))
        self.SetMenuBar(menubar)
        
        # Help Menu Binds
        self.Bind(wx.EVT_MENU, self.OnShowUserGuide, item_guide)
        self.Bind(wx.EVT_MENU, self.OnShowWhatsNew, item_whats)
        self.Bind(wx.EVT_MENU, self.OnOpenSupport, item_support)
        self.Bind(wx.EVT_MENU, self.OnOpenReport, item_report)
        self.Bind(wx.EVT_MENU, self.OnShowWelcome, item_welcome)
        self.Bind(wx.EVT_MENU, self.OnCheckUpdate, item_update)
        self.Bind(wx.EVT_MENU, self.OnShowAbout, item_about)
        
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnCharHook)
        self.calendar.Bind(wx.adv.EVT_CALENDAR_SEL_CHANGED, self.OnDateChanged)
        
        # Bind OS-level global hotkeys
        self.Bind(wx.EVT_HOTKEY, self.OnGlobalHotKey)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        
        bus.subscribe("on_open_preferences", self._handle_open_preferences)
        
        # Set up the heartbeat timer (every 60 seconds)
        self.heartbeat_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnHeartbeat, self.heartbeat_timer)
        self.heartbeat_timer.Start(60000)
        
        # Set up the system monitor timer (every 1 second for clipboard, context, etc.)
        self._last_clipboard = ""
        self._last_window_info = {"title": "", "process": ""}
        self._is_idle = False
        self._last_power_state = {"ac_line_status": 255, "battery_percent": 255, "charging": False}
        self._last_network_state = True
        self.monitor_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnSystemMonitor, self.monitor_timer)
        self.monitor_timer.Start(1000)
        
        self.Centre()
        
    def OnHeartbeat(self, event):
        import datetime
        now = datetime.datetime.now()
        bus.emit("on_minute_tick", now)
        
    def OnSystemMonitor(self, event):
        # 1. Clipboard Monitor
        current_clip = core.api.get_clipboard()
        if current_clip and current_clip != self._last_clipboard:
            self._last_clipboard = current_clip
            bus.emit("on_clipboard_changed", current_clip)
            
        # 2. Active Window Monitor
        win_info = core.api.get_active_window_info()
        if win_info["process"] and win_info["process"] != self._last_window_info["process"]:
            self._last_window_info = win_info
            bus.emit("on_active_window_changed", win_info)
            
        # 3. Idle monitor (threshold 5 minutes = 300 seconds)
        idle_time = core.api.get_user_idle_time()
        if idle_time > 300 and not self._is_idle:
            self._is_idle = True
            bus.emit("on_user_idle", idle_time)
        elif idle_time < 5 and self._is_idle:
            self._is_idle = False
            bus.emit("on_user_active", idle_time)
            
        # 4. Power Status Monitor
        power_status = core.api.get_power_status()
        if power_status != self._last_power_state and power_status["ac_line_status"] != 255:
            self._last_power_state = power_status
            bus.emit("on_power_changed", power_status)
            
        # 5. Network Monitor
        network_state = core.api.is_network_online()
        if network_state != self._last_network_state:
            self._last_network_state = network_state
            bus.emit("on_network_changed", network_state)
        
    def OnGlobalHotKey(self, event):
        core.hotkeys.process_global_hotkey(event.GetId())
        
    def RegisterCoreHotkeys(self):
        cat = "Calendar Navigation"
        
        core.hotkeys.register_action(cat, "prev_day", _("nav_prev_day"), wx.WXK_LEFT, False, lambda: self.MoveDate(days=-1))
        core.hotkeys.register_action(cat, "next_day", _("nav_next_day"), wx.WXK_RIGHT, False, lambda: self.MoveDate(days=1))
        core.hotkeys.register_action(cat, "prev_month", _("nav_prev_month"), wx.WXK_UP, False, lambda: self.MoveDate(months=-1))
        core.hotkeys.register_action(cat, "next_month", _("nav_next_month"), wx.WXK_DOWN, False, lambda: self.MoveDate(months=1))
        core.hotkeys.register_action(cat, "prev_year", _("nav_prev_year"), wx.WXK_PAGEUP, False, lambda: self.MoveDate(years=-1))
        core.hotkeys.register_action(cat, "next_year", _("nav_next_year"), wx.WXK_PAGEDOWN, False, lambda: self.MoveDate(years=1))
        
        core.hotkeys.register_action(cat, "start_of_week", _("nav_start_week"), wx.WXK_LEFT, True, self.GoStartOfWeek)
        core.hotkeys.register_action(cat, "end_of_week", _("nav_end_week"), wx.WXK_RIGHT, True, self.GoEndOfWeek)
        core.hotkeys.register_action(cat, "start_of_month", _("nav_start_month"), wx.WXK_HOME, True, self.GoStartOfMonth)
        core.hotkeys.register_action(cat, "end_of_month", _("nav_end_month"), wx.WXK_END, True, self.GoEndOfMonth)
        core.hotkeys.register_action(cat, "today", _("nav_today"), ord('D'), False, self.GoToToday)
        
        core.hotkeys.register_action("Hariku Core", "volume_down", _("nav_volume_down"), wx.WXK_F5, False, core.sounds.volume_down)
        core.hotkeys.register_action("Hariku Core", "volume_up", _("nav_volume_up"), wx.WXK_F6, False, core.sounds.volume_up)
        core.hotkeys.register_action("Hariku Core", "input_gestures", _("nav_open_prefs"), ord('P'), True, lambda: self.OnOpenPreferences(None))
        core.hotkeys.register_action("Hariku Core", "manage_extensions", _("nav_manage_ext"), ord('X'), True, lambda: self.OnManageExtensions(None))
        core.hotkeys.register_action("Hariku Core", "go_to_date", _("nav_go_to_date"), ord('G'), True, lambda: self.OnGoToDate(None))
        core.hotkeys.register_action("Hariku Core", "quit_app",    _("nav_quit_app"),    ord('Q'), True, self.ShowExitOptions)
        core.hotkeys.register_action("Hariku Core", "minimize_tray", _("nav_minimize_tray"), ord('M'), True, self.MinimizeToTray)
        core.hotkeys.register_action("Hariku Core", "show_app",    _("nav_show_app"),    ord('H'), True, self.OnToggleVisibility, default_alt=True, default_global=True)
        core.hotkeys.register_action("Hariku Core", "show_shortcuts", "Show Keyboard Shortcuts", wx.WXK_F1, False, self.OnShowShortcuts)

    def OnShowShortcuts(self):
        from ui.shortcuts_dialog import show_shortcuts
        show_shortcuts(self)

    def OnToggleVisibility(self):
        if self.IsShown() and self.IsActive():
            self.Hide()
        else:
            self.Show()
            self.Raise()
            self.SetFocus()

    def MoveDate(self, days=0, months=0, years=0):
        d = self.calendar.GetDate()
        if days != 0: d.Add(wx.DateSpan(0, 0, 0, days))
        if months != 0: d.Add(wx.DateSpan(0, months, 0, 0))
        if years != 0: d.Add(wx.DateSpan(years, 0, 0, 0))
        self._UpdateDate(d)
        
    def GoStartOfWeek(self):
        d = self.calendar.GetDate()
        while d.GetWeekDay() != wx.DateTime.Mon: d.Subtract(wx.DateSpan(0, 0, 0, 1))
        self._UpdateDate(d)
        
    def GoEndOfWeek(self):
        d = self.calendar.GetDate()
        while d.GetWeekDay() != wx.DateTime.Sun: d.Add(wx.DateSpan(0, 0, 0, 1))
        self._UpdateDate(d)
        
    def GoStartOfMonth(self):
        d = self.calendar.GetDate()
        d.SetDay(1)
        self._UpdateDate(d)
        
    def GoEndOfMonth(self):
        d = self.calendar.GetDate()
        d.SetToLastMonthDay()
        self._UpdateDate(d)
        
    def GoToToday(self, tap_count=1):
        if tap_count == 1:
            self._UpdateDate(wx.DateTime.Now())
        elif tap_count == 2:
            import datetime
            now = datetime.datetime.now()
            core.speech.speak(now.strftime("%I:%M %p"), interrupt=True)
        elif tap_count >= 3:
            import datetime
            now = datetime.datetime.now()
            day_of_year = now.timetuple().tm_yday
            week_num = now.isocalendar()[1]
            days_in_year = 366 if (now.year % 4 == 0 and now.year % 100 != 0) or (now.year % 400 == 0) else 365
            rem_days = days_in_year - day_of_year
            msg = now.strftime("%I:%M %p, %A, %B %d, %Y. ") + _("day_info").format(day=day_of_year, week=week_num, year=now.year, rem=rem_days)
            core.speech.speak(msg, interrupt=True)
        
    def _UpdateDate(self, new_date):
        self.calendar.SetDate(new_date)
        self._TriggerDateChange(new_date)

    def _handle_open_preferences(self, tab_name):
        self.OnOpenPreferences(None, tab_name=tab_name)

    def OnOpenPreferences(self, event, tab_name=None):
        from ui.preferences_dialog import PreferencesDialog
        dlg = PreferencesDialog(self, select_tab=tab_name)
        dlg.ShowModal()
        dlg.Destroy()

    def OnManageExtensions(self, event):
        from ui.extension_manager_dialog import ExtensionManagerDialog
        dlg = ExtensionManagerDialog(self)
        dlg.ShowModal()
        
        if dlg.requires_restart:
            resp = wx.MessageBox(_("restart_required_msg"),
                                 _("restart_required_title"), wx.YES_NO | wx.ICON_INFORMATION, self)
            if resp == wx.YES:
                import sys
                sys.modules['core.api'].restart_app()
        
        dlg.Destroy()

    def OnGoToDate(self, event):
        date_str = core.api.prompt_text(_("go_to_date_title"), _("go_to_date_prompt"), "")
        if date_str:
            import datetime
            try:
                if "/" in date_str:
                    d = datetime.datetime.strptime(date_str, "%d/%m/%Y")
                    date_str = d.strftime("%Y-%m-%d")
                
                success = core.api.set_selected_date(date_str)
                if not success:
                    core.api.show_message(_("error"), _("error_invalid_date_format"))
                else:
                    self.OnDateChanged(None) # Force broadcast
            except Exception as e:
                core.api.show_message(_("error"), _("error_invalid_date", error=str(e)))

    def OnCharHook(self, event):
        keycode = event.GetKeyCode()
        ctrl_down = event.ControlDown()
        
        if keycode == wx.WXK_RETURN and not ctrl_down:
            focus = wx.Window.FindFocus()
            if focus == self.calendar or focus == self:
                date_str = self.calendar.GetDate().Format("%Y-%m-%d")
                # Allow extensions to override the Enter key behavior.
                # If an extension sets payload["handled"] = True, the
                # default AddReminderDialog will NOT open.
                payload = {"date": date_str, "handled": False}
                bus.emit("on_enter_pressed", payload)
                if payload["handled"]:
                    return
                from ui.reminder_dialog import AddReminderDialog
                dlg = AddReminderDialog(self, date_str)
                dlg.ShowModal()
                dlg.Destroy()
                return
                
        if keycode == wx.WXK_SPACE and not ctrl_down:
            focus = wx.Window.FindFocus()
            # Focus now sits on self.panel because of the earlier focus-redirect trick
            if focus == self.panel or focus == self.calendar or focus == self:
                date_str = self.calendar.GetDate().Format("%Y-%m-%d")
                from core.reminders import get_reminders_for_date
                reminders = get_reminders_for_date(date_str)
                
                if not reminders:
                    speak(_("no_reminders"), interrupt=True)
                else:
                    from ui.agenda_dialog import show_agenda
                    show_agenda(self, date_str, reminders)
                return
        
        # Let the hotkey manager handle everything (including calendar arrow navigation)
        if not core.hotkeys.process_key_event(keycode, ctrl_down, event.ShiftDown(), event.AltDown(), event.MetaDown() or wx.GetKeyState(wx.WXK_WINDOWS_LEFT) or wx.GetKeyState(wx.WXK_WINDOWS_RIGHT)):
            event.Skip()

    def OnDateChanged(self, event):
        current_date = self.calendar.GetDate()
        self._TriggerDateChange(current_date)
        if event:
            event.Skip()

    def _TriggerDateChange(self, current_date):
        date_str = current_date.Format("%Y-%m-%d")
        
        from core.sounds import play_internal_sound
        play_internal_sound("move.wav")
        
        from core.reminders import get_reminders_for_date
        reminders = get_reminders_for_date(date_str)
        if reminders:
            play_internal_sound("penClick.wav")
            
        import core.api
        config = core.api.load_data("Core")
        dt_format = config.get("date_format", "%A, %d %B %Y")
        
        spoken_date = format_date(current_date, dt_format)
        speak(spoken_date, interrupt=True)
        
        bus.emit("on_date_changed", date_str)

    def MinimizeToTray(self):
        """Hide the main window to the system tray."""
        self.Hide()

    def ShowExitOptions(self):
        """Show a popup dialog with Exit / Restart / Restart Safe Mode / Minimize options."""
        dlg = ExitOptionsDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def DoQuit(self):
        bus.emit("on_unload")
        if hasattr(self, 'tb_icon'):
            self.tb_icon.RemoveIcon()
            self.tb_icon.Destroy()
        self.Destroy()

    def OnQuit(self, e):
        self.DoQuit()
        
    def OnCloseWindow(self, e):
        import sys
        config = sys.modules['core.api'].load_data("Core")
        behavior = config.get("close_behavior", "minimize")
        
        if behavior == "quit":
            self.DoQuit()
        elif behavior == "ask":
            self.ShowExitOptions()
        else:
            # Default: hide to the system tray
            self.Hide()

    # --- Help Menu Handlers ---
    def OnShowUserGuide(self, event):
        from ui.document_viewer import show_document
        show_document(self, _("menu_help_guide"), "user_guide.txt")

    def OnShowWhatsNew(self, event):
        from ui.document_viewer import show_document
        show_document(self, _("menu_help_whats_new"), "whats_new.txt")

    def OnOpenSupport(self, event):
        import webbrowser
        import core.endpoints
        webbrowser.open(core.endpoints.SUPPORT_URL)

    def OnOpenReport(self, event):
        import webbrowser
        import core.endpoints
        webbrowser.open(core.endpoints.NEW_ISSUE_URL)

    def OnShowWelcome(self, event):
        from ui.onboarding_dialog import run_onboarding
        run_onboarding()

    def OnCheckUpdate(self, event):
        import core.updater
        import threading
        threading.Thread(target=core.updater.check_for_updates, args=(True,), daemon=True).start()

    def OnShowAbout(self, event):
        from ui.about_dialog import show_about
        show_about(self)


# ---------------------------------------------------------------------------

class ExitOptionsDialog(wx.Dialog):
    """Small dialog shown when the user presses the exit hotkey or menu item."""

    def __init__(self, parent):
        super().__init__(parent, title="Exit Options",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP)
        self._parent = parent
        self._build_ui()
        self.CentreOnParent()

    def _build_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        from core.i18n import get_translator
        _ = get_translator("core")

        lbl = wx.StaticText(self, label=_("menu_exit_options"))
        lbl.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(lbl, 0, wx.ALL | wx.ALIGN_CENTER, 12)

        self.options = [
            ("minimize", _("menu_minimize_to_tray")),
            ("exit", _("menu_exit")),
            ("restart", _("menu_restart")),
            ("safe_mode", _("menu_restart_safe"))
        ]
        choices = [opt[1] for opt in self.options]

        self.cb_options = wx.ComboBox(self, choices=choices, style=wx.CB_READONLY)
        self.cb_options.SetSelection(1) # Default to 'Exit'
        vbox.Add(self.cb_options, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        hbox_btns = wx.BoxSizer(wx.HORIZONTAL)
        btn_ok = wx.Button(self, wx.ID_OK, label="OK")
        btn_ok.Bind(wx.EVT_BUTTON, self._on_ok)
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label="Cancel")
        
        # Set default button so Enter key works
        btn_ok.SetDefault()
        
        hbox_btns.Add(btn_ok, 1, wx.RIGHT, 5)
        hbox_btns.Add(btn_cancel, 1, wx.LEFT, 5)
        
        vbox.Add(hbox_btns, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)

        self.SetSizerAndFit(vbox)

    def _on_ok(self, _e):
        sel = self.cb_options.GetSelection()
        if sel < 0:
            return
            
        action = self.options[sel][0]
        self.EndModal(wx.ID_OK)
        
        if action == "minimize":
            self._parent.MinimizeToTray()
        elif action == "exit":
            self._parent.DoQuit()
        elif action == "restart":
            core.api.restart_app()
        elif action == "safe_mode":
            core.api.restart_app(safe_mode=True)
