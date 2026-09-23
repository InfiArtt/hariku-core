# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for the Sea Conditions extension, in the user's
language. Heights use the language's decimal separator ("0.3 metres",
"0,3 meter") and the sea state words of the WMO sea state scale, which BMKG
also uses in Indonesia.
"""

import datetime
import math
import os
import time

from core.i18n import format_date, get_translator

import marine_api
import marine_tides

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("marine", os.path.join(EXT_DIR, "locales"))

# WMO sea state code 3700 (Douglas scale): upper bound in metres -> key.
SEA_STATES = ((0.1, "sea_calm"), (0.5, "sea_smooth"), (1.25, "sea_slight"),
              (2.5, "sea_moderate"), (4.0, "sea_rough"), (6.0, "sea_very_rough"),
              (9.0, "sea_high"), (14.0, "sea_very_high"), (None, "sea_phenomenal"))

_ERROR_KEYS = {"offline": "err_offline", "service": "err_service",
               "bad_response": "err_bad_response"}


# ------------------------------------------------------------
# Numbers, units and words
# ------------------------------------------------------------

def _separator(key_text, default):
    return key_text if len(key_text) <= 1 else default


def round_half_up(value, decimals=0):
    """Rounding as people expect it (4.5 -> 5), where round() gives 4."""
    scale = 10 ** decimals
    magnitude = math.floor(abs(value) * scale + 0.5 + 1e-9) / scale
    return -magnitude if value < 0 else magnitude


def number(value, decimals=0):
    """`value` with the language's decimal separator."""
    value = round_half_up(value, decimals)
    if value == 0:
        value = 0.0  # never "-0"
    text = f"{value:.{decimals}f}"
    return text.replace(".", _separator(_("number_decimal"), ".") or ".")


def height_text(metres):
    """'0.3 metres', '1 metre', '2 metres'; one decimal below 10 metres."""
    if metres < 0.05:
        return _("height_under")
    value = round_half_up(metres, 1) if metres < 10 else round_half_up(metres)
    decimals = 0 if value == int(value) else 1
    key = "unit_metre" if decimals == 0 and value == 1 else "unit_metres"
    return _(key, value=number(value, decimals))


def level_text(metres):
    """A sea level: '0.9 metres above mean sea level' or '... below ...'."""
    value = round_half_up(metres, 1)
    decimals = 0 if value == int(value) else 1
    key = "unit_metre" if decimals == 0 and abs(value) == 1 else "unit_metres"
    amount = _(key, value=number(abs(value), decimals))
    return _("level_below" if value < 0 else "level_above", height=amount)


def sea_state(metres):
    for limit, key in SEA_STATES:
        if limit is None or metres < limit:
            return _(key)
    return _("sea_phenomenal")


def compass(degrees):
    """8-point direction the waves come from, or None."""
    if degrees is None:
        return None
    index = int((degrees % 360) / 45 + 0.5) % 8
    return _(("dir_n", "dir_ne", "dir_e", "dir_se", "dir_s", "dir_sw", "dir_w", "dir_nw")[index])


def error_text(kind):
    return _(_ERROR_KEYS.get(kind, "err_bad_response"))


def _sentence(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ""
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] + "."


def _clock(when):
    return marine_tides.round_time(when).strftime("%H:%M")


def _when(when, now):
    """'at about 14:20', 'tomorrow at about 02:10', 'on Friday at about 03:10'."""
    rounded = marine_tides.round_time(when)
    days = (rounded.date() - now.date()).days
    if days <= 0:
        return _("when_today", time=_clock(when))
    if days == 1:
        return _("when_tomorrow", time=_clock(when))
    return _("when_day", day=format_date(rounded.date(), "%A"), time=_clock(when))


def _row_when(when, now):
    """'today at about 14:20', 'tomorrow at about 02:10', 'Friday 25 September at about 03:10'."""
    rounded = marine_tides.round_time(when)
    days = (rounded.date() - now.date()).days
    if days <= 0:
        return _("row_today", time=_clock(when))
    if days == 1:
        return _("row_tomorrow", time=_clock(when))
    return _("row_day", date=format_date(rounded.date(), "%A %d %B"), time=_clock(when))


# ------------------------------------------------------------
# Reports
# ------------------------------------------------------------

def _wave_parts(height, direction, period, up_to=False):
    if height is None:
        return []
    return [
        _("piece_waves_up_to" if up_to else "piece_waves", height=height_text(height)),
        sea_state(height),
        _("piece_from", direction=compass(direction)) if direction is not None else None,
        (_("piece_period_up_to" if up_to else "piece_period", value=number(period))
         if period is not None else None),
    ]


def tide_sentence(forecast, now_utc=None):
    """'The tide is rising: high tide at about 21:40, low tide tomorrow at
    about 03:10.' or "" without tide data."""
    now = marine_api.location_now(forecast, now_utc)
    tides = marine_tides.find_tides(forecast.get("sea_level"))
    direction = marine_tides.trend(tides, now)
    if direction is None:
        return ""
    ahead = [t for t in (marine_tides.next_tide(tides, now, "high"),
                         marine_tides.next_tide(tides, now, "low")) if t]
    ahead.sort(key=lambda t: t["time"])
    pieces = [_("tide_high_at" if t["kind"] == "high" else "tide_low_at",
                when=_when(t["time"], now)) for t in ahead]
    return _("tide_rising" if direction == "rising" else "tide_falling",
             tides=", ".join(pieces))


def current_report(location, forecast, now_utc=None):
    """The full answer for "Speak the sea conditions"."""
    if not forecast.get("has_data"):
        return _("no_sea_data", place=location["name"])
    cur = forecast["current"]
    sentences = [_sentence(_wave_parts(cur.get("wave_height"), cur.get("wave_direction"),
                                       cur.get("wave_period")))]
    if cur.get("swell_height") is not None:
        sentences.append(_("piece_swell", height=height_text(cur["swell_height"])))
    if cur.get("sea_temperature") is not None:
        sentences.append(_("piece_sea_temp", value=number(cur["sea_temperature"])))
    sentences.append(tide_sentence(forecast, now_utc))
    text = " ".join(s for s in sentences if s)
    return f"{location['name']}: {text}" if text else _("no_sea_data", place=location["name"])


def briefing_sentence(location, forecast, now_utc=None):
    """One sentence for the Morning Briefing, or "" without data."""
    if not forecast.get("has_data"):
        return ""
    cur = forecast["current"]
    parts = []
    if cur.get("wave_height") is not None:
        parts += [_("piece_waves", height=height_text(cur["wave_height"])),
                  sea_state(cur["wave_height"])]
    now = marine_api.location_now(forecast, now_utc)
    high = marine_tides.next_tide(marine_tides.find_tides(forecast.get("sea_level")), now, "high")
    if high:
        parts.append(_("tide_next_high", when=_when(high["time"], now)))
    if not parts:
        return ""
    return _("briefing", place=location["name"], text=", ".join(parts))


def alert_text(location, height):
    return _("alert", place=location["name"], height=height_text(height), state=sea_state(height))


def alert_height_choice(metres):
    """'2.5 metres, rough' or '1.25 metres, moderate' for the alert height list
    (exact, where height_text() would round 1.25 to 1.2)."""
    decimals = next((d for d in (0, 1) if abs(round_half_up(metres, d) - metres) < 1e-9), 2)
    key = "unit_metre" if metres == 1 else "unit_metres"
    return f"{_(key, value=number(metres, decimals))}, {sea_state(metres)}"


# ------------------------------------------------------------
# Forecast rows
# ------------------------------------------------------------

def day_rows(forecast, now_utc=None):
    """One sentence per day from today on, with that day's tides."""
    now = marine_api.location_now(forecast, now_utc)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    tides = marine_tides.find_tides(forecast.get("sea_level"))
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
        parts = _wave_parts(day.get("wave_max"), day.get("direction"), day.get("period_max"),
                            up_to=True)
        if day.get("swell_max") is not None:
            parts.append(_("piece_swell_up_to", height=height_text(day["swell_max"])))
        text = ", ".join(p for p in parts if p)
        day_tides = [t for t in tides
                     if marine_tides.round_time(t["time"]).strftime("%Y-%m-%d") == date_str]
        if day_tides:
            items = ", ".join(_("tide_item_high" if t["kind"] == "high" else "tide_item_low",
                                time=_clock(t["time"])) for t in day_tides)
            tide_text = _("day_tides", tides=items)
            text = f"{text}; {tide_text}" if text else tide_text
        rows.append(f"{label}: {text}." if text else f"{label}: {_('day_no_data')}")
    return rows


def tide_rows(forecast, now_utc=None):
    """One sentence per coming tide, e.g. 'High tide today at about 21:40,
    0.9 metres above mean sea level.'"""
    now = marine_api.location_now(forecast, now_utc)
    rows = []
    for tide in marine_tides.upcoming(marine_tides.find_tides(forecast.get("sea_level")), now):
        rows.append(_("tide_row_high" if tide["kind"] == "high" else "tide_row_low",
                      when=_row_when(tide["time"], now), level=level_text(tide["level"])))
    return rows


def time_text(timestamp, now=None):
    """Local clock time of `timestamp`, with the date when it is not today."""
    when = datetime.datetime.fromtimestamp(timestamp)
    today = datetime.datetime.fromtimestamp(time.time() if now is None else now).date()
    clock = when.strftime("%H:%M")
    if when.date() == today:
        return clock
    return f"{format_date(when.date(), '%d %B')} {clock}"
