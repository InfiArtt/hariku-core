# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for the Cockpit extension, in the user's language:
decoded METARs ("Wind from 200 degrees at 6 knots. Visibility 7 kilometres. A
few clouds at 1,400 feet."), TAF periods, the Briefing and evening lines, the
airport list and messages. Codes are spelled ("W I D D", or "Whiskey India
Delta Delta" in Captain mode) so a screen reader doesn't read them as words.
"""

import datetime
import os
import time

from core.i18n import format_date, get_translator

import cockpit_metar as metar

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("cockpit", os.path.join(EXT_DIR, "locales"))

OLD_REPORT_SECONDS = 2 * 3600      # say how old a report is from then on
MAX_ROW_CLOUDS = 2                 # cloud layers in a short line

_ERROR_KEYS = {"offline": "err_offline", "service": "err_service",
               "rate_limited": "err_rate_limited", "bad_response": "err_bad_response"}


# ------------------------------------------------------------
# Numbers, units, codes and times
# ------------------------------------------------------------

def _separator(key_text, default):
    return key_text if len(key_text) <= 1 else default


def number(value, decimals=0):
    """`value` with the language's thousands and decimal separators."""
    value = round(float(value), decimals)
    if value == 0:
        value = 0.0  # never "-0"
    text = f"{abs(value):,.{decimals}f}"
    thousands = _separator(_("number_thousands"), ",")
    decimal = _separator(_("number_decimal"), ".") or "."
    text = text.replace(",", "\0").replace(".", decimal).replace("\0", thousands)
    return _("minus", value=text) if value < 0 else text


def spell(code, nato=False):
    """"W I D D", or "Whiskey India Delta Delta" with `nato`."""
    chars = [c for c in str(code or "").upper() if c.isalnum()]
    return " ".join(metar.NATO.get(c, c) for c in chars) if nato else " ".join(chars)


def clock(when):
    return when.strftime("%H:%M")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _cap(text):
    return text[:1].upper() + text[1:] if text else text


def _sentence(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ""
    text = ", ".join(parts)
    return _cap(text) + ("" if text.endswith((".", "!", "?")) else ".")


def _join_and(words):
    words = [w for w in words if w]
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + _("and_word") + words[-1]


def names(airport):
    """(full, short) names of an airport dict ({"icao", "name"})."""
    return metar.airport_names(airport.get("name"), airport.get("icao", ""))


def error_text(kind):
    return _(_ERROR_KEYS.get(kind, "err_bad_response"))


def time_text(timestamp, now=None):
    """Local clock time of `timestamp`, with the date when it is not today."""
    when = datetime.datetime.fromtimestamp(timestamp)
    today = datetime.datetime.fromtimestamp(time.time() if now is None else now).date()
    if when.date() == today:
        return clock(when)
    return f"{format_date(when.date(), '%d %B')} {clock(when)}"


# ------------------------------------------------------------
# Pieces of a report
# ------------------------------------------------------------

def speed_text(value, unit):
    if unit == "MPS":
        return _("unit_mps", value=number(value))
    if unit == "KMH":
        return _("unit_kmh", value=number(value))
    return _("unit_kt_one" if value == 1 else "unit_kt", value=number(value))


def wind_text(cond):
    wind = cond.get("wind")
    if not wind:
        return None
    if wind["calm"]:
        return _("wind_calm")
    speed = speed_text(wind["speed"], wind["unit"])
    if wind["variable"] or wind["direction"] is None:
        text = _("wind_variable", speed=speed)
    else:
        text = _("wind", direction=wind["direction"], speed=speed)
    if wind["gust"]:
        text = _("wind_gust", wind=text, gust=speed_text(wind["gust"], wind["unit"]))
    if cond.get("wind_range"):
        low, high = cond["wind_range"]
        text = _("wind_range", wind=text, low=low, high=high)
    return text


def distance_text(vis):
    """A visibility group's distance: "800 metres", "7 kilometres", "1.5 statute miles"."""
    if vis.get("miles") is not None:
        miles = vis["miles"]
        decimals = 0 if miles == int(miles) else (1 if miles * 10 == int(miles * 10) else 2)
        return _("unit_sm_one" if miles == 1 else "unit_sm", value=number(miles, decimals))
    metres = vis["metres"]
    if metres >= 5000:
        km = metres / 1000.0
        decimals = 0 if km == int(km) else 1
        return _("unit_km_one" if km == 1 else "unit_km", value=number(km, decimals))
    return _("unit_m", value=number(metres))


def _direction(code):
    return _("dir_" + code) if code else ""


def visibility_text(cond, short=False):
    vis = cond.get("visibility")
    if cond.get("cavok"):
        return _("cavok_short") if short else _("cavok")
    if not vis:
        return None
    if vis["more"] and vis.get("miles") is None:
        text = _("vis_10km")
    elif vis["less"] and vis.get("miles") is None:
        text = _("vis_under_50m")
    else:
        distance = distance_text(vis)
        if vis["more"]:
            distance = _("more_than", value=distance)
        elif vis["less"]:
            distance = _("less_than", value=distance)
        text = _("vis", distance=distance)
        if vis.get("direction"):
            text = _("vis_toward", text=text, direction=_direction(vis["direction"]))
    low = cond.get("min_visibility")
    if low and not short:
        text = _("vis_min", text=text, distance=distance_text(low),
                 direction=_direction(low.get("direction")))
    return text


def _intensify(text, intensity):
    if intensity == "-":
        return _("wx_light", what=text)
    if intensity == "+":
        return _("wx_heavy", what=text)
    return text


def weather_text(w):
    """One present weather group: "light rain showers", "thunderstorm in the
    vicinity", "recent rain"."""
    phenomena = w["phenomena"]
    descriptor = w["descriptor"]
    if "FC" in phenomena and w["intensity"] == "+":
        text = _("wx_tornado")
    else:
        what = _join_and([_("wx_" + p) for p in phenomena])
        if descriptor == "TS":
            text = (_("wx_ts_with", what=_intensify(what, w["intensity"])) if what
                    else _intensify(_("wx_ts"), w["intensity"]))
        elif descriptor == "SH":
            text = _intensify(_("wx_showers", what=what) if what else _("wx_showers_alone"),
                              w["intensity"])
        elif descriptor:
            text = _intensify(_("wx_" + descriptor.lower(), what=what), w["intensity"])
        else:
            text = _intensify(what, w["intensity"])
    if w["vicinity"]:
        text = _("wx_vicinity", what=text)
    if w.get("recent"):
        text = _("wx_recent", what=text)
    return text


def height_text(feet):
    if feet is None:
        return _("height_unknown")
    return _("unit_ft", value=number(feet))


def cloud_text(layer):
    if layer["cover"] == "VV":
        return _("cloud_VV", height=height_text(layer["height"]))
    height = height_text(layer["height"])
    if layer.get("type"):
        return _(f"cloud_{layer['cover']}_typed", type=_("type_" + layer["type"]), height=height)
    return _(f"cloud_{layer['cover']}", height=height)


def cloud_pieces(cond, limit=None):
    layers = cond.get("clouds") or []
    pieces = [cloud_text(layer) for layer in layers[:limit]]
    if not pieces and cond.get("sky"):
        pieces.append(_("sky_" + cond["sky"]))
    return pieces


def conditions_pieces(cond, short=False):
    """Wind, visibility, weather and clouds of a report or forecast period."""
    pieces = [wind_text(cond), visibility_text(cond, short)]
    pieces += [weather_text(w) for w in cond.get("weather") or []]
    if cond.get("nsw"):
        pieces.append(_("nsw"))
    if not cond.get("cavok"):
        pieces += cloud_pieces(cond, MAX_ROW_CLOUDS if short else None)
    return [p for p in pieces if p]


def temperature_value(value):
    return number(value)


def category_sentence(category):
    return _("category", text=_("cat_" + category)) if category in metar.CATEGORIES else ""


# ------------------------------------------------------------
# A whole METAR
# ------------------------------------------------------------

def _when_text(obs_time, now):
    observed = datetime.datetime.fromtimestamp(obs_time)
    zulu = clock(datetime.datetime.fromtimestamp(obs_time, datetime.timezone.utc))
    today = datetime.datetime.fromtimestamp(now).date()
    if observed.date() == today:
        return _("when_today", local=clock(observed), zulu=zulu)
    return _("when_day", date=format_date(observed.date(), "%d %B"), local=clock(observed),
             zulu=zulu)


def _age_sentence(obs_time, now):
    age = now - obs_time
    if age < OLD_REPORT_SECONDS:
        return ""
    return _("report_old", hours=int(age // 3600))


def header_sentence(airport, report, parsed, captain=False, now=None):
    now = time.time() if now is None else now
    full, _short = names(airport)
    nearest = _("nearest", city=airport["city"]) if airport.get("auto") and airport.get("city") else ""
    parts = [full + nearest, spell(airport["icao"], captain)]
    if parsed.get("auto"):
        parts.append(_("auto_station"))
    parts.append(_when_text(report["obs_time"], now))
    return ", ".join(parts) + "."


def _rvr_value(value, prefix, feet):
    text = _("unit_ft" if feet else "unit_m", value=number(value))
    if prefix == "P":
        return _("more_than", value=text)
    if prefix == "M":
        return _("less_than", value=text)
    return text


def runway_text(runway):
    digits, side = runway[:2], runway[2:]
    return f"{int(digits)} {_('runway_' + side)}" if side else str(int(digits))


def rvr_sentence(rvr):
    low = _rvr_value(rvr["low"], rvr["low_prefix"], rvr["feet"])
    if rvr["high"] is not None:
        value = _("range_values", low=low,
                  high=_rvr_value(rvr["high"], rvr["high_prefix"], rvr["feet"]))
    else:
        value = low
    trend = _("rvr_trend_" + rvr["trend"]) if rvr.get("trend") else ""
    return _("rvr", runway=runway_text(rvr["runway"]), value=value,
             trend=(", " + trend) if trend else "")


def _trend_times(trend):
    if trend["from"] and trend["until"]:
        return _("trend_from_until", start="%02d:%02d" % trend["from"],
                 end="%02d:%02d" % trend["until"])
    if trend["from"]:
        return _("trend_from", start="%02d:%02d" % trend["from"])
    if trend["until"]:
        return _("trend_until", end="%02d:%02d" % trend["until"])
    if trend["at"]:
        return _("trend_at", at="%02d:%02d" % trend["at"])
    return ""


def trend_sentence(trend):
    if trend["kind"] == "NOSIG":
        return _("trend_NOSIG")
    what = ", ".join(conditions_pieces(trend["conditions"]))
    if not what:
        return ""
    return _("trend_" + trend["kind"], times=_trend_times(trend), what=what)


def metar_lines(airport, report, captain=False, raw=False, now=None):
    """The decoded METAR as sentences: the station and time, wind, visibility,
    weather, clouds, temperature, QNH, the rest, the trend and the flight
    category; then the raw report when asked for."""
    now = time.time() if now is None else now
    parsed = metar.parse_metar(report["raw"])
    lines = [header_sentence(airport, report, parsed, captain, now)]
    if parsed["nil"]:
        lines.append(_("report_nil"))
    lines.append(_age_sentence(report["obs_time"], now))
    lines.append(_sentence([wind_text(parsed)]))
    lines.append(_sentence([visibility_text(parsed)]))
    lines.append(_sentence([weather_text(w) for w in parsed["weather"]]))
    if not parsed["cavok"]:
        lines.append(_sentence(cloud_pieces(parsed)))
    if parsed["temperature"] is not None:
        if parsed["dewpoint"] is not None:
            lines.append(_("temperature", temp=temperature_value(parsed["temperature"]),
                           dew=temperature_value(parsed["dewpoint"])))
        else:
            lines.append(_("temperature_only", temp=temperature_value(parsed["temperature"])))
    if parsed["altimeter"] is not None:
        lines.append(_("qnh_inches", value=parsed["qnh"],
                       inches=number(parsed["altimeter"], 2)))
    elif parsed["qnh"] is not None:
        lines.append(_("qnh", value=parsed["qnh"]))
    lines += [rvr_sentence(r) for r in parsed["rvr"]]
    for runway in parsed["windshear"]:
        lines.append(_("windshear_all") if runway == "ALL"
                     else _("windshear", runway=runway_text(runway)))
    lines.append(_sentence([weather_text(w) for w in parsed["recent"]]))
    lines += [trend_sentence(t) for t in parsed["trends"]]
    lines.append(category_sentence(metar.report_category(parsed, report.get("category"))))
    if raw:
        lines.append(_("raw_report", raw=report["raw"]))
    return [line for line in lines if line]


def metar_speech(airport, report, captain=False, raw=False, now=None):
    return " ".join(metar_lines(airport, report, captain, raw, now))


def short_line(airport, report):
    """%airportweather% and the Captain's briefing: "Hang Nadim: wind from 200
    degrees at 6 knots, visibility 7 kilometres, a few clouds at 1,400 feet,
    30 degrees, QNH 1013" (no full stop)."""
    parsed = metar.parse_metar(report["raw"])
    pieces = conditions_pieces(parsed, short=True)
    if parsed["temperature"] is not None:
        pieces.append(_("short_temp", temp=temperature_value(parsed["temperature"])))
    if parsed["qnh"] is not None:
        pieces.append(_("short_qnh", value=parsed["qnh"]))
    _full, short = names(airport)
    return f"{short}: {', '.join(pieces)}" if pieces else ""


def sky_word(parsed):
    """"a few clouds", "overcast", "clear skies" or the weather, for short rows."""
    if parsed["weather"]:
        return weather_text(parsed["weather"][0])
    if parsed["cavok"] or parsed["sky"] in ("SKC", "CLR", "NSC", "NCD"):
        return _("sky_word_clear")
    covers = [c["cover"] for c in parsed["clouds"] if c["cover"] in metar.COVERS]
    if covers:
        worst = max(covers, key=metar.COVERS.index)
        return _("sky_word_" + worst)
    return None


def _short_wind(parsed):
    wind = parsed.get("wind")
    if not wind:
        return None
    if wind["calm"]:
        return _("wind_calm")
    return _("short_wind", speed=speed_text(wind["speed"], wind["unit"]))


def summary_pieces(report):
    """"a few clouds", "30 degrees", "wind 6 knots": the short weather of a row."""
    parsed = metar.parse_metar(report["raw"])
    pieces = [sky_word(parsed)]
    if parsed["temperature"] is not None:
        pieces.append(_("short_temp", temp=temperature_value(parsed["temperature"])))
    pieces.append(_short_wind(parsed))
    return [p for p in pieces if p], parsed


def briefing_captain(airport, report, now_utc=None):
    """"It's 00:15 Zulu. Hang Nadim: wind from 200 degrees at 6 knots, ... QNH 1013." """
    line = short_line(airport, report)
    if not line:
        return ""
    return _("briefing_captain", zulu=clock(now_utc or utc_now()), text=line)


def briefing_short(airport, report):
    """"Airport weather at Hang Nadim: a few clouds, 30 degrees, wind 6 knots." """
    pieces, _parsed = summary_pieces(report)
    if not pieces:
        return ""
    _full, short = names(airport)
    return _("briefing_short", name=short, text=", ".join(pieces))


def airport_row(airport, entry, is_default=False, loading=False, captain=False):
    """One row of the airport list: name, code, "default", and the weather."""
    full, _short = names(airport)
    nearest = _("nearest", city=airport["city"]) if airport.get("auto") and airport.get("city") else ""
    head = f"{full}{nearest}, {spell(airport['icao'], captain)}"
    if is_default:
        head += _("row_default")
    if entry is None:
        return _("row", head=head, text=_("row_loading") if loading else _("row_no_report"))
    pieces, parsed = summary_pieces(entry["report"])
    category = metar.report_category(parsed, entry["report"].get("category"))
    if category:
        pieces.append(spell(category))
    return _("row", head=head, text=", ".join(pieces) or _("row_no_report"))


# ------------------------------------------------------------
# TAF
# ------------------------------------------------------------

def _ordinal_suffix(day):
    if 10 <= day % 100 <= 20:
        return _("ord_th")
    return _({1: "ord_st", 2: "ord_nd", 3: "ord_rd"}.get(day % 10, "ord_th"))


def _day_suffix(when, first_day):
    if first_day is None or when.day == first_day:
        return ""
    return _("day_suffix", day=when.day, suffix=_ordinal_suffix(when.day))


def zulu_point(when, first_day):
    """"06:00 Zulu", or "06:00 Zulu on the 25th" on a later day."""
    return _("point", time=clock(when), day=_day_suffix(when, first_day))


def zulu_range(start, end, first_day):
    """"01:00 to 03:00 Zulu", "06:00 to 10:00 Zulu on the 25th", or "23:00
    Zulu to 01:00 Zulu on the 25th"."""
    start_day, end_day = _day_suffix(start, first_day), _day_suffix(end, first_day)
    if start.date() == end.date() or (not start_day and not end_day):
        return _("range", start=clock(start), end=clock(end)) + start_day
    return _("range_days", start=zulu_point(start, first_day), end=zulu_point(end, first_day))


def _reference(taf):
    return datetime.datetime.fromtimestamp(taf["valid_from"], datetime.timezone.utc)


def _group_times(group, reference):
    start = metar.resolve_time(*group["from"], reference) if group.get("from") else None
    end = metar.resolve_time(group["to"][0], group["to"][1], 0, reference) \
        if group.get("to") else None
    return start, end


def taf_period_sentence(group, reference, first_day):
    """One forecast period, e.g. "From 01:00 to 03:00 Zulu, becoming wind from
    50 degrees at 12 knots." "" when it says nothing."""
    what = ", ".join(conditions_pieces(group["conditions"]))
    if not what:
        return ""
    start, end = _group_times(group, reference)
    if group["kind"] == "FM":
        if not start:
            return _cap(what) + "."
        return _("taf_FM", point=zulu_point(start, first_day), what=what)
    if not start or not end:
        return _cap(what) + "."
    span = zulu_range(start, end, first_day)
    if group["kind"] in ("PROB", "PROB_TEMPO"):
        return _("taf_" + group["kind"], range=span, percent=group["probability"], what=what)
    if group["kind"] in ("BECMG", "TEMPO"):
        return _("taf_" + group["kind"], range=span, what=what)
    return _("taf_BASE", range=span, what=what)


def taf_lines(taf, captain=False):
    """The decoded TAF: when it was issued and how long it is valid, then one
    sentence per period, and the highest and lowest temperatures."""
    parsed = metar.parse_taf(taf["raw"])
    reference = _reference(taf)
    valid_from = reference
    first_day = valid_from.day
    lines = []
    valid_to = datetime.datetime.fromtimestamp(taf["valid_to"], datetime.timezone.utc)
    issued = datetime.datetime.fromtimestamp(taf["issue_time"], datetime.timezone.utc)
    lines.append(_("taf_header", issued=zulu_point(issued, first_day),
                   range=zulu_range(valid_from, valid_to, first_day)))
    if parsed["nil"]:
        lines.append(_("taf_nil"))
    if parsed["cancelled"]:
        lines.append(_("taf_cancelled"))
    for group in parsed["groups"]:
        lines.append(taf_period_sentence(group, reference, first_day))
        for temp in group["temperatures"]:
            when = metar.resolve_time(temp["at"][0], temp["at"][1], 0, reference)
            if when:
                lines.append(_("taf_" + temp["kind"], temp=temperature_value(temp["value"]),
                               point=zulu_point(when, first_day)))
    return [line for line in lines if line]


def evening_line(airport, taf, now=None):
    """Tomorrow's TAF headline for the evening summary: the conditions forecast
    for 09:00 local time tomorrow, and a temporary or possible change with
    weather during tomorrow's daytime. "" when the TAF doesn't reach it."""
    now = now or datetime.datetime.now().astimezone()
    tomorrow = (now + datetime.timedelta(days=1)).date()
    local_zone = now.tzinfo or datetime.datetime.now().astimezone().tzinfo
    target = datetime.datetime.combine(tomorrow, datetime.time(9, 0), local_zone)
    target = target.astimezone(datetime.timezone.utc)
    parsed = metar.parse_taf(taf["raw"])
    reference = _reference(taf)
    cond = metar.conditions_at(parsed, target, reference)
    if cond is None:
        return ""
    what = ", ".join(conditions_pieces(cond))
    if not what:
        return ""
    _full, short = names(airport)
    lines = [_("evening_taf", name=short, what=what)]
    day_start = datetime.datetime.combine(tomorrow, datetime.time(6, 0), local_zone)
    day_end = datetime.datetime.combine(tomorrow, datetime.time(18, 0), local_zone)
    for group in parsed["groups"]:
        if group["kind"] not in ("TEMPO", "PROB", "PROB_TEMPO"):
            continue
        if not group["conditions"]["weather"]:
            continue
        start, end = _group_times(group, reference)
        if start and end and start < day_end and end > day_start:
            lines.append(taf_period_sentence(group, reference, reference.day))
            break
    return " ".join(line for line in lines if line)
