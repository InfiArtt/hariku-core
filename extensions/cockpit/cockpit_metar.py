# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
METAR and TAF decoding for the Cockpit extension, from the raw reports. The
JSON aviationweather.gov sends rounds visibility to statute miles (7000 metres
becomes 4.35), so the raw groups are read here instead: "7000" is 7 km, "9999"
10 km or more, CAVOK, present weather, cloud layers, trends and so on. Also the
flight category, the ICAO spelling alphabet and the distance maths for the
nearest airport. Pure data: no wx, no network and no translated text.
"""

import datetime
import math
import re

METRES_PER_STATUTE_MILE = 1609.344
HPA_PER_INHG = 33.8639
TEN_KM = 10000          # "9999" and CAVOK: 10 km or more

# The ICAO spelling alphabet (the same words in every language).
NATO = {
    "A": "Alfa", "B": "Bravo", "C": "Charlie", "D": "Delta", "E": "Echo", "F": "Foxtrot",
    "G": "Golf", "H": "Hotel", "I": "India", "J": "Juliett", "K": "Kilo", "L": "Lima",
    "M": "Mike", "N": "November", "O": "Oscar", "P": "Papa", "Q": "Quebec", "R": "Romeo",
    "S": "Sierra", "T": "Tango", "U": "Uniform", "V": "Victor", "W": "Whiskey",
    "X": "X-ray", "Y": "Yankee", "Z": "Zulu", "0": "Zero", "1": "One", "2": "Two",
    "3": "Three", "4": "Four", "5": "Five", "6": "Six", "7": "Seven", "8": "Eight",
    "9": "Niner",
}

DESCRIPTORS = ("MI", "PR", "BC", "DR", "BL", "SH", "TS", "FZ")
PHENOMENA = ("DZ", "RA", "SN", "SG", "IC", "PL", "GR", "GS", "UP", "BR", "FG", "FU", "VA",
             "DU", "SA", "HZ", "PY", "PO", "SQ", "FC", "SS", "DS")
PRECIPITATION = frozenset(("DZ", "RA", "SN", "SG", "IC", "PL", "GR", "GS", "UP"))
COVERS = ("FEW", "SCT", "BKN", "OVC")
CATEGORIES = ("VFR", "MVFR", "IFR", "LIFR")

ICAO_RE = re.compile(r"^[A-Z][A-Z0-9]{3}$")
_TIME_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})Z$")
_WIND_RE = re.compile(r"^(\d{3}|VRB|///)(\d{2,3}|//)(?:G(\d{2,3}))?(KT|MPS|KMH)$")
_WIND_RANGE_RE = re.compile(r"^(\d{3})V(\d{3})$")
_VIS_M_RE = re.compile(r"^(\d{4})(NDV|NE|NW|SE|SW|N|E|S|W)?$")
_VIS_SM_RE = re.compile(r"^([PM])?(\d{1,2})?(?: ?(\d)/(\d{1,2}))?SM$")
_RVR_RE = re.compile(r"^R(\d{2}[LCR]?)/([PM])?(\d{4})(?:V([PM])?(\d{4}))?(FT)?/?([UDN])?$")
_WX_RE = re.compile(r"^(RE)?([+-])?(VC)?(%s)?((?:%s)*)$"
                    % ("|".join(DESCRIPTORS), "|".join(PHENOMENA)))
_CLOUD_RE = re.compile(r"^(FEW|SCT|BKN|OVC)(\d{3}|///)(CB|TCU|///)?$")
_VV_RE = re.compile(r"^VV(\d{3}|///)$")
_TEMP_RE = re.compile(r"^(M?\d{2})/(M?\d{2})?$")
_QNH_RE = re.compile(r"^Q(\d{3,4})$")
_ALT_RE = re.compile(r"^A(\d{4})$")
_TREND_TIME_RE = re.compile(r"^(FM|TL|AT)(\d{2})(\d{2})$")
_PERIOD_RE = re.compile(r"^(\d{2})(\d{2})/(\d{2})(\d{2})$")
_FM_RE = re.compile(r"^FM(\d{2})(\d{2})(\d{2})$")
_TAF_TEMP_RE = re.compile(r"^T([XN])(M?\d{2})/(\d{2})(\d{2})Z$")
_PROB_RE = re.compile(r"^PROB(\d{2})$")
_RUNWAY_RE = re.compile(r"^R(?:WY)?(\d{2}[LCR]?)$")


# ------------------------------------------------------------
# Tokens and small values
# ------------------------------------------------------------

def tokens(raw):
    """The report's groups, with the "=" end mark gone and a split statute-mile
    visibility ("1 1/2SM") put back together."""
    parts = str(raw or "").replace("=", " ").upper().split()
    out = []
    for part in parts:
        if (out and re.match(r"^\d/\d{1,2}SM$", part) and re.match(r"^[PM]?\d{1,2}$", out[-1])):
            out[-1] = out[-1] + " " + part
        else:
            out.append(part)
    return out


def signed(text):
    """"M02" -> -2, "25" -> 25."""
    return -int(text[1:]) if text.startswith("M") else int(text)


def new_conditions():
    """The weather in one report or forecast period."""
    return {"wind": None, "wind_range": None, "visibility": None, "min_visibility": None,
            "cavok": False, "weather": [], "clouds": [], "sky": None, "nsw": False}


def parse_weather(token):
    """A present weather group ("-SHRA", "VCTS", "+TSRAGR", "RERA") as a dict,
    or None when `token` isn't one."""
    match = _WX_RE.match(token)
    if not match or not token:
        return None
    recent, intensity, vicinity, descriptor, rest = match.groups()
    phenomena = [rest[i:i + 2] for i in range(0, len(rest), 2)]
    if not phenomena and descriptor not in ("SH", "TS"):
        return None
    if recent and (intensity or vicinity):
        return None
    return {"intensity": intensity or "", "vicinity": bool(vicinity), "descriptor": descriptor,
            "phenomena": phenomena, "recent": bool(recent)}


def _visibility_sm(match):
    prefix, whole, num, den = match.groups()
    if whole is None and num is None:
        return None
    miles = float(whole or 0)
    if num is not None:
        if int(den) == 0:
            return None
        miles += int(num) / int(den)
    return {"metres": int(round(miles * METRES_PER_STATUTE_MILE)), "miles": miles,
            "direction": None, "more": prefix == "P", "less": prefix == "M"}


def parse_condition(token, cond):
    """Read `token` into `cond` if it is a wind, visibility, weather or cloud
    group. Returns whether it was one."""
    match = _WIND_RE.match(token)
    if match:
        direction, speed, gust, unit = match.groups()
        if speed == "//":
            return True     # wind not reported
        speed = int(speed)
        cond["wind"] = {"direction": int(direction) if direction.isdigit() else None,
                        "variable": direction == "VRB", "speed": speed,
                        "gust": int(gust) if gust else None, "unit": unit,
                        "calm": speed == 0 and not gust}
        return True
    match = _WIND_RANGE_RE.match(token)
    if match:
        cond["wind_range"] = (int(match.group(1)), int(match.group(2)))
        return True
    if token == "CAVOK":
        cond["cavok"] = True
        cond["visibility"] = {"metres": TEN_KM, "miles": None, "direction": None,
                              "more": True, "less": False}
        return True
    match = _VIS_M_RE.match(token)
    if match:
        metres, direction = int(match.group(1)), match.group(2)
        direction = None if direction == "NDV" else direction
        vis = {"metres": TEN_KM if metres == 9999 else metres, "miles": None,
               "direction": direction, "more": metres == 9999, "less": metres == 0}
        if cond["visibility"] is not None and direction:
            cond["min_visibility"] = vis     # "4000 1500NE": the lowest, and where
        else:
            cond["visibility"] = vis
        return True
    match = _VIS_SM_RE.match(token)
    if match:
        vis = _visibility_sm(match)
        if vis:
            cond["visibility"] = vis
            return True
        return False
    if token in ("SKC", "CLR", "NSC", "NCD"):
        cond["sky"] = token
        return True
    if token == "NSW":
        cond["nsw"] = True
        return True
    match = _CLOUD_RE.match(token)
    if match:
        cover, height, kind = match.groups()
        cond["clouds"].append({"cover": cover,
                               "height": None if height == "///" else int(height) * 100,
                               "type": kind if kind in ("CB", "TCU") else None})
        return True
    match = _VV_RE.match(token)
    if match:
        height = match.group(1)
        cond["clouds"].append({"cover": "VV",
                               "height": None if height == "///" else int(height) * 100,
                               "type": None})
        return True
    weather = parse_weather(token)
    if weather and not weather["recent"]:
        cond["weather"].append(weather)
        return True
    return False


# ------------------------------------------------------------
# METAR
# ------------------------------------------------------------

def parse_metar(raw):
    """A METAR (or SPECI) as a dict: station, day/hour/minute, the conditions
    (see new_conditions()), runway visual ranges, temperature and dew point,
    QNH in hectopascals, recent weather, wind shear, trends (NOSIG, BECMG,
    TEMPO) and the remarks as text. Groups it can't read are listed in
    "unparsed" and otherwise skipped."""
    report = new_conditions()
    report.update({"raw": " ".join(str(raw or "").split()), "station": None, "time": None,
                   "auto": False, "corrected": False, "nil": False, "rvr": [],
                   "temperature": None, "dewpoint": None, "qnh": None, "altimeter": None,
                   "recent": [], "windshear": [], "trends": [], "remarks": "", "unparsed": []})
    parts = tokens(raw)
    i = 0
    while i < len(parts) and parts[i] in ("METAR", "SPECI"):
        i += 1
    if i < len(parts) and parts[i] == "COR":
        report["corrected"] = True
        i += 1
    if i < len(parts) and ICAO_RE.match(parts[i]):
        report["station"] = parts[i]
        i += 1
    if i < len(parts):
        match = _TIME_RE.match(parts[i])
        if match:
            report["time"] = tuple(int(g) for g in match.groups())
            i += 1
    trend = None
    while i < len(parts):
        token = parts[i]
        i += 1
        if token == "RMK":
            report["remarks"] = " ".join(parts[i:])
            break
        if token in ("NOSIG", "BECMG", "TEMPO"):
            trend = {"kind": token, "from": None, "until": None, "at": None,
                     "conditions": new_conditions()}
            report["trends"].append(trend)
            continue
        if trend is not None:
            match = _TREND_TIME_RE.match(token)
            if match:
                trend[{"FM": "from", "TL": "until", "AT": "at"}[match.group(1)]] = \
                    (int(match.group(2)), int(match.group(3)))
            elif not parse_condition(token, trend["conditions"]):
                report["unparsed"].append(token)
            continue
        if token == "AUTO":
            report["auto"] = True
        elif token == "NIL":
            report["nil"] = True
        elif token == "COR":
            report["corrected"] = True
        elif parse_condition(token, report):
            pass
        elif _RVR_RE.match(token):
            report["rvr"].append(_rvr(_RVR_RE.match(token)))
        elif _TEMP_RE.match(token):
            match = _TEMP_RE.match(token)
            report["temperature"] = signed(match.group(1))
            report["dewpoint"] = signed(match.group(2)) if match.group(2) else None
        elif _QNH_RE.match(token):
            report["qnh"] = int(_QNH_RE.match(token).group(1))
        elif _ALT_RE.match(token):
            inches = int(_ALT_RE.match(token).group(1)) / 100.0
            report["altimeter"] = inches
            report["qnh"] = int(round(inches * HPA_PER_INHG))
        elif token == "WS":
            runways = []
            while i < len(parts) and (_RUNWAY_RE.match(parts[i]) or parts[i] in ("ALL", "RWY")):
                if parts[i] == "ALL":
                    runways.append("ALL")
                elif parts[i] != "RWY":
                    runways.append(_RUNWAY_RE.match(parts[i]).group(1))
                i += 1
            report["windshear"].extend(runways or ["ALL"])
        else:
            weather = parse_weather(token)
            if weather and weather["recent"]:
                report["recent"].append(weather)
            else:
                report["unparsed"].append(token)
    return report


def _rvr(match):
    runway, low_prefix, low, high_prefix, high, feet, trend = match.groups()
    return {"runway": runway, "low": int(low), "low_prefix": low_prefix or "",
            "high": int(high) if high else None, "high_prefix": high_prefix or "",
            "feet": bool(feet), "trend": trend}


# ------------------------------------------------------------
# TAF
# ------------------------------------------------------------

def parse_taf(raw):
    """A TAF as a dict: station, issue time, validity ((day, hour), (day,
    hour)) and "groups": the base forecast, then each FM, BECMG, TEMPO and
    PROB change in order, each with its times and conditions."""
    taf = {"raw": " ".join(str(raw or "").split()), "station": None, "issued": None,
           "valid": None, "amended": False, "corrected": False, "cancelled": False,
           "nil": False, "groups": [], "unparsed": []}
    parts = tokens(raw)
    i = 0
    while i < len(parts) and parts[i] in ("TAF", "AMD", "COR", "RTD"):
        taf["amended"] |= parts[i] == "AMD"
        taf["corrected"] |= parts[i] in ("COR", "RTD")
        i += 1
    if i < len(parts) and ICAO_RE.match(parts[i]):
        taf["station"] = parts[i]
        i += 1
    if i < len(parts) and _TIME_RE.match(parts[i]):
        taf["issued"] = tuple(int(g) for g in _TIME_RE.match(parts[i]).groups())
        i += 1
    if i < len(parts) and _PERIOD_RE.match(parts[i]):
        d1, h1, d2, h2 = (int(g) for g in _PERIOD_RE.match(parts[i]).groups())
        taf["valid"] = ((d1, h1), (d2, h2))
        i += 1
    start, end = taf["valid"] or (None, None)
    group = {"kind": "BASE", "probability": None, "from": start + (0,) if start else None,
             "to": end, "conditions": new_conditions(), "temperatures": []}
    taf["groups"].append(group)
    while i < len(parts):
        token = parts[i]
        i += 1
        if token == "RMK":
            break
        if token == "NIL":
            taf["nil"] = True
            continue
        if token == "CNL":
            taf["cancelled"] = True
            continue
        match = _FM_RE.match(token)
        if match:
            day, hour, minute = (int(g) for g in match.groups())
            group = {"kind": "FM", "probability": None, "from": (day, hour, minute), "to": None,
                     "conditions": new_conditions(), "temperatures": []}
            taf["groups"].append(group)
            continue
        prob = _PROB_RE.match(token)
        if token in ("BECMG", "TEMPO", "INTER") or prob:
            kind = "TEMPO" if token == "INTER" else token
            probability = None
            if prob:
                probability = int(prob.group(1))
                kind = "PROB"
                if i < len(parts) and parts[i] == "TEMPO":
                    kind = "PROB_TEMPO"
                    i += 1
            group = {"kind": kind, "probability": probability, "from": None, "to": None,
                     "conditions": new_conditions(), "temperatures": []}
            if i < len(parts) and _PERIOD_RE.match(parts[i]):
                d1, h1, d2, h2 = (int(g) for g in _PERIOD_RE.match(parts[i]).groups())
                group["from"], group["to"] = (d1, h1, 0), (d2, h2)
                i += 1
            taf["groups"].append(group)
            continue
        match = _TAF_TEMP_RE.match(token)
        if match:
            group["temperatures"].append({"kind": "max" if match.group(1) == "X" else "min",
                                          "value": signed(match.group(2)),
                                          "at": (int(match.group(3)), int(match.group(4)))})
            continue
        if not parse_condition(token, group["conditions"]):
            taf["unparsed"].append(token)
    return taf


def resolve_time(day, hour, minute, reference):
    """The UTC datetime for "day DD at HH:MM Zulu", in the month (before, of or
    after the aware UTC `reference`) that puts it nearest to it. Hour 24 is
    midnight at the end of the day. None when no month has that day."""
    reference = reference.astimezone(datetime.timezone.utc)
    extra = datetime.timedelta(days=1) if hour == 24 else datetime.timedelta()
    hour = 0 if hour == 24 else hour
    best = None
    for shift in (-1, 0, 1):
        month = reference.month + shift
        year = reference.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        try:
            when = datetime.datetime(year, month, day, hour, minute,
                                     tzinfo=datetime.timezone.utc) + extra
        except ValueError:
            continue
        if best is None or abs(when - reference) < abs(best - reference):
            best = when
    return best


def merge_conditions(base, change):
    """`base` with what a BECMG group changes (the parts it gives)."""
    merged = dict(base)
    merged["weather"] = list(base["weather"])
    merged["clouds"] = list(base["clouds"])
    if change["wind"]:
        merged["wind"], merged["wind_range"] = change["wind"], change["wind_range"]
    if change["visibility"]:
        merged["visibility"] = change["visibility"]
        merged["min_visibility"] = change["min_visibility"]
        merged["cavok"] = change["cavok"]
    if change["cavok"]:
        merged["weather"], merged["clouds"], merged["sky"] = [], [], None
    if change["weather"] or change["nsw"]:
        merged["weather"] = list(change["weather"])
        merged["nsw"] = change["nsw"]
    if change["clouds"] or change["sky"]:
        merged["clouds"], merged["sky"] = list(change["clouds"]), change["sky"]
    return merged


def conditions_at(taf, when, reference):
    """The prevailing forecast conditions at UTC datetime `when`: the base
    period with every FM and BECMG change up to then (TEMPO and PROB groups
    are left out). None outside the TAF's validity."""
    start, end = taf.get("valid") or (None, None)
    if not start:
        return None
    valid_from = resolve_time(start[0], start[1], 0, reference)
    valid_to = resolve_time(end[0], end[1], 0, reference)
    if not valid_from or not valid_to or not valid_from <= when < valid_to:
        return None
    current = None
    for group in taf["groups"]:
        if group["kind"] == "BASE":
            current = group["conditions"]
            continue
        if group["kind"] not in ("FM", "BECMG") or not group["from"]:
            continue
        begins = resolve_time(*group["from"], reference)
        if begins is None or begins > when:
            continue
        current = (group["conditions"] if group["kind"] == "FM"
                   else merge_conditions(current or new_conditions(), group["conditions"]))
    return current


# ------------------------------------------------------------
# Flight category
# ------------------------------------------------------------

def ceiling_ft(cond):
    """The lowest broken or overcast layer (or vertical visibility), in feet."""
    heights = [c["height"] for c in cond.get("clouds") or []
               if c["cover"] in ("BKN", "OVC", "VV") and c["height"] is not None]
    return min(heights) if heights else None


def flight_category(visibility_m, ceiling):
    """VFR, MVFR, IFR or LIFR as the US National Weather Service defines them
    (ceiling in feet, visibility in statute miles), or None with neither."""
    miles = None if visibility_m is None else visibility_m / METRES_PER_STATUTE_MILE
    if miles is None and ceiling is None:
        return None
    if (ceiling is not None and ceiling < 500) or (miles is not None and miles < 1):
        return "LIFR"
    if (ceiling is not None and ceiling < 1000) or (miles is not None and miles < 3):
        return "IFR"
    if (ceiling is not None and ceiling <= 3000) or (miles is not None and miles <= 5):
        return "MVFR"
    return "VFR"


def report_category(report, fallback=None):
    """The flight category of a parsed METAR: worked out from its raw groups,
    else `fallback` (the category aviationweather.gov sent)."""
    vis = (report.get("visibility") or {}).get("metres")
    category = flight_category(vis, ceiling_ft(report))
    if category is None and report.get("cavok"):
        category = "VFR"
    if category is None and fallback in CATEGORIES:
        category = fallback
    return category


# ------------------------------------------------------------
# Airports: codes, names and the nearest one
# ------------------------------------------------------------

def normalize_icao(text):
    """An ICAO location indicator ("widd " -> "WIDD"), or None."""
    code = "".join(str(text or "").split()).upper()
    return code if ICAO_RE.match(code) else None


_NAME_WORDS = {"INTL": "International", "ARPT": "Airport", "APT": "Airport",
               "RGNL": "Regional", "MUNI": "Municipal", "FLD": "Field", "AB": "Air Base"}


def airport_names(raw_name, icao=""):
    """(full, short) speakable names from aviationweather.gov's name:
    "Batam/Hang Nadim, RI, ID" -> ("Batam Hang Nadim", "Hang Nadim"). The
    code itself when there is no name."""
    name = str(raw_name or "").split(",")[0].strip()
    if not name:
        return icao, icao
    words = lambda text: " ".join(_NAME_WORDS.get(w.upper().strip("."), w)
                                  for w in text.replace("_", " ").split())
    if "/" in name:
        city, airport = (words(p) for p in name.split("/", 1))
        full = f"{city} {airport}".strip() if city.lower() not in airport.lower() else airport
        return full or icao, airport or full or icao
    full = words(name)
    short = full[:-len(" Airport")] if full.endswith(" Airport") else full
    return full, short or full


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def nearest_station(reports, latitude, longitude):
    """(report, km) of the station nearest to the point among `reports`
    (dicts with "icao", "latitude" and "longitude"), or (None, None)."""
    best, best_km = None, None
    for report in sorted(reports, key=lambda r: r.get("icao") or ""):
        lat, lon = report.get("latitude"), report.get("longitude")
        if lat is None or lon is None:
            continue
        km = distance_km(latitude, longitude, lat, lon)
        if best_km is None or km < best_km:
            best, best_km = report, km
    return best, best_km


def search_box(latitude, longitude, degrees):
    """"lat0,lon0,lat1,lon1" around a point rounded to 0.1 degree: what
    aviationweather.gov gets to find the nearest airport (never the point)."""
    lat, lon = round(float(latitude), 1), round(float(longitude), 1)
    lat0, lat1 = max(-90.0, lat - degrees), min(90.0, lat + degrees)
    lon0, lon1 = max(-180.0, lon - degrees), min(180.0, lon + degrees)
    return f"{lat0:.1f},{lon0:.1f},{lat1:.1f},{lon1:.1f}"
