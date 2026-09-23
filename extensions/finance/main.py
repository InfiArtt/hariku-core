# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# ============================================================
# Finance — offline income and expense tracking for Hariku V2.
# Entry point: hotkeys, the preferences panel, and the bus handlers that post
# recurring transactions (on startup and when the day changes) and give the
# optional daily reminder. Modules:
#   finance_engine.py - pure logic (parsing, summaries, budgets, schedules)
#   finance_store.py  - persistence, settings, spoken wording, changes
#   finance_ui.py     - dialogs and the preferences panel
# Works fully offline; nothing here touches the network.
# ============================================================
import datetime
import logging

import core.api
import core.hotkeys
import core.preferences
from core.events import bus as core_bus
from core.speech import speak

import finance_engine as engine
import finance_store as store
import finance_ui
from finance_store import _

logger = logging.getLogger(__name__)

EXT_NAME = "Finance"   # fixed, so action ids stay the same in every language

_bus = None
_last_day = None
_panel = None


# --------------------------------------------------------------------------- #
# Hotkey actions
# --------------------------------------------------------------------------- #
def open_finance():
    finance_ui.open_finance_dialog()


def quick_add_expense():
    finance_ui.open_quick_add()


# --------------------------------------------------------------------------- #
# Background work (kept cheap: runs on the UI thread)
# --------------------------------------------------------------------------- #
def process_recurring(today=None):
    posted = store.run_recurring(today=today)
    if posted:
        speak(_("recurring_posted", count=len(posted)))
    return posted


def _check_day(now):
    """Post recurring transactions once per calendar day."""
    global _last_day
    day = now.date().isoformat()
    if day == _last_day:
        return
    _last_day = day
    try:
        process_recurring(today=day)
    except Exception as e:
        logger.error(f"[Finance] Recurring processing failed: {e}")


def _check_reminder(now):
    """At most one disk read a day, and none at all while the reminder is off."""
    settings = store.get_settings()
    if not engine.reminder_due(settings, now):
        return
    day = now.date().isoformat()
    store.update_settings(last_reminder_date=day)
    ledger = store.load_ledger()
    if engine.has_manual_entry_on(ledger["transactions"], day):
        return
    text = _("reminder_text")
    speak(text)
    try:
        core.api.show_toast(_("ext_name"), text)
    except Exception as e:
        logger.debug(f"[Finance] Toast failed: {e}")


def _on_app_startup(*_args, **_kwargs):
    _check_day(datetime.datetime.now())


def _on_minute_tick(now=None, *_args, **_kwargs):
    if not isinstance(now, datetime.datetime):
        now = datetime.datetime.now()
    try:
        _check_day(now)
        _check_reminder(now)
    except Exception as e:
        logger.error(f"[Finance] Minute tick failed: {e}")


_SUBSCRIPTIONS = (
    ("on_app_startup", _on_app_startup),
    ("on_minute_tick", _on_minute_tick),
)


# --------------------------------------------------------------------------- #
# Preferences panel
# --------------------------------------------------------------------------- #
def _create_panel(parent):
    global _panel
    _panel = finance_ui.FinanceSettingsPanel(parent)
    return _panel


def _apply_panel():
    if _panel:
        _panel.ApplyChanges()


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def register(bus):
    global _bus
    _bus = bus or core_bus
    for event, handler in _SUBSCRIPTIONS:
        _bus.subscribe(event, handler)
    # K ("Keuangan") and Shift+K are free in the core and bundled extensions.
    core.hotkeys.register_action(EXT_NAME, "open_finance", _("action_open"),
                                 ord("K"), False, open_finance)
    core.hotkeys.register_action(EXT_NAME, "quick_add_expense", _("action_quick_add"),
                                 ord("K"), False, quick_add_expense, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("Finance extension loaded.")


def teardown():
    global _bus, _last_day, _panel
    bus = _bus or core_bus
    for event, handler in _SUBSCRIPTIONS:
        try:
            bus.unsubscribe(event, handler)
        except Exception as e:
            logger.error(f"[Finance] Could not unsubscribe {event}: {e}")
    _bus = None
    _last_day = None
    _panel = None
    store.reset_cache()
    logger.info("Finance extension unloaded.")
