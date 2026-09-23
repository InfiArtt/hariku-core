# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import wx.stc
import sys
import os
import io
import logging
import importlib
import zipfile
import shutil

import core.api
import core.extension_manager
from core.speech import speak
from core.i18n import apply_rtl_layout

logger = logging.getLogger("ext.developer_toolkit")


class DeveloperToolkitDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Developer Toolkit", size=(700, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.notebook = wx.Notebook(self)
        
        self.tab_repl = ReplPanel(self.notebook)
        self.tab_sniffer = SnifferPanel(self.notebook)
        self.tab_log = LogViewerPanel(self.notebook)
        self.tab_inspector = InspectorPanel(self.notebook)
        self.tab_packer = PackerPanel(self.notebook)
        
        self.notebook.AddPage(self.tab_repl, "REPL Console")
        self.notebook.AddPage(self.tab_sniffer, "Event Sniffer")
        self.notebook.AddPage(self.tab_log, "Log Viewer")
        self.notebook.AddPage(self.tab_inspector, "Extension Inspector")
        self.notebook.AddPage(self.tab_packer, "HRK Packer")
        
        vbox.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        
        # Close button
        btn_close = wx.Button(self, wx.ID_CLOSE, "Close")
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        vbox.Add(btn_close, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        
        self.SetSizer(vbox)
        self.CentreOnParent()
        
        apply_rtl_layout(self)
        
        speak("Developer Toolkit. Use Ctrl+Tab to switch between tabs.", interrupt=True)


# ============================================================
# TAB 1: REPL Console
# ============================================================
class ReplPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Input area
        lbl_input = wx.StaticText(self, label="Python Code (multi-line supported):")
        vbox.Add(lbl_input, 0, wx.LEFT | wx.TOP, 10)
        
        self.txt_input = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_PROCESS_TAB, size=(-1, 120))
        self.txt_input.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        vbox.Add(self.txt_input, 0, wx.EXPAND | wx.ALL, 10)
        
        # Buttons
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        btn_exec = wx.Button(self, label="Execute (F5)")
        btn_exec.Bind(wx.EVT_BUTTON, self.OnExecute)
        hbox.Add(btn_exec, 0, wx.RIGHT, 5)
        
        btn_clear = wx.Button(self, label="Clear Output")
        btn_clear.Bind(wx.EVT_BUTTON, self.OnClearOutput)
        hbox.Add(btn_clear, 0, wx.RIGHT, 5)
        
        btn_clear_input = wx.Button(self, label="Clear Input")
        btn_clear_input.Bind(wx.EVT_BUTTON, self.OnClearInput)
        hbox.Add(btn_clear_input, 0)
        
        vbox.Add(hbox, 0, wx.LEFT | wx.BOTTOM, 10)
        
        # Output area
        lbl_output = wx.StaticText(self, label="Output:")
        vbox.Add(lbl_output, 0, wx.LEFT, 10)
        
        self.txt_output = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.txt_output.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.txt_output.SetBackgroundColour(wx.Colour(30, 30, 30))
        self.txt_output.SetForegroundColour(wx.Colour(0, 255, 0))
        vbox.Add(self.txt_output, 1, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(vbox)
        
        # Bind keys to both input and output areas
        self.txt_input.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.txt_output.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        
        # Safe help function that doesn't block
        def _safe_help(obj=None):
            if obj is None:
                return "Usage: help(object) — e.g. help(core.api), help(speak)"
            import pydoc
            return pydoc.render_doc(obj, title='%s')
        
        # Execution namespace (persistent across calls)
        self._exec_ns = {
            "wx": wx,
            "core": __import__("core"),
            "speak": speak,
            "bus": __import__("core.events", fromlist=["bus"]).bus,
            "api": core.api,
            "help": _safe_help,
        }
    
    def OnKeyDown(self, event):
        if event.GetKeyCode() == wx.WXK_F5:
            self.OnExecute(None)
        elif event.ControlDown() and event.GetKeyCode() == ord('M'):
            # Toggle focus between input and output
            focused = wx.Window.FindFocus()
            if focused == self.txt_output:
                self.txt_input.SetFocus()
                speak("Code input.", interrupt=True)
            else:
                self.txt_output.SetFocus()
                speak("Output.", interrupt=True)
        else:
            event.Skip()
    
    def OnExecute(self, event):
        code = self.txt_input.GetValue().strip()
        if not code:
            speak("No code to execute.")
            return
        
        # Capture stdout and stderr, block stdin
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin = sys.stdin
        sys.stdout = captured_out = io.StringIO()
        sys.stderr = captured_err = io.StringIO()
        sys.stdin = io.StringIO("")  # Block interactive input
        
        result_text = ""
        try:
            # Try eval first (for expressions that return a value)
            try:
                result = eval(code, self._exec_ns)
                if result is not None:
                    result_text = repr(result)
            except SyntaxError:
                # If eval fails, use exec (for statements)
                exec(code, self._exec_ns)
        except Exception as e:
            result_text = f"ERROR: {type(e).__name__}: {e}"
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin
        
        stdout_text = captured_out.getvalue()
        stderr_text = captured_err.getvalue()
        
        # Build output
        output_parts = []
        if stdout_text:
            output_parts.append(stdout_text.rstrip())
        if stderr_text:
            output_parts.append(f"[STDERR] {stderr_text.rstrip()}")
        if result_text:
            output_parts.append(f">>> {result_text}")
        
        output = "\n".join(output_parts) if output_parts else "(No output)"
        
        # Append to output area
        current = self.txt_output.GetValue()
        separator = "\n" + "=" * 50 + "\n" if current else ""
        self.txt_output.SetValue(current + separator + f">>> {code}\n{output}\n")
        self.txt_output.ShowPosition(self.txt_output.GetLastPosition())
        
        speak(output[:200], interrupt=True)
    
    def OnClearOutput(self, event):
        self.txt_output.SetValue("")
        speak("Output cleared.")
    
    def OnClearInput(self, event):
        self.txt_input.SetValue("")
        self.txt_input.SetFocus()
        speak("Input cleared.")


# ============================================================
# TAB 2: Event Sniffer
# ============================================================
class SnifferPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Status
        hbox_status = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_status = wx.StaticText(self, label="Status: Active")
        hbox_status.Add(self.lbl_status, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        vbox.Add(hbox_status, 0, wx.EXPAND)
        
        # Buttons
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        btn_refresh = wx.Button(self, label="Refresh (F5)")
        btn_refresh.Bind(wx.EVT_BUTTON, self.OnRefresh)
        hbox.Add(btn_refresh, 0, wx.RIGHT, 5)
        
        btn_clear = wx.Button(self, label="Clear Events")
        btn_clear.Bind(wx.EVT_BUTTON, self.OnClear)
        hbox.Add(btn_clear, 0, wx.RIGHT, 5)
        
        self.btn_toggle = wx.Button(self, label="Stop Sniffer")
        self.btn_toggle.Bind(wx.EVT_BUTTON, self.OnToggle)
        hbox.Add(self.btn_toggle, 0)
        
        vbox.Add(hbox, 0, wx.LEFT | wx.BOTTOM, 10)
        
        # Events list
        self.txt_events = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.txt_events.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.txt_events.SetBackgroundColour(wx.Colour(20, 20, 40))
        self.txt_events.SetForegroundColour(wx.Colour(100, 200, 255))
        vbox.Add(self.txt_events, 1, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(vbox)
        
        self.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.txt_events.Bind(wx.EVT_KEY_DOWN, self._on_key)
    
    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_F5:
            self.OnRefresh(None)
        else:
            event.Skip()
    
    def OnRefresh(self, event):
        import main as _dtk_main
        
        self.lbl_status.SetLabel(f"Status: {'Active' if _dtk_main._sniffer_active else 'Stopped'} | Events captured: {len(_dtk_main._sniffed_events)}")
        
        if _dtk_main._sniffed_events:
            self.txt_events.SetValue("\n".join(_dtk_main._sniffed_events))
            self.txt_events.ShowPosition(self.txt_events.GetLastPosition())
            speak(f"{len(_dtk_main._sniffed_events)} events captured. Latest: {_dtk_main._sniffed_events[-1][:80]}", interrupt=True)
        else:
            self.txt_events.SetValue("(No events captured yet)")
            speak("No events captured yet.", interrupt=True)
    
    def OnClear(self, event):
        import main as _dtk_main
        _dtk_main._sniffed_events.clear()
        self.txt_events.SetValue("")
        speak("Events cleared.")
    
    def OnToggle(self, event):
        import main as _dtk_main
        if _dtk_main._sniffer_active:
            _dtk_main._stop_sniffer()
            self.btn_toggle.SetLabel("Start Sniffer")
            self.lbl_status.SetLabel("Status: Stopped")
            speak("Event Sniffer stopped.")
        else:
            _dtk_main._start_sniffer()
            self.btn_toggle.SetLabel("Stop Sniffer")
            self.lbl_status.SetLabel("Status: Active")
            speak("Event Sniffer started.")


# ============================================================
# TAB 3: Live Log Viewer
# ============================================================
class LogViewerPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Log file path display
        hbox_path = wx.BoxSizer(wx.HORIZONTAL)
        hbox_path.Add(wx.StaticText(self, label="Log File:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.lbl_path = wx.StaticText(self, label=self._get_log_path())
        self.lbl_path.SetForegroundColour(wx.Colour(100, 100, 100))
        hbox_path.Add(self.lbl_path, 1, wx.ALIGN_CENTER_VERTICAL)
        
        vbox.Add(hbox_path, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        
        # Buttons
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        btn_refresh = wx.Button(self, label="Refresh (F5)")
        btn_refresh.Bind(wx.EVT_BUTTON, self.OnRefresh)
        hbox.Add(btn_refresh, 0, wx.RIGHT, 5)
        
        btn_copy = wx.Button(self, label="Copy All")
        btn_copy.Bind(wx.EVT_BUTTON, self.OnCopyAll)
        hbox.Add(btn_copy, 0, wx.RIGHT, 5)
        
        btn_open_folder = wx.Button(self, label="Open Log Folder")
        btn_open_folder.Bind(wx.EVT_BUTTON, self.OnOpenFolder)
        hbox.Add(btn_open_folder, 0, wx.RIGHT, 5)
        
        self.chk_tail = wx.CheckBox(self, label="Show last 200 lines only")
        self.chk_tail.SetValue(True)
        hbox.Add(self.chk_tail, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        
        self.chk_auto = wx.CheckBox(self, label="Auto-refresh (3s)")
        self.chk_auto.SetValue(False)
        self.chk_auto.Bind(wx.EVT_CHECKBOX, self.OnToggleAutoRefresh)
        hbox.Add(self.chk_auto, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        
        vbox.Add(hbox, 0, wx.ALL, 10)
        
        # Log content
        self.txt_log = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.txt_log.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.txt_log.SetBackgroundColour(wx.Colour(20, 20, 20))
        self.txt_log.SetForegroundColour(wx.Colour(200, 200, 200))
        vbox.Add(self.txt_log, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        self.SetSizer(vbox)
        
        self.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.txt_log.Bind(wx.EVT_KEY_DOWN, self._on_key)
        
        # Auto-refresh timer
        self._auto_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_auto_tick, self._auto_timer)
        
        # Auto-load on first view
        wx.CallAfter(self.OnRefresh, None)
    
    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_F5:
            self.OnRefresh(None)
        else:
            event.Skip()
    
    def _get_log_path(self):
        temp_dir = os.environ.get("TEMP", os.environ.get("TMP", os.path.expanduser("~")))
        return os.path.join(temp_dir, "hariku2", "hariku_debug.log")
    
    def OnRefresh(self, event):
        log_path = self._get_log_path()
        
        if not os.path.exists(log_path):
            self.txt_log.SetValue(f"Log file not found at:\n{log_path}\n\nThe log file is created when Hariku starts.\nMake sure Hariku is running normally (not in Safe Mode).")
            if event is not None:  # Don't speak on auto-refresh
                speak("Log file not found.", interrupt=True)
            return
        
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            if self.chk_tail.GetValue():
                lines = lines[-200:]
            
            content = "".join(lines)
            
            # Only update if content changed (avoids flicker on auto-refresh)
            if content != self.txt_log.GetValue():
                self.txt_log.SetValue(content)
                self.txt_log.ShowPosition(self.txt_log.GetLastPosition())
            
            if event is not None:  # Don't speak on auto-refresh
                speak(f"Log refreshed. {len(lines)} lines loaded.", interrupt=True)
        except Exception as e:
            self.txt_log.SetValue(f"Error reading log: {e}")
            if event is not None:
                speak(f"Error reading log: {e}", interrupt=True)
    
    def OnCopyAll(self, event):
        content = self.txt_log.GetValue()
        if content:
            core.api.set_clipboard(content)
            speak("Log copied to clipboard.")
        else:
            speak("Nothing to copy.")
    
    def OnOpenFolder(self, event):
        log_path = self._get_log_path()
        folder = os.path.dirname(log_path)
        if os.path.exists(folder):
            os.startfile(folder)
            speak("Opening log folder.")
        else:
            speak("Log folder does not exist yet.")
    
    def OnToggleAutoRefresh(self, event):
        if self.chk_auto.GetValue():
            self._auto_timer.Start(3000)
            speak("Auto-refresh enabled.")
        else:
            self._auto_timer.Stop()
            speak("Auto-refresh disabled.")
    
    def _on_auto_tick(self, event):
        self.OnRefresh(None)  # Pass None so it doesn't speak


# ============================================================
# TAB 4: Extension Inspector & Hot-Reloader
# ============================================================
class InspectorPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label="Loaded Extensions in Memory:")
        vbox.Add(lbl, 0, wx.ALL, 10)
        
        # Extension list
        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, "ID", width=150)
        self.list_ctrl.InsertColumn(1, "Name", width=180)
        self.list_ctrl.InsertColumn(2, "Version", width=60)
        self.list_ctrl.InsertColumn(3, "Mode", width=80)
        self.list_ctrl.InsertColumn(4, "Module", width=180)
        vbox.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # Buttons
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        btn_refresh = wx.Button(self, label="Refresh List")
        btn_refresh.Bind(wx.EVT_BUTTON, self.OnRefresh)
        hbox.Add(btn_refresh, 0, wx.RIGHT, 5)
        
        btn_reload = wx.Button(self, label="Force Reload Selected")
        btn_reload.Bind(wx.EVT_BUTTON, self.OnReload)
        hbox.Add(btn_reload, 0, wx.RIGHT, 5)
        
        btn_inspect = wx.Button(self, label="Inspect Module")
        btn_inspect.Bind(wx.EVT_BUTTON, self.OnInspect)
        hbox.Add(btn_inspect, 0)
        
        vbox.Add(hbox, 0, wx.ALL, 10)
        
        # Info area
        self.txt_info = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 100))
        self.txt_info.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        vbox.Add(self.txt_info, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        self.SetSizer(vbox)
        
        wx.CallAfter(self.OnRefresh, None)
    
    def OnRefresh(self, event):
        self.list_ctrl.DeleteAllItems()
        
        for idx, (ext_id, ext_data) in enumerate(core.extension_manager.LOADED_EXTENSIONS.items()):
            manifest = ext_data["manifest"]
            module = ext_data["module"]
            mode = "Unpacked" if ext_data.get("is_unpacked") else "Zipped"
            module_name = module.__name__ if module else "N/A"
            
            self.list_ctrl.InsertItem(idx, ext_id)
            self.list_ctrl.SetItem(idx, 1, manifest.get("name", "Unknown"))
            self.list_ctrl.SetItem(idx, 2, manifest.get("version", "?"))
            self.list_ctrl.SetItem(idx, 3, mode)
            self.list_ctrl.SetItem(idx, 4, module_name)
        
        count = len(core.extension_manager.LOADED_EXTENSIONS)
        speak(f"Extension list refreshed. {count} extensions loaded.", interrupt=True)
    
    def OnReload(self, event):
        sel = self.list_ctrl.GetFirstSelected()
        if sel == -1:
            speak("No extension selected.")
            return
        
        ext_id = self.list_ctrl.GetItemText(sel, 0)
        ext_data = core.extension_manager.LOADED_EXTENSIONS.get(ext_id)
        
        if not ext_data:
            speak(f"Extension {ext_id} not found in memory.")
            return
        
        module = ext_data["module"]
        module_name = module.__name__
        
        # Call teardown if it exists
        if hasattr(module, "teardown"):
            try:
                module.teardown()
            except Exception as e:
                logger.error(f"Error calling teardown on {ext_id}: {e}")
        
        # Find extension directory
        ext_dir = None
        if ext_data.get("is_unpacked"):
            ext_dir = os.path.join(core.extension_manager.EXTENSIONS_DIR, ext_id)
        else:
            ext_dir = os.path.join(core.extension_manager.EXTENSIONS_DIR, ".cache", ext_id)
        
        if not ext_dir or not os.path.exists(ext_dir):
            speak(f"Cannot find source directory for {ext_id}.")
            return
        
        # Remove old module references from sys.modules
        mods_to_remove = [name for name in sys.modules if name == module_name or name.startswith(module_name + ".")]
        for name in mods_to_remove:
            del sys.modules[name]
        
        # Remove from LOADED_EXTENSIONS
        del core.extension_manager.LOADED_EXTENSIONS[ext_id]
        
        # Reload
        try:
            core.extension_manager._load_extension_from_dir(ext_dir, ext_id)
            speak(f"Extension {ext_id} reloaded successfully!", interrupt=True)
            self.txt_info.SetValue(f"[OK] {ext_id} was force-reloaded from:\n{ext_dir}")
        except Exception as e:
            speak(f"Failed to reload {ext_id}: {e}", interrupt=True)
            self.txt_info.SetValue(f"[ERROR] Failed to reload {ext_id}:\n{e}")
        
        self.OnRefresh(None)
    
    def OnInspect(self, event):
        sel = self.list_ctrl.GetFirstSelected()
        if sel == -1:
            speak("No extension selected.")
            return
        
        ext_id = self.list_ctrl.GetItemText(sel, 0)
        ext_data = core.extension_manager.LOADED_EXTENSIONS.get(ext_id)
        
        if not ext_data:
            speak(f"Extension {ext_id} not found.")
            return
        
        module = ext_data["module"]
        manifest = ext_data["manifest"]
        
        # Build inspection report
        lines = []
        lines.append(f"=== Extension: {manifest.get('name', ext_id)} ===")
        lines.append(f"ID: {ext_id}")
        lines.append(f"Version: {manifest.get('version', '?')}")
        lines.append(f"Author: {manifest.get('author', '?')}")
        lines.append(f"Description: {manifest.get('description', 'N/A')}")
        lines.append(f"Module: {module.__name__}")
        lines.append(f"File: {getattr(module, '__file__', 'N/A')}")
        lines.append(f"Mode: {'Unpacked' if ext_data.get('is_unpacked') else 'Zipped'}")
        lines.append(f"Official: {'Yes' if ext_data.get('is_official') else 'No'}")
        lines.append("")
        lines.append("--- Exported Symbols ---")
        
        for attr_name in sorted(dir(module)):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name)
            attr_type = type(attr).__name__
            lines.append(f"  {attr_name} ({attr_type})")
        
        report = "\n".join(lines)
        self.txt_info.SetValue(report)
        speak(f"Inspecting {manifest.get('name', ext_id)}. {len(lines)} attributes found.", interrupt=True)


# ============================================================
# TAB 5: HRK Packer
# ============================================================
class PackerPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label="Package an unpacked extension folder into a distributable .hrk file.")
        lbl.Wrap(600)
        vbox.Add(lbl, 0, wx.ALL, 10)
        
        # Source folder picker
        hbox_src = wx.BoxSizer(wx.HORIZONTAL)
        hbox_src.Add(wx.StaticText(self, label="Extension Folder:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.txt_source = wx.TextCtrl(self, style=wx.TE_READONLY)
        hbox_src.Add(self.txt_source, 1, wx.RIGHT, 5)
        
        btn_browse = wx.Button(self, label="Browse...")
        btn_browse.Bind(wx.EVT_BUTTON, self.OnBrowse)
        hbox_src.Add(btn_browse, 0)
        
        vbox.Add(hbox_src, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        vbox.AddSpacer(10)
        
        # Pack button
        btn_pack = wx.Button(self, label="Validate & Pack into .hrk")
        btn_pack.Bind(wx.EVT_BUTTON, self.OnPack)
        vbox.Add(btn_pack, 0, wx.LEFT, 10)
        
        vbox.AddSpacer(10)
        
        # Output log
        lbl_out = wx.StaticText(self, label="Packer Output:")
        vbox.Add(lbl_out, 0, wx.LEFT, 10)
        
        self.txt_output = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.txt_output.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        vbox.Add(self.txt_output, 1, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(vbox)
    
    def OnBrowse(self, event):
        dlg = wx.DirDialog(self, "Select Extension Folder", 
                           defaultPath=core.extension_manager.EXTENSIONS_DIR,
                           style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.txt_source.SetValue(dlg.GetPath())
            speak(f"Selected: {os.path.basename(dlg.GetPath())}")
        dlg.Destroy()
    
    def OnPack(self, event):
        source = self.txt_source.GetValue().strip()
        if not source:
            speak("Please select an extension folder first.")
            return
        
        if not os.path.isdir(source):
            speak("Selected path is not a valid folder.")
            return
        
        output_lines = []
        
        def log(msg):
            output_lines.append(msg)
        
        ext_id = os.path.basename(source)
        manifest_path = os.path.join(source, "manifest.json")
        
        # Step 1: Check manifest
        log(f"[1/4] Checking manifest for '{ext_id}'...")
        if not os.path.exists(manifest_path):
            log("  ERROR: manifest.json not found!")
            self._show_output(output_lines)
            speak("Manifest not found. Packing aborted.")
            return
        
        try:
            import json
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            log(f"  ERROR: Failed to parse manifest: {e}")
            self._show_output(output_lines)
            speak("Invalid manifest JSON. Packing aborted.")
            return
        
        # Validate required fields
        required = ["name", "version", "author", "description", "main", "language", "minimum_core_version"]
        missing = [f for f in required if f not in manifest]
        if missing:
            log(f"  ERROR: Missing required fields: {missing}")
            self._show_output(output_lines)
            speak(f"Manifest is missing fields: {', '.join(missing)}")
            return
        
        log(f"  OK: {manifest['name']} v{manifest['version']} by {manifest['author']}")
        
        # Step 2: Check entry point
        log(f"[2/4] Checking entry point '{manifest['main']}'...")
        entry_path = os.path.join(source, manifest["main"])
        if not os.path.exists(entry_path):
            log(f"  ERROR: Entry point '{manifest['main']}' not found!")
            self._show_output(output_lines)
            speak("Entry point file not found.")
            return
        log("  OK: Entry point exists.")
        
        # Step 3: Clean __pycache__
        log("[3/4] Cleaning __pycache__ directories...")
        cleaned = 0
        for root, dirs, files in os.walk(source):
            if "__pycache__" in dirs:
                pycache_path = os.path.join(root, "__pycache__")
                shutil.rmtree(pycache_path)
                cleaned += 1
                dirs.remove("__pycache__")
        log(f"  Cleaned {cleaned} __pycache__ folder(s).")
        
        # Step 4: Create .hrk
        log("[4/4] Creating .hrk archive...")
        output_path = os.path.join(os.path.dirname(source), f"{ext_id}.hrk")
        
        try:
            file_count = 0
            total_size = 0
            
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(source):
                    # Skip hidden folders
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for file in files:
                        if file.startswith("."):
                            continue
                        filepath = os.path.join(root, file)
                        arcname = os.path.relpath(filepath, source)
                        zf.write(filepath, arcname)
                        file_count += 1
                        total_size += os.path.getsize(filepath)
            
            hrk_size = os.path.getsize(output_path)
            log(f"  OK: Packed {file_count} files ({total_size:,} bytes) into {ext_id}.hrk ({hrk_size:,} bytes)")
            log(f"  Compression ratio: {hrk_size/total_size*100:.1f}%" if total_size > 0 else "")
            log(f"\n  Output: {output_path}")
            log("\n  SUCCESS! Extension is ready for distribution.")
            
            speak(f"Packing complete! {ext_id}.hrk created. {file_count} files packed.", interrupt=True)
        except Exception as e:
            log(f"  ERROR: Failed to create .hrk: {e}")
            speak(f"Packing failed: {e}", interrupt=True)
        
        self._show_output(output_lines)
    
    def _show_output(self, lines):
        self.txt_output.SetValue("\n".join(lines))
        self.txt_output.ShowPosition(self.txt_output.GetLastPosition())
