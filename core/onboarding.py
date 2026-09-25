# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The welcome (core 2.10): what Hariku asks and says the first time it starts,
and again from Help, Welcome Dialog, worked out without any window so it can
be tested. The window is ui/onboarding_dialog.py.

Eight pages, one conversation:
  1. hello, and the language (it switches at once: core.i18n.use_language);
  2. the user's name, what to call them (default: the first word of the
     name) and how Hariku talks (core.persona: "auto" follows the nickname,
     so "Princess" gets the royal persona). From here on everything Hariku
     says uses that nickname, in that persona;
  3. where they live: a city search (Open-Meteo), then the local time there
     and, online, the weather, in words;
  4. their birthday (day and month, the year optional);
  5. meeting Aruna, with a field to try "jam berapa" / "what time is it";
  6. extensions from the store, the recommended ones this Hariku can run;
  7. starting with Windows, and the greeting when Hariku starts;
  8. a summary, then Finish.

A text with the user's name goes through personal(): core.personal.
tidy_spoken() closes the gap a missing name leaves ("Senang kenalan, !"
becomes "Senang kenalan!"), so every question works without a name too.

Answers holds what the pages edit. prefill() reads the current settings, so
running the welcome again shows what is there, and save() never erases:
a blank name, nickname or birthday, or no city chosen, keeps what is saved.
save() writes each answer where it belongs: the Profile (core.personal:
"user_name", the same key the old wizard wrote, so its name is already the
Profile's; its "User" placeholder counts as no name), the birthday and
"greet_on_startup"; Places (the city becomes the main place, "Rumah"/"Home";
the other places stay); "auto_start" with the Run key (core.api.
set_autostart); "language"; and "onboarding_completed" on the first run.

Cancel saves nothing, except on the first run: "onboarding_completed", so the
welcome doesn't come back at every start (Help, Welcome Dialog shows it
again), and the language the welcome was shown in when none was saved yet.

Network, on worker threads only (the window hands results back through
wx.CallAfter): the city search (core.place_search.search_cities), the current
weather (fetch_weather: the point rounded to about 1 km, never the exact one)
and the store's list (core.store.fetch_registry). Nothing is downloaded
before Finish; install() then downloads the extensions the user ticked.
"""
import ctypes
import datetime
import logging
import urllib.parse

import core.api
import core.commands
import core.extension_catalog as catalog
import core.extension_manager
import core.i18n
import core.persona
import core.personal
import core.place_search
import core.places
import core.store
from core.i18n import get_translator

_ = get_translator("core")
logger = logging.getLogger(__name__)

DATA_KEY = "Core"
COMPLETED_KEY = "onboarding_completed"
AUTOSTART_KEY = "auto_start"
LANGUAGE_KEY = "language"

PAGES = ("hello", "name", "where", "birthday", "aruna", "extensions", "startup", "done")
CITY_MIN_LENGTH = 2

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# The actions "Try it" may answer; nothing else ever runs from the welcome.
TIME_ACTION = "Hariku Core.speak_time"
DATE_ACTION = "Hariku Core.speak_date"

# Store extensions the welcome suggests, in this order; only those in the
# store that this Hariku can install and that aren't installed are shown.
RECOMMENDED = ("weather", "briefing", "timer_alarm", "voice_control", "world_trip",
               "earthquake", "world_clock", "air_quality", "lumina", "sound_themes")
# Ticked at first; Weather too when there is a place (it uses the main place).
CHECKED = frozenset({"briefing", "timer_alarm"})
NEEDS_PLACE = frozenset({"weather"})

# WMO weather codes (what Open-Meteo reports) -> the words for them.
_SKY = {0: "clear", 1: "mostly_clear", 2: "partly_cloudy", 3: "overcast",
        45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
        56: "freezing", 57: "freezing", 61: "light_rain", 63: "rain", 65: "heavy_rain",
        66: "freezing", 67: "freezing", 71: "snow", 73: "snow", 75: "snow", 77: "snow",
        80: "light_rain", 81: "rain", 82: "heavy_rain", 85: "snow", 86: "snow",
        95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm"}
SKY_KEYS = tuple(sorted(set(_SKY.values())))


def _one_line(value):
    return " ".join(str(value or "").split())


def personal(text):
    """`text` as Hariku says it: the gap a missing name leaves closed up."""
    return core.personal.tidy_spoken(text)


# ------------------------------------------------------------
# What the pages edit
# ------------------------------------------------------------

class Answers:
    """What the welcome's pages edit. `place` is a city the user chose (a
    core.place_search candidate), or None to keep the main place as it is;
    `birthday` is (day, month, year or None) or None; `extensions` the ids of
    the store extensions to install at Finish."""

    FIELDS = ("language", "name", "nickname", "persona", "place", "birthday", "autostart",
              "greet", "extensions")

    def __init__(self, language="en", name="", nickname="", persona=core.persona.AUTO,
                 place=None, birthday=None, autostart=False, greet=True, extensions=()):
        self.language = language
        self.name = name
        self.nickname = nickname
        self.persona = persona
        self.place = dict(place) if place else None
        self.birthday = tuple(birthday) if birthday else None
        self.autostart = bool(autostart)
        self.greet = bool(greet)
        self.extensions = list(extensions or ())

    def as_dict(self):
        return {field: getattr(self, field) for field in self.FIELDS}

    def copy(self):
        return Answers(**self.as_dict())

    def __eq__(self, other):
        return isinstance(other, Answers) and self.as_dict() == other.as_dict()

    def __repr__(self):
        return f"Answers({self.as_dict()!r})"


def first_word(name):
    """The first word of a name: what Hariku calls "Rafli Hidayat" unless told."""
    words = _one_line(name).split(" ")
    return words[0] if words else ""


def nickname_for(name, nickname):
    """What Hariku calls the user: their nickname, else the first word of their name."""
    return _one_line(nickname) or first_word(name)


def _config():
    data = core.api.load_data(DATA_KEY)
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------
# Languages
# ------------------------------------------------------------

def languages():
    """[(code, name)] of Hariku's own languages, by name."""
    found = {m["language_code"]: m["language_name"]
             for m in core.i18n.get_available_languages("core")}
    return sorted(found.items(), key=lambda item: item[1].casefold())


def windows_languages():
    """Windows' display language, then its regional format, as tags
    ("id-ID", "en-US"); empty when Windows can't say."""
    tags = []
    try:
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_unicode_buffer(85)
        if kernel32.LCIDToLocaleName(kernel32.GetUserDefaultUILanguage(), buf, 85, 0):
            tags.append(buf.value)
        buf = ctypes.create_unicode_buffer(85)
        if kernel32.GetUserDefaultLocaleName(buf, 85):
            tags.append(buf.value)
    except Exception as e:
        logger.debug(f"Windows' language unknown: {e}")
    return tags


def _primary(tag):
    return str(tag or "").replace("_", "-").split("-")[0].strip().lower()


def default_language(saved, windows_tags, available):
    """The language the welcome starts in: the saved one, else the first of
    Windows' languages Hariku has, else English."""
    available = list(available)
    if saved in available:
        return saved
    for tag in windows_tags or ():
        if _primary(tag) in available:
            return _primary(tag)
    return "en" if "en" in available or not available else available[0]


# ------------------------------------------------------------
# Prefilling from the current settings
# ------------------------------------------------------------

def prefill(first_run=False, windows_tags=None):
    """Answers from what is saved. The old wizard saved the name in Core.json
    "user_name", which is the Profile's name, so it shows here (its "User"
    placeholder counts as no name). With no language saved (a first run), the
    language comes from Windows."""
    config = _config()
    profile = core.personal.get_profile()
    codes = [code for code, _name in languages()]
    saved = config.get(LANGUAGE_KEY) if isinstance(config.get(LANGUAGE_KEY), str) else None
    if saved or not first_run:
        language = default_language(saved or core.i18n.get_current_language(), (), codes)
    else:
        language = default_language(None, windows_languages() if windows_tags is None
                                    else windows_tags, codes)
    name = profile["name"]
    return Answers(language=language, name=name,
                   nickname=profile["nickname"] or first_word(name),
                   persona=core.persona.get_setting(),
                   birthday=profile["birthday"],
                   autostart=config.get(AUTOSTART_KEY) is True,
                   greet=profile["greet_on_startup"])


def nickname_is_automatic(answers):
    """Whether the prefilled nickname is only the default (the first word of
    the name), which then follows the name as it is typed."""
    return not core.personal.get_profile()["nickname"] and \
        answers.nickname == first_word(answers.name)


def main_place():
    """The main place (a copy), or None."""
    return core.places.get_main()


# ------------------------------------------------------------
# The conversation
# ------------------------------------------------------------

def name_reply(nickname):
    """ "Halo, Rafli! Akhirnya kita kenalan juga." (in the persona talked in) """
    return personal(_("onb_name_reply", name=nickname))


def use_persona(setting, name, nickname):
    """Talk in the persona the name page chose from here on (core.persona);
    returns it. Saved only at Finish; Cancel goes back to the saved one."""
    return core.persona.apply(setting, nickname_for(name, nickname))


def question(page, nickname="", reply=""):
    """The line that opens a page: the reply to the page before (if any),
    then the page's question, with the nickname in it."""
    keys = {"hello": "onb_hello_question", "name": "onb_name_question",
            "where": "onb_where_question", "birthday": "onb_birthday_question",
            "aruna": "onb_aruna_question", "extensions": "onb_ext_question",
            "startup": "onb_startup_question"}
    return personal(_(keys[page], name=nickname, reply=reply))


def city_of(place):
    """What to call a place or a city found in a sentence: its city, else its
    name, else its label."""
    if not place:
        return ""
    for field in ("city", "name", "label"):
        value = _one_line(place.get(field))
        if value:
            return value.split(",")[0].strip() if field == "label" else value
    return ""


def local_time(place, now=None):
    """The time at the place (its time zone, else the computer's)."""
    zone = core.places.timezone_for(place)
    if now is None:
        return datetime.datetime.now(zone)
    return now.astimezone(zone)


def sky_words(code):
    """A WMO weather code in words ("cerah berawan", "light rain"), or ""."""
    try:
        key = _SKY.get(int(code))
    except (TypeError, ValueError):
        key = None
    return _("onb_sky_" + key) if key else ""


def _degrees(weather):
    return str(int(round(weather["temperature"])))


def place_sentence(place, now=None, weather=None):
    """ "Di Batam sekarang jam 14:20, cerah berawan, 31 derajat." The weather
    is left out when there is none (offline, or not here yet)."""
    city = city_of(place)
    if not city:
        return ""
    time_text = local_time(place, now).strftime("%H:%M")
    if weather:
        sky = sky_words(weather.get("code"))
        if sky:
            return _("onb_place_time_weather", city=city, time=time_text, sky=sky,
                     temperature=_degrees(weather))
        return _("onb_place_time_temperature", city=city, time=time_text,
                 temperature=_degrees(weather))
    return _("onb_place_time", city=city, time=time_text)


def weather_sentence(place, weather):
    """The weather alone, when it arrives after the time was said:
    "Cuaca di Batam: cerah berawan, 31 derajat." """
    city = city_of(place)
    if not city or not weather:
        return ""
    sky = sky_words(weather.get("code"))
    if sky:
        return _("onb_weather_late", city=city, sky=sky, temperature=_degrees(weather))
    return _("onb_weather_late_temperature", city=city, temperature=_degrees(weather))


def check_birthday(day, month, year=None):
    """(day, month, year or None), None when not given, or core.personal.ProfileError."""
    return core.personal.check_birthday(day, month, year)


def birthday_reply(birthday):
    """ "Oke, 12 Mei. Nanti aku ucapkan selamat." """
    if not birthday:
        return ""
    return _("onb_birthday_reply", date=core.personal.birthday_text(tuple(birthday)))


def startup_example(nickname, now=None):
    """What Hariku will say when it starts: "Selamat siang, Rafli. Selamat
    datang di Hariku versi 2.10.0." """
    import core.constants
    welcome = _("welcome_message", version=core.constants.CORE_VERSION)
    text = f"{core.personal.greeting(now, nickname=nickname)} {welcome}"
    return text if text.endswith((".", "!", "?")) else text + "."


# ------------------------------------------------------------
# The weather (worker thread)
# ------------------------------------------------------------

def weather_url(place):
    """Open-Meteo's current weather for the place, rounded to about 1 km."""
    lat, lon = core.places.rounded(place)
    params = {"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code",
              "timezone": "auto"}
    return WEATHER_URL + "?" + urllib.parse.urlencode(params)


def weather_key(place):
    """What a weather answer is remembered by: the rounded point."""
    return core.places.rounded(place)


def parse_weather(payload):
    """{"temperature", "code"} from Open-Meteo's answer, or None."""
    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict):
        return None
    temperature = core.place_search.to_float(current.get("temperature_2m"))
    if temperature is None:
        return None
    try:
        code = int(current.get("weather_code"))
    except (TypeError, ValueError):
        code = None
    return {"temperature": temperature, "code": code}


def fetch_weather(place):
    """The current weather at the place, or None (offline, or an answer that
    can't be read). Blocks: worker threads only."""
    try:
        return parse_weather(core.place_search.fetch_json(weather_url(place)))
    except core.place_search.FetchError as e:
        logger.info(f"Welcome: no weather ({e.kind}).")
    except Exception:
        logger.exception("Welcome: the weather failed")
    return None


def search_cities(query, language="en"):
    """(cities, error kind or None) for what the user typed. Worker threads only."""
    try:
        return core.place_search.search_cities(query, language), None
    except core.place_search.LocationError as e:
        return [], e.kind
    except Exception:
        logger.exception("Welcome: the city search failed")
        return [], "city_failed"


# ------------------------------------------------------------
# Meeting Aruna: "Try it"
# ------------------------------------------------------------

def try_commands():
    """The only commands "Try it" answers: the time and the date."""
    return [core.commands.Command(TIME_ACTION, _("nav_speak_time"),
                                  core.commands.aliases_for(TIME_ACTION)),
            core.commands.Command(DATE_ACTION, _("nav_speak_date"),
                                  core.commands.aliases_for(DATE_ACTION))]


def try_answer(text, now=None, parse=None):
    """(kind, answer) for what the user typed: "time" or "date" with Aruna's
    own answer ("Sekarang jam 14:20."), "reminder" (a reminder sentence,
    which Aruna saves once the welcome is over), "empty" or "other". Nothing
    ever runs from here."""
    decision = core.commands.decide(text, candidates=try_commands(), parse=parse,
                                    intent_candidates=[])
    if decision.kind == "empty":
        return "empty", _("onb_aruna_empty")
    if decision.kind in ("run", "confirm"):
        if decision.action_id == TIME_ACTION:
            return "time", core.commands.time_text(now)
        if decision.action_id == DATE_ACTION:
            return "date", core.commands.date_text(now)
    if decision.kind in ("reminder", "offer_reminder"):
        return "reminder", _("onb_aruna_reminder")
    return "other", _("onb_aruna_other")


# ------------------------------------------------------------
# Extensions
# ------------------------------------------------------------

def description(ext_id, fallback=""):
    """The welcome's one line about a recommended extension, in the user's
    language (the store's description for one it has no line for)."""
    key = "onb_ext_desc_" + ext_id
    text = _(key)
    return fallback if text == key else text


def recommendations(installed, registry, has_place=False, system_dir=None):
    """The recommended extensions to offer, in RECOMMENDED order: those in
    the store that aren't installed and that this Hariku can install
    (core.extension_catalog.can_install: not for a newer Hariku, not too
    old). [{"id", "name", "version", "description", "download_url",
    "checked"}]. `installed` is core.extension_manager.
    get_installed_extensions_info(), `registry` core.store.fetch_registry()."""
    system_dir = system_dir or core.extension_manager.SYSTEM_EXTENSIONS_DIR
    rows = catalog.build(installed or [], registry or [], system_dir)["available"]
    offered = {row["id"]: row for row in rows if catalog.can_install(row)}
    found = []
    for ext_id in RECOMMENDED:
        row = offered.get(ext_id)
        if row is None or not row.get("download_url"):
            continue
        found.append({"id": ext_id, "name": row["name"], "version": row["version"],
                      "description": description(ext_id, row["description"]),
                      "download_url": row["download_url"],
                      "checked": ext_id in CHECKED or (has_place and ext_id in NEEDS_PLACE)})
    return found


def join_names(names):
    """ "Weather", "Weather and Timer & Alarm", "A, B and C" in the user's language."""
    names = [n for n in names if n]
    if len(names) < 2:
        return names[0] if names else ""
    return _("onb_and", first=", ".join(names[:-1]), last=names[-1])


def install(extensions, download=None, progress=None):
    """Download each extension (worker threads only); `progress(index, ext,
    ok)` after each. A failure doesn't stop the others. Returns (installed,
    failed), lists of the extensions given."""
    download = download or core.store.download_extension
    good, bad = [], []
    for index, ext in enumerate(extensions):
        try:
            ok = bool(download(ext["id"], ext["download_url"]))
        except Exception:
            logger.exception(f"Welcome: installing {ext.get('id')} failed")
            ok = False
        (good if ok else bad).append(ext)
        if progress is not None:
            progress(index, ext, ok)
    return good, bad


def install_start_text(extensions):
    if len(extensions) == 1:
        return _("onb_install_start_one", name=extensions[0]["name"])
    return _("onb_install_start", count=len(extensions))


def install_progress_text(index, count, ext, ok):
    if ok:
        return _("onb_install_progress", name=ext["name"], number=index + 1, count=count)
    return _("onb_install_progress_failed", name=ext["name"], number=index + 1, count=count)


def install_summary(good, bad, store_key):
    """What happened, then how to go on."""
    names = join_names(e["name"] for e in good)
    failed = join_names(e["name"] for e in bad)
    if good and not bad:
        text = _("onb_install_done", names=names)
    elif good:
        text = _("onb_install_partly", names=names, failed=failed, shortcut=store_key)
    else:
        text = _("onb_install_failed", failed=failed, shortcut=store_key)
    return f"{text} {_('onb_install_close')}"


# ------------------------------------------------------------
# The summary
# ------------------------------------------------------------

def summary(answers, place=None, aruna_key="", extensions=()):
    """The Done page, sentence by sentence: "Semua siap, Rafli!", where home
    is, the birthday, the greeting, the extensions to install, Aruna's key
    and a welcome."""
    nickname = nickname_for(answers.name, answers.nickname)
    lines = [personal(_("onb_done_ready", name=nickname))]
    city = _one_line((place or {}).get("city"))
    if city:
        lines.append(_("onb_done_place", city=city))
    if answers.birthday:
        lines.append(_("onb_done_birthday",
                       date=core.personal.birthday_text(tuple(answers.birthday))))
    if answers.greet:
        lines.append(_("onb_done_greet_boot") if answers.autostart else _("onb_done_greet"))
    elif answers.autostart:
        lines.append(_("onb_done_autostart"))
    names = [e["name"] for e in extensions]
    if names:
        lines.append(_("onb_done_extensions", names=join_names(names)))
    lines.append(_("onb_done_aruna", shortcut=aruna_key))
    lines.append(_("onb_done_welcome"))
    return lines


# ------------------------------------------------------------
# Saving, or not
# ------------------------------------------------------------

def home_name():
    """The name the city gets as a place: "Rumah" or "Home"."""
    return _("places_default_home")


def save_place(candidate, name=None):
    """Make the city the main place and return it. The place called
    "Rumah"/"Home" (in any of Hariku's languages; the main one first) moves
    there, keeping its id so extensions that chose it follow; without one, a
    new place with that name is added. Other places stay. Raises
    core.places.PlaceError."""
    name = name or home_name()
    names = {n.casefold() for n in core.i18n.translations("places_default_home")}
    names.add(name.casefold())
    places = core.places.get_places()
    main_id = core.places.get_main_id()
    homes = [p for p in places if p["name"].casefold() in names]
    target = next((p for p in homes if p["id"] == main_id), homes[0] if homes else None)
    if target is not None:
        place = core.places.place_from_candidate(candidate, target["name"], target["id"])
        places = [place if p["id"] == target["id"] else p for p in places]
    else:
        place_id = core.places.new_id({p["id"] for p in places})
        place = core.places.place_from_candidate(candidate, name, place_id)
        places.append(place)
    saved = core.places.set_places(places, place["id"])
    return next(p for p in saved if p["id"] == core.places.get_main_id())


def save(answers, first_run=False, set_autostart=None):
    """Write the answers where they belong; a blank name, nickname or
    birthday, or no city chosen, keeps what is saved. Returns what changed
    ({"name", "persona", "place", "birthday", "greet", "autostart", "language",
    "completed", "errors"}); a part that fails is logged and the rest is
    still saved."""
    set_autostart = set_autostart or core.api.set_autostart
    done = {"errors": []}
    profile = core.personal.get_profile()

    name = _one_line(answers.name) or profile["name"]
    typed = _one_line(answers.nickname)
    if name == profile["name"] and not profile["nickname"] and typed == first_word(name):
        # The default the page showed, untouched: Hariku goes on calling
        # them as before (by the whole name when no nickname was saved).
        nickname = ""
    else:
        nickname = typed or profile["nickname"] or first_word(name)
    if (name, nickname) != (profile["name"], profile["nickname"]):
        try:
            core.personal.set_name(name, nickname)
            done["name"] = (name, nickname)
        except core.personal.ProfileError as e:
            done["errors"].append(("name", str(e)))

    if answers.birthday and tuple(answers.birthday) != profile["birthday"]:
        try:
            core.personal.set_birthday(*answers.birthday)
            done["birthday"] = tuple(answers.birthday)
        except core.personal.ProfileError as e:
            done["errors"].append(("birthday", str(e)))

    if answers.greet != profile["greet_on_startup"]:
        core.personal.set_startup_greeting(answers.greet)
        done["greet"] = answers.greet

    # Saved when changed, and applied again either way: the nickname may pick
    # another persona.
    if answers.persona != core.persona.get_setting():
        done["persona"] = answers.persona
    core.persona.save_setting(answers.persona)

    if answers.place:
        try:
            done["place"] = save_place(answers.place)
        except core.places.PlaceError as e:
            done["errors"].append(("place", str(e)))
        except Exception as e:
            logger.exception("Welcome: saving the place failed")
            done["errors"].append(("place", str(e)))

    config = _config()   # read again: the Profile has just been written
    if (config.get(AUTOSTART_KEY) is True) != answers.autostart:
        config[AUTOSTART_KEY] = answers.autostart
        done["autostart"] = answers.autostart
        try:
            set_autostart(answers.autostart)
        except Exception as e:
            logger.exception("Welcome: autostart failed")
            done["errors"].append(("autostart", str(e)))
    if answers.language and config.get(LANGUAGE_KEY) != answers.language:
        config[LANGUAGE_KEY] = answers.language
        done["language"] = answers.language
    if first_run and config.get(COMPLETED_KEY) is not True:
        config[COMPLETED_KEY] = True
        done["completed"] = True
    if any(k in done for k in ("autostart", "language", "completed")):
        core.api.save_data(DATA_KEY, config)
    if done["errors"]:
        logger.warning(f"Welcome: some answers weren't saved: {done['errors']}")
    return done


def cancel(first_run=False, shown_language=None, opened_language=None):
    """Cancel: nothing is saved, except on the first run, where the welcome is
    marked done (so it doesn't come back at every start) and `shown_language`,
    the one the welcome was in, is kept when no language was saved yet.
    Returns the language Hariku goes on in: the saved one, else the one
    Hariku had when the welcome opened (`opened_language`), or on a first run
    without a saved one, the one shown."""
    core.persona.apply()     # the one saved, not the one the name page chose
    config = _config()
    saved = config.get(LANGUAGE_KEY) if isinstance(config.get(LANGUAGE_KEY), str) else None
    if not first_run:
        return saved or opened_language or shown_language
    changed = False
    if config.get(COMPLETED_KEY) is not True:
        config[COMPLETED_KEY] = True
        changed = True
    if shown_language and not saved:
        config[LANGUAGE_KEY] = shown_language
        saved = shown_language
        changed = True
    if changed:
        core.api.save_data(DATA_KEY, config)
    return saved or opened_language or shown_language
