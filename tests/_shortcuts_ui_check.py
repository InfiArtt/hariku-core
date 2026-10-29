# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The Keyboard Shortcuts window (F1, core 2.13) with real wxPython: a tree of
groups (Hariku, Extensions) filled when a folder opens, and a virtual list of
the selected group's shortcuts.

Run by tests/test_shortcuts_ui.py in a separate process, because conftest.py
mocks wx inside the pytest process. The caller points APPDATA at a temporary
folder. Prints one "OK" line per stage.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import wx
import core.ui_overrides
core.ui_overrides.apply_overrides()

app = wx.App(False)
import core.i18n
core.i18n.init()
import core.hotkeys as hk
hk.init_hotkeys()

from ui.main_window import MainWindow
frame = MainWindow(None, title="shortcuts check")
for i in range(40):
    hk.register_action("Orbit", f"cue_{i}", f"Orbit cue {i:02d}", None, False, lambda: None)
hk.register_action("Bintang Kecil", "open", "Open the sky", wx.WXK_F9, True, lambda: None,
                   default_global=True)

from ui import shortcuts_dialog as sd
dlg = sd.ShortcutsDialog(frame)
dlg.Show()
wx.Yield()


def children(item):
    found = []
    child, cookie = dlg.tree.GetFirstChild(item)
    while child.IsOk():
        found.append(dlg.tree.GetItemText(child))
        child, cookie = dlg.tree.GetNextChild(item, cookie)
    return found


def rows():
    return [(dlg.list.GetItemText(i, 0), dlg.list.GetItemText(i, 1))
            for i in range(dlg.list.GetItemCount())]


# It opens on the core's shortcuts, the tree focused.
selected = dlg.tree.GetSelection()
assert dlg.tree.GetItemText(selected) == "Hariku Core", dlg.tree.GetItemText(selected)
assert wx.Window.FindFocus() is dlg.tree
assert children(dlg.folders["core"]) == ["Hariku Core", "Calendar Navigation"]
assert ("Show Keyboard Shortcuts", "F1") in rows(), rows()
assert ("Increase global volume", "F6") in rows(), rows()
# The Extensions folder isn't filled until it is opened.
assert children(dlg.folders["extensions"]) == [] and "extensions" not in dlg._loaded
assert dlg.tree.ItemHasChildren(dlg.folders["extensions"])
print("OK opens_on_core")

# Selecting a folder lists its groups like subfolders; Enter opens one.
dlg.tree.SelectItem(dlg.folders["extensions"])
wx.Yield()
assert rows() == [("Bintang Kecil", "1 shortcuts"), ("Orbit", "40 shortcuts")], rows()
dlg.tree.Expand(dlg.folders["extensions"])
assert children(dlg.folders["extensions"]) == ["Bintang Kecil", "Orbit"]
event = wx.ListEvent(wx.wxEVT_LIST_ITEM_ACTIVATED, dlg.list.GetId())
event.SetIndex(1)
dlg.list.GetEventHandler().ProcessEvent(event)
wx.Yield()
assert dlg.tree.GetItemText(dlg.tree.GetSelection()) == "Orbit"
print("OK folders")

# The list is virtual: a row is made when it is shown, not all 40 at once.
assert dlg.list.GetItemCount() == 40
assert len(dlg.list._cache) < 40, len(dlg.list._cache)
assert dlg.list.GetItemText(39, 0) == "Orbit cue 39"
assert dlg.list.GetItemText(0, 1) == "Unassigned"
assert dlg.open_group("Bintang Kecil")
wx.Yield()
assert rows() == [("Open the sky", "Ctrl + F9 (global)")], rows()
print("OK virtual_list")

# A screen reader hears each pane's label.
for win, label in ((dlg.tree, "Groups"), (dlg.list, "Shortcuts")):
    accessible = win.GetAccessible()
    assert accessible and accessible.GetName(wx.ACC_SELF)[1].startswith(label), (label, accessible)
print("OK labels")

kept_item = dlg.folders["core"]          # an item id the tree gave out
dlg.Destroy()
wx.Yield()

# A selection the tree reports after the window is gone (Escape) is ignored:
# it raised "wrapped C/C++ object of type ShortcutsDialog has been deleted".
late = type("LateTreeEvent", (), {"GetItem": lambda self: kept_item})()
sd.ShortcutsDialog._on_selected(dlg, late)
print("OK late_selection")

# Opened with F1 and closed with a real Escape key: nothing goes wrong.
errors = []
sys.excepthook = lambda kind, value, tb: errors.append(value)


def press_escape():
    opened = [w for w in wx.GetTopLevelWindows() if isinstance(w, sd.ShortcutsDialog)]
    assert opened, "the window did not open"
    opened[0].tree.SelectItem(opened[0].folders["extensions"])
    opened[0].tree.SetFocus()
    wx.UIActionSimulator().Char(wx.WXK_ESCAPE)
    wx.CallLater(3000, lambda: [w.EndModal(wx.ID_CANCEL) for w in wx.GetTopLevelWindows()
                               if isinstance(w, sd.ShortcutsDialog) and w.IsModal()])


wx.CallLater(700, press_escape)
sd.show_shortcuts(frame)
for _ in range(30):
    wx.Yield()
assert not errors, errors
sys.excepthook = sys.__excepthook__
print("OK escape")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(200, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
