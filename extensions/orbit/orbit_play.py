# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Playing Orbit: the connection, what comes in, and what the player types or
says, without wx. main.py's Services do the speaking, the sounds, the timers
and the saving; the tests fake them.

What comes in is shown (the Messages list keeps the last 500 lines), played
(a sound for the kind of event, the reactor's tones, the ambience of the
place) and read aloud, when "Speak messages" is on:

  * other players' words (say, whisper, shout) in their own voice, when
    "A different voice for each player" is on and Hariku Voice has enough
    voices of your language (orbit_speech.pick_voice);
  * your own actions by their short confirmation ("Sent.", "Whispered to
    Sari.") while the Messages list keeps the whole line;
  * everything else by the narrator: Hariku Voice for commands, or the
    screen reader.

A command from Aruna (or one of Orbit's actions) is always answered aloud,
whatever the setting, and a line a player's voice reads is also shown in
Aruna's Last result (core.commands.show_answer).

Accounts have no password: the first time you join a server, a random secret
is made on this computer and kept with the character's name for that server
only (a different server gets a different secret). The server keeps only a
hash of it.
"""

import time

import orbit_audio
import orbit_parse
import orbit_speech
import orbit_ws
from orbit_text import _

PROTOCOL_VERSION = 1
CLIENT_NAME = "Hariku Orbit 1.0"
MAX_MESSAGES = 500
TRIM_MESSAGES = 50
MAX_LINE = 2000
ARUNA_SECONDS = 8.0
TALK_KINDS = ("say", "whisper", "shout")
JOBS = ("pilot", "engineer", "trader", "scientist", "security")
LANGUAGES = ("id", "en")
FAILURES = {"kicked": "fail_kicked", "replaced": "fail_replaced", "banned": "fail_banned"}


def job_name(job):
    return _(f"job_{job}") if job in JOBS else str(job or "")


def check_address(url):
    """The address if it can be used, else None: wss:// anywhere, ws:// only
    on this computer (anything else would send the secret unencrypted)."""
    try:
        secure, host, _port, _path = orbit_ws.parse_url(url)
    except ValueError:
        return None
    if not secure and not orbit_ws.is_local(host):
        return None
    return str(url).strip()


class OrbitClient:
    def __init__(self, services, clock=time.monotonic):
        self.s = services
        self.clock = clock
        self.speaker = orbit_speech.Speaker(services, clock)
        self.messages = []
        self.listeners = []
        self.conn = None
        self.url = None
        self.account = None
        self.state = "idle"
        self.status = _("status_idle")
        self.me = None
        self.job = None
        self.room = None
        self.amb = None
        self.aruna_until = 0.0
        self._said_offline = False
        self._announce = False
        self._token = None

    # --- listeners (the window, the Preferences page) ------------------------------------

    def add_listener(self, fn):
        if fn not in self.listeners:
            self.listeners.append(fn)

    def remove_listener(self, fn):
        if fn in self.listeners:
            self.listeners.remove(fn)

    def _notify(self, event, value=None):
        for fn in list(self.listeners):
            try:
                fn(event, value)
            except Exception:
                self.remove_listener(fn)       # a window that is gone

    def _set_status(self, text):
        self.status = text
        self._notify("status", text)

    def add_line(self, text):
        text = " ".join(str(text or "").split())[:MAX_LINE]
        if not text:
            return
        self.messages.append(text)
        self._notify("message", text)
        if len(self.messages) > MAX_MESSAGES:
            del self.messages[:TRIM_MESSAGES]
            self._notify("trim", TRIM_MESSAGES)

    def _narrate(self, text, always=False):
        """A line of the client's own, read by the narrator."""
        if always or self.s.settings().get("speak", True) or self._aruna():
            self.speaker.say(text)

    def _aruna(self):
        return self.clock() < self.aruna_until

    # --- connecting ------------------------------------------------------------------

    def online(self):
        return self.state == "online"

    def connecting(self):
        return self.conn is not None and self.conn.running()

    def connect(self, url=None, name=None, job=None):
        """Connect with the settings (or, from the Preferences page, what it
        shows). Returns False, saying why, when it can't start."""
        settings = self.s.settings()
        address = check_address(url if url is not None else settings.get("server", ""))
        if address is None:
            self._fail(_("err_address"))
            return False
        account = self.s.account(address)
        if not account or not account.get("joined"):
            name = str(name if name is not None else settings.get("name", "")).strip()
            job = job if job in JOBS else settings.get("job", "pilot")
            if not name:
                self._fail(_("err_no_name"))
                return False
            account = dict(account or {}, name=name, job=job, joined=False)
            if not account.get("secret"):
                account["secret"] = self.s.new_secret()
            self.s.save_account(address, account)
        if self.conn is not None:
            self.conn.stop(wait=0)
        self.url = address
        self.account = dict(account)
        self._said_offline = False
        self._announce = True
        token = self._token = object()      # what an older connection says is ignored
        hello = self.hello(self.account)

        def on_message(message):
            self.s.call_after(self._message_if_current, token, message)

        def on_state(state, info):
            self.s.call_after(self._state_if_current, token, state, info)

        self.conn = self.s.connect(address, lambda: dict(hello), on_message, on_state)
        self.conn.start()
        return True

    def disconnect(self, say=True):
        conn, self.conn = self.conn, None
        self._token = None
        if conn is not None:
            conn.stop(wait=0)
        self.state = "stopped"
        self.me = None
        self._set_status(_("status_idle"))
        self._notify("state", self.state)
        self.update_ambience()
        if say and conn is not None:
            self._narrate(_("say_disconnected"), always=True)

    def hello(self, account):
        """The hello a connection sends (every time it connects) for `account`."""
        language = self.s.language()
        return {"t": "hello", "v": PROTOCOL_VERSION, "client": CLIENT_NAME,
                "lang": language if language in LANGUAGES else "en",
                "secret": account.get("secret", ""), "name": account.get("name", ""),
                "job": account.get("job", "pilot")}

    def _message_if_current(self, token, message):
        if token is self._token and self.conn is not None:
            self.handle(message)

    def _state_if_current(self, token, state, info):
        if token is self._token and self.conn is not None:
            self.state_changed(state, info)

    def state_changed(self, state, info=None):
        info = info if isinstance(info, dict) else {}
        previous, self.state = self.state, state
        if state == "connecting":
            self._set_status(_("status_connecting"))
            if self._announce and not info.get("attempt"):
                self._narrate(_("say_connecting"), always=True)
        elif state == "offline":
            seconds = int(round(float(info.get("retry_in") or 0)))
            self._set_status(_("status_offline", seconds=max(1, seconds)))
            if not self._said_offline:
                self._said_offline = True
                self._narrate(_("say_offline"), always=True)
        elif state == "failed":
            code = str(info.get("code") or "")
            text = info.get("text") if info.get("t") == "err" else None
            self._fail(text or _(FAILURES.get(code, "fail_other"), code=code))
            self.conn = None
        elif state == "stopped":
            self._set_status(_("status_idle"))
        if state != "online" and previous == "online":
            self.me = None
        self._notify("state", state)
        self.update_ambience()

    def _fail(self, text):
        self.state = "failed" if self.state != "online" else self.state
        self._set_status(text)
        self.add_line(text)
        self._narrate(text, always=True)

    # --- what comes in ---------------------------------------------------------------

    def handle(self, message):
        kind = message.get("t")
        if kind == "welcome":
            self._welcome(message)
        elif kind == "ev":
            self._event(message)
        elif kind == "err":
            text = str(message.get("text") or "")
            if text:
                self.add_line(text)
                self._narrate(text, always=True)

    def _welcome(self, message):
        self.state = "online"
        self.me = str(message.get("name") or "")
        self.job = message.get("job")
        if self.account is not None:
            self.account.update(name=self.me, job=self.job, joined=True)
            self.s.save_account(self.url, dict(self.account))
        self._set_status(_("status_online", name=self.me, job=job_name(self.job)))
        self._notify("state", "online")
        if not message.get("resumed") or self._said_offline:
            self._narrate(_("say_connected"), always=True)
        self._said_offline = False
        self._announce = False
        self._where(message)

    def _where(self, message):
        if message.get("amb"):
            self.room = message.get("room")
            self.amb = message.get("amb")
            self.update_ambience()

    def _event(self, message):
        text = str(message.get("text") or "").strip()
        if not text:
            return
        self.add_line(text)
        self._where(message)
        settings = self.s.settings()
        sounds_on = settings.get("sounds", True)
        sound = orbit_audio.sound_for(message)
        if sound and sounds_on:
            self.s.play(sound)
        delay = 0.0
        tones = orbit_audio.tone_names(message.get("codes"))
        if tones and sounds_on:
            for i, name in enumerate(tones):
                self.s.call_later(0.3 + i * orbit_audio.TONE_GAP_SECONDS,
                                  lambda n=name: self.s.play(n))
            delay = 0.3 + len(tones) * orbit_audio.TONE_GAP_SECONDS + 0.2
        aruna = self._aruna()
        if not (settings.get("speak", True) or aruna):
            return
        line = str(message.get("brief") or text)
        voice = None
        actor = message.get("actor")
        if (message.get("k") in TALK_KINDS and actor and actor != self.me
                and settings.get("voices", True)):
            voice = self.s.voice_for(actor)
        if voice is not None and aruna:
            self.s.show_answer(line)
        if delay:
            self.s.call_later(delay, lambda: self.speaker.say(line, voice))
        else:
            self.speaker.say(line, voice)

    # --- what the player asks --------------------------------------------------------

    def submit(self, text, source="window"):
        """Handle a typed or spoken command. `source` is "window" or "aruna"
        (Aruna and Orbit's actions: always answered aloud). Returns "empty",
        "local", "sent", "queued" or "failed"."""
        parsed = orbit_parse.parse(text)
        if parsed is None:
            return "empty"
        if source == "aruna":
            self.aruna_until = self.clock() + ARUNA_SECONDS
        if "local" in parsed:
            self._local(parsed["local"])
            return "local"
        message = {"t": "cmd"}
        message.update(parsed)
        if self.conn is None or not self.conn.running():
            if not self.connect():
                return "failed"
        self.conn.send(message)
        return "sent" if self.online() else "queued"

    def _local(self, what):
        if what == "help":
            text = _("help")
            self.add_line(text)
            self._narrate(text, always=True)
        elif what == "connect":
            if self.online() or self.connecting():
                self._narrate(self.status, always=True)
            else:
                self.connect()
        elif what == "disconnect":
            if self.conn is None:
                self._narrate(_("status_idle"), always=True)
            else:
                self.disconnect()
        elif what == "repeat":
            self._narrate(self.messages[-1] if self.messages else _("nothing_yet"), always=True)

    # --- the ambience ----------------------------------------------------------------

    def update_ambience(self):
        settings = self.s.settings()
        if (self.state == "online" and self.amb and settings.get("ambience", True)
                and self.s.window_open()):
            self.s.ambience(self.amb, settings.get("ambience_volume", 30))
        else:
            self.s.ambience(None, None)

    def shutdown(self):
        self.speaker.clear()
        conn, self.conn = self.conn, None
        self._token = None
        if conn is not None:
            conn.stop(wait=1.0)
        self.s.ambience(None, None)
