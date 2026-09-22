# hariku2/core/api.py
import wx
import os
import json
import logging
import sys

logger = logging.getLogger(__name__)

# Menyimpan referensi ke jendela utama agar bisa diakses oleh fungsi API.
# Nilai ini akan diisi secara otomatis oleh main_window.py saat aplikasi dimulai.
main_window_instance = None

def get_selected_date():
    """
    Mengembalikan tanggal yang sedang disorot di kalender.
    Format string: 'YYYY-MM-DD'
    """
    if main_window_instance and hasattr(main_window_instance, 'calendar'):
        wx_date = main_window_instance.calendar.GetDate()
        return wx_date.Format("%Y-%m-%d")
    return None

def set_selected_date(date_str):
    """
    Memaksa kalender untuk berpindah ke tanggal tertentu.
    Format yang diharapkan: 'YYYY-MM-DD'
    """
    if main_window_instance and hasattr(main_window_instance, 'calendar'):
        try:
            new_date = wx.DateTime()
            # Parse format string ke objek DateTime wx
            success = new_date.ParseFormat(date_str, "%Y-%m-%d")
            
            if success:
                main_window_instance.calendar.SetDate(new_date)
                return True
        except Exception as e:
            pass
    return False

# --- Storage API ---

# Direktori penyimpanan global
_app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
USER_DATA_DIR = os.path.join(_app_data, "Hariku2")
DATA_DIR = os.path.join(USER_DATA_DIR, "data")

def get_data_path(extension_name):
    """Mendapatkan path file JSON untuk ekstensi tertentu."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    
    # Sanitasi nama ekstensi untuk keamanan nama file
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
    """Memuat data JSON milik ekstensi sebagai dictionary.
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
    """Menyimpan dictionary ke dalam file JSON milik ekstensi (atomic)."""
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
    Menjalankan fungsi setelah X milidetik.
    Mengembalikan objek timer, panggil .Stop() jika ingin dibatalkan.
    """
    # wx.CallLater sangat aman untuk GUI thread
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
    Menjalankan fungsi secara berulang setiap X milidetik.
    Mengembalikan objek timer, panggil .Stop() jika ingin dihentikan.
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
    """Menampilkan kotak dialog pesan (OK saja)."""
    parent = _get_parent_window()
    if parent:
        dlg = wx.MessageDialog(parent, message, title, wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

def prompt_yes_no(title, message):
    """Menanyakan Yes/No, mengembalikan True/False."""
    parent = _get_parent_window()
    if parent:
        dlg = wx.MessageDialog(parent, message, title, wx.YES_NO | wx.ICON_QUESTION)
        result = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        return result
    return False

def prompt_text(title, message, default_value=""):
    """Meminta input teks singkat."""
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
    """Meminta input teks panjang (multiline)."""
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
    Menampilkan notifikasi sistem bawaan (misal Windows Toast di pojok kanan bawah).
    flags: wx.ICON_INFORMATION, wx.ICON_WARNING, atau wx.ICON_ERROR
    """
    import wx.adv
    parent = _get_parent_window()
    if parent:
        toast = wx.adv.NotificationMessage(title, message, parent=parent, flags=flags)
        toast.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)

# --- OS Context API ---

def get_active_window_info():
    """
    Mengambil informasi jendela yang sedang aktif (fokus) di Windows.
    Mengembalikan dict: {"title": "Judul Jendela", "process": "nama_proses.exe"}
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
    """Mengembalikan waktu (dalam detik) sejak user terakhir kali menyentuh keyboard/mouse."""
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
    Mengembalikan dict status daya:
    {"ac_line_status": 1 (plugged in) atau 0 (battery), "battery_percent": 0-100, "charging": bool}
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
    """Mengembalikan True jika komputer terhubung ke internet."""
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
    """Menyalin teks ke clipboard OS menggunakan pyperclip."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception as e:
        logger.error(f"Clipboard set error: {e}")
        return False

def get_clipboard():
    """Mengambil teks dari clipboard OS menggunakan pyperclip."""
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception as e:
        logger.error(f"Failed to get clipboard: {e}")
        return ""

def restart_app(safe_mode=False):
    """
    Me-restart aplikasi Hariku secara penuh.
    Menyimpan semua state (melalui on_unload) lalu menjalankan ulang proses.
    Jika safe_mode=True, tambahkan flag --safe-mode ke argumen.
    """
    import sys
    import os
    import subprocess
    import wx
    from core.events import bus
    
    logger.info(f"Restarting application... (safe_mode={safe_mode})")
    
    # 1. Beritahu semua modul untuk menyimpan state mereka
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
    
    # 3. Matikan proses saat ini
    app = wx.GetApp()
    if app:
        app.ExitMainLoop()
    
    os._exit(0)  # Gunakan os._exit(0) untuk memastikan proses langsung mati tanpa delay

def get_storage_dir(ext_id):
    """
    Mengembalikan path absolut ke folder penyimpanan khusus untuk ekstensi tertentu.
    Aman untuk menyimpan database SQLite, gambar, atau file besar.
    """
    # [SEC HIGH-1] Sanitize ext_id to prevent path traversal (e.g. "../../Windows")
    safe_id = "".join(c for c in ext_id if c.isalnum() or c in ("-", "_")).strip()
    if not safe_id:
        raise ValueError(f"[Security] Invalid extension ID for storage: {ext_id!r}")
    storage_dir = os.path.join(DATA_DIR, "extensions", safe_id)
    # Paranoia check: verify realpath stays inside DATA_DIR
    if not os.path.realpath(storage_dir).startswith(os.path.realpath(DATA_DIR)):
        raise ValueError(f"[Security] Path traversal detected in get_storage_dir: {ext_id!r}")
    if not os.path.exists(storage_dir):
        os.makedirs(storage_dir)
    return storage_dir

def run_thread(background_func, callback=None):
    """
    Menjalankan fungsi (background_func) di thread terpisah agar UI tidak macet (freeze).
    Sangat cocok untuk HTTP Request (NASA/Weather) atau query database.
    Jika fungsi mengembalikan nilai, hasilnya akan dikirim ke callback.
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
                # Kirim None atau Exception object (bisa disesuaikan)
                wx.CallAfter(callback, None)
                
    t = threading.Thread(target=thread_target)
    t.daemon = True
    t.start()

# --- Advanced System API ---

def open_log_viewer():
    """Membuka file log di text editor default sistem."""
    import tempfile
    import os
    log_file = os.path.join(tempfile.gettempdir(), "Hariku2", "hariku_debug.log")
    if os.path.exists(log_file):
        os.startfile(log_file)
    else:
        logger.warning("Log file not found.")

def open_data_folder():
    """Membuka folder penyimpan data di Windows Explorer."""
    import os
    if os.path.exists(USER_DATA_DIR):
        os.startfile(USER_DATA_DIR)

def clear_cache():
    """Menghapus folder .cache di ekstensi."""
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

def set_autostart(enable=True):
    """Mengatur apakah Hariku berjalan otomatis saat Windows startup."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "HarikuV2"
        
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to set autostart: {e}")

def open_preferences(tab_name=None):
    """Membuka jendela Preferences. Jika tab_name diberikan, ia akan mencoba langsung memilih tab tersebut."""
    from core.events import bus
    import wx
    wx.CallAfter(lambda: bus.emit("on_open_preferences", tab_name))


# ── WebView API ─────────────────────────────────────────────────────

def show_html_view(html_content: str, title: str = "Hariku Viewer",
                   width: int = 850, height: int = 650) -> bool:
    """
    Tampilkan HTML content di jendela terpisah yang mendukung NVDA Browse Mode.

    Jendela berjalan di subprocess terisolasi sehingga tidak bisa crash
    proses utama Hariku.

    Args:
        html_content: String HTML lengkap.
        title: Judul jendela.
        width: Lebar jendela (pixels).
        height: Tinggi jendela (pixels).

    Returns:
        True jika berhasil diluncurkan.
    """
    from core.webview import show_html
    return show_html(html_content, title, width, height)


def show_html_file_view(html_path: str, title: str = "Hariku Viewer",
                        width: int = 850, height: int = 650) -> bool:
    """
    Tampilkan file HTML di jendela terpisah yang mendukung NVDA Browse Mode.

    Args:
        html_path: Path absolut ke file HTML.
        title: Judul jendela.
        width: Lebar jendela.
        height: Tinggi jendela.

    Returns:
        True jika berhasil diluncurkan.
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

