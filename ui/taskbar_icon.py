# hariku2/ui/taskbar_icon.py
import wx
import wx.adv
from core.events import bus

class HarikuTaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        
        # Gunakan icon bawaan wx
        icon = wx.ArtProvider.GetIcon(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16))
        from core.i18n import get_translator
        _ = get_translator("core")
        self.SetIcon(icon, _("app_title"))
        
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.OnLeftDClick)
        
        # Dengarkan event perubahan tanggal untuk memperbarui tooltip
        bus.subscribe("on_date_changed", self.UpdateTooltip)
        
    def UpdateTooltip(self, date_str):
        if not self.frame or not hasattr(self.frame, 'calendar'):
            return
            
        from core.i18n import get_translator, format_date
        import core.api
        from core.reminders import get_reminders_for_date
        
        _ = get_translator("core")
        
        current_date = self.frame.calendar.GetDate()
        config = core.api.load_data("Core")
        dt_format = config.get("date_format", "%A, %d %B %Y")
        
        spoken_date = format_date(current_date, dt_format)
        
        d_str = current_date.Format("%Y-%m-%d")
        reminders = get_reminders_for_date(d_str)
        
        text = f"{_('app_title')}\n{spoken_date}"
        if reminders:
            text += f"\n{_('agenda_lbl_has_reminders', count=len(reminders))}"
            
        # Izinkan ekstensi untuk menyisipkan info mereka sendiri ke dalam tooltip
        tooltip_data = {"text": text}
        bus.emit("on_build_tray_tooltip", tooltip_data)
            
        icon = wx.ArtProvider.GetIcon(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16))
        self.SetIcon(icon, tooltip_data["text"])
        
    def CreatePopupMenu(self):
        menu = wx.Menu()
        
        from core.i18n import get_translator
        _ = get_translator("core")
        
        item_show = menu.Append(wx.ID_ANY, _("nav_show_app"))
        item_view_log = menu.Append(wx.ID_ANY, _("nav_view_log"))
        menu.AppendSeparator()
        
        # Izinkan ekstensi menyisipkan menu mereka sendiri
        bus.emit("on_build_tray_menu", menu, self.frame)
        
        # Tambahkan separator jika ekstensi menambahkan menu
        if menu.GetMenuItemCount() > 3:
            menu.AppendSeparator()

        # Minimize to tray
        item_minimize = menu.Append(wx.ID_ANY, _("menu_minimize_to_tray"))

        menu.AppendSeparator()

        # Exit Options submenu
        exitMenu = wx.Menu()
        item_exit      = exitMenu.Append(wx.ID_ANY, _("menu_exit"))
        item_restart   = exitMenu.Append(wx.ID_ANY, _("menu_restart"))
        item_safe_mode = exitMenu.Append(wx.ID_ANY, _("menu_restart_safe"))
        menu.AppendSubMenu(exitMenu, _("menu_exit_options"))
        
        self.Bind(wx.EVT_MENU, self.OnShow,    item_show)
        self.Bind(wx.EVT_MENU, self.OnViewLog, item_view_log)
        self.Bind(wx.EVT_MENU, lambda e: self.frame.MinimizeToTray(), item_minimize)
        self.Bind(wx.EVT_MENU, self.OnQuit,    item_exit)
        self.Bind(wx.EVT_MENU, lambda e: self._restart(),            item_restart)
        self.Bind(wx.EVT_MENU, lambda e: self._restart(safe_mode=True), item_safe_mode)
        
        return menu

        
    def _restart(self, safe_mode=False):
        import core.api
        self.RemoveIcon()
        self.Destroy()
        core.api.restart_app(safe_mode=safe_mode)

    def OnViewLog(self, event):
        import core.api
        core.api.open_log_viewer()
        
    def OnLeftDClick(self, event):
        if self.frame.IsIconized():
            self.frame.Iconize(False)
        if not self.frame.IsShown():
            self.frame.Show(True)
        self.frame.Raise()
        
    def OnShow(self, event):
        self.OnLeftDClick(event)
        
    def OnQuit(self, event):
        bus.emit("on_unload")
        self.RemoveIcon()
        self.Destroy()
        wx.CallAfter(self.frame.Destroy)
