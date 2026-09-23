# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load the Finance extension through the real loader with real wxPython, run its
hotkey actions, open every dialog, add/edit/delete through the dialogs' own
methods, and browse every list, choice and combo box the way arrow keys do,
checking that focus never leaves the control.

Run by tests/test_finance_ui.py in a separate process, because conftest.py mocks
wx inside the pytest process. The caller points APPDATA at a temporary folder so
the user's real data is never touched. Prints one "OK" line per stage.
"""
import datetime
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the finance check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(180, _watchdog)
_timer.daemon = True
_timer.start()

import wx

app = wx.App(False)

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()

# Record speech and toasts instead of producing them.
import core.speech
spoken = []
core.speech.speak = lambda text, interrupt=False: spoken.append(text)
import core.api
toasts = []
core.api.show_toast = lambda title, message, *a, **k: toasts.append(message)

from ui.main_window import MainWindow
frame = MainWindow(None, title="finance check")
print("OK main_window")

K = ord("K")
PLAIN_K = (K, False, False, False, False)
SHIFT_K = (K, False, True, False, False)
assert PLAIN_K not in core.hotkeys.keybindings, "K is already bound by the core"
assert SHIFT_K not in core.hotkeys.keybindings, "Shift+K is already bound by the core"

import core.extension_manager as em
em.load_unpacked_extension(os.path.join(ROOT, "extensions", "finance"))
assert "finance" in em.LOADED_EXTENSIONS, "Finance extension did not load"
main = em.LOADED_EXTENSIONS["finance"]["module"]
fui = sys.modules["finance_ui"]
store = sys.modules["finance_store"]
engine = sys.modules["finance_engine"]
assert core.hotkeys.keybindings[PLAIN_K][0] == "Finance.open_finance"
assert core.hotkeys.keybindings[SHIFT_K][0] == "Finance.quick_add_expense"
print("OK load")

# Message boxes are native and can't be closed from here: record them instead.
errors = []
confirms = []
fui._show_error = lambda parent, message: errors.append(message)
fui._confirm = lambda parent, message, title: confirms.append(message) or True

TODAY = datetime.date.today()
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TODAY_LABEL = f"{TODAY.day} {MONTHS[TODAY.month - 1]} {TODAY.year}"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def pump(ms=100):
    """Run the event loop for a while so timers (CallLater) fire."""
    loop = wx.GUIEventLoop()
    wx.CallLater(ms, loop.Exit)
    loop.Run()


def wait_for_speech(text, since=0, timeout_ms=3000):
    """Wait until `text` is spoken (in a message after index `since`)."""
    waited = 0
    while not any(text in s for s in spoken[since:]):
        if waited >= timeout_ms:
            raise AssertionError(f"never spoke {text!r}; spoke {spoken[-5:]}")
        pump(100)
        waited += 100
    return next(s for s in reversed(spoken[since:]) if text in s)


def modal_dialogs():
    return [w for w in wx.GetTopLevelWindows() if isinstance(w, wx.Dialog) and w.IsModal()]


def while_modal(action, work, label):
    """Call action(), which shows a modal dialog; work(dialog) runs inside it and
    must close it. A dialog left open fails the check instead of hanging it."""
    problems = []
    seen = []
    state = {"returned": False}

    def guard(dlg):
        if not state["returned"]:
            problems.append(AssertionError(f"{label}: dialog was left open"))
            dlg.EndModal(wx.ID_CANCEL)

    def step(tries=0):
        dialogs = modal_dialogs()
        if not dialogs:
            if tries < 50:
                wx.CallLater(100, step, tries + 1)
            else:
                problems.append(AssertionError(f"{label}: no dialog opened"))
            return
        dlg = dialogs[-1]
        seen.append(type(dlg).__name__)
        try:
            work(dlg)
        except Exception as e:
            problems.append(e)
        wx.CallLater(1500, guard, dlg)

    wx.CallLater(200, step)
    action()
    state["returned"] = True
    if problems:
        raise problems[0]
    assert seen, f"{label}: no dialog opened"
    return seen[0]


def run_and_close(action_id, expected):
    name = while_modal(core.hotkeys.actions[action_id].callback,
                       lambda dlg: dlg.EndModal(wx.ID_CANCEL), action_id)
    assert name == expected, f"{action_id} opened {name}, expected {expected}"


def focus_is(ctrl):
    return wx.Window.FindFocus() is ctrl


def _describe(window):
    if window is None:
        return "nothing (the app is not the foreground window)"
    return f"{type(window).__name__} {window.GetName()!r}"


def browse(ctrl, event_binder, label, after_each=None):
    """Fire the selection event for every item, as arrow keys do, and check that
    focus stays on the control. Returns whether focus could be observed.

    Focus is only observable while this process owns the foreground window; if
    another desktop window takes it mid-check, FindFocus() returns None, which
    is not a finding. Focus on any other window of ours is."""
    ctrl.SetFocus()
    pump(30)
    observable = focus_is(ctrl)
    for i in range(ctrl.GetCount()):
        ctrl.SetSelection(i)
        evt = wx.CommandEvent(event_binder.typeId, ctrl.GetId())
        evt.SetEventObject(ctrl)
        evt.SetInt(i)
        ctrl.GetEventHandler().ProcessEvent(evt)
        wx.Yield()
        if after_each:
            after_each(i)
        if observable:
            now = wx.Window.FindFocus()
            if now is None:
                observable = False
                continue
            assert now is ctrl, (f"focus left {label} at item {i} ({ctrl.GetString(i)!r}) "
                                 f"for {_describe(now)}")
    return observable


focus_checked = []


def browse_all(dlg, controls, label):
    for ctrl, binder, name in controls:
        focus_checked.append(browse(ctrl, binder, f"{label} {name}"))


def row_index(listbox, text):
    for i in range(listbox.GetCount()):
        if text in listbox.GetString(i):
            return i
    raise AssertionError(f"no row containing {text!r}")


# --------------------------------------------------------------------------- #
# Hotkey actions open their dialogs
# --------------------------------------------------------------------------- #
run_and_close("Finance.open_finance", "FinanceDialog")
run_and_close("Finance.quick_add_expense", "TransactionDialog")
print("OK hotkeys")


# Quick add through the hotkey, including a rejected amount first.
def quick_add(dlg):
    assert isinstance(dlg, fui.TransactionDialog)
    assert dlg.type_choice is None and dlg.date is None, "quick add should be compact"
    dlg.amount.SetValue("twenty")
    dlg._on_save()
    assert errors and dlg.result is None, "an invalid amount must keep the dialog open"
    dlg.amount.SetValue("20rb")
    dlg.category.SetValue("Food")
    dlg.description.SetValue("coffee")
    dlg._on_save()


while_modal(core.hotkeys.actions["Finance.quick_add_expense"].callback, quick_add, "quick add")
wait_for_speech("Expense Rp 20.000, Food, saved")
assert len(store.load_ledger()["transactions"]) == 1
print("OK quick_add")

# --------------------------------------------------------------------------- #
# Main window: add, edit, filters, budgets, recurring, delete
# --------------------------------------------------------------------------- #
dlg = fui.FinanceDialog(frame)
dlg.Show()
pump(50)
assert dlg.list.GetString(0) == f"{TODAY_LABEL}, Expense, Food, Rp 20.000, coffee", dlg.list.GetString(0)
assert "Balance: Rp -20.000" in dlg.summary.GetValue()
assert dlg.GetTitle() == "Finance, balance Rp -20.000"
dlg.list.SetFocus()
pump(30)
list_focus_observable = focus_is(dlg.list)


def add_income(d):
    assert isinstance(d, fui.TransactionDialog) and d.type_choice is not None
    assert d.date.GetValue() == TODAY.isoformat(), "the date should default to today"
    browse_all(d, [(d.type_choice, wx.EVT_CHOICE, "type"),
                   (d.category, wx.EVT_COMBOBOX, "category")], "add dialog")
    d.type_choice.SetSelection(1)
    d.amount.SetValue("1,5jt")
    d.category.SetValue("Salary")
    d.date.SetValue("not a date")
    d._on_save()
    assert d.result is None, "an invalid date must keep the dialog open"
    d.date.SetValue(TODAY.isoformat())
    d._on_save()


while_modal(dlg.on_add, add_income, "add")
wait_for_speech("Income Rp 1.500.000, Salary, saved")
assert dlg.list.GetCount() == 2
assert "Income, Salary, Rp 1.500.000" in dlg.list.GetStringSelection()
if list_focus_observable:
    assert focus_is(dlg.list), "focus should return to the list after adding"
print("OK add")

dlg.list.SetSelection(row_index(dlg.list, "Food"))


def edit_food(d):
    assert d.amount.GetValue() == "20.000", d.amount.GetValue()
    assert d.category.GetValue() == "Food"
    d.amount.SetValue("25.000")
    d._on_save()


while_modal(dlg.on_edit, edit_food, "edit")
wait_for_speech("Expense Rp 25.000, Food, updated")
assert "Food, Rp 25.000" in dlg.list.GetStringSelection()
print("OK edit")


# Filters and the history list: arrow through each without losing focus.
def after_category(i):
    category = fui._current(dlg.category_choice, dlg._categories)
    if category:
        rows = [dlg.list.GetString(r) for r in range(dlg.list.GetCount())]
        assert all(category in r for r in rows), (category, rows)


browse(dlg.month_choice, wx.EVT_CHOICE, "month filter")
browse(dlg.category_choice, wx.EVT_CHOICE, "category filter", after_category)
dlg.month_choice.SetSelection(0)
dlg.category_choice.SetSelection(0)
dlg._on_filter()
focus_checked.append(browse(dlg.list, wx.EVT_LISTBOX, "transactions list"))
assert dlg.list.GetCount() == 2
print("OK filters")

# Budgets: set one, see its usage, cross 100% with a new expense.
bd = fui.BudgetsDialog(dlg)
bd.Show()
pump(30)
assert bd.list.GetString(0).startswith("Food: Rp 25.000 spent"), bd.list.GetString(0)


def set_budget(d):
    assert isinstance(d, fui.BudgetEditDialog)
    focus_checked.append(browse(d.category, wx.EVT_COMBOBOX, "budget category"))
    d.category.SetValue("Food")
    d.limit.SetValue("zero")
    d._on_save()
    assert d.result is None, "an invalid limit must keep the dialog open"
    d.limit.SetValue("30rb")
    d._on_save()


while_modal(bd.on_add, set_budget, "set budget")
wait_for_speech("Budget for Food set to Rp 30.000 a month")
assert bd.list.GetString(0) == "Food: Rp 25.000 of Rp 30.000, 83%, Rp 5.000 left", bd.list.GetString(0)
focus_checked.append(browse(bd.list, wx.EVT_LISTBOX, "budgets list"))
bd.Destroy()


def add_snack(d):
    d.amount.SetValue("6rb")
    d.category.SetValue("food")
    d._on_save()


while_modal(dlg.on_add, add_snack, "add over budget")
warning = wait_for_speech("Expense Rp 6.000, food, saved")
assert "Food budget exceeded: Rp 31.000 of Rp 30.000, 103%" in warning, warning

bd = fui.BudgetsDialog(dlg)
bd.Show()
pump(30)
assert bd.list.GetString(0) == "Food: Rp 31.000 of Rp 30.000, 103%, Rp 1.000 over", bd.list.GetString(0)
bd.list.SetSelection(0)
bd.on_remove()
wait_for_speech("Budget for Food removed")
bd.Destroy()
print("OK budgets")

# Recurring: add a monthly rule starting today (posts once), prove it is idempotent.
rd = fui.RecurringDialog(dlg)
rd.Show()
pump(30)
assert rd.list.GetString(0) == "No recurring transactions. Use Add to create one."


def add_rule(d):
    assert isinstance(d, fui.RecurringEditDialog)
    labels = []
    browse_all(d, [(d.type_choice, wx.EVT_CHOICE, "type"),
                   (d.category, wx.EVT_COMBOBOX, "category")], "recurring dialog")
    focus_checked.append(browse(d.freq_choice, wx.EVT_CHOICE, "repeats",
                                lambda i: labels.append(d.interval_label.GetLabel())))
    assert labels == ["&Every how many days:", "&Every how many weeks:",
                      "&Every how many months:", "&Every how many years:"], labels
    assert d.interval.GetName() == "Every how many years"
    d.type_choice.SetSelection(0)
    d.amount.SetValue("Rp 100.000")
    d.category.SetValue("Internet")
    d.description.SetValue("fiber")
    d.freq_choice.SetSelection(engine.FREQUENCIES.index("monthly"))
    d._on_frequency()
    d.interval.SetValue(1)
    d.start.SetValue(TODAY.isoformat())
    d._on_save()


while_modal(rd.on_add, add_rule, "add recurring")
said = wait_for_speech("Recurring Expense Rp 100.000, Internet, saved")
assert "Recurring transactions recorded: 1" in said, said
assert rd.list.GetString(0).startswith("Monthly, Expense, Internet, Rp 100.000, next "), rd.list.GetString(0)
count = len(store.load_ledger()["transactions"])
main._on_app_startup()
main._on_minute_tick(datetime.datetime.now())
main.process_recurring()
store.run_recurring()
assert len(store.load_ledger()["transactions"]) == count, "recurring posted twice"

rd.list.SetSelection(0)
rd.on_toggle()
assert rd.list.GetString(0).endswith("paused"), rd.list.GetString(0)
rd.on_toggle()
assert ", next " in rd.list.GetString(0)


def edit_rule(d):
    assert d.amount.GetValue() == "100.000"
    d.amount.SetValue("150rb")
    d._on_save()


while_modal(rd.on_edit, edit_rule, "edit recurring")
wait_for_speech("Recurring Expense Rp 150.000, Internet, saved")
assert len(store.load_ledger()["transactions"]) == count, "editing re-posted a date"
focus_checked.append(browse(rd.list, wx.EVT_LISTBOX, "recurring list"))
rd.list.SetSelection(0)
rd.on_delete()
wait_for_speech("Recurring transaction deleted")
assert rd.list.GetString(0) == "No recurring transactions. Use Add to create one."
assert len(store.load_ledger()["transactions"]) == count, "deleting a rule removed its history"
rd.Destroy()
print("OK recurring")

# The Budgets and Recurring buttons open modal dialogs too.
while_modal(dlg.on_budgets, lambda d: d.EndModal(wx.ID_CANCEL), "budgets button")
while_modal(dlg.on_recurring, lambda d: d.EndModal(wx.ID_CANCEL), "recurring button")

# Delete a transaction (confirmation is recorded and answered Yes).
dlg.refresh()
before = dlg.list.GetCount()
dlg.list.SetSelection(row_index(dlg.list, "Internet"))
dlg.on_delete()
wait_for_speech("Transaction deleted")
assert confirms and "Internet" in confirms[-1]
assert dlg.list.GetCount() == before - 1
if list_focus_observable:
    assert focus_is(dlg.list), "focus should stay on the list after deleting"

# Enter and Delete on the list go through the dialog's key handler.
if list_focus_observable:
    dlg.list.SetFocus()
    dlg.list.SetSelection(row_index(dlg.list, "Salary"))
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_DELETE)
    mark = len(spoken)
    dlg.GetEventHandler().ProcessEvent(key)
    wait_for_speech("Transaction deleted", since=mark)
    assert all("Salary" not in dlg.list.GetString(i) for i in range(dlg.list.GetCount()))
print("OK delete")

# --------------------------------------------------------------------------- #
# Settings panel and the daily reminder
# --------------------------------------------------------------------------- #
import core.preferences
entry = core.preferences.get_all_panels()["Finance"][0]
holder = wx.Frame(frame)
panel = entry["create"](holder)
assert panel.symbol.GetValue() == "Rp" and not panel.reminder.GetValue()
panel.reminder.SetValue(True)
panel.time.SetValue("7.30")
entry["apply"]()
assert store.get_settings()["reminder_enabled"] is True
assert store.get_settings()["reminder_time"] == "07:30"
panel.time.SetValue("late")
entry["apply"]()
assert store.get_settings()["reminder_time"] == "07:30"
wait_for_speech("the reminder time must look like 20:00")
holder.Destroy()

tomorrow = datetime.datetime.combine(TODAY + datetime.timedelta(days=1), datetime.time(7, 29))
reminder = "Reminder: you haven't recorded any expenses today."
main._on_minute_tick(tomorrow)
assert reminder not in spoken, "reminded before the chosen time"
main._on_minute_tick(tomorrow.replace(minute=31))
assert spoken.count(reminder) == 1 and toasts == [reminder]
main._on_minute_tick(tomorrow.replace(minute=45))
assert spoken.count(reminder) == 1, "reminded twice in one day"
# Today already has entries, so no reminder today.
store.update_settings(last_reminder_date="")
main._on_minute_tick(datetime.datetime.combine(TODAY, datetime.time(23, 59)))
assert spoken.count(reminder) == 1, "reminded although something was recorded today"
print("OK reminder")

# --------------------------------------------------------------------------- #
# Teardown and shutdown
# --------------------------------------------------------------------------- #
dlg.Destroy()
from core.events import bus
main.teardown()
for event, handler in main._SUBSCRIPTIONS:
    assert handler not in bus._listeners.get(event, []), f"{event} still subscribed"
print("OK teardown")
print(f"OK focus ({'checked' if focus_checked and all(focus_checked) else 'not observable here'})")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
