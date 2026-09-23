# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
"Track a flight": reading what the user types (a ticket flight number such as
"GA 408", an ICAO callsign such as "GIA408", or a registration such as
"PK-GPA") and the rules for what to announce about a tracked flight. Pure
logic: no wx, no network, no translated text.
"""

import re

import flight_radar_api as api
import flight_radar_atc as atc
import flight_radar_names as names
import flight_radar_registrations as registrations

TRACK_MAX_SECONDS = 24 * 3600        # tracking stops by itself after a day
AFTER_LANDING_SECONDS = 3600         # ... or an hour after landing
NEAR_DESTINATION_KM = 50
LANDED_ALTITUDE_FT = 330             # about 100 m
LANDED_SPEED_KT = 80
LANDED_NEAR_KM = 10                  # "low and slow" only counts this near the destination

_ICAO_FLIGHT = re.compile(r"^([A-Z]{3})([0-9]{1,4}[A-Z]?)$")
_IATA_FLIGHT = re.compile(r"^([A-Z0-9]{2})([0-9]{1,4}[A-Z]?)$")


class FlightInputError(Exception):
    """`kind`: "empty", "unknown_airline" (with `code`) or "not_understood"."""

    def __init__(self, kind, code=""):
        super().__init__(f"{kind}: {code}" if code else kind)
        self.kind = kind
        self.code = code


def _number(flight):
    """"0408" -> "408"; a letter suffix stays ("15A")."""
    digits = re.match(r"[0-9]+", flight).group(0)
    return (digits.lstrip("0") or "0") + flight[len(digits):]


def _registration(compact):
    """"PKGPA" -> "PK-GPA" when the prefix is a known nationality mark followed
    by 3 or 4 letters; N-, JA- and HL- numbers are written without a dash."""
    if registrations.country_key(compact) in ("US", "JP", "KR"):
        return compact
    for head in sorted(registrations.PREFIXES, key=len, reverse=True):
        mark = compact[len(head):]
        if compact.startswith(head) and 3 <= len(mark) <= 4 and mark.isalpha():
            return f"{head}-{mark}"
    return None


def parse_flight_input(text):
    """{"kind": "callsign", "id": "GIA408"} or {"kind": "registration",
    "id": "PK-GPA"} from "GA 408", "GA408", "ga-408", "GIA 408", "8B 5205",
    "PK-GPA" or "PKGPA". Raises FlightInputError."""
    raw = " ".join((text or "").strip().upper().split())
    if not raw:
        raise FlightInputError("empty")
    if "-" in raw:
        head, _sep, mark = raw.replace(" ", "").partition("-")
        known_airline = (names.icao_for_iata(head) if len(head) == 2
                         else head if len(head) == 3 and names.airline_name(head) else None)
        is_flight = mark.isdigit() or bool(re.fullmatch(r"[0-9]{1,4}[A-Z]", mark))
        if registrations.country_key(raw.replace(" ", "")) and not (known_airline and is_flight):
            if re.fullmatch(r"[A-Z0-9]{1,4}-[A-Z0-9]{1,5}", f"{head}-{mark}"):
                return {"kind": "registration", "id": f"{head}-{mark}"}
    compact = raw.replace(" ", "").replace("-", "")
    match = _ICAO_FLIGHT.match(compact)
    if match:
        # A 3-letter prefix is already the callsign form, known airline or not.
        return {"kind": "callsign", "id": match.group(1) + _number(match.group(2))}
    match = _IATA_FLIGHT.match(compact)
    if match and re.search(r"[A-Z]", match.group(1)):
        icao = names.icao_for_iata(match.group(1))
        if icao:
            return {"kind": "callsign", "id": icao + _number(match.group(2))}
        if not _registration(compact):
            raise FlightInputError("unknown_airline", match.group(1))
    registration = _registration(compact)
    if registration:
        return {"kind": "registration", "id": registration}
    raise FlightInputError("not_understood")


def target_key(target):
    return (target["kind"], target["id"])


def pick_aircraft(aircraft):
    """The one aircraft to report when a lookup finds several (a stale copy, or
    one tracked by two receivers): airborne first, then the freshest."""
    if not aircraft:
        return None

    def rank(plane):
        seen = plane.get("seen")
        return (plane.get("on_ground", False), seen if seen is not None else 1e9)

    return sorted(aircraft, key=rank)[0]


def new_entry(target, now):
    return {"kind": target["kind"], "id": target["id"], "added": float(now),
            "landed_at": None, "seen_airborne": False, "notified": []}


def should_stop(entry, now):
    """Tracking ends 24 hours after it began, or an hour after landing."""
    if now - entry.get("added", 0) >= TRACK_MAX_SECONDS:
        return True
    landed = entry.get("landed_at")
    return landed is not None and now - landed >= AFTER_LANDING_SECONDS


def destination_airport(leg):
    """The destination of a plausible route leg, with coordinates, or None."""
    if not leg:
        return None
    airport = atc.route_airport(leg.get("destination"))
    if airport and airport.get("latitude") is not None:
        return airport
    return None


def _km(plane, airport):
    return api.distance_and_bearing(airport["latitude"], airport["longitude"],
                                    plane["lat"], plane["lon"])[0]


def evaluate(entry, plane, now, leg=None, near_you_km=None, quiet=False):
    """What to announce about a tracked flight after a new observation, each
    thing once: [(event, detail)] with event in "airborne", "near_you",
    "near_destination", "landed". Updates `entry`. `near_you_km` is the alert
    distance when the user's location is known (the plane's distance_km is
    from it). With `quiet`, the first sighting is only recorded (the user has
    just heard where the flight is)."""
    if plane is None or plane.get("lat") is None:
        return []
    events = []
    notified = entry.setdefault("notified", [])

    def once(event, detail=None):
        if event not in notified:
            notified.append(event)
            if not quiet:
                events.append((event, detail))

    airborne = not plane.get("on_ground")
    if airborne and not entry.get("seen_airborne"):
        entry["seen_airborne"] = True
        once("airborne")
    destination = destination_airport(leg)
    to_destination = _km(plane, destination) if destination else None
    if airborne and near_you_km is not None and plane.get("distance_km", 1e9) <= near_you_km:
        once("near_you")
    if airborne and to_destination is not None and to_destination <= NEAR_DESTINATION_KM:
        once("near_destination", {"airport": destination, "km": to_destination})
    if entry.get("seen_airborne") and "landed" not in notified:
        altitude, speed = plane.get("altitude_ft"), plane.get("speed_kt")
        low_and_slow = (altitude is not None and altitude <= LANDED_ALTITUDE_FT
                        and (speed is None or speed <= LANDED_SPEED_KT)
                        and to_destination is not None and to_destination <= LANDED_NEAR_KM)
        if plane.get("on_ground") or low_and_slow:
            entry["landed_at"] = float(now)
            once("landed")
    return events
