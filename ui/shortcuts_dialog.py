# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Every registered keyboard shortcut, laid out like File Explorer (core 2.13):
# a tree of groups on the left and, on the right, a list of what the selected
# one holds. "Hariku" holds the core's groups and "Extensions" one group per
# extension; a folder's groups are added to the tree when it is first opened,
# and the list is virtual, so a row is only made when it is shown. Selecting a
# folder lists its groups, like subfolders; Enter on one opens it. Opened with
# F1 (rebindable via Input Gestures). It used to be one long text.
import wx
from collections import defaultdict

import core.hotkeys as hk
from core.i18n import get_translator

_ = get_translator("core")

# The core's own groups (ui/main_window.py); every other one is an extension's.
CORE_GROUPS = ("Hariku Core", "Calendar Navigation")
CORE_FOLDER, EXTENSIONS_FOLDER = "core", "extensions"


def collect_groups():
    """{group name: [action, ...]} of every registered action, each list in
    description order."""
    groups = defaultdict(list)
    for action in hk.actions.values():
        groups[action.extension_name].append(action)
    for group in groups.values():
        group.sort(key=lambda a: a.description.lower())
    return dict(groups)


def folder_groups(groups, folder):
    """The groups a folder of the tree holds, in order."""
    if folder == CORE_FOLDER:
        return [name for name in CORE_GROUPS if name in groups]
    return sorted((name for name in groups if name not in CORE_GROUPS), key=str.lower)


def keys_text(action):
    """An action's keys as they are said: "Ctrl+Alt+H (global), F5", or
    "Unassigned"."""
    binds = hk.get_current_bindings(action.id)
    if not binds:
        return _("shortcuts_unassigned")
    texts = []
    for b in sorted(binds):
        keys = hk.format_key_name(b[0], b[1], b[2], b[3], b[4])
        texts.append(_("shortcuts_global", keys=keys) if b[5] else keys)
    return ", ".join(texts)


class _RowList(wx.ListCtrl):
    """A virtual report list: rows are (name, keys) pairs, or a callable that
    makes the pair for an index, read only when shown."""

    def __init__(self, parent):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
        self.InsertColumn(0, _("shortcuts_col_name"), width=300)
        self.InsertColumn(1, _("shortcuts_col_keys"), width=200)
        self._count = 0
        self._row = None
        self._cache = {}

    def show(self, count, row):
        self._count, self._row, self._cache = count, row, {}
        self.SetItemCount(count)
        self.Refresh()
        if count:
            self.Select(0)
            self.Focus(0)

    def row(self, index):
        if index not in self._cache:
            self._cache[index] = self._row(index) if self._row and 0 <= index < self._count else ("", "")
        return self._cache[index]

    def OnGetItemText(self, item, column):
        return self.row(item)[column]


class ShortcutsDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("shortcuts_title"), size=(720, 480),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.groups = collect_groups()
        self._loaded = set()          # folders whose groups are in the tree

        panes = wx.BoxSizer(wx.HORIZONTAL)
        left = wx.BoxSizer(wx.VERTICAL)
        left.Add(wx.StaticText(self, label=_("shortcuts_lbl_groups")), 0, wx.BOTTOM, 4)
        self.tree = wx.TreeCtrl(self, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT
                                | wx.TR_SINGLE)
        left.Add(self.tree, 1, wx.EXPAND)
        panes.Add(left, 2, wx.EXPAND | wx.ALL, 8)

        right = wx.BoxSizer(wx.VERTICAL)
        right.Add(wx.StaticText(self, label=_("shortcuts_lbl_list")), 0, wx.BOTTOM, 4)
        self.list = _RowList(self)
        right.Add(self.list, 1, wx.EXPAND)
        panes.Add(right, 3, wx.EXPAND | wx.TOP | wx.RIGHT | wx.BOTTOM, 8)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(panes, 1, wx.EXPAND)
        btn = wx.Button(self, wx.ID_CANCEL, label=_("shortcuts_close"))
        vbox.Add(btn, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizer(vbox)

        root = self.tree.AddRoot("")
        self.folders = {}
        for folder, label in ((CORE_FOLDER, _("shortcuts_folder_core")),
                              (EXTENSIONS_FOLDER, _("shortcuts_folder_extensions"))):
            item = self.tree.AppendItem(root, label, data=("folder", folder))
            if folder_groups(self.groups, folder):
                self.tree.SetItemHasChildren(item, True)   # filled when opened
            self.folders[folder] = item

        self.tree.Bind(wx.EVT_TREE_ITEM_EXPANDING, self._on_expanding)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_selected)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activated)

        try:
            from core.i18n import apply_rtl_layout
            apply_rtl_layout(self)
        except Exception:
            pass
        self.CentreOnParent()
        try:
            import core.ui_scale
            core.ui_scale.apply_appearance(self)
        except Exception:
            pass

        # Start on the core's shortcuts, the ones asked for most.
        self.open_group(CORE_GROUPS[0]) or self.tree.SelectItem(self.folders[CORE_FOLDER])
        self.tree.SetFocus()

    # --- The tree -----------------------------------------------------------

    def load_folder(self, folder):
        """Add a folder's groups to the tree, the first time only."""
        if folder in self._loaded:
            return
        self._loaded.add(folder)
        item = self.folders[folder]
        for name in folder_groups(self.groups, folder):
            self.tree.AppendItem(item, name, data=("group", name))

    def _on_expanding(self, event):
        kind, value = self.tree.GetItemData(event.GetItem()) or (None, None)
        if kind == "folder":
            self.load_folder(value)
        event.Skip()

    def group_item(self, name):
        folder = CORE_FOLDER if name in CORE_GROUPS else EXTENSIONS_FOLDER
        self.load_folder(folder)
        item, cookie = self.tree.GetFirstChild(self.folders[folder])
        while item.IsOk():
            if self.tree.GetItemData(item) == ("group", name):
                return item
            item, cookie = self.tree.GetNextChild(self.folders[folder], cookie)
        return None

    def open_group(self, name):
        """Select a group in the tree (its folder opened); False if it has none."""
        item = self.group_item(name)
        if item is None:
            return False
        self.tree.Expand(self.tree.GetItemParent(item))
        self.tree.SelectItem(item)
        self.tree.EnsureVisible(item)
        return True

    # --- The list -----------------------------------------------------------

    def _on_selected(self, event):
        item = event.GetItem()
        if item.IsOk() and not self.IsBeingDeleted():
            self.show(self.tree.GetItemData(item))
        event.Skip()

    def show(self, data):
        kind, value = data or (None, None)
        if kind == "folder":
            names = folder_groups(self.groups, value)
            self._listed = ("folder", names)
            self.list.show(len(names), lambda i: (
                names[i], _("shortcuts_group_count", count=len(self.groups[names[i]]))))
        elif kind == "group":
            actions = self.groups.get(value, [])
            self._listed = ("group", actions)
            self.list.show(len(actions), lambda i: (actions[i].description, keys_text(actions[i])))
        else:
            self._listed = (None, [])
            self.list.show(0, None)

    def _on_activated(self, event):
        kind, items = getattr(self, "_listed", (None, []))
        index = event.GetIndex()
        if kind == "folder" and 0 <= index < len(items):
            self.open_group(items[index])
            self.tree.SetFocus()


def show_shortcuts(parent):
    dlg = ShortcutsDialog(parent)
    dlg.ShowModal()
    dlg.Destroy()
