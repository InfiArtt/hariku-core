# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Finance dialogs. Built from native wx controls for NVDA: every field has a
# StaticText label right before it and the same accessible name, every list row
# is a full sentence, Escape closes, Enter presses the default button. Focus is
# only moved after an explicit action (a saved dialog, Enter, a button), never
# on a selection change, because those fire on every arrow key press.
import wx

import core.api
import core.ui_scale
from core.speech import speak

import finance_engine as engine
import finance_store as store
from finance_store import _

_DIALOG_STYLE = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
_BORDER = 8

# Speak confirmations a moment after focus settles; the screen reader's focus
# announcement would otherwise cut them off.
ANNOUNCE_DELAY_MS = 300


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _plain(label):
    return label.replace("&", "").strip().rstrip(":").strip()


def _apply_appearance(window):
    try:
        core.ui_scale.apply_appearance(window)
    except Exception:
        pass


def _labeled(parent, sizer, label, make, proportion=0, expand=True):
    """Add a label, then the control it names, and give the control the same
    accessible name. Returns (label, control)."""
    text = wx.StaticText(parent, label=label)
    sizer.Add(text, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, proportion, (wx.EXPAND if expand else 0) | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return text, ctrl


def _inline(parent, sizer, label, make):
    """Label and control side by side (used for the filter row)."""
    text = wx.StaticText(parent, label=label)
    sizer.Add(text, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
    return ctrl


def _button(parent, sizer, label, handler, button_id=wx.ID_ANY):
    btn = wx.Button(parent, button_id, label)
    if handler:
        btn.Bind(wx.EVT_BUTTON, handler)
    sizer.Add(btn, 0, wx.RIGHT | wx.TOP, 4)
    return btn


def _save_cancel(dialog, handler):
    sizer = wx.StdDialogButtonSizer()
    ok = wx.Button(dialog, wx.ID_OK, _("btn_save"))
    ok.SetDefault()
    ok.Bind(wx.EVT_BUTTON, handler)
    cancel = wx.Button(dialog, wx.ID_CANCEL, _("btn_cancel"))
    sizer.AddButton(ok)
    sizer.AddButton(cancel)
    sizer.Realize()
    return sizer


def _fit_form(dialog, min_width=400):
    # Fit after the appearance pass so large text still fits.
    _apply_appearance(dialog)
    dialog.Fit()
    width, height = dialog.GetSize()
    dialog.SetMinSize((width, height))
    dialog.SetSize((max(width, min_width), height))
    dialog.CentreOnParent()


def _set_choice(choice, labels, values, current):
    if choice.GetStrings() != labels:
        choice.Set(labels)
    choice.SetSelection(values.index(current) if current in values else 0)


def _current(choice, values):
    index = choice.GetSelection()
    return values[index] if 0 <= index < len(values) else None


def _confirm(parent, message, title):
    style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING
    return wx.MessageBox(message, title, style, parent) == wx.YES


def _show_error(parent, message):
    wx.MessageBox(message, _("err_title"), wx.OK | wx.ICON_ERROR, parent)


def _announce(message, delay=None):
    delay = ANNOUNCE_DELAY_MS if delay is None else delay
    if delay <= 0:
        speak(message)
    else:
        wx.CallLater(delay, speak, message)


def _list_keys(dialog, listbox, on_enter, on_delete):
    """Enter on the list runs on_enter, Delete runs on_delete; other keys pass."""
    def handler(event):
        if wx.Window.FindFocus() is listbox and not event.HasAnyModifiers():
            key = event.GetKeyCode()
            if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                on_enter()
                return
            if key in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
                on_delete()
                return
        event.Skip()
    dialog.Bind(wx.EVT_CHAR_HOOK, handler)


def _parent():
    return getattr(core.api, "main_window_instance", None)


# --------------------------------------------------------------------------- #
# Add / edit a transaction
# --------------------------------------------------------------------------- #
class TransactionDialog(wx.Dialog):
    """Add or edit one transaction. compact=True is the quick "Add expense"
    form: amount, category and description, dated today."""

    def __init__(self, parent, tx=None, compact=False, categories=()):
        if compact:
            title = _("dlg_quick_title")
        else:
            title = _("dlg_edit_title") if tx else _("dlg_add_title")
        super().__init__(parent, title=title, style=_DIALOG_STYLE)
        tx = tx or {}
        self.result = None
        root = wx.BoxSizer(wx.VERTICAL)

        self.type_choice = None
        if not compact:
            self.type_choice = _labeled(self, root, _("lbl_type"), lambda: wx.Choice(
                self, choices=[_("type_expense"), _("type_income")]))[1]
            self.type_choice.SetSelection(1 if tx.get("type") == "income" else 0)

        amount = engine.group_thousands(tx["amount"]) if tx.get("amount") else ""
        self.amount = _labeled(self, root, _("lbl_amount"),
                               lambda: wx.TextCtrl(self, value=amount))[1]
        self.category = _labeled(self, root, _("lbl_category"), lambda: wx.ComboBox(
            self, value=tx.get("category", ""), choices=list(categories),
            style=wx.CB_DROPDOWN))[1]
        self.description = _labeled(self, root, _("lbl_description"), lambda: wx.TextCtrl(
            self, value=tx.get("description", "")))[1]

        self.date = None
        if not compact:
            self.date = _labeled(self, root, _("lbl_date"), lambda: wx.TextCtrl(
                self, value=tx.get("date") or engine.today_iso()))[1]

        root.Add(_save_cancel(self, self._on_save), 0, wx.ALIGN_RIGHT | wx.ALL, _BORDER)
        self.SetSizer(root)
        _fit_form(self)
        (self.type_choice or self.amount).SetFocus()

    def _on_save(self, event=None):
        amount = engine.parse_amount(self.amount.GetValue())
        if amount is None:
            _show_error(self, _("err_amount"))
            self.amount.SetFocus()
            return
        date = engine.today_iso()
        if self.date is not None:
            date = engine.parse_date(self.date.GetValue())
            if date is None:
                _show_error(self, _("err_date", today=engine.today_iso()))
                self.date.SetFocus()
                return
        income = self.type_choice is not None and self.type_choice.GetSelection() == 1
        self.result = {
            "type": "income" if income else "expense",
            "amount": amount,
            "category": " ".join(self.category.GetValue().split()) or _("category_other"),
            "description": self.description.GetValue().strip(),
            "date": date,
        }
        self.EndModal(wx.ID_OK)


# --------------------------------------------------------------------------- #
# Main Finance window
# --------------------------------------------------------------------------- #
class FinanceDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("finance_title"), size=(700, 600), style=_DIALOG_STYLE)
        self.ledger = engine.empty_ledger()
        self._summary_lines = []
        self._row_ids = []
        self._months = [None]
        self._categories = [None]
        root = wx.BoxSizer(wx.VERTICAL)

        self.summary = _labeled(self, root, _("lbl_summary"), lambda: wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 120)))[1]

        filters = wx.BoxSizer(wx.HORIZONTAL)
        self.month_choice = _inline(self, filters, _("lbl_filter_month"), lambda: wx.Choice(self))
        self.category_choice = _inline(self, filters, _("lbl_filter_category"),
                                       lambda: wx.Choice(self))
        root.Add(filters, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)

        self.list_label, self.list = _labeled(
            self, root, _("lbl_transactions", count=0),
            lambda: wx.ListBox(self, style=wx.LB_SINGLE), proportion=1)

        buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_add = _button(self, buttons, _("btn_add"), self.on_add)
        _button(self, buttons, _("btn_edit"), self.on_edit)
        _button(self, buttons, _("btn_delete"), self.on_delete)
        _button(self, buttons, _("btn_budgets"), self.on_budgets)
        _button(self, buttons, _("btn_recurring"), self.on_recurring)
        _button(self, buttons, _("btn_close"), None, wx.ID_CANCEL)
        self.btn_add.SetDefault()
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.SetMinSize((520, 460))

        self.month_choice.Bind(wx.EVT_CHOICE, self._on_filter)
        self.category_choice.Bind(wx.EVT_CHOICE, self._on_filter)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_edit)
        _list_keys(self, self.list, self.on_edit, self.on_delete)

        self.refresh()
        _apply_appearance(self)
        self.Layout()
        self.CentreOnParent()
        self.list.SetFocus()

    # -- data -> controls ---------------------------------------------------- #
    def refresh(self, select_id=None, select_index=None):
        self.ledger = store.load_ledger()
        today = engine.today_iso()
        report = engine.summary_report(self.ledger, today)
        money = store.money
        self._summary_lines = [
            _("summary_balance", balance=money(report["balance"])),
            _("summary_today", income=money(report["today"]["income"]),
              expense=money(report["today"]["expense"])),
            _("summary_month", month=store.month_label(today[:7]),
              income=money(report["month"]["income"]), expense=money(report["month"]["expense"])),
            _("summary_all", income=money(report["all"]["income"]),
              expense=money(report["all"]["expense"])),
        ]
        self.SetTitle(_("finance_title_balance", balance=money(report["balance"])))
        self._fill_filters(today)
        self._fill_list(select_id, select_index)

    def _fill_filters(self, today):
        month = _current(self.month_choice, self._months)
        category = _current(self.category_choice, self._categories)
        txs = self.ledger["transactions"]
        self._months = [None] + engine.months_in(txs, extra=[today[:7]])
        self._categories = [None] + engine.categories_in(txs)
        _set_choice(self.month_choice,
                    [_("all_months")] + [store.month_label(m) for m in self._months[1:]],
                    self._months, month)
        _set_choice(self.category_choice,
                    [_("all_categories")] + [store.category_label(c) for c in self._categories[1:]],
                    self._categories, category)

    def _fill_list(self, select_id=None, select_index=None):
        month = _current(self.month_choice, self._months)
        category = _current(self.category_choice, self._categories)
        rows = engine.filter_transactions(self.ledger["transactions"], month, category)
        target = select_id or self.selected_id()
        self._row_ids = [t["id"] for t in rows]
        self.list.Set([store.transaction_row(t) for t in rows] or [_("no_transactions")])
        label = _("lbl_transactions", count=len(rows))
        self.list_label.SetLabel(label)
        self.list.SetName(_plain(label))
        if target in self._row_ids:
            index = self._row_ids.index(target)
        else:
            index = select_index or 0
        self.list.SetSelection(max(0, min(index, self.list.GetCount() - 1)))
        shown = engine.summarize(rows)
        lines = self._summary_lines + [_("summary_shown", count=len(rows),
                                         income=store.money(shown["income"]),
                                         expense=store.money(shown["expense"]))]
        self.summary.SetValue("\n".join(lines))

    def selected_id(self):
        index = self.list.GetSelection()
        return self._row_ids[index] if 0 <= index < len(self._row_ids) else None

    def _selected_tx(self):
        tx_id = self.selected_id()
        return engine.find_transaction(self.ledger, tx_id) if tx_id else None

    # -- events -------------------------------------------------------------- #
    def _on_filter(self, event=None):
        # Selection events fire on every arrow press: rebuild the list only.
        self._fill_list()

    def on_add(self, event=None):
        dlg = TransactionDialog(self, categories=store.all_categories(self.ledger))
        try:
            if dlg.ShowModal() != wx.ID_OK or not dlg.result:
                return
            tx, message = store.save_transaction(dlg.result)
        finally:
            dlg.Destroy()
        self._after_save(tx, message)

    def on_edit(self, event=None):
        tx = self._selected_tx()
        if tx is None:
            speak(_("nothing_selected"))
            return
        dlg = TransactionDialog(self, tx=tx, categories=store.all_categories(self.ledger))
        try:
            if dlg.ShowModal() != wx.ID_OK or not dlg.result:
                return
            saved, message = store.save_transaction(dlg.result, tx_id=tx["id"])
        finally:
            dlg.Destroy()
        self._after_save(saved, message)

    def _after_save(self, tx, message):
        if tx is None:
            _show_error(self, message)
            return
        self.refresh(select_id=tx["id"])
        self.list.SetFocus()
        _announce(message)

    def on_delete(self, event=None):
        tx = self._selected_tx()
        if tx is None:
            speak(_("nothing_selected"))
            return
        index = self.list.GetSelection()
        if not _confirm(self, _("confirm_delete", row=store.transaction_row(tx)),
                        _("confirm_delete_title")):
            return
        removed, message = store.delete_transaction(tx["id"])
        if removed is None:
            _show_error(self, message)
            return
        self.refresh(select_index=index)
        self.list.SetFocus()
        _announce(message)

    def on_budgets(self, event=None):
        dlg = BudgetsDialog(self)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        self.refresh()

    def on_recurring(self, event=None):
        dlg = RecurringDialog(self)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        self.refresh()


# --------------------------------------------------------------------------- #
# Budgets
# --------------------------------------------------------------------------- #
class BudgetEditDialog(wx.Dialog):
    def __init__(self, parent, item=None, categories=()):
        super().__init__(parent, title=_("dlg_budget_title"), style=_DIALOG_STYLE)
        item = item or {}
        self.result = None
        root = wx.BoxSizer(wx.VERTICAL)
        self.category = _labeled(self, root, _("lbl_category"), lambda: wx.ComboBox(
            self, value=item.get("category", ""), choices=list(categories),
            style=wx.CB_DROPDOWN))[1]
        limit = engine.group_thousands(item["limit"]) if item.get("limit") else ""
        self.limit = _labeled(self, root, _("lbl_budget_limit"),
                              lambda: wx.TextCtrl(self, value=limit))[1]
        root.Add(_save_cancel(self, self._on_save), 0, wx.ALIGN_RIGHT | wx.ALL, _BORDER)
        self.SetSizer(root)
        _fit_form(self, min_width=360)
        (self.limit if item.get("category") else self.category).SetFocus()

    def _on_save(self, event=None):
        category = " ".join(self.category.GetValue().split())
        if not category:
            _show_error(self, _("err_category"))
            self.category.SetFocus()
            return
        limit = engine.parse_amount(self.limit.GetValue())
        if limit is None:
            _show_error(self, _("err_limit"))
            self.limit.SetFocus()
            return
        self.result = (category, limit)
        self.EndModal(wx.ID_OK)


class BudgetsDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("budgets_title"), size=(580, 440), style=_DIALOG_STYLE)
        self.month = engine.today_iso()[:7]
        self.ledger = engine.empty_ledger()
        self._items = []
        root = wx.BoxSizer(wx.VERTICAL)
        self.list = _labeled(self, root, _("lbl_budgets", month=store.month_label(self.month)),
                             lambda: wx.ListBox(self, style=wx.LB_SINGLE), proportion=1)[1]
        buttons = wx.WrapSizer(wx.HORIZONTAL)
        btn_set = _button(self, buttons, _("btn_set_budget"), self.on_add)
        _button(self, buttons, _("btn_edit"), self.on_edit)
        _button(self, buttons, _("btn_remove"), self.on_remove)
        _button(self, buttons, _("btn_close"), None, wx.ID_CANCEL)
        btn_set.SetDefault()
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.SetMinSize((420, 320))
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_edit)
        _list_keys(self, self.list, self.on_edit, self.on_remove)
        self.refresh()
        _apply_appearance(self)
        self.Layout()
        self.CentreOnParent()
        self.list.SetFocus()

    def refresh(self, select_category=None, select_index=None):
        self.ledger = store.load_ledger()
        previous = self.selected()
        self._items = engine.budget_usage(self.ledger, self.month)
        self.list.Set([store.budget_row(i) for i in self._items] or [_("no_budgets")])
        wanted = (select_category or (previous or {}).get("category") or "").casefold()
        names = [i["category"].casefold() for i in self._items]
        index = names.index(wanted) if wanted in names else (select_index or 0)
        self.list.SetSelection(max(0, min(index, self.list.GetCount() - 1)))

    def selected(self):
        index = self.list.GetSelection()
        return self._items[index] if 0 <= index < len(self._items) else None

    def on_add(self, event=None):
        self._edit(None)

    def on_edit(self, event=None):
        item = self.selected()
        if item is None:
            speak(_("nothing_selected_budget"))
            return
        self._edit(item)

    def _edit(self, item):
        dlg = BudgetEditDialog(self, item, categories=store.all_categories(self.ledger))
        try:
            if dlg.ShowModal() != wx.ID_OK or not dlg.result:
                return
            category, limit = dlg.result
        finally:
            dlg.Destroy()
        old = item["category"] if item and item["limit"] is not None else None
        ok, message = store.save_budget(category, limit, old_category=old)
        if not ok:
            _show_error(self, message)
            return
        self.refresh(select_category=category)
        self.list.SetFocus()
        _announce(message)

    def on_remove(self, event=None):
        item = self.selected()
        if item is None:
            speak(_("nothing_selected_budget"))
            return
        category = store.category_label(item["category"])
        if item["limit"] is None:
            speak(_("no_budget_to_remove", category=category))
            return
        index = self.list.GetSelection()
        if not _confirm(self, _("confirm_remove_budget", category=category),
                        _("confirm_remove_budget_title")):
            return
        ok, message = store.remove_budget(item["category"])
        if not ok:
            _show_error(self, message)
            return
        self.refresh(select_index=index)
        self.list.SetFocus()
        _announce(message)


# --------------------------------------------------------------------------- #
# Recurring transactions
# --------------------------------------------------------------------------- #
class RecurringEditDialog(wx.Dialog):
    def __init__(self, parent, rule=None, categories=()):
        title = _("dlg_recurring_edit") if rule else _("dlg_recurring_add")
        super().__init__(parent, title=title, style=_DIALOG_STYLE)
        rule = rule or {}
        self.result = None
        root = wx.BoxSizer(wx.VERTICAL)

        self.type_choice = _labeled(self, root, _("lbl_type"), lambda: wx.Choice(
            self, choices=[_("type_expense"), _("type_income")]))[1]
        self.type_choice.SetSelection(1 if rule.get("type") == "income" else 0)
        amount = engine.group_thousands(rule["amount"]) if rule.get("amount") else ""
        self.amount = _labeled(self, root, _("lbl_amount"),
                               lambda: wx.TextCtrl(self, value=amount))[1]
        self.category = _labeled(self, root, _("lbl_category"), lambda: wx.ComboBox(
            self, value=rule.get("category", ""), choices=list(categories),
            style=wx.CB_DROPDOWN))[1]
        self.description = _labeled(self, root, _("lbl_description"), lambda: wx.TextCtrl(
            self, value=rule.get("description", "")))[1]

        self.freq_choice = _labeled(self, root, _("lbl_frequency"), lambda: wx.Choice(
            self, choices=[_("freq_" + f) for f in engine.FREQUENCIES]))[1]
        frequency = rule.get("frequency", "monthly")
        self.freq_choice.SetSelection(engine.FREQUENCIES.index(frequency))
        self.interval_label, self.interval = _labeled(
            self, root, _("lbl_interval_" + frequency),
            lambda: wx.SpinCtrl(self, min=1, max=engine.MAX_INTERVAL,
                                initial=rule.get("interval", 1)),
            expand=False)
        self.start = _labeled(self, root, _("lbl_start"), lambda: wx.TextCtrl(
            self, value=rule.get("start_date") or engine.today_iso()))[1]
        self.active = wx.CheckBox(self, label=_("chk_active"))
        self.active.SetValue(rule.get("active", True))
        root.Add(self.active, 0, wx.ALL, _BORDER)

        root.Add(_save_cancel(self, self._on_save), 0, wx.ALIGN_RIGHT | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.freq_choice.Bind(wx.EVT_CHOICE, self._on_frequency)
        _fit_form(self, min_width=420)
        self.type_choice.SetFocus()

    def _frequency(self):
        index = self.freq_choice.GetSelection()
        return engine.FREQUENCIES[index] if 0 <= index < len(engine.FREQUENCIES) else "monthly"

    def _on_frequency(self, event=None):
        # Relabel "Every how many ..." for the chosen unit; focus stays put.
        label = _("lbl_interval_" + self._frequency())
        self.interval_label.SetLabel(label)
        self.interval.SetName(_plain(label))
        self.Layout()

    def _on_save(self, event=None):
        amount = engine.parse_amount(self.amount.GetValue())
        if amount is None:
            _show_error(self, _("err_amount"))
            self.amount.SetFocus()
            return
        start = engine.parse_date(self.start.GetValue())
        if start is None:
            _show_error(self, _("err_date", today=engine.today_iso()))
            self.start.SetFocus()
            return
        self.result = {
            "type": "income" if self.type_choice.GetSelection() == 1 else "expense",
            "amount": amount,
            "category": " ".join(self.category.GetValue().split()) or _("category_other"),
            "description": self.description.GetValue().strip(),
            "frequency": self._frequency(),
            "interval": self.interval.GetValue(),
            "start_date": start,
            "active": self.active.GetValue(),
        }
        self.EndModal(wx.ID_OK)


class RecurringDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("recurring_title"), size=(640, 440), style=_DIALOG_STYLE)
        self.ledger = engine.empty_ledger()
        root = wx.BoxSizer(wx.VERTICAL)
        self.list = _labeled(self, root, _("lbl_recurring"),
                             lambda: wx.ListBox(self, style=wx.LB_SINGLE), proportion=1)[1]
        buttons = wx.WrapSizer(wx.HORIZONTAL)
        btn_add = _button(self, buttons, _("btn_add"), self.on_add)
        _button(self, buttons, _("btn_edit"), self.on_edit)
        _button(self, buttons, _("btn_delete"), self.on_delete)
        _button(self, buttons, _("btn_pause_resume"), self.on_toggle)
        _button(self, buttons, _("btn_close"), None, wx.ID_CANCEL)
        btn_add.SetDefault()
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.SetMinSize((440, 320))
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_edit)
        _list_keys(self, self.list, self.on_edit, self.on_delete)
        self.refresh()
        _apply_appearance(self)
        self.Layout()
        self.CentreOnParent()
        self.list.SetFocus()

    @property
    def rules(self):
        return self.ledger["recurring"]

    def refresh(self, select_id=None, select_index=None):
        previous = self.selected()
        self.ledger = store.load_ledger()
        self.list.Set([store.recurring_row(r) for r in self.rules] or [_("no_recurring")])
        ids = [r["id"] for r in self.rules]
        target = select_id or (previous or {}).get("id")
        index = ids.index(target) if target in ids else (select_index or 0)
        self.list.SetSelection(max(0, min(index, self.list.GetCount() - 1)))

    def selected(self):
        index = self.list.GetSelection()
        return self.rules[index] if 0 <= index < len(self.rules) else None

    def _open_editor(self, rule):
        dlg = RecurringEditDialog(self, rule, categories=store.all_categories(self.ledger))
        try:
            if dlg.ShowModal() != wx.ID_OK or not dlg.result:
                return
            saved, message = store.save_rule(dlg.result, rule_id=rule["id"] if rule else None)
        finally:
            dlg.Destroy()
        if saved is None:
            _show_error(self, message)
            return
        self.refresh(select_id=saved["id"])
        self.list.SetFocus()
        _announce(message)

    def on_add(self, event=None):
        self._open_editor(None)

    def on_edit(self, event=None):
        rule = self.selected()
        if rule is None:
            speak(_("nothing_selected_recurring"))
            return
        self._open_editor(rule)

    def on_delete(self, event=None):
        rule = self.selected()
        if rule is None:
            speak(_("nothing_selected_recurring"))
            return
        index = self.list.GetSelection()
        if not _confirm(self, _("confirm_delete_recurring", row=store.recurring_row(rule)),
                        _("confirm_delete_recurring_title")):
            return
        ok, message = store.delete_rule(rule["id"])
        if not ok:
            _show_error(self, message)
            return
        self.refresh(select_index=index)
        self.list.SetFocus()
        _announce(message)

    def on_toggle(self, event=None):
        rule = self.selected()
        if rule is None:
            speak(_("nothing_selected_recurring"))
            return
        saved, message = store.toggle_rule(rule["id"])
        if saved is None:
            _show_error(self, message)
            return
        # The button keeps focus; the row text now says paused or its next date.
        self.refresh(select_id=saved["id"])
        speak(message)


# --------------------------------------------------------------------------- #
# Preferences panel
# --------------------------------------------------------------------------- #
class FinanceSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        settings = store.get_settings()
        root = wx.BoxSizer(wx.VERTICAL)
        self.symbol = _labeled(self, root, _("lbl_currency"), lambda: wx.TextCtrl(
            self, value=settings["currency_symbol"]), expand=False)[1]
        self.reminder = wx.CheckBox(self, label=_("chk_reminder"))
        self.reminder.SetValue(settings["reminder_enabled"])
        root.Add(self.reminder, 0, wx.ALL, _BORDER)
        self.time = _labeled(self, root, _("lbl_reminder_time"), lambda: wx.TextCtrl(
            self, value=settings["reminder_time"]), expand=False)[1]
        self.SetSizer(root)

    def ApplyChanges(self):
        settings = dict(store.get_settings())
        settings["currency_symbol"] = self.symbol.GetValue().strip()
        settings["reminder_enabled"] = bool(self.reminder.GetValue())
        time_value = engine.parse_time(self.time.GetValue())
        if time_value:
            settings["reminder_time"] = time_value
        else:
            speak(_("err_reminder_time"))
        store.save_settings(settings)


# --------------------------------------------------------------------------- #
# Entry points (hotkey actions)
# --------------------------------------------------------------------------- #
def open_finance_dialog():
    posted = store.run_recurring()
    dlg = FinanceDialog(_parent())
    if posted:
        _announce(_("recurring_posted", count=len(posted)), delay=ANNOUNCE_DELAY_MS * 2)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def open_quick_add():
    ledger = store.load_ledger()
    dlg = TransactionDialog(_parent(), compact=True, categories=store.all_categories(ledger))
    try:
        if dlg.ShowModal() != wx.ID_OK or not dlg.result:
            return
        tx, message = store.save_transaction(dlg.result)
    finally:
        dlg.Destroy()
    if tx is None:
        _show_error(_parent(), message)
        return
    _announce(message)
