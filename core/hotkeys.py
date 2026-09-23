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
import logging
import wx
import time
import inspect

logger = logging.getLogger(__name__)

_app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
SETTINGS_DIR = os.path.join(_app_data, "Hariku2", "settings")
KEYBINDINGS_FILE = os.path.join(SETTINGS_DIR, "keybindings.json")

class Action:
    def __init__(self, extension_name, action_name, description, default_keycode, default_ctrl, callback, default_shift=False, default_alt=False, default_win=False, default_global=False):
        self.extension_name = extension_name
        self.action_name = action_name
        self.description = description
        self.default_keycode = default_keycode
        self.default_ctrl = default_ctrl
        self.default_shift = default_shift
        self.default_alt = default_alt
        self.default_win = default_win
        self.default_global = default_global
        self.callback = callback
        self.id = f"{extension_name}.{action_name}"
        
        # Backward compatibility: check if callback accepts 'tap_count'
        self.wants_tap_count = False
        try:
            sig = inspect.signature(callback)
            self.wants_tap_count = "tap_count" in sig.parameters
        except Exception:
            pass

actions = {} # action_id -> Action
keybindings = {} # (keycode, ctrl_down) -> (action_id, is_global)
saved_config = {} # action_id -> [{"keycode": 123, "ctrl": false, "global": true}, ...]

_next_hotkey_id = 100
_registered_hotkeys = {} # hotkey_id -> action_id

# State for Multi-Tap System
_last_hotkey_trigger = None
_last_hotkey_time = 0.0
_current_tap_count = 1
DOUBLE_TAP_TIMEOUT = 0.5

def init_hotkeys():
    if not os.path.exists(SETTINGS_DIR):
        os.makedirs(SETTINGS_DIR)
    load_keybindings()

def register_action(extension_name, action_name, description, default_keycode, default_ctrl, callback, default_shift=False, default_alt=False, default_win=False, default_global=False):
    action = Action(extension_name, action_name, description, default_keycode, default_ctrl, callback, default_shift, default_alt, default_win, default_global)
    actions[action.id] = action
    _rebuild_all_bindings()

def _rebuild_all_bindings():
    keybindings.clear()
    
    # Apply the defaults first.
    for action_id, action in actions.items():
        if action_id not in saved_config:
            if action.default_keycode is not None:
                keybindings[(action.default_keycode, action.default_ctrl, action.default_shift, action.default_alt, action.default_win)] = (action_id, action.default_global)
                
    # Override with saved_config (the user's configuration).
    for action_id in actions.keys():
        if action_id in saved_config:
            for b in saved_config[action_id]:
                # This automatically overrides the same shortcut from another action.
                keybindings[(b["keycode"], b.get("ctrl", False), b.get("shift", False), b.get("alt", False), b.get("win", False))] = (action_id, b.get("global", False))

    import core.api
    if core.api.main_window_instance:
        apply_global_hotkeys(core.api.main_window_instance)

def _execute_action(action, trigger_signature):
    global _last_hotkey_trigger, _last_hotkey_time, _current_tap_count
    
    now = time.time()
    if trigger_signature == _last_hotkey_trigger and (now - _last_hotkey_time) <= DOUBLE_TAP_TIMEOUT:
        _current_tap_count += 1
    else:
        _current_tap_count = 1
        
    _last_hotkey_trigger = trigger_signature
    _last_hotkey_time = now
    
    try:
        if action.wants_tap_count:
            action.callback(tap_count=_current_tap_count)
        else:
            action.callback()
    except Exception as e:
        logger.error(f"Error executing action {action.id}: {e}")

def process_key_event(keycode, ctrl_down, shift_down=False, alt_down=False, win_down=False):
    trigger_sig = ("local", keycode, ctrl_down, shift_down, alt_down, win_down)
    binding = keybindings.get((keycode, ctrl_down, shift_down, alt_down, win_down))
    if binding:
        action_id, is_global = binding
        if action_id in actions:
            _execute_action(actions[action_id], trigger_sig)
            return True
    return False

# --- Global Hotkey Management ---

def apply_global_hotkeys(window):
    global _next_hotkey_id, _registered_hotkeys
    
    for hid in _registered_hotkeys.keys():
        window.UnregisterHotKey(hid)
    _registered_hotkeys.clear()
    _next_hotkey_id = 100
    
    for (kc, ctrl, shift, alt, win), (act_id, is_global) in keybindings.items():
        if is_global and kc is not None:
            hid = _next_hotkey_id
            _next_hotkey_id += 1
            modifiers = wx.MOD_CONTROL if ctrl else wx.MOD_NONE
            if shift: modifiers |= wx.MOD_SHIFT
            if alt: modifiers |= wx.MOD_ALT
            if win: modifiers |= wx.MOD_WIN
            try:
                success = window.RegisterHotKey(hid, modifiers, kc)
                if success:
                    _registered_hotkeys[hid] = act_id
            except Exception as e:
                logger.error(f"Exception registering global hotkey {act_id}: {e}")

def process_global_hotkey(hotkey_id):
    if hotkey_id in _registered_hotkeys:
        action_id = _registered_hotkeys[hotkey_id]
        if action_id in actions:
            trigger_sig = ("global", hotkey_id)
            _execute_action(actions[action_id], trigger_sig)

def suspend_global_hotkeys():
    """Temporarily unregister all global hotkeys (e.g. while CaptureKeyDialog is open)."""
    import core.api
    window = core.api.main_window_instance
    if window:
        for hid in list(_registered_hotkeys.keys()):
            try:
                window.UnregisterHotKey(hid)
            except Exception:
                pass

def resume_global_hotkeys():
    """Re-register all global hotkeys after CaptureKeyDialog is closed."""
    import core.api
    window = core.api.main_window_instance
    if window:
        apply_global_hotkeys(window)

# --- Persistence ---

def load_keybindings():
    global saved_config
    if os.path.exists(KEYBINDINGS_FILE):
        try:
            with open(KEYBINDINGS_FILE, "r") as f:
                saved_config = json.load(f)

            # Migrate the old structure to the new one (a list).
            migrated = False
            for k, v in list(saved_config.items()):
                if isinstance(v, dict): # Old format
                    saved_config[k] = [v]
                    migrated = True
            if migrated:
                save_keybindings()
        except Exception:
            saved_config = {}

def save_keybindings():
    try:
        with open(KEYBINDINGS_FILE, "w") as f:
            json.dump(saved_config, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save keybindings: {e}")

def get_resolved_config():
    import copy
    resolved = copy.deepcopy(saved_config)
    for action_id, action in actions.items():
        if action_id not in resolved:
            resolved[action_id] = []
            if action.default_keycode is not None:
                resolved[action_id].append({
                    "keycode": action.default_keycode, 
                    "ctrl": action.default_ctrl, 
                    "shift": action.default_shift,
                    "alt": action.default_alt,
                    "win": action.default_win,
                    "global": action.default_global
                })
    return resolved

def apply_new_config(new_config):
    global saved_config
    saved_config = new_config
    save_keybindings()
    _rebuild_all_bindings()

def get_current_bindings(action_id):
    results = []
    for (kc, ctrl, shift, alt, win), (act_id, is_global) in keybindings.items():
        if act_id == action_id:
            results.append((kc, ctrl, shift, alt, win, is_global))
    return results

def format_key_name(keycode, ctrl, shift=False, alt=False, win=False):
    if keycode is None: return "None"
    name = ""
    if ctrl: name += "Ctrl + "
    if shift: name += "Shift + "
    if alt: name += "Alt + "
    if win: name += "Win + "
    special_keys = {
        wx.WXK_LEFT: "Left Arrow", wx.WXK_RIGHT: "Right Arrow",
        wx.WXK_UP: "Up Arrow", wx.WXK_DOWN: "Down Arrow",
        wx.WXK_PAGEUP: "Page Up", wx.WXK_PAGEDOWN: "Page Down",
        wx.WXK_HOME: "Home", wx.WXK_END: "End",
        wx.WXK_RETURN: "Enter", wx.WXK_SPACE: "Space",
        wx.WXK_ESCAPE: "Escape", wx.WXK_BACK: "Backspace",
        wx.WXK_TAB: "Tab",
    }
    if keycode in special_keys:
        name += special_keys[keycode]
    elif 32 <= keycode <= 126:
        name += chr(keycode).upper()
    else:
        name += f"Key({keycode})"
    return name
