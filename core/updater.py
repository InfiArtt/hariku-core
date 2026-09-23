# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import urllib.request
import urllib.parse
import json
import logging
import threading
import os
import shutil
import subprocess
import tempfile
import hashlib
import wx
import core.constants
import core.endpoints
from core.speech import speak

logger = logging.getLogger(__name__)

# Nuitka defines __compiled__ in every module it compiles. Without it we are
# running from a source checkout, where CORE_VERSION isn't stamped by the release
# build and the installer would not update the checkout anyway.
RUNNING_FROM_SOURCE = "__compiled__" not in globals()

UPDATE_JSON_URL = core.endpoints.UPDATE_JSON_URL

# How many times a "recommended" update can be snoozed before it becomes forced
MAX_SNOOZE_COUNT = 3

# Snooze state (in-memory, resets on app restart — intentional)
_snooze_count = 0

# ---------------------------------------------------------------------------
# [SEC CRIT-4] Update integrity / trust configuration
# ---------------------------------------------------------------------------
# The auto-updater downloads an .exe and runs it silently, so a tampered or
# spoofed installer is a full remote-code-execution vector. Three independent
# layers now guard it:
#   1. The download URL must be HTTPS on a domain we own (below).
#   2. The SHA256 from version.json must match (fail-closed — see perform_update).
#   3. The installer's Authenticode signature is checked (see _verify_authenticode).
#
# Note: layers 1 & 2 come from the SAME server as the binary, so they do NOT
# protect against a compromised update server — only layer 3 (a signature made
# with a private key that never touches the server) does. Sign your installer
# and set REQUIRE_AUTHENTICODE_SIGNATURE = True for the strongest protection.

_ALLOWED_UPDATE_DOMAINS = core.endpoints.ALLOWED_DOWNLOAD_HOSTS

# When True, an update is REFUSED unless the installer carries a valid,
# trusted Authenticode signature. Leave False only while your installer is
# unsigned; flip to True the moment you start code-signing your builds.
REQUIRE_AUTHENTICODE_SIGNATURE = False

# Optional publisher pinning. When set (e.g. "PT Novarealm" or your cert's
# Common Name), a valid signature is additionally required to be issued to
# exactly this subject. Empty string = accept any valid, trusted signature.
EXPECTED_PUBLISHER_CN = ""


def _validate_update_url(url):
    """
    [SEC CRIT-4] Reject an installer/download URL that is not HTTPS under one of
    our own base URLs. The URL comes from server JSON, so without this a single
    poisoned manifest could point the silent installer at any file. Delegates to
    the central host- AND path-pinned policy in core.endpoints.
    Raises ValueError if the URL is not acceptable.
    """
    core.endpoints.assert_download_url(url)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_version(ver_str):
    """Convert '2.1.3' -> (2, 1, 3) for proper comparison."""
    try:
        parts = str(ver_str).strip().split(".")
        return tuple(int(p) for p in parts)
    except Exception:
        return (0,)


def _is_newer(server_ver_str, local_ver_str):
    return _parse_version(server_ver_str) > _parse_version(local_ver_str)


def _is_below_minimum(local_ver_str, min_ver_str):
    return _parse_version(local_ver_str) < _parse_version(min_ver_str)


# ---------------------------------------------------------------------------
# Update Dialogs — one per severity
# ---------------------------------------------------------------------------

class _BaseUpdateDialog(wx.Dialog):
    """Shared base for all update dialogs."""

    def __init__(self, parent, title, version, notes, accent_colour,
                 can_snooze=True, snooze_label="Remind Me Later"):
        super().__init__(parent, title=title,
                         size=(520, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Coloured banner
        banner = wx.Panel(panel, size=(-1, 8))
        banner.SetBackgroundColour(accent_colour)
        vbox.Add(banner, 0, wx.EXPAND)

        # Version label
        lbl_ver = wx.StaticText(panel, label=f"Version {version} is available")
        font = lbl_ver.GetFont()
        font.SetPointSize(13)
        font.MakeBold()
        lbl_ver.SetFont(font)
        vbox.Add(lbl_ver, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 15)

        # Release notes
        lbl_notes_title = wx.StaticText(panel, label="What's new:")
        vbox.Add(lbl_notes_title, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.tc_notes = wx.TextCtrl(panel, value=notes,
                                    style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
        vbox.Add(self.tc_notes, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Buttons
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_install = wx.Button(panel, label="Download & Install Now")
        self.btn_install.SetDefault()
        self.btn_install.Bind(wx.EVT_BUTTON, self._on_install)
        hbox.Add(self.btn_install, 0, wx.RIGHT, 10)

        if can_snooze:
            self.btn_snooze = wx.Button(panel, label=snooze_label)
            self.btn_snooze.Bind(wx.EVT_BUTTON, self._on_snooze)
            hbox.Add(self.btn_snooze, 0)

        vbox.Add(hbox, 0, wx.ALIGN_RIGHT | wx.ALL, 15)
        panel.SetSizer(vbox)
        self.Centre()

    def _on_install(self, event):
        self.EndModal(wx.ID_YES)

    def _on_snooze(self, event):
        self.EndModal(wx.ID_NO)


class CriticalUpdateDialog(_BaseUpdateDialog):
    """
    Red banner. No snooze button. If force_update=True the dialog is
    also made non-closable so the user must update.
    """
    def __init__(self, parent, version, notes, force=False):
        super().__init__(parent,
                         title="⚠ Critical Update Required" if force else "⚠ Critical Update",
                         version=version,
                         notes=notes,
                         accent_colour=wx.Colour(200, 40, 40),
                         can_snooze=not force)
        if force:
            # Block window close button
            self.Bind(wx.EVT_CLOSE, lambda e: None)


class RecommendedUpdateDialog(_BaseUpdateDialog):
    """Yellow banner. Snooze allowed up to MAX_SNOOZE_COUNT times."""
    def __init__(self, parent, version, notes, snooze_remaining):
        snooze_label = f"Remind Me Later ({snooze_remaining} skips left)"
        super().__init__(parent,
                         title="Update Recommended",
                         version=version,
                         notes=notes,
                         accent_colour=wx.Colour(210, 140, 0),
                         can_snooze=True,
                         snooze_label=snooze_label)


class OptionalUpdateDialog(_BaseUpdateDialog):
    """Subtle blue banner. Free to skip."""
    def __init__(self, parent, version, notes):
        super().__init__(parent,
                         title="Update Available",
                         version=version,
                         notes=notes,
                         accent_colour=wx.Colour(30, 120, 210),
                         can_snooze=True,
                         snooze_label="Skip This Version")


# ---------------------------------------------------------------------------
# Core update logic
# ---------------------------------------------------------------------------

def get_update_info():
    """Fetch version.json from server."""
    try:
        req = urllib.request.Request(UPDATE_JSON_URL, headers={"User-Agent": "HarikuV2/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to fetch update info: {e}")
        return None


def check_for_updates(interactive=True):
    """
    Main entry point. Runs the full update check logic.

    update_type values (from server version.json):
      - "critical"    : Red dialog, limited or no snooze, possible force
      - "recommended" : Yellow dialog, snooze up to MAX_SNOOZE_COUNT times
      - "optional"    : Blue dialog, freely skippable (default)
    """
    global _snooze_count

    if RUNNING_FROM_SOURCE and not interactive:
        logger.info("Running from source; skipping the automatic update check.")
        return False

    info = get_update_info()
    if not info:
        if interactive:
            def _err():
                speak("Failed to check for updates. Please check your internet connection.")
                wx.MessageBox("Failed to check for updates.\nPlease check your internet connection.",
                              "Update Error", wx.ICON_ERROR)
            wx.CallAfter(_err)
        return False

    latest_version  = info.get("latest_version", "0.0.0")
    update_type     = info.get("update_type", "optional").lower()
    download_url    = info.get("download_url", core.endpoints.DEFAULT_INSTALLER_URL)
    release_notes   = info.get("release_notes", "")
    min_version     = info.get("min_version_required", "0.0.0")
    force_update    = info.get("force_update", False)
    # [SEC CRIT-3] Read expected SHA256 from server manifest.
    # Server should include this field in version.json.
    expected_sha256 = info.get("sha256", "")

    local_version   = str(getattr(core.constants, "CORE_VERSION", "2.0.0"))

    # --- Check if below minimum required version (force regardless of type) ---
    if _is_below_minimum(local_version, min_version):
        update_type  = "critical"
        force_update = True

    # --- No update available ---
    if not _is_newer(latest_version, local_version):
        if interactive:
            def _ok():
                speak("You are already using the latest version of Hariku.")
                wx.MessageBox("Hariku is up to date!", "No Updates", wx.ICON_INFORMATION)
            wx.CallAfter(_ok)
        return False

    # --- Update available — pick dialog based on type ---
    logger.info(f"Update available: {latest_version} (type={update_type}, force={force_update})")

    def _show_dialog():
        global _snooze_count

        if update_type == "critical":
            speak("A critical update for Hariku is available.")
            dlg = CriticalUpdateDialog(None, latest_version, release_notes, force=force_update)

        elif update_type == "recommended":
            # If user has snoozed too many times, treat as critical
            if _snooze_count >= MAX_SNOOZE_COUNT:
                speak("An important update for Hariku is available. You have skipped it too many times.")
                dlg = CriticalUpdateDialog(None, latest_version, release_notes, force=False)
            else:
                remaining = MAX_SNOOZE_COUNT - _snooze_count
                speak("A recommended update for Hariku is available.")
                dlg = RecommendedUpdateDialog(None, latest_version, release_notes, snooze_remaining=remaining)

        else:  # optional
            speak("A new version of Hariku is available.")
            dlg = OptionalUpdateDialog(None, latest_version, release_notes)

        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            threading.Thread(
                target=perform_update,
                args=(download_url, expected_sha256),
                daemon=True
            ).start()
        else:
            # Snoozed or skipped
            if update_type == "recommended":
                _snooze_count += 1
                logger.info(f"Update snoozed ({_snooze_count}/{MAX_SNOOZE_COUNT})")

    wx.CallAfter(_show_dialog)
    return True


def _verify_sha256(file_path, expected_hex):
    """
    [SEC CRIT-3] Verify SHA256 checksum of a downloaded file.
    Raises ValueError if the checksum does not match.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    actual_hex = sha256.hexdigest().lower()
    expected_hex = expected_hex.lower()
    if actual_hex != expected_hex:
        raise ValueError(
            f"[Security] Checksum mismatch!\n"
            f"  Expected : {expected_hex}\n"
            f"  Actual   : {actual_hex}\n"
            f"The installer may be corrupted or tampered with."
        )
    logger.info(f"SHA256 verified OK: {actual_hex}")


# Well-known WinVerifyTrust return code: file carries no signature at all.
_TRUST_E_NOSIGNATURE = 0x800B0100


def _verify_authenticode(file_path):
    """
    [SEC CRIT-4] Check the Authenticode signature of a PE file via WinVerifyTrust.

    Unlike the SHA256 check, the signature is made with a private key that never
    lives on the update server, so a valid signature still holds even if the
    server (and thus version.json + the binary) is fully compromised.

    Returns one of: "valid"    — signed and trusted,
                    "unsigned" — no signature present,
                    "invalid"  — signature present but tampered/untrusted/expired,
                    "error"    — verification could not be performed.
    """
    if os.name != "nt":
        return "error"
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD),
                        ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        # WINTRUST_ACTION_GENERIC_VERIFY_V2
        action = GUID(0xaac56b, 0xcd44, 0x11d0,
                      (ctypes.c_ubyte * 8)(0x8c, 0xc2, 0x00, 0xc0, 0x4f, 0xc2, 0x95, 0xee))

        class WINTRUST_FILE_INFO(ctypes.Structure):
            _fields_ = [("cbStruct", wintypes.DWORD),
                        ("pcwszFilePath", wintypes.LPCWSTR),
                        ("hFile", wintypes.HANDLE),
                        ("pgKnownSubject", ctypes.c_void_p)]

        class WINTRUST_DATA(ctypes.Structure):
            _fields_ = [("cbStruct", wintypes.DWORD),
                        ("pPolicyCallbackData", ctypes.c_void_p),
                        ("pSIPClientData", ctypes.c_void_p),
                        ("dwUIChoice", wintypes.DWORD),
                        ("fdwRevocationChecks", wintypes.DWORD),
                        ("dwUnionChoice", wintypes.DWORD),
                        ("pFile", ctypes.POINTER(WINTRUST_FILE_INFO)),
                        ("dwStateAction", wintypes.DWORD),
                        ("hWVTStateData", wintypes.HANDLE),
                        ("pwszURLReference", wintypes.LPCWSTR),
                        ("dwProvFlags", wintypes.DWORD),
                        ("dwUIContext", wintypes.DWORD),
                        ("pSignatureSettings", ctypes.c_void_p)]

        WTD_UI_NONE = 2
        WTD_REVOKE_NONE = 0
        WTD_CHOICE_FILE = 1
        WTD_STATEACTION_VERIFY = 1
        WTD_STATEACTION_CLOSE = 2
        WTD_SAFER_FLAG = 0x00000100

        file_info = WINTRUST_FILE_INFO()
        file_info.cbStruct = ctypes.sizeof(WINTRUST_FILE_INFO)
        file_info.pcwszFilePath = file_path
        file_info.hFile = None
        file_info.pgKnownSubject = None

        data = WINTRUST_DATA()
        data.cbStruct = ctypes.sizeof(WINTRUST_DATA)
        data.dwUIChoice = WTD_UI_NONE
        data.fdwRevocationChecks = WTD_REVOKE_NONE
        data.dwUnionChoice = WTD_CHOICE_FILE
        data.pFile = ctypes.pointer(file_info)
        data.dwStateAction = WTD_STATEACTION_VERIFY
        data.dwProvFlags = WTD_SAFER_FLAG

        WinVerifyTrust = ctypes.windll.wintrust.WinVerifyTrust
        WinVerifyTrust.restype = wintypes.LONG

        rc = WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(data))

        # Always release the state data, whatever the result.
        data.dwStateAction = WTD_STATEACTION_CLOSE
        WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(data))

        rc &= 0xFFFFFFFF
        if rc == 0:
            return "valid"
        if rc == _TRUST_E_NOSIGNATURE:
            logger.warning("[Security] Installer is not Authenticode-signed.")
            return "unsigned"
        logger.warning(f"[Security] Installer signature check failed: 0x{rc:08X}")
        return "invalid"
    except Exception as e:
        logger.error(f"[Security] Authenticode verification error: {e}")
        return "error"


def _signature_subject_cns(file_path):
    """
    [SEC CRIT-4] Return the subject Common Names of every certificate embedded in
    the file's Authenticode signature (leaf + intermediates), e.g.
    ['Python Software Foundation', 'Microsoft ID Verified ...', ...].

    Enumerating the whole cert store is far more robust than parsing the signer
    info by hand (which is fragile with dual-signed / timestamped binaries).
    Publisher pinning then just asks whether the expected name is present: only
    the real leaf certificate carries the publisher's own organisation name, and
    an attacker cannot include it without the matching private key (which would
    also fail the WinVerifyTrust validity check above). Returns [] on any error.
    """
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        crypt32 = ctypes.windll.crypt32

        CERT_QUERY_OBJECT_FILE = 0x00000001
        CERT_QUERY_CONTENT_FLAG_PKCS7_SIGNED_EMBED = 1 << 10
        CERT_QUERY_FORMAT_FLAG_BINARY = 1 << 1
        CERT_NAME_SIMPLE_DISPLAY_TYPE = 4

        # Declare pointer-returning calls so 64-bit handles are not truncated.
        crypt32.CryptQueryObject.restype = wintypes.BOOL
        crypt32.CertEnumCertificatesInStore.restype = ctypes.c_void_p
        crypt32.CertEnumCertificatesInStore.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        crypt32.CertGetNameStringW.restype = wintypes.DWORD
        crypt32.CertGetNameStringW.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.LPWSTR, wintypes.DWORD]
        crypt32.CertCloseStore.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        crypt32.CryptMsgClose.argtypes = [ctypes.c_void_p]

        h_store = ctypes.c_void_p()
        h_msg = ctypes.c_void_p()
        ok = crypt32.CryptQueryObject(
            CERT_QUERY_OBJECT_FILE,
            ctypes.c_wchar_p(file_path),
            CERT_QUERY_CONTENT_FLAG_PKCS7_SIGNED_EMBED,
            CERT_QUERY_FORMAT_FLAG_BINARY,
            0, None, None, None,
            ctypes.byref(h_store), ctypes.byref(h_msg), None,
        )
        if not ok:
            return []

        names = []
        try:
            p_cert = crypt32.CertEnumCertificatesInStore(h_store, None)
            while p_cert:
                size = crypt32.CertGetNameStringW(
                    p_cert, CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, None, None, 0)
                if size > 1:
                    nb = ctypes.create_unicode_buffer(size)
                    crypt32.CertGetNameStringW(
                        p_cert, CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, None, nb, size)
                    if nb.value:
                        names.append(nb.value)
                p_cert = crypt32.CertEnumCertificatesInStore(h_store, p_cert)
        finally:
            if h_store:
                crypt32.CertCloseStore(h_store, 0)
            if h_msg:
                crypt32.CryptMsgClose(h_msg)
        return names
    except Exception as e:
        logger.error(f"[Security] Publisher enumeration error: {e}")
        return []


def _verify_installer_trust(installer_path, expected_sha256):
    """
    [SEC CRIT-4] Apply the full trust policy to a freshly downloaded installer.
    Raises ValueError (fail-closed) if the installer must not be executed.
    """
    # Layer 2: SHA256 is mandatory. Never run an unverified installer.
    if not expected_sha256:
        raise ValueError(
            "[Security] Update manifest is missing the 'sha256' field. "
            "Refusing to run an installer whose integrity cannot be verified."
        )
    _verify_sha256(installer_path, expected_sha256)  # raises on mismatch

    # Layer 3: Authenticode signature.
    sig_state = _verify_authenticode(installer_path)

    if sig_state == "invalid":
        # A present-but-broken signature always means tamper/untrusted — abort.
        raise ValueError(
            "[Security] Installer carries an INVALID Authenticode signature "
            "(tampered, expired, or from an untrusted publisher). Aborting update."
        )

    if REQUIRE_AUTHENTICODE_SIGNATURE and sig_state != "valid":
        raise ValueError(
            f"[Security] A valid Authenticode signature is required but the "
            f"installer is '{sig_state}'. Aborting update."
        )

    if sig_state == "valid" and EXPECTED_PUBLISHER_CN:
        cns = _signature_subject_cns(installer_path)
        logger.info(f"[Security] Installer signature subjects: {cns}")
        want = EXPECTED_PUBLISHER_CN.strip().lower()
        if not any(cn.strip().lower() == want for cn in cns):
            raise ValueError(
                f"[Security] Expected publisher {EXPECTED_PUBLISHER_CN!r} not found "
                f"in the installer's signature chain {cns}. Aborting update."
            )

    logger.info(f"[Security] Installer trust verified (signature={sig_state}).")


def perform_update(download_url, expected_sha256=""):
    """Download the installer, verify its integrity, then run it silently."""
    wx.CallAfter(speak, "Downloading update. Please wait.")
    logger.info(f"Downloading update from: {download_url}")

    installer_path = None
    try:
        # [SEC CRIT-4] Reject non-HTTPS / off-domain URLs before touching the network.
        _validate_update_url(download_url)

        # [SEC HIGH-2] Use a random temp filename to prevent TOCTOU race condition.
        # A predictable name like 'hariku_updater_latest.exe' could be replaced
        # by a local attacker during the 3-second sleep window.
        import tempfile
        tmp_fd, installer_path = tempfile.mkstemp(
            suffix=".exe", prefix="hariku_upd_",
            dir=tempfile.gettempdir()
        )
        os.close(tmp_fd)  # Close fd, we'll reopen via shutil

        req = urllib.request.Request(download_url, headers={"User-Agent": "HarikuV2/2.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, \
             open(installer_path, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)

        # [SEC CRIT-3 / CRIT-4] Fail-closed integrity + authenticity verification.
        # On any failure this raises, and the except block deletes the file and
        # notifies the user WITHOUT ever executing the installer.
        _verify_installer_trust(installer_path, expected_sha256)

        logger.info("Download complete. Launching installer...")
        wx.CallAfter(speak, "Download complete. Hariku will now close to install the update.")

        import time
        time.sleep(3)

        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [installer_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NOCANCEL", "/NORESTART"],
            creationflags=DETACHED_PROCESS
        )


        app = wx.GetApp()
        if app:
            wx.CallAfter(app.ExitMainLoop)

        time.sleep(0.5)
        os._exit(0)

    except Exception as e:
        # [SEC CRIT-4] Any verification failure must delete the suspect file and
        # abort — never fall through to execution.
        if installer_path and os.path.exists(installer_path):
            try:
                os.remove(installer_path)
            except OSError:
                pass
        # [SEC LOW-2] Log full exception detail privately; show generic message to user.
        logger.error(f"Update failed (details): {e}")
        wx.CallAfter(speak, "Update failed. Please try again later.")
        wx.CallAfter(wx.MessageBox,
            "Update failed. Please check your internet connection and try again.",
            "Error", wx.ICON_ERROR)
