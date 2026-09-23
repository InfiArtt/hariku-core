# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for Sound Themes, in the user's language. List rows
are whole sentences so a screen reader says everything on one arrow press.
"""

import os

from core.i18n import get_translator

import sound_themes_store as store

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("sound_themes", os.path.join(EXT_DIR, "locales"))

# ThemeError codes -> message keys.
ERROR_KEYS = {
    "name_empty": "err_name_empty",
    "name_too_long": "err_name_too_long",
    "name_invalid": "err_name_invalid",
    "name_reserved": "err_name_reserved",
    "name_exists": "err_name_exists",
    "default_readonly": "err_default_readonly",
    "not_found": "err_not_found",
    "unknown_sound": "err_unknown_sound",
    "too_big": "err_too_big",
    "not_wav": "err_not_wav",
    "file_missing": "err_file_missing",
    "file_unreadable": "err_file_unreadable",
    "io": "err_io",
    "delete_active": "err_delete_active",
    "no_other_themes": "err_no_other_themes",
    "archive_unreadable": "err_archive_unreadable",
    "archive_unsafe": "err_archive_unsafe",
    "archive_too_large": "err_archive_too_large",
    "archive_no_sounds": "err_archive_no_sounds",
    "archive_all_default": "err_archive_all_default",
    "export_empty": "err_export_empty",
}


def error_text(error):
    code = getattr(error, "code", "io")
    params = getattr(error, "params", None) or {}
    return _(ERROR_KEYS.get(code, "err_io"), **params)


def theme_name(name):
    """A theme's name as shown and spoken; None is the Default theme."""
    return _("default_name") if name is None else name


def theme_row(name, active, own_count):
    parts = [_("default_row") if name is None else name]
    if active:
        parts.append(_("row_in_use"))
    if name is not None:
        if own_count == 0:
            parts.append(_("row_own_none"))
        elif own_count == 1:
            parts.append(_("row_own_one"))
        else:
            parts.append(_("row_own_many", count=own_count))
    return ", ".join(parts)


def sound_label(sound):
    """A sound's name without ".wav" ("confirm")."""
    return sound[:-4] if sound.lower().endswith(".wav") else sound


def sound_description(sound):
    key = store.SOUND_KEYS.get(sound)
    if key == "snd_writing":
        return _("snd_writing", number=sound_label(sound)[-1])
    return _(key) if key else _("snd_other")


def sound_row(sound, theme, custom):
    row = _("sound_row", sound=sound_label(sound), description=sound_description(sound))
    if theme is None:
        return row
    return ", ".join([row, _("status_custom") if custom else _("status_default")])


def applied_text(name):
    return _("default_applied") if name is None else _("theme_applied", name=name)
