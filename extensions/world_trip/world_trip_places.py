# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Where World Trip flies: what the user asked for ("Tokyo", "Jepang", "mana
saja") turned into a destination, and the flight's distance and time.

  parse_query(text)      -> home, a surprise city, a country or a place
  resolve(text, lang, fetch) -> a destination (blocks on the network: call it
                            on a worker thread)
  localized_name(...)    -> the city's name in another language
  flight_minutes(km), round_minutes(), round_km()

A country becomes its capital or best-known city (COUNTRY_CITIES). Places
are found through Open-Meteo's geocoding (core.place_search's URL, fetch and
User-Agent), searched in English and in the user's language and then looked
up by id to be named in the user's language; the geocoder also knows
countries by name (feature code PCL...). Only the name typed or said is
sent; the user's own place is never part of a request. No wx.
"""

import math
import random
import urllib.parse

import core.place_search as place_search

import world_trip_phrases as phrases

CRUISE_KMH = 800.0          # a jet's cruising speed
EXTRA_MINUTES = 30          # taxi, climb and descent
SAME_PLACE_KM = 30.0        # closer than this to home: "you're already there"
NEAR_KM = 60.0              # a localized search result this close is the same city
SEARCH_COUNT = 10


class ResolveError(Exception):
    """`kind`: "not_found", "offline" or "no_city" (a country we know no city of)."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


# ------------------------------------------------------------
# Countries
# ------------------------------------------------------------

# Each country's capital or best-known city (its English name, searched with
# the country code). A trip "to Japan" lands in Tokyo.
COUNTRY_CITIES = {
    "AD": "Andorra la Vella", "AE": "Dubai", "AF": "Kabul", "AG": "Saint John's",
    "AL": "Tirana", "AM": "Yerevan", "AO": "Luanda", "AR": "Buenos Aires", "AT": "Vienna",
    "AU": "Sydney", "AW": "Oranjestad", "AZ": "Baku", "BA": "Sarajevo", "BB": "Bridgetown",
    "BD": "Dhaka", "BE": "Brussels", "BF": "Ouagadougou", "BG": "Sofia", "BH": "Manama",
    "BI": "Gitega", "BJ": "Cotonou", "BN": "Bandar Seri Begawan", "BO": "La Paz",
    "BR": "Rio de Janeiro", "BS": "Nassau", "BT": "Thimphu", "BW": "Gaborone", "BY": "Minsk",
    "BZ": "Belize City", "CA": "Toronto", "CD": "Kinshasa", "CF": "Bangui", "CG": "Brazzaville",
    "CH": "Zurich", "CI": "Abidjan", "CL": "Santiago", "CM": "Yaounde", "CN": "Beijing",
    "CO": "Bogota", "CR": "San Jose", "CU": "Havana", "CV": "Praia", "CW": "Willemstad",
    "CY": "Nicosia", "CZ": "Prague", "DE": "Berlin", "DJ": "Djibouti", "DK": "Copenhagen",
    "DM": "Roseau", "DO": "Santo Domingo", "DZ": "Algiers", "EC": "Quito", "EE": "Tallinn",
    "EG": "Cairo", "ER": "Asmara", "ES": "Madrid", "ET": "Addis Ababa", "FI": "Helsinki",
    "FJ": "Suva", "FM": "Palikir", "FR": "Paris", "GA": "Libreville", "GB": "London",
    "GD": "Saint George's", "GE": "Tbilisi", "GH": "Accra", "GL": "Nuuk", "GM": "Banjul",
    "GN": "Conakry", "GQ": "Malabo", "GR": "Athens", "GT": "Guatemala City", "GU": "Hagatna",
    "GW": "Bissau", "GY": "Georgetown", "HK": "Hong Kong", "HN": "Tegucigalpa",
    "HR": "Zagreb", "HT": "Port-au-Prince", "HU": "Budapest", "ID": "Jakarta", "IE": "Dublin",
    "IL": "Tel Aviv", "IN": "New Delhi", "IQ": "Baghdad", "IR": "Tehran", "IS": "Reykjavik",
    "IT": "Rome", "JM": "Kingston", "JO": "Amman", "JP": "Tokyo", "KE": "Nairobi",
    "KG": "Bishkek", "KH": "Phnom Penh", "KI": "Tarawa", "KM": "Moroni", "KN": "Basseterre",
    "KP": "Pyongyang", "KR": "Seoul", "KW": "Kuwait City", "KZ": "Almaty", "LA": "Vientiane",
    "LB": "Beirut", "LC": "Castries", "LI": "Vaduz", "LK": "Colombo", "LR": "Monrovia",
    "LS": "Maseru", "LT": "Vilnius", "LU": "Luxembourg", "LV": "Riga", "LY": "Tripoli",
    "MA": "Marrakesh", "MC": "Monaco", "MD": "Chisinau", "ME": "Podgorica",
    "MG": "Antananarivo", "MH": "Majuro", "MK": "Skopje", "ML": "Bamako", "MM": "Yangon",
    "MN": "Ulaanbaatar", "MO": "Macau", "MR": "Nouakchott", "MT": "Valletta",
    "MU": "Port Louis", "MV": "Male", "MW": "Lilongwe", "MX": "Mexico City",
    "MY": "Kuala Lumpur", "MZ": "Maputo", "NA": "Windhoek", "NC": "Noumea", "NE": "Niamey",
    "NG": "Lagos", "NI": "Managua", "NL": "Amsterdam", "NO": "Oslo", "NP": "Kathmandu",
    "NR": "Yaren", "NZ": "Auckland", "OM": "Muscat", "PA": "Panama City", "PE": "Lima",
    "PF": "Papeete", "PG": "Port Moresby", "PH": "Manila", "PK": "Islamabad", "PL": "Warsaw",
    "PR": "San Juan", "PS": "Ramallah", "PT": "Lisbon", "PW": "Ngerulmud", "PY": "Asuncion",
    "QA": "Doha", "RO": "Bucharest", "RS": "Belgrade", "RU": "Moscow", "RW": "Kigali",
    "SA": "Mecca", "SB": "Honiara", "SC": "Victoria", "SD": "Khartoum", "SE": "Stockholm",
    "SG": "Singapore", "SI": "Ljubljana", "SK": "Bratislava", "SL": "Freetown",
    "SM": "San Marino", "SN": "Dakar", "SO": "Mogadishu", "SR": "Paramaribo", "SS": "Juba",
    "ST": "Sao Tome", "SV": "San Salvador", "SY": "Damascus", "SZ": "Mbabane",
    "TD": "N'Djamena", "TG": "Lome", "TH": "Bangkok", "TJ": "Dushanbe", "TL": "Dili",
    "TM": "Ashgabat", "TN": "Tunis", "TO": "Nuku'alofa", "TR": "Istanbul",
    "TT": "Port of Spain", "TV": "Funafuti", "TW": "Taipei", "TZ": "Dar es Salaam",
    "UA": "Kyiv", "UG": "Kampala", "US": "New York", "UY": "Montevideo", "UZ": "Tashkent",
    "VA": "Vatican City", "VC": "Kingstown", "VE": "Caracas", "VN": "Hanoi",
    "VU": "Port Vila", "WS": "Apia", "XK": "Pristina", "YE": "Sanaa", "ZA": "Cape Town",
    "ZM": "Lusaka", "ZW": "Harare",
}

# Country names people say, in Indonesian and English (compared without case
# or accents). Anything else is still found as a country through the geocoder.
COUNTRY_ALIASES = {
    "JP": ("jepang", "japan", "nippon"),
    "KR": ("korea", "korea selatan", "south korea", "korsel"),
    "KP": ("korea utara", "north korea", "korut"),
    "CN": ("cina", "china", "tiongkok", "rrt", "tiongkok daratan"),
    "TW": ("taiwan",),
    "TH": ("thailand", "muangthai", "thai"),
    "VN": ("vietnam", "viet nam"),
    "MY": ("malaysia",),
    "PH": ("filipina", "philippines", "the philippines"),
    "IN": ("india",),
    "KH": ("kamboja", "cambodia"),
    "LA": ("laos",),
    "MM": ("myanmar", "burma"),
    "BN": ("brunei", "brunei darussalam"),
    "TL": ("timor leste", "east timor"),
    "SA": ("arab saudi", "saudi arabia", "saudi", "arab"),
    "AE": ("uni emirat arab", "united arab emirates", "uae", "emirat arab", "emirates"),
    "EG": ("mesir", "egypt"),
    "JO": ("yordania", "jordan"),
    "LB": ("lebanon", "libanon"),
    "SY": ("suriah", "syria"),
    "IQ": ("irak", "iraq"),
    "KW": ("kuwait",),
    "QA": ("qatar",),
    "BH": ("bahrain",),
    "OM": ("oman",),
    "YE": ("yaman", "yemen"),
    "MA": ("maroko", "morocco"),
    "DZ": ("aljazair", "algeria"),
    "TN": ("tunisia",),
    "LY": ("libya", "libia"),
    "SD": ("sudan",),
    "PS": ("palestina", "palestine"),
    "TR": ("turki", "turkey", "turkiye"),
    "RU": ("rusia", "russia"),
    "UA": ("ukraina", "ukraine"),
    "FR": ("prancis", "perancis", "france"),
    "BE": ("belgia", "belgium"),
    "CH": ("swiss", "switzerland", "swis"),
    "DE": ("jerman", "germany"),
    "AT": ("austria",),
    "ES": ("spanyol", "spain"),
    "MX": ("meksiko", "mexico"),
    "AR": ("argentina",),
    "CO": ("kolombia", "colombia"),
    "PE": ("peru",),
    "CL": ("chili", "chile"),
    "VE": ("venezuela",),
    "CU": ("kuba", "cuba"),
    "BR": ("brasil", "brazil"),
    "PT": ("portugal",),
    "IT": ("italia", "italy"),
    "NL": ("belanda", "netherlands", "the netherlands", "holland"),
    "GR": ("yunani", "greece"),
    "CY": ("siprus", "cyprus"),
    "SE": ("swedia", "sweden"),
    "NO": ("norwegia", "norway"),
    "DK": ("denmark",),
    "FI": ("finlandia", "finland"),
    "IS": ("islandia", "iceland"),
    "PL": ("polandia", "poland"),
    "CZ": ("ceko", "czech", "czechia", "czech republic"),
    "HU": ("hungaria", "hungary"),
    "GB": ("inggris", "england", "britania raya", "united kingdom", "uk", "great britain",
           "britain"),
    "IE": ("irlandia", "ireland"),
    "US": ("amerika", "amerika serikat", "usa", "united states", "america",
           "united states of america"),
    "CA": ("kanada", "canada"),
    "AU": ("australia",),
    "NZ": ("selandia baru", "new zealand"),
    "ZA": ("afrika selatan", "south africa"),
    "NG": ("nigeria",),
    "KE": ("kenya",),
    "TZ": ("tanzania",),
    "ET": ("ethiopia", "etiopia"),
    "GH": ("ghana",),
    "IL": ("israel",),
    "IR": ("iran",),
    "AF": ("afganistan", "afghanistan"),
    "PK": ("pakistan",),
    "BD": ("bangladesh",),
    "NP": ("nepal",),
    "LK": ("sri lanka",),
    "MV": ("maladewa", "maldives"),
    "MN": ("mongolia",),
    "KZ": ("kazakhstan",),
    "UZ": ("uzbekistan",),
    "ID": ("indonesia",),
}
_ALIAS_TO_CC = {alias: cc for cc, aliases in COUNTRY_ALIASES.items() for alias in aliases}

# Cities for "take me anywhere": famous, far apart, all with a local greeting.
SURPRISE_CITIES = (
    ("Tokyo", "JP"), ("Kyoto", "JP"), ("Osaka", "JP"), ("Seoul", "KR"), ("Busan", "KR"),
    ("Beijing", "CN"), ("Shanghai", "CN"), ("Hong Kong", "HK"), ("Taipei", "TW"),
    ("Bangkok", "TH"), ("Chiang Mai", "TH"), ("Hanoi", "VN"), ("Kuala Lumpur", "MY"),
    ("Singapore", "SG"), ("Manila", "PH"), ("New Delhi", "IN"), ("Jaipur", "IN"),
    ("Siem Reap", "KH"), ("Dubai", "AE"), ("Mecca", "SA"), ("Istanbul", "TR"),
    ("Cairo", "EG"), ("Marrakesh", "MA"), ("Tehran", "IR"), ("Moscow", "RU"),
    ("Paris", "FR"), ("London", "GB"), ("Berlin", "DE"), ("Vienna", "AT"),
    ("Amsterdam", "NL"), ("Rome", "IT"), ("Venice", "IT"), ("Barcelona", "ES"),
    ("Madrid", "ES"), ("Lisbon", "PT"), ("Athens", "GR"), ("Stockholm", "SE"),
    ("Krakow", "PL"), ("Nairobi", "KE"), ("Cape Town", "ZA"), ("New York", "US"),
    ("San Francisco", "US"), ("Mexico City", "MX"), ("Rio de Janeiro", "BR"),
    ("Buenos Aires", "AR"), ("Sydney", "AU"), ("Montreal", "CA"), ("Yogyakarta", "ID"),
)

HOME_WORDS = ("rumah", "home", "pulang", "kampung halaman", "rumahku", "my home", "back home")
ANYWHERE_WORDS = ("mana saja", "mana aja", "manapun", "mana pun", "sembarang tempat",
                  "sembarang", "anywhere", "somewhere", "random", "acak", "kejutan",
                  "surprise", "somewhere nice", "tempat kejutan", "mana saja deh")


def parse_query(text):
    """What a trip request asks for: {"kind": "home"}, {"kind": "surprise"},
    {"kind": "country", "cc": "JP"} or {"kind": "place", "name": "Tokyo"}."""
    name = " ".join(str(text or "").strip(" \t.,!?;:\"'“”").split())
    key = phrases.normalize(name)
    if not key:
        return {"kind": "empty"}
    if key in HOME_WORDS:
        return {"kind": "home"}
    if key in ANYWHERE_WORDS:
        return {"kind": "surprise"}
    cc = _ALIAS_TO_CC.get(key)
    if cc:
        return {"kind": "country", "cc": cc}
    return {"kind": "place", "name": name}


# ------------------------------------------------------------
# Open-Meteo geocoding
# ------------------------------------------------------------
# A search's results depend on its language: in Indonesian, "Mecca" doesn't
# find the city in Saudi Arabia (its Indonesian name is "Mekkah") and "New
# York" finds York, Nebraska first. So a place is searched in English and in
# the user's language, the candidates are scored (the name said, population,
# a capital, the user's own country), and the one chosen is then looked up by
# its GeoNames id in the user's language ("Mekkah, Arab Saudi") and, later,
# in the local language ("Москва", "Αθήνα"), which is always the same place.

GET_URL = "https://geocoding-api.open-meteo.com/v1/get"
# The country whose places win a close call, by the user's language: "Bali"
# is the island for an Indonesian, not Bāli in India.
HOME_COUNTRY_BY_LANGUAGE = {"id": "ID"}
# Words the Indonesian names put before a city: "Kota New York", "DI Yogyakarta".
ADMIN_PREFIXES = ("kota", "di", "daerah istimewa", "kabupaten", "pulau", "provinsi",
                  "kota administrasi", "city of", "prefektur")


def city_url(name, language="en", count=SEARCH_COUNT):
    """A geocoding search in any language Open-Meteo knows ("ja" gives 東京都)."""
    params = {"name": " ".join(str(name or "").split()), "count": count,
              "language": (language or "en").split("-")[0].lower(), "format": "json"}
    return place_search.GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def get_url(geo_id, language="en"):
    """One place by its GeoNames id, named in `language`."""
    params = {"id": int(geo_id), "language": (language or "en").split("-")[0].lower()}
    return GET_URL + "?" + urllib.parse.urlencode(params)


def parse_result(item):
    """One Open-Meteo place as a plain dict, or None when unusable."""
    if not isinstance(item, dict):
        return None
    lat = place_search.to_float(item.get("latitude"))
    lon = place_search.to_float(item.get("longitude"))
    name = " ".join(str(item.get("name") or "").split())
    if lat is None or lon is None or not name:
        return None
    try:
        place_search.validate(lat, lon)
    except place_search.LocationError:
        return None
    population = item.get("population")
    geo_id = item.get("id")
    return {
        "id": geo_id if isinstance(geo_id, int) and not isinstance(geo_id, bool) else None,
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "country": " ".join(str(item.get("country") or "").split()),
        "country_code": str(item.get("country_code") or "").upper()[:2],
        "region": " ".join(str(item.get("admin1") or "").split()),
        "timezone": place_search.clean_timezone(item.get("timezone")) or "",
        "feature": str(item.get("feature_code") or "").upper(),
        "population": population if isinstance(population, int) else 0,
    }


def parse_results(payload):
    """Open-Meteo's results as plain dicts, the unusable ones dropped."""
    results = payload.get("results") if isinstance(payload, dict) else None
    found = [parse_result(item) for item in (results if isinstance(results, list) else [])]
    return [r for r in found if r]


def is_country(result):
    return str(result.get("feature", "")).startswith("PCL")


# Things that aren't a place to land in: airports, parks, buildings...
_NOT_A_TOWN = ("AIRP", "AIRH", "AMUS", "HTL", "RSTN", "BLDG", "SCH", "HSP", "MUS", "STDM",
               "MALL", "CH", "MSQE", "TMPL", "PRK", "RES", "ZOO", "PO", "RSTP", "BUSTN")


def score(result, query, bias_cc=None, first=False):
    """How well a result fits what was said: its name (said exactly, or in
    its name), how many live there, a capital, the user's own country."""
    key, name = phrases.normalize(query), phrases.normalize(result["name"])
    value = 0.0
    if key and name == key:
        value += 3.0
    elif key and f" {key} " in f" {name} ":
        value += 2.0
    value += math.log10(max(0, result.get("population") or 0) + 1)
    value += {"PPLC": 2.0, "PPLA": 1.0, "PPLA2": 0.5}.get(result["feature"], 0.0)
    if bias_cc and result["country_code"] == bias_cc:
        value += 1.0
    if first:
        value += 0.3
    return value


def choose(results, query="", cc=None, bias_cc=None):
    """The best town among the results (in country `cc` when given): never a
    country, an airport or a building."""
    usable = [(i, r) for i, r in enumerate(results)
              if not is_country(r) and r["feature"] not in _NOT_A_TOWN
              and (cc is None or r["country_code"] == cc)]
    if not usable:
        return None
    return max(usable, key=lambda item: (score(item[1], query, bias_cc, item[0] == 0),
                                         -item[0]))[1]


def _search(name, language, fetch):
    try:
        return parse_results(fetch(city_url(name, language)))
    except place_search.FetchError as e:
        raise ResolveError("offline", str(e)) from e


def _searches(name, language, fetch):
    """Results in English, then in the user's language (duplicates once),
    each with the language it was named in ("source_language")."""
    found = [dict(r, source_language="en") for r in _search(name, "en", fetch)]
    if language and language != "en":
        seen = {r["id"] for r in found if r["id"]}
        found += [dict(r, source_language=language) for r in _search(name, language, fetch)
                  if not r["id"] or r["id"] not in seen]
    return found


def lookup(geo_id, language, fetch):
    """A place by its GeoNames id, named in `language`, or None."""
    if not geo_id:
        return None
    try:
        return parse_result(fetch(get_url(geo_id, language)))
    except (place_search.FetchError, ValueError, TypeError):
        return None


def display_name(local, english):
    """The user's name for a city without an administrative word before it:
    "Kota New York" -> "New York", "DI Yogyakarta" -> "Yogyakarta"; "Kota
    Kinabalu" stays (that is its name)."""
    local_key, english_key = phrases.normalize(local), phrases.normalize(english)
    if english and local_key != english_key and local_key.endswith(" " + english_key):
        if local_key[:-len(english_key)].strip() in ADMIN_PREFIXES:
            return english
    return local


def destination(result, query="", language="en", fetch=None):
    """A result as the trip keeps it: named in the user's language (looked
    up by its id), with its English name in "name_en"."""
    dest = dict(result)
    source = dest.pop("source_language", "en")
    dest["query"] = query
    english = result["name"]
    if source != "en" and fetch is not None:
        found = lookup(result.get("id"), "en", fetch)
        english = found["name"] if found else english
    dest["name_en"] = english
    if language and language != "en" and fetch is not None:
        local = result if source == language else lookup(result.get("id"), language, fetch)
        if local:
            dest["name"] = display_name(local["name"], english)
            dest["country"] = local["country"] or result["country"]
            dest["region"] = local["region"] or result["region"]
    if dest["country_code"] == "SG" and dest.get("country"):
        # The city-state goes by its country's name: "Singapura", not
        # "Singapore, Singapura" (the geocoder names the city in English).
        dest["name"] = dest["country"]
    return dest


def _city_of_country(cc, language, fetch, query):
    city = COUNTRY_CITIES.get(cc)
    if not city:
        raise ResolveError("no_city", cc)
    found = choose(_search(city, "en", fetch), city, cc=cc)
    if found is None:
        raise ResolveError("not_found", city)
    return destination(found, query, language, fetch)


def resolve(text, language, fetch=None, rng=None, avoid=None):
    """The destination for what the user asked (not "home"): a dict with
    "name" (in the user's language), "name_en", "country", "country_code",
    "region", "latitude", "longitude", "timezone", "feature", "population",
    "id" (GeoNames) and "query". `language` is the user's ("id" or "en").
    Blocks on the network. Raises ResolveError."""
    fetch = fetch or place_search.fetch_json
    query = parse_query(text)
    kind = query["kind"]
    if kind in ("empty", "home"):
        raise ResolveError("not_found", text)
    if kind == "surprise":
        rng = rng or random
        choices = [c for c in SURPRISE_CITIES if c[0] != avoid] or list(SURPRISE_CITIES)
        name, cc = rng.choice(choices)
        found = choose(_search(name, "en", fetch), name, cc=cc)
        if found is None:
            raise ResolveError("not_found", name)
        dest = destination(found, text, language, fetch)
        dest["surprise"] = name          # its English name, so the next surprise differs
        return dest
    if kind == "country":
        return _city_of_country(query["cc"], language, fetch, text)
    name = query["name"]
    results = _searches(name, language, fetch)
    key = phrases.normalize(name)
    for result in results:
        # "Jepang", "Prancis", "Japan": a country, so its best-known city.
        if is_country(result) and result["country_code"] and \
                phrases.normalize(result["name"]) == key:
            return _city_of_country(result["country_code"], language, fetch, text)
    found = choose(results, name, bias_cc=HOME_COUNTRY_BY_LANGUAGE.get(language))
    if found is None:
        raise ResolveError("not_found", name)
    return destination(found, text, language, fetch)


def localized_name(dest, code, fetch=None):
    """The destination's name in language `code` (its primary subtag is
    sent): looked up by its id, else from a search result within NEAR_KM of
    it; None when unknown. Blocks on the network."""
    fetch = fetch or place_search.fetch_json
    found = lookup(dest.get("id"), code, fetch)
    if found:
        return found["name"]
    try:
        results = parse_results(fetch(city_url(dest.get("name_en") or dest["name"], code)))
    except place_search.FetchError:
        return None
    for result in results:
        if not is_country(result) and distance_km(result, dest) <= NEAR_KM:
            return result["name"]
    return None


# ------------------------------------------------------------
# Distance and flight time
# ------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0


def distance_km(a, b):
    """Great-circle distance between two dicts with "latitude"/"longitude"."""
    lat1, lon1 = math.radians(a["latitude"]), math.radians(a["longitude"])
    lat2, lon2 = math.radians(b["latitude"]), math.radians(b["longitude"])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def flight_minutes(km):
    """About how long the flight takes: at 800 km/h, plus 30 minutes."""
    return max(0.0, float(km)) / CRUISE_KMH * 60.0 + EXTRA_MINUTES


def round_minutes(minutes):
    """A flight time as people say it: to 5 minutes under an hour, to a
    quarter of an hour under three hours, to half an hour after that."""
    minutes = max(0.0, float(minutes))
    if minutes < 60:
        return max(5, int(round(minutes / 5.0)) * 5)
    if minutes < 180:
        return int(round(minutes / 15.0)) * 15
    return int(round(minutes / 30.0)) * 30


def round_km(km):
    """A distance as people say it: 5,300 kilometres, 850, 35."""
    km = max(0.0, float(km))
    if km < 100:
        return max(5, int(round(km / 5.0)) * 5)
    if km < 1000:
        return int(round(km / 10.0)) * 10
    return int(round(km / 100.0)) * 100


# ------------------------------------------------------------
# Home: the user's main place (Preferences, Places)
# ------------------------------------------------------------

def home_from_place(place):
    """The main place as a trip needs it, or None. Its exact point stays on
    this computer: it is only used here, for the distance."""
    if not place:
        return None
    try:
        lat, lon = float(place["lat"]), float(place["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    name = str(place.get("city") or "").strip() or str(place.get("name") or "").strip()
    return {"name": name, "latitude": lat, "longitude": lon,
            "timezone": str(place.get("timezone") or ""),
            "country_code": ""}
