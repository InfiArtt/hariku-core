# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Finance persistence and wording: loads/saves the ledger and settings through
# core.api (atomic JSON), turns records into the sentences the screen reader
# hears, and performs each change as load -> modify -> save so an open dialog
# never writes back a stale copy.
import datetime
import logging
import os

import core.api
from core.i18n import format_date, get_translator

import finance_engine as engine

logger = logging.getLogger(__name__)

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("finance", os.path.join(EXT_DIR, "locales"))

LEDGER_KEY = "Finance"
SETTINGS_KEY = "FinanceSettings"

_settings_cache = None


# --------------------------------------------------------------------------- #
# Ledger and settings
# --------------------------------------------------------------------------- #
def load_ledger():
    raw = core.api.load_data(LEDGER_KEY)
    ledger, changed = engine.normalize_ledger(raw)
    if changed and raw:
        logger.warning("[Finance] Repaired invalid or outdated finance data.")
        core.api.save_data(LEDGER_KEY, ledger)
    return ledger


def save_ledger(ledger):
    return core.api.save_data(LEDGER_KEY, ledger)


def get_settings():
    """Cached, so the minute tick never touches the disk while nothing is due."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = engine.normalize_settings(core.api.load_data(SETTINGS_KEY))
    return _settings_cache


def save_settings(settings):
    global _settings_cache
    _settings_cache = engine.normalize_settings(settings)
    return core.api.save_data(SETTINGS_KEY, _settings_cache)


def update_settings(**changes):
    settings = dict(get_settings())
    settings.update(changes)
    return save_settings(settings)


def reset_cache():
    global _settings_cache
    _settings_cache = None


# --------------------------------------------------------------------------- #
# Wording
# --------------------------------------------------------------------------- #
def money(amount):
    return engine.format_money(amount, get_settings()["currency_symbol"])


def type_label(tx_type):
    return _("type_income") if tx_type == "income" else _("type_expense")


def category_label(category):
    return category or _("uncategorized")


def date_label(iso):
    """'2026-09-03' -> '3 Sep 2026' with translated month names."""
    try:
        day = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso)
    return f"{day.day} {format_date(day, '%b %Y')}"


def month_label(year_month):
    try:
        day = datetime.date.fromisoformat(year_month + "-01")
    except (TypeError, ValueError):
        return str(year_month)
    return format_date(day, "%B %Y")


def transaction_row(tx):
    """One full sentence per row: '23 Sep 2026, Expense, Food, Rp 20.000, coffee'."""
    parts = [date_label(tx["date"]), type_label(tx["type"]),
             category_label(tx["category"]), money(tx["amount"])]
    if tx.get("description"):
        parts.append(tx["description"])
    if tx.get("recurring_id"):
        parts.append(_("row_recurring"))
    return ", ".join(parts)


def schedule_label(rule):
    n = rule.get("interval", 1)
    if n == 1:
        return _("freq_" + rule["frequency"])
    return _("every_" + rule["frequency"], n=n)


def recurring_row(rule):
    values = {"schedule": schedule_label(rule), "type": type_label(rule["type"]),
              "category": category_label(rule["category"]), "amount": money(rule["amount"])}
    if not rule.get("next_date"):
        return _("recurring_row_ended", **values)
    if not rule.get("active", True):
        return _("recurring_row_paused", **values)
    return _("recurring_row", next=date_label(rule["next_date"]), **values)


def budget_row(item):
    """'Food: Rp 450.000 of Rp 500.000, 90%, Rp 50.000 left'."""
    category = category_label(item["category"])
    if item["limit"] is None:
        return _("budget_row_unbudgeted", category=category, used=money(item["used"]))
    values = {"category": category, "used": money(item["used"]),
              "limit": money(item["limit"]), "percent": item["percent"]}
    if item["used"] > item["limit"]:
        return _("budget_row_over", over=money(item["used"] - item["limit"]), **values)
    return _("budget_row_left", left=money(item["limit"] - item["used"]), **values)


def budget_warning_text(warning):
    key = "budget_warn_100" if warning["threshold"] >= 100 else "budget_warn_80"
    return _(key, category=category_label(warning["category"]), percent=warning["percent"],
             used=money(warning["used"]), limit=money(warning["limit"]))


def default_categories():
    return [c.strip() for c in _("default_categories").split("|") if c.strip()]


def all_categories(ledger):
    return engine.list_categories(ledger, default_categories())


# --------------------------------------------------------------------------- #
# Changes (each one: load, modify, save)
# --------------------------------------------------------------------------- #
def save_transaction(values, tx_id=None, today=None):
    """Add (tx_id None) or edit a transaction. `values` holds type, amount,
    category, description and date. Returns (tx, message to speak) or
    (None, error message)."""
    today = today or engine.today_iso()
    ledger = load_ledger()
    month = values["date"][:7]
    used_before = engine.spent_in_month(ledger["transactions"], month, values["category"])
    if tx_id:
        tx = engine.update_transaction(ledger, tx_id, values)
        if tx is None:
            return None, _("tx_missing")
    else:
        tx = engine.add_transaction(ledger, engine.make_transaction(
            values["type"], values["amount"], values["category"],
            values["description"], values["date"]))
    if not save_ledger(ledger):
        return None, _("save_failed")
    message = _("updated_tx" if tx_id else "saved_tx", type=type_label(tx["type"]),
                amount=money(tx["amount"]), category=category_label(tx["category"]))
    if tx["type"] == "expense" and month == today[:7]:
        warning = engine.budget_warning(ledger, tx["category"], month, used_before)
        if warning:
            message += ". " + budget_warning_text(warning)
    return tx, message


def delete_transaction(tx_id):
    ledger = load_ledger()
    removed = engine.delete_transaction(ledger, tx_id)
    if removed is None:
        return None, _("tx_missing")
    if not save_ledger(ledger):
        return None, _("save_failed")
    return removed, _("deleted_tx")


def save_budget(category, limit, old_category=None):
    ledger = load_ledger()
    engine.set_budget(ledger, category, limit, old_category=old_category)
    if not save_ledger(ledger):
        return False, _("save_failed")
    return True, _("budget_saved", category=category, limit=money(limit))


def remove_budget(category):
    ledger = load_ledger()
    if not engine.remove_budget(ledger, category):
        return False, _("no_budget_to_remove", category=category_label(category))
    if not save_ledger(ledger):
        return False, _("save_failed")
    return True, _("budget_removed", category=category_label(category))


def run_recurring(today=None, now=None):
    """Post every due recurring occurrence. Returns the posted transactions."""
    ledger = load_ledger()
    if not ledger["recurring"]:
        return []
    posted, changed = engine.process_recurring(ledger, today or engine.today_iso(now), now=now)
    if changed and not save_ledger(ledger):
        logger.error("[Finance] Could not save recurring transactions.")
        return []
    return posted


def save_rule(values, rule_id=None, today=None):
    """Add or edit a recurring rule, then post anything already due.
    Returns (rule, message) or (None, error message)."""
    today = today or engine.today_iso()
    ledger = load_ledger()
    if rule_id:
        rule = engine.update_rule(ledger, rule_id, values, today)
        if rule is None:
            return None, _("tx_missing")
    else:
        rule = engine.make_rule(values["type"], values["amount"], values["category"],
                                values["description"], values["frequency"],
                                values["interval"], values["start_date"],
                                active=values.get("active", True))
        ledger["recurring"].append(rule)
    posted, _changed = engine.process_recurring(ledger, today)
    if not save_ledger(ledger):
        return None, _("save_failed")
    message = _("recurring_saved", type=type_label(rule["type"]),
                amount=money(rule["amount"]), category=category_label(rule["category"]))
    if posted:
        message += ". " + _("recurring_posted", count=len(posted))
    return rule, message


def delete_rule(rule_id):
    ledger = load_ledger()
    if engine.delete_rule(ledger, rule_id) is None:
        return False, _("tx_missing")
    if not save_ledger(ledger):
        return False, _("save_failed")
    return True, _("recurring_deleted")


def toggle_rule(rule_id, today=None):
    """Pause an active rule or resume a paused one (skipping missed dates)."""
    today = today or engine.today_iso()
    ledger = load_ledger()
    rule = engine.find_rule(ledger, rule_id)
    if rule is None:
        return None, _("tx_missing")
    engine.set_rule_active(ledger, rule_id, not rule["active"], today)
    posted, _changed = engine.process_recurring(ledger, today)
    if not save_ledger(ledger):
        return None, _("save_failed")
    message = _("recurring_resumed" if rule["active"] else "recurring_paused")
    if posted:
        message += ". " + _("recurring_posted", count=len(posted))
    return rule, message
