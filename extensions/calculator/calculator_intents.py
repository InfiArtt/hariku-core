# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What Calculator & Converter answers in Aruna. No wx here.

Aruna finds it (core.commands.add_intent) through:
  * a matcher (core 2.11), which reads every sentence no other extension's
    pattern took: "25 x 4", "2 foot in inches", "5 km ke mil", "100 dolar ke
    rupiah", "berapa 25 kali 4", "tambah 5". It takes only what
    calculator_parse.read() is sure of, or understood after a lead word of
    ours, so other commands keep their sentences;
  * on older cores (2.9, 2.10), PATTERNS instead: sentences that start or end
    with a word of ours ("berapa {text}", "hitung {text}", "{text} berapa",
    "what's {text}", "convert {text}", "lempar {text}"...).

Either way the handler reads the whole sentence again and returns None when it
isn't a sum or a conversion after all (Aruna then goes on as before), a
sentence, or Reply(wait=True) while the day's exchange rates are fetched.

The last result is kept for FOLLOW_UP_SECONDS: "tambah 5", "kali dua",
"hasilnya dibagi 3", "times two" work on it, "berapa hasilnya" says it again
and "salin hasilnya" copies it.
"""

import random
import time
from decimal import Decimal
from fractions import Fraction

from core.commands import Reply

import calculator_money as money
import calculator_numbers as numbers
import calculator_parse as parse
import calculator_text as text
import calculator_units as units
from calculator_text import _

FOLLOW_UP_SECONDS = 300
PAIR_DECIMALS = 1           # "5 kaki 6,9 inci"
DECIMAL_CHOICES = ("auto", 0, 1, 2, 3, 4, 5, 6)
HOME_CHOICES = ("auto", "IDR", "USD", "EUR", "SGD", "MYR", "JPY", "SAR", "AUD", "GBP", "CNY",
                "KRW", "THB", "HKD", "TWD", "INR", "AED", "PHP", "VND", "CHF", "CAD", "NZD")
DEFAULT_SETTINGS = {"home": "auto", "decimals": "auto", "data": 1024, "auto_copy": False}

# Only for cores without a matcher (2.9, 2.10). Their fixed words also become
# Voice Control's vocabulary, where short words push out other commands' names
# (its prompt is 400 characters, shortest phrases first), so the list is kept
# to the most useful lead words. With a matcher (core 2.11) there are none:
# every sentence is read by calculator_parse.read(), lead words and all.
PATTERNS = [
    "berapa {text}", "{text} berapa", "hitung {text}", "what is {text}", "what's {text}",
    "how much {text}", "how many {text}", "calculate {text}", "convert {text}",
    "konversi {text}", "square root of {text}", "{text} faktorial", "{text} factorial",
    "sisa bagi {text}", "hasilnya {text}", "the result {text}", "lempar {text}",
    "angka acak {text}", "random number {text}", "bagi tagihan {text}",
]

# Actions (no content), with the other ways people say them.
ACTIONS = ("copy_result", "last_result", "random_number", "flip_coin", "roll_die")
ALIASES = {
    "copy_result": ["salin hasilnya", "salin hasil", "salin hasil terakhir", "salin jawabannya",
                    "copy the result", "copy result", "copy the answer", "copy that result"],
    "last_result": ["hasil terakhir", "hasil kalkulator", "last result", "the last result",
                    "what was the result", "calculator result"],
    "random_number": ["angka acak", "angka random", "bilangan acak", "random number",
                      "pick a number", "pick a random number", "pilih angka acak"],
    "flip_coin": ["lempar koin", "lempar uang logam", "flip a coin", "toss a coin",
                  "heads or tails"],
    "roll_die": ["lempar dadu", "kocok dadu", "roll a die", "roll the dice", "roll a dice",
                 "throw a die"],
}


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = dict(DEFAULT_SETTINGS)
    home = raw.get("home")
    if home == "auto" or (isinstance(home, str) and len(home) == 3 and money.known(home)):
        settings["home"] = home
    decimals = raw.get("decimals")
    if decimals in DECIMAL_CHOICES and not isinstance(decimals, bool):
        settings["decimals"] = decimals
    if raw.get("data") in (1000, 1024):
        settings["data"] = raw["data"]
    if isinstance(raw.get("auto_copy"), bool):
        settings["auto_copy"] = raw["auto_copy"]
    return settings


class _Kept:
    """The last result: its value (and unit or currency), how it was said
    ("24 inci") and the number to copy ("24")."""

    def __init__(self, value, unit, currency, said, digits, at):
        self.value = value
        self.unit = unit
        self.currency = currency
        self.said = said
        self.digits = digits
        self.at = at


class Calculator:
    """The answers. Everything outside is passed in: `language()` (the
    Hariku language), `copy(text)` (the clipboard), `speak(text)` (for an
    answer that comes later), `run_thread(work, done)` (work on a worker
    thread, done(result) on the UI thread), `rates` (a RateBook), `clock()`
    (seconds, for how old the last result is), `rng` (a random.Random)."""

    def __init__(self, settings=None, rates=None, language=None, copy=None, speak=None,
                 run_thread=None, clock=None, rng=None, today=None):
        self.settings = normalize_settings(settings)
        self.rates = rates or money.RateBook()
        self._language = language or (lambda: "en")
        self._copy = copy or (lambda value: None)
        self._speak = speak or (lambda value: None)
        self._run_thread = run_thread
        self._clock = clock or time.monotonic
        self.rng = rng or random.Random()
        self._today = today
        self.kept = None

    # --- small helpers ----------------------------------------------------------------------

    def language(self):
        code = str(self._language() or "en").split("-")[0].lower()
        return code

    def home(self):
        home = self.settings["home"]
        if home == "auto":
            return "IDR" if self.language() == "id" else "USD"
        return home

    def decimals(self):
        return self.settings["decimals"]

    def last(self):
        """The kept result while it is recent enough, else None."""
        if self.kept is None:
            return None
        if self._clock() - self.kept.at > FOLLOW_UP_SECONDS:
            self.kept = None
            return None
        return self.kept

    def context(self):
        kept = self.last()
        last = parse.Last(kept.value, kept.unit, kept.currency) if kept else None
        return parse.context(self.language(), last, self.settings["data"], self.home())

    def _keep(self, value, unit=None, currency=None, said="", digits=""):
        self.kept = _Kept(value, unit, currency, said, digits, self._clock())
        if self.settings["auto_copy"] and digits:
            try:
                self._copy(digits)
            except Exception:
                pass

    # --- Aruna --------------------------------------------------------------------------------

    def matcher(self, sentence):
        """For core.commands' matcher (core 2.11): the sentence when it is
        clearly ours: a sum or conversion without any lead word ("25 x 4",
        "5 km ke mil"), or anything read() understood after a lead word of
        ours ("berapa 5 km", "berapa hasilnya"). Else None."""
        try:
            query = parse.read(sentence, self.context())
        except Exception:
            return None
        if query is None or not (query.sure or query.get("lead")):
            return None
        return sentence

    def on_request(self, request):
        query = parse.read(request.full_text, self.context())
        if query is None and request.text != request.full_text:
            query = parse.read(request.text, self.context())
        if query is None:
            return None
        return self.answer(query)

    def answer(self, query):
        handler = getattr(self, "_answer_" + query.kind, None)
        if handler is None:
            return None
        return handler(query)

    # --- answers ------------------------------------------------------------------------------

    def _answer_error(self, query):
        return text.error(query.error)

    def _answer_hint(self, query):
        return text.error(query.what)

    def _answer_calc(self, query):
        language = self.language()
        kept = self.last() if query.get("followup") else None
        unit = currency = None
        if kept is not None and self._linear(query.mtoks):
            unit, currency = kept.unit, kept.currency
        expr = text.expression(query.mtoks, language, kept.said if kept else "")
        return self._say_value(query.value, unit, currency,
                               lambda value_text, approx: text.result(expr, value_text, approx))

    @staticmethod
    def _linear(mtoks):
        """Whether a result keeps the unit of the last one: only +, -, *, /
        and % with it used once ("24 inci kali 2" is 48 inci)."""
        if sum(1 for m in mtoks if m.kind == "last") != 1:
            return False
        return all(m.kind in ("num", "last", "pct", "lp", "rp") or
                   (m.kind == "op" and m.value in ("+", "-", "*", "/")) for m in mtoks)

    def _say_value(self, value, unit, currency, frame):
        """Say value (with its unit or currency) through frame(value_text,
        approx), keep it as the last result, copy it if the user wants."""
        language = self.language()
        if currency:
            # Money is said to the cent (or the rupiah), without "about".
            digits, _approx = text.money_amount(value, currency, language)
            said, approx = text.money_text(value, currency, language), False
        elif unit:
            digits, approx = text.number(value, language, self.decimals())
            said, approx = text.quantity(value, unit, language, self.decimals())
        else:
            digits, approx = text.number(value, language, self.decimals())
            said = digits
        self._keep(value, unit, currency, said, digits)
        return frame(said, approx)

    def _answer_convert(self, query):
        language = self.language()
        convention = self.settings["data"]
        try:
            if query.get("in_base"):
                value = units.from_base(query.amount, query.dst, convention)
            else:
                value = units.convert(query.amount, query.src, query.dst, convention)
        except units.ConvertError as e:
            return text.error(e.kind)
        if query.get("parts"):
            src_text = " ".join(text.quantity(v, units.pick(side.units, [query.src])[0],
                                              language)[0] for v, side in query.parts)
        else:
            src_text = text.quantity(query.amount, query.src, language)[0]
        notes = units.notes(query.src, query.dst, convention)
        if query.get("pair"):
            said, approx, value_small = self._pair(value, query.dst, query.pair)
            self._keep(value, query.dst, None, text.quantity(value, query.dst, language,
                                                             self.decimals())[0],
                       text.number(value, language, self.decimals())[0])
            return text.conversion(src_text, said, approx, notes)
        return self._say_value(value, query.dst, None,
                               lambda said, approx: text.conversion(src_text, said, approx, notes))

    def _pair(self, value, big, small):
        """ "5 kaki 6,9 inci": the whole number of the big unit and the rest
        in the small one, with one decimal at most (or the decimals the user
        chose); a rest that rounds up to a whole big unit is carried (never
        "5 kaki 12 inci"), one that rounds to 0 is left out."""
        language = self.language()
        places = PAIR_DECIMALS if self.decimals() == "auto" else self.decimals()
        magnitude = abs(Fraction(value))
        whole = int(magnitude)
        rest = units.convert(magnitude - whole, big, small)
        rounded = Fraction(numbers.present(rest, places).digits or 0)
        if rounded >= units.convert(Fraction(1), big, small):
            whole, rounded = whole + 1, Fraction(0)
        said = text.quantity(whole, big, language)[0]
        if rounded:
            said += " " + text.quantity(rounded, small, language, places)[0]
        if value < 0:
            said = "-" + said
        return said, whole + units.convert(rounded, small, big) != magnitude, rest

    def _answer_money(self, query):
        rates = self.rates.fresh()
        if rates is not None:
            return self._money_sentence(query, rates)
        if self._run_thread is None:
            return text.error("offline")

        def work():
            try:
                return self.rates.refresh()
            except money.RateError:
                return None

        def done(rates):
            sentence = self._money_sentence(query, rates) if rates is not None \
                else text.error("offline")
            self._speak(sentence)

        self._run_thread(work, done)
        return Reply(wait=True)

    def _money_sentence(self, query, rates):
        language = self.language()
        try:
            value, day = rates.convert(query.amount, query.src, query.dst)
        except money.RateError as e:
            return text.error("unknown", code=e.code)
        src_text = text.money_text(query.amount, query.src, language)
        today = self._today() if self._today else None
        date = text.date_text(day, language, today) if day else ""
        return self._say_value(value, None, query.dst,
                               lambda said, approx: _("money_result", src=src_text, dst=said,
                                                      date=date))

    def _answer_percent_of(self, query):
        if query.whole == 0:
            return text.error("div_zero")
        language = self.language()
        value = Fraction(query.part) / Fraction(query.whole) * 100
        part = text.number(query.part, language)[0]
        whole = text.number(query.whole, language)[0]
        digits, approx = text.number(value, language, self.decimals())
        self._keep(value, None, None, digits + "%", digits)
        key = "percent_of_about" if approx else "percent_of_result"
        return _(key, part=part, whole=whole, value=digits)

    def _answer_say_last(self, query):
        kept = self.last()
        if kept is None:
            return text.error("no_result")
        return _("say_last", value=kept.said)

    def _answer_coin(self, query):
        side = self.rng.choice(("coin_heads", "coin_tails"))
        return _("coin_result", side=_(side))

    def _answer_dice(self, query):
        rolls = [self.rng.randint(1, query.sides) for _i in range(query.count)]
        if query.count == 1:
            return _("dice_one", value=rolls[0])
        return _("dice_many", count=query.count, values=text.join_list(rolls), total=sum(rolls))

    def _answer_random(self, query):
        value = self.rng.randint(query.low, query.high)
        language = self.language()
        digits = numbers.format_decimal(Decimal(value), language)
        self._keep(Fraction(value), None, None, digits, digits)
        return _("random_result", low=numbers.format_decimal(Decimal(query.low), language),
                 high=numbers.format_decimal(Decimal(query.high), language), value=digits)

    def _amount_text(self, value, currency):
        language = self.language()
        if currency:
            return text.money_text(value, currency, language)
        return text.number(value, language, 2 if self.decimals() == "auto" else self.decimals())[0]

    def _answer_split(self, query):
        amount = Fraction(query.amount)
        total = amount * (1 + Fraction(query.tip) / 100)
        each = total / query.people
        each_text = self._amount_text(each, query.currency)
        digits = text.money_amount(each, query.currency, self.language())[0] if query.currency \
            else text.number(each, self.language(), 2)[0]
        self._keep(each, None, query.currency, each_text, digits)
        if query.tip:
            tip = text.number(query.tip, self.language())[0]
            return _("split_tip", tip=tip, total=self._amount_text(total, query.currency),
                     each=each_text, people=query.people)
        return _("split_result", each=each_text, people=query.people)

    def _answer_discount(self, query):
        amount = Fraction(query.amount)
        percent = Fraction(query.percent)
        price = amount * (1 - percent / 100)
        saved = amount - price
        language = self.language()
        price_text = self._amount_text(price, query.currency)
        digits = text.money_amount(price, query.currency, language)[0] if query.currency \
            else text.number(price, language, 2)[0]
        self._keep(price, None, query.currency, price_text, digits)
        return _("discount_result", percent=text.number(percent, language)[0], price=price_text,
                 saved=self._amount_text(saved, query.currency))

    # --- actions ------------------------------------------------------------------------------

    def copy_result(self):
        kept = self.last()
        if kept is None:
            return _("err_nothing_to_copy")
        try:
            self._copy(kept.digits)
        except Exception:
            return _("err_copy_failed")
        return _("copied", value=kept.digits)

    def last_result(self):
        return self._answer_say_last(None)

    def random_number(self):
        return self._answer_random(parse.Query("random", low=1, high=100))

    def flip_coin(self):
        return self._answer_coin(None)

    def roll_die(self):
        return self._answer_dice(parse.Query("dice", count=1, sides=6))
