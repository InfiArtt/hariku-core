# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Hariku Voice (since core 2.7): four kinds of Hariku's own announcements, the
startup greeting, the Briefing and evening summary, fired reminders and the
answers to commands (the command bar, Ctrl+Alt+Backspace), can be spoken by a
voice the user picks instead of their screen reader. Everything else stays
with the screen reader, and a braille display still gets the text.

Voices come from providers. "windows" (SAPI 5, core/voice_sapi.py) is built in
and is the fallback; extensions add more with register_provider() (Edge Voices
adds "edge"). A provider only has to list its voices and speak text without
blocking; providers that produce audio files can hand them to play_file().

announce() decides per kind: with Hariku Voice off (the default) the text goes
to core.speech.speak() as before. With it on, the chosen voice speaks; when
that fails, the fallback Windows voice, then the screen reader. One worker
thread speaks one announcement at a time; while it does, it watches
GetLastInputInfo so a key press can stop it. No keyboard hook is ever used.

The kinds are off until the user turns them on, except "command": the user
asked for command answers in their Hariku Voice, so it is on by default, but
only once they have set up Hariku Voice (saved its page); before that the
screen reader speaks them.

route_speech(kind, seconds) sends core.speech.speak() to Hariku Voice for a
short while: an action run from the command bar speaks through speak(),
often seconds later after a download, and that answer should come in the
same voice. The window ends at the next key press (GetLastInputInfo again),
after `seconds`, or with stop_routing().

Settings live in Core.json under "hariku_voice" (see DEFAULT_SETTINGS).
"""
import collections
import ctypes
import ctypes.wintypes
import itertools
import logging
import os
import re
import threading
import time

import core.api
from core.events import bus
from core.i18n import get_translator

_ = get_translator("core")

logger = logging.getLogger(__name__)

KINDS = ("greeting", "briefing", "reminder", "command")
# Off until the user turns them on; "command" is on by default (see above).
DEFAULT_KINDS = {"greeting": False, "briefing": False, "reminder": False, "command": True}
# Kinds that are on by default speak with Hariku Voice only once the user has
# set it up (the settings exist in Core.json); before that, the screen reader.
NEEDS_SETUP = frozenset(kind for kind, on in DEFAULT_KINDS.items() if on)
GENDERS = ("female", "male")        # a voice's "gender", or "" when it has none
WINDOWS = "windows"                 # the built-in provider, also the fallback
SETTINGS_KEY = "hariku_voice"       # in Core.json
RATE_MIN, RATE_MAX = -10, 10        # 0 is the voice's normal rate
VOLUME_MIN, VOLUME_MAX = 0, 100
DEFAULT_SETTINGS = {
    "kinds": dict(DEFAULT_KINDS),   # nothing changes until the user sets it up
    "provider": WINDOWS,
    "voice": "",            # "" = the provider's default voice
    "rate": 0,
    "volume": 100,
    "fallback": "",         # a Windows voice id, or "" for the screen reader
    "stop_on_key": True,
}

POLL_SECONDS = 0.1            # how often the worker checks for key presses
STOP_GRACE_SECONDS = 2.0      # how long a stopped provider gets to report back
KEY_GRACE_SECONDS = 0.5       # input right after speech starts (the key that
KEY_HELD_GRACE_SECONDS = 3.0  # started it being released) doesn't stop it
MOUSE_MOVE_SECONDS = 0.3      # input this soon after the pointer moved is the mouse
PLAYER_POLL_SECONDS = 0.05
ROUTE_SECONDS = 20.0          # route_speech(): how long speech goes to Hariku Voice
ROUTE_MAX_SECONDS = 60.0

_PROVIDER_ID_RE = re.compile(r"[a-z0-9_]{1,32}\Z")


# ------------------------------------------------------------
# Provider registry
# ------------------------------------------------------------

class _Provider:
    def __init__(self, provider_id, name, list_voices, speak, stop, is_available, privacy_note):
        self.id = provider_id
        self._name = name
        self.list_voices = list_voices
        self.speak = speak
        self.stop = stop
        self.is_available = is_available
        self._privacy_note = privacy_note

    @staticmethod
    def _text(value):
        try:
            value = value() if callable(value) else value
        except Exception:
            logger.exception("Hariku Voice: a provider's text could not be read")
            return ""
        return value if isinstance(value, str) else ""

    @property
    def name(self):
        return self._text(self._name) or self.id

    @property
    def privacy_note(self):
        return self._text(self._privacy_note)


_providers = collections.OrderedDict()
_providers_lock = threading.RLock()


def register_provider(provider_id, name, list_voices, speak, stop, is_available=None,
                      privacy_note=""):
    """Add a voice source to Hariku Voice (or replace one with the same id).

    provider_id   lower-case letters, digits and "_", at most 32 ("edge").
    name          what Preferences shows ("Microsoft Edge neural voices (online)").
    list_voices() a list of {"id", "name", "language" (BCP-47, e.g. "id-ID")},
                  optionally with "gender" ("female" or "male"; leave it out
                  when you don't know). "name" is the voice's own name
                  ("Gadis"), without its language or gender: the page groups
                  the voices by language, then gender, and lists the names.
                  May be slow or use the network: it is never called on the UI thread.
    speak(text, voice_id, rate, volume, on_done)
                  start speaking and return at once. voice_id "" means your
                  default voice; rate is -10..10 (0 normal), volume 0..100.
                  Call on_done(None) when finished or stopped, or on_done(error)
                  when it could not speak, exactly once, from any thread.
    stop()        stop the current speech now (thread-safe, must not block).
    is_available() False while the source can't work (offline, blocked). Must be
                  fast: it is asked before every announcement.
    privacy_note  shown on the Hariku Voice page when this source is selected.

    `name` and `privacy_note` may also be functions returning the text.
    """
    if not isinstance(provider_id, str) or not _PROVIDER_ID_RE.match(provider_id):
        raise ValueError(f"invalid provider id: {provider_id!r}")
    for label, fn in (("list_voices", list_voices), ("speak", speak), ("stop", stop)):
        if not callable(fn):
            raise TypeError(f"{label} must be callable")
    if is_available is not None and not callable(is_available):
        raise TypeError("is_available must be callable or None")
    if not (isinstance(name, str) or callable(name)):
        raise TypeError("name must be a string")
    provider = _Provider(provider_id, name, list_voices, speak, stop, is_available,
                         privacy_note or "")
    with _providers_lock:
        replaced = provider_id in _providers
        _providers[provider_id] = provider
        if not replaced and provider_id != WINDOWS and WINDOWS in _providers:
            _providers.move_to_end(provider_id)
    _forget_failures(provider_id)
    logger.info(f"Hariku Voice: {'replaced' if replaced else 'registered'} provider '{provider_id}'.")
    return True


def unregister_provider(provider_id):
    """Remove a provider (an extension's teardown()). Speech from it stops.
    The built-in Windows provider stays. Returns whether one was removed."""
    if provider_id == WINDOWS:
        logger.warning("Hariku Voice: the Windows voice provider can't be removed.")
        return False
    with _providers_lock:
        provider = _providers.pop(provider_id, None)
    if provider is None:
        return False
    if _announcer.uses(provider_id):
        _announcer.stop()
    try:
        provider.stop()
    except Exception:
        logger.exception(f"Hariku Voice: stopping provider '{provider_id}' failed")
    logger.info(f"Hariku Voice: unregistered provider '{provider_id}'.")
    return True


def _get_provider(provider_id):
    with _providers_lock:
        return _providers.get(provider_id)


def get_providers():
    """The registered sources, the Windows voices first:
    [{"id", "name", "privacy_note"}]."""
    with _providers_lock:
        providers = list(_providers.values())
    providers.sort(key=lambda p: p.id != WINDOWS)
    return [{"id": p.id, "name": p.name, "privacy_note": p.privacy_note} for p in providers]


def is_provider_available(provider_id):
    """True when the provider is registered and says it can speak now."""
    provider = _get_provider(provider_id)
    if provider is None:
        return False
    if provider.is_available is None:
        return True
    try:
        return bool(provider.is_available())
    except Exception:
        logger.exception(f"Hariku Voice: is_available() of '{provider_id}' failed")
        return False


def list_voices(provider_id):
    """The provider's voices as [{"id", "name", "language", "gender", ...}],
    checked and without duplicates; "gender" is "female", "male" or "". Slow:
    call it on a worker thread. Raises what the provider raises, or ValueError
    for an unknown provider."""
    provider = _get_provider(provider_id)
    if provider is None:
        raise ValueError(f"unknown voice provider: {provider_id!r}")
    voices, seen = [], set()
    for item in provider.list_voices() or ():
        if not isinstance(item, dict):
            continue
        voice_id = item.get("id")
        if not isinstance(voice_id, str) or not voice_id or voice_id in seen:
            continue
        seen.add(voice_id)
        entry = dict(item)
        entry["id"] = voice_id
        entry["name"] = str(item.get("name") or voice_id)
        language = item.get("language")
        entry["language"] = language if isinstance(language, str) else ""
        gender = item.get("gender")
        gender = gender.strip().lower() if isinstance(gender, str) else ""
        entry["gender"] = gender if gender in GENDERS else ""
        voices.append(entry)
    return voices


# ------------------------------------------------------------
# Languages
# ------------------------------------------------------------

def _primary(tag):
    return str(tag or "").replace("_", "-").split("-")[0].strip().lower()


def _windows_locale():
    try:
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.WinDLL("kernel32").GetUserDefaultLocaleName(buf, 85):
            return buf.value
    except Exception:
        pass
    return ""


def user_languages():
    """Language codes to list first: Hariku's language, then Windows' own."""
    from core.i18n import get_current_language
    languages = []
    for tag in (get_current_language(), _windows_locale()):
        primary = _primary(tag)
        if primary and primary not in languages:
            languages.append(primary)
    return languages


def order_voices(voices, languages=None):
    """Voices in the user's languages first (Hariku's, then Windows'), then the
    rest, each group by language and name."""
    preferred = [p for p in (_primary(l) for l in (
        user_languages() if languages is None else languages)) if p]

    def key(voice):
        primary = _primary(voice.get("language"))
        rank = preferred.index(primary) if primary in preferred else len(preferred)
        return (rank, str(voice.get("language") or "").lower(),
                str(voice.get("name") or "").lower())

    return sorted(voices, key=key)


LOCALE_SLOCALIZEDDISPLAYNAME = 0x02


def language_name(tag):
    """A readable name for a BCP-47 tag in Windows' language, e.g.
    "Indonesian (Indonesia)"; the tag itself when Windows doesn't know it."""
    if not tag:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(128)
        if ctypes.WinDLL("kernel32").GetLocaleInfoEx(str(tag), LOCALE_SLOCALIZEDDISPLAYNAME,
                                                     buf, 128):
            return buf.value or str(tag)
    except Exception:
        pass
    return str(tag)


# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------

def _int_in(value, low, high, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def normalize_settings(raw):
    """Settings as stored, from anything (a hand-edited file included)."""
    raw = raw if isinstance(raw, dict) else {}
    kinds = raw.get("kinds") if isinstance(raw.get("kinds"), dict) else {}
    provider = raw.get("provider")
    if not isinstance(provider, str) or not _PROVIDER_ID_RE.match(provider):
        provider = WINDOWS
    voice = raw.get("voice")
    fallback = raw.get("fallback")
    return {
        "kinds": {kind: bool(kinds.get(kind, DEFAULT_KINDS[kind])) for kind in KINDS},
        "provider": provider,
        "voice": voice if isinstance(voice, str) else "",
        "rate": _int_in(raw.get("rate"), RATE_MIN, RATE_MAX, 0),
        "volume": _int_in(raw.get("volume"), VOLUME_MIN, VOLUME_MAX, 100),
        "fallback": fallback if isinstance(fallback, str) else "",
        "stop_on_key": bool(raw.get("stop_on_key", True)),
    }


def _core_config():
    config = core.api.load_data("Core")
    return config if isinstance(config, dict) else {}


def get_settings():
    """The Hariku Voice settings (see DEFAULT_SETTINGS)."""
    return normalize_settings(_core_config().get(SETTINGS_KEY))


def save_settings(settings):
    """Check and save the settings; returns whether the save worked."""
    config = _core_config()
    config[SETTINGS_KEY] = normalize_settings(settings)
    return core.api.save_data("Core", config)


def is_configured(config=None):
    """Whether the user has set up Hariku Voice (saved its page)."""
    config = _core_config() if config is None else config
    return isinstance(config.get(SETTINGS_KEY), dict)


def is_enabled(kind):
    """Whether Hariku Voice speaks this kind of announcement."""
    config = _core_config()
    if kind in NEEDS_SETUP and not is_configured(config):
        return False
    return normalize_settings(config.get(SETTINGS_KEY))["kinds"].get(kind, False)


def cache_dir(provider_id):
    """A folder for a provider's saved audio, %APPDATA%\\Hariku2\\voice_cache\\<id>,
    created if missing."""
    if not isinstance(provider_id, str) or not _PROVIDER_ID_RE.match(provider_id):
        raise ValueError(f"invalid provider id: {provider_id!r}")
    path = os.path.join(core.api.USER_DATA_DIR, "voice_cache", provider_id)
    os.makedirs(path, exist_ok=True)
    return path


# ------------------------------------------------------------
# Logging failures once
# ------------------------------------------------------------

_logged = set()
_logged_lock = threading.Lock()


def _log_once(key, message):
    with _logged_lock:
        first = key not in _logged
        _logged.add(key)
    if first:
        logger.warning(message)
    else:
        logger.debug(message)


def _forget_failures(provider_id):
    """After the provider works again, its next failure is logged again."""
    with _logged_lock:
        for key in [k for k in _logged if len(k) > 1 and k[1] == provider_id]:
            _logged.discard(key)


# ------------------------------------------------------------
# Watching for key presses (GetLastInputInfo; never a keyboard hook)
# ------------------------------------------------------------

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]


_user32_dll = None


def _user32():
    global _user32_dll
    if _user32_dll is None:
        dll = ctypes.WinDLL("user32")   # our own instance: argtypes stay private
        dll.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
        dll.GetLastInputInfo.restype = ctypes.wintypes.BOOL
        dll.GetAsyncKeyState.argtypes = [ctypes.c_int]
        dll.GetAsyncKeyState.restype = ctypes.c_short
        dll.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
        dll.GetCursorPos.restype = ctypes.wintypes.BOOL
        dll.PeekMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG), ctypes.wintypes.HWND,
                                     ctypes.wintypes.UINT, ctypes.wintypes.UINT,
                                     ctypes.wintypes.UINT]
        dll.PeekMessageW.restype = ctypes.wintypes.BOOL
        dll.TranslateMessage.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
        dll.DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
        dll.DispatchMessageW.restype = ctypes.c_ssize_t
        _user32_dll = dll
    return _user32_dll


def _last_input_tick():
    """GetTickCount() of the last keyboard or mouse input in this session."""
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if _user32().GetLastInputInfo(ctypes.byref(info)):
            return info.dwTime
    except Exception:
        pass
    return None


def _any_key_down():
    """Whether a keyboard key is held down right now (mouse buttons excluded)."""
    try:
        state = _user32().GetAsyncKeyState
        return any(state(vk) & 0x8000 for vk in range(0x08, 0xFF))
    except Exception:
        return False


def _cursor_pos():
    try:
        point = ctypes.wintypes.POINT()
        if _user32().GetCursorPos(ctypes.byref(point)):
            return (point.x, point.y)
    except Exception:
        pass
    return None


def _pump_messages():
    """Dispatch window messages queued for this worker thread, if any. COM and
    MCI may create hidden windows on the thread that uses them; this keeps them
    served without needing Hariku's UI loop."""
    try:
        user32 = _user32()
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):   # PM_REMOVE
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except Exception:
        pass


class _KeyWatch:
    """Notices a key press after speech started, from GetLastInputInfo polled on
    the voice worker. Input in the first moment (the key that started the
    announcement being released) and plain mouse movement don't count."""

    def __init__(self):
        self._start = time.monotonic()
        self._baseline = _last_input_tick()
        self._cursor = _cursor_pos()
        self._moved_at = float("-inf")

    def key_pressed(self):
        now = time.monotonic()
        tick = _last_input_tick()
        cursor = _cursor_pos()
        if cursor != self._cursor:
            self._cursor = cursor
            self._moved_at = now
        if tick is None or tick == self._baseline:
            return False
        elapsed = now - self._start
        held = _any_key_down()
        if elapsed < KEY_GRACE_SECONDS or (held and elapsed < KEY_HELD_GRACE_SECONDS):
            self._baseline = tick
            return False
        if not held and now - self._moved_at < MOUSE_MOVE_SECONDS:
            self._baseline = tick     # the mouse moved; that isn't a key press
            return False
        return True


# ------------------------------------------------------------
# The announcer: one worker, one announcement at a time
# ------------------------------------------------------------

class _Job:
    def __init__(self, text, chain, rate, volume, stop_on_key, reader_fallback,
                 interrupt=False, kind=None, on_done=None):
        self.text = text
        self.chain = list(chain)
        self.rate = rate
        self.volume = volume
        self.stop_on_key = stop_on_key
        self.reader_fallback = reader_fallback
        self.interrupt = interrupt
        self.kind = kind
        self.cancelled = False
        self.wake = threading.Event()
        self._on_done = on_done
        self._finished = False
        self._lock = threading.Lock()

    def cancel(self):
        self.cancelled = True
        self.wake.set()

    def finish(self, error=None):
        with self._lock:
            if self._finished:
                return
            self._finished = True
        if self._on_done is not None:
            try:
                self._on_done(error)
            except Exception:
                logger.exception("Hariku Voice: an on_done callback failed")


def _time_limit(text, rate):
    """Generous upper bound for speaking `text`, in seconds (a stuck provider
    must not block every later announcement)."""
    speed = 3.0 ** (max(RATE_MIN, min(RATE_MAX, rate)) / 10.0)
    return 30.0 + 2.0 * len(text) / (8.0 * speed)


class _Announcer:
    def __init__(self):
        self._cond = threading.Condition()
        self._queue = collections.deque()
        self._current = None
        self._current_provider = None
        self._thread = None

    def submit(self, job, interrupt):
        dropped = []
        with self._cond:
            if interrupt:
                dropped = self._cancel_all_locked()
            self._queue.append(job)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True,
                                                name="hariku-voice")
                self._thread.start()
            self._cond.notify_all()
        for old in dropped:
            old.finish(None)

    def stop(self):
        with self._cond:
            dropped = self._cancel_all_locked()
            self._cond.notify_all()
        for old in dropped:
            old.finish(None)

    def busy(self):
        with self._cond:
            return self._current is not None or bool(self._queue)

    def uses(self, provider_id):
        with self._cond:
            return self._current_provider == provider_id or any(
                provider_id == pid for job in self._queue for pid, _v in job.chain)

    def _cancel_all_locked(self):
        """Cancel the current job and empty the queue; returns the dropped jobs,
        whose on_done the caller runs once the lock is released."""
        dropped = list(self._queue)
        self._queue.clear()
        for job in dropped:
            job.cancel()
        if self._current is not None:
            self._current.cancel()
        return dropped

    def _run(self):
        while True:
            with self._cond:
                while not self._queue:
                    self._cond.wait()
                job = self._queue.popleft()
                self._current = job
            error = None
            try:
                error = self._speak(job)
            except Exception as e:
                logger.exception("Hariku Voice: the announcement failed")
                error = e
            finally:
                with self._cond:
                    self._current = None
                    self._current_provider = None
                job.finish(error)

    def _speak(self, job):
        """Try each (provider, voice) of the job's chain, then the screen reader.
        Returns None, or the last error when nothing could speak."""
        last_error = None
        for index, (provider_id, voice_id) in enumerate(job.chain):
            if job.cancelled:
                return None
            provider = _get_provider(provider_id)
            if provider is None:
                last_error = LookupError(f"voice provider '{provider_id}' is not registered")
            else:
                with self._cond:
                    self._current_provider = provider_id
                last_error = self._attempt(job, provider, voice_id)
                if last_error is None or job.cancelled:
                    _forget_failures(provider_id)
                    return None
            _log_once(("failed", provider_id, type(last_error).__name__),
                      f"Hariku Voice: {provider_id} could not speak: {last_error}")
            if index + 1 < len(job.chain):
                nxt = job.chain[index + 1][0]
                _log_once(("fallback", provider_id, nxt),
                          f"Hariku Voice: falling back from {provider_id} to {nxt}.")
        if job.cancelled:
            return None
        if job.reader_fallback:
            _log_once(("reader", job.chain[-1][0] if job.chain else ""),
                      "Hariku Voice: no voice could speak; the screen reader speaks instead.")
            import core.speech
            core.speech.speak_announced(job.text, job.interrupt, braille=False)
        return last_error

    def _attempt(self, job, provider, voice_id):
        done = threading.Event()
        outcome = []
        lock = threading.Lock()

        def on_done(error=None):
            with lock:
                if done.is_set():
                    return
                outcome.append(error)
                done.set()
            job.wake.set()

        job.wake.clear()
        watch = _KeyWatch() if job.stop_on_key else None
        try:
            provider.speak(job.text, voice_id, job.rate, job.volume, on_done)
        except Exception as e:
            return e
        deadline = time.monotonic() + _time_limit(job.text, job.rate)
        while not done.is_set():
            job.wake.wait(POLL_SECONDS)
            job.wake.clear()
            if done.is_set():
                break
            if job.cancelled:
                self._halt(provider)
                done.wait(STOP_GRACE_SECONDS)
                return None
            if watch is not None and watch.key_pressed():
                logger.info("Hariku Voice: stopped by a key press.")
                self.stop()
                self._halt(provider)
                done.wait(STOP_GRACE_SECONDS)
                return None
            if time.monotonic() > deadline:
                self._halt(provider)
                return TimeoutError("the voice did not finish in time")
        return outcome[0] if outcome else None

    @staticmethod
    def _halt(provider):
        try:
            provider.stop()
        except Exception:
            logger.exception(f"Hariku Voice: stopping '{provider.id}' failed")
        stop_playback()


_announcer = _Announcer()


def _voice_chain(settings):
    chain = []
    provider_id, voice_id = settings["provider"], settings["voice"]
    if is_provider_available(provider_id):
        chain.append((provider_id, voice_id))
    else:
        _log_once(("unavailable", provider_id),
                  f"Hariku Voice: the voice source '{provider_id}' is not available.")
    fallback = settings["fallback"]
    if fallback and (WINDOWS, fallback) not in chain and is_provider_available(WINDOWS):
        chain.append((WINDOWS, fallback))
    return chain


def _voiced(kind, config):
    """(settings, voice chain) when Hariku Voice speaks this kind now, else
    None (the kind is off, not set up yet, or no voice is available)."""
    settings = normalize_settings(config.get(SETTINGS_KEY))
    if not settings["kinds"][kind]:
        return None
    if kind in NEEDS_SETUP and not is_configured(config):
        return None
    chain = _voice_chain(settings)
    if not chain:
        _log_once(("reader", settings["provider"]),
                  "Hariku Voice: no voice is available; the screen reader speaks instead.")
        return None
    return settings, chain


def _clean_text(text):
    return text.strip() if isinstance(text, str) else str(text or "").strip()


def announce(text, kind, interrupt=True):
    """Say one of Hariku's own announcements. `kind` is "greeting",
    "briefing", "reminder" or "command". With Hariku Voice off for that kind
    this is core.speech.speak(text, interrupt). With it on, the chosen voice
    speaks and the braille display gets the text; on failure the fallback
    Windows voice, then the screen reader. `interrupt` stops a Hariku voice
    that is speaking, otherwise this one waits its turn. These are the user's
    own content, so quiet hours don't apply.

    Returns True when a Hariku voice speaks it (the screen reader is not given
    the text), False when the screen reader speaks it."""
    if kind not in KINDS:
        raise ValueError(f"unknown announcement kind: {kind!r}")
    text = _clean_text(text)
    if not text:
        return False
    import core.speech
    config = _core_config()
    voiced = _voiced(kind, config)
    if voiced is None:
        core.speech.speak(text, interrupt=interrupt)
        return False
    return _speak_voiced(text, kind, interrupt, config, *voiced)


def _speak_voiced(text, kind, interrupt, config, settings, chain):
    """on_before_speak (once, with the kind and voice), braille, then the
    voice. Returns True: the screen reader is not given the text."""
    import core.speech
    payload = {"text": text, "interrupt": interrupt, "cancel": False, "kind": kind,
               "voice": chain[0][0]}
    bus.emit("on_before_speak", payload)
    if payload.get("cancel"):
        return True
    final = payload.get("text", text)
    text = final.strip() if isinstance(final, str) and final.strip() else text
    interrupt = bool(payload.get("interrupt", interrupt))

    core.speech.braille(text, interrupt=interrupt)
    job = _Job(text, chain, settings["rate"], settings["volume"], settings["stop_on_key"],
               reader_fallback=True, interrupt=interrupt, kind=kind)
    _announcer.submit(job, interrupt and config.get("interrupt_speech", True))
    return True


# ------------------------------------------------------------
# Routing screen reader speech to Hariku Voice for a while
# ------------------------------------------------------------

class _Route:
    def __init__(self, kind, seconds):
        self.kind = kind
        self.deadline = time.monotonic() + seconds
        self.watch = _KeyWatch()


_route_lock = threading.Lock()
_route = None
_route_thread = None


def route_speech(kind, seconds=ROUTE_SECONDS):
    """From now until the next key press, or `seconds` at most (20 by
    default, 60 at most), core.speech.speak() speaks with Hariku Voice as if
    it were an announcement of `kind`, when that kind is on and a voice is
    available; otherwise the screen reader speaks as usual. Braille still gets
    every text. The command bar calls route_speech("command") right before it
    runs an action, whose answer often comes seconds later (after a
    download). A new call replaces the previous window. No keyboard hook:
    key presses are noticed with GetLastInputInfo, as for "Stop when I press
    a key", and the key that ran the command doesn't count."""
    global _route, _route_thread
    if kind not in KINDS:
        raise ValueError(f"unknown announcement kind: {kind!r}")
    try:
        seconds = max(0.0, min(float(seconds), ROUTE_MAX_SECONDS))
    except (TypeError, ValueError):
        seconds = ROUTE_SECONDS
    route = _Route(kind, seconds)
    with _route_lock:
        _route = route
        if _route_thread is None:
            _route_thread = threading.Thread(target=_watch_routes, daemon=True,
                                             name="hariku-voice-route")
            _route_thread.start()
    return True


def stop_routing():
    """End the window route_speech() opened, if any."""
    global _route
    with _route_lock:
        _route = None


def _end_route(route):
    global _route
    with _route_lock:
        if _route is route:
            _route = None


def routed_kind():
    """The kind speech is routed to Hariku Voice as right now, or None."""
    with _route_lock:
        route = _route
    if route is None:
        return None
    if time.monotonic() >= route.deadline:
        _end_route(route)
        return None
    return route.kind


def _watch_routes():
    """Ends the routing window at a key press or when its time is up."""
    global _route_thread
    while True:
        with _route_lock:
            route = _route
            if route is None:
                _route_thread = None
                return
        if time.monotonic() >= route.deadline or route.watch.key_pressed():
            _end_route(route)
        else:
            time.sleep(POLL_SECONDS)


def speak_routed(text, interrupt=False):
    """core.speech.speak() asks this first: while route_speech() is in effect
    and the voice speaks that kind, say `text` with it (on_before_speak fires
    here, with "kind" and "voice") and return True. False: the screen reader
    should speak it as usual."""
    kind = routed_kind()
    if kind is None:
        return False
    text = _clean_text(text)
    if not text:
        return False
    config = _core_config()
    voiced = _voiced(kind, config)
    if voiced is None:
        return False
    return _speak_voiced(text, kind, bool(interrupt), config, *voiced)


def preview(text, provider_id, voice_id="", rate=0, volume=100, stop_on_key=True,
            on_done=None):
    """Speak `text` with this voice now, as the Hariku Voice page's Test button
    does, interrupting any Hariku voice. Nothing falls back. on_done(error or
    None) is called once, on a worker thread. Returns False, without calling
    on_done, when the provider is unknown or unavailable."""
    if not is_provider_available(provider_id):
        return False
    text = str(text or "").strip()
    import core.speech
    core.speech.braille(text, interrupt=True)
    job = _Job(text, [(provider_id, voice_id or "")],
               _int_in(rate, RATE_MIN, RATE_MAX, 0),
               _int_in(volume, VOLUME_MIN, VOLUME_MAX, 100),
               bool(stop_on_key), reader_fallback=False, on_done=on_done)
    _announcer.submit(job, True)
    return True


def stop():
    """Stop the Hariku voice now and drop what was waiting (the "Stop Hariku
    voice" action). The screen reader is not affected."""
    _announcer.stop()


def is_speaking():
    """Whether a Hariku voice is speaking or has announcements waiting."""
    return _announcer.busy()


# ------------------------------------------------------------
# The shared audio file player (MCI, not winsound)
# ------------------------------------------------------------
# core/sounds.py plays UI sounds through MCI "waveaudio" devices named after
# the file. Voice audio uses its own "mpegvideo" device (MP3 and WAV, with a
# volume setting) under a unique alias, so a UI sound never cuts a voice off
# and neither closes the other. winsound.PlaySound has a single slot and would.

class MciError(OSError):
    pass


_winmm_dll = None


def _winmm():
    global _winmm_dll
    if _winmm_dll is None:
        dll = ctypes.WinDLL("winmm")   # our own instance: sounds.py's calls stay as they are
        dll.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
                                       ctypes.c_void_p]
        dll.mciSendStringW.restype = ctypes.c_uint
        dll.mciGetErrorStringW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
        dll.mciGetErrorStringW.restype = ctypes.wintypes.BOOL
        _winmm_dll = dll
    return _winmm_dll


def _mci_send(command):
    """Send an MCI command string; its reply, or MciError."""
    winmm = _winmm()
    reply = ctypes.create_unicode_buffer(256)
    code = winmm.mciSendStringW(command, reply, 255, None)
    if code:
        message = ctypes.create_unicode_buffer(256)
        winmm.mciGetErrorStringW(code, message, 255)
        raise MciError(code, message.value or f"MCI error {code}")
    return reply.value


def _as_int(text):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return 0


class _Playback:
    _serial = itertools.count(1)

    def __init__(self, path, volume, on_done):
        self.path = path
        self.volume = volume
        self.alias = f"hariku_voice_{next(self._serial)}"
        self._on_done = on_done
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="hariku-voice-player")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        # Every MCI command for this alias comes from this thread, which ends
        # with the playback (taking any window MCI made for it along).
        error = None
        opened = False
        try:
            if not os.path.isfile(self.path):
                raise FileNotFoundError(self.path)
            _mci_send(f'open "{self.path}" type mpegvideo alias {self.alias}')
            opened = True
            _mci_send(f"set {self.alias} time format milliseconds")
            length = _as_int(_mci_send(f"status {self.alias} length"))
            try:
                _mci_send(f"setaudio {self.alias} volume to {self.volume * 10}")
            except MciError as e:
                logger.debug(f"Hariku Voice: could not set the playback volume: {e}")
            if self._stop.is_set():
                return
            _mci_send(f"play {self.alias}")
            started = time.monotonic()
            limit = (length / 1000.0 + 10.0) if length > 0 else 600.0
            seen_playing = False
            while not self._stop.wait(PLAYER_POLL_SECONDS):
                _pump_messages()
                mode = _mci_send(f"status {self.alias} mode").strip().lower()
                elapsed = time.monotonic() - started
                if mode == "playing":
                    seen_playing = True
                    if length > 0 and _as_int(_mci_send(f"status {self.alias} position")) >= length:
                        break
                # Before "play" takes effect the device still says "stopped".
                elif mode != "seeking" and (seen_playing or elapsed > 3.0):
                    break
                if elapsed > limit:
                    raise TimeoutError("playback did not finish in time")
        except Exception as e:
            error = e
        finally:
            if opened:
                for command in (f"stop {self.alias}", f"close {self.alias}"):
                    try:
                        _mci_send(command)
                    except Exception:
                        pass
            _playback_finished(self)
            if self._on_done is not None:
                try:
                    self._on_done(error)
                except Exception:
                    logger.exception("Hariku Voice: a playback on_done callback failed")


_playback_lock = threading.Lock()
_current_playback = None


def _playback_finished(playback):
    global _current_playback
    with _playback_lock:
        if _current_playback is playback:
            _current_playback = None


def play_file(path, volume=100, on_done=None):
    """Play an MP3 or WAV file for a provider, without blocking, at `volume`
    (0-100, on top of Hariku's own volume). One file plays at a time: a new one
    stops the previous. on_done(None) when it ends or is stopped, on_done(error)
    when it can't be played; exactly once, on the player's thread."""
    global _current_playback
    playback = _Playback(os.path.abspath(str(path)), _int_in(volume, VOLUME_MIN, VOLUME_MAX, 100),
                         on_done)
    with _playback_lock:
        previous, _current_playback = _current_playback, playback
    if previous is not None:
        previous.stop()
    playback.start()
    return True


def stop_playback():
    """Stop the file play_file() is playing, if any."""
    global _current_playback
    with _playback_lock:
        playback, _current_playback = _current_playback, None
    if playback is not None:
        playback.stop()


# ------------------------------------------------------------
# The built-in Windows voices, and shutting down
# ------------------------------------------------------------

def shutdown(*_args):
    """Stop speaking and release the Windows voice (Hariku is closing)."""
    stop()
    stop_playback()
    try:
        from core import voice_sapi
        voice_sapi.shutdown()
    except Exception:
        logger.exception("Hariku Voice: shutting down the Windows voice failed")


def _register_builtin():
    from core import voice_sapi
    register_provider(WINDOWS, lambda: _("voice_provider_windows"), voice_sapi.list_voices,
                      voice_sapi.speak, voice_sapi.stop, voice_sapi.is_available,
                      privacy_note=lambda: _("voice_windows_privacy"))


_register_builtin()
bus.subscribe("on_unload", shutdown)
