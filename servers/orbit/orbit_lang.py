# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What the Orbit server says, in each player's language.

The server renders every line itself, in the language the client asked for
when it joined ("id" or "en"; anything else gets English), so everyone in a
room reads the same event in their own language. The lines are in
texts.json: {"en": {key: text}, "id": {key: text}}, with {placeholders}
filled in by str.format.

A value given to render() may itself be in several languages: a dict such as
{"en": "Cantina", "id": "Kantin"} (a place or an item from world.json) is
put in the reader's language. A list is joined as a sentence would be:
"Sari, Budi and Tono" / "Sari, Budi, dan Tono".
"""

import json
import os
import string

HERE = os.path.dirname(os.path.abspath(__file__))
LANGUAGES = ("en", "id")
DEFAULT_LANGUAGE = "en"


def language(code):
    """ "id" or "en" for whatever a client sent."""
    code = str(code or "").split("-")[0].split("_")[0].strip().lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def pick(value, lang):
    """A value in `lang`: a {"en":..., "id":...} dict gives its `lang` text (or
    the English one); anything else is itself."""
    if isinstance(value, dict):
        if lang in value:
            return value[lang]
        return value.get(DEFAULT_LANGUAGE, next(iter(value.values()), ""))
    return value


def placeholders(text):
    return {name for _literal, name, _spec, _conv in string.Formatter().parse(text) if name}


class Texts:
    def __init__(self, path=None, data=None):
        if data is None:
            with open(path or os.path.join(HERE, "texts.json"), encoding="utf-8") as f:
                data = json.load(f)
        self.data = {lang: dict(data.get(lang) or {}) for lang in LANGUAGES}

    def has(self, key):
        return key in self.data[DEFAULT_LANGUAGE]

    def raw(self, lang, key):
        table = self.data.get(language(lang), {})
        if key in table:
            return table[key]
        return self.data[DEFAULT_LANGUAGE].get(key, key)

    def join(self, lang, items):
        """ "a, b and c" / "a, b, dan c"."""
        items = [str(pick(i, lang)) for i in items if pick(i, lang) not in (None, "")]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return self.raw(lang, "list_two").format(a=items[0], b=items[1])
        return self.raw(lang, "list_many").format(rest=", ".join(items[:-1]), last=items[-1])

    def render(self, lang, key, **params):
        lang = language(lang)
        values = {}
        for name, value in params.items():
            if isinstance(value, (list, tuple)):
                values[name] = self.join(lang, value)
            else:
                values[name] = pick(value, lang)
        text = self.raw(lang, key)
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return text
