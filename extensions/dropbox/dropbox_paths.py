# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The Dropbox folder on this computer: where the desktop app keeps it
(info.json), turning a path in it into a Dropbox path and back (Windows
paths ignore case, so the mapping does too), the files Dropbox never syncs,
and a file's size, time and attributes read without opening it, so an
online-only file is never downloaded by looking at it. No wx here.
"""

import ctypes
import ctypes.wintypes
import json
import os
import sys

# Windows file attributes that mean "online-only": reading the file would
# download it. Such files are left alone.
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_TEMPORARY = 0x100
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
ONLINE_ONLY = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

# Names Dropbox doesn't sync, or that are only a moment's scratch.
IGNORED_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", "icon\r", ".dropbox", ".dropbox.attr",
                 ".dropbox.cache"}
IGNORED_PREFIXES = ("~$", ".~lock")
IGNORED_SUFFIXES = (".tmp", ".crdownload", ".partial", ".part")
IGNORED_FOLDERS = {".dropbox.cache"}
IGNORE_STREAM = "com.dropbox.ignored"     # Dropbox's "don't sync this" marker


# ------------------------------------------------------------
# Where the Dropbox folder is
# ------------------------------------------------------------

def info_json_paths(environ=None):
    """Where the desktop app writes info.json (newer versions in LOCALAPPDATA)."""
    environ = os.environ if environ is None else environ
    found = []
    for var in ("LOCALAPPDATA", "APPDATA"):
        base = environ.get(var)
        if base:
            found.append(os.path.join(base, "Dropbox", "info.json"))
    return found


def parse_info(text):
    """{"personal": path, "business": path} from info.json's text (the ones
    it has). Unreadable text gives {}."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    found = {}
    if isinstance(data, dict):
        for kind in ("personal", "business"):
            entry = data.get(kind)
            path = entry.get("path") if isinstance(entry, dict) else None
            if isinstance(path, str) and path.strip():
                found[kind] = os.path.normpath(path.strip())
    return found


def read_info(environ=None, read=None):
    """The Dropbox folders the desktop app has on this computer."""
    for path in info_json_paths(environ):
        try:
            if read is not None:
                text = read(path)
            else:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        found = parse_info(text)
        if found:
            return found
    return {}


def pick_folder(folders, business):
    """The folder for the signed-in account: its business one for a business
    (team) account, else the personal one. None when that one isn't here: a
    folder of another account would map to the wrong files."""
    if not folders:
        return None
    return folders.get("business" if business else "personal")


# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

def _clean(path):
    path = str(path or "").replace("/", "\\")
    if path.startswith("\\\\?\\") and not path.startswith("\\\\?\\UNC\\"):
        path = path[4:]
    while len(path) > 3 and path.endswith("\\"):
        path = path[:-1]
    return path


def same_path(a, b):
    return _clean(a).casefold() == _clean(b).casefold()


def to_dropbox(local, root):
    """The Dropbox path of `local` under `root` ("/Kelas/tugas.docx"), "" for
    the root itself, or None when it isn't in the Dropbox folder. Case
    doesn't matter (Windows paths ignore it)."""
    if not local or not root:
        return None
    local, root = _clean(local), _clean(root)
    if local.casefold() == root.casefold():
        return ""
    prefix = root if root.endswith("\\") else root + "\\"
    if not local.casefold().startswith(prefix.casefold()):
        return None
    rest = local[len(prefix):].strip("\\")
    return "/" + rest.replace("\\", "/") if rest else ""


def to_local(dropbox_path, root):
    """The path on this computer of a Dropbox path under `root`."""
    rest = str(dropbox_path or "").strip("/").replace("/", "\\")
    root = _clean(root)
    return root if not rest else (root.rstrip("\\") + "\\" + rest)


def key(dropbox_path):
    """A Dropbox path compared the way Dropbox does: without case."""
    return str(dropbox_path or "").casefold()


def name_of(path):
    """The last part of a local or Dropbox path."""
    path = str(path or "").replace("\\", "/").rstrip("/")
    return path.rsplit("/", 1)[-1]


def parent_name(dropbox_path):
    """The folder a Dropbox path is in ("Kelas" for "/Kelas/tugas.docx"),
    "" at the top."""
    parts = str(dropbox_path or "").strip("/").split("/")
    return parts[-2] if len(parts) >= 2 else ""


def parent_path(dropbox_path):
    path = str(dropbox_path or "").rstrip("/")
    return path.rsplit("/", 1)[0] if "/" in path else ""


def ignored_name(name):
    """A name Dropbox doesn't sync, or a moment's scratch (Office's "~$",
    LibreOffice's ".~lock", ".tmp", a browser's unfinished download)."""
    lower = str(name or "").casefold()
    if not lower or lower in IGNORED_NAMES:
        return True
    return lower.startswith(IGNORED_PREFIXES) or lower.endswith(IGNORED_SUFFIXES)


def ignored_relative(relative):
    """Whether a path relative to the Dropbox folder ("Kelas\\~$tugas.docx")
    is one to leave alone: an ignored name, or anything in the desktop app's
    own folders (.dropbox.cache)."""
    parts = [p for p in str(relative or "").replace("/", "\\").split("\\") if p]
    if not parts:
        return True
    if any(p.casefold() in IGNORED_FOLDERS for p in parts[:-1]):
        return True
    return ignored_name(parts[-1])


# ------------------------------------------------------------
# A file's details without opening it
# ------------------------------------------------------------

class FileInfo:
    """What the directory knows of a file: `size` (bytes), `mtime` (seconds
    since 1970, UTC) and Windows `attributes`."""

    def __init__(self, size, mtime, attributes=0):
        self.size = int(size)
        self.mtime = float(mtime)
        self.attributes = int(attributes)

    @property
    def is_dir(self):
        return bool(self.attributes & FILE_ATTRIBUTE_DIRECTORY)

    @property
    def online_only(self):
        return bool(self.attributes & ONLINE_ONLY)

    @property
    def temporary(self):
        return bool(self.attributes & FILE_ATTRIBUTE_TEMPORARY)

    def __repr__(self):
        return f"FileInfo({self.size}, {self.mtime}, 0x{self.attributes:x})"


class _AttributeData(ctypes.Structure):
    _fields_ = [("dwFileAttributes", ctypes.wintypes.DWORD),
                ("ftCreationTime", ctypes.wintypes.FILETIME),
                ("ftLastAccessTime", ctypes.wintypes.FILETIME),
                ("ftLastWriteTime", ctypes.wintypes.FILETIME),
                ("nFileSizeHigh", ctypes.wintypes.DWORD),
                ("nFileSizeLow", ctypes.wintypes.DWORD)]


_get_attributes = None
_EPOCH_AS_FILETIME = 116444736000000000


def _attributes_api():
    global _get_attributes
    if _get_attributes is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        fn = kernel32.GetFileAttributesExW
        fn.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p]
        fn.restype = ctypes.wintypes.BOOL
        _get_attributes = fn
    return _get_attributes


def file_info(path):
    """A FileInfo of `path`, or None when it isn't there. On Windows it asks
    GetFileAttributesExW, which reads the directory entry and never opens the
    file (so an online-only file stays in the cloud)."""
    if sys.platform != "win32":
        try:
            st = os.lstat(path)
        except OSError:
            return None
        return FileInfo(st.st_size, st.st_mtime, getattr(st, "st_file_attributes", 0))
    data = _AttributeData()
    if not _attributes_api()(str(path), 0, ctypes.byref(data)):   # GetFileExInfoStandard
        return None
    written = (data.ftLastWriteTime.dwHighDateTime << 32) | data.ftLastWriteTime.dwLowDateTime
    size = (data.nFileSizeHigh << 32) | data.nFileSizeLow
    return FileInfo(size, (written - _EPOCH_AS_FILETIME) / 10_000_000, data.dwFileAttributes)


def marked_ignored(path, root, exists=os.path.exists):
    """Whether the user told Dropbox not to sync this file or a folder it is
    in (the com.dropbox.ignored stream). Only asked of files that are on
    this computer, never of online-only ones."""
    root = _clean(root).casefold()
    current = _clean(path)
    for _step in range(64):
        try:
            if exists(current + ":" + IGNORE_STREAM):
                return True
        except (OSError, ValueError):
            pass
        parent = os.path.dirname(current)
        if not parent or parent == current or _clean(parent).casefold() == root \
                or not _clean(parent).casefold().startswith(root):
            return False
        current = parent
    return False


def folder_matches(local_names, server_names):
    """Whether the folder on this computer looks like the signed-in account's
    Dropbox: most of its top-level names are also on the server. An empty
    folder matches. (The desktop app may be signed in to another account.)"""
    local = {n.casefold() for n in local_names if not ignored_name(n)}
    if not local:
        return True
    server = {n.casefold() for n in server_names}
    found = len(local & server)
    return found * 2 >= len(local)
