# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Reading a sentence said to Aruna for Calculator & Converter. No wx here, no
AI: rules only, on this computer.

    read(text, context) -> Query or None

A Query's `kind` says what was asked:
  "calc"        arithmetic ("25 x 4", "berapa 12 persen dari 350"); a
                follow-up on the last result ("tambah 5", "hasilnya kali 2")
                is one too, with `followup` set
  "error"       arithmetic that can't be worked out (`error`: "div_zero",
                "too_big", ..., "syntax", "no_result")
  "convert"     units ("2 kaki berapa inci", "5 km to miles")
  "money"       currencies ("100 dolar berapa rupiah", "kurs dolar")
  "percent_of"  "20 itu berapa persen dari 80"
  "say_last"    "berapa hasilnya": the last result again
  "hint"        a measure without a unit to convert to ("berapa 5 km")
  "coin", "dice", "random", "split", "discount"

`sure` is True when the sentence is clearly one of these without any lead
word ("25 x 4", "5 km ke mil"): Aruna's matcher takes only those, so a bare
sentence is never taken from another command. Sentences that start with a
word such as "berapa", "hitung" or "what's" come through Aruna's patterns
and may be read more loosely. A bare sum that reads like a date, a time or a
phone number ("25/12", "10:30", "0812-3456-7890") is not sure.

Lead words are dropped first ("tolong hitung", "berapa", "what's", "how
much is"), then trailing ones ("?", "=", "berapa", "sama dengan"). Then, in
this order: the extras, "what percent", a conversion, the last result, a
remainder ("sisa bagi 17 dan 5"), arithmetic.
"""

import collections
import re
from fractions import Fraction

import calculator_math as calc
import calculator_money as money
import calculator_numbers as numbers
import calculator_units as units
from calculator_numbers import Tok, norm_at

MAX_CHARS = 200
MAX_DICE = 10
MAX_SIDES = 1000
MAX_PEOPLE = 1000
MAX_RANDOM_SPAN = 10 ** 12


class Query:
    def __init__(self, kind, sure=False, **fields):
        self.kind = kind
        self.sure = sure
        self.__dict__.update(fields)

    def get(self, name, default=None):
        return self.__dict__.get(name, default)

    def __repr__(self):
        fields = {k: v for k, v in self.__dict__.items() if k not in ("kind", "sure", "mtoks")}
        return f"Query({self.kind!r}, sure={self.sure}, {fields})"


# What the reader needs to know: the user's language (for "1.250" and
# "2,5"), the last result (or None when there is none, or it is too old),
# the data-size convention (1024 or 1000) and the home currency.
Context = collections.namedtuple("Context", "language last convention home")
Last = collections.namedtuple("Last", "value unit currency")


def context(language="en", last=None, convention=1024, home="USD"):
    return Context(language, last, convention, home)


def _phrase(words):
    return tuple(t.norm for t in numbers.tokenize(words))


def _phrases(*texts):
    return sorted({_phrase(t) for t in texts}, key=lambda p: -len(p))


FILLERS = _phrases("tolong", "coba", "aruna", "hariku", "hai", "halo", "hey", "hi", "please",
                   "ok", "okay", "oke", "eh", "dong", "ya", "yuk", "ayo", "can you", "could you",
                   "would you", "tell me", "kasih tahu", "beri tahu", "kasih tau", "tolong dong",
                   "mau tanya", "aku mau tanya", "i want to know", "do you know", "dan", "and",
                   "so", "jadi", "terus", "lalu", "then", "sekarang", "now")
STRONG_LEADS = _phrases("hitung", "hitungkan", "hitunglah", "hitungin", "kalkulasi",
                        "kalkulasikan", "kalkulator", "calculate", "compute", "calc", "konversi",
                        "konversikan", "convert", "ubah", "ubahkan", "solve", "work out")
WEAK_LEADS = _phrases("berapa", "berapakah", "brp", "what is", "what's", "whats", "what",
                      "what are", "what was", "how much is", "how much are", "how much",
                      "how many", "hasil dari", "nilai dari", "is", "berapa hasil dari",
                      "berapa sih", "berapa ya")
TRAILING = _phrases("?", "=", "berapa", "berapa ya", "berapa sih", "sama dengan",
                    "sama dengan berapa", "equals", "equals what", "is what", "ya", "dong",
                    "please", "itu berapa", "jadi berapa", "jadinya berapa", "jadinya",
                    "hari ini", "sekarang", "saat ini", "today", "now", "right now", "sih",
                    "berapa hasilnya", "=?", ".", "!?")
QUESTION_WORDS = {("berapa",), ("berapakah",), ("brp",), ("how", "many"), ("how", "much"),
                  ("berapa", "sih"), ("berapa", "ya")}

# Words that stand for the last result.
REFERENCES = _phrases("hasilnya", "hasil tadi", "hasil itu", "hasil terakhir",
                      "hasil sebelumnya", "hasil barusan", "the result", "the last result",
                      "that result", "the answer", "the previous result", "that", "ans")
# A sentence that starts with one of these works on the last result: "tambah 5".
FOLLOW_OPS = {"+", "-", "*", "/", "^", "mod"}

CONNECTORS = _phrases("sama dengan berapa", "itu berapa", "jadi berapa", "jadinya berapa",
                      "sama dengan", "is how many", "are how many", "equals how many",
                      "is how much", "in terms of", "berapa", "ke", "jadi", "menjadi", "dalam",
                      "dlm", "in", "to", "into", "as", "equals", "=", "-> ", "→", "ke dalam",
                      "is", "are", "itu", "sama dengan berapa banyak", "berapa banyak")
AFTER_CONNECTOR = _phrases("berapa", "berapa banyak", "how many", "how much", "what")
PAIR_JOINERS = _phrases("dan", "and", "&", ",", "plus")
QUESTION_GAPS = _phrases("are there in", "is there in", "are in", "is in", "are there",
                         "in", "is", "are", "dalam", "di", "untuk", "dari", "pada", "ada di",
                         "ada dalam", "per", "for")
RATE_LEADS = _phrases("kurs", "nilai tukar", "exchange rate", "the exchange rate",
                      "exchange rate of", "the exchange rate of", "exchange rate for",
                      "kurs dari", "harga")
RATE_JOINERS = _phrases("ke", "to", "terhadap", "dalam", "in", "against", "vs", "versus",
                        "per", "dengan")

MOD_LEADS = _phrases("sisa bagi", "sisa pembagian", "sisa hasil bagi", "sisa dari",
                     "remainder of", "the remainder of", "remainder when", "the remainder when",
                     "sisa")
MOD_JOINERS = _phrases("dan", "dengan", "oleh", "dibagi", "dibagi dengan", "bagi", "by",
                       "divided by", "is divided by", "and", "mod", "modulo", ",")
FACTORIAL_LEADS = _phrases("faktorial", "factorial", "faktorial dari", "factorial of",
                           "the factorial of")

COIN_VERBS = _phrases("lempar", "lemparkan", "lempar sebuah", "flip", "toss", "flip a",
                      "toss a", "lempar satu", "kocok")
COIN_WORDS = _phrases("koin", "coin", "uang logam", "uang koin", "a coin", "coins")
DICE_VERBS = _phrases("lempar", "lemparkan", "kocok", "roll", "throw", "toss", "roll a",
                      "roll the", "throw a", "lempar sebuah", "lempar satu", "kocokkan")
DICE_WORDS = _phrases("dadu", "die", "dice", "dadunya", "the dice", "the die")
SIDES_WORDS = _phrases("sisi", "sided", "sides", "muka")
RANDOM_LEADS = _phrases("angka acak", "angka random", "bilangan acak", "nomor acak",
                        "random number", "a random number", "pick a number",
                        "pick a random number", "pilih angka", "pilih angka acak",
                        "pilihkan angka", "pilihkan angka acak", "acak angka", "random",
                        "kasih angka acak", "choose a number", "give me a random number")
RANGE_STARTS = _phrases("antara", "dari", "between", "from")
RANGE_JOINERS = _phrases("sampai", "hingga", "ke", "dan", "to", "and", "through", "-", "sd",
                         "s/d", "sampai dengan")
RANGE_UPTO = _phrases("sampai", "hingga", "up to", "to", "maksimal", "max")
SPLIT_LEADS = _phrases("bagi tagihan", "bagi bill", "bagi rata", "patungan", "split the bill",
                       "split the check", "split bill", "split", "bagi tagihannya",
                       "split the bill of", "bagi bon")
PEOPLE_WORDS = _phrases("orang", "people", "persons", "person", "ways", "way", "cara",
                        "kepala", "pax")
PEOPLE_STARTS = _phrases("untuk", "jadi", "ke", "dengan", "between", "among", "by", "for",
                         "with", "buat", "sama", "bareng", "dibagi", "dibagi ke")
TIP_WORDS = _phrases("tip", "tips", "tipnya", "gratuity")
DISCOUNT_WORDS = _phrases("diskon", "potongan", "potongan harga", "discount", "disc", "korting")
OFF_WORDS = _phrases("off",)


def _match(toks, i, phrases):
    """The end of the first phrase that starts at token i, or None."""
    for phrase in phrases:
        n = len(phrase)
        if n and tuple(t.norm for t in toks[i:i + n]) == phrase:
            return i + n
    return None


def _match_end(toks, phrases):
    """The start of the first phrase that ends the tokens, or None."""
    for phrase in phrases:
        n = len(phrase)
        if n and len(toks) >= n and tuple(t.norm for t in toks[-n:]) == phrase:
            return len(toks) - n
    return None


def _strip(toks):
    """(tokens, lead words dropped, strength): "strong" for a calculating verb
    ("hitung", "convert"), "weak" for a question word ("berapa", "what's")."""
    lead, strength = [], None
    changed = True
    while changed and toks:
        changed = False
        for phrases, kind in ((STRONG_LEADS, "strong"), (WEAK_LEADS, "weak"), (FILLERS, None)):
            end = _match(toks, 0, phrases)
            if end is not None and end < len(toks):
                lead.append(tuple(t.norm for t in toks[:end]))
                if kind == "strong" or (kind == "weak" and strength is None):
                    strength = kind
                toks = toks[end:]
                changed = True
                break
    changed = True
    while changed and len(toks) > 1:
        changed = False
        start = _match_end(toks, TRAILING)
        if start is not None and start > 0:
            if tuple(t.norm for t in toks[start:]) in (("berapa",), ("berapa", "ya"),
                                                        ("berapa", "sih")):
                lead.append(("berapa",))
                strength = strength or "weak"
            toks = toks[:start]
            changed = True
    return toks, lead, strength


# ------------------------------------------------------------
# Guards for bare sums
# ------------------------------------------------------------

_DATE_LIKE = [
    re.compile(r"^\s*\d{1,2}\s*[/.-]\s*\d{1,2}(\s*[/.-]\s*\d{2,4})?\s*$"),
    re.compile(r"^\s*\d{4}\s*[/-]\s*\d{1,2}\s*[/-]\s*\d{1,2}\s*$"),
    re.compile(r"^\s*\d{1,2}\s*:\s*\d{2}(\s*:\s*\d{2})?\s*$"),
    re.compile(r"^\s*\+?\d[\d\s]*(-[\d\s]+){2,}$"),                       # 0812-3456-7890
    re.compile(r"^\s*\+\d[\d\s-]{6,}$"),                                  # +62 812 ...
]


def date_like(text):
    return any(r.match(text) for r in _DATE_LIKE)


# ------------------------------------------------------------
# The last result
# ------------------------------------------------------------

def _mark_references(toks):
    """The tokens with each "hasilnya" / "the result" as one Tok of kind
    "last", and whether there was one."""
    out, found, i = [], False, 0
    while i < len(toks):
        end = _match(toks, i, REFERENCES)
        if end is not None:
            out.append(Tok("last", "", "last", toks[i].start, toks[end - 1].end, toks[i].glued))
            found = True
            i = end
            continue
        out.append(toks[i])
        i += 1
    return out, found


def _starts_with_operator(toks):
    """Whether a sentence begins with a binary operator ("tambah 5",
    "kali dua", "divided by 3", "pangkat 2") rather than a number."""
    if not toks or numbers.read_number(toks, 0) is not None:
        return False
    if toks[0].norm == "-" and len(toks) > 1 and toks[1].glued and toks[1].kind == "num":
        return False                         # "-5 + 3" typed: a new sum
    found = calc._phrase_at(toks, 0)
    return found is not None and found[0].kind == "op" and found[0].value in FOLLOW_OPS


# ------------------------------------------------------------
# Quantities and units
# ------------------------------------------------------------

Side = collections.namedtuple("Side", "units currency end")


def _side(toks, i):
    """The unit(s) and/or currency named at token i: Side, or None."""
    unit = units.unit_at(toks, i)
    currency = money.currency_at(toks, i, with_pound=True)
    if unit is None and currency is None:
        return None
    unit_end = unit[1] if unit else -1
    currency_end = currency[1] if currency else -1
    if unit_end > currency_end:
        return Side(unit[0], None, unit_end)
    if currency_end > unit_end:
        return Side([], currency[0], currency_end)
    return Side(unit[0], currency[0], unit_end)


def _se_word(toks, i):
    """ "sekilo", "semeter", "seliter": one of a unit, as one word. Returns
    the Side of the unit, or None."""
    if i >= len(toks) or toks[i].kind != "word":
        return None
    t = toks[i].norm
    if not t.startswith("se") or len(t) < 4:
        return None
    rest = numbers.tokenize(t[2:])
    found = units.unit_at(rest, 0)
    if found and found[1] == len(rest):
        return Side(found[0], None, i + 1)
    return None


def _quantity(toks, i, language):
    """(value, end, currency from a symbol or None) of an amount at token i:
    "2", "dua setengah", "-40", "minus 40", "$100", "Rp 1,5 juta", "a"."""
    sign = 1
    if norm_at(toks, i) in ("-", "minus", "negatif", "negative"):
        sign, i = -1, i + 1
    symbol = money.symbol_at(toks, i)
    code = None
    if symbol is not None:
        code, i = symbol
    number = numbers.read_number(toks, i, language)
    if number is None:
        if code is None and norm_at(toks, i) in ("a", "an") and sign == 1:
            return 1, i + 1, None
        return None
    return sign * number[0], number[1], code


def _source(toks, i, language):
    """What is converted, from token i: (amount, Side, end), several amounts of
    one kind added up ("5 kaki 11 inci", "1 jam 30 menit"), or None."""
    se = _se_word(toks, i)
    if se is not None:
        return 1, se, se.end
    quantity = _quantity(toks, i, language)
    if quantity is None:
        return None
    value, j, code = quantity
    if code is not None:
        # "$100", "Rp 50.000", perhaps named again: "Rp 50.000 rupiah"
        again = money.currency_at(toks, j)
        if again is not None and again[0] == code:
            j = again[1]
        return value, Side([], code, j), j
    side = _side(toks, j)
    if side is None:
        return None
    if side.units and not side.currency:
        # More amounts of the same kind: "5 kaki 11 inci"
        parts = [(value, side)]
        k = side.end
        while k < len(toks):
            more = _quantity(toks, k, language)
            if more is None or more[2] is not None:
                break
            more_side = _side(toks, more[1])
            if more_side is None or not more_side.units:
                break
            if units.category_of(more_side.units) != units.category_of(side.units):
                break
            parts.append((more[0], more_side))
            k = more_side.end
        if len(parts) > 1:
            return parts, side, k
    return value, side, side.end


def _target(toks, i):
    """(Side, second unit id or None, end) of what to convert to: "inci",
    "kaki dan inci", "feet and inches", or None."""
    side = _side(toks, i)
    if side is None:
        return None
    j = _match(toks, side.end, PAIR_JOINERS)
    if j is not None and side.units:
        second = _side(toks, j)
        if second is not None and second.units:
            for big in side.units:
                for small in second.units:
                    if (big, small) in units.PAIRS:
                        return Side([big], None, second.end), small, second.end
    return side, None, side.end


def _convert_query(amount, src, dst, pair, context, sure):
    """A Query for amount src -> dst when they fit: money or units, or None."""
    if src.currency and dst.currency and not (src.units and dst.units and not pair
                                              and _only_pound(src) and _only_pound(dst)):
        if src.currency == dst.currency or isinstance(amount, list):
            return None
        return Query("money", sure=sure, amount=amount, src=src.currency, dst=dst.currency)
    if src.units and dst.units:
        picked = units.pick(src.units, dst.units)
        if picked is None:
            return None
        s, d = picked
        if isinstance(amount, list):
            total = 0
            for value, side in amount:
                one = units.pick(side.units, [s])
                if one is None:
                    return None
                total += units.to_base(value, one[0], context.convention)
            return Query("convert", sure=sure, amount=total, src=s, dst=d, pair=pair,
                         in_base=True, parts=amount)
        if pair is not None and units.UNITS[pair].category != units.UNITS[d].category:
            return None
        return Query("convert", sure=sure, amount=amount, src=s, dst=d, pair=pair,
                     in_base=False)
    return None


def _only_pound(side):
    return side.currency == "GBP" and "lb" in side.units


def _read_conversion(toks, lead, strength, context):
    language = context.language
    question = bool(lead) and lead[-1] in QUESTION_WORDS or ("berapa",) in lead
    # "kurs dolar", "exchange rate of the euro to yen"
    rate = _read_rate(toks, context)
    if rate is not None:
        return rate
    # "2 kaki berapa inci", "100 dolar ke rupiah", "5 kaki 11 inci ke cm"
    source = _source(toks, 0, language)
    if source is not None:
        amount, src, k = source
        if k == len(toks):
            # No unit to convert to: money goes home; a measure asks which unit.
            if not (lead or strength):
                return None
            if src.currency and not (src.units and not question):
                home = context.home if src.currency != context.home else \
                    ("USD" if context.home != "USD" else "EUR")
                if isinstance(amount, list):
                    return None
                return Query("money", sure=False, amount=amount, src=src.currency, dst=home)
            if src.units:
                return Query("hint", sure=False, what="no_target")
            return None
        j = _match(toks, k, CONNECTORS)
        if j is None:
            return None
        j = _match(toks, j, AFTER_CONNECTOR) or j
        target = _target(toks, j)
        if target is None or target[2] != len(toks):
            return None
        dst, pair, _end = target
        return _convert_query(amount, src, dst, pair, context, sure=True)
    # "berapa inci 2 kaki", "how many inches are in 2 feet"
    if question:
        target = _target(toks, 0)
        if target is None:
            return None
        dst, pair, j = target
        j = _match(toks, j, QUESTION_GAPS) or j
        source = _source(toks, j, language)
        if source is None or source[2] != len(toks):
            return None
        amount, src, _k = source
        return _convert_query(amount, src, dst, pair, context, sure=False)
    return None


def _read_rate(toks, context):
    """ "kurs dolar", "kurs euro ke yen", "exchange rate of the dollar"."""
    j = _match(toks, 0, RATE_LEADS)
    if j is None:
        return None
    if norm_at(toks, j) == "the":
        j += 1
    src = money.currency_at(toks, j, with_pound=True)
    if src is None:
        return None
    code, k = src
    dst = None
    if k < len(toks):
        m = _match(toks, k, RATE_JOINERS)
        if m is None:
            return None
        found = money.currency_at(toks, m, with_pound=True)
        if found is None or found[1] != len(toks):
            return None
        dst = found[0]
    if dst is None:
        dst = context.home if code != context.home else ("USD" if context.home != "USD" else "EUR")
    if dst == code:
        return None
    return Query("money", sure=True, amount=1, src=code, dst=dst, rate=True)


# ------------------------------------------------------------
# Arithmetic
# ------------------------------------------------------------

def _looks_like_a_sum(toks):
    """A number and an operator somewhere ("hitung 5 apel tambah 3 jeruk"),
    so "hitung" was meant for us; "hitung mundur 90 detik" has none."""
    numeric = any(t.kind == "num" for t in toks) or \
        any(numbers.read_number(toks, i) is not None for i in range(len(toks)))
    operator = False
    for i in range(len(toks)):
        found = calc._phrase_at(toks, i)
        if found is not None and found[0].kind in ("op", "pct", "fact", "sq", "cube", "func"):
            operator = True
            break
    return numeric and operator


def _read_arithmetic(toks, lead, strength, context, raw):
    marked, has_reference = _mark_references(toks)
    followup = False
    if _starts_with_operator(marked):
        if context.last is not None:
            marked = [Tok("last", "", "last", 0, 0, False)] + marked
            followup = True
        elif calc._phrase_at(marked, 0)[0].value not in ("-", "+"):
            return None                     # "kali dua" with nothing to multiply
        # else a sign: "minus tiga kali dua" is -3 * 2
    last_value = context.last.value if context.last is not None else None
    try:
        mtoks = calc.lex(marked, context.language, last=last_value)
    except calc.CalcError:
        if strength == "strong" and _looks_like_a_sum(toks):
            return Query("error", sure=False, error="syntax")
        return None
    uses_last = followup or any(m.kind == "last" for m in mtoks)
    if uses_last and context.last is None:
        if calc.has_operator(mtoks):
            return Query("error", sure=True, error="no_result")
        return None
    operator = calc.has_operator(mtoks)
    if not operator and not (strength and any(m.kind == "pct" for m in mtoks)):
        return None
    sure = operator and (uses_last or not date_like(raw))
    try:
        value = calc.evaluate(mtoks)
    except calc.CalcError as e:
        if e.kind == "syntax":
            if strength == "strong":
                return Query("error", sure=False, error="syntax")
            return None
        return Query("error", sure=sure, error=e.kind, mtoks=mtoks)
    return Query("calc", sure=sure, mtoks=mtoks, value=value, followup=uses_last)


def _read_mod(toks, context):
    """ "sisa bagi 17 dan 5", "remainder of 17 divided by 5"."""
    j = _match(toks, 0, MOD_LEADS)
    if j is None:
        return None
    first = _signed_number(toks, j, context.language)
    if first is None:
        return None
    k = _match(toks, first[1], MOD_JOINERS)
    if k is None:
        return None
    second = _signed_number(toks, k, context.language)
    if second is None or second[1] != len(toks):
        return None
    mtoks = [calc.MTok("num", first[0]), calc.MTok("op", "mod"), calc.MTok("num", second[0])]
    try:
        value = calc.evaluate(mtoks)
    except calc.CalcError as e:
        return Query("error", sure=True, error=e.kind, mtoks=mtoks)
    return Query("calc", sure=True, mtoks=mtoks, value=value, followup=False)


def _signed_number(toks, i, language):
    sign = 1
    if norm_at(toks, i) in ("-", "minus", "negatif", "negative"):
        sign, i = -1, i + 1
    found = numbers.read_number(toks, i, language)
    if found is None:
        return None
    return sign * found[0], found[1]


def _read_percent_question(toks, lead, context):
    """ "20 itu berapa persen dari 80", "berapa persen 20 dari 80", "20 is what
    percent of 80", "what percentage of 80 is 20"."""
    language = context.language
    norms = [t.norm for t in toks]
    pct_words = ("persen", "%", "percent", "percentage", "prosen")

    def number_between(start, end):
        found = _signed_number(toks, start, language)
        return found[0] if found is not None and found[1] == end else None

    def index_of(seq):
        n = len(seq)
        for s in range(len(norms) - n + 1):
            if tuple(norms[s:s + n]) == seq:
                return s
        return None

    for middle in (("itu", "berapa"), ("berapa",), ("is", "what"), ("adalah", "berapa")):
        for word in pct_words:
            for tail in (("dari",), ("of",)):
                seq = middle + (word,) + tail
                at = index_of(seq)
                if at is not None and at > 0:
                    a = number_between(0, at)
                    b = number_between(at + len(seq), len(toks))
                    if a is not None and b is not None:
                        return Query("percent_of", sure=True, part=a, whole=b)
    asked = ("berapa",) in lead or (bool(lead) and lead[-1] in (("what",), ("what", "is")))
    if asked and norms and norms[0] in pct_words:
        # "berapa persen 20 dari 80" / "what percent of 80 is 20"
        for tail in ("dari", "of"):
            if tail not in norms:
                continue
            at = norms.index(tail)
            if tail == "dari":
                a, b = number_between(1, at), number_between(at + 1, len(toks))
                if a is not None and b is not None:
                    return Query("percent_of", sure=False, part=a, whole=b)
            else:
                if "is" in norms[at:]:
                    is_at = at + norms[at:].index("is")
                    b, a = number_between(at + 1, is_at), number_between(is_at + 1, len(toks))
                    if a is not None and b is not None:
                        return Query("percent_of", sure=False, part=a, whole=b)
    return None


# ------------------------------------------------------------
# Extras: a coin, dice, a random number, splitting a bill, a discount
# ------------------------------------------------------------

def _read_coin(toks):
    j = _match(toks, 0, COIN_VERBS)
    if j is None:
        return None
    j = _match(toks, j, (("a",), ("sebuah",), ("satu",), ("the",))) or j
    k = _match(toks, j, COIN_WORDS)
    if k is None or k != len(toks):
        return None
    return Query("coin", sure=True)


def _read_dice(toks, language):
    j = _match(toks, 0, DICE_VERBS)
    if j is None:
        return None
    count, sides = 1, 6
    # "roll 2d6", "roll a d20"
    j = _match(toks, j, (("a",), ("sebuah",), ("the",))) or j
    number = numbers.read_number(toks, j, language)
    if number is not None and number[0].denominator == 1:
        count, j = int(number[0]), number[1]
    if norm_at(toks, j) == "d" and j + 1 < len(toks) and toks[j + 1].kind == "num" \
            and toks[j + 1].glued:
        sides = int(toks[j + 1].text) if toks[j + 1].text.isdigit() else 0
        j += 2
    else:
        k = _match(toks, j, DICE_WORDS)
        if k is None:
            return None
        j = k
        # "dadu 20 sisi", "20-sided die" is rare enough: "dadu 20 sisi" only
        sided = numbers.read_number(toks, j, language)
        if sided is not None:
            end = _match(toks, sided[1], SIDES_WORDS)
            if end is not None and sided[0].denominator == 1:
                sides, j = int(sided[0]), end
    if j != len(toks):
        return None
    if not (1 <= count <= MAX_DICE and 2 <= sides <= MAX_SIDES):
        return Query("error", sure=True, error="dice")
    return Query("dice", sure=True, count=count, sides=sides)


def _read_random(toks, language):
    j = _match(toks, 0, RANDOM_LEADS)
    if j is None:
        return None
    low, high = Fraction(1), Fraction(100)
    if j < len(toks):
        k = _match(toks, j, RANGE_STARTS) or j
        first = _signed_number(toks, k, language)
        if first is not None:
            m = _match(toks, first[1], RANGE_JOINERS)
            second = _signed_number(toks, m, language) if m is not None else None
            if second is None or second[1] != len(toks):
                return None
            low, high = first[0], second[0]
        else:
            m = _match(toks, j, RANGE_UPTO)
            upper = _signed_number(toks, m, language) if m is not None else None
            if upper is None or upper[1] != len(toks):
                return None
            low, high = Fraction(1), upper[0]
    if low.denominator != 1 or high.denominator != 1:
        return Query("error", sure=True, error="random")
    low, high = int(low), int(high)
    if low > high:
        low, high = high, low
    if high - low > MAX_RANDOM_SPAN:
        return Query("error", sure=True, error="random")
    return Query("random", sure=True, low=low, high=high)


def _money_amount(toks, i, language):
    """(value, currency or None, end) of an amount with an optional currency:
    "350 ribu", "Rp 350.000", "120 dollars", "$120"."""
    quantity = _quantity(toks, i, language)
    if quantity is None or quantity[1] == i:
        return None
    value, j, code = quantity
    if code is None:
        found = money.currency_at(toks, j)
        if found is not None:
            code, j = found
    elif money.currency_at(toks, j) is not None and money.currency_at(toks, j)[0] == code:
        j = money.currency_at(toks, j)[1]
    return value, code, j


_PERCENT_SIGNS = (("%",), ("persen",), ("percent",), ("prosen",))
_PERCENT_JOINERS = {"plus", "dengan", "dan", "with", "and", "a", "+", "ditambah", "including",
                    "termasuk", "pakai", "pake"}


def _take_percent(toks, words, language, before=True, after=True):
    """Find "<words> N%" or "N% <words>" anywhere: (percent, tokens without
    it and the word joining it, like "plus" or "with a") or None."""
    for i in range(len(toks)):
        start = i
        while start > 0 and toks[start - 1].norm in _PERCENT_JOINERS:
            start -= 1
        end = _match(toks, i, words)
        if end is not None and after:
            k = _match(toks, end, (("sebesar",), ("of",), ("nya",))) or end
            found = numbers.read_number(toks, k, language)
            if found is not None:
                p = _match(toks, found[1], _PERCENT_SIGNS) or found[1]
                return found[0], toks[:start] + toks[p:]
        if before:
            found = numbers.read_number(toks, i, language)
            if found is not None:
                p = _match(toks, found[1], _PERCENT_SIGNS)
                if p is not None:
                    w = _match(toks, p, words)
                    if w is not None:
                        return found[0], toks[:start] + toks[w:]
    return None


def _read_split(toks, language):
    j = _match(toks, 0, SPLIT_LEADS)
    if j is None:
        return None
    rest = toks[j:]
    tip = 0
    taken = _take_percent(rest, TIP_WORDS, language)
    if taken is not None:
        tip, rest = taken
    rest = list(rest)
    if rest and rest[0].norm in ("of", "sebesar", "senilai", "total"):
        rest = rest[1:]
    # The number of people ends the sentence ("... 4 orang", "... 3 ways"); the
    # amount is what comes before it ("100 ribu 3 orang" is 100 ribu for 3).
    end = _match_end(rest, PEOPLE_WORDS)
    end = len(rest) if end is None else end
    found = None
    for i in range(1, end):
        people = numbers.read_number(rest, i, language)
        if people is None or people[1] != end:
            continue
        head = rest[:i]
        while head and _match_end(head, PEOPLE_STARTS) is not None:
            head = head[:_match_end(head, PEOPLE_STARTS)]
        amount = _money_amount(head, 0, language) if head else None
        if amount is not None and amount[2] == len(head):
            found = amount, people[0]
            break
    if found is None:
        return None
    (value, code, _end), count = found
    if count.denominator != 1 or not (1 <= count <= MAX_PEOPLE):
        return Query("error", sure=True, error="people")
    if value < 0 or tip < 0 or tip > 100:
        return Query("error", sure=True, error="syntax")
    return Query("split", sure=True, amount=value, people=int(count), tip=tip, currency=code)


def _read_discount(toks, language):
    """ "diskon 30% dari 250 ribu", "250 ribu diskon 30%", "30% off 250",
    "potongan 20 persen untuk 100 ribu"."""
    taken = _take_percent(toks, DISCOUNT_WORDS, language) or \
        _take_percent(toks, OFF_WORDS, language, after=False)
    if taken is None:
        return None
    percent, rest = taken
    rest = list(rest)
    while rest and rest[0].norm in ("dari", "untuk", "buat", "of", "on", "from", "harga", "price",
                                    "for", "the", "a", "pada", "di", "dengan", "with", "at"):
        rest = rest[1:]
    while rest and rest[-1].norm in ("dengan", "with", "at", "dapat", "dapet", "get", "kena",
                                     "pakai", "pake", "setelah", "after", "harga"):
        rest = rest[:-1]
    amount = _money_amount(rest, 0, language)
    if amount is None or amount[2] != len(rest):
        return None
    value, code, _end = amount
    if not (0 <= percent <= 100) or value < 0:
        return Query("error", sure=True, error="percent")
    return Query("discount", sure=True, amount=value, percent=percent, currency=code)


# ------------------------------------------------------------
# Reading
# ------------------------------------------------------------

def read(text, context_):
    """What `text` asks, as a Query, or None when it isn't for Calculator &
    Converter. `context_` is a Context. The Query's `lead` says whether a
    lead word of ours came with it ("berapa", "hitung", "what's")."""
    raw = " ".join(str(text or "").split())
    if not raw or len(raw) > MAX_CHARS:
        return None
    toks = numbers.tokenize(raw)
    if not toks:
        return None
    toks, lead, strength = _strip(toks)
    if not toks:
        return None
    query = _read(raw, toks, lead, strength, context_)
    if query is not None:
        query.lead = strength is not None
    return query


def _read(raw, toks, lead, strength, context_):
    language = context_.language
    stripped = raw[toks[0].start:toks[-1].end]
    for reader in (_read_coin, lambda t: _read_dice(t, language),
                   lambda t: _read_random(t, language), lambda t: _read_split(t, language)):
        query = reader(toks)
        if query is not None:
            return query
    query = _read_percent_question(toks, lead, context_)
    if query is not None:
        return query
    query = _read_discount(toks, language)
    if query is not None:
        return query
    query = _read_conversion(toks, lead, strength, context_)
    if query is not None:
        return query
    marked, has_reference = _mark_references(toks)
    if has_reference and len(marked) == 1:
        # "berapa hasilnya", "what was the result"
        if context_.last is None:
            return Query("error", sure=False, error="no_result")
        return Query("say_last", sure=False)
    query = _read_mod(toks, context_)
    if query is not None:
        return query
    if _match(toks, 0, FACTORIAL_LEADS) is not None:
        # "faktorial 7" -> "7 faktorial"
        j = _match(toks, 0, FACTORIAL_LEADS)
        toks = toks[j:] + [Tok("word", "faktorial", "faktorial", 0, 0, False)]
    return _read_arithmetic(toks, lead, strength, context_, stripped)
