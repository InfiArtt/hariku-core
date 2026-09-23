# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
When to announce an earthquake. Pure logic, no wx and no text.

BMKG's latest quake is checked every time it is fetched:
  * "tsunami": BMKG's Potensi mentions tsunami potential. Always announced
    (when the setting is on, as it is by default), wherever the quake is.
  * "nearby":  within the alert distance and at least the minimum magnitude.
  * "felt":    BMKG's felt report (Dirasakan) names the user's region.
Each quake is announced once. The one exception is safety: when BMKG later
adds tsunami potential to a quake already announced (or heard through the
hotkey), the tsunami alert is still given. BMKG often adds felt reports after
its first release, so a quake that did not qualify yet is checked again on
every poll while it is recent.

USGS worldwide alerts (M6.5+, opt-in) skip quakes already announced from BMKG,
and BMKG's nearby and felt alerts skip quakes already announced from USGS.

Quakes older than an hour (three for tsunami potential) are never announced,
so starting Hariku does not replay old news. The records survive a restart.
"""

import earthquake_api as api

ALERT_MAX_AGE = 3600
TSUNAMI_MAX_AGE = 3 * 3600
FUTURE_TOLERANCE = 24 * 3600   # the computer's clock may be behind
KEEP_SECONDS = 3 * 86400
MAX_RECORDS = 200


def is_recent(quake, max_age, now):
    when = quake.get("time")
    if when is None:
        return False
    age = now - when
    return -FUTURE_TOLERANCE <= age <= max_age


def tsunami_match(quake, settings):
    return bool(settings.get("tsunami_alerts")) and api.is_tsunami_potential(quake.get("potential"))


def nearby_match(quake, settings, location):
    if not settings.get("nearby_alerts") or not location:
        return False
    found = api.distance_from(location, quake)
    if found is None or quake.get("magnitude") is None:
        return False
    return (found[0] <= settings["alert_km"]
            and quake["magnitude"] >= settings["min_magnitude"] - 1e-9)


def felt_match(quake, settings, location):
    if not settings.get("felt_alerts"):
        return False
    names = api.region_names(location, settings.get("felt_names", ""))
    return bool(names) and api.felt_in_region(quake.get("felt"), names)


class AlertTracker:
    """What has been announced, per source and quake id."""

    def __init__(self):
        self.records = {"bmkg": {}, "usgs": {}}
        self.changed = False

    # --- records ------------------------------------------------------------

    def _record(self, quake):
        records = self.records[quake["source"]]
        record = records.get(quake["id"])
        if record is None:
            record = records[quake["id"]] = {"announced": False, "tsunami": False}
            self.changed = True
        position = {"t": quake.get("time"), "lat": quake.get("lat"), "lon": quake.get("lon")}
        if any(record.get(k) != v for k, v in position.items()):
            record.update(position)   # BMKG revised the quake
            self.changed = True
        return record

    def _set(self, record, **values):
        for key, value in values.items():
            if record.get(key) != value:
                record[key] = value
                self.changed = True

    def _announced_in(self, source, quake):
        """True when a quake announced from `source` is the same event."""
        for record in self.records[source].values():
            if record.get("announced") and api.same_event(
                    quake, {"time": record.get("t"), "lat": record.get("lat"),
                            "lon": record.get("lon")}):
                return True
        return False

    def heard(self, quake):
        """The user just heard this quake (the hotkey): no alert repeats it,
        unless BMKG later adds tsunami potential."""
        record = self._record(quake)
        self._set(record, announced=True)
        if quake["source"] == "bmkg" and api.is_tsunami_potential(quake.get("potential")):
            self._set(record, tsunami=True)

    # --- decisions ----------------------------------------------------------

    def check_bmkg(self, quake, settings, location, now):
        """"tsunami", "nearby", "felt" or None, and remember it."""
        record = self._record(quake)
        if (tsunami_match(quake, settings) and not record["tsunami"]
                and is_recent(quake, TSUNAMI_MAX_AGE, now)):
            self._set(record, tsunami=True, announced=True)
            return "tsunami"
        if record["announced"] or not is_recent(quake, ALERT_MAX_AGE, now):
            return None
        if nearby_match(quake, settings, location):
            reason = "nearby"
        elif felt_match(quake, settings, location):
            reason = "felt"
        else:
            return None
        self._set(record, announced=True)
        if self._announced_in("usgs", quake):
            return None   # already heard as a worldwide alert
        return reason

    def check_usgs(self, quakes, settings, now):
        """The USGS quakes to announce as worldwide alerts, and remember them."""
        if not settings.get("world_alerts"):
            return []
        new = []
        for quake in quakes:
            if quake["magnitude"] < api.WORLD_ALERT_MAGNITUDE - 1e-9:
                continue
            record = self._record(quake)
            if record["announced"] or not is_recent(quake, ALERT_MAX_AGE, now):
                continue
            self._set(record, announced=True)
            if not self._announced_in("bmkg", quake):
                new.append(quake)
        return new

    # --- persistence --------------------------------------------------------

    def prune(self, now):
        for source, records in self.records.items():
            keep = {}
            for ident, record in records.items():
                when = record.get("t")
                if when is None or now - when <= KEEP_SECONDS:
                    keep[ident] = record
            if len(keep) > MAX_RECORDS:
                newest = sorted(keep.items(), key=lambda item: item[1].get("t") or 0,
                                reverse=True)[:MAX_RECORDS]
                keep = dict(newest)
            if len(keep) != len(records):
                self.records[source] = keep
                self.changed = True

    def to_json(self):
        return {"bmkg": dict(self.records["bmkg"]), "usgs": dict(self.records["usgs"])}

    @classmethod
    def from_json(cls, raw):
        tracker = cls()
        raw = raw if isinstance(raw, dict) else {}
        for source in ("bmkg", "usgs"):
            records = raw.get(source)
            if not isinstance(records, dict):
                continue
            for ident, record in records.items():
                if not isinstance(ident, str) or not isinstance(record, dict):
                    continue
                lat, lon = api.to_float(record.get("lat")), api.to_float(record.get("lon"))
                tracker.records[source][ident] = {
                    "announced": record.get("announced") is True,
                    "tsunami": record.get("tsunami") is True,
                    "t": api.to_float(record.get("t")),
                    "lat": lat if lon is not None else None,
                    "lon": lon if lat is not None else None,
                }
        return tracker
