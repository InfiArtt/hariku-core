# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Air Quality extension: Air Quality API parsing, the AQI and UV
# categories and tips in both languages, the forecast rows, the unhealthy-air
# alert, the cache, the briefing, and the actions. No test touches the
# network; the fetch functions are replaced.

import datetime
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AIR_DIR = os.path.join(ROOT, "extensions", "air_quality")


def _hours(start, count):
    return [(start + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(count)]


# Trimmed real response for Jakarta (Open-Meteo, 23-24 September 2026; the shape
# verified against the live Air Quality API).
AIR_JSON = {
    "latitude": -6.199997, "longitude": 106.80002, "generationtime_ms": 0.91,
    "utc_offset_seconds": 25200, "timezone": "Asia/Jakarta", "timezone_abbreviation": "GMT+7",
    "elevation": 18.0,
    "current_units": {"time": "iso8601", "interval": "seconds", "us_aqi": "USAQI",
                      "pm2_5": "μg/m³", "pm10": "μg/m³", "uv_index": ""},
    "current": {"time": "2026-09-23T19:00", "interval": 3600, "us_aqi": 231, "pm2_5": 102.4,
                "pm10": 103.6, "uv_index": 0.0, "us_aqi_pm2_5": 190, "us_aqi_pm10": 79,
                "us_aqi_ozone": 231, "us_aqi_nitrogen_dioxide": 53,
                "us_aqi_carbon_monoxide": 14, "us_aqi_sulphur_dioxide": 32},
    "hourly_units": {"time": "iso8601", "us_aqi": "USAQI", "pm2_5": "μg/m³", "uv_index": ""},
    "hourly": {
        "time": _hours(datetime.datetime(2026, 9, 23), 48),
        "us_aqi": [182, 183, 185, 185, 186, 186, 186, 187, 186, 186, 187, 187,
                   188, 188, 188, 198, 219, 232, 236, 231, 219, 202, 191, 192,
                   193, 194, 195, 197, 198, 198, 199, 199, 199, 199, 198, 197,
                   196, 196, 195, 194, 193, 192, 190, 189, 188, 187, 187, 186],
        "pm2_5": [160.2, 154.1, 151.3, 148.1, 147.1, 149.0, 156.0, 153.7, 116.4, 79.4, 70.3, 66.1,
                  68.9, 71.0, 72.6, 69.6, 72.6, 88.5, 88.2, 102.4, 121.5, 142.0, 159.3, 180.7,
                  189.1, 195.6, 206.3, 170.4, 167.6, 162.1, 160.7, 163.0, 95.5, 54.4, 42.5, 43.1,
                  43.5, 41.8, 40.3, 38.8, 38.5, 41.7, 51.5, 69.8, 90.6, 111.8, 127.1, 136.0],
        "uv_index": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.7, 2.4, 4.7, 6.55, 7.4,
                     7.35, 6.2, 3.8, 1.7, 0.6, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.7, 2.4, 5.2, 8.05, 9.85,
                     10.1, 8.5, 5.75, 2.95, 1.0, 0.15, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
}

GEOCODING_JSON = {"results": [
    {"id": 1642911, "name": "Jakarta", "latitude": -6.21462, "longitude": 106.84513,
     "country_code": "ID", "timezone": "Asia/Jakarta", "country": "Indonesia", "admin1": "Jakarta"},
    {"id": 7, "name": "Nowhere", "latitude": "north"},
]}

# 12:15 UTC is 19:15 in Jakarta on 23 September, the sample's "now".
NOW_UTC = datetime.datetime(2026, 9, 23, 12, 15, tzinfo=datetime.timezone.utc)

JAKARTA = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
           "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"}
BANDUNG = {"name": "Bandung", "admin1": "West Java", "country": "Indonesia",
           "latitude": -6.9175, "longitude": 107.6191, "timezone": "Asia/Jakarta"}

VERY_UNHEALTHY_TIP = ("Everyone should avoid prolonged or heavy outdoor exertion; "
                      "sensitive groups should avoid all physical activity outdoors.")


def _import_helpers():
    if AIR_DIR not in sys.path:
        sys.path.insert(0, AIR_DIR)
    import air_quality_api
    import air_quality_text
    return air_quality_api, air_quality_text


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


def _copy(data):
    return json.loads(json.dumps(data))


@pytest.fixture
def forecast(api):
    return api.parse_air(_copy(AIR_JSON))


@pytest.fixture
def amain(monkeypatch, tmp_data_dir, api, text):
    """Air Quality's main.py with speech and sounds captured and the fetch
    thread run inline."""
    spec = importlib.util.spec_from_file_location("air_quality_main_under_test",
                                                  os.path.join(AIR_DIR, "main.py"))
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
            raise api.AirError(error)
        return _copy(response)

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    return calls


def _set(amain, location=JAKARTA, **settings):
    amain._settings = dict(amain.api.normalize_settings(None),
                           location=dict(location) if location else None, **settings)


# ------------------------------------------------------------
# Locale files
# ------------------------------------------------------------

def test_locales_have_the_same_keys():
    keys = {}
    for code in ("en", "id"):
        with open(os.path.join(AIR_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            keys[code] = set(json.load(f)["messages"])
    assert keys["en"] == keys["id"]


def test_every_category_tip_and_pollutant_is_translated(api, text, lang):
    keys = [f"cat_{k}" for _l, k in api.AQI_CATEGORIES] + [f"tip_{k}" for _l, k in api.AQI_CATEGORIES]
    keys += [f"uv_{k}" for _l, k in api.UV_CATEGORIES] + [f"pol_{p}" for p in api.POLLUTANTS]
    english = {}
    for code in ("en", "id"):
        lang(code)
        for key in keys:
            value = text._(key)
            assert value != key, (code, key)
            if code == "en":
                english[key] = value
    lang("id")
    assert text._("tip_hazardous") != english["tip_hazardous"]


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def test_parse_air(forecast):
    assert forecast["timezone"] == "Asia/Jakarta" and forecast["utc_offset_seconds"] == 25200
    assert forecast["current"] == {"time": "2026-09-23T19:00", "aqi": 231, "pm2_5": 102.4,
                                   "pm10": 103.6, "uv": 0.0, "main_pollutant": "ozone"}
    assert len(forecast["hourly"]) == 48
    assert forecast["hourly"][19] == {"time": "2026-09-23T19:00", "aqi": 231, "pm2_5": 102.4, "uv": 0.0}
    assert forecast["has_data"] is True


def test_nulls_mean_no_data(api):
    payload = _copy(AIR_JSON)
    payload["current"] = {k: (None if k not in ("time", "interval") else v)
                          for k, v in payload["current"].items()}
    payload["hourly"]["us_aqi"] = [None] * 48
    parsed = api.parse_air(payload)
    assert parsed["has_data"] is False
    assert parsed["current"]["aqi"] is None and parsed["current"]["main_pollutant"] is None


@pytest.mark.parametrize("payload", [None, [], "text", {}, {"current": "x"}, {"hourly": {}}])
def test_parse_air_rejects_unusable_data(api, payload):
    with pytest.raises(api.AirError) as info:
        api.parse_air(payload)
    assert info.value.kind == "bad_response"


def test_parse_air_tolerates_short_and_odd_columns(api):
    payload = _copy(AIR_JSON)
    payload["hourly"]["uv_index"] = [1.0]
    payload["hourly"]["pm2_5"][1] = "lots"
    payload["hourly"]["time"][2] = "yesterday"
    parsed = api.parse_air(payload)
    assert len(parsed["hourly"]) == 47
    assert parsed["hourly"][0]["uv"] == 1.0 and parsed["hourly"][1]["uv"] is None
    assert parsed["hourly"][1]["pm2_5"] is None


def test_main_pollutant(api):
    assert api.main_pollutant({"pm2_5": 190, "ozone": 231, "pm10": 79}) == "ozone"
    assert api.main_pollutant({"pm2_5": 120, "pm10": 120}) == "pm2_5"   # a tie: the first
    assert api.main_pollutant({"pm2_5": None, "ozone": "x"}) is None
    assert api.main_pollutant(None) is None


def test_parse_places(api):
    places = api.parse_places(GEOCODING_JSON)
    assert places == [JAKARTA]
    assert api.place_label(places[0]) == "Jakarta, Indonesia"
    assert api.parse_places(None) == []


def test_request_urls_send_only_the_place_and_what_is_needed(api):
    url = api.build_air_url(-6.214621234, 106.84513, "Asia/Jakarta")
    assert url.startswith("https://air-quality-api.open-meteo.com/v1/air-quality?")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query == {
        "latitude": ["-6.2146"], "longitude": ["106.8451"],
        "current": ["us_aqi,pm2_5,pm10,uv_index,us_aqi_pm2_5,us_aqi_pm10,us_aqi_ozone,"
                    "us_aqi_nitrogen_dioxide,us_aqi_carbon_monoxide,us_aqi_sulphur_dioxide"],
        "hourly": ["us_aqi,pm2_5,uv_index"],
        "timezone": ["Asia/Jakarta"], "forecast_days": ["5"],
    }
    assert "timezone=auto" in api.build_air_url(1, 2)
    url = api.build_search_url("  Jakarta ", "fr")
    assert url.startswith("https://geocoding-api.open-meteo.com/v1/search?")
    assert "name=Jakarta&" in url and "language=en" in url


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
    assert seen["agent"].startswith("HarikuV2/") and seen["agent"].endswith("(Air Quality extension)")
    assert seen["timeout"] == api.TIMEOUT_SECONDS


@pytest.mark.parametrize("failure, kind", [
    (urllib.error.URLError("no route to host"), "offline"),
    (ConnectionResetError("reset"), "offline"),
    (urllib.error.HTTPError("https://x", 429, "Too Many Requests", {}, None), "service"),
])
def test_fetch_json_maps_failures(api, monkeypatch, failure, kind):
    def fake_urlopen(req, timeout=None):
        raise failure

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(api.AirError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == kind


def test_fetch_json_rejects_bad_body(api, monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b"<html>oops</html>"))
    with pytest.raises(api.AirError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == "bad_response"


# ------------------------------------------------------------
# Categories and text
# ------------------------------------------------------------

@pytest.mark.parametrize("aqi, key", [
    (0, "good"), (50, "good"), (51, "moderate"), (100, "moderate"), (101, "sensitive"),
    (150, "sensitive"), (151, "unhealthy"), (200, "unhealthy"), (201, "very_unhealthy"),
    (300, "very_unhealthy"), (301, "hazardous"), (500, "hazardous"), (None, None),
])
def test_aqi_categories(api, aqi, key):
    assert api.aqi_category(aqi) == key


@pytest.mark.parametrize("uv, value, key", [
    (0.0, 0, "low"), (-0.2, 0, "low"), (2.49, 2, "low"), (2.5, 3, "moderate"),
    (5.4, 5, "moderate"), (5.5, 6, "high"), (7.4, 7, "high"), (7.5, 8, "very_high"),
    (10.4, 10, "very_high"), (10.5, 11, "extreme"), (None, None, None),
])
def test_uv_categories(api, uv, value, key):
    assert api.uv_value(uv) == value and api.uv_category(uv) == key


def test_category_names_and_tips_in_both_languages(text, lang):
    assert [text.category_text(a) for a in (10, 60, 120, 160, 250, 400)] == [
        "good", "moderate", "unhealthy for sensitive groups", "unhealthy", "very unhealthy",
        "hazardous"]
    assert text.tip_text(120).startswith("People with heart or lung disease")
    assert text.tip_text(250) == VERY_UNHEALTHY_TIP
    assert text.uv_text(9.85) == "UV index 10, very high"
    lang("id")
    assert [text.category_text(a) for a in (10, 60, 120, 160, 250, 400)] == [
        "baik", "sedang", "tidak sehat bagi kelompok sensitif", "tidak sehat",
        "sangat tidak sehat", "berbahaya"]
    assert text.tip_text(400) == "Semua orang sebaiknya menghindari semua aktivitas fisik di luar ruangan."
    assert text.uv_text(11.2) == "indeks UV 11, ekstrem"


def test_current_report_english(text, lang, forecast):
    assert text.current_report(JAKARTA, forecast) == (
        "Jakarta: Air quality index 231, very unhealthy, mostly ozone. "
        "PM2.5 102, PM10 104 micrograms per cubic metre. UV index 0, low. " + VERY_UNHEALTHY_TIP)


def test_current_report_indonesian(text, lang, forecast):
    lang("id")
    assert text.current_report(JAKARTA, forecast) == (
        "Jakarta: Indeks kualitas udara 231, sangat tidak sehat, terutama ozon. "
        "PM2,5 102, PM10 104 mikrogram per meter kubik. Indeks UV 0, rendah. "
        "Semua orang sebaiknya menghindari aktivitas berat atau lama di luar ruangan; "
        "kelompok sensitif sebaiknya menghindari semua aktivitas fisik di luar ruangan.")


def test_good_air_skips_the_main_pollutant(text, lang, forecast):
    forecast["current"].update(aqi=32, pm10=None, uv=None)
    assert text.current_report(JAKARTA, forecast) == (
        "Jakarta: Air quality index 32, good. PM2.5 102 micrograms per cubic metre. "
        "Air quality is good; a fine time to be active outside.")


def test_report_without_data(text, lang, forecast):
    forecast["has_data"] = False
    assert text.current_report(JAKARTA, forecast) == (
        "No air quality data for Jakarta right now. Please try again later.")
    assert text.briefing_sentence(JAKARTA, forecast) == ""


def test_briefing_and_alert_sentences(text, lang, forecast):
    assert text.briefing_sentence(JAKARTA, forecast) == (
        "Air quality in Jakarta: index 231, very unhealthy.")
    assert text.alert_text(JAKARTA, 231) == (
        "Air quality alert for Jakarta: index 231, very unhealthy. " + VERY_UNHEALTHY_TIP)
    lang("id")
    assert text.briefing_sentence(JAKARTA, forecast) == (
        "Kualitas udara di Jakarta: indeks 231, sangat tidak sehat.")


def test_hour_rows(text, lang, forecast):
    assert text.hour_rows(forecast, NOW_UTC) == [
        "Today 19:00: index 231, very unhealthy, PM2.5 102.",
        "Today 22:00: index 191, unhealthy, PM2.5 159.",
        "Tomorrow 01:00: index 194, unhealthy, PM2.5 196.",
        "Tomorrow 04:00: index 198, unhealthy, PM2.5 168.",
        "Tomorrow 07:00: index 199, unhealthy, PM2.5 163, UV index 1, low.",
        "Tomorrow 10:00: index 198, unhealthy, PM2.5 43, UV index 8, very high.",
        "Tomorrow 13:00: index 196, unhealthy, PM2.5 42, UV index 9, very high.",
        "Tomorrow 16:00: index 193, unhealthy, PM2.5 39, UV index 1, low.",
    ]
    lang("id")
    assert text.hour_rows(forecast, NOW_UTC)[2] == "Besok 01:00: indeks 194, tidak sehat, PM2,5 196."


def test_day_rows(text, lang, forecast):
    assert text.day_rows(forecast, NOW_UTC) == [
        "Today, Wednesday 23 September: index up to 236, very unhealthy, PM2.5 up to 181, "
        "UV index up to 7, high.",
        "Tomorrow, Thursday 24 September: index up to 199, unhealthy, PM2.5 up to 206, "
        "UV index up to 10, very high.",
    ]
    lang("id")
    assert text.day_rows(forecast, NOW_UTC)[0] == (
        "Hari ini, Rabu 23 September: indeks hingga 236, sangat tidak sehat, PM2,5 hingga 181, "
        "indeks UV hingga 7, tinggi.")
    # A day later, only the 24th is left.
    later = NOW_UTC + datetime.timedelta(days=1)
    assert len(text.day_rows(forecast, later)) == 1


def test_error_text(text, lang):
    assert "internet connection" in text.error_text("offline")
    assert text.error_text("weird") == text.error_text("bad_response")
    lang("id")
    assert "koneksi internet" in text.error_text("offline")


# ------------------------------------------------------------
# Alert rule, settings and cache
# ------------------------------------------------------------

def test_alert_rule(api, forecast):
    on = dict(api.normalize_settings(None), alert=True)
    assert api.should_alert(on, forecast, "2026-09-23") == 231
    assert api.should_alert(dict(on, alert=False), forecast, "2026-09-23") is None
    assert api.should_alert(dict(on, alert_date="2026-09-23"), forecast, "2026-09-23") is None
    assert api.should_alert(dict(on, alert_date="2026-09-22"), forecast, "2026-09-23") == 231
    forecast["current"]["aqi"] = 150
    assert api.should_alert(on, forecast, "2026-09-23") is None   # sensitive groups only
    forecast["current"]["aqi"] = 151
    assert api.should_alert(on, forecast, "2026-09-23") == 151
    forecast["current"]["aqi"] = None
    assert api.should_alert(on, forecast, "2026-09-23") is None


@pytest.mark.parametrize("raw", [
    None, "garbage", [], {}, {"location": "Jakarta"},
    {"location": {"name": "X", "latitude": 95, "longitude": 1}},
    {"alert": 1, "alert_date": "yesterday"},
])
def test_settings_survive_corrupt_data(api, raw):
    assert api.normalize_settings(raw) == {"location": None, "alert": False, "alert_date": ""}


def test_settings_keep_valid_values(api):
    raw = {"location": JAKARTA, "alert": True, "alert_date": "2026-09-23", "extra": 1}
    assert api.normalize_settings(raw) == {"location": JAKARTA, "alert": True,
                                           "alert_date": "2026-09-23"}


def test_cache_freshness(api, forecast):
    cache = api.make_cache(JAKARTA, forecast, now=1000.0)
    assert api.is_fresh(cache, 600, now=1599.0)
    assert not api.is_fresh(cache, 600, now=1601.0)
    assert not api.is_fresh(cache, 600, now=900.0)
    assert not api.is_fresh(None, 600)
    assert api.cache_matches(cache, JAKARTA) and not api.cache_matches(cache, BANDUNG)


@pytest.mark.parametrize("raw", [
    None, "x", {}, {"fetched_at": 1, "latitude": 1, "longitude": 1},
    {"fetched_at": 1, "latitude": 1, "longitude": 1, "forecast": {"current": {}}},
    {"fetched_at": "x", "latitude": 1, "longitude": 1, "forecast": {"current": {}, "hourly": []}},
])
def test_corrupt_cache_is_dropped(api, raw):
    assert api.normalize_cache(raw) is None


def test_valid_cache_is_kept(api, forecast):
    cache = api.make_cache(JAKARTA, forecast, now=5.0)
    assert api.normalize_cache(_copy(cache)) == cache
    broken = _copy(cache)
    broken["forecast"]["current"]["main_pollutant"] = "smoke"
    broken["forecast"]["hourly"].append({"time": "later", "aqi": 3})
    kept = api.normalize_cache(broken)
    assert kept["forecast"]["current"]["main_pollutant"] is None
    assert len(kept["forecast"]["hourly"]) == 48


# ------------------------------------------------------------
# Actions (main.py)
# ------------------------------------------------------------

def test_no_location_speaks_where_to_set_it(amain, lang, monkeypatch):
    _set(amain, None)

    def no_dialog(*args, **kwargs):
        raise AssertionError("the forecast window must not open without a city")

    monkeypatch.setattr(amain.air_quality_ui, "AirForecastDialog", no_dialog)
    amain.speak_air_quality()
    amain.show_forecast()
    hint = "No air quality location is set. Choose your city in Preferences, Air Quality."
    assert amain.spoken == [hint, hint]
    lang("id")
    amain.speak_air_quality()
    assert amain.spoken[-1].startswith("Lokasi kualitas udara belum diatur.")


def test_the_weather_city_is_the_default(amain, tmp_data_dir):
    import core.api
    _set(amain, None)
    assert amain.get_location() is None
    core.api.save_data("Weather", {"location": BANDUNG, "units": "metric"})
    assert amain.get_location() == BANDUNG
    _set(amain, JAKARTA)
    assert amain.get_location() == JAKARTA


def test_fresh_cache_is_spoken_without_fetching(amain, api, forecast, lang, monkeypatch):
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set(amain)
    amain._cache = api.make_cache(JAKARTA, forecast)
    amain.speak_air_quality()
    assert calls == []
    assert amain.spoken == [text_report(amain, forecast)]


def text_report(amain, forecast):
    return amain.text.current_report(JAKARTA, forecast)


def test_stale_cache_is_refreshed_then_spoken(amain, api, forecast, lang, monkeypatch):
    import core.api
    calls = _fetch_calls(monkeypatch, api, response=AIR_JSON)
    _set(amain)
    amain._cache = api.make_cache(JAKARTA, forecast, now=1.0)
    amain.speak_air_quality()
    assert len(calls) == 1 and "latitude=-6.2146" in calls[0]
    assert amain.spoken[0] == "Getting the air quality..."
    assert amain.spoken[1].startswith("Jakarta: Air quality index 231, very unhealthy")
    assert api.normalize_cache(core.api.load_data(amain.CACHE_KEY)) is not None


def test_offline_falls_back_to_the_last_known_air(amain, api, forecast, lang, monkeypatch):
    import time
    _fetch_calls(monkeypatch, api, error="offline")
    _set(amain)
    amain._cache = api.make_cache(JAKARTA, forecast, now=time.time() - 2 * 3600)
    amain.speak_air_quality()
    last = amain.spoken[-1]
    assert last.startswith("Could not reach the air quality service.")
    assert "Showing the last air quality from" in last and "Jakarta: Air quality index 231" in last


def test_offline_without_cache_says_so(amain, api, lang, monkeypatch):
    _fetch_calls(monkeypatch, api, error="service")
    _set(amain)
    amain._cache = None
    amain.speak_air_quality()
    assert amain.spoken == ["Getting the air quality...",
                            "The air quality service is not responding properly. "
                            "Please try again later."]


def test_one_fetch_at_a_time(amain, monkeypatch):
    started = []
    monkeypatch.setattr(amain, "_start_thread", lambda target, *args: started.append(args))
    _set(amain)
    done = []
    assert amain.refresh(done.append) and amain.refresh(done.append) and amain.refresh()
    assert len(started) == 1 and len(amain._waiters) == 1
    amain._on_fetched(None, "offline")
    assert done == ["offline"] and not amain._loading


def test_background_refresh_backs_off_after_failures(amain, api, monkeypatch):
    import time
    clock = [100000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set(amain)
    amain._cache = None

    amain._on_minute_tick()
    assert len(calls) == 1
    clock[0] += amain.RETRY_SECONDS
    amain._on_minute_tick()
    assert len(calls) == 2
    clock[0] += amain.RETRY_SECONDS
    amain._on_minute_tick()
    assert len(calls) == 2                       # 20 minutes after two failures
    clock[0] += amain.RETRY_SECONDS
    amain._on_minute_tick()
    assert len(calls) == 3

    calls = _fetch_calls(monkeypatch, api, response=AIR_JSON)
    clock[0] += amain.MAX_RETRY_SECONDS
    amain._on_minute_tick()
    assert len(calls) == 1 and amain._failures == 0
    clock[0] += amain.REFRESH_SECONDS - 60
    amain._on_minute_tick()
    assert len(calls) == 1
    clock[0] += 120
    amain._on_minute_tick()
    assert len(calls) == 2


def test_no_background_fetch_without_a_city(amain, api, monkeypatch):
    calls = _fetch_calls(monkeypatch, api, response=AIR_JSON)
    _set(amain, None)
    amain._on_minute_tick()
    amain._on_app_startup()
    assert calls == []


def test_changing_the_city_fetches_it(amain, api, forecast, monkeypatch):
    import core.api
    calls = _fetch_calls(monkeypatch, api, response=AIR_JSON)
    _set(amain)
    amain._cache = api.make_cache(JAKARTA, forecast)
    amain._save_settings({"location": BANDUNG, "alert": False})
    assert len(calls) == 1 and "latitude=-6.9175" in calls[0]
    assert core.api.load_data(amain.DATA_KEY)["location"]["name"] == "Bandung"


def test_unhealthy_air_is_announced_once_a_day(amain, api, forecast, lang, monkeypatch):
    import core.api
    calls = _fetch_calls(monkeypatch, api, error="offline")
    day = ["2026-09-23"]
    monkeypatch.setattr(amain, "_today", lambda: day[0])
    _set(amain, alert=True)
    amain._cache = api.make_cache(JAKARTA, forecast)

    amain._check_alert()
    assert amain.spoken == ["Air quality alert for Jakarta: index 231, very unhealthy. "
                            + VERY_UNHEALTHY_TIP]
    assert amain.sounds == [amain.ALERT_SOUND]
    assert core.api.load_data(amain.DATA_KEY)["alert_date"] == "2026-09-23"
    amain._check_alert()
    amain._on_app_startup()                      # a restart the same day
    assert len(amain.spoken) == 1
    day[0] = "2026-09-24"
    amain._check_alert()
    assert len(amain.spoken) == 2 and calls == []


def test_alert_after_a_background_fetch(amain, api, lang, monkeypatch):
    _fetch_calls(monkeypatch, api, response=AIR_JSON)
    monkeypatch.setattr(amain, "_today", lambda: "2026-09-23")
    _set(amain, alert=True)
    amain._cache = None
    amain._on_minute_tick()
    assert len(amain.spoken) == 1 and amain.spoken[0].startswith("Air quality alert for Jakarta")


def test_no_alert_when_off_moderate_or_old(amain, api, forecast, monkeypatch):
    import time
    _fetch_calls(monkeypatch, api, error="offline")
    _set(amain, alert=False)
    amain._cache = api.make_cache(JAKARTA, forecast)
    amain._check_alert()
    _set(amain, alert=True)
    amain._cache = api.make_cache(JAKARTA, forecast, now=time.time() - 2 * 3600)
    amain._check_alert()
    forecast["current"]["aqi"] = 120
    amain._cache = api.make_cache(JAKARTA, forecast)
    amain._check_alert()
    assert amain.spoken == [] and amain.sounds == []


def test_briefing_contribution_uses_the_cache_only(amain, api, forecast, lang, monkeypatch):
    import time
    calls = _fetch_calls(monkeypatch, api, error="offline")
    _set(amain)
    amain._cache = api.make_cache(JAKARTA, forecast)
    lines = []
    amain._on_briefing_collect(lines)
    assert lines == ["Air quality in Jakarta: index 231, very unhealthy."]

    lines = []
    amain._cache = api.make_cache(JAKARTA, forecast, now=time.time() - 4 * 3600)
    amain._on_briefing_collect(lines)
    assert lines == []

    _set(amain, None)
    amain._on_briefing_collect(lines)
    assert lines == [] and calls == []


def test_register_and_teardown(amain, fresh_event_bus, monkeypatch, tmp_data_dir):
    import core.api
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *args, **kwargs: panels.append(args))
    for key in (amain.DATA_KEY, amain.CACHE_KEY):
        with open(core.api.get_data_path(key), "w", encoding="utf-8") as f:
            f.write("{not json")

    amain.register(fresh_event_bus)
    assert amain._settings["location"] is None and amain._cache is None
    for event_name, handler in amain._SUBSCRIPTIONS:
        assert handler in fresh_event_bus._listeners[event_name]
    by_name = {args[1]: (args, kwargs) for args, kwargs in actions}
    args, kwargs = by_name["speak_air"]
    assert args[0] == "Air Quality" and args[3] == ord("U") and args[4] is False and kwargs == {}
    args, kwargs = by_name["show_forecast"]
    assert args[0] == "Air Quality" and args[3] == ord("U") and kwargs == {"default_shift": True}
    assert len(panels) == 1

    amain.teardown()
    for event_name, handler in amain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    assert not amain._active


# ------------------------------------------------------------
# Quiet hours (Air Quality 1.1, core 2.7)
# ------------------------------------------------------------

def test_quiet_hours_hold_the_unhealthy_air_alert(amain, api, forecast, lang, monkeypatch):
    import core.api
    import core.personal
    _fetch_calls(monkeypatch, api, error="offline")
    monkeypatch.setattr(amain, "_today", lambda: "2026-09-23")
    quiet = {"on": True}
    monkeypatch.setattr(core.personal, "is_quiet_time", lambda now=None: quiet["on"])
    _set(amain, alert=True)
    amain._cache = api.make_cache(JAKARTA, forecast)
    amain._check_alert()
    assert amain.spoken == [] and amain.sounds == []
    assert core.api.load_data(amain.DATA_KEY).get("alert_date") is None
    quiet["on"] = False
    amain._check_alert()
    assert amain.spoken[0].startswith("Air quality alert for Jakarta: index 231")


def test_manifest_needs_core_2_7_for_quiet_hours():
    with open(os.path.join(AIR_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["version"] == "1.1" and manifest["minimum_core_version"] == "2.7"
