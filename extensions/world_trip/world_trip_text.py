# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What World Trip says, in the user's language (English or Indonesian, casual:
"kamu", "aku"): the captain's announcement, the arrival, local times and
their difference from home, the weather in words, the radio, the answers to
commands. Numbers are written as digits with the language's separators, so
every voice reads them. No wx.
"""

import datetime
import os

from core.i18n import format_date, get_current_language, get_translator

import world_trip_phrases as phrases
import world_trip_places as places

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("world_trip", os.path.join(EXT_DIR, "locales"))

# WMO weather codes Open-Meteo uses; each has a "wmo_<code>" text.
KNOWN_CODES = (0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77,
               80, 81, 82, 85, 86, 95, 96, 99)

# Parts of the day, from the hour they start: "Jumat malam", "Friday evening".
PARTS_OF_DAY = {
    "id": ((0, "part_dawn"), (3, "part_morning"), (11, "part_midday"),
           (15, "part_afternoon"), (18, "part_evening")),
    "en": ((0, "part_night"), (5, "part_morning"), (12, "part_afternoon"),
           (17, "part_evening"), (21, "part_night")),
}

READER_SECONDS_PER_CHAR = 0.06   # a guess at how long a screen reader takes
READER_MIN_SECONDS = 0.6
READER_MAX_SECONDS = 25.0


def user_language():
    """ "id" or "en": the language greetings and phrases are explained in."""
    code = (get_current_language() or "en").split("-")[0].lower()
    return code if code in phrases.USER_LANGUAGES else "en"


def speech_seconds(text):
    """About how long a screen reader takes to say `text`."""
    return max(READER_MIN_SECONDS, min(READER_MAX_SECONDS,
                                       READER_MIN_SECONDS + len(text or "") * READER_SECONDS_PER_CHAR))


# ------------------------------------------------------------
# Numbers, durations, times
# ------------------------------------------------------------

def number(value):
    """5300 -> "5,300" or "5.300"."""
    text = f"{int(round(value)):,}"
    separator = _("number_thousands")
    return text.replace(",", separator if len(separator) <= 1 else ",")


def duration(minutes):
    """90 -> "an hour and a half", 420 -> "7 hours", 30 -> "30 minutes"."""
    minutes = int(round(minutes))
    hours, rest = divmod(minutes, 60)
    if hours == 0:
        return _("dur_min", m=rest)
    if rest == 0:
        return _("dur_h1") if hours == 1 else _("dur_h", h=hours)
    if rest == 30:
        return _("dur_h1_half") if hours == 1 else _("dur_h_half", h=hours)
    return _("dur_h1_min", m=rest) if hours == 1 else _("dur_h_min", h=hours, m=rest)


def clock(when):
    return _("clock", hour=f"{when.hour:02d}", minute=f"{when.minute:02d}")


def part_of_day(hour):
    key = PARTS_OF_DAY["en"][0][1]
    for start, name in PARTS_OF_DAY.get(user_language(), PARTS_OF_DAY["en"]):
        if hour >= start:
            key = name
    return _(key)


def day_and_part(when):
    """ "Jumat malam", "Friday evening"."""
    return _("day_part", day=format_date(when, "%A"), part=part_of_day(when.hour))


def utc_offset_minutes(zone, utc_now):
    offset = utc_now.astimezone(zone).utcoffset()
    return int(offset.total_seconds() // 60) if offset is not None else 0


def offset_text(minutes, home_name):
    """The time difference from home, in words: "2 jam lebih cepat dari Batam"."""
    if minutes == 0:
        return _("offset_same", home=home_name)
    words = duration(abs(minutes))
    key = "offset_ahead" if minutes > 0 else "offset_behind"
    return _(key, diff=words, home=home_name)


# ------------------------------------------------------------
# Places and weather
# ------------------------------------------------------------

def place_name(dest):
    """ "Tokyo, Jepang", or just "Singapura" when the city is the country."""
    city = dest.get("name") or ""
    country = dest.get("country") or ""
    if not country or phrases.normalize(country) == phrases.normalize(city):
        return city
    return _("place_and_country", city=city, country=country)


def condition(code):
    return _(f"wmo_{code}") if code in KNOWN_CODES else ""


def weather_text(weather):
    """ "18 derajat, gerimis", or "" without the weather."""
    if not weather:
        return ""
    temp = int(round(weather["temperature"]))
    words = condition(weather.get("code"))
    return _("weather_line", temp=temp, condition=words) if words else \
        _("weather_temp_only", temp=temp)


# ------------------------------------------------------------
# The flight
# ------------------------------------------------------------

def departure(dest, home, addressed=""):
    """The captain's announcement."""
    intro = _("depart_intro_captain", name=addressed) if addressed else _("depart_intro")
    if dest.get("surprise"):
        intro = f"{intro} {_('depart_surprise', city=dest['name'])}"
    if home:
        km = places.distance_km(home, dest)
        minutes = places.round_minutes(places.flight_minutes(km))
        route = _("depart_route", home=home["name"], city=dest["name"],
                  km=number(places.round_km(km)), duration=duration(minutes))
    else:
        route = _("depart_route_nohome", city=dest["name"])
    return " ".join([intro, route, _("depart_seatbelt")])


def local_time_parts(dest, utc_now, home=None):
    """(local datetime, the difference from home in words, or "" without a
    home). A home without a time zone uses the computer's."""
    zone = zone_of(dest)
    local = utc_now.astimezone(zone)
    if home is None:
        return local, ""
    minutes = utc_offset_minutes(zone, utc_now) - utc_offset_minutes(zone_of(home), utc_now)
    return local, offset_text(minutes, home["name"])


def zone_of(place):
    """The place's time zone (zoneinfo), else the computer's own."""
    name = (place or {}).get("timezone") or ""
    if name:
        try:
            import zoneinfo
            return zoneinfo.ZoneInfo(name)
        except Exception:
            pass
    return datetime.datetime.now().astimezone().tzinfo


def arrival(dest, utc_now, weather=None, home=None):
    """ "Selamat datang di Tokyo, Jepang. Waktu setempat jam 21.30, Jumat
    malam, 2 jam lebih cepat dari Batam. 18 derajat, gerimis." """
    local, offset = local_time_parts(dest, utc_now, home)
    parts = [_("arrive_welcome", place=place_name(dest))]
    if offset:
        parts.append(_("arrive_time", time=clock(local), day_part=day_and_part(local),
                       offset=offset))
    else:
        parts.append(_("arrive_time_nohome", time=clock(local), day_part=day_and_part(local)))
    words = weather_text(weather)
    if words:
        parts.append(_cap(words) + ".")
    return " ".join(parts)


def _cap(text):
    return text[:1].upper() + text[1:] if text else text


def time_there(dest, utc_now, home=None):
    local, offset = local_time_parts(dest, utc_now, home)
    if offset:
        return _("time_there", city=dest["name"], time=clock(local),
                 day_part=day_and_part(local), offset=offset)
    return _("time_there_nohome", city=dest["name"], time=clock(local),
             day_part=day_and_part(local))


def time_home(utc_now, home=None):
    local = utc_now.astimezone(zone_of(home) if home else zone_of({}))
    if home:
        return _("time_home", home=home["name"], time=clock(local))
    return _("time_home_noplace", time=clock(local))


def where(dest, utc_now, home=None, station=None):
    local = utc_now.astimezone(zone_of(dest))
    if home:
        km = number(places.round_km(places.distance_km(home, dest)))
        text = _("where_trip", place=place_name(dest), km=km, home=home["name"],
                 time=clock(local))
    else:
        text = _("where_trip_nohome", place=place_name(dest), time=clock(local))
    if station:
        text = f"{text} {_('where_radio', station=station['name'])}"
    return text


def landed_home(utc_now, home=None):
    if home:
        local = utc_now.astimezone(zone_of(home))
        return _("home_landed", home=home["name"], time=clock(local))
    return _("home_landed_noplace")


# ------------------------------------------------------------
# Greetings and phrases
# ------------------------------------------------------------

def explained(spoken, meaning, latin):
    """What the user's own voice says after a native voice: "Konbanwa! ...,
    artinya: selamat malam!", or only the meaning for Latin-script languages
    (the native voice said the words; they are also in Last result)."""
    if latin or not spoken:
        return _("meaning_only", meaning=meaning)
    return _("meaning_spoken", spoken=spoken, meaning=meaning)


def read_out(spoken, meaning):
    """Without a native voice: the words and their meaning, in the user's voice."""
    return _("meaning_spoken", spoken=spoken, meaning=meaning)
