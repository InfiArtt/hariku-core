# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The Sound Themes page in Preferences, and its theme-name dialog.

Built from native controls for screen readers: a label right before each list
with the same accessible name, whole-sentence rows, Enter and Delete on the
lists, Escape and Enter in the dialog. Every button acts at once (there is
nothing to save with OK). Selection changes only refill the sound list; focus
moves only after an explicit action. Import and export run on a worker thread.
"""

import logging
import os
import threading

import wx

import core.sounds
import core.ui_scale
from core.i18n import apply_rtl_layout
from core.speech import speak

import sound_themes_store as store
import sound_themes_text as text
from sound_themes_text import _

logger = logging.getLogger(__name__)

_DIALOG_STYLE = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
_BORDER = 8
_KEEP = object()   # refresh(): keep the selected row

# Speak a result a moment after a dialog closes, so the screen reader's focus
# announcement doesn't cut it off.
ANNOUNCE_DELAY_MS = 300


# ------------------------------------------------------------
# Helpers (the prompts are module functions so checks can replace them)
# ------------------------------------------------------------

def _plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def _apply_appearance(window):
    try:
        core.ui_scale.apply_appearance(window)
    except Exception:
        pass


def _labeled(parent, sizer, label, make, proportion=0):
    """A label, then the control it names, with the same accessible name."""
    static = wx.StaticText(parent, label=label)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return static, ctrl


def _button(parent, sizer, label, handler):
    btn = wx.Button(parent, wx.ID_ANY, label)
    btn.Bind(wx.EVT_BUTTON, handler)
    sizer.Add(btn, 0, wx.RIGHT | wx.TOP, 4)
    return btn


def _announce(message, delay=None):
    delay = ANNOUNCE_DELAY_MS if delay is None else delay
    if delay <= 0:
        speak(message)
    else:
        wx.CallLater(delay, speak, message)


def _show_error(message):
    speak(message, interrupt=True)


def _confirm(parent, message, title):
    style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING
    return wx.MessageBox(message, title, style, parent) == wx.YES


def _ask_open_path(parent, title, wildcard):
    dlg = wx.FileDialog(parent, title, wildcard=wildcard,
                        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
    try:
        return dlg.GetPath() if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()


def _ask_save_path(parent, title, default_file, wildcard):
    dlg = wx.FileDialog(parent, title, defaultFile=default_file, wildcard=wildcard,
                        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
    try:
        return dlg.GetPath() if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()


def _open_folder(path):
    os.startfile(path)


def ask_name(parent, title, value, validate):
    """Show the theme-name dialog; the checked name, or None if cancelled."""
    dlg = ThemeNameDialog(parent, title, value, validate)
    try:
        return dlg.result if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()


def _run_in_thread(work, done):
    # Worker thread: files only, never wx; the result comes back via CallAfter.
    def runner():
        result, error = None, None
        try:
            result = work()
        except store.ThemeError as e:
            error = e
        except Exception as e:
            logger.exception("[Sound Themes] Background task failed")
            error = store.ThemeError("io")
        wx.CallAfter(done, result, error)

    threading.Thread(target=runner, daemon=True, name="sound-themes").start()


# ------------------------------------------------------------
# Theme name dialog
# ------------------------------------------------------------

class ThemeNameDialog(wx.Dialog):
    """Asks for a theme name. `validate(text)` returns the name to use or raises
    ThemeError; the dialog stays open, says why, and keeps focus in the field."""

    def __init__(self, parent, title, value="", validate=None):
        super().__init__(parent, title=title, style=_DIALOG_STYLE)
        self.result = None
        self._validate = validate
        root = wx.BoxSizer(wx.VERTICAL)
        self.text = _labeled(self, root, _("lbl_theme_name"),
                             lambda: wx.TextCtrl(self, value=value))[1]
        buttons = wx.StdDialogButtonSizer()
        ok = wx.Button(self, wx.ID_OK, _("btn_ok"))
        ok.SetDefault()
        ok.Bind(wx.EVT_BUTTON, self._on_ok)
        buttons.AddButton(ok)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL, _("btn_cancel")))
        buttons.Realize()
        root.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.SetEscapeId(wx.ID_CANCEL)
        apply_rtl_layout(self)
        _apply_appearance(self)
        self.Fit()
        width, height = self.GetSize()
        self.SetMinSize((width, height))
        self.SetSize((max(width, 380), height))
        self.CentreOnParent()
        self.text.SetFocus()
        self.text.SelectAll()

    def _on_ok(self, event=None):
        value = self.text.GetValue()
        try:
            self.result = self._validate(value) if self._validate else value
        except store.ThemeError as e:
            _show_error(text.error_text(e))
            self.text.SetFocus()
            self.text.SelectAll()
            return
        self.EndModal(wx.ID_OK)


# ------------------------------------------------------------
# Preferences page
# ------------------------------------------------------------

class SoundThemesPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self._themes = []
        self._sounds = []
        self._busy = False
        root = wx.BoxSizer(wx.VERTICAL)

        self.lbl_themes, self.list_themes = _labeled(
            self, root, _("lbl_themes"), lambda: wx.ListBox(self, style=wx.LB_SINGLE), proportion=1)
        theme_buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_use = _button(self, theme_buttons, _("btn_use"), self.on_use)
        self.btn_new = _button(self, theme_buttons, _("btn_new"), self.on_new)
        self.btn_duplicate = _button(self, theme_buttons, _("btn_duplicate"), self.on_duplicate)
        self.btn_rename = _button(self, theme_buttons, _("btn_rename"), self.on_rename)
        self.btn_delete = _button(self, theme_buttons, _("btn_delete"), self.on_delete)
        self.btn_folder = _button(self, theme_buttons, _("btn_open_folder"), self.on_open_folder)
        self.btn_import = _button(self, theme_buttons, _("btn_import"), self.on_import)
        self.btn_export = _button(self, theme_buttons, _("btn_export"), self.on_export)
        root.Add(theme_buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _BORDER)

        self.lbl_sounds, self.list_sounds = _labeled(
            self, root, _("lbl_sounds_in", theme=_("default_name")),
            lambda: wx.ListBox(self, style=wx.LB_SINGLE), proportion=1)
        sound_buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_play = _button(self, sound_buttons, _("btn_play"), self.on_play)
        self.btn_replace = _button(self, sound_buttons, _("btn_replace"), self.on_replace)
        self.btn_reset = _button(self, sound_buttons, _("btn_reset"), self.on_reset)
        root.Add(sound_buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, _BORDER)
        self.SetSizer(root)

        self.list_themes.Bind(wx.EVT_LISTBOX, self._on_theme_selected)
        self.list_themes.Bind(wx.EVT_LISTBOX_DCLICK, self.on_use)
        self.list_sounds.Bind(wx.EVT_LISTBOX_DCLICK, self.on_play)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        self.refresh(select=store.get_active())
        _apply_appearance(self)

    # -- data -> controls ---------------------------------------------------- #
    def refresh(self, select=_KEEP):
        """Rebuild the theme list, selecting theme `select` (None is Default)
        if it exists, else the row that was selected."""
        previous = self.list_themes.GetSelection()
        active = store.get_active()
        self._themes = store.list_themes()
        self.list_themes.Set([text.theme_row(t, t == active, len(store.custom_sounds(t)))
                              for t in self._themes])
        if select is not _KEEP and select in self._themes:
            index = self._themes.index(select)
        elif previous != wx.NOT_FOUND:
            index = min(previous, len(self._themes) - 1)
        else:
            index = 0
        self.list_themes.SetSelection(index)
        self._fill_sounds()

    def _fill_sounds(self):
        found, theme = self.selected_theme()
        previous = self.list_sounds.GetSelection()
        self._sounds = store.sound_names()
        custom = set(store.custom_sounds(theme)) if found else set()
        self.list_sounds.Set([text.sound_row(s, theme, s in custom) for s in self._sounds])
        self.list_sounds.SetSelection(previous if 0 <= previous < len(self._sounds) else 0)
        label = _("lbl_sounds_in", theme=text.theme_name(theme).replace("&", "&&"))
        self.lbl_sounds.SetLabel(label)
        self.list_sounds.SetName(_plain(label))
        self.Layout()

    def selected_theme(self):
        """(True, name) for the selected theme (name None is Default), or (False, None)."""
        index = self.list_themes.GetSelection()
        if 0 <= index < len(self._themes):
            return True, self._themes[index]
        return False, None

    def selected_sound(self):
        index = self.list_sounds.GetSelection()
        return self._sounds[index] if 0 <= index < len(self._sounds) else None

    def _custom_theme(self):
        """The selected theme if it can be changed; otherwise says why and returns None."""
        found, theme = self.selected_theme()
        if not found:
            speak(_("nothing_selected"), interrupt=True)
            return None
        if theme is None:
            _show_error(text.error_text(store.ThemeError("default_readonly")))
            return None
        return theme

    # -- events -------------------------------------------------------------- #
    def _on_theme_selected(self, event=None):
        # Fires on every arrow press: refill the sounds only, never move focus.
        self._fill_sounds()

    def _on_char_hook(self, event):
        focus = wx.Window.FindFocus()
        if not event.HasAnyModifiers() and focus in (self.list_themes, self.list_sounds):
            key = event.GetKeyCode()
            enter = key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
            delete = key in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE)
            if focus is self.list_themes and enter:
                self.on_use()
                return
            if focus is self.list_themes and delete:
                self.on_delete()
                return
            if focus is self.list_sounds and enter:
                self.on_play()
                return
            if focus is self.list_sounds and delete:
                self.on_reset()
                return
        event.Skip()

    def _fail(self, error, delay=0):
        message = text.error_text(error)
        if delay:
            _announce(message, delay)
        else:
            _show_error(message)

    # -- theme actions ------------------------------------------------------- #
    def on_use(self, event=None):
        found, theme = self.selected_theme()
        if not found:
            speak(_("nothing_selected"), interrupt=True)
            return
        try:
            theme = store.apply_theme(theme)
        except store.ThemeError as e:
            self._fail(e)
            self.refresh()
            return
        self.refresh(select=theme)
        speak(text.applied_text(theme), interrupt=True)

    def on_new(self, event=None):
        name = ask_name(self, _("dlg_new_title"), "", store.check_name)
        if name is None:
            return
        try:
            name = store.create_theme(name)
        except store.ThemeError as e:
            self._fail(e, ANNOUNCE_DELAY_MS)
            return
        self.refresh(select=name)
        _announce(_("theme_created", name=name))

    def on_duplicate(self, event=None):
        found, source = self.selected_theme()
        if not found:
            speak(_("nothing_selected"), interrupt=True)
            return
        suggestion = store.unique_name(_("copy_name", name=text.theme_name(source)),
                                       _("copy_name", name=text.theme_name(source)))
        name = ask_name(self, _("dlg_duplicate_title"), suggestion, store.check_name)
        if name is None:
            return
        try:
            name = store.duplicate_theme(source, name)
        except store.ThemeError as e:
            self._fail(e, ANNOUNCE_DELAY_MS)
            self.refresh()
            return
        self.refresh(select=name)
        _announce(_("theme_duplicated", name=name, source=text.theme_name(source)))

    def on_rename(self, event=None):
        old = self._custom_theme()
        if old is None:
            return
        name = ask_name(self, _("dlg_rename_title"), old,
                        lambda value: store.check_name(value, renaming=old))
        if name is None or name == old:
            return
        try:
            name = store.rename_theme(old, name)
        except store.ThemeError as e:
            self._fail(e, ANNOUNCE_DELAY_MS)
            self.refresh()
            return
        self.refresh(select=name)
        _announce(_("theme_renamed", old=old, name=name))

    def on_delete(self, event=None):
        theme = self._custom_theme()
        if theme is None:
            return
        if store.get_active() == theme:
            self._fail(store.ThemeError("delete_active", name=theme))
            return
        if not _confirm(self, _("confirm_delete", name=theme), _("confirm_delete_title")):
            return
        try:
            store.delete_theme(theme)
        except store.ThemeError as e:
            self._fail(e, ANNOUNCE_DELAY_MS)
            self.refresh()
            return
        self.refresh()
        _announce(_("theme_deleted", name=theme))

    def on_open_folder(self, event=None):
        found, theme = self.selected_theme()
        if not found:
            speak(_("nothing_selected"), interrupt=True)
            return
        if theme is None:
            _show_error(_("default_no_folder"))
            return
        try:
            _open_folder(store.theme_dir(theme))
        except OSError as e:
            logger.info(f"[Sound Themes] Could not open the theme folder: {e}")
            _show_error(text.error_text(store.ThemeError("io")))

    def on_import(self, event=None):
        if self._busy:
            speak(_("busy"), interrupt=True)
            return
        path = _ask_open_path(self, _("dlg_import_title"), _("wildcard_import"))
        if not path:
            return
        self._busy = True
        _announce(_("importing"))
        fallback = _("imported_name")
        _run_in_thread(lambda: store.import_theme(path, fallback), self._import_done)

    def _import_done(self, result, error):
        if self:
            self._busy = False
        if error is not None:
            speak(text.error_text(error), interrupt=True)
            return
        name, count, skipped = result
        if self:
            self.refresh(select=name)
        if skipped:
            speak(_("imported_skipped", name=name, count=count, skipped=skipped), interrupt=True)
        else:
            speak(_("imported", name=name, count=count), interrupt=True)

    def on_export(self, event=None):
        if self._busy:
            speak(_("busy"), interrupt=True)
            return
        found, theme = self.selected_theme()
        if not found:
            speak(_("nothing_selected"), interrupt=True)
            return
        label = text.theme_name(theme)
        if theme is not None and not store.custom_sounds(theme):
            self._fail(store.ThemeError("export_empty", name=label))
            return
        # Theme names are valid file names already.
        path = _ask_save_path(self, _("dlg_export_title", name=label), f"{label}.zip",
                              _("wildcard_zip"))
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        self._busy = True
        _announce(_("exporting"))
        _run_in_thread(lambda: store.export_theme(theme, path),
                       lambda count, error: self._export_done(label, count, error))

    def _export_done(self, label, count, error):
        if self:
            self._busy = False
        if error is not None:
            speak(text.error_text(error), interrupt=True)
            return
        speak(_("exported", name=label, count=count), interrupt=True)

    # -- sound actions ------------------------------------------------------- #
    def on_play(self, event=None):
        found, theme = self.selected_theme()
        sound = self.selected_sound()
        if not found or sound is None:
            speak(_("no_sound_selected"), interrupt=True)
            return
        if not core.sounds.play_sound(store.sound_path(theme, sound)):
            _show_error(_("play_failed", sound=text.sound_label(sound)))

    def on_replace(self, event=None):
        theme = self._custom_theme()
        if theme is None:
            return
        sound = self.selected_sound()
        if sound is None:
            speak(_("no_sound_selected"), interrupt=True)
            return
        path = _ask_open_path(self, _("dlg_pick_wav", sound=text.sound_label(sound)),
                              _("wildcard_wav"))
        if not path:
            return
        try:
            store.replace_sound(theme, sound, path)
        except store.ThemeError as e:
            self._fail(e, ANNOUNCE_DELAY_MS)
            return
        self.refresh(select=theme)
        _announce(_("sound_replaced", sound=text.sound_label(sound)))

    def on_reset(self, event=None):
        theme = self._custom_theme()
        if theme is None:
            return
        sound = self.selected_sound()
        if sound is None:
            speak(_("no_sound_selected"), interrupt=True)
            return
        try:
            removed = store.reset_sound(theme, sound)
        except store.ThemeError as e:
            self._fail(e)
            return
        if not removed:
            speak(_("sound_not_custom", sound=text.sound_label(sound)), interrupt=True)
            return
        self.refresh(select=theme)
        speak(_("sound_reset", sound=text.sound_label(sound)), interrupt=True)
