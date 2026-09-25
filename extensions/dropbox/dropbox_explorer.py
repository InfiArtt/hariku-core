# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Which file the user is on in File Explorer.

"The window you were using" is the one that had the focus: a hotkey fires
while it still does, and Aruna gives the focus back to the window it was
opened from (ui.command_bar remembers it with GetForegroundWindow) before it
runs an action or a Reply's `then`. So the foreground window is asked, and it
must be an Explorer window (class CabinetWClass).

Explorer tells its selection through the Shell.Application scripting object
(its Windows(), each with HWND, Document.FocusedItem and SelectedItems()).
Hariku's compiled build can't make comtypes wrappers at run time (see
core/voice_sapi.py), and calling IDispatch by hand through ctypes means
marshalling VARIANTs and initialising COM on the worker thread: a lot of
fragile code for three properties. A short PowerShell (part of every
Windows 10 and 11) asks the same object instead: one process for one
command the user asked for, about half a second, with a 10-second timeout,
and no window (CREATE_NO_WINDOW). The script is fixed text plus the window
number, so nothing the user typed ever reaches it. No wx here.
"""

import base64
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys

import dropbox_paths as paths

EXPLORER_CLASSES = ("CabinetWClass", "ExploreWClass")
TIMEOUT = 10
CREATE_NO_WINDOW = 0x08000000

_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$target = [int64]__HWND__
$found = @()
$shell = New-Object -ComObject Shell.Application
foreach ($w in @($shell.Windows())) {
  $h = 0
  try { $h = [int64]$w.HWND } catch { continue }
  if ($h -ne $target) { continue }
  $doc = $w.Document
  $folder = ''
  try { $folder = [string]$doc.Folder.Self.Path } catch {}
  $focused = ''
  try { $item = $doc.FocusedItem; if ($item) { $focused = [string]$item.Path } } catch {}
  $selected = @()
  try { foreach ($i in @($doc.SelectedItems())) { $selected += [string]$i.Path } } catch {}
  $found += New-Object PSObject -Property @{ name = [string]$w.LocationName; folder = $folder; focused = $focused; selected = $selected }
}
ConvertTo-Json -InputObject @($found) -Compress -Depth 4
"""


class ExplorerError(Exception):
    """File Explorer couldn't be asked (PowerShell missing, too slow, no answer)."""


# ------------------------------------------------------------
# The window
# ------------------------------------------------------------

_user32 = None


def _user():
    global _user32
    if _user32 is None:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetForegroundWindow.argtypes = []
        u.GetForegroundWindow.restype = ctypes.wintypes.HWND
        u.GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
        u.GetClassNameW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        _user32 = u
    return _user32


def foreground_window():
    """The window that has the focus, as a number (0 for none)."""
    if sys.platform != "win32":
        return 0
    try:
        return int(_user().GetForegroundWindow() or 0)
    except Exception:
        return 0


def window_class(hwnd):
    if not hwnd or sys.platform != "win32":
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    _user().GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def window_title(hwnd):
    if not hwnd or sys.platform != "win32":
        return ""
    buffer = ctypes.create_unicode_buffer(512)
    _user().GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def is_explorer(hwnd, class_of=window_class):
    return bool(hwnd) and class_of(hwnd) in EXPLORER_CLASSES


# ------------------------------------------------------------
# Asking Explorer
# ------------------------------------------------------------

def script_for(hwnd):
    """The PowerShell script for one window (only a number goes into it)."""
    return _SCRIPT.replace("__HWND__", str(int(hwnd)))


def powershell_path(environ=None):
    environ = os.environ if environ is None else environ
    root = environ.get("SystemRoot") or environ.get("windir") or r"C:\Windows"
    path = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return path if os.path.isfile(path) else "powershell.exe"


def parse_output(stdout):
    """The tabs PowerShell reported: [{"name", "folder", "focused", "selected"}]."""
    text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else str(stdout)
    text = text.lstrip("\ufeff").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        raise ExplorerError("File Explorer's answer couldn't be read") from None
    if isinstance(data, dict):
        data = [data]
    tabs = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        selected = item.get("selected") or []
        if isinstance(selected, str):
            selected = [selected]
        tabs.append({"name": str(item.get("name") or ""), "folder": str(item.get("folder") or ""),
                     "focused": str(item.get("focused") or ""),
                     "selected": [str(p) for p in selected if p]})
    return tabs


def ask_explorer(hwnd, run=subprocess.run, timeout=TIMEOUT):
    """The tabs of Explorer window `hwnd` (Windows 11 has several per window)."""
    script = script_for(hwnd)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    command = [powershell_path(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-EncodedCommand", encoded]
    try:
        result = run(command, capture_output=True, timeout=timeout,
                     creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except subprocess.TimeoutExpired:
        raise ExplorerError("File Explorer took too long to answer") from None
    except OSError as e:
        raise ExplorerError(f"PowerShell couldn't start: {e}") from None
    if result.returncode != 0 and not result.stdout:
        raise ExplorerError(f"PowerShell failed ({result.returncode})")
    return parse_output(result.stdout)


def active_tab(tabs, title):
    """The tab the user sees: the one whose name the window's title shows
    ("Kelas" or "Kelas - File Explorer"); the only one when there is one."""
    if not tabs:
        return None
    if len(tabs) == 1:
        return tabs[0]
    title = str(title or "").strip().casefold()
    for tab in tabs:
        name = tab["name"].strip().casefold()
        if name and (title == name or title.startswith(name + " - ") or
                     title.startswith(name + " \u2014 ")):
            return tab
    return tabs[0]


def chosen_item(tab):
    """(path, is_folder_itself): the focused item when it is selected, else
    the first selected one; with nothing selected, the folder shown."""
    if tab is None:
        return "", True
    selected = [p for p in tab["selected"] if p]
    if selected:
        for path in selected:
            if tab["focused"] and paths.same_path(path, tab["focused"]):
                return path, False
        return selected[0], False
    return tab["folder"], True


def selected_path(hwnd, ask=ask_explorer, title_of=window_title):
    """The path the user means in Explorer window `hwnd` (see chosen_item),
    or ("", True) when Explorer reported nothing."""
    tab = active_tab(ask(hwnd), title_of(hwnd))
    return chosen_item(tab)
