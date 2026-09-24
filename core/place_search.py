# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Finding a place (core 2.8): what the Places page and extensions use to turn
what the user types or pastes into a point on the map.

  * parse_location_text() - coordinates or a map link (Google Maps, Apple
    Maps, OpenStreetMap) the user pasted, parsed offline.
  * resolve_short_link()  - a maps.app.goo.gl or goo.gl/maps short link,
    expanded only when the user asks (the Use button).
  * search_addresses()    - a street address, through OpenStreetMap Nominatim.
  * search_cities()       - a city, through Open-Meteo's geocoding (with the
    city's IANA time zone).

The last three block on the network: call them from a worker thread, only
after an explicit user action, and hand the result back with wx.CallAfter.
Nominatim's usage policy is kept for all of Hariku: at most one request per
1.1 seconds (one AddressSearch shared by everyone), identical queries answered
from memory, an identifying User-Agent, and never a search while typing.
Short links: only maps.app.goo.gl and goo.gl/maps are ever fetched; the
address they redirect to is read from the Location header, never fetched.

Results are "candidates": {"name", "label", "latitude", "longitude",
"timezone" (IANA or None), "source" ("address", "city" or "coordinates"),
"city", "region", "country"}. core.places turns one into a saved place.
Flight Radar moved this code here from its flight_radar_location module.
"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from core.constants import CORE_VERSION

PROJECT_URL = "https://github.com/InfiArtt/hariku-core"
# Nominatim's usage policy asks for an application-identifying User-Agent.
USER_AGENT = f"HarikuV2/{CORE_VERSION} (+{PROJECT_URL})"
NOMINATIM_USER_AGENT = f"HarikuV2/{CORE_VERSION} (Places; {PROJECT_URL})"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_MIN_GAP = 1.1          # seconds; the policy's absolute maximum is 1 per second
ADDRESS_LIMIT = 10
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
CITY_LIMIT = 10
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
LINK_TIMEOUT_SECONDS = 8
SHORT_LINK_HOSTS = ("maps.app.goo.gl", "goo.gl")
MAX_REDIRECTS = 5
SOURCES = ("address", "city", "coordinates")
_ZONE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+){0,2}$")


class LocationError(Exception):
    """`kind`: "empty", "not_found", "out_of_range", "zero",
    "link_no_coordinates", "link_failed", "address_failed", "address_busy" or
    "city_failed"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


class FetchError(Exception):
    """A failed request. `kind` is "offline", "service", "rate_limited" or
    "bad_response"; `status` is the HTTP status when there was one."""

    def __init__(self, kind, detail="", status=None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.status = status


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


def clean_timezone(value):
    """An IANA zone name ("Asia/Jakarta"), or None for anything else."""
    value = str(value or "").strip()
    return value if len(value) <= 64 and _ZONE_RE.match(value) else None


def fetch_json(url, timeout=TIMEOUT_SECONDS, user_agent=None):
    """GET `url` and decode its JSON body. Raises FetchError. Worker threads only."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent or USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        kind = "rate_limited" if e.code == 429 else "service"
        raise FetchError(kind, f"HTTP {e.code}", status=e.code) from e
    except Exception as e:  # URLError, timeouts, resets: treat as unreachable
        raise FetchError("offline", str(e)) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise FetchError("bad_response", "response too large")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise FetchError("bad_response", str(e)) from e


def candidate(latitude, longitude, source="coordinates", name="", label="", timezone=None,
              city="", region="", country=""):
    """A search result or pasted point in the shape core.places takes."""
    return {"name": str(name or "").strip(), "label": str(label or "").strip(),
            "latitude": float(latitude), "longitude": float(longitude),
            "timezone": clean_timezone(timezone),
            "source": source if source in SOURCES else "coordinates",
            "city": str(city or "").strip(), "region": str(region or "").strip(),
            "country": str(country or "").strip()}


# ------------------------------------------------------------
# Plain coordinates
# ------------------------------------------------------------

# Words people paste along with coordinates ("lat: -6.2, lng: 106.8").
_WORDS = re.compile(r"\b(latitude|longitude|lat|lon|lng|long|lintang|bujur)\b\s*[:=]?", re.I)
_ALLOWED = re.compile(r"^[\s0-9.,;:/°º'′’\"″”+\-−NSEWUTBLnsewutbl]*$")
_TOKEN = re.compile(r"""
    (?P<num>[-+−]?\d+(?:[.,]\d+)?)\s*(?P<unit>''|[°º'′’"″”])?
  | (?P<hemi>LU|LS|BT|BB|[NSEWUTB])(?![A-Z])
""", re.X | re.I)
_SOUTH_WEST = ("S", "W", "B", "LS", "BB")
_LONGITUDE = ("E", "W", "T", "B", "BT", "BB")
_LATITUDE = ("N", "S", "U", "LU", "LS")


def _number(text):
    return float(text.replace("−", "-").replace(",", "."))


def parse_coordinates(text):
    """(latitude, longitude) from text such as "-6.2088, 106.8456",
    "-6,2088; 106,8456", "6.2088° S 106.8456° E" or "6°12'31.7"S 106°50'44.2"E"
    (also Indonesian LS/LU/BT/BB). Raises LocationError."""
    text = _WORDS.sub(" ", (text or "").strip())
    if not text.strip():
        raise LocationError("empty")
    if not _ALLOWED.match(text):
        raise LocationError("not_found")
    components = []   # [value, negative, hemisphere, start position, last unit]
    letters = []      # (position, hemisphere)
    starts_with_letter = None
    for match in _TOKEN.finditer(text):
        if match.group("hemi"):
            letters.append((match.start(), match.group("hemi").upper()))
            if starts_with_letter is None:
                starts_with_letter = True
            continue
        if starts_with_letter is None:
            starts_with_letter = False
        raw, unit = match.group("num"), match.group("unit") or ""
        value = abs(_number(raw))
        negative = raw[0] in "-−"
        if unit in ("'", "′", "’") and components and components[-1][4] in ("°", "º"):
            components[-1][0] += value / 60
            components[-1][4] = "'"
        elif unit in ('"', "″", "”", "''") and components and components[-1][4] in ("°", "º", "'"):
            components[-1][0] += value / 3600
            components[-1][4] = '"'
        else:
            components.append([value, negative, None, match.start(), unit])
    if len(components) != 2:
        raise LocationError("not_found")
    # Hemisphere letters belong to the following number when the text starts
    # with one ("S 6.2 E 106.8"), otherwise to the preceding one.
    for position, letter in letters:
        if starts_with_letter:
            owner = next((c for c in components if c[3] > position), None)
        else:
            owner = next((c for c in reversed(components) if c[3] < position), None)
        if owner is None or owner[2] is not None:
            raise LocationError("not_found")
        owner[2] = letter
    values = []
    for value, negative, letter, _position, _unit in components:
        if letter is not None:
            negative = letter in _SOUTH_WEST
        values.append((-value if negative else value, letter))
    (lat, lat_letter), (lon, lon_letter) = values
    if lat_letter and lon_letter and (lat_letter in _LONGITUDE) == (lon_letter in _LONGITUDE):
        raise LocationError("not_found")  # two latitudes or two longitudes
    if lat_letter in _LONGITUDE or lon_letter in _LATITUDE:
        lat, lon = lon, lat
    return validate(lat, lon)


def validate(latitude, longitude):
    """(latitude, longitude) when on the map and not 0, 0. Raises LocationError."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise LocationError("out_of_range")
    if abs(latitude) < 1e-9 and abs(longitude) < 1e-9:
        raise LocationError("zero")
    return latitude, longitude


# ------------------------------------------------------------
# Map links
# ------------------------------------------------------------

_NUM = r"[-+]?\d+(?:\.\d+)?"
_PIN = re.compile(rf"!3d({_NUM})!4d({_NUM})")
_AT = re.compile(rf"@({_NUM}),({_NUM})")
_OSM_HASH = re.compile(rf"#map=\d+(?:\.\d+)?/({_NUM})/({_NUM})")
_MLAT = re.compile(rf"[?&#;]mlat=({_NUM})")
_MLON = re.compile(rf"[?&#;]mlon=({_NUM})")
_PARAM = re.compile(r"[?&#;](q|query|ll|destination|daddr|center|coordinate|sll)=([^&#]+)")


def _param_value(value):
    value = urllib.parse.unquote_plus(value).strip()
    return value[4:] if value.lower().startswith("loc:") else value


def parse_map_url(url):
    """(latitude, longitude) from a Google Maps, Apple Maps or OpenStreetMap
    link, preferring the pin over the map view; None when there is none."""
    candidates = [url]
    for _ in range(2):
        decoded = urllib.parse.unquote(candidates[-1])
        if decoded != candidates[-1]:
            candidates.append(decoded)

    def first(finders):
        for finder in finders:
            for text in candidates:
                found = finder(text)
                if found:
                    return found
        return None

    def pin(s):
        matches = _PIN.findall(s)
        return (float(matches[-1][0]), float(matches[-1][1])) if matches else None

    def marker(s):
        lat, lon = _MLAT.search(s), _MLON.search(s)
        return (float(lat.group(1)), float(lon.group(1))) if lat and lon else None

    def params(s):
        for _name, value in _PARAM.findall(s):
            try:
                return parse_coordinates(_param_value(value))
            except LocationError:
                continue
        return None

    def at(s):
        match = _AT.search(s)
        return (float(match.group(1)), float(match.group(2))) if match else None

    def osm_view(s):
        match = _OSM_HASH.search(s)
        return (float(match.group(1)), float(match.group(2))) if match else None

    return first((pin, marker, params, at, osm_view))


def looks_like_link(text):
    text = (text or "").strip().lower()
    return bool(re.match(r"^[a-z][a-z0-9+.-]*://", text) or text.startswith("www.")
                or re.match(r"^(maps\.|goo\.gl/)", text))


def short_link(text):
    """The HTTPS form of a Google Maps short link (maps.app.goo.gl/... or
    goo.gl/maps/...), or None for anything else."""
    text = (text or "").strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
        text = "https://" + text
    try:
        parts = urllib.parse.urlsplit(text)
        host, port = (parts.hostname or "").lower(), parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or host not in SHORT_LINK_HOSTS:
        return None
    if host == "goo.gl" and not parts.path.startswith("/maps"):
        return None
    if port not in (None, 443) or parts.username or not parts.path.strip("/"):
        return None
    return urllib.parse.urlunsplit(("https", host, parts.path, parts.query, ""))


def parse_location_text(text):
    """What the user pasted: {"kind": "coordinates", "latitude", "longitude"}
    or {"kind": "short_link", "url"}. Raises LocationError."""
    text = (text or "").strip()
    if not text:
        raise LocationError("empty")
    if not looks_like_link(text):
        # Shared text from a map app: "Monumen Nasional https://maps.app.goo.gl/..."
        embedded = re.search(r"https?://\S+", text)
        if embedded:
            text = embedded.group(0)
    link = short_link(text) if looks_like_link(text) else None
    if link:
        return {"kind": "short_link", "url": link}
    if looks_like_link(text):
        found = parse_map_url(text)
        if not found:
            raise LocationError("link_no_coordinates")
        lat, lon = validate(*found)
    else:
        lat, lon = parse_coordinates(text)
    return {"kind": "coordinates", "latitude": lat, "longitude": lon}


# ------------------------------------------------------------
# Short links (network, worker thread only)
# ------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report redirects instead of following them, so no other host is fetched."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_without_redirects(url, timeout):
    """(status, Location header) for one GET of `url`."""
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location")


def expand_short_link(url):
    """Follow a short link's redirects while they stay on the short-link hosts
    and return the first address elsewhere (which is never fetched). Raises
    LocationError("link_failed")."""
    current = short_link(url)
    if not current:
        raise LocationError("link_failed", "not a short link")
    for _ in range(MAX_REDIRECTS):
        try:
            status, location = _open_without_redirects(current, LINK_TIMEOUT_SECONDS)
        except Exception as e:  # offline, timeout, TLS
            raise LocationError("link_failed", str(e)) from e
        if 200 <= status < 300:
            raise LocationError("link_no_coordinates", "no redirect")
        if not (300 <= status < 400) or not location:
            raise LocationError("link_failed", f"HTTP {status}")
        location = urllib.parse.urljoin(current, location)
        following = short_link(location)
        if not following or parse_map_url(location):
            return location
        current = following
    raise LocationError("link_failed", "too many redirects")


def resolve_short_link(url):
    """(latitude, longitude) behind a short link. Raises LocationError."""
    found = parse_map_url(expand_short_link(url))
    if not found:
        raise LocationError("link_no_coordinates")
    return validate(*found)


# ------------------------------------------------------------
# Address search (Nominatim)
# ------------------------------------------------------------

def _language(language):
    return language if language in ("en", "id") else "en"


def build_address_url(query, language="en"):
    params = {
        "q": " ".join((query or "").split()),
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": ADDRESS_LIMIT,
        "accept-language": _language(language),
    }
    return NOMINATIM_URL + "?" + urllib.parse.urlencode(params)


_CITY_KEYS = ("city", "town", "village", "municipality", "county", "state_district")


def parse_addresses(payload):
    """Nominatim jsonv2 results -> address candidates (possibly empty)."""
    found = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        lat, lon = to_float(item.get("lat")), to_float(item.get("lon"))
        label = " ".join(str(item.get("display_name") or "").split())
        if lat is None or lon is None or not label:
            continue
        try:
            validate(lat, lon)
        except LocationError:
            continue
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        city = next((str(address[k]).strip() for k in _CITY_KEYS
                     if isinstance(address.get(k), str) and address[k].strip()), "")
        found.append(candidate(lat, lon, "address", name=label.split(",")[0].strip() or label,
                               label=label, city=city, region=address.get("state") or "",
                               country=address.get("country") or ""))
        if len(found) >= ADDRESS_LIMIT:
            break
    return found


class AddressSearch:
    """Nominatim searches, spaced at least `min_gap` seconds apart across all
    threads, with identical queries answered from memory. search() blocks:
    call it from a worker thread."""

    def __init__(self, fetch=None, clock=time.monotonic, sleep=time.sleep,
                 min_gap=NOMINATIM_MIN_GAP, max_cached=50):
        self._fetch = fetch or (lambda url: fetch_json(url, user_agent=NOMINATIM_USER_AGENT))
        self._clock = clock
        self._sleep = sleep
        self.min_gap = min_gap
        self.max_cached = max_cached
        self._lock = threading.Lock()
        self._last_request = None
        self._cache = {}
        self.requests = 0

    @staticmethod
    def _key(query, language):
        return (" ".join((query or "").split()).lower(), language)

    def search(self, query, language="en"):
        key = self._key(query, language)
        with self._lock:
            if key in self._cache:
                return [dict(p) for p in self._cache[key]]
            if self._last_request is not None:
                wait = self._last_request + self.min_gap - self._clock()
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()
            self.requests += 1
            try:
                places = parse_addresses(self._fetch(build_address_url(query, language)))
            except FetchError as e:
                kind = "address_busy" if e.status in (403, 429) else "address_failed"
                raise LocationError(kind, str(e)) from e
            if len(self._cache) >= self.max_cached:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = places
            return [dict(p) for p in places]


# One for all of Hariku, so the pacing holds whoever searches.
_address_search = AddressSearch()


def search_addresses(query, language="en"):
    """Address candidates for `query` (at least 3 characters: check first).
    Worker thread only. Raises LocationError("address_failed" / "address_busy")."""
    return _address_search.search(query, _language(language))


# ------------------------------------------------------------
# City search (Open-Meteo geocoding)
# ------------------------------------------------------------

def build_city_url(name, language="en"):
    params = {
        "name": " ".join((name or "").split()),
        "count": CITY_LIMIT,
        "language": _language(language),
        "format": "json",
    }
    return GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def city_label(name, region="", country=""):
    """'Name, Region, Country', skipping empty or repeated parts."""
    parts = []
    for value in (name, region, country):
        value = str(value or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def parse_cities(payload):
    """Open-Meteo geocoding JSON -> city candidates (possibly empty)."""
    results = payload.get("results") if isinstance(payload, dict) else None
    found = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        lat, lon = to_float(item.get("latitude")), to_float(item.get("longitude"))
        name = " ".join(str(item.get("name") or "").split())
        if lat is None or lon is None or not name:
            continue
        try:
            validate(lat, lon)
        except LocationError:
            continue
        region = str(item.get("admin1") or "").strip()
        country = str(item.get("country") or "").strip()
        found.append(candidate(lat, lon, "city", name=name,
                               label=city_label(name, region, country),
                               timezone=item.get("timezone"), city=name, region=region,
                               country=country))
        if len(found) >= CITY_LIMIT:
            break
    return found


def search_cities(name, language="en", fetch=None):
    """City candidates for `name` (at least 2 characters: check first).
    Worker thread only. Raises LocationError("city_failed")."""
    try:
        return parse_cities((fetch or fetch_json)(build_city_url(name, language)))
    except FetchError as e:
        raise LocationError("city_failed", str(e)) from e
