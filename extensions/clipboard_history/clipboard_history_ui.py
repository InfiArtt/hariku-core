# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Windows for Clipboard History:
  * HistoryDialog  - filter box, one row per item, the full text of the
                     selected item, and Copy / Pin / Delete / Clear all / Close.
  * SettingsPanel  - the Preferences page.
Every control has a StaticText label right before it and the same accessible
name. Selection changes never move keyboard focus (they fire on every arrow
press); focus only moves after an explicit action such as Enter in the filter
box or Delete.
"""

import time

import wx

import core.ui_scale
from core.i18n import apply_rtl_layout
from core.speech import speak

import clipboard_history_store as store
import clipboard_history_text as text
from clipboard_history_text import _

_BORDER = 8
ANNOUNCE_DELAY_MS = 300      # speak after the screen reader's focus announcement
COUNT_DELAY_MS = 700         # speak the match count once typing pauses


def _plain(label):
    return label.replace("&", "").strip().rstrip(":").strip()


def _labeled(parent, sizer, label, make, proportion=0):
    """A label, then the control it names, which gets the same accessible name."""
    static = wx.StaticText(parent, label=label)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return static, ctrl


def _button(parent, sizer, label, handler, button_id=wx.ID_ANY):
    btn = wx.Button(parent, button_id, label)
    if handler:
        btn.Bind(wx.EVT_BUTTON, handler)
    sizer.Add(btn, 0, wx.RIGHT | wx.TOP, 4)
    return btn


def _confirm(parent, message, title):
    style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING
    return wx.MessageBox(message, title, style, parent) == wx.YES


def announce(message, delay=ANNOUNCE_DELAY_MS):
    """Speak a moment later, so a focus change does not cut the message off.
    Module level, so it still runs after the dialog is gone."""
    wx.CallLater(delay, speak, message)


class HistoryDialog(wx.Dialog):
    """`actions` is main.py's DialogActions: items(), latest(), copy(id),
    toggle_pin(id), delete(id), clear(), is_paused()."""

    def __init__(self, parent, actions):
        title = _("dlg_title_paused") if actions.is_paused() else _("dlg_title")
        super().__init__(parent, title=title, size=(700, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._actions = actions
        self._items = []         # every item, display order
        self._rows = []          # item ids of the visible rows
        self._folded = {}        # item id -> casefolded text, for the filter
        self._count_timer = None
        root = wx.BoxSizer(wx.VERTICAL)

        self.txt_filter = _labeled(self, root, _("lbl_filter"), lambda: wx.TextCtrl(
            self, style=wx.TE_PROCESS_ENTER))[1]
        self.lbl_list, self.list = _labeled(self, root, _("lbl_items", count=0), lambda: wx.ListBox(
            self, style=wx.LB_SINGLE), proportion=3)
        self.txt_full = _labeled(self, root, _("lbl_full_text"), lambda: wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY), proportion=2)[1]

        buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_copy = _button(self, buttons, _("btn_copy"), self.on_copy)
        self.btn_pin = _button(self, buttons, _("btn_pin"), self.on_pin)
        self.btn_delete = _button(self, buttons, _("btn_delete"), self.on_delete)
        self.btn_clear = _button(self, buttons, _("btn_clear"), self.on_clear)
        self.btn_close = _button(self, buttons, _("btn_close"), None, wx.ID_CANCEL)
        self.btn_copy.SetDefault()
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.SetMinSize((480, 420))
        self.SetEscapeId(wx.ID_CANCEL)

        self.txt_filter.Bind(wx.EVT_TEXT, self._on_filter_text)
        self.txt_filter.Bind(wx.EVT_TEXT_ENTER, self._on_filter_enter)
        self.list.Bind(wx.EVT_LISTBOX, self._on_select)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_copy)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        latest = actions.latest()
        self.refresh(select_id=latest["id"] if latest else None)
        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.Layout()
        self.CentreOnParent()
        self.list.SetFocus()

    # -- data -> controls ---------------------------------------------------- #
    def _terms(self):
        return self.txt_filter.GetValue().casefold().split()

    def _matches(self, item, terms):
        if not terms:
            return True
        folded = self._folded.get(item["id"])
        if folded is None:
            folded = self._folded[item["id"]] = item["text"].casefold()
        return all(term in folded for term in terms)

    def refresh(self, select_id=None, select_index=None):
        """Rebuild the rows from the history, keeping the selected item selected.
        Never moves focus."""
        target = select_id or self.selected_id()
        self._items = list(self._actions.items())
        terms = self._terms()
        visible = [i for i in self._items if self._matches(i, terms)]
        self._rows = [i["id"] for i in visible]
        now = time.time()
        if visible:
            labels = [text.row(i, now) for i in visible]
        else:
            labels = [_("no_matches") if self._items else _("empty_history")]
        self.list.Set(labels)
        if terms:
            label = _("lbl_items_filtered", shown=len(visible), total=len(self._items))
        else:
            label = _("lbl_items", count=len(self._items))
        self.lbl_list.SetLabel(label)
        self.list.SetName(_plain(label))
        if target in self._rows:
            index = self._rows.index(target)
        else:
            index = select_index or 0
        self.list.SetSelection(max(0, min(index, self.list.GetCount() - 1)))
        self._show_selected()

    def _show_selected(self):
        item = self.selected_item()
        self.txt_full.ChangeValue(item["text"] if item else "")
        label = _("btn_unpin") if item and item["pinned"] else _("btn_pin")
        if self.btn_pin.GetLabel() != label:
            self.btn_pin.SetLabel(label)
            self.Layout()

    def selected_id(self):
        index = self.list.GetSelection()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def selected_item(self):
        item_id = self.selected_id()
        for item in self._items:
            if item["id"] == item_id:
                return item
        return None

    def _selected_or_say(self):
        item = self.selected_item()
        if item is None:
            speak(_("nothing_selected"))
        return item

    # -- events -------------------------------------------------------------- #
    def _on_select(self, event=None):
        # Fires on every arrow press: update the text box only, focus stays put.
        self._show_selected()

    def _on_filter_text(self, event=None):
        self.refresh()
        if self._count_timer is not None:
            self._count_timer.Stop()
        self._count_timer = wx.CallLater(COUNT_DELAY_MS, self._announce_count)

    def _announce_count(self):
        if not self:
            return      # closed while waiting
        self._count_timer = None
        speak(text.count_text(len(self._rows)) if self._rows else _("no_matches"))

    def _on_filter_enter(self, event=None):
        self.list.SetFocus()

    def _on_char_hook(self, event):
        # Enter copies and Delete deletes, but only on the list; other keys pass.
        if wx.Window.FindFocus() is self.list and not event.HasAnyModifiers():
            key = event.GetKeyCode()
            if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                self.on_copy()
                return
            if key in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
                self.on_delete()
                return
        event.Skip()

    def _item_gone(self):
        self.refresh()
        speak(_("item_gone"))

    def on_copy(self, event=None):
        item = self._selected_or_say()
        if item is None:
            return
        if not self._actions.copy(item["id"]):
            speak(_("copy_failed"))
            return
        if self.IsModal():
            self.EndModal(wx.ID_OK)
        else:
            self.Hide()
        announce(_("copied"))

    def on_pin(self, event=None):
        item = self._selected_or_say()
        if item is None:
            return
        item = self._actions.toggle_pin(item["id"])
        if item is None:
            self._item_gone()
            return
        # The item moves to the top of its group; the selection follows it.
        self.refresh(select_id=item["id"])
        speak(_("pinned") if item["pinned"] else _("unpinned"))

    def on_delete(self, event=None):
        item = self._selected_or_say()
        if item is None:
            return
        if item["pinned"] and not _confirm(
                self, _("confirm_delete_pinned", text=text.preview(item["text"])),
                _("confirm_delete_title")):
            return
        index = self.list.GetSelection()
        if self._actions.delete(item["id"]) is None:
            self._item_gone()
            return
        self.refresh(select_index=index)
        self.list.SetFocus()
        announce(_("deleted"))

    def on_clear(self, event=None):
        unpinned = sum(1 for i in self._actions.items() if not i["pinned"])
        if not unpinned:
            speak(_("nothing_to_clear"))
            return
        if not _confirm(self, _("confirm_clear", count=unpinned), _("confirm_clear_title")):
            return
        _removed, kept = self._actions.clear()
        self.refresh(select_index=0)
        self.list.SetFocus()
        announce(_("cleared_kept", kept=kept) if kept else _("cleared"))

    def Destroy(self):
        if self._count_timer is not None:
            self._count_timer.Stop()
            self._count_timer = None
        return super().Destroy()


class SettingsPanel(wx.Panel):
    def __init__(self, parent, settings):
        super().__init__(parent)
        root = wx.BoxSizer(wx.VERTICAL)
        self.choice_size = _labeled(self, root, _("lbl_size"), lambda: wx.Choice(
            self, choices=[_("size_option", count=n) for n in store.SIZES]))[1]
        limit = settings.get("limit", store.DEFAULT_SIZE)
        self.choice_size.SetSelection(store.SIZES.index(limit) if limit in store.SIZES
                                      else store.SIZES.index(store.DEFAULT_SIZE))

        self.chk_remember = wx.CheckBox(self, label=_("chk_remember"))
        self.chk_remember.SetValue(bool(settings.get("remember")))
        root.Add(self.chk_remember, 0, wx.ALL, _BORDER)
        self.chk_paused = wx.CheckBox(self, label=_("chk_paused"))
        self.chk_paused.SetValue(bool(settings.get("paused")))
        root.Add(self.chk_paused, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, _BORDER)

        # A read-only field rather than a StaticText, so Tab reaches it.
        self.txt_privacy = _labeled(self, root, _("lbl_privacy"), lambda: wx.TextCtrl(
            self, value=_("privacy_note"), size=(-1, 110),
            style=wx.TE_MULTILINE | wx.TE_READONLY), proportion=1)[1]
        self.SetSizer(root)
        core.ui_scale.apply_appearance(self)

    def get_settings(self):
        index = self.choice_size.GetSelection()
        limit = store.SIZES[index] if 0 <= index < len(store.SIZES) else store.DEFAULT_SIZE
        return {"limit": limit, "remember": bool(self.chk_remember.GetValue()),
                "paused": bool(self.chk_paused.GetValue())}
