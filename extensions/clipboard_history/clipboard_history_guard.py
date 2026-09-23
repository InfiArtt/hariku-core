# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tells whether the text now on the clipboard was marked private by the app that
copied it. Password managers (KeePass, 1Password, Bitwarden, ...) add extra
registered clipboard formats next to the text, the same ones Windows' own
clipboard history (Win+V) honours:

  ExcludeClipboardContentFromMonitorProcessing  present -> private
  Clipboard Viewer Ignore                       present -> private (older convention)
  CanIncludeInClipboardHistory                  a DWORD; 0 -> private

Presence is checked with IsClipboardFormatAvailable, which does not open the
clipboard; it is only opened to read the DWORD when that format is there. If it
cannot be read, the copy counts as private.

The Windows functions come from private ctypes.WinDLL handles, so declaring
their argtypes never changes the shared ctypes.windll objects other code uses.
"""

import ctypes
import logging

logger = logging.getLogger(__name__)

EXCLUDE_FORMAT = "ExcludeClipboardContentFromMonitorProcessing"
VIEWER_IGNORE_FORMAT = "Clipboard Viewer Ignore"
HISTORY_FORMAT = "CanIncludeInClipboardHistory"


def is_private(has_format, read_dword):
    """The decision alone. has_format(name) -> bool; read_dword(name) -> int,
    or None when the value could not be read."""
    if has_format(EXCLUDE_FORMAT) or has_format(VIEWER_IGNORE_FORMAT):
        return True
    if has_format(HISTORY_FORMAT):
        value = read_dword(HISTORY_FORMAT)
        return value is None or value == 0
    return False


def load_windows_api():
    """(user32, kernel32) as private handles with the signatures declared."""
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE

    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    return user32, kernel32


class WindowsClipboard:
    """is_private() for the real clipboard. user32/kernel32 can be injected
    (tests); by default they are loaded with load_windows_api()."""

    def __init__(self, user32=None, kernel32=None):
        if user32 is None or kernel32 is None:
            try:
                user32, kernel32 = load_windows_api()
            except (OSError, AttributeError, ValueError, ImportError) as e:
                logger.warning(f"[Clipboard History] Clipboard formats cannot be checked: {e}")
                user32 = kernel32 = None
        self._user32 = user32
        self._kernel32 = kernel32
        self._format_ids = {}

    @property
    def available(self):
        return self._user32 is not None

    def _format_id(self, name):
        if name not in self._format_ids:
            self._format_ids[name] = int(self._user32.RegisterClipboardFormatW(name) or 0)
        return self._format_ids[name]

    def has_format(self, name):
        format_id = self._format_id(name)
        return bool(format_id) and bool(self._user32.IsClipboardFormatAvailable(format_id))

    def read_dword(self, name):
        format_id = self._format_id(name)
        if not format_id or not self._user32.OpenClipboard(None):
            return None
        try:
            handle = self._user32.GetClipboardData(format_id)
            if not handle:
                return None
            pointer = self._kernel32.GlobalLock(handle)
            if not pointer:
                return None
            try:
                if self._kernel32.GlobalSize(handle) < ctypes.sizeof(ctypes.c_uint32):
                    return None
                return ctypes.c_uint32.from_address(pointer).value
            finally:
                self._kernel32.GlobalUnlock(handle)
        finally:
            self._user32.CloseClipboard()

    def is_private(self):
        if self._user32 is None:
            return False
        return is_private(self.has_format, self.read_dword)
