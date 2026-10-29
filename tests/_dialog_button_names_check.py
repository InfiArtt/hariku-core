# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
With the StaticText override on (as hariku.py turns it on), a text just above
a control names it, but never a dialog's OK, Cancel... button (core 2.13): in
Places' Add Place dialog, OK was read as "Address search: © OpenStreetMap
contributors. City search: Open-Meteo.com. ... OK".

Run by tests/test_ui_overrides_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder. Prints one "OK" line per stage.
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


def name_of(win):
    accessible = win.GetAccessible()
    return accessible.GetName(wx.ACC_SELF)[1] if accessible else win.GetLabel()


dlg = wx.Dialog(None, title="names")
wx.StaticText(dlg, label="City:")
field = wx.TextCtrl(dlg)
wx.StaticText(dlg, label="A note about where the data comes from.")
ok = wx.Button(dlg, wx.ID_OK, "OK")
wx.StaticText(dlg, label="Another note.")
other = wx.Button(dlg, wx.ID_ANY, "Search")
dlg.Show()
wx.Yield()
assert name_of(field) == "City:", name_of(field)
assert name_of(ok) == "OK", name_of(ok)
assert name_of(other) == "Another note. Search", name_of(other)   # unchanged for other buttons
dlg.Destroy()
print("OK plain_dialog")

from core import places_ui
frame = wx.Frame(None)
place = places_ui.PlaceDialog(frame, "Add place")
place.Show()
wx.Yield()
assert "OpenStreetMap" not in name_of(place.btn_ok), name_of(place.btn_ok)
assert name_of(place.btn_ok) == place.btn_ok.GetLabel(), name_of(place.btn_ok)
place.Destroy()
frame.Destroy()
print("OK place_dialog")
