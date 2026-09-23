# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Earthquakes & Tsunami extension: BMKG and USGS parsing, the
# tsunami wording, distances, every alert rule, text in both languages, the
# once-per-session disclaimer, polling, the briefing and the actions. No test
# touches the network (fetch_json and urlopen are replaced) and no sound plays.

import datetime
import importlib.util
import json
import os
import re
import sys
import types
import urllib.error

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EQ_DIR = os.path.join(ROOT, "extensions", "earthquake")

UTC = datetime.timezone.utc
QUAKE_TIME = datetime.datetime(2026, 9, 23, 2, 2, 44, tzinfo=UTC).timestamp()  # 09:02:44 WIB
NOW = QUAKE_TIME + 600   # ten minutes later


def _gempa(**overrides):
    """One BMKG entry in the verified autogempa.json shape (23 September 2026)."""
    entry = {"Tanggal": "23 Sep 2026", "Jam": "09:02:44 WIB",
             "DateTime": "2026-09-23T02:02:44+00:00", "Coordinates": "-8.21,120.61",
             "Lintang": "8.21 LS", "Bujur": "120.61 BT", "Magnitude": "4.7",
             "Kedalaman": "9 km",
             "Wilayah": "Pusat gempa berada di laut 48 km utara Ruteng-Manggarai",
             "Potensi": "Gempa ini dirasakan untuk diteruskan pada masyarakat",
             "Dirasakan": "II - III Kab. Manggarai", "Shakemap": "20260923090244.mmi.jpg"}
    entry.update(overrides)
    return {k: v for k, v in entry.items() if v is not None}


def _autogempa(**overrides):
    return {"Infogempa": {"gempa": _gempa(**overrides)}}


# A tsunami-potential quake south of Java, far from Ruteng.
TSUNAMI = dict(DateTime="2026-09-23T02:05:00+00:00", Jam="09:05:00 WIB",
               Coordinates="-9.50,112.80", Lintang="9.50 LS", Bujur="112.80 BT",
               Magnitude="7.1", Kedalaman="10 km",
               Wilayah="Pusat gempa berada di laut 150 km BaratDaya Jember",
               Potensi="Berpotensi tsunami untuk diteruskan pada masyarakat", Dirasakan=None)

TERKINI = {"Infogempa": {"gempa": [
    {"Tanggal": "22 Sep 2026", "Jam": "06:48:13 WIB", "DateTime": "2026-09-21T23:48:13+00:00",
     "Coordinates": "4.74,125.30", "Lintang": "4.74 LU", "Bujur": "125.30 BT",
     "Magnitude": "5.2", "Kedalaman": "10 km",
     "Wilayah": "127 km BaratLaut TAHUNA-KEP.SANGIHE-SULUT", "Potensi": "Tidak berpotensi tsunami"},
    {"Tanggal": "04 Sep 2026", "Jam": "12:04:59 WIB", "DateTime": "2026-09-04T05:04:59+00:00",
     "Coordinates": "-8.42,109.02", "Lintang": "8.42 LS", "Bujur": "109.02 BT",
     "Magnitude": "5.4", "Kedalaman": "10 km", "Wilayah": "77 km Tenggara CILACAP-JATENG",
     "Potensi": "Tidak berpotensi tsunami"},
]}}

DIRASAKAN = {"Infogempa": {"gempa": [
    _gempa(Potensi=None, Shakemap=None),
    {"Tanggal": "20 Sep 2026", "Jam": "17:20:32 WIB", "DateTime": "2026-09-20T10:20:32+00:00",
     "Coordinates": "-5.82,122.84", "Lintang": "5.82 LS", "Bujur": "122.84 BT",
     "Magnitude": "3.9", "Kedalaman": "14 km",
     "Wilayah": "Pusat gempa berada di laut 32 km selatan Buton", "Dirasakan": "III Kab. Buton"},
    {"Tanggal": "19 Sep 2026", "Jam": "01:00:00 WIB", "Magnitude": "", "Wilayah": "broken"},
]}}


def _feature(ident, mag, place, when, lon, lat, depth, tsunami=0, kind="earthquake"):
    return {"type": "Feature", "id": ident,
            "properties": {"mag": mag, "place": place, "time": int(when * 1000),
                           "tsunami": tsunami, "title": f"M {mag} - {place}", "type": kind},
            "geometry": {"type": "Point", "coordinates": [lon, lat, depth]}}


USGS = {"type": "FeatureCollection",
        "metadata": {"title": "USGS Magnitude 4.5+ Earthquakes, Past Day", "count": 5},
        "features": [
            _feature("us7000japan", 6.8, "120 km S of Hachijo-jima, Japan", NOW - 300,
                     139.7, 32.0, 35.0, tsunami=1),
            _feature("us6000tx29", 5.3, "51 km WSW of Arauco, Argentina", QUAKE_TIME - 3 * 3600,
                     -67.2912, -28.7298, 121.534),
            _feature("us6000small", 4.6, "Fiji region", QUAKE_TIME - 3600, 178.0, -17.9, 550.0),
            # BMKG's autogempa quake, as USGS located it.
            _feature("us6000dup", 5.1, "80 km N of Ruteng, Indonesia", QUAKE_TIME + 20,
                     120.58, -8.25, 12.0),
            _feature("us6000blast", 4.5, "quarry", NOW - 60, 100.0, 0.0, 0.0, kind="quarry blast"),
        ]}

RUTENG = {"name": "Ruteng", "admin1": "East Nusa Tenggara", "admin2": "Kabupaten Manggarai",
          "country": "Indonesia", "latitude": -8.6136, "longitude": 120.4721, "timezone": ""}
JAKARTA = {"name": "Jakarta", "admin1": "Jakarta", "admin2": "", "country": "Indonesia",
           "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"}

GEOCODING_JSON = {"results": [
    {"name": "Ruteng", "latitude": -8.6136, "longitude": 120.4721, "country": "Indonesia",
     "admin1": "East Nusa Tenggara", "admin2": "Kabupaten Manggarai", "timezone": "Asia/Makassar"},
    {"name": "Nowhere", "latitude": "north"},
]}


def _import_helpers():
    if EQ_DIR not in sys.path:
        sys.path.insert(0, EQ_DIR)
    import earthquake_alerts
    import earthquake_api
    import earthquake_text
    return earthquake_api, earthquake_alerts, earthquake_text


@pytest.fixture(scope="module")
def api():
    return _import_helpers()[0]


@pytest.fixture(scope="module")
def alerts():
    return _import_helpers()[1]


@pytest.fixture(scope="module")
def text():
    return _import_helpers()[2]


@pytest.fixture
def lang(monkeypatch, text):
    """Switch the UI language; the core day and month names are loaded too."""
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


def _copy(payload):
    return json.loads(json.dumps(payload))


@pytest.fixture
def latest(api):
    return api.parse_autogempa(_copy(_autogempa()))


@pytest.fixture
def tsunami_quake(api):
    return api.parse_autogempa(_copy(_autogempa(**TSUNAMI)))


def _settings(api, **overrides):
    settings = api.default_settings()
    settings.update(overrides)
    return settings


# ------------------------------------------------------------
# Locale files and module rules
# ------------------------------------------------------------

def test_locales_have_the_same_keys():
    keys = {}
    for code in ("en", "id"):
        with open(os.path.join(EQ_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            data = json.load(f)
        keys[code] = set(data["messages"])
        for field in ("language_name", "language_code", "translator", "email", "version"):
            assert field in data["manifest"]
    assert keys["en"] == keys["id"]


def test_keys_built_at_runtime_exist(text, lang):
    for kind in ("offline", "service", "bad_response"):
        assert text.error_text(kind) != text._ERROR_KEYS[kind]
    for key in text._ERROR_KEYS.values():
        assert text._(key) != key


def test_every_python_file_has_the_licence_header():
    with open(os.path.join(ROOT, "extensions", "weather", "main.py"), encoding="utf-8") as f:
        header = "".join(f.readlines()[:8])
    for name in os.listdir(EQ_DIR):
        if name.endswith(".py"):
            with open(os.path.join(EQ_DIR, name), encoding="utf-8") as f:
                assert f.read().startswith(header), name


def test_manifest():
    with open(os.path.join(EQ_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["version"] == "1.0" and manifest["minimum_core_version"] == "2.4"
    assert manifest["main"] == "main.py" and "BMKG" in manifest["description"]


# ------------------------------------------------------------
# Numbers, coordinates and times in BMKG's text
# ------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("4.7", 4.7), (4.7, 4.7), ("9 km", 9.0), ("2.13 LS", 2.13), ("120.41 BT", 120.41),
    ("4,7", 4.7), ("  10 km ", 10.0), ("-3.5", -3.5), (5, 5.0),
    ("", None), ("km", None), (None, None), (True, None), ("nan", None), ([], None),
])
def test_parse_number(api, value, expected):
    assert api.parse_number(value) == expected


def test_latitude_longitude_and_coordinates(api):
    assert api.parse_latitude("8.21 LS") == -8.21
    assert api.parse_latitude("4.74 LU") == 4.74
    assert api.parse_latitude("2.13 S") == -2.13
    assert api.parse_latitude("95 LU") is None
    assert api.parse_longitude("120.61 BT") == 120.61
    assert api.parse_longitude("10.5 BB") == -10.5
    assert api.parse_longitude("east") is None
    assert api.parse_coordinates("-8.21,120.61") == (-8.21, 120.61)
    assert api.parse_coordinates("-8.21, 120.61") == (-8.21, 120.61)
    assert api.parse_coordinates("x,y") == (None, None)
    assert api.parse_coordinates("-95,1") == (None, None)
    assert api.parse_coordinates(None) == (None, None)


def test_times(api):
    assert api.parse_iso_time("2026-09-23T02:02:44+00:00") == QUAKE_TIME
    assert api.parse_iso_time("2026-09-23T02:02:44Z") == QUAKE_TIME
    assert api.parse_iso_time("yesterday") is None
    assert api.parse_clock("09:02:44 WIB") == ("09:02", "WIB")
    assert api.parse_clock("21.15.00 WITA") == ("21:15", "WITA")
    assert api.parse_clock("25:00:00 WIB") == ("", "")
    assert api.parse_clock("") == ("", "")
    # Without a DateTime: Tanggal and Jam in Indonesian, in their zone.
    assert api.parse_local_time("23 Sep 2026", "09:02:44 WIB") == QUAKE_TIME
    assert api.parse_local_time("23 Sep 2026", "10:02:44 WITA") == QUAKE_TIME
    assert api.parse_local_time("23 Agu 2026", "09:02:44 WIB") is not None
    assert api.parse_local_time("23 Mei 2026", "09:02:44 WIB") is not None
    assert api.parse_local_time("23 Foo 2026", "09:02:44 WIB") is None


# ------------------------------------------------------------
# BMKG parsing
# ------------------------------------------------------------

def test_parse_autogempa(latest):
    assert latest["source"] == "bmkg"
    assert latest["id"] == "2026-09-23T02:02:44+00:00"
    assert latest["time"] == QUAKE_TIME
    assert latest["magnitude"] == 4.7 and latest["depth_km"] == 9.0
    assert (latest["lat"], latest["lon"]) == (-8.21, 120.61)
    assert latest["region"] == "Pusat gempa berada di laut 48 km utara Ruteng-Manggarai"
    assert latest["potential"] == "Gempa ini dirasakan untuk diteruskan pada masyarakat"
    assert latest["felt"] == "II - III Kab. Manggarai"
    assert (latest["clock"], latest["zone"]) == ("09:02", "WIB")
    assert (latest["date_text"], latest["time_text"]) == ("23 Sep 2026", "09:02:44 WIB")
    assert (latest["lat_text"], latest["lon_text"], latest["depth_text"]) == \
        ("8.21 LS", "120.61 BT", "9 km")


def test_parse_autogempa_without_coordinates_or_datetime(api):
    quake = api.parse_autogempa(_autogempa(Coordinates=None, DateTime=None))
    assert (quake["lat"], quake["lon"]) == (-8.21, 120.61)   # from Lintang / Bujur
    assert quake["time"] == QUAKE_TIME                        # from Tanggal / Jam
    assert quake["id"] == "23 Sep 2026 09:02:44 WIB"


def test_parse_autogempa_collapses_whitespace_only(api):
    quake = api.parse_autogempa(_autogempa(Potensi="  Tidak  berpotensi\ntsunami "))
    assert quake["potential"] == "Tidak berpotensi tsunami"


@pytest.mark.parametrize("payload", [
    None, [], "text", {}, {"Infogempa": {}}, {"Infogempa": "x"},
    {"Infogempa": {"gempa": {"Magnitude": "besar"}}},
    {"Infogempa": {"gempa": {"Magnitude": "5.0"}}},       # no DateTime, Tanggal or Jam
    {"Infogempa": {"gempa": []}},
])
def test_parse_autogempa_rejects_unusable_data(api, payload):
    with pytest.raises(api.QuakeError) as info:
        api.parse_autogempa(payload)
    assert info.value.kind == "bad_response"


def test_parse_lists_and_merge(api):
    recent = api.parse_bmkg_list(_copy(TERKINI))
    felt = api.parse_bmkg_list(_copy(DIRASAKAN))
    assert len(recent) == 2 and len(felt) == 2   # the broken entry is dropped
    assert recent[0]["felt"] == "" and recent[0]["potential"] == "Tidak berpotensi tsunami"
    assert felt[0]["potential"] == "" and felt[0]["felt"] == "II - III Kab. Manggarai"
    with pytest.raises(api.QuakeError):
        api.parse_bmkg_list({"Infogempa": {"gempa": "x"}})

    latest = api.parse_autogempa(_copy(_autogempa()))
    merged = api.merge_bmkg(felt + [latest])
    same = next(q for q in merged if q["id"] == latest["id"])
    assert same["felt"] == "II - III Kab. Manggarai"
    assert same["potential"] == "Gempa ini dirasakan untuk diteruskan pada masyarakat"
    assert len(merged) == 2


@pytest.mark.parametrize("potential, expected", [
    ("Tidak berpotensi tsunami", False),
    ("TIDAK BERPOTENSI TSUNAMI", False),
    ("Tidak berpotensi Tsunami, waspada gempa susulan", False),
    ("Gempa ini dirasakan untuk diteruskan pada masyarakat", False),
    ("Berpotensi tsunami", True),
    ("Berpotensi TSUNAMI untuk diteruskan pada masyarakat", True),
    ("Potensi tsunami untuk diteruskan pada masyarakat", True),
    ("Gempa ini ber-potensi tsunami", True),
    ("Peringatan dini tsunami", True),
    ("tsunami", False),
    ("", False),
    (None, False),
])
def test_tsunami_wording(api, potential, expected):
    assert api.is_tsunami_potential(potential) is expected


# ------------------------------------------------------------
# USGS parsing
# ------------------------------------------------------------

def test_parse_usgs(api):
    quakes = api.parse_usgs(_copy(USGS))
    assert [q["id"] for q in quakes] == ["us7000japan", "us6000tx29", "us6000small", "us6000dup"]
    japan = quakes[0]
    assert japan["source"] == "usgs" and japan["magnitude"] == 6.8
    assert japan["time"] == pytest.approx(NOW - 300)
    assert (japan["lat"], japan["lon"], japan["depth_km"]) == (32.0, 139.7, 35.0)
    assert japan["region"] == "120 km S of Hachijo-jima, Japan"
    assert japan["tsunami_flag"] is True and quakes[1]["tsunami_flag"] is False


@pytest.mark.parametrize("payload", [None, {}, {"features": "x"}, []])
def test_parse_usgs_rejects_unusable_data(api, payload):
    with pytest.raises(api.QuakeError):
        api.parse_usgs(payload)


def test_parse_usgs_skips_broken_features(api):
    payload = {"features": [None, {"properties": "x"}, {"id": "a", "properties": {"mag": None}},
                            {"id": "b", "properties": {"mag": 5.0, "time": 1000}}]}
    quakes = api.parse_usgs(payload)
    assert [q["id"] for q in quakes] == ["b"]
    assert quakes[0]["lat"] is None and quakes[0]["time"] == 1.0


# ------------------------------------------------------------
# Distances and directions
# ------------------------------------------------------------

def test_distance_and_direction(api, text, lang, latest):
    assert api.distance_and_bearing(0, 100, 0, 101) == (pytest.approx(111.19, abs=0.01),
                                                        pytest.approx(90))
    assert api.distance_and_bearing(-7, 110, -6, 110) == (pytest.approx(111.19, abs=0.01),
                                                          pytest.approx(0))
    km, bearing = api.distance_from(RUTENG, latest)
    assert km == pytest.approx(47.4, abs=0.2) and bearing == pytest.approx(18.7, abs=0.5)
    assert [api.compass_index(d) for d in (0, 44, 46, 90, 180, 225, 270, 315, 350)] == \
        [0, 1, 1, 2, 4, 5, 6, 7, 0]
    assert api.distance_from(None, latest) is None
    assert api.distance_from(RUTENG, dict(latest, lat=None, lon=None)) is None
    assert text.distance_phrase(latest, RUTENG) == "47 kilometres north of Ruteng"
    assert text.distance_phrase(latest, JAKARTA) == "1,530 kilometres east of Jakarta"
    lang("id")
    assert text.distance_phrase(latest, JAKARTA) == "1.530 kilometer di sebelah timur Jakarta"


def test_km_and_magnitude_text(text, lang):
    assert text.km_text(1) == "1 kilometre"
    assert text.km_text(4.44) == "4.4 kilometres"
    assert text.km_text(47.4) == "47 kilometres"
    assert text.km_text(1534.5) == "1,530 kilometres"
    assert text.km_text(121.534, tens=False) == "122 kilometres"
    assert text.magnitude_value(4.7) == "4.7"
    assert text.magnitude_value(5.0) == "5.0"
    assert text.magnitude_value(4.56) == "4.56"
    lang("id")
    assert text.magnitude_value(4.7) == "4,7"
    assert text.km_text(4.44) == "4,4 kilometer"


# ------------------------------------------------------------
# Felt reports, settings and the cache
# ------------------------------------------------------------

def test_region_names_and_felt_matching(api):
    assert api.region_names(RUTENG) == ["Ruteng", "Manggarai"]
    assert api.region_names(JAKARTA, "Kota Bogor, , De, depok") == ["Jakarta", "Bogor", "depok"]
    assert api.region_names(None) == []
    assert api.felt_in_region("II - III Kab. Manggarai", ["Ruteng", "Manggarai"])
    assert api.felt_in_region("III MANGGARAI BARAT", ["manggarai"])
    assert not api.felt_in_region("II Kab. Manggarai", ["Ruteng"])
    assert not api.felt_in_region("III Baturaja", ["Batu"])      # whole words only
    assert not api.felt_in_region("", ["Ruteng"])
    assert not api.felt_in_region(None, ["Ruteng"])


def test_settings_defaults(api):
    settings = api.normalize_settings(None)
    assert settings == {"location": None, "tsunami_alerts": True, "nearby_alerts": False,
                        "alert_km": 300, "min_magnitude": 4.0, "felt_alerts": False,
                        "felt_names": "", "world_alerts": False, "list_world": False,
                        "sounds": True}


@pytest.mark.parametrize("raw", [
    "garbage", [], {"alert_km": 250}, {"alert_km": True}, {"min_magnitude": 7.5},
    {"min_magnitude": "lots"}, {"tsunami_alerts": "no"}, {"location": "Ruteng"},
    {"location": {"name": "X", "latitude": 95, "longitude": 1}}, {"felt_names": 5},
])
def test_settings_survive_corrupt_data(api, raw):
    assert api.normalize_settings(raw) == api.default_settings()


def test_settings_keep_valid_values(api):
    raw = {"location": RUTENG, "tsunami_alerts": False, "nearby_alerts": True, "alert_km": 1000,
           "min_magnitude": "5.5", "felt_alerts": True, "felt_names": "  Kab.  Manggarai ",
           "world_alerts": True, "list_world": True, "sounds": False, "extra": 1}
    settings = api.normalize_settings(raw)
    assert settings["location"] == RUTENG
    assert settings["alert_km"] == 1000 and settings["min_magnitude"] == 5.5
    assert settings["felt_names"] == "Kab. Manggarai"
    assert not settings["tsunami_alerts"] and settings["nearby_alerts"] and not settings["sounds"]
    assert "extra" not in settings


def test_cache_round_trip_and_corruption(api, latest):
    cache = api.empty_cache()
    cache.update(latest=latest, latest_at=5.0, lists=[latest], history=[latest])
    assert api.normalize_cache(_copy(cache)) == cache
    assert api.normalize_cache("junk") == api.empty_cache()
    broken = api.normalize_cache({"latest": {"source": "bmkg"}, "lists": [None, 5, latest],
                                  "latest_at": "soon"})
    assert broken["latest"] is None and broken["lists"] == [latest] and broken["latest_at"] is None
    assert api.is_fresh(100.0, 60, now=150.0)
    assert not api.is_fresh(100.0, 60, now=161.0)
    assert not api.is_fresh(100.0, 60, now=50.0)   # clock went backwards
    assert not api.is_fresh(None, 60)


def test_recent_quakes_are_merged_deduplicated_and_newest_first(api, latest):
    lists = api.merge_bmkg(api.parse_bmkg_list(_copy(TERKINI)) + api.parse_bmkg_list(_copy(DIRASAKAN)))
    cache = dict(api.empty_cache(), latest=latest, lists=lists,
                 world_day=api.parse_usgs(_copy(USGS)))
    rows = api.recent_quakes(cache, False, NOW)
    assert [q["id"] for q in rows] == ["2026-09-23T02:02:44+00:00", "2026-09-21T23:48:13+00:00",
                                       "2026-09-20T10:20:32+00:00", "2026-09-04T05:04:59+00:00"]
    rows = api.recent_quakes(cache, True, NOW)
    ids = [q["id"] for q in rows]
    # USGS M5+ from the last day only; its copy of BMKG's quake is dropped.
    assert ids[:2] == ["us7000japan", "2026-09-23T02:02:44+00:00"]
    assert "us6000tx29" in ids and "us6000small" not in ids and "us6000dup" not in ids
    assert api.recent_quakes(api.empty_cache(), True, NOW) == []


def test_list_rows_use_the_poll_history(api, latest):
    # The felt list has no Potensi; the polled autogempa report fills it in.
    cache = dict(api.empty_cache(), lists=[dict(latest, potential="")], history=[latest])
    assert api.recent_quakes(cache, False, NOW)[0]["potential"] == latest["potential"]
    # A fresher felt report in BMKG's lists replaces the history's.
    cache = dict(api.empty_cache(), lists=[dict(latest, felt="IV Kab. Manggarai")],
                 history=[latest])
    assert api.recent_quakes(cache, False, NOW)[0]["felt"] == "IV Kab. Manggarai"
    # Polled quakes no longer in BMKG's lists are still shown.
    older = dict(latest, id="2026-09-22T10:00:00+00:00", time=QUAKE_TIME - 16 * 3600)
    cache = dict(api.empty_cache(), history=[latest, older])
    assert [q["id"] for q in api.recent_quakes(cache, False, NOW)] == [latest["id"], older["id"]]


def test_history_keeps_two_days(api, latest):
    old = dict(latest, id="old", time=NOW - 3 * 86400)
    history = api.add_to_history([old], latest, NOW)
    assert [q["id"] for q in history] == [latest["id"]]
    assert api.add_to_history(history, latest, NOW) == history


def test_latest_near(api, latest, tsunami_quake):
    quakes = [latest, tsunami_quake]
    assert api.latest_near(quakes, RUTENG, 300, NOW, 86400) is latest
    assert api.latest_near(quakes, RUTENG, 1000, NOW, 86400) is tsunami_quake
    assert api.latest_near(quakes, JAKARTA, 300, NOW, 86400) is None
    assert api.latest_near(quakes, RUTENG, 300, NOW + 2 * 86400, 86400) is None
    assert api.latest_near(quakes, None, 300, NOW, 86400) is None


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
        seen["url"] = req.full_url
        seen["agent"] = req.get_header("User-agent")
        seen["timeout"] = timeout
        return _Response(b'\xef\xbb\xbf{"ok": true}')   # BMKG may send a BOM

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    assert api.fetch_json(api.AUTOGEMPA_URL) == {"ok": True}
    assert seen["url"] == "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
    assert seen["agent"].startswith("HarikuV2/") and seen["agent"].endswith("(Earthquake extension)")
    assert seen["timeout"] == api.TIMEOUT_SECONDS


@pytest.mark.parametrize("failure, kind", [
    (urllib.error.URLError("no route to host"), "offline"),
    (TimeoutError("timed out"), "offline"),
    (urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None), "service"),
])
def test_fetch_json_maps_failures(api, monkeypatch, failure, kind):
    def fake_urlopen(req, timeout=None):
        raise failure

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(api.QuakeError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == kind


def test_fetch_json_rejects_bad_body(api, monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b"<html>oops</html>"))
    with pytest.raises(api.QuakeError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == "bad_response"


def test_search_url_and_places(api):
    url = api.build_search_url("  Ruteng ", "id")
    assert url.startswith("https://geocoding-api.open-meteo.com/v1/search?")
    assert "name=Ruteng&" in url and "language=id" in url
    assert "language=en" in api.build_search_url("Paris", "fr")
    places = api.parse_places(GEOCODING_JSON)
    assert len(places) == 1 and places[0]["admin2"] == "Kabupaten Manggarai"
    assert api.place_label(places[0]) == "Ruteng, East Nusa Tenggara, Indonesia"


# ------------------------------------------------------------
# Alert rules
# ------------------------------------------------------------

def test_tsunami_is_always_announced_regardless_of_distance(api, alerts, tsunami_quake):
    tracker = alerts.AlertTracker()
    # Every other alert is off and the quake is 850 km away: still announced.
    settings = _settings(api)
    assert tracker.check_bmkg(tsunami_quake, settings, RUTENG, NOW) == "tsunami"
    assert tracker.check_bmkg(tsunami_quake, settings, RUTENG, NOW + 60) is None   # once
    # Without any location too.
    assert alerts.AlertTracker().check_bmkg(tsunami_quake, settings, None, NOW) == "tsunami"
    # Only when the setting is on.
    off = _settings(api, tsunami_alerts=False)
    assert alerts.AlertTracker().check_bmkg(tsunami_quake, off, RUTENG, NOW) is None


def test_no_tsunami_wording_is_not_a_tsunami_alert(api, alerts):
    for potential in ("Tidak berpotensi tsunami", "Gempa ini dirasakan untuk diteruskan pada masyarakat"):
        quake = api.parse_autogempa(_autogempa(**dict(TSUNAMI, Potensi=potential)))
        assert alerts.AlertTracker().check_bmkg(quake, _settings(api), RUTENG, NOW) is None


def test_nearby_needs_distance_and_magnitude(api, alerts, latest):
    on = _settings(api, nearby_alerts=True)
    assert alerts.AlertTracker().check_bmkg(latest, on, RUTENG, NOW) == "nearby"   # 47 km, M4.7
    assert alerts.AlertTracker().check_bmkg(latest, on, JAKARTA, NOW) is None      # 1,530 km
    far = _settings(api, nearby_alerts=True, alert_km=1000)
    assert alerts.AlertTracker().check_bmkg(latest, far, JAKARTA, NOW) is None
    wide = _settings(api, nearby_alerts=True, alert_km=1000)
    assert alerts.AlertTracker().check_bmkg(latest, wide, dict(JAKARTA, longitude=112.0),
                                            NOW) == "nearby"
    strict = _settings(api, nearby_alerts=True, min_magnitude=5.0)
    assert alerts.AlertTracker().check_bmkg(latest, strict, RUTENG, NOW) is None
    exact = _settings(api, nearby_alerts=True, min_magnitude=4.5)
    assert alerts.AlertTracker().check_bmkg(dict(latest, magnitude=4.5), exact, RUTENG,
                                            NOW) == "nearby"
    assert alerts.AlertTracker().check_bmkg(latest, _settings(api), RUTENG, NOW) is None  # opt-in
    assert alerts.AlertTracker().check_bmkg(latest, on, None, NOW) is None             # no location


def test_felt_in_my_region(api, alerts, latest):
    on = _settings(api, felt_alerts=True)
    assert alerts.AlertTracker().check_bmkg(latest, on, RUTENG, NOW) == "felt"   # "Manggarai"
    weather_city = dict(RUTENG, admin2="")
    assert alerts.AlertTracker().check_bmkg(latest, on, weather_city, NOW) is None
    extra = _settings(api, felt_alerts=True, felt_names="Manggarai")
    assert alerts.AlertTracker().check_bmkg(latest, extra, weather_city, NOW) == "felt"
    assert alerts.AlertTracker().check_bmkg(latest, extra, None, NOW) == "felt"
    assert alerts.AlertTracker().check_bmkg(latest, _settings(api), RUTENG, NOW) is None  # opt-in
    both = _settings(api, felt_alerts=True, nearby_alerts=True)
    assert alerts.AlertTracker().check_bmkg(latest, both, RUTENG, NOW) == "nearby"


def test_each_quake_is_announced_once(api, alerts, latest):
    tracker = alerts.AlertTracker()
    settings = _settings(api, nearby_alerts=True, felt_alerts=True)
    assert tracker.check_bmkg(latest, settings, RUTENG, NOW) == "nearby"
    for minute in range(1, 5):
        assert tracker.check_bmkg(latest, settings, RUTENG, NOW + 60 * minute) is None
    revised = dict(latest, magnitude=4.9, felt="IV Kab. Manggarai")
    assert tracker.check_bmkg(revised, settings, RUTENG, NOW + 600) is None


def test_felt_report_added_later_is_announced(api, alerts, latest):
    tracker = alerts.AlertTracker()
    settings = _settings(api, felt_alerts=True)
    early = dict(latest, felt="")
    assert tracker.check_bmkg(early, settings, RUTENG, NOW) is None
    assert tracker.check_bmkg(latest, settings, RUTENG, NOW + 120) == "felt"
    assert tracker.check_bmkg(latest, settings, RUTENG, NOW + 180) is None


def test_tsunami_potential_added_later_is_still_announced(api, alerts, latest):
    tracker = alerts.AlertTracker()
    settings = _settings(api, nearby_alerts=True)
    assert tracker.check_bmkg(latest, settings, RUTENG, NOW) == "nearby"
    escalated = dict(latest, potential="Berpotensi tsunami")
    assert tracker.check_bmkg(escalated, settings, RUTENG, NOW + 60) == "tsunami"
    assert tracker.check_bmkg(escalated, settings, RUTENG, NOW + 120) is None


def test_heard_through_the_hotkey_is_not_repeated(api, alerts, latest, tsunami_quake):
    tracker = alerts.AlertTracker()
    settings = _settings(api, nearby_alerts=True)
    tracker.heard(latest)
    assert tracker.check_bmkg(latest, settings, RUTENG, NOW) is None
    tracker.heard(tsunami_quake)
    assert tracker.check_bmkg(tsunami_quake, settings, RUTENG, NOW) is None
    # BMKG adds tsunami potential after the user heard it: that is announced.
    assert tracker.check_bmkg(dict(latest, potential="Berpotensi tsunami"), settings, RUTENG,
                              NOW) == "tsunami"


def test_old_quakes_are_not_announced(api, alerts, latest, tsunami_quake):
    settings = _settings(api, nearby_alerts=True)
    assert alerts.AlertTracker().check_bmkg(latest, settings, RUTENG, QUAKE_TIME + 3500) == "nearby"
    assert alerts.AlertTracker().check_bmkg(latest, settings, RUTENG, QUAKE_TIME + 3700) is None
    late = tsunami_quake["time"] + 2 * 3600
    assert alerts.AlertTracker().check_bmkg(tsunami_quake, settings, RUTENG, late) == "tsunami"
    later = tsunami_quake["time"] + 4 * 3600
    assert alerts.AlertTracker().check_bmkg(tsunami_quake, settings, RUTENG, later) is None
    # A computer clock a few minutes behind still gets the alert.
    assert alerts.AlertTracker().check_bmkg(latest, settings, RUTENG, QUAKE_TIME - 300) == "nearby"
    assert alerts.AlertTracker().check_bmkg(dict(latest, time=None), settings, RUTENG, NOW) is None


def test_worldwide_alerts_are_opt_in_strong_and_once(api, alerts):
    quakes = api.parse_usgs(_copy(USGS))
    assert alerts.AlertTracker().check_usgs(quakes, _settings(api), NOW) == []
    tracker = alerts.AlertTracker()
    on = _settings(api, world_alerts=True)
    new = tracker.check_usgs(quakes, on, NOW)
    assert [q["id"] for q in new] == ["us7000japan"]   # M6.8; the rest are below 6.5
    assert tracker.check_usgs(quakes, on, NOW + 300) == []
    assert alerts.AlertTracker().check_usgs(quakes, on, NOW + 2 * 3600) == []   # too old


def test_bmkg_and_usgs_do_not_announce_the_same_quake_twice(api, alerts, latest):
    strong_dup = dict(api.parse_usgs(_copy(USGS))[3], magnitude=6.6)
    settings = _settings(api, nearby_alerts=True, world_alerts=True)
    tracker = alerts.AlertTracker()
    assert tracker.check_bmkg(latest, settings, RUTENG, NOW) == "nearby"
    assert tracker.check_usgs([strong_dup], settings, NOW) == []

    tracker = alerts.AlertTracker()
    assert [q["id"] for q in tracker.check_usgs([strong_dup], settings, NOW)] == ["us6000dup"]
    assert tracker.check_bmkg(latest, settings, RUTENG, NOW) is None
    # Tsunami potential is never held back.
    assert tracker.check_bmkg(dict(latest, potential="Berpotensi tsunami"), settings, RUTENG,
                              NOW) == "tsunami"


def test_tracker_survives_a_restart_and_prunes(api, alerts, latest):
    tracker = alerts.AlertTracker()
    settings = _settings(api, nearby_alerts=True)
    tracker.check_bmkg(latest, settings, RUTENG, NOW)
    assert tracker.changed
    restored = alerts.AlertTracker.from_json(_copy(tracker.to_json()))
    assert restored.check_bmkg(latest, settings, RUTENG, NOW + 60) is None
    restored.prune(NOW + 4 * 86400)
    assert restored.records["bmkg"] == {}
    assert alerts.AlertTracker.from_json("junk").records == {"bmkg": {}, "usgs": {}}
    odd = alerts.AlertTracker.from_json({"bmkg": {"x": {"announced": "yes", "lat": "a"}, 5: {}}})
    assert odd.records["bmkg"] == {"x": {"announced": False, "tsunami": False, "t": None,
                                         "lat": None, "lon": None}}


# ------------------------------------------------------------
# Text in both languages
# ------------------------------------------------------------

def test_latest_report_english(text, lang, latest):
    assert text.latest_report(latest, RUTENG, NOW) == (
        "Latest earthquake according to BMKG: magnitude 4.7, depth 9 kilometres, "
        "Pusat gempa berada di laut 48 km utara Ruteng-Manggarai. "
        "47 kilometres north of Ruteng. Time: 09:02 WIB, 10 minutes ago. "
        "Felt, on the MMI scale: II - III Kab. Manggarai. "
        "BMKG says: Gempa ini dirasakan untuk diteruskan pada masyarakat.")


def test_latest_report_indonesian(text, lang, latest):
    lang("id")
    assert text.latest_report(latest, RUTENG, NOW) == (
        "Gempa terkini menurut BMKG: magnitudo 4,7, kedalaman 9 kilometer, "
        "Pusat gempa berada di laut 48 km utara Ruteng-Manggarai. "
        "47 kilometer di sebelah utara Ruteng. Waktu: pukul 09:02 WIB, 10 menit yang lalu. "
        "Dirasakan (skala MMI): II - III Kab. Manggarai. "
        "BMKG menyatakan: Gempa ini dirasakan untuk diteruskan pada masyarakat.")


def test_latest_report_without_location_or_optional_fields(text, lang, latest):
    bare = dict(latest, depth_km=None, felt="", potential="")
    assert text.latest_report(bare, None, NOW) == (
        "Latest earthquake according to BMKG: magnitude 4.7, "
        "Pusat gempa berada di laut 48 km utara Ruteng-Manggarai. Time: 09:02 WIB, 10 minutes ago.")


def test_tsunami_report_starts_with_the_warning_and_keeps_bmkg_words(text, lang, tsunami_quake):
    report = text.latest_report(tsunami_quake, RUTENG, NOW, disclaimer=True)
    assert report.startswith("Tsunami potential, according to BMKG. Latest earthquake")
    assert "BMKG says: Berpotensi tsunami untuk diteruskan pada masyarakat." in report
    assert report.endswith("Hariku is not an official warning system. "
                           "Always follow BMKG and your local authorities.")
    alert = text.alert_text("tsunami", tsunami_quake, RUTENG, NOW)
    assert alert == (
        "Tsunami potential, according to BMKG. "
        "BMKG says: Berpotensi tsunami untuk diteruskan pada masyarakat. "
        "Earthquake: magnitude 7.1, depth 10 kilometres, "
        "Pusat gempa berada di laut 150 km BaratDaya Jember. "
        "850 kilometres west of Ruteng. Time: 09:05 WIB, 7 minutes ago.")
    lang("id")
    alert = text.alert_text("tsunami", tsunami_quake, RUTENG, NOW)
    assert alert.startswith("Berpotensi tsunami, menurut BMKG. "
                            "BMKG menyatakan: Berpotensi tsunami untuk diteruskan pada masyarakat.")
    # BMKG's Indonesian statement is kept as is in the English interface too.
    lang("en")
    assert "Berpotensi tsunami untuk diteruskan pada masyarakat" in text.alert_text(
        "tsunami", tsunami_quake, RUTENG, NOW)


def test_nearby_and_felt_alerts(text, lang, latest):
    assert text.alert_text("nearby", latest, RUTENG, NOW) == (
        "Earthquake near you, according to BMKG: magnitude 4.7, depth 9 kilometres, "
        "Pusat gempa berada di laut 48 km utara Ruteng-Manggarai. "
        "47 kilometres north of Ruteng. Time: 09:02 WIB, 10 minutes ago. "
        "Felt, on the MMI scale: II - III Kab. Manggarai. "
        "BMKG says: Gempa ini dirasakan untuk diteruskan pada masyarakat.")
    assert text.alert_text("felt", latest, RUTENG, NOW).startswith(
        "Earthquake felt in your region, according to BMKG: magnitude 4.7")
    lang("id")
    assert text.alert_text("nearby", latest, RUTENG, NOW).startswith(
        "Gempa di dekat Anda, menurut BMKG: magnitudo 4,7, kedalaman 9 kilometer")
    assert text.alert_text("felt", latest, RUTENG, NOW).startswith(
        "Gempa dirasakan di wilayah Anda, menurut BMKG:")


def test_world_alert_text(api, text, lang):
    japan = api.parse_usgs(_copy(USGS))[0]
    alert = text.world_alert_text([japan], None, NOW)
    assert alert.startswith("Strong earthquake, according to USGS: magnitude 6.8, depth 35 kilometres, "
                            "120 km S of Hachijo-jima, Japan. Time: ")
    assert ", 5 minutes ago." in alert
    assert alert.endswith("The flag alone does not mean a tsunami was generated.")
    lang("id")
    assert text.world_alert_text([japan], None, NOW).startswith("Gempa kuat, menurut USGS: magnitudo 6,8")


def test_row_texts(api, text, lang, latest, tsunami_quake):
    assert text.row_text(latest, RUTENG, NOW) == (
        "Magnitude 4.7, Pusat gempa berada di laut 48 km utara Ruteng-Manggarai, "
        "depth 9 kilometres, 09:02 WIB, 10 minutes ago, 47 kilometres north of Ruteng. "
        "Felt: II - III Kab. Manggarai.")
    old = api.parse_bmkg_list(_copy(TERKINI))[0]
    assert text.row_text(old, None, NOW) == (
        "Magnitude 5.2, 127 km BaratLaut TAHUNA-KEP.SANGIHE-SULUT, depth 10 kilometres, "
        "22 September, 06:48 WIB.")
    assert text.row_text(tsunami_quake, None, NOW).startswith(
        "Tsunami potential, according to BMKG. Magnitude 7.1")
    usgs_row = text.row_text(api.parse_usgs(_copy(USGS))[1], None, NOW)
    assert usgs_row.startswith("Magnitude 5.3, 51 km WSW of Arauco, Argentina, depth 122 kilometres")
    assert usgs_row.endswith(" Source: USGS.")
    lang("id")
    assert text.row_text(old, None, NOW) == (
        "Magnitudo 5,2, 127 km BaratLaut TAHUNA-KEP.SANGIHE-SULUT, kedalaman 10 kilometer, "
        "22 September, pukul 06:48 WIB.")


def test_details(api, text, lang, latest):
    assert text.details_lines(latest, RUTENG, NOW) == [
        "Magnitude: 4.7",
        "Time: 23 Sep 2026, 09:02:44 WIB (10 minutes ago)",
        "Location: Pusat gempa berada di laut 48 km utara Ruteng-Manggarai",
        "Coordinates: 8.21 LS, 120.61 BT",
        "Depth: 9 km",
        "Distance: 47 kilometres north of Ruteng",
        "Felt, on the MMI scale: II - III Kab. Manggarai",
        "BMKG says: Gempa ini dirasakan untuk diteruskan pada masyarakat",
        "Source: BMKG",
    ]
    assert text.details_speech(latest, None, NOW).startswith("Magnitude: 4.7. Time: 23 Sep 2026")
    lines = text.details_lines(api.parse_usgs(_copy(USGS))[0], None, NOW)
    assert lines[0] == "Magnitude: 6.8" and "Coordinates: 32.00; 139.70" in lines
    assert lines[-1] == "Source: USGS" and any("tsunami flag" in line for line in lines)
    lang("id")
    assert text.details_lines(latest, RUTENG, NOW)[-1] == "Sumber: BMKG"


def test_times_in_text(text, lang, latest):
    assert text.ago_text(30) == "just now"
    assert text.ago_text(61) == "1 minute ago"
    assert text.ago_text(3 * 3600 + 5) == "3 hours ago"
    assert text.when_text(latest, QUAKE_TIME + 3600) == "09:02 WIB, 1 hour ago"
    assert text.when_text(latest, QUAKE_TIME + 2 * 86400) == "23 September, 09:02 WIB"
    assert text.when_text(latest, QUAKE_TIME + 400 * 86400) == "23 September 2026, 09:02 WIB"
    lang("id")
    assert text.when_text(latest, QUAKE_TIME + 2 * 86400) == "23 September, pukul 09:02 WIB"
    assert text.ago_text(3 * 3600 + 5) == "3 jam yang lalu"


def test_briefing_sentence(text, lang, latest, tsunami_quake):
    assert text.briefing_sentence(latest, RUTENG, NOW) == (
        "Earthquake near you in the last 24 hours, according to BMKG: magnitude 4.7, "
        "47 kilometres north of Ruteng, 09:02 WIB, 10 minutes ago.")
    assert text.briefing_sentence(tsunami_quake, RUTENG, NOW).endswith(
        " BMKG reported tsunami potential for it.")
    lang("id")
    assert text.briefing_sentence(latest, RUTENG, NOW) == (
        "Gempa di dekat Anda dalam 24 jam terakhir, menurut BMKG: magnitudo 4,7, "
        "47 kilometer di sebelah utara Ruteng, pukul 09:02 WIB, 10 menit yang lalu.")


def test_disclaimer_attribution_and_errors(text, lang):
    assert text._("disclaimer") == ("Hariku is not an official warning system. "
                                    "Always follow BMKG and your local authorities.")
    assert text._("attribution") == ("Earthquake data: BMKG (Badan Meteorologi, Klimatologi, "
                                     "dan Geofisika) and USGS")
    assert "internet connection" in text.error_text("offline")
    assert text.error_text("weird") == text.error_text("bad_response")
    assert text.location_text(None, RUTENG) == \
        "Ruteng, East Nusa Tenggara, Indonesia (from the Weather settings)"
    assert text.location_text(None) == "Not set"
    lang("id")
    assert text._("disclaimer") == ("Hariku bukan sistem peringatan resmi. "
                                    "Selalu ikuti BMKG dan pihak berwenang setempat.")
    assert text.location_text(None, RUTENG).endswith("(dari pengaturan Cuaca)")


# ------------------------------------------------------------
# main.py: actions, alerts, polling, briefing, registration
# ------------------------------------------------------------

class _Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now


class _Timer:
    def __init__(self, seconds, callback):
        self.seconds, self.callback, self.stopped = seconds, callback, False

    def Stop(self):
        self.stopped = True


@pytest.fixture
def eqmain(monkeypatch, tmp_data_dir, api, alerts, text):
    """main.py with speech captured, threads run inline, timers and sounds
    recorded, a controllable clock and BMKG / USGS answered from samples."""
    spec = importlib.util.spec_from_file_location("earthquake_main_under_test",
                                                  os.path.join(EQ_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = _Clock(NOW)
    spoken, timers, sounds, urls = [], [], [], []
    monkeypatch.setattr(module, "speak",
                        lambda msg, interrupt=False: spoken.append((msg, interrupt)))
    monkeypatch.setattr(module, "_start_thread", lambda target, *args: target(*args))
    monkeypatch.setattr(module, "_wall", clock)

    def call_later(seconds, callback):
        timers.append(_Timer(seconds, callback))
        return timers[-1]

    monkeypatch.setattr(module, "_call_later", call_later)
    monkeypatch.setattr(module, "_play_sound", sounds.append)
    responses = {api.AUTOGEMPA_URL: _autogempa(), api.TERKINI_URL: TERKINI,
                 api.DIRASAKAN_URL: DIRASAKAN, api.USGS_DAY_URL: USGS, api.USGS_HOUR_URL: USGS}

    def fake_fetch_json(url):
        urls.append(url)
        answer = responses.get(url)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise AssertionError(f"unexpected URL {url}")
        return _copy(answer)

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    module._active = True
    module._settings = api.normalize_settings({"location": RUTENG})
    module._cache = api.empty_cache()
    module._tracker = alerts.AlertTracker()
    module._disclaimer_given = False
    module.spoken, module.timers, module.sounds, module.urls = spoken, timers, sounds, urls
    module.responses, module.clock = responses, clock
    yield module
    module._active = False


def _texts(eqmain):
    return [msg for msg, _interrupt in eqmain.spoken]


def test_latest_hotkey_fetches_then_speaks(eqmain, lang):
    eqmain.speak_latest()
    assert eqmain.urls == [eqmain.api.AUTOGEMPA_URL]
    assert eqmain.spoken[0] == ("Checking BMKG...", True)
    msg, interrupt = eqmain.spoken[1]
    assert interrupt and msg.startswith("Latest earthquake according to BMKG: magnitude 4.7")
    assert "47 kilometres north of Ruteng" in msg
    assert "Hariku is not an official warning system" not in msg   # not a tsunami
    # Fresh: answered from the cache.
    eqmain.clock.now += 10
    eqmain.speak_latest()
    assert len(eqmain.urls) == 1 and eqmain.spoken[-1][0] == msg
    assert eqmain.sounds == []


def test_latest_hotkey_offline(eqmain, api, lang, latest):
    eqmain.responses[api.AUTOGEMPA_URL] = api.QuakeError("offline")
    eqmain.speak_latest()
    assert _texts(eqmain) == ["Checking BMKG...",
                              "Could not reach the earthquake data service. "
                              "Check your internet connection."]
    eqmain._cache.update(latest=latest, latest_at=NOW - 3600)
    eqmain.speak_latest()
    last = _texts(eqmain)[-1]
    assert last.startswith("Could not reach the earthquake data service.")
    assert "Showing the last earthquake data from" in last and "magnitude 4.7" in last


def test_hotkey_with_tsunami_potential(eqmain, api, lang):
    eqmain.responses[api.AUTOGEMPA_URL] = _autogempa(**TSUNAMI)
    eqmain.speak_latest()
    msg, interrupt = eqmain.spoken[-1]
    assert interrupt and msg.startswith("Tsunami potential, according to BMKG.")
    assert msg.endswith("Always follow BMKG and your local authorities.")
    assert eqmain.sounds == [eqmain.TSUNAMI_SOUND]
    # Heard: the background check does not repeat it.
    eqmain._poll()
    assert len(eqmain.spoken) == 2


def test_tsunami_alert_first_urgent_with_sound_and_disclaimer_once(eqmain, api, lang):
    eqmain._settings = api.normalize_settings({"location": RUTENG})
    eqmain.responses[api.AUTOGEMPA_URL] = _autogempa(**TSUNAMI)
    eqmain._poll()
    assert len(eqmain.spoken) == 1
    msg, interrupt = eqmain.spoken[0]
    assert interrupt is True
    assert msg.startswith("Tsunami potential, according to BMKG. BMKG says: Berpotensi tsunami")
    assert msg.endswith("Hariku is not an official warning system. "
                        "Always follow BMKG and your local authorities.")
    assert eqmain.sounds == [eqmain.TSUNAMI_SOUND]
    # Polled again: announced once only.
    eqmain.clock.now += 60
    eqmain._poll()
    assert len(eqmain.spoken) == 1
    # The next alert of the session has no disclaimer.
    eqmain._settings = api.normalize_settings({"location": RUTENG, "nearby_alerts": True})
    eqmain.responses[api.AUTOGEMPA_URL] = _autogempa(DateTime="2026-09-23T02:11:00+00:00",
                                                     Jam="09:11:00 WIB")
    eqmain._poll()
    msg, interrupt = eqmain.spoken[-1]
    assert msg.startswith("Earthquake near you, according to BMKG") and interrupt is False
    assert "official warning system" not in msg
    assert eqmain.sounds == [eqmain.TSUNAMI_SOUND, eqmain.ALERT_SOUND]


def test_disclaimer_comes_with_the_first_alert_of_each_session(eqmain, api, lang, tmp_data_dir,
                                                               fresh_event_bus, monkeypatch):
    import core.hotkeys
    import core.preferences
    monkeypatch.setattr(core.hotkeys, "register_action", lambda *a, **k: None)
    monkeypatch.setattr(core.preferences, "register_panel", lambda *a, **k: None)
    eqmain._settings = api.normalize_settings({"location": RUTENG, "nearby_alerts": True})
    eqmain._poll()
    assert eqmain.spoken[-1][0].endswith("Always follow BMKG and your local authorities.")
    # A new session (restart): the next alert carries it again.
    eqmain.teardown()
    eqmain.register(fresh_event_bus)
    eqmain._settings = api.normalize_settings({"location": RUTENG, "nearby_alerts": True})
    eqmain.responses[api.AUTOGEMPA_URL] = _autogempa(DateTime="2026-09-23T02:11:00+00:00")
    eqmain._poll()
    assert len(eqmain.spoken) == 2
    assert eqmain.spoken[-1][0].endswith("Always follow BMKG and your local authorities.")
    eqmain.teardown()


def test_sounds_can_be_turned_off(eqmain, api, lang):
    eqmain._settings = api.normalize_settings({"location": RUTENG, "sounds": False})
    eqmain.responses[api.AUTOGEMPA_URL] = _autogempa(**TSUNAMI)
    eqmain._poll()
    assert eqmain.spoken and eqmain.sounds == []


def test_default_settings_only_announce_tsunami(eqmain, api, lang):
    eqmain._poll()                       # a felt M4.7 47 km away: not announced by default
    assert eqmain.spoken == []
    assert eqmain.urls == [api.AUTOGEMPA_URL]


def test_polling_interval_backoff_and_stop(eqmain, api):
    eqmain._update_polling()
    assert [t.seconds for t in eqmain.timers] == [eqmain.FIRST_POLL_SECONDS]
    eqmain.timers[-1].callback()
    assert eqmain.timers[-1].seconds == eqmain.POLL_SECONDS
    eqmain.responses[api.AUTOGEMPA_URL] = api.QuakeError("offline")
    delays = []
    for _ in range(6):
        eqmain.timers[-1].callback()
        delays.append(eqmain.timers[-1].seconds)
    assert delays == [120, 240, 480, 900, 900, 900]
    eqmain.responses[api.AUTOGEMPA_URL] = _autogempa()
    eqmain.timers[-1].callback()
    assert eqmain.timers[-1].seconds == eqmain.POLL_SECONDS
    # Every BMKG alert off: polling stops.
    eqmain._save_settings({"tsunami_alerts": False})
    assert eqmain._poll_timer is None and eqmain.timers[-1].stopped
    count = len(eqmain.urls)
    eqmain._poll()
    assert len(eqmain.urls) == count


def test_world_polling_is_opt_in(eqmain, api, lang):
    eqmain._update_polling()
    assert eqmain._world_timer is None
    eqmain._save_settings({"world_alerts": True})
    assert eqmain._world_timer is not None
    eqmain._world_timer.callback()
    assert eqmain.urls[-1] == api.USGS_HOUR_URL
    msg, interrupt = eqmain.spoken[-1]
    assert msg.startswith("Strong earthquake, according to USGS: magnitude 6.8") and not interrupt
    assert eqmain._world_timer.seconds == eqmain.WORLD_POLL_SECONDS
    eqmain._world_timer.callback()
    assert len(eqmain.spoken) == 1        # once
    eqmain._save_settings({"world_alerts": False})
    assert eqmain._world_timer is None


def test_one_request_in_flight(eqmain, api, monkeypatch):
    started = []
    monkeypatch.setattr(eqmain, "_start_thread", lambda target, *args: started.append(args))
    done = []
    assert eqmain.request("latest", done.append)
    assert eqmain.request("latest", done.append)
    assert eqmain.request("lists")
    assert eqmain.request("lists")
    assert started == [("latest",)] and eqmain._queue == ["lists"]
    latest = api.parse_autogempa(_autogempa())
    eqmain._on_job_done("latest", latest, None)
    assert done == [None, None]
    assert started == [("latest",), ("lists",)] and eqmain._queue == []
    eqmain._on_job_done("lists", [], "offline")
    assert eqmain._running is None


def test_refresh_list_waits_for_every_part(eqmain, api, lang):
    results = []
    assert eqmain.refresh_list(results.append)
    assert results == [None]
    assert eqmain.urls == [api.TERKINI_URL, api.DIRASAKAN_URL]
    eqmain.set_list_world(True)
    eqmain.refresh_list(results.append)
    assert eqmain.urls[-1] == api.USGS_DAY_URL
    quakes, updated = eqmain.list_data()
    assert updated == NOW and quakes[0]["id"] == "us7000japan"
    eqmain.responses[api.DIRASAKAN_URL] = api.QuakeError("service")
    eqmain.refresh_list(results.append)
    assert results[-1] == "service"


def test_show_recent_opens_the_list(eqmain, monkeypatch):
    opened = []

    class FakeDialog:
        def __init__(self, parent, get_data, request_refresh, get_location, **kwargs):
            opened.append(kwargs)

        def ShowModal(self):
            return 0

        def Destroy(self):
            pass

    monkeypatch.setattr(eqmain.earthquake_ui, "RecentDialog", FakeDialog)
    eqmain.show_recent()
    assert opened[0]["refresh_now"] is True and opened[0]["list_world"] is False


def test_weather_location_is_the_default(eqmain, api):
    import core.api
    eqmain._settings = api.normalize_settings({})
    assert eqmain.get_location() is None
    core.api.save_data("Weather", {"location": JAKARTA, "units": "metric"})
    assert eqmain.get_location()["name"] == "Jakarta"
    eqmain._settings = api.normalize_settings({"location": RUTENG})
    assert eqmain.get_location()["name"] == "Ruteng"


def test_briefing_uses_the_cache_only(eqmain, api, lang, latest):
    lines = []
    eqmain._on_briefing_collect(lines)
    assert lines == [] and eqmain.urls == []          # nothing cached, nothing fetched
    eqmain._cache["history"] = [latest]
    eqmain._on_briefing_collect(lines)
    assert lines == ["Earthquake near you in the last 24 hours, according to BMKG: magnitude 4.7, "
                     "47 kilometres north of Ruteng, 09:02 WIB, 10 minutes ago."]
    lines = []
    eqmain.clock.now = NOW + 2 * 86400
    eqmain._on_briefing_collect(lines)
    assert lines == []                                # older than a day
    eqmain.clock.now = NOW
    eqmain._settings = api.normalize_settings({"location": JAKARTA})
    eqmain._on_briefing_collect(lines)
    assert lines == []                                # far away
    eqmain._settings = api.normalize_settings({})
    eqmain._on_briefing_collect(lines)
    assert lines == [] and eqmain.urls == []


def test_polling_keeps_a_history_for_the_briefing(eqmain, api):
    import core.api
    eqmain._poll()
    assert [q["id"] for q in eqmain._cache["history"]] == ["2026-09-23T02:02:44+00:00"]
    saved = api.normalize_cache(core.api.load_data(eqmain.CACHE_KEY))
    assert saved["latest"]["id"] == "2026-09-23T02:02:44+00:00"
    stored = core.api.load_data(eqmain.ALERTS_KEY)
    assert "2026-09-23T02:02:44+00:00" in stored["bmkg"]


def test_register_and_teardown(eqmain, fresh_event_bus, monkeypatch, tmp_data_dir):
    import core.api
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *args, **kwargs: panels.append(args))
    # Corrupt files on disk must not stop the extension from loading.
    for key in (eqmain.DATA_KEY, eqmain.CACHE_KEY, eqmain.ALERTS_KEY):
        with open(core.api.get_data_path(key), "w", encoding="utf-8") as f:
            f.write("{not json")

    eqmain.register(fresh_event_bus)
    assert eqmain._settings["tsunami_alerts"] is True and eqmain._cache["latest"] is None
    for event_name, handler in eqmain._SUBSCRIPTIONS:
        assert handler in fresh_event_bus._listeners[event_name]
    by_name = {args[1]: (args, kwargs) for args, kwargs in actions}
    latest_args, latest_kwargs = by_name["speak_latest"]
    assert latest_args[0] == "Earthquakes" and latest_args[3] == ord("G")
    assert latest_args[4] is False and latest_kwargs == {}
    recent_args, recent_kwargs = by_name["show_recent"]
    assert recent_args[0] == "Earthquakes" and recent_args[3] == ord("G")
    assert recent_kwargs == {"default_shift": True}
    assert len(panels) == 1
    # Tsunami alerts are on by default, so the BMKG poll is scheduled.
    poll = eqmain._poll_timer
    assert poll is not None and poll.seconds == eqmain.FIRST_POLL_SECONDS

    eqmain.teardown()
    for event_name, handler in eqmain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    assert not eqmain._active and poll.stopped and eqmain._poll_timer is None
    assert eqmain.request("latest") is False


def test_network_back_online_polls_soon(eqmain, api):
    eqmain._update_polling()
    eqmain.responses[api.AUTOGEMPA_URL] = api.QuakeError("offline")
    eqmain.timers[-1].callback()
    eqmain.timers[-1].callback()
    assert eqmain.timers[-1].seconds == 240
    eqmain._on_network_changed(True)
    assert eqmain.timers[-1].seconds == eqmain.FIRST_POLL_SECONDS and eqmain._poll_failures == 0
    eqmain._on_network_changed(False)
    assert eqmain.timers[-1].seconds == eqmain.FIRST_POLL_SECONDS


# ------------------------------------------------------------
# Settings page: "Use the Weather location" (the panel's methods run on a
# stand-in, since wx is mocked here; tests/_earthquake_ui_check.py presses the
# real button in CI)
# ------------------------------------------------------------

class _Ctrl:
    """Records what the panel does to one control."""

    def __init__(self, value="", selection=-1):
        self.value, self.selection, self.label, self.calls = value, selection, "", []

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        self.calls.append("SetValue")
        self.value = value

    def ChangeValue(self, value):
        self.calls.append("ChangeValue")
        self.value = value

    def GetSelection(self):
        return self.selection

    def SetSelection(self, index):
        self.calls.append("SetSelection")
        self.selection = index

    def SetLabel(self, label):
        self.label = label

    def SetFocus(self):
        self.calls.append("SetFocus")


@pytest.fixture
def eq_ui(text):
    import earthquake_ui
    return earthquake_ui


def _page(location, weather_location, results=()):
    return types.SimpleNamespace(
        _location=location, _weather_location=weather_location, _results=list(results),
        _pending="place" if results else None,
        list_results=_Ctrl(selection=0 if results else -1), txt_location=_Ctrl(),
        txt_felt_names=_Ctrl(""), lbl_felt_note=_Ctrl(), btn_use_weather=_Ctrl())


class _Event:
    def __init__(self):
        self.skipped = False

    def Skip(self):
        self.skipped = True


def test_use_the_weather_location_button(eq_ui, lang, monkeypatch):
    spoken = []
    monkeypatch.setattr(eq_ui, "speak", lambda msg, interrupt=False: spoken.append((msg, interrupt)))
    Panel = eq_ui.EarthquakePanel
    page = _page(JAKARTA, RUTENG, results=[JAKARTA])
    assert Panel.chosen_location(page) is JAKARTA

    Panel._on_use_weather(page, None)
    # The page's own city is dropped: OK saves None, so the Weather city is used.
    assert Panel.chosen_location(page) is None
    assert page.txt_location.value == \
        "Ruteng, East Nusa Tenggara, Indonesia (from the Weather settings)"
    assert "SetValue" in page.txt_location.calls   # Preferences sees a change to save
    assert page.list_results.selection == eq_ui.wx.NOT_FOUND
    assert page.lbl_felt_note.label == \
        "Felt alerts look for these names in BMKG's felt reports: Ruteng, Manggarai."
    assert spoken == [("Ruteng, East Nusa Tenggara, Indonesia, the Weather location, will be "
                       "used. Press OK to save.", True)]
    # Focus never moves.
    for ctrl in (page.list_results, page.txt_location, page.btn_use_weather):
        assert "SetFocus" not in ctrl.calls

    # Choosing a search result again takes over.
    page.list_results.selection = 0
    event = _Event()
    Panel._on_result_selected(page, event)
    assert event.skipped and Panel.chosen_location(page) is JAKARTA

    # Without a Weather location.
    page = _page(JAKARTA, None)
    Panel._on_use_weather(page, None)
    assert Panel.chosen_location(page) is None and page.txt_location.value == "Not set"
    assert spoken[-1] == ("No Weather location is set yet. Choose one here, or in Preferences, "
                          "Weather.", True)

    lang("id")
    Panel._on_use_weather(_page(None, RUTENG), None)
    assert spoken[-1][0] == ("Ruteng, East Nusa Tenggara, Indonesia, lokasi Cuaca, akan digunakan. "
                             "Tekan Oke untuk menyimpan.")
    assert eq_ui._("btn_use_weather") == "&Gunakan lokasi Cuaca"


def test_no_selection_keeps_the_saved_location(eq_ui):
    page = _page(JAKARTA, RUTENG)
    assert eq_ui.EarthquakePanel.chosen_location(page) is JAKARTA
    page = _page(None, RUTENG)
    assert eq_ui.EarthquakePanel.chosen_location(page) is None


def test_settings_page_alt_letters_do_not_clash():
    # Every control on the settings page whose label can carry an Alt letter.
    keys = ("btn_search", "btn_use_weather", "chk_tsunami", "chk_nearby", "chk_felt",
            "chk_world", "chk_sounds", "lbl_current_location", "lbl_search", "lbl_results",
            "lbl_alert_distance", "lbl_min_magnitude", "lbl_felt_names", "disclaimer",
            "alerts_note", "attribution", "attribution_search")
    expected = {"en": "w", "id": "g"}
    for code in ("en", "id"):
        with open(os.path.join(EQ_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            messages = json.load(f)["messages"]
        letters = [m.group(1).lower() for key in keys
                   for m in re.finditer(r"&([^&\s])", messages[key])]
        assert len(letters) == len(set(letters)), (code, letters)
        assert re.search(r"&(.)", messages["btn_use_weather"]).group(1).lower() == expected[code]


def test_applying_use_weather_saves_no_city(eqmain, lang):
    import core.api
    core.api.save_data("Weather", {"location": RUTENG, "units": "metric"})
    eqmain._settings = eqmain.api.normalize_settings({"location": JAKARTA})
    assert eqmain.get_location()["name"] == "Jakarta"
    shown = []
    eqmain._panel = types.SimpleNamespace(
        get_settings=lambda: dict(eqmain.get_settings(), location=None),
        set_location=lambda place, weather: shown.append((place, weather)))
    eqmain._apply_panel()
    assert core.api.load_data(eqmain.DATA_KEY)["location"] is None
    assert eqmain.get_location()["name"] == "Ruteng"
    place, weather = shown[-1]
    assert place is None and weather["name"] == "Ruteng"
    assert eqmain.text.location_text(place, weather) == \
        "Ruteng, East Nusa Tenggara, Indonesia (from the Weather settings)"
    eqmain._panel = None
