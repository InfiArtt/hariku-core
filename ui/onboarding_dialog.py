import wx
import wx.adv
import core.preferences
import core.store
import core.api
import os
import sys
from core.speech import speak
from core.i18n import get_translator

_ = get_translator("core")



class OnboardingWizard(wx.adv.Wizard):
    def __init__(self, parent):
        super().__init__(parent, title=_("dlg_onboard_title"))
        
        self.page1 = self.CreatePage1()
        self.page2 = self.CreatePage2()
        self.page3 = self.CreatePage3()
        self.page4 = self.CreatePage4()
        
        wx.adv.WizardPageSimple.Chain(self.page1, self.page2)
        wx.adv.WizardPageSimple.Chain(self.page2, self.page3)
        wx.adv.WizardPageSimple.Chain(self.page3, self.page4)
        
        self.GetPageAreaSizer().Add(self.page1)
        self.Bind(wx.adv.EVT_WIZARD_PAGE_CHANGED, self.OnPageChanged)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        
    def CreatePage1(self):
        page = wx.adv.WizardPageSimple(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        title = wx.StaticText(page, label=_("onb_p1_title"))
        font = title.GetFont()
        font.SetPointSize(16)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        sizer.Add(title, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        msg = _("onb_p1_msg")
               
        text = wx.TextCtrl(page, value=msg, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE)
        sizer.Add(text, 1, wx.ALL | wx.EXPAND, 15)
        
        page.SetSizer(sizer)
        return page
        
    def CreatePage2(self):
        page = wx.adv.WizardPageSimple(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        title = wx.StaticText(page, label=_("onb_p2_title"))
        font = title.GetFont()
        font.SetPointSize(16)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        sizer.Add(title, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        msg = _("onb_p2_msg")
               
        text = wx.TextCtrl(page, value=msg, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE)
        sizer.Add(text, 1, wx.ALL | wx.EXPAND, 15)
        
        page.SetSizer(sizer)
        return page
        
    def CreatePage3(self):
        page = wx.adv.WizardPageSimple(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        title = wx.StaticText(page, label=_("onb_p3_title"))
        font = title.GetFont()
        font.SetPointSize(14)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        sizer.Add(title, 0, wx.ALL, 10)
        
        msg = _("onb_p3_msg_name")
        sizer.Add(wx.StaticText(page, label=msg), 0, wx.LEFT | wx.RIGHT, 10)
        
        self.txt_name = wx.TextCtrl(page)
        sizer.Add(self.txt_name, 0, wx.ALL | wx.EXPAND, 10)
        
        sizer.AddSpacer(20)
        
        self.chk_autostart = wx.CheckBox(page, label=_("onb_p3_chk_auto"))
        self.chk_autostart.SetValue(True)
        sizer.Add(self.chk_autostart, 0, wx.ALL, 10)
        
        page.SetSizer(sizer)
        return page
        
    def CreatePage4(self):
        page = wx.adv.WizardPageSimple(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        title = wx.StaticText(page, label=_("onb_p4_title"))
        font = title.GetFont()
        font.SetPointSize(14)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        sizer.Add(title, 0, wx.ALL, 10)
        
        desc = _("onb_p4_desc")
        text_desc = wx.StaticText(page, label=desc)
        text_desc.Wrap(400)
        sizer.Add(text_desc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        self.rb_basic = wx.RadioButton(page, label=_("onb_p4_rb_1"), style=wx.RB_GROUP)
        self.rb_normal = wx.RadioButton(page, label=_("onb_p4_rb_2"))
        self.rb_advanced = wx.RadioButton(page, label=_("onb_p4_rb_3"))
        self.rb_super = wx.RadioButton(page, label=_("onb_p4_rb_4"))
        
        self.rb_normal.SetValue(True)
        
        # Sembunyikan opsi setup untuk sementara (paksa "Normal" dengan konfigurasi default)
        self.rb_basic.Hide()
        self.rb_normal.Hide()
        self.rb_advanced.Hide()
        self.rb_super.Hide()
        
        # Tambahkan teks informasi tambahan (opsional)
        info = wx.StaticText(page, label="Hariku will install the recommended extensions for you automatically.")
        sizer.Add(info, 0, wx.ALL, 10)
        
        # Opsi Telemetri (Opt-out)
        tel_box = wx.StaticBox(page, label="Public Telemetry Data (Opt-Out)")
        tel_sizer = wx.StaticBoxSizer(tel_box, wx.VERTICAL)
        
        tel_info = wx.StaticText(tel_box, label="Anonymous usage statistics are currently disabled: the previous statistics server was retired, so no data is collected or sent. This setting is kept for when telemetry returns.")
        tel_info.Wrap(380)
        tel_sizer.Add(tel_info, 0, wx.ALL, 5)
        
        self.chk_telemetry = wx.CheckBox(tel_box, label="Share my anonymous usage data publicly")
        self.chk_telemetry.SetValue(True) # ON by default
        tel_sizer.Add(self.chk_telemetry, 0, wx.ALL, 5)
        
        sizer.Add(tel_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 10)
        
        page.SetSizer(sizer)
        return page
        
    def OnPageChanged(self, event):
        page = event.GetPage()
        if page == self.page1:
            speak(_("onb_speak_p1"), interrupt=True)
        elif page == self.page2:
            speak(_("onb_speak_p2"), interrupt=True)
        elif page == self.page3:
            speak(_("onb_speak_p3"), interrupt=True)
            self.txt_name.SetFocus()
        elif page == self.page4:
            speak(_("onb_speak_p4"), interrupt=True)
            self.rb_normal.SetFocus()

def run_onboarding():
    wizard = OnboardingWizard(None)
    wizard.FitToPage(wizard.page1)
    
    if wizard.RunWizard(wizard.page1):
        name = wizard.txt_name.GetValue().strip() or "User"
        autostart = wizard.chk_autostart.GetValue()
        
        preset = "Basic"
        if wizard.rb_normal.GetValue(): preset = "Normal"
        elif wizard.rb_advanced.GetValue(): preset = "Advanced"
        elif wizard.rb_super.GetValue(): preset = "Super"
        
        wizard.Destroy()
        
        # Save preferences
        config = core.api.load_data("Core")
        config["user_name"] = name
        config["onboarding_completed"] = True
        config["auto_start"] = autostart
        config["telemetry_enabled"] = wizard.chk_telemetry.GetValue()
        core.api.save_data("Core", config)
        
        # Apply autostart to Windows Registry
        core.api.set_autostart(autostart)
        
        if preset != "Basic":
            # Show downloading dialog
            dlg = wx.ProgressDialog(_("onb_dlg_dl_title"), _("onb_dlg_dl_msg", preset=preset), maximum=100, style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
            dlg.Pulse(_("onb_dlg_dl_pulse1"))
            
            registry = core.store.fetch_registry()
            
            # Install semua ekstensi kecuali yang diblacklist
            excluded_extensions = ["developer_toolkit", "wikipedia_reader", "window_teleporter"]
            extensions_to_download = []
            
            for item in registry:
                if item["id"] not in excluded_extensions:
                    extensions_to_download.append(item["id"])
            
            for ext_id in extensions_to_download:
                dlg.Pulse(_("onb_dlg_dl_pulse2", ext=ext_id))
                url = None
                for item in registry:
                    if item["id"] == ext_id:
                        url = item["download_url"]
                        break
                
                if url:
                    success = core.store.download_extension(ext_id, url)
                    if success:
                        full_path = os.path.join(core.extension_manager.USER_EXTENSIONS_DIR, f"{ext_id}.hrk")
                        core.extension_manager.load_zipped_extension(full_path)
            
            dlg.Update(100, _("onb_dlg_dl_done"))
            dlg.Destroy()
            
        return True
    else:
        wizard.Destroy()
        return False
