# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import wx
import os
import json
import logging
import sys

logger = logging.getLogger(__name__)

# Reference to the main window so API functions can reach it.
# main_window.py fills this in automatically when the app starts.
main_window_instance = None

def get_selected_date():
    """
    Return the date currently highlighted in the calendar.
    Format string: 'YYYY-MM-DD'
    """
    if main_window_instance and hasattr(main_window_instance, 'calendar'):
        wx_date = main_window_instance.calendar.GetDate()
        return wx_date.Format("%Y-%m-%d")
    return None

def set_selected_date(date_str):
    """
    Force the calendar to jump to a specific date.
    Expected format: 'YYYY-MM-DD'
    """
    if main_window_instance and hasattr(main_window_instance, 'calendar'):
        try:
            new_date = wx.DateTime()
            # Parse the format string into a wx.DateTime object.
            success = new_date.ParseFormat(date_str, "%Y-%m-%d")
            
            if success:
                main_window_instance.calendar.SetDate(new_date)
                return True
        except Exception as e:
            pass
    return False

# --- Storage API ---

# Global storage directory.
_app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
USER_DATA_DIR = os.path.join(_app_data, "Hariku2")
DATA_DIR = os.path.join(USER_DATA_DIR, "data")

def get_data_path(extension_name):
    """Return the JSON file path for a given extension."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # Sanitize the extension name for filename safety.
    safe_name = "".join(c for c in extension_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    return os.path.join(DATA_DIR, f"{safe_name}.json")

def atomic_write_json(path, data):
    """
    [Stability] Write JSON atomically so a crash or power loss mid-write can never
    leave a truncated/corrupt file. Writes to a temp file in the same directory,
    flushes+fsyncs it, keeps one '.bak' of the previous good copy, then atomically
    replaces the target (os.replace is atomic on Windows and POSIX).
    Raises on failure (after cleaning up the temp file).
    """
    import tempfile
    import shutil
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # Preserve the last known-good file as a backup before replacing.
        if os.path.exists(path):
            try:
                shutil.copy2(path, path + ".bak")
            except OSError:
                pass
        os.replace(tmp_path, path)
        return True
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

def load_data(extension_name):
    """Load an extension's JSON data as a dictionary.
    [Stability] Only if the main file EXISTS but is corrupt does it fall back to
    the '.bak' backup. A missing main file means 'no data' (return {})."""
    path = get_data_path(extension_name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Gagal memuat data {extension_name}: {e}")
        bak = path + ".bak"
        if os.path.exists(bak):
            try:
                with open(bak, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.warning(f"Data '{extension_name}' rusak; dipulihkan dari backup (.bak).")
                return data
            except Exception as e2:
                logger.error(f"Backup data {extension_name} juga gagal dimuat: {e2}")
    return {}

def save_data(extension_name, data_dict):
    """Save a dictionary into the extension's JSON file (atomically)."""
    path = get_data_path(extension_name)
    try:
        atomic_write_json(path, data_dict)
        return True
    except Exception as e:
        logger.error(f"Gagal menyimpan data {extension_name}: {e}")
        return False

# --- Timer API (Non-Blocking) ---

def set_timeout(milliseconds, callback, *args, **kwargs):
    """
    Run a function after X milliseconds.
    Returns the timer object; call .Stop() to cancel it.
    """
    # wx.CallLater is safe to use on the GUI thread.
    timer = wx.CallLater(milliseconds, callback, *args, **kwargs)
    return timer

class _IntervalTimer(wx.Timer):
    def __init__(self, callback, *args, **kwargs):
        super().__init__()
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def Notify(self):
        try:
            self.callback(*self.args, **self.kwargs)
        except Exception as e:
            logger.error(f"Error in IntervalTimer: {e}")

def set_interval(milliseconds, callback, *args, **kwargs):
    """
    Run a function repeatedly every X milliseconds.
    Returns the timer object; call .Stop() to stop it.
    """
    timer = _IntervalTimer(callback, *args, **kwargs)
    timer.Start(milliseconds)
    return timer

# --- UI Dialog API ---

def _get_parent_window():
    app = wx.GetApp()
    if app:
        active = wx.GetActiveWindow()
        if active:
            return active
    return main_window_instance

def show_message(title, message):
    """Show a message dialog box (OK only)."""
    parent = _get_parent_window()
    if parent:
        dlg = wx.MessageDialog(parent, message, title, wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

def prompt_yes_no(title, message):
    """Ask a Yes/No question, returning True/False."""
    parent = _get_parent_window()
    if parent:
        dlg = wx.MessageDialog(parent, message, title, wx.YES_NO | wx.ICON_QUESTION)
        result = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        return result
    return False

def prompt_text(title, message, default_value=""):
    """Prompt for a short text input."""
    parent = _get_parent_window()
    if parent:
        dlg = wx.TextEntryDialog(parent, message, title, default_value)
        if dlg.ShowModal() == wx.ID_OK:
            val = dlg.GetValue()
            dlg.Destroy()
            return val
        dlg.Destroy()
    return None

def prompt_multiline(title, message, default_value=""):
    """Prompt for a long (multiline) text input."""
    parent = _get_parent_window()
    if parent:
        dlg = wx.TextEntryDialog(parent, message, title, default_value, style=wx.OK | wx.CANCEL | wx.TE_MULTILINE)
        if dlg.ShowModal() == wx.ID_OK:
            val = dlg.GetValue()
            dlg.Destroy()
            return val
        dlg.Destroy()
    return None

def show_toast(title, message, flags=wx.ICON_INFORMATION):
    """
    Show a native system notification (e.g. a Windows toast in the bottom-right corner).
    flags: wx.ICON_INFORMATION, wx.ICON_WARNING, or wx.ICON_ERROR
    """
    import wx.adv
    parent = _get_parent_window()
    if parent:
        toast = wx.adv.NotificationMessage(title, message, parent=parent, flags=flags)
        toast.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)

# --- OS Context API ---

def get_active_window_info():
    """
    Get information about the currently active (focused) window in Windows.
    Returns a dict: {"title": "Window Title", "process": "process_name.exe"}
    """
    import ctypes
    import ctypes.wintypes
    
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"title": "", "process": ""}
            
        # Get Title
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        
        # Get Process Name
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        process_name = ""
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        
        h_process = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if h_process:
            exe_buf = ctypes.create_unicode_buffer(260)
            if psapi.GetModuleBaseNameW(h_process, None, exe_buf, 260) > 0:
                process_name = exe_buf.value
            kernel32.CloseHandle(h_process)
            
        return {"title": title, "process": process_name}
    except Exception as e:
        logger.error(f"Error getting active window info: {e}")
        return {"title": "", "process": ""}

def get_user_idle_time():
    """Return the time (in seconds) since the user last touched the keyboard/mouse."""
    import ctypes
    import ctypes.wintypes
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.wintypes.UINT),
                    ("dwTime", ctypes.wintypes.DWORD)]
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
    except Exception as e:
        logger.error(f"Error getting idle time: {e}")
    return 0.0

def get_power_status():
    """
    Return a power-status dict:
    {"ac_line_status": 1 (plugged in) or 0 (battery), "battery_percent": 0-100, "charging": bool}
    """
    import ctypes
    import ctypes.wintypes
    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.wintypes.BYTE),
                    ("BatteryFlag", ctypes.wintypes.BYTE),
                    ("BatteryLifePercent", ctypes.wintypes.BYTE),
                    ("SystemStatusFlag", ctypes.wintypes.BYTE),
                    ("BatteryLifeTime", ctypes.wintypes.DWORD),
                    ("BatteryFullLifeTime", ctypes.wintypes.DWORD)]
    try:
        status = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return {
                "ac_line_status": status.ACLineStatus,
                "battery_percent": status.BatteryLifePercent,
                "charging": bool(status.BatteryFlag & 8)
            }
    except Exception as e:
        logger.error(f"Error getting power status: {e}")
    return {"ac_line_status": 255, "battery_percent": 255, "charging": False}

def is_network_online():
    """Return True if the computer is connected to the internet."""
    import ctypes
    import ctypes.wintypes
    try:
        flags = ctypes.wintypes.DWORD()
        return bool(ctypes.windll.wininet.InternetGetConnectedState(ctypes.byref(flags), 0))
    except Exception as e:
        logger.error(f"Error checking network state: {e}")
        return True # Fallback assume online

# --- Clipboard API ---

def set_clipboard(text):
    """Copy text to the OS clipboard using pyperclip."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception as e:
        logger.error(f"Clipboard set error: {e}")
        return False

def get_clipboard():
    """Get text from the OS clipboard using pyperclip."""
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception as e:
        logger.error(f"Failed to get clipboard: {e}")
        return ""

def restart_app(safe_mode=False):
    """
    Fully restart the Hariku application.
    Saves all state (via on_unload) then relaunches the process.
    If safe_mode=True, add the --safe-mode flag to the arguments.
    """
    import sys
    import os
    import subprocess
    import wx
    from core.events import bus

    logger.info(f"Restarting application... (safe_mode={safe_mode})")

    # Tell every module to save its state.
    bus.emit("on_unload")
    
    DETACHED_PROCESS = 0x00000008
    
    logger.info(f"  sys.executable={sys.executable} (exists={os.path.exists(sys.executable)})")
    logger.info(f"  sys.argv={sys.argv} (argv[0] exists={os.path.exists(sys.argv[0])})")
    
    try:
        # [SEC MED-4] Only forward known-safe arguments on restart to prevent argument injection.
        _ALLOWED_RESTART_ARGS = frozenset(["--safe-mode", "--debug"])
        base_argv = [a for a in sys.argv[1:]
                     if a in _ALLOWED_RESTART_ARGS and a != "--safe-mode"]
        if safe_mode:
            base_argv.append("--safe-mode")

        if os.path.exists(sys.executable):
            if os.path.abspath(sys.executable) == os.path.abspath(sys.argv[0]):
                cmd = [sys.executable] + base_argv
            else:
                cmd = [sys.executable, sys.argv[0]] + base_argv
        elif os.path.exists(sys.argv[0]):
            cmd = [os.path.abspath(sys.argv[0])] + base_argv
        else:
            logger.error(f"Tidak bisa menemukan executable manapun untuk restart!")
            return
        
        logger.info(f"  Restart command: {cmd}")
        subprocess.Popen(cmd, creationflags=DETACHED_PROCESS)
    except Exception as e:
        logger.error(f"Gagal melakukan restart: {e}")
    
    # Kill the current process.
    app = wx.GetApp()
    if app:
        app.ExitMainLoop()

    os._exit(0)  # os._exit(0) makes the process die immediately without delay.

def get_storage_dir(ext_id):
    """
    Return the absolute path to a dedicated storage folder for a given extension.
    Safe for storing SQLite databases, images, or large files.
    """
    # [SEC HIGH-1] Sanitize ext_id to prevent path traversal (e.g. "../../Windows")
    safe_id = "".join(c for c in ext_id if c.isalnum() or c in ("-", "_")).strip()
    if not safe_id:
        raise ValueError(f"[Security] Invalid extension ID for storage: {ext_id!r}")
    storage_dir = os.path.join(DATA_DIR, "extensions", safe_id)
    # Paranoia check: verify realpath stays inside DATA_DIR (a junction or
    # link inside it could point elsewhere). The parent folders are made
    # first: realpath() only expands what exists, so comparing a path that
    # exists with one that doesn't (another process creating it meanwhile)
    # could compare a short 8.3 name ("RUNNER~1") with the long one.
    os.makedirs(os.path.join(DATA_DIR, "extensions"), exist_ok=True)
    base = os.path.realpath(DATA_DIR)
    real = os.path.realpath(storage_dir)
    try:
        inside = os.path.normcase(os.path.commonpath([base, real])) == os.path.normcase(base)
    except ValueError:      # different drives
        inside = False
    if not inside:
        raise ValueError(f"[Security] Path traversal detected in get_storage_dir: {ext_id!r}")
    os.makedirs(storage_dir, exist_ok=True)
    return storage_dir

def run_thread(background_func, callback=None):
    """
    Run a function (background_func) on a separate thread so the UI never freezes.
    Ideal for HTTP requests (NASA/Weather) or database queries.
    If the function returns a value, the result is delivered to the callback.
    """
    import wx
    import threading

    def thread_target():
        try:
            result = background_func()
            if callback:
                wx.CallAfter(callback, result)
        except Exception as e:
            logger.error(f"Error in run_thread ({background_func.__name__}): {e}")
            if callback:
                # Pass None (or an Exception object, if preferred).
                wx.CallAfter(callback, None)
                
    t = threading.Thread(target=thread_target)
    t.daemon = True
    t.start()

# --- Advanced System API ---

def open_log_viewer():
    """Open the log file in the system's default text editor."""
    import tempfile
    import os
    log_file = os.path.join(tempfile.gettempdir(), "Hariku2", "hariku_debug.log")
    if os.path.exists(log_file):
        os.startfile(log_file)
    else:
        logger.warning("Log file not found.")

def open_data_folder():
    """Open the data storage folder in Windows Explorer."""
    import os
    if os.path.exists(USER_DATA_DIR):
        os.startfile(USER_DATA_DIR)

def clear_cache():
    """Delete the extensions' .cache folder."""
    import os
    import shutil
    import core.extension_manager
    cache_dir = os.path.join(core.extension_manager.USER_EXTENSIONS_DIR, ".cache")
    if os.path.exists(cache_dir):
        try:
            shutil.rmtree(cache_dir)
            return True
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
    return True

# Windows starts Hariku with this argument (the Run value set_autostart()
# writes), so Hariku knows the computer has just started (core 2.7).
AUTOSTART_FLAG = "--autostart"
_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE_NAME = "HarikuV2"


def _running_compiled():
    # Nuitka defines __compiled__ in every module it compiles (see core.updater);
    # other freezers set sys.frozen.
    return "__compiled__" in globals() or bool(getattr(sys, "frozen", False))


def autostart_command(compiled=None, executable=None, script=None):
    """The command line the Run value holds: the program (and, from source,
    the script) in quotes, then AUTOSTART_FLAG."""
    compiled = _running_compiled() if compiled is None else compiled
    executable = executable or sys.executable
    if compiled:
        return f'"{executable}" {AUTOSTART_FLAG}'
    script = os.path.abspath(script or sys.argv[0])
    return f'"{executable}" "{script}" {AUTOSTART_FLAG}'


def started_with_windows(argv=None):
    """True when Windows started Hariku (the Run value's AUTOSTART_FLAG is in
    the command line), False when the user or a restart did."""
    return AUTOSTART_FLAG in (sys.argv[1:] if argv is None else argv)


def set_autostart(enable=True):
    """Set whether Hariku runs automatically at Windows startup."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            winreg.SetValueEx(key, _RUN_VALUE_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, _RUN_VALUE_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to set autostart: {e}")


def _read_autostart_value():
    """The Run value's command line, or None when there is none."""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ)
    except OSError:
        return None
    try:
        value, _kind = winreg.QueryValueEx(key, _RUN_VALUE_NAME)
        return value if isinstance(value, str) else None
    except OSError:
        return None
    finally:
        winreg.CloseKey(key)


def autostart_needs_update(config, run_value):
    """Whether the Run value (an older Hariku's, without AUTOSTART_FLAG) should
    be written again. Only while the user has autostart on and the value is
    there: a value they removed stays removed."""
    return (isinstance(config, dict) and config.get("auto_start") is True
            and isinstance(run_value, str) and AUTOSTART_FLAG not in run_value.split())


def migrate_autostart(config=None, read_value=None, write=None):
    """At startup: add AUTOSTART_FLAG to a Run value written before core 2.7.
    Returns True when it rewrote the value."""
    config = load_data("Core") if config is None else config
    if not (isinstance(config, dict) and config.get("auto_start") is True):
        return False   # nothing to look at, and no registry read
    try:
        run_value = (read_value or _read_autostart_value)()
    except Exception as e:
        logger.info(f"Could not read the autostart entry: {e}")
        return False
    if not autostart_needs_update(config, run_value):
        return False
    (write or set_autostart)(True)
    logger.info("Autostart entry updated so Hariku knows when Windows started it.")
    return True

def open_preferences(tab_name=None):
    """Open the Preferences window. If tab_name is given, it tries to select that tab directly."""
    from core.events import bus
    import wx
    wx.CallAfter(lambda: bus.emit("on_open_preferences", tab_name))


# ── WebView API ─────────────────────────────────────────────────────

def show_html_view(html_content: str, title: str = "Hariku Viewer",
                   width: int = 850, height: int = 650) -> bool:
    """
    Show HTML content in a separate window that supports NVDA Browse Mode.

    The window runs in an isolated subprocess so it cannot crash Hariku's
    main process.

    Args:
        html_content: Complete HTML string.
        title: Window title.
        width: Window width (pixels).
        height: Window height (pixels).

    Returns:
        True if launched successfully.
    """
    from core.webview import show_html
    return show_html(html_content, title, width, height)


def show_html_file_view(html_path: str, title: str = "Hariku Viewer",
                        width: int = 850, height: int = 650) -> bool:
    """
    Show an HTML file in a separate window that supports NVDA Browse Mode.

    Args:
        html_path: Absolute path to the HTML file.
        title: Window title.
        width: Window width.
        height: Window height.

    Returns:
        True if launched successfully.
    """
    # [SEC MED-2] Only allow files from trusted directories to prevent
    # extensions from using this to display arbitrary system files.
    import tempfile
    from core.extension_manager import USER_EXTENSIONS_DIR, SYSTEM_EXTENSIONS_DIR
    _ALLOWED_HTML_DIRS = [
        os.path.realpath(os.path.join(tempfile.gettempdir(), "hariku2")),
        os.path.realpath(DATA_DIR),
        os.path.realpath(SYSTEM_EXTENSIONS_DIR),
        os.path.realpath(USER_EXTENSIONS_DIR),
    ]
    real_path = os.path.realpath(html_path)
    allowed = any(real_path.startswith(d + os.sep) or real_path == d
                  for d in _ALLOWED_HTML_DIRS)
    if not allowed:
        logger.error(f"[Security] show_html_file_view blocked: path not in allowed dirs: {html_path}")
        return False
    from core.webview import show_html_file
    return show_html_file(html_path, title, width, height)

