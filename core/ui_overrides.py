# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import wx
import os

_OldStaticText = wx.StaticText

class PrefixAccessible(wx.Accessible):
    def __init__(self, win, prefix):
        super().__init__(win)
        self.win = win
        self.prefix = prefix

    def GetName(self, childId):
        if childId == wx.ACC_SELF:
            label = ""
            if hasattr(self.win, 'GetLabel'):
                label = self.win.GetLabel().replace('&', '')
            elif hasattr(self.win, 'GetValue') and isinstance(self.win.GetValue(), str):
                label = self.win.GetValue()
            return wx.ACC_OK, f"{self.prefix} {label}".strip()
        return wx.ACC_NOT_IMPLEMENTED, ""

class AccessibleStaticText(_OldStaticText):
    """
    A monkey-patched version of wx.StaticText that dynamically injects its text 
    into the Accessible Name of the NEXT interactive sibling control.
    This allows NVDA to seamlessly read the static text BEFORE the item's native label,
    with zero extra Tab stops and no overlapping speech!
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        wx.CallAfter(self._attach_to_next_sibling)
        
    def _attach_to_next_sibling(self):
        parent = self.GetParent()
        if not parent:
            return
            
        children = parent.GetChildren()
        try:
            idx = children.index(self)
            if idx + 1 < len(children):
                next_child = children[idx + 1]
                # Skip if the next child is not an interactive control
                if not isinstance(next_child, (wx.StaticText, wx.StaticBox, wx.StaticBitmap, wx.Panel)):
                    # Check if it already has an accessible object to avoid overwriting
                    # wxPython doesn't have HasAccessible, but we can just set it
                    prefix = self.GetLabel().replace('&', '').replace('\n', ' ')
                    if prefix.strip():
                        acc = PrefixAccessible(next_child, prefix)
                        next_child.SetAccessible(acc)
        except ValueError:
            pass

def apply_overrides():
    if os.name == 'nt':
        wx.StaticText = AccessibleStaticText
