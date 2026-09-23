# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Air Quality — Hariku V2 extension.

Speaks the US air quality index with its category, fine and coarse particles
(PM2.5, PM10), the UV index with its category and a short tip for the
category, and shows the next hours and days in a window. Data from Open-Meteo's
Air Quality API (CAMS; no account or API key). The city defaults to the Weather
extension's city; another one is chosen in Preferences, Air Quality, along with
an optional once-a-day announcement when the air turns unhealthy.

  air_quality_api.py  - requests, parsing, categories, settings, cache and the
                        alert rule (no wx)
  air_quality_text.py - spoken/displayed text in the user's language
  air_quality_ui.py   - Preferences page and the forecast window

The last answer is cached on disk and refreshed in the background at startup
and about every 30 minutes, and on demand when it is older than 10 minutes.
One request at a time, on a worker thread; results come back via wx.CallAfter.
Failed background attempts back off from 10 minutes to 2 hours.

Also adds a sentence to the Morning Briefing through "on_briefing_collect",
from the cache only (see briefing_core.py).
"""

import datetime
import logging
import threading
import time

import wx

import core.api
import core.hotkeys
import core.preferences
from core.speech import speak

import air_quality_api as api
import air_quality_text as text
import air_quality_ui
from air_quality_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Air Quality"     # fixed, so saved hotkeys survive a language change
DATA_KEY = "AirQuality"      # settings, see air_quality_api.normalize_settings()
CACHE_KEY = "AirQualityCache"
WEATHER_DATA_KEY = "Weather"

FRESH_SECONDS = 10 * 60      # answer from the cache without fetching
REFRESH_SECONDS = 30 * 60    # background refresh interval
RETRY_SECONDS = 10 * 60      # first gap after a failed background attempt
MAX_RETRY_SECONDS = 2 * 3600
STALE_MAX_AGE = 12 * 3600    # oldest cache still offered when offline
BRIEFING_MAX_AGE = 3 * 3600  # oldest cache used in the Morning Briefing
ALERT_MAX_AGE = 60 * 60      # oldest cache an alert may come from
ALERT_SOUND = "info.wav"

_bus = None
_active = False
_settings = api.normalize_settings(None)
_cache = None
_loading = False
_waiters = []        # callbacks run on the UI thread when the running fetch ends
_last_attempt = 0.0
_failures = 0        # failed fetches in a row
_panel = None


# ------------------------------------------------------------
# Small wrappers (replaced in tests)
# ------------------------------------------------------------

def _start_thread(target, *args):
    threading.Thread(target=target, args=args, daemon=True, name="air-quality-fetch").start()


def _play_sound(name):
    try:
        import core.sounds
        core.sounds.play_internal_sound(name)
    except Exception as e:
        logger.debug(f"[Air Quality] Sound failed: {e}")


def _today():
    return datetime.date.today().isoformat()


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

def weather_location():
    """The Weather extension's city, used when no air quality city is chosen."""
    data = core.api.load_data(WEATHER_DATA_KEY)
    return api.normalize_location(data.get("location")) if isinstance(data, dict) else None


def get_location():
    return _settings.get("location") or weather_location()


def get_settings():
    return dict(_settings)


def current_cache():
    """The cached answer for the current location, or None."""
    location = get_location()
    if location and _cache and api.cache_matches(_cache, location):
        return _cache
    return None


def _store_settings():
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(_settings)
    core.api.save_data(DATA_KEY, data)


def _save_settings(new_settings):
    global _settings
    merged = dict(_settings)
    merged.update(new_settings or {})
    _settings = api.normalize_settings(merged)
    _store_settings()
    if not get_location():
        return
    cache = current_cache()
    if cache is None or (_settings["alert"] and not api.is_fresh(cache, ALERT_MAX_AGE)):
        refresh()   # a new city, or the alert was switched on with old data
    else:
        _check_alert()


# ------------------------------------------------------------
# Background fetch
# ------------------------------------------------------------

def refresh(on_done=None):
    """Fetch in the background. on_done(error) runs on the UI thread afterwards
    (error is None on success). Returns False if nothing can be fetched
    because no location is set."""
    global _loading, _last_attempt
    location = get_location()
    if not _active or not location:
        return False
    if on_done is not None and on_done not in _waiters:
        _waiters.append(on_done)
    if _loading:
        return True
    _loading = True
    _last_attempt = time.time()
    _start_thread(_fetch_worker, dict(location))
    return True


def _fetch_worker(location):
    # Worker thread: network and the cache file only, never wx objects.
    cache, error = None, None
    try:
        forecast = api.fetch_air(location["latitude"], location["longitude"],
                                 location.get("timezone", ""))
        cache = api.make_cache(location, forecast)
        core.api.save_data(CACHE_KEY, cache)
    except api.AirError as e:
        error = e.kind
        logger.info(f"[Air Quality] Fetch failed: {e}")
    except Exception:
        error = "bad_response"
        logger.exception("[Air Quality] Fetch failed")
    wx.CallAfter(_on_fetched, cache, error)


def _on_fetched(cache, error):
    global _loading, _cache, _failures
    _loading = False
    if cache is not None:
        _cache = cache
    _failures = 0 if error is None else _failures + 1
    if not _active:
        del _waiters[:]
        return
    location = get_location()
    if cache is not None and location and not api.cache_matches(cache, location):
        refresh()  # the city changed while fetching; the waiters want the new one
        return
    waiters = _waiters[:]
    del _waiters[:]
    for callback in waiters:
        try:
            callback(error)
        except Exception:
            logger.exception("[Air Quality] Refresh callback failed")
    if error is None:
        _check_alert()


def _retry_gap():
    """Wait between background attempts: 10 minutes, doubling after each
    failure in a row, at most 2 hours."""
    return min(RETRY_SECONDS * 2 ** max(0, _failures - 1), MAX_RETRY_SECONDS)


# ------------------------------------------------------------
# The unhealthy-air alert
# ------------------------------------------------------------

def _check_alert():
    """Announce unhealthy air once a day, from recent data only."""
    location = get_location()
    cache = current_cache()
    if not _active or not location or not api.is_fresh(cache, ALERT_MAX_AGE):
        return
    today = _today()
    aqi = api.should_alert(_settings, cache["forecast"], today)
    if aqi is None:
        return
    _settings["alert_date"] = today
    _store_settings()
    _play_sound(ALERT_SOUND)
    speak(text.alert_text(location, aqi))


# ------------------------------------------------------------
# Actions
# ------------------------------------------------------------

def speak_air_quality():
    location = get_location()
    if not location:
        speak(_("no_location"), interrupt=True)
        return
    cache = current_cache()
    if cache and api.is_fresh(cache, FRESH_SECONDS):
        speak(text.current_report(location, cache["forecast"]), interrupt=True)
        return
    speak(_("fetching"), interrupt=True)
    refresh(_speak_after_refresh)


def _speak_after_refresh(error):
    location = get_location()
    cache = current_cache()
    if not location:
        speak(_("no_location"), interrupt=True)
    elif cache and (error is None or api.is_fresh(cache, FRESH_SECONDS)):
        speak(text.current_report(location, cache["forecast"]), interrupt=True)
    elif cache and api.is_fresh(cache, STALE_MAX_AGE):
        speak(" ".join([text.error_text(error),
                        _("stale_notice", time=text.time_text(cache["fetched_at"])),
                        text.current_report(location, cache["forecast"])]),
              interrupt=True)
    else:
        speak(text.error_text(error), interrupt=True)


def show_forecast():
    location = get_location()
    if not location:
        speak(_("no_location"), interrupt=True)
        return
    cache = current_cache()
    parent = getattr(core.api, "main_window_instance", None)
    dlg = air_quality_ui.AirForecastDialog(parent, location, current_cache, refresh,
                                           refresh_now=not api.is_fresh(cache, FRESH_SECONDS))
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------------
# Events
# ------------------------------------------------------------

def _on_app_startup(*_args, **_kwargs):
    if not get_location():
        return
    if api.is_fresh(current_cache(), FRESH_SECONDS):
        _check_alert()
    else:
        refresh()


def _on_minute_tick(*_args, **_kwargs):
    if not get_location() or _loading:
        return
    now = time.time()
    if now - _last_attempt < _retry_gap():
        return
    if api.is_fresh(current_cache(), REFRESH_SECONDS, now):
        return
    refresh()


def _on_briefing_collect(lines):
    # Briefing contract: fast, cache only, append nothing without data.
    location = get_location()
    cache = current_cache()
    if location and cache and api.is_fresh(cache, BRIEFING_MAX_AGE):
        sentence = text.briefing_sentence(location, cache["forecast"])
        if sentence:
            lines.append(sentence)


_SUBSCRIPTIONS = (
    ("on_app_startup", _on_app_startup),
    ("on_minute_tick", _on_minute_tick),
    ("on_briefing_collect", _on_briefing_collect),
)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    _panel = air_quality_ui.AirQualityPanel(parent, get_settings(), weather_location())
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        new_settings = _panel.get_settings()
    except RuntimeError:
        return  # panel already destroyed
    _save_settings(new_settings)
    _panel.set_location(_settings["location"], weather_location())


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register(bus):
    global _bus, _active, _settings, _cache, _loading, _last_attempt, _failures, _panel
    _bus = bus
    _active = True
    _loading = False
    _last_attempt = 0.0
    _failures = 0
    _panel = None
    del _waiters[:]
    _settings = api.normalize_settings(core.api.load_data(DATA_KEY))
    _cache = api.normalize_cache(core.api.load_data(CACHE_KEY))

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # U ("udara", air) and Shift+U: free in the core and in every bundled and
    # store extension (Window Teleporter only uses U with Ctrl or Alt).
    core.hotkeys.register_action(EXT_NAME, "speak_air", _("action_speak"),
                                 ord("U"), False, speak_air_quality)
    core.hotkeys.register_action(EXT_NAME, "show_forecast", _("action_forecast"),
                                 ord("U"), False, show_forecast, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("Air Quality extension loaded.")


def teardown():
    global _active, _panel
    _active = False
    _panel = None
    del _waiters[:]
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _bus.unsubscribe(event_name, handler)
            except Exception:
                pass
    logger.info("Air Quality extension unloaded.")
