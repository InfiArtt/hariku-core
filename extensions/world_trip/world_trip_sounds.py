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
              first still rings (like Cockpit's "ding-dong"), with a little
              of the cabin's echo on each side
  engine.wav  a jet taking off, heard from a seat between the wings, about 7
              seconds: the left engine in the left ear and the right one in
              the right, their turbines a little apart so they beat like real
              ones; a low rumble and a wide roar swelling as they spool up;
              the wheels thumping over the runway joints faster and faster
              until the plane lifts off; the gear coming up with a clunk; then
              the plane climbing away

    python extensions/world_trip/world_trip_sounds.py

The files are committed; run this again only to change them. Everything is
computed from sine waves and seeded noise (the same bytes every time), not
recorded or sampled from anything, so there is no copyright question; the
sounds are part of Hariku under its licence. 16-bit stereo, peaks well below
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


def wav_bytes(samples, rate, channels=2):
    """`samples`: interleaved left, right, left, right... for stereo."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
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


def _interleave(left, right):
    out = []
    for pair in zip(left, right):
        out.extend(pair)
    return out


def chime():
    total = int(1.4 * CHIME_RATE)
    buffer = [0.0] * total
    for first, samples in (_bell(E5, 0.0, 0.9, CHIME_RATE, 3.0),
                           _bell(C5, 0.42, 0.98, CHIME_RATE, 2.8)):
        for i, value in enumerate(samples):
            if first + i < total:
                buffer[first + i] += value
    # The cabin's echo: a few quieter, later copies, at other delays on each
    # side, so the chime sounds like a speaker in a room rather than in the head.
    left, right = list(buffer), [0.95 * v for v in buffer]
    for side, echoes in ((left, ((0.023, 0.30), (0.047, 0.18), (0.083, 0.08))),
                         (right, ((0.031, 0.30), (0.059, 0.18), (0.097, 0.08)))):
        for delay, gain in echoes:
            shift = int(delay * CHIME_RATE)
            for i in range(shift, total):
                side[i] += gain * buffer[i - shift]
    fade = int(0.03 * CHIME_RATE)
    for i in range(fade):
        k = i / fade
        left[total - 1 - i] *= k
        right[total - 1 - i] *= k
    return wav_bytes(_to_pcm(_interleave(left, right), 0.6), CHIME_RATE)


# ------------------------------------------------------------
# The engines
# ------------------------------------------------------------

def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class _Side:
    """One engine's filters: the rumble (two one-pole low-passes) and the
    roar (a state-variable band-pass, then a gentle low-pass)."""

    def __init__(self):
        self.low1 = self.low2 = 0.0
        self.svf_low = self.svf_band = self.soft = 0.0
        self.phase1 = self.phase2 = 0.0

    def rumble(self, noise, a):
        self.low1 += a * (noise - self.low1)
        self.low2 += a * (self.low1 - self.low2)
        return self.low2 * 5.0

    def roar(self, noise, f, b):
        high = noise - self.svf_low - 1.1 * self.svf_band
        self.svf_band += f * high
        self.svf_low += f * self.svf_band
        self.soft += b * (self.svf_band - self.soft)
        return self.soft * 0.5

    def whine(self, pitch, rate):
        self.phase1 += 2 * math.pi * pitch / rate
        self.phase2 += 2 * math.pi * pitch * 1.5 / rate
        return math.sin(self.phase1) + 0.3 * math.sin(self.phase2)


LIFTOFF = 4.3            # seconds: the wheels leave the runway
GEAR_UP = 5.4            # the gear comes up


def engine():
    rate = ENGINE_RATE
    count = int(ENGINE_SECONDS * rate)
    rng = random.Random(SEED)
    left, right = _Side(), _Side()
    bump_phase = 0.0          # the runway joints
    bump_age = 1.0            # seconds since the last thump
    out = []
    for n in range(count):
        t = n / rate
        spool = _smooth(t / 3.6)                     # the engines spool up...
        away = _smooth((t - 4.6) / 2.4)              # ...then the plane climbs away
        common = rng.uniform(-1.0, 1.0)              # what both sides hear (the low end)
        noise_l, noise_r = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)

        # Rumble: mostly shared (low sounds seem to come from everywhere), a
        # low-pass opening from 90 to 320 Hz as the thrust builds.
        cutoff = 90.0 + 230.0 * spool - 120.0 * away
        a = 1.0 - math.exp(-2 * math.pi * cutoff / rate)
        rumble_l = left.rumble(0.5 * common + 0.5 * noise_l, a)
        rumble_r = right.rumble(0.5 * common + 0.5 * noise_r, a)

        # Roar: each side its own noise, so it's wide; its centre rising
        # from 350 to 1,400 Hz.
        centre = 350.0 + 1050.0 * spool - 600.0 * away
        f = 2 * math.sin(math.pi * centre / rate)
        b = 1.0 - math.exp(-2 * math.pi * (2200.0 - 1200.0 * away) / rate)
        roar_l, roar_r = left.roar(noise_l, f, b), right.roar(noise_r, f, b)

        # Whine: each engine's turbine, the right one 1.3% faster, so the two
        # beat against each other; each mostly in its own ear.
        pitch = (600.0 + 1600.0 * spool - 450.0 * away) * (1 + 0.004 * math.sin(2 * math.pi * 5.3 * t))
        gain = 0.03 * _smooth(t / 2.5)
        whine_l = left.whine(pitch, rate) * gain
        whine_r = right.whine(pitch * 1.013, rate) * gain

        # The runway: a thump at each joint, closer together as the plane
        # speeds up, gone once it lifts off.
        on_ground = 1.0 - _smooth((t - (LIFTOFF - 0.3)) / 0.6)
        bump_phase += (0.8 + 7.0 * spool) / rate
        if bump_phase >= 1.0:
            bump_phase -= 1.0
            bump_age = 0.0
        bump_age += 1.0 / rate
        thump = math.exp(-bump_age / 0.045) * math.sin(2 * math.pi * 48.0 * bump_age)
        thump *= 0.35 * on_ground * (0.3 + 0.7 * spool)

        # The gear coming up: a soft, low clunk under the floor.
        gear = 0.0
        if GEAR_UP <= t < GEAR_UP + 0.25:
            g = t - GEAR_UP
            gear = 0.25 * math.exp(-g / 0.06) * math.sin(2 * math.pi * 70.0 * g)

        level = (0.08 + 0.92 * spool) * (1.0 - 0.9 * away)
        edge = min(1.0, t / 0.05, (ENGINE_SECONDS - t) / 0.3)
        body_l = rumble_l * (0.8 + 0.2 * spool) + roar_l * spool
        body_r = rumble_r * (0.8 + 0.2 * spool) + roar_r * spool
        # A little of each engine reaches the other ear.
        sample_l = (body_l + whine_l + 0.35 * whine_r) * level + (thump + gear) * edge
        sample_r = (body_r + whine_r + 0.35 * whine_l) * level + (thump + gear) * edge
        out.append(sample_l * edge)
        out.append(sample_r * edge)
    return wav_bytes(_to_pcm(out, 0.5), rate)


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
