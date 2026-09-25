# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Makes the Timer & Alarm extension's two fallback tones, from nothing but sine
waves, in extensions/timer_alarm/sounds/:

  timer_alarm_alarm.wav  four pairs of bright beeps, like a bedside alarm clock
  timer_alarm_timer.wav  a rising three-note chime, twice, like a kitchen timer

They play when the Windows alarm sounds the user chose (%WINDIR%\\Media\\
Alarm01.wav ...) aren't on the computer; Hariku can't ship those. A ring
plays its sound again every 10 seconds, so each tone is under 3 seconds.

    python tools/make_timer_alarm_sounds.py

The files are committed; run this again only to change them. 44.1 kHz,
16-bit mono, like Hariku's other sounds.
"""
import math
import os
import struct
import wave

SAMPLE_RATE = 44100
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "extensions", "timer_alarm", "sounds")
C6, E6, G6, A5 = 1046.50, 1318.51, 1567.98, 880.0


def beep(frequency, length):
    """A square-ish beep (a sine with odd harmonics), 3 ms edges so it doesn't click."""
    count = int(length * SAMPLE_RATE)
    edge = int(0.003 * SAMPLE_RATE)
    out = []
    for n in range(count):
        t = n / SAMPLE_RATE
        env = min(1.0, n / edge, (count - n) / edge)
        phase = 2 * math.pi * frequency * t
        out.append(env * (math.sin(phase) + 0.3 * math.sin(3 * phase) + 0.12 * math.sin(5 * phase)))
    return out


def chime(frequency, length, decay=4.5):
    count = int(length * SAMPLE_RATE)
    rise = int(0.004 * SAMPLE_RATE)
    release = int(0.03 * SAMPLE_RATE)
    out = []
    for n in range(count):
        t = n / SAMPLE_RATE
        env = min(1.0, n / rise) * math.exp(-decay * t)
        if n > count - release:
            env *= max(0.0, (count - n) / release)
        out.append(env * (math.sin(2 * math.pi * frequency * t)
                          + 0.35 * math.sin(2 * math.pi * 2 * frequency * t)
                          + 0.1 * math.sin(2 * math.pi * 3 * frequency * t)))
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
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    print(f"{path}: {len(samples) / SAMPLE_RATE:.2f} s")


def alarm_tone():
    parts = []
    for group in range(4):                       # beep-beep ... four times
        start = group * 0.6
        parts.append((start, beep(A5 * 2, 0.11)))
        parts.append((start + 0.17, beep(A5 * 2, 0.11)))
    return mix(2.4, parts, peak=0.6)


def timer_tone():
    parts = []
    for round_ in range(2):
        start = round_ * 1.25
        for k, frequency in enumerate((C6, E6, G6)):
            parts.append((start + k * 0.16, chime(frequency, 1.0 - k * 0.1)))
    return mix(2.5, parts, peak=0.6)


if __name__ == "__main__":
    write("timer_alarm_alarm.wav", alarm_tone())
    write("timer_alarm_timer.wav", timer_tone())
