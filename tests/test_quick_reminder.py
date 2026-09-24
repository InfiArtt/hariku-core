# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the quick reminder in the core (core/quick_reminder.py): the
# read-back in both UI languages, what the reminder dialog's Fill in and the
# quick reminder's Edit put in the fields, the languages switched on in
# Preferences, saving through the core reminders API, the N key and the
# keybinding saved by the Hariku Assistant extension it came from. No windows
# (see test_quick_reminder_ui.py for those); the sentence reader itself is
# tested in test_when.py.

import ast
import datetime
import json
import os
import zipfile

import pytest

import core.quick_reminder as quick
from core import when

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_ROOT = os.path.join(ROOT, "extensions")

THU = datetime.datetime(2026, 9, 24, 10, 40)      # Thursday 24 September 2026, 10:40


def parse(text, now=THU, language="id", use=None):
    return when.parse(text, now, language=language, packs=use)


@pytest.fixture
def lang(monkeypatch):
    from core import i18n
    if not i18n._language_cache.get("core"):
        i18n._load_domain("core", i18n.CORE_LOCALES_DIR)

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("en")
    return set_lang


# --- the read-back, in both UI languages --------------------------------------------------

BENCHMARK = "ingatkan aku minum obat besok jam 8 pagi, ulangi tiap hari"


def test_readback_indonesian(lang):
    lang("id")
    assert quick.readback(parse(BENCHMARK)) == \
        "Minum obat, Jumat 25 September 2026, jam 08:00, setiap hari. Simpan?"


def test_readback_english(lang):
    assert quick.readback(parse(BENCHMARK)) == \
        "Minum obat, Friday 25 September 2026, at 08:00, every day. Save?"


@pytest.mark.parametrize("text, language, expected", [
    ("rapat besok", "id",
     "Rapat, Jumat 25 September 2026, jam 09:00. Anda tidak menyebut jam, jadi saya pakai "
     "jam 09:00. Simpan?"),
    ("rapat besok", "en",
     "Rapat, Friday 25 September 2026, at 09:00. You didn't say a time, so I used 09:00. Save?"),
    ("olahraga tiap Senin jam 6 pagi", "id",
     "Olahraga, Senin 28 September 2026, jam 06:00, setiap Senin. Simpan?"),
    ("gym every Monday at 6 pm", "en",
     "Gym, Monday 28 September 2026, at 18:00, every Monday. Save?"),
    ("minum vitamin tiap 2 hari jam 7 pagi", "id",
     "Minum vitamin, Jumat 25 September 2026, jam 07:00, setiap 2 hari. Simpan?"),
    ("water plants every 2 days at 7 am", "en",
     "Water plants, Friday 25 September 2026, at 07:00, every 2 days. Save?"),
    ("ganti sprei tiap 2 minggu hari Sabtu jam 8 pagi", "id",
     "Ganti sprei, Sabtu 26 September 2026, jam 08:00, setiap 2 minggu, hari Sabtu. Simpan?"),
    ("bayar listrik tiap bulan tanggal 5 jam 9", "id",
     "Bayar listrik, Senin 5 Oktober 2026, jam 09:00, setiap bulan tanggal 5. Simpan?"),
    ("pay rent monthly on the 1st at 9 am", "en",
     "Pay rent, Thursday 1 October 2026, at 09:00, every month on day 1. Save?"),
    ("ulang tahun ibu tiap tahun 17 Agustus jam 7 pagi", "id",
     "Ulang tahun ibu, Selasa 17 Agustus 2027, jam 07:00, setiap tahun tanggal 17 Agustus. "
     "Simpan?"),
    ("rapat hari ini jam 9 pagi", "id",
     "Rapat, Kamis 24 September 2026, jam 09:00. Waktu itu sudah lewat. Simpan?"),
    ("rapat jam 8 pagi, eh jam 9 pagi", "en",
     "Rapat, Friday 25 September 2026, at 08:00. You gave more than one date or time; "
     "I used the first one. Save?"),
])
def test_readback_sentences(lang, text, language, expected):
    lang(language)
    assert quick.readback(parse(text, language=language)) == expected


@pytest.mark.parametrize("text, key", [
    ("minum obat", "qr_rb_nothing_found"),
    ("rapat 31/9", "qr_rb_invalid_date"),
    ("minum obat tiap jam", "qr_rb_unsupported_repeat"),
])
def test_readback_problems_offer_the_full_dialog(lang, text, key):
    for language in ("en", "id"):
        lang(language)
        message = quick.readback(parse(text, language=language))
        assert message == quick._(key)
        assert not message.endswith(("Save?", "Simpan?"))
    lang("en")
    assert "full reminder dialog" in quick.readback(parse("minum obat"))
    lang("id")
    assert "dialog pengingat lengkap" in quick.readback(parse("minum obat"))


def test_readback_without_a_title(lang):
    lang("id")
    assert quick.readback(parse("besok jam 8")) == (
        "Saya tangkap Jumat 25 September 2026, jam 08:00, tapi belum tahu apa yang perlu "
        "diingatkan. Tambahkan ke kalimatnya.")


def test_readback_invalid_time(lang):
    result = when.resolve(dict(title="rapat", hour=25), THU)
    assert quick.readback(result) == quick._("qr_rb_invalid_time")
    assert quick.fill_readback(result) == quick._("qr_rb_invalid_time_fill")


# --- the reminder dialog: Fill in, and Edit in the quick reminder -------------------------

def test_fill_values(lang):
    assert quick.fill_values(parse("minum obat tiap 2 hari jam 8 pagi")) == {
        "title": "Minum obat", "date": "2026-09-25", "time": "08:00", "recurrence": "daily",
        "interval": 2}
    # No title in the sentence: the title field keeps what it has.
    assert quick.fill_values(parse("besok jam 8")) == {
        "date": "2026-09-25", "time": "08:00", "recurrence": "none", "interval": 1}


@pytest.mark.parametrize("text", ["minum obat", "rapat 31/9", "minum obat tiap jam"])
def test_nothing_is_filled_in_from_a_sentence_with_a_problem(text):
    assert quick.fill_values(parse(text)) is None


def test_fill_values_without_a_result():
    assert quick.fill_values(None) is None


@pytest.mark.parametrize("text, language, expected", [
    ("minum obat tiap 2 hari jam 8 pagi", "en",
     "Minum obat, Friday 25 September 2026, at 08:00, every 2 days. "
     "The fields are filled in; check them, then save."),
    ("rapat besok", "id",
     "Rapat, Jumat 25 September 2026, jam 09:00. Anda tidak menyebut jam, jadi saya pakai "
     "jam 09:00. Kolom-kolomnya sudah diisi; periksa, lalu simpan."),
    ("besok jam 8", "en",
     "I filled in Friday 25 September 2026, at 08:00, but not what to remind you about. "
     "Type it in the title field."),
])
def test_fill_readback(lang, text, language, expected):
    lang(language)
    assert quick.fill_readback(parse(text, language=language)) == expected


@pytest.mark.parametrize("text, key", [
    ("minum obat", "qr_rb_nothing_found_fill"),
    ("rapat 31/9", "qr_rb_invalid_date_fill"),
    ("minum obat tiap jam", "qr_rb_unsupported_repeat_fill"),
])
def test_fill_readback_problems_point_at_the_fields(lang, text, key):
    for language in ("en", "id"):
        lang(language)
        message = quick.fill_readback(parse(text, language=language))
        assert message == quick._(key)
        # In the full reminder dialog, it doesn't send people to itself.
        assert "full reminder dialog" not in message and "dialog pengingat lengkap" not in message


def test_full_dialog_prefill_keeps_everything(lang):
    result = parse("minum obat tiap 2 hari jam 8 pagi")
    assert quick.full_dialog_prefill(result, "minum obat tiap 2 hari jam 8 pagi", "2026-10-01") \
        == ("Minum obat", "2026-09-25", "08:00", "daily", 2)
    monthly = parse("bayar listrik tiap 3 bulan tanggal 31 jam 9")
    assert quick.full_dialog_prefill(monthly, "", "2026-10-01") == \
        ("Bayar listrik", "2026-10-31", "09:00", "monthly", 3)


def test_full_dialog_prefill_with_what_is_missing():
    assert quick.full_dialog_prefill(None, "", "2026-10-01") == ("", "2026-10-01", None, "none", 1)
    assert quick.full_dialog_prefill(None, "rapat", "2026-10-01") == \
        ("rapat", "2026-10-01", None, "none", 1)
    # Nothing about when: the words become the title, the date the fallback.
    assert quick.full_dialog_prefill(parse("minum obat"), "minum obat", "2026-10-01") == \
        ("Minum obat", "2026-10-01", None, "none", 1)
    assert quick.full_dialog_prefill(parse("rapat 31/9 jam 9"), "rapat 31/9 jam 9", "2026-10-01") \
        == ("Rapat", "2026-10-01", None, "none", 1)


def test_interval_choices(lang):
    assert quick.interval_choices("daily", 3) == ["every day", "every 2 days", "every 3 days"]
    assert quick.interval_choices("monthly", 2) == ["every month", "every 2 months"]
    assert quick.interval_choices("yearly", 2) == ["every year", "every 2 years"]
    assert len(quick.interval_choices("weekly")) == quick.MAX_INTERVAL == 30
    assert quick.interval_choices("none", 2) == ["every day", "every 2 days"]
    lang("id")
    assert quick.interval_choices("weekly", 2) == ["setiap minggu", "setiap 2 minggu"]
    assert quick.interval_choices("daily", 2) == ["setiap hari", "setiap 2 hari"]


def test_the_repeat_choice_follows_the_reminders_api():
    import core.reminders
    assert quick.REPEATS == core.reminders.RECURRENCES == when.RECURRENCES


@pytest.mark.parametrize("typed, expected", [
    ("2026-10-05", "2026-10-05"), ("2026-9-5", "2026-09-05"), (" 05/10/2026 ", "2026-10-05"),
    ("5/10/2026", "2026-10-05"), ("2026-02-30", None), ("31/9/2026", None), ("", None),
    ("besok", None), (None, None),
])
def test_the_date_field(typed, expected):
    import core.reminders
    assert core.reminders.parse_date_text(typed) == expected


@pytest.mark.parametrize("typed, expected", [
    ("14:30", "14:30"), ("8:30", "08:30"), ("08.30", "08:30"), ("00:00", "00:00"),
    ("24:00", None), ("8", None), ("jam 8", None), ("", None), (None, None),
])
def test_the_time_field(typed, expected):
    import core.reminders
    assert core.reminders.parse_time_text(typed) == expected


# --- locales ----------------------------------------------------------------------------------

def _messages(code):
    with open(os.path.join(ROOT, "locales", f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)["messages"]


def _translation_keys(path):
    """The literal keys a module passes to _()."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            yield node.args[0].value


NEW_PREFIXES = ("qr_", "rem_", "prefs_rem_", "menu_reminders", "menu_add_reminder",
                "menu_quick_reminder", "menu_with_shortcut", "nav_quick_reminder",
                "prefs_tab_reminders")


def test_locales_have_the_quick_reminder_strings():
    en, id_ = _messages("en"), _messages("id")
    ours_en = {k for k in en if k.startswith(NEW_PREFIXES)}
    ours_id = {k for k in id_ if k.startswith(NEW_PREFIXES)}
    assert ours_en == ours_id
    used = set()
    for path in ("core/quick_reminder.py", "ui/quick_reminder_dialog.py", "ui/reminder_dialog.py"):
        used |= set(_translation_keys(os.path.join(ROOT, path)))
    used |= {key + suffix for _problem, key in quick._PROBLEM_KEYS for suffix in ("", "_fill")}
    used |= {f"qr_repeat_{r}{s}" for r in ("daily", "weekly", "monthly", "yearly")
             for s in ("", "_n")}
    used |= {f"rem_every_{u}{s}" for u in ("day", "week", "month", "year") for s in ("", "_n")}
    used |= {"qr_rb_no_title_fill", "menu_reminders", "menu_add_reminder", "menu_quick_reminder",
             "menu_with_shortcut", "nav_quick_reminder", "prefs_tab_reminders",
             "prefs_rem_lbl_languages", "prefs_rem_none", "prefs_rem_privacy"}
    used |= {f"day_{i}" for i in range(7)} | {f"month_{m}" for m in range(1, 13)}
    assert not used - set(en), sorted(used - set(en))
    assert not used - set(id_), sorted(used - set(id_))


def test_locale_wording():
    en, id_ = _messages("en"), _messages("id")
    assert id_["qr_lbl_input"].startswith("Ingatkan tentang apa, dan kapan?")
    assert en["qr_lbl_input"].startswith("What should I remind you about, and when?")
    assert "minum obat besok jam 8 pagi, tiap hari" in id_["qr_lbl_input"]
    assert en["rem_lbl_sentence"] == "Or type it in one sentence:"
    assert id_["rem_lbl_sentence"] == "Atau ketik dalam satu kalimat:"
    assert en["rem_every_day_n"].format(n=2) == "every 2 days"
    assert id_["rem_every_day_n"].format(n=2) == "setiap 2 hari"
    # The core says "Anda", not "kamu".
    assert "Anda" in id_["qr_rb_time_assumed"]
    ours = [v for k, v in id_.items() if k.startswith(NEW_PREFIXES)]
    assert not [v for v in ours if "kamu" in v.lower().split()], "the core uses Anda"


# --- the N key --------------------------------------------------------------------------------

def _literal(node):
    if isinstance(node, ast.Constant):
        return node.value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ord"
            and node.args and isinstance(node.args[0], ast.Constant)):
        return ord(node.args[0].value)
    if isinstance(node, ast.Attribute):
        return node.attr
    return "<dynamic>"


def _register_calls(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "register_action":
            yield node


def _default_bindings(source, origin):
    found = []
    for node in _register_calls(source):
        kw = {k.arg: k.value for k in node.keywords}
        key = node.args[3] if len(node.args) > 3 else kw.get("default_keycode")
        ctrl = node.args[4] if len(node.args) > 4 else kw.get("default_ctrl")
        keycode = _literal(key) if key is not None else None
        if keycode in (None, "<dynamic>"):
            continue
        mods = tuple(bool(_literal(kw[m])) if m in kw else False
                     for m in ("default_shift", "default_alt", "default_win"))
        found.append(((keycode, bool(_literal(ctrl)) if ctrl is not None else False) + mods, origin))
    return found


def _main_window_source():
    with open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8") as f:
        return f.read()


PLAIN_N = (ord("N"), False, False, False, False)


def test_n_is_free_in_the_extensions_and_store_packages():
    core_bindings = [combo for combo, origin in _default_bindings(_main_window_source(), "core")]
    assert core_bindings.count(PLAIN_N) == 1
    bindings = []
    hrk = [os.path.join(EXT_ROOT, e) for e in os.listdir(EXT_ROOT) if e.endswith(".hrk")]
    store = os.path.join(ROOT, "tools", "hrk_store")
    if os.path.isdir(store):
        hrk += [os.path.join(store, e) for e in os.listdir(store) if e.endswith(".hrk")]
    for entry in sorted(os.listdir(EXT_ROOT)):
        path = os.path.join(EXT_ROOT, entry)
        if os.path.isdir(path):
            for name in os.listdir(path):
                if name.endswith(".py"):
                    with open(os.path.join(path, name), encoding="utf-8") as f:
                        bindings += _default_bindings(f.read(), entry)
    for path in hrk:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith(".py") and "lib/" not in name:
                    bindings += _default_bindings(z.read(name).decode("utf-8", "replace"),
                                                  os.path.basename(path)[:-4])
    clashes = [origin for combo, origin in bindings if combo == PLAIN_N]
    assert not clashes, clashes


def test_main_window_registers_the_quick_reminder():
    calls = [node for node in _register_calls(_main_window_source())
             if [_literal(a) for a in node.args[:2]] == ["Hariku Core", "quick_reminder"]]
    assert len(calls) == 1
    (node,) = calls
    assert _literal(node.args[3]) == ord("N") and _literal(node.args[4]) is False
    assert not node.keywords, "N is a plain, local key"
    source = _main_window_source()
    for needed in ("def OnQuickReminder", "def OnAddReminder", "def UpdateReminderMenu",
                   '_("menu_reminders")', '_("menu_quick_reminder")', "EVT_MENU_OPEN"):
        assert needed in source, needed
    # The shortcut is written in the label, never as a menu accelerator.
    en = _messages("en")
    assert "\t" not in en["menu_quick_reminder"] and "\t" not in en["menu_add_reminder"]


def test_the_old_action_id_is_renamed():
    import core.hotkeys as hk
    assert hk.RENAMED_ACTIONS["Assistant.quick_reminder"] == "Hariku Core.quick_reminder"


# --- the keybinding the Hariku Assistant extension saved ----------------------------------

N_BINDING = {"keycode": 78, "ctrl": False, "shift": False, "alt": False, "win": False,
             "global": False}
CTRL_N = dict(N_BINDING, ctrl=True)


@pytest.fixture
def hotkeys(tmp_path, monkeypatch):
    import core.api
    import core.hotkeys as hk
    path = tmp_path / "keybindings.json"
    monkeypatch.setattr(hk, "KEYBINDINGS_FILE", str(path))
    monkeypatch.setattr(hk, "saved_config", {})
    monkeypatch.setattr(hk, "actions", {})
    monkeypatch.setattr(hk, "keybindings", {})
    monkeypatch.setattr(core.api, "main_window_instance", None)
    monkeypatch.setattr(hk, "path", path, raising=False)
    return hk


def _load(hk, config):
    hk.path.write_text(json.dumps(config), encoding="utf-8")
    hk.load_keybindings()


def _register_quick_reminder(hk):
    called = []
    hk.register_action("Hariku Core", "quick_reminder", "Quick reminder", ord("N"), False,
                       lambda: called.append("core"))
    return called


def test_saved_assistant_binding_moves_to_the_core(hotkeys):
    today = dict(N_BINDING, keycode=68)
    _load(hotkeys, {"Assistant.quick_reminder": [N_BINDING], "Calendar Navigation.today": [today]})
    assert hotkeys.saved_config == {"Hariku Core.quick_reminder": [N_BINDING],
                                    "Calendar Navigation.today": [today]}
    # Saved that way, so it happens once.
    assert json.loads(hotkeys.path.read_text(encoding="utf-8")) == hotkeys.saved_config
    called = _register_quick_reminder(hotkeys)
    assert hotkeys.process_key_event(ord("N"), False) and called == ["core"]
    assert [action for (key, *_mods), (action, _g) in hotkeys.keybindings.items()
            if key == ord("N")] == ["Hariku Core.quick_reminder"]


def test_a_moved_binding_stays_moved(hotkeys):
    _load(hotkeys, {"Assistant.quick_reminder": [CTRL_N]})
    called = _register_quick_reminder(hotkeys)
    assert not hotkeys.process_key_event(ord("N"), False)
    assert hotkeys.process_key_event(ord("N"), True) and called == ["core"]


def test_an_unassigned_quick_reminder_stays_unassigned(hotkeys):
    _load(hotkeys, {"Assistant.quick_reminder": []})
    called = _register_quick_reminder(hotkeys)
    assert not hotkeys.process_key_event(ord("N"), False) and called == []


def test_the_core_binding_wins_over_the_old_one(hotkeys):
    _load(hotkeys, {"Assistant.quick_reminder": [N_BINDING],
                    "Hariku Core.quick_reminder": [CTRL_N]})
    assert hotkeys.saved_config == {"Hariku Core.quick_reminder": [CTRL_N]}


def test_keybindings_without_the_old_id_are_not_rewritten(hotkeys, monkeypatch):
    saves = []
    monkeypatch.setattr(hotkeys, "save_keybindings", lambda: saves.append(True))
    _load(hotkeys, {"Calendar Navigation.today": [dict(N_BINDING, keycode=68)]})
    assert saves == []
    called = _register_quick_reminder(hotkeys)      # the default, N
    assert hotkeys.process_key_event(ord("N"), False) and called == ["core"]


# --- the languages switched on in Preferences, Reminders ----------------------------------

def test_extra_languages_from_the_core_settings(tmp_data_dir, lang):
    import core.api
    assert quick.extra_languages() == []
    core.api.save_data("Core", {"volume": 80})
    quick.set_extra_languages(["de", "de", "", 5, "xx"])
    assert core.api.load_data("Core") == {"volume": 80, "quick_reminder_languages": ["de", "xx"]}
    assert quick.extra_languages() == ["de", "xx"]
    assert quick.active_packs() == ["en", "id", "de"]          # unknown codes are skipped
    lang("id")
    assert quick.active_packs() == ["id", "en", "de"]


def test_extra_languages_saved_by_the_assistant_extension(tmp_data_dir):
    import core.api
    core.api.save_data("Assistant", {"extra_languages": ["de"]})
    assert quick.extra_languages() == ["de"]
    # Once the core has its own setting, that is what counts.
    quick.set_extra_languages([])
    assert quick.extra_languages() == []
    core.api.save_data("Core", {"quick_reminder_languages": "de"})
    assert quick.extra_languages() == []


def test_preferences_has_a_reminders_page(monkeypatch):
    import core.core_panels
    import core.preferences
    pages = []
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda category, name, create, apply=None: pages.append(
                            (category, create, apply)))
    core.core_panels.register()
    assert (core.core_panels._("prefs_tab_reminders"), core.core_panels.create_reminders_panel,
            core.core_panels.apply_reminders_settings) in pages


def test_optional_languages(lang):
    assert quick.optional_languages() == [("de", "Deutsch")]
    lang("id")
    assert quick.optional_languages() == [("de", "Deutsch")]


# --- parsing and saving through the core reminders API -------------------------------------

@pytest.fixture
def qr(monkeypatch, tmp_data_dir, lang):
    import core.reminders
    spoken = []
    monkeypatch.setattr(quick, "speak", lambda text, interrupt=False: spoken.append(text))
    monkeypatch.setattr(quick, "_now", lambda: THU)
    monkeypatch.setattr(core.reminders, "REMINDERS_FILE",
                        os.path.join(tmp_data_dir, "reminders.json"))
    quick.spoken = spoken
    yield quick
    del quick.spoken


def test_parse_text_uses_now_the_ui_language_and_the_settings(qr, lang):
    lang("en")
    qr.set_extra_languages(["de"])
    assert qr.active_packs() == ["en", "id", "de"]
    result = qr.parse_text("morgen um 8 Uhr Zahnarzt")
    assert (result.date, result.time) == ("2026-09-25", "08:00")
    qr.set_extra_languages([])
    assert qr.active_packs() == ["en", "id"]
    assert "nothing_found" in qr.parse_text("morgen um 8 Uhr Zahnarzt").problems


def test_parse_text_with_the_dialogs_date(qr):
    result = qr.parse_text("rapat jam 3", default_date="2026-10-05")
    assert (result.date, result.time) == ("2026-10-05", "15:00")
    result = qr.parse_text("rapat jam 3", default_date=datetime.date(2026, 10, 5))
    assert (result.date, result.time) == ("2026-10-05", "15:00")
    # Today's date changes nothing: "jam 8" is still the next 8 o'clock.
    result = qr.parse_text("rapat jam 8", default_date="2026-09-24")
    assert (result.date, result.time) == ("2026-09-24", "20:00")
    # Nor does a date field that doesn't hold a date.
    result = qr.parse_text("rapat jam 8", default_date="besok")
    assert (result.date, result.time) == ("2026-09-24", "20:00")
    # A date in the sentence wins.
    result = qr.parse_text("rapat besok jam 3", default_date="2026-10-05")
    assert result.date == "2026-09-25"


def test_save_calls_the_core_reminders_api(qr, monkeypatch):
    import core.reminders
    calls = []
    monkeypatch.setattr(core.reminders, "add_reminder",
                        lambda *args, **kwargs: calls.append((args, kwargs)))
    result = qr.parse_text("minum obat tiap 2 hari jam 8 pagi")
    assert qr.save_result(result) is True
    assert calls == [(("Minum obat", "2026-09-25", "08:00"),
                      {"recurrence": "daily", "interval": 2})]
    assert qr.spoken == ["Reminder saved."]


def test_nothing_is_saved_without_a_valid_result(qr, monkeypatch):
    import core.reminders
    calls = []
    monkeypatch.setattr(core.reminders, "add_reminder", lambda *a, **k: calls.append(a))
    assert qr.save_result(None) is False
    assert qr.save_result(qr.parse_text("minum obat")) is False
    assert qr.save_result(qr.parse_text("besok jam 8")) is False
    assert calls == [] and qr.spoken == []


def test_saved_reminder_is_in_the_reminders_file(qr):
    import core.reminders
    qr.save_result(qr.parse_text("bayar listrik tiap bulan tanggal 31 jam 9"))
    saved = core.reminders.load_reminders()
    assert len(saved) == 1
    reminder = saved[0]
    # September has no 31st: the first one is in October.
    assert (reminder["title"], reminder["date"], reminder["time"]) == \
        ("Bayar listrik", "2026-10-31", "09:00")
    assert (reminder["recurrence"], reminder["interval"], reminder["is_done"]) == \
        ("monthly", 1, False)
    # The day it repeats on, so November's 30th doesn't become every 30th.
    assert reminder["anchor_day"] == 31


def test_saved_indonesian_message(qr, lang):
    lang("id")
    qr.save_result(qr.parse_text("minum obat besok jam 8"))
    assert qr.spoken == ["Pengingat disimpan."]
