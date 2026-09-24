# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import ctypes
import logging
import time

import wx
import core.preferences
import core.ui_scale
from ui.input_gestures_panel import InputGesturesPanel
from core.i18n import get_translator

_ = get_translator("core")

logger = logging.getLogger(__name__)

# Pages are built when first needed. While the user arrows through the page
# list, building every page passed over made it stutter, so a page is built
# once the selection has settled for SETTLE_MS; the rest are built in the
# background, one at a time, whenever the keyboard has been idle for IDLE_MS.
SETTLE_MS = 200
IDLE_MS = 700
BACKGROUND_GAP_MS = 60


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _ms_since_input():
    """Milliseconds since the last keyboard or mouse input (no hook), or a
    large number when Windows can't say."""
    try:
        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 1 << 30
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    except Exception:
        return 1 << 30


class PreferencesDialog(wx.Dialog):
    def __init__(self, parent, select_tab=None):
        super().__init__(parent, title=_("dlg_prefs_title"), size=(800, 500))
        
        self.panels = []           # one entry per page, in page order
        self.select_tab = select_tab
        self._realizing = []       # holders of pages being built right now
        self._settle_timer = None
        self._background_timer = None
        self._last_page_change = 0.0
        self.InitUI()
        self.CentreOnParent()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # We use a Treebook to have a left-side navigation
        self.treebook = wx.Treebook(self, style=wx.BK_DEFAULT)
        
        # Note: General Settings is now injected automatically from core.core_panels
        
        # 2. Core Settings (Input Gestures)
        input_panel = InputGesturesPanel(self.treebook)
        self.treebook.AddPage(input_panel, _("prefs_tab_input"))
        self.panels.append({"panel": input_panel, "apply": input_panel.ApplyChanges})
        
        # 2. Extension Settings. Each page is built the first time it is shown:
        # building every page up front made Preferences slow to open, and a
        # screen reader walks every control of a dialog when it appears.
        registered = core.preferences.get_all_panels()
        for category, items in registered.items():
            for item in items:
                page_title = item['name'] if item['name'] else category
                holder = wx.Panel(self.treebook)
                holder.SetSizer(wx.BoxSizer(wx.VERTICAL))
                self.treebook.AddPage(holder, page_title)
                self.panels.append({"panel": None, "holder": holder, "title": page_title,
                                    "create": item["create"], "apply": item["apply"]})

        vbox.Add(self.treebook, 1, wx.EXPAND | wx.ALL, 10)
        
        if self.select_tab:
            for i in range(self.treebook.GetPageCount()):
                if self.select_tab.lower() in self.treebook.GetPageText(i).lower():
                    self.treebook.SetSelection(i)
                    break
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_ok = wx.Button(self, id=wx.ID_OK, label=_("prefs_btn_ok", default="OK"))
        self.btn_apply = wx.Button(self, id=wx.ID_APPLY, label=_("prefs_btn_apply", default="Apply"))
        self.btn_cancel = wx.Button(self, id=wx.ID_CANCEL, label=_("prefs_btn_cancel", default="Cancel"))
        
        hbox.AddStretchSpacer()
        hbox.Add(self.btn_ok, 0, wx.RIGHT, 10)
        hbox.Add(self.btn_cancel, 0, wx.RIGHT, 10)
        hbox.Add(self.btn_apply, 0)
        
        vbox.Add(hbox, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(vbox)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        # Large text and high contrast for every page, including extension panels
        # (pages built later get it in _realize).
        core.ui_scale.apply_appearance(self)
        self._realize(self.treebook.GetSelection())
        self.treebook.Bind(wx.EVT_TREEBOOK_PAGE_CHANGED, self._on_page_changed)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        self._background_timer = wx.CallLater(IDLE_MS, self._build_in_background)

        self.Bind(wx.EVT_BUTTON, self.OnOK, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self.OnApply, id=wx.ID_APPLY)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnCharHook)
        
        # Track dirty state
        self.is_dirty = False
        self.Bind(wx.EVT_TEXT, self.MarkDirty)
        self.Bind(wx.EVT_CHECKBOX, self.MarkDirty)
        self.Bind(wx.EVT_RADIOBUTTON, self.MarkDirty)
        self.Bind(wx.EVT_COMBOBOX, self.MarkDirty)
        self.Bind(wx.EVT_CHOICE, self.MarkDirty)
        
        # Reset dirty state after initial panel population triggers
        wx.CallAfter(self.ResetDirty)
        
    def MarkDirty(self, event):
        # A page filling in its own values while it is built isn't a change.
        if not self._inside_page_being_built(event.GetEventObject()):
            self.is_dirty = True
        event.Skip()

    def _inside_page_being_built(self, window):
        while window is not None and self._realizing:
            if any(window is holder for holder in self._realizing):
                return True
            window = window.GetParent()
        return False

    def _on_page_changed(self, event):
        # Build the page once the user stops on it; focus stays in the page list.
        self._last_page_change = time.monotonic()
        if self._settle_timer is not None:
            self._settle_timer.Stop()
        self._settle_timer = wx.CallLater(SETTLE_MS, self._realize_selected)
        event.Skip()

    def _realize_selected(self):
        self._settle_timer = None
        try:
            self._realize(self.treebook.GetSelection())
        except RuntimeError:
            pass   # the dialog closed meanwhile

    def _build_in_background(self):
        """Build the next unbuilt page while the user isn't typing or moving
        through the list, then come back for the one after it."""
        self._background_timer = None
        try:
            if not self:
                return
            since_change = (time.monotonic() - self._last_page_change) * 1000
            if (self._settle_timer is not None or since_change < IDLE_MS
                    or _ms_since_input() < IDLE_MS):
                self._background_timer = wx.CallLater(IDLE_MS, self._build_in_background)
                return
            index = next((i for i, p in enumerate(self.panels)
                          if p["panel"] is None and not p.get("failed")), None)
            if index is None:
                return
            focus = wx.Window.FindFocus()
            self._realize(index)
            # A page must never take the focus while it is built unseen.
            if focus is not None and wx.Window.FindFocus() is not focus:
                focus.SetFocus()
            self._background_timer = wx.CallLater(BACKGROUND_GAP_MS, self._build_in_background)
        except RuntimeError:
            pass   # the dialog closed meanwhile

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            for timer in (self._settle_timer, self._background_timer):
                if timer is not None:
                    timer.Stop()
            self._settle_timer = self._background_timer = None
        event.Skip()

    def _realize(self, index):
        """Build page `index` if it hasn't been built yet."""
        if not 0 <= index < len(self.panels):
            return
        entry = self.panels[index]
        if entry["panel"] is not None or entry.get("failed"):
            return
        holder = entry["holder"]
        self._realizing.append(holder)
        try:
            panel = entry["create"](holder)
            holder.GetSizer().Add(panel, 1, wx.EXPAND)
            entry["panel"] = panel
            from core.i18n import apply_rtl_layout
            apply_rtl_layout(panel)
            core.ui_scale.apply_appearance(panel)
        except Exception as e:
            entry["failed"] = True
            logger.error(f"Failed to create settings panel '{entry['title']}': {e}")
            holder.GetSizer().Add(wx.StaticText(holder, label=_("prefs_page_failed")),
                                  0, wx.ALL, 10)
        finally:
            holder.Layout()
            # Events a page posts while filling in arrive later; ignore those too.
            wx.CallAfter(self._end_realizing, holder)

    def _end_realizing(self, holder):
        try:
            self._realizing.remove(holder)
        except ValueError:
            pass

    def realize_all(self):
        """Build every page now (checks that look at all pages use this)."""
        for index in range(len(self.panels)):
            self._realize(index)
        
    def ResetDirty(self):
        self.is_dirty = False
        
    def OnCharHook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close() # Triggers OnClose (shows prompt if dirty)
            return
        if event.GetKeyCode() == wx.WXK_TAB and self._settle_timer is not None:
            # Tab right after arrowing: build the page now, so Tab lands in it.
            self._settle_timer.Stop()
            self._realize_selected()
        event.Skip()
            
    def _validate(self):
        """A page with ValidateChanges() returning (message, control) keeps the
        dialog open: its page is shown, the message said, and focus put on the
        control to fix. Nothing is saved."""
        for index, p in enumerate(self.panels):
            if p["panel"] is None:
                continue   # never shown, so nothing changed
            check = getattr(p["panel"], "ValidateChanges", None)
            if check is None:
                continue
            try:
                problem = check()
            except Exception as e:
                logger.error(f"Error validating preferences: {e}")
                continue
            if problem:
                message, ctrl = problem
                self.treebook.SetSelection(index)
                wx.MessageBox(message, _("error"), wx.OK | wx.ICON_ERROR, self)
                ctrl.SetFocus()
                return False
        return True

    def OnApply(self, event):
        if not self._validate():
            return False
        for p in self.panels:
            if p["panel"] is not None and p["apply"]:
                try:
                    p["apply"]()
                except Exception as e:
                    logger.error(f"Error applying preferences: {e}")
        # A changed text size or contrast setting shows here immediately too.
        core.ui_scale.apply_appearance(self)
        self.Layout()
        self.is_dirty = False
        # Do not close window
        return True

    def OnOK(self, event):
        if self.OnApply(None) is False:
            return   # a page refused its input; the dialog stays open on it
        self.EndModal(wx.ID_OK)
        
    def OnCancel(self, event):
        # Cancel explicitly clicked -> No prompt
        self.EndModal(wx.ID_CANCEL)

    def OnClose(self, event):
        if self.is_dirty:
            dlg = wx.MessageDialog(self, _("dlg_unsaved_msg", default="You have unsaved settings. Do you want to save them before exiting?"), 
                                   _("dlg_unsaved_title", default="Unsaved Settings"), 
                                   wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
            res = dlg.ShowModal()
            if res == wx.ID_YES:
                self.OnOK(None)
            elif res == wx.ID_NO:
                self.EndModal(wx.ID_CANCEL)
            else:
                if event.CanVeto():
                    event.Veto()
                return
        else:
            self.EndModal(wx.ID_CANCEL)
