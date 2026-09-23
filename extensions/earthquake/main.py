# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Earthquakes & Tsunami (Gempa & Tsunami) — Hariku V2 extension.

Speaks BMKG's latest earthquake on a hotkey, lists recent earthquakes (BMKG,
optionally with USGS worldwide), and announces in the background:
  * earthquakes BMKG says have tsunami potential, anywhere (on by default);
  * earthquakes near the user, above a minimum magnitude (opt-in);
  * earthquakes BMKG reports as felt in the user's region (opt-in);
  * strong earthquakes worldwide from USGS, M6.5+ (opt-in).
Hariku is not an official warning system; the settings page and the first
alert of each session say so.

  earthquake_api.py    - requests, parsing, settings, the cache, distances
  earthquake_alerts.py - when to announce, and remembering what was announced
  earthquake_text.py   - spoken/displayed text in the user's language
  earthquake_ui.py     - Preferences page and the recent list

Data: BMKG (data.bmkg.go.id) and USGS (earthquake.usgs.gov), no account or
key; neither receives the user's location. The city search uses Open-Meteo.
All network calls run on worker threads, one request at a time; results come
back via wx.CallAfter. BMKG's latest-quake file (under 1 KB) is polled every 60
seconds while any BMKG alert is on, USGS every 5 minutes while worldwide alerts
are on; failures back off up to 15 minutes.
"""

import logging
import threading
import time

import wx

import core.api
import core.hotkeys
import core.preferences
from core.speech import speak

import earthquake_alerts as alerts
import earthquake_api as api
import earthquake_text as text
import earthquake_ui
from earthquake_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Earthquakes"          # fixed, so saved hotkeys survive a language change
DATA_KEY = "Earthquake"           # settings
CACHE_KEY = "EarthquakeCache"     # last BMKG/USGS data, see earthquake_api.normalize_cache()
ALERTS_KEY = "EarthquakeAlerts"   # what was announced, see earthquake_alerts.AlertTracker
WEATHER_DATA_KEY = "Weather"

POLL_SECONDS = 60                 # BMKG latest quake
WORLD_POLL_SECONDS = 300          # USGS past hour
FIRST_POLL_SECONDS = 15
MAX_BACKOFF_SECONDS = 15 * 60
LATEST_FRESH_SECONDS = 30         # the hotkey answers from the cache
LIST_FRESH_SECONDS = 120          # the list opens without fetching
STALE_MAX_AGE = 6 * 3600          # oldest data still offered when offline
BRIEFING_MAX_AGE = 24 * 3600
ALERT_SOUND = "info.wav"
TSUNAMI_SOUND = "error.wav"

JOBS = ("latest", "lists", "world_day", "world_hour")

_bus = None
_active = False
_settings = api.normalize_settings(None)
_cache = api.empty_cache()
_tracker = alerts.AlertTracker()
_running = None          # the job whose request is in flight
_queue = []              # jobs waiting for their turn
_waiters = {}            # job -> callbacks run on the UI thread when it ends
_poll_timer = None
_world_timer = None
_poll_running = False
_world_running = False
_poll_failures = 0
_world_failures = 0
_disclaimer_given = False
_panel = None


# ------------------------------------------------------------
# Small wrappers (replaced in tests)
# ------------------------------------------------------------

def _wall():
    return time.time()


def _start_thread(target, *args):
    threading.Thread(target=target, args=args, daemon=True, name="earthquake-fetch").start()


def _call_later(seconds, callback):
    return wx.CallLater(max(1, int(seconds * 1000)), callback)


def _cancel(timer):
    if timer is not None:
        try:
            timer.Stop()
        except Exception:
            pass


def _play_sound(name):
    try:
        import core.sounds
        core.sounds.play_internal_sound(name)
    except Exception as e:
        logger.debug(f"[Earthquakes] Sound failed: {e}")


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

def weather_location():
    """The Weather extension's city, used when no location is set here."""
    data = core.api.load_data(WEATHER_DATA_KEY)
    return api.normalize_location(data.get("location")) if isinstance(data, dict) else None


def get_location():
    return _settings.get("location") or weather_location()


def get_settings():
    return dict(_settings)


def _save_settings(new_settings):
    """Save settings; keys not given keep their current values."""
    global _settings
    _settings = api.normalize_settings(dict(_settings, **new_settings))
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(_settings)
    core.api.save_data(DATA_KEY, data)
    _update_polling()


def _save_cache():
    core.api.save_data(CACHE_KEY, _cache)


def _save_tracker():
    _tracker.prune(_wall())
    if _tracker.changed:
        core.api.save_data(ALERTS_KEY, _tracker.to_json())
        _tracker.changed = False


# ------------------------------------------------------------
# Fetching: one request in flight, jobs queued behind it
# ------------------------------------------------------------

def request(kind, on_done=None):
    """Fetch `kind` (one of JOBS) in the background. on_done(error) runs on
    the UI thread afterwards (error is None on success). A job already queued
    or running is joined, not repeated."""
    if not _active:
        return False
    if on_done is not None:
        _waiters.setdefault(kind, []).append(on_done)
    if kind != _running and kind not in _queue:
        _queue.append(kind)
    _dispatch()
    return True


def _dispatch():
    global _running
    if not _active or _running is not None or not _queue:
        return
    _running = _queue.pop(0)
    _start_thread(_job_worker, _running)


def _job_worker(kind):
    # Worker thread: network only, never wx objects.
    result, error = None, None
    try:
        if kind == "latest":
            result = api.fetch_latest()
        elif kind == "lists":
            result = api.fetch_bmkg_lists()
        elif kind == "world_day":
            result = api.fetch_usgs(api.USGS_DAY_URL)
        else:
            result = api.fetch_usgs(api.USGS_HOUR_URL)
    except api.QuakeError as e:
        error = e.kind
        logger.info(f"[Earthquakes] {kind} fetch failed: {e}")
    except Exception:
        error = "bad_response"
        logger.exception(f"[Earthquakes] {kind} fetch failed")
    wx.CallAfter(_on_job_done, kind, result, error)


def _on_job_done(kind, result, error):
    global _running
    _running = None
    if not _active:
        _waiters.clear()
        del _queue[:]
        return
    if error is None:
        _store(kind, result, _wall())
    for callback in _waiters.pop(kind, []):
        try:
            callback(error)
        except Exception:
            logger.exception("[Earthquakes] Refresh callback failed")
    # After the callbacks, so a quake the user just heard is not announced again.
    if error is None and kind == "latest":
        _check_bmkg_alert(result)
    elif error is None and kind == "world_hour":
        _check_world_alerts(result)
    _dispatch()


def _store(kind, result, now):
    if kind == "latest":
        history = api.add_to_history(_cache["history"], result, now)
        changed = result != _cache["latest"] or history != _cache["history"]
        _cache.update(latest=result, latest_at=now, history=history)
    elif kind == "lists":
        changed = True
        _cache.update(lists=result, lists_at=now)
    elif kind == "world_day":
        changed = True
        _cache.update(world_day=result, world_day_at=now)
    else:
        return   # the worldwide alert poll is not kept
    if changed:
        _save_cache()


def refresh_list(on_done=None):
    """Fetch what the recent list shows; on_done(error) once all of it is in
    (error is the first failure, or None)."""
    if not _active:
        return False
    kinds = ["lists"] + (["world_day"] if _settings["list_world"] else [])
    state = {"left": len(kinds), "error": None}

    def done(error):
        state["left"] -= 1
        if error and state["error"] is None:
            state["error"] = error
        if state["left"] == 0 and on_done is not None:
            on_done(state["error"])

    for kind in kinds:
        request(kind, done)
    return True


def refresh_world(on_done=None):
    return request("world_day", on_done)


# ------------------------------------------------------------
# Alerts
# ------------------------------------------------------------

def _announce(message, urgent=False):
    """Speak an alert. The first one of the session carries the disclaimer."""
    global _disclaimer_given
    if not _disclaimer_given:
        message = f"{message} {_('disclaimer')}"
        _disclaimer_given = True
    if _settings["sounds"]:
        _play_sound(TSUNAMI_SOUND if urgent else ALERT_SOUND)
    speak(message, interrupt=urgent)


def _check_bmkg_alert(quake):
    now = _wall()
    reason = _tracker.check_bmkg(quake, _settings, get_location(), now)
    _save_tracker()
    if reason is not None:
        _announce(text.alert_text(reason, quake, get_location(), now), urgent=reason == "tsunami")


def _check_world_alerts(quakes):
    now = _wall()
    new = _tracker.check_usgs(quakes, _settings, now)
    _save_tracker()
    if new:
        _announce(text.world_alert_text(new, get_location(), now))


def _bmkg_polling_wanted():
    return _active and (_settings["tsunami_alerts"] or _settings["nearby_alerts"]
                        or _settings["felt_alerts"])


def _world_polling_wanted():
    return _active and _settings["world_alerts"]


def _backoff(base, failures):
    return min(MAX_BACKOFF_SECONDS, base * (2 ** min(failures, 6)))


def _update_polling(first_delay=FIRST_POLL_SECONDS):
    """Start each poll when an alert needs it, stop it when none does."""
    global _poll_timer, _world_timer
    if not _bmkg_polling_wanted():
        _cancel(_poll_timer)
        _poll_timer = None
    elif _poll_timer is None and not _poll_running:
        _poll_timer = _call_later(first_delay, _poll)
    if not _world_polling_wanted():
        _cancel(_world_timer)
        _world_timer = None
    elif _world_timer is None and not _world_running:
        _world_timer = _call_later(first_delay, _world_poll)


def _poll():
    global _poll_timer, _poll_running
    _poll_timer = None
    if not _bmkg_polling_wanted():
        return
    _poll_running = True
    if not request("latest", _after_poll):
        _poll_running = False


def _after_poll(error):
    global _poll_timer, _poll_running, _poll_failures
    _poll_running = False
    _poll_failures = _poll_failures + 1 if error else 0
    if _bmkg_polling_wanted() and _poll_timer is None:
        _poll_timer = _call_later(_backoff(POLL_SECONDS, _poll_failures), _poll)


def _world_poll():
    global _world_timer, _world_running
    _world_timer = None
    if not _world_polling_wanted():
        return
    _world_running = True
    if not request("world_hour", _after_world_poll):
        _world_running = False


def _after_world_poll(error):
    global _world_timer, _world_running, _world_failures
    _world_running = False
    _world_failures = _world_failures + 1 if error else 0
    if _world_polling_wanted() and _world_timer is None:
        _world_timer = _call_later(_backoff(WORLD_POLL_SECONDS, _world_failures), _world_poll)


# ------------------------------------------------------------
# Actions
# ------------------------------------------------------------

def speak_latest():
    """BMKG's latest earthquake, spoken."""
    if _cache["latest"] and api.is_fresh(_cache["latest_at"], LATEST_FRESH_SECONDS, _wall()):
        _speak_latest_report()
        return
    speak(_("checking"), interrupt=True)
    request("latest", _speak_after_refresh)


def _speak_after_refresh(error):
    latest = _cache["latest"]
    if latest and error is None:
        _speak_latest_report()
    elif latest and api.is_fresh(_cache["latest_at"], STALE_MAX_AGE, _wall()):
        _speak_latest_report(" ".join([
            text.error_text(error),
            _("stale_notice", time=text.time_text(_cache["latest_at"], _wall()))]))
    else:
        speak(text.error_text(error), interrupt=True)


def _speak_latest_report(prefix=""):
    global _disclaimer_given
    quake = _cache["latest"]
    tsunami = api.is_tsunami_potential(quake.get("potential"))
    disclaimer = tsunami and not _disclaimer_given
    if disclaimer:
        _disclaimer_given = True
    if tsunami and _settings["sounds"]:
        _play_sound(TSUNAMI_SOUND)
    _tracker.heard(quake)
    _save_tracker()
    report = text.latest_report(quake, get_location(), _wall(), disclaimer)
    speak(" ".join(p for p in (prefix, report) if p), interrupt=True)


def list_data():
    """(quakes, updated_at) for the recent list."""
    return (api.recent_quakes(_cache, _settings["list_world"], _wall()), _cache["lists_at"])


def _list_fresh():
    now = _wall()
    if not api.is_fresh(_cache["lists_at"], LIST_FRESH_SECONDS, now):
        return False
    return not _settings["list_world"] or api.is_fresh(_cache["world_day_at"],
                                                        LIST_FRESH_SECONDS, now)


def set_list_world(value):
    _save_settings({"list_world": bool(value)})


def show_recent():
    """The list of recent earthquakes."""
    parent = getattr(core.api, "main_window_instance", None)
    dlg = earthquake_ui.RecentDialog(
        parent, list_data, refresh_list, get_location, list_world=_settings["list_world"],
        set_list_world=set_list_world, request_world=refresh_world,
        refresh_now=not _list_fresh(), now=_wall)
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------------
# Events
# ------------------------------------------------------------

def _on_network_changed(online=True, *_args, **_kwargs):
    global _poll_failures, _world_failures, _poll_timer, _world_timer
    if not online:
        return
    _poll_failures = _world_failures = 0
    # Back online: don't sit out the back-off.
    if _poll_timer is not None:
        _cancel(_poll_timer)
        _poll_timer = _call_later(FIRST_POLL_SECONDS, _poll)
    if _world_timer is not None:
        _cancel(_world_timer)
        _world_timer = _call_later(FIRST_POLL_SECONDS, _world_poll)


def _on_briefing_collect(lines):
    # Briefing contract: fast, cache only, append nothing without data.
    location = get_location()
    if not location:
        return
    now = _wall()
    quake = api.latest_near(api.known_bmkg(_cache), location, _settings["alert_km"], now,
                            BRIEFING_MAX_AGE)
    if quake:
        lines.append(text.briefing_sentence(quake, location, now))


_SUBSCRIPTIONS = (
    ("on_network_changed", _on_network_changed),
    ("on_briefing_collect", _on_briefing_collect),
)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    _panel = earthquake_ui.EarthquakePanel(parent, get_settings(), weather_location())
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
    global _bus, _active, _settings, _cache, _tracker, _running, _poll_timer, _world_timer
    global _poll_running, _world_running, _poll_failures, _world_failures, _disclaimer_given
    _bus = bus
    _active = True
    _running = None
    del _queue[:]
    _waiters.clear()
    _poll_timer = _world_timer = None
    _poll_running = _world_running = False
    _poll_failures = _world_failures = 0
    _disclaimer_given = False
    _settings = api.normalize_settings(core.api.load_data(DATA_KEY))
    _cache = api.normalize_cache(core.api.load_data(CACHE_KEY))
    _tracker = alerts.AlertTracker.from_json(core.api.load_data(ALERTS_KEY))

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # G ("gempa") and Shift+G: free in the core (which uses Ctrl+G) and in every
    # bundled and store extension. Shift+G opens a window, G only speaks.
    core.hotkeys.register_action(EXT_NAME, "speak_latest", _("action_latest"),
                                 ord("G"), False, speak_latest)
    core.hotkeys.register_action(EXT_NAME, "show_recent", _("action_recent"),
                                 ord("G"), False, show_recent, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    _update_polling()
    logger.info("Earthquakes extension loaded.")


def teardown():
    global _active, _poll_timer, _world_timer, _panel, _running
    _active = False
    _cancel(_poll_timer)
    _cancel(_world_timer)
    _poll_timer = _world_timer = None
    _running = None
    del _queue[:]
    _waiters.clear()
    _panel = None
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _bus.unsubscribe(event_name, handler)
            except Exception:
                pass
    logger.info("Earthquakes extension unloaded.")
