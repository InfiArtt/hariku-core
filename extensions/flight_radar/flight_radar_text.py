# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for the Flight Radar extension, in the user's
language. Callsign prefixes become airline names, type codes become model
names, and codes without a name are spelled out ("S J V 357") so the screen
reader does not try to read them as words. Numbers are rounded for listening.
"""

import datetime
import os
import re

from core.i18n import get_current_language, get_translator

import flight_radar_airports as airports
import flight_radar_api as api
import flight_radar_atc as atc
import flight_radar_names as names
import flight_radar_registrations as registrations
import flight_radar_routes as routes

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("flight_radar", os.path.join(EXT_DIR, "locales"))

NEARBY_COUNT = 3               # aircraft spoken by "What's flying nearby?"
LEVEL_RATE_FPM = 250           # slower climbs and descents count as level

_ERROR_KEYS = {"offline": "err_offline", "service": "err_service",
               "rate_limited": "err_rate_limited", "bad_response": "err_bad_response"}
_AIRLINE_CALLSIGN = re.compile(r"^([A-Z]{3})([0-9][A-Z0-9]*)$")


# ------------------------------------------------------------
# Numbers, units and directions
# ------------------------------------------------------------

def _separator(key_text, default):
    return key_text if len(key_text) <= 1 else default


def number(value, decimals=0):
    """`value` with the language's thousands and decimal separators."""
    if value == 0:
        value = 0.0  # never "-0"
    text = f"{value:,.{decimals}f}"
    thousands = _separator(_("number_thousands"), ",")
    decimal = _separator(_("number_decimal"), ".") or "."
    return text.replace(",", "\0").replace(".", decimal).replace("\0", thousands)


def distance_text(km, units):
    """0.1 precision under 10, whole numbers above."""
    metric = units != "aviation"
    value = km if metric else api.km_to_nm(km)
    if value < 10:
        value = round(value, 1)
        decimals = 0 if value == int(value) else 1
    else:
        value, decimals = round(value), 0
    text = number(value, decimals)
    if decimals == 0 and value == 1:
        return _("unit_km_one", value=text) if metric else _("unit_nm_one", value=text)
    return _("unit_km", value=text) if metric else _("unit_nm", value=text)


def _round_to(value, step):
    return int(round(value / step) * step)


def altitude_text(feet, units):
    """Rounded to 100 metres or feet (to 10 when very low)."""
    metric = units != "aviation"
    value = max(0.0, api.ft_to_m(feet) if metric else feet)
    value = _round_to(value, 100 if value >= 100 else 10)
    return _("unit_m", value=number(value)) if metric else _("unit_ft", value=number(value))


def speed_text(knots, units):
    metric = units != "aviation"
    value = max(0.0, api.kt_to_kmh(knots) if metric else knots)
    value = _round_to(value, 10 if value >= 100 else 1)
    return _("unit_kmh", value=number(value)) if metric else _("unit_kt", value=number(value))


def rate_text(fpm, units):
    """A climb or descent rate without its sign."""
    if units != "aviation":
        return _("unit_m_per_min", value=number(_round_to(abs(api.ft_to_m(fpm)), 10)))
    return _("unit_ft_per_min", value=number(_round_to(abs(fpm), 100)))


def compass_names():
    return [_("dir_n"), _("dir_ne"), _("dir_e"), _("dir_se"),
            _("dir_s"), _("dir_sw"), _("dir_w"), _("dir_nw")]


def compass(degrees):
    """8-point compass direction, or None."""
    if degrees is None:
        return None
    return compass_names()[api.compass_index(degrees)]


def trend(fpm):
    """"climbing", "descending", "level" or None."""
    if fpm is None:
        return None
    if fpm >= LEVEL_RATE_FPM:
        return "climbing"
    if fpm <= -LEVEL_RATE_FPM:
        return "descending"
    return "level"


def _trend_word(kind):
    return {"climbing": _("trend_climbing"), "descending": _("trend_descending"),
            "level": _("trend_level")}.get(kind)


# ------------------------------------------------------------
# Names
# ------------------------------------------------------------

def spell_code(code):
    """Letters one by one, digit runs kept together: "SJV357" -> "S J V 357"."""
    return " ".join(t.upper() for t in re.findall(r"[A-Za-z]|[0-9]+", code or ""))


def spell_all(code):
    """Every letter and digit separately: "PK-GPA" -> "P K G P A"."""
    return " ".join(ch.upper() for ch in (code or "") if ch.isascii() and ch.isalnum())


def registration_text(reg):
    """"registration 9 V T N G, Singapore": a registration said as one, with
    the country of its prefix when known."""
    country = registrations.country_name(reg, get_current_language())
    if country:
        return _("registration_name", reg=spell_all(reg), country=country)
    return _("registration_name_no_country", reg=spell_all(reg))


def _is_registration(callsign, plane):
    """Aircraft without an airline callsign often broadcast their registration."""
    reg = (plane.get("registration") or "").replace("-", "").upper()
    if reg and callsign.replace("-", "").upper() == reg:
        return True
    return registrations.country_key(callsign) is not None


def aircraft_name(plane):
    """"Garuda Indonesia 155", else a registration ("registration 9 V T N G,
    Singapore"), else the spelled callsign."""
    callsign = plane.get("callsign") or ""
    match = _AIRLINE_CALLSIGN.match(callsign)
    if match:
        airline = names.airline_name(match.group(1))
        if airline:
            flight = match.group(2)
            digits = re.match(r"[0-9]+", flight).group(0)
            flight = (digits.lstrip("0") or "0") + flight[len(digits):]
            return f"{airline} {spell_code(flight)}"
    if callsign and not _is_registration(callsign, plane):
        return spell_code(callsign)
    if plane.get("registration") or callsign:
        return registration_text(plane.get("registration") or callsign)
    return _("unidentified")


def _tidy_description(desc):
    """"BOEING 737-800" -> "Boeing 737-800"; short acronyms stay as they are."""
    return " ".join(w.capitalize() if w.isalpha() and w.isupper() and len(w) > 3 else w
                    for w in desc.split())


def type_name(plane):
    code = plane.get("type_code") or ""
    name = names.aircraft_type_name(code)
    if not name and plane.get("type_desc"):
        name = _tidy_description(plane["type_desc"])
    if not name and code:
        name = spell_code(code)
    if name and names.is_helicopter(code, plane.get("category")):
        name = _("type_helicopter", name=name)
    return name or None


def route_text(leg):
    """"from Batam to Jakarta" for a plausible route leg, or None."""
    if not leg:
        return None
    origin, destination = routes.place_name(leg["origin"]), routes.place_name(leg["destination"])
    if not origin or not destination:
        return None
    return _("piece_route", origin=origin, destination=destination)


def squawk_meaning(squawk):
    """What a transponder code means, e.g. 7700 -> "general emergency"."""
    return {
        "7700": _("squawk_7700"), "7600": _("squawk_7600"), "7500": _("squawk_7500"),
        "2000": _("squawk_2000"), "7000": _("squawk_7000"), "1200": _("squawk_1200"),
    }.get(squawk) or _("squawk_other")


def status_meaning(status):
    """What a readsb emergency value means, or None for none/reserved/unknown."""
    return {
        "general": _("status_general"), "lifeguard": _("status_lifeguard"),
        "minfuel": _("status_minfuel"), "nordo": _("status_nordo"),
        "unlawful": _("status_unlawful"), "downed": _("status_downed"),
    }.get(status)


def _where(plane, units):
    """"20 kilometres west" (and "on the ground" when it is)."""
    distance = distance_text(plane["distance_km"], units)
    direction = compass(plane.get("bearing"))
    where = (_("piece_distance_direction", distance=distance, direction=direction)
             if direction else distance)
    return f"{where}, {_('piece_on_ground')}" if plane.get("on_ground") else where


# ------------------------------------------------------------
# Sentences
# ------------------------------------------------------------

def _sentence(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ""
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] + "."


def aircraft_sentence(plane, units, leg=None):
    """One aircraft, e.g. "Garuda Indonesia 155, from Batam to Jakarta, Boeing
    737-800, 12 kilometres northeast, 3,000 metres, descending." `leg` is a
    plausible route leg (or None)."""
    parts = [aircraft_name(plane), route_text(leg), type_name(plane), _where(plane, units)]
    if not plane.get("on_ground"):
        if plane.get("altitude_ft") is not None:
            parts.append(_("piece_altitude", altitude=altitude_text(plane["altitude_ft"], units)))
        parts.append(_trend_word(trend(plane.get("vertical_rate_fpm"))))
    sentence = _sentence(parts)
    return _("row_emergency", text=sentence) if api.is_emergency(plane) else sentence


def emergency_text(aircraft, units):
    """"Attention: Garuda Indonesia 155 is squawking 7 7 0 0, general
    emergency, 20 kilometres west." for each aircraft in emergency. Worded as
    what the transponder says, since codes are sometimes set by mistake."""
    sentences = []
    for plane in api.emergencies(aircraft):
        squawk, status = api.emergency_squawk(plane), api.emergency_status(plane)
        squawking = (_("emergency_squawking", code=spell_all(squawk), meaning=squawk_meaning(squawk))
                     if squawk else None)
        # "downed" already says "reported" in its own wording ("pesawat
        # dilaporkan jatuh"), so it gets a sentence without "reports".
        reports_key = "emergency_reports_downed" if status == "downed" else "emergency_reports"
        reports = (_(reports_key, meaning=status_meaning(status))
                   if status and status != api.EMERGENCY_SQUAWKS.get(squawk) else None)
        if squawking and reports:
            what = _("emergency_both", squawking=squawking, reports=reports)
        else:
            what = squawking or reports
        sentences.append(_("emergency_attention", name=aircraft_name(plane), what=what,
                           where=_where(plane, units)))
    return " ".join(sentences)


def _no_leg(_plane):
    return None


def none_text(radius_km, units, include_ground):
    radius = distance_text(radius_km, units)
    return _("none_in_range", radius=radius) if include_ground else _("none_in_air", radius=radius)


def count_text(count, radius_km, units, include_ground):
    if not count:
        return none_text(radius_km, units, include_ground)
    return _("count_in_range", count=count, radius=distance_text(radius_km, units))


def nearby_report(aircraft, radius_km, units, include_ground, leg_for=_no_leg):
    """The answer to "What's flying nearby?": the nearest aircraft (visible
    list, nearest first), then how many more there are."""
    if not aircraft:
        return none_text(radius_km, units, include_ground)
    sentences = [aircraft_sentence(p, units, leg_for(p)) for p in aircraft[:NEARBY_COUNT]]
    more = len(aircraft) - NEARBY_COUNT
    if more > 0:
        sentences.append(_("more_in_range", count=more, radius=distance_text(radius_km, units)))
    return " ".join(sentences)


def alert_text(aircraft, units, leg_for=_no_leg):
    return " ".join(_("alert_overhead", text=aircraft_sentence(p, units, leg_for(p)))
                    for p in aircraft)


def details_text(plane, units, leg=None):
    """Everything else known about one aircraft."""
    first = _sentence([aircraft_name(plane), route_text(leg)])
    parts = []
    if plane.get("registration"):
        parts.append(_("detail_registration", value=spell_all(plane["registration"])))
    kind = type_name(plane)
    if kind:
        parts.append(_("detail_type", value=kind))
    if plane.get("speed_kt") is not None:
        parts.append(_("detail_speed", value=speed_text(plane["speed_kt"], units)))
    if plane.get("track") is not None:
        parts.append(_("detail_heading", value=compass(plane["track"])))
    rate = plane.get("vertical_rate_fpm")
    movement = trend(rate)
    if movement == "climbing":
        parts.append(_("detail_climbing", value=rate_text(rate, units)))
    elif movement == "descending":
        parts.append(_("detail_descending", value=rate_text(rate, units)))
    elif movement == "level":
        parts.append(_("detail_level"))
    squawk = plane.get("squawk")
    if squawk:
        parts.append(_("detail_squawk", value=spell_all(squawk), meaning=squawk_meaning(squawk)))
    status = plane.get("emergency")
    if status_meaning(status) and status != api.EMERGENCY_SQUAWKS.get(squawk):
        parts.append(_("detail_status", meaning=status_meaning(status)))
    if not parts:
        parts.append(_("detail_none"))
    airport = atc.airport_for_aircraft(plane, leg)
    if airport:
        parts.append(_("detail_atc", airport=airports.label(airport)))
    return " ".join([first] + parts)


def error_text(kind):
    return _(_ERROR_KEYS.get(kind, "err_bad_response"))


def location_error_text(kind):
    """What went wrong with a pasted location, a map link or an address search."""
    return {
        "empty": _("coords_empty"),
        "not_found": _("coords_not_found"),
        "out_of_range": _("coords_out_of_range"),
        "zero": _("coords_zero"),
        "link_no_coordinates": _("link_no_coordinates"),
        "link_failed": _("link_failed"),
        "address_busy": _("err_address_busy"),
    }.get(kind) or _("err_address_search")


def time_text(wall_timestamp):
    return datetime.datetime.fromtimestamp(wall_timestamp).strftime("%H:%M:%S")


def distance_choice(km):
    """A radius or alert distance in both unit systems, for the settings page."""
    return f"{distance_text(km, 'metric')} ({distance_text(km, 'aviation')})"


# ------------------------------------------------------------
# Tracked flights
# ------------------------------------------------------------

def flight_label(target):
    """What to call a tracked flight: "Garuda Indonesia 408" or "registration
    P K G P A, Indonesia"."""
    if target.get("kind") == "registration":
        return registration_text(target["id"])
    return aircraft_name({"callsign": target["id"]})


def flight_input_error_text(error):
    if error.kind == "empty":
        return _("flight_empty")
    if error.kind == "unknown_airline":
        return _("flight_unknown_airline", code=spell_all(error.code))
    return _("flight_not_understood")


def relative_text(plane, units, leg=None):
    """Where an aircraft is, relative to the nearest airport Hariku knows (its
    own table plus the ends of the flight's route): "120 kilometres east of
    Jakarta Soekarno-Hatta", or "at Jakarta Soekarno-Hatta" when very close.
    Nothing is looked up."""
    lat, lon = plane.get("lat"), plane.get("lon")
    if lat is None or lon is None:
        return None
    candidates = []
    nearest = airports.nearest(lat, lon)
    if nearest:
        candidates.append(nearest)
    for end in ("origin", "destination"):
        airport = atc.route_airport((leg or {}).get(end))
        if airport and airport.get("latitude") is not None:
            candidates.append(airport)
    if not candidates:
        return None
    best, best_km, bearing = None, None, None
    for airport in candidates:
        km, degrees = api.distance_and_bearing(airport["latitude"], airport["longitude"], lat, lon)
        if best_km is None or km < best_km:
            best, best_km, bearing = airport, km, degrees
    place = airports.label(best)
    if best_km < 3:
        return _("piece_at_place", place=place)
    return _("piece_relative", distance=distance_text(best_km, units),
             direction=compass(bearing), place=place)


def _flight_state(plane, units):
    """["9,000 metres", "descending"] or ["on the ground"]."""
    if plane.get("on_ground"):
        return [_("piece_on_ground")]
    parts = []
    if plane.get("altitude_ft") is not None:
        parts.append(_("piece_altitude", altitude=altitude_text(plane["altitude_ft"], units)))
    parts.append(_trend_word(trend(plane.get("vertical_rate_fpm"))))
    return [p for p in parts if p]


def tracked_details(plane, units, leg=None):
    """"from Denpasar to Jakarta, 120 kilometres east of Jakarta Soekarno-Hatta,
    9,000 metres, descending"."""
    return ", ".join(p for p in [route_text(leg), relative_text(plane, units, leg)]
                     + _flight_state(plane, units) if p)


def tracked_sentence(plane, units, leg=None, name=None):
    """"Garuda Indonesia 408, from Denpasar to Jakarta, 120 kilometres east of
    Jakarta Soekarno-Hatta, 9,000 metres, descending."."""
    sentence = _sentence([name or aircraft_name(plane), tracked_details(plane, units, leg)])
    return _("row_emergency", text=sentence) if api.is_emergency(plane) else sentence


def not_transmitting_text(name):
    return _("track_not_transmitting", name=name)


def event_text(event, name, plane, units, leg=None, detail=None):
    """The announcement for one tracked-flight event."""
    state = ", ".join(_flight_state(plane, units))
    if event == "airborne":
        return _("event_airborne", name=name, details=tracked_details(plane, units, leg))
    if event == "near_you":
        return _("event_near_you", name=name,
                 details=", ".join(p for p in (_where(plane, units), state) if p))
    if event == "near_destination":
        values = {"name": name, "distance": distance_text(detail["km"], units),
                  "airport": airports.label(detail["airport"])}
        if state:
            return _("event_near_destination", state=state, **values)
        return _("event_near_destination_short", **values)
    return _("event_landed", name=name, where=relative_text(plane, units, leg) or "")


def tracked_row(name, observation, units, leg=None):
    """One row of the tracked-flights list. `observation` is (wall time, plane
    or None) from the last check, or None before the first."""
    if observation is None:
        return _("tracked_row", name=name, status=_("tracked_not_checked"))
    checked, plane = observation
    status = (tracked_details(plane, units, leg) if plane
              else _("tracked_not_transmitting"))
    return _("tracked_row_checked", name=name, status=status, time=time_text(checked))


def location_text(location):
    """How the settings page shows a location: "Jakarta, Indonesia", "Home:
    Jalan Merdeka Barat, ..." or "Home: -6.20880, 106.84560"."""
    kind = location.get("kind", "city")
    if kind == "address":
        return _("location_address", name=location["name"], detail=location.get("detail", ""))
    if kind == "coordinates":
        return _("location_coordinates", name=location["name"],
                 lat=f"{location['latitude']:.5f}", lon=f"{location['longitude']:.5f}")
    return api.place_label(location)


def near_airport_hint(latitude, longitude, units):
    """"about 12 kilometres from Batam Hang Nadim airport", worked out from
    Hariku's own airport table (nothing is looked up), so a blind user can
    tell whether a pasted point is where they expect."""
    airport = airports.nearest(latitude, longitude)
    if airport is None:
        return None
    return _("hint_near_airport", distance=distance_text(airport["distance_km"], units),
             airport=airports.label(airport))
