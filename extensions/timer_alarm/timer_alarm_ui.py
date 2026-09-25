# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The "Timer & Alarm" Preferences page: the alarms and timers there are (Name,
When or time left, Repeats) with Remove (Delete too, after asking) and Stop
ringing, then the settings: alarm sound and timer sound (each with a Test
button that plays three seconds), how long a ring lasts and how long a snooze
is. Settings are saved on OK or Apply; Remove and Stop ringing act at once.

Every control comes right after the label that names it (screen readers name
a control after the static text created just before it; SetName doesn't
change that). Selecting a row never moves the focus. Nothing here opens when
something rings.
"""

import wx

import core.ui_scale
from core.speech import speak

import timer_alarm_store as store
import timer_alarm_text as text
from timer_alarm_text import _

_BORDER = 8
ANNOUNCE_DELAY_MS = 300      # after the screen reader's own announcement
TEST_MS = 3000               # the Test buttons play this long


def _plain(label):
    return " ".join(label.replace("&&", "\0").replace("&", "").replace("\0", "&")
                    .strip().rstrip(":").split())


def _labeled(parent, sizer, label, make, proportion=0):
    """A label, then the control it names (created after it), with the same
    accessible name."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return ctrl


def _confirm(parent, message, title):
    style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
    return wx.MessageBox(message, title, style, parent) == wx.YES


def announce(message, delay=ANNOUNCE_DELAY_MS):
    wx.CallLater(delay, speak, message)


def sound_label(choice):
    """ "Windows alarm 1", "Windows ring 3", "Hariku alarm tone"."""
    value, family, number = choice
    if family == "Alarm":
        return _("sound_windows_alarm", n=number)
    if family == "Ring":
        return _("sound_windows_ring", n=number)
    return _("sound_tone_alarm") if number == "alarm" else _("sound_tone_timer")


class SettingsPanel(wx.Panel):
    """`actions` is main.py's PageActions: rows(), remove(item_id), stop(),
    settings(), sound_choices(), sound_path(choice, kind), play(path),
    stop_sound(path)."""

    def __init__(self, parent, actions):
        super().__init__(parent)
        self._actions = actions
        self._ids = []
        self._test_path = None
        self._test_timer = None
        settings = actions.settings()
        self._choices = list(actions.sound_choices())
        root = wx.BoxSizer(wx.VERTICAL)

        self.list = _labeled(self, root, _("lbl_items"), lambda: wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=(-1, 150)), proportion=1)
        self.list.InsertColumn(0, _("col_name"), width=200)
        self.list.InsertColumn(1, _("col_when"), width=260)
        self.list.InsertColumn(2, _("col_repeats"), width=160)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_remove = wx.Button(self, label=_("btn_remove"))
        self.btn_stop = wx.Button(self, label=_("btn_stop"))
        buttons.Add(self.btn_remove, 0, wx.RIGHT, _BORDER)
        buttons.Add(self.btn_stop, 0)
        root.Add(buttons, 0, wx.ALL, _BORDER)

        labels = [sound_label(c) for c in self._choices]
        self.choice_alarm_sound = _labeled(self, root, _("lbl_alarm_sound"), lambda: wx.Choice(
            self, choices=labels))
        self.btn_test_alarm = wx.Button(self, label=_("btn_test_alarm"))
        root.Add(self.btn_test_alarm, 0, wx.LEFT | wx.TOP, _BORDER)
        self.choice_timer_sound = _labeled(self, root, _("lbl_timer_sound"), lambda: wx.Choice(
            self, choices=labels))
        self.btn_test_timer = wx.Button(self, label=_("btn_test_timer"))
        root.Add(self.btn_test_timer, 0, wx.LEFT | wx.TOP, _BORDER)
        self._select_sound(self.choice_alarm_sound, settings["alarm_sound"], "tone:alarm")
        self._select_sound(self.choice_timer_sound, settings["timer_sound"], "tone:timer")

        self.choice_ring = _labeled(self, root, _("lbl_ring"), lambda: wx.Choice(
            self, choices=[text.duration_text(m * 60) for m in store.RING_CHOICES]))
        self.choice_ring.SetSelection(store.RING_CHOICES.index(settings["ring_minutes"]))
        self.choice_snooze = _labeled(self, root, _("lbl_snooze"), lambda: wx.Choice(
            self, choices=[text.duration_text(m * 60) for m in store.SNOOZE_CHOICES]))
        self.choice_snooze.SetSelection(store.SNOOZE_CHOICES.index(settings["snooze_minutes"]))

        # A read-only field rather than a StaticText, so Tab reaches it.
        self.txt_about = _labeled(self, root, _("lbl_about"), lambda: wx.TextCtrl(
            self, value=_("about_text"), size=(-1, 120),
            style=wx.TE_MULTILINE | wx.TE_READONLY), proportion=1)
        self.SetSizer(root)

        self.btn_remove.Bind(wx.EVT_BUTTON, self.on_remove)
        self.btn_stop.Bind(wx.EVT_BUTTON, self.on_stop)
        self.btn_test_alarm.Bind(wx.EVT_BUTTON, lambda e: self.on_test("alarm"))
        self.btn_test_timer.Bind(wx.EVT_BUTTON, lambda e: self.on_test("timer"))
        self.list.Bind(wx.EVT_LIST_KEY_DOWN, self._on_list_key)
        self.Bind(wx.EVT_SHOW, self._on_show)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        self.refresh()
        core.ui_scale.apply_appearance(self)

    # --- the list -------------------------------------------------------------------

    def refresh(self, select_id=None, select_index=None):
        """Rebuild the rows, keeping the selected item selected. Never moves
        the focus."""
        target = select_id if select_id is not None else self.selected_id()
        old_index = self.list.GetFirstSelected()
        rows = list(self._actions.rows())
        self.list.DeleteAllItems()
        self._ids = []
        if not rows:
            self.list.InsertItem(0, _("list_empty_row"))
            self._ids.append(None)
        for index, (item_id, cells) in enumerate(rows):
            self.list.InsertItem(index, cells[0])
            self.list.SetItem(index, 1, cells[1])
            self.list.SetItem(index, 2, cells[2])
            self._ids.append(item_id)
        if target in self._ids and target is not None:
            index = self._ids.index(target)
        elif select_index is not None:
            index = select_index
        else:
            index = max(0, old_index)
        index = max(0, min(index, self.list.GetItemCount() - 1))
        if self.list.GetItemCount():
            self.list.Select(index)
            self.list.Focus(index)

    def selected_id(self):
        index = self.list.GetFirstSelected()
        return self._ids[index] if 0 <= index < len(self._ids) else None

    def _on_list_key(self, event):
        if event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
            self.on_remove()
            return
        event.Skip()

    def _on_show(self, event):
        if event.IsShown():
            self.refresh()
        event.Skip()

    # --- buttons --------------------------------------------------------------------

    def on_remove(self, event=None):
        item_id = self.selected_id()
        if item_id is None:
            speak(_("nothing_selected"))
            return
        index = self.list.GetFirstSelected()
        name = self.list.GetItemText(index, 0)
        if not _confirm(self, _("confirm_remove", name=name), _("confirm_title")):
            return
        message = self._actions.remove(item_id)
        self.refresh(select_index=index)
        announce(message)

    def on_stop(self, event=None):
        message = self._actions.stop()
        self.refresh()
        speak(message)

    def on_test(self, kind):
        """Play the chosen sound for three seconds."""
        ctrl = self.choice_alarm_sound if kind == "alarm" else self.choice_timer_sound
        choice = self._choice_at(ctrl)
        self._stop_test()
        path = self._actions.sound_path(choice, kind)
        self._test_path = path
        self._actions.play(path)
        self._test_timer = wx.CallLater(TEST_MS, self._stop_test)

    def _stop_test(self):
        timer, self._test_timer = self._test_timer, None
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass
        path, self._test_path = self._test_path, None
        if path:
            self._actions.stop_sound(path)

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._stop_test()
        event.Skip()

    # --- settings -------------------------------------------------------------------

    def _select_sound(self, ctrl, value, fallback):
        values = [c[0] for c in self._choices]
        index = values.index(value) if value in values else values.index(fallback)
        ctrl.SetSelection(index)

    def _choice_at(self, ctrl):
        index = ctrl.GetSelection()
        if 0 <= index < len(self._choices):
            return self._choices[index][0]
        return self._choices[-1][0]

    def get_settings(self):
        ring = self.choice_ring.GetSelection()
        snooze = self.choice_snooze.GetSelection()
        return {
            "alarm_sound": self._choice_at(self.choice_alarm_sound),
            "timer_sound": self._choice_at(self.choice_timer_sound),
            "ring_minutes": store.RING_CHOICES[ring] if 0 <= ring < len(store.RING_CHOICES)
            else store.DEFAULT_SETTINGS["ring_minutes"],
            "snooze_minutes": store.SNOOZE_CHOICES[snooze]
            if 0 <= snooze < len(store.SNOOZE_CHOICES)
            else store.DEFAULT_SETTINGS["snooze_minutes"],
        }
