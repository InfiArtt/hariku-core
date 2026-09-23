# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Morning Briefing: putting the spoken briefing together, and the contract other
extensions use to add to it.

The briefing is, in order: a greeting for the time of day, today's date (in the
date format chosen in General settings), today's reminders (the same list the
agenda shows, recurring ones included), then what other extensions contribute.

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
"""

import os

from core.i18n import format_date, get_translator

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("briefing", os.path.join(EXT_DIR, "locales"))

COLLECT_EVENT = "on_briefing_collect"
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


def _agenda_item(reminder):
    title = " ".join(str(reminder.get("title") or "").split()) or _("agenda_untitled")
    clock = str(reminder.get("time") or "").strip()
    text = _("agenda_item", time=clock, title=title) if clock else title
    return _end_sentence(text)


def agenda_sentences(reminders):
    """Sentences for today's reminders. Done ones are left out."""
    reminders = [r for r in (reminders or []) if isinstance(r, dict)]
    if not reminders:
        return [_("agenda_none")]
    pending = [r for r in reminders if not r.get("is_done")]
    if not pending:
        return [_("agenda_all_done")]
    pending.sort(key=lambda r: (str(r.get("time") or "99:99"), str(r.get("title") or "")))
    head = _("agenda_one") if len(pending) == 1 else _("agenda_many", count=len(pending))
    sentences = [head] + [_agenda_item(r) for r in pending[:MAX_AGENDA_ITEMS]]
    if len(pending) > MAX_AGENDA_ITEMS:
        sentences.append(_("agenda_more", count=len(pending) - MAX_AGENDA_ITEMS))
    return sentences


def collect_contributions(bus):
    """Emit the collect event and return the usable entries, in order."""
    lines = []
    bus.emit(COLLECT_EVENT, lines)
    collected = []
    for line in lines:
        if isinstance(line, str):
            text = " ".join(line.split())
            if text:
                collected.append(text)
    return collected


def build_briefing(now, reminders, date_format, bus):
    """The briefing as a list of sentences. `now` is a local datetime."""
    return ([_(greeting_key(now.hour)),
             _("today_is", date=format_date(now.date(), date_format or DEFAULT_DATE_FORMAT))]
            + agenda_sentences(reminders)
            + collect_contributions(bus))


def should_auto_play(config, today_str):
    """True if the automatic briefing is on and has not played today."""
    config = config if isinstance(config, dict) else {}
    return bool(config.get("auto_first_start")) and config.get("last_auto_date") != today_str
