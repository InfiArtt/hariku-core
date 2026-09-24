# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The microphone and the sound it gives (no wx, no network, standard library
only).

  Recorder             16 kHz, 16-bit mono from the default microphone with
                       winmm's waveIn (ctypes), on the calling worker thread
  VoiceActivity        a simple energy-based voice activity detector: when
                       speech started, and when it ended
  wav_bytes()          a recording as a WAV file, in memory
  microphone_blocked() Windows' privacy switches for the microphone
  level_db()           a loudness in dB below full scale, for the microphone test

A recording stays in memory. It is handed to the whisper.cpp program on this
computer and then dropped: it is never written to disk or sent anywhere.
"""
import array
import ctypes
import ctypes.wintypes
import io
import math
import sys
import threading
import time
import wave

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2               # bytes: 16-bit
CHANNELS = 1
BUFFER_MS = 100                # one waveIn buffer
BUFFERS = 8
POLL_SECONDS = 0.01

WAVE_MAPPER = 0xFFFFFFFF
WAVE_FORMAT_PCM = 1
CALLBACK_NULL = 0
WHDR_DONE = 0x00000001
MMSYSERR_BADDEVICEID = 2
MMSYSERR_ALLOCATED = 4
MMSYSERR_NODRIVER = 6
MMSYSERR_NOMEM = 7
WAVERR_BADFORMAT = 32

# Windows' privacy switches (Settings, Privacy, Microphone).
CONSENT_KEY = (r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager"
               r"\ConsentStore\microphone")


class MicrophoneError(Exception):
    """kind: "none" (no microphone), "blocked_device", "blocked_apps",
    "blocked_desktop" (a Windows privacy switch is off), "busy" (another
    program has it), "silent" (it gave nothing but silence) or "failed"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = str(detail or "")


# ------------------------------------------------------------
# Windows' privacy switches
# ------------------------------------------------------------

def _read_consent(root, path):
    try:
        import winreg
        roots = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}
        with winreg.OpenKey(roots[root], path) as key:
            value, _kind = winreg.QueryValueEx(key, "Value")
        return str(value)
    except (OSError, ImportError, KeyError):
        return None


def microphone_blocked(read=None):
    """Which of Windows' microphone switches is off, or None: "blocked_device"
    (Allow access to the microphone on this device), "blocked_apps" (Allow
    apps to access your microphone) or "blocked_desktop" (Let desktop apps
    access your microphone). Only reads the registry."""
    read = read or _read_consent
    if read("HKLM", CONSENT_KEY) == "Deny":
        return "blocked_device"
    if read("HKCU", CONSENT_KEY) == "Deny":
        return "blocked_apps"
    if read("HKCU", CONSENT_KEY + r"\NonPackaged") == "Deny":
        return "blocked_desktop"
    return None


# ------------------------------------------------------------
# Loudness and speech
# ------------------------------------------------------------

def samples_of(pcm):
    """16-bit little-endian PCM bytes as an array of ints."""
    samples = array.array("h")
    samples.frombytes(bytes(pcm[:len(pcm) - len(pcm) % 2]))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def rms(samples):
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def level_db(value):
    """A loudness (RMS of 16-bit samples) in dB below full scale: -96 for
    silence, about -20 for speech close to the microphone."""
    if value <= 0:
        return -96.0
    return max(-96.0, 20.0 * math.log10(value / 32768.0))


class VoiceActivity:
    """Feed it the recording as it comes; `state` says what it heard:

      "waiting"    no speech yet
      "speaking"   speech started
      "done"       speech, then `silence_ms` of silence: stop recording
      "no_speech"  nothing in the first `start_timeout_ms`
      "too_long"   still going after `max_ms`: stop and use what there is

    Energy only: 30 ms frames, the first `calibrate_ms` measure the room;
    speech is `ratio` times louder than the room and at least `min_level`
    (RMS of 16-bit samples), for `min_speech_ms` in a row. While speaking, a
    frame counts as speech from 60% of that."""

    WAITING, SPEAKING = "waiting", "speaking"
    DONE, NO_SPEECH, TOO_LONG = "done", "no_speech", "too_long"
    FINISHED = (DONE, NO_SPEECH, TOO_LONG)

    def __init__(self, sample_rate=SAMPLE_RATE, frame_ms=30, silence_ms=1000,
                 start_timeout_ms=5000, max_ms=12000, min_speech_ms=150, calibrate_ms=150,
                 min_level=300.0, ratio=3.0):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_samples = sample_rate * frame_ms // 1000
        self.silence_ms = silence_ms
        self.start_timeout_ms = start_timeout_ms
        self.max_ms = max_ms
        self.min_speech_ms = min_speech_ms
        self.calibrate_ms = calibrate_ms
        self.min_level = float(min_level)
        self.ratio = float(ratio)
        self.state = self.WAITING
        self.elapsed_ms = 0
        self.noise = None
        self.peak = 0.0
        self.speech_start_ms = None     # where speech began, and ended
        self.speech_end_ms = None
        self._calibration = []
        self._run_ms = 0
        self._silent_ms = 0
        self._pending = array.array("h")
        self._odd_byte = b""

    @property
    def finished(self):
        return self.state in self.FINISHED

    @property
    def heard_speech(self):
        return self.speech_start_ms is not None

    def thresholds(self):
        noise = self.noise if self.noise is not None else 0.0
        start = max(self.min_level, noise * self.ratio)
        return start, start * 0.6

    def feed(self, pcm):
        """Add recorded bytes (or an array of samples); returns the state. A
        sample split between two pieces of bytes is put back together."""
        if isinstance(pcm, array.array):
            samples = pcm
        else:
            data = self._odd_byte + bytes(pcm)
            self._odd_byte = data[len(data) - len(data) % SAMPLE_WIDTH:]
            samples = samples_of(data)
        self._pending.extend(samples)
        size = self.frame_samples
        while len(self._pending) >= size and not self.finished:
            frame = self._pending[:size]
            del self._pending[:size]
            self._frame(frame)
        return self.state

    def _frame(self, frame):
        self.elapsed_ms += self.frame_ms
        level = rms(frame)
        self.peak = max(self.peak, level)
        if self.elapsed_ms <= self.calibrate_ms:
            self._calibration.append(level)
            ordered = sorted(self._calibration)
            self.noise = ordered[len(ordered) // 2]
            return
        start, keep = self.thresholds()
        if self.state == self.WAITING:
            if level >= start:
                self._run_ms += self.frame_ms
                if self._run_ms >= self.min_speech_ms:
                    self.state = self.SPEAKING
                    self.speech_start_ms = self.elapsed_ms - self._run_ms
                    self.speech_end_ms = self.elapsed_ms
                    self._silent_ms = 0
            else:
                self._run_ms = 0
                self.noise = 0.9 * self.noise + 0.1 * level    # follow the room
                if self.elapsed_ms >= self.start_timeout_ms:
                    self.state = self.NO_SPEECH
                    return
        elif self.state == self.SPEAKING:
            if level >= keep:
                self._silent_ms = 0
                self.speech_end_ms = self.elapsed_ms
            else:
                self._silent_ms += self.frame_ms
                if self._silent_ms >= self.silence_ms:
                    self.state = self.DONE
                    return
        if self.elapsed_ms >= self.max_ms and not self.finished:
            self.state = self.TOO_LONG if self.heard_speech else self.NO_SPEECH

    def speech_bytes(self, pcm, margin_ms=300):
        """The part of `pcm` with the speech, `margin_ms` around it (the whole
        recording when no speech was heard)."""
        if not self.heard_speech:
            return bytes(pcm)
        per_ms = self.sample_rate * SAMPLE_WIDTH // 1000
        start = max(0, (self.speech_start_ms - margin_ms)) * per_ms
        end = min(len(pcm), (self.speech_end_ms + margin_ms) * per_ms)
        return bytes(pcm[start:end])


# ------------------------------------------------------------
# WAV, in memory
# ------------------------------------------------------------

def wav_bytes(pcm, sample_rate=SAMPLE_RATE):
    """16-bit mono PCM as the bytes of a WAV file (never saved)."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(bytes(pcm))
    return out.getvalue()


def seconds_of(pcm, sample_rate=SAMPLE_RATE):
    return len(pcm) / float(sample_rate * SAMPLE_WIDTH)


# ------------------------------------------------------------
# Recording with waveIn (winmm through ctypes)
# ------------------------------------------------------------

class WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", ctypes.wintypes.WORD), ("nChannels", ctypes.wintypes.WORD),
                ("nSamplesPerSec", ctypes.wintypes.DWORD),
                ("nAvgBytesPerSec", ctypes.wintypes.DWORD),
                ("nBlockAlign", ctypes.wintypes.WORD), ("wBitsPerSample", ctypes.wintypes.WORD),
                ("cbSize", ctypes.wintypes.WORD)]


class WAVEHDR(ctypes.Structure):
    pass


WAVEHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", ctypes.wintypes.DWORD),
                    ("dwBytesRecorded", ctypes.wintypes.DWORD), ("dwUser", ctypes.c_size_t),
                    ("dwFlags", ctypes.wintypes.DWORD), ("dwLoops", ctypes.wintypes.DWORD),
                    ("lpNext", ctypes.POINTER(WAVEHDR)), ("reserved", ctypes.c_size_t)]

_winmm_dll = None
_winmm_lock = threading.Lock()


def _winmm():
    global _winmm_dll
    with _winmm_lock:
        if _winmm_dll is None:
            dll = ctypes.WinDLL("winmm")      # our own instance: argtypes stay private
            HANDLE = ctypes.wintypes.HANDLE
            UINT = ctypes.wintypes.UINT
            header = ctypes.POINTER(WAVEHDR)
            dll.waveInGetNumDevs.argtypes = []
            dll.waveInGetNumDevs.restype = UINT
            dll.waveInOpen.argtypes = [ctypes.POINTER(HANDLE), UINT, ctypes.POINTER(WAVEFORMATEX),
                                       ctypes.c_size_t, ctypes.c_size_t, ctypes.wintypes.DWORD]
            dll.waveInOpen.restype = UINT
            for name in ("waveInPrepareHeader", "waveInUnprepareHeader", "waveInAddBuffer"):
                fn = getattr(dll, name)
                fn.argtypes = [HANDLE, header, UINT]
                fn.restype = UINT
            for name in ("waveInStart", "waveInStop", "waveInReset", "waveInClose"):
                fn = getattr(dll, name)
                fn.argtypes = [HANDLE]
                fn.restype = UINT
            _winmm_dll = dll
        return _winmm_dll


def _error_for(code, where):
    if code in (MMSYSERR_BADDEVICEID, MMSYSERR_NODRIVER):
        return MicrophoneError("none", f"{where}: {code}")
    if code == MMSYSERR_ALLOCATED:
        return MicrophoneError("busy", f"{where}: {code}")
    return MicrophoneError("failed", f"{where}: MMRESULT {code}")


class Recorder:
    """Records from the default microphone on the calling thread. `winmm` is
    the DLL (or a fake with the same functions, for tests)."""

    def __init__(self, winmm=None, sample_rate=SAMPLE_RATE, buffer_ms=BUFFER_MS,
                 buffers=BUFFERS, sleep=time.sleep, clock=time.monotonic):
        self._winmm = winmm
        self.sample_rate = sample_rate
        self.buffer_bytes = sample_rate * SAMPLE_WIDTH * buffer_ms // 1000
        self.buffers = buffers
        self._sleep = sleep
        self._clock = clock

    def record(self, on_chunk, stop=None, max_seconds=30.0):
        """Record until on_chunk(bytes) returns True, `stop` (a
        threading.Event) is set, or `max_seconds` pass. Returns all the PCM
        recorded. Raises MicrophoneError."""
        winmm = self._winmm or _winmm()
        if not winmm.waveInGetNumDevs():
            raise MicrophoneError("none", "no recording device")
        fmt = WAVEFORMATEX(WAVE_FORMAT_PCM, CHANNELS, self.sample_rate,
                           self.sample_rate * SAMPLE_WIDTH * CHANNELS, SAMPLE_WIDTH * CHANNELS,
                           8 * SAMPLE_WIDTH, 0)
        handle = ctypes.wintypes.HANDLE()
        code = winmm.waveInOpen(ctypes.byref(handle), WAVE_MAPPER, ctypes.byref(fmt), 0, 0,
                                CALLBACK_NULL)
        if code:
            raise _error_for(code, "waveInOpen")
        size = ctypes.sizeof(WAVEHDR)
        memory, headers, prepared = [], [], []
        pcm = bytearray()
        try:
            for _i in range(self.buffers):
                buffer = ctypes.create_string_buffer(self.buffer_bytes)
                header = WAVEHDR()
                header.lpData = ctypes.cast(buffer, ctypes.c_void_p)
                header.dwBufferLength = self.buffer_bytes
                memory.append(buffer)
                headers.append(header)
                code = winmm.waveInPrepareHeader(handle, ctypes.byref(header), size)
                if code:
                    raise _error_for(code, "waveInPrepareHeader")
                prepared.append(header)
                code = winmm.waveInAddBuffer(handle, ctypes.byref(header), size)
                if code:
                    raise _error_for(code, "waveInAddBuffer")
            code = winmm.waveInStart(handle)
            if code:
                raise _error_for(code, "waveInStart")
            deadline = self._clock() + max_seconds
            index = 0
            while True:
                header = headers[index]
                while not header.dwFlags & WHDR_DONE:
                    if (stop is not None and stop.is_set()) or self._clock() > deadline:
                        return bytes(pcm)
                    self._sleep(POLL_SECONDS)
                chunk = ctypes.string_at(memory[index], header.dwBytesRecorded)
                pcm += chunk
                if on_chunk(chunk) or (stop is not None and stop.is_set()):
                    return bytes(pcm)
                header.dwFlags &= ~WHDR_DONE
                header.dwBytesRecorded = 0
                code = winmm.waveInAddBuffer(handle, ctypes.byref(header), size)
                if code:
                    raise _error_for(code, "waveInAddBuffer")
                index = (index + 1) % len(headers)
        finally:
            try:
                winmm.waveInReset(handle)
            except Exception:
                pass
            for header in prepared:
                try:
                    winmm.waveInUnprepareHeader(handle, ctypes.byref(header), size)
                except Exception:
                    pass
            try:
                winmm.waveInClose(handle)
            except Exception:
                pass
