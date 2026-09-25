# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Keeping the Dropbox sign-in (its refresh token) encrypted on this computer
with Windows' Data Protection API (CryptProtectData, through ctypes): only
the same Windows user on the same computer can decrypt it, so a copy of
Hariku's data folder is useless elsewhere. No wx here.

Stored as "dpapi1:" + base64 of the encrypted bytes.
"""

import base64
import ctypes
import ctypes.wintypes
import sys

PREFIX = "dpapi1:"
CRYPTPROTECT_UI_FORBIDDEN = 0x01
# Mixed into the encryption, so another program of the same user that calls
# CryptUnprotectData without it can't simply read the token back.
_ENTROPY = b"Hariku Dropbox sign-in"
_DESCRIPTION = "Hariku Dropbox"


class SecretError(Exception):
    """Encrypting or decrypting failed (another user or computer, or not Windows)."""


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_api = None


def _crypt():
    global _api
    if _api is None:
        if sys.platform != "win32":
            raise SecretError("Windows' Data Protection API is only on Windows")
        # Own instances, so these argtypes never change anyone else's.
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        blob_p = ctypes.POINTER(_Blob)
        crypt32.CryptProtectData.argtypes = [blob_p, ctypes.wintypes.LPCWSTR, blob_p,
                                             ctypes.c_void_p, ctypes.c_void_p,
                                             ctypes.wintypes.DWORD, blob_p]
        crypt32.CryptProtectData.restype = ctypes.wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [blob_p, ctypes.c_void_p, blob_p,
                                               ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.wintypes.DWORD, blob_p]
        crypt32.CryptUnprotectData.restype = ctypes.wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        _api = (crypt32, kernel32)
    return _api


def _blob(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _take(blob, kernel32):
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))


def protect(text):
    """Encrypt `text` for this Windows user: "dpapi1:..."."""
    crypt32, kernel32 = _crypt()
    data_in, keep_in = _blob(str(text).encode("utf-8"))
    entropy, keep_entropy = _blob(_ENTROPY)
    out = _Blob()
    if not crypt32.CryptProtectData(ctypes.byref(data_in), _DESCRIPTION, ctypes.byref(entropy),
                                    None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise SecretError(f"CryptProtectData failed ({ctypes.get_last_error()})")
    del keep_in, keep_entropy
    return PREFIX + base64.b64encode(_take(out, kernel32)).decode("ascii")


def unprotect(stored):
    """The text back from protect()'s result, or SecretError."""
    if not isinstance(stored, str) or not stored.startswith(PREFIX):
        raise SecretError("not an encrypted Hariku secret")
    try:
        raw = base64.b64decode(stored[len(PREFIX):], validate=True)
    except (ValueError, TypeError):
        raise SecretError("damaged secret") from None
    crypt32, kernel32 = _crypt()
    data_in, keep_in = _blob(raw)
    entropy, keep_entropy = _blob(_ENTROPY)
    out = _Blob()
    if not crypt32.CryptUnprotectData(ctypes.byref(data_in), None, ctypes.byref(entropy),
                                      None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise SecretError(f"CryptUnprotectData failed ({ctypes.get_last_error()})")
    del keep_in, keep_entropy
    try:
        return _take(out, kernel32).decode("utf-8")
    except UnicodeDecodeError:
        raise SecretError("damaged secret") from None
