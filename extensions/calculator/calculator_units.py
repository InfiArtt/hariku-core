# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Units of measure for Calculator & Converter. No wx here.

    unit_at(toks, i)                  -> ([Unit], end): the units a phrase can mean
    pick(sources, targets)            -> (Unit, Unit) of one category, or None
    convert(value, src, dst, conv)    -> the value in dst
    name(unit, language, value)       -> "inci", "inches", "derajat Celsius"
    notes(src, dst, conv)             -> ["ons"], ["data_1024"], ...

Categories: length, mass, volume (cooking too: a cup is 240 ml, a tablespoon
15 ml, a teaspoon 5 ml, as on US food labels, so 1 cup is 16 tablespoons),
temperature, speed, area, time, data, pressure, energy, fuel economy and
angle. Indonesian units where they are well defined: ons (100 g), kuintal
(100 kg), are (100 m²) and tumbak (14 m²).

Names as typed and as whisper writes them, in both languages, singular and
plural, with abbreviations and common misspellings ("sentimeter", "senti",
"celcius", "farenheit", "inchi"). Some mean two things, settled by the other
unit in the sentence:
  "kilo"                 kilograms, or kilometres next to a length
  "ounce", "oz"          mass, or fluid ounces next to a volume
  "derajat", "degrees"   a temperature (Celsius, or Fahrenheit when converting
                         to Celsius), or an angle next to radians
KB, MB, GB, TB and PB follow the user's setting (1024 per step, as Windows
counts, or 1000, as drive makers do); KiB, MiB, GiB and TiB are always 1024,
and bits (kilobit, megabit, "Mb" with a small b) always 1000.

A year is 365 days and a month a twelfth of it, so a year is 12 months.
"""

import collections
from fractions import Fraction

import calculator_numbers as numbers

Unit = collections.namedtuple("Unit", "id category factor id_name en_one en_many")

# Units whose size follows the 1000/1024 setting: (id, power).
CONVENTION_UNITS = {"kb": 1, "mb": 2, "gb": 3, "tb": 4, "pb": 5}

_F = Fraction

# (id, category, factor to the category's base unit or None, Indonesian name,
#  English singular, English plural, [what people type or say])
_TABLE = [
    # Length: metres
    ("mm", "length", _F(1, 1000), "milimeter", "millimeter", "millimeters",
     ["mm", "milimeter", "millimeter", "millimetre", "millimeters", "millimetres", "mili meter"]),
    ("cm", "length", _F(1, 100), "sentimeter", "centimeter", "centimeters",
     ["cm", "sentimeter", "centimeter", "centimetre", "centimeters", "centimetres", "senti",
      "senti meter", "centi meter", "sm"]),
    ("m", "length", _F(1), "meter", "meter", "meters",
     ["m", "meter", "metre", "meters", "metres", "mtr", "mter"]),
    ("km", "length", _F(1000), "kilometer", "kilometer", "kilometers",
     ["km", "kilometer", "kilometre", "kilometers", "kilometres", "kilo meter", "kilo meters",
      "kilo"]),
    ("inch", "length", _F(254, 10000), "inci", "inch", "inches",
     ["inci", "inchi", "inch", "inches", "incis", "inc", "\""]),
    ("foot", "length", _F(3048, 10000), "kaki", "foot", "feet",
     ["kaki", "foot", "feet", "ft", "feets", "'"]),
    ("yard", "length", _F(9144, 10000), "yard", "yard", "yards",
     ["yard", "yards", "yd", "yds", "yar"]),
    ("mile", "length", _F(1609344, 1000), "mil", "mile", "miles",
     ["mil", "mile", "miles", "mi", "mils"]),
    ("nmi", "length", _F(1852), "mil laut", "nautical mile", "nautical miles",
     ["mil laut", "nautical mile", "nautical miles", "nmi"]),
    ("ly", "length", _F(9460730472580800), "tahun cahaya", "light-year", "light-years",
     ["tahun cahaya", "light year", "light years", "lightyear", "lightyears"]),
    # Mass: kilograms
    ("mg", "mass", _F(1, 10 ** 6), "miligram", "milligram", "milligrams",
     ["mg", "miligram", "milligram", "milligrams", "milligramme"]),
    ("g", "mass", _F(1, 1000), "gram", "gram", "grams",
     ["g", "gr", "gram", "grams", "gramme", "grammes", "grm"]),
    ("ons", "mass", _F(1, 10), "ons", "ons (100 g)", "ons (100 g)",
     ["ons"]),
    ("kg", "mass", _F(1), "kilogram", "kilogram", "kilograms",
     ["kg", "kilogram", "kilograms", "kilogramme", "kilo", "kilos", "kilo gram", "kgs"]),
    ("kuintal", "mass", _F(100), "kuintal", "quintal", "quintals",
     ["kuintal", "kwintal", "quintal", "quintals"]),
    ("ton", "mass", _F(1000), "ton", "tonne", "tonnes",
     ["ton", "tons", "tonne", "tonnes"]),
    ("oz", "mass", _F(28349523125, 10 ** 12), "ounce", "ounce", "ounces",
     ["ounce", "ounces", "oz", "ons inggris"]),
    ("lb", "mass", _F(45359237, 10 ** 8), "pon", "pound", "pounds",
     ["pon", "pound", "pounds", "lb", "lbs", "paun"]),
    ("stone", "mass", _F(635029318, 10 ** 8), "stone", "stone", "stone",
     ["stone", "stones"]),
    # Volume: litres
    ("ml", "volume", _F(1, 1000), "mililiter", "milliliter", "milliliters",
     ["ml", "mililiter", "milliliter", "millilitre", "milliliters", "millilitres", "cc",
      "cm3", "cm³", "mili liter"]),
    ("l", "volume", _F(1), "liter", "liter", "liters",
     ["l", "liter", "litre", "liters", "litres", "ltr", "lt", "lter"]),
    ("m3", "volume", _F(1000), "meter kubik", "cubic meter", "cubic meters",
     ["m3", "m³", "meter kubik", "cubic meter", "cubic meters", "cubic metre", "cubic metres",
      "kubik"]),
    ("cup", "volume", _F(24, 100), "cangkir", "cup", "cups",
     ["cup", "cups", "cangkir", "cangkir takar", "gelas takar"]),
    ("tbsp", "volume", _F(15, 1000), "sendok makan", "tablespoon", "tablespoons",
     ["sendok makan", "sdm", "tablespoon", "tablespoons", "tbsp", "tbs", "sendok besar"]),
    ("tsp", "volume", _F(5, 1000), "sendok teh", "teaspoon", "teaspoons",
     ["sendok teh", "sdt", "teaspoon", "teaspoons", "tsp", "sendok kecil"]),
    ("floz", "volume", _F(295735295625, 10 ** 13), "ons cairan", "fluid ounce", "fluid ounces",
     ["fl oz", "floz", "fluid ounce", "fluid ounces", "ons cairan", "ounce cair"]),
    ("pint", "volume", _F(473176473, 10 ** 9), "pint", "pint", "pints",
     ["pint", "pints"]),
    ("quart", "volume", _F(946352946, 10 ** 9), "quart", "quart", "quarts",
     ["quart", "quarts", "qt"]),
    ("gallon", "volume", _F(3785411784, 10 ** 9), "galon AS", "US gallon", "US gallons",
     ["galon", "gallon", "gallons", "gal", "galon as", "galon amerika", "us gallon",
      "us gallons", "gallon as"]),
    ("impgallon", "volume", _F(454609, 10 ** 5), "galon Inggris", "imperial gallon",
     "imperial gallons",
     ["galon inggris", "imperial gallon", "imperial gallons", "uk gallon", "uk gallons"]),
    ("barrel", "volume", _F(158987294928, 10 ** 9), "barel", "barrel", "barrels",
     ["barel", "barrel", "barrels", "bbl"]),
    # Temperature: converted through kelvin (see _TEMPERATURE)
    ("celsius", "temperature", None, "derajat Celsius", "degree Celsius", "degrees Celsius",
     ["celsius", "celcius", "selsius", "selcius", "centigrade", "°c", "c", "derajat celsius",
      "derajat celcius", "derajat c", "degrees celsius", "degree celsius", "degrees c",
      "° celsius"]),
    ("fahrenheit", "temperature", None, "derajat Fahrenheit", "degree Fahrenheit",
     "degrees Fahrenheit",
     ["fahrenheit", "farenheit", "fahrenhait", "farenhait", "fahrenheid", "°f", "f",
      "derajat fahrenheit", "derajat farenheit", "derajat f", "degrees fahrenheit",
      "degree fahrenheit", "degrees f", "° fahrenheit"]),
    ("kelvin", "temperature", None, "kelvin", "kelvin", "kelvins",
     ["kelvin", "kelvins", "derajat kelvin", "degrees kelvin"]),
    ("reamur", "temperature", None, "derajat Réaumur", "degree Réaumur", "degrees Réaumur",
     ["reamur", "reaumur", "réaumur", "derajat reamur", "derajat reaumur", "degrees reaumur",
      "°r"]),
    # Speed: metres per second
    ("mps", "speed", _F(1), "meter per detik", "meter per second", "meters per second",
     ["m/s", "m / s", "meter per detik", "meter per second", "meters per second",
      "metre per second", "metres per second", "mps", "m per s"]),
    ("kmh", "speed", _F(1000, 3600), "kilometer per jam", "kilometer per hour",
     "kilometers per hour",
     ["km/jam", "km/j", "km/h", "kmh", "kph", "kmj", "km per jam", "kilometer per jam",
      "km per hour", "kilometer per hour", "kilometers per hour", "kilometre per hour",
      "kilometres per hour", "kilo per jam", "km perjam"]),
    ("mph", "speed", _F(1609344, 3600000), "mil per jam", "mile per hour", "miles per hour",
     ["mph", "mil per jam", "mile per hour", "miles per hour", "mi/h"]),
    ("knot", "speed", _F(1852, 3600), "knot", "knot", "knots",
     ["knot", "knots", "kn", "kt", "simpul"]),
    # Area: square metres
    ("cm2", "area", _F(1, 10000), "sentimeter persegi", "square centimeter",
     "square centimeters",
     ["cm2", "cm²", "sentimeter persegi", "centimeter persegi", "square centimeter",
      "square centimeters", "square centimetre", "square centimetres", "sq cm"]),
    ("m2", "area", _F(1), "meter persegi", "square meter", "square meters",
     ["m2", "m²", "meter persegi", "square meter", "square meters", "square metre",
      "square metres", "sq m", "sqm", "meter kuadrat", "mter persegi"]),
    ("km2", "area", _F(10 ** 6), "kilometer persegi", "square kilometer", "square kilometers",
     ["km2", "km²", "kilometer persegi", "square kilometer", "square kilometers",
      "square kilometre", "square kilometres", "sq km"]),
    ("ha", "area", _F(10000), "hektare", "hectare", "hectares",
     ["hektar", "hektare", "hectare", "hectares", "ha", "hektaran"]),
    ("are", "area", _F(100), "are", "are", "ares",
     ["are", "ares", "ar"]),
    ("acre", "area", _F(40468564224, 10 ** 7), "acre", "acre", "acres",
     ["acre", "acres", "ekar", "akre"]),
    ("sqft", "area", _F(9290304, 10 ** 8), "kaki persegi", "square foot", "square feet",
     ["sq ft", "sqft", "ft2", "ft²", "square foot", "square feet", "kaki persegi"]),
    ("sqmi", "area", _F(2589988110336, 10 ** 6), "mil persegi", "square mile", "square miles",
     ["square mile", "square miles", "mil persegi", "sq mi"]),
    ("tumbak", "area", _F(14), "tumbak", "tumbak", "tumbak",
     ["tumbak"]),
    # Time: seconds
    ("msec", "time", _F(1, 1000), "milidetik", "millisecond", "milliseconds",
     ["milidetik", "millisecond", "milliseconds", "ms", "mili detik"]),
    ("sec", "time", _F(1), "detik", "second", "seconds",
     ["detik", "second", "seconds", "sec", "secs", "dtk", "s"]),
    ("min", "time", _F(60), "menit", "minute", "minutes",
     ["menit", "minute", "minutes", "min", "mins", "mnt"]),
    ("hour", "time", _F(3600), "jam", "hour", "hours",
     ["jam", "hour", "hours", "hr", "hrs", "h"]),
    ("day", "time", _F(86400), "hari", "day", "days",
     ["hari", "day", "days"]),
    ("week", "time", _F(604800), "minggu", "week", "weeks",
     ["minggu", "pekan", "week", "weeks"]),
    ("month", "time", _F(31536000, 12), "bulan", "month", "months",
     ["bulan", "month", "months"]),
    ("year", "time", _F(31536000), "tahun", "year", "years",
     ["tahun", "year", "years", "yr", "yrs", "thn"]),
    ("decade", "time", _F(315360000), "dekade", "decade", "decades",
     ["dekade", "dasawarsa", "decade", "decades"]),
    ("century", "time", _F(3153600000), "abad", "century", "centuries",
     ["abad", "century", "centuries"]),
    # Data: bytes (KB..PB follow the setting)
    ("bit", "data", _F(1, 8), "bit", "bit", "bits", ["bit", "bits"]),
    ("byte", "data", _F(1), "byte", "byte", "bytes", ["byte", "bytes", "bita"]),
    ("kb", "data", None, "kilobyte", "kilobyte", "kilobytes",
     ["kb", "kilobyte", "kilobytes", "kilo byte", "kbyte"]),
    ("mb", "data", None, "megabyte", "megabyte", "megabytes",
     ["mb", "megabyte", "megabytes", "mega byte", "mega", "mbyte"]),
    ("gb", "data", None, "gigabyte", "gigabyte", "gigabytes",
     ["gb", "gigabyte", "gigabytes", "giga byte", "giga", "gbyte", "giga bite"]),
    ("tb", "data", None, "terabyte", "terabyte", "terabytes",
     ["tb", "terabyte", "terabytes", "tera byte", "tera"]),
    ("pb", "data", None, "petabyte", "petabyte", "petabytes",
     ["pb", "petabyte", "petabytes"]),
    ("kib", "data", _F(1024), "kibibyte", "kibibyte", "kibibytes",
     ["kib", "kibibyte", "kibibytes"]),
    ("mib", "data", _F(1024 ** 2), "mebibyte", "mebibyte", "mebibytes",
     ["mib", "mebibyte", "mebibytes"]),
    ("gib", "data", _F(1024 ** 3), "gibibyte", "gibibyte", "gibibytes",
     ["gib", "gibibyte", "gibibytes"]),
    ("tib", "data", _F(1024 ** 4), "tebibyte", "tebibyte", "tebibytes",
     ["tib", "tebibyte", "tebibytes"]),
    ("kbit", "data", _F(1000, 8), "kilobit", "kilobit", "kilobits",
     ["kilobit", "kilobits", "kbit"]),
    ("mbit", "data", _F(10 ** 6, 8), "megabit", "megabit", "megabits",
     ["megabit", "megabits", "mbit"]),
    ("gbit", "data", _F(10 ** 9, 8), "gigabit", "gigabit", "gigabits",
     ["gigabit", "gigabits", "gbit"]),
    # Pressure: pascals
    ("pa", "pressure", _F(1), "pascal", "pascal", "pascals", ["pa", "pascal", "pascals"]),
    ("kpa", "pressure", _F(1000), "kilopascal", "kilopascal", "kilopascals",
     ["kpa", "kilopascal", "kilopascals"]),
    ("hpa", "pressure", _F(100), "hektopascal", "hectopascal", "hectopascals",
     ["hpa", "hektopascal", "hectopascal", "hectopascals", "mbar", "milibar", "millibar",
      "millibars"]),
    ("bar", "pressure", _F(100000), "bar", "bar", "bars", ["bar", "bars"]),
    ("psi", "pressure", _F(6894757293168, 10 ** 9), "psi", "psi", "psi", ["psi"]),
    ("atm", "pressure", _F(101325), "atmosfer", "atmosphere", "atmospheres",
     ["atm", "atmosfer", "atmosfir", "atmosphere", "atmospheres"]),
    ("mmhg", "pressure", _F(133322387415, 10 ** 9), "milimeter air raksa",
     "millimeter of mercury", "millimeters of mercury",
     ["mmhg", "mm hg", "milimeter air raksa", "millimeter of mercury",
      "millimeters of mercury"]),
    # Energy: joules
    ("j", "energy", _F(1), "joule", "joule", "joules", ["j", "joule", "joules"]),
    ("kj", "energy", _F(1000), "kilojoule", "kilojoule", "kilojoules",
     ["kj", "kilojoule", "kilojoules", "kilo joule"]),
    ("cal", "energy", _F(4184, 1000), "kalori kecil", "small calorie", "small calories",
     ["kalori kecil", "small calorie", "small calories", "gram calorie", "gram calories"]),
    ("kcal", "energy", _F(4184), "kilokalori", "kilocalorie", "kilocalories",
     ["kkal", "kcal", "kilokalori", "kilocalorie", "kilocalories", "kalori", "calorie",
      "calories", "cal", "kal"]),
    ("wh", "energy", _F(3600), "watt-jam", "watt-hour", "watt-hours",
     ["wh", "watt jam", "watt hour", "watt hours"]),
    ("kwh", "energy", _F(3600000), "kilowatt-jam", "kilowatt-hour", "kilowatt-hours",
     ["kwh", "kilowatt jam", "kilowatt hour", "kilowatt hours", "kilowatt-hour",
      "kilowatt-hours"]),
    # Fuel economy: kilometres per litre (litres per 100 km is the inverse)
    ("kml", "fuel", _F(1), "kilometer per liter", "kilometer per liter", "kilometers per liter",
     ["km/l", "km/liter", "kmpl", "km per liter", "km per litre", "kilometer per liter",
      "kilometers per liter", "kilometre per litre", "kilometres per litre", "km/ltr"]),
    ("mpg", "fuel", _F(1609344000, 3785411784), "mil per galon", "mile per gallon",
     "miles per gallon",
     ["mpg", "mil per galon", "mile per gallon", "miles per gallon"]),
    ("l100", "fuel", None, "liter per 100 kilometer", "liter per 100 kilometers",
     "liters per 100 kilometers",
     ["l/100km", "l/100 km", "l per 100 km", "liter per 100 km", "liter per 100 kilometer",
      "litre per 100 km", "liters per 100 km", "litres per 100 km", "liter per seratus km",
      "liter per seratus kilometer", "liters per 100 kilometers"]),
    # Angle: degrees (only next to radians; a bare "derajat" is a temperature)
    ("deg", "angle", _F(1), "derajat", "degree", "degrees", []),
    ("rad", "angle", None, "radian", "radian", "radians", ["radian", "radians", "rad"]),
]

UNITS = {row[0]: Unit(*row[:6]) for row in _TABLE}
CATEGORIES = sorted({u.category for u in UNITS.values()})

# A bare degree: a temperature or an angle, settled by the other unit.
BARE_DEGREES = ["derajat", "degree", "degrees", "°", "deg"]
# Units written with a capital that changes their meaning: "Mb" is a megabit.
CASED = {"Kb": "kbit", "Mb": "mbit", "Gb": "gbit", "Mbit": "mbit", "Gbit": "gbit"}
# One word, two units: the first is taken unless the other fits the sentence.
AMBIGUOUS = {"kilo": ["kg", "km"], "ounce": ["oz", "floz"], "ounces": ["oz", "floz"],
             "oz": ["oz", "floz"], "c": ["celsius"], "f": ["fahrenheit"]}


def _key(text):
    return tuple(t.norm for t in numbers.tokenize(text))


def _index():
    index = {}
    for row in _TABLE:
        for alias in row[6]:
            key = _key(alias)
            ids = index.setdefault(key, [])
            if row[0] not in ids:
                ids.append(row[0])
    for word, ids in AMBIGUOUS.items():
        index[_key(word)] = list(ids)
    for word in BARE_DEGREES:
        index[_key(word)] = ["degrees"]
    return index


INDEX = _index()
LONGEST = max(len(k) for k in INDEX)


def unit_at(toks, i):
    """([unit ids], end) of the longest unit name at token i, or None.
    "degrees" stands for a bare degree (see pick())."""
    if i < len(toks) and toks[i].text in CASED:
        return [CASED[toks[i].text]], i + 1
    for length in range(min(LONGEST, len(toks) - i), 0, -1):
        key = tuple(t.norm for t in toks[i:i + length])
        ids = INDEX.get(key)
        if ids:
            return list(ids), i + length
    return None


def pick(sources, targets):
    """(src id, dst id) from the candidates of each side that share a
    category, or None. A bare degree becomes the other side's opposite
    temperature (to Celsius: from Fahrenheit, else from Celsius), or an
    angle next to radians."""
    sources, targets = list(sources), list(targets)
    for mine, other in ((sources, targets), (targets, sources)):
        if mine == ["degrees"]:
            other_units = [UNITS[o] for o in other if o in UNITS]
            if any(u.category == "angle" for u in other_units):
                mine[:] = ["deg"]
            elif other == ["degrees"]:
                return None
            elif any(u.id == "celsius" for u in other_units):
                mine[:] = ["fahrenheit"]
            else:
                mine[:] = ["celsius"]
    for s in sources:
        for t in targets:
            if s in UNITS and t in UNITS and UNITS[s].category == UNITS[t].category:
                return s, t
    return None


def category_of(ids):
    for uid in ids:
        if uid in UNITS:
            return UNITS[uid].category
    return None


def factor(uid, convention=1024):
    unit = UNITS[uid]
    if uid in CONVENTION_UNITS:
        return Fraction(convention) ** CONVENTION_UNITS[uid]
    if uid == "rad":
        return None
    return unit.factor


_KELVIN_OFFSET = Fraction(27315, 100)


def _to_kelvin(value, uid):
    if uid == "celsius":
        return value + _KELVIN_OFFSET
    if uid == "fahrenheit":
        return (value - 32) * Fraction(5, 9) + _KELVIN_OFFSET
    if uid == "reamur":
        return value * Fraction(5, 4) + _KELVIN_OFFSET
    return value


def _from_kelvin(value, uid):
    if uid == "celsius":
        return value - _KELVIN_OFFSET
    if uid == "fahrenheit":
        return (value - _KELVIN_OFFSET) * Fraction(9, 5) + 32
    if uid == "reamur":
        return (value - _KELVIN_OFFSET) * Fraction(4, 5)
    return value


class ConvertError(Exception):
    """kind: "below_zero" (under absolute zero), "div_zero" (0 L/100 km)."""

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


def to_base(value, uid, convention=1024):
    """The value in its category's base unit (for adding "5 kaki 11 inci")."""
    unit = UNITS[uid]
    if unit.category == "temperature":
        return _to_kelvin(value, uid)
    if uid == "l100":
        if value == 0:
            raise ConvertError("div_zero")
        return Fraction(100) / value
    if uid == "rad":
        import math
        return float(value) * 180.0 / math.pi
    return value * factor(uid, convention)


def from_base(value, uid, convention=1024):
    unit = UNITS[uid]
    if unit.category == "temperature":
        return _from_kelvin(value, uid)
    if uid == "l100":
        if value == 0:
            raise ConvertError("div_zero")
        return Fraction(100) / value
    if uid == "rad":
        import math
        return float(value) * math.pi / 180.0
    if isinstance(value, float):
        return value / float(factor(uid, convention))
    return value / factor(uid, convention)


def convert(value, src, dst, convention=1024):
    """`value` src in dst: exact where it can be. Raises ConvertError."""
    base = to_base(value, src, convention)
    if UNITS[src].category == "temperature" and base < 0:
        raise ConvertError("below_zero")
    return from_base(base, dst, convention)


def name(uid, language="en", value=None):
    """The unit's name to say after a number: Indonesian has one form,
    English the singular only for exactly one."""
    unit = UNITS[uid]
    if language == "id":
        return unit.id_name
    if value is not None and abs(value) == 1:
        return unit.en_one
    return unit.en_many


def notes(src, dst, convention=1024):
    """What to add after the answer so it can't be misunderstood: ["ons"]
    (the Indonesian ons is 100 g), ["kcal"] (calories are food calories),
    ["data_1024"] or ["data_1000"] (which KB, MB, GB), ["cup"], ["tumbak"],
    ["month"], ["year"]."""
    found = []
    ids = (src, dst)
    if src == dst:
        return found
    if "ons" in ids:
        found.append("ons")
    if "kcal" in ids and "cal" not in ids:
        found.append("kcal")
    if any(uid in CONVENTION_UNITS for uid in ids):
        found.append("data_1024" if convention == 1024 else "data_1000")
    if "cup" in ids:
        found.append("cup")
    if "tumbak" in ids:
        found.append("tumbak")
    small_time = {"msec", "sec", "min", "hour", "day", "week"}
    if "month" in ids and not set(ids) <= {"month", "year", "decade", "century"}:
        found.append("month")
    elif "year" in ids or "decade" in ids or "century" in ids:
        if any(uid in small_time for uid in ids):
            found.append("year")
    return found


# "kaki dan inci", "feet and inches", "jam dan menit": a target said as two
# units, the larger one in whole numbers.
PAIRS = {("foot", "inch"), ("hour", "min"), ("min", "sec"), ("lb", "oz"), ("m", "cm"),
         ("kg", "g"), ("day", "hour"), ("year", "month"), ("week", "day"), ("mile", "yard"),
         ("stone", "lb")}
