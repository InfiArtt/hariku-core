# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
World Trip's requests, apart from the radio: the weather at the destination
(Open-Meteo, the destination's point rounded to about 1 km) and a short
Wikipedia summary of it (the REST summary API, in the user's language, else
English). Only the destination's name or point is ever sent, never anything
about the user. Every function here blocks: call them on a worker thread.
Also Cache, a small store with an age limit that main.py keeps on disk. No wx.
"""

import re
import time
import urllib.parse

import core.place_search as place_search
from core.constants import CORE_VERSION

import world_trip_places as places

PROJECT_URL = "https://github.com/InfiArtt/hariku-core"
USER_AGENT = f"HarikuV2/{CORE_VERSION} (World Trip extension; +{PROJECT_URL})"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SUMMARY_URL = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
TIMEOUT_SECONDS = 10
QUERY_DECIMALS = 2              # about 1 km
SUMMARY_MAX_CHARS = 480
SUMMARY_MAX_SENTENCES = 3
SUMMARY_NEAR_KM = 100.0         # a page this close to the city is the city's page
WIKI_LANGUAGES = ("id", "en")


class NetError(Exception):
    """`kind`: "offline", "service", "not_found" or "bad_response"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


def _fetch(url, fetch=None):
    try:
        return (fetch or (lambda u: place_search.fetch_json(u, timeout=TIMEOUT_SECONDS,
                                                            user_agent=USER_AGENT)))(url)
    except place_search.FetchError as e:
        if e.status == 404:
            raise NetError("not_found", str(e)) from e
        raise NetError("offline" if e.kind == "offline" else "service", str(e)) from e


# ------------------------------------------------------------
# The weather at the destination
# ------------------------------------------------------------

def weather_url(latitude, longitude):
    lat, lon = round(float(latitude), QUERY_DECIMALS), round(float(longitude), QUERY_DECIMALS)
    params = {"latitude": f"{lat:.{QUERY_DECIMALS}f}", "longitude": f"{lon:.{QUERY_DECIMALS}f}",
              "current": "temperature_2m,weather_code,is_day", "timezone": "auto"}
    return FORECAST_URL + "?" + urllib.parse.urlencode(params)


def parse_weather(payload):
    """{"temperature", "code", "is_day", "timezone"} or NetError."""
    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict):
        raise NetError("bad_response", "no current weather")
    temperature = place_search.to_float(current.get("temperature_2m"))
    code = place_search.to_float(current.get("weather_code"))
    if temperature is None:
        raise NetError("bad_response", "no temperature")
    return {"temperature": temperature,
            "code": int(code) if code is not None else None,
            "is_day": bool(current.get("is_day", 1)),
            "timezone": place_search.clean_timezone(payload.get("timezone")) or ""}


def weather(dest, fetch=None):
    return parse_weather(_fetch(weather_url(dest["latitude"], dest["longitude"]), fetch))


# ------------------------------------------------------------
# Wikipedia summaries
# ------------------------------------------------------------

def summary_url(title, lang):
    lang = lang if lang in WIKI_LANGUAGES else "en"
    return SUMMARY_URL.format(lang=lang, title=urllib.parse.quote(
        str(title).strip().replace(" ", "_"), safe=""))


_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?)])")
_EMPTY_PARENS = re.compile(r"\(\s*[,;]?\s*\)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9\"“(])")


def clean_extract(text, max_chars=SUMMARY_MAX_CHARS, max_sentences=SUMMARY_MAX_SENTENCES):
    """The summary's first sentences, tidied for speech: "Tokyo , nama
    resminya ..." -> "Tokyo, nama resminya ...", at most a few sentences."""
    text = " ".join(str(text or "").split())
    text = _EMPTY_PARENS.sub("", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = " ".join(text.split())
    sentences = _SENTENCE_END.split(text)
    kept = []
    for sentence in sentences:
        if kept and (len(kept) >= max_sentences
                     or len(" ".join(kept + [sentence])) > max_chars):
            break
        kept.append(sentence)
    result = " ".join(kept)
    if len(result) > max_chars + 120:        # one enormous sentence
        result = result[:max_chars].rsplit(" ", 1)[0] + "..."
    return result


def parse_summary(payload):
    """{"title", "text", "type", "coordinates"} from the REST summary."""
    if not isinstance(payload, dict):
        raise NetError("bad_response", "not an object")
    coordinates = payload.get("coordinates")
    point = None
    if isinstance(coordinates, dict):
        lat = place_search.to_float(coordinates.get("lat"))
        lon = place_search.to_float(coordinates.get("lon"))
        if lat is not None and lon is not None:
            point = {"latitude": lat, "longitude": lon}
    return {"title": str(payload.get("title") or ""),
            "text": clean_extract(payload.get("extract") or ""),
            "type": str(payload.get("type") or ""),
            "coordinates": point}


def page_summary(title, lang, fetch=None):
    return parse_summary(_fetch(summary_url(title, lang), fetch))


def _titles(names, dest):
    titles = []
    for name in names:
        name = str(name or "").strip()
        if not name:
            continue
        for title in (name, f"{name}, {dest.get('region') or ''}".strip(", "),
                      f"{name}, {dest.get('country') or ''}".strip(", ")):
            if title and title not in titles:
                titles.append(title)
    return titles


def city_summary(dest, user_language, names=(), english_names=(), fetch=None):
    """A few sentences about the destination from Wikipedia, in the user's
    language when its Wikipedia has the city (a page near the city's point),
    else English: {"text", "lang", "title"}. Raises NetError("not_found")."""
    tries = []
    if user_language in WIKI_LANGUAGES and user_language != "en":
        tries.append((user_language, _titles(list(names) or [dest["name"]], dest)))
    tries.append(("en", _titles(list(english_names) or list(names) or [dest["name"]], dest)))
    last_error = NetError("not_found")
    for lang, titles in tries:
        for title in titles:
            try:
                page = page_summary(title, lang, fetch)
            except NetError as e:
                if e.kind != "not_found":
                    raise
                last_error = e
                continue
            if page["type"] != "standard" or not page["text"]:
                continue
            where = page["coordinates"]
            if where is None or places.distance_km(where, dest) > SUMMARY_NEAR_KM:
                continue
            return {"text": page["text"], "lang": lang, "title": page["title"]}
    raise last_error if last_error.kind != "not_found" else NetError("not_found")


def country_summary(country, user_language, fetch=None):
    """A few sentences about a country: {"text", "lang", "title"}."""
    langs = [user_language] if user_language in WIKI_LANGUAGES else []
    langs += [lang for lang in ("en",) if lang not in langs]
    for lang in langs:
        try:
            page = page_summary(country, lang, fetch)
        except NetError as e:
            if e.kind != "not_found":
                raise
            continue
        if page["type"] == "standard" and page["text"]:
            return {"text": page["text"], "lang": lang, "title": page["title"]}
    raise NetError("not_found", country)


# ------------------------------------------------------------
# A small cache with an age limit
# ------------------------------------------------------------

class Cache:
    """{key: value} with each entry's time; entries older than `max_age`
    seconds are gone, and the oldest go first past `max_entries`. Keys are
    strings, values JSON-friendly, so main.py can keep it on disk."""

    def __init__(self, max_age, max_entries=40, clock=time.time):
        self.max_age = max_age
        self.max_entries = max_entries
        self._clock = clock
        self._items = {}

    def get(self, key):
        item = self._items.get(key)
        if item is None:
            return None
        if not 0 <= self._clock() - item[0] <= self.max_age:
            self._items.pop(key, None)
            return None
        return item[1]

    def put(self, key, value):
        self._items.pop(key, None)
        self._items[key] = (self._clock(), value)
        while len(self._items) > self.max_entries:
            self._items.pop(next(iter(self._items)))

    def to_dict(self):
        now = self._clock()
        return {k: [t, v] for k, (t, v) in self._items.items() if 0 <= now - t <= self.max_age}

    def load(self, data):
        self._items = {}
        if not isinstance(data, dict):
            return
        now = self._clock()
        for key, item in data.items():
            if (isinstance(key, str) and isinstance(item, list) and len(item) == 2
                    and isinstance(item[0], (int, float)) and 0 <= now - item[0] <= self.max_age):
                self._items[key] = (float(item[0]), item[1])
        while len(self._items) > self.max_entries:
            self._items.pop(next(iter(self._items)))


def point_key(dest, prefix=""):
    """A cache key for a destination: its point rounded to about 1 km."""
    return f"{prefix}{round(float(dest['latitude']), 2):.2f},{round(float(dest['longitude']), 2):.2f}"
