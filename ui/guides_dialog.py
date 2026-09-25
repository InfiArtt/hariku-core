# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Guides (core 2.11). Help, Extension guides... lists the installed extensions
that have a guide: the label, then the list, then Open and Close. Enter (or
Open) opens the selected guide in the web browser, and the list stays open
for the next one; Escape closes it.

show_guide() is how every way in opens a guide: this list, the Extension
Manager's Guide button, Help, User Guide and Aruna ("panduan orbit"). The
page opens in the web browser (core.guides explains why); when the browser
can't be opened, the guide shows as plain text in a window instead.
"""
import wx

import core.guides
import core.ui_scale
from core.core_panels import _labeled, _speak
from core.i18n import apply_rtl_layout, get_translator

_ = get_translator("core")


def _title_of(ext_id, text):
    if ext_id == core.guides.CORE_ID:
        return _("menu_help_guide")
    return core.guides.guide_title(text) or ext_id


def _text_window(parent, title, text):
    from ui.document_viewer import show_text as show
    show(parent, title, text)


def show_guide(parent, ext_id, opener=None, show_text=None):
    """Open a guide (core.guides.CORE_ID: the User Guide). Returns True when
    it opened, in the browser or as text."""
    if (opener or core.guides.open_guide)(ext_id):
        return True
    path = core.guides.find_guide(ext_id)
    text = core.guides.read_guide(path) if path else None
    if text is None:
        _speak(_("guide_open_failed"))
        return False
    (show_text or _text_window)(parent, _title_of(ext_id, text), text)
    return True


class GuidesDialog(wx.Dialog):
    """Help, Extension guides...: the installed extensions with a guide."""

    def __init__(self, parent, guides=None, opener=None):
        super().__init__(parent, title=_("guides_title"), size=(460, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.guides = core.guides.list_guides() if guides is None else list(guides)
        self._opener = opener or (lambda ext_id: show_guide(self, ext_id))

        sizer = wx.BoxSizer(wx.VERTICAL)
        label = _("guides_list_label") if self.guides else _("guides_none")
        self.list = _labeled(self, sizer, label, lambda: wx.ListBox(
            self, choices=[name for _id, name in self.guides], style=wx.LB_SINGLE),
            proportion=1)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.AddStretchSpacer()
        self.btn_open = wx.Button(self, wx.ID_OPEN, _("guides_btn_open"))
        self.btn_open.Bind(wx.EVT_BUTTON, lambda evt: self.open_selected())
        row.Add(self.btn_open, 0, wx.RIGHT, 8)
        self.btn_close = wx.Button(self, wx.ID_CLOSE, _("guides_btn_close"))
        self.btn_close.Bind(wx.EVT_BUTTON, lambda evt: self._close())
        row.Add(self.btn_close, 0)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(sizer)

        self.SetEscapeId(wx.ID_CLOSE)
        self.btn_open.SetDefault()
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda evt: self.open_selected())
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.Bind(wx.EVT_CLOSE, lambda evt: self._close())

        if self.guides:
            self.list.SetSelection(0)
        self.btn_open.Enable(bool(self.guides))

        apply_rtl_layout(self)
        try:
            core.ui_scale.apply_appearance(self)
        except Exception:
            pass
        self.CentreOnParent()
        self.list.SetFocus()
        # Again once shown, so the list, not the default button, has the focus.
        wx.CallAfter(self._focus_list)

    def _focus_list(self):
        if self and self.IsShown():
            self.list.SetFocus()

    def selected(self):
        """(id, name) of the selected guide, or None."""
        index = self.list.GetSelection()
        return self.guides[index] if 0 <= index < len(self.guides) else None

    def open_selected(self):
        chosen = self.selected()
        if chosen is None:
            return False
        return self._opener(chosen[0])

    def _on_key(self, event):
        # Enter on the list opens the guide (a list box doesn't press the
        # default button everywhere).
        if (event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
                and wx.Window.FindFocus() == self.list):
            self.open_selected()
            return
        event.Skip()

    def _close(self):
        if self.IsModal():
            self.EndModal(wx.ID_CLOSE)
        else:
            self.Hide()


def show_guides(parent):
    """Help, Extension guides...: the list, modal."""
    dlg = GuidesDialog(parent)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()
