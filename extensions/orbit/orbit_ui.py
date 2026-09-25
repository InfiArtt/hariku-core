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

The game window has the Messages list (read-only, newest last; arrows read
it, and a new message never moves the selection or the focus), the Command
field (Enter sends; Up and Down bring back earlier commands), Connect or
Disconnect, Help, and the status. Escape or closing it only hides it: the
game goes on, and messages are still read aloud.

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


def _alive(window):
    try:
        return bool(window) and not window.IsBeingDeleted()
    except RuntimeError:
        return False


class OrbitFrame(wx.Frame):
    """`client` is orbit_play.OrbitClient; `on_visibility()` is called when
    the window is shown or hidden (the ambience follows it)."""

    def __init__(self, client, on_visibility=None):
        super().__init__(None, title=_("window_title"), size=(680, 540))
        self.client = client
        self._on_visibility = on_visibility
        self._history = []
        self._history_at = None
        self.closing = False
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.lst_messages = _labeled(panel, sizer, _("lbl_messages"),
                                     lambda: wx.ListBox(panel, style=wx.LB_SINGLE), proportion=1)
        self.txt_command = _labeled(panel, sizer, _("lbl_command"),
                                    lambda: wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER))
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_connect = wx.Button(panel, label=_("btn_connect"))
        self.btn_help = wx.Button(panel, label=_("btn_help"))
        row.Add(self.btn_connect, 0, wx.RIGHT, _BORDER)
        row.Add(self.btn_help, 0)
        sizer.Add(row, 0, wx.ALL, _BORDER)
        self.txt_status = _labeled(panel, sizer, _("lbl_status"),
                                   lambda: wx.TextCtrl(panel, value=client.status,
                                                       style=wx.TE_READONLY))
        sizer.AddSpacer(_BORDER)
        panel.SetSizer(sizer)

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.lst_messages.Set(list(client.messages))
        self.txt_command.Bind(wx.EVT_TEXT_ENTER, self._on_enter)
        self.txt_command.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.btn_connect.Bind(wx.EVT_BUTTON, self._on_connect)
        self.btn_help.Bind(wx.EVT_BUTTON, lambda event: self.client.submit("help"))
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

    def _on_show(self, event):
        event.Skip()
        if self._on_visibility is not None:
            wx.CallAfter(self._on_visibility)

    def _on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.hide()
            return
        event.Skip()

    def _on_close(self, event):
        if event.CanVeto() and not self.closing:
            event.Veto()
            self.hide()
            return
        self.client.remove_listener(self.on_client)
        event.Skip()

    def destroy(self):
        self.closing = True
        self.client.remove_listener(self.on_client)
        self.Destroy()

    # --- the client's news ------------------------------------------------------------

    def on_client(self, event, value):
        if not _alive(self):
            raise RuntimeError("the window is gone")
        if event == "message":
            self.lst_messages.Append(value)       # the selection and the focus stay put
        elif event == "trim":
            count = min(int(value), self.lst_messages.GetCount())
            selected = self.lst_messages.GetSelection()
            self.lst_messages.Freeze()
            try:
                for _i in range(count):
                    self.lst_messages.Delete(0)
            finally:
                self.lst_messages.Thaw()
            if selected != wx.NOT_FOUND and selected - count >= 0:
                self.lst_messages.SetSelection(selected - count)
        elif event == "status":
            self.txt_status.ChangeValue(value)
            self._update_buttons()
        elif event == "state":
            self._update_buttons()

    def _update_buttons(self):
        busy = self.client.online() or self.client.connecting()
        label = _("btn_disconnect") if busy else _("btn_connect")
        if self.btn_connect.GetLabel() != label:
            self.btn_connect.SetLabel(label)
            self.Layout()

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


class OrbitPanel(wx.Panel):
    """The Preferences page. `actions` has connect(server, name, job),
    disconnect(), busy(), status(), character(server) -> account or None,
    add_listener(fn) and remove_listener(fn)."""

    JOBS = ("pilot", "engineer", "trader", "scientist", "security")

    def __init__(self, parent, settings, actions):
        super().__init__(parent)
        self.actions = actions
        sizer = wx.BoxSizer(wx.VERTICAL)
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
        self.chk_speak = _check(self, sizer, _("chk_speak"), settings["speak"])
        self.chk_voices = _check(self, sizer, _("chk_voices"), settings["voices"])
        self.chk_ambience = _check(self, sizer, _("chk_ambience"), settings["ambience"])
        self.sld_volume = _labeled(self, sizer, _("lbl_volume"),
                                   lambda: wx.Slider(self, value=int(settings["ambience_volume"]),
                                                     minValue=0, maxValue=100))
        self.sld_volume.SetLineSize(5)
        self.sld_volume.SetPageSize(10)
        self.chk_sounds = _check(self, sizer, _("chk_sounds"), settings["sounds"])
        self.btn_connect = wx.Button(self, label=_("btn_connect"))
        sizer.Add(self.btn_connect, 0, wx.LEFT | wx.RIGHT | wx.TOP, _BORDER)
        self.txt_status = _labeled(self, sizer, _("lbl_status"),
                                   lambda: wx.TextCtrl(self, value=actions.status(),
                                                       style=wx.TE_READONLY))
        _note(self, sizer, _("note_voices"))
        _note(self, sizer, _("note_privacy"))
        self.SetSizer(sizer)

        self.chk_speak.Bind(wx.EVT_CHECKBOX, lambda event: self._follow())
        self.chk_ambience.Bind(wx.EVT_CHECKBOX, lambda event: self._follow())
        self.btn_connect.Bind(wx.EVT_BUTTON, self._on_connect)
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
        """Voices belong to speaking messages, the volume to the ambience."""
        self.chk_voices.Enable(self.chk_speak.GetValue())
        self.sld_volume.Enable(self.chk_ambience.GetValue())

    def _update_button(self):
        label = _("btn_disconnect") if self.actions.busy() else _("btn_connect")
        if self.btn_connect.GetLabel() != label:
            self.btn_connect.SetLabel(label)
            self.Layout()

    def on_client(self, event, value):
        if self._closed or not _alive(self):
            raise RuntimeError("the page is gone")
        if event == "status":
            self.txt_status.ChangeValue(value)
        if event in ("status", "state"):
            self._update_button()

    def _on_connect(self, event):
        if self.actions.busy():
            self.actions.disconnect()
        else:
            settings = self.get_settings()
            self.actions.connect(settings["server"], settings["name"], settings["job"])
        self._update_button()

    def get_settings(self):
        index = self.ch_job.GetSelection()
        return {"server": self.txt_server.GetValue().strip(),
                "name": self.txt_name.GetValue().strip(),
                "job": self.JOBS[index] if 0 <= index < len(self.JOBS) else "pilot",
                "speak": self.chk_speak.GetValue(),
                "voices": self.chk_voices.GetValue(),
                "ambience": self.chk_ambience.GetValue(),
                "ambience_volume": int(self.sld_volume.GetValue()),
                "sounds": self.chk_sounds.GetValue()}
