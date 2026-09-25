# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Makes World Trip's two sounds in sounds/, from nothing but arithmetic:

  chime.wav   the cabin chime: a high bell note, then a lower one while the
              first still rings (like Cockpit's "ding-dong")
  engine.wav  a jet taking off, about 7 seconds: a low rumble and a roar of
              filtered noise swelling as the engines spool up, a turbine
              whine rising with them, then the plane climbing away

    python extensions/world_trip/world_trip_sounds.py

The files are committed; run this again only to change them. Everything is
computed from sine waves and seeded noise (the same bytes every time), not
recorded or sampled from anything, so there is no copyright question; the
sounds are part of Hariku under its licence. 16-bit mono, peaks well below
full scale, with fades at both ends so nothing clicks. Standard library only.
"""

import io
import math
import os
import random
import struct
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(HERE, "sounds")
CHIME_RATE = 44100
ENGINE_RATE = 22050
ENGINE_SECONDS = 7.0
SEED = 20260925
E5, C5 = 659.26, 523.25


def wav_bytes(samples, rate):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return out.getvalue()


def _to_pcm(buffer, peak):
    loudest = max((abs(v) for v in buffer), default=0.0) or 1.0
    scale = peak * 32767 / loudest
    return [int(round(v * scale)) for v in buffer]


# ------------------------------------------------------------
# The cabin chime
# ------------------------------------------------------------

def _bell(frequency, start, length, rate, decay):
    first = int(start * rate)
    count = int(length * rate)
    rise = max(1, int(0.006 * rate))
    release = int(0.02 * rate)
    out = []
    for n in range(count):
        t = n / rate
        env = min(1.0, n / rise) * math.exp(-decay * t)
        if n > count - release:
            env *= max(0.0, (count - n) / release)
        out.append(env * (math.sin(2 * math.pi * frequency * t)
                          + 0.25 * math.sin(4 * math.pi * frequency * t)
                          + 0.08 * math.sin(6 * math.pi * frequency * t)))
    return first, out


def chime():
    total = int(1.4 * CHIME_RATE)
    buffer = [0.0] * total
    for first, samples in (_bell(E5, 0.0, 0.9, CHIME_RATE, 3.0),
                           _bell(C5, 0.42, 0.98, CHIME_RATE, 2.8)):
        for i, value in enumerate(samples):
            if first + i < total:
                buffer[first + i] += value
    return wav_bytes(_to_pcm(buffer, 0.6), CHIME_RATE)


# ------------------------------------------------------------
# The engines
# ------------------------------------------------------------

def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def engine():
    rate = ENGINE_RATE
    count = int(ENGINE_SECONDS * rate)
    rng = random.Random(SEED)
    low1 = low2 = 0.0               # the rumble: noise through two one-pole low-passes
    svf_low = svf_band = 0.0        # the roar: noise through a state-variable band-pass...
    soft = 0.0                      # ...and a gentle low-pass, so it roars rather than hisses
    phase1 = phase2 = 0.0           # the turbine whine
    buffer = []
    for n in range(count):
        t = n / rate
        spool = _smooth(t / 3.6)                     # the engines spool up...
        away = _smooth((t - 4.6) / 2.4)              # ...then the plane climbs away
        noise = rng.uniform(-1.0, 1.0)

        # Rumble: a low-pass opening from 90 to 320 Hz as the thrust builds.
        cutoff = 90.0 + 230.0 * spool - 120.0 * away
        a = 1.0 - math.exp(-2 * math.pi * cutoff / rate)
        low1 += a * (noise - low1)
        low2 += a * (low1 - low2)
        rumble = low2 * 5.0

        # Roar: band-passed noise, its centre rising from 350 to 1,400 Hz.
        centre = 350.0 + 1050.0 * spool - 600.0 * away
        f = 2 * math.sin(math.pi * centre / rate)
        high = noise - svf_low - 1.1 * svf_band
        svf_band += f * high
        svf_low += f * svf_band
        b = 1.0 - math.exp(-2 * math.pi * (2200.0 - 1200.0 * away) / rate)
        soft += b * (svf_band - soft)
        roar = soft * 0.5

        # Whine: a turbine note rising from 600 to 2,200 Hz with a slight wobble.
        pitch = (600.0 + 1600.0 * spool - 450.0 * away) * (1 + 0.004 * math.sin(2 * math.pi * 5.3 * t))
        phase1 += 2 * math.pi * pitch / rate
        phase2 += 2 * math.pi * pitch * 1.5 / rate
        whine = (math.sin(phase1) + 0.3 * math.sin(phase2)) * 0.03 * _smooth(t / 2.5)

        level = (0.08 + 0.92 * spool) * (1.0 - 0.9 * away)
        edge = min(1.0, t / 0.05, (ENGINE_SECONDS - t) / 0.3)
        buffer.append((rumble * (0.8 + 0.2 * spool) + roar * spool + whine) * level * edge)
    return wav_bytes(_to_pcm(buffer, 0.5), rate)


SOUNDS = (("chime.wav", chime), ("engine.wav", engine))


def write_all(folder=SOUNDS_DIR):
    os.makedirs(folder, exist_ok=True)
    for name, make in SOUNDS:
        data = make()
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)
        with wave.open(io.BytesIO(data)) as w:
            print(f"{name}: {w.getnframes() / w.getframerate():.2f} s, {len(data)} bytes")


if __name__ == "__main__":
    write_all()
