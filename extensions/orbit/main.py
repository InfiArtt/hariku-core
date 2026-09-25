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
space station orbiting the Earth, the entry hub of a shared simulation.
Walk the decks by compass, hang out in the Cantina, look down at Indonesia
from the Observation Deck, work your job, farm, mine the Asteroid Belt,
trade and take small missions.

Play it in its window ("Open Orbit", no key by default; "orbit" or "buka
orbit" to Aruna) or straight from Aruna, typed or spoken, with "orbit" in
front: "orbit utara", "orbit bilang halo", "orbit harian", "orbit panen",
"orbit status", "orbit keluar".

  orbit_ws.py      the WebSocket protocol (a copy of servers/orbit/orbit_ws.py)
  orbit_net.py     the connection: its own thread, pings, reconnecting
  orbit_parse.py   what was typed or said -> a command (Indonesian, English)
  orbit_play.py    playing: messages, speech, sounds, ambience (no wx)
  orbit_speech.py  who speaks: the narrator, or each player's own voice
  orbit_audio.py   which cue an event plays and from where; the ambience loop
  orbit_mix.py     finds a cue's file (yours, a sound theme's, the generated one) and places it
  orbit_text.py    Orbit's own words
  orbit_ui.py      the game window and the Preferences page
  orbit_sounds.py  makes the sounds in sounds/

The game itself runs on the server (servers/orbit in Hariku's source), which
decides everything; this extension only asks, shows and speaks. Orbit
connects only when you open it, press Connect or give it a command (or when
Hariku starts, if you ask it to).
"""

import logging
import os
import threading

import wx

import core.api
import core.commands
import core.hotkeys
import core.preferences
import core.sounds
import core.voice
from core.commands import Reply

import orbit_audio
import orbit_mix
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
USER_SOUNDS = "orbit_sounds"         # %APPDATA%\Hariku2\orbit_sounds: your own recordings
SOUND_CACHE = "orbit_sound_cache"
DEFAULT_SERVER = "wss://infiartt.com/orbit/ws"
PLAY_INTENT = f"{EXT_NAME}.play"
PLAY_PATTERNS = ("orbit {text}",)
OPEN_WORDS = {"buka", "open", "main", "play", "jendela", "window", "tampilkan", "show"}
MAX_COMMAND = 300
CONNECT_HOLD_SECONDS = 15
AUTOCONNECT_SECONDS = 5

READ_SETTINGS = ("read_say", "read_whisper", "read_shout", "read_moves", "read_money", "read_announce",
                 "read_events")
BOOL_SETTINGS = ("speak", "voices", "speak_own", "speak_names", "ambience", "sounds", "other_sounds",
                 "autoconnect") + READ_SETTINGS
DEFAULT_SETTINGS = {"server": DEFAULT_SERVER, "name": "", "job": "pilot", "speak": True,
                    "voices": True, "speak_own": True, "speak_names": True,
                    "ambience": True, "ambience_volume": 25, "sounds": True,
                    "effects_volume": 100, "other_sounds": True,
                    "read_say": True, "read_whisper": True, "read_shout": True, "read_moves": True,
                    "read_money": True, "read_announce": True, "read_events": True,
                    "background": "important", "close_action": "stay", "auto_logout": 30,
                    "autoconnect": False, "ignored": [], "close_hints": 0}


def _number(value, default, low=0, high=100):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = dict(DEFAULT_SETTINGS)
    settings["ignored"] = []
    for key in BOOL_SETTINGS:
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
    settings["ambience_volume"] = _number(raw.get("ambience_volume"), DEFAULT_SETTINGS["ambience_volume"])
    settings["effects_volume"] = _number(raw.get("effects_volume"), DEFAULT_SETTINGS["effects_volume"])
    if raw.get("background") in orbit_play.BACKGROUND_MODES:
        settings["background"] = raw["background"]
    if raw.get("close_action") in orbit_play.CLOSE_ACTIONS:
        settings["close_action"] = raw["close_action"]
    if raw.get("auto_logout") in orbit_play.AUTO_LOGOUT:
        settings["auto_logout"] = raw["auto_logout"]
    settings["close_hints"] = _number(raw.get("close_hints"), 0, 0, 99)
    ignored = raw.get("ignored")
    if isinstance(ignored, list):
        seen = set()
        for name in ignored:
            if isinstance(name, str) and name.strip() and name.strip().casefold() not in seen:
                seen.add(name.strip().casefold())
                settings["ignored"].append(name.strip()[:20])
        settings["ignored"] = settings["ignored"][:100]
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


def _sound_folders():
    """Where cues are looked for, in order: your own files, the sound theme's
    Orbit folder, the generated ones."""
    folders = [os.path.join(core.api.USER_DATA_DIR, USER_SOUNDS)]
    theme = core.sounds.get_theme_dir() if hasattr(core.sounds, "get_theme_dir") else None
    if theme:
        folders.append(os.path.join(theme, "orbit"))
    folders.append(SOUNDS_DIR)
    return folders


# ------------------------------------------------------------
# What playing uses from Hariku (orbit_play's services)
# ------------------------------------------------------------

class Services:
    def __init__(self):
        self.voices = orbit_speech.VoiceBook(
            lambda: [p["id"] for p in core.voice.get_providers()],
            core.voice.is_provider_available, core.voice.list_voices)
        self.ambience_player = orbit_audio.AmbiencePlayer(is_speaking=core.voice.is_speaking)
        self.mixer = orbit_mix.Mixer(_sound_folders, os.path.join(core.api.USER_DATA_DIR, SOUND_CACHE))

    # --- settings and accounts -------------------------------------------------------

    def settings(self):
        return dict(_settings)

    def set_setting(self, key, value):
        """A setting changed from the game ("suara pemain mati") or the client."""
        if key not in DEFAULT_SETTINGS:
            return
        voices_before = _settings["voices"]
        _settings.update(normalize_settings(dict(_settings, **{key: value})))
        _save_settings()
        if _settings["voices"] != voices_before:
            self.voices.forget()
            if _settings["voices"]:
                self.voices.refresh_in_background()
        if _panel:
            try:
                _panel.follow_settings(dict(_settings))
            except RuntimeError:
                pass

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

    def open_settings(self):
        core.api.open_preferences(_("ext_name"))

    def open_key(self):
        """The key that opens the Orbit window, or Aruna's words for it."""
        try:
            bindings = core.hotkeys.get_current_bindings(action_id("open"))
        except Exception:
            bindings = []
        if bindings:
            kc, ctrl, shift, alt, win, _is_global = bindings[0]
            return core.hotkeys.format_key_name(kc, ctrl, shift, alt, win)
        return ""

    # --- the connection, timers, threads ---------------------------------------------------

    def connect(self, url, hello, on_message, on_state):
        return orbit_net.Connection(url, hello, on_message, on_state)

    def call_later(self, seconds, fn):
        return _Timer(wx.CallLater(max(1, int(seconds * 1000)), fn))

    def call_after(self, fn, *args):
        _call_after(fn, *args)

    # --- speech -----------------------------------------------------------------------

    def say(self, text):
        """The narrator when Hariku Voice can't speak (narrator_voice() is None)."""
        return core.voice.announce(text, "command", interrupt=False)

    def narrator_voice(self):
        """Hariku Voice's own voice (Preferences, Hariku Voice), when it can speak now;
        else its Windows fallback voice; else None (the screen reader reads)."""
        settings = core.voice.get_settings()
        provider = settings.get("provider")
        if provider and core.voice.is_provider_available(provider):
            return {"provider": provider, "id": settings.get("voice") or ""}
        fallback = settings.get("fallback")
        if fallback and core.voice.is_provider_available(core.voice.WINDOWS):
            return {"provider": core.voice.WINDOWS, "id": fallback}
        return None

    def voice_count(self):
        """How many voices players can be given (None while they're being listed)."""
        cached = self.voices.cached()
        if cached is None:
            self.voices.refresh_in_background()
            return None
        settings = core.voice.get_settings()
        narrator = (settings["provider"], settings["voice"]) if settings.get("voice") else None
        return orbit_speech.pool_size(orbit_speech.voices_of(cached, self.language()), narrator)

    def speak_voice(self, text, voice, on_done):
        settings = core.voice.get_settings()
        return core.voice.preview(text, voice["provider"], voice["id"], rate=settings["rate"],
                                  volume=settings["volume"], stop_on_key=settings["stop_on_key"],
                                  on_done=on_done)

    def voice_busy(self):
        return core.voice.is_speaking()

    def voice_for(self, name, number=None):
        cached = self.voices.cached()
        if cached is None:
            self.voices.refresh_in_background()
            return None
        voices = orbit_speech.voices_of(cached, self.language())
        settings = core.voice.get_settings()
        narrator = (settings["provider"], settings["voice"]) if settings.get("voice") else None
        return orbit_speech.pick_voice(name, voices, exclude=narrator, number=number)

    def show_answer(self, text):
        if hasattr(core.commands, "show_answer"):
            core.commands.show_answer(text)

    def add_reminder(self, title, when):
        """A Hariku reminder at `when` (a local datetime): it rings even with Orbit closed."""
        import core.reminders
        core.reminders.add_reminder(title, when.strftime("%Y-%m-%d"), when.strftime("%H:%M"))
        return True

    # --- sounds -----------------------------------------------------------------------

    def play(self, name, pan=0.0, acoustics=None):
        """Play a cue (orbit_mix finds and places it). Returns False when there's no file."""
        if not self.mixer.variants(name):
            return False
        volume = _settings.get("effects_volume", 100) / 100.0

        def render():
            path = self.mixer.render(name, pan, volume, acoustics)
            if path:
                _call_after(core.sounds.play_sound, path)

        threading.Thread(target=render, daemon=True, name="orbit-sound").start()
        return True

    def ambience(self, name, volume):
        if name in orbit_audio.AMBIENCES:
            path = self.mixer.render(f"amb_{name}") or os.path.join(SOUNDS_DIR, f"amb_{name}.wav")
            self.ambience_player.play(path, volume)
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
        _frame = orbit_ui.OrbitFrame(_client, on_visibility=_client.update_ambience,
                                     on_settings=_services.open_settings if _services else None)
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
    parsed = orbit_parse.parse(text)
    if not _client.online() and "local" not in parsed and hasattr(core.commands, "hold_answer"):
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


def _leave():
    if _client is not None:
        _client.aruna_until = _client.clock() + orbit_play.ARUNA_SECONDS
        _client.submit("keluar", "aruna")


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
    ("status", "action_status", "title_status", _ask("status"),
     ("orbit status", "status orbit", "orbit connection status"), True),
    ("leave", "action_leave", "title_leave", _leave,
     ("orbit keluar", "keluar dari orbit", "orbit logout", "orbit log out", "leave orbit"), True),
    ("daily", "action_daily", "title_daily", _ask("harian"),
     ("orbit harian", "orbit bonus harian", "orbit daily", "orbit daily bonus"), True),
    ("harvest", "action_harvest", "title_harvest", _ask("panen"),
     ("orbit panen", "orbit harvest"), True),
    ("profile", "action_profile", "title_profile", _ask("profil"),
     ("orbit profil", "orbit profile"), True),
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
    def online():
        return _client is not None and _client.online()

    @staticmethod
    def status():
        return _client.status if _client is not None else _("status_idle")

    @staticmethod
    def character(server):
        return _services.account(server) if _services is not None else None

    @staticmethod
    def request_transfer_code():
        return _client is not None and _client.request_transfer_code()

    @staticmethod
    def redeem_transfer(code, server):
        return _client is not None and _client.redeem_transfer(code, server)

    @staticmethod
    def transfer_code():
        return _client.transfer_code if _client is not None else ""

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
    """Hariku is closing: goodbye to the server, stop the ambience."""
    if _client is not None:
        _client.shutdown()
    if _services is not None:
        _services.ambience_player.shutdown(wait=1.0)


def _autoconnect():
    if _active and _client is not None and _settings.get("autoconnect") \
            and not _client.online() and not _client.connecting():
        _client.connect()


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
    if _settings.get("autoconnect"):
        try:
            wx.CallLater(AUTOCONNECT_SECONDS * 1000, _autoconnect)
        except Exception:
            pass
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
