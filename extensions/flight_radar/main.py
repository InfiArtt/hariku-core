# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Flight Radar — Hariku V2 extension.

Hear the aircraft flying near your city: the nearest few on a hotkey, a list of
everything in range, and optional announcements when one passes overhead.
Aircraft positions come from adsb.fi (adsb.lol when adsb.fi fails), routes from
adsbdb.com; none need an account or key. The city, radius and units are chosen
in Preferences, Flight Radar.

  flight_radar_api.py    - aircraft requests, parsing, settings, units, pacing
  flight_radar_routes.py - best-effort routes (memory only, plausibility check)
  flight_radar_names.py  - airline and aircraft type names
  flight_radar_text.py   - spoken/displayed text in the user's language
  flight_radar_ui.py     - Preferences page and the aircraft list dialog

All network calls run on worker threads; results come back via wx.CallAfter.
At most one aircraft request is in flight, requests are at least 5 seconds
apart, answers are reused for 15 seconds, and failures back off.
"""

import logging
import threading
import time

import wx

import core.api
import core.hotkeys
import core.preferences
from core.speech import speak

import flight_radar_api as api
import flight_radar_routes as routes
import flight_radar_text as text
import flight_radar_ui
from flight_radar_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Flight Radar"   # fixed, so saved hotkeys survive a language change
DATA_KEY = "FlightRadar"    # settings only; aircraft and routes are never saved
WEATHER_DATA_KEY = "Weather"

CACHE_SECONDS = 15          # answer from the last result without fetching
STALE_MAX_AGE = 120         # oldest result still offered after a failure
POLL_SECONDS = 30           # overhead alerts
FIRST_POLL_SECONDS = 10
ALERT_COOLDOWN = 600        # an aircraft is announced once per 10 minutes
ALERT_SOUND = "info.wav"
ROUTE_WAIT_SECONDS = 3.0    # longest wait for route lookups before speaking

_bus = None
_active = False
_settings = api.normalize_settings(None)
_cache = None
_loading = False
_waiters = []           # callbacks run on the UI thread when the running fetch ends
_gate = api.RateGate()
_tracker = api.AlertTracker(ALERT_COOLDOWN)
_routes = routes.RouteLookup()
_fetch_timer = None     # a fetch waiting for the rate limit
_poll_timer = None
_poll_running = False
_panel = None


# ------------------------------------------------------------
# Small wrappers (replaced in tests)
# ------------------------------------------------------------

def _now():
    return time.monotonic()


def _start_thread(target, *args):
    threading.Thread(target=target, args=args, daemon=True, name="flight-radar").start()


def _call_later(seconds, callback):
    return wx.CallLater(max(1, int(seconds * 1000)), callback)


def _cancel(timer):
    if timer is not None:
        try:
            timer.Stop()
        except Exception:
            pass


def _play_alert_sound():
    try:
        import core.sounds
        core.sounds.play_internal_sound(ALERT_SOUND)
    except Exception as e:
        logger.debug(f"[Flight Radar] Alert sound failed: {e}")


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

def weather_location():
    """The Weather extension's city, offered when no radar city is set."""
    data = core.api.load_data(WEATHER_DATA_KEY)
    return api.normalize_location(data.get("location")) if isinstance(data, dict) else None


def get_location():
    return _settings.get("location") or weather_location()


def get_settings():
    return dict(_settings)


def query_radius_nm():
    return api.query_radius_nm(max(_settings["radius_km"], _settings["alert_km"]))


def current_cache():
    """The last result for the current city and radius, or None."""
    location = get_location()
    if location and _cache and api.cache_matches(_cache, location, query_radius_nm()):
        return _cache
    return None


def visible_aircraft():
    cache = current_cache()
    if not cache:
        return []
    return api.visible_aircraft(cache["aircraft"], _settings["radius_km"],
                                _settings["include_ground"])


def list_data():
    """(visible aircraft, cache) for the list dialog."""
    return visible_aircraft(), current_cache()


def _save_settings(new_settings):
    global _settings
    new_settings = api.normalize_settings(new_settings)
    old_location = get_location()
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(new_settings)
    core.api.save_data(DATA_KEY, data)
    _settings = new_settings
    if get_location() != old_location:
        _tracker.reset()
    _update_polling()


# ------------------------------------------------------------
# Fetching aircraft
# ------------------------------------------------------------

def refresh(on_done=None):
    """Fetch aircraft now, or as soon as the rate limit allows. on_done(error)
    runs on the UI thread afterwards (error is None on success). Returns False
    if nothing can be fetched because no location is set."""
    global _fetch_timer
    if not _active or not get_location():
        return False
    if on_done is not None and on_done not in _waiters:
        _waiters.append(on_done)
    if _loading or _fetch_timer is not None:
        return True
    now = _now()
    if _gate.cooldown_left(now) > 0:
        wx.CallAfter(_deliver, "rate_limited")
        return True
    wait = _gate.wait_time(now)
    if wait > 0:
        _fetch_timer = _call_later(wait, _start_fetch)
        return True
    _start_fetch()
    return True


def _start_fetch():
    global _loading, _fetch_timer
    _fetch_timer = None
    location = get_location()
    if not _active:
        return
    if not location:
        _deliver(None)
        return
    _loading = True
    _gate.started(_now())
    _start_thread(_fetch_worker, dict(location), query_radius_nm())


def _fetch_worker(location, radius_nm):
    # Worker thread: network only, never wx objects.
    aircraft, source, error = [], "", None
    try:
        aircraft, source = api.fetch_aircraft(location["latitude"], location["longitude"], radius_nm)
    except api.FlightError as e:
        error = e.kind
    except Exception:
        error = "bad_response"
        logger.exception("[Flight Radar] Fetch failed")
    wx.CallAfter(_on_fetched, location, radius_nm, aircraft, source, error, time.time())


def _on_fetched(location, radius_nm, aircraft, source, error, wall):
    global _loading, _cache
    _loading = False
    _gate.finished(_now(), error)
    if error is None:
        _cache = api.make_cache(location, radius_nm, aircraft, source, _now(), wall)
    if not _active:
        del _waiters[:]
        return
    if error is None and not current_cache() and get_location():
        refresh()  # the city or radius changed while fetching
        return
    _deliver(error)


def _deliver(error):
    waiters = _waiters[:]
    del _waiters[:]
    for callback in waiters:
        try:
            callback(error)
        except Exception:
            logger.exception("[Flight Radar] Refresh callback failed")


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

def leg_for(plane):
    """The plausible route leg of an aircraft from the route cache, or None.
    Never looks anything up."""
    callsign = routes.route_callsign(plane)
    if not callsign:
        return None
    known, route = _routes.get(callsign)
    return routes.plausible_leg(route, plane.get("lat"), plane.get("lon")) if known else None


def with_routes(aircraft, callback):
    """Look up the routes of `aircraft` (those not cached yet), then run
    callback() on the UI thread, at most ROUTE_WAIT_SECONDS later."""
    callsigns = []
    for plane in aircraft:
        callsign = routes.route_callsign(plane)
        if callsign and callsign not in callsigns and _routes.needs_lookup(callsign):
            callsigns.append(callsign)
    if not callsigns:
        callback()
        return
    state = {"done": False, "timer": None}

    def finish():
        if state["done"]:
            return
        state["done"] = True
        _cancel(state["timer"])
        if _active:
            callback()

    state["timer"] = _call_later(ROUTE_WAIT_SECONDS, finish)
    _start_thread(_route_worker, callsigns, finish)


def _route_worker(callsigns, finish):
    # Worker thread: adsbdb only, paced by RouteLookup.
    try:
        _routes.lookup_many(callsigns)
    except Exception:
        logger.exception("[Flight Radar] Route lookup failed")
    wx.CallAfter(finish)


# ------------------------------------------------------------
# Actions
# ------------------------------------------------------------

def speak_nearby():
    """What's flying nearby? The nearest aircraft, spoken."""
    if not get_location():
        speak(_("no_location"), interrupt=True)
        return
    if api.is_fresh(current_cache(), CACHE_SECONDS, _now()):
        _speak_report()
        return
    speak(_("checking"), interrupt=True)
    refresh(_speak_after_refresh)


def _speak_after_refresh(error):
    if not get_location():
        speak(_("no_location"), interrupt=True)
        return
    cache = current_cache()
    if cache and error is None:
        _speak_report()
    elif cache and api.is_fresh(cache, STALE_MAX_AGE, _now()):
        _speak_report(" ".join([text.error_text(error),
                                _("stale_notice", time=text.time_text(cache["fetched_wall"]))]))
    else:
        speak(text.error_text(error), interrupt=True)


def _speak_report(prefix=""):
    aircraft = visible_aircraft()
    settings = get_settings()

    def say():
        report = text.nearby_report(aircraft, settings["radius_km"], settings["units"],
                                    settings["include_ground"], leg_for)
        speak(f"{prefix} {report}".strip(), interrupt=True)

    with_routes(aircraft[:text.NEARBY_COUNT], say)


def show_list():
    """The list of every aircraft in range."""
    location = get_location()
    if not location:
        speak(_("no_location"), interrupt=True)
        return
    parent = getattr(core.api, "main_window_instance", None)
    dlg = flight_radar_ui.RadarListDialog(
        parent, api.place_label(location), get_settings(), list_data, refresh,
        leg_for, with_routes,
        refresh_now=not api.is_fresh(current_cache(), CACHE_SECONDS, _now()))
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------------
# Overhead alerts
# ------------------------------------------------------------

def _polling_wanted():
    return _active and _settings["alerts"] and get_location() is not None


def _update_polling(first_delay=FIRST_POLL_SECONDS):
    """Start polling when alerts are on, stop it when they are off."""
    global _poll_timer
    if not _polling_wanted():
        _cancel(_poll_timer)
        _poll_timer = None
        return
    if _poll_timer is None and not _poll_running:
        _schedule_poll(first_delay)


def _schedule_poll(delay):
    global _poll_timer
    _cancel(_poll_timer)
    _poll_timer = _call_later(delay, _poll)


def _poll():
    global _poll_timer, _poll_running
    _poll_timer = None
    if not _polling_wanted():
        return
    if api.is_fresh(current_cache(), CACHE_SECONDS, _now()):
        _check_alerts()
        _schedule_poll(POLL_SECONDS)
        return
    _poll_running = True
    if not refresh(_after_poll):
        _poll_running = False


def _after_poll(error):
    global _poll_running
    _poll_running = False
    if not _polling_wanted():
        return
    if error is None:
        _check_alerts()
    _schedule_poll(POLL_SECONDS if error is None else _gate.backoff(POLL_SECONDS))


def _check_alerts():
    cache = current_cache()
    if not cache:
        return
    new = _tracker.check(cache["aircraft"], _settings["alert_km"], _now())
    if not new:
        return
    units = _settings["units"]

    def announce():
        if not _settings["alerts"]:
            return
        _play_alert_sound()
        speak(text.alert_text(new, units, leg_for))

    with_routes(new, announce)


# ------------------------------------------------------------
# Events
# ------------------------------------------------------------

def _on_app_startup(*_args, **_kwargs):
    _update_polling()


def _on_network_changed(online=True, *_args, **_kwargs):
    if not online:
        return
    _gate.reset()
    if _poll_timer is not None:
        _schedule_poll(FIRST_POLL_SECONDS)  # back online: don't sit out the back-off


_SUBSCRIPTIONS = (
    ("on_app_startup", _on_app_startup),
    ("on_network_changed", _on_network_changed),
)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    _panel = flight_radar_ui.FlightRadarPanel(parent, get_settings(), weather_location())
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
    global _bus, _active, _settings, _cache, _loading, _gate, _tracker, _routes
    global _fetch_timer, _poll_timer, _poll_running
    _bus = bus
    _active = True
    _cache = None
    _loading = False
    _fetch_timer = _poll_timer = None
    _poll_running = False
    _gate = api.RateGate()
    _tracker = api.AlertTracker(ALERT_COOLDOWN)
    _routes = routes.RouteLookup()
    _settings = api.normalize_settings(core.api.load_data(DATA_KEY))

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # P ("pesawat" / plane) and Shift+P: free in the core (which uses Ctrl+P) and
    # in every bundled and store extension (Project System uses Ctrl+Shift+P).
    core.hotkeys.register_action(EXT_NAME, "speak_nearby", _("action_nearby"),
                                 ord("P"), False, speak_nearby)
    core.hotkeys.register_action(EXT_NAME, "show_list", _("action_list"),
                                 ord("P"), False, show_list, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    _update_polling()
    logger.info("Flight Radar extension loaded.")


def teardown():
    global _active, _fetch_timer, _poll_timer, _panel
    _active = False
    del _waiters[:]
    _cancel(_fetch_timer)
    _cancel(_poll_timer)
    _fetch_timer = _poll_timer = None
    _panel = None
    _routes.clear()
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _bus.unsubscribe(event_name, handler)
            except Exception:
                pass
    logger.info("Flight Radar extension unloaded.")
