# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The user's profile (Preferences, Profile): their name, what Hariku should call
them, and their own placeholders, plus filling in %token% placeholders in text.

Everything lives in Core.json, unencrypted: "user_name" (also written by the
first-run wizard and read by Lumina), "user_nickname" and "user_fields", a list
of {"key": ..., "value": ...} in the user's order.
"""
import os
import re

import core.api
from core.i18n import get_translator

_ = get_translator("core")

DATA_KEY = "Core"
# What the first-run wizard saved for a blank name before 2.7.
LEGACY_BLANK_NAME = "User"
MAX_KEY_LENGTH = 32
MAX_VALUE_LENGTH = 500
# Tokens Hariku itself uses (the profile and Routines); custom keys can't take them.
RESERVED_KEYS = frozenset({
    "myname", "mynickname", "time", "date", "battery", "app", "clipboard",
    "ssid", "ram", "cpu", "events", "var",
})

_KEY_RE = re.compile(r"[a-z0-9_]{1,%d}\Z" % MAX_KEY_LENGTH)
# %key% or %namespace:rest% (Routines passes %var:NAME% through `extra`).
_TOKEN_RE = re.compile(r"%([A-Za-z0-9_]{1,32}(?::[^%\r\n]{1,64})?)%")


class ProfileError(ValueError):
    """A profile value that can't be saved. `code` says why, `field` which input
    ("name", "nickname", "key" or "value") and `index` which custom field, if any.
    str(error) is a message for the user, in their language."""

    def __init__(self, code, field=None, **details):
        self.code = code
        self.field = field
        self.index = None
        self.details = details
        super().__init__(_("profile_err_" + code, **details))


# ------------------------------------------------------------
# Reading
# ------------------------------------------------------------

def _config():
    data = core.api.load_data(DATA_KEY)
    return data if isinstance(data, dict) else {}


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _name_from(config):
    name = _text(config.get("user_name"))
    return "" if name == LEGACY_BLANK_NAME else name


def _fields_from(config):
    """The stored custom fields, skipping anything a hand edit may have broken."""
    fields, seen = [], set()
    raw = config.get("user_fields")
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            key, value = item.get("key"), item.get("value")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            key, value = item
        else:
            continue
        key = _text(key).lower()
        if not _KEY_RE.match(key) or key in RESERVED_KEYS or key in seen:
            continue
        seen.add(key)
        fields.append((key, value if isinstance(value, str) else ("" if value is None else str(value))))
    return fields


def get_name():
    """The user's name, or "" when they haven't given one."""
    return _name_from(_config())


def get_nickname():
    """What Hariku should call the user: their nickname, else their name, else ""."""
    config = _config()
    return _text(config.get("user_nickname")) or _name_from(config)


def get_fields():
    """The user's own placeholders as an ordered list of (key, value)."""
    return _fields_from(_config())


def get_profile():
    """Everything the Profile page shows, from a single read: {"name",
    "nickname" (as typed, without the fallback to the name), "fields"}."""
    config = _config()
    return {"name": _name_from(config),
            "nickname": _text(config.get("user_nickname")),
            "fields": _fields_from(config)}


# ------------------------------------------------------------
# Validation and saving
# ------------------------------------------------------------

def normalize_key(key):
    """A key as stored: trimmed, lower-case, without surrounding % signs."""
    return _text(key).strip("%").strip().lower()


def check_key(key, taken=()):
    """The key as stored, or ProfileError. `taken` are keys already in use."""
    key = normalize_key(key)
    if not key:
        raise ProfileError("key_empty", "key")
    if len(key) > MAX_KEY_LENGTH:
        raise ProfileError("key_too_long", "key", max=MAX_KEY_LENGTH)
    if not _KEY_RE.match(key):
        raise ProfileError("key_chars", "key")
    if key in RESERVED_KEYS:
        raise ProfileError("key_reserved", "key", token=key)
    # Windows variables such as %TEMP% or %USERPROFILE% are filled in by Routines'
    # open actions; a profile key with the same name would shadow them.
    if key in {name.lower() for name in os.environ if not name.startswith("_")}:
        raise ProfileError("key_windows", "key", token=key)
    if key in {normalize_key(t) for t in taken}:
        raise ProfileError("key_duplicate", "key", token=key)
    return key


def check_value(value, field="value"):
    """The value as stored (trimmed), or ProfileError when it is too long."""
    value = "" if value is None else str(value).strip()
    if len(value) > MAX_VALUE_LENGTH:
        raise ProfileError(f"{field}_too_long", field, max=MAX_VALUE_LENGTH)
    return value


def set_profile(name, nickname="", fields=()):
    """Check and save the profile. `fields` is an iterable of (key, value) in the
    order to keep. Raises ProfileError, saving nothing, if anything is invalid;
    otherwise returns whether the save worked."""
    name = check_value(name, "name")
    nickname = check_value(nickname, "nickname")
    clean, taken = [], []
    for index, (key, value) in enumerate(fields or ()):
        try:
            key = check_key(key, taken)
            value = check_value(value)
        except ProfileError as e:
            e.index = index
            raise
        taken.append(key)
        clean.append({"key": key, "value": value})
    config = _config()
    config["user_name"] = name
    config["user_nickname"] = nickname
    config["user_fields"] = clean
    return core.api.save_data(DATA_KEY, config)


# ------------------------------------------------------------
# Placeholders
# ------------------------------------------------------------

def _profile_tokens(config):
    tokens = {key: value for key, value in _fields_from(config)}
    tokens["myname"] = _name_from(config)
    tokens["mynickname"] = _text(config.get("user_nickname")) or tokens["myname"]
    return tokens


def _resolver(extra):
    exact, folded = {}, {}
    for key, value in (extra or {}).items():
        if isinstance(key, str):
            value = "" if value is None else str(value)
            exact[key] = value
            folded.setdefault(key.lower(), value)
    profile = None

    def resolve(token):
        nonlocal profile
        if token in exact:
            return exact[token]
        lower = token.lower()
        if lower in folded:
            return folded[lower]
        if profile is None:
            profile = _profile_tokens(_config())   # read only when needed
        return profile.get(lower)

    return resolve


def expand(text, extra=None):
    """Fill in %token% placeholders in `text`, case-insensitively, in a single
    pass: inserted values are never expanded again. `extra` maps more tokens to
    values and is looked up before the profile (%myname%, %mynickname% and the
    user's own keys). Unknown tokens and lone % signs are left as they are."""
    if not isinstance(text, str) or "%" not in text:
        return text
    resolve = _resolver(extra)
    out, done = [], 0
    start = text.find("%")
    while start != -1:
        match = _TOKEN_RE.match(text, start)
        value = resolve(match.group(1)) if match else None
        if value is None:
            # Not a token here; its closing % may still open the next one.
            start = text.find("%", start + 1)
            continue
        out.append(text[done:start])
        out.append(value)
        done = match.end()
        start = text.find("%", done)
    out.append(text[done:])
    return "".join(out)
