# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Network access and data rules for the Space extension: the ISS position and
the country below it (wheretheiss.at), upcoming rocket launches (The Space
Devs Launch Library 2), city search (Open-Meteo), and the pure helpers for
settings, the launch cache, request pacing and launch reminders. No wx and no
translated text, so tests can drive it with sample responses.

Privacy: none of these services ever gets the user's location. wheretheiss.at
gets the ISS's own position (rounded) to name the country below it; Launch
Library gets nothing but the request for the list; Open-Meteo gets the city
name the user types. Distances are worked out on this computer.

fetch_json(), fetch_iss(), fetch_country(), fetch_launches() and
search_places() block on the network: call them from a worker thread only.
"""

import datetime
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import zoneinfo

from core.constants import CORE_VERSION

logger = logging.getLogger(__name__)

ISS_URL = "https://api.wheretheiss.at/v1/satellites/25544"
COORDINATES_URL = "https://api.wheretheiss.at/v1/coordinates/{lat},{lon}"
LAUNCHES_URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = f"HarikuV2/{CORE_VERSION} (Space extension)"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 1024 * 1024
SEARCH_COUNT = 10
LAUNCH_REQUEST_LIMIT = 15     # a few spare for launches that have just gone
LAUNCH_LIST_COUNT = 10        # shown in the list

# wheretheiss.at allows roughly one request a second.
ISS_MIN_GAP = 10.0            # never ask for the position more often than this
ISS_COUNTRY_GAP = 1.1         # between the position and the country request
ISS_MAX_BACKOFF = 300.0

# Launch Library 2 allows about 15 anonymous requests an hour.
LAUNCH_AUTO_AGE = 3600        # automatic refreshes: at most once an hour
LAUNCH_MANUAL_AGE = 15 * 60   # the Refresh button: when older than 15 minutes
LAUNCH_BACKOFF_BASE = 300     # after a failure: 5, 10, 20, 40, then 60 minutes
LAUNCH_MAX_BACKOFF = 3600
LAUNCH_RATE_LIMIT_WAIT = 1800  # after "too many requests" without a hint
LAUNCH_MAX_WAIT = 2 * 3600

LEAD_CHOICES = (10, 30, 60)   # reminder lead time, minutes
DEFAULT_LEAD = 30
MAX_REMINDERS = 20
REMINDER_KEEP_SECONDS = 6 * 3600   # forget a reminder this long after its launch

# Launch Library net_precision ids: second, minute, hour are exact enough to
# name a time and set a reminder; then morning/afternoon/day, week, and
# month or vaguer.
EXACT_PRECISIONS = (0, 1, 2)
DAY_PRECISIONS = (3, 4, 5)
WEEK_PRECISION = 6

# Launch Library status ids with their own wording (see space_text).
KNOWN_STATUSES = (1, 2, 3, 4, 5, 6, 7, 8)
IN_FLIGHT_STATUS = 6

_COUNTRY = re.compile(r"^[A-Z]{2}$")
_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?")
_THROTTLE_HINT = re.compile(r"(\d+)\s*second")


class SpaceError(Exception):
    """A failed request. `kind` is "offline", "service", "rate_limited" or
    "bad_response"; `retry_after` is the wait in seconds a service asked for."""

    def __init__(self, kind, detail="", retry_after=None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.retry_after = retry_after


# ------------------------------------------------------------
# Requests
# ------------------------------------------------------------

def _retry_after(error):
    """Seconds to wait from a 429 answer: its Retry-After header, or Launch
    Library's "Expected available in 1234 seconds."."""
    try:
        header = error.headers.get("Retry-After") if error.headers else None
        if header and str(header).strip().isdigit():
            return int(str(header).strip())
    except Exception:
        pass
    try:
        body = error.read(4096).decode("utf-8", "replace")
        match = _THROTTLE_HINT.search(body)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return None


def fetch_json(url):
    """GET `url` and decode its JSON body. Raises SpaceError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise SpaceError("rate_limited", "HTTP 429", _retry_after(e)) from e
        raise SpaceError("service", f"HTTP {e.code}") from e
    except Exception as e:  # URLError, timeouts, resets: treat as unreachable
        raise SpaceError("offline", str(e)) from e
    if len(body) > MAX_RESPONSE_BYTES:
        raise SpaceError("bad_response", "response too large")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise SpaceError("bad_response", str(e)) from e


def build_coordinates_url(latitude, longitude):
    """The country lookup for the point below the ISS (never the user's point)."""
    return COORDINATES_URL.format(lat=f"{float(latitude):.2f}", lon=f"{float(longitude):.2f}")


def build_launches_url():
    params = {"limit": LAUNCH_REQUEST_LIMIT, "mode": "list"}
    return LAUNCHES_URL + "?" + urllib.parse.urlencode(params)


def build_search_url(name, language="en"):
    params = {
        "name": (name or "").strip(),
        "count": SEARCH_COUNT,
        "language": language if language in ("en", "id") else "en",
        "format": "json",
    }
    return GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def fetch_iss():
    return parse_iss(fetch_json(ISS_URL))


def fetch_country(latitude, longitude):
    return parse_country(fetch_json(build_coordinates_url(latitude, longitude)))


def fetch_launches():
    return parse_launches(fetch_json(build_launches_url()))


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


def _text(value, limit=200):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    return " ".join(str(value).split())[:limit]


def parse_iss(payload):
    """wheretheiss.at satellite JSON -> {"latitude", "longitude", "altitude_km",
    "speed_kmh", "visibility" ("daylight", "eclipsed" or "")}. Raises SpaceError."""
    if not isinstance(payload, dict):
        raise SpaceError("bad_response", "not an object")
    lat, lon = to_float(payload.get("latitude")), to_float(payload.get("longitude"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise SpaceError("bad_response", "no position")
    altitude = to_float(payload.get("altitude"))
    speed = to_float(payload.get("velocity"))
    visibility = payload.get("visibility")
    return {
        "latitude": lat,
        "longitude": lon,
        "altitude_km": altitude if altitude is not None and altitude > 0 else None,
        "speed_kmh": speed if speed is not None and speed > 0 else None,
        "visibility": visibility if visibility in ("daylight", "eclipsed") else "",
    }


def parse_country(payload):
    """The country code below a point, "" over the ocean ("??"). Raises
    SpaceError when the answer is unusable."""
    if not isinstance(payload, dict) or "country_code" not in payload:
        raise SpaceError("bad_response", "no country_code")
    code = str(payload.get("country_code") or "").strip().upper()
    return code if _COUNTRY.match(code) else ""


def parse_time(text):
    """"2026-09-23T13:30:00Z" (Launch Library gives UTC) -> aware UTC datetime,
    or None."""
    match = _TIME.match(str(text or "").strip())
    if not match:
        return None
    try:
        parts = [int(p) for p in match.groups(default="0")]
        return datetime.datetime(*parts, tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def format_time(when):
    return when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nested(item, key, field):
    value = item.get(key)
    return value.get(field) if isinstance(value, dict) else None


def normalize_launch(raw):
    """One Launch Library list-mode launch -> a plain dict, or None when it
    has no id, name or time. Also re-validates launches read from the cache."""
    if not isinstance(raw, dict):
        return None
    launch_id = _text(raw.get("id"), 80)
    name = _text(raw.get("name"))
    net = parse_time(raw.get("net"))
    if not launch_id or not name or net is None:
        return None
    status = raw.get("status")
    status_id = to_int(status.get("id")) if isinstance(status, dict) else to_int(raw.get("status_id"))
    # Launch Library sends {"net_precision": {"id": 2, ...}}; the cache keeps "precision": 2.
    precision = raw.get("net_precision") if "net_precision" in raw else raw.get("precision")
    precision_id = to_int(precision.get("id")) if isinstance(precision, dict) else to_int(precision)
    window_start, window_end = parse_time(raw.get("window_start")), parse_time(raw.get("window_end"))
    return {
        "id": launch_id,
        "name": name,
        "net": format_time(net),
        "precision": precision_id,
        "window_start": format_time(window_start) if window_start else "",
        "window_end": format_time(window_end) if window_end else "",
        "status_id": status_id,
        "status_abbrev": _text(_nested(raw, "status", "abbrev") or raw.get("status_abbrev"), 40),
        "provider": _text(raw.get("lsp_name") or raw.get("provider")),
        "mission_type": _text(raw.get("mission_type"), 80),
        "pad": _text(raw.get("pad")),
        "location": _text(raw.get("location")),
        "orbit": _text(raw.get("orbit"), 80),
    }


def parse_launches(payload):
    """Launch Library upcoming launches (list mode) -> launch dicts sorted by
    time. Raises SpaceError for anything without a results list."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SpaceError("bad_response", "no results")
    launches, seen = [], set()
    for item in payload["results"]:
        launch = normalize_launch(item)
        if launch and launch["id"] not in seen:
            seen.add(launch["id"])
            launches.append(launch)
    launches.sort(key=lambda launch: launch["net"])
    return launches


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
# Launch helpers
# ------------------------------------------------------------

def launch_time(launch):
    return parse_time((launch or {}).get("net"))


def is_exact(launch):
    """True when the launch time is known to the hour or better."""
    precision = (launch or {}).get("precision")
    return precision is None or precision in EXACT_PRECISIONS


def upcoming(launches, now, limit=LAUNCH_LIST_COUNT):
    """The launches still to come (or launched within the last hour, or in
    flight), soonest first."""
    keep = []
    for launch in launches or []:
        net = launch_time(launch)
        if net is None:
            continue
        if net >= now - datetime.timedelta(hours=1) or launch.get("status_id") == IN_FLIGHT_STATUS:
            keep.append(launch)
    keep.sort(key=lambda launch: launch["net"])
    return keep[:limit]


# Words that make a launch site's name long without helping to recognise it.
_SITE_SUFFIXES = (" Space Launch Site", " Satellite Launch Center", " Space Launch Center",
                  " Cosmodrome", " Space Force Station", " Space Force Base", " SFS", " SFB",
                  " Air Force Station", " AFS")


def site_name(launch):
    """A short launch site name: "Wenchang Space Launch Site, People's Republic
    of China" -> "Wenchang"."""
    location = (launch or {}).get("location") or ""
    name = location.split(",")[0].strip()
    for suffix in _SITE_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)].strip()
            break
    return name


def launch_name(launch):
    """"Long March 8A | Unknown Payload" -> "Long March 8A, Unknown Payload"."""
    return ", ".join(p.strip() for p in (launch or {}).get("name", "").split("|") if p.strip())


# ------------------------------------------------------------
# Settings and stored data (all may be missing or corrupt on disk)
# ------------------------------------------------------------

def normalize_location(raw):
    """A clean location dict, or None if `raw` is not a usable place."""
    if not isinstance(raw, dict):
        return None
    lat, lon = to_float(raw.get("latitude")), to_float(raw.get("longitude"))
    name = str(raw.get("name") or "").strip()[:100]
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
    lead = raw.get("lead_minutes")
    return {
        "location": normalize_location(raw.get("location")),
        "lead_minutes": lead if lead in LEAD_CHOICES and not isinstance(lead, bool) else DEFAULT_LEAD,
    }


def zone_for(location):
    """The location's time zone, or None (use the computer's own)."""
    name = (location or {}).get("timezone") or ""
    if not name:
        return None
    try:
        return zoneinfo.ZoneInfo(name)
    except Exception:
        return None


def empty_launch_state():
    return {"fetched_at": None, "launches": [], "retry_after": 0.0, "failures": 0}


def normalize_launch_state(raw):
    """The stored launch cache and back-off state, repaired where needed."""
    state = empty_launch_state()
    if not isinstance(raw, dict):
        return state
    items = raw.get("launches") if isinstance(raw.get("launches"), list) else []
    launches = [launch for launch in (normalize_launch(item) for item in items) if launch]
    state["launches"] = sorted(launches, key=lambda launch: launch["net"])
    state["fetched_at"] = to_float(raw.get("fetched_at"))
    state["retry_after"] = to_float(raw.get("retry_after")) or 0.0
    failures = to_int(raw.get("failures"))
    state["failures"] = failures if failures is not None and failures > 0 else 0
    return state


def launch_age(state, now):
    """Seconds since the launches were fetched; None if never (or the clock
    went backwards)."""
    fetched = to_float((state or {}).get("fetched_at"))
    if fetched is None or fetched > now:
        return None
    return now - fetched


def launch_wait(state, now):
    """Seconds until a launch request may be made again (0 when it may)."""
    retry_after = to_float((state or {}).get("retry_after")) or 0.0
    wait = retry_after - now
    if wait > LAUNCH_MAX_WAIT:
        return 0.0   # the clock was changed; don't stay locked out
    return max(0.0, wait)


def launch_fetch_decision(state, now, min_age):
    """"fetch", "fresh" (the cache is younger than `min_age`) or "wait" (backing off)."""
    age = launch_age(state, now)
    if age is not None and age < min_age:
        return "fresh"
    if launch_wait(state, now) > 0:
        return "wait"
    return "fetch"


def after_launch_fetch(state, now, launches=None, error=None, retry_after=None):
    """The launch state after a request: new launches on success; on failure
    the old ones are kept and the next attempt is pushed back."""
    state = dict(state or empty_launch_state())
    if error is None:
        return {"fetched_at": now, "launches": list(launches or []),
                "retry_after": 0.0, "failures": 0}
    failures = int(state.get("failures") or 0) + 1
    if error == "rate_limited":
        wait = retry_after if retry_after else LAUNCH_RATE_LIMIT_WAIT
        wait = max(60, min(LAUNCH_MAX_WAIT, wait))
    else:
        wait = min(LAUNCH_MAX_BACKOFF, LAUNCH_BACKOFF_BASE * 2 ** (failures - 1))
    state.update(failures=failures, retry_after=now + wait)
    return state


class RequestGate:
    """Pacing for the ISS requests. Times are monotonic seconds.

    A request may start `min_gap` after the previous one started; after
    failures the gap doubles each time up to `max_backoff`."""

    def __init__(self, min_gap=ISS_MIN_GAP, max_backoff=ISS_MAX_BACKOFF):
        self.min_gap = min_gap
        self.max_backoff = max_backoff
        self.last_start = None
        self.failures = 0

    def gap(self):
        if not self.failures:
            return self.min_gap
        return min(self.max_backoff, self.min_gap * 2 ** self.failures)

    def wait_time(self, now):
        if self.last_start is None or now < self.last_start:
            return 0.0
        return max(0.0, self.last_start + self.gap() - now)

    def started(self, now):
        self.last_start = now

    def finished(self, error_kind):
        self.failures = 0 if error_kind is None else self.failures + 1

    def reset(self):
        self.failures = 0
        self.last_start = None


# ------------------------------------------------------------
# Launch reminders
# ------------------------------------------------------------

def normalize_reminders(raw):
    reminders = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        launch_id = _text(item.get("id"), 80)
        net = parse_time(item.get("net"))
        if not launch_id or net is None or any(r["id"] == launch_id for r in reminders):
            continue
        notified = parse_time(item.get("notified_for"))
        reminders.append({"id": launch_id, "name": _text(item.get("name")) or launch_id,
                          "net": format_time(net),
                          "notified_for": format_time(notified) if notified else ""})
        if len(reminders) >= MAX_REMINDERS:
            break
    return reminders


def new_reminder(launch):
    return {"id": launch["id"], "name": launch["name"], "net": launch["net"], "notified_for": ""}


def check_reminders(reminders, launches_by_id, now, lead_minutes):
    """The minute-tick rule. Returns (due, kept): `due` is [(reminder, launch
    or None, launch time)] to announce now, `kept` the reminders to store.

    A reminder follows its launch's latest known time. It is announced once,
    when the launch is at most `lead_minutes` away and has not started; if the
    launch is later moved by at least the lead time, it is announced again
    for the new time. Launches that are only known to the day are not
    announced. Reminders are forgotten some hours after their launch."""
    lead = datetime.timedelta(minutes=lead_minutes)
    due, kept = [], []
    for reminder in reminders:
        launch = launches_by_id.get(reminder["id"])
        net = launch_time(launch) if launch else parse_time(reminder["net"])
        if net is None or now - net > datetime.timedelta(seconds=REMINDER_KEEP_SECONDS):
            continue
        reminder = dict(reminder, net=format_time(net))
        if launch:
            reminder["name"] = launch["name"]
        if net - lead <= now < net and (launch is None or is_exact(launch)):
            notified = parse_time(reminder.get("notified_for"))
            if notified is None or abs(notified - net) >= lead:
                reminder["notified_for"] = format_time(net)
                due.append((reminder, launch, net))
        kept.append(reminder)
    return due, kept


def minutes_until(when, now):
    return max(0, int(round((when - now).total_seconds() / 60)))
