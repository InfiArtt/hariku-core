# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Weather — Hariku V2 extension.

Speaks the current weather and shows a 7-day forecast for one city, using
Open-Meteo (https://open-meteo.com; no account or API key). The city and units
are chosen in Preferences, Weather.

  weather_api.py  - requests, parsing, cache and unit helpers (no wx)
  weather_text.py - spoken/displayed text in the user's language
  weather_ui.py   - Preferences page and forecast dialog

The last forecast is cached on disk and refreshed in the background at startup
and about every 30 minutes, and on demand when it is older than 10 minutes. All
network calls run on worker threads; results come back via wx.CallAfter.

Also adds a one-sentence summary to the Morning Briefing through the
"on_briefing_collect" event, and tomorrow's forecast to its evening summary
through "on_evening_collect", both from the cache only (see briefing_core.py).
"""

import logging
import threading
import time

import wx

import core.api
import core.hotkeys
import core.preferences
from core.speech import speak

import weather_api
import weather_text
import weather_ui
from weather_text import _

logger = logging.getLogger(__name__)

DATA_KEY = "Weather"         # {"location": {...} or None, "units": "metric" | "imperial"}
CACHE_KEY = "WeatherCache"   # last forecast, see weather_api.make_cache()

FRESH_SECONDS = 10 * 60      # answer from the cache without fetching
REFRESH_SECONDS = 30 * 60    # background refresh interval
RETRY_SECONDS = 10 * 60      # minimum gap between background attempts
STALE_MAX_AGE = 12 * 3600    # oldest cache still offered when offline
BRIEFING_MAX_AGE = 3 * 3600  # oldest cache used in the Morning Briefing

_bus = None
_active = False
_settings = {"location": None, "units": "metric"}
_cache = None
_loading = False
_waiters = []        # callbacks run on the UI thread when the running fetch ends
_last_attempt = 0.0
_panel = None


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

def get_location():
    return _settings.get("location")


def get_units():
    return _settings.get("units", "metric")


def current_cache():
    """The cached forecast for the configured location, or None."""
    location = get_location()
    if location and _cache and weather_api.cache_matches(_cache, location):
        return _cache
    return None


def _save_settings(new_settings):
    global _settings
    new_settings = weather_api.normalize_settings(new_settings)
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(new_settings)
    core.api.save_data(DATA_KEY, data)
    _settings = new_settings
    location = new_settings["location"]
    if location and not weather_api.cache_matches(_cache, location):
        refresh()


# ------------------------------------------------------------
# Background fetch
# ------------------------------------------------------------

def _start_thread(target, *args):
    threading.Thread(target=target, args=args, daemon=True, name="weather-fetch").start()


def refresh(on_done=None):
    """Fetch the forecast in the background. on_done(error) runs on the UI
    thread afterwards (error is None on success). Returns False if nothing can
    be fetched because no location is set."""
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
        forecast = weather_api.fetch_forecast(location["latitude"], location["longitude"],
                                              location.get("timezone", ""))
        cache = weather_api.make_cache(location, forecast)
        core.api.save_data(CACHE_KEY, cache)
    except weather_api.WeatherError as e:
        error = e.kind
        logger.info(f"[Weather] Fetch failed: {e}")
    except Exception:
        error = "bad_response"
        logger.exception("[Weather] Fetch failed")
    wx.CallAfter(_on_fetched, cache, error)


def _on_fetched(cache, error):
    global _loading, _cache
    _loading = False
    if cache is not None:
        _cache = cache
    if not _active:
        del _waiters[:]
        return
    location = get_location()
    if cache is not None and location and not weather_api.cache_matches(cache, location):
        refresh()  # the city changed while fetching; the waiters want the new one
        return
    waiters = _waiters[:]
    del _waiters[:]
    for callback in waiters:
        try:
            callback(error)
        except Exception:
            logger.exception("[Weather] Refresh callback failed")


# ------------------------------------------------------------
# Actions
# ------------------------------------------------------------

def speak_current_weather():
    location = get_location()
    if not location:
        speak(_("no_location"), interrupt=True)
        return
    cache = current_cache()
    if cache and weather_api.is_fresh(cache, FRESH_SECONDS):
        speak(weather_text.current_report(location, cache["forecast"], get_units()), interrupt=True)
        return
    speak(_("fetching"), interrupt=True)
    refresh(_speak_after_refresh)


def _speak_after_refresh(error):
    location = get_location()
    cache = current_cache()
    if not location:
        speak(_("no_location"), interrupt=True)
    elif cache and (error is None or weather_api.is_fresh(cache, FRESH_SECONDS)):
        speak(weather_text.current_report(location, cache["forecast"], get_units()), interrupt=True)
    elif cache and weather_api.is_fresh(cache, STALE_MAX_AGE):
        speak(" ".join([weather_text.error_text(error),
                        _("stale_notice", time=weather_text.time_text(cache["fetched_at"])),
                        weather_text.current_report(location, cache["forecast"], get_units())]),
              interrupt=True)
    else:
        speak(weather_text.error_text(error), interrupt=True)


def show_forecast():
    location = get_location()
    if not location:
        speak(_("no_location"), interrupt=True)
        return
    cache = current_cache()
    parent = getattr(core.api, "main_window_instance", None)
    dlg = weather_ui.ForecastDialog(parent, location, get_units(), current_cache, refresh,
                                    refresh_now=not weather_api.is_fresh(cache, FRESH_SECONDS))
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------------
# Events
# ------------------------------------------------------------

def _on_app_startup(*_args):
    if get_location() and not weather_api.is_fresh(current_cache(), FRESH_SECONDS):
        refresh()


def _on_minute_tick(*_args):
    if not get_location() or _loading:
        return
    now = time.time()
    if now - _last_attempt < RETRY_SECONDS:
        return
    if weather_api.is_fresh(current_cache(), REFRESH_SECONDS, now):
        return
    refresh()


def _on_briefing_collect(lines):
    # Briefing contract: fast, cache only, append nothing without data.
    location = get_location()
    cache = current_cache()
    if location and cache and weather_api.is_fresh(cache, BRIEFING_MAX_AGE):
        lines.append(weather_text.briefing_sentence(location, cache["forecast"], get_units()))


def _on_evening_collect(lines):
    # Evening summary contract (the same as the briefing's): tomorrow's weather.
    location = get_location()
    cache = current_cache()
    if location and cache and weather_api.is_fresh(cache, BRIEFING_MAX_AGE):
        sentence = weather_text.evening_sentence(cache["forecast"], get_units())
        if sentence:
            lines.append(sentence)


_SUBSCRIPTIONS = (
    ("on_app_startup", _on_app_startup),
    ("on_minute_tick", _on_minute_tick),
    ("on_briefing_collect", _on_briefing_collect),
    ("on_evening_collect", _on_evening_collect),
)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    _panel = weather_ui.WeatherPanel(parent, _settings)
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        new_settings = _panel.get_settings()
    except RuntimeError:
        return  # panel already destroyed
    _save_settings(new_settings)
    _panel.set_location(get_location())


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def _unsubscribe(bus, event_name, handler):
    unsubscribe = getattr(bus, "unsubscribe", None)
    if callable(unsubscribe):
        unsubscribe(event_name, handler)
        return
    listeners = getattr(bus, "_listeners", {}).get(event_name)
    if listeners and handler in listeners:
        listeners.remove(handler)


def register(bus):
    global _bus, _active, _settings, _cache, _loading, _last_attempt
    _bus = bus
    _active = True
    _loading = False
    _last_attempt = 0.0
    _settings = weather_api.normalize_settings(core.api.load_data(DATA_KEY))
    _cache = weather_api.normalize_cache(core.api.load_data(CACHE_KEY))

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # Shift+W: next to World Clock's W, and free in the core and bundled extensions.
    core.hotkeys.register_action("Weather", "speak_current_weather", _("action_speak"),
                                 ord("W"), False, speak_current_weather, default_shift=True)
    core.hotkeys.register_action("Weather", "show_forecast", _("action_forecast"),
                                 None, False, show_forecast)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("Weather extension loaded.")


def teardown():
    global _active
    _active = False
    del _waiters[:]
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _unsubscribe(_bus, event_name, handler)
            except Exception:
                pass
    logger.info("Weather extension unloaded.")
