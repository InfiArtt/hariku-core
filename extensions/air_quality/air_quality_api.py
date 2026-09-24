# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Open-Meteo access for the Air Quality extension: request URLs, the HTTP fetch,
and turning the Air Quality API JSON into plain dicts, plus the pure helpers
for categories, settings, the cache and the unhealthy-air alert. No wx and no
translated text, so tests can drive it with sample responses.

Privacy (core 2.8): the Air Quality API gets the place rounded to 2 decimals
(about 1 km), never more; the cache is kept for that rounded point.

fetch_json(), fetch_air() and search_places() block on the network: call them
from a worker thread only.
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

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = f"HarikuV2/{CORE_VERSION} (Air Quality extension)"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 1024 * 1024
FORECAST_DAYS = 5    # the global CAMS forecast reaches about 5 days
SEARCH_COUNT = 10

# Each pollutant's own US AQI; the highest one sets the index.
POLLUTANTS = ("pm2_5", "pm10", "ozone", "nitrogen_dioxide", "carbon_monoxide",
              "sulphur_dioxide")
CURRENT_FIELDS = ("us_aqi", "pm2_5", "pm10", "uv_index") + tuple(f"us_aqi_{p}" for p in POLLUTANTS)
HOURLY_FIELDS = ("us_aqi", "pm2_5", "uv_index")

QUERY_DECIMALS = 2   # the point Open-Meteo gets: about 1 km

# US AQI (U.S. EPA): highest index of each category.
AQI_CATEGORIES = ((50, "good"), (100, "moderate"), (150, "sensitive"), (200, "unhealthy"),
                  (300, "very_unhealthy"), (None, "hazardous"))
UNHEALTHY_AQI = 151
# UV index (WHO): highest rounded value of each category.
UV_CATEGORIES = ((2, "low"), (5, "moderate"), (7, "high"), (10, "very_high"), (None, "extreme"))


class AirError(Exception):
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


def build_air_url(latitude, longitude, timezone=""):
    # Always rounded here, so an exact point can never reach the URL.
    lat, lon = query_point(latitude, longitude)
    params = {
        "latitude": f"{lat:.{QUERY_DECIMALS}f}",
        "longitude": f"{lon:.{QUERY_DECIMALS}f}",
        "current": ",".join(CURRENT_FIELDS),
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": timezone or "auto",
        "forecast_days": FORECAST_DAYS,
    }
    return AIR_URL + "?" + urllib.parse.urlencode(params)


def build_search_url(name, language="en"):
    params = {
        "name": (name or "").strip(),
        "count": SEARCH_COUNT,
        "language": language if language in ("en", "id") else "en",
        "format": "json",
    }
    return GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def fetch_json(url):
    """GET `url` and decode its JSON body. Raises AirError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise AirError("service", f"HTTP {e.code}") from e
    except Exception as e:  # URLError, timeouts, resets: treat as unreachable
        raise AirError("offline", str(e)) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise AirError("bad_response", "response too large")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise AirError("bad_response", str(e)) from e


def fetch_air(latitude, longitude, timezone=""):
    return parse_air(fetch_json(build_air_url(latitude, longitude, timezone)))


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
    """The nearest whole number (halves up, not to even), or None."""
    number = to_float(value)
    if number is None:
        return None
    return int(number + 0.5) if number >= 0 else -int(-number + 0.5)


def _column(block, name, index):
    values = block.get(name)
    if isinstance(values, list) and index < len(values):
        return values[index]
    return None


def _is_hour(text):
    return isinstance(text, str) and len(text) == 16 and text[10:11] == "T"


def main_pollutant(sub_indices):
    """The pollutant with the highest US AQI of its own, or None."""
    best, best_value = None, None
    for name in POLLUTANTS:
        value = to_float((sub_indices or {}).get(name))
        if value is not None and (best_value is None or value > best_value):
            best, best_value = name, value
    return best


def has_air_data(forecast):
    cur = forecast.get("current") or {}
    if cur.get("aqi") is not None or cur.get("pm2_5") is not None:
        return True
    return any(h.get("aqi") is not None for h in forecast.get("hourly") or [])


def parse_air(payload):
    """Air Quality API JSON -> {"timezone", "utc_offset_seconds", "current":
    {...}, "hourly": [{"time", "aqi", "pm2_5", "uv"}], "has_data"}. Raises
    AirError for anything unreadable."""
    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise AirError("bad_response", "no current conditions")
    cur = payload["current"]
    current = {
        "time": str(cur.get("time") or ""),
        "aqi": to_int(cur.get("us_aqi")),
        "pm2_5": to_float(cur.get("pm2_5")),
        "pm10": to_float(cur.get("pm10")),
        "uv": to_float(cur.get("uv_index")),
        "main_pollutant": main_pollutant({p: cur.get(f"us_aqi_{p}") for p in POLLUTANTS}),
    }

    block = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
    hours = block.get("time") if isinstance(block.get("time"), list) else []
    hourly = []
    for i, hour in enumerate(hours):
        if not _is_hour(hour):
            continue
        hourly.append({
            "time": hour,
            "aqi": to_int(_column(block, "us_aqi", i)),
            "pm2_5": to_float(_column(block, "pm2_5", i)),
            "uv": to_float(_column(block, "uv_index", i)),
        })

    forecast = {
        "timezone": str(payload.get("timezone") or ""),
        "utc_offset_seconds": to_int(payload.get("utc_offset_seconds")) or 0,
        "current": current,
        "hourly": hourly,
    }
    forecast["has_data"] = has_air_data(forecast)
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
# Categories
# ------------------------------------------------------------

def aqi_category(aqi):
    """"good" ... "hazardous" for a US AQI value, or None."""
    if aqi is None:
        return None
    for limit, key in AQI_CATEGORIES:
        if limit is None or aqi <= limit:
            return key
    return "hazardous"


def uv_value(uv):
    """The UV index as it is reported: a whole number, halves rounded up."""
    return None if uv is None else int(max(0.0, uv) + 0.5)


def uv_category(uv):
    value = uv_value(uv)
    if value is None:
        return None
    for limit, key in UV_CATEGORIES:
        if limit is None or value <= limit:
            return key
    return "extreme"


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
    alert_date = raw.get("alert_date")
    return {
        # "main", a place id or "own" (core.places); None until decided.
        "place": core.places.normalize_choice(raw.get("place")),
        "location": normalize_location(raw.get("location")),
        "alert": raw.get("alert") is True,
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
        if not isinstance(forecast.get("current"), dict) or not isinstance(forecast.get("hourly"), list):
            return None
        cur = forecast["current"]
        cur["aqi"] = to_int(cur.get("aqi"))
        for key in ("pm2_5", "pm10", "uv"):
            cur[key] = to_float(cur.get(key))
        if cur.get("main_pollutant") not in POLLUTANTS:
            cur["main_pollutant"] = None
        forecast["hourly"] = [{"time": h["time"], "aqi": to_int(h.get("aqi")),
                               "pm2_5": to_float(h.get("pm2_5")), "uv": to_float(h.get("uv"))}
                              for h in forecast["hourly"]
                              if isinstance(h, dict) and _is_hour(h.get("time"))]
        forecast["utc_offset_seconds"] = to_int(forecast.get("utc_offset_seconds")) or 0
        forecast["has_data"] = has_air_data(forecast)
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
# Times, the forecast summary and the alert
# ------------------------------------------------------------

def location_now(forecast, now_utc=None):
    """The wall-clock time at the forecast's location (naive), from its UTC offset."""
    if now_utc is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
    offset = to_int((forecast or {}).get("utc_offset_seconds")) or 0
    return (now_utc + datetime.timedelta(seconds=offset)).replace(tzinfo=None)


def coming_hours(forecast, now_utc=None, count=8, step=3):
    """Hourly entries from the current hour on, every `step` hours, at most `count`."""
    start = location_now(forecast, now_utc).strftime("%Y-%m-%dT%H:00")
    ahead = [h for h in forecast.get("hourly") or [] if h["time"] >= start]
    return ahead[::step][:count]


def daily_summary(forecast, now_utc=None):
    """[{"date", "aqi_max", "pm2_5_max", "uv_max"}] from today on, from the hourly data."""
    today = location_now(forecast, now_utc).strftime("%Y-%m-%d")
    days = {}
    for hour in forecast.get("hourly") or []:
        date_str = hour["time"][:10]
        if date_str < today:
            continue
        day = days.setdefault(date_str, {"date": date_str, "aqi_max": None,
                                         "pm2_5_max": None, "uv_max": None})
        for source, target in (("aqi", "aqi_max"), ("pm2_5", "pm2_5_max"), ("uv", "uv_max")):
            value = hour.get(source)
            if value is not None and (day[target] is None or value > day[target]):
                day[target] = value
    return [days[d] for d in sorted(days)]


def should_alert(settings, forecast, today_str):
    """The index to announce, or None: alerts on, not announced on `today_str`
    yet, and the air is now unhealthy or worse."""
    if not settings.get("alert") or settings.get("alert_date") == today_str:
        return None
    aqi = ((forecast or {}).get("current") or {}).get("aqi")
    return aqi if aqi is not None and aqi >= UNHEALTHY_AQI else None
