# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The alarms and timers Timer & Alarm keeps, and its settings. No wx here.

Every item has an absolute due time, so it survives a restart:

    {"id": "3f9a1c2e40b1", "kind": "alarm" or "timer", "label": "gang war",
     "due": "2026-09-26T02:00:00", "created": "...",
     "recurrence": "none"|"daily"|"weekly"|"monthly"|"yearly", "interval": 1,
     "start": "...", "anchor_day": 31,     (repeating alarms)
     "seconds": 180}                         (timers: how long they ran)

In memory `due`, `created` and `start` are datetimes. The data is saved with
core.api.save_data (atomic, with a .bak) under DATA_KEY; this module only turns
it into plain JSON and back, checking everything it reads.

When an item comes due (pop_due), a one-off alarm or a timer leaves the list
(it rings, then it is gone; a snooze adds it back) and a repeating alarm moves
to its next time. `missed` holds rings nobody stopped and items that came due
while Hariku was closed, until they have been said once.
"""

import calendar
import datetime
import uuid

DATA_KEY = "TimerAlarm"
KINDS = ("alarm", "timer")
RECURRENCES = ("none", "daily", "weekly", "monthly", "yearly")
RING_CHOICES = (1, 2, 3, 5, 10, 15)                    # minutes
SNOOZE_CHOICES = (1, 2, 3, 5, 10, 15, 20, 30)          # minutes
DEFAULT_SETTINGS = {
    "alarm_sound": "windows:Alarm01.wav",
    "timer_sound": "windows:Alarm02.wav",
    "ring_minutes": 3,
    "snooze_minutes": 5,
}
MAX_ITEMS = 200
MAX_MISSED = 20
MAX_LABEL = 80
MAX_TIMER_SECONDS = 24 * 3600
MAX_INTERVAL = 999


def _parse_time(value):
    if isinstance(value, datetime.datetime):
        return value.replace(microsecond=0)
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.fromisoformat(value).replace(microsecond=0, tzinfo=None)
    except ValueError:
        return None


def _iso(moment):
    return moment.replace(microsecond=0).isoformat() if moment else None


def new_id():
    return uuid.uuid4().hex[:12]


# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------

def is_sound_choice(value):
    """ "windows:Alarm01.wav" ... "windows:Ring10.wav", "tone:alarm" or "tone:timer".
    Only these names: a setting can never point Hariku at another file."""
    if value in ("tone:alarm", "tone:timer"):
        return True
    if not isinstance(value, str) or not value.startswith("windows:"):
        return False
    name = value[len("windows:"):]
    for prefix in ("Alarm", "Ring"):
        if name.startswith(prefix) and name.endswith(".wav"):
            number = name[len(prefix):-4]
            return number.isdigit() and len(number) == 2 and 1 <= int(number) <= 10
    return False


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = dict(DEFAULT_SETTINGS)
    for key in ("alarm_sound", "timer_sound"):
        if is_sound_choice(raw.get(key)):
            settings[key] = raw[key]
    if raw.get("ring_minutes") in RING_CHOICES:
        settings["ring_minutes"] = raw["ring_minutes"]
    if raw.get("snooze_minutes") in SNOOZE_CHOICES:
        settings["snooze_minutes"] = raw["snooze_minutes"]
    return settings


# ------------------------------------------------------------
# Items
# ------------------------------------------------------------

def make_alarm(due, label="", recurrence="none", interval=1, anchor_day=None, now=None):
    now = (now or datetime.datetime.now()).replace(microsecond=0)
    recurrence = recurrence if recurrence in RECURRENCES else "none"
    item = {"id": new_id(), "kind": "alarm", "label": _clean_label(label),
            "due": due.replace(second=0, microsecond=0), "created": now,
            "recurrence": recurrence, "interval": 1}
    if recurrence != "none":
        item["interval"] = max(1, min(MAX_INTERVAL, int(interval or 1)))
        item["start"] = item["due"]
        if recurrence in ("monthly", "yearly"):
            item["anchor_day"] = anchor_day if isinstance(anchor_day, int) and 1 <= anchor_day <= 31 \
                else item["due"].day
    return item


def make_timer(seconds, label="", now=None):
    now = (now or datetime.datetime.now()).replace(microsecond=0)
    seconds = max(1, min(MAX_TIMER_SECONDS, int(seconds)))
    return {"id": new_id(), "kind": "timer", "label": _clean_label(label),
            "due": now + datetime.timedelta(seconds=seconds), "created": now,
            "recurrence": "none", "interval": 1, "seconds": seconds}


def _clean_label(label):
    label = " ".join(str(label or "").split())
    return label[:MAX_LABEL]


def normalize_item(raw):
    """An item read from disk, checked, with datetimes; None when unusable."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    due = _parse_time(raw.get("due"))
    if kind not in KINDS or due is None:
        return None
    item_id = raw.get("id")
    if not isinstance(item_id, str) or not item_id or len(item_id) > 40:
        item_id = new_id()
    item = {"id": item_id, "kind": kind, "label": _clean_label(raw.get("label")), "due": due,
            "created": _parse_time(raw.get("created")) or due, "recurrence": "none",
            "interval": 1}
    if kind == "timer":
        seconds = raw.get("seconds")
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not \
                1 <= seconds <= MAX_TIMER_SECONDS:
            seconds = max(1, int((due - item["created"]).total_seconds()))
        item["seconds"] = min(seconds, MAX_TIMER_SECONDS)
        return item
    recurrence = raw.get("recurrence")
    if recurrence in RECURRENCES and recurrence != "none":
        interval = raw.get("interval")
        item["recurrence"] = recurrence
        item["interval"] = interval if isinstance(interval, int) and not isinstance(interval, bool) \
            and 1 <= interval <= MAX_INTERVAL else 1
        item["start"] = _parse_time(raw.get("start")) or due
        if recurrence in ("monthly", "yearly"):
            anchor = raw.get("anchor_day")
            item["anchor_day"] = anchor if isinstance(anchor, int) and not isinstance(anchor, bool) \
                and 1 <= anchor <= 31 else item["start"].day
    return item


def item_to_data(item):
    data = {"id": item["id"], "kind": item["kind"], "label": item.get("label", ""),
            "due": _iso(item["due"]), "created": _iso(item.get("created")),
            "recurrence": item.get("recurrence", "none"), "interval": item.get("interval", 1)}
    if item["kind"] == "timer":
        data["seconds"] = item.get("seconds", 0)
    if item.get("start"):
        data["start"] = _iso(item["start"])
    if item.get("anchor_day"):
        data["anchor_day"] = item["anchor_day"]
    return data


def copy_item(item):
    return dict(item)


# ------------------------------------------------------------
# Repeats
# ------------------------------------------------------------

def _add_months(moment, months, anchor):
    index = moment.month - 1 + months
    year, month = moment.year + index // 12, index % 12 + 1
    day = min(anchor, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def next_occurrence(item, after):
    """The first time after `after` a repeating alarm rings, counted in whole
    steps from its start (so a monthly alarm on the 31st keeps the 31st after
    February, and missed ones are skipped, not rung one by one)."""
    recurrence = item.get("recurrence", "none")
    start = item.get("start") or item["due"]
    if recurrence == "none":
        return None
    interval = max(1, int(item.get("interval") or 1))
    anchor = item.get("anchor_day") or start.day

    def step(k):
        if recurrence == "daily":
            return start + datetime.timedelta(days=interval * k)
        if recurrence == "weekly":
            return start + datetime.timedelta(weeks=interval * k)
        if recurrence == "monthly":
            return _add_months(start, interval * k, anchor)
        return _add_months(start, 12 * interval * k, anchor)

    # Jump close first, then walk: an alarm unused for years stays cheap.
    k = 0
    if recurrence in ("daily", "weekly") and after > start:
        span = datetime.timedelta(days=interval * (1 if recurrence == "daily" else 7))
        k = max(0, int((after - start) / span) - 1)
    elif recurrence in ("monthly", "yearly") and after > start:
        months = (after.year - start.year) * 12 + after.month - start.month
        k = max(0, months // (interval * (1 if recurrence == "monthly" else 12)) - 1)
    moment = step(k)
    guard = 0
    while moment <= after and guard < 1000:
        k += 1
        guard += 1
        moment = step(k)
    return moment


# ------------------------------------------------------------
# The schedule
# ------------------------------------------------------------

class Schedule:
    def __init__(self, items=None, missed=None, settings=None):
        self.items = list(items or [])
        self.missed = list(missed or [])        # [{"item", "reason", "at"}]
        self.settings = normalize_settings(settings)

    # --- saving -----------------------------------------------------------------

    @classmethod
    def from_data(cls, data):
        data = data if isinstance(data, dict) else {}
        items = []
        seen = set()
        for raw in data.get("items") or []:
            item = normalize_item(raw)
            if item is not None and item["id"] not in seen:
                seen.add(item["id"])
                items.append(item)
        missed = []
        for raw in data.get("missed") or []:
            if not isinstance(raw, dict):
                continue
            item = normalize_item(raw.get("item"))
            if item is not None:
                missed.append({"item": item, "reason": "closed" if raw.get("reason") == "closed"
                               else "missed"})
        return cls(items[:MAX_ITEMS], missed[-MAX_MISSED:], data.get("settings"))

    def to_data(self):
        return {"version": 1,
                "items": [item_to_data(i) for i in self.items],
                "missed": [{"item": item_to_data(m["item"]), "reason": m["reason"]}
                           for m in self.missed],
                "settings": dict(self.settings)}

    # --- items ------------------------------------------------------------------

    def add(self, item):
        if len(self.items) >= MAX_ITEMS:
            return False
        self.items.append(item)
        return True

    def get(self, item_id):
        return next((i for i in self.items if i["id"] == item_id), None)

    def remove(self, item_id):
        item = self.get(item_id)
        if item is not None:
            self.items.remove(item)
        return item

    def alarms(self):
        return sorted((i for i in self.items if i["kind"] == "alarm"), key=lambda i: i["due"])

    def timers(self):
        return sorted((i for i in self.items if i["kind"] == "timer"), key=lambda i: i["due"])

    def ordered(self):
        return self.alarms() + self.timers()

    def find_same_alarm(self, due, label, recurrence):
        for item in self.items:
            if (item["kind"] == "alarm" and item["due"] == due
                    and (item.get("label") or "").casefold() == (label or "").casefold()
                    and item.get("recurrence", "none") == recurrence):
                return item
        return None

    def next_due(self):
        return min((i["due"] for i in self.items), default=None)

    # --- coming due -------------------------------------------------------------

    def pop_due(self, now):
        """The items due at `now`, as copies to ring (or to report missed).
        One-offs leave the list; repeating alarms move to their next time."""
        fired = []
        for item in sorted(self.items, key=lambda i: i["due"]):
            if item["due"] > now:
                continue
            fired.append(copy_item(item))
            if item.get("recurrence", "none") == "none":
                self.items.remove(item)
            else:
                item["due"] = next_occurrence(item, now)
        return fired

    def add_missed(self, item, reason="missed"):
        self.missed.append({"item": copy_item(item), "reason": reason})
        del self.missed[:-MAX_MISSED]

    def take_missed(self):
        missed, self.missed = self.missed, []
        return missed

    def todays_alarms(self, now):
        """Alarms still to come today, earliest first."""
        return [a for a in self.alarms() if a["due"].date() == now.date() and a["due"] >= now]


def start_up(schedule, now, ring_seconds):
    """What to do with items that came due while Hariku was closed: those
    within the ring length still ring (returned), older ones are missed
    ("closed", said once); repeating alarms move on either way."""
    to_ring = []
    for item in schedule.pop_due(now):
        if (now - item["due"]).total_seconds() <= ring_seconds:
            to_ring.append(item)
        else:
            schedule.add_missed(item, "closed")
    return to_ring
