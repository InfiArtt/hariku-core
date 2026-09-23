# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Earthquake data for the Earthquakes & Tsunami extension: request URLs, the
HTTP fetch, turning BMKG and USGS JSON into plain dicts, city search
(Open-Meteo), and the pure helpers for settings, the cache and distances. No wx
and no translated text, so tests can drive it with sample responses.

Every parsed quake is a dict with the same keys (see normalize_quake). BMKG's
own text (Wilayah, Potensi, Dirasakan, Tanggal, Jam, Lintang, Bujur, Kedalaman)
is kept as BMKG wrote it, only with runs of whitespace collapsed.

Privacy: the BMKG and USGS requests are plain downloads of public files; they
carry no location. Only a city search sends what the user typed (to Open-Meteo).

fetch_json() and the fetch_* / search_places() helpers block on the network:
call them from a worker thread only.
"""

import datetime
import json
import logging
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from core.constants import CORE_VERSION

logger = logging.getLogger(__name__)

AUTOGEMPA_URL = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
TERKINI_URL = "https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json"
DIRASAKAN_URL = "https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json"
USGS_HOUR_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_hour.geojson"
USGS_DAY_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = f"HarikuV2/{CORE_VERSION} (Earthquake extension)"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 1024 * 1024
SEARCH_COUNT = 10

EARTH_RADIUS_KM = 6371.0

ALERT_DISTANCES_KM = (100, 300, 500, 1000)
DEFAULT_ALERT_KM = 300
MIN_MAGNITUDES = (3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0)
DEFAULT_MIN_MAGNITUDE = 4.0
WORLD_ALERT_MAGNITUDE = 6.5   # USGS worldwide alerts
WORLD_LIST_MAGNITUDE = 5.0    # USGS rows in the recent list
WORLD_LIST_MAX_AGE = 24 * 3600
FELT_NAMES_MAX = 200

# Two reports are the same earthquake when this close in time and place (BMKG
# and USGS locate the same quake a little differently).
SAME_EVENT_SECONDS = 120
SAME_EVENT_KM = 150

HISTORY_MAX_AGE = 2 * 86400
HISTORY_MAX = 50

# BMKG writes its times in Indonesian zones.
ZONE_OFFSETS = {"WIB": 7, "WITA": 8, "WIT": 9, "UTC": 0, "GMT": 0}
DEFAULT_ZONE = "WIB"
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7,
           "agu": 8, "agt": 8, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11,
           "des": 12, "dec": 12}

_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_CLOCK = re.compile(r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?\s*([A-Za-z]{2,4})?")
_DATE = re.compile(r"(\d{1,2})\s*[- ]\s*([A-Za-z]{3,})\s*[- ]\s*(\d{4})")

# Potensi wording. BMKG says "Tidak berpotensi tsunami" when there is none;
# anything that mentions tsunami potential without a negation counts.
_TSUNAMI_POSITIVE = ("berpotensi tsunami", "potensi tsunami", "peringatan dini tsunami",
                     "waspada tsunami", "awas tsunami", "tsunami warning")
_TSUNAMI_NEGATIVE = ("tidak berpotensi", "tidak ada potensi", "tidak memiliki potensi",
                     "tanpa potensi", "tidak menimbulkan tsunami", "no tsunami")

QUAKE_TEXT_FIELDS = ("region", "potential", "felt", "clock", "zone", "date_text",
                     "time_text", "lat_text", "lon_text", "depth_text")


class QuakeError(Exception):
    """A failed request. `kind` is "offline", "service" or "bad_response"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


# ------------------------------------------------------------
# Requests
# ------------------------------------------------------------

def build_search_url(name, language="en"):
    params = {
        "name": (name or "").strip(),
        "count": SEARCH_COUNT,
        "language": language if language in ("en", "id") else "en",
        "format": "json",
    }
    return GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def fetch_json(url):
    """GET `url` and decode its JSON body. Raises QuakeError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise QuakeError("service", f"HTTP {e.code}") from e
    except Exception as e:  # URLError, timeouts, resets: treat as unreachable
        raise QuakeError("offline", str(e)) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise QuakeError("bad_response", "response too large")
    try:
        # BMKG's files sometimes start with a byte-order mark.
        return json.loads(body.decode("utf-8-sig"))
    except ValueError as e:
        raise QuakeError("bad_response", str(e)) from e


def fetch_latest():
    """BMKG's latest earthquake (autogempa.json)."""
    return parse_autogempa(fetch_json(AUTOGEMPA_URL))


def fetch_bmkg_lists():
    """BMKG's recent M5+ list and felt list, merged. Two requests, one after
    the other."""
    recent = parse_bmkg_list(fetch_json(TERKINI_URL))
    felt = parse_bmkg_list(fetch_json(DIRASAKAN_URL))
    return merge_bmkg(recent + felt)


def fetch_usgs(url):
    return parse_usgs(fetch_json(url))


def search_places(name, language="en"):
    return parse_places(fetch_json(build_search_url(name, language)))


# ------------------------------------------------------------
# Numbers, places and times in BMKG's text
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


def parse_number(value):
    """The first number in `value`: 4.7, "4.7", "9 km", "2.13 LS", "4,7"."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return to_float(value)
    if not isinstance(value, str):
        return None
    match = _NUMBER.search(value)
    return to_float(match.group(0).replace(",", ".")) if match else None


def parse_latitude(text):
    """ "8.21 LS" -> -8.21 (Lintang Selatan, south); "4.74 LU" -> 4.74."""
    value = parse_number(text)
    if value is None:
        return None
    hemisphere = re.sub(r"[^A-Z]", "", str(text).upper())
    if hemisphere in ("LS", "S") and value > 0:
        value = -value
    return value if -90 <= value <= 90 else None


def parse_longitude(text):
    """ "120.61 BT" -> 120.61 (Bujur Timur, east); "BB" or "W" is west."""
    value = parse_number(text)
    if value is None:
        return None
    hemisphere = re.sub(r"[^A-Z]", "", str(text).upper())
    if hemisphere in ("BB", "W") and value > 0:
        value = -value
    return value if -180 <= value <= 180 else None


def parse_coordinates(text):
    """ "-8.21,120.61" -> (-8.21, 120.61), or (None, None)."""
    parts = str(text or "").split(",")
    if len(parts) != 2:
        return None, None
    lat, lon = to_float(parts[0].strip()), to_float(parts[1].strip())
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon


def parse_iso_time(text):
    """Epoch seconds from BMKG's DateTime ("2026-09-23T02:02:44+00:00")."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        when = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when.timestamp()


def parse_clock(jam):
    """("09:02", "WIB") from "09:02:44 WIB"; ("", "") if unreadable."""
    match = _CLOCK.search(str(jam or ""))
    if not match:
        return "", ""
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return "", ""
    zone = (match.group(4) or "").upper()
    return f"{hour:02d}:{minute:02d}", zone if zone in ZONE_OFFSETS else ""


def parse_local_time(tanggal, jam):
    """Epoch seconds from BMKG's Tanggal ("23 Sep 2026") and Jam ("09:02:44
    WIB"), for entries without a DateTime."""
    date_match = _DATE.search(str(tanggal or ""))
    clock_match = _CLOCK.search(str(jam or ""))
    if not date_match or not clock_match:
        return None
    month = _MONTHS.get(date_match.group(2)[:3].lower())
    if not month:
        return None
    zone = (clock_match.group(4) or DEFAULT_ZONE).upper()
    offset = ZONE_OFFSETS.get(zone, ZONE_OFFSETS[DEFAULT_ZONE])
    try:
        local = datetime.datetime(int(date_match.group(3)), month, int(date_match.group(1)),
                                  int(clock_match.group(1)), int(clock_match.group(2)),
                                  int(clock_match.group(3) or 0),
                                  tzinfo=datetime.timezone(datetime.timedelta(hours=offset)))
    except ValueError:
        return None
    return local.timestamp()


def zone_date(timestamp, zone):
    """The calendar date of `timestamp` in a BMKG zone (WIB when unknown)."""
    offset = ZONE_OFFSETS.get(zone or DEFAULT_ZONE, ZONE_OFFSETS[DEFAULT_ZONE])
    return (datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
            + datetime.timedelta(hours=offset)).date()


def zone_clock(timestamp, zone):
    offset = ZONE_OFFSETS.get(zone or DEFAULT_ZONE, ZONE_OFFSETS[DEFAULT_ZONE])
    return (datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
            + datetime.timedelta(hours=offset)).strftime("%H:%M")


def clean_text(value):
    """BMKG's text with runs of whitespace collapsed; "" for non-strings."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _normalize_for_match(text):
    return " ".join(str(text or "").lower().replace("-", " ").split())


def is_tsunami_potential(potential):
    """True when BMKG's Potensi statement mentions tsunami potential and does
    not deny it ("Tidak berpotensi tsunami" is False)."""
    text = _normalize_for_match(potential)
    if "tsunami" not in text:
        return False
    if any(neg in text for neg in _TSUNAMI_NEGATIVE):
        return False
    return any(pos in text for pos in _TSUNAMI_POSITIVE)


# ------------------------------------------------------------
# Quakes
# ------------------------------------------------------------

def normalize_quake(raw):
    """A clean quake dict, or None if `raw` has no id or magnitude. Used for
    fresh responses and for quakes read back from the cache."""
    if not isinstance(raw, dict):
        return None
    source = raw.get("source")
    ident = clean_text(raw.get("id"))
    magnitude = to_float(raw.get("magnitude"))
    if source not in ("bmkg", "usgs") or not ident or magnitude is None:
        return None
    lat, lon = to_float(raw.get("lat")), to_float(raw.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat = lon = None
    quake = {
        "source": source,
        "id": ident,
        "time": to_float(raw.get("time")),
        "magnitude": magnitude,
        "depth_km": to_float(raw.get("depth_km")),
        "lat": lat,
        "lon": lon,
        "tsunami_flag": raw.get("tsunami_flag") is True,
    }
    for key in QUAKE_TEXT_FIELDS:
        quake[key] = clean_text(raw.get(key))
    if quake["zone"] not in ZONE_OFFSETS:
        quake["zone"] = ""
    return quake


def parse_bmkg_quake(raw):
    """One entry of a BMKG file -> quake dict, or None when unusable."""
    if not isinstance(raw, dict):
        return None
    date_time = clean_text(raw.get("DateTime"))
    tanggal, jam = clean_text(raw.get("Tanggal")), clean_text(raw.get("Jam"))
    when = parse_iso_time(date_time)
    if when is None:
        when = parse_local_time(tanggal, jam)
    clock, zone = parse_clock(jam)
    if not clock and when is not None:
        clock, zone = zone_clock(when, DEFAULT_ZONE), DEFAULT_ZONE
    lat, lon = parse_coordinates(raw.get("Coordinates"))
    if lat is None:
        lat, lon = parse_latitude(raw.get("Lintang")), parse_longitude(raw.get("Bujur"))
        if lat is None or lon is None:
            lat = lon = None
    ident = date_time or (f"{tanggal} {jam}".strip() if tanggal and jam else "")
    return normalize_quake({
        "source": "bmkg",
        "id": ident,
        "time": when,
        "magnitude": parse_number(raw.get("Magnitude")),
        "depth_km": parse_number(raw.get("Kedalaman")),
        "lat": lat,
        "lon": lon,
        "region": raw.get("Wilayah"),
        "potential": raw.get("Potensi"),
        "felt": raw.get("Dirasakan"),
        "clock": clock,
        "zone": zone,
        "date_text": tanggal,
        "time_text": jam,
        "lat_text": raw.get("Lintang"),
        "lon_text": raw.get("Bujur"),
        "depth_text": raw.get("Kedalaman"),
    })


def _bmkg_entries(payload):
    info = payload.get("Infogempa") if isinstance(payload, dict) else None
    if not isinstance(info, dict) or "gempa" not in info:
        raise QuakeError("bad_response", "no Infogempa.gempa")
    return info["gempa"]


def parse_autogempa(payload):
    """autogempa.json -> the latest quake. Raises QuakeError."""
    entry = _bmkg_entries(payload)
    if isinstance(entry, list):  # tolerate a one-item list
        entry = entry[0] if entry else None
    quake = parse_bmkg_quake(entry)
    if quake is None:
        raise QuakeError("bad_response", "unreadable latest earthquake")
    return quake


def parse_bmkg_list(payload):
    """gempaterkini.json / gempadirasakan.json -> list of quakes (unusable
    entries are dropped). Raises QuakeError when the shape is wrong."""
    entries = _bmkg_entries(payload)
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        raise QuakeError("bad_response", "gempa is not a list")
    return [q for q in (parse_bmkg_quake(e) for e in entries) if q]


def parse_usgs(payload):
    """A USGS GeoJSON summary feed -> list of quakes. Raises QuakeError."""
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise QuakeError("bad_response", "no features")
    quakes = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        if not isinstance(props, dict) or props.get("type", "earthquake") != "earthquake":
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") \
            if isinstance(feature.get("geometry"), dict) else None
        coords = coords if isinstance(coords, list) else []
        millis = to_float(props.get("time"))
        quake = normalize_quake({
            "source": "usgs",
            "id": feature.get("id") or props.get("code"),
            "time": millis / 1000.0 if millis is not None else None,
            "magnitude": props.get("mag"),
            "depth_km": coords[2] if len(coords) > 2 else None,
            "lat": coords[1] if len(coords) > 1 else None,
            "lon": coords[0] if coords else None,
            "region": props.get("place") or props.get("title"),
            "tsunami_flag": to_float(props.get("tsunami")) == 1,
        })
        if quake:
            quakes.append(quake)
    return quakes


def merge_bmkg(quakes):
    """Merge reports of the same BMKG quake (same id). Later reports fill in or
    replace fields, so pass the most recently fetched last."""
    merged = {}
    for quake in quakes:
        if not quake:
            continue
        current = merged.get(quake["id"])
        if current is None:
            merged[quake["id"]] = dict(quake)
            continue
        for key, value in quake.items():
            if value not in (None, "", False):
                current[key] = value
    return list(merged.values())


def sort_newest_first(quakes):
    return sorted(quakes, key=lambda q: q["time"] if q.get("time") is not None else -1e18,
                  reverse=True)


def same_event(a, b):
    """True when two reports (e.g. BMKG and USGS) describe the same quake."""
    if a.get("time") is None or b.get("time") is None:
        return False
    if abs(a["time"] - b["time"]) > SAME_EVENT_SECONDS:
        return False
    if a.get("lat") is None or b.get("lat") is None:
        return False
    km, _bearing = distance_and_bearing(a["lat"], a["lon"], b["lat"], b["lon"])
    return km <= SAME_EVENT_KM


def world_list(quakes, now):
    """USGS quakes for the recent list: M5+ from the last 24 hours."""
    return [q for q in quakes
            if q["magnitude"] >= WORLD_LIST_MAGNITUDE - 1e-9 and q.get("time") is not None
            and -3600 <= now - q["time"] <= WORLD_LIST_MAX_AGE]


def recent_quakes(cache, include_world, now):
    """The rows of the recent list: every BMKG quake known (its lists, the
    poll history and the latest quake, merged), plus (optionally) USGS's M5+
    from the last day that BMKG did not report, newest first."""
    bmkg = known_bmkg(cache)
    rows = list(bmkg)
    if include_world:
        for quake in world_list(cache.get("world_day") or [], now):
            if not any(same_event(quake, other) for other in bmkg):
                rows.append(quake)
    return sort_newest_first(rows)


def known_bmkg(cache):
    """Every BMKG quake the cache knows, merged by id: the poll history, then
    BMKG's lists, then the latest quake, so fresher reports fill in or
    replace older ones (BMKG adds felt reports after its first release)."""
    return merge_bmkg(list(cache.get("history") or []) + list(cache.get("lists") or [])
                      + [cache.get("latest")])


def latest_near(quakes, location, radius_km, now, max_age):
    """The newest quake within `radius_km` of the location and `max_age`
    seconds, or None."""
    if not location:
        return None
    for quake in sort_newest_first(quakes):
        when = quake.get("time")
        if when is None or now - when > max_age:
            return None   # newest first: the rest are older still
        found = distance_from(location, quake)
        if found is not None and found[0] <= radius_km and now - when >= -3600:
            return quake
    return None


def add_to_history(history, quake, now):
    """The poll history with `quake` added (merged by id), old ones dropped."""
    history = merge_bmkg(list(history or []) + [quake])
    history = [q for q in history
               if q.get("time") is not None and now - q["time"] <= HISTORY_MAX_AGE]
    return sort_newest_first(history)[:HISTORY_MAX]


# ------------------------------------------------------------
# Geometry
# ------------------------------------------------------------

def distance_and_bearing(lat1, lon1, lat2, lon2):
    """Great-circle distance in km and initial bearing in degrees, 1 -> 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    km = 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return km, (math.degrees(math.atan2(y, x)) + 360) % 360


def compass_index(degrees):
    """0..7 for north, northeast, east, ... northwest."""
    return int(((float(degrees) % 360) + 22.5) // 45) % 8


def distance_from(location, quake):
    """(km, bearing) from the user's location to the epicentre, or None."""
    if not location or quake.get("lat") is None or quake.get("lon") is None:
        return None
    return distance_and_bearing(location["latitude"], location["longitude"],
                                quake["lat"], quake["lon"])


# ------------------------------------------------------------
# City search, settings and the cache
# ------------------------------------------------------------

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
        "admin2": str(raw.get("admin2") or "").strip(),
        "country": str(raw.get("country") or "").strip(),
        "latitude": lat,
        "longitude": lon,
        "timezone": str(raw.get("timezone") or "").strip(),
    }


_REGION_PREFIXES = ("kabupaten ", "kab. ", "kab ", "kota administrasi ", "kotamadya ",
                    "kota ", "regency of ", "city of ")
_REGION_SUFFIXES = (" regency", " city", " district")


def _strip_region_words(name):
    name = " ".join(str(name or "").split())
    lowered = name.lower()
    for prefix in _REGION_PREFIXES:
        if lowered.startswith(prefix):
            name, lowered = name[len(prefix):], lowered[len(prefix):]
            break
    for suffix in _REGION_SUFFIXES:
        if lowered.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name.strip(" ,.")


def region_names(location, extra=""):
    """Names to look for in BMKG's felt reports: the city, its regency (when
    the city search gave one) and the user's own comma-separated extra names."""
    candidates = []
    if location:
        candidates += [location.get("name"), location.get("admin2")]
    candidates += str(extra or "").split(",")
    names = []
    for candidate in candidates:
        name = _strip_region_words(candidate)
        if len(name) >= 3 and name.lower() not in [n.lower() for n in names]:
            names.append(name)
    return names


def felt_in_region(felt, names):
    """True when BMKG's felt report (Dirasakan) names one of `names`, as a
    whole word, ignoring case."""
    text = clean_text(felt)
    if not text:
        return False
    for name in names:
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.IGNORECASE):
            return True
    return False


def default_settings():
    return {
        "location": None,
        "tsunami_alerts": True,
        "nearby_alerts": False,
        "alert_km": DEFAULT_ALERT_KM,
        "min_magnitude": DEFAULT_MIN_MAGNITUDE,
        "felt_alerts": False,
        "felt_names": "",
        "world_alerts": False,
        "list_world": False,
        "sounds": True,
    }


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = default_settings()
    settings["location"] = normalize_location(raw.get("location"))
    for key in ("tsunami_alerts", "nearby_alerts", "felt_alerts", "world_alerts",
                "list_world", "sounds"):
        if isinstance(raw.get(key), bool):
            settings[key] = raw[key]
    if raw.get("alert_km") in ALERT_DISTANCES_KM and not isinstance(raw.get("alert_km"), bool):
        settings["alert_km"] = int(raw["alert_km"])
    magnitude = to_float(raw.get("min_magnitude"))
    for choice in MIN_MAGNITUDES:
        if magnitude is not None and abs(magnitude - choice) < 1e-6:
            settings["min_magnitude"] = choice
    if isinstance(raw.get("felt_names"), str):
        settings["felt_names"] = " ".join(raw["felt_names"].split())[:FELT_NAMES_MAX]
    return settings


def empty_cache():
    return {"latest": None, "latest_at": None, "lists": [], "lists_at": None,
            "world_day": [], "world_day_at": None, "history": []}


def normalize_cache(raw):
    """The cache with every stored quake re-validated; missing parts empty."""
    cache = empty_cache()
    if not isinstance(raw, dict):
        return cache
    cache["latest"] = normalize_quake(raw.get("latest"))
    for key in ("lists", "world_day", "history"):
        items = raw.get(key)
        if isinstance(items, list):
            cache[key] = [q for q in (normalize_quake(i) for i in items) if q]
    for key in ("latest_at", "lists_at", "world_day_at"):
        cache[key] = to_float(raw.get(key))
    return cache


def is_fresh(fetched_at, max_age, now=None):
    """True if `fetched_at` is less than `max_age` seconds ago. A time in the
    future (clock changed) counts as stale."""
    fetched_at = to_float(fetched_at)
    if fetched_at is None:
        return False
    age = (time.time() if now is None else now) - fetched_at
    return 0 <= age <= max_age
