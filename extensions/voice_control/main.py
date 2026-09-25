# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Voice Control — Hariku V2 extension (needs core 2.7).

Speak commands into Hariku's command bar (Ctrl+Alt+Backspace): "gempa terbaru",
"jam berapa", "ingatkan aku minum obat besok jam 8". Speech is recognised on
this computer by whisper.cpp (MIT) with OpenAI's Whisper models (MIT); the
program and the models are downloaded only when the user presses Download in
Preferences, Voice Control.

  voice_control_audio.py     the microphone (winmm waveIn), voice activity, WAV
  voice_control_download.py  pinned, checked downloads from GitHub and Hugging Face
  voice_control_store.py     files and settings
  voice_control_engine.py    whisper-server: start, recognise, stop when idle
  voice_control_wake.py      the wake phrase: the phrase, and the listener thread
  voice_control_kws.py       sherpa-onnx's keyword spotter (its C API, ctypes)
  voice_control_bpe.py       a phrase as the keyword model's tokens
  voice_control_text.py      text in the user's language
  voice_control_ui.py        the Preferences page

The wake phrase (1.1, off until the user turns it on): "Hey Aruna", or any
phrase the user types, opens Aruna listening, as the hotkey does. sherpa-onnx
(Apache-2.0) spots it on this computer with an English keyword model; both
are downloaded only when the user asks. See voice_control_wake.py for when it
listens and when it doesn't.

How a command is heard: the screen reader and Hariku Voice are silenced (with
speakers they would talk into the microphone), the start tone plays, and the
recording begins about 150 ms after it ends. Speech starts once the voice is
loud enough for the microphone sensitivity (Preferences; the microphone test
measures the voice and the room and suggests one). It ends after about a
second of silence once speech started (Preferences: the silence length), after
12 seconds, when the hotkey or Enter is pressed again, or after 5 seconds with
no speech (then Hariku says so). High sounds (birdsong) never count as speech,
and once the voice is heard, sounds 12 dB below it count as silence. Twelve
seconds without a single pause: the part up to the voice's last loud moment is
recognised, and only when nothing comes of it does Hariku say it was too
noisy. The end tone plays, whisper-server recognises
the recording (in memory, over 127.0.0.1), and the text goes to the command
bar. With the model set to Automatic, words that look like a reminder are
recognised again with a more accurate model, when one is installed. The
recording is then dropped: it is never saved or sent anywhere.

The command bar gets this recogniser through core.commands.register_listener.
"""
import logging
import threading
import time
import wave

import wx

import core.api
import core.commands
import core.hotkeys
import core.personal
import core.preferences
import core.sounds
import core.speech
import core.voice
from core.i18n import get_current_language

import voice_control_audio as audio
import voice_control_bpe as bpe
import voice_control_download as download
import voice_control_engine as engine
import voice_control_kws as kws
import voice_control_store as store
import voice_control_text as text
import voice_control_ui
import voice_control_wake as wake
from voice_control_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Voice Control"      # fixed, whatever the language
TONE_GAP_SECONDS = 0.15         # start recording this long after the tone ends
DEFAULT_TONE_SECONDS = 0.25
MAX_TONE_SECONDS = 1.5
START_TIMEOUT_MS = 5000         # no speech this long: stop and say so
MAX_RECORD_MS = 12000
MIC_TEST_SECONDS = 5.0          # time for a sentence, with quiet before and after it
WAKE_TEST_SECONDS = wake.TEST_SECONDS
WAKE_ACTION = "toggle_wake"     # "Voice Control.toggle_wake"
MILESTONES = (25, 50, 75, 100)

_panel = None
_bus = None


def _call_after(fn, *args):
    """wx.CallAfter from a worker thread, unless Hariku is already closing."""
    try:
        if wx.GetApp() is not None:
            wx.CallAfter(fn, *args)
    except Exception:
        pass


def _say(message, interrupt=True):
    try:
        core.speech.speak(message, interrupt=interrupt)
    except Exception:
        logger.exception(f"[{EXT_NAME}] Speaking a message failed")


# ------------------------------------------------------------
# What is installed, and the settings (kept in memory: is_available() and
# listen_on_open() are asked on the UI thread and must be quick)
# ------------------------------------------------------------

_state_lock = threading.Lock()
_available = False
_wake_available = False
_settings = dict(store.DEFAULT_SETTINGS)


def refresh_state():
    """Look at the disk again; returns the installed models."""
    global _available, _wake_available
    root = store.root_dir()
    models = store.installed_models(root)
    wake_ready = download.wake_installed(root)
    with _state_lock:
        _available = bool(models) and store.runtime_installed(root)
        _wake_available = wake_ready
    return models


def is_available():
    """The program and at least one model are installed."""
    return _available


def wake_available():
    """The wake phrase listener is installed."""
    return _wake_available


def get_settings():
    with _state_lock:
        return dict(_settings, speeds=dict(_settings["speeds"]))


def reload_settings():
    global _settings
    settings = store.load_settings()
    with _state_lock:
        _settings = settings
    _configure_wake(settings)
    return settings


def save_settings(model, listen_on_open, silence_ms, sensitivity=None, wake_settings=None):
    """Save the page's settings (the sensitivity and the wake phrase stay as
    they are when None). `wake_settings`: {"enabled", "phrase",
    "sensitivity", "quiet_hours"}."""
    settings = get_settings()
    settings.update(model=model, listen_on_open=bool(listen_on_open), silence_ms=silence_ms)
    if sensitivity is not None:
        settings["sensitivity"] = sensitivity
    if wake_settings is not None:
        settings.update(wake=bool(wake_settings.get("enabled")),
                        wake_phrase=wake_settings.get("phrase") or wake.DEFAULT_PHRASE,
                        wake_sensitivity=wake_settings.get("sensitivity"),
                        wake_quiet_hours=bool(wake_settings.get("quiet_hours")))
    store.save_settings(settings)
    reload_settings()


def listen_on_open():
    return get_settings()["listen_on_open"]


def _record_speed(model, seconds):
    try:
        store.record_speed(model, seconds)
        reload_settings()
    except Exception:
        logger.exception(f"[{EXT_NAME}] Keeping the measured speed failed")


# ------------------------------------------------------------
# whisper-server
# ------------------------------------------------------------

def language():
    return engine.whisper_language(get_current_language())


def prompt():
    """The vocabulary prompt: the words the command bar expects."""
    try:
        phrases = core.commands.vocabulary()
    except Exception:
        logger.exception(f"[{EXT_NAME}] Reading the commands failed")
        phrases = []
    return engine.build_prompt(text.prompt_words() + phrases)


def _make_server(model):
    root = store.root_dir()
    return engine.Server(model, store.server_exe(root), store.model_path(root, model),
                         language=language(), prompt=prompt(), log_path=store.log_path(root))


_engine = engine.Engine(_make_server)


# ------------------------------------------------------------
# Sounds and silence
# ------------------------------------------------------------

def tone_seconds(sound_name):
    """How long a (theme's) sound plays, to start recording after it."""
    try:
        with wave.open(core.sounds.sound_path(sound_name), "rb") as w:
            seconds = w.getnframes() / float(w.getframerate())
        return max(0.0, min(MAX_TONE_SECONDS, seconds))
    except Exception:
        return DEFAULT_TONE_SECONDS


def play_tone(sound_name):
    """Play a (theme's) sound on the UI thread, where Hariku's other sounds
    play, so their MCI devices never meet on two threads."""
    if threading.current_thread() is threading.main_thread():
        core.sounds.play_internal_sound(sound_name)
    else:
        _call_after(core.sounds.play_internal_sound, sound_name)


def quiet():
    """Silence the screen reader and Hariku Voice (they would talk into the
    microphone through speakers)."""
    silence = getattr(core.speech, "silence", None)
    if silence is not None:
        try:
            silence()
        except Exception:
            logger.debug("Silencing the screen reader failed", exc_info=True)
    try:
        core.voice.stop()
    except Exception:
        logger.debug("Stopping Hariku Voice failed", exc_info=True)


# ------------------------------------------------------------
# Listening: one session at a time, on a worker thread
# ------------------------------------------------------------

class Session:
    def __init__(self, listener, on_event):
        self.listener = listener
        self.on_event = on_event
        self.stop_event = threading.Event()
        self.discard = False
        self.alive = True

    def stop(self, discard=False):
        if discard:
            self.discard = True
        self.stop_event.set()

    def send(self, kind, value=None):
        if self.discard and kind != "stopped":
            return
        try:
            self.on_event(kind, value)
        except Exception:
            logger.exception(f"[{EXT_NAME}] The command bar's callback failed")

    def run(self):
        try:
            self._listen()
        except audio.MicrophoneError as e:
            logger.info(f"[{EXT_NAME}] Microphone: {e}")
            self.send("error", text.mic_error(e.kind))
        except engine.EngineError as e:
            logger.warning(f"[{EXT_NAME}] Recognition failed: {e}")
            self.send("error", text.engine_error(e))
        except Exception:
            logger.exception(f"[{EXT_NAME}] Listening failed")
            self.send("error", _("err_unexpected"))
        finally:
            self.alive = False
            self.listener._finished(self)

    def _listen(self):
        listener = self.listener
        blocked = listener.blocked()
        if blocked:
            raise audio.MicrophoneError(blocked)
        settings = get_settings()
        installed = store.installed_models(store.root_dir())
        model = engine.choose_model(settings["model"], installed, settings["speeds"], "command")
        if model is None:
            raise engine.EngineError("missing", "no model")
        # The model loads while the user speaks.
        threading.Thread(target=listener.engine.warm_up, args=(model,), daemon=True,
                         name="hariku-voice-control-warm-up").start()

        listener.quiet()
        listener.play(core.commands.LISTEN_SOUND)
        listener.sleep(listener.tone_seconds(core.commands.LISTEN_SOUND) + TONE_GAP_SECONDS)
        if self.stop_event.is_set():
            self.send("stopped")
            return
        listener.quiet()        # the screen reader may have started talking meanwhile
        self.send("listening")
        vad = audio.VoiceActivity(silence_ms=settings["silence_ms"],
                                  start_timeout_ms=START_TIMEOUT_MS, max_ms=MAX_RECORD_MS,
                                  sensitivity=settings["sensitivity"])
        recorder = listener.make_recorder()
        try:
            pcm = recorder.record(lambda chunk: vad.feed(chunk) in vad.FINISHED,
                                  stop=self.stop_event, max_seconds=MAX_RECORD_MS / 1000.0 + 1)
        finally:
            listener.play(core.commands.LISTEN_END_SOUND)
        if self.discard:
            self.send("stopped")
            return
        if pcm and vad.peak <= 0:
            raise audio.MicrophoneError("silent")
        if not vad.heard_speech:
            self.send("error", _("err_no_speech"))
            return
        if vad.noisy:
            # Twelve seconds without a pause: the room kept it going. What the
            # voice itself said (up to its last loud frame) is still recognised.
            logger.info(f"[{EXT_NAME}] Too noisy to hear the end of speech "
                        f"(room {audio.level_db(vad.noise or 0):.0f} dB, voice "
                        f"{audio.level_db(vad.voice_level or 0):.0f} dB); recognising "
                        f"the voice's first {(vad.voice_end_ms or 0) / 1000:.1f} s.")
        self.send("recognising")
        wav = audio.wav_bytes(vad.speech_bytes(pcm, voice_only=vad.noisy))
        del pcm
        words, prompt_text = language(), prompt()
        heard, seconds = listener.engine.transcribe(model, wav, prompt=prompt_text,
                                                    language=words)
        listener.record_speed(model, seconds)
        better = engine.reminder_model(settings["model"], installed, settings["speeds"], model)
        if better and heard and not self.discard and core.commands.looks_like_reminder(heard):
            # A reminder: worth a more careful listen; the read-back confirms anyway.
            again, seconds = listener.engine.transcribe(better, wav, prompt=prompt_text,
                                                        language=words)
            listener.record_speed(better, seconds)
            if again:
                heard = again
        del wav
        if self.discard:
            self.send("stopped")
            return
        if vad.noisy and not (heard or "").strip():
            self.send("error", _("err_too_noisy", seconds=MAX_RECORD_MS // 1000))
            return
        self.send("text", heard)


class Listener:
    """The command bar's speech recogniser. Everything slow it uses can be
    replaced for tests: the recorder, the engine, the privacy check, the
    sounds and the waiting."""

    def __init__(self, make_recorder=None, engine_=None, blocked=None, play=None, sleep=None,
                 quiet_=None, tones=None, record_speed=None, available=None):
        self.make_recorder = make_recorder or audio.Recorder
        self.engine = engine_ or _engine
        self.blocked = blocked or audio.microphone_blocked
        self.play = play or play_tone
        self.sleep = sleep or time.sleep
        self.quiet = quiet_ or quiet
        self.tone_seconds = tones or tone_seconds
        self.record_speed = record_speed or _record_speed
        self._available = available or is_available
        self._lock = threading.Lock()
        self._session = None

    def is_available(self):
        return bool(self._available())

    def listen_on_open(self):
        return listen_on_open()

    def busy(self):
        with self._lock:
            return self._session is not None

    def start(self, on_event):
        with self._lock:
            if self._session is not None:
                busy = True
            else:
                busy = False
                if self.is_available():
                    session = Session(self, on_event)
                    self._session = session
                else:
                    session = None
        if busy:
            on_event("error", _("err_busy"))
            return False
        if session is None:
            on_event("error", _("err_not_ready"))
            return False
        threading.Thread(target=session.run, daemon=True,
                         name="hariku-voice-control-listen").start()
        return True

    def stop(self, discard=False):
        with self._lock:
            session = self._session
        if session is not None:
            session.stop(discard)

    def _finished(self, session):
        with self._lock:
            if self._session is session:
                self._session = None


_listener = Listener()


# ------------------------------------------------------------
# The wake phrase: a keyword spotter listens in the background while the
# user has it on; hearing the phrase opens Aruna listening
# ------------------------------------------------------------

def _interrupt_speech():
    """Hariku's "Interrupt speech" setting: does interrupting text cut the
    screen reader off?"""
    config = core.api.load_data("Core")
    return not isinstance(config, dict) or bool(config.get("interrupt_speech", True))


# Hariku speaking (Hariku Voice, or the screen reader through Hariku) isn't heard.
_speech = wake.SpeechWatch(voice_speaking=lambda: core.voice.is_speaking(),
                           interrupts=_interrupt_speech)
_tokenizers = {}
_tokenizers_lock = threading.Lock()


def _tokenizer(path):
    with _tokenizers_lock:
        model = _tokenizers.get(path)
        if model is None:
            model = _tokenizers[path] = bpe.UnigramModel.load(path)
        return model


def make_spotter(phrase, sensitivity):
    """A keyword spotter for the phrase (on a worker thread: loading takes a
    moment). Raises kws.KwsError, ValueError (a phrase the model can't hear)
    or bpe.ModelError."""
    root = store.root_dir()
    if not download.wake_installed(root):
        raise kws.KwsError("missing", "the wake phrase listener")
    if not download.verify_wake(root):
        raise kws.KwsError("damaged", "a file doesn't match its SHA-256")
    files = store.wake_files(root)
    tokens = kws.read_tokens(files["tokens"])
    keywords = wake.keywords_text(phrase, _tokenizer(files["bpe"]), tokens, sensitivity)
    threshold, score, paths = wake.sensitivity_values(sensitivity)
    return kws.Spotter(store.wake_runtime_dir(root), files, keywords, threshold=threshold,
                       score=score, threads=1, max_active_paths=paths)


def _make_wake_recorder():
    return audio.Recorder(poll_seconds=wake.POLL_SECONDS)


def _quiet_time():
    return core.personal.is_quiet_time()


def open_aruna_listening():
    """The wake phrase was heard (UI thread): Aruna opens and listens, as the
    hotkey does with "Start listening as soon as Aruna opens"; when Aruna is
    open already, it starts listening."""
    import ui.command_bar as command_bar
    bar = command_bar.current_bar()
    if bar is None:
        command_bar.open_command_bar(listen=True)
        return
    command_bar.bring_to_front(bar)
    if not getattr(bar, "_listening", False):
        bar.start_listening()


def _on_wake_detected(name):
    logger.info(f"[{EXT_NAME}] Heard the wake phrase ({name}).")
    _call_after(_open_aruna)


def _open_aruna():
    try:
        open_aruna_listening()
    except Exception:
        logger.exception(f"[{EXT_NAME}] Opening Aruna for the wake phrase failed")


_wake_state_listeners = []


def _on_wake_state(state):
    _call_after(_notify_wake_state, state)


def _notify_wake_state(state):
    for listener in list(_wake_state_listeners):
        try:
            listener(state)
        except Exception:
            logger.exception(f"[{EXT_NAME}] A wake phrase state listener failed")


def _on_wake_problem(kind, value):
    _say(text.wake_problem(kind, value), interrupt=False)


_wake = wake.WakeListener(make_spotter, _make_wake_recorder, _on_wake_detected,
                          installed=wake_available, busy=lambda: _listener.busy(),
                          quiet_time=_quiet_time, speaking=_speech.speaking,
                          on_state=_on_wake_state, on_problem=_on_wake_problem)


def _configure_wake(settings):
    _wake.configure(wake.Config(settings["wake"], settings["wake_phrase"],
                                settings["wake_sensitivity"], settings["wake_quiet_hours"]))


def toggle_wake_pause():
    """The "Pause or resume the wake phrase" action (no key by default; also
    from Aruna by name). The pause lasts until it's resumed or Hariku
    restarts."""
    settings = get_settings()
    if not settings["wake"]:
        _say(_("wake_is_off"))
        return
    if not wake_available():
        _say(_("wake_not_installed"))
        return
    paused = not _wake.paused
    _wake.set_paused(paused)
    _say(_("wake_paused") if paused else _("wake_resumed", phrase=settings["wake_phrase"]))


def test_wake(phrase, sensitivity, on_heard, stop, listener=None, seconds=WAKE_TEST_SECONDS,
              spotter=None):
    """The page's "Test the wake phrase": listen for `phrase` with this
    sensitivity (the page's, not yet saved) for `seconds`, or until `stop`
    (an Event) is set; on_heard(count) for each detection, on this worker
    thread. Nothing is kept. Returns {"count", "seconds", "stopped"}.
    Raises audio.MicrophoneError, kws.KwsError or ValueError."""
    listener = listener or _listener
    blocked = listener.blocked()
    if blocked:
        raise audio.MicrophoneError(blocked)
    spotter = spotter or make_spotter(phrase, sensitivity)
    count = 0
    try:
        listener.quiet()
        listener.play(core.commands.LISTEN_SOUND)
        listener.sleep(listener.tone_seconds(core.commands.LISTEN_SOUND) + TONE_GAP_SECONDS)
        ear = wake.Ear(spotter, _speech.speaking)

        def on_chunk(chunk):
            nonlocal count
            if ear.hear(chunk):
                count += 1
                on_heard(count)
            return False

        if not stop.is_set():
            listener.make_recorder().record(on_chunk, stop=stop, max_seconds=seconds,
                                            keep=False)
    finally:
        listener.play(core.commands.LISTEN_END_SOUND)
        spotter.close()
    stopped = stop.is_set()
    logger.info(f"[{EXT_NAME}] Wake phrase test: heard it {count} times"
                f"{' (stopped early)' if stopped else ''}.")
    return {"count": count, "seconds": seconds, "stopped": stopped}


# ------------------------------------------------------------
# The microphone test (Preferences): a sentence at the user's normal volume,
# measured to suggest a sensitivity; nothing played back
# ------------------------------------------------------------

def test_microphone(listener=None, seconds=MIC_TEST_SECONDS):
    """Record `seconds` while the user says a sentence, and measure the room
    and the voice: {"level": the loudest dB, "speech": bool, "seconds": s,
    "room": RMS, "voice": RMS or None, "calibration": audio.Calibration}. The
    recording is dropped; nothing is played back or saved (the page applies
    the suggested sensitivity; OK or Apply saves it). Raises
    audio.MicrophoneError."""
    listener = listener or _listener
    blocked = listener.blocked()
    if blocked:
        raise audio.MicrophoneError(blocked)
    listener.quiet()
    listener.play(core.commands.LISTEN_SOUND)
    listener.sleep(listener.tone_seconds(core.commands.LISTEN_SOUND) + TONE_GAP_SECONDS)
    try:
        pcm = listener.make_recorder().record(lambda chunk: False, max_seconds=seconds)
    finally:
        listener.play(core.commands.LISTEN_END_SOUND)
    levels = audio.frame_levels(pcm)
    peak = max(levels, default=0.0)
    if pcm and peak <= 0:
        raise audio.MicrophoneError("silent")
    room, voice = audio.measure(levels)
    calibration = audio.calibrate(room, voice)
    voice_db = "none" if voice is None else f"{audio.level_db(voice):.0f} dB"
    logger.info(f"[{EXT_NAME}] Microphone test: room {audio.level_db(room):.0f} dB, voice "
                f"{voice_db}; sensitivity {calibration.sensitivity or 'unchanged'}, "
                f"problem {calibration.problem or 'none'}.")
    return {"level": audio.level_db(peak), "speech": voice is not None,
            "seconds": audio.seconds_of(pcm), "room": room, "voice": voice,
            "calibration": calibration}


# ------------------------------------------------------------
# Downloads: one at a time, on a worker thread
# ------------------------------------------------------------

class Download:
    """The program, a model or the wake phrase listener being downloaded (a
    model brings the program along when it isn't installed)."""

    def __init__(self, item, need_runtime):
        self.item = item
        if item == "wake":
            self.need_runtime = False
            self.total = download.WAKE_SIZE
        else:
            self.need_runtime = need_runtime or item == "runtime"
            self.total = (download.RUNTIME_SIZE if self.need_runtime else 0) + (
                0 if item == "runtime" else download.MODELS[item]["size"])
        self.percent = 0
        self.spoken = 0
        self.reported = -1
        self.cancel_event = threading.Event()

    @property
    def title(self):
        return text.item_name(self.item)


class Downloads:
    def __init__(self, install_runtime=None, install_model=None, install_wake=None):
        self._install_runtime = install_runtime or download.install_runtime
        self._install_model = install_model or download.install_model
        self._install_wake = install_wake or download.install_wake
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

    def start(self, item):
        """Start downloading `item` ("runtime" or a model). False when
        another download is running."""
        with self._lock:
            if self._current is not None:
                return False
            job = Download(item, not store.runtime_installed(store.root_dir()))
            self._current = job
        _say(_("download_started", name=job.title, size=text.size_label(job.total)))
        threading.Thread(target=self._run, args=(job,), daemon=True,
                         name="hariku-voice-control-download").start()
        return True

    def cancel(self):
        job = self.current()
        if job is None:
            return False
        job.cancel_event.set()
        return True

    def _run(self, job):
        root = store.root_dir()
        error = None
        try:
            store.cleanup_partials(root)
            done_before = 0
            if job.item == "wake":
                _wake.suspend("download")          # its files may be replaced
                try:
                    self._install_wake(root, progress=lambda n: self._progress(job, n),
                                       cancelled=job.cancel_event.is_set)
                finally:
                    _wake.release("download")
            if job.need_runtime:
                _engine.stop_all()          # its files may be replaced
                self._install_runtime(root, progress=lambda n: self._progress(job, n),
                                      cancelled=job.cancel_event.is_set)
                done_before = download.RUNTIME_SIZE
            if job.item not in ("runtime", "wake"):
                self._install_model(job.item, root,
                                    progress=lambda n: self._progress(job, done_before + n),
                                    cancelled=job.cancel_event.is_set)
        except download.Cancelled as e:
            error = e
        except download.DownloadError as e:
            error = download.Cancelled() if job.cancel_event.is_set() else e
            logger.info(f"[{EXT_NAME}] Downloading {job.item} failed: {e}")
        except Exception as e:
            error = e
            logger.exception(f"[{EXT_NAME}] Downloading {job.item} failed")
        try:
            refresh_state()
            _wake.refresh()
        except Exception:
            logger.exception(f"[{EXT_NAME}] Reading what is installed failed")
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
            _say(_("progress_spoken", percent=reached[-1]), interrupt=False)
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
            _say(_("download_failed", error=text.download_error(error)))
        self._notify("finished", job, error)

    def _notify(self, event, job, value):
        for listener in list(self._listeners):
            try:
                listener(event, job, value)
            except Exception:
                logger.exception(f"[{EXT_NAME}] A download listener failed")


_downloads = Downloads()


# ------------------------------------------------------------
# What the Preferences page uses
# ------------------------------------------------------------

def _in_thread(work, done, name):
    """Run work() on a worker thread; done(result, error) on the UI thread."""
    def runner():
        result, error = None, None
        try:
            result = work()
        except Exception as e:
            error = e
            if isinstance(e, (kws.KwsError, ValueError, bpe.ModelError)):
                logger.warning(f"[{EXT_NAME}] {name} failed: {e}")
            elif not isinstance(e, (audio.MicrophoneError, download.DownloadError, OSError)):
                logger.exception(f"[{EXT_NAME}] {name} failed")
        _call_after(done, result, error)

    threading.Thread(target=runner, daemon=True, name=f"hariku-voice-control-{name}").start()


class Controller:
    """The page's way to everything slow; results come back on the UI thread."""

    downloads = _downloads

    @staticmethod
    def installed():
        """{item: True/False} for the program, each model and the wake phrase
        listener (a quick look at the disk)."""
        root = store.root_dir()
        models = set(store.installed_models(root))
        state = {"runtime": store.runtime_installed(root),
                 "wake": download.wake_installed(root)}
        state.update({name: name in models for name in store.MODEL_NAMES})
        return state

    @staticmethod
    def settings():
        return get_settings()

    @staticmethod
    def save_settings(model, listen_on_open_, silence_ms, sensitivity=None, wake_settings=None):
        save_settings(model, listen_on_open_, silence_ms, sensitivity, wake_settings)

    @staticmethod
    def remove(item):
        """Delete the program, a model (its server is stopped first: Windows
        can't delete a file in use) or the wake phrase listener. Returns
        whether it was there, or "later" when some files are only deleted at
        the next start (a DLL Hariku has loaded)."""
        _engine.stop_all()
        root = store.root_dir()
        try:
            if item == "runtime":
                return store.remove_runtime(root)
            if item == "wake":
                removed, complete = store.remove_wake(root)
                return removed and (True if complete else "later")
            removed = store.remove_model(root, item)
            store.forget_speed(item)
            reload_settings()
            return removed
        finally:
            refresh_state()
            _wake.refresh()

    @staticmethod
    def test_microphone(done):
        """done(result, error) on the UI thread; see test_microphone()."""
        if _listener.busy():
            done(None, RuntimeError("busy"))
            return
        _wake.suspend("microphone-test")

        def finished(result, error):
            _wake.release("microphone-test")
            done(result, error)

        _in_thread(test_microphone, finished, "microphone-test")

    @staticmethod
    def wake_state():
        """(the wake phrase listener's state, the phrase it listens for)."""
        return _wake.state, _wake.config.phrase

    @staticmethod
    def add_wake_listener(listener):
        """listener(state) on the UI thread whenever the wake phrase's state changes."""
        if listener not in _wake_state_listeners:
            _wake_state_listeners.append(listener)

    @staticmethod
    def remove_wake_listener(listener):
        if listener in _wake_state_listeners:
            _wake_state_listeners.remove(listener)

    @staticmethod
    def test_wake(phrase, sensitivity, on_heard, done, stop=None):
        """Start the wake phrase test; returns the Event (`stop`, or a new
        one) that stops it early. on_heard(count) and done(result, error)
        come on the UI thread; see test_wake()."""
        stop = stop or threading.Event()
        if _listener.busy():
            done(None, RuntimeError("busy"))
            return stop
        _wake.suspend("wake-test")

        def heard(count):
            _call_after(on_heard, count)

        def finished(result, error):
            _wake.release("wake-test")
            done(result, error)

        _in_thread(lambda: test_wake(phrase, sensitivity, heard, stop), finished, "wake-test")
        return stop


controller = Controller()


def _create_panel(parent):
    global _panel
    _panel = voice_control_ui.VoiceControlPanel(parent, controller)
    return _panel


def _apply_panel():
    if _panel is not None:
        try:
            _panel.ApplyChanges()
        except RuntimeError:
            pass     # the page is gone


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def wake_action_id():
    return f"{EXT_NAME}.{WAKE_ACTION}"


def register(bus):
    global _panel, _bus
    _panel = None
    if not hasattr(core.commands, "register_listener"):
        logger.warning(f"[{EXT_NAME}] This Hariku has no command bar; Voice Control needs core 2.7.")
        return
    _bus = bus
    _engine.restart()
    _wake.restart()
    bus.subscribe("on_before_speak", _speech.on_before_speak)
    try:
        store.cleanup_partials(store.root_dir())
        refresh_state()
        reload_settings()                  # starts the wake phrase listener when it's on
    except Exception:
        logger.exception(f"[{EXT_NAME}] Reading what is installed failed")
    core.commands.register_listener(_listener.start, _listener.stop, _listener.is_available,
                                    _listener.listen_on_open, name=EXT_NAME)
    core.hotkeys.register_action(EXT_NAME, WAKE_ACTION, _("action_toggle_wake"), None, False,
                                 toggle_wake_pause)
    core.commands.add_aliases(wake_action_id(), text.WAKE_ALIASES,
                              title=_("action_toggle_wake_title"))
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info(f"[{EXT_NAME}] Extension loaded.")


def _shutdown():
    _listener.stop(discard=True)
    _downloads.cancel()
    _wake.stop()
    _engine.shutdown()


def teardown():
    global _panel, _bus
    _panel = None
    try:
        core.commands.unregister_listener(_listener.start)
        core.commands.remove_aliases(wake_action_id())
    except Exception:
        pass
    if _bus is not None:
        _bus.unsubscribe("on_before_speak", _speech.on_before_speak)
        _bus = None
    _shutdown()
    logger.info(f"[{EXT_NAME}] Extension unloaded.")
