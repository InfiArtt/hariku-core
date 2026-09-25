# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What Calculator & Converter says, in the Hariku language (English or
Indonesian; unit and currency names for other languages are English). No wx
here.

Numbers are written the language's way ("1.250.000,5" in Indonesian,
"1,250,000.5" in English) and rounded as calculator_numbers.present() says;
a rounded answer says so ("kira-kira 33,33", "about 33.33"). A sum is said
back with its operators in words, so a misheard number is noticed: "25 kali
4 = 100.", "100 divided by 3 = about 33.33."
"""

import os
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from core.i18n import format_date, get_translator

import calculator_money as money
import calculator_numbers as numbers
import calculator_units as units

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("calculator", os.path.join(EXT_DIR, "locales"))

OP_KEYS = {"+": "op_plus", "-": "op_minus", "*": "op_times", "/": "op_divide", "^": "op_power",
           "mod": "op_mod"}
POSTFIX_KEYS = {"fact": "op_fact", "sq": "op_squared", "cube": "op_cubed", "of": "op_of"}
NOTE_KEYS = {"ons": "note_ons", "kcal": "note_kcal", "data_1024": "note_data_1024",
             "data_1000": "note_data_1000", "cup": "note_cup", "tumbak": "note_tumbak",
             "month": "note_month", "year": "note_year"}
ERROR_KEYS = {"syntax": "err_syntax", "div_zero": "err_div_zero", "too_big": "err_too_big",
              "negative_root": "err_negative_root", "complex": "err_complex",
              "factorial": "err_factorial", "no_result": "err_no_result",
              "below_zero": "err_below_zero", "offline": "err_offline",
              "unknown": "err_unknown_currency", "dice": "err_dice", "random": "err_random",
              "people": "err_people", "percent": "err_percent", "no_target": "hint_no_target"}


def cap(text):
    return text[:1].upper() + text[1:] if text else text


# ------------------------------------------------------------
# Numbers, quantities, money
# ------------------------------------------------------------

def number(value, language="en", decimals="auto"):
    """(text, approx): "33,33" / "33.33", or "7,26 kali 10 pangkat 306"."""
    shown = numbers.present(value, decimals)
    if shown.digits is not None:
        return numbers.format_decimal(shown.digits, language), shown.approx
    mantissa = numbers.format_decimal(shown.mantissa, language)
    return _("sci", mantissa=mantissa, exponent=shown.exponent), shown.approx


def _is_one(text):
    return text in ("1", "-1")


def quantity(value, uid, language="en", decimals="auto"):
    """(text, approx): "24 inci", "24 inches", "1 foot"."""
    text, approx = number(value, language, decimals)
    count = 1 if _is_one(text) and not approx else 2
    return f"{text} {units.name(uid, language, count)}", approx


def money_amount(value, code, language="en"):
    """(number text, approx) of an amount of money: whole rupiah, yen, won
    and dong, cents for the others ("12,50"), and a few significant digits
    below one ("0,0000558")."""
    places = money.decimals(code)
    d = numbers.to_decimal(value, 28)
    magnitude = abs(d)
    if magnitude >= numbers.SCI_ABOVE:
        return number(value, language)
    if 0 < magnitude < 1:
        places = max(places, -magnitude.adjusted() + 2)
    shown = d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if places and shown == shown.to_integral_value():
        text = numbers.format_decimal(shown, language)
    else:
        text = numbers.format_decimal(shown, language, keep_places=places)
    approx = Fraction(shown) != Fraction(value) \
        if not isinstance(value, float) else True
    return text, approx


def money_text(value, code, language="en"):
    text, _approx = money_amount(value, code, language)
    count = 1 if _is_one(text) else 2
    return f"{text} {money.name(code, language, count)}"


def date_text(day, language="en", today=None):
    """ "25 September" (with the year when it isn't this year's)."""
    month = format_date(day, "%B")
    text = f"{day.day} {month}"
    if today is not None and day.year != today.year:
        text += f" {day.year}"
    return text


def join_list(items):
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " " + _("and") + " " + items[-1]


# ------------------------------------------------------------
# A sum said back
# ------------------------------------------------------------

def expression(mtoks, language="en", last_text=""):
    """The sum in words: "25 kali 4", "(3 tambah 4) kali 2", "12% dari
    350", "akar 144", "7 factorial", "-3 times 2". `last_text` stands for the
    previous result ("24 inci")."""
    parts = []          # [text, glue to the previous part]
    previous = None
    glue_next = False
    for m in mtoks:
        glue = glue_next
        glue_next = False
        if m.kind == "num":
            text = number(m.value, language)[0]
        elif m.kind == "last":
            text = last_text or number(m.value, language)[0]
        elif m.kind == "op":
            unary = m.value in ("+", "-") and (previous is None or previous.kind in (
                "op", "lp", "func", "of"))
            if unary:
                text = "-" if m.value == "-" else "+"
                glue_next = True
            else:
                text = _(OP_KEYS[m.value])
        elif m.kind == "pct":
            text, glue = "%", True
        elif m.kind == "of" and previous is not None and previous.kind == "func":
            glue_next = glue            # "akar dari 144": the root's own words say it
            continue
        elif m.kind in POSTFIX_KEYS:
            text = _(POSTFIX_KEYS[m.kind])
        elif m.kind == "lp":
            text = "("
            glue_next = True
        elif m.kind == "rp":
            text, glue = ")", True
        elif m.kind == "func":
            if m.value == 2:
                text = _("op_sqrt")
            elif m.value == 3:
                text = _("op_cbrt")
            else:
                text = _("op_root", n=m.value)
        else:
            continue
        parts.append((text, glue))
        previous = m
    out = ""
    for text, glue in parts:
        out += text if (glue or not out) else " " + text
    return out


# ------------------------------------------------------------
# Answers
# ------------------------------------------------------------

def result(expr, value_text, approx):
    return cap(_("calc_about" if approx else "calc_result", expr=expr, value=value_text))


def conversion(src_text, dst_text, approx, note_ids=()):
    sentence = cap(_("convert_about" if approx else "convert_result", src=src_text,
                     dst=dst_text))
    return with_notes(sentence, note_ids)


def with_notes(sentence, note_ids):
    notes = [_(NOTE_KEYS[n]) for n in note_ids if n in NOTE_KEYS]
    return " ".join([sentence] + notes)


def error(kind, **fields):
    return _(ERROR_KEYS.get(kind, "err_syntax"), **fields)
