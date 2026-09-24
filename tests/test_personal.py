# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for core.personal (the Profile: name, nickname, own placeholders and
# %token% expansion) and for reminders being announced with it filled in.
# Every test runs on a temporary data folder, never the user's real Core.json.

import ast
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
        assert personal.get_profile() == {"name": "Rafli", "nickname": "",
                                          "fields": [("kantor", "Jl. A")]}


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
        ["myname", "mynickname", "time", "date", "battery", "app", "clipboard",
         "ssid", "ram", "cpu", "events", "var", "MyName", "%TIME%"]))
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
    used = _literal_keys(panels, ("profile_", "prefs_tab_profile", "prefs_btn_", "error"))
    with open(personal_py, encoding="utf-8") as f:
        source = f.read()
    codes = set(re.findall(r'ProfileError\("(\w+)"', source))
    codes |= {f"{field}_too_long" for field in ("name", "nickname", "value")}
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
