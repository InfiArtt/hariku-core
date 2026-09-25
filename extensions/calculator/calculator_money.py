# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Currencies for Calculator & Converter: their names and the day's rates. No
wx here.

    currency_at(toks, i)      -> (code, end) of a currency name or code, or None
    symbol_at(toks, i)        -> (code, end) of "$", "Rp", "€" before an amount
    name(code, language, n)   -> "dolar AS", "US dollars"
    RateBook(fetch, ...)      -> the rates, cached; fetch() runs on a worker thread
    fetch_rates()             -> the rates from Frankfurter (network)

The rates come from Frankfurter (frankfurter.dev), a free service without an
API key that publishes the reference rates of central banks: the European
Central Bank, Bank Indonesia and others, blended into one rate per currency
each working day. Hariku asks for all of them at once against the euro, so
nothing about what you convert is sent, and works out any pair from those.
They are kept for FRESH_HOURS; when the service can't be reached, rates up to
STALE_DAYS old are used, and the answer always says their date.
"""

import collections
import datetime
import json
import logging
import threading
from decimal import Decimal
from fractions import Fraction

import calculator_numbers as numbers

logger = logging.getLogger(__name__)

RATES_URL = "https://api.frankfurter.dev/v2/rates?base=EUR"
USER_AGENT = "Hariku (Calculator & Converter extension)"
TIMEOUT = 8                     # seconds
FRESH_HOURS = 6
STALE_DAYS = 7
MAX_BYTES = 512 * 1024

Currency = collections.namedtuple("Currency", "code id_name en_one en_many decimals names")

# (code, Indonesian name, English singular, plural, decimals said, names people use)
_TABLE = [
    ("IDR", "rupiah", "rupiah", "rupiah", 0, ["rupiah", "rupiahs", "idr", "rp"]),
    ("USD", "dolar AS", "US dollar", "US dollars", 2,
     ["dolar", "dollar", "dollars", "usd", "dolar as", "dolar amerika", "dollar amerika",
      "us dollar", "us dollars", "american dollar", "american dollars", "dolar amerika serikat",
      "buck", "bucks", "dolar us"]),
    ("EUR", "euro", "euro", "euros", 2, ["euro", "euros", "eur"]),
    ("JPY", "yen", "yen", "yen", 0, ["yen", "jpy", "yen jepang", "japanese yen"]),
    ("SGD", "dolar Singapura", "Singapore dollar", "Singapore dollars", 2,
     ["dolar singapura", "dollar singapura", "dolar singapore", "sgd", "singapore dollar",
      "singapore dollars"]),
    ("MYR", "ringgit", "ringgit", "ringgit", 2,
     ["ringgit", "myr", "ringgit malaysia", "malaysian ringgit"]),
    ("AUD", "dolar Australia", "Australian dollar", "Australian dollars", 2,
     ["dolar australia", "dollar australia", "aud", "australian dollar", "australian dollars"]),
    ("GBP", "pound sterling", "British pound", "British pounds", 2,
     ["pound sterling", "poundsterling", "gbp", "pound inggris", "british pound",
      "british pounds", "sterling", "pounds sterling"]),
    ("CNY", "yuan", "yuan", "yuan", 2, ["yuan", "renminbi", "rmb", "cny", "yuan china"]),
    ("KRW", "won", "won", "won", 0, ["won", "krw", "won korea", "korean won"]),
    ("THB", "baht", "baht", "baht", 2, ["baht", "thb", "baht thailand", "thai baht"]),
    ("SAR", "riyal Saudi", "Saudi riyal", "Saudi riyals", 2,
     ["riyal", "riyals", "rial", "riyal saudi", "rial saudi", "real saudi", "sar",
      "saudi riyal", "saudi riyals"]),
    ("AED", "dirham", "UAE dirham", "UAE dirhams", 2, ["dirham", "dirhams", "aed", "dirham uea"]),
    ("QAR", "riyal Qatar", "Qatari riyal", "Qatari riyals", 2,
     ["riyal qatar", "qar", "qatari riyal", "qatari riyals"]),
    ("KWD", "dinar Kuwait", "Kuwaiti dinar", "Kuwaiti dinars", 2,
     ["dinar kuwait", "kwd", "kuwaiti dinar", "kuwaiti dinars", "dinar"]),
    ("INR", "rupee India", "Indian rupee", "Indian rupees", 2,
     ["rupee", "rupees", "rupe", "inr", "rupee india", "indian rupee", "indian rupees"]),
    ("HKD", "dolar Hong Kong", "Hong Kong dollar", "Hong Kong dollars", 2,
     ["dolar hong kong", "hkd", "hong kong dollar", "hong kong dollars"]),
    ("TWD", "dolar Taiwan", "Taiwan dollar", "Taiwan dollars", 2,
     ["dolar taiwan", "twd", "taiwan dollar", "taiwan dollars", "new taiwan dollar"]),
    ("PHP", "peso Filipina", "Philippine peso", "Philippine pesos", 2,
     ["peso", "pesos", "php", "peso filipina", "philippine peso", "philippine pesos"]),
    ("VND", "dong", "Vietnamese dong", "Vietnamese dong", 0,
     ["dong", "vnd", "dong vietnam", "vietnamese dong"]),
    ("CHF", "franc Swiss", "Swiss franc", "Swiss francs", 2,
     ["franc", "francs", "chf", "franc swiss", "swiss franc", "swiss francs"]),
    ("CAD", "dolar Kanada", "Canadian dollar", "Canadian dollars", 2,
     ["dolar kanada", "dollar kanada", "cad", "canadian dollar", "canadian dollars"]),
    ("NZD", "dolar Selandia Baru", "New Zealand dollar", "New Zealand dollars", 2,
     ["dolar selandia baru", "nzd", "new zealand dollar", "new zealand dollars"]),
    ("BND", "dolar Brunei", "Brunei dollar", "Brunei dollars", 2,
     ["dolar brunei", "bnd", "brunei dollar", "brunei dollars"]),
    ("TRY", "lira Turki", "Turkish lira", "Turkish lira", 2,
     ["lira", "lira turki", "turkish lira"]),
    ("RUB", "rubel", "Russian ruble", "Russian rubles", 2,
     ["rubel", "ruble", "rubles", "rouble", "roubles", "rub"]),
    ("EGP", "pound Mesir", "Egyptian pound", "Egyptian pounds", 2,
     ["pound mesir", "egp", "egyptian pound", "egyptian pounds"]),
    ("BRL", "real Brasil", "Brazilian real", "Brazilian reais", 2,
     ["real brasil", "brl", "brazilian real", "brazilian reais"]),
    ("MXN", "peso Meksiko", "Mexican peso", "Mexican pesos", 2,
     ["peso meksiko", "mxn", "mexican peso", "mexican pesos"]),
    ("ZAR", "rand", "South African rand", "South African rand", 2,
     ["rand", "zar", "south african rand"]),
    ("SEK", "krona Swedia", "Swedish krona", "Swedish kronor", 2,
     ["krona swedia", "sek", "swedish krona", "swedish kronor"]),
    ("NOK", "krone Norwegia", "Norwegian krone", "Norwegian kroner", 2,
     ["krone norwegia", "nok", "norwegian krone", "norwegian kroner"]),
    ("DKK", "krone Denmark", "Danish krone", "Danish kroner", 2,
     ["krone denmark", "dkk", "danish krone", "danish kroner"]),
    ("PKR", "rupee Pakistan", "Pakistani rupee", "Pakistani rupees", 2,
     ["rupee pakistan", "pkr", "pakistani rupee", "pakistani rupees"]),
    ("BDT", "taka", "Bangladeshi taka", "Bangladeshi taka", 2, ["taka", "bdt"]),
]
CURRENCIES = {row[0]: Currency(*row) for row in _TABLE}
# "pound" alone is a pound sterling next to another currency, else a pound in weight.
AMBIGUOUS_WITH_UNITS = {"pound": "GBP", "pounds": "GBP", "pon": "GBP"}
# Symbols written before an amount ("$100", "Rp 50.000").
SYMBOLS = {"$": "USD", "us$": "USD", "rp": "IDR", "€": "EUR", "£": "GBP", "¥": "JPY",
           "rm": "MYR", "s$": "SGD", "₩": "KRW", "฿": "THB", "₹": "INR", "₱": "PHP", "₫": "VND"}
# Other ISO codes the rates have, understood when typed in capitals ("100 NOK").
MORE_CODES = frozenset("""AFN ALL AMD ANG AOA ARS AWG AZN BAM BBD BGN BHD BIF BMD BOB BSD BTN BWP
BYN BZD CDF CLP COP CRC CUP CVE CZK DJF DOP DZD ERN ETB FJD FKP GEL GHS GIP GMD GNF GTQ GYD HNL
HTG HUF ILS IQD IRR ISK JMD JOD KES KGS KHR KMF KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD
MMK MNT MOP MRU MUR MVR MWK MZN NAD NGN NIO NPR OMR PAB PEN PGK PLN PYG RON RSD RWF SBD SCR SDG
SHP SLE SOS SRD SSP STN SVC SYP SZL TJS TMT TND TOP TTD TZS UAH UGX UYU UZS VES VUV WST XAF XCD
XOF XPF YER ZMW""".split())


def _index():
    index = {}
    for row in _TABLE:
        for alias in row[5]:
            key = tuple(t.norm for t in numbers.tokenize(alias))
            index.setdefault(key, row[0])
    return index


INDEX = _index()
LONGEST = max(len(k) for k in INDEX)


def currency_at(toks, i, with_pound=False):
    """(code, end) of the longest currency name at token i, or None. "pound"
    counts only with `with_pound` (the other side is a currency)."""
    if i >= len(toks):
        return None
    tok = toks[i]
    if tok.kind == "word" and len(tok.text) == 3 and tok.text.isupper() and tok.text in MORE_CODES:
        return tok.text, i + 1
    for length in range(min(LONGEST, len(toks) - i), 0, -1):
        key = tuple(t.norm for t in toks[i:i + length])
        code = INDEX.get(key)
        if code:
            return code, i + length
    if with_pound and tok.norm in AMBIGUOUS_WITH_UNITS:
        return AMBIGUOUS_WITH_UNITS[tok.norm], i + 1
    return None


def symbol_at(toks, i):
    """(code, end) of a currency symbol written before an amount: "$",
    "Rp", "€", "RM", "US$" ("Rp" also as "Rp." ), or None."""
    if i >= len(toks):
        return None
    t = toks[i].norm
    if t in ("us", "s") and i + 1 < len(toks) and toks[i + 1].norm == "$" and toks[i + 1].glued:
        return SYMBOLS[t + "$"], i + 2
    if t in SYMBOLS:
        end = i + 1
        if t in ("rp", "rm") and end < len(toks) and toks[end].norm == "." and toks[end].glued:
            end += 1                                  # "Rp."
        return SYMBOLS[t], end
    return None


def name(code, language="en", value=None):
    currency = CURRENCIES.get(code)
    if currency is None:
        return code
    if language == "id":
        return currency.id_name
    if value is not None and abs(value) == 1:
        return currency.en_one
    return currency.en_many


def decimals(code):
    currency = CURRENCIES.get(code)
    return currency.decimals if currency else 2


def known(code):
    return code in CURRENCIES or code in MORE_CODES


# ------------------------------------------------------------
# Rates
# ------------------------------------------------------------

class RateError(Exception):
    """The rates couldn't be had: `kind` "offline" or "unknown" (a currency
    the service has no rate for)."""

    def __init__(self, kind, code=""):
        super().__init__(kind)
        self.kind = kind
        self.code = code


class Rates:
    """One set of rates: `rates` {code: units per euro (Fraction)}, `dates`
    {code: date of that rate}, `fetched` (when they were fetched)."""

    def __init__(self, rates, dates, fetched):
        self.rates = dict(rates)
        self.rates["EUR"] = Fraction(1)
        self.dates = dict(dates)
        self.fetched = fetched
        if "EUR" not in self.dates and self.dates:
            self.dates["EUR"] = max(self.dates.values())

    def has(self, code):
        return code in self.rates

    def convert(self, amount, src, dst):
        """(value, date of the rates used) for amount src in dst."""
        for code in (src, dst):
            if code not in self.rates or not self.rates[code]:
                raise RateError("unknown", code)
        value = Fraction(amount) / self.rates[src] * self.rates[dst]
        dates = [self.dates.get(src), self.dates.get(dst)]
        dates = [d for d in dates if d is not None]
        return value, (min(dates) if dates else None)

    def to_json(self):
        return {"fetched": self.fetched.isoformat(timespec="seconds"),
                "rates": {code: [str(Decimal(rate.numerator) / Decimal(rate.denominator)),
                                 self.dates[code].isoformat() if code in self.dates else ""]
                          for code, rate in self.rates.items() if code != "EUR"}}

    @classmethod
    def from_json(cls, data):
        try:
            fetched = datetime.datetime.fromisoformat(data["fetched"])
            rates, dates = {}, {}
            for code, (rate, day) in data["rates"].items():
                if not (isinstance(code, str) and len(code) == 3 and code.isalpha()):
                    continue
                value = Fraction(Decimal(str(rate)))
                if value <= 0:
                    continue
                rates[code.upper()] = value
                if day:
                    dates[code.upper()] = datetime.date.fromisoformat(day)
            return cls(rates, dates, fetched) if rates else None
        except (KeyError, TypeError, ValueError, ArithmeticError):
            return None


def parse_rates(payload, fetched):
    """Rates from Frankfurter's answer: a list of {"date", "base", "quote",
    "rate"} against the euro. The newest row of each currency counts."""
    if not isinstance(payload, list):
        raise ValueError("unexpected answer")
    rates, dates = {}, {}
    for row in payload:
        if not isinstance(row, dict) or row.get("base") != "EUR":
            continue
        code, rate, day = row.get("quote"), row.get("rate"), row.get("date")
        if not (isinstance(code, str) and len(code) == 3 and code.isalpha()):
            continue
        try:
            value = Fraction(Decimal(str(rate)))
            when = datetime.date.fromisoformat(str(day))
        except (ValueError, ArithmeticError):
            continue
        if value <= 0:
            continue
        code = code.upper()
        if code not in dates or when >= dates[code]:
            rates[code], dates[code] = value, when
    if not rates:
        raise ValueError("no rates")
    return Rates(rates, dates, fetched)


def fetch_rates(now=None, urlopen=None):
    """The day's rates from Frankfurter (network, on a worker thread only).
    Only the address above is requested: no currency and nothing about the
    user is sent. Raises RateError("offline") on any failure."""
    import urllib.request
    opener = urlopen or urllib.request.urlopen
    request = urllib.request.Request(RATES_URL, headers={"User-Agent": USER_AGENT,
                                                         "Accept": "application/json"})
    try:
        with opener(request, timeout=TIMEOUT) as response:
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("answer too large")
        return parse_rates(json.loads(body.decode("utf-8")), now or datetime.datetime.now())
    except RateError:
        raise
    except Exception as e:
        logger.info(f"[Calculator] Rates not fetched: {e}")
        raise RateError("offline")


class RateBook:
    """The rates the extension has: fresh ones from memory or the saved
    copy, else fetched. `fetch()` returns Rates (or raises RateError);
    `load()` and `save(dict)` keep a copy between runs; `now()` is the clock."""

    def __init__(self, fetch=None, load=None, save=None, now=None):
        self._fetch = fetch or fetch_rates
        self._load = load
        self._save = save
        self._now = now or datetime.datetime.now
        self._rates = None
        self._loaded = False
        self._lock = threading.Lock()

    def _stored(self):
        if not self._loaded:
            self._loaded = True
            if self._load is not None:
                try:
                    data = self._load()
                    if data:
                        self._rates = Rates.from_json(data)
                except Exception:
                    logger.exception("[Calculator] Reading the saved rates failed")
        return self._rates

    def fresh(self):
        """Rates fetched within FRESH_HOURS, or None: no network."""
        with self._lock:
            rates = self._stored()
        if rates is None:
            return None
        age = self._now() - rates.fetched
        return rates if datetime.timedelta(0) <= age <= datetime.timedelta(hours=FRESH_HOURS) \
            else None

    def usable(self):
        """Rates up to STALE_DAYS old (for when the service can't be reached)."""
        with self._lock:
            rates = self._stored()
        if rates is None:
            return None
        age = self._now() - rates.fetched
        return rates if age <= datetime.timedelta(days=STALE_DAYS) else None

    def refresh(self):
        """Fetch now (worker thread). Returns fresh Rates, or older usable
        ones when the service can't be reached; raises RateError("offline")
        when there are none."""
        try:
            rates = self._fetch()
        except RateError:
            rates = None
        except Exception:
            logger.exception("[Calculator] Fetching rates failed")
            rates = None
        if rates is None:
            older = self.usable()
            if older is None:
                raise RateError("offline")
            return older
        with self._lock:
            self._rates = rates
            self._loaded = True
        if self._save is not None:
            try:
                self._save(rates.to_json())
            except Exception:
                logger.exception("[Calculator] Saving the rates failed")
        return rates
