# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Recording, settings and corrections for Sleep Pattern (no wx).

Each local date holds 1440 minutes, one byte per minute in memory:
  0 unknown  - no data: Hariku wasn't sampling and nothing else tells
  1 inactive - no keyboard or mouse input in that minute
  2 active   - some input in that minute
On disk a day is run-length encoded ("420i15a1005u"). That is all that is
recorded about the user: no keys, no window titles, no apps. A minute only ever
moves up (unknown -> inactive -> active), since any input makes it active.

Time Hariku wasn't sampling is filled in when the next sample arrives:
  * Another boot (the uptime went back, or the boot time moved): the computer
    was shut down or restarted, so nobody used it until it booted -> inactive.
  * Same boot: wall-clock time the awake-only clock didn't count was spent in
    sleep or hibernation -> inactive. The rest (the computer was on but Hariku
    was closed or stalled) -> unknown.
  * Either way, no input came after the last input Windows reports, so the
    minutes after it are inactive, and the minute of that input is active.
"""

import datetime
import itertools
import re

UNKNOWN, INACTIVE, ACTIVE = 0, 1, 2
MINUTES_PER_DAY = 1440
KEEP_DAYS = 90
CONTINUOUS_SECONDS = 180       # samples this close are back to back, no gap
BOOT_TOLERANCE_SECONDS = 300   # boot-time jitter still counted as the same boot
SAVE_SECONDS = 600             # periodic save; the most a killed Hariku loses
ONE_DAY = datetime.timedelta(days=1)
ONE_MINUTE = datetime.timedelta(minutes=1)

_CODES = "uia"
_RUN_RE = re.compile(r"(\d{1,4})([uia])")
_RUNS_RE = re.compile(rb"\x00+|\x01+|\x02+|[^\x00-\x02]+")
_UPGRADE = {state: bytes(max(i, state) if i <= ACTIVE else i for i in range(256))
            for state in (INACTIVE, ACTIVE)}
_generations = itertools.count(1)

# Settings -------------------------------------------------------------------
BEDTIME_CHOICES = (1320, 1350, 1380, 1410, 0, 30, 60, 90, 120)   # 22:00 .. 02:00
MIN_SLEEP_CHOICES = (120, 180, 240)
IGNORE_CHOICES = (0, 5, 10, 15)
DEFAULT_SETTINGS = {
    "enabled": True,          # installing the extension is the opt-in
    "bedtime": 0,             # minutes after midnight
    "min_sleep": 180,
    "ignore_activity": 10,
    "nudge": False,
    "nudge_sound": True,
}
MAX_CORRECTIONS = 200


def parse_date(text):
    try:
        return datetime.datetime.strptime(str(text), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def local_minute(ts):
    """The local minute (naive datetime) that epoch time `ts` falls in."""
    return datetime.datetime.fromtimestamp(ts).replace(second=0, microsecond=0)


# ------------------------------------------------------------
# Samples
# ------------------------------------------------------------

def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value and abs(value) < 1e15 else None


def normalize_sample(raw):
    """A stored sample, or None if it is unusable."""
    if not isinstance(raw, dict):
        return None
    wall, tick, boot, idle = (_number(raw.get(k)) for k in ("wall", "tick", "boot", "idle"))
    if None in (wall, tick, boot, idle) or tick < 0 or idle < 0:
        return None
    awake = _number(raw.get("awake"))
    sample = {"wall": wall, "tick": int(tick), "boot": boot,
              "awake": awake if awake is not None and awake >= 0 else None, "idle": idle}
    if raw.get("final") is True:
        sample["final"] = True
    return sample


def same_boot(prev, now):
    return (now["tick"] >= prev["tick"]
            and abs(now["boot"] - prev["boot"]) <= BOOT_TOLERANCE_SECONDS)


def machine_sleep_seconds(prev, now):
    """Seconds the machine slept or hibernated between two samples of one boot:
    the wall-clock time the awake-only clock did not count."""
    if prev.get("awake") is None or now.get("awake") is None:
        return 0.0
    wall = max(now["wall"] - prev["wall"], 0.0)
    return min(max(wall - (now["awake"] - prev["awake"]), 0.0), wall)


# ------------------------------------------------------------
# Day encoding
# ------------------------------------------------------------

def encode_day(minutes):
    data = bytes(minutes)
    parts = []
    for match in _RUNS_RE.finditer(data):
        start, end = match.span()
        code = data[start]
        parts.append(f"{end - start}{_CODES[code] if code <= ACTIVE else 'u'}")
    return "".join(parts)


def decode_day(text):
    """1440 minutes from encode_day's text, or None if it can't be read."""
    if not isinstance(text, str) or not text:
        return None
    out = bytearray()
    pos = 0
    for match in _RUN_RE.finditer(text):
        if match.start() != pos:
            return None
        pos = match.end()
        out.extend(bytes([_CODES.index(match.group(2))]) * int(match.group(1)))
        if len(out) > MINUTES_PER_DAY:
            return None
    if pos != len(text) or len(out) != MINUTES_PER_DAY:
        return None
    return out


# ------------------------------------------------------------
# Recorder
# ------------------------------------------------------------

class Recorder:
    """The minute-by-minute activity record, and the last sample seen."""

    def __init__(self, days=None, last=None):
        self.days = dict(days or {})      # datetime.date -> bytearray(1440)
        self.last = last
        self.generation = next(_generations)
        self._versions = {}
        self._encoded = {}                # date -> (version, text): only changed days are re-encoded
        self.dirty = False

    # -- reading ---------------------------------------------------------
    def day(self, date):
        return self.days.get(date)

    def version(self, date):
        return self._versions.get(date, 0)

    def has_data(self, date):
        minutes = self.days.get(date)
        return minutes is not None and minutes.count(UNKNOWN) < MINUTES_PER_DAY

    def state_at(self, dt):
        minutes = self.days.get(dt.date())
        return UNKNOWN if minutes is None else minutes[dt.hour * 60 + dt.minute]

    # -- writing ---------------------------------------------------------
    def _touch(self, date):
        self._versions[date] = self._versions.get(date, 0) + 1
        self.dirty = True

    def _raise(self, first, last, state):
        """Move the minutes from `first` to `last` (local, inclusive) up to `state`."""
        table = _UPGRADE[state]
        date = first.date()
        while date <= last.date():
            lo = first.hour * 60 + first.minute if date == first.date() else 0
            hi = last.hour * 60 + last.minute if date == last.date() else MINUTES_PER_DAY - 1
            minutes = self.days.get(date)
            if minutes is None:
                minutes = self.days[date] = bytearray(MINUTES_PER_DAY)
                self._touch(date)
            before = minutes[lo:hi + 1]
            after = before.translate(table)
            if after != before:
                minutes[lo:hi + 1] = after
                self._touch(date)
            date += ONE_DAY

    def mark(self, start_ts, end_ts, state):
        """Every minute overlapping (start_ts, end_ts] moves up to `state`."""
        if end_ts > start_ts:
            self._raise(local_minute(start_ts), local_minute(end_ts), state)

    def mark_minute(self, ts, state):
        minute = local_minute(ts)
        self._raise(minute, minute, state)

    def add_sample(self, now):
        """Record what a new sample says about the time since the previous one."""
        prev, self.last = self.last, {k: v for k, v in now.items() if k != "final"}
        self.dirty = True
        t = now["wall"]
        last_input = t - now["idle"]
        if prev is None or t <= prev["wall"]:
            # First sample, or the clock was set back: only the last minute is known.
            self._observe(t - 60.0, t, last_input)
            return
        since = max(prev["wall"], t - KEEP_DAYS * 86400.0)
        if not same_boot(prev, now):
            self._after_restart(prev, since, now, last_input)
        elif t - since <= CONTINUOUS_SECONDS:
            self._observe(since, t, last_input)
        else:
            self._after_gap(prev, since, now, last_input)

    def _observe(self, since, t, last_input):
        """What the last-input time says about (since, t]."""
        if last_input > since:
            self.mark_minute(last_input, ACTIVE)
            self.mark(last_input, t, INACTIVE)
        else:
            self.mark(since, t, INACTIVE)

    def _after_restart(self, prev, since, now, last_input):
        t = now["wall"]
        boot = min(max(now["boot"], since), t)
        off_from = since
        if not prev.get("final"):
            # Saved by the periodic save, so Hariku may have run up to
            # SAVE_SECONDS longer (killed at shutdown, say): unknown.
            off_from = min(since + SAVE_SECONDS, boot)
        # The computer was off: nobody used it.
        self.mark(off_from, boot, INACTIVE)
        self._observe(boot, t, last_input)

    def _after_gap(self, prev, since, now, last_input):
        t = now["wall"]
        asleep = machine_sleep_seconds(prev, now)
        if last_input > since and asleep > t - last_input:
            # No input is possible while the machine sleeps, so it slept before
            # the last input, which is usually the key press that woke it.
            self.mark(max(since, last_input - asleep), last_input, INACTIVE)
        # Awake time with no sleep behind it stays unknown (Hariku closed or
        # stalled), except after the last input, when nobody touched anything.
        self._observe(since, t, last_input)

    # -- housekeeping ----------------------------------------------------
    def prune(self, today, keep_days=KEEP_DAYS):
        oldest = today - datetime.timedelta(days=keep_days - 1)
        for date in [d for d in self.days if d < oldest or not self.has_data(d)]:
            del self.days[date]
            self._touch(date)

    def clear(self):
        """Forget every recorded minute; the last sample stays, so recording
        simply carries on from now."""
        dates = list(self.days)
        self.days.clear()
        for date in dates:
            self._touch(date)
        self.generation = next(_generations)
        self.dirty = True

    def _encode(self, date):
        version = self.version(date)
        cached = self._encoded.get(date)
        if cached is None or cached[0] != version:
            cached = self._encoded[date] = (version, encode_day(self.days[date]))
        return cached[1]

    def to_data(self, today=None, final=False):
        if today is not None:
            self.prune(today)
        for date in [d for d in self._encoded if d not in self.days]:
            del self._encoded[date]
        last = dict(self.last) if self.last else None
        if last and final:
            last["final"] = True
        return {"version": 1,
                "days": {d.isoformat(): self._encode(d) for d in sorted(self.days)},
                "last": last}

    @classmethod
    def from_data(cls, data, today=None):
        data = data if isinstance(data, dict) else {}
        days, encoded = {}, {}
        raw_days = data.get("days")
        for key, text in (raw_days.items() if isinstance(raw_days, dict) else ()):
            date, minutes = parse_date(key), decode_day(text)
            if date is not None and minutes is not None:
                days[date] = minutes
                encoded[date] = (0, text)
        recorder = cls(days, normalize_sample(data.get("last")))
        recorder._encoded = encoded
        if today is not None:
            recorder.prune(today)
        recorder.dirty = False
        return recorder


# ------------------------------------------------------------
# Settings and corrections
# ------------------------------------------------------------

def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = dict(DEFAULT_SETTINGS)
    for key in ("enabled", "nudge", "nudge_sound"):
        if isinstance(raw.get(key), bool):
            settings[key] = raw[key]
    for key, choices in (("bedtime", BEDTIME_CHOICES), ("min_sleep", MIN_SLEEP_CHOICES),
                         ("ignore_activity", IGNORE_CHOICES)):
        value = raw.get(key)
        if not isinstance(value, bool) and value in choices:
            settings[key] = int(value)
    return settings


def normalize_corrections(raw, today=None):
    """[{"night": "YYYY-MM-DD", "start": epoch, "end": epoch}], oldest first."""
    out = []
    oldest = today - datetime.timedelta(days=KEEP_DAYS) if today is not None else None
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        night = parse_date(item.get("night"))
        start, end = _number(item.get("start")), _number(item.get("end"))
        if night is None or start is None or end is None or end <= start:
            continue
        if oldest is not None and night < oldest:
            continue
        out.append({"night": night.isoformat(), "start": start, "end": end})
    return out[-MAX_CORRECTIONS:]


def corrections_for(corrections, night):
    key = night.isoformat()
    return tuple((c["start"], c["end"]) for c in corrections if c["night"] == key)
