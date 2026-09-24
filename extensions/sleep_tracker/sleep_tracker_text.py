# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Spoken and displayed text for Sleep Pattern, in the user's language. Times are
24-hour ("01:15"); durations are words ("6 hours 25 minutes", "6 jam 25
menit"), rounded to 5 minutes where they are an estimate.
"""

import datetime
import os

from core.i18n import format_date, get_translator

import sleep_tracker_analysis as analysis

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("sleep_tracker", os.path.join(EXT_DIR, "locales"))

ROUND_TO = 5
SAME_WITHIN = 10     # minutes: "about the same as your average"


# ------------------------------------------------------------
# Pieces
# ------------------------------------------------------------

def clock(value):
    """"HH:MM" for a datetime, or for minutes after midnight."""
    if isinstance(value, datetime.datetime):
        return value.strftime("%H:%M")
    value = int(value) % analysis.MINUTES_PER_DAY
    return f"{value // 60:02d}:{value % 60:02d}"


def rounded(minutes, step=ROUND_TO):
    return int(step * round(float(minutes) / step))


def duration(minutes, exact=False):
    """"6 hours 25 minutes"; rounded to 5 minutes (at least 5) unless exact."""
    minutes = max(0, int(round(minutes))) if exact else max(ROUND_TO, rounded(minutes))
    hours, rest = divmod(minutes, 60)
    hour_text = _("hours_one") if hours == 1 else _("hours_many", count=hours)
    minute_text = _("minutes_one") if rest == 1 else _("minutes_many", count=rest)
    if hours and rest:
        return _("hours_minutes", hours=hour_text, minutes=minute_text)
    return hour_text if hours else minute_text


def night_label(night):
    return format_date(night, "%A %d %B")


def _span(block):
    return {"start": clock(block["start"]), "end": clock(block["end"])}


# ------------------------------------------------------------
# Sentences
# ------------------------------------------------------------

def sleep_sentences(result):
    """The main sleep, staying up late and naps, as sentences."""
    main = result["main"]
    key = "sleep_day" if result["daytime"] else "sleep_night"
    sentences = [_(key, duration=duration(main["asleep"]), **_span(main))]
    if result["late"] and not result["daytime"]:
        sentences.append(_("late", time=clock(main["start"])))
    naps = result["naps"]
    if len(naps) == 1:
        sentences.append(_("nap_one", **_span(naps[0])))
    elif naps:
        items = ", ".join(_("nap_item", **_span(n)) for n in naps)
        sentences.append(_("nap_many", count=len(naps), list=items))
    return sentences


def marked_sentences(result):
    return [_("marked_not_sleep", **_span(b)) for b in result["corrected"]]


def compare_sentence(diff):
    if diff is None:
        return ""
    if abs(diff) < SAME_WITHIN:
        return _("compare_same")
    key = "compare_more" if diff > 0 else "compare_less"
    return _(key, duration=duration(abs(diff)))


def _away_hours():
    # No times: the block may run past the 48 hours the analysis reads.
    return {"hours": analysis.MAX_SLEEP_SPAN // 60}


def last_night_text(result, diff=None):
    """The answer for "Last night's sleep"."""
    status = result["status"]
    if status == "sleep":
        sentences = sleep_sentences(result) + [compare_sentence(diff)]
    elif status == "away":
        sentences = [_("away_last", **_away_hours())]
    elif status == "corrected":
        sentences = [_("corrected_last", **_span(result["corrected"][-1]))]
    elif status == "no_sleep":
        sentences = [_("no_sleep_last")]
    else:
        sentences = [_("no_data_last")]
    return " ".join(s for s in sentences if s)


def night_text(result):
    """What happened on a night, as full sentences (without the date)."""
    status = result["status"]
    if status == "sleep":
        sentences = sleep_sentences(result) + marked_sentences(result)
    elif status == "away":
        sentences = [_("away_row", **_away_hours())]
    elif status == "corrected":
        sentences = marked_sentences(result)
    elif status == "no_sleep":
        sentences = [_("no_sleep_row")]
    else:
        sentences = [_("no_data_row")]
    return " ".join(sentences)


def row_text(result):
    """One history row: the night's date, then what happened."""
    return _("row", label=night_label(result["night"]), text=night_text(result))


def briefing_sentence(result):
    main = result["main"]
    key = "briefing_day" if result["daytime"] else "briefing"
    return _(key, duration=duration(main["asleep"]), **_span(main))


def summary_text(stats):
    if not stats["month_nights"]:
        return _("summary_empty")
    sentences = []
    if stats["week_nights"]:
        sentences.append(_("summary_week", duration=duration(stats["week_average"]),
                           bedtime=clock(stats["bedtime"]), wake=clock(stats["wake"])))
        late = stats["late_nights"]
        if late == 0:
            sentences.append(_("summary_late_none"))
        elif late == 1:
            sentences.append(_("summary_late_one"))
        else:
            sentences.append(_("summary_late_many", count=late))
    else:
        sentences.append(_("summary_week_none"))
    sentences.append(_("summary_month", duration=duration(stats["month_average"])))
    return " ".join(sentences)


def details_text(result, diff=None):
    """Everything known about one night, one fact per line."""
    lines = [night_label(result["night"]), night_text(result)]
    main = result["main"]
    bedtime = clock(result["bedtime"])
    if main is not None:
        if main["wakeups"] == 1:
            lines.append(_("details_wakeups_one", duration=duration(main["awake"], exact=True)))
        elif main["wakeups"] > 1:
            lines.append(_("details_wakeups_many", count=main["wakeups"],
                           duration=duration(main["awake"], exact=True)))
        if main["unknown"]:
            lines.append(_("details_unknown", duration=duration(main["unknown"], exact=True)))
        if result["late"]:
            lines.append(_("details_late", time=clock(main["start"]), bedtime=bedtime))
        else:
            lines.append(_("details_not_late", bedtime=bedtime))
        for nap in result["naps"]:
            lines.append(_("details_nap", duration=duration(nap["asleep"]), **_span(nap)))
        comparison = compare_sentence(diff)
        if comparison:
            lines.append(comparison)
    for block in result["corrected"]:
        lines.append(_("details_marked", **_span(block)))
    lines.append(_("details_coverage", known=duration(result["known"], exact=True),
                   elapsed=duration(result["elapsed"], exact=True)))
    lines.append(_("estimate_note"))
    return "\n".join(lines)


def nudge_text(now, nickname=""):
    nickname = " ".join(str(nickname or "").split())
    if nickname:
        return _("nudge_name", time=clock(now), name=nickname)
    return _("nudge", time=clock(now))
