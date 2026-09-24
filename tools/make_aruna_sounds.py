# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Makes Aruna's two sounds (core 2.8) in sounds/, from nothing but sine waves:

  aruna_send.wav   a short soft "bloop" rising in pitch: a typed message sent
  aruna_reply.wav  two gentle bell notes going up: Aruna answered

    python tools/make_aruna_sounds.py

The files are committed; run this again only to change them. 44.1 kHz,
16-bit mono, like listen.wav and listen_end.wav.
"""
import math
import os
import struct
import wave

SAMPLE_RATE = 44100
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G5, C6 = 783.99, 1046.50


def sweep(start_hz, end_hz, length, decay=18.0):
    """A sine gliding from start_hz to end_hz, with a 4 ms attack and a quick decay."""
    count = int(length * SAMPLE_RATE)
    rise = int(0.004 * SAMPLE_RATE)
    phase, out = 0.0, []
    for n in range(count):
        t = n / SAMPLE_RATE
        frequency = start_hz + (end_hz - start_hz) * min(1.0, t / (length * 0.6))
        phase += 2 * math.pi * frequency / SAMPLE_RATE
        env = min(1.0, n / rise) * math.exp(-decay * t) * min(1.0, (count - n) / rise)
        out.append(env * (math.sin(phase) + 0.15 * math.sin(2 * phase)))
    return out


def bell(frequency, length, decay=7.0):
    count = int(length * SAMPLE_RATE)
    rise = int(0.005 * SAMPLE_RATE)
    release = int(0.02 * SAMPLE_RATE)
    out = []
    for n in range(count):
        t = n / SAMPLE_RATE
        env = min(1.0, n / rise) * math.exp(-decay * t)
        if n > count - release:
            env *= max(0.0, (count - n) / release)
        out.append(env * (math.sin(2 * math.pi * frequency * t)
                          + 0.3 * math.sin(2 * math.pi * 2 * frequency * t)
                          + 0.08 * math.sin(2 * math.pi * 3 * frequency * t)))
    return out


def mix(total, parts, peak):
    buffer = [0.0] * int(total * SAMPLE_RATE)
    for start, samples in parts:
        first = int(start * SAMPLE_RATE)
        for i, value in enumerate(samples):
            if first + i < len(buffer):
                buffer[first + i] += value
    loudest = max(abs(v) for v in buffer) or 1.0
    return [int(round(v * peak * 32767 / loudest)) for v in buffer]


def write(name, samples):
    path = os.path.join(ROOT, "sounds", name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    print(f"{path}: {len(samples) / SAMPLE_RATE:.2f} s")


if __name__ == "__main__":
    write("aruna_send.wav", mix(0.12, [(0.0, sweep(520.0, 900.0, 0.12))], peak=0.45))
    write("aruna_reply.wav", mix(0.5, [(0.0, bell(G5, 0.45)), (0.09, bell(C6, 0.41))],
                                 peak=0.5))
