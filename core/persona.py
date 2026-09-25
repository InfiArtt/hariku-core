# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
How Hariku talks (core 2.10): a persona.

  playful  a cheeky friend who teases a little (the default)
  sweet    cute and affectionate ("babyy", "sayang")
  bro      laid-back ("bro", "bang", "cuy")
  royal    a loyal servant of the court ("Princess", "Yang Mulia")
  polite   polite and a little formal

The setting is Core.json "persona": one of those, or "auto" (the default),
which picks the persona from what Hariku calls the user: a nickname with
"princess" in it gets the royal one, "bro" the laid-back one, "babyy" the
sweet one; any other nickname, the default.

A persona is only words: core.i18n looks a text up as "key@persona" first
(core.i18n.set_persona), so a language file gives a persona its own version
of any text, and every other text stays as it is. Extensions' language files
can do the same.
"""
import logging
import re

import core.api
import core.i18n
from core.i18n import get_translator

_ = get_translator("core")
logger = logging.getLogger(__name__)

DATA_KEY = "Core"
SETTING_KEY = "persona"
AUTO = "auto"
DEFAULT = "playful"
PERSONAS = ("playful", "sweet", "bro", "royal", "polite")

# Words in a nickname that pick a persona (with "auto"). Compared without
# case or repeated letters, so "Babyy", "brooo" and "PRINCESS" count. Words
# that are also common names (Putri, Raja, Ratu, Cinta) are left out: a Putri
# shouldn't be answered like royalty unless she asks for it.
TRIGGERS = {
    "royal": ("princess", "prince", "tuan putri", "pangeran", "queen", "king",
              "yang mulia", "highness", "majesty", "baginda", "paduka"),
    "sweet": ("baby", "babe", "beb", "bebeb", "sayang", "ayang", "honey", "sweetie",
              "cutie", "darling", "bunny"),
    "bro": ("bro", "bruh", "brother", "brader", "bang", "abang", "bos", "boss", "cuy",
            "gan", "agan", "dude", "mate", "bestie", "sis"),
}


def _squash(text):
    """Lower case, letters and spaces only, a letter repeated in a row once:
    "Babyy!" -> "baby", "Brooo" -> "bro"."""
    text = re.sub(r"[^a-z ]+", " ", str(text or "").casefold())
    text = re.sub(r"(.)\1+", r"\1", text)
    return " ".join(text.split())


_WORDS = {persona: tuple(_squash(word) for word in words)
          for persona, words in TRIGGERS.items()}


def detect(nickname):
    """The persona a nickname asks for, or None. Phrases first ("yang mulia"),
    then single words."""
    squashed = f" {_squash(nickname)} "
    if not squashed.strip():
        return None
    for persona, words in _WORDS.items():
        if any(" " in word and f" {word} " in squashed for word in words):
            return persona
    for persona, words in _WORDS.items():
        if any(f" {word} " in squashed for word in words):
            return persona
    return None


def resolve(setting, nickname=""):
    """The persona to talk in: the chosen one, or with "auto" (or anything
    unknown) the one the nickname asks for, else the default."""
    if setting in PERSONAS:
        return setting
    return detect(nickname) or DEFAULT


def get_setting():
    """The saved setting: "auto" or one of PERSONAS."""
    config = core.api.load_data(DATA_KEY)
    value = config.get(SETTING_KEY) if isinstance(config, dict) else None
    return value if value in PERSONAS else AUTO


def save_setting(value):
    """Save the setting ("auto" or one of PERSONAS) and talk in it at once."""
    value = value if value in PERSONAS else AUTO
    config = core.api.load_data(DATA_KEY)
    config = config if isinstance(config, dict) else {}
    if config.get(SETTING_KEY, AUTO) != value:
        config[SETTING_KEY] = value
        core.api.save_data(DATA_KEY, config)
    return apply()


def current_nickname():
    """What Hariku calls the user now: the nickname, else the first word of the name."""
    import core.personal
    profile = core.personal.get_profile()
    return profile["nickname"] or (profile["name"].split() or [""])[0]


def apply(setting=None, nickname=None):
    """Talk in the persona `setting` and `nickname` give (by default the saved
    ones) from now on; returns it."""
    try:
        setting = get_setting() if setting is None else setting
        nickname = current_nickname() if nickname is None else nickname
    except Exception as e:
        logger.warning(f"Persona: the settings couldn't be read: {e}")
        setting, nickname = AUTO, ""
    persona = resolve(setting, nickname)
    core.i18n.set_persona(persona)
    return persona


def choices():
    """[(setting, label)] for a list: "auto" first, then every persona."""
    return [(AUTO, _("persona_auto"))] + [(p, _(f"persona_{p}")) for p in PERSONAS]
