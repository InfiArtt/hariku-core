import threading
import time
import ctypes
import os
import core.api
from core.sounds import play_sound

stop_flag = False
poll_thread = None

VK_CAPITAL = 0x14
VK_NUMLOCK = 0x90

def get_config():
    config = core.api.load_data("key_notifier")
    ext_dir = os.path.dirname(os.path.abspath(__file__))
    
    if "sound_on" not in config:
        default_on = os.path.join(ext_dir, "sounds", "on.wav")
        config["sound_on"] = default_on if os.path.exists(default_on) else ""
    if "sound_off" not in config:
        default_off = os.path.join(ext_dir, "sounds", "off.wav")
        config["sound_off"] = default_off if os.path.exists(default_off) else ""
    if "sound_loop" not in config:
        default_loop = os.path.join(ext_dir, "sounds", "loop.wav")
        config["sound_loop"] = default_loop if os.path.exists(default_loop) else ""
        
    config.setdefault("monitor_capslock", True)
    config.setdefault("monitor_numlock", False)
    config.setdefault("loop_enabled", True)
    config.setdefault("loop_interval_sec", 2.0)
    
    return config

def play_if_exists(filepath):
    if filepath and os.path.exists(filepath):
        play_sound(filepath)
    else:
        # Fallback jika file audio tidak ditemukan tapi user meminta suara
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)

def _poll_keys():
    last_caps = ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1
    last_num = ctypes.windll.user32.GetKeyState(VK_NUMLOCK) & 1
    last_loop_time = time.time()
    
    while not stop_flag:
        time.sleep(0.1)
        config = get_config()
        
        current_caps = ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1
        current_num = ctypes.windll.user32.GetKeyState(VK_NUMLOCK) & 1
        
        # Check toggles
        if config["monitor_capslock"] and current_caps != last_caps:
            if current_caps == 1:
                play_if_exists(config["sound_on"])
            else:
                play_if_exists(config["sound_off"])
            last_loop_time = time.time() # Reset loop timer on toggle
            
        if config["monitor_numlock"] and current_num != last_num:
            if current_num == 1:
                play_if_exists(config["sound_on"])
            else:
                play_if_exists(config["sound_off"])
            last_loop_time = time.time()
            
        last_caps = current_caps
        last_num = current_num
        
        # Check loop
        if config["loop_enabled"]:
            is_any_on = False
            if config["monitor_capslock"] and current_caps == 1:
                is_any_on = True
            if config["monitor_numlock"] and current_num == 1:
                is_any_on = True
                
            if is_any_on:
                interval = max(2.0, config["loop_interval_sec"])
                if time.time() - last_loop_time >= interval:
                    play_if_exists(config["sound_loop"])
                    last_loop_time = time.time()

def register(bus):
    global stop_flag, poll_thread
    stop_flag = False
    poll_thread = threading.Thread(target=_poll_keys, daemon=True)
    poll_thread.start()
    
    # Register Preferences Panel secara dinamis!
    import core.preferences
    # Local import agar wxPython load di thread UI jika dibutuhkan
    from settings_ui import KeyNotifierSettingsPanel
    
    _panel_instance = None
    
    def create_panel(parent):
        nonlocal _panel_instance
        _panel_instance = KeyNotifierSettingsPanel(parent)
        return _panel_instance

    def apply_settings():
        if _panel_instance:
            _panel_instance.ApplyChanges()
            
    core.preferences.register_panel("Extensions", "Key Notifier", create_panel, apply_settings)
    
    bus.subscribe("on_unload", _unload)

def _unload():
    global stop_flag
    stop_flag = True
