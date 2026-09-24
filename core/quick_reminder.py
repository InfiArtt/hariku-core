# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The quick reminder (N) and the reminder dialog's "Or type it in one sentence"
field: which language packs are on, reading a sentence with core.when, the
read-back spoken in the Hariku language ("Minum obat, Jumat 25 September 2026,
jam 08:00, setiap hari. Simpan?"), and saving through core.reminders. No wx
here; the windows are ui/quick_reminder_dialog.py and ui/reminder_dialog.py.

Everything is read on this computer. Nothing is sent anywhere.
"""

import datetime
import logging

import core.api
import core.reminders
from core import when, when_packs
from core.i18n import get_current_language, get_translator
from core.speech import speak

logger = logging.getLogger(__name__)
_ = get_translator("core")

# Core config key: the packs switched on in Preferences, Reminders, besides the
# Hariku language, English and Indonesian ({"quick_reminder_languages": ["de"]}).
CONFIG_KEY = "quick_reminder_languages"
# Where the Hariku Assistant extension (the quick reminder before core 2.7)
# kept the same setting, read once when the core has none yet.
LEGACY_DATA_KEY = "Assistant"

# The order of the reminder dialog's Repeat choice.
REPEATS = core.reminders.RECURRENCES
# The reminder dialog's "How often" choice goes up to this many (more when a
# sentence asked for more).
MAX_INTERVAL = 30
_UNITS = {"daily": "day", "weekly": "week", "monthly": "month", "yearly": "year"}


def _now():
    return datetime.datetime.now()


# ------------------------------------------------------------
# Languages
# ------------------------------------------------------------

def _clean_codes(value):
    if not isinstance(value, list):
        return []
    out = []
    for code in value:
        if isinstance(code, str) and code and code not in out:
            out.append(code)
    return out


def extra_languages():
    """Pack codes switched on in Preferences, Reminders (the Hariku language,
    English and Indonesian are always on)."""
    config = core.api.load_data("Core")
    if isinstance(config, dict) and CONFIG_KEY in config:
        return _clean_codes(config.get(CONFIG_KEY))
    legacy = core.api.load_data(LEGACY_DATA_KEY)
    return _clean_codes(legacy.get("extra_languages")) if isinstance(legacy, dict) else []


def set_extra_languages(codes):
    config = core.api.load_data("Core")
    config = config if isinstance(config, dict) else {}
    config[CONFIG_KEY] = _clean_codes(list(codes))
    core.api.save_data("Core", config)


def optional_languages():
    """[(code, name)] of the packs the user can switch on."""
    return [(code, when_packs.pack_name(code))
            for code in when_packs.optional_codes(get_current_language())]


def active_packs():
    """Pack codes in priority order: the Hariku language, English,
    Indonesian, then the ones added in Preferences."""
    return when_packs.default_codes(get_current_language(), extra_languages())


# ------------------------------------------------------------
# Reading and saving
# ------------------------------------------------------------

def parse_text(text, now=None, default_date=None):
    """Read a sentence with the active packs. `default_date` ("YYYY-MM-DD" or
    a date) is the date for a sentence that says a time or a repeat but no
    date; it is ignored when it is today, so "jam 8" still means the next
    8 o'clock."""
    now = now or _now()
    if isinstance(default_date, str):
        parsed = core.reminders.parse_date_text(default_date)
        default_date = datetime.date.fromisoformat(parsed) if parsed else None
    if isinstance(default_date, datetime.datetime):
        default_date = default_date.date()
    if default_date == now.date():
        default_date = None
    return when.parse(text, now=now, language=get_current_language(), packs=active_packs(),
                      default_date=default_date)


def save_result(result):
    """Add the reminder through the core reminders API and say so."""
    if result is None or not result.ok:
        return False
    core.reminders.add_reminder(result.title, result.date, result.time,
                                recurrence=result.recurrence, interval=result.interval)
    logger.info(f"Quick reminder added for {result.date} {result.time} "
                f"({result.recurrence}, every {result.interval}).")
    speak(_("qr_saved"), interrupt=True)
    return True


# ------------------------------------------------------------
# The read-back, in the Hariku language
# ------------------------------------------------------------

def weekday_name(index):
    return _(f"day_{index}")


def month_name(month):
    return _(f"month_{month}")


def _day(date_str):
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()


def date_text(date_str):
    """ "Friday 25 September 2026" / "Jumat 25 September 2026"."""
    day = _day(date_str)
    return _("qr_rb_date", weekday=weekday_name(day.weekday()), day=day.day,
             month=month_name(day.month), year=day.year)


def time_text(time_str):
    return _("qr_rb_time", time=time_str)


def repeat_text(recurrence, interval, date_str):
    """ "every day", "setiap 2 hari", "every Monday"... or "" for none."""
    if recurrence == "none" or not date_str:
        return ""
    day = _day(date_str)
    n = max(1, int(interval or 1))
    suffix = "_n" if n > 1 else ""
    if recurrence == "daily":
        return _("qr_repeat_daily" + suffix, n=n)
    if recurrence == "weekly":
        return _("qr_repeat_weekly" + suffix, n=n, weekday=weekday_name(day.weekday()))
    if recurrence == "monthly":
        return _("qr_repeat_monthly" + suffix, n=n, day=day.day)
    if recurrence == "yearly":
        return _("qr_repeat_yearly" + suffix, n=n, day=day.day, month=month_name(day.month))
    return ""


def when_text(result):
    return ", ".join([date_text(result.date), time_text(result.time)])


_PROBLEM_KEYS = (
    ("invalid_date", "qr_rb_invalid_date"),
    ("invalid_time", "qr_rb_invalid_time"),
    ("unsupported_repeat", "qr_rb_unsupported_repeat"),
    ("nothing_found", "qr_rb_nothing_found"),
)


def _summary(result):
    """ "Minum obat, Jumat 25 September 2026, jam 08:00, setiap hari." and the
    notes after it (assumed time, conflict, in the past)."""
    parts = [result.title, date_text(result.date), time_text(result.time)]
    repeat = repeat_text(result.recurrence, result.interval, result.date)
    if repeat:
        parts.append(repeat)
    sentences = [", ".join(parts) + "."]
    if result.time_assumed:
        sentences.append(_("qr_rb_time_assumed", time=result.time))
    if "conflict" in result.problems:
        sentences.append(_("qr_rb_conflict"))
    if result.in_past:
        sentences.append(_("qr_rb_in_past"))
    return sentences


def readback(result):
    """The quick reminder's sentence after Enter, ending in "Save?" when it
    can be saved."""
    for problem, key in _PROBLEM_KEYS:
        if problem in result.problems:
            return _(key)
    if "no_title" in result.problems:
        return _("qr_rb_no_title", when=when_text(result))
    return " ".join(_summary(result) + [_("qr_rb_save")])


def fill_values(result):
    """What the reminder dialog's fields get from a sentence: a dict with
    date, time, recurrence, interval and, when the sentence had one, title.
    None when nothing can be filled in."""
    if result is None or not result.date or not result.time:
        return None
    if any(p in when.BLOCKING and p != "no_title" for p in result.problems):
        return None
    values = {"date": result.date, "time": result.time, "recurrence": result.recurrence,
              "interval": result.interval}
    if result.title:
        values["title"] = result.title
    return values


def fill_readback(result):
    """What the reminder dialog says after Fill in: the read-back with its
    notes, or what went wrong. The fields are filled in (see fill_values)."""
    for problem, key in _PROBLEM_KEYS:
        if problem in result.problems:
            return _(key + "_fill")
    if "no_title" in result.problems:
        return _("qr_rb_no_title_fill", when=when_text(result))
    return " ".join(_summary(result) + [_("qr_rb_filled")])


def full_dialog_prefill(result, text="", fallback_date=None):
    """(title, date, time, recurrence, interval) for the reminder dialog when
    the quick reminder's Edit is pressed. Whatever the sentence didn't give is
    None (the dialog keeps its own default), except the title, which is then
    the text as typed, and the date, which is then `fallback_date`."""
    if result is None:
        return (text or "", fallback_date, None, "none", 1)
    return (result.title or text or "", result.date or fallback_date, result.time,
            result.recurrence, result.interval)


def interval_choices(recurrence, maximum=MAX_INTERVAL):
    """The reminder dialog's "How often" items for a repeat: "every day",
    "every 2 days", ... up to `maximum`."""
    unit = _UNITS.get(recurrence, "day")
    return [_(f"rem_every_{unit}") if n == 1 else _(f"rem_every_{unit}_n", n=n)
            for n in range(1, max(1, int(maximum)) + 1)]
