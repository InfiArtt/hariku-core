# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Open-Meteo access for the Weather extension: request URLs, the HTTP fetch, and
turning the JSON into plain dicts, plus the pure helpers for settings, the cache
and unit conversion. No wx and no translated text, so tests can drive it with
sample responses.

fetch_json(), fetch_forecast() and search_places() block on the network: call
them from a worker thread only.
"""

import datetime
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from core.constants import CORE_VERSION

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = f"HarikuV2/{CORE_VERSION} (Weather extension)"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 1024 * 1024
FORECAST_DAYS = 7
SEARCH_COUNT = 10

CURRENT_FIELDS = ("temperature_2m", "relative_humidity_2m", "apparent_temperature",
                  "weather_code", "wind_speed_10m")
DAILY_FIELDS = ("weather_code", "temperature_2m_max", "temperature_2m_min",
                "precipitation_probability_max")

UNITS = ("metric", "imperial")   # metric: Celsius + km/h, imperial: Fahrenheit + mph


class WeatherError(Exception):
    """A failed request. `kind` is "offline", "service" or "bad_response"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


# ------------------------------------------------------------
# Requests
# ------------------------------------------------------------

def build_forecast_url(latitude, longitude, timezone=""):
    # Always metric; weather_text converts for imperial users, so a unit change
    # never needs a new request.
    params = {
        "latitude": f"{float(latitude):.4f}",
        "longitude": f"{float(longitude):.4f}",
        "current": ",".join(CURRENT_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
        "timezone": timezone or "auto",
        "forecast_days": FORECAST_DAYS,
    }
    return FORECAST_URL + "?" + urllib.parse.urlencode(params)


def build_search_url(name, language="en"):
    params = {
        "name": (name or "").strip(),
        "count": SEARCH_COUNT,
        "language": language if language in ("en", "id") else "en",
        "format": "json",
    }
    return GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def fetch_json(url):
    """GET `url` and decode its JSON body. Raises WeatherError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise WeatherError("service", f"HTTP {e.code}") from e
    except Exception as e:  # URLError, timeouts, resets: treat as unreachable
        raise WeatherError("offline", str(e)) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise WeatherError("bad_response", "response too large")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise WeatherError("bad_response", str(e)) from e


def fetch_forecast(latitude, longitude, timezone=""):
    return parse_forecast(fetch_json(build_forecast_url(latitude, longitude, timezone)))


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


def parse_forecast(payload):
    """Open-Meteo forecast JSON -> {"timezone", "utc_offset_seconds",
    "current": {...}, "daily": [{...}, ...]}. Raises WeatherError."""
    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise WeatherError("bad_response", "no current conditions")
    cur = payload["current"]
    current = {
        "time": str(cur.get("time") or ""),
        "temperature": to_float(cur.get("temperature_2m")),
        "feels_like": to_float(cur.get("apparent_temperature")),
        "humidity": to_int(cur.get("relative_humidity_2m")),
        "wind_speed": to_float(cur.get("wind_speed_10m")),
        "code": to_int(cur.get("weather_code")),
    }
    if current["temperature"] is None:
        raise WeatherError("bad_response", "no current temperature")

    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    dates = daily.get("time") if isinstance(daily.get("time"), list) else []
    days = []
    for i, date_str in enumerate(dates):
        if not isinstance(date_str, str) or len(date_str) != 10:
            continue
        days.append({
            "date": date_str,
            "code": to_int(_column(daily, "weather_code", i)),
            "high": to_float(_column(daily, "temperature_2m_max", i)),
            "low": to_float(_column(daily, "temperature_2m_min", i)),
            "rain_chance": to_int(_column(daily, "precipitation_probability_max", i)),
        })

    return {
        "timezone": str(payload.get("timezone") or ""),
        "utc_offset_seconds": to_int(payload.get("utc_offset_seconds")) or 0,
        "current": current,
        "daily": days,
    }


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
    units = raw.get("units")
    return {
        "location": normalize_location(raw.get("location")),
        "units": units if units in UNITS else "metric",
    }


def make_cache(location, forecast, now=None):
    return {
        "fetched_at": time.time() if now is None else now,
        "latitude": location["latitude"],
        "longitude": location["longitude"],
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
        # Re-validate the stored forecast the same way as a fresh response.
        if not isinstance(forecast.get("current"), dict) or not isinstance(forecast.get("daily"), list):
            return None
        if to_float(forecast["current"].get("temperature")) is None:
            return None
        forecast["daily"] = [d for d in forecast["daily"]
                             if isinstance(d, dict) and isinstance(d.get("date"), str)]
    except Exception:
        return None
    return raw


def cache_matches(cache, location):
    if not cache or not location:
        return False
    try:
        return (abs(float(cache["latitude"]) - float(location["latitude"])) < 1e-4
                and abs(float(cache["longitude"]) - float(location["longitude"])) < 1e-4)
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
# Dates and units
# ------------------------------------------------------------

def location_today(forecast, now_utc=None):
    """Today's date (YYYY-MM-DD) at the forecast's location, from its UTC offset."""
    if now_utc is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
    offset = to_int((forecast or {}).get("utc_offset_seconds")) or 0
    return (now_utc + datetime.timedelta(seconds=offset)).strftime("%Y-%m-%d")


def day_entry(forecast, date_str):
    for day in (forecast or {}).get("daily") or []:
        if day.get("date") == date_str:
            return day
    return None


def convert_temperature(celsius, units):
    if celsius is None:
        return None
    return celsius * 9 / 5 + 32 if units == "imperial" else celsius


def convert_speed(kmh, units):
    if kmh is None:
        return None
    return kmh / 1.609344 if units == "imperial" else kmh
