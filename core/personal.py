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
them and the title before it, their birthday and their own placeholders, plus
filling in %token% placeholders in text (the profile's, Hariku's dynamic ones
such as %time% and %reminders%, and those extensions register), the
time-of-day greeting or the user's own startup greeting, and quiet hours.

Everything lives in Core.json, unencrypted: "user_name" (also written by the
first-run wizard and read by Lumina), "user_nickname", "user_title",
"user_birthday" ({"day", "month", "year" or null}), "user_fields" (a list of
{"key", "value"} in the user's order), "greet_on_startup", "custom_greeting"
(the user's own words, raw), "custom_greeting_boot_only" and "quiet_hours"
({"enabled", "start", "end"}).
"""
import datetime
import logging
import os
import re
import time

import core.api
from core.i18n import format_date, get_translator

_ = get_translator("core")
logger = logging.getLogger(__name__)

DATA_KEY = "Core"
# What the first-run wizard saved for a blank name before 2.7.
LEGACY_BLANK_NAME = "User"
MAX_KEY_LENGTH = 32
MAX_VALUE_LENGTH = 500
# The profile's own tokens.
PROFILE_KEYS = ("myname", "mynickname", "mytitle", "mybirthday", "myage")
# Hariku's dynamic placeholders, filled in when the text is used (see below).
DYNAMIC_KEYS = ("greeting", "time", "day", "date", "zulu", "reminders", "version")
# Tokens Hariku itself uses (the profile, the dynamic ones and Routines); custom
# keys can't take them. Placeholders extensions register are refused too.
RESERVED_KEYS = frozenset(PROFILE_KEYS + DYNAMIC_KEYS + (
    "battery", "app", "clipboard", "ssid", "ram", "cpu", "events", "var",
))
MIN_BIRTH_YEAR = 1900
DEFAULT_QUIET_HOURS = {"enabled": False, "start": "22:00", "end": "05:00"}
# The startup greeting waits for the screen reader to announce the main window.
STARTUP_GREETING_DELAY_MS = 1500
# When Windows started Hariku: wait for the network, then a little more so
# extensions can refresh what %weather% and the like read, but never too long.
BOOT_GREETING_MAX_WAIT = 25.0     # seconds after the greeting was scheduled
BOOT_GREETING_SETTLE = 3.0        # seconds after the network was first seen up
BOOT_GREETING_POLL = 1.0          # how often the network is checked
MAX_PLACEHOLDER_VALUE = 300       # characters a registered placeholder may insert
_KEEP = object()

_KEY_RE = re.compile(r"[a-z0-9_]{1,%d}\Z" % MAX_KEY_LENGTH)
# %key% or %namespace:rest% (Routines passes %var:NAME% through `extra`).
_TOKEN_RE = re.compile(r"%([A-Za-z0-9_]{1,32}(?::[^%\r\n]{1,64})?)%")


class ProfileError(ValueError):
    """A profile value that can't be saved. `code` says why, `field` which input
    ("name", "nickname", "title", "greeting", "key" or "value") and `index` which
    custom field, if any. str(error) is a message for the user, in their language."""

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


def _one_line(value):
    return " ".join(str(value or "").split())


def _name_from(config):
    name = _text(config.get("user_name"))
    return "" if name == LEGACY_BLANK_NAME else name


def _nickname_from(config):
    return _text(config.get("user_nickname")) or _name_from(config)


def _title_from(config):
    return _one_line(config.get("user_title") if isinstance(config.get("user_title"), str) else "")


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
    return _nickname_from(_config())


def get_title():
    """The title the user wants before their name ("Kapten", "Pak"), or ""."""
    return _title_from(_config())


def _addressed(title, nickname):
    return " ".join(p for p in (_one_line(title), _one_line(nickname)) if p)


def get_addressed_name():
    """How Hariku addresses the user: the title and the nickname, "Kapten Bro";
    either one alone, or "" with neither."""
    config = _config()
    return _addressed(_title_from(config), _nickname_from(config))


def get_fields():
    """The user's own placeholders as an ordered list of (key, value)."""
    return _fields_from(_config())


def get_birthday():
    """The user's birthday as (day, month, year or None), or None."""
    return _birthday_from(_config())


def _custom_greeting_from(config):
    return {"text": _text(config.get("custom_greeting")),
            "boot_only": config.get("custom_greeting_boot_only") is True}


def get_custom_greeting():
    """{"text", "boot_only"}: what the user wants Hariku to say when it starts
    (raw, with its %placeholders%; "" means the standard greeting), and whether
    only when Windows started Hariku."""
    return _custom_greeting_from(_config())


def get_profile():
    """Everything the Profile page shows, from a single read: {"name",
    "nickname" (as typed, without the fallback to the name), "title",
    "birthday", "fields", "greet_on_startup", "custom_greeting",
    "custom_greeting_boot_only"}."""
    config = _config()
    custom = _custom_greeting_from(config)
    return {"name": _name_from(config),
            "nickname": _text(config.get("user_nickname")),
            "title": _title_from(config),
            "birthday": _birthday_from(config),
            "fields": _fields_from(config),
            "greet_on_startup": _greet_from(config),
            "custom_greeting": custom["text"],
            "custom_greeting_boot_only": custom["boot_only"]}


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


def greeting(now=None, nickname=None, title=None):
    """"Good morning, Kapten Bro." for the time of day, with the user's title
    and nickname (either may be missing), or "Good morning." without them; on
    the user's birthday "Happy birthday!" follows."""
    now = now or datetime.datetime.now()
    config = _config()
    if nickname is None:
        nickname = _nickname_from(config)
    if title is None:
        title = _title_from(config)
    name = _addressed(title, nickname)
    key = greeting_key(now.hour)
    text = _end_sentence(_(key + "_name", name=name)) if name else _(key)
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


def set_custom_greeting(text, boot_only=False):
    """Save the user's own startup greeting (raw; "" goes back to the standard
    greeting). Raises ProfileError, saving nothing, when it is too long."""
    text = check_value(text, "greeting")
    config = _config()
    config["custom_greeting"] = text
    config["custom_greeting_boot_only"] = bool(boot_only)
    return core.api.save_data(DATA_KEY, config)


def set_title(title):
    """Save the title before the user's name ("" removes it). Raises
    ProfileError, saving nothing, when it is too long."""
    title = _one_line(check_value(title, "title"))
    config = _config()
    config["user_title"] = title
    return core.api.save_data(DATA_KEY, config)


def startup_speech(welcome="", now=None, boot=False):
    """What Hariku says once its window is ready. The user's own greeting when
    they wrote one (and it isn't only for starts with Windows while this start
    wasn't one), with its placeholders filled in; otherwise the greeting, then
    `welcome`, as one announcement. "Happy birthday!" is added on the day."""
    now = now or datetime.datetime.now()
    config = _config()
    custom = _custom_greeting_from(config)
    if custom["text"] and (boot or not custom["boot_only"]):
        text = tidy_spoken(expand(custom["text"], now=now, unknown=""))
        if text:
            if is_birthday(now, _birthday_from(config)):
                text = _end_sentence(text) + " " + _("greet_birthday")
            return text
    parts = [greeting(now), _end_sentence(welcome or "")]
    return " ".join(p for p in parts if p)


def speak_startup_greeting(welcome="", boot=False):
    # Hariku Voice speaks it when the user chose a voice for the greeting;
    # otherwise the screen reader does, as before.
    import core.voice
    core.voice.announce(startup_speech(welcome, boot=boot), "greeting", interrupt=False)


def boot_greeting_wait(elapsed, online_at):
    """Seconds to wait before looking again, or 0 to greet now, for a start
    with Windows. `elapsed` is the time since the greeting was scheduled,
    `online_at` when the network was first seen up (None: not yet). Greets
    BOOT_GREETING_SETTLE seconds after the network came up, and at
    BOOT_GREETING_MAX_WAIT at the latest."""
    left = BOOT_GREETING_MAX_WAIT - elapsed
    if left <= 0:
        return 0.0
    if online_at is not None:
        return max(0.0, min(online_at + BOOT_GREETING_SETTLE - elapsed, left))
    return min(BOOT_GREETING_POLL, left)


def schedule_startup_greeting(welcome="", boot=False, call_later=None, is_online=None,
                              clock=None):
    """Say the startup greeting on timers, never holding up the UI. A manual
    start greets STARTUP_GREETING_DELAY_MS after the window appears; a start
    with Windows then also waits for the network (see boot_greeting_wait()).
    `call_later(ms, fn)`, `is_online()` and `clock()` are replaced in tests."""
    if call_later is None:
        import wx
        call_later = wx.CallLater
    if not boot:
        return call_later(STARTUP_GREETING_DELAY_MS, speak_startup_greeting, welcome)
    is_online = is_online or core.api.is_network_online
    clock = clock or time.monotonic
    start = clock()
    state = {"online_at": None}

    def check():
        elapsed = clock() - start
        if state["online_at"] is None:
            try:
                up = bool(is_online())
            except Exception:
                up = True   # can't tell: don't wait for nothing
            if up:
                state["online_at"] = elapsed
        wait = boot_greeting_wait(elapsed, state["online_at"])
        if wait <= 0:
            speak_startup_greeting(welcome, boot=True)
        else:
            call_later(max(1, int(wait * 1000)), check)

    return call_later(STARTUP_GREETING_DELAY_MS, check)


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


def check_key(key, taken=(), registered=True):
    """The key as stored, or ProfileError. `taken` are keys already in use.
    `registered=False` lets a key through that an extension registered as a
    placeholder after the user had already saved it (see set_profile())."""
    key = normalize_key(key)
    if not key:
        raise ProfileError("key_empty", "key")
    if len(key) > MAX_KEY_LENGTH:
        raise ProfileError("key_too_long", "key", max=MAX_KEY_LENGTH)
    if not _KEY_RE.match(key):
        raise ProfileError("key_chars", "key")
    if key in RESERVED_KEYS or (registered and key in _providers):
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


def set_profile(name, nickname="", fields=(), birthday=_KEEP, title=_KEEP):
    """Check and save the profile. `fields` is an iterable of (key, value) in the
    order to keep; `birthday` is (day, month, year or None) or None, and `title`
    a string; both stay as they are when not given. Raises ProfileError, saving
    nothing, if anything is invalid; otherwise returns whether the save worked.
    A saved key an extension has registered since stays (the extension's
    placeholder wins when text is filled in); new ones are checked by the
    Profile page's dialog."""
    name = check_value(name, "name")
    nickname = check_value(nickname, "nickname")
    if title is not _KEEP:
        title = _one_line(check_value(title, "title"))
    if birthday is not _KEEP:
        birthday = check_birthday(*birthday) if birthday else None
    clean, taken = [], []
    for index, (key, value) in enumerate(fields or ()):
        try:
            key = check_key(key, taken, registered=False)
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
    if title is not _KEEP:
        config["user_title"] = title
    if birthday is not _KEEP:
        _store_birthday(config, birthday)
    return core.api.save_data(DATA_KEY, config)


# ------------------------------------------------------------
# Dynamic placeholders: Hariku's own, and those extensions register
# ------------------------------------------------------------

_providers = {}   # name -> (provider, description), in registration order


def register_placeholder(name, provider, description=""):
    """Let %name% be filled in everywhere Hariku expands text (routines,
    reminders, the Briefing, the startup greeting). `provider()` returns a short
    string from data the extension already has: it runs on whichever thread is
    expanding text, so no network and no waiting. An exception or None becomes
    "". `description` (in the user's language) is shown in the Insert
    placeholder menus. Registering a name again replaces it. Returns the name
    as stored; raises ValueError for a name Hariku uses itself or that isn't
    1-32 of a-z, 0-9 and _."""
    key = normalize_key(name)
    if not _KEY_RE.match(key) or key in RESERVED_KEYS:
        raise ValueError(f"placeholder name not allowed: {name!r}")
    if not callable(provider):
        raise TypeError("provider must be callable")
    _providers.pop(key, None)
    _providers[key] = (provider, _one_line(description))
    return key


def unregister_placeholder(name):
    """Remove a placeholder registered with register_placeholder(). Returns
    whether there was one."""
    return _providers.pop(normalize_key(name), None) is not None


def is_placeholder_registered(name):
    return normalize_key(name) in _providers


def _clean_value(value):
    if value is None:
        return ""
    value = _one_line(value)
    return value[:MAX_PLACEHOLDER_VALUE]


def _registered_value(key):
    entry = _providers.get(key)
    if entry is None:
        return None
    try:
        return _clean_value(entry[0]())
    except Exception as e:
        logger.debug(f"Placeholder %{key}% failed: {e}")
        return ""


def reminders_today_text(count):
    """"no reminders today", "1 reminder today", "3 reminders today"."""
    if count <= 0:
        return _("token_reminders_none")
    if count == 1:
        return _("token_reminders_one")
    return _("token_reminders_many", count=count)


def reminders_today_count(day=None):
    """Today's reminders that aren't done yet, including those extensions add
    to the agenda. Reads the saved reminders only."""
    from core import reminders as _reminders   # core.reminders imports this module
    day = day or datetime.date.today()
    items = _reminders.get_reminders_for_date(day.isoformat())
    return sum(1 for r in items if isinstance(r, dict) and not r.get("is_done"))


def dynamic_value(key, now=None):
    """The current value of one of Hariku's dynamic placeholders (DYNAMIC_KEYS),
    or None for another key."""
    now = now or datetime.datetime.now()
    if key == "greeting":
        return _(greeting_key(now.hour)).rstrip(".!")
    if key == "time":
        return now.strftime("%H:%M")
    if key == "day":
        return format_date(now, "%A")
    if key == "date":
        return f"{now.day} {_('month_%d' % now.month)}"
    if key == "zulu":
        utc = now.astimezone(datetime.timezone.utc) if now.tzinfo else \
            datetime.datetime.fromtimestamp(now.timestamp(), datetime.timezone.utc)
        return utc.strftime("%H:%M")
    if key == "version":
        import core.constants
        return core.constants.CORE_VERSION
    if key == "reminders":
        try:
            return reminders_today_text(reminders_today_count(now.date()))
        except Exception as e:
            logger.debug(f"Placeholder %reminders% failed: {e}")
            return ""
    return None


def placeholder_description(key):
    """What a dynamic or registered placeholder is, for the menus; "" if unknown."""
    if key in DYNAMIC_KEYS:
        return _("token_desc_" + key)
    entry = _providers.get(key)
    return entry[1] if entry else ""


def get_placeholders(now=None, values=True):
    """[(key, description, value)] for Hariku's dynamic placeholders, then the
    ones extensions registered (in the order they registered). `value` is the
    current value ("" when `values` is False)."""
    rows = []
    for key in DYNAMIC_KEYS:
        rows.append((key, placeholder_description(key),
                     (dynamic_value(key, now) or "") if values else ""))
    for key, (provider, description) in list(_providers.items()):
        rows.append((key, description, (_registered_value(key) or "") if values else ""))
    return rows


# ------------------------------------------------------------
# Placeholders
# ------------------------------------------------------------

def _profile_tokens(config):
    tokens = {key: value for key, value in _fields_from(config)}
    tokens["myname"] = _name_from(config)
    tokens["mynickname"] = _nickname_from(config)
    tokens["mytitle"] = _title_from(config)
    birthday = _birthday_from(config)
    tokens["mybirthday"] = birthday_text(birthday)
    age = get_age(birthday=birthday)
    tokens["myage"] = "" if age is None else str(age)
    return tokens


def _resolver(extra, now):
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
        if lower in DYNAMIC_KEYS:
            return dynamic_value(lower, now)
        if lower in _providers:
            return _registered_value(lower)
        if profile is None:
            profile = _profile_tokens(_config())   # read only when needed
        return profile.get(lower)

    return resolve


def expand(text, extra=None, now=None, unknown=None):
    """Fill in %token% placeholders in `text`, case-insensitively, in a single
    pass: inserted values are never expanded again. Looked up in this order:
    `extra` (a dict of more tokens), Hariku's dynamic placeholders (%greeting%,
    %time%, %day%, %date%, %zulu%, %reminders%), those extensions registered,
    then the profile (%myname%, %mynickname%, %mytitle%, %mybirthday%, %myage%
    and the user's own keys). `now` is the time for the dynamic ones (default:
    the clock). Unknown tokens and lone % signs are left as they are, unless
    `unknown` is a string: then unknown tokens become it (the startup greeting
    passes "", so the placeholder of an extension that is gone says nothing)."""
    if not isinstance(text, str) or "%" not in text:
        return text
    resolve = _resolver(extra, now)
    out, done = [], 0
    start = text.find("%")
    while start != -1:
        match = _TOKEN_RE.match(text, start)
        value = resolve(match.group(1)) if match else None
        if value is None and match and unknown is not None:
            value = unknown
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


_SPACE_BEFORE_MARK = re.compile(r"\s+([.,!?;:])")
_REPEATED_COMMAS = re.compile(r",(?:\s*,)+")
_PAUSE_BEFORE_STOP = re.compile(r"[,;:]+(?=[.!?])")
_AFTER_STOP = re.compile(r"([.!?])(?:\s*[.,;:])+")


def tidy_spoken(text):
    """Text with the gaps an empty placeholder leaves closed up: runs of spaces,
    a space before punctuation, ". ." and ", ." ("Welcome aboard, ." becomes
    "Welcome aboard."). Clock times and decimals are left alone."""
    text = _one_line(text)
    text = _SPACE_BEFORE_MARK.sub(r"\1", text)
    text = _REPEATED_COMMAS.sub(",", text)
    text = _PAUSE_BEFORE_STOP.sub("", text)
    text = _AFTER_STOP.sub(r"\1", text)
    return text.lstrip(" .,;:!?").strip()


# ------------------------------------------------------------
# The "Insert placeholder" menu (the Profile page and Routines' builder)
# ------------------------------------------------------------

MENU_VALUE_MAX = 40


def menu_value(value, empty=None):
    """A value shortened for a menu label; `empty` (default "not set") when blank."""
    value = _one_line(value)
    if not value:
        return _("profile_menu_not_set") if empty is None else empty
    return value if len(value) <= MENU_VALUE_MAX else value[:MENU_VALUE_MAX - 1] + "…"


def menu_entries(name="", nickname="", title="", birthday="", age="", fields=(),
                 tokens=(), dynamic=None):
    """(token, label) pairs for an Insert placeholder menu: the profile, the
    user's own keys, `tokens` (the caller's own (key, description) pairs, such
    as Routines' %battery%), then Hariku's dynamic placeholders and those
    extensions registered, skipping keys `tokens` already has. `dynamic` is
    [(key, description, value)] (default: get_placeholders())."""
    entries = [
        ("%myname%", _("profile_menu_myname", value=menu_value(name))),
        ("%mynickname%", _("profile_menu_mynickname", value=menu_value(nickname or name))),
        ("%mytitle%", _("profile_menu_mytitle", value=menu_value(title))),
        ("%mybirthday%", _("profile_menu_mybirthday", value=menu_value(birthday))),
        ("%myage%", _("profile_menu_myage", value=menu_value(age))),
    ]
    for key, value in fields or ():
        entries.append((f"%{key}%", _("profile_menu_field", token=key,
                                      value=menu_value(value, _("profile_menu_empty")))))
    own = set()
    for key, description in tokens or ():
        own.add(key)
        entries.append((f"%{key}%", f"%{key}%: {description}"))
    for key, description, value in (get_placeholders() if dynamic is None else dynamic):
        if key in own:
            continue
        value = _one_line(value)
        if value:
            label = _("profile_menu_dynamic_value", token=key, description=description,
                      value=menu_value(value))
        else:
            label = _("profile_menu_dynamic", token=key, description=description)
        entries.append((f"%{key}%", label))
    return entries


def insert_placeholder(value, start, end, token):
    """Put `token` into `value` at the caret, or in place of a partly selected
    stretch start..end. When all the text is selected, as tabbing into a field
    does, the token goes at the end instead, so no text is lost. Returns
    (new_value, caret after the token)."""
    value = str(value or "")
    start = max(0, min(int(start), len(value)))
    end = max(start, min(int(end), len(value)))
    if start == 0 and end == len(value):
        start = end = len(value)
    return value[:start] + token + value[end:], start + len(token)
