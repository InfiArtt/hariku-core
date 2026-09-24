# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for the Earthquakes & Tsunami extension, in the
user's language. BMKG's own words (the location, the Potensi statement, the
felt report) are passed through as BMKG wrote them, in Indonesian, even in the
English interface. Numbers use the language's decimal separator.
"""

import datetime
import os
import time

from core.i18n import format_date, get_translator

import earthquake_api as api

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("earthquake", os.path.join(EXT_DIR, "locales"))

_ERROR_KEYS = {"offline": "err_offline", "service": "err_service",
               "bad_response": "err_bad_response"}


def error_text(kind):
    return _(_ERROR_KEYS.get(kind, "err_bad_response"))


# ------------------------------------------------------------
# Numbers, distances and directions
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


def magnitude_value(magnitude):
    """One decimal, or two when the source gave two (USGS sometimes does)."""
    decimals = 2 if f"{magnitude:.2f}"[-1] != "0" else 1
    return number(magnitude, decimals)


def km_text(km, tens=True):
    """0.1 precision under 10 km, whole kilometres under 100, tens above
    (whole kilometres for depths: tens=False)."""
    if km < 10:
        value = round(km, 1)
        decimals = 0 if value == int(value) else 1
    elif km < 100 or not tens:
        value, decimals = round(km), 0
    else:
        value, decimals = int(round(km / 10.0) * 10), 0
    text = number(value, decimals)
    return _("unit_km_one", value=text) if decimals == 0 and value == 1 else _("unit_km", value=text)


def compass(degrees):
    names = [_("dir_n"), _("dir_ne"), _("dir_e"), _("dir_se"),
             _("dir_s"), _("dir_sw"), _("dir_w"), _("dir_nw")]
    return names[api.compass_index(degrees)]


def _end(text):
    text = (text or "").strip()
    return text if not text or text[-1] in ".!?" else text + "."


def _cap(text):
    return text[:1].upper() + text[1:] if text else text


# ------------------------------------------------------------
# Pieces of a report
# ------------------------------------------------------------

def magnitude_piece(quake):
    return _("piece_magnitude", value=magnitude_value(quake["magnitude"]))


def depth_piece(quake):
    if quake.get("depth_km") is None:
        return None
    return _("piece_depth", value=km_text(quake["depth_km"], tens=False))


def quake_pieces(quake):
    """ "magnitude 4.7, depth 9 kilometres, <BMKG's location text>" """
    parts = [magnitude_piece(quake), depth_piece(quake), quake.get("region")]
    return ", ".join(p for p in parts if p)


def distance_phrase(quake, location):
    """ "350 kilometres east of Bandung", or None without a location."""
    found = api.distance_from(location, quake)
    if found is None:
        return None
    km, bearing = found
    return _("distance_phrase", distance=km_text(km), direction=compass(bearing),
             place=location["name"])


def ago_text(age):
    minutes = int(age // 60)
    if minutes < 1:
        return _("ago_now")
    if minutes < 60:
        return _("ago_minute") if minutes == 1 else _("ago_minutes", count=minutes)
    hours = minutes // 60
    return _("ago_hour") if hours == 1 else _("ago_hours", count=hours)


def clock_text(quake):
    """BMKG: its own clock and zone ("09:02 WIB"). USGS: this computer's time."""
    if quake["source"] == "bmkg":
        if quake.get("clock"):
            return f"{quake['clock']} {quake.get('zone') or ''}".strip()
        if quake.get("time") is not None:
            return f"{api.zone_clock(quake['time'], api.DEFAULT_ZONE)} {api.DEFAULT_ZONE}"
        return ""
    if quake.get("time") is None:
        return ""
    return datetime.datetime.fromtimestamp(quake["time"]).strftime("%H:%M")


def date_text(quake, now):
    if quake.get("time") is None:
        return quake.get("date_text", "")
    if quake["source"] == "bmkg":
        day = api.zone_date(quake["time"], quake.get("zone") or api.DEFAULT_ZONE)
        this_year = api.zone_date(now, quake.get("zone") or api.DEFAULT_ZONE).year
    else:
        day = datetime.datetime.fromtimestamp(quake["time"]).date()
        this_year = datetime.datetime.fromtimestamp(now).year
    return format_date(day, "%d %B" if day.year == this_year else "%d %B %Y")


def when_text(quake, now):
    """ "09:02 WIB, 12 minutes ago" within a day, else "22 September, 06:48 WIB"."""
    clock = clock_text(quake)
    when = quake.get("time")
    if when is not None and 0 <= now - when < 86400:
        return _("when_recent", clock=clock, ago=ago_text(now - when))
    return _("when_dated", date=date_text(quake, now), clock=clock)


def _common_sentences(quake, location, now):
    parts = [_cap(_end(distance_phrase(quake, location) or "")),
             _("time_sentence", when=when_text(quake, now))]
    if quake.get("felt"):
        parts.append(_("felt_sentence", felt=_end(quake["felt"])))
    return [p for p in parts if p]


def _bmkg_says(quake):
    return _("bmkg_says", text=_end(quake["potential"])) if quake.get("potential") else ""


# ------------------------------------------------------------
# Reports and alerts
# ------------------------------------------------------------

def latest_report(quake, location, now, disclaimer=False):
    """The answer for "Latest earthquake": BMKG's statement spoken verbatim."""
    parts = []
    if api.is_tsunami_potential(quake.get("potential")):
        parts.append(_("head_tsunami"))
    parts.append(_end(_("sentence_head", head=_("head_latest"), text=quake_pieces(quake))))
    parts += _common_sentences(quake, location, now)
    parts.append(_bmkg_says(quake))
    if disclaimer:
        parts.append(_("disclaimer"))
    return " ".join(p for p in parts if p)


def alert_text(reason, quake, location, now):
    """A background alert: "tsunami", "nearby" or "felt" (all from BMKG)."""
    if reason == "tsunami":
        parts = [_("head_tsunami"), _bmkg_says(quake),
                 _end(_("sentence_head", head=_("head_quake"), text=quake_pieces(quake)))]
        parts += _common_sentences(quake, location, now)
    else:
        head = _("head_nearby") if reason == "nearby" else _("head_felt")
        parts = [_end(_("sentence_head", head=head, text=quake_pieces(quake)))]
        parts += _common_sentences(quake, location, now)
        parts.append(_bmkg_says(quake))
    return " ".join(p for p in parts if p)


def world_alert_text(quakes, location, now):
    """Worldwide alerts from USGS, one after the other."""
    parts = []
    for quake in quakes:
        parts.append(_end(_("sentence_head", head=_("head_world"), text=quake_pieces(quake))))
        parts += _common_sentences(quake, location, now)
        if quake.get("tsunami_flag"):
            parts.append(_("usgs_tsunami_flag"))
    return " ".join(parts)


def row_text(quake, location, now):
    """One sentence per quake for the recent list."""
    pieces = [_cap(magnitude_piece(quake)), quake.get("region"), depth_piece(quake),
              when_text(quake, now), distance_phrase(quake, location)]
    text = _end(", ".join(p for p in pieces if p))
    if quake["source"] == "bmkg" and api.is_tsunami_potential(quake.get("potential")):
        text = _("row_tsunami", text=text)
    if quake.get("felt"):
        text += " " + _("row_felt", felt=_end(quake["felt"]))
    if quake["source"] == "usgs":
        text += " " + _("row_source_usgs")
    return text


def details_lines(quake, location, now):
    """Everything known about one quake, a line per fact."""
    lines = []
    bmkg = quake["source"] == "bmkg"
    if bmkg and api.is_tsunami_potential(quake.get("potential")):
        lines.append(_("head_tsunami"))
    lines.append(_("detail_magnitude", value=magnitude_value(quake["magnitude"])))
    if bmkg and quake.get("date_text") and quake.get("time_text"):
        when = f"{quake['date_text']}, {quake['time_text']}"
        if quake.get("time") is not None and 0 <= now - quake["time"] < 86400:
            when = f"{when} ({ago_text(now - quake['time'])})"
    else:
        when = when_text(quake, now)
    lines.append(_("detail_time", value=when))
    if quake.get("region"):
        lines.append(_("detail_region", value=quake["region"]))
    if bmkg and quake.get("lat_text") and quake.get("lon_text"):
        lines.append(_("detail_coordinates", value=f"{quake['lat_text']}, {quake['lon_text']}"))
    elif quake.get("lat") is not None:
        lines.append(_("detail_coordinates",
                       value=f"{number(quake['lat'], 2)}; {number(quake['lon'], 2)}"))
    if bmkg and quake.get("depth_text"):
        lines.append(_("detail_depth", value=quake["depth_text"]))
    elif quake.get("depth_km") is not None:
        lines.append(_("detail_depth", value=km_text(quake["depth_km"], tens=False)))
    distance = distance_phrase(quake, location)
    if distance:
        lines.append(_("detail_distance", value=distance))
    if quake.get("felt"):
        lines.append(_("detail_felt", value=quake["felt"]))
    if quake.get("potential"):
        lines.append(_("detail_potential", value=quake["potential"]))
    if quake.get("tsunami_flag"):
        lines.append(_("usgs_tsunami_flag"))
    lines.append(_("detail_source_bmkg") if bmkg else _("detail_source_usgs"))
    return lines


def details_speech(quake, location, now):
    return " ".join(_end(line) for line in details_lines(quake, location, now))


def briefing_sentence(quake, location, now):
    """One sentence (two with tsunami potential) for the Morning Briefing."""
    parts = [magnitude_piece(quake), distance_phrase(quake, location), when_text(quake, now)]
    text = _("briefing_quake", text=", ".join(p for p in parts if p))
    if api.is_tsunami_potential(quake.get("potential")):
        text += " " + _("briefing_tsunami")
    return text


def list_count_text(count):
    if count == 0:
        return _("list_empty")
    return _("list_count_one") if count == 1 else _("list_count", count=count)


def time_text(timestamp, now=None):
    """Local clock time of `timestamp`, with the date when it is not today."""
    when = datetime.datetime.fromtimestamp(timestamp)
    today = datetime.datetime.fromtimestamp(time.time() if now is None else now).date()
    clock = when.strftime("%H:%M")
    if when.date() == today:
        return clock
    return f"{format_date(when.date(), '%d %B')} {clock}"


def location_text(location):
    """How the settings page shows its own place (a city search result)."""
    return api.place_label(location) if location else _("location_not_set")


def felt_note(location, extra):
    """Which names felt alerts look for, for the location in use."""
    names = api.region_names(location, extra)
    if not names:
        return _("felt_note_none")
    return _("felt_note", names=", ".join(names))
