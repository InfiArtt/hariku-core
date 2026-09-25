# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
World Trip's Preferences page: the departure announcement, the engine sound,
the radio and its volume, native voices, and which voice each language would
use (listed on a worker thread; the page shows "Looking for voices..." until
then).

Every label is created right before the control it names (screen readers
name a control after the static text created just before it; SetName doesn't
change that). Nothing here moves the focus.
"""

import wx

from world_trip_text import _

_BORDER = 10


def _plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def _labeled(parent, sizer, label, make, proportion=0):
    """A label, then the control it names, with the same accessible name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return ctrl


def _check(parent, sizer, label, value):
    box = wx.CheckBox(parent, label=label)
    box.SetValue(bool(value))
    sizer.Add(box, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    return box


def _note(parent, sizer, label, width=520):
    static = wx.StaticText(parent, label=label)
    static.Wrap(width)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    return static


class WorldTripPanel(wx.Panel):
    """`list_voices(done)` starts listing the native voices and calls
    done(text) on the UI thread with the lines to show."""

    def __init__(self, parent, settings, list_voices):
        super().__init__(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.chk_departure = _check(self, sizer, _("chk_departure"), settings["departure"])
        self.chk_engine = _check(self, sizer, _("chk_engine"), settings["engine"])
        self.chk_radio = _check(self, sizer, _("chk_radio"), settings["radio"])
        self.sld_volume = _labeled(self, sizer, _("lbl_volume"),
                                   lambda: wx.Slider(self, value=int(settings["radio_volume"]),
                                                     minValue=0, maxValue=100))
        self.sld_volume.SetLineSize(5)
        self.sld_volume.SetPageSize(10)
        self.chk_native = _check(self, sizer, _("chk_native"), settings["native_voices"])
        self.txt_voices = _labeled(self, sizer, _("lbl_voices"),
                                   lambda: wx.TextCtrl(self, value=_("voices_loading"),
                                                       size=(-1, 150),
                                                       style=wx.TE_MULTILINE | wx.TE_READONLY),
                                   proportion=1)
        _note(self, sizer, _("note_how"))
        _note(self, sizer, _("note_credits"))
        _note(self, sizer, _("note_privacy"))
        self.SetSizer(sizer)

        self.chk_departure.Bind(wx.EVT_CHECKBOX, lambda event: self._follow())
        self.chk_radio.Bind(wx.EVT_CHECKBOX, lambda event: self._follow())
        self._follow()
        self._closed = False
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        list_voices(self.show_voices)

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._closed = True
        event.Skip()

    def _follow(self):
        """The engine sound belongs to the departure, the volume to the radio."""
        self.chk_engine.Enable(self.chk_departure.GetValue())
        self.sld_volume.Enable(self.chk_radio.GetValue())

    def show_voices(self, text):
        if self._closed:
            return
        try:
            self.txt_voices.ChangeValue(text)
        except RuntimeError:
            pass        # the page is gone

    def get_settings(self):
        return {"departure": self.chk_departure.GetValue(),
                "engine": self.chk_engine.GetValue(),
                "radio": self.chk_radio.GetValue(),
                "radio_volume": int(self.sld_volume.GetValue()),
                "native_voices": self.chk_native.GetValue()}
