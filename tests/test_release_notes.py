# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""The update window's release notes (core 2.12.1): taken from What's New by
tools/release_notes.py when a version is released, shown in the user's
language by core.updater, and every What's New entry starts by saying why
the release is out."""
import importlib.util
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tool():
    spec = importlib.util.spec_from_file_location("release_notes",
                                                  os.path.join(ROOT, "tools", "release_notes.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


WHATS_NEW = """Version 2.13.0 (Core Update - October 1, 2026)
================================================================================
Why this update: reminders got
friendlier.

- First item, wrapped
  over two lines.
- Second item.

Version 2.12.0 (Core Update - September 28, 2026)
================================================================================
- Older.
"""


def test_a_version_s_entry_is_unwrapped_into_paragraphs_and_items():
    rn = _tool()
    lines = rn.section_lines(WHATS_NEW, "2.13.0", "Version")
    assert rn.unwrap(lines) == ("Why this update: reminders got friendlier.\n\n"
                                "- First item, wrapped over two lines.\n\n- Second item.")
    assert rn.unwrap(rn.section_lines(WHATS_NEW, "2.12.0", "Version")) == "- Older."
    with pytest.raises(KeyError):
        rn.section_lines(WHATS_NEW, "2.13", "Version")        # not a prefix of 2.13.0
    with pytest.raises(KeyError):
        rn.section_lines(WHATS_NEW, "9.9.9", "Version")


def test_the_released_version_has_notes_in_every_language(tmp_path):
    from core.constants import CORE_VERSION
    rn = _tool()
    out = tmp_path / "notes.json"
    text = tmp_path / "notes_en.txt"
    assert rn.main([CORE_VERSION, "--json", str(out), "--text", str(text)]) == 0
    notes = json.loads(out.read_text(encoding="utf-8"))
    assert set(notes) == {"en", "id"}
    assert all(notes[lang] for lang in notes)
    assert text.read_text(encoding="utf-8") == notes["en"] + "\n"
    for lang in notes:
        assert "====" not in notes[lang] and "\n  " not in notes[lang]


def test_a_version_without_notes_isnt_released(capsys):
    assert _tool().main(["9.9.9"]) == 1
    assert "Write the What's New entry first" in capsys.readouterr().err


def test_the_release_workflow_uses_the_notes():
    workflow = _read(".github", "workflows", "release.yml")
    assert "python tools/release_notes.py" in workflow
    assert "release_notes        = $notes.en" in workflow
    assert "release_notes_id     = $notes.id" in workflow
    assert "--notes-file release_notes_en.txt" in workflow
    assert workflow.index("tools/release_notes.py") < workflow.index("python -m nuitka")


def _entries(text, word):
    """[(version, first line of its body)] of every entry."""
    found = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"{word} (\d+\.\d+\.\d+)", line)
        if m:
            body = [x for x in lines[i + 2:i + 6] if x.strip()]
            found.append((m.group(1), body[0] if body else ""))
    return found


@pytest.mark.parametrize("lang, word", [("en", "Version"), ("id", "Versi")])
def test_every_entry_since_2_12_says_first_why_the_release_is_out(lang, word):
    # The update window shows the entry: before the list of changes, a
    # paragraph says what the release is for.
    for version, first in _entries(_read("docs", lang, "whats_new.txt"), word):
        if tuple(int(p) for p in version.split(".")) >= (2, 12, 0):
            assert first and not first.startswith("- "), (lang, version, first)


# ------------------------------------------------------------
# The update window
# ------------------------------------------------------------

@pytest.fixture
def lang(monkeypatch):
    from core import i18n
    had, old = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)

    def use(code):
        monkeypatch.setattr(i18n, "_current_language", code)
    use("en")
    yield use
    if had:
        i18n._language_cache["core"] = old
    else:
        i18n._language_cache.pop("core", None)


def test_the_notes_are_in_the_user_s_language(lang):
    from core.updater import release_notes_for
    info = {"latest_version": "2.12.1", "release_notes": "English.", "release_notes_id": "Indonesia."}
    assert release_notes_for(info, "en") == "English."
    assert release_notes_for(info, "id") == "Indonesia."
    assert release_notes_for(info, "id-ID") == "Indonesia."
    assert release_notes_for(info, "de") == "English."                  # no German notes
    lang("id")
    assert release_notes_for(info) == "Indonesia."
    # An older version.json, with only its version: a line saying which it is.
    assert release_notes_for({"latest_version": "2.12.1", "release_notes": " "}, "id") == \
        "Hariku 2.12.1."
    assert len(release_notes_for({"release_notes": "x" * 20000}, "en")) == 8000


@pytest.mark.parametrize("code", ["en", "id"])
def test_the_update_window_is_translated(code):
    with open(os.path.join(ROOT, "locales", f"{code}.json"), encoding="utf-8") as f:
        messages = json.load(f)["messages"]
    source = _read("core", "updater.py")
    for key in sorted(set(re.findall(r'_\("(upd_[a-z_]+)"', source))):
        assert key in messages, key
    assert '"Download & Install Now"' not in source            # "& " made space the access key
    for key in ("upd_btn_install", "upd_btn_later", "upd_btn_later_n", "upd_btn_skip"):
        assert messages[key].count("&") == 1, key
