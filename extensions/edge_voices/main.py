# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Edge Voices — Hariku V2 extension.

Adds the Microsoft Edge "Read Aloud" online neural voices (including the
Indonesian Ardi and Gadis) as a Hariku Voice source, "edge". Choose it in
Preferences, Hariku Voice.

  edge_voices_protocol.py - the service's message formats (no network)
  edge_voices_ws.py       - a small WebSocket client on socket and ssl
  edge_voices_service.py  - synthesizing and fetching the voice list
  edge_voices_cache.py    - saved audio (30 MB, least recently used first) and
                            the voice list (7 days)

The service is meant for the Edge browser and may stop working at any time.
Then this source reports errors, Hariku falls back to the user's fallback
voice, and after 3 failures in a row this source says it is unavailable for
10 minutes, so announcements don't wait for it. Everything network-related
runs on one worker thread, one synthesis at a time.
"""

import collections
import logging
import os
import threading
import time

import core.voice
from core.i18n import get_current_language, get_translator

import edge_voices_cache
import edge_voices_protocol
import edge_voices_service

logger = logging.getLogger(__name__)

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("edge_voices", os.path.join(EXT_DIR, "locales"))

EXT_NAME = "Edge Voices"   # fixed, whatever the language
PROVIDER_ID = "edge"
DEFAULT_VOICES = {"id": "id-ID-GadisNeural"}
FALLBACK_DEFAULT_VOICE = "en-US-EmmaMultilingualNeural"

FAILURES_BEFORE_PAUSE = 3
PAUSE_SECONDS = 10 * 60
VOICE_LIST_MAX_AGE = 7 * 24 * 3600
CACHE_LIMIT_BYTES = 30 * 1024 * 1024
IDLE_EXIT_SECONDS = 60.0


class Unavailable(Exception):
    """The service failed several times in a row; it is not tried for a while."""


# ------------------------------------------------------------
# Failure back-off
# ------------------------------------------------------------

_state_lock = threading.Lock()
_failures = 0
_paused_until = 0.0


def _record_failure(error):
    global _failures, _paused_until
    with _state_lock:
        _failures += 1
        pause = _failures >= FAILURES_BEFORE_PAUSE
        if pause:
            _failures = 0
            _paused_until = time.monotonic() + PAUSE_SECONDS
    if pause:
        logger.warning(f"[{EXT_NAME}] {FAILURES_BEFORE_PAUSE} failures in a row "
                       f"(last: {error}); not used for {PAUSE_SECONDS // 60} minutes.")
    else:
        logger.info(f"[{EXT_NAME}] The speech service failed: {error}")


def _record_success():
    global _failures, _paused_until
    with _state_lock:
        _failures = 0
        _paused_until = 0.0


def is_available():
    return time.monotonic() >= _paused_until


def _reset_state():
    global _failures, _paused_until
    with _state_lock:
        _failures = 0
        _paused_until = 0.0


# ------------------------------------------------------------
# Voices
# ------------------------------------------------------------

def _cache_dir():
    return core.voice.cache_dir(PROVIDER_ID)


def default_voice():
    """A voice for Hariku's language when the user picked none."""
    language = (get_current_language() or "").split("-")[0].lower()
    return DEFAULT_VOICES.get(language, FALLBACK_DEFAULT_VOICE)


def _shown(voice):
    # The plain name ("Gadis"): Preferences groups the voices by language and
    # gender itself.
    return {"id": voice["id"], "name": voice["name"], "language": voice.get("language", ""),
            "gender": voice.get("gender", "")}


def list_voices():
    """The service's voices; from the saved list while it is under 7 days old,
    and from an older one when the service can't be reached."""
    directory = _cache_dir()
    voices = edge_voices_cache.load_voice_list(directory, max_age=VOICE_LIST_MAX_AGE)
    if voices is None:
        try:
            if not is_available():
                raise Unavailable(_("err_paused"))
            voices = edge_voices_service.fetch_voice_list()
        except Exception as e:
            if not isinstance(e, Unavailable):
                _record_failure(e)
            voices = edge_voices_cache.load_voice_list(directory)
            if voices is None:
                raise
            logger.info(f"[{EXT_NAME}] Using the saved voice list: {e}")
        else:
            _record_success()
            edge_voices_cache.save_voice_list(directory, voices)
    return [_shown(v) for v in voices]


# ------------------------------------------------------------
# Speaking: one worker thread, one synthesis at a time
# ------------------------------------------------------------

class _Job:
    def __init__(self, text, voice_id, rate, volume, on_done):
        self.text = text
        self.voice_id = voice_id
        self.rate = rate
        self.volume = volume
        self.cancelled = False
        self._on_done = on_done
        self._finished = False
        self._lock = threading.Lock()
        self._connection = None

    def attach(self, connection):
        with self._lock:
            self._connection = connection
            abort = self.cancelled
        if abort:
            connection.abort()

    def cancel(self):
        with self._lock:
            self.cancelled = True
            connection = self._connection
        if connection is not None:
            connection.abort()      # a recv() waiting on the network returns now

    def finish(self, error=None):
        with self._lock:
            if self._finished:
                return
            self._finished = True
        try:
            self._on_done(error)
        except Exception:
            logger.exception(f"[{EXT_NAME}] on_done failed")


class _Worker:
    def __init__(self):
        self._cond = threading.Condition()
        self._queue = collections.deque()
        self._current = None
        self._thread = None

    def submit(self, job):
        with self._cond:
            self._queue.append(job)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True,
                                                name="hariku-edge-voices")
                self._thread.start()
            self._cond.notify_all()

    def cancel_all(self):
        with self._cond:
            dropped = list(self._queue)
            self._queue.clear()
            current = self._current
        for job in dropped:
            job.cancel()
            job.finish(None)
        if current is not None:
            current.cancel()

    def _run(self):
        while True:
            with self._cond:
                if not self._queue:
                    self._cond.wait(IDLE_EXIT_SECONDS)
                if not self._queue:
                    self._thread = None
                    return
                job = self._current = self._queue.popleft()
            try:
                _process(job)
            except Exception as e:
                logger.exception(f"[{EXT_NAME}] Speaking failed")
                job.finish(e)
            finally:
                with self._cond:
                    self._current = None


_worker = _Worker()


def _process(job):
    if job.cancelled:
        job.finish(None)
        return
    voice = job.voice_id or default_voice()
    rate = edge_voices_protocol.rate_percent(job.rate)
    cache = edge_voices_cache.AudioCache(_cache_dir(), CACHE_LIMIT_BYTES)
    key = cache.key(voice, rate, job.text)
    path = cache.get(key)
    if path is None:
        if not is_available():
            job.finish(Unavailable(_("err_paused")))
            return
        try:
            # The volume is applied when playing, so saved audio fits any volume.
            audio = edge_voices_service.synthesize(job.text, voice, rate,
                                                   cancelled=lambda: job.cancelled,
                                                   on_connection=job.attach)
        except edge_voices_service.Cancelled:
            job.finish(None)
            return
        except Exception as e:
            if job.cancelled:
                job.finish(None)
                return
            _record_failure(e)
            job.finish(e)
            return
        _record_success()
        path = cache.put(key, audio)
    if job.cancelled:
        job.finish(None)
        return
    core.voice.play_file(path, job.volume, job.finish)


def speak(text, voice_id, rate, volume, on_done):
    _worker.submit(_Job(text, voice_id, rate, volume, on_done))


def stop():
    _worker.cancel_all()


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register(bus):
    core.voice.register_provider(PROVIDER_ID, _("provider_name"), list_voices, speak, stop,
                                 is_available, privacy_note=_("privacy_note"))
    logger.info(f"[{EXT_NAME}] Extension loaded.")


def teardown():
    core.voice.unregister_provider(PROVIDER_ID)
    _worker.cancel_all()
    logger.info(f"[{EXT_NAME}] Extension unloaded.")
