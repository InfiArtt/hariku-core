# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Pure Finance logic: amount parsing, money formatting, data validation and
# repair, summaries, budgets, recurring schedules and the reminder rule.
# No wx and no Hariku imports, so the tests can load this file on its own.
# Amounts are whole numbers (Rupiah has no cents in everyday use).
import datetime
import re
import uuid

TYPES = ("expense", "income")
FREQUENCIES = ("daily", "weekly", "monthly", "yearly")
BUDGET_THRESHOLDS = (80, 100)
MAX_AMOUNT = 10 ** 15
MAX_INTERVAL = 999
MAX_CATCH_UP = 1000        # occurrences posted per rule per run
MAX_CATEGORY_LEN = 60
MAX_DESCRIPTION_LEN = 200
DEFAULT_SYMBOL = "Rp"
DEFAULT_REMINDER_TIME = "20:00"
LEDGER_VERSION = 1

_MULTIPLIERS = {"": 1, "k": 1000, "rb": 1000, "ribu": 1000,
                "jt": 1000000, "juta": 1000000}
_PREFIX_RE = re.compile(r"^(?:rp\.?|idr|[$€£¥])\s*")
_DASH_RE = re.compile(r"(?<=[0-9])[.,]-$")  # "20.000,-" (no cents)
_AMOUNT_RE = re.compile(r"^([0-9][0-9.,]*)\s*([a-z]*)$")
_GROUPED_RE = re.compile(r"^[0-9]{1,3}([.,])[0-9]{3}(?:\1[0-9]{3})*$")
_CENTS_RE = re.compile(r"^(.*)([.,])([0-9]{1,2})$")
_SCALED_RE = re.compile(r"^([0-9]+)(?:[.,]([0-9]{1,2}))?$")
_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


# --------------------------------------------------------------------------- #
# Amounts
# --------------------------------------------------------------------------- #
def parse_amount(text):
    """Turn user input into a whole amount, or None if it isn't one.

    Accepted: "20000", "20.000", "20,000", "Rp 20.000", "Rp 20.000,-",
    "20.000,00", "20rb" / "20 ribu" / "20k" (thousands), "1,5jt" / "1.5 juta"
    (millions). Without a suffix, "." and "," are thousands separators; with one
    they are a decimal point (one or two digits). Anything ambiguous is rejected."""
    if not isinstance(text, str):
        return None
    s = _PREFIX_RE.sub("", text.strip().lower(), count=1)
    s = _DASH_RE.sub("", s)
    m = _AMOUNT_RE.match(s)
    if not m:
        return None
    number, suffix = m.groups()
    multiplier = _MULTIPLIERS.get(suffix)
    if multiplier is None:
        return None
    if multiplier == 1:
        value = _parse_plain(number)
    else:
        value = _parse_scaled(number, multiplier)
    if value is None or value <= 0 or value > MAX_AMOUNT:
        return None
    return value


def _parse_plain(number):
    m = _CENTS_RE.match(number)
    if m:
        whole, sep, cents = m.groups()
        # Zero cents only ("20.000,00"), written with the other separator.
        if int(cents) != 0 or sep in whole:
            return None
        number = whole
    if number.isdigit():
        return int(number)
    if _GROUPED_RE.match(number):
        return int(number.replace(".", "").replace(",", ""))
    return None


def _parse_scaled(number, multiplier):
    m = _SCALED_RE.match(number)
    if not m:
        return None
    whole, frac = m.group(1), m.group(2) or ""
    scale = 10 ** len(frac)
    total = int(whole) * multiplier * scale + int(frac or 0) * multiplier
    if total % scale:
        return None
    return total // scale


def group_thousands(amount):
    """20000 -> '20.000' (dot as the thousands separator)."""
    return f"{abs(int(amount)):,}".replace(",", ".")


def format_money(amount, symbol=DEFAULT_SYMBOL):
    """20000 -> 'Rp 20.000'; negative -> 'Rp -20.000' (reads as 'minus')."""
    amount = int(amount)
    digits = group_thousands(amount)
    if amount < 0:
        digits = "-" + digits
    symbol = (symbol or "").strip()
    return f"{symbol} {digits}" if symbol else digits


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #
def today_iso(now=None):
    return (now or datetime.datetime.now()).date().isoformat()


def parse_date(text):
    """User date input -> 'YYYY-MM-DD', or None. Accepts YYYY-MM-DD, YYYY/MM/DD,
    DD/MM/YYYY, DD-MM-YYYY and DD.MM.YYYY."""
    if not isinstance(text, str):
        return None
    s = text.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _is_iso(value):
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        datetime.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _to_date(value):
    return datetime.date.fromisoformat(value)


def days_in_month(year, month):
    if month == 12:
        return 31
    return (datetime.date(year, month + 1, 1) - datetime.date(year, month, 1)).days


def add_months(day, months, anchor_day):
    """Move `day` by whole months, landing on `anchor_day` clamped to the month's
    length (Jan 31 + 1 month -> Feb 28/29). None past year 9999."""
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    if year < 1 or year > 9999:
        return None
    return datetime.date(year, month, min(anchor_day, days_in_month(year, month)))


# --------------------------------------------------------------------------- #
# Validation and repair
# --------------------------------------------------------------------------- #
def new_id():
    return uuid.uuid4().hex


def _clean_text(value, limit):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return " ".join(value.split())[:limit]


def _clean_amount(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not abs(value) <= MAX_AMOUNT:  # also rejects NaN and infinity
            return None
        number = int(round(value))
    elif isinstance(value, str):
        number = parse_amount(value)
    else:
        return None
    if number is None or number <= 0 or number > MAX_AMOUNT:
        return None
    return number


def _clean_date(value):
    if isinstance(value, str) and len(value) >= 10 and _is_iso(value[:10]):
        return value[:10]
    return parse_date(value) if isinstance(value, str) else None


def _clean_type(value):
    t = str(value or "").strip().lower()
    return t if t in TYPES else None


def _clean_interval(value):
    if isinstance(value, bool):
        return 1
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(MAX_INTERVAL, n))


def normalize_transaction(item):
    """A cleaned copy of one transaction, or None if it can't be salvaged.
    Unknown fields are kept so newer data survives an older version."""
    if not isinstance(item, dict):
        return None
    tx_type = _clean_type(item.get("type"))
    amount = _clean_amount(item.get("amount"))
    date = _clean_date(item.get("date"))
    if tx_type is None or amount is None or date is None:
        return None
    tx = dict(item)
    tx_id = item.get("id")
    tx["id"] = tx_id.strip() if isinstance(tx_id, str) and tx_id.strip() else new_id()
    tx["date"] = date
    tx["type"] = tx_type
    tx["category"] = _clean_text(item.get("category"), MAX_CATEGORY_LEN)
    tx["amount"] = amount
    tx["description"] = _clean_text(item.get("description"), MAX_DESCRIPTION_LEN)
    if not isinstance(tx.get("recurring_id"), str) or not tx.get("recurring_id"):
        tx.pop("recurring_id", None)
    if not isinstance(tx.get("created"), str):
        tx.pop("created", None)
    return tx


def normalize_rule(item):
    """A cleaned copy of one recurring rule, or None if it can't be salvaged."""
    if not isinstance(item, dict):
        return None
    tx_type = _clean_type(item.get("type"))
    amount = _clean_amount(item.get("amount"))
    frequency = str(item.get("frequency") or "").strip().lower()
    start = _clean_date(item.get("start_date"))
    next_date = _clean_date(item.get("next_date"))
    if start is None:
        start = next_date
    if tx_type is None or amount is None or frequency not in FREQUENCIES or start is None:
        return None
    rule = dict(item)
    rule_id = item.get("id")
    rule["id"] = rule_id.strip() if isinstance(rule_id, str) and rule_id.strip() else new_id()
    rule["type"] = tx_type
    rule["amount"] = amount
    rule["category"] = _clean_text(item.get("category"), MAX_CATEGORY_LEN)
    rule["description"] = _clean_text(item.get("description"), MAX_DESCRIPTION_LEN)
    rule["frequency"] = frequency
    rule["interval"] = _clean_interval(item.get("interval", 1))
    rule["start_date"] = start
    rule["last_posted"] = _clean_date(item.get("last_posted")) or ""
    rule["active"] = item.get("active", True) is not False
    if item.get("next_date") == "" and not rule["active"]:
        rule["next_date"] = ""  # schedule ran out (past year 9999)
        return rule
    if next_date is None or next_date < start or (rule["last_posted"] and next_date <= rule["last_posted"]):
        # Never go back to a date that was already posted.
        after = _day_after(rule["last_posted"]) if rule["last_posted"] else start
        next_date = first_occurrence_on_or_after(rule, after) if after else None
    rule["next_date"] = next_date or ""
    if not next_date:
        rule["active"] = False
    return rule


def _normalize_budgets(raw):
    if isinstance(raw, dict):
        items = [{"category": k, "limit": v} for k, v in raw.items()]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    merged = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        category = _clean_text(item.get("category"), MAX_CATEGORY_LEN)
        limit = _clean_amount(item.get("limit"))
        if category and limit is not None:
            merged[category.casefold()] = {"category": category, "limit": limit}
    return sorted(merged.values(), key=lambda b: b["category"].casefold())


def empty_ledger():
    return {"version": LEDGER_VERSION, "transactions": [], "budgets": [], "recurring": []}


def normalize_ledger(data):
    """Return (ledger, changed). Repairs missing or corrupt parts, drops records
    that can't be salvaged, and removes double-posted recurring entries. A bare
    list is read as a list of transactions (Hariku V1's finance_data.json)."""
    if isinstance(data, list):
        source = {"transactions": data}
    elif isinstance(data, dict):
        source = data
    else:
        source = {}
    ledger = {k: v for k, v in source.items()
              if k not in ("version", "transactions", "budgets", "recurring")}
    ledger["version"] = LEDGER_VERSION

    transactions, seen = [], set()
    raw_txs = source.get("transactions")
    for item in raw_txs if isinstance(raw_txs, list) else []:
        tx = normalize_transaction(item)
        if tx is None:
            continue
        if tx["id"] in seen:
            if tx["id"].startswith("rec-"):
                continue  # the same recurring occurrence posted twice
            tx["id"] = new_id()
        seen.add(tx["id"])
        transactions.append(tx)
    ledger["transactions"] = transactions

    ledger["budgets"] = _normalize_budgets(source.get("budgets"))

    rules, rule_ids = [], set()
    raw_rules = source.get("recurring")
    for item in raw_rules if isinstance(raw_rules, list) else []:
        rule = normalize_rule(item)
        if rule is None:
            continue
        if rule["id"] in rule_ids:
            rule["id"] = new_id()
        rule_ids.add(rule["id"])
        rules.append(rule)
    ledger["recurring"] = rules
    return ledger, ledger != data


def normalize_settings(data):
    data = data if isinstance(data, dict) else {}
    settings = dict(data)
    symbol = data.get("currency_symbol", DEFAULT_SYMBOL)
    settings["currency_symbol"] = _clean_text(symbol, 8) if isinstance(symbol, str) else DEFAULT_SYMBOL
    settings["reminder_enabled"] = data.get("reminder_enabled") is True
    time_str = data.get("reminder_time")
    settings["reminder_time"] = time_str if is_valid_time(time_str) else DEFAULT_REMINDER_TIME
    last = data.get("last_reminder_date")
    settings["last_reminder_date"] = last if _is_iso(last) else ""
    return settings


def is_valid_time(value):
    return isinstance(value, str) and bool(_TIME_RE.match(value))


def parse_time(text):
    """'8:05', '08:05' or '8.05' -> '08:05' (24-hour), else None."""
    if not isinstance(text, str):
        return None
    m = re.match(r"^\s*([0-9]{1,2})[:.]([0-9]{2})\s*$", text)
    if not m:
        return None
    value = f"{int(m.group(1)):02d}:{m.group(2)}"
    return value if is_valid_time(value) else None


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
def make_transaction(tx_type, amount, category, description, date,
                     tx_id=None, recurring_id=None, now=None):
    tx = normalize_transaction({
        "id": tx_id or new_id(), "type": tx_type, "amount": amount,
        "category": category, "description": description, "date": date,
        "created": (now or datetime.datetime.now()).isoformat(timespec="seconds"),
    })
    if tx is None:
        raise ValueError("invalid transaction")
    if recurring_id:
        tx["recurring_id"] = recurring_id
    return tx


def find_transaction(ledger, tx_id):
    for tx in ledger["transactions"]:
        if tx["id"] == tx_id:
            return tx
    return None


def add_transaction(ledger, tx):
    ledger["transactions"].append(tx)
    return tx


def update_transaction(ledger, tx_id, values):
    """Apply edited fields (type, amount, category, description, date)."""
    tx = find_transaction(ledger, tx_id)
    if tx is None:
        return None
    merged = dict(tx)
    for key in ("type", "amount", "category", "description", "date"):
        if key in values:
            merged[key] = values[key]
    cleaned = normalize_transaction(merged)
    if cleaned is None:
        raise ValueError("invalid transaction")
    tx.clear()
    tx.update(cleaned)
    return tx


def delete_transaction(ledger, tx_id):
    for i, tx in enumerate(ledger["transactions"]):
        if tx["id"] == tx_id:
            return ledger["transactions"].pop(i)
    return None


def _sort_key(tx):
    return (tx["date"], tx.get("created", ""))


def filter_transactions(transactions, month=None, category=None):
    """Newest first. `month` is 'YYYY-MM'; `category` matches case-insensitively
    ('' means uncategorized); None means no filter."""
    wanted = category.casefold() if category is not None else None
    rows = [t for t in transactions
            if (not month or t["date"].startswith(month))
            and (wanted is None or t["category"].casefold() == wanted)]
    rows.sort(key=_sort_key, reverse=True)
    return rows


def months_in(transactions, extra=()):
    months = {t["date"][:7] for t in transactions}
    months.update(m for m in extra if m)
    return sorted(months, reverse=True)


def _unique_sorted(names):
    seen = {}
    for name in names:
        if name and name.casefold() not in seen:
            seen[name.casefold()] = name
    return sorted(seen.values(), key=str.casefold)


def categories_in(transactions):
    """Categories used in these transactions, including '' if any is blank."""
    names = _unique_sorted(t["category"] for t in transactions)
    if any(not t["category"] for t in transactions):
        names.append("")
    return names


def list_categories(ledger, defaults=()):
    """Every known category (used, budgeted, recurring, defaults), sorted.
    The spelling already used in the data wins over a default."""
    names = [t["category"] for t in ledger["transactions"]]
    names += [b["category"] for b in ledger["budgets"]]
    names += [r["category"] for r in ledger["recurring"]]
    names += list(defaults)
    return _unique_sorted(names)


# --------------------------------------------------------------------------- #
# Summaries
# --------------------------------------------------------------------------- #
def summarize(transactions, prefix=""):
    income = expense = count = 0
    for tx in transactions:
        if prefix and not tx["date"].startswith(prefix):
            continue
        if tx["type"] == "income":
            income += tx["amount"]
        else:
            expense += tx["amount"]
        count += 1
    return {"income": income, "expense": expense, "net": income - expense, "count": count}


def summary_report(ledger, today):
    txs = ledger["transactions"]
    everything = summarize(txs)
    return {"today": summarize(txs, today),
            "month": summarize(txs, today[:7]),
            "all": everything,
            "balance": everything["net"]}


# --------------------------------------------------------------------------- #
# Budgets (monthly, per category, expenses only)
# --------------------------------------------------------------------------- #
def _find_budget(ledger, category):
    key = (category or "").casefold()
    for b in ledger["budgets"]:
        if b["category"].casefold() == key:
            return b
    return None


def get_budget(ledger, category):
    budget = _find_budget(ledger, category)
    return budget["limit"] if budget else None


def set_budget(ledger, category, limit, old_category=None):
    category = _clean_text(category, MAX_CATEGORY_LEN)
    limit = _clean_amount(limit)
    if not category or limit is None:
        raise ValueError("invalid budget")
    drop = {category.casefold()}
    if old_category:
        drop.add(old_category.casefold())
    budgets = [b for b in ledger["budgets"] if b["category"].casefold() not in drop]
    budgets.append({"category": category, "limit": limit})
    ledger["budgets"] = sorted(budgets, key=lambda b: b["category"].casefold())
    return ledger["budgets"]


def remove_budget(ledger, category):
    key = (category or "").casefold()
    before = len(ledger["budgets"])
    ledger["budgets"] = [b for b in ledger["budgets"] if b["category"].casefold() != key]
    return len(ledger["budgets"]) < before


def spent_in_month(transactions, month, category):
    key = (category or "").casefold()
    return sum(t["amount"] for t in transactions
               if t["type"] == "expense" and t["date"].startswith(month)
               and t["category"].casefold() == key)


def budget_percent(used, limit):
    """Whole percent, rounded down, so 100% only shows once the limit is reached."""
    return used * 100 // limit if limit else 0


def budget_usage(ledger, month):
    """Budgeted categories first (alphabetical), then categories with spending
    but no budget (limit None)."""
    spent = {}
    names = {}
    for t in ledger["transactions"]:
        if t["type"] == "expense" and t["date"].startswith(month):
            key = t["category"].casefold()
            spent[key] = spent.get(key, 0) + t["amount"]
            names.setdefault(key, t["category"])
    rows = []
    budgeted = set()
    for b in ledger["budgets"]:
        key = b["category"].casefold()
        budgeted.add(key)
        used = spent.get(key, 0)
        rows.append({"category": b["category"], "limit": b["limit"], "used": used,
                     "percent": budget_percent(used, b["limit"])})
    extra = [{"category": names[k], "limit": None, "used": v, "percent": None}
             for k, v in spent.items() if k not in budgeted]
    extra.sort(key=lambda r: r["category"].casefold())
    return rows + extra


def budget_crossings(used_before, used_after, limit):
    """Thresholds (80, 100) that spending crossed going from before to after."""
    if not limit:
        return []
    return [t for t in BUDGET_THRESHOLDS
            if used_before * 100 < t * limit <= used_after * 100]


def budget_warning(ledger, category, month, used_before):
    """Describe the highest budget threshold a change just crossed, or None.
    The category is named the way the budget spells it."""
    budget = _find_budget(ledger, category)
    if not budget:
        return None
    limit = budget["limit"]
    used = spent_in_month(ledger["transactions"], month, category)
    crossed = budget_crossings(used_before, used, limit)
    if not crossed:
        return None
    return {"category": budget["category"], "limit": limit, "used": used,
            "percent": budget_percent(used, limit), "threshold": max(crossed)}


# --------------------------------------------------------------------------- #
# Recurring transactions
# --------------------------------------------------------------------------- #
def _day_after(iso):
    try:
        return (_to_date(iso) + datetime.timedelta(days=1)).isoformat()
    except (ValueError, OverflowError):
        return None


def _step(rule):
    n = rule.get("interval", 1)
    freq = rule["frequency"]
    if freq == "daily":
        return "days", n
    if freq == "weekly":
        return "days", 7 * n
    if freq == "monthly":
        return "months", n
    return "months", 12 * n


def next_occurrence(rule, current):
    """The occurrence after `current` (an occurrence date), or None when the
    schedule runs past year 9999. Months keep the start date's day, clamped."""
    unit, size = _step(rule)
    day = _to_date(current)
    try:
        if unit == "days":
            result = day + datetime.timedelta(days=size)
        else:
            result = add_months(day, size, _to_date(rule["start_date"]).day)
    except OverflowError:
        return None
    return result.isoformat() if result else None


def first_occurrence_on_or_after(rule, target):
    """The first occurrence on or after `target` ('YYYY-MM-DD'), or None."""
    start = _to_date(rule["start_date"])
    goal = _to_date(target)
    if goal <= start:
        return start.isoformat()
    unit, size = _step(rule)
    try:
        if unit == "days":
            k = -(-(goal - start).days // size)
            return (start + datetime.timedelta(days=k * size)).isoformat()
        months = (goal.year - start.year) * 12 + (goal.month - start.month)
        k = max(0, months // size)
        while True:
            candidate = add_months(start, k * size, start.day)
            if candidate is None:
                return None
            if candidate >= goal:
                return candidate.isoformat()
            k += 1
    except OverflowError:
        return None


def make_rule(tx_type, amount, category, description, frequency, interval,
              start_date, active=True, rule_id=None):
    rule = normalize_rule({
        "id": rule_id or new_id(), "type": tx_type, "amount": amount,
        "category": category, "description": description, "frequency": frequency,
        "interval": interval, "start_date": start_date, "next_date": start_date,
        "last_posted": "", "active": active,
    })
    if rule is None:
        raise ValueError("invalid recurring rule")
    return rule


def find_rule(ledger, rule_id):
    for rule in ledger["recurring"]:
        if rule["id"] == rule_id:
            return rule
    return None


def _reschedule(rule, not_before=None):
    """Point next_date at the first occurrence after the last posted one (and on
    or after `not_before`), so an edit never re-posts past dates."""
    after = _day_after(rule["last_posted"]) if rule["last_posted"] else rule["start_date"]
    if not_before and (after is None or not_before > after):
        after = not_before
    rule["next_date"] = (first_occurrence_on_or_after(rule, after) if after else None) or ""
    if not rule["next_date"]:
        rule["active"] = False


def update_rule(ledger, rule_id, values, today):
    """Edit a rule. Changing the schedule re-plans the next date without going
    back over dates this rule already posted; resuming skips missed dates."""
    rule = find_rule(ledger, rule_id)
    if rule is None:
        return None
    schedule_keys = ("frequency", "interval", "start_date")
    old_schedule = tuple(rule[k] for k in schedule_keys)
    was_active = rule["active"]
    merged = dict(rule)
    merged.update({k: v for k, v in values.items()
                   if k in ("type", "amount", "category", "description", "active") + schedule_keys})
    cleaned = normalize_rule(merged)
    if cleaned is None:
        raise ValueError("invalid recurring rule")
    rule.clear()
    rule.update(cleaned)
    resumed = rule["active"] and not was_active
    if resumed or tuple(rule[k] for k in schedule_keys) != old_schedule:
        _reschedule(rule, not_before=today if resumed else None)
    return rule


def set_rule_active(ledger, rule_id, active, today):
    """Pause or resume. Resuming skips the dates missed while paused."""
    rule = find_rule(ledger, rule_id)
    if rule is None:
        return None
    rule["active"] = bool(active)
    if active:
        _reschedule(rule, not_before=today)
    return rule


def delete_rule(ledger, rule_id):
    """Remove a rule. Transactions it already posted stay in the history."""
    for i, rule in enumerate(ledger["recurring"]):
        if rule["id"] == rule_id:
            return ledger["recurring"].pop(i)
    return None


def recurring_tx_id(rule_id, date):
    return f"rec-{rule_id}-{date}"


def process_recurring(ledger, today, now=None, max_per_rule=MAX_CATCH_UP):
    """Post every due occurrence up to and including `today`.

    Returns (posted transactions, changed). Idempotent: each occurrence has a
    fixed id, and next_date moves past it in the same saved ledger, so running
    again (or after a restart) never posts it twice."""
    existing = {t["id"] for t in ledger["transactions"]}
    posted = []
    changed = False
    for rule in ledger["recurring"]:
        if not rule.get("active", True) or not rule.get("next_date"):
            continue
        due = rule["next_date"]
        count = 0
        while due and due <= today and count < max_per_rule:
            tx_id = recurring_tx_id(rule["id"], due)
            if tx_id not in existing:
                tx = make_transaction(rule["type"], rule["amount"], rule["category"],
                                      rule["description"], due, tx_id=tx_id,
                                      recurring_id=rule["id"], now=now)
                ledger["transactions"].append(tx)
                existing.add(tx_id)
                posted.append(tx)
            rule["last_posted"] = due
            due = next_occurrence(rule, due)
            count += 1
            changed = True
        if due is None:
            rule["next_date"] = ""
            rule["active"] = False
        else:
            rule["next_date"] = due
    return posted, changed


# --------------------------------------------------------------------------- #
# Daily reminder
# --------------------------------------------------------------------------- #
def reminder_due(settings, now):
    """True once a day, at or after the chosen time, while enabled."""
    if not settings.get("reminder_enabled"):
        return False
    if settings.get("last_reminder_date") == now.date().isoformat():
        return False
    return now.strftime("%H:%M") >= settings.get("reminder_time", DEFAULT_REMINDER_TIME)


def has_manual_entry_on(transactions, day):
    """Did the user record anything themselves for `day` or on `day`?
    Automatic recurring entries don't count."""
    for tx in transactions:
        if tx.get("recurring_id"):
            continue
        if tx["date"] == day or str(tx.get("created", "")).startswith(day):
            return True
    return False
