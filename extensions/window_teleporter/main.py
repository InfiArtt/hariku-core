import logging
import wx
import ctypes
import os
import core.i18n
from core.speech import speak
from core.hotkeys import register_action

logger = logging.getLogger(__name__)

# Translator
locales_dir = os.path.join(os.path.dirname(__file__), "locales")
from core.i18n import get_translator
translator = get_translator("window_teleporter", locales_dir=locales_dir)
_ = translator

# Windows API
user32 = ctypes.windll.user32

# State
pinned_windows = {} # slot (int) -> {"hwnd": int, "title": str}

# Optional dependency
try:
    import sys
    # Hariku uses wxPython. If 2 (STA) caused a conflict, wx is likely using 0 (MTA).
    sys.coinit_flags = 0 
    
    from pyvda import VirtualDesktop
    has_pyvda = True
except ImportError:
    has_pyvda = False
    logger.warning("pyvda not installed, virtual desktop jumping is disabled.")

def get_window_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return "Unknown Window"
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def pin_window(slot):
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        speak(_("slot_empty", slot=slot))
        return
        
    title = get_window_title(hwnd)
    pinned_windows[slot] = {"hwnd": hwnd, "title": title}
    speak(_("pinned_success", title=title[:50], slot=slot), interrupt=True)

def teleport_window(slot):
    if slot not in pinned_windows:
        speak(_("slot_empty", slot=slot), interrupt=True)
        return
        
    hwnd = pinned_windows[slot]["hwnd"]
    title = pinned_windows[slot]["title"]
    
    if not user32.IsWindow(hwnd):
        speak(_("slot_empty", slot=slot), interrupt=True)
        del pinned_windows[slot]
        return
        
    # SW_RESTORE = 9
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    speak(_("teleport_success", title=title[:50]), interrupt=True)

def check_window(slot):
    if slot not in pinned_windows:
        speak(_("slot_empty", slot=slot), interrupt=True)
        return
        
    hwnd = pinned_windows[slot]["hwnd"]
    title = pinned_windows[slot]["title"]
    
    if not user32.IsWindow(hwnd):
        speak(_("slot_empty", slot=slot), interrupt=True)
        del pinned_windows[slot]
        return
        
    speak(_("check_success", slot=slot, title=title[:80]), interrupt=True)

def jump_desktop(desktop_num):
    if not has_pyvda:
        speak(_("pyvda_missing"), interrupt=True)
        return
        
    try:
        vd = VirtualDesktop(desktop_num)
        vd.go()
        speak(_("desktop_success", desktop=desktop_num), interrupt=True)
    except Exception as e:
        logger.error(f"Failed to jump to desktop {desktop_num}: {e}")
        speak(_("jump_failed", desktop=desktop_num, error=str(e)[:50]), interrupt=True)

def prompt_jump_desktop():
    import core.api
    num_str = core.api.prompt_text(_("prompt_title"), _("prompt_msg"))
    if not num_str:
        return
        
    try:
        desktop_num = int(num_str)
        if desktop_num < 1:
            raise ValueError
        jump_desktop(desktop_num)
    except ValueError:
        speak(_("prompt_invalid"), interrupt=True)

def _create_pin_callback(slot):
    return lambda: pin_window(slot)

def _create_teleport_callback(slot):
    return lambda: teleport_window(slot)

def _create_check_callback(slot):
    return lambda: check_window(slot)

def _create_jump_callback(desktop_num):
    return lambda: jump_desktop(desktop_num)

def register(bus):
    logger.info("Registering Window Teleporter...")
    
    # Register hotkeys for Slots 1 to 10 using QWERTYUIOP
    slot_keys = ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P']
    
    for i in range(1, 11):
        slot = i
        keycode = ord(slot_keys[i-1])
        
        # 1. Pin Window: Ctrl + Shift + [Letter] (Lebih aman dari Win key)
        register_action(
            "window_teleporter",
            f"pin_slot_{slot}",
            _("teleporter_pin", slot=slot),
            default_keycode=keycode,
            default_ctrl=True,
            default_shift=True,
            default_win=False,
            default_alt=False,
            default_global=True,
            callback=_create_pin_callback(slot)
        )
        
        # 2. Teleport to Window: Ctrl + Alt + [Letter]
        register_action(
            "window_teleporter",
            f"jump_slot_{slot}",
            _("teleporter_jump", slot=slot),
            default_keycode=keycode,
            default_ctrl=True,
            default_alt=True,
            default_shift=False,
            default_win=False,
            default_global=True,
            callback=_create_teleport_callback(slot)
        )
        
        # 3. Check Slot: Ctrl + Alt + Shift + [Letter]
        register_action(
            "window_teleporter",
            f"check_slot_{slot}",
            _("teleporter_check", slot=slot),
            default_keycode=keycode,
            default_ctrl=True,
            default_alt=True,
            default_shift=True,
            default_win=False,
            default_global=True,
            callback=_create_check_callback(slot)
        )
        
        # 4. Jump Desktop: Alt + Shift + [Letter] (Aman dari Game Bar/Windows)
        register_action(
            "window_teleporter",
            f"desktop_jump_{slot}",
            _("desktop_jump", desktop=slot),
            default_keycode=keycode,
            default_ctrl=False,
            default_win=False,
            default_shift=True,
            default_alt=True,
            default_global=True,
            callback=_create_jump_callback(slot)
        )
    
    # 5. Jump to Any Desktop Prompt: Alt + Shift + D
    register_action(
        "window_teleporter",
        "desktop_prompt",
        _("desktop_prompt"),
        default_keycode=ord('D'),
        default_ctrl=False,
        default_win=False,
        default_shift=True,
        default_alt=True,
        default_global=True,
        callback=prompt_jump_desktop
    )

def teardown():
    pinned_windows.clear()
