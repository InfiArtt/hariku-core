# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for Clipboard History, in the user's language:
one-line previews, "2 minutes ago", list rows.
"""

import datetime
import os
import time

from core.i18n import format_date, get_translator

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("clipboard_history", os.path.join(EXT_DIR, "locales"))

PREVIEW_CHARS = 120
SPEAK_CHARS = 4000     # longer texts are cut when spoken with Shift+V
LINE_SEPARATOR = " / "
ELLIPSIS = "…"


def preview(text, limit=PREVIEW_CHARS):
    """One line: blank lines dropped, whitespace collapsed, lines joined with
    " / ", at most `limit` characters plus an ellipsis."""
    text = (text or "").strip()
    head = text[:limit * 8]     # enough to fill a preview; the rest is never looked at
    lines = (" ".join(line.split()) for line in head.splitlines())
    line = LINE_SEPARATOR.join(part for part in lines if part)
    if len(line) > limit:
        return line[:limit].rstrip() + ELLIPSIS
    if len(head) < len(text):
        return line + ELLIPSIS
    return line


def ago(timestamp, now=None):
    """'just now', '2 minutes ago', '3 hours ago', '4 days ago' or 'on 3 September 2026'."""
    now = time.time() if now is None else now
    seconds = now - timestamp
    if seconds < 60:
        return _("time_just_now")
    minutes = int(seconds // 60)
    if minutes < 60:
        return _("time_minute") if minutes == 1 else _("time_minutes", count=minutes)
    hours = minutes // 60
    if hours < 24:
        return _("time_hour") if hours == 1 else _("time_hours", count=hours)
    days = hours // 24
    if days < 30:
        return _("time_day") if days == 1 else _("time_days", count=days)
    day = datetime.date.fromtimestamp(timestamp)
    return _("time_on_date", date=f"{day.day} {format_date(day, '%B %Y')}")


def row(item, now=None):
    """One list row: 'Pinned: first line / second line, 2 minutes ago'."""
    values = {"text": preview(item["text"]), "ago": ago(item["time"], now)}
    return _("row_pinned", **values) if item["pinned"] else _("row", **values)


def count_text(count):
    return _("count_one") if count == 1 else _("count_many", count=count)


def speakable(text):
    """What Shift+V says: the text, cut after SPEAK_CHARS characters."""
    if len(text) <= SPEAK_CHARS:
        return text
    return text[:SPEAK_CHARS].rstrip() + " " + ELLIPSIS + " " + _("speak_truncated")
