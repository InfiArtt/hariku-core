# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# A screen-reader-friendly cheat sheet of every registered keyboard shortcut,
# grouped by extension. Opened with F1 (rebindable via Input Gestures).
import wx
from collections import defaultdict

import core.hotkeys as hk


def _build_text():
    groups = defaultdict(list)
    for action in hk.actions.values():
        groups[action.extension_name].append(action)

    lines = []
    for ext in sorted(groups, key=str.lower):
        lines.append(f"== {ext} ==")
        for action in sorted(groups[ext], key=lambda a: a.description.lower()):
            binds = hk.get_current_bindings(action.id)
            if binds:
                keys = ", ".join(
                    hk.format_key_name(b[0], b[1], b[2], b[3], b[4])
                    + (" (global)" if b[5] else "")
                    for b in binds
                )
            else:
                keys = "Unassigned"
            lines.append(f"{action.description}: {keys}")
        lines.append("")
    if not lines:
        lines = ["No shortcuts registered."]
    return "\n".join(lines).rstrip()


class ShortcutsDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Keyboard Shortcuts", size=(560, 480),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        vbox = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(self, label="All keyboard shortcuts (press Escape to close):")
        vbox.Add(lbl, 0, wx.ALL, 8)

        # Read-only multiline text: NVDA reads/arrows through it line by line.
        self.text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.text.SetValue(_build_text())
        vbox.Add(self.text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        btn = wx.Button(self, wx.ID_CANCEL, label="Close")
        vbox.Add(btn, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        try:
            from core.i18n import apply_rtl_layout
            apply_rtl_layout(self)
        except Exception:
            pass

        self.SetSizer(vbox)
        self.CentreOnParent()
        try:
            import core.ui_scale
            core.ui_scale.apply_appearance(self)
        except Exception:
            pass
        self.text.SetFocus()
        self.text.SetInsertionPoint(0)


def show_shortcuts(parent):
    dlg = ShortcutsDialog(parent)
    dlg.ShowModal()
    dlg.Destroy()
