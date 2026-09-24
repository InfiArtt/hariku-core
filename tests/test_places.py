# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for core.places (core 2.8): the places store and its checks, the
# migration from Flight Radar's home or the Weather city, rounding, distance
# and bearing, time zones, which place an extension uses, and the Places
# page's logic (with wx mocked, see conftest.py). Everything runs in a
# temporary data folder; nothing touches the network.

import ast
import datetime
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BATAM_HOME = {"name": "Home", "lat": 1.130112, "lon": 104.052871,
              "label": "Jalan Raja Ali Haji, Batam, Kepulauan Riau, Indonesia",
              "timezone": None, "source": "address", "city": "Batam",
              "region": "Kepulauan Riau", "country": "Indonesia"}
OFFICE = {"name": "Office", "lat": 1.1452, "lon": 104.0132, "label": "", "timezone": None,
          "source": "coordinates"}
MUM = {"name": "Mum's house", "lat": -5.1477, "lon": 119.4327,
       "label": "Makassar, South Sulawesi, Indonesia", "timezone": "Asia/Makassar",
       "source": "city", "city": "Makassar", "region": "South Sulawesi",
       "country": "Indonesia"}


@pytest.fixture
def places(tmp_data_dir, monkeypatch):
    import core.places
    from core import i18n
    had_core, old_core = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    monkeypatch.setattr(i18n, "_current_language", "en")
    yield core.places
    if had_core:
        i18n._language_cache["core"] = old_core
    else:
        i18n._language_cache.pop("core", None)


@pytest.fixture
def events(places, monkeypatch):
    from core.events import bus
    seen = []
    handler = lambda *args, **kwargs: seen.append((args, kwargs))  # noqa: E731
    bus.subscribe(places.EVENT, handler)
    yield seen
    bus.unsubscribe(places.EVENT, handler)


def _saved(places):
    import core.api
    return core.api.load_data(places.DATA_KEY)


# ------------------------------------------------------------
# The store
# ------------------------------------------------------------

def test_no_places_at_first(places):
    assert places.get_places() == [] and places.get_main() is None
    assert places.get_main_id() is None and places.get_place("abc") is None
    assert not os.path.exists(os.path.join(places.core.api.DATA_DIR, "Places.json"))


def test_set_places_saves_checks_and_announces(places, events):
    saved = places.set_places([BATAM_HOME, OFFICE, MUM])
    assert [p["name"] for p in saved] == ["Home", "Office", "Mum's house"]
    assert all(re.match(r"^[a-z0-9]{8}$", p["id"]) for p in saved)
    assert len({p["id"] for p in saved}) == 3
    # Without a main id, the first place is the main one.
    assert places.get_main()["name"] == "Home"
    assert events == [((), {})]
    stored = _saved(places)
    assert stored["version"] == 1 and stored["migrated"] is True
    assert stored["main"] == saved[0]["id"]
    assert stored["places"][2] == dict(MUM, id=saved[2]["id"])
    # Optional parts come back empty rather than missing.
    assert stored["places"][1] == dict(OFFICE, id=saved[1]["id"], city="", region="",
                                       country="")
    assert places.get_place(saved[2]["id"])["timezone"] == "Asia/Makassar"


def test_the_main_place_can_be_any_of_them(places):
    saved = places.set_places([BATAM_HOME, OFFICE])
    places.set_places(saved, saved[1]["id"])
    assert places.get_main()["name"] == "Office"
    # An unknown main id falls back to the first place.
    places.set_places(saved, "zzzzzzzz")
    assert places.get_main()["name"] == "Home"
    places.set_places([])
    assert places.get_main() is None and _saved(places)["main"] is None


def test_ids_are_kept_and_repaired(places):
    saved = places.set_places([dict(BATAM_HOME, id="home1"), dict(OFFICE, id="home1"),
                               dict(MUM, id="Not An Id!")])
    assert saved[0]["id"] == "home1"
    assert saved[1]["id"] != "home1" and saved[2]["id"] != "Not An Id!"
    assert len({p["id"] for p in saved}) == 3


def test_returned_places_are_copies(places):
    places.set_places([BATAM_HOME])
    places.get_places()[0]["name"] = "Changed"
    places.get_main()["name"] = "Changed"
    assert places.get_main()["name"] == "Home"


@pytest.mark.parametrize("name, code", [
    ("", "name_empty"), ("   ", "name_empty"), (None, "name_empty"), (12, "name_empty"),
    ("x" * 41, "name_too_long"), ("home", "name_duplicate"), (" HOME ", "name_duplicate"),
])
def test_names_are_checked(places, name, code):
    with pytest.raises(places.PlaceError) as info:
        places.set_places([BATAM_HOME, dict(OFFICE, name=name)])
    assert (info.value.code, info.value.field, info.value.index) == (code, "name", 1)
    assert str(info.value)   # a message for the user, never empty


def test_names_are_tidied(places):
    saved = places.set_places([dict(BATAM_HOME, name="  Rumah \n Mama  "), dict(OFFICE, name="x" * 40)])
    assert saved[0]["name"] == "Rumah Mama" and len(saved[1]["name"]) == 40
    assert places.check_name("Kantor", taken=["Rumah"]) == "Kantor"


@pytest.mark.parametrize("lat, lon, code", [
    (None, 104.0, "no_point"), ("north", 104.0, "no_point"), (True, 104.0, "no_point"),
    (float("nan"), 104.0, "no_point"), (91, 104.0, "out_of_range"), (-90.5, 0, "out_of_range"),
    (1.0, 180.01, "out_of_range"), (0, 0, "zero"),
])
def test_points_are_checked(places, lat, lon, code):
    with pytest.raises(places.PlaceError) as info:
        places.set_places([dict(BATAM_HOME, lat=lat, lon=lon)])
    assert (info.value.code, info.value.field, info.value.index) == (code, "point", 0)


def test_edges_of_the_map_are_places(places):
    saved = places.set_places([dict(BATAM_HOME, lat=90, lon=180), dict(OFFICE, lat=-90, lon=-180)])
    assert (saved[0]["lat"], saved[1]["lon"]) == (90.0, -180.0)


def test_at_most_fifty_places(places):
    many = [dict(OFFICE, name=f"Place {i}") for i in range(places.MAX_PLACES + 1)]
    with pytest.raises(places.PlaceError) as info:
        places.set_places(many)
    assert info.value.code == "too_many"
    assert len(places.set_places(many[:-1])) == places.MAX_PLACES


def test_other_fields_are_cleaned(places):
    saved = places.set_places([dict(BATAM_HOME, label="  A\nlabel  " + "x" * 400,
                                    timezone="../../evil", source="satellite",
                                    city=["Batam"], country=None)])[0]
    assert saved["label"].startswith("A label") and len(saved["label"]) == 300
    assert saved["timezone"] is None and saved["source"] == "coordinates"
    assert saved["city"] == "" and saved["country"] == ""


def test_a_broken_file_is_repaired_when_read(places):
    import core.api
    core.api.save_data("Places", {"places": [
        dict(BATAM_HOME, id="aaaa1111"), {"name": "No point"}, "junk",
        dict(OFFICE, id="bbbb2222", name="home"),          # a duplicate name
        dict(MUM, id="cccc3333")], "main": "gone"})
    assert [p["name"] for p in places.get_places()] == ["Home", "Mum's house"]
    assert places.get_main_id() == "aaaa1111"
    core.api.save_data("Places", "not a dict")
    assert places.get_places() == []
    # A corrupt file: core.api falls back to the last good copy (.bak).
    core.api.save_data("Places", {"places": [dict(OFFICE, id="bbbb2222")]})
    with open(core.api.get_data_path("Places"), "w", encoding="utf-8") as f:
        f.write("{broken json")
    assert [p["name"] for p in places.get_places()] == []   # the .bak held "not a dict"
    os.remove(core.api.get_data_path("Places") + ".bak")
    with open(core.api.get_data_path("Places"), "w", encoding="utf-8") as f:
        f.write("{still broken")
    assert places.get_places() == []


def test_the_store_is_read_again_when_the_file_changes(places):
    import core.api
    places.set_places([BATAM_HOME])
    assert places.get_main()["name"] == "Home"
    core.api.save_data("Places", {"places": [dict(OFFICE, id="bbbb2222")], "main": "bbbb2222",
                                  "migrated": True})
    assert places.get_main()["name"] == "Office"


def test_reading_is_cheap(places, monkeypatch):
    import core.api
    places.set_places([BATAM_HOME])
    places.get_main()

    def no_reading(name):
        raise AssertionError("the unchanged file was read again")

    monkeypatch.setattr(core.api, "load_data", no_reading)
    for _ in range(3):
        assert places.get_main()["name"] == "Home"


def test_place_from_a_search_result(places):
    import core.place_search as search
    found = search.candidate(-5.1477, 119.4327, "city", name="Makassar",
                             label="Makassar, South Sulawesi, Indonesia",
                             timezone="Asia/Makassar", city="Makassar",
                             region="South Sulawesi", country="Indonesia")
    place = places.place_from_candidate(found, "Mum's house", place_id="mum12345")
    assert place == dict(MUM, id="mum12345")
    with pytest.raises(places.PlaceError):
        places.place_from_candidate(found, "")


# ------------------------------------------------------------
# Migration
# ------------------------------------------------------------

FR_HOME = {"name": "My flat", "admin1": "", "country": "", "latitude": 1.130112,
           "longitude": 104.052871, "kind": "address",
           "detail": "Jalan Raja Ali Haji, Batam, Kepulauan Riau, Indonesia"}
WEATHER_CITY = {"name": "Batam", "admin1": "Riau Islands", "country": "Indonesia",
                "latitude": 1.14937, "longitude": 104.02491, "timezone": "Asia/Jakarta"}


def _data(**keys):
    import core.api
    for key, value in keys.items():
        core.api.save_data(key, value)


def test_migration_takes_flight_radars_exact_home_first(places):
    _data(FlightRadar={"location": FR_HOME, "radius_km": 25},
          Weather={"location": WEATHER_CITY, "units": "metric"})
    home = places.migrate()
    assert home["name"] == "Home" and home["source"] == "address"
    assert (home["lat"], home["lon"]) == (1.130112, 104.052871)
    assert home["label"] == FR_HOME["detail"] and home["timezone"] is None
    assert places.get_main() == home and places.get_places() == [home]
    # The extensions' own data is untouched.
    import core.api
    assert core.api.load_data("FlightRadar")["location"] == FR_HOME
    assert core.api.load_data("Weather")["location"] == WEATHER_CITY


def test_migration_takes_pasted_coordinates(places):
    _data(FlightRadar={"location": dict(FR_HOME, kind="coordinates", detail="")})
    home = places.migrate()
    assert home["source"] == "coordinates" and home["label"] == ""


def test_migration_skips_flight_radars_city_and_uses_the_weather_city(places):
    fr_city = {"name": "Jakarta", "admin1": "Jakarta", "country": "Indonesia",
               "latitude": -6.2, "longitude": 106.8}
    _data(FlightRadar={"location": fr_city}, Weather={"location": WEATHER_CITY})
    home = places.migrate()
    assert home == dict(home, name="Home", lat=1.14937, lon=104.02491, source="city",
                        label="Batam, Riau Islands, Indonesia", timezone="Asia/Jakarta",
                        city="Batam", region="Riau Islands", country="Indonesia")


def test_migration_names_home_in_the_users_language(places, monkeypatch):
    from core import i18n
    monkeypatch.setattr(i18n, "_current_language", "id")
    _data(Weather={"location": WEATHER_CITY})
    assert places.migrate()["name"] == "Rumah"


def test_migration_runs_once(places, events):
    _data(Weather={"location": WEATHER_CITY})
    assert places.migrate()["name"] == "Home"
    places.set_places([])                  # the user removes every place
    assert places.migrate() is None        # and Home doesn't come back
    assert places.get_places() == []
    assert events == [((), {})]            # only set_places announced a change


def test_migration_without_anything_to_take(places):
    _data(FlightRadar={"location": {"name": "x", "latitude": "?", "longitude": 1,
                                    "kind": "address"}},
          Weather={"location": None})
    assert places.migrate() is None
    assert _saved(places) == {"version": 1, "places": [], "main": None, "migrated": True}
    _data(Weather={"location": WEATHER_CITY})
    assert places.migrate() is None        # already done


def test_migration_leaves_existing_places_alone(places):
    places.set_places([OFFICE])
    _data(Weather={"location": WEATHER_CITY})
    assert places.migrate() is None
    assert [p["name"] for p in places.get_places()] == ["Office"]


def test_startup_migrates_before_the_extensions_load():
    with open(os.path.join(ROOT, "hariku.py"), encoding="utf-8") as f:
        source = f.read()
    assert source.index("core.places.migrate()") < source.index("load_all_extensions()\n")
    assert source.index("core.i18n.init()") < source.index("core.places.migrate()")


# ------------------------------------------------------------
# Rounding, distance, bearing, time zones, words
# ------------------------------------------------------------

def test_rounding(places):
    assert places.rounded(BATAM_HOME) == (1.13, 104.05)
    assert places.rounded(BATAM_HOME, 3) == (1.13, 104.053)
    assert places.rounded({"latitude": -6.208812, "longitude": 106.845613}) == (-6.21, 106.85)
    assert places.rounded((-6.205, 106.8449)) == (round(-6.205, 2), 106.84)
    import random
    rng = random.Random(3)
    for _ in range(300):
        point = (rng.uniform(-80, 80), rng.uniform(-179, 179))
        # Two decimals move a point by at most about 0.8 km.
        assert places.distance_km(point, places.rounded(point)) < 0.8


def test_distance_and_bearing(places):
    assert places.distance_km((0, 100), (0, 101)) == pytest.approx(111.19, abs=0.01)
    assert places.bearing((0, 100), (0, 101)) == pytest.approx(90)
    assert places.bearing((-7, 110), (-6, 110)) == pytest.approx(0)
    assert places.bearing((-6, 110), (-7, 110)) == pytest.approx(180)
    assert places.bearing((0, 101), (0, 100)) == pytest.approx(270)
    # Soekarno-Hatta to Halim, both ways.
    cgk, halim = (-6.1256, 106.6559), (-6.2666, 106.891)
    assert places.distance_km(cgk, halim) == pytest.approx(30.3, abs=0.2)
    assert places.bearing(cgk, halim) == pytest.approx(121.3, abs=0.5)
    assert places.bearing(halim, cgk) == pytest.approx(301.2, abs=0.5)
    # Places, location dicts and pairs all work.
    assert places.distance_km(BATAM_HOME, {"latitude": 1.130112, "longitude": 104.052871}) == 0
    assert places.distance_km(BATAM_HOME, MUM) == pytest.approx(1845, abs=10)
    assert places.same_point(BATAM_HOME, (1.13012, 104.05287))
    assert not places.same_point(BATAM_HOME, OFFICE) and not places.same_point(None, OFFICE)


def test_time_zones(places):
    import zoneinfo
    assert places.timezone_for(MUM) == zoneinfo.ZoneInfo("Asia/Makassar")
    now = datetime.datetime(2026, 9, 24, 12, 0, tzinfo=datetime.timezone.utc)
    assert now.astimezone(places.timezone_for(MUM)).hour == 20
    # Without one (an address, pasted coordinates, an unknown name): the computer's own.
    local = datetime.datetime.now().astimezone().utcoffset()
    for place in (BATAM_HOME, OFFICE, dict(MUM, timezone="Mars/Olympus"), None, {}):
        zone = places.timezone_for(place)
        assert datetime.datetime.now(zone).utcoffset() == local


def test_words(places):
    assert places.point_text(1.130112, 104.052871) == "1.1301, 104.0529"
    assert places.where_text(OFFICE) == "1.1452, 104.0132"
    assert places.where_text(MUM) == "Makassar, South Sulawesi, Indonesia (-5.1477, 119.4327)"
    assert places.describe(dict(OFFICE, name="Kantor")) == "Kantor: 1.1452, 104.0132"


# ------------------------------------------------------------
# Which place an extension uses
# ------------------------------------------------------------

def test_normalize_choice(places):
    for value in ("main", "own", "abc12345"):
        assert places.normalize_choice(value) == value
    for value in (None, "", "Main", 5, "../x", "a" * 33, True):
        assert places.normalize_choice(value) is None


def test_initial_choice(places):
    city = {"name": "Batam", "latitude": 1.14937, "longitude": 104.02491}
    # No places: an extension with its own place keeps it; one without follows main.
    assert places.initial_choice(None) == "main"
    assert places.initial_choice(city) == "own"
    places.set_places([dict(BATAM_HOME, lat=1.14937, lon=104.02491)])
    # Its place is the main place: it follows the main place from now on.
    assert places.initial_choice(city) == "main"
    assert places.initial_choice(dict(city, latitude=-6.2)) == "own"


def test_location_for(places):
    saved = places.set_places([BATAM_HOME, MUM])
    own = {"name": "Pantai Nongsa", "latitude": 1.2, "longitude": 104.1}
    home = places.location_for("main", own)
    assert home == {"name": "Home", "admin1": "", "admin2": "", "country": "",
                    "latitude": 1.130112, "longitude": 104.052871, "timezone": "",
                    "kind": "address", "detail": BATAM_HOME["label"],
                    "place_id": saved[0]["id"], "city": "Batam", "label": BATAM_HOME["label"]}
    assert places.location_for(saved[1]["id"], own)["timezone"] == "Asia/Makassar"
    assert places.location_for("own", own) == own
    assert places.location_for("own", None) is None
    # A removed place: the main place.
    assert places.location_for("gone1234", own)["name"] == "Home"
    # Not decided yet: its own place unless that is the main place.
    assert places.location_for(None, own) == own
    assert places.location_for(None, None)["name"] == "Home"
    assert places.location_for("junk!", None)["name"] == "Home"
    coords = places.location_dict(dict(OFFICE, id="office12"))
    assert coords["kind"] == "coordinates" and coords["detail"] == "" and coords["city"] == ""
    places.set_places([])
    assert places.location_for("main", own) is None


def test_resolve(places):
    saved = places.set_places([BATAM_HOME, MUM], main_id=None)
    assert places.resolve("main")["name"] == "Home"
    assert places.resolve(saved[1]["id"])["name"] == "Mum's house"
    assert places.resolve("own") is None
    assert places.resolve("gone1234")["name"] == "Home"


def test_choice_entries(places):
    assert places.choice_entries() == [
        ("main", "The main place (none yet: add one in Preferences, Places)"),
        ("own", "Its own place…")]
    saved = places.set_places([BATAM_HOME, MUM])
    places.set_places(saved, saved[1]["id"])
    assert places.choice_entries() == [("main", "The main place (Mum's house)"),
                                       (saved[0]["id"], "Home"), (saved[1]["id"], "Mum's house"),
                                       ("own", "Its own place…")]
    assert places.choice_entries(own=False)[-1] == (saved[1]["id"], "Mum's house")


def test_choice_entries_in_indonesian(places, monkeypatch):
    from core import i18n
    monkeypatch.setattr(i18n, "_current_language", "id")
    places.set_places([dict(BATAM_HOME, name="Rumah")])
    assert places.choice_entries()[0][1] == "Tempat utama (Rumah)"
    assert places.choice_entries()[-1][1] == "Tempat sendiri…"


# ------------------------------------------------------------
# The Places page (wx mocked)
# ------------------------------------------------------------

@pytest.fixture
def page(places, monkeypatch):
    from unittest.mock import MagicMock
    import core.places_ui
    spoken = []
    monkeypatch.setattr(core.places_ui, "_speak", lambda text, interrupt=False: spoken.append(text))
    monkeypatch.setattr(core.places_ui, "_announce", spoken.append)

    def make():
        # The page's logic without its window (the window check in CI builds it).
        class Page:
            pass

        for name, value in vars(core.places_ui.PlacesPanel).items():
            if callable(value) and name != "__init__":
                setattr(Page, name, value)
        panel = Page()
        panel.list_places = MagicMock()
        panel.txt_main = MagicMock()
        panel.btn_add = MagicMock()
        panel._load()
        panel.spoken = spoken
        panel.answers = []
        panel.selected = 0
        panel.confirm = True
        panel._ask = lambda title, place=None, taken=(): panel.answers.pop(0)
        panel._confirm = lambda message: spoken.append(message) or panel.confirm
        panel.selected_index = lambda: panel.selected
        return panel

    return make


def _new(places, raw):
    return places.check_place(raw)


def test_page_add_edit_make_main_remove(page, places, events):
    panel = page()
    assert panel.places() == [] and panel.main_id() is None and not panel.is_changed()
    panel.answers = [_new(places, BATAM_HOME), _new(places, MUM)]
    panel.on_add()
    assert panel.spoken[-1] == "Added Home. It is your main place."
    panel.on_add()
    assert panel.spoken[-1] == "Added Mum's house."
    home, mum = panel.places()
    assert panel.main_id() == home["id"] and panel.is_changed()

    panel.selected = 1
    panel.on_make_main()
    assert panel.spoken[-1] == "Mum's house is now the main place." and panel.main_id() == mum["id"]
    panel.on_make_main()
    assert panel.spoken[-1] == "Mum's house is already the main place."

    panel.answers = [_new(places, dict(MUM, name="Rumah Mama"))]
    panel.on_edit()
    assert panel.places()[1]["id"] == mum["id"] and panel.places()[1]["name"] == "Rumah Mama"
    assert panel.spoken[-1] == "Changed Rumah Mama."

    panel.answers = [None]                  # cancelled: nothing changes
    panel.on_edit()
    assert panel.places()[1]["name"] == "Rumah Mama"

    # Nothing is saved before OK or Apply.
    assert places.get_places() == [] and events == []
    panel.ApplyChanges()
    assert [p["name"] for p in places.get_places()] == ["Home", "Rumah Mama"]
    assert places.get_main()["name"] == "Rumah Mama" and len(events) == 1
    panel.ApplyChanges()                    # unchanged: not saved or announced again
    assert len(events) == 1

    # Removing the main place (after the confirmation) makes the first one main.
    panel.confirm = False
    panel.on_remove()
    assert panel.spoken[-1] == "Remove Rumah Mama? Extensions that use it will use the main place instead."
    assert len(panel.places()) == 2
    panel.confirm = True
    panel.on_remove()
    assert panel.spoken[-1] == "Removed Rumah Mama. Home is now the main place."
    assert [p["name"] for p in panel.places()] == ["Home"] and panel.main_id() == home["id"]
    panel.selected = 0
    panel.on_remove()
    assert panel.places() == [] and panel.main_id() is None
    panel.ApplyChanges()
    assert places.get_places() == [] and len(events) == 2


def test_page_without_a_selection(page):
    panel = page()
    panel.selected = -1
    for action in (panel.on_edit, panel.on_remove, panel.on_make_main):
        action()
        assert panel.spoken[-1] == "Select a place in the list first."


def test_page_starts_with_the_saved_places(page, places):
    saved = places.set_places([BATAM_HOME, MUM], None)
    places.set_places(saved, saved[1]["id"])
    panel = page()
    assert [p["name"] for p in panel.places()] == ["Home", "Mum's house"]
    assert panel.main_id() == saved[1]["id"] and not panel.is_changed()
    assert panel._row_name(panel.places()[1]) == "Mum's house (main)"
    assert panel._row_name(panel.places()[0]) == "Home"


def test_page_asks_with_the_other_names_taken(page, places):
    panel = page()
    asked = []
    panel._ask = lambda title, place=None, taken=(): asked.append((title, place, list(taken)))
    panel.answers = []
    places_list = [_new(places, BATAM_HOME), _new(places, MUM)]
    panel._places = places_list
    panel.on_add()
    panel.selected = 1
    panel.on_edit()
    assert asked[0] == ("Add Place", None, ["Home", "Mum's house"])
    assert asked[1][0] == "Edit Place" and asked[1][1]["name"] == "Mum's house"
    assert asked[1][2] == ["Home"]


# ------------------------------------------------------------
# Workers and messages
# ------------------------------------------------------------

def test_workers_hand_back_results_and_errors(places, monkeypatch):
    import core.place_search as search
    import core.places_ui as ui
    got = []
    done = lambda *args: got.append(args)  # noqa: E731
    monkeypatch.setattr(search, "search_addresses",
                        lambda query, language: [search.candidate(1, 104, "address", label="A")])
    ui._address_worker(done, 3, "Jalan A", "en")
    assert got[-1][:2] == (3, "Jalan A") and got[-1][2][0]["label"] == "A" and got[-1][3] is None

    def busy(query, language):
        raise search.LocationError("address_busy")

    monkeypatch.setattr(search, "search_addresses", busy)
    ui._address_worker(done, 4, "Jalan A", "en")
    assert got[-1] == (4, "Jalan A", [], "address_busy")

    def crash(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(search, "search_cities", crash)
    ui._city_worker(done, 5, "Batam", "en")
    assert got[-1] == (5, "Batam", [], "city_failed")
    monkeypatch.setattr(search, "resolve_short_link", lambda url: (1.13, 104.05))
    ui._link_worker(done, 6, "https://maps.app.goo.gl/x")
    assert got[-1] == (6, (1.13, 104.05), None)
    monkeypatch.setattr(search, "resolve_short_link", crash)
    ui._link_worker(done, 7, "https://maps.app.goo.gl/x")
    assert got[-1] == (7, None, "link_failed")


def test_error_messages(places):
    import core.places_ui as ui
    kinds = ("empty", "not_found", "out_of_range", "zero", "link_no_coordinates", "link_failed",
             "address_failed", "address_busy", "city_failed")
    texts = {ui.error_text(kind) for kind in kinds}
    assert len(texts) == len(kinds) and not any(t.startswith("places_") for t in texts)
    assert ui.error_text("something else") == ui.error_text("not_found")
    assert ui.candidate_where({"latitude": 1.13, "longitude": 104.05, "label": ""}) == \
        "1.1300, 104.0500"


# ------------------------------------------------------------
# Source checks
# ------------------------------------------------------------

def _literal_keys(path, prefixes):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value.startswith(prefixes)):
            keys.add(node.args[0].value)
    return keys


def test_messages_exist_in_both_languages():
    used = set()
    for name in ("places.py", "places_ui.py", "core_panels.py"):
        used |= _literal_keys(os.path.join(ROOT, "core", name), ("places_", "prefs_"))
    with open(os.path.join(ROOT, "core", "places.py"), encoding="utf-8") as f:
        used |= {"places_err_" + code
                 for code in re.findall(r'PlaceError\("(\w+)"', f.read())}
    used |= {"places_find_err_" + kind for kind in (
        "empty", "not_found", "out_of_range", "zero", "link_no_coordinates", "link_failed",
        "address_failed", "address_busy", "city_failed")}
    assert "places_err_name_duplicate" in used and "places_lbl_choice" in used
    messages = {}
    for code in ("en", "id"):
        with open(os.path.join(ROOT, "locales", f"{code}.json"), encoding="utf-8") as f:
            messages[code] = json.load(f)["messages"]
        missing = sorted(k for k in used if k not in messages[code])
        assert not missing, f"locales/{code}.json lacks {missing}"
    place_keys = {k for k in messages["en"] if k.startswith("places_")}
    assert place_keys == {k for k in messages["id"] if k.startswith("places_")}
    # The core speaks Indonesian with "Anda", never "kamu".
    for key in place_keys:
        assert not re.search(r"\b(kamu|-mu)\b", messages["id"][key], re.I), key


def test_every_label_comes_before_its_control():
    # The page and the dialog build each input through a helper that makes the
    # label first (the window check in CI checks the page too).
    with open(os.path.join(ROOT, "core", "places_ui.py"), encoding="utf-8") as f:
        source = f.read()
    for ctrl in ("wx.TextCtrl(", "wx.ListCtrl(", "wx.Choice("):
        for match in re.finditer(re.escape(ctrl), source):
            before = source[max(0, match.start() - 300):match.start()]
            assert "lambda" in before or "make" in before or "StaticText" in before, (
                ctrl, source[match.start() - 120:match.start() + 40])
    for forbidden in ("FilePickerCtrl", "DirPickerCtrl", "SpinCtrlDouble"):
        assert forbidden not in source


def test_the_core_imports_what_extensions_need():
    # Nuitka only compiles modules the core imports.
    with open(os.path.join(ROOT, "core", "core_panels.py"), encoding="utf-8") as f:
        panels = f.read()
    assert "import core.places_ui" in panels
    with open(os.path.join(ROOT, "core", "places_ui.py"), encoding="utf-8") as f:
        ui = f.read()
    assert "import core.place_search" in ui and "import core.places" in ui
    with open(os.path.join(ROOT, "hariku.py"), encoding="utf-8") as f:
        assert "import core.places\n" in f.read()


def test_core_version_is_2_8():
    from core.constants import CORE_VERSION
    assert CORE_VERSION == "2.8.0"
