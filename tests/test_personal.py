# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for core.personal (the Profile: name, nickname, birthday, own
# placeholders and %token% expansion; the greeting; quiet hours) and for
# reminders being announced with it filled in.
# Every test runs on a temporary data folder, never the user's real Core.json.

import ast
import datetime
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def personal(tmp_data_dir):
    import core.personal
    return core.personal


def _save_core(data):
    import core.api
    core.api.save_data("Core", data)


def _load_core():
    import core.api
    return core.api.load_data("Core")


@pytest.fixture
def lang(monkeypatch):
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


# ------------------------------------------------------------
# Name and nickname
# ------------------------------------------------------------

class TestNameAndNickname:
    def test_nothing_saved(self, personal):
        assert personal.get_name() == ""
        assert personal.get_nickname() == ""
        assert personal.get_fields() == []

    def test_name_is_trimmed(self, personal):
        _save_core({"user_name": "  Rafli  "})
        assert personal.get_name() == "Rafli"

    def test_legacy_placeholder_name_means_no_name(self, personal):
        # The first-run wizard saved "User" for a blank name before 2.7.
        _save_core({"user_name": "User"})
        assert personal.get_name() == ""
        assert personal.get_nickname() == ""
        assert personal.expand("Hi %myname%.") == "Hi ."

    def test_nickname_falls_back_to_name(self, personal):
        _save_core({"user_name": "Rafli"})
        assert personal.get_nickname() == "Rafli"
        _save_core({"user_name": "Rafli", "user_nickname": "   "})
        assert personal.get_nickname() == "Rafli"

    def test_nickname_wins(self, personal):
        _save_core({"user_name": "Rafli", "user_nickname": " Bro "})
        assert personal.get_name() == "Rafli"
        assert personal.get_nickname() == "Bro"

    def test_nickname_without_name(self, personal):
        _save_core({"user_name": "User", "user_nickname": "Bro"})
        assert personal.get_name() == ""
        assert personal.get_nickname() == "Bro"

    def test_non_text_values_are_ignored(self, personal):
        _save_core({"user_name": 42, "user_nickname": None, "user_fields": "junk"})
        assert personal.get_name() == ""
        assert personal.get_nickname() == ""
        assert personal.get_fields() == []

    def test_get_profile_keeps_the_nickname_as_typed(self, personal):
        _save_core({"user_name": "Rafli", "user_fields": [{"key": "kantor", "value": "Jl. A"}]})
        assert personal.get_profile() == {"name": "Rafli", "nickname": "", "title": "",
                                          "birthday": None,
                                          "fields": [("kantor", "Jl. A")],
                                          "greet_on_startup": True, "custom_greeting": "",
                                          "custom_greeting_boot_only": False}


# ------------------------------------------------------------
# Custom fields as stored
# ------------------------------------------------------------

def test_fields_keep_their_order(personal):
    _save_core({"user_fields": [{"key": "kantor", "value": "Jl. Sudirman 1"},
                                {"key": "hp", "value": "0812"},
                                ["rumah", "Bekasi"]]})
    assert personal.get_fields() == [("kantor", "Jl. Sudirman 1"), ("hp", "0812"),
                                     ("rumah", "Bekasi")]


def test_broken_stored_fields_are_skipped(personal):
    _save_core({"user_fields": [
        {"key": "Kantor", "value": "A"},        # read as lower-case
        {"key": "kantor", "value": "duplicate"},
        {"key": "time", "value": "reserved"},
        {"key": "has space", "value": "x"},
        {"key": "", "value": "x"},
        {"value": "no key"},
        "junk", None, 7,
        {"key": "angka", "value": 12},
        {"key": "kosong", "value": None},
    ]})
    assert personal.get_fields() == [("kantor", "A"), ("angka", "12"), ("kosong", "")]


# ------------------------------------------------------------
# expand()
# ------------------------------------------------------------

@pytest.fixture
def profile(personal):
    _save_core({"user_name": "Rafli", "user_nickname": "Bro",
                "user_fields": [{"key": "kantor", "value": "Jl. Sudirman 1"},
                                {"key": "sapaan", "value": "halo %myname%"},
                                {"key": "kosong", "value": ""}]})
    return personal


class TestExpand:
    def test_profile_tokens(self, profile):
        assert profile.expand("Hi %myname%, or %mynickname%.") == "Hi Rafli, or Bro."

    def test_case_insensitive(self, profile):
        assert profile.expand("%MyName% %MYNICKNAME% %Kantor%") == "Rafli Bro Jl. Sudirman 1"

    def test_custom_fields(self, profile):
        assert profile.expand("Go to %kantor%.") == "Go to Jl. Sudirman 1."

    def test_unknown_tokens_untouched(self, profile):
        assert profile.expand("%nope% and %USERPROFILE%\\x") == "%nope% and %USERPROFILE%\\x"

    @pytest.mark.parametrize("text", [
        "50%", "100% done", "50%-70%", "%", "%%", "a % b % c", "%%%", "% myname %",
        "%my name%", "", "no tokens at all",
    ])
    def test_bare_percent_signs_untouched(self, profile, text):
        assert profile.expand(text) == text

    def test_percent_next_to_tokens(self, profile):
        assert profile.expand("100%%myname%") == "100%Rafli"
        assert profile.expand("%%myname%%") == "%Rafli%"
        assert profile.expand("50% off for %myname%") == "50% off for Rafli"

    def test_unknown_token_does_not_swallow_the_next(self, profile):
        # The closing % of an unknown token may open a real one.
        assert profile.expand("%foo%myname%") == "%fooRafli"

    def test_single_pass(self, profile):
        # A value holding a token is inserted as it is, never expanded again.
        assert profile.expand("%sapaan%") == "halo %myname%"
        assert profile.expand("%x%", extra={"x": "%myname%"}) == "%myname%"

    def test_empty_values(self, profile):
        assert profile.expand("[%kosong%]") == "[]"

    def test_empty_profile_expands_to_nothing(self, personal):
        assert personal.expand("Hi %myname%%mynickname%!") == "Hi !"

    def test_extra_tokens(self, profile):
        assert profile.expand("%city%, %CITY%", extra={"city": "Jakarta"}) == "Jakarta, Jakarta"
        assert profile.expand("%n%", extra={"n": 42}) == "42"
        assert profile.expand("[%none%]", extra={"none": None}) == "[]"

    def test_extra_is_checked_before_the_profile(self, profile):
        assert profile.expand("%myname%", extra={"myname": "Other"}) == "Other"

    def test_extra_namespaced_keys(self, profile):
        extra = {"var:greeting": "Hello", "var:My Var": "spaced"}
        assert profile.expand("%var:greeting% %var:My Var% %VAR:GREETING%", extra) == \
            "Hello spaced Hello"
        assert profile.expand("%var:missing%", extra) == "%var:missing%"

    def test_not_text_is_returned_unchanged(self, profile):
        assert profile.expand(None) is None
        assert profile.expand(5) == 5

    def test_profile_is_read_only_when_needed(self, profile, monkeypatch):
        reads = []
        real = profile._config
        monkeypatch.setattr(profile, "_config", lambda: reads.append(1) or real())
        assert profile.expand("battery 50%, %x%", extra={"x": "1"}) == "battery 50%, 1"
        assert reads == []
        profile.expand("%myname% %mynickname% %kantor%")
        assert reads == [1]


# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------

class TestValidation:
    @pytest.mark.parametrize("raw, stored", [
        ("kantor", "kantor"), ("Kantor", "kantor"), ("%kantor%", "kantor"),
        ("  no_hp2 ", "no_hp2"), ("x" * 32, "x" * 32), ("_", "_"),
    ])
    def test_good_keys(self, personal, raw, stored):
        assert personal.check_key(raw) == stored

    @pytest.mark.parametrize("key", sorted(
        ["myname", "mynickname", "mybirthday", "myage", "time", "date", "battery", "app",
         "clipboard", "ssid", "ram", "cpu", "events", "var", "MyName", "%TIME%", "MyAge"]))
    def test_reserved_keys(self, personal, key):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_key(key)
        assert e.value.code == "key_reserved" and e.value.field == "key"

    @pytest.mark.parametrize("key", ["has space", "dash-key", "dot.key", "kötü", "a:b", "%x%y%"])
    def test_bad_characters(self, personal, key):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_key(key)
        assert e.value.code == "key_chars"

    @pytest.mark.parametrize("key", ["", "   ", "%%", None])
    def test_empty_key(self, personal, key):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_key(key)
        assert e.value.code == "key_empty"

    def test_long_key(self, personal):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_key("x" * 33)
        assert e.value.code == "key_too_long"

    def test_duplicate_key(self, personal):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_key("KANTOR", taken=["hp", "kantor"])
        assert e.value.code == "key_duplicate"
        assert personal.check_key("kantor", taken=["hp"]) == "kantor"

    def test_value_length(self, personal):
        assert personal.check_value("  x  ") == "x"
        assert personal.check_value(None) == ""
        assert personal.check_value("x" * 500) == "x" * 500
        with pytest.raises(personal.ProfileError) as e:
            personal.check_value("x" * 501)
        assert e.value.code == "value_too_long" and e.value.field == "value"

    def test_messages_are_translated(self, personal, lang):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_key("time")
        assert str(e.value) == "%time% is already used by Hariku. Choose another name."
        lang("id")
        with pytest.raises(personal.ProfileError) as e:
            personal.check_key("kantor", taken=["kantor"])
        assert str(e.value) == "Anda sudah punya %kantor%. Pilih nama lain."
        with pytest.raises(personal.ProfileError) as e:
            personal.check_value("x" * 501)
        assert "500" in str(e.value)


# ------------------------------------------------------------
# set_profile()
# ------------------------------------------------------------

class TestSetProfile:
    def test_saves_and_reads_back(self, personal):
        _save_core({"date_format": "%d/%m/%Y", "onboarding_completed": True, "user_name": "User"})
        assert personal.set_profile(" Rafli ", " Bro ",
                                    [("%Kantor%", " Jl. Sudirman 1 "), ("hp", "0812")]) is True
        saved = _load_core()
        assert saved["user_name"] == "Rafli"
        assert saved["user_nickname"] == "Bro"
        assert saved["user_fields"] == [{"key": "kantor", "value": "Jl. Sudirman 1"},
                                        {"key": "hp", "value": "0812"}]
        # Everything else in Core.json is kept.
        assert saved["date_format"] == "%d/%m/%Y" and saved["onboarding_completed"] is True
        assert personal.get_name() == "Rafli"
        assert personal.get_nickname() == "Bro"
        assert personal.get_fields() == [("kantor", "Jl. Sudirman 1"), ("hp", "0812")]
        assert personal.expand("%mynickname% @ %KANTOR%") == "Bro @ Jl. Sudirman 1"

    def test_blank_profile(self, personal):
        personal.set_profile("", "", [])
        saved = _load_core()
        assert saved["user_name"] == "" and saved["user_nickname"] == "" and saved["user_fields"] == []
        assert personal.get_nickname() == ""

    @pytest.mark.parametrize("fields, code, index", [
        ([("kantor", "a"), ("Kantor", "b")], "key_duplicate", 1),
        ([("time", "a")], "key_reserved", 0),
        ([("ok", "a"), ("bad key", "b")], "key_chars", 1),
        ([("ok", "x" * 501)], "value_too_long", 0),
    ])
    def test_invalid_fields_save_nothing(self, personal, fields, code, index):
        _save_core({"user_name": "Before"})
        with pytest.raises(personal.ProfileError) as e:
            personal.set_profile("After", "", fields)
        assert e.value.code == code and e.value.index == index
        assert _load_core() == {"user_name": "Before"}

    @pytest.mark.parametrize("name, nickname, code", [
        ("x" * 501, "", "name_too_long"), ("Rafli", "x" * 501, "nickname_too_long"),
    ])
    def test_long_name_or_nickname(self, personal, name, nickname, code):
        with pytest.raises(personal.ProfileError) as e:
            personal.set_profile(name, nickname, [])
        assert e.value.code == code
        assert _load_core() == {}


# ------------------------------------------------------------
# Every message the Profile page and core.personal use exists in en and id
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


def test_profile_messages_exist_in_both_languages():
    panels = os.path.join(ROOT, "core", "core_panels.py")
    personal_py = os.path.join(ROOT, "core", "personal.py")
    used = _literal_keys(panels, ("profile_", "prefs_tab_", "prefs_btn_", "error", "quiet_"))
    used |= _literal_keys(personal_py, ("greet_", "month_", "profile_", "token_"))
    import core.personal
    used |= {"token_desc_" + key for key in core.personal.DYNAMIC_KEYS}
    used |= {f"{key}_name" for key in ("greet_morning", "greet_midday", "greet_afternoon",
                                       "greet_evening")}
    with open(personal_py, encoding="utf-8") as f:
        source = f.read()
    codes = set(re.findall(r'ProfileError\("(\w+)"', source))
    codes |= {f"{field}_too_long" for field in ("name", "nickname", "value", "title", "greeting")}
    used |= {"profile_err_" + code for code in codes}
    assert "profile_err_key_reserved" in used and "profile_lbl_fields" in used
    for code in ("en", "id"):
        with open(os.path.join(ROOT, "locales", f"{code}.json"), encoding="utf-8") as f:
            messages = json.load(f)["messages"]
        missing = sorted(k for k in used if k not in messages)
        assert not missing, f"locales/{code}.json lacks {missing}"


def test_onboarding_mentions_where_to_change_the_name():
    for code, words in (("en", "Preferences, Profile"), ("id", "Pengaturan, Profil")):
        with open(os.path.join(ROOT, "locales", f"{code}.json"), encoding="utf-8") as f:
            assert words in json.load(f)["messages"]["onb_p3_msg_name"]


def test_onboarding_no_longer_saves_user_for_a_blank_name():
    with open(os.path.join(ROOT, "ui", "onboarding_dialog.py"), encoding="utf-8") as f:
        source = f.read()
    assert 'or "User"' not in source


def test_core_always_imports_personal():
    # Nuitka only compiles modules the core imports; core.reminders is imported
    # by hariku.py at startup.
    for rel in (("core", "reminders.py"), ("core", "core_panels.py")):
        with open(os.path.join(ROOT, *rel), encoding="utf-8") as f:
            assert re.search(r"^import core\.personal$", f.read(), re.M), rel


# ------------------------------------------------------------
# Reminders: announced with the profile filled in, stored raw
# ------------------------------------------------------------

@pytest.fixture
def reminders(tmp_data_dir, monkeypatch):
    # Imported only inside the temporary data folder, and pointed at a file in it.
    import core.reminders
    monkeypatch.setattr(core.reminders, "REMINDERS_FILE",
                        os.path.join(tmp_data_dir, "reminders_personal.json"))
    _save_core({"user_name": "Rafli", "user_nickname": "Bro",
                "user_fields": [{"key": "kantor", "value": "Jl. Sudirman 1"}]})
    return core.reminders


def _raw_reminder(rem):
    rem.add_reminder("%mynickname%, meeting at %kantor% (100% sure)", "2026-09-24", "09:00")
    stored = rem.load_reminders()[0]
    stored["notes"] = "Ask %myname% about %unknown%"
    rem.save_reminders([stored])
    return rem.load_reminders()[0]


def test_expanded_copy(reminders):
    r = _raw_reminder(reminders)
    shown = reminders.expanded_copy(r)
    assert shown["title"] == "Bro, meeting at Jl. Sudirman 1 (100% sure)"
    assert shown["notes"] == "Ask Rafli about %unknown%"
    assert r["title"] == "%mynickname%, meeting at %kantor% (100% sure)"   # not changed
    assert shown["id"] == r["id"] and shown["time"] == "09:00"
    assert reminders.expanded_copy({"id": "x", "title": None})["title"] is None


def test_fired_reminder_is_announced_expanded_and_stored_raw(reminders, monkeypatch):
    import core.sounds
    import core.speech
    from core.events import bus
    r = _raw_reminder(reminders)
    spoken, shown, fired = [], [], []

    class FakeDialog:
        def __init__(self, parent, data):
            shown.append(dict(data))

        def Raise(self):
            pass

        def ShowModal(self):
            return 2   # "Mark as Done"

        def Destroy(self):
            pass

    def on_fired(reminder):
        fired.append(dict(reminder))

    monkeypatch.setattr(core.speech, "speak", lambda text, interrupt=False: spoken.append(text))
    monkeypatch.setattr(core.sounds, "play_sound", lambda path: True)
    monkeypatch.setattr(reminders, "ReminderDialog", FakeDialog)
    bus.subscribe("on_reminder_fired", on_fired)
    try:
        reminders.show_notification(r)
    finally:
        bus.unsubscribe("on_reminder_fired", on_fired)

    expected = "Bro, meeting at Jl. Sudirman 1 (100% sure)"
    assert spoken[0] == f"Reminder: {expected}"
    assert shown[0]["title"] == expected and shown[0]["notes"] == "Ask Rafli about %unknown%"
    assert spoken[1] == f"Reminder '{expected}' marked as done."
    # The event and the file keep what the user typed.
    assert fired[0]["title"] == "%mynickname%, meeting at %kantor% (100% sure)"
    stored = reminders.load_reminders()[0]
    assert stored["title"] == "%mynickname%, meeting at %kantor% (100% sure)"
    assert stored["notes"] == "Ask %myname% about %unknown%"
    assert stored["is_done"] is True
    with open(reminders.REMINDERS_FILE, encoding="utf-8") as f:
        assert "Bro" not in f.read()


def test_snooze_announces_expanded(reminders, monkeypatch):
    import core.speech
    r = _raw_reminder(reminders)
    spoken = []
    monkeypatch.setattr(core.speech, "speak", lambda text, interrupt=False: spoken.append(text))
    reminders.snooze_reminder(r["id"], 5)
    assert spoken == ["Reminder 'Bro, meeting at Jl. Sudirman 1 (100% sure)' snoozed for 5 minutes."]
    assert reminders.load_reminders()[0]["title"].startswith("%mynickname%")


def test_agenda_list_keeps_raw_text(reminders):
    # The agenda and the edit views show what the user typed.
    _raw_reminder(reminders)
    assert reminders.get_reminders_for_date("2026-09-24")[0]["title"].startswith("%mynickname%")


def test_windows_variable_names_are_rejected(personal, monkeypatch):
    monkeypatch.setenv("HARIKUTESTVAR", "x")
    with pytest.raises(personal.ProfileError) as e:
        personal.check_key("harikutestvar")
    assert e.value.code == "key_windows" and e.value.field == "key"


def test_routines_open_actions_fill_in_windows_variables(personal, monkeypatch):
    import sys
    routines_dir = os.path.join(ROOT, "extensions", "routines")
    monkeypatch.syspath_prepend(routines_dir)
    for name in ("routines_actions", "routines_engine"):
        sys.modules.pop(name, None)
    import routines_actions
    opened = []
    monkeypatch.setenv("HARIKUTESTDIR", r"C:\Data")
    monkeypatch.setattr(routines_actions.os, "startfile", opened.append, raising=False)
    routines_actions._a_open_file({"path": r"%HARIKUTESTDIR%\%myname%.txt"}, {}, {})
    _save_core({"user_name": "Rafli"})
    routines_actions._a_open_file({"path": r"%HARIKUTESTDIR%\%myname%.txt"}, {}, {})
    assert opened == [r"C:\Data\.txt", r"C:\Data\Rafli.txt"]


# ------------------------------------------------------------
# Birthday
# ------------------------------------------------------------

class TestBirthday:
    def test_check_birthday(self, personal):
        this_year = datetime.date.today().year
        assert personal.check_birthday(None, None) is None
        assert personal.check_birthday(0, 0, "") is None
        assert personal.check_birthday(24, 9) == (24, 9, None)
        assert personal.check_birthday("24", "9", " 1999 ") == (24, 9, 1999)
        assert personal.check_birthday(29, 2) == (29, 2, None)       # no year: fine
        assert personal.check_birthday(29, 2, 2000) == (29, 2, 2000)
        assert personal.check_birthday(1, 1, this_year) == (1, 1, this_year)

    @pytest.mark.parametrize("day, month, year, code, field", [
        (24, 0, None, "birthday_incomplete", "birthday_month"),
        (0, 9, None, "birthday_incomplete", "birthday_day"),
        (31, 4, None, "birthday_invalid", "birthday_day"),
        (32, 1, None, "birthday_invalid", "birthday_day"),
        (1, 13, None, "birthday_invalid", "birthday_day"),
        (29, 2, 1999, "birthday_invalid", "birthday_day"),
        (24, 9, "abc", "birthday_year", "birthday_year"),
        (24, 9, 1899, "birthday_year", "birthday_year"),
        (24, 9, 9999, "birthday_year", "birthday_year"),
    ])
    def test_bad_birthdays(self, personal, day, month, year, code, field):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_birthday(day, month, year)
        assert e.value.code == code and e.value.field == field

    def test_messages(self, personal, lang):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_birthday(24, None)
        assert str(e.value) == "Choose both the day and the month of your birthday, or neither."
        lang("id")
        with pytest.raises(personal.ProfileError) as e:
            personal.check_birthday(24, 9, "1800")
        assert str(e.value).startswith("Tahun kelahiran harus berupa angka dari 1900 sampai ")

    def test_set_get_and_clear(self, personal):
        _save_core({"user_name": "Rafli", "date_format": "%d/%m/%Y"})
        assert personal.get_birthday() is None
        assert personal.set_birthday(24, 9, 1999) is True
        assert personal.get_birthday() == (24, 9, 1999)
        assert _load_core()["user_birthday"] == {"day": 24, "month": 9, "year": 1999}
        assert _load_core()["date_format"] == "%d/%m/%Y"
        personal.set_birthday(24, 9)
        assert personal.get_birthday() == (24, 9, None)
        personal.set_birthday(None, None)
        assert personal.get_birthday() is None and "user_birthday" not in _load_core()

    def test_broken_stored_birthdays_are_ignored(self, personal):
        for raw in ("24-09", {"day": 31, "month": 2}, {"day": 24}, {"day": "x", "month": 9},
                    {"day": 24, "month": 9, "year": "soon"}):
            _save_core({"user_birthday": raw})
            assert personal.get_birthday() is None, raw

    def test_set_profile_keeps_or_changes_the_birthday(self, personal):
        personal.set_birthday(24, 9, 1999)
        personal.set_profile("Rafli", "Bro", [])                  # not given: kept
        assert personal.get_birthday() == (24, 9, 1999)
        personal.set_profile("Rafli", "Bro", [], birthday=(1, 1, None))
        assert personal.get_birthday() == (1, 1, None)
        personal.set_profile("Rafli", "Bro", [], birthday=None)   # removed
        assert personal.get_birthday() is None
        with pytest.raises(personal.ProfileError):
            personal.set_profile("Other", "", [], birthday=(31, 4, None))
        assert personal.get_name() == "Rafli"                     # nothing saved

    def test_text(self, personal, lang):
        assert personal.birthday_text((24, 9, None)) == "24 September"
        assert personal.birthday_text((5, 8, 1999)) == "5 August 1999"
        assert personal.birthday_text(None) == ""
        lang("id")
        assert personal.birthday_text((5, 8, 1999)) == "5 Agustus 1999"

    def test_age(self, personal):
        bday = (24, 9, 1999)
        assert personal.get_age(datetime.date(2026, 9, 23), bday) == 26
        assert personal.get_age(datetime.date(2026, 9, 24), bday) == 27
        assert personal.get_age(datetime.datetime(2026, 12, 31, 23, 0), bday) == 27
        assert personal.get_age(datetime.date(2026, 9, 24), (24, 9, None)) is None
        assert personal.get_age(datetime.date(2026, 9, 24), None) is None
        leap = (29, 2, 2000)
        assert personal.get_age(datetime.date(2025, 2, 27), leap) == 24
        assert personal.get_age(datetime.date(2025, 2, 28), leap) == 25

    def test_is_birthday(self, personal):
        assert personal.is_birthday(datetime.date(2026, 9, 24), (24, 9, 1999))
        assert personal.is_birthday(datetime.datetime(2030, 9, 24, 7, 0), (24, 9, None))
        assert not personal.is_birthday(datetime.date(2026, 9, 25), (24, 9, 1999))
        assert not personal.is_birthday(datetime.date(2026, 9, 24), None)
        # 29 February is celebrated on the 28th in other years.
        assert personal.is_birthday(datetime.date(2025, 2, 28), (29, 2, None))
        assert not personal.is_birthday(datetime.date(2024, 2, 28), (29, 2, None))
        assert personal.is_birthday(datetime.date(2024, 2, 29), (29, 2, None))

    def test_is_birthday_reads_the_profile(self, personal):
        today = datetime.date.today()
        personal.set_birthday(today.day, today.month)
        assert personal.is_birthday()
        personal.set_birthday(None, None)
        assert not personal.is_birthday()

    def test_tokens(self, personal, lang):
        today = datetime.date.today()
        _save_core({"user_birthday": {"day": 24, "month": 9, "year": 1999}})
        age = personal.get_age()
        assert age == today.year - 1999 - (today < datetime.date(today.year, 9, 24))
        assert personal.expand("%mybirthday% (%MyAge%)") == f"24 September 1999 ({age})"
        _save_core({"user_birthday": {"day": 24, "month": 9, "year": None}})
        assert personal.expand("[%mybirthday%][%myage%]") == "[24 September][]"
        _save_core({})
        assert personal.expand("[%mybirthday%][%myage%]") == "[][]"

    def test_profile_includes_the_birthday(self, personal):
        personal.set_birthday(24, 9)
        assert personal.get_profile()["birthday"] == (24, 9, None)


# ------------------------------------------------------------
# Greeting
# ------------------------------------------------------------

MORNING = datetime.datetime(2026, 9, 23, 7, 30)


class TestGreeting:
    @pytest.mark.parametrize("hour, key", [
        (0, "greet_evening"), (4, "greet_morning"), (10, "greet_morning"), (11, "greet_midday"),
        (15, "greet_afternoon"), (17, "greet_afternoon"), (18, "greet_evening"),
    ])
    def test_key(self, personal, hour, key):
        assert personal.greeting_key(hour) == key

    def test_with_nickname_name_or_nothing(self, personal, lang):
        _save_core({"user_name": "Rafli", "user_nickname": "Bro"})
        assert personal.greeting(MORNING) == "Good morning, Bro."
        _save_core({"user_name": "Rafli"})
        assert personal.greeting(MORNING.replace(hour=12)) == "Good day, Rafli."
        _save_core({"user_name": "User"})
        assert personal.greeting(MORNING.replace(hour=16)) == "Good afternoon."
        assert personal.greeting(MORNING.replace(hour=21), nickname="Bro!") == "Good evening, Bro!"
        lang("id")
        _save_core({"user_nickname": "Bro"})
        assert personal.greeting(MORNING) == "Selamat pagi, Bro."
        assert personal.greeting(MORNING.replace(hour=20)) == "Selamat malam, Bro."

    def test_birthday_line(self, personal, lang):
        _save_core({"user_nickname": "Bro", "user_birthday": {"day": 23, "month": 9}})
        assert personal.greeting(MORNING) == "Good morning, Bro. Happy birthday!"
        assert personal.greeting(MORNING + datetime.timedelta(days=1)) == "Good morning, Bro."
        lang("id")
        assert personal.greeting(MORNING) == "Selamat pagi, Bro. Selamat ulang tahun!"
        _save_core({"user_birthday": {"day": 23, "month": 9}})
        assert personal.greeting(MORNING) == "Selamat pagi. Selamat ulang tahun!"

    def test_startup_greeting_setting(self, personal):
        assert personal.startup_greeting_enabled() is True         # on by default
        personal.set_startup_greeting(False)
        assert personal.startup_greeting_enabled() is False
        assert personal.get_profile()["greet_on_startup"] is False
        personal.set_startup_greeting(True)
        assert _load_core()["greet_on_startup"] is True

    def test_startup_speech_is_one_announcement(self, personal, lang):
        _save_core({"user_nickname": "Bro"})
        assert personal.startup_speech("Welcome to Hariku version 2.7.0", MORNING) == (
            "Good morning, Bro. Welcome to Hariku version 2.7.0.")
        assert personal.startup_speech("", MORNING) == "Good morning, Bro."
        _save_core({"user_nickname": "Bro", "user_birthday": {"day": 23, "month": 9}})
        assert personal.startup_speech("Welcome.", MORNING) == (
            "Good morning, Bro. Happy birthday! Welcome.")

    def test_speak_startup_greeting(self, personal, lang, monkeypatch):
        import core.speech
        spoken = []
        monkeypatch.setattr(core.speech, "speak",
                            lambda text, interrupt=False: spoken.append((text, interrupt)))
        _save_core({"user_nickname": "Bro"})
        personal.speak_startup_greeting("Welcome to Hariku version 2.7.0")
        [(text, interrupt)] = spoken
        assert text.startswith("Good ") and ", Bro. " in text
        assert text.endswith("Welcome to Hariku version 2.7.0.") and interrupt is False


def test_hariku_merges_the_welcome_into_the_greeting():
    # The startup speech is one announcement after the window is ready, on a
    # timer so startup never waits for it.
    with open(os.path.join(ROOT, "hariku.py"), encoding="utf-8") as f:
        source = f.read()
    assert "if core.personal.startup_greeting_enabled():" in source
    assert ("core.personal.schedule_startup_greeting(\n"
            "                welcome, boot=core.api.started_with_windows())") in source
    assert source.index("self.frame.Show(True)") < source.index("schedule_startup_greeting")


# ------------------------------------------------------------
# Quiet hours
# ------------------------------------------------------------

def _at(hour, minute=0):
    return datetime.datetime(2026, 9, 23, hour, minute)


class TestQuietHours:
    def test_off_by_default(self, personal):
        assert personal.get_quiet_hours() == {"enabled": False, "start": "22:00", "end": "05:00"}
        assert not any(personal.is_quiet_time(_at(h)) for h in range(24))

    @pytest.mark.parametrize("hour, minute, quiet", [
        (21, 59, False), (22, 0, True), (23, 59, True), (0, 0, True), (3, 0, True),
        (4, 59, True), (5, 0, False), (12, 0, False),
    ])
    def test_range_past_midnight(self, personal, hour, minute, quiet):
        personal.set_quiet_hours(True, "22:00", "05:00")
        assert personal.is_quiet_time(_at(hour, minute)) is quiet

    @pytest.mark.parametrize("hour, minute, quiet", [
        (12, 59, False), (13, 0, True), (14, 30, True), (15, 0, False), (23, 0, False),
    ])
    def test_range_within_a_day(self, personal, hour, minute, quiet):
        personal.set_quiet_hours(True, "13:00", "15:00")
        assert personal.is_quiet_time(_at(hour, minute)) is quiet

    def test_uses_the_clock_by_default(self, personal, monkeypatch):
        personal.set_quiet_hours(True, "00:00", "23:59")
        now = datetime.datetime.now()
        assert personal.is_quiet_time() is (now.hour * 60 + now.minute < 23 * 60 + 59)

    def test_turned_off_keeps_the_times(self, personal):
        personal.set_quiet_hours(False, "21:30", "06:00")
        assert personal.get_quiet_hours() == {"enabled": False, "start": "21:30", "end": "06:00"}
        assert not personal.is_quiet_time(_at(23))

    def test_times_are_normalized(self, personal):
        personal.set_quiet_hours(True, " 9:05 ", "17:00")
        assert personal.get_quiet_hours()["start"] == "09:05"
        assert personal.is_quiet_time(_at(9, 5))

    @pytest.mark.parametrize("start, end, code, field", [
        ("25:00", "05:00", "quiet_time", "quiet_start"),
        ("22:00", "5pm", "quiet_time", "quiet_end"),
        ("", "05:00", "quiet_time", "quiet_start"),
        ("22:00", "22:00", "quiet_same", "quiet_end"),
    ])
    def test_invalid(self, personal, start, end, code, field):
        with pytest.raises(personal.ProfileError) as e:
            personal.set_quiet_hours(True, start, end)
        assert e.value.code == code and e.value.field == field
        assert "quiet_hours" not in _load_core()

    def test_same_times_are_fine_while_off(self, personal):
        personal.set_quiet_hours(False, "22:00", "22:00")
        assert personal.get_quiet_hours()["enabled"] is False

    def test_broken_stored_values(self, personal):
        _save_core({"quiet_hours": {"enabled": True, "start": "late", "end": 5}})
        assert personal.get_quiet_hours() == {"enabled": True, "start": "22:00", "end": "05:00"}
        assert personal.is_quiet_time(_at(23))
        _save_core({"quiet_hours": "yes"})
        assert personal.get_quiet_hours()["enabled"] is False
        # Equal times saved by hand mean never quiet.
        _save_core({"quiet_hours": {"enabled": True, "start": "08:00", "end": "08:00"}})
        assert not personal.is_quiet_time(_at(8))


def test_quiet_hours_messages(personal, lang):
    with pytest.raises(personal.ProfileError) as e:
        personal.set_quiet_hours(True, "22:00", "22:00")
    assert str(e.value) == "Quiet hours can't start and end at the same time."
    lang("id")
    with pytest.raises(personal.ProfileError) as e:
        personal.set_quiet_hours(True, "x", "05:00")
    assert str(e.value) == "Pilih waktu dalam jam dan menit, misalnya 22:00."


def test_preferences_pages_follow_general(monkeypatch):
    import core.core_panels
    import core.preferences
    pages = []
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda category, name, create, apply=None: pages.append(
                            (category, create, apply)))
    core.core_panels.register()
    assert [p[0] for p in pages][:3] == ["General", core.core_panels._("prefs_tab_profile"),
                                          core.core_panels._("prefs_tab_quiet")]
    assert pages[1][1] is core.core_panels.create_profile_panel
    assert pages[2][1:] == (core.core_panels.create_quiet_panel,
                            core.core_panels.apply_quiet_settings)
    assert core.core_panels.QUIET_TIMES[:3] == ["00:00", "00:30", "01:00"]
    assert len(core.core_panels.QUIET_TIMES) == 48 and "22:00" in core.core_panels.QUIET_TIMES


def test_preferences_refuse_invalid_pages_before_saving():
    # OK and Apply first ask each page's ValidateChanges(); a problem keeps the
    # dialog open on that page and saves nothing.
    with open(os.path.join(ROOT, "ui", "preferences_dialog.py"), encoding="utf-8") as f:
        source = f.read()
    apply_body = source[source.index("def OnApply"):source.index("def OnOK")]
    assert apply_body.index("self._validate()") < apply_body.index('p["apply"]()')
    ok_body = source[source.index("def OnOK"):source.index("def OnCancel")]
    assert "if self.OnApply(None) is False:" in ok_body


# ------------------------------------------------------------
# Title and %mytitle% (core 2.7)
# ------------------------------------------------------------

class TestTitle:
    def test_nothing_saved(self, personal):
        assert personal.get_title() == ""
        assert personal.get_addressed_name() == ""
        assert personal.get_profile()["title"] == ""

    def test_title_before_the_nickname(self, personal):
        _save_core({"user_name": "Rafli", "user_nickname": "Bro", "user_title": "  Kapten "})
        assert personal.get_title() == "Kapten"
        assert personal.get_addressed_name() == "Kapten Bro"
        _save_core({"user_name": "Rafli", "user_title": "Pak"})
        assert personal.get_addressed_name() == "Pak Rafli"
        _save_core({"user_title": "Kak"})
        assert personal.get_addressed_name() == "Kak"
        _save_core({"user_title": 42, "user_nickname": "Bro"})
        assert personal.get_title() == "" and personal.get_addressed_name() == "Bro"

    def test_greeting_with_a_title(self, personal, lang):
        _save_core({"user_name": "Rafli", "user_nickname": "Bro", "user_title": "Kapten"})
        lang("id")
        assert personal.greeting(MORNING) == "Selamat pagi, Kapten Bro."
        lang("en")
        assert personal.greeting(MORNING) == "Good morning, Kapten Bro."
        assert personal.greeting(MORNING, nickname="Budi", title="") == "Good morning, Budi."
        _save_core({"user_title": "Captain"})
        assert personal.greeting(MORNING.replace(hour=20)) == "Good evening, Captain."
        _save_core({"user_title": "Captain", "user_birthday": {"day": 23, "month": 9}})
        assert personal.greeting(MORNING) == "Good morning, Captain. Happy birthday!"

    def test_mytitle_placeholder(self, personal):
        _save_core({"user_nickname": "Bro", "user_title": "Kapten"})
        assert personal.expand("%mytitle% %mynickname%, %MyTitle%!") == "Kapten Bro, Kapten!"
        _save_core({"user_nickname": "Bro"})
        assert personal.expand("[%mytitle%]") == "[]"

    def test_mytitle_is_reserved(self, personal):
        with pytest.raises(personal.ProfileError) as e:
            personal.check_key("mytitle")
        assert e.value.code == "key_reserved"

    def test_set_title_and_set_profile(self, personal):
        _save_core({"user_name": "Rafli", "user_title": "Pak"})
        personal.set_profile("Rafli", "Bro", [])
        assert personal.get_title() == "Pak"                   # kept when not given
        personal.set_profile("Rafli", "Bro", [], title="  Kapten   Udara ")
        assert _load_core()["user_title"] == "Kapten Udara"
        assert personal.set_title("") is True and personal.get_title() == ""
        personal.set_title("Captain")
        assert personal.get_title() == "Captain"
        with pytest.raises(personal.ProfileError) as e:
            personal.set_title("x" * 501)
        assert e.value.code == "title_too_long" and personal.get_title() == "Captain"


# ------------------------------------------------------------
# Dynamic placeholders: Hariku's own and registered ones (core 2.7)
# ------------------------------------------------------------

WIB = datetime.timezone(datetime.timedelta(hours=7))
NOW_WIB = datetime.datetime(2026, 9, 24, 10, 30, tzinfo=WIB)     # a Thursday, 03:30 UTC


@pytest.fixture
def registry(personal, monkeypatch):
    """No registered placeholders besides the test's own, and no real reminders read."""
    saved = dict(personal._providers)
    personal._providers.clear()
    counts = {"today": 3}
    monkeypatch.setattr(personal, "reminders_today_count", lambda day=None: counts["today"])
    personal.counts = counts
    yield personal
    personal._providers.clear()
    personal._providers.update(saved)


class TestDynamicPlaceholders:
    def test_values_in_english(self, registry, lang):
        p = registry
        assert p.expand("%greeting%|%time%|%day%|%date%|%zulu%|%reminders%", now=NOW_WIB) == (
            "Good morning|10:30|Thursday|24 September|03:30|3 reminders today")
        p.counts["today"] = 1
        assert p.expand("%reminders%", now=NOW_WIB) == "1 reminder today"
        p.counts["today"] = 0
        assert p.expand("You have %REMINDERS%.", now=NOW_WIB) == "You have no reminders today."
        assert p.expand("%greeting%", now=NOW_WIB.replace(hour=16)) == "Good afternoon"

    def test_values_in_indonesian(self, registry, lang):
        lang("id")
        assert registry.expand("%greeting%, %day% %date%, %reminders%", now=NOW_WIB) == (
            "Selamat pagi, Kamis 24 September, 3 pengingat hari ini")
        registry.counts["today"] = 0
        assert registry.expand("%reminders%", now=NOW_WIB) == "tidak ada pengingat hari ini"

    def test_zulu_from_a_local_clock(self, registry):
        naive = datetime.datetime(2026, 9, 24, 10, 30)
        expected = datetime.datetime.fromtimestamp(naive.timestamp(), datetime.timezone.utc)
        assert registry.dynamic_value("zulu", naive) == expected.strftime("%H:%M")

    def test_register_and_unregister(self, registry):
        p = registry
        assert p.register_placeholder("Weather", lambda: "light rain, 25 degrees",
                                      "the weather now") == "weather"
        assert p.is_placeholder_registered("WEATHER")
        assert p.expand("It is %weather%.") == "It is light rain, 25 degrees."
        assert ("weather", "the weather now", "light rain, 25 degrees") in p.get_placeholders()
        assert p.unregister_placeholder("weather") is True
        assert p.unregister_placeholder("weather") is False
        assert p.expand("It is %weather%.") == "It is %weather%."

    def test_failing_or_empty_providers_give_nothing(self, registry):
        p = registry

        def boom():
            raise RuntimeError("no cache")

        p.register_placeholder("boom", boom)
        p.register_placeholder("none", lambda: None)
        p.register_placeholder("number", lambda: 42)
        p.register_placeholder("messy", lambda: "  two\nlines\t" + "x" * 400)
        assert p.expand("[%boom%][%none%][%number%]") == "[][][42]"
        messy = p.expand("%messy%")
        assert messy.startswith("two lines x") and len(messy) == p.MAX_PLACEHOLDER_VALUE

    def test_order_extra_dynamic_registered_profile(self, registry):
        p = registry
        _save_core({"user_fields": [{"key": "weather", "value": "my own"}]})
        assert p.expand("%weather%") == "my own"
        p.register_placeholder("weather", lambda: "registered")
        assert p.expand("%weather%") == "registered"             # before the profile
        assert p.expand("%weather%", {"weather": "extra"}) == "extra"
        assert p.expand("%time%", {"time": "08:00"}, now=NOW_WIB) == "08:00"   # Routines' own
        assert p.expand("%time%", now=NOW_WIB) == "10:30"

    @pytest.mark.parametrize("name", ["time", "myname", "mytitle", "reminders", "var",
                                      "bad name", "", "x" * 33])
    def test_names_hariku_uses_are_refused(self, registry, name):
        with pytest.raises(ValueError):
            registry.register_placeholder(name, lambda: "x")

    def test_registered_names_are_reserved_for_new_keys(self, registry):
        p = registry
        p.register_placeholder("airportweather", lambda: "")
        with pytest.raises(p.ProfileError) as e:
            p.check_key("airportweather")
        assert e.value.code == "key_reserved"
        # A key the user saved before the extension registered it still saves.
        p.set_profile("Rafli", "", [("airportweather", "mine"), ("kantor", "K")])
        assert p.get_fields() == [("airportweather", "mine"), ("kantor", "K")]

    def test_unknown_tokens_can_be_dropped(self, registry):
        assert registry.expand("A %gone% B 100%") == "A %gone% B 100%"
        assert registry.expand("A %gone% B 100%", unknown="") == "A  B 100%"


def test_reminders_today_count_skips_done_ones(reminders, monkeypatch):
    import core.personal
    today = datetime.date.today().isoformat()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    reminders.save_reminders([
        {"id": "a", "title": "A", "date": today, "time": "09:00", "is_done": False},
        {"id": "b", "title": "B", "date": today, "time": "10:00", "is_done": True},
        {"id": "c", "title": "C", "date": today, "time": "11:00", "is_done": False},
        {"id": "d", "title": "D", "date": tomorrow, "time": "09:00", "is_done": False},
    ])
    assert core.personal.reminders_today_count() == 2


@pytest.mark.parametrize("raw, tidy", [
    ("Welcome aboard,  Bro.", "Welcome aboard, Bro."),
    ("Welcome aboard, .", "Welcome aboard."),
    ("It is 10:30, 03:30 Zulu. . You have 3 reminders today.",
     "It is 10:30, 03:30 Zulu. You have 3 reminders today."),
    ("Zulu. .. Next", "Zulu. Next"),
    ("Hi , there", "Hi, there"),
    ("A,, b", "A, b"),
    (". Hello", "Hello"),
    ("Visibility 7.5 kilometres at 10:30.", "Visibility 7.5 kilometres at 10:30."),
    ("Wow! . Next?", "Wow! Next?"),
])
def test_tidy_spoken(personal, raw, tidy):
    assert personal.tidy_spoken(raw) == tidy


# ------------------------------------------------------------
# The user's own startup greeting (core 2.7)
# ------------------------------------------------------------

COCKPIT_EN = ("Welcome aboard, %mytitle% %mynickname%. Welcome to your cockpit. It's %time% "
              "local, %zulu% Zulu. %airportweather%. You have %reminders%. "
              "What are we doing today?")


class TestCustomGreeting:
    def test_saved_and_read(self, personal):
        assert personal.get_custom_greeting() == {"text": "", "boot_only": False}
        personal.set_custom_greeting("  Hello %mynickname%  ", boot_only=True)
        assert personal.get_custom_greeting() == {"text": "Hello %mynickname%", "boot_only": True}
        assert _load_core()["custom_greeting"] == "Hello %mynickname%"   # raw
        with pytest.raises(personal.ProfileError) as e:
            personal.set_custom_greeting("x" * 501)
        assert e.value.code == "greeting_too_long"

    def test_replaces_the_greeting_and_welcome(self, registry, lang):
        p = registry
        _save_core({"user_nickname": "Bro", "user_title": "Kapten", "custom_greeting": COCKPIT_EN})
        p.register_placeholder("airportweather",
                               lambda: "Hang Nadim: wind from 200 degrees at 6 knots")
        assert p.startup_speech("Welcome to Hariku version 2.7.0", NOW_WIB) == (
            "Welcome aboard, Kapten Bro. Welcome to your cockpit. It's 10:30 local, 03:30 Zulu. "
            "Hang Nadim: wind from 200 degrees at 6 knots. You have 3 reminders today. "
            "What are we doing today?")

    def test_empty_placeholders_leave_no_gaps(self, registry, lang):
        p = registry
        _save_core({"custom_greeting": COCKPIT_EN})
        p.register_placeholder("airportweather", lambda: "")
        assert p.startup_speech("", NOW_WIB) == (
            "Welcome aboard. Welcome to your cockpit. It's 10:30 local, 03:30 Zulu. "
            "You have 3 reminders today. What are we doing today?")
        p.unregister_placeholder("airportweather")   # Cockpit removed: nothing is said
        assert "%" not in p.startup_speech("", NOW_WIB)

    def test_only_when_windows_started_hariku(self, registry, lang):
        _save_core({"user_nickname": "Bro", "custom_greeting": "Morning, %mynickname%!",
                    "custom_greeting_boot_only": True})
        assert registry.startup_speech("Welcome.", MORNING, boot=True) == "Morning, Bro!"
        assert registry.startup_speech("Welcome.", MORNING) == "Good morning, Bro. Welcome."

    def test_nothing_left_means_the_usual_greeting(self, registry, lang):
        _save_core({"user_nickname": "Bro", "custom_greeting": "%gone%."})
        assert registry.startup_speech("Welcome.", MORNING) == "Good morning, Bro. Welcome."

    def test_birthday(self, registry, lang):
        _save_core({"custom_greeting": "Hello %mynickname%", "user_nickname": "Bro",
                    "user_birthday": {"day": 23, "month": 9}})
        assert registry.startup_speech("", MORNING) == "Hello Bro. Happy birthday!"

    def test_spoken_as_the_greeting(self, registry, lang, monkeypatch):
        import core.voice
        said = []
        monkeypatch.setattr(core.voice, "announce",
                            lambda text, kind, interrupt=True: said.append((text, kind, interrupt)))
        _save_core({"custom_greeting": "Hi %mynickname%", "user_nickname": "Bro",
                    "custom_greeting_boot_only": True})
        registry.speak_startup_greeting("Welcome.", boot=True)
        registry.speak_startup_greeting("Welcome.")
        assert said[0] == ("Hi Bro", "greeting", False)
        assert said[1][0].endswith(", Bro. Welcome.") and said[1][1] == "greeting"


# ------------------------------------------------------------
# When Windows started Hariku: the greeting waits for the network (core 2.7)
# ------------------------------------------------------------

@pytest.mark.parametrize("elapsed, online_at, wait", [
    (1.5, None, 1.0),       # offline: look again in a second
    (1.5, 1.5, 3.0),        # online at the first look: 3 seconds to settle
    (4.0, 1.5, 0.5),
    (4.5, 1.5, 0.0),        # greet now
    (24.5, None, 0.5),      # never past the cap
    (25.0, None, 0.0),
    (23.0, 22.5, 2.0),      # settling is cut short by the cap
    (30.0, 29.0, 0.0),
])
def test_boot_greeting_wait(personal, elapsed, online_at, wait):
    assert personal.boot_greeting_wait(elapsed, online_at) == pytest.approx(wait)


class _Timers:
    """A fake clock and wx.CallLater."""

    def __init__(self):
        self.now = 0.0
        self.pending = []

    def call_later(self, ms, fn, *args):
        self.pending.append((self.now + ms / 1000.0, fn, args))

    def run(self, limit=100):
        while self.pending and limit:
            self.pending.sort(key=lambda item: item[0])
            when, fn, args = self.pending.pop(0)
            self.now = when
            fn(*args)
            limit -= 1


@pytest.fixture
def greeted(personal, monkeypatch):
    said = []
    timers = _Timers()
    monkeypatch.setattr(personal, "speak_startup_greeting",
                        lambda welcome="", boot=False: said.append((timers.now, welcome, boot)))
    return said, timers


def test_a_manual_start_greets_after_the_window(personal, greeted):
    said, timers = greeted
    personal.schedule_startup_greeting("Welcome.", boot=False, call_later=timers.call_later,
                                       is_online=lambda: False, clock=lambda: timers.now)
    timers.run()
    assert said == [(1.5, "Welcome.", False)]


@pytest.mark.parametrize("online_from, greeted_at", [
    (0.0, 4.5),       # the network is already up: 1.5 + 3
    (6.0, 9.5),       # seen up at the 6.5 s look, then 3 more seconds
    (None, 25.0),     # never: the cap
])
def test_a_start_with_windows_waits_for_the_network(personal, greeted, online_from, greeted_at):
    said, timers = greeted
    personal.schedule_startup_greeting(
        "Welcome.", boot=True, call_later=timers.call_later, clock=lambda: timers.now,
        is_online=lambda: online_from is not None and timers.now >= online_from)
    timers.run()
    assert said == [(pytest.approx(greeted_at), "Welcome.", True)]


def test_a_failing_network_check_does_not_hold_the_greeting(personal, greeted):
    said, timers = greeted

    def broken():
        raise OSError("wininet")

    personal.schedule_startup_greeting("", boot=True, call_later=timers.call_later,
                                       is_online=broken, clock=lambda: timers.now)
    timers.run()
    assert said == [(pytest.approx(4.5), "", True)]


# ------------------------------------------------------------
# Knowing Windows started Hariku (core.api, 2.7)
# ------------------------------------------------------------

def test_autostart_command_has_the_flag():
    import core.api
    exe = r"C:\Program Files\Hariku\Hariku.exe"
    assert core.api.autostart_command(True, exe) == f'"{exe}" --autostart'
    assert core.api.autostart_command(False, r"C:\Py\python.exe", r"D:\hariku2\hariku.py") == \
        r'"C:\Py\python.exe" "D:\hariku2\hariku.py" --autostart'


def test_started_with_windows():
    import core.api
    assert core.api.started_with_windows(["--autostart"]) is True
    assert core.api.started_with_windows(["--safe-mode", "--autostart"]) is True
    assert core.api.started_with_windows([]) is False
    assert core.api.started_with_windows(["--safe-mode"]) is False


def test_a_restart_is_not_a_start_with_windows():
    with open(os.path.join(ROOT, "core", "api.py"), encoding="utf-8") as f:
        source = f.read()
    allowed = source[source.index("_ALLOWED_RESTART_ARGS"):]
    allowed = allowed[:allowed.index("\n")]
    assert "--autostart" not in allowed


@pytest.mark.parametrize("config, value, needed", [
    ({"auto_start": True}, r'"C:\Hariku\Hariku.exe"', True),
    ({"auto_start": True}, r'C:\Hariku\Hariku.exe', True),
    ({"auto_start": True}, r'"C:\Hariku\Hariku.exe" --autostart', False),
    ({"auto_start": True}, None, False),        # removed by the user: stays removed
    ({"auto_start": False}, r'"C:\Hariku\Hariku.exe"', False),
    ({}, r'"C:\Hariku\Hariku.exe"', False),
])
def test_autostart_needs_update(config, value, needed):
    import core.api
    assert core.api.autostart_needs_update(config, value) is needed


def test_migrate_autostart():
    import core.api
    writes = []
    assert core.api.migrate_autostart({"auto_start": True}, read_value=lambda: r'"C:\H.exe"',
                                      write=writes.append) is True
    assert writes == [True]

    def must_not_read():
        raise AssertionError("the registry is only read when autostart is on")

    assert core.api.migrate_autostart({"auto_start": False}, read_value=must_not_read,
                                      write=writes.append) is False
    assert core.api.migrate_autostart({"auto_start": True},
                                      read_value=lambda: r'"C:\H.exe" --autostart',
                                      write=writes.append) is False

    def broken():
        raise OSError("no registry")

    assert core.api.migrate_autostart({"auto_start": True}, read_value=broken,
                                      write=writes.append) is False
    assert writes == [True]


def test_hariku_migrates_and_loads_the_theme_before_the_start_sound():
    with open(os.path.join(ROOT, "hariku.py"), encoding="utf-8") as f:
        source = f.read()
    assert "core.api.migrate_autostart(config)" in source
    first_sound = source.index('core.sounds.play_internal_sound("start.wav")')
    assert source.index("core.sounds.load_remembered_theme()") < first_sound
    assert source.index("core.sounds.load_remembered_theme()") > source.index(
        "self.is_safe_mode = ")


# ------------------------------------------------------------
# The shared Insert placeholder menu
# ------------------------------------------------------------

def test_menu_entries(registry, lang):
    p = registry
    p.register_placeholder("sleep", lambda: "about 6 hours 25 minutes", "how long you slept")
    entries = p.menu_entries(name="Rafli", nickname="Bro", title="Kapten",
                             fields=[("kantor", "Jl. Sudirman 1")])
    tokens = [t for t, _label in entries]
    labels = dict(entries)
    assert tokens[:6] == ["%myname%", "%mynickname%", "%mytitle%", "%mybirthday%", "%myage%",
                          "%kantor%"]
    assert labels["%mytitle%"] == "%mytitle%: your title (Kapten)"
    assert labels["%mybirthday%"] == "%mybirthday%: your birthday (not set)"
    assert labels["%kantor%"] == "%kantor%: your placeholder (Jl. Sudirman 1)"
    assert labels["%reminders%"].startswith("%reminders%: how many reminders")
    assert labels["%sleep%"] == "%sleep%: how long you slept (about 6 hours 25 minutes)"
    assert tokens[-1] == "%sleep%"
    lang("id")
    labels = dict(p.menu_entries(dynamic=[]))
    assert labels["%mytitle%"] == "%mytitle%: sapaan Anda (belum diisi)"


@pytest.mark.parametrize("value, start, end, expected, caret", [
    ("", 0, 0, "%time%", 6),
    ("Hi ", 3, 3, "Hi %time%", 9),
    ("Hi there", 0, 8, "Hi there%time%", 14),      # everything selected: added at the end
    ("Hi XX!", 3, 5, "Hi %time%!", 9),
])
def test_insert_placeholder(personal, value, start, end, expected, caret):
    assert personal.insert_placeholder(value, start, end, "%time%") == (expected, caret)


def test_version_placeholder(personal):
    import core.constants
    assert personal.dynamic_value("version") == core.constants.CORE_VERSION
    assert personal.expand("Welcome to Hariku %version%.") == \
        f"Welcome to Hariku {core.constants.CORE_VERSION}."
    with pytest.raises(personal.ProfileError) as e:
        personal.check_key("version")        # Hariku's own placeholder now
    assert e.value.code == "key_reserved"
