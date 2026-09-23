# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Offline astronomy for the Space extension: sunrise and sunset (NOAA's solar
position equations), the phases of the Moon (Jean Meeus, Astronomical
Algorithms, 2nd ed., chapter 49, with every periodic term), the Moon's
illuminated fraction (chapter 48), and the geometry of the ISS as seen from
the user's point. Pure maths: no network, no wx, no translated text.

All datetimes going in and out are timezone-aware.
"""

import datetime
import math

UTC = datetime.timezone.utc
EARTH_RADIUS_KM = 6371.0
SUN_ZENITH = 90.833          # sunrise/sunset: refraction plus the Sun's radius
SYNODIC_MONTH = 29.530588861

NEW, FIRST_QUARTER, FULL, LAST_QUARTER = 0.0, 0.25, 0.5, 0.75
PRINCIPAL_PHASES = (NEW, FIRST_QUARTER, FULL, LAST_QUARTER)

# The eight phase names, in order through the month.
PHASE_NAMES = ("new", "waxing_crescent", "first_quarter", "waxing_gibbous",
               "full", "waning_gibbous", "last_quarter", "waning_crescent")
_PRINCIPAL_NAME = {NEW: "new", FIRST_QUARTER: "first_quarter", FULL: "full",
                   LAST_QUARTER: "last_quarter"}
_AFTER_NAME = {NEW: "waxing_crescent", FIRST_QUARTER: "waxing_gibbous",
               FULL: "waning_gibbous", LAST_QUARTER: "waning_crescent"}


def _sin(deg):
    return math.sin(math.radians(deg))


def _cos(deg):
    return math.cos(math.radians(deg))


def julian_day(when):
    return when.astimezone(UTC).timestamp() / 86400.0 + 2440587.5


def from_julian_day(jd):
    return datetime.datetime(1970, 1, 1, tzinfo=UTC) + datetime.timedelta(days=jd - 2440587.5)


# ------------------------------------------------------------
# The Sun (NOAA)
# ------------------------------------------------------------

def _sun_terms(jd):
    """(declination in degrees, equation of time in minutes) at `jd`."""
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    center = (_sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t))
              + _sin(2 * m) * (0.019993 - 0.000101 * t) + _sin(3 * m) * 0.000289)
    omega = 125.04 - 1934.136 * t
    apparent = l0 + center - 0.00569 - 0.00478 * _sin(omega)
    obliquity = (23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
                 + 0.00256 * _cos(omega))
    declination = math.degrees(math.asin(_sin(obliquity) * _sin(apparent)))
    y = math.tan(math.radians(obliquity / 2)) ** 2
    eq_time = 4 * math.degrees(y * _sin(2 * l0) - 2 * e * _sin(m)
                               + 4 * e * y * _sin(m) * _cos(2 * l0)
                               - 0.5 * y * y * _sin(4 * l0) - 1.25 * e * e * _sin(2 * m))
    return declination, eq_time


def _hour_angle(latitude, declination, zenith=SUN_ZENITH):
    """(hour angle in degrees, None), or (None, "day"/"night") when the Sun
    stays above or below the horizon all day."""
    lat = max(-89.99, min(89.99, latitude))
    cos_h = (_cos(zenith) / (_cos(lat) * _cos(declination))
             - math.tan(math.radians(lat)) * math.tan(math.radians(declination)))
    if cos_h > 1:
        return None, "night"
    if cos_h < -1:
        return None, "day"
    return math.degrees(math.acos(cos_h)), None


def local_datetime(day, hour, tz):
    """`day` at `hour`:00 in `tz` (None: the computer's own time zone)."""
    naive = datetime.datetime.combine(day, datetime.time(hour))
    return naive.astimezone() if tz is None else naive.replace(tzinfo=tz)


def _solar_noon(near, longitude):
    """(solar noon, the UTC midnight it is counted from) closest to `near`."""
    near = near.astimezone(UTC)
    midnight = near.replace(hour=0, minute=0, second=0, microsecond=0)
    noon = midnight + datetime.timedelta(minutes=720 - 4 * longitude - _sun_terms(julian_day(near))[1])
    midnight += datetime.timedelta(days=round((near - noon).total_seconds() / 86400))
    for _ in range(2):
        noon = midnight + datetime.timedelta(
            minutes=720 - 4 * longitude - _sun_terms(julian_day(noon))[1])
    return noon, midnight


def sun_times(day, latitude, longitude, tz=None):
    """Sunrise, solar noon and sunset on the local date `day` at a place, as
    {"sunrise", "noon", "sunset", "polar"}: aware datetimes in `tz` (sunrise
    and sunset None when the Sun does not rise or set; "polar" is then "day"
    or "night", else None)."""
    noon, midnight = _solar_noon(local_datetime(day, 12, tz), longitude)
    result = {"noon": noon, "sunrise": None, "sunset": None, "polar": None}
    for key, sign in (("sunrise", -1), ("sunset", 1)):
        when = noon
        for _ in range(3):
            declination, eq_time = _sun_terms(julian_day(when))
            angle, polar = _hour_angle(latitude, declination)
            if angle is None:
                result["polar"] = polar
                when = None
                break
            when = midnight + datetime.timedelta(
                minutes=720 - 4 * longitude - eq_time + sign * 4 * angle)
        result[key] = when
    for key in ("noon", "sunrise", "sunset"):
        if result[key] is not None:
            result[key] = result[key].astimezone(tz) if tz is not None else result[key].astimezone()
    if result["sunrise"] is None or result["sunset"] is None:
        result["sunrise"] = result["sunset"] = None
    return result


def sun_altitude(when, latitude, longitude):
    """The Sun's altitude above the horizon in degrees (no refraction)."""
    when = when.astimezone(UTC)
    declination, eq_time = _sun_terms(julian_day(when))
    minutes = when.hour * 60 + when.minute + when.second / 60
    hour_angle = (minutes + eq_time + 4 * longitude) / 4 - 180
    cos_zenith = (_sin(latitude) * _sin(declination)
                  + _cos(latitude) * _cos(declination) * _cos(hour_angle))
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))


# ------------------------------------------------------------
# The Moon (Meeus)
# ------------------------------------------------------------

def delta_t_seconds(year):
    """TT - UT, Espenak & Meeus' polynomial for 2005-2050 (clamped outside)."""
    t = min(max(year, 2005), 2050) - 2000
    return 62.92 + 0.32217 * t + 0.005589 * t * t


_NEW_TERMS = ((-0.40720, 0, 0, 1, 0), (0.17241, 1, 1, 0, 0), (0.01608, 0, 0, 2, 0),
              (0.01039, 0, 0, 0, 2), (0.00739, 1, -1, 1, 0), (-0.00514, 1, 1, 1, 0),
              (0.00208, 2, 2, 0, 0), (-0.00111, 0, 0, 1, -2), (-0.00057, 0, 0, 1, 2),
              (0.00056, 1, 1, 2, 0), (-0.00042, 0, 0, 3, 0), (0.00042, 1, 1, 0, 2),
              (0.00038, 1, 1, 0, -2), (-0.00024, 1, -1, 2, 0))
_FULL_TERMS = ((-0.40614, 0, 0, 1, 0), (0.17302, 1, 1, 0, 0), (0.01614, 0, 0, 2, 0),
               (0.01043, 0, 0, 0, 2), (0.00734, 1, -1, 1, 0), (-0.00515, 1, 1, 1, 0),
               (0.00209, 2, 2, 0, 0), (-0.00111, 0, 0, 1, -2), (-0.00057, 0, 0, 1, 2),
               (0.00056, 1, 1, 2, 0), (-0.00042, 0, 0, 3, 0), (0.00042, 1, 1, 0, 2),
               (0.00038, 1, 1, 0, -2), (-0.00024, 1, -1, 2, 0))
# (coefficient, power of E, M, M', F); the terms both new and full moon share.
_SMALL_TERMS = ((-0.00007, 0, 2, 1, 0), (0.00004, 0, 0, 2, -2), (0.00004, 0, 3, 0, 0),
                (0.00003, 0, 1, 1, -2), (0.00003, 0, 0, 2, 2), (-0.00003, 0, 1, 1, 2),
                (0.00003, 0, -1, 1, 2), (-0.00002, 0, -1, 1, -2), (-0.00002, 0, 1, 3, 0),
                (0.00002, 0, 0, 4, 0))
_QUARTER_TERMS = ((-0.62801, 0, 0, 1, 0), (0.17172, 1, 1, 0, 0), (-0.01183, 1, 1, 1, 0),
                  (0.00862, 0, 0, 2, 0), (0.00804, 0, 0, 0, 2), (0.00454, 1, -1, 1, 0),
                  (0.00204, 2, 2, 0, 0), (-0.00180, 0, 0, 1, -2), (-0.00070, 0, 0, 1, 2),
                  (-0.00040, 0, 0, 3, 0), (-0.00034, 1, -1, 2, 0), (0.00032, 1, 1, 0, 2),
                  (0.00032, 1, 1, 0, -2), (-0.00028, 2, 2, 1, 0), (0.00027, 1, 1, 2, 0),
                  (-0.00005, 0, -1, 1, -2), (0.00004, 0, 0, 2, 2), (-0.00004, 0, 1, 1, 2),
                  (0.00004, 0, -2, 1, 0), (0.00003, 0, 1, 1, -2), (0.00003, 0, 3, 0, 0),
                  (0.00002, 0, 0, 2, -2), (0.00002, 0, -1, 1, 2), (-0.00002, 0, 1, 3, 0))
_PLANETARY = ((0.000325, 299.77, 0.107408), (0.000165, 251.88, 0.016321),
              (0.000164, 251.83, 26.651886), (0.000126, 349.42, 36.412478),
              (0.000110, 84.66, 18.206239), (0.000062, 141.74, 53.303771),
              (0.000060, 207.14, 2.453732), (0.000056, 154.84, 7.306860),
              (0.000047, 34.52, 27.261239), (0.000042, 207.19, 0.121824),
              (0.000040, 291.34, 1.844379), (0.000037, 161.72, 24.198154),
              (0.000035, 239.56, 25.513099), (0.000023, 331.55, 3.592518))


def phase_jde(k):
    """Julian Ephemeris Day of the phase `k` (an integer for a new moon, plus
    .25, .5 or .75 for first quarter, full moon and last quarter; k = 0 is the
    new moon of 6 January 2000)."""
    t = k / 1236.85
    jde = (2451550.09766 + SYNODIC_MONTH * k + 0.00015437 * t ** 2
           - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4)
    e = 1 - 0.002516 * t - 0.0000074 * t ** 2
    m = 2.5534 + 29.10535670 * k - 0.0000014 * t ** 2 - 0.00000011 * t ** 3
    mp = (201.5643 + 385.81693528 * k + 0.0107582 * t ** 2 + 0.00001238 * t ** 3
          - 0.000000058 * t ** 4)
    f = (160.7108 + 390.67050284 * k - 0.0016118 * t ** 2 - 0.00000227 * t ** 3
         + 0.000000011 * t ** 4)
    omega = 124.7746 - 1.56375588 * k + 0.0020672 * t ** 2 + 0.00000215 * t ** 3

    fraction = round((k - math.floor(k)) * 4) / 4
    if fraction == NEW:
        terms = _NEW_TERMS + _SMALL_TERMS
    elif fraction == FULL:
        terms = _FULL_TERMS + _SMALL_TERMS
    else:
        terms = _QUARTER_TERMS
    correction = -0.00017 * _sin(omega)
    for coefficient, e_power, cm, cmp, cf in terms:
        correction += coefficient * e ** e_power * _sin(cm * m + cmp * mp + cf * f)
    if fraction in (FIRST_QUARTER, LAST_QUARTER):
        w = (0.00306 - 0.00038 * e * _cos(m) + 0.00026 * _cos(mp) - 0.00002 * _cos(mp - m)
             + 0.00002 * _cos(mp + m) + 0.00002 * _cos(2 * f))
        correction += w if fraction == FIRST_QUARTER else -w
    for coefficient, a0, rate in _PLANETARY:
        angle = a0 + rate * k
        if a0 == 299.77:
            angle -= 0.009173 * t ** 2
        correction += coefficient * _sin(angle)
    return jde + correction


def phase_time(k):
    """The phase `k` as an aware UTC datetime (Universal Time)."""
    tt = from_julian_day(phase_jde(k))
    return tt - datetime.timedelta(seconds=delta_t_seconds(tt.year + (tt.timetuple().tm_yday - 1) / 365.25))


def _k_near(when, phase):
    when = when.astimezone(UTC)
    year = when.year + (when.timetuple().tm_yday - 1) / 365.25
    return math.floor((year - 2000) * 12.3685) + phase


def next_phase(after, phase):
    """The first `phase` (NEW, FIRST_QUARTER, FULL or LAST_QUARTER) after `after`."""
    k = _k_near(after, phase) - 2
    while phase_time(k) <= after:
        k += 1
    return phase_time(k)


def previous_phase(before, phase):
    """The last `phase` at or before `before`."""
    k = _k_near(before, phase) + 2
    while phase_time(k) > before:
        k -= 1
    return phase_time(k)


def illuminated_fraction(when):
    """The Moon's illuminated fraction (0..1), Meeus 48.1 and 48.4."""
    t = (julian_day(when) + delta_t_seconds(when.year) / 86400.0 - 2451545.0) / 36525.0
    d = (297.8501921 + 445267.1114034 * t - 0.0018819 * t ** 2 + t ** 3 / 545868
         - t ** 4 / 113065000)
    m = 357.5291092 + 35999.0502909 * t - 0.0001536 * t ** 2 + t ** 3 / 24490000
    mp = (134.9633964 + 477198.8675055 * t + 0.0087414 * t ** 2 + t ** 3 / 69699
          - t ** 4 / 14712000)
    i = (180 - d % 360 - 6.289 * _sin(mp) + 2.100 * _sin(m) - 1.274 * _sin(2 * d - mp)
         - 0.658 * _sin(2 * d) - 0.214 * _sin(2 * mp) - 0.110 * _sin(d))
    return (1 + _cos(i)) / 2


def moon_phase(now, tz=None):
    """{"name": one of PHASE_NAMES, "fraction": illuminated 0..1,
    "next_new": datetime, "next_full": datetime}. A principal phase (new,
    first quarter, full, last quarter) is named for the whole local date it
    falls on, as calendars do; between them the intermediate name is used."""
    local = now.astimezone(tz) if tz is not None else now.astimezone()
    today = local.date()
    latest, latest_phase = None, NEW
    name = None
    for phase in PRINCIPAL_PHASES:
        before, after = previous_phase(now, phase), next_phase(now, phase)
        for event in (before, after):
            event_local = event.astimezone(tz) if tz is not None else event.astimezone()
            if event_local.date() == today:
                name = _PRINCIPAL_NAME[phase]
        if latest is None or before > latest:
            latest, latest_phase = before, phase
    return {
        "name": name or _AFTER_NAME[latest_phase],
        "fraction": illuminated_fraction(now),
        "next_new": next_phase(now, NEW),
        "next_full": next_phase(now, FULL),
    }


# ------------------------------------------------------------
# The ISS from the ground
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


def elevation_angle(ground_km, altitude_km):
    """How high above the horizon (degrees) an object `altitude_km` up looks
    from a point `ground_km` away from the spot right below it."""
    theta = ground_km / EARTH_RADIUS_KM
    r, orbit = EARTH_RADIUS_KM, EARTH_RADIUS_KM + altitude_km
    slant = math.sqrt(r * r + orbit * orbit - 2 * r * orbit * math.cos(theta))
    if slant <= 0:
        return 90.0
    return math.degrees(math.asin(max(-1.0, min(1.0, (orbit * math.cos(theta) - r) / slant))))


def compass_index(degrees):
    """0..7 for north, northeast, east, ... northwest."""
    return int(((float(degrees) % 360) + 22.5) // 45) % 8
