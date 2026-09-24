# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The wake phrase: "Hey Aruna" (or any phrase the user types) opens Aruna and
starts listening, as the hotkey does (no wx here; main.py opens the bar).

  clean_phrase(), phrase_problem()   what the user typed, and whether it is a
                                     good wake phrase (one word, very short,
                                     common, letters the model can't hear)
  keywords_text()                    the phrase as sherpa-onnx keyword lines,
                                     in the model's tokens, with the
                                     sensitivity's threshold and boost
  ActivityGate                       only sound worth hearing reaches the
                                     spotter, so a quiet room costs no CPU
  SpeechWatch                        Hariku speaking (Hariku Voice, or the
                                     screen reader through Hariku): not heard
  WakeListener                       the background thread: microphone ->
                                     gate -> spotter -> "heard it"

Nothing heard is ever kept: each 100 ms of sound is handed to the spotter and
dropped. Nothing is saved or sent anywhere. The listener pauses (and closes
the microphone) while Voice Control itself listens to a command, while the
user has paused it, during quiet hours when the user asked for that, while
Windows' privacy settings block the microphone (said once), and while a test
on the Preferences page uses the microphone. While Hariku is speaking it
keeps the microphone open but ignores what it hears, so the screen reader or
Hariku Voice saying "Hey Aruna" can't wake it.
"""
import array
import collections
import logging
import math
import threading
import time
import unicodedata

import voice_control_audio as audio
import voice_control_kws as kws

logger = logging.getLogger(__name__)

DEFAULT_PHRASE = "Hey Aruna"
MAX_PHRASE_CHARS = 40
TEST_SECONDS = 20              # the page's "Test the wake phrase"
MAX_WORDS = 5
SHORT_LETTERS = 6            # fewer letters than this is very short
LONG_LETTERS = 30

# Sensitivity: (threshold, boost score, beam width) for sherpa-onnx. A lower
# threshold, a higher boost and more paths searched at once (max_active_paths)
# hear the phrase more easily, and other speech too. Chosen with the real
# sherpa-onnx on synthetic clips (Windows voices at three speeds, and Piper):
# "Hey Aruna" 26 times, "Hi Princess", "Hi Baby" and "Hey Jarvis" 8 times each,
# against 116 decoy sentences (many near misses: "Hey Arun", "Hey, a rune",
# "Aruba", "a runner") and 81 seconds of ordinary speech:
#   low     Aruna  6/26, English 23/24; false: none
#   normal  Aruna 10/26, English 24/24; false: Aruna 1/116 ("Hey, a rune")
#   high    Aruna 24/26, English 24/24; false: Aruna 3/116 ("Hey Arun", "Hey, a
#           rune"), Princess 1/116 ("Hari ini aku mau ke pasar")
# and never in the 81 seconds of speech. Normal is sherpa-onnx's own default.
# A wider beam alone hears Aruna more but loses short English phrases ("Hi
# Baby" 4/8 at 16 paths); with the higher boost they stay 8/8.
SENSITIVITY = {
    "low": (0.35, 1.0, 4),
    "normal": (0.25, 1.0, 4),
    "high": (0.1, 2.0, 12),
}
SENSITIVITIES = ("low", "normal", "high")
DEFAULT_SENSITIVITY = "normal"

# Indonesian spellings of English greetings: the English model only knows the
# English one, so it is added as another keyword line with the same name. On
# the clips (said the English way), typed "Hai Princess"/"Hai Baby" went from
# 0/8 to 8/8, "Hei Jarvis" 0/8 to 8/8, "Hei Aruna" 0/18 to 6/18 and "Halo
# Aruna" 0/8 to 6/8, with no false detection added. Other spellings of Aruna
# itself ("A runa", "Aroona", "Arunah", ...) found nothing more and one of them
# found less, and "Oke" -> "Okay" didn't help, so none of those is added.
ALTERNATIVES = {
    "HEI": ("HEY",),
    "HAI": ("HI",),
    "HALO": ("HELLO",),
}

# Words people say in ordinary talk (English and Indonesian): a phrase made
# only of these would wake Aruna by mistake.
COMMON_WORDS = frozenset("""
A AN THE AND OR BUT SO IF OF TO IN ON AT FOR WITH FROM BY UP DOWN OUT OFF OVER
I ME MY YOU YOUR HE SHE IT WE THEY THEM THIS THAT THESE THOSE WHAT WHO WHERE WHEN
WHY HOW IS ARE WAS WERE BE BEEN AM DO DOES DID HAVE HAS HAD CAN COULD WILL WOULD
SHALL SHOULD MAY MIGHT MUST NOT NO YES YEAH YEP NOPE OK OKAY OKE ALRIGHT RIGHT WELL
HEY HI HELLO HOWDY BYE GOODBYE PLEASE THANKS THANK SORRY EXCUSE GOOD MORNING NIGHT
EVENING AFTERNOON DAY TODAY NOW THEN HERE THERE COME GO GET LET STOP WAIT LOOK LISTEN
SAY TELL KNOW THINK WANT NEED LIKE LOVE JUST REALLY VERY TOO ALSO ONE TWO THREE
HAI HALO HEI YA TIDAK GAK NGGAK ENGGAK IYA ADA APA SIAPA MANA KAPAN KENAPA BAGAIMANA
AKU KAMU DIA KITA KAMI MEREKA SAYA INI ITU DAN ATAU TAPI DI KE DARI YANG UNTUK DENGAN
SUDAH BELUM MAU BISA TOLONG TERIMA KASIH SELAMAT PAGI SIANG SORE MALAM OKE SIP AYO
DONG DEH SIH NIH KAN LAGI JUGA AJA SAJA NANTI SEKARANG BESOK
""".split())

LETTERS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
INNER = set("'-")                   # the model's tokens have these inside words
SEPARATORS = set(" \t\n,.!?;:\"()[]{}/’‘“”")


# ------------------------------------------------------------
# The phrase
# ------------------------------------------------------------

def tidy(text):
    """The phrase as saved: spaces collapsed, at most MAX_PHRASE_CHARS."""
    return " ".join(str(text or "").split())[:MAX_PHRASE_CHARS].strip()


def clean_phrase(text):
    """(words, unsupported): the phrase as the model's upper-case words, and
    the characters it can't hear ("2", "你"; accents are dropped: "é" is
    "E"). Punctuation separates words; "'" and "-" may join them."""
    text = unicodedata.normalize("NFKD", tidy(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").upper()
    words, current, unsupported = [], [], []
    for char in text:
        if char in LETTERS:
            current.append(char)
        elif char in INNER:
            if current:
                current.append(char)          # inside a word; at its start it's nothing
        elif char in SEPARATORS or char.isspace():
            if current:
                words.append("".join(current))
                current = []
        else:
            unsupported.append(char)
    if current:
        words.append("".join(current))
    words = [w.strip("'-") for w in words]
    return [w for w in words if w], unsupported


def phrase_problem(text):
    """Why a phrase makes a poor wake phrase, or None: "empty",
    "digits" (write numbers as words), "unsupported" (letters the English
    model doesn't have), "common" (only everyday words), "one_word",
    "short" (under SHORT_LETTERS letters) or "long"."""
    words, unsupported = clean_phrase(text)
    if not words and not unsupported:
        return "empty"
    if any(c.isdigit() for c in unsupported):
        return "digits"
    if unsupported or not words:
        return "unsupported"
    if all(w in COMMON_WORDS for w in words):
        return "common"
    if len(words) == 1:
        return "one_word"
    letters = sum(1 for w in words for c in w if c in LETTERS)
    if letters < SHORT_LETTERS:
        return "short"
    if len(words) > MAX_WORDS or letters > LONG_LETTERS:
        return "long"
    return None


def usable(text):
    """Whether a phrase can be listened for at all (it has words and every
    character can be heard); a poor one (one word, short, common) still can."""
    words, unsupported = clean_phrase(text)
    return bool(words) and not unsupported


def keyword_name(words):
    """The name sherpa-onnx reports for the phrase: "HEY_ARUNA"."""
    return "_".join(words)


def spellings(words):
    """The phrase's words, then each alternative spelling (ALTERNATIVES),
    without duplicates."""
    found = [list(words)]
    for index, word in enumerate(words):
        for other in ALTERNATIVES.get(word, ()):
            for known in list(found):
                variant = known[:index] + other.split() + known[index + 1:]
                if variant not in found:
                    found.append(variant)
    return found


def sensitivity_values(name):
    """(threshold, score, max_active_paths) of a sensitivity; Normal for an
    unknown one."""
    return SENSITIVITY.get(name, SENSITIVITY[DEFAULT_SENSITIVITY])


def keywords_text(phrase, tokenizer, tokens, sensitivity=DEFAULT_SENSITIVITY):
    """sherpa-onnx's keyword lines for a phrase: "▁HE Y ▁A RU N A :1.0 #0.25
    @HEY_ARUNA", one per spelling. `tokenizer` has encode(text) -> pieces;
    `tokens` is the set of tokens.txt. ValueError when the phrase can't be
    heard (no words, or a piece the model doesn't have)."""
    words, unsupported = clean_phrase(phrase)
    if not words or unsupported:
        raise ValueError(f"not a phrase the model can hear: {phrase!r}")
    threshold, score, _paths = sensitivity_values(sensitivity)
    name = keyword_name(words)
    lines = []
    for variant in spellings(words):
        pieces = tokenizer.encode(" ".join(variant))
        if not pieces or any(p not in tokens for p in pieces):
            raise ValueError(f"the model has no tokens for {' '.join(variant)!r}")
        line = f"{' '.join(pieces)} :{score:g} #{threshold:g} @{name}"
        if line not in lines:
            lines.append(line)
    return "\n".join(lines)


# ------------------------------------------------------------
# Only sound worth hearing reaches the spotter
# ------------------------------------------------------------

def chunk_level(samples, parts=3):
    """The loudest of `parts` pieces of a chunk (RMS of 16-bit samples)."""
    if not samples:
        return 0.0
    size = max(1, len(samples) // parts)
    best = 0.0
    for start in range(0, len(samples), size):
        piece = samples[start:start + size]
        best = max(best, math.sqrt(sum(s * s for s in piece) / len(piece)))
    return best


class ActivityGate:
    """Decides which chunks the spotter hears: sound louder than the room
    (at least `min_level`, `ratio` times the room), with `preroll` chunks
    before it and `hangover` chunks after it. In a quiet room nothing reaches
    the spotter, so it costs no CPU. The room's level follows quieter chunks
    quickly and louder ones slowly (and only those less than 1.5 times it),
    like the command's voice activity detector; and when `settle` chunks in a
    row were all loud (a fan or a radio switched on, not speech, which pauses),
    the quietest of them becomes the room."""

    def __init__(self, min_level=40.0, ratio=1.6, preroll=6, hangover=20, settle=100):
        self.min_level = float(min_level)
        self.ratio = float(ratio)
        self.preroll = preroll
        self.hangover = hangover
        self.room = None
        self._before = []
        self._left = 0          # chunks still to pass after the last loud one
        self._loud_levels = collections.deque(maxlen=settle)
        self.active = False

    def reset(self):
        self._before = []
        self._left = 0
        self.active = False

    def _follow_room(self, level):
        if self.room is None:
            self.room = level
        elif level <= self.room:
            self.room += audio.ROOM_FOLLOW_DOWN * (level - self.room)
        elif level < self.room * audio.ROOM_RISE_LIMIT:
            self.room += audio.ROOM_FOLLOW_UP * (level - self.room)

    def feed(self, samples):
        """Add one chunk (an array("h")); returns (new segment?, [chunks to
        hear]): a loud chunk after quiet brings the chunks before it."""
        level = chunk_level(samples)
        loud = level >= max(self.min_level, (self.room or 0.0) * self.ratio)
        if not loud:
            self._follow_room(level)
            self._loud_levels.clear()
        else:
            self._loud_levels.append(level)
            if len(self._loud_levels) == self._loud_levels.maxlen:
                self.room = max(self.room or 0.0, min(self._loud_levels))   # the new room
                self._loud_levels.clear()
        if loud:
            started = not self.active
            chunks = (self._before + [samples]) if started else [samples]
            self._before = []
            self.active = True
            self._left = self.hangover
            return started, chunks
        if self.active:
            self._left -= 1
            if self._left <= 0:
                self.active = False
            return False, [samples]
        self._before.append(samples)
        del self._before[:-self.preroll]
        return False, []


# ------------------------------------------------------------
# Hariku speaking
# ------------------------------------------------------------

READER_SECONDS = 0.8          # a screen reader starts a little late...
READER_SECONDS_PER_CHAR = 0.07  # ...and says about 14 characters a second
READER_MAX_SECONDS = 60.0
AFTER_SPEECH_SECONDS = 0.6    # the microphone's buffers still hold the end of it


def speech_seconds(text):
    """About how long a screen reader takes to say `text`."""
    return min(READER_MAX_SECONDS,
               READER_SECONDS + len(str(text or "").strip()) * READER_SECONDS_PER_CHAR)


class SpeechWatch:
    """While Hariku speaks, the wake phrase isn't listened for: Hariku Voice
    speaking (voice_speaking(), core.voice.is_speaking), or text handed to
    the screen reader through Hariku (on_before_speak), for about as long as
    the screen reader needs to say it.

    Text that interrupts (and "Interrupt speech" is on: interrupts()) cuts
    off what the screen reader was saying, so only it is left to say; other
    text is said after what is already waiting."""

    def __init__(self, voice_speaking=None, clock=None, interrupts=None):
        self._voice_speaking = voice_speaking or (lambda: False)
        self._clock = clock or time.monotonic
        self._interrupts = interrupts or (lambda: True)
        self._lock = threading.Lock()
        self._until = 0.0

    def on_before_speak(self, payload):
        """core.events' on_before_speak (any thread): Hariku is about to speak."""
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            return
        interrupt = bool(payload.get("interrupt"))
        if interrupt:
            try:
                interrupt = bool(self._interrupts())
            except Exception:
                logger.debug("Voice Control: reading Interrupt speech failed", exc_info=True)
        self.hold(speech_seconds(text), queued=not interrupt)

    def hold(self, seconds, queued=False):
        """Ignore what is heard for `seconds` (and a moment more) from now,
        or, `queued`, from when what is being said now ends."""
        now = self._clock()
        with self._lock:
            start = max(now, self._until - AFTER_SPEECH_SECONDS) if queued else now
            self._until = start + seconds + AFTER_SPEECH_SECONDS

    def speaking(self):
        with self._lock:
            until = self._until
        if self._clock() < until:
            return True
        try:
            if self._voice_speaking():
                self.hold(0.0)          # and a moment after it ends
                return True
        except Exception:
            logger.debug("Voice Control: asking whether Hariku Voice speaks failed",
                         exc_info=True)
        return False


# ------------------------------------------------------------
# The spotter behind the gate
# ------------------------------------------------------------

COOLDOWN_SECONDS = 2.0         # one "Hey Aruna" is one detection


class Ear:
    """What the listener (and the page's test) do with each 100 ms of sound:
    ignore it while Hariku speaks, pass it through the activity gate, and
    give the spotter what comes out, starting a fresh stream for each new
    stretch of sound. hear(chunk) returns the phrases detected (at most one
    per COOLDOWN_SECONDS). The chunk is dropped afterwards."""

    def __init__(self, spotter, speaking=None, gate=None, clock=None):
        self.spotter = spotter
        self._speaking = speaking or (lambda: False)
        self.gate = gate or ActivityGate()
        self._clock = clock or time.monotonic
        self._fresh = True
        self._cooldown = 0.0
        spotter.new_stream()

    def hear(self, chunk):
        if self._speaking():
            self.gate.reset()
            self._fresh = True            # what came before doesn't join what comes after
            return []
        samples = array.array("h")
        samples.frombytes(bytes(chunk[:len(chunk) - len(chunk) % 2]))
        started, chunks = self.gate.feed(samples)
        if not chunks:
            return []
        if started or self._fresh:
            self.spotter.new_stream()
            self._fresh = False
        names = []
        for piece in chunks:
            names += self.spotter.accept(array.array("f", [s / 32768.0 for s in piece]))
        now = self._clock()
        if not names or now < self._cooldown:
            return []
        self._cooldown = now + COOLDOWN_SECONDS
        return names[:1]


# ------------------------------------------------------------
# The listener
# ------------------------------------------------------------

# What the listener is doing (main.py and the page show it).
OFF = "off"                    # the wake phrase is off
MISSING = "missing"            # the program or model isn't downloaded
LISTENING = "listening"
PAUSED = "paused"              # the user paused it
QUIET = "quiet"                # quiet hours
BUSY = "busy"                  # Voice Control is listening, or a test uses the microphone
BLOCKED = "blocked"            # Windows' privacy settings block the microphone
MIC_ERROR = "mic_error"        # no microphone, or another program has it
ENGINE_ERROR = "engine_error"  # the spotter could not start
STATES = (OFF, MISSING, LISTENING, PAUSED, QUIET, BUSY, BLOCKED, MIC_ERROR, ENGINE_ERROR)

CAPTURE_SECONDS = 3600.0       # the microphone is reopened every hour
POLL_SECONDS = 0.04            # checking for the next 100 ms of sound
IDLE_SECONDS = 1.0             # checking whether a pause has ended
BLOCKED_CHECK_SECONDS = 5.0    # Windows' privacy settings, while listening
RETRY_SECONDS = 15.0           # after a microphone or spotter error
QUIET_CHECK_SECONDS = 30.0
HANDOVER_SECONDS = 4.0         # after a detection, the bar gets the microphone
AFTER_COMMAND_SECONDS = 1.0


class Config:
    def __init__(self, enabled=False, phrase=DEFAULT_PHRASE, sensitivity=DEFAULT_SENSITIVITY,
                 quiet_hours=False):
        self.enabled = bool(enabled)
        self.phrase = tidy(phrase) or DEFAULT_PHRASE
        self.sensitivity = sensitivity if sensitivity in SENSITIVITY else DEFAULT_SENSITIVITY
        self.quiet_hours = bool(quiet_hours)

    def spotter_key(self):
        return (self.phrase, self.sensitivity)

    def __eq__(self, other):
        return isinstance(other, Config) and vars(self) == vars(other)

    def __repr__(self):
        return f"Config({vars(self)!r})"


class WakeListener:
    """Listens for the wake phrase on its own thread while enabled.

    make_spotter(phrase, sensitivity) -> an object with accept(float
    samples) -> [names], new_stream() and close() (voice_control_kws.Spotter);
    make_recorder() -> audio.Recorder; on_detect(name) is called on the
    listener's thread. installed() says whether the files are there;
    busy() whether Voice Control is listening to a command; quiet_time()
    whether it is quiet hours; blocked() is audio.microphone_blocked;
    speaking() is SpeechWatch.speaking. on_state(state) tells about a new
    state, on_problem(kind, value) about a problem to say once ("blocked",
    kind), ("mic", kind) or ("engine", KwsError)."""

    def __init__(self, make_spotter, make_recorder, on_detect, installed=None, busy=None,
                 quiet_time=None, blocked=None, speaking=None, on_state=None, on_problem=None,
                 clock=None, gate=None):
        self._make_spotter = make_spotter
        self._make_recorder = make_recorder
        self._on_detect = on_detect
        self._installed = installed or (lambda: True)
        self._busy = busy or (lambda: False)
        self._quiet_time = quiet_time or (lambda: False)
        self._blocked = blocked or audio.microphone_blocked
        self._speaking = speaking or (lambda: False)
        self._on_state = on_state
        self._on_problem = on_problem
        self._clock = clock or time.monotonic
        self._make_gate = gate or ActivityGate
        self._lock = threading.Lock()
        self._config = Config()
        self._paused = False               # by the user, until Hariku restarts
        self._suspended = set()            # tests on the page using the microphone
        self._hold_until = 0.0
        self._was_busy = False
        self._changed = threading.Event()  # wakes the thread: settings or a pause changed
        self._stopping = threading.Event()
        self._thread = None
        self._state = OFF
        self._said = set()                 # problems said once
        self._quiet_checked = None
        self._quiet_now = False
        self.detections = 0

    # --- what others ask -------------------------------------------------------------

    @property
    def state(self):
        return self._state

    @property
    def config(self):
        with self._lock:
            return self._config

    @property
    def paused(self):
        return self._paused

    def configure(self, config):
        """New settings (a Config); starts or stops the thread."""
        with self._lock:
            changed = config != self._config
            self._config = config
        if changed:
            self._said.discard(("engine", None))
            self._quiet_checked = None
            self._changed.set()
        self._ensure_thread()

    def set_paused(self, paused):
        self._paused = bool(paused)
        self._changed.set()
        self._ensure_thread()

    def suspend(self, reason):
        """A test on the page uses the microphone: pause until release()."""
        with self._lock:
            self._suspended.add(reason)
        self._changed.set()

    def release(self, reason):
        with self._lock:
            self._suspended.discard(reason)
        self._changed.set()

    def refresh(self):
        """Look again now (the files were downloaded or removed)."""
        self._changed.set()
        self._ensure_thread()

    def hold(self, seconds):
        """Don't listen for `seconds` (the bar is taking the microphone)."""
        with self._lock:
            self._hold_until = max(self._hold_until, self._clock() + seconds)
        self._changed.set()

    def stop(self):
        """Stop for good (the extension is unloading)."""
        self._stopping.set()
        self._changed.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)

    def restart(self):
        """Usable again after stop() (the extension was loaded again)."""
        self._stopping.clear()

    # --- the thread --------------------------------------------------------------------

    def _ensure_thread(self):
        if self._stopping.is_set():
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if not self._config.enabled:
                self._set_state(OFF)
                return
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="hariku-voice-control-wake")
            self._thread.start()

    def _set_state(self, state):
        if state == self._state:
            return
        self._state = state
        logger.info(f"Voice Control: the wake phrase is {state}.")
        if self._on_state is not None:
            try:
                self._on_state(state)
            except Exception:
                logger.exception("Voice Control: telling about the wake phrase's state failed")

    def _problem(self, kind, value):
        """Say a problem once (until it clears or the settings change)."""
        key = (kind, None if kind == "engine" else value)
        if key in self._said:
            return
        self._said.add(key)
        if self._on_problem is not None:
            try:
                self._on_problem(kind, value)
            except Exception:
                logger.exception("Voice Control: telling about a wake phrase problem failed")

    def _is_quiet(self, config):
        if not config.quiet_hours:
            return False
        now = self._clock()
        if self._quiet_checked is None or now - self._quiet_checked >= QUIET_CHECK_SECONDS:
            self._quiet_checked = now
            try:
                self._quiet_now = bool(self._quiet_time())
            except Exception:
                logger.exception("Voice Control: reading the quiet hours failed")
                self._quiet_now = False
        return self._quiet_now

    def _pause_reason(self, config):
        """Why not to listen now, or None. Checked before and while listening."""
        if not config.enabled:
            return OFF
        if not self._installed():
            return MISSING
        if self._paused:
            return PAUSED
        with self._lock:
            suspended = bool(self._suspended)
            held = self._clock() < self._hold_until
        busy = False
        try:
            busy = bool(self._busy())
        except Exception:
            logger.exception("Voice Control: asking whether a command is heard failed")
        if busy:
            self._was_busy = True
        elif self._was_busy:
            self._was_busy = False
            self.hold(AFTER_COMMAND_SECONDS)      # the bar may still be answering
            held = True
        if suspended or held or busy:
            return BUSY
        if self._is_quiet(config):
            return QUIET
        return None

    def _run(self):
        spotter, spotter_key = None, None
        try:
            while not self._stopping.is_set():
                config = self.config
                if not config.enabled:
                    self._set_state(OFF)
                    break
                reason = self._pause_reason(config)
                if reason is None:
                    blocked = self._blocked()
                    if blocked:
                        reason = BLOCKED
                        self._problem("blocked", blocked)
                    else:
                        self._said = {k for k in self._said if k[0] != "blocked"}
                if reason is not None:
                    self._set_state(reason)
                    if reason in (MISSING, OFF) and spotter is not None:
                        spotter.close()
                        spotter, spotter_key = None, None
                    self._changed.wait(BLOCKED_CHECK_SECONDS if reason == BLOCKED
                                       else IDLE_SECONDS)
                    self._changed.clear()
                    continue
                if spotter is None or spotter_key != config.spotter_key():
                    if spotter is not None:
                        spotter.close()
                        spotter = None
                    try:
                        spotter = self._make_spotter(config.phrase, config.sensitivity)
                        spotter_key = config.spotter_key()
                        self._said.discard(("engine", None))
                    except Exception as e:
                        logger.warning(f"Voice Control: the wake phrase can't start: {e}")
                        self._set_state(ENGINE_ERROR)
                        self._problem("engine", e)
                        self._changed.wait(RETRY_SECONDS)
                        self._changed.clear()
                        continue
                self._set_state(LISTENING)
                try:
                    self._listen(spotter, config)
                    self._said = {k for k in self._said if k[0] != "mic"}
                except audio.MicrophoneError as e:
                    logger.info(f"Voice Control: the wake phrase's microphone: {e}")
                    self._set_state(BLOCKED if e.kind.startswith("blocked") else MIC_ERROR)
                    self._problem("mic", e.kind)
                    self._changed.wait(RETRY_SECONDS)
                    self._changed.clear()
                except Exception:
                    logger.exception("Voice Control: listening for the wake phrase failed")
                    self._set_state(ENGINE_ERROR)
                    self._changed.wait(RETRY_SECONDS)
                    self._changed.clear()
        finally:
            if spotter is not None:
                try:
                    spotter.close()
                except Exception:
                    logger.exception("Voice Control: closing the keyword spotter failed")
            with self._lock:
                self._thread = None
            if self._stopping.is_set():
                self._set_state(OFF)
            elif self.config.enabled:
                self._ensure_thread()       # the settings were turned on again meanwhile

    def _listen(self, spotter, config):
        """Record until something pauses the listener; each chunk goes
        through the Ear, then is dropped."""
        ear = Ear(spotter, self._speaking, self._make_gate(), self._clock)
        checked = [self._clock()]
        self._changed.clear()

        def on_chunk(chunk):
            if self._stopping.is_set() or self._changed.is_set():
                return True                  # new settings, a pause or a test
            if self.config != config or self._pause_reason(config) is not None:
                return True
            now = self._clock()
            if now - checked[0] >= BLOCKED_CHECK_SECONDS:
                checked[0] = now
                if self._blocked():
                    return True
            names = ear.hear(chunk)
            if not names:
                return False
            self.detections += 1
            self.hold(HANDOVER_SECONDS)          # the bar takes the microphone now
            try:
                self._on_detect(names[0])
            except Exception:
                logger.exception("Voice Control: opening Aruna for the wake phrase failed")
            return True

        # Any change (settings, a pause, stop()) also ends the recording while
        # the microphone gives nothing.
        recorder = self._make_recorder()
        recorder.record(on_chunk, stop=self._changed, max_seconds=CAPTURE_SECONDS, keep=False)
