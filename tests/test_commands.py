# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# core/commands.py: what the command bar makes of a typed or spoken command.
# The commands are the real actions, named as the core and the official
# extensions name them in English and Indonesian (read from their locale
# files), so a renamed action breaks these tests rather than the command bar.
# The misrecognitions are real: whisper.cpp's tiny model on the user's laptop.

import datetime
import json
import os
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.datetime(2026, 9, 24, 10, 40)      # a Thursday

# action id -> (extension folder, message key); the ids are the extensions' own
# (EXT_NAME + action name, fixed in every language).
EXTENSION_ACTIONS = {
    "Earthquakes.speak_latest": ("earthquake", "action_latest"),
    "Earthquakes.show_recent": ("earthquake", "action_recent"),
    "Flight Radar.speak_nearby": ("flight_radar", "action_nearby"),
    "Flight Radar.show_list": ("flight_radar", "action_list"),
    "Flight Radar.listen_atc": ("flight_radar", "action_listen_atc"),
    "Flight Radar.speak_tracked": ("flight_radar", "action_speak_tracked"),
    "Flight Radar.track_flight": ("flight_radar", "action_track"),
    "Morning Briefing.play_briefing": ("briefing", "action_play"),
    "Morning Briefing.evening_summary": ("briefing", "action_evening"),
    "Weather.speak_current_weather": ("weather", "action_speak"),
    "Weather.show_forecast": ("weather", "action_forecast"),
    "Sea Conditions.speak_sea": ("marine", "action_speak"),
    "Sea Conditions.show_forecast": ("marine", "action_forecast"),
    "Air Quality.speak_air": ("air_quality", "action_speak"),
    "Air Quality.show_forecast": ("air_quality", "action_forecast"),
    "Space.where_is_iss": ("space", "action_iss"),
    "Space.show_launches": ("space", "action_launches"),
    "Space.sun_and_moon": ("space", "action_sun_moon"),
    "Sleep Pattern.last_night": ("sleep_tracker", "action_last_night"),
    "Sleep Pattern.history": ("sleep_tracker", "action_history"),
    "Clipboard History.open_history": ("clipboard_history", "action_open"),
    "Clipboard History.speak_last": ("clipboard_history", "action_speak_last"),
    "Finance.open_finance": ("finance", "action_open"),
    "Finance.quick_add_expense": ("finance", "action_quick_add"),
    "Cockpit.pilot_weather": ("cockpit", "action_pilot"),
    "Cockpit.airport_weather": ("cockpit", "action_airports"),
    "Sound Themes.next_theme": ("sound_themes", "action_next_theme"),
}
CORE_ACTIONS = {
    "Calendar Navigation.prev_day": "nav_prev_day",
    "Calendar Navigation.next_day": "nav_next_day",
    "Calendar Navigation.prev_month": "nav_prev_month",
    "Calendar Navigation.next_month": "nav_next_month",
    "Calendar Navigation.prev_year": "nav_prev_year",
    "Calendar Navigation.next_year": "nav_next_year",
    "Calendar Navigation.start_of_week": "nav_start_week",
    "Calendar Navigation.end_of_week": "nav_end_week",
    "Calendar Navigation.start_of_month": "nav_start_month",
    "Calendar Navigation.end_of_month": "nav_end_month",
    "Calendar Navigation.today": "nav_today",
    "Hariku Core.volume_down": "nav_volume_down",
    "Hariku Core.volume_up": "nav_volume_up",
    "Hariku Core.input_gestures": "nav_open_prefs",
    "Hariku Core.manage_extensions": "nav_manage_ext",
    "Hariku Core.go_to_date": "nav_go_to_date",
    "Hariku Core.quit_app": "nav_quit_app",
    "Hariku Core.minimize_tray": "nav_minimize_tray",
    "Hariku Core.show_app": "nav_show_app",
    "Hariku Core.stop_voice": "nav_stop_voice",
    "Hariku Core.quick_reminder": "nav_quick_reminder",
    "Hariku Core.speak_time": "nav_speak_time",
    "Hariku Core.speak_date": "nav_speak_date",
    "Hariku Core.command_bar": "nav_command_bar",
    "Hariku Core.user_guide": "nav_user_guide",
    "Hariku Core.extension_guides": "nav_ext_guides",
}
# Actions registered with English names only, whatever the language.
ENGLISH_ONLY = {
    "Hariku Core.show_shortcuts": "Show Keyboard Shortcuts",
    "World Clock.speak_world_clock": "Speak world clock times",
    "World Clock.open_world_clock": "Open the world clock window",
    "Routines.manage_routines": "Manage Routines (Shortcuts)",
    "Routines.view_routines_log": "View Routines Log",
    "Filter.open_filter": "Open Filter dialog (tap twice to reset filters)",
    "Google Calendar.read_events": "Read events for selected date (tap twice for all)",
    "Google Calendar.add_event": "Add a new event",
}


def _messages(folder, language):
    with open(os.path.join(ROOT, folder, f"{language}.json"), encoding="utf-8") as f:
        return json.load(f)["messages"]


def real_actions(language):
    """{action id: an object with .description}, as Hariku registers them."""
    core = _messages("locales", language)
    found = {aid: core[key] for aid, key in CORE_ACTIONS.items()}
    for aid, (ext, key) in EXTENSION_ACTIONS.items():
        found[aid] = _messages(os.path.join("extensions", ext, "locales"), language)[key]
    found.update(ENGLISH_ONLY)
    return {aid: types.SimpleNamespace(description=name, callback=lambda: None,
                                       wants_tap_count=False)
            for aid, name in found.items()}


@pytest.fixture(params=["id", "en"])
def language(request):
    return request.param


@pytest.fixture
def commands(language):
    import core.commands
    return core.commands.commands(real_actions(language))


def parse_reminder(text, packs=("id", "en")):
    from core import when
    return when.parse(text, now=NOW, language="id", packs=list(packs))


# ------------------------------------------------------------
# The action ids and names these tests rely on exist
# ------------------------------------------------------------

def _registered_ids(folder):
    """ "EXT.action" ids the extension registers (read from its main.py)."""
    import ast
    import re
    path = os.path.join(ROOT, "extensions", folder, "main.py")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    ext_name = re.search(r'^EXT_NAME = "([^"]+)"', source, re.M)
    ids = set()
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "register_action" and len(node.args) >= 2):
            first, second = node.args[0], node.args[1]
            ext = (ext_name.group(1) if isinstance(first, ast.Name) and ext_name
                   else getattr(first, "value", None))
            if isinstance(second, ast.Constant):
                ids.add(f"{ext}.{second.value}")
    return ids


def test_the_extension_action_ids_are_real():
    for action_id, (folder, _key) in EXTENSION_ACTIONS.items():
        assert action_id in _registered_ids(folder), action_id


def test_builtin_aliases_name_real_actions():
    import core.commands
    known = set(EXTENSION_ACTIONS) | set(CORE_ACTIONS) | set(ENGLISH_ONLY)
    unknown = [aid for aid in core.commands.BUILTIN_ALIASES if aid not in known]
    assert not unknown, unknown


def test_core_registers_the_time_date_and_command_bar_actions():
    with open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8") as f:
        source = f.read()
    assert ('register_action("Hariku Core", "speak_time", _("nav_speak_time"), None, False, '
            'core.commands.say_time)') in source
    assert ('register_action("Hariku Core", "speak_date", _("nav_speak_date"), None, False, '
            'core.commands.say_date)') in source
    assert "register_hotkey(self.OnCommandBar)" in source


# ------------------------------------------------------------
# Words
# ------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Gampak terbaru.", "gampak terbaru"),
    ("Tua-tahari ini.", "tua tahari ini"),
    ("  JAM   berapa??  ", "jam berapa"),
    ("Gempaaa!!", "gempa"),
    ("saat", "sat"),                     # a letter said twice counts once
    ("what's flying nearby", "what flying nearby"),
    ("Cuáca", "cuaca"),                  # accents
    ("jam 11", "jam 11"),                # digits are left alone
    ("", ""), (None, ""),
])
def test_normalize(text, expected):
    import core.commands
    assert core.commands.normalize(text) == expected


def test_fillers_are_dropped_unless_that_is_everything():
    import core.commands as c
    assert c.words("Tolong ucapkan gempa terbaru dong") == ["gempa", "terbaru"]
    assert c.words("Jam berapa sekarang?") == ["jam", "berapa"]
    assert c.words("halo") == []
    assert c.words("the", keep_all_fillers=True) == ["the"]


def test_similarity_basics():
    import core.commands as c
    assert c.similarity(["gempa"], ["gempa"]) == 1.0
    assert c.similarity([], ["gempa"]) == 0.0
    # Short words must match closely: "halo" is not "saldo".
    assert c.similarity(["halo"], ["saldo"]) == 0.0
    assert 0.8 < c.similarity(["gampak", "terbaru"], ["gempa", "terbaru"]) < 1.0
    # Leaving out a word of the phrase costs: the list isn't the latest.
    assert c.similarity(["gampak", "terbaru"], ["gempa", "terbaru"]) > \
        c.similarity(["gampak", "terbaru"], ["daftar", "gempa", "terbaru"])


# ------------------------------------------------------------
# Matching the real commands, in both languages
# ------------------------------------------------------------

# What the recogniser wrote -> the action, and "run" (at once) or "ask".
MISRECOGNITIONS = [
    ("Gampak terbaru.", "Earthquakes.speak_latest", "run"),
    ("Pasawat di dekat sini.", "Flight Radar.speak_nearby", "run"),
    ("Baca kan briefing pagi.", "Morning Briefing.play_briefing", "run"),
    ("Jam berapa sekarang?", "Hariku Core.speak_time", "run"),
    ("Tua-tahari ini.", "Weather.speak_current_weather", "ask"),    # "cuaca hari ini"
    ("Gemba terbaru", "Earthquakes.speak_latest", "run"),
    ("Kuaca.", "Weather.speak_current_weather", "run"),
]


@pytest.mark.parametrize("text, action_id, kind", MISRECOGNITIONS)
def test_whisper_tiny_misrecognitions(commands, text, action_id, kind):
    import core.commands
    found = core.commands.match(text, commands)
    assert found.best.id == action_id, found
    assert found.kind == kind, found


CLEAR = [
    # Indonesian
    ("gempa terbaru", "Earthquakes.speak_latest"),
    ("daftar gempa", "Earthquakes.show_recent"),
    ("buka daftar gempa", "Earthquakes.show_recent"),
    ("pesawat terdekat", "Flight Radar.speak_nearby"),
    ("briefing", "Morning Briefing.play_briefing"),
    ("ringkasan malam", "Morning Briefing.evening_summary"),
    ("cuaca", "Weather.speak_current_weather"),
    ("cuaca hari ini", "Weather.speak_current_weather"),
    ("cuaca besok", "Weather.show_forecast"),
    ("berapa suhu", "Weather.speak_current_weather"),
    ("kualitas udara", "Air Quality.speak_air"),
    ("kondisi laut", "Sea Conditions.speak_sea"),
    ("tidur semalam", "Sleep Pattern.last_night"),
    ("jam berapa", "Hariku Core.speak_time"),
    ("tanggal berapa", "Hariku Core.speak_date"),
    ("hari apa sekarang", "Hariku Core.speak_date"),
    ("catat pengeluaran", "Finance.quick_add_expense"),
    ("pengaturan", "Hariku Core.input_gestures"),
    ("diam", "Hariku Core.stop_voice"),
    ("tolong bacakan briefing pagi dong", "Morning Briefing.play_briefing"),
    # English
    ("latest earthquake", "Earthquakes.speak_latest"),
    ("what's flying nearby", "Flight Radar.speak_nearby"),
    ("what time is it", "Hariku Core.speak_time"),
    ("the weather", "Weather.speak_current_weather"),
    ("weather forecast", "Weather.show_forecast"),
    ("evening summary", "Morning Briefing.evening_summary"),
    ("air quality", "Air Quality.speak_air"),
    ("where is the ISS?", "Space.where_is_iss"),
    ("Please play the morning briefing.", "Morning Briefing.play_briefing"),
]


@pytest.mark.parametrize("text, action_id", CLEAR)
def test_clear_commands_run(commands, text, action_id):
    import core.commands
    found = core.commands.match(text, commands)
    assert (found.best.id, found.kind) == (action_id, "run"), found


@pytest.mark.parametrize("text", ["asdf", "halo", "Apa kabar?", "Terima kasih.",
                                  "Selamat pagi.", "beli susu", "minum obat besok jam 8",
                                  "hmm", "ok", "."])
def test_nothing_close(commands, text):
    import core.commands
    assert core.commands.match(text, commands).kind == "none"


def test_the_command_bar_is_not_a_command(commands):
    assert "Hariku Core.command_bar" not in {c.id for c in commands}


def test_names_in_the_user_language_match_too():
    import core.commands
    candidates = core.commands.commands(real_actions("id"))
    found = core.commands.match("Ucapkan gempa terkini dari BMKG", candidates)
    assert (found.best.id, found.kind) == ("Earthquakes.speak_latest", "run")
    candidates = core.commands.commands(real_actions("en"))
    found = core.commands.match("Speak the latest earthquake from BMKG", candidates)
    assert (found.best.id, found.kind) == ("Earthquakes.speak_latest", "run")


def test_ties_are_asked_not_run():
    import core.commands as c
    same = [c.Command("A.one", "Open the list"), c.Command("B.two", "Open the list")]
    found = c.match("open the list", same)
    assert found.score == 1.0 and found.kind == "ask"


# ------------------------------------------------------------
# Aliases from extensions
# ------------------------------------------------------------

def test_extensions_add_aliases_with_a_title():
    import core.commands as c
    actions = {"Pets.feed": types.SimpleNamespace(description="Feed the cat")}
    try:
        assert c.add_aliases("Pets.feed", ["kasih makan kucing", "", 5, "feed kitty"],
                             title="Makan kucing") == ["kasih makan kucing", "feed kitty"]
        c.add_aliases("Pets.feed", "kasih makan kucing")        # no duplicates
        assert c.aliases_for("Pets.feed") == ["kasih makan kucing", "feed kitty"]
        (command,) = c.commands(actions)
        assert command.title == "Makan kucing"
        found = c.match("kasih makan kucing", [command])
        assert found.best.id == "Pets.feed" and found.kind == "run"
    finally:
        assert c.remove_aliases("Pets.feed") is True
    assert c.aliases_for("Pets.feed") == []
    assert c.commands(actions)[0].title == "Feed the cat"
    with pytest.raises(ValueError):
        c.add_aliases("", ["x"])


def test_vocabulary_holds_names_and_aliases():
    import core.commands as c
    words = c.vocabulary(real_actions("id"))
    assert "Ucapkan gempa terkini dari BMKG" in words and "gempa terbaru" in words
    assert "jam berapa" in words
    assert "Buka bilah perintah: ketik atau ucapkan perintah" not in words


# ------------------------------------------------------------
# Yes or no
# ------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("ya", "yes"), ("Ya.", "yes"), ("Iya, simpan.", "yes"), ("simpan", "yes"),
    ("yes", "yes"), ("Save.", "yes"), ("oke", "yes"), ("Iyaa", "yes"), ("betul", "yes"),
    ("tidak", "no"), ("Tidak.", "no"), ("batal", "no"), ("no", "no"), ("Cancel!", "no"),
    ("bukan", "no"), ("nggak", "no"), ("tidak jadi", "no"), ("jangan", "no"),
    ("ya tidak", "no"),                  # "no" wins
    ("pasang", "yes"), ("Set it.", "yes"), ("pasang aja", "yes"),   # "..., Pasang?" (alarms)
    ("ya, pasang", "yes"), ("jangan pasang", "no"),
    ("pasang alarm jam 6", None), ("set alarm 6", None),            # a new command
    ("gempa terbaru", None), ("", None),
    ("ya tolong ingatkan aku minum obat besok", None),   # a new command
])
def test_answers(text, expected):
    import core.commands
    assert core.commands.answer(text) == expected


# ------------------------------------------------------------
# A reminder or a command
# ------------------------------------------------------------

def _decide(text, commands):
    import core.commands
    return core.commands.decide(text, commands, parse=parse_reminder)


@pytest.mark.parametrize("text", [
    "ingatkan aku minum obat besok jam 8",
    "remind me to call mom tomorrow at 7pm",
    "ingatkan aku cek gempa terbaru besok",       # a trigger, whatever follows
    "minum obat besok jam 8",
    "rapat tiap Senin jam 9",
    "bayar listrik tanggal 5",
    "call Budi in 30 minutes",
])
def test_reminder_sentences(commands, text):
    decision = _decide(text, commands)
    assert decision.kind == "reminder", decision
    assert decision.result.ok, decision.result


@pytest.mark.parametrize("text, action_id", [
    ("Baca kan briefing pagi.", "Morning Briefing.play_briefing"),   # "pagi" is a time word
    ("ringkasan malam", "Morning Briefing.evening_summary"),         # so is "malam"
    ("cuaca hari ini", "Weather.speak_current_weather"),             # and "hari ini"
    ("cuaca besok", "Weather.show_forecast"),                        # and "besok"
    ("Gampak terbaru.", "Earthquakes.speak_latest"),
    ("Jam berapa sekarang?", "Hariku Core.speak_time"),
])
def test_commands_with_date_words_run(commands, text, action_id):
    decision = _decide(text, commands)
    assert (decision.kind, decision.action_id) == ("run", action_id), decision


def test_a_close_call_is_asked(commands):
    decision = _decide("Tua-tahari ini.", commands)
    assert (decision.kind, decision.action_id) == ("confirm", "Weather.speak_current_weather")
    assert decision.alternative is None


def test_a_close_call_with_a_weak_date_offers_the_reminder_after_no():
    import core.commands as c
    candidates = [c.Command("Weather.speak_current_weather", "Speak the current weather",
                            ["cuaca"])]
    decision = c.decide("cuaka sore", candidates, parse=parse_reminder)
    assert decision.kind == "confirm", decision
    assert decision.alternative is not None and decision.alternative.ok


def test_a_date_without_a_title_is_still_a_reminder(commands):
    decision = _decide("besok jam 8", commands)
    assert decision.kind == "reminder" and not decision.result.ok
    assert "no_title" in decision.result.problems


def test_not_understood_and_empty(commands):
    assert _decide("asdf qwerty", commands).kind == "unknown"
    assert _decide("   ", commands).kind == "empty"
    assert _decide("halo", commands).kind == "unknown"


def test_date_looking_words_offer_the_quick_reminder():
    import core.commands as c
    result = types.SimpleNamespace(trigger="", recognised=[], title="Rapat jam", ok=False,
                                   unparsed=["jam"], components={})
    decision = c.decide("rapat jam", [], parse=lambda text: result)
    assert decision.kind == "offer_reminder" and decision.result is result


def test_a_broken_reader_does_not_stop_commands(commands):
    import core.commands as c

    def broken(text):
        raise RuntimeError("oops")

    decision = c.decide("gempa terbaru", commands, parse=broken)
    assert (decision.kind, decision.action_id) == ("run", "Earthquakes.speak_latest")


def test_strong_and_weak_dates():
    import core.commands as c
    assert c.strong_when(parse_reminder("rapat besok"))
    assert c.strong_when(parse_reminder("rapat jam 8"))
    assert c.strong_when(parse_reminder("olahraga tiap hari"))
    assert c.strong_when(parse_reminder("arisan hari Senin"))
    assert not c.strong_when(parse_reminder("briefing pagi"))
    assert not c.strong_when(parse_reminder("cuaca hari ini"))
    assert not c.strong_when(parse_reminder("gempa terbaru"))


def test_looks_like_reminder():
    import core.commands as c
    assert c.looks_like_reminder("ingatkan aku minum obat", parse=parse_reminder)
    assert c.looks_like_reminder("minum obat besok jam 8", parse=parse_reminder)
    assert not c.looks_like_reminder("gempa terbaru", parse=parse_reminder)


# ------------------------------------------------------------
# Running, the recogniser, the fallback, the time
# ------------------------------------------------------------

def test_run_action_like_a_hotkey():
    import core.commands as c
    calls = []

    def tapped(tap_count=1):
        calls.append(tap_count)

    def broken():
        raise RuntimeError("oops")

    actions = {"A.plain": types.SimpleNamespace(callback=lambda: calls.append("plain"),
                                                wants_tap_count=False),
               "A.tapped": types.SimpleNamespace(callback=tapped, wants_tap_count=True),
               "A.broken": types.SimpleNamespace(callback=broken, wants_tap_count=False)}
    assert c.run_action("A.plain", actions) and c.run_action("A.tapped", actions)
    assert calls == ["plain", 1]
    assert c.run_action("A.broken", actions) is False
    assert c.run_action("A.gone", actions) is False


def test_one_listener_at_a_time():
    import core.commands as c
    first = (lambda on_event: True, lambda discard=False: None)
    second = (lambda on_event: True, lambda discard=False: None)
    try:
        assert c.register_listener(*first, is_available=lambda: False,
                                   listen_on_open=lambda: True, name="One")
        assert c.get_listener().name == "One"
        assert c.get_listener().is_available() is False
        assert c.get_listener().listen_on_open() is True
        c.register_listener(*second, name="Two")
        assert c.get_listener().name == "Two" and c.get_listener().is_available()
        assert c.unregister_listener(first[0]) is False     # not the registered one
        assert c.unregister_listener(second[0]) is True
        assert c.get_listener() is None
        with pytest.raises(TypeError):
            c.register_listener(None, second[1])

        def broken():
            raise RuntimeError("oops")

        c.register_listener(*second, is_available=broken)
        assert c.get_listener().is_available() is False
    finally:
        c.unregister_listener()


def test_fallback_hook():
    import core.commands as c
    candidates = [c.Command("Weather.speak_current_weather", "Speak the current weather")]
    assert c.ask_fallback("anything", candidates) is None           # none registered
    try:
        c.set_fallback(lambda text, commands: "Weather.speak_current_weather")
        assert c.ask_fallback("is it going to rain", candidates).id == \
            "Weather.speak_current_weather"
        c.set_fallback(lambda text, commands: "Nothing.here")
        assert c.ask_fallback("x", candidates) is None
        c.set_fallback(lambda text, commands: 1 / 0)
        assert c.ask_fallback("x", candidates) is None
        with pytest.raises(TypeError):
            c.set_fallback("not callable")
    finally:
        c.set_fallback(None)
    assert c.get_fallback() is None


@pytest.fixture
def core_in(monkeypatch):
    from core import i18n

    def use(code):
        i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
        monkeypatch.setattr(i18n, "_current_language", code)

    return use


def test_time_and_date_answers(core_in):
    import core.commands as c
    when = datetime.datetime(2026, 9, 24, 7, 5)
    core_in("id")
    assert c.time_text(when) == "Sekarang jam 07:05."
    assert c.date_text(when) == "Hari ini Kamis, 24 September 2026."
    core_in("en")
    assert c.time_text(when) == "It's 07:05."
    assert c.date_text(when) == "Today is Thursday, 24 September 2026."


def test_the_time_is_spoken_with_speak(monkeypatch):
    import core.commands as c
    import core.speech
    said = []
    monkeypatch.setattr(core.speech, "speak", lambda text, interrupt=False: said.append(text))
    c.say_time()
    c.say_date()
    assert len(said) == 2 and all(said)


def test_command_bar_strings_exist_in_both_languages():
    import ast
    used = set()
    for path in (os.path.join(ROOT, "core", "commands.py"),
                 os.path.join(ROOT, "ui", "command_bar.py"),
                 os.path.join(ROOT, "ui", "main_window.py")):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and str(node.args[0].value).startswith(("cmd_", "nav_", "menu_"))):
                used.add(node.args[0].value)
    used |= {"menu_command_bar", "voice_chk_command"}
    assert "cmd_did_you_mean" in used and "cmd_voice_missing" in used
    for code in ("en", "id"):
        messages = _messages("locales", code)
        assert not sorted(used - set(messages)), f"locales/{code}.json lacks some keys"
    # Spoken replies may say "kamu"/"aku", like the quick reminder's read-back.
    indonesian = _messages("locales", "id")
    assert indonesian["cmd_not_understood"] == "Hmm, itu belum masuk kamusku. Coba pakai kata lain?"


# ------------------------------------------------------------
# Commands with content: intents (core 2.9)
# ------------------------------------------------------------

@pytest.fixture
def no_intents(monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    return core.commands


def _ignore(request):
    return None


def test_intent_patterns_are_checked(no_intents):
    c = no_intents
    for bad in ("catat", "{text}", "catat {text} dan {text}", ""):
        with pytest.raises(ValueError):
            c.add_intent("Notes.add", [bad], _ignore)
    with pytest.raises(TypeError):
        c.add_intent("Notes.add", ["catat {text}"], "not a function")
    with pytest.raises(ValueError):
        c.add_intent("Notes.add", [], _ignore)
    with pytest.raises(TypeError):
        c.Reply("x", confirm="yes")


@pytest.mark.parametrize("text, slot", [
    ("catat beli gula", "beli gula"),
    ("Catat: beli Gula Aren.", "beli Gula Aren"),              # capitals kept, edges trimmed
    ("Tolong catat beli gula dong", "beli gula dong"),         # a filler before it is skipped
    ("Aruna, catat beli gula", "beli gula"),
    ("katat beli gula", "beli gula"),                          # misheard
    ("tambahkan kopi susu ke daftar belanja", "kopi susu"),   # a pattern with words after
    ("Tambahkan kopi ke daftar belanja.", "kopi"),
    ("note: call the bank", "call the bank"),
])
def test_intents_match_and_keep_the_text(no_intents, text, slot):
    c = no_intents
    c.add_intent("Notes.add", ["catat {text}", "note {text}",
                               "tambahkan {text} ke daftar belanja"], _ignore)
    found = c.match_intents(text)
    assert [(m.intent.id, m.text) for m in found] == [("Notes.add", slot)]


@pytest.mark.parametrize("text", ["catat", "catat.", "gempa terbaru", "catatan hari ini",
                                  "ke daftar belanja", "beli gula"])
def test_no_intent_without_its_words_or_content(no_intents, text):
    c = no_intents
    c.add_intent("Notes.add", ["catat {text}", "{text} ke daftar belanja"], _ignore)
    assert c.match_intents(text) == []


def test_the_most_specific_pattern_wins(no_intents):
    c = no_intents
    c.add_intent("Timer.start", ["timer {text}"], _ignore)
    c.add_intent("Timer.stop", ["hentikan timer {text}"], _ignore)
    found = c.match_intents("hentikan timer mie")
    assert [(m.intent.id, m.text) for m in found] == [("Timer.stop", "mie")]
    found = c.match_intents("timer mie 3 menit")
    assert [m.intent.id for m in found] == ["Timer.start"]


def test_a_matcher_takes_sentences_without_fixed_words(no_intents):
    # Core 2.11: "25 x 4" has no word to make a pattern of.
    c = no_intents
    assert c.INTENT_MATCHERS is True
    seen = []

    def matcher(text):
        seen.append(text)
        return text if " x " in text else None

    c.add_intent("Calc.calculate", ["hitung {text}"], _ignore, matcher=matcher)
    c.add_intent("Timer.start", ["timer {text}"], _ignore)
    found = c.match_intents("25  x 4")
    assert [(m.intent.id, m.text, m.size) for m in found] == [("Calc.calculate", "25 x 4", 0)]
    # A pattern of its own wins over the matcher, which isn't asked then.
    seen.clear()
    assert [(m.intent.id, m.text) for m in c.match_intents("hitung 2 x 3")] == \
        [("Calc.calculate", "2 x 3")]
    assert seen == []
    # A sentence the matcher takes is asked after every pattern of every intent.
    found = c.match_intents("timer 2 x 3")
    assert [(m.intent.id, m.size) for m in found] == [("Timer.start", 1), ("Calc.calculate", 0)]
    assert c.match_intents("gempa terbaru") == []
    # Patterns may be left out when there is a matcher; the vocabulary gets nothing.
    c.add_intent("Calc.calculate", [], _ignore, matcher=lambda text: True)
    assert [m.text for m in c.match_intents("apa saja")] == ["apa saja"]
    assert c.match_intents("x" * (c.MATCHER_MAX_CHARS + 1)) == []
    with pytest.raises(TypeError):
        c.add_intent("Calc.calculate", [], _ignore, matcher="not a function")


def test_decide_asks_a_matcher_too(no_intents):
    c = no_intents
    c.add_intent("Calc.calculate", [], _ignore,
                 matcher=lambda text: text if text.startswith("25") else None)
    actions = c.commands(real_actions("id"))
    decision = c.decide("25 x 4", actions, parse=parse_reminder)
    assert decision.kind == "intent" and decision.intents[0].text == "25 x 4"
    assert decision.fallback is not None and decision.fallback.kind != "intent"
    assert c.decide("gempa terbaru", actions, parse=parse_reminder).kind == "run"


def test_a_failing_matcher_is_no_match(no_intents, caplog):
    c = no_intents

    def broken(text):
        raise RuntimeError("oops")

    c.add_intent("Calc.calculate", [], _ignore, matcher=broken)
    c.add_intent("Notes.add", [], _ignore, matcher=lambda text: "   ")
    assert c.match_intents("25 x 4") == []
    assert "Calc.calculate" in caplog.text


def test_adding_again_replaces_and_removing_works(no_intents):
    c = no_intents
    c.add_intent("Notes.add", ["catat {text}"], _ignore, title="Notes")
    c.add_intent("Notes.add", ["tulis {text}"], _ignore)
    assert [i.id for i in c.intents()] == ["Notes.add"]
    assert c.match_intents("catat x") == [] and c.match_intents("tulis x")
    assert c.remove_intent("Notes.add") is True and c.remove_intent("Notes.add") is False
    assert c.intents() == []


def test_vocabulary_holds_the_patterns_words(no_intents):
    c = no_intents
    c.add_intent("Notes.add", ["catat {text}", "tambahkan {text} ke daftar belanja"], _ignore)
    words = c.vocabulary(real_actions("id"))
    assert "catat" in words and "tambahkan ke daftar belanja" in words


def test_decide_puts_intents_before_dates_but_after_reminder_triggers(no_intents):
    c = no_intents
    c.add_intent("Timer.start", ["timer {text}"], _ignore)
    c.add_intent("Notes.add", ["ingat {text}"], _ignore)
    actions = c.commands(real_actions("id"))
    decision = c.decide("timer mie 10 menit", actions, parse=parse_reminder)
    assert decision.kind == "intent"
    assert [(m.intent.id, m.text) for m in decision.intents] == [("Timer.start", "mie 10 menit")]
    assert decision.fallback is not None and decision.fallback.kind != "intent"
    decision = c.decide("ingatkan aku minum obat besok jam 8", actions, parse=parse_reminder)
    assert decision.kind == "reminder"
    decision = c.decide("gempa terbaru", actions, parse=parse_reminder)
    assert decision.kind == "run"                        # no intent: as before


def test_reply_of(no_intents):
    c = no_intents
    assert c.Reply.of(None) is None
    reply = c.Reply.of("Dicatat.")
    assert isinstance(reply, c.Reply) and reply.say == "Dicatat." and not reply.wait
    same = c.Reply("x", wait=True)
    assert c.Reply.of(same) is same


# ------------------------------------------------------------
# Core 2.9: answers told in steps (hold_answer, show_answer)
# ------------------------------------------------------------

@pytest.fixture
def no_hold(monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_hold", {"until": 0.0})
    monkeypatch.setattr(core.commands, "_answer_sink", None)
    return core.commands


def test_hold_answer_is_bounded(no_hold):
    c = no_hold
    assert c.answer_hold_left() == 0
    assert c.hold_answer(20) == 20 and 19 < c.answer_hold_left() <= 20
    assert c.hold_answer(10_000) == c.MAX_HOLD_SECONDS
    assert c.hold_answer("nonsense") == 0 and c.answer_hold_left() == 0
    assert c.hold_answer(-5) == 0 and c.answer_hold_left() == 0


def test_show_answer_needs_the_bar(no_hold):
    c = no_hold
    assert c.show_answer("こんばんは") is False            # no Aruna: nothing shows it
    shown = []

    def sink(text):
        shown.append(text)
        return True

    c.set_answer_sink(sink)
    assert c.show_answer("  Konbanwa!\n Tōkyō e yōkoso! ") is True
    assert c.show_answer("   ") is False
    assert shown == ["Konbanwa! Tōkyō e yōkoso!"]
    assert c.remove_answer_sink(lambda text: True) is False   # another bar's: kept
    assert c.remove_answer_sink(sink) is True
    assert c.show_answer("later") is False


def test_a_failing_sink_is_no_answer(no_hold):
    c = no_hold

    def boom(text):
        raise RuntimeError("closed")

    c.set_answer_sink(boom)
    assert c.show_answer("x") is False
