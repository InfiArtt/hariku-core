import wx
import core.reminders
import datetime
from core.i18n import get_translator

_ = get_translator("core")

class AddReminderDialog(wx.Dialog):
    def __init__(self, parent, date_str):
        super().__init__(parent, title=_("dlg_reminder_title"), size=(400, 250))
        self.date_str = date_str
        self.InitUI()
        self.CentreOnParent()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl_date = wx.StaticText(self, label=_("rem_lbl_date", date=self.date_str))
        lbl_date.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(lbl_date, 0, wx.ALL, 10)
        
        # Title
        vbox.Add(wx.StaticText(self, label=_("rem_lbl_title")), 0, wx.LEFT | wx.RIGHT, 10)
        self.txt_title = wx.TextCtrl(self)
        vbox.Add(self.txt_title, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Time
        vbox.Add(wx.StaticText(self, label=_("rem_lbl_time")), 0, wx.LEFT | wx.RIGHT, 10)
        
        # Default time is current time + 1 min
        now = datetime.datetime.now()
        default_time = (now + datetime.timedelta(minutes=1)).strftime("%H:%M")
        
        self.txt_time = wx.TextCtrl(self, value=default_time)
        vbox.Add(self.txt_time, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Buttons
        hbox = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, label=_("rem_btn_save"))
        btn_ok.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("rem_btn_cancel"))
        hbox.AddButton(btn_ok)
        hbox.AddButton(btn_cancel)
        hbox.Realize()
        
        vbox.Add(hbox, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        self.SetSizer(vbox)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        
        btn_ok.Bind(wx.EVT_BUTTON, self.OnSave)
        
    def OnSave(self, event):
        title = self.txt_title.GetValue().strip()
        time_str = self.txt_time.GetValue().strip()
        
        if not title:
            wx.MessageBox(_("rem_msg_empty_title"), _("error"), wx.ICON_ERROR)
            return
            
        try:
            datetime.datetime.strptime(time_str, "%H:%M")
        except ValueError:
            wx.MessageBox(_("rem_msg_invalid_time"), _("error"), wx.ICON_ERROR)
            return
            
        core.reminders.add_reminder(title, self.date_str, time_str)
        from core.speech import speak
        speak(_("rem_msg_saved"))
        self.EndModal(wx.ID_OK)
