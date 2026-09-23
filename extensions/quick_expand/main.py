# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# ============================================================
# Quick Expand Extension for Hariku V2
# ============================================================
# Automatically expands custom typed abbreviations (like "my_email")
# into full text templates globally across Windows.
# ============================================================

import ctypes
from ctypes import wintypes
import logging
import time
import threading
import re
import wx

# --- Core Imports ---
import core.api
import core.preferences
from core.speech import speak

logger = logging.getLogger(__name__)

# ============================================================
# WINDOWS API & CTYPES CONFIGURATION
# ============================================================

# Constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002

# Virtual Key Codes
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SPACE = 0x20
VK_SHIFT = 0x10

# Types
LRESULT = wintypes.LPARAM

# Structures
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort)
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", INPUT_UNION)
    ]

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_ulong),
        ("scanCode", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

# Hook Callback Delegate Type
HOOKPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM
)

# Private DLL handles: setting argtypes on the shared ctypes.windll objects would
# change them for every other module that calls the same functions.
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD
]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM
]
user32.CallNextHookEx.restype = LRESULT

user32.SendInput.argtypes = [
    ctypes.c_uint,
    ctypes.POINTER(INPUT),
    ctypes.c_int
]
user32.SendInput.restype = ctypes.c_uint

user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


# ============================================================
# EXTENSION STATE
# ============================================================

EXPANSIONS = {}
typed_buffer = ""
is_sending_keys = False
hook_id = None
callback_keep_alive = None
queued_physical_keys = []
_hook_thread = None
_hook_thread_id = None

# ============================================================
# KEYBOARD SIMULATION UTILITIES
# ============================================================

def send_vk_key_paced(vk_code):
    """Simulates a key down and key up with a micro-delay to ensure target apps register it."""
    inputs = (INPUT * 1)()
    
    # Key down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].ii.ki.wVk = vk_code
    inputs[0].ii.ki.dwFlags = 0
    user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
    
    time.sleep(0.002)
    
    # Key up
    inputs[0].ii.ki.dwFlags = KEYEVENTF_KEYUP
    user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
    
    time.sleep(0.002)

def send_string_paced(s):
    """Sends a string character-by-character with micro-delays between down/up events."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    
    for char in s:
        if char == "\n":
            send_vk_key_paced(VK_RETURN)
        else:
            code = ord(char)
            inputs = (INPUT * 1)()
            
            # Key down
            inputs[0].type = INPUT_KEYBOARD
            inputs[0].ii.ki.wVk = 0
            inputs[0].ii.ki.wScan = code
            inputs[0].ii.ki.dwFlags = KEYEVENTF_UNICODE
            user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
            
            time.sleep(0.002)
            
            # Key up
            inputs[0].ii.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
            
            time.sleep(0.002)


# ============================================================
# HOOK LOGIC
# ============================================================

def handle_key(vk_code):
    """
    Manages the input buffer and checks if an expansion needs to be triggered.
    Returns True if the key event should be consumed/blocked, False otherwise.
    """
    global typed_buffer
    
    # Check shift modifier key state
    shift_pressed = (user32.GetKeyState(VK_SHIFT) & 0x8000) != 0
    
    # A-Z letters
    if 0x41 <= vk_code <= 0x5A:
        char = chr(vk_code).lower()
        typed_buffer += char
        return False
        
    # 0-9 digits (standard keyboard)
    elif 0x30 <= vk_code <= 0x39:
        char = chr(vk_code - 0x30 + ord('0'))
        typed_buffer += char
        return False
        
    # 0-9 digits (numeric keypad)
    elif 0x60 <= vk_code <= 0x69:
        char = chr(vk_code - 0x60 + ord('0'))
        typed_buffer += char
        return False
        
    # Minus / Underscore key
    elif vk_code == 0xBD:
        char = "_" if shift_pressed else "-"
        typed_buffer += char
        return False
        
    # Backspace
    elif vk_code == VK_BACK:
        if typed_buffer:
            typed_buffer = typed_buffer[:-1]
        return False
        
    # Trigger Keys (Space, Tab, Enter/Return)
    elif vk_code in (VK_SPACE, VK_TAB, VK_RETURN):
        if typed_buffer in EXPANSIONS:
            trigger_key = vk_code
            abbrev = typed_buffer
            replacement = EXPANSIONS[abbrev]
            
            # Run expansion in a separate thread so we don't stall the low-level hook
            threading.Thread(
                target=perform_expansion,
                args=(abbrev, replacement, trigger_key),
                daemon=True
            ).start()
            
            typed_buffer = ""
            return True  # Consume/block the trigger keypress
            
        typed_buffer = ""
        return False
        
    else:
        # Any other keyboard inputs resets the buffer
        typed_buffer = ""
        return False


def perform_expansion(abbrev, replacement, trigger_key):
    """Asynchronously erases the abbreviation and types the replacement text safely."""
    global is_sending_keys, typed_buffer
    is_sending_keys = True
    try:
        # 1. Erase abbreviation via Backspaces
        for _ in range(len(abbrev)):
            send_vk_key_paced(VK_BACK)
            
        time.sleep(0.01)
        
        # 2. Type out replacement text
        send_string_paced(replacement)
        
        # 3. Type the original consumed trigger key
        send_vk_key_paced(trigger_key)
        
    except Exception as e:
        logger.error(f"Quick Expand: Error executing text expansion: {e}")
    finally:
        # Flush any physical keys the user typed while we were injecting text
        for vk, is_keyup in queued_physical_keys:
            inputs = (INPUT * 1)()
            inputs[0].type = INPUT_KEYBOARD
            inputs[0].ii.ki.wVk = vk
            inputs[0].ii.ki.dwFlags = KEYEVENTF_KEYUP if is_keyup else 0
            user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
            time.sleep(0.002)
            
        queued_physical_keys.clear()
        
        is_sending_keys = False
        typed_buffer = ""


def keyboard_proc(nCode, wParam, lParam):
    """Low-level keyboard hook callback procedure."""
    global is_sending_keys, typed_buffer
    
    if nCode < 0:
        return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)
        
    try:
        struct = KBDLLHOOKSTRUCT.from_address(lParam)
        flags = struct.flags
        vk_code = struct.vkCode
        
        # Ignore synthetic/injected events to prevent feedback loops
        if flags & 0x10:
            return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)
            
        if is_sending_keys:
            # Physical key pressed DURING our text expansion injection!
            # Queue it up and block it so it doesn't interleave and scramble the text!
            is_keyup = (wParam == WM_KEYUP or wParam == WM_SYSKEYUP)
            queued_physical_keys.append((vk_code, is_keyup))
            return 1  # Block the physical key
            
        # Process physical keys normally
        if wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN:
            consume = handle_key(vk_code)
            
            if consume:
                return 1  # Consumed, prevent dispatching to other apps
                
    except Exception as e:
        logger.error(f"Quick Expand: Hook callback exception: {e}")
        
    return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)


def _hook_thread_main(ready):
    """Own the low-level keyboard hook and pump the messages that drive it.

    Windows runs a low-level hook's callback on the thread that installed it, and
    every keystroke in the system waits for that callback. On the UI thread, that
    wait included whatever the UI happened to be doing, which held up keys on
    their way to the screen reader. A dedicated thread only ever runs the hook.
    """
    global hook_id, callback_keep_alive, _hook_thread_id
    msg = wintypes.MSG()
    try:
        _hook_thread_id = kernel32.GetCurrentThreadId()
        # Create this thread's message queue before anyone can post WM_QUIT to it.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        # Keep-alive reference prevents ctypes callback garbage collection crash
        callback_keep_alive = HOOKPROC(keyboard_proc)
        hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, callback_keep_alive, kernel32.GetModuleHandleW(None), 0)
    except Exception as e:
        logger.error(f"Quick Expand: Failed to install hook: {e}")
        hook_id = None
    finally:
        ready.set()

    if not hook_id:
        logger.error(f"Quick Expand: SetWindowsHookExW failed (error {ctypes.get_last_error()}).")
        callback_keep_alive = None
        return

    logger.info("Quick Expand: Low-level keyboard hook installed on its own thread.")
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        pass  # hook callbacks are dispatched inside GetMessageW

    user32.UnhookWindowsHookEx(hook_id)
    hook_id = None
    callback_keep_alive = None
    logger.info("Quick Expand: Keyboard hook uninstalled.")


def install_hook():
    """Start the keyboard hook thread, but only when there is something to expand,
    so users without abbreviations never have a system-wide hook running."""
    global _hook_thread
    if not EXPANSIONS:
        return
    if _hook_thread is not None and _hook_thread.is_alive():
        return
    ready = threading.Event()
    _hook_thread = threading.Thread(target=_hook_thread_main, args=(ready,),
                                    name="quick-expand-hook", daemon=True)
    _hook_thread.start()
    ready.wait(2)


def uninstall_hook():
    """Stop the hook thread; it unhooks itself when its message loop ends."""
    global _hook_thread
    thread = _hook_thread
    if thread is not None and thread.is_alive() and _hook_thread_id:
        user32.PostThreadMessageW(_hook_thread_id, WM_QUIT, 0, 0)
        thread.join(2)
    _hook_thread = None


# ============================================================
# PREFERENCES SETTINGS PANEL (wxPython)
# ============================================================

class ExpanderSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        # Load the user's abbreviations (starts empty; no demo entries).
        self.expansions = dict(core.api.load_data("QuickExpand") or {})

        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Header title
        title_text = wx.StaticText(self, label="Pengaturan Quick Expand (Text Expander)")
        title_font = title_text.GetFont()
        title_font.MakeBold()
        title_text.SetFont(title_font)
        vbox.Add(title_text, 0, wx.ALL, 10)
        
        # Description
        desc_text = (
            "Daftar singkatan di bawah ini akan diganti secara otomatis saat Anda mengetiknya\n"
            "diikuti oleh tombol Spasi, Tab, atau Enter secara global di seluruh sistem Windows.\n"
            "Hanya mendukung huruf (a-z), angka (0-9), garis hubung (-), dan garis bawah (_)."
        )
        vbox.Add(wx.StaticText(self, label=desc_text), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # List of expansions
        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list_ctrl.InsertColumn(0, "Singkatan (Abbrev)", width=120)
        self.list_ctrl.InsertColumn(1, "Teks Pengganti (Replacement)", width=350)
        vbox.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # Populate List View
        self.populate_list()
        
        # Inputs Form
        form_sizer = wx.FlexGridSizer(2, 2, 10, 10)
        form_sizer.AddGrowableCol(1, 1)
        
        form_sizer.Add(wx.StaticText(self, label="Singkatan:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_abbrev = wx.TextCtrl(self)
        form_sizer.Add(self.txt_abbrev, 1, wx.EXPAND)
        
        form_sizer.Add(wx.StaticText(self, label="Teks Pengganti:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_replace = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_BESTWRAP)
        form_sizer.Add(self.txt_replace, 1, wx.EXPAND)
        
        vbox.Add(form_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # Action Buttons
        hbox_buttons = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_add = wx.Button(self, label="Tambah / Perbarui")
        self.btn_add.Bind(wx.EVT_BUTTON, self.on_add_update)
        hbox_buttons.Add(self.btn_add, 1, wx.ALL, 5)
        
        self.btn_delete = wx.Button(self, label="Hapus Pilihan")
        self.btn_delete.Bind(wx.EVT_BUTTON, self.on_delete)
        hbox_buttons.Add(self.btn_delete, 1, wx.ALL, 5)
        
        vbox.Add(hbox_buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # UI Event Bindings
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        
        self.SetSizer(vbox)
        
    def populate_list(self):
        self.list_ctrl.DeleteAllItems()
        for i, (abbrev, repl) in enumerate(sorted(self.expansions.items())):
            index = self.list_ctrl.InsertItem(i, abbrev)
            # Show single line visual layout of multiline texts
            self.list_ctrl.SetItem(index, 1, repl.replace("\n", " [LF] "))
            
    def on_item_selected(self, event):
        index = event.GetIndex()
        abbrev = self.list_ctrl.GetItemText(index, 0)
        # Fetch actual text with original breaks
        repl = self.expansions.get(abbrev, "")
        self.txt_abbrev.SetValue(abbrev)
        self.txt_replace.SetValue(repl)
        
    def on_add_update(self, event):
        abbrev = self.txt_abbrev.GetValue().strip().lower()
        repl = self.txt_replace.GetValue()
        
        if not abbrev or not repl:
            core.api.show_message("Error", "Isian singkatan dan teks pengganti tidak boleh kosong.")
            return
            
        # Input validation
        if not re.match("^[a-z0-9_-]+$", abbrev):
            core.api.show_message(
                "Error",
                "Singkatan hanya boleh mengandung huruf kecil (a-z), angka (0-9), tanda minus (-), dan garis bawah (_)."
            )
            return
            
        self.expansions[abbrev] = repl
        self.populate_list()
        self.txt_abbrev.Clear()
        self.txt_replace.Clear()
        speak(f"Singkatan {abbrev} berhasil ditambahkan atau diperbarui.")
        
    def on_delete(self, event):
        index = self.list_ctrl.GetFirstSelected()
        if index == -1:
            core.api.show_message("Error", "Pilih singkatan pada list terlebih dahulu untuk menghapus.")
            return
            
        abbrev = self.list_ctrl.GetItemText(index, 0)
        if abbrev in self.expansions:
            del self.expansions[abbrev]
            self.populate_list()
            self.txt_abbrev.Clear()
            self.txt_replace.Clear()
            speak(f"Singkatan {abbrev} berhasil dihapus.")
            
    def ApplyChanges(self):
        """Save settings and apply them instantly to the active expansion runtime."""
        core.api.save_data("QuickExpand", self.expansions)
        global EXPANSIONS
        EXPANSIONS = self.expansions
        # The hook runs only while at least one abbreviation exists.
        if EXPANSIONS:
            install_hook()
        else:
            uninstall_hook()


# Settings Panel Hook Instances
_panel_instance = None

def _create_panel(parent):
    global _panel_instance
    _panel_instance = ExpanderSettingsPanel(parent)
    return _panel_instance

def _apply_panel():
    if _panel_instance:
        _panel_instance.ApplyChanges()


# ============================================================
# EXTENSION LIFECYCLE HOOKS
# ============================================================

def on_app_startup():
    """Triggered on application launch."""
    install_hook()


def on_active_window_changed(window_info):
    """Triggered when the focused foreground window changes in Windows."""
    global typed_buffer
    typed_buffer = ""  # Clear buffer to prevent cross-app typing leak


def register(bus):
    """Entry point called by the extension loader on load."""
    global EXPANSIONS
    logger.info("Quick Expand: Loading extension...")
    
    # Load the user's abbreviations. No demo entries are created: a system-wide
    # keyboard hook should only run for someone who set up an abbreviation.
    EXPANSIONS = dict(core.api.load_data("QuickExpand") or {})

    # Connect lifecycle events
    bus.subscribe("on_app_startup", on_app_startup)
    bus.subscribe("on_active_window_changed", on_active_window_changed)
    
    # Connect Preferences GUI
    core.preferences.register_panel(
        "Quick Expand",
        "",
        _create_panel,
        _apply_panel
    )
    
    # Support for live hot-reloading: If UI is already running, install hook immediately
    if core.api.main_window_instance is not None:
        install_hook()
        
    logger.info("Quick Expand: Extension registered successfully.")


def teardown():
    """Directly called by the extension manager during unload or shutdown."""
    logger.info("Quick Expand: Tearing down extension...")
    uninstall_hook()
