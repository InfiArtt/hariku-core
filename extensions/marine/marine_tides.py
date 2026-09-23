# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
High and low tides from Open-Meteo's hourly sea level (sea_level_height_msl,
metres above mean sea level, one value per hour in the place's local time).

A tide is a turning point of that series. Two things make the obvious "higher
than both neighbours" test wrong on real data, so it is not used:
  * the values are rounded to centimetres, so the top of a tide is often two
    equal hours (0.92, 0.92), and
  * the model wobbles by a centimetre or two on the way up or down.
Instead the series is followed with hysteresis: a high only counts once the
water has fallen at least MIN_TIDE_RANGE below it (and a low once it has risen
that much), and each swing keeps its most extreme hour. Runs of equal values
count as one point in their middle. The turning point is then placed between
the hours with a parabola through it and its neighbours, since tides rarely
turn exactly on the hour.

The first and last swing of the data can't be confirmed and are left out; the
request asks for yesterday too, so the tides around "now" are always complete.
"""

import datetime

MIN_TIDE_RANGE = 0.05   # metres; smaller wobbles are not tides
ONE_HOUR = datetime.timedelta(hours=1)


def parse_hour(text):
    """'2026-09-23T14:00' -> datetime, or None."""
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def _level(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _segments(sea_level):
    """Runs of consecutive hours with a value. A missing value or a gap in the
    hours starts a new run, so a tide is never invented across missing data."""
    segment, previous = [], None
    for item in sea_level or []:
        try:
            when, level = parse_hour(item[0]), _level(item[1])
        except (TypeError, IndexError, KeyError):
            when = level = None
        if when is None or level is None or (previous is not None and when - previous != ONE_HOUR):
            if len(segment) > 0:
                yield segment
            segment = []
        if when is not None and level is not None:
            segment.append((when, level))
            previous = when
        else:
            previous = None
    if segment:
        yield segment


def _runs(segment):
    """[first index, last index, value] for each run of equal values."""
    runs = []
    for i, (_when, level) in enumerate(segment):
        if runs and abs(runs[-1][2] - level) < 1e-9:
            runs[-1][1] = i
        else:
            runs.append([i, i, level])
    return runs


def _turning_points(runs, min_range):
    """[(run index, "high" | "low")] with hysteresis (see the module docstring)."""
    found = []
    mode, low, high, candidate = None, 0, 0, 0
    for k in range(1, len(runs)):
        value = runs[k][2]
        if mode is None:
            # Until the water has moved min_range, the direction is unknown and
            # the first point can't be a confirmed tide.
            if value > runs[high][2]:
                high = k
            if value < runs[low][2]:
                low = k
            if runs[high][2] - runs[low][2] >= min_range:
                mode, candidate = ("rising", high) if high > low else ("falling", low)
        elif mode == "rising":
            if value > runs[candidate][2]:
                candidate = k
            elif runs[candidate][2] - value >= min_range:
                found.append((candidate, "high"))
                mode, candidate = "falling", k
        else:
            if value < runs[candidate][2]:
                candidate = k
            elif value - runs[candidate][2] >= min_range:
                found.append((candidate, "low"))
                mode, candidate = "rising", k
    return found


def _turning_time(segment, run):
    """When the water turns: between the hours for a single-hour extreme, the
    middle of a run of equal values."""
    first, last, level = run
    when = segment[first][0]
    if first != last:
        return when + (last - first) * ONE_HOUR / 2
    if 0 < first < len(segment) - 1:
        before, after = segment[first - 1][1], segment[first + 1][1]
        curve = before - 2 * level + after
        if abs(curve) > 1e-12:
            shift = max(-0.5, min(0.5, 0.5 * (before - after) / curve))
            return when + shift * ONE_HOUR
    return when


def find_tides(sea_level, min_range=MIN_TIDE_RANGE):
    """[{"time": datetime, "level": metres, "kind": "high" | "low"}], in time
    order, from [[hour string, metres or None], ...]."""
    tides = []
    for segment in _segments(sea_level):
        runs = _runs(segment)
        for index, kind in _turning_points(runs, min_range):
            run = runs[index]
            tides.append({"time": _turning_time(segment, run), "level": run[2], "kind": kind})
    tides.sort(key=lambda t: t["time"])
    return tides


def upcoming(tides, now):
    """The tides after `now` (a naive local datetime), in order."""
    return [t for t in tides if t["time"] > now]


def next_tide(tides, now, kind):
    for tide in upcoming(tides, now):
        if tide["kind"] == kind:
            return tide
    return None


def trend(tides, now):
    """"rising" if the next tide is a high, "falling" if it is a low, else None."""
    ahead = upcoming(tides, now)
    if not ahead:
        return None
    return "rising" if ahead[0]["kind"] == "high" else "falling"


def round_time(when, minutes=10):
    """`when` to the nearest `minutes` (it may move to the next day)."""
    base = when.replace(second=0, microsecond=0) - datetime.timedelta(minutes=when.minute)
    total = when.minute + when.second / 60 + when.microsecond / 60e6
    return base + datetime.timedelta(minutes=int(total / minutes + 0.5) * minutes)
