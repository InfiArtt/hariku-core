# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The welcome (core 2.10, core.onboarding): the nickname, the personal texts,
# prefilling from what is saved (including the old wizard's name), saving to
# the Profile, Places, autostart and the greeting, Cancel, the time and
# weather sentence (fake network), "Try it", and the extensions it suggests.
# Every test runs on a temporary data folder, never the user's real settings.
# The window itself is checked by tests/test_onboarding_ui.py (CI only).

import ast
import datetime
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BATAM = {"name": "Batam", "label": "Batam, Riau Islands, Indonesia", "latitude": 1.14937,
         "longitude": 104.02491, "timezone": "Asia/Jakarta", "source": "city", "city": "Batam",
         "region": "Riau Islands", "country": "Indonesia"}
# 07:20 UTC is 14:20 in Batam (WIB, UTC+7).
NOON_UTC = datetime.datetime(2026, 9, 25, 7, 20, tzinfo=datetime.timezone.utc)
SYSTEM = os.path.abspath(os.path.join(os.sep, "hariku", "extensions"))


@pytest.fixture
def lang(monkeypatch):
    from core import i18n
    had_core, old_core = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)

    def use(code):
        monkeypatch.setattr(i18n, "_current_language", code)
    use("en")
    yield use
    if had_core:
        i18n._language_cache["core"] = old_core
    else:
        i18n._language_cache.pop("core", None)


@pytest.fixture
def onb(tmp_data_dir, lang, monkeypatch):
    import core.onboarding
    import core.places
    # Places keeps its store in memory; start each test from the empty folder.
    monkeypatch.setattr(core.places, "_cache", {"stamp": None, "store": None})
    return core.onboarding


def _core():
    import core.api
    return core.api.load_data("Core")


def _save_core(data):
    import core.api
    core.api.save_data("Core", data)


def _messages(code):
    with open(os.path.join(ROOT, "locales", f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)["messages"]


# ------------------------------------------------------------
# Names
# ------------------------------------------------------------

def test_the_nickname_is_the_first_word_of_the_name(onb):
    assert onb.first_word("  Rafli   Hidayat ") == "Rafli"
    assert onb.first_word("") == ""
    assert onb.nickname_for("Rafli Hidayat", "") == "Rafli"
    assert onb.nickname_for("Rafli Hidayat", "  Bro ") == "Bro"
    assert onb.nickname_for("", "") == ""


# ------------------------------------------------------------
# Languages
# ------------------------------------------------------------

@pytest.mark.parametrize("saved, windows, expected", [
    ("en", ["id-ID"], "en"),                  # the saved one wins
    (None, ["id-ID"], "id"),
    (None, ["en-US", "id-ID"], "en"),         # Windows' display language first
    (None, ["fr-FR", "id_ID"], "id"),
    (None, ["fr-FR"], "en"),
    (None, [], "en"),
    ("xx", [], "en"),                         # a language Hariku doesn't have
])
def test_default_language(onb, saved, windows, expected):
    assert onb.default_language(saved, windows, ["en", "id"]) == expected


def test_hariku_s_languages(onb):
    found = onb.languages()
    assert {code for code, _name in found} == {"en", "id"}
    assert dict(found)["id"] == "Bahasa Indonesia"
    assert [name for _code, name in found] == sorted((n for _c, n in found), key=str.casefold)


def test_use_language_switches_at_once_and_keeps_other_translations(lang, i18n_cache):
    from core import i18n
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    i18n_cache["some_extension"] = {"en": {"manifest": {}, "messages": {"hi": "Hi"}}}
    _ = i18n.get_translator("core")
    assert i18n.use_language("id") is True
    assert _("places_default_home") == "Rumah"
    assert "some_extension" in i18n_cache, "an extension's translations were dropped"
    assert i18n.use_language("xx") is False
    assert i18n.get_current_language() == "id"
    assert sorted(i18n.translations("places_default_home")) == ["Home", "Rumah"]
    assert i18n.translations("no_such_key") == []


# ------------------------------------------------------------
# Prefilling
# ------------------------------------------------------------

def test_prefill_on_a_first_run(onb):
    answers = onb.prefill(first_run=True, windows_tags=["id-ID"])
    assert answers.as_dict() == {"language": "id", "name": "", "nickname": "", "persona": "auto",
                                 "place": None, "birthday": None, "autostart": False,
                                 "greet": True, "extensions": []}
    assert onb.nickname_is_automatic(answers)


def test_prefill_uses_the_old_wizard_s_name(onb):
    # The wizard before 2.10 saved "user_name" in Core.json: that is the Profile's
    # name, so it is simply there, and the nickname follows its first word.
    _save_core({"user_name": "Budi Santoso", "auto_start": True, "onboarding_completed": True,
                "language": "en", "telemetry_enabled": True})
    answers = onb.prefill()
    assert (answers.name, answers.nickname, answers.autostart, answers.language) == (
        "Budi Santoso", "Budi", True, "en")
    assert onb.nickname_is_automatic(answers)


def test_prefill_treats_the_old_placeholder_as_no_name(onb):
    _save_core({"user_name": "User", "onboarding_completed": True})
    answers = onb.prefill()
    assert answers.name == "" and answers.nickname == ""


def test_prefill_shows_the_whole_profile(onb, lang):
    lang("id")
    _save_core({"user_name": "Rafli Hidayat", "user_nickname": "Bro", "language": "id",
                "user_birthday": {"day": 12, "month": 5, "year": 1999},
                "greet_on_startup": False, "auto_start": False})
    answers = onb.prefill(windows_tags=["en-US"])
    assert answers.as_dict() == {"language": "id", "name": "Rafli Hidayat", "nickname": "Bro",
                                 "persona": "auto", "place": None, "birthday": (12, 5, 1999),
                                 "autostart": False, "greet": False, "extensions": []}
    assert not onb.nickname_is_automatic(answers)


def test_answers_compare_and_copy(onb):
    a = onb.Answers(name="Rafli", birthday=[12, 5, None], extensions=("weather",))
    b = a.copy()
    assert a == b and a.birthday == (12, 5, None) and b.extensions == ["weather"]
    b.greet = False
    assert a != b


# ------------------------------------------------------------
# What Hariku says
# ------------------------------------------------------------

def test_the_personal_texts_in_indonesian(onb, lang):
    lang("id")
    reply = onb.name_reply("Rafli")
    assert reply == "Halo, Rafli! Akhirnya kita kenalan juga."
    assert onb.question("where", "Rafli", reply) == (
        "Halo, Rafli! Akhirnya kita kenalan juga. Nah, Rafli, kamu tinggal di mana? Biar aku "
        "nggak bilang selamat pagi pas di tempatmu sudah tengah malam. Ketik nama kotamu, lalu "
        "tekan Enter:")
    assert onb.question("birthday", "Rafli") == (
        "Sekarang pertanyaan paling penting: kapan ulang tahunmu, Rafli? Tanggal:")
    assert onb.question("hello") == (
        "Halo! Aku Hariku, teman barumu yang agak kepo. Pertama, kita ngobrol pakai bahasa apa?")
    assert onb.question("startup", "Rafli") == (
        "Terakhir, janji: boleh aku ikut bangun tiap komputermu menyala, Rafli? Aku nggak "
        "berisik kok. Sedikit.")


def test_the_personal_texts_in_english(onb):
    assert onb.name_reply("Rafli") == "Hey, Rafli! Finally, we meet."
    assert onb.question("where", "Rafli") == (
        "So, Rafli, where do you live? That way I won't say good morning at midnight. Type your "
        "city, then press Enter:")
    assert onb.question("extensions", "Rafli").startswith(
        "What else should I learn, Rafli? Pick some, I'm a fast learner. ")


@pytest.mark.parametrize("code", ["en", "id"])
@pytest.mark.parametrize("page", ["hello", "name", "where", "birthday", "aruna", "extensions",
                                  "startup"])
def test_every_question_reads_well_without_a_name(onb, lang, code, page):
    lang(code)
    text = onb.question(page, "", "")
    assert text and "{" not in text and "  " not in text, text
    assert not re.search(r"[,;:]\s*[?!.]|\s[,.?!]|^[\s,.]", text), text
    assert onb.name_reply("") in ("Hey! Finally, we meet.", "Halo! Akhirnya kita kenalan juga.")
    assert "Rafli" in onb.question(page, "Rafli", "") or page in ("hello", "name")


def test_the_place_sentence_with_the_weather(onb, lang):
    lang("id")
    weather = {"temperature": 31.4, "code": 1}
    assert onb.place_sentence(BATAM, NOON_UTC, weather) == (
        "Di Batam sekarang jam 14:20, cerah berawan, 31 derajat.")
    assert onb.place_sentence(BATAM, NOON_UTC) == "Di Batam sekarang jam 14:20."
    assert onb.place_sentence(BATAM, NOON_UTC, {"temperature": 27.6, "code": 1234}) == (
        "Di Batam sekarang jam 14:20, 28 derajat.")
    assert onb.weather_sentence(BATAM, {"temperature": 26, "code": 63}) == (
        "Cuaca di Batam: hujan, 26 derajat.")
    lang("en")
    assert onb.place_sentence(BATAM, NOON_UTC, {"temperature": 30.2, "code": 95}) == (
        "In Batam it's 14:20 now, a thunderstorm, 30 degrees.")
    assert onb.place_sentence(None, NOON_UTC) == ""
    assert onb.weather_sentence(BATAM, None) == ""


def test_a_saved_place_is_called_by_its_city(onb):
    place = {"id": "3f9a1c2e", "name": "Rumah", "lat": 1.13, "lon": 104.05,
             "label": "Jalan Raja Ali Haji, Batam", "timezone": None, "source": "address",
             "city": "Batam", "region": "", "country": ""}
    assert onb.city_of(place) == "Batam"
    assert onb.city_of(dict(place, city="")) == "Rumah"
    assert onb.city_of({"label": "Somewhere, Far"}) == "Somewhere"


@pytest.mark.parametrize("code", ["en", "id"])
def test_every_weather_code_has_words(onb, lang, code):
    lang(code)
    for wmo in (0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80,
                81, 82, 85, 86, 95, 96, 99):
        words = onb.sky_words(wmo)
        assert words and not words.startswith("onb_"), (wmo, words)
    assert onb.sky_words(1234) == "" and onb.sky_words(None) == "" and onb.sky_words("x") == ""


def test_the_birthday_reply(onb, lang):
    lang("id")
    assert onb.birthday_reply((12, 5, None)) == "12 Mei, dicatat! Siap-siap aku heboh di hari itu."
    assert onb.birthday_reply((12, 5, 1999)) == "12 Mei 1999, dicatat! Siap-siap aku heboh di hari itu."
    assert onb.birthday_reply(None) == ""
    assert onb.check_birthday(0, 0, None) is None
    import core.personal
    with pytest.raises(core.personal.ProfileError):
        onb.check_birthday(12, 0, None)


def test_the_startup_example_greets_by_name(onb, lang):
    import core.constants
    lang("id")
    text = onb.startup_example("Rafli", datetime.datetime(2026, 9, 25, 7, 30))
    assert text == f"Selamat pagi, Rafli. Selamat datang di Hariku versi {core.constants.CORE_VERSION}."


# ------------------------------------------------------------
# The weather and the city search (no network: the fetch is replaced)
# ------------------------------------------------------------

def test_the_weather_request_sends_only_a_rounded_point(onb):
    url = onb.weather_url({"lat": 1.130123, "lon": 104.052987})
    assert url.startswith("https://api.open-meteo.com/v1/forecast?")
    assert "latitude=1.13&longitude=104.05" in url
    assert "current=temperature_2m%2Cweather_code" in url
    assert onb.weather_key(BATAM) == (1.15, 104.02)


def test_parse_weather(onb):
    assert onb.parse_weather({"current": {"temperature_2m": 31.2, "weather_code": 2}}) == {
        "temperature": 31.2, "code": 2}
    assert onb.parse_weather({"current": {"temperature_2m": 31.2}}) == {
        "temperature": 31.2, "code": None}
    for bad in (None, [], {}, {"current": {}}, {"current": {"temperature_2m": "hot"}}):
        assert onb.parse_weather(bad) is None


def test_fetch_weather(onb, monkeypatch):
    import core.place_search
    asked = []

    def fetch(url, timeout=None, user_agent=None):
        asked.append(url)
        return {"current": {"temperature_2m": 30.6, "weather_code": 3}}

    monkeypatch.setattr(core.place_search, "fetch_json", fetch)
    assert onb.fetch_weather(BATAM) == {"temperature": 30.6, "code": 3}
    assert "latitude=1.15&longitude=104.02" in asked[0]

    def offline(url, timeout=None, user_agent=None):
        raise core.place_search.FetchError("offline", "no network")

    monkeypatch.setattr(core.place_search, "fetch_json", offline)
    assert onb.fetch_weather(BATAM) is None


def test_search_cities(onb, monkeypatch):
    import core.place_search

    def fetch(url, timeout=None, user_agent=None):
        assert "name=Batam" in url and "language=id" in url
        return {"results": [{"name": "Batam", "admin1": "Riau Islands", "country": "Indonesia",
                             "latitude": 1.14937, "longitude": 104.02491,
                             "timezone": "Asia/Jakarta"}]}

    monkeypatch.setattr(core.place_search, "fetch_json", fetch)
    found, error = onb.search_cities("Batam", "id")
    assert error is None and [c["label"] for c in found] == ["Batam, Riau Islands, Indonesia"]

    def offline(url, timeout=None, user_agent=None):
        raise core.place_search.FetchError("offline")

    monkeypatch.setattr(core.place_search, "fetch_json", offline)
    assert onb.search_cities("Batam") == ([], "city_failed")


# ------------------------------------------------------------
# "Try it": only the time and the date, nothing ever runs
# ------------------------------------------------------------

@pytest.fixture
def nothing_runs(monkeypatch):
    import core.commands
    import core.hotkeys
    ran = []

    class Action:
        description = "Open settings"
        wants_tap_count = False

        def callback(self):
            ran.append("settings")

    monkeypatch.setattr(core.hotkeys, "actions", {"Hariku Core.input_gestures": Action()})
    monkeypatch.setattr(core.commands, "run_action",
                        lambda *a, **k: ran.append(a) or pytest.fail("an action ran"))
    return ran


def test_try_it_answers_the_time_and_the_date(onb, lang, nothing_runs):
    lang("id")
    now = datetime.datetime(2026, 9, 25, 14, 20)
    assert onb.try_answer("jam berapa", now) == ("time", "Sekarang jam 14:20.")
    assert onb.try_answer("Jam berapa sekarang?", now) == ("time", "Sekarang jam 14:20.")
    kind, text = onb.try_answer("tanggal berapa", now)
    assert kind == "date" and text == "Hari ini Jumat, 25 September 2026."
    lang("en")
    assert onb.try_answer("what time is it", now) == ("time", "It's 14:20.")
    assert onb.try_answer("what day is it", now)[0] == "date"
    assert nothing_runs == []


def test_try_it_never_runs_anything_else(onb, lang, nothing_runs):
    lang("id")
    assert onb.try_answer("", None) == ("empty", "Kotaknya masih kosong, lho. Aku belum bisa baca pikiran. Ketik sesuatu dulu, misalnya jam berapa.")
    assert onb.try_answer("buka pengaturan")[0] == "other"
    assert onb.try_answer("ingatkan aku besok jam 7 minum obat")[0] == "reminder"
    lang("en")
    assert onb.try_answer("open settings")[0] == "other"
    assert onb.try_answer("remind me tomorrow at 7 to take my medicine")[0] == "reminder"
    assert nothing_runs == []


# ------------------------------------------------------------
# Extensions
# ------------------------------------------------------------

def _entry(ext_id, name, minimum="", url=True):
    e = {"id": ext_id, "name": name, "version": "1.0", "author": "Rafli",
         "description": f"The store's {name}."}
    if url:
        e["download_url"] = f"https://example.invalid/{ext_id}.hrk"
    if minimum:
        e["minimum_core_version"] = minimum
    return e


def _installed(ext_id):
    return {"id": ext_id, "name": ext_id.title(), "version": "1.0", "author": "Rafli",
            "description": "", "is_enabled": True, "is_unpacked": True,
            "path": os.path.join(SYSTEM, ext_id), "minimum_core_version": "2.0",
            "last_tested_core_version": "", "missing_fields": []}


REGISTRY = [
    _entry("world_trip", "World Trip", "2.9"),
    _entry("orbit", "Orbit"),                         # not one the welcome suggests
    _entry("weather", "Weather", "2.8"),
    _entry("voice_control", "Voice Control", "2.7"),  # installed already
    _entry("timer_alarm", "Timer & Alarm", "2.9"),
    _entry("briefing", "Morning Briefing", "2.7"),
    _entry("world_clock", "World Clock", "9.0"),      # needs a newer Hariku
    _entry("lumina", "Lumina", url=False),             # nothing to download
    _entry("earthquake", "Earthquakes & Tsunami", "2.8"),
]


def test_recommendations(onb, lang):
    found = onb.recommendations([_installed("voice_control")], REGISTRY, has_place=True,
                                system_dir=SYSTEM)
    assert [e["id"] for e in found] == ["weather", "briefing", "timer_alarm", "world_trip",
                                        "earthquake"]
    assert {e["id"] for e in found if e["checked"]} == {"weather", "briefing", "timer_alarm"}
    by_id = {e["id"]: e for e in found}
    assert by_id["weather"]["description"] == (
        "The weather now and for the next 7 days where you live. Ask Aruna: weather.")
    assert by_id["timer_alarm"]["name"] == "Timer & Alarm"
    assert by_id["weather"]["download_url"] == "https://example.invalid/weather.hrk"
    lang("id")
    found = onb.recommendations([], REGISTRY, has_place=False, system_dir=SYSTEM)
    assert "voice_control" in [e["id"] for e in found]
    assert {e["id"] for e in found if e["checked"]} == {"briefing", "timer_alarm"}
    assert {e["id"]: e for e in found}["briefing"]["description"].startswith("Briefing singkat")


def test_no_recommendations_offline(onb):
    assert onb.recommendations([], [], system_dir=SYSTEM) == []
    assert onb.recommendations([], None, system_dir=SYSTEM) == []


def test_join_names(onb, lang):
    assert onb.join_names([]) == ""
    assert onb.join_names(["Weather"]) == "Weather"
    assert onb.join_names(["Weather", "Timer & Alarm"]) == "Weather and Timer & Alarm"
    assert onb.join_names(["A", "B", "C"]) == "A, B and C"
    lang("id")
    assert onb.join_names(["A", "B", "C"]) == "A, B dan C"


def test_install_goes_on_after_a_failure(onb):
    extensions = [{"id": i, "name": i.title(), "download_url": f"https://example.invalid/{i}"}
                  for i in ("weather", "briefing", "timer_alarm")]
    downloads, progress = [], []

    def download(ext_id, url):
        downloads.append((ext_id, url))
        if ext_id == "briefing":
            raise OSError("disk full")
        return ext_id != "timer_alarm"

    good, bad = onb.install(extensions, download,
                            lambda i, ext, ok: progress.append((i, ext["id"], ok)))
    assert [e["id"] for e in good] == ["weather"]
    assert [e["id"] for e in bad] == ["briefing", "timer_alarm"]
    assert progress == [(0, "weather", True), (1, "briefing", False), (2, "timer_alarm", False)]
    assert len(downloads) == 3


def test_install_texts(onb, lang):
    lang("id")
    a, b = {"name": "Weather"}, {"name": "Timer & Alarm"}
    assert onb.install_start_text([a]) == "Memasang Weather. Tunggu sebentar ya."
    assert onb.install_start_text([a, b]) == "Memasang 2 ekstensi. Tunggu sebentar ya."
    assert onb.install_progress_text(0, 2, a, True) == "Weather terpasang (1 dari 2)."
    assert onb.install_progress_text(1, 2, b, False) == "Timer & Alarm gagal dipasang (2 dari 2)."
    assert onb.install_summary([a, b], [], "Ctrl + X") == (
        "Sudah terpasang: Weather dan Timer & Alarm. Tekan Enter, dan ayo mulai!")
    assert "Belum terpasang: Timer & Alarm" in onb.install_summary([a], [b], "Ctrl + X")
    assert onb.install_summary([], [a], "Ctrl + X").startswith(
        "Aku gagal memasang Weather; coba lagi nanti di Pengelola Ekstensi (Ctrl + X).")


# ------------------------------------------------------------
# The summary
# ------------------------------------------------------------

def test_the_summary(onb, lang):
    lang("id")
    answers = onb.Answers(language="id", name="Rafli Hidayat", nickname="Rafli",
                          birthday=(12, 5, None), autostart=True, greet=True)
    lines = onb.summary(answers, place=BATAM, aruna_key="Ctrl + Alt + Backspace",
                        extensions=[{"name": "Weather"}, {"name": "Timer & Alarm"}])
    assert lines == [
        "Beres, Rafli! Kita resmi kenalan.",
        "Rumahmu di Batam.",
        "Tanggal 12 Mei nanti aku ucapkan selamat ulang tahun.",
        "Setiap kali komputermu menyala, aku menyapamu.",
        "Setelah kamu tekan Selesai, aku pasang Weather dan Timer & Alarm.",
        "Tekan Ctrl + Alt + Backspace untuk memanggil Aruna.",
        "Mulai sekarang aku ada di sini, siap diganggu kapan saja. Selamat datang di Hariku!",
    ]
    bare = onb.summary(onb.Answers(greet=False), aruna_key="Ctrl + Alt + Backspace")
    assert bare == ["Beres! Kita resmi kenalan.", "Tekan Ctrl + Alt + Backspace untuk memanggil Aruna.",
                    "Mulai sekarang aku ada di sini, siap diganggu kapan saja. Selamat datang di Hariku!"]
    lang("en")
    lines = onb.summary(onb.Answers(name="Rafli", greet=True), aruna_key="Ctrl + Alt + Backspace")
    assert lines[:2] == ["Done, Rafli! We're officially acquainted.", "Every time Hariku starts, I'll greet you."]


# ------------------------------------------------------------
# Saving, and Cancel
# ------------------------------------------------------------

def test_save_on_a_first_run(onb, lang):
    import core.places
    lang("id")
    calls = []
    answers = onb.Answers(language="id", name="Rafli Hidayat", nickname="", place=BATAM,
                          birthday=(12, 5, None), autostart=True, greet=True)
    done = onb.save(answers, first_run=True, set_autostart=calls.append)
    assert done["errors"] == [] and calls == [True]
    saved = _core()
    assert saved["user_name"] == "Rafli Hidayat" and saved["user_nickname"] == "Rafli"
    assert saved["user_birthday"] == {"day": 12, "month": 5, "year": None}
    assert saved["auto_start"] is True and saved["language"] == "id"
    assert saved["onboarding_completed"] is True
    assert "greet_on_startup" not in saved      # on by default, and left on
    assert "user_fields" not in saved and "telemetry_enabled" not in saved
    places = core.places.get_places()
    assert [(p["name"], p["city"], p["timezone"]) for p in places] == [
        ("Rumah", "Batam", "Asia/Jakarta")]
    assert core.places.get_main_id() == places[0]["id"]
    assert done["place"]["id"] == places[0]["id"]


def test_saving_the_answers_prefilled_changes_nothing(onb):
    import core.api
    import core.places
    _save_core({"user_name": "Budi Santoso", "user_nickname": "", "language": "en",
                "user_birthday": {"day": 1, "month": 2, "year": None}, "auto_start": True,
                "greet_on_startup": False, "user_fields": [{"key": "kantor", "value": "Jl. A"}],
                "onboarding_completed": True, "user_title": "Pak"})
    core.places.set_places([{"name": "Kantor", "lat": 1.1, "lon": 104.0}])
    core_before = core.api.load_data("Core")
    places_before = core.api.load_data("Places")
    calls = []
    done = onb.save(onb.prefill(), set_autostart=calls.append)
    assert done == {"errors": []} and calls == []
    assert core.api.load_data("Core") == core_before
    assert core.api.load_data("Places") == places_before


def test_blank_answers_keep_what_is_saved(onb):
    _save_core({"user_name": "Budi", "user_nickname": "Bro",
                "user_birthday": {"day": 1, "month": 2, "year": 1990}})
    onb.save(onb.Answers(name="", nickname="", birthday=None, greet=True), set_autostart=None)
    saved = _core()
    assert saved["user_name"] == "Budi" and saved["user_nickname"] == "Bro"
    assert saved["user_birthday"] == {"day": 1, "month": 2, "year": 1990}


def test_a_new_name_gets_its_first_word_as_nickname(onb):
    _save_core({"user_name": "Budi", "user_nickname": ""})
    onb.save(onb.Answers(name="Rafli Hidayat", nickname="Rafli Hidayat"))
    assert _core()["user_nickname"] == "Rafli Hidayat"      # what was typed
    onb.save(onb.Answers(name="Rafli Hidayat", nickname=""))
    assert _core()["user_nickname"] == "Rafli Hidayat"      # blank keeps it
    _save_core({"user_name": "Budi", "user_nickname": ""})
    onb.save(onb.Answers(name="Rafli Hidayat", nickname=""))
    assert _core()["user_nickname"] == "Rafli"


def test_turning_things_off(onb):
    _save_core({"auto_start": True, "onboarding_completed": True})
    calls = []
    done = onb.save(onb.Answers(autostart=False, greet=False), set_autostart=calls.append)
    assert calls == [False] and done["autostart"] is False and done["greet"] is False
    saved = _core()
    assert saved["auto_start"] is False and saved["greet_on_startup"] is False


def test_the_city_joins_the_places_already_there(onb, lang):
    import core.places
    lang("id")
    core.places.set_places([{"name": "Kantor", "lat": 1.1, "lon": 104.0},
                            {"name": "Rumah Mama", "lat": -5.1, "lon": 119.4}])
    office = core.places.get_main_id()
    onb.save(onb.Answers(place=BATAM))
    places = core.places.get_places()
    assert [p["name"] for p in places] == ["Kantor", "Rumah Mama", "Rumah"]
    assert places[0]["id"] == office and core.places.get_main()["name"] == "Rumah"


def test_the_city_moves_the_home_already_there(onb, lang):
    import core.places
    lang("en")
    core.places.set_places([{"name": "Kantor", "lat": 1.1, "lon": 104.0},
                            {"name": "Rumah", "lat": -6.2, "lon": 106.8}])
    home = core.places.get_places()[1]["id"]
    onb.save(onb.Answers(place=BATAM))
    places = core.places.get_places()
    assert [p["name"] for p in places] == ["Kantor", "Rumah"]   # "Rumah" is Home in Indonesian
    assert places[1]["id"] == home and places[1]["city"] == "Batam"
    assert core.places.get_main_id() == home


def test_cancel_changes_nothing_when_run_again(onb):
    import core.api
    _save_core({"user_name": "Budi", "onboarding_completed": True, "language": "en"})
    before = core.api.load_data("Core")
    assert onb.cancel(first_run=False, shown_language="id", opened_language="en") == "en"
    assert core.api.load_data("Core") == before
    _save_core({"user_name": "Budi", "onboarding_completed": True})
    assert onb.cancel(first_run=False, shown_language="id", opened_language="en") == "en"
    assert "language" not in _core()


def test_cancel_on_a_first_run_only_marks_the_welcome_done(onb):
    assert onb.cancel(first_run=True, shown_language="id", opened_language="en") == "id"
    assert _core() == {"onboarding_completed": True, "language": "id"}
    _save_core({"language": "en"})
    assert onb.cancel(first_run=True, shown_language="id", opened_language="en") == "en"
    assert _core() == {"onboarding_completed": True, "language": "en"}


def test_set_name_keeps_the_rest_of_the_profile(tmp_data_dir, lang):
    import core.personal
    _save_core({"user_title": "Kapten", "user_fields": [{"key": "hp", "value": "0812"}]})
    assert core.personal.set_name(" Rafli ", " Bro ") is True
    saved = _core()
    assert saved == {"user_title": "Kapten", "user_fields": [{"key": "hp", "value": "0812"}],
                     "user_name": "Rafli", "user_nickname": "Bro"}
    with pytest.raises(core.personal.ProfileError):
        core.personal.set_name("x" * 501)
    assert _core() == saved


# ------------------------------------------------------------
# The texts exist in both languages; the old wizard is gone
# ------------------------------------------------------------

def _literal_keys(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            keys.add(node.args[0].value)
    return keys


def test_every_welcome_text_exists_in_both_languages():
    import core.onboarding
    used = _literal_keys(os.path.join(ROOT, "core", "onboarding.py"))
    used |= _literal_keys(os.path.join(ROOT, "ui", "onboarding_dialog.py"))
    used |= {"onb_sky_" + key for key in core.onboarding.SKY_KEYS}
    used |= {"onb_ext_desc_" + ext_id for ext_id in core.onboarding.RECOMMENDED}
    used |= {f"onb_{page}_question" for page in ("hello", "name", "where", "birthday",
                                                  "aruna", "startup")} | {"onb_ext_question"}
    assert "onb_name_reply" in used and "onb_done_ready" in used
    en, id_ = _messages("en"), _messages("id")
    for code, messages in (("en", en), ("id", id_)):
        missing = sorted(k for k in used if k not in messages)
        assert not missing, f"locales/{code}.json lacks {missing}"
    welcome_en = {k for k in en if k.startswith("onb_")}
    welcome_id = {k for k in id_ if k.startswith("onb_")}
    assert welcome_en == welcome_id
    # A persona's version ("key@sweet") counts as its key (tests/test_persona.py checks them).
    unused = {k.split("@")[0] for k in welcome_en} - used
    assert not unused, f"unused welcome texts: {sorted(unused)}"
    for key in welcome_en:
        fields = lambda text: sorted(re.findall(r"\{(\w+)\}", text))
        assert fields(en[key]) == fields(id_[key]), key


def test_the_old_wizard_s_texts_are_gone():
    for code in ("en", "id"):
        messages = _messages(code)
        old = [k for k in messages if re.match(r"onb_(p\d|speak_|dlg_)", k)]
        assert not old and "dlg_onboard_title" not in messages, old


def test_the_welcome_speaks_casually_in_indonesian():
    messages = _messages("id")
    for key, text in messages.items():
        if key.startswith("onb_"):
            assert not re.search(r"\b(Anda|Saya)\b", text), (key, text)


def test_the_welcome_window_uses_only_accessible_controls():
    with open(os.path.join(ROOT, "ui", "onboarding_dialog.py"), encoding="utf-8") as f:
        source = f.read()
    for banned in ("FilePickerCtrl", "DirPickerCtrl", "SpinCtrlDouble", "DatePickerCtrl",
                   "wx.adv", "RadioButton"):
        assert banned not in source, banned


def test_a_cancelled_first_welcome_doesn_t_stop_hariku():
    with open(os.path.join(ROOT, "hariku.py"), encoding="utf-8") as f:
        source = f.read()
    assert "run_onboarding(first_run=True)" in source
    assert "exiting" not in source.split("run_onboarding(first_run=True)")[1][:300]
