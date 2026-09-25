# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What you see from the Observation Deck, worked out from the real time (UTC),
with no network: where the sun is overhead, which places are in daylight,
at night, at dawn or at dusk, and what lies right below the station.

The sun: the declination and the equation of time from the day of the year
(good to well under a degree, plenty for "Java is at night"). The station: a
made-up orbit like the ISS's (92.7 minutes a lap, 51.6 degrees inclined),
computed from the clock, so what is below changes as you watch.

Places are world.json's "earth" regions: each has a few points, a name, and
what it looks like by day and by night. The nearest point names the place
below the station or under the sun.
"""

import datetime
import math

SIDEREAL_DAY = 86164.0905          # seconds for one turn of the Earth
ORBIT_MINUTES = 92.68
INCLINATION = 51.64                 # degrees
ORBIT_NODE = 40.0                   # where the orbit crosses the equator northwards (at time 0)
TWILIGHT = 6.0                      # the sun within this many degrees of the horizon: dawn or dusk
HOME = "indonesia"                  # always mentioned: the players' home
EARTH_RADIUS_KM = 6371.0


def _utc(when):
    if when.tzinfo is None:
        return when.replace(tzinfo=datetime.timezone.utc)
    return when.astimezone(datetime.timezone.utc)


def _wrap(lon):
    return (lon + 180.0) % 360.0 - 180.0


def sun_position(when):
    """(latitude, longitude) of the point where the sun is overhead."""
    when = _utc(when)
    day = when.timetuple().tm_yday
    hours = when.hour + when.minute / 60.0 + when.second / 3600.0
    declination = -23.44 * math.cos(2 * math.pi / 365.0 * (day + 10))
    b = 2 * math.pi * (day - 81) / 364.0
    equation_minutes = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    longitude = -15.0 * (hours - 12.0 + equation_minutes / 60.0)
    return declination, _wrap(longitude)


def sun_elevation(lat, lon, when):
    """The sun's height above the horizon at (lat, lon), in degrees."""
    dec, sub_lon = sun_position(when)
    phi, delta = math.radians(lat), math.radians(dec)
    hour_angle = math.radians(lon - sub_lon)
    s = math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.cos(hour_angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, s))))


def phase(lat, lon, when):
    """ "day", "night", "dawn" or "dusk" at (lat, lon)."""
    elevation = sun_elevation(lat, lon, when)
    if elevation > TWILIGHT:
        return "day"
    if elevation < -TWILIGHT:
        return "night"
    _dec, sub_lon = sun_position(when)
    # East of the sun's longitude it's afternoon, west of it morning.
    return "dusk" if _wrap(lon - sub_lon) > 0 else "dawn"


def station_point(when):
    """(latitude, longitude) right below the station."""
    seconds = _utc(when).timestamp()
    period = ORBIT_MINUTES * 60.0
    u = 2 * math.pi * ((seconds % period) / period)
    inc = math.radians(INCLINATION)
    lat = math.degrees(math.asin(math.sin(inc) * math.sin(u)))
    along = math.degrees(math.atan2(math.cos(inc) * math.sin(u), math.cos(u)))
    turned = (seconds % SIDEREAL_DAY) / SIDEREAL_DAY * 360.0
    # The orbit's own slow drift is left out: each lap still crosses other
    # places, because the Earth turns underneath.
    return lat, _wrap(along + ORBIT_NODE - turned)


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def nearest(regions, point):
    """(region, the point of it nearest `point`)."""
    best = None
    for region in regions:
        for p in region["points"]:
            d = distance_km(point, p)
            if best is None or d < best[0]:
                best = (d, region, p)
    return (best[1], best[2]) if best else (None, None)


def region_phase(region, when):
    """A region's phase at its main (first) point."""
    lat, lon = region["points"][0]
    return phase(lat, lon, when)


def describe(regions, when, render):
    """The view, as sentences. render(key, **params) gives a line in the
    reader's language (params may be {"en","id"} dicts)."""
    by_id = {r["id"]: r for r in regions}
    lines = []

    below, point = nearest(regions, station_point(when))
    mentioned = set()
    if below is not None:
        state = phase(point[0], point[1], when)
        view = below.get("night" if state == "night" else "day", "")
        lines.append(render(f"earth_below_{state}", place=below["name"], view=view))
        mentioned.add(below["id"])

    sun_region, _p = nearest(regions, sun_position(when))
    if sun_region is not None and sun_region["id"] not in mentioned:
        lines.append(render("earth_sun", place=sun_region["name"]))
        mentioned.add(sun_region["id"])

    home = by_id.get(HOME)
    if home is not None and HOME not in mentioned:
        state = region_phase(home, when)
        view = home.get("night" if state == "night" else "day", "")
        lines.append(render(f"earth_home_{state}", place=home["name"], view=view))
        mentioned.add(HOME)

    # One place on the line between day and night, if any.
    for region in regions:
        if region["id"] in mentioned or region.get("ocean"):
            continue
        state = region_phase(region, when)
        if state in ("dawn", "dusk"):
            lines.append(render(f"earth_edge_{state}", place=region["name"]))
            break
    return " ".join(line for line in lines if line)
