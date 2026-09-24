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
import voice_control_kws as kws
import voice_control_wake as wake

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("voice_control", os.path.join(EXT_DIR, "locales"))

MB = 1000 * 1000

# Words a command bar user says besides command names, for whisper's prompt.
PROMPT_WORDS = {
    "id": ["ya", "tidak", "simpan", "batal", "ingatkan aku", "besok", "jam", "hari ini"],
    "en": ["yes", "no", "save", "cancel", "remind me", "tomorrow", "today"],
}

# More ways to ask Aruna for "Pause or resume the wake phrase", in every
# language (core.commands matches them whatever Hariku's language is).
WAKE_ALIASES = [
    "pause the wake phrase", "resume the wake phrase", "stop listening for hey aruna",
    "start listening for hey aruna", "wake phrase", "wake word", "pause wake word",
    "jeda frasa pemanggil", "lanjutkan frasa pemanggil", "frasa pemanggil",
    "berhenti mendengarkan hey aruna", "dengarkan hey aruna lagi",
]

ITEMS = ("runtime", "tiny", "base", "small", "wake")


def size_label(size_bytes):
    """ "77.7 MB" (decimal megabytes, as download sites show them)."""
    value = f"{max(0, int(size_bytes or 0)) / MB:.1f}".replace(".", _("decimal_point"))
    return _("size_mb", value=value)


def item_name(item):
    return {"runtime": _("item_runtime"), "tiny": _("model_tiny"), "base": _("model_base"),
            "small": _("model_small"), "wake": _("item_wake")}.get(item, item)


def item_size(item):
    if item == "runtime":
        return download.RUNTIME_SIZE
    if item == "wake":
        return download.WAKE_SIZE
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


def wake_sensitivity_choices():
    """[(setting, label)] of the Wake phrase sensitivity choice, least sensitive first."""
    labels = {"low": _("sensitivity_low"), "normal": _("sensitivity_normal"),
              "high": _("sensitivity_high")}
    return [(name, labels[name]) for name in wake.SENSITIVITIES]


def wake_advice(problem):
    """What the page says about a wake phrase: what's wrong with it, if
    anything, and that English words work best with this model."""
    warning = {
        "empty": _("wake_advice_empty"),
        "digits": _("wake_advice_digits"),
        "unsupported": _("wake_advice_unsupported"),
        "common": _("wake_advice_common"),
        "one_word": _("wake_advice_one_word"),
        "short": _("wake_advice_short"),
        "long": _("wake_advice_long"),
    }.get(problem)
    note = _("wake_advice_note")
    return f"{warning} {note}" if warning else note


def wake_status(state, phrase):
    """The wake phrase's part of the page's status line ("" when it's off)."""
    return {
        wake.LISTENING: _("wake_status_listening", phrase=phrase),
        wake.BUSY: _("wake_status_listening", phrase=phrase),
        wake.PAUSED: _("wake_status_paused"),
        wake.QUIET: _("wake_status_quiet"),
        wake.MISSING: _("wake_status_missing"),
        wake.BLOCKED: _("wake_status_blocked"),
        wake.MIC_ERROR: _("wake_status_mic"),
        wake.ENGINE_ERROR: _("wake_status_error"),
    }.get(state, "")


def wake_engine_error(error):
    """Why the wake phrase listener didn't start, for the user."""
    if isinstance(error, kws.KwsError):
        if error.kind in ("missing", "damaged", "version", "load"):
            return _("wake_err_damaged")
        if error.kind == "path":
            return _("wake_err_path")
        if error.kind == "keywords":
            return _("wake_err_phrase")
    if isinstance(error, ValueError):
        return _("wake_err_phrase")
    return _("wake_err_engine")


def wake_problem(kind, value):
    """What to say (once) when the wake phrase can't listen: ("blocked" or
    "mic", a microphone error kind) or ("engine", the error)."""
    if kind in ("blocked", "mic"):
        return _("wake_problem", reason=mic_error(value))
    return _("wake_problem_engine", reason=wake_engine_error(value))


def wake_test_outcome(count, seconds, stopped=False):
    """What the wake phrase test says when it ends."""
    if stopped:
        return _("wake_test_stopped", count=count) if count > 0 else _("wake_test_cancelled")
    if count <= 0:
        return _("wake_test_none")
    if count == 1:
        return _("wake_test_done_once", seconds=seconds)
    return _("wake_test_done", count=count, seconds=seconds)


def wake_heard(count):
    """What the test says for each time it hears the phrase."""
    return _("wake_test_heard") if count <= 1 else _("wake_test_heard_count", count=count)


def wake_test_message(result, error):
    """What the page shows and says when the wake phrase test ends."""
    if error is None:
        return wake_test_outcome(result["count"], result["seconds"], result.get("stopped"))
    kind = getattr(error, "kind", None)
    if isinstance(error, audio.MicrophoneError):
        return mic_error(kind)
    if isinstance(error, (kws.KwsError, ValueError)):
        return _("wake_test_failed", reason=wake_engine_error(error))
    if isinstance(error, RuntimeError) and str(error) == "busy":
        return _("mic_test_busy")
    return _("wake_test_failed", reason=_("wake_err_engine"))


def prompt_words(language=None):
    language = (language or get_current_language() or "en").split("-")[0]
    return PROMPT_WORDS.get(language, PROMPT_WORDS["en"])


def confirm_download(item, need_runtime):
    """What the download question says: what, how big, from where, license."""
    if item == "runtime":
        return _("confirm_runtime", size=size_label(download.RUNTIME_SIZE))
    if item == "wake":
        return _("confirm_wake", runtime=size_label(download.WAKE_RUNTIME_SIZE),
                 model=size_label(download.WAKE_MODEL_SIZE),
                 total=size_label(download.WAKE_SIZE))
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
        if kind == "unsupported":
            return _("err_unsupported")
        if kind == "in_use":
            return _("err_in_use")
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
