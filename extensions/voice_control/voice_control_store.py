# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Voice Control's files and settings (no network, no wx), in
%APPDATA%\\Hariku2\\voice_control:

  runtime\\                  whisper.cpp, unpacked from the pinned release;
  runtime\\runtime.json      written last, it marks the program as installed
  models\\ggml-<name>.bin    a speech model, with <file>.json next to it once
                            its SHA-256 matched
  downloads\\                the whisper.cpp zip or the wake phrase archives
                            while they download
  server.log                what whisper-server printed last time it ran
  wake\\runtime\\             sherpa-onnx's C API DLL and ONNX Runtime (the
                            wake phrase listener)
  wake\\model\\               the English keyword model: tokens.txt, bpe.model
                            and the encoder, decoder and joiner (int8)
  wake\\wake.json            written last, it marks them as installed

A file being downloaded is "<name>.part" next to where it goes. No recording
is ever stored here (or anywhere). The settings are Hariku data
("VoiceControl"): the model choice, listening on open, the silence length, the
microphone sensitivity, each model's measured speed, and the wake phrase:
whether to listen for it, the phrase, its sensitivity and whether to pause it
during quiet hours.
"""
import json
import os
import shutil

import core.api

import voice_control_audio as audio
import voice_control_wake as wake

ROOT_NAME = "voice_control"
RUNTIME_DIR = "runtime"
RUNTIME_MARKER = "runtime.json"
SERVER_EXE = "whisper-server.exe"
DEFAULT_EXE = ("Release", SERVER_EXE)
MODELS_DIR = "models"
DOWNLOADS_DIR = "downloads"
LOG_FILE = "server.log"
PART_SUFFIX = ".part"
MODEL_NAMES = ("tiny", "base", "small")
WAKE_DIR = "wake"
WAKE_MARKER = "wake.json"
WAKE_PARTS = {"tokens": ("model", "tokens.txt"), "bpe": ("model", "bpe.model"),
              "encoder": ("model", "encoder.int8.onnx"),
              "decoder": ("model", "decoder.int8.onnx"),
              "joiner": ("model", "joiner.int8.onnx")}

SETTINGS_NAME = "VoiceControl"
MODEL_CHOICES = ("auto",) + MODEL_NAMES
SILENCE_CHOICES = (600, 800, 1000, 1500, 2000)    # milliseconds
SENSITIVITY_CHOICES = audio.SENSITIVITIES           # least sensitive first
WAKE_SENSITIVITY_CHOICES = wake.SENSITIVITIES       # least sensitive first
DEFAULT_SETTINGS = {"model": "auto", "listen_on_open": True, "silence_ms": 1000,
                    "sensitivity": audio.DEFAULT_SENSITIVITY, "speeds": {},
                    "wake": False, "wake_phrase": wake.DEFAULT_PHRASE,
                    "wake_sensitivity": wake.DEFAULT_SENSITIVITY, "wake_quiet_hours": False}


def root_dir():
    """%APPDATA%\\Hariku2\\voice_control (not created here)."""
    return os.path.join(core.api.USER_DATA_DIR, ROOT_NAME)


def runtime_dir(root):
    return os.path.join(root, RUNTIME_DIR)


def downloads_dir(root):
    return os.path.join(root, DOWNLOADS_DIR)


def models_dir(root):
    return os.path.join(root, MODELS_DIR)


def log_path(root):
    return os.path.join(root, LOG_FILE)


def model_file(name):
    if name not in MODEL_NAMES:
        raise ValueError(f"unknown model: {name!r}")
    return f"ggml-{name}.bin"


def model_path(root, name):
    return os.path.join(models_dir(root), model_file(name))


def _marker_path(root, name):
    return model_path(root, name) + ".json"


# ------------------------------------------------------------
# Writing
# ------------------------------------------------------------

def write_atomically(path, data):
    """Write bytes to a temporary file next to `path`, then rename it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temporary, "wb") as f:
            f.write(data)
        os.replace(temporary, path)
    except BaseException:
        remove_quietly(temporary)
        raise


def write_json(path, data):
    write_atomically(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


# ------------------------------------------------------------
# The program
# ------------------------------------------------------------

def find_server_exe(folder):
    """whisper-server.exe in an unpacked release: Release\\ first, else the
    first one found at most three folders down. None when there is none."""
    expected = os.path.join(folder, *DEFAULT_EXE)
    if os.path.isfile(expected):
        return expected
    base_depth = folder.rstrip("\\/").count(os.sep)
    for dirpath, dirs, files in os.walk(folder):
        if dirpath.count(os.sep) - base_depth >= 3:
            dirs[:] = []
        for name in files:
            if name.lower() == SERVER_EXE:
                return os.path.join(dirpath, name)
    return None


def write_runtime_marker(root, info):
    write_json(os.path.join(runtime_dir(root), RUNTIME_MARKER), dict(info))


def server_exe(root):
    """Where whisper-server.exe is (the path the marker recorded)."""
    marker = read_json(os.path.join(runtime_dir(root), RUNTIME_MARKER))
    relative = marker.get("exe") if isinstance(marker, dict) else None
    if isinstance(relative, str) and relative and ".." not in relative.replace("\\", "/").split("/"):
        return os.path.join(runtime_dir(root), relative)
    return os.path.join(runtime_dir(root), *DEFAULT_EXE)


def runtime_installed(root):
    return (os.path.isfile(os.path.join(runtime_dir(root), RUNTIME_MARKER))
            and os.path.isfile(server_exe(root)))


def remove_runtime(root):
    """Delete the program; the marker goes first, so a program that can't be
    removed completely (a file in use) is no longer counted as installed."""
    folder = runtime_dir(root)
    if not os.path.isdir(folder):
        return False
    remove_quietly(os.path.join(folder, RUNTIME_MARKER))
    shutil.rmtree(folder)
    return True


# ------------------------------------------------------------
# Models
# ------------------------------------------------------------

def write_model_marker(root, name, size, sha256):
    write_json(_marker_path(root, name), {"model": name, "size": int(size), "sha256": sha256})


def model_installed(root, name):
    """A model counts once its SHA-256 matched (its marker) and its file is
    still there, with the same size."""
    marker = read_json(_marker_path(root, name))
    if not isinstance(marker, dict) or marker.get("model") != name:
        return False
    try:
        return os.path.getsize(model_path(root, name)) == marker.get("size")
    except OSError:
        return False


def installed_models(root):
    return [name for name in MODEL_NAMES if model_installed(root, name)]


def remove_model(root, name):
    marker = _marker_path(root, name)
    path = model_path(root, name)
    if not os.path.exists(path) and not os.path.exists(marker):
        return False
    remove_quietly(marker)
    if os.path.exists(path):
        os.remove(path)
    return True


def cleanup_partials(root):
    """Remove half-unpacked programs, a wake phrase listener that was removed
    while Hariku still had it loaded, and temporary files left by a crash
    (unfinished downloads are kept, to be continued)."""
    for staging in (runtime_dir(root) + ".new", wake_dir(root) + ".new"):
        if os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)
    if os.path.isdir(wake_dir(root)) and not os.path.isfile(_wake_marker(root)):
        shutil.rmtree(wake_dir(root), ignore_errors=True)
    for folder in (models_dir(root), downloads_dir(root)):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            if name.endswith(".tmp"):
                remove_quietly(os.path.join(folder, name))


# ------------------------------------------------------------
# The wake phrase listener
# ------------------------------------------------------------

def wake_dir(root):
    return os.path.join(root, WAKE_DIR)


def wake_runtime_dir(root):
    return os.path.join(wake_dir(root), "runtime")


def _wake_marker(root):
    return os.path.join(wake_dir(root), WAKE_MARKER)


def wake_files(root):
    """{"tokens", "bpe", "encoder", "decoder", "joiner"}: the model's files."""
    return {key: os.path.join(wake_dir(root), *parts) for key, parts in WAKE_PARTS.items()}


def wake_installed(root):
    """The wake phrase listener counts once its marker was written (after
    every file matched its SHA-256) and each file is still there, with the
    size the marker recorded."""
    marker = read_json(_wake_marker(root))
    files = marker.get("files") if isinstance(marker, dict) else None
    if not isinstance(files, dict) or not files:
        return False
    for relative, info in files.items():
        if (not isinstance(relative, str) or ".." in relative.replace("\\", "/").split("/")
                or not isinstance(info, dict)):
            return False
        try:
            if os.path.getsize(os.path.join(wake_dir(root), *relative.split("/"))) != \
                    info.get("size"):
                return False
        except OSError:
            return False
    return True


def remove_wake(root):
    """Delete the wake phrase listener. The marker goes first, so files
    Windows keeps (a DLL Hariku has loaded can't be deleted until Hariku
    closes) no longer count as installed; cleanup_partials() removes them at
    the next start. Returns (removed anything, removed everything)."""
    folder = wake_dir(root)
    if not os.path.isdir(folder):
        return False, True
    remove_quietly(_wake_marker(root))
    shutil.rmtree(folder, ignore_errors=True)
    return True, not os.path.exists(folder)


# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------

def normalize_settings(raw):
    """The settings with every value checked; a missing or unknown one gets
    its default (settings saved before the sensitivity existed get Normal,
    before the wake phrase existed, the wake phrase off)."""
    raw = raw if isinstance(raw, dict) else {}
    model = raw.get("model")
    silence = raw.get("silence_ms")
    sensitivity = raw.get("sensitivity")
    speeds = raw.get("speeds") if isinstance(raw.get("speeds"), dict) else {}
    clean_speeds = {}
    for name in MODEL_NAMES:
        value = speeds.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 600:
            clean_speeds[name] = round(float(value), 2)
    phrase = raw.get("wake_phrase")
    phrase = wake.tidy(phrase) if isinstance(phrase, str) else ""
    wake_sensitivity = raw.get("wake_sensitivity")
    return {
        "model": model if model in MODEL_CHOICES else DEFAULT_SETTINGS["model"],
        "listen_on_open": bool(raw.get("listen_on_open", DEFAULT_SETTINGS["listen_on_open"])),
        "silence_ms": silence if silence in SILENCE_CHOICES else DEFAULT_SETTINGS["silence_ms"],
        "sensitivity": sensitivity if isinstance(sensitivity, str)
        and sensitivity in SENSITIVITY_CHOICES else DEFAULT_SETTINGS["sensitivity"],
        "speeds": clean_speeds,
        "wake": raw.get("wake") is True,
        "wake_phrase": phrase or DEFAULT_SETTINGS["wake_phrase"],
        "wake_sensitivity": wake_sensitivity if isinstance(wake_sensitivity, str)
        and wake_sensitivity in WAKE_SENSITIVITY_CHOICES else DEFAULT_SETTINGS["wake_sensitivity"],
        "wake_quiet_hours": raw.get("wake_quiet_hours") is True,
    }


def load_settings():
    return normalize_settings(core.api.load_data(SETTINGS_NAME))


def save_settings(settings):
    return core.api.save_data(SETTINGS_NAME, normalize_settings(settings))


def record_speed(name, seconds, settings=None):
    """Keep a model's measured speed (seconds for a short command) the first
    time it is measured. Returns the settings as saved."""
    settings = load_settings() if settings is None else settings
    if name in MODEL_NAMES and name not in settings["speeds"] and seconds > 0:
        settings["speeds"][name] = round(float(seconds), 2)
        save_settings(settings)
    return settings


def forget_speed(name):
    settings = load_settings()
    if settings["speeds"].pop(name, None) is not None:
        save_settings(settings)
