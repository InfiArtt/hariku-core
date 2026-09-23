# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import core.extension_manager
import core.store
import core.api
from core.i18n import get_translator

_ = get_translator("core")

class InstalledPanel(wx.Panel):
    def __init__(self, parent, dialog):
        super().__init__(parent)
        self.dialog = dialog
        self.extensions = []
        self.InitUI()
        self.LoadData()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, _("ext_col_name"),    width=150)
        self.list_ctrl.InsertColumn(1, _("ext_col_version"), width=80)
        self.list_ctrl.InsertColumn(2, _("ext_col_author"),  width=110)
        self.list_ctrl.InsertColumn(3, _("ext_col_status"),  width=80)
        self.list_ctrl.InsertColumn(4, _("ext_col_type"),    width=80)
        self.list_ctrl.InsertColumn(5, "Update",             width=100)
        
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self.list_ctrl)
        vbox.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        self.desc_text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 60))
        vbox.Add(self.desc_text, 0, wx.EXPAND | wx.ALL, 5)

        hbox = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_toggle = wx.Button(self, label=_("ext_btn_toggle"))
        self.btn_toggle.Disable()
        self.Bind(wx.EVT_BUTTON, self.OnToggle, self.btn_toggle)
        
        self.btn_uninstall = wx.Button(self, label=_("ext_btn_uninstall"))
        self.btn_uninstall.Disable()
        self.Bind(wx.EVT_BUTTON, self.OnUninstall, self.btn_uninstall)
        
        self.btn_update = wx.Button(self, label="Update Selected")
        self.btn_update.Disable()
        self.Bind(wx.EVT_BUTTON, self.OnUpdate, self.btn_update)
        
        hbox.Add(self.btn_toggle,    0, wx.RIGHT, 10)
        hbox.Add(self.btn_uninstall, 0, wx.RIGHT, 10)
        hbox.Add(self.btn_update,    0)
        
        vbox.Add(hbox, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(vbox)
        
    def LoadData(self):
        self.list_ctrl.DeleteAllItems()
        self.extensions = core.extension_manager.get_installed_extensions_info()
        
        # Build update map from store registry (non-blocking: use cached result if any)
        try:
            import sys
            _store = sys.modules.get('core.store')
            if not _store:
                import core.store as _store
            
            registry = _store.fetch_registry()
            self._update_map = {
                e["id"]: e for e in registry
                if _store._parse_version(e.get("version", "0")) >
                   _store._parse_version(
                       core.extension_manager.LOADED_EXTENSIONS.get(e["id"], {}).get("manifest", {}).get("version", "0")
                   )
            }
        except Exception:
            self._update_map = {}
        
        for idx, ext in enumerate(self.extensions):
            badge = " [Official]" if ext.get("is_official") else ""
            self.list_ctrl.InsertItem(idx, f"{ext['name']}{badge}")
            
            # Show version with upgrade arrow if update available
            upd = self._update_map.get(ext["id"])
            ver_str = ext["version"]
            if upd:
                ver_str = f"{ext['version']} → {upd['version']}"
            self.list_ctrl.SetItem(idx, 1, ver_str)
            
            self.list_ctrl.SetItem(idx, 2, ext["author"])
            status_text = _("ext_status_enabled") if ext["is_enabled"] else _("ext_status_disabled")
            self.list_ctrl.SetItem(idx, 3, status_text)
            type_text = _("ext_status_unpacked") if ext["is_unpacked"] else _("ext_status_zipped")
            self.list_ctrl.SetItem(idx, 4, type_text)
            self.list_ctrl.SetItem(idx, 5, "⬆ Available" if upd else "")
            self.list_ctrl.SetItemData(idx, idx)

    def OnItemSelected(self, event):
        idx = event.GetIndex()
        ext = self.extensions[idx]
        self.desc_text.SetValue(ext["description"])
        self.btn_toggle.Enable()
        self.btn_toggle.SetLabel(_("ext_btn_disable") if ext["is_enabled"] else _("ext_btn_enable"))
        self.btn_uninstall.Enable()
        # Enable update button only if this extension has an update
        if hasattr(self, '_update_map') and ext["id"] in self._update_map:
            self.btn_update.Enable()
        else:
            self.btn_update.Disable()
        
    def OnToggle(self, event):
        idx = self.list_ctrl.GetFirstSelected()
        if idx < 0: return
        ext = self.extensions[idx]
        new_status = not ext["is_enabled"]
        
        core.extension_manager.toggle_extension(ext["id"], new_status)
        ext["is_enabled"] = new_status
        self.dialog.requires_restart = True
        
        self.list_ctrl.SetItem(idx, 3, _("ext_status_enabled") if new_status else _("ext_status_disabled"))
        self.btn_toggle.SetLabel(_("ext_btn_disable") if new_status else _("ext_btn_enable"))
        
    def OnUninstall(self, event):
        idx = self.list_ctrl.GetFirstSelected()
        if idx < 0: return
        ext = self.extensions[idx]
        
        dlg = wx.MessageDialog(self, _("ext_msg_uninstall_confirm", name=ext['name']), 
                               _("ext_title_uninstall"), wx.YES_NO | wx.ICON_WARNING)
        if dlg.ShowModal() == wx.ID_YES:
            success = core.extension_manager.uninstall_extension(ext["id"])
            if success:
                self.dialog.requires_restart = True
                self.btn_toggle.Disable()
                self.btn_uninstall.Disable()
                self.btn_update.Disable()
                self.desc_text.SetValue("")
                self.LoadData()
            else:
                wx.MessageBox(_("ext_msg_uninstall_failed"), _("error"), wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def OnUpdate(self, event):
        idx = self.list_ctrl.GetFirstSelected()
        if idx < 0: return
        ext  = self.extensions[idx]
        upd  = self._update_map.get(ext["id"])
        if not upd: return

        self.btn_update.Disable()
        self.btn_update.SetLabel("Updating...")
        wx.Yield()

        # core.store is already imported globally
        ok = core.store.download_extension(upd["id"], upd["download_url"])
        if ok:
            self.dialog.requires_restart = True
            wx.MessageBox(
                f"{ext['name']} updated to v{upd['version']}.\nRestart Hariku to apply.",
                "Update Successful", wx.OK | wx.ICON_INFORMATION
            )
            self.LoadData()
        else:
            wx.MessageBox("Update failed. Please try again.", _("error"), wx.OK | wx.ICON_ERROR)
        self.btn_update.SetLabel("Update Selected")


class StorePanel(wx.Panel):
    def __init__(self, parent, dialog):
        super().__init__(parent)
        self.dialog = dialog
        self.store_extensions = []
        self.InitUI()
        self.LoadStore()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, _("ext_col_name"), width=150)
        self.list_ctrl.InsertColumn(1, _("ext_col_version"), width=60)
        self.list_ctrl.InsertColumn(2, _("ext_col_author"), width=120)
        self.list_ctrl.InsertColumn(3, _("ext_col_status"), width=250)
        
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self.list_ctrl)
        vbox.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        self.desc_text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 60))
        vbox.Add(self.desc_text, 0, wx.EXPAND | wx.ALL, 5)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_install = wx.Button(self, label=_("ext_btn_install"))
        self.btn_install.Disable()
        self.Bind(wx.EVT_BUTTON, self.OnInstall, self.btn_install)
        
        self.btn_refresh = wx.Button(self, label=_("ext_btn_refresh"))
        self.Bind(wx.EVT_BUTTON, self.OnRefresh, self.btn_refresh)
        
        hbox.Add(self.btn_install, 0, wx.RIGHT, 10)
        hbox.Add(self.btn_refresh, 0)
        
        vbox.Add(hbox, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(vbox)
        
    def LoadStore(self):
        self.list_ctrl.DeleteAllItems()
        self.store_extensions = core.store.fetch_registry()
        
        installed = {ext["id"]: ext["version"] for ext in core.extension_manager.get_installed_extensions_info()}
        
        for idx, ext in enumerate(self.store_extensions):
            author = ext.get("author", "").strip().lower()
            badge = " [Official]" if author == "rafli" else ""
            self.list_ctrl.InsertItem(idx, f"{ext['name']}{badge}")
            self.list_ctrl.SetItem(idx, 1, ext["version"])
            self.list_ctrl.SetItem(idx, 2, ext["author"])
            
            status = _("ext_status_not_installed")
            if ext["id"] in installed:
                if installed[ext["id"]] == ext["version"]:
                    status = _("ext_status_installed_up_to_date")
                else:
                    status = _("ext_status_update_available", version=installed[ext['id']])
            
            self.list_ctrl.SetItem(idx, 3, status)
            self.list_ctrl.SetItemData(idx, idx)

    def OnRefresh(self, event):
        self.LoadStore()
        self.btn_install.Disable()
        self.desc_text.SetValue(_("ext_msg_refreshed"))

    def OnItemSelected(self, event):
        idx = event.GetIndex()
        ext = self.store_extensions[idx]
        self.desc_text.SetValue(ext.get("description", ""))
        
        installed = {e["id"]: e["version"] for e in core.extension_manager.get_installed_extensions_info()}
        
        self.btn_install.Enable()
        if ext["id"] in installed:
            if installed[ext["id"]] == ext["version"]:
                self.btn_install.Disable()
                self.btn_install.SetLabel(_("ext_status_installed_up_to_date"))
            else:
                self.btn_install.SetLabel(_("ext_btn_update"))
        else:
            self.btn_install.SetLabel(_("ext_btn_install"))
            
    def OnInstall(self, event):
        idx = self.list_ctrl.GetFirstSelected()
        if idx < 0: return
        ext = self.store_extensions[idx]
        
        self.btn_install.Disable()
        self.btn_install.SetLabel(_("ext_btn_downloading"))
        wx.Yield() 
        
        success = core.store.download_extension(ext["id"], ext["download_url"])
        if success:
            self.dialog.requires_restart = True
            wx.MessageBox(_("ext_msg_download_success", name=ext['name']), _("ext_title_success"), wx.OK | wx.ICON_INFORMATION)
            self.LoadStore()
            # Also refresh the Installed tab
            self.dialog.installed_panel.LoadData()
        else:
            wx.MessageBox(_("ext_msg_download_failed"), _("error"), wx.OK | wx.ICON_ERROR)
            self.btn_install.Enable()
            self.btn_install.SetLabel(_("ext_btn_install"))


class ExtensionManagerDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("dlg_ext_mgr_title"), size=(800, 500))
        self.requires_restart = False
        self.InitUI()
        self.CentreOnParent()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.notebook = wx.Notebook(self)
        self.installed_panel = InstalledPanel(self.notebook, self)
        self.store_panel = StorePanel(self.notebook, self)
        
        self.notebook.AddPage(self.installed_panel, _("ext_tab_installed"))
        self.notebook.AddPage(self.store_panel, _("ext_tab_store"))
        
        vbox.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 10)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.AddStretchSpacer()
        btn_close = wx.Button(self, label=_("ext_btn_close"))
        self.Bind(wx.EVT_BUTTON, self.OnCloseButton, btn_close)
        hbox.Add(btn_close, 0)
        
        vbox.Add(hbox, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(vbox)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        
    def OnCloseButton(self, event):
        self.EndModal(wx.ID_OK)
        
    def OnClose(self, event):
        self.EndModal(wx.ID_OK)
