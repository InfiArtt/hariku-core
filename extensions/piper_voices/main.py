# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Piper Voices — Hariku V2 extension.

Adds Piper (https://github.com/rhasspy/piper, MIT) as a Hariku Voice source,
"piper": neural voices that speak on this computer, without the internet.
Nothing is downloaded until the user asks: in Preferences, Piper Voices, they
pick a voice, see its size, quality and license, and download it; the Piper
program comes along with the first voice.

  piper_voices_catalogue.py - the voice index and model cards (no network)
  piper_voices_store.py     - where everything lives on disk
  piper_voices_download.py  - checked, resumable downloads from GitHub and
                              Hugging Face only
  piper_voices_synth.py     - running piper.exe (no window) and the WAV cache
  piper_voices_text.py      - text in the user's language
  piper_voices_ui.py        - the Preferences page and the download dialog

Speaking runs on one worker thread, one piper.exe at a time; downloads on
another. The UI gets results through wx.CallAfter.
"""

import collections
import logging
import threading

import wx

import core.preferences
import core.voice
from core.speech import speak as _speak_text

import piper_voices_catalogue as catalogue
import piper_voices_download as download
import piper_voices_store as store
import piper_voices_synth as synth
import piper_voices_ui
from piper_voices_text import _
import piper_voices_text as text

logger = logging.getLogger(__name__)

EXT_NAME = "Piper Voices"   # fixed, whatever the language
PROVIDER_ID = "piper"
CATALOGUE_MAX_AGE = 7 * 24 * 3600
CACHE_LIMIT_BYTES = 30 * 1024 * 1024
IDLE_EXIT_SECONDS = 60.0
MILESTONES = (25, 50, 75, 100)

_panel = None


def _call_after(fn, *args):
    """wx.CallAfter from a worker thread, unless Hariku is already closing."""
    try:
        if wx.GetApp() is not None:
            wx.CallAfter(fn, *args)
    except Exception:
        pass


def _say(message, interrupt=False):
    try:
        _speak_text(message, interrupt=interrupt)
    except Exception:
        logger.exception(f"[{EXT_NAME}] Speaking a message failed")


# ------------------------------------------------------------
# What is installed (kept in memory: is_available() must not touch the disk)
# ------------------------------------------------------------

_state_lock = threading.Lock()
_available = False


def refresh_state():
    """Look at the disk again; returns the installed voices."""
    global _available
    root = store.root_dir()
    voices = store.installed_voices(root)
    available = bool(voices) and store.runtime_installed(root)
    with _state_lock:
        _available = available
    return voices


def is_available():
    """True when the Piper program and at least one voice are installed."""
    return _available


def list_voices():
    """The installed voices, for Hariku Voice."""
    return [{"id": v["key"], "name": text.voice_name(v), "language": v["language"],
             "quality": v["quality"]}
            for v in catalogue.order_voices(refresh_state(), core.voice.user_languages())]


def default_voice(voices, languages=None):
    """An installed voice for the user's language (Hariku's, then Windows'),
    else the first one; None when there is none."""
    languages = core.voice.user_languages() if languages is None else languages
    ordered = catalogue.order_voices(voices, languages)
    return ordered[0]["key"] if ordered else None


# ------------------------------------------------------------
# Speaking: one worker thread, one piper.exe at a time
# ------------------------------------------------------------

class _Job:
    def __init__(self, text_, voice_id, rate, volume, on_done):
        self.text = text_
        self.voice_id = voice_id
        self.rate = rate
        self.volume = volume
        self.cancelled = False
        self._on_done = on_done
        self._finished = False
        self._lock = threading.Lock()
        self._process = None
        self._playing = False

    def attach(self, process):
        with self._lock:
            self._process = process
            abort = self.cancelled
        if abort:
            synth.kill(process)

    def detach(self):
        with self._lock:
            self._process = None

    def start_playing(self):
        """Mark the job as playing; False when it was cancelled meanwhile."""
        with self._lock:
            if self.cancelled:
                return False
            self._playing = True
            return True

    def cancel(self):
        with self._lock:
            self.cancelled = True
            process, playing = self._process, self._playing and not self._finished
        if process is not None:
            synth.kill(process)       # communicate() returns; the job finishes
        if playing:
            core.voice.stop_playback()   # its on_done finishes the job

    def finish(self, error=None):
        with self._lock:
            if self._finished:
                return
            self._finished = True
            self._playing = False
        try:
            self._on_done(error)
        except Exception:
            logger.exception(f"[{EXT_NAME}] on_done failed")


class _Worker:
    def __init__(self):
        self._cond = threading.Condition()
        self._queue = collections.deque()
        self._current = None
        self._playing = None      # its file may still play after the worker moved on
        self._thread = None

    def submit(self, job):
        with self._cond:
            self._queue.append(job)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True,
                                                name="hariku-piper-voices")
                self._thread.start()
            self._cond.notify_all()

    def playing(self, job):
        with self._cond:
            self._playing = job

    def cancel_all(self):
        with self._cond:
            dropped = list(self._queue)
            self._queue.clear()
            current, playing = self._current, self._playing
            self._playing = None
        for job in dropped:
            job.cancel()
            job.finish(None)
        if current is not None:
            current.cancel()
        if playing is not None and playing is not current:
            playing.cancel()          # stops its file; a finished job is left alone

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


def _choose_voice(root, voice_id):
    voices = store.installed_voices(root)
    if voice_id:
        if any(v["key"] == voice_id for v in voices):
            return voice_id
        raise LookupError(_("err_voice_missing", voice=voice_id))
    chosen = default_voice(voices)
    if chosen is None:
        raise LookupError(_("err_no_voice"))
    return chosen


def _process(job):
    if job.cancelled:
        job.finish(None)
        return
    root = store.root_dir()
    try:
        if not store.runtime_installed(root):
            raise FileNotFoundError(_("err_no_runtime"))
        voice = _choose_voice(root, job.voice_id)
    except Exception as e:
        job.finish(e)
        return
    cache = synth.AudioCache(core.voice.cache_dir(PROVIDER_ID), CACHE_LIMIT_BYTES)
    key = cache.key(voice, synth.length_scale_text(job.rate), job.text)
    path = cache.get(key)
    if path is None:
        temporary = cache.temporary_path(key)
        try:
            synth.synthesize(store.exe_path(root), store.model_path(root, voice), temporary,
                             job.text, job.rate, on_process=job.attach)
            path = cache.put_file(key, temporary)
        except Exception as e:
            synth.remove_quietly(temporary)
            if job.cancelled:
                job.finish(None)
            else:
                logger.info(f"[{EXT_NAME}] Piper could not speak: {e}")
                job.finish(e)
            return
        finally:
            job.detach()
    _worker.playing(job)
    if not job.start_playing():
        job.finish(None)
        return
    core.voice.play_file(path, job.volume, job.finish)
    if job.cancelled:
        core.voice.stop_playback()   # stop() came just before the file started


def speak(text_, voice_id, rate, volume, on_done):
    _worker.submit(_Job(text_, voice_id, rate, volume, on_done))


def stop():
    _worker.cancel_all()


# ------------------------------------------------------------
# Downloads: one at a time, on a worker thread
# ------------------------------------------------------------

class Download:
    """A voice being downloaded, with the Piper program first if needed."""

    def __init__(self, voice, card_text, need_runtime):
        self.voice = voice
        self.card_text = card_text
        self.need_runtime = need_runtime
        self.total = voice["size"] + (download.RUNTIME_SIZE if need_runtime else 0)
        self.percent = 0
        self.spoken = 0
        self.reported = -1
        self.cancel_event = threading.Event()

    @property
    def key(self):
        return self.voice["key"]

    @property
    def title(self):
        return text.voice_title(self.voice)


class _Downloads:
    def __init__(self):
        self._lock = threading.Lock()
        self._current = None
        self._listeners = []

    def current(self):
        with self._lock:
            return self._current

    def add_listener(self, listener):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener):
        if listener in self._listeners:
            self._listeners.remove(listener)

    def start(self, voice, card_text):
        """Start downloading `voice` (and the Piper program when it isn't
        installed). False when another download is running."""
        with self._lock:
            if self._current is not None:
                return False
            job = Download(voice, card_text, not store.runtime_installed(store.root_dir()))
            self._current = job
        _say(_("download_started", name=job.title, size=text.size_label(job.total)))
        threading.Thread(target=self._run, args=(job,), daemon=True,
                         name="hariku-piper-download").start()
        return True

    def cancel(self):
        job = self.current()
        if job is None:
            return False
        job.cancel_event.set()
        return True

    # --- worker thread ---------------------------------------------------------

    def _run(self, job):
        root = store.root_dir()
        error = None
        try:
            store.cleanup_partials(root)
            done_before = 0
            if job.need_runtime:
                download.install_runtime(root, progress=lambda n: self._progress(job, n),
                                         cancelled=job.cancel_event.is_set)
                done_before = download.RUNTIME_SIZE
            download.install_voice(job.voice, root, job.card_text,
                                   progress=lambda n: self._progress(job, done_before + n),
                                   cancelled=job.cancel_event.is_set)
        except download.Cancelled as e:
            error = e
        except download.DownloadError as e:
            error = download.Cancelled() if job.cancel_event.is_set() else e
            logger.info(f"[{EXT_NAME}] Downloading {job.key} failed: {e}")
        except Exception as e:
            error = e
            logger.exception(f"[{EXT_NAME}] Downloading {job.key} failed")
        try:
            refresh_state()
        except Exception:
            logger.exception(f"[{EXT_NAME}] Reading the installed voices failed")
        _call_after(self._finished, job, error)

    def _progress(self, job, done):
        percent = max(0, min(100, int(done * 100 / job.total))) if job.total else 100
        if percent != job.reported:
            job.reported = percent
            _call_after(self._on_progress, job, percent)

    # --- UI thread ---------------------------------------------------------------

    def _on_progress(self, job, percent):
        if job.cancel_event.is_set() or self.current() is not job:
            return
        job.percent = percent
        reached = [m for m in MILESTONES if job.spoken < m <= percent]
        if reached:
            job.spoken = reached[-1]
            _say(_("progress_spoken", percent=reached[-1]))
        self._notify("progress", job, percent)

    def _finished(self, job, error):
        with self._lock:
            if self._current is job:
                self._current = None
        if error is None:
            _say(_("download_done", name=job.title))
        elif isinstance(error, download.Cancelled):
            _say(_("download_cancelled"))
        else:
            _say(_("download_failed", error=text.error_text(error)))
        self._notify("finished", job, error)

    def _notify(self, event, job, value):
        for listener in list(self._listeners):
            try:
                listener(event, job, value)
            except Exception:
                logger.exception(f"[{EXT_NAME}] A download listener failed")


_downloads = _Downloads()


# ------------------------------------------------------------
# What the Preferences page uses
# ------------------------------------------------------------

_cards = {}          # voice key -> model card text fetched this session
_cards_lock = threading.Lock()


def _in_thread(work, done, name):
    """Run work() on a worker thread; done(result, error) on the UI thread."""
    def runner():
        result, error = None, None
        try:
            result = work()
        except Exception as e:
            error = e
            if not isinstance(e, (download.DownloadError, catalogue.CatalogueError, OSError)):
                logger.exception(f"[{EXT_NAME}] {name} failed")
        _call_after(done, result, error)

    threading.Thread(target=runner, daemon=True, name=f"hariku-piper-{name}").start()


class Controller:
    """The page's way to everything slow; results come back on the UI thread."""

    downloads = _downloads

    @staticmethod
    def runtime_installed():
        return store.runtime_installed(store.root_dir())

    @staticmethod
    def runtime_size():
        return download.RUNTIME_SIZE

    @staticmethod
    def installed():
        """{key: installed voice} (a quick look at the disk)."""
        return {v["key"]: v for v in store.installed_voices(store.root_dir())}

    @staticmethod
    def load_catalogue(force, done):
        """done((voices, stale error or None), error): the index from disk while
        it is under 7 days old (unless `force`), else from Hugging Face; an
        older saved one when that fails."""
        def work():
            root = store.root_dir()
            index = None if force else store.load_catalogue(root, max_age=CATALOGUE_MAX_AGE)
            if index is not None:
                return catalogue.parse_catalogue(index), None
            try:
                index = download.fetch_catalogue()
                voices = catalogue.parse_catalogue(index)
            except Exception as e:
                saved = store.load_catalogue(root)
                if saved is None:
                    raise
                logger.info(f"[{EXT_NAME}] Using the saved voice list: {e}")
                return catalogue.parse_catalogue(saved), e
            try:
                store.save_catalogue(root, index)
            except OSError as e:
                logger.info(f"[{EXT_NAME}] Could not save the voice list: {e}")
            return voices, None

        _in_thread(work, done, "catalogue")

    @staticmethod
    def fetch_card(voice, done):
        """done(card text, error), from this session's copy when there is one."""
        def work():
            with _cards_lock:
                cached = _cards.get(voice["key"])
            if cached is not None:
                return cached
            card = download.fetch_model_card(voice)
            with _cards_lock:
                _cards[voice["key"]] = card
            return card

        _in_thread(work, done, "card")

    @staticmethod
    def remove_voice(key):
        try:
            return store.remove_voice(store.root_dir(), key)
        finally:
            refresh_state()


controller = Controller()


def _create_panel(parent):
    global _panel
    _panel = piper_voices_ui.PiperVoicesPanel(parent, controller)
    return _panel


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register(bus):
    global _panel
    _panel = None
    try:
        refresh_state()
    except Exception:
        logger.exception(f"[{EXT_NAME}] Reading the installed voices failed")
    core.voice.register_provider(PROVIDER_ID, lambda: _("provider_name"), list_voices, speak,
                                 stop, is_available, privacy_note=lambda: _("privacy_note"))
    # Nothing to apply on OK: the page's buttons act at once.
    core.preferences.register_panel(_("ext_name"), "", _create_panel, None)
    logger.info(f"[{EXT_NAME}] Extension loaded.")


def teardown():
    global _panel
    _panel = None
    core.voice.unregister_provider(PROVIDER_ID)
    _worker.cancel_all()
    _downloads.cancel()
    logger.info(f"[{EXT_NAME}] Extension unloaded.")
