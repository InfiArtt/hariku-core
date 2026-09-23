# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Standalone subprocess script — do NOT import it directly.
Launched by core.webview via subprocess.Popen.

Usage:
  python webview_host.py <html_file> <title> [width] [height]

This runs as a SEPARATE process from Hariku. Being separate from the main
process, it carries no WH_KEYBOARD_LL hook, so wx.html2.WebView can be
initialized safely without a COM deadlock.
"""

import sys
import os

# Ensure the hariku2 directory is on the path so core.* can be imported.
_script_dir = os.path.dirname(os.path.abspath(__file__))
_hariku_root = os.path.dirname(_script_dir)
if _hariku_root not in sys.path:
    sys.path.insert(0, _hariku_root)

import wx
import wx.html2


class WebViewFrame(wx.Frame):
    def __init__(self, html_path, title, width, height):
        super().__init__(
            None,
            title=title,
            size=(width, height),
            style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER
        )

        # Attach the Hariku icon if present.
        _icon_path = os.path.join(_hariku_root, "hariku.ico")
        if os.path.exists(_icon_path):
            self.SetIcon(wx.Icon(_icon_path))

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Accessibility info bar.
        info = wx.StaticText(
            panel,
            label="NVDA: tekan H=Heading, T=Tabel, L=List, K=Link, I=Item | ESC=Tutup"
        )
        sizer.Add(info, 0, wx.ALL | wx.EXPAND, 4)

        self.webview = wx.html2.WebView.New(panel)
        sizer.Add(self.webview, 1, wx.EXPAND)

        panel.SetSizer(sizer)
        self.Centre()

        # Load the HTML from the file.
        file_uri = "file:///" + html_path.replace("\\", "/")
        self.webview.LoadURL(file_uri)

        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.Show()

    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()


def main():
    if len(sys.argv) < 3:
        print("Usage: webview_host.py <html_file> <title> [width] [height]")
        sys.exit(1)

    html_path = sys.argv[1]
    title = sys.argv[2]
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 850
    height = int(sys.argv[4]) if len(sys.argv) > 4 else 650

    app = wx.App(False)
    frame = WebViewFrame(html_path, title, width, height)
    app.MainLoop()


if __name__ == "__main__":
    main()
