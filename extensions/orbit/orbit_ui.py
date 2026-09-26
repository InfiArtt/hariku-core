# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Orbit's windows: the game window and the Preferences page.

The game window has the Messages box (read-only text, newest line last, read
with the arrow keys like any text; a reply of several parts takes a line for
each, so the client's "message" and "trim" counts are lines of the box; a new
line never moves the focus, nor your reading place while you're in it), the Command
field (Enter sends; Up and Down bring back earlier commands), Connect or
Leave Orbit, Help, Settings (Orbit's Preferences page), and the status; the
title says whether you're connected. Escape or closing it does what the
Preferences say: Orbit stays connected in the background (the default), or
you leave Orbit.

Every label is created right before the control it names (screen readers
name a control after the static text created just before it; SetName
doesn't change that). Nothing here moves the focus, except opening the
window, which puts it in the Command field.
"""

import wx

import core.ui_scale
from core.i18n import apply_rtl_layout

from orbit_text import _

_BORDER = 10
HISTORY = 50
BACKGROUND_MODES = ("all", "important", "none")
READERS = ("mixed", "nvda", "voices")
MAX_LINES = 2000
CLOSE_ACTIONS = ("stay", "leave")
AUTO_LOGOUT = (0, 15, 30, 60)
READ_SETTINGS = ("read_say", "read_whisper", "read_shout", "read_moves", "read_money", "read_announce",
                 "read_events")


def _plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def _labeled(parent, sizer, label, make, proportion=0):
    """A label, then the control it names, with the same accessible name."""
    static = wx.StaticText(parent, label=label)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
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


def _button(parent, sizer, label):
    button = wx.Button(parent, label=label)
    sizer.Add(button, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
    return button


# A page that scrolls (it's long); a plain panel where wx has no scrolled window.
_PageBase = wx.ScrolledWindow if isinstance(getattr(wx, "ScrolledWindow", None), type) else wx.Panel


def _alive(window):
    try:
        return bool(window) and not window.IsBeingDeleted()
    except RuntimeError:
        return False


class OrbitFrame(wx.Frame):
    """`client` is orbit_play.OrbitClient; `on_visibility()` is called when
    the window is shown or hidden (the ambience follows it); `on_settings()`
    opens Orbit's Preferences page."""

    def __init__(self, client, on_visibility=None, on_settings=None):
        super().__init__(None, title=_("window_title"), size=(680, 540))
        self.client = client
        self._on_visibility = on_visibility
        self._on_settings = on_settings
        self._history = []
        self._history_at = None
        self.closing = False
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.txt_messages = _labeled(
            panel, sizer, _("lbl_messages"),
            lambda: wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
                                | wx.TE_NOHIDESEL),
            proportion=1)
        self.txt_command = _labeled(panel, sizer, _("lbl_command"),
                                    lambda: wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER))
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_connect = wx.Button(panel, label=_("btn_connect"))
        self.btn_help = wx.Button(panel, label=_("btn_help"))
        self.btn_remind = wx.Button(panel, label=_("btn_remind"))
        self.btn_settings = wx.Button(panel, label=_("btn_settings"))
        row.Add(self.btn_connect, 0, wx.RIGHT, _BORDER)
        row.Add(self.btn_help, 0, wx.RIGHT, _BORDER)
        row.Add(self.btn_remind, 0, wx.RIGHT, _BORDER)
        row.Add(self.btn_settings, 0)
        sizer.Add(row, 0, wx.ALL, _BORDER)
        self.txt_status = _labeled(panel, sizer, _("lbl_status"),
                                   lambda: wx.TextCtrl(panel, value=client.status,
                                                       style=wx.TE_READONLY))
        sizer.AddSpacer(_BORDER)
        panel.SetSizer(sizer)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.txt_messages.ChangeValue("\n".join(client.messages))
        self.txt_command.Bind(wx.EVT_TEXT_ENTER, self._on_enter)
        self.txt_command.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.btn_connect.Bind(wx.EVT_BUTTON, self._on_connect)
        self.btn_help.Bind(wx.EVT_BUTTON, lambda event: self.client.submit("help"))
        self.btn_remind.Bind(wx.EVT_BUTTON, lambda event: self.client.remind(""))
        self.btn_settings.Bind(wx.EVT_BUTTON, self._on_settings_button)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_SHOW, self._on_show)
        client.add_listener(self.on_client)
        self._update_buttons()

    # --- showing and hiding -----------------------------------------------------------

    def show_and_focus(self):
        if self.IsIconized():
            self.Iconize(False)
        self.Show()
        self.Raise()
        self.txt_command.SetFocus()

    def hide(self):
        self.Hide()

    def close_request(self):
        """Escape or the close button: hide, and stay connected or leave (the setting)."""
        self.hide()
        self.client.window_closing()

    def _on_show(self, event):
        event.Skip()
        if self._on_visibility is not None:
            wx.CallAfter(self._on_visibility)

    def _on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.close_request()
            return
        event.Skip()

    def _on_close(self, event):
        if event.CanVeto() and not self.closing:
            event.Veto()
            self.close_request()
            return
        self.client.remove_listener(self.on_client)
        event.Skip()

    def destroy(self):
        self.closing = True
        self.client.remove_listener(self.on_client)
        self.Destroy()

    def _on_settings_button(self, event):
        if self._on_settings is not None:
            self._on_settings()

    # --- the client's news ------------------------------------------------------------

    def on_client(self, event, value):
        if not _alive(self):
            raise RuntimeError("the window is gone")
        if event == "message":
            self.append_line(value)
        elif event == "trim":
            self.trim_lines(int(value))
        elif event == "status":
            self.txt_status.ChangeValue(value)
            self._update_buttons()
        elif event == "state":
            self._update_buttons()

    def lines(self):
        text = self.txt_messages.GetValue()
        return text.split("\n") if text else []

    def append_line(self, line):
        """Add a line at the end. Someone reading the box keeps their place
        (the caret and any selection stay put); otherwise it follows the end."""
        box = self.txt_messages
        reading = wx.Window.FindFocus() is box
        if reading:
            start, end = box.GetSelection()
        box.AppendText(("\n" if box.GetLastPosition() > 0 else "") + str(line))
        if reading:
            box.SetSelection(start, end)

    def trim_lines(self, count):
        """Drop the oldest `count` lines (the client keeps the last few hundred)."""
        box = self.txt_messages
        lines = self.lines()
        count = min(count, len(lines))
        if count <= 0:
            return
        cut = len("\n".join(lines[:count])) + (1 if count < len(lines) else 0)
        reading = wx.Window.FindFocus() is box
        start, end = box.GetSelection()
        box.Remove(0, cut)
        if reading:
            box.SetSelection(max(0, start - cut), max(0, end - cut))

    def _update_buttons(self):
        busy = self.client.online() or self.client.connecting()
        label = _("btn_leave") if busy else _("btn_connect")
        if self.btn_connect.GetLabel() != label:
            self.btn_connect.SetLabel(label)
            self.Layout()
        title = f"{_('window_title')}: {self.client.title_state}"
        if self.GetTitle() != title:
            self.SetTitle(title)

    # --- typing -----------------------------------------------------------------------

    def _on_enter(self, event):
        text = self.txt_command.GetValue().strip()
        if not text:
            return
        if not self._history or self._history[-1] != text:
            self._history.append(text)
            del self._history[:-HISTORY]
        self._history_at = None
        self.txt_command.ChangeValue("")
        self.client.submit(text, "window")

    def _on_key(self, event):
        key = event.GetKeyCode()
        if key not in (wx.WXK_UP, wx.WXK_DOWN) or event.HasAnyModifiers() or not self._history:
            event.Skip()
            return
        if self._history_at is None:
            self._history_at = len(self._history)
        step = -1 if key == wx.WXK_UP else 1
        self._history_at = max(0, min(len(self._history), self._history_at + step))
        text = self._history[self._history_at] if self._history_at < len(self._history) else ""
        self.txt_command.ChangeValue(text)
        self.txt_command.SetInsertionPointEnd()

    def _on_connect(self, event):
        if self.client.online() or self.client.connecting():
            self.client.disconnect()
        else:
            self.client.connect()
        self._update_buttons()


class OrbitPanel(_PageBase):
    """The Preferences page. `actions` has connect(server, name, job),
    disconnect(), busy(), online(), status(), character(server) -> account
    or None, request_transfer_code(), redeem_transfer(code, server),
    transfer_code(), add_listener(fn) and remove_listener(fn)."""

    JOBS = ("pilot", "engineer", "trader", "scientist", "security")

    def __init__(self, parent, settings, actions):
        super().__init__(parent)
        if hasattr(self, "SetScrollRate"):
            self.SetScrollRate(0, 20)
        self.actions = actions
        sizer = wx.BoxSizer(wx.VERTICAL)
        # The character
        self.txt_server = _labeled(self, sizer, _("lbl_server"),
                                   lambda: wx.TextCtrl(self, value=settings["server"]))
        self.txt_name = _labeled(self, sizer, _("lbl_name"),
                                 lambda: wx.TextCtrl(self, value=settings["name"]))
        self.ch_job = _labeled(self, sizer, _("lbl_job"),
                               lambda: wx.Choice(self, choices=[_(f"job_{j}") for j in self.JOBS]))
        self.ch_job.SetSelection(self.JOBS.index(settings["job"]) if settings["job"] in self.JOBS else 0)
        account = actions.character(settings["server"])
        if account and account.get("joined"):
            text = _("note_character", name=account.get("name", ""),
                     job=_(f"job_{account.get('job')}") if account.get("job") in self.JOBS else "")
        else:
            text = _("note_first")
        self.lbl_character = _note(self, sizer, text)
        self.btn_connect = _button(self, sizer, _("btn_connect"))
        self.txt_status = _labeled(self, sizer, _("lbl_status"),
                                   lambda: wx.TextCtrl(self, value=actions.status(),
                                                       style=wx.TE_READONLY))
        # Reading aloud
        self.ch_reader = _labeled(
            self, sizer, _("lbl_reader"),
            lambda: wx.Choice(self, choices=[_(f"reader_{r}") for r in READERS]))
        self.ch_reader.SetSelection(READERS.index(settings.get("reader", "mixed"))
                                    if settings.get("reader", "mixed") in READERS else 0)
        self.chk_speak = _check(self, sizer, _("chk_speak"), settings["speak"])
        self.chk_voices = _check(self, sizer, _("chk_voices"), settings["voices"])
        self.chk_speak_own = _check(self, sizer, _("chk_speak_own"), settings.get("speak_own", True))
        self.chk_speak_names = _check(self, sizer, _("chk_speak_names"), settings.get("speak_names", True))
        _note(self, sizer, _("lbl_read"))
        self.chk_read = {}
        for key in READ_SETTINGS:
            self.chk_read[key] = _check(self, sizer, _(f"chk_{key}"), settings.get(key, True))
        self.ch_background = _labeled(
            self, sizer, _("lbl_background"),
            lambda: wx.Choice(self, choices=[_(f"background_{m}") for m in BACKGROUND_MODES]))
        self.ch_background.SetSelection(BACKGROUND_MODES.index(settings.get("background", "important")))
        # Leaving
        self.ch_close = _labeled(self, sizer, _("lbl_close"),
                                 lambda: wx.Choice(self, choices=[_(f"close_{c}") for c in CLOSE_ACTIONS]))
        self.ch_close.SetSelection(CLOSE_ACTIONS.index(settings.get("close_action", "stay")))
        self.ch_logout = _labeled(
            self, sizer, _("lbl_auto_logout"),
            lambda: wx.Choice(self, choices=[_("logout_never") if m == 0 else _("logout_minutes", n=m)
                                             for m in AUTO_LOGOUT]))
        self.ch_logout.SetSelection(AUTO_LOGOUT.index(settings.get("auto_logout", 30)))
        self.chk_autoconnect = _check(self, sizer, _("chk_autoconnect"), settings.get("autoconnect", False))
        # Sound
        self.chk_ambience = _check(self, sizer, _("chk_ambience"), settings["ambience"])
        self.sld_volume = _labeled(self, sizer, _("lbl_volume"),
                                   lambda: wx.Slider(self, value=int(settings["ambience_volume"]),
                                                     minValue=0, maxValue=100))
        self.sld_volume.SetLineSize(5)
        self.sld_volume.SetPageSize(10)
        self.chk_sounds = _check(self, sizer, _("chk_sounds"), settings["sounds"])
        self.sld_effects = _labeled(self, sizer, _("lbl_effects_volume"),
                                    lambda: wx.Slider(self, value=int(settings.get("effects_volume", 100)),
                                                      minValue=0, maxValue=100))
        self.sld_effects.SetLineSize(5)
        self.sld_effects.SetPageSize(10)
        self.chk_other_sounds = _check(self, sizer, _("chk_other_sounds"), settings.get("other_sounds", True))
        # Players you don't want to hear
        self.txt_ignored = _labeled(self, sizer, _("lbl_ignored"),
                                    lambda: wx.TextCtrl(self, value=", ".join(settings.get("ignored") or [])))
        # Moving the character to another computer
        _note(self, sizer, _("note_transfer"))
        self.btn_transfer = _button(self, sizer, _("btn_transfer"))
        self.txt_transfer = _labeled(self, sizer, _("lbl_transfer_code"),
                                     lambda: wx.TextCtrl(self, value=actions.transfer_code(),
                                                         style=wx.TE_READONLY))
        self.txt_redeem = _labeled(self, sizer, _("lbl_redeem"), lambda: wx.TextCtrl(self))
        self.btn_redeem = _button(self, sizer, _("btn_redeem"))
        _note(self, sizer, _("note_quick"))
        _note(self, sizer, _("note_voices"))
        _note(self, sizer, _("note_privacy"))
        sizer.AddSpacer(_BORDER)
        self.SetSizer(sizer)
        if hasattr(self, "FitInside"):
            self.FitInside()

        self.chk_speak.Bind(wx.EVT_CHECKBOX, lambda event: self._follow())
        self.chk_ambience.Bind(wx.EVT_CHECKBOX, lambda event: self._follow())
        self.chk_sounds.Bind(wx.EVT_CHECKBOX, lambda event: self._follow())
        self.btn_connect.Bind(wx.EVT_BUTTON, self._on_connect)
        self.btn_transfer.Bind(wx.EVT_BUTTON, self._on_transfer)
        self.btn_redeem.Bind(wx.EVT_BUTTON, self._on_redeem)
        self._closed = False
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        actions.add_listener(self.on_client)
        self._follow()
        self._update_button()

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._closed = True
            self.actions.remove_listener(self.on_client)
        event.Skip()

    def _follow(self):
        """Voices and what is read belong to speaking, the volumes to their sounds."""
        speak = self.chk_speak.GetValue()
        self.chk_voices.Enable(speak)
        self.chk_speak_own.Enable(speak)
        self.chk_speak_names.Enable(speak)
        for box in self.chk_read.values():
            box.Enable(speak)
        self.sld_volume.Enable(self.chk_ambience.GetValue())
        sounds = self.chk_sounds.GetValue()
        self.sld_effects.Enable(sounds)
        self.chk_other_sounds.Enable(sounds)
        self.btn_transfer.Enable(self.actions.online())

    def follow_settings(self, settings):
        """A setting changed from the game ("voices off"): show it here."""
        if self._closed or not _alive(self):
            raise RuntimeError("the page is gone")
        for key, box in (("speak", self.chk_speak), ("voices", self.chk_voices),
                         ("speak_own", self.chk_speak_own), ("speak_names", self.chk_speak_names),
                         ("ambience", self.chk_ambience), ("sounds", self.chk_sounds),
                         ("other_sounds", self.chk_other_sounds)):
            box.SetValue(bool(settings.get(key)))
        reader = settings.get("reader", "mixed")
        self.ch_reader.SetSelection(READERS.index(reader) if reader in READERS else 0)
        self.sld_volume.SetValue(int(settings.get("ambience_volume", 25)))
        self.sld_effects.SetValue(int(settings.get("effects_volume", 100)))
        self.txt_ignored.ChangeValue(", ".join(settings.get("ignored") or []))
        self._follow()

    def _update_button(self):
        label = _("btn_leave") if self.actions.busy() else _("btn_connect")
        if self.btn_connect.GetLabel() != label:
            self.btn_connect.SetLabel(label)
            self.Layout()
        self.btn_transfer.Enable(self.actions.online())

    def on_client(self, event, value):
        if self._closed or not _alive(self):
            raise RuntimeError("the page is gone")
        if event == "status":
            self.txt_status.ChangeValue(value)
        if event in ("status", "state"):
            self._update_button()
        if event == "transfer":
            self.txt_transfer.ChangeValue(value)

    def _on_connect(self, event):
        if self.actions.busy():
            self.actions.disconnect()
        else:
            settings = self.get_settings()
            self.actions.connect(settings["server"], settings["name"], settings["job"])
        self._update_button()

    def _on_transfer(self, event):
        self.actions.request_transfer_code()

    def _on_redeem(self, event):
        code = self.txt_redeem.GetValue().strip()
        if self.actions.redeem_transfer(code, self.txt_server.GetValue().strip()):
            self.txt_redeem.ChangeValue("")
        self._update_button()

    def get_settings(self):
        index = self.ch_job.GetSelection()
        ignored = [n.strip() for n in self.txt_ignored.GetValue().replace(";", ",").split(",") if n.strip()]
        settings = {"server": self.txt_server.GetValue().strip(),
                    "name": self.txt_name.GetValue().strip(),
                    "job": self.JOBS[index] if 0 <= index < len(self.JOBS) else "pilot",
                    "reader": READERS[max(0, self.ch_reader.GetSelection())],
                    "speak": self.chk_speak.GetValue(),
                    "voices": self.chk_voices.GetValue(),
                    "speak_own": self.chk_speak_own.GetValue(),
                    "speak_names": self.chk_speak_names.GetValue(),
                    "ambience": self.chk_ambience.GetValue(),
                    "ambience_volume": int(self.sld_volume.GetValue()),
                    "sounds": self.chk_sounds.GetValue(),
                    "effects_volume": int(self.sld_effects.GetValue()),
                    "other_sounds": self.chk_other_sounds.GetValue(),
                    "background": BACKGROUND_MODES[max(0, self.ch_background.GetSelection())],
                    "close_action": CLOSE_ACTIONS[max(0, self.ch_close.GetSelection())],
                    "auto_logout": AUTO_LOGOUT[max(0, self.ch_logout.GetSelection())],
                    "autoconnect": self.chk_autoconnect.GetValue(),
                    "ignored": ignored}
        for key, box in self.chk_read.items():
            settings[key] = box.GetValue()
        return settings
