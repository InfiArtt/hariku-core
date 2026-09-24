# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Running Piper and keeping what it said (blocking; no wx, no network).

PiperProcess keeps one piper.exe running with the voice model loaded
(--json-input): each sentence is one line of JSON on its standard input, and
Piper prints the WAV file's path once it has written it. Loading the model
takes one to three seconds on an older laptop, so a new piper.exe for every
text made each answer wait that long, like an online voice.
synthesize() is the one-off way (a new piper.exe loads the model, says the
text and exits), used when the kept process can't start or fails. Neither
ever gets a console window (CREATE_NO_WINDOW, hidden), and both are killed
when they take too long.

split_sentences() cuts a text into sentences, so the first one plays while
Piper makes the next.

The WAV files are kept in %APPDATA%\\Hariku2\\voice_cache\\piper, named by a
hash of the voice, the speed and the text, so a phrase said again (the
greeting) plays at once. Least recently used files go first once the folder is
over 30 MB, like Edge Voices' cache.
"""
import collections
import hashlib
import itertools
import json
import os
import queue
import re
import subprocess
import threading
import time
import wave

RATE_MIN, RATE_MAX = -10, 10
SLOWEST_LENGTH_SCALE = 1.6      # rate -10
FASTEST_LENGTH_SCALE = 0.6      # rate 10
MIN_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 600.0
AUDIO_SUFFIX = ".wav"
DEFAULT_LIMIT_BYTES = 30 * 1024 * 1024
STALE_TEMPORARY_SECONDS = 3600
CANCEL_GRACE_SECONDS = 3.0      # a stopped sentence may finish; after that Piper is killed
MAX_SENTENCE_CHARS = 220
MIN_SENTENCE_CHARS = 8

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_SW_HIDE = 0
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Spaces after ".", "!", "?" or "…", or after one of those and a closing quote
# or bracket. "2.8" and "31,5" have no space, so they stay whole.
_SENTENCE_END_RE = re.compile(
    r"(?<=[.!?…])\s+|(?<=[.!?…][\"'”’)\]])\s+")
_CLAUSE_END_RE = re.compile(r"(?<=[,;:])\s+")
_serial = itertools.count(1)


class PiperError(Exception):
    """Piper could not speak the text."""


def _clamp_rate(rate):
    try:
        rate = int(rate)
    except (TypeError, ValueError):
        rate = 0
    return max(RATE_MIN, min(RATE_MAX, rate))


def length_scale(rate):
    """Hariku's rate -10..10 as Piper's --length_scale: 1.6 (slowest) to 0.6
    (fastest), 1.0 at 0. Longer sounds mean slower speech."""
    rate = _clamp_rate(rate)
    if rate < 0:
        scale = 1.0 + (SLOWEST_LENGTH_SCALE - 1.0) * (-rate / RATE_MAX)
    else:
        scale = 1.0 - (1.0 - FASTEST_LENGTH_SCALE) * (rate / RATE_MAX)
    return round(scale, 2)


def length_scale_text(rate):
    return f"{length_scale(rate):.2f}"


def prepare_text(text):
    """One line of text: Piper reads its input line by line."""
    return " ".join(_CONTROL_RE.sub(" ", str(text or "")).split())


def _split_long(sentence, limit):
    """A sentence over `limit` characters in pieces: at the last comma,
    semicolon or colon that fits, else at the last space."""
    pieces = []
    while len(sentence) > limit:
        cut = -1
        for match in _CLAUSE_END_RE.finditer(sentence, 0, limit + 1):
            cut = match.start()
        if cut < limit // 3:
            cut = sentence.rfind(" ", 0, limit + 1)
        if cut <= 0:
            cut = limit
        pieces.append(sentence[:cut].strip())
        sentence = sentence[cut:].strip()
    if sentence:
        pieces.append(sentence)
    return pieces


def split_sentences(text, limit=MAX_SENTENCE_CHARS):
    """The text as sentences, each on one line, in order. A line is a sentence
    too, a long sentence is split, and a piece shorter than MIN_SENTENCE_CHARS
    joins the next. [] when there is nothing to say."""
    pieces = []
    for line in str(text or "").splitlines():
        for sentence in _SENTENCE_END_RE.split(prepare_text(line)):
            pieces.extend(_split_long(sentence.strip(), limit))
    merged, carry = [], ""
    for piece in pieces:
        if not piece:
            continue
        piece = f"{carry} {piece}" if carry else piece
        if len(piece) < MIN_SENTENCE_CHARS:
            carry = piece
        else:
            merged.append(piece)
            carry = ""
    if carry:
        if merged:
            merged[-1] = f"{merged[-1]} {carry}"
        else:
            merged.append(carry)
    return merged


def build_command(exe, model, output, rate):
    """The piper.exe command line; the text goes to its standard input."""
    return [exe, "--model", model, "--output_file", output,
            "--length_scale", length_scale_text(rate)]


def timeout_for(text):
    """Generous: loading the model, then about a fifth of real time."""
    return max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, 20.0 + len(text) * 0.1))


def _hidden_startupinfo():
    startupinfo_class = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_class is None:
        return None
    info = startupinfo_class()
    info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
    info.wShowWindow = _SW_HIDE
    return info


def kill(process):
    try:
        process.kill()
    except (OSError, AttributeError):
        pass


def synthesize(exe, model, output, text, rate=0, on_process=None, timeout=None,
               popen=None):
    """Make `output` (a WAV file) with Piper saying `text`. `on_process(process)`
    receives the running process so another thread can kill it. Raises
    PiperError when Piper fails, times out or is killed."""
    text = prepare_text(text)
    if not text:
        raise PiperError("nothing to say")
    popen = popen or subprocess.Popen
    command = build_command(exe, model, output, rate)
    try:
        process = popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, cwd=os.path.dirname(exe),
                        creationflags=CREATE_NO_WINDOW, startupinfo=_hidden_startupinfo())
    except OSError as e:
        raise PiperError(f"piper.exe could not start: {e}") from None
    if on_process is not None:
        on_process(process)
    try:
        _out, err = process.communicate((text + "\n").encode("utf-8"),
                                        timeout=timeout or timeout_for(text))
    except subprocess.TimeoutExpired:
        kill(process)
        try:
            process.communicate(timeout=5)
        except Exception:
            pass
        raise PiperError("Piper took too long") from None
    if process.returncode != 0:
        raise PiperError(_last_line(err) or f"piper.exe exited with code {process.returncode}")
    check_wav(output)
    return output


class PiperProcess:
    """One piper.exe kept running with a voice model loaded, at one speed.
    synthesize() is called by one thread at a time (the speaking worker);
    close() by any."""

    def __init__(self, exe, model, rate, output_dir, popen=None):
        self.key = (exe, model, length_scale_text(rate))
        self._lines = queue.Queue()
        self._errors = collections.deque(maxlen=20)
        popen = popen or subprocess.Popen
        command = [exe, "--model", model, "--json-input", "--output_dir", output_dir,
                   "--length_scale", length_scale_text(rate)]
        try:
            self._process = popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, cwd=os.path.dirname(exe),
                                  creationflags=CREATE_NO_WINDOW,
                                  startupinfo=_hidden_startupinfo())
        except OSError as e:
            raise PiperError(f"piper.exe could not start: {e}") from None
        self.last_used = time.monotonic()
        for target, name in ((self._read_stdout, "out"), (self._read_stderr, "err")):
            threading.Thread(target=target, daemon=True, name=f"hariku-piper-{name}").start()

    def _read_stdout(self):
        try:
            for line in self._process.stdout:
                self._lines.put(line.decode("utf-8", "replace").strip())
        except (OSError, ValueError):
            pass
        self._lines.put(None)

    def _read_stderr(self):
        try:
            for line in self._process.stderr:
                self._errors.append(line.decode("utf-8", "replace").strip())
        except (OSError, ValueError):
            pass

    def alive(self):
        return self._process.poll() is None

    def _failure(self, fallback):
        lines = [l for l in self._errors if "error" in l.lower()]
        return PiperError(lines[-1][:300] if lines else fallback)

    def synthesize(self, text, output, cancelled=None, timeout=None):
        """Make `output` (a WAV file) with the loaded voice saying `text`. Once
        `cancelled()` is true the sentence may finish for CANCEL_GRACE_SECONDS,
        then Piper is killed. Raises PiperError when Piper fails, stops or
        takes too long."""
        text = prepare_text(text)
        if not text:
            raise PiperError("nothing to say")
        while not self._lines.empty():           # nothing should be left over; be sure
            if self._lines.get_nowait() is None:
                self.close()
                raise self._failure("Piper stopped")
        request = json.dumps({"text": text, "output_file": output}) + "\n"
        try:
            self._process.stdin.write(request.encode("utf-8"))
            self._process.stdin.flush()
        except (OSError, ValueError, AttributeError):
            self.close()
            raise self._failure("Piper stopped") from None
        deadline = time.monotonic() + (timeout or timeout_for(text))
        cancel_seen = False
        while True:
            if cancelled is not None and not cancel_seen and cancelled():
                cancel_seen = True
                deadline = min(deadline, time.monotonic() + CANCEL_GRACE_SECONDS)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close()
                raise PiperError("Piper was stopped" if cancel_seen else "Piper took too long")
            try:
                line = self._lines.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            if line is None:
                self.close()
                raise self._failure("Piper stopped")
            if line:                              # the path of the file it wrote
                break
        check_wav(output)
        self.last_used = time.monotonic()
        return output

    def close(self):
        process = getattr(self, "_process", None)
        if process is None:
            return
        try:
            process.stdin.close()
        except (OSError, ValueError, AttributeError):
            pass
        kill(process)


def _last_line(data):
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    lines = [l.strip() for l in str(data or "").splitlines() if l.strip()]
    return lines[-1][:300] if lines else ""


def wav_duration(path):
    """Seconds of audio in a WAV file; raises PiperError when it isn't one."""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise PiperError("Piper did not write a WAV file")
        with wave.open(path, "rb") as w:
            frames, rate = w.getnframes(), w.getframerate()
    except (OSError, EOFError, wave.Error) as e:
        raise PiperError(f"Piper's WAV file can't be read: {e}") from None
    if frames <= 0 or rate <= 0:
        raise PiperError("Piper wrote no audio")
    return frames / float(rate)


def check_wav(path):
    wav_duration(path)
    return path


def remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


class AudioCache:
    """WAV files named by a hash; least recently used first out."""

    def __init__(self, directory, limit_bytes=DEFAULT_LIMIT_BYTES):
        self.directory = directory
        self.limit_bytes = limit_bytes

    @staticmethod
    def key(voice, scale, text):
        blob = json.dumps([voice, str(scale), prepare_text(text)], ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def path(self, key):
        return os.path.join(self.directory, key + AUDIO_SUFFIX)

    def temporary_path(self, key):
        """Where Piper writes before the file is checked and renamed."""
        os.makedirs(self.directory, exist_ok=True)
        return os.path.join(self.directory, f"{key}.{os.getpid()}.{next(_serial)}.tmp")

    def get(self, key):
        """The cached file for `key`, marked as just used; None if absent."""
        path = self.path(key)
        try:
            if os.path.getsize(path) <= 44:
                return None
        except OSError:
            return None
        try:
            os.utime(path, None)
        except OSError:
            pass
        return path

    def put_file(self, key, temporary):
        """Check the WAV Piper wrote, move it into place, trim the cache."""
        try:
            check_wav(temporary)
            path = self.path(key)
            os.replace(temporary, path)
        except BaseException:
            remove_quietly(temporary)
            raise
        self.evict(keep=path)
        return path

    def entries(self):
        """[(last used, size, path)] of the cached audio, oldest first."""
        found = []
        try:
            names = os.listdir(self.directory)
        except OSError:
            return found
        for name in names:
            if not name.endswith(AUDIO_SUFFIX):
                continue
            path = os.path.join(self.directory, name)
            try:
                info = os.stat(path)
            except OSError:
                continue
            found.append((info.st_mtime, info.st_size, path))
        found.sort()
        return found

    def size(self):
        return sum(size for _mtime, size, _path in self.entries())

    def remove_stale_temporaries(self, max_age=STALE_TEMPORARY_SECONDS, now=None):
        """Remove what Piper was writing when Hariku stopped (a crash)."""
        now = time.time() if now is None else now
        try:
            names = os.listdir(self.directory)
        except OSError:
            return
        for name in names:
            if name.endswith(".tmp"):
                path = os.path.join(self.directory, name)
                try:
                    if now - os.path.getmtime(path) > max_age:
                        os.remove(path)
                except OSError:
                    pass

    def evict(self, keep=None):
        """Remove the least recently used files until the cache fits its limit.
        `keep` (the file about to play) and files in use are left alone."""
        self.remove_stale_temporaries()
        entries = self.entries()
        total = sum(size for _mtime, size, _path in entries)
        for _mtime, size, path in entries:
            if total <= self.limit_bytes:
                break
            if keep and os.path.normcase(path) == os.path.normcase(keep):
                continue
            try:
                os.remove(path)
                total -= size
            except OSError:
                pass        # playing right now; it goes next time
        return total
