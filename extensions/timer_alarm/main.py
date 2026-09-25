# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Timer & Alarm — Hariku V2 extension (needs core 2.9: commands with content).

Tell Aruna, typed or spoken, in Indonesian or English:
  "alarm besok jam 2 gang war", "set alarm tomorrow at 2 for gang war",
  "bangunkan aku jam 4.30", "alarm setiap hari jam 5 sholat subuh"
      -> read back with the day, date and part of the day, set on "ya"
  "timer mie 3 menit", "set a timer for 1 hour 30 minutes", "timer setengah jam"
      -> starts at once
  "batalkan timer mie", "sisa timer mie", "daftar alarm", "stop", "tunda 10 menit"

When one is due it rings even with Hariku in the tray and during quiet hours
(the user set it): the sound and "Alarm: gang war" (Hariku Voice's reminder
voice when the user chose one) every 10 seconds until a key is pressed, the
user says stop or snooze, or the ring length is over (then it is missed and
said once when the user is back). No window opens and the focus stays put.

  timer_alarm_parse.py    reading durations, alarm times and names (core.when)
  timer_alarm_store.py    the alarms and timers, repeats, settings, saving
  timer_alarm_ring.py     ringing and the key-press watch (pure logic)
  timer_alarm_app.py      the state: ticking, ringing, snoozing, missed rings
  timer_alarm_intents.py  what Aruna says and asks
  timer_alarm_text.py     sentences in the user's language
  timer_alarm_system.py   Windows: input readings and sounds
  timer_alarm_ui.py       the Preferences page

Everything stays on this computer: nothing is sent anywhere.
"""

import logging

import wx

import core.api
import core.commands
import core.hotkeys
import core.preferences
import core.voice
from core.i18n import get_current_language
from core.speech import speak

import timer_alarm_app as app_module
import timer_alarm_intents as intents
import timer_alarm_store as store
import timer_alarm_system as system
import timer_alarm_text as text
from timer_alarm_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Timer and Alarm"        # fixed, so saved hotkeys survive a language change
TICK_MS = 1000                      # checking what is due
RING_TICK_MS = 250                  # while ringing: noticing a key press quickly
STARTUP_DELAY_MS = 6000             # "While Hariku was closed, ..." after the greeting
KEY_STOP_DELAY_MS = 600             # "Alarm gang war dimatikan." after the key that stopped it

# Hotkey actions, all answer actions (they only speak). No default keys: any
# key already stops a ring (a dedicated Stop key would be one more key doing
# the same), and the user can give each one a key in Input Gestures.
ACTIONS = ("stop", "snooze", "time_left", "list", "cancel_timer", "cancel_all_timers",
           "cancel_alarm")
INTENTS = ("alarm", "wake", "timer", "cancel", "stop", "left", "snooze", "fix")

_app = None
_assistant = None
_timer = None
_timer_ms = None
_panel = None
_bus = None
_startup_call = None


# ------------------------------------------------------------
# Speaking
# ------------------------------------------------------------

def _say_ring(message):
    """What rings: Hariku Voice's reminder voice when the user chose one,
    else the screen reader. Quiet hours don't apply: the user set it."""
    try:
        core.voice.announce(message, "reminder", interrupt=True)
    except Exception:
        logger.exception("[Timer & Alarm] Announcing failed")


def _aruna_open():
    try:
        import ui.command_bar
        return ui.command_bar.current_bar() is not None
    except Exception:
        return False


def _on_key_stop(items):
    """A key stopped the ring: say which, a moment later (after what the key
    itself makes the screen reader say), unless Aruna just opened: then the
    user is about to say "stop" or "tunda" anyway."""
    message = text.stopped_text(items)

    def later():
        if _app is None or _aruna_open():
            return
        try:
            core.voice.announce(message, "reminder", interrupt=False)
        except Exception:
            logger.exception("[Timer & Alarm] Announcing failed")

    try:
        wx.CallLater(KEY_STOP_DELAY_MS, later)
    except Exception:
        pass


def _announce_startup():
    global _startup_call
    _startup_call = None
    if _app is None:
        return
    message = _app.startup_text()
    if message:
        try:
            core.voice.announce(message, "reminder", interrupt=False)
        except Exception:
            logger.exception("[Timer & Alarm] Announcing failed")


# ------------------------------------------------------------
# The tick
# ------------------------------------------------------------

def _set_interval(ms):
    global _timer_ms
    if _timer is not None and ms != _timer_ms:
        try:
            _timer.Start(ms)
            _timer_ms = ms
        except Exception:
            pass


def _tick():
    if _app is None:
        return
    try:
        _app.tick()
    except Exception:
        logger.exception("[Timer & Alarm] Tick failed")
    _set_interval(RING_TICK_MS if _app.ringing else TICK_MS)


# ------------------------------------------------------------
# Hotkey actions (answer actions: Aruna stays open and shows what they say)
# ------------------------------------------------------------

def _run(method):
    def action():
        if _assistant is None:
            return
        message = getattr(_assistant, method)()
        if message:
            speak(message, interrupt=True)
    return action


def action_id(name):
    return f"{EXT_NAME}.{name}"


_ACTION_METHODS = {
    "stop": "stop", "snooze": "snooze", "time_left": "time_left", "list": "list_all",
    "cancel_timer": "cancel_timer", "cancel_all_timers": "cancel_all_timers",
    "cancel_alarm": "cancel_alarm",
}


def intent_id(name):
    return f"{EXT_NAME}.{name}"


def _intent_handler(name):
    method = {"alarm": "on_alarm", "wake": "on_wake", "timer": "on_timer", "cancel": "on_cancel",
              "stop": "on_stop", "left": "on_time_left", "snooze": "on_snooze",
              "fix": "on_fix"}[name]

    def handler(request):
        if _assistant is None:
            return None
        return getattr(_assistant, method)(request)
    return handler


# ------------------------------------------------------------
# Events
# ------------------------------------------------------------

def _on_briefing_collect(lines):
    # Briefing contract: fast, stored data only.
    if _app is None:
        return
    try:
        sentence = text.briefing_sentence(_app.schedule.todays_alarms(_app.now()))
    except Exception:
        logger.exception("[Timer & Alarm] Briefing sentence failed")
        return
    if sentence:
        lines.append(sentence)


_SUBSCRIPTIONS = (
    ("on_briefing_collect", _on_briefing_collect),
)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

class PageActions:
    """What the Preferences page may do."""

    @staticmethod
    def rows():
        if _app is None:
            return []
        now = _app.now()
        rows = [(item["id"], text.row(item, now, ringing=True)) for item in _app.ringing_items()]
        rows += [(item["id"], text.row(item, now)) for item in _app.schedule.ordered()]
        return rows

    @staticmethod
    def remove(item_id):
        if _app is None:
            return ""
        if any(i["id"] == item_id for i in _app.ringing_items()):
            return text.stopped_text(_app.stop())
        item = _app.remove(item_id)
        return _("removed") if item is not None else _("item_gone")

    @staticmethod
    def stop():
        return _assistant.stop() if _assistant is not None else ""

    @staticmethod
    def settings():
        return _app.settings if _app is not None else dict(store.DEFAULT_SETTINGS)

    @staticmethod
    def sound_choices():
        return system.available_choices()

    @staticmethod
    def sound_path(choice, kind):
        return system.sound_path(choice, kind)

    @staticmethod
    def play(path):
        system.play(path)

    @staticmethod
    def stop_sound(path):
        system.stop(path)


def _create_panel(parent):
    global _panel
    import timer_alarm_ui as ui
    _panel = ui.SettingsPanel(parent, PageActions)
    return _panel


def _apply_panel():
    if not _panel or _app is None:
        return
    try:
        settings = _panel.get_settings()
    except RuntimeError:
        return                              # the page is already gone
    _app.set_settings(settings)


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def _packs():
    try:
        import core.quick_reminder
        return core.quick_reminder.active_packs()
    except Exception:
        return None


def make_app(**overrides):
    """The TimerAlarm with Hariku's clock, sounds, speech and data (tests
    replace any of them)."""
    options = dict(
        load=lambda: core.api.load_data(store.DATA_KEY),
        save=lambda data: core.api.save_data(store.DATA_KEY, data),
        play=system.play, stop=system.stop, say=_say_ring,
        input_readers=(system.last_input_tick, system.key_down, system.cursor_pos),
        packs=_packs, language=get_current_language,
        sound_path=system.sound_path, on_key_stop=_on_key_stop)
    options.update(overrides)
    return app_module.TimerAlarm(**options)


def _unsubscribe(bus, event_name, handler):
    unsubscribe = getattr(bus, "unsubscribe", None)
    if callable(unsubscribe):
        unsubscribe(event_name, handler)


def register(bus, app=None):
    global _app, _assistant, _timer, _timer_ms, _panel, _bus, _startup_call
    _bus = bus
    _panel = None
    _app = app or make_app()
    _app.start()
    _assistant = intents.Assistant(_app)

    for name in ACTIONS:
        core.hotkeys.register_action(EXT_NAME, name, _(f"action_{name}"), None, False,
                                     _run(_ACTION_METHODS[name]))
        core.commands.add_aliases(action_id(name), intents.ALIASES[name])
    core.commands.add_answer_actions([action_id(name) for name in ACTIONS])
    for name in INTENTS:
        core.commands.add_intent(intent_id(name), intents.PATTERNS[name], _intent_handler(name),
                                 title=_(f"intent_{name}"))
    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)

    _timer = core.api.set_interval(TICK_MS, _tick)
    _timer_ms = TICK_MS
    _startup_call = wx.CallLater(STARTUP_DELAY_MS, _announce_startup)
    logger.info("Timer & Alarm extension loaded.")


def teardown():
    global _app, _assistant, _timer, _panel, _startup_call
    for timer in (_timer, _startup_call):
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass
    _timer = _startup_call = None
    for name in INTENTS:
        try:
            core.commands.remove_intent(intent_id(name))
        except Exception:
            pass
    for name in ACTIONS:
        try:
            core.commands.remove_aliases(action_id(name))
        except Exception:
            pass
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _unsubscribe(_bus, event_name, handler)
            except Exception:
                pass
    if _app is not None:
        try:
            _app.shutdown()
        except Exception:
            logger.exception("[Timer & Alarm] Could not save")
    _app = _assistant = _panel = None
    logger.info("Timer & Alarm extension unloaded.")
