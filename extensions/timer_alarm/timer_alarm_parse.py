# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Reading what was said to Aruna for Timer & Alarm. No wx here, and no AI:
rules only, on this computer.

    parse_duration(text, packs)          -> Duration (seconds, label) or None
    parse_alarm(text, now, packs, ...)   -> AlarmParse (due, label, repeat, problem)
    alarm_from_components(c, now, ...)   -> the same from core.when components
    clean_query(text) / match_items(...) -> which alarm or timer a name means

Durations ("3 menit", "setengah jam", "satu setengah jam", "1,5 jam", "an
hour and a half", "1 hour 30 minutes", "90 detik", "dua puluh lima menit")
are read here: core.when knows minutes and hours but not seconds, and has no
"1,5". Its packs' number words and units are used too, so a pack for another
language ("zehn Minuten") works as far as its words go.

Alarm dates and times come from core.when with the user's packs: the same
rules as the quick reminder, except for a bare hour from 1 to 12 ("jam 2",
"at 5"), which the quick reminder reads as daytime when a date is given. An
alarm often wakes someone, so:

  * with a day ("besok jam 2", "Friday at 5") or a repeat ("setiap hari jam
    5"), it is the first such hour on that day: 02:00, 05:00. 12 is noon.
    When that has passed today, the later one (the pm hour) if it hasn't;
  * with no day, the next one to come: at 10:40 "jam 5" is 17:00 today, at
    22:00 it is 05:00 tomorrow (as the quick reminder does);
  * "wake me up" / "bangunkan aku" is always the morning one.

The read-back always says the part of the day, so a wrong guess is heard and
corrected ("jam 2 siang"). A time with no hour ("besok pagi") or no time at
all is not guessed: the alarm says what is missing.
"""

import collections
import datetime
import difflib
import re
import unicodedata

from core import when, when_packs

MAX_TIMER_SECONDS = 24 * 3600
SECONDS = {"second": 1, "minute": 60, "hour": 3600}

# Unit words (folded: lower case, no accents). Single letters only count when
# glued to digits ("5m", "30s", "1h30m").
UNIT_WORDS = {
    "second": {"detik", "dtk", "det", "second", "seconds", "sec", "secs", "sekunde",
               "sekunden", "sek"},
    "minute": {"menit", "mnt", "minute", "minutes", "min", "mins", "minuten"},
    "hour": {"jam", "hour", "hours", "hr", "hrs", "stunde", "stunden", "std"},
}
GLUED_UNITS = {"s": "second", "m": "minute", "h": "hour"}
SE_UNITS = {"sedetik": ("second", 1), "semenit": ("minute", 1), "sejam": ("hour", 1)}

# Numbers, Indonesian: "dua puluh lima", "tiga belas", "seratus", "setengah".
ID_DIGITS = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6, "tujuh": 7,
             "delapan": 8, "sembilan": 9}
ID_WORDS = {"nol": 0, "sepuluh": 10, "sebelas": 11, "seratus": 100, "setengah": 0.5,
            "seperempat": 0.25}
# English: "twenty five", "thirteen", "a hundred", "half", "one and a half".
EN_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
           "seven": 7, "eight": 8, "nine": 9}
EN_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
            "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
           "eighty": 80, "ninety": 90}
ARTICLES = {"a", "an"}
CONNECTORS = {"dan", "and", "und", ","}

# Words around a label that aren't part of it ("timer for the pasta", "alarm
# untuk sholat", "stell den Wecker auf 7 Uhr").
LABEL_EDGE_WORDS = {
    "for", "the", "a", "an", "my", "of", "to", "at", "on", "and", "please", "called",
    "named", "now", "start", "starting", "timer", "timers", "alarm", "alarms", "me", "it",
    "untuk", "buat", "selama", "lagi", "yang", "dengan", "nama", "namanya", "bernama",
    "tolong", "dong", "ya", "aja", "saja", "deh", "dan", "mulai", "sekarang", "aku", "saya",
    "pada", "jam", "pukul", "itu", "ini",
    "für", "fur", "auf", "um", "mit", "und", "bitte", "den", "einen", "wecker",
}

# Words a name of an alarm or timer is said with but that aren't the name.
QUERY_NOISE = {
    "the", "my", "a", "an", "timer", "timers", "alarm", "alarms", "for", "called", "named",
    "on", "of", "is", "left", "how", "long", "much", "time", "until", "one", "that", "this",
    "yang", "untuk", "buat", "bernama", "nama", "itu", "ini", "sisa", "berapa", "lama", "lagi",
    "waktu", "waktunya", "nya", "dong", "tolong", "ya", "aku", "saya", "punya", "please",
    "wecker", "den", "der", "die", "das",
}
ALL_WORDS = {"all", "semua", "semuanya", "everything", "every", "alle", "seluruh"}
ALARM_WORDS = {"alarm", "alarms", "alarmnya", "wecker"}
TIMER_WORDS = {"timer", "timers", "timernya"}
QUESTION_WORDS = {"sisa", "berapa", "left", "remaining", "how", "wie", "lama"}
CANCEL_WORDS = {"batal", "batalkan", "hapus", "cancel", "delete", "remove", "hentikan",
                "matikan", "stop"}

MATCH_SCORE = 0.72      # how close a spoken name must be to an item's label


def fold(text):
    """Lower case without accents: "Jum'at" -> "jum'at", "Für" -> "fur"."""
    text = unicodedata.normalize("NFKD", str(text or "")).casefold()
    return "".join(c for c in text if not unicodedata.combining(c))


# ------------------------------------------------------------
# Tokens
# ------------------------------------------------------------

Tok = collections.namedtuple("Tok", "text norm start end glued")
_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+(?:['’][^\W\d_]+)*|[^\w\s]")


def tokenize(text):
    tokens, previous_end = [], None
    for m in _TOKEN_RE.finditer(text or ""):
        glued = previous_end is not None and m.start() == previous_end
        tokens.append(Tok(m.group(0), fold(m.group(0)).replace("’", "'"), m.start(), m.end(),
                          glued))
        previous_end = m.end()
    return tokens


def _is_digits(tok):
    return tok.text[:1].isdigit()


# ------------------------------------------------------------
# Words from the language packs
# ------------------------------------------------------------

class PackWords:
    """Number words, units and fixed durations from core.when's packs, for
    languages this module has no grammar for."""

    def __init__(self, codes=()):
        self.numbers = {}          # ("zehn",) -> 10
        self.units = {}            # "minuten" -> "minute"
        self.fixed = {}            # ("eine", "halbe", "stunde") -> seconds
        self.clock_prefix = "at"
        prefixes = []
        for code in codes or ():
            pack = when_packs.load_pack(code)
            if not pack:
                continue
            for word, value in pack.get("numbers", {}).items():
                key = tuple(t.norm for t in tokenize(word))
                if key and isinstance(value, int):
                    self.numbers.setdefault(key, value)
            for word in pack.get("count_words", []):
                key = tuple(t.norm for t in tokenize(word))
                if key:
                    self.numbers.setdefault(key, 1)
            for unit in ("minute", "hour"):
                for word in pack.get("units", {}).get(unit, []):
                    key = tuple(t.norm for t in tokenize(word))
                    if len(key) == 1:
                        self.units.setdefault(key[0], unit)
            for word, (unit, count) in pack.get("counted_units", {}).items():
                if unit in SECONDS:
                    key = tuple(t.norm for t in tokenize(word))
                    if key:
                        self.fixed.setdefault(key, count * SECONDS[unit])
            prefixes.extend(pack.get("clock_prefixes", [])[:1])
        if prefixes:
            self.clock_prefix = prefixes[0]
        self.max_number = max((len(k) for k in self.numbers), default=0)
        self.fixed_sorted = sorted(self.fixed.items(), key=lambda kv: -len(kv[0]))


_pack_cache = {}


def pack_words(codes):
    key = tuple(codes or ())
    if key not in _pack_cache:
        _pack_cache[key] = PackWords(key)
    return _pack_cache[key]


# ------------------------------------------------------------
# Numbers
# ------------------------------------------------------------

def _norm_at(toks, i):
    return toks[i].norm if 0 <= i < len(toks) else ""


def _plus_half(toks, j, value):
    """ "satu setengah", "one and a half": + 0.5."""
    if _norm_at(toks, j) == "setengah" and value >= 1:
        return value + 0.5, j + 1
    if (_norm_at(toks, j), _norm_at(toks, j + 1), _norm_at(toks, j + 2)) == ("and", "a", "half") \
            and value >= 1:
        return value + 0.5, j + 3
    return value, j


def _below_hundred(toks, i):
    """An Indonesian or English number from 0 to 99 in words, or None."""
    t = _norm_at(toks, i)
    if t in ID_DIGITS:
        d = ID_DIGITS[t]
        nxt = _norm_at(toks, i + 1)
        if nxt == "belas":
            return 10 + d, i + 2
        if nxt == "puluh":
            value, j = 10 * d, i + 2
            if _norm_at(toks, j) in ID_DIGITS:
                return value + ID_DIGITS[_norm_at(toks, j)], j + 1
            return value, j
        return d, i + 1
    if t in ("sepuluh", "sebelas", "nol"):
        return ID_WORDS[t], i + 1
    if t in EN_TENS:
        value, j = EN_TENS[t], i + 1
        k = j + 1 if _norm_at(toks, j) == "-" and toks[j].glued else j     # "twenty-five"
        if _norm_at(toks, k) in EN_ONES and EN_ONES[_norm_at(toks, k)] > 0:
            return value + EN_ONES[_norm_at(toks, k)], k + 1
        return value, j
    if t in EN_TEENS:
        return EN_TEENS[t], i + 1
    if t in EN_ONES:
        return EN_ONES[t], i + 1
    return None


def parse_number(toks, i, words=None):
    """(value, end) of a number at token i ("25", "1,5", "dua puluh lima",
    "satu setengah", "three quarters", "a half"), or None. The value may be a
    fraction."""
    if i >= len(toks):
        return None
    tok = toks[i]
    if _is_digits(tok):
        try:
            value = float(tok.text.replace(",", "."))
        except ValueError:
            return None
        if value == int(value):
            value = int(value)
        return _plus_half(toks, i + 1, value)
    t = tok.norm
    if t in ("setengah", "seperempat"):
        return ID_WORDS[t], i + 1
    if t == "half":
        return 0.5, i + 1
    if t == "quarter":
        return 0.25, i + 1
    if t in ARTICLES:
        nxt = _norm_at(toks, i + 1)
        if nxt == "half":
            return 0.5, i + 2
        if nxt == "quarter":
            return 0.25, i + 2
        if nxt == "hundred":
            return 100, i + 2
        return 1, i + 1                  # "an hour": only kept when a unit follows
    if t == "seratus":
        value, j = 100, i + 1
        rest = _below_hundred(toks, j)
        return (value + rest[0], rest[1]) if rest else (value, j)
    found = _below_hundred(toks, i)
    if found is not None:
        value, j = found
        nxt = _norm_at(toks, j)
        if nxt in ("ratus", "hundred") and 1 <= value <= 9:
            value, j = value * 100, j + 1
            rest = _below_hundred(toks, j + (1 if _norm_at(toks, j) == "and" else 0))
            if rest:
                value, j = value + rest[0], rest[1]
        elif nxt == "perempat" and 1 <= value <= 3:      # "tiga perempat"
            return value / 4.0, j + 1
        elif nxt == "quarters" and 1 <= value <= 3:      # "three quarters"
            return value / 4.0, j + 1
        return _plus_half(toks, j, value)
    if words is not None:
        for length in range(min(words.max_number, len(toks) - i), 0, -1):
            key = tuple(t.norm for t in toks[i:i + length])
            if key in words.numbers:
                return _plus_half(toks, i + length, words.numbers[key])
    return None


# ------------------------------------------------------------
# Durations
# ------------------------------------------------------------

Duration = collections.namedtuple("Duration", "seconds label start end")


def _unit_at(toks, k, after_digits, words):
    if k >= len(toks):
        return None
    t = toks[k].norm
    for unit, names in UNIT_WORDS.items():
        if t in names:
            return unit
    if words is not None and t in words.units:
        return words.units[t]
    if after_digits and toks[k].glued and t in GLUED_UNITS:
        return GLUED_UNITS[t]
    return None


def _term(toks, i, words):
    """(seconds, end, unit) of one "number unit" at token i, or None."""
    if words is not None:
        for key, seconds in words.fixed_sorted:
            if tuple(t.norm for t in toks[i:i + len(key)]) == key:
                unit = "hour" if seconds % 3600 == 0 else "minute"
                return seconds, i + len(key), unit
    t = _norm_at(toks, i)
    if t in SE_UNITS:
        unit, value = SE_UNITS[t]
        value, k = _plus_half(toks, i + 1, value)
        if _norm_at(toks, k) == "setengah":      # "sejam setengah"
            value, k = value + 0.5, k + 1
        return value * SECONDS[unit], k, unit
    number = parse_number(toks, i, words)
    if number is None:
        return None
    value, k = number
    if value < 1:                                  # "half an hour", "a quarter of an hour"
        if _norm_at(toks, k) == "of":
            k += 1
        if _norm_at(toks, k) in ARTICLES:
            k += 1
    unit = _unit_at(toks, k, _is_digits(toks[i]), words)
    if unit is None:
        return None
    k += 1
    if _norm_at(toks, k) == "setengah":            # "1 jam setengah"
        value, k = value + 0.5, k + 1
    elif (_norm_at(toks, k), _norm_at(toks, k + 1), _norm_at(toks, k + 2)) == ("and", "a", "half"):
        value, k = value + 0.5, k + 3              # "an hour and a half"
    return value * SECONDS[unit], k, unit


def _smaller(unit):
    return {"hour": "minute", "minute": "second"}.get(unit)


def find_duration(text, packs=None):
    """The first duration in `text`: (seconds, start token, end token) plus
    the tokens, or None. "1 jam 30" is an hour and a half, "2 menit 30" two
    and a half minutes."""
    toks = tokenize(text)
    words = pack_words(packs) if packs else None
    i = 0
    while i < len(toks):
        term = _term(toks, i, words)
        if term is None:
            i += 1
            continue
        start = i
        total, end, unit = term
        while True:
            j = end
            if _norm_at(toks, j) in CONNECTORS and _term(toks, j + 1, words):
                j += 1
            nxt = _term(toks, j, words)
            if nxt is not None:
                total, end, unit = total + nxt[0], nxt[1], nxt[2]
                continue
            smaller = _smaller(unit)
            if smaller and j < len(toks) and _is_digits(toks[j]) and "." not in toks[j].text \
                    and "," not in toks[j].text:
                value = int(toks[j].text)
                if 0 < value < 60 and _unit_at(toks, j + 1, True, words) is None:
                    total, end, unit = total + value * SECONDS[smaller], j + 1, smaller
                    continue
            break
        return total, start, end, toks
    return None


def _strip_edges(words_list, edge_words):
    while words_list and (words_list[0][1] in edge_words or not words_list[0][1].strip("-–—:;,.!?\"'")):
        words_list = words_list[1:]
    while words_list and (words_list[-1][1] in edge_words or not words_list[-1][1].strip("-–—:;,.!?\"'")):
        words_list = words_list[:-1]
    return words_list


def label_from(text, toks, used):
    """The words no duration took, without fillers at their edges, as typed."""
    runs, current = [], []
    for index, tok in enumerate(toks):
        if used[index]:
            if current:
                runs.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        runs.append(current)
    pieces = []
    for run in runs:
        kept = _strip_edges([(t, t.norm) for t in run], LABEL_EDGE_WORDS)
        if kept:
            pieces.append(text[kept[0][0].start:kept[-1][0].end])
    return clean_label(" ".join(pieces))


def clean_label(label):
    """A label on one line, trimmed of fillers and punctuation at its edges, at
    most 80 characters."""
    label = " ".join(str(label or "").split())
    toks = tokenize(label)
    kept = _strip_edges([(t, t.norm) for t in toks], LABEL_EDGE_WORDS)
    if not kept:
        return ""
    label = label[kept[0][0].start:kept[-1][0].end].strip()
    return label[:80].rstrip()


def parse_duration(text, packs=None):
    """A timer's duration and label: "mie 3 menit" -> (180, "mie"). None
    when no duration is said."""
    found = find_duration(text, packs)
    if found is None:
        return None
    total, start, end, toks = found
    used = [start <= i < end for i in range(len(toks))]
    seconds = int(round(total))
    return Duration(seconds, label_from(text, toks, used), start, end)


# ------------------------------------------------------------
# Alarms
# ------------------------------------------------------------

DATE_FIELDS = ("day_offset", "weekday", "week_offset", "month_offset", "year_offset",
               "day_of_month", "month", "year")
TIME_FIELDS = ("hour", "minute", "hour_24", "meridiem", "part_of_day", "part_hours",
               "part_default", "minutes_from_now")
BLOCKING = ("invalid_date", "invalid_time", "unsupported_repeat")


class AlarmParse:
    """An alarm as understood. `ok` when it can be set: `due` (a datetime),
    `label`, `recurrence`, `interval`, `anchor_day`. Otherwise `problem`:
    "no_time", "invalid_date", "invalid_time", "unsupported_repeat" or
    "in_past". Notes for the read-back: `passed_today` (no day was said and
    today's has passed: it is tomorrow), `conflict` (two dates or times; the
    first counts). `ambiguous` says whether the hour could be am or pm."""

    def __init__(self):
        self.due = None
        self.label = ""
        self.recurrence = "none"
        self.interval = 1
        self.anchor_day = None
        self.problem = None
        self.passed_today = False
        self.conflict = False
        self.ambiguous = False
        self.date_said = False
        self.wake = False
        self.recognised = []
        self.components = {}

    @property
    def ok(self):
        return self.problem is None and self.due is not None

    def __repr__(self):
        return (f"AlarmParse(due={self.due}, label={self.label!r}, rec={self.recurrence}, "
                f"problem={self.problem})")


_REWRITES = [
    # "dini hari" (before dawn) is morning to core.when; "subuh" right after a
    # time too ("jam 5 subuh"), but not "sholat subuh".
    (re.compile(r"\bdini\s+hari\b", re.I), "pagi"),
    (re.compile(r"\b(pagi|siang|sore|malam)\s+hari\b(?!\s+ini)", re.I), r"\1"),
    (re.compile(r"(\b\d{1,2}(?:[.:]\d{2})?)\s+subuh\b", re.I), r"\1 pagi"),
    (re.compile(r"(\bjam\s+[^\W\d_]+)\s+subuh\b", re.I), r"\1 pagi"),
]
_LEADING_FOR = re.compile(r"^\s*(?:for|untuk|buat|für|fur)\s+", re.I)


def _rewrite(text):
    for pattern, replacement in _REWRITES:
        text = pattern.sub(replacement, text)
    return text


def _has_time(c):
    return c.get("hour") is not None or c.get("minutes_from_now") is not None


def _has_any(c, fields):
    return any(c.get(f) is not None for f in fields)


def _leading_hour(text, words):
    """ "6", "6:30", "lima" at the start of an alarm ("alarm 6", "alarm lima
    pagi", "set an alarm for 6"), not followed by a unit ("alarm 10 menit")."""
    toks = tokenize(text)
    if not toks:
        return False
    if _is_digits(toks[0]):
        hour = toks[0].text.replace(",", ".").split(".")[0]
        if not hour.isdigit() or int(hour) > 24:
            return False
        nxt = 1
        if (nxt + 1 < len(toks) and toks[nxt].text == ":" and toks[nxt].glued
                and _is_digits(toks[nxt + 1]) and toks[nxt + 1].glued):
            nxt += 2                                   # "6:30"
        return _unit_at(toks, nxt, True, words) is None
    number = parse_number(toks, 0, words)
    if number is None or toks[0].norm in ARTICLES:
        return False
    value, end = number
    return isinstance(value, int) and 0 <= value <= 24 and _unit_at(toks, end, False, words) is None


def _due_of(result):
    if not result.date or not result.time:
        return None
    return datetime.datetime.strptime(f"{result.date} {result.time}", "%Y-%m-%d %H:%M")


def _resolve(c, now, problems):
    """core.when.resolve's date and time as a datetime (None when there is
    none); its date or time problems are added to `problems`."""
    result = when.resolve(c, now)
    problems.extend(x for x in result.problems if x in BLOCKING and x not in problems)
    return _due_of(result)


def _fixed(c, hour24):
    c = dict(c)
    c["hour"] = hour24
    c["hour_24"] = True
    c["meridiem"] = None
    c["part_of_day"] = None
    c["part_hours"] = None
    c["part_default"] = None
    return c


def alarm_from_components(c, now, wake=False, label="", problems=(), recognised=()):
    """Work out an alarm from core.when components (see the module notes for
    how a bare hour is read)."""
    now = now.replace(second=0, microsecond=0)
    p = AlarmParse()
    p.components = dict(c)
    p.wake = wake
    p.label = clean_label(label)
    p.recognised = list(recognised)
    p.conflict = "conflict" in problems
    p.recurrence = c.get("recurrence") or "none"
    p.interval = c.get("interval") or 1
    p.date_said = _has_any(c, DATE_FIELDS)
    blocking = [x for x in problems if x in BLOCKING]
    if blocking:
        p.problem = blocking[0]
        return p
    repeating = p.recurrence != "none"
    hour = c.get("hour")
    found = []
    if c.get("minutes_from_now") is not None:
        p.due = _resolve(c, now, found)
    elif hour is None:
        p.problem = "no_time"
        return p
    else:
        ambiguous = (1 <= hour <= 12 and not c.get("hour_24") and not c.get("meridiem")
                     and not c.get("part_of_day"))
        p.ambiguous = ambiguous
        if not ambiguous:
            p.due = _resolve(c, now, found)
        else:
            am = hour % 12
            readings = [12] if hour == 12 and wake else [am] if wake else \
                [12, 0] if hour == 12 else [am, am + 12]
            options = [_resolve(_fixed(c, h), now, found) for h in readings]
            options = [o for o in options if o is not None]
            if not options:
                p.due = None
            elif not p.date_said and not repeating and not wake:
                # No day: the next one to come, today or tomorrow.
                p.due = min(options)
            else:
                # A day or a repeat: the first reading still ahead on that day.
                ahead = [o for o in options if o > now]
                p.due = ahead[0] if ahead else options[0]
    if p.due is None or found:
        p.problem = found[0] if found else "invalid_time"
        p.due = None
        return p
    if p.due <= now:
        p.problem = "in_past"
        return p
    if p.recurrence in ("monthly", "yearly"):
        p.anchor_day = c.get("day_of_month") or p.due.day
    if (not p.date_said and not repeating and c.get("minutes_from_now") is None
            and p.due.date() > now.date() and p.due.hour >= 4
            and now.replace(hour=p.due.hour, minute=p.due.minute) <= now):
        p.passed_today = True
    return p


def parse_alarm(text, now, packs=None, language=None, wake=False):
    """Read an alarm from what followed "alarm" / "bangunkan aku": "besok
    jam 2 gang war", "tomorrow at 2 for gang war", "setiap hari jam 5 sholat
    subuh", "for 6", "10 menit". `packs` are core.when pack codes (default:
    the language, English and Indonesian)."""
    words = pack_words(packs or when_packs.default_codes(language or "en"))
    rewritten = _rewrite(" ".join(str(text or "").split()))
    result = when.parse(rewritten, now=now, language=language, packs=packs)
    c = result.components
    if not _has_time(c):
        # "alarm 6", "alarm lima pagi", "set an alarm for 6": an hour said alone.
        stripped = _LEADING_FOR.sub("", rewritten)
        if _leading_hour(stripped, words):
            again = when.parse(f"{words.clock_prefix} {stripped}", now=now, language=language,
                               packs=packs)
            if _has_time(again.components):
                result, c = again, again.components
    if not _has_time(c) and not _has_any(c, DATE_FIELDS) and not c.get("part_of_day") \
            and (c.get("recurrence") or "none") == "none":
        # "alarm 10 menit": in ten minutes.
        found = parse_duration(rewritten, packs)
        if found is not None and found.seconds >= 60:
            c = dict(c)
            c["minutes_from_now"] = max(1, int(round(found.seconds / 60.0)))
            c["title"] = found.label
            result.problems = [x for x in result.problems if x != "nothing_found"]
    return alarm_from_components(c, now, wake=wake, label=c.get("title") or "",
                                 problems=result.problems, recognised=result.recognised)


def parse_time_fix(text, now, packs=None, language=None):
    """A correction said after an alarm's read-back ("jam 2 siang", "at 2
    pm", "besok jam 7"): its core.when components, or None when it isn't only
    a date or time (it has other words, or no time at all)."""
    rewritten = _rewrite(" ".join(str(text or "").split()))
    result = when.parse(rewritten, now=now, language=language, packs=packs)
    c = result.components
    if result.trigger or clean_label(c.get("title") or ""):
        return None
    if not _has_time(c) and not _has_any(c, DATE_FIELDS):
        return None
    if any(x in BLOCKING for x in result.problems):
        return None
    return c


def merge_fix(draft, fix):
    """A draft alarm's components with a correction's date and time put in."""
    merged = dict(draft)
    if _has_any(fix, TIME_FIELDS):
        for field in TIME_FIELDS:
            merged[field] = fix.get(field)
    if _has_any(fix, DATE_FIELDS):
        for field in DATE_FIELDS:
            merged[field] = fix.get(field)
    if (fix.get("recurrence") or "none") != "none":
        merged["recurrence"] = fix["recurrence"]
        merged["interval"] = fix.get("interval") or 1
    return merged


# ------------------------------------------------------------
# Which alarm or timer a name means
# ------------------------------------------------------------

_word_sets = {}


def _normalized(name, words):
    """A word set in Aruna's normal form (core.commands.normalize: a letter
    said twice counts once, so "all" is "al")."""
    if name not in _word_sets:
        from core.commands import normalize
        _word_sets[name] = {normalize(w) for w in words}
    return _word_sets[name]


class Query:
    """What was said to pick items: `words` (the name, normalized), `kind`
    ("alarm", "timer" or None), `all` ("semua timer"), `asks` (a question
    word: "sisa", "how long") and `cancels` (a cancel word)."""

    def __init__(self, text):
        from core.commands import normalize
        text = str(text or "")
        tokens = normalize(text).split()
        self.raw = text
        self.kind = None
        all_words = _normalized("all", ALL_WORDS)
        question = _normalized("question", QUESTION_WORDS)
        cancel = _normalized("cancel", CANCEL_WORDS)
        alarm = _normalized("alarm", ALARM_WORDS)
        timer = _normalized("timer", TIMER_WORDS)
        self.all = any(t in all_words for t in tokens)
        self.asks = any(t in question for t in tokens)
        self.cancels = any(t in cancel for t in tokens)
        if any(t in alarm for t in tokens):
            self.kind = "alarm"
        elif any(t in timer for t in tokens):
            self.kind = "timer"
        noise = (_normalized("noise", QUERY_NOISE) | all_words | question | cancel | alarm
                 | timer)
        self.words = [t for t in tokens if t not in noise]
        # The same without the noise, as typed ("the 5:00 AM" -> "5:00 AM"),
        # for reading a time or a duration.
        kept = [t for t in tokenize(text) if normalize(t.text) not in noise]
        self.rest = "".join((" " if (k and not t.glued) else "") + t.text
                            for k, t in enumerate(kept)).strip()

    @property
    def name(self):
        return " ".join(self.words)

    def __repr__(self):
        return f"Query({self.name!r}, kind={self.kind}, all={self.all})"


def clean_query(text):
    return Query(text)


def name_score(query_name, label):
    """0 to 1: how well a spoken name fits a label ("mi" fits "mie")."""
    from core.commands import normalize
    label = normalize(label)
    if not query_name or not label:
        return 0.0
    if query_name == label:
        return 1.0
    said, have = query_name.split(), label.split()
    if set(said) <= set(have) or set(have) <= set(said):
        return 0.9
    return difflib.SequenceMatcher(None, query_name.replace(" ", ""),
                                   label.replace(" ", "")).ratio()


def match_items(query, items, now=None, packs=None, language=None):
    """The items a query names, best first (ties kept): by label; for timers
    also by duration ("timer 10 menit"), for alarms by time ("alarm jam 5")."""
    if isinstance(query, str):
        query = Query(query)
    name = query.name
    if not name:
        return []
    scored = []
    duration = parse_duration(query.rest, packs)
    clock = None
    if now is not None:
        fix = parse_time_fix(query.rest, now, packs, language)
        if fix is not None and fix.get("hour") is not None:
            hour, minute = fix["hour"], fix.get("minute") or 0
            if fix.get("hour_24") or fix.get("meridiem") or fix.get("part_of_day"):
                clock = {_fixed_clock(fix)}
            else:
                clock = {((hour % 12) * 60 + minute), ((hour % 12 + 12) * 60 + minute)}
    for item in items:
        score = name_score(name, item.get("label") or "")
        if item["kind"] == "timer" and duration is not None and not duration.label \
                and duration.seconds == item.get("seconds"):
            score = max(score, 1.0)
        if item["kind"] == "alarm" and clock is not None:
            due = item["due"]
            if due.hour * 60 + due.minute in clock:
                score = max(score, 0.95)
        if score >= MATCH_SCORE:
            scored.append((score, item))
    if not scored:
        return []
    best = max(s for s, _ in scored)
    return [item for s, item in sorted(scored, key=lambda x: (-x[0], x[1]["due"]))
            if s >= best - 0.001]


def _fixed_clock(c):
    try:
        result = when.resolve(c, datetime.datetime(2026, 1, 1, 0, 0))
        hour, minute = map(int, result.time.split(":"))
        return hour * 60 + minute
    except Exception:
        return -1
