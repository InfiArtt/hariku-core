# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Exact locations for Flight Radar: coordinates or a map link pasted by the user
(parsed offline), Google Maps short links (expanded only on request), and
street-address search through OpenStreetMap Nominatim.

Only two things here touch the network, both from worker threads and only
after an explicit user action: expand_short_link() (maps.app.goo.gl and
goo.gl/maps only, never any other host) and AddressSearch.search() (Nominatim,
at most one request per 1.1 seconds, identical queries answered from memory).
"""

import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from core.constants import CORE_VERSION

import flight_radar_api as api

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy asks for an application-identifying User-Agent.
NOMINATIM_USER_AGENT = (f"HarikuV2/{CORE_VERSION} (Flight Radar extension; "
                        "https://github.com/InfiArtt/hariku-core)")
NOMINATIM_MIN_GAP = 1.1          # seconds; the policy's absolute maximum is 1 per second
ADDRESS_LIMIT = 10
LINK_TIMEOUT_SECONDS = 8
SHORT_LINK_HOSTS = ("maps.app.goo.gl", "goo.gl")
MAX_REDIRECTS = 5


class LocationError(Exception):
    """`kind`: "empty", "not_found", "out_of_range", "zero", "link_no_coordinates",
    "link_failed", "address_failed" or "address_busy"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


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
            for candidate in candidates:
                found = finder(candidate)
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
    req = urllib.request.Request(url, headers={"User-Agent": api.USER_AGENT})
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

def build_address_url(query, language="en"):
    params = {
        "q": " ".join((query or "").split()),
        "format": "jsonv2",
        "limit": ADDRESS_LIMIT,
        "accept-language": language if language in ("en", "id") else "en",
    }
    return NOMINATIM_URL + "?" + urllib.parse.urlencode(params)


def parse_addresses(payload):
    """Nominatim jsonv2 results -> address location dicts."""
    places = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        lat, lon = api.to_float(item.get("lat")), api.to_float(item.get("lon"))
        detail = str(item.get("display_name") or "").strip()
        if lat is None or lon is None or not detail:
            continue
        try:
            validate(lat, lon)
        except LocationError:
            continue
        places.append({"name": detail.split(",")[0].strip() or detail, "admin1": "",
                       "country": "", "latitude": lat, "longitude": lon,
                       "kind": "address", "detail": detail})
        if len(places) >= ADDRESS_LIMIT:
            break
    return places


class AddressSearch:
    """Nominatim searches, spaced at least `min_gap` seconds apart across all
    threads, with identical queries answered from memory. search() blocks:
    call it from a worker thread."""

    def __init__(self, fetch=None, clock=time.monotonic, sleep=time.sleep,
                 min_gap=NOMINATIM_MIN_GAP, max_cached=50):
        self._fetch = fetch or (lambda url: api.fetch_json(url, user_agent=NOMINATIM_USER_AGENT))
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
                return list(self._cache[key])
            if self._last_request is not None:
                wait = self._last_request + self.min_gap - self._clock()
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()
            self.requests += 1
            try:
                places = parse_addresses(self._fetch(build_address_url(query, language)))
            except api.FlightError as e:
                kind = "address_busy" if e.status in (403, 429) else "address_failed"
                raise LocationError(kind, str(e)) from e
            if len(self._cache) >= self.max_cached:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = places
            return list(places)


_address_search = AddressSearch()


def search_addresses(query, language="en"):
    return _address_search.search(query, language)
