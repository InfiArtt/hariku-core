# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Weather extension: Open-Meteo parsing, text in both languages,
# units, the cache, the actions, and which place it uses (core 2.8 Places). No
# test touches the network; the fetch functions are replaced.

import datetime
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEATHER_DIR = os.path.join(ROOT, "extensions", "weather")

# Trimmed real responses (Jakarta, 23 September 2026).
FORECAST_JSON = {
    "latitude": -6.25, "longitude": 106.875, "generationtime_ms": 0.08,
    "utc_offset_seconds": 25200, "timezone": "Asia/Jakarta",
    "timezone_abbreviation": "WIB", "elevation": 8.0,
    "current_units": {"time": "iso8601", "interval": "seconds", "temperature_2m": "°C",
                      "relative_humidity_2m": "%", "apparent_temperature": "°C",
                      "weather_code": "wmo code", "wind_speed_10m": "km/h"},
    "current": {"time": "2026-09-23T08:15", "interval": 900, "temperature_2m": 27.3,
                "relative_humidity_2m": 84, "apparent_temperature": 31.2,
                "weather_code": 61, "wind_speed_10m": 5.4},
    "daily_units": {"time": "iso8601", "weather_code": "wmo code",
                    "temperature_2m_max": "°C", "temperature_2m_min": "°C",
                    "precipitation_probability_max": "%"},
    "daily": {"time": ["2026-09-23", "2026-09-24", "2026-09-25"],
              "weather_code": [61, 3, 95],
              "temperature_2m_max": [31.0, 32.4, 30.1],
              "temperature_2m_min": [24.0, 24.6, 23.8],
              "precipitation_probability_max": [80, 10, None]},
}

GEOCODING_JSON = {
    "results": [
        {"id": 1642911, "name": "Jakarta", "latitude": -6.21462, "longitude": 106.84513,
         "elevation": 8.0, "feature_code": "PPLC", "country_code": "ID",
         "timezone": "Asia/Jakarta", "population": 8540121, "country": "Indonesia",
         "admin1": "Jakarta"},
        {"id": 4809537, "name": "Jakarta", "latitude": 38.1, "longitude": -80.2,
         "country_code": "US", "timezone": "America/New_York",
         "country": "United States", "admin1": "West Virginia"},
        {"id": 7, "name": "Nowhere", "latitude": "north"},
    ],
    "generationtime_ms": 0.6,
}

# 01:00 UTC is 08:00 in Jakarta on the sample's first day.
NOW_UTC = datetime.datetime(2026, 9, 23, 1, 0, tzinfo=datetime.timezone.utc)

JAKARTA = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
           "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"}
BANDUNG = {"name": "Bandung", "admin1": "West Java", "country": "Indonesia",
           "latitude": -6.9175, "longitude": 107.6191, "timezone": "Asia/Jakarta"}


def _import_helpers():
    if WEATHER_DIR not in sys.path:
        sys.path.insert(0, WEATHER_DIR)
    import weather_api
    import weather_text
    return weather_api, weather_text


@pytest.fixture(scope="module")
def api():
    return _import_helpers()[0]


@pytest.fixture(scope="module")
def text():
    return _import_helpers()[1]


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


@pytest.fixture
def forecast(api):
    return api.parse_forecast(json.loads(json.dumps(FORECAST_JSON)))


@pytest.fixture
def wmain(monkeypatch, tmp_data_dir, api, text):
    """Weather's main.py with speech captured and the fetch thread run inline."""
    spec = importlib.util.spec_from_file_location("weather_main_under_test",
                                                  os.path.join(WEATHER_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken = []
    monkeypatch.setattr(module, "speak", lambda msg, interrupt=False: spoken.append(msg))
    monkeypatch.setattr(module, "_start_thread", lambda target, *args: target(*args))
    module._active = True
    module.spoken = spoken
    yield module
    module._active = False


def _fetch_calls(monkeypatch, api, response=None, error=None):
    calls = []

    def fake_fetch_json(url):
        calls.append(url)
        if error:
            raise api.WeatherError(error)
        return json.loads(json.dumps(response))

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    return calls


# ------------------------------------------------------------
# Locale files
# ------------------------------------------------------------

def test_locales_have_the_same_keys():
    keys = {}
    for code in ("en", "id"):
        with open(os.path.join(WEATHER_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            keys[code] = set(json.load(f)["messages"])
    assert keys["en"] == keys["id"]


# ------------------------------------------------------------
# WMO codes
# ------------------------------------------------------------

def test_every_wmo_code_is_translated(text, lang):
    english = {}
    for code in text.KNOWN_CODES:
        english[code] = text.condition_text(code)
        assert english[code] != f"wmo_{code}"
    lang("id")
    for code in text.KNOWN_CODES:
        indonesian = text.condition_text(code)
        assert indonesian != f"wmo_{code}"
        assert indonesian != english[code]


@pytest.mark.parametrize("code, en, id_", [
    (0, "Clear sky", "Cerah"),
    (3, "Overcast", "Mendung"),
    (61, "Light rain", "Hujan ringan"),
    (95, "Thunderstorm", "Badai petir"),
    (42, "Unknown conditions", "Kondisi tidak diketahui"),
    (None, "Unknown conditions", "Kondisi tidak diketahui"),
])
def test_wmo_code_text(text, lang, code, en, id_):
    assert text.condition_text(code) == en
    lang("id")
    assert text.condition_text(code) == id_


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def test_parse_forecast(forecast):
    assert forecast["timezone"] == "Asia/Jakarta"
    assert forecast["utc_offset_seconds"] == 25200
    cur = forecast["current"]
    assert cur == {"time": "2026-09-23T08:15", "temperature": 27.3, "feels_like": 31.2,
                   "humidity": 84, "wind_speed": 5.4, "code": 61}
    assert [d["date"] for d in forecast["daily"]] == ["2026-09-23", "2026-09-24", "2026-09-25"]
    assert forecast["daily"][0] == {"date": "2026-09-23", "code": 61, "high": 31.0,
                                    "low": 24.0, "rain_chance": 80}
    assert forecast["daily"][2]["rain_chance"] is None


@pytest.mark.parametrize("payload", [
    None, [], "text", {}, {"current": "x"}, {"current": {"temperature_2m": None}},
    {"current": {"temperature_2m": "warm"}},
])
def test_parse_forecast_rejects_unusable_data(api, payload):
    with pytest.raises(api.WeatherError) as info:
        api.parse_forecast(payload)
    assert info.value.kind == "bad_response"


def test_parse_forecast_tolerates_short_daily_columns(api):
    payload = json.loads(json.dumps(FORECAST_JSON))
    payload["daily"]["temperature_2m_max"] = [31.0]
    del payload["daily"]["precipitation_probability_max"]
    days = api.parse_forecast(payload)["daily"]
    assert len(days) == 3
    assert days[1]["high"] is None and days[0]["rain_chance"] is None


def test_parse_places(api):
    places = api.parse_places(GEOCODING_JSON)
    assert len(places) == 2  # the entry without coordinates is dropped
    assert places[0] == JAKARTA
    assert api.place_label(places[0]) == "Jakarta, Indonesia"
    assert api.place_label(places[1]) == "Jakarta, West Virginia, United States"
    assert api.parse_places({"generationtime_ms": 0.2}) == []
    assert api.parse_places(None) == []


def test_request_urls_send_only_what_is_needed(api):
    url = api.build_forecast_url(-6.214621234, 106.84513, "Asia/Jakarta")
    assert url.startswith("https://api.open-meteo.com/v1/forecast?")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query == {
        # The point rounded to 2 decimals (about 1 km), never more (core 2.8).
        "latitude": ["-6.21"], "longitude": ["106.85"],
        "current": ["temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "weather_code,wind_speed_10m"],
        "daily": ["weather_code,temperature_2m_max,temperature_2m_min,"
                  "precipitation_probability_max"],
        "timezone": ["Asia/Jakarta"], "forecast_days": ["7"],
    }
    assert "timezone=Asia%2FJakarta" in url and "forecast_days=7" in url
    assert "timezone=auto" in api.build_forecast_url(1, 2)
    assert "latitude=1.00&longitude=2.00&" in api.build_forecast_url(1, 2)

    url = api.build_search_url("  Jakarta ", "id")
    assert url.startswith("https://geocoding-api.open-meteo.com/v1/search?")
    assert "name=Jakarta&" in url and "count=10" in url and "language=id" in url
    assert "language=en" in api.build_search_url("Paris", "fr")


# ------------------------------------------------------------
# HTTP errors (urlopen replaced, nothing is sent)
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
    assert seen["agent"].startswith("HarikuV2/")
    assert seen["timeout"] == api.TIMEOUT_SECONDS


@pytest.mark.parametrize("failure, kind", [
    (urllib.error.URLError("no route to host"), "offline"),
    (TimeoutError("timed out"), "offline"),
    (ConnectionResetError("reset"), "offline"),
    (urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None), "service"),
])
def test_fetch_json_maps_failures(api, monkeypatch, failure, kind):
    def fake_urlopen(req, timeout=None):
        raise failure

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(api.WeatherError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == kind


def test_fetch_json_rejects_bad_body(api, monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b"<html>oops</html>"))
    with pytest.raises(api.WeatherError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == "bad_response"


# ------------------------------------------------------------
# Units and text
# ------------------------------------------------------------

def test_unit_conversion(api):
    assert api.convert_temperature(0, "imperial") == 32
    assert api.convert_temperature(100, "imperial") == 212
    assert api.convert_temperature(21.5, "metric") == 21.5
    assert api.convert_temperature(None, "imperial") is None
    assert round(api.convert_speed(16.09344, "imperial"), 6) == 10
    assert api.convert_speed(12, "metric") == 12
    assert api.convert_speed(None, "metric") is None


def test_current_report_english(text, lang, forecast):
    assert text.current_report(JAKARTA, forecast, "metric", NOW_UTC) == (
        "Jakarta: Light rain, 27 degrees, feels like 31. "
        "Humidity 84 percent, wind 5 kilometres per hour. "
        "Today: high 31, low 24, 80 percent chance of rain.")


def test_current_report_fahrenheit(text, lang, forecast):
    assert text.current_report(JAKARTA, forecast, "imperial", NOW_UTC) == (
        "Jakarta: Light rain, 81 degrees, feels like 88. "
        "Humidity 84 percent, wind 3 miles per hour. "
        "Today: high 88, low 75, 80 percent chance of rain.")


def test_current_report_indonesian(text, lang, forecast):
    lang("id")
    assert text.current_report(JAKARTA, forecast, "metric", NOW_UTC) == (
        "Jakarta: Hujan ringan, 27 derajat, terasa seperti 31. "
        "Kelembapan 84 persen, angin 5 kilometer per jam. "
        "Hari ini: tertinggi 31, terendah 24, peluang hujan 80 persen.")


def test_current_report_skips_missing_values(text, lang, forecast):
    forecast["current"].update(feels_like=None, humidity=None, wind_speed=None)
    later = NOW_UTC + datetime.timedelta(days=30)  # no daily entry for "today"
    assert text.current_report(JAKARTA, forecast, "metric", later) == "Jakarta: Light rain, 27 degrees."


def test_forecast_rows(text, lang, forecast):
    assert text.forecast_rows(forecast, "metric", NOW_UTC) == [
        "Today, Wednesday 23 September: Light rain, high 31, low 24, 80 percent chance of rain",
        "Tomorrow, Thursday 24 September: Overcast, high 32, low 25, 10 percent chance of rain",
        "Friday 25 September: Thunderstorm, high 30, low 24",
    ]
    lang("id")
    rows = text.forecast_rows(forecast, "metric", NOW_UTC)
    assert rows[0] == "Hari ini, Rabu 23 September: Hujan ringan, tertinggi 31, terendah 24, peluang hujan 80 persen"
    assert rows[1].startswith("Besok, Kamis 24 September: Mendung")


def test_forecast_rows_skip_past_days(text, lang, forecast):
    next_day = NOW_UTC + datetime.timedelta(days=1)
    rows = text.forecast_rows(forecast, "metric", next_day)
    assert len(rows) == 2 and rows[0].startswith("Today, Thursday 24 September")


def test_briefing_sentence(text, lang, forecast):
    assert text.briefing_sentence(JAKARTA, forecast, "metric", NOW_UTC) == (
        "Weather in Jakarta: Light rain, 27 degrees, high 31, low 24, 80 percent chance of rain.")
    lang("id")
    assert text.briefing_sentence(JAKARTA, forecast, "metric", NOW_UTC) == (
        "Cuaca di Jakarta: Hujan ringan, 27 derajat, tertinggi 31, terendah 24, peluang hujan 80 persen.")


def test_error_text(text, lang):
    assert "internet connection" in text.error_text("offline")
    assert "try again later" in text.error_text("service")
    assert text.error_text("something else") == text.error_text("bad_response")
    lang("id")
    assert "koneksi internet" in text.error_text("offline")


def test_location_today_uses_the_utc_offset(api, forecast):
    late_utc = datetime.datetime(2026, 9, 23, 18, 0, tzinfo=datetime.timezone.utc)
    assert api.location_today(forecast, late_utc) == "2026-09-24"  # 01:00 in Jakarta
    assert api.location_today({"utc_offset_seconds": -18000}, late_utc) == "2026-09-23"


# ------------------------------------------------------------
# Cache and settings
# ------------------------------------------------------------

def test_cache_freshness(api, forecast):
    cache = api.make_cache(JAKARTA, forecast, now=1000.0)
    assert api.is_fresh(cache, 600, now=1000.0 + 599)
    assert not api.is_fresh(cache, 600, now=1000.0 + 601)
    assert not api.is_fresh(cache, 600, now=900.0)  # clock went backwards
    assert not api.is_fresh(None, 600)
    assert not api.is_fresh({"fetched_at": "soon"}, 600)
    assert api.cache_matches(cache, JAKARTA)
    assert not api.cache_matches(cache, dict(JAKARTA, latitude=38.1))
    assert not api.cache_matches(None, JAKARTA)
    # Kept for the rounded point (core 2.8), and compared at the rounded point.
    assert (cache["latitude"], cache["longitude"]) == (-6.21, 106.85)
    assert api.cache_matches(cache, dict(JAKARTA, latitude=-6.2149))
    assert not api.cache_matches(cache, dict(JAKARTA, latitude=-6.2249))


@pytest.mark.parametrize("raw", [
    None, "garbage", [], {}, {"location": "Jakarta"},
    {"location": {"name": "X", "latitude": "north", "longitude": 1}},
    {"location": {"name": "X", "latitude": 95, "longitude": 1}},
    {"location": {"name": "", "latitude": 1, "longitude": 1}},
    {"units": "kelvin"},
    {"place": "../x"}, {"place": 3}, {"place": ["main"]},
])
def test_settings_survive_corrupt_data(api, raw):
    settings = api.normalize_settings(raw)
    assert settings == {"place": None, "location": None, "units": "metric"}


def test_settings_keep_valid_values(api):
    settings = api.normalize_settings({"place": "own", "location": JAKARTA, "units": "imperial",
                                       "extra": 1})
    assert settings == {"place": "own", "location": JAKARTA, "units": "imperial"}
    for place in ("main", "abc12345"):
        assert api.normalize_settings({"place": place})["place"] == place


@pytest.mark.parametrize("raw", [
    None, "x", {}, {"fetched_at": 1, "latitude": 1, "longitude": 1},
    {"fetched_at": 1, "latitude": 1, "longitude": 1, "forecast": {"current": {}, "daily": []}},
    {"fetched_at": "x", "latitude": 1, "longitude": 1,
     "forecast": {"current": {"temperature": 3}, "daily": []}},
])
def test_corrupt_cache_is_dropped(api, raw):
    assert api.normalize_cache(raw) is None


def test_valid_cache_is_kept(api, forecast):
    cache = api.make_cache(JAKARTA, forecast, now=5.0)
    assert api.normalize_cache(json.loads(json.dumps(cache))) == cache


# ------------------------------------------------------------
# Actions (main.py)
# ------------------------------------------------------------

def _set_location(wmain, location=JAKARTA, place=None):
    wmain._settings = {"place": place, "location": dict(location) if location else None,
                       "units": "metric"}


def _place(location, name=None):
    """A saved place (core 2.8) at `location`."""
    return {"name": name or location["name"], "lat": location["latitude"],
            "lon": location["longitude"], "label": location["name"],
            "timezone": location.get("timezone"), "source": "city", "city": location["name"]}


def test_no_city_speaks_where_to_set_it(wmain, text, lang, monkeypatch):
    _set_location(wmain, None)

    def no_dialog(*args, **kwargs):
        raise AssertionError("the forecast window must not open without a city")

    monkeypatch.setattr(wmain.weather_ui, "ForecastDialog", no_dialog)
    wmain.speak_current_weather()
    wmain.show_forecast()
    hint = ("No weather location is set. Add a place in Preferences, Places, or choose your "
            "city in Preferences, Weather.")
    assert wmain.spoken == [hint, hint]
    lang("id")
    wmain.speak_current_weather()
    assert wmain.spoken[-1] == ("Lokasi cuaca belum diatur. Tambahkan tempat di Pengaturan, "
                                "Tempat, atau pilih kota Anda di Pengaturan, Cuaca.")


def test_fresh_cache_is_spoken_without_fetching(wmain, api, forecast, lang, monkeypatch):
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set_location(wmain)
    wmain._cache = api.make_cache(JAKARTA, forecast)
    wmain.speak_current_weather()
    assert calls == []
    assert len(wmain.spoken) == 1 and wmain.spoken[0].startswith("Jakarta: Light rain, 27 degrees")


def test_stale_cache_is_refreshed_then_spoken(wmain, api, forecast, lang, monkeypatch):
    import core.api
    calls = _fetch_calls(monkeypatch, api, response=FORECAST_JSON)
    _set_location(wmain)
    wmain._cache = api.make_cache(JAKARTA, forecast, now=1.0)
    wmain.speak_current_weather()
    assert len(calls) == 1 and "latitude=-6.21&longitude=106.85&" in calls[0]
    assert wmain.spoken[0] == "Getting the weather..."
    assert wmain.spoken[1].startswith("Jakarta: Light rain, 27 degrees")
    assert api.is_fresh(wmain._cache, 60)
    assert api.normalize_cache(core.api.load_data(wmain.CACHE_KEY)) is not None


def test_offline_falls_back_to_the_last_known_weather(wmain, api, forecast, lang, monkeypatch):
    import time
    _fetch_calls(monkeypatch, api, error="offline")
    _set_location(wmain)
    wmain._cache = api.make_cache(JAKARTA, forecast, now=time.time() - 2 * 3600)
    wmain.speak_current_weather()
    last = wmain.spoken[-1]
    assert last.startswith("Could not reach the weather service.")
    assert "Showing the last weather from" in last and "Jakarta: Light rain" in last


def test_offline_without_cache_says_so(wmain, api, lang, monkeypatch):
    _fetch_calls(monkeypatch, api, error="offline")
    _set_location(wmain)
    wmain._cache = None
    wmain.speak_current_weather()
    assert wmain.spoken == ["Getting the weather...",
                            "Could not reach the weather service. Check your internet connection."]


def test_one_fetch_at_a_time(wmain, api, monkeypatch):
    started = []
    monkeypatch.setattr(wmain, "_start_thread", lambda target, *args: started.append(args))
    _set_location(wmain)
    done = []
    assert wmain.refresh(done.append)
    assert wmain.refresh(done.append)
    assert wmain.refresh()
    assert len(started) == 1 and len(wmain._waiters) == 1
    wmain._on_fetched(None, "offline")
    assert done == ["offline"] and not wmain._loading


def test_background_refresh_backs_off_after_failure(wmain, api, forecast, monkeypatch):
    import time
    clock = [100000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set_location(wmain)
    wmain._cache = None

    wmain._on_minute_tick()
    assert len(calls) == 1
    clock[0] += 60
    wmain._on_minute_tick()
    assert len(calls) == 1          # no retry a minute later
    clock[0] += wmain.RETRY_SECONDS
    wmain._on_minute_tick()
    assert len(calls) == 2

    calls = _fetch_calls(monkeypatch, api, response=FORECAST_JSON)
    clock[0] += wmain.RETRY_SECONDS
    wmain._on_minute_tick()
    assert len(calls) == 1 and wmain.current_cache() is not None
    clock[0] += wmain.RETRY_SECONDS
    wmain._on_minute_tick()
    assert len(calls) == 1          # cache younger than 30 minutes
    clock[0] += wmain.REFRESH_SECONDS
    wmain._on_minute_tick()
    assert len(calls) == 2


def test_no_background_fetch_without_a_city(wmain, api, monkeypatch):
    calls = _fetch_calls(monkeypatch, api, response=FORECAST_JSON)
    _set_location(wmain, None)
    wmain._on_minute_tick()
    wmain._on_app_startup()
    assert calls == []


def test_changing_the_city_fetches_it(wmain, api, forecast, monkeypatch):
    import core.api
    calls = _fetch_calls(monkeypatch, api, response=FORECAST_JSON)
    _set_location(wmain)
    wmain._cache = api.make_cache(JAKARTA, forecast)
    other = dict(JAKARTA, name="Bandung", latitude=-6.9175, longitude=107.6191)
    wmain._save_settings({"location": other, "units": "imperial"})
    assert len(calls) == 1 and "latitude=-6.92&longitude=107.62" in calls[0]
    assert wmain.current_cache() is not None
    saved = core.api.load_data(wmain.DATA_KEY)
    assert saved["location"]["name"] == "Bandung" and saved["units"] == "imperial"
    # The main place instead: its own city is kept for later, the main place is fetched.
    import core.places
    core.places.set_places([_place(JAKARTA, "Home")])
    wmain._save_settings({"place": "main"})
    saved = core.api.load_data(wmain.DATA_KEY)
    assert saved["place"] == "main" and saved["location"]["name"] == "Bandung"
    assert saved["units"] == "imperial"
    assert wmain.get_location()["name"] == "Home" and len(calls) == 2
    assert "latitude=-6.21&longitude=106.85" in calls[1]
    # Saving again with the place in use already fetched: nothing new.
    wmain._save_settings({"units": "metric"})
    assert len(calls) == 2 and wmain.current_cache() is not None


def test_briefing_contribution_uses_the_cache_only(wmain, api, forecast, lang, monkeypatch):
    import time
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set_location(wmain)
    wmain._cache = api.make_cache(JAKARTA, forecast)
    lines = []
    wmain._on_briefing_collect(lines)
    assert len(lines) == 1 and lines[0].startswith("Weather in Jakarta: Light rain, 27 degrees")

    lines = []
    wmain._cache = api.make_cache(JAKARTA, forecast, now=time.time() - 4 * 3600)
    wmain._on_briefing_collect(lines)
    assert lines == []              # too old to be today's weather

    _set_location(wmain, None)
    wmain._on_briefing_collect(lines)
    assert lines == [] and calls == []


def test_register_and_teardown(wmain, fresh_event_bus, monkeypatch, tmp_data_dir):
    import core.api
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *args, **kwargs: panels.append(args))
    # Corrupt files on disk must not stop the extension from loading.
    for key in (wmain.DATA_KEY, wmain.CACHE_KEY):
        with open(core.api.get_data_path(key), "w", encoding="utf-8") as f:
            f.write("{not json")

    import core.personal
    wmain.register(fresh_event_bus)
    assert wmain.get_location() is None and wmain._cache is None
    assert core.personal.is_placeholder_registered("weather")       # %weather% (core 2.7)
    for event_name, handler in wmain._SUBSCRIPTIONS:
        assert handler in fresh_event_bus._listeners[event_name]
    by_name = {args[1]: (args, kwargs) for args, kwargs in actions}
    speak_args, speak_kwargs = by_name["speak_current_weather"]
    assert speak_args[0] == "Weather" and speak_args[3] == ord("W") and speak_args[4] is False
    assert speak_kwargs == {"default_shift": True}
    assert by_name["show_forecast"][0][3] is None
    assert len(panels) == 1

    wmain.teardown()
    for event_name, handler in wmain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    assert not wmain._active
    assert not core.personal.is_placeholder_registered("weather")


# --- Evening summary (Weather 1.1) --------------------------------------------------

def test_evening_sentence(text, lang, forecast):
    # The sample's tomorrow (24 September) is overcast with a high of 32.4.
    assert text.evening_sentence(forecast, "metric", NOW_UTC) == "Tomorrow: overcast, 32 degrees."
    assert text.evening_sentence(forecast, "imperial", NOW_UTC) == "Tomorrow: overcast, 90 degrees."
    lang("id")
    assert text.evening_sentence(forecast, "metric", NOW_UTC) == "Besok: mendung, 32 derajat."


def test_evening_sentence_without_tomorrow(text, lang, forecast):
    last_day = NOW_UTC + datetime.timedelta(days=2)
    assert text.evening_sentence(forecast, "metric", last_day) == ""
    forecast["daily"][1]["code"] = None
    assert text.evening_sentence(forecast, "metric", NOW_UTC) == "Tomorrow: high 32."
    forecast["daily"][1]["high"] = None
    assert text.evening_sentence(forecast, "metric", NOW_UTC) == ""


def test_evening_contribution_uses_the_cache_only(wmain, api, forecast, lang, monkeypatch):
    import time
    calls = _fetch_calls(monkeypatch, api, error="offline")
    real = wmain.weather_text.evening_sentence
    monkeypatch.setattr(wmain.weather_text, "evening_sentence",
                        lambda fc, units, now_utc=None: real(fc, units, NOW_UTC))
    _set_location(wmain)
    wmain._cache = api.make_cache(JAKARTA, forecast)
    lines = []
    wmain._on_evening_collect(lines)
    assert lines == ["Tomorrow: overcast, 32 degrees."]
    lines = []
    wmain._cache = api.make_cache(JAKARTA, forecast, now=time.time() - 4 * 3600)
    wmain._on_evening_collect(lines)
    assert lines == []              # too old
    _set_location(wmain, None)
    wmain._on_evening_collect(lines)
    assert lines == [] and calls == []


# --- %weather% and refreshing when back online (core 2.7) ------------------------------

def test_placeholder_text(text, lang, forecast):
    assert text.placeholder_text(forecast, "metric") == "light rain, 27 degrees"
    lang("id")
    assert text.placeholder_text(forecast, "metric") == "hujan ringan, 27 derajat"
    forecast["current"]["code"] = None
    assert text.placeholder_text(forecast, "metric") == "27 derajat"
    forecast["current"]["temperature"] = None
    assert text.placeholder_text(forecast, "metric") == ""


def test_weather_placeholder_uses_the_cache_only(wmain, api, forecast, lang, monkeypatch):
    import time
    import core.personal
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set_location(wmain)
    wmain._cache = api.make_cache(JAKARTA, forecast)
    assert wmain.placeholder_text() == "light rain, 27 degrees"
    core.personal.register_placeholder("weather", wmain.placeholder_text)
    try:
        assert core.personal.expand("It is %weather% in %mynickname%land.").startswith(
            "It is light rain, 27 degrees in ")
    finally:
        core.personal.unregister_placeholder("weather")
    wmain._cache = api.make_cache(JAKARTA, forecast, now=time.time() - 4 * 3600)
    assert wmain.placeholder_text() == ""            # too old to be "now"
    _set_location(wmain, None)
    assert wmain.placeholder_text() == "" and calls == []


def test_back_online_refreshes_a_stale_forecast(wmain, api, forecast, monkeypatch):
    import time
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set_location(wmain)
    wmain._cache = api.make_cache(JAKARTA, forecast)
    wmain._on_network_changed(True)
    assert calls == []                               # fresh: nothing to do
    wmain._cache = api.make_cache(JAKARTA, forecast, now=time.time() - 3600)
    wmain._on_network_changed(False)
    assert calls == []                               # offline: nothing to do
    wmain._on_network_changed(True)
    assert len(calls) == 1


# ------------------------------------------------------------
# Places (Weather 1.2, core 2.8)
# ------------------------------------------------------------

def test_manifest_needs_core_2_8_for_places():
    with open(os.path.join(WEATHER_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["version"] == "1.2" and manifest["minimum_core_version"] == "2.8"


def test_the_main_place_is_the_default(wmain, tmp_data_dir):
    import core.places
    _set_location(wmain, None)
    assert wmain.get_location() is None
    core.places.set_places([_place(BANDUNG, "Home")])
    location = wmain.get_location()
    assert location["name"] == "Home" and location["latitude"] == BANDUNG["latitude"]
    assert location["admin1"] == "" and location["country"] == ""   # just "Home" in labels
    assert location["timezone"] == "Asia/Jakarta"
    # A city of its own from before 2.8, not decided yet: it stays in use...
    _set_location(wmain, JAKARTA)
    assert wmain.get_location() == JAKARTA
    # ...unless it is the main place anyway.
    _set_location(wmain, BANDUNG)
    assert wmain.get_location()["name"] == "Home"


def test_the_place_choice(wmain, tmp_data_dir):
    import core.places
    home, office = core.places.set_places([_place(BANDUNG, "Home"), _place(JAKARTA, "Office")])
    city = dict(JAKARTA, name="Kota")
    _set_location(wmain, city, place="main")
    assert wmain.get_location()["name"] == "Home"
    _set_location(wmain, city, place=office["id"])
    assert wmain.get_location()["name"] == "Office"
    _set_location(wmain, city, place="own")
    assert wmain.get_location()["name"] == "Kota"
    # Its own place chosen but no city found yet: no place.
    _set_location(wmain, None, place="own")
    assert wmain.get_location() is None
    # A place that was removed: the main place.
    core.places.set_places([home])
    _set_location(wmain, None, place=office["id"])
    assert wmain.get_location()["name"] == "Home"


def test_the_exact_point_never_leaves_the_computer(wmain, api, lang, monkeypatch):
    import core.api
    import core.places
    calls = _fetch_calls(monkeypatch, api, response=FORECAST_JSON)
    core.places.set_places([{"name": "Home", "lat": -6.108812, "lon": 106.885613,
                             "source": "coordinates"}])
    _set_location(wmain, None, place="main")
    wmain.speak_current_weather()
    assert len(calls) == 1
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0]).query)
    assert (query["latitude"], query["longitude"]) == (["-6.11"], ["106.89"])
    assert query["timezone"] == ["auto"]            # a pasted point has no time zone
    assert "6.1088" not in calls[0] and "106.8856" not in calls[0]
    # The cache keeps the rounded point too, and answers for the exact one.
    stored = core.api.load_data(wmain.CACHE_KEY)
    assert (stored["latitude"], stored["longitude"]) == (-6.11, 106.89)
    assert wmain.current_cache() is not None
    assert wmain.spoken[-1].startswith("Home: Light rain, 27 degrees")


def test_the_briefing_and_weather_placeholder_follow_the_place_in_use(wmain, api, forecast, lang,
                                                                      monkeypatch):
    import core.places
    calls = _fetch_calls(monkeypatch, api, error="offline")
    core.places.set_places([_place(BANDUNG, "Home")])
    _set_location(wmain, JAKARTA, place="main")
    wmain._cache = api.make_cache(BANDUNG, forecast)
    lines = []
    wmain._on_briefing_collect(lines)
    assert len(lines) == 1 and lines[0].startswith("Weather in Home: Light rain, 27 degrees")
    assert wmain.placeholder_text() == "light rain, 27 degrees"
    # The cache is for another point (its own city): nothing, and nothing fetched.
    wmain._cache = api.make_cache(JAKARTA, forecast)
    lines = []
    wmain._on_briefing_collect(lines)
    wmain._on_evening_collect(lines)
    assert lines == [] and wmain.placeholder_text() == "" and calls == []


def test_a_city_of_its_own_from_before_is_kept(wmain, fresh_event_bus, monkeypatch, tmp_data_dir):
    import core.api
    import core.hotkeys
    import core.places
    import core.preferences
    monkeypatch.setattr(core.hotkeys, "register_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(core.preferences, "register_panel", lambda *args, **kwargs: None)
    # Home is somewhere else (Flight Radar's home, say): the city stays its own place.
    core.places.set_places([_place(BANDUNG, "Home")])
    core.api.save_data(wmain.DATA_KEY, {"location": JAKARTA, "units": "imperial"})
    wmain.register(fresh_event_bus)
    assert wmain._settings["place"] == "own" and wmain.get_location() == JAKARTA
    saved = core.api.load_data(wmain.DATA_KEY)
    assert saved["place"] == "own" and saved["units"] == "imperial"
    wmain.teardown()
    # Decided once: a later start keeps it.
    wmain.register(fresh_event_bus)
    assert wmain._settings["place"] == "own"
    wmain.teardown()
    # Its city is the main place anyway: it follows the main place.
    core.api.save_data(wmain.DATA_KEY, {"location": BANDUNG, "units": "metric"})
    wmain.register(fresh_event_bus)
    assert wmain._settings["place"] == "main" and wmain.get_location()["name"] == "Home"
    assert core.api.load_data(wmain.DATA_KEY)["place"] == "main"
    wmain.teardown()
    # Nothing of its own: the main place, and nothing written.
    core.api.save_data(wmain.DATA_KEY, {"units": "metric"})
    wmain.register(fresh_event_bus)
    assert wmain._settings["place"] is None and wmain.get_location()["name"] == "Home"
    assert "place" not in core.api.load_data(wmain.DATA_KEY)
    wmain.teardown()


def test_the_weather_city_becomes_home_and_the_main_place(wmain, fresh_event_bus, lang,
                                                           monkeypatch, tmp_data_dir):
    # The first start with core 2.8: the core makes "Home" from the Weather city
    # (no Flight Radar home here) before the extensions load.
    import core.api
    import core.hotkeys
    import core.places
    import core.preferences
    monkeypatch.setattr(core.hotkeys, "register_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(core.preferences, "register_panel", lambda *args, **kwargs: None)
    core.api.save_data(wmain.DATA_KEY, {"location": JAKARTA, "units": "metric"})
    home = core.places.migrate()
    assert home["name"] == "Home"
    wmain.register(fresh_event_bus)
    assert wmain._settings["place"] == "main"
    location = wmain.get_location()
    assert location["name"] == "Home" and location["place_id"] == home["id"]
    assert (location["latitude"], location["longitude"]) == (JAKARTA["latitude"],
                                                             JAKARTA["longitude"])
    assert location["timezone"] == "Asia/Jakarta"
    assert core.api.load_data(wmain.DATA_KEY)["location"] == JAKARTA   # kept as its own
    wmain.teardown()


def test_places_changing_refreshes_the_page_and_the_data(wmain, api, forecast, monkeypatch):
    import core.places
    from core.events import bus
    calls = _fetch_calls(monkeypatch, api, response=FORECAST_JSON)
    home, = core.places.set_places([_place(JAKARTA, "Home")])
    _set_location(wmain, None, place="main")
    wmain._cache = api.make_cache(JAKARTA, forecast)

    class Page:
        refreshed = 0

        def refresh_places(self):
            Page.refreshed += 1

    class ClosedPage:
        def refresh_places(self):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    monkeypatch.setattr(wmain, "_panel", Page())
    bus.subscribe("on_places_changed", wmain._on_places_changed)
    try:
        # The main place moves: the page lists the places again, the new one is fetched.
        core.places.set_places([dict(home, lat=BANDUNG["latitude"], lon=BANDUNG["longitude"])])
        assert Page.refreshed == 1 and len(calls) == 1
        assert "latitude=-6.92&longitude=107.62" in calls[0]
        assert wmain.current_cache() is not None
        # A change that doesn't move the place in use fetches nothing.
        core.places.set_places(core.places.get_places() + [_place(JAKARTA, "Office")])
        assert Page.refreshed == 2 and len(calls) == 1
        # Its own city: the places don't matter.
        _set_location(wmain, JAKARTA, place="own")
        wmain._cache = api.make_cache(JAKARTA, forecast)
        core.places.set_places([])
        assert Page.refreshed == 3 and len(calls) == 1
        # A page that was closed already is skipped.
        monkeypatch.setattr(wmain, "_panel", ClosedPage())
        core.places.set_places([_place(BANDUNG, "Home")])
        assert len(calls) == 1
    finally:
        bus.unsubscribe("on_places_changed", wmain._on_places_changed)


def test_the_page_has_the_place_choice():
    with open(os.path.join(WEATHER_DIR, "weather_ui.py"), encoding="utf-8") as f:
        source = f.read()
    assert "PlaceChoice(" in source and "refresh_places" in source
    for code, word in (("en", "Places"), ("id", "Tempat")):
        with open(os.path.join(WEATHER_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            messages = json.load(f)["messages"]
        assert word in messages["no_location"] and messages["note_privacy"]
