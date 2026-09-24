# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Morning Briefing — Hariku V2 extension.

A hotkey (B) speaks a greeting (with the user's nickname from Preferences,
Profile), today's date, today's reminders and whatever other extensions add
through the "on_briefing_collect" event (the contract is documented in
briefing_core.py). Optionally the briefing plays the first time Hariku starts
each day (off by default; Preferences, Morning Briefing).

Shift+B speaks the evening summary: what's done today, what's left, tomorrow's
first reminder, and what other extensions add through "on_evening_collect".
Optionally it plays by itself at a chosen time between 18:00 and 23:00 (off by
default).
"""

import datetime
import logging

import wx

import core.api
import core.hotkeys
import core.personal
import core.preferences
import core.reminders
import core.ui_scale
from core.voice import announce   # Hariku Voice when chosen, else the screen reader

import briefing_core
from briefing_core import _

logger = logging.getLogger(__name__)

# {"auto_first_start": bool, "last_auto_date": "YYYY-MM-DD", "evening_auto": bool,
#  "evening_time": "HH:MM", "last_evening_date": "YYYY-MM-DD"}
DATA_KEY = "Briefing"
AUTO_DELAY_MS = 5000    # let startup sounds and speech finish first

_bus = None
_active = False
_auto_timer = None
_panel = None


def _load_config():
    data = core.api.load_data(DATA_KEY)
    return data if isinstance(data, dict) else {}


def _today_str(now=None):
    return (now or datetime.datetime.now()).strftime("%Y-%m-%d")


# ------------------------------------------------------------
# Action
# ------------------------------------------------------------

def _reminders_on(day):
    try:
        return core.reminders.get_reminders_for_date(day.strftime("%Y-%m-%d"))
    except Exception:
        logger.exception("[Briefing] Could not read the reminders")
        return []


def briefing_text(now=None, greet=True):
    now = now or datetime.datetime.now()
    reminders = _reminders_on(now)
    core_config = core.api.load_data("Core")
    date_format = core_config.get("date_format") if isinstance(core_config, dict) else None
    return " ".join(briefing_core.build_briefing(now, reminders, date_format, _bus,
                                                 nickname=core.personal.get_addressed_name(),
                                                 expand=core.personal.expand,
                                                 birthday=core.personal.is_birthday(now),
                                                 greet=greet))


def evening_text(now=None):
    now = now or datetime.datetime.now()
    return " ".join(briefing_core.build_evening(now, _reminders_on(now),
                                                _reminders_on(now + datetime.timedelta(days=1)),
                                                _bus,
                                                nickname=core.personal.get_addressed_name(),
                                                expand=core.personal.expand,
                                                birthday=core.personal.is_birthday(now)))


def play_briefing():
    if _bus is None:
        return
    announce(briefing_text(), "briefing", interrupt=True)


def play_evening_summary():
    if _bus is None:
        return
    announce(evening_text(), "briefing", interrupt=True)


# ------------------------------------------------------------
# Automatic briefing on the first start of the day
# ------------------------------------------------------------

def _on_app_startup(*_args):
    global _auto_timer
    if briefing_core.should_auto_play(_load_config(), _today_str()):
        _auto_timer = wx.CallLater(AUTO_DELAY_MS, _auto_play)


def _auto_play():
    global _auto_timer
    _auto_timer = None
    if not _active:
        return
    config = _load_config()
    today = _today_str()
    if not briefing_core.should_auto_play(config, today):
        return
    config["last_auto_date"] = today
    core.api.save_data(DATA_KEY, config)
    if _bus is None:
        return
    # Hariku's startup greeting has just said "Good morning": don't say it twice.
    # It waits for the greeting instead of cutting it off.
    announce(briefing_text(greet=not core.personal.startup_greeting_enabled()), "briefing",
             interrupt=False)


# ------------------------------------------------------------
# Automatic evening summary
# ------------------------------------------------------------

def _on_minute_tick(now=None, *_args, **_kwargs):
    if not _active:
        return
    now = now if isinstance(now, datetime.datetime) else datetime.datetime.now()
    config = _load_config()
    if not briefing_core.should_auto_evening(config, now):
        return
    config["last_evening_date"] = _today_str(now)
    core.api.save_data(DATA_KEY, config)
    play_evening_summary()


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _plain(label):
    return label.replace("&", "").strip().rstrip(":").strip()


class BriefingPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        config = _load_config()
        vbox = wx.BoxSizer(wx.VERTICAL)
        label = _("chk_auto")
        self.chk_auto = wx.CheckBox(self, label=label)
        self.chk_auto.SetName(label)
        self.chk_auto.SetValue(bool(config.get("auto_first_start", False)))
        vbox.Add(self.chk_auto, 0, wx.ALL, 10)

        label = _("chk_evening")
        self.chk_evening = wx.CheckBox(self, label=label)
        self.chk_evening.SetName(label)
        self.chk_evening.SetValue(bool(config.get("evening_auto", False)))
        vbox.Add(self.chk_evening, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        label = _("lbl_evening_time")
        vbox.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT, 10)
        self.choice_evening_time = wx.Choice(self, choices=briefing_core.EVENING_TIMES)
        self.choice_evening_time.SetName(_plain(label))
        self.choice_evening_time.SetSelection(
            briefing_core.EVENING_TIMES.index(briefing_core.evening_time(config)))
        vbox.Add(self.choice_evening_time, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizer(vbox)
        core.ui_scale.apply_appearance(self)

    def ApplyChanges(self):
        config = _load_config()
        config["auto_first_start"] = bool(self.chk_auto.GetValue())
        config["evening_auto"] = bool(self.chk_evening.GetValue())
        index = self.choice_evening_time.GetSelection()
        if 0 <= index < len(briefing_core.EVENING_TIMES):
            config["evening_time"] = briefing_core.EVENING_TIMES[index]
        core.api.save_data(DATA_KEY, config)


def _create_panel(parent):
    global _panel
    _panel = BriefingPanel(parent)
    return _panel


def _apply_panel():
    if _panel:
        try:
            _panel.ApplyChanges()
        except RuntimeError:
            pass  # panel already destroyed


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register(bus):
    global _bus, _active
    _bus = bus
    _active = True
    bus.subscribe("on_app_startup", _on_app_startup)
    bus.subscribe("on_minute_tick", _on_minute_tick)
    # B and Shift+B: free in the core, every extension and store package (Lumina
    # uses Ctrl+Shift+B).
    core.hotkeys.register_action("Morning Briefing", "play_briefing", _("action_play"),
                                 ord("B"), False, play_briefing)
    core.hotkeys.register_action("Morning Briefing", "evening_summary", _("action_evening"),
                                 ord("B"), False, play_evening_summary, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("Morning Briefing extension loaded.")


def teardown():
    global _active, _auto_timer
    _active = False
    if _auto_timer is not None:
        try:
            _auto_timer.Stop()
        except Exception:
            pass
        _auto_timer = None
    if _bus is not None:
        unsubscribe = getattr(_bus, "unsubscribe", None)
        for event_name, handler in (("on_app_startup", _on_app_startup),
                                    ("on_minute_tick", _on_minute_tick)):
            try:
                if callable(unsubscribe):
                    unsubscribe(event_name, handler)
                else:
                    listeners = getattr(_bus, "_listeners", {}).get(event_name)
                    if listeners and handler in listeners:
                        listeners.remove(handler)
            except Exception:
                pass
    logger.info("Morning Briefing extension unloaded.")
