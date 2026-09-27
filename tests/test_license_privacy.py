# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Help, About Hariku, License (docs/<lang>/license.txt) states the GPL license
# and a privacy summary that agrees with PRIVACY.md, with nothing left from the
# old Personal Use License: no novarealm.cloud, no opt-out telemetry. Hariku
# collects no telemetry, so Preferences has no telemetry control (core 2.11)
# and core.telemetry.is_enabled() is always False. wx is mocked (conftest.py).

import ast
import os
import re
from unittest.mock import MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("en", "id")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _license(lang):
    return _read("docs", lang, "license.txt")


def _flat(lang):
    """The license text with its line breaks and indentation folded to spaces."""
    return " ".join(_license(lang).split())


# ------------------------------------------------------------
# docs/<lang>/license.txt
# ------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_license_has_no_novarealm_or_old_brands(lang):
    text = _license(lang).lower()
    for word in ("novarealm", "nova realm", "inflinity"):
        assert word not in text, (lang, word)


@pytest.mark.parametrize("lang", LANGS)
def test_license_states_the_gpl_and_the_extension_exception(lang):
    text = _flat(lang)
    assert "GPL-3.0-or-later" in text and "GNU General Public License" in text
    assert "LICENSE-EXCEPTION" in text
    assert re.search(r"^\s+LICENSE\s", _license(lang), re.M)
    assert "https://www.gnu.org/licenses/gpl-3.0.html" in text
    assert "https://github.com/InfiArtt/hariku-core" in text
    assert "https://github.com/InfiArtt/hariku-sdk" in text
    assert "Personal Use License" in text      # "earlier versions used ..."
    assert "Rafli / InfiArtt" in text and "27 September 2026" in text


@pytest.mark.parametrize("lang", LANGS)
def test_license_points_to_privacy_md(lang):
    text = _flat(lang)
    assert "PRIVACY.md" in text
    assert "https://github.com/InfiArtt/hariku-core/blob/main/PRIVACY.md" in text


@pytest.mark.parametrize("lang", LANGS)
def test_license_makes_no_telemetry_claims(lang):
    text = _flat(lang).lower()
    assert not re.search(r"telemetr\w*\s*\(opt-out\)", text)
    for phrase in ("opt-out model", "share my anonymous usage data", "/stats",
                   "/api/telemetry", "usage statistics on startup"):
        assert phrase not in text, (lang, phrase)
    # It says the opposite, in so many words.
    assert ("collects no analytics or telemetry" in text
            or "tidak mengumpulkan analitik atau telemetri" in text)


@pytest.mark.parametrize("lang", LANGS)
def test_license_has_no_email_address(lang):
    # The owner picks the contact address later; until then, none.
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", _license(lang))


@pytest.mark.parametrize("lang", LANGS)
def test_license_names_only_hosts_privacy_md_names(lang):
    import core.endpoints
    privacy = _read("PRIVACY.md").lower()
    text = _license(lang).lower()
    hosts = set(re.findall(r"\b(?:[a-z0-9-]+\.)+(?:com|org|io|gov|dev|info|at)\b", text))
    assert core.endpoints.PAGES_HOST in hosts            # updates, store, trust list
    assert "infiartt.com" in hosts                       # crash reports, Orbit, accounts
    # Links to the license, the source, the SDK and the forum are not connections.
    extra = {"www.gnu.org", "github.com"}
    unknown = sorted(h for h in hosts if h not in privacy and h not in extra)
    assert not unknown, unknown


def test_the_release_ships_the_files_the_license_names():
    workflow = _read(".github", "workflows", "release.yml")
    for name in ("LICENSE", "LICENSE-EXCEPTION", "PRIVACY.md", "THIRD-PARTY-NOTICES.md"):
        assert f"--include-data-file={name}={name}" in workflow, name
        assert os.path.isfile(os.path.join(ROOT, name)), name


def test_no_shipped_doc_mentions_novarealm_except_history():
    # What's New keeps its history; everything else in docs/ is current.
    bad = []
    for folder, _dirs, files in os.walk(os.path.join(ROOT, "docs")):
        for name in files:
            if name == "whats_new.txt":
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as f:
                if "novarealm" in f.read().lower():
                    bad.append(os.path.relpath(path, ROOT))
    assert not bad, bad


# ------------------------------------------------------------
# No telemetry control in Preferences
# ------------------------------------------------------------

def test_core_panels_has_no_telemetry_code():
    tree = ast.parse(_read("core", "core_panels.py"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
        elif isinstance(node, ast.Name):
            value = node.id
        elif isinstance(node, ast.Attribute):
            value = node.attr
        else:
            continue
        if "telemetry" in value.lower() or "usage data" in value.lower():
            found.append((node.lineno, value))
    assert not found, found


WIDGETS = ("CheckBox", "StaticText", "StaticBox", "StaticBoxSizer", "Slider", "ComboBox",
           "Choice", "RadioBox", "Button", "BoxSizer")


@pytest.fixture
def general_panel(tmp_data_dir, monkeypatch):
    """The General page built with recording widgets, and what they were labelled."""
    import wx
    import core.api
    import core.core_panels
    import core.events
    made = []

    def factory(kind):
        def make(*args, **kwargs):
            widget = MagicMock(name=kind)
            widget.GetValue.return_value = 100 if kind == "Slider" else False
            widget.GetSelection.return_value = 0
            widget.GetStringSelection.return_value = ""
            widget.GetCount.return_value = 0
            label = kwargs.get("label")
            if label is None and len(args) > 1 and isinstance(args[1], str):
                label = args[1]
            made.append((kind, label or ""))
            return widget
        return make

    for kind in WIDGETS:
        monkeypatch.setattr(wx, kind, factory(kind), raising=False)
    monkeypatch.setattr(core.core_panels, "get_available_languages", lambda domain: [])
    # The page is a MagicMock subclass here; a missing method would be made by
    # calling the page's own __init__ again.
    monkeypatch.setattr(core.core_panels.GeneralSettingsPanel, "SetSizer",
                        lambda self, sizer: None, raising=False)
    monkeypatch.setattr(core.events.bus, "emit", lambda *args, **kwargs: None)
    # An old config, from when the telemetry box existed.
    core.api.save_data("Core", {"language": "en", "telemetry_enabled": True,
                                "telemetry_id": "0f1e2d3c-old", "close_behavior": "quit"})
    panel = core.core_panels.GeneralSettingsPanel(None)
    return panel, made


def test_general_page_has_no_telemetry_control(general_panel):
    panel, made = general_panel
    kinds = [kind for kind, _label in made]
    assert "CheckBox" in kinds and "Button" in kinds        # the page was really built
    labels = [label.lower() for _kind, label in made]
    assert not [l for l in labels if "telemetry" in l or "usage data" in l], labels
    assert "StaticBox" not in kinds                          # the telemetry box was the only one
    assert "chk_telemetry" not in vars(panel)


def test_general_page_ignores_old_telemetry_keys(general_panel):
    import core.api
    panel, _made = general_panel
    panel.ApplyChanges()
    saved = core.api.load_data("Core")
    assert saved["close_behavior"] == "minimize"            # ApplyChanges did save
    # Old keys load fine and are left alone: nothing reads or writes them.
    assert saved["telemetry_enabled"] is True and saved["telemetry_id"] == "0f1e2d3c-old"


# ------------------------------------------------------------
# core.telemetry: kept for extensions, always off
# ------------------------------------------------------------

def test_telemetry_is_never_enabled_and_never_sends(tmp_data_dir, monkeypatch):
    import threading
    import urllib.request
    import core.api
    import core.telemetry

    def refuse(*args, **kwargs):
        raise AssertionError("telemetry must not touch the network or start threads")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(threading, "Thread", refuse)
    core.api.save_data("Core", {"telemetry_enabled": True})
    assert core.telemetry.is_enabled() is False
    assert core.telemetry.record_startup() is None
    assert core.api.load_data("Core") == {"telemetry_enabled": True}   # no id written
    assert not hasattr(core.telemetry, "API_URL")


def test_hariku_imports_telemetry_but_sends_nothing():
    # Nuitka only compiles modules the core imports; extensions may still call
    # telemetry.is_enabled() (DEVELOPERS.md), so hariku.py keeps the import.
    source = _read("hariku.py")
    assert re.search(r"^import core\.telemetry$", source, re.M)
    assert "record_startup" not in source


def test_no_telemetry_endpoint_is_left():
    import core.endpoints
    assert not hasattr(core.endpoints, "TELEMETRY_URL")
    assert "telemetry" not in core.endpoints.CRASH_REPORT_URL


# ------------------------------------------------------------
# Language files: no novarealm.cloud contact left
# ------------------------------------------------------------

def _locale_files():
    import glob
    return sorted(glob.glob(os.path.join(ROOT, "locales", "*.json"))
                  + glob.glob(os.path.join(ROOT, "extensions", "*", "locales", "*.json")))


def test_no_locale_mentions_novarealm():
    files = _locale_files()
    assert len(files) > 10
    bad = [os.path.relpath(p, ROOT) for p in files
           if "novarealm" in open(p, encoding="utf-8").read().lower()]
    assert not bad, bad


def test_core_locales_point_to_the_issue_tracker_and_still_load(i18n_cache):
    # core.i18n needs the "email" key; it may hold a web address, and nothing
    # shows it as an email.
    import json
    from core import i18n
    for lang in LANGS:
        with open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8") as f:
            manifest = json.load(f)["manifest"]
        assert manifest["email"] == "https://github.com/InfiArtt/hariku/issues"
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    assert set(LANGS) <= set(i18n_cache["core"])
