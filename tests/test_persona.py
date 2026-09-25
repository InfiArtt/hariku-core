# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""How Hariku talks (core.persona, core 2.10): the persona a nickname picks,
the setting, and the "key@persona" texts in the language files."""
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


@pytest.mark.parametrize("nickname, persona", [
    ("Princess", "royal"), ("princess rafli", "royal"), ("Tuan Putri", "royal"),
    ("yang mulia", "royal"), ("KING", "royal"),
    ("babyy", "sweet"), ("Baby", "sweet"), ("sayangg", "sweet"), ("bebeb", "sweet"),
    ("bro", "bro"), ("Brooo", "bro"), ("bang Rafli", "bro"), ("cuy", "bro"), ("boss", "bro"),
    ("Rafli", None), ("", None), ("Putri", None), ("Raja", None), ("Cinta", None),
    ("brownies", None), ("kingdom", None), ("yang", None),
])
def test_a_nickname_picks_a_persona(nickname, persona):
    import core.persona
    assert core.persona.detect(nickname) == persona


def test_the_setting_wins_over_the_nickname():
    import core.persona
    assert core.persona.resolve("auto", "Princess") == "royal"
    assert core.persona.resolve("auto", "Rafli") == core.persona.DEFAULT == "playful"
    assert core.persona.resolve("polite", "Princess") == "polite"
    assert core.persona.resolve("nonsense", "bro") == "bro"


def test_the_setting_is_saved_and_applied(tmp_data_dir, lang):
    import core.api
    import core.i18n
    import core.persona
    assert core.persona.get_setting() == "auto"
    core.api.save_data("Core", {"user_name": "Rafli Hidayat", "user_nickname": "Princess"})
    assert core.persona.apply() == "royal" and core.i18n.get_persona() == "royal"
    assert core.persona.save_setting("bro") == "bro"
    assert core.api.load_data("Core")["persona"] == "bro" and core.persona.get_setting() == "bro"
    core.api.save_data("Core", dict(core.api.load_data("Core"), persona="weird"))
    assert core.persona.get_setting() == "auto" and core.persona.apply() == "royal"


def test_a_persona_s_own_text_comes_first(lang):
    import core.i18n
    _ = core.i18n.get_translator("core")
    base = _("onb_name_reply", name="Rafli")
    core.i18n.set_persona("royal")
    assert _("onb_name_reply", name="Rafli") == (
        "Salam hormat, Rafli! Mulai hari ini, hamba pelayan setiamu.")
    # A text the persona has no version of stays as it is.
    assert _("onb_where_chosen") == "Kotamu:"
    lang("en")
    assert _("onb_name_reply", name="Rafli").startswith("Greetings, Rafli!")
    core.i18n.set_persona("playful")      # the default: the plain texts
    lang("id")
    assert _("onb_name_reply", name="Rafli") == base


def test_the_greeting_follows_the_persona(lang):
    import core.i18n
    import core.personal
    _ = core.i18n.get_translator("core")
    core.i18n.set_persona("sweet")
    assert _("greet_morning_name", name="Rafli") == "Pagiii, Rafli"
    core.i18n.set_persona("bro")
    assert _("greet_evening_name", name="Rafli") == "Malam, Rafli"


@pytest.mark.parametrize("code", ["en", "id"])
def test_every_persona_text_belongs_to_a_known_persona_and_key(code):
    import core.persona
    messages = _messages(code)
    fields = lambda text: sorted(re.findall(r"\{(\w+)\}", text))
    variants = [k for k in messages if "@" in k]
    assert variants, "no persona texts"
    for key in variants:
        base, persona = key.split("@", 1)
        assert persona in core.persona.PERSONAS, key
        assert persona != core.persona.DEFAULT, f"{key}: the default persona uses the plain text"
        assert base in messages, key
        assert fields(messages[key]) == fields(messages[base]), key
        assert messages[key].strip() and "  " not in messages[key], key


def test_both_languages_have_the_same_persona_texts():
    english = {k for k in _messages("en") if "@" in k}
    indonesian = {k for k in _messages("id") if "@" in k}
    assert english == indonesian


def test_every_persona_has_a_name_in_both_languages():
    import core.persona
    for code in ("en", "id"):
        messages = _messages(code)
        for setting in (core.persona.AUTO,) + core.persona.PERSONAS:
            assert messages.get(f"persona_{setting}"), (code, setting)


@pytest.mark.parametrize("persona", ["sweet", "bro", "royal", "polite"])
@pytest.mark.parametrize("code", ["en", "id"])
def test_every_persona_s_welcome_reads_well_without_a_name(lang, code, persona):
    import core.i18n
    import core.onboarding as onb
    lang(code)
    core.i18n.set_persona(persona)
    for page in ("where", "birthday", "aruna", "extensions", "startup"):
        text = onb.question(page, "", "")
        assert text and "{" not in text and "  " not in text, text
        assert not re.search(r"[,;:]\s*[?!.]|\s[,.?!]|^[\s,.]", text), text
        assert "Rafli" in onb.question(page, "Rafli", ""), (page, persona)
    reply = onb.name_reply("")
    assert reply and not re.search(r"[,;:]\s*[?!.]|\s[,.?!]|^[\s,.]", reply), reply
    done = onb.personal(core.i18n.get_translator("core")("onb_done_ready", name=""))
    assert done and not re.search(r"[,;:]\s*[?!.]|\s[,.?!]|^[\s,.]", done), done


def test_the_welcome_talks_in_the_persona_chosen_then_cancel_restores_it(tmp_data_dir, lang):
    import core.api
    import core.i18n
    import core.onboarding as onb
    core.api.save_data("Core", {"user_name": "Rafli Hidayat", "language": "id"})
    assert onb.prefill().persona == "auto"
    assert onb.use_persona("auto", "Rafli Hidayat", "Princess") == "royal"
    assert onb.name_reply("Princess").startswith("Salam hormat, Princess!")
    assert onb.use_persona("sweet", "Rafli Hidayat", "Princess") == "sweet"
    onb.cancel(first_run=False)
    assert core.i18n.get_persona() == "playful"
    assert "persona" not in core.api.load_data("Core")


def test_finishing_saves_the_persona(tmp_data_dir, lang):
    import core.api
    import core.i18n
    import core.onboarding as onb
    core.api.save_data("Core", {"user_name": "Rafli Hidayat", "language": "id"})
    answers = onb.prefill()
    answers.nickname = "bro"
    done = onb.save(answers)
    assert "persona" not in done and core.i18n.get_persona() == "bro"   # "auto" follows "bro"
    answers.persona = "royal"
    assert onb.save(answers)["persona"] == "royal"
    assert core.api.load_data("Core")["persona"] == "royal"
    assert core.i18n.get_persona() == "royal"
