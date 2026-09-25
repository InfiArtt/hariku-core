# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Numbers for Calculator & Converter: reading them as typed or as Voice Control
writes them, in Indonesian and English, and writing them back for the user's
language. No wx here.

    tokenize(text)                     -> [Tok]
    numeral_value("1.250.000", "id")   -> Fraction(1250000)
    read_number(toks, i, language)     -> (Fraction, end) or None
    present(value, language, decimals) -> Shown (the digits, whether rounded)
    format_decimal(Decimal, language)  -> "1.250.000,5" / "1,250,000.5"

Digits. Indonesian writes "2,5" and "1.250.000", English "2.5" and
"1,250,000". A number with both marks ("1.250,75", "1,250.75") uses the last
one for the decimals. With one mark, the language decides: in Indonesian a
dot followed by exactly three digits groups thousands ("1.250" is 1250) and
anything else is a decimal point ("1.5", and a comma always: "2,5"); in
English the same holds for the comma ("1,250" is 1250, "2,5" is 2.5). Several
marks of one kind are thousands ("1.250.000", "1,250,000"), and so is one mark
before "000" in either language ("25,000" said in Indonesian is 25000, not
25).

Words, as whisper writes them: "dua puluh lima", "seratus dua belas", "dua
ribu dua puluh enam", "satu juta dua ratus ribu", "setengah", "seperempat",
"tiga perempat", "satu setengah", "sejuta setengah", "satu koma lima", "nol
koma nol lima"; "twenty-five", "one hundred and twelve", "a hundred", "a
million", "one and a half", "three quarters", "two thirds", "one point five",
"a dozen"; and digits with scale words: "2 juta", "350 ribu", "350rb",
"1,5 miliar", "3.5 million", "250k". Signs ("minus tiga") belong to the
sentence, not the number.

Values are exact fractions (fractions.Fraction), so 0.1 + 0.2 is 0.3 and
100 / 3 * 3 is 100.
"""

import collections
import math
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction

# Languages that write a decimal comma and group thousands with dots.
COMMA_DECIMAL = {"id", "de", "nl", "es", "it", "pt", "tr", "ru", "pl", "cs", "da", "ro", "vi"}

ID_ONES = {"nol": 0, "kosong": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
           "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9}
EN_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
           "seven": 7, "eight": 8, "nine": 9}
EN_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
            "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60,
           "seventy": 70, "eighty": 80, "ninety": 90}
ONES = dict(ID_ONES, **EN_ONES)

# Scale words after a number ("2 juta", "tiga ribu", "3.5 million"). Single
# letters only count glued to digits ("250k").
SCALES = {"ribu": 1000, "rb": 1000, "juta": 10 ** 6, "jt": 10 ** 6, "miliar": 10 ** 9,
          "milyar": 10 ** 9, "milliar": 10 ** 9, "triliun": 10 ** 12, "trilyun": 10 ** 12,
          "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9, "bn": 10 ** 9,
          "trillion": 10 ** 12, "lusin": 12, "dozen": 12}
GLUED_SCALES = {"k": 1000}
# "seribu" is one thousand, "sejuta" one million.
SE_SCALES = {"seribu": 1000, "sejuta": 10 ** 6, "semiliar": 10 ** 9, "semilyar": 10 ** 9,
             "setriliun": 10 ** 12, "selusin": 12}
# Fractions said by themselves ("setengah dari 80", "half of 80").
FRACTION_WORDS = {"setengah": Fraction(1, 2), "separuh": Fraction(1, 2),
                  "seperempat": Fraction(1, 4), "sepertiga": Fraction(1, 3),
                  "half": Fraction(1, 2)}
# ...after "a" or "one": "a quarter", "one third".
EN_PARTS = {"half": 2, "third": 3, "quarter": 4, "fourth": 4, "fifth": 5}
# ...after a count: "tiga perempat", "two thirds".
COUNTED_PARTS = {"perempat": 4, "pertiga": 3, "perlima": 5, "quarters": 4, "thirds": 3,
                 "fourths": 4, "fifths": 5}
UNICODE_FRACTIONS = {"½": Fraction(1, 2), "¼": Fraction(1, 4), "¾": Fraction(3, 4),
                     "⅓": Fraction(1, 3), "⅔": Fraction(2, 3), "⅛": Fraction(1, 8)}
DECIMAL_WORDS = {"koma", "point"}
ARTICLES = {"a", "an"}

MAX_DIGITS = 60          # a numeral longer than this is not read

# Tokens: numbers (with their marks), words (letters, inner apostrophes; "m²"
# and "½" count as letters), and single symbols.
Tok = collections.namedtuple("Tok", "kind text norm start end glued")
_TOKEN_RE = re.compile(r"(?P<num>\d+(?:[.,]\d+)*|(?<!\d)[.,]\d+)"
                       r"|(?P<word>[^\W\d_]+(?:['’][^\W\d_]+)*)"
                       r"|(?P<sym>\*\*|[^\w\s])")
_SYMBOLS = {"−": "-", "–": "-", "—": "-", "‒": "-", "·": "*", "⋅": "*", "✕": "×", "✖": "×",
            "＋": "+", "／": "/", "＝": "=", "’": "'"}


def fold(text):
    """Lower case without accents: "Réaumur" -> "reaumur". "½" and "²" stay
    as they are (NFD, not NFKD, which would make "½" three characters)."""
    text = unicodedata.normalize("NFD", str(text or "")).casefold()
    return "".join(c for c in text if not unicodedata.combining(c))


def tokenize(text):
    """[Tok] of a sentence. A hyphen between two words joins them
    ("twenty-five", "km-per-jam") and is dropped."""
    toks, previous_end = [], None
    for m in _TOKEN_RE.finditer(str(text or "")):
        kind = m.lastgroup
        raw = m.group(0)
        norm = _SYMBOLS.get(raw, raw) if kind == "sym" else fold(raw).replace("’", "'")
        glued = previous_end is not None and m.start() == previous_end
        toks.append(Tok(kind, raw, norm, m.start(), m.end(), glued))
        previous_end = m.end()
    kept = []
    for i, tok in enumerate(toks):
        if tok.kind == "sym" and tok.norm == "-" and 0 < i < len(toks) - 1 \
                and toks[i - 1].kind == "word" and toks[i + 1].kind == "word" \
                and tok.glued and toks[i + 1].glued:
            continue
        kept.append(tok)
    return kept


def norm_at(toks, i):
    return toks[i].norm if 0 <= i < len(toks) else ""


# ------------------------------------------------------------
# Numerals: "1.250.000", "2,5", "1,250.75"
# ------------------------------------------------------------

def _grouped(groups):
    """Thousand groups: 1 to 3 digits first, then exactly 3 each."""
    return 1 <= len(groups[0]) <= 3 and all(len(g) == 3 for g in groups[1:])


def _fraction(whole, frac):
    whole = whole or "0"
    if frac:
        return Fraction(int(whole + frac), 10 ** len(frac))
    return Fraction(int(whole))


def numeral_value(raw, language="en"):
    """The value of a numeral as typed, read with the language's marks (see
    the module notes), or None when its marks make no sense ("1.2.3")."""
    raw = str(raw or "").strip()
    if not raw or len(raw) > MAX_DIGITS:
        return None
    if raw[0] in ".,":
        raw = "0" + raw
    marks = [c for c in raw if c in ".,"]
    if not marks:
        return Fraction(int(raw))
    if len(set(marks)) == 2:
        point = marks[-1]
        if raw.count(point) != 1:
            return None
        whole, frac = raw.rsplit(point, 1)
        groups = whole.split("," if point == "." else ".")
        return _fraction("".join(groups), frac) if _grouped(groups) else None
    parts = re.split(r"[.,]", raw)
    if len(parts) > 2:
        return Fraction(int("".join(parts))) if _grouped(parts) else None
    whole, frac = parts
    thousands_mark = "." if language in COMMA_DECIMAL else ","
    if len(frac) == 3 and not whole.startswith("0") and \
            (marks[0] == thousands_mark or frac == "000"):
        return Fraction(int(whole + frac))
    return _fraction(whole, frac)


# ------------------------------------------------------------
# Number words
# ------------------------------------------------------------

def _small_digit(tok):
    """A digits token 1..9 ("5 ratus")."""
    if tok is not None and tok.kind == "num" and tok.text.isdigit() and 1 <= int(tok.text) <= 9:
        return int(tok.text)
    return None


def _id_below_hundred(toks, i):
    t = norm_at(toks, i)
    if t == "sepuluh":
        return 10, i + 1
    if t == "sebelas":
        return 11, i + 1
    if t in ID_ONES:
        d = ID_ONES[t]
        nxt = norm_at(toks, i + 1)
        if nxt == "belas" and d >= 1:
            return 10 + d, i + 2
        if nxt == "puluh" and d >= 1:
            value, j = 10 * d, i + 2
            if ID_ONES.get(norm_at(toks, j), 0) >= 1:
                return value + ID_ONES[norm_at(toks, j)], j + 1
            return value, j
        return d, i + 1
    return None


def _en_below_hundred(toks, i):
    t = norm_at(toks, i)
    if t in EN_TENS:
        value, j = EN_TENS[t], i + 1
        if EN_ONES.get(norm_at(toks, j), 0) >= 1:
            return value + EN_ONES[norm_at(toks, j)], j + 1
        return value, j
    if t in EN_TEENS:
        return EN_TEENS[t], i + 1
    if t in EN_ONES:
        return EN_ONES[t], i + 1
    return None


def _below_hundred(toks, i):
    return _id_below_hundred(toks, i) or _en_below_hundred(toks, i)


def _hundreds(toks, i):
    """(value, end) of "seratus", "dua ratus", "5 ratus", "a hundred", "two
    hundred", or None."""
    t = norm_at(toks, i)
    if t == "seratus":
        return 100, i + 1
    nxt = norm_at(toks, i + 1)
    if nxt in ("ratus", "hundred"):
        d = ONES.get(t) if t in ONES else _small_digit(toks[i] if i < len(toks) else None)
        if t in ARTICLES and nxt == "hundred":
            d = 1
        if d:
            return d * 100, i + 2
    return None


def _below_thousand(toks, i):
    """(value, end) of a number 0-999 in words, or None."""
    found = _hundreds(toks, i)
    if found is not None:
        value, j = found
        k = j + 1 if norm_at(toks, j) == "and" and _below_hundred(toks, j + 1) else j
        rest = _below_hundred(toks, k)
        if rest is not None:
            return value + rest[0], rest[1]
        return value, j
    return _below_hundred(toks, i)


def _decimal_tail(toks, i):
    """(fraction, end) of "koma lima", "koma dua lima", "point one four",
    "koma 25" after a whole number, or None."""
    if norm_at(toks, i) not in DECIMAL_WORDS:
        return None
    j = i + 1
    if j < len(toks) and toks[j].kind == "num" and toks[j].text.isdigit():
        digits = toks[j].text
        return Fraction(int(digits), 10 ** len(digits)), j + 1
    compound = _below_thousand(toks, j)
    if compound is not None and compound[1] - j > 1:
        digits = str(compound[0])
        return Fraction(int(digits), 10 ** len(digits)), compound[1]
    digits = ""
    while norm_at(toks, j) in ONES:
        digits += str(ONES[norm_at(toks, j)])
        j += 1
    if not digits:
        return None
    return Fraction(int(digits), 10 ** len(digits)), j


def _parts(toks, i, count):
    """ "tiga perempat" / "two thirds": count / parts, or None."""
    t = norm_at(toks, i)
    if t in COUNTED_PARTS:
        return Fraction(count, COUNTED_PARTS[t]), i + 1
    if count == 1 and t in EN_PARTS:
        return Fraction(1, EN_PARTS[t]), i + 1
    return None


def _chunk(toks, i, language):
    """One piece of a number: (value, end, scale), where scale is set for the
    words that carry their own ("seribu", "sejuta")."""
    if i >= len(toks):
        return None
    tok = toks[i]
    t = tok.norm
    if tok.kind == "num":
        value = numeral_value(tok.text, language)
        if value is None:
            return None
        j = i + 1
        if j < len(toks) and toks[j].glued and toks[j].norm in UNICODE_FRACTIONS:
            return value + UNICODE_FRACTIONS[toks[j].norm], j + 1, None      # "1½"
        if value.denominator == 1 and value < 1000:
            tail = _decimal_tail(toks, j)
            if tail is not None and "," not in tok.text and "." not in tok.text:
                return value + tail[0], tail[1], None                         # "1 koma 5"
            hundreds = _hundreds(toks, i)
            if hundreds is not None:                                          # "5 ratus"
                return _below_thousand(toks, i) + (None,)
        return value, j, None
    if t in UNICODE_FRACTIONS:
        return UNICODE_FRACTIONS[t], i + 1, None
    if t in SE_SCALES:
        return Fraction(1), i + 1, SE_SCALES[t]
    if t in FRACTION_WORDS:
        return FRACTION_WORDS[t], i + 1, None
    if t in ARTICLES or t == "one":
        parts = _parts(toks, i + 1, 1)
        if parts is not None:
            return parts[0], parts[1], None                                   # "a quarter"
        if t in ARTICLES:
            nxt = norm_at(toks, i + 1)
            if nxt in SCALES:
                return Fraction(1), i + 1, None                               # "a million"
            if nxt == "hundred":
                return _below_thousand(toks, i) + (None,)
            return None
    if t == "point":
        tail = _decimal_tail(toks, i)
        return (tail[0], tail[1], None) if tail else None                     # "point five"
    found = _below_thousand(toks, i)
    if found is None:
        return None
    value, j = found
    parts = _parts(toks, j, value)
    if parts is not None:
        return parts[0], parts[1], None                                       # "tiga perempat"
    tail = _decimal_tail(toks, j)
    if tail is not None:
        return value + tail[0], tail[1], None                                 # "satu koma lima"
    return Fraction(value), j, None


def _scale_at(toks, i):
    t = norm_at(toks, i)
    if t in SCALES:
        return SCALES[t]
    if t in GLUED_SCALES and i < len(toks) and toks[i].glued and i > 0 \
            and toks[i - 1].kind == "num":
        return GLUED_SCALES[t]
    return None


def read_number(toks, i, language="en"):
    """(value, end) of the number at token i, in digits or words, with its
    scales ("2 juta 500 ribu"), a half after it ("satu setengah", "sejuta
    setengah", "one and a half") and a decimal tail ("satu koma lima"), or
    None when no number starts there."""
    total = Fraction(0)
    last_scale = None
    unit = Fraction(1)          # what "setengah" after the number is half of
    found = False
    j = i
    while j < len(toks):
        if found and (_half_after(toks, j) is not None):
            break                   # "sejuta setengah": half of the scale, below
        chunk = _chunk(toks, j, language)
        if chunk is None:
            break
        value, k, own_scale = chunk
        scale = own_scale
        if scale is None:
            scale = _scale_at(toks, k)
            if scale is not None:
                k += 1
        if scale is not None:
            if last_scale is not None and scale >= last_scale:
                break
            total += value * scale
            last_scale, unit = scale, Fraction(scale)
            j, found = k, True
            continue
        if last_scale is not None and value >= last_scale:
            break
        total += value
        j, found = k, True
        unit = Fraction(1)
        break
    if not found:
        return None
    half = _half_after(toks, j)
    if half is not None and total >= 1:
        return total + unit / 2, half
    return total, j


def _half_after(toks, j):
    """The end of "setengah" / "and a half" at token j, or None."""
    if norm_at(toks, j) == "setengah":
        return j + 1
    if (norm_at(toks, j), norm_at(toks, j + 1), norm_at(toks, j + 2)) == ("and", "a", "half"):
        return j + 3
    return None


# ------------------------------------------------------------
# Saying numbers
# ------------------------------------------------------------

Shown = collections.namedtuple("Shown", "digits mantissa exponent approx")
SCI_ABOVE = Decimal(10) ** 15      # from here, "1,5 kali 10 pangkat 18"
SCI_BELOW = Decimal(1) / 10 ** 6   # and below this (but not 0)
AUTO_EXACT_DECIMALS = 4            # an exact value with up to this many decimals is said as it is
AUTO_DECIMALS = 2                  # otherwise: two decimals ("33,33"),
AUTO_SMALL_DIGITS = 2              # or two significant digits below 1 ("0,33", "0,0012")
SIGNIFICANT = 10


def to_decimal(value, digits=SIGNIFICANT):
    """A Decimal of `value` (Fraction, int or float) to `digits` significant digits."""
    with localcontext() as ctx:
        ctx.prec = digits
        ctx.rounding = ROUND_HALF_UP
        if isinstance(value, float):
            return +Decimal(repr(value))
        value = Fraction(value)
        return Decimal(value.numerator) / Decimal(value.denominator)


def _places(d):
    exponent = d.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _quantize(d, places):
    return d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _is_exact(value, d):
    return not isinstance(value, float) and Fraction(d) == Fraction(value)


def present(value, decimals="auto"):
    """How to say a result: Shown(digits, mantissa, exponent, approx).
    `digits` is a Decimal to write out, or None for a very large or small
    number, which is said as mantissa x 10^exponent. `approx` is True when
    rounding changed the value.

    decimals "auto": an exact value with up to 4 decimals as it is (0.125,
    12.5), anything longer rounded to 2 decimals (33.33), or below 1 to 2
    significant digits (0.33, 0.0012). A number 0-6: that many decimals at
    most. Trailing zeros are always dropped."""
    exact = not isinstance(value, float)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OverflowError("not a finite number")
    d10 = to_decimal(value)
    magnitude = abs(d10)
    if magnitude >= SCI_ABOVE or (0 < magnitude < SCI_BELOW):
        return _scientific(value, d10, decimals)
    if decimals == "auto":
        if _places(d10) <= AUTO_EXACT_DECIMALS and (_is_exact(value, d10) or not exact):
            return Shown(d10.normalize(), None, None, False)
        if magnitude >= 1 or magnitude == 0:
            shown = _quantize(d10, AUTO_DECIMALS)
        else:
            first = magnitude.adjusted()           # -1 for 0.33, -3 for 0.0012
            shown = _quantize(d10, -first + AUTO_SMALL_DIGITS - 1)
    else:
        shown = _quantize(d10, int(decimals))
    approx = not _is_exact(value, shown)
    return Shown(shown.normalize() if shown else Decimal(0), None, None, approx)


def _scientific(value, d10, decimals):
    exponent = d10.adjusted()
    mantissa = d10.scaleb(-exponent)
    places = AUTO_DECIMALS if decimals == "auto" else int(decimals)
    shown = _quantize(mantissa, places)
    if abs(shown) >= 10:                           # 9.999 -> 10.00
        exponent += 1
        shown = _quantize(mantissa.scaleb(-1), places)
    approx = not _is_exact(value, shown.scaleb(exponent))
    return Shown(None, shown.normalize(), exponent, approx)


def format_decimal(d, language="en", keep_places=None):
    """ "1.250.000,5" (Indonesian) or "1,250,000.5" (English) for a Decimal.
    `keep_places` writes exactly that many decimals (money: "12,50")."""
    if keep_places is not None:
        d = _quantize(Decimal(d), keep_places)
        text = format(d, "f")
    else:
        text = format(Decimal(d).normalize(), "f")
    negative = text.startswith("-")
    text = text.lstrip("-")
    whole, _dot, frac = text.partition(".")
    if keep_places is None:
        frac = frac.rstrip("0")
    comma = language in COMMA_DECIMAL
    group = "." if comma else ","
    point = "," if comma else "."
    parts = []
    while len(whole) > 3:
        parts.insert(0, whole[-3:])
        whole = whole[:-3]
    parts.insert(0, whole)
    out = group.join(parts)
    if frac:
        out += point + frac
    if negative and out.strip("0.,") != "":
        out = "-" + out
    return out
