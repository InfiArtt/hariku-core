import wx.adv
import logging
import os
import core.api
from core.i18n import get_translator

_ = get_translator("core")

logger = logging.getLogger(__name__)

def get_global_volume():
    config = core.api.load_data("Core")
    return config.get("volume", 100)

def apply_system_volume(vol_percent):
    import ctypes
    vol = max(0, min(100, vol_percent))
    # Convert percentage to 16-bit word (0x0000 to 0xFFFF)
    vol_word = int((vol / 100.0) * 0xFFFF)
    # Pack left and right channels
    volume_dword = (vol_word & 0xFFFF) | ((vol_word & 0xFFFF) << 16)
    # Apply to default wave output device (ID 0)
    ctypes.windll.winmm.waveOutSetVolume(0, volume_dword)

def set_global_volume(vol_percent):
    vol = max(0, min(100, vol_percent))
    config = core.api.load_data("Core")
    config["volume"] = vol
    core.api.save_data("Core", config)
    apply_system_volume(vol)
    return vol

def volume_up():
    from core.speech import speak
    vol = get_global_volume()
    new_vol = min(100, vol + 5)
    set_global_volume(new_vol)
    speak(_("volume_status", percent=new_vol))

def volume_down():
    from core.speech import speak
    vol = get_global_volume()
    new_vol = max(0, vol - 5)
    set_global_volume(new_vol)
    speak(_("volume_status", percent=new_vol))

def play_sound(filepath):
    """
    Memainkan efek suara secara asinkron agar tidak memblokir aplikasi.
    Menggunakan MCI API Windows agar suara bisa tumpang tindih (overlapping).
    """
    if not os.path.exists(filepath):
        logger.warning(f"Sound file not found: {filepath}")
        return False
        
    try:
        import ctypes
        filename = os.path.basename(filepath)
        # Buat alias unik berdasarkan nama file agar file yang berbeda bisa tumpang tindih
        alias = filename.replace(".", "").replace(" ", "")
        
        # Hentikan dan tutup jika file yang sama sedang dimainkan
        ctypes.windll.winmm.mciSendStringW(f"close {alias}", None, 0, None)
        
        # Terapkan volume setiap kali memutar untuk berjaga-jaga
        apply_system_volume(get_global_volume())
        
        # Buka
        ctypes.windll.winmm.mciSendStringW(f"open \"{filepath}\" type waveaudio alias {alias}", None, 0, None)
        
        # Mainkan
        ctypes.windll.winmm.mciSendStringW(f"play {alias}", None, 0, None)
        
        return True
    except Exception as e:
        logger.error(f"Error playing sound {filepath}: {e}")
        return False

def play_internal_sound(sound_name):
    """
    Memainkan file suara dari folder hariku2/sounds/
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sounds_dir = os.path.join(base_dir, "sounds")
    filepath = os.path.join(sounds_dir, sound_name)
    return play_sound(filepath)
