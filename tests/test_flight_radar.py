# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Flight Radar extension: adsb.fi / adsb.lol parsing and fallback,
# units, names, sentences in both languages, request pacing, overhead alerts,
# adsbdb routes and the actions. No test touches the network: the fetch
# functions are replaced. All aircraft samples are synthetic.

import importlib.util
import json
import os
import sys
import urllib.error

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FR_DIR = os.path.join(ROOT, "extensions", "flight_radar")

JAKARTA = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
           "latitude": -6.2, "longitude": 106.8}


def _plane(**overrides):
    plane = {"hex": "abc001", "flight": "GIA155  ", "r": "PK-QQA", "t": "B738",
             "alt_baro": 9843, "gs": 250.0, "track": 315.0, "baro_rate": -832,
             "dst": 6.48, "dir": 45.0, "squawk": "2345", "emergency": "none",
             "category": "A3", "lat": -6.12, "lon": 106.88, "seen": 0.4}
    plane.update(overrides)
    return {k: v for k, v in plane.items() if v is not None}


# 12 km northeast, descending; 4.5 km south, climbing; on the ground at 20 km;
# an unknown airline without distance (computed from its position, 11 km east);
# one without any identity and one that is not an object (both dropped).
PLANES = [
    _plane(),
    _plane(hex="abc002", flight="CTV991", r="PK-QQB", t="A320", alt_baro=4921, gs=180,
           track=0, baro_rate=1500, dst=2.43, dir=180.0, squawk="1200", lat=-6.24, lon=106.8),
    _plane(hex="abc003", flight="AWQ531", r="PK-QQC", t="A20N", alt_baro="ground", gs=3,
           baro_rate=None, dst=10.8, dir=270.0, squawk=None),
    _plane(hex="abc004", flight="XQZ357", r=None, t="ZZZ9", desc="DIAMOND DA-62",
           alt_baro=2000, baro_rate=0, dst=None, dir=None, lat=-6.2, lon=106.9, squawk=None),
    {"alt_baro": 1000, "dst": 1.0},
    "junk",
]
ADSBFI_JSON = {"aircraft": PLANES, "now": 1790000000000, "resultCount": 6, "ptime": 2}
ADSBLOL_JSON = {"ac": PLANES[:2], "ctime": 1790000000000, "msg": "No error",
                "now": 1790000000000, "ptime": 1, "total": 2}

BATAM = {"municipality": "Batam", "name": "Hang Nadim International Airport",
         "iata_code": "BTH", "icao_code": "WIDD", "latitude": 1.121, "longitude": 104.119}
CGK = {"municipality": "Jakarta", "name": "Soekarno-Hatta International Airport",
       "iata_code": "CGK", "icao_code": "WIII", "latitude": -6.1256, "longitude": 106.6559}
ROUTE_JSON = {"response": {"flightroute": {
    "callsign": "GIA155",
    "airline": {"name": "Some Other Airline Name", "icao": "GIA"},
    "origin": dict(BATAM, country_name="Indonesia", country_iso_name="ID", elevation=126),
    "destination": dict(CGK, country_name="Indonesia", country_iso_name="ID", elevation=34),
}}}


def _import_helpers():
    if FR_DIR not in sys.path:
        sys.path.insert(0, FR_DIR)
    import flight_radar_api
    import flight_radar_names
    import flight_radar_routes
    import flight_radar_text
    return flight_radar_api, flight_radar_text, flight_radar_names, flight_radar_routes


@pytest.fixture(scope="module")
def api():
    return _import_helpers()[0]


@pytest.fixture(scope="module")
def text():
    return _import_helpers()[1]


@pytest.fixture(scope="module")
def names():
    return _import_helpers()[2]


@pytest.fixture(scope="module")
def routes():
    return _import_helpers()[3]


@pytest.fixture
def lang(monkeypatch, text):
    from core import i18n

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("en")
    return set_lang


@pytest.fixture
def planes(api):
    return api.parse_aircraft_list(json.loads(json.dumps(ADSBFI_JSON)),
                                   JAKARTA["latitude"], JAKARTA["longitude"])


def _by_callsign(aircraft, callsign):
    return next(p for p in aircraft if p["callsign"] == callsign)


# ------------------------------------------------------------
# Locale files
# ------------------------------------------------------------

def test_locales_have_the_same_keys():
    keys = {}
    for code in ("en", "id"):
        with open(os.path.join(FR_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            keys[code] = set(json.load(f)["messages"])
    assert keys["en"] == keys["id"]


def test_keys_built_at_runtime_exist(text, lang):
    with open(os.path.join(FR_DIR, "locales", "en.json"), encoding="utf-8") as f:
        keys = set(json.load(f)["messages"])
    assert set(text._ERROR_KEYS.values()) <= keys
    for kind in ("offline", "service", "rate_limited", "bad_response"):
        assert not text.error_text(kind).startswith("err_")


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def test_parse_adsbfi(api, planes):
    assert [p["callsign"] for p in planes] == ["GIA155", "CTV991", "AWQ531", "XQZ357"]
    gia = planes[0]
    assert gia["id"] == "abc001" and gia["registration"] == "PK-QQA"
    assert gia["type_code"] == "B738" and not gia["on_ground"]
    assert gia["altitude_ft"] == 9843 and gia["speed_kt"] == 250 and gia["track"] == 315
    assert gia["vertical_rate_fpm"] == -832 and gia["squawk"] == "2345"
    assert gia["emergency"] == "" and gia["bearing"] == 45
    assert gia["distance_km"] == pytest.approx(12.0, abs=0.01)
    ground = planes[2]
    assert ground["on_ground"] and ground["altitude_ft"] is None
    # No dst/dir in the sample: worked out from its position, about 11 km east.
    unknown = planes[3]
    assert unknown["distance_km"] == pytest.approx(11.05, abs=0.1)
    assert unknown["bearing"] == pytest.approx(90, abs=1)
    assert unknown["type_desc"] == "DIAMOND DA-62" and unknown["registration"] == ""


def test_parse_adsblol(api):
    planes = api.parse_aircraft_list(json.loads(json.dumps(ADSBLOL_JSON)), -6.2, 106.8)
    assert [p["callsign"] for p in planes] == ["GIA155", "CTV991"]


@pytest.mark.parametrize("payload", [None, [], "x", {}, {"aircraft": "none"}, {"ac": None},
                                     {"msg": "error"}])
def test_parse_rejects_unusable_data(api, payload):
    with pytest.raises(api.FlightError) as info:
        api.parse_aircraft_list(payload)
    assert info.value.kind == "bad_response"


def test_parse_skips_aircraft_without_a_distance(api):
    assert api.parse_aircraft_list({"aircraft": [_plane(dst=None, lat=None, lon=None)]}, 1, 2) == []
    assert api.parse_aircraft_list({"aircraft": [_plane(dst=None)]}) == []  # no query point


def test_surface_vehicles_count_as_ground(api):
    plane = api.normalize_aircraft(_plane(category="C2", alt_baro=0))
    assert plane["on_ground"]


def test_request_urls(api):
    assert api.build_adsbfi_url(-6.214621, 106.84513, 14) == (
        "https://opendata.adsb.fi/api/v2/lat/-6.2146/lon/106.8451/dist/14")
    assert api.build_adsblol_url(-6.214621, 106.84513, 14) == (
        "https://api.adsb.lol/v2/point/-6.2146/106.8451/14")
    url = api.build_search_url("  Jakarta ", "id")
    assert url.startswith("https://geocoding-api.open-meteo.com/v1/search?")
    assert "name=Jakarta&" in url and "count=10" in url and "language=id" in url
    assert "language=en" in api.build_search_url("Paris", "fr")


def test_parse_places(api):
    places = api.parse_places({"results": [
        {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
         "latitude": -6.2, "longitude": 106.8, "timezone": "Asia/Jakarta"},
        {"name": "Nowhere", "latitude": "north"}]})
    assert places == [JAKARTA]
    assert api.place_label(places[0]) == "Jakarta, Indonesia"
    assert api.parse_places(None) == []


# ------------------------------------------------------------
# HTTP (urlopen replaced, nothing is sent)
# ------------------------------------------------------------

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
        seen["agent"] = req.get_header("User-agent")
        seen["timeout"] = timeout
        return _Response(b'{"ok": true}')

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    assert api.fetch_json("https://example.invalid/") == {"ok": True}
    assert seen["agent"].startswith("HarikuV2/") and "Flight Radar" in seen["agent"]
    assert seen["timeout"] == api.TIMEOUT_SECONDS


@pytest.mark.parametrize("failure, kind, status", [
    (urllib.error.URLError("no route to host"), "offline", None),
    (TimeoutError("timed out"), "offline", None),
    (urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None), "service", 503),
    (urllib.error.HTTPError("https://x", 404, "Not Found", {}, None), "service", 404),
    (urllib.error.HTTPError("https://x", 429, "Too Many Requests", {}, None), "rate_limited", 429),
])
def test_fetch_json_maps_failures(api, monkeypatch, failure, kind, status):
    def fake_urlopen(req, timeout=None):
        raise failure

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(api.FlightError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == kind and info.value.status == status


def test_fetch_json_rejects_bad_body(api, monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b"<html>oops</html>"))
    with pytest.raises(api.FlightError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == "bad_response"


def _fake_sources(monkeypatch, api, fi=None, lol=None):
    """Replace fetch_json: each argument is a JSON payload or a FlightError kind."""
    calls = []

    def fake_fetch_json(url, timeout=None):
        calls.append(url)
        answer = fi if "adsb.fi" in url else lol
        if isinstance(answer, str):
            raise api.FlightError(answer, status=429 if answer == "rate_limited" else 503)
        return json.loads(json.dumps(answer))

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    return calls


def test_adsbfi_is_used_first(api, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi=ADSBFI_JSON, lol=ADSBLOL_JSON)
    aircraft, source = api.fetch_aircraft(-6.2, 106.8, 14)
    assert source == "adsb.fi" and len(aircraft) == 4
    assert calls == ["https://opendata.adsb.fi/api/v2/lat/-6.2000/lon/106.8000/dist/14"]


def test_adsblol_is_the_fallback(api, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi="service", lol=ADSBLOL_JSON)
    aircraft, source = api.fetch_aircraft(-6.2, 106.8, 14)
    assert source == "adsb.lol" and len(aircraft) == 2
    assert calls[1] == "https://api.adsb.lol/v2/point/-6.2000/106.8000/14"

    calls = _fake_sources(monkeypatch, api, fi={"unexpected": True}, lol=ADSBLOL_JSON)
    assert api.fetch_aircraft(-6.2, 106.8, 14)[1] == "adsb.lol"


@pytest.mark.parametrize("fi, lol, kind", [
    ("offline", "offline", "offline"),
    ("rate_limited", "rate_limited", "rate_limited"),
    ("rate_limited", "offline", "rate_limited"),
    ("service", "offline", "service"),
])
def test_both_sources_failing(api, monkeypatch, fi, lol, kind):
    calls = _fake_sources(monkeypatch, api, fi=fi, lol=lol)
    with pytest.raises(api.FlightError) as info:
        api.fetch_aircraft(-6.2, 106.8, 14)
    assert info.value.kind == kind and len(calls) == 2


# ------------------------------------------------------------
# Filtering, units, directions
# ------------------------------------------------------------

def test_visible_aircraft_filters_and_sorts(api, planes):
    airborne = api.visible_aircraft(planes, 25)
    assert [p["callsign"] for p in airborne] == ["CTV991", "XQZ357", "GIA155"]
    with_ground = api.visible_aircraft(planes, 25, include_ground=True)
    assert [p["callsign"] for p in with_ground] == ["CTV991", "XQZ357", "GIA155", "AWQ531"]
    assert [p["callsign"] for p in api.visible_aircraft(planes, 10)] == ["CTV991"]
    assert api.visible_aircraft([], 25) == []


def test_unit_conversion(api):
    assert api.nm_to_km(1) == pytest.approx(1.852)
    assert api.km_to_nm(1.852) == pytest.approx(1)
    assert api.ft_to_m(1000) == pytest.approx(304.8)
    assert api.kt_to_kmh(100) == pytest.approx(185.2)
    assert [api.query_radius_nm(km) for km in api.RADIUS_CHOICES_KM] == [6, 14, 27]


@pytest.mark.parametrize("degrees, index", [
    (0, 0), (22.4, 0), (22.5, 1), (45, 1), (90, 2), (135, 3), (180, 4), (225, 5),
    (270, 6), (315, 7), (337.4, 7), (337.5, 0), (359.9, 0), (360, 0), (-90, 6), (720 + 45, 1),
])
def test_compass_index(api, degrees, index):
    assert api.compass_index(degrees) == index


def test_compass_names(text, lang):
    assert text.compass_names() == ["north", "northeast", "east", "southeast",
                                    "south", "southwest", "west", "northwest"]
    assert text.compass(None) is None
    lang("id")
    assert text.compass_names() == ["utara", "timur laut", "timur", "tenggara",
                                    "selatan", "barat daya", "barat", "barat laut"]


def test_distance_and_bearing(api):
    km, bearing = api.distance_and_bearing(0, 0, 0, 1)
    assert km == pytest.approx(111.19, abs=0.1) and bearing == pytest.approx(90)
    km, bearing = api.distance_and_bearing(0, 0, 1, 0)
    assert bearing == pytest.approx(0)


def test_numbers_and_units(text, lang):
    assert text.number(3000) == "3,000"
    assert text.number(4.5, 1) == "4.5"
    assert text.number(-0.0) == "0"
    assert text.distance_text(4.46, "metric") == "4.5 kilometres"
    assert text.distance_text(12.3, "metric") == "12 kilometres"
    assert text.distance_text(1.02, "metric") == "1 kilometre"
    assert text.distance_text(9.97, "metric") == "10 kilometres"
    assert text.distance_text(12.0, "aviation") == "6.5 nautical miles"
    assert text.distance_text(1.852, "aviation") == "1 nautical mile"
    assert text.altitude_text(9843, "metric") == "3,000 metres"
    assert text.altitude_text(10049, "aviation") == "10,000 feet"
    assert text.altitude_text(150, "metric") == "50 metres"
    assert text.altitude_text(-120, "aviation") == "0 feet"
    assert text.speed_text(250, "metric") == "460 kilometres per hour"
    assert text.speed_text(250, "aviation") == "250 knots"
    assert text.speed_text(4, "aviation") == "4 knots"
    assert text.rate_text(-832, "metric") == "250 metres per minute"
    assert text.rate_text(1540, "aviation") == "1,500 feet per minute"
    lang("id")
    assert text.number(3000) == "3.000"
    assert text.distance_text(4.46, "metric") == "4,5 kilometer"
    assert text.altitude_text(35000, "aviation") == "35.000 kaki"
    assert text.speed_text(250, "metric") == "460 kilometer per jam"


def test_trend(text):
    assert text.trend(None) is None
    assert text.trend(1000) == "climbing" and text.trend(-1000) == "descending"
    assert text.trend(100) == "level" and text.trend(-200) == "level"


# ------------------------------------------------------------
# Names
# ------------------------------------------------------------

def test_airline_table(names):
    assert 60 <= len(names.AIRLINES) <= 100
    for prefix, airline in {"GIA": "Garuda Indonesia", "CTV": "Citilink", "LNI": "Lion Air",
                            "BTK": "Batik Air", "AWQ": "Indonesia AirAsia",
                            "SJY": "Sriwijaya Air", "WON": "Wings Air",
                            "TGN": "Trigana Air"}.items():
        assert names.airline_name(prefix) == airline
    assert names.airline_name("gia") == "Garuda Indonesia"
    assert names.airline_name("XQZ") is None
    assert all(len(k) == 3 and k.isupper() for k in names.AIRLINES)


def test_type_table(names):
    assert len(names.AIRCRAFT_TYPES) >= 60
    assert names.aircraft_type_name("B738") == "Boeing 737-800"
    assert names.aircraft_type_name("a320") == "Airbus A320"
    assert names.aircraft_type_name("AT76") == "ATR 72-600"
    assert names.aircraft_type_name("ZZZ9") is None
    assert names.HELICOPTER_TYPES <= set(names.AIRCRAFT_TYPES)


def test_aircraft_names(text, lang):
    assert text.aircraft_name({"callsign": "GIA155"}) == "Garuda Indonesia 155"
    assert text.aircraft_name({"callsign": "BTK6339"}) == "Batik Air 6339"
    assert text.aircraft_name({"callsign": "GIA0155"}) == "Garuda Indonesia 155"
    assert text.aircraft_name({"callsign": "AWQ53A"}) == "Indonesia AirAsia 53 A"
    # Unknown prefixes and non-airline callsigns are spelled out.
    assert text.aircraft_name({"callsign": "XQZ357"}) == "X Q Z 357"
    assert text.aircraft_name({"callsign": "PKQQA"}) == "P K Q Q A"
    assert text.aircraft_name({"callsign": "", "registration": "PK-QQA"}) == "P K Q Q A"
    assert text.aircraft_name({"callsign": "", "registration": ""}) == "Unidentified aircraft"
    lang("id")
    assert text.aircraft_name({}) == "Pesawat tanpa identitas"


def test_spelling(text):
    assert text.spell_code("SJV357") == "S J V 357"
    assert text.spell_code("C172") == "C 172"
    assert text.spell_code("") == ""
    assert text.spell_all("PK-QQA") == "P K Q Q A"
    assert text.spell_all("7700") == "7 7 0 0"


def test_type_names(text, lang):
    assert text.type_name({"type_code": "B738"}) == "Boeing 737-800"
    assert text.type_name({"type_code": "ZZZ9", "type_desc": "DIAMOND DA-62"}) == "Diamond DA-62"
    assert text.type_name({"type_code": "ZZZ9", "type_desc": "ATR ATR-72"}) == "ATR ATR-72"
    assert text.type_name({"type_code": "ZZZ9"}) == "Z Z Z 9"
    assert text.type_name({}) is None
    assert text.type_name({"type_code": "EC35"}) == "Airbus H135 helicopter"
    assert text.type_name({"type_code": "ZZZ9", "category": "A7"}) == "Z Z Z 9 helicopter"
    lang("id")
    assert text.type_name({"type_code": "EC35"}) == "helikopter Airbus H135"


# ------------------------------------------------------------
# Sentences
# ------------------------------------------------------------

def test_aircraft_sentence_english(text, lang, planes):
    gia = _by_callsign(planes, "GIA155")
    assert text.aircraft_sentence(gia, "metric") == (
        "Garuda Indonesia 155, Boeing 737-800, 12 kilometres northeast, 3,000 metres, descending.")
    assert text.aircraft_sentence(gia, "aviation") == (
        "Garuda Indonesia 155, Boeing 737-800, 6.5 nautical miles northeast, 9,800 feet, descending.")
    ctv = _by_callsign(planes, "CTV991")
    assert text.aircraft_sentence(ctv, "metric") == (
        "Citilink 991, Airbus A320, 4.5 kilometres south, 1,500 metres, climbing.")
    xqz = _by_callsign(planes, "XQZ357")
    assert text.aircraft_sentence(xqz, "metric") == (
        "X Q Z 357, Diamond DA-62, 11 kilometres east, 600 metres, level.")
    ground = _by_callsign(planes, "AWQ531")
    assert text.aircraft_sentence(ground, "metric") == (
        "Indonesia AirAsia 531, Airbus A320neo, 20 kilometres west, on the ground.")


def test_aircraft_sentence_indonesian(text, lang, planes):
    lang("id")
    gia = _by_callsign(planes, "GIA155")
    assert text.aircraft_sentence(gia, "metric") == (
        "Garuda Indonesia 155, Boeing 737-800, 12 kilometer di sebelah timur laut, "
        "ketinggian 3.000 meter, turun.")
    ground = _by_callsign(planes, "AWQ531")
    assert text.aircraft_sentence(ground, "metric").endswith("di sebelah barat, di darat.")


def test_sentence_with_route(text, lang, planes):
    leg = {"origin": BATAM, "destination": CGK}
    gia = _by_callsign(planes, "GIA155")
    assert text.aircraft_sentence(gia, "metric", leg).startswith(
        "Garuda Indonesia 155, from Batam to Jakarta, Boeing 737-800, 12 kilometres")
    no_town = {"origin": dict(BATAM, municipality=""), "destination": CGK}
    assert "from Hang Nadim International Airport to Jakarta" in text.aircraft_sentence(
        gia, "metric", no_town)
    lang("id")
    assert text.aircraft_sentence(gia, "metric", leg).startswith(
        "Garuda Indonesia 155, dari Batam ke Jakarta, Boeing 737-800")


def test_sentence_skips_missing_values(text, lang, api):
    plane = api.normalize_aircraft({"hex": "abc009", "dst": 1.0})
    assert text.aircraft_sentence(plane, "metric") == "Unidentified aircraft, 1.9 kilometres."


def test_emergency_is_mentioned(text, lang, api):
    plane = api.normalize_aircraft(_plane(squawk="7700"))
    assert text.aircraft_sentence(plane, "metric").endswith("descending, emergency.")
    plane = api.normalize_aircraft(_plane(emergency="general"))
    assert "Emergency reported." in text.details_text(plane, "metric")


def test_nearby_report(text, lang, api, planes):
    extra = [api.normalize_aircraft(_plane(hex=f"abd{i}", flight=f"LNI{i}0", dst=10 + i))
             for i in range(2)]
    visible = api.visible_aircraft(planes + extra, 50)
    report = text.nearby_report(visible, 50, "metric", False)
    assert report.startswith("Citilink 991, Airbus A320, 4.5 kilometres south")
    assert report.count(".") >= 4 and "Garuda Indonesia 155" in report
    assert "Lion Air" not in report
    assert report.endswith("And 2 more within 50 kilometres.")
    lang("id")
    assert text.nearby_report(visible, 50, "metric", False).endswith(
        "Dan 2 lainnya dalam radius 50 kilometer.")


def test_nearby_report_small_and_empty(text, lang, api, planes):
    visible = api.visible_aircraft(planes, 10)
    assert text.nearby_report(visible, 10, "metric", False) == (
        "Citilink 991, Airbus A320, 4.5 kilometres south, 1,500 metres, climbing.")
    assert text.nearby_report([], 25, "metric", False) == (
        "No aircraft in the air within 25 kilometres right now.")
    assert text.nearby_report([], 25, "metric", True) == "No aircraft within 25 kilometres right now."
    assert text.nearby_report([], 25, "aviation", False) == (
        "No aircraft in the air within 13 nautical miles right now.")
    lang("id")
    assert text.nearby_report([], 25, "metric", False) == (
        "Saat ini tidak ada pesawat di udara dalam radius 25 kilometer.")


def test_details_text(text, lang, planes):
    gia = _by_callsign(planes, "GIA155")
    assert text.details_text(gia, "metric") == (
        "Garuda Indonesia 155. Registration P K Q Q A. Type Boeing 737-800. "
        "Speed 460 kilometres per hour. Heading northwest. Descending 250 metres per minute. "
        "Squawk 2 3 4 5.")
    assert "Speed 250 knots." in text.details_text(gia, "aviation")
    assert "Descending 800 feet per minute." in text.details_text(gia, "aviation")
    leg = {"origin": BATAM, "destination": CGK}
    assert text.details_text(gia, "metric", leg).startswith(
        "Garuda Indonesia 155, from Batam to Jakarta. Registration")
    lang("id")
    assert text.details_text(gia, "metric") == (
        "Garuda Indonesia 155. Registrasi P K Q Q A. Tipe Boeing 737-800. "
        "Kecepatan 460 kilometer per jam. Menuju arah barat laut. Turun 250 meter per menit. "
        "Squawk 2 3 4 5.")


def test_details_with_nothing_known(text, lang, api):
    plane = api.normalize_aircraft({"hex": "abc009", "dst": 1.0})
    assert text.details_text(plane, "metric") == "Unidentified aircraft. No other details available."


def test_alert_text(text, lang, planes):
    ctv = _by_callsign(planes, "CTV991")
    assert text.alert_text([ctv], "metric") == (
        "Overhead: Citilink 991, Airbus A320, 4.5 kilometres south, 1,500 metres, climbing.")
    lang("id")
    assert text.alert_text([ctv], "metric").startswith("Melintas di atas: Citilink 991")


def test_distance_choices(text, lang):
    assert text.distance_choice(25) == "25 kilometres (13 nautical miles)"
    assert text.distance_choice(10) == "10 kilometres (5.4 nautical miles)"
    assert text.distance_choice(1) == "1 kilometre (0.5 nautical miles)"


def test_error_text(text, lang):
    assert "internet connection" in text.error_text("offline")
    assert "slow down" in text.error_text("rate_limited")
    assert text.error_text("something else") == text.error_text("bad_response")
    lang("id")
    assert "koneksi internet" in text.error_text("offline")


# ------------------------------------------------------------
# Pacing, cache, alerts, settings
# ------------------------------------------------------------

def test_rate_gate(api):
    gate = api.RateGate(min_gap=5, cooldown=60, max_backoff=600)
    assert gate.wait_time(100) == 0
    gate.started(100)
    assert gate.wait_time(101) == 4 and gate.wait_time(105) == 0
    gate.finished(101, None)
    assert gate.backoff(30) == 30 and gate.cooldown_left(101) == 0
    gate.finished(102, "offline")
    assert gate.backoff(30) == 60 and gate.cooldown_left(102) == 0
    gate.finished(103, "service")
    assert gate.backoff(30) == 120
    for _ in range(10):
        gate.finished(104, "offline")
    assert gate.backoff(30) == 600
    gate.finished(110, "rate_limited")
    assert gate.cooldown_left(120) == 50
    gate.reset()
    assert gate.backoff(30) == 30 and gate.cooldown_left(120) == 0


def test_cache_freshness(api, planes):
    cache = api.make_cache(JAKARTA, 14, planes, "adsb.fi", now=1000.0, wall=5.0)
    assert api.is_fresh(cache, 15, 1014) and not api.is_fresh(cache, 15, 1016)
    assert not api.is_fresh(cache, 15, 999)  # clock went backwards
    assert not api.is_fresh(None, 15, 1000)
    assert api.cache_matches(cache, JAKARTA, 14)
    assert not api.cache_matches(cache, JAKARTA, 27)
    assert not api.cache_matches(cache, dict(JAKARTA, latitude=1.0), 14)
    assert not api.cache_matches(None, JAKARTA, 14)


def test_alert_tracker(api, planes):
    tracker = api.AlertTracker(cooldown=600)
    first = tracker.check(planes, 5, now=0)
    assert [p["callsign"] for p in first] == ["CTV991"]      # 4.5 km; others are farther
    assert tracker.check(planes, 5, now=30) == []            # once per aircraft
    assert tracker.check(planes, 5, now=599) == []
    assert [p["callsign"] for p in tracker.check(planes, 5, now=600)] == ["CTV991"]
    # A wider alert distance picks up the others, but never ground traffic.
    wider = tracker.check(planes, 20, now=601)
    assert [p["callsign"] for p in wider] == ["XQZ357", "GIA155"]
    tracker.reset()
    assert len(tracker.check(planes, 20, now=602)) == 3


@pytest.mark.parametrize("raw", [
    None, "garbage", [], {}, {"location": "Jakarta"}, {"radius_km": 7}, {"radius_km": True},
    {"units": "imperial"}, {"include_ground": "yes"}, {"alerts": 1}, {"alert_km": 4},
    {"location": {"name": "X", "latitude": 95, "longitude": 1}},
])
def test_settings_survive_corrupt_data(api, raw):
    assert api.normalize_settings(raw) == {"location": None, "radius_km": 25, "units": "metric",
                                           "include_ground": False, "alerts": False,
                                           "alert_km": 5}


def test_settings_keep_valid_values(api):
    raw = {"location": dict(JAKARTA, timezone="Asia/Jakarta"), "radius_km": 50,
           "units": "aviation", "include_ground": True, "alerts": True, "alert_km": 2, "x": 1}
    assert api.normalize_settings(raw) == {"location": JAKARTA, "radius_km": 50,
                                           "units": "aviation", "include_ground": True,
                                           "alerts": True, "alert_km": 2}


# ------------------------------------------------------------
# Routes (adsbdb)
# ------------------------------------------------------------

def test_parse_route(routes):
    route = routes.parse_route(json.loads(json.dumps(ROUTE_JSON)))
    assert route["origin"]["municipality"] == "Batam" and route["origin"]["iata_code"] == "BTH"
    assert route["destination"]["municipality"] == "Jakarta"
    assert route["midpoint"] is None
    assert "airline" not in route  # adsbdb's airline name is never used
    assert routes.parse_route({"response": "unknown callsign"}) is None
    assert routes.parse_route(None) is None
    broken = json.loads(json.dumps(ROUTE_JSON))
    del broken["response"]["flightroute"]["destination"]["latitude"]
    assert routes.parse_route(broken) is None


def test_route_callsigns(routes):
    assert routes.route_callsign({"callsign": "GIA155"}) == "GIA155"
    assert routes.route_callsign({"callsign": "BTK6339"}) == "BTK6339"
    assert routes.route_callsign({"callsign": "PKQQA"}) is None
    assert routes.route_callsign({"callsign": "N123AB"}) is None
    assert routes.route_callsign({"callsign": ""}) is None
    assert routes.build_route_url("GIA155") == "https://api.adsbdb.com/v0/callsign/GIA155"


@pytest.mark.parametrize("lat, lon, plausible", [
    (-2.5, 105.4, True),      # between Batam and Jakarta
    (0.9, 104.2, True),       # just after take-off from Batam
    (-6.3, 106.9, True),      # near Jakarta, a little past the airport
    (-7.25, 112.75, False),   # over Surabaya
    (5.0, 102.0, False),      # far beyond Batam
    (-3.0, 110.0, False),     # far off to the side
])
def test_route_plausibility(routes, lat, lon, plausible):
    route = {"origin": BATAM, "destination": CGK, "midpoint": None}
    leg = routes.plausible_leg(route, lat, lon)
    assert (leg is not None) == plausible
    if plausible:
        assert leg == {"origin": BATAM, "destination": CGK}


def test_route_plausibility_needs_a_position(routes):
    route = {"origin": BATAM, "destination": CGK, "midpoint": None}
    assert routes.plausible_leg(route, None, None) is None
    assert routes.plausible_leg(None, -2.5, 105.4) is None


def test_route_with_a_midpoint_picks_the_leg_being_flown(routes):
    surabaya = {"municipality": "Surabaya", "name": "Juanda", "latitude": -7.3798,
                "longitude": 112.787}
    route = {"origin": BATAM, "midpoint": CGK, "destination": surabaya}
    assert routes.plausible_leg(route, -2.5, 105.4)["destination"] is CGK
    assert routes.plausible_leg(route, -6.8, 110.0)["origin"] is CGK


def test_route_lengths(routes):
    length, cross, along = routes.track_distances(BATAM, CGK, -2.5, 105.4)
    assert 850 < length < 900 and cross < 50 and 0 < along < length


class _Clock:
    def __init__(self, start=1000.0):
        self.now = start
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def _lookup(routes, api, answers, clock):
    calls = []

    def fetch(callsign):
        calls.append(callsign)
        answer = answers.get(callsign)
        if isinstance(answer, api.FlightError):
            raise answer
        return answer

    return routes.RouteLookup(fetch=fetch, clock=clock, sleep=clock.sleep), calls


def test_route_lookup_caches_in_memory(routes, api):
    clock = _Clock()
    route = routes.parse_route(ROUTE_JSON)
    lookup, calls = _lookup(routes, api, {"GIA155": route,
                                          "XQZ1": api.FlightError("service", status=404)}, clock)
    assert lookup.get("GIA155") == (False, None) and lookup.needs_lookup("GIA155")
    assert lookup.lookup("GIA155") is route
    assert lookup.lookup("GIA155") is route and calls == ["GIA155"]
    assert lookup.get("GIA155") == (True, route) and not lookup.needs_lookup("GIA155")
    # Unknown callsigns (404) are cached too.
    assert lookup.lookup("XQZ1") is None and lookup.get("XQZ1") == (True, None)
    lookup.lookup("XQZ1")
    assert calls == ["GIA155", "XQZ1"]
    # Requests were at least a second apart.
    assert clock.slept == [pytest.approx(1.0)]
    # After about an hour, looked up again.
    clock.now += routes.ROUTE_TTL_SECONDS
    assert lookup.get("GIA155") == (False, None)
    lookup.lookup("GIA155")
    assert calls == ["GIA155", "XQZ1", "GIA155"]


def test_route_lookup_backs_off_after_errors(routes, api):
    clock = _Clock()
    lookup, calls = _lookup(routes, api, {"GIA155": api.FlightError("offline"),
                                          "CTV991": None}, clock)
    assert lookup.lookup("GIA155") is None
    assert lookup.get("GIA155") == (False, None)       # an error is not a "no route"
    assert lookup.backing_off() and not lookup.needs_lookup("CTV991")
    lookup.lookup_many(["CTV991", "GIA155"])
    assert calls == ["GIA155"]                          # nothing sent while backing off
    clock.now += routes.ERROR_BACKOFF_SECONDS
    lookup.lookup("CTV991")
    assert calls == ["GIA155", "CTV991"]


def test_route_lookup_limits_its_size(routes, api):
    clock = _Clock()
    lookup = routes.RouteLookup(fetch=lambda cs: None, clock=clock, sleep=clock.sleep,
                                max_entries=3, min_gap=0)
    lookup.lookup_many(["AAA1", "AAA2", "AAA3", "AAA4"])
    assert len(lookup._entries) == 3 and lookup.get("AAA4")[0]


def test_fetch_route_uses_a_short_timeout(routes, api, monkeypatch):
    seen = {}

    def fake_fetch_json(url, timeout=None):
        seen.update(url=url, timeout=timeout)
        return json.loads(json.dumps(ROUTE_JSON))

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    assert routes.fetch_route("GIA155")["origin"]["municipality"] == "Batam"
    assert seen == {"url": "https://api.adsbdb.com/v0/callsign/GIA155",
                    "timeout": routes.ROUTE_TIMEOUT_SECONDS}


# ------------------------------------------------------------
# Actions (main.py)
# ------------------------------------------------------------

class _Timer:
    def __init__(self, seconds, callback):
        self.seconds, self.callback, self.stopped = seconds, callback, False

    def Stop(self):
        self.stopped = True

    def fire(self):
        if not self.stopped:
            self.stopped = True
            self.callback()


@pytest.fixture
def frmain(monkeypatch, tmp_data_dir, api, text, routes):
    """main.py with speech captured, threads run inline, timers recorded and a
    controllable monotonic clock."""
    spec = importlib.util.spec_from_file_location("flight_radar_main_under_test",
                                                  os.path.join(FR_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = _Clock(start=10000.0)
    spoken, timers, sounds = [], [], []
    monkeypatch.setattr(module, "speak", lambda msg, interrupt=False: spoken.append(msg))
    monkeypatch.setattr(module, "_start_thread", lambda target, *args: target(*args))
    monkeypatch.setattr(module, "_now", clock)

    def call_later(seconds, callback):
        timers.append(_Timer(seconds, callback))
        return timers[-1]

    monkeypatch.setattr(module, "_call_later", call_later)
    monkeypatch.setattr(module, "_play_alert_sound", lambda: sounds.append(module.ALERT_SOUND))
    module._routes = routes.RouteLookup(fetch=lambda cs: None, clock=clock, sleep=clock.sleep)
    module._active = True
    module.spoken, module.timers, module.clock, module.sounds = spoken, timers, clock, sounds
    yield module
    module._active = False


def _set(frmain, api, **settings):
    frmain._settings = api.normalize_settings(dict({"location": JAKARTA}, **settings))


def test_no_location_speaks_where_to_set_it(frmain, api, lang, monkeypatch):
    _set(frmain, api, location=None)

    def no_dialog(*args, **kwargs):
        raise AssertionError("the list must not open without a location")

    monkeypatch.setattr(frmain.flight_radar_ui, "RadarListDialog", no_dialog)
    calls = _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    frmain.speak_nearby()
    frmain.show_list()
    hint = "No flight radar location is set. Choose your city in Preferences, Flight Radar."
    assert frmain.spoken == [hint, hint] and calls == []
    assert frmain.refresh() is False
    lang("id")
    frmain.speak_nearby()
    assert frmain.spoken[-1] == ("Lokasi radar pesawat belum diatur. "
                                 "Pilih kota Anda di Pengaturan, Radar Pesawat.")


def test_weather_city_is_the_default(frmain, api, lang, monkeypatch):
    import core.api
    core.api.save_data("Weather", {"location": dict(JAKARTA, name="Bandung", latitude=-6.9,
                                                    longitude=107.6), "units": "metric"})
    _set(frmain, api, location=None)
    assert frmain.get_location()["name"] == "Bandung"
    calls = _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    frmain.speak_nearby()
    assert calls == ["https://opendata.adsb.fi/api/v2/lat/-6.9000/lon/107.6000/dist/14"]
    # A radar city of its own wins.
    _set(frmain, api)
    assert frmain.get_location()["name"] == "Jakarta"


def test_nearby_fetches_then_speaks(frmain, api, lang, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    _set(frmain, api)
    frmain.speak_nearby()
    assert calls == ["https://opendata.adsb.fi/api/v2/lat/-6.2000/lon/106.8000/dist/14"]
    assert frmain.spoken[0] == "Checking the radar..."
    assert frmain.spoken[1] == (
        "Citilink 991, Airbus A320, 4.5 kilometres south, 1,500 metres, climbing. "
        "X Q Z 357, Diamond DA-62, 11 kilometres east, 600 metres, level. "
        "Garuda Indonesia 155, Boeing 737-800, 12 kilometres northeast, 3,000 metres, descending.")
    # Within 15 seconds the answer comes from the cache.
    frmain.clock.now += 10
    frmain.speak_nearby()
    assert len(calls) == 1 and frmain.spoken[-1] == frmain.spoken[1]
    frmain.clock.now += 10
    frmain.speak_nearby()
    assert len(calls) == 2


def test_nearby_uses_the_fallback_source(frmain, api, lang, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi="rate_limited", lol=ADSBLOL_JSON)
    _set(frmain, api)
    frmain.speak_nearby()
    assert len(calls) == 2 and frmain._cache["source"] == "adsb.lol"
    assert frmain.spoken[-1].startswith("Citilink 991")


def test_ground_traffic_follows_the_setting(frmain, api, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi={"aircraft": [PLANES[2]]})
    _set(frmain, api)
    frmain.speak_nearby()
    assert frmain.spoken[-1] == "No aircraft in the air within 25 kilometres right now."
    _set(frmain, api, include_ground=True)
    frmain.speak_nearby()
    assert frmain.spoken[-1].endswith("20 kilometres west, on the ground.")


def test_requests_are_spaced_and_single(frmain, api, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi="offline", lol="offline")
    _set(frmain, api)
    done = []
    assert frmain.refresh(done.append)
    assert len(calls) == 2 and done == ["offline"]
    # Right after a request, the next one waits for the 5-second gap.
    assert frmain.refresh(done.append) and frmain.refresh(done.append)
    assert len(calls) == 2 and len(frmain.timers) == 1
    assert 0 < frmain.timers[0].seconds <= api.MIN_GAP_SECONDS
    assert frmain._waiters == [done.append]
    frmain.clock.now += frmain.timers[0].seconds
    frmain.timers[0].fire()
    assert len(calls) == 4 and done == ["offline", "offline"]


def test_one_fetch_in_flight(frmain, api, monkeypatch):
    started = []
    monkeypatch.setattr(frmain, "_start_thread", lambda target, *args: started.append(args))
    _set(frmain, api)
    done = []
    assert frmain.refresh(done.append)
    assert frmain.refresh(done.append) and frmain.refresh()
    assert len(started) == 1 and len(frmain._waiters) == 1
    frmain._on_fetched(dict(JAKARTA), 14, [], "adsb.fi", "offline", 0)
    assert done == ["offline"] and not frmain._loading


def test_rate_limited_answers_cool_down(frmain, api, lang, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi="rate_limited", lol="rate_limited")
    _set(frmain, api)
    frmain.speak_nearby()
    assert len(calls) == 2 and "slow down" in frmain.spoken[-1]
    frmain.clock.now += 20
    frmain.speak_nearby()
    assert len(calls) == 2 and "slow down" in frmain.spoken[-1]   # nothing sent
    frmain.clock.now += 45
    frmain.speak_nearby()
    assert len(calls) == 4


def test_failure_offers_the_last_result(frmain, api, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    _set(frmain, api)
    frmain.speak_nearby()
    _fake_sources(monkeypatch, api, fi="offline", lol="offline")
    frmain.clock.now += 30
    frmain.speak_nearby()
    last = frmain.spoken[-1]
    assert last.startswith("Could not reach the flight data service.")
    assert "Showing the radar from" in last and "Citilink 991" in last
    frmain.clock.now += frmain.STALE_MAX_AGE
    frmain.speak_nearby()
    assert frmain.spoken[-1] == ("Could not reach the flight data service. "
                                 "Check your internet connection.")


def test_nearby_waits_for_routes(frmain, api, routes, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    lookups = []
    route = routes.parse_route(ROUTE_JSON)

    def fetch(callsign):
        lookups.append(callsign)
        return route if callsign == "GIA155" else None

    frmain._routes = routes.RouteLookup(fetch=fetch, clock=frmain.clock, sleep=frmain.clock.sleep)
    _set(frmain, api)
    frmain.speak_nearby()
    # Only the three aircraft spoken (all have airline-style callsigns).
    assert lookups == ["CTV991", "XQZ357", "GIA155"]
    # GIA155 is 12 km northeast of Jakarta: on the Batam route, so it is spoken.
    assert "Garuda Indonesia 155, from Batam to Jakarta, Boeing 737-800" in frmain.spoken[-1]
    assert "Citilink 991, Airbus A320" in frmain.spoken[-1]
    # The route-wait timer was cancelled once the lookups finished.
    assert all(t.stopped for t in frmain.timers)
    frmain.clock.now += 20
    frmain.speak_nearby()
    assert lookups == ["CTV991", "XQZ357", "GIA155"]  # cached in memory


def test_implausible_routes_are_not_spoken(frmain, api, routes, lang, monkeypatch):
    far = {"aircraft": [_plane(lat=-7.25, lon=112.75)]}  # over Surabaya, route says BTH-CGK
    _fake_sources(monkeypatch, api, fi=far)
    frmain._routes = routes.RouteLookup(fetch=lambda cs: routes.parse_route(ROUTE_JSON),
                                        clock=frmain.clock, sleep=frmain.clock.sleep)
    _set(frmain, api)
    frmain.speak_nearby()
    assert frmain.spoken[-1].startswith("Garuda Indonesia 155, Boeing 737-800")


def test_slow_routes_do_not_hold_up_speech(frmain, api, routes, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    _set(frmain, api)
    pending = []
    monkeypatch.setattr(frmain, "_start_thread",
                        lambda target, *args: pending.append((target, args))
                        if target is frmain._route_worker else target(*args))
    frmain.speak_nearby()
    assert frmain.spoken == ["Checking the radar..."]
    wait = [t for t in frmain.timers if t.seconds == frmain.ROUTE_WAIT_SECONDS]
    assert len(wait) == 1
    wait[0].fire()                      # three seconds passed without an answer
    assert frmain.spoken[-1].startswith("Citilink 991, Airbus A320")
    target, args = pending[0]
    target(*args)                       # the late answer does not speak again
    assert len(frmain.spoken) == 2


def test_routes_are_never_written_to_disk(frmain, api, routes, lang, monkeypatch, tmp_data_dir):
    _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    frmain._routes = routes.RouteLookup(fetch=lambda cs: routes.parse_route(ROUTE_JSON),
                                        clock=frmain.clock, sleep=frmain.clock.sleep)
    frmain._save_settings({"location": JAKARTA, "alerts": True})
    frmain.speak_nearby()
    assert "from Batam to Jakarta" in frmain.spoken[-1]
    for name in os.listdir(tmp_data_dir):
        with open(os.path.join(tmp_data_dir, name), encoding="utf-8") as f:
            content = f.read()
        assert "Batam" not in content and "GIA155" not in content and "aircraft" not in content
    assert os.listdir(tmp_data_dir) == ["FlightRadar.json"]


def _poll_timers(frmain):
    return [t for t in frmain.timers if t.callback == frmain._poll and not t.stopped]


def test_alerts_announce_once_per_aircraft(frmain, api, lang, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    _set(frmain, api)
    frmain._update_polling()
    assert _poll_timers(frmain) == []       # alerts are off by default
    _set(frmain, api, alerts=True)
    frmain._update_polling()
    [timer] = _poll_timers(frmain)
    assert timer.seconds == frmain.FIRST_POLL_SECONDS
    timer.fire()
    assert len(calls) == 1 and frmain.sounds == ["info.wav"]
    assert frmain.spoken == [
        "Overhead: Citilink 991, Airbus A320, 4.5 kilometres south, 1,500 metres, climbing."]
    [timer] = _poll_timers(frmain)
    assert timer.seconds == frmain.POLL_SECONDS
    for _ in range(3):
        frmain.clock.now += frmain.POLL_SECONDS
        _poll_timers(frmain)[0].fire()
    assert len(calls) == 4 and len(frmain.spoken) == 1   # not again within 10 minutes
    frmain.clock.now += frmain.ALERT_COOLDOWN
    _poll_timers(frmain)[0].fire()
    assert len(frmain.spoken) == 2 and frmain.sounds == ["info.wav", "info.wav"]


def test_alert_distance_setting(frmain, api, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    _set(frmain, api, alerts=True, alert_km=2)
    frmain._update_polling()
    _poll_timers(frmain)[0].fire()
    assert frmain.spoken == [] and frmain.sounds == []


def test_polling_backs_off_and_stops(frmain, api, lang, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi="offline", lol="offline")
    _set(frmain, api, alerts=True)
    frmain._update_polling()
    delays = []
    for _ in range(4):
        timer = _poll_timers(frmain)[0]
        frmain.clock.now += timer.seconds
        timer.fire()
        delays.append(_poll_timers(frmain)[0].seconds)
    assert delays == [60, 120, 240, 480] and len(calls) == 8
    assert frmain.spoken == []              # background failures stay quiet
    # Back online: the next poll comes soon.
    frmain._on_network_changed(True)
    assert _poll_timers(frmain)[0].seconds == frmain.FIRST_POLL_SECONDS
    # Alerts off: polling stops.
    frmain._save_settings(dict(frmain._settings, alerts=False))
    assert _poll_timers(frmain) == []


def test_changing_settings_saves_them(frmain, api, monkeypatch):
    import core.api
    _set(frmain, api, location=None)
    frmain._save_settings({"location": JAKARTA, "radius_km": 50, "units": "aviation",
                           "include_ground": True, "alerts": True, "alert_km": 3})
    saved = core.api.load_data(frmain.DATA_KEY)
    assert saved["location"]["name"] == "Jakarta" and saved["radius_km"] == 50
    assert saved["units"] == "aviation" and saved["alerts"] is True and saved["alert_km"] == 3
    assert frmain.query_radius_nm() == 27
    assert len(_poll_timers(frmain)) == 1


def test_register_and_teardown(frmain, fresh_event_bus, monkeypatch, tmp_data_dir):
    import core.api
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *args, **kwargs: panels.append(args))
    with open(core.api.get_data_path(frmain.DATA_KEY), "w", encoding="utf-8") as f:
        f.write("{not json")

    frmain.register(fresh_event_bus)
    assert frmain.get_location() is None and frmain._settings["alerts"] is False
    for event_name, handler in frmain._SUBSCRIPTIONS:
        assert handler in fresh_event_bus._listeners[event_name]
    by_name = {args[1]: (args, kwargs) for args, kwargs in actions}
    nearby_args, nearby_kwargs = by_name["speak_nearby"]
    assert nearby_args[0] == "Flight Radar" and nearby_args[3] == ord("P")
    assert nearby_args[4] is False and nearby_kwargs == {}
    list_args, list_kwargs = by_name["show_list"]
    assert list_args[0] == "Flight Radar" and list_args[3] == ord("P")
    assert list_kwargs == {"default_shift": True}
    assert len(panels) == 1 and panels[0][0] == "Flight Radar"

    frmain._settings = dict(frmain._settings, location=JAKARTA, alerts=True)
    frmain._update_polling()
    timer = frmain._poll_timer
    frmain.teardown()
    assert timer.stopped and frmain._poll_timer is None
    for event_name, handler in frmain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    assert not frmain._active and frmain.refresh() is False
