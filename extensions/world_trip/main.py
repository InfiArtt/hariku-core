# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
World Trip — Hariku V2 extension ("Keliling Dunia" in Indonesian).

Ask Aruna "bawa aku ke Tokyo", "take me to Japan", "terbang ke Paris" or
"take me anywhere": a cabin chime and the captain's announcement (distance
and flight time from your main place), the engines, then the arrival with the
local time and weather, a greeting in the local language spoken by a native
voice, and local radio playing quietly. There you can ask about the city
(Wikipedia), learn a phrase, change the station, ask the time or where you
are, and fly home.

  world_trip_places.py   - what was asked -> a destination; distance and flight time
  world_trip_phrases.py  - greetings and phrases in 31 languages; which language a place speaks
  world_trip_text.py     - what is said, in English and Indonesian
  world_trip_net.py      - the weather (Open-Meteo) and Wikipedia summaries, a small cache
  world_trip_stations.py - Radio Browser: finding and ranking stations
  world_trip_radio.py    - the stream player (Media Foundation, reusable)
  world_trip_voices.py   - which Hariku Voice voice speaks each language
  world_trip_keys.py     - "any key skips the flight" without a keyboard hook
  world_trip_trip.py     - the trip itself (no wx; tested with fakes)
  world_trip_ui.py       - the Preferences page
  world_trip_sounds.py   - makes sounds/chime.wav and sounds/engine.wav

Privacy: only the destination (its name, its country code, its point rounded
to about 1 km) goes to Open-Meteo, Wikipedia and Radio Browser. The distance
from your main place is worked out on this computer.
"""

import datetime
import logging
import os
import threading
import time
import wave

import wx

import core.api
import core.commands
import core.hotkeys
import core.personal
import core.places
import core.preferences
import core.sounds
import core.voice
from core.commands import Reply

import world_trip_keys as keys
import world_trip_net as net
import world_trip_phrases as phrases
import world_trip_places as places
import world_trip_radio as radio
import world_trip_stations as stations
import world_trip_text as texts
import world_trip_trip as trips
import world_trip_ui
import world_trip_voices as voices
from world_trip_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "World Trip"          # fixed, so saved hotkeys survive a language change
DATA_KEY = "WorldTrip"
CACHE_KEY = "WorldTripCache"
EXT_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(EXT_DIR, "sounds")
TRIP_INTENT = f"{EXT_NAME}.go"
ABOUT_INTENT = f"{EXT_NAME}.about"
WHERE_INTENT = f"{EXT_NAME}.where"
MAX_QUERY_LENGTH = 80
DUCK_MS = 150
SUMMARY_MAX_AGE = 7 * 24 * 3600
STATIONS_MAX_AGE = 24 * 3600

DEFAULT_SETTINGS = {"departure": True, "engine": True, "radio": True, "radio_volume": 35,
                    "native_voices": True, "trips": 0}

TRIP_PATTERNS = (
    "bawa aku ke {text}", "bawa saya ke {text}", "terbang ke {text}", "jalan-jalan ke {text}",
    "kunjungi {text}", "liburan ke {text}", "wisata ke {text}", "antar aku ke {text}",
    "ajak aku ke {text}",
    "take me to {text}", "fly me to {text}", "fly to {text}", "travel to {text}",
    "visit {text}", "let's go to {text}", "trip to {text}",
)
ABOUT_PATTERNS = ("ceritakan tentang {text}", "ceritakan soal {text}", "tell me about {text}")
# "di mana aku": both "di" and "aku" are words Aruna ignores in a command, so as a
# command it would be only "mana", like Space's "di mana ISS". As a command with
# content it is "di mana" + who.
WHERE_PATTERNS = ("di mana {text}", "{text} di mana", "{text} sedang di mana",
                  "{text} lagi di mana")
WHO_WORDS = ("aku", "saya", "kita", "gue", "gw", "aku sekarang", "kita sekarang",
             "saya sekarang")


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = dict(DEFAULT_SETTINGS)
    for key in ("departure", "engine", "radio", "native_voices"):
        if isinstance(raw.get(key), bool):
            settings[key] = raw[key]
    try:
        settings["radio_volume"] = max(0, min(100, int(raw.get("radio_volume",
                                                               DEFAULT_SETTINGS["radio_volume"]))))
    except (TypeError, ValueError):
        pass
    try:
        settings["trips"] = max(0, int(raw.get("trips", 0)))
    except (TypeError, ValueError):
        pass
    return settings


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

_bus = None
_active = False
_settings = normalize_settings(None)
_manager = None
_services = None
_panel = None
_duck_timer = None
_cache_lock = threading.Lock()
_cache = {"summaries": net.Cache(SUMMARY_MAX_AGE, 40), "stations": net.Cache(STATIONS_MAX_AGE, 30)}


def _save_settings():
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(_settings)
    core.api.save_data(DATA_KEY, data)


def _save_cache():
    with _cache_lock:
        data = {name: cache.to_dict() for name, cache in _cache.items()}
    core.api.save_data(CACHE_KEY, data)


def _load_cache():
    data = core.api.load_data(CACHE_KEY)
    data = data if isinstance(data, dict) else {}
    with _cache_lock:
        for name, cache in _cache.items():
            cache.load(data.get(name))


def _call_after(fn, *args):
    try:
        if _active and wx.GetApp() is not None:
            wx.CallAfter(fn, *args)
    except Exception:
        pass


def _sound_path(name):
    return os.path.join(SOUNDS_DIR, f"{name}.wav")


_durations = {}


def _duration(name):
    if name not in _durations:
        try:
            with wave.open(_sound_path(name)) as w:
                _durations[name] = w.getnframes() / float(w.getframerate())
        except Exception:
            _durations[name] = 0.0
    return _durations[name]


# ------------------------------------------------------------
# What a trip uses from Hariku (world_trip_trip.Services)
# ------------------------------------------------------------

class _Timer:
    def __init__(self, timer):
        self._timer = timer

    def cancel(self):
        try:
            self._timer.Stop()
        except Exception:
            pass


class _Radio:
    """The player, starting the ducking timer when a station plays."""

    def __init__(self, player):
        self.player = player

    def play(self, url, volume=None, on_event=None):
        _start_ducking()
        return self.player.play(url, volume=volume, on_event=on_event)

    def stop(self):
        self.player.stop()

    def set_volume(self, volume):
        self.player.set_volume(volume)

    def set_ducked(self, ducked):
        self.player.set_ducked(ducked)

    def is_active(self):
        return self.player.is_active()


class Services:
    def __init__(self):
        self.player = radio.RadioPlayer()
        self.radio = _Radio(self.player)
        self.browser = stations.RadioBrowser()
        self.voices = voices.VoiceBook(
            lambda: [p["id"] for p in core.voice.get_providers()],
            core.voice.is_provider_available, core.voice.list_voices)

    # --- time and threads -------------------------------------------------------------

    def utcnow(self):
        return datetime.datetime.now(datetime.timezone.utc)

    def monotonic(self):
        return time.monotonic()

    def call_later(self, seconds, fn):
        return _Timer(wx.CallLater(max(1, int(seconds * 1000)), fn))

    def call_after(self, fn, *args):
        _call_after(fn, *args)

    def run(self, work, done):
        def target():
            result, error = None, None
            try:
                result = work()
            except Exception as e:           # reported to done(); expected ones are logged there
                error = e
                if not isinstance(e, (places.ResolveError, net.NetError, stations.StationError)):
                    logger.exception("[World Trip] A request failed")
            _call_after(done, result, error)
        threading.Thread(target=target, daemon=True, name="world-trip-fetch").start()

    # --- speech and sounds -------------------------------------------------------------

    def say(self, text, interrupt=False):
        return core.voice.announce(text, "command", interrupt=interrupt)

    def voice_busy(self):
        return core.voice.is_speaking()

    def stop_voice(self):
        core.voice.stop()

    def speak_native(self, text, voice, on_done):
        volume = core.voice.get_settings().get("volume", 100)
        return core.voice.preview(text, voice["provider"], voice["id"], rate=0, volume=volume,
                                  stop_on_key=True, on_done=on_done)

    def show(self, text):
        if hasattr(core.commands, "show_answer"):
            core.commands.show_answer(text)

    def hold(self, seconds):
        if hasattr(core.commands, "hold_answer"):
            core.commands.hold_answer(seconds)

    def play_sound(self, name):
        return _duration(name) if core.sounds.play_sound(_sound_path(name)) else 0.0

    def stop_sound(self, name):
        try:
            core.sounds.stop_sound(_sound_path(name))
        except Exception:
            pass

    def key_watch(self):
        return keys.KeyWatch()

    def has_provider(self, provider_id):
        return any(p["id"] == provider_id for p in core.voice.get_providers())

    def radio_supported(self):
        return radio.is_supported()

    # --- settings and the user ------------------------------------------------------------

    def settings(self):
        return dict(_settings)

    def save_radio_volume(self, volume):
        _settings["radio_volume"] = int(volume)
        _save_settings()

    def hariku_volume(self, step):
        (core.sounds.volume_up if step > 0 else core.sounds.volume_down)()

    def home(self):
        return places.home_from_place(core.places.get_main())

    def addressed(self):
        return core.personal.get_addressed_name() if core.personal.get_title() else ""

    def count_trip(self):
        _settings["trips"] = _settings.get("trips", 0) + 1
        _save_settings()

    def trips_taken(self):
        return _settings.get("trips", 0)

    # --- the network (worker threads) --------------------------------------------------------

    def resolve(self, text, avoid=None):
        return places.resolve(text, texts.user_language(), avoid=avoid)

    def localized_name(self, dest, code):
        return places.localized_name(dest, code)

    def weather(self, dest):
        return net.weather(dest)

    def native_voice(self, code, country_code):
        return self.voices.for_language(code, country_code)

    def stations(self, dest, names):
        key = net.point_key(dest, f"{dest.get('country_code', '')}:")
        with _cache_lock:
            found = _cache["stations"].get(key)
        if found is not None:
            return found
        found = self.browser.stations_for(dest, [n for n in names if n])
        with _cache_lock:
            _cache["stations"].put(key, found)
        _call_after(_save_cache)
        return found

    def summary(self, dest, names, english_names):
        language = texts.user_language()
        key = net.point_key(dest, f"{language}:")
        with _cache_lock:
            found = _cache["summaries"].get(key)
        if found is not None:
            return found
        found = net.city_summary(dest, language, names, english_names)
        with _cache_lock:
            _cache["summaries"].put(key, found)
        _call_after(_save_cache)
        return found

    def country_summary(self, country):
        language = texts.user_language()
        key = f"{language}:country:{phrases.normalize(country)}"
        with _cache_lock:
            found = _cache["summaries"].get(key)
        if found is not None:
            return found
        found = net.country_summary(country, language)
        with _cache_lock:
            _cache["summaries"].put(key, found)
        _call_after(_save_cache)
        return found

    def count_click(self, uuid):
        self.browser.count_click(uuid)


# ------------------------------------------------------------
# The radio's volume while something is said
# ------------------------------------------------------------

def _start_ducking():
    global _duck_timer
    if _duck_timer is None and _active:
        _duck_timer = core.api.set_interval(DUCK_MS, _duck_tick)


def _stop_ducking():
    global _duck_timer
    timer, _duck_timer = _duck_timer, None
    if timer is not None:
        try:
            timer.Stop()
        except Exception:
            pass


def _duck_tick():
    if _manager is None or not _services.radio.is_active():
        _stop_ducking()
        return
    _manager.duck_tick()


def _on_before_speak(payload, *args, **kwargs):
    # Any thread. Only a note of when speech is likely to end.
    if _manager is not None and isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            _manager.note_speech(text)


# ------------------------------------------------------------
# Aruna: commands with content, actions
# ------------------------------------------------------------

def _is_a_reminder(text):
    """ "bawa aku ke dokter besok jam 9" is a reminder, not a trip."""
    try:
        import core.quick_reminder
        return core.commands.strong_when(core.quick_reminder.parse_text(text))
    except Exception:
        return False


def _defer(fn, *args):
    """Run fn a moment later, once Aruna waits for the answer (Reply(wait=True)),
    so everything it says lands in Last result."""
    try:
        wx.CallAfter(fn, *args)
    except Exception:
        logger.exception("[World Trip] Could not run a command")


def _on_trip_intent(request):
    text = " ".join(str(request.text or "").split()).strip(" \t.,!?;:\"'")
    if not text or len(text) > MAX_QUERY_LENGTH or _manager is None:
        return None
    kind = places.parse_query(text)["kind"]
    if kind == "empty":
        return None
    if kind != "home" and _is_a_reminder(text):
        return None
    _defer(_manager.start, text)
    return Reply(wait=True)


def _on_about_intent(request):
    if _manager is None:
        return None
    target = _manager.about_target(request.text)
    if target is None:
        return None                   # not about this trip: Aruna carries on
    _defer(_manager.about, target)
    return Reply(wait=True)


def _on_where_intent(request):
    if _manager is None or phrases.normalize(request.text) not in WHO_WORDS:
        return None                   # "di mana ISS" is Space's
    _defer(_manager.where_am_i)
    return Reply(wait=True)


def _action(fn):
    def run():
        if _manager is not None:
            fn()
    return run


ACTIONS = (
    ("next_station", "action_next_station", "title_next_station",
     lambda: _manager.next_station(),
     ("ganti stasiun", "stasiun berikutnya", "stasiun lain", "ganti radio", "radio lain",
      "next station", "change station", "another station", "next radio station")),
    ("radio_louder", "action_louder", "title_louder",
     lambda: _manager.change_volume(trips.VOLUME_STEP),
     ("keraskan", "keraskan radio", "radio lebih keras", "besarkan radio",
      "radio louder", "turn the radio up", "louder radio")),
    ("radio_quieter", "action_quieter", "title_quieter",
     lambda: _manager.change_volume(-trips.VOLUME_STEP),
     ("kecilkan", "kecilkan radio", "pelankan radio", "radio lebih pelan",
      "radio quieter", "turn the radio down", "quieter radio")),
    ("about_city", "action_about", "title_about",
     lambda: _manager.about("city"),
     ("ceritakan tentang kota ini", "ceritakan kota ini", "tentang kota ini",
      "tell me about this city", "about this city", "tell me about this place")),
    ("teach_phrase", "action_phrase", "title_phrase",
     lambda: _manager.teach_phrase(),
     ("ajari aku satu kalimat", "ajari aku kalimat", "ajari satu kalimat", "kalimat baru",
      "ajari aku", "teach me a phrase", "teach me a sentence", "teach me something",
      "another phrase")),
    ("time_there", "action_time", "title_time",
     lambda: _manager.time_there(),
     ("jam berapa di sana", "jam berapa di sini", "sekarang jam berapa di sana",
      "waktu setempat", "what time is it there", "what time is it here", "local time")),
    ("where_am_i", "action_where", "title_where",
     lambda: _manager.where_am_i(),
     ("where am i", "where are we", "posisiku", "lokasiku")),
    ("go_home", "action_home", "title_home",
     lambda: _manager.go_home(),
     ("pulang", "ayo pulang", "bawa aku pulang", "pulang ke rumah",
      "go home", "take me home", "fly home", "let's go home")),
    ("skip_flight", "action_skip", "title_skip",
     lambda: _manager.skip(),
     ("lewati", "lewati penerbangan", "langsung sampai", "langsung mendarat",
      "skip", "skip the flight", "skip flight")),
    ("which_station", "action_station", "title_station",
     lambda: _manager.which_station(),
     ("stasiun apa ini", "radio apa ini", "ini radio apa",
      "what station is this", "which station is this", "which radio station")),
    ("surprise", "action_surprise", "title_surprise",
     lambda: _manager.start("mana saja"),
     ("bawa aku ke mana saja", "jalan-jalan ke mana saja", "kejutkan aku",
      "take me anywhere", "surprise me", "surprise trip", "random trip")),
)


def action_id(name):
    return f"{EXT_NAME}.{name}"


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def voice_lines(voices_by_provider, native_on=True, provider_names=None, user_language=None):
    """The Preferences page's list: which voice each language would use."""
    user = user_language or texts.user_language()
    names = provider_names or {}
    lines = []
    if not native_on:
        lines.append(_("voices_off"))
    for code in sorted(phrases.LANGUAGES, key=lambda c: phrases.language_name(c, user).lower()):
        language = phrases.language_name(code, user)
        voice = voices.pick_for(voices_by_provider, code)
        if voice:
            lines.append(_("voice_line", language=language, voice=voice.get("name") or voice["id"],
                           provider=names.get(voice["provider"], voice["provider"])))
        else:
            lines.append(_("voice_none", language=language))
    if "edge" not in voices_by_provider:
        lines.append(_("voices_hint_edge"))
    return "\n".join(lines)


def _list_voices_for_page(done):
    native_on = _settings["native_voices"]
    names = {p["id"]: p["name"] for p in core.voice.get_providers()}

    def work():
        return voice_lines(_services.voices.voices(), native_on, names)

    def finished(text, error):
        done(text if error is None and text else _("voices_failed"))
    _services.run(work, finished)


def _create_panel(parent):
    global _panel
    _panel = world_trip_ui.WorldTripPanel(parent, dict(_settings), _list_voices_for_page)
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        new = _panel.get_settings()
    except RuntimeError:
        return          # the page is gone
    _settings.update(normalize_settings(dict(_settings, **new)))
    _save_settings()
    if _services is not None:
        _services.player.set_volume(_settings["radio_volume"])
        if not _settings["radio"]:
            _services.player.stop()
        _services.voices.forget()


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def _on_unload(*_args, **_kwargs):
    """Hariku is closing: the radio stops now."""
    if _manager is not None:
        _manager.shutdown()
    if _services is not None:
        _services.player.shutdown(wait=1.0)
    _stop_ducking()


def register(bus):
    global _bus, _active, _settings, _manager, _services, _panel
    _bus = bus
    _active = True
    _panel = None
    _settings = normalize_settings(core.api.load_data(DATA_KEY))
    _load_cache()
    _services = Services()
    _manager = trips.TripManager(_services)

    bus.subscribe("on_before_speak", _on_before_speak)
    bus.subscribe("on_unload", _on_unload)
    core.commands.add_intent(TRIP_INTENT, list(TRIP_PATTERNS), _on_trip_intent,
                             title=_("title_trip"))
    core.commands.add_intent(ABOUT_INTENT, list(ABOUT_PATTERNS), _on_about_intent,
                             title=_("title_about"))
    core.commands.add_intent(WHERE_INTENT, list(WHERE_PATTERNS), _on_where_intent,
                             title=_("title_where"))
    for name, description, title, callback, aliases in ACTIONS:
        core.hotkeys.register_action(EXT_NAME, name, _(description), None, False,
                                     _action(callback))
        core.commands.add_aliases(action_id(name), list(aliases), title=_(title))
    core.commands.add_answer_actions([action_id(name) for name, *_rest in ACTIONS])
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("World Trip extension loaded.")


def teardown():
    global _active, _panel, _manager
    try:
        _on_unload()
    except Exception:
        logger.exception("[World Trip] Stopping failed")
    _active = False
    _panel = None
    _manager = None
    for intent in (TRIP_INTENT, ABOUT_INTENT, WHERE_INTENT):
        try:
            core.commands.remove_intent(intent)
        except Exception:
            pass
    for name, *_rest in ACTIONS:
        try:
            core.commands.remove_aliases(action_id(name))
        except Exception:
            pass
    if _bus is not None:
        for event_name, handler in (("on_before_speak", _on_before_speak),
                                    ("on_unload", _on_unload)):
            try:
                _bus.unsubscribe(event_name, handler)
            except Exception:
                pass
    logger.info("World Trip extension unloaded.")
