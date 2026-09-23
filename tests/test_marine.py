# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Sea Conditions extension: Marine API parsing (inland nulls
# included), high and low tides, text in both languages, the high-wave alert,
# the cache, the briefing, and the actions. No test touches the network; the
# fetch functions are replaced.

import datetime
import importlib.util
import json
import math
import os
import sys
import urllib.error
import urllib.parse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARINE_DIR = os.path.join(ROOT, "extensions", "marine")

# Real sea level for Jakarta Bay (Open-Meteo, 22-24 September 2026), hourly from
# 22 September 00:00 WIB. Note the equal hours at the tops and bottoms.
SEA_LEVEL = [
    0.51, 0.41, 0.33, 0.31, 0.32, 0.36, 0.41, 0.48, 0.55, 0.61, 0.67, 0.72,
    0.75, 0.76, 0.78, 0.82, 0.87, 0.9, 0.92, 0.92, 0.89, 0.83, 0.74, 0.65,
    0.54, 0.42, 0.34, 0.3, 0.3, 0.33, 0.39, 0.44, 0.5, 0.56, 0.61, 0.65,
    0.68, 0.7, 0.72, 0.74, 0.79, 0.85, 0.88, 0.88, 0.86, 0.81, 0.73, 0.63,
    0.53, 0.44, 0.35, 0.3, 0.3, 0.35, 0.41, 0.47, 0.53, 0.59, 0.63, 0.67,
    0.7, 0.73, 0.75, 0.76, 0.81, 0.87, 0.92, 0.93, 0.9, 0.85, 0.78, 0.7,
]


def _hours(start, count):
    return [(start + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(count)]


HOURS = _hours(datetime.datetime(2026, 9, 22), len(SEA_LEVEL))

# Trimmed real response (the shape verified against the live Marine API).
MARINE_JSON = {
    "latitude": -5.958336, "longitude": 106.875015, "generationtime_ms": 0.27,
    "utc_offset_seconds": 25200, "timezone": "Asia/Jakarta", "timezone_abbreviation": "GMT+7",
    "elevation": 0.0,
    "current_units": {"time": "iso8601", "interval": "seconds", "wave_height": "m",
                      "wave_direction": "°", "wave_period": "s", "swell_wave_height": "m",
                      "sea_surface_temperature": "°C"},
    "current": {"time": "2026-09-23T19:15", "interval": 900, "wave_height": 0.32,
                "wave_direction": 45, "wave_period": 3.2, "swell_wave_height": 0.22,
                "sea_surface_temperature": 30.3},
    "hourly_units": {"time": "iso8601", "sea_level_height_msl": "m"},
    "hourly": {"time": HOURS, "sea_level_height_msl": SEA_LEVEL},
    "daily_units": {"time": "iso8601", "wave_height_max": "m", "wave_direction_dominant": "°",
                    "wave_period_max": "s", "swell_wave_height_max": "m"},
    "daily": {"time": ["2026-09-22", "2026-09-23", "2026-09-24"],
              "wave_height_max": [0.52, 0.36, 0.66], "wave_direction_dominant": [52, 46, 52],
              "wave_period_max": [4.2, 4.5, 3.9], "swell_wave_height_max": [0.38, 0.28, 0.38]},
}

# An inland point: the same shape, every value null.
INLAND_JSON = {
    "latitude": -6.92, "longitude": 107.6, "utc_offset_seconds": 25200, "timezone": "Asia/Jakarta",
    "current": {"time": "2026-09-23T19:15", "interval": 900, "wave_height": None,
                "wave_direction": None, "wave_period": None, "swell_wave_height": None,
                "sea_surface_temperature": None},
    "hourly": {"time": HOURS[:24], "sea_level_height_msl": [None] * 24},
    "daily": {"time": ["2026-09-22"], "wave_height_max": [None], "wave_direction_dominant": [None],
              "wave_period_max": [None], "swell_wave_height_max": [None]},
}

GEOCODING_JSON = {"results": [
    {"id": 1, "name": "Tanjung Priok", "latitude": -6.1, "longitude": 106.88, "country_code": "ID",
     "timezone": "Asia/Jakarta", "country": "Indonesia", "admin1": "Jakarta"},
    {"id": 2, "name": "Nowhere", "latitude": "north"},
]}

# 12:15 UTC is 19:15 in Jakarta on 23 September, the sample's "now".
NOW_UTC = datetime.datetime(2026, 9, 23, 12, 15, tzinfo=datetime.timezone.utc)

PRIOK = {"name": "Tanjung Priok", "admin1": "Jakarta", "country": "Indonesia",
         "latitude": -6.1, "longitude": 106.88, "timezone": "Asia/Jakarta"}
BANDUNG = {"name": "Bandung", "admin1": "West Java", "country": "Indonesia",
           "latitude": -6.9175, "longitude": 107.6191, "timezone": "Asia/Jakarta"}


def _import_helpers():
    if MARINE_DIR not in sys.path:
        sys.path.insert(0, MARINE_DIR)
    import marine_api
    import marine_text
    import marine_tides
    return marine_api, marine_tides, marine_text


@pytest.fixture(scope="module")
def api():
    return _import_helpers()[0]


@pytest.fixture(scope="module")
def tides():
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


def _copy(data):
    return json.loads(json.dumps(data))


@pytest.fixture
def forecast(api):
    return api.parse_marine(_copy(MARINE_JSON))


@pytest.fixture
def inland(api):
    return api.parse_marine(_copy(INLAND_JSON))


@pytest.fixture
def mmain(monkeypatch, tmp_data_dir, api, text):
    """Sea Conditions' main.py with speech and sounds captured and the fetch
    thread run inline."""
    spec = importlib.util.spec_from_file_location("marine_main_under_test",
                                                  os.path.join(MARINE_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken, sounds = [], []
    monkeypatch.setattr(module, "speak", lambda msg, interrupt=False: spoken.append(msg))
    monkeypatch.setattr(module, "_play_sound", sounds.append)
    monkeypatch.setattr(module, "_start_thread", lambda target, *args: target(*args))
    module._active = True
    module.spoken = spoken
    module.sounds = sounds
    yield module
    module._active = False


def _fetch_calls(monkeypatch, api, response=None, error=None):
    calls = []

    def fake_fetch_json(url):
        calls.append(url)
        if error:
            raise api.MarineError(error)
        return _copy(response)

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    return calls


def _set(mmain, location=PRIOK, **settings):
    mmain._settings = dict(mmain.api.normalize_settings(None),
                           location=dict(location) if location else None, **settings)


# ------------------------------------------------------------
# Locale files
# ------------------------------------------------------------

def test_locales_have_the_same_keys():
    keys = {}
    for code in ("en", "id"):
        with open(os.path.join(MARINE_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            keys[code] = set(json.load(f)["messages"])
    assert keys["en"] == keys["id"]


def test_every_sea_state_and_direction_is_translated(text, lang):
    keys = [key for _limit, key in text.SEA_STATES]
    keys += ["dir_n", "dir_ne", "dir_e", "dir_se", "dir_s", "dir_sw", "dir_w", "dir_nw"]
    for code in ("en", "id"):
        lang(code)
        for key in keys:
            assert text._(key) != key, (code, key)


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def test_parse_marine(forecast):
    assert forecast["timezone"] == "Asia/Jakarta" and forecast["utc_offset_seconds"] == 25200
    assert forecast["current"] == {"time": "2026-09-23T19:15", "wave_height": 0.32,
                                   "wave_direction": 45.0, "wave_period": 3.2,
                                   "swell_height": 0.22, "sea_temperature": 30.3}
    assert [d["date"] for d in forecast["daily"]] == ["2026-09-22", "2026-09-23", "2026-09-24"]
    assert forecast["daily"][1] == {"date": "2026-09-23", "wave_max": 0.36, "direction": 46.0,
                                    "period_max": 4.5, "swell_max": 0.28}
    assert forecast["sea_level"][0] == ["2026-09-22T00:00", 0.51]
    assert len(forecast["sea_level"]) == 72
    assert forecast["has_data"] is True


def test_inland_point_is_no_data_not_an_error(inland):
    assert inland["has_data"] is False
    assert inland["current"]["wave_height"] is None
    assert all(level is None for _hour, level in inland["sea_level"])


def test_partial_data_still_counts(api):
    payload = _copy(INLAND_JSON)
    payload["current"]["sea_surface_temperature"] = 29.1   # a coastal cell with SST only
    assert api.parse_marine(payload)["has_data"] is True


@pytest.mark.parametrize("payload", [
    None, [], "text", {}, {"current": "x"}, {"hourly": {}},
])
def test_parse_marine_rejects_unusable_data(api, payload):
    with pytest.raises(api.MarineError) as info:
        api.parse_marine(payload)
    assert info.value.kind == "bad_response"


def test_parse_marine_tolerates_short_and_odd_columns(api):
    payload = _copy(MARINE_JSON)
    payload["daily"]["wave_height_max"] = [0.52]
    del payload["daily"]["swell_wave_height_max"]
    payload["hourly"]["time"] = payload["hourly"]["time"][:5] + ["garbage"]
    payload["hourly"]["sea_level_height_msl"] = [0.5, "x", None, True, 0.4]
    parsed = api.parse_marine(payload)
    assert parsed["daily"][1]["wave_max"] is None and parsed["daily"][0]["swell_max"] is None
    assert [level for _h, level in parsed["sea_level"]] == [0.5, None, None, None, 0.4]


def test_parse_places(api):
    places = api.parse_places(GEOCODING_JSON)
    assert places == [PRIOK]
    assert api.place_label(places[0]) == "Tanjung Priok, Jakarta, Indonesia"
    assert api.parse_places(None) == [] and api.parse_places({}) == []


def test_request_urls_send_only_the_place_and_what_is_needed(api):
    url = api.build_marine_url(-6.100001234, 106.88, "Asia/Jakarta")
    assert url.startswith("https://marine-api.open-meteo.com/v1/marine?")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query == {
        "latitude": ["-6.1000"], "longitude": ["106.8800"],
        "current": ["wave_height,wave_direction,wave_period,swell_wave_height,sea_surface_temperature"],
        "hourly": ["sea_level_height_msl"],
        "daily": ["wave_height_max,wave_direction_dominant,wave_period_max,swell_wave_height_max"],
        "timezone": ["Asia/Jakarta"], "past_days": ["1"], "forecast_days": ["7"],
    }
    assert "timezone=auto" in api.build_marine_url(1, 2)
    url = api.build_search_url(" Pelabuhan Ratu ", "id")
    assert url.startswith("https://geocoding-api.open-meteo.com/v1/search?")
    assert "name=Pelabuhan+Ratu&" in url and "language=id" in url and "count=10" in url


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
    assert seen["agent"].startswith("HarikuV2/") and seen["agent"].endswith("(Marine extension)")
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
    with pytest.raises(api.MarineError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == kind


def test_fetch_json_rejects_bad_and_huge_bodies(api, monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b"<html>oops</html>"))
    with pytest.raises(api.MarineError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == "bad_response"
    monkeypatch.setattr(api.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b" " * (api.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(api.MarineError):
        api.fetch_json("https://example.invalid/")


# ------------------------------------------------------------
# Tides
# ------------------------------------------------------------

def _series(levels, start=datetime.datetime(2026, 9, 23)):
    return [[hour, level] for hour, level in zip(_hours(start, len(levels)), levels)]


def _summary(found):
    return [(t["kind"], t["time"].strftime("%d %H:%M"), t["level"]) for t in found]


def test_tides_of_the_real_sample(tides, forecast):
    found = tides.find_tides(forecast["sea_level"])
    # The first fall (from 00:00) can't be confirmed, so the list starts at a low.
    assert _summary(found) == [
        ("low", "22 03:10", 0.31),     # 0.33, 0.31, 0.32: turns a little after 03:00
        ("high", "22 18:30", 0.92),    # 0.92 at 18:00 and 19:00: the middle
        ("low", "23 03:30", 0.3),
        ("high", "23 18:30", 0.88),
        ("low", "24 03:30", 0.3),
        ("high", "24 18:45", 0.93),    # 0.92, 0.93, 0.90: a little before 19:00
    ]


def test_next_tides_and_trend(tides, forecast):
    found = tides.find_tides(forecast["sea_level"])
    now = datetime.datetime(2026, 9, 23, 19, 15)
    assert tides.trend(found, now) == "falling"
    assert tides.next_tide(found, now, "low")["time"] == datetime.datetime(2026, 9, 24, 3, 30)
    assert tides.next_tide(found, now, "high")["time"] == datetime.datetime(2026, 9, 24, 18, 45)
    morning = datetime.datetime(2026, 9, 23, 9, 0)
    assert tides.trend(found, morning) == "rising"
    assert tides.next_tide(found, morning, "high")["time"] == datetime.datetime(2026, 9, 23, 18, 30)
    assert tides.next_tide(found, morning, "low")["time"] == datetime.datetime(2026, 9, 24, 3, 30)
    assert tides.trend(found, datetime.datetime(2026, 9, 25)) is None   # past the data


def test_semidiurnal_tide_times_are_found_between_hours(tides):
    # A 12.42-hour tide, 0.8 m high, peaking at 02:30 on the 23rd.
    period, peak = 12.42, 2.5
    levels = [round(0.8 * math.cos(2 * math.pi * (h - peak) / period), 2) for h in range(60)]
    found = tides.find_tides(_series(levels))
    kinds = [t["kind"] for t in found]
    assert kinds == ["high", "low", "high", "low", "high", "low", "high", "low", "high"]
    start = datetime.datetime(2026, 9, 23)
    for n, tide in enumerate(found):
        expected = start + datetime.timedelta(hours=peak + n * period / 2)
        assert abs((tide["time"] - expected).total_seconds()) < 12 * 60, (n, tide, expected)
        assert abs(abs(tide["level"]) - 0.8) < 0.05


def test_flat_tops_count_once_in_their_middle(tides):
    found = tides.find_tides(_series([0.1, 0.5, 0.9, 0.9, 0.9, 0.5, 0.1, 0.1, 0.5]))
    assert _summary(found) == [("high", "23 03:00", 0.9), ("low", "23 06:30", 0.1)]


def test_small_wobbles_are_not_tides(tides):
    levels = [0.1, 0.3, 0.5, 0.49, 0.6, 0.8, 0.6, 0.3, 0.32, 0.1, 0.4]
    found = tides.find_tides(_series(levels))
    assert [(t["kind"], t["level"]) for t in found] == [("high", 0.8), ("low", 0.1)]
    assert found[0]["time"] == datetime.datetime(2026, 9, 23, 5, 0)   # symmetric: on the hour


def test_the_higher_of_two_close_peaks_is_the_high_tide(tides):
    found = tides.find_tides(_series([0.2, 0.6, 0.95, 0.93, 0.94, 0.91, 0.5, 0.2, 0.5]))
    assert [(t["kind"], t["level"]) for t in found] == [("high", 0.95), ("low", 0.2)]


def test_no_tide_is_invented_across_missing_data(tides):
    assert tides.find_tides(_series([0.1, 0.5, 0.9, None, 0.5, 0.1])) == []
    # A gap in the hours splits the series too.
    series = _series([0.1, 0.5, 0.9]) + _series([0.5, 0.1], datetime.datetime(2026, 9, 23, 6))
    assert tides.find_tides(series) == []


@pytest.mark.parametrize("sea_level", [
    [], None, [[h, None] for h in HOURS[:24]], [["bad", 0.3], ["2026-09-23T01:00"], "x"],
    _series([0.5] * 24), _series([0.5, 0.52, 0.5, 0.52, 0.5]),
])
def test_no_tides_without_usable_data(tides, sea_level):
    assert tides.find_tides(sea_level) == []


def test_round_time(tides):
    t = datetime.datetime
    assert tides.round_time(t(2026, 9, 23, 18, 45)) == t(2026, 9, 23, 18, 50)
    assert tides.round_time(t(2026, 9, 23, 18, 44, 59)) == t(2026, 9, 23, 18, 40)
    assert tides.round_time(t(2026, 9, 23, 23, 57)) == t(2026, 9, 24, 0, 0)


# ------------------------------------------------------------
# Text
# ------------------------------------------------------------

def test_current_report_english(text, lang, forecast):
    assert text.current_report(PRIOK, forecast, NOW_UTC) == (
        "Tanjung Priok: Waves 0.3 metres, smooth, from the northeast, period 3 seconds. "
        "Swell 0.2 metres. Sea temperature 30 degrees. "
        "The tide is falling: low tide tomorrow at about 03:30, high tide tomorrow at about 18:50.")


def test_current_report_indonesian(text, lang, forecast):
    lang("id")
    assert text.current_report(PRIOK, forecast, NOW_UTC) == (
        "Tanjung Priok: Gelombang 0,3 meter, tenang, dari timur laut, periode 3 detik. "
        "Alun 0,2 meter. Suhu laut 30 derajat. "
        "Air laut sedang turun: surut besok sekitar pukul 03:30, pasang besok sekitar pukul 18:50.")


def test_current_report_in_the_morning_has_both_tides_today(text, lang, forecast):
    morning = datetime.datetime(2026, 9, 23, 2, 0, tzinfo=datetime.timezone.utc)  # 09:00 WIB
    assert text.current_report(PRIOK, forecast, morning).endswith(
        "The tide is rising: high tide at about 18:30, low tide tomorrow at about 03:30.")


def test_current_report_skips_missing_values(text, lang, forecast):
    forecast["current"].update(wave_direction=None, wave_period=None, swell_height=None,
                               sea_temperature=None)
    later = NOW_UTC + datetime.timedelta(days=5)   # past the tide data
    assert text.current_report(PRIOK, forecast, later) == "Tanjung Priok: Waves 0.3 metres, smooth."


def test_inland_report(text, lang, inland):
    hint = "No sea data for Bandung. Choose a beach or port in Preferences, Sea Conditions."
    assert text.current_report(BANDUNG, inland, NOW_UTC) == hint
    assert text.briefing_sentence(BANDUNG, inland, NOW_UTC) == ""
    lang("id")
    assert text.current_report(BANDUNG, inland, NOW_UTC).startswith("Tidak ada data laut untuk Bandung.")


def test_briefing_sentence(text, lang, forecast):
    assert text.briefing_sentence(PRIOK, forecast, NOW_UTC) == (
        "Sea at Tanjung Priok: waves 0.3 metres, smooth, next high tide tomorrow at about 18:50.")
    lang("id")
    assert text.briefing_sentence(PRIOK, forecast, NOW_UTC) == (
        "Laut di Tanjung Priok: gelombang 0,3 meter, tenang, pasang berikutnya besok sekitar pukul 18:50.")


def test_day_rows(text, lang, forecast):
    assert text.day_rows(forecast, NOW_UTC) == [
        "Today, Wednesday 23 September: waves up to 0.4 metres, smooth, from the northeast, "
        "period up to 5 seconds, swell up to 0.3 metres; tides: low about 03:30, high about 18:30.",
        "Tomorrow, Thursday 24 September: waves up to 0.7 metres, slight, from the northeast, "
        "period up to 4 seconds, swell up to 0.4 metres; tides: low about 03:30, high about 18:50.",
    ]
    lang("id")
    assert text.day_rows(forecast, NOW_UTC)[0] == (
        "Hari ini, Rabu 23 September: gelombang hingga 0,4 meter, tenang, dari timur laut, "
        "periode hingga 5 detik, alun hingga 0,3 meter; pasang surut: surut sekitar 03:30, "
        "pasang sekitar 18:30.")


def test_tide_rows(text, lang, forecast):
    assert text.tide_rows(forecast, NOW_UTC) == [
        "Low tide tomorrow at about 03:30, 0.3 metres above mean sea level.",
        "High tide tomorrow at about 18:50, 0.9 metres above mean sea level.",
    ]
    earlier = NOW_UTC - datetime.timedelta(days=1)   # 22 September, 19:15
    rows = text.tide_rows(forecast, earlier)
    assert rows[0] == "Low tide tomorrow at about 03:30, 0.3 metres above mean sea level."
    assert rows[2] == "Low tide Thursday 24 September at about 03:30, 0.3 metres above mean sea level."
    lang("id")
    assert text.tide_rows(forecast, NOW_UTC)[1] == (
        "Pasang besok sekitar pukul 18:50, 0,9 meter di atas permukaan laut rata-rata.")


def test_numbers_and_words(text, lang):
    assert text.height_text(0.32) == "0.3 metres"
    assert text.height_text(0.25) == "0.3 metres"          # halves round up
    assert text.height_text(1.0) == "1 metre"
    assert text.height_text(2.04) == "2 metres"
    assert text.height_text(0.02) == "under 0.1 metres"
    assert text.height_text(12.4) == "12 metres"
    assert text.level_text(-0.34) == "0.3 metres below mean sea level"
    assert text.level_text(-0.01) == "0 metres above mean sea level"
    assert [text.sea_state(h) for h in (0.05, 0.3, 0.5, 1.25, 2.49, 2.5, 4.0, 6.0, 9.0, 14.0)] == [
        "calm", "smooth", "slight", "moderate", "moderate", "rough", "very rough", "high seas",
        "very high seas", "phenomenal seas"]
    assert [text.compass(d) for d in (0, 22, 23, 45, 180, 337, 338, 359.9)] == [
        "north", "north", "northeast", "northeast", "south", "northwest", "north", "north"]
    assert text.compass(None) is None
    lang("id")
    assert text.height_text(1.25) == "1,3 meter"
    assert text.sea_state(3.0) == "tinggi" and text.compass(225) == "barat daya"


def test_alert_height_choices(api, text, lang):
    assert [text.alert_height_choice(h) for h in api.ALERT_HEIGHTS] == [
        "1 metre, slight", "1.25 metres, moderate", "1.5 metres, moderate", "2 metres, moderate",
        "2.5 metres, rough", "3 metres, rough", "4 metres, very rough", "6 metres, high seas"]
    lang("id")
    assert text.alert_height_choice(1.25) == "1,25 meter, sedang"


def test_error_text(text, lang):
    assert "internet connection" in text.error_text("offline")
    assert "try again later" in text.error_text("service")
    assert text.error_text("weird") == text.error_text("bad_response")
    lang("id")
    assert "koneksi internet" in text.error_text("offline")


# ------------------------------------------------------------
# Alert rule, settings and cache
# ------------------------------------------------------------

def _rough(forecast, current=1.9, today_max=2.8):
    forecast["current"]["wave_height"] = current
    forecast["daily"][1]["wave_max"] = today_max
    return forecast


def test_alert_rule(api, forecast):
    rough = _rough(forecast)
    on = dict(api.normalize_settings(None), alert=True)
    assert api.should_alert(on, rough, "2026-09-23", NOW_UTC) == 2.8
    assert api.should_alert(dict(on, alert=False), rough, "2026-09-23", NOW_UTC) is None
    assert api.should_alert(dict(on, alert_date="2026-09-23"), rough, "2026-09-23", NOW_UTC) is None
    assert api.should_alert(dict(on, alert_date="2026-09-22"), rough, "2026-09-23", NOW_UTC) == 2.8
    assert api.should_alert(dict(on, alert_height=3.0), rough, "2026-09-23", NOW_UTC) is None
    # The current height counts too, and exactly the threshold is enough.
    calm_day = _rough(forecast, current=2.5, today_max=None)
    assert api.should_alert(on, calm_day, "2026-09-23", NOW_UTC) == 2.5


def test_no_alert_without_sea_data(api, inland):
    on = dict(api.normalize_settings(None), alert=True, alert_height=1.0)
    assert api.should_alert(on, inland, "2026-09-23", NOW_UTC) is None


def test_alert_text(text, lang):
    assert text.alert_text(PRIOK, 2.83) == "Sea alert for Tanjung Priok: waves up to 2.8 metres today, rough."
    lang("id")
    assert text.alert_text(PRIOK, 2.83) == (
        "Peringatan laut untuk Tanjung Priok: gelombang hingga 2,8 meter hari ini, tinggi.")


@pytest.mark.parametrize("raw", [
    None, "garbage", [], {}, {"location": "Jakarta"},
    {"location": {"name": "X", "latitude": "north", "longitude": 1}},
    {"alert": "yes", "alert_height": 2.7, "alert_date": 20260923},
])
def test_settings_survive_corrupt_data(api, raw):
    assert api.normalize_settings(raw) == {"location": None, "alert": False,
                                           "alert_height": 2.5, "alert_date": ""}


def test_settings_keep_valid_values(api):
    raw = {"location": PRIOK, "alert": True, "alert_height": 1.25, "alert_date": "2026-09-23",
           "extra": 1}
    assert api.normalize_settings(raw) == {"location": PRIOK, "alert": True, "alert_height": 1.25,
                                           "alert_date": "2026-09-23"}


def test_cache_freshness(api, forecast):
    cache = api.make_cache(PRIOK, forecast, now=1000.0)
    assert api.is_fresh(cache, 600, now=1599.0)
    assert not api.is_fresh(cache, 600, now=1601.0)
    assert not api.is_fresh(cache, 600, now=900.0)   # clock went backwards
    assert not api.is_fresh(None, 600) and not api.is_fresh({"fetched_at": "x"}, 600)
    assert api.cache_matches(cache, PRIOK)
    assert not api.cache_matches(cache, BANDUNG) and not api.cache_matches(None, PRIOK)


@pytest.mark.parametrize("raw", [
    None, "x", {}, {"fetched_at": 1, "latitude": 1, "longitude": 1},
    {"fetched_at": 1, "latitude": 1, "longitude": 1, "forecast": {"current": {}, "daily": []}},
    {"fetched_at": "x", "latitude": 1, "longitude": 1,
     "forecast": {"current": {}, "daily": [], "sea_level": []}},
])
def test_corrupt_cache_is_dropped(api, raw):
    assert api.normalize_cache(raw) is None


def test_valid_cache_is_kept(api, forecast, inland):
    cache = api.make_cache(PRIOK, forecast, now=5.0)
    assert api.normalize_cache(_copy(cache)) == cache
    cache = api.make_cache(BANDUNG, inland, now=5.0)
    assert api.normalize_cache(_copy(cache))["forecast"]["has_data"] is False


# ------------------------------------------------------------
# Actions (main.py)
# ------------------------------------------------------------

def test_no_location_speaks_where_to_set_it(mmain, lang, monkeypatch):
    _set(mmain, None)

    def no_dialog(*args, **kwargs):
        raise AssertionError("the forecast window must not open without a place")

    monkeypatch.setattr(mmain.marine_ui, "SeaForecastDialog", no_dialog)
    mmain.speak_sea_conditions()
    mmain.show_forecast()
    hint = "No sea location is set. Choose a beach or port in Preferences, Sea Conditions."
    assert mmain.spoken == [hint, hint]
    lang("id")
    mmain.speak_sea_conditions()
    assert mmain.spoken[-1].startswith("Lokasi laut belum diatur.")


def test_the_weather_city_is_the_default(mmain, api, tmp_data_dir):
    import core.api
    _set(mmain, None)
    assert mmain.get_location() is None
    core.api.save_data("Weather", {"location": BANDUNG, "units": "metric"})
    assert mmain.get_location() == BANDUNG
    _set(mmain, PRIOK)
    assert mmain.get_location() == PRIOK


def test_fresh_cache_is_spoken_without_fetching(mmain, api, forecast, lang, monkeypatch):
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set(mmain)
    mmain._cache = api.make_cache(PRIOK, forecast)
    mmain.speak_sea_conditions()
    assert calls == []
    assert len(mmain.spoken) == 1 and mmain.spoken[0].startswith("Tanjung Priok: Waves 0.3 metres")


def test_stale_cache_is_refreshed_then_spoken(mmain, api, forecast, lang, monkeypatch):
    import core.api
    calls = _fetch_calls(monkeypatch, api, response=MARINE_JSON)
    _set(mmain)
    mmain._cache = api.make_cache(PRIOK, forecast, now=1.0)
    mmain.speak_sea_conditions()
    assert len(calls) == 1 and "latitude=-6.1000" in calls[0]
    assert mmain.spoken[0] == "Getting the sea conditions..."
    assert mmain.spoken[1].startswith("Tanjung Priok: Waves 0.3 metres, smooth")
    assert api.is_fresh(mmain._cache, 60)
    assert api.normalize_cache(core.api.load_data(mmain.CACHE_KEY)) is not None


def test_inland_place_says_so(mmain, api, lang, monkeypatch):
    _fetch_calls(monkeypatch, api, response=INLAND_JSON)
    _set(mmain, BANDUNG)
    mmain._cache = None
    mmain.speak_sea_conditions()
    assert mmain.spoken[-1] == ("No sea data for Bandung. Choose a beach or port in "
                                "Preferences, Sea Conditions.")


def test_offline_falls_back_to_the_last_known_conditions(mmain, api, forecast, lang, monkeypatch):
    import time
    _fetch_calls(monkeypatch, api, error="offline")
    _set(mmain)
    mmain._cache = api.make_cache(PRIOK, forecast, now=time.time() - 2 * 3600)
    mmain.speak_sea_conditions()
    last = mmain.spoken[-1]
    assert last.startswith("Could not reach the sea data service.")
    assert "Showing the last sea conditions from" in last and "Tanjung Priok: Waves" in last


def test_offline_without_cache_says_so(mmain, api, lang, monkeypatch):
    _fetch_calls(monkeypatch, api, error="offline")
    _set(mmain)
    mmain._cache = None
    mmain.speak_sea_conditions()
    assert mmain.spoken == ["Getting the sea conditions...",
                            "Could not reach the sea data service. Check your internet connection."]


def test_one_fetch_at_a_time(mmain, monkeypatch):
    started = []
    monkeypatch.setattr(mmain, "_start_thread", lambda target, *args: started.append(args))
    _set(mmain)
    done = []
    assert mmain.refresh(done.append) and mmain.refresh(done.append) and mmain.refresh()
    assert len(started) == 1 and len(mmain._waiters) == 1
    mmain._on_fetched(None, "offline")
    assert done == ["offline"] and not mmain._loading


def test_background_refresh_backs_off_after_failures(mmain, api, monkeypatch):
    import time
    clock = [100000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set(mmain)
    mmain._cache = None

    mmain._on_minute_tick()
    assert len(calls) == 1
    clock[0] += 60
    mmain._on_minute_tick()
    assert len(calls) == 1                       # no retry a minute later
    clock[0] += mmain.RETRY_SECONDS
    mmain._on_minute_tick()
    assert len(calls) == 2                       # 10 minutes after one failure
    clock[0] += mmain.RETRY_SECONDS
    mmain._on_minute_tick()
    assert len(calls) == 2                       # two failures: 20 minutes
    clock[0] += mmain.RETRY_SECONDS
    mmain._on_minute_tick()
    assert len(calls) == 3
    for _ in range(10):                          # never more than 2 hours apart
        clock[0] += mmain.MAX_RETRY_SECONDS
        mmain._on_minute_tick()
    assert len(calls) == 13

    calls = _fetch_calls(monkeypatch, api, response=MARINE_JSON)
    clock[0] += mmain.MAX_RETRY_SECONDS
    mmain._on_minute_tick()
    assert len(calls) == 1 and mmain.current_cache() is not None and mmain._failures == 0
    clock[0] += mmain.RETRY_SECONDS
    mmain._on_minute_tick()
    assert len(calls) == 1                       # cache younger than 30 minutes
    clock[0] += mmain.REFRESH_SECONDS
    mmain._on_minute_tick()
    assert len(calls) == 2


def test_an_inland_place_is_rechecked_once_a_day(mmain, api, inland, monkeypatch):
    import time
    clock = [100000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    calls = _fetch_calls(monkeypatch, api, response=INLAND_JSON)
    _set(mmain, BANDUNG)
    mmain._cache = api.make_cache(BANDUNG, inland, now=clock[0])
    clock[0] += 3 * 3600
    mmain._on_minute_tick()
    assert calls == []
    clock[0] += 22 * 3600
    mmain._on_minute_tick()
    assert len(calls) == 1


def test_no_background_fetch_without_a_place(mmain, api, monkeypatch):
    calls = _fetch_calls(monkeypatch, api, response=MARINE_JSON)
    _set(mmain, None)
    mmain._on_minute_tick()
    mmain._on_app_startup()
    assert calls == []


def test_changing_the_place_fetches_it(mmain, api, forecast, monkeypatch):
    import core.api
    calls = _fetch_calls(monkeypatch, api, response=MARINE_JSON)
    _set(mmain)
    mmain._cache = api.make_cache(PRIOK, forecast)
    mmain._save_settings({"location": BANDUNG, "alert": False, "alert_height": 2.5})
    assert len(calls) == 1 and "latitude=-6.9175" in calls[0]
    saved = core.api.load_data(mmain.DATA_KEY)
    assert saved["location"]["name"] == "Bandung" and saved["alert"] is False
    # Back to the Weather city: nothing saved of our own, the Weather city is used.
    core.api.save_data("Weather", {"location": PRIOK})
    mmain._save_settings({"location": None})
    assert core.api.load_data(mmain.DATA_KEY)["location"] is None
    assert mmain.get_location() == PRIOK


def test_high_waves_are_announced_once_a_day(mmain, api, forecast, lang, monkeypatch):
    import core.api
    calls = _fetch_calls(monkeypatch, api, error="offline")
    day = ["2026-09-23"]
    monkeypatch.setattr(mmain, "_today", lambda: day[0])
    # High waves right now, so the real date doesn't matter.
    rough = _rough(forecast, current=2.83, today_max=None)
    _set(mmain, alert=True)
    mmain._cache = api.make_cache(PRIOK, rough)

    mmain._check_alert()
    assert mmain.spoken == ["Sea alert for Tanjung Priok: waves up to 2.8 metres today, rough."]
    assert mmain.sounds == [mmain.ALERT_SOUND]
    assert core.api.load_data(mmain.DATA_KEY)["alert_date"] == "2026-09-23"
    mmain._check_alert()
    mmain._on_app_startup()                      # a restart the same day
    assert len(mmain.spoken) == 1
    day[0] = "2026-09-24"
    mmain._check_alert()
    assert len(mmain.spoken) == 2 and calls == []


def test_no_alert_when_off_or_from_old_data(mmain, api, forecast, monkeypatch):
    import time
    _fetch_calls(monkeypatch, api, error="offline")
    rough = _rough(forecast, current=5.0, today_max=5.0)
    _set(mmain, alert=False)
    mmain._cache = api.make_cache(PRIOK, rough)
    mmain._check_alert()
    _set(mmain, alert=True)
    mmain._cache = api.make_cache(PRIOK, rough, now=time.time() - 2 * 3600)
    mmain._check_alert()
    assert mmain.spoken == [] and mmain.sounds == []


def test_switching_the_alert_on_with_old_data_fetches(mmain, api, forecast, monkeypatch):
    import time
    calls = _fetch_calls(monkeypatch, api, response=MARINE_JSON)
    _set(mmain)
    mmain._cache = api.make_cache(PRIOK, forecast, now=time.time() - 2 * 3600)
    mmain._save_settings({"alert": True, "alert_height": 1.0})
    assert len(calls) == 1


def test_briefing_contribution_uses_the_cache_only(mmain, api, forecast, inland, lang, monkeypatch):
    import time
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set(mmain)
    mmain._cache = api.make_cache(PRIOK, forecast)
    lines = []
    mmain._on_briefing_collect(lines)
    assert len(lines) == 1 and lines[0].startswith("Sea at Tanjung Priok: waves 0.3 metres, smooth")

    lines = []
    mmain._cache = api.make_cache(PRIOK, forecast, now=time.time() - 4 * 3600)
    mmain._on_briefing_collect(lines)
    assert lines == []                           # too old for this morning

    _set(mmain, BANDUNG)
    mmain._cache = api.make_cache(BANDUNG, inland)
    mmain._on_briefing_collect(lines)
    assert lines == []                           # inland: nothing to say

    _set(mmain, None)
    mmain._on_briefing_collect(lines)
    assert lines == [] and calls == []


def test_register_and_teardown(mmain, fresh_event_bus, monkeypatch, tmp_data_dir):
    import core.api
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *args, **kwargs: panels.append(args))
    for key in (mmain.DATA_KEY, mmain.CACHE_KEY):
        with open(core.api.get_data_path(key), "w", encoding="utf-8") as f:
            f.write("{not json")

    mmain.register(fresh_event_bus)
    assert mmain._settings["location"] is None and mmain._cache is None
    for event_name, handler in mmain._SUBSCRIPTIONS:
        assert handler in fresh_event_bus._listeners[event_name]
    by_name = {args[1]: (args, kwargs) for args, kwargs in actions}
    args, kwargs = by_name["speak_sea"]
    assert args[0] == "Sea Conditions" and args[3] == ord("O") and args[4] is False and kwargs == {}
    args, kwargs = by_name["show_forecast"]
    assert args[0] == "Sea Conditions" and args[3] == ord("O") and kwargs == {"default_shift": True}
    assert len(panels) == 1

    mmain.teardown()
    for event_name, handler in mmain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    assert not mmain._active
