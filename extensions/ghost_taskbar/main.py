# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import ctypes
from ctypes import wintypes
import logging
import wx
import os
import core.hotkeys
from core.speech import speak
from core.i18n import get_translator

logger = logging.getLogger("ext.ghost_taskbar")

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("ext.ghost_taskbar", os.path.join(EXT_DIR, "locales"))

def clear_tray():
    try:
        user32 = ctypes.windll.user32
        WM_MOUSEMOVE = 0x0200
        
        cleared_something = False
        
        # 1. Clear Main Tray
        tray_wnd = user32.FindWindowA(b"Shell_TrayWnd", None)
        if tray_wnd:
            tray_notify_wnd = user32.FindWindowExA(tray_wnd, 0, b"TrayNotifyWnd", None)
            if tray_notify_wnd:
                sys_pager = user32.FindWindowExA(tray_notify_wnd, 0, b"SysPager", None)
                if sys_pager:
                    toolbar = user32.FindWindowExA(sys_pager, 0, b"ToolbarWindow32", None)
                    if toolbar:
                        rect = wintypes.RECT()
                        user32.GetClientRect(toolbar, ctypes.byref(rect))
                        for x in range(0, rect.right, 5):
                            for y in range(0, rect.bottom, 5):
                                lparam = (y << 16) | x
                                user32.SendMessageA(toolbar, WM_MOUSEMOVE, 0, lparam)
                        cleared_something = True

        # 2. Clear Overflow Tray (Hidden Icons)
        overflow = user32.FindWindowA(b"NotifyIconOverflowWindow", None)
        if overflow:
            overflow_toolbar = user32.FindWindowExA(overflow, 0, b"ToolbarWindow32", None)
            if overflow_toolbar:
                rect = wintypes.RECT()
                user32.GetClientRect(overflow_toolbar, ctypes.byref(rect))
                for x in range(0, rect.right, 5):
                    for y in range(0, rect.bottom, 5):
                        lparam = (y << 16) | x
                        user32.SendMessageA(overflow_toolbar, WM_MOUSEMOVE, 0, lparam)
                cleared_something = True
                
        if cleared_something:
            speak(_("msg_tray_cleared"))
        else:
            speak(_("msg_tray_not_found"))
            
    except Exception as e:
        logger.error(f"Failed to clear tray: {e}")
        speak(_("msg_clear_failed"))

def register(bus):
    logger.info("Ghost Taskbar Cleaner extension initialized.")
    # Register hotkey: Ctrl + Alt + C
    core.hotkeys.register_action(
        extension_name="Ghost Taskbar",
        action_name="clear_tray",
        description=_("desc_action_clear"),
        default_keycode=ord('C'),
        default_ctrl=True,
        default_alt=True,
        default_global=True,
        callback=clear_tray
    )

def teardown():
    logger.info("Ghost Taskbar Cleaner extension unloaded.")
