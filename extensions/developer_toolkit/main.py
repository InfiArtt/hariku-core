# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import wx
import core.hotkeys
from core.events import bus
from core.speech import speak

logger = logging.getLogger("ext.developer_toolkit")

# --- Event Sniffer Storage ---
_sniffer_active = False
_sniffed_events = []
_original_emit = None

def _start_sniffer():
    """Monkey-patch EventBus.emit to capture all events."""
    global _sniffer_active, _original_emit
    if _sniffer_active:
        return
    
    _original_emit = bus.emit
    
    def patched_emit(event_name, *args, **kwargs):
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        arg_preview = ", ".join([repr(a)[:80] for a in args])
        _sniffed_events.append(f"[{timestamp}] {event_name}({arg_preview})")
        # Keep only last 500 events
        if len(_sniffed_events) > 500:
            _sniffed_events.pop(0)
        _original_emit(event_name, *args, **kwargs)
    
    bus.emit = patched_emit
    _sniffer_active = True
    logger.info("Event Sniffer started.")

def _stop_sniffer():
    """Restore original EventBus.emit."""
    global _sniffer_active, _original_emit
    if _original_emit:
        bus.emit = _original_emit
        _original_emit = None
    _sniffer_active = False
    logger.info("Event Sniffer stopped.")

# --- Toolkit Dialog ---
def _show_toolkit():
    """Show the Developer Toolkit dialog."""
    import core.api
    parent = core.api.main_window_instance
    from developer_toolkit_ui import DeveloperToolkitDialog
    dlg = DeveloperToolkitDialog(parent)
    dlg.ShowModal()
    dlg.Destroy()

def register(event_bus):
    logger.info("Developer Toolkit extension initialized.")
    
    # Start sniffer immediately so it captures events from app startup
    _start_sniffer()
    
    # Register global hotkey: Ctrl + Alt + D
    core.hotkeys.register_action(
        extension_name="Developer Toolkit",
        action_name="open_toolkit",
        description="Open Developer Toolkit",
        default_keycode=ord('D'),
        default_ctrl=True,
        callback=_show_toolkit,
        default_alt=True,
        default_global=True
    )
    
    # Add to System Tray context menu
    event_bus.subscribe("on_build_tray_menu", _on_tray_menu)

def _on_tray_menu(menu, frame):
    item = menu.Append(wx.ID_ANY, "Developer Toolkit")
    frame.Bind(wx.EVT_MENU, lambda e: _show_toolkit(), item)

def teardown():
    _stop_sniffer()
    logger.info("Developer Toolkit extension unloaded.")
