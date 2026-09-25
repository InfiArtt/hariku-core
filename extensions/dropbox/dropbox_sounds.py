# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Makes the Dropbox extension's two sounds in sounds/, from arithmetic alone:

  synced.wav  "done": two soft, rounded notes rising a fourth (G5, C6), the
              second a little to the right, like something settling into place
  shared.wav  "something came for you": three light notes (E5, G5, B5) that
              travel from the left ear to the right, with a faint shimmer

    python extensions/dropbox/dropbox_sounds.py

The files are committed; run this again only to change them. Sine waves
with a touch of their octave, soft attacks and long gentle decays, so they
sit quietly under the screen reader: 16-bit stereo at 44.1 kHz, peaks well
below full scale, faded at both ends so nothing clicks. Nothing recorded or
sampled, so they are part of Hariku under its licence. Standard library only.
"""

import io
import math
import os
import struct
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(HERE, "sounds")
RATE = 44100
G5, C6, E5, B5 = 783.99, 1046.50, 659.26, 987.77


def wav_bytes(samples, rate=RATE):
    """`samples`: interleaved left, right, left, right..."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return out.getvalue()


def _to_pcm(buffer, peak):
    loudest = max((abs(v) for v in buffer), default=0.0) or 1.0
    scale = peak * 32767 / loudest
    return [int(round(v * scale)) for v in buffer]


def _note(frequency, t, decay):
    """A soft bell-ish tone at time t (seconds into the note)."""
    if t < 0:
        return 0.0
    attack = min(1.0, t / 0.012)
    env = attack * math.exp(-decay * t)
    return env * (math.sin(2 * math.pi * frequency * t)
                  + 0.18 * math.sin(2 * math.pi * 2 * frequency * t)
                  + 0.05 * math.sin(2 * math.pi * 3 * frequency * t))


def _render(notes, seconds, peak):
    """notes: (frequency, start, decay, pan -1..1, gain)."""
    count = int(seconds * RATE)
    fade = int(0.03 * RATE)
    out = []
    for n in range(count):
        t = n / RATE
        left = right = 0.0
        for frequency, start, decay, pan, gain in notes:
            v = _note(frequency, t - start, decay) * gain
            # Equal-power panning.
            angle = (pan + 1) * math.pi / 4
            left += v * math.cos(angle)
            right += v * math.sin(angle)
        edge = min(1.0, (count - n) / fade) if n > count - fade else 1.0
        out.append(left * edge)
        out.append(right * edge)
    return wav_bytes(_to_pcm(out, peak))


def synced():
    return _render([(G5, 0.0, 9.0, -0.15, 0.8), (C6, 0.09, 6.5, 0.2, 1.0)], 0.55, 0.32)


def shared():
    return _render([(E5, 0.0, 8.0, -0.6, 0.8), (G5, 0.08, 8.0, 0.0, 0.85),
                    (B5, 0.16, 5.5, 0.6, 1.0), (B5 * 2, 0.16, 12.0, 0.6, 0.12)], 0.75, 0.3)


SOUNDS = (("synced.wav", synced), ("shared.wav", shared))


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
