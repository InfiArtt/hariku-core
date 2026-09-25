# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Watching the Dropbox folder for files written, added, renamed or removed,
with Windows' ReadDirectoryChangesW (through ctypes) on a thread of its own:
Windows tells us what changed, so the folder is never scanned, however big.
The read is overlapped, so stop() ends it within half a second. No wx here.
"""

import ctypes
import ctypes.wintypes
import logging
import struct
import threading

logger = logging.getLogger(__name__)

FILE_LIST_DIRECTORY = 0x0001
FILE_SHARE_ALL = 0x1 | 0x2 | 0x4
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE = ctypes.c_void_p(-1).value
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
ERROR_OPERATION_ABORTED = 995
ERROR_NOTIFY_ENUM_DIR = 1022

# File names (added, removed, renamed), writes and sizes; folders' own
# changes aren't asked for.
FILTER = 0x001 | 0x008 | 0x010

ADDED, REMOVED, MODIFIED, RENAMED_OLD, RENAMED_NEW = 1, 2, 3, 4, 5
ACTIONS = {ADDED: "added", REMOVED: "removed", MODIFIED: "modified",
           RENAMED_OLD: "renamed_from", RENAMED_NEW: "renamed_to"}
OVERFLOW = "overflow"
BUFFER_BYTES = 64 * 1024        # the most a network share takes


def parse_notifications(data):
    """[(action, relative path)] from a FILE_NOTIFY_INFORMATION buffer:
    action is "added", "removed", "modified", "renamed_from" or "renamed_to"."""
    found = []
    offset = 0
    size = len(data)
    for _guard in range(100000):
        if offset + 12 > size:
            break
        next_entry, action, length = struct.unpack_from("<III", data, offset)
        start = offset + 12
        name = bytes(data[start:start + length]).decode("utf-16-le", errors="replace")
        if action in ACTIONS and name:
            found.append((ACTIONS[action], name))
        if not next_entry:
            break
        offset += next_entry
    return found


class _Overlapped(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", ctypes.wintypes.DWORD), ("OffsetHigh", ctypes.wintypes.DWORD),
                ("hEvent", ctypes.wintypes.HANDLE)]


_kernel = None


def _kernel32():
    global _kernel
    if _kernel is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        H = ctypes.wintypes.HANDLE
        k.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
                                  ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD,
                                  ctypes.wintypes.DWORD, H]
        k.CreateFileW.restype = H
        k.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.BOOL,
                                   ctypes.wintypes.LPCWSTR]
        k.CreateEventW.restype = H
        k.ResetEvent.argtypes = [H]
        k.ResetEvent.restype = ctypes.wintypes.BOOL
        k.ReadDirectoryChangesW.argtypes = [H, ctypes.c_void_p, ctypes.wintypes.DWORD,
                                            ctypes.wintypes.BOOL, ctypes.wintypes.DWORD,
                                            ctypes.c_void_p, ctypes.POINTER(_Overlapped),
                                            ctypes.c_void_p]
        k.ReadDirectoryChangesW.restype = ctypes.wintypes.BOOL
        k.WaitForSingleObject.argtypes = [H, ctypes.wintypes.DWORD]
        k.WaitForSingleObject.restype = ctypes.wintypes.DWORD
        k.GetOverlappedResult.argtypes = [H, ctypes.POINTER(_Overlapped),
                                          ctypes.POINTER(ctypes.wintypes.DWORD),
                                          ctypes.wintypes.BOOL]
        k.GetOverlappedResult.restype = ctypes.wintypes.BOOL
        k.CancelIoEx.argtypes = [H, ctypes.POINTER(_Overlapped)]
        k.CancelIoEx.restype = ctypes.wintypes.BOOL
        k.CloseHandle.argtypes = [H]
        k.CloseHandle.restype = ctypes.wintypes.BOOL
        _kernel = k
    return _kernel


class FolderWatcher:
    """Watches `root` and everything in it. on_events([(action, relative
    path)]) is called on the watcher's thread; ("overflow", "") when Windows
    lost track (too much at once). on_error(message) when watching stopped
    by itself (the folder was removed or moved)."""

    def __init__(self, root, on_events, on_error=None):
        self.root = root
        self._on_events = on_events
        self._on_error = on_error
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="dropbox-watch")
        self._thread.start()
        return self

    def stop(self, wait=2.0):
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(wait)

    def alive(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        try:
            self._watch()
        except Exception as e:
            logger.exception("[Dropbox] Watching the folder failed")
            self._report(str(e))

    def _report(self, message):
        if self._on_error is not None and not self._stop.is_set():
            try:
                self._on_error(message)
            except Exception:
                logger.exception("[Dropbox] Reporting a watcher error failed")

    def _watch(self):
        k = _kernel32()
        handle = k.CreateFileW(self.root, FILE_LIST_DIRECTORY, FILE_SHARE_ALL, None, OPEN_EXISTING,
                               FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED, None)
        if not handle or handle == INVALID_HANDLE:
            self._report(f"cannot open the folder ({ctypes.get_last_error()})")
            return
        event = k.CreateEventW(None, True, False, None)
        # DWORD-aligned, as ReadDirectoryChangesW requires.
        buffer = (ctypes.c_uint32 * (BUFFER_BYTES // 4))()
        try:
            while not self._stop.is_set():
                overlapped = _Overlapped()
                overlapped.hEvent = event
                k.ResetEvent(event)
                if not k.ReadDirectoryChangesW(handle, ctypes.byref(buffer), BUFFER_BYTES, True,
                                               FILTER, None, ctypes.byref(overlapped), None):
                    self._report(f"cannot watch the folder ({ctypes.get_last_error()})")
                    return
                while True:
                    state = k.WaitForSingleObject(event, 500)
                    if state == WAIT_OBJECT_0:
                        break
                    if self._stop.is_set():
                        k.CancelIoEx(handle, ctypes.byref(overlapped))
                        done = ctypes.wintypes.DWORD(0)
                        k.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(done),
                                              True)
                        return
                    if state != WAIT_TIMEOUT:
                        self._report(f"waiting failed ({ctypes.get_last_error()})")
                        return
                done = ctypes.wintypes.DWORD(0)
                if not k.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(done),
                                             False):
                    error = ctypes.get_last_error()
                    if error == ERROR_NOTIFY_ENUM_DIR:
                        self._deliver([(OVERFLOW, "")])
                        continue
                    if error != ERROR_OPERATION_ABORTED:
                        self._report(f"reading changes failed ({error})")
                    return
                if done.value == 0:
                    self._deliver([(OVERFLOW, "")])
                    continue
                self._deliver(parse_notifications(ctypes.string_at(buffer, done.value)))
        finally:
            k.CloseHandle(handle)
            if event:
                k.CloseHandle(event)

    def _deliver(self, events):
        if events and not self._stop.is_set():
            try:
                self._on_events(events)
            except Exception:
                logger.exception("[Dropbox] Handling folder changes failed")
