# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Orbit — Hariku V2 extension: a small multiplayer text game (a MUD) on a
space station orbiting the Earth. Hang out in the Cantina, look down at
Indonesia from the Observation Deck, whisper to friends, repair the reactor,
fly cargo to the Moon, trade on the Promenade, take small missions.

Play it in its window ("Open Orbit", no key by default; "orbit" or "buka
orbit" to Aruna) or straight from Aruna, typed or spoken, with "orbit" in
front: "orbit pergi ke kantin", "orbit bilang halo", "orbit bisik Sari
ketemu di dek", "orbit siapa online".

  orbit_ws.py      the WebSocket protocol (a copy of servers/orbit/orbit_ws.py)
  orbit_net.py     the connection: its own thread, pings, reconnecting
  orbit_parse.py   what was typed or said -> a command (Indonesian, English)
  orbit_play.py    playing: messages, speech, sounds, ambience (no wx)
  orbit_speech.py  who speaks: the narrator, or each player's own voice
  orbit_audio.py   which sound an event plays; the ambience loop (MCI)
  orbit_text.py    Orbit's own words
  orbit_ui.py      the game window and the Preferences page
  orbit_sounds.py  makes the sounds in sounds/

The game itself runs on the server (servers/orbit in Hariku's source), which
decides everything; this extension only asks and shows. Orbit connects only
when you open it, press Connect or give it a command.
"""

import logging
import os

import wx

import core.api
import core.commands
import core.hotkeys
import core.preferences
import core.sounds
import core.voice
from core.commands import Reply

import orbit_audio
import orbit_net
import orbit_parse
import orbit_play
import orbit_speech
import orbit_text
import orbit_ui
from orbit_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Orbit"               # fixed, so saved hotkeys survive a language change
DATA_KEY = "Orbit"
ACCOUNTS_KEY = "OrbitAccounts"
EXT_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(EXT_DIR, "sounds")
DEFAULT_SERVER = "wss://infiartt.com/orbit/ws"
PLAY_INTENT = f"{EXT_NAME}.play"
PLAY_PATTERNS = ("orbit {text}",)
OPEN_WORDS = {"buka", "open", "main", "play", "jendela", "window", "tampilkan", "show"}
MAX_COMMAND = 300
CONNECT_HOLD_SECONDS = 15

DEFAULT_SETTINGS = {"server": DEFAULT_SERVER, "name": "", "job": "pilot", "speak": True,
                    "voices": True, "ambience": True, "ambience_volume": 25, "sounds": True}


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = dict(DEFAULT_SETTINGS)
    for key in ("speak", "voices", "ambience", "sounds"):
        if isinstance(raw.get(key), bool):
            settings[key] = raw[key]
    server = raw.get("server")
    if isinstance(server, str) and server.strip():
        settings["server"] = server.strip()[:300]
    name = raw.get("name")
    if isinstance(name, str):
        settings["name"] = name.strip()[:20]
    if raw.get("job") in orbit_play.JOBS:
        settings["job"] = raw["job"]
    try:
        settings["ambience_volume"] = max(0, min(100, int(raw.get("ambience_volume",
                                                                 DEFAULT_SETTINGS["ambience_volume"]))))
    except (TypeError, ValueError):
        pass
    return settings


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

_bus = None
_active = False
_settings = normalize_settings(None)
_services = None
_client = None
_frame = None
_panel = None


def _save_settings():
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data.update(_settings)
    core.api.save_data(DATA_KEY, data)


def _call_after(fn, *args):
    try:
        if _active and wx.GetApp() is not None:
            wx.CallAfter(fn, *args)
    except Exception:
        pass


class _Timer:
    def __init__(self, timer):
        self._timer = timer

    def cancel(self):
        try:
            self._timer.Stop()
        except Exception:
            pass


# ------------------------------------------------------------
# What playing uses from Hariku (orbit_play's services)
# ------------------------------------------------------------

class Services:
    def __init__(self):
        self.voices = orbit_speech.VoiceBook(
            lambda: [p["id"] for p in core.voice.get_providers()],
            core.voice.is_provider_available, core.voice.list_voices)
        self.ambience_player = orbit_audio.AmbiencePlayer(is_speaking=core.voice.is_speaking)

    # --- settings and accounts -------------------------------------------------------

    def settings(self):
        return dict(_settings)

    def language(self):
        return orbit_text.user_language()

    def account(self, url):
        data = core.api.load_data(ACCOUNTS_KEY)
        account = data.get(url) if isinstance(data, dict) else None
        return dict(account) if isinstance(account, dict) else None

    def save_account(self, url, account):
        data = core.api.load_data(ACCOUNTS_KEY)
        data = data if isinstance(data, dict) else {}
        data[url] = dict(account)
        core.api.save_data(ACCOUNTS_KEY, data)

    def new_secret(self):
        return os.urandom(32).hex()

    # --- the connection, timers, threads ---------------------------------------------------

    def connect(self, url, hello, on_message, on_state):
        return orbit_net.Connection(url, hello, on_message, on_state)

    def call_later(self, seconds, fn):
        return _Timer(wx.CallLater(max(1, int(seconds * 1000)), fn))

    def call_after(self, fn, *args):
        _call_after(fn, *args)

    # --- speech -----------------------------------------------------------------------

    def say(self, text):
        return core.voice.announce(text, "command", interrupt=False)

    def speak_voice(self, text, voice, on_done):
        settings = core.voice.get_settings()
        return core.voice.preview(text, voice["provider"], voice["id"], rate=settings["rate"],
                                  volume=settings["volume"], stop_on_key=settings["stop_on_key"],
                                  on_done=on_done)

    def voice_busy(self):
        return core.voice.is_speaking()

    def voice_for(self, name):
        cached = self.voices.cached()
        if cached is None:
            self.voices.refresh_in_background()
            return None
        voices = orbit_speech.voices_of(cached, self.language())
        settings = core.voice.get_settings()
        narrator = (settings["provider"], settings["voice"]) if settings.get("voice") else None
        return orbit_speech.pick_voice(name, voices, exclude=narrator)

    def show_answer(self, text):
        if hasattr(core.commands, "show_answer"):
            core.commands.show_answer(text)

    # --- sounds -----------------------------------------------------------------------

    def play(self, name):
        path = os.path.join(SOUNDS_DIR, f"{name}.wav")
        if os.path.isfile(path):
            core.sounds.play_sound(path)

    def ambience(self, name, volume):
        if name in orbit_audio.AMBIENCES:
            self.ambience_player.play(os.path.join(SOUNDS_DIR, f"amb_{name}.wav"), volume)
        else:
            self.ambience_player.play(None)

    def window_open(self):
        return _frame is not None and orbit_ui._alive(_frame) and _frame.IsShown()


def _on_before_speak(payload, *args, **kwargs):
    # Any thread: the ambience goes quiet for about as long as the line takes.
    if _services is not None and isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            _services.ambience_player.hush(orbit_speech.reader_seconds(text))


# ------------------------------------------------------------
# The window
# ------------------------------------------------------------

def open_window():
    global _frame
    if _client is None:
        return
    if _frame is None or not orbit_ui._alive(_frame):
        _frame = orbit_ui.OrbitFrame(_client, on_visibility=_client.update_ambience)
    _frame.show_and_focus()
    if not _client.online() and not _client.connecting():
        _client.connect()
    if _services is not None and _settings["voices"]:
        _services.voices.refresh_in_background()


def _destroy_window():
    global _frame
    frame, _frame = _frame, None
    if frame is not None and orbit_ui._alive(frame):
        try:
            frame.destroy()
        except Exception:
            pass


# ------------------------------------------------------------
# Aruna
# ------------------------------------------------------------

def _defer(fn, *args):
    """Run fn a moment later, once Aruna waits for the answer (Reply(wait=True)),
    so what it says lands in Last result."""
    try:
        wx.CallAfter(fn, *args)
    except Exception:
        logger.exception("[Orbit] Could not run a command")


def _on_play_intent(request):
    text = " ".join(str(request.text or "").split())
    if not text or len(text) > MAX_COMMAND or _client is None:
        return None
    if orbit_parse.parse(text) is None:
        return None
    if text.lower().strip(" .!?") in OPEN_WORDS:
        return Reply(then=open_window)
    if not _client.online() and hasattr(core.commands, "hold_answer"):
        # Connecting first takes a moment: keep Last result open for the answer.
        core.commands.hold_answer(CONNECT_HOLD_SECONDS)
    _defer(_client.submit, text, "aruna")
    return Reply(wait=True)


def _ask(text):
    def run():
        if _client is not None:
            _client.submit(text, "aruna")
    return run


def _toggle_connection():
    if _client is None:
        return
    if _client.online() or _client.connecting():
        _client.disconnect()
    else:
        _client.aruna_until = _client.clock() + orbit_play.ARUNA_SECONDS
        _client.connect()


ACTIONS = (
    ("open", "action_open", "title_open", open_window,
     ("orbit", "buka orbit", "open orbit", "main orbit", "play orbit", "ke orbit"), False),
    ("look", "action_look", "title_look", _ask("look"),
     ("orbit lihat sekitar", "orbit look around", "orbit lihat"), True),
    ("who", "action_who", "title_who", _ask("who"),
     ("orbit siapa online", "orbit siapa yang online", "orbit who is online", "orbit who"), True),
    ("credits", "action_credits", "title_credits", _ask("inventory"),
     ("orbit cek kredit", "orbit kredit", "orbit check credits", "orbit inventory", "orbit tas"), True),
    ("connect", "action_connect", "title_connect", _toggle_connection,
     ("orbit sambungkan", "orbit putuskan", "orbit connect", "orbit disconnect"), True),
)


def action_id(name):
    return f"{EXT_NAME}.{name}"


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

class _PageActions:
    """What the Preferences page may do."""

    @staticmethod
    def connect(server, name, job):
        if _client is not None:
            _client.connect(server, name, job)

    @staticmethod
    def disconnect():
        if _client is not None:
            _client.disconnect()

    @staticmethod
    def busy():
        return _client is not None and (_client.online() or _client.connecting())

    @staticmethod
    def status():
        return _client.status if _client is not None else _("status_idle")

    @staticmethod
    def character(server):
        return _services.account(server) if _services is not None else None

    @staticmethod
    def add_listener(fn):
        if _client is not None:
            _client.add_listener(fn)

    @staticmethod
    def remove_listener(fn):
        if _client is not None:
            _client.remove_listener(fn)


def _create_panel(parent):
    global _panel
    _panel = orbit_ui.OrbitPanel(parent, dict(_settings), _PageActions)
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        new = _panel.get_settings()
    except RuntimeError:
        return          # the page is gone
    voices_before = _settings["voices"]
    _settings.update(normalize_settings(dict(_settings, **new)))
    _save_settings()
    if _services is not None and _settings["voices"] != voices_before:
        _services.voices.forget()
    if _client is not None:
        _client.update_ambience()


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def _on_unload(*_args, **_kwargs):
    """Hariku is closing: say goodbye to the server, stop the ambience."""
    if _client is not None:
        _client.shutdown()
    if _services is not None:
        _services.ambience_player.shutdown(wait=1.0)


def register(bus):
    global _bus, _active, _settings, _services, _client, _panel
    _bus = bus
    _active = True
    _panel = None
    _settings = normalize_settings(core.api.load_data(DATA_KEY))
    _services = Services()
    _client = orbit_play.OrbitClient(_services)

    bus.subscribe("on_before_speak", _on_before_speak)
    bus.subscribe("on_unload", _on_unload)
    core.commands.add_intent(PLAY_INTENT, list(PLAY_PATTERNS), _on_play_intent,
                             title=_("title_play"))
    for name, description, title, callback, aliases, _answers in ACTIONS:
        core.hotkeys.register_action(EXT_NAME, name, _(description), None, False, callback)
        core.commands.add_aliases(action_id(name), list(aliases), title=_(title))
    core.commands.add_answer_actions([action_id(name) for name, *_rest, answers in ACTIONS
                                      if answers])
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("Orbit extension loaded.")


def teardown():
    global _active, _panel, _client
    try:
        _on_unload()
    except Exception:
        logger.exception("[Orbit] Stopping failed")
    _destroy_window()
    _active = False
    _panel = None
    _client = None
    try:
        core.commands.remove_intent(PLAY_INTENT)
    except Exception:
        pass
    for name, *_rest in ACTIONS:
        try:
            core.commands.remove_aliases(action_id(name))
        except Exception:
            pass
    if _bus is not None:
        for event_name, handler in (("on_before_speak", _on_before_speak),
                                    ("on_unload", _on_unload)):
            try:
                _bus.unsubscribe(event_name, handler)
            except Exception:
                pass
    logger.info("Orbit extension unloaded.")
