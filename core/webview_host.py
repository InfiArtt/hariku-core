"""
hariku2/core/webview_host.py

Standalone subprocess script — JANGAN di-import secara langsung.
Dipanggil oleh core.webview melalui subprocess.Popen.

Cara kerja:
  python webview_host.py <html_file> <title> [width] [height]

Script ini berjalan sebagai proses TERPISAH dari Hariku. Karena
terpisah dari proses utama, tidak ada WH_KEYBOARD_LL hook, sehingga
wx.html2.WebView dapat diinisialisasi dengan aman tanpa deadlock COM.
"""

import sys
import os

# Pastikan direktori hariku2 ada di path agar core.* bisa diimport
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

        # Coba pasang ikon Hariku
        _icon_path = os.path.join(_hariku_root, "hariku.ico")
        if os.path.exists(_icon_path):
            self.SetIcon(wx.Icon(_icon_path))

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Info bar aksesibilitas
        info = wx.StaticText(
            panel,
            label="NVDA: tekan H=Heading, T=Tabel, L=List, K=Link, I=Item | ESC=Tutup"
        )
        sizer.Add(info, 0, wx.ALL | wx.EXPAND, 4)

        self.webview = wx.html2.WebView.New(panel)
        sizer.Add(self.webview, 1, wx.EXPAND)

        panel.SetSizer(sizer)
        self.Centre()

        # Muat HTML dari file
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
