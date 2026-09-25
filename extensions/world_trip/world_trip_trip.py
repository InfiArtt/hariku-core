# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The trip: find the place, fly (a cabin chime, the captain's announcement, the
engines), arrive (a chime, the local time and weather), be greeted in the
local language, and listen to local radio while asking about the city,
learning phrases or flying home.

TripManager runs one trip at a time; a new one replaces it. Its narration is
a Script: steps (say this, play that sound, wait for the weather) that run one
after the other, each calling done() when it has finished, so nothing talks
over anything else. Skipping the flight jumps to the "arrival" step; flying
home cancels what is left. Everything outside (speech, sounds, the network,
the radio, timers, settings) goes through a Services object that main.py
fills in and the tests fake, so this module has no wx and does no I/O itself.

Steps and callbacks run on the UI thread; network work runs through
Services.run(work, done), which calls done(result, error) back on it.
"""

import collections
import logging
import random

import world_trip_phrases as phrases
import world_trip_places as places
import world_trip_text as texts
from world_trip_text import _

logger = logging.getLogger(__name__)

PENDING = "pending"               # a fetch that hasn't answered yet
ARRIVAL_WAIT_SECONDS = 6.0        # how long the arrival waits for the weather
GREETING_WAIT_SECONDS = 5.0       # ...and the greeting for the city's name and voice
STATIONS_WAIT_SECONDS = 12.0      # ...and the radio for the station list
HOLD_MARGIN_SECONDS = 15.0        # Aruna's Last result stays open this much longer
RESOLVE_HOLD_SECONDS = 30.0
VOICE_POLL_SECONDS = 0.15
KEY_POLL_SECONDS = 0.2
NATIVE_TIMEOUT_SECONDS = 30.0
MAX_STATION_TRIES = 6
VOLUME_STEP = 10
HINT_TRIPS = 3                    # the first trips end with a hint of what to say
NATIVE_SPEECH_KEYS = ("male", "female")
# The geocoder's language for a city's local name, where it isn't the code's own.
GEOCODER_LANGUAGES = {"yue": "zh", "zh-TW": "zh", "pt-PT": "pt"}


# ------------------------------------------------------------
# The script
# ------------------------------------------------------------

class Script:
    """Steps run one after another. A step is step(done, gen): it starts
    something and calls done() once when it has finished (a callback from an
    older generation, after cancel() or skip_to(), is ignored)."""

    def __init__(self, sv):
        self.sv = sv
        self._steps = collections.deque()
        self._gen = 0
        self._timers = []
        self.running = False
        self.label = None

    @property
    def generation(self):
        return self._gen

    def alive(self, gen):
        return gen == self._gen

    def add(self, step, label=None):
        self._steps.append((label, step))

    def extend(self, steps):
        """Queue more steps and start them if nothing is running."""
        for step in steps:
            self.add(step)
        self.start()

    def start(self):
        if not self.running:
            self.running = True
            self._advance(self._gen)

    def later(self, seconds, fn, gen):
        """fn() after `seconds`, unless the script moved on (cancel, skip)."""
        holder = []

        def fire():
            if holder and holder[0] in self._timers:
                self._timers.remove(holder[0])
            if gen == self._gen:
                fn()
        holder.append(self.sv.call_later(seconds, fire))
        self._timers.append(holder[0])

    def _advance(self, gen):
        while True:
            if gen != self._gen:
                return
            if not self._steps:
                self.running = False
                self.label = None
                return
            label, step = self._steps.popleft()
            self.label = label
            state = {"done": False, "sync": True, "again": False}

            def done(state=state):
                if state["done"]:
                    return
                state["done"] = True
                if state["sync"]:
                    state["again"] = True      # finished at once: loop, don't recurse
                else:
                    self._advance(gen)
            try:
                step(done, gen)
            except Exception:
                logger.exception("[World Trip] A step failed")
                done()
            state["sync"] = False
            if not state["again"]:
                return

    def _cancel_timers(self):
        timers, self._timers = self._timers, []
        for timer in timers:
            try:
                timer.cancel()
            except Exception:
                pass

    def cancel(self):
        self._gen += 1
        self._steps.clear()
        self._cancel_timers()
        self.running = False
        self.label = None

    def has_label(self, label):
        return any(step_label == label for step_label, _step in self._steps)

    def skip_to(self, label):
        """Drop the steps before `label` (and the running one) and go on from
        there. False when no step has that label."""
        if not self.has_label(label):
            return False
        self._gen += 1
        self._cancel_timers()
        while self._steps and self._steps[0][0] != label:
            self._steps.popleft()
        self.running = True
        self._advance(self._gen)
        return True


# ------------------------------------------------------------
# One trip
# ------------------------------------------------------------

class Trip:
    def __init__(self, query):
        self.query = query
        self.phase = "resolving"      # departing, arriving, exploring, homebound, ended
        self.dest = None
        self.home = None
        self.language = None
        self.weather = PENDING
        self.names = PENDING          # {"english", "native": (name, transliteration) or None}
        self.voice = PENDING          # a native voice, or None
        self.stations = PENDING       # [stations] or None (couldn't ask)
        self.station_index = -1
        self.playing = None           # the station on the air
        self.hint_pending = False
        self.phrase_bag = []
        self.noted = False            # the language's note (Thai particles) was said

    def english_name(self):
        return self.names.get("english") if isinstance(self.names, dict) else None

    def native_city(self):
        return self.names.get("native") if isinstance(self.names, dict) else None


def native_names(dest, code, user_language, localized):
    """(name, transliteration) of the destination in language `code`: from
    the built-in table, else the geocoder's name in that language
    (`localized(code)`, which may return None), else, for languages written
    in Latin letters, its English or own name. None when unknown."""
    if code is None:
        return None
    english = dest.get("name_en") or (localized("en") if user_language != "en" else dest["name"])
    names = [dest["name"], dest.get("query"), english]
    found = phrases.native_city(dest.get("country_code"), names, code)
    if found:
        return found, english
    entry = phrases.LANGUAGES[code]
    if code == user_language:
        return (dest["name"], ""), english
    local = localized(GEOCODER_LANGUAGES.get(code, code.split("-")[0]))
    if local:
        local = phrases.trim_native(local, code)
        if entry["latin"] or not phrases.has_latin_letters_only(local):
            return (local, "" if entry["latin"] else (english or dest["name"])), english
    if entry["latin"]:
        return (english or dest["name"], ""), english
    return None, english


class TripManager:
    """Runs the trips; see the module notes."""

    def __init__(self, sv, rng=None):
        self.sv = sv
        self.rng = rng or random.Random()
        self.script = Script(sv)
        self.trip = None
        self.last_surprise = None
        self.speaking_until = 0.0
        self.native_active = False
        self._radio_token = 0
        self._told_unsupported = False
        self._told_edge = False

    # --- what's going on -------------------------------------------------------------

    def active(self):
        return self.trip is not None and self.trip.phase not in ("ended",)

    def at_destination(self):
        trip = self.trip
        return trip is not None and trip.dest is not None and \
            trip.phase in ("arriving", "exploring")

    def flying(self):
        trip = self.trip
        return trip is not None and trip.phase in ("departing", "homebound") and \
            self.script.running

    # --- speaking --------------------------------------------------------------------

    def note_speech(self, text):
        """Something is being said (on_before_speak): the radio stays down
        for about as long as a screen reader takes."""
        self.speaking_until = max(self.speaking_until,
                                  self.sv.monotonic() + texts.speech_seconds(text))

    def should_duck(self):
        return (self.native_active or self.sv.monotonic() < self.speaking_until
                or self.sv.voice_busy())

    def duck_tick(self):
        """Called a few times a second while the radio plays."""
        self.sv.radio.set_ducked(self.should_duck())

    def _speak(self, text, then=None, gen=None, interrupt=False):
        """Say `text` (Hariku Voice for command answers when the user set it
        up) and call then() once it has been said."""
        seconds = texts.speech_seconds(text)
        self.sv.hold(seconds + HOLD_MARGIN_SECONDS)
        self.note_speech(text)
        voiced = self.sv.say(text, interrupt)
        if then is None:
            return
        gen = self.script.generation if gen is None else gen
        if not voiced:
            self.script.later(seconds, then, gen)
            return
        limit = self.sv.monotonic() + seconds * 3 + 10.0

        def check():
            if self.sv.voice_busy() and self.sv.monotonic() < limit:
                self.script.later(VOICE_POLL_SECONDS, check, gen)
            else:
                then()
        self.script.later(0.3, check, gen)

    def say_now(self, text):
        """An answer to a command: said at once."""
        if text:
            self._speak(text, interrupt=True)

    # --- steps -----------------------------------------------------------------------

    def _say_step(self, make_text, interrupt=False):
        def step(done, gen):
            text = make_text() if callable(make_text) else make_text
            if not text:
                done()
                return
            self._speak(text, done, gen, interrupt)
        return step

    def _sound_step(self, name, enabled=lambda: True):
        def step(done, gen):
            if not enabled():
                done()
                return
            seconds = self.sv.play_sound(name)
            if not seconds:
                done()
                return
            self.sv.hold(seconds + HOLD_MARGIN_SECONDS)
            self.script.later(seconds + 0.15, done, gen)
        return step

    def _call_step(self, fn):
        def step(done, gen):
            fn()
            done()
        return step

    def _wait_step(self, ready, seconds):
        def step(done, gen):
            deadline = self.sv.monotonic() + seconds

            def check():
                if ready() or self.sv.monotonic() >= deadline:
                    done()
                else:
                    self.script.later(0.2, check, gen)
            check()
        return step

    def _native_step(self, make_item):
        """Say something in the local language: with its native voice, then
        its meaning in the user's voice; without one, both in the user's."""
        def step(done, gen):
            item = make_item()
            if not item:
                done()
                return
            if item.get("same_language"):
                self._speak(item["native"], done, gen)
                return
            voice = item.get("voice")
            if voice is None:
                self._speak(self._read_out(item), done, gen)
                return
            self.sv.show(item["written"])       # Last result: what the native voice says
            state = {"finished": False}

            def after(error=None):
                if state["finished"] or not self.script.alive(gen):
                    return
                state["finished"] = True
                self.native_active = False
                if error is not None:
                    self._speak(self._read_out(item, hint=False), done, gen)
                else:
                    self._speak(texts.explained(item["spoken"], item["meaning"], item["latin"]),
                                done, gen)

            self.native_active = True
            self.sv.hold(texts.speech_seconds(item["native"]) + HOLD_MARGIN_SECONDS)
            started = self.sv.speak_native(item["native"], voice,
                                           lambda error=None: self.sv.call_after(after, error))
            if not started:
                after(RuntimeError("voice not available"))
                return
            self.script.later(NATIVE_TIMEOUT_SECONDS, lambda: after(TimeoutError()), gen)
        return step

    def _read_out(self, item, hint=True):
        text = texts.read_out(item["spoken"], item["meaning"])
        if hint and not self._told_edge and self.sv.settings()["native_voices"] \
                and not self.sv.has_provider("edge"):
            self._told_edge = True
            text = f"{text} {_('hint_edge_voices')}"
        return text

    # --- items in the local language -----------------------------------------------------

    def _gender(self, trip):
        voice = trip.voice if isinstance(trip.voice, dict) else None
        gender = (voice or {}).get("gender") or ""
        return gender if gender in NATIVE_SPEECH_KEYS else None

    def _item(self, trip, parts):
        """One native line from greeting/phrase parts (each {"native",
        "translit", "means"}) plus what the step needs."""
        code = trip.language
        entry = phrases.LANGUAGES[code]
        user = texts.user_language()
        native = " ".join(p["native"] for p in parts if p.get("native"))
        translit = " ".join(p["translit"] for p in parts if p.get("translit"))
        meaning = " ".join(phrases.meaning(p["means"], user, city=trip.dest["name"])
                           for p in parts)
        voice = trip.voice if isinstance(trip.voice, dict) and \
            self.sv.settings()["native_voices"] else None
        return {"native": native, "translit": translit, "meaning": meaning,
                "spoken": translit or native, "latin": entry["latin"],
                "written": phrases.written_form({"native": native, "translit": translit}),
                "voice": voice, "same_language": code == user,
                "language_name": phrases.language_name(code, user)}

    def greeting_item(self, trip):
        if trip.language is None or trip.dest is None:
            return None
        local = self.sv.utcnow().astimezone(texts.zone_of(trip.dest))
        gender = self._gender(trip)
        hello = phrases.greeting(trip.language, local.hour, gender)
        native_city = trip.native_city()
        welcome = phrases.welcome(trip.language, *(native_city or (None, None)))
        return self._item(trip, [hello, welcome])

    def phrase_item(self, trip):
        if not trip.phrase_bag:
            trip.phrase_bag = list(phrases.PHRASE_KEYS)
            self.rng.shuffle(trip.phrase_bag)
        key = trip.phrase_bag.pop()
        item = self._item(trip, [phrases.phrase(trip.language, key, self._gender(trip))])
        note = phrases.LANGUAGES[trip.language].get("note")
        if note and not getattr(trip, "noted", False):
            trip.noted = True
            item["meaning"] = f"{item['meaning']} {phrases.meaning(note, texts.user_language())}"
        return item

    # --- starting a trip ---------------------------------------------------------------

    def start(self, text):
        """Fly to what the user asked for (on the UI thread; returns at once)."""
        query = places.parse_query(text)
        if query["kind"] == "home":
            self.go_home()
            return None
        self._end_trip()
        trip = Trip(text)
        self.trip = trip
        self.sv.hold(RESOLVE_HOLD_SECONDS)
        avoid = self.last_surprise
        self.sv.run(lambda: self.sv.resolve(text, avoid),
                    lambda dest, error: self._resolved(trip, dest, error))
        return trip

    def _resolved(self, trip, dest, error):
        if trip is not self.trip:
            return
        if error is not None or dest is None:
            kind = getattr(error, "kind", "not_found")
            name = places.parse_query(trip.query).get("name") or trip.query
            if kind == "offline":
                message = _("search_offline")
            elif kind == "no_city":
                message = _("no_city", name=name)
            else:
                message = _("not_found", name=name)
            self.trip = None
            trip.phase = "ended"
            self.say_now(message)
            return
        home = self.sv.home()
        if home and places.distance_km(home, dest) < places.SAME_PLACE_KM:
            self.trip = None
            trip.phase = "ended"
            self.say_now(_("already_there", city=dest["name"]))
            return
        trip.dest, trip.home = dest, home
        if dest.get("surprise"):
            self.last_surprise = dest["surprise"]
        trip.language = phrases.language_for(dest.get("country_code"),
                                             [dest["name"], dest.get("query")],
                                             dest.get("region"))
        self.sv.count_trip()
        trip.hint_pending = self.sv.trips_taken() <= HINT_TRIPS
        self._fetch(trip)
        self._fly(trip)

    def _fetch(self, trip):
        """The weather, the city's names, the native voice and the stations,
        all at once while the plane flies."""
        dest, sv = trip.dest, self.sv
        settings = sv.settings()
        user = texts.user_language()

        def keep(attribute, fallback=None):
            def done(result, error):
                if error is not None:
                    logger.info(f"[World Trip] {attribute} unavailable: {error}")
                setattr(trip, attribute, fallback if error is not None else result)
            return done

        sv.run(lambda: sv.weather(dest), keep("weather"))

        def names():
            native, english = native_names(dest, trip.language, user,
                                           lambda code: sv.localized_name(dest, code))
            return {"native": native, "english": english}
        sv.run(names, keep("names", {"native": None, "english": None}))
        if trip.language and settings["native_voices"]:
            sv.run(lambda: sv.native_voice(trip.language, dest.get("country_code")),
                   keep("voice"))
        else:
            trip.voice = None
        if settings["radio"]:
            names = [dest["name"], dest.get("name_en") or "", dest.get("query") or ""]
            sv.run(lambda: sv.stations(dest, names, trip.language), keep("stations"))
        else:
            trip.stations = []

    def _fly(self, trip):
        settings = self.sv.settings()
        script = self.script
        script.cancel()
        departure = settings["departure"]

        def phase(name):
            def set_phase():
                if self.trip is trip:
                    trip.phase = name
            return set_phase

        script.add(self._call_step(phase("departing")))
        if departure:
            script.add(self._call_step(lambda: self._watch_keys(trip, "departing")))
            script.add(self._sound_step("chime"))
            script.add(self._say_step(lambda: texts.departure(trip.dest, trip.home,
                                                              self.sv.addressed())))
            script.add(self._sound_step("engine", lambda: self.sv.settings()["engine"]))
        script.add(self._call_step(phase("arriving")), label="arrival")
        script.add(self._wait_step(lambda: trip.weather is not PENDING, ARRIVAL_WAIT_SECONDS))
        script.add(self._sound_step("chime"))
        script.add(self._say_step(lambda: texts.arrival(
            trip.dest, self.sv.utcnow(), trip.weather if trip.weather is not PENDING else None,
            trip.home)))
        if trip.language:
            script.add(self._wait_step(lambda: trip.names is not PENDING and
                                       trip.voice is not PENDING, GREETING_WAIT_SECONDS))
            script.add(self._native_step(lambda: self.greeting_item(trip)))
        script.add(self._call_step(phase("exploring")))
        script.add(self._call_step(lambda: self._start_radio(trip)))
        script.start()

    def _watch_keys(self, trip, phase):
        """Any key skips the flight (GetLastInputInfo; no keyboard hook)."""
        watch = self.sv.key_watch()

        def poll():
            if self.trip is not trip or trip.phase != phase or not self.script.running:
                return
            try:
                pressed = watch.pressed()
            except Exception:
                pressed = False
            if pressed:
                self.skip()
                return
            self.sv.call_later(KEY_POLL_SECONDS, poll)
        poll()

    # --- the radio -----------------------------------------------------------------------

    def _then_hint(self, trip):
        steps = []
        if trip.hint_pending:
            trip.hint_pending = False
            steps.append(self._say_step(_("hint_commands")))
        return steps

    def _start_radio(self, trip, waited=0.0):
        if self.trip is not trip:
            return
        if not self.sv.settings()["radio"]:
            self.script.extend(self._then_hint(trip))
            return
        if not self.sv.radio_supported():
            steps = []
            if not self._told_unsupported:
                self._told_unsupported = True
                steps.append(self._say_step(_("radio_unsupported")))
            self.script.extend(steps + self._then_hint(trip))
            return
        if trip.stations is PENDING and waited < STATIONS_WAIT_SECONDS:
            self.sv.call_later(0.5, lambda: self._start_radio(trip, waited + 0.5))
            return
        if trip.stations is PENDING or trip.stations is None:
            self.script.extend([self._say_step(_("radio_offline"))] + self._then_hint(trip))
            return
        if not trip.stations:
            self.script.extend([self._say_step(_("radio_none", place=texts.place_name(trip.dest)))]
                               + self._then_hint(trip))
            return
        self._play_station(trip, 0, 0)

    def _play_station(self, trip, index, tries):
        stations = trip.stations if isinstance(trip.stations, list) else []
        if not stations or tries >= min(MAX_STATION_TRIES, len(stations)):
            trip.playing = None
            self.sv.radio.stop()
            self.script.extend([self._say_step(_("radio_failed_all",
                                                 place=texts.place_name(trip.dest)))]
                               + self._then_hint(trip))
            return
        index %= len(stations)
        trip.station_index = index
        trip.playing = None
        self._radio_token += 1
        token = self._radio_token
        station = stations[index]

        def on_event(kind, detail=None):
            self.sv.call_after(self._radio_event, trip, token, index, tries, kind, detail)
        self.sv.radio.play(station["url"], volume=self.sv.settings()["radio_volume"],
                           on_event=on_event)

    def _radio_event(self, trip, token, index, tries, kind, detail):
        if trip is not self.trip or token != self._radio_token:
            return
        stations = trip.stations if isinstance(trip.stations, list) else []
        if kind == "playing":
            station = stations[index]
            trip.playing = station
            local = places.distance_km(station, trip.dest) <= 80 \
                if station.get("latitude") is not None else False
            where = trip.dest["name"] if local or self._names_city(station, trip) \
                else (trip.dest.get("country") or trip.dest["name"])
            self.script.extend([self._say_step(_("radio_playing", station=station["name"],
                                                 place=where))] + self._then_hint(trip))
            uuid = station.get("uuid")
            if uuid:
                self.sv.run(lambda: self.sv.count_click(uuid), lambda result, error: None)
        elif kind == "error" and detail == "unsupported":
            self._told_unsupported = True
            self.script.extend([self._say_step(_("radio_unsupported"))] + self._then_hint(trip))
        elif kind in ("error", "dropped"):
            trip.playing = None
            self._play_station(trip, index + 1, tries + 1)

    @staticmethod
    def _names_city(station, trip):
        text = f" {phrases.normalize(station.get('name'))} {phrases.normalize(station.get('state'))} "
        for name in (trip.dest["name"], trip.english_name()):
            key = phrases.normalize(name)
            if len(key) >= 3 and f" {key} " in text:
                return True
        return False

    def next_station(self):
        trip = self.trip
        if not self.at_destination():
            self.say_now(_("radio_no_trip"))
            return
        if not self.sv.settings()["radio"]:
            self.say_now(_("radio_off_setting"))
            return
        if not isinstance(trip.stations, list) or not trip.stations:
            self.say_now(_("radio_none", place=texts.place_name(trip.dest)))
            return
        if len(trip.stations) == 1 and trip.playing is not None:
            self.say_now(_("radio_only_one", station=trip.playing["name"]))
            return
        self._play_station(trip, trip.station_index + 1, 0)

    def change_volume(self, step):
        """Louder or quieter: the radio's volume while it plays, else Hariku's."""
        if not self.sv.radio.is_active():
            self.sv.hariku_volume(step)
            return
        volume = max(0, min(100, self.sv.settings()["radio_volume"] + step))
        self.sv.save_radio_volume(volume)
        self.sv.radio.set_volume(volume)
        self.say_now(_("radio_volume", percent=volume))

    def which_station(self):
        trip = self.trip
        if trip is None or trip.playing is None:
            self.say_now(_("radio_not_on"))
            return
        self.say_now(_("radio_this_is", station=trip.playing["name"]))

    # --- answers at the destination ------------------------------------------------------

    def about_target(self, text):
        """What "tell me about {text}" means during a trip: "city", "country"
        or None (not about this trip)."""
        if not self.at_destination():
            return None
        key = phrases.normalize(text)
        if key in ("kota ini", "sini", "tempat ini", "this city", "this place", "here",
                   "kota ini dong", "di sini", "the city"):
            return "city"
        trip = self.trip
        for name in (trip.dest["name"], trip.english_name(), trip.query):
            if name and phrases.normalize(name) == key:
                return "city"
        if trip.dest.get("country") and phrases.normalize(trip.dest["country"]) == key:
            return "country"
        return None

    def about(self, target="city"):
        trip = self.trip
        if not self.at_destination():
            self.say_now(_("about_no_trip"))
            return
        dest = trip.dest
        english = trip.english_name()

        def work():
            if target == "country":
                return self.sv.country_summary(dest["country"])
            return self.sv.summary(dest, [dest["name"]], [english] if english else [])

        def done(found, error):
            if trip is not self.trip:
                return
            if error is not None or not found:
                kind = getattr(error, "kind", "not_found")
                self.say_now(_("about_offline") if kind in ("offline", "service")
                             else _("about_none", place=dest["name"] if target == "city"
                                    else dest.get("country") or dest["name"]))
                return
            fallback = found["lang"] == "en" and texts.user_language() != "en"
            self.say_now(_("about_wiki_en" if fallback else "about_wiki", text=found["text"]))
        self.sv.run(work, done)

    def teach_phrase(self):
        trip = self.trip
        if not self.at_destination():
            self.say_now(_("lesson_no_trip"))
            return
        if trip.language is None:
            self.say_now(_("lesson_no_language"))
            return
        if trip.language == texts.user_language():
            self.say_now(_("lesson_same_language"))
            return
        item = self.phrase_item(trip)
        self.sv.stop_voice()
        self.script.extend([self._native_step(lambda: item)])

    def time_there(self):
        now = self.sv.utcnow()
        if self.at_destination():
            self.say_now(texts.time_there(self.trip.dest, now, self.trip.home))
        else:
            self.say_now(texts.time_home(now, self.sv.home()))

    def where_am_i(self):
        now = self.sv.utcnow()
        if self.at_destination():
            trip = self.trip
            self.say_now(texts.where(trip.dest, now, trip.home, trip.playing))
            return
        if self.trip is not None and self.trip.phase in ("departing", "homebound"):
            self.say_now(_("where_flying"))
            return
        home = self.sv.home()
        self.say_now(_("where_home", home=home["name"]) if home else _("where_home_noplace"))

    # --- skipping, going home, stopping --------------------------------------------------

    def skip(self):
        """Skip the flight ("lewati", or any key while flying)."""
        trip = self.trip
        if trip is not None and trip.phase == "departing" and self.script.has_label("arrival"):
            self.sv.stop_sound("engine")
            self.sv.stop_sound("chime")
            self.sv.stop_voice()
            self.script.skip_to("arrival")
            return True
        if trip is not None and trip.phase == "homebound" and self.script.has_label("landing"):
            self.sv.stop_sound("engine")
            self.sv.stop_voice()
            self.script.skip_to("landing")
            return True
        if self.at_destination():
            self.say_now(_("skip_landed"))
        else:
            self.say_now(_("skip_not_flying"))
        return False

    def go_home(self):
        trip = self.trip
        if trip is None or trip.phase == "ended":
            self.say_now(_("home_already"))
            return
        if trip.phase == "homebound":
            self.say_now(_("home_on_the_way"))
            return
        was_resolving = trip.phase == "resolving"
        self._stop_all()
        trip.phase = "homebound"
        home = self.sv.home()
        if was_resolving:
            self.trip = None
            trip.phase = "ended"
            self.say_now(_("home_cancelled"))
            return
        script = self.script
        name = home["name"] if home else ""
        script.add(self._say_step(_("home_fly", home=name) if home else _("home_fly_noplace"),
                                  interrupt=True))
        settings = self.sv.settings()
        if settings["departure"] and settings["engine"]:
            script.add(self._call_step(lambda: self._watch_keys(trip, "homebound")))
            script.add(self._sound_step("engine"))
        script.add(self._sound_step("chime"), label="landing")
        script.add(self._say_step(lambda: texts.landed_home(self.sv.utcnow(), home)))
        script.add(self._call_step(lambda: self._ended(trip)))
        script.start()

    def _ended(self, trip):
        trip.phase = "ended"
        if self.trip is trip:
            self.trip = None

    def _stop_all(self):
        self.script.cancel()
        self._radio_token += 1
        self.sv.radio.stop()
        self.native_active = False
        for name in ("engine", "chime"):
            self.sv.stop_sound(name)

    def _end_trip(self):
        """A new trip replaces this one: silence it first."""
        if self.trip is not None:
            self.trip.phase = "ended"
            self.trip = None
            self._stop_all()
            self.sv.stop_voice()

    def shutdown(self):
        """Hariku is closing, or the extension is unloaded."""
        if self.trip is not None:
            self.trip.phase = "ended"
        self.trip = None
        self._stop_all()
