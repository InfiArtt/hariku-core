# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
aviationweather.gov access for the Cockpit extension: request URLs, the HTTP
fetch and turning its JSON into plain dicts, plus the pure helpers for
settings, the cache and backing off after errors. No wx and no translated
text, so tests can drive it with sample responses.

What is sent (see PRIVACY.md): the ICAO codes of the airports asked about, or,
to find the nearest airport, a box of a degree or three around the chosen
place (Preferences, Places) rounded to 0.1 degree. Never the user's own
location.

The fetch_* functions block on the network: call them from a worker thread.
The API allows 100 requests a minute; Cockpit sends one at a time, at least
MIN_GAP_SECONDS apart, and far fewer (see main.py).
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

import cockpit_metar as metar

logger = logging.getLogger(__name__)

API_URL = "https://aviationweather.gov/api/data"
METAR_URL = API_URL + "/metar"
TAF_URL = API_URL + "/taf"
STATION_URL = API_URL + "/stationinfo"
USER_AGENT = (f"HarikuV2/{CORE_VERSION} (Cockpit extension; "
              f"+https://github.com/InfiArtt/hariku-core)")
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MIN_GAP_SECONDS = 2.0
BOX_DEGREES = (1.0, 3.0)      # about 110 km, then 330 km around the place
FOR_DECIMALS = 2              # the place a nearest airport was found for, as kept
MAX_FAVOURITES = 20

# Back-off. On demand: a pause after a failure, 15 s doubling to 5 minutes, or
# 10 minutes when the service says "too many requests". In the background
# (Captain mode): every 30 minutes, doubling after failures up to 2 hours.
FAIL_PAUSE = 15
MAX_FAIL_PAUSE = 5 * 60
RATE_LIMIT_PAUSE = 10 * 60
BACKGROUND_REFRESH = 30 * 60
MAX_BACKGROUND_GAP = 2 * 3600


class AviationError(Exception):
    """A failed request. `kind` is "offline", "service", "rate_limited" or
    "bad_response"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


# ------------------------------------------------------------
# Requests
# ------------------------------------------------------------

def _url(base, **params):
    return base + "?" + urllib.parse.urlencode(params)


def build_metar_url(ids):
    return _url(METAR_URL, ids=",".join(ids), format="json")


def build_box_url(box):
    return _url(METAR_URL, bbox=box, format="json")


def build_taf_url(ids):
    return _url(TAF_URL, ids=",".join(ids), format="json")


def build_station_url(icao):
    return _url(STATION_URL, ids=icao, format="json")


def fetch_json(url):
    """GET `url` and decode its JSON body; an empty answer (HTTP 204, no data)
    is []. Raises AviationError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise AviationError("rate_limited" if e.code == 429 else "service",
                            f"HTTP {e.code}") from e
    except Exception as e:  # URLError, timeouts, resets: treat as unreachable
        raise AviationError("offline", str(e)) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise AviationError("bad_response", "response too large")
    if not body.strip():
        return []
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise AviationError("bad_response", str(e)) from e


def fetch_metars(ids):
    return parse_metars(fetch_json(build_metar_url(ids)))


def fetch_box(box):
    return parse_metars(fetch_json(build_box_url(box)))


def fetch_tafs(ids):
    return parse_tafs(fetch_json(build_taf_url(ids)))


def fetch_station(icao):
    return parse_station(fetch_json(build_station_url(icao)), icao)


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


def _items(payload):
    if isinstance(payload, list):
        return payload
    raise AviationError("bad_response", "not a list")


def _text(value, limit=200):
    return " ".join(str(value).split())[:limit] if isinstance(value, str) else ""


def iso_to_epoch(text):
    """"2026-09-23T23:00:00.000Z" -> seconds since 1970, or None."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        when = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when.timestamp()


def normalize_metar(item):
    """One METAR from the JSON (or the cache) as a clean dict, or None."""
    if not isinstance(item, dict):
        return None
    icao = metar.normalize_icao(item.get("icaoId") or item.get("icao"))
    raw = _text(item.get("rawOb") or item.get("raw"), 1000)
    obs = to_float(item.get("obsTime") if "obsTime" in item else item.get("obs_time"))
    if not icao or not raw or obs is None:
        return None
    category = item.get("fltCat") if "fltCat" in item else item.get("category")
    return {"icao": icao, "name": _text(item.get("name")), "raw": raw, "obs_time": obs,
            "latitude": to_float(item.get("lat") if "lat" in item else item.get("latitude")),
            "longitude": to_float(item.get("lon") if "lon" in item else item.get("longitude")),
            "category": category if category in metar.CATEGORIES else None}


def parse_metars(payload):
    """{icao: the newest METAR of that station}."""
    reports = {}
    for item in _items(payload):
        report = normalize_metar(item)
        if report and (report["icao"] not in reports
                       or report["obs_time"] > reports[report["icao"]]["obs_time"]):
            reports[report["icao"]] = report
    return reports


def normalize_taf(item):
    """One TAF from the JSON (or the cache) as a clean dict, or None."""
    if not isinstance(item, dict):
        return None
    icao = metar.normalize_icao(item.get("icaoId") or item.get("icao"))
    raw = _text(item.get("rawTAF") or item.get("raw"), 3000)
    if "issueTime" in item:
        issued = iso_to_epoch(item.get("issueTime")) or iso_to_epoch(item.get("bulletinTime"))
    else:
        issued = to_float(item.get("issue_time"))
    valid_from = to_float(item.get("validTimeFrom") if "validTimeFrom" in item
                          else item.get("valid_from"))
    valid_to = to_float(item.get("validTimeTo") if "validTimeTo" in item
                        else item.get("valid_to"))
    if not icao or not raw or valid_from is None or valid_to is None:
        return None
    return {"icao": icao, "name": _text(item.get("name")), "raw": raw,
            "issue_time": issued if issued is not None else valid_from,
            "valid_from": valid_from, "valid_to": valid_to}


def parse_tafs(payload):
    """{icao: the most recently issued TAF of that station}."""
    tafs = {}
    for item in _items(payload):
        taf = normalize_taf(item)
        if taf and (taf["icao"] not in tafs
                    or taf["issue_time"] > tafs[taf["icao"]]["issue_time"]):
            tafs[taf["icao"]] = taf
    return tafs


def parse_station(payload, icao):
    """{"icao", "name", "latitude", "longitude"} from stationinfo, or None."""
    for item in _items(payload):
        if isinstance(item, dict) and metar.normalize_icao(item.get("icaoId")) == icao:
            return {"icao": icao, "name": _text(item.get("site")),
                    "latitude": to_float(item.get("lat")),
                    "longitude": to_float(item.get("lon"))}
    return None


# ------------------------------------------------------------
# Settings (they come from disk and may be missing or corrupt)
# ------------------------------------------------------------

def normalize_airport(raw):
    if not isinstance(raw, dict):
        return None
    icao = metar.normalize_icao(raw.get("icao"))
    return {"icao": icao, "name": _text(raw.get("name"))} if icao else None


def normalize_location(raw):
    """A place ({"name", "latitude", "longitude", ...}), or None."""
    if not isinstance(raw, dict):
        return None
    lat, lon = to_float(raw.get("latitude")), to_float(raw.get("longitude"))
    name = _text(raw.get("name"))
    if lat is None or lon is None or not name or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"name": name, "latitude": lat, "longitude": lon}


def for_point(location):
    """What is kept of the place a nearest airport was found for: its name and
    the point rounded to about 1 km (the exact point stays in Places)."""
    return {"name": _text(location.get("name")),
            "latitude": round(float(location["latitude"]), FOR_DECIMALS),
            "longitude": round(float(location["longitude"]), FOR_DECIMALS)}


def _normalize_auto(raw):
    """The nearest airport found for a place."""
    airport = normalize_airport(raw)
    if not airport:
        return None
    place = normalize_location(raw.get("for"))
    if not place:
        return None
    airport["for"] = place
    airport["km"] = to_float(raw.get("km"))
    return airport


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    favourites, seen = [], set()
    for item in raw.get("favourites") if isinstance(raw.get("favourites"), list) else []:
        airport = normalize_airport(item)
        if airport and airport["icao"] not in seen and len(favourites) < MAX_FAVOURITES:
            seen.add(airport["icao"])
            favourites.append(airport)
    place = core.places.normalize_choice(raw.get("place"))
    return {"favourites": favourites,
            # The place for the nearest airport: "main" or a place id (core
            # 2.8); Cockpit has no place of its own (its airports are).
            "place": None if place == core.places.CHOICE_OWN else place,
            "captain": raw.get("captain") is True,
            "raw": raw.get("raw") is True,
            "briefing": raw.get("briefing") is True,
            "auto": _normalize_auto(raw.get("auto"))}


def same_place(a, b):
    try:
        return (abs(float(a["latitude"]) - float(b["latitude"])) < 1e-3
                and abs(float(a["longitude"]) - float(b["longitude"])) < 1e-3)
    except (KeyError, TypeError, ValueError):
        return False


# ------------------------------------------------------------
# The cache: {"metar": {icao: {"fetched_at", "report"}}, "taf": {...},
# "no_metar": {icao: when a request found no report}, "no_taf": {...}}
# ------------------------------------------------------------

def empty_cache():
    return {"metar": {}, "taf": {}, "no_metar": {}, "no_taf": {}}


def normalize_cache(raw):
    cache = empty_cache()
    if not isinstance(raw, dict):
        return cache
    for kind, normalize in (("metar", normalize_metar), ("taf", normalize_taf)):
        entries = raw.get(kind) if isinstance(raw.get(kind), dict) else {}
        for icao, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            fetched = to_float(entry.get("fetched_at"))
            report = normalize(entry.get("report"))
            if fetched is not None and report and report["icao"] == icao:
                cache[kind][icao] = {"fetched_at": fetched, "report": report}
    for kind in ("no_metar", "no_taf"):
        entries = raw.get(kind) if isinstance(raw.get(kind), dict) else {}
        for icao, when in entries.items():
            if metar.normalize_icao(icao) == icao and to_float(when) is not None:
                cache[kind][icao] = to_float(when)
    return cache


def store_metars(cache, ids, reports, now):
    for icao in ids:
        if icao in reports:
            cache["metar"][icao] = {"fetched_at": now, "report": reports[icao]}
            cache["no_metar"].pop(icao, None)
        else:
            cache["no_metar"][icao] = now


def store_tafs(cache, ids, tafs, now):
    for icao in ids:
        if icao in tafs:
            cache["taf"][icao] = {"fetched_at": now, "report": tafs[icao]}
            cache["no_taf"].pop(icao, None)
        else:
            cache["no_taf"][icao] = now


def is_fresh(when, max_age, now=None):
    """True if `when` (seconds) is at most `max_age` seconds ago. A time in the
    future (the clock changed) counts as stale."""
    when = to_float(when)
    if when is None:
        return False
    age = (time.time() if now is None else now) - when
    return 0 <= age <= max_age


def needs_fetch(cache, kind, icao, max_age, now=None):
    """Whether `icao`'s METAR or TAF (`kind`) should be asked for again: no
    answer, report or "none", younger than `max_age`."""
    entry = cache[kind].get(icao)
    if entry and is_fresh(entry["fetched_at"], max_age, now):
        return False
    return not is_fresh(cache["no_" + kind].get(icao), max_age, now)


# ------------------------------------------------------------
# Backing off
# ------------------------------------------------------------

class Backoff:
    """When the next request may go. After a failure, requests the user asks
    for wait a short while (longer each time, and 10 minutes when the service
    asks to slow down); background refreshes wait longer and longer."""

    def __init__(self):
        self.failures = 0
        self.blocked_until = 0.0
        self.last_error = None

    def failed(self, kind, now):
        self.failures += 1
        self.last_error = kind
        if kind == "rate_limited":
            pause = RATE_LIMIT_PAUSE
        else:
            pause = min(FAIL_PAUSE * 2 ** (self.failures - 1), MAX_FAIL_PAUSE)
        self.blocked_until = max(self.blocked_until, now + pause)

    def succeeded(self):
        self.failures = 0
        self.blocked_until = 0.0
        self.last_error = None

    def blocked(self, now):
        return now < self.blocked_until

    def background_gap(self):
        """Seconds between background refreshes: 30 minutes, doubling after
        each failure in a row, at most 2 hours."""
        return min(BACKGROUND_REFRESH * 2 ** self.failures, MAX_BACKGROUND_GAP)
