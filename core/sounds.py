# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
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

def _sound_alias(filepath):
    # Build a unique alias from the filename so different files can overlap.
    return os.path.basename(filepath).replace(".", "").replace(" ", "")

def stop_sound(filepath):
    """
    Stop a sound started by play_sound() and release its file. Windows keeps a
    played file open (so it can't be replaced or deleted) until this is called
    or a file with the same name plays. Sounds share one channel per file name,
    so this stops whichever file of that name played last. Returns True if one
    was open.
    """
    try:
        import ctypes
        return ctypes.windll.winmm.mciSendStringW(f"close {_sound_alias(filepath)}", None, 0, None) == 0
    except Exception as e:
        logger.error(f"Error stopping sound {filepath}: {e}")
        return False

def play_sound(filepath):
    """
    Play a sound effect asynchronously so it never blocks the app.
    Uses the Windows MCI API so sounds can overlap.
    """
    if not os.path.exists(filepath):
        logger.warning(f"Sound file not found: {filepath}")
        return False
        
    try:
        import ctypes
        alias = _sound_alias(filepath)

        # Stop and close the same file if it is already playing.
        ctypes.windll.winmm.mciSendStringW(f"close {alias}", None, 0, None)

        # Re-apply the volume on every play, just in case.
        apply_system_volume(get_global_volume())

        ctypes.windll.winmm.mciSendStringW(f"open \"{filepath}\" type waveaudio alias {alias}", None, 0, None)

        ctypes.windll.winmm.mciSendStringW(f"play {alias}", None, 0, None)
        
        return True
    except Exception as e:
        logger.error(f"Error playing sound {filepath}: {e}")
        return False

# --- Sound theme override (since 2.6) ---
# A sound theme is a folder of .wav files named like the built-in ones. When a
# theme is set, play_internal_sound() plays the theme's copy of a sound and
# falls back to the built-in file when the theme doesn't have one.
_theme_dir = None


def get_builtin_sounds_dir():
    """The folder holding Hariku's own sounds."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "sounds")


# Core.json key holding the theme folder the user picked (core 2.7), so the
# next start plays that theme's start.wav before any extension has loaded.
REMEMBERED_THEME_KEY = "sound_theme_dir"
THEMES_FOLDER_NAME = "sound_themes"   # %APPDATA%\Hariku2\sound_themes, the Sound Themes extension's


def set_theme_dir(path, remember=False):
    """Use the sound theme in folder `path`, or pass None for the built-in sounds.
    With remember=True (core 2.7) the choice is also saved for the next start
    (None forgets it); a plain call, such as an extension unloading, leaves the
    saved choice alone."""
    global _theme_dir
    _theme_dir = os.path.abspath(path) if path else None
    logger.info(f"Sound theme folder: {_theme_dir or 'built-in sounds'}")
    if remember:
        try:
            config = core.api.load_data("Core")
            config = config if isinstance(config, dict) else {}
            if _theme_dir:
                config[REMEMBERED_THEME_KEY] = _theme_dir
            else:
                config.pop(REMEMBERED_THEME_KEY, None)
            core.api.save_data("Core", config)
        except Exception as e:
            logger.error(f"Could not save the sound theme choice: {e}")


def themes_root():
    """The folder the Sound Themes extension keeps its themes in."""
    return os.path.join(core.api.USER_DATA_DIR, THEMES_FOLDER_NAME)


def remembered_theme_dir(config=None):
    """The saved theme folder if it still exists inside the themes folder, else None."""
    if config is None:
        config = core.api.load_data("Core")
    path = config.get(REMEMBERED_THEME_KEY) if isinstance(config, dict) else None
    if not isinstance(path, str) or not path.strip():
        return None
    try:
        real = os.path.normcase(os.path.realpath(path))
        root = os.path.normcase(os.path.realpath(themes_root()))
    except (OSError, ValueError):
        return None
    if not real.startswith(root + os.sep) or not os.path.isdir(path):
        return None
    if os.path.basename(real).startswith("."):
        return None   # a half-made theme (Sound Themes builds them in ".work-" folders)
    return path


def load_remembered_theme():
    """At startup, before start.wav: use the theme the user picked last time, so
    its start sound plays. Returns the folder, or None for the built-in sounds."""
    try:
        path = remembered_theme_dir()
    except Exception as e:
        logger.error(f"Could not read the sound theme choice: {e}")
        path = None
    if path:
        set_theme_dir(path)
    return path


def get_theme_dir():
    """The current sound theme folder, or None when the built-in sounds are used."""
    return _theme_dir


def _is_plain_file_name(name):
    # Only a bare file name may be looked up in a theme folder, so a theme can
    # never lead Hariku to a file outside it.
    return (isinstance(name, str) and name.strip() != "" and ".." not in name
            and not any(c in name for c in '/\\:\0')
            and os.path.basename(name) == name)


def _theme_sound_path(sound_name):
    theme_dir = _theme_dir
    if not theme_dir or not _is_plain_file_name(sound_name):
        return None
    candidate = os.path.join(theme_dir, sound_name)
    if not os.path.isfile(candidate):
        return None
    # A link inside the theme must not point outside it either.
    real_dir = os.path.normcase(os.path.realpath(theme_dir))
    if not os.path.normcase(os.path.realpath(candidate)).startswith(real_dir + os.sep):
        return None
    return candidate


def play_internal_sound(sound_name):
    """
    Play a sound file from the hariku2/sounds/ folder, or the active sound
    theme's copy of it when the theme has one.
    """
    theme_path = _theme_sound_path(sound_name)
    if theme_path:
        return play_sound(theme_path)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sounds_dir = os.path.join(base_dir, "sounds")
    filepath = os.path.join(sounds_dir, sound_name)
    return play_sound(filepath)
