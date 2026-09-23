# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for the Weather extension, in the user's language.
Numbers are written out with words ("27 degrees", "80 percent") so every
screen reader says them the same way.
"""

import datetime
import os
import time

from core.i18n import format_date, get_translator

import weather_api

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("weather", os.path.join(EXT_DIR, "locales"))

# WMO weather interpretation codes used by Open-Meteo.
KNOWN_CODES = (0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67,
               71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99)

_ERROR_KEYS = {"offline": "err_offline", "service": "err_service",
               "bad_response": "err_bad_response"}


def condition_text(code):
    return _(f"wmo_{code}") if code in KNOWN_CODES else _("wmo_unknown")


def error_text(kind):
    return _(_ERROR_KEYS.get(kind, "err_bad_response"))


def unit_name(units):
    return _("unit_fahrenheit") if units == "imperial" else _("unit_celsius")


def _temp(celsius, units):
    value = weather_api.convert_temperature(celsius, units)
    return None if value is None else str(int(round(value)))


def _sentence(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ""
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] + "."


def _day_parts(day, units):
    """[condition, high, low, rain chance] pieces for one forecast day."""
    high, low = _temp(day.get("high"), units), _temp(day.get("low"), units)
    rain = day.get("rain_chance")
    return [
        condition_text(day.get("code")) if day.get("code") is not None else None,
        _("piece_high", temp=high) if high is not None else None,
        _("piece_low", temp=low) if low is not None else None,
        _("piece_rain_chance", value=rain) if rain is not None else None,
    ]


def current_report(location, forecast, units, now_utc=None):
    """The full answer for "Speak current weather"."""
    cur = forecast["current"]
    feels = _temp(cur.get("feels_like"), units)
    wind = weather_api.convert_speed(cur.get("wind_speed"), units)
    wind_key = "piece_wind_imperial" if units == "imperial" else "piece_wind_metric"

    first = [
        _("piece_condition_temp", condition=condition_text(cur.get("code")),
          temp=_temp(cur.get("temperature"), units)),
        _("piece_feels_like", temp=feels) if feels is not None else None,
    ]
    second = [
        _("piece_humidity", value=cur["humidity"]) if cur.get("humidity") is not None else None,
        _(wind_key, value=int(round(wind))) if wind is not None else None,
    ]
    sentences = [f"{location['name']}: {_sentence(first)}", _sentence(second)]

    today = weather_api.day_entry(forecast, weather_api.location_today(forecast, now_utc))
    if today:
        day_text = ", ".join(p for p in _day_parts(today, units)[1:] if p)
        if day_text:
            sentences.append(_("today_prefix", text=day_text))
    return " ".join(s for s in sentences if s)


def briefing_sentence(location, forecast, units, now_utc=None):
    """One sentence for the Morning Briefing."""
    cur = forecast["current"]
    parts = [_("piece_condition_temp", condition=condition_text(cur.get("code")),
               temp=_temp(cur.get("temperature"), units))]
    today = weather_api.day_entry(forecast, weather_api.location_today(forecast, now_utc))
    if today:
        parts += _day_parts(today, units)[1:]
    return _("weather_in", place=location["name"], text=", ".join(p for p in parts if p))


def forecast_rows(forecast, units, now_utc=None):
    """One line per day from today on, e.g. 'Tomorrow, Thursday 24 September: ...'."""
    today = weather_api.location_today(forecast, now_utc)
    try:
        tomorrow = (datetime.datetime.strptime(today, "%Y-%m-%d")
                    + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        tomorrow = ""
    rows = []
    for day in forecast.get("daily") or []:
        date_str = day.get("date", "")
        if date_str < today:
            continue
        try:
            label = format_date(datetime.datetime.strptime(date_str, "%Y-%m-%d").date(), "%A %d %B")
        except ValueError:
            continue
        if date_str == today:
            label = _("day_today", date=label)
        elif date_str == tomorrow:
            label = _("day_tomorrow", date=label)
        text = ", ".join(p for p in _day_parts(day, units) if p)
        rows.append(f"{label}: {text}" if text else label)
    return rows


def time_text(timestamp, now=None):
    """Local clock time of `timestamp`, with the date when it is not today."""
    when = datetime.datetime.fromtimestamp(timestamp)
    today = datetime.datetime.fromtimestamp(time.time() if now is None else now).date()
    clock = when.strftime("%H:%M")
    if when.date() == today:
        return clock
    return f"{format_date(when.date(), '%d %B')} {clock}"
