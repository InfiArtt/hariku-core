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
and the saving; the tests fake them. The server decides everything; this
only asks, shows and speaks.

What comes in is shown (the Messages list keeps the last 500 lines), played
(a cue for the event, from the side it happens on; the reactor's tones; the
ambience of the place) and read aloud when "Speak messages" is on:

  * other players' words (say, whisper, shout) in their own voice, when
    "A different voice for each player" is on and Hariku Voice has enough
    voices of your language: the voice a player chose ("my voice 3"), or
    one picked from their name (orbit_speech);
  * your own actions by their short confirmation ("Sent.", "Whispered to
    Sari.") while the Messages list keeps the whole line;
  * everything else by the narrator: Hariku Voice for commands, or the
    screen reader.

What is read can be narrowed (Preferences: chat, whispers, shouts, arrivals
and departures, work and money, announcements); what isn't read still goes
to the Messages list. While the window is closed, only whispers, your name
and station news are read (or everything, or nothing: a setting), and the
sounds follow. Players you ignore ("abaikan Budi") are neither shown nor
heard. A command from Aruna (or one of Orbit's actions) is always answered
aloud, and a line a player's voice reads also goes to Aruna's Last result.

Closing the window keeps you connected in the background (or leaves Orbit:
a setting); "keluar" ("quit"), the Leave button and quitting Hariku tell the
server goodbye, so you leave at once. With the window closed and nothing
typed for 5 minutes, others see you as away; after a while longer (a
setting) Orbit logs you out.

Accounts have no password: the first time you join a server, a random secret
is made on this computer and kept with the character's name for that server
only (a different server gets a different secret). The server keeps only a
hash of it. A transfer code moves the character to another computer: that
computer makes a secret of its own and sends it with the code.
"""

import datetime
import time

import orbit_audio
import orbit_parse
import orbit_speech
import orbit_ws
from orbit_text import _

PROTOCOL_VERSION = 1
CLIENT_NAME = "Hariku Orbit 1.1"
MAX_MESSAGES = 500
TRIM_MESSAGES = 50
MAX_LINE = 2000
ARUNA_SECONDS = 8.0
TALK_KINDS = ("say", "whisper", "shout")
OWN_TALK_KINDS = ("said", "whispered", "shouted")
JOBS = ("pilot", "engineer", "trader", "scientist", "security")
LANGUAGES = ("id", "en")
FAILURES = {"kicked": "fail_kicked", "replaced": "fail_replaced", "banned": "fail_banned"}
# What each read-aloud setting covers.
READ_KINDS = {"say": "read_say", "emote": "read_say", "whisper": "read_whisper", "shout": "read_shout",
              "arrive": "read_moves", "leave": "read_moves", "paid": "read_money",
              "failed": "read_money", "received": "read_money", "gave": "read_money",
              "trade": "read_money", "announce": "read_announce"}
IGNORABLE_KINDS = ("say", "whisper", "shout", "emote", "offer")
# With the window closed, "whispers, my name and events" reads these kinds (and your name).
BACKGROUND_KINDS = ("whisper", "announce", "system", "offer", "tones", "task")
BACKGROUND_MODES = ("all", "important", "none")
CLOSE_ACTIONS = ("stay", "leave")
AUTO_LOGOUT = (0, 15, 30, 60)
AWAY_SECONDS = 300
REMIND_BEFORE_SECONDS = 300           # a reminder of an event, five minutes before it
TICK_SECONDS = 20
CLOSE_HINTS = 3
TRANSFER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"
HELP_TOPICS_LOCAL = {"pengaturan", "settings", "setelan", "suara", "voices", "orbit"}


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


def transfer_letters(text):
    """A typed transfer code as its 16 letters, or "" when it can't be one."""
    letters = "".join(c for c in str(text or "").upper() if c.isalpha())
    if len(letters) != 16 or any(c not in TRANSFER_ALPHABET for c in letters):
        return ""
    return letters


class OrbitClient:
    def __init__(self, services, clock=time.monotonic):
        self.s = services
        self.clock = clock
        self.speaker = orbit_speech.Speaker(services, clock)
        self.voices_hint_said = False     # "too few voices" is said once a session
        self.schedule = []                # the events coming, from the server's last list
        self.pending_remind = None        # "remind me" asked before a list came
        self.wall_clock = time.time       # the real time, for reminders
        self.messages = []
        self.listeners = []
        self.conn = None
        self.url = None
        self.account = None
        self.state = "idle"
        self.status = _("status_idle")
        self.title_state = _("title_idle")
        self.me = None
        self.job = None
        self.room = None
        self.amb = None
        self.acoustics = None
        self.aruna_until = 0.0
        self.transfer_code = ""
        self.last_activity = clock()
        self.away = False
        self._said_offline = False
        self._announce = False
        self._token = None
        self._timer = None

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

    def _set_status(self, text, title=None):
        self.status = text
        if title is not None:
            self.title_state = title
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

    def _window_open(self):
        try:
            return bool(self.s.window_open())
        except Exception:
            return False

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
        if not account or not (account.get("joined") or account.get("pending")):
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
        self.state = "idle"
        self._said_offline = False
        self._announce = True
        self.away = False
        self.last_activity = self.clock()
        token = self._token = object()      # what an older connection says is ignored

        def on_message(message):
            self.s.call_after(self._message_if_current, token, message)

        def on_state(state, info):
            self.s.call_after(self._state_if_current, token, state, info)

        self.conn = self.s.connect(address, lambda: self.hello(self.account), on_message, on_state)
        self.conn.start()
        self._schedule_tick()
        return True

    def disconnect(self, say=True, bye=True):
        """Leave Orbit: tell the server goodbye (so the avatar leaves at once), then close."""
        conn, self.conn = self.conn, None
        self._token = None
        if conn is not None:
            if bye and self.state == "online":
                conn.send({"t": "cmd", "c": "bye"})
            conn.stop(wait=0)
        self.state = "stopped"
        self.me = None
        self.away = False
        self._cancel_tick()
        self._set_status(_("status_idle"), _("title_idle"))
        self._notify("state", self.state)
        self.update_ambience()
        if say and conn is not None:
            self._narrate(_("say_disconnected"), always=True)

    def hello(self, account):
        """The hello a connection sends (every time it connects) for `account`:
        with a transfer code while one waits to be used."""
        language = self.s.language()
        account = account or {}
        pending = account.get("pending") if isinstance(account.get("pending"), dict) else None
        message = {"t": "hello", "v": PROTOCOL_VERSION, "client": CLIENT_NAME,
                   "lang": language if language in LANGUAGES else "en"}
        if pending:
            message.update(secret=pending.get("secret", ""), transfer=pending.get("code", ""))
            return message
        message.update(secret=account.get("secret", ""), name=account.get("name", ""),
                       job=account.get("job", "pilot"))
        return message

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
            self._set_status(_("status_connecting"), _("title_connecting"))
            if self._announce and not info.get("attempt"):
                self._narrate(_("say_connecting"), always=True)
        elif state == "offline":
            seconds = int(round(float(info.get("retry_in") or 0)))
            self._set_status(_("status_offline", seconds=max(1, seconds)), _("title_offline"))
            if not self._said_offline:
                self._said_offline = True
                self._narrate(_("say_offline"), always=True)
        elif state == "failed":
            code = str(info.get("code") or "")
            text = info.get("text") if info.get("t") == "err" else None
            if self.account and self.account.get("pending") and code.startswith("transfer"):
                self._drop_pending()
            self._fail(text or _(FAILURES.get(code, "fail_other"), code=code))
            self.conn = None
            self._cancel_tick()
        elif state == "stopped":
            self._set_status(_("status_idle"), _("title_idle"))
        if state != "online" and previous == "online":
            self.me = None
        self._notify("state", state)
        self.update_ambience()

    def _fail(self, text):
        self.state = "failed" if self.state != "online" else self.state
        self._set_status(text, _("title_idle"))
        self.add_line(text)
        self._narrate(text, always=True)

    # --- what comes in ---------------------------------------------------------------

    def handle(self, message):
        kind = message.get("t")
        if kind == "welcome":
            self._welcome(message)
        elif kind == "ev":
            self._event(message)
            if isinstance(message.get("schedule"), list):
                self.schedule = [e for e in message["schedule"] if isinstance(e, dict) and e.get("at")]
                if self.pending_remind is not None:       # "remind me" was waiting for this list
                    name, self.pending_remind = self.pending_remind, None
                    self.remind(name, asked=True)
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
            pending = self.account.pop("pending", None)
            if isinstance(pending, dict) and pending.get("secret"):
                self.account["secret"] = pending["secret"]
            self.account.update(name=self.me, job=self.job, joined=True)
            self.s.save_account(self.url, dict(self.account))
        self._set_status(_("status_online", name=self.me, job=job_name(self.job)), _("title_online"))
        self._notify("state", "online")
        if self._said_offline:
            self._narrate(_("say_reconnected"), always=True)
        elif not message.get("resumed"):
            self._narrate(_("say_connected"), always=True)
        self._said_offline = False
        self._announce = False
        self._where(message)

    def _drop_pending(self):
        self.account.pop("pending", None)
        self.s.save_account(self.url, dict(self.account))

    def _where(self, message):
        if message.get("acoustics"):
            self.acoustics = message.get("acoustics")
        if message.get("amb"):
            self.room = message.get("room")
            self.amb = message.get("amb")
            self.update_ambience()

    def _ignored(self, message):
        actor = message.get("actor")
        if not isinstance(actor, str) or not actor:
            return False
        if message.get("k") not in IGNORABLE_KINDS and not message.get("ask"):
            return False
        ignored = {str(n).casefold() for n in self.s.settings().get("ignored") or []}
        return actor.casefold() in ignored

    def _background_allows(self, message, text):
        """With the window closed: whether this event may be heard at all."""
        mode = self.s.settings().get("background", "important")
        if mode == "all":
            return True
        if mode == "none":
            return False
        kind = message.get("k")
        if kind in BACKGROUND_KINDS:
            return True
        return bool(self.me) and kind in ("say", "shout", "emote") and self.me.casefold() in text.casefold()

    def _event(self, message):
        text = str(message.get("text") or "").strip()
        if not text or self._ignored(message):
            return
        self.add_line(text)
        self._where(message)
        if message.get("transfer_code"):
            self.transfer_code = str(message["transfer_code"])
            self._notify("transfer", self.transfer_code)
        settings = self.s.settings()
        aruna = self._aruna()
        heard = aruna or self._window_open() or self._background_allows(message, text)
        kind = message.get("k")
        actor = message.get("actor")
        others = bool(actor) and actor != self.me and kind in orbit_audio.OTHERS_KINDS
        sounds_on = settings.get("sounds", True) and heard and not (others and not settings.get("other_sounds", True))
        if sounds_on:
            for cue, pan, room, fallback in orbit_audio.cues_for(message, self.acoustics):
                if not self.s.play(cue, pan, room) and fallback:
                    self.s.play(fallback, pan, room)
        delay = 0.0
        tones = orbit_audio.tone_names(message.get("codes"))
        if tones and sounds_on:
            for i, name in enumerate(tones):
                self.s.call_later(0.3 + i * orbit_audio.TONE_GAP_SECONDS,
                                  lambda n=name: self.s.play(n))
            delay = 0.3 + len(tones) * orbit_audio.TONE_GAP_SECONDS + 0.2
        timed, wait = orbit_audio.timed_cues(message)
        if timed and sounds_on:
            for at, cue, pan in timed:
                self.s.call_later(at, lambda c=cue, p=pan: self.s.play(c, p, self.acoustics))
            delay = max(delay, wait)
        if not heard or not (settings.get("speak", True) or aruna):
            return
        setting = "read_events" if message.get("event") else READ_KINDS.get(kind)
        if setting and not aruna and not settings.get(setting, True) and (actor or kind != "emote"):
            return
        parts = self._parts(message, text, settings, aruna)
        if delay:
            self.s.call_later(delay, lambda: self.speaker.say_parts(parts))
        else:
            self.speaker.say_parts(parts)

    def _parts(self, message, text, settings, aruna):
        """What to say for an event, in parts: [(text, voice or None for the narrator)].
        Another player's line: their name in the narrator's voice ("Budi:"), then
        their words in their own voice. Your own line: your words in your voice
        (a whisper says who to first). Without enough voices, or with the words
        missing (an older server), the whole line in one voice."""
        kind = message.get("k")
        actor = message.get("actor")
        line = str(message.get("brief") or text)
        words = message.get("words")
        words = words.strip() if isinstance(words, str) else ""
        voices = settings.get("voices", True)
        names = settings.get("speak_names", True)
        if kind in TALK_KINDS and actor and actor != self.me:
            voice = self.s.voice_for(actor, message.get("voice")) if voices else None
            self._voices_hint(voices)
            if voice is None:
                return [(text, None)]
            if aruna:
                self.s.show_answer(text)
            if not words:
                return [(text, voice)]
            name = [(_(f"line_{kind}", name=actor), None)] if names else []
            return name + [(words, voice)]
        if kind in OWN_TALK_KINDS and words and settings.get("speak_own", True):
            if aruna:
                self.s.show_answer(line)          # Aruna's Last result: "Sent."
            voice = self.s.voice_for(self.me or "", message.get("voice") or None) if voices else None
            self._voices_hint(voices)
            to = message.get("to")
            first = [(_("line_whispered", name=to), None)] if kind == "whispered" and to and names else []
            return first + [(words, voice)]
        if message.get("preview") and voices:
            voice = self.s.voice_for(self.me or "", message.get("voice") or None)
            if voice is not None:
                return [(line, voice)]
        return [(line, None)]

    def _voices_hint(self, voices_on):
        """Once a session: Hariku Voice has too few voices to give players their own."""
        if not voices_on or self.voices_hint_said:
            return
        count = self.s.voice_count()
        if count is not None and count < 2:
            self.voices_hint_said = True
            text = _("voices_few")
            self.add_line(text)
            self.speaker.say(text)

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
            self._local(parsed)
            return "local"
        message = {"t": "cmd"}
        message.update(parsed)
        return self.send(message)

    def send(self, message):
        """A command for the server (connecting first when needed)."""
        self.last_activity = self.clock()
        self.away = False
        if self.conn is None or not self.conn.running():
            if not self.connect():
                return "failed"
        self.conn.send(message)
        return "sent" if self.online() else "queued"

    def _local(self, parsed):
        what = parsed["local"]
        if what == "help":
            topic = str(parsed.get("topic") or "")
            if topic and topic not in HELP_TOPICS_LOCAL:
                self.send({"t": "cmd", "c": "help", "a": topic})
                return
            text = _("help_settings") if topic else _("help")
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
        elif what == "status":
            self.say_status()
        elif what == "settings":
            self._narrate(_("say_settings"), always=True)
            self.s.open_settings()
        elif what == "set":
            self.set_setting(parsed["key"], parsed["value"])
        elif what in ("ignore", "unignore"):
            self.ignore(parsed.get("name", ""), what == "ignore")
        elif what == "remind":
            self.remind(parsed.get("name", ""))
        elif what == "ignored":
            names = self.s.settings().get("ignored") or []
            text = _("ignored_list", names=", ".join(names)) if names else _("ignored_none")
            self.add_line(text)
            self._narrate(text, always=True)

    def remind(self, name, asked=False):
        """A Hariku reminder five minutes before a coming event (the first, or the one named)."""
        name = str(name or "").strip()
        if not self.schedule and not asked:
            if self.online():
                self.pending_remind = name
                self.conn.send({"t": "cmd", "c": "events"})
                return
            text = _("remind_offline")
        else:
            wanted = name.casefold()
            chosen = next((e for e in self.schedule if not wanted or wanted in str(e.get("name", "")).casefold()
                           or wanted == str(e.get("event", "")).casefold()), None)
            if chosen is None:
                text = _("remind_unknown", name=name) if (name and self.schedule) else _("remind_none")
            else:
                at = float(chosen["at"])
                when = datetime.datetime.fromtimestamp(at - REMIND_BEFORE_SECONDS)
                if at - REMIND_BEFORE_SECONDS <= self.wall_clock():
                    text = _("remind_soon", name=chosen["name"])
                else:
                    self.s.add_reminder(_("remind_title", name=chosen["name"]), when)
                    text = _("remind_set", name=chosen["name"], when=when.strftime("%d-%m %H:%M"))
        self.add_line(text)
        self._narrate(text, always=True)

    def set_setting(self, key, value):
        self.s.set_setting(key, value)
        if key in ("effects_volume", "ambience_volume"):
            text = _(f"set_{key}", n=int(value))
        else:
            text = _(f"set_{key}_{'on' if value else 'off'}")
        self.add_line(text)
        self._narrate(text, always=True)
        self.update_ambience()

    def ignore(self, name, on):
        name = str(name or "").strip()[:20]
        if not name:
            return
        ignored = [n for n in (self.s.settings().get("ignored") or []) if n.casefold() != name.casefold()]
        if on:
            ignored.append(name)
        self.s.set_setting("ignored", ignored)
        text = _("ignoring", name=name) if on else _("unignoring", name=name)
        self.add_line(text)
        self._narrate(text, always=True)

    def say_status(self):
        """ "orbit status": the server's line when connected (room, players), else the state."""
        if self.online():
            self.last_activity = self.clock()
            self.conn.send({"t": "cmd", "c": "status"})         # asking isn't coming back
        else:
            self._narrate(self.status, always=True)

    # --- moving a character ---------------------------------------------------------------

    def request_transfer_code(self):
        """Ask the server for a code to move this character to another computer."""
        if not self.online():
            self._fail(_("transfer_offline"))
            return False
        self.send({"t": "cmd", "c": "transfer"})
        return True

    def redeem_transfer(self, typed, url=None):
        """Use a code from another computer: connect with it and a new secret."""
        code = transfer_letters(typed)
        if not code:
            self._fail(_("transfer_bad_code"))
            return False
        address = check_address(url if url is not None else self.s.settings().get("server", ""))
        if address is None:
            self._fail(_("err_address"))
            return False
        account = self.s.account(address) or {}
        account["pending"] = {"secret": self.s.new_secret(), "code": code}
        self.s.save_account(address, account)
        if self.conn is not None:
            self.disconnect(say=False)
        return self.connect(address)

    # --- the window, being away, logging out by itself ---------------------------------------

    def window_closing(self):
        """The window is being closed (Escape, the close button): stay or leave,
        as the setting says. Returns True when Orbit left."""
        settings = self.s.settings()
        if settings.get("close_action", "stay") == "leave":
            if self.conn is not None:
                self.disconnect()
            return True
        if self.online() or self.connecting():
            hints = int(settings.get("close_hints", 0) or 0)
            if hints < CLOSE_HINTS:
                self.s.set_setting("close_hints", hints + 1)
                key = self.s.open_key()
                self._narrate(_("say_background_hint_key", hotkey=key) if key else _("say_background_hint"),
                              always=True)
            else:
                self._narrate(_("say_background"), always=True)
        return False

    def _schedule_tick(self):
        if self._timer is None:
            self._timer = self.s.call_later(TICK_SECONDS, self._tick)

    def _cancel_tick(self):
        timer, self._timer = self._timer, None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _tick(self):
        self._timer = None
        if self.conn is None:
            return
        self.check_idle()
        self._schedule_tick()

    def check_idle(self):
        """Away after a while with the window closed; then, maybe, logged out."""
        if not self.online() or self._window_open():
            return
        idle = self.clock() - self.last_activity
        minutes = int(self.s.settings().get("auto_logout", 30) or 0)
        if minutes and idle >= minutes * 60:
            text = _("say_auto_logout")
            self.add_line(text)
            self._narrate(text, always=True)
            self.disconnect(say=False)
            return
        if idle >= AWAY_SECONDS and not self.away:
            self.away = True
            self.conn.send({"t": "cmd", "c": "away", "on": True})

    # --- the ambience ----------------------------------------------------------------

    def update_ambience(self):
        settings = self.s.settings()
        if (self.state == "online" and self.amb and settings.get("ambience", True)
                and self._window_open()):
            self.s.ambience(self.amb, settings.get("ambience_volume", 30))
        else:
            self.s.ambience(None, None)

    def shutdown(self):
        """Hariku is closing: goodbye to the server, if there's time."""
        self.speaker.clear()
        self._cancel_tick()
        conn, self.conn = self.conn, None
        self._token = None
        if conn is not None:
            if self.state == "online":
                conn.send({"t": "cmd", "c": "bye"})
            conn.stop(wait=1.0)
        self.state = "stopped"
        self.s.ambience(None, None)
