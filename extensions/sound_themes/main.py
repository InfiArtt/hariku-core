# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Sound Themes — Hariku V2 extension.

Sounds are how many Hariku users "see" the app, so this lets them change them
the way others change a colour theme. A theme is a folder of WAV files named
like Hariku's sounds (see sound_themes_store.py); the core plays the active
theme's copy of a sound and falls back to its own (core.sounds.set_theme_dir,
core 2.6).

  sound_themes_store.py - theme folders, the active theme, import/export (no wx)
  sound_themes_text.py  - spoken and displayed text
  sound_themes_ui.py    - the Preferences page and its name dialog
"""

import logging

import core.hotkeys
import core.preferences
import core.sounds
from core.speech import speak

import sound_themes_store as store
import sound_themes_text as text
import sound_themes_ui
from sound_themes_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Sound Themes"   # fixed, so the action id is the same in every language

_panel = None


def next_sound_theme():
    """Hotkey: switch to the next theme and play its startup sound as a preview."""
    try:
        name = store.next_theme()
    except store.ThemeError as e:
        speak(text.error_text(e), interrupt=True)
        return
    speak(text.applied_text(name), interrupt=True)
    core.sounds.play_internal_sound("start.wav")
    if _panel:
        _panel.refresh(select=name)


def _create_panel(parent):
    global _panel
    _panel = sound_themes_ui.SoundThemesPanel(parent)
    return _panel


def register(bus):
    global _panel
    _panel = None
    try:
        name = store.restore_active()
        if name:
            logger.info(f"[Sound Themes] Using sound theme {name!r}.")
    except Exception:
        logger.exception("[Sound Themes] Could not apply the saved sound theme")
    # Shift+S ("sound") is free in the core, the bundled extensions and the
    # store packages. Nothing to apply on OK: the page's buttons act at once.
    core.hotkeys.register_action(EXT_NAME, "next_theme", _("action_next_theme"),
                                 ord("S"), False, next_sound_theme, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, None)
    logger.info("Sound Themes extension loaded.")


def teardown():
    global _panel
    _panel = None
    # This extension subscribes to no bus events; it only has to hand the
    # sounds back to the core.
    core.sounds.set_theme_dir(None)
    logger.info("Sound Themes extension unloaded.")
