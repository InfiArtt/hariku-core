# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Spoken and displayed text for Voice Control, in the user's language. Spoken
replies say "kamu"/"aku" in Indonesian, like the quick reminder's read-back.
"""
import os

from core.i18n import get_current_language, get_translator

import voice_control_audio as audio
import voice_control_download as download
import voice_control_engine as engine

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("voice_control", os.path.join(EXT_DIR, "locales"))

MB = 1000 * 1000

# Words a command bar user says besides command names, for whisper's prompt.
PROMPT_WORDS = {
    "id": ["ya", "tidak", "simpan", "batal", "ingatkan aku", "besok", "jam", "hari ini"],
    "en": ["yes", "no", "save", "cancel", "remind me", "tomorrow", "today"],
}

ITEMS = ("runtime", "tiny", "base", "small")


def size_label(size_bytes):
    """ "77.7 MB" (decimal megabytes, as download sites show them)."""
    value = f"{max(0, int(size_bytes or 0)) / MB:.1f}".replace(".", _("decimal_point"))
    return _("size_mb", value=value)


def item_name(item):
    return {"runtime": _("item_runtime"), "tiny": _("model_tiny"), "base": _("model_base"),
            "small": _("model_small")}.get(item, item)


def item_size(item):
    if item == "runtime":
        return download.RUNTIME_SIZE
    return download.MODELS[item]["size"]


def seconds_label(seconds):
    value = f"{float(seconds):.1f}".replace(".", _("decimal_point"))
    return _("seconds", value=value)


def status_label(item, installed, speeds=None, percent=None):
    """The Status column: installed or not, a model's measured speed, or the
    download's progress."""
    if percent is not None:
        return _("status_downloading_short", percent=percent)
    if not installed:
        return _("installed_no")
    speed = (speeds or {}).get(item)
    if speed:
        return _("installed_speed", speed=seconds_label(speed))
    return _("installed_yes")


def model_choices():
    """[(setting, label)] of the Recognition model choice."""
    return [("auto", _("choice_auto")), ("tiny", _("choice_tiny")),
            ("base", _("choice_base")), ("small", _("choice_small"))]


def silence_label(milliseconds):
    return seconds_label(milliseconds / 1000.0)


def sensitivity_choices():
    """[(setting, label)] of the Microphone sensitivity choice, least sensitive first."""
    labels = {"low": _("sensitivity_low"), "normal": _("sensitivity_normal"),
              "high": _("sensitivity_high"), "very_high": _("sensitivity_very_high")}
    return [(name, labels[name]) for name in audio.SENSITIVITIES]


def sensitivity_label(name):
    return dict(sensitivity_choices()).get(name, name)


def prompt_words(language=None):
    language = (language or get_current_language() or "en").split("-")[0]
    return PROMPT_WORDS.get(language, PROMPT_WORDS["en"])


def confirm_download(item, need_runtime):
    """What the download question says: what, how big, from where, license."""
    if item == "runtime":
        return _("confirm_runtime", size=size_label(download.RUNTIME_SIZE))
    lines = [_("confirm_model", name=item_name(item), size=size_label(item_size(item)))]
    if need_runtime:
        lines.append(_("confirm_with_runtime", size=size_label(download.RUNTIME_SIZE),
                       total=size_label(item_size(item) + download.RUNTIME_SIZE)))
    if item == "small":
        lines.append(_("confirm_small_slow"))
    lines.append(_("confirm_license"))
    return "\n".join(lines)


def mic_error(kind):
    """What to say when the microphone can't be used, and where to fix it."""
    return {
        "none": _("mic_none"),
        "busy": _("mic_busy"),
        "blocked_device": _("mic_blocked_device"),
        "blocked_apps": _("mic_blocked_apps"),
        "blocked_desktop": _("mic_blocked_desktop"),
        "silent": _("mic_silent"),
    }.get(kind, _("mic_failed"))


def engine_error(error):
    if isinstance(error, engine.EngineError):
        if error.kind == "missing":
            return _("err_not_ready")
        if error.kind == "timeout":
            return _("err_timeout")
        return _("err_engine")
    return _("err_unexpected")


def download_error(error):
    if isinstance(error, download.DownloadError):
        kind = error.kind
        if kind == "offline":
            return _("err_offline")
        if kind == "http":
            return _("err_http", code=error.detail or "?")
        if kind == "host":
            return _("err_host", host=error.detail or "?")
        if kind in ("verify", "size"):
            return _("err_verify")
        if kind == "extract":
            return _("err_extract")
        if kind == "disk":
            return _("err_disk")
        return _("err_bad_data")
    if isinstance(error, OSError):
        return _("err_disk")
    return _("err_unexpected")


def db_label(level):
    """A level (RMS of 16-bit samples) as whole dB below full scale: "-38"."""
    return f"{audio.level_db(level):.0f}"


def calibration_message(calibration):
    """What the microphone test says: the voice's and the room's level, and
    the sensitivity it set, or what's wrong and how to fix it."""
    room = db_label(calibration.room)
    if calibration.problem == "no_speech" or calibration.voice is None:
        return _("calibrate_no_speech", room=room)
    values = {"voice": db_label(calibration.voice), "room": room,
              "level": sensitivity_label(calibration.sensitivity)}
    if calibration.problem == "too_quiet":
        return _("calibrate_too_quiet", **values)
    if calibration.problem == "too_noisy":
        return _("calibrate_too_noisy", **values)
    return _("calibrate_done", **values)


def mic_test_outcome(result, error):
    """What the page does with the microphone test's answer: (the message to
    show and say, the sensitivity to select or None)."""
    if error is not None:
        kind = getattr(error, "kind", None)
        return (mic_error(kind) if kind else _("mic_test_busy")), None
    calibration = result["calibration"]
    return calibration_message(calibration), calibration.sensitivity
