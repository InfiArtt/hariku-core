# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Language packs for the quick reminder's sentence reader (core/when.py).

The reader knows no language. Every word it understands comes from a pack: one
Python file per language, core/when_lang_<code>.py, holding a PACK dict (the
words) and an EXAMPLES list (sentences with the reminder they must give).
Plain data, no code.

The pack fields, the EXAMPLES table and how to add a language are described
in DEVELOPERS.md, "For translators". In short: copy when_lang_en.py, translate
it, add its module to PACK_MODULES below (the compiled Hariku only contains
modules the core imports by name), and run tests/test_when.py.

Several packs can be active at once, so people can mix languages ("meeting
besok jam 3"). The Hariku language, English and Indonesian are always on; the
user adds others in Preferences, Reminders.
"""

from core import when_lang_de, when_lang_en, when_lang_id

# Every pack, imported by name so the compiled build includes it.
PACK_MODULES = (when_lang_id, when_lang_en, when_lang_de)
PACK_PREFIX = "when_lang_"
ALWAYS_ON = ("en", "id")          # besides the Hariku language
PARTS = ("morning", "midday", "afternoon", "evening", "night")
UNITS = ("minute", "hour", "day", "week", "month", "year")
REPEATS = ("daily", "weekly", "monthly", "yearly")

LIST_FIELDS = (
    "count_words", "noon", "midnight", "meridiem_am", "meridiem_pm", "clock_prefixes",
    "clock_suffixes", "relative_patterns", "weekday_prefixes", "next_before", "next_after",
    "this_before", "this_after", "every", "every_other", "repeat_leads", "repeat_patterns",
    "day_prefixes", "ordinal_day_prefixes", "ordinal_suffixes", "date_connectors", "fillers",
    "triggers",
)


def _modules():
    """{code: module} for every pack module whose PACK names its code."""
    found = {}
    for module in PACK_MODULES:
        pack = getattr(module, "PACK", None)
        code = pack.get("code") if isinstance(pack, dict) else None
        if isinstance(code, str) and code and code not in found:
            found[code] = module
    return found


def available_codes():
    """Codes of the installed packs, sorted."""
    return sorted(_modules())


def load_pack(code):
    """The PACK dict of one language, or None when there is no such pack."""
    module = _modules().get(code)
    return module.PACK if module is not None else None


def pack_examples(code):
    module = _modules().get(code)
    return list(getattr(module, "EXAMPLES", [])) if module is not None else []


def pack_name(code):
    pack = load_pack(code)
    return pack.get("name", code) if pack else code


def default_codes(ui_language, extra=()):
    """The packs to use, in order of priority: the Hariku language, English,
    Indonesian, then the ones the user added in Preferences."""
    have = set(available_codes())
    order = []
    for code in [ui_language, *ALWAYS_ON, *(extra or ())]:
        if code in have and code not in order:
            order.append(code)
    return order


def optional_codes(ui_language):
    """Packs the user can switch on (everything that isn't always on)."""
    return [c for c in available_codes() if c != ui_language and c not in ALWAYS_ON]


def _word_lists(value, count=None):
    if not isinstance(value, list) or (count is not None and len(value) != count):
        return False
    return all(isinstance(names, list) and all(isinstance(w, str) and w for w in names)
               for names in value)


def validate_pack(pack):
    """Problems with a PACK dict's fields (not its patterns; the parser checks
    those when it builds its word tables). An empty list means it's fine."""
    if not isinstance(pack, dict):
        return ["PACK is not a dict"]
    problems = []
    for field in ("code", "name"):
        if not isinstance(pack.get(field), str) or not pack.get(field):
            problems.append(f"{field} is missing")
    if pack.get("date_order", "DMY") not in ("DMY", "MDY"):
        problems.append("date_order must be DMY or MDY")
    if not _word_lists(pack.get("weekdays"), 7) or not all(pack["weekdays"]):
        problems.append("weekdays must be 7 non-empty lists, Monday first")
    if not _word_lists(pack.get("months"), 12) or not all(pack["months"]):
        problems.append("months must be 12 non-empty lists")
    for field in ("weekday_abbreviations", "weekday_plurals"):
        if field in pack and not _word_lists(pack[field], 7):
            problems.append(f"{field} must be 7 lists")
    numbers = pack.get("numbers", {})
    if not isinstance(numbers, dict) or not all(
            isinstance(k, str) and isinstance(v, int) and 0 <= v <= 59 for k, v in numbers.items()):
        problems.append("numbers must map words to 0-59")
    elif not set(range(1, 13)) <= set(numbers.values()):
        problems.append("numbers must cover 1-12")
    for word, value in pack.get("relative_days", {}).items():
        if isinstance(value, int):
            continue
        if not (isinstance(value, list) and len(value) == 2 and isinstance(value[0], int)
                and value[1] in PARTS):
            problems.append(f"relative_days[{word!r}] must be a number or [days, part]")
    units = pack.get("units", {})
    if not isinstance(units, dict) or not set(units) <= set(UNITS):
        problems.append(f"units keys must be among {UNITS}")
    for word, value in pack.get("counted_units", {}).items():
        if not (isinstance(value, list) and len(value) == 2 and value[0] in UNITS
                and isinstance(value[1], int) and value[1] > 0):
            problems.append(f"counted_units[{word!r}] must be [unit, count]")
    for entry in pack.get("parts_of_day", []):
        if not isinstance(entry, dict) or entry.get("part") not in PARTS or not entry.get("words"):
            problems.append(f"parts_of_day entry {entry!r} needs a part and words")
            continue
        hours = entry.get("hours")
        if hours is not None and not (isinstance(hours, list) and len(hours) == 2
                                      and 0 <= hours[0] <= hours[1] <= 30):
            problems.append(f"parts_of_day hours {hours!r} must be [first, last]")
        default = entry.get("default")
        if default is not None and not is_clock(default):
            problems.append(f"parts_of_day default {default!r} must be HH:MM")
    repeat_words = pack.get("repeat_words", {})
    if not isinstance(repeat_words, dict) or not set(repeat_words) <= set(REPEATS):
        problems.append(f"repeat_words keys must be among {REPEATS}")
    for field in LIST_FIELDS:
        value = pack.get(field, [])
        if not isinstance(value, list) or not all(isinstance(w, str) and w for w in value):
            problems.append(f"{field} must be a list of words")
    for idiom in pack.get("clock_idioms", []):
        minutes = idiom.get("minutes") if isinstance(idiom, dict) else None
        if not (isinstance(minutes, int) or minutes in ("+m", "-m")) or not idiom.get("pattern"):
            problems.append(f"clock_idioms entry {idiom!r} needs a pattern and minutes")
    marker = pack.get("infinitive_marker")
    if marker is not None and not (isinstance(marker, str) and marker):
        problems.append("infinitive_marker must be a word")
    return problems


def is_clock(text):
    """True for "HH:MM" (0-23, two-digit minutes)."""
    try:
        hour, minute = text.split(":")
        return len(minute) == 2 and 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59
    except (ValueError, AttributeError):
        return False
