# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Open-Meteo access for the Sea Conditions extension: request URLs, the HTTP
fetch, and turning the Marine API JSON into plain dicts, plus the pure helpers
for settings, the cache and the high-wave alert. No wx and no translated text,
so tests can drive it with sample responses.

Privacy (core 2.8): the Marine API gets the place rounded to 2 decimals
(about 1 km), never more; the cache is kept for that rounded point.

fetch_json(), fetch_marine() and search_places() block on the network: call
them from a worker thread only.
"""

import datetime
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

import core.places
from core.constants import CORE_VERSION

logger = logging.getLogger(__name__)

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = f"HarikuV2/{CORE_VERSION} (Marine extension)"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 1024 * 1024
FORECAST_DAYS = 7
PAST_DAYS = 1        # yesterday's sea level, so the tide around "now" is complete
SEARCH_COUNT = 10

CURRENT_FIELDS = ("wave_height", "wave_direction", "wave_period", "swell_wave_height",
                  "sea_surface_temperature")
HOURLY_FIELDS = ("sea_level_height_msl",)
DAILY_FIELDS = ("wave_height_max", "wave_direction_dominant", "wave_period_max",
                "swell_wave_height_max")

QUERY_DECIMALS = 2   # the point Open-Meteo gets: about 1 km

ALERT_HEIGHTS = (1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0)   # metres
DEFAULT_ALERT_HEIGHT = 2.5


class MarineError(Exception):
    """A failed request. `kind` is "offline", "service" or "bad_response"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


# ------------------------------------------------------------
# Requests
# ------------------------------------------------------------

def query_point(latitude, longitude):
    """The rounded point sent instead of the exact one."""
    return round(float(latitude), QUERY_DECIMALS), round(float(longitude), QUERY_DECIMALS)


def build_marine_url(latitude, longitude, timezone=""):
    # Always rounded here, so an exact point can never reach the URL.
    lat, lon = query_point(latitude, longitude)
    params = {
        "latitude": f"{lat:.{QUERY_DECIMALS}f}",
        "longitude": f"{lon:.{QUERY_DECIMALS}f}",
        "current": ",".join(CURRENT_FIELDS),
        "hourly": ",".join(HOURLY_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
        "timezone": timezone or "auto",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
    }
    return MARINE_URL + "?" + urllib.parse.urlencode(params)


def build_search_url(name, language="en"):
    params = {
        "name": (name or "").strip(),
        "count": SEARCH_COUNT,
        "language": language if language in ("en", "id") else "en",
        "format": "json",
    }
    return GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def fetch_json(url):
    """GET `url` and decode its JSON body. Raises MarineError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise MarineError("service", f"HTTP {e.code}") from e
    except Exception as e:  # URLError, timeouts, resets: treat as unreachable
        raise MarineError("offline", str(e)) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise MarineError("bad_response", "response too large")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise MarineError("bad_response", str(e)) from e


def fetch_marine(latitude, longitude, timezone=""):
    return parse_marine(fetch_json(build_marine_url(latitude, longitude, timezone)))


def search_places(name, language="en"):
    return parse_places(fetch_json(build_search_url(name, language)))


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def to_float(value):
    """A finite float, or None for anything else (including bools)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def to_int(value):
    number = to_float(value)
    return None if number is None else int(round(number))


def _column(block, name, index):
    values = block.get(name)
    if isinstance(values, list) and index < len(values):
        return values[index]
    return None


def _is_hour(text):
    return isinstance(text, str) and len(text) == 16 and text[10:11] == "T"


def has_sea_data(forecast):
    """False when the model has nothing for this point (inland places)."""
    cur = forecast.get("current") or {}
    if any(cur.get(k) is not None for k in ("wave_height", "sea_temperature", "swell_height")):
        return True
    if any(d.get("wave_max") is not None for d in forecast.get("daily") or []):
        return True
    return any(level is not None for _t, level in forecast.get("sea_level") or [])


def parse_marine(payload):
    """Marine API JSON -> {"timezone", "utc_offset_seconds", "current": {...},
    "daily": [{...}], "sea_level": [[hour, metres or None], ...], "has_data"}.
    An inland point answers with nulls: that is "has_data": False, not an
    error. Raises MarineError for anything unreadable."""
    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise MarineError("bad_response", "no current conditions")
    cur = payload["current"]
    current = {
        "time": str(cur.get("time") or ""),
        "wave_height": to_float(cur.get("wave_height")),
        "wave_direction": to_float(cur.get("wave_direction")),
        "wave_period": to_float(cur.get("wave_period")),
        "swell_height": to_float(cur.get("swell_wave_height")),
        "sea_temperature": to_float(cur.get("sea_surface_temperature")),
    }

    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    dates = daily.get("time") if isinstance(daily.get("time"), list) else []
    days = []
    for i, date_str in enumerate(dates):
        if not isinstance(date_str, str) or len(date_str) != 10:
            continue
        days.append({
            "date": date_str,
            "wave_max": to_float(_column(daily, "wave_height_max", i)),
            "direction": to_float(_column(daily, "wave_direction_dominant", i)),
            "period_max": to_float(_column(daily, "wave_period_max", i)),
            "swell_max": to_float(_column(daily, "swell_wave_height_max", i)),
        })

    hourly = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
    hours = hourly.get("time") if isinstance(hourly.get("time"), list) else []
    sea_level = [[hour, to_float(_column(hourly, "sea_level_height_msl", i))]
                 for i, hour in enumerate(hours) if _is_hour(hour)]

    forecast = {
        "timezone": str(payload.get("timezone") or ""),
        "utc_offset_seconds": to_int(payload.get("utc_offset_seconds")) or 0,
        "current": current,
        "daily": days,
        "sea_level": sea_level,
    }
    forecast["has_data"] = has_sea_data(forecast)
    return forecast


def parse_places(payload):
    """Open-Meteo geocoding JSON -> list of location dicts (possibly empty)."""
    results = payload.get("results") if isinstance(payload, dict) else None
    places = []
    for item in results if isinstance(results, list) else []:
        place = normalize_location(item)
        if place:
            places.append(place)
    return places


def place_label(place):
    """'Name, Region, Country', skipping empty or repeated parts."""
    parts = []
    for key in ("name", "admin1", "country"):
        value = str((place or {}).get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


# ------------------------------------------------------------
# Settings and cache (both come from disk and may be missing or corrupt)
# ------------------------------------------------------------

def normalize_location(raw):
    """A clean location dict, or None if `raw` is not a usable place."""
    if not isinstance(raw, dict):
        return None
    lat, lon = to_float(raw.get("latitude")), to_float(raw.get("longitude"))
    name = str(raw.get("name") or "").strip()
    if lat is None or lon is None or not name or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {
        "name": name,
        "admin1": str(raw.get("admin1") or "").strip(),
        "country": str(raw.get("country") or "").strip(),
        "latitude": lat,
        "longitude": lon,
        "timezone": str(raw.get("timezone") or "").strip(),
    }


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    height = to_float(raw.get("alert_height"))
    alert_date = raw.get("alert_date")
    return {
        # "main", a place id or "own" (core.places); None until decided.
        "place": core.places.normalize_choice(raw.get("place")),
        "location": normalize_location(raw.get("location")),
        "alert": raw.get("alert") is True,
        "alert_height": height if height in ALERT_HEIGHTS else DEFAULT_ALERT_HEIGHT,
        "alert_date": alert_date if isinstance(alert_date, str) and len(alert_date) == 10 else "",
    }


def make_cache(location, forecast, now=None):
    # Kept for the point that was asked about (rounded), not the exact one.
    lat, lon = query_point(location["latitude"], location["longitude"])
    return {
        "fetched_at": time.time() if now is None else now,
        "latitude": lat,
        "longitude": lon,
        "forecast": forecast,
    }


def normalize_cache(raw):
    """The cache dict if it is well formed, else None."""
    if not isinstance(raw, dict):
        return None
    forecast = raw.get("forecast")
    if (to_float(raw.get("fetched_at")) is None or to_float(raw.get("latitude")) is None
            or to_float(raw.get("longitude")) is None or not isinstance(forecast, dict)):
        return None
    try:
        if (not isinstance(forecast.get("current"), dict)
                or not isinstance(forecast.get("daily"), list)
                or not isinstance(forecast.get("sea_level"), list)):
            return None
        cur = forecast["current"]
        for key in ("wave_height", "wave_direction", "wave_period", "swell_height",
                    "sea_temperature"):
            cur[key] = to_float(cur.get(key))
        forecast["daily"] = [d for d in forecast["daily"]
                             if isinstance(d, dict) and isinstance(d.get("date"), str)]
        forecast["sea_level"] = [[p[0], to_float(p[1])] for p in forecast["sea_level"]
                                 if isinstance(p, list) and len(p) == 2 and _is_hour(p[0])]
        forecast["utc_offset_seconds"] = to_int(forecast.get("utc_offset_seconds")) or 0
        forecast["has_data"] = has_sea_data(forecast)
    except Exception:
        return None
    return raw


def cache_matches(cache, location):
    """Whether the cache answers for `location` (compared at the rounded point)."""
    if not cache or not location:
        return False
    try:
        lat, lon = query_point(location["latitude"], location["longitude"])
        return (abs(float(cache["latitude"]) - lat) < 1e-4
                and abs(float(cache["longitude"]) - lon) < 1e-4)
    except (KeyError, TypeError, ValueError):
        return False


def cache_age(cache, now=None):
    fetched = to_float((cache or {}).get("fetched_at"))
    if fetched is None:
        return None
    return (time.time() if now is None else now) - fetched


def is_fresh(cache, max_age, now=None):
    """True if the cache is younger than `max_age` seconds. A timestamp in the
    future (clock changed) counts as stale."""
    age = cache_age(cache, now)
    return age is not None and 0 <= age <= max_age


# ------------------------------------------------------------
# Dates and the alert
# ------------------------------------------------------------

def location_now(forecast, now_utc=None):
    """The wall-clock time at the forecast's location (naive), from its UTC offset."""
    if now_utc is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
    offset = to_int((forecast or {}).get("utc_offset_seconds")) or 0
    return (now_utc + datetime.timedelta(seconds=offset)).replace(tzinfo=None)


def location_today(forecast, now_utc=None):
    return location_now(forecast, now_utc).strftime("%Y-%m-%d")


def day_entry(forecast, date_str):
    for day in (forecast or {}).get("daily") or []:
        if day.get("date") == date_str:
            return day
    return None


def todays_highest_wave(forecast, now_utc=None):
    """The highest wave expected today at the place (the current height or
    today's forecast maximum), or None."""
    heights = [(forecast.get("current") or {}).get("wave_height")]
    today = day_entry(forecast, location_today(forecast, now_utc))
    if today:
        heights.append(today.get("wave_max"))
    heights = [h for h in heights if h is not None]
    return max(heights) if heights else None


def alert_height(forecast, threshold, now_utc=None):
    """Today's highest wave when it reaches `threshold` metres, else None."""
    if not forecast or not forecast.get("has_data"):
        return None
    highest = todays_highest_wave(forecast, now_utc)
    return highest if highest is not None and highest >= threshold else None


def should_alert(settings, forecast, today_str, now_utc=None):
    """The wave height to announce, or None: alerts on, not announced on
    `today_str` yet, and today's waves reach the chosen height."""
    if not settings.get("alert") or settings.get("alert_date") == today_str:
        return None
    return alert_height(forecast, settings.get("alert_height", DEFAULT_ALERT_HEIGHT), now_utc)
