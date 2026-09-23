# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for the Air Quality extension, in the user's
language: the US AQI with its category, particles, the UV index with its
category, and one short, factual tip per category (the U.S. EPA's AirNow
guidance, not medical advice).
"""

import datetime
import os
import time

from core.i18n import format_date, get_translator

import air_quality_api as api

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("air_quality", os.path.join(EXT_DIR, "locales"))

_ERROR_KEYS = {"offline": "err_offline", "service": "err_service",
               "bad_response": "err_bad_response"}


def error_text(kind):
    return _(_ERROR_KEYS.get(kind, "err_bad_response"))


def category_text(aqi):
    key = api.aqi_category(aqi)
    return _(f"cat_{key}") if key else ""


def tip_text(aqi):
    key = api.aqi_category(aqi)
    return _(f"tip_{key}") if key else ""


def uv_text(uv):
    """'UV index 7, high' or None."""
    key = api.uv_category(uv)
    if key is None:
        return None
    return _("piece_uv", value=api.uv_value(uv), category=_(f"uv_{key}"))


def pollutant_text(name):
    return _(f"pol_{name}") if name in api.POLLUTANTS else ""


def _particles(value):
    return None if value is None else str(int(value + 0.5))


def _sentence(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ""
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] + "."


def current_report(location, forecast):
    """The full answer for "Speak the air quality"."""
    if not forecast.get("has_data"):
        return _("no_data", place=location["name"])
    cur = forecast["current"]
    aqi = cur.get("aqi")
    first = []
    if aqi is not None:
        first.append(_("piece_aqi", value=aqi, category=category_text(aqi)))
        # "Mostly ozone" says what to look out for; not worth saying on a good day.
        if api.aqi_category(aqi) != "good" and cur.get("main_pollutant"):
            first.append(_("piece_main", pollutant=pollutant_text(cur["main_pollutant"])))
    particles = [_("piece_pm2_5", value=_particles(cur.get("pm2_5"))) if cur.get("pm2_5") is not None else None,
                 _("piece_pm10", value=_particles(cur.get("pm10"))) if cur.get("pm10") is not None else None]
    particles = [p for p in particles if p]
    sentences = [
        _sentence(first),
        _("pm_sentence", values=", ".join(particles)) if particles else "",
        _sentence([uv_text(cur.get("uv"))]),
        tip_text(aqi) if aqi is not None else "",
    ]
    text = " ".join(s for s in sentences if s)
    return f"{location['name']}: {text}" if text else _("no_data", place=location["name"])


def briefing_sentence(location, forecast):
    """One sentence for the Morning Briefing, or "" without data."""
    aqi = (forecast.get("current") or {}).get("aqi") if forecast.get("has_data") else None
    if aqi is None:
        return ""
    return _("briefing", place=location["name"], value=aqi, category=category_text(aqi))


def alert_text(location, aqi):
    return _("alert", place=location["name"], value=aqi, category=category_text(aqi),
             tip=tip_text(aqi))


# ------------------------------------------------------------
# Forecast rows
# ------------------------------------------------------------

def _row_parts(aqi, pm2_5, uv, up_to=False):
    suffix = "_up_to" if up_to else ""
    parts = []
    if aqi is not None:
        parts.append(_("row_aqi" + suffix, value=aqi, category=category_text(aqi)))
    if pm2_5 is not None:
        parts.append(_("row_pm2_5" + suffix, value=_particles(pm2_5)))
    # Night hours have no sun; leave "UV index 0" out of the hourly rows.
    if uv is not None and (up_to or api.uv_value(uv) > 0):
        key = api.uv_category(uv)
        parts.append(_("row_uv" + suffix, value=api.uv_value(uv), category=_(f"uv_{key}")))
    return parts


def hour_rows(forecast, now_utc=None):
    """'Today 21:00: index 219, very unhealthy, PM2.5 122.' every 3 hours for a day."""
    today = api.location_now(forecast, now_utc).date()
    rows = []
    for hour in api.coming_hours(forecast, now_utc):
        when = datetime.datetime.strptime(hour["time"], "%Y-%m-%dT%H:%M")
        days = (when.date() - today).days
        clock = when.strftime("%H:%M")
        if days == 0:
            label = _("hour_today", time=clock)
        elif days == 1:
            label = _("hour_tomorrow", time=clock)
        else:
            label = _("hour_day", day=format_date(when.date(), "%A"), time=clock)
        parts = _row_parts(hour.get("aqi"), hour.get("pm2_5"), hour.get("uv"))
        rows.append(f"{label}: {', '.join(parts)}." if parts else f"{label}: {_('row_no_data')}")
    return rows


def day_rows(forecast, now_utc=None):
    """One sentence per day from today on, with that day's highest values."""
    now = api.location_now(forecast, now_utc)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    rows = []
    for day in api.daily_summary(forecast, now_utc):
        date_str = day["date"]
        try:
            label = format_date(datetime.datetime.strptime(date_str, "%Y-%m-%d").date(), "%A %d %B")
        except ValueError:
            continue
        if date_str == today:
            label = _("day_today", date=label)
        elif date_str == tomorrow:
            label = _("day_tomorrow", date=label)
        parts = _row_parts(day["aqi_max"], day["pm2_5_max"], day["uv_max"], up_to=True)
        rows.append(f"{label}: {', '.join(parts)}." if parts else f"{label}: {_('row_no_data')}")
    return rows


def time_text(timestamp, now=None):
    """Local clock time of `timestamp`, with the date when it is not today."""
    when = datetime.datetime.fromtimestamp(timestamp)
    today = datetime.datetime.fromtimestamp(time.time() if now is None else now).date()
    clock = when.strftime("%H:%M")
    if when.date() == today:
        return clock
    return f"{format_date(when.date(), '%d %B')} {clock}"
