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
User-Agent), which also knows countries by name in any language (feature
code PCL...). Only the name typed or said is sent; the user's own place is
never part of a request. No wx.
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

def city_url(name, language="en", count=SEARCH_COUNT):
    """A geocoding search in any language Open-Meteo knows ("ja" gives 東京都)."""
    params = {"name": " ".join(str(name or "").split()), "count": count,
              "language": (language or "en").split("-")[0].lower(), "format": "json"}
    return place_search.GEOCODING_URL + "?" + urllib.parse.urlencode(params)


def parse_results(payload):
    """Open-Meteo's results as plain dicts, the unusable ones dropped."""
    found = []
    results = payload.get("results") if isinstance(payload, dict) else None
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        lat = place_search.to_float(item.get("latitude"))
        lon = place_search.to_float(item.get("longitude"))
        name = " ".join(str(item.get("name") or "").split())
        if lat is None or lon is None or not name:
            continue
        try:
            place_search.validate(lat, lon)
        except place_search.LocationError:
            continue
        population = item.get("population")
        found.append({
            "name": name,
            "latitude": lat,
            "longitude": lon,
            "country": " ".join(str(item.get("country") or "").split()),
            "country_code": str(item.get("country_code") or "").upper()[:2],
            "region": " ".join(str(item.get("admin1") or "").split()),
            "timezone": place_search.clean_timezone(item.get("timezone")) or "",
            "feature": str(item.get("feature_code") or "").upper(),
            "population": population if isinstance(population, int) else 0,
        })
    return found


def is_country(result):
    return str(result.get("feature", "")).startswith("PCL")


# Things that aren't a place to land in: airports, parks, buildings...
_NOT_A_TOWN = ("AIRP", "AMUS", "HTL", "RSTN", "BLDG", "SCH", "HSP", "MUS", "STDM", "MALL",
               "CH", "MSQE", "TMPL", "PRK", "RES", "ZOO", "PO", "RSTP", "BUSTN")


def choose(results, cc=None, capital_first=False):
    """The best result: in country `cc` when given, never a country or an
    airport; with `capital_first`, a capital (PPLC) before a bigger town."""
    usable = [r for r in results if not is_country(r) and r["feature"] not in _NOT_A_TOWN
              and (cc is None or r["country_code"] == cc)]
    if not usable:
        return None
    if capital_first:
        capitals = [r for r in usable if r["feature"] == "PPLC"]
        if capitals:
            return capitals[0]
    # The geocoder puts the best match first; a town beats a same-named hill.
    towns = [r for r in usable if r["feature"].startswith(("PPL", "ADM", "ISL"))]
    return (towns or usable)[0]


def _search(name, language, fetch):
    try:
        return parse_results(fetch(city_url(name, language)))
    except place_search.FetchError as e:
        raise ResolveError("offline", str(e)) from e


def destination(result, query=""):
    """A result as the trip keeps it."""
    dest = dict(result)
    dest["query"] = query
    return dest


def _city_of_country(cc, language, fetch):
    city = COUNTRY_CITIES.get(cc)
    if not city:
        raise ResolveError("no_city", cc)
    found = choose(_search(city, language, fetch), cc=cc, capital_first=False)
    if found is None:
        raise ResolveError("not_found", city)
    return found


def resolve(text, language, fetch=None, rng=None, avoid=None):
    """The destination for what the user asked (not "home"): a dict with
    "name", "country", "country_code", "region", "latitude", "longitude",
    "timezone", "feature", "population" and "query". `language` is the user's
    ("id" or "en"), for the names. Blocks on the network. Raises ResolveError."""
    fetch = fetch or place_search.fetch_json
    query = parse_query(text)
    kind = query["kind"]
    if kind in ("empty", "home"):
        raise ResolveError("not_found", text)
    if kind == "surprise":
        rng = rng or random
        choices = [c for c in SURPRISE_CITIES if c[0] != avoid] or list(SURPRISE_CITIES)
        name, cc = rng.choice(choices)
        found = choose(_search(name, language, fetch), cc=cc)
        if found is None:
            raise ResolveError("not_found", name)
        dest = destination(found, text)
        dest["surprise"] = name          # its English name, so the next surprise differs
        return dest
    if kind == "country":
        return destination(_city_of_country(query["cc"], language, fetch), text)
    results = _search(query["name"], language, fetch)
    if not results:
        raise ResolveError("not_found", query["name"])
    first = results[0]
    if is_country(first) and first["country_code"]:
        # "Jepang", "Prancis", "Japan": a country, so its best-known city.
        return destination(_city_of_country(first["country_code"], language, fetch), text)
    found = choose(results)
    if found is None:
        raise ResolveError("not_found", query["name"])
    return destination(found, text)


def localized_name(dest, code, fetch=None):
    """The destination's name in language `code` (the primary subtag is sent),
    from a result within NEAR_KM of it, or None. Blocks on the network."""
    fetch = fetch or place_search.fetch_json
    try:
        results = parse_results(fetch(city_url(dest["name"], code)))
    except place_search.FetchError:
        return None
    for result in results:
        if is_country(result):
            continue
        if distance_km(result, dest) <= NEAR_KM:
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
