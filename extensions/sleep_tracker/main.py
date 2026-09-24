# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Sleep Pattern — Hariku V2 extension.

Estimates when you slept from when you used the computer, the way a phone's
sleep tracker does: hours without touching the keyboard or mouse at night mean
you were asleep; still using it after your bedtime means you stayed up late.

  sleep_tracker_system.py   - Windows input and clock readings (ctypes, no hooks)
  sleep_tracker_store.py    - the minute record, gaps, settings, corrections
  sleep_tracker_analysis.py - finding the sleep in a night (pure functions)
  sleep_tracker_text.py     - sentences in the user's language
  sleep_tracker_ui.py       - Preferences page, sleep history, details

Once a minute (on_minute_tick) one sample is read and the minute is marked
active or inactive in memory; the record is saved every 10 minutes and when
Hariku closes. Only active / inactive / unknown per minute is kept, for 90
days, in Hariku's data folder on this computer. Nothing is sent anywhere.

Also adds last night's sleep to the Morning Briefing ("on_briefing_collect",
see briefing_core.py) and can remind the user to rest after bedtime.
"""

import datetime
import logging

import core.api
import core.hotkeys
import core.preferences
import core.sounds
from core.speech import speak

try:
    import core.personal   # core 2.7: what the user wants to be called
except ImportError:
    pass

import sleep_tracker_analysis as analysis
import sleep_tracker_store as store
import sleep_tracker_system as system
import sleep_tracker_text as text
import sleep_tracker_ui as ui
from sleep_tracker_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Sleep Pattern"            # fixed, so saved hotkeys survive a language change
DATA_KEY = "SleepTracker"             # settings, corrections, last nudge
ACTIVITY_KEY = "SleepTrackerActivity" # the minute record and the last sample
NUDGE_AFTER_MINUTES = 30
NUDGE_UNTIL_OFFSET = 12 * 60          # no reminder from 06:00 on
NUDGE_SOUND = "info.wav"
ACTIVE_WITHIN_SECONDS = 60            # "still using the computer"
BRIEFING_MAX_HOURS = 12               # older sleeps aren't news in the briefing
PLACEHOLDER = "sleep"                 # %sleep%: last night's sleep (core 2.7)

_bus = None
_active = False
_settings = dict(store.DEFAULT_SETTINGS)
_corrections = []
_last_nudge_night = ""
_recorder = store.Recorder()
_clock = None
_nights = analysis.Nights()
_last_save = 0.0
_panel = None
_dialog = None


# ------------------------------------------------------------
# Small wrappers (replaced in tests)
# ------------------------------------------------------------

def _now():
    return datetime.datetime.now()


def _play_sound(name):
    try:
        core.sounds.play_internal_sound(name)
    except Exception as e:
        logger.debug(f"[Sleep Pattern] Sound failed: {e}")


def _nickname():
    personal = getattr(core, "personal", None)
    if personal is None:
        return ""
    try:
        return personal.get_nickname() or ""
    except Exception:
        return ""


# ------------------------------------------------------------
# Saving
# ------------------------------------------------------------

def _load(key):
    data = core.api.load_data(key)
    return data if isinstance(data, dict) else {}


def _save_config():
    data = dict(_settings)
    data["corrections"] = list(_corrections)
    data["last_nudge_night"] = _last_nudge_night
    core.api.save_data(DATA_KEY, data)


def _save_activity(wall=None, final=False):
    global _last_save
    now = _now()
    _last_save = now.timestamp() if wall is None else wall
    if core.api.save_data(ACTIVITY_KEY, _recorder.to_data(now.date(), final=final)):
        _recorder.dirty = False
    _nights.forget_before(now.date() - datetime.timedelta(days=store.KEEP_DAYS + 7))


# ------------------------------------------------------------
# Sampling
# ------------------------------------------------------------

def _read_sample():
    return _clock.read() if _clock is not None else None


def sample_now():
    """Bring the record up to date. The hotkeys and the briefing call this
    first, so a gap Hariku hasn't seen yet (the computer just woke) counts."""
    if not (_active and _settings["enabled"]):
        return None
    sample = _read_sample()
    if sample is not None:
        _recorder.add_sample(sample)
    return sample


def _on_minute_tick(*_args, **_kwargs):
    # UI thread, once a minute: four API calls and a few bytes in memory.
    if not _active:
        return
    try:
        sample = _read_sample()
        if sample is None:
            return
        if _settings["enabled"]:
            _recorder.add_sample(sample)
            if sample["wall"] - _last_save >= store.SAVE_SECONDS or sample["wall"] < _last_save:
                _save_activity(sample["wall"])
        _maybe_nudge(sample)
    except Exception:
        logger.exception("[Sleep Pattern] Minute tick failed")


def _maybe_nudge(sample):
    """Once a night, from bedtime + 30 minutes until 06:00, if the computer is
    still in use."""
    global _last_nudge_night
    if not _settings["nudge"] or sample["idle"] >= ACTIVE_WITHIN_SECONDS:
        return
    now = datetime.datetime.fromtimestamp(sample["wall"])
    night = analysis.night_of(now)
    offset = analysis.offset_in_night(now, night)
    start = analysis.bedtime_offset(_settings["bedtime"]) + NUDGE_AFTER_MINUTES
    if not start <= offset < NUDGE_UNTIL_OFFSET or night.isoformat() == _last_nudge_night:
        return
    _last_nudge_night = night.isoformat()
    _save_config()
    if _settings["nudge_sound"]:
        _play_sound(NUDGE_SOUND)
    speak(text.nudge_text(now, _nickname()))


# ------------------------------------------------------------
# Nights
# ------------------------------------------------------------

def night_result(night, now=None):
    now = now or _now()
    return _nights.get(_recorder, night, _settings,
                       store.corrections_for(_corrections, night), now)


def last_night_result(now=None):
    now = now or _now()
    return analysis.last_night(lambda n: night_result(n, now), now)


def _week_diff(result, now):
    results = {}
    for i in range(1, 8):
        night = result["night"] - datetime.timedelta(days=i)
        results[night] = night_result(night, now)
    return analysis.compare_to_week(result, results)


def history_results(now=None):
    """Results for every night with any data, newest first. The running night
    is listed once its sleep is over (or once the user marked it)."""
    now = now or _now()
    current = analysis.night_of(now)
    results = []
    for i in range(store.KEEP_DAYS):
        night = current - datetime.timedelta(days=i)
        if not analysis.window_has_data(_recorder.day, night):
            continue
        result = night_result(night, now)
        if (night == current and result["status"] != "sleep"
                and not store.corrections_for(_corrections, night)):
            continue
        results.append(result)
    return results


def mark_not_sleep(night, now=None):
    """The user says the night's detected sleep wasn't sleep (a film, say)."""
    result = night_result(night, now)
    if result["status"] != "sleep":
        return False
    main = result["main"]
    _corrections.append({"night": night.isoformat(), "start": main["start"].timestamp(),
                         "end": main["end"].timestamp()})
    del _corrections[:-store.MAX_CORRECTIONS]
    _save_config()
    return True


def undo_mark(night):
    """Take back the last "This wasn't sleep" on `night`."""
    key = night.isoformat()
    for i in range(len(_corrections) - 1, -1, -1):
        if _corrections[i]["night"] == key:
            del _corrections[i]
            _save_config()
            return True
    return False


def clear_history():
    global _corrections
    _recorder.clear()
    _corrections = []
    _nights.clear()
    _save_config()
    _save_activity()


class HistoryActions:
    """What the history dialog may do."""

    @staticmethod
    def rows():
        rows = []
        for result in history_results():
            night = result["night"]
            if store.corrections_for(_corrections, night):
                mark = "undo"
            elif result["status"] == "sleep":
                mark = "mark"
            else:
                mark = None
            rows.append((night, text.row_text(result), mark))
        return rows

    @staticmethod
    def summary():
        now = _now()
        results = {r["night"]: r for r in history_results(now)}
        return text.summary_text(analysis.summary(results, last_night_result(now)["night"]))

    @staticmethod
    def details(night):
        now = _now()
        result = night_result(night, now)
        return text.details_text(result, _week_diff(result, now))

    mark = staticmethod(mark_not_sleep)
    undo = staticmethod(undo_mark)
    clear = staticmethod(clear_history)


# ------------------------------------------------------------
# Hotkey actions
# ------------------------------------------------------------

def speak_last_night():
    if not _settings["enabled"]:
        speak(_("tracking_off"), interrupt=True)
        return
    sample_now()
    now = _now()
    result = last_night_result(now)
    speak(text.last_night_text(result, _week_diff(result, now)), interrupt=True)


def show_history():
    global _dialog
    if _dialog:
        _dialog.Raise()     # already open
        return
    sample_now()
    parent = getattr(core.api, "main_window_instance", None)
    dlg = ui.HistoryDialog(parent, HistoryActions)
    _dialog = dlg
    try:
        dlg.ShowModal()
    finally:
        _dialog = None
        dlg.Destroy()


# ------------------------------------------------------------
# Events
# ------------------------------------------------------------

def _on_briefing_collect(lines):
    # Briefing contract: fast, stored data only, nothing without a detected sleep.
    if not (_active and _settings["enabled"]):
        return
    sample_now()
    now = _now()
    result = last_night_result(now)
    if result["status"] != "sleep":
        return
    if now - result["main"]["end"] > datetime.timedelta(hours=BRIEFING_MAX_HOURS):
        return
    lines.append(text.briefing_sentence(result))


def placeholder_text():
    """%sleep%: "about 6 hours 25 minutes" of last night's sleep, from what is
    already recorded (nothing is sampled), or "" when it isn't known."""
    if not (_active and _settings["enabled"]):
        return ""
    now = _now()
    result = last_night_result(now)
    if result["status"] != "sleep":
        return ""
    if now - result["main"]["end"] > datetime.timedelta(hours=BRIEFING_MAX_HOURS):
        return ""
    return text.placeholder_text(result)


_SUBSCRIPTIONS = (
    ("on_minute_tick", _on_minute_tick),
    ("on_briefing_collect", _on_briefing_collect),
)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def get_settings():
    return dict(_settings)


def apply_settings(new_settings):
    global _settings
    new_settings = store.normalize_settings(new_settings)
    was_enabled = _settings["enabled"]
    _settings = new_settings
    if was_enabled != new_settings["enabled"]:
        # Time with tracking off stays unknown: no gap is filled across it.
        _recorder.last = None
        if new_settings["enabled"]:
            sample_now()
        _save_activity()
    _save_config()


def _create_panel(parent):
    global _panel
    _panel = ui.SettingsPanel(parent, _settings, clear_history)
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        new_settings = _panel.get_settings()
    except RuntimeError:
        return  # panel already destroyed
    apply_settings(new_settings)


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def _unsubscribe(bus, event_name, handler):
    unsubscribe = getattr(bus, "unsubscribe", None)
    if callable(unsubscribe):
        unsubscribe(event_name, handler)
        return
    listeners = getattr(bus, "_listeners", {}).get(event_name)   # older cores
    if listeners and handler in listeners:
        listeners.remove(handler)


def register(bus):
    global _bus, _active, _settings, _corrections, _last_nudge_night
    global _recorder, _clock, _nights, _last_save, _panel, _dialog
    _bus = bus
    today = _now().date()
    config = _load(DATA_KEY)
    _settings = store.normalize_settings(config)
    _corrections = store.normalize_corrections(config.get("corrections"), today)
    nudged = config.get("last_nudge_night")
    _last_nudge_night = nudged if isinstance(nudged, str) else ""
    _recorder = store.Recorder.from_data(_load(ACTIVITY_KEY), today)
    _nights = analysis.Nights()
    _clock = system.WindowsClock()
    _panel = _dialog = None
    _active = True
    # Fill in the time since Hariku last ran (asleep, shut down, or closed).
    first = sample_now()
    _last_save = first["wall"] if first else _now().timestamp()

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # Z and Shift+Z ("Zzz") are free in the core, every shipped extension and
    # the saved key bindings (only the unshipped developer test package
    # extensions/dummy.hrk uses Z).
    core.hotkeys.register_action(EXT_NAME, "last_night", _("action_last_night"),
                                 ord("Z"), False, speak_last_night)
    core.hotkeys.register_action(EXT_NAME, "history", _("action_history"),
                                 ord("Z"), False, show_history, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    personal = getattr(core, "personal", None)
    if personal is not None and hasattr(personal, "register_placeholder"):
        personal.register_placeholder(PLACEHOLDER, placeholder_text, _("placeholder_desc"))
    logger.info("Sleep Pattern extension loaded.")


def teardown():
    global _active, _panel
    personal = getattr(core, "personal", None)
    if personal is not None and hasattr(personal, "unregister_placeholder"):
        personal.unregister_placeholder(PLACEHOLDER)
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _unsubscribe(_bus, event_name, handler)
            except Exception:
                pass
    if _active and _settings["enabled"]:
        try:
            sample_now()
            _save_activity(final=True)
        except Exception:
            logger.exception("[Sleep Pattern] Could not save the sleep record")
    _active = False
    _panel = None
    logger.info("Sleep Pattern extension unloaded.")
