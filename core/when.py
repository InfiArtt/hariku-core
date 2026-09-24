# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The sentence reader behind Hariku's quick reminder (N) and the reminder
dialog's "Or type it in one sentence" field: one sentence in, one reminder out
(title, date, time and repeat). No AI: a wrong date on a medicine reminder is
dangerous, and small local models get dates wrong, so dates, times and repeats
come from these rules only. Pure Python, no wx. Everything happens on this
computer; nothing is sent anywhere.

    parse(text, now, language, packs, default_date) -> Result
    resolve(components, now, default_date)          -> Result   (for an AI fallback)

This module knows no language. Words come from the language packs
(core/when_lang_*.py, loaded by core/when_packs.py; how to add a language is
in DEVELOPERS.md, "For translators"). The engine has the tokenizer, numbers
and clock formats ("8:30", "08.30", "5/10/2026"), the templates that put pack
words together, the calendar maths and the rules below.

How a sentence is read
----------------------
1. The text becomes tokens: words, numbers, marks ("." ":" "/" "-"), and
   other punctuation (commas and the like are ignored for matching).
2. From left to right, every template is tried at each token and the longest
   match wins; a tie goes to the earlier kind in KIND_ORDER, then the earlier
   template, then the pack with more priority. What no template takes stays in
   the title. A trigger ("remind me to") only counts before the first title word.
3. Each match fills fields of the neutral structure (COMPONENT_FIELDS), made
   of relative parts only: a day offset, a weekday, a day and month, an hour
   as said, a part of the day, a repeat... An AI fallback produces the same
   structure, and resolve() does all the calendar maths for both.

Several packs at once (mixed languages)
---------------------------------------
The packs are merged, in priority order: the Hariku language, English,
Indonesian, then the ones added in Preferences, Reminders. Result.packs lists
the packs whose words were used. Clashes are settled like this:
  * A phrase that means different things in two packs within the same kind of
    word (two weekdays, say) takes the meaning of the pack with more priority.
  * Different kinds of word never clash, because templates only take a word
    where its kind fits: "am" is a.m. after a number ("8 am") but German "on"
    before a weekday or a date ("um 3 am Montag"); "jam" is a clock word before
    a number and a unit after one ("2 jam lagi"); "minggu" is a week in "minggu
    depan" and "tiap minggu" (those templates come first) and Sunday elsewhere.
  * A part of the day standing alone ("sore") is also an everyday word in some
    languages ("sore throat"). It counts only when it is next to another date
    or time, when another phrase of its pack was used, or, with no other date
    or time, when its pack is the Hariku language. Otherwise it stays in the
    title and is reported in Result.unparsed.
  * Two different values for the same field ("jam 8 ... jam 9") keep the first
    and add the problem "conflict".

Rules
-----
Dates (`today` is the date of `now`):
  * A weekday ("Senin", "next Monday", "am Montag", "on Friday") is the next
    such day, never today ("hari ini"/"today" is how to say today).
  * A weekday and "next week" ("Senin minggu depan", "Montag nächste Woche")
    is that day in the next calendar week (weeks start on Monday).
  * "next week", "next month", "next year" alone: the same day then.
  * A day and month without a year: this year, or next year once it has
    passed; the next year it exists for 29 February. With a year, as said.
  * A day of the month alone ("tanggal 5", "the 5th"): this month, or the
    next month that has that day once it has passed ("tanggal 31" in
    September is 31 October).
  * Numeric dates are day/month ("5/10" is 5 October) unless the first pack
    says month/day. "-" and "." need a year ("5-10-2026").
  * With several date phrases that disagree, a calendar date wins over a
    weekday, which wins over "tomorrow"; the problem "conflict" is added.
Times:
  * "in 30 minutes" / "30 menit lagi": now plus that, to the minute.
  * With a part of the day, the hour is the one inside the part's range
    (PARTS_OF_DAY), else the nearest (on a tie, the later): "jam 1 siang"
    13:00, "jam 4 sore" 16:00, "jam 9 malam" 21:00, "jam 12 malam" 00:00 of
    the next day, "jam 2 malam" 02:00 of the next day.
  * am/pm as said. Hours 13-24, and hours written with a leading zero
    ("08.30") or as 0, are 24-hour.
  * Any other hour 1-12 is ambiguous:
      - a one-off reminder with no date: the next upcoming of the two ("jam 8"
        at 10:40 is 20:00 today; at 21:00 it is 08:00 tomorrow);
      - with a date, or a repeat: the daytime rule, 07:00-18:59 ("besok jam 8"
        08:00, "besok jam 3" 15:00); on today, once that has passed, the other.
  * A time with no date: today, or tomorrow once it has passed.
  * A time, a part of the day or a repeat with no date, when the caller gives
    a default_date (the reminder dialog gives the date it is set to, unless
    that is today): that date, as if it had been said. date_assumed stays set.
  * A part of the day with no clock time: its default time (PARTS_OF_DAY).
  * No time but a date or a repeat: 09:00 and time_assumed.
  * Nothing about when at all: the problem "nothing_found".
  * A time at or before now on an explicit date sets in_past.
Repeats map to the core reminders: daily, weekly, monthly, yearly, with an
interval ("every 2 days" is daily, interval 2). "every Monday" is weekly,
dated the next Monday; "tiap bulan tanggal 5" is monthly, dated the next 5th.
Every hour/minute is the problem "unsupported_repeat".
"""

import calendar
import collections
import datetime
import re

from core import when_packs

RECURRENCES = ("none", "daily", "weekly", "monthly", "yearly")
DEFAULT_MINUTES = 9 * 60             # "09:00" when no time was said
DAYTIME_FIRST_HOUR = 7                # the daytime rule: 07:00-18:59

# Parts of the day: (first hour, last hour, default time). Hours past 24 are
# after midnight. A pack can give its own words other hours or a default.
PARTS_OF_DAY = {
    "morning":   (1, 11, "07:00"),    # pagi
    "midday":    (11, 14, "12:00"),   # siang
    "afternoon": (15, 18, "16:00"),   # sore
    "evening":   (18, 24, "19:00"),   # malam; 24 is midnight ("jam 12 malam")
    "night":     (20, 28, "21:00"),   # late night; 25-28 are 01:00-04:00
}

# The neutral structure between the words and the calendar. parse() builds it
# from the sentence; a future AI fallback returns the same. Everything is
# relative, the engine does the calendar maths (see resolve()).
COMPONENT_FIELDS = {
    "title": "what to remind about",
    "day_offset": "days from today: 0 today, 1 tomorrow, 2 the day after",
    "weekday": "0 Monday ... 6 Sunday: the next such day",
    "week_offset": "1 = next week (with a weekday: that day of next week)",
    "month_offset": "1 = next month",
    "year_offset": "1 = next year",
    "day_of_month": "1-31",
    "month": "1-12",
    "year": "four digits",
    "hour": "the hour as said, 0-24 (1-12 may be am or pm)",
    "minute": "0-59",
    "hour_24": "true when the hour was given in 24-hour form",
    "meridiem": "am or pm",
    "part_of_day": "morning, midday, afternoon, evening or night",
    "minutes_from_now": "for 'in 30 minutes'",
    "recurrence": "none, daily, weekly, monthly or yearly",
    "interval": "every N days/weeks/months/years, 1 or more",
}

# Problems that stop a reminder from being saved; the others are warnings.
BLOCKING = ("nothing_found", "no_title", "invalid_date", "invalid_time", "unsupported_repeat")

KIND_ORDER = ("trigger", "recur", "relative", "period", "date", "day_of_month", "clock_time",
              "rel_day", "this_part", "weekday", "part")


# ----------------------------------------------------------------------------
# Result
# ----------------------------------------------------------------------------

class Result:
    """What a sentence (or an AI's components) gives. `ok` means it can be
    saved; `needs_fallback` means a fallback (a person, or later an AI) should
    have a look."""

    def __init__(self):
        self.text = ""
        self.title = ""
        self.date = None            # "YYYY-MM-DD"
        self.time = None            # "HH:MM"
        self.recurrence = "none"
        self.interval = 1
        self.recognised = []        # the date/time/repeat phrases, as typed
        self.trigger = ""           # "remind me to", as typed
        self.leftover = []          # words no template took (the title's words)
        self.unparsed = []          # leftover words that look like dates or times
        self.time_assumed = False   # no time was said: 09:00
        self.date_assumed = False   # no date was said: today, tomorrow or default_date
        self.in_past = False
        self.problems = []
        self.confidence = 0.0
        self.packs = []             # packs whose words were used
        self.components = {}

    @property
    def ok(self):
        return (bool(self.title) and bool(self.date) and bool(self.time)
                and not any(p in BLOCKING for p in self.problems))

    @property
    def needs_fallback(self):
        return not self.ok or self.confidence < 0.7 or bool(self.unparsed)

    @property
    def weekday(self):
        return _date(self.date).weekday() if self.date else None

    def to_dict(self):
        return {
            "title": self.title, "date": self.date, "time": self.time,
            "recurrence": self.recurrence, "interval": self.interval,
            "recognised": list(self.recognised), "leftover": list(self.leftover),
            "unparsed": list(self.unparsed), "time_assumed": self.time_assumed,
            "date_assumed": self.date_assumed, "in_past": self.in_past,
            "problems": list(self.problems), "confidence": self.confidence,
            "packs": list(self.packs), "ok": self.ok,
        }

    def __repr__(self):
        return f"Result({self.to_dict()!r})"


def _date(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d").date()


# ----------------------------------------------------------------------------
# Tokens
# ----------------------------------------------------------------------------

Token = collections.namedtuple("Token", "kind text norm start end space_before")
_TOKEN_RE = re.compile(r"\d+|[^\W\d_]+(?:['’][^\W\d_]+)*|[.:/\-]|\S")


def normalize(word):
    return word.casefold().replace("’", "'")


def tokenize(text):
    """Words, numbers, marks (. : / -) and other punctuation, each with
    its place in the text and whether a space comes before it."""
    tokens, previous_end = [], 0
    for m in _TOKEN_RE.finditer(text or ""):
        s = m.group(0)
        if s.isdecimal():
            kind = "num"
        elif s in ".:/-":
            kind = "mark"
        elif s[0].isalpha() or s == "@":
            kind = "word"
        else:
            kind = "punct"
        tokens.append(Token(kind, s, normalize(s), m.start(), m.end(), m.start() > previous_end))
        previous_end = m.end()
    return tokens


def _phrase_key(phrase):
    return tuple(t.norm for t in tokenize(phrase) if t.kind != "punct")


# ----------------------------------------------------------------------------
# Patterns: word  (a|b)  [optional]  {slot} / {slot:label}
# ----------------------------------------------------------------------------

class PackError(ValueError):
    """A pack's pattern or field can't be used."""


_Lit = collections.namedtuple("_Lit", "norm")
_Slot = collections.namedtuple("_Slot", "name label")
_Group = collections.namedtuple("_Group", "options optional")
_PATTERN_LEX = re.compile(r"\{\s*([a-z_0-9]+)\s*(?::\s*([a-z_0-9]+)\s*)?\}|[()\[\]|]|[^\s()\[\]|{}]+|[{}]")


def compile_pattern(text, allowed_slots=None):
    items = []
    for m in _PATTERN_LEX.finditer(text or ""):
        chunk = m.group(0)
        if m.group(1):
            if allowed_slots is not None and m.group(1) not in allowed_slots:
                raise PackError(f"unknown slot {{{m.group(1)}}} in {text!r}")
            items.append(("slot", m.group(1), m.group(2) or m.group(1)))
        elif chunk in ("{", "}"):
            raise PackError(f"bad slot in {text!r}")
        elif chunk in "()[]|":
            items.append((chunk,))
        else:
            items.extend(("lit", t.norm) for t in tokenize(chunk) if t.kind != "punct")
    pos = [0]

    def parse_seq():
        seq = []
        while pos[0] < len(items):
            item = items[pos[0]]
            if item[0] in (")", "]", "|"):
                break
            pos[0] += 1
            if item[0] == "lit":
                seq.append(_Lit(item[1]))
            elif item[0] == "slot":
                seq.append(_Slot(item[1], item[2]))
            else:
                close = ")" if item[0] == "(" else "]"
                options = [parse_seq()]
                while pos[0] < len(items) and items[pos[0]][0] == "|":
                    pos[0] += 1
                    options.append(parse_seq())
                if pos[0] >= len(items) or items[pos[0]][0] != close:
                    raise PackError(f"unbalanced brackets in {text!r}")
                pos[0] += 1
                if not all(options) and item[0] == "(":
                    raise PackError(f"empty choice in {text!r}")
                seq.append(_Group(tuple(options), item[0] == "["))
        return tuple(seq)

    seq = parse_seq()
    if pos[0] != len(items):
        raise PackError(f"unbalanced brackets in {text!r}")
    if not seq:
        raise PackError(f"empty pattern {text!r}")
    return seq


def _match_seq(seq, k, ctx, i):
    """Every way `seq` (from element k) matches at token i: (end, captures, packs)."""
    if k == len(seq):
        yield i, {}, ()
        return
    for j, caps, packs in _match_element(seq[k], ctx, i):
        for end, caps2, packs2 in _match_seq(seq, k + 1, ctx, j):
            if caps:
                merged = dict(caps)
                merged.update(caps2)
            else:
                merged = caps2
            yield end, merged, packs + packs2


def _match_element(element, ctx, i):
    if isinstance(element, _Lit):
        if i < ctx.n and ctx.stream[i].norm == element.norm:
            yield i + 1, {}, ()
    elif isinstance(element, _Group):
        for option in element.options:
            yield from _match_seq(option, 0, ctx, i)
        if element.optional:
            yield i, {}, ()
    else:
        for j, value, packs in ctx.slot(element.name, i):
            yield j, {element.label: value}, packs


def _best(seq, ctx, i):
    best = None
    for end, caps, packs in _match_seq(seq, 0, ctx, i):
        if end > i and (best is None or end > best[0]):
            best = (end, caps, packs)
    return best


# ----------------------------------------------------------------------------
# Values read by slots
# ----------------------------------------------------------------------------

Num = collections.namedtuple("Num", "value digits zero")      # digits 0: a number word
Clock = collections.namedtuple("Clock", "hour minute h24")
Dur = collections.namedtuple("Dur", "unit n")
Part = collections.namedtuple("Part", "key first last default")
NumDate = collections.namedtuple("NumDate", "day month year")

# Word categories a pack fills, by pack field. The value is what the word means.
_WORD_LIST_FIELDS = {
    "clock_prefixes": "clock_prefix", "clock_suffixes": "clock_suffix",
    "next_before": "next_before", "next_after": "next_after",
    "this_before": "this_before", "this_after": "this_after",
    "every": "every_word", "every_other": "every_other", "repeat_leads": "repeat_lead",
    "day_prefixes": "day_prefix", "ordinal_day_prefixes": "ordinal_day_prefix",
    "weekday_prefixes": "weekday_prefix", "date_connectors": "date_connector",
    "noon": "noon_word", "midnight": "midnight_word",
}
_CATEGORIES = set(_WORD_LIST_FIELDS.values()) | {
    "number", "count", "weekday", "weekday_abbr", "weekday_plural", "month", "unit", "counted",
    "part", "rel_day", "repeat_word", "ordinal_suffix", "meridiem_word"}
_ENGINE_SLOTS = {"h", "hdigits", "m", "m2", "n", "hm", "day", "ordinal", "year", "numdate",
                 "numdate_dot", "dur", "idiom", "clocktime", "meridiem"}
KNOWN_SLOTS = _CATEGORIES | _ENGINE_SLOTS
PACK_SLOTS = {"h", "m", "n", "dur", "unit", "weekday", "month", "day", "part"}

# Leftover words of these kinds are reported as unparsed. (Not units: "ulang
# tahun" is a birthday, "3 hari" in a title is fine.)
_SIGNAL_CATEGORIES = ("clock_prefix", "clock_suffix", "every_word", "repeat_lead", "rel_day",
                      "part", "weekday", "month_name", "noon_word", "midnight_word")


class Lexicon:
    """The words and patterns of a set of packs, merged in priority order."""

    def __init__(self, packs):
        self.codes = tuple(p["code"] for p in packs)
        self.primary = self.codes[0] if self.codes else None
        self.date_order = packs[0].get("date_order", "DMY") if packs else "DMY"
        self.words = {}
        self.maxlen = {}
        self.fillers = set()
        self.ordinal_dot = False
        self.idioms = []
        self.markers = {}
        self.pack_templates = {"trigger": [], "relative": [], "recur": []}
        for pack in packs:
            self._add_pack(pack)

    def _add(self, category, phrase, value, code):
        key = _phrase_key(phrase)
        if not key:
            return
        table = self.words.setdefault(category, {})
        if key not in table:              # first pack wins
            table[key] = (value, code)
            self.maxlen[category] = max(self.maxlen.get(category, 0), len(key))

    def _add_pack(self, p):
        code = p["code"]
        add = lambda category, phrase, value=True: self._add(category, phrase, value, code)
        for word, value in p.get("numbers", {}).items():
            add("number", word, value)
        for word in p.get("count_words", []):
            add("count", word, 1)
        for index, names in enumerate(p.get("weekdays", [])):
            for word in names:
                add("weekday", word, index)
        for index, names in enumerate(p.get("weekday_abbreviations", [])):
            for word in names:
                add("weekday_abbr", word, index)
        for index, names in enumerate(p.get("weekday_plurals", [])):
            for word in names:
                add("weekday_plural", word, index)
        for index, names in enumerate(p.get("months", [])):
            for position, word in enumerate(names):
                add("month", word, index + 1)
                if position == 0:
                    add("month_name", word, index + 1)
        for word, value in p.get("relative_days", {}).items():
            if isinstance(value, int):
                add("rel_day", word, (value, None))
            else:
                add("rel_day", word, (value[0], _part(value[1])))
        for unit, words in p.get("units", {}).items():
            for word in words:
                add("unit", word, unit)
        for word, (unit, count) in p.get("counted_units", {}).items():
            add("counted", word, Dur(unit, count))
        for entry in p.get("parts_of_day", []):
            part = _part(entry["part"], entry.get("hours"), entry.get("default"))
            for word in entry["words"]:
                add("part", word, part)
        for word in p.get("meridiem_am", []):
            add("meridiem_word", word, "am")
        for word in p.get("meridiem_pm", []):
            add("meridiem_word", word, "pm")
        for field, category in _WORD_LIST_FIELDS.items():
            for word in p.get(field, []):
                add(category, word)
        for repeat, words in p.get("repeat_words", {}).items():
            for word in words:
                add("repeat_word", word, repeat)
        for suffix in p.get("ordinal_suffixes", []):
            if suffix == ".":
                self.ordinal_dot = True
            else:
                add("ordinal_suffix", suffix)
        for word in p.get("fillers", []):
            key = _phrase_key(word)
            if len(key) == 1:
                self.fillers.add(key[0])
        for idiom in p.get("clock_idioms", []):
            minutes = idiom.get("minutes")
            seq = compile_pattern(idiom["pattern"], PACK_SLOTS)
            slots = _slots_in(seq)
            if "h" not in slots or (minutes in ("+m", "-m")) != ("m" in slots):
                raise PackError(f"clock idiom {idiom['pattern']!r} needs {{h}}"
                                f"{' and {m}' if minutes in ('+m', '-m') else ''}")
            self.idioms.append((seq, minutes, code))
        for text in p.get("relative_patterns", []):
            seq = compile_pattern(text, PACK_SLOTS)
            if "dur" not in _slots_in(seq):
                raise PackError(f"relative pattern {text!r} needs {{dur}}")
            self.pack_templates["relative"].append(("pack", seq, code))
        for text in p.get("repeat_patterns", []):
            seq = compile_pattern(text, PACK_SLOTS)
            if not {"dur", "unit"} & _slots_in(seq):
                raise PackError(f"repeat pattern {text!r} needs {{dur}} or {{unit}}")
            self.pack_templates["recur"].append(("pack", seq, code))
        for text in p.get("triggers", []):
            self.pack_templates["trigger"].append(("pack", compile_pattern(text, set()), code))
        if p.get("infinitive_marker"):
            self.markers[code] = normalize(p["infinitive_marker"])

    def templates(self):
        """(kind, [(name, seq, code)]) in KIND_ORDER."""
        out = []
        for kind in KIND_ORDER:
            entries = list(_ENGINE_TEMPLATES.get(kind, []))
            entries += self.pack_templates.get(kind, [])
            if entries:
                out.append((kind, entries))
        return out

    def is_word(self, category, norm):
        return (norm,) in self.words.get(category, {})


def _slots_in(seq):
    found = set()
    for element in seq:
        if isinstance(element, _Slot):
            found.add(element.name)
        elif isinstance(element, _Group):
            for option in element.options:
                found |= _slots_in(option)
    return found


def _part(key, hours=None, default=None):
    first, last, standard = PARTS_OF_DAY[key]
    if hours:
        first, last = hours
    return Part(key, first, last, default or standard)


_lexicon_cache = {}


def lexicon(codes):
    """The merged Lexicon for these pack codes (in priority order)."""
    codes = tuple(codes)
    if codes not in _lexicon_cache:
        packs = [p for p in (when_packs.load_pack(c) for c in codes) if p]
        _lexicon_cache[codes] = Lexicon(packs)
    return _lexicon_cache[codes]


class _Ctx:
    """One sentence being read with one Lexicon."""

    def __init__(self, lex, stream):
        self.lex = lex
        self.stream = stream
        self.n = len(stream)

    def lookup(self, category, i):
        table = self.lex.words.get(category)
        if not table or i >= self.n:
            return
        for length in range(min(self.lex.maxlen[category], self.n - i), 0, -1):
            entry = table.get(tuple(t.norm for t in self.stream[i:i + length]))
            if entry:
                yield i + length, entry[0], (entry[1],)

    def slot(self, name, i):
        special = _SLOTS.get(name)
        if special:
            return special(self, i)
        return self.lookup(name, i)

    def tight(self, i, kind=None):
        """Token i exists, touches the one before it, and has this kind."""
        return (i < self.n and not self.stream[i].space_before
                and (kind is None or self.stream[i].kind == kind))


def _nums(ctx, i):
    if i >= ctx.n:
        return
    t = ctx.stream[i]
    if t.kind == "num":
        yield i + 1, Num(int(t.text), len(t.text), len(t.text) > 1 and t.text[0] == "0"), ()
    else:
        for end, value, packs in ctx.lookup("number", i):
            yield end, Num(value, 0, False), packs


def _slot_h(ctx, i):
    for end, num, packs in _nums(ctx, i):
        if num.digits <= 2 and 0 <= num.value <= 24:
            yield end, num, packs


def _slot_hdigits(ctx, i):
    for end, num, packs in _nums(ctx, i):
        if 1 <= num.digits <= 2 and 0 <= num.value <= 24:
            yield end, num, packs


def _slot_m(ctx, i):
    for end, num, packs in _nums(ctx, i):
        if num.digits <= 2 and 0 <= num.value <= 59:
            yield end, num, packs


def _slot_m2(ctx, i):
    # Minutes right after an hour ("jam 8 15", "at eight thirty"): two digits or a word.
    for end, num, packs in _nums(ctx, i):
        if num.digits in (0, 2) and 10 <= num.value <= 59:
            yield end, num, packs


def _slot_n(ctx, i):
    for end, num, packs in _nums(ctx, i):
        if num.digits <= 3 and 1 <= num.value <= 999:
            yield end, num, packs
    for end, value, packs in ctx.lookup("count", i):
        yield end, Num(value, 0, False), packs


def _slot_hm(ctx, i):
    """8:30, 08.30, 20.00 (not 5.10.2026, a date)."""
    s = ctx.stream
    if i + 2 >= ctx.n:
        return
    t0, t1, t2 = s[i], s[i + 1], s[i + 2]
    if not (t0.kind == "num" and len(t0.text) <= 2 and t1.kind == "mark" and t1.text in ".:"
            and ctx.tight(i + 1) and t2.kind == "num" and len(t2.text) == 2 and ctx.tight(i + 2)):
        return
    hour, minute = int(t0.text), int(t2.text)
    if hour > 24 or minute > 59 or (hour == 24 and minute):
        return
    if ctx.tight(i + 3, "mark") and ctx.tight(i + 4, "num"):
        return
    zero = len(t0.text) > 1 and t0.text[0] == "0"
    yield i + 3, Clock(hour, minute, hour >= 13 or hour == 0 or zero), ()


def _slot_day(ctx, i):
    for end, num, packs in _nums(ctx, i):
        if num.digits > 2 or not 1 <= num.value <= 31:
            continue
        if num.digits and ctx.tight(end):
            nxt = ctx.stream[end]
            if nxt.kind == "word" and ctx.lex.is_word("ordinal_suffix", nxt.norm):
                yield end + 1, num.value, packs
            elif nxt.text == "." and not ctx.tight(end + 1, "num"):
                yield end + 1, num.value, packs
        yield end, num.value, packs


def _slot_ordinal(ctx, i):
    for end, num, packs in _nums(ctx, i):
        if not (1 <= num.digits <= 2 and 1 <= num.value <= 31) or not ctx.tight(end):
            continue
        nxt = ctx.stream[end]
        if nxt.kind == "word" and ctx.lex.is_word("ordinal_suffix", nxt.norm):
            yield end + 1, num.value, packs
        elif nxt.text == "." and ctx.lex.ordinal_dot and not ctx.tight(end + 1, "num"):
            yield end + 1, num.value, packs


def _slot_year(ctx, i):
    if i < ctx.n and ctx.stream[i].kind == "num" and len(ctx.stream[i].text) == 4:
        value = int(ctx.stream[i].text)
        if 1900 <= value <= 2199:
            yield i + 1, value, ()


def _numbers_joined(ctx, i, separators):
    """d<sep>m[<sep>y] with no spaces: (end, a, b, year or None, sep)."""
    s = ctx.stream
    if not (i < ctx.n and s[i].kind == "num" and len(s[i].text) <= 2):
        return None
    if not (ctx.tight(i + 1, "mark") and s[i + 1].text in separators
            and ctx.tight(i + 2, "num") and len(s[i + 2].text) <= 2):
        return None
    sep = s[i + 1].text
    end, year = i + 3, None
    if ctx.tight(end, "mark") and s[end].text == sep and ctx.tight(end + 1, "num") \
            and len(s[end + 1].text) in (2, 4):
        year = int(s[end + 1].text)
        year = 2000 + year if year < 100 else year
        end += 2
    return end, int(s[i].text), int(s[i + 2].text), year, sep


def _ordered(ctx, a, b, year):
    return NumDate(a, b, year) if ctx.lex.date_order == "DMY" else NumDate(b, a, year)


def _slot_numdate(ctx, i):
    """5/10, 5/10/2026, 5-10-2026, 5.10.2026 ("-" and "." need the year)."""
    found = _numbers_joined(ctx, i, "/-.")
    if found:
        end, a, b, year, sep = found
        if sep == "/" or year is not None:
            yield end, _ordered(ctx, a, b, year), ()


def _slot_numdate_dot(ctx, i):
    """German 5.10. (after "am"): day, month and a closing dot."""
    found = _numbers_joined(ctx, i, ".")
    if found:
        end, a, b, year, _sep = found
        if year is None and ctx.tight(end) and ctx.stream[end].text == "." \
                and not ctx.tight(end + 1, "num"):
            yield end + 1, _ordered(ctx, a, b, None), ()


def _slot_dur(ctx, i):
    for j, num, packs in _slot_n(ctx, i):
        for end, unit, packs2 in ctx.lookup("unit", j):
            yield end, Dur(unit, num.value), packs + packs2
    for end, dur, packs in ctx.lookup("counted", i):
        yield end, dur, packs


def _slot_idiom(ctx, i):
    """A pack's half/quarter idiom: "setengah 9", "Viertel vor acht", "half past eight"."""
    for seq, minutes, code in ctx.lex.idioms:
        for end, caps, packs in _match_seq(seq, 0, ctx, i):
            hour = caps["h"].value
            if minutes in ("+m", "-m"):
                offset = caps["m"].value if minutes == "+m" else -caps["m"].value
            else:
                offset = minutes
            total = hour * 60 + offset
            if total < 0:
                total += 24 * 60
            yield end, Clock(total // 60, total % 60, hour >= 13), packs + (code,)


def _slot_clocktime(ctx, i):
    yield from _slot_hm(ctx, i)
    yield from _slot_idiom(ctx, i)
    for end, num, packs in _slot_h(ctx, i):
        h24 = num.value >= 13 or (num.digits > 0 and (num.zero or num.value == 0))
        yield end, Clock(num.value, 0, h24), packs
        for end2, minute, packs2 in _slot_m2(ctx, end):
            yield end2, Clock(num.value, minute.value, h24), packs + packs2


def _slot_meridiem(ctx, i):
    """am/pm, except where the word is also a pack's "on" before a weekday or a
    date (German "am Montag", "am 5.")."""
    for end, value, packs in ctx.lookup("meridiem_word", i):
        key = tuple(t.norm for t in ctx.stream[i:end])
        doubles = (key in ctx.lex.words.get("weekday_prefix", {})
                   or key in ctx.lex.words.get("ordinal_day_prefix", {}))
        if doubles and (any(ctx.lookup("weekday", end)) or any(ctx.lookup("weekday_abbr", end))
                        or any(_slot_day(ctx, end))):
            continue
        yield end, value, packs


_SLOTS = {
    "h": _slot_h, "hdigits": _slot_hdigits, "m": _slot_m, "m2": _slot_m2, "n": _slot_n,
    "hm": _slot_hm, "day": _slot_day, "ordinal": _slot_ordinal, "year": _slot_year,
    "numdate": _slot_numdate, "numdate_dot": _slot_numdate_dot, "dur": _slot_dur,
    "idiom": _slot_idiom, "clocktime": _slot_clocktime, "meridiem": _slot_meridiem,
}


# ----------------------------------------------------------------------------
# Engine templates: only slots, never words
# ----------------------------------------------------------------------------

_PART_AFTER = "[{part:part_after} [{this_after:this_day}]]"


def _t(name, text):
    return (name, compile_pattern(text, KNOWN_SLOTS), None)


_ENGINE_TEMPLATES = {
    "recur": [
        _t("unit", "[{repeat_lead}] {every_word} {unit}"),
        _t("n_unit", "[{repeat_lead}] {every_word} {n} {unit}"),
        _t("every_other_unit", "[{repeat_lead}] {every_other} {unit}"),
        _t("weekday", "[{repeat_lead}] {every_word} [{weekday_prefix}] ({weekday}|{weekday_abbr})"),
        _t("day", "[{repeat_lead}] {every_word} ({day_prefix} {day}|{ordinal_day_prefix} {ordinal})"),
        _t("part", "[{repeat_lead}] {every_word} {part}"),
        _t("word", "[{repeat_lead}] {repeat_word}"),
        _t("plural", "[{repeat_lead}] [{weekday_prefix}] {weekday_plural}"),
    ],
    "period": [
        _t("period_next", "{next_before} {unit}"),
        _t("period_next", "{unit} {next_after}"),
    ],
    "date": [
        _t("dmy", "[{day_prefix}|{ordinal_day_prefix}] {day} [{date_connector}] {month} [{year}]"),
        _t("mdy", "{month} {day} [{year}]"),
        _t("num", "[{day_prefix}|{ordinal_day_prefix}] {numdate}"),
        _t("num", "({day_prefix}|{ordinal_day_prefix}) {numdate_dot}"),
    ],
    "day_of_month": [
        _t("plain", "{day_prefix} {day}"),
        _t("ordinal", "{ordinal_day_prefix} {ordinal}"),
    ],
    "clock_time": [
        _t("prefix", "[{part:part_before}] {clock_prefix} {clocktime} "
                     "[{clock_suffix} [{m:minute_after}]] [{meridiem}] " + _PART_AFTER),
        _t("suffix", "[{part:part_before}] {clocktime} {clock_suffix} [{m:minute_after}] "
                     "[{meridiem}] " + _PART_AFTER),
        _t("hm", "[{part:part_before}] {hm:clocktime} [{meridiem}] " + _PART_AFTER),
        _t("idiom", "[{part:part_before}] {idiom:clocktime} [{clock_suffix}] [{meridiem}] "
                    + _PART_AFTER),
        _t("meridiem", "[{part:part_before}] {h:hour} {meridiem} " + _PART_AFTER),
        _t("part", "{hdigits:hour} {part:part_after} [{this_after:this_day}]"),
        _t("at_noon", "[{clock_prefix}] {noon_word}"),
        _t("at_midnight", "[{clock_prefix}] {midnight_word}"),
    ],
    "rel_day": [_t("rel_day", "{rel_day}")],
    "this_part": [
        _t("this_part", "{this_before} {part}"),
        _t("this_part", "{part} {this_after}"),
    ],
    "weekday": [
        _t("weekday", "[{weekday_prefix}] [{next_before}|{this_before}] {weekday} "
                      "[{next_after}|{this_after}]"),
        _t("weekday", "({weekday_prefix}|{next_before}|{this_before}) {weekday_abbr} "
                      "[{next_after}|{this_after}]"),
    ],
    "part": [_t("part", "{part}")],
}


# ----------------------------------------------------------------------------
# Reading a sentence
# ----------------------------------------------------------------------------

Atom = collections.namedtuple("Atom", "kind name start end caps packs")


def _scan(ctx):
    """Left to right, the longest template match at each token."""
    atoms, i, title_started = [], 0, False
    templates = ctx.lex.templates()
    while i < ctx.n:
        best = None
        for kind, entries in templates:
            if kind == "trigger" and title_started:
                continue
            for name, seq, code in entries:
                found = _best(seq, ctx, i)
                if found and (best is None or found[0] > best[0]):
                    packs = found[2] + ((code,) if code else ())
                    best = (found[0], kind, name, found[1], packs)
        if best:
            end, kind, name, caps, packs = best
            atoms.append(Atom(kind, name, i, end, caps, _unique(packs)))
            i = end
        else:
            title_started = True
            i += 1
    return atoms


def _unique(items):
    out = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return tuple(out)


def _accept_weak_parts(atoms, primary):
    """A part of the day standing alone counts only next to another date or
    time, with another phrase of its pack, or, when nothing else says when,
    in the Hariku language (see the module notes)."""
    kept, rejected = [], []
    for atom in atoms:
        if atom.kind != "part":
            kept.append(atom)
            continue
        # A trigger ("ingatkan aku") shows the language, but isn't a date or time.
        evidence = [a for a in atoms if a is not atom and a.kind != "part"]
        timing = [a for a in evidence if a.kind != "trigger"]
        adjacent = any(a.end == atom.start or a.start == atom.end for a in timing)
        same_pack = any(set(a.packs) & set(atom.packs) for a in evidence)
        alone = not timing and primary in atom.packs
        (kept if adjacent or same_pack or alone else rejected).append(atom)
    return kept, rejected


class _Builder:
    def __init__(self):
        self.c = {"title": "", "recurrence": "none", "interval": 1}
        self.conflicts = []
        self.problems = []

    def put(self, field, value):
        if value is None:
            return
        old = self.c.get(field)
        if old is None:
            self.c[field] = value
        elif old != value:
            self.conflicts.append(field)

    def put_part(self, part):
        if part is None:
            return
        self.put("part_of_day", part.key)
        base = PARTS_OF_DAY[part.key]
        if (part.first, part.last, part.default) != base and self.c.get("part_of_day") == part.key:
            self.c.setdefault("part_hours", [part.first, part.last])
            self.c.setdefault("part_default", part.default)

    def put_clock(self, clock):
        self.put("hour", clock.hour)
        self.put("minute", clock.minute)
        if clock.h24:
            self.c["hour_24"] = True

    def put_repeat(self, recurrence, interval=1):
        if self.c["recurrence"] == "none":
            self.c["recurrence"] = recurrence
            self.c["interval"] = interval
        elif (self.c["recurrence"], self.c["interval"]) != (recurrence, interval):
            self.conflicts.append("recurrence")

    def put_repeat_unit(self, unit, n):
        repeat = {"day": "daily", "week": "weekly", "month": "monthly", "year": "yearly"}.get(unit)
        if repeat:
            self.put_repeat(repeat, n)
        else:
            self.problems.append("unsupported_repeat")

    def add(self, atom):
        caps, kind = atom.caps, atom.kind
        if kind == "recur":
            if "every_other" in caps:
                self.put_repeat_unit(caps["unit"], 2)
            elif "dur" in caps:
                self.put_repeat_unit(caps["dur"].unit, caps["dur"].n)
            elif "unit" in caps:
                self.put_repeat_unit(caps["unit"], caps["n"].value if "n" in caps else 1)
            elif "repeat_word" in caps:
                self.put_repeat(caps["repeat_word"])
            elif "weekday_plural" in caps:
                self.put_repeat("weekly")
                self.put("weekday", caps["weekday_plural"])
            elif "weekday" in caps or "weekday_abbr" in caps:
                self.put_repeat("weekly")
                self.put("weekday", caps.get("weekday", caps.get("weekday_abbr")))
            elif "day" in caps or "ordinal" in caps:
                self.put_repeat("monthly")
                self.put("day_of_month", caps.get("day", caps.get("ordinal")))
            elif "part" in caps:
                self.put_repeat("daily")
                self.put_part(caps["part"])
        elif kind == "relative":
            dur = caps["dur"]
            if dur.unit == "minute":
                self.put("minutes_from_now", dur.n)
            elif dur.unit == "hour":
                self.put("minutes_from_now", dur.n * 60)
            elif dur.unit == "day":
                self.put("day_offset", dur.n)
            elif dur.unit == "week":
                self.put("day_offset", dur.n * 7)
            elif dur.unit == "month":
                self.put("month_offset", dur.n)
            else:
                self.put("year_offset", dur.n)
        elif kind == "period":
            field = {"week": "week_offset", "month": "month_offset", "year": "year_offset"}.get(
                caps["unit"])
            if field:
                self.put(field, 1)
        elif kind == "date":
            if "numdate" in caps or "numdate_dot" in caps:
                value = caps.get("numdate") or caps.get("numdate_dot")
                self.put("day_of_month", value.day)
                self.put("month", value.month)
                self.put("year", value.year)
            else:
                self.put("day_of_month", caps["day"])
                self.put("month", caps["month"])
                self.put("year", caps.get("year"))
        elif kind == "day_of_month":
            self.put("day_of_month", caps.get("day", caps.get("ordinal")))
        elif kind == "clock_time":
            if "noon_word" in caps:
                self.put_clock(Clock(12, 0, True))
            elif "midnight_word" in caps:
                self.put_clock(Clock(24, 0, True))
            else:
                clock = caps.get("clocktime")
                if clock is None:
                    num = caps["hour"]
                    clock = Clock(num.value, 0, num.value >= 13 or num.zero
                                  or (num.digits > 0 and num.value == 0))
                if "minute_after" in caps and clock.minute == 0:
                    clock = Clock(clock.hour, caps["minute_after"].value, clock.h24)
                self.put_clock(clock)
            self.put("meridiem", caps.get("meridiem"))
            self.put_part(caps.get("part_before") or caps.get("part_after"))
            if "this_day" in caps:
                self.put("day_offset", 0)
        elif kind == "rel_day":
            days, part = caps["rel_day"]
            self.put("day_offset", days)
            self.put_part(part)
        elif kind == "this_part":
            self.put("day_offset", 0)
            self.put_part(caps["part"])
        elif kind == "weekday":
            self.put("weekday", caps.get("weekday", caps.get("weekday_abbr")))
        elif kind == "part":
            self.put_part(caps["part"])


def _title(text, tokens, consumed, lex, trigger_packs):
    """The words no template took, without fillers and punctuation at the
    edges of each stretch, the first letter in capitals."""
    segments, current = [], []
    for index, token in enumerate(tokens):
        if consumed[index]:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)

    def edge_junk(token):
        return token.kind in ("punct", "mark") or token.norm in lex.fillers

    pieces = []
    for seg in segments:
        while seg and edge_junk(seg[0]):
            seg = seg[1:]
        while seg and edge_junk(seg[-1]):
            seg = seg[:-1]
        if seg:
            pieces.append(text[seg[0].start:seg[-1].end])
    title = " ".join(" ".join(pieces).split())
    for code in trigger_packs:
        marker = lex.markers.get(code)
        words = title.split(" ")
        if marker and len(words) >= 3 and normalize(words[-2]) == marker:
            title = " ".join(words[:-2] + words[-1:])
    return title


def parse(text, now=None, language=None, packs=None, default_date=None):
    """Read one sentence. `language` is the Hariku (UI) language, which comes
    first; `packs` is the list of pack codes to use (default: the Hariku
    language, English and Indonesian). `default_date` (a datetime.date) is
    the date for a sentence that says a time or a repeat but no date; without
    it, that is today or tomorrow. Returns a Result."""
    now = now or datetime.datetime.now()
    codes = list(packs) if packs is not None else when_packs.default_codes(language or "en")
    lex = lexicon(codes)
    tokens = tokenize(text)
    stream_index = [i for i, t in enumerate(tokens) if t.kind != "punct"]
    stream = [tokens[i] for i in stream_index]
    ctx = _Ctx(lex, stream)

    atoms = _scan(ctx)
    atoms, rejected = _accept_weak_parts(atoms, lex.primary)

    builder = _Builder()
    consumed = [False] * len(tokens)
    trigger_packs, trigger_text, recognised, used = [], "", [], []
    for atom in atoms:
        for k in range(atom.start, atom.end):
            consumed[stream_index[k]] = True
        phrase = text[stream[atom.start].start:stream[atom.end - 1].end]
        if atom.kind == "trigger":
            trigger_packs.extend(atom.packs)
            trigger_text = phrase
        else:
            builder.add(atom)
            recognised.append(phrase)
        used.extend(atom.packs)

    builder.c["title"] = _title(text, tokens, consumed, lex, trigger_packs)
    result = resolve(builder.c, now, default_date=default_date)
    result.text = text or ""
    result.recognised = recognised
    result.trigger = trigger_text
    result.packs = [c for c in lex.codes if c in used]
    for problem in builder.problems + (["conflict"] if builder.conflicts else []):
        if problem not in result.problems:
            result.problems.append(problem)

    rejected_tokens = {stream_index[k] for a in rejected for k in range(a.start, a.end)}
    leftover, unparsed = [], []
    for index, token in enumerate(tokens):
        if consumed[index] or token.kind not in ("word", "num"):
            continue
        leftover.append(token.text)
        if token.norm in lex.fillers and index not in rejected_tokens:
            continue
        if token.kind == "num" or index in rejected_tokens or any(
                lex.is_word(category, token.norm) for category in _SIGNAL_CATEGORIES):
            unparsed.append(token.text)
    result.leftover = leftover
    result.unparsed = unparsed
    result.confidence = _confidence(result)
    return result


# ----------------------------------------------------------------------------
# From components to a date and time
# ----------------------------------------------------------------------------

_RANGES = {
    "day_offset": (-3660, 3660), "weekday": (0, 6), "week_offset": (0, 520),
    "month_offset": (0, 120), "year_offset": (0, 10), "day_of_month": (1, 31), "month": (1, 12),
    "year": (1900, 2199), "hour": (0, 24), "minute": (0, 59), "minutes_from_now": (1, 527040),
    "interval": (1, 999),
}
_DATE_FIELDS = ("day_offset", "weekday", "week_offset", "month_offset", "year_offset",
                "day_of_month", "month", "year")


def _clean_components(raw):
    """Components with the right types; values out of range become problems.
    An AI's output goes through here too, so nothing is trusted."""
    raw = raw if isinstance(raw, dict) else {}
    c, problems = {}, []
    for field, (low, high) in _RANGES.items():
        value = raw.get(field)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value.strip())
        if value is None or isinstance(value, bool) or not isinstance(value, int):
            c[field] = None
            continue
        if not low <= value <= high:
            problems.append("invalid_time" if field in ("hour", "minute") else "invalid_date")
            value = None
        c[field] = value
    c["interval"] = c["interval"] or 1
    c["hour_24"] = raw.get("hour_24") is True
    c["meridiem"] = raw.get("meridiem") if raw.get("meridiem") in ("am", "pm") else None
    c["part_of_day"] = raw.get("part_of_day") if raw.get("part_of_day") in PARTS_OF_DAY else None
    hours, default = raw.get("part_hours"), raw.get("part_default")
    c["part_hours"] = hours if (isinstance(hours, (list, tuple)) and len(hours) == 2
                                and all(isinstance(h, int) for h in hours)) else None
    c["part_default"] = default if when_packs.is_clock(default) else None
    recurrence = raw.get("recurrence") or "none"
    if recurrence not in RECURRENCES:
        problems.append("unsupported_repeat")
        recurrence = "none"
    c["recurrence"] = recurrence
    if recurrence == "none":
        c["interval"] = 1
    title = raw.get("title")
    c["title"] = title if isinstance(title, str) else ""
    return c, problems


def _add_months(day, months):
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def _calendar_date(day, month, year, year_offset, today):
    if year is None and year_offset:
        year = today.year + year_offset
    if year is not None:
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None
    for candidate_year in range(today.year, today.year + 9):
        try:
            candidate = datetime.date(candidate_year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    return None


def _day_of_month_date(day, month_offset, today):
    if month_offset:
        first = _add_months(today.replace(day=1), month_offset)
        if day > calendar.monthrange(first.year, first.month)[1]:
            return None
        return first.replace(day=day)
    first = today.replace(day=1)
    for k in range(0, 13):
        month_start = _add_months(first, k)
        if day <= calendar.monthrange(month_start.year, month_start.month)[1]:
            candidate = month_start.replace(day=day)
            if candidate >= today:
                return candidate
    return None


def _weekday_date(weekday, week_offset, today):
    if week_offset:
        monday = today - datetime.timedelta(days=today.weekday())
        return monday + datetime.timedelta(weeks=week_offset, days=weekday)
    ahead = (weekday - today.weekday()) % 7 or 7
    return today + datetime.timedelta(days=ahead)


def _resolve_date(c, today):
    """(date or None, problems). A calendar date beats a weekday, which beats
    a day offset; disagreeing ones add "conflict"."""
    candidates, problems = [], []
    if c["day_of_month"] is not None:
        if c["month"] is not None:
            found = _calendar_date(c["day_of_month"], c["month"], c["year"], c["year_offset"], today)
        else:
            found = _day_of_month_date(c["day_of_month"], c["month_offset"], today)
        if found is None:
            return None, ["invalid_date"]
        candidates.append(found)
    elif c["month"] is not None or c["year"] is not None:
        return None, ["invalid_date"]      # a month or year without a day
    if c["weekday"] is not None:
        candidates.append(_weekday_date(c["weekday"], c["week_offset"], today))
    if c["day_offset"] is not None:
        candidates.append(today + datetime.timedelta(days=c["day_offset"]))
    if not candidates:
        if c["week_offset"]:
            candidates.append(today + datetime.timedelta(weeks=c["week_offset"]))
        elif c["month_offset"]:
            candidates.append(_add_months(today, c["month_offset"]))
        elif c["year_offset"]:
            candidates.append(_add_months(today, 12 * c["year_offset"]))
    if len(set(candidates)) > 1:
        problems.append("conflict")
    return (candidates[0] if candidates else None), problems


def _at(day, minutes):
    return datetime.datetime.combine(day, datetime.time(0, 0)) + datetime.timedelta(minutes=minutes)


def _part_range(c):
    first, last, default = PARTS_OF_DAY[c["part_of_day"]]
    if c["part_hours"]:
        first, last = c["part_hours"]
    return first, last, c["part_default"] or default


def _fixed_minutes(c):
    """Minutes after midnight (over 1440 is the next day) when the hour is not
    ambiguous, else None."""
    hour, minute = c["hour"], c["minute"] or 0
    if hour >= 13:
        return hour * 60 + minute
    if c["meridiem"] == "am":
        return (hour % 12) * 60 + minute
    if c["meridiem"] == "pm":
        return (hour % 12 + 12) * 60 + minute
    if c["part_of_day"]:
        first, last, _default = _part_range(c)
        low, high = first * 60, last * 60 + 59
        base = (hour % 12) * 60 + minute
        candidates = (base, base + 720, base + 1440)
        inside = [m for m in candidates if low <= m <= high]
        if inside:
            return inside[0]
        return min(candidates, key=lambda m: (low - m if m < low else m - high, -m))
    if c["hour_24"]:
        return hour * 60 + minute
    return None


def _minutes(text):
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def resolve(components, now=None, default_date=None):
    """Turn the neutral components (COMPONENT_FIELDS) into a date and time,
    with the rules in the module notes. This is where a future AI fallback
    comes in: it only says "tomorrow, 8, evening", never a date.
    `default_date`: see parse()."""
    c, problems = _clean_components(components)
    now = (now or datetime.datetime.now()).replace(second=0, microsecond=0)
    today = now.date()
    if isinstance(default_date, datetime.datetime):
        default_date = default_date.date()
    elif not isinstance(default_date, datetime.date):
        default_date = None
    r = Result()
    r.components = c
    title = " ".join(c["title"].split())
    r.title = title[:1].upper() + title[1:]
    r.recurrence, r.interval = c["recurrence"], c["interval"]
    final = None

    if c["minutes_from_now"] is not None:
        final = now + datetime.timedelta(minutes=c["minutes_from_now"])
        if c["hour"] is not None or any(c[f] is not None for f in _DATE_FIELDS):
            problems.append("conflict")
    elif not any(p in ("invalid_date", "invalid_time") for p in problems):
        day, date_problems = _resolve_date(c, today)
        problems += date_problems
        repeating = c["recurrence"] != "none"
        if (day is None and default_date is not None and "invalid_date" not in problems
                and (c["hour"] is not None or c["part_of_day"] or repeating)):
            # The caller's date (the reminder dialog's), as if it had been said.
            day = default_date
            r.date_assumed = True
        if "invalid_date" in problems:
            pass
        elif c["hour"] is not None:
            fixed = _fixed_minutes(c)
            if fixed is not None:
                if day is None:
                    day = today if _at(today, fixed) > now else today + datetime.timedelta(days=1)
                    r.date_assumed = True
                final = _at(day, fixed)
            else:
                base = (c["hour"] % 12) * 60 + (c["minute"] or 0)
                if day is None and not repeating:
                    # A one-off with no date: the next upcoming of the two.
                    r.date_assumed = True
                    options = sorted(_at(d, m) for d in (today, today + datetime.timedelta(days=1))
                                     for m in (base, base + 720))
                    final = next(o for o in options if o > now)
                else:
                    # The daytime rule, 07:00-18:59.
                    b = c["hour"] % 12
                    primary = base if DAYTIME_FIRST_HOUR <= b <= 11 else base + 720
                    other = base + 720 if primary == base else base
                    if day is None:
                        r.date_assumed = True
                        day = today if _at(today, primary) > now else today + datetime.timedelta(days=1)
                        final = _at(day, primary)
                    else:
                        final = _at(day, primary)
                        if day == today and final <= now and _at(day, other) > now:
                            final = _at(day, other)
        elif c["part_of_day"]:
            minutes = _minutes(_part_range(c)[2])
            if day is None:
                r.date_assumed = True
                day = today if _at(today, minutes) > now else today + datetime.timedelta(days=1)
            final = _at(day, minutes)
        elif day is not None or repeating:
            r.time_assumed = True
            if day is None:
                r.date_assumed = True
                day = today if _at(today, DEFAULT_MINUTES) > now else today + datetime.timedelta(days=1)
            final = _at(day, DEFAULT_MINUTES)
        else:
            problems.append("nothing_found")

    if final is not None:
        r.date = final.strftime("%Y-%m-%d")
        r.time = final.strftime("%H:%M")
        r.in_past = final <= now
    if not r.title:
        problems.append("no_title")
    r.problems = list(_unique(problems))
    r.confidence = _confidence(r)
    return r


def _confidence(r):
    """0-1, how sure the reading is: 1 for a clear sentence."""
    if "nothing_found" in r.problems:
        return 0.0
    score = 1.0
    if r.time_assumed:
        score -= 0.3
    score -= min(0.6, 0.2 * len(r.unparsed))
    if "conflict" in r.problems:
        score -= 0.3
    if "no_title" in r.problems:
        score -= 0.4
    if r.in_past:
        score -= 0.2
    if any(p in ("invalid_date", "invalid_time", "unsupported_repeat") for p in r.problems):
        score = min(score, 0.2)
    return round(max(0.0, min(1.0, score)), 2)
