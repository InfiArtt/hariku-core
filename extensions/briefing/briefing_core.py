# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Morning Briefing: putting the spoken briefing and the evening summary together,
and the contract other extensions use to add to them.

The briefing is, in order: a greeting for the time of day (with the name the
user gave in Preferences, Profile, if any), today's date (in the date format
chosen in General settings), today's reminders (the same list the agenda shows,
recurring ones included, with %placeholders% filled in), then what other
extensions contribute. On the user's birthday the greeting adds "Happy
birthday!".

The evening summary is: the greeting, how many of today's reminders are done
(naming the ones that aren't), tomorrow's reminders (how many, and the first
with its time), then what other extensions contribute.

Contributing to the briefing
----------------------------
Each time the briefing plays, Morning Briefing calls

    bus.emit("on_briefing_collect", lines)

where `lines` is a new, empty list. To add to the briefing, subscribe in your
register(bus) and append to that list:

    def _on_briefing_collect(lines):
        if _cached_summary:
            lines.append(_cached_summary)   # "Weather in Jakarta: light rain, ..."

    bus.subscribe("on_briefing_collect", _on_briefing_collect)

Rules:
  * The handler runs on the UI thread while the briefing is being built, so it
    MUST return quickly. Use data you already have (a cache). Never do network
    requests, subprocesses, sleeps or other slow work in it. If you have no data
    yet, append nothing.
  * Append plain text in the user's current language: one short sentence, two at
    most. No markup. Don't call speak() yourself; the briefing speaks it.
  * Only append. Don't remove, reorder or change entries other extensions added.
  * Entries that are not strings, or are blank, are ignored. If your handler
    raises, the bus logs it and the briefing goes on without you.
  * Contributions are spoken after the reminders, in subscription order.

Contributing to the evening summary
-----------------------------------
The same contract, with its own event:

    bus.emit("on_evening_collect", lines)

Append what matters for tonight or tomorrow, e.g. "Tomorrow: light rain, 31
degrees." Everything above applies: fast, cache only, plain text, append only.
"""

import os

from core.i18n import format_date, get_translator

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("briefing", os.path.join(EXT_DIR, "locales"))

COLLECT_EVENT = "on_briefing_collect"
EVENING_COLLECT_EVENT = "on_evening_collect"
# Times offered for the automatic evening summary.
EVENING_TIMES = ["%02d:%02d" % divmod(minutes, 60) for minutes in range(18 * 60, 23 * 60 + 1, 30)]
DEFAULT_EVENING_TIME = "20:00"
DEFAULT_DATE_FORMAT = "%A, %d %B %Y"   # the core's default "date_format"
MAX_AGENDA_ITEMS = 10


def greeting_key(hour):
    """Locale key for a greeting at `hour` (0-23). Four parts of the day, as
    Indonesian has them: pagi, siang, sore, malam."""
    if 4 <= hour < 11:
        return "greet_morning"
    if 11 <= hour < 15:
        return "greet_midday"
    if 15 <= hour < 18:
        return "greet_afternoon"
    return "greet_evening"


def _end_sentence(text):
    return text if text[-1:] in (".", "!", "?") else text + "."


def greeting(hour, nickname=""):
    """The greeting for `hour`, addressing the user by `nickname` when there is
    one: "Good morning, Bro." / "Selamat pagi, Bro."."""
    key = greeting_key(hour)
    nickname = " ".join(str(nickname or "").split())
    if not nickname:
        return _(key)
    return _end_sentence(_(key + "_name", name=nickname))


def greeting_sentences(hour, nickname="", birthday=False):
    """The greeting, and "Happy birthday!" on the user's birthday."""
    return [greeting(hour, nickname)] + ([_("happy_birthday")] if birthday else [])


def _item_text(reminder, expand=None):
    """ "09:00, Stand-up" (no full stop), with placeholders filled in."""
    title = str(reminder.get("title") or "")
    if expand is not None:
        title = expand(title)
    title = " ".join(title.split()) or _("agenda_untitled")
    clock = str(reminder.get("time") or "").strip()
    return _("agenda_item", time=clock, title=title) if clock else title


def _agenda_item(reminder, expand=None):
    return _end_sentence(_item_text(reminder, expand))


def agenda_sentences(reminders, expand=None):
    """Sentences for today's reminders. Done ones are left out. `expand`, if
    given, fills in placeholders in each title (core.personal.expand)."""
    reminders = [r for r in (reminders or []) if isinstance(r, dict)]
    if not reminders:
        return [_("agenda_none")]
    pending = [r for r in reminders if not r.get("is_done")]
    if not pending:
        return [_("agenda_all_done")]
    pending.sort(key=lambda r: (str(r.get("time") or "99:99"), str(r.get("title") or "")))
    head = _("agenda_one") if len(pending) == 1 else _("agenda_many", count=len(pending))
    sentences = [head] + [_agenda_item(r, expand) for r in pending[:MAX_AGENDA_ITEMS]]
    if len(pending) > MAX_AGENDA_ITEMS:
        sentences.append(_("agenda_more", count=len(pending) - MAX_AGENDA_ITEMS))
    return sentences


def _by_time(reminders):
    return sorted(reminders, key=lambda r: (str(r.get("time") or "99:99"), str(r.get("title") or "")))


def evening_today_sentences(reminders, expand=None):
    """How many of today's reminders are done, naming the ones that aren't."""
    reminders = [r for r in (reminders or []) if isinstance(r, dict)]
    if not reminders:
        return [_("evening_none")]
    open_ones = _by_time([r for r in reminders if not r.get("is_done")])
    if not open_ones:
        return [_("evening_all_done")]
    done = len(reminders) - len(open_ones)
    sentences = [_("evening_done_count", done=done, count=len(reminders)), _("evening_not_done")]
    sentences += [_agenda_item(r, expand) for r in open_ones[:MAX_AGENDA_ITEMS]]
    if len(open_ones) > MAX_AGENDA_ITEMS:
        sentences.append(_("agenda_more", count=len(open_ones) - MAX_AGENDA_ITEMS))
    return sentences


def evening_tomorrow_sentences(reminders, expand=None):
    """Tomorrow's reminders: how many, and the first one with its time."""
    pending = _by_time([r for r in (reminders or [])
                        if isinstance(r, dict) and not r.get("is_done")])
    if not pending:
        return [_("tomorrow_none")]
    first = _item_text(pending[0], expand)
    if len(pending) == 1:
        return [_end_sentence(_("tomorrow_one", item=first))]
    return [_("tomorrow_many", count=len(pending)), _end_sentence(_("tomorrow_first", item=first))]


def collect_contributions(bus, event=COLLECT_EVENT):
    """Emit a collect event and return the usable entries, in order."""
    lines = []
    bus.emit(event, lines)
    collected = []
    for line in lines:
        if isinstance(line, str):
            text = " ".join(line.split())
            if text:
                collected.append(text)
    return collected


def build_briefing(now, reminders, date_format, bus, nickname="", expand=None,
                   birthday=False, greet=True):
    """The briefing as a list of sentences. `now` is a local datetime; `nickname`,
    `expand` and `birthday` come from core.personal (see main.briefing_text).
    greet=False leaves the greeting out (Hariku has just said it)."""
    return ((greeting_sentences(now.hour, nickname, birthday) if greet else [])
            + [_("today_is", date=format_date(now.date(), date_format or DEFAULT_DATE_FORMAT))]
            + agenda_sentences(reminders, expand)
            + collect_contributions(bus))


def build_evening(now, today_reminders, tomorrow_reminders, bus, nickname="", expand=None,
                  birthday=False):
    """The evening summary as a list of sentences."""
    return (greeting_sentences(now.hour, nickname, birthday)
            + evening_today_sentences(today_reminders, expand)
            + evening_tomorrow_sentences(tomorrow_reminders, expand)
            + collect_contributions(bus, EVENING_COLLECT_EVENT))


def should_auto_play(config, today_str):
    """True if the automatic briefing is on and has not played today."""
    config = config if isinstance(config, dict) else {}
    return bool(config.get("auto_first_start")) and config.get("last_auto_date") != today_str


def evening_time(config):
    """The automatic evening summary's time, "HH:MM" between 18:00 and 23:00."""
    config = config if isinstance(config, dict) else {}
    value = config.get("evening_time")
    return value if value in EVENING_TIMES else DEFAULT_EVENING_TIME


def should_auto_evening(config, now):
    """True once the evening summary's time has come today, if it is on and
    hasn't played today. `now` is a local datetime."""
    config = config if isinstance(config, dict) else {}
    if not config.get("evening_auto"):
        return False
    if config.get("last_evening_date") == now.strftime("%Y-%m-%d"):
        return False
    return now.strftime("%H:%M") >= evening_time(config)
