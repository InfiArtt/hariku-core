# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The Voice Control page in Preferences: download or remove the whisper.cpp
program, the speech models and the wake phrase listener (with their sizes,
progress and Cancel), the recognition model, "Start listening as soon as the
command bar opens", the silence that ends listening, the microphone
sensitivity, a microphone test that measures a sentence and sets the
sensitivity that suits it, and the wake phrase: "Listen for a wake phrase",
the phrase (with advice about it, said when it changes), its sensitivity,
"Pause the wake phrase during quiet hours" and a test that listens for the
phrase for 20 seconds and says "Heard it" each time.

Every control comes right after the label that names it (screen readers name
a control after the static text created just before it; SetName alone
doesn't change that). Selecting a row only shows its details; focus never
moves by itself. Download, Remove, Cancel and the tests act at once; the
settings, including a sensitivity the microphone test chose, are saved with
OK or Apply. The status line also says whether the wake phrase is heard.
"""
import logging
import threading

import wx

import core.ui_scale
from core.speech import speak

import voice_control_download as download
import voice_control_store as store
import voice_control_text as text
import voice_control_wake as wake
from voice_control_text import _

logger = logging.getLogger(__name__)

_BORDER = 8
ANNOUNCE_DELAY_MS = 300     # after a message box closes, so the focus announcement doesn't cut it
MIC_TEST_DELAY_MS = 2000    # "say a sentence" is said before the tone (listening silences it)
ADVICE_DELAY_MS = 700       # the advice about the phrase waits for typing to pause
WHISPER_ITEMS = ("runtime", "tiny", "base", "small")


def _plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


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


def _announce(message, interrupt=True, delay=0):
    if delay <= 0:
        speak(message, interrupt=interrupt)
    else:
        wx.CallLater(delay, speak, message, interrupt)


def ask(parent, message, title):
    """A Yes/No question, No by default (a module function, so checks can
    answer it)."""
    style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
    return wx.MessageBox(message, title, style, parent) == wx.YES


# The page is taller than the Preferences dialog, so it scrolls (and scrolls
# the focused control into view). A plain panel where wx is not the real one.
_PageBase = wx.ScrolledWindow if isinstance(getattr(wx, "ScrolledWindow", None), type) else wx.Panel


class VoiceControlPanel(_PageBase):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self._c = controller
        self._alive = True
        self._testing = False
        self._wake_stop = None            # the running wake phrase test's stop Event
        self._advice_timer = None
        self._advice_problem = None
        self._status_message = ""
        self._installed = self._c.installed()
        settings = self._c.settings()
        self._speeds = settings["speeds"]
        self._wake_was_on = settings["wake"]
        self._rows = list(text.ITEMS)

        root = wx.BoxSizer(wx.VERTICAL)
        intro = wx.StaticText(self, label=_("page_help"))
        intro.Wrap(560)
        root.Add(intro, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)

        self.list_items = _labeled(
            self, root, _("lbl_downloads"),
            lambda: wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
                                size=(-1, 120)),
            proportion=1)
        for index, (label, width) in enumerate(((_("col_name"), 300), (_("col_size"), 90),
                                                (_("col_status"), 190))):
            self.list_items.InsertColumn(index, label, width=width)

        buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_download = _button(self, buttons, _("btn_download"), self.on_download)
        self.btn_remove = _button(self, buttons, _("btn_remove"), self.on_remove)
        self.btn_cancel = _button(self, buttons, _("btn_cancel_download"), self.on_cancel)
        root.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _BORDER)

        self.gauge = _labeled(self, root, _("lbl_progress"), lambda: wx.Gauge(self, range=100))
        self.txt_status = _labeled(self, root, _("lbl_status"),
                                   lambda: wx.TextCtrl(self, style=wx.TE_READONLY))

        self._model_keys = [key for key, _label in text.model_choices()]
        self.choice_model = _labeled(
            self, root, _("lbl_model"),
            lambda: wx.Choice(self, choices=[label for _key, label in text.model_choices()]))
        self.choice_model.SetSelection(self._model_keys.index(settings["model"])
                                       if settings["model"] in self._model_keys else 0)

        self.chk_listen = wx.CheckBox(self, label=_("chk_listen_on_open"))
        self.chk_listen.SetValue(settings["listen_on_open"])
        root.Add(self.chk_listen, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)

        self._silences = list(store.SILENCE_CHOICES)
        self.choice_silence = _labeled(
            self, root, _("lbl_silence"),
            lambda: wx.Choice(self, choices=[text.silence_label(ms) for ms in self._silences]))
        self.choice_silence.SetSelection(self._silences.index(settings["silence_ms"])
                                         if settings["silence_ms"] in self._silences else 2)

        self._sensitivities = [name for name, _label in text.sensitivity_choices()]
        self.choice_sensitivity = _labeled(
            self, root, _("lbl_sensitivity"),
            lambda: wx.Choice(self, choices=[label for _name, label in text.sensitivity_choices()]))
        self.choice_sensitivity.SetSelection(self._sensitivity_index(settings["sensitivity"]))

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_test = _button(self, row, _("btn_test_mic"), self.on_test)
        root.Add(row, 0, wx.LEFT | wx.RIGHT, _BORDER)
        self.txt_test = _labeled(self, root, _("lbl_test_result"),
                                 lambda: wx.TextCtrl(self, style=wx.TE_READONLY))

        # The wake phrase.
        wake_help = wx.StaticText(self, label=_("wake_help"))
        wake_help.Wrap(560)
        root.Add(wake_help, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        self.chk_wake = wx.CheckBox(self, label=_("chk_wake"))
        self.chk_wake.SetValue(settings["wake"])
        root.Add(self.chk_wake, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        self.txt_phrase = _labeled(self, root, _("lbl_wake_phrase"),
                                   lambda: wx.TextCtrl(self))
        self.txt_phrase.SetMaxLength(wake.MAX_PHRASE_CHARS)
        self.txt_phrase.ChangeValue(settings["wake_phrase"])     # not a change by the user
        self.txt_advice = _labeled(self, root, _("lbl_wake_advice"),
                                   lambda: wx.TextCtrl(self, size=(-1, 60),
                                                       style=wx.TE_READONLY | wx.TE_MULTILINE))
        self._wake_sensitivities = [name for name, _label in text.wake_sensitivity_choices()]
        self.choice_wake_sensitivity = _labeled(
            self, root, _("lbl_wake_sensitivity"),
            lambda: wx.Choice(self, choices=[label for _name, label
                                             in text.wake_sensitivity_choices()]))
        self.choice_wake_sensitivity.SetSelection(
            self._wake_sensitivity_index(settings["wake_sensitivity"]))
        self.chk_wake_quiet = wx.CheckBox(self, label=_("chk_wake_quiet"))
        self.chk_wake_quiet.SetValue(settings["wake_quiet_hours"])
        root.Add(self.chk_wake_quiet, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_test_wake = _button(self, row, _("btn_test_wake"), self.on_test_wake)
        root.Add(row, 0, wx.LEFT | wx.RIGHT, _BORDER)
        self.txt_wake_test = _labeled(self, root, _("lbl_wake_test"),
                                      lambda: wx.TextCtrl(self, style=wx.TE_READONLY))

        note = wx.StaticText(self, label=_("page_headset"))
        note.Wrap(560)
        root.Add(note, 0, wx.ALL, _BORDER)
        self.SetSizer(root)
        if hasattr(self, "SetScrollRate"):
            self.SetScrollRate(0, 20)

        self.list_items.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_download)
        self.list_items.Bind(wx.EVT_LIST_KEY_DOWN, self.on_list_key)
        self.txt_phrase.Bind(wx.EVT_TEXT, self.on_phrase_text)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        self._c.downloads.add_listener(self._on_download_event)
        self._c.add_wake_listener(self._on_wake_state)

        self._fill_list()
        self._show_download_state()
        self._update_advice(speak_it=False)
        try:
            core.ui_scale.apply_appearance(self)
        except Exception:
            pass
        if hasattr(self, "FitInside"):
            self.FitInside()      # after scaling, so large text can still be scrolled to

    # --- state -------------------------------------------------------------------

    def _usable(self):
        try:
            return bool(self._alive and self)
        except RuntimeError:
            return False

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._alive = False
            self._c.downloads.remove_listener(self._on_download_event)
            self._c.remove_wake_listener(self._on_wake_state)
            if self._wake_stop is not None:
                self._wake_stop.set()           # the page is gone: stop listening
            timer, self._advice_timer = self._advice_timer, None
            if timer is not None:
                try:
                    timer.Stop()
                except Exception:
                    pass
        event.Skip()

    def _mark_dirty(self):
        top = wx.GetTopLevelParent(self)
        if top is not None and hasattr(top, "is_dirty"):
            top.is_dirty = True

    def _sensitivity_index(self, name):
        if name in self._sensitivities:
            return self._sensitivities.index(name)
        return self._sensitivities.index(store.DEFAULT_SETTINGS["sensitivity"])

    def _wake_sensitivity_index(self, name):
        if name in self._wake_sensitivities:
            return self._wake_sensitivities.index(name)
        return self._wake_sensitivities.index(wake.DEFAULT_SENSITIVITY)

    def select_sensitivity(self, name):
        """Show a sensitivity the microphone test chose (saved with OK or
        Apply, like a choice the user made). Focus stays where it is."""
        index = self._sensitivity_index(name)
        if self.choice_sensitivity.GetSelection() != index:
            self.choice_sensitivity.SetSelection(index)
            self._mark_dirty()

    def _set_status(self, message, speak_it=False):
        """Show `message` in the status line, followed by what the wake phrase
        is doing (only `message` is said)."""
        self._status_message = message
        state, phrase = self._c.wake_state()
        extra = text.wake_status(state, phrase)
        self.txt_status.ChangeValue(f"{message} {extra}" if extra else message)   # not a setting
        if speak_it:
            _announce(message)

    def _on_wake_state(self, state):
        if self._usable():
            self._set_status(self._status_message)

    def _status_text(self, item, percent=None):
        return text.status_label(item, self._installed.get(item), self._speeds, percent)

    def _fill_list(self):
        keep = self.selected_item()
        lst = self.list_items
        lst.DeleteAllItems()
        for i, item in enumerate(self._rows):
            lst.InsertItem(i, text.item_name(item))
            lst.SetItem(i, 1, text.size_label(text.item_size(item)))
            lst.SetItem(i, 2, self._status_text(item))
        index = self._rows.index(keep) if keep in self._rows else 1   # the tiny model
        state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
        lst.SetItemState(index, state, state)

    def _update_status_cells(self, job=None, percent=None):
        """Only the Status column changes, so the row a screen reader is on
        isn't rebuilt."""
        for i, item in enumerate(self._rows):
            downloading = job is not None and percent is not None and (
                item == job.item or (item == "runtime" and job.need_runtime))
            label = self._status_text(item, percent if downloading else None)
            if self.list_items.GetItemText(i, 2) != label:
                self.list_items.SetItem(i, 2, label)

    def _refresh(self):
        self._installed = self._c.installed()
        self._speeds = self._c.settings()["speeds"]
        self._update_status_cells()

    def selected_item(self):
        index = self.list_items.GetFirstSelected() if self.list_items.GetItemCount() else -1
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def _show_download_state(self):
        job = self._c.downloads.current()
        if job is None:
            self.gauge.SetValue(0)
            models = [i for i in WHISPER_ITEMS if i != "runtime" and self._installed.get(i)]
            if not self._installed.get("runtime") or not models:
                self._set_status(_("status_not_ready"))
            else:
                self._set_status(_("status_ready"))
        else:
            self.gauge.SetValue(job.percent)
            self._set_status(_("status_downloading", name=job.title, percent=job.percent))

    # --- events ----------------------------------------------------------------

    def on_list_key(self, event):
        if event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
            self.on_remove()
        else:
            event.Skip()

    def on_download(self, event=None):
        item = self.selected_item()
        if item is None:
            _announce(_("nothing_selected"))
            return
        name = text.item_name(item)
        if self._installed.get(item):
            _announce(_("already_installed", name=name))
            return
        if self._c.downloads.current() is not None:
            _announce(_("busy"))
            return
        need_runtime = item != "runtime" and not self._installed.get("runtime")
        if not ask(self, text.confirm_download(item, need_runtime), _("confirm_title")):
            self._set_status(_("download_declined", name=name))
            return
        if not self._c.downloads.start(item):
            _announce(_("busy"), delay=ANNOUNCE_DELAY_MS)
            return
        self._show_download_state()

    def on_remove(self, event=None):
        item = self.selected_item()
        if item is None:
            _announce(_("nothing_selected"))
            return
        name = text.item_name(item)
        if not self._installed.get(item):
            _announce(_("not_installed", name=name))
            return
        if self._c.downloads.current() is not None:
            _announce(_("busy"))
            return
        if not ask(self, _("confirm_remove", name=name), _("confirm_remove_title")):
            return
        try:
            removed = self._c.remove(item)
        except OSError as e:
            logger.info(f"[Voice Control] Removing {item} failed: {e}")
            message = _("remove_failed", name=name)
        else:
            message = _("remove_later" if removed == "later" else "removed", name=name)
        self._refresh()
        self._show_download_state()
        self._set_status(message)
        _announce(message, delay=ANNOUNCE_DELAY_MS)

    def on_cancel(self, event=None):
        if self._c.downloads.cancel():
            self._set_status(_("status_cancelling"), speak_it=True)
        else:
            _announce(_("nothing_downloading"))

    def on_test(self, event=None):
        if self._testing:
            _announce(_("mic_test_running"))
            return
        self._testing = True
        self.txt_test.ChangeValue(_("mic_test_speak"))
        _announce(_("mic_test_speak"))
        # The test waits a moment for that sentence before the tone and silence.
        wx.CallLater(MIC_TEST_DELAY_MS, self._start_test)

    def _start_test(self):
        if not self._usable():
            return
        self._c.test_microphone(self._test_done)

    def _test_done(self, result, error):
        if not self._usable():
            return
        self._testing = False
        message, sensitivity = text.mic_test_outcome(result, error)
        if sensitivity is not None:
            self.select_sensitivity(sensitivity)
        self.txt_test.ChangeValue(message)
        _announce(message)

    # --- the wake phrase ----------------------------------------------------------

    def on_phrase_text(self, event):
        """Typing in Wake phrase: the advice follows once typing pauses."""
        event.Skip()                 # Preferences marks the change
        timer = self._advice_timer
        if timer is not None and timer.IsRunning():
            timer.Restart(ADVICE_DELAY_MS)
        else:
            self._advice_timer = wx.CallLater(ADVICE_DELAY_MS, self._update_advice, True)

    def _update_advice(self, speak_it=False):
        """Show the advice about the phrase; say it when what's wrong with
        the phrase changed."""
        if not self._usable():
            return
        problem = wake.phrase_problem(self.txt_phrase.GetValue())
        message = text.wake_advice(problem)
        if self.txt_advice.GetValue() != message:
            self.txt_advice.ChangeValue(message)
        if speak_it and problem != self._advice_problem:
            _announce(message, interrupt=False)
        self._advice_problem = problem

    def _wake_sensitivity(self):
        index = self.choice_wake_sensitivity.GetSelection()
        if 0 <= index < len(self._wake_sensitivities):
            return self._wake_sensitivities[index]
        return wake.DEFAULT_SENSITIVITY

    def _show_wake_test(self, message, speak_it=True):
        self.txt_wake_test.ChangeValue(message)
        if speak_it:
            _announce(message)

    def on_test_wake(self, event=None):
        """Listen for the phrase on the page (not yet saved) for 20 seconds;
        pressed again, stop."""
        if self._wake_stop is not None:
            self._wake_stop.set()
            return
        phrase = wake.tidy(self.txt_phrase.GetValue())
        if not wake.usable(phrase):
            self._show_wake_test(_("wake_test_bad_phrase"))
            return
        if not self._installed.get("wake"):
            self._show_wake_test(_("wake_not_installed"))
            return
        stop = self._wake_stop = threading.Event()
        message = _("wake_test_speak", phrase=phrase, seconds=wake.TEST_SECONDS)
        self._show_wake_test(message)
        # The test starts once that is said (it would be ignored anyway).
        delay = int(wake.speech_seconds(message) * 1000)
        wx.CallLater(delay, self._start_wake_test, phrase, self._wake_sensitivity(), stop)

    def _start_wake_test(self, phrase, sensitivity, stop):
        if not self._usable() or stop is not self._wake_stop:
            return
        if stop.is_set():
            self._wake_test_done({"count": 0, "seconds": 0, "stopped": True}, None)
            return
        self._show_wake_test(_("wake_test_listening", phrase=phrase), speak_it=False)
        self._c.test_wake(phrase, sensitivity, self._wake_heard, self._wake_test_done, stop)

    def _wake_heard(self, count):
        if self._usable() and self._wake_stop is not None:
            self._show_wake_test(text.wake_heard(count))

    def _wake_test_done(self, result, error):
        if not self._usable():
            return
        self._wake_stop = None
        self._show_wake_test(text.wake_test_message(result, error))

    # --- downloads (on the UI thread) -------------------------------------------

    def _on_download_event(self, event, job, value):
        if not self._usable():
            return
        if event == "progress":
            self.gauge.SetValue(value)
            self._set_status(_("status_downloading", name=job.title, percent=value))
            self._update_status_cells(job, value)
            return
        self.gauge.SetValue(100 if value is None else 0)
        self._refresh()
        if value is None:
            message = _("download_done", name=job.title)
        elif isinstance(value, download.Cancelled):
            message = _("download_cancelled")
        else:
            message = _("download_failed", error=text.download_error(value))
        self._set_status(message)       # the extension speaks it

    # --- saving ------------------------------------------------------------------

    def get_settings(self):
        model_index = self.choice_model.GetSelection()
        silence_index = self.choice_silence.GetSelection()
        sensitivity_index = self.choice_sensitivity.GetSelection()
        return {
            "model": self._model_keys[model_index] if 0 <= model_index < len(self._model_keys)
            else "auto",
            "listen_on_open": self.chk_listen.GetValue(),
            "silence_ms": self._silences[silence_index]
            if 0 <= silence_index < len(self._silences) else 1000,
            "sensitivity": self._sensitivities[sensitivity_index]
            if 0 <= sensitivity_index < len(self._sensitivities)
            else store.DEFAULT_SETTINGS["sensitivity"],
            "wake": {
                "enabled": self.chk_wake.GetValue(),
                "phrase": wake.tidy(self.txt_phrase.GetValue()) or wake.DEFAULT_PHRASE,
                "sensitivity": self._wake_sensitivity(),
                "quiet_hours": self.chk_wake_quiet.GetValue(),
            },
        }

    def ValidateChanges(self):
        """Preferences asks before saving: with the wake phrase on, a phrase
        the model can't hear (empty, digits, other letters) keeps the dialog
        open, with the reason said and focus in Wake phrase."""
        phrase = self.txt_phrase.GetValue()
        if self.chk_wake.GetValue() and not wake.usable(phrase):
            return text.wake_advice(wake.phrase_problem(phrase)), self.txt_phrase
        return None

    def ApplyChanges(self):
        values = self.get_settings()
        self._c.save_settings(values["model"], values["listen_on_open"], values["silence_ms"],
                              values["sensitivity"], values["wake"])
        turned_on = values["wake"]["enabled"] and not self._wake_was_on
        self._wake_was_on = values["wake"]["enabled"]
        if turned_on and not self._c.installed().get("wake"):
            _announce(_("wake_saved_missing"), delay=ANNOUNCE_DELAY_MS)
