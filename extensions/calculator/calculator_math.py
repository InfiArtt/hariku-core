# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Arithmetic for Calculator & Converter: a small parser of its own, never
Python's eval. No wx here.

    lex(toks, language)   -> [MTok]  words and symbols as math tokens
    evaluate(mtoks)       -> Fraction or float, or raises CalcError
    has_operator(mtoks)   -> whether there is something to calculate

Operators, in symbols and in words (Indonesian and English):
    + plus tambah ditambah          - minus kurang dikurangi
    * x × kali dikali times         / : ÷ bagi dibagi "divided by" over
    ^ ** pangkat "to the power of"  mod modulo
    %  persen percent               ! faktorial factorial
    kuadrat squared ², cubed ³      akar "square root of" √,
    "akar pangkat tiga" "cube root of" ∛, "akar pangkat 4"
    ( ) and "kurung buka" / "kurung tutup"

Precedence, loosest first: + and -; *, / and mod (and a number right before
a bracket or a root: "2(3+4)"); a sign ("minus 3"); ^ (right to left, so
2^3^2 is 2^9, and -2^2 is -4); then !, %, "squared" and "of" after a value.

Percent works as on a pocket calculator: "12% dari 350" and "15% of 80" take
that share, "350 + 12%" adds 12% of 350 (392), "350 - 12%" takes it off,
"80 * 15%" is 12, and "50%" alone is 0.5.

Limits keep a sentence from running away: at most MAX_TOKENS tokens,
brackets MAX_DEPTH deep, whole exponents up to MAX_EXPONENT, results up to
MAX_RESULT_DIGITS digits, factorials up to MAX_FACTORIAL.

Values stay exact fractions while they can (so 100 / 3 * 3 is 100); roots
and powers that aren't exact become floats.
"""

import collections
import math
from fractions import Fraction

import calculator_numbers as numbers

MAX_TOKENS = 80
MAX_DEPTH = 20
MAX_EXPONENT = 10000
MAX_RESULT_DIGITS = 1000
MAX_FACTORIAL = 1000
MAX_ROOT = 100


class CalcError(Exception):
    """A sum that can't be worked out. `kind`: "syntax" (not arithmetic as
    far as we can read it), "div_zero", "too_big", "negative_root",
    "factorial" or "complex"."""

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


# A math token: kind "num" (value: Fraction or float), "op" (+ - * / ^ mod),
# "pct", "fact", "sq", "cube", "of", "lp", "rp", "func" (value: the root's
# degree, 2 for a square root), "last" (the previous result: value).
MTok = collections.namedtuple("MTok", "kind value")

_OPS = [
    ("+", ["+"], ["plus"], ["tambah"], ["ditambah"], ["ditambahkan"], ["ditambah", "dengan"],
     ["tambah", "dengan"], ["ditambahin"], ["tambahin"]),
    ("-", ["-"], ["minus"], ["kurang"], ["dikurangi"], ["dikurang"], ["dikurangi", "dengan"],
     ["dikurangin"], ["kurangin"], ["kurangi"], ["less"], ["take", "away"]),
    ("*", ["*"], ["×"], ["x"], ["kali"], ["dikali"], ["dikalikan"], ["dikali", "dengan"],
     ["dikalikan", "dengan"], ["kalikan"], ["times"], ["multiplied", "by"], ["multiply", "by"]),
    ("/", ["/"], [":"], ["÷"], ["bagi"], ["dibagi"], ["dibagi", "dengan"], ["dibagikan"],
     ["bagi", "dengan"], ["divided", "by"], ["divide", "by"], ["over"]),
    ("^", ["^"], ["**"], ["pangkat"], ["dipangkatkan"], ["dipangkatkan", "dengan"],
     ["dipangkat"], ["to", "the", "power", "of"], ["to", "the", "power"], ["to", "the"],
     ["raised", "to", "the", "power", "of"], ["raised", "to"], ["power"]),
    ("mod", ["mod"], ["modulo"], ["modulus"]),
]
_POSTFIX = [
    ("pct", ["%"], ["persen"], ["percent"], ["per", "cent"], ["pct"], ["prosen"]),
    ("fact", ["!"], ["faktorial"], ["factorial"]),
    ("sq", ["kuadrat"], ["squared"], ["²"], ["dikuadratkan"]),
    ("cube", ["cubed"], ["³"]),
    ("of", ["dari"], ["of"]),
]
_BRACKETS = [
    ("lp", ["("], ["["], ["{"], ["kurung", "buka"], ["buka", "kurung"], ["open", "bracket"],
     ["open", "parenthesis"], ["open", "paren"]),
    ("rp", [")"], ["]"], ["}"], ["kurung", "tutup"], ["tutup", "kurung"], ["close", "bracket"],
     ["close", "parenthesis"], ["close", "paren"]),
]
_ROOTS = [
    (3, ["akar", "pangkat", "tiga"], ["akar", "kubik"], ["akar", "kubus"], ["cube", "root", "of"],
     ["the", "cube", "root", "of"], ["cube", "root"], ["cbrt"], ["∛"]),
    (2, ["akar", "kuadrat"], ["akar", "pangkat", "dua"], ["akar"], ["square", "root", "of"],
     ["the", "square", "root", "of"], ["square", "root"], ["sqrt"], ["√"], ["root", "of"],
     ["root"]),
]
# Unary signs spelled out.
_SIGNS = {"negatif": "-", "negative": "-", "positif": "+", "positive": "+"}
_ORDINAL_ENDINGS = {"th", "st", "nd", "rd"}


def _phrases():
    table = []
    for group, kind in ((_OPS, "op"), (_POSTFIX, None), (_BRACKETS, None)):
        for entry in group:
            name, variants = entry[0], entry[1:]
            for words in variants:
                if kind == "op":
                    table.append((tuple(words), MTok("op", name)))
                else:
                    table.append((tuple(words), MTok(name, None)))
    for degree, *variants in _ROOTS:
        for words in variants:
            table.append((tuple(words), MTok("func", degree)))
    table.sort(key=lambda item: -len(item[0]))
    return table


PHRASES = _phrases()
LONGEST = max(len(words) for words, _tok in PHRASES)


def _phrase_at(toks, i):
    for words, mtok in PHRASES:
        n = len(words)
        if tuple(t.norm for t in toks[i:i + n]) == words:
            return mtok, i + n
    return None


def lex(toks, language="en", last=None):
    """Math tokens for `toks` (from calculator_numbers.tokenize). `last` is
    the value "hasilnya" / "the result" stands for, if any (the caller finds
    those words and passes the rest). Raises CalcError("syntax") at the
    first thing that isn't arithmetic."""
    out = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        if tok.kind == "sym" and tok.norm in ("=", "?"):
            i += 1
            continue
        if tok.kind == "last":
            out.append(MTok("last", last))
            i += 1
            continue
        # "akar pangkat 4 dari 16", "akar pangkat lima 32"
        if tok.norm == "akar" and numbers.norm_at(toks, i + 1) == "pangkat":
            degree = numbers.read_number(toks, i + 2, language)
            if degree is not None and degree[0].denominator == 1 and 2 <= degree[0] <= MAX_ROOT:
                out.append(MTok("func", int(degree[0])))
                i = degree[1]
                continue
        number = numbers.read_number(toks, i, language)
        if number is not None:
            out.append(MTok("num", number[0]))
            i = number[1]
            continue
        found = _phrase_at(toks, i)
        if found is not None:
            mtok, i = found
            out.append(mtok)
            continue
        if tok.norm in _SIGNS:
            out.append(MTok("op", _SIGNS[tok.norm]))
            i += 1
            continue
        if tok.norm in _ORDINAL_ENDINGS and tok.glued and out and out[-1].kind == "num":
            i += 1                               # "2 to the 10th"
            continue
        raise CalcError("syntax")
    if not out or len(out) > MAX_TOKENS:
        raise CalcError("syntax")
    return out


def has_operator(mtoks):
    """Whether the tokens hold something to work out (not a lone number)."""
    kinds = [m.kind for m in mtoks]
    if any(k in ("fact", "sq", "cube", "func", "of") for k in kinds):
        return True
    # A binary operator between two things (a leading sign doesn't count).
    for index, m in enumerate(mtoks):
        if m.kind == "op" and index > 0 and mtoks[index - 1].kind in ("num", "rp", "pct",
                                                                      "fact", "sq", "cube",
                                                                      "last"):
            return True
    return False


# ------------------------------------------------------------
# Arithmetic on exact fractions (floats where it can't be exact)
# ------------------------------------------------------------

def _check(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CalcError("too_big")
        return value
    if value.numerator and _digits(value.numerator) - _digits(value.denominator) > MAX_RESULT_DIGITS:
        raise CalcError("too_big")
    if _digits(value.denominator) > MAX_RESULT_DIGITS * 2:
        return float(value) if abs(value) > 1e-300 else 0.0
    return value


def _digits(n):
    """About how many digits n has (from its bits: no huge str())."""
    n = abs(int(n))
    return int(n.bit_length() * 0.30103) + 1 if n else 1


def _log10(n):
    n = abs(int(n))
    return math.log10(n) if n.bit_length() < 1000 else n.bit_length() * 0.30103


def _float(value):
    try:
        return float(value)
    except OverflowError:
        raise CalcError("too_big")


def _add(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return _check(_float(a) + _float(b))
    return _check(a + b)


def _mul(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return _check(_float(a) * _float(b))
    return _check(a * b)


def _div(a, b):
    if b == 0:
        raise CalcError("div_zero")
    if isinstance(a, float) or isinstance(b, float):
        return _check(_float(a) / _float(b))
    return _check(Fraction(a) / Fraction(b))


def _mod(a, b):
    if b == 0:
        raise CalcError("div_zero")
    if isinstance(a, float) or isinstance(b, float):
        return _check(math.fmod(_float(a), _float(b)) % abs(_float(b)))
    return _check(Fraction(a) % Fraction(b))


def iroot(n, k):
    """The exact integer k-th root of n >= 0, or None."""
    if n < 0:
        return None
    if n < 2:
        return n
    # Newton's method from above: 2^ceil(bits / k) is at least the root.
    x = 1 << ((n.bit_length() + k - 1) // k)
    while True:
        y = ((k - 1) * x + n // x ** (k - 1)) // k
        if y >= x:
            break
        x = y
    for candidate in (x - 1, x, x + 1):
        if candidate >= 0 and candidate ** k == n:
            return candidate
    return None


def _root(value, degree):
    """The degree-th root: exact when it can be (akar 144 is 12, ∛27 is 3)."""
    negative = value < 0
    if negative and degree % 2 == 0:
        raise CalcError("negative_root")
    if not isinstance(value, float):
        top = iroot(abs(value.numerator), degree)
        bottom = iroot(value.denominator, degree)
        if top is not None and bottom is not None:
            result = Fraction(top, bottom)
            return -result if negative else result
    magnitude = abs(_float(value))
    result = magnitude ** (1.0 / degree)
    return _check(-result if negative else result)


def _power(base, exponent):
    if not isinstance(exponent, float) and exponent.denominator == 1:
        e = int(exponent)
        if abs(e) > MAX_EXPONENT:
            raise CalcError("too_big")
        if isinstance(base, float):
            try:
                return _check(math.pow(base, e))
            except OverflowError:
                raise CalcError("too_big")
            except (ValueError, ZeroDivisionError):
                raise CalcError("div_zero")
        if base == 0 and e < 0:
            raise CalcError("div_zero")
        if abs(base.numerator) > 1 or base.denominator > 1:
            # About how many digits base ** e has above (or below) the point.
            size = abs(e) * abs(_log10(base.numerator) - _log10(base.denominator))
            shrinks = (abs(base) < 1) == (e > 0)
            if size > MAX_RESULT_DIGITS and not shrinks:
                raise CalcError("too_big")
            if size > MAX_RESULT_DIGITS:
                return 0.0                          # 0.5 ^ 10000: far below anything said
        return _check(base ** e)
    # A fractional exponent: 8^(1/3), 2^0.5
    if base < 0 and (isinstance(exponent, float) or exponent.denominator % 2 == 0):
        raise CalcError("complex")                  # (-2) ^ 0.3 is not a real number
    if not isinstance(exponent, float) and exponent.denominator <= MAX_ROOT \
            and abs(exponent.numerator) <= MAX_EXPONENT:
        root = _root(base, exponent.denominator) if not isinstance(base, float) else None
        if root is not None and not isinstance(root, float):
            return _power(root, Fraction(exponent.numerator))
        if base < 0 and exponent.denominator % 2 == 1:
            magnitude = _root(-base, exponent.denominator)
            result = _power(magnitude, Fraction(exponent.numerator))
            return -result if exponent.numerator % 2 else result
    if base < 0:
        raise CalcError("complex")
    if base == 0:
        if exponent < 0:
            raise CalcError("div_zero")
        return Fraction(0)
    try:
        return _check(math.pow(_float(base), _float(exponent)))
    except OverflowError:
        raise CalcError("too_big")


def _factorial(value):
    if isinstance(value, float) or value.denominator != 1 or value < 0:
        raise CalcError("factorial")
    if value > MAX_FACTORIAL:
        raise CalcError("too_big")
    return Fraction(math.factorial(int(value)))


# ------------------------------------------------------------
# The parser
# ------------------------------------------------------------

class _Val:
    __slots__ = ("v", "pct")

    def __init__(self, v, pct=False):
        self.v = v
        self.pct = pct


class _Parser:
    def __init__(self, mtoks):
        self.toks = mtoks
        self.i = 0
        self.depth = 0

    def peek(self, kind=None, value=None):
        if self.i >= len(self.toks):
            return None
        tok = self.toks[self.i]
        if kind is not None and tok.kind != kind:
            return None
        if value is not None and tok.value not in value:
            return None
        return tok

    def take(self):
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def expression(self):
        left = self.term()
        while self.peek("op", ("+", "-")):
            op = self.take().value
            self._no_plus_after_operator()
            right = self.term()
            if right.pct:                         # 350 + 12% -> 350 * 1.12
                share = _mul(left.v, right.v)
                left = _Val(_add(left.v, share if op == "+" else -share))
            else:
                left = _Val(_add(left.v, right.v if op == "+" else -right.v))
        return left

    def term(self):
        left = self.unary()
        while True:
            tok = self.peek()
            if tok is not None and tok.kind == "op" and tok.value in ("*", "/", "mod"):
                self.take()
                self._no_plus_after_operator()
                right = self.unary()
                if tok.value == "*":
                    left = _Val(_mul(left.v, right.v))
                elif tok.value == "/":
                    left = _Val(_div(left.v, right.v))
                else:
                    left = _Val(_mod(left.v, right.v))
            elif tok is not None and tok.kind in ("lp", "func"):
                right = self.unary()                     # 2(3 + 4), 2√9
                left = _Val(_mul(left.v, right.v))
            else:
                return left

    def _no_plus_after_operator(self):
        # "2x + 3" is algebra, not 2 * (+3).
        if self.peek("op", ("+",)):
            raise CalcError("syntax")

    def unary(self):
        tok = self.peek("op", ("-", "+"))
        if tok is not None:
            self.take()
            if self.peek("op", ("-", "+")):
                raise CalcError("syntax")
            value = self.unary()
            return _Val(-value.v if tok.value == "-" else value.v, value.pct)
        return self.power()

    def power(self):
        base = self.postfix()
        if self.peek("op", ("^",)):
            self.take()
            exponent = self.unary()
            if base.pct or exponent.pct:
                raise CalcError("syntax")
            return _Val(_power(base.v, exponent.v))
        return base

    def postfix(self):
        value = self.primary()
        while True:
            tok = self.peek()
            if tok is None:
                return value
            if tok.kind == "fact":
                self.take()
                value = _Val(_factorial(value.v))
            elif tok.kind == "pct":
                self.take()
                if value.pct:
                    raise CalcError("syntax")
                value = _Val(_div(value.v, Fraction(100)), pct=True)
            elif tok.kind == "sq":
                self.take()
                value = _Val(_power(value.v, Fraction(2)))
            elif tok.kind == "cube":
                self.take()
                value = _Val(_power(value.v, Fraction(3)))
            elif tok.kind == "of":
                # "12% dari 350", "setengah dari 80", "half of 80"
                if not (value.pct or (0 < abs(value.v) < 1)):
                    raise CalcError("syntax")
                self.take()
                right = self.unary()
                value = _Val(_mul(value.v, right.v))
            else:
                return value

    def primary(self):
        tok = self.peek()
        if tok is None:
            raise CalcError("syntax")
        if tok.kind in ("num", "last"):
            self.take()
            if tok.value is None:
                raise CalcError("syntax")
            return _Val(tok.value)
        if tok.kind == "lp":
            self.take()
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise CalcError("too_big")
            value = self.expression()
            self.depth -= 1
            if self.peek("rp"):
                self.take()
            elif self.i < len(self.toks):
                raise CalcError("syntax")       # a bracket left open at the end is closed
            return _Val(value.v, value.pct)
        if tok.kind == "func":
            self.take()
            if self.peek("of"):
                self.take()                     # "akar dari 144", "square root of 2"
            argument = self.unary()
            if argument.pct:
                raise CalcError("syntax")
            return _Val(_root(argument.v, tok.value))
        raise CalcError("syntax")


def evaluate(mtoks):
    """The value of math tokens: a Fraction when it is exact, else a float.
    A percent left over ("50%") is its share (0.5)."""
    parser = _Parser(list(mtoks))
    value = parser.expression()
    if parser.i != len(parser.toks):
        raise CalcError("syntax")
    return value.v
