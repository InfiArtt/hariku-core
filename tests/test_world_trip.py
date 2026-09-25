# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the World Trip extension, all on fakes: the greetings and phrases
# (every language has every one), which language a place speaks, finding a
# destination (Open-Meteo answers are canned), the distance and flight time,
# what is said in English and Indonesian, the weather and Wikipedia parsing,
# Radio Browser (servers, ranking), the native voice choice, "any key", the
# radio player (a fake Media Foundation), the trip from departure to home
# (a fake clock, fake speech, fake radio), Aruna's commands, the settings and
# the generated sounds. Nothing reaches the network (urlopen fails the test),
# nothing is played, spoken or shown.

import datetime
import importlib.util
import io
import json
import os
import random
import sys
import types
import wave

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "world_trip")
UTC = datetime.timezone.utc


def _modules():
    if EXT_DIR not in sys.path:
        sys.path.insert(0, EXT_DIR)
    import world_trip_keys
    import world_trip_net
    import world_trip_phrases
    import world_trip_places
    import world_trip_radio
    import world_trip_stations
    import world_trip_text
    import world_trip_trip
    import world_trip_voices
    return types.SimpleNamespace(keys=world_trip_keys, net=world_trip_net,
                                 phrases=world_trip_phrases, places=world_trip_places,
                                 radio=world_trip_radio, stations=world_trip_stations,
                                 text=world_trip_text, trip=world_trip_trip,
                                 voices=world_trip_voices)


@pytest.fixture(scope="module")
def m():
    return _modules()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import urllib.request

    def refuse(*args, **kwargs):
        raise AssertionError(f"real network access attempted: {args[:1]}")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture
def lang(monkeypatch, m):
    """Switch Hariku's language (the core day names are loaded too)."""
    from core import i18n
    had_core, old_core = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("id")
    yield set_lang
    if had_core:
        i18n._language_cache["core"] = old_core
    else:
        i18n._language_cache.pop("core", None)


# Places as Open-Meteo gives them (checked on 25 September 2026).
BATAM = {"name": "Batam", "latitude": 1.1301, "longitude": 104.0529, "timezone": "Asia/Jakarta",
         "country_code": ""}
TOKYO = {"name": "Tokyo", "country": "Jepang", "country_code": "JP", "region": "Prefektur Tokyo",
         "latitude": 35.6895, "longitude": 139.69171, "timezone": "Asia/Tokyo", "feature": "PPLC",
         "population": 9733276, "query": "Tokyo"}
PARIS = {"name": "Paris", "country": "Prancis", "country_code": "FR", "region": "Île-de-France",
         "latitude": 48.85341, "longitude": 2.3488, "timezone": "Europe/Paris", "feature": "PPLC",
         "population": 2138551, "query": "Paris"}
BANGKOK = {"name": "Bangkok", "country": "Thailand", "country_code": "TH", "region": "Bangkok",
           "latitude": 13.75398, "longitude": 100.50144, "timezone": "Asia/Bangkok",
           "feature": "PPLC", "population": 5104476, "query": "Bangkok"}
DENPASAR = {"name": "Denpasar", "country": "Indonesia", "country_code": "ID", "region": "Bali",
            "latitude": -8.65, "longitude": 115.21667, "timezone": "Asia/Makassar",
            "feature": "PPLA", "population": 405923, "query": "Denpasar"}
SINGAPURA = {"name": "Singapura", "country": "Singapura", "country_code": "SG", "region": "",
             "latitude": 1.28967, "longitude": 103.85007, "timezone": "Asia/Singapore",
             "feature": "PPLC", "population": 3547809, "query": "Singapura"}
NOW = datetime.datetime(2026, 9, 25, 12, 30, tzinfo=UTC)     # 19:30 in Batam, 21:30 in Tokyo


def geo(name, lat, lon, cc, country, feature="PPL", population=0, tz="", region="", geo_id=None):
    return {"id": geo_id, "name": name, "latitude": lat, "longitude": lon, "country_code": cc,
            "country": country, "feature_code": feature, "population": population,
            "timezone": tz, "admin1": region}


# ------------------------------------------------------------
# Greetings and phrases
# ------------------------------------------------------------

REQUIRED_LANGUAGES = ("ja", "ko", "zh", "yue", "th", "vi", "ms", "tl", "hi", "ar", "tr", "ru",
                      "fr", "de", "es", "pt", "it", "nl", "el", "sv", "pl", "en", "id", "jv",
                      "he", "fa", "sw")


def _variants(entry):
    return [entry["male"], entry["female"]] if "male" in entry else [entry]


def test_every_language_has_every_greeting_and_phrase(m):
    p = m.phrases
    problems = []
    assert len(p.LANGUAGES) >= 30
    for code in REQUIRED_LANGUAGES:
        assert code in p.LANGUAGES, code
    for code, entry in p.LANGUAGES.items():
        for user in ("id", "en"):
            if not entry["name"].get(user):
                problems.append(f"{code}: no {user} name")
        if not entry["voices"]:
            problems.append(f"{code}: no voice languages")
        items = [(f"greeting {k}", entry["greetings"].get(k)) for k in p.GREETING_KEYS]
        items += [(f"phrase {k}", entry["phrases"].get(k)) for k in p.PHRASE_KEYS]
        items += [("welcome", entry["welcome"]), ("welcome_plain", entry["welcome_plain"])]
        if "afternoon_late" in entry["greetings"]:
            items.append(("afternoon_late", entry["greetings"]["afternoon_late"]))
        for what, item in items:
            if item is None:
                problems.append(f"{code}: no {what}")
                continue
            for variant in _variants(item):
                if not variant["native"].strip():
                    problems.append(f"{code}: {what} is empty")
                if entry["latin"] and variant["translit"]:
                    problems.append(f"{code}: {what} has a transliteration but is Latin")
                if not entry["latin"] and not variant["translit"].strip():
                    problems.append(f"{code}: {what} has no transliteration")
                means = variant["means"] or what.split()[-1]
                for user in ("id", "en"):
                    if not p.meaning(means, user, city="Tokyo"):
                        problems.append(f"{code}: {what} has no {user} meaning ({means})")
        if "{city" not in entry["welcome"]["native"]:
            problems.append(f"{code}: welcome without the city")
        if not entry["latin"] and "{city" not in entry["welcome"]["translit"]:
            problems.append(f"{code}: welcome's transliteration without the city")
    assert not problems, "\n".join(problems)


def test_scripts_are_what_they_say(m):
    p = m.phrases
    for code, entry in p.LANGUAGES.items():
        for group in (entry["greetings"], entry["phrases"]):
            for item in group.values():
                for variant in _variants(item):
                    if entry["latin"]:
                        assert p.has_latin_letters_only(variant["native"]), (code, variant)
                    else:
                        assert not p.has_latin_letters_only(variant["native"]), (code, variant)
                        assert p.has_latin_letters_only(variant["translit"]), (code, variant)


@pytest.mark.parametrize("cc, names, region, expected", [
    ("JP", ["Tokyo"], "", "ja"),
    ("KR", ["Seoul"], "", "ko"),
    ("HK", ["Hong Kong"], "", "yue"),
    ("CN", ["Guangzhou"], "Guangdong", "yue"),
    ("CN", ["Beijing"], "", "zh"),
    ("TW", ["Taipei"], "", "zh-TW"),
    ("CA", ["Montréal"], "Quebec", "fr"),
    ("CA", ["Toronto"], "Ontario", "en"),
    ("BE", ["Antwerpen"], "", "nl"),
    ("BE", ["Brussels"], "", "fr"),
    ("CH", ["Genève"], "", "fr"),
    ("CH", ["Zurich"], "", "de"),
    ("CH", ["Lugano"], "", "it"),
    ("ID", ["Yogyakarta"], "Daerah Istimewa Yogyakarta", "jv"),
    ("ID", ["Surabaya"], "Jawa Timur", "jv"),
    ("ID", ["Batam"], "Kepulauan Riau", "id"),
    ("IL", ["Jerusalem"], "", "ar"),
    ("IL", ["Tel Aviv"], "", "he"),
    ("PT", ["Lisboa"], "", "pt-PT"),
    ("BR", ["Rio de Janeiro"], "", "pt"),
    ("SA", ["Mekkah"], "", "ar"),
    ("KH", ["Siem Reap"], "", "km"),
    ("MN", ["Ulaanbaatar"], "", None),
])
def test_which_language_a_place_speaks(m, cc, names, region, expected):
    assert m.phrases.language_for(cc, names, region) == expected


def test_voice_languages(m):
    p = m.phrases
    assert p.voice_tags("ja", "JP")[0] == "ja-JP"
    assert p.voice_tags("en", "AU")[0] == "en-AU"
    assert p.voice_tags("ar", "EG")[0] == "ar-EG"
    assert p.voice_tags("zh", "CN") == ["zh-CN", "zh-SG", "zh-TW", "cmn-CN"]
    assert "zh-HK" in p.voice_tags("yue", "HK")
    assert not p.any_region("zh") and p.any_region("yue") and p.any_region("fr")
    assert p.voice_tags("xx") == []


def test_greetings_follow_the_local_hour(m):
    p = m.phrases
    assert p.greeting("ja", 7)["translit"] == "Ohayō gozaimasu!"
    assert p.greeting("ja", 13)["translit"] == "Konnichiwa!"
    assert p.greeting("ja", 21)["translit"] == "Konbanwa!"
    assert p.greeting("ja", 2)["means"] == "evening"
    late = p.greeting("id", 16)
    assert late["native"] == "Selamat sore!" and p.meaning(late["means"], "id") == "Selamat sore!"
    assert p.greeting("id", 12)["native"] == "Selamat siang!"
    korean = p.greeting("ko", 8)
    assert korean["native"] == "안녕하세요!" and p.meaning(korean["means"], "id") == "Halo!"
    german = p.greeting("de", 16)                      # "Guten Tag" at four: "Selamat sore!"
    assert german["native"] == "Guten Tag!" and p.meaning(german["means"], "id") == "Selamat sore!"
    assert p.greeting("th", 9, "female")["translit"] == "Sawatdi kha!"
    assert p.greeting("th", 9, "male")["translit"] == "Sawatdi khrap!"
    assert p.greeting("th", 9)["translit"] == "Sawatdi khrap!"
    assert p.phrase("pt", "thanks", "female")["native"] == "Obrigada!"
    assert p.phrase("pt-PT", "toilet")["native"] == "Onde fica a casa de banho?"
    assert p.phrase("pt", "toilet")["native"] == "Onde fica o banheiro?"


@pytest.mark.parametrize("code, native, translit, text, spoken", [
    ("ja", "東京", "Tōkyō", "東京へようこそ！", "Tōkyō e yōkoso!"),
    ("ko", "서울", "Seoul", "서울에 오신 것을 환영합니다!", "Seoul-e osin geoseul hwanyeonghamnida!"),
    ("zh", "北京", "Běijīng", "欢迎来到北京！", "Huānyíng láidào Běijīng!"),
    ("th", "กรุงเทพฯ", "Krung Thep", "ยินดีต้อนรับสู่กรุงเทพฯ", "Yindi tonrap su Krung Thep!"),
    ("ar", "القاهرة", "al-Qahira", "أهلاً وسهلاً في القاهرة!", "Ahlan wa sahlan fi al-Qahira!"),
    ("tr", "İstanbul", "", "İstanbul'a hoş geldiniz!", "İstanbul'a hoş geldiniz!"),
    ("tr", "Ankara", "", "Ankara'ya hoş geldiniz!", "Ankara'ya hoş geldiniz!"),
    ("tr", "İzmir", "", "İzmir'e hoş geldiniz!", "İzmir'e hoş geldiniz!"),
    ("ru", "Москва", "Moskva", "Добро пожаловать в Москву!", "Dobro pozhalovat v Moskvu!"),
    ("ru", "Казань", "Kazan", "Добро пожаловать в Казань!", "Dobro pozhalovat v Kazan!"),
    ("pt", "Rio de Janeiro", "", "Bem-vindos ao Rio de Janeiro!", "Bem-vindos ao Rio de Janeiro!"),
    ("pt-PT", "Lisboa", "", "Bem-vindos a Lisboa!", "Bem-vindos a Lisboa!"),
    ("el", "Αθήνα", "Athína", "Καλώς ήρθατε στην Αθήνα!", "Kalós írthate stin Athína!"),
    ("el", "Βόλος", "Vólos", "Καλώς ήρθατε!", "Kalós írthate!"),
    ("pl", "Kraków", "", "Witamy w Krakowie!", "Witamy w Krakowie!"),
    ("pl", "Olsztyn", "", "Witamy!", "Witamy!"),
    ("uk", "Київ", "Kyiv", "Ласкаво просимо до Києва!", "Laskavo prosymo do Kyieva!"),
    ("fr", "Paris", "", "Bienvenue à Paris !", "Bienvenue à Paris !"),
    ("jv", "Yogyakarta", "", "Sugeng rawuh ing Yogyakarta!", "Sugeng rawuh ing Yogyakarta!"),
    ("ja", None, None, "ようこそ！", "Yōkoso!"),
])
def test_welcome_to_the_city(m, code, native, translit, text, spoken):
    found = m.phrases.welcome(code, native, translit)
    assert found["native"] == text
    assert m.phrases.spoken_form(found) == spoken


def test_meanings_in_the_users_language(m):
    p = m.phrases
    assert p.meaning("welcome", "id", city="Tokyo") == "Selamat datang di Tokyo!"
    assert p.meaning("welcome", "en", city="Tokyo") == "Welcome to Tokyo!"
    assert p.meaning({"id": "Satu", "en": "One"}, "id") == "Satu"
    assert p.meaning("thanks", "de") == "Thank you."          # other languages: English
    assert p.written_form(p.greeting("ja", 21)) == "Konbanwa! (こんばんは！)"
    assert p.written_form(p.greeting("fr", 21)) == "Bonsoir !"


def test_native_city_names(m):
    p = m.phrases
    assert p.native_city("JP", ["Tokyo"], "ja") == ("東京", "Tōkyō")
    assert p.native_city("SA", ["Mekkah"], "ar") == ("مكة المكرمة", "Makka al-Mukarrama")
    assert p.native_city("RU", ["Moskwa"], "ru") == ("Москва", "Moskva")
    assert p.native_city("US", ["Tokyo"], "ja") is None
    assert p.trim_native("東京都", "ja") == "東京"
    assert p.trim_native("서울특별시", "ko") == "서울"
    assert p.trim_native("부산광역시", "ko") == "부산"
    assert p.trim_native("北京市", "zh") == "北京"
    assert p.trim_native("大阪", "ja") == "大阪"
    assert p.turkish_dative("Bursa") == "Bursa'ya" and p.turkish_dative("Trabzon") == "Trabzon'a"
    assert p.russian_accusative("Самара") == "Самару"
    assert p.russian_accusative("Samara", translit=True) == "Samaru"


# ------------------------------------------------------------
# Finding the destination
# ------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Tokyo.", {"kind": "place", "name": "Tokyo"}),
    ("  new   york ", {"kind": "place", "name": "new york"}),
    ("Jepang", {"kind": "country", "cc": "JP"}),
    ("Japan!", {"kind": "country", "cc": "JP"}),
    ("Arab Saudi", {"kind": "country", "cc": "SA"}),
    ("mana saja", {"kind": "surprise"}),
    ("anywhere", {"kind": "surprise"}),
    ("rumah", {"kind": "home"}),
    ("home", {"kind": "home"}),
    ("", {"kind": "empty"}),
])
def test_what_a_trip_asks_for(m, text, expected):
    assert m.places.parse_query(text) == expected


class FakeGeocoder:
    """Canned Open-Meteo answers: searches keyed by (name, language), places
    looked up by id keyed by (id, language)."""

    def __init__(self, answers, by_id=None, fail=None):
        self.answers = answers
        self.by_id = by_id or {}
        self.urls = []
        self.fail = fail

    def __call__(self, url):
        import urllib.parse
        import core.place_search
        self.urls.append(url)
        if self.fail:
            raise core.place_search.FetchError(self.fail, "down")
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parts.query)
        if parts.path.endswith("/get"):
            found = self.by_id.get((int(query["id"][0]), query["language"][0]))
            if found is None:
                raise core.place_search.FetchError("service", "HTTP 404", status=404)
            return dict(found)
        key = (query["name"][0], query["language"][0])
        return {"results": [dict(r) for r in self.answers.get(key, [])]}


TOKYO_EN = geo("Tokyo", 35.6895, 139.69171, "JP", "Japan", "PPLC", 9733276, "Asia/Tokyo",
               "Tokyo", geo_id=1850147)
TOKYO_ID = dict(TOKYO_EN, country="Jepang", admin1="Prefektur Tokyo")
TOKYO_PNG = geo("Tokyo", -8.0, 147.0, "PG", "Papua Nugini", "PPL", 0, "Pacific/Port_Moresby",
                geo_id=2)
TOKYO_RESULTS = [TOKYO_ID, TOKYO_PNG]


def test_a_city_is_found_and_named_in_the_users_language(m):
    fetch = FakeGeocoder({("Tokyo", "en"): [TOKYO_EN, dict(TOKYO_PNG, country="Papua New Guinea")],
                          ("Tokyo", "id"): TOKYO_RESULTS},
                         by_id={(1850147, "id"): TOKYO_ID})
    dest = m.places.resolve("Tokyo", "id", fetch)
    assert (dest["name"], dest["name_en"], dest["country"], dest["country_code"],
            dest["timezone"], dest["region"]) == ("Tokyo", "Tokyo", "Jepang", "JP", "Asia/Tokyo",
                                                  "Prefektur Tokyo")
    assert dest["query"] == "Tokyo" and dest["feature"] == "PPLC" and dest["id"] == 1850147
    assert [u.split("?")[0] for u in fetch.urls] == [
        "https://geocoding-api.open-meteo.com/v1/search",
        "https://geocoding-api.open-meteo.com/v1/search",
        "https://geocoding-api.open-meteo.com/v1/get"]
    assert "source_language" not in dest
    fetch = FakeGeocoder({("Tokyo", "en"): [TOKYO_EN]})
    english = m.places.resolve("Tokyo", "en", fetch)
    assert english["country"] == "Japan" and len(fetch.urls) == 1        # nothing to look up


MECCA_EN = geo("Mecca", 21.42664, 39.82563, "SA", "Saudi Arabia", "PPLA", 1578722,
               "Asia/Riyadh", "Mecca Region", geo_id=104515)
MECCA_ID = dict(MECCA_EN, name="Mekkah", country="Arab Saudi")


def test_what_the_user_says_in_either_language(m):
    # "Mecca" in an Indonesian search finds only towns in America and Italy.
    fetch = FakeGeocoder({
        ("Mecca", "en"): [MECCA_EN, geo("Mecca", 33.57, -116.08, "US", "United States", "PPL",
                                        8577, geo_id=5371858)],
        ("Mecca", "id"): [geo("Mecca", 33.57, -116.08, "US", "AS", "PPL", 8577, geo_id=5371858),
                          geo("Mecca", 44.9, 7.9, "IT", "Italia", "PPL", 25, geo_id=3)]},
        by_id={(104515, "id"): MECCA_ID})
    dest = m.places.resolve("Mecca", "id", fetch)
    assert (dest["name"], dest["name_en"], dest["country"]) == ("Mekkah", "Mecca", "Arab Saudi")
    # "Mekkah" only an Indonesian search knows; its English name is looked up.
    fetch = FakeGeocoder({("Mekkah", "id"): [MECCA_ID]}, by_id={(104515, "en"): MECCA_EN})
    dest = m.places.resolve("Mekkah", "id", fetch)
    assert (dest["name"], dest["name_en"], dest["country_code"]) == ("Mekkah", "Mecca", "SA")
    # "New York": "Kota New York" in Indonesian, said without the "Kota".
    nyc = geo("New York", 40.71, -74.0, "US", "United States", "PPL", 8804190,
              "America/New_York", "New York", geo_id=5128581)
    fetch = FakeGeocoder({
        ("New York", "en"): [nyc],
        ("New York", "id"): [geo("York", 40.87, -97.59, "US", "AS", "PPLA2", 7864, geo_id=9)]},
        by_id={(5128581, "id"): dict(nyc, name="Kota New York", country="AS")})
    dest = m.places.resolve("New York", "id", fetch)
    assert (dest["name"], dest["country"]) == ("New York", "AS")


def test_home_country_wins_a_close_call(m):
    # "Bali" for an Indonesian is the island, not Bāli in India.
    bali_india = geo("Bāli", 22.64, 88.34, "IN", "India", "PPL", 296973, geo_id=1277539)
    island = geo("Pulau Bali", -8.33, 115.0, "ID", "Indonesia", "ISL", 4225384,
                 "Asia/Makassar", "Provinsi Bali", geo_id=1650535)
    answers = {("Bali", "en"): [bali_india],
               ("Bali", "id"): [bali_india, island,
                                geo("Bali", 35.0, 104.0, "CN", "Tiongkok", "PPLA4", 7101)]}
    fetch = FakeGeocoder(answers, by_id={(1650535, "en"): dict(island, name="Bali")})
    dest = m.places.resolve("Bali", "id", fetch)
    assert (dest["name"], dest["country_code"], dest["timezone"]) == ("Bali", "ID", "Asia/Makassar")
    assert m.places.resolve("Bali", "en", FakeGeocoder(answers))["country_code"] == "IN"


def test_names_without_their_administrative_word(m):
    p = m.places
    assert p.display_name("DI Yogyakarta", "Yogyakarta") == "Yogyakarta"
    assert p.display_name("Kota New York", "New York") == "New York"
    assert p.display_name("Kota Kinabalu", "Kota Kinabalu") == "Kota Kinabalu"
    assert p.display_name("Moskwa", "Moscow") == "Moskwa"
    singapore = geo("Singapore", 1.29, 103.85, "SG", "Singapore", "PPLC", 3547809,
                    "Asia/Singapore", geo_id=1880252)
    fetch = FakeGeocoder({("Singapura", "id"): [geo("Singapura", 1.36, 103.8, "SG", "Singapura",
                                                   "PCLI", 5638676)],
                          ("Singapore", "en"): [singapore]},
                         by_id={(1880252, "id"): dict(singapore, country="Singapura")})
    dest = m.places.resolve("Singapura", "id", fetch)       # the country, so its city
    assert dest["name"] == "Singapura" and dest["country"] == "Singapura"


def test_a_country_lands_in_its_best_known_city(m):
    fetch = FakeGeocoder({("Tokyo", "en"): [TOKYO_EN]}, by_id={(1850147, "id"): TOKYO_ID})
    dest = m.places.resolve("Jepang", "id", fetch)
    assert (dest["name"], dest["country"], dest["country_code"]) == ("Tokyo", "Jepang", "JP")
    assert dest["query"] == "Jepang"
    # A country the aliases don't know, found as a country by the geocoder.
    zagreb = geo("Zagreb", 45.81, 15.98, "HR", "Croatia", "PPLC", 698966, "Europe/Zagreb",
                 geo_id=3186886)
    fetch = FakeGeocoder({
        ("Kroasia", "id"): [geo("Kroasia", 45.17, 15.5, "HR", "Kroasia", "PCLI", 4000000)],
        ("Zagreb", "en"): [zagreb]}, by_id={(3186886, "id"): dict(zagreb, country="Kroasia")})
    dest = m.places.resolve("Kroasia", "id", fetch)
    assert (dest["name"], dest["country"]) == ("Zagreb", "Kroasia")
    assert m.places.COUNTRY_CITIES["SA"] == "Mecca" and m.places.COUNTRY_CITIES["US"] == "New York"


def test_airports_and_other_countries_are_skipped(m):
    fetch = FakeGeocoder({("Phnom Penh", "en"): [
        geo("Phnom Penh International Airport", 11.55, 104.84, "KH", "Cambodia", "AIRP"),
        geo("Phnom Penh", 11.56, 104.92, "KH", "Cambodia", "PPLC", 1573544, "Asia/Phnom_Penh")]})
    assert m.places.resolve("Phnom Penh", "en", fetch)["feature"] == "PPLC"
    results = m.places.parse_results({"results": TOKYO_RESULTS})
    assert m.places.choose(results, "Tokyo")["country_code"] == "JP"      # by population
    assert m.places.choose(results, "Tokyo", cc="PG")["country_code"] == "PG"
    assert m.places.choose(results, "Tokyo", cc="FR") is None


def test_a_surprise_trip_avoids_the_last_city(m):
    answers = {(name, "en"): [geo(name, 10.0, 10.0, cc, cc)]
               for name, cc in m.places.SURPRISE_CITIES}
    fetch = FakeGeocoder(answers)
    seen = set()
    rng = random.Random(3)
    last = None
    for _ in range(20):
        dest = m.places.resolve("mana saja", "id", fetch, rng=rng, avoid=last)
        assert dest["surprise"] != last
        last = dest["surprise"]
        seen.add(last)
    assert len(seen) > 5


def test_nothing_found_or_offline(m):
    with pytest.raises(m.places.ResolveError) as e:
        m.places.resolve("Atlantis", "id", FakeGeocoder({}))
    assert e.value.kind == "not_found"
    with pytest.raises(m.places.ResolveError) as e:
        m.places.resolve("Tokyo", "id", FakeGeocoder({}, fail="offline"))
    assert e.value.kind == "offline"


def test_the_local_name_is_the_same_city(m):
    by_id = FakeGeocoder({}, by_id={(1850147, "ja"): dict(TOKYO_EN, name="東京都")})
    assert m.places.localized_name(dict(TOKYO, id=1850147), "ja", by_id) == "東京都"
    # Without an id: a search, and only a result near the city counts.
    fetch = FakeGeocoder({("Tokyo", "ja"): [
        geo("東京都", 35.6895, 139.69171, "JP", "日本", "PPLC"),
        geo("Tokyo", -8.0, 147.0, "PG", "パプアニューギニア")]})
    assert m.places.localized_name(TOKYO, "ja", fetch) == "東京都"
    far = FakeGeocoder({("Tokyo", "ja"): [geo("Tokyo", -8.0, 147.0, "PG", "PNG")]})
    assert m.places.localized_name(TOKYO, "ja", far) is None
    assert m.places.localized_name(TOKYO, "ja", FakeGeocoder({}, fail="offline")) is None


def test_distance_and_flight_time(m):
    p = m.places
    km = p.distance_km(BATAM, TOKYO)
    assert 5250 < km < 5400
    assert p.round_km(km) == 5300
    assert p.round_minutes(p.flight_minutes(km)) == 7 * 60
    km = p.distance_km(BATAM, PARIS)
    assert p.round_km(km) == 10800 and p.round_minutes(p.flight_minutes(km)) == 14 * 60
    assert p.round_minutes(32) == 30 and p.round_minutes(1) == 5
    assert p.round_minutes(75) == 75 and p.round_minutes(95) == 90
    assert p.round_minutes(200) == 210 and p.round_minutes(415) == 420
    assert p.round_km(33) == 35 and p.round_km(847) == 850 and p.round_km(2) == 5
    assert p.flight_minutes(800) == 90


def test_home_is_the_main_place(m):
    place = {"id": "a1", "name": "Rumah", "lat": 1.13, "lon": 104.05, "city": "Batam",
             "timezone": "Asia/Jakarta"}
    assert m.places.home_from_place(place)["name"] == "Batam"
    assert m.places.home_from_place(dict(place, city=""))["name"] == "Rumah"
    assert m.places.home_from_place(None) is None


# ------------------------------------------------------------
# What is said
# ------------------------------------------------------------

def test_the_flight_in_indonesian(m, lang):
    t = m.text
    assert t.departure(TOKYO, BATAM) == (
        "Selamat datang di Hariku Air. Penerbangan dari Batam ke Tokyo, sekitar 5.300 kilometer, "
        "kurang lebih 7 jam. Kencangkan sabuk pengaman.")
    assert t.departure(TOKYO, BATAM, "Kapten Rafli").startswith("Kokpit siap, Kapten Rafli. ")
    assert t.departure(TOKYO, None) == ("Selamat datang di Hariku Air. Penerbangan ke Tokyo. "
                                        "Kencangkan sabuk pengaman.")
    surprise = dict(TOKYO, surprise="Tokyo")
    assert "Tujuan kejutan hari ini: Tokyo!" in t.departure(surprise, BATAM)
    weather = {"temperature": 18.4, "code": 53, "is_day": False}
    assert t.arrival(TOKYO, NOW, weather, BATAM) == (
        "Selamat datang di Tokyo, Jepang. Waktu setempat jam 21.30, Jumat malam, "
        "2 jam lebih cepat dari Batam. 18 derajat, gerimis.")
    assert t.arrival(PARIS, NOW, None, BATAM) == (
        "Selamat datang di Paris, Prancis. Waktu setempat jam 14.30, Jumat siang, "
        "5 jam lebih lambat dari Batam.")
    assert t.arrival(SINGAPURA, NOW, None, None).startswith("Selamat datang di Singapura. ")


def test_the_flight_in_english(m, lang):
    lang("en")
    t = m.text
    assert t.departure(TOKYO, BATAM) == (
        "Welcome aboard Hariku Air. Flight from Batam to Tokyo, about 5,300 kilometres, "
        "roughly 7 hours. Please fasten your seat belt.")
    weather = {"temperature": 18.4, "code": 61, "is_day": False}
    assert t.arrival(TOKYO, NOW, weather, BATAM) == (
        "Welcome to Tokyo, Jepang. Local time 21:30, Friday night, 2 hours ahead of Batam. "
        "18 degrees, light rain.")


@pytest.mark.parametrize("minutes, id_text, en_text", [
    (30, "30 menit", "30 minutes"),
    (60, "1 jam", "1 hour"),
    (75, "1 jam 15 menit", "1 hour 15 minutes"),
    (90, "satu setengah jam", "an hour and a half"),
    (150, "2 setengah jam", "2 and a half hours"),
    (420, "7 jam", "7 hours"),
    (135, "2 jam 15 menit", "2 hours 15 minutes"),
])
def test_durations_in_words(m, lang, minutes, id_text, en_text):
    assert m.text.duration(minutes) == id_text
    lang("en")
    assert m.text.duration(minutes) == en_text


def test_local_time_and_its_difference(m, lang):
    t = m.text
    delhi = {"name": "New Delhi", "country": "India", "latitude": 28.6, "longitude": 77.2,
             "timezone": "Asia/Kolkata"}
    assert t.time_there(delhi, NOW, BATAM) == (
        "Di New Delhi sekarang jam 18.00, Jumat malam, satu setengah jam lebih lambat dari Batam.")
    jakarta = {"name": "Jakarta", "country": "Indonesia", "latitude": -6.2, "longitude": 106.8,
               "timezone": "Asia/Jakarta"}
    assert t.time_there(jakarta, NOW, BATAM).endswith("sama dengan waktu Batam.")
    assert t.time_there(TOKYO, NOW) == "Di Tokyo sekarang jam 21.30, Jumat malam."
    early = datetime.datetime(2026, 9, 25, 17, 30, tzinfo=UTC)          # 02:30 in Tokyo
    assert "Sabtu dini hari" in t.time_there(TOKYO, early, BATAM)
    assert t.time_home(NOW, BATAM) == "Kamu di Batam, sekarang jam 19.30."
    lang("en")
    assert "Saturday night" in t.time_there(TOKYO, early, BATAM)
    morning = datetime.datetime(2026, 9, 24, 23, 0, tzinfo=UTC)          # 08:00 in Tokyo
    assert "Friday morning" in t.time_there(TOKYO, morning, BATAM)


def test_the_weather_in_words(m, lang):
    t = m.text
    assert t.weather_text({"temperature": 27.6, "code": 95}) == "28 derajat, badai petir"
    assert t.weather_text({"temperature": -2.2, "code": 1234}) == "-2 derajat"
    assert t.weather_text(None) == ""
    for code in t.KNOWN_CODES:
        assert t.condition(code) != f"wmo_{code}"


def test_where_am_i(m, lang):
    t = m.text
    assert t.where(TOKYO, NOW, BATAM, {"name": "J-Wave"}) == (
        "Kamu di Tokyo, Jepang, sekitar 5.300 kilometer dari Batam. Waktu setempat jam 21.30. "
        "Di radio: J-Wave.")
    assert t.where(TOKYO, NOW) == "Kamu di Tokyo, Jepang. Waktu setempat jam 21.30."


def test_both_languages_have_the_same_keys(m):
    def keys(code):
        with open(os.path.join(EXT_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            return set(json.load(f)["messages"])
    assert keys("en") == keys("id")
    used = {f"wmo_{c}" for c in m.text.KNOWN_CODES}
    used |= {key for parts in m.text.PARTS_OF_DAY.values() for _start, key in parts}
    assert used <= keys("en")


# ------------------------------------------------------------
# Weather and Wikipedia
# ------------------------------------------------------------

def test_the_weather_request_and_answer(m):
    n = m.net
    url = n.weather_url(35.68951234, 139.69171234)
    assert "latitude=35.69" in url and "longitude=139.69" in url and "35.6895" not in url
    found = n.parse_weather({"timezone": "Asia/Tokyo", "current": {
        "temperature_2m": 18.4, "weather_code": 53, "is_day": 0}})
    assert found == {"temperature": 18.4, "code": 53, "is_day": False, "timezone": "Asia/Tokyo"}
    with pytest.raises(n.NetError):
        n.parse_weather({"current": {}})


def test_summaries_are_tidied(m):
    text = ("Tokyo , nama resminya Metropolis Tokyo ( ), adalah ibu kota Jepang. Kota ini besar. "
            "Kalimat ketiga. Kalimat keempat.")
    assert m.net.clean_extract(text) == ("Tokyo, nama resminya Metropolis Tokyo, adalah ibu kota "
                                         "Jepang. Kota ini besar. Kalimat ketiga.")


class FakeWiki:
    def __init__(self, pages, fail=None):
        self.pages = pages
        self.urls = []
        self.fail = fail

    def __call__(self, url):
        import urllib.parse
        import core.place_search
        self.urls.append(url)
        if self.fail:
            raise core.place_search.FetchError(self.fail, "down")
        lang = url.split("//")[1].split(".")[0]
        title = urllib.parse.unquote(url.rsplit("/", 1)[1]).replace("_", " ")
        page = self.pages.get((lang, title))
        if page is None:
            raise core.place_search.FetchError("service", "HTTP 404", status=404)
        return page


def _page(title, extract, lat=None, lon=None, kind="standard"):
    page = {"title": title, "extract": extract, "type": kind}
    if lat is not None:
        page["coordinates"] = {"lat": lat, "lon": lon}
    return page


def test_a_city_summary_prefers_the_users_wikipedia(m):
    n = m.net
    pages = {("id", "Tokyo"): _page("Tokyo", "Tokyo adalah ibu kota Jepang.", 35.69, 139.69),
             ("en", "Tokyo"): _page("Tokyo", "Tokyo is the capital of Japan.", 35.69, 139.69)}
    fetch = FakeWiki(pages)
    assert n.city_summary(TOKYO, "id", ["Tokyo"], ["Tokyo"], fetch) == {
        "text": "Tokyo adalah ibu kota Jepang.", "lang": "id", "title": "Tokyo"}
    assert fetch.urls == ["https://id.wikipedia.org/api/rest_v1/page/summary/Tokyo"]
    # No Indonesian page (or one about something far away): English.
    pages[("id", "Tokyo")] = _page("Tokyo", "Tokyo di Papua.", -8.0, 147.0)
    found = n.city_summary(TOKYO, "id", ["Tokyo"], ["Tokyo"], FakeWiki(pages))
    assert found["lang"] == "en"
    pages[("en", "Tokyo")] = _page("Tokyo (disambiguation)", "Tokyo may refer to", kind="disambiguation")
    with pytest.raises(n.NetError) as e:
        n.city_summary(TOKYO, "id", ["Tokyo"], ["Tokyo"], FakeWiki(pages))
    assert e.value.kind == "not_found"
    with pytest.raises(n.NetError) as e:
        n.city_summary(TOKYO, "id", ["Tokyo"], ["Tokyo"], FakeWiki(pages, fail="offline"))
    assert e.value.kind == "offline"


def test_a_country_summary(m):
    pages = {("id", "Jepang"): _page("Jepang", "Jepang adalah negara kepulauan di Asia Timur.")}
    found = m.net.country_summary("Jepang", "id", FakeWiki(pages))
    assert found["text"].startswith("Jepang adalah") and found["lang"] == "id"


def test_the_cache_forgets_old_entries(m):
    clock = {"now": 1000.0}
    cache = m.net.Cache(60, max_entries=2, clock=lambda: clock["now"])
    cache.put("a", 1)
    cache.put("b", [2])
    cache.put("c", {"x": 3})
    assert cache.get("a") is None and cache.get("b") == [2]
    saved = json.loads(json.dumps(cache.to_dict()))
    again = m.net.Cache(60, clock=lambda: clock["now"])
    again.load(saved)
    assert again.get("c") == {"x": 3}
    clock["now"] += 61
    assert again.get("c") is None and cache.to_dict() == {}
    again.load("broken")
    assert again.get("b") is None
    assert m.net.point_key(TOKYO, "id:") == "id:35.69,139.69"


# ------------------------------------------------------------
# Radio Browser
# ------------------------------------------------------------

def station(name, codec="MP3", url=None, cc="JP", votes=10, clicks=1, state="", lat=None, lon=None,
            hls=0, uuid=None):
    return {"name": name, "codec": codec, "url_resolved": url or f"http://radio.example/{name}",
            "countrycode": cc, "votes": votes, "clickcount": clicks, "state": state,
            "geo_lat": lat, "geo_long": lon, "hls": hls, "stationuuid": uuid or name,
            "bitrate": 128}


def test_only_playable_stations(m):
    s = m.stations
    assert s.playable(s.clean_station(station("A")))
    assert s.playable(s.clean_station(station("B", codec="AAC+")))
    assert not s.playable(s.clean_station(station("C", codec="OGG")))
    assert not s.playable(s.clean_station(station("D", hls=1)))
    assert not s.playable(s.clean_station(station("E", url="http://x/live.m3u8")))
    assert s.clean_station(station("F", url="ftp://x")) is None
    assert s.clean_station("junk") is None


def test_stations_of_the_city_come_first(m):
    s = m.stations
    raw = [station("Big National", votes=50000, clicks=500),
           station("Gotanno FM", lat=35.76, lon=139.81, votes=139, clicks=71),
           station("Tokyo Jazz", votes=20, clicks=2),
           station("Shonan Beach FM", state="Kanagawa", votes=232, clicks=23),
           station("Big National", url="http://mirror/big", votes=1),        # same name again
           station("Paris Hits", cc="FR", votes=99999),                       # another country
           station("Ogg Radio", codec="OGG", state="Tokyo", votes=9999)]
    ranked = s.rank([s.clean_station(r) for r in raw], TOKYO, ["Tokyo"])
    assert [r["name"] for r in ranked] == ["Gotanno FM", "Tokyo Jazz", "Big National",
                                           "Shonan Beach FM"]


def test_the_local_language_comes_first(m):
    s = m.stations

    def french(name, language, votes, **kw):
        raw = station(name, cc="FR", votes=votes, state="Paris", **kw)
        raw["language"] = language
        return s.clean_station(raw)

    found = [french("RFI-Chinese", "chinese", 900), french("NRJ Paris", "french", 400),
             french("Nostalgie", "", 300), french("FIP", "French,English", 200)]
    ranked = s.rank(found, PARIS, ["Paris"], languages=s.RADIO_LANGUAGES["fr"])
    assert [r["name"] for r in ranked] == ["NRJ Paris", "Nostalgie", "FIP", "RFI-Chinese"]
    assert [r["name"] for r in s.rank(found, PARIS, ["Paris"])][0] == "RFI-Chinese"
    for code in m.phrases.LANGUAGES:
        assert s.RADIO_LANGUAGES.get(code), code


class FakeRadioBrowser:
    def __init__(self, stations_by_query, servers=None, down=()):
        self.stations = stations_by_query
        self.servers = servers
        self.down = set(down)
        self.urls = []

    def __call__(self, url):
        import urllib.parse
        import core.place_search
        self.urls.append(url)
        parts = urllib.parse.urlsplit(url)
        if parts.netloc == "all.api.radio-browser.info":
            if self.servers is None:
                raise core.place_search.FetchError("offline", "no DNS")
            return [{"name": s} for s in self.servers]
        if parts.netloc in self.down:
            raise core.place_search.FetchError("offline", "down")
        if parts.path.startswith("/json/url/"):
            return {"ok": True}
        query = dict(urllib.parse.parse_qsl(parts.query))
        key = "geo" if "geo_lat" in query else query.get("countrycode")
        return list(self.stations.get(key, []))


def test_radio_browser_mirrors_and_what_is_sent(m):
    s = m.stations
    fake = FakeRadioBrowser({"geo": [station("Gotanno FM", lat=35.76, lon=139.81)],
                             "JP": [station("J-Wave", votes=900), station("Gotanno FM", lat=35.76,
                                                                          lon=139.81)]},
                            servers=["de1.api.radio-browser.info", "de2.api.radio-browser.info",
                                     "evil.example.com"], down={"de1.api.radio-browser.info"})
    browser = s.RadioBrowser(fetch=fake, rng=random.Random(1))
    assert sorted(browser.servers()) == ["de1.api.radio-browser.info", "de2.api.radio-browser.info"]
    found = browser.stations_for(TOKYO, ["Tokyo"])
    assert [f["name"] for f in found] == ["Gotanno FM", "J-Wave"]
    searches = [u for u in fake.urls if "/json/stations/search" in u]
    assert all("hidebroken=true" in u and "order=clickcount" in u for u in searches)
    assert any("geo_lat=35.69" in u and "geo_long=139.69" in u for u in searches)
    assert any("countrycode=JP" in u for u in searches)
    for url in fake.urls:                       # never the user's own place
        assert "104.05" not in url and "1.13" not in url
    browser.count_click("abc-123")
    assert fake.urls[-1].endswith("/json/url/abc-123")
    assert "HarikuV2" in s.USER_AGENT and "World Trip" in s.USER_AGENT


def test_radio_browser_falls_back_to_its_own_list(m):
    s = m.stations
    fake = FakeRadioBrowser({"JP": [station("J-Wave")]}, servers=None)
    browser = s.RadioBrowser(fetch=fake, rng=random.Random(2))
    assert sorted(browser.servers()) == sorted(s.FALLBACK_SERVERS)
    all_down = FakeRadioBrowser({}, servers=None, down=set(s.FALLBACK_SERVERS))
    with pytest.raises(s.StationError) as e:
        s.RadioBrowser(fetch=all_down).stations_for(TOKYO, ["Tokyo"])
    assert e.value.kind == "offline"


# ------------------------------------------------------------
# Native voices
# ------------------------------------------------------------

EDGE = [{"id": "ja-JP-NanamiNeural", "name": "Nanami", "language": "ja-JP", "gender": "female"},
        {"id": "ja-JP-KeitaNeural", "name": "Keita", "language": "ja-JP", "gender": "male"},
        {"id": "zh-HK-HiuMaanNeural", "name": "HiuMaan", "language": "zh-HK", "gender": "female"},
        {"id": "th-TH-PremwadeeNeural", "name": "Premwadee", "language": "th-TH",
         "gender": "female"},
        {"id": "fr-CA-SylvieNeural", "name": "Sylvie", "language": "fr-CA", "gender": "female"},
        {"id": "fr-FR-DeniseNeural", "name": "Denise", "language": "fr-FR", "gender": "female"}]
PIPER = [{"id": "fr_FR-siwis-medium", "name": "Siwis", "language": "fr-FR", "gender": ""},
         {"id": "ru_RU-irina-medium", "name": "Irina", "language": "ru_RU", "gender": ""}]
WINDOWS = [{"id": "HKLM\\Haruka", "name": "Haruka", "language": "ja-JP", "gender": "female"},
           {"id": "HKLM\\Andika", "name": "Andika", "language": "id-ID", "gender": "male"}]


def test_edge_then_piper_then_windows(m):
    v = m.voices
    everything = {"edge": EDGE, "piper": PIPER, "windows": WINDOWS}
    assert v.pick_for(everything, "ja", "JP")["id"] == "ja-JP-KeitaNeural"      # by name
    assert v.pick_for(everything, "ja", "JP")["provider"] == "edge"
    assert v.pick_for(everything, "fr", "CA")["id"] == "fr-CA-SylvieNeural"
    assert v.pick_for(everything, "fr", "FR")["id"] == "fr-FR-DeniseNeural"
    assert v.pick_for(everything, "ru", "RU")["provider"] == "piper"
    assert v.pick_for({"windows": WINDOWS}, "ja", "JP")["name"] == "Haruka"
    assert v.pick_for(everything, "yue", "HK")["id"] == "zh-HK-HiuMaanNeural"
    assert v.pick_for(everything, "zh", "CN") is None          # a Cantonese voice won't do
    assert v.pick_for(everything, "ko", "KR") is None
    assert v.pick_for(everything, "xx", "") is None


def test_the_voice_book_lists_once_and_skips_what_fails(m):
    listed = []

    def list_voices(provider):
        listed.append(provider)
        if provider == "piper":
            raise RuntimeError("not installed")
        return {"edge": EDGE, "windows": WINDOWS}[provider]

    clock = {"now": 0.0}
    book = m.voices.VoiceBook(lambda: ["windows", "edge", "piper", "other"],
                              lambda provider: provider != "other", list_voices,
                              clock=lambda: clock["now"])
    assert set(book.voices()) == {"edge", "windows"}
    assert book.for_language("th", "TH")["name"] == "Premwadee"
    assert listed == ["edge", "piper", "windows"]            # asked once
    clock["now"] += 601
    book.voices()
    assert len(listed) == 6


# ------------------------------------------------------------
# Any key skips the flight
# ------------------------------------------------------------

def test_any_key_but_not_the_one_that_started_it(m):
    state = {"tick": 100, "held": False, "cursor": (5, 5), "now": 0.0}
    watch = m.keys.KeyWatch(last_input=lambda: state["tick"], keys_down=lambda: state["held"],
                            cursor=lambda: state["cursor"], clock=lambda: state["now"])
    assert not watch.pressed()
    state.update(tick=101, now=0.3)                  # Enter let go right after starting
    assert not watch.pressed()
    state.update(tick=102, held=True, now=1.5)       # still holding it
    assert not watch.pressed()
    state.update(tick=103, held=False, now=4.0, cursor=(50, 60))   # the mouse moved
    assert not watch.pressed()
    state.update(tick=104, now=5.0)                  # a key
    assert watch.pressed()


# ------------------------------------------------------------
# The radio player (a fake Media Foundation)
# ------------------------------------------------------------

class FakeBackend:
    """MFPlay as the player sees it: open() may fail; the state goes EMPTY,
    STOPPED (item set), PLAYING (after play()); `script` changes it on a poll."""

    def __init__(self, player, fail=None, drop_after=None, stop_after=None):
        self.player = player
        self.fail = fail
        self.state_value = 0
        self.volumes = []
        self.polls = 0
        self.drop_after = drop_after
        self.stop_after = stop_after
        self.closed = False
        self.played = False

    def open(self, url):
        if self.fail:
            raise self.player_module.RadioError(self.fail)
        self.state_value = 1

    def state(self):
        self.polls += 1
        if self.played and self.drop_after is not None and self.polls > self.drop_after:
            return 1
        if self.played and self.stop_after is not None and self.polls > self.stop_after:
            self.player.stop()
        return self.state_value

    def play(self):
        self.played = True
        self.state_value = 2

    def set_volume(self, level):
        self.volumes.append(round(level, 3))

    def pump(self):
        pass

    def close(self):
        self.closed = True


def make_player(m, **backend_kwargs):
    clock = {"now": 0.0}
    backends = []
    events = []

    def factory():
        backend = FakeBackend(player, **backend_kwargs)
        backend.player_module = m.radio
        backends.append(backend)
        return backend

    def sleep(seconds):
        clock["now"] += seconds

    player = m.radio.RadioPlayer(backend_factory=factory, supported=lambda: True,
                                 clock=lambda: clock["now"], sleep=sleep,
                                 start_thread=lambda target, session: target(session))
    return player, backends, events, clock


def test_a_station_plays_fades_in_ducks_and_stops(m):
    player, backends, events, clock = make_player(m, stop_after=40)
    player.set_volume(50)
    player.play("http://radio.example/live", on_event=lambda k, d: events.append(k))
    backend = backends[0]
    assert events == ["connecting", "playing", "stopped"]
    assert backend.volumes[0] == 0.0 and max(backend.volumes) == 0.5    # a fade in, to 50%
    assert all(b - a <= m.radio.RAMP_STEP + 1e-9 for a, b in zip(backend.volumes, backend.volumes[1:]))
    assert backend.closed and not player.is_active()
    player.set_ducked(True)
    assert player.target_level() == pytest.approx(0.5 * m.radio.DUCK_FACTOR)
    player.set_volume(250)
    assert player.volume == 100


def test_a_station_that_fails_or_drops(m):
    player, backends, events, clock = make_player(m, fail="offline")
    player.play("http://dead.example/", on_event=lambda k, d: events.append((k, d)))
    assert events == [("connecting", "http://dead.example/"), ("error", "offline")]
    assert backends[0].closed and not player.is_active()
    player, backends, events, clock = make_player(m, drop_after=10)
    player.play("http://flaky.example/", on_event=lambda k, d: events.append(k))
    assert events == ["connecting", "playing", "dropped"] and not player.is_active()
    player = m.radio.RadioPlayer(supported=lambda: False)
    player.play("http://x/", on_event=lambda k, d: events.append((k, d)))
    assert events[-1] == ("error", "unsupported") and not player.is_active()


def test_a_newer_station_silences_the_older_one(m):
    player = m.radio.RadioPlayer(backend_factory=lambda: None, supported=lambda: True,
                                 start_thread=lambda target, session: None)
    heard = []
    player.play("http://one/", on_event=lambda k, d: heard.append(("one", k)))
    first = player._session
    player.play("http://two/", on_event=lambda k, d: heard.append(("two", k)))
    assert first.stopped.is_set() and player._session is not first
    player._emit(first, "playing", "http://one/")          # too late: not heard
    assert heard == []
    player.stop()
    assert not player.is_active()


def test_media_foundation_errors_have_names(m):
    assert m.radio.error_kind(0xC00D36C4) == "format"
    assert m.radio.error_kind(0x80072EE2) == "offline"
    assert m.radio.error_kind(0xC00D001A) == "not_found"
    assert m.radio.error_kind(0x80004005) == "open"
    assert isinstance(m.radio.is_supported(), bool)       # only loads the DLL


# ------------------------------------------------------------
# The trip, on a fake clock
# ------------------------------------------------------------

VOICE_JA = {"provider": "edge", "id": "ja-JP-NanamiNeural", "name": "Nanami",
            "language": "ja-JP", "gender": "female"}
VOICE_TH = {"provider": "edge", "id": "th-TH-PremwadeeNeural", "name": "Premwadee",
            "language": "th-TH", "gender": "female"}
STATIONS = [{"uuid": "u1", "name": "J-Wave", "url": "http://jwave/", "latitude": None,
             "longitude": None, "state": "Tokyo"},
            {"uuid": "u2", "name": "Gotanno FM", "url": "http://gotanno/", "latitude": 35.76,
             "longitude": 139.81, "state": "Tokyo"},
            {"uuid": "u3", "name": "Ottava", "url": "http://ottava/", "latitude": None,
             "longitude": None, "state": ""}]


class FakeTimer:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeRadio:
    def __init__(self):
        self.plays = []
        self.stops = 0
        self.volume = None
        self.ducked = []
        self.on_event = None
        self.active = False

    def play(self, url, volume=None, on_event=None):
        self.plays.append((url, volume))
        self.on_event = on_event
        self.active = True

    def stop(self):
        self.stops += 1
        self.active = False

    def set_volume(self, volume):
        self.volume = volume

    def set_ducked(self, ducked):
        self.ducked.append(ducked)

    def is_active(self):
        return self.active

    def emit(self, kind, detail=None):
        self.on_event(kind, detail)


class FakeServices:
    """Everything a trip uses: a fake clock and timers, speech and sounds
    recorded, network answers canned (run() is synchronous)."""

    SOUNDS = {"chime": 1.4, "engine": 7.0}

    def __init__(self, m, **settings):
        self.m = m
        self.now = 1000.0
        self._timers = []
        self._seq = 0
        self.log = []
        self.holds = []
        self.voiced = False
        self.busy_until = 0.0
        self.native_ok = True
        self.native_seconds = 2.0
        self.radio = FakeRadio()
        self.supported = True
        self._settings = dict(departure=True, engine=True, radio=True, radio_volume=35,
                              native_voices=True)
        self._settings.update(settings)
        self.trips = 0
        self.home_place = dict(BATAM)
        self.destinations = {"Tokyo": TOKYO, "Paris": PARIS, "Bangkok": BANGKOK,
                             "Denpasar": DENPASAR, "Batam": dict(BATAM, name="Batam")}
        self.errors = {}
        self.weather_value = {"temperature": 18.4, "code": 53, "is_day": False}
        self.voice_by_language = {"ja": VOICE_JA, "th": VOICE_TH}
        self.station_list = list(STATIONS)
        self.localized = {("Tokyo", "en"): "Tokyo", ("Tokyo", "ja"): "東京都"}
        self.summaries = {}
        self.providers = {"edge"}
        self.keys_pressed = False
        self.clicks = []
        self.volume_changes = []
        self.resolved = []
        self.station_requests = []

    # time
    def utcnow(self):
        return NOW + datetime.timedelta(seconds=self.now - 1000.0)

    def monotonic(self):
        return self.now

    def call_later(self, seconds, fn):
        timer = FakeTimer()
        self._seq += 1
        self._timers.append((self.now + seconds, self._seq, fn, timer))
        return timer

    def call_after(self, fn, *args):
        fn(*args)

    def run(self, work, done):
        try:
            result = work()
        except Exception as e:
            done(None, e)
            return
        done(result, None)

    def advance(self, seconds, step=0.05):
        end = self.now + seconds
        while True:
            due = [t for t in self._timers if t[0] <= end and not t[3].cancelled]
            if not due:
                break
            due.sort(key=lambda t: (t[0], t[1]))
            first = due[0]
            self._timers.remove(first)
            self.now = max(self.now, first[0])
            first[2]()
        self.now = end

    # speech and sounds
    def say(self, text, interrupt=False):
        self.log.append(("say", text))
        if self.voiced:
            self.busy_until = self.now + 2.0
        return self.voiced

    def voice_busy(self):
        return self.now < self.busy_until

    def stop_voice(self):
        self.log.append(("stop_voice",))
        self.busy_until = 0.0

    def speak_native(self, text, voice, on_done):
        self.log.append(("native", text, voice["id"]))
        if not self.native_ok:
            return False
        self.call_later(self.native_seconds, lambda: on_done(None))
        return True

    def show(self, text):
        self.log.append(("show", text))

    def hold(self, seconds):
        self.holds.append(seconds)

    def play_sound(self, name):
        self.log.append(("sound", name))
        return self.SOUNDS[name]

    def stop_sound(self, name):
        self.log.append(("stop_sound", name))

    def key_watch(self):
        return types.SimpleNamespace(pressed=lambda: self.keys_pressed)

    def has_provider(self, provider_id):
        return provider_id in self.providers

    def radio_supported(self):
        return self.supported

    # settings and the user
    def settings(self):
        return dict(self._settings)

    def save_radio_volume(self, volume):
        self._settings["radio_volume"] = volume

    def hariku_volume(self, step):
        self.volume_changes.append(step)

    def home(self):
        return dict(self.home_place) if self.home_place else None

    def addressed(self):
        return ""

    def count_trip(self):
        self.trips += 1

    def trips_taken(self):
        return self.trips

    # the network
    def resolve(self, text, avoid=None):
        self.resolved.append((text, avoid))
        if text in self.errors:
            raise self.m.places.ResolveError(self.errors[text])
        if text in ("mana saja", "anywhere"):
            return dict(TOKYO, surprise="Tokyo", query=text)
        return dict(self.destinations[text], query=text)

    def localized_name(self, dest, code):
        return self.localized.get((dest["name"], code))

    def weather(self, dest):
        if isinstance(self.weather_value, Exception):
            raise self.weather_value
        return self.weather_value

    def native_voice(self, code, country_code):
        return self.voice_by_language.get(code)

    def stations(self, dest, names, language=None):
        self.station_requests.append((dest["name"], language))
        if isinstance(self.station_list, Exception):
            raise self.station_list
        return list(self.station_list)

    def summary(self, dest, names, english_names):
        found = self.summaries.get(dest["name"])
        if isinstance(found, Exception) or found is None:
            raise found or self.m.net.NetError("not_found")
        return found

    def country_summary(self, country):
        return {"text": f"{country} adalah negara.", "lang": "id", "title": country}

    def count_click(self, uuid):
        self.clicks.append(uuid)

    # checking
    def said(self):
        return [entry[1] for entry in self.log if entry[0] == "say"]

    def kinds(self):
        return [entry[0] if entry[0] != "sound" else f"sound:{entry[1]}" for entry in self.log]


@pytest.fixture
def trip(m, lang):
    def make(**settings):
        sv = FakeServices(m, **settings)
        manager = m.trip.TripManager(sv, rng=random.Random(7))
        return sv, manager
    return make


def test_batam_to_tokyo_from_take_off_to_the_radio(m, trip):
    sv, manager = trip()
    manager.start("Tokyo")
    assert manager.trip.phase == "departing"
    sv.advance(60)
    assert sv.kinds()[:4] == ["sound:chime", "say", "sound:engine", "sound:chime"]
    said = sv.said()
    assert said[0].startswith("Selamat datang di Hariku Air. Penerbangan dari Batam ke Tokyo")
    assert said[1] == ("Selamat datang di Tokyo, Jepang. Waktu setempat jam 21.30, Jumat malam, "
                       "2 jam lebih cepat dari Batam. 18 derajat, gerimis.")
    # The greeting in a Japanese voice, shown in Last result, then what it means.
    assert ("native", "こんばんは！ 東京へようこそ！", "ja-JP-NanamiNeural") in sv.log
    assert ("show", "Konbanwa! Tōkyō e yōkoso! (こんばんは！ 東京へようこそ！)") in sv.log
    assert said[2] == ("Konbanwa! Tōkyō e yōkoso! Artinya: Selamat malam! "
                       "Selamat datang di Tokyo!")
    # The radio: the first station, quietly, then what's on and a hint (first trips).
    assert sv.radio.plays == [("http://jwave/", 35)]
    assert manager.trip.phase == "exploring"
    sv.radio.emit("playing", "http://jwave/")
    sv.advance(30)
    assert sv.said()[3:] == ["Kamu mendengarkan J-Wave dari Tokyo.",
                             "Coba bilang: ceritakan tentang kota ini, ajari aku satu kalimat, "
                             "ganti stasiun, atau pulang."]
    assert sv.clicks == ["u1"] and manager.trip.playing["name"] == "J-Wave"
    assert all(seconds > 0 for seconds in sv.holds)       # Aruna's Last result stays open


def test_batam_to_paris_in_english_with_hariku_voice(m, trip, lang):
    lang("en")
    sv, manager = trip()
    sv.voiced = True                                  # Hariku Voice: wait until it's done
    sv.localized[("Paris", "fr")] = "Paris"
    sv.station_list = [{"uuid": "f", "name": "FIP", "url": "http://fip/", "latitude": None,
                        "longitude": None, "state": "Paris"}]
    manager.start("Paris")
    sv.advance(90)
    said = sv.said()
    assert said[0] == ("Welcome aboard Hariku Air. Flight from Batam to Paris, about 10,800 "
                       "kilometres, roughly 14 hours. Please fasten your seat belt.")
    assert said[1].startswith("Welcome to Paris, Prancis. Local time 14:30, Friday afternoon, "
                              "5 hours behind Batam.")
    # No French voice: the greeting and its meaning in the user's own voice, and a hint.
    assert said[2].startswith("Bonjour ! Bienvenue à Paris ! That means: Hello! Welcome to Paris!")
    assert "Edge Voices" not in said[2]               # Edge Voices is there, just no French voice
    sv.radio.emit("playing", "http://fip/")
    sv.advance(10)
    assert "You're listening to FIP, from Paris." in sv.said()


def test_departure_and_engine_can_be_turned_off(m, trip):
    sv, manager = trip(departure=False)
    manager.start("Tokyo")
    sv.advance(60)
    assert sv.kinds()[:2] == ["sound:chime", "say"]
    assert sv.said()[0].startswith("Selamat datang di Tokyo, Jepang.")
    assert ("sound", "engine") not in sv.log
    sv, manager = trip(engine=False)
    manager.start("Tokyo")
    sv.advance(60)
    assert ("sound", "engine") not in sv.log and sv.said()[0].startswith("Selamat datang di Hariku")


def test_any_key_skips_to_the_arrival(m, trip):
    sv, manager = trip()
    manager.start("Tokyo")
    sv.advance(3)                                     # the captain is talking
    sv.keys_pressed = True
    sv.advance(0.5)
    assert ("stop_sound", "engine") in sv.log and ("stop_voice",) in sv.log
    sv.keys_pressed = False
    sv.advance(10)
    assert any(s.startswith("Selamat datang di Tokyo, Jepang.") for s in sv.said())
    assert ("sound", "engine") not in sv.log          # skipped before the engines


def test_skip_command(m, trip):
    sv, manager = trip()
    manager.skip()
    assert sv.said() == ["Kamu sedang tidak dalam penerbangan."]
    manager.start("Tokyo")
    sv.advance(2)
    assert manager.skip() is True
    sv.advance(40)
    assert manager.trip.phase == "exploring"
    manager.skip()
    assert sv.said()[-1] == "Kita sudah mendarat."


def test_a_trip_at_home_or_nowhere(m, trip):
    sv, manager = trip()
    sv.errors["Atlantis"] = "not_found"
    manager.start("Atlantis")
    assert sv.said() == ["Aku tidak menemukan tempat bernama Atlantis."] and manager.trip is None
    sv.errors["Tokyo"] = "offline"
    manager.start("Tokyo")
    assert sv.said()[-1].startswith("Aku tidak bisa mencari tempat sekarang.")
    sv.errors.pop("Tokyo")
    manager.start("Batam")
    assert sv.said()[-1] == "Kamu sudah di Batam!"
    manager.start("rumah")
    assert sv.said()[-1] == "Kamu sudah di rumah."


def test_without_a_main_place(m, trip):
    sv, manager = trip()
    sv.home_place = None
    manager.start("Tokyo")
    sv.advance(60)
    assert sv.said()[0] == ("Selamat datang di Hariku Air. Penerbangan ke Tokyo. "
                            "Kencangkan sabuk pengaman.")
    assert sv.said()[1] == ("Selamat datang di Tokyo, Jepang. Waktu setempat jam 21.30, "
                            "Jumat malam. 18 derajat, gerimis.")


def test_no_native_voice_reads_the_greeting_and_hints_at_edge_voices(m, trip):
    sv, manager = trip()
    sv.voice_by_language = {}
    sv.providers = set()
    manager.start("Tokyo")
    sv.advance(60)
    greeting = sv.said()[2]
    assert greeting.startswith("Konbanwa! Tōkyō e yōkoso! Artinya: Selamat malam!")
    assert greeting.endswith("pasang Edge Voices dari Toko Ekstensi.")
    assert not any(entry[0] in ("native", "show") for entry in sv.log)
    manager.start("Tokyo")                            # the hint is said once
    sv.advance(60)
    assert "Edge Voices" not in sv.said()[-1]


def test_a_native_voice_that_fails_falls_back(m, trip):
    sv, manager = trip()
    sv.native_ok = False
    manager.start("Tokyo")
    sv.advance(60)
    assert sv.said()[2].startswith("Konbanwa! Tōkyō e yōkoso! Artinya: Selamat malam!")
    assert not manager.native_active


def test_native_voices_can_be_turned_off(m, trip):
    sv, manager = trip(native_voices=False)
    manager.start("Tokyo")
    sv.advance(60)
    assert not any(entry[0] == "native" for entry in sv.log)
    assert "Edge Voices" not in sv.said()[2]


def test_home_language_is_greeted_without_a_translation(m, trip):
    sv, manager = trip()
    manager.start("Denpasar")
    sv.advance(60)
    greeting = sv.said()[2]
    assert greeting == "Selamat malam! Selamat datang di Denpasar!"   # 20:30 in Bali
    manager.teach_phrase()
    assert sv.said()[-1] == "Di sini orang berbahasa sama denganmu!"


def test_teach_me_a_phrase_all_eight_then_again(m, trip):
    sv, manager = trip()
    manager.start("Tokyo")
    sv.advance(60)
    manager.trip.hint_pending = False
    before = len(sv.said())
    natives = []
    for _ in range(8):
        manager.teach_phrase()
        sv.advance(20)
        natives.append([e for e in sv.log if e[0] == "native"][-1][1])
    ja = m.phrases.LANGUAGES["ja"]["phrases"]
    assert sorted(natives) == sorted(p["native"] for p in ja.values())      # no repeats
    lessons = sv.said()[before:]
    assert "Arigatō gozaimasu. Artinya: Terima kasih." in lessons
    manager.teach_phrase()                            # a new round
    sv.advance(20)
    assert len(sv.said()) == before + 9


def test_thai_lessons_explain_the_polite_particle_once(m, trip):
    sv, manager = trip()
    manager.start("Bangkok")
    sv.advance(60)
    assert ("native", "สวัสดีค่ะ ยินดีต้อนรับสู่กรุงเทพฯ", "th-TH-PremwadeeNeural") in sv.log
    manager.teach_phrase()
    sv.advance(20)
    manager.teach_phrase()
    sv.advance(20)
    notes = [s for s in sv.said() if "khrap" in s and "kha." in s and "Laki-laki" in s]
    assert len(notes) == 1


def test_the_radio_tries_the_next_station(m, trip):
    sv, manager = trip()
    manager.start("Tokyo")
    sv.advance(60)
    sv.radio.emit("error", "offline")
    assert sv.radio.plays[-1][0] == "http://gotanno/"
    sv.radio.emit("playing", "http://gotanno/")
    sv.advance(10)
    assert "Kamu mendengarkan Gotanno FM dari Tokyo." in sv.said()
    manager.next_station()
    assert sv.radio.plays[-1][0] == "http://ottava/"
    sv.radio.emit("playing", "http://ottava/")
    sv.advance(10)
    assert sv.said()[-1] == "Kamu mendengarkan Ottava dari Jepang."    # not the city's own
    manager.next_station()                            # round again
    assert sv.radio.plays[-1][0] == "http://jwave/"
    sv.radio.emit("dropped", "http://jwave/")
    assert sv.radio.plays[-1][0] == "http://gotanno/"


def test_when_no_station_plays(m, trip):
    sv, manager = trip()
    manager.start("Tokyo")
    sv.advance(60)
    for _ in range(3):
        sv.radio.emit("error", "format")
    sv.advance(10)
    assert "Stasiun radio dari Tokyo, Jepang sedang tidak bisa diputar." in sv.said()
    sv, manager = trip()
    sv.station_list = []
    manager.start("Tokyo")
    sv.advance(60)
    assert "Aku belum menemukan stasiun radio dari Tokyo, Jepang yang bisa diputar." in sv.said()
    sv, manager = trip()
    sv.station_list = m.stations.StationError("offline")
    manager.start("Tokyo")
    sv.advance(60)
    assert "Direktori radio sedang tidak bisa dihubungi." in sv.said()
    sv, manager = trip()
    sv.supported = False
    manager.start("Tokyo")
    sv.advance(60)
    assert any(s.startswith("Radio butuh Windows Media Foundation") for s in sv.said())
    assert sv.radio.plays == []
    sv, manager = trip(radio=False)
    manager.start("Tokyo")
    sv.advance(60)
    assert sv.radio.plays == []
    manager.next_station()
    assert sv.said()[-1] == "Radio dimatikan di Pengaturan, Keliling Dunia."


def test_louder_and_quieter(m, trip):
    sv, manager = trip()
    manager.change_volume(10)                         # no radio: Hariku's own volume
    assert sv.volume_changes == [10]
    manager.start("Tokyo")
    sv.advance(60)
    manager.change_volume(10)
    assert sv.radio.volume == 45 and sv.said()[-1] == "Volume radio 45 persen."
    for _ in range(10):
        manager.change_volume(-10)
    assert sv.radio.volume == 0 and sv.settings()["radio_volume"] == 0


def test_the_radio_ducks_while_something_is_said(m, trip):
    sv, manager = trip()
    manager.start("Tokyo")
    sv.advance(60)
    manager.duck_tick()
    assert sv.radio.ducked[-1] is False
    manager.note_speech("Gempa magnitudo 5,2 di Ambon.")
    manager.duck_tick()
    assert sv.radio.ducked[-1] is True
    sv.advance(10)
    manager.duck_tick()
    assert sv.radio.ducked[-1] is False
    sv.busy_until = sv.now + 5                        # Hariku Voice speaking
    manager.duck_tick()
    assert sv.radio.ducked[-1] is True


def test_tell_me_about_this_city(m, trip):
    sv, manager = trip()
    manager.about()
    assert sv.said()[-1] == "Kamu sedang tidak jalan-jalan. Coba bilang: bawa aku ke Tokyo."
    manager.start("Tokyo")
    sv.advance(60)
    sv.summaries["Tokyo"] = {"text": "Tokyo adalah ibu kota Jepang.", "lang": "id", "title": "Tokyo"}
    manager.about()
    assert sv.said()[-1] == "Dari Wikipedia: Tokyo adalah ibu kota Jepang."
    sv.summaries["Tokyo"] = {"text": "Tokyo is the capital.", "lang": "en", "title": "Tokyo"}
    manager.about()
    assert sv.said()[-1] == "Dari Wikipedia bahasa Inggris: Tokyo is the capital."
    sv.summaries["Tokyo"] = m.net.NetError("offline")
    manager.about()
    assert sv.said()[-1] == "Wikipedia sedang tidak bisa dihubungi."
    sv.summaries.pop("Tokyo")
    manager.about()
    assert sv.said()[-1] == "Aku tidak menemukan artikel Wikipedia tentang Tokyo."
    manager.about("country")
    assert sv.said()[-1] == "Dari Wikipedia: Jepang adalah negara."
    assert manager.about_target("kota ini") == "city"
    assert manager.about_target("Tokyo") == "city"
    assert manager.about_target("jepang") == "country"
    assert manager.about_target("Nintendo") is None


def test_what_time_and_where(m, trip):
    sv, manager = trip()
    manager.time_there()
    assert sv.said()[-1] == "Kamu di Batam, sekarang jam 19.30."
    manager.where_am_i()
    assert sv.said()[-1] == "Kamu di rumah, di Batam."
    sv.home_place = None
    manager.where_am_i()
    assert sv.said()[-1].startswith("Kamu di rumah. Tambahkan tempat utamamu")
    sv.home_place = dict(BATAM)
    manager.start("Tokyo")
    manager.where_am_i()
    assert sv.said()[-1] == "Kamu sedang di pesawat."
    sv.advance(60)
    sv.radio.emit("playing", "http://jwave/")
    manager.time_there()
    assert sv.said()[-1].startswith("Di Tokyo sekarang jam 21.3")
    manager.where_am_i()
    assert sv.said()[-1].startswith("Kamu di Tokyo, Jepang, sekitar 5.300 kilometer dari Batam.")
    assert sv.said()[-1].endswith("Di radio: J-Wave.")
    manager.which_station()
    assert sv.said()[-1] == "Ini J-Wave."


def test_flying_home(m, trip):
    sv, manager = trip()
    manager.go_home()
    assert sv.said() == ["Kamu sudah di rumah."]
    manager.start("Tokyo")
    sv.advance(60)
    stops = sv.radio.stops
    manager.go_home()
    assert sv.radio.stops == stops + 1 and manager.trip.phase == "homebound"
    assert sv.said()[-1] == "Siap, kita pulang ke Batam."
    manager.go_home()
    assert sv.said()[-1] == "Kita sedang dalam perjalanan pulang."
    sv.advance(40)
    assert sv.kinds()[-4:] == ["say", "sound:engine", "sound:chime", "say"]
    assert sv.said()[-1].startswith("Kita kembali ke Batam. Sekarang jam 19.3")
    assert sv.said()[-1].endswith("Terima kasih sudah terbang bersama Hariku Air.")
    assert manager.trip is None


def test_flying_home_can_be_skipped(m, trip):
    sv, manager = trip()
    manager.start("Tokyo")
    sv.advance(60)
    manager.go_home()
    sv.advance(3)
    assert manager.skip() is True
    sv.advance(10)
    assert sv.said()[-1].startswith("Kita kembali ke Batam.")


def test_a_new_trip_replaces_the_old_one(m, trip):
    sv, manager = trip()
    manager.start("Tokyo")
    sv.advance(3)
    first = manager.trip
    manager.start("Paris")
    assert first.phase == "ended" and manager.trip is not first
    assert ("stop_voice",) in sv.log and sv.radio.stops >= 1
    sv.advance(60)
    said = sv.said()
    assert not any("Tokyo, Jepang. Waktu" in s for s in said)       # Tokyo never arrived
    assert any(s.startswith("Selamat datang di Paris, Prancis.") for s in said)


def test_a_surprise_trip(m, trip):
    sv, manager = trip()
    manager.start("mana saja")
    sv.advance(60)
    assert "Tujuan kejutan hari ini: Tokyo!" in sv.said()[0]
    manager.start("mana saja")
    assert sv.resolved[-1] == ("mana saja", "Tokyo")                 # not Tokyo again


def test_the_weather_is_optional(m, trip):
    sv, manager = trip()
    sv.weather_value = m.net.NetError("offline")
    manager.start("Tokyo")
    sv.advance(60)
    assert sv.said()[1].endswith("2 jam lebih cepat dari Batam.")


def test_native_names(m):
    names = {("Tokyo", "en"): "Tokyo", ("Nagoya", "en"): "Nagoya", ("Nagoya", "ja"): "名古屋市",
             ("Kobe", "ja"): "Kobe", ("Vienna", "de"): "Wien", ("Wina", "en"): "Vienna",
             ("Wina", "de"): "Wien"}

    def localized(dest):
        return lambda code: names.get((dest["name"], code))
    tokyo = dict(TOKYO)
    assert m.trip.native_names(tokyo, "ja", "id", localized(tokyo)) == (("東京", "Tōkyō"), "Tokyo")
    nagoya = dict(TOKYO, name="Nagoya", query="Nagoya")
    assert m.trip.native_names(nagoya, "ja", "id", localized(nagoya))[0] == ("名古屋", "Nagoya")
    kobe = dict(TOKYO, name="Kobe", query="Kobe")      # the table has it
    assert m.trip.native_names(kobe, "ja", "id", localized(kobe))[0] == ("神戸", "Kōbe")
    osaka_unknown = dict(TOKYO, name="Hamamatsu", query="Hamamatsu")
    assert m.trip.native_names(osaka_unknown, "ja", "id", lambda code: "Hamamatsu")[0] is None
    wina = {"name": "Wina", "country_code": "AT", "query": "Wina"}
    assert m.trip.native_names(wina, "de", "id", localized(wina))[0] == ("Wien", "")
    assert m.trip.native_names(wina, "de", "id", lambda code: None)[0] == ("Wien", "")  # table
    graz = {"name": "Graz", "country_code": "AT", "query": "Graz"}
    assert m.trip.native_names(graz, "de", "id", lambda code: None)[0] == ("Graz", "")
    assert m.trip.native_names(wina, None, "id", localized(wina)) is None


def test_the_script_runs_steps_in_order_and_can_skip(m):
    sv = FakeServices(m)
    script = m.trip.Script(sv)
    ran = []

    def instant(name):
        return lambda done, gen: (ran.append(name), done())

    def slow(name, seconds):
        def step(done, gen):
            ran.append(name)
            script.later(seconds, done, gen)
        return step

    script.add(instant("a"))
    script.add(slow("b", 5))
    script.add(instant("c"))
    script.add(instant("d"), label="there")
    script.add(instant("e"))
    script.start()
    assert ran == ["a", "b"] and script.running
    assert script.skip_to("there")
    assert ran == ["a", "b", "d", "e"] and not script.running
    sv.advance(10)
    assert ran == ["a", "b", "d", "e"]               # b's timer was cancelled
    many = [instant(str(i)) for i in range(2000)]    # no recursion limit
    script.extend(many)
    assert ran[-1] == "1999"


# ------------------------------------------------------------
# main.py: Aruna, actions, settings
# ------------------------------------------------------------

@pytest.fixture
def wmain(monkeypatch, tmp_data_dir, lang, m):
    spec = importlib.util.spec_from_file_location("world_trip_main_under_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    try:
        module.teardown()
    except Exception:
        pass


def test_register_and_teardown(wmain, fresh_event_bus, monkeypatch):
    import core.commands
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel", lambda *args: panels.append(args))
    monkeypatch.setattr(core.commands, "_intents", {})
    monkeypatch.setattr(core.commands, "_answer_actions", set())
    wmain.register(fresh_event_bus)
    names = {args[1] for args, kwargs in actions}
    assert names == {name for name, *_rest in wmain.ACTIONS}
    for args, kwargs in actions:
        assert args[0] == "World Trip" and args[3] is None and kwargs == {}   # no default keys
        assert core.commands.is_answer_action(f"World Trip.{args[1]}")
    assert {i.id for i in core.commands.intents()} == {"World Trip.go", "World Trip.about",
                                                       "World Trip.where"}
    assert "ganti stasiun" in core.commands.aliases_for("World Trip.next_station")
    assert panels[0][0] == "Keliling Dunia"
    assert wmain._on_before_speak in fresh_event_bus._listeners["on_before_speak"]
    wmain.teardown()
    assert core.commands.intents() == []
    assert core.commands.aliases_for("World Trip.next_station") == []
    assert wmain._on_before_speak not in fresh_event_bus._listeners.get("on_before_speak", [])


@pytest.mark.parametrize("text, slot", [
    ("bawa aku ke Tokyo", "Tokyo"),
    ("Aruna, terbang ke Paris.", "Paris"),
    ("take me to Japan", "Japan"),
    ("fly to Seoul", "Seoul"),
    ("jalan-jalan ke Istanbul", "Istanbul"),
    ("kunjungi New York", "New York"),
    ("bawa aku ke mana saja", "mana saja"),
])
def test_trip_sentences_reach_the_trip(wmain, monkeypatch, text, slot):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    core.commands.add_intent(wmain.TRIP_INTENT, list(wmain.TRIP_PATTERNS), wmain._on_trip_intent)
    found = core.commands.match_intents(text)
    assert found and found[0].intent.id == "World Trip.go" and found[0].text == slot
    started = []
    monkeypatch.setattr(wmain, "_manager", types.SimpleNamespace(start=started.append))
    reply = found[0].intent.handler(core.commands.Request(found[0].text, text))
    assert isinstance(reply, core.commands.Reply) and reply.wait and not reply.say
    assert started == [slot]


@pytest.mark.parametrize("text, mine", [
    ("di mana aku", True), ("Aku di mana?", True), ("kita lagi di mana", True),
    ("di mana saya sekarang", True), ("di mana ISS", False), ("di mana penerbanganku", False),
])
def test_where_am_i_in_indonesian(wmain, monkeypatch, text, mine):
    # As a command, "di mana aku" would only be "mana" (Aruna ignores "di" and
    # "aku"), the same as Space's "di mana ISS"; as a command with content it isn't.
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    core.commands.add_intent(wmain.WHERE_INTENT, list(wmain.WHERE_PATTERNS), wmain._on_where_intent)
    asked = []
    monkeypatch.setattr(wmain, "_manager",
                        types.SimpleNamespace(where_am_i=lambda: asked.append(True)))
    found = core.commands.match_intents(text)
    assert found and found[0].intent.id == "World Trip.where"
    reply = found[0].intent.handler(core.commands.Request(found[0].text, text))
    if mine:
        assert isinstance(reply, core.commands.Reply) and reply.wait and asked == [True]
    else:
        assert reply is None and asked == []


def test_not_a_trip(wmain, monkeypatch):
    import core.commands
    monkeypatch.setattr(wmain, "_manager", types.SimpleNamespace(start=lambda text: None))
    request = core.commands.Request
    assert wmain._on_trip_intent(request("   ", "bawa aku ke")) is None
    assert wmain._on_trip_intent(request("x" * 100, "...")) is None
    monkeypatch.setattr(wmain, "_is_a_reminder", lambda text: True)
    assert wmain._on_trip_intent(request("dokter besok jam 9", "...")) is None
    monkeypatch.setattr(wmain, "_manager", types.SimpleNamespace(about_target=lambda text: None))
    assert wmain._on_about_intent(request("Nintendo", "ceritakan tentang Nintendo")) is None


def _commands(wmain, lang_code="id"):
    """World Trip's actions and some of the core's, as Aruna matches them."""
    import core.commands
    candidates = []
    for name, description, title, _callback, aliases in wmain.ACTIONS:
        candidates.append(core.commands.Command(f"World Trip.{name}", wmain._(description),
                                                list(aliases)))
    for action_id, description in (("Hariku Core.speak_time", "Ucapkan waktu"),
                                   ("Hariku Core.volume_up", "Keraskan volume"),
                                   ("Hariku Core.volume_down", "Kecilkan volume"),
                                   ("Space.where_is_iss", "Di mana ISS?")):
        candidates.append(core.commands.Command(action_id, description,
                                                core.commands.aliases_for(action_id)))
    return candidates


@pytest.mark.parametrize("text, action_id", [
    ("ganti stasiun", "World Trip.next_station"),
    ("next station", "World Trip.next_station"),
    ("kecilkan", "World Trip.radio_quieter"),
    ("keraskan", "World Trip.radio_louder"),
    ("kecilkan suara", "Hariku Core.volume_down"),
    ("ceritakan tentang kota ini", "World Trip.about_city"),
    ("ajari aku satu kalimat", "World Trip.teach_phrase"),
    ("teach me a phrase", "World Trip.teach_phrase"),
    ("jam berapa di sana", "World Trip.time_there"),
    ("what time is it there", "World Trip.time_there"),
    ("jam berapa", "Hariku Core.speak_time"),
    ("where am I", "World Trip.where_am_i"),
    ("pulang", "World Trip.go_home"),
    ("go home", "World Trip.go_home"),
    ("lewati", "World Trip.skip_flight"),
    ("stasiun apa ini", "World Trip.which_station"),
    ("take me anywhere", "World Trip.surprise"),
    ("di mana iss", "Space.where_is_iss"),
])
def test_what_aruna_runs(wmain, text, action_id):
    import core.commands
    found = core.commands.match(text, _commands(wmain))
    assert found.kind == "run" and found.best.id == action_id, found


def test_settings_are_checked(wmain):
    s = wmain.normalize_settings({"departure": False, "engine": "yes", "radio_volume": 250,
                                  "native_voices": False, "trips": -3})
    assert s == {"departure": False, "engine": True, "radio": True, "radio_volume": 100,
                 "native_voices": False, "trips": 0}
    assert wmain.normalize_settings("broken") == wmain.DEFAULT_SETTINGS


def test_the_voice_list_on_the_settings_page(wmain, lang):
    text = wmain.voice_lines({"edge": EDGE, "windows": WINDOWS},
                             provider_names={"edge": "Edge", "windows": "Windows"})
    lines = text.splitlines()
    assert "Jepang: Keita (Edge)" in lines
    assert "Kanton: HiuMaan (Edge)" in lines
    assert "Korea: belum ada suara asli" in lines
    assert "Indonesia: Andika (Windows)" in lines
    assert len(lines) == len(wmain.phrases.LANGUAGES)
    text = wmain.voice_lines({"windows": WINDOWS}, native_on=False)
    assert text.startswith("Suara asli dimatikan") and "Edge Voices" in text.splitlines()[-1]


def test_the_services_hold_and_show_through_aruna(wmain, monkeypatch):
    import core.commands
    held, shown = [], []
    monkeypatch.setattr(core.commands, "hold_answer", held.append)
    monkeypatch.setattr(core.commands, "show_answer", shown.append)
    services = wmain.Services()
    services.hold(12)
    services.show("Konbanwa! (こんばんは！)")
    assert held == [12] and shown == ["Konbanwa! (こんばんは！)"]
    assert services.play_sound.__func__ is wmain.Services.play_sound
    assert round(wmain._duration("chime"), 1) == 1.4 and round(wmain._duration("engine"), 1) == 7.0


# ------------------------------------------------------------
# The sounds
# ------------------------------------------------------------

def _wav(path):
    with wave.open(path) as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()


def test_the_sounds_ship_and_are_what_the_generator_makes(m):
    if EXT_DIR not in sys.path:
        sys.path.insert(0, EXT_DIR)
    import world_trip_sounds as sounds
    for name, low, high in (("chime.wav", 1.0, 1.6), ("engine.wav", 5.0, 8.0)):
        path = os.path.join(EXT_DIR, "sounds", name)
        channels, width, rate, frames = _wav(path)
        assert channels == 1 and width == 2 and low <= frames / rate <= high, name
        with open(path, "rb") as f:
            data = f.read()
        samples = memoryview(data[44:]).cast("h")
        loudest = max(abs(v) for v in samples)
        assert 0.3 * 32767 < loudest < 0.8 * 32767, name
        assert abs(samples[0]) < 200 and abs(samples[-1]) < 200, name       # no clicks
    with open(os.path.join(EXT_DIR, "sounds", "chime.wav"), "rb") as f:
        assert f.read() == sounds.chime()
    with open(os.path.join(EXT_DIR, "sounds", "engine.wav"), "rb") as f:
        assert f.read() == sounds.engine()
