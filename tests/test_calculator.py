# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Calculator & Converter extension: numbers in digits and words
# (Indonesian and English, as Voice Control writes them), the decimal comma,
# the arithmetic parser (precedence, brackets, signs, percent, limits, never
# eval), every unit category, currencies with a fake rate source, follow-ups
# on the last result, the extras with a seeded random generator, Aruna's
# routing next to the other extensions' commands, personas, the sentences in
# both languages, and registering with Hariku. Nothing is fetched, spoken,
# copied or shown.

import ast
import datetime
import json
import os
import random
import re
import sys
import types
from fractions import Fraction

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "calculator")
TODAY = datetime.date(2026, 9, 25)
NOON = datetime.datetime(2026, 9, 25, 12, 0)


def _modules():
    if EXT_DIR not in sys.path:
        sys.path.insert(0, EXT_DIR)
    import calculator_intents
    import calculator_math
    import calculator_money
    import calculator_numbers
    import calculator_parse
    import calculator_text
    import calculator_units
    return types.SimpleNamespace(intents=calculator_intents, math=calculator_math,
                                 money=calculator_money, numbers=calculator_numbers,
                                 parse=calculator_parse, text=calculator_text,
                                 units=calculator_units)


@pytest.fixture(scope="module")
def m():
    return _modules()


@pytest.fixture
def lang(monkeypatch, m):
    """Switch the UI language; the core's month names and this extension's
    texts are loaded (another test may have cleared them)."""
    from core import i18n
    saved = {d: i18n._language_cache.get(d) for d in ("core", "calculator")}
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    i18n._load_domain("calculator", os.path.join(EXT_DIR, "locales"))

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("en")
    yield set_lang
    for domain, data in saved.items():
        if data is None:
            i18n._language_cache.pop(domain, None)
        else:
            i18n._language_cache[domain] = data


# ------------------------------------------------------------
# Numbers
# ------------------------------------------------------------

@pytest.mark.parametrize("raw, language, value", [
    ("1.250.000", "id", 1250000), ("1,250,000", "en", 1250000),
    ("2,5", "id", Fraction(5, 2)), ("2.5", "en", Fraction(5, 2)),
    ("1.5", "id", Fraction(3, 2)),               # not three digits: a decimal point
    ("1,5", "en", Fraction(3, 2)),               # an Indonesian comma in English still reads
    ("1.250", "id", 1250), ("1,250", "en", 1250),
    ("1,250", "id", Fraction(5, 4)), ("1.250", "en", Fraction(5, 4)),
    ("1.250,75", "id", Fraction(125075, 100)), ("1,250.75", "id", Fraction(125075, 100)),
    ("1,250.75", "en", Fraction(125075, 100)), ("1.250,75", "en", Fraction(125075, 100)),
    ("25,000", "id", 25000), ("25.000", "en", 25000),   # "000" is always thousands
    ("0.125", "id", Fraction(1, 8)), (",5", "id", Fraction(1, 2)), (".5", "en", Fraction(1, 2)),
    ("007", "en", 7), ("12", "id", 12),
])
def test_numerals_follow_the_language(m, raw, language, value):
    assert m.numbers.numeral_value(raw, language) == value


@pytest.mark.parametrize("raw", ["1.2.3", "12,34,567", "1,2.3.4", "1" * 61])
def test_numerals_that_make_no_sense(m, raw):
    assert m.numbers.numeral_value(raw, "en") is None


@pytest.mark.parametrize("text, value", [
    # Indonesian, as whisper writes it
    ("dua puluh lima", 25), ("seratus dua belas", 112), ("dua ribu dua puluh enam", 2026),
    ("satu juta dua ratus ribu", 1200000), ("setengah", Fraction(1, 2)),
    ("seperempat", Fraction(1, 4)), ("sepertiga", Fraction(1, 3)),
    ("tiga perempat", Fraction(3, 4)), ("dua pertiga", Fraction(2, 3)),
    ("satu setengah", Fraction(3, 2)), ("dua setengah", Fraction(5, 2)),
    ("sejuta setengah", 1500000), ("setengah juta", 500000), ("satu koma lima", Fraction(3, 2)),
    ("nol koma nol lima", Fraction(1, 20)), ("satu koma dua lima", Fraction(5, 4)),
    ("satu koma dua puluh lima", Fraction(5, 4)), ("1 koma 25", Fraction(5, 4)),
    ("2 juta", 2000000), ("1,5 miliar", 1500000000), ("350 ribu", 350000), ("350rb", 350000),
    ("2jt", 2000000), ("seribu", 1000), ("sebelas", 11), ("tujuh belas", 17),
    ("sembilan puluh sembilan", 99), ("5 ratus", 500), ("selusin", 12), ("dua lusin", 24),
    ("sepuluh ribu", 10000), ("seratus lima puluh ribu", 150000), ("2 juta 500 ribu", 2500000),
    ("25 ribu 500", 25500), ("nol", 0),
    # English
    ("twenty-five", 25), ("twenty five", 25), ("one hundred and twelve", 112),
    ("a hundred", 100), ("a million", 1000000), ("one and a half", Fraction(3, 2)),
    ("three quarters", Fraction(3, 4)), ("two thirds", Fraction(2, 3)),
    ("a quarter", Fraction(1, 4)), ("half", Fraction(1, 2)), ("a half", Fraction(1, 2)),
    ("one point five", Fraction(3, 2)), ("point five", Fraction(1, 2)),
    ("3.5 million", 3500000), ("250k", 250000), ("a dozen", 12), ("two dozen", 24),
    ("nineteen", 19), ("ninety nine", 99), ("1½", Fraction(3, 2)), ("½", Fraction(1, 2)),
    ("two thousand twenty six", 2026), ("five hundred thousand", 500000),
])
def test_number_words(m, text, value):
    toks = m.numbers.tokenize(text)
    found = m.numbers.read_number(toks, 0, "id")
    assert found is not None, text
    assert found == (value, len(toks)), text


@pytest.mark.parametrize("text", ["kaki", "a", "the", "koma", "k", "minus", "setengahnya"])
def test_not_numbers(m, text):
    assert m.numbers.read_number(m.numbers.tokenize(text), 0, "en") is None


def test_a_hyphen_joins_words_and_digits_stay_apart(m):
    norms = [t.norm for t in m.numbers.tokenize("Twenty-five km-per-jam 25x4 3-2")]
    assert norms == ["twenty", "five", "km", "per", "jam", "25", "x", "4", "3", "-", "2"]


# ------------------------------------------------------------
# Arithmetic
# ------------------------------------------------------------

def _calc(m, text, language="id"):
    return m.math.evaluate(m.math.lex(m.numbers.tokenize(text), language))


@pytest.mark.parametrize("text, value", [
    # precedence and brackets
    ("2 + 3 * 4", 14), ("(2 + 3) * 4", 20), ("2 * 3 + 4", 10), ("10 - 2 - 3", 5),
    ("100 / 10 / 2", 5), ("2 ^ 3 ^ 2", 512), ("-2 ^ 2", -4), ("(-2) ^ 2", 4),
    ("2 ^ -1", Fraction(1, 2)), ("2 * -3", -6), ("5 - -3", 8), ("2(3 + 4)", 14),
    ("(3 + 4", 7), ("((1 + 2) * (3 + 4))", 21), ("[2 + 3] * 2", 10),
    ("kurung buka 3 tambah 4 kurung tutup kali 2", 14),
    # operators in symbols and words
    ("25 x 4", 100), ("25x4", 100), ("25 × 4", 100), ("100 : 4", 25), ("100 ÷ 4", 25),
    ("2 ** 10", 1024), ("17 mod 5", 2), ("17 modulo 5", 2), ("-7 mod 3", 2),
    ("25 kali 4", 100), ("100 dibagi 3 kali 3", 100), ("2 pangkat 10", 1024),
    ("10 dikurangi 3", 7), ("10 kurang 3", 7), ("7 tambah 8", 15), ("7 ditambah dengan 8", 15),
    ("6 dikalikan dengan 7", 42), ("twenty-five times four", 100), ("9 divided by 3", 3),
    ("2 to the power of 10", 1024), ("2 to the 10th", 1024), ("3 over 4", Fraction(3, 4)),
    ("10 minus 3", 7), ("minus tiga kali dua", -6), ("negative 3 plus 5", 2),
    # postfix and functions
    ("7!", 5040), ("7 faktorial", 5040), ("7 factorial", 5040), ("0!", 1),
    ("5 kuadrat", 25), ("2 cubed", 8), ("3²", 9), ("akar 144", 12), ("√144", 12),
    ("akar dari 144", 12), ("akar 16 tambah 9", 13), ("akar (16 + 9)", 5),
    ("square root of 81", 9), ("the square root of 81", 9), ("akar pangkat tiga 27", 3),
    ("cube root of -8", -2), ("akar pangkat 4 dari 16", 2), ("8 ^ (1/3)", 2),
    ("(-8) ^ (1/3)", -2), ("2√9", 6),
    # percent, pocket-calculator style
    ("12 persen dari 350", 42), ("15% of 80", 12), ("350 + 12%", 392),
    ("350 ditambah 12%", 392), ("350 - 12%", 308), ("80 * 15%", 12), ("50%", Fraction(1, 2)),
    ("10 / 50%", 20), ("setengah dari 80", 40), ("half of 80", 40),
    ("12% dari 350 ditambah 5", 47),
    # exact fractions
    ("0.1 + 0.2", Fraction(3, 10)), ("1/3 + 1/3 + 1/3", 1), ("100 / 3 * 3", 100),
    ("1.250.000 + 1", 1250001), ("2 juta + 1,5 miliar", 1502000000),
    ("sejuta setengah + 0", 1500000), ("tiga perempat kali 100", 75),
    ("satu koma lima kali dua", 3), ("dua puluh lima kali empat", 100),
    ("seratus dua belas tambah setengah", Fraction(225, 2)),
])
def test_arithmetic(m, text, value):
    assert _calc(m, text) == value, text


def test_irrational_results_are_floats(m):
    assert _calc(m, "akar 2") == pytest.approx(2 ** 0.5)
    assert _calc(m, "2 ^ 0.5") == pytest.approx(2 ** 0.5)
    assert _calc(m, "akar 2 * akar 2") == pytest.approx(2)


@pytest.mark.parametrize("text, kind", [
    ("1 / 0", "div_zero"), ("5 mod 0", "div_zero"), ("0 ^ -1", "div_zero"),
    ("2 ^ 100000", "too_big"), ("10 ^ 1001", "too_big"), ("1001!", "too_big"),
    ("3.5!", "factorial"), ("(-1)!", "factorial"), ("akar -4", "negative_root"),
    ("(-8) ^ 0.5", "complex"), ("(-2) ^ 0.3", "complex"),
    ("2 +", "syntax"), ("2 3", "syntax"), ("2x + 3", "syntax"), ("+ + 2", "syntax"),
    ("2 )", "syntax"), ("( )", "syntax"), ("2 dari 3", "syntax"), ("abc", "syntax"),
    ("", "syntax"), ("10% ^ 2", "syntax"),
])
def test_arithmetic_errors(m, text, kind):
    with pytest.raises(m.math.CalcError) as caught:
        _calc(m, text)
    assert caught.value.kind == kind, text


def test_limits(m):
    deep = "(" * (m.math.MAX_DEPTH + 1) + "1" + ")" * (m.math.MAX_DEPTH + 1)
    with pytest.raises(m.math.CalcError) as caught:
        _calc(m, deep)
    assert caught.value.kind == "too_big"
    assert _calc(m, "(" * m.math.MAX_DEPTH + "1" + ")" * m.math.MAX_DEPTH) == 1
    with pytest.raises(m.math.CalcError):
        _calc(m, " + ".join(["1"] * 50))                     # 99 tokens
    assert _calc(m, "10 ^ 999") == 10 ** 999
    assert _calc(m, "170!") > 10 ** 306
    assert _calc(m, "0.5 ^ 10000") == 0


def test_no_eval_anywhere(m):
    # A parser of its own: Python never runs what was said.
    for name in ("calculator_math.py", "calculator_parse.py", "calculator_numbers.py",
                 "calculator_intents.py", "calculator_units.py", "calculator_money.py"):
        with open(os.path.join(EXT_DIR, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("eval", "exec", "compile", "__import__"), name
    for text in ("__import__('os').system('calc')", "open('x').read()", "1 + os", "lambda: 1"):
        with pytest.raises(m.math.CalcError):
            _calc(m, text)


@pytest.mark.parametrize("text, expected", [
    ("5", False), ("-5", False), ("50%", False), ("dua", False), ("2 + 3", True),
    ("akar 9", True), ("7!", True), ("12% dari 50", True), ("5 kuadrat", True),
])
def test_has_operator(m, text, expected):
    assert m.math.has_operator(m.math.lex(m.numbers.tokenize(text), "id")) is expected


def test_integer_roots(m):
    assert m.math.iroot(10 ** 40, 2) == 10 ** 20
    assert m.math.iroot(27 ** 3 * 10 ** 30, 3) == 27 * 10 ** 10
    assert m.math.iroot(2, 2) is None and m.math.iroot(0, 5) == 0


# ------------------------------------------------------------
# Saying numbers
# ------------------------------------------------------------

@pytest.mark.parametrize("value, decimals, id_text, en_text, approx", [
    (Fraction(100, 3), "auto", "33,33", "33.33", True),
    (Fraction(200, 3), "auto", "66,67", "66.67", True),
    (1250000, "auto", "1.250.000", "1,250,000", False),
    (Fraction(1, 8), "auto", "0,125", "0.125", False),
    (Fraction(1, 3), "auto", "0,33", "0.33", True),
    (Fraction(1, 300), "auto", "0,0033", "0.0033", True),
    (Fraction(25, 2), "auto", "12,5", "12.5", False),
    (Fraction(123456, 10000), "auto", "12,3456", "12.3456", False),
    (Fraction(1234567, 100000), "auto", "12,35", "12.35", True),
    (Fraction(-24691, 20), "auto", "-1.234,55", "-1,234.55", False),
    (0, "auto", "0", "0", False),
    (Fraction(100, 3), 0, "33", "33", True),
    (Fraction(100, 3), 6, "33,333333", "33.333333", True),
    (Fraction(5, 2), 0, "3", "3", True),                         # half up
    (Fraction(3, 2), 4, "1,5", "1.5", False),                    # trailing zeros dropped
    (2 ** 0.5, "auto", "1,41", "1.41", True),
    (2.0000000000000004, "auto", "2", "2", False),
    (10 ** 14, "auto", "100.000.000.000.000", "100,000,000,000,000", False),
])
def test_numbers_are_said_the_language_s_way(m, lang, value, decimals, id_text, en_text, approx):
    lang("id")
    assert m.text.number(value, "id", decimals) == (id_text, approx)
    lang("en")
    assert m.text.number(value, "en", decimals) == (en_text, approx)


def test_huge_and_tiny_numbers_in_words(m, lang):
    lang("id")
    assert m.text.number(2 ** 60, "id") == ("1,15 kali 10 pangkat 18", True)
    assert m.text.number(Fraction(1, 10 ** 9), "id") == ("1 kali 10 pangkat -9", False)
    lang("en")
    assert m.text.number(Fraction(math_factorial(170)), "en")[0] == \
        "7.26 times 10 to the power of 306"


def math_factorial(n):
    import math
    return math.factorial(n)


def test_money_is_said_with_its_decimals(m, lang):
    lang("id")
    assert m.text.money_text(1790855, "IDR", "id") == "1.790.855 rupiah"
    assert m.text.money_text(Fraction(1255, 100), "USD", "id") == "12,55 dolar AS"
    assert m.text.money_text(Fraction(125, 10), "USD", "id") == "12,50 dolar AS"
    assert m.text.money_text(40, "USD", "id") == "40 dolar AS"
    assert m.text.money_text(Fraction(1, 17909), "USD", "id") == "0,0000558 dolar AS"
    lang("en")
    assert m.text.money_text(1, "USD", "en") == "1 US dollar"
    assert m.text.money_text(Fraction(8925, 1), "JPY", "en") == "8,925 yen"


# ------------------------------------------------------------
# Units
# ------------------------------------------------------------

def _unit(m, text):
    toks = m.numbers.tokenize(text)
    found = m.units.unit_at(toks, 0)
    assert found is not None and found[1] == len(toks), text
    return found[0]


@pytest.mark.parametrize("words, uid", [
    ("centimeter", "cm"), ("sentimeter", "cm"), ("cm", "cm"), ("senti", "cm"),
    ("feet", "foot"), ("foot", "foot"), ("kaki", "foot"), ("ft", "foot"),
    ("inci", "inch"), ("inch", "inch"), ("inches", "inch"), ("inchi", "inch"),
    ("mil", "mile"), ("miles", "mile"), ("mil laut", "nmi"), ("tahun cahaya", "ly"),
    ("gram", "g"), ("ons", "ons"), ("kuintal", "kuintal"), ("pon", "lb"), ("lbs", "lb"),
    ("liter", "l"), ("ml", "ml"), ("galon", "gallon"), ("galon inggris", "impgallon"),
    ("sendok makan", "tbsp"), ("sdm", "tbsp"), ("sendok teh", "tsp"), ("tsp", "tsp"),
    ("cangkir", "cup"), ("cups", "cup"), ("fl oz", "floz"),
    ("celsius", "celsius"), ("Celcius", "celsius"), ("°C", "celsius"),
    ("derajat celsius", "celsius"), ("farenheit", "fahrenheit"), ("°F", "fahrenheit"),
    ("kelvin", "kelvin"), ("reamur", "reamur"), ("Réaumur", "reamur"),
    ("km per jam", "kmh"), ("km/jam", "kmh"), ("km/h", "kmh"), ("kmh", "kmh"),
    ("mph", "mph"), ("miles per hour", "mph"), ("knot", "knot"), ("m/s", "mps"),
    ("meter persegi", "m2"), ("m2", "m2"), ("m²", "m2"), ("hektar", "ha"), ("are", "are"),
    ("acres", "acre"), ("square feet", "sqft"), ("tumbak", "tumbak"),
    ("detik", "sec"), ("menit", "min"), ("jam", "hour"), ("hari", "day"), ("minggu", "week"),
    ("bulan", "month"), ("tahun", "year"), ("abad", "century"),
    ("GB", "gb"), ("gigabyte", "gb"), ("MB", "mb"), ("Mb", "mbit"), ("megabit", "mbit"),
    ("GiB", "gib"), ("byte", "byte"), ("bit", "bit"),
    ("psi", "psi"), ("bar", "bar"), ("atm", "atm"), ("mmHg", "mmhg"), ("hPa", "hpa"),
    ("kkal", "kcal"), ("kalori", "kcal"), ("kJ", "kj"), ("kWh", "kwh"),
    ("km/l", "kml"), ("km per liter", "kml"), ("mpg", "mpg"), ("liter per 100 km", "l100"),
    ("radian", "rad"),
])
def test_unit_names(m, words, uid):
    assert uid in _unit(m, words)


def test_every_unit_has_its_names_and_the_table_is_sound(m):
    for uid, unit in m.units.UNITS.items():
        assert unit.id_name and unit.en_one and unit.en_many, uid
        assert unit.category in m.units.CATEGORIES
    for key, ids in m.units.INDEX.items():
        assert all(i in m.units.UNITS or i == "degrees" for i in ids), key
        categories = {m.units.UNITS[i].category for i in ids if i in m.units.UNITS}
        assert len(categories) == len([i for i in ids if i in m.units.UNITS]), key


@pytest.mark.parametrize("category", ["length", "mass", "volume", "speed", "area", "time",
                                      "data", "pressure", "energy", "fuel"])
def test_round_trips_in_every_category(m, category):
    ids = [uid for uid, u in m.units.UNITS.items() if u.category == category]
    for convention in (1024, 1000):
        for a in ids:
            for b in ids:
                there = m.units.convert(Fraction(7, 3), a, b, convention)
                back = m.units.convert(there, b, a, convention)
                assert back == Fraction(7, 3), (a, b, convention)


@pytest.mark.parametrize("value, src, dst, expected", [
    (0, "celsius", "fahrenheit", 32), (100, "celsius", "fahrenheit", 212),
    (-40, "celsius", "fahrenheit", -40), (37, "celsius", "fahrenheit", Fraction(986, 10)),
    (0, "celsius", "kelvin", Fraction(27315, 100)), (80, "reamur", "celsius", 100),
    (212, "fahrenheit", "reamur", 80), (0, "kelvin", "celsius", Fraction(-27315, 100)),
    (2, "foot", "inch", 24), (1, "mile", "km", Fraction(1609344, 10 ** 6)),
    (1, "kg", "ons", 10), (1, "kuintal", "kg", 100), (1, "ha", "m2", 10000),
    (1, "are", "m2", 100), (1, "tumbak", "m2", 14), (3, "hour", "min", 180),
    (1, "year", "day", 365), (1, "year", "month", 12), (1, "week", "day", 7),
    (1, "cup", "tbsp", 16), (1, "tbsp", "tsp", 3), (1, "cup", "ml", 240),
    (1, "bar", "pa", 100000), (1, "kwh", "kj", 3600), (1, "kcal", "kj", Fraction(4184, 1000)),
    (1, "byte", "bit", 8), (1, "gib", "mib", 1024), (1, "gbit", "mbit", 1000),
    (10, "kml", "l100", 10), (4, "l100", "kml", 25),
])
def test_known_conversions(m, value, src, dst, expected):
    assert m.units.convert(Fraction(value), src, dst) == expected


@pytest.mark.parametrize("src, dst, expected", [
    # Published definitions, to catch a slip in the table's factors.
    ("inch", "cm", 2.54), ("foot", "cm", 30.48), ("yard", "m", 0.9144), ("mile", "km", 1.609344),
    ("nmi", "km", 1.852), ("ly", "km", 9.4607304725808e12), ("oz", "g", 28.349523125),
    ("lb", "g", 453.59237), ("stone", "kg", 6.35029318), ("ons", "g", 100),
    ("kuintal", "kg", 100), ("ton", "kg", 1000), ("gallon", "l", 3.785411784),
    ("impgallon", "l", 4.54609), ("floz", "ml", 29.5735295625), ("pint", "ml", 473.176473),
    ("quart", "ml", 946.352946), ("barrel", "l", 158.987294928), ("m3", "l", 1000),
    ("acre", "m2", 4046.8564224), ("sqft", "m2", 0.09290304), ("sqmi", "km2", 2.589988110336),
    ("ha", "km2", 0.01), ("cm2", "m2", 0.0001), ("knot", "kmh", 1.852), ("mph", "kmh", 1.609344),
    ("mps", "kmh", 3.6), ("atm", "pa", 101325), ("mmhg", "pa", 133.322387415),
    ("psi", "pa", 6894.757293168), ("psi", "bar", 0.06894757293168), ("hpa", "pa", 100),
    ("kpa", "pa", 1000), ("kcal", "kj", 4.184), ("cal", "j", 4.184), ("kwh", "j", 3.6e6),
    ("wh", "j", 3600), ("mpg", "kml", 0.425143707430272), ("decade", "year", 10),
    ("century", "year", 100), ("msec", "sec", 0.001), ("day", "hour", 24),
    ("kbit", "byte", 125), ("mbit", "kbit", 1000), ("tib", "gib", 1024),
])
def test_unit_factors_match_their_definitions(m, src, dst, expected):
    assert float(m.units.convert(Fraction(1), src, dst)) == pytest.approx(expected, rel=1e-9)


def test_fuel_angles_and_absolute_zero(m):
    assert float(m.units.convert(Fraction(10), "kml", "mpg")) == pytest.approx(23.5215, rel=1e-4)
    assert m.units.convert(Fraction(180), "deg", "rad") == pytest.approx(3.14159265)
    with pytest.raises(m.units.ConvertError) as caught:
        m.units.convert(Fraction(-300), "celsius", "fahrenheit")
    assert caught.value.kind == "below_zero"
    with pytest.raises(m.units.ConvertError) as caught:
        m.units.convert(Fraction(0), "l100", "kml")
    assert caught.value.kind == "div_zero"


def test_data_sizes_follow_the_setting(m):
    assert m.units.convert(Fraction(1), "gb", "mb", 1024) == 1024
    assert m.units.convert(Fraction(1), "gb", "mb", 1000) == 1000
    assert m.units.convert(Fraction(1), "gb", "byte", 1024) == 1024 ** 3
    assert m.units.convert(Fraction(1), "gib", "gb", 1000) == Fraction(1024 ** 3, 1000 ** 3)
    assert m.units.notes("gb", "mb", 1024) == ["data_1024"]
    assert m.units.notes("gb", "mb", 1000) == ["data_1000"]
    assert m.units.notes("gib", "mib", 1024) == []            # always 1024: nothing to say


def test_ambiguous_words_are_settled_by_the_other_unit(m):
    assert m.units.pick(_unit(m, "kilo"), _unit(m, "pon")) == ("kg", "lb")
    assert m.units.pick(_unit(m, "kilo"), _unit(m, "mil")) == ("km", "mile")
    assert m.units.pick(_unit(m, "ounces"), _unit(m, "ml")) == ("floz", "ml")
    assert m.units.pick(_unit(m, "ounces"), _unit(m, "gram")) == ("oz", "g")
    assert m.units.pick(_unit(m, "degrees"), _unit(m, "celsius")) == ("fahrenheit", "celsius")
    assert m.units.pick(_unit(m, "derajat"), _unit(m, "fahrenheit")) == ("celsius", "fahrenheit")
    assert m.units.pick(_unit(m, "derajat"), _unit(m, "kelvin")) == ("celsius", "kelvin")
    assert m.units.pick(_unit(m, "derajat"), _unit(m, "radian")) == ("deg", "rad")
    assert m.units.pick(_unit(m, "derajat"), _unit(m, "derajat")) is None
    assert m.units.pick(_unit(m, "kaki"), _unit(m, "kg")) is None
    assert m.units.notes("ons", "g") == ["ons"] and m.units.notes("kcal", "kj") == ["kcal"]
    assert m.units.notes("month", "day") == ["month"] and m.units.notes("year", "day") == ["year"]
    assert m.units.notes("year", "month") == []


def test_unit_names_in_both_languages(m):
    assert m.units.name("inch", "id", 24) == "inci"
    assert m.units.name("inch", "en", 24) == "inches" and m.units.name("inch", "en", 1) == "inch"
    assert m.units.name("foot", "en", 2) == "feet"
    assert m.units.name("celsius", "en", 30) == "degrees Celsius"


# ------------------------------------------------------------
# Currencies and rates
# ------------------------------------------------------------

RATE_ROWS = [
    {"date": "2026-09-25", "base": "EUR", "quote": "IDR", "rate": 20405},
    {"date": "2026-09-25", "base": "EUR", "quote": "USD", "rate": 1.1394},
    {"date": "2026-09-24", "base": "EUR", "quote": "USD", "rate": 1.2},       # older: ignored
    {"date": "2026-09-25", "base": "EUR", "quote": "JPY", "rate": 178.5},
    {"date": "2026-09-24", "base": "EUR", "quote": "SGD", "rate": 1.47},
    {"date": "2026-09-25", "base": "EUR", "quote": "GBP", "rate": 0.85},
    {"date": "2026-09-25", "base": "USD", "quote": "IDR", "rate": 1},         # another base
    {"date": "bad", "base": "EUR", "quote": "XXX", "rate": 1},
    {"date": "2026-09-25", "base": "EUR", "quote": "ZZZ", "rate": -3},
    "junk",
]


def _rates(m, fetched=NOON):
    return m.money.parse_rates(RATE_ROWS, fetched)


def test_parse_rates_keeps_the_newest_row_of_each_currency(m):
    rates = _rates(m)
    assert rates.rates["USD"] == Fraction("1.1394") and rates.rates["EUR"] == 1
    assert "XXX" not in rates.rates and "ZZZ" not in rates.rates
    value, day = rates.convert(100, "USD", "IDR")
    assert round(value) == 1790855 and day == TODAY
    value, day = rates.convert(1, "SGD", "IDR")
    assert day == datetime.date(2026, 9, 24)                    # the older of the two
    with pytest.raises(m.money.RateError) as caught:
        rates.convert(1, "USD", "NOK")
    assert caught.value.kind == "unknown" and caught.value.code == "NOK"
    with pytest.raises(ValueError):
        m.money.parse_rates({"not": "a list"}, NOON)


def test_rates_survive_saving(m):
    rates = _rates(m)
    again = m.money.Rates.from_json(json.loads(json.dumps(rates.to_json())))
    assert again.rates == rates.rates and again.dates["SGD"] == datetime.date(2026, 9, 24)
    assert again.fetched == NOON
    assert m.money.Rates.from_json({"fetched": "nonsense"}) is None
    assert m.money.Rates.from_json({"fetched": NOON.isoformat(), "rates": {"x": [1, ""]}}) is None


class Clock:
    def __init__(self, now=NOON):
        self.now = now

    def __call__(self):
        return self.now


def test_the_rate_book_caches_and_falls_back(m):
    clock = Clock()
    saved = {}
    calls = []

    def fetch():
        calls.append(clock.now)
        return _rates(m, clock.now)

    book = m.money.RateBook(fetch=fetch, load=lambda: saved.get("data"),
                            save=lambda data: saved.update(data=data), now=clock)
    assert book.fresh() is None and book.usable() is None
    rates = book.refresh()
    assert calls == [NOON] and saved["data"]["rates"]["IDR"][0] == "20405"
    assert book.fresh() is rates
    clock.now = NOON + datetime.timedelta(hours=m.money.FRESH_HOURS, minutes=1)
    assert book.fresh() is None and book.usable() is rates
    # Offline: the older rates still answer, with their date.
    book._fetch = lambda: (_ for _ in ()).throw(m.money.RateError("offline"))
    assert book.refresh() is rates
    clock.now = NOON + datetime.timedelta(days=m.money.STALE_DAYS + 1)
    with pytest.raises(m.money.RateError):
        book.refresh()
    # A new run reads the saved copy.
    clock.now = NOON + datetime.timedelta(hours=1)
    again = m.money.RateBook(fetch=fetch, load=lambda: saved.get("data"), now=clock)
    assert again.fresh() is not None and again.fresh().rates["USD"] == Fraction("1.1394")


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self, limit=-1):
        return self.body[:limit] if limit >= 0 else self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetching_sends_nothing_but_the_address(m):
    seen = []

    def urlopen(request, timeout=None):
        seen.append((request.full_url, request.get_method(), request.data, timeout))
        return FakeResponse(json.dumps(RATE_ROWS[:6]).encode("utf-8"))

    rates = m.money.fetch_rates(NOON, urlopen=urlopen)
    assert rates.rates["IDR"] == 20405
    assert seen == [("https://api.frankfurter.dev/v2/rates?base=EUR", "GET", None,
                     m.money.TIMEOUT)]

    def broken(request, timeout=None):
        raise OSError("no network")

    for opener in (broken, lambda r, timeout=None: FakeResponse(b"<html>"),
                   lambda r, timeout=None: FakeResponse(b"[]"),
                   lambda r, timeout=None: FakeResponse(b"x" * (m.money.MAX_BYTES + 10))):
        with pytest.raises(m.money.RateError) as caught:
            m.money.fetch_rates(NOON, urlopen=opener)
        assert caught.value.kind == "offline"


@pytest.mark.parametrize("words, code", [
    ("dolar", "USD"), ("dollars", "USD"), ("USD", "USD"), ("dolar singapura", "SGD"),
    ("rupiah", "IDR"), ("IDR", "IDR"), ("euro", "EUR"), ("yen", "JPY"), ("ringgit", "MYR"),
    ("riyal", "SAR"), ("pound sterling", "GBP"), ("NOK", "NOK"), ("won", "KRW"),
])
def test_currency_names(m, words, code):
    toks = m.numbers.tokenize(words)
    assert m.money.currency_at(toks, 0) == (code, len(toks))


def test_pound_and_symbols(m):
    toks = m.numbers.tokenize("pound")
    assert m.money.currency_at(toks, 0) is None
    assert m.money.currency_at(toks, 0, with_pound=True) == ("GBP", 1)
    for text, code in (("$100", "USD"), ("Rp 50.000", "IDR"), ("Rp. 50.000", "IDR"),
                       ("€20", "EUR"), ("RM 5", "MYR"), ("US$ 5", "USD"), ("£3", "GBP")):
        toks = m.numbers.tokenize(text)
        found = m.money.symbol_at(toks, 0)
        assert found is not None and found[0] == code, text
    assert m.money.currency_at(m.numbers.tokenize("huf"), 0) is None     # only in capitals
    assert m.money.currency_at(m.numbers.tokenize("HUF"), 0) == ("HUF", 1)


# ------------------------------------------------------------
# The calculator: answers in both languages
# ------------------------------------------------------------

class Harness:
    """A Calculator with fakes: rates from RATE_ROWS, a clock, a seeded random
    generator, and what it copies, speaks and starts on threads."""

    def __init__(self, m, language="id", settings=None, rates=True, fetch=None):
        self.m = m
        self.language = language
        self.clock = 1000.0
        self.copied = []
        self.spoken = []
        self.threads = []
        self.now = Clock()
        fetched = []

        def default_fetch():
            fetched.append(1)
            return _rates(m, self.now.now)

        self.fetched = fetched
        self.book = m.money.RateBook(fetch=fetch or default_fetch, now=self.now)
        if rates:
            self.book.refresh()
            fetched.clear()
        self.calc = m.intents.Calculator(
            settings=settings, rates=self.book, language=lambda: self.language,
            copy=self.copied.append, speak=self.spoken.append,
            run_thread=lambda work, done: self.threads.append((work, done)),
            clock=lambda: self.clock, rng=random.Random(7), today=lambda: TODAY)

    def ask(self, text):
        """What the calculator answers, in its own language (the lang fixture
        restores Hariku's language afterwards)."""
        import core.commands
        from core import i18n
        i18n._current_language = self.language
        found = core.commands.match_intents(text, [self.intent()])
        slot = found[0].text if found else text
        reply = self.calc.on_request(core.commands.Request(slot, text))
        if isinstance(reply, core.commands.Reply):
            return reply
        return reply

    def act(self, name):
        """One of the actions ("copy_result", ...), in the harness's language."""
        from core import i18n
        i18n._current_language = self.language
        return getattr(self.calc, name)()

    def intent(self, old_core=False):
        """The intent as main.py registers it: a matcher and no patterns
        (core 2.11), or the patterns only (older cores)."""
        import core.commands
        if old_core:
            return core.commands.Intent("Calculator.calculate", self.m.intents.PATTERNS,
                                        self.calc.on_request)
        return core.commands.Intent("Calculator.calculate", [], self.calc.on_request,
                                    matcher=self.calc.matcher)

    def finish_threads(self):
        from core import i18n
        i18n._current_language = self.language
        while self.threads:
            work, done = self.threads.pop(0)
            done(work())


@pytest.fixture
def h(m, lang):
    lang("id")
    return Harness(m, "id")


@pytest.fixture
def h_en(m, lang):
    lang("en")
    return Harness(m, "en")


@pytest.mark.parametrize("text, answer", [
    ("berapa 25 kali 4", "25 kali 4 = 100."),
    ("25 x 4", "25 kali 4 = 100."),
    ("Berapa 25 kali 4?", "25 kali 4 = 100."),
    ("25 × 4.", "25 kali 4 = 100."),
    ("12 persen dari 350", "12% dari 350 = 42."),
    ("350 ditambah 12%", "350 tambah 12% = 392."),
    ("akar 144", "Akar 144 = 12."),
    ("akar pangkat tiga 27", "Akar pangkat tiga 27 = 3."),
    ("2 pangkat 10", "2 pangkat 10 = 1.024."),
    ("(3 + 4) * 2", "(3 tambah 4) kali 2 = 14."),
    ("100 dibagi 3", "100 bagi 3 = kira-kira 33,33."),
    ("sisa bagi 17 dan 5", "17 modulo 5 = 2."),
    ("sisa pembagian 17 dengan 5", "17 modulo 5 = 2."),
    ("7 faktorial", "7 faktorial = 5.040."),
    ("faktorial 7", "7 faktorial = 5.040."),
    ("hitung dua puluh lima kali empat", "25 kali 4 = 100."),
    ("satu koma lima kali dua", "1,5 kali 2 = 3."),
    ("minus tiga kali dua", "-3 kali 2 = -6."),
    ("2,5 kali 4", "2,5 kali 4 = 10."),
    ("1.250.000 dibagi 4", "1.250.000 bagi 4 = 312.500."),
    ("2 juta dibagi 3", "2.000.000 bagi 3 = kira-kira 666.666,67."),
    ("setengah dari 80", "0,5 dari 80 = 40."),
    ("25 kali 4 berapa", "25 kali 4 = 100."),
    ("25 kali 4 sama dengan berapa", "25 kali 4 = 100."),
    ("tolong hitung 5 + 5", "5 tambah 5 = 10."),
    ("berapa 12%", "12% = 0,12."),
    ("1 dibagi 0", "Angka tidak bisa dibagi nol."),
    ("2 pangkat 100000", "Angkanya terlalu besar buatku."),
    ("akar -4", "Bilangan negatif tidak punya akar kuadrat di bilangan real."),
    ("hitung 5 apel tambah 3 jeruk", "Aku belum bisa menghitung itu."),
    ("20 itu berapa persen dari 80", "20 adalah 25% dari 80."),
    ("berapa persen 30 dari 90", "30 kira-kira 33,33% dari 90."),
])
def test_indonesian_sums(h, text, answer):
    assert h.ask(text) == answer


@pytest.mark.parametrize("text, answer", [
    ("what's 15% of 80", "15% of 80 = 12."),
    ("what is 2 plus 2", "2 plus 2 = 4."),
    ("square root of 2", "The square root of 2 = about 1.41."),
    ("7 factorial", "7 factorial = 5,040."),
    ("twenty-five times four", "25 times 4 = 100."),
    ("one and a half plus a hundred", "1.5 plus 100 = 101.5."),
    ("3.5 million divided by 2", "3,500,000 divided by 2 = 1,750,000."),
    ("1,250,000 + 1", "1,250,000 plus 1 = 1,250,001."),
    ("calculate 2 to the power of 10", "2 to the power of 10 = 1,024."),
    ("remainder of 17 divided by 5", "17 mod 5 = 2."),
    ("20 is what percent of 80", "20 is 25% of 80."),
    ("what percent of 80 is 20", "20 is 25% of 80."),
    ("170!", "170 factorial = about 7.26 times 10 to the power of 306."),
    ("1 / 0", "Dividing by zero doesn't work."),
])
def test_english_sums(h_en, text, answer):
    assert h_en.ask(text) == answer


@pytest.mark.parametrize("text, answer", [
    ("2 kaki berapa inci", "2 kaki = 24 inci."),
    ("dua kaki berapa inci?", "2 kaki = 24 inci."),
    ("berapa inci 2 kaki", "2 kaki = 24 inci."),
    ("5 km ke mil", "5 kilometer = kira-kira 3,11 mil."),
    ("100 fahrenheit ke celsius", "100 derajat Fahrenheit = kira-kira 37,78 derajat Celsius."),
    ("30 derajat celsius berapa fahrenheit", "30 derajat Celsius = 86 derajat Fahrenheit."),
    ("30 derajat ke fahrenheit", "30 derajat Celsius = 86 derajat Fahrenheit."),
    ("minus 40 derajat celsius berapa fahrenheit",
     "-40 derajat Celsius = -40 derajat Fahrenheit."),
    ("1 galon berapa liter", "1 galon AS = kira-kira 3,79 liter."),
    ("70 kg dalam pon", "70 kilogram = kira-kira 154,32 pon."),
    ("5 kilo ke pon", "5 kilogram = kira-kira 11,02 pon."),
    ("10 kilo ke mil", "10 kilometer = kira-kira 6,21 mil."),
    ("60 mph ke km per jam", "60 mil per jam = kira-kira 96,56 kilometer per jam."),
    ("1 GB berapa MB", "1 gigabyte = 1.024 megabyte. (Hitungan 1024, seperti Windows.)"),
    ("3 jam berapa menit", "3 jam = 180 menit."),
    ("1 jam 30 menit berapa menit", "1 jam 30 menit = 90 menit."),
    ("1 hektar berapa meter persegi", "1 hektare = 10.000 meter persegi."),
    ("sekilo berapa ons", "1 kilogram = 10 ons. (1 ons = 100 gram.)"),
    ("3 ons berapa gram", "3 ons = 300 gram. (1 ons = 100 gram.)"),
    ("1 tahun berapa hari", "1 tahun = 365 hari. (1 tahun dihitung 365 hari.)"),
    ("1 bulan berapa hari", "1 bulan = kira-kira 30,42 hari. (1 bulan dihitung seperdua belas "
                            "tahun.)"),
    ("500 kalori ke kj", "500 kilokalori = 2.092 kilojoule. (Kalori di sini kalori makanan, "
                         "yaitu kilokalori.)"),
    ("2 cangkir berapa sendok makan", "2 cangkir = 32 sendok makan. (1 cangkir = 240 ml.)"),
    ("5 kaki 11 inci ke cm", "5 kaki 11 inci = 180,34 sentimeter."),
    ("170 cm ke kaki dan inci", "170 sentimeter = kira-kira 5 kaki 6,9 inci."),
    ("183 cm ke kaki dan inci", "183 sentimeter = kira-kira 6 kaki."),
    ("konversi 32 psi ke bar", "32 psi = kira-kira 2,21 bar."),
    ("15 km/l berapa l/100 km", "15 kilometer per liter = kira-kira 6,67 liter per 100 "
                                "kilometer."),
    ("berapa 5 km", "Mau diubah ke satuan apa? Misalnya: 5 km ke mil."),
    ("5 kaki ke kg", None),
    ("-300 celsius ke fahrenheit", "Itu lebih dingin dari nol mutlak."),
])
def test_indonesian_conversions(h, text, answer):
    assert h.ask(text) == answer


@pytest.mark.parametrize("text, answer", [
    ("2 foot in inches", "2 feet = 24 inches."),
    ("2 feet in inches", "2 feet = 24 inches."),
    ("1 foot to inches", "1 foot = 12 inches."),
    ("how many inches in 2 feet", "2 feet = 24 inches."),
    ("how many inches are in 2 feet", "2 feet = 24 inches."),
    ("how many ml in a cup", "1 cup = 240 milliliters. (A cup is 240 ml.)"),
    ("100 degrees to celsius", "100 degrees Fahrenheit = about 37.78 degrees Celsius."),
    ("5 km to miles", "5 kilometers = about 3.11 miles."),
    ("1 GB in MB", "1 gigabyte = 1,024 megabytes. (Counting 1024 per step, as Windows does.)"),
    ("convert 1 mile to km", "1 mile = about 1.61 kilometers."),
    ("100 pounds to kg", "100 pounds = about 45.36 kilograms."),
    ("8 ounces in ml", "8 fluid ounces = about 236.59 milliliters."),
    ("180 degrees to radians", "180 degrees = about 3.14 radians."),
    ("2 hours and 15 minutes in minutes", None),
    ("2 hours 15 minutes in minutes", "2 hours 15 minutes = 135 minutes."),
])
def test_english_conversions(h_en, text, answer):
    assert h_en.ask(text) == answer


def test_the_data_setting_changes_the_answer(m, lang):
    lang("en")
    h = Harness(m, "en", settings={"data": 1000})
    assert h.ask("1 GB in MB") == \
        "1 gigabyte = 1,000 megabytes. (Counting 1000 per step, as drive makers do.)"
    assert h.ask("1 GiB in MiB") == "1 gibibyte = 1,024 mebibytes."


def test_the_decimals_setting(m, lang):
    lang("id")
    h = Harness(m, "id", settings={"decimals": 4})
    assert h.ask("100 dibagi 3") == "100 bagi 3 = kira-kira 33,3333."
    h.calc.settings["decimals"] = 0
    assert h.ask("100 dibagi 3") == "100 bagi 3 = kira-kira 33."
    assert h.ask("5 km ke mil") == "5 kilometer = kira-kira 3 mil."


def test_currency_with_fresh_rates(h, h_en):
    assert h.ask("100 dolar berapa rupiah") == \
        "100 dolar AS = 1.790.855 rupiah, kurs 25 September."
    assert h.ask("50 euro ke yen") == "50 euro = 8.925 yen, kurs 25 September."
    assert h.ask("1 juta rupiah dalam dolar") == \
        "1.000.000 rupiah = 55,84 dolar AS, kurs 25 September."
    assert h.ask("Rp 1,5 juta ke dolar singapura") == \
        "1.500.000 rupiah = 108,06 dolar Singapura, kurs 24 September."
    assert h.ask("kurs dolar") == "1 dolar AS = 17.909 rupiah, kurs 25 September."
    assert h.ask("kurs euro ke yen") == "1 euro = 179 yen, kurs 25 September."
    assert h.ask("100 dolar berapa") == "100 dolar AS = 1.790.855 rupiah, kurs 25 September."
    assert h.ask("berapa rupiah 100 dolar") == \
        "100 dolar AS = 1.790.855 rupiah, kurs 25 September."
    assert h.ask("100 pound ke rupiah") == "100 pound sterling = 2.400.588 rupiah, kurs 25 " \
                                          "September."
    assert h.ask("100 dolar ke NOK") == "Aku tidak punya kurs untuk NOK."
    assert h.fetched == [] and h.threads == []
    assert h_en.ask("$100 to rupiah") == \
        "100 US dollars = 1,790,855 rupiah, at the rates of 25 September."
    assert h_en.ask("convert 100 usd to idr") == \
        "100 US dollars = 1,790,855 rupiah, at the rates of 25 September."
    assert h_en.ask("exchange rate of the euro") == \
        "1 euro = 1.14 US dollars, at the rates of 25 September."


def test_the_home_currency(m, lang):
    lang("en")
    h = Harness(m, "en")
    assert h.calc.home() == "USD"
    assert h.ask("how much is 1000 yen") == "1,000 yen = 6.38 US dollars, at the rates of 25 " \
                                          "September."
    h.calc.settings["home"] = "IDR"
    assert h.ask("how much is 1000 yen") == "1,000 yen = 114,314 rupiah, at the rates of 25 " \
                                          "September."
    h.language = "id"
    h.calc.settings["home"] = "auto"
    assert h.calc.home() == "IDR"
    assert h.ask("kurs rupiah").startswith("1 rupiah = 0,0000558 dolar AS")


def test_currency_waits_for_the_rates_then_says_them(m, lang):
    lang("id")
    h = Harness(m, "id", rates=False)
    reply = h.ask("100 dolar berapa rupiah")
    import core.commands
    assert isinstance(reply, core.commands.Reply) and reply.wait and not reply.say
    assert h.spoken == [] and len(h.threads) == 1
    h.finish_threads()
    assert h.spoken == ["100 dolar AS = 1.790.855 rupiah, kurs 25 September."]
    assert h.fetched == [1]
    # Now fresh: at once, no second fetch.
    assert h.ask("50 dolar ke rupiah") == "50 dolar AS = 895.427 rupiah, kurs 25 September."
    assert h.fetched == [1]


def test_currency_offline(m, lang):
    lang("id")

    def offline():
        raise m.money.RateError("offline")

    h = Harness(m, "id", rates=False, fetch=offline)
    reply = h.ask("100 dolar ke rupiah")
    assert reply.wait
    h.finish_threads()
    assert h.spoken == ["Aku belum bisa mengambil kurs sekarang. Cek koneksi internet, "
                        "lalu coba lagi."]
    lang("en")
    h.language = "en"
    h.spoken.clear()
    h.ask("100 dollars to rupiah")
    h.finish_threads()
    assert h.spoken == ["I can't get exchange rates right now. Check the internet connection "
                        "and try again."]


def test_old_rates_answer_when_offline(m, lang):
    lang("id")
    h = Harness(m, "id")
    h.now.now = NOON + datetime.timedelta(days=2)
    h.book._fetch = lambda: (_ for _ in ()).throw(m.money.RateError("offline"))
    h.ask("100 dolar ke rupiah")
    h.finish_threads()
    assert h.spoken == ["100 dolar AS = 1.790.855 rupiah, kurs 25 September."]


# ------------------------------------------------------------
# Follow-ups on the last result
# ------------------------------------------------------------

def test_follow_ups_in_indonesian(h):
    assert h.ask("25 x 4") == "25 kali 4 = 100."
    assert h.ask("tambah 5") == "100 tambah 5 = 105."
    assert h.ask("kali dua") == "105 kali 2 = 210."
    assert h.ask("bagi 3") == "210 bagi 3 = 70."
    assert h.ask("hasilnya dikurangi 10") == "70 kurang 10 = 60."
    assert h.ask("tambah 10%") == "60 tambah 10% = 66."
    assert h.ask("pangkat 2") == "66 pangkat 2 = 4.356."
    assert h.ask("akar hasilnya") == "Akar 4.356 = 66."
    assert h.ask("berapa hasilnya") == "Hasil terakhir: 66."
    assert h.act("copy_result") == "Disalin: 66."
    assert h.copied == ["66"]


def test_follow_ups_in_english(h_en):
    h_en.ask("12 times 12")
    assert h_en.ask("plus 5") == "144 plus 5 = 149."
    assert h_en.ask("times two") == "149 times 2 = 298."
    assert h_en.ask("the result divided by 4") == "298 divided by 4 = 74.5."
    assert h_en.ask("minus 0.5") == "74.5 minus 0.5 = 74."
    assert h_en.act("copy_result") == "Copied: 74."


def test_follow_ups_keep_the_unit_or_currency(h):
    h.ask("2 kaki berapa inci")
    assert h.ask("kali 2") == "24 inci kali 2 = 48 inci."
    assert h.ask("hasilnya kali hasilnya") == "48 inci kali 48 inci = 2.304."
    h.ask("100 dolar berapa rupiah")
    assert h.ask("bagi 4") == "1.790.855 rupiah bagi 4 = 447.714 rupiah."
    assert h.act("copy_result") == "Disalin: 447.714."


def test_the_last_result_expires(h):
    h.ask("25 x 4")
    h.clock += h.m.intents.FOLLOW_UP_SECONDS + 1
    assert h.ask("tambah 5") is None                       # not ours without a result
    assert h.ask("hasilnya kali 2") == "Belum ada hasil sebelumnya."
    assert h.ask("berapa hasilnya") == "Belum ada hasil sebelumnya."
    assert h.act("copy_result") == "Belum ada hasil untuk disalin."
    assert h.act("last_result") == "Belum ada hasil sebelumnya."


def test_a_typed_negative_number_starts_a_new_sum(h):
    h.ask("25 x 4")
    assert h.ask("-5 + 3") == "-5 tambah 3 = -2."
    assert h.ask("minus 2") == "-2 kurang 2 = -4."


def test_auto_copy(m, lang):
    lang("en")
    h = Harness(m, "en", settings={"auto_copy": True})
    h.ask("100 / 3")
    h.ask("2 feet in inches")
    h.ask("100 dollars to rupiah")
    assert h.copied == ["33.33", "24", "1,790,855"]
    h.ask("flip a coin")
    assert h.copied == ["33.33", "24", "1,790,855"]           # nothing to copy there


# ------------------------------------------------------------
# Extras (seeded)
# ------------------------------------------------------------

def test_coin_dice_and_random_numbers(h, h_en):
    assert h.ask("lempar koin") in ("Hasilnya angka.", "Hasilnya gambar.")
    assert h_en.ask("flip a coin") in ("It's heads.", "It's tails.")
    sides = {h.ask("lempar koin") for _i in range(30)}
    assert sides == {"Hasilnya angka.", "Hasilnya gambar."}
    assert re.fullmatch(r"Dadunya: [1-6]\.", h.ask("lempar dadu"))
    assert re.fullmatch(r"2 dadu: [1-6] dan [1-6]\. Jumlahnya \d+\.", h.ask("lempar 2 dadu"))
    assert re.fullmatch(r"The die shows \d+\.", h_en.ask("roll a d20"))
    assert re.fullmatch(r"3 dice: \d, \d and \d\. Total \d+\.", h_en.ask("roll 3d6"))
    assert h.ask("lempar 11 dadu") == \
        "Aku bisa melempar 1 sampai 10 dadu, dengan 2 sampai 1000 sisi."
    for _i in range(50):
        value = int(h.ask("angka acak 1 sampai 6").rsplit(" ", 1)[1].rstrip("."))
        assert 1 <= value <= 6
    assert h.ask("angka acak antara 10 dan 1").startswith("Angka acak dari 1 sampai 10: ")
    assert h.ask("angka acak sampai 3").startswith("Angka acak dari 1 sampai 3: ")
    assert h_en.ask("random number between 1 and 100").startswith(
        "A random number from 1 to 100: ")
    assert h.act("random_number").startswith("Angka acak dari 1 sampai 100: ")
    assert h.ask("angka acak 1,5 sampai 3") == \
        "Sebutkan dua bilangan bulat, misalnya: angka acak 1 sampai 100."


def test_coin_and_die_actions(h, h_en):
    # Commands of their own too, so "flip a coin" works on cores without a matcher.
    assert h.act("flip_coin") in ("Hasilnya angka.", "Hasilnya gambar.")
    assert re.fullmatch(r"Dadunya: [1-6]\.", h.act("roll_die"))
    assert h_en.act("flip_coin") in ("It's heads.", "It's tails.")
    assert re.fullmatch(r"The die shows [1-6]\.", h_en.act("roll_die"))


def test_the_same_seed_gives_the_same_rolls(m, lang):
    lang("en")
    first = [Harness(m, "en").ask("roll 5 dice") for _i in range(2)]
    assert first[0] == first[1]


def test_split_the_bill(h, h_en):
    assert h.ask("bagi tagihan 350 ribu untuk 4 orang") == "Dibagi 4 orang, masing-masing 87.500."
    assert h.ask("bagi tagihan 350 ribu untuk 4 orang tip 10%") == \
        "Dengan tip 10%, totalnya 385.000. Dibagi 4 orang, masing-masing 96.250."
    assert h.ask("patungan 100 ribu plus tip 10 persen 3 orang") == \
        "Dengan tip 10%, totalnya 110.000. Dibagi 3 orang, masing-masing 36.666,67."
    assert h_en.ask("split 120 dollars 3 ways") == "Split between 3, each pays 40 US dollars."
    assert h_en.ask("split 120 dollars 3 ways with a 15% tip") == \
        "With a 15% tip the total is 138 US dollars. Split between 3, each pays 46 US dollars."
    assert h_en.ask("split the bill of 90 between 4 people") == "Split between 4, each pays 22.5."
    assert h.ask("bagi tagihan 100 ribu untuk 0 orang") == "Bagi untuk 1 sampai 1000 orang."


def test_discounts(h, h_en):
    assert h.ask("diskon 30% dari 250 ribu") == "Setelah diskon 30%: 175.000. Hemat 75.000."
    assert h.ask("250 ribu diskon 30%") == "Setelah diskon 30%: 175.000. Hemat 75.000."
    assert h.ask("harga 250 ribu diskon 30 persen") == \
        "Setelah diskon 30%: 175.000. Hemat 75.000."
    assert h.ask("potongan 20 persen untuk Rp 100.000") == \
        "Setelah diskon 20%: 80.000 rupiah. Hemat 20.000 rupiah."
    assert h_en.ask("30% off 250") == "After 30% off: 175. You save 75."
    assert h_en.ask("250 with 30% off") == "After 30% off: 175. You save 75."
    assert h_en.ask("discount 15% on 80 dollars") == \
        "After 15% off: 68 US dollars. You save 12 US dollars."
    assert h.ask("diskon 150% dari 100") == "Diskon atau tip dari 0 sampai 100 persen."


# ------------------------------------------------------------
# Aruna: what is ours, what isn't
# ------------------------------------------------------------

def _literal(node):
    try:
        return ast.literal_eval(node)
    except ValueError:
        return None


def _other_extension_commands():
    """Commands and patterns of World Trip, Dropbox and Orbit, read from their
    main.py without importing them: [(action id, aliases)], [(intent id,
    patterns)]."""
    actions, intents = [], []
    for ext in ("world_trip", "dropbox", "orbit"):
        path = os.path.join(ROOT, "extensions", ext, "main.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        ext_name = ext
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                    isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name == "EXT_NAME":
                    ext_name = _literal(node.value)
        for node in tree.body:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and
                    isinstance(node.targets[0], ast.Name)):
                continue
            name = node.targets[0].id
            if name.endswith("_PATTERNS"):
                patterns = _literal(node.value)
                if patterns:
                    intents.append((f"{ext_name}.{name[:-9].lower()}", list(patterns)))
            elif name == "ACTIONS" and isinstance(node.value, (ast.Tuple, ast.List)):
                for entry in node.value.elts:
                    if not isinstance(entry, ast.Tuple) or not entry.elts:
                        continue
                    action = _literal(entry.elts[0])
                    for part in entry.elts[1:]:
                        value = _literal(part) if isinstance(part, (ast.Tuple, ast.List)) \
                            else None
                        if value and all(isinstance(v, str) for v in value):
                            actions.append((f"{ext_name}.{action}", list(value)))
    assert intents and actions
    return actions, intents


_FOREIGN = []


def _foreign_commands():
    """Hariku's own commands and the other extensions', as core.commands
    Commands (made once)."""
    if not _FOREIGN:
        import core.commands
        timer_dir = os.path.join(ROOT, "extensions", "timer_alarm")
        if timer_dir not in sys.path:
            sys.path.insert(0, timer_dir)
        import timer_alarm_intents
        actions, _intents = _other_extension_commands()
        for action_id, aliases in list(core.commands.BUILTIN_ALIASES.items()) + actions:
            _FOREIGN.append(core.commands.Command(action_id, action_id, aliases))
        for name, aliases in timer_alarm_intents.ALIASES.items():
            _FOREIGN.append(core.commands.Command(f"Timer and Alarm.{name}", name, aliases))
    return list(_FOREIGN)


class FakeAruna:
    """What ui/command_bar.py does with a text, without the window: intents
    are asked in turn (the calculator's real handler, the others answer
    "<intent id>" except Timer & Alarm's time corrections, which need an alarm
    waiting), then commands."""

    def __init__(self, m, h, with_calculator=True):
        import core.commands
        from core import when
        import timer_alarm_intents
        self.m = m
        self.c = core.commands
        self.h = h
        _actions, others = _other_extension_commands()
        self.commands_list = _foreign_commands()
        if with_calculator:
            for name, aliases in m.intents.ALIASES.items():
                self.commands_list.append(core.commands.Command(f"Calculator.{name}", name,
                                                                aliases))

        def owner(intent_id):
            return lambda request: None if intent_id.endswith(".fix") else f"<{intent_id}>"

        self.intents = [h.intent()] if with_calculator else []
        for name, patterns in timer_alarm_intents.PATTERNS.items():
            intent_id = f"Timer and Alarm.{name}"
            self.intents.append(core.commands.Intent(intent_id, patterns, owner(intent_id)))
        for intent_id, patterns in others:
            self.intents.append(core.commands.Intent(intent_id, patterns, owner(intent_id)))
        self.parse = lambda text: when.parse(text, now=NOON, language="id", packs=["id", "en"])

    def without_calculator(self):
        return FakeAruna(self.m, self.h, with_calculator=False)

    def send(self, text):
        """(who answered, what was said): who is an intent or action id,
        "reminder", "unknown" or "confirm". As core.commands.decide(), with the
        commands scored only when no intent took the text (it is slow)."""
        text = " ".join(text.split())
        result = self.c._parse(text, self.parse)
        if result is not None and result.trigger:
            return "reminder", ""
        for found in self.c.match_intents(text, self.intents):
            request = self.c.Request(found.text, text, "typed", found.intent.id)
            reply = self.c.Reply.of(found.intent.handler(request))
            if reply is not None:
                return found.intent.id, reply.say
        decision = self.c._decide_without_intents(text, result, self.commands_list)
        if decision.kind == "run":
            return decision.action_id, ""
        return decision.kind, ""


@pytest.fixture
def aruna(m, lang):
    timer_dir = os.path.join(ROOT, "extensions", "timer_alarm")
    if timer_dir not in sys.path:
        sys.path.insert(0, timer_dir)
    lang("id")
    h = Harness(m, "id")
    return FakeAruna(m, h)


CALCULATOR_SENTENCES = [
    "berapa 25 kali 4", "25 x 4", "25 kali 4", "12 persen dari 350", "350 ditambah 12%",
    "akar 144", "akar pangkat tiga 27", "2 pangkat 10", "(3 + 4) * 2", "100 dibagi 3",
    "sisa bagi 17 dan 5", "what's 15% of 80", "square root of 2", "7 factorial",
    "dua puluh lima kali empat", "2 foot in inches", "2 kaki berapa inci", "5 km ke mil",
    "100 fahrenheit ke celsius", "30 derajat celsius berapa fahrenheit", "1 galon berapa liter",
    "70 kg dalam pon", "60 mph ke km per jam", "1 GB berapa MB", "3 jam berapa menit",
    "1 hektar berapa meter persegi", "100 dolar berapa rupiah", "50 euro ke yen",
    "1 juta rupiah dalam dolar", "kurs dolar", "lempar koin", "flip a coin", "lempar 2 dadu",
    "roll a die", "angka acak 1 sampai 100", "random number between 1 and 100",
    "bagi tagihan 350 ribu untuk 4 orang", "split 120 dollars 3 ways",
    "diskon 30% dari 250 ribu", "30% off 250", "10 menit berapa detik", "3 jam ke menit",
    "Berapa 25 kali 4?", "Dua kaki berapa inci?", "2 kaki = berapa inci",
]


@pytest.mark.parametrize("text", CALCULATOR_SENTENCES)
def test_aruna_gives_sums_and_conversions_to_the_calculator(aruna, text):
    who, said = aruna.send(text)
    assert who == "Calculator.calculate", (text, who)
    assert said


OTHER_SENTENCES = [
    # Timer & Alarm
    "timer 10 menit", "timer mie 3 menit", "set a timer for 1 hour 30 minutes",
    "hitung mundur 90 detik", "timer tea 4-5 minutes", "timer setengah jam",
    "alarm besok jam 5 pagi", "bangunkan aku jam 4.30", "wake me up at 6", "batalkan timer mie",
    "sisa timer mie", "berapa lama lagi timer mie", "how long is left on the tea timer",
    "tunda 10 menit", "snooze 5 minutes", "berapa lama lagi", "daftar alarm", "stop",
    "cancel all timers", "delete the 18:00 alarm", "jam 2 siang", "at 5", "tunda",
    # World Trip, Dropbox, Orbit
    "take me to Tokyo", "bawa aku ke Paris", "terbang ke Seoul", "tell me about Jakarta",
    "next station", "radio louder", "jam berapa di sana", "what time is it there", "where am I",
    "di mana aku", "go home", "pulang", "teach me a phrase",
    "salin link", "copy link", "salin link laporan", "copy link to the budget",
    "dropbox status", "bagikan link ini",
    "orbit pergi ke kantin", "orbit beri Sari 50 kredit", "orbit beli 2 kopi", "buka orbit",
    "orbit siapa online",
    # Hariku's own
    "jam berapa", "what time is it", "tanggal berapa", "hari ini hari apa", "cuaca",
    "berapa suhu", "weather", "weather forecast", "gempa terbaru", "ringkasan malam",
    "briefing pagi", "keraskan suara", "volume up", "buka pengaturan", "tambah pengingat",
    "pengingat baru", "catat pengeluaran", "jam dunia", "diam", "stop talking",
    "kualitas udara", "di mana iss", "pesawat terdekat", "saldo", "metar",
    "ingatkan aku minum obat besok jam 8", "remind me to call mom tomorrow at 7pm",
    "rapat 25/12 jam 10", "minum obat 3x sehari jam 8", "besok jam 5 kurang 10 rapat",
    "25/12", "10:30", "jam setengah 5",
]


@pytest.fixture(scope="module")
def own_commands(m):
    import core.commands
    return [core.commands.Command(f"Calculator.{name}", name, aliases)
            for name, aliases in m.intents.ALIASES.items()]


@pytest.mark.parametrize("text", OTHER_SENTENCES)
def test_aruna_leaves_other_commands_alone(h, own_commands, text):
    """With the calculator installed, every other sentence goes where it went
    without it: the matcher doesn't take it, the handler turns down whatever
    a pattern of ours took from it, and our actions' names score too low to
    win or to make another command's clear win a question."""
    import core.commands
    c = core.commands
    assert h.calc.matcher(text) is None, text
    for found in c.match_intents(text, [h.intent()]):
        assert h.calc.on_request(c.Request(found.text, text)) is None, text
    mine = c.match(text, own_commands).score
    if mine >= c.ASK_SCORE:
        # Close enough to be asked about alone ("salin link" is like "salin
        # hasil"), so the command it is for must still clearly win.
        theirs = c.match(text, _foreign_commands()).score
        assert theirs >= c.RUN_SCORE and theirs - mine >= c.RUN_MARGIN, (text, mine, theirs)


@pytest.mark.parametrize("text", ["rapat 25/12 jam 10", "timer mie 3 menit", "berapa lama lagi",
                                  "jam berapa di sana", "tambah pengingat"])
def test_aruna_without_the_calculator_decides_the_same(aruna, text):
    assert aruna.send(text) == aruna.without_calculator().send(text)


@pytest.mark.parametrize("text, owner", [
    ("timer 10 menit", "Timer and Alarm.timer"), ("hitung mundur 90 detik", "Timer and Alarm.timer"),
    ("berapa lama lagi timer mie", "Timer and Alarm.left"), ("tunda 10 menit",
                                                             "Timer and Alarm.snooze"),
    ("take me to Tokyo", "World Trip.trip"), ("salin link laporan", "Dropbox.link"),
    ("orbit beri Sari 50 kredit", "Orbit.play"), ("jam berapa", "Hariku Core.speak_time"),
    ("berapa suhu", "Weather.speak_current_weather"), ("cuaca", "Weather.speak_current_weather"),
    ("tambah pengingat", "Hariku Core.quick_reminder"),
    ("ingatkan aku minum obat besok jam 8", "reminder"), ("rapat 25/12 jam 10", "reminder"),
])
def test_aruna_still_finds_their_owners(aruna, text, owner):
    assert aruna.send(text)[0] == owner


@pytest.mark.parametrize("text", ["25/12", "10:30", "0812-3456-7890", "2026-09-25", "17-08-1945",
                                  "+62 812 3456 7890", "5", "-5", "12%", "dua", "10 menit",
                                  "5 km", "100 dolar", "setengah 5", "jam 5 kurang 10",
                                  "hasilnya", "kali", "tambah", "berapa", "x", "2x + 3 = 7",
                                  "1 minggu ke depan", "2 jam ke kantor", "5 menit ke rumah",
                                  "10 orang ke bandung", "lima menit lagi", "3 hari lagi",
                                  "satu kali", "dua kali lipat", "sekali lagi", "take 5",
                                  "top 10", "iphone 15 pro", "windows 11", "covid 19"])
def test_the_matcher_is_strict(aruna, text):
    assert aruna.h.calc.matcher(text) is None, text


def test_follow_ups_are_only_ours_with_a_recent_result(aruna):
    assert aruna.send("tambah 5")[0] != "Calculator.calculate"
    aruna.send("25 x 4")
    assert aruna.send("tambah 5") == ("Calculator.calculate", "100 tambah 5 = 105.")
    assert aruna.send("kali dua") == ("Calculator.calculate", "105 kali 2 = 210.")
    assert aruna.send("salin hasilnya")[0] == "Calculator.copy_result"
    assert aruna.send("tambah pengingat")[0] == "Hariku Core.quick_reminder"


def test_patterns_are_valid(m):
    import core.commands
    intent = core.commands.Intent("Calculator.calculate", m.intents.PATTERNS, lambda r: None)
    assert len(intent.patterns) == len(m.intents.PATTERNS) == len(set(m.intents.PATTERNS))
    assert all(p.size >= 1 for p in intent.patterns)
    # Few, for Voice Control's vocabulary (older cores only).
    assert len(m.intents.PATTERNS) <= 20


@pytest.mark.parametrize("text, answered", [
    ("berapa 25 kali 4", True), ("hitung 5 + 5", True), ("what's 15% of 80", True),
    ("25 kali 4 berapa", True), ("convert 5 km to miles", True), ("how many inches in 2 feet", True),
    ("berapa inci 2 kaki", True), ("100 dolar berapa", True), ("lempar koin", True),
    ("angka acak 1 sampai 6", True), ("bagi tagihan 350 ribu untuk 4 orang", True),
    ("7 faktorial", True), ("sisa bagi 17 dan 5", True), ("square root of 2", True),
    ("berapa diskon 30% dari 250 ribu", True), ("berapa kurs dolar", True),
    # the examples on the Preferences page and in the store description
    ("what's 25 x 4", True), ("convert 2 feet to inches", True), ("berapa akar 144", True),
    ("konversi 30 derajat celsius ke fahrenheit", True), ("convert 100 dollars to rupiah", True),
    ("random number from 1 to 6", True), ("hasilnya tambah 5", True),
    ("the result times two", True), ("berapa 12 persen dari 350", True),
    # without a lead word these need core 2.11's matcher
    ("25 x 4", False), ("2 kaki berapa inci", False), ("5 km ke mil", False),
])
def test_an_older_core_answers_after_a_lead_word(h, text, answered):
    import core.commands
    h.ask("7 x 6")                                     # a result for the follow-ups
    found = core.commands.match_intents(text, [h.intent(old_core=True)])
    reply = h.calc.on_request(core.commands.Request(found[0].text, text)) if found else None
    assert (reply is not None) is answered, (text, reply)


def test_the_matcher_adds_nothing_to_voice_control_s_vocabulary(h, monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {"Calculator.calculate": h.intent()})
    assert core.commands.vocabulary({}) == []
    monkeypatch.setattr(core.commands, "_intents",
                        {"Calculator.calculate": h.intent(old_core=True)})
    assert "berapa" in core.commands.vocabulary({})


# ------------------------------------------------------------
# Personas and texts
# ------------------------------------------------------------

def _locale(code):
    with open(os.path.join(EXT_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)["messages"]


def test_both_languages_have_the_same_texts():
    assert set(_locale("en")) == set(_locale("id"))


@pytest.mark.parametrize("code", ["en", "id"])
def test_persona_texts_are_valid(code):
    import core.persona
    messages = _locale(code)
    fields = lambda s: sorted(re.findall(r"\{(\w+)\}", s))
    variants = [k for k in messages if "@" in k]
    assert len(variants) >= 40
    for key in variants:
        base, persona = key.split("@", 1)
        assert persona in core.persona.PERSONAS and persona != core.persona.DEFAULT, key
        assert base in messages, key
        assert fields(messages[key]) == fields(messages[base]), key
        assert messages[key].strip() and "  " not in messages[key], key
        assert messages[key] != messages[base], key
    main_lines = ("calc_result", "calc_about", "convert_result", "convert_about", "money_result",
                  "copied", "coin_result", "err_syntax", "err_div_zero", "err_too_big",
                  "err_offline", "err_no_result", "hint_no_target")
    for base in main_lines:
        for persona in ("sweet", "bro", "royal", "polite"):
            assert f"{base}@{persona}" in messages, (base, persona)


def test_a_persona_changes_the_words(h, h_en):
    from core import i18n
    i18n.set_persona("royal")
    assert h_en.ask("25 x 4") == "By my reckoning, 25 times 4 = 100."
    assert h_en.ask("2 feet in inches") == "By the royal measure, 2 feet = 24 inches."
    i18n.set_persona("bro")
    assert h_en.ask("1 / 0") == "Divide by zero? No can do."
    i18n.set_persona("")
    assert h_en.ask("25 x 4") == "25 times 4 = 100."


def test_keys_made_at_run_time_exist(m):
    en = _locale("en")
    needed = [f"action_{n}" for n in m.intents.ACTIONS]
    needed += list(m.text.ERROR_KEYS.values()) + list(m.text.NOTE_KEYS.values())
    needed += list(m.text.OP_KEYS.values()) + list(m.text.POSTFIX_KEYS.values())
    needed += ["op_sqrt", "op_cbrt", "op_root", "sci", "and", "coin_heads", "coin_tails",
               "ext_name", "intent_title", "home_auto", "home_item", "decimals_auto",
               "data_1024", "data_1000"]
    assert [k for k in needed if k not in en] == []
    for code in ("en", "id"):
        for key, value in _locale(code).items():
            assert value.strip() == value and "  " not in value, (code, key)


def test_the_expression_is_said_back(m, lang):
    lang("en")

    def said(text):
        return m.text.expression(m.math.lex(m.numbers.tokenize(text), "en"), "en")

    assert said("(3+4)*-2") == "(3 plus 4) times -2"
    assert said("12% of 350") == "12% of 350"
    assert said("akar pangkat 5 dari 32") == "root 5 of 32"
    assert said("5 squared + 2 cubed") == "5 squared plus 2 cubed"


# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------

def test_settings_are_checked(m):
    normalize = m.intents.normalize_settings
    assert normalize(None) == m.intents.DEFAULT_SETTINGS
    assert normalize({"home": "SGD", "decimals": 3, "data": 1000, "auto_copy": True}) == \
        {"home": "SGD", "decimals": 3, "data": 1000, "auto_copy": True}
    assert normalize({"home": "XYZ", "decimals": 9, "data": 999, "auto_copy": "yes"}) == \
        m.intents.DEFAULT_SETTINGS
    assert normalize({"decimals": True})["decimals"] == "auto"
    assert all(money_ok(m, code) for code in m.intents.HOME_CHOICES[1:])


def money_ok(m, code):
    return code in m.money.CURRENCIES


# ------------------------------------------------------------
# Registering with Hariku
# ------------------------------------------------------------

@pytest.fixture
def main(m, monkeypatch, lang):
    import importlib.util
    import core.commands
    import core.hotkeys
    import core.preferences
    monkeypatch.setattr(core.commands, "_intents", {})
    monkeypatch.setattr(core.commands, "_aliases", {})
    monkeypatch.setattr(core.commands, "_titles", {})
    monkeypatch.setattr(core.commands, "_answer_actions", set())
    monkeypatch.setattr(core.preferences, "_panels", {})
    monkeypatch.setattr(core.hotkeys, "actions", {})
    monkeypatch.setattr(core.hotkeys, "keybindings", {})
    spec = importlib.util.spec_from_file_location("hariku_ext.calculator_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from core.events import EventBus
    h = Harness(m, "en")
    module.register(EventBus(), calculator=h.calc)
    yield types.SimpleNamespace(module=module, h=h)
    module.teardown()


def test_registering(main):
    import core.commands
    import core.hotkeys
    import core.preferences
    ids = [f"Calculator.{n}" for n in main.module.intents.ACTIONS]
    assert sorted(core.hotkeys.actions) == sorted(ids)
    assert all(core.hotkeys.actions[i].default_keycode is None for i in ids)
    assert all(core.commands.is_answer_action(i) for i in ids)
    assert "salin hasilnya" in core.commands.aliases_for("Calculator.copy_result")
    [intent] = core.commands.intents()
    assert intent.id == "Calculator.calculate" and intent.matcher is not None
    assert intent.patterns == []                     # nothing for Voice Control's vocabulary
    assert "Calculator & Converter" in core.preferences.get_all_panels()
    for text, said in (("25 x 4", "25 times 4 = 100."), ("berapa 25 kali 4", "25 times 4 = 100."),
                       ("2 feet in inches", "2 feet = 24 inches.")):
        found = core.commands.match_intents(text)
        assert [(f.intent.id, f.size) for f in found] == [("Calculator.calculate", 0)]
        assert found[0].intent.handler(core.commands.Request(found[0].text, text)) == said
    assert core.commands.match_intents("jam berapa") == []


def test_teardown_removes_what_it_added(main):
    import core.commands
    main.module.teardown()
    assert core.commands.intents() == []
    assert core.commands.aliases_for("Calculator.copy_result") == []


def test_an_older_core_gets_the_patterns_only(m, monkeypatch, lang):
    # Core 2.9 and 2.10: add_intent has no matcher; "25 x 4" needs a lead word.
    import importlib.util
    import core.commands
    import core.hotkeys
    import core.preferences
    added = []
    monkeypatch.delattr(core.commands, "INTENT_MATCHERS")
    monkeypatch.setattr(core.commands, "add_intent",
                        lambda intent_id, patterns, handler, title=None:
                        added.append((intent_id, patterns, handler, title)))
    monkeypatch.setattr(core.commands, "_aliases", {})
    monkeypatch.setattr(core.commands, "_answer_actions", set())
    monkeypatch.setattr(core.preferences, "_panels", {})
    monkeypatch.setattr(core.hotkeys, "actions", {})
    monkeypatch.setattr(core.hotkeys, "keybindings", {})
    spec = importlib.util.spec_from_file_location("hariku_ext.calculator_old_core",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from core.events import EventBus
    module.register(EventBus(), calculator=Harness(m, "en").calc)
    assert [a[0] for a in added] == ["Calculator.calculate"]
    assert added[0][1] == m.intents.PATTERNS
    monkeypatch.setattr(core.commands, "remove_intent", lambda intent_id: True)
    module.teardown()


def test_the_preferences_page_is_applied(main, monkeypatch):
    import core.api
    saved = {}
    monkeypatch.setattr(core.api, "save_data", lambda key, data: saved.update({key: data}))

    class FakePanel:
        def get_settings(self):
            return {"home": "SGD", "decimals": 2, "data": 1000, "auto_copy": True}

    main.module._panel = FakePanel()
    main.module._apply_panel()
    assert saved["Calculator"]["home"] == "SGD"
    assert main.h.calc.settings["data"] == 1000 and main.h.calc.home() == "SGD"


def test_official_extension():
    for path, name in (("core/extension_manager.py", "_OFFICIAL_EXTENSION_IDS"),
                       ("tools/server/generate_trusted_hashes.py", "OFFICIAL_EXTENSION_IDS")):
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            assert '"calculator"' in f.read(), path
    with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["id"] == "calculator" and manifest["minimum_core_version"] == "2.9"
    assert manifest["version"] == "1.0" and manifest["main"] == "main.py"
