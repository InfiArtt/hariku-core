# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""English for the quick reminder. Fields: DEVELOPERS.md, "For translators".

Copy this file to start a new language. Numeric dates are read day first
(5/10 is 5 October), as in most of the world; an American pack would say
"MDY". "half past eight" and British "half eight" are 08:30 (half AFTER).
"""

PACK = {
    "code": "en",
    "name": "English",
    "date_order": "DMY",
    "numbers": {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
        "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "forty five": 45,
    },
    "count_words": ["a", "an"],
    "weekdays": [["monday"], ["tuesday"], ["wednesday"], ["thursday"], ["friday"],
                 ["saturday"], ["sunday"]],
    "weekday_abbreviations": [["mon"], ["tue", "tues"], ["wed"], ["thu", "thur", "thurs"],
                              ["fri"], ["sat"], ["sun"]],
    "weekday_plurals": [["mondays"], ["tuesdays"], ["wednesdays"], ["thursdays"], ["fridays"],
                        ["saturdays"], ["sundays"]],
    "months": [
        ["january", "jan"], ["february", "feb"], ["march", "mar"], ["april", "apr"], ["may"],
        ["june", "jun"], ["july", "jul"], ["august", "aug"], ["september", "sep", "sept"],
        ["october", "oct"], ["november", "nov"], ["december", "dec"],
    ],
    "relative_days": {"today": 0, "tomorrow": 1, "tmrw": 1, "tmr": 1,
                      "the day after tomorrow": 2, "day after tomorrow": 2,
                      "tonight": [0, "evening"]},
    "units": {
        "minute": ["minute", "minutes", "min", "mins"], "hour": ["hour", "hours", "hr", "hrs"],
        "day": ["day", "days"], "week": ["week", "weeks"], "month": ["month", "months"],
        "year": ["year", "years"],
    },
    "counted_units": {
        "half an hour": ["minute", 30], "half hour": ["minute", 30],
        "a quarter of an hour": ["minute", 15], "quarter of an hour": ["minute", 15],
        "an hour and a half": ["minute", 90],
    },
    "parts_of_day": [
        {"part": "morning", "words": ["morning", "in the morning"]},
        {"part": "midday", "words": ["lunchtime", "at lunchtime"]},
        {"part": "afternoon", "words": ["afternoon", "in the afternoon"], "hours": [12, 18],
         "default": "15:00"},
        {"part": "evening", "words": ["evening", "in the evening"]},
        {"part": "night", "words": ["night", "at night"]},
    ],
    "noon": ["noon", "midday"],
    "midnight": ["midnight"],
    "meridiem_am": ["am", "a.m.", "a.m"],
    "meridiem_pm": ["pm", "p.m.", "p.m"],
    "clock_prefixes": ["at", "@"],
    "clock_suffixes": ["o'clock", "oclock"],
    "clock_idioms": [
        {"pattern": "half past {h}", "minutes": 30},
        {"pattern": "half {h}", "minutes": 30},
        {"pattern": "[a] quarter (past|after) {h}", "minutes": 15},
        {"pattern": "[a] quarter (to|before|of) {h}", "minutes": -15},
        {"pattern": "{m} [minutes|minute|mins] (past|after) {h}", "minutes": "+m"},
        {"pattern": "{m} [minutes|minute|mins] (to|before) {h}", "minutes": "-m"},
    ],
    "relative_patterns": ["in {dur}", "{dur} from now", "{dur} later", "after {dur}"],
    "weekday_prefixes": ["on"],
    "next_before": ["next", "coming", "this coming"],
    "next_after": [],
    "this_before": ["this"],
    "this_after": [],
    "every": ["every", "each"],
    "every_other": ["every other", "every second"],
    "repeat_leads": ["repeat", "repeating", "repeats"],
    "repeat_words": {"daily": ["daily", "everyday"], "weekly": ["weekly"],
                     "monthly": ["monthly"], "yearly": ["yearly", "annually"]},
    "repeat_patterns": ["once [every] {dur}"],
    "day_prefixes": [],
    "ordinal_day_prefixes": ["the", "on the"],
    "ordinal_suffixes": ["st", "nd", "rd", "th"],
    "date_connectors": ["of"],
    "fillers": ["at", "on", "around", "about", "approximately", "and", "please", "to", "of"],
    "triggers": [
        "[please] remind me [to|about|of|that]",
        "[please] (set|create|add|make) [me] [a] reminder [to|for|about|that]",
        "reminder [:]",
        "(don't|dont) forget [to]",
    ],
}

# (now, sentence, expected). Thursday 24 September 2026 10:40 unless noted.
EXAMPLES = [
    ("2026-09-24 10:40", "remind me to call mom tomorrow at 7pm",
     {"title": "Call mom", "date": "2026-09-25", "time": "19:00"}),
    ("2026-09-24 10:40", "take pills every day at 8 am",
     {"title": "Take pills", "date": "2026-09-25", "time": "08:00", "recurrence": "daily"}),
    ("2026-09-24 10:40", "dentist next Monday at half past nine",
     {"title": "Dentist", "date": "2026-09-28", "time": "09:30"}),
    ("2026-09-24 10:40", "check the oven in 20 minutes",
     {"title": "Check the oven", "date": "2026-09-24", "time": "11:00"}),
    ("2026-09-24 10:40", "pay rent monthly on the 1st",
     {"title": "Pay rent", "date": "2026-10-01", "time": "09:00", "recurrence": "monthly",
      "time_assumed": True}),
    ("2026-09-24 10:40", "team meeting every other week on Friday at 3",
     {"title": "Team meeting", "date": "2026-09-25", "time": "15:00", "recurrence": "weekly",
      "interval": 2}),
    ("2026-09-24 10:40", "water the plants this evening",
     {"title": "Water the plants", "date": "2026-09-24", "time": "19:00"}),
    ("2026-09-24 10:40", "renew passport on 5 October 2027",
     {"title": "Renew passport", "date": "2027-10-05", "time": "09:00", "time_assumed": True}),
    ("2026-09-24 10:40", "call Budi at a quarter to nine tonight",
     {"title": "Call Budi", "date": "2026-09-24", "time": "20:45"}),
]
