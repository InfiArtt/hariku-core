# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What Timer & Alarm says and shows, in the Hariku language (English or
Indonesian, casual "kamu"/"aku"). No wx here.

Times: the read-back of a new alarm always says the day, the date and the time
with its part of the day, because a bare "jam 2" could be 02:00 or 14:00:
"jam 02.00 dini hari" in Indonesian, "at 2:00 AM" in English (the locale's
"clock_spoken"). Other sentences use the 24-hour clock ("clock_24": 14.00 or
14:00).
"""

import datetime
import math
import os

from core.i18n import format_date, get_translator

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("timer_alarm", os.path.join(EXT_DIR, "locales"))


def cap(text):
    """The first letter in capitals ("timer mie selesai." -> "Timer mie selesai.")."""
    return text[:1].upper() + text[1:] if text else text


# ------------------------------------------------------------
# Clock times and dates
# ------------------------------------------------------------

def clock_24(moment):
    """ "14:00" / "14.00"."""
    return _("clock_24", hh=f"{moment.hour:02d}", mm=f"{moment.minute:02d}")


def part_key(moment):
    """The part of the day a time falls in, as a locale key: midnight (00:00),
    early (00:01-03:59, "dini hari"), morning (04:00-10:59), midday (11:00-
    14:59), afternoon (15:00-17:59) or evening (18:00-23:59)."""
    minutes = moment.hour * 60 + moment.minute
    if minutes == 0:
        return "part_midnight"
    if moment.hour < 4:
        return "part_early"
    if moment.hour < 11:
        return "part_morning"
    if moment.hour < 15:
        return "part_midday"
    if moment.hour < 18:
        return "part_afternoon"
    return "part_evening"


def ampm(moment):
    if moment.hour == 0 and moment.minute == 0:
        return _("ampm_midnight")
    if moment.hour == 12 and moment.minute == 0:
        return _("ampm_noon")
    return _("ampm_am") if moment.hour < 12 else _("ampm_pm")


def clock_spoken(moment):
    """A time nobody can mistake: "02.00 dini hari" / "2:00 AM"."""
    return _("clock_spoken", h12=moment.hour % 12 or 12, hh=f"{moment.hour:02d}",
             mm=f"{moment.minute:02d}", ampm=ampm(moment), part=_(part_key(moment)))


def date_text(day, today):
    """ "Saturday 26 September" (with the year when it isn't this year)."""
    values = {"weekday": format_date(day, "%A"), "day": day.day,
              "month": format_date(day, "%B"), "year": day.year}
    return _("date_year" if day.year != today.year else "date", **values)


def day_text(day, today):
    """ "tomorrow, Saturday 26 September", "today, ..." or just the date."""
    if day == today:
        return _("when_today", date=date_text(day, today))
    if day == today + datetime.timedelta(days=1):
        return _("when_tomorrow", date=date_text(day, today))
    return date_text(day, today)


def short_day(day, today):
    """ "today", "tomorrow" or "Saturday 26 September"."""
    if day == today:
        return _("rel_today")
    if day == today + datetime.timedelta(days=1):
        return _("rel_tomorrow")
    return date_text(day, today)


# ------------------------------------------------------------
# Durations
# ------------------------------------------------------------

def _count(n, one, many):
    return _(one) if n == 1 else _(many, n=n)


def duration_text(seconds):
    """ "1 hour 30 minutes", "3 menit", "1 minute 30 seconds"."""
    seconds = max(0, int(round(seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(_count(hours, "dur_hour", "dur_hours"))
    if minutes:
        parts.append(_count(minutes, "dur_minute", "dur_minutes"))
    if secs or not parts:
        parts.append(_count(secs, "dur_second", "dur_seconds"))
    return " ".join(parts)


def left_text(seconds, precise=False):
    """Time still to go. `precise` (a timer's last minutes): with seconds,
    counted up so it never says 0 while running. Otherwise to the nearest
    minute, "less than a minute" under half a minute."""
    seconds = max(0.0, float(seconds))
    if precise and seconds < 600:
        return duration_text(math.ceil(seconds))
    minutes = int(round(seconds / 60.0))
    if minutes == 0:
        return _("less_than_minute")
    return duration_text(minutes * 60)


# ------------------------------------------------------------
# Repeats
# ------------------------------------------------------------

def repeat_text(recurrence, interval, due):
    """ "every day", "setiap Senin", "every month on day 5"... or ""."""
    if recurrence == "none" or due is None:
        return ""
    n = max(1, int(interval or 1))
    many = n > 1
    if recurrence == "daily":
        return _("rpt_daily_n", n=n) if many else _("rpt_daily")
    weekday = format_date(due, "%A")
    if recurrence == "weekly":
        return _("rpt_weekly_n", n=n, weekday=weekday) if many else _("rpt_weekly", weekday=weekday)
    if recurrence == "monthly":
        day = due.day
        return _("rpt_monthly_n", n=n, day=day) if many else _("rpt_monthly", day=day)
    if recurrence == "yearly":
        values = {"n": n, "day": due.day, "month": format_date(due, "%B")}
        return _("rpt_yearly_n", **values) if many else _("rpt_yearly", **values)
    return ""


# ------------------------------------------------------------
# Alarms and timers by name
# ------------------------------------------------------------

def _due(item):
    return item["due"]


def name(item):
    """How a sentence names an item: "alarm gang war", 'the alarm "gang war"',
    "timer 10 menit", "the timer for 10 minutes"."""
    label = item.get("label") or ""
    if item["kind"] == "timer":
        if label:
            return _("name_timer_named", label=label)
        return _("name_timer_plain", duration=duration_text(item.get("seconds") or 0))
    if label:
        return _("name_alarm_named", label=label)
    return _("name_alarm_plain", clock=clock_24(_due(item)))


def title(item):
    """An item's name for a list: "Alarm gang war", 'Timer "tea"', "Alarm"."""
    label = item.get("label") or ""
    kind = item["kind"]
    if label:
        return _(f"title_{kind}_named", label=label)
    return _(f"title_{kind}_plain")


def join_names(names):
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return _("join_and", first=", ".join(names[:-1]), last=names[-1])


def when_short(item, now):
    """ "tomorrow at 2:00 AM", "setiap hari jam 05.00 pagi"."""
    due = _due(item)
    repeat = repeat_text(item.get("recurrence", "none"), item.get("interval", 1), due)
    day = repeat or short_day(due.date(), now.date())
    return _("when_short", day=day, clock=clock_spoken(due))


def at_text(moment, now):
    """ "02:00", or "02:00 on Friday 25 September" when it wasn't today."""
    if moment.date() == now.date():
        return clock_24(moment)
    return _("at_with_date", clock=clock_24(moment), date=date_text(moment.date(), now.date()))


# ------------------------------------------------------------
# A new alarm, read back before it is set
# ------------------------------------------------------------

def readback(parsed, now):
    """ 'Alarm "gang war", tomorrow, Saturday 26 September, at 2:00 AM. Set
    it?' with its notes (the time had passed today; two dates said)."""
    due = parsed.due
    alarm = (_("rb_alarm_named", label=parsed.label) if parsed.label
             else _("rb_alarm_plain"))
    repeat = repeat_text(parsed.recurrence, parsed.interval, due)
    sentences = [_("rb_alarm", name=alarm, when=day_text(due.date(), now.date()),
                   clock=clock_spoken(due), repeat=f", {repeat}" if repeat else "")]
    if parsed.passed_today:
        sentences.append(_("rb_passed_today"))
    if parsed.conflict:
        sentences.append(_("rb_conflict"))
    sentences.append(_("rb_ask"))
    return " ".join(sentences)


PROBLEM_KEYS = {
    "invalid_date": "err_bad_date",
    "invalid_time": "err_bad_time",
    "unsupported_repeat": "err_bad_repeat",
    "in_past": "err_in_past",
}


def alarm_problem(parsed):
    """What to say when an alarm can't be set as said."""
    if parsed.problem == "no_time":
        heard = ", ".join(parsed.recognised)
        if heard:
            return _("err_no_time_heard", heard=heard)
        return _("err_no_time")
    return _(PROBLEM_KEYS.get(parsed.problem, "err_no_time"))


def alarm_set(item, now):
    return _("alarm_set", left=left_text((_due(item) - now).total_seconds()))


# ------------------------------------------------------------
# Timers
# ------------------------------------------------------------

def timer_started(item):
    duration = duration_text(item.get("seconds") or 0)
    if item.get("label"):
        return _("timer_started_named", label=item["label"], duration=duration)
    return _("timer_started_plain", duration=duration)


def timer_left(item, now):
    left = left_text((_due(item) - now).total_seconds(), precise=True)
    return cap(_("left_timer", name=name(item), left=left))


def alarm_left(item, now):
    left = left_text((_due(item) - now).total_seconds())
    return cap(_("left_alarm", name=name(item), when=when_short(item, now), left=left))


# ------------------------------------------------------------
# Ringing, stopping, snoozing, missing
# ------------------------------------------------------------

def ring_text(items):
    """What is said while they ring: "Alarm: gang war." "Timer mie selesai."."""
    sentences = []
    for item in items:
        if item["kind"] == "alarm":
            if item.get("label"):
                sentences.append(_("ring_alarm_named", label=item["label"]))
            else:
                sentences.append(_("ring_alarm_plain", clock=clock_24(_due(item))))
        else:
            sentences.append(cap(_("ring_timer", name=name(item))))
    return " ".join(sentences)


def stopped_text(items):
    return cap(_("msg_stopped", name=join_names([name(i) for i in items])))


def already_stopped_text(items):
    return cap(_("msg_already_stopped", name=join_names([name(i) for i in items])))


def snoozed_text(items, seconds, until):
    return cap(_("msg_snoozed", name=join_names([name(i) for i in items]),
                 duration=duration_text(seconds), clock=clock_spoken(until)))


def missed_text(entry, now):
    """A ring nobody stopped, or one that came while Hariku was closed."""
    item = entry["item"]
    due = _due(item)
    if entry.get("reason") == "closed":
        key = "closed_timer" if item["kind"] == "timer" else "closed_alarm"
        return cap(_(key, name=name(item), at=at_text(due, now)))
    key = "missed_timer" if item["kind"] == "timer" else "missed_alarm"
    return cap(_(key, name=name(item), at=at_text(due, now)))


# ------------------------------------------------------------
# Lists
# ------------------------------------------------------------

def _alarm_item(item, now):
    when = when_short(item, now)
    if item.get("label"):
        return _("list_alarm_named", label=item["label"], when=when)
    return when


def _timer_item(item, now):
    left = left_text((_due(item) - now).total_seconds(), precise=True)
    if item.get("label"):
        return _("list_timer_named", label=item["label"], left=left)
    return _("list_timer_plain", duration=duration_text(item.get("seconds") or 0), left=left)


def list_text(alarms, timers, ringing, now):
    """Everything there is, spoken: what rings, the alarms, the timers."""
    sentences = []
    if ringing:
        sentences.append(_("list_ringing", items=join_names([name(i) for i in ringing])))
    if alarms:
        sentences.append(_("list_alarms", items="; ".join(_alarm_item(a, now) for a in alarms)))
    if timers:
        sentences.append(_("list_timers", items="; ".join(_timer_item(t, now) for t in timers)))
    if not sentences:
        return _("list_empty")
    return " ".join(sentences)


def alarm_example(item):
    """What to say to name an alarm: its label, else its time ("jam 05.00")."""
    if item.get("label"):
        return item["label"]
    return _("example_clock", clock=clock_24(_due(item)))


def timer_example(item):
    return item.get("label") or duration_text(item.get("seconds") or 0)


def which_alarm(alarms, now):
    items = "; ".join(_alarm_item(a, now) for a in alarms)
    return _("which_alarm", items=items, example=alarm_example(alarms[0]))


def which_timer(timers, now):
    items = "; ".join(_timer_item(t, now) for t in timers)
    return _("which_timer", items=items, example=timer_example(timers[0]))


def ask_delete(item, now):
    return _("ask_delete", name=name(item), when=when_short(item, now))


# ------------------------------------------------------------
# The Morning Briefing
# ------------------------------------------------------------

def briefing_sentence(alarms):
    """Today's alarms still to come: "You have an alarm at 14:00: gang war."."""
    if not alarms:
        return ""
    if len(alarms) == 1:
        alarm = alarms[0]
        if alarm.get("label"):
            return _("brief_one", clock=clock_24(_due(alarm)), label=alarm["label"])
        return _("brief_one_plain", clock=clock_24(_due(alarm)))
    items = []
    for alarm in alarms:
        if alarm.get("label"):
            items.append(_("brief_item", clock=clock_24(_due(alarm)), label=alarm["label"]))
        else:
            items.append(clock_24(_due(alarm)))
    return _("brief_many", count=len(alarms), items="; ".join(items))


# ------------------------------------------------------------
# The Preferences list
# ------------------------------------------------------------

def row(item, now, ringing=False):
    """(Name, When or time left, Repeats) for the Preferences list."""
    if ringing:
        when = _("row_ringing")
    elif item["kind"] == "timer":
        left = left_text((_due(item) - now).total_seconds(), precise=True)
        when = _("row_timer_when", left=left, clock=clock_24(_due(item)))
    else:
        due = _due(item)
        when = _("row_alarm_when", day=day_text(due.date(), now.date()), clock=clock_spoken(due))
    repeat = repeat_text(item.get("recurrence", "none"), item.get("interval", 1), _due(item))
    return title(item), when, cap(repeat) if repeat else _("row_no_repeat")
