# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The Extension Manager's tabs (core.extension_catalog): what each lists and
# says, and the loader's side of it: extensions too old for this Hariku, ones
# that need a newer one, and the errors extensions stop with.

import json
import os
import sys

import pytest

import core.constants
import core.extension_catalog as catalog
import core.extension_manager as manager

SYSTEM = os.path.abspath(os.path.join(os.sep, "hariku", "extensions"))
USER = os.path.abspath(os.path.join(os.sep, "appdata", "Hariku2", "extensions"))


@pytest.fixture
def lang(monkeypatch):
    from core import i18n
    had_core, old_core = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    monkeypatch.setattr(i18n, "_current_language", "en")

    def use(code):
        monkeypatch.setattr(i18n, "_current_language", code)
    yield use
    if had_core:
        i18n._language_cache["core"] = old_core
    else:
        i18n._language_cache.pop("core", None)


@pytest.fixture
def core_28(monkeypatch):
    monkeypatch.setattr(core.constants, "CORE_VERSION", "2.8.0")
    monkeypatch.setattr(core.constants, "EXTENSION_API_BACK_COMPAT", "2.0")


def info(ext_id, version="1.0", *, folder=SYSTEM, packed=False, enabled=True, minimum="2.0",
         tested="", missing=(), name=None, author="Rafli", description=""):
    path = os.path.join(folder, ext_id + (".hrk" if packed else ""))
    return {"id": ext_id, "name": name or ext_id.replace("_", " ").title(), "version": version,
            "author": author, "description": description or f"About {ext_id}.",
            "is_enabled": enabled, "is_unpacked": not packed, "path": path,
            "minimum_core_version": minimum, "last_tested_core_version": tested,
            "missing_fields": list(missing)}


def entry(ext_id, version, minimum="", tested="", name=None, author="Rafli"):
    e = {"id": ext_id, "name": name or ext_id.replace("_", " ").title(), "version": version,
         "description": f"Store {ext_id}.", "author": author,
         "download_url": f"https://example.invalid/{ext_id}.hrk"}
    if minimum:
        e["minimum_core_version"] = minimum
    if tested:
        e["last_tested_core_version"] = tested
    return e


def ids(rows):
    return [row["id"] for row in rows]


# --- The loader's rules ---------------------------------------------------------------------

def test_needs_newer_core_compares_major_and_minor(core_28):
    assert manager.needs_newer_core({"minimum_core_version": "2.9"}) == "2.9"
    assert manager.needs_newer_core({"minimum_core_version": "2.10"}) == "2.10"
    assert manager.needs_newer_core({"minimum_core_version": "2.8"}) == ""
    assert manager.needs_newer_core({"minimum_core_version": "2.8.5"}) == ""   # as the loader
    assert manager.needs_newer_core({}) == ""
    assert manager.needs_newer_core({"minimum_core_version": "soon"}) == ""


def test_too_old_uses_last_tested_then_minimum(core_28):
    assert manager.too_old_for_core({"minimum_core_version": "1.5"}) == "1.5"
    assert manager.too_old_for_core({"minimum_core_version": "1.5",
                                     "last_tested_core_version": "2.3"}) == ""
    assert manager.too_old_for_core({"minimum_core_version": "2.0"}) == ""
    assert manager.too_old_for_core({}) == ""


def test_every_extension_made_so_far_still_runs():
    # No 2.x change broke extensions: key_notifier's manifest even says 1.0.
    assert core.constants.EXTENSION_API_BACK_COMPAT == "1.0"
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extensions")
    for ext_id in os.listdir(root):
        path = os.path.join(root, ext_id, "manifest.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                assert not manager.too_old_for_core(json.load(f)), ext_id


def _write_extension(folder, ext_id, main_source, **manifest):
    ext_dir = folder / ext_id
    ext_dir.mkdir()
    data = {"name": ext_id, "version": "1.0", "description": "Test.", "main": "main.py",
            "author": "Tester", "language": "en", "minimum_core_version": "2.0"}
    data.update(manifest)
    (ext_dir / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    (ext_dir / "main.py").write_text(main_source, encoding="utf-8")
    return str(ext_dir)


@pytest.fixture
def loader(monkeypatch, fresh_event_bus):
    monkeypatch.setattr(manager, "bus", fresh_event_bus)
    monkeypatch.setattr(manager, "LOADED_EXTENSIONS", {})
    monkeypatch.setattr(manager, "LOAD_ERRORS", {})
    yield manager
    for name in [n for n in sys.modules if n.startswith("hariku_ext.catalog_test_")]:
        sys.modules.pop(name, None)


def test_the_loader_refuses_an_extension_too_old(loader, tmp_path, monkeypatch, core_28):
    path = _write_extension(tmp_path, "catalog_test_old", "def register(bus): pass\n",
                            minimum_core_version="1.2")
    assert loader._load_extension_from_dir(path, "catalog_test_old") is False
    assert "catalog_test_old" not in loader.LOADED_EXTENSIONS


def test_the_loader_remembers_the_error_an_extension_stopped_with(loader, tmp_path):
    path = _write_extension(tmp_path, "catalog_test_boom",
                            "def register(bus):\n    raise RuntimeError('no weather key')\n")
    assert loader._load_extension_from_dir(path, "catalog_test_boom") is False
    assert loader.LOAD_ERRORS["catalog_test_boom"] == "RuntimeError: no weather key"

    ok = _write_extension(tmp_path, "catalog_test_fine", "def register(bus): pass\n")
    loader.LOAD_ERRORS["catalog_test_fine"] = "an earlier error"
    assert loader._load_extension_from_dir(ok, "catalog_test_fine") is True
    assert "catalog_test_fine" not in loader.LOAD_ERRORS


def test_the_loader_remembers_a_missing_main_file(loader, tmp_path):
    path = _write_extension(tmp_path, "catalog_test_nomain", "", main="start.py")
    assert loader._load_extension_from_dir(path, "catalog_test_nomain") is False
    assert loader.LOAD_ERRORS["catalog_test_nomain"] == "start.py is missing"


def test_installed_info_has_the_core_versions_and_missing_fields(tmp_path, monkeypatch):
    system, user = tmp_path / "system", tmp_path / "user"
    system.mkdir(), user.mkdir()
    _write_extension(system, "weather", "", minimum_core_version="2.8",
                     last_tested_core_version="2.9")
    broken = system / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text(json.dumps({"name": "Broken", "version": "0.1"}),
                                          encoding="utf-8")
    monkeypatch.setattr(manager, "SYSTEM_EXTENSIONS_DIR", str(system))
    monkeypatch.setattr(manager, "USER_EXTENSIONS_DIR", str(user))
    monkeypatch.setattr(manager, "_get_disabled_extensions", lambda: [])
    found = {i["id"]: i for i in manager.get_installed_extensions_info()}
    assert found["weather"]["minimum_core_version"] == "2.8"
    assert found["weather"]["last_tested_core_version"] == "2.9"
    assert found["weather"]["missing_fields"] == []
    assert found["broken"]["missing_fields"] == ["description", "main", "author", "language",
                                                 "minimum_core_version"]


# --- The tabs -------------------------------------------------------------------------------

def test_source_of():
    assert catalog.source_of(info("weather"), SYSTEM) == catalog.BUNDLED
    assert catalog.source_of(info("weather", folder=USER, packed=True), SYSTEM) == catalog.STORE
    assert catalog.source_of(info("mine", folder=USER), SYSTEM) == catalog.DEVELOPER


def test_the_tabs(core_28):
    installed = [
        info("weather", "1.1"),                                     # store has 1.2
        info("space", "1.0"),                                       # store's 1.1 needs 2.9
        info("finance", "1.0"),                                     # up to date
        info("routines", "1.0", minimum="2.9"),                     # needs a newer Hariku
        info("oldie", "0.9", minimum="1.0", folder=USER, packed=True),   # too old
        info("broken", "0.1", missing=["main"]),                    # broken manifest
        info("crashy", "1.0", folder=USER, packed=True),            # stopped with an error
        info("mine", "0.1", folder=USER),                           # developer folder
        info("lumina", "1.0", enabled=False),
    ]
    registry = [
        entry("weather", "1.2", "2.8"),
        entry("space", "1.1", "2.9"),
        entry("finance", "1.0"),
        entry("mine", "9.0"),                        # never replaces a developer folder
        entry("observatory", "1.0", "2.8"),          # available
        entry("aurora", "1.0", "3.0"),               # needs a newer Hariku
        entry("ancient", "1.0", "1.4"),              # too old
        entry("tested", "1.0", "1.4", tested="2.5"), # old minimum, tested recently: fine
    ]
    tabs = catalog.build(installed, registry, SYSTEM, {"crashy": "RuntimeError: boom"})
    assert set(tabs) == set(catalog.TABS)
    assert ids(tabs["installed"]) == ["broken", "crashy", "finance", "lumina", "mine",
                                      "routines", "space", "weather"]
    assert ids(tabs["updates"]) == ["space", "weather"]
    assert ids(tabs["available"]) == ["aurora", "observatory", "tested"]
    assert ids(tabs["incompatible"]) == ["ancient", "oldie"]

    rows = {row["id"]: row for tab in tabs.values() for row in tab}
    assert rows["weather"]["update"] == "1.2" and catalog.can_update(rows["weather"])
    assert rows["space"]["needs_core"] == "2.9" and not catalog.can_update(rows["space"])
    assert rows["mine"]["update"] == ""
    assert (rows["routines"]["problem"], rows["routines"]["problem_detail"]) == ("needs_core",
                                                                                 "2.9")
    assert rows["broken"]["problem"] == "manifest"
    assert (rows["crashy"]["problem"], rows["crashy"]["problem_detail"]) == (
        "error", "RuntimeError: boom")
    assert rows["oldie"]["problem"] == "too_old" and rows["ancient"]["problem"] == "too_old"
    assert catalog.can_install(rows["observatory"])
    assert not catalog.can_install(rows["aurora"]) and catalog.waits_for_core(rows["aurora"]) == "3.0"
    assert catalog.waits_for_core(rows["routines"]) == "2.9"
    assert catalog.waits_for_core(rows["weather"]) == ""
    assert rows["weather"]["official"] and not rows["tested"]["official"]


def test_before_the_store_answers(core_28):
    tabs = catalog.build([info("weather"), info("oldie", minimum="1.0")], None, SYSTEM)
    assert ids(tabs["installed"]) == ["weather"]
    assert tabs["updates"] == [] and tabs["available"] == []
    assert ids(tabs["incompatible"]) == ["oldie"]


def test_official_comes_from_the_fixed_list_not_the_author():
    tabs = catalog.build([], [entry("fake_weather", "1.0", author="Rafli")], SYSTEM)
    assert tabs["available"][0]["official"] is False


def test_rows_are_sorted_by_name(core_28):
    installed = [info("b", name="banana"), info("a", name="Apple"), info("c", name="cherry")]
    assert ids(catalog.build(installed, [], SYSTEM)["installed"]) == ["a", "b", "c"]


def test_matching_needs_every_word():
    rows = [dict(name="Weather", description="Forecast for your place.", author="Rafli"),
            dict(name="Earthquakes", description="BMKG and USGS.", author="Rafli"),
            dict(name="Lumina", description="Screen curtain.", author="Someone")]
    assert [r["name"] for r in catalog.matching(rows, "")] == ["Weather", "Earthquakes", "Lumina"]
    assert [r["name"] for r in catalog.matching(rows, "  RAFLI place ")] == ["Weather"]
    assert [r["name"] for r in catalog.matching(rows, "someone")] == ["Lumina"]
    assert catalog.matching(rows, "nothing here") == []


# --- The words ------------------------------------------------------------------------------

def _all_rows():
    installed = [info("weather", "1.1"), info("space"), info("routines", minimum="2.9"),
                 info("oldie", minimum="1.0", folder=USER, packed=True),
                 info("broken", missing=["main"]), info("crashy"), info("mine", folder=USER),
                 info("lumina", enabled=False, author="")]
    registry = [entry("weather", "1.2"), entry("space", "1.1", "2.9"),
                entry("observatory", "1.0"), entry("aurora", "1.0", "3.0"),
                entry("ancient", "1.0", "1.4")]
    return catalog.build(installed, registry, SYSTEM, {"crashy": "RuntimeError: boom"})


@pytest.mark.parametrize("code", ["en", "id"])
def test_every_row_has_words_in_both_languages(lang, core_28, code):
    lang(code)
    for tab, rows in _all_rows().items():
        for row in rows:
            for done in ("", "downloading", "installed", "updated", "removed", "failed"):
                for text in (catalog.status_text(row, tab, done),
                             catalog.details_text(row, tab, done),
                             catalog.version_text(row, tab)):
                    assert "ext_" not in text and "{" not in text, (tab, row["id"], text)
        assert "ext_" not in catalog.tab_title(tab, len(rows))
        assert "ext_" not in catalog.tab_title(tab, None)


def test_the_words_in_english(lang, core_28):
    tabs = _all_rows()
    rows = {(tab, row["id"]): row for tab, tab_rows in tabs.items() for row in tab_rows}
    status = lambda tab, ext_id, done="": catalog.status_text(rows[tab, ext_id], tab, done)
    assert status("installed", "weather") == "Enabled, update 1.2 available"
    assert status("installed", "space") == "Enabled"             # its update needs 2.9
    assert status("installed", "lumina") == "Disabled"
    assert status("installed", "routines") == "Not running: needs Hariku 2.9"
    assert status("installed", "broken") == "Not running: its manifest is broken"
    assert status("installed", "crashy") == "Stopped with an error"
    assert status("updates", "weather") == "Ready to update"
    assert status("updates", "space") == "Needs Hariku 2.9"
    assert status("available", "observatory") == ""
    assert status("available", "aurora") == "Needs Hariku 3.0"
    assert status("incompatible", "oldie") == "Too old: made for Hariku 1.0"
    assert status("available", "observatory", "installed") == "Installed, restart Hariku to use it"
    assert catalog.version_text(rows["updates", "weather"], "updates") == "1.1 to 1.2"
    assert catalog.tab_title("updates", 2) == "Updates (2)"
    assert catalog.tab_title("updates", None) == "Updates"

    weather = catalog.details_text(rows["installed", "weather"], "installed")
    assert weather.splitlines()[:4] == [
        "Weather 1.1, by Rafli (official).", "Enabled.",
        "It comes with Hariku: you can disable it, but not remove it.",
        "Version 1.2 is in the store."]
    assert weather.endswith("\n\nAbout weather.")
    space = catalog.details_text(rows["updates", "space"], "updates")
    assert ("Version 1.1 is in the store, but it needs Hariku 2.9 and you have 2.8.0. "
            "The version you have keeps working.") in space
    oldie = catalog.details_text(rows["incompatible", "oldie"], "incompatible")
    assert "Installed from the Extension Store." in oldie
    assert ("It was made for Hariku 1.0, and Hariku 2.8.0 only runs extensions made for "
            "Hariku 2.0 or later.") in oldie
    crashy = catalog.details_text(rows["installed", "crashy"], "installed")
    assert "It stopped with an error when Hariku started: RuntimeError: boom." in crashy
    lumina = catalog.details_text(rows["installed", "lumina"], "installed")
    assert lumina.startswith("Lumina 1.0, by an unknown author (official).\nDisabled.")


def test_the_words_in_indonesian(lang, core_28):
    lang("id")
    tabs = _all_rows()
    weather = [r for r in tabs["installed"] if r["id"] == "weather"][0]
    assert catalog.status_text(weather, "installed") == "Aktif, pembaruan 1.2 tersedia"
    oldie = tabs["incompatible"][-1]
    assert catalog.status_text(oldie, "incompatible") == "Terlalu lama: dibuat untuk Hariku 1.0"
    assert catalog.tab_title("incompatible", 1) == "Tidak kompatibel (1)"


def test_every_button_and_message_the_window_uses_exists(lang):
    import ast
    source_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "ui", "extension_manager_dialog.py")
    with open(source_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    keys = {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value.startswith(("ext_", "dlg_ext"))}
    buttons = {"ext_btn_" + key for key in ("toggle", "uninstall", "update", "update_all",
                                            "install", "check_core")}
    empties = {"ext_msg_empty_" + tab for tab in catalog.TABS}
    from core import i18n
    for code in ("en", "id"):
        messages = i18n._language_cache["core"][code]["messages"]
        missing = sorted(k for k in (keys - {"ext_btn_", "ext_msg_empty_", "ext_tab_"}) | buttons | empties
                         if k not in messages)
        assert not missing, (code, missing)
