# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Places (core 2.8): the user's named locations, such as Home, Office or Mum's
house, shared by every extension that needs one. One of them is the main
place, which extensions use unless the user picks another place (or the
extension's own place) on the extension's settings page.

Stored on this computer only, in the "Places" data key (Places.json):
{"version": 1, "places": [place, ...], "main": id, "migrated": true}. A place
is {"id", "name", "lat", "lon", "label" (the address or city the user chose,
"" for pasted coordinates), "timezone" (IANA, or None), "source" ("address",
"city" or "coordinates"), "city", "region", "country"}; the last three are ""
when unknown.

The store is kept in memory and re-read when the file changes, so reading a
place is cheap (placeholder providers may call it). set_places() is the only
writer; it emits "on_places_changed" on the event bus (no arguments).
Nothing here touches the network: core.place_search finds places. Services
should get a place rounded (rounded(), 2 decimals, about 1 km), never the
exact point.
"""

import datetime
import logging
import math
import os
import re
import threading
import uuid

import core.api
from core.events import bus
from core.i18n import get_translator
from core.place_search import candidate, clean_timezone, city_label, to_float

_ = get_translator("core")
logger = logging.getLogger(__name__)

DATA_KEY = "Places"
EVENT = "on_places_changed"
VERSION = 1
MAX_NAME_LENGTH = 40
MAX_LABEL_LENGTH = 300
MAX_TEXT_LENGTH = 100
MAX_PLACES = 50
SOURCES = ("address", "city", "coordinates")
# What an extension stores to say which place it uses.
CHOICE_MAIN = "main"
CHOICE_OWN = "own"
SAME_POINT_DEGREES = 1e-4        # about 11 metres
EARTH_RADIUS_KM = 6371.0
# Where the migration looks for the place the user already had.
FLIGHT_RADAR_KEY = "FlightRadar"
WEATHER_KEY = "Weather"

_ID_RE = re.compile(r"^[a-z0-9]{1,32}$")
_lock = threading.Lock()
_cache = {"stamp": None, "store": None}


class PlaceError(ValueError):
    """A place that can't be saved. `code` says why ("name_empty",
    "name_too_long", "name_duplicate", "no_point", "out_of_range", "zero" or
    "too_many"), `field` which input ("name" or "point") and `index` which
    place in a list, if any. str(error) is a message for the user."""

    def __init__(self, code, field=None, index=None, **details):
        self.code = code
        self.field = field
        self.index = index
        self.details = details
        super().__init__(_("places_err_" + code, max=MAX_NAME_LENGTH, count=MAX_PLACES,
                           **details))


# ------------------------------------------------------------
# Checking
# ------------------------------------------------------------

def _one_line(value, limit):
    return " ".join(str(value or "").split())[:limit] if isinstance(value, (str, int, float)) \
        and not isinstance(value, bool) else ""


def clean_name(name):
    """The name as it would be saved: on one line, spaces collapsed."""
    return " ".join(str(name or "").split()) if isinstance(name, str) else ""


def check_name(name, taken=()):
    """The cleaned name, or PlaceError: 1 to 40 characters, not the same
    (ignoring case) as a name in `taken`."""
    name = clean_name(name)
    if not name:
        raise PlaceError("name_empty", "name")
    if len(name) > MAX_NAME_LENGTH:
        raise PlaceError("name_too_long", "name")
    if name.casefold() in {clean_name(t).casefold() for t in taken}:
        raise PlaceError("name_duplicate", "name", name=name)
    return name


def check_point(latitude, longitude):
    """(latitude, longitude) as floats on the map, not 0, 0. Raises PlaceError."""
    lat, lon = to_float(latitude), to_float(longitude)
    if lat is None or lon is None:
        raise PlaceError("no_point", "point")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise PlaceError("out_of_range", "point")
    if abs(lat) < 1e-9 and abs(lon) < 1e-9:
        raise PlaceError("zero", "point")
    return lat, lon


def new_id(taken=()):
    while True:
        place_id = uuid.uuid4().hex[:8]
        if place_id not in taken:
            return place_id


def check_place(raw, taken_names=(), taken_ids=()):
    """A clean place from `raw` (a place, or a core.place_search candidate
    with "latitude"/"longitude" and a "name"). Keeps a valid id not in
    `taken_ids`, else makes one. Raises PlaceError."""
    if not isinstance(raw, dict):
        raise PlaceError("no_point", "point")
    name = check_name(raw.get("name"), taken_names)
    lat, lon = check_point(raw.get("lat", raw.get("latitude")),
                           raw.get("lon", raw.get("longitude")))
    place_id = raw.get("id")
    if not (isinstance(place_id, str) and _ID_RE.match(place_id)) or place_id in taken_ids:
        place_id = new_id(taken_ids)
    source = raw.get("source")
    return {
        "id": place_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "label": _one_line(raw.get("label"), MAX_LABEL_LENGTH),
        "timezone": clean_timezone(raw.get("timezone")),
        "source": source if source in SOURCES else "coordinates",
        "city": _one_line(raw.get("city"), MAX_TEXT_LENGTH),
        "region": _one_line(raw.get("region"), MAX_TEXT_LENGTH),
        "country": _one_line(raw.get("country"), MAX_TEXT_LENGTH),
    }


def check_places(places, main_id=None):
    """(clean places, main id) for a whole list: names unique, ids unique, at
    most MAX_PLACES; the main id is one of them (the first place otherwise), or
    None for an empty list. Raises PlaceError with `index` set."""
    places = list(places or [])
    if len(places) > MAX_PLACES:
        raise PlaceError("too_many")
    clean, names, ids = [], [], set()
    for index, raw in enumerate(places):
        try:
            place = check_place(raw, names, ids)
        except PlaceError as e:
            e.index = index
            raise
        clean.append(place)
        names.append(place["name"])
        ids.add(place["id"])
    if main_id not in ids:
        main_id = clean[0]["id"] if clean else None
    return clean, main_id


# ------------------------------------------------------------
# The store
# ------------------------------------------------------------

def _empty_store():
    return {"version": VERSION, "places": [], "main": None, "migrated": False}


def _normalize_store(raw):
    """The stored data repaired: broken places (a hand edit) are skipped."""
    store = _empty_store()
    if not isinstance(raw, dict):
        return store
    names, ids = [], set()
    for item in raw.get("places") if isinstance(raw.get("places"), list) else []:
        try:
            place = check_place(item, names, ids)
        except PlaceError:
            continue
        if len(store["places"]) >= MAX_PLACES:
            break
        store["places"].append(place)
        names.append(place["name"])
        ids.add(place["id"])
    main = raw.get("main")
    store["main"] = main if main in ids else (store["places"][0]["id"] if store["places"] else None)
    store["migrated"] = raw.get("migrated") is True or bool(store["places"])
    return store


def _stamp(path):
    try:
        info = os.stat(path)
    except OSError:
        return (path, None, None)
    return (path, info.st_mtime_ns, info.st_size)


def _store():
    """The store, from memory while the file is unchanged."""
    path = core.api.get_data_path(DATA_KEY)
    stamp = _stamp(path)
    with _lock:
        if _cache["store"] is None or _cache["stamp"] != stamp:
            _cache["store"] = (_normalize_store(core.api.load_data(DATA_KEY))
                               if stamp[1] is not None else _empty_store())
            _cache["stamp"] = stamp
        return _cache["store"]


def _save_store(store):
    ok = core.api.save_data(DATA_KEY, store)
    with _lock:
        _cache["store"] = store
        _cache["stamp"] = _stamp(core.api.get_data_path(DATA_KEY))
    return ok


def get_places():
    """The saved places, in the user's order (copies)."""
    return [dict(p) for p in _store()["places"]]


def get_place(place_id):
    """The place with this id (a copy), or None."""
    return next((dict(p) for p in _store()["places"] if p["id"] == place_id), None)


def get_main_id():
    """The main place's id, or None when there are no places."""
    return _store()["main"]


def get_main():
    """The main place (a copy), or None when there are no places."""
    store = _store()
    return next((dict(p) for p in store["places"] if p["id"] == store["main"]), None)


def set_places(places, main_id=None, emit=True):
    """Save the whole list and which place is the main one, then emit
    "on_places_changed". Returns the saved places. Raises PlaceError."""
    clean, main_id = check_places(places, main_id)
    store = {"version": VERSION, "places": clean, "main": main_id, "migrated": True}
    _save_store(store)
    if emit:
        bus.emit(EVENT)
    return [dict(p) for p in clean]


def place_from_candidate(found, name, place_id=None):
    """A place (not yet saved) from a core.place_search candidate and the
    name the user gave it. Raises PlaceError."""
    raw = dict(found or {}, name=name)
    if place_id:
        raw["id"] = place_id
    return check_place(raw)


# ------------------------------------------------------------
# Migration (first start of core 2.8)
# ------------------------------------------------------------

def _home_from_flight_radar(data):
    """Flight Radar's exact home (an address or pasted coordinates), or None."""
    location = data.get("location") if isinstance(data, dict) else None
    if not isinstance(location, dict) or location.get("kind") not in ("address", "coordinates"):
        return None
    lat, lon = to_float(location.get("latitude")), to_float(location.get("longitude"))
    if lat is None or lon is None:
        return None
    return candidate(lat, lon, location["kind"], label=location.get("detail") or "")


def _home_from_weather(data):
    """The Weather extension's city, or None."""
    location = data.get("location") if isinstance(data, dict) else None
    if not isinstance(location, dict):
        return None
    lat, lon = to_float(location.get("latitude")), to_float(location.get("longitude"))
    name = clean_name(location.get("name"))
    if lat is None or lon is None or not name:
        return None
    region, country = location.get("admin1") or "", location.get("country") or ""
    return candidate(lat, lon, "city", name=name, label=city_label(name, region, country),
                     timezone=location.get("timezone"), city=name, region=region,
                     country=country)


def migrate(load=None):
    """Once, when there are no places yet: make "Home" ("Rumah") from Flight
    Radar's exact home if it has one, otherwise from the Weather city.
    Extensions keep their own saved places (see initial_choice), so nothing
    is lost. Returns the place made, or None."""
    load = load or core.api.load_data
    if _store()["migrated"]:
        return None
    home = None
    for key, reader in ((FLIGHT_RADAR_KEY, _home_from_flight_radar),
                        (WEATHER_KEY, _home_from_weather)):
        try:
            found = reader(load(key))
            home = place_from_candidate(found, _("places_default_home")) if found else None
        except PlaceError:
            home = None
        if home:
            break
    store = {"version": VERSION, "places": [home] if home else [],
             "main": home["id"] if home else None, "migrated": True}
    _save_store(store)
    if home:
        logger.info(f"Places: made {home['name']} from the {home['source']} saved before.")
    return dict(home) if home else None


# ------------------------------------------------------------
# Geometry and time zones
# ------------------------------------------------------------

def _point(value):
    """(lat, lon) of a place, a location dict or a (lat, lon) pair."""
    if isinstance(value, dict):
        lat = value.get("lat", value.get("latitude"))
        lon = value.get("lon", value.get("longitude"))
    else:
        lat, lon = value
    return float(lat), float(lon)


def rounded(place, decimals=2):
    """The point to send to a service: (lat, lon) rounded, 2 decimals by
    default (about 1 km), so the exact point stays on this computer."""
    lat, lon = _point(place)
    return round(lat, decimals), round(lon, decimals)


def distance_km(a, b):
    """Great-circle distance in kilometres between two places or points."""
    lat1, lon1 = map(math.radians, _point(a))
    lat2, lon2 = map(math.radians, _point(b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def bearing(a, b):
    """Initial compass bearing from a to b, in degrees (0 north, 90 east)."""
    lat1, lon1 = map(math.radians, _point(a))
    lat2, lon2 = map(math.radians, _point(b))
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def same_point(a, b, tolerance=SAME_POINT_DEGREES):
    try:
        (lat1, lon1), (lat2, lon2) = _point(a), _point(b)
    except (TypeError, ValueError, KeyError):
        return False
    return abs(lat1 - lat2) < tolerance and abs(lon1 - lon2) < tolerance


def local_zone():
    """The computer's own time zone."""
    return datetime.datetime.now().astimezone().tzinfo


def timezone_for(place):
    """The place's time zone (zoneinfo), or the computer's own when the place
    has none (an address or pasted coordinates) or it is unknown here."""
    name = clean_timezone((place or {}).get("timezone"))
    if name:
        try:
            import zoneinfo
            return zoneinfo.ZoneInfo(name)
        except Exception:
            pass
    return local_zone()


# ------------------------------------------------------------
# Words
# ------------------------------------------------------------

def point_text(latitude, longitude, decimals=4):
    return f"{float(latitude):.{decimals}f}, {float(longitude):.{decimals}f}"


def where_text(place):
    """Where a place is, in words: "Jalan Merdeka 1, Batam (1.1301, 104.0529)",
    or just the coordinates."""
    point = point_text(place["lat"], place["lon"])
    label = place.get("label") or ""
    return _("places_where", label=label, point=point) if label else point


def describe(place):
    """ "Home: Jalan Merdeka 1, Batam (1.1301, 104.0529)" """
    return _("places_describe", name=place["name"], where=where_text(place))


# ------------------------------------------------------------
# Extensions: which place they use
# ------------------------------------------------------------

def normalize_choice(value):
    """What an extension stored: "main", "own", a place id, or None (not
    decided yet)."""
    if value in (CHOICE_MAIN, CHOICE_OWN):
        return value
    if isinstance(value, str) and _ID_RE.match(value):
        return value
    return None


def initial_choice(own_location=None):
    """The choice for an extension that has none saved yet: "own" when it has
    a place of its own that isn't the main place, else "main"."""
    if not own_location:
        return CHOICE_MAIN
    main = get_main()
    if main and same_point(main, own_location):
        return CHOICE_MAIN
    return CHOICE_OWN


def resolve(choice):
    """The place a choice means: the main place for "main" (and for a place
    that was removed), that place for an id, None for "own"."""
    choice = normalize_choice(choice) or CHOICE_MAIN
    if choice == CHOICE_OWN:
        return None
    if choice != CHOICE_MAIN:
        place = get_place(choice)
        if place:
            return place
    return get_main()


def location_dict(place):
    """A place in the shape extensions keep their own location in: "name",
    "latitude", "longitude", "timezone" ("" when unknown), empty "admin1",
    "admin2" and "country" (so labels built from them show just the name),
    "kind"/"detail" ("address" and the address or city, or "coordinates"),
    and "place_id", "city" and "label"."""
    label = place.get("label") or ""
    return {"name": place["name"], "admin1": "", "admin2": "", "country": "",
            "latitude": place["lat"], "longitude": place["lon"],
            "timezone": place.get("timezone") or "",
            "kind": "address" if label else "coordinates", "detail": label,
            "place_id": place["id"], "city": place.get("city") or "", "label": label}


def location_for(choice, own_location=None):
    """The location an extension uses: its own for "own" (None if it has
    none), else the chosen place (or the main place) as location_dict(), or
    None when there is none. A choice not saved yet is initial_choice()."""
    choice = normalize_choice(choice) or initial_choice(own_location)
    if choice == CHOICE_OWN:
        return own_location
    place = resolve(choice)
    return location_dict(place) if place else None


def choice_entries(own=True):
    """[(choice, text)] for an extension's "Place:" list: the main place,
    every saved place, then "Its own place…" when the extension has one."""
    main = get_main()
    entries = [(CHOICE_MAIN, _("places_choice_main", name=main["name"]) if main
                else _("places_choice_main_none"))]
    entries += [(p["id"], p["name"]) for p in get_places()]
    if own:
        entries.append((CHOICE_OWN, _("places_choice_own")))
    return entries
