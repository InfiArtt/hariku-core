# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Space (Antariksa) — Hariku V2 extension.

  * Where is the ISS? Its distance and direction from the user's city, the
    country below it, altitude, speed, and whether it is in sunlight
    (wheretheiss.at).
  * Upcoming rocket launches, with a spoken reminder before a chosen launch
    (The Space Devs Launch Library 2).
  * Sun and Moon: sunrise, sunset, day length, the Moon's phase and the next
    new and full moon, calculated offline.
  * A sentence for the Morning Briefing ("on_briefing_collect"), from
    calculations and the launch cache only.

  space_api.py       - requests, parsing, settings, cache, pacing, reminders (no wx)
  space_astro.py     - sun, moon and ISS geometry (pure maths)
  space_countries.py - country names in English and Indonesian
  space_text.py      - spoken/displayed text in the user's language
  space_ui.py        - Preferences page and the launches list

The place is the main place from Preferences, Places (core 2.8) unless another
place, or a city of its own, is chosen in Preferences, Space. It never leaves
the computer; a place without a time zone (an address or pasted coordinates)
uses the computer's own. All network calls run on worker threads; results
come back via wx.CallAfter. At most one request per service is in flight; the
ISS is asked at most every 10 seconds, launches at most once an hour
(the Refresh button: when the list is older than 15 minutes), and failures
back off.
"""

import datetime
import logging
import math
import threading
import time

import wx

import core.api
import core.hotkeys
import core.places
import core.preferences
from core.speech import speak

import space_api as api
import space_text as text
import space_ui
from space_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Space"               # fixed, so saved hotkeys survive a language change
DATA_KEY = "Space"               # see space_api.normalize_settings()
LAUNCH_KEY = "SpaceLaunches"     # the launch cache and its back-off state
REMINDER_KEY = "SpaceReminders"  # {"reminders": [...]}
BRIEFING_LAUNCH_MAX_AGE = 24 * 3600   # older launch lists are not used in the briefing
REMINDER_SOUND = "info.wav"

_bus = None
_active = False
_settings = api.normalize_settings(None)
_panel = None

_iss = None              # {"at": monotonic time, "position": {...}, "country": code/""/None}
_iss_loading = False
_iss_waiters = []
_iss_error = None        # the last request's error kind
_iss_gate = api.RequestGate()

_launch_state = api.empty_launch_state()
_launch_index = {}       # launch id -> launch, from the cache
_launch_loading = False
_launch_waiters = []
_reminders = []


# ------------------------------------------------------------
# Small wrappers (replaced in tests)
# ------------------------------------------------------------

def _now():
    return time.monotonic()


def _wall():
    return time.time()


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _start_thread(target, *args):
    threading.Thread(target=target, args=args, daemon=True, name="space-fetch").start()


def _sleep(seconds):
    time.sleep(seconds)


def _play_sound(name):
    try:
        import core.sounds
        core.sounds.play_internal_sound(name)
    except Exception as e:
        logger.debug(f"[Space] Sound failed: {e}")


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

def get_location():
    """The place in use: the chosen place from Preferences, Places (the main
    place by default), or the city of its own; None without one."""
    return core.places.location_for(_settings.get("place"), _settings.get("location"))


def get_settings():
    return dict(_settings)


def _store_settings():
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(_settings)
    core.api.save_data(DATA_KEY, data)


def _save_settings(new_settings):
    global _settings
    _settings = api.normalize_settings(dict(_settings, **new_settings))
    _store_settings()


# ------------------------------------------------------------
# Where is the ISS?
# ------------------------------------------------------------

def speak_iss():
    now = _now()
    if _iss and 0 <= now - _iss["at"] < api.ISS_MIN_GAP:
        _speak_iss_report()
        return
    if _iss_loading:
        _fetch_iss(_speak_iss_after)
        return
    wait = _iss_gate.wait_time(now)
    if wait > 0 and _iss_error is None and _iss:
        _speak_iss_report()
        return
    if wait > 0:
        # The last request failed moments ago: say so rather than ask again.
        speak(" ".join([text.iss_error_text(_iss_error),
                        _("iss_wait", seconds=text.number(int(math.ceil(wait))))]), interrupt=True)
        return
    speak(_("iss_checking"), interrupt=True)
    _fetch_iss(_speak_iss_after)


def _fetch_iss(on_done):
    global _iss_loading
    if on_done not in _iss_waiters:
        _iss_waiters.append(on_done)
    if _iss_loading or not _active:
        return
    _iss_loading = True
    _iss_gate.started(_now())
    _start_thread(_iss_worker)


def _iss_worker():
    # Worker thread: network only, never wx objects. The country lookup sends
    # the ISS's position, never the user's.
    position, country, error = None, None, None
    try:
        position = api.fetch_iss()
    except api.SpaceError as e:
        error = e.kind
        logger.info(f"[Space] ISS position failed: {e}")
    except Exception:
        error = "bad_response"
        logger.exception("[Space] ISS position failed")
    if position is not None:
        _sleep(api.ISS_COUNTRY_GAP)   # wheretheiss.at: about one request a second
        try:
            country = api.fetch_country(position["latitude"], position["longitude"])
        except Exception as e:
            logger.info(f"[Space] Country lookup failed: {e}")
    wx.CallAfter(_on_iss_fetched, position, country, error)


def _on_iss_fetched(position, country, error):
    global _iss_loading, _iss, _iss_error
    _iss_loading = False
    _iss_gate.finished(error)
    _iss_error = error
    if position is not None:
        _iss = {"at": _now(), "position": position, "country": country}
    waiters = _iss_waiters[:]
    del _iss_waiters[:]
    if not _active:
        return
    for callback in waiters:
        try:
            callback(error)
        except Exception:
            logger.exception("[Space] ISS callback failed")


def _speak_iss_after(error):
    if error or not _iss:
        speak(text.iss_error_text(error), interrupt=True)
        return
    _speak_iss_report()


def _speak_iss_report():
    speak(text.iss_report(_iss["position"], _iss["country"], get_location(), _utcnow()),
          interrupt=True)


# ------------------------------------------------------------
# Rocket launches
# ------------------------------------------------------------

def _index_launches():
    global _launch_index
    _launch_index = {launch["id"]: launch for launch in _launch_state["launches"]}


def launch_data():
    """(launches to list, launch state) for the dialog."""
    return api.upcoming(_launch_state["launches"], _utcnow()), dict(_launch_state)


def refresh_launches(on_done=None, explicit=False):
    """Fetch the launch list in the background when the pacing allows.
    Returns (status, message): "started" (on_done(error) runs on the UI thread
    later), "fresh" or "wait" with the text to speak, or "inactive"."""
    global _launch_loading
    if not _active:
        return "inactive", ""
    if _launch_loading:
        if on_done is not None and on_done not in _launch_waiters:
            _launch_waiters.append(on_done)
        return "started", ""
    min_age = api.LAUNCH_MANUAL_AGE if explicit else api.LAUNCH_AUTO_AGE
    decision = api.launch_fetch_decision(_launch_state, _wall(), min_age)
    if decision == "fresh":
        return "fresh", _("launches_fresh", time=text.time_of(_launch_state["fetched_at"]))
    if decision == "wait":
        return "wait", _("launches_wait", time=text.time_of(_launch_state["retry_after"]))
    if on_done is not None:
        _launch_waiters.append(on_done)
    _launch_loading = True
    _start_thread(_launch_worker)
    return "started", ""


def _launch_worker():
    # Worker thread: network only.
    launches, error, retry_after = None, None, None
    try:
        launches = api.fetch_launches()
    except api.SpaceError as e:
        error, retry_after = e.kind, e.retry_after
        logger.info(f"[Space] Launch list failed: {e}")
    except Exception:
        error = "bad_response"
        logger.exception("[Space] Launch list failed")
    wx.CallAfter(_on_launches_fetched, launches, error, retry_after)


def _on_launches_fetched(launches, error, retry_after):
    global _launch_loading, _launch_state
    _launch_loading = False
    waiters = _launch_waiters[:]
    del _launch_waiters[:]
    if not _active:
        return
    _launch_state = api.after_launch_fetch(_launch_state, _wall(), launches, error, retry_after)
    _index_launches()
    core.api.save_data(LAUNCH_KEY, _launch_state)
    for callback in waiters:
        try:
            callback(error)
        except Exception:
            logger.exception("[Space] Launch callback failed")


def show_launches():
    location = get_location()
    tz = api.zone_for(location)
    if location and tz is not None:
        label = _("launches_label", place=location["name"])
    else:
        label = _("launches_label_local")
    refresh_now = _launch_loading or api.launch_fetch_decision(
        _launch_state, _wall(), api.LAUNCH_AUTO_AGE) == "fetch"
    parent = getattr(core.api, "main_window_instance", None)
    dlg = space_ui.LaunchesDialog(parent, label, launch_data, refresh_launches, has_reminder,
                                  toggle_reminder, lambda: _settings["lead_minutes"], tz, _utcnow,
                                  refresh_now=refresh_now)
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------------
# Launch reminders
# ------------------------------------------------------------

def has_reminder(launch_id):
    return any(r["id"] == launch_id for r in _reminders)


def _set_reminders(reminders):
    global _reminders
    _reminders = reminders
    core.api.save_data(REMINDER_KEY, {"reminders": reminders})


def toggle_reminder(launch):
    """Set or cancel the reminder for `launch`; returns the text to speak."""
    name = api.launch_name(launch)
    if has_reminder(launch["id"]):
        _set_reminders([r for r in _reminders if r["id"] != launch["id"]])
        return _("reminder_cancelled", name=name)
    if not api.is_exact(launch):
        return _("reminder_not_exact", name=name)
    if api.launch_time(launch) <= _utcnow():
        return _("reminder_past", name=name)
    if len(_reminders) >= api.MAX_REMINDERS:
        return _("reminder_full", count=api.MAX_REMINDERS)
    _set_reminders(_reminders + [api.new_reminder(launch)])
    return _("reminder_set", lead=text.duration_text(_settings["lead_minutes"]), name=name)


def _on_minute_tick(*_args, **_kwargs):
    # Runs every minute on the UI thread: a few comparisons, no network.
    if not _reminders:
        return
    now = _utcnow()
    due, kept = api.check_reminders(_reminders, _launch_index, now, _settings["lead_minutes"])
    if kept != _reminders:
        _set_reminders(kept)
    if due:
        tz = api.zone_for(get_location())
        _play_sound(REMINDER_SOUND)
        speak(" ".join(text.reminder_due_text(reminder["name"], launch, net, tz, now)
                       for reminder, launch, net in due))
    # Launches move: keep the reminded ones' times current (at most hourly).
    if kept and not _launch_loading and api.launch_fetch_decision(
            _launch_state, _wall(), api.LAUNCH_AUTO_AGE) == "fetch":
        refresh_launches()


# ------------------------------------------------------------
# Sun and Moon
# ------------------------------------------------------------

def speak_sun_moon():
    location = get_location()
    speak(text.sun_moon_report(location, api.zone_for(location), _utcnow()), interrupt=True)


def launches_today(tz, now):
    """Cached launches with an exact time later today (location time)."""
    age = api.launch_age(_launch_state, _wall())
    if age is None or age > BRIEFING_LAUNCH_MAX_AGE:
        return []
    today = text.local(now, tz).date()
    return [launch for launch in api.upcoming(_launch_state["launches"], now, limit=50)
            if api.is_exact(launch) and api.launch_time(launch) > now
            and text.local(api.launch_time(launch), tz).date() == today]


def _on_briefing_collect(lines):
    # Briefing contract: fast, no network. Sun and Moon are calculated; the
    # launch comes from the cache.
    location = get_location()
    tz = api.zone_for(location)
    now = _utcnow()
    lines.append(text.briefing_text(location, tz, now, launches_today(tz, now)))


# ------------------------------------------------------------
# Events
# ------------------------------------------------------------

def _on_app_startup(*_args, **_kwargs):
    if _reminders and api.launch_fetch_decision(_launch_state, _wall(),
                                                api.LAUNCH_AUTO_AGE) == "fetch":
        refresh_launches()


def _on_network_changed(online=True, *_args, **_kwargs):
    if online:
        _iss_gate.reset()


def _on_places_changed(*_args, **_kwargs):
    """The places changed (Preferences, Places): show them on the settings
    page. Everything else reads the place when it is needed."""
    if _panel:
        try:
            _panel.refresh_places()
        except RuntimeError:
            pass  # panel already destroyed


_SUBSCRIPTIONS = (
    ("on_app_startup", _on_app_startup),
    ("on_minute_tick", _on_minute_tick),
    ("on_briefing_collect", _on_briefing_collect),
    ("on_network_changed", _on_network_changed),
    ("on_places_changed", _on_places_changed),
)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    _panel = space_ui.SpacePanel(parent, get_settings())
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        new_settings = _panel.get_settings()
    except RuntimeError:
        return  # panel already destroyed
    _save_settings(new_settings)
    _panel.set_location(_settings["location"])


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register(bus):
    global _bus, _active, _settings, _panel, _iss, _iss_loading, _iss_error, _iss_gate
    global _launch_state, _launch_loading, _reminders
    _bus = bus
    _active = True
    _panel = None
    _iss, _iss_loading, _iss_error = None, False, None
    _iss_gate = api.RequestGate()
    _launch_loading = False
    del _iss_waiters[:]
    del _launch_waiters[:]
    _settings = api.normalize_settings(core.api.load_data(DATA_KEY))
    if _settings["place"] is None and _settings["location"]:
        # First start with core 2.8: a city of its own stays in use, unless it
        # is the main place anyway.
        _settings["place"] = core.places.initial_choice(_settings["location"])
        _store_settings()
    _launch_state = api.normalize_launch_state(core.api.load_data(LAUNCH_KEY))
    _index_launches()
    stored = core.api.load_data(REMINDER_KEY)
    _reminders = api.normalize_reminders(stored.get("reminders") if isinstance(stored, dict) else None)

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # A ("antariksa"): free in the core and in every bundled and store
    # extension. Shift+A is Google Calendar's "Add a new event", so the list
    # of launches and Sun and Moon have no default key.
    core.hotkeys.register_action(EXT_NAME, "where_is_iss", _("action_iss"),
                                 ord("A"), False, speak_iss)
    core.hotkeys.register_action(EXT_NAME, "show_launches", _("action_launches"),
                                 None, False, show_launches)
    core.hotkeys.register_action(EXT_NAME, "sun_and_moon", _("action_sun_moon"),
                                 None, False, speak_sun_moon)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("Space extension loaded.")


def teardown():
    global _active, _panel
    _active = False
    _panel = None
    del _iss_waiters[:]
    del _launch_waiters[:]
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _bus.unsubscribe(event_name, handler)
            except Exception:
                pass
    logger.info("Space extension unloaded.")
