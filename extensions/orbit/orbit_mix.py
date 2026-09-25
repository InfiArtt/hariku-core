# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Orbit's sound cues, looked up by name and shaped for where they happen.

A cue ("step_metal", "arrive", "bell"...) is a WAV file, or several numbered
variants of one ("step_metal_1.wav", "step_metal_2.wav"...), one picked at
random each time so a sound heard often doesn't feel mechanical. Folders are
searched in order, and the first one with any file for the cue wins:

  1. %APPDATA%\\Hariku2\\orbit_sounds       your own recordings
  2. <the Sound Themes theme>\\orbit         a sound theme's Orbit sounds
  3. the extension's sounds folder         the generated ones

A name with parts falls back to a shorter one when nothing has it:
"emote_clap" plays "emote" if no folder has an "emote_clap".

Where it happens changes how it sounds: a pan from -1 (left) to 1 (right)
for things to your west or east, an echo for the kind of room (a small
cabin, a hall, a hangar, a cave, the muffled hush outside), and the effects
volume. Those copies are made once and kept in a cache folder, so playing
stays quick; the first play of a new combination takes a few milliseconds.
Standard library only, no wx.
"""

import array
import hashlib
import logging
import math
import os
import random
import re
import sys
import threading
import wave

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_VARIANT_RE = re.compile(r"^(?P<cue>[a-z0-9_]+?)(?:_(?P<n>\d{1,2}))?\.wav$")

# Echo taps (seconds, gain) and a low-pass cutoff (Hz) for each kind of room.
ACOUSTICS = {
    "room": {"taps": ((0.021, 0.18), (0.037, 0.10))},
    "small": {"taps": ((0.011, 0.20),), "cutoff": 7000},
    "open": {"taps": ((0.030, 0.07),)},
    "hall": {"taps": ((0.055, 0.32), (0.105, 0.24), (0.165, 0.16), (0.235, 0.10), (0.31, 0.06))},
    "hangar": {"taps": ((0.085, 0.30), (0.18, 0.19), (0.29, 0.11), (0.41, 0.06))},
    "cave": {"taps": ((0.045, 0.30), (0.095, 0.22), (0.15, 0.15), (0.21, 0.09)), "cutoff": 5000},
    "outside": {"taps": (), "cutoff": 1200, "gain": 0.6},
}
PAN_STEPS = 4          # pans are rounded to quarters: -1, -0.75 ... 1
VOLUME_STEP = 10       # volumes to tens of percent


def _plain(name):
    return isinstance(name, str) and bool(_NAME_RE.match(name))


def read_wav(path):
    """(channels, rate, samples as array('h')) of a 16-bit PCM WAV."""
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() not in (1, 2):
            raise ValueError("16-bit mono or stereo WAV files only")
        channels, rate = w.getnchannels(), w.getframerate()
        data = w.readframes(w.getnframes())
    samples = array.array("h")
    samples.frombytes(data)
    if sys.byteorder == "big":
        samples.byteswap()
    return channels, rate, samples


def write_wav(path, rate, left, right):
    out = array.array("h", (0,)) * (2 * len(left))
    for i, (a, b) in enumerate(zip(left, right)):
        out[2 * i] = max(-32768, min(32767, int(round(a))))
        out[2 * i + 1] = max(-32768, min(32767, int(round(b))))
    if sys.byteorder == "big":
        out.byteswap()
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    os.replace(tmp, path)


def shape(channels, rate, samples, pan=0.0, volume=1.0, acoustics=None):
    """(left, right) float lists: `samples` panned, echoed for the room, at `volume`."""
    if channels == 1:
        left = [float(v) for v in samples]
        right = list(left)
    else:
        left = [float(v) for v in samples[0::2]]
        right = [float(v) for v in samples[1::2]]
    if pan:
        # A centred source is placed with equal power; a stereo design is balanced.
        centred = all(abs(a - b) < 64 for a, b in zip(left[::97], right[::97]))
        angle = (max(-1.0, min(1.0, pan)) + 1) * math.pi / 4
        gl, gr = math.cos(angle) * math.sqrt(2), math.sin(angle) * math.sqrt(2)
        if centred:
            mono = left
            left = [v * gl for v in mono]
            right = [v * gr for v in mono]
        else:
            left = [v * min(1.0, gl) for v in left]
            right = [v * min(1.0, gr) for v in right]
    room = ACOUSTICS.get(acoustics or "")
    if room:
        cutoff = room.get("cutoff")
        if cutoff:
            a = 1.0 - math.exp(-2 * math.pi * cutoff / rate)
            for channel in (left, right):
                y = 0.0
                for i, v in enumerate(channel):
                    y += a * (v - y)
                    channel[i] = y
        taps = room.get("taps", ())
        if taps:
            tail = int(max(d for d, _g in taps) * rate) + 1
            dry_l, dry_r = left + [0.0] * tail, right + [0.0] * tail
            left, right = list(dry_l), list(dry_r)
            for n, (delay, gain) in enumerate(taps):
                shift = int(delay * rate)
                # Alternate sides a little, so the room sounds wide.
                src_l, src_r = (dry_r, dry_l) if n % 2 else (dry_l, dry_r)
                for i in range(shift, len(left)):
                    left[i] += gain * src_l[i - shift]
                    right[i] += gain * src_r[i - shift]
        volume *= room.get("gain", 1.0)
    if volume != 1.0:
        left = [v * volume for v in left]
        right = [v * volume for v in right]
    return left, right


class Mixer:
    """`folders()` gives the folders to search, in order (see the notes);
    `cache_dir` is where shaped copies are kept."""

    def __init__(self, folders, cache_dir, rng=None):
        self._folders = folders
        self.cache_dir = cache_dir
        self.rng = rng or random.Random()
        self._lock = threading.Lock()

    def folders(self):
        try:
            return [f for f in self._folders() if f and os.path.isdir(f)]
        except Exception:
            return []

    def variants(self, cue):
        """The files for `cue` (its variants) from the first folder that has any,
        falling back to shorter names ("emote_clap" -> "emote")."""
        if not _plain(cue):
            return []
        folders = self.folders()
        name = cue
        while name:
            for folder in folders:
                found = []
                try:
                    entries = os.listdir(folder)
                except OSError:
                    continue
                for entry in entries:
                    m = _VARIANT_RE.match(entry.lower())
                    if m and m.group("cue") == name:
                        found.append(os.path.join(folder, entry))
                if found:
                    return sorted(found)
            name = name.rpartition("_")[0]
        return []

    def render(self, cue, pan=0.0, volume=1.0, acoustics=None):
        """The file to play for `cue` (a variant, shaped), or None when there's none."""
        files = self.variants(cue)
        if not files:
            return None
        with self._lock:
            source = self.rng.choice(files)
        pan = round(max(-1.0, min(1.0, float(pan or 0))) * PAN_STEPS) / PAN_STEPS
        level = int(round(max(0.0, min(1.0, float(volume))) * 100 / VOLUME_STEP)) * VOLUME_STEP
        room = acoustics if acoustics in ACOUSTICS else None
        if not pan and level == 100 and room is None:
            return source
        stem = os.path.splitext(os.path.basename(source))[0]
        folder_tag = hashlib.sha1(os.path.dirname(os.path.abspath(source)).encode("utf-8")).hexdigest()[:6]
        name = f"{stem}_{folder_tag}_p{int(pan * PAN_STEPS):+d}_v{level}_{room or 'dry'}.wav"
        target = os.path.join(self.cache_dir, name)
        try:
            if os.path.isfile(target) and os.path.getmtime(target) >= os.path.getmtime(source):
                return target
            os.makedirs(self.cache_dir, exist_ok=True)
            channels, rate, samples = read_wav(source)
            left, right = shape(channels, rate, samples, pan, level / 100.0, room)
            write_wav(target, rate, left, right)
            return target
        except (OSError, ValueError, EOFError, wave.Error) as e:
            logger.info("[Orbit] Could not shape %s: %s", source, e)
            return source
