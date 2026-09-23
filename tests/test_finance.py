# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Finance extension's pure logic (finance_engine.py) and its
# persistence layer (finance_store.py) against a temporary data folder.
import ast
import datetime
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "finance")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(EXT_DIR, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def eng():
    return _load("finance_engine")


def _tx(eng, date, amount, category="Food", tx_type="expense", description="", **extra):
    tx = eng.make_transaction(tx_type, amount, category, description, date,
                              now=datetime.datetime(2026, 1, 1, 9, 0))
    tx.update(extra)
    return tx


def _ledger(eng, txs=(), budgets=(), rules=()):
    ledger = eng.empty_ledger()
    ledger["transactions"] = list(txs)
    ledger["budgets"] = list(budgets)
    ledger["recurring"] = list(rules)
    return ledger


# --------------------------------------------------------------------------- #
# Amount parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text, expected", [
    ("20000", 20000),
    ("20.000", 20000),
    ("20,000", 20000),
    ("1.250.000", 1250000),
    ("1,250,000", 1250000),
    ("  20000  ", 20000),
    ("999", 999),
    ("7", 7),
    ("20rb", 20000),
    ("20 rb", 20000),
    ("20RB", 20000),
    ("20ribu", 20000),
    ("20 ribu", 20000),
    ("20k", 20000),
    ("20K", 20000),
    ("1.5k", 1500),
    ("2,5rb", 2500),
    ("1,5jt", 1500000),
    ("1.5jt", 1500000),
    ("1,5 juta", 1500000),
    ("2jt", 2000000),
    ("2 JUTA", 2000000),
    ("0,5jt", 500000),
    ("1.25jt", 1250000),
    ("Rp 20.000", 20000),
    ("Rp20.000", 20000),
    ("rp. 20.000", 20000),
    ("RP 1,5jt", 1500000),
    ("IDR 20000", 20000),
    ("Rp 20.000,-", 20000),
    ("20.000,-", 20000),
    ("20.000,00", 20000),
    ("20,000.00", 20000),
    ("20000,00", 20000),
    ("20.00", 20),
    ("$20", 20),
])
def test_parse_amount_accepts(eng, text, expected):
    assert eng.parse_amount(text) == expected


@pytest.mark.parametrize("text", [
    "", "   ", "abc", "Rp", "rb", "jt", "rb20",
    "0", "0rb", "000", "-20000", "- 20000", "+20000",
    "20.5", "20,5", "20.000,50",          # cents are not whole amounts
    "20.00.000", "2.0000", "20.0000",     # broken thousands groups
    "1.000,000", "1,000.000", "20.000.00", # mixed or doubled separators
    "20 000", "20k5", "1e5", "20m", "20 jt rb", "20jtan",
    "1.2345rb", "1.250jt", "1.000rb",     # ambiguous with a suffix
    ".5jt", "20..000", "20.", "20,",
    "12345678901234567",                  # over the maximum
    "٢٠٠٠",                                # non-ASCII digits
])
def test_parse_amount_rejects(eng, text):
    assert eng.parse_amount(text) is None


@pytest.mark.parametrize("value", [None, 20000, 20000.0, ["20000"], {"a": 1}])
def test_parse_amount_rejects_non_strings(eng, value):
    assert eng.parse_amount(value) is None


def test_parse_amount_maximum(eng):
    assert eng.parse_amount(str(eng.MAX_AMOUNT)) == eng.MAX_AMOUNT
    assert eng.parse_amount(str(eng.MAX_AMOUNT + 1)) is None


# --------------------------------------------------------------------------- #
# Money formatting
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("amount, text", [
    (0, "Rp 0"),
    (7, "Rp 7"),
    (999, "Rp 999"),
    (1000, "Rp 1.000"),
    (20000, "Rp 20.000"),
    (1500000, "Rp 1.500.000"),
    (1234567890, "Rp 1.234.567.890"),
    (-20000, "Rp -20.000"),
])
def test_format_money(eng, amount, text):
    assert eng.format_money(amount) == text


def test_format_money_symbol(eng):
    assert eng.format_money(20000, "$") == "$ 20.000"
    assert eng.format_money(20000, "") == "20.000"
    assert eng.format_money(20000, None) == "20.000"
    assert eng.format_money(20000, " IDR ") == "IDR 20.000"


@pytest.mark.parametrize("amount", [1, 999, 1000, 20000, 1500000, 987654321])
def test_formatted_amount_parses_back(eng, amount):
    assert eng.parse_amount(eng.format_money(amount)) == amount
    assert eng.parse_amount(eng.group_thousands(amount)) == amount


# --------------------------------------------------------------------------- #
# Dates and times
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text, expected", [
    ("2026-09-23", "2026-09-23"),
    ("2026-9-3", "2026-09-03"),
    ("2026/09/23", "2026-09-23"),
    ("23/09/2026", "2026-09-23"),
    ("23-09-2026", "2026-09-23"),
    ("23.09.2026", "2026-09-23"),
    (" 2024-02-29 ", "2024-02-29"),
])
def test_parse_date_accepts(eng, text, expected):
    assert eng.parse_date(text) == expected


@pytest.mark.parametrize("text", ["", "today", "2026-02-30", "2025-02-29", "31/04/2026",
                                  "2026-13-01", None, 20260923])
def test_parse_date_rejects(eng, text):
    assert eng.parse_date(text) is None


@pytest.mark.parametrize("year, month, days", [
    (2026, 1, 31), (2026, 2, 28), (2024, 2, 29), (2000, 2, 29),
    (2100, 2, 28), (2026, 4, 30), (2026, 12, 31),
])
def test_days_in_month(eng, year, month, days):
    assert eng.days_in_month(year, month) == days


def test_add_months_clamps_to_month_end(eng):
    d = datetime.date
    assert eng.add_months(d(2026, 1, 31), 1, 31) == d(2026, 2, 28)
    assert eng.add_months(d(2024, 1, 31), 1, 31) == d(2024, 2, 29)
    assert eng.add_months(d(2026, 2, 28), 1, 31) == d(2026, 3, 31)
    assert eng.add_months(d(2026, 11, 30), 3, 30) == d(2027, 2, 28)
    assert eng.add_months(d(2026, 12, 15), 1, 15) == d(2027, 1, 15)
    assert eng.add_months(d(9999, 12, 1), 1, 1) is None


@pytest.mark.parametrize("text, expected", [
    ("20:00", "20:00"), ("8:05", "08:05"), ("08.05", "08:05"), (" 23:59 ", "23:59"),
    ("24:00", None), ("12:60", None), ("noon", None), ("", None), (None, None),
])
def test_parse_time(eng, text, expected):
    assert eng.parse_time(text) == expected


# --------------------------------------------------------------------------- #
# Summaries, history and categories
# --------------------------------------------------------------------------- #
TODAY = "2026-09-23"


@pytest.fixture
def sample(eng):
    return _ledger(eng, [
        _tx(eng, "2026-09-23", 20000, "Food", description="coffee"),
        _tx(eng, "2026-09-23", 5000000, "Salary", "income"),
        _tx(eng, "2026-09-10", 150000, "transport"),
        _tx(eng, "2026-08-31", 300000, "Food"),
        _tx(eng, "2025-12-01", 1000000, "Gift", "income"),
        _tx(eng, "2026-09-05", 45000, ""),
    ])


def test_summary_report(eng, sample):
    report = eng.summary_report(sample, TODAY)
    assert report["today"] == {"income": 5000000, "expense": 20000, "net": 4980000, "count": 2}
    assert report["month"] == {"income": 5000000, "expense": 215000, "net": 4785000, "count": 4}
    assert report["all"] == {"income": 6000000, "expense": 515000, "net": 5485000, "count": 6}
    assert report["balance"] == 5485000


def test_summary_of_empty_ledger(eng):
    report = eng.summary_report(eng.empty_ledger(), TODAY)
    assert report["balance"] == 0
    assert report["today"] == {"income": 0, "expense": 0, "net": 0, "count": 0}


def test_filter_transactions_newest_first(eng, sample):
    dates = [t["date"] for t in eng.filter_transactions(sample["transactions"])]
    assert dates == sorted(dates, reverse=True)
    september = eng.filter_transactions(sample["transactions"], month="2026-09")
    assert {t["date"][:7] for t in september} == {"2026-09"}
    assert len(september) == 4


def test_filter_transactions_by_category_ignores_case(eng, sample):
    food = eng.filter_transactions(sample["transactions"], category="FOOD")
    assert [t["amount"] for t in food] == [20000, 300000]
    assert len(eng.filter_transactions(sample["transactions"], "2026-09", "food")) == 1
    blank = eng.filter_transactions(sample["transactions"], category="")
    assert [t["amount"] for t in blank] == [45000]


def test_months_in(eng, sample):
    assert eng.months_in(sample["transactions"]) == ["2026-09", "2026-08", "2025-12"]
    assert eng.months_in([], extra=["2026-09"]) == ["2026-09"]


def test_categories_in_lists_blank_last(eng, sample):
    assert eng.categories_in(sample["transactions"]) == ["Food", "Gift", "Salary", "transport", ""]


def test_list_categories_merges_and_dedupes(eng, sample):
    sample["budgets"] = [{"category": "Rent", "limit": 1000}]
    names = eng.list_categories(sample, ["Food", "Transport", "Health"])
    assert names == ["Food", "Gift", "Health", "Rent", "Salary", "transport"]
    assert "" not in names


def test_transaction_crud(eng):
    ledger = eng.empty_ledger()
    tx = eng.add_transaction(ledger, _tx(eng, TODAY, 20000))
    assert eng.find_transaction(ledger, tx["id"]) is tx
    eng.update_transaction(ledger, tx["id"], {"amount": 25000, "category": "Snacks"})
    assert (tx["amount"], tx["category"], tx["date"]) == (25000, "Snacks", TODAY)
    with pytest.raises(ValueError):
        eng.update_transaction(ledger, tx["id"], {"amount": 0})
    assert tx["amount"] == 25000
    assert eng.update_transaction(ledger, "missing", {"amount": 1}) is None
    assert eng.delete_transaction(ledger, tx["id"])["id"] == tx["id"]
    assert eng.delete_transaction(ledger, tx["id"]) is None
    assert ledger["transactions"] == []


def test_make_transaction_rejects_bad_values(eng):
    with pytest.raises(ValueError):
        eng.make_transaction("expense", 0, "Food", "", TODAY)
    with pytest.raises(ValueError):
        eng.make_transaction("gift", 100, "Food", "", TODAY)
    with pytest.raises(ValueError):
        eng.make_transaction("expense", 100, "Food", "", "not a date")


# --------------------------------------------------------------------------- #
# Budgets
# --------------------------------------------------------------------------- #
def test_budget_usage(eng, sample):
    eng.set_budget(sample, "food", 25000)
    eng.set_budget(sample, "Transport", 200000)
    eng.set_budget(sample, "Health", 100000)
    rows = eng.budget_usage(sample, "2026-09")
    assert rows[:3] == [
        {"category": "food", "limit": 25000, "used": 20000, "percent": 80},
        {"category": "Health", "limit": 100000, "used": 0, "percent": 0},
        {"category": "Transport", "limit": 200000, "used": 150000, "percent": 75},
    ]
    # Spending without a budget is listed after the budgets.
    assert rows[3:] == [{"category": "", "limit": None, "used": 45000, "percent": None}]


def test_budget_percent_rounds_down(eng):
    assert eng.budget_percent(450000, 500000) == 90
    assert eng.budget_percent(499999, 500000) == 99
    assert eng.budget_percent(500000, 500000) == 100
    assert eng.budget_percent(1, 0) == 0


def test_set_and_remove_budget(eng):
    ledger = eng.empty_ledger()
    eng.set_budget(ledger, "Food", 500000)
    eng.set_budget(ledger, "FOOD", 600000)
    assert ledger["budgets"] == [{"category": "FOOD", "limit": 600000}]
    assert eng.get_budget(ledger, "food") == 600000
    eng.set_budget(ledger, "Groceries", 700000, old_category="food")
    assert ledger["budgets"] == [{"category": "Groceries", "limit": 700000}]
    assert eng.remove_budget(ledger, "groceries")
    assert not eng.remove_budget(ledger, "groceries")
    assert eng.get_budget(ledger, "Groceries") is None
    with pytest.raises(ValueError):
        eng.set_budget(ledger, "", 1000)
    with pytest.raises(ValueError):
        eng.set_budget(ledger, "Food", 0)


@pytest.mark.parametrize("before, after, crossed", [
    (0, 79, []),
    (0, 80, [80]),
    (79, 80, [80]),
    (80, 85, []),
    (85, 99, []),
    (99, 100, [100]),
    (70, 100, [80, 100]),
    (0, 250, [80, 100]),
    (100, 120, []),
    (90, 80, []),
])
def test_budget_crossings(eng, before, after, crossed):
    assert eng.budget_crossings(before, after, 100) == crossed


def test_budget_crossings_exact_thresholds(eng):
    # 80% of 500.000 is exactly 400.000.
    assert eng.budget_crossings(399999, 400000, 500000) == [80]
    assert eng.budget_crossings(400000, 499999, 500000) == []
    assert eng.budget_crossings(499999, 500000, 500000) == [100]
    assert eng.budget_crossings(0, 10 ** 9, 0) == []


def test_budget_warning(eng):
    ledger = _ledger(eng, [_tx(eng, TODAY, 350000)], [{"category": "Food", "limit": 500000}])
    before = eng.spent_in_month(ledger["transactions"], "2026-09", "Food")
    eng.add_transaction(ledger, _tx(eng, TODAY, 60000, "food"))
    warning = eng.budget_warning(ledger, "food", "2026-09", before)
    assert warning == {"category": "Food", "limit": 500000, "used": 410000,
                       "percent": 82, "threshold": 80}
    before = eng.spent_in_month(ledger["transactions"], "2026-09", "Food")
    eng.add_transaction(ledger, _tx(eng, TODAY, 20000))
    assert eng.budget_warning(ledger, "Food", "2026-09", before) is None
    before = eng.spent_in_month(ledger["transactions"], "2026-09", "Food")
    eng.add_transaction(ledger, _tx(eng, TODAY, 100000))
    assert eng.budget_warning(ledger, "Food", "2026-09", before)["threshold"] == 100
    assert eng.budget_warning(ledger, "Transport", "2026-09", 0) is None


def test_income_never_counts_toward_budgets(eng):
    ledger = _ledger(eng, [_tx(eng, TODAY, 900000, "Food", "income")],
                     [{"category": "Food", "limit": 500000}])
    assert eng.spent_in_month(ledger["transactions"], "2026-09", "Food") == 0
    assert eng.budget_warning(ledger, "Food", "2026-09", 0) is None


# --------------------------------------------------------------------------- #
# Recurring schedules
# --------------------------------------------------------------------------- #
def _rule(eng, frequency, start, interval=1, **kw):
    return eng.make_rule(kw.get("tx_type", "expense"), kw.get("amount", 100000),
                         kw.get("category", "Rent"), kw.get("description", ""),
                         frequency, interval, start)


def _series(eng, rule, count):
    dates, current = [], rule["start_date"]
    for _i in range(count):
        dates.append(current)
        current = eng.next_occurrence(rule, current)
    return dates


def test_monthly_keeps_month_end(eng):
    rule = _rule(eng, "monthly", "2026-01-31")
    assert _series(eng, rule, 6) == ["2026-01-31", "2026-02-28", "2026-03-31",
                                     "2026-04-30", "2026-05-31", "2026-06-30"]


def test_monthly_in_a_leap_year(eng):
    rule = _rule(eng, "monthly", "2024-01-31")
    assert _series(eng, rule, 3) == ["2024-01-31", "2024-02-29", "2024-03-31"]
    rule = _rule(eng, "monthly", "2024-01-29")
    assert _series(eng, rule, 3) == ["2024-01-29", "2024-02-29", "2024-03-29"]


def test_monthly_with_interval(eng):
    rule = _rule(eng, "monthly", "2025-11-30", interval=3)
    assert _series(eng, rule, 4) == ["2025-11-30", "2026-02-28", "2026-05-30", "2026-08-30"]


def test_yearly_from_leap_day(eng):
    rule = _rule(eng, "yearly", "2024-02-29")
    assert _series(eng, rule, 5) == ["2024-02-29", "2025-02-28", "2026-02-28",
                                     "2027-02-28", "2028-02-29"]
    assert _series(eng, _rule(eng, "yearly", "2024-02-29", interval=4), 3) == [
        "2024-02-29", "2028-02-29", "2032-02-29"]


def test_daily_and_weekly(eng):
    assert _series(eng, _rule(eng, "daily", "2026-02-27"), 4) == [
        "2026-02-27", "2026-02-28", "2026-03-01", "2026-03-02"]
    assert _series(eng, _rule(eng, "daily", "2026-09-23", interval=3), 3) == [
        "2026-09-23", "2026-09-26", "2026-09-29"]
    assert _series(eng, _rule(eng, "weekly", "2026-12-24", interval=2), 3) == [
        "2026-12-24", "2027-01-07", "2027-01-21"]


def test_schedule_ends_after_year_9999(eng):
    assert eng.next_occurrence(_rule(eng, "yearly", "9999-06-01"), "9999-06-01") is None


@pytest.mark.parametrize("frequency, start, interval, target, expected", [
    ("monthly", "2026-01-31", 1, "2025-12-01", "2026-01-31"),
    ("monthly", "2026-01-31", 1, "2026-01-31", "2026-01-31"),
    ("monthly", "2026-01-31", 1, "2026-02-01", "2026-02-28"),
    ("monthly", "2026-01-31", 1, "2026-03-01", "2026-03-31"),
    ("monthly", "2026-01-31", 2, "2026-02-15", "2026-03-31"),
    ("yearly", "2024-02-29", 1, "2027-03-01", "2028-02-29"),
    ("daily", "2026-09-01", 3, "2026-09-05", "2026-09-07"),
    ("daily", "2026-09-01", 3, "2026-09-07", "2026-09-07"),
    ("weekly", "2026-09-01", 1, "2026-09-02", "2026-09-08"),
])
def test_first_occurrence_on_or_after(eng, frequency, start, interval, target, expected):
    rule = _rule(eng, frequency, start, interval=interval)
    assert eng.first_occurrence_on_or_after(rule, target) == expected


def test_process_recurring_catches_up_with_month_end(eng):
    ledger = _ledger(eng, rules=[_rule(eng, "monthly", "2026-01-31")])
    posted, changed = eng.process_recurring(ledger, "2026-04-15")
    assert changed
    assert [t["date"] for t in posted] == ["2026-01-31", "2026-02-28", "2026-03-31"]
    rule = ledger["recurring"][0]
    assert rule["next_date"] == "2026-04-30"
    assert rule["last_posted"] == "2026-03-31"
    assert all(t["recurring_id"] == rule["id"] for t in posted)
    assert len({t["id"] for t in posted}) == 3


def test_process_recurring_is_idempotent_across_restarts(eng):
    ledger = _ledger(eng, rules=[_rule(eng, "monthly", "2026-01-31"),
                                 _rule(eng, "weekly", "2026-09-01", category="Laundry")])
    first, _changed = eng.process_recurring(ledger, TODAY)
    assert len(first) == 8 + 4
    # Same day again: nothing.
    assert eng.process_recurring(ledger, TODAY) == ([], False)
    # "Restart": serialize, reload, repair, process again.
    for _restart in range(3):
        reloaded, changed = eng.normalize_ledger(json.loads(json.dumps(ledger)))
        assert not changed
        assert eng.process_recurring(reloaded, TODAY) == ([], False)
        ledger = reloaded
    assert len(ledger["transactions"]) == 12
    # The next day posts only what became due.
    posted, _changed = eng.process_recurring(ledger, "2026-09-29")
    assert [t["date"] for t in posted] == ["2026-09-29"]


def test_process_recurring_never_double_posts_a_stale_rule(eng):
    ledger = _ledger(eng, rules=[_rule(eng, "monthly", "2026-01-31")])
    stale_rule = dict(ledger["recurring"][0])
    eng.process_recurring(ledger, "2026-03-31")
    # A crash or an old backup put back the rule without its progress.
    ledger["recurring"][0] = dict(stale_rule)
    posted, _changed = eng.process_recurring(ledger, "2026-03-31")
    assert posted == []
    assert len(ledger["transactions"]) == 3
    assert ledger["recurring"][0]["next_date"] == "2026-04-30"


def test_process_recurring_skips_paused_and_caps_catch_up(eng):
    paused = _rule(eng, "daily", "2026-01-01")
    paused["active"] = False
    busy = _rule(eng, "daily", "2020-01-01", category="Parking")
    ledger = _ledger(eng, rules=[paused, busy])
    posted, _changed = eng.process_recurring(ledger, TODAY, max_per_rule=100)
    assert len(posted) == 100
    assert all(t["category"] == "Parking" for t in posted)
    assert busy["next_date"] == "2020-04-10"
    posted, _changed = eng.process_recurring(ledger, "2020-04-10", max_per_rule=100)
    assert [t["date"] for t in posted] == ["2020-04-10"]


def test_future_rule_posts_nothing_yet(eng):
    ledger = _ledger(eng, rules=[_rule(eng, "monthly", "2026-10-01")])
    assert eng.process_recurring(ledger, TODAY) == ([], False)


def test_resume_skips_missed_dates(eng):
    ledger = _ledger(eng, rules=[_rule(eng, "monthly", "2026-01-05")])
    rule_id = ledger["recurring"][0]["id"]
    eng.process_recurring(ledger, "2026-02-10")
    eng.set_rule_active(ledger, rule_id, False, "2026-02-10")
    assert eng.process_recurring(ledger, "2026-06-10") == ([], False)
    eng.set_rule_active(ledger, rule_id, True, "2026-06-10")
    assert ledger["recurring"][0]["next_date"] == "2026-07-05"
    posted, _changed = eng.process_recurring(ledger, "2026-07-05")
    assert [t["date"] for t in posted] == ["2026-07-05"]


def test_update_rule_never_reposts_past_dates(eng):
    ledger = _ledger(eng, rules=[_rule(eng, "monthly", "2026-01-15")])
    rule_id = ledger["recurring"][0]["id"]
    eng.process_recurring(ledger, "2026-03-20")
    assert len(ledger["transactions"]) == 3
    # Moving the start back must not back-fill January to March again.
    eng.update_rule(ledger, rule_id, {"start_date": "2026-01-01"}, "2026-03-20")
    assert ledger["recurring"][0]["next_date"] == "2026-04-01"
    eng.update_rule(ledger, rule_id, {"amount": 250000}, "2026-03-20")
    assert ledger["recurring"][0]["next_date"] == "2026-04-01"
    assert ledger["recurring"][0]["amount"] == 250000
    assert eng.update_rule(ledger, "missing", {}, "2026-03-20") is None
    with pytest.raises(ValueError):
        eng.update_rule(ledger, rule_id, {"frequency": "hourly"}, "2026-03-20")


def test_delete_rule_keeps_posted_transactions(eng):
    ledger = _ledger(eng, rules=[_rule(eng, "weekly", "2026-09-01")])
    eng.process_recurring(ledger, TODAY)
    assert eng.delete_rule(ledger, ledger["recurring"][0]["id"])
    assert ledger["recurring"] == []
    assert len(ledger["transactions"]) == 4


# --------------------------------------------------------------------------- #
# Reminder rule
# --------------------------------------------------------------------------- #
def test_reminder_due(eng):
    at = datetime.datetime(2026, 9, 23, 20, 0)
    settings = eng.normalize_settings({"reminder_enabled": True, "reminder_time": "20:00"})
    assert eng.reminder_due(settings, at)
    assert eng.reminder_due(settings, at.replace(hour=23))
    assert not eng.reminder_due(settings, at.replace(hour=19, minute=59))
    assert not eng.reminder_due(dict(settings, last_reminder_date="2026-09-23"), at)
    assert eng.reminder_due(dict(settings, last_reminder_date="2026-09-22"), at)
    assert not eng.reminder_due(eng.normalize_settings({}), at)


def test_manual_entry_detection(eng):
    auto = _tx(eng, TODAY, 100, recurring_id="r1", created=TODAY + "T00:01:00")
    assert not eng.has_manual_entry_on([auto], TODAY)
    backdated = _tx(eng, "2026-09-20", 100, created=TODAY + "T19:00:00")
    assert eng.has_manual_entry_on([auto, backdated], TODAY)
    dated_today = _tx(eng, TODAY, 100, created="2026-09-22T10:00:00")
    assert eng.has_manual_entry_on([dated_today], TODAY)
    assert not eng.has_manual_entry_on([], TODAY)


def test_settings_defaults_and_repair(eng):
    assert eng.normalize_settings(None) == {"currency_symbol": "Rp", "reminder_enabled": False,
                                            "reminder_time": "20:00", "last_reminder_date": ""}
    fixed = eng.normalize_settings({"currency_symbol": 5, "reminder_enabled": "yes",
                                    "reminder_time": "25:00", "last_reminder_date": "x"})
    assert fixed == {"currency_symbol": "Rp", "reminder_enabled": False,
                     "reminder_time": "20:00", "last_reminder_date": ""}
    assert eng.normalize_settings({"currency_symbol": ""})["currency_symbol"] == ""
    assert eng.normalize_settings({"currency_symbol": "  $  "})["currency_symbol"] == "$"


# --------------------------------------------------------------------------- #
# Validation and repair of stored data
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw", [None, {}, [], "garbage", 42, {"transactions": "x",
                                                                 "budgets": 5, "recurring": {}}])
def test_normalize_empty_or_corrupt(eng, raw):
    ledger, _changed = eng.normalize_ledger(raw)
    assert ledger == eng.empty_ledger()


def test_normalize_repairs_records(eng):
    raw = {
        "transactions": [
            {"id": "a", "date": "2026-09-23", "type": "expense", "amount": 20000,
             "category": "Food", "description": "coffee"},
            {"id": "a", "date": "2026-09-22", "type": "EXPENSE", "amount": "20rb",
             "category": "  Food  ", "description": None},
            {"date": "2026-09-21T08:30:00", "type": "income", "amount": 5000.4,
             "category": None, "description": 12},
            {"date": "2026-09-20", "type": "expense", "amount": -300},
            {"date": "2026-09-20", "type": "transfer", "amount": 100},
            {"date": "not a date", "type": "expense", "amount": 100},
            {"date": "2026-09-20", "type": "expense", "amount": 0},
            {"date": "2026-09-20", "type": "expense", "amount": True},
            {"date": "2026-09-20", "type": "expense", "amount": "lots"},
            {"date": "2026-09-20", "type": "expense", "amount": float("nan")},
            {"id": "rec-r1-2026-09-01", "date": "2026-09-01", "type": "expense",
             "amount": 100, "recurring_id": "r1"},
            {"id": "rec-r1-2026-09-01", "date": "2026-09-01", "type": "expense",
             "amount": 100, "recurring_id": "r1"},
            "not a dict",
            None,
        ],
        "budgets": {"Food": 500000, "food": 600000, "Bad": -5, "": 100, "None": "x"},
        "recurring": [
            {"id": "r1", "type": "expense", "amount": 100, "frequency": "monthly",
             "start_date": "2026-01-01", "last_posted": "2026-09-01", "interval": "abc"},
            {"id": "r2", "type": "expense", "amount": 100, "frequency": "hourly",
             "start_date": "2026-01-01"},
            {"id": "r3", "type": "income", "amount": 100, "frequency": "weekly",
             "next_date": "2026-09-24", "interval": 5000},
            {"type": "expense", "amount": 100, "frequency": "daily"},
        ],
        "future_key": {"kept": True},
    }
    ledger, changed = eng.normalize_ledger(raw)
    assert changed
    txs = ledger["transactions"]
    assert [t["amount"] for t in txs] == [20000, 20000, 5000, 100]   # negative dropped
    assert txs[0]["id"] == "a" and txs[1]["id"] != "a"
    assert txs[1]["type"] == "expense" and txs[1]["category"] == "Food"
    assert txs[1]["description"] == ""
    assert txs[2]["date"] == "2026-09-21" and txs[2]["category"] == ""
    assert txs[2]["description"] == "12"
    assert sum(1 for t in txs if t["id"] == "rec-r1-2026-09-01") == 1
    assert ledger["budgets"] == [{"category": "food", "limit": 600000}]
    rules = {r["id"]: r for r in ledger["recurring"]}
    assert set(rules) == {"r1", "r3"}
    assert rules["r1"]["interval"] == 1
    assert rules["r1"]["next_date"] == "2026-10-01"   # after last_posted, never before
    assert rules["r3"]["start_date"] == "2026-09-24"
    assert rules["r3"]["interval"] == eng.MAX_INTERVAL
    assert ledger["future_key"] == {"kept": True}
    # Repairing again changes nothing.
    assert eng.normalize_ledger(ledger) == (ledger, False)


def test_normalize_reads_v1_transaction_list(eng):
    v1 = [{"date": "2026-01-02T10:00:00.123", "type": "expense", "category": "Food",
           "amount": 15000, "description": "Nasi", "original_text": "Manual Entry"},
          {"date": "2026-01-03", "type": "investment", "amount": 1}]
    ledger, changed = eng.normalize_ledger(v1)
    assert changed
    assert len(ledger["transactions"]) == 1
    tx = ledger["transactions"][0]
    assert (tx["date"], tx["amount"], tx["original_text"]) == ("2026-01-02", 15000, "Manual Entry")


def test_normalize_keeps_valid_ledger_unchanged(eng, sample):
    sample["budgets"] = [{"category": "Food", "limit": 500000}]
    sample["recurring"] = [_rule(eng, "monthly", "2026-01-31")]
    eng.process_recurring(sample, TODAY)
    assert eng.normalize_ledger(json.loads(json.dumps(sample))) == (sample, False)


# --------------------------------------------------------------------------- #
# Persistence through core.api (temporary data folder)
# --------------------------------------------------------------------------- #
@pytest.fixture
def store(tmp_data_dir, eng, monkeypatch):
    monkeypatch.setitem(sys.modules, "finance_engine", eng)
    module = _load("finance_store")
    module.reset_cache()
    return module


def _write_raw(tmp_data_dir, name, text):
    with open(os.path.join(tmp_data_dir, name + ".json"), "w", encoding="utf-8") as f:
        f.write(text)


def test_store_round_trip(store):
    tx, message = store.save_transaction({"type": "expense", "amount": 20000, "category": "Food",
                                          "description": "coffee", "date": TODAY}, today=TODAY)
    assert tx is not None
    assert "Rp 20.000" in message
    ledger = store.load_ledger()
    assert [t["id"] for t in ledger["transactions"]] == [tx["id"]]
    edited, _message = store.save_transaction(dict(tx, amount=25000), tx_id=tx["id"], today=TODAY)
    assert edited["amount"] == 25000
    assert store.load_ledger()["transactions"][0]["amount"] == 25000
    removed, _message = store.delete_transaction(tx["id"])
    assert removed["id"] == tx["id"]
    assert store.load_ledger()["transactions"] == []
    assert store.delete_transaction(tx["id"])[0] is None


def test_store_budget_warning_is_spoken_once(store):
    store.save_budget("Food", 100000)
    values = {"type": "expense", "amount": 50000, "category": "Food", "description": "", "date": TODAY}
    _tx1, first = store.save_transaction(values, today=TODAY)
    _tx2, second = store.save_transaction(dict(values, amount=35000), today=TODAY)
    _tx3, third = store.save_transaction(dict(values, amount=1000), today=TODAY)
    _tx4, fourth = store.save_transaction(dict(values, amount=20000), today=TODAY)
    assert "Rp 100.000" not in first
    assert "85%" in second and "Rp 85.000" in second and "Rp 100.000" in second
    assert "%" not in third
    assert "106%" in fourth
    # An expense in an earlier month does not warn about this month's budget.
    _tx5, old = store.save_transaction(dict(values, date="2026-08-01", amount=99000), today=TODAY)
    assert "%" not in old


def test_store_repairs_corrupt_file(store, tmp_data_dir):
    _write_raw(tmp_data_dir, store.LEDGER_KEY, "{ this is not json")
    assert store.load_ledger()["transactions"] == []
    _write_raw(tmp_data_dir, store.LEDGER_KEY, json.dumps(
        {"transactions": [{"date": TODAY, "type": "expense", "amount": "20rb"}, 7]}))
    ledger = store.load_ledger()
    assert [t["amount"] for t in ledger["transactions"]] == [20000]
    with open(os.path.join(tmp_data_dir, store.LEDGER_KEY + ".json"), encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["transactions"][0]["amount"] == 20000   # repaired copy written back
    assert on_disk["version"] == 1


def test_store_recurring_survives_restarts(store, eng, tmp_data_dir, monkeypatch):
    rule, message = store.save_rule({"type": "expense", "amount": 2000000, "category": "Rent",
                                     "description": "", "frequency": "monthly", "interval": 1,
                                     "start_date": "2026-07-31", "active": True}, today=TODAY)
    assert rule is not None and "Rp 2.000.000" in message
    assert len(store.load_ledger()["transactions"]) == 2      # Jul 31 and Aug 31
    for _restart in range(3):
        fresh = _load("finance_store")                         # a new process, same data
        assert fresh.run_recurring(today=TODAY) == []
    assert len(store.load_ledger()["transactions"]) == 2
    assert [t["date"] for t in store.run_recurring(today="2026-09-30")] == ["2026-09-30"]
    assert store.run_recurring(today="2026-09-30") == []
    ok, _message = store.delete_rule(rule["id"])
    assert ok and len(store.load_ledger()["transactions"]) == 3


def test_store_settings_are_cached_and_saved(store):
    assert store.get_settings()["currency_symbol"] == "Rp"
    store.update_settings(currency_symbol="$", reminder_enabled=True)
    assert store.money(20000) == "$ 20.000"
    store.reset_cache()
    assert store.get_settings()["reminder_enabled"] is True
    assert store.get_settings()["currency_symbol"] == "$"


# --------------------------------------------------------------------------- #
# Extension hygiene
# --------------------------------------------------------------------------- #
HEADER = """# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""


def _py_files():
    return sorted(f for f in os.listdir(EXT_DIR) if f.endswith(".py"))


def test_helper_modules_are_prefixed():
    assert all(f == "main.py" or f.startswith("finance_") for f in _py_files())


def test_files_carry_the_license_header():
    for name in _py_files() + ["../../tests/test_finance.py", "../../tests/_finance_ui_check.py"]:
        with open(os.path.join(EXT_DIR, name), encoding="utf-8") as f:
            assert f.read().startswith(HEADER), name


def test_no_network_imports():
    network = {"socket", "ssl", "urllib", "http", "requests", "ftplib", "smtplib"}
    for name in _py_files():
        with open(os.path.join(EXT_DIR, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not {n.split(".")[0] for n in names} & network, name


def _used_keys():
    """String keys passed to _() anywhere in the extension."""
    keys = set()
    for name in _py_files():
        with open(os.path.join(EXT_DIR, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
    return keys


def test_translations_cover_every_key(eng):
    locales = {}
    for lang in ("en", "id"):
        with open(os.path.join(EXT_DIR, "locales", lang + ".json"), encoding="utf-8") as f:
            locales[lang] = json.load(f)["messages"]
    assert set(locales["en"]) == set(locales["id"])
    dynamic = {prefix + f for f in eng.FREQUENCIES
               for prefix in ("freq_", "every_", "lbl_interval_")}
    dynamic |= {"budget_warn_80", "budget_warn_100", "saved_tx", "updated_tx",
                "recurring_resumed", "recurring_paused"}
    missing = (_used_keys() | dynamic) - set(locales["en"])
    assert not missing, sorted(missing)
    for lang, messages in locales.items():
        for key, text in messages.items():
            assert text.strip(), f"{lang}:{key} is empty"
