# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Calculator & Converter (Kalkulator & Konversi) — Hariku V2 extension (needs
core 2.9: commands with content; core 2.11 adds sentences with no lead word).

Ask Aruna, typed or spoken, in Indonesian or English:
  "berapa 25 kali 4", "25 x 4", "12 persen dari 350", "akar 144",
  "(3 + 4) * 2", "sisa bagi 17 dan 5", "what's 15% of 80", "7 factorial"
  "tambah 5", "kali dua", "hasilnya dibagi 3", "salin hasilnya"
  "2 kaki berapa inci", "2 feet in inches", "100 fahrenheit ke celsius",
  "1 GB berapa MB", "3 jam berapa menit", "1 hektar berapa meter persegi"
  "100 dolar berapa rupiah", "50 euro ke yen", "kurs dolar"
  "lempar koin", "lempar 2 dadu", "angka acak 1 sampai 100",
  "bagi tagihan 350 ribu untuk 4 orang", "diskon 30% dari 250 ribu"

  calculator_numbers.py  numbers in digits and words, and how they are said
  calculator_math.py     the arithmetic (a parser of its own, never eval)
  calculator_units.py    units of measure
  calculator_money.py    currencies and the day's exchange rates
  calculator_parse.py    reading a sentence
  calculator_text.py     sentences in the user's language
  calculator_intents.py  what Aruna answers
  calculator_ui.py       the Preferences page

Everything is worked out on this computer. Only for currencies does it ask
Frankfurter (frankfurter.dev) for the day's rates, all of them at once.
"""

import datetime
import logging

import core.api
import core.commands
import core.hotkeys
import core.preferences
from core.i18n import get_current_language
from core.speech import speak

import calculator_intents as intents
import calculator_money as money
from calculator_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Calculator"             # fixed, so saved hotkeys survive a language change
INTENT_ID = "Calculator.calculate"
DATA_KEY = "Calculator"
RATES_KEY = "CalculatorRates"

_calculator = None
_panel = None


def action_id(name):
    return f"{EXT_NAME}.{name}"


def _settings():
    return intents.normalize_settings(core.api.load_data(DATA_KEY))


def _save_rates(data):
    core.api.save_data(RATES_KEY, data)


def make_calculator(**overrides):
    """The Calculator with Hariku's settings, clipboard, speech, threads and
    the saved rates (tests replace any of them)."""
    options = dict(
        settings=_settings(),
        rates=money.RateBook(load=lambda: core.api.load_data(RATES_KEY), save=_save_rates),
        language=get_current_language,
        copy=core.api.set_clipboard,
        speak=lambda text: speak(text, interrupt=True),
        run_thread=core.api.run_thread,
        today=datetime.date.today)
    options.update(overrides)
    return intents.Calculator(**options)


# ------------------------------------------------------------
# Aruna
# ------------------------------------------------------------

def _on_request(request):
    if _calculator is None:
        return None
    return _calculator.on_request(request)


def _matcher(text):
    if _calculator is None:
        return None
    return _calculator.matcher(text)


def _run(method):
    def action():
        if _calculator is None:
            return
        message = getattr(_calculator, method)()
        if message:
            speak(message, interrupt=True)
    return action


def can_match():
    """Whether this core takes a matcher (core 2.11) for sentences with no
    lead word ("25 x 4")."""
    return bool(getattr(core.commands, "INTENT_MATCHERS", False))


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    import calculator_ui as ui
    settings = _calculator.settings if _calculator is not None else _settings()
    _panel = ui.CalculatorPanel(parent, settings, get_current_language())
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        settings = _panel.get_settings()
    except RuntimeError:
        return                              # the page is already gone
    core.api.save_data(DATA_KEY, settings)
    if _calculator is not None:
        _calculator.settings = settings


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register(bus, calculator=None):
    global _calculator, _panel
    _panel = None
    _calculator = calculator or make_calculator()
    for name in intents.ACTIONS:
        core.hotkeys.register_action(EXT_NAME, name, _(f"action_{name}"), None, False,
                                     _run(name))
        core.commands.add_aliases(action_id(name), intents.ALIASES[name])
    core.commands.add_answer_actions([action_id(name) for name in intents.ACTIONS])
    if can_match():
        # No patterns: the matcher reads every sentence (lead words too), and
        # Voice Control's vocabulary gets no short words from us.
        core.commands.add_intent(INTENT_ID, [], _on_request, title=_("intent_title"),
                                 matcher=_matcher)
    else:
        core.commands.add_intent(INTENT_ID, intents.PATTERNS, _on_request,
                                 title=_("intent_title"))
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("Calculator & Converter extension loaded.")


def teardown():
    global _calculator, _panel
    try:
        core.commands.remove_intent(INTENT_ID)
    except Exception:
        pass
    for name in intents.ACTIONS:
        try:
            core.commands.remove_aliases(action_id(name))
        except Exception:
            pass
    _calculator = _panel = None
    logger.info("Calculator & Converter extension unloaded.")
