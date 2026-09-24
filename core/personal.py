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
them, their birthday and their own placeholders, plus filling in %token%
placeholders in text, the time-of-day greeting, and quiet hours.

Everything lives in Core.json, unencrypted: "user_name" (also written by the
first-run wizard and read by Lumina), "user_nickname", "user_birthday"
({"day", "month", "year" or null}), "user_fields" (a list of {"key", "value"}
in the user's order), "greet_on_startup" and "quiet_hours" ({"enabled",
"start", "end"}).
"""
import datetime
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
    "myname", "mynickname", "mybirthday", "myage", "time", "date", "battery",
    "app", "clipboard", "ssid", "ram", "cpu", "events", "var",
})
MIN_BIRTH_YEAR = 1900
DEFAULT_QUIET_HOURS = {"enabled": False, "start": "22:00", "end": "05:00"}
# The startup greeting waits for the screen reader to announce the main window.
STARTUP_GREETING_DELAY_MS = 1500
_KEEP = object()

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


def get_birthday():
    """The user's birthday as (day, month, year or None), or None."""
    return _birthday_from(_config())


def get_profile():
    """Everything the Profile page shows, from a single read: {"name",
    "nickname" (as typed, without the fallback to the name), "birthday",
    "fields", "greet_on_startup"}."""
    config = _config()
    return {"name": _name_from(config),
            "nickname": _text(config.get("user_nickname")),
            "birthday": _birthday_from(config),
            "fields": _fields_from(config),
            "greet_on_startup": _greet_from(config)}


# ------------------------------------------------------------
# Birthday
# ------------------------------------------------------------

def _year_or_none(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        raise ProfileError("birthday_year", "birthday_year", min=MIN_BIRTH_YEAR,
                           max=datetime.date.today().year) from None


def check_birthday(day, month, year=None):
    """(day, month, year or None) as stored, None when no birthday is given, or
    ProfileError. Day and month go together; the year is optional."""
    day = None if day in (None, "", 0) else day
    month = None if month in (None, "", 0) else month
    if day is None and month is None:
        return None
    if day is None or month is None:
        raise ProfileError("birthday_incomplete",
                           "birthday_day" if day is None else "birthday_month")
    try:
        day, month = int(day), int(month)
        datetime.date(2000, month, day)   # a leap year, so 29 February is fine
    except (TypeError, ValueError):
        raise ProfileError("birthday_invalid", "birthday_day") from None
    year = _year_or_none(year)
    if year is not None:
        this_year = datetime.date.today().year
        if not MIN_BIRTH_YEAR <= year <= this_year:
            raise ProfileError("birthday_year", "birthday_year", min=MIN_BIRTH_YEAR,
                               max=this_year)
        try:
            datetime.date(year, month, day)
        except ValueError:
            raise ProfileError("birthday_invalid", "birthday_day") from None
    return day, month, year


def _birthday_from(config):
    raw = config.get("user_birthday")
    if not isinstance(raw, dict):
        return None
    try:
        return check_birthday(raw.get("day"), raw.get("month"), raw.get("year"))
    except ProfileError:
        return None


def set_birthday(day, month, year=None):
    """Check and save the birthday; day and month None removes it. Raises
    ProfileError, saving nothing, when it is invalid."""
    birthday = check_birthday(day, month, year)
    config = _config()
    _store_birthday(config, birthday)
    return core.api.save_data(DATA_KEY, config)


def _store_birthday(config, birthday):
    if birthday is None:
        config.pop("user_birthday", None)
    else:
        config["user_birthday"] = {"day": birthday[0], "month": birthday[1],
                                   "year": birthday[2]}


def _in_year(birthday, year):
    """The birthday's date in `year`; 29 February falls on the 28th otherwise."""
    try:
        return datetime.date(year, birthday[1], birthday[0])
    except ValueError:
        return datetime.date(year, birthday[1], 28)


def _as_date(today):
    if today is None:
        return datetime.date.today()
    return today.date() if isinstance(today, datetime.datetime) else today


def is_birthday(today=None, birthday=_KEEP):
    """True on the user's birthday (`today` defaults to the real date)."""
    birthday = get_birthday() if birthday is _KEEP else birthday
    if not birthday:
        return False
    today = _as_date(today)
    return today == _in_year(birthday, today.year)


def get_age(today=None, birthday=_KEEP):
    """The user's age in whole years, or None without a birth year."""
    birthday = get_birthday() if birthday is _KEEP else birthday
    if not birthday or not birthday[2]:
        return None
    today = _as_date(today)
    return max(0, today.year - birthday[2] - (today < _in_year(birthday, today.year)))


def birthday_text(birthday=_KEEP):
    """The birthday in the user's language, e.g. "24 September" or
    "24 September 1999"; "" without one."""
    birthday = get_birthday() if birthday is _KEEP else birthday
    if not birthday:
        return ""
    day, month, year = birthday
    text = f"{day} {_('month_%d' % month)}"
    return f"{text} {year}" if year else text


# ------------------------------------------------------------
# Greeting
# ------------------------------------------------------------

def greeting_key(hour):
    """Locale key for a greeting at `hour` (0-23): pagi, siang, sore, malam."""
    if 4 <= hour < 11:
        return "greet_morning"
    if 11 <= hour < 15:
        return "greet_midday"
    if 15 <= hour < 18:
        return "greet_afternoon"
    return "greet_evening"


def _end_sentence(text):
    text = text.strip()
    return text if not text or text[-1:] in (".", "!", "?") else text + "."


def greeting(now=None, nickname=None):
    """"Good morning, Bro." for the time of day, or "Good morning." without a
    name; on the user's birthday "Happy birthday!" follows."""
    now = now or datetime.datetime.now()
    config = _config()
    if nickname is None:
        nickname = _text(config.get("user_nickname")) or _name_from(config)
    nickname = " ".join(str(nickname or "").split())
    key = greeting_key(now.hour)
    text = _end_sentence(_(key + "_name", name=nickname)) if nickname else _(key)
    if is_birthday(now, _birthday_from(config)):
        text += " " + _("greet_birthday")
    return text


def _greet_from(config):
    return bool(config.get("greet_on_startup", True))


def startup_greeting_enabled():
    """Whether Hariku greets the user when it starts (on unless turned off)."""
    return _greet_from(_config())


def set_startup_greeting(enabled):
    config = _config()
    config["greet_on_startup"] = bool(enabled)
    return core.api.save_data(DATA_KEY, config)


def startup_speech(welcome="", now=None):
    """What Hariku says once its window is ready: the greeting, then `welcome`,
    as one announcement."""
    parts = [greeting(now), _end_sentence(welcome or "")]
    return " ".join(p for p in parts if p)


def speak_startup_greeting(welcome=""):
    # Hariku Voice speaks it when the user chose a voice for the greeting;
    # otherwise the screen reader does, as before.
    import core.voice
    core.voice.announce(startup_speech(welcome), "greeting", interrupt=False)


# ------------------------------------------------------------
# Quiet hours
# ------------------------------------------------------------

_TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)\Z")


def parse_time(text):
    """Minutes after midnight for "HH:MM", or None."""
    match = _TIME_RE.match(_text(text))
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def _clock(text):
    minutes = parse_time(text)
    return None if minutes is None else "%02d:%02d" % divmod(minutes, 60)


def get_quiet_hours():
    """{"enabled", "start", "end"}, with "HH:MM" times; off by default."""
    raw = _config().get("quiet_hours")
    raw = raw if isinstance(raw, dict) else {}
    return {"enabled": bool(raw.get("enabled", DEFAULT_QUIET_HOURS["enabled"])),
            "start": _clock(raw.get("start")) or DEFAULT_QUIET_HOURS["start"],
            "end": _clock(raw.get("end")) or DEFAULT_QUIET_HOURS["end"]}


def check_quiet_hours(enabled, start, end):
    """Quiet hours as stored, or ProfileError for a time that isn't HH:MM or,
    when enabled, the same start and end."""
    clean_start, clean_end = _clock(start), _clock(end)
    if clean_start is None:
        raise ProfileError("quiet_time", "quiet_start")
    if clean_end is None:
        raise ProfileError("quiet_time", "quiet_end")
    if enabled and clean_start == clean_end:
        raise ProfileError("quiet_same", "quiet_end")
    return {"enabled": bool(enabled), "start": clean_start, "end": clean_end}


def set_quiet_hours(enabled, start, end):
    """Check and save quiet hours; raises ProfileError, saving nothing."""
    quiet = check_quiet_hours(enabled, start, end)
    config = _config()
    config["quiet_hours"] = quiet
    return core.api.save_data(DATA_KEY, config)


def is_quiet_time(now=None):
    """True during the user's quiet hours, when extensions keep their alerts to
    themselves. Handles ranges past midnight (22:00-05:00): the start minute is
    quiet, the end minute is not."""
    quiet = get_quiet_hours()
    if not quiet["enabled"]:
        return False
    now = now or datetime.datetime.now()
    minute = now.hour * 60 + now.minute
    start, end = parse_time(quiet["start"]), parse_time(quiet["end"])
    if start == end:
        return False
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


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


def set_profile(name, nickname="", fields=(), birthday=_KEEP):
    """Check and save the profile. `fields` is an iterable of (key, value) in the
    order to keep; `birthday` is (day, month, year or None) or None, and stays
    as it is when not given. Raises ProfileError, saving nothing, if anything is
    invalid; otherwise returns whether the save worked."""
    name = check_value(name, "name")
    nickname = check_value(nickname, "nickname")
    if birthday is not _KEEP:
        birthday = check_birthday(*birthday) if birthday else None
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
    if birthday is not _KEEP:
        _store_birthday(config, birthday)
    return core.api.save_data(DATA_KEY, config)


# ------------------------------------------------------------
# Placeholders
# ------------------------------------------------------------

def _profile_tokens(config):
    tokens = {key: value for key, value in _fields_from(config)}
    tokens["myname"] = _name_from(config)
    tokens["mynickname"] = _text(config.get("user_nickname")) or tokens["myname"]
    birthday = _birthday_from(config)
    tokens["mybirthday"] = birthday_text(birthday)
    age = get_age(birthday=birthday)
    tokens["myage"] = "" if age is None else str(age)
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
    values and is looked up before the profile (%myname%, %mynickname%,
    %mybirthday%, %myage% and the user's own keys). Unknown tokens and lone %
    signs are left as they are."""
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
