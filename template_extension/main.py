# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# ============================================================
# Hariku V2 Extension Template — "Hello World"
# ============================================================
# This is a minimal, fully-commented extension that demonstrates
# every major feature of the Hariku V2 Extension API.
#
# To use this template:
#   1. Copy the entire "template_extension" folder into your
#      Hariku extensions directory (or keep it here for dev).
#   2. Rename the folder to your extension's ID (e.g. "my_tool").
#   3. Edit manifest.json with your extension's info.
#   4. Modify this file to implement your logic.
#   5. Run packager.py to package it into a .hrk file.
# ============================================================

import logging
import wx

# --- Core Imports (always available) ---
import core.api          # Data storage, UI dialogs, clipboard, timers
import core.hotkeys      # Register keyboard shortcuts
import core.preferences  # Add a settings panel
from core.events import bus   # Subscribe to lifecycle events
from core.speech import speak # Text-to-Speech (NVDA / screen reader)
from core.sounds import play_internal_sound  # Play .wav sounds

logger = logging.getLogger(__name__)


# ============================================================
# 1. CORE LOGIC
# ============================================================

def say_hello():
    """
    The main action of this extension.
    Called when the user presses the assigned hotkey.
    """
    # Read saved data (returns {} if no data exists yet)
    config = core.api.load_data("HelloWorld")
    count = config.get("hello_count", 0) + 1
    
    # Speak through NVDA / screen reader
    speak(f"Hello World! You have greeted me {count} times.", interrupt=True)
    
    # Save updated data persistently
    config["hello_count"] = count
    core.api.save_data("HelloWorld", config)


def show_hello_dialog():
    """
    Example: Open a custom wxPython dialog.
    """
    config = core.api.load_data("HelloWorld")
    count = config.get("hello_count", 0)
    
    # Simple built-in dialog (no need to create wx.Dialog manually)
    core.api.show_message(
        "Hello World Extension",
        f"This extension has been triggered {count} times.\n\n"
        "You can build powerful features using the Hariku API!"
    )


def fetch_example():
    """
    Example: Run a network request in the background
    so the UI does not freeze.
    """
    def _background_work():
        import urllib.request
        import json
        req = urllib.request.Request(
            "https://api.github.com/zen",
            headers={"User-Agent": "Hariku-Extension"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")
    
    def _on_result(result):
        if result:
            speak(f"GitHub Zen says: {result}")
        else:
            speak("Failed to fetch data.")
    
    # run_thread handles threading + CallAfter for you
    core.api.run_thread(_background_work, _on_result)


# ============================================================
# 2. SETTINGS PANEL (Optional)
# ============================================================
# If your extension needs user-configurable settings, create
# a wx.Panel subclass and register it via core.preferences.

class HelloSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        config = core.api.load_data("HelloWorld")
        
        # Checkbox example
        self.chk_greet_on_startup = wx.CheckBox(
            self, label="Greet me when Hariku starts"
        )
        self.chk_greet_on_startup.SetValue(
            config.get("greet_on_startup", False)
        )
        vbox.Add(self.chk_greet_on_startup, 0, wx.ALL, 10)
        
        # Text input example
        vbox.Add(
            wx.StaticText(self, label="Your name:"),
            0, wx.LEFT | wx.TOP, 10
        )
        self.txt_name = wx.TextCtrl(
            self, value=config.get("user_name", "Developer")
        )
        vbox.Add(self.txt_name, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        self.SetSizer(vbox)
    
    def ApplyChanges(self):
        """Called automatically when the user clicks OK in Preferences."""
        config = core.api.load_data("HelloWorld")
        config["greet_on_startup"] = self.chk_greet_on_startup.GetValue()
        config["user_name"] = self.txt_name.GetValue()
        core.api.save_data("HelloWorld", config)


# Panel factory functions (required by core.preferences)
_panel_instance = None

def _create_panel(parent):
    global _panel_instance
    _panel_instance = HelloSettingsPanel(parent)
    return _panel_instance

def _apply_panel():
    if _panel_instance:
        _panel_instance.ApplyChanges()


# ============================================================
# 3. EVENT HANDLERS (Optional)
# ============================================================

def on_app_startup():
    """Called once after all extensions are loaded and the UI is ready."""
    config = core.api.load_data("HelloWorld")
    if config.get("greet_on_startup", False):
        name = config.get("user_name", "Developer")
        # Delay 2 seconds so it doesn't clash with the startup quote
        wx.CallLater(2000, speak, f"Good day, {name}!")


def on_date_changed(date_str):
    """
    Called when the user selects a different date on the calendar.
    date_str format: 'YYYY-MM-DD'
    """
    # Uncomment to hear the date every time you navigate:
    # speak(f"Selected date: {date_str}")
    pass


# ============================================================
# 4. REGISTER FUNCTION (Required)
# ============================================================
# This is the ONLY required function. Hariku calls register(bus)
# when your extension is loaded. Use it to:
#   - Subscribe to events
#   - Register hotkeys
#   - Register settings panels

def register(bus):
    """
    Entry point called by Hariku when this extension is loaded.
    
    Args:
        bus: The global EventBus instance for subscribing to events.
    """
    logger.info("Hello World extension loaded!")
    
    # --- Subscribe to lifecycle events ---
    bus.subscribe("on_app_startup", on_app_startup)
    bus.subscribe("on_date_changed", on_date_changed)
    
    # --- Register keyboard shortcuts ---
    # Parameters: extension_name, action_name, description, 
    #             default_keycode, default_ctrl, callback,
    #             default_shift=False, default_alt=False
    #
    # Set default_keycode to None if you don't want a default shortcut.
    # Users can always assign their own via Settings > Input Gestures.
    core.hotkeys.register_action(
        "Hello World",          # Extension name (shown in Input Gestures)
        "say_hello",            # Unique action ID
        "Say Hello",            # Human-readable description
        ord("H"),               # Default key: H
        False,                  # Ctrl required? False
        say_hello,              # Callback function
        default_shift=False,
        default_alt=False
    )
    
    core.hotkeys.register_action(
        "Hello World",
        "show_dialog",
        "Show Hello Dialog",
        None,                   # No default shortcut
        False,
        show_hello_dialog
    )
    
    core.hotkeys.register_action(
        "Hello World",
        "fetch_zen",
        "Fetch GitHub Zen Quote",
        None,
        False,
        fetch_example
    )
    
    # --- Register a settings panel ---
    # Parameters: category, panel_name, create_func, apply_func
    core.preferences.register_panel(
        "Hello World",       # Category in the Preferences tree
        "",                  # Panel name (leave empty if only 1 panel)
        _create_panel,
        _apply_panel
    )
