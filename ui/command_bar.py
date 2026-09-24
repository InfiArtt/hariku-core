# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The command bar (core 2.7): Ctrl+Alt+Space, from anywhere, even with Hariku
hidden in the tray, opens a small always-on-top window, "Hariku", with one
field: "Say or type a command". Enter runs what was typed (core.commands
decides what it means):

  * a reminder sentence gets the quick reminder's read-back, "... Save?";
    Enter again, or "ya" / "simpan", saves it; "tidak" / "batal" or Escape
    doesn't;
  * a command runs at once: the bar closes first, focus goes back to the
    window that had it, and the action runs as its hotkey would, so an action
    that opens a window opens it as usual;
  * a close call asks "Did you mean …?" (Enter or "ya" runs it);
  * anything else: "I didn't understand".

What the bar says goes through core.voice.announce(text, "command"), and an
action's own speech is routed to Hariku Voice for a moment
(core.voice.route_speech), so answers come in the voice the user picked.

With a speech recogniser registered (the Voice Control extension, through
core.commands.register_listener), the hotkey pressed again while the bar is
open starts or stops listening; the Listen button does too. What was heard
goes into the field and is handled as if typed. After a question asked by
voice, the bar listens again for the answer once the question has been said.
Without a recogniser, the bar is typing only, and the hotkey says how to get
Voice Control.

Every label is created right before its control (see core.core_panels.
_labeled). Focus moves only when the bar opens (to the field) and when it
closes (back to the previous window). Global hotkeys use RegisterHotKey
(core.hotkeys); no keyboard hook is ever installed. The only key state read
here is GetAsyncKeyState, to wait until the key that confirmed has been let
go before focus moves.
"""
import ctypes
import ctypes.wintypes
import logging
import threading
import time

import wx

import core.api
import core.commands
import core.hotkeys
import core.quick_reminder as quick
import core.ui_scale
import core.voice
from core.core_panels import _labeled
from core.events import bus
from core.i18n import apply_rtl_layout, get_translator

_ = get_translator("core")

logger = logging.getLogger(__name__)

ACTION_NAME = "command_bar"                       # "Hariku Core.command_bar"
ACTION_ID = core.commands.COMMAND_BAR_ACTION
KEY_RELEASE_POLL_MS = 20       # waiting for the confirming key to be let go...
KEY_RELEASE_MAX_MS = 800       # ...at most this long
AUTO_LISTEN_DELAY_MS = 400     # the screen reader has started announcing the bar by then
FOLLOW_UP_POLL_MS = 150
FOLLOW_UP_MAX_SECONDS = 15.0   # waiting for a question to be said before listening
READER_SECONDS_PER_CHAR = 0.065  # a guess at how long the screen reader takes


# ------------------------------------------------------------
# The hotkey
# ------------------------------------------------------------

def register_hotkey(callback=None):
    """Register "Open the command bar" as a global Ctrl+Alt+Space. Global
    hotkeys go through core.hotkeys, which uses RegisterHotKey on the main
    window; users can move it in Input Gestures."""
    core.hotkeys.register_action("Hariku Core", ACTION_NAME, _("nav_command_bar"),
                                 wx.WXK_SPACE, True, callback or toggle_command_bar,
                                 default_alt=True, default_global=True)


def hotkey_label():
    """The command bar's current key, "Ctrl + Alt + Space", or ""."""
    bindings = core.hotkeys.get_current_bindings(ACTION_ID)
    if not bindings:
        return ""
    keycode, ctrl, shift, alt, win, _is_global = sorted(bindings)[0]
    return core.hotkeys.format_key_name(keycode, ctrl, shift, alt, win)


# ------------------------------------------------------------
# The foreground window (plain user32 calls, no hook)
# ------------------------------------------------------------

_user32_dll = None


def _user32():
    global _user32_dll
    if _user32_dll is None:
        dll = ctypes.WinDLL("user32")      # our own instance: argtypes stay private
        HWND = ctypes.wintypes.HWND
        dll.GetForegroundWindow.argtypes = []
        dll.GetForegroundWindow.restype = HWND
        dll.SetForegroundWindow.argtypes = [HWND]
        dll.SetForegroundWindow.restype = ctypes.wintypes.BOOL
        dll.IsWindow.argtypes = [HWND]
        dll.IsWindow.restype = ctypes.wintypes.BOOL
        dll.IsWindowVisible.argtypes = [HWND]
        dll.IsWindowVisible.restype = ctypes.wintypes.BOOL
        _user32_dll = dll
    return _user32_dll


def foreground_window():
    """The window that has the focus now, as a number (0 for none)."""
    try:
        return int(_user32().GetForegroundWindow() or 0)
    except Exception:
        return 0


def set_foreground(hwnd):
    """Give a window the focus back, if it still exists and shows."""
    if not hwnd:
        return False
    try:
        user32 = _user32()
        if user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd):
            return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        logger.debug("Command bar: could not give the focus back", exc_info=True)
    return False


def _keys_down():
    return core.voice._any_key_down()


def _call_after(fn, *args):
    """wx.CallAfter from any thread, unless Hariku is closing."""
    try:
        if wx.GetApp() is not None:
            wx.CallAfter(fn, *args)
    except Exception:
        pass


def run_command(action_id):
    """Run an action for the command bar: its speech goes to Hariku Voice for
    a moment (core.voice.route_speech), then it runs as its hotkey would."""
    core.voice.route_speech("command")
    if core.commands.run_action(action_id):
        return True
    core.voice.announce(_("cmd_action_failed"), "command")
    return False


class _Pending:
    """A question the bar asked and waits for: "action" (Did you mean …?),
    "reminder" (… Save?) or "offer" (open it as a quick reminder?)."""

    def __init__(self, kind, text, command=None, result=None, alternative=None):
        self.kind = kind
        self.text = text
        self.command = command
        self.result = result
        self.alternative = alternative


# ------------------------------------------------------------
# The window
# ------------------------------------------------------------

class CommandBar(wx.Dialog):
    """`previous` is the window to give the focus back to on closing.
    `decide(text)`, `run(action_id)` and `say(text)` can be replaced for
    tests; `say` returns True when Hariku Voice speaks the text."""

    def __init__(self, parent=None, previous=0, decide=None, run=None, say=None):
        super().__init__(parent, title=_("cmd_title"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP)
        self._previous = previous
        self._decide = decide or core.commands.decide
        self._run = run or run_command
        self._say_fn = say or (lambda text: core.voice.announce(text, "command", interrupt=True))
        self._pending = None
        self._listening = False
        self._voice_turn = False
        self._closed = False
        self._busy = False               # running or saving: further input is ignored
        self._follow_up = None
        self._generation = 0             # listening sessions; old events are ignored
        self.last_said = ""

        vbox = wx.BoxSizer(wx.VERTICAL)
        # Each label right before its control (screen readers name a control
        # after the static text just before it; SetName doesn't change that).
        self.txt_input = _labeled(self, vbox, _("cmd_lbl_input"),
                                  lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER,
                                                      size=(460, -1)))
        self.txt_result = _labeled(self, vbox, _("cmd_lbl_result"),
                                   lambda: wx.TextCtrl(self, size=(460, 90),
                                                       style=wx.TE_READONLY | wx.TE_MULTILINE),
                                   proportion=1)
        self.txt_status = _labeled(self, vbox, _("cmd_lbl_status"),
                                   lambda: wx.TextCtrl(self, size=(460, -1),
                                                       style=wx.TE_READONLY))
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_listen = wx.Button(self, label=_("cmd_btn_listen"))
        self.btn_close = wx.Button(self, wx.ID_CANCEL, label=_("cmd_btn_close"))
        buttons.Add(self.btn_listen, 0, wx.RIGHT, 6)
        buttons.Add(self.btn_close, 0)
        vbox.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizer(vbox)

        self.btn_listen.Show(core.commands.get_listener() is not None)
        self._set_status(self._idle_status())

        self.txt_input.Bind(wx.EVT_TEXT_ENTER, self._on_enter)
        self.txt_input.Bind(wx.EVT_TEXT, self._on_text)
        self.btn_listen.Bind(wx.EVT_BUTTON, lambda event: self.toggle_listening())
        self.btn_close.Bind(wx.EVT_BUTTON, lambda event: self.close())
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.Bind(wx.EVT_CLOSE, lambda event: self.close())

        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.CentreOnScreen()

    # --- small helpers -------------------------------------------------------------

    def _alive(self):
        try:
            return not self._closed and bool(self)
        except RuntimeError:
            return False

    def text(self):
        return " ".join(self.txt_input.GetValue().split())

    def _idle_status(self):
        listener = core.commands.get_listener()
        if listener is None:
            return _("cmd_status_typing")
        return _("cmd_status_ready", shortcut=hotkey_label() or _("cmd_btn_listen_plain"))

    def _set_status(self, message):
        self.txt_status.ChangeValue(message)

    def say(self, message):
        """Show `message` in Last result and say it (Hariku Voice for command
        answers, else the screen reader). Returns True when a voice says it."""
        self.last_said = message
        self.txt_result.ChangeValue(message)
        try:
            return bool(self._say_fn(message))
        except Exception:
            logger.exception("Command bar: saying a message failed")
            return False

    # --- input -----------------------------------------------------------------------

    def _on_text(self, event):
        # Typing takes over from listening for an answer.
        self._cancel_follow_up()
        event.Skip()

    def _on_enter(self, event):
        if self._listening:
            self.stop_listening()             # Enter again: stop and recognise
            return
        self.submit()

    def _on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE and not event.HasAnyModifiers():
            if self._listening:
                self.stop_listening(discard=True)
            if self._pending is not None and not self._busy:
                self._answer(self._pending, "no")      # the question is answered; stay
            else:
                self.close()
            return
        event.Skip()

    def submit(self, text=None, source="typed"):
        """Handle a command, typed (Enter) or heard (`source` "voice")."""
        if not self._alive() or self._busy:
            return None
        text = self.text() if text is None else " ".join(str(text).split())
        self._voice_turn = source == "voice"
        self._cancel_follow_up()
        pending = self._pending
        if pending is not None:
            if source == "typed" and (not text or text == pending.text):
                return self._answer(pending, "yes")      # Enter again
            reply = core.commands.answer(text)
            if reply is not None:
                return self._answer(pending, reply)
            self._pending = None                          # something new instead
        if not text:
            self.say(_("cmd_empty"))
            return None
        decision = self._decide(text)
        self._handle(decision)
        return decision

    def _handle(self, decision):
        kind = decision.kind
        if kind == "run":
            self._run_command(decision.command)
        elif kind == "reminder":
            self._reminder(decision.result, decision.text)
        elif kind == "confirm":
            self._ask(_Pending("action", decision.text, command=decision.command,
                               alternative=decision.alternative),
                      _("cmd_did_you_mean", name=decision.command.title))
        elif kind == "offer_reminder":
            self._ask(_Pending("offer", decision.text, result=decision.result),
                      _("cmd_offer_reminder"))
        elif kind == "empty":
            self.say(_("cmd_empty"))
        else:
            self._not_understood(decision.text)

    def _not_understood(self, text):
        if core.commands.get_fallback() is None:
            self.say(_("cmd_not_understood"))
            return
        # A future AI fallback: slow, so on a worker thread; its answer is
        # only ever asked about, never run straight away.
        self._set_status(_("cmd_status_thinking"))
        candidates = core.commands.commands()

        def work():
            command = core.commands.ask_fallback(text, candidates)
            _call_after(self._fallback_done, text, command)

        threading.Thread(target=work, daemon=True, name="hariku-command-fallback").start()

    def _fallback_done(self, text, command):
        if not self._alive():
            return
        self._set_status(self._idle_status())
        if command is None:
            self.say(_("cmd_not_understood"))
        else:
            self._ask(_Pending("action", text, command=command),
                      _("cmd_did_you_mean", name=command.title))

    # --- questions and answers -------------------------------------------------------

    def _ask(self, pending, message):
        self._pending = pending
        voiced = self.say(message)
        if self._voice_turn:
            self._listen_for_answer(message, voiced)

    def _answer(self, pending, reply):
        self._pending = None
        if reply == "yes":
            if pending.kind == "action":
                self._run_command(pending.command)
            elif pending.kind == "reminder":
                self._save(pending.result)
            elif pending.kind == "offer":
                self._open_quick_reminder(pending.text)
            return None
        if pending.kind == "action" and pending.alternative is not None:
            # Not that command: then perhaps the reminder the sentence also was.
            self._reminder(pending.alternative, pending.text)
            return None
        self.say(_("cmd_cancelled"))
        self.txt_input.SelectAll()
        return None

    def _reminder(self, result, text):
        message = quick.readback(result)
        if result is not None and result.ok:
            self._ask(_Pending("reminder", text, result=result), message)
        else:
            self.say(message)

    def _save(self, result):
        self._busy = True
        core.voice.route_speech("command")
        try:
            saved = quick.save_result(result)       # says "Reminder saved."
        except Exception:
            logger.exception("Command bar: saving the reminder failed")
            saved = False
        if not saved:
            self._busy = False
            self.say(_("cmd_save_failed"))
            return
        self.last_said = _("qr_saved")
        self.txt_result.ChangeValue(self.last_said)
        self._after_keys_released(self.close)

    def _run_command(self, command):
        self._busy = True
        self._pending = None
        self.stop_listening(discard=True)
        self.txt_result.ChangeValue(_("cmd_running", name=command.title))
        action_id = command.id
        run = self._run
        # The bar closes first, then the action runs: a window it opens opens
        # as usual, and speech-only actions leave the user where they were.
        self._after_keys_released(lambda: self.close(then=lambda: run(action_id)))

    def _open_quick_reminder(self, text):
        self._busy = True

        def open_it():
            from ui.quick_reminder_dialog import open_quick_reminder
            open_quick_reminder(core.api.main_window_instance, text=text)

        self._after_keys_released(lambda: self.close(restore=False, then=open_it))

    def _after_keys_released(self, then, waited=0):
        """Call then() once the key that confirmed (Enter) is let go, so its
        release reaches this window, not the one focus goes back to."""
        if waited < KEY_RELEASE_MAX_MS and _keys_down():
            wx.CallLater(KEY_RELEASE_POLL_MS, self._after_keys_released, then,
                         waited + KEY_RELEASE_POLL_MS)
            return
        then()

    # --- listening -------------------------------------------------------------------

    def toggle_listening(self):
        if self._listening:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self):
        """Ask the speech recogniser to listen. False when there is none or it
        couldn't start (it says why)."""
        if not self._alive() or self._busy:
            return False
        listener = core.commands.get_listener()
        if listener is None:
            self.say(_("cmd_voice_missing"))
            return False
        self._cancel_follow_up()
        self._generation += 1
        generation = self._generation

        def on_event(kind, value=None):
            _call_after(self._on_listener_event, generation, kind, value)

        self._listening = True
        self.btn_listen.SetLabel(_("cmd_btn_stop_listening"))
        try:
            started = bool(listener.start(on_event))
        except Exception:
            logger.exception("Command bar: the speech recogniser failed to start")
            started = False
        if not started and generation == self._generation:
            self._listening = False
            self.btn_listen.SetLabel(_("cmd_btn_listen"))
        return started

    def stop_listening(self, discard=False):
        if not self._listening:
            return
        listener = core.commands.get_listener()
        if listener is None:
            self._listening = False
            return
        try:
            listener.stop(discard)
        except Exception:
            logger.exception("Command bar: stopping the speech recogniser failed")
        if discard:
            self._generation += 1          # nothing more from that session
            self._listening = False
            self._listening_ended()

    def _listening_ended(self):
        try:
            self.btn_listen.SetLabel(_("cmd_btn_listen"))
            self._set_status(self._idle_status())
        except RuntimeError:
            pass

    def _on_listener_event(self, generation, kind, value):
        if not self._alive() or generation != self._generation:
            return
        if kind == "listening":
            self._listening = True
            self._set_status(_("cmd_status_listening", shortcut=hotkey_label() or "Enter"))
        elif kind == "recognising":
            self._set_status(_("cmd_status_recognising"))
        elif kind == "text":
            self._listening = False
            self._listening_ended()
            text = " ".join(str(value or "").split())
            if not text:
                self.say(_("cmd_heard_nothing"))
                return
            self.txt_input.ChangeValue(text)
            self.txt_input.SetInsertionPointEnd()
            self.submit(text, source="voice")
        elif kind == "error":
            self._listening = False
            self._listening_ended()
            self.say(str(value or _("cmd_voice_failed")))
        elif kind == "stopped":
            self._listening = False
            self._listening_ended()

    def _auto_listen(self):
        """Listening as the bar opens (Voice Control's setting)."""
        if self._alive() and not self._listening and not self.text():
            self.start_listening()

    def _listen_for_answer(self, message, voiced):
        """After a question asked by voice, listen for the answer once it has
        been said (so the microphone doesn't hear the question)."""
        listener = core.commands.get_listener()
        if listener is None or not listener.is_available():
            return
        reader_seconds = 0.0 if voiced else min(8.0, 0.6 + len(message) * READER_SECONDS_PER_CHAR)
        started = time.monotonic()

        def check():
            self._follow_up = None
            if not self._alive() or self._pending is None or self._listening or self._busy:
                return
            waited = time.monotonic() - started
            if waited < FOLLOW_UP_MAX_SECONDS and (waited < reader_seconds
                                                   or core.voice.is_speaking()):
                self._follow_up = wx.CallLater(FOLLOW_UP_POLL_MS, check)
                return
            self.start_listening()

        self._follow_up = wx.CallLater(FOLLOW_UP_POLL_MS, check)

    def _cancel_follow_up(self):
        timer, self._follow_up = self._follow_up, None
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass

    # --- closing ---------------------------------------------------------------------

    def close(self, restore=True, then=None):
        """Close the bar; focus goes back to the previous window (unless
        `restore` is False), then then() runs."""
        if self._closed:
            return
        self._cancel_follow_up()
        if self._listening:
            self.stop_listening(discard=True)
        self._closed = True
        previous = self._previous
        _forget(self)
        try:
            self.Hide()
            self.Destroy()
        except RuntimeError:
            pass
        if restore:
            set_foreground(previous)
        if then is not None:
            wx.CallAfter(then)


# ------------------------------------------------------------
# Opening and the hotkey
# ------------------------------------------------------------

_bar = None


def _forget(bar):
    global _bar
    if _bar is bar:
        _bar = None


def current_bar():
    """The open command bar, or None."""
    bar = _bar
    if bar is None:
        return None
    try:
        return bar if bar._alive() else None
    except RuntimeError:
        return None


def bring_to_front(bar):
    bar.Show()
    bar.Raise()
    try:
        _user32().SetForegroundWindow(bar.GetHandle())
    except Exception:
        pass
    bar.txt_input.SetFocus()


def open_command_bar(listen=None, previous=None, **kwargs):
    """Open the command bar (or bring the open one to the front). `listen`:
    start listening at once; None follows the speech recogniser's "listen as
    soon as the bar opens"."""
    global _bar
    bar = current_bar()
    if bar is not None:
        bring_to_front(bar)
        return bar
    if previous is None:
        previous = foreground_window()
    bar = CommandBar(None, previous, **kwargs)
    _bar = bar
    bring_to_front(bar)
    listener = core.commands.get_listener()
    if listen is None:
        listen = listener is not None and listener.is_available() and listener.listen_on_open()
    if listen:
        # After the screen reader has begun announcing the bar: listening
        # silences it, so it doesn't talk into the microphone.
        wx.CallLater(AUTO_LISTEN_DELAY_MS, bar._auto_listen)
    return bar


def close_command_bar(*_args):
    """Close the bar without giving the focus anywhere (Hariku is quitting:
    a window without a parent would keep it running)."""
    bar = current_bar()
    if bar is not None:
        bar.close(restore=False)


bus.subscribe("on_unload", close_command_bar)


def toggle_command_bar():
    """The hotkey: open the bar; pressed again while it is open, start or stop
    listening (or say how to get Voice Control)."""
    bar = current_bar()
    if bar is None:
        return open_command_bar()
    bring_to_front(bar)
    if core.commands.get_listener() is None:
        bar.say(_("cmd_voice_missing"))
    else:
        bar.toggle_listening()
    return bar
