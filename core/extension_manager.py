# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import json
import zipfile
import importlib.util
import sys
import logging
import shutil
import hashlib
import urllib.request
import threading
from core.events import bus
import core.api
import core.constants

logger = logging.getLogger(__name__)
_app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
USER_EXTENSIONS_DIR = os.path.join(_app_data, "Hariku2", "extensions")
SYSTEM_EXTENSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "extensions"))
SCRATCHPAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scratchpad"))

# Alias kept for backward compatibility and the cache directory.
EXTENSIONS_DIR = USER_EXTENSIONS_DIR

LOADED_EXTENSIONS = {}

# Why an extension that Hariku tried to load didn't start, by id: the error it
# stopped with (the Extension Manager's Installed tab shows it).
LOAD_ERRORS = {}

# [SEC MED-3] Hardcoded list of official Hariku extension IDs.
# This prevents spoofing the [Official] badge via the manifest author field.
#
# HOW TO ADD A NEW OFFICIAL EXTENSION:
#   1. Add the extension folder ID (folder name / .hrk name without extension) here.
#   2. Also add the same ID to OFFICIAL_EXTENSION_IDS in:
#      tools/server/generate_trusted_hashes.py
#   3. Re-run generate_trusted_hashes.py and publish the new
#      trusted_extensions.json to the GitHub Pages path in core.endpoints
#      (TRUSTED_HASHES_URL, i.e. <pages>/security/trusted_extensions.json).
#   That's it. The [Official] badge will appear automatically.
_OFFICIAL_EXTENSION_IDS = frozenset([
    "developer_toolkit",
    "ghost_taskbar",
    "key_notifier",
    "ambience",
    "project_system",
    "window_teleporter",
    "markdown_reader",
    "lumina",
    "account_manager",
    "world_clock",
    "routines",
    "gcal_integration",
    "filter",
    "quick_expand",
    "weather",
    "briefing",
    "finance",
    "flight_radar",
    "clipboard_history",
    "sound_themes",
    "earthquake",
    "marine",
    "air_quality",
    "space",
    "edge_voices",
    "sleep_tracker",
    "piper_voices",
    "cockpit",
    "voice_control",
])


_REQUIRED_MANIFEST_FIELDS = ("name", "version", "description", "main", "author", "language",
                             "minimum_core_version")


def _version_tuple(text):
    """(major, minor) from "2.4", "2.4.0" or "2.10", or None if unreadable.
    Tuples compare correctly where float("2.10") < float("2.4") would not."""
    try:
        parts = [int(p) for p in str(text).strip().split(".")[:2]]
    except ValueError:
        return None
    return tuple(parts + [0] * (2 - len(parts)))


def needs_newer_core(manifest):
    """The minimum_core_version of a manifest (or store entry) when this Hariku
    is older than it, else ""."""
    required = str((manifest or {}).get("minimum_core_version") or "").strip()
    need = _version_tuple(required) if required else None
    have = _version_tuple(core.constants.CORE_VERSION)
    return required if need and have and need > have else ""


def too_old_for_core(manifest):
    """The Hariku version an extension was made for (its last_tested_core_version,
    else its minimum_core_version) when this Hariku no longer runs extensions
    that old (core.constants.EXTENSION_API_BACK_COMPAT), else ""."""
    manifest = manifest or {}
    made_for = str(manifest.get("last_tested_core_version")
                   or manifest.get("minimum_core_version") or "").strip()
    made = _version_tuple(made_for) if made_for else None
    oldest = _version_tuple(core.constants.EXTENSION_API_BACK_COMPAT)
    return made_for if made and oldest and made < oldest else ""


def _safe_extractall(zip_ref, dest_path):
    """
    [SEC CRIT-2] Safe ZIP extraction that prevents Zip Slip path traversal.

    A maliciously crafted .hrk could contain entries like '../../evil.bat'
    which would place files outside the intended extraction directory.
    This function validates every entry before extraction.
    """
    dest_real = os.path.realpath(dest_path)
    for member in zip_ref.infolist():
        member_real = os.path.realpath(os.path.join(dest_path, member.filename))
        if not member_real.startswith(dest_real + os.sep) and member_real != dest_real:
            raise ValueError(
                f"[Security] Zip Slip blocked: entry '{member.filename}' "
                f"would extract outside target directory."
            )
    zip_ref.extractall(dest_path)


# [SEC CRIT-1] Trusted extension hash registry URL (see core.endpoints).
# Hosts a JSON file: {"trusted": ["sha256hex1", "sha256hex2", ...]}
import core.endpoints
_TRUSTED_HASHES_URL = core.endpoints.TRUSTED_HASHES_URL

# In-memory cache for the session (None = not fetched yet, set = fetched)
_trusted_hash_cache = None
_trusted_hash_lock = threading.Lock()


def _sha256_file(path):
    """Compute SHA256 hex digest of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest().lower()


def _fetch_trusted_hashes():
    """
    [SEC CRIT-1] Fetch the server-hosted trusted extension hash list.
    Returns a set of lowercase SHA256 hex strings, or empty set on failure.
    """
    global _trusted_hash_cache
    with _trusted_hash_lock:
        if _trusted_hash_cache is not None:
            return _trusted_hash_cache
        try:
            req = urllib.request.Request(
                _TRUSTED_HASHES_URL,
                headers={"User-Agent": "HarikuV2/2.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                hashes = {h.lower() for h in data.get("trusted", [])}
                _trusted_hash_cache = hashes
                logger.info(f"[Security] Loaded {len(hashes)} trusted extension hashes from server.")
                return hashes
        except Exception as e:
            logger.info(f"[Security] Trusted extension hash list not available: {e}. "
                        f"All third-party .hrk extensions will require user consent.")
            _trusted_hash_cache = set()
            return set()


def _show_security_dialog(message, title):
    import wx
    import core.api
    parent = core.api._get_parent_window()
    
    dlg = wx.Dialog(parent, title=title, size=(500, 400))
    panel = wx.Panel(dlg)
    vbox = wx.BoxSizer(wx.VERTICAL)
    
    text_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
    text_ctrl.SetValue(message)
    
    btn_sizer = wx.StdDialogButtonSizer()
    btn_yes = wx.Button(panel, wx.ID_YES, "Yes, Load")
    btn_no = wx.Button(panel, wx.ID_NO, "No, Skip")
    
    btn_yes.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_YES))
    btn_no.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_NO))
    
    btn_sizer.AddButton(btn_yes)
    btn_sizer.AddButton(btn_no)
    btn_sizer.Realize()
    
    vbox.Add(text_ctrl, 1, wx.EXPAND | wx.ALL, 10)
    vbox.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
    
    panel.SetSizer(vbox)
    dlg.Centre()
    
    text_ctrl.SetFocus()
    result = dlg.ShowModal()
    dlg.Destroy()
    return result == wx.ID_YES


def _check_hrk_trust(hrk_path, ext_id):
    """
    [SEC CRIT-1] Verify that a .hrk file is trusted before loading.

    Trust hierarchy:
      1. If ext_id is in _OFFICIAL_EXTENSION_IDS → always trusted (bundled official).
      2. If file SHA256 is in server trusted hash list → trusted.
      3. Otherwise → show warning dialog, require explicit user consent.

    Returns True if the extension should be loaded, False to skip it.
    """
    # Official bundled extensions are always trusted
    if ext_id in _OFFICIAL_EXTENSION_IDS:
        return True

    file_hash = _sha256_file(hrk_path)
    trusted_hashes = _fetch_trusted_hashes()

    if file_hash in trusted_hashes:
        logger.info(f"[Security] Extension '{ext_id}' hash verified as trusted.")
        return True

    # Unknown extension — ask user
    logger.warning(
        f"[Security] Extension '{ext_id}' (sha256={file_hash}) is NOT in the "
        f"trusted hash list. Showing user consent dialog."
    )

    msg = (
        f"The extension \"{ext_id}\" is not recognized by Hariku's security registry.\n\n"
        f"Loading unverified extensions can be dangerous — they run with full access "
        f"to your files, keyboard, and network.\n\n"
        f"SHA256: {file_hash}\n\n"
        f"Do you trust this extension and want to load it anyway?"
    )

    import wx
    import threading

    if threading.current_thread() is threading.main_thread():
        return _show_security_dialog(msg, "Unverified Extension")
    else:
        consent = [False]
        event   = threading.Event()

        def _ask():
            consent[0] = _show_security_dialog(msg, "Unverified Extension")
            event.set()

        wx.CallAfter(_ask)
        event.wait(timeout=120)
        return consent[0]


def ensure_extensions_dir():
    if not os.path.exists(USER_EXTENSIONS_DIR):
        os.makedirs(USER_EXTENSIONS_DIR)

def _get_disabled_extensions():
    config = core.api.load_data("Core")
    return config.get("disabled_extensions", [])

def load_all_extensions():
    ensure_extensions_dir()
    logger.info(f"Scanning extensions in {SYSTEM_EXTENSIONS_DIR} and {USER_EXTENSIONS_DIR}")
    
    disabled = _get_disabled_extensions()

    # Collect everything to load, in priority order.
    # format: to_load[ext_id] = {"type": "folder"|"hrk", "path": "..."}
    to_load = {}

    # 1. System extensions (folders only) - lowest priority.
    if os.path.exists(SYSTEM_EXTENSIONS_DIR):
        for item in os.listdir(SYSTEM_EXTENSIONS_DIR):
            if item in (".cache", "__pycache__") or item in disabled: continue
            full_path = os.path.join(SYSTEM_EXTENSIONS_DIR, item)
            if os.path.isdir(full_path) and os.path.exists(os.path.join(full_path, "manifest.json")):
                to_load[item] = {"type": "folder", "path": full_path}
                
    # 2. User extensions (.hrk files) - medium priority.
    if os.path.exists(USER_EXTENSIONS_DIR):
        for item in os.listdir(USER_EXTENSIONS_DIR):
            if item.endswith(".hrk"):
                ext_id = item.replace(".hrk", "")
                if ext_id in disabled: continue
                to_load[ext_id] = {"type": "hrk", "path": os.path.join(USER_EXTENSIONS_DIR, item)}
                
    # 3. User extensions (folders) - high priority (developer mode in AppData).
    if os.path.exists(USER_EXTENSIONS_DIR):
        for item in os.listdir(USER_EXTENSIONS_DIR):
            if item in (".cache", "__pycache__") or item in disabled: continue
            full_path = os.path.join(USER_EXTENSIONS_DIR, item)
            if os.path.isdir(full_path) and os.path.exists(os.path.join(full_path, "manifest.json")):
                to_load[item] = {"type": "folder", "path": full_path}

    # 4. Scratchpad extensions (folders) - absolute priority (live development).
    config = core.api.load_data("Core")
    enable_scratchpad = config.get("enable_scratchpad", False)
    scratchpad_path = config.get("scratchpad_dir", "") or SCRATCHPAD_DIR
    
    if enable_scratchpad and os.path.exists(scratchpad_path):
        logger.info(f"Developer Scratchpad Mode enabled. Scanning: {scratchpad_path}")
        for item in os.listdir(scratchpad_path):
            if item in (".cache", "__pycache__") or item in disabled: continue
            full_path = os.path.join(scratchpad_path, item)
            if os.path.isdir(full_path) and os.path.exists(os.path.join(full_path, "manifest.json")):
                to_load[item] = {"type": "folder", "path": full_path}
                
    # --- Batch Security Prompt ---
    unverified = []
    trusted_hashes = _fetch_trusted_hashes()
    
    for ext_id, data in to_load.items():
        if data["type"] == "hrk" and ext_id not in _OFFICIAL_EXTENSION_IDS:
            fhash = _sha256_file(data["path"])
            if fhash not in trusted_hashes:
                unverified.append((ext_id, fhash))
                
    if unverified:
        msg = f"{len(unverified)} extensions are not recognized by Hariku's security registry:\n\n"
        for ext_id, fhash in unverified:
            msg += f"- {ext_id}\n"
            
        msg += "\nLoading unverified extensions can be dangerous — they run with full access to your files, keyboard, and network.\n\nDo you trust ALL of these extensions and want to load them anyway?"
        
        import wx
        import threading
        
        def _ask_batch():
            if threading.current_thread() is threading.main_thread():
                return _show_security_dialog(msg, "Unverified Extensions")
            else:
                consent = [False]
                ev = threading.Event()
                def _do_ask():
                    consent[0] = _show_security_dialog(msg, "Unverified Extensions")
                    ev.set()
                wx.CallAfter(_do_ask)
                ev.wait(timeout=120)
                return consent[0]
                
        if _ask_batch():
            # User accepted all, temporarily trust them in memory
            for _, fhash in unverified:
                _trusted_hash_cache.add(fhash)
        else:
            # User rejected, remove them from load queue
            for ext_id, _ in unverified:
                del to_load[ext_id]
                logger.warning(f"[Security] Batch rejected: '{ext_id}'")
    # -----------------------------
                
    # Now execute the load.
    for ext_id, data in to_load.items():
        if data["type"] == "folder":
            load_unpacked_extension(data["path"])
        else:
            load_zipped_extension(data["path"])

    # [Lifecycle] Call each extension's teardown() when the app shuts down.
    # (on_unload is emitted by DoQuit / restart / tray-quit.) Subscribe once.
    bus.subscribe("on_unload", unload_all_extensions)


def unload_all_extensions(*args, **kwargs):
    """
    [Lifecycle] Call the optional module-level teardown() on every loaded
    extension so it can stop timers/threads and release resources. Each call is
    isolated so one misbehaving extension can't block the others' cleanup.
    """
    for ext_id, data in list(LOADED_EXTENSIONS.items()):
        module = data.get("module")
        fn = getattr(module, "teardown", None)
        if callable(fn):
            try:
                fn()
            except Exception as e:
                logger.error(f"Error in teardown() of extension '{ext_id}': {e}")

def load_zipped_extension(hrk_path):
    ext_id = os.path.basename(hrk_path).replace(".hrk", "")
    extract_path = os.path.join(EXTENSIONS_DIR, ".cache", ext_id)
    mtime_file = os.path.join(extract_path, ".hrk_mtime")
    
    try:
        # [SEC CRIT-1] Verify trust before doing anything with this file.
        # This blocks on user consent dialog if the extension is unrecognized.
        if not _check_hrk_trust(hrk_path, ext_id):
            logger.warning(f"[Security] Extension '{ext_id}' rejected by user or trust check.")
            return

        current_mtime = str(os.path.getmtime(hrk_path))

        needs_extraction = True
        
        if os.path.exists(extract_path) and os.path.exists(mtime_file):
            with open(mtime_file, "r") as f:
                cached_mtime = f.read().strip()
            if cached_mtime == current_mtime:
                needs_extraction = False
                
        if needs_extraction:
            logger.info(f"Extracting new or updated extension: {hrk_path}")
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path)
                
            with zipfile.ZipFile(hrk_path, 'r') as zip_ref:
                _safe_extractall(zip_ref, extract_path)
                
            with open(mtime_file, "w") as f:
                f.write(current_mtime)
        else:
            logger.debug(f"Using cached extraction for: {hrk_path}")
            
        _load_extension_from_dir(extract_path, ext_id)
    except Exception as e:
        logger.exception(f"Failed to load {hrk_path}: {e}")
        LOAD_ERRORS[ext_id] = f"{type(e).__name__}: {e}"[:300]

def load_unpacked_extension(folder_path):
    ext_id = os.path.basename(folder_path)
    _load_extension_from_dir(folder_path, ext_id)

def _load_extension_from_dir(ext_dir, ext_id):
    manifest_path = os.path.join(ext_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        logger.error(f"Manifest not found in extension: {ext_id}")
        return False
        
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        # --- Strict Manifest Validation ---
        missing = [f for f in _REQUIRED_MANIFEST_FIELDS if f not in manifest]
        if missing:
            logger.error(f"Extension '{ext_id}' rejected. Missing required manifest fields: {missing}")
            return False
            
        required = _version_tuple(manifest["minimum_core_version"])
        current = _version_tuple(core.constants.CORE_VERSION)
        if required is None:
            logger.warning(f"Extension '{ext_id}' has an unreadable minimum_core_version: "
                           f"{manifest['minimum_core_version']!r}")
        elif current is not None and required > current:
            logger.error(f"Extension '{ext_id}' requires Core Version {manifest['minimum_core_version']}, "
                         f"but current is {core.constants.CORE_VERSION}")
            return False
        if too_old_for_core(manifest):
            logger.error(f"Extension '{ext_id}' is made for Hariku {too_old_for_core(manifest)}, older "
                         f"than {core.constants.EXTENSION_API_BACK_COMPAT}, the oldest this core runs")
            return False
        # ----------------------------------
            
        entry_point = manifest.get("main", "main.py")
        # [SEC HIGH-5] Validate entry_point to prevent path traversal via manifest
        entry_point = os.path.normpath(entry_point)
        if os.sep in entry_point or entry_point.startswith(".."):
            logger.error(f"Extension '{ext_id}' rejected: malicious 'main' path: {entry_point}")
            return False
        entry_path = os.path.join(ext_dir, entry_point)
        # Double-check with realpath
        if not os.path.realpath(entry_path).startswith(os.path.realpath(ext_dir)):
            logger.error(f"Extension '{ext_id}' rejected: 'main' escapes extension directory")
            return False
        
        if not os.path.exists(entry_path):
            logger.error(f"Entry point {entry_point} not found in extension: {ext_id}")
            LOAD_ERRORS[ext_id] = f"{entry_point} is missing"
            return False
            
        if ext_dir not in sys.path:
            sys.path.insert(0, ext_dir)
            
        lib_dir = os.path.join(ext_dir, "lib")
        if os.path.exists(lib_dir) and lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)

        spec = importlib.util.spec_from_file_location(f"hariku_ext.{ext_id}", entry_path)
        if spec is None:
            logger.error(f"Failed to create module spec for {entry_path}")
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module 
        
        spec.loader.exec_module(module)
        
        if hasattr(module, "register"):
            module.register(bus)
            
        is_unpacked = not ext_dir.startswith(os.path.join(EXTENSIONS_DIR, ".cache"))
        
        # [SEC MED-3] Official status determined by hardcoded ID list, not manifest author field.
        # Anyone can set "author": "rafli" in their manifest — don't trust it for security decisions.
        is_official = ext_id in _OFFICIAL_EXTENSION_IDS
        
        LOADED_EXTENSIONS[ext_id] = {
            "manifest": manifest,
            "module": module,
            "is_unpacked": is_unpacked,
            "is_official": is_official
        }
        
        LOAD_ERRORS.pop(ext_id, None)
        mode = "UNPACKED" if is_unpacked else "ZIPPED"
        badge = "[Official]" if is_official else "[Community]"
        logger.info(f"Successfully loaded extension [{mode}] {badge}: {manifest.get('name', ext_id)} v{manifest.get('version', '1.0')}")
        return True
    except Exception as e:
        logger.exception(f"Failed to load extension from dir {ext_dir}: {e}")
        LOAD_ERRORS[ext_id] = f"{type(e).__name__}: {e}"[:300]
        return False

def get_installed_extensions_info():
    ensure_extensions_dir()
    disabled = _get_disabled_extensions()
    info_dict = {}
    
    def scan_dir(target_dir):
        if not os.path.exists(target_dir): return
        for item in os.listdir(target_dir):
            if item in (".cache", "__pycache__"):
                continue
                
            full_path = os.path.join(target_dir, item)
            ext_id = item.replace(".hrk", "")
            is_unpacked = os.path.isdir(full_path)
            
            manifest = None
            if is_unpacked:
                m_path = os.path.join(full_path, "manifest.json")
                if os.path.exists(m_path):
                    with open(m_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
            elif item.endswith(".hrk"):
                try:
                    with zipfile.ZipFile(full_path, 'r') as z:
                        if "manifest.json" in z.namelist():
                            with z.open("manifest.json") as f:
                                manifest = json.load(f)
                except Exception:
                    pass
                    
            if manifest:
                author = manifest.get("author", "Unknown")
                info_dict[ext_id] = {
                    "id": ext_id,
                    "name": manifest.get("name", ext_id),
                    "version": manifest.get("version", "1.0"),
                    "author": author,
                    "is_official": (author.strip().lower() == "rafli"),
                    "description": manifest.get("description", "No description available."),
                    "is_enabled": ext_id not in disabled,
                    "is_unpacked": is_unpacked,
                    "path": full_path,
                    "minimum_core_version": str(manifest.get("minimum_core_version") or ""),
                    "last_tested_core_version": str(manifest.get("last_tested_core_version") or ""),
                    "missing_fields": [f for f in _REQUIRED_MANIFEST_FIELDS if f not in manifest],
                }
                
    scan_dir(SYSTEM_EXTENSIONS_DIR)
    scan_dir(USER_EXTENSIONS_DIR)
            
    return list(info_dict.values())

def toggle_extension(ext_id, enable=True):
    config = core.api.load_data("Core")
    disabled = config.get("disabled_extensions", [])
    
    if enable and ext_id in disabled:
        disabled.remove(ext_id)
    elif not enable and ext_id not in disabled:
        disabled.append(ext_id)
        
    config["disabled_extensions"] = disabled
    core.api.save_data("Core", config)
    
def uninstall_extension(ext_id):
    full_path_hrk = os.path.join(USER_EXTENSIONS_DIR, f"{ext_id}.hrk")
    full_path_dir = os.path.join(USER_EXTENSIONS_DIR, ext_id)
    
    try:
        if os.path.exists(full_path_hrk):
            os.remove(full_path_hrk)
        if os.path.exists(full_path_dir) and os.path.isdir(full_path_dir):
            shutil.rmtree(full_path_dir)
            
        cache_dir = os.path.join(USER_EXTENSIONS_DIR, ".cache", ext_id)
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            
        config = core.api.load_data("Core")
        disabled = config.get("disabled_extensions", [])
        if ext_id in disabled:
            disabled.remove(ext_id)
            config["disabled_extensions"] = disabled
            core.api.save_data("Core", config)
            
        return True
    except Exception as e:
        logger.error(f"Failed to uninstall {ext_id}: {e}")
        return False
