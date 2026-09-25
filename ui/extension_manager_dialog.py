# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The Extension Manager (Extensions, Manage Extensions; Ctrl+X): four tabs, each
with a Search field, the list (Name, Version, Status), a Details box and the
tab's buttons.
  * Installed    - Enable/Disable, Remove (Delete too), Update, Guide (the
                   extension's own guide, core 2.11: ui/guides_dialog.py).
  * Updates      - Update (Enter too), Update all.
  * Available    - Install (Enter too).
  * Incompatible - extensions made for a Hariku older than this one still
                   runs, as in NVDA: Update (when the store has a newer
                   version), Remove.
An extension or update that needs a newer Hariku stays on its tab, says so and
can't be installed; "Check for Hariku updates" appears for it.
core.extension_catalog decides what each tab lists and says.

The store answers on a worker thread, so the window opens at once with the
Installed tab filled; the store's tabs fill in when it answers (the answer is
kept for ten minutes; Refresh asks again). Downloads run on a worker thread
too. Rows never jump while their tab is shown: what happened to one (installed,
updated, removed) shows in its Status, and a tab picks up the new lists when
it's shown next. Every label is created right before its control, and
selecting never moves focus.
"""

import logging
import threading
import time

import wx

import core.extension_catalog as catalog
import core.extension_manager
import core.guides
import core.store
from core.core_panels import _labeled, _speak
from core.i18n import get_translator

_ = get_translator("core")
logger = logging.getLogger(__name__)

REGISTRY_MAX_AGE = 600       # seconds the store's answer is reused
SEARCH_SPEAK_MS = 700        # after typing stops, say how many match

_registry_cache = {"time": 0.0, "entries": None}


def cached_registry():
    """The store's answer from the last ten minutes, or None."""
    if _registry_cache["entries"] and time.time() - _registry_cache["time"] < REGISTRY_MAX_AGE:
        return _registry_cache["entries"]
    return None


def _fetch_worker(done, generation):
    try:
        entries = core.store.fetch_registry()
    except Exception:
        logger.exception("[Extensions] The store's list failed")
        entries = []
    if entries:
        _registry_cache.update(time=time.time(), entries=entries)
    wx.CallAfter(done, generation, entries)


def _download_worker(done, finished, rows):
    results = []
    for row in rows:
        try:
            ok = core.store.download_extension(row["id"], row["download_url"])
        except Exception:
            logger.exception("[Extensions] Download of %s failed", row["id"])
            ok = False
        results.append((row, ok))
        wx.CallAfter(done, row, ok)
    wx.CallAfter(finished, results)


# The buttons of each tab, in Tab order.
BUTTONS = {
    "installed": ("toggle", "uninstall", "update", "guide", "check_core"),
    "updates": ("update", "update_all", "check_core"),
    "available": ("install", "check_core"),
    "incompatible": ("update", "uninstall"),
}


class ExtensionTab(wx.Panel):
    """One tab: Search, the list, Details and the tab's buttons."""

    def __init__(self, parent, dialog, tab):
        super().__init__(parent)
        self.dialog, self.tab = dialog, tab
        self.rows = []            # every row of this tab
        self.shown = []           # the rows matching the search, as listed
        self.pending = None       # newer rows to show when the tab is shown next
        self.state = "ready"      # or "loading" / "failed" (the store's tabs)
        self._search_timer = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.search = _labeled(self, sizer, _("ext_search"), lambda: wx.TextCtrl(self))
        self.search.Bind(wx.EVT_TEXT, self._on_search)

        self.list = _labeled(self, sizer, _("ext_list_label"), lambda: wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN), proportion=1)
        self.list.InsertColumn(0, _("ext_col_name"), width=230)
        self.list.InsertColumn(1, _("ext_col_version"), width=110)
        self.list.InsertColumn(2, _("ext_col_status"), width=300)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_selected)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_selected)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activated)
        self.list.Bind(wx.EVT_LIST_KEY_DOWN, self._on_list_key)

        self.details = _labeled(self, sizer, _("ext_details"), lambda: wx.TextCtrl(
            self, size=(-1, 120), style=wx.TE_MULTILINE | wx.TE_READONLY))

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.buttons = {}
        for key in BUTTONS[tab]:
            button = wx.Button(self, label=_("ext_btn_" + key))
            button.Bind(wx.EVT_BUTTON, lambda evt, k=key: dialog.run(k, self))
            row.Add(button, 0, wx.RIGHT, 8)
            self.buttons[key] = button
        sizer.Add(row, 0, wx.ALL, 10)
        self.SetSizer(sizer)

    # --- Rows ---------------------------------------------------------------------------

    def set_rows(self, rows, state="ready"):
        self.rows, self.state, self.pending = list(rows), state, None
        self.refill()

    def refill(self):
        """List the rows matching the search. The same rows in the same order
        are updated in place (nothing is re-read); otherwise the list is
        rebuilt and the selected extension stays selected when it's still
        there, else the first one is."""
        chosen = self.selected_row()
        shown = catalog.matching(self.rows, self.search.GetValue())
        if [r["id"] for r in shown] == [r["id"] for r in self.shown]:
            self.shown = shown
            for index, row_data in enumerate(shown):
                self._set_cells(index, row_data)
        else:
            self.shown = shown
            self.list.DeleteAllItems()
            for index, row_data in enumerate(shown):
                self.list.InsertItem(index, row_data["name"])
                self._set_cells(index, row_data)
            ids = [r["id"] for r in shown]
            if shown:
                index = ids.index(chosen["id"]) if chosen and chosen["id"] in ids else 0
                self.list.Select(index)
                self.list.Focus(index)
        self.show_details()

    def _set_cells(self, index, row):
        done = self.dialog.done.get(row["id"], "")
        self.list.SetItem(index, 0, row["name"])
        self.list.SetItem(index, 1, catalog.version_text(row, self.tab))
        self.list.SetItem(index, 2, catalog.status_text(row, self.tab, done))

    def update_row(self, ext_id):
        for index, row in enumerate(self.shown):
            if row["id"] == ext_id:
                self._set_cells(index, row)
        self.show_details()

    def selected_row(self):
        index = self.list.GetFirstSelected()
        return self.shown[index] if 0 <= index < len(self.shown) else None

    def show_details(self):
        row = self.selected_row()
        if row:
            text = catalog.details_text(row, self.tab, self.dialog.done.get(row["id"], ""))
        elif self.state == "loading":
            text = _("ext_msg_loading")
        elif self.state == "failed":
            text = _("ext_msg_store_failed")
        elif self.rows and not self.shown:
            text = _("ext_msg_no_match", query=self.search.GetValue().strip())
        elif not self.rows:
            text = _("ext_msg_empty_" + self.tab)
        else:
            text = _("ext_msg_select")
        if self.details.GetValue() != text:
            self.details.SetValue(text)
        self.dialog.update_buttons(self)

    # --- Events -------------------------------------------------------------------------

    def _on_selected(self, event):
        self.show_details()
        event.Skip()

    def _on_activated(self, event):
        if self.tab == "available":
            self.dialog.run("install", self)
        elif self.tab == "updates":
            self.dialog.run("update", self)

    def _on_list_key(self, event):
        if event.GetKeyCode() == wx.WXK_DELETE and "uninstall" in self.buttons:
            self.dialog.run("uninstall", self)
        else:
            event.Skip()

    def _on_search(self, event):
        self.refill()
        if self._search_timer:
            self._search_timer.Stop()
        self._search_timer = wx.CallLater(SEARCH_SPEAK_MS, self._speak_found)
        event.Skip()

    def _speak_found(self):
        self._search_timer = None
        if self and self.search.HasFocus() and self.search.GetValue().strip():
            _speak(_("ext_found", count=len(self.shown)))


class ExtensionManagerDialog(wx.Dialog):
    def __init__(self, parent, tab="installed"):
        super().__init__(parent, title=_("dlg_ext_mgr_title"), size=(840, 580),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.requires_restart = False
        self.done = {}              # ext id -> "installed" / "updated" / "removed" / "failed" / "downloading"
        self.registry = cached_registry()
        self.busy = False
        self._generation = 0
        self._closed = False
        self._guides = {}           # ext id -> whether it has a guide (read once)

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.notebook = wx.Notebook(self)
        self.tabs = {}
        for key in catalog.TABS:
            page = ExtensionTab(self.notebook, self, key)
            self.notebook.AddPage(page, _("ext_tab_" + key))
            self.tabs[key] = page
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_page_changed)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.AddStretchSpacer()
        self.btn_refresh = wx.Button(self, label=_("ext_btn_refresh"))
        self.btn_refresh.Bind(wx.EVT_BUTTON, lambda evt: self.refresh())
        row.Add(self.btn_refresh, 0, wx.RIGHT, 8)
        btn_close = wx.Button(self, wx.ID_CLOSE, _("ext_btn_close"))
        btn_close.Bind(wx.EVT_BUTTON, lambda evt: self._close())
        row.Add(btn_close, 0)
        sizer.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizer(sizer)
        self.SetEscapeId(wx.ID_CLOSE)
        self.Bind(wx.EVT_CLOSE, lambda evt: self._close())

        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)

        self._fill_all()
        if tab in self.tabs:
            self.notebook.SetSelection(catalog.TABS.index(tab))
        if self.registry is None:
            self.refresh()
        self.CentreOnParent()

    # --- Lists --------------------------------------------------------------------------

    def current_tab(self):
        index = self.notebook.GetSelection()
        return self.tabs.get(catalog.TABS[index]) if 0 <= index < len(catalog.TABS) else None

    def _data(self):
        return catalog.build(core.extension_manager.get_installed_extensions_info(),
                             self.registry, core.extension_manager.SYSTEM_EXTENSIONS_DIR,
                             core.extension_manager.LOAD_ERRORS)

    def _fill_all(self, keep_current=False):
        """Give every tab its rows. With keep_current, the tab being shown keeps
        its rows (only their Status changes) and gets the new ones when it's
        shown next."""
        data = self._data()
        self._guides.clear()        # installing or updating may bring one
        store_state = ("loading" if self.registry is None else
                       "failed" if not self.registry else "ready")
        shown = self.current_tab() if keep_current else None
        for key, page in self.tabs.items():
            state = store_state if key in ("updates", "available") else "ready"
            if page is shown:
                page.pending = (data[key], state)
                page.refill()
            else:
                page.set_rows(data[key], state)
            known = bool(self.registry) or key in ("installed", "incompatible")
            self.notebook.SetPageText(catalog.TABS.index(key),
                                      catalog.tab_title(key, len(data[key]) if known else None))

    def _on_page_changed(self, event):
        page = self.current_tab()
        if page is not None and page.pending:
            rows, state = page.pending
            page.set_rows(rows, state)
        event.Skip()

    def refresh(self):
        """Ask the store for its list again (on a worker thread)."""
        self._generation += 1
        self.registry = None
        for key in ("updates", "available"):
            page = self.tabs[key]
            page.set_rows([], "loading")
            self.notebook.SetPageText(catalog.TABS.index(key), catalog.tab_title(key, None))
        self.update_buttons()
        threading.Thread(target=_fetch_worker, args=(self._on_registry, self._generation),
                         daemon=True, name="hariku-store-list").start()

    def _on_registry(self, generation, entries):
        if self._closed or not self or generation != self._generation:
            return
        self.registry = entries
        self._fill_all()
        page = self.current_tab()
        if page is not None and page.tab != "installed":
            if not entries:
                _speak(_("ext_msg_store_failed"))
            else:
                _speak(self.notebook.GetPageText(self.notebook.GetSelection()))

    def update_buttons(self, page=None):
        pages = [page] if page else self.tabs.values()
        for page in pages:
            row = page.selected_row()
            for key, button in page.buttons.items():
                button.Enable(self._can(key, row, page))
                if key == "toggle":
                    label = (_("ext_btn_enable") if row and not row["enabled"]
                             else _("ext_btn_disable"))
                    if button.GetLabel() != label:
                        button.SetLabel(label)
        self.btn_refresh.Enable(not self.busy)

    def _can(self, key, row, page):
        if key == "update_all":
            return not self.busy and bool(self._updatable(page))
        done = self.done.get(row["id"], "") if row else ""
        if not row or done == "removed":
            return False
        if key == "check_core":
            return bool(catalog.waits_for_core(row))
        if key == "toggle":
            return row["installed"]
        if key == "guide":
            return catalog.can_open_guide(row, done, self._has_guide)
        if key == "uninstall":
            return row["installed"] and row["source"] != catalog.BUNDLED
        if key == "update":
            return (not self.busy and catalog.can_update(row)
                    and done not in ("updated", "downloading"))
        if key == "install":
            return (not self.busy and catalog.can_install(row)
                    and done not in ("installed", "downloading"))
        return False

    def _has_guide(self, ext_id):
        if ext_id not in self._guides:
            self._guides[ext_id] = core.guides.has_guide(ext_id)
        return self._guides[ext_id]

    def _updatable(self, page):
        return [r for r in page.rows if catalog.can_update(r)
                and self.done.get(r["id"]) not in ("updated", "downloading", "removed")]

    def _refresh_row(self, ext_id):
        for page in self.tabs.values():
            page.update_row(ext_id)

    # --- Actions ------------------------------------------------------------------------

    def run(self, key, page):
        row = page.selected_row()
        if not self._can(key, row, page):
            return
        getattr(self, "_do_" + key)(row, page)

    def _do_toggle(self, row, page):
        row["enabled"] = not row["enabled"]
        core.extension_manager.toggle_extension(row["id"], row["enabled"])
        self.requires_restart = True
        self._refresh_row(row["id"])
        _speak(_("ext_msg_enabled" if row["enabled"] else "ext_msg_disabled", name=row["name"]))

    def confirm(self, message, title):
        dlg = wx.MessageDialog(self, message, title, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
        try:
            return dlg.ShowModal() == wx.ID_YES
        finally:
            dlg.Destroy()

    def _do_uninstall(self, row, page):
        if not self.confirm(_("ext_msg_uninstall_confirm", name=row["name"]),
                            _("ext_title_uninstall")):
            return
        if core.extension_manager.uninstall_extension(row["id"]):
            self.done[row["id"]] = "removed"
            self.requires_restart = True
            self._refresh_row(row["id"])
            _speak(_("ext_msg_removed", name=row["name"]))
        else:
            wx.MessageBox(_("ext_msg_uninstall_failed"), _("error"), wx.OK | wx.ICON_ERROR, self)

    def _do_guide(self, row, page):
        from ui.guides_dialog import show_guide
        show_guide(self, row["id"])

    def _do_install(self, row, page):
        self._download([row])

    def _do_update(self, row, page):
        self._download([row])

    def _do_update_all(self, row, page):
        rows = self._updatable(page)
        if rows:
            self._download(rows)

    def _do_check_core(self, row, page):
        import core.updater
        threading.Thread(target=core.updater.check_for_updates, args=(True,), daemon=True,
                         name="hariku-core-update").start()

    def _download(self, rows):
        self.busy = True
        for row in rows:
            self.done[row["id"]] = "downloading"
            self._refresh_row(row["id"])
        self.update_buttons()
        if len(rows) == 1:
            _speak(_("ext_msg_downloading", name=rows[0]["name"]))
        else:
            _speak(_("ext_msg_downloading_many", count=len(rows)))
        threading.Thread(target=_download_worker, args=(self._downloaded, self._downloads_finished,
                                                        rows),
                         daemon=True, name="hariku-store-download").start()

    def _downloaded(self, row, ok):
        if self._closed or not self:
            return
        if ok:
            self.done[row["id"]] = "installed" if not row["installed"] else "updated"
            self.requires_restart = True
        else:
            self.done[row["id"]] = "failed"
        self._refresh_row(row["id"])

    def _downloads_finished(self, results):
        if self._closed or not self:
            return
        self.busy = False
        good = [row for row, ok in results if ok]
        bad = [row for row, ok in results if not ok]
        if good:
            self._fill_all(keep_current=True)
        self.update_buttons()
        if len(results) == 1:
            row = results[0][0]
            if good:
                _speak(_("ext_msg_installed" if not row["installed"] else "ext_msg_updated",
                         name=row["name"]))
            else:
                _speak(_("ext_msg_download_failed_one", name=row["name"]))
        else:
            message = (_("ext_msg_updated", name=good[0]["name"]) if len(good) == 1 else
                       _("ext_msg_updated_many", count=len(good)) if good else "")
            if bad:
                message = (message + " " if message else "") + _(
                    "ext_msg_failed_many", names=", ".join(r["name"] for r in bad))
            _speak(message)

    def _close(self):
        self._closed = True
        for page in self.tabs.values():
            if page._search_timer:
                page._search_timer.Stop()
        if self.IsModal():
            self.EndModal(wx.ID_OK)
        else:
            self.Hide()
