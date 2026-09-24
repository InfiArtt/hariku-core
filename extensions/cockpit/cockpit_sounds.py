# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The "Cockpit" sound theme, generated here with the standard library (wave,
math, struct): a two-tone cabin chime ("ding-dong"), a single high chime, a
short low double beep and a soft rising three-note chime. These are original
sounds computed from plain sine tones, not recordings or samples of anything,
so there is no copyright question; they are part of Hariku under its licence.

Everything is deterministic (the same bytes every time): 44.1 kHz, 16-bit,
mono, each under 1.5 seconds, with short fade-ins and fade-outs so nothing
clicks, and peaks well below full scale so nothing clips.

A Sound Themes theme is a folder %APPDATA%\\Hariku2\\sound_themes\\<name>\\
holding WAV files named like Hariku's own sounds (see the Sound Themes
extension's sound_themes_store.py); install_theme() writes that folder. No wx.
"""

import io
import math
import os
import struct
import tempfile
import wave

SAMPLE_RATE = 44100
PEAK = 0.8                 # of full scale, after mixing
MAX_SECONDS = 1.5
THEME_NAME = "Cockpit"
THEMES_FOLDER = "sound_themes"   # sound_themes_store.FOLDER_NAME

# Note frequencies (equal temperament, A4 = 440 Hz).
C5, E5, G5, C6 = 523.25, 659.26, 783.99, 1046.50
D4 = 293.66


def _note(frequency, start, length, volume=1.0, attack=0.006, decay=3.2,
          partials=((1.0, 1.0), (2.0, 0.25), (3.0, 0.08))):
    """A bell-like note: sine partials, a short linear attack, an exponential
    decay and a 20 ms fade-out at its end: (first sample, list of floats),
    for _mix() to add up (so notes overlap naturally)."""
    first = int(start * SAMPLE_RATE)
    count = int(length * SAMPLE_RATE)
    release = int(0.02 * SAMPLE_RATE)
    rise = max(1, int(attack * SAMPLE_RATE))
    out = []
    for n in range(count):
        t = n / SAMPLE_RATE
        env = min(1.0, n / rise) * math.exp(-decay * t)
        if n > count - release:
            env *= max(0.0, (count - n) / release)
        value = sum(weight * math.sin(2 * math.pi * frequency * ratio * t)
                    for ratio, weight in partials)
        out.append(volume * env * value)
    return first, out


def _beep(frequency, start, length, volume=1.0):
    """A plain sine beep with 8 ms fades at both ends (for the error sound)."""
    first = int(start * SAMPLE_RATE)
    count = int(length * SAMPLE_RATE)
    fade = int(0.008 * SAMPLE_RATE)
    out = []
    for n in range(count):
        env = min(1.0, n / fade, (count - n) / fade)
        out.append(volume * env * (math.sin(2 * math.pi * frequency * n / SAMPLE_RATE)
                                   + 0.2 * math.sin(2 * math.pi * 2 * frequency * n / SAMPLE_RATE)))
    return first, out


def _mix(total, notes, peak=PEAK):
    """The notes added together over `total` seconds, scaled so the loudest
    sample is `peak` of full scale, as 16-bit integers."""
    buffer = [0.0] * int(total * SAMPLE_RATE)
    for first, samples in notes:
        for i, value in enumerate(samples):
            if first + i < len(buffer):
                buffer[first + i] += value
    loudest = max((abs(v) for v in buffer), default=0.0) or 1.0
    scale = peak * 32767 / loudest
    return [int(round(v * scale)) for v in buffer]


def _wav_bytes(samples):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return out.getvalue()


def ding_dong():
    """The cabin chime: a high note, then a lower one while the first rings."""
    return _wav_bytes(_mix(1.4, [_note(E5, 0.0, 0.9, decay=3.0),
                                 _note(C5, 0.42, 0.98, decay=2.8)]))


def single_chime():
    """One high, short chime."""
    return _wav_bytes(_mix(0.6, [_note(C6, 0.0, 0.6, decay=6.0)], peak=0.7))


def double_beep():
    """Two short, low beeps."""
    return _wav_bytes(_mix(0.36, [_beep(D4, 0.0, 0.13), _beep(D4, 0.2, 0.13)], peak=0.7))


def rising_chime():
    """A soft rising three-note chime: C, E, G."""
    return _wav_bytes(_mix(1.3, [_note(C5, 0.0, 0.7, decay=3.5),
                                 _note(E5, 0.2, 0.7, decay=3.5),
                                 _note(G5, 0.4, 0.9, decay=3.0)], peak=0.55))


# Hariku's sound file -> the Cockpit sound for it. info.wav is what Hariku and
# the extensions play for information and their own alerts and reminders
# (Space, Sleep Pattern, Sea Conditions...); penClick.wav marks a day that has
# reminders; confirm.wav is a confirmation; error.wav and start.wav as named.
THEME_SOUNDS = (
    ("info.wav", ding_dong),
    ("penClick.wav", single_chime),
    ("confirm.wav", single_chime),
    ("error.wav", double_beep),
    ("start.wav", rising_chime),
)


def theme_files():
    """{file name: WAV bytes} of the Cockpit theme."""
    made = {}
    files = {}
    for name, maker in THEME_SOUNDS:
        if maker not in made:
            made[maker] = maker()
        files[name] = made[maker]
    return files


def wav_info(data):
    """(channels, sample width, rate, frames) of WAV bytes."""
    with wave.open(io.BytesIO(data), "rb") as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()


def samples_of(data):
    """The 16-bit samples of mono WAV bytes."""
    with wave.open(io.BytesIO(data), "rb") as w:
        frames = w.readframes(w.getnframes())
    return struct.unpack("<%dh" % (len(frames) // 2), frames)


def themes_root(user_data_dir):
    return os.path.join(user_data_dir, THEMES_FOLDER)


def install_theme(root, stop_sound=None, check=None):
    """Write the Cockpit theme into `root` (the Sound Themes folder), replacing
    its sound files if it is already there; other files are left alone. Each
    file is written beside its target and swapped in. `stop_sound(name)`
    releases a file Windows still holds open after playing it; `check(data)`
    may validate each WAV the way Sound Themes does. Returns the folder."""
    folder = os.path.join(root, THEME_NAME)
    os.makedirs(folder, exist_ok=True)
    for name, data in theme_files().items():
        if check is not None:
            check(data)
        if stop_sound is not None:
            try:
                stop_sound(name)
            except Exception:
                pass
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".wav", dir=folder)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, os.path.join(folder, name))
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    return folder
