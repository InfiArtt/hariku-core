# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Cockpit — Hariku V2 extension ("Kokpit" in Indonesian).

Pilot vibes: aviation weather (METAR and TAF from the NOAA Aviation Weather
Center, aviationweather.gov, no account or key) decoded into plain sentences,
and Captain mode, which puts the airport weather in the Morning Briefing and
the evening summary, keeps it fresh in the background, spells codes in the
ICAO alphabet and offers to call the user Captain.

  cockpit_metar.py  - METAR and TAF decoding, flight category, nearest airport (pure)
  cockpit_api.py    - requests, parsing, settings, cache and back-off (no wx)
  cockpit_text.py   - spoken and displayed sentences in the user's language
  cockpit_sounds.py - the generated "Cockpit" sound theme and its installer
  cockpit_ui.py     - the Preferences page and the Airport weather window

With no favourite airports, it uses the airport with a METAR nearest to a
place from Preferences, Places (core 2.8): the main place unless another one
is chosen in Preferences, Cockpit.

Network: worker threads only, one request at a time and at least 2 seconds
apart, 10-second timeouts. A METAR is fetched on demand at most every 10
minutes and a TAF every 30; after errors, requests pause (longer each time).
Nothing is polled unless Captain mode is on: then the default airport's METAR
and TAF are refreshed at most every 30 minutes. The Briefing, the evening
summary and %airportweather% only read the cache.
"""

import logging
import threading
import time

import wx

import core.api
import core.hotkeys
import core.personal
import core.places
import core.preferences
import core.sounds
from core.speech import speak

import cockpit_api as api
import cockpit_metar as metar
import cockpit_sounds as sounds
import cockpit_text as text
import cockpit_ui
from cockpit_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Cockpit"        # fixed, so saved hotkeys survive a language change
DATA_KEY = "Cockpit"        # settings, see cockpit_api.normalize_settings()
CACHE_KEY = "CockpitCache"  # reports, see cockpit_api.normalize_cache()
PLACEHOLDER = "airportweather"

METAR_FRESH = 10 * 60       # on demand: answer from the cache when younger
TAF_FRESH = 30 * 60
BACKGROUND_FRESH = 30 * 60  # Captain mode: refresh what is older than this
BRIEFING_MAX_AGE = 3 * 3600  # oldest observation used in the Briefing and %airportweather%
EVENING_TAF_AGE = 12 * 3600  # oldest TAF used in the evening summary
STALE_MAX_AGE = 12 * 3600    # oldest report still offered when offline

_bus = None
_active = False
_settings = api.normalize_settings(None)
_cache = api.empty_cache()
_backoff = api.Backoff()
_queue = []          # jobs waiting: {"kind", "key", "args", "callbacks"}
_running = None      # the job whose request is in flight
_last_request = 0.0
_last_background = 0.0
_panel = None
_dialog = None


# ------------------------------------------------------------
# Small wrappers (replaced in tests)
# ------------------------------------------------------------

def _start_thread(target, *args):
    threading.Thread(target=target, args=args, daemon=True, name="cockpit-fetch").start()


def _sleep(seconds):
    time.sleep(seconds)


def _now():
    return time.time()


def _ask_yes_no(message):
    """Captain mode's offers: a Yes/No dialog, Yes by default. They come while
    Preferences is open, so they belong to it (the active window), on top."""
    parent = wx.GetActiveWindow() or getattr(core.api, "main_window_instance", None)
    return cockpit_ui.ask_yes_no(parent, _("captain_title"), message)


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

def place_location():
    """The place the nearest airport is found for: the chosen place from
    Preferences, Places (the main place by default), or None."""
    return core.places.location_for(_settings.get("place") or core.places.CHOICE_MAIN)


def get_settings():
    return dict(_settings, favourites=[dict(a) for a in _settings["favourites"]])


def is_captain():
    return _settings["captain"]


def _save_settings():
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(_settings)
    core.api.save_data(DATA_KEY, data)


def _save_cache():
    core.api.save_data(CACHE_KEY, _cache)


def favourites():
    return [dict(a) for a in _settings["favourites"]]


def auto_airport():
    """The nearest airport found for the current place, or None."""
    auto = _settings.get("auto")
    location = place_location()
    if auto and location and api.same_place(auto["for"], api.for_point(location)):
        return {"icao": auto["icao"], "name": auto["name"], "auto": True,
                "city": location["name"]}
    return None


def airports():
    """What the airport list shows: the favourites, or else the nearest one."""
    if _settings["favourites"]:
        return [dict(a, auto=False) for a in _settings["favourites"]]
    auto = auto_airport()
    return [auto] if auto else []


def default_airport():
    """The first favourite, else the airport nearest to the place (once
    found), else None."""
    listed = airports()
    return listed[0] if listed else None


def metar_entry(icao):
    return _cache["metar"].get(icao)


def taf_entry(icao):
    return _cache["taf"].get(icao)


def is_loading():
    return _running is not None or bool(_queue)


def requests_paused():
    """True while requests wait after errors (see cockpit_api.Backoff)."""
    return _backoff.blocked(_now())


# ------------------------------------------------------------
# Requests: one at a time, on a worker thread
# ------------------------------------------------------------

def _job_metar(ids):
    return api.fetch_metars(ids)


def _job_taf(ids):
    return api.fetch_tafs(ids)


def _job_box(box):
    return api.fetch_box(box)


def _job_station(icao):
    return api.fetch_station(icao)


_JOBS = {"metar": _job_metar, "taf": _job_taf, "box": _job_box, "station": _job_station}


def _submit(kind, arg, callback=None):
    """Queue a request; callback(result, error) runs on the UI thread when it
    ends (error None on success). The same request already waiting or running
    gets the callback instead. While requests pause after errors, the callback
    gets the last error right away (no request). Returns whether the callback
    will be called."""
    key = (kind, tuple(arg) if isinstance(arg, (list, tuple)) else arg)
    for job in ([_running] if _running else []) + _queue:
        if job["key"] == key:
            if callback is not None:
                job["callbacks"].append(callback)
            return True
    if not _active:
        return False
    if _backoff.blocked(_now()):
        if callback is None:
            return False
        wx.CallAfter(callback, None, _backoff.last_error or "offline")
        return True
    _queue.append({"kind": kind, "key": key, "arg": arg,
                   "callbacks": [callback] if callback is not None else []})
    _pump()
    return True


def _pump():
    global _running
    if _running is not None or not _queue or not _active:
        return
    _running = _queue.pop(0)
    _start_thread(_worker, _running)


def _worker(job):
    # Worker thread: the network only, never wx objects or the settings.
    global _last_request
    wait = _last_request + api.MIN_GAP_SECONDS - time.time()
    if wait > 0:
        _sleep(wait)
    _last_request = time.time()
    result, error = None, None
    try:
        result = _JOBS[job["kind"]](job["arg"])
    except api.AviationError as e:
        error = e.kind
        logger.info(f"[Cockpit] Request failed: {e}")
    except Exception:
        error = "bad_response"
        logger.exception("[Cockpit] Request failed")
    wx.CallAfter(_on_job_done, job, result, error)


def _on_job_done(job, result, error):
    global _running
    _running = None
    now = _now()
    if error:
        _backoff.failed(error, now)
    else:
        _backoff.succeeded()
        if job["kind"] == "metar":
            api.store_metars(_cache, job["arg"], result, now)
            _save_cache()
        elif job["kind"] == "taf":
            api.store_tafs(_cache, job["arg"], result, now)
            _save_cache()
    if not _active:
        del _queue[:]
        return
    for callback in job["callbacks"]:
        try:
            callback(result, error)
        except Exception:
            logger.exception("[Cockpit] Request callback failed")
    _pump()


def request_metar(ids, callback=None, force=False):
    """Fetch the METARs of `ids` that are older than 10 minutes (all with
    `force`). Returns False when nothing needed fetching (or, without a
    callback, when requests are paused); `callback` then isn't called."""
    ids = [i for i in ids if force or api.needs_fetch(_cache, "metar", i, METAR_FRESH, _now())]
    if not ids:
        return False
    return _submit("metar", tuple(ids), callback)


def request_taf(ids, callback=None, force=False):
    ids = [i for i in ids if force or api.needs_fetch(_cache, "taf", i, TAF_FRESH, _now())]
    if not ids:
        return False
    return _submit("taf", tuple(ids), callback)


def find_nearest(callback):
    """Find the airport with a METAR nearest to the place: a box of about
    110 km around it, then 330 km. callback(airport, error) on the UI thread;
    error "none_near" when there is none, "no_location" without a place."""
    location = place_location()
    if not location:
        callback(None, "no_location")
        return

    def attempt(index):
        box = metar.search_box(location["latitude"], location["longitude"],
                               api.BOX_DEGREES[index])

        def done(reports, error):
            if error:
                callback(None, error)
                return
            report, km = metar.nearest_station(list(reports.values()),
                                               location["latitude"], location["longitude"])
            if report is None:
                if index + 1 < len(api.BOX_DEGREES):
                    attempt(index + 1)
                else:
                    callback(None, "none_near")
                return
            now = _now()
            _cache["metar"][report["icao"]] = {"fetched_at": now, "report": report}
            _cache["no_metar"].pop(report["icao"], None)
            _save_cache()
            _settings["auto"] = {"icao": report["icao"], "name": report["name"],
                                 "km": round(km, 1), "for": api.for_point(location)}
            _save_settings()
            callback(auto_airport(), None)

        _submit("box", box, done)

    attempt(0)


# ------------------------------------------------------------
# Favourites (acted on at once, from the Preferences page or the window)
# ------------------------------------------------------------

def validate_airport(code, callback):
    """Check an ICAO code by fetching its weather, then add it to the
    favourites. callback(airport or None, problem, has_report) on the UI
    thread; problem is None, "not_icao", "already", "too_many", "unknown" or a
    request error."""
    icao = metar.normalize_icao(code)
    if not icao:
        callback(None, "not_icao", False)
        return
    for airport in _settings["favourites"]:
        if airport["icao"] == icao:
            callback(dict(airport), "already", False)
            return
    if len(_settings["favourites"]) >= api.MAX_FAVOURITES:
        callback(None, "too_many", False)
        return

    def after_station(station, error):
        if error:
            callback(None, error, False)
        elif not station:
            callback(None, "unknown", False)
        else:
            callback(_add_favourite(icao, station["name"]), None, False)

    def after_metar(result, error):
        if error:
            callback(None, error, False)
            return
        report = (result or {}).get(icao)
        if report:
            callback(_add_favourite(icao, report["name"]), None, True)
        else:
            _submit("station", icao, after_station)

    _submit("metar", (icao,), after_metar)


def _add_favourite(icao, name):
    if not any(a["icao"] == icao for a in _settings["favourites"]):
        _settings["favourites"].append({"icao": icao, "name": name})
        _save_settings()
    return {"icao": icao, "name": name}


def remove_favourite(icao):
    before = len(_settings["favourites"])
    _settings["favourites"] = [a for a in _settings["favourites"] if a["icao"] != icao]
    if len(_settings["favourites"]) != before:
        _save_settings()
        return True
    return False


def make_default(icao):
    """Move a favourite to the top of the list. Returns False if it already
    was the default or isn't a favourite."""
    items = _settings["favourites"]
    index = next((i for i, a in enumerate(items) if a["icao"] == icao), -1)
    if index <= 0:
        return False
    items.insert(0, items.pop(index))
    _save_settings()
    return True


# ------------------------------------------------------------
# Hotkey actions
# ------------------------------------------------------------

def speak_pilot_weather():
    """Speak the decoded METAR of the default airport; with no favourites,
    find the airport nearest to the place first and say so."""
    airport = default_airport()
    if airport is not None:
        _speak_airport(airport)
        return
    location = place_location()
    if not location:
        speak(_("no_airport"), interrupt=True)
        return
    speak(_("finding_nearest", city=location["name"]), interrupt=True)
    find_nearest(_after_nearest)


def _after_nearest(airport, error):
    location = place_location()
    city = location["name"] if location else ""
    if error == "none_near":
        speak(_("nearest_none", city=city), interrupt=True)
    elif error == "no_location":
        speak(_("no_airport"), interrupt=True)
    elif error or airport is None:
        speak(text.error_text(error), interrupt=True)
    else:
        full, _short = text.names(airport)
        entry = metar_entry(airport["icao"])
        intro = _("nearest_chosen", name=full, code=text.spell(airport["icao"], is_captain()),
                  city=city)
        speech = text.metar_speech(airport, entry["report"], is_captain(), _settings["raw"],
                                   _now()) if entry else ""
        speak(" ".join(p for p in (intro, speech) if p), interrupt=True)


def _speak_airport(airport):
    icao = airport["icao"]
    now = _now()
    entry = metar_entry(icao)
    if entry and api.is_fresh(entry["fetched_at"], METAR_FRESH, now):
        speak(_metar_speech(airport, entry), interrupt=True)
        return
    if not api.needs_fetch(_cache, "metar", icao, METAR_FRESH, now):
        _speak_after_fetch(airport, None)     # asked recently: no report then
        return
    if not requests_paused():
        speak(_("fetching"), interrupt=True)
    request_metar([icao], lambda result, error: _speak_after_fetch(airport, error))


def _metar_speech(airport, entry):
    return text.metar_speech(airport, entry["report"], is_captain(), _settings["raw"], _now())


def _speak_after_fetch(airport, error):
    icao = airport["icao"]
    now = _now()
    entry = metar_entry(icao)
    name = text.names(airport)[0]
    if error is None and entry and api.is_fresh(entry["fetched_at"], METAR_FRESH, now):
        speak(_metar_speech(airport, entry), interrupt=True)
        return
    stale = entry and api.is_fresh(entry["fetched_at"], STALE_MAX_AGE, now)
    first = _("no_report", name=name) if error is None else text.error_text(error)
    if stale:
        speak(" ".join([first, _("stale_notice", time=text.time_text(entry["fetched_at"])),
                        _metar_speech(airport, entry)]), interrupt=True)
    else:
        speak(first, interrupt=True)


def show_airport_weather():
    """Open the Airport weather window (the airports, their decoded METAR and
    TAF, and the raw codes)."""
    global _dialog
    if _dialog:
        _dialog.Raise()
        return
    location = place_location()
    if not airports() and location:
        # Nothing to list yet: find the nearest airport first, then open.
        speak(_("finding_nearest", city=location["name"]), interrupt=True)

        def opened(airport, error):
            if error and error not in ("none_near", "no_location"):
                speak(text.error_text(error), interrupt=True)
            elif error == "none_near":
                speak(_("nearest_none", city=location["name"]), interrupt=True)
            _open_dialog()

        find_nearest(opened)
        return
    _open_dialog()


def _open_dialog():
    global _dialog
    if _dialog:
        return
    parent = getattr(core.api, "main_window_instance", None)
    dlg = cockpit_ui.AirportWeatherDialog(parent, WindowActions)
    _dialog = dlg
    try:
        dlg.ShowModal()
    finally:
        _dialog = None
        dlg.Destroy()


class WindowActions:
    """What the Airport weather window and the Preferences page may do."""

    @staticmethod
    def airports():
        return airports()

    @staticmethod
    def default_icao():
        airport = default_airport()
        return airport["icao"] if airport else None

    @staticmethod
    def captain():
        return is_captain()

    @staticmethod
    def metar(icao):
        return metar_entry(icao)

    @staticmethod
    def taf(icao):
        return taf_entry(icao)

    @staticmethod
    def no_metar(icao):
        return api.is_fresh(_cache["no_metar"].get(icao), METAR_FRESH, _now())

    @staticmethod
    def no_taf(icao):
        return icao in _cache["no_taf"] and icao not in _cache["taf"]

    @staticmethod
    def loading():
        return is_loading()

    @staticmethod
    def refresh(callback, force=False):
        """Fetch what is stale for every listed airport: one METAR request and
        one TAF request. callback(error) once both ended. Returns False when
        everything is fresh (callback not called)."""
        ids = [a["icao"] for a in airports()]
        # "left" starts at 1 while the requests are handed out, so an answer
        # that comes at once (a pause after errors) can't end it early.
        state = {"left": 1, "error": None}

        def one_done(_result, error):
            state["error"] = state["error"] or error
            state["left"] -= 1
            if state["left"] == 0:
                callback(state["error"])

        started = 0
        for request in (request_metar, request_taf):
            state["left"] += 1
            if request(ids, one_done, force):
                started += 1
            else:
                state["left"] -= 1
        if not started:
            return False
        one_done(None, None)
        return True

    add = staticmethod(validate_airport)
    remove = staticmethod(remove_favourite)
    make_default = staticmethod(make_default)
    auto = staticmethod(auto_airport)


# ------------------------------------------------------------
# Captain mode
# ------------------------------------------------------------

def _captain_word():
    return _("captain_word")


def cockpit_greeting():
    """The cockpit greeting in the UI language (raw, with its placeholders)."""
    return _("cockpit_greeting")


def _is_cockpit_greeting(greeting):
    # Either language's version counts, in case the language changed since.
    return greeting.strip() in _cockpit_greetings()


def _cockpit_greetings():
    import json
    import os
    found = set()
    locales = os.path.join(text.EXT_DIR, "locales")
    for code in ("en", "id"):
        try:
            with open(os.path.join(locales, f"{code}.json"), encoding="utf-8") as f:
                found.add(json.load(f)["messages"]["cockpit_greeting"].strip())
        except (OSError, ValueError, KeyError):
            pass
    found.add(cockpit_greeting().strip())
    return found


def _example_greeting(template):
    extra = {PLACEHOLDER: placeholder_text() or ""}
    return core.personal.tidy_spoken(core.personal.expand(template, extra, unknown=""))


def captain_turned_on():
    """Offer to call the user Captain (when they have no title yet), then to
    set the cockpit greeting; start keeping the airport weather fresh."""
    word = _captain_word()
    if not core.personal.get_title():
        nickname = core.personal.get_nickname()
        example = core.personal.greeting(title=word, nickname=nickname)
        if _ask_yes_no(_("offer_title", title=word, example=example)):
            core.personal.set_title(word)
    custom = core.personal.get_custom_greeting()
    if not _is_cockpit_greeting(custom["text"]):
        example = _example_greeting(cockpit_greeting())
        if _ask_yes_no(_("offer_greeting", example=example)):
            core.personal.set_custom_greeting(cockpit_greeting(), custom["boot_only"])
    _background_refresh(force=True)


def captain_turned_off():
    """Offer to take back what turning Captain mode on set, if it is unchanged."""
    title = core.personal.get_title()
    words = {"Captain", "Kapten", _captain_word()}
    if title in words and _ask_yes_no(_("offer_clear_title", title=title)):
        core.personal.set_title("")
    custom = core.personal.get_custom_greeting()
    if _is_cockpit_greeting(custom["text"]) and _ask_yes_no(_("offer_clear_greeting")):
        core.personal.set_custom_greeting("", custom["boot_only"])


def apply_settings(new_settings, offers=True):
    """Save the Preferences page's options; turning Captain mode on or off
    makes its offers (unless `offers` is False)."""
    was_captain = _settings["captain"]
    for key in ("captain", "raw", "briefing"):
        if key in new_settings:
            _settings[key] = bool(new_settings[key])
    moved = False
    if "place" in new_settings:
        place = api.normalize_settings({"place": new_settings["place"]})["place"]
        moved = place != _settings.get("place")
        _settings["place"] = place
    _save_settings()
    if moved:
        _place_moved()
    if not offers:
        return
    if _settings["captain"] and not was_captain:
        captain_turned_on()
    elif was_captain and not _settings["captain"]:
        captain_turned_off()


# ------------------------------------------------------------
# Background refresh (Captain mode only)
# ------------------------------------------------------------

def _background_refresh(force=False):
    """Refresh the default airport's METAR and TAF when older than 30 minutes,
    at most every 30 minutes (longer after failures). Only in Captain mode."""
    global _last_background
    if not (_active and _settings["captain"]):
        return False
    now = _now()
    if requests_paused() or is_loading():
        return False
    if not force and now - _last_background < _backoff.background_gap():
        return False
    airport = default_airport()
    if airport is None:
        if place_location():
            _last_background = now
            find_nearest(lambda _airport, _error: None)
            return True
        return False
    icao = airport["icao"]
    started = False
    if api.needs_fetch(_cache, "metar", icao, BACKGROUND_FRESH, now):
        started = request_metar([icao], force=True) or started
    if api.needs_fetch(_cache, "taf", icao, BACKGROUND_FRESH, now):
        started = request_taf([icao], force=True) or started
    if started:
        _last_background = now
    return started


# ------------------------------------------------------------
# Events: the Briefing, the evening summary, %airportweather%
# ------------------------------------------------------------

def _recent_report(airport, now=None):
    entry = metar_entry(airport["icao"]) if airport else None
    if entry and api.is_fresh(entry["report"]["obs_time"], BRIEFING_MAX_AGE,
                              _now() if now is None else now):
        return entry["report"]
    return None


def placeholder_text():
    """%airportweather%: "Hang Nadim: wind from 200 degrees at 6 knots, ...,
    QNH 1013" from the cache, or "" without a recent report."""
    airport = default_airport()
    report = _recent_report(airport)
    return text.short_line(airport, report) if report else ""


def _on_briefing_collect(lines):
    # Briefing contract: fast, cache only, append nothing without data.
    airport = default_airport()
    report = _recent_report(airport)
    if not report:
        return
    if _settings["captain"]:
        sentence = text.briefing_captain(airport, report)
    elif _settings["briefing"] and _settings["favourites"]:
        sentence = text.briefing_short(airport, report)
    else:
        return
    if sentence:
        lines.append(sentence)


def _on_evening_collect(lines):
    # Same contract: tomorrow's TAF headline for the default airport, in Captain mode.
    if not _settings["captain"]:
        return
    airport = default_airport()
    entry = taf_entry(airport["icao"]) if airport else None
    if not entry or not api.is_fresh(entry["fetched_at"], EVENING_TAF_AGE, _now()):
        return
    sentence = text.evening_line(airport, entry["report"])
    if sentence:
        lines.append(sentence)


def _on_app_startup(*_args, **_kwargs):
    _background_refresh(force=True)


def _on_minute_tick(*_args, **_kwargs):
    _background_refresh()


def _on_network_changed(online=True, *_args, **_kwargs):
    # Back online after failures (a start with Windows, say): try again now,
    # so the greeting and the Briefing have the weather.
    if online and _backoff.failures and _backoff.last_error == "offline":
        _backoff.succeeded()
        _background_refresh(force=True)


def _place_moved():
    """The place for the nearest airport may have changed: the settings page
    shows the airports again, and Captain mode keeps the new one fresh."""
    if _panel:
        try:
            _panel.refresh()
        except RuntimeError:
            pass  # panel already destroyed
    if _settings["captain"] and not _settings["favourites"] and auto_airport() is None:
        _background_refresh(force=True)


def _on_places_changed(*_args, **_kwargs):
    """The places changed (Preferences, Places)."""
    if _panel:
        try:
            _panel.refresh_places()
        except RuntimeError:
            pass  # panel already destroyed
    _place_moved()


_SUBSCRIPTIONS = (
    ("on_app_startup", _on_app_startup),
    ("on_minute_tick", _on_minute_tick),
    ("on_network_changed", _on_network_changed),
    ("on_briefing_collect", _on_briefing_collect),
    ("on_evening_collect", _on_evening_collect),
    ("on_places_changed", _on_places_changed),
)


# ------------------------------------------------------------
# The Cockpit sound theme
# ------------------------------------------------------------

def sound_themes_state():
    """"loaded", "disabled" or "missing": the Sound Themes extension."""
    from core import extension_manager
    if "sound_themes" in extension_manager.LOADED_EXTENSIONS:
        return "loaded"
    try:
        for info in extension_manager.get_installed_extensions_info():
            if info.get("id") == "sound_themes":
                return "disabled"
    except Exception:
        logger.exception("[Cockpit] Could not list the installed extensions")
    return "missing"


def _theme_check():
    """Sound Themes' own WAV check, when it is loaded."""
    import sys
    store = sys.modules.get("sound_themes_store")
    return getattr(store, "check_wav_data", None)


def install_sound_theme(done):
    """Write the Cockpit theme into the Sound Themes folder on a worker thread;
    done(message) on the UI thread. Says so when Sound Themes isn't there."""
    state = sound_themes_state()
    if state != "loaded":
        done(_("theme_disabled" if state == "disabled" else "theme_no_extension"))
        return False
    root = sounds.themes_root(core.api.USER_DATA_DIR)
    check = _theme_check()

    def work():
        try:
            sounds.install_theme(root, stop_sound=core.sounds.stop_sound, check=check)
            message = _("theme_installed")
        except Exception:
            logger.exception("[Cockpit] Could not write the sound theme")
            message = _("theme_failed")
        wx.CallAfter(_theme_done, done, message)

    _start_thread(work)
    return True


def _theme_done(done, message):
    # Show the new theme on the Sound Themes page if it is already built.
    try:
        from core import extension_manager
        module = extension_manager.LOADED_EXTENSIONS.get("sound_themes", {}).get("module")
        panel = getattr(module, "_panel", None)
        if panel:
            panel.refresh()
    except Exception:
        pass
    done(message)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    _panel = cockpit_ui.CockpitPanel(parent, get_settings(), WindowActions,
                                     install_sound_theme)
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

def register(bus):
    global _bus, _active, _settings, _cache, _backoff, _running, _last_background
    global _last_request, _panel, _dialog
    _bus = bus
    _active = True
    _running = None
    _last_background = 0.0
    _last_request = 0.0
    _panel = _dialog = None
    del _queue[:]
    _backoff = api.Backoff()
    _settings = api.normalize_settings(core.api.load_data(DATA_KEY))
    _cache = api.normalize_cache(core.api.load_data(CACHE_KEY))

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # Q ("QNH", the pilot's altimeter setting) and Shift+Q. M, for METAR, is
    # taken: the store's Date Calculator uses M, Hariku uses Ctrl+M, Markdown
    # Reader Ctrl+Shift+M, Routines Alt+M. Plain Q and Shift+Q are free in the
    # core (Ctrl+Q quits), every bundled and store extension (Window Teleporter
    # only uses Q with Ctrl or Alt) and the saved key bindings.
    core.hotkeys.register_action(EXT_NAME, "pilot_weather", _("action_pilot"),
                                 ord("Q"), False, speak_pilot_weather)
    core.hotkeys.register_action(EXT_NAME, "airport_weather", _("action_airports"),
                                 ord("Q"), False, show_airport_weather, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    core.personal.register_placeholder(PLACEHOLDER, placeholder_text, _("placeholder_desc"))
    logger.info("Cockpit extension loaded.")


def teardown():
    global _active, _panel, _dialog
    _active = False
    _panel = _dialog = None
    del _queue[:]
    try:
        core.personal.unregister_placeholder(PLACEHOLDER)
    except Exception:
        pass
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _bus.unsubscribe(event_name, handler)
            except Exception:
                pass
    logger.info("Cockpit extension unloaded.")
