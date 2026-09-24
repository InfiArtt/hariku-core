# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Deutsch for the quick reminder. Fields: DEVELOPERS.md, "For translators".

"halb neun" is 08:30 (half BEFORE nine, like Indonesian "setengah 9"),
"Viertel vor acht" 07:45, "Viertel nach acht" 08:15. "morgen" is tomorrow;
the morning is "morgens", "früh", "am Morgen" ("heute Morgen", "morgen früh").
Hariku has no German interface yet, so the read-back is in the Hariku language.
"""

PACK = {
    "code": "de",
    "name": "Deutsch",
    "date_order": "DMY",
    "numbers": {
        "null": 0, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
        "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12,
        "zwoelf": 12, "fünfzehn": 15, "fuenfzehn": 15, "zwanzig": 20, "dreißig": 30,
        "vierzig": 40, "fünfundvierzig": 45, "fuenfundvierzig": 45,
    },
    "count_words": ["ein", "eine", "einer", "einem", "einen"],
    "weekdays": [["montag"], ["dienstag"], ["mittwoch"], ["donnerstag"], ["freitag"],
                 ["samstag", "sonnabend"], ["sonntag"]],
    "weekday_abbreviations": [["mo"], ["di"], ["mi"], ["do"], ["fr"], ["sa"], ["so"]],
    "weekday_plurals": [["montags"], ["dienstags"], ["mittwochs"], ["donnerstags"],
                        ["freitags"], ["samstags", "sonnabends"], ["sonntags"]],
    "months": [
        ["januar", "jan", "jänner"], ["februar", "feb"], ["märz", "maerz", "mär", "mrz"],
        ["april", "apr"], ["mai"], ["juni", "jun"], ["juli", "jul"], ["august", "aug"],
        ["september", "sep", "sept"], ["oktober", "okt"], ["november", "nov"],
        ["dezember", "dez"],
    ],
    "relative_days": {
        "heute": 0, "morgen": 1, "übermorgen": 2, "uebermorgen": 2,
        "heute abend": [0, "evening"], "heute nacht": [0, "night"],
        "heute früh": [0, "morning"], "heute morgen": [0, "morning"],
        "morgen früh": [1, "morning"], "morgen frueh": [1, "morning"],
        "morgen abend": [1, "evening"],
    },
    "units": {
        "minute": ["minute", "minuten", "min"], "hour": ["stunde", "stunden", "std"],
        "day": ["tag", "tage", "tagen"], "week": ["woche", "wochen"],
        "month": ["monat", "monate", "monaten"], "year": ["jahr", "jahre", "jahren"],
    },
    "counted_units": {
        "einer halben stunde": ["minute", 30], "eine halbe stunde": ["minute", 30],
        "einer viertelstunde": ["minute", 15], "eine viertelstunde": ["minute", 15],
        "anderthalb stunden": ["minute", 90],
    },
    "parts_of_day": [
        {"part": "morning", "words": ["früh", "frueh", "morgens", "am morgen", "in der früh"]},
        {"part": "morning", "words": ["vormittag", "vormittags", "am vormittag"],
         "hours": [8, 11], "default": "10:00"},
        {"part": "midday", "words": ["mittag", "mittags", "am mittag"]},
        {"part": "afternoon", "words": ["nachmittag", "nachmittags", "am nachmittag"],
         "hours": [12, 18], "default": "15:00"},
        {"part": "evening", "words": ["abend", "abends", "am abend"]},
        {"part": "night", "words": ["nacht", "nachts", "in der nacht"]},
    ],
    "noon": [],
    "midnight": ["mitternacht"],
    "meridiem_am": [],
    "meridiem_pm": [],
    "clock_prefixes": ["um", "gegen"],
    "clock_suffixes": ["uhr"],
    "clock_idioms": [
        {"pattern": "halb {h}", "minutes": -30},
        {"pattern": "viertel vor {h}", "minutes": -15},
        {"pattern": "viertel nach {h}", "minutes": 15},
        {"pattern": "dreiviertel {h}", "minutes": -15},
        {"pattern": "{m} [minuten] vor {h}", "minutes": "-m"},
        {"pattern": "{m} [minuten] nach {h}", "minutes": "+m"},
    ],
    "relative_patterns": ["in {dur}"],
    "weekday_prefixes": ["am"],
    "next_before": ["nächsten", "nächste", "nächster", "nächstes", "naechsten", "naechste",
                    "naechster", "naechstes", "kommenden", "kommende", "kommender", "kommendes"],
    "next_after": [],
    "this_before": ["diesen", "diese", "dieses", "dieser"],
    "this_after": [],
    "every": ["jeden", "jede", "jedes", "alle"],
    "every_other": ["jeden zweiten", "jede zweite", "jedes zweite"],
    "repeat_leads": ["wiederhole", "wiederholen", "wiederholt"],
    "repeat_words": {"daily": ["täglich", "taeglich"], "weekly": ["wöchentlich", "woechentlich"],
                     "monthly": ["monatlich"], "yearly": ["jährlich", "jaehrlich"]},
    "repeat_patterns": ["einmal (pro|im|in der|am) {unit}"],
    "day_prefixes": [],
    "ordinal_day_prefixes": ["am", "den", "zum"],
    "ordinal_suffixes": ["."],
    "date_connectors": [],
    "fillers": ["um", "am", "gegen", "und", "bitte", "an", "ca", "circa", "etwa"],
    "triggers": [
        "[bitte] (erinnere|erinner) mich [bitte] [daran|an]",
        "erinnerung [:]",
        "nicht vergessen [:]",
        "vergiss nicht [zu]",
    ],
    "infinitive_marker": "zu",
}

# (now, sentence, expected). Thursday 24 September 2026 10:40 unless noted.
EXAMPLES = [
    ("2026-09-24 10:40", "erinnere mich morgen um 8 Uhr an den Zahnarzt",
     {"title": "Den Zahnarzt", "date": "2026-09-25", "time": "08:00"}),
    ("2026-09-24 10:40", "übermorgen Mutter anrufen",
     {"title": "Mutter anrufen", "date": "2026-09-26", "time": "09:00", "time_assumed": True}),
    ("2026-09-24 10:40", "nächsten Montag halb neun Besprechung",
     {"title": "Besprechung", "date": "2026-09-28", "time": "08:30"}),
    ("2026-09-24 10:40", "am 5. Oktober Reifen wechseln",
     {"title": "Reifen wechseln", "date": "2026-10-05", "time": "09:00"}),
    ("2026-09-24 10:40", "jeden Tag um 20 Uhr Tabletten nehmen",
     {"title": "Tabletten nehmen", "date": "2026-09-24", "time": "20:00",
      "recurrence": "daily"}),
    ("2026-09-24 10:40", "jeden Montag Sport",
     {"title": "Sport", "date": "2026-09-28", "time": "09:00", "recurrence": "weekly"}),
    ("2026-09-24 10:40", "alle 2 Tage Blumen gießen",
     {"title": "Blumen gießen", "date": "2026-09-25", "time": "09:00", "recurrence": "daily",
      "interval": 2}),
    ("2026-09-24 10:40", "in 30 Minuten Nudeln abgießen",
     {"title": "Nudeln abgießen", "date": "2026-09-24", "time": "11:10"}),
    ("2026-09-24 10:40", "heute Abend Müll rausbringen",
     {"title": "Müll rausbringen", "date": "2026-09-24", "time": "19:00"}),
    ("2026-09-24 10:40", "Viertel vor acht Bus nehmen",
     {"title": "Bus nehmen", "date": "2026-09-24", "time": "19:45"}),
    ("2026-09-24 10:40", "erinnere mich, morgen die Tabletten zu nehmen",
     {"title": "Die Tabletten nehmen", "date": "2026-09-25", "time": "09:00"}),
]
