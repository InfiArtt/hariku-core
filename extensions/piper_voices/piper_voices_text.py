# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Spoken and displayed text for Piper Voices, in the user's language. Model
card lines are shown as the card writes them (in English).
"""
import os

import core.voice
from core.i18n import get_translator

import piper_voices_catalogue as catalogue
import piper_voices_download as download

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("piper_voices", os.path.join(EXT_DIR, "locales"))

MB = 1024 * 1024


def voice_title(voice):
    """"news_tts" -> "News tts"."""
    name = " ".join(str(voice.get("name") or voice.get("key") or "").replace("_", " ").split())
    return name[:1].upper() + name[1:]


def quality_label(quality):
    labels = {"x_low": _("quality_x_low"), "low": _("quality_low"),
              "medium": _("quality_medium"), "high": _("quality_high")}
    return labels.get(quality, quality or "")


def voice_name(voice):
    """The name Hariku Voice lists: "News tts (medium)"."""
    return _("voice_name", name=voice_title(voice), quality=quality_label(voice.get("quality")))


def size_label(size_bytes):
    size_bytes = max(0, int(size_bytes or 0))
    if size_bytes >= MB:
        value = f"{size_bytes / MB:.1f}".replace(".", _("decimal_point"))
        return _("size_mb", value=value)
    return _("size_kb", value=max(1, round(size_bytes / 1024)))


def language_label(voice):
    """"Indonesian (Indonesia)": Windows' name for the language, or the
    catalogue's English one when Windows doesn't know it."""
    tag = voice.get("language") or ""
    name = core.voice.language_name(tag) if tag else ""
    if name and name != tag:
        return name
    english, country = voice.get("language_english"), voice.get("country_english")
    if english and country:
        return f"{english} ({country})"
    return english or tag or _("language_unknown")


def family_label(family, voices=()):
    """The Language choice's name for a language family ("Indonesian")."""
    if not family:
        return _("language_all")
    name = core.voice.language_name(family)
    if name and name != family:
        return name
    for voice in voices:
        if voice.get("family") == family and voice.get("language_english"):
            return voice["language_english"]
    return family


def installed_label(installed):
    return _("installed_yes") if installed else _("installed_no")


def card_lines(card):
    """The model card's dataset and license lines, and a warning when the
    license isn't clear."""
    if not card:
        return []
    lines = list(card.get("lines") or [])
    if not card.get("license"):
        lines.append(_("card_license_missing"))
    if not card.get("license_clear"):
        lines.append(_("license_unclear"))
    return lines


def details_text(voice, installed, card=None):
    """The Details field for the selected voice, one fact per line."""
    lines = [_("details_voice", name=voice_title(voice), language=language_label(voice)),
             _("details_quality", quality=quality_label(voice.get("quality")),
               speakers=voice.get("speakers") or 1)]
    if voice.get("size"):
        lines.append(_("details_size", size=size_label(voice["size"])))
    lines.append(_("details_installed") if installed else _("details_not_installed"))
    if card:
        lines.append(_("details_card_heading"))
        lines += card_lines(card)
    elif installed:
        lines.append(_("details_card_missing"))
    else:
        lines.append(_("details_card_pending"))
    return "\n".join(lines)


def confirm_summary(voice, card, runtime_size=0):
    """What the download dialog says before the user decides."""
    lines = [_("confirm_question", name=voice_title(voice), language=language_label(voice),
               quality=quality_label(voice.get("quality")))]
    size = voice.get("size") or 0
    if runtime_size:
        lines.append(_("confirm_size_runtime", size=size_label(size),
                       runtime=size_label(runtime_size), total=size_label(size + runtime_size)))
    else:
        lines.append(_("confirm_size", size=size_label(size)))
    license_text = (card or {}).get("license")
    if license_text:
        lines.append(_("confirm_license", license=license_text))
    else:
        lines.append(_("confirm_license_missing"))
    if not (card or {}).get("license_clear"):
        lines.append(_("license_unclear"))
    return "\n".join(lines)


def error_text(error):
    """A sentence for why something failed."""
    if isinstance(error, download.DownloadError):
        kind = error.kind
        if kind == "offline":
            return _("err_offline")
        if kind == "http":
            return _("err_http", code=error.detail or "?")
        if kind == "host":
            return _("err_host", host=error.detail or "?")
        if kind == "verify":
            return _("err_verify")
        if kind == "size":
            return _("err_size")
        if kind == "extract":
            return _("err_extract")
        if kind == "disk":
            return _("err_disk")
        return _("err_bad_data")
    if isinstance(error, catalogue.CatalogueError):
        return _("err_bad_data")
    if isinstance(error, OSError):
        return _("err_disk")
    return _("err_unexpected", error=str(error) or type(error).__name__)
