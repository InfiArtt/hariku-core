# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the real main window and save General settings, using real wxPython.

Run by tests/test_startup.py in a separate process, because conftest.py mocks
wx inside the pytest process. The caller points APPDATA at a temporary folder so
the user's real settings are never touched. Prints one "OK" line per stage.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import wx

app = wx.App(False)

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()

from ui.main_window import MainWindow
frame = MainWindow(None, title="startup check")
print("OK main_window")

import core.core_panels
panel = core.core_panels.GeneralSettingsPanel(frame)
panel.chk_high_contrast.SetValue(True)
panel.choice_scale.SetSelection(panel._scale_keys.index("large"))
panel.ApplyChanges()
print("OK apply_settings")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
