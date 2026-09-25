# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Keeping Orbit friendly: character names, the word filter, tidy text, and rate
limits (token buckets). No I/O.

The word filter compares whole words after folding look-alike characters
("4nj1ng" is "anjing") and letters repeated for emphasis ("fuuuck"). A name
with a filtered word in it is refused; a sentence gets the word masked with
asterisks.
"""

import json
import re
import time
import unicodedata

NAME_MIN, NAME_MAX = 3, 20
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{%d,%d}$" % (NAME_MIN - 1, NAME_MAX - 1))

# Folded before comparing with the filter's words.
_LOOKALIKES = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
                             "@": "a", "$": "s", "!": "i", "|": "i", "8": "b"})
# A word may hide a letter behind ! or | inside it ("sh!t"), not at its end ("wow!").
_WORD_RE = re.compile(r"[\w@$]+(?:[!|]+[\w@$]+)*", re.UNICODE)
_REPEATS_RE = re.compile(r"(.)\1+")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")


def fold(word):
    """A word as the filter compares it: lower case, no accents, look-alikes
    folded, a letter repeated counting once."""
    text = unicodedata.normalize("NFKD", str(word)).casefold()
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.translate(_LOOKALIKES)
    return _REPEATS_RE.sub(r"\1", text)


def load_words(path):
    """The filter's words from a JSON file: {"en": [...], "id": [...], ...}
    or a plain list."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    words = []
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                words.extend(str(w) for w in value)
    elif isinstance(data, list):
        words.extend(str(w) for w in data)
    return words


class WordFilter:
    def __init__(self, words=()):
        self.words = {fold(w) for w in words if str(w).strip()}

    def _bad(self, token):
        return fold(token) in self.words

    def contains(self, text):
        return any(self._bad(m.group()) for m in _WORD_RE.finditer(str(text or "")))

    def clean(self, text):
        """`text` with every filtered word replaced by asterisks."""
        return _WORD_RE.sub(lambda m: "*" * len(m.group()) if self._bad(m.group()) else m.group(),
                            str(text or ""))


def tidy(text, limit):
    """One line of at most `limit` characters: control and direction-changing
    characters removed, spaces collapsed."""
    text = _CONTROL_RE.sub(" ", unicodedata.normalize("NFC", str(text or "")))
    text = " ".join(text.split())
    return text[:limit].rstrip()


def name_key(name):
    """What makes two names the same name."""
    return str(name or "").strip().casefold()


def check_name(name, word_filter=None, reserved=()):
    """(the name as it will be used, None) or (None, why): "length",
    "characters", "filtered" or "reserved". A name is 3 to 20 letters and
    digits, starting with a letter; its first letter is made a capital."""
    name = str(name or "").strip()
    if not NAME_MIN <= len(name) <= NAME_MAX:
        return None, "length"
    if not NAME_RE.match(name):
        return None, "characters"
    if word_filter is not None and (word_filter.contains(name) or any(
            bad and bad in fold(name) for bad in word_filter.words if len(bad) >= 4)):
        return None, "filtered"
    if name_key(name) in {name_key(r) for r in reserved}:
        return None, "reserved"
    return name[0].upper() + name[1:], None


class TokenBucket:
    """`rate` tokens a second, at most `burst` saved up. take() spends one
    and says whether there was one."""

    def __init__(self, rate, burst, clock=time.monotonic):
        self.rate = float(rate)
        self.burst = float(burst)
        self.clock = clock
        self.tokens = float(burst)
        self.stamp = clock()

    def take(self, cost=1.0):
        now = self.clock()
        self.tokens = min(self.burst, self.tokens + (now - self.stamp) * self.rate)
        self.stamp = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def wait_seconds(self, cost=1.0):
        """How long until take(cost) would work."""
        now = self.clock()
        tokens = min(self.burst, self.tokens + (now - self.stamp) * self.rate)
        return 0.0 if tokens >= cost else (cost - tokens) / self.rate
