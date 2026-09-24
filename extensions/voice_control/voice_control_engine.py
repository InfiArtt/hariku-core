# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Speech recognition with whisper.cpp's whisper-server (blocking; no wx).

whisper-server loads a model once and keeps it loaded, answering on
127.0.0.1 only: a short command then takes about 1.6 s with the tiny model
on an i5-4300U, where starting the program for every command would first
spend the loading time again. One server runs per model in use. It starts on
the first listen, runs at below-normal priority without a window, is tied to
Hariku (a Windows job object ends it if Hariku ends) and stops after
IDLE_SECONDS without use.

The recording goes to the server over that local connection as a WAV file in
memory; nothing is written to disk and nothing leaves the computer.

Measured on an i5-4300U (2 cores, 4 threads, 8 GB), server kept running, four
threads, Indonesian, with a vocabulary prompt:
    tiny   about 1.6 s per short command, 176 MB of memory
    base   about 4.8 s, 284 MB
    small  about 17.8 s, 661 MB, and 21 s to load
So "Automatic" uses the most accurate model that answers a command within
BUDGETS["command"] (tiny there), and listens again with the most accurate one
within BUDGETS["reminder"] (base) when the words look like a reminder. The
speed of each model is measured once, the first time it is used, and kept.
"""
import ctypes
import ctypes.wintypes
import http.client
import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
import uuid

logger = logging.getLogger(__name__)

MODELS = ("tiny", "base", "small")                 # fastest (least accurate) first
DEFAULT_SECONDS = {"tiny": 1.6, "base": 4.8, "small": 17.8}
BUDGETS = {"command": 2.5, "reminder": 8.0}        # seconds a person will wait
LOAD_TIMEOUT = {"tiny": 30.0, "base": 45.0, "small": 120.0}
REQUEST_TIMEOUT = {"tiny": 30.0, "base": 60.0, "small": 180.0}
IDLE_SECONDS = 300.0                               # stop a server unused this long
IDLE_CHECK_SECONDS = 15.0
MAX_PROMPT_CHARS = 400
HOST = "127.0.0.1"
LANGUAGES = {"id", "en", "de", "nl", "fr", "es", "it", "pt", "ms", "ja", "ko", "zh", "ar"}

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
BELOW_NORMAL_PRIORITY_CLASS = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x00004000)


class EngineError(Exception):
    """kind: "missing" (program or model not installed), "start" (the server
    didn't start), "timeout", "http" or "bad_data"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = str(detail or "")


# ------------------------------------------------------------
# Choosing a model
# ------------------------------------------------------------

def seconds_for(model, speeds=None):
    """A model's measured seconds per short command, or the i5-4300U's."""
    speeds = speeds or {}
    value = speeds.get(model)
    return float(value) if isinstance(value, (int, float)) and value > 0 else DEFAULT_SECONDS[model]


def choose_model(setting, installed, speeds=None, purpose="command"):
    """The model to recognise with. `setting` is "auto" or a model name; a
    chosen model is used when installed. Automatic, or a chosen model that
    isn't installed: the most accurate installed model within
    BUDGETS[purpose], else the fastest installed. None when none is."""
    installed = [m for m in MODELS if m in set(installed or ())]
    if not installed:
        return None
    if setting in installed:
        return setting
    budget = BUDGETS.get(purpose, BUDGETS["command"])
    fitting = [m for m in installed if seconds_for(m, speeds) <= budget]
    if fitting:
        return fitting[-1]
    return min(installed, key=lambda m: seconds_for(m, speeds))


def reminder_model(setting, installed, speeds, used):
    """The model to listen again with when a command looks like a reminder,
    or None: only with "auto", and only a more accurate installed model than
    `used` that fits the reminder budget."""
    if setting != "auto" or used is None:
        return None
    better = choose_model("auto", installed, speeds, "reminder")
    if better is None or MODELS.index(better) <= MODELS.index(used):
        return None
    return better


def whisper_language(code):
    """Whisper's language for Hariku's ("id" for Indonesian), else "auto"."""
    code = str(code or "").split("-")[0].lower()
    return code if code in LANGUAGES else "auto"


def threads(cpu_count=None):
    """Four threads (measured best on 2 cores / 4 threads), fewer on smaller CPUs."""
    cpu_count = cpu_count or os.cpu_count() or 2
    return max(1, min(4, cpu_count))


def build_prompt(phrases, max_chars=MAX_PROMPT_CHARS):
    """A vocabulary prompt from command names and aliases: it makes whisper
    expect these words. Short phrases first, no duplicates, at most
    `max_chars`."""
    seen, picked, length = set(), [], 0
    for phrase in sorted((" ".join(str(p).split()) for p in phrases),
                         key=lambda p: (len(p), p.casefold())):
        key = phrase.casefold()
        if not phrase or key in seen or len(phrase) > 60:
            continue
        added = len(phrase) + (2 if picked else 0)
        if length + added > max_chars:
            continue
        seen.add(key)
        picked.append(phrase)
        length += added
    return ", ".join(picked) + ("." if picked else "")


_TAG_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*|♪+")


def clean_text(text):
    """What whisper heard, without its tags ("[BLANK_AUDIO]", "(musik)")."""
    return " ".join(_TAG_RE.sub(" ", str(text or "")).split()).strip()


# ------------------------------------------------------------
# Ending the server with Hariku (a job object)
# ------------------------------------------------------------

class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.wintypes.DWORD),
                ("SchedulingClass", ctypes.wintypes.DWORD)]


class _EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BASIC_LIMIT), ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


def tie_to_hariku(process):
    """Put the server in a job that Windows ends when Hariku's handle to it
    closes (Hariku quits or crashes), so no server is left running. Returns
    the job handle (keep it), or None when that isn't possible."""
    handle = getattr(process, "_handle", None)
    if handle is None:
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.CreateJobObjectW.restype = ctypes.wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.SetInformationJobObject.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_int,
                                                     ctypes.POINTER(_EXTENDED_LIMIT),
                                                     ctypes.wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = ctypes.wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.wintypes.HANDLE,
                                                      ctypes.wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = ctypes.wintypes.BOOL
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                                ctypes.byref(info), ctypes.sizeof(info)) or \
                not kernel32.AssignProcessToJobObject(job, int(handle)):
            kernel32.CloseHandle(job)
            return None
        return job
    except Exception:
        logger.debug("Voice Control: could not tie whisper-server to Hariku", exc_info=True)
        return None


def _close_handle(handle):
    if handle:
        try:
            ctypes.WinDLL("kernel32").CloseHandle(ctypes.wintypes.HANDLE(handle))
        except Exception:
            pass


# ------------------------------------------------------------
# One whisper-server
# ------------------------------------------------------------

def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _hidden_startupinfo():
    startupinfo_class = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_class is None:
        return None
    info = startupinfo_class()
    info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
    info.wShowWindow = 0      # SW_HIDE
    return info


def _can_connect(port):
    try:
        with socket.create_connection((HOST, port), timeout=0.5):
            return True
    except OSError:
        return False


def multipart(fields, file_field, filename, data, content_type="audio/wav"):
    """(content type, body) of a multipart/form-data request."""
    boundary = "hariku-" + uuid.uuid4().hex
    body = []
    for name, value in fields.items():
        body.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                     f"{value}\r\n").encode("utf-8"))
    body.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
                 f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n")
                .encode("utf-8") + bytes(data) + b"\r\n")
    body.append(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", b"".join(body)


def build_command(exe, model_path, port, language, prompt, thread_count):
    command = [exe, "-m", model_path, "--host", HOST, "--port", str(port),
               "-t", str(thread_count), "-l", language]
    if prompt:
        command += ["--prompt", prompt]
    return command


class Server:
    """whisper-server with one model. `popen`, `can_connect`, `post` and
    `clock` can be replaced for tests."""

    def __init__(self, model, exe, model_path, language="id", prompt="", thread_count=None,
                 log_path=None, popen=None, can_connect=None, post=None, clock=None,
                 sleep=None):
        self.model = model
        self.exe = exe
        self.model_path = model_path
        self.language = language
        self.prompt = prompt
        self.thread_count = thread_count or threads()
        self.log_path = log_path
        self._popen = popen or subprocess.Popen
        self._can_connect = can_connect or _can_connect
        self._post = post or self._http_post
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self.process = None
        self.port = None
        self._job = None
        self.last_used = self._clock()
        self.lock = threading.Lock()

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        """Start the server and wait until it answers; EngineError otherwise."""
        if self.running:
            return
        if not os.path.isfile(self.exe):
            raise EngineError("missing", self.exe)
        if not os.path.isfile(self.model_path):
            raise EngineError("missing", self.model_path)
        self.port = free_port()
        command = build_command(self.exe, self.model_path, self.port, self.language,
                                self.prompt, self.thread_count)
        log = None
        if self.log_path:
            try:
                log = open(self.log_path, "wb")     # only the last run's messages
            except OSError:
                log = None
        try:
            self.process = self._popen(
                command, stdin=subprocess.DEVNULL, stdout=log or subprocess.DEVNULL,
                stderr=log or subprocess.DEVNULL, cwd=os.path.dirname(self.exe),
                creationflags=CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS,
                startupinfo=_hidden_startupinfo())
        except OSError as e:
            raise EngineError("start", f"whisper-server could not start: {e}") from None
        finally:
            if log is not None:
                log.close()
        self._job = tie_to_hariku(self.process)
        deadline = self._clock() + LOAD_TIMEOUT.get(self.model, 60.0)
        while True:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.stop()
                raise EngineError("start", f"whisper-server ended (code {code})")
            if self._can_connect(self.port):
                break
            if self._clock() > deadline:
                self.stop()
                raise EngineError("timeout", "whisper-server took too long to load the model")
            self._sleep(0.1)
        self.last_used = self._clock()
        logger.info(f"Voice Control: whisper-server with {self.model} is ready on port "
                    f"{self.port}.")

    def transcribe(self, wav, prompt=None, language=None):
        """The text in a WAV recording (bytes). Starts the server if needed."""
        with self.lock:
            self.start()
            self.last_used = self._clock()
            fields = {"response_format": "json", "temperature": "0.0",
                      "language": language or self.language}
            if prompt or self.prompt:
                fields["prompt"] = prompt or self.prompt
            try:
                status, body = self._post(self.port, fields, wav,
                                          REQUEST_TIMEOUT.get(self.model, 60.0))
            finally:
                self.last_used = self._clock()
        if status == 503:
            raise EngineError("http", "503 (still loading)")
        if status != 200:
            raise EngineError("http", str(status))
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            raise EngineError("bad_data", "not JSON") from None
        if not isinstance(data, dict) or ("error" in data and "text" not in data):
            raise EngineError("bad_data", str(data)[:200])
        return clean_text(data.get("text", ""))

    @staticmethod
    def _http_post(port, fields, wav, timeout):
        content_type, body = multipart(fields, "file", "speech.wav", wav)
        connection = http.client.HTTPConnection(HOST, port, timeout=timeout)
        try:
            connection.request("POST", "/inference", body=body,
                               headers={"Content-Type": content_type})
            response = connection.getresponse()
            return response.status, response.read()
        except socket.timeout:
            raise EngineError("timeout", "whisper-server did not answer in time") from None
        except (OSError, http.client.HTTPException) as e:
            raise EngineError("http", str(e)) from None
        finally:
            connection.close()

    def stop(self):
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        job, self._job = self._job, None
        _close_handle(job)


# ------------------------------------------------------------
# The servers in use
# ------------------------------------------------------------

class Engine:
    """Keeps a server per model while it is used and stops the idle ones.
    `make_server(model)` returns a Server (main.py knows the paths)."""

    def __init__(self, make_server, clock=None, idle_seconds=IDLE_SECONDS,
                 check_seconds=IDLE_CHECK_SECONDS, watch=True):
        self._make_server = make_server
        self._clock = clock or time.monotonic
        self.idle_seconds = idle_seconds
        self.check_seconds = check_seconds
        self._watch = watch
        self._servers = {}
        self._lock = threading.Lock()
        self._watcher = None
        self._stopping = threading.Event()

    def restart(self):
        """After shutdown(): usable again (the extension was reloaded)."""
        self._stopping.clear()

    def server(self, model):
        with self._lock:
            server = self._servers.get(model)
            if server is None:
                server = self._make_server(model)
                self._servers[model] = server
            self._ensure_watcher()
            return server

    def warm_up(self, model):
        """Start a model's server now (while the user is still speaking)."""
        server = self.server(model)
        try:
            with server.lock:
                server.start()
        except EngineError as e:
            logger.info(f"Voice Control: warming up {model} failed: {e}")

    def transcribe(self, model, wav, prompt=None, language=None):
        """(text, seconds the recognition took)."""
        server = self.server(model)
        started = self._clock()
        text = server.transcribe(wav, prompt=prompt, language=language)
        return text, self._clock() - started

    def running_models(self):
        with self._lock:
            return [m for m, s in self._servers.items() if s.running]

    def stop_idle(self, now=None):
        """Stop the servers unused for idle_seconds; returns their models."""
        now = self._clock() if now is None else now
        stopped = []
        with self._lock:
            servers = list(self._servers.items())
        for model, server in servers:
            if not server.running:
                continue
            if server.lock.acquire(blocking=False):
                try:
                    if now - server.last_used >= self.idle_seconds:
                        server.stop()
                        stopped.append(model)
                finally:
                    server.lock.release()
        if stopped:
            logger.info(f"Voice Control: stopped idle whisper-server ({', '.join(stopped)}).")
        return stopped

    def stop_all(self):
        with self._lock:
            servers = list(self._servers.values())
            self._servers.clear()
        for server in servers:
            server.stop()

    def shutdown(self):
        self._stopping.set()
        self.stop_all()

    def _ensure_watcher(self):
        """One thread checks for idle servers every check_seconds, from the
        first use until shutdown() (it only wakes up; no work while idle)."""
        if not self._watch or self._stopping.is_set():
            return
        if self._watcher is None or not self._watcher.is_alive():
            self._watcher = threading.Thread(target=self._watch_idle, daemon=True,
                                             name="hariku-voice-control-idle")
            self._watcher.start()

    def _watch_idle(self):
        while not self._stopping.wait(self.check_seconds):
            try:
                self.stop_idle()
            except Exception:
                logger.exception("Voice Control: stopping an idle whisper-server failed")
