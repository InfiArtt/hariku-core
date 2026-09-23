# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Aircraft data for the Flight Radar extension: request URLs, the HTTP fetch,
turning adsb.fi / adsb.lol JSON into plain dicts, city search (Open-Meteo), and
the pure helpers for settings, the cache, units, the request rate limit,
emergencies and the overhead alerts. No wx and no translated text, so tests can drive it with
sample responses.

Privacy: the user's exact point never leaves the computer. The aircraft
services get it rounded to 2 decimals (about 1 km) with the radius widened to
still cover the user's radius; distances and bearings are then worked out here
from the exact point to each aircraft's own position.

fetch_json(), fetch_aircraft() and search_places() block on the network: call
them from a worker thread only.
"""

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request

from core.constants import CORE_VERSION

logger = logging.getLogger(__name__)

ADSBFI_URL = "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{dist}"
ADSBLOL_URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/{dist}"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = f"HarikuV2/{CORE_VERSION} (Flight Radar extension)"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
SEARCH_COUNT = 10

KM_PER_NM = 1.852
M_PER_FT = 0.3048
EARTH_RADIUS_KM = 6371.0

RADIUS_CHOICES_KM = (10, 25, 50)
DEFAULT_RADIUS_KM = 25
ALERT_CHOICES_KM = (1, 2, 3, 5, 10)
DEFAULT_ALERT_KM = 5
UNITS = ("metric", "aviation")   # metric: km, m, km/h; aviation: nm, ft, kt
LOCATION_KINDS = ("city", "address", "coordinates")

QUERY_DECIMALS = 2               # the point sent to adsb.fi / adsb.lol: about 1.1 km
QUERY_MARGIN_NM = 1.0            # rounding moves the point by at most 0.43 nm

MIN_GAP_SECONDS = 5.0            # never two requests closer than this
RATE_LIMITED_COOLDOWN = 60.0     # after both services answered 429
MAX_BACKOFF_SECONDS = 600.0

GROUND_CATEGORIES = ("C1", "C2")  # surface emergency and service vehicles

# Emergency squawk codes, with the readsb `emergency` value each one means.
EMERGENCY_SQUAWKS = {"7500": "unlawful", "7600": "nordo", "7700": "general"}
# readsb `emergency` values that are emergencies. "lifeguard" (a medical or
# priority flight) is only mentioned in details; "reserved" is ignored.
EMERGENCY_STATUSES = ("general", "minfuel", "nordo", "unlawful", "downed")
KNOWN_STATUSES = EMERGENCY_STATUSES + ("lifeguard",)


class FlightError(Exception):
    """A failed request. `kind` is "offline", "service", "rate_limited" or
    "bad_response"; `status` is the HTTP status when there was one."""

    def __init__(self, kind, detail="", status=None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.status = status


# ------------------------------------------------------------
# Requests
# ------------------------------------------------------------

def query_point(latitude, longitude):
    """The rounded point sent to the aircraft services instead of the exact one."""
    return round(float(latitude), QUERY_DECIMALS), round(float(longitude), QUERY_DECIMALS)


def _coord(value):
    # Always rounded here too, so an exact point can never reach a URL.
    return f"{round(float(value), QUERY_DECIMALS):.{QUERY_DECIMALS}f}"


def build_adsbfi_url(latitude, longitude, radius_nm):
    return ADSBFI_URL.format(lat=_coord(latitude), lon=_coord(longitude), dist=int(radius_nm))


def build_adsblol_url(latitude, longitude, radius_nm):
    return ADSBLOL_URL.format(lat=_coord(latitude), lon=_coord(longitude), dist=int(radius_nm))


# Tried in order; the second only when the first fails.
SOURCES = (("adsb.fi", build_adsbfi_url), ("adsb.lol", build_adsblol_url))


def build_search_url(name, language="en"):
    params = {
        "name": (name or "").strip(),
        "count": SEARCH_COUNT,
        "language": language if language in ("en", "id") else "en",
        "format": "json",
    }
    return GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def fetch_json(url, timeout=TIMEOUT_SECONDS, user_agent=None):
    """GET `url` and decode its JSON body. Raises FlightError."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent or USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        kind = "rate_limited" if e.code == 429 else "service"
        raise FlightError(kind, f"HTTP {e.code}", status=e.code) from e
    except Exception as e:  # URLError, timeouts, resets: treat as unreachable
        raise FlightError("offline", str(e)) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise FlightError("bad_response", "response too large")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise FlightError("bad_response", str(e)) from e


def combined_error_kind(kinds):
    """One error kind for a request that failed at every source."""
    kinds = set(kinds)
    if not kinds:
        return "bad_response"
    if kinds == {"offline"}:
        return "offline"
    if "rate_limited" in kinds:
        return "rate_limited"
    if "service" in kinds or "offline" in kinds:
        return "service"
    return "bad_response"


def fetch_aircraft(latitude, longitude, radius_nm):
    """Aircraft around the user's exact point from adsb.fi, or adsb.lol when
    adsb.fi fails. Only the rounded point is sent; `radius_nm` must already be
    widened (query_radius_nm). Returns (aircraft list, source name) with
    distances from the exact point. Raises FlightError."""
    kinds = []
    sent_lat, sent_lon = query_point(latitude, longitude)
    for name, build_url in SOURCES:
        try:
            payload = fetch_json(build_url(sent_lat, sent_lon, radius_nm))
            return parse_aircraft_list(payload, latitude, longitude), name
        except FlightError as e:
            logger.info(f"[Flight Radar] {name} failed: {e}")
            kinds.append(e.kind)
    raise FlightError(combined_error_kind(kinds))


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


def _text(value):
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def _valid_position(lat, lon):
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def parse_aircraft_list(payload, latitude, longitude):
    """adsb.fi ({"aircraft": [...]}) or adsb.lol ({"ac": [...]}) JSON -> list
    of aircraft dicts, measured from the exact point (latitude, longitude).
    Raises FlightError for anything else."""
    if not isinstance(payload, dict):
        raise FlightError("bad_response", "not an object")
    items = payload.get("aircraft") if "aircraft" in payload else payload.get("ac")
    if not isinstance(items, list):
        raise FlightError("bad_response", "no aircraft list")
    aircraft = []
    for item in items:
        plane = normalize_aircraft(item, latitude, longitude)
        if plane:
            aircraft.append(plane)
    return aircraft


def normalize_aircraft(raw, latitude, longitude):
    """One readsb/tar1090 aircraft object -> a plain dict with its distance and
    bearing from the exact point (latitude, longitude), or None when it has no
    identity or no position. The services' own dst/dir are relative to the
    rounded point, so they are not used."""
    if not isinstance(raw, dict):
        return None
    hex_id = _text(raw.get("hex")).lower()
    callsign = _text(raw.get("flight")).upper()
    registration = _text(raw.get("r")).upper()
    ident = hex_id or callsign or registration
    if not ident:
        return None

    alt = raw.get("alt_baro")
    on_ground = isinstance(alt, str) and alt.strip().lower() == "ground"
    altitude = None if on_ground else to_float(alt)
    if altitude is None and not on_ground:
        altitude = to_float(raw.get("alt_geom"))
    category = _text(raw.get("category")).upper()
    if category in GROUND_CATEGORIES:
        on_ground = True

    lat, lon = to_float(raw.get("lat")), to_float(raw.get("lon"))
    origin_lat, origin_lon = to_float(latitude), to_float(longitude)
    if not _valid_position(lat, lon) or not _valid_position(origin_lat, origin_lon):
        return None
    distance_km, bearing = distance_and_bearing(origin_lat, origin_lon, lat, lon)

    track = to_float(raw.get("track"))
    if track is None:
        track = to_float(raw.get("true_heading"))
    rate = to_float(raw.get("baro_rate"))
    if rate is None:
        rate = to_float(raw.get("geom_rate"))
    emergency = _text(raw.get("emergency")).lower()
    return {
        "id": ident,
        "hex": hex_id,
        "callsign": callsign,
        "registration": registration,
        "type_code": _text(raw.get("t")).upper(),
        "type_desc": _text(raw.get("desc")),
        "on_ground": on_ground,
        "altitude_ft": altitude,
        "speed_kt": to_float(raw.get("gs")),
        "track": None if track is None else track % 360,
        "vertical_rate_fpm": rate,
        "distance_km": distance_km,
        "bearing": bearing % 360,
        "squawk": _text(raw.get("squawk")),
        "emergency": "" if emergency in ("", "none") else emergency,
        "category": category,
        "lat": lat,
        "lon": lon,
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
    """'Name, Region, Country' for a city, skipping empty or repeated parts;
    just the user's name for it ("Home") for an address or coordinates."""
    if (place or {}).get("kind", "city") != "city":
        return str(place.get("name") or "").strip()
    parts = []
    for key in ("name", "admin1", "country"):
        value = str((place or {}).get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


# ------------------------------------------------------------
# Geometry and units
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


def nm_to_km(nm):
    return nm * KM_PER_NM


def km_to_nm(km):
    return km / KM_PER_NM


def ft_to_m(feet):
    return feet * M_PER_FT


def kt_to_kmh(knots):
    return knots * KM_PER_NM


def query_radius_nm(radius_km):
    """Whole nautical miles (the APIs take nm) that cover `radius_km` around the
    exact point when asking around the rounded one: rounding to 2 decimals
    moves the point by at most about 0.79 km (0.43 nm), so 1 nm is added."""
    return max(1, int(math.ceil(km_to_nm(radius_km) + QUERY_MARGIN_NM - 1e-9)))


def visible_aircraft(aircraft, radius_km, include_ground=False):
    """Aircraft within `radius_km`, nearest first; ground traffic only on request."""
    chosen = [a for a in aircraft or []
              if a["distance_km"] <= radius_km + 0.05 and (include_ground or not a["on_ground"])]
    return sorted(chosen, key=lambda a: a["distance_km"])


# ------------------------------------------------------------
# Settings and cache
# ------------------------------------------------------------

def normalize_location(raw):
    """A clean location dict, or None if `raw` is not a usable place. A city
    has name/admin1/country; an address or coordinates also have "kind" and
    "detail" (the address found), and the name the user gave the place."""
    if not isinstance(raw, dict):
        return None
    lat, lon = to_float(raw.get("latitude")), to_float(raw.get("longitude"))
    name = str(raw.get("name") or "").strip()[:100]
    if not name or not _valid_position(lat, lon) or (lat == 0 and lon == 0):
        return None
    location = {
        "name": name,
        "admin1": str(raw.get("admin1") or "").strip(),
        "country": str(raw.get("country") or "").strip(),
        "latitude": lat,
        "longitude": lon,
    }
    kind = raw.get("kind")
    if kind in LOCATION_KINDS and kind != "city":
        location["kind"] = kind
        location["detail"] = str(raw.get("detail") or "").strip()[:500]
    return location


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    radius = raw.get("radius_km")
    alert = raw.get("alert_km")
    units = raw.get("units")
    return {
        "location": normalize_location(raw.get("location")),
        "radius_km": radius if radius in RADIUS_CHOICES_KM and not isinstance(radius, bool)
        else DEFAULT_RADIUS_KM,
        "units": units if units in UNITS else "metric",
        "include_ground": raw.get("include_ground") is True,
        "alerts": raw.get("alerts") is True,
        "alert_km": alert if alert in ALERT_CHOICES_KM and not isinstance(alert, bool)
        else DEFAULT_ALERT_KM,
        "emergency_watch": raw.get("emergency_watch") is True,
    }


def make_cache(location, radius_nm, aircraft, source, now, wall=None):
    """`now` is a monotonic time (freshness); `wall` is for "updated at"."""
    return {
        "fetched_at": now,
        "fetched_wall": time.time() if wall is None else wall,
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "radius_nm": radius_nm,
        "aircraft": aircraft,
        "source": source,
    }


def cache_matches(cache, location, radius_nm):
    if not cache or not location:
        return False
    try:
        return (abs(float(cache["latitude"]) - float(location["latitude"])) < 1e-4
                and abs(float(cache["longitude"]) - float(location["longitude"])) < 1e-4
                and cache["radius_nm"] == radius_nm)
    except (KeyError, TypeError, ValueError):
        return False


def is_fresh(cache, max_age, now):
    """True if the cache is at most `max_age` seconds old at monotonic `now`."""
    fetched = to_float((cache or {}).get("fetched_at"))
    if fetched is None:
        return False
    return 0 <= now - fetched <= max_age


# ------------------------------------------------------------
# Request pacing
# ------------------------------------------------------------

class RateGate:
    """Spacing and back-off for aircraft requests. Times are monotonic seconds.

    Every request waits until `min_gap` after the previous one started. After
    a rate-limited answer no request may start for `cooldown` seconds. Failed
    requests double the background poll delay up to `max_backoff`."""

    def __init__(self, min_gap=MIN_GAP_SECONDS, cooldown=RATE_LIMITED_COOLDOWN,
                 max_backoff=MAX_BACKOFF_SECONDS):
        self.min_gap = min_gap
        self.cooldown = cooldown
        self.max_backoff = max_backoff
        self.last_start = None
        self.failures = 0
        self.limited_until = 0.0

    def wait_time(self, now):
        if self.last_start is None:
            return 0.0
        return max(0.0, self.last_start + self.min_gap - now)

    def cooldown_left(self, now):
        return max(0.0, self.limited_until - now)

    def started(self, now):
        self.last_start = now

    def finished(self, now, error_kind):
        if error_kind is None:
            self.failures = 0
            self.limited_until = 0.0
            return
        self.failures += 1
        if error_kind == "rate_limited":
            self.limited_until = now + self.cooldown

    def backoff(self, base):
        """Delay before the next background poll."""
        return min(self.max_backoff, base * (2 ** min(self.failures, 10)))

    def reset(self):
        self.failures = 0
        self.limited_until = 0.0


# ------------------------------------------------------------
# Emergencies
# ------------------------------------------------------------

def emergency_squawk(plane):
    """The aircraft's squawk when it is an emergency code, else ""."""
    squawk = plane.get("squawk") or ""
    return squawk if squawk in EMERGENCY_SQUAWKS else ""


def emergency_status(plane):
    """The readsb emergency value when it is an emergency, else ""."""
    status = plane.get("emergency") or ""
    return status if status in EMERGENCY_STATUSES else ""


def is_emergency(plane):
    return bool(emergency_squawk(plane) or emergency_status(plane))


def emergencies(aircraft):
    """The aircraft in emergency, in the order given."""
    return [p for p in aircraft or [] if is_emergency(p)]


# ------------------------------------------------------------
# Announcing once
# ------------------------------------------------------------

class _OnceTracker:
    """Remembers what was announced, forgetting each entry after `cooldown`
    seconds (or when the clock goes backwards)."""

    def __init__(self, cooldown):
        self.cooldown = cooldown
        self._announced = {}  # key -> monotonic time announced

    def _forget_old(self, now):
        for key, when in list(self._announced.items()):
            if now - when >= self.cooldown or now < when:
                del self._announced[key]

    def _take_new(self, items, key, now):
        self._forget_old(now)
        new = []
        for item in items:
            if key(item) in self._announced:
                continue
            self._announced[key(item)] = now
            new.append(item)
        return new

    def reset(self):
        self._announced.clear()


class AlertTracker(_OnceTracker):
    """Decides which airborne aircraft to announce: each one within the alert
    distance once, then not again for `cooldown` seconds."""

    def __init__(self, cooldown=600.0):
        super().__init__(cooldown)

    def check(self, aircraft, alert_km, now):
        return self._take_new(visible_aircraft(aircraft, alert_km, include_ground=False),
                              lambda p: p["id"], now)


def _emergency_key(plane):
    return (plane["id"], emergency_squawk(plane), emergency_status(plane))


class EmergencyTracker(_OnceTracker):
    """Each aircraft and emergency once, then not again for `cooldown` seconds.
    A different emergency on the same aircraft counts as new."""

    def __init__(self, cooldown=1800.0):
        super().__init__(cooldown)

    def check(self, aircraft, now):
        """The emergencies among `aircraft` not announced recently."""
        return self._take_new(emergencies(aircraft), _emergency_key, now)

    def mark(self, aircraft, now):
        """Record emergencies the user has just heard some other way."""
        self._take_new(emergencies(aircraft), _emergency_key, now)
