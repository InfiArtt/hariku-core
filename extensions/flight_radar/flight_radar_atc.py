# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
"Listen to ATC": which airport's air traffic control to open, and the LiveATC
page for it.

LiveATC's terms forbid using its audio streams in other products, so Hariku
never fetches, embeds or plays anything from liveatc.net. It only builds the
address of LiveATC's own web page, which main.py opens in the user's browser
when the user asks. Nothing here touches the network.
"""

import re

import flight_radar_airports as airports
import flight_radar_api as api

# LiveATC listen pages known to exist; other airports get LiveATC's search
# page, which shows whether that airport has a feed.
LIVEATC_FEEDS = {
    "WIII": "https://www.liveatc.net/hlisten.php?mount=wiii",   # Jakarta Tower/Approach
    "WARR": "https://www.liveatc.net/hlisten.php?mount=warr",   # Surabaya Gnd/Twr/Radar
}
LIVEATC_SEARCH = "https://www.liveatc.net/search/?icao={icao}"

CLIMB_DESCENT_FPM = 300      # faster than this counts as climbing or descending
FEED_PREFERENCE_KM = 60      # a known feed this close wins over a nearer airport
MAX_NEAREST_KM = 500         # beyond this Hariku knows no airport near the point

_ICAO = re.compile(r"^[A-Z0-9]{4}$")


def liveatc_url(icao):
    """(url, has_known_feed) for an airport, or (None, False) for a bad code."""
    icao = (icao or "").strip().upper()
    if not _ICAO.match(icao):
        return None, False
    if icao in LIVEATC_FEEDS:
        return LIVEATC_FEEDS[icao], True
    return LIVEATC_SEARCH.format(icao=icao), False


def nearest_airport(latitude, longitude):
    """The airport nearest to a point, preferring one with a known LiveATC feed
    when it is almost as close (Soekarno-Hatta rather than Halim for central
    Jakarta). None when no listed airport is within MAX_NEAREST_KM."""
    if latitude is None or longitude is None:
        return None
    nearest = airports.nearest(latitude, longitude, max_km=MAX_NEAREST_KM)
    if nearest is None or nearest["icao"] in LIVEATC_FEEDS:
        return nearest
    with_feed = airports.nearest(latitude, longitude, max_km=FEED_PREFERENCE_KM,
                                 among=LIVEATC_FEEDS)
    return with_feed or nearest


def route_airport(end):
    """A route end from adsbdb as an airport dict, or None without an ICAO code.
    Hariku's own table supplies the name when it knows the airport."""
    if not end:
        return None
    icao = (end.get("icao_code") or "").strip().upper()
    if not _ICAO.match(icao):
        return None
    known = airports.by_icao(icao)
    if known:
        return known
    return {"icao": icao, "city": end.get("municipality") or "",
            "name": airports.short_name(end.get("name")),
            "latitude": end.get("latitude"), "longitude": end.get("longitude")}


def _distance_to(airport, latitude, longitude):
    if latitude is None or longitude is None or airport.get("latitude") is None:
        return float("inf")
    return api.distance_and_bearing(latitude, longitude,
                                    airport["latitude"], airport["longitude"])[0]


def airport_for_aircraft(plane, leg=None):
    """The airport whose controllers an aircraft is most likely talking to:
    with a plausible route, the destination when descending, the origin when
    climbing, otherwise the nearer of the two; without one, the airport
    nearest to the aircraft. None when nothing fits."""
    lat, lon = plane.get("lat"), plane.get("lon")
    if leg:
        origin, destination = route_airport(leg.get("origin")), route_airport(leg.get("destination"))
        rate = plane.get("vertical_rate_fpm")
        if destination and rate is not None and rate < -CLIMB_DESCENT_FPM:
            return destination
        if origin and rate is not None and rate > CLIMB_DESCENT_FPM:
            return origin
        ends = [a for a in (origin, destination) if a]
        if ends:
            return min(ends, key=lambda a: _distance_to(a, lat, lon))
    return nearest_airport(lat, lon)
