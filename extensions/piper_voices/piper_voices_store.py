# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Piper Voices' files (no network, no wx), all in %APPDATA%\\Hariku2\\piper:

  runtime\\piper\\piper.exe   the Piper program with its libraries and
  runtime\\runtime.json       espeak-ng data, unpacked from the pinned release
  voices\\<key>\\             one folder per voice: <key>.onnx, <key>.onnx.json,
                             MODEL_CARD, and voice.json, written last, which
                             marks the voice as installed
  downloads\\                the Piper zip while it downloads
  catalogue.json            the voice index, used for 7 days (longer offline)

A file being downloaded is "<name>.part" next to where it goes; it is renamed
once its checksum matches. Parts left for more than 7 days are removed.
Synthesized speech is not here but in voice_cache\\piper (core.voice.cache_dir).
"""
import json
import os
import shutil
import time

import core.api

import piper_voices_catalogue as catalogue

ROOT_NAME = "piper"
RUNTIME_DIR = "runtime"
RUNTIME_EXE = ("piper", "piper.exe")
RUNTIME_MARKER = "runtime.json"
VOICES_DIR = "voices"
VOICE_MARKER = "voice.json"
CARD_FILE = "MODEL_CARD"
DOWNLOADS_DIR = "downloads"
CATALOGUE_FILE = "catalogue.json"
PART_SUFFIX = ".part"
STALE_PART_SECONDS = 7 * 24 * 3600


def root_dir():
    """%APPDATA%\\Hariku2\\piper (not created here)."""
    return os.path.join(core.api.USER_DATA_DIR, ROOT_NAME)


def runtime_dir(root):
    return os.path.join(root, RUNTIME_DIR)


def exe_path(root):
    return os.path.join(runtime_dir(root), *RUNTIME_EXE)


def downloads_dir(root):
    return os.path.join(root, DOWNLOADS_DIR)


def voices_dir(root):
    return os.path.join(root, VOICES_DIR)


def voice_dir(root, key):
    if not catalogue.valid_key(key):
        raise ValueError(f"invalid voice key: {key!r}")
    return os.path.join(voices_dir(root), key)


def model_path(root, key):
    return os.path.join(voice_dir(root, key), key + ".onnx")


def config_path(root, key):
    return os.path.join(voice_dir(root, key), key + ".onnx.json")


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
# The runtime
# ------------------------------------------------------------

def runtime_installed(root):
    return os.path.isfile(exe_path(root)) and os.path.isfile(
        os.path.join(runtime_dir(root), RUNTIME_MARKER))


def write_runtime_marker(root, info):
    write_json(os.path.join(runtime_dir(root), RUNTIME_MARKER), dict(info))


# ------------------------------------------------------------
# Installed voices
# ------------------------------------------------------------

def _clean_card(card):
    card = card if isinstance(card, dict) else {}
    lines = [str(l) for l in card.get("lines") or () if isinstance(l, str)]
    license_text = card.get("license") if isinstance(card.get("license"), str) else ""
    return {"lines": lines[:catalogue.MAX_CARD_LINES],
            "dataset_url": card.get("dataset_url") if isinstance(card.get("dataset_url"), str)
            else "",
            "license": license_text,
            "license_clear": catalogue.license_is_clear(license_text)}


def marker_for(voice, card=None):
    """What voice.json keeps about an installed voice."""
    return {
        "key": voice["key"],
        "name": voice.get("name") or voice["key"],
        "language": voice.get("language") or catalogue.bcp47(voice["key"].split("-")[0]),
        "family": voice.get("family") or catalogue.primary(voice["key"]),
        "language_english": voice.get("language_english", ""),
        "country_english": voice.get("country_english", ""),
        "quality": voice.get("quality", ""),
        "speakers": voice.get("speakers", 1),
        "size": voice.get("size", 0),
        "card": _clean_card(card),
        "installed_at": int(time.time()),
    }


def write_voice_marker(root, voice, card=None):
    write_json(os.path.join(voice_dir(root, voice["key"]), VOICE_MARKER), marker_for(voice, card))


def _installed_voice(root, key):
    marker = read_json(os.path.join(voice_dir(root, key), VOICE_MARKER))
    if not isinstance(marker, dict) or marker.get("key") != key:
        return None
    if not (os.path.isfile(model_path(root, key)) and os.path.isfile(config_path(root, key))):
        return None
    quality = marker.get("quality")
    size = marker.get("size")
    speakers = marker.get("speakers")
    return {
        "key": key,
        "name": marker.get("name") if isinstance(marker.get("name"), str) else key,
        "language": catalogue.bcp47(key.split("-")[0]),
        "family": catalogue.primary(key),
        "language_english": marker.get("language_english")
        if isinstance(marker.get("language_english"), str) else "",
        "country_english": marker.get("country_english")
        if isinstance(marker.get("country_english"), str) else "",
        "quality": quality if quality in catalogue.QUALITIES else "",
        "speakers": speakers if isinstance(speakers, int) and speakers > 0 else 1,
        "size": size if isinstance(size, int) and size > 0 else 0,
        "card": _clean_card(marker.get("card")),
    }


def installed_voices(root):
    """The voices whose files and voice.json are all there, by key."""
    try:
        names = sorted(os.listdir(voices_dir(root)))
    except OSError:
        return []
    found = []
    for name in names:
        if catalogue.valid_key(name):
            voice = _installed_voice(root, name)
            if voice is not None:
                found.append(voice)
    return found


def is_installed(root, key):
    return catalogue.valid_key(key) and _installed_voice(root, key) is not None


def remove_voice(root, key):
    """Delete a voice's folder; voice.json goes first, so a voice that can't be
    removed completely (a file in use) is no longer listed as installed."""
    folder = voice_dir(root, key)
    if not os.path.isdir(folder):
        return False
    marker = os.path.join(folder, VOICE_MARKER)
    if os.path.exists(marker):
        os.remove(marker)
    shutil.rmtree(folder)
    return True


# ------------------------------------------------------------
# Partial downloads
# ------------------------------------------------------------

def discard_partials(folder):
    """Remove the unfinished downloads in one folder."""
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        if name.endswith(PART_SUFFIX):
            remove_quietly(os.path.join(folder, name))


def cleanup_partials(root, max_age=STALE_PART_SECONDS, now=None):
    """Remove unfinished downloads older than `max_age`, voice folders that
    only hold such leftovers, and a runtime left half unpacked. Returns the
    paths removed."""
    now = time.time() if now is None else now
    removed = []
    folders = [downloads_dir(root)]
    try:
        folders += [os.path.join(voices_dir(root), n) for n in os.listdir(voices_dir(root))]
    except OSError:
        pass
    for folder in folders:
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            if not name.endswith((PART_SUFFIX, ".tmp")):
                continue
            try:
                if now - os.path.getmtime(path) > max_age:
                    os.remove(path)
                    removed.append(path)
            except OSError:
                pass
        if folder != downloads_dir(root) and os.path.isdir(folder):
            try:
                if not os.listdir(folder):
                    os.rmdir(folder)
                    removed.append(folder)
            except OSError:
                pass
    staging = runtime_dir(root) + ".new"
    if os.path.isdir(staging):
        shutil.rmtree(staging, ignore_errors=True)
        removed.append(staging)
    return removed


# ------------------------------------------------------------
# The catalogue
# ------------------------------------------------------------

def load_catalogue(root, max_age=None, now=None):
    """The saved voice index if it is at most `max_age` seconds old (any age
    when None), else None."""
    data = read_json(os.path.join(root, CATALOGUE_FILE))
    if not isinstance(data, dict) or not isinstance(data.get("index"), dict):
        return None
    saved_at = data.get("saved_at")
    if not isinstance(saved_at, (int, float)) or isinstance(saved_at, bool):
        return None
    now = time.time() if now is None else now
    if max_age is not None and not (0 <= now - saved_at <= max_age):
        return None
    return data["index"]


def save_catalogue(root, index, now=None):
    write_json(os.path.join(root, CATALOGUE_FILE),
               {"saved_at": time.time() if now is None else now, "index": index})
