# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The quick reminder (N): type one sentence such as "minum obat besok jam 8
pagi, tiap hari", press Enter, hear what Hariku understood, and save it as an
ordinary reminder. No AI and nothing leaves the computer: dates, times and
repeats come from the rule-based reader in core/when.py.

Every label is created right before the control it names: screen readers
name a control after the static text just before it, and SetName() doesn't
change that. Focus only moves when the dialog opens.
"""

import wx

import core.api
import core.quick_reminder as quick
import core.ui_scale
from core.core_panels import _labeled
from core.i18n import apply_rtl_layout, get_translator
from core.speech import speak

_ = get_translator("core")


class QuickReminderDialog(wx.Dialog):
    """Type a sentence and press Enter: the read-back is spoken and shown in a
    read-only field (one Tab away, for braille). Enter again on the same text,
    or Save, saves it; nothing is saved before a read-back was given for the
    text as it is now. Edit closes with wx.ID_EDIT so the caller can open the
    full reminder dialog. `parse(text)` returns a core.when Result,
    `readback(result)` its sentence, `save(result)` saves it and returns True.
    `text` fills in the field (the command bar hands over a sentence)."""

    def __init__(self, parent, parse=None, readback=None, save=None, say=None, text=""):
        super().__init__(parent, title=_("qr_title"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._parse = parse or quick.parse_text
        self._readback = readback or quick.readback
        self._save = save or quick.save_result
        self._say = say or (lambda text: speak(text, interrupt=True))
        self.result = None
        self._checked_text = None
        self._stale = False

        vbox = wx.BoxSizer(wx.VERTICAL)
        self.txt_input = _labeled(self, vbox, _("qr_lbl_input"),
                                  lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER,
                                                      size=(480, -1)))
        self.txt_readback = _labeled(self, vbox, _("qr_lbl_readback"),
                                     lambda: wx.TextCtrl(self, value=_("qr_readback_hint"),
                                                         size=(480, 96),
                                                         style=wx.TE_READONLY | wx.TE_MULTILINE),
                                     proportion=1)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_save = wx.Button(self, label=_("qr_btn_save"))
        self.btn_edit = wx.Button(self, label=_("qr_btn_edit"))
        self.btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("qr_btn_cancel"))
        buttons.Add(self.btn_save, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_edit, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_cancel, 0)
        vbox.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizer(vbox)
        self.SetEscapeId(wx.ID_CANCEL)

        self.txt_input.Bind(wx.EVT_TEXT_ENTER, self._on_enter)
        self.txt_input.Bind(wx.EVT_TEXT, self._on_text)
        self.btn_save.Bind(wx.EVT_BUTTON, self._on_save)
        self.btn_edit.Bind(wx.EVT_BUTTON, self._on_edit)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.CentreOnParent()
        if text:
            self.txt_input.ChangeValue(text)
            self.txt_input.SetInsertionPointEnd()
        self.txt_input.SetFocus()

    def text(self):
        return self.txt_input.GetValue().strip()

    def _current(self, text):
        return self.result is not None and text == self._checked_text

    def check(self, text=None):
        """Parse the text, show and speak the read-back. Focus stays put."""
        text = self.text() if text is None else text
        if not text:
            self._say(_("qr_empty_input"))
            return None
        self.result = self._parse(text)
        self._checked_text = text
        self._stale = False
        message = self._readback(self.result)
        self.txt_readback.SetValue(message)
        if self.result.ok:
            self.btn_save.SetDefault()
        self._say(message)
        return self.result

    def _on_text(self, event):
        # The read-back no longer matches what is typed: don't leave it on the
        # braille display as if it did. Save checks the new text first.
        if self._checked_text is not None and not self._stale \
                and self.text() != self._checked_text:
            self._stale = True
            self.txt_readback.SetValue(_("qr_readback_hint"))
        event.Skip()

    def _on_enter(self, event):
        text = self.text()
        if text and self._current(text) and self.result.ok:
            self._do_save()
        else:
            self.check(text)

    def _on_save(self, event):
        text = self.text()
        if not text or not self._current(text):
            self.check(text)          # read it back first; the next Save saves
        elif not self.result.ok:
            self._say(self._readback(self.result))
        else:
            self._do_save()

    def _do_save(self):
        if self._save(self.result):
            self.EndModal(wx.ID_OK)

    def _on_edit(self, event):
        text = self.text()
        if text and not self._current(text):
            self.result = self._parse(text)
            self._checked_text = text
        self.EndModal(wx.ID_EDIT)


_dialog_open = False


def open_quick_reminder(parent=None, text=""):
    """The N action: the quick reminder, then, after Edit, the full reminder
    dialog filled in with everything understood. `text` is put in the field."""
    global _dialog_open
    if _dialog_open:
        return
    _dialog_open = True
    parent = parent or core.api.main_window_instance
    try:
        dlg = QuickReminderDialog(parent, text=text)
        try:
            code = dlg.ShowModal()
            result, text = dlg.result, dlg.text()
        finally:
            dlg.Destroy()
    finally:
        _dialog_open = False
    if code == wx.ID_EDIT:
        open_full_dialog(parent, result, text)


def open_full_dialog(parent, result, text=""):
    """Hariku's reminder dialog, filled in with what was understood: title,
    date, time, repeat and how often."""
    from ui.reminder_dialog import AddReminderDialog
    fallback = core.api.get_selected_date() or quick._now().strftime("%Y-%m-%d")
    prefill = quick.full_dialog_prefill(result, text, fallback)
    dlg = AddReminderDialog(parent, prefill[1] or fallback, prefill=prefill)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()
