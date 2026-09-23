# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# A screen-reader-friendly viewer for the Routines execution log. It shows the
# recent runs (newest first) in a read-only multiline text box that a screen
# reader can arrow through line by line, plus Clear and Close buttons.
# Public entry point: show_log(parent).
import wx

import routines_runtime as runtime


class LogViewerDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Routines Log", size=(560, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        v = wx.BoxSizer(wx.VERTICAL)
        v.Add(wx.StaticText(self, label="Recent routine activity (newest first):"),
              0, wx.ALL, 8)

        # Read-only multiline text: screen readers can navigate it line by line.
        self.txt = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.HSCROLL)
        self.txt.SetName("Routine activity log")
        v.Add(self.txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        h = wx.BoxSizer(wx.HORIZONTAL)
        btn_clear = wx.Button(self, label="C&lear")
        btn_clear.Bind(wx.EVT_BUTTON, self.on_clear)
        h.Add(btn_clear, 0, wx.RIGHT, 6)
        btn_close = wx.Button(self, wx.ID_CANCEL, label="&Close")
        h.Add(btn_close, 0)
        v.Add(h, 0, wx.ALL, 8)

        self.SetSizer(v)
        self.SetEscapeId(wx.ID_CANCEL)
        try:
            import core.ui_scale
            core.ui_scale.apply_appearance(self)
        except Exception:
            pass
        self._refresh()
        self.txt.SetFocus()

    @staticmethod
    def _format(entry):
        base = "[%s] %s (%s)" % (entry.get("time", ""),
                                 entry.get("name", "?"),
                                 entry.get("source", ""))
        errors = entry.get("errors") or []
        if errors:
            return base + " - ERRORS: " + "; ".join(str(e) for e in errors)
        return base + " - ok"

    def _refresh(self):
        try:
            entries = runtime.get_log()
        except Exception:
            entries = []
        lines = [self._format(e) for e in reversed(entries)]  # newest first
        self.txt.SetValue("\n".join(lines) if lines
                          else "No routine activity yet.")
        self.txt.SetInsertionPoint(0)

    def on_clear(self, _e):
        try:
            runtime.clear_log()
        except Exception:
            pass
        self._refresh()
        self.txt.SetFocus()


def show_log(parent=None):
    dlg = LogViewerDialog(parent)
    dlg.ShowModal()
    dlg.Destroy()
