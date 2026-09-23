# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Best-effort flight routes (origin and destination) from adsbdb.com, looked up
by callsign only for the aircraft Hariku is about to speak.

adsbdb's terms: the route data is the work of David Taylor and Jim Mason and
may not be copied, published or put into other databases without permission.
So routes are only ever held in memory for about an hour (RouteLookup) and are
never written to disk or to any data key. Only the origin and destination are
used; adsbdb's airline name is ignored in favour of our own table.

Routes come from a callsign database and can be stale, so a route is only
spoken when the aircraft's position fits it (plausible_leg).
"""

import logging
import math
import re
import threading
import time
import urllib.parse

import flight_radar_api as api

logger = logging.getLogger(__name__)

ROUTE_URL = "https://api.adsbdb.com/v0/callsign/{callsign}"
ROUTE_TIMEOUT_SECONDS = 4
ROUTE_TTL_SECONDS = 3600.0       # found and not-found routes alike
ERROR_BACKOFF_SECONDS = 120.0    # no lookups after a network or service error
MIN_GAP_SECONDS = 1.0            # at most one adsbdb request per second
MAX_ENTRIES = 500

MIN_OFF_ROUTE_KM = 150.0
OFF_ROUTE_FRACTION = 0.2

_AIRLINE_CALLSIGN = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9]{0,4}$")


def route_callsign(aircraft):
    """The callsign to look up, or None when it is not an airline-style one
    (registrations used as callsigns have no route)."""
    callsign = ((aircraft or {}).get("callsign") or "").strip().upper()
    return callsign if _AIRLINE_CALLSIGN.match(callsign) else None


def build_route_url(callsign):
    return ROUTE_URL.format(callsign=urllib.parse.quote(callsign, safe=""))


def fetch_route(callsign):
    """The route for `callsign`, or None when adsbdb has none. Raises
    api.FlightError (status 404 for an unknown callsign)."""
    return parse_route(api.fetch_json(build_route_url(callsign), timeout=ROUTE_TIMEOUT_SECONDS))


def _airport(raw):
    if not isinstance(raw, dict):
        return None
    lat, lon = api.to_float(raw.get("latitude")), api.to_float(raw.get("longitude"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    airport = {"latitude": lat, "longitude": lon}
    for key in ("municipality", "name", "iata_code", "icao_code"):
        value = raw.get(key)
        airport[key] = value.strip() if isinstance(value, str) else ""
    if not airport["municipality"] and not airport["name"]:
        return None
    return airport


def parse_route(payload):
    """adsbdb callsign JSON -> {"origin", "destination", "midpoint"} or None."""
    response = payload.get("response") if isinstance(payload, dict) else None
    flightroute = response.get("flightroute") if isinstance(response, dict) else None
    if not isinstance(flightroute, dict):
        return None
    origin = _airport(flightroute.get("origin"))
    destination = _airport(flightroute.get("destination"))
    if not origin or not destination:
        return None
    return {"origin": origin, "destination": destination,
            "midpoint": _airport(flightroute.get("midpoint"))}


def place_name(airport):
    """The town an airport serves, or its name."""
    return airport.get("municipality") or airport.get("name") or ""


# ------------------------------------------------------------
# Plausibility
# ------------------------------------------------------------

def track_distances(start, end, latitude, longitude):
    """(route length, cross-track distance, along-track distance) in km for a
    point against the great circle start -> end. Along-track is negative
    behind the start."""
    r = api.EARTH_RADIUS_KM
    length, bearing_route = api.distance_and_bearing(start["latitude"], start["longitude"],
                                                     end["latitude"], end["longitude"])
    to_point, bearing_point = api.distance_and_bearing(start["latitude"], start["longitude"],
                                                       latitude, longitude)
    d13 = to_point / r
    angle = math.radians(bearing_point - bearing_route)
    cross = math.asin(max(-1.0, min(1.0, math.sin(d13) * math.sin(angle))))
    cos_cross = math.cos(cross)
    along = math.acos(max(-1.0, min(1.0, math.cos(d13) / cos_cross))) if cos_cross else 0.0
    if math.cos(angle) < 0:
        along = -along
    return length, abs(cross) * r, along * r


def leg_is_plausible(start, end, latitude, longitude):
    """True when the point lies near the path from start to end: within
    max(150 km, 20% of the leg) of it sideways, and not that far beyond
    either end."""
    length, cross, along = track_distances(start, end, latitude, longitude)
    limit = max(MIN_OFF_ROUTE_KM, OFF_ROUTE_FRACTION * length)
    if length < 1.0:  # same airport at both ends
        return api.distance_and_bearing(start["latitude"], start["longitude"],
                                        latitude, longitude)[0] <= limit
    return cross <= limit and -limit <= along <= length + limit


def plausible_leg(route, latitude, longitude):
    """{"origin", "destination"} of the leg the aircraft is flying, or None
    when its position does not fit the route (or is unknown)."""
    if not route or latitude is None or longitude is None:
        return None
    midpoint = route.get("midpoint")
    legs = ([(route["origin"], midpoint), (midpoint, route["destination"])] if midpoint
            else [(route["origin"], route["destination"])])
    for start, end in legs:
        if leg_is_plausible(start, end, latitude, longitude):
            return {"origin": start, "destination": end}
    return None


# ------------------------------------------------------------
# Lookup with a memory-only cache
# ------------------------------------------------------------

class RouteLookup:
    """Routes by callsign, cached in memory only. lookup() blocks on the
    network: call it from a worker thread. Requests are serialised and spaced
    at least `min_gap` seconds apart across all threads."""

    def __init__(self, fetch=None, ttl=ROUTE_TTL_SECONDS, error_backoff=ERROR_BACKOFF_SECONDS,
                 min_gap=MIN_GAP_SECONDS, clock=time.monotonic, sleep=time.sleep,
                 max_entries=MAX_ENTRIES):
        self._fetch = fetch or fetch_route
        self.ttl = ttl
        self.error_backoff = error_backoff
        self.min_gap = min_gap
        self._clock = clock
        self._sleep = sleep
        self.max_entries = max_entries
        self._entries = {}              # callsign -> (expires, route or None)
        self._lock = threading.Lock()   # guards _entries
        self._request_lock = threading.Lock()
        self._last_request = None
        self._backoff_until = 0.0
        self.requests = 0

    def get(self, callsign):
        """(known, route): known is False when nothing (fresh) is cached."""
        if not callsign:
            return True, None
        with self._lock:
            entry = self._entries.get(callsign)
            if entry is None:
                return False, None
            if self._clock() >= entry[0]:
                del self._entries[callsign]
                return False, None
            return True, entry[1]

    def needs_lookup(self, callsign):
        return bool(callsign) and not self.get(callsign)[0] and not self.backing_off()

    def backing_off(self):
        return self._clock() < self._backoff_until

    def _store(self, callsign, route):
        with self._lock:
            now = self._clock()
            if len(self._entries) >= self.max_entries:
                for key, (expires, _route) in list(self._entries.items()):
                    if now >= expires:
                        del self._entries[key]
                while len(self._entries) >= self.max_entries:
                    del self._entries[next(iter(self._entries))]
            self._entries[callsign] = (now + self.ttl, route)

    def lookup(self, callsign):
        """The route for `callsign` (None if unknown or unavailable)."""
        with self._request_lock:
            known, route = self.get(callsign)
            if known or self.backing_off():
                return route
            if self._last_request is not None:
                wait = self._last_request + self.min_gap - self._clock()
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()
            self.requests += 1
            try:
                route = self._fetch(callsign)
            except api.FlightError as e:
                if e.status != 404:
                    logger.info(f"[Flight Radar] Route lookup failed: {e}")
                    self._backoff_until = self._clock() + self.error_backoff
                    return None
                route = None
            except Exception as e:
                logger.info(f"[Flight Radar] Route lookup failed: {e}")
                self._backoff_until = self._clock() + self.error_backoff
                return None
            self._store(callsign, route)
            return route

    def lookup_many(self, callsigns):
        for callsign in callsigns:
            if callsign:
                self.lookup(callsign)

    def clear(self):
        with self._lock:
            self._entries.clear()
        self._backoff_until = 0.0
