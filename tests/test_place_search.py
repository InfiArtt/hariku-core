# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for core.place_search (core 2.8): pasted coordinates and map links,
# Google Maps short links, the Nominatim address search (pacing, memory, the
# User-Agent) and the Open-Meteo city search. Most of them moved here from
# tests/test_flight_radar.py with the code (flight_radar_location.py).
# Nothing touches the network: the fetch functions are replaced.

import urllib.error

import pytest


@pytest.fixture(scope="module")
def loc():
    import core.place_search
    return core.place_search


class _Clock:
    def __init__(self, start=1000.0):
        self.now = start
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class _Response:
    def __init__(self, body):
        self._body = body

    def read(self, size=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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
    assert [p["label"] for p in places] == [NOMINATIM_JSON[0]["display_name"],
                                             "Jalan Merdeka, Bandung"]
    assert places[0]["source"] == "address" and places[0]["latitude"] == -6.1753924
    assert loc.parse_addresses({"error": "x"}) == []


def test_address_search_is_paced_and_cached(loc):
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


def test_address_search_errors_are_not_cached(loc):
    clock = _Clock()
    answers = [loc.FetchError("rate_limited", status=429), loc.FetchError("offline"),
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


def test_address_search_identifies_hariku(loc, monkeypatch):
    seen = {}

    def fake_fetch_json(url, timeout=None, user_agent=None):
        seen.update(url=url, agent=user_agent)
        return []

    monkeypatch.setattr(loc, "fetch_json", fake_fetch_json)
    loc.AddressSearch().search("Monas", "en")
    assert seen["agent"] == loc.NOMINATIM_USER_AGENT
    assert seen["agent"].startswith("HarikuV2/")
    assert "github.com/InfiArtt/hariku-core" in seen["agent"]


# ------------------------------------------------------------
# New in core 2.8
# ------------------------------------------------------------

def test_address_results_carry_the_city_region_and_country(loc):
    found = loc.parse_addresses([
        {"lat": "1.1301", "lon": "104.0529",
         "display_name": "Jalan Raja Ali Haji, Sungai Jodoh, Batam, Kepulauan Riau, Indonesia",
         "address": {"road": "Jalan Raja Ali Haji", "suburb": "Sungai Jodoh", "city": "Batam",
                     "state": "Kepulauan Riau", "country": "Indonesia"}},
        {"lat": "-7.0", "lon": "110.4", "display_name": "Desa Sukamaju, Jawa Tengah",
         "address": {"village": "Sukamaju", "state": "Jawa Tengah"}},
        {"lat": "95", "lon": "1", "display_name": "Off the map"},
    ])
    assert found == [
        {"name": "Jalan Raja Ali Haji",
         "label": "Jalan Raja Ali Haji, Sungai Jodoh, Batam, Kepulauan Riau, Indonesia",
         "latitude": 1.1301, "longitude": 104.0529, "timezone": None, "source": "address",
         "city": "Batam", "region": "Kepulauan Riau", "country": "Indonesia"},
        {"name": "Desa Sukamaju", "label": "Desa Sukamaju, Jawa Tengah", "latitude": -7.0,
         "longitude": 110.4, "timezone": None, "source": "address", "city": "Sukamaju",
         "region": "Jawa Tengah", "country": ""},
    ]
    assert "addressdetails=1" in loc.build_address_url("Batam")


GEOCODING_JSON = {"results": [
    {"name": "Batam", "admin1": "Riau Islands", "country": "Indonesia", "latitude": 1.14937,
     "longitude": 104.02491, "timezone": "Asia/Jakarta"},
    {"name": "Batam", "admin1": "Batam", "country": "", "latitude": 1.1, "longitude": 104.0,
     "timezone": "not a zone!"},
    {"name": "Broken", "latitude": "north", "longitude": 1},
    {"name": "", "latitude": 1, "longitude": 1},
]}


def test_city_url_and_results(loc):
    url = loc.build_city_url("  Batam ", "id")
    assert url.startswith("https://geocoding-api.open-meteo.com/v1/search?")
    assert "name=Batam&" in url and "count=10" in url and "language=id" in url
    assert "language=en" in loc.build_city_url("Paris", "fr")
    found = loc.parse_cities(GEOCODING_JSON)
    assert found[0] == {"name": "Batam", "label": "Batam, Riau Islands, Indonesia",
                        "latitude": 1.14937, "longitude": 104.02491, "timezone": "Asia/Jakarta",
                        "source": "city", "city": "Batam", "region": "Riau Islands",
                        "country": "Indonesia"}
    # A repeated part is said once; a zone that isn't one is dropped.
    assert found[1]["label"] == "Batam" and found[1]["timezone"] is None
    assert len(found) == 2
    assert loc.parse_cities(None) == [] and loc.parse_cities({"results": "x"}) == []


def test_city_search_sends_only_the_name_and_maps_failures(loc):
    urls = []

    def fetch(url):
        urls.append(url)
        return GEOCODING_JSON

    assert [c["label"] for c in loc.search_cities("Batam", "en", fetch=fetch)][0] == \
        "Batam, Riau Islands, Indonesia"
    assert urls == [loc.build_city_url("Batam", "en")]

    def broken(url):
        raise loc.FetchError("offline")

    with pytest.raises(loc.LocationError) as info:
        loc.search_cities("Batam", "en", fetch=broken)
    assert info.value.kind == "city_failed"


def test_fetch_json_identifies_hariku_and_maps_failures(loc, monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen.update(agent=req.get_header("User-agent"), timeout=timeout)
        return _Response(b'{"ok": true}')

    monkeypatch.setattr(loc.urllib.request, "urlopen", fake_urlopen)
    assert loc.fetch_json("https://example.invalid/") == {"ok": True}
    assert seen["agent"] == loc.USER_AGENT and seen["timeout"] == loc.TIMEOUT_SECONDS
    assert "github.com/InfiArtt/hariku-core" in loc.USER_AGENT
    assert loc.fetch_json("https://example.invalid/", user_agent="Test/1") == {"ok": True}
    assert seen["agent"] == "Test/1"

    def http_error(code):
        def fail(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
        return fail

    for code, kind in ((429, "rate_limited"), (503, "service")):
        monkeypatch.setattr(loc.urllib.request, "urlopen", http_error(code))
        with pytest.raises(loc.FetchError) as info:
            loc.fetch_json("https://example.invalid/")
        assert (info.value.kind, info.value.status) == (kind, code)

    def offline(req, timeout=None):
        raise OSError("down")

    monkeypatch.setattr(loc.urllib.request, "urlopen", offline)
    with pytest.raises(loc.FetchError) as info:
        loc.fetch_json("https://example.invalid/")
    assert info.value.kind == "offline"
    monkeypatch.setattr(loc.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(b"<html>"))
    with pytest.raises(loc.FetchError) as info:
        loc.fetch_json("https://example.invalid/")
    assert info.value.kind == "bad_response"


@pytest.mark.parametrize("value, expected", [
    ("Asia/Jakarta", "Asia/Jakarta"),
    ("America/Argentina/Buenos_Aires", "America/Argentina/Buenos_Aires"),
    ("UTC", "UTC"), ("Etc/GMT+7", "Etc/GMT+7"), ("", None), (None, None), (7, None),
    ("../../etc/passwd", None), ("Asia/Jakarta; rm", None), ("x" * 70, None),
])
def test_clean_timezone(loc, value, expected):
    assert loc.clean_timezone(value) == expected


def test_one_address_search_for_all_of_hariku(loc):
    # Every caller shares one pacing gate, so two windows can't break the policy.
    assert isinstance(loc._address_search, loc.AddressSearch)
    assert loc._address_search.min_gap >= 1.0


def test_parsing_never_touches_the_network(loc, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("parsing must not touch the network")

    monkeypatch.setattr(loc.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(loc, "_open_without_redirects", forbidden)
    assert loc.parse_location_text("https://www.google.com/maps/@-6.2088,106.8456,15z")[
        "kind"] == "coordinates"
    assert loc.parse_location_text("https://maps.app.goo.gl/AbC")["kind"] == "short_link"
