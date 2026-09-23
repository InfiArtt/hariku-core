# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# ============================================================
# Lightweight iCalendar (.ics) Parser for Hariku V2
# ============================================================
# Parses VEVENT components from iCalendar files downloaded from
# Google Calendar's private iCal URL. No external dependencies.
#
# Supported fields:
#   UID, SUMMARY, DESCRIPTION, LOCATION, DTSTART, DTEND,
#   RRULE, STATUS, TRANSP (free/busy)
# ============================================================

import logging
import urllib.request
import ssl
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


# ============================================================
# ICS Text Parsing
# ============================================================

def _unfold_lines(text):
    """
    iCalendar spec (RFC 5545) allows long lines to be 'folded' by
    inserting a CRLF followed by a whitespace character. This function
    unfolds them back into single logical lines.
    """
    lines = []
    for raw_line in text.splitlines():
        if raw_line.startswith((" ", "\t")) and lines:
            # Continuation of the previous line
            lines[-1] += raw_line[1:]
        else:
            lines.append(raw_line)
    return lines


def _parse_dt(value, params=None):
    """
    Parse a DATE or DATE-TIME value from an iCal property.

    Handles:
      - DATE:          20261225
      - DATE-TIME:     20261225T180000
      - DATE-TIME UTC: 20261225T110000Z
      - With TZID param (timezone is noted but not converted)

    Returns a dict with:
      - 'dt': datetime or date object
      - 'all_day': True if the value was a DATE (no time component)
      - 'tzid': timezone string if present, else None
    """
    params = params or {}
    tzid = params.get("TZID")
    value = value.strip()

    # Pure date (8 digits): YYYYMMDD
    if len(value) == 8 and value.isdigit():
        return {
            "dt": datetime.strptime(value, "%Y%m%d").date(),
            "all_day": True,
            "tzid": tzid,
        }

    # DATE-TIME with UTC indicator (Z suffix)
    if value.endswith("Z"):
        value = value[:-1]
        try:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
        except ValueError:
            dt = datetime.strptime(value, "%Y%m%d")
        return {"dt": dt, "all_day": False, "tzid": "UTC"}

    # DATE-TIME without Z
    try:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y%m%d")
            return {"dt": dt.date(), "all_day": True, "tzid": tzid}
        except ValueError:
            logger.warning(f"[GCal] Could not parse date/time value: {value}")
            return None

    return {"dt": dt, "all_day": False, "tzid": tzid}


def _parse_params(raw):
    """
    Parse property parameters from a line like:
      DTSTART;TZID=Asia/Jakarta;VALUE=DATE:20261225
    Returns (property_name, params_dict, value_string)
    """
    # Split property (with params) from value
    if ":" not in raw:
        return raw, {}, ""

    prop_and_params, value = raw.split(":", 1)

    parts = prop_and_params.split(";")
    prop_name = parts[0].strip().upper()
    params = {}

    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            params[k.strip().upper()] = v.strip()

    return prop_name, params, value


def _unescape(text):
    """
    Unescape iCalendar text values.
    \\n -> newline, \\, -> comma, \\\\ -> backslash
    """
    if not text:
        return text
    return (
        text.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


# ============================================================
# VEVENT Extraction
# ============================================================

def _extract_vevents(lines):
    """
    Given a list of unfolded iCal lines, extract raw property dicts
    for each VEVENT component.
    """
    events = []
    current = None

    for line in lines:
        stripped = line.strip()
        if stripped == "BEGIN:VEVENT":
            current = []
        elif stripped == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
        elif current is not None:
            current.append(stripped)

    return events


def _vevent_to_dict(raw_lines):
    """
    Convert raw VEVENT property lines into a structured event dict
    matching the Hariku gcal_integration schema.
    """
    event = {
        "id": None,
        "summary": "",
        "description": "",
        "location": "",
        "all_day": False,
        "start_time": None,
        "end_time": None,
        "recurrence": None,
        "status": "confirmed",
        "transparency": "opaque",
        "is_local": False,
    }

    for line in raw_lines:
        prop_name, params, value = _parse_params(line)

        if prop_name == "UID":
            event["id"] = value.strip()

        elif prop_name == "SUMMARY":
            event["summary"] = _unescape(value)

        elif prop_name == "DESCRIPTION":
            event["description"] = _unescape(value)

        elif prop_name == "LOCATION":
            event["location"] = _unescape(value)

        elif prop_name == "DTSTART":
            parsed = _parse_dt(value, params)
            if parsed:
                event["all_day"] = parsed["all_day"]
                dt = parsed["dt"]
                if isinstance(dt, date) and not isinstance(dt, datetime):
                    event["start_time"] = dt.isoformat()
                else:
                    event["start_time"] = dt.strftime("%Y-%m-%dT%H:%M:%S")

        elif prop_name == "DTEND":
            parsed = _parse_dt(value, params)
            if parsed:
                dt = parsed["dt"]
                if isinstance(dt, date) and not isinstance(dt, datetime):
                    event["end_time"] = dt.isoformat()
                else:
                    event["end_time"] = dt.strftime("%Y-%m-%dT%H:%M:%S")

        elif prop_name == "RRULE":
            event["recurrence"] = value.strip()

        elif prop_name == "STATUS":
            event["status"] = value.strip().lower()

        elif prop_name == "TRANSP":
            event["transparency"] = value.strip().lower()

    return event


# ============================================================
# Recurrence Expansion (Basic)
# ============================================================

def _parse_rrule(rrule_str):
    """Parse an RRULE string into a dict of its components."""
    parts = {}
    for segment in rrule_str.split(";"):
        if "=" in segment:
            k, v = segment.split("=", 1)
            parts[k.strip().upper()] = v.strip()
    return parts


_DAY_MAP = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def expand_recurrence(event, range_start, range_end):
    """
    Given an event with a recurrence rule, expand it into individual
    event instances within the date range [range_start, range_end].

    Supports: FREQ=DAILY, WEEKLY, MONTHLY, YEARLY with INTERVAL, COUNT,
    UNTIL, and BYDAY (for WEEKLY).

    Returns a list of event dicts (copies with adjusted start/end times).
    """
    rrule_str = event.get("recurrence")
    if not rrule_str:
        return [event]

    rule = _parse_rrule(rrule_str)
    freq = rule.get("FREQ", "").upper()
    interval = int(rule.get("INTERVAL", "1"))
    count = int(rule.get("COUNT", "0")) or None
    until_str = rule.get("UNTIL")

    until_date = None
    if until_str:
        parsed = _parse_dt(until_str)
        if parsed:
            dt = parsed["dt"]
            until_date = dt if isinstance(dt, date) else dt.date() if hasattr(dt, "date") else None

    # Parse original start
    start_str = event.get("start_time", "")
    end_str = event.get("end_time", "")
    is_all_day = event.get("all_day", False)

    try:
        if is_all_day or len(start_str) == 10:
            orig_start = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
            if end_str:
                orig_end = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
            else:
                orig_end = orig_start
            duration = orig_end - orig_start
        else:
            orig_start = datetime.strptime(start_str[:19], "%Y-%m-%dT%H:%M:%S")
            if end_str:
                orig_end = datetime.strptime(end_str[:19], "%Y-%m-%dT%H:%M:%S")
            else:
                orig_end = orig_start
            duration = orig_end - orig_start
    except (ValueError, TypeError):
        return [event]

    results = []
    current = orig_start
    generated = 0
    max_iterations = 1000  # Safety limit

    # For WEEKLY with BYDAY
    by_days = None
    if freq == "WEEKLY" and "BYDAY" in rule:
        by_days = [_DAY_MAP[d.strip()] for d in rule["BYDAY"].split(",") if d.strip() in _DAY_MAP]

    for _ in range(max_iterations):
        # Check termination conditions
        if count and generated >= count:
            break

        check_date = current if isinstance(current, date) and not isinstance(current, datetime) else current.date() if hasattr(current, "date") else current

        if until_date and check_date > until_date:
            break
        if check_date > range_end:
            break

        # WEEKLY with BYDAY: check each day in the week
        if freq == "WEEKLY" and by_days:
            week_start = current if isinstance(current, (date,)) else current
            for day_offset in range(7):
                if isinstance(week_start, datetime):
                    candidate = (week_start + timedelta(days=day_offset))
                    cand_date = candidate.date()
                else:
                    candidate = week_start + timedelta(days=day_offset)
                    cand_date = candidate

                if cand_date.weekday() in by_days:
                    if range_start <= cand_date <= range_end:
                        if count and generated >= count:
                            break
                        instance = dict(event)
                        if isinstance(candidate, datetime):
                            instance["start_time"] = candidate.strftime("%Y-%m-%dT%H:%M:%S")
                            instance["end_time"] = (candidate + duration).strftime("%Y-%m-%dT%H:%M:%S")
                        else:
                            instance["start_time"] = candidate.isoformat()
                            instance["end_time"] = (candidate + duration).isoformat()
                        instance["recurrence"] = None
                        instance["id"] = f"{event['id']}_r{generated}"
                        results.append(instance)
                        generated += 1
        else:
            if check_date >= range_start:
                instance = dict(event)
                if isinstance(current, datetime):
                    instance["start_time"] = current.strftime("%Y-%m-%dT%H:%M:%S")
                    instance["end_time"] = (current + duration).strftime("%Y-%m-%dT%H:%M:%S")
                else:
                    instance["start_time"] = current.isoformat()
                    instance["end_time"] = (current + duration).isoformat()
                instance["recurrence"] = None
                instance["id"] = f"{event['id']}_r{generated}"
                results.append(instance)
                generated += 1

        # Advance to next occurrence
        if freq == "DAILY":
            current += timedelta(days=interval)
        elif freq == "WEEKLY":
            current += timedelta(weeks=interval)
        elif freq == "MONTHLY":
            month = current.month + interval
            year = current.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(current.day, 28)  # Simplified
            if isinstance(current, datetime):
                current = current.replace(year=year, month=month, day=day)
            else:
                current = current.replace(year=year, month=month, day=day)
        elif freq == "YEARLY":
            try:
                if isinstance(current, datetime):
                    current = current.replace(year=current.year + interval)
                else:
                    current = current.replace(year=current.year + interval)
            except ValueError:
                # Feb 29 in non-leap year
                current = current.replace(year=current.year + interval, day=28)
        else:
            break

    return results


# ============================================================
# Public API
# ============================================================

def fetch_and_parse(ics_url):
    """
    Download an .ics file from the given URL and parse all VEVENT
    components into a list of event dicts.

    Returns:
        list[dict]: List of event dictionaries matching the
                    gcal_integration schema, or empty list on error.
    """
    if not ics_url or not ics_url.strip():
        return []

    try:
        logger.info(f"[GCal] Fetching calendar from: {ics_url[:60]}...")
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            ics_url.strip(),
            headers={"User-Agent": "Hariku-GCal-Extension/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(f"[GCal] Failed to fetch .ics: {e}")
        return []

    lines = _unfold_lines(raw)
    raw_events = _extract_vevents(lines)
    logger.info(f"[GCal] Parsed {len(raw_events)} events from .ics file.")

    events = []
    for raw_ev in raw_events:
        ev = _vevent_to_dict(raw_ev)
        if ev["id"] and ev["start_time"]:
            events.append(ev)

    return events


def get_events_for_date(all_events, target_date):
    """
    Filter a list of event dicts to only those occurring on `target_date`.

    Handles:
      - All-day events (date match)
      - Timed events (start_time date match)
      - Recurring events (expanded within target_date range)

    Args:
        all_events: list of event dicts (from fetch_and_parse or local)
        target_date: date object or 'YYYY-MM-DD' string

    Returns:
        list[dict]: Sorted by start_time
    """
    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

    matched = []

    for event in all_events:
        # Handle recurring events
        if event.get("recurrence"):
            expanded = expand_recurrence(event, target_date, target_date)
            for inst in expanded:
                matched.append(inst)
            continue

        # Non-recurring: check date match
        start_str = event.get("start_time", "")
        if not start_str:
            continue

        try:
            event_date = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        if event_date == target_date:
            matched.append(event)

    # Sort by start_time (all-day events first, then by time)
    def sort_key(ev):
        s = ev.get("start_time", "")
        if ev.get("all_day"):
            return "0_" + s  # All-day events first
        return "1_" + s

    matched.sort(key=sort_key)
    return matched
