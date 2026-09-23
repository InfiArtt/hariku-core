# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Markdown Reader dialog — the main UI for browsing Markdown documents.

Uses a lightweight, stable TextCtrl for internal navigation, plus a
"Read in Web View" button that opens an isolated WebView2 window (a
separate subprocess from Hariku) so NVDA Browse Mode works fully without
crashing.
"""

import os
import wx

from core.speech import speak
from core.i18n import apply_rtl_layout
import core.api

import md_parser

# ── HTML page template ──────────────────────────────────────────────

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{
        font-family: "Segoe UI", Calibri, Arial, sans-serif;
        font-size: 15px;
        line-height: 1.7;
        color: #e0e0e0;
        background: #1e1e1e;
        padding: 20px 30px;
        margin: 0;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: #ffffff;
        margin-top: 1.4em;
        margin-bottom: 0.4em;
        line-height: 1.3;
    }}
    h1 {{ font-size: 1.8em; border-bottom: 2px solid #444; padding-bottom: 6px; }}
    h2 {{ font-size: 1.5em; border-bottom: 1px solid #333; padding-bottom: 4px; }}
    h3 {{ font-size: 1.25em; }}
    h4 {{ font-size: 1.1em; }}
    p {{ margin: 0.6em 0; }}
    a {{ color: #6cb4ee; text-decoration: underline; }}
    a:focus {{ outline: 2px solid #6cb4ee; outline-offset: 2px; }}
    code {{
        font-family: Consolas, "Courier New", monospace;
        background: #2d2d2d;
        padding: 2px 5px;
        border-radius: 3px;
        font-size: 0.92em;
    }}
    pre {{
        background: #2d2d2d;
        border: 1px solid #444;
        border-radius: 6px;
        padding: 14px 18px;
        overflow-x: auto;
        margin: 1em 0;
    }}
    pre code {{ background: none; padding: 0; font-size: 0.9em; line-height: 1.5; }}
    blockquote {{
        border-left: 4px solid #6cb4ee;
        margin: 1em 0;
        padding: 8px 16px;
        background: #252530;
        color: #c0c0c0;
    }}
    ul, ol {{ padding-left: 28px; margin: 0.5em 0; }}
    li {{ margin: 4px 0; }}
    table {{ border-collapse: collapse; margin: 1em 0; width: auto; }}
    th, td {{ border: 1px solid #555; padding: 8px 12px; text-align: left; }}
    th {{ background: #333; color: #fff; font-weight: bold; }}
    tr:nth-child(even) {{ background: #262626; }}
    hr {{ border: none; border-top: 1px solid #444; margin: 1.5em 0; }}
    strong {{ color: #ffffff; }}
    del {{ color: #888; }}
    img {{ max-width: 100%; }}
    :focus {{ outline: 2px solid #6cb4ee; }}
</style>
</head>
<body>
{content}
</body>
</html>"""


class MarkdownReaderDialog(wx.Dialog):
    """Modal dialog for reading Markdown files."""

    def __init__(self, parent, filepath, translate_func):
        self._ = translate_func
        self.filepath = filepath
        self.headings = []
        self._plain_text = ""
        self._raw_source = ""
        self.sections = []

        filename = os.path.basename(filepath)
        title = self._("reader_title", filename=filename)
        super().__init__(parent, title=title, size=(800, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)

        apply_rtl_layout(self)
        self._build_ui()
        self._load_file(filepath)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    # ── UI Construction ─────────────────────────────────────────────

    def _build_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        splitter = wx.SplitterWindow(panel, style=wx.SP_LIVE_UPDATE)

        # ── Left: Heading navigation ────────────────────────────────
        left_panel = wx.Panel(splitter)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        self.heading_label = wx.StaticText(
            left_panel, label=self._("heading_list_label", count=0))
        left_sizer.Add(self.heading_label, 0, wx.ALL | wx.EXPAND, 5)

        self.heading_list = wx.ListBox(left_panel, style=wx.LB_SINGLE)
        self.heading_list.Bind(wx.EVT_LISTBOX, self._on_heading_selected)
        self.heading_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_heading_activate)
        left_sizer.Add(self.heading_list, 1, wx.ALL | wx.EXPAND, 5)

        left_panel.SetSizer(left_sizer)

        # ── Right: TextCtrl (lightweight, stable, NVDA can read line by line) ──
        right_panel = wx.Panel(splitter)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        content_label = wx.StaticText(right_panel, label=self._("content_label"))
        right_sizer.Add(content_label, 0, wx.ALL, 5)

        self.content_text = wx.TextCtrl(
            right_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL)
        font = wx.Font(11, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL,
                        wx.FONTWEIGHT_NORMAL, faceName="Consolas")
        self.content_text.SetFont(font)
        self.content_text.SetMargins(10, 10)
        right_sizer.Add(self.content_text, 1, wx.ALL | wx.EXPAND, 5)

        right_panel.SetSizer(right_sizer)

        splitter.SplitVertically(left_panel, right_panel, sashPosition=250)
        splitter.SetMinimumPaneSize(150)
        main_sizer.Add(splitter, 1, wx.EXPAND)

        # ── Status bar ──────────────────────────────────────────────
        self.status_text = wx.StaticText(panel, label=self._("status_no_file"))
        main_sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 5)

        # ── Buttons ─────────────────────────────────────────────────
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_open = wx.Button(panel, label=self._("btn_open"))
        btn_open.Bind(wx.EVT_BUTTON, self._on_open_file)
        btn_sizer.Add(btn_open, 0, wx.ALL, 5)

        btn_webview = wx.Button(panel, label=self._("btn_open_web"))
        btn_webview.Bind(wx.EVT_BUTTON, self._on_open_webview)
        btn_sizer.Add(btn_webview, 0, wx.ALL, 5)

        btn_copy_all = wx.Button(panel, label=self._("btn_copy_all"))
        btn_copy_all.Bind(wx.EVT_BUTTON, self._on_copy_all)
        btn_sizer.Add(btn_copy_all, 0, wx.ALL, 5)

        btn_sizer.AddStretchSpacer()

        btn_close = wx.Button(panel, wx.ID_CLOSE, label=self._("btn_close"))
        btn_close.Bind(wx.EVT_BUTTON, self._on_close)
        btn_sizer.Add(btn_close, 0, wx.ALL, 5)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND)

        panel.SetSizer(main_sizer)
        self.Centre()

    # ── File Loading ────────────────────────────────────────────────

    def _load_file(self, filepath):
        """Read and parse a Markdown file, then populate the UI."""
        try:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    raw = f.read()
            except UnicodeDecodeError:
                with open(filepath, "r", encoding="latin-1") as f:
                    raw = f.read()

            self._raw_source = raw
            self.filepath = filepath

            # Parse to plain text for display in the TextCtrl
            text, headings = md_parser.parse(raw)
            self.headings = headings
            self._plain_text = text

            self.content_text.SetValue(text)
            self.content_text.SetInsertionPoint(0)

            # Populate heading list
            self.heading_list.Clear()
            for h in headings:
                indent = "  " * (h.level - 1)
                self.heading_list.Append(f"{indent}{h.title}")

            self._build_sections(text, headings)

            filename = os.path.basename(filepath)
            line_count = raw.count("\n") + 1
            self.heading_label.SetLabel(
                self._("heading_list_label", count=len(headings)))
            self.status_text.SetLabel(
                self._("status_loaded",
                       filename=filename,
                       lines=line_count,
                       headings=len(headings)))

            self.SetTitle(self._("reader_title", filename=filename))
            speak(self._("status_loaded",
                         filename=filename,
                         lines=line_count,
                         headings=len(headings)))

        except Exception as e:
            core.api.show_message(
                self._("error_title"),
                self._("error_open", error=str(e)))

    def _build_sections(self, text, headings):
        lines = text.split("\n")
        total_lines = len(lines)
        self.sections = []

        if not headings:
            if total_lines > 0:
                self.sections.append((0, total_lines - 1))
            return

        for idx, h in enumerate(headings):
            start = min(h.line_index, total_lines - 1)
            if idx + 1 < len(headings):
                end = min(headings[idx + 1].line_index - 1, total_lines - 1)
                while end > start and lines[end].strip() == "":
                    end -= 1
            else:
                end = total_lines - 1
            self.sections.append((start, max(start, end)))

    def _get_section_text(self, idx):
        if idx < 0 or idx >= len(self.sections):
            return ""
        start, end = self.sections[idx]
        lines = self.content_text.GetValue().split("\n")
        return "\n".join(lines[start:end + 1])

    # ── WebView ─────────────────────────────────────────────────────

    def _on_open_webview(self, event):
        """Open in an isolated WebView — full NVDA Browse Mode."""
        if not self._raw_source:
            speak("No file loaded.", interrupt=True)
            return

        html_body, _ = md_parser.parse_to_html(self._raw_source)
        filename = os.path.basename(self.filepath)
        full_html = _HTML_TEMPLATE.format(content=html_body, title=filename)

        title = self._("reader_title", filename=filename)
        ok = core.api.show_html_view(full_html, title=title)

        if ok:
            speak(self._("webview_opened"), interrupt=True)
        else:
            speak(self._("webview_failed"), interrupt=True)

    # ── Event Handlers ──────────────────────────────────────────────

    def _on_heading_selected(self, event):
        idx = self.heading_list.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self.headings):
            return
        h = self.headings[idx]
        lines = self.content_text.GetValue().split("\n")
        pos = sum(len(lines[i]) + 1 for i in range(min(h.line_index, len(lines))))
        self.content_text.SetInsertionPoint(pos)
        self.content_text.ShowPosition(pos)
        speak(f"{h.title}")

    def _on_heading_activate(self, event):
        idx = self.heading_list.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        self._on_heading_selected(event)
        section_text = self._get_section_text(idx)
        if section_text:
            speak(section_text, interrupt=True)

    def _on_copy_all(self, event):
        if self._plain_text:
            core.api.set_clipboard(self._plain_text)
            speak(self._("copied_all"), interrupt=True)

    def _on_open_file(self, event):
        path = _pick_markdown_file(self, self._)
        if path:
            self._load_file(path)

    def _on_close(self, event):
        self.EndModal(wx.ID_CLOSE)

    def _on_key(self, event):
        keycode = event.GetKeyCode()
        ctrl = event.ControlDown()
        alt = event.AltDown()

        if keycode == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CLOSE)
            return
        if ctrl and keycode == ord("O"):
            self._on_open_file(event)
            return
        if ctrl and event.ShiftDown() and keycode == ord("C"):
            self._on_copy_all(event)
            return
        if ctrl and keycode == ord("B"):
            self._on_open_webview(event)
            return
        if alt and keycode == wx.WXK_UP:
            self._navigate_heading(-1)
            return
        if alt and keycode == wx.WXK_DOWN:
            self._navigate_heading(1)
            return

        event.Skip()

    def _navigate_heading(self, direction):
        if not self.headings:
            speak(self._("no_headings"))
            return
        current = self.heading_list.GetSelection()
        new_idx = 0 if current == wx.NOT_FOUND else current + direction
        if 0 <= new_idx < len(self.headings):
            self.heading_list.SetSelection(new_idx)
            self._on_heading_selected(None)


# ── Helper functions ────────────────────────────────────────────────

def _pick_markdown_file(parent, translate_func):
    _ = translate_func
    dlg = wx.FileDialog(
        parent,
        message=_("file_dialog_title"),
        wildcard=_("file_dialog_filter"),
        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
    try:
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetPath()
        return None
    finally:
        dlg.Destroy()


def open_reader(filepath, translate_func):
    parent = core.api.main_window_instance
    dlg = MarkdownReaderDialog(parent, filepath, translate_func)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def open_with_picker(translate_func):
    parent = core.api.main_window_instance
    path = _pick_markdown_file(parent, translate_func)
    if path:
        open_reader(path, translate_func)
    return path
