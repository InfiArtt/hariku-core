# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import os

# Check the Shift key instantly, before any other library loads.
import ctypes
import winsound
VK_SHIFT = 0x10
SHIFT_PRESSED_AT_STARTUP = (ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0
if SHIFT_PRESSED_AT_STARTUP:
    # Use an internal WAV so it isn't too loud and follows the Windows volume.
    sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds", "history.wav")
    winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)


# Add the hariku2 root directory to the path so internal imports work from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.crash_handler
core.crash_handler.setup()

import wx

# Apply the Ghost Widget (StaticText accessibility) override.
import core.ui_overrides
core.ui_overrides.apply_overrides()

import logging
from core.speech import init_speech, unload_speech, speak
from core.extension_manager import load_all_extensions
from core.events import bus
import core.hotkeys
import core.personal
import core.preferences
import core.reminders
import core.api
from ui.main_window import MainWindow

# Prevent Nuitka from stripping the standard library.
import core.stdlib_includes

import os
import sys

import tempfile

# Put the log directory in Temp so it doesn't become permanent clutter (like NVDA).
log_dir = os.path.join(tempfile.gettempdir(), "Hariku2")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "hariku_debug.log")

# Set up logging early at INFO so importing api.py doesn't error.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode='w', encoding='utf-8'), # mode 'w' overwrites the old log
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Adjust the log level based on the Core settings.
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

        # Single-instance guard: a second copy would fight over global hotkeys
        # and the tray icon, so refuse to start it.
        self._instance_checker = wx.SingleInstanceChecker(f"Hariku2-{wx.GetUserId()}")
        if self._instance_checker.IsAnotherRunning():
            logger.warning("Another instance of Hariku is already running. Exiting.")
            wx.MessageBox("Hariku is already running.", "Hariku",
                          wx.OK | wx.ICON_INFORMATION)
            return False
        
        # Load and set internal config
        import core.api
        config = core.api.load_data("Core")
        # A Run value from before 2.7 lacks --autostart; add it so a start with
        # Windows can be told apart (core.api.started_with_windows).
        core.api.migrate_autostart(config)
        
        # Initialize internal audio/volume setup
        import core.sounds
        # Make sure the system volume matches the config.
        core.sounds.apply_system_volume(config.get("volume", 100))

        # Initialize the translation system (i18n).
        import core.i18n
        core.i18n.init()
        _ = core.i18n.get_translator("core")

        import core.core_panels
        core.core_panels.register()

        # Core 2.8: the first time, make "Home" from the place the user already
        # had (Flight Radar's exact home, else the Weather city), before the
        # extensions that use it load.
        import core.places
        try:
            core.places.migrate()
        except Exception as e:
            logger.error(f"Places migration failed: {e}")

        # Initialize the hotkey / input-gesture system.
        core.hotkeys.init_hotkeys()

        # Load accessibility (Tolk via cytolk).
        # Check whether we're running in Safe Mode (via argument or by holding Shift at startup).
        self.is_safe_mode = "--safe-mode" in sys.argv or SHIFT_PRESSED_AT_STARTUP
        if not self.is_safe_mode:
            # The sound theme the user picked, so its start sound plays: the
            # Sound Themes extension itself only loads later.
            core.sounds.load_remembered_theme()
        
        speech_ready = False
        if self.is_safe_mode:
            logger.warning(_("safe_mode_log"))
            if config.get("play_startup_sound", True):
                core.sounds.play_internal_sound("start.wav")
            if init_speech():
                speak(_("safe_mode_message"))
        else:
            if config.get("play_startup_sound", True):
                core.sounds.play_internal_sound("start.wav")
            speech_ready = init_speech()

        # The first time, the welcome (core 2.10) asks the user's name, city and
        # so on, before the main window. However it ends, Hariku goes on
        # starting (Cancel marks it done: core.onboarding.cancel), in the
        # language chosen there; Help, Welcome Dialog shows it again.
        if not config.get("onboarding_completed", False):
            from ui.onboarding_dialog import run_onboarding
            if not run_onboarding(first_run=True):
                logger.info("Welcome cancelled; starting anyway.")

        if speech_ready:
            # Made after the welcome, so it is in the language chosen there.
            welcome = _("welcome_message", version=core.constants.CORE_VERSION)
            if core.personal.startup_greeting_enabled():
                # Said once the main window is ready, together with the greeting.
                self._startup_welcome = welcome
            else:
                speak(welcome)

        # Init Core Reminders
        core.reminders.init(bus)
        
        if not self.is_safe_mode:
            # Load all extensions ONLY when not in safe mode.
            load_all_extensions()
            # A remembered theme only plays while Sound Themes, which manages
            # it, is there (turned off or removed: the built-in sounds).
            import core.extension_manager
            if (core.sounds.get_theme_dir()
                    and "sound_themes" not in core.extension_manager.LOADED_EXTENSIONS):
                core.sounds.set_theme_dir(None)
            # Check for extension updates in the background (6s delay so startup isn't burdened).
            import core.update_checker
            core.update_checker.start(delay_seconds=6)

            # Check for Core app updates in the background (3s delay).
            import core.updater
            import threading
            def _delayed_core_update_check():
                import time
                time.sleep(3)
                core.updater.check_for_updates(interactive=False)
            threading.Thread(target=_delayed_core_update_check, daemon=True, name="core-update-checker").start()
        
        # Tell extensions that the main system is now running.
        bus.emit("on_app_startup")

        # Show the main UI.
        self.frame = MainWindow(None, title=_("app_title_safe_mode") if self.is_safe_mode else _("app_title"))
        self.SetTopWindow(self.frame)
        self.frame.Show(True)

        # "Good morning, Bro. Welcome to Hariku ..." (or the user's own
        # greeting): one announcement, after the screen reader has read the
        # window. Timers, so startup doesn't wait; when Windows started Hariku
        # it also waits for the network, so %weather% and the like are fresh.
        welcome = getattr(self, "_startup_welcome", None)
        if welcome is not None:
            core.personal.schedule_startup_greeting(
                welcome, boot=core.api.started_with_windows())

        # Send the telemetry ping.
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
