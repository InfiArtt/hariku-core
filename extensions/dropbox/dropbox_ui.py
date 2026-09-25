# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The Dropbox page in Preferences: the account (Connect or Disconnect, and
who is connected), the Code field for signing in by hand (only shown when
the browser can't come back to Hariku by itself), the Dropbox folder on
this computer, what to announce, and sounds.

Every label is created right before the control it names (screen readers
name a control after the static text created just before it; SetName
doesn't change that). Nothing here moves the focus.
"""

import wx

from dropbox_text import _

_BORDER = 10

CHECKS = (("progress", "chk_progress"), ("up_to_date", "chk_up_to_date"),
          ("others", "chk_others"), ("shared", "chk_shared"), ("sounds", "chk_sounds"))


def _plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def _labeled(parent, sizer, label, make):
    """A label, then the control it names, with the same accessible name."""
    static = wx.StaticText(parent, label=label)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return static, ctrl


def _note(parent, sizer, label, width=520):
    static = wx.StaticText(parent, label=label)
    static.Wrap(width)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    return static


def _alive(window):
    try:
        return bool(window) and not window.IsBeingDeleted()
    except RuntimeError:
        return False


class DropboxPanel(wx.Panel):
    """`actions` has view() -> {"account", "button", "button_enabled",
    "code", "folder"}, press(), give_code(text), add_listener(fn) and
    remove_listener(fn)."""

    def __init__(self, parent, settings, actions):
        super().__init__(parent)
        self.actions = actions
        view = actions.view()
        sizer = wx.BoxSizer(wx.VERTICAL)
        _label, self.txt_account = _labeled(
            self, sizer, _("lbl_account"),
            lambda: wx.TextCtrl(self, value=view["account"], style=wx.TE_READONLY))
        self.btn_connect = wx.Button(self, label=view["button"])
        sizer.Add(self.btn_connect, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        self.lbl_code, self.txt_code = _labeled(
            self, sizer, _("lbl_code"),
            lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER))
        self.btn_code = wx.Button(self, label=_("btn_use_code"))
        sizer.Add(self.btn_code, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        _label, self.txt_folder = _labeled(
            self, sizer, _("lbl_folder"),
            lambda: wx.TextCtrl(self, value=view["folder"], style=wx.TE_READONLY))
        self.checks = {}
        for name, label in CHECKS:
            box = wx.CheckBox(self, label=_(label))
            box.SetValue(bool(settings.get(name, True)))
            sizer.Add(box, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
            self.checks[name] = box
        _note(self, sizer, _("note_link"))
        _note(self, sizer, _("note_privacy"))
        sizer.AddSpacer(_BORDER)
        self.SetSizer(sizer)

        # (Preferences applies the RTL layout and the font scale to its pages.)
        self.btn_connect.Bind(wx.EVT_BUTTON, self._on_connect)
        self.btn_code.Bind(wx.EVT_BUTTON, self._on_code)
        self.txt_code.Bind(wx.EVT_TEXT_ENTER, self._on_code)
        self._closed = False
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        actions.add_listener(self.refresh)
        self.refresh()

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._closed = True
            self.actions.remove_listener(self.refresh)
        event.Skip()

    def refresh(self):
        """Show what the account and the folder are now (on the UI thread)."""
        if self._closed or not _alive(self):
            raise RuntimeError("the page is gone")
        view = self.actions.view()
        if self.txt_account.GetValue() != view["account"]:
            self.txt_account.ChangeValue(view["account"])
        if self.txt_folder.GetValue() != view["folder"]:
            self.txt_folder.ChangeValue(view["folder"])
        changed = False
        if self.btn_connect.GetLabel() != view["button"]:
            self.btn_connect.SetLabel(view["button"])
            changed = True
        self.btn_connect.Enable(view["button_enabled"])
        show_code = bool(view["code"])
        if self.txt_code.IsShown() != show_code:
            for window in (self.lbl_code, self.txt_code, self.btn_code):
                window.Show(show_code)
            if not show_code:
                self.txt_code.ChangeValue("")
            changed = True
        if changed:
            self.Layout()

    def _on_connect(self, event):
        self.actions.press()

    def _on_code(self, event):
        code = self.txt_code.GetValue().strip()
        if code:
            self.actions.give_code(code)

    def get_settings(self):
        return {name: box.GetValue() for name, box in self.checks.items()}
