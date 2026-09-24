# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Cockpit extension: METAR and TAF decoding (real reports from
# aviationweather.gov plus hand-made ones for every kind of group), flight
# categories, the spelling alphabet, local and Zulu times, the nearest
# airport, favourites, the cache and back-off, the Briefing and evening lines,
# Captain mode, %airportweather%, the generated sound theme and its install,
# and sentences in both languages. Nothing reaches the network: urlopen fails
# the test if anything tries.

import datetime
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "cockpit")
THEMES_EXT_DIR = os.path.join(ROOT, "extensions", "sound_themes")

# Verified with one request each on 24 September 2026 (the lead's samples).
METAR_JSON = [
    {"icaoId": "WIII", "receiptTime": "2026-09-24T03:35:18.697Z", "obsTime": 1790220600,
     "reportTime": "2026-09-24T03:30:00.000Z", "temp": 33, "dewp": 24, "wdir": 40, "wspd": 11,
     "visib": 4.35, "altim": 1012, "qcField": 16, "metarType": "METAR",
     "rawOb": "METAR WIII 240330Z 04011KT 360V060 7000 FEW020 33/24 Q1012 NOSIG",
     "lat": -6.125, "lon": 106.659, "elev": 9, "name": "Jakarta/Hatta Intl, JB, ID",
     "cover": "FEW", "clouds": [{"cover": "FEW", "base": 2000}], "fltCat": "MVFR"},
    {"icaoId": "WIDD", "receiptTime": "2026-09-24T03:35:18.726Z", "obsTime": 1790220600,
     "reportTime": "2026-09-24T03:30:00.000Z", "temp": 30, "dewp": 25, "wdir": 200, "wspd": 6,
     "visib": 4.35, "altim": 1013, "qcField": 16, "metarType": "METAR",
     "rawOb": "METAR WIDD 240330Z 20006KT 7000 FEW014 30/25 Q1013 NOSIG",
     "lat": 1.121, "lon": 104.119, "elev": 26, "name": "Batam/Hang Nadim, RI, ID",
     "cover": "FEW", "clouds": [{"cover": "FEW", "base": 1400}], "fltCat": "MVFR"},
]
# metar?bbox=0.1,103.0,2.1,105.0 around Batam (trimmed to what Cockpit reads).
BOX_JSON = [
    {"icaoId": "WIDD", "obsTime": 1790220600, "name": "Batam/Hang Nadim, RI, ID",
     "rawOb": "METAR WIDD 240330Z 20006KT 7000 FEW014 30/25 Q1013 NOSIG",
     "lat": 1.121, "lon": 104.119, "fltCat": "MVFR"},
    {"icaoId": "WIDN", "obsTime": 1790220600, "name": "Tanjung Pinang Arpt, RI, ID",
     "rawOb": "METAR WIDN 240330Z 20007KT 180V250 4000 VCTS -RA FEW015CB SCT017 27/26 Q1013 "
              "NOSIG RMK CB ON AREA", "lat": 0.923, "lon": 104.532, "fltCat": "IFR"},
    {"icaoId": "WSSS", "obsTime": 1790220600, "name": "Singapore/Changi Intl, 4, SG",
     "rawOb": "METAR WSSS 240330Z 18005KT 150V210 9999 FEW018 BKN150 31/25 Q1013 NOSIG",
     "lat": 1.368, "lon": 103.982, "fltCat": "VFR"},
    {"icaoId": "WSAP", "obsTime": 1790218800, "name": "Singapore/Pays, 4, SG",
     "rawOb": "METAR WSAP 240300Z 18006KT 8000 FEW018 BKN150 30/25 Q1013",
     "lat": 1.36, "lon": 103.909, "fltCat": "MVFR"},
]
TAF_JSON = [{
    "icaoId": "WIII", "dbPopTime": "2026-09-23T23:24:04.232Z",
    "bulletinTime": "2026-09-23T23:24:00.000Z", "issueTime": "2026-09-23T23:00:00.000Z",
    "validTimeFrom": 1790208000, "validTimeTo": 1790316000,
    "rawTAF": "TAF WIII 232300Z 2400/2506 13006KT 7000 SCT020 BECMG 2401/2403 05012KT "
              "BECMG 2415/2417 14005KT",
    "mostRecent": 1, "lat": -6.125, "lon": 106.659, "name": "Jakarta/Hatta Intl",
    "fcsts": [],
}]
STATION_JSON = [{"id": "WIDD", "icaoId": "WIDD", "iataId": "BTH", "site": "Batam/Hang Nadim",
                 "lat": 1.121, "lon": 104.119, "elev": 26, "state": "RI", "country": "ID"}]

BATAM = {"name": "Batam", "admin1": "Riau Islands", "country": "Indonesia",
         "latitude": 1.14937, "longitude": 104.02491, "timezone": "Asia/Jakarta"}
OBS = 1790220600                       # 24 September 2026 03:30 UTC
WIB = datetime.timezone(datetime.timedelta(hours=7))


def _utc(day, hour, minute=0):
    return datetime.datetime(2026, 9, day, hour, minute, tzinfo=datetime.timezone.utc).timestamp()


def _copy(data):
    return json.loads(json.dumps(data))


def _local(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M")


def _helpers():
    if EXT_DIR not in sys.path:
        sys.path.insert(0, EXT_DIR)
    import cockpit_api
    import cockpit_metar
    import cockpit_sounds
    import cockpit_text
    return cockpit_metar, cockpit_api, cockpit_text, cockpit_sounds


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import urllib.request

    def refuse(*args, **kwargs):
        raise AssertionError(f"real network access attempted: {args[:1]}")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture(scope="module")
def mt():
    return _helpers()[0]


@pytest.fixture(scope="module")
def api():
    return _helpers()[1]


@pytest.fixture(scope="module")
def text():
    return _helpers()[2]


@pytest.fixture(scope="module")
def snd():
    return _helpers()[3]


@pytest.fixture(scope="module")
def theme_files(snd):
    return snd.theme_files()


@pytest.fixture
def lang(monkeypatch, text):
    """Switch the UI language; the core month names are loaded too."""
    from core import i18n
    had_core, old_core = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("en")
    yield set_lang
    if had_core:
        i18n._language_cache["core"] = old_core
    else:
        i18n._language_cache.pop("core", None)


def report(api, raw, obs=OBS, name="Batam/Hang Nadim, RI, ID", icao=None, category=None):
    icao = icao or raw.split()[1] if raw.startswith(("METAR", "SPECI")) else (icao or raw.split()[0])
    return api.normalize_metar({"icaoId": icao, "rawOb": raw, "obsTime": obs, "name": name,
                                "lat": 1.121, "lon": 104.119, "fltCat": category})


def airport(icao="WIDD", name="Batam/Hang Nadim, RI, ID", **extra):
    return dict({"icao": icao, "name": name}, **extra)


NAMES = {"WIDD": "Batam/Hang Nadim, RI, ID", "WIII": "Jakarta/Hatta Intl, JB, ID"}


def decode(api, text, raw_ob, captain=False, obs=OBS, **kw):
    code = raw_ob.split()[1]
    name = NAMES.get(code, "Batam/Hang Nadim, RI, ID")
    return text.metar_lines(airport(code, name), report(api, raw_ob, obs, name=name), captain,
                            now=obs + 600, **kw)


# ------------------------------------------------------------
# Files: locales, manifest, the official list
# ------------------------------------------------------------

def test_locales_have_the_same_keys():
    keys = {}
    for code in ("en", "id"):
        with open(os.path.join(EXT_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            data = json.load(f)
        keys[code] = set(data["messages"])
        assert data["manifest"]["language_code"] == code
    assert keys["en"] == keys["id"]


def test_indonesian_is_casual():
    with open(os.path.join(EXT_DIR, "locales", "id.json"), encoding="utf-8") as f:
        messages = json.load(f)["messages"]
    assert not [k for k, v in messages.items() if "Anda" in v]
    assert "kamu" in messages["cockpit_greeting"] and "utamamu" in messages["action_pilot"]


def test_manifest():
    with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["id"] == "cockpit" and manifest["version"] == "1.0"
    assert manifest["minimum_core_version"] == "2.7" and manifest["main"] == "main.py"


def test_every_code_has_a_word(text, lang, mt):
    for lang_code in ("en", "id"):
        lang(lang_code)
        for key in ([f"wx_{p}" for p in mt.PHENOMENA] + [f"cat_{c}" for c in mt.CATEGORIES]
                    + [f"cloud_{c}" for c in mt.COVERS] + [f"sky_word_{c}" for c in mt.COVERS]
                    + ["dir_" + d for d in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")]):
            assert text._(key) != key, (lang_code, key)


# ------------------------------------------------------------
# METAR decoding
# ------------------------------------------------------------

def test_the_widd_sample_in_english(api, text, lang):
    lines = decode(api, text, METAR_JSON[1]["rawOb"])
    assert lines == [
        f"Batam Hang Nadim, W I D D, at {_local(OBS)} local time, 03:30 Zulu.",
        "Wind from 200 degrees at 6 knots.",
        "Visibility 7 kilometres.",
        "A few clouds at 1,400 feet.",
        "Temperature 30 degrees, dew point 25.",
        "QNH 1013 hectopascals.",
        "No significant change expected.",
        "Flight category: marginal V F R, visibility or cloud base somewhat reduced.",
    ]


def test_the_widd_sample_in_indonesian(api, text, lang):
    lang("id")
    lines = decode(api, text, METAR_JSON[1]["rawOb"], captain=True)
    assert lines == [
        f"Batam Hang Nadim, Whiskey India Delta Delta, pukul {_local(OBS)} waktu lokal, 03:30 Zulu.",
        "Angin dari 200 derajat, 6 knot.",
        "Jarak pandang 7 kilometer.",
        "Sedikit awan di ketinggian 1.400 kaki.",
        "Suhu 30 derajat, titik embun 25.",
        "QNH 1013 hektopascal.",
        "Tidak ada perubahan berarti yang diperkirakan.",
        "Kategori penerbangan: V F R marginal, jarak pandang atau dasar awan agak berkurang.",
    ]


def test_the_wiii_sample_with_a_variable_wind(api, text, lang):
    lines = decode(api, text, METAR_JSON[0]["rawOb"])
    assert lines[0].startswith("Jakarta Hatta International, W I I I, at ")
    assert lines[1] == "Wind from 40 degrees at 11 knots, varying between 360 and 60 degrees."
    lang("id")
    assert decode(api, text, METAR_JSON[0]["rawOb"])[1] == (
        "Angin dari 40 derajat, 11 knot, arah berubah-ubah antara 360 dan 60 derajat.")


@pytest.mark.parametrize("raw, expected", [
    ("METAR WIII 240000Z 00000KT 9999 FEW020 26/24 Q1010 NOSIG",
     ["Wind calm.", "Visibility 10 kilometres or more.", "Flight category: V F R, good "
      "visibility and a high cloud base."]),
    ("METAR WADD 240300Z VRB03KT 8000 SCT018 30/24 Q1009",
     ["Wind variable at 3 knots.", "Visibility 8 kilometres.", "Scattered clouds at 1,800 feet."]),
    ("METAR WSSS 240300Z 18015G25KT 150V210 9999 FEW018 31/25 Q1013",
     ["Wind from 180 degrees at 15 knots, gusting 25 knots, varying between 150 and 210 degrees."]),
    ("METAR WAAA 240300Z 27010KT CAVOK 32/22 Q1008 NOSIG",
     ["Ceiling and visibility OK (CAVOK): visibility 10 kilometres or more, no cloud below "
      "5,000 feet and no significant weather.", "Flight category: V F R, good visibility and "
      "a high cloud base."]),
    ("METAR WIDN 240330Z 20007KT 180V250 4000 VCTS -RA FEW015CB SCT017 27/26 Q1013 NOSIG "
     "RMK CB ON AREA",
     ["Visibility 4,000 metres.", "Thunderstorm in the vicinity, light rain.",
      "A few cumulonimbus clouds at 1,500 feet, scattered clouds at 1,700 feet.",
      "Flight category: I F R, low clouds or poor visibility, instruments needed."]),
    ("METAR WARR 240900Z 27015G28KT 3000 +TSRA BKN014CB OVC080 25/23 Q1006 TEMPO 2000 TSRA",
     ["Thunderstorm with heavy rain.",
      "Broken cumulonimbus clouds at 1,400 feet, overcast at 8,000 feet.",
      "Temporarily: visibility 2,000 metres, thunderstorm with rain."]),
    ("METAR WIHH 240600Z 32012KT 2500 +RA BKN010 OVC030 24/23 Q1008 BECMG FM0700 TL0800 5000 -RA",
     ["Heavy rain.", "Broken clouds at 1,000 feet, overcast at 3,000 feet.",
      "Becoming from 07:00 to 08:00 Zulu: visibility 5 kilometres, light rain."]),
    ("METAR WIBB 232300Z 00000KT 3000 BR FEW010 24/24 Q1010 NOSIG",
     ["Mist.", "Temperature 24 degrees, dew point 24."]),
    ("METAR WMKK 240000Z 00000KT 0800 FG OVC003 23/23 Q1010 BECMG 3000 BR",
     ["Visibility 800 metres.", "Fog.", "Overcast at 300 feet.",
      "Becoming: visibility 3,000 metres, mist.",
      "Flight category: low I F R, very low clouds or very poor visibility."]),
    ("METAR WIII 240500Z 25010KT 4000 1500NE -SHRA VCSH BCFG SCT012TCU 25/24 Q1008",
     ["Visibility 4,000 metres, down to 1,500 metres toward the northeast.",
      "Light rain showers, showers in the vicinity, patches of fog.",
      "Scattered towering cumulus clouds at 1,200 feet."]),
    ("METAR WIII 240500Z 25010KT 1500 R25L/1200N +TSRA BKN008CB 24/23 Q1007 RETSRA WS R25L",
     ["Runway 25 left visual range 1,200 metres, no change.",
      "Wind shear on runway 25 left.", "Recent thunderstorm with rain."]),
    ("METAR KSFO 240356Z 29012KT 1 1/2SM BR OVC004 17/16 A2992 RMK AO2",
     ["Visibility 1.5 statute miles.", "Overcast at 400 feet.",
      "QNH 1013 hectopascals, altimeter 29.92 inches of mercury.",
      "Flight category: low I F R, very low clouds or very poor visibility."]),
    ("METAR UUEE 240330Z 05005MPS 9999 -FZDZ OVC005 M02/M04 Q1021",
     ["Wind from 50 degrees at 5 metres per second.", "Light freezing drizzle.",
      "Temperature minus 2 degrees, dew point minus 4."]),
])
def test_decoding(api, text, lang, raw, expected):
    lines = decode(api, text, raw)
    for sentence in expected:
        assert sentence in lines, (sentence, lines)


def test_missing_and_odd_groups_do_not_break_it(api, text, lang, mt):
    lines = decode(api, text, "METAR WIDD 240300Z AUTO 20006KT //// ////// Q1012 =")
    assert lines[0].startswith("Batam Hang Nadim, W I D D, automatic station, at ")
    assert "Wind from 200 degrees at 6 knots." in lines
    assert not any(line.startswith(("Temperature", "Visibility", "Flight")) for line in lines)
    nil = decode(api, text, "METAR WIDD 240300Z NIL")
    assert "No report was sent (NIL)." in nil
    parsed = mt.parse_metar("METAR WIDD 240300Z 20006KT 9999 XYZ123 Q1012")
    assert parsed["unparsed"] == ["XYZ123"] and parsed["qnh"] == 1012
    assert mt.parse_metar("")["station"] is None


def test_the_json_category_is_the_fallback(api, text, lang):
    raw = "METAR WIDD 240300Z 20006KT 30/25 Q1013"
    lines = text.metar_lines(airport(), report(api, raw, category="VFR"), now=OBS + 600)
    assert lines[-1].startswith("Flight category: V F R")


def test_raw_report_on_request(api, text, lang):
    lines = decode(api, text, METAR_JSON[1]["rawOb"], raw=True)
    assert lines[-1] == "Raw report: METAR WIDD 240330Z 20006KT 7000 FEW014 30/25 Q1013 NOSIG"


def test_an_old_report_says_so(api, text, lang):
    lines = text.metar_lines(airport(), report(api, METAR_JSON[1]["rawOb"]), now=OBS + 3 * 3600 + 60)
    assert "This report is about 3 hours old." in lines
    yesterday = datetime.datetime.fromtimestamp(OBS - 86400)
    lines = text.metar_lines(airport(), report(api, METAR_JSON[1]["rawOb"], obs=OBS - 86400),
                             now=OBS)
    assert f"on {yesterday.day} September at {yesterday.strftime('%H:%M')} local time" in lines[0]


def test_weather_words_in_indonesian(mt, text, lang):
    lang("id")
    cases = {"-SHRA": "hujan sesaat ringan", "+TSRA": "badai petir disertai hujan lebat",
             "VCTS": "badai petir di sekitar bandara", "HZ": "udara kabur", "BR": "kabut tipis",
             "FZFG": "kabut beku", "-DZ": "gerimis ringan", "RERA": "baru saja terjadi hujan",
             "BCFG": "kabut di beberapa tempat", "+FC": "tornado atau puting beliung",
             "TSRAGR": "badai petir disertai hujan dan hujan es"}
    for code, words in cases.items():
        assert text.weather_text(mt.parse_weather(code)) == words, code
    lang("en")
    assert text.weather_text(mt.parse_weather("TSRAGR")) == "thunderstorm with rain and hail"
    assert text.weather_text(mt.parse_weather("-RADZ")) == "light rain and drizzle"


def test_parse_weather_rejects_other_groups(mt):
    for token in ("FZ", "WIDD", "RA-", "NOSIG", "Q1013", "RMK", "1400"):
        assert mt.parse_weather(token) is None, token


# ------------------------------------------------------------
# Flight categories, spelling, names
# ------------------------------------------------------------

@pytest.mark.parametrize("vis, ceiling, category", [
    (10000, None, "VFR"), (9999, 3100, "VFR"), (7000, None, "MVFR"), (10000, 3000, "MVFR"),
    (8000, 5000, "MVFR"), (4000, None, "IFR"), (10000, 900, "IFR"), (1500, 400, "LIFR"),
    (1000, None, "LIFR"), (None, 400, "LIFR"), (None, None, None),
])
def test_flight_category(mt, vis, ceiling, category):
    assert mt.flight_category(vis, ceiling) == category


def test_every_sample_matches_the_services_category(api, mt):
    for item in METAR_JSON + BOX_JSON:
        parsed = mt.parse_metar(item["rawOb"])
        assert mt.report_category(parsed) == item["fltCat"], item["rawOb"]


def test_spelling(text):
    assert text.spell("WIDD", nato=True) == "Whiskey India Delta Delta"
    assert text.spell("widd") == "W I D D"
    assert text.spell("K1V9", nato=True) == "Kilo One Victor Niner"
    assert text.spell("MVFR") == "M V F R"


def test_airport_names(mt):
    assert mt.airport_names("Batam/Hang Nadim, RI, ID") == ("Batam Hang Nadim", "Hang Nadim")
    assert mt.airport_names("Singapore/Changi Intl, 4, SG") == (
        "Singapore Changi International", "Changi International")
    assert mt.airport_names("Tanjung Pinang Arpt, RI, ID") == (
        "Tanjung Pinang Airport", "Tanjung Pinang")
    assert mt.airport_names("", "WXYZ") == ("WXYZ", "WXYZ")


def test_icao_codes(mt):
    assert mt.normalize_icao(" widd ") == "WIDD"
    for bad in ("WID", "WIDDD", "1IDD", "WI D", "", None, "WI-D"):
        assert mt.normalize_icao(bad) is None, bad


def test_local_and_zulu_time(api, text, lang):
    header = decode(api, text, METAR_JSON[1]["rawOb"])[0]
    assert header.endswith(f"at {_local(OBS)} local time, 03:30 Zulu.")
    now = datetime.datetime(2026, 9, 24, 7, 15, tzinfo=WIB)
    assert text.briefing_captain(airport(), report(api, METAR_JSON[1]["rawOb"]),
                                 now.astimezone(datetime.timezone.utc)).startswith(
        "It's 00:15 Zulu. Hang Nadim: ")


# ------------------------------------------------------------
# TAF
# ------------------------------------------------------------

def test_taf_periods_in_english(api, text, lang):
    taf = api.parse_tafs(_copy(TAF_JSON))["WIII"]
    assert text.taf_lines(taf) == [
        "Forecast (TAF), issued at 23:00 Zulu on the 23rd, valid from 00:00 Zulu to "
        "06:00 Zulu on the 25th.",
        "From 00:00 Zulu to 06:00 Zulu on the 25th: wind from 130 degrees at 6 knots, "
        "visibility 7 kilometres, scattered clouds at 2,000 feet.",
        "From 01:00 to 03:00 Zulu, becoming wind from 50 degrees at 12 knots.",
        "From 15:00 to 17:00 Zulu, becoming wind from 140 degrees at 5 knots.",
    ]


def test_taf_periods_in_indonesian(api, text, lang):
    lang("id")
    lines = text.taf_lines(api.parse_tafs(_copy(TAF_JSON))["WIII"])
    assert lines[2] == "Dari 01:00 sampai 03:00 Zulu, berubah menjadi angin dari 50 derajat, 12 knot."


STORM_TAF = {"icao": "WIDD", "name": "Batam/Hang Nadim, RI, ID",
             "raw": "TAF WIDD 241100Z 2412/2518 20008KT 9000 FEW018 TEMPO 2418/2422 4000 TSRA "
                    "FEW015CB PROB30 TEMPO 2506/2510 3000 +TSRA BKN012CB FM251200 18010G20KT "
                    "9999 SCT020 TX33/2506Z TN25/2422Z",
             "issue_time": _utc(24, 11), "valid_from": _utc(24, 12), "valid_to": _utc(25, 18)}


def test_taf_change_groups(api, text, lang):
    lines = text.taf_lines(api.normalize_taf(STORM_TAF))
    assert "From 18:00 to 22:00 Zulu, temporarily visibility 4,000 metres, thunderstorm with " \
           "rain, a few cumulonimbus clouds at 1,500 feet." in lines
    assert "From 06:00 to 10:00 Zulu on the 25th, a 30 percent chance of temporarily " \
           "visibility 3,000 metres, thunderstorm with heavy rain, broken cumulonimbus clouds " \
           "at 1,200 feet." in lines
    assert "From 12:00 Zulu on the 25th, wind from 180 degrees at 10 knots, gusting 20 knots, " \
           "visibility 10 kilometres or more, scattered clouds at 2,000 feet." in lines
    assert "Highest temperature 33 degrees at 06:00 Zulu on the 25th." in lines
    assert "Lowest temperature 25 degrees at 22:00 Zulu." in lines


def test_resolve_time_across_a_month(mt):
    ref = datetime.datetime(2026, 9, 30, 23, 0, tzinfo=datetime.timezone.utc)
    assert mt.resolve_time(1, 6, 0, ref) == datetime.datetime(2026, 10, 1, 6, tzinfo=datetime.timezone.utc)
    assert mt.resolve_time(30, 24, 0, ref) == datetime.datetime(2026, 10, 1, 0, tzinfo=datetime.timezone.utc)
    ref = datetime.datetime(2026, 10, 1, 1, 0, tzinfo=datetime.timezone.utc)
    assert mt.resolve_time(30, 18, 0, ref).month == 9


def test_evening_headline(api, text, lang):
    evening = datetime.datetime(2026, 9, 24, 20, 0, tzinfo=WIB)
    wiii = api.parse_tafs(_copy(TAF_JSON))["WIII"]
    assert text.evening_line(airport("WIII", "Jakarta/Hatta Intl"), wiii, evening) == (
        "Tomorrow morning at Hatta International: wind from 140 degrees at 5 knots, "
        "visibility 7 kilometres, scattered clouds at 2,000 feet.")
    storm = api.normalize_taf(STORM_TAF)
    line = text.evening_line(airport(), storm, evening)
    assert line.startswith("Tomorrow morning at Hang Nadim: wind from 200 degrees at 8 knots, "
                           "visibility 9 kilometres, a few clouds at 1,800 feet. From 06:00 to "
                           "10:00 Zulu on the 25th, a 30 percent chance of temporarily ")
    lang("id")
    assert text.evening_line(airport(), storm, evening).startswith("Besok pagi di Hang Nadim: ")
    # A TAF that ends before tomorrow morning says nothing.
    assert text.evening_line(airport(), storm, evening + datetime.timedelta(days=2)) == ""


# ------------------------------------------------------------
# Short lines, rows, the Briefing lines
# ------------------------------------------------------------

def test_short_line_and_briefing_lines(api, text, lang):
    widd = report(api, METAR_JSON[1]["rawOb"])
    assert text.short_line(airport(), widd) == ("Hang Nadim: wind from 200 degrees at 6 knots, "
                                                "visibility 7 kilometres, a few clouds at 1,400 "
                                                "feet, 30 degrees, QNH 1013")
    at = datetime.datetime(2026, 9, 24, 0, 15, tzinfo=datetime.timezone.utc)
    assert text.briefing_captain(airport(), widd, at) == (
        "It's 00:15 Zulu. Hang Nadim: wind from 200 degrees at 6 knots, visibility 7 "
        "kilometres, a few clouds at 1,400 feet, 30 degrees, QNH 1013.")
    assert text.briefing_short(airport(), widd) == (
        "Airport weather at Hang Nadim: a few clouds, 30 degrees, wind 6 knots.")
    lang("id")
    assert text.briefing_captain(airport(), widd, at) == (
        "Sekarang pukul 00:15 Zulu. Hang Nadim: angin dari 200 derajat, 6 knot, jarak pandang "
        "7 kilometer, sedikit awan di ketinggian 1.400 kaki, 30 derajat, QNH 1013.")
    assert text.briefing_short(airport(), widd) == (
        "Cuaca bandara Hang Nadim: sedikit awan, 30 derajat, angin 6 knot.")


def test_airport_rows(api, text, lang):
    entry = {"fetched_at": OBS, "report": report(api, METAR_JSON[1]["rawOb"])}
    assert text.airport_row(airport(), entry, is_default=True) == (
        "Batam Hang Nadim, W I D D, default: a few clouds, 30 degrees, wind 6 knots, M V F R")
    nearest = airport(auto=True, city="Batam")
    assert text.airport_row(nearest, None, loading=True, captain=True) == (
        "Batam Hang Nadim (nearest to Batam), Whiskey India Delta Delta: loading")
    assert text.airport_row(airport(), None).endswith(": no recent report")


# ------------------------------------------------------------
# Requests and parsing
# ------------------------------------------------------------

def test_request_urls_send_only_codes_or_a_box(api):
    for url, keys in ((api.build_metar_url(["WIDD", "WIII"]), {"ids", "format"}),
                      (api.build_taf_url(["WIDD"]), {"ids", "format"}),
                      (api.build_station_url("WIDD"), {"ids", "format"}),
                      (api.build_box_url("0.1,103.0,2.1,105.0"), {"bbox", "format"})):
        parts = urllib.parse.urlsplit(url)
        assert parts.scheme == "https" and parts.netloc == "aviationweather.gov"
        query = urllib.parse.parse_qs(parts.query)
        assert set(query) == keys and query["format"] == ["json"]
    assert "ids=WIDD%2CWIII" in api.build_metar_url(["WIDD", "WIII"])


def test_search_box_is_rounded(mt):
    assert mt.search_box(1.14937, 104.02491, 1.0) == "0.1,103.0,2.1,105.0"
    assert mt.search_box(-6.2088, 106.8456, 3.0) == "-9.2,103.8,-3.2,109.8"
    assert mt.search_box(89.5, 179.6, 1.0) == "88.5,178.6,90.0,180.0"


class _Response:
    def __init__(self, body):
        self._body = body

    def read(self, size=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_json_sends_user_agent_and_timeout(api, monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["agent"], seen["timeout"] = req.get_header("User-agent"), timeout
        return _Response(b"[]")

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    assert api.fetch_json("https://aviationweather.gov/api/data/metar?ids=WIDD&format=json") == []
    assert seen["agent"].startswith("HarikuV2/") and seen["agent"].endswith(
        "(Cockpit extension; +https://github.com/InfiArtt/hariku-core)")
    assert seen["timeout"] == api.TIMEOUT_SECONDS


@pytest.mark.parametrize("failure, kind", [
    (urllib.error.URLError("no route to host"), "offline"),
    (TimeoutError("timed out"), "offline"),
    (urllib.error.HTTPError("https://x", 429, "Too Many Requests", {}, None), "rate_limited"),
    (urllib.error.HTTPError("https://x", 500, "Server Error", {}, None), "service"),
])
def test_fetch_json_maps_failures(api, monkeypatch, failure, kind):
    def fake_urlopen(req, timeout=None):
        raise failure

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(api.AviationError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == kind


def test_fetch_json_no_content_and_bad_bodies(api, monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen", lambda req, timeout=None: _Response(b""))
    assert api.fetch_json("https://example.invalid/") == []          # HTTP 204
    monkeypatch.setattr(api.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b"<html>oops</html>"))
    with pytest.raises(api.AviationError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == "bad_response"
    with pytest.raises(api.AviationError):
        api.parse_metars({"error": "nope"})


def test_parse_metars_keeps_the_newest_per_station(api):
    older = dict(METAR_JSON[1], obsTime=OBS - 1800, rawOb="METAR WIDD 240300Z 20005KT 9999 "
                                                           "FEW014 29/25 Q1013")
    reports = api.parse_metars(_copy([older, METAR_JSON[1], METAR_JSON[0], {"icaoId": "BAD"}]))
    assert set(reports) == {"WIDD", "WIII"}
    assert reports["WIDD"]["obs_time"] == OBS and reports["WIDD"]["category"] == "MVFR"
    assert reports["WIDD"]["latitude"] == 1.121 and reports["WIDD"]["name"].startswith("Batam")


def test_parse_tafs_and_station(api):
    taf = api.parse_tafs(_copy(TAF_JSON))["WIII"]
    assert taf["issue_time"] == _utc(23, 23) and taf["valid_to"] == 1790316000
    assert api.parse_station(_copy(STATION_JSON), "WIDD")["name"] == "Batam/Hang Nadim"
    assert api.parse_station([], "WIDD") is None


def test_nearest_airport_to_batam(api, mt):
    reports = list(api.parse_metars(_copy(BOX_JSON)).values())
    nearest, km = mt.nearest_station(reports, BATAM["latitude"], BATAM["longitude"])
    assert nearest["icao"] == "WIDD" and 10 < km < 12
    nearest, _km = mt.nearest_station(reports, 1.35, 103.99)       # Changi
    assert nearest["icao"] == "WSSS"
    assert mt.nearest_station([], 0, 0) == (None, None)
    assert round(mt.distance_km(1.121, 104.119, -6.125, 106.659)) == 854


# ------------------------------------------------------------
# Settings, cache and back-off
# ------------------------------------------------------------

@pytest.mark.parametrize("raw", [None, "junk", {"favourites": "x"}, {"favourites": [1, {"icao": "bad"}]}])
def test_settings_survive_corrupt_data(api, raw):
    settings = api.normalize_settings(raw)
    assert settings["favourites"] == [] and settings["captain"] is False and settings["auto"] is None


def test_settings_keep_valid_values(api):
    raw = {"favourites": [{"icao": "widd", "name": "Batam/Hang Nadim, RI, ID"},
                          {"icao": "WIDD", "name": "dupe"}, {"icao": "WIII"}],
           "captain": True, "raw": True, "briefing": "yes",
           "auto": {"icao": "WIDD", "name": "x", "for": BATAM}}
    settings = api.normalize_settings(raw)
    assert [a["icao"] for a in settings["favourites"]] == ["WIDD", "WIII"]
    assert settings["captain"] and settings["raw"] and settings["briefing"] is False
    assert settings["auto"]["for"]["name"] == "Batam"


def test_cache_round_trip_and_corruption(api):
    cache = api.empty_cache()
    api.store_metars(cache, ["WIDD", "WXYZ"], api.parse_metars(_copy(METAR_JSON)), 1000.0)
    assert cache["metar"]["WIDD"]["fetched_at"] == 1000.0 and cache["no_metar"] == {"WXYZ": 1000.0}
    again = api.normalize_cache(_copy(cache))
    assert again["metar"]["WIDD"]["report"] == cache["metar"]["WIDD"]["report"]
    broken = api.normalize_cache({"metar": {"WIDD": {"fetched_at": "x"}, "WIII": 3}, "taf": [],
                                  "no_metar": {"??": 1}})
    assert broken == api.empty_cache()


def test_needs_fetch(api):
    cache = api.empty_cache()
    assert api.needs_fetch(cache, "metar", "WIDD", 600, now=5000)
    cache["metar"]["WIDD"] = {"fetched_at": 4500.0, "report": {}}
    assert not api.needs_fetch(cache, "metar", "WIDD", 600, now=5000)
    assert api.needs_fetch(cache, "metar", "WIDD", 600, now=5200)
    cache["no_metar"]["WIDD"] = 5100.0      # asked again: nothing new
    assert not api.needs_fetch(cache, "metar", "WIDD", 600, now=5200)
    assert api.needs_fetch(cache, "metar", "WIDD", 600, now=4000)   # clock went back


def test_backoff(api):
    b = api.Backoff()
    assert not b.blocked(0) and b.background_gap() == 30 * 60
    b.failed("offline", 100)
    assert b.blocked(114) and not b.blocked(115) and b.background_gap() == 60 * 60
    b.failed("offline", 200)
    assert b.blocked(229) and not b.blocked(230)
    for _ in range(10):
        b.failed("service", 1000)
    assert b.blocked(1299) and not b.blocked(1300) and b.background_gap() == 2 * 3600
    b.succeeded()
    assert not b.blocked(0) and b.failures == 0
    b.failed("rate_limited", 0)
    assert b.blocked(599) and not b.blocked(600) and b.last_error == "rate_limited"


# ------------------------------------------------------------
# main.py: actions, favourites, requests, Captain mode
# ------------------------------------------------------------

@pytest.fixture
def cmain(monkeypatch, tmp_data_dir, api, text, lang):
    """Cockpit's main.py with speech captured, the worker thread run inline,
    no waiting, and a fake aviationweather.gov."""
    import core.personal
    spec = importlib.util.spec_from_file_location("cockpit_main_under_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken, asked, requests = [], [], []
    clock = {"now": OBS + 600.0}
    service = {"metar": _copy(METAR_JSON), "box": _copy(BOX_JSON), "taf": _copy(TAF_JSON),
               "station": _copy(STATION_JSON), "error": None}

    def fake_fetch_json(url):
        requests.append(url)
        if service["error"]:
            raise api.AviationError(service["error"])
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        path = urllib.parse.urlsplit(url).path
        ids = set(query.get("ids", [""])[0].split(","))
        if path.endswith("/metar") and "bbox" in query:
            return _copy(service["box"])
        if path.endswith("/metar"):
            return [m for m in _copy(service["metar"]) if m["icaoId"] in ids]
        if path.endswith("/taf"):
            return [t for t in _copy(service["taf"]) if t["icaoId"] in ids]
        return [s for s in _copy(service["station"]) if s["icaoId"] in ids]

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(module, "speak", lambda msg, interrupt=False: spoken.append(msg))
    monkeypatch.setattr(module, "_start_thread", lambda target, *args: target(*args))
    monkeypatch.setattr(module, "_sleep", lambda seconds: None)
    monkeypatch.setattr(module, "_now", lambda: clock["now"])
    def ask(message):
        asked.append(message)
        return module.answers.pop(0) if module.answers else False

    monkeypatch.setattr(module, "_ask_yes_no", ask)
    monkeypatch.setattr(core.personal, "reminders_today_count", lambda day=None: 0)
    saved_providers = dict(core.personal._providers)
    module._active = True
    module.spoken, module.asked, module.requests = spoken, asked, requests
    module.clock, module.service, module.answers = clock, service, []
    yield module
    module._active = False
    core.personal._providers.clear()
    core.personal._providers.update(saved_providers)


def _weather_city(location=BATAM):
    import core.api
    core.api.save_data("Weather", {"location": location, "units": "metric"})


def _favourites(cmain, *codes):
    names = {"WIDD": "Batam/Hang Nadim, RI, ID", "WIII": "Jakarta/Hatta Intl, JB, ID"}
    cmain._settings["favourites"] = [{"icao": c, "name": names.get(c, c)} for c in codes]


def test_register_and_teardown(cmain, fresh_event_bus, monkeypatch):
    import core.hotkeys
    import core.personal
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel", lambda *args, **kwargs: panels.append(args))
    cmain.register(fresh_event_bus)
    for event_name, handler in cmain._SUBSCRIPTIONS:
        assert handler in fresh_event_bus._listeners[event_name]
    by_name = {args[1]: (args, kwargs) for args, kwargs in actions}
    args, kwargs = by_name["pilot_weather"]
    assert args[0] == "Cockpit" and args[3] == ord("Q") and args[4] is False and kwargs == {}
    args, kwargs = by_name["airport_weather"]
    assert args[3] == ord("Q") and kwargs == {"default_shift": True}
    assert panels[0][0] == "Cockpit"
    assert core.personal.is_placeholder_registered("airportweather")
    cmain.teardown()
    for event_name, handler in cmain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    assert not core.personal.is_placeholder_registered("airportweather")
    assert cmain.requests == []


def test_no_airport_and_no_city(cmain):
    cmain.speak_pilot_weather()
    assert cmain.spoken == [cmain._("no_airport")] and cmain.requests == []


def test_the_nearest_airport_to_the_weather_city(cmain):
    _weather_city()
    cmain.speak_pilot_weather()
    assert cmain.spoken[0] == "Looking for the airport nearest to Batam..."
    assert len(cmain.requests) == 1
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(cmain.requests[0]).query)
    assert query == {"bbox": ["0.1,103.0,2.1,105.0"], "format": ["json"]}
    assert cmain.spoken[1].startswith(
        "No favourite airports yet, so Hariku uses Batam Hang Nadim, W I D D, the nearest "
        "airport with a weather report to Batam. Batam Hang Nadim (nearest to Batam), W I D D, at ")
    assert cmain.default_airport() == {"icao": "WIDD", "name": "Batam/Hang Nadim, RI, ID",
                                       "auto": True, "city": "Batam"}
    # From the cache next time, and it says which airport it is.
    cmain.speak_pilot_weather()
    assert len(cmain.requests) == 1
    assert cmain.spoken[-1].startswith("Batam Hang Nadim (nearest to Batam), W I D D, at ")


def test_no_airport_near_the_city(cmain):
    _weather_city({"name": "Nowhere", "latitude": -40.0, "longitude": -120.0})
    cmain.service["box"] = []
    cmain.speak_pilot_weather()
    assert len(cmain.requests) == 2                       # 1 degree, then 3
    assert "bbox=-43.0%2C-123.0%2C-37.0%2C-117.0" in cmain.requests[1]
    assert cmain.spoken[-1].startswith("No airport with a weather report was found within "
                                       "about 300 kilometres of Nowhere.")


def test_fresh_cache_is_spoken_without_fetching(cmain):
    _favourites(cmain, "WIDD")
    cmain.speak_pilot_weather()
    assert cmain.spoken[0] == "Getting the airport weather..."
    assert cmain.spoken[1].startswith("Batam Hang Nadim, W I D D, at ")
    cmain.clock["now"] += 9 * 60
    cmain.speak_pilot_weather()
    assert len(cmain.requests) == 1                      # at most every 10 minutes
    cmain.clock["now"] += 2 * 60
    cmain.speak_pilot_weather()
    assert len(cmain.requests) == 2


def test_captain_mode_spells_the_code_and_the_raw_report(cmain):
    _favourites(cmain, "WIDD")
    cmain._settings.update(captain=True, raw=True)
    cmain.speak_pilot_weather()
    assert cmain.spoken[-1].startswith("Batam Hang Nadim, Whiskey India Delta Delta, at ")
    assert cmain.spoken[-1].endswith("Raw report: METAR WIDD 240330Z 20006KT 7000 FEW014 30/25 "
                                     "Q1013 NOSIG")


def test_offline_falls_back_to_the_last_report(cmain):
    _favourites(cmain, "WIDD")
    cmain.speak_pilot_weather()
    cmain.clock["now"] += 3600
    cmain.service["error"] = "offline"
    cmain.speak_pilot_weather()
    last = cmain.spoken[-1]
    assert last.startswith("Could not reach the aviation weather service.")
    assert "Showing the report fetched at " in last and "Batam Hang Nadim, W I D D" in last
    # Requests now pause: another press answers without a request.
    count = len(cmain.requests)
    cmain.speak_pilot_weather()
    assert len(cmain.requests) == count and cmain.spoken[-1].startswith("Could not reach")
    cmain.clock["now"] += 16
    cmain.service["error"] = None
    cmain.speak_pilot_weather()
    assert len(cmain.requests) == count + 1 and cmain.spoken[-1].startswith("Batam Hang Nadim")


def test_no_recent_report(cmain):
    _favourites(cmain, "WIDD")
    cmain.service["metar"] = []
    cmain.speak_pilot_weather()
    assert cmain.spoken[-1] == "No recent weather report from Batam Hang Nadim."
    cmain.speak_pilot_weather()                           # asked a moment ago: no new request
    assert len(cmain.requests) == 1 and cmain.spoken[-1].startswith("No recent weather report")


def test_one_request_at_a_time(cmain, monkeypatch):
    started = []
    monkeypatch.setattr(cmain, "_start_thread", lambda target, *args: started.append(args))
    done = []
    assert cmain.request_metar(["WIDD"], lambda r, e: done.append(("a", e)))
    assert cmain.request_metar(["WIDD"], lambda r, e: done.append(("b", e)))   # merged
    assert cmain.request_taf(["WIDD"], lambda r, e: done.append(("t", e)))     # queued
    assert len(started) == 1 and len(cmain._queue) == 1
    job = started[0][0]
    cmain._on_job_done(job, cmain.api.parse_metars(_copy(METAR_JSON)), None)
    assert done == [("a", None), ("b", None)] and len(started) == 2
    assert cmain.metar_entry("WIDD")["report"]["icao"] == "WIDD"


def test_requests_wait_between_each_other(cmain, monkeypatch):
    waits = []
    monkeypatch.setattr(cmain, "_sleep", waits.append)
    cmain.request_metar(["WIDD"])
    cmain.request_taf(["WIDD"])
    assert len(waits) == 1 and 0 < waits[0] <= cmain.api.MIN_GAP_SECONDS


def test_rate_limit_pauses_requests(cmain):
    _favourites(cmain, "WIDD")
    cmain.service["error"] = "rate_limited"
    cmain.speak_pilot_weather()
    assert cmain.spoken[-1].startswith("The aviation weather service asked Hariku to slow down.")
    cmain.service["error"] = None
    cmain.clock["now"] += 9 * 60
    cmain.speak_pilot_weather()
    assert len(cmain.requests) == 1
    cmain.clock["now"] += 2 * 60
    cmain.speak_pilot_weather()
    assert len(cmain.requests) == 2


# --- favourites -------------------------------------------------------------

def test_adding_a_favourite_checks_it(cmain):
    results = []
    add = lambda code: cmain.validate_airport(code, lambda *r: results.append(r))
    add("wi d")
    assert results[-1] == (None, "not_icao", False) and cmain.requests == []
    add("widd")
    assert results[-1] == ({"icao": "WIDD", "name": "Batam/Hang Nadim, RI, ID"}, None, True)
    assert [a["icao"] for a in cmain.favourites()] == ["WIDD"]
    import core.api
    assert core.api.load_data("Cockpit")["favourites"][0]["icao"] == "WIDD"
    add("WIDD")
    assert results[-1][1] == "already" and len(cmain.requests) == 1
    # A station without a recent report is looked up by name.
    cmain.service["metar"] = []
    cmain.service["station"] = [dict(STATION_JSON[0], icaoId="WIDN", site="Tanjung Pinang")]
    add("WIDN")
    assert results[-1] == ({"icao": "WIDN", "name": "Tanjung Pinang"}, None, False)
    assert "stationinfo?ids=WIDN" in cmain.requests[-1]
    add("ZZZZ")
    assert results[-1] == (None, "unknown", False)
    cmain.service["error"] = "offline"
    add("WIII")
    assert results[-1] == (None, "offline", False)


def test_too_many_favourites(cmain):
    _favourites(cmain, *[f"WA{c}{d}" for c in "ABCDE" for d in "ABCD"])
    results = []
    cmain.validate_airport("WIDD", lambda *r: results.append(r))
    assert results == [(None, "too_many", False)] and cmain.requests == []


def test_remove_and_make_default(cmain):
    _favourites(cmain, "WIDD", "WIII")
    assert cmain.make_default("WIII") is True
    assert cmain.default_airport()["icao"] == "WIII"
    assert cmain.make_default("WIII") is False
    assert cmain.remove_favourite("WIII") and not cmain.remove_favourite("WIII")
    assert [a["icao"] for a in cmain.airports()] == ["WIDD"]


def test_add_messages(text, lang):
    import cockpit_ui
    airport_ = {"icao": "WIDD", "name": "Batam/Hang Nadim, RI, ID"}
    assert cockpit_ui.add_result_message(airport_, None, True, "WIDD") == \
        "Added Batam Hang Nadim, W I D D."
    assert cockpit_ui.add_result_message(None, "unknown", False, "ZZZZ") == \
        "Z Z Z Z is not an airport with weather reports."
    lang("id")
    assert cockpit_ui.add_result_message(airport_, None, False, "WIDD") == (
        "Batam Hang Nadim, W I D D, ditambahkan. Saat ini belum ada laporan cuaca terbarunya.")


# --- the window's refresh ----------------------------------------------------

def test_window_refresh_asks_once_per_kind(cmain):
    _favourites(cmain, "WIDD", "WIII")
    ended = []
    assert cmain.WindowActions.refresh(ended.append) is True
    assert ended == [None] and len(cmain.requests) == 2
    assert "ids=WIDD%2CWIII" in cmain.requests[0] and "/taf?" in cmain.requests[1]
    assert cmain.WindowActions.refresh(ended.append) is False      # all fresh
    assert cmain.WindowActions.taf("WIII")["report"]["icao"] == "WIII"
    assert cmain.WindowActions.no_taf("WIDD")                       # WIDD has no TAF now


# --- the Briefing, the evening summary and %airportweather% ------------------

def test_briefing_lines(cmain):
    _favourites(cmain, "WIDD")
    lines = []
    cmain._on_briefing_collect(lines)
    assert lines == [] and cmain.requests == []           # nothing cached: nothing said
    cmain.request_metar(["WIDD"])
    count = len(cmain.requests)
    cmain._on_briefing_collect(lines)
    assert lines == []                                    # Captain mode off, box not ticked
    cmain._settings["briefing"] = True
    cmain._on_briefing_collect(lines)
    assert lines == ["Airport weather at Hang Nadim: a few clouds, 30 degrees, wind 6 knots."]
    cmain._settings["captain"] = True
    lines = []
    cmain._on_briefing_collect(lines)
    assert len(lines) == 1 and lines[0].startswith("It's ") and " Zulu. Hang Nadim: wind from " \
        "200 degrees at 6 knots, visibility 7 kilometres, a few clouds at 1,400 feet, 30 " \
        "degrees, QNH 1013." in lines[0]
    cmain.clock["now"] = OBS + 3 * 3600 + 60              # the observation is too old
    lines = []
    cmain._on_briefing_collect(lines)
    assert lines == [] and len(cmain.requests) == count


def test_briefing_line_needs_a_favourite_without_captain_mode(cmain):
    _weather_city()
    cmain.speak_pilot_weather()                           # the nearest airport, cached
    cmain._settings["briefing"] = True
    lines = []
    cmain._on_briefing_collect(lines)
    assert lines == []
    cmain._settings["captain"] = True
    cmain._on_briefing_collect(lines)
    assert len(lines) == 1


def test_evening_line(cmain, monkeypatch):
    _favourites(cmain, "WIII")
    real = cmain.text.evening_line
    evening = datetime.datetime(2026, 9, 24, 20, 0, tzinfo=WIB)
    monkeypatch.setattr(cmain.text, "evening_line", lambda a, t, now=None: real(a, t, evening))
    cmain.request_taf(["WIII"])
    lines = []
    cmain._on_evening_collect(lines)
    assert lines == []                                    # not in Captain mode
    cmain._settings["captain"] = True
    cmain._on_evening_collect(lines)
    assert lines == ["Tomorrow morning at Hatta International: wind from 140 degrees at 5 "
                     "knots, visibility 7 kilometres, scattered clouds at 2,000 feet."]


def test_airportweather_placeholder(cmain, fresh_event_bus, monkeypatch):
    import core.hotkeys
    import core.personal
    import core.preferences
    monkeypatch.setattr(core.hotkeys, "register_action", lambda *a, **k: None)
    monkeypatch.setattr(core.preferences, "register_panel", lambda *a, **k: None)
    cmain.register(fresh_event_bus)
    cmain.clock["now"] = OBS + 600
    _favourites(cmain, "WIDD")
    assert core.personal.expand("[%airportweather%]") == "[]"   # nothing cached yet
    cmain.request_metar(["WIDD"])
    assert core.personal.expand("%airportweather%.") == (
        "Hang Nadim: wind from 200 degrees at 6 knots, visibility 7 kilometres, a few clouds "
        "at 1,400 feet, 30 degrees, QNH 1013.")
    requests = len(cmain.requests)
    core.personal.expand("%airportweather%")
    assert len(cmain.requests) == requests                     # the cache only
    cmain.teardown()


# --- background refresh (Captain mode only) ----------------------------------

def test_no_polling_without_captain_mode(cmain):
    _favourites(cmain, "WIDD")
    cmain._on_app_startup()
    cmain._on_minute_tick()
    assert cmain.requests == []


def test_captain_mode_refreshes_every_30_minutes(cmain):
    _favourites(cmain, "WIII")
    cmain._settings["captain"] = True
    cmain._on_app_startup()
    assert len(cmain.requests) == 2                       # the METAR and the TAF
    cmain.clock["now"] += 29 * 60
    cmain._on_minute_tick()
    assert len(cmain.requests) == 2
    cmain.clock["now"] += 2 * 60
    cmain._on_minute_tick()
    assert len(cmain.requests) == 4
    # A failure doubles the gap.
    cmain.service["error"] = "offline"
    cmain.clock["now"] += 31 * 60
    cmain._on_minute_tick()
    assert len(cmain.requests) == 5
    cmain.service["error"] = None
    cmain.clock["now"] += 31 * 60
    cmain._on_minute_tick()
    assert len(cmain.requests) == 5                       # 60 minutes now
    cmain._on_network_changed(True)                       # but back online: try at once
    assert len(cmain.requests) == 7


def test_captain_mode_finds_the_nearest_airport_in_the_background(cmain):
    _weather_city()
    cmain._settings["captain"] = True
    cmain._on_app_startup()
    assert "bbox=" in cmain.requests[0]
    assert cmain.default_airport()["icao"] == "WIDD"


# --- Captain mode's offers ---------------------------------------------------

def test_turning_captain_mode_on_and_off(cmain):
    import core.personal
    core.personal.set_profile("Rafli", "Bro", [])
    cmain.answers[:] = [True, True]
    cmain.apply_settings({"captain": True, "raw": False, "briefing": False})
    assert cmain.is_captain()
    assert cmain.asked[0].startswith("Shall Hariku call you Captain? Your greeting would then "
                                     "be, for example: Good ")
    assert ", Captain Bro." in cmain.asked[0]
    assert cmain.asked[1].startswith("Set a cockpit greeting for when Hariku starts? Hariku "
                                      "would say something like: Welcome aboard, Captain Bro. "
                                      "Welcome to your cockpit. It's ")
    assert core.personal.get_title() == "Captain"
    assert core.personal.get_custom_greeting()["text"] == cmain._("cockpit_greeting")
    # Applying again with Captain mode still on asks nothing.
    cmain.apply_settings({"captain": True})
    assert len(cmain.asked) == 2
    cmain.answers[:] = [True, True]
    cmain.apply_settings({"captain": False})
    assert cmain.asked[2] == "Captain mode is off. Remove the title Captain?"
    assert cmain.asked[3] == "Remove the cockpit greeting too, so Hariku greets you as usual?"
    assert core.personal.get_title() == ""
    assert core.personal.get_custom_greeting()["text"] == ""


def test_captain_mode_respects_what_the_user_chose(cmain, lang):
    import core.personal
    lang("id")
    core.personal.set_title("Pak")
    core.personal.set_custom_greeting("Halo %mynickname%")
    cmain.answers[:] = [False]
    cmain.apply_settings({"captain": True})
    assert len(cmain.asked) == 1 and cmain.asked[0].startswith("Pasang sapaan kokpit")
    assert core.personal.get_title() == "Pak"
    assert core.personal.get_custom_greeting()["text"] == "Halo %mynickname%"
    cmain.apply_settings({"captain": False})
    assert len(cmain.asked) == 1                           # nothing of ours to take back


def test_the_indonesian_title_and_greeting(cmain, lang):
    import core.personal
    lang("id")
    core.personal.set_profile("Rafli", "Bro", [])
    cmain.answers[:] = [True, True]
    cmain.apply_settings({"captain": True})
    assert cmain.asked[0].startswith("Mau Hariku panggil Kapten? Sapaanmu nanti jadi misalnya: "
                                     "Selamat ")
    assert core.personal.get_title() == "Kapten"
    greeting = core.personal.get_custom_greeting()["text"]
    assert greeting.startswith("Selamat datang di kokpit, %mytitle% %mynickname%.")
    # The greeting as Hariku will say it, with the airport weather cached.
    _favourites(cmain, "WIDD")
    cmain.request_metar(["WIDD"])
    core.personal.register_placeholder("airportweather", cmain.placeholder_text)
    core.personal.reminders_today_count = lambda day=None: 2     # undone by monkeypatch
    now = datetime.datetime(2026, 9, 24, 10, 40, tzinfo=WIB)
    spoken = core.personal.startup_speech("", now, boot=True)
    assert spoken == ("Selamat datang di kokpit, Kapten Bro. Sekarang pukul 10:40, 03:40 Zulu. "
                      "Hang Nadim: angin dari 200 derajat, 6 knot, jarak pandang 7 kilometer, "
                      "sedikit awan di ketinggian 1.400 kaki, 30 derajat, QNH 1013. Agenda kamu: "
                      "2 pengingat hari ini. Kita mau ke mana hari ini?")


# ------------------------------------------------------------
# The Cockpit sound theme
# ------------------------------------------------------------

def test_sound_files(snd, theme_files):
    assert set(theme_files) == {"info.wav", "penClick.wav", "confirm.wav", "error.wav", "start.wav"}
    for name, data in theme_files.items():
        assert data[:4] == b"RIFF" and data[8:12] == b"WAVE", name
        channels, width, rate, frames = snd.wav_info(data)
        assert (channels, width, rate) == (1, 2, 44100), name
        assert 0.2 < frames / rate < snd.MAX_SECONDS, name
        samples = snd.samples_of(data)
        peak = max(abs(s) for s in samples)
        assert 0.4 * 32767 < peak <= 0.81 * 32767, (name, peak)       # loud enough, no clipping
        assert samples[0] == 0 and abs(samples[-1]) < 200, name        # no clicks


def test_sounds_are_different_and_deterministic(snd, theme_files):
    assert len({theme_files[n] for n in ("info.wav", "penClick.wav", "error.wav", "start.wav")}) == 4
    assert snd.double_beep() == theme_files["error.wav"]
    assert snd.single_chime() == theme_files["penClick.wav"] == theme_files["confirm.wav"]


def test_the_ding_dong_has_two_tones(snd, theme_files):
    samples = snd.samples_of(theme_files["info.wav"])

    def crossings(start, end):
        part = samples[int(start * 44100):int(end * 44100)]
        return sum(1 for a, b in zip(part, part[1:]) if a < 0 <= b) / (end - start)

    ding, dong = crossings(0.1, 0.35), crossings(0.9, 1.2)
    assert 600 < ding < 720 and 480 < dong < 570       # E5 then C5


def test_install_theme_in_the_sound_themes_format(snd, tmp_path, theme_files):
    if THEMES_EXT_DIR not in sys.path:
        sys.path.insert(0, THEMES_EXT_DIR)
    import sound_themes_store
    root = tmp_path / "sound_themes"
    (root / "Cockpit").mkdir(parents=True)
    (root / "Cockpit" / "move.wav").write_bytes(b"the user's own")
    (root / "Cockpit" / "info.wav").write_bytes(b"old")
    stopped = []
    folder = snd.install_theme(str(root), stop_sound=stopped.append,
                               check=sound_themes_store.check_wav_data)
    assert folder == str(root / "Cockpit")
    assert sorted(os.listdir(folder)) == ["confirm.wav", "error.wav", "info.wav", "move.wav",
                                          "penClick.wav", "start.wav"]
    assert (root / "Cockpit" / "info.wav").read_bytes() == theme_files["info.wav"]
    assert (root / "Cockpit" / "move.wav").read_bytes() == b"the user's own"
    assert sorted(stopped) == sorted(theme_files)
    for name in theme_files:
        assert sound_themes_store.canonical_sound_name(name) == name


def test_install_needs_the_sound_themes_extension(cmain, monkeypatch, tmp_path):
    import core.api
    from core import extension_manager
    messages = []
    monkeypatch.setattr(extension_manager, "LOADED_EXTENSIONS", {})
    monkeypatch.setattr(extension_manager, "get_installed_extensions_info", lambda: [])
    assert cmain.install_sound_theme(messages.append) is False
    assert messages[-1].startswith("The Sound Themes extension isn't installed.")
    monkeypatch.setattr(extension_manager, "get_installed_extensions_info",
                        lambda: [{"id": "sound_themes", "is_enabled": False}])
    cmain.install_sound_theme(messages.append)
    assert messages[-1].startswith("The Sound Themes extension is turned off.")
    monkeypatch.setattr(extension_manager, "LOADED_EXTENSIONS", {"sound_themes": {"module": None}})
    monkeypatch.setattr(core.api, "USER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cmain, "_theme_check", lambda: None)
    monkeypatch.setattr(cmain.core.sounds, "stop_sound", lambda name: True)
    monkeypatch.setattr(cmain.sounds, "theme_files", lambda: {"info.wav": b"RIFF....WAVEdata"})
    assert cmain.install_sound_theme(messages.append) is True
    assert messages[-1].startswith("The Cockpit sound theme is installed.")
    assert (tmp_path / "sound_themes" / "Cockpit" / "info.wav").is_file()
