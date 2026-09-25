# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Calculator & Converter's Preferences page: the home currency, how many
decimals to say, which KB/MB/GB to use, and whether to copy every result.

Every label is created right before the control it names (screen readers
name a control after the static text created just before it; SetName doesn't
change that). Nothing here moves the focus.
"""

import wx

import calculator_intents as intents
import calculator_money as money
from calculator_text import _

_BORDER = 10


def _plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def _labeled(parent, sizer, label, make):
    """A label, then the control it names, with the same accessible name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return ctrl


def _note(parent, sizer, label, width=520):
    static = wx.StaticText(parent, label=label)
    static.Wrap(width)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    return static


def home_choices(language):
    """[(value, label)] for the home currency list."""
    choices = [("auto", _("home_auto"))]
    for code in intents.HOME_CHOICES[1:]:
        choices.append((code, _("home_item", name=money.name(code, language, 2), code=code)))
    return choices


def decimal_choices():
    return [("auto", _("decimals_auto"))] + [(n, str(n)) for n in range(7)]


def data_choices():
    return [(1024, _("data_1024")), (1000, _("data_1000"))]


class CalculatorPanel(wx.Panel):
    def __init__(self, parent, settings, language="en"):
        super().__init__(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self._homes = home_choices(language)
        self._decimals = decimal_choices()
        self._data = data_choices()
        self.cho_home = _labeled(self, sizer, _("lbl_home"), lambda: wx.Choice(
            self, choices=[label for _value, label in self._homes]))
        self.cho_decimals = _labeled(self, sizer, _("lbl_decimals"), lambda: wx.Choice(
            self, choices=[label for _value, label in self._decimals]))
        self.cho_data = _labeled(self, sizer, _("lbl_data"), lambda: wx.Choice(
            self, choices=[label for _value, label in self._data]))
        self.chk_copy = wx.CheckBox(self, label=_("chk_copy"))
        sizer.Add(self.chk_copy, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        _note(self, sizer, _("note_how"))
        _note(self, sizer, _("note_privacy"))
        self.SetSizer(sizer)
        self.set_settings(settings)

    @staticmethod
    def _select(ctrl, choices, value):
        values = [v for v, _label in choices]
        ctrl.SetSelection(values.index(value) if value in values else 0)

    def set_settings(self, settings):
        settings = intents.normalize_settings(settings)
        self._select(self.cho_home, self._homes, settings["home"])
        self._select(self.cho_decimals, self._decimals, settings["decimals"])
        self._select(self.cho_data, self._data, settings["data"])
        self.chk_copy.SetValue(bool(settings["auto_copy"]))

    def get_settings(self):
        def value(ctrl, choices):
            index = ctrl.GetSelection()
            return choices[index][0] if 0 <= index < len(choices) else choices[0][0]
        return intents.normalize_settings({
            "home": value(self.cho_home, self._homes),
            "decimals": value(self.cho_decimals, self._decimals),
            "data": value(self.cho_data, self._data),
            "auto_copy": self.chk_copy.GetValue(),
        })
