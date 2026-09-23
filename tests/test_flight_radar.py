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
# emergencies, adsbdb routes, the airport table, Listen to ATC, exact locations
# (pasted coordinates, map links, address search, privacy rounding) and the
# actions.
# No test touches the network or opens a browser: the fetch functions and the
# browser call are replaced. All aircraft samples are synthetic.

import importlib.util
import json
import math
import os
import sys
import urllib.error

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FR_DIR = os.path.join(ROOT, "extensions", "flight_radar")

JAKARTA = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
           "latitude": -6.2, "longitude": 106.8}
HOME = (JAKARTA["latitude"], JAKARTA["longitude"])


def _at(km, bearing, origin=HOME):
    """{"lat", "lon"} of the point `km` away from `origin` on `bearing` (sphere)."""
    d = km / 6371.0
    lat1, lon1, b = math.radians(origin[0]), math.radians(origin[1]), math.radians(bearing)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(b))
    lon2 = lon1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(lat1),
                             math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return {"lat": math.degrees(lat2), "lon": math.degrees(lon2)}


def _plane(**overrides):
    # dst/dir are what the services send, relative to the rounded point: ignored.
    plane = {"hex": "abc001", "flight": "GIA155  ", "r": "PK-QQA", "t": "B738",
             "alt_baro": 9843, "gs": 250.0, "track": 315.0, "baro_rate": -832,
             "dst": 6.48, "dir": 45.0, "squawk": "2345", "emergency": "none",
             "category": "A3", "seen": 0.4, **_at(12, 45)}
    plane.update(overrides)
    return {k: v for k, v in plane.items() if v is not None}


def _normalize(api, raw):
    return api.normalize_aircraft(raw, *HOME)


# 12 km northeast, descending; 4.5 km south, climbing; on the ground at 20 km;
# an unknown airline without distance (computed from its position, 11 km east);
# one without any identity and one that is not an object (both dropped).
PLANES = [
    _plane(),
    _plane(hex="abc002", flight="CTV991", r="PK-QQB", t="A320", alt_baro=4921, gs=180,
           track=0, baro_rate=1500, dst=2.43, dir=180.0, squawk="1200", **_at(4.5, 180)),
    _plane(hex="abc003", flight="AWQ531", r="PK-QQC", t="A20N", alt_baro="ground", gs=3,
           baro_rate=None, dst=10.8, dir=270.0, squawk=None, **_at(20, 270)),
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
    import flight_radar_airports
    import flight_radar_api
    import flight_radar_atc
    import flight_radar_names
    import flight_radar_routes
    import flight_radar_text
    return (flight_radar_api, flight_radar_text, flight_radar_names, flight_radar_routes,
            flight_radar_airports, flight_radar_atc)


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


@pytest.fixture(scope="module")
def airports():
    return _import_helpers()[4]


@pytest.fixture(scope="module")
def atc():
    return _import_helpers()[5]


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
    assert gia["emergency"] == "" and gia["bearing"] == pytest.approx(45)
    assert gia["distance_km"] == pytest.approx(12.0, abs=0.01)
    ground = planes[2]
    assert ground["on_ground"] and ground["altitude_ft"] is None
    # Worked out from its own position, about 11 km east.
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
        api.parse_aircraft_list(payload, *HOME)
    assert info.value.kind == "bad_response"


def test_aircraft_without_a_position_are_dropped(api):
    # The services' own distance is from the rounded point, so it is not enough.
    assert api.parse_aircraft_list({"aircraft": [_plane(lat=None, lon=None)]}, *HOME) == []
    assert api.parse_aircraft_list({"aircraft": [_plane(lat=95.0)]}, *HOME) == []
    assert api.parse_aircraft_list({"aircraft": [_plane()]}, None, None) == []


def test_distance_comes_from_the_exact_point_not_the_service(api):
    plane = _normalize(api, _plane(dst=100.0, dir=270.0, **_at(3.2, 200)))
    assert plane["distance_km"] == pytest.approx(3.2, abs=0.001)
    assert plane["bearing"] == pytest.approx(200, abs=0.01)


def test_surface_vehicles_count_as_ground(api):
    plane = _normalize(api, _plane(category="C2", alt_baro=0))
    assert plane["on_ground"]


def test_request_urls(api):
    # Never more than 2 decimals (about 1.1 km), whatever the caller passes.
    assert api.build_adsbfi_url(-6.214621, 106.84513, 14) == (
        "https://opendata.adsb.fi/api/v2/lat/-6.21/lon/106.85/dist/14")
    assert api.build_adsblol_url(-6.214621, 106.84513, 14) == (
        "https://api.adsb.lol/v2/point/-6.21/106.85/14")
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
    assert calls == ["https://opendata.adsb.fi/api/v2/lat/-6.20/lon/106.80/dist/14"]


def test_adsblol_is_the_fallback(api, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi="service", lol=ADSBLOL_JSON)
    aircraft, source = api.fetch_aircraft(-6.2, 106.8, 14)
    assert source == "adsb.lol" and len(aircraft) == 2
    assert calls[1] == "https://api.adsb.lol/v2/point/-6.20/106.80/14"

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
    # Widened by 1 nm so the rounded point still covers the radius (see below).
    assert [api.query_radius_nm(km) for km in api.RADIUS_CHOICES_KM] == [7, 15, 28]


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
    plane = _normalize(api, {"hex": "abc009", **_at(1.852, 180)})
    assert text.aircraft_sentence(plane, "metric") == "Unidentified aircraft, 1.9 kilometres south."


@pytest.mark.parametrize("squawk, status, emergency", [
    ("7700", "none", True), ("7600", "", True), ("7500", "none", True),
    ("2345", "general", True), ("2345", "minfuel", True), ("2345", "nordo", True),
    ("2345", "unlawful", True), ("2345", "downed", True),
    ("2345", "lifeguard", False), ("2345", "reserved", False), ("2345", "none", False),
    ("7000", "none", False), ("", "", False),
])
def test_what_counts_as_an_emergency(api, squawk, status, emergency):
    plane = _normalize(api, _plane(squawk=squawk or None, emergency=status or None))
    assert api.is_emergency(plane) is emergency
    assert (api.emergencies([plane]) == [plane]) is emergency


def test_emergency_rows_are_marked(text, lang, api):
    plane = _normalize(api, _plane(squawk="7700"))
    assert text.aircraft_sentence(plane, "metric") == (
        "Emergency: Garuda Indonesia 155, Boeing 737-800, 12 kilometres northeast, "
        "3,000 metres, descending.")
    lifeguard = _normalize(api, _plane(emergency="lifeguard"))
    assert text.aircraft_sentence(lifeguard, "metric").startswith("Garuda Indonesia 155")
    lang("id")
    assert text.aircraft_sentence(plane, "metric").startswith("Darurat: Garuda Indonesia 155,")


def test_emergency_text(text, lang, api):
    plane = _normalize(api, _plane(squawk="7700", **_at(20, 270)))
    assert text.emergency_text([plane], "metric") == (
        "Attention: Garuda Indonesia 155 is squawking 7 7 0 0, general emergency, "
        "20 kilometres west.")
    hijack = _normalize(api, _plane(squawk="7500"))
    assert text.emergency_text([hijack], "metric") == (
        "Attention: Garuda Indonesia 155 is squawking 7 5 0 0, unlawful interference "
        "(hijack code), 12 kilometres northeast.")
    fuel = _normalize(api, _plane(emergency="minfuel", alt_baro="ground"))
    assert text.emergency_text([fuel], "metric") == (
        "Attention: Garuda Indonesia 155 reports low fuel, 12 kilometres northeast, "
        "on the ground.")
    both = _normalize(api, _plane(squawk="7600", emergency="minfuel"))
    assert "is squawking 7 6 0 0, radio failure (lost communications), and reports low fuel," \
        in text.emergency_text([both], "metric")
    same = _normalize(api, _plane(squawk="7700", emergency="general"))
    assert "reports" not in text.emergency_text([same], "metric")
    normal = _normalize(api, _plane(emergency="lifeguard"))
    assert text.emergency_text([normal], "metric") == ""
    assert text.emergency_text([plane, hijack], "metric").count("Attention:") == 2
    lang("id")
    assert text.emergency_text([plane], "metric") == (
        "Perhatian: Garuda Indonesia 155 memancarkan kode squawk 7 7 0 0, keadaan darurat umum, "
        "20 kilometer di sebelah barat.")
    assert "melaporkan bahan bakar menipis" in text.emergency_text([fuel], "metric")


@pytest.mark.parametrize("code, en, id_", [
    ("7700", "general emergency", "keadaan darurat umum"),
    ("7600", "radio failure (lost communications)", "gangguan radio (komunikasi terputus)"),
    ("7500", "unlawful interference (hijack code)", "gangguan melawan hukum (kode pembajakan)"),
    ("2000", "no code assigned yet (usually when entering controlled airspace)",
     "belum diberi kode (biasanya saat memasuki wilayah udara terkendali)"),
    ("7000", "visual flight, no code assigned (used in many countries)",
     "penerbangan visual tanpa kode khusus (dipakai di banyak negara)"),
    ("1200", "visual flight, no code assigned (used in the US and Canada)",
     "penerbangan visual tanpa kode khusus (dipakai di Amerika Serikat dan Kanada)"),
    ("4521", "a code assigned by air traffic control to identify this flight",
     "kode dari pengatur lalu lintas udara untuk mengenali penerbangan ini"),
])
def test_squawk_meanings(text, lang, code, en, id_):
    assert text.squawk_meaning(code) == en
    lang("id")
    assert text.squawk_meaning(code) == id_


@pytest.mark.parametrize("status, en", [
    ("general", "general emergency"), ("lifeguard", "medical or priority flight"),
    ("minfuel", "low fuel"), ("nordo", "radio failure"), ("downed", "aircraft down"),
    ("unlawful", "unlawful interference"), ("reserved", None), ("", None), (None, None),
])
def test_status_meanings(text, lang, status, en):
    assert text.status_meaning(status) == en
    if en:
        lang("id")
        assert text.status_meaning(status) not in (None, en)


def test_details_explain_the_squawk_and_status(text, lang, api):
    plane = _normalize(api, _plane(squawk="7000", emergency="lifeguard"))
    details = text.details_text(plane, "metric")
    assert ("Squawk 7 0 0 0, visual flight, no code assigned (used in many countries). "
            "Reported status: medical or priority flight.") in details
    plane = _normalize(api, _plane(squawk="7700", emergency="general"))
    details = text.details_text(plane, "metric")
    assert "Squawk 7 7 0 0, general emergency." in details and "Reported status" not in details
    plane = _normalize(api, _plane(squawk="2000", emergency="minfuel"))
    assert "Reported status: low fuel." in text.details_text(plane, "metric")
    plane = _normalize(api, _plane(squawk=None, emergency="reserved"))
    details = text.details_text(plane, "metric")
    assert "Squawk" not in details and "status" not in details


def test_nearby_report(text, lang, api, planes):
    extra = [_normalize(api, _plane(hex=f"abd{i}", flight=f"LNI{i}0", **_at(18 + i, 90)))
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
        "Squawk 2 3 4 5, a code assigned by air traffic control to identify this flight. "
        "Listen to ATC opens Jakarta Soekarno-Hatta.")
    assert "Speed 250 knots." in text.details_text(gia, "aviation")
    assert "Descending 800 feet per minute." in text.details_text(gia, "aviation")
    leg = {"origin": BATAM, "destination": CGK}
    assert text.details_text(gia, "metric", leg).startswith(
        "Garuda Indonesia 155, from Batam to Jakarta. Registration")
    lang("id")
    assert text.details_text(gia, "metric") == (
        "Garuda Indonesia 155. Registrasi P K Q Q A. Tipe Boeing 737-800. "
        "Kecepatan 460 kilometer per jam. Menuju arah barat laut. Turun 250 meter per menit. "
        "Squawk 2 3 4 5, kode dari pengatur lalu lintas udara untuk mengenali penerbangan ini. "
        "Dengarkan ATC akan membuka Jakarta Soekarno-Hatta.")


def test_details_with_nothing_known(text, lang, api):
    plane = _normalize(api, {"hex": "abc009", **_at(1.852, 180)})
    assert text.details_text(plane, "metric") == (
        "Unidentified aircraft. No other details available. "
        "Listen to ATC opens Jakarta Soekarno-Hatta.")


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


def test_emergency_tracker(api):
    mayday = _normalize(api, _plane(squawk="7700"))
    quiet = _normalize(api, _plane(hex="abc009", squawk="2345"))
    tracker = api.EmergencyTracker(cooldown=1800)
    assert tracker.check([quiet, mayday], now=0) == [mayday]
    assert tracker.check([quiet, mayday], now=60) == []          # once
    assert tracker.check([mayday], now=1799) == []
    assert tracker.check([mayday], now=1800) == [mayday]         # 30 minutes later
    # A different emergency on the same aircraft is new.
    radio = dict(mayday, squawk="7600")
    assert tracker.check([radio], now=1801) == [radio]
    # Emergencies the user already heard are not repeated.
    fuel = _normalize(api, _plane(hex="abc010", emergency="minfuel"))
    tracker.mark([fuel, quiet], now=1802)
    assert tracker.check([fuel], now=1803) == []
    tracker.reset()
    assert tracker.check([fuel], now=1804) == [fuel]


@pytest.mark.parametrize("raw", [
    None, "garbage", [], {}, {"location": "Jakarta"}, {"radius_km": 7}, {"radius_km": True},
    {"units": "imperial"}, {"include_ground": "yes"}, {"alerts": 1}, {"alert_km": 4},
    {"location": {"name": "X", "latitude": 95, "longitude": 1}}, {"emergency_watch": "on"},
])
def test_settings_survive_corrupt_data(api, raw):
    assert api.normalize_settings(raw) == {"location": None, "radius_km": 25, "units": "metric",
                                           "include_ground": False, "alerts": False,
                                           "alert_km": 5, "emergency_watch": False}


def test_settings_keep_valid_values(api):
    raw = {"location": dict(JAKARTA, timezone="Asia/Jakarta"), "radius_km": 50,
           "units": "aviation", "include_ground": True, "alerts": True, "alert_km": 2,
           "emergency_watch": True, "x": 1}
    assert api.normalize_settings(raw) == {"location": JAKARTA, "radius_km": 50,
                                           "units": "aviation", "include_ground": True,
                                           "alerts": True, "alert_km": 2,
                                           "emergency_watch": True}


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
# Airports and Listen to ATC
# ------------------------------------------------------------

def test_airport_table(airports):
    codes = [row[0] for row in airports.AIRPORTS]
    assert len(codes) == len(set(codes)) >= 100
    assert all(len(c) == 4 and c.isalnum() and c.isupper() for c in codes)
    indonesian = [c for c in codes if c.startswith("WA") or c.startswith("WI")]
    assert len(indonesian) >= 70
    for code in ("WIII", "WARR", "WADD", "WIMM", "WAAA", "WSSS", "WMKK", "VTBS", "RPLL",
                 "YPPH", "YPDN"):
        assert code in codes, code
    for icao, city, name, lat, lon in airports.AIRPORTS:
        assert name and -40 < lat < 20 and 90 < lon < 150, icao


def test_airport_names(airports):
    assert airports.label(airports.by_icao("WIII")) == "Jakarta Soekarno-Hatta"
    assert airports.label(airports.by_icao("wsss")) == "Singapore Changi"
    assert airports.label(airports.by_icao("WARR")) == "Surabaya Juanda"
    assert airports.label(airports.by_icao("YPDN")) == "Darwin"
    assert airports.by_icao("ZZZZ") is None
    assert airports.short_name("Soekarno-Hatta International Airport") == "Soekarno-Hatta"
    assert airports.short_name("Juwata International Airport / Suharnoko Harbani AFB") == "Juwata"
    assert airports.label({"city": "Batam", "name": ""}) == "Batam"


def test_nearest_airport(airports):
    near = airports.nearest(-6.9, 107.6)
    assert near["icao"] == "WICC" and near["distance_km"] < 10
    assert airports.nearest(48.85, 2.35, max_km=500) is None        # Paris
    assert airports.nearest(-6.2, 106.85, among={"WARR"})["icao"] == "WARR"


def test_liveatc_urls(atc):
    assert atc.liveatc_url("WIII") == ("https://www.liveatc.net/hlisten.php?mount=wiii", True)
    assert atc.liveatc_url("warr") == ("https://www.liveatc.net/hlisten.php?mount=warr", True)
    assert atc.liveatc_url("WICC") == ("https://www.liveatc.net/search/?icao=WICC", False)
    assert atc.liveatc_url("") == (None, False)
    assert atc.liveatc_url("WI I/") == (None, False)


def test_nearest_prefers_a_known_feed(atc):
    # Central Jakarta: Halim is nearer, but Soekarno-Hatta has a LiveATC feed.
    assert atc.nearest_airport(-6.2, 106.85)["icao"] == "WIII"
    assert atc.nearest_airport(-6.9, 107.6)["icao"] == "WICC"      # Bandung: no feed nearby
    assert atc.nearest_airport(-7.3, 112.7)["icao"] == "WARR"
    assert atc.nearest_airport(48.85, 2.35) is None
    assert atc.nearest_airport(None, None) is None


def _atc_plane(api, rate, lat=-3.0, lon=105.5):
    return _normalize(api, _plane(baro_rate=rate, lat=lat, lon=lon))


def test_atc_airport_for_aircraft(atc, api):
    leg = {"origin": BATAM, "destination": CGK}
    assert atc.airport_for_aircraft(_atc_plane(api, -1200), leg)["icao"] == "WIII"   # descending
    assert atc.airport_for_aircraft(_atc_plane(api, 1500), leg)["icao"] == "WIDD"    # climbing
    # Level (or unknown rate): the nearer end of the route.
    assert atc.airport_for_aircraft(_atc_plane(api, 0, lat=0.0, lon=104.5), leg)["icao"] == "WIDD"
    assert atc.airport_for_aircraft(_atc_plane(api, None, lat=-5.5, lon=106.3), leg)["icao"] == "WIII"
    # No plausible route: the airport nearest to the aircraft.
    assert atc.airport_for_aircraft(_atc_plane(api, -1200, lat=-6.95, lon=107.55))["icao"] == "WICC"
    # A route end without an ICAO code falls back to the other end or the nearest airport.
    no_code = {"origin": dict(BATAM, icao_code=""), "destination": CGK}
    assert atc.airport_for_aircraft(_atc_plane(api, 1500), no_code)["icao"] == "WIII"
    # An airport Hariku does not list keeps adsbdb's name.
    far = {"municipality": "Tokyo", "name": "Tokyo Haneda International Airport",
           "icao_code": "RJTT", "latitude": 35.55, "longitude": 139.78}
    airport = atc.airport_for_aircraft(_atc_plane(api, -1500), {"origin": CGK, "destination": far})
    assert airport["icao"] == "RJTT" and airport["name"] == "Tokyo Haneda"


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
    monkeypatch.setattr(module, "_play_sound", sounds.append)
    opened = []
    monkeypatch.setattr(module, "_open_url", opened.append)
    module._routes = routes.RouteLookup(fetch=lambda cs: None, clock=clock, sleep=clock.sleep)
    module._active = True
    module.spoken, module.timers, module.clock, module.sounds = spoken, timers, clock, sounds
    module.opened = opened
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
    assert calls == ["https://opendata.adsb.fi/api/v2/lat/-6.90/lon/107.60/dist/15"]
    # A radar city of its own wins.
    _set(frmain, api)
    assert frmain.get_location()["name"] == "Jakarta"


def test_nearby_fetches_then_speaks(frmain, api, lang, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    _set(frmain, api)
    frmain.speak_nearby()
    assert calls == ["https://opendata.adsb.fi/api/v2/lat/-6.20/lon/106.80/dist/15"]
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
    # Over Jakarta, but adsbdb says Surabaya to Makassar: a stale route.
    _fake_sources(monkeypatch, api, fi={"aircraft": [_plane()]})
    stale = json.loads(json.dumps(ROUTE_JSON))
    stale["response"]["flightroute"]["origin"].update(latitude=-7.3798, longitude=112.787)
    stale["response"]["flightroute"]["destination"].update(latitude=-5.0755, longitude=119.5537)
    frmain._routes = routes.RouteLookup(fetch=lambda cs: routes.parse_route(stale),
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


EMERGENCY_PLANE = _plane(hex="abc007", flight="XQZ777", r="PK-QQG", squawk="7700",
                         **_at(20, 270))
EMERGENCY_JSON = {"aircraft": PLANES[:4] + [EMERGENCY_PLANE]}
MAYDAY = ("Attention: X Q Z 777 is squawking 7 7 0 0, general emergency, "
          "20 kilometres west.")


def test_nearby_speaks_emergencies_first(frmain, api, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi=EMERGENCY_JSON)
    _set(frmain, api)
    frmain.speak_nearby()
    said = frmain.spoken[-1]
    assert said.startswith(MAYDAY + " Citilink 991, Airbus A320"), said
    assert said.endswith("And 1 more within 25 kilometres.")
    # The emergency watch does not repeat what the user has just heard.
    _set(frmain, api, emergency_watch=True)
    frmain._update_polling()
    _poll_timers(frmain)[0].fire()
    assert len(frmain.spoken) == 2 and frmain.sounds == []
    assert _poll_timers(frmain)[0].seconds == frmain.EMERGENCY_POLL_SECONDS
    lang("id")
    frmain.speak_nearby()
    assert frmain.spoken[-1].startswith("Perhatian: X Q Z 777 memancarkan kode squawk 7 7 0 0")


def test_emergency_watch_announces_in_the_background(frmain, api, lang, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi=EMERGENCY_JSON)
    _set(frmain, api)
    frmain._update_polling()
    assert _poll_timers(frmain) == []                    # off by default
    _set(frmain, api, emergency_watch=True)
    frmain._update_polling()
    [timer] = _poll_timers(frmain)
    assert timer.seconds == frmain.FIRST_POLL_SECONDS
    timer.fire()
    assert len(calls) == 1 and frmain.spoken == [MAYDAY] and frmain.sounds == ["error.wav"]
    # Overhead alerts are off: CTV991 at 4.5 km is not announced.
    [timer] = _poll_timers(frmain)
    assert timer.seconds == frmain.EMERGENCY_POLL_SECONDS
    for _ in range(3):
        frmain.clock.now += frmain.EMERGENCY_POLL_SECONDS
        _poll_timers(frmain)[0].fire()
    assert len(calls) == 4 and frmain.spoken == [MAYDAY]  # once per 30 minutes
    # A new emergency code on the same aircraft is announced straight away.
    radio = {"aircraft": PLANES[:4] + [dict(EMERGENCY_PLANE, squawk="7600")]}
    _fake_sources(monkeypatch, api, fi=radio)
    frmain.clock.now += frmain.EMERGENCY_POLL_SECONDS
    _poll_timers(frmain)[0].fire()
    assert frmain.spoken[-1].startswith("Attention: X Q Z 777 is squawking 7 6 0 0, radio failure")
    # And the first one again after 30 minutes.
    _fake_sources(monkeypatch, api, fi=EMERGENCY_JSON)
    frmain.clock.now += frmain.EMERGENCY_COOLDOWN
    _poll_timers(frmain)[0].fire()
    assert frmain.spoken[-1] == MAYDAY and len(frmain.spoken) == 3
    # Watch off: polling stops.
    frmain._save_settings(dict(frmain._settings, emergency_watch=False))
    assert _poll_timers(frmain) == []


def test_alerts_and_the_watch_share_one_poll(frmain, api, lang, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi=EMERGENCY_JSON)
    _set(frmain, api, alerts=True, emergency_watch=True)
    frmain._update_polling()
    frmain._update_polling()
    [timer] = _poll_timers(frmain)
    timer.fire()
    assert len(calls) == 1
    # The emergency first, then the overhead alert.
    assert frmain.spoken == [MAYDAY, "Overhead: Citilink 991, Airbus A320, 4.5 kilometres south, "
                                     "1,500 metres, climbing."]
    assert frmain.sounds == ["error.wav", "info.wav"]
    [timer] = _poll_timers(frmain)
    assert timer.seconds == frmain.POLL_SECONDS
    # Turning the watch off keeps the overhead alerts polling.
    frmain._save_settings(dict(frmain._settings, emergency_watch=False))
    assert len(_poll_timers(frmain)) == 1


def test_overhead_polling_also_reports_emergencies(frmain, api, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi=EMERGENCY_JSON)
    _set(frmain, api, alerts=True)
    frmain._update_polling()
    _poll_timers(frmain)[0].fire()
    assert frmain.spoken[0] == MAYDAY and frmain.sounds[0] == "error.wav"


def test_list_emergency_intro_marks_them_heard(frmain, api, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi=EMERGENCY_JSON)
    _set(frmain, api)
    assert frmain.refresh()
    aircraft, cache = frmain.list_data()
    assert frmain.emergency_intro(aircraft) == MAYDAY
    assert frmain._emergency_tracker.check(aircraft, frmain.clock()) == []
    assert frmain.emergency_intro(aircraft[:3]) == ""


def test_listen_to_atc_opens_liveatc_only(frmain, api, lang):
    _set(frmain, api, location=None)
    frmain.listen_to_atc()
    assert frmain.spoken == ["No flight radar location is set. Choose your city in "
                             "Preferences, Flight Radar."] and frmain.opened == []
    _set(frmain, api)
    frmain.listen_to_atc()
    assert frmain.spoken[-1] == "Opening LiveATC for Jakarta Soekarno-Hatta in your browser."
    assert frmain.opened == ["https://www.liveatc.net/hlisten.php?mount=wiii"]
    _set(frmain, api, location=dict(JAKARTA, name="Bandung", latitude=-6.9, longitude=107.6))
    frmain.listen_to_atc()
    assert frmain.spoken[-1] == ("Opening LiveATC's page for Bandung Husein Sastranegara in your "
                                 "browser. It shows whether a live feed exists.")
    assert frmain.opened[-1] == "https://www.liveatc.net/search/?icao=WICC"
    _set(frmain, api, location=dict(JAKARTA, name="Paris", latitude=48.85, longitude=2.35))
    frmain.listen_to_atc()
    assert frmain.spoken[-1] == "Hariku does not know an airport near here to listen to."
    assert len(frmain.opened) == 2
    lang("id")
    _set(frmain, api)
    frmain.listen_to_atc()
    assert frmain.spoken[-1] == "Membuka LiveATC untuk Jakarta Soekarno-Hatta di peramban Anda."


def test_listen_for_an_aircraft(frmain, api, routes, lang, monkeypatch):
    _fake_sources(monkeypatch, api, fi=ADSBFI_JSON)
    frmain._routes = routes.RouteLookup(fetch=lambda cs: routes.parse_route(ROUTE_JSON),
                                        clock=frmain.clock, sleep=frmain.clock.sleep)
    _set(frmain, api)
    frmain.speak_nearby()          # looks up GIA155's route (Batam to Jakarta)
    gia = _by_callsign(frmain.visible_aircraft(), "GIA155")
    frmain.listen_for_aircraft(gia)
    assert frmain.spoken[-1] == ("Opening LiveATC for Jakarta Soekarno-Hatta in your browser. "
                                 "You'll hear the whole frequency, not just this aircraft.")
    assert frmain.opened == ["https://www.liveatc.net/hlisten.php?mount=wiii"]
    # No route: the airport nearest to the aircraft.
    bandung = _normalize(api, _plane(hex="abc011", flight="", lat=-6.95, lon=107.55))
    frmain.listen_for_aircraft(bandung)
    assert frmain.opened[-1] == "https://www.liveatc.net/search/?icao=WICC"
    assert "Bandung Husein Sastranegara" in frmain.spoken[-1]
    # No aircraft selected: the airport nearest to the city.
    frmain.listen_for_aircraft(None)
    assert frmain.spoken[-1] == "Opening LiveATC for Jakarta Soekarno-Hatta in your browser."


def test_changing_settings_saves_them(frmain, api, monkeypatch):
    import core.api
    _set(frmain, api, location=None)
    frmain._save_settings({"location": JAKARTA, "radius_km": 50, "units": "aviation",
                           "include_ground": True, "alerts": True, "alert_km": 3,
                           "emergency_watch": True})
    saved = core.api.load_data(frmain.DATA_KEY)
    assert saved["location"]["name"] == "Jakarta" and saved["radius_km"] == 50
    assert saved["units"] == "aviation" and saved["alerts"] is True and saved["alert_km"] == 3
    assert saved["emergency_watch"] is True
    assert frmain.query_radius_nm() == 28
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
    atc_args, atc_kwargs = by_name["listen_atc"]
    assert atc_args[0] == "Flight Radar" and atc_args[3] == ord("L") and atc_args[4] is False
    assert atc_kwargs == {"default_shift": True}
    assert len(actions) == 3
    assert len(panels) == 1 and panels[0][0] == "Flight Radar"

    frmain._settings = dict(frmain._settings, location=JAKARTA, alerts=True)
    frmain._update_polling()
    timer = frmain._poll_timer
    frmain.teardown()
    assert timer.stopped and frmain._poll_timer is None
    for event_name, handler in frmain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    assert not frmain._active and frmain.refresh() is False


# ------------------------------------------------------------
# Exact locations (1.2): maths, privacy, pasted coordinates, links, addresses
# ------------------------------------------------------------

@pytest.fixture(scope="module")
def loc():
    _import_helpers()
    import flight_radar_location
    return flight_radar_location


def test_distance_and_bearing_against_known_values(api, airports):
    cgk, halim = airports.by_icao("WIII"), airports.by_icao("WIHH")
    km, bearing = api.distance_and_bearing(cgk["latitude"], cgk["longitude"],
                                           halim["latitude"], halim["longitude"])
    assert km == pytest.approx(30.3, abs=0.2) and bearing == pytest.approx(121.3, abs=0.5)
    back = api.distance_and_bearing(halim["latitude"], halim["longitude"],
                                    cgk["latitude"], cgk["longitude"])
    assert back[0] == pytest.approx(km) and back[1] == pytest.approx(301.2, abs=0.5)
    changi = airports.by_icao("WSSS")
    km, bearing = api.distance_and_bearing(cgk["latitude"], cgk["longitude"],
                                           changi["latitude"], changi["longitude"])
    assert km == pytest.approx(882, abs=3) and bearing == pytest.approx(340.3, abs=0.5)
    # One degree along the equator and along a meridian.
    assert api.distance_and_bearing(0, 100, 0, 101) == (pytest.approx(111.19, abs=0.01),
                                                        pytest.approx(90))
    assert api.distance_and_bearing(-7, 110, -6, 110) == (pytest.approx(111.19, abs=0.01),
                                                          pytest.approx(0))


def test_the_query_point_is_rounded_and_the_radius_still_covers_it(api):
    assert api.query_point(-6.208812, 106.845613) == (-6.21, 106.85)
    import random
    rng = random.Random(7)
    for _ in range(500):
        lat, lon = rng.uniform(-60, 60), rng.uniform(-179, 179)
        sent = api.query_point(lat, lon)
        offset = api.distance_and_bearing(lat, lon, *sent)[0]
        assert offset < 0.8
        for km in api.RADIUS_CHOICES_KM:
            # Everything within `km` of the exact point is within the widened
            # radius around the rounded one.
            assert api.nm_to_km(api.query_radius_nm(km)) >= km + offset


def test_only_the_rounded_point_is_sent(api, monkeypatch):
    calls = _fake_sources(monkeypatch, api, fi="offline", lol=ADSBLOL_JSON)
    exact = (-6.208812, 106.845613)
    aircraft, source = api.fetch_aircraft(*exact, 15)
    assert calls == ["https://opendata.adsb.fi/api/v2/lat/-6.21/lon/106.85/dist/15",
                     "https://api.adsb.lol/v2/point/-6.21/106.85/15"]
    assert all("6.2088" not in url and "106.8456" not in url for url in calls)
    # Distances are measured from the exact point, not the rounded one.
    ctv = next(p for p in aircraft if p["callsign"] == "CTV991")
    expected = api.distance_and_bearing(*exact, PLANES[1]["lat"], PLANES[1]["lon"])[0]
    assert ctv["distance_km"] == pytest.approx(expected)


@pytest.mark.parametrize("pasted, lat, lon", [
    ("-6.2088, 106.8456", -6.2088, 106.8456),
    ("-6.2088,106.8456", -6.2088, 106.8456),
    ("-6.2088 106.8456", -6.2088, 106.8456),
    ("-6.2088;106.8456", -6.2088, 106.8456),
    ("  -6.2088 ,  106.8456  ", -6.2088, 106.8456),
    ("−6.2088, 106.8456", -6.2088, 106.8456),
    ("-6,2088; 106,8456", -6.2088, 106.8456),
    ("-6,2088 106,8456", -6.2088, 106.8456),
    ("-6,2088, 106,8456", -6.2088, 106.8456),
    ("-6.2088°, 106.8456°", -6.2088, 106.8456),
    ("6.2088° S, 106.8456° E", -6.2088, 106.8456),
    ("6.2088°S 106.8456°E", -6.2088, 106.8456),
    ("S 6.2088 E 106.8456", -6.2088, 106.8456),
    ("106.8456 E, 6.2088 S", -6.2088, 106.8456),
    ("6,2088 LS 106,8456 BT", -6.2088, 106.8456),
    ("6°12'31.7\"S 106°50'44.2\"E", -6.208806, 106.845611),
    ("6°12′31.7″ LS 106°50′44.2″ BT", -6.208806, 106.845611),
    ("6° 12.5' S, 106° 50.7' E", -6.208333, 106.845),
    ("lat: -6.2088, lng: 106.8456", -6.2088, 106.8456),
    ("Latitude -6.2088 Longitude 106.8456", -6.2088, 106.8456),
    ("40.7128, -74.0060", 40.7128, -74.006),
    ("1.3521 N, 103.8198 E", 1.3521, 103.8198),
])
def test_pasted_coordinates(loc, pasted, lat, lon):
    found = loc.parse_location_text(pasted)
    assert found["kind"] == "coordinates"
    assert found["latitude"] == pytest.approx(lat, abs=1e-5)
    assert found["longitude"] == pytest.approx(lon, abs=1e-5)


@pytest.mark.parametrize("pasted, kind", [
    ("", "empty"), ("   ", "empty"), ("Monas, Jakarta", "not_found"), ("-6.2088", "not_found"),
    ("1, 2, 3", "not_found"), ("95, 10", "out_of_range"), ("10, 200", "out_of_range"),
    ("106.8456, -6.2088, 5", "not_found"), ("0, 0", "zero"), ("0.0; 0.0", "zero"),
    ("S 6.2 S 106.8", "not_found"),
])
def test_pasted_text_that_is_not_a_location(loc, pasted, kind):
    with pytest.raises(loc.LocationError) as info:
        loc.parse_location_text(pasted)
    assert info.value.kind == kind


@pytest.mark.parametrize("link, lat, lon", [
    # Google Maps place: the pin (!3d/!4d) wins over the map view (@).
    ("https://www.google.com/maps/place/Monumen+Nasional/@-6.1753924,106.8249641,17z/"
     "data=!3m1!4b1!4m6!3m5!1s0x2e69f5d2e764b12d:0x3d2ad6e1e0e9bcc8!8m2!3d-6.1753924"
     "!4d106.8271528!16zL20vMDJzNXg1?entry=ttu", -6.1753924, 106.8271528),
    ("https://www.google.com/maps/@-6.2088,106.8456,15z", -6.2088, 106.8456),
    ("https://www.google.com/maps/search/?api=1&query=-6.2088%2C106.8456", -6.2088, 106.8456),
    ("https://maps.google.com/?q=-6.2088,106.8456", -6.2088, 106.8456),
    ("https://maps.google.com/maps?q=loc:-6.2088+106.8456", -6.2088, 106.8456),
    ("https://maps.google.com/?ll=-6.2088,106.8456&z=16", -6.2088, 106.8456),
    ("https://www.google.com/maps/dir/?api=1&destination=-6.2088%2C106.8456", -6.2088, 106.8456),
    ("https://maps.apple.com/?ll=-6.2088,106.8456&q=Dropped%20Pin", -6.2088, 106.8456),
    ("https://maps.apple.com/?q=Monas&ll=-6.2088,106.8456", -6.2088, 106.8456),
    ("https://maps.apple.com/place?coordinate=-6.2088,106.8456&name=Marked%20Location",
     -6.2088, 106.8456),
    ("https://www.openstreetmap.org/?mlat=-6.2088&mlon=106.8456#map=17/-6.20000/106.80000",
     -6.2088, 106.8456),
    ("https://www.openstreetmap.org/#map=17/-6.20880/106.84560", -6.2088, 106.8456),
    ("www.openstreetmap.org/?mlat=-6.2088&mlon=106.8456", -6.2088, 106.8456),
    ("https://consent.google.com/ml?continue=https://www.google.com/maps/place/X/%40-6.2,106.8,17z"
     "/data%3D!3m1!4b1!4m5!3m4!1s0x0:0x0!8m2!3d-6.2088!4d106.8456&gl=ID", -6.2088, 106.8456),
    ("Monumen Nasional\nhttps://www.google.com/maps/@-6.2088,106.8456,15z", -6.2088, 106.8456),
])
def test_map_links(loc, link, lat, lon):
    found = loc.parse_location_text(link)
    assert (found["kind"], found["latitude"], found["longitude"]) == (
        "coordinates", pytest.approx(lat), pytest.approx(lon))


def test_map_links_without_coordinates(loc):
    for link in ("https://www.google.com/maps/place/Monumen+Nasional/data=!4m2!3m1"
                 "!1s0x2e69f5d2e764b12d:0x3d2ad6e1e0e9bcc8",
                 "https://goo.gl/AbCdEf", "https://maps.apple.com/?q=Monas"):
        with pytest.raises(loc.LocationError) as info:
            loc.parse_location_text(link)
        assert info.value.kind == "link_no_coordinates", link
    with pytest.raises(loc.LocationError) as info:
        loc.parse_location_text("https://www.google.com/maps/@95.1,10.2,15z")
    assert info.value.kind == "out_of_range"


@pytest.mark.parametrize("pasted, url", [
    ("https://maps.app.goo.gl/AbCdEf123", "https://maps.app.goo.gl/AbCdEf123"),
    ("maps.app.goo.gl/AbCdEf123", "https://maps.app.goo.gl/AbCdEf123"),
    ("http://maps.app.goo.gl/AbCdEf123?g_st=ic", "https://maps.app.goo.gl/AbCdEf123?g_st=ic"),
    ("https://goo.gl/maps/AbCdEf123", "https://goo.gl/maps/AbCdEf123"),
    ("Monas https://maps.app.goo.gl/AbCdEf123", "https://maps.app.goo.gl/AbCdEf123"),
])
def test_short_links_are_recognised(loc, pasted, url):
    assert loc.parse_location_text(pasted) == {"kind": "short_link", "url": url}


@pytest.mark.parametrize("link", [
    "https://goo.gl/AbCdEf", "https://maps.app.goo.gl.example.com/x",
    "https://example.com/maps.app.goo.gl/x", "https://maps.app.goo.gl:8443/x",
    "https://user@maps.app.goo.gl/x", "https://maps.app.goo.gl/", "ftp://maps.app.goo.gl/x",
])
def test_other_links_are_not_short_links(loc, link):
    assert loc.short_link(link) is None


PIN_URL = ("https://www.google.com/maps/place/Monas/@-6.17,106.82,17z/data=!4m6!3m5!1s0x0:0x0"
           "!8m2!3d-6.2088!4d106.8456")


def _redirects(loc, monkeypatch, answers):
    """Replace the single-request helper: answers maps URL -> (status, Location)."""
    fetched = []

    def fake(url, timeout):
        fetched.append(url)
        answer = answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(loc, "_open_without_redirects", fake)
    return fetched


def test_short_link_expansion_stops_at_other_hosts(loc, monkeypatch):
    fetched = _redirects(loc, monkeypatch, {
        "https://maps.app.goo.gl/AbC": (302, "https://maps.app.goo.gl/Next"),
        "https://maps.app.goo.gl/Next": (301, PIN_URL),
    })
    assert loc.resolve_short_link("https://maps.app.goo.gl/AbC") == (-6.2088, 106.8456)
    # google.com was never fetched: its address was only read from the Location header.
    assert fetched == ["https://maps.app.goo.gl/AbC", "https://maps.app.goo.gl/Next"]


def test_short_link_expansion_reads_nested_and_relative_redirects(loc, monkeypatch):
    consent = ("https://consent.google.com/ml?continue=" +
               PIN_URL.replace("@", "%40").replace("!", "%21") + "&gl=ID")
    fetched = _redirects(loc, monkeypatch, {
        "https://goo.gl/maps/AbC": (302, "/maps/Next"),
        "https://goo.gl/maps/Next": (302, consent),
    })
    assert loc.resolve_short_link("https://goo.gl/maps/AbC") == (-6.2088, 106.8456)
    assert all(url.startswith("https://goo.gl/maps/") for url in fetched)


@pytest.mark.parametrize("answer, kind", [
    ((302, "https://www.google.com/maps/place/Monas/data=!4m2!3m1!1s0x0:0x0"),
     "link_no_coordinates"),
    ((200, None), "link_no_coordinates"),
    ((404, None), "link_failed"),
    ((302, None), "link_failed"),
    (OSError("offline"), "link_failed"),
])
def test_short_link_failures(loc, monkeypatch, answer, kind):
    _redirects(loc, monkeypatch, {"https://maps.app.goo.gl/AbC": answer})
    with pytest.raises(loc.LocationError) as info:
        loc.resolve_short_link("https://maps.app.goo.gl/AbC")
    assert info.value.kind == kind


def test_short_link_redirect_loops_end(loc, monkeypatch):
    fetched = _redirects(loc, monkeypatch, {
        "https://maps.app.goo.gl/A": (302, "https://maps.app.goo.gl/B"),
        "https://maps.app.goo.gl/B": (302, "https://maps.app.goo.gl/A"),
    })
    with pytest.raises(loc.LocationError) as info:
        loc.resolve_short_link("https://maps.app.goo.gl/A")
    assert info.value.kind == "link_failed" and len(fetched) == loc.MAX_REDIRECTS
    with pytest.raises(loc.LocationError):
        loc.expand_short_link("https://example.com/x")   # never fetched at all


def test_redirects_are_reported_not_followed(loc, monkeypatch):
    seen = {}

    class Opener:
        def open(self, req, timeout=None):
            seen.update(url=req.full_url, agent=req.get_header("User-agent"), timeout=timeout)
            raise urllib.error.HTTPError(req.full_url, 302, "Found",
                                         {"Location": PIN_URL}, None)

    def build_opener(*handlers):
        seen["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(loc.urllib.request, "build_opener", build_opener)
    assert loc._open_without_redirects("https://maps.app.goo.gl/AbC", 8) == (302, PIN_URL)
    assert seen["handlers"] == (loc._NoRedirect,) and seen["timeout"] == 8
    assert seen["agent"].startswith("HarikuV2/")
    assert loc._NoRedirect().redirect_request(None, None, 302, "", {}, PIN_URL) is None


NOMINATIM_JSON = [
    {"place_id": 1, "lat": "-6.1753924", "lon": "106.8271528",
     "display_name": "Monumen Nasional, Jalan Medan Merdeka, Gambir, Jakarta Pusat, Indonesia"},
    {"place_id": 2, "lat": "north", "lon": "106.8", "display_name": "Broken"},
    {"place_id": 3, "lat": "-6.2", "lon": "106.8", "display_name": ""},
    {"place_id": 4, "lat": "-6.2", "lon": "106.8", "display_name": "Jalan Merdeka, Bandung"},
]


def test_address_url_and_results(loc):
    url = loc.build_address_url("  Jalan  Merdeka   Barat ", "id")
    assert url.startswith("https://nominatim.openstreetmap.org/search?")
    assert "q=Jalan+Merdeka+Barat&" in url and "format=jsonv2" in url
    assert "limit=10" in url and "accept-language=id" in url
    assert "accept-language=en" in loc.build_address_url("x", "fr")
    places = loc.parse_addresses(NOMINATIM_JSON)
    assert [p["detail"] for p in places] == [NOMINATIM_JSON[0]["display_name"],
                                             "Jalan Merdeka, Bandung"]
    assert places[0]["kind"] == "address" and places[0]["latitude"] == -6.1753924
    assert loc.parse_addresses({"error": "x"}) == []


def test_address_search_is_paced_and_cached(loc, api):
    clock = _Clock()
    urls = []

    def fetch(url):
        urls.append(url)
        return NOMINATIM_JSON

    search = loc.AddressSearch(fetch=fetch, clock=clock, sleep=clock.sleep)
    assert len(search.search("Jalan Merdeka", "en")) == 2
    assert len(search.search("  jalan   MERDEKA ", "en")) == 2      # identical: from memory
    assert len(urls) == 1 and clock.slept == []
    search.search("Jalan Thamrin", "en")
    search.search("Jalan Sudirman", "en")
    assert len(urls) == 3 and clock.slept == [pytest.approx(1.1), pytest.approx(1.1)]
    search.search("Jalan Merdeka", "id")                            # another language
    assert len(urls) == 4


def test_address_search_errors_are_not_cached(loc, api):
    clock = _Clock()
    answers = [api.FlightError("rate_limited", status=429), api.FlightError("offline"),
               NOMINATIM_JSON]

    def fetch(url):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    search = loc.AddressSearch(fetch=fetch, clock=clock, sleep=clock.sleep)
    for kind in ("address_busy", "address_failed"):
        with pytest.raises(loc.LocationError) as info:
            search.search("Monas", "en")
        assert info.value.kind == kind
    assert len(search.search("Monas", "en")) == 2


def test_address_search_identifies_hariku(loc, api, monkeypatch):
    seen = {}

    def fake_fetch_json(url, timeout=None, user_agent=None):
        seen.update(url=url, agent=user_agent)
        return []

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    loc.AddressSearch().search("Monas", "en")
    assert seen["agent"] == loc.NOMINATIM_USER_AGENT
    assert seen["agent"].startswith("HarikuV2/") and "Flight Radar" in seen["agent"]
    assert "github.com" in seen["agent"]


def test_fetch_json_can_send_another_user_agent(api, monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["agent"] = req.get_header("User-agent")
        return _Response(b"[]")

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    api.fetch_json("https://example.invalid/", user_agent="Test/1")
    assert seen["agent"] == "Test/1"


def test_exact_locations_are_kept_with_their_name(api, text, lang):
    home = {"name": "Home", "latitude": -6.208812, "longitude": 106.845613,
            "kind": "coordinates", "detail": "", "extra": 1}
    saved = api.normalize_location(home)
    assert saved == {"name": "Home", "admin1": "", "country": "", "latitude": -6.208812,
                     "longitude": 106.845613, "kind": "coordinates", "detail": ""}
    assert api.place_label(saved) == "Home"
    assert text.location_text(saved) == "Home: -6.20881, 106.84561"
    office = api.normalize_location({"name": "Office", "latitude": -6.17, "longitude": 106.82,
                                     "kind": "address", "detail": "Jalan Medan Merdeka, Gambir"})
    assert api.place_label(office) == "Office"
    assert text.location_text(office) == "Office: Jalan Medan Merdeka, Gambir"
    assert text.location_text(JAKARTA) == "Jakarta, Indonesia"
    assert api.normalize_location(dict(home, latitude=0, longitude=0)) is None
    assert api.normalize_location(dict(home, kind="satellite"))["name"] == "Home"
    assert "kind" not in api.normalize_location(dict(home, kind="satellite"))


def test_near_airport_hint(text, lang, airports):
    widd = airports.by_icao("WIDD")
    point = _at(12, 135, origin=(widd["latitude"], widd["longitude"]))
    assert text.near_airport_hint(point["lat"], point["lon"], "metric") == (
        "about 12 kilometres from Batam Hang Nadim airport")
    assert text.near_airport_hint(point["lat"], point["lon"], "aviation") == (
        "about 6.5 nautical miles from Batam Hang Nadim airport")
    lang("id")
    assert text.near_airport_hint(point["lat"], point["lon"], "metric") == (
        "sekitar 12 kilometer dari bandara Batam Hang Nadim")


@pytest.mark.parametrize("kind, words", [
    ("empty", "Paste coordinates"), ("not_found", "could not find coordinates"),
    ("out_of_range", "out of range"), ("zero", "not a real place"),
    ("link_no_coordinates", "does not contain coordinates"),
    ("link_failed", "short link"), ("address_busy", "busy"),
    ("address_failed", "Could not search for addresses"),
])
def test_location_error_texts(text, lang, kind, words):
    assert words in text.location_error_text(kind)


def test_exact_home_end_to_end(frmain, api, lang, monkeypatch):
    import core.api
    calls = _fake_sources(monkeypatch, api, fi={"aircraft": [
        _plane(**_at(3.0, 90, origin=(-6.208812, 106.845613)))]})
    home = {"name": "Home", "admin1": "", "country": "", "latitude": -6.208812,
            "longitude": 106.845613, "kind": "coordinates", "detail": ""}
    frmain._save_settings({"location": home})
    # Stored exactly, on this computer only.
    assert core.api.load_data(frmain.DATA_KEY)["location"]["latitude"] == -6.208812
    frmain.speak_nearby()
    assert calls == ["https://opendata.adsb.fi/api/v2/lat/-6.21/lon/106.85/dist/15"]
    assert frmain.spoken[-1].startswith("Garuda Indonesia 155, Boeing 737-800, "
                                        "3 kilometres east,")
    assert api.place_label(frmain.get_location()) == "Home"
