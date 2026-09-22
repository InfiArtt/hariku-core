# hariku2/main.py
import sys
import os

# Cek tombol Shift secara instan sebelum library lain dimuat
import ctypes
import winsound
VK_SHIFT = 0x10
SHIFT_PRESSED_AT_STARTUP = (ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0
if SHIFT_PRESSED_AT_STARTUP:
    # Menggunakan suara WAV internal agar tidak terlalu keras dan mengikuti volume Windows
    sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds", "history.wav")
    winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)


# Tambahkan root directory hariku2 ke path agar imports internal bekerja dari mana saja
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.crash_handler
core.crash_handler.setup()

import wx

# Terapkan Ghost Widget (Aksesibilitas StaticText)
import core.ui_overrides
core.ui_overrides.apply_overrides()

import logging
from core.speech import init_speech, unload_speech, speak
from core.extension_manager import load_all_extensions
from core.events import bus
import core.hotkeys
import core.preferences
import core.reminders
import core.api
from ui.main_window import MainWindow

# Mencegah Nuitka membuang library standar
import core.stdlib_includes

import os
import sys

import tempfile

# Siapkan direktori log di folder Temp agar tidak menjadi sampah permanen (seperti NVDA)
log_dir = os.path.join(tempfile.gettempdir(), "Hariku2")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "hariku_debug.log")

# Setup logging awal dengan INFO agar import api.py tidak error
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode='w', encoding='utf-8'), # Gunakan mode 'w' agar menimpa log lama
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Sesuaikan level log berdasarkan pengaturan Core
try:
    import core.api
    config = core.api.load_data("Core")
    log_level_str = config.get("log_level", "INFO").upper()
    
    root_logger = logging.getLogger()
    if log_level_str == "DISABLED":
        root_logger.handlers = []
        root_logger.addHandler(logging.NullHandler())
        root_logger.setLevel(logging.CRITICAL)
    else:
        level = getattr(logging, log_level_str, logging.INFO)
        root_logger.setLevel(level)
except Exception as e:
    logger.error(f"Failed to set log level: {e}")

class HarikuApp(wx.App):
    def OnInit(self):
        import core.constants
        logger.info(f"Starting Hariku V{core.constants.CORE_VERSION} Core...")
        
        # Load and set internal config
        import core.api
        config = core.api.load_data("Core")
        
        # Initialize internal audio/volume setup
        import core.sounds
        # Memastikan volume system diset sesuai config
        core.sounds.apply_system_volume(config.get("volume", 100))
        
        # Inisialisasi sistem terjemahan (i18n)
        import core.i18n
        core.i18n.init()
        _ = core.i18n.get_translator("core")
        
        import core.core_panels
        core.core_panels.register()
        
        # Inisialisasi sistem Hotkey / Input Gestures
        core.hotkeys.init_hotkeys()
        
        # Memuat aksesibilitas (Tolk melalui cytolk)
        # Mengecek apakah berjalan di Safe Mode (lewat argumen atau tahan tombol Shift di awal)
        self.is_safe_mode = "--safe-mode" in sys.argv or SHIFT_PRESSED_AT_STARTUP
        
        if self.is_safe_mode:
            logger.warning(_("safe_mode_log"))
            if config.get("play_startup_sound", True):
                core.sounds.play_internal_sound("start.wav")
            if init_speech():
                speak(_("safe_mode_message"))
        else:
            if config.get("play_startup_sound", True):
                core.sounds.play_internal_sound("start.wav")
                
            if init_speech():
                speak(_("welcome_message", version=core.constants.CORE_VERSION))
            
        # Cek Onboarding
        completed = config.get("onboarding_completed", False)
        if not completed:
            from ui.onboarding_dialog import run_onboarding
            success = run_onboarding()
            if not success:
                logger.info("Onboarding cancelled, exiting.")
                return False
        
        # Init Core Reminders
        core.reminders.init(bus)
        
        if not self.is_safe_mode:
            # Memuat semua ekstensi HANYA jika bukan di safe mode
            load_all_extensions()
            # Cek update ekstensi di background (delay 6 detik agar startup tidak terbebani)
            import core.update_checker
            core.update_checker.start(delay_seconds=6)
            
            # Cek update Core aplikasi di background (delay 3 detik)
            import core.updater
            import threading
            def _delayed_core_update_check():
                import time
                time.sleep(3)
                core.updater.check_for_updates(interactive=False)
            threading.Thread(target=_delayed_core_update_check, daemon=True, name="core-update-checker").start()
        
        # Memberitahu ekstensi bahwa sistem utama sudah berjalan
        bus.emit("on_app_startup")
        
        # Menampilkan UI Utama
        self.frame = MainWindow(None, title=_("app_title_safe_mode") if self.is_safe_mode else _("app_title"))
        self.SetTopWindow(self.frame)
        self.frame.Show(True)
        
        # Kirim ping telemetri
        import core.telemetry
        core.telemetry.record_startup()
        
        return True

    def OnExit(self):
        logger.info("Shutting down Hariku V2 Core...")
        unload_speech()
        return super().OnExit()



def main():
    app = HarikuApp()
    app.MainLoop()

if __name__ == "__main__":
    main()
