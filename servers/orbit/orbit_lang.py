# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What the Orbit server says. Orbit is played in English (since 1.4): every
line is English, whatever language a client asks for when it joins (older
clients may still send "id"; it's ignored).

The lines are in texts.json, {"en": {key: text}}, with {placeholders} filled
in by str.format. The game still passes a language along (always "en"), so
the rest of the code needn't care.

A value given to render() may be an {"en": ...} dict (a place or a thing
from world.json): its English text is used. A list is joined as a sentence
would be: "Sam, Alex and Kim".
"""

import json
import os
import string

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LANGUAGE = "en"
LANGUAGES = (DEFAULT_LANGUAGE,)


def language(_code=None):
    """The language to speak to a client: English, whatever it asked for."""
    return DEFAULT_LANGUAGE


def pick(value, _lang=None):
    """The text of a value: an {"en": ...} dict gives its English text (a season file of
    the hunt may have other languages too, which are left alone); anything else is itself."""
    if isinstance(value, dict):
        if DEFAULT_LANGUAGE in value:
            return value[DEFAULT_LANGUAGE]
        return next(iter(value.values()), "")
    return value


def placeholders(text):
    return {name for _literal, name, _spec, _conv in string.Formatter().parse(text) if name}


class Texts:
    def __init__(self, path=None, data=None):
        if data is None:
            with open(path or os.path.join(HERE, "texts.json"), encoding="utf-8") as f:
                data = json.load(f)
        self.data = {DEFAULT_LANGUAGE: dict(data.get(DEFAULT_LANGUAGE) or {})}

    def has(self, key):
        return key in self.data[DEFAULT_LANGUAGE]

    def raw(self, _lang, key):
        return self.data[DEFAULT_LANGUAGE].get(key, key)

    def join(self, lang, items):
        """ "a, b and c"."""
        items = [str(pick(i)) for i in items if pick(i) not in (None, "")]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return self.raw(lang, "list_two").format(a=items[0], b=items[1])
        return self.raw(lang, "list_many").format(rest=", ".join(items[:-1]), last=items[-1])

    def render(self, lang, key, **params):
        values = {}
        for name, value in params.items():
            if isinstance(value, (list, tuple)):
                values[name] = self.join(lang, value)
            else:
                values[name] = pick(value)
        text = self.raw(lang, key)
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return text
