# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The Piper Voices page in Preferences, and the download dialog.

Built from native controls for screen readers: every control comes right
after the label that names it (screen readers name a control after the static
text created just before it; SetName alone doesn't change that). Selecting a
voice or a language only refills the list and the details; focus never moves
by itself. The buttons act at once, so there is nothing to save with OK.

The voice list loads when the page is first shown (from disk while it is under
7 days old). Model cards are fetched only when the user presses Download, so
browsing the list sends nothing anywhere.
"""

import logging

import wx

import core.ui_scale
import core.voice
from core.i18n import apply_rtl_layout
from core.speech import speak

import piper_voices_catalogue as catalogue
import piper_voices_download as download
import piper_voices_text as text
from piper_voices_text import _

logger = logging.getLogger(__name__)

_BORDER = 8
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
    """A label, then the control make() creates, with the same accessible
    name. The factory runs after the label exists, so the order is right."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    ctrl = make()
    ctrl.SetName(_plain(label))
    sizer.Add(ctrl, proportion, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, _BORDER // 2)
    return ctrl


def _button(parent, sizer, label, handler):
    btn = wx.Button(parent, wx.ID_ANY, label)
    btn.Bind(wx.EVT_BUTTON, handler)
    sizer.Add(btn, 0, wx.RIGHT | wx.TOP, 4)
    return btn


def _announce(message, interrupt=False, delay=0):
    if delay <= 0:
        speak(message, interrupt=interrupt)
    else:
        wx.CallLater(delay, speak, message, interrupt)


def _confirm(parent, message, title):
    style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING
    return wx.MessageBox(message, title, style, parent) == wx.YES


def ask_download(parent, voice, card, runtime_size=0):
    """Show the download dialog; True when the user chose Download."""
    dlg = ConfirmDownloadDialog(parent, voice, card, runtime_size)
    try:
        return dlg.ShowModal() == wx.ID_OK
    finally:
        dlg.Destroy()


# ------------------------------------------------------------
# The download dialog
# ------------------------------------------------------------

class ConfirmDownloadDialog(wx.Dialog):
    """Says what will be downloaded before anything is: the voice, its quality,
    the size (with the Piper program the first time) and the dataset license
    from its model card. Enter downloads, Escape cancels."""

    def __init__(self, parent, voice, card, runtime_size=0):
        super().__init__(parent, title=_("confirm_title"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        root = wx.BoxSizer(wx.VERTICAL)
        # Screen readers read this text when the dialog opens.
        self.summary_text = text.confirm_summary(voice, card, runtime_size)
        self.lbl_summary = wx.StaticText(self, label=self.summary_text.replace("&", "&&"))
        self.lbl_summary.Wrap(480)
        root.Add(self.lbl_summary, 0, wx.ALL, _BORDER)
        card_text = "\n".join(text.card_lines(card)) or _("card_empty")
        self.txt_card = _labeled(
            self, root, _("lbl_card"),
            lambda: wx.TextCtrl(self, value=card_text, size=(-1, 100),
                                style=wx.TE_READONLY | wx.TE_MULTILINE),
            proportion=1)
        buttons = wx.StdDialogButtonSizer()
        self.btn_download = wx.Button(self, wx.ID_OK, _("btn_confirm_download"))
        self.btn_download.SetDefault()
        self.btn_cancel = wx.Button(self, wx.ID_CANCEL, _("btn_confirm_cancel"))
        buttons.AddButton(self.btn_download)
        buttons.AddButton(self.btn_cancel)
        buttons.Realize()
        root.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, _BORDER)
        self.SetSizer(root)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        apply_rtl_layout(self)
        _apply_appearance(self)
        self.Fit()
        width, height = self.GetSize()
        self.SetMinSize((width, height))
        self.SetSize((max(width, 440), height))
        self.CentreOnParent()
        self.btn_download.SetFocus()


# ------------------------------------------------------------
# The Preferences page
# ------------------------------------------------------------

class PiperVoicesPanel(wx.Panel):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self._c = controller
        self._alive = True
        self._voices = None          # the catalogue's voices, once loaded
        self._load_error = None
        self._installed = {}         # key -> installed voice
        self._rows = []              # the voices in the list, row by row
        self._families = [None]      # the Language choice's entries (None: all)
        self._family_chosen = False  # the user picked a language themselves
        self._cards = {}             # key -> parsed model card, fetched this session
        self._language_names = {}
        self._family_names = {}
        self._loading = False
        self._requested = False
        self._fetching_card = False
        self._filling = False

        root = wx.BoxSizer(wx.VERTICAL)
        intro = wx.StaticText(self, label=_("page_help"))
        intro.Wrap(560)
        root.Add(intro, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)

        self.choice_language = _labeled(self, root, _("lbl_language"),
                                        lambda: wx.Choice(self, choices=[_("language_all")]))
        self.choice_language.SetSelection(0)
        self.list_voices = _labeled(
            self, root, _("lbl_voices"),
            lambda: wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
                                size=(-1, 180)),
            proportion=1)
        columns = ((_("col_name"), 190), (_("col_language"), 190), (_("col_quality"), 100),
                   (_("col_size"), 90), (_("col_installed"), 120))
        for index, (label, width) in enumerate(columns):
            self.list_voices.InsertColumn(index, label, width=width)

        buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_download = _button(self, buttons, _("btn_download"), self.on_download)
        self.btn_remove = _button(self, buttons, _("btn_remove"), self.on_remove)
        self.btn_refresh = _button(self, buttons, _("btn_refresh"), self.on_refresh)
        self.btn_cancel = _button(self, buttons, _("btn_cancel_download"), self.on_cancel)
        root.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _BORDER)

        self.txt_status = _labeled(self, root, _("lbl_status"),
                                   lambda: wx.TextCtrl(self, style=wx.TE_READONLY))
        # Read-only but in the Tab order, so screen reader users can review it.
        self.txt_details = _labeled(
            self, root, _("lbl_details"),
            lambda: wx.TextCtrl(self, size=(-1, 130), style=wx.TE_READONLY | wx.TE_MULTILINE))
        self.gauge = _labeled(self, root, _("lbl_progress"), lambda: wx.Gauge(self, range=100))
        root.AddSpacer(_BORDER)
        self.SetSizer(root)

        self.choice_language.Bind(wx.EVT_CHOICE, self.on_language)
        self.list_voices.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_voice_selected)
        self.list_voices.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_activate)
        self.list_voices.Bind(wx.EVT_LIST_KEY_DOWN, self.on_list_key)
        self.Bind(wx.EVT_SHOW, self.on_show)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        self._c.downloads.add_listener(self._on_download_event)

        self._installed = self._c.installed()
        self._fill_languages()
        self._fill_list()
        self._show_download_state()
        # Large text and high contrast: Preferences applies them to every page
        # once they are all built. Preferences builds every page; only the one
        # showing loads the voice list.
        wx.CallAfter(self._load_if_shown)

    # --- state -------------------------------------------------------------------

    def _usable(self):
        try:
            return bool(self._alive and self)
        except RuntimeError:
            return False       # destroyed meanwhile

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._alive = False
            self._c.downloads.remove_listener(self._on_download_event)
        event.Skip()

    def _set_status(self, message, speak_it=False):
        self.txt_status.ChangeValue(message)      # ChangeValue: no "unsaved" mark
        if speak_it:
            _announce(message, True)

    # --- loading the voice list -----------------------------------------------

    def on_show(self, event):
        if event.IsShown():
            wx.CallAfter(self._load_if_shown)
        event.Skip()

    def _load_if_shown(self):
        if self._usable() and not self._requested and self.IsShown():
            self._requested = True
            self._load(force=False, announce=False)

    def _load(self, force, announce):
        if self._loading:
            if announce:
                _announce(_("loading"), True)
            return
        self._loading = True
        if announce:
            self._set_status(_("catalogue_refreshing"), speak_it=True)
        elif self._voices is None:
            self._set_status(_("loading"))
        self._c.load_catalogue(force, lambda result, error: self._loaded(result, error, announce))

    def _loaded(self, result, error, announce):
        if not self._usable():
            return
        self._loading = False
        self._installed = self._c.installed()
        if error is not None:
            logger.info(f"[Piper Voices] The voice list could not be loaded: {error}")
            self._load_error = error
            message = _("status_load_failed", error=text.error_text(error))
            if self._installed:
                message = f"{message} {_('status_installed_only')}"
        else:
            voices, stale = result
            self._voices = voices
            self._load_error = None
            ready = _("status_ready", count=len(voices), installed=len(self._installed))
            if stale is not None:
                message = _("status_stale", error=text.error_text(stale))
            elif announce:
                message = f"{_('catalogue_refreshed')} {ready}"
            else:
                message = ready
        self._fill_languages()
        self._fill_list()
        if self._c.downloads.current() is None:
            self._set_status(message, speak_it=announce)
        elif announce:
            _announce(message, True)

    # --- filling the controls -------------------------------------------------

    def _all_voices(self):
        """The catalogue's voices, and installed voices it doesn't list (it
        isn't loaded yet, or couldn't be)."""
        voices = list(self._voices or [])
        known = {v["key"] for v in voices}
        voices += [v for key, v in sorted(self._installed.items()) if key not in known]
        return voices

    def _family_name(self, family, voices):
        if family not in self._family_names:
            self._family_names[family] = text.family_label(family, voices)
        return self._family_names[family]

    def _language(self, voice):
        tag = voice.get("language") or ""
        if tag not in self._language_names:
            self._language_names[tag] = text.language_label(voice)
        return self._language_names[tag]

    def _selected_family(self):
        index = self.choice_language.GetSelection()
        return self._families[index] if 0 <= index < len(self._families) else None

    def _fill_languages(self):
        voices = self._all_voices()
        previous = self._selected_family()
        families = catalogue.language_choices(voices, core.voice.user_languages(),
                                              lambda f: self._family_name(f, voices))
        self._families = families
        self.choice_language.Set([self._family_name(f, voices) for f in families])
        if self._family_chosen and previous in families:
            index = families.index(previous)
        else:
            index = 0      # the user's language when it has voices, else all
        self.choice_language.SetSelection(index)

    def selected_voice(self):
        """The voice selected in the list, or None (nothing, or a message row)."""
        index = self.list_voices.GetFirstSelected()
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def selected_key(self):
        voice = self.selected_voice()
        return voice["key"] if voice else None

    def _fill_list(self):
        keep = self.selected_key()
        voices = catalogue.filter_voices(self._all_voices(), self._selected_family())
        rows = catalogue.order_voices(voices, core.voice.user_languages())
        lst = self.list_voices
        self._filling = True
        try:
            lst.DeleteAllItems()
            self._rows = rows
            if not rows:
                if self._voices is None and self._load_error is not None and not self._loading:
                    message = _("status_load_failed", error=text.error_text(self._load_error))
                elif self._voices is None or self._loading:
                    message = _("loading")
                else:
                    message = _("no_voices")
                lst.InsertItem(0, message)
            for i, voice in enumerate(rows):
                lst.InsertItem(i, text.voice_title(voice))
                lst.SetItem(i, 1, self._language(voice))
                lst.SetItem(i, 2, text.quality_label(voice.get("quality")))
                lst.SetItem(i, 3, text.size_label(voice["size"]) if voice.get("size") else "")
                lst.SetItem(i, 4, text.installed_label(voice["key"] in self._installed))
            if rows:
                index = next((i for i, v in enumerate(rows) if v["key"] == keep), 0)
                state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
                lst.SetItemState(index, state, state)
                lst.EnsureVisible(index)
        finally:
            self._filling = False
        self._show_details()

    def _update_installed_cells(self):
        """Only the Installed column changes, so the row a screen reader is on
        isn't rebuilt."""
        for i, voice in enumerate(self._rows):
            label = text.installed_label(voice["key"] in self._installed)
            if self.list_voices.GetItemText(i, 4) != label:
                self.list_voices.SetItem(i, 4, label)

    def _card_for(self, key):
        if key in self._cards:
            return self._cards[key]
        installed = self._installed.get(key)
        return installed.get("card") if installed else None

    def _show_details(self):
        voice = self.selected_voice()
        if voice is None:
            value = ""
        else:
            value = text.details_text(voice, voice["key"] in self._installed,
                                      self._card_for(voice["key"]))
        self.txt_details.ChangeValue(value)

    def _show_download_state(self):
        job = self._c.downloads.current()
        if job is None:
            self.gauge.SetValue(0)
        else:
            self.gauge.SetValue(job.percent)
            self._set_status(_("status_downloading", name=job.title, percent=job.percent))

    # --- events ----------------------------------------------------------------

    def on_language(self, event):
        # Only the list changes; focus stays on the choice. Not skipped:
        # Preferences would take it for an unsaved setting, and nothing on
        # this page waits for OK.
        self._family_chosen = True
        self._fill_list()

    def on_voice_selected(self, event):
        if not self._filling:
            self._show_details()
        event.Skip()

    def on_activate(self, event=None):
        self.on_download()

    def on_list_key(self, event):
        if event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
            self.on_remove()
        else:
            event.Skip()

    def on_download(self, event=None):
        voice = self.selected_voice()
        if voice is None:
            _announce(_("nothing_selected"), True)
            return
        title = text.voice_title(voice)
        if voice["key"] in self._installed:
            _announce(_("already_installed", name=title), True)
            return
        if self._c.downloads.current() is not None or self._fetching_card:
            _announce(_("busy"), True)
            return
        if "files" not in voice:
            _announce(_("not_in_catalogue", name=title), True)
            return
        self._fetching_card = True
        self._set_status(_("status_card", name=title), speak_it=True)
        self._c.fetch_card(voice, lambda card_text, error: self._card_ready(voice, card_text,
                                                                             error))

    def _card_ready(self, voice, card_text, error):
        if not self._usable():
            return
        self._fetching_card = False
        title = text.voice_title(voice)
        if error is not None:
            logger.info(f"[Piper Voices] The model card of {voice['key']} failed: {error}")
            self._set_status(_("card_failed", name=title, error=text.error_text(error)),
                             speak_it=True)
            return
        card = catalogue.parse_model_card(card_text)
        self._cards[voice["key"]] = card
        if self.selected_key() == voice["key"]:
            self._show_details()
        if voice["key"] in self._installed or self._c.downloads.current() is not None:
            return
        runtime = 0 if self._c.runtime_installed() else self._c.runtime_size()
        if not ask_download(self, voice, card, runtime):
            self._set_status(_("download_declined", name=title))
            return
        if not self._c.downloads.start(voice, card_text):
            _announce(_("busy"), True, ANNOUNCE_DELAY_MS)
            return
        self._show_download_state()

    def on_remove(self, event=None):
        voice = self.selected_voice()
        if voice is None:
            _announce(_("nothing_selected"), True)
            return
        title = text.voice_title(voice)
        if voice["key"] not in self._installed:
            _announce(_("not_installed", name=title), True)
            return
        job = self._c.downloads.current()
        if job is not None and job.key == voice["key"]:
            _announce(_("busy"), True)
            return
        if not _confirm(self, _("confirm_remove", name=title), _("confirm_remove_title")):
            return
        try:
            self._c.remove_voice(voice["key"])
        except OSError as e:
            logger.info(f"[Piper Voices] Removing {voice['key']} failed: {e}")
            message = _("remove_failed", name=title)
        else:
            message = _("removed", name=title)
        self._installed = self._c.installed()
        self._update_installed_cells()
        self._show_details()
        self._set_status(message)
        _announce(message, True, ANNOUNCE_DELAY_MS)

    def on_refresh(self, event=None):
        self._requested = True
        self._load(force=True, announce=True)

    def on_cancel(self, event=None):
        if self._c.downloads.cancel():
            self._set_status(_("status_cancelling"), speak_it=True)
        else:
            _announce(_("nothing_downloading"), True)

    # --- downloads (on the UI thread) -------------------------------------------

    def _on_download_event(self, event, job, value):
        if not self._usable():
            return
        if event == "progress":
            self.gauge.SetValue(value)
            self._set_status(_("status_downloading", name=job.title, percent=value))
            return
        self._installed = self._c.installed()
        if value is None:
            self.gauge.SetValue(100)
            message = _("download_done", name=job.title)
        elif isinstance(value, download.Cancelled):
            self.gauge.SetValue(0)
            message = _("download_cancelled")
        else:
            self.gauge.SetValue(0)
            message = _("download_failed", error=text.error_text(value))
        self._set_status(message)       # the extension speaks it
        self._update_installed_cells()
        self._show_details()
