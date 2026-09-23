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

A hotkey speaks a greeting, today's date, today's reminders and whatever other
extensions add through the "on_briefing_collect" event (the contract is
documented in briefing_core.py). Optionally the briefing plays the first time
Hariku starts each day (off by default; Preferences, Morning Briefing).
"""

import datetime
import logging

import wx

import core.api
import core.hotkeys
import core.preferences
import core.reminders
import core.ui_scale
from core.speech import speak

import briefing_core
from briefing_core import _

logger = logging.getLogger(__name__)

DATA_KEY = "Briefing"   # {"auto_first_start": bool, "last_auto_date": "YYYY-MM-DD"}
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

def briefing_text(now=None):
    now = now or datetime.datetime.now()
    try:
        reminders = core.reminders.get_reminders_for_date(_today_str(now))
    except Exception:
        logger.exception("[Briefing] Could not read today's reminders")
        reminders = []
    core_config = core.api.load_data("Core")
    date_format = core_config.get("date_format") if isinstance(core_config, dict) else None
    return " ".join(briefing_core.build_briefing(now, reminders, date_format, _bus))


def play_briefing():
    if _bus is None:
        return
    speak(briefing_text(), interrupt=True)


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
    play_briefing()


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

class BriefingPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        vbox = wx.BoxSizer(wx.VERTICAL)
        label = _("chk_auto")
        self.chk_auto = wx.CheckBox(self, label=label)
        self.chk_auto.SetName(label)
        self.chk_auto.SetValue(bool(_load_config().get("auto_first_start", False)))
        vbox.Add(self.chk_auto, 0, wx.ALL, 10)
        self.SetSizer(vbox)
        core.ui_scale.apply_appearance(self)

    def ApplyChanges(self):
        config = _load_config()
        config["auto_first_start"] = bool(self.chk_auto.GetValue())
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
    # B: free in the core and the bundled extensions (Lumina uses Ctrl+Shift+B).
    core.hotkeys.register_action("Morning Briefing", "play_briefing", _("action_play"),
                                 ord("B"), False, play_briefing)
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
        try:
            if callable(unsubscribe):
                unsubscribe("on_app_startup", _on_app_startup)
            else:
                listeners = getattr(_bus, "_listeners", {}).get("on_app_startup")
                if listeners and _on_app_startup in listeners:
                    listeners.remove(_on_app_startup)
        except Exception:
            pass
    logger.info("Morning Briefing extension unloaded.")
