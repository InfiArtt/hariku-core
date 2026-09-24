# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Finding sleep in the activity record (pure functions, no wx).

A night is labelled by the morning's date D and runs from 18:00 on D-1 to
18:00 on D. Detection reads the 48 hours around it (06:00 on D-1 to 06:00 on
D+1), so a sleep that crosses 18:00 is seen whole; a block belongs to the
night that holds its midpoint.

1. Stretches: runs of at least MIN_STRETCH inactive minutes.
2. Blocks: neighbouring stretches merge when what lies between them has at
   most `ignore_activity` active minutes (checking the time at 3 a.m.) and at
   most MAX_UNKNOWN_BRIDGE unknown minutes. Unknown time is never counted as
   sleep, and never as awake: a sleep doesn't end because Hariku missed a few
   minutes, so a block may span a short unknown stretch, but a longer one
   breaks the block, because the sleep may well have ended inside it.
3. The main sleep is the block with the most inactive minutes, if it has at
   least `min_sleep`. Other blocks of MIN_NAP minutes or more that start
   between 09:00 and 18:00 are naps. A block over MAX_SLEEP_SPAN is not sleep:
   the computer was off or untouched for too long to tell.
4. Time asleep is the block's inactive minutes; brief activity and unknown
   minutes inside it are left out.
5. A night reports "not enough data" instead of guessing when less than half
   of it is known, or when an unknown stretch is as long as the sleep found
   (or, with no sleep found, as long as the shortest sleep that counts).

Local dates and clock times are naive local datetimes; the record is kept per
local date, so a DST change (Indonesia has none) shifts one hour at most.
"""

import datetime
import re

from sleep_tracker_store import ACTIVE, INACTIVE, MINUTES_PER_DAY, UNKNOWN

FUTURE = 3                                  # minutes after "now" in a running night
ONE_DAY = datetime.timedelta(days=1)
NIGHT_START_MINUTE = 18 * 60                # nights run from 18:00 to 18:00
TIMELINE_MINUTES = 2 * MINUTES_PER_DAY      # 06:00 on D-1 to 06:00 on D+1
MAIN_FROM = 12 * 60                         # 18:00 on D-1, as a timeline index
MAIN_TO = MAIN_FROM + MINUTES_PER_DAY       # 18:00 on D
MIN_STRETCH = 15
MAX_UNKNOWN_BRIDGE = 15
MIN_NAP = 90
NAP_FROM_OFFSET = 15 * 60                   # 09:00 on D, in minutes after 18:00
DAYTIME_FROM_OFFSET = 12 * 60               # 06:00 on D
MAX_SLEEP_SPAN = 16 * 60
MIN_KNOWN_SHARE = 0.5
COMPARE_MIN_NIGHTS = 2

_STRETCH_RE = re.compile(b"\x01{%d,}" % MIN_STRETCH)
_UNKNOWN_RE = re.compile(b"\x00+")
_ACTIVE_RE = re.compile(b"\x02+")
_FUTURE_BYTE = bytes([FUTURE])


# ------------------------------------------------------------
# Time helpers
# ------------------------------------------------------------

def night_start(night):
    """18:00 on the evening before `night` (the morning's date)."""
    return datetime.datetime.combine(night - ONE_DAY, datetime.time(18, 0))


def timeline_start(night):
    return night_start(night) - datetime.timedelta(hours=12)


def night_of(dt):
    """The night (the morning's date) that local time `dt` belongs to."""
    return dt.date() + ONE_DAY if dt.hour >= 18 else dt.date()


def offset_in_night(dt, night):
    """Minutes from 18:00 on the evening before `night` to `dt`."""
    return int((dt - night_start(night)).total_seconds() // 60)


def bedtime_offset(bedtime_minute):
    """A bedtime (minutes after midnight) as minutes after 18:00."""
    return (int(bedtime_minute) - NIGHT_START_MINUTE) % MINUTES_PER_DAY


def clock_minute(offset):
    """Minutes after 18:00 back to minutes after midnight."""
    return (NIGHT_START_MINUTE + int(round(offset))) % MINUTES_PER_DAY


def future_cutoff(night, now):
    """Timeline index of the first minute after `now`, or None when the whole
    48 hours are over. The current minute counts as recorded."""
    if now is None:
        return None
    minute = now.replace(second=0, microsecond=0)
    index = int((minute - timeline_start(night)).total_seconds() // 60) + 1
    return None if index >= TIMELINE_MINUTES else max(0, index)


# ------------------------------------------------------------
# Timeline and blocks
# ------------------------------------------------------------

def build_timeline(day, night, cutoff=None):
    """The 48 hours around `night`; `day(date)` returns a date's 1440 minutes
    or None. Minutes from `cutoff` on are FUTURE."""
    parts = []
    for date, lo, hi in ((night - ONE_DAY, 360, MINUTES_PER_DAY), (night, 0, MINUTES_PER_DAY),
                         (night + ONE_DAY, 0, 360)):
        minutes = day(date)
        parts.append(bytes(minutes[lo:hi]) if minutes is not None else bytes(hi - lo))
    timeline = bytearray(b"".join(parts))
    if cutoff is not None:
        timeline[cutoff:] = _FUTURE_BYTE * (TIMELINE_MINUTES - cutoff)
    return timeline


def window_has_data(day, night):
    """True if anything is known about the 24 hours of `night`."""
    for date, lo, hi in ((night - ONE_DAY, NIGHT_START_MINUTE, MINUTES_PER_DAY),
                         (night, 0, NIGHT_START_MINUTE)):
        minutes = day(date)
        if minutes is not None and minutes[lo:hi].count(UNKNOWN) < hi - lo:
            return True
    return False


def find_blocks(timeline, ignore_activity):
    """(start, end) timeline indexes of merged inactive blocks, in order."""
    blocks = []
    for match in _STRETCH_RE.finditer(timeline):
        start, end = match.span()
        if blocks:
            between = timeline[blocks[-1][1]:start]
            if (FUTURE not in between and between.count(ACTIVE) <= ignore_activity
                    and between.count(UNKNOWN) <= MAX_UNKNOWN_BRIDGE):
                blocks[-1][1] = end
                continue
        blocks.append([start, end])
    return [(start, end) for start, end in blocks]


def _block_info(timeline, start, end, base):
    part = timeline[start:end]
    return {
        "start": base + datetime.timedelta(minutes=start),
        "end": base + datetime.timedelta(minutes=end),
        "asleep": part.count(INACTIVE),
        "awake": part.count(ACTIVE),
        "unknown": part.count(UNKNOWN),
        "wakeups": len(_ACTIVE_RE.findall(part)),
        "index": (start, end),
    }


def _correction_indexes(corrections, base):
    out = []
    for start_ts, end_ts in corrections:
        try:
            start = datetime.datetime.fromtimestamp(start_ts)
            end = datetime.datetime.fromtimestamp(end_ts)
        except (OverflowError, OSError, ValueError):
            continue
        out.append(((start - base).total_seconds() / 60, (end - base).total_seconds() / 60))
    return out


def _is_corrected(start, end, marks):
    # Matched by overlap, so a block that grew or shrank a little when later
    # data came in is still the one the user marked.
    for mark_start, mark_end in marks:
        overlap = min(end, mark_end) - max(start, mark_start)
        if overlap > 0 and overlap >= 0.5 * min(end - start, mark_end - mark_start):
            return True
    return False


def analyze_night(timeline, night, settings, corrections=()):
    """What the 48-hour `timeline` says about `night`. `corrections` are
    (start, end) epoch pairs of blocks the user marked as not sleep.

    status is "sleep", "no_data", "no_sleep", "away" (inactive far too long),
    "corrected" (the only block found was marked as not sleep) or "ongoing"
    (a running night whose latest block hasn't ended)."""
    base = timeline_start(night)
    min_sleep = settings["min_sleep"]
    cutoff = timeline.find(_FUTURE_BYTE)
    marks = _correction_indexes(corrections, base)

    candidates, corrected = [], []
    away = None
    ongoing = False
    for start, end in find_blocks(timeline, settings["ignore_activity"]):
        if cutoff >= 0 and end >= cutoff:
            ongoing = ongoing or end > MAIN_FROM
            continue
        if end - start > MAX_SLEEP_SPAN:
            overlap = min(end, MAIN_TO) - max(start, MAIN_FROM)
            if overlap >= min_sleep and (away is None or end - start > away["index"][1] - away["index"][0]):
                away = _block_info(timeline, start, end, base)
            continue
        if not MAIN_FROM <= (start + end) / 2 < MAIN_TO:
            continue
        info = _block_info(timeline, start, end, base)
        (corrected if _is_corrected(start, end, marks) else candidates).append(info)

    window = timeline[MAIN_FROM:MAIN_TO]
    elapsed = MINUTES_PER_DAY - window.count(FUTURE)
    known = elapsed - window.count(UNKNOWN)
    longest_unknown = max((m.end() - m.start() for m in _UNKNOWN_RE.finditer(window)), default=0)
    enough = elapsed > 0 and known >= MIN_KNOWN_SHARE * elapsed

    sleeps = [b for b in candidates if b["asleep"] >= min_sleep]
    main = max(sleeps, key=lambda b: (b["asleep"], -b["index"][0])) if sleeps else None
    if main is not None and (not enough or longest_unknown >= main["asleep"]):
        main = None
        status = "no_data"
    elif main is not None:
        status = "sleep"
    elif away is not None:
        status = "away"
    elif ongoing:
        status = "ongoing"
    elif corrected:
        status = "corrected"
    elif not enough or longest_unknown >= min_sleep:
        status = "no_data"
    else:
        status = "no_sleep"

    naps = []
    if main is not None:
        naps = sorted((b for b in candidates if b is not main and b["asleep"] >= MIN_NAP
                       and b["index"][0] - MAIN_FROM >= NAP_FROM_OFFSET),
                      key=lambda b: b["index"][0])
    start_offset = main["index"][0] - MAIN_FROM if main else None
    return {
        "night": night,
        "status": status,
        "main": main,
        "naps": naps,
        "late": main is not None and start_offset > bedtime_offset(settings["bedtime"]),
        "daytime": main is not None and start_offset >= DAYTIME_FROM_OFFSET,
        "corrected": corrected,
        "away": away,
        "known": known,
        "elapsed": elapsed,
        "in_progress": cutoff >= 0,
        "bedtime": settings["bedtime"],
    }


# ------------------------------------------------------------
# Several nights
# ------------------------------------------------------------

class Nights:
    """Per-night results, cached until the minutes, settings or corrections
    behind them change (or, for a running night, until the next minute)."""

    def __init__(self):
        self._cache = {}

    def clear(self):
        self._cache.clear()

    def forget_before(self, date):
        for night in [n for n in self._cache if n < date]:
            del self._cache[night]

    def get(self, recorder, night, settings, corrections, now):
        cutoff = future_cutoff(night, now)
        key = (recorder.generation, recorder.version(night - ONE_DAY), recorder.version(night),
               recorder.version(night + ONE_DAY), settings["min_sleep"],
               settings["ignore_activity"], settings["bedtime"], tuple(corrections), cutoff)
        hit = self._cache.get(night)
        if hit is not None and hit[0] == key:
            return hit[1]
        timeline = build_timeline(recorder.day, night, cutoff)
        result = analyze_night(timeline, night, settings, corrections)
        self._cache[night] = (key, result)
        return result


def last_night(get, now):
    """The most recent night with a finished sleep: the running night once its
    sleep is over, otherwise the night before. `get(night)` returns a result."""
    current = night_of(now)
    result = get(current)
    if result["status"] == "sleep":
        return result
    return get(current - ONE_DAY)


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _median(values):
    values = sorted(values)
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def summary(results, last):
    """Averages over the 7 and 30 nights up to `last`. `results` maps nights to
    results; nights without a detected sleep are left out. Bedtime and wake
    time are medians ("usually"), so one all-nighter doesn't move them hours."""
    def slept(days):
        found = []
        for i in range(days):
            result = results.get(last - datetime.timedelta(days=i))
            if result is not None and result["status"] == "sleep":
                found.append(result)
        return found

    week, month = slept(7), slept(30)
    bed = _median(offset_in_night(r["main"]["start"], r["night"]) for r in week)
    wake = _median(offset_in_night(r["main"]["end"], r["night"]) for r in week)
    return {
        "week_nights": len(week),
        "month_nights": len(month),
        "week_average": _mean(r["main"]["asleep"] for r in week),
        "month_average": _mean(r["main"]["asleep"] for r in month),
        "bedtime": None if bed is None else clock_minute(bed),
        "wake": None if wake is None else clock_minute(wake),
        "late_nights": sum(1 for r in week if r["late"]),
    }


def compare_to_week(result, results):
    """Minutes slept more (+) or less (-) than the average of the 7 nights
    before, or None without a sleep or with fewer than 2 nights to compare."""
    if result.get("status") != "sleep":
        return None
    previous = []
    for i in range(1, 8):
        other = results.get(result["night"] - datetime.timedelta(days=i))
        if other is not None and other["status"] == "sleep":
            previous.append(other["main"]["asleep"])
    if len(previous) < COMPARE_MIN_NIGHTS:
        return None
    return result["main"]["asleep"] - _mean(previous)
