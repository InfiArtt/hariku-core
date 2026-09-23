# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Space extension: ISS and country parsing and sentences, Launch
# Library parsing, local times, launch reminders, the launch cache and request
# pacing, the Sun and Moon maths against published reference values, the
# Morning Briefing sentence, both languages, and the actions. No test touches
# the network: the fetch function is replaced.

import copy
import datetime
import importlib.util
import json
import os
import sys
import urllib.error

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPACE_DIR = os.path.join(ROOT, "extensions", "space")
UTC = datetime.timezone.utc
WIB = datetime.timezone(datetime.timedelta(hours=7))

JAKARTA = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
           "latitude": -6.21462, "longitude": 106.84513, "timezone": "Asia/Jakarta"}

# 12:27 UTC on 23 September 2026 is 19:27 in Jakarta.
NOW = datetime.datetime(2026, 9, 23, 12, 27, tzinfo=UTC)

# wheretheiss.at satellite answer (the shape verified on 23 September 2026;
# the position here is synthetic: over Western Australia).
ISS_JSON = {"name": "iss", "id": 25544, "latitude": -20.5, "longitude": 118.3,
            "altitude": 434.28, "velocity": 27539.4, "visibility": "daylight",
            "footprint": 4580.1, "timestamp": 1790166420, "daynum": 2461307.0,
            "solar_lat": -0.4, "solar_lon": 175.2, "units": "kilometers"}
# wheretheiss.at coordinates answers: over the ocean (verbatim, 23 September
# 2026) and over land.
OCEAN_JSON = {"latitude": "-20.0", "longitude": "80.0", "timezone_id": "Etc/GMT-5",
              "offset": 0, "country_code": "??",
              "map_url": "https://maps.google.com/maps?q=-20.0,80.0&z=4"}
LAND_JSON = {"latitude": "-20.50", "longitude": "118.30", "timezone_id": "Australia/Perth",
             "offset": 8, "country_code": "AU",
             "map_url": "https://maps.google.com/maps?q=-20.50,118.30&z=4"}

# Launch Library 2, /2.2.0/launch/upcoming/?limit=2&mode=list, 23 September
# 2026 (trimmed of the url, slug, image and timestamps).
LAUNCHES_JSON = {"count": 369, "next": None, "previous": None, "results": [
    {"id": "63063b9d-ade9-4448-8717-6f910aa81188",
     "name": "Long March 8A | Unknown Payload",
     "status": {"id": 1, "name": "Go for Launch", "abbrev": "Go",
                "description": "Current T-0 confirmed by official or reliable sources."},
     "net": "2026-09-23T13:30:00Z",
     "net_precision": {"id": 2, "name": "Hour", "abbrev": "HR",
                       "description": "The T-0 is accurate to the hour."},
     "window_end": "2026-09-23T13:49:00Z", "window_start": "2026-09-23T13:24:00Z",
     "lsp_name": "China Aerospace Science and Technology Corporation",
     "mission": "Unknown Payload", "mission_type": "Unknown", "pad": "Commercial LC-1",
     "location": "Wenchang Space Launch Site, People's Republic of China",
     "landing": None, "landing_success": None, "launcher": None, "orbit": None, "type": "list"},
    {"id": "aed67837-b567-43e0-8071-c3ccc24aa496",
     "name": "Long March 6A | Unknown Payload",
     "status": {"id": 1, "name": "Go for Launch", "abbrev": "Go",
                "description": "Current T-0 confirmed by official or reliable sources."},
     "net": "2026-09-24T08:45:00Z",
     "net_precision": {"id": 2, "name": "Hour", "abbrev": "HR",
                       "description": "The T-0 is accurate to the hour."},
     "window_end": "2026-09-24T09:04:00Z", "window_start": "2026-09-24T08:38:00Z",
     "lsp_name": "China Aerospace Science and Technology Corporation",
     "mission": "Unknown Payload", "mission_type": "Unknown", "pad": "Launch Complex 9A",
     "location": "Taiyuan Satellite Launch Center, People's Republic of China",
     "landing": None, "landing_success": None, "launcher": None, "orbit": None, "type": "list"},
]}
LONG_MARCH_8A = "63063b9d-ade9-4448-8717-6f910aa81188"


def _synthetic_launch(launch_id, name, net, precision=2, status=8, location="Cape Canaveral SFS, FL, USA",
                      **extra):
    item = {"id": launch_id, "name": name, "net": net,
            "status": {"id": status, "abbrev": "TBC", "name": "To Be Confirmed"},
            "net_precision": {"id": precision} if precision is not None else None,
            "window_start": net, "window_end": net, "lsp_name": "SpaceX",
            "mission_type": "Communications", "pad": "Space Launch Complex 40",
            "location": location, "orbit": "Low Earth Orbit"}
    item.update(extra)
    return item


def _import_helpers():
    if SPACE_DIR not in sys.path:
        sys.path.insert(0, SPACE_DIR)
    import space_api
    import space_astro
    import space_countries
    import space_text
    return space_api, space_astro, space_countries, space_text


@pytest.fixture(scope="module")
def api():
    return _import_helpers()[0]


@pytest.fixture(scope="module")
def astro():
    return _import_helpers()[1]


@pytest.fixture(scope="module")
def countries():
    return _import_helpers()[2]


@pytest.fixture(scope="module")
def text():
    return _import_helpers()[3]


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
def launches(api):
    return api.parse_launches(copy.deepcopy(LAUNCHES_JSON))


@pytest.fixture
def jakarta_tz(api):
    tz = api.zone_for(JAKARTA)
    assert tz is not None, "tzdata is needed for these tests"
    return tz


def _launch(api, **overrides):
    return api.normalize_launch(_synthetic_launch(**dict(
        {"launch_id": "x1", "name": "Falcon 9 Block 5 | Starlink Group 10-1",
         "net": "2026-09-23T15:00:00Z"}, **overrides)))


# ------------------------------------------------------------
# Locale files and names
# ------------------------------------------------------------

def _messages(code):
    with open(os.path.join(SPACE_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)["messages"]


def test_locales_have_the_same_keys():
    assert set(_messages("en")) == set(_messages("id"))


def test_keys_built_at_run_time_exist(astro, api):
    keys = [f"status_{i}" for i in api.KNOWN_STATUSES]
    keys += [f"phase_{name}" for name in astro.PHASE_NAMES]
    keys += [f"unit_{u}{s}" for u in ("day", "hour", "minute") for s in ("", "_one")]
    for code in ("en", "id"):
        messages = _messages(code)
        assert not [k for k in keys if k not in messages], code


def test_indonesian_phase_names(text, lang):
    lang("id")
    assert [text.phase_name(n) for n in ("new", "waxing_crescent", "first_quarter",
                                         "waxing_gibbous", "full", "waning_gibbous",
                                         "last_quarter", "waning_crescent")] == [
        "Bulan baru", "Bulan sabit awal", "Bulan kuartal pertama", "Bulan cembung awal",
        "Bulan purnama", "Bulan cembung akhir", "Bulan kuartal akhir", "Bulan sabit akhir"]
    lang("en")
    assert text.phase_name("waxing_gibbous") == "Waxing gibbous"


def test_country_table(countries):
    assert countries.country_name("ID") == "Indonesia"
    assert countries.country_name("us") == "the United States"
    assert countries.country_name("US", "id") == "Amerika Serikat"
    assert countries.country_name("CN", "id") == "Tiongkok"
    assert countries.country_name("ZZ") is None
    assert countries.country_name(None) is None
    for code, (en, id_) in countries.COUNTRIES.items():
        assert len(code) == 2 and code.isupper() and en and id_, code


# ------------------------------------------------------------
# ISS: parsing and requests
# ------------------------------------------------------------

def test_parse_iss(api):
    position = api.parse_iss(copy.deepcopy(ISS_JSON))
    assert position == {"latitude": -20.5, "longitude": 118.3, "altitude_km": 434.28,
                        "speed_kmh": 27539.4, "visibility": "daylight"}
    odd = api.parse_iss(dict(ISS_JSON, visibility="night", altitude=None, velocity="fast"))
    assert odd["visibility"] == "" and odd["altitude_km"] is None and odd["speed_kmh"] is None


@pytest.mark.parametrize("payload", [None, [], "x", {}, {"latitude": 1},
                                     dict(ISS_JSON, latitude=95), dict(ISS_JSON, longitude="east")])
def test_parse_iss_rejects_unusable_data(api, payload):
    with pytest.raises(api.SpaceError) as info:
        api.parse_iss(payload)
    assert info.value.kind == "bad_response"


def test_parse_country(api):
    assert api.parse_country(OCEAN_JSON) == ""        # "??" over the ocean
    assert api.parse_country(LAND_JSON) == "AU"
    assert api.parse_country({"country_code": "id"}) == "ID"
    assert api.parse_country({"country_code": None}) == ""
    with pytest.raises(api.SpaceError):
        api.parse_country({"error": "invalid coordinates"})


def test_request_urls_never_carry_the_users_location(api):
    # The country lookup is for the ISS's own point, rounded to 2 decimals.
    assert api.build_coordinates_url(-20.512345, 118.30001) == \
        "https://api.wheretheiss.at/v1/coordinates/-20.51,118.30"
    assert api.ISS_URL == "https://api.wheretheiss.at/v1/satellites/25544"
    assert api.build_launches_url() == \
        "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=15&mode=list"
    url = api.build_search_url(" Jakarta ", "id")
    assert url.startswith("https://geocoding-api.open-meteo.com/v1/search?")
    assert "name=Jakarta&" in url and "language=id" in url
    assert api.USER_AGENT.startswith("HarikuV2/") and api.USER_AGENT.endswith("(Space extension)")


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
    assert seen["agent"] == api.USER_AGENT and seen["timeout"] == api.TIMEOUT_SECONDS


class _Body:
    def __init__(self, data):
        self.data = data

    def read(self, size=-1):
        return self.data

    def close(self):
        pass


@pytest.mark.parametrize("failure, kind, retry_after", [
    (urllib.error.URLError("no route to host"), "offline", None),
    (TimeoutError("timed out"), "offline", None),
    (urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None), "service", None),
    (urllib.error.HTTPError("https://x", 429, "Too Many Requests", {"Retry-After": "120"}, None),
     "rate_limited", 120),
    # Launch Library's own throttling answer.
    (urllib.error.HTTPError("https://x", 429, "Too Many Requests", {},
                            _Body(b'{"detail": "Request was throttled. '
                                  b'Expected available in 1234 seconds."}')),
     "rate_limited", 1234),
])
def test_fetch_json_maps_failures(api, monkeypatch, failure, kind, retry_after):
    def fake_urlopen(req, timeout=None):
        raise failure

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(api.SpaceError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == kind and info.value.retry_after == retry_after


def test_fetch_json_rejects_bad_body(api, monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b"<html>oops</html>"))
    with pytest.raises(api.SpaceError) as info:
        api.fetch_json("https://example.invalid/")
    assert info.value.kind == "bad_response"


def test_iss_gate_paces_and_backs_off(api):
    gate = api.RequestGate()
    assert gate.wait_time(100.0) == 0
    gate.started(100.0)
    gate.finished(None)
    assert gate.wait_time(105.0) == 5.0          # never faster than every 10 seconds
    assert gate.wait_time(110.0) == 0
    gate.started(110.0)
    gate.finished("offline")
    assert gate.wait_time(110.0) == 20.0
    gate.started(130.0)
    gate.finished("offline")
    assert gate.wait_time(130.0) == 40.0
    for _ in range(10):
        gate.finished("offline")
    assert gate.wait_time(130.0) == api.ISS_MAX_BACKOFF
    gate.started(200.0)
    gate.finished(None)
    assert gate.wait_time(200.0) == 10.0
    gate.reset()
    assert gate.wait_time(200.0) == 0


# ------------------------------------------------------------
# ISS: sentences
# ------------------------------------------------------------

def test_iss_report_english(api, text, lang):
    position = api.parse_iss(copy.deepcopy(ISS_JSON))
    assert text.iss_report(position, "AU", JAKARTA, NOW) == (
        "The ISS is 2,000 kilometres southeast of you, over Australia. "
        "It is 434 kilometres up, moving at 27,540 kilometres per hour. It is in sunlight.")
    shadow = dict(position, visibility="eclipsed")
    assert text.iss_report(shadow, "", JAKARTA, NOW).startswith(
        "The ISS is 2,000 kilometres southeast of you, over the ocean. ")
    assert text.iss_report(shadow, "", JAKARTA, NOW).endswith("It is in Earth's shadow.")
    # The country lookup failed: no country, the rest as usual.
    assert text.iss_report(position, None, JAKARTA, NOW).startswith(
        "The ISS is 2,000 kilometres southeast of you. It is 434")


def test_iss_report_indonesian(api, text, lang):
    lang("id")
    position = api.parse_iss(copy.deepcopy(ISS_JSON))
    assert text.iss_report(position, "AU", JAKARTA, NOW) == (
        "ISS berada 2.000 kilometer di sebelah tenggara Anda, di atas Australia. "
        "ISS berada di ketinggian 434 kilometer, melaju 27.540 kilometer per jam. "
        "ISS sedang disinari matahari.")
    assert "dalam bayangan Bumi" in text.iss_report(dict(position, visibility="eclipsed"),
                                                   "", JAKARTA, NOW)
    assert "di atas lautan" in text.iss_report(position, "", JAKARTA, NOW)


def test_iss_overhead_in_a_dark_sky(api, text, lang):
    # 400 km south-east of Jakarta at 20:30 local time: high in a dark sky.
    position = api.parse_iss(dict(ISS_JSON, latitude=-8.0, longitude=110.0))
    evening = datetime.datetime(2026, 9, 23, 13, 30, tzinfo=UTC)
    report = text.iss_report(position, "ID", JAKARTA, evening)
    assert report.startswith("The ISS is 400 kilometres southeast of you, over Indonesia.")
    assert "It is above your horizon now, 45 degrees up, towards the southeast." in report
    assert report.endswith("Your sky is dark, so you may be able to see it.")
    # In Earth's shadow it can't be seen; at midday the sky is too bright.
    assert "may be able to see" not in text.iss_report(dict(position, visibility="eclipsed"),
                                                        "ID", JAKARTA, evening)
    noon = datetime.datetime(2026, 9, 23, 5, 0, tzinfo=UTC)
    report = text.iss_report(position, "ID", JAKARTA, noon)
    assert "above your horizon" in report and "may be able to see" not in report


def test_iss_report_without_a_location(api, text, lang):
    position = api.parse_iss(copy.deepcopy(ISS_JSON))
    assert text.iss_report(position, "", None, NOW) == (
        "The ISS is over the ocean. It is 434 kilometres up, moving at 27,540 kilometres per "
        "hour. It is in sunlight. Choose your city in Preferences, Space, to hear how far "
        "away it is.")
    assert text.iss_report(position, None, None, NOW).startswith(
        "The ISS is above 20 degrees south, 118 degrees east.")
    lang("id")
    assert text.iss_report(position, None, None, NOW).startswith(
        "ISS berada di atas 20 derajat lintang selatan, 118 derajat bujur timur.")


def test_geometry(astro):
    km, bearing = astro.distance_and_bearing(0, 0, 0, 1)
    assert round(km, 1) == 111.2 and round(bearing) == 90
    assert [astro.compass_index(d) for d in (0, 44, 46, 180, 315, 359)] == [0, 1, 1, 4, 7, 0]
    assert round(astro.elevation_angle(0, 420)) == 90
    assert astro.elevation_angle(2500, 420) < 0          # below the horizon
    assert 0 < astro.elevation_angle(1500, 420) < 10


# ------------------------------------------------------------
# Launches: parsing, times, rows
# ------------------------------------------------------------

def test_parse_launches(api, launches):
    assert [launch["id"] for launch in launches] == [LONG_MARCH_8A,
                                                     "aed67837-b567-43e0-8071-c3ccc24aa496"]
    assert launches[0] == {
        "id": LONG_MARCH_8A, "name": "Long March 8A | Unknown Payload",
        "net": "2026-09-23T13:30:00Z", "precision": 2,
        "window_start": "2026-09-23T13:24:00Z", "window_end": "2026-09-23T13:49:00Z",
        "status_id": 1, "status_abbrev": "Go",
        "provider": "China Aerospace Science and Technology Corporation",
        "mission_type": "Unknown", "pad": "Commercial LC-1",
        "location": "Wenchang Space Launch Site, People's Republic of China", "orbit": ""}
    # A launch read back from the cache is the same launch.
    assert api.normalize_launch(json.loads(json.dumps(launches[0]))) == launches[0]


def test_parse_launches_drops_unusable_entries_and_sorts(api):
    payload = {"results": [
        _synthetic_launch("b", "Later", "2026-10-02T10:00:00Z"),
        _synthetic_launch("a", "Sooner", "2026-10-01T10:00:00.123Z"),
        _synthetic_launch("a", "Duplicate", "2026-10-01T10:00:00Z"),
        {"id": "c", "name": "No time"}, {"name": "No id", "net": "2026-10-01T10:00:00Z"},
        "junk", None,
    ]}
    assert [launch["name"] for launch in api.parse_launches(payload)] == ["Sooner", "Later"]
    for bad in (None, {}, {"results": "x"}, []):
        with pytest.raises(api.SpaceError):
            api.parse_launches(bad)


def test_site_and_launch_names(api):
    def site(location):
        return api.site_name({"location": location})
    assert site("Wenchang Space Launch Site, People's Republic of China") == "Wenchang"
    assert site("Taiyuan Satellite Launch Center, People's Republic of China") == "Taiyuan"
    assert site("Cape Canaveral SFS, FL, USA") == "Cape Canaveral"
    assert site("Baikonur Cosmodrome, Republic of Kazakhstan") == "Baikonur"
    assert site("Kennedy Space Center, FL, USA") == "Kennedy Space Center"
    assert site("") == ""
    assert api.launch_name({"name": "Long March 8A | Unknown Payload"}) == \
        "Long March 8A, Unknown Payload"


def test_upcoming_keeps_what_is_still_to_come(api):
    launches = api.parse_launches({"results": [
        _synthetic_launch("gone", "Gone", "2026-09-23T10:00:00Z", status=3),
        _synthetic_launch("flying", "Flying", "2026-09-23T09:00:00Z", status=6),
        _synthetic_launch("just", "Just launched", "2026-09-23T12:00:00Z"),
        _synthetic_launch("next", "Next", "2026-09-23T15:00:00Z"),
    ] + [_synthetic_launch(f"n{i}", f"Later {i}", f"2026-10-{i + 1:02d}T00:00:00Z")
         for i in range(12)]})
    shown = api.upcoming(launches, NOW)
    assert [launch["id"] for launch in shown[:3]] == ["flying", "just", "next"]
    assert len(shown) == api.LAUNCH_LIST_COUNT == 10


def test_launch_rows_in_local_time(api, text, lang, launches, jakarta_tz):
    assert text.launch_row(launches[0], jakarta_tz, NOW) == \
        "Long March 8A, Unknown Payload, today at 20:30, from Wenchang, status Go"
    assert text.launch_row(launches[1], jakarta_tz, NOW, reminder=True) == \
        "Long March 6A, Unknown Payload, tomorrow at 15:45, from Taiyuan, status Go, reminder set"
    later = NOW + datetime.timedelta(days=2)
    assert text.launch_row(launches[1], jakarta_tz, later).startswith(
        "Long March 6A, Unknown Payload, Thursday 24 September at 15:45")
    # The same launch seen from New York.
    new_york = api.zone_for({"timezone": "America/New_York"})
    assert "today at 09:30" in text.launch_row(launches[0], new_york, NOW)
    lang("id")
    assert text.launch_row(launches[0], jakarta_tz, NOW) == \
        "Long March 8A, Unknown Payload, hari ini pukul 20:30, dari Wenchang, status siap meluncur"
    assert text.launch_row(launches[1], jakarta_tz, NOW, reminder=True).endswith(
        "besok pukul 15:45, dari Taiyuan, status siap meluncur, pengingat aktif")


@pytest.mark.parametrize("precision, en, id_", [
    (5, "Friday 25 September, time not yet fixed", "Jumat 25 September, jam belum pasti"),
    (6, "the week of Friday 25 September, date not yet fixed",
     "pekan Jumat 25 September, tanggal belum pasti"),
    (7, "September 2026, date not yet fixed", "September 2026, tanggal belum pasti"),
    (None, "Friday 25 September at 09:00", "Jumat 25 September pukul 09:00"),
])
def test_when_follows_the_precision(api, text, lang, jakarta_tz, precision, en, id_):
    launch = _launch(api, net="2026-09-25T02:00:00Z", precision=precision)
    assert text.when_text(launch, jakarta_tz, NOW) == en
    lang("id")
    assert text.when_text(launch, jakarta_tz, NOW) == id_


def test_launch_status_words(api, text, lang):
    assert text.status_text({"status_id": 3}) == "launched successfully"
    assert text.status_text({"status_id": 99, "status_abbrev": "Hold"}) == "Hold"
    assert text.status_text({}) == "unknown"
    lang("id")
    assert text.status_text({"status_id": 5}) == "ditahan"


def test_launch_details(api, text, lang, launches, jakarta_tz):
    assert text.launch_details(launches[0], jakarta_tz, NOW, reminder_lead=30) == (
        "Long March 8A, Unknown Payload. Launch time: today at 20:30. "
        "That is in 1 hour 3 minutes. Launch window from 20:24 to 20:49. Status: Go. "
        "Launch provider: China Aerospace Science and Technology Corporation. "
        "Launch pad: Commercial LC-1, Wenchang Space Launch Site, People's Republic of China. "
        "You'll be reminded 30 minutes before.")
    other = _launch(api)
    details = text.launch_details(other, jakarta_tz, NOW)
    assert "The launch window is instantaneous." in details
    assert "Mission type: Communications. Orbit: Low Earth Orbit." in details
    lang("id")
    assert text.launch_details(launches[0], jakarta_tz, NOW).startswith(
        "Long March 8A, Unknown Payload. Waktu peluncuran: hari ini pukul 20:30. "
        "Itu 1 jam 3 menit lagi. Jendela peluncuran pukul 20:24 sampai 20:49.")


def test_durations(text, lang):
    assert text.duration_text(125) == "2 hours 5 minutes"
    assert text.duration_text(60) == "1 hour"
    assert text.duration_text(1) == "1 minute"
    assert text.duration_text(0.2) == "less than a minute"
    assert text.duration_text(3 * 1440 + 65) == "3 days 1 hour"
    lang("id")
    assert text.duration_text(125) == "2 jam 5 menit"


# ------------------------------------------------------------
# Launch reminders
# ------------------------------------------------------------

def _at(hour, minute):
    return datetime.datetime(2026, 9, 23, hour, minute, tzinfo=UTC)


def test_reminder_is_announced_once_within_the_lead_time(api, launches):
    index = {launch["id"]: launch for launch in launches}
    reminders = [api.new_reminder(launches[0])]         # launch at 13:30 UTC
    due, reminders = api.check_reminders(reminders, index, _at(12, 59), 30)
    assert due == []
    due, reminders = api.check_reminders(reminders, index, _at(13, 0), 30)
    assert [(r["id"], net) for r, _launch, net in due] == [(LONG_MARCH_8A, _at(13, 30))]
    for minute in range(1, 30):
        due, reminders = api.check_reminders(reminders, index, _at(13, minute), 30)
        assert due == [], minute                         # once only
    due, reminders = api.check_reminders(reminders, index, _at(13, 35), 30)
    assert due == [] and len(reminders) == 1             # launched; kept a while


def test_reminder_lead_time(api, launches):
    index = {launch["id"]: launch for launch in launches}
    for lead, first in ((10, _at(13, 20)), (60, _at(12, 30))):
        reminders = [api.new_reminder(launches[0])]
        before = first - datetime.timedelta(minutes=1)
        assert api.check_reminders(reminders, index, before, lead)[0] == []
        assert len(api.check_reminders(reminders, index, first, lead)[0]) == 1


def test_reminder_catches_up_but_never_after_the_launch(api, launches):
    index = {launch["id"]: launch for launch in launches}
    # Hariku was off at 13:00; at 13:20 the launch is still ahead.
    due, _kept = api.check_reminders([api.new_reminder(launches[0])], index, _at(13, 20), 30)
    assert len(due) == 1
    due, _kept = api.check_reminders([api.new_reminder(launches[0])], index, _at(13, 30), 30)
    assert due == []


def test_reminder_follows_a_rescheduled_launch(api, launches):
    index = {launch["id"]: launch for launch in launches}
    due, reminders = api.check_reminders([api.new_reminder(launches[0])], index, _at(13, 0), 30)
    assert len(due) == 1
    # A small slip is the same launch time: not announced again.
    index[LONG_MARCH_8A] = dict(launches[0], net="2026-09-23T13:40:00Z")
    due, reminders = api.check_reminders(reminders, index, _at(13, 15), 30)
    assert due == [] and reminders[0]["net"] == "2026-09-23T13:40:00Z"
    # Scrubbed to tomorrow: announced again before the new time.
    index[LONG_MARCH_8A] = dict(launches[0], net="2026-09-24T13:30:00Z")
    due, reminders = api.check_reminders(reminders, index, _at(13, 20), 30)
    assert due == []
    tomorrow = datetime.datetime(2026, 9, 24, 13, 0, tzinfo=UTC)
    due, reminders = api.check_reminders(reminders, index, tomorrow, 30)
    assert len(due) == 1
    # Only known to the day now: not announced.
    index[LONG_MARCH_8A] = dict(launches[0], net="2026-09-25T13:30:00Z", precision=5)
    later = datetime.datetime(2026, 9, 25, 13, 10, tzinfo=UTC)
    assert api.check_reminders(reminders, index, later, 30)[0] == []


def test_reminders_are_forgotten_after_the_launch(api, launches):
    reminders = [api.new_reminder(launches[0])]
    # Not in the launch list any more: the stored time is used.
    late = _at(13, 30) + datetime.timedelta(seconds=api.REMINDER_KEEP_SECONDS + 60)
    assert api.check_reminders(reminders, {}, late, 30) == ([], [])
    assert len(api.check_reminders(reminders, {}, _at(13, 5), 30)[0]) == 1


def test_stored_reminders_survive_corrupt_data(api):
    assert api.normalize_reminders(None) == []
    assert api.normalize_reminders([{"id": "a"}, "x", {"id": "b", "net": "soon"},
                                    {"id": "c", "net": "2026-09-23T13:30:00Z", "name": 5}]) == [
        {"id": "c", "name": "5", "net": "2026-09-23T13:30:00Z", "notified_for": ""}]
    many = [{"id": str(i), "net": "2026-09-23T13:30:00Z"} for i in range(50)]
    assert len(api.normalize_reminders(many)) == api.MAX_REMINDERS


def test_reminder_text(api, text, lang, launches, jakarta_tz):
    net = _at(13, 30)
    assert text.reminder_due_text("x", launches[0], net, jakarta_tz, _at(13, 0)) == \
        "Rocket launch in 30 minutes: Long March 8A, Unknown Payload, at 20:30, from Wenchang."
    assert text.reminder_due_text("Long March 8A | Unknown Payload", None, net, jakarta_tz,
                                  _at(13, 29, )) == \
        "Rocket launch in 1 minute: Long March 8A, Unknown Payload, at 20:30."
    lang("id")
    assert text.reminder_due_text("x", launches[0], net, jakarta_tz, _at(13, 0)) == \
        "Peluncuran roket 30 menit lagi: Long March 8A, Unknown Payload, pukul 20:30, dari Wenchang."


# ------------------------------------------------------------
# Launch cache and pacing (Launch Library: about 15 requests an hour)
# ------------------------------------------------------------

def test_launch_fetch_decisions(api, launches):
    t0 = 1_000_000.0
    state = api.empty_launch_state()
    assert api.launch_fetch_decision(state, t0, api.LAUNCH_AUTO_AGE) == "fetch"
    state = api.after_launch_fetch(state, t0, launches)
    assert state["fetched_at"] == t0 and state["failures"] == 0
    # Automatic refreshes: once an hour. The Refresh button: after 15 minutes.
    assert api.launch_fetch_decision(state, t0 + 3599, api.LAUNCH_AUTO_AGE) == "fresh"
    assert api.launch_fetch_decision(state, t0 + 3600, api.LAUNCH_AUTO_AGE) == "fetch"
    assert api.launch_fetch_decision(state, t0 + 899, api.LAUNCH_MANUAL_AGE) == "fresh"
    assert api.launch_fetch_decision(state, t0 + 900, api.LAUNCH_MANUAL_AGE) == "fetch"
    # The clock went backwards: the cache counts as stale.
    assert api.launch_fetch_decision(state, t0 - 100, api.LAUNCH_AUTO_AGE) == "fetch"


def test_launch_failures_back_off(api, launches):
    t0 = 1_000_000.0
    state = api.after_launch_fetch(api.empty_launch_state(), t0, launches)
    waits = []
    now = t0 + 3600
    for _ in range(6):
        state = api.after_launch_fetch(state, now, error="offline")
        waits.append(state["retry_after"] - now)
        assert api.launch_fetch_decision(state, now + 1, api.LAUNCH_MANUAL_AGE) == "wait"
        now = state["retry_after"]
    assert waits == [300, 600, 1200, 2400, 3600, 3600]
    assert state["launches"] == launches                # the old list is kept
    assert api.launch_fetch_decision(state, now, api.LAUNCH_MANUAL_AGE) == "fetch"
    state = api.after_launch_fetch(state, now, launches)
    assert state["failures"] == 0 and state["retry_after"] == 0


def test_rate_limited_waits_as_asked(api):
    state = api.after_launch_fetch(api.empty_launch_state(), 0.0, error="rate_limited",
                                   retry_after=1234)
    assert state["retry_after"] == 1234
    state = api.after_launch_fetch(api.empty_launch_state(), 0.0, error="rate_limited")
    assert state["retry_after"] == api.LAUNCH_RATE_LIMIT_WAIT
    state = api.after_launch_fetch(api.empty_launch_state(), 0.0, error="rate_limited",
                                   retry_after=999999)
    assert state["retry_after"] == api.LAUNCH_MAX_WAIT
    # A retry time far in the future (the clock was changed) does not lock out.
    assert api.launch_wait({"retry_after": 10 * 3600.0}, 0.0) == 0


@pytest.mark.parametrize("raw", [None, "x", [], {}, {"launches": "x", "fetched_at": "soon"},
                                 {"launches": [None, {"id": "a"}], "failures": -3}])
def test_launch_state_survives_corrupt_data(api, raw):
    state = api.normalize_launch_state(raw)
    assert state["launches"] == [] and state["failures"] == 0 and state["retry_after"] == 0


def test_launch_state_round_trip(api, launches):
    vague = _launch(api, launch_id="v", net="2026-12-31T00:00:00Z", precision=7)
    state = api.after_launch_fetch(api.empty_launch_state(), 5.0, launches + [vague])
    restored = api.normalize_launch_state(json.loads(json.dumps(state)))
    assert restored == state
    # A launch only known to the month stays vague after a restart.
    assert not api.is_exact(restored["launches"][-1])


# ------------------------------------------------------------
# Sun and Moon against published values
# ------------------------------------------------------------

# Sunrise and sunset in Jakarta (6°12'S, 106°49'E, UTC+7) from the table
# "Sunrise, sunset and twilights in Jakarta in 2024",
# https://www.stjerneskinn.com/sunrise-world-jakarta.htm (computed with Jean
# Meeus' Astronomical Algorithms; whole minutes).
JAKARTA_SUN_2024 = [
    (datetime.date(2024, 1, 1), (5, 41), (18, 10)),
    (datetime.date(2024, 3, 20), (5, 56), (18, 3)),
    (datetime.date(2024, 9, 23), (5, 41), (17, 48)),
]


@pytest.mark.parametrize("day, sunrise, sunset", JAKARTA_SUN_2024)
def test_sunrise_and_sunset_in_jakarta(astro, day, sunrise, sunset):
    times = astro.sun_times(day, -(6 + 12 / 60), 106 + 49 / 60, WIB)
    for got, (hour, minute) in ((times["sunrise"], sunrise), (times["sunset"], sunset)):
        expected = datetime.datetime.combine(day, datetime.time(hour, minute), WIB)
        assert abs((got - expected).total_seconds()) <= 120, (got, expected)
    assert times["polar"] is None and times["sunrise"].tzinfo is WIB


def test_sun_in_a_zone_far_from_its_longitude(astro):
    # Kiritimati (Kiribati) keeps UTC+14 at 157°W: still the right local day.
    tz = datetime.timezone(datetime.timedelta(hours=14))
    times = astro.sun_times(datetime.date(2026, 3, 20), 1.87, -157.4, tz)
    assert times["sunrise"].date() == times["sunset"].date() == datetime.date(2026, 3, 20)
    assert 5 <= times["sunrise"].hour <= 7 and 17 <= times["sunset"].hour <= 19


def test_polar_day_and_night(astro):
    tz = datetime.timezone(datetime.timedelta(hours=1))
    summer = astro.sun_times(datetime.date(2026, 6, 21), 69.65, 18.96, tz)    # Tromsø
    winter = astro.sun_times(datetime.date(2026, 12, 21), 69.65, 18.96, tz)
    assert summer["polar"] == "day" and summer["sunrise"] is None and summer["sunset"] is None
    assert winter["polar"] == "night"


def test_sun_altitude(astro):
    # Local noon on the March equinox in Jakarta: 90 - 6.2 degrees.
    noon = datetime.datetime(2024, 3, 20, 5, 0, tzinfo=UTC)
    assert abs(astro.sun_altitude(noon, -6.2, 106.8167) - 83.8) < 0.3
    assert astro.sun_altitude(datetime.datetime(2024, 3, 20, 17, 0, tzinfo=UTC), -6.2, 106.8) < -60


def test_meeus_worked_examples(astro):
    # Astronomical Algorithms, 2nd ed., examples 49.a and 49.b (JDE).
    assert abs(astro.phase_jde(-283) - 2443192.65118) < 0.00001     # new moon, 18 Feb 1977
    assert abs(astro.phase_jde(544.75) - 2467636.49186) < 0.00001   # last quarter, 21 Jan 2044


# Universal Time of phases from NASA GSFC, Fred Espenak, "Phases of the Moon:
# 2001 to 2100", https://eclipse.gsfc.nasa.gov/phase/phases2001.html
NASA_PHASES = [
    ("NEW", (2024, 4, 8, 18, 21)),            # total solar eclipse
    ("FIRST_QUARTER", (2024, 1, 18, 3, 53)),
    ("FULL", (2024, 9, 18, 2, 34)),           # partial lunar eclipse
    ("LAST_QUARTER", (2024, 2, 2, 23, 18)),
    ("NEW", (2024, 10, 2, 18, 49)),           # annular solar eclipse
    ("FULL", (2026, 3, 3, 11, 38)),           # total lunar eclipse
    ("NEW", (2026, 8, 12, 17, 37)),           # total solar eclipse
    ("FIRST_QUARTER", (2026, 9, 18, 20, 44)),
    ("FULL", (2026, 9, 26, 16, 49)),
    ("LAST_QUARTER", (2026, 10, 3, 13, 25)),
    ("NEW", (2026, 10, 10, 15, 50)),
]


@pytest.mark.parametrize("phase, when", NASA_PHASES)
def test_moon_phases_match_nasa(astro, phase, when):
    expected = datetime.datetime(*when, tzinfo=UTC)
    got = astro.next_phase(expected - datetime.timedelta(days=3), getattr(astro, phase))
    assert abs((got - expected).total_seconds()) <= 5 * 60, got
    assert astro.previous_phase(expected + datetime.timedelta(days=3),
                                getattr(astro, phase)) == got


def test_illuminated_fraction(astro):
    assert astro.illuminated_fraction(datetime.datetime(2026, 9, 26, 16, 49, tzinfo=UTC)) > 0.995
    assert astro.illuminated_fraction(datetime.datetime(2026, 10, 10, 15, 50, tzinfo=UTC)) < 0.005
    half = astro.illuminated_fraction(datetime.datetime(2026, 9, 18, 20, 44, tzinfo=UTC))
    assert abs(half - 0.5) < 0.02


@pytest.mark.parametrize("when, name", [
    ((2026, 9, 23, 12, 27), "waxing_gibbous"),
    ((2026, 9, 26, 3, 0), "full"),              # full at 23:49 Jakarta time that day
    ((2026, 9, 27, 3, 0), "waning_gibbous"),
    ((2026, 10, 3, 1, 0), "last_quarter"),
    ((2026, 10, 6, 1, 0), "waning_crescent"),
    ((2026, 10, 10, 1, 0), "new"),
    ((2026, 10, 13, 1, 0), "waxing_crescent"),
    ((2026, 10, 18, 1, 0), "first_quarter"),
])
def test_moon_phase_names(astro, when, name):
    jakarta = datetime.timezone(datetime.timedelta(hours=7))
    assert astro.moon_phase(datetime.datetime(*when, tzinfo=UTC), jakarta)["name"] == name


def test_next_new_and_full_moon(astro):
    moon = astro.moon_phase(NOW, WIB)
    assert abs((moon["next_full"] - datetime.datetime(2026, 9, 26, 16, 49, tzinfo=UTC))
               .total_seconds()) < 300
    assert abs((moon["next_new"] - datetime.datetime(2026, 10, 10, 15, 50, tzinfo=UTC))
               .total_seconds()) < 300


def test_sun_and_moon_report(text, lang, jakarta_tz):
    assert text.sun_moon_report(JAKARTA, jakarta_tz, NOW) == (
        "Jakarta, Wednesday 23 September. Sunrise at 05:42, sunset at 17:48, "
        "12 hours 6 minutes of daylight. Tomorrow the sun rises at 05:41. "
        "Moon phase: Waxing gibbous, 89 percent illuminated. "
        "Next full moon: Saturday 26 September at 23:49. "
        "Next new moon: Saturday 10 October at 22:50.")
    morning = datetime.datetime(2026, 9, 23, 1, 0, tzinfo=UTC)
    assert "Tomorrow" not in text.sun_moon_report(JAKARTA, jakarta_tz, morning)
    lang("id")
    assert text.sun_moon_report(JAKARTA, jakarta_tz, NOW) == (
        "Jakarta, Rabu 23 September. Matahari terbit pukul 05:42, terbenam pukul 17:48, "
        "lama siang 12 jam 6 menit. Besok matahari terbit pukul 05:41. "
        "Fase bulan: Bulan cembung awal, 89 persen tersinari. "
        "Purnama berikutnya: Sabtu 26 September pukul 23:49. "
        "Bulan baru berikutnya: Sabtu 10 Oktober pukul 22:50.")


def test_sun_and_moon_without_a_location(text, lang):
    report = text.sun_moon_report(None, WIB, NOW)
    assert report.startswith("Moon phase: Waxing gibbous, 89 percent illuminated.")
    assert report.endswith("Choose your city in Preferences, Space, to hear sunrise and "
                           "sunset times.")


def test_briefing_text(api, text, lang, launches, jakarta_tz):
    assert text.briefing_text(JAKARTA, jakarta_tz, NOW, launches[:1]) == (
        "Sunset at 17:48; moon phase: Waxing gibbous, 89 percent illuminated. "
        "Rocket launch today at 20:30: Long March 8A, Unknown Payload.")
    assert text.briefing_text(JAKARTA, jakarta_tz, NOW, launches).endswith(
        "2 rocket launches today, the first at 20:30: Long March 8A, Unknown Payload.")
    assert text.briefing_text(None, jakarta_tz, NOW, []) == \
        "Moon phase: Waxing gibbous, 89 percent illuminated."
    lang("id")
    assert text.briefing_text(JAKARTA, jakarta_tz, NOW, launches[:1]) == (
        "Matahari terbenam pukul 17:48; fase bulan: Bulan cembung awal, 89 persen tersinari. "
        "Peluncuran roket hari ini pukul 20:30: Long March 8A, Unknown Payload.")


def test_time_zones(api):
    assert api.zone_for(JAKARTA) is not None
    assert api.zone_for({"timezone": "Not/AZone"}) is None
    assert api.zone_for({"timezone": ""}) is None and api.zone_for(None) is None


@pytest.mark.parametrize("raw", [None, "x", {}, {"location": "Jakarta", "lead_minutes": 45},
                                 {"lead_minutes": True},
                                 {"location": {"name": "X", "latitude": 95, "longitude": 1}}])
def test_settings_survive_corrupt_data(api, raw):
    assert api.normalize_settings(raw) == {"location": None, "lead_minutes": 30}


def test_settings_keep_valid_values(api):
    settings = api.normalize_settings({"location": JAKARTA, "lead_minutes": 60, "x": 1})
    assert settings == {"location": JAKARTA, "lead_minutes": 60}


# ------------------------------------------------------------
# The settings page logic (stand-in controls; wx is mocked here)
# ------------------------------------------------------------

BANDUNG = {"name": "Bandung", "admin1": "West Java", "country": "Indonesia",
           "latitude": -6.9175, "longitude": 107.6191, "timezone": "Asia/Jakarta"}


@pytest.fixture
def make_panel(monkeypatch, api, text, lang):
    """Builds the real SpacePanel with plain stand-ins for its controls, and
    records what it speaks and every focus change."""
    from unittest.mock import MagicMock
    import space_ui
    spoken, focus_moves = [], []

    class _Control:
        def __init__(self, *args, value="", choices=None, label="", **kwargs):
            self.value, self.label = value, label
            self.items, self.selection, self.edits = list(choices or []), -1, 0

        def SetName(self, name):
            self.name = name

        def Bind(self, *args, **kwargs):
            pass

        def SetValue(self, value):
            self.value = value
            self.edits += 1

        def ChangeValue(self, value):
            self.value = value

        def GetValue(self):
            return self.value

        def Set(self, items):
            self.items = list(items)

        def SetSelection(self, index):
            self.selection = index

        def GetSelection(self):
            return self.selection

        def SetLabel(self, label):
            self.label = label

        def SetFocus(self):
            focus_moves.append(self)

    for name in ("StaticText", "TextCtrl", "Button", "ListBox", "Choice"):
        monkeypatch.setattr(space_ui.wx, name, _Control)
    monkeypatch.setattr(space_ui.wx, "BoxSizer", lambda *args, **kwargs: MagicMock())
    monkeypatch.setattr(space_ui.wx, "NOT_FOUND", -1)
    monkeypatch.setattr(space_ui.core.ui_scale, "apply_appearance", lambda window: None)
    monkeypatch.setattr(space_ui, "speak", lambda msg, interrupt=False: spoken.append(msg))

    class _Panel(space_ui.SpacePanel):
        # wx.Panel is a MagicMock here; its own calls (SetSizer, Layout) get plain mocks.
        def _get_child_mock(self, **kwargs):
            return MagicMock(**kwargs)

    def make(location=None, weather=None, lead=30):
        panel = _Panel(None, {"location": location, "lead_minutes": lead}, weather)
        panel.spoken, panel.focus_moves = spoken, focus_moves
        return panel

    return make


def test_use_the_weather_location(make_panel, lang):
    panel = make_panel(location=BANDUNG, weather=JAKARTA)
    assert panel.txt_location.GetValue() == "Bandung, West Java, Indonesia"
    assert panel.btn_use_weather.label == "Use the &Weather location"
    assert panel.get_settings() == {"location": BANDUNG, "lead_minutes": 30}
    panel._on_use_weather(None)
    assert panel.spoken == ["Jakarta, Indonesia, the Weather location, will be used. "
                            "Press OK to save."]
    assert panel.txt_location.GetValue() == "Jakarta, Indonesia (from the Weather settings)"
    assert panel.txt_location.edits == 1          # Preferences sees a change to save
    assert panel.get_settings() == {"location": None, "lead_minutes": 30}
    assert panel.focus_moves == []                # focus stays on the button


def test_use_the_weather_location_without_one(make_panel, lang):
    panel = make_panel(location=BANDUNG, weather=None)
    panel._on_use_weather(None)
    assert panel.spoken == ["No Weather location is set yet. Choose one here, or in "
                            "Preferences, Weather."]
    assert panel.txt_location.GetValue() == "Not set"
    assert panel.chosen_location() is None and panel.focus_moves == []
    lang("id")
    assert make_panel(weather=JAKARTA).btn_use_weather.label == "&Gunakan lokasi Cuaca"
    panel._on_use_weather(None)
    assert panel.spoken[-1] == ("Lokasi Cuaca belum diatur. Pilih tempat di sini, atau di "
                                "Pengaturan, Cuaca.")


def test_search_result_and_weather_location_take_turns(make_panel, api):
    from unittest.mock import MagicMock
    panel = make_panel(location=None, weather=JAKARTA)
    assert panel.txt_location.GetValue() == "Jakarta, Indonesia (from the Weather settings)"
    panel._search_id = 1
    panel._on_search_done(1, "Bandung", [BANDUNG, dict(BANDUNG, name="Bandung Barat")], None)
    assert panel.chosen_location() == BANDUNG      # the first result, selected
    panel._on_use_weather(None)
    assert panel.list_results.GetSelection() == -1 and panel.chosen_location() is None
    panel.list_results.SetSelection(1)
    panel._on_result_selected(MagicMock())        # an arrow key in the results
    assert panel.chosen_location()["name"] == "Bandung Barat"
    assert panel.focus_moves == []


def test_applying_the_weather_location(smain, api, make_panel):
    import core.api
    core.api.save_data("Weather", {"location": BANDUNG, "units": "metric"})
    assert smain.get_location()["name"] == "Jakarta"      # its own city
    panel = make_panel(location=JAKARTA, weather=smain.weather_location())
    smain._panel = panel
    panel._on_use_weather(None)
    smain._apply_panel()
    assert core.api.load_data("Space")["location"] is None
    assert smain.get_location() == BANDUNG
    assert panel.txt_location.GetValue() == "Bandung, West Java, Indonesia (from the Weather settings)"
    smain.speak_sun_moon()
    assert smain.spoken[-1].startswith("Bandung, Wednesday 23 September.")


# ------------------------------------------------------------
# The extension (main.py)
# ------------------------------------------------------------

class _Clock:
    def __init__(self, start):
        self.t = start

    def __call__(self):
        return self.t


@pytest.fixture
def smain(monkeypatch, tmp_data_dir, api, text, lang):
    """main.py with speech and sounds captured, threads run inline and every
    clock controlled."""
    spec = importlib.util.spec_from_file_location("space_main_under_test",
                                                  os.path.join(SPACE_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken, sounds = [], []
    mono, wall, utc = _Clock(1000.0), _Clock(NOW.timestamp()), _Clock(NOW)
    monkeypatch.setattr(module, "speak", lambda msg, interrupt=False: spoken.append(msg))
    monkeypatch.setattr(module, "_start_thread", lambda target, *args: target(*args))
    monkeypatch.setattr(module, "_sleep", lambda seconds: None)
    monkeypatch.setattr(module, "_play_sound", sounds.append)
    monkeypatch.setattr(module, "_now", mono)
    monkeypatch.setattr(module, "_wall", wall)
    monkeypatch.setattr(module, "_utcnow", utc)

    def advance(seconds):
        mono.t += seconds
        wall.t += seconds
        utc.t += datetime.timedelta(seconds=seconds)

    module._active = True
    module._settings = api.normalize_settings({"location": JAKARTA})
    module.spoken, module.sounds, module.advance = spoken, sounds, advance
    yield module
    module._active = False


def _services(monkeypatch, api, errors=None, country=LAND_JSON):
    """Replace the network: answers by URL; `errors` maps a URL prefix to the
    error kind to raise."""
    calls = []

    def fake_fetch_json(url):
        calls.append(url)
        for prefix, kind in (errors or {}).items():
            if url.startswith(prefix):
                raise api.SpaceError(kind, "test", 60 if kind == "rate_limited" else None)
        if url == api.ISS_URL:
            return copy.deepcopy(ISS_JSON)
        if url.startswith("https://api.wheretheiss.at/v1/coordinates/"):
            return copy.deepcopy(country)
        if url.startswith(api.LAUNCHES_URL):
            return copy.deepcopy(LAUNCHES_JSON)
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(api, "fetch_json", fake_fetch_json)
    return calls


def test_where_is_the_iss(smain, api, monkeypatch):
    calls = _services(monkeypatch, api)
    smain.speak_iss()
    assert calls == [api.ISS_URL, "https://api.wheretheiss.at/v1/coordinates/-20.50,118.30"]
    assert smain.spoken == ["Checking where the ISS is...", (
        "The ISS is 2,000 kilometres southeast of you, over Australia. It is 434 kilometres "
        "up, moving at 27,540 kilometres per hour. It is in sunlight.")]
    # The user's own point is never sent anywhere.
    assert not [u for u in calls if "6.21" in u or "106.8" in u]

    smain.advance(9)
    smain.speak_iss()                     # within 10 seconds: the same answer, no request
    assert len(calls) == 2 and smain.spoken[-1] == smain.spoken[1]
    smain.advance(2)
    smain.speak_iss()
    assert len(calls) == 4


def test_iss_one_request_at_a_time(smain, api, monkeypatch):
    started = []
    monkeypatch.setattr(smain, "_start_thread", lambda target, *args: started.append(target))
    smain.speak_iss()
    smain.speak_iss()
    smain.speak_iss()
    assert len(started) == 1 and len(smain._iss_waiters) == 1
    smain._on_iss_fetched(None, None, "offline")
    assert smain.spoken[-1] == ("Could not reach the ISS position service. "
                                "Check your internet connection.")


def test_iss_errors_back_off(smain, api, monkeypatch):
    calls = _services(monkeypatch, api, errors={api.ISS_URL: "offline"})
    smain.speak_iss()
    assert calls == [api.ISS_URL]
    assert smain.spoken[-1].startswith("Could not reach the ISS position service.")
    smain.advance(5)
    smain.speak_iss()                     # backing off: no request, a hint instead
    assert calls == [api.ISS_URL]
    assert smain.spoken[-1].endswith("You can try again in 15 seconds.")
    smain.advance(15)
    smain.speak_iss()
    assert calls == [api.ISS_URL] * 2
    smain._on_network_changed(True)       # back online: no need to wait
    smain.speak_iss()
    assert len(calls) == 3


def test_iss_without_the_country(smain, api, monkeypatch):
    calls = _services(monkeypatch, api, errors={"https://api.wheretheiss.at/v1/coordinates/":
                                                "service"})
    smain.speak_iss()
    assert len(calls) == 2
    assert smain.spoken[-1].startswith("The ISS is 2,000 kilometres southeast of you. It is 434")


def test_iss_without_any_location(smain, api, monkeypatch):
    _services(monkeypatch, api, country=OCEAN_JSON)
    smain._settings = api.normalize_settings(None)
    smain.speak_iss()
    assert smain.spoken[-1].startswith("The ISS is over the ocean.")
    assert smain.spoken[-1].endswith("to hear how far away it is.")


def test_weather_city_is_the_default(smain, api):
    import core.api
    smain._settings = api.normalize_settings(None)
    assert smain.get_location() is None
    core.api.save_data("Weather", {"location": JAKARTA, "units": "metric"})
    assert smain.get_location() == JAKARTA
    bandung = dict(JAKARTA, name="Bandung", latitude=-6.9175, longitude=107.6191)
    smain._save_settings({"location": bandung})
    assert smain.get_location()["name"] == "Bandung"
    assert core.api.load_data("Space") == {"location": bandung, "lead_minutes": 30}


def test_launch_refresh_is_paced(smain, api, monkeypatch):
    import core.api
    calls = _services(monkeypatch, api)
    done = []
    assert smain.refresh_launches(done.append) == ("started", "")
    assert done == [None] and len(calls) == 1
    assert [l["id"] for l in smain.launch_data()[0]] == [LONG_MARCH_8A,
                                                         "aed67837-b567-43e0-8071-c3ccc24aa496"]
    saved = api.normalize_launch_state(core.api.load_data("SpaceLaunches"))
    assert len(saved["launches"]) == 2 and saved["fetched_at"] == NOW.timestamp()

    status, message = smain.refresh_launches(done.append, explicit=True)
    assert status == "fresh" and message.startswith("The launch list is up to date;")
    smain.advance(15 * 60)
    assert smain.refresh_launches(explicit=False)[0] == "fresh"     # automatic: hourly
    assert smain.refresh_launches(explicit=True)[0] == "started"    # the button: 15 minutes
    assert len(calls) == 2


def test_launch_failure_waits_and_survives_restart(smain, api, monkeypatch):
    import core.api
    calls = _services(monkeypatch, api, errors={api.LAUNCHES_URL: "rate_limited"})
    errors = []
    smain.refresh_launches(errors.append, explicit=True)
    assert errors == ["rate_limited"] and len(calls) == 1
    status, message = smain.refresh_launches(explicit=True)
    assert status == "wait" and "can be refreshed again after" in message
    assert len(calls) == 1
    stored = api.normalize_launch_state(core.api.load_data("SpaceLaunches"))
    assert stored["retry_after"] == NOW.timestamp() + 60 and stored["failures"] == 1
    smain.advance(61)
    assert smain.refresh_launches(explicit=True)[0] == "started"


def test_launch_one_request_at_a_time(smain, api, monkeypatch):
    started = []
    monkeypatch.setattr(smain, "_start_thread", lambda target, *args: started.append(target))
    first, second = [], []
    assert smain.refresh_launches(first.append)[0] == "started"
    assert smain.refresh_launches(second.append, explicit=True)[0] == "started"
    assert len(started) == 1
    smain._on_launches_fetched(api.parse_launches(copy.deepcopy(LAUNCHES_JSON)), None, None)
    assert first == [None] and second == [None]


def _load_launches(smain, api):
    smain._launch_state = api.after_launch_fetch(
        api.empty_launch_state(), NOW.timestamp(), api.parse_launches(copy.deepcopy(LAUNCHES_JSON)))
    smain._index_launches()
    return smain.launch_data()[0]


def test_remind_me(smain, api, lang):
    import core.api
    launches = _load_launches(smain, api)
    assert smain.toggle_reminder(launches[0]) == \
        "You'll be reminded 30 minutes before Long March 8A, Unknown Payload."
    assert smain.has_reminder(LONG_MARCH_8A)
    stored = core.api.load_data("SpaceReminders")["reminders"]
    assert stored == [{"id": LONG_MARCH_8A, "name": "Long March 8A | Unknown Payload",
                       "net": "2026-09-23T13:30:00Z", "notified_for": ""}]
    assert smain.toggle_reminder(launches[0]) == \
        "Reminder cancelled for Long March 8A, Unknown Payload."
    assert not smain.has_reminder(LONG_MARCH_8A)
    assert core.api.load_data("SpaceReminders")["reminders"] == []

    vague = api.normalize_launch(_synthetic_launch("v", "Vague", "2026-10-01T00:00:00Z", precision=7))
    assert smain.toggle_reminder(vague) == \
        "Vague has no exact launch time yet, so a reminder can't be set."
    past = api.normalize_launch(_synthetic_launch("p", "Past", "2026-09-23T12:00:00Z"))
    assert smain.toggle_reminder(past) == "The launch time of Past has already passed."
    smain._reminders = [api.new_reminder(dict(launches[1], id=str(i))) for i in range(20)]
    assert smain.toggle_reminder(launches[0]).startswith("You can have up to 20 launch reminders.")
    lang("id")
    smain._reminders = []
    assert smain.toggle_reminder(launches[0]) == \
        "Anda akan diingatkan 30 menit sebelum peluncuran Long March 8A, Unknown Payload."


def test_minute_tick_announces_a_reminder_once(smain, api, monkeypatch):
    calls = _services(monkeypatch, api)
    launches = _load_launches(smain, api)
    smain._settings["lead_minutes"] = 10
    smain.toggle_reminder(launches[0])                 # launch at 13:30 UTC, 20:30 WIB
    del smain.spoken[:]
    smain.advance((13 * 60 + 19 - (12 * 60 + 27)) * 60)   # 13:19 UTC
    smain._on_minute_tick()
    assert smain.spoken == [] and smain.sounds == []
    smain.advance(60)
    smain._on_minute_tick()
    assert smain.spoken == ["Rocket launch in 10 minutes: Long March 8A, Unknown Payload, "
                            "at 20:30, from Wenchang."]
    assert smain.sounds == ["info.wav"]
    for _ in range(12):
        smain.advance(60)
        smain._on_minute_tick()
    assert len(smain.spoken) == 1 and len(smain.sounds) == 1
    # Launch times are refreshed at most hourly while reminders are pending.
    assert len(calls) == 1


def test_minute_tick_is_idle_without_reminders(smain, api, monkeypatch):
    calls = _services(monkeypatch, api)
    _load_launches(smain, api)
    for _ in range(5 * 60):
        smain.advance(60)
        smain._on_minute_tick()
    smain._on_app_startup()
    assert calls == [] and smain.spoken == []


def _tick_minutes(smain, minutes):
    for _ in range(minutes):
        smain.advance(60)
        smain._on_minute_tick()


def test_minute_tick_keeps_reminded_launch_times_current(smain, api, monkeypatch):
    # Hariku left open for hours: the list behind a reminder is refreshed
    # hourly, on a worker thread, and the reminder follows a new time.
    calls = _services(monkeypatch, api)
    workers = []
    run_inline = smain._start_thread
    monkeypatch.setattr(smain, "_start_thread",
                        lambda target, *args: workers.append(target.__name__) or run_inline(target, *args))
    launches = _load_launches(smain, api)
    smain.toggle_reminder(launches[1])            # tomorrow: nothing is announced today
    _tick_minutes(smain, 59)
    assert calls == []
    _tick_minutes(smain, 1)
    assert len(calls) == 1 and workers == ["_launch_worker"]
    _tick_minutes(smain, 120)
    assert len(calls) == 3 and workers == ["_launch_worker"] * 3
    # The launch was moved; the next refresh brings the new time.
    moved = copy.deepcopy(LAUNCHES_JSON)
    moved["results"][1]["net"] = "2026-09-25T08:45:00Z"
    monkeypatch.setattr(api, "fetch_json", lambda url: calls.append(url) or copy.deepcopy(moved))
    _tick_minutes(smain, 60)
    assert len(calls) == 4
    assert smain._launch_index[launches[1]["id"]]["net"] == "2026-09-25T08:45:00Z"
    _tick_minutes(smain, 1)                       # the next tick moves the reminder too
    assert smain._reminders[0]["net"] == "2026-09-25T08:45:00Z"
    assert len(calls) == 4
    assert smain.spoken[1:] == []                 # only "You'll be reminded..." so far


@pytest.mark.parametrize("error, retry_after, minutes", [
    ("rate_limited", 1800, [60, 90, 120, 150, 180]),      # the wait the service asked for
    ("offline", None, [60, 65, 75, 95, 135]),             # 5, 10, 20, 40 minutes
])
def test_minute_tick_respects_the_back_off(smain, api, monkeypatch, error, retry_after, minutes):
    attempts = []

    def failing(url):
        attempts.append(round((smain._wall() - NOW.timestamp()) / 60))
        raise api.SpaceError(error, "test", retry_after)

    monkeypatch.setattr(api, "fetch_json", failing)
    launches = _load_launches(smain, api)
    smain.toggle_reminder(launches[1])
    _tick_minutes(smain, 180)
    assert attempts == minutes
    assert len(smain._launch_state["launches"]) == 2   # the saved list is kept meanwhile


def test_sun_and_moon_action(smain, api):
    smain.speak_sun_moon()
    assert smain.spoken[-1].startswith("Jakarta, Wednesday 23 September. Sunrise at 05:42")


def test_briefing_uses_no_network(smain, api, monkeypatch):
    calls = _services(monkeypatch, api)
    lines = []
    smain._on_briefing_collect(lines)
    assert lines == ["Sunset at 17:48; moon phase: Waxing gibbous, 89 percent illuminated."]
    _load_launches(smain, api)
    lines = []
    smain._on_briefing_collect(lines)
    assert lines[0].endswith("Rocket launch today at 20:30: Long March 8A, Unknown Payload.")
    # A day-old list is too old to trust for today's launches.
    smain._launch_state["fetched_at"] = NOW.timestamp() - 25 * 3600
    lines = []
    smain._on_briefing_collect(lines)
    assert "Rocket" not in lines[0]
    assert calls == []


def test_register_and_teardown(smain, fresh_event_bus, monkeypatch, tmp_data_dir):
    import core.api
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *args, **kwargs: panels.append(args))
    # Corrupt files on disk must not stop the extension from loading.
    for key in (smain.DATA_KEY, smain.LAUNCH_KEY, smain.REMINDER_KEY):
        with open(core.api.get_data_path(key), "w", encoding="utf-8") as f:
            f.write("{not json")

    smain.register(fresh_event_bus)
    assert smain._settings == {"location": None, "lead_minutes": 30}
    assert smain._reminders == [] and smain._launch_state["launches"] == []
    for event_name, handler in smain._SUBSCRIPTIONS:
        assert handler in fresh_event_bus._listeners[event_name]
    by_name = {args[1]: (args, kwargs) for args, kwargs in actions}
    assert set(by_name) == {"where_is_iss", "show_launches", "sun_and_moon"}
    assert all(args[0] == "Space" for args, _kwargs in by_name.values())
    iss_args, iss_kwargs = by_name["where_is_iss"]
    assert iss_args[3] == ord("A") and iss_args[4] is False and iss_kwargs == {}
    assert by_name["show_launches"][0][3] is None and by_name["sun_and_moon"][0][3] is None
    assert len(panels) == 1 and panels[0][0] == "Space"

    smain.teardown()
    for event_name, handler in smain._SUBSCRIPTIONS:
        assert handler not in fresh_event_bus._listeners.get(event_name, [])
    assert not smain._active
