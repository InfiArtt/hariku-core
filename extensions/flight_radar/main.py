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
everything in range, optional announcements when one passes overhead or
reports an emergency (both silent during the user's quiet hours), and a
shortcut to LiveATC's web page for the nearby airport. Aircraft positions come from adsb.fi (adsb.lol when adsb.fi fails),
routes from adsbdb.com; none need an account or key. The place is the main
place from Preferences, Places (core 2.8) unless another place, or a place of
its own (a city, an address or pasted coordinates), is chosen in Preferences,
Flight Radar, with the radius and units.

  flight_radar_api.py      - aircraft requests, parsing, settings, units, pacing,
                             emergencies
  flight_radar_routes.py   - best-effort routes (memory only, plausibility check)
  flight_radar_names.py    - airline and aircraft type names
  flight_radar_airports.py - airports near Indonesia (OurAirports data)
  flight_radar_atc.py      - which airport to listen to, and its LiveATC page
  flight_radar_flights.py  - "Track a flight": flight numbers and what to announce
  flight_radar_text.py     - spoken/displayed text in the user's language
  flight_radar_registrations.py - the country of a registration prefix
  flight_radar_ui.py       - Preferences page, the aircraft list, Track a flight

Pasted coordinates, map links and the address search come from the core
(core.place_search, which Flight Radar's own module moved to). The user's
exact location stays on this computer (Places.json, or the FlightRadar data
key for a place of its own); the aircraft services get it rounded to about
1 km (see flight_radar_api.py).
All network calls run on worker threads; results come back via wx.CallAfter.
At most one aircraft request (area or tracked flight) is in flight, requests
are at least 5 seconds apart, answers are reused for 15 seconds, and failures
back off.
"""

import logging
import threading
import time
import webbrowser

import wx

import core.api
import core.hotkeys
import core.personal
import core.places
import core.preferences
from core.speech import speak

import flight_radar_airports as airports
import flight_radar_api as api
import flight_radar_atc as atc
import flight_radar_flights as flights
import flight_radar_routes as routes
import flight_radar_text as text
import flight_radar_ui
from flight_radar_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Flight Radar"   # fixed, so saved hotkeys survive a language change
DATA_KEY = "FlightRadar"    # settings only; aircraft and routes are never saved

CACHE_SECONDS = 15          # answer from the last result without fetching
STALE_MAX_AGE = 120         # oldest result still offered after a failure
POLL_SECONDS = 30           # overhead alerts
EMERGENCY_POLL_SECONDS = 60  # emergency watch alone
FIRST_POLL_SECONDS = 10
ALERT_COOLDOWN = 600        # an aircraft is announced once per 10 minutes
EMERGENCY_COOLDOWN = 1800   # an aircraft's emergency is announced once per 30 minutes
ALERT_SOUND = "info.wav"
EMERGENCY_SOUND = "error.wav"
TRACK_SOUND = "info.wav"
ROUTE_WAIT_SECONDS = 3.0    # longest wait for route lookups before speaking

_bus = None
_active = False
_settings = api.normalize_settings(None)
_cache = None
_loading = False
_waiters = []           # callbacks run on the UI thread when the running fetch ends
_gate = api.RateGate()
_tracker = api.AlertTracker(ALERT_COOLDOWN)
_emergency_tracker = api.EmergencyTracker(EMERGENCY_COOLDOWN)
_routes = routes.RouteLookup()
_fetch_timer = None     # the next request waiting for the rate limit
_area_pending = False   # an area fetch is waiting for its turn
_flight_jobs = []       # worldwide flight lookups waiting for their turn
_flight_running = None  # the flight lookup in flight
_flight_cache = {}      # (kind, id) -> (monotonic time, aircraft); memory only
_observations = {}      # (kind, id) -> (wall time, plane or None); memory only
_poll_timer = None
_poll_running = False
_panel = None


# ------------------------------------------------------------
# Small wrappers (replaced in tests)
# ------------------------------------------------------------

def _now():
    return time.monotonic()


def _wall():
    # Tracked flights outlive a restart, so their times are wall-clock.
    return time.time()


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


def _play_sound(name):
    try:
        import core.sounds
        core.sounds.play_internal_sound(name)
    except Exception as e:
        logger.debug(f"[Flight Radar] Sound failed: {e}")


def _open_url(url):
    # Only ever LiveATC's own page, in the user's browser, after they asked.
    try:
        webbrowser.open(url)
    except Exception as e:
        logger.info(f"[Flight Radar] Could not open the browser: {e}")


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

def get_location():
    """The place in use: the chosen place from Preferences, Places (the main
    place by default), or the place of its own; None without one."""
    return core.places.location_for(_settings.get("place"), _settings.get("location"))


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
    """Save settings; keys not given keep their current values."""
    global _settings
    new_settings = api.normalize_settings(dict(_settings, **new_settings))
    old_location = get_location()
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(new_settings)
    core.api.save_data(DATA_KEY, data)
    _settings = new_settings
    if get_location() != old_location:
        _tracker.reset()
        _emergency_tracker.reset()
    _update_polling()


# ------------------------------------------------------------
# Fetching aircraft
# ------------------------------------------------------------

def refresh(on_done=None):
    """Fetch aircraft now, or as soon as the rate limit allows. on_done(error)
    runs on the UI thread afterwards (error is None on success). Returns False
    if nothing can be fetched because no location is set."""
    global _area_pending
    if not _active or not get_location():
        return False
    if on_done is not None and on_done not in _waiters:
        _waiters.append(on_done)
    if not _loading:
        _area_pending = True
    _dispatch()
    return True


def _dispatch():
    """Start the next waiting request (area first, then flight lookups) when
    none is in flight and the rate limit allows; otherwise try again later."""
    global _fetch_timer, _area_pending
    if not _active or _loading or _flight_running is not None or _fetch_timer is not None:
        return
    if not _area_pending and not _flight_jobs:
        return
    now = _now()
    if _gate.cooldown_left(now) > 0:
        if _area_pending:
            _area_pending = False
            wx.CallAfter(_deliver, "rate_limited")
        jobs = _flight_jobs[:]
        del _flight_jobs[:]
        for job in jobs:
            wx.CallAfter(_deliver_flight, job, [], "rate_limited")
        return
    wait = _gate.wait_time(now)
    if wait > 0:
        _fetch_timer = _call_later(wait, _on_dispatch_timer)
        return
    if _area_pending:
        _area_pending = False
        _start_fetch()
    else:
        _start_flight(_flight_jobs.pop(0))


def _on_dispatch_timer():
    global _fetch_timer
    _fetch_timer = None
    _dispatch()


def _start_fetch():
    global _loading
    location = get_location()
    if not _active:
        return
    if not location:
        _deliver(None)
        _dispatch()
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
    _dispatch()


def _deliver(error):
    waiters = _waiters[:]
    del _waiters[:]
    for callback in waiters:
        try:
            callback(error)
        except Exception:
            logger.exception("[Flight Radar] Refresh callback failed")


# ------------------------------------------------------------
# Worldwide flight lookups
# ------------------------------------------------------------

def lookup_flight(target, on_done):
    """Find one flight worldwide by callsign or registration ({"kind", "id"}).
    on_done(aircraft list, error) runs on the UI thread. Shares the pacing with
    the area fetch; answers are reused for 15 seconds."""
    if not _active:
        return False
    key = flights.target_key(target)
    cached = _flight_cache.get(key)
    if cached and 0 <= _now() - cached[0] <= CACHE_SECONDS:
        on_done(list(cached[1]), None)
        return True
    for job in _flight_jobs + ([_flight_running] if _flight_running else []):
        if job["key"] == key:
            job["callbacks"].append(on_done)
            return True
    _flight_jobs.append({"key": key, "target": {"kind": key[0], "id": key[1]},
                         "callbacks": [on_done]})
    _dispatch()
    return True


def _start_flight(job):
    global _flight_running
    _flight_running = job
    _gate.started(_now())
    location = get_location()
    point = (location["latitude"], location["longitude"]) if location else (None, None)
    _start_thread(_flight_worker, job, *point)


def _flight_worker(job, latitude, longitude):
    # Worker thread: sends only the callsign or registration.
    aircraft, error = [], None
    try:
        aircraft, _source = api.fetch_flight(job["target"]["kind"], job["target"]["id"],
                                             latitude, longitude)
    except api.FlightError as e:
        error = e.kind
    except Exception:
        error = "bad_response"
        logger.exception("[Flight Radar] Flight lookup failed")
    wx.CallAfter(_on_flight_fetched, job, aircraft, error)


def _on_flight_fetched(job, aircraft, error):
    global _flight_running
    _flight_running = None
    _gate.finished(_now(), error)
    if error is None:
        _flight_cache[job["key"]] = (_now(), aircraft)
    if _active:
        _deliver_flight(job, aircraft, error)
    _dispatch()


def _deliver_flight(job, aircraft, error):
    for callback in job["callbacks"]:
        try:
            callback(list(aircraft), error)
        except Exception:
            logger.exception("[Flight Radar] Flight lookup callback failed")


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


def emergency_intro(aircraft):
    """The emergencies among `aircraft`, to speak before anything else. They
    count as heard, so the background watch does not repeat them."""
    _emergency_tracker.mark(aircraft, _now())
    return text.emergency_text(aircraft, _settings["units"])


def _speak_report(prefix=""):
    aircraft = visible_aircraft()
    settings = get_settings()
    urgent = emergency_intro(aircraft)

    def say():
        report = text.nearby_report(aircraft, settings["radius_km"], settings["units"],
                                    settings["include_ground"], leg_for)
        speak(" ".join(p for p in (urgent, prefix, report) if p), interrupt=True)

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
        refresh_now=not api.is_fresh(current_cache(), CACHE_SECONDS, _now()),
        listen=listen_for_aircraft, emergency_intro=emergency_intro, track=track_from_list)
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------------
# Track a flight
# ------------------------------------------------------------

def tracked_flights():
    return [dict(entry, notified=list(entry["notified"])) for entry in _settings["tracked"]]


def _find_tracked(key):
    return next((dict(t, notified=list(t["notified"])) for t in _settings["tracked"]
                 if flights.target_key(t) == key), None)


def _replace_tracked(entry):
    key = flights.target_key(entry)
    _save_settings({"tracked": [entry if flights.target_key(t) == key else t
                                for t in _settings["tracked"]]})


def _near_you_km():
    return _settings["alert_km"] if get_location() else None


def _record(key, plane, quiet):
    """Remember the latest sighting and update the entry's state; returns the
    events to announce."""
    _observations[key] = (_wall(), plane)
    entry = _find_tracked(key)
    if entry is None or plane is None:
        return []
    before = dict(entry, notified=list(entry["notified"]))
    events = flights.evaluate(entry, plane, _wall(), leg_for(plane), _near_you_km(), quiet=quiet)
    if entry != before:
        _replace_tracked(entry)
    return events


def track_flight(typed, on_result=None):
    """Look up a flight the user typed, say where it is, and track it."""
    try:
        target = flights.parse_flight_input(typed)
    except flights.FlightInputError as e:
        speak(text.flight_input_error_text(e), interrupt=True)
        return False
    name = text.flight_label(target)
    key = flights.target_key(target)
    speak(_("track_looking", name=name), interrupt=True)

    def finish():
        if on_result is not None:
            on_result()

    def found(aircraft, error):
        if error:
            speak(text.error_text(error), interrupt=True)
            finish()
            return
        plane = flights.pick_aircraft(aircraft)
        outcome = _start_tracking(target, plane)

        def say():
            _record(key, plane, quiet=True)
            leg = leg_for(plane) if plane else None
            parts = [text.tracked_sentence(plane, _settings["units"], leg, name) if plane
                     else text.not_transmitting_text(name)]
            if outcome == "added":
                parts.append(_("track_added"))
            elif outcome == "full":
                parts.append(_("track_full", count=api.TRACK_LIMIT))
            speak(" ".join(parts), interrupt=True)
            finish()

        if plane:
            with_routes([plane], say)
        else:
            say()

    lookup_flight(target, found)
    return True


def _start_tracking(target, plane):
    """"added", "already" or "full"."""
    key = flights.target_key(target)
    tracked = _settings["tracked"]
    if any(flights.target_key(t) == key for t in tracked):
        return "already"
    if len(tracked) >= api.TRACK_LIMIT:
        return "full"
    _save_settings({"tracked": tracked + [flights.new_entry(target, _wall())]})
    return "added"


def untrack(key):
    entry = _find_tracked(key)
    if entry is None:
        return
    _save_settings({"tracked": [t for t in _settings["tracked"] if flights.target_key(t) != key]})
    _observations.pop(key, None)
    speak(_("track_stopped", name=text.flight_label(entry)), interrupt=True)


def tracked_rows():
    """[(key, row)] for the Track dialog, from the last sightings (no lookups)."""
    rows = []
    for entry in _settings["tracked"]:
        key = flights.target_key(entry)
        observation = _observations.get(key)
        plane = observation[1] if observation else None
        rows.append((key, text.tracked_row(text.flight_label(entry), observation,
                                           _settings["units"],
                                           leg_for(plane) if plane else None)))
    return rows


def speak_tracked(on_done=None):
    """Where are my tracked flights? Looks each one up, then speaks them all."""
    entries = tracked_flights()
    if not entries:
        speak(_("track_none"), interrupt=True)
        if on_done is not None:
            on_done()
        return
    speak(_("track_checking"), interrupt=True)
    results = {}

    def got(entry, aircraft, error):
        key = flights.target_key(entry)
        results[key] = (None if error else flights.pick_aircraft(aircraft), error)
        if len(results) == len(entries):
            with_routes([plane for plane, _error in results.values() if plane], say)

    def say():
        sentences = []
        for entry in entries:
            key = flights.target_key(entry)
            plane, error = results[key]
            name = text.flight_label(entry)
            if error:
                sentences.append(_("tracked_row", name=name, status=text.error_text(error)))
                continue
            _record(key, plane, quiet=True)
            sentences.append(text.tracked_sentence(plane, _settings["units"], leg_for(plane), name)
                             if plane else text.not_transmitting_text(name))
        speak(" ".join(sentences), interrupt=True)
        if on_done is not None:
            on_done()

    for entry in entries:
        lookup_flight(entry, lambda aircraft, error, entry=entry: got(entry, aircraft, error))


def show_track_dialog(initial=""):
    """Track a flight: type a flight number; see and stop tracked flights."""
    parent = getattr(core.api, "main_window_instance", None)
    dlg = flight_radar_ui.TrackFlightDialog(parent, tracked_rows, track_flight, untrack,
                                            speak_tracked, initial=initial)
    dlg.ShowModal()
    dlg.Destroy()


def track_from_list(plane):
    """The list's Track button: the dialog, filled in with this aircraft."""
    initial = ""
    if plane:
        initial = plane.get("callsign") or plane.get("registration") or ""
    show_track_dialog(initial)


def _check_tracked(entry, done):
    """One background check of a tracked flight; done(error) afterwards."""
    key = flights.target_key(entry)

    def found(aircraft, error):
        if error or _find_tracked(key) is None:
            done(error)
            return
        plane = flights.pick_aircraft(aircraft)
        if plane is None:
            _observations[key] = (_wall(), None)
            done(None)
            return

        def check():
            events = _record(key, plane, quiet=False)
            if events:
                name = text.flight_label(entry)
                leg = leg_for(plane)
                _play_sound(TRACK_SOUND)
                speak(" ".join(text.event_text(event, name, plane, _settings["units"], leg, detail)
                               for event, detail in events))
            done(None)

        with_routes([plane], check)

    lookup_flight(entry, found)


def _prune_tracked():
    """Stop tracking flights an hour after landing or after 24 hours."""
    now = _wall()
    keep = [t for t in _settings["tracked"] if not flights.should_stop(t, now)]
    if len(keep) != len(_settings["tracked"]):
        for t in _settings["tracked"]:
            if t not in keep:
                _observations.pop(flights.target_key(t), None)
        _save_settings({"tracked": keep})


# ------------------------------------------------------------
# Listen to ATC (LiveATC's web page, in the browser)
# ------------------------------------------------------------

def listen_to_atc():
    """Open LiveATC for the airport nearest to the chosen city."""
    location = get_location()
    if not location:
        speak(_("no_location"), interrupt=True)
        return
    _open_atc(atc.nearest_airport(location["latitude"], location["longitude"]), False)


def listen_for_aircraft(plane):
    """Open LiveATC for the airport an aircraft is most likely talking to
    (after its route has been looked up), or the one nearest to the city."""
    if plane is None:
        listen_to_atc()
        return
    airport = atc.airport_for_aircraft(plane, leg_for(plane))
    if airport is None:
        location = get_location()
        airport = location and atc.nearest_airport(location["latitude"], location["longitude"])
    _open_atc(airport, True)


def _open_atc(airport, for_aircraft):
    url, has_feed = atc.liveatc_url(airport["icao"]) if airport else (None, False)
    if not url:
        speak(_("atc_no_airport"), interrupt=True)
        return
    name = airports.label(airport)
    parts = [_("atc_opening_feed", airport=name) if has_feed
             else _("atc_opening_search", airport=name)]
    if for_aircraft:
        parts.append(_("atc_whole_frequency"))
    speak(" ".join(parts), interrupt=True)
    _start_thread(_open_url, url)


# ------------------------------------------------------------
# Background polling: overhead alerts, the emergency watch and tracked
# flights share it
# ------------------------------------------------------------

def _area_polling_wanted():
    return ((_settings["alerts"] or _settings["emergency_watch"])
            and get_location() is not None)


def _polling_wanted():
    return _active and (_area_polling_wanted() or bool(_settings["tracked"]))


def _poll_interval():
    return POLL_SECONDS if _settings["alerts"] and get_location() else EMERGENCY_POLL_SECONDS


def _update_polling(first_delay=FIRST_POLL_SECONDS):
    """Start polling when alerts, the emergency watch or a tracked flight need
    it, stop it when nothing does."""
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
    _poll_running = True
    _prune_tracked()
    tasks = []
    # Quiet hours: no overhead alerts or emergency watch, so no area requests
    # either. Tracked flights, which the user asked for, still report.
    if _area_polling_wanted() and not core.personal.is_quiet_time():
        tasks.append(_poll_area)
    for entry in tracked_flights():
        tasks.append(lambda done, entry=entry: _check_tracked(entry, done))
    if not tasks:
        _after_poll()   # keeps polling through quiet hours, stops when unwanted
        return
    state = {"left": len(tasks), "errors": 0}

    def done(error):
        state["left"] -= 1
        state["errors"] += 1 if error else 0
        if state["left"] == 0:
            _after_poll(state["errors"])

    for task in tasks:
        task(done)


def _poll_area(done):
    if api.is_fresh(current_cache(), CACHE_SECONDS, _now()):
        _check_emergencies()
        _check_alerts()
        done(None)
        return

    def after(error):
        if error is None and _area_polling_wanted():
            _check_emergencies()
            _check_alerts()
        done(error)

    if not refresh(after):
        done(None)


def _after_poll(errors=0):
    global _poll_running
    _poll_running = False
    if not _polling_wanted():
        return
    interval = _poll_interval()
    _schedule_poll(_gate.backoff(interval) if errors else interval)


def _check_emergencies():
    """Announce emergencies not heard in the last 30 minutes, first. Nothing
    during quiet hours, and nothing saved up for afterwards."""
    if not current_cache() or core.personal.is_quiet_time():
        return
    new = _emergency_tracker.check(visible_aircraft(), _now())
    if new:
        _play_sound(EMERGENCY_SOUND)
        speak(text.emergency_text(new, _settings["units"]))


def _check_alerts():
    cache = current_cache()
    if not cache or not _settings["alerts"] or core.personal.is_quiet_time():
        return
    new = _tracker.check(cache["aircraft"], _settings["alert_km"], _now())
    if not new:
        return
    units = _settings["units"]

    def announce():
        if not _settings["alerts"]:
            return
        _play_sound(ALERT_SOUND)
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


def _on_places_changed(*_args, **_kwargs):
    """The places changed (Preferences, Places): show them on the settings
    page; when the place in use moved, forget what was announced for the old
    one, and start or stop polling."""
    if _panel:
        try:
            _panel.refresh_places()
        except RuntimeError:
            pass  # panel already destroyed
    if _cache is not None and current_cache() is None:
        _tracker.reset()
        _emergency_tracker.reset()
    _update_polling()


_SUBSCRIPTIONS = (
    ("on_app_startup", _on_app_startup),
    ("on_network_changed", _on_network_changed),
    ("on_places_changed", _on_places_changed),
)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    _panel = flight_radar_ui.FlightRadarPanel(parent, get_settings())
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
    global _bus, _active, _settings, _cache, _loading, _gate, _tracker, _routes
    global _fetch_timer, _poll_timer, _poll_running, _emergency_tracker
    global _area_pending, _flight_running
    _bus = bus
    _active = True
    _cache = None
    _loading = False
    _fetch_timer = _poll_timer = None
    _poll_running = False
    _area_pending = False
    _flight_running = None
    del _flight_jobs[:]
    _flight_cache.clear()
    _observations.clear()
    _gate = api.RateGate()
    _tracker = api.AlertTracker(ALERT_COOLDOWN)
    _emergency_tracker = api.EmergencyTracker(EMERGENCY_COOLDOWN)
    _routes = routes.RouteLookup()
    _settings = api.normalize_settings(core.api.load_data(DATA_KEY))
    if _settings["place"] is None and _settings["location"]:
        # First start with core 2.8: a place of its own stays in use, unless it
        # is the main place anyway (the exact home Places was made from).
        _settings["place"] = core.places.initial_choice(_settings["location"])
        data = core.api.load_data(DATA_KEY)
        data = data if isinstance(data, dict) else {}
        data["place"] = _settings["place"]
        core.api.save_data(DATA_KEY, data)

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # P ("pesawat" / plane) and Shift+P: free in the core (which uses Ctrl+P) and
    # in every bundled and store extension (Project System uses Ctrl+Shift+P).
    core.hotkeys.register_action(EXT_NAME, "speak_nearby", _("action_nearby"),
                                 ord("P"), False, speak_nearby)
    core.hotkeys.register_action(EXT_NAME, "show_list", _("action_list"),
                                 ord("P"), False, show_list, default_shift=True)
    # Shift+L ("listen"): also free everywhere. Shifted, like Shift+P, because
    # it opens a window (the browser).
    core.hotkeys.register_action(EXT_NAME, "listen_atc", _("action_listen_atc"),
                                 ord("L"), False, listen_to_atc, default_shift=True)
    # T and Shift+T ("track"): free everywhere (Window Teleporter only uses T
    # with Ctrl or Alt). Shift+T opens the Track dialog, T speaks the flights.
    core.hotkeys.register_action(EXT_NAME, "speak_tracked", _("action_speak_tracked"),
                                 ord("T"), False, speak_tracked)
    core.hotkeys.register_action(EXT_NAME, "track_flight", _("action_track"),
                                 ord("T"), False, show_track_dialog, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    _update_polling()
    logger.info("Flight Radar extension loaded.")


def teardown():
    global _active, _fetch_timer, _poll_timer, _panel
    _active = False
    del _waiters[:]
    del _flight_jobs[:]
    _flight_cache.clear()
    _observations.clear()
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
