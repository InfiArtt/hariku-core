# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a reminder says when it fires, is done or is snoozed (core 2.12): in
the persona Hariku talks in, with the user's nickname, a different line each
time, "sorry I'm late" after a catch-up, and read well without a nickname."""
import datetime
import json
import os
import random

import pytest

import core.reminders as rem

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSONAS = ("", "sweet", "bro", "royal", "polite")


def _messages(code):
    with open(os.path.join(ROOT, "locales", f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)["messages"]


@pytest.fixture
def lang(monkeypatch):
    from core import i18n
    had, old = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)

    def use(code):
        monkeypatch.setattr(i18n, "_current_language", code)
    use("id")
    yield use
    if had:
        i18n._language_cache["core"] = old
    else:
        i18n._language_cache.pop("core", None)


@pytest.fixture
def nickname(monkeypatch):
    name = {"value": "Rafli"}
    import core.persona
    monkeypatch.setattr(core.persona, "current_nickname", lambda: name["value"])

    def use(value):
        name["value"] = value
    return use


@pytest.mark.parametrize("code", ["id", "en"])
def test_every_persona_has_every_line(code):
    messages = _messages(code)
    keys = ["rem_dialog_title", "rem_btn_snooze", "rem_btn_done", "rem_fire_late",
            "rem_snoozed", "rem_deleted"]
    keys += [f"rem_fire_{n}" for n in range(1, rem.FIRE_VARIANTS + 1)]
    keys += [f"rem_done_{n}" for n in range(1, rem.DONE_VARIANTS + 1)]
    for key in keys:
        assert key in messages, key
    # Each persona has its own firing, late, done and snoozed lines: none falls
    # back to the playful one in the middle of another persona.
    for persona in PERSONAS[1:]:
        for n in range(1, rem.FIRE_VARIANTS + 1):
            assert f"rem_fire_{n}@{persona}" in messages, (persona, n)
        for n in range(1, rem.DONE_VARIANTS + 1):
            assert f"rem_done_{n}@{persona}" in messages, (persona, n)
        for key in ("rem_fire_late", "rem_snoozed"):
            assert f"{key}@{persona}" in messages, (key, persona)


@pytest.mark.parametrize("code", ["id", "en"])
def test_the_title_and_name_go_in_every_line(code):
    for key, text in _messages(code).items():
        if key.startswith(("rem_fire_", "rem_done_", "rem_snoozed")):
            assert "{title}" in text, key
            assert not text.startswith("{name}"), key          # reads well without one
        if key.startswith("rem_fire_"):
            assert "{name}" in text, key
        if key.startswith(("rem_btn_snooze", "rem_btn_done")):
            assert text.count("&") == 1, key                   # one access key


@pytest.mark.parametrize("before, after", [
    ("Hei , ada pengingat nih: X.", "Hei, ada pengingat nih: X."),
    ("Psst, ! Ada pengingat nih: X.", "Psst! Ada pengingat nih: X."),
    ("Ampun, , sudah tiba waktunya: X.", "Ampun, sudah tiba waktunya: X."),
    ("Hamba menghadap, . Tiba waktunya: X.", "Hamba menghadap. Tiba waktunya: X."),
    ("Sudah waktunya, : X.", "Sudah waktunya: X."),
    ("Hai ~ ada pengingat", "Hai~ ada pengingat"),
    ("Bro  Rafli, ada", "Bro Rafli, ada"),
])
def test_tidy(before, after):
    assert rem.tidy(before) == after


@pytest.mark.parametrize("code", ["id", "en"])
@pytest.mark.parametrize("persona", PERSONAS)
def test_every_line_reads_well_with_and_without_a_nickname(lang, nickname, code, persona):
    from core import i18n
    lang(code)
    i18n.set_persona(persona)
    title = "Minum obat, 2 tablet (penting!)"
    for name in ("Rafli", ""):
        nickname(name)
        lines = {rem.fire_text(title) for _ in range(40)}
        lines.add(rem.fire_text(title, late_minutes=30, due="08:05"))
        lines.add(rem._say(rem._variant("rem_done", rem.DONE_VARIANTS), title))
        lines.add(rem._say("rem_snoozed", title, minutes=5))
        for line in lines:
            assert title in line, line                         # the title as it is
            assert "{" not in line and "}" not in line, line
            assert " ," not in line and ",," not in line and ", !" not in line, line
            assert "  " not in line and line == line.strip(), line
            if name:
                assert "Rafli" in line or "rem_done" in line or "Minum obat" in line
        assert len({rem.fire_text(title) for _ in range(60)}) == rem.FIRE_VARIANTS


def test_the_persona_changes_the_words(lang, nickname):
    from core import i18n
    lang("id")
    random_line = random.Random(1)
    i18n.set_persona("bro")
    assert ": minum obat." in rem.fire_text("minum obat", rng=random_line)
    bro = {rem.fire_text("minum obat") for _ in range(40)}
    assert "Bro Rafli, ada pengingat nih: minum obat." in bro
    i18n.set_persona("royal")
    royal = {rem.fire_text("minum obat") for _ in range(40)}
    assert "Ampun, Rafli, sudah tiba waktunya: minum obat." in royal
    assert not bro & royal
    lang("en")
    i18n.set_persona("")
    assert "Psst, Rafli! Reminder time: take medicine." in \
        {rem.fire_text("take medicine") for _ in range(40)}


def test_never_the_same_line_twice_in_a_row(lang, nickname):
    last = None
    for _ in range(50):
        line = rem.fire_text("x")
        assert line != last
        last = line


def test_late_reminders_say_so_with_their_time(lang, nickname):
    lang("id")
    assert rem.fire_text("rapat", late_minutes=45, due="08:05") == \
        "Maaf telat, Rafli! Tadi jam 08.05 ada pengingat: rapat."
    assert "telat" not in rem.fire_text("rapat", late_minutes=rem.LATE_MINUTES - 1, due="08:05")
    lang("en")
    assert rem.fire_text("meeting", late_minutes=45, due="20:05") == \
        "Sorry I'm late, Rafli! This was for 8:05 PM: meeting."


def test_minutes_late():
    r = {"date": "2026-09-28", "time": "08:00"}
    assert rem.minutes_late(r, datetime.datetime(2026, 9, 28, 8, 0, 40)) == 0
    assert rem.minutes_late(r, datetime.datetime(2026, 9, 28, 9, 30)) == 90
    assert rem.minutes_late(r, datetime.datetime(2026, 9, 28, 7, 0)) == 0
    assert rem.minutes_late({"date": "x"}, datetime.datetime(2026, 9, 28)) == 0


def test_the_nickname_comes_from_the_profile(tmp_data_dir, lang):
    import core.personal
    core.personal.set_name("Rafli Hidayat", "Bos")
    lines = {rem.fire_text("x") for _ in range(40)}
    assert all("Bos" in line for line in lines), lines


def test_plain_words_without_the_language_files(monkeypatch):
    from core import i18n
    monkeypatch.setattr(i18n, "_language_cache", {})
    assert rem.fire_text("take medicine") == "Reminder: take medicine."
    assert rem.fire_text("x", late_minutes=60, due="08:00") == "Reminder: x."
    assert rem._say("rem_done_1", "x") == "Done: x."
    assert rem._say("rem_snoozed", "x", minutes=5) == "Snoozed for 5 minutes: x."
