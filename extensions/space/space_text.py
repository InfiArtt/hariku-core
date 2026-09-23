# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for the Space extension, in the user's language.
Times are the location's local time (or the computer's when the location has
no time zone). Numbers are rounded for listening and written with the
language's separators.
"""

import datetime
import os

from core.i18n import format_date, get_current_language, get_translator

import space_api as api
import space_astro as astro
import space_countries as countries

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("space", os.path.join(EXT_DIR, "locales"))

HORIZON_MIN_DEGREES = 10     # "above your horizon" from this elevation
DARK_SUN_ALTITUDE = -6       # the sky counts as dark below civil twilight

_ISS_ERRORS = {"offline": "err_iss_offline", "service": "err_iss_service",
               "rate_limited": "err_iss_rate_limited", "bad_response": "err_iss_bad_response"}
_LAUNCH_ERRORS = {"offline": "err_launch_offline", "service": "err_launch_service",
                  "rate_limited": "err_launch_rate_limited",
                  "bad_response": "err_launch_bad_response"}


def language():
    return "id" if get_current_language() == "id" else "en"


# ------------------------------------------------------------
# Numbers, units, times
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


def distance_text(km):
    """Whole kilometres under 100, then to the nearest 10, then 100."""
    if km < 100:
        value = round(km)
    elif km < 1000:
        value = int(round(km, -1))
    else:
        value = int(round(km, -2))
    return _("unit_km_one", value=number(value)) if value == 1 else _("unit_km", value=number(value))


def altitude_text(km):
    value = int(round(km))
    return _("unit_km_one", value=number(value)) if value == 1 else _("unit_km", value=number(value))


def speed_text(kmh):
    return _("unit_kmh", value=number(int(round(kmh, -1))))


def compass(degrees):
    names = [_("dir_n"), _("dir_ne"), _("dir_e"), _("dir_se"),
             _("dir_s"), _("dir_sw"), _("dir_w"), _("dir_nw")]
    return names[astro.compass_index(degrees)]


def _unit(value, one_key, many_key):
    return _(one_key, value=value) if value == 1 else _(many_key, value=number(value))


def duration_text(minutes):
    """"2 hours 5 minutes", "45 minutes", "3 days 4 hours"."""
    minutes = max(0, int(round(minutes)))
    if minutes < 1:
        return _("duration_under_minute")
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days >= 2:
        parts = [_unit(days, "unit_day_one", "unit_day"),
                 _unit(hours, "unit_hour_one", "unit_hour") if hours else None]
    else:
        hours += days * 24
        parts = [_unit(hours, "unit_hour_one", "unit_hour") if hours else None,
                 _unit(mins, "unit_minute_one", "unit_minute") if mins else None]
    return " ".join(p for p in parts if p)


def local(when, tz):
    return when.astimezone(tz) if tz is not None else when.astimezone()


def _round_minute(when):
    return (when + datetime.timedelta(seconds=30)).replace(second=0, microsecond=0)


def clock(when, tz):
    """"20:30", rounded to the nearest minute."""
    return local(_round_minute(when), tz).strftime("%H:%M")


def date_text(day):
    """"Friday 25 September" (no leading zero)."""
    return f"{format_date(day, '%A')} {day.day} {format_date(day, '%B')}"


def day_text(when, tz, now):
    """"today", "tomorrow" or "Friday 25 September", seen from `now`."""
    day, today = local(when, tz).date(), local(now, tz).date()
    if day == today:
        return _("day_today")
    if day == today + datetime.timedelta(days=1):
        return _("day_tomorrow")
    return date_text(day)


def at_text(when, tz, now):
    """"today at 20:30"."""
    when = _round_minute(when)
    return _("when_at", day=day_text(when, tz, now), time=clock(when, tz))


def _sentence(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ""
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] + "."


# ------------------------------------------------------------
# The ISS
# ------------------------------------------------------------

def country_phrase(code):
    """"over Australia", "over the ocean", or None when unknown."""
    if code is None:
        return None
    if code == "":
        return _("iss_over_ocean")
    name = countries.country_name(code, language())
    return _("iss_over_country", country=name) if name else None


def _coordinates(position):
    lat, lon = position["latitude"], position["longitude"]
    return _("iss_coordinates",
             lat=number(abs(lat)), ns=_("lat_s") if lat < 0 else _("lat_n"),
             lon=number(abs(lon)), ew=_("lon_w") if lon < 0 else _("lon_e"))


def iss_report(position, country, location, now):
    """The answer to "Where is the ISS?". `country` is a country code, ""
    over the ocean, or None when unknown; `location` may be None."""
    over = country_phrase(country)
    sentences = []
    ground_km = bearing = None
    if location:
        ground_km, bearing = astro.distance_and_bearing(
            location["latitude"], location["longitude"], position["latitude"], position["longitude"])
        where = _("iss_where", distance=distance_text(ground_km), direction=compass(bearing))
        sentences.append(f"{where}, {over}." if over else f"{where}.")
    elif over:
        sentences.append(_("iss_where_over", over=over))
    else:
        sentences.append(_coordinates(position))

    motion = []
    if position.get("altitude_km") is not None:
        motion.append(_("piece_altitude", altitude=altitude_text(position["altitude_km"])))
    if position.get("speed_kmh") is not None:
        motion.append(_("piece_speed", speed=speed_text(position["speed_kmh"])))
    if motion:
        sentences.append(_("iss_motion", text=", ".join(motion)))
    if position.get("visibility") == "daylight":
        sentences.append(_("iss_daylight"))
    elif position.get("visibility") == "eclipsed":
        sentences.append(_("iss_eclipsed"))

    if location and position.get("altitude_km"):
        elevation = astro.elevation_angle(ground_km, position["altitude_km"])
        if elevation >= HORIZON_MIN_DEGREES:
            sentences.append(_("iss_above_horizon", degrees=number(int(round(elevation))),
                               direction=compass(bearing)))
            sky_dark = astro.sun_altitude(now, location["latitude"],
                                          location["longitude"]) < DARK_SUN_ALTITUDE
            if position.get("visibility") == "daylight" and sky_dark:
                sentences.append(_("iss_may_be_visible"))
    if not location:
        sentences.append(_("iss_set_location"))
    return " ".join(sentences)


def iss_error_text(kind):
    return _(_ISS_ERRORS.get(kind, "err_iss_bad_response"))


# ------------------------------------------------------------
# Launches
# ------------------------------------------------------------

def launch_error_text(kind):
    return _(_LAUNCH_ERRORS.get(kind, "err_launch_bad_response"))


def status_text(launch):
    status_id = launch.get("status_id")
    if status_id in api.KNOWN_STATUSES:
        return _(f"status_{status_id}")
    return launch.get("status_abbrev") or _("status_unknown")


def when_text(launch, tz, now):
    """When a launch is, as exactly as it is known."""
    net = api.launch_time(launch)
    precision = launch.get("precision")
    if api.is_exact(launch):
        return at_text(net, tz, now)
    if precision in api.DAY_PRECISIONS:
        return _("when_day", day=day_text(net, tz, now))
    if precision == api.WEEK_PRECISION:
        return _("when_week", day=day_text(net, tz, now))
    return _("when_month", month=format_date(local(net, tz).date(), "%B %Y"))


def launch_row(launch, tz, now, reminder=False):
    """One row of the list: "Long March 8A, Unknown Payload, today at 20:30,
    from Wenchang, status Go"."""
    values = {"name": api.launch_name(launch), "when": when_text(launch, tz, now),
              "site": api.site_name(launch), "status": status_text(launch)}
    row = _("launch_row", **values) if values["site"] else _("launch_row_no_site", **values)
    return _("launch_row_reminder", row=row) if reminder else row


def _known(value):
    return bool(value) and value.strip().lower() not in ("unknown", "tbd")


def launch_details(launch, tz, now, reminder_lead=None):
    """Everything known about one launch, a sentence per fact."""
    net = api.launch_time(launch)
    sentences = [_sentence([api.launch_name(launch)]),
                 _("detail_when", when=when_text(launch, tz, now))]
    if api.is_exact(launch) and net > now:
        sentences.append(_("detail_countdown",
                           duration=duration_text((net - now).total_seconds() / 60)))
    start, end = api.parse_time(launch.get("window_start")), api.parse_time(launch.get("window_end"))
    if api.is_exact(launch) and start and end:
        if start == end:
            sentences.append(_("detail_window_instant"))
        else:
            sentences.append(_("detail_window", start=clock(start, tz), end=clock(end, tz)))
    sentences.append(_("detail_status", value=status_text(launch)))
    if launch.get("provider"):
        sentences.append(_("detail_provider", value=launch["provider"]))
    pad = ", ".join(p for p in (launch.get("pad"), launch.get("location")) if p)
    if pad:
        sentences.append(_("detail_pad", value=pad))
    if _known(launch.get("mission_type")):
        sentences.append(_("detail_mission", value=launch["mission_type"]))
    if _known(launch.get("orbit")):
        sentences.append(_("detail_orbit", value=launch["orbit"]))
    if reminder_lead:
        sentences.append(_("detail_reminder", lead=duration_text(reminder_lead)))
    return " ".join(sentences)


def reminder_due_text(name, launch, net, tz, now):
    """The reminder itself: "Rocket launch in 30 minutes: Long March 8A, ..."."""
    values = {"duration": duration_text(api.minutes_until(net, now)),
              "name": api.launch_name(launch or {"name": name}),
              "time": clock(net, tz), "site": api.site_name(launch) if launch else ""}
    return _("reminder_due", **values) if values["site"] else _("reminder_due_no_site", **values)


# ------------------------------------------------------------
# Sun and Moon
# ------------------------------------------------------------

def phase_name(key):
    return _(f"phase_{key}")


def moon_sentence(moon):
    return _("moon_phase", phase=phase_name(moon["name"]),
             percent=number(int(round(moon["fraction"] * 100))))


def sun_sentences(sun, tomorrow_sun, tz, now):
    if sun["polar"] == "day":
        return [_("sun_polar_day")]
    if sun["polar"] == "night":
        return [_("sun_polar_night")]
    # From the rounded times, so the numbers the user hears add up.
    length = (_round_minute(sun["sunset"]) - _round_minute(sun["sunrise"])).total_seconds() / 60
    sentences = [_("sun_times", sunrise=clock(sun["sunrise"], tz), sunset=clock(sun["sunset"], tz),
                   length=duration_text(length))]
    if now > sun["sunset"] and tomorrow_sun and tomorrow_sun["sunrise"]:
        sentences.append(_("sun_tomorrow", time=clock(tomorrow_sun["sunrise"], tz)))
    return sentences


def sun_moon_report(location, tz, now):
    """The answer to "Sun and Moon"."""
    today = local(now, tz).date()
    sentences = []
    if location:
        sentences.append(_("sun_moon_place", place=location["name"], date=date_text(today)))
        lat, lon = location["latitude"], location["longitude"]
        sun = astro.sun_times(today, lat, lon, tz)
        tomorrow = astro.sun_times(today + datetime.timedelta(days=1), lat, lon, tz)
        sentences += sun_sentences(sun, tomorrow, tz, now)
    moon = astro.moon_phase(now, tz)
    sentences.append(moon_sentence(moon))
    sentences.append(_("moon_next_full", when=at_text(moon["next_full"], tz, now)))
    sentences.append(_("moon_next_new", when=at_text(moon["next_new"], tz, now)))
    if not location:
        sentences.append(_("sun_no_location"))
    return " ".join(sentences)


def briefing_text(location, tz, now, launches_today):
    """One or two sentences for the Morning Briefing. `launches_today` are
    cached launches with an exact time later today, soonest first."""
    moon = astro.moon_phase(now, tz)
    phase = phase_name(moon["name"])
    percent = number(int(round(moon["fraction"] * 100)))
    sentences = []
    sun = None
    if location:
        sun = astro.sun_times(local(now, tz).date(), location["latitude"], location["longitude"], tz)
    if sun and sun["sunset"]:
        sentences.append(_("briefing_sun_moon", sunset=clock(sun["sunset"], tz), phase=phase,
                           percent=percent))
    else:
        sentences.append(_("moon_phase", phase=phase, percent=percent))
    if launches_today:
        first = launches_today[0]
        values = {"time": clock(api.launch_time(first), tz), "name": api.launch_name(first)}
        if len(launches_today) == 1:
            sentences.append(_("briefing_launch", **values))
        else:
            sentences.append(_("briefing_launches", count=len(launches_today), **values))
    return " ".join(sentences)


def time_of(timestamp):
    """Clock time of a wall-clock timestamp, with the date when not today."""
    when = datetime.datetime.fromtimestamp(timestamp)
    if when.date() == datetime.date.today():
        return when.strftime("%H:%M")
    return f"{date_text(when.date())} {when.strftime('%H:%M')}"
