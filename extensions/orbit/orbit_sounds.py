# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Makes Orbit's sounds in sounds/: recorded ones where a recording beats
arithmetic, synthesized ones for the rest.

Recorded (RECORDED below): footsteps on each kind of floor, doors, the
airlock's latch, cloth for waves and hugs, coins, the pick on rock, cutting
a crop, the shuttle's engines and thrusters, the interface's little sounds,
and the whole casino (dice, cards, chips). They come from five sound packs
by Kenney (www.kenney.nl): Casino Audio, Impact Sounds, RPG Audio, Sci-fi
Sounds and Interface Sounds, released under CC0 1.0 (public domain; see
sounds/LICENSE-kenney.txt). tools/orbit_convert_kenney.py turned the packs
into trimmed, level-matched mono 22.05 kHz WAVs once; each recipe here mixes
one or more of those (a pair of steps, a latch then a door), and scales the
result to a peak that fits beside the other cues.

Synthesized (SOUNDS below), from nothing but arithmetic: layered and
filtered noise, damped resonators for metal, wood and glass, envelopes
shaped like real ones, a small room reverb. Human sounds (laughs, claps, a
cheer, a sigh), the reactor's tones, the temple bell, the ambience loops
and the little stings (a level up, an achievement) are made this way; a few
recipes mix a synthesized part with recorded ones ("synth:airlock").

Every file is a cue orbit_mix looks up by name ("step_metal_2.wav" is a
variant of "step_metal"). Cues heard from a direction (steps, someone
arriving, a gesture) are mono: Orbit pans them to the side they come from
and adds the room's echo when it plays them; every recorded cue is mono.
The cue names, what they are, and how to replace them with your own
recordings are in README.md (servers/orbit), and CUES below.

    python extensions/orbit/orbit_sounds.py                    the synthesized cues
    python extensions/orbit/orbit_sounds.py --kenney <folder>  and the recorded ones

The files are committed; run this again only to change them (the recorded
ones need the converted packs, see tools/orbit_convert_kenney.py). The
synthesized sounds are computed from sine waves and seeded noise (the same
bytes every time), not sampled from anything, and are part of Hariku under
its licence. 16-bit, peaks well below full scale, short fades so nothing
clicks. The ambience files loop without a seam: each is made a little
longer than it plays and its end is crossfaded into its start, and its
steady tones fit a whole number of cycles into the loop. Standard library
only.
"""

import array
import io
import math
import os
import random
import struct
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(HERE, "sounds")
RATE = 22050                 # effects
LOOP_RATE = 11025            # ambience: low, soft sounds, so small files
LOOP_SECONDS = 4.0
LOOP_OVERLAP = 0.5
SEED = 20260925
TAU = 2 * math.pi

C5, E5, G5, C6 = 523.25, 659.25, 783.99, 1046.5


# ------------------------------------------------------------
# Writing files
# ------------------------------------------------------------

def _fade_list(samples, rate, fade_in, fade_out):
    n = len(samples)
    rise = max(1, int(fade_in * rate))
    fall = max(1, int(fade_out * rate))
    for i in range(min(rise, n)):
        samples[i] *= i / rise
    for i in range(min(fall, n)):
        samples[n - 1 - i] *= i / fall
    return samples


def wav_bytes(left, right, rate, peak):
    """Interleave, scale the loudest sample to `peak`, and make a stereo WAV."""
    loudest = max(max((abs(v) for v in left), default=0.0),
                  max((abs(v) for v in right), default=0.0)) or 1.0
    scale = peak * 32767 / loudest
    samples = []
    for a, b in zip(left, right):
        samples.append(int(round(a * scale)))
        samples.append(int(round(b * scale)))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return out.getvalue()


def mono_bytes(samples, rate, peak, fade_in=0.004, fade_out=0.02):
    """A mono WAV, the loudest sample at `peak`: for cues Orbit places itself."""
    samples = _fade_list(list(samples), rate, fade_in, fade_out)
    loudest = max((abs(v) for v in samples), default=0.0) or 1.0
    scale = peak * 32767 / loudest
    ints = [int(round(v * scale)) for v in samples]
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(ints), *ints))
    return out.getvalue()


def _fade(left, right, rate, fade_in=0.005, fade_out=0.02):
    _fade_list(left, rate, fade_in, fade_out)
    _fade_list(right, rate, fade_in, fade_out)
    return left, right


def _pan(position):
    """(left gain, right gain) for -1 (left) to 1 (right), equal power."""
    angle = (position + 1) * math.pi / 4
    return math.cos(angle), math.sin(angle)


def _blank(seconds, rate=RATE):
    n = int(seconds * rate)
    return [0.0] * n, [0.0] * n


def _zeros(seconds, rate=RATE):
    return [0.0] * int(seconds * rate)


def _add(left, right, start, samples, position=0.0, gain=1.0, rate=RATE):
    gl, gr = _pan(position)
    first = int(start * rate)
    for i, v in enumerate(samples):
        j = first + i
        if 0 <= j < len(left):
            left[j] += v * gl * gain
            right[j] += v * gr * gain


def _put(dst, start, samples, gain=1.0, rate=RATE):
    first = int(start * rate)
    for i, v in enumerate(samples):
        j = first + i
        if 0 <= j < len(dst):
            dst[j] += v * gain


# ------------------------------------------------------------
# Building blocks
# ------------------------------------------------------------

def _bell(frequency, seconds, decay, rate=RATE, partials=((1, 1.0), (2, 0.25), (3, 0.08))):
    count = int(seconds * rate)
    rise = max(1, int(0.004 * rate))
    out = []
    for n in range(count):
        t = n / rate
        env = min(1.0, n / rise) * math.exp(-decay * t)
        out.append(env * sum(g * math.sin(TAU * frequency * k * t) for k, g in partials))
    return out


def _resonator(freqs, decays, gains, seconds, rate=RATE, attack=0.001):
    """Damped sines: struck metal, wood, glass (inharmonic partials)."""
    count = int(seconds * rate)
    rise = max(1, int(attack * rate))
    out = [0.0] * count
    for f, d, g in zip(freqs, decays, gains):
        step = TAU * f / rate
        for n in range(count):
            out[n] += g * math.exp(-d * n / rate) * math.sin(step * n)
    for n in range(min(rise, count)):
        out[n] *= n / rise
    return out


def _echo(left, right, rate, taps):
    """A room: quieter, later copies on each side (taps: (seconds, gain, side))."""
    dry_l, dry_r = list(left), list(right)
    for delay, gain, side in taps:
        shift = int(delay * rate)
        src, dst = (dry_l, right) if side > 0 else (dry_r, left)
        for i in range(shift, len(dst)):
            dst[i] += gain * src[i - shift]
    return left, right


def _reverb(samples, rate, size=1.0, damp=0.35, wet=0.35):
    """A small Schroeder reverb (four combs, two all-passes): a hall around a sound."""
    combs = [0.0297, 0.0371, 0.0411, 0.0437]
    feedback = 0.72 + 0.1 * min(1.0, size)
    out = [0.0] * len(samples)
    for delay in combs:
        d = max(1, int(delay * size * rate))
        buf = [0.0] * d
        idx = 0
        low = 0.0
        for n, x in enumerate(samples):
            y = buf[idx]
            low = y * (1 - damp) + low * damp
            buf[idx] = x + low * feedback
            idx = (idx + 1) % d
            out[n] += y
    for delay, g in ((0.005, 0.7), (0.0017, 0.7)):
        d = max(1, int(delay * rate))
        buf = [0.0] * d
        idx = 0
        for n, x in enumerate(out):
            b = buf[idx]
            y = -g * x + b
            buf[idx] = x + g * y
            idx = (idx + 1) % d
            out[n] = y
    return [x + wet * y / len(combs) for x, y in zip(samples, out)]


class _SVF:
    """A state-variable filter: band-pass (and low-pass) at a moving centre."""

    def __init__(self, q=1.2):
        self.low = self.band = 0.0
        self.damp = 1.0 / q

    def band_pass(self, x, centre, rate):
        f = 2 * math.sin(math.pi * min(centre, rate / 6.0) / rate)
        high = x - self.low - self.damp * self.band
        self.band += f * high
        self.low += f * self.band
        return self.band

    def low_pass(self, x, centre, rate):
        self.band_pass(x, centre, rate)
        return self.low


def _lowpass_coeff(cutoff, rate):
    return 1.0 - math.exp(-TAU * cutoff / rate)


def _noise(n, rng):
    return [rng.uniform(-1, 1) for _ in range(n)]


def _band(samples, centre, q=1.2, rate=RATE):
    filt = _SVF(q)
    if callable(centre):
        return [filt.band_pass(x, centre(i / rate), rate) for i, x in enumerate(samples)]
    return [filt.band_pass(x, centre, rate) for x in samples]


def _low(samples, cutoff, rate=RATE):
    a = _lowpass_coeff(cutoff, rate)
    y = 0.0
    out = []
    for x in samples:
        y += a * (x - y)
        out.append(y)
    return out


def _high(samples, cutoff, rate=RATE):
    low = _low(samples, cutoff, rate)
    return [x - l for x, l in zip(samples, low)]


def _env(n, attack, decay, rate=RATE, hold=0.0):
    """Attack (seconds), hold, then an exponential decay (per second)."""
    rise = max(1, int(attack * rate))
    flat = int(hold * rate)
    out = []
    for i in range(n):
        if i < rise:
            out.append(i / rise)
        elif i < rise + flat:
            out.append(1.0)
        else:
            out.append(math.exp(-decay * (i - rise - flat) / rate))
    return out


def _burst(rng, seconds, centre, q, attack, decay, rate=RATE):
    """Filtered noise with an envelope: the body of most real-world sounds."""
    n = int(seconds * rate)
    env = _env(n, attack, decay, rate)
    return [v * e for v, e in zip(_band(_noise(n, rng), centre, q, rate), env)]


def _thump(frequency, seconds, decay, rate=RATE, drop=0.3):
    """A low, falling thud (a foot, a body, a heavy door)."""
    out = []
    phase = 0.0
    for i in range(int(seconds * rate)):
        t = i / rate
        f = frequency * (1 - drop * min(1.0, t / seconds))
        phase += TAU * f / rate
        out.append(math.sin(phase) * math.exp(-decay * t) * min(1.0, i / 20))
    return out


def _chirp(f0, f1, seconds, rate=RATE, decay=0.0, shape=None):
    out = []
    phase = 0.0
    n = int(seconds * rate)
    for i in range(n):
        t = i / rate
        f = f0 + (f1 - f0) * (i / max(1, n - 1))
        phase += TAU * f / rate
        env = math.sin(math.pi * i / n) if shape == "arch" else math.exp(-decay * t)
        out.append(math.sin(phase) * env)
    return out


def _soft_square(frequency, seconds, decay, rate=RATE):
    count = int(seconds * rate)
    out = []
    for n in range(count):
        t = n / rate
        env = min(1.0, t / 0.005) * math.exp(-decay * t)
        x = TAU * frequency * t
        out.append(env * (math.sin(x) + math.sin(3 * x) / 3 + math.sin(5 * x) / 5))
    return out


def _grains(rng, seconds, count, centre_lo, centre_hi, grain=0.0015, rate=RATE, env=None):
    """Many tiny clicks: gravel, grass, crackling, rustling."""
    out = _zeros(seconds, rate)
    n = len(out)
    for _k in range(count):
        at = rng.random()
        start = int(at * (n - int(grain * rate) - 1))
        amp = rng.uniform(0.3, 1.0) * (env(at) if env else 1.0)
        burst = _burst(rng, grain * 3, rng.uniform(centre_lo, centre_hi), 2.0, 0.0002, 1.0 / grain, rate)
        _put(out, start / rate, burst, amp, rate)
    return out


# ------------------------------------------------------------
# Footsteps: heel and toe, a little different every time
# ------------------------------------------------------------

def _step_pair(rng, make, gap):
    out = _zeros(0.36)
    _put(out, 0.0, make(rng, 1.0))
    _put(out, gap, make(rng, 0.6))
    return out


def step_metal(variant):
    rng = random.Random(SEED + 100 + variant)
    base = rng.uniform(520, 700)

    def strike(rng, force):
        n = 0.3
        click = _burst(rng, 0.01, 4200, 0.8, 0.0003, 400)
        ring = _resonator([base, base * 1.63, base * 2.37, base * 3.11],
                          [38, 45, 60, 80], [0.5, 0.35, 0.2, 0.12], n)
        body = _thump(95, 0.08, 45)
        out = _zeros(n)
        _put(out, 0.0, click, 0.9 * force)
        _put(out, 0.0, ring, 0.25 * force)
        _put(out, 0.0, body, 0.6 * force)
        rattle = _grains(rng, 0.08, 4, 2500, 5000)
        _put(out, 0.02, rattle, 0.15 * force)
        return out

    return mono_bytes(_step_pair(rng, strike, rng.uniform(0.07, 0.1)), RATE, 0.32)


def step_carpet(variant):
    rng = random.Random(SEED + 110 + variant)

    def press(rng, force):
        n = 0.14
        soft = _low(_burst(rng, n, 420, 0.7, 0.004, 35), 700)
        out = _zeros(n)
        _put(out, 0.0, soft, 1.0 * force)
        _put(out, 0.0, _thump(70, 0.07, 55), 0.5 * force)
        return out

    return mono_bytes(_step_pair(rng, press, rng.uniform(0.08, 0.11)), RATE, 0.24)


def step_grass(variant):
    rng = random.Random(SEED + 120 + variant)

    def swish(rng, force):
        n = 0.18
        rustle = _grains(rng, n, 40, 2200, 6000, env=lambda a: math.sin(math.pi * a))
        out = _zeros(n)
        _put(out, 0.0, rustle, 0.8 * force)
        _put(out, 0.0, _thump(75, 0.06, 60), 0.35 * force)
        return out

    return mono_bytes(_step_pair(rng, swish, rng.uniform(0.09, 0.12)), RATE, 0.26)


def step_stone(variant):
    rng = random.Random(SEED + 130 + variant)

    def tap(rng, force):
        n = 0.16
        click = _high(_burst(rng, 0.006, 3500, 0.9, 0.0002, 600), 2000)
        body = _burst(rng, 0.05, 900, 1.5, 0.001, 70)
        ring = _resonator([1800 + rng.uniform(-80, 80), 2950], [70, 110], [0.3, 0.15], n)
        out = _zeros(n)
        _put(out, 0.0, click, 1.0 * force)
        _put(out, 0.0, body, 0.6 * force)
        _put(out, 0.0, ring, 0.12 * force)
        _put(out, 0.0, _thump(85, 0.05, 70), 0.4 * force)
        return out

    return mono_bytes(_step_pair(rng, tap, rng.uniform(0.07, 0.09)), RATE, 0.28)


def step_rock(variant):
    rng = random.Random(SEED + 140 + variant)

    def crunch(rng, force):
        n = 0.16
        grit = _grains(rng, n, 30, 1800, 5000, grain=0.001, env=lambda a: math.exp(-3 * a))
        out = _zeros(n)
        _put(out, 0.0, grit, 1.0 * force)
        _put(out, 0.0, _thump(65, 0.06, 55), 0.5 * force)
        return out

    return mono_bytes(_step_pair(rng, crunch, rng.uniform(0.09, 0.12)), RATE, 0.28)


def step_suit(variant):
    rng = random.Random(SEED + 150 + variant)

    def boot(rng, force):
        n = 0.2
        thud = _low(_thump(60, 0.12, 30), 300)
        creak = _burst(rng, 0.12, 700 + rng.uniform(-60, 60), 4.0, 0.02, 25)
        out = _zeros(n)
        _put(out, 0.0, thud, 1.0 * force)
        _put(out, 0.03, creak, 0.25 * force)
        return out

    return mono_bytes(_step_pair(rng, boot, rng.uniform(0.12, 0.15)), RATE, 0.26)


def step_wet(variant):
    rng = random.Random(SEED + 160 + variant)

    def splash(rng, force):
        n = 0.2
        water = _burst(rng, n, lambda t: 1600 - 4500 * t, 1.1, 0.002, 22)
        drip = _chirp(1100, 1900, 0.03, decay=60)
        out = _zeros(n)
        _put(out, 0.0, water, 0.9 * force)
        _put(out, 0.0, _thump(70, 0.05, 60), 0.4 * force)
        _put(out, 0.1 + rng.uniform(0, 0.05), drip, 0.15 * force)
        return out

    return mono_bytes(_step_pair(rng, splash, rng.uniform(0.09, 0.12)), RATE, 0.26)


# ------------------------------------------------------------
# Getting about
# ------------------------------------------------------------

def door(variant):
    """A pneumatic door: a hiss that rises and falls, then a soft thunk."""
    rng = random.Random(SEED + 1 + variant)
    out = _zeros(0.8)
    hiss = _burst(rng, 0.62, lambda t: 500 + 2200 * math.sin(math.pi * min(1.0, t / 0.62)) ** 1.5,
                  1.5, 0.05, 2.0)
    env = [math.sin(math.pi * min(1.0, i / len(hiss))) ** 0.8 for i in range(len(hiss))]
    _put(out, 0.0, [h * e for h, e in zip(hiss, env)], 1.0)
    _put(out, 0.58 + 0.02 * variant, _thump(85, 0.16, 28), 0.7)
    return mono_bytes(out, RATE, 0.45)


def airlock():
    rng = random.Random(SEED + 170)
    out = _zeros(1.6)
    for k in range(2):
        _put(out, 0.02 + 0.14 * k, _soft_square(1000, 0.08, 30), 0.15)
    hiss = _high(_noise(int(0.8 * RATE), rng), 1400)
    env = _env(len(hiss), 0.08, 4.0, hold=0.35)
    _put(out, 0.3, [h * e for h, e in zip(hiss, env)], 0.7)
    _put(out, 1.1, _thump(60, 0.3, 14), 1.0)
    _put(out, 1.1, _thump(120, 0.12, 30), 0.4)
    _put(out, 1.1, _burst(rng, 0.03, 2500, 1.0, 0.0005, 150), 0.5)
    return mono_bytes(out, RATE, 0.45)


def _lift(rising):
    rng = random.Random(SEED + 180 + rising)
    seconds = 1.5
    out = _zeros(seconds)
    phase = 0.0
    rumble = _low(_noise(len(out), rng), 150)
    for i in range(len(out)):
        t = i / RATE
        f = (100 + 45 * t / seconds) if rising else (145 - 45 * t / seconds)
        phase += TAU * f / RATE
        env = min(1.0, t / 0.15) * min(1.0, (seconds - 0.25 - t) / 0.2) if t < seconds - 0.25 else 0.0
        hum = math.sin(phase) + 0.4 * math.sin(2 * phase) + 0.2 * math.sin(3 * phase)
        out[i] += (hum * 0.25 + rumble[i] * 2.0) * max(0.0, env)
    ding = _bell(1318.5 if rising else 987.8, 0.7, 5.0)
    _put(out, seconds - 0.4, [d * 0.8 for d in ding[:int(0.4 * RATE)]], 1.0)
    return mono_bytes(out, RATE, 0.4)


def lift_up():
    return _lift(True)


def lift_down():
    return _lift(False)


def ladder(variant):
    rng = random.Random(SEED + 190 + variant)
    out = _zeros(0.6)
    for k in range(3):
        f = rng.uniform(380, 480)
        clank = _resonator([f, f * 2.7, f * 4.1], [30, 45, 70], [0.6, 0.3, 0.15], 0.25)
        _put(out, 0.04 + 0.16 * k + rng.uniform(-0.01, 0.01), clank, 0.7)
        _put(out, 0.04 + 0.16 * k, _burst(rng, 0.01, 3500, 0.8, 0.0003, 300), 0.5)
    return mono_bytes(out, RATE, 0.36)


def slide():
    rng = random.Random(SEED + 200)
    out = _zeros(1.4)
    swoosh = _burst(rng, 1.05, lambda t: 2400 - 1600 * t, 1.3, 0.1, 0.5)
    env = [math.sin(math.pi * i / len(swoosh)) for i in range(len(swoosh))]
    _put(out, 0.0, [s * e for s, e in zip(swoosh, env)], 1.0)
    _put(out, 1.08, _thump(70, 0.25, 18), 1.0)
    _put(out, 1.12, _thump(90, 0.15, 30), 0.5)
    return mono_bytes(out, RATE, 0.42)


def bump(variant):
    rng = random.Random(SEED + 210 + variant)
    out = _zeros(0.3)
    _put(out, 0.0, _low(_burst(rng, 0.12, 300, 0.7, 0.002, 30), 500), 1.0)
    _put(out, 0.0, _thump(70 + 8 * variant, 0.15, 30), 0.8)
    buzz = _resonator([rng.uniform(220, 260), 690], [25, 40], [0.2, 0.08], 0.25)
    _put(out, 0.005, buzz, 0.3)
    return mono_bytes(out, RATE, 0.35)


def locked():
    rng = random.Random(SEED + 220)
    left, right = _blank(0.55)
    _add(left, right, 0.0, _soft_square(880, 0.09, 20), 0.2, 0.6)
    _add(left, right, 0.11, _soft_square(622, 0.16, 12), 0.2, 0.6)
    clack = _burst(rng, 0.04, 1800, 1.4, 0.0005, 120)
    _add(left, right, 0.3, clack, 0.0, 0.8)
    _add(left, right, 0.3, _thump(110, 0.06, 60), 0.0, 0.5)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.35)


def _people_steps(rng, louder):
    """Steps getting nearer (louder=True) or further away, then a soft chime."""
    out = _zeros(0.9)
    for k in range(4):
        gain = (0.35 + 0.2 * k) if louder else (0.95 - 0.2 * k)
        base = rng.uniform(500, 650)
        tap = _resonator([base, base * 1.6], [60, 80], [0.3, 0.15], 0.1)
        _put(out, 0.05 + 0.14 * k, _burst(rng, 0.03, 2500, 0.9, 0.0005, 150), 0.6 * gain)
        _put(out, 0.05 + 0.14 * k, tap, 0.3 * gain)
        _put(out, 0.05 + 0.14 * k, _thump(90, 0.05, 60), 0.5 * gain)
    notes = (G5, C6) if louder else (C6, G5)
    _put(out, 0.55, _bell(notes[0], 0.3, 9.0), 0.25)
    _put(out, 0.65, _bell(notes[1], 0.25, 9.0), 0.25)
    return out


def arrive():
    return mono_bytes(_people_steps(random.Random(SEED + 230), True), RATE, 0.32)


def leave():
    return mono_bytes(_people_steps(random.Random(SEED + 231), False), RATE, 0.32)


# ------------------------------------------------------------
# Talking
# ------------------------------------------------------------

def say(variant):
    """Someone speaks: the comm opens with a click and a breath."""
    rng = random.Random(SEED + 240 + variant)
    out = _zeros(0.4)
    _put(out, 0.0, _high(_burst(rng, 0.006, 3000, 0.8, 0.0002, 500), 1500), 0.4)
    _put(out, 0.01, _chirp(760 + 40 * variant, 980 + 40 * variant, 0.05, decay=20), 0.25)
    breath = _burst(rng, 0.3, lambda t: 1300 + 300 * math.sin(TAU * 3 * t), 0.6, 0.04, 9)
    _put(out, 0.05, breath, 0.5)
    return mono_bytes(out, RATE, 0.24)


def shout(variant):
    """A shout across the station: louder, and ringing through the halls."""
    rng = random.Random(SEED + 250 + variant)
    left, right = _blank(1.1)
    voice = [a + b for a, b in zip(_burst(rng, 0.35, 700, 3.0, 0.02, 6),
                                   _burst(rng, 0.35, 1450, 3.0, 0.02, 6))]
    click = _high(_burst(rng, 0.006, 3000, 0.8, 0.0002, 500), 1500)
    _add(left, right, 0.0, click, 0.0, 0.5)
    _add(left, right, 0.02, voice, 0.0, 1.0)
    _echo(left, right, RATE, ((0.09, 0.45, 1), (0.16, 0.35, -1), (0.27, 0.22, 1), (0.39, 0.12, -1)))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.1), RATE, 0.4)


def whisper():
    rng = random.Random(SEED + 2)
    left, right = _blank(0.55)
    filt = _SVF(0.9)
    psst = []
    for i in range(int(0.28 * RATE)):
        t = i / RATE
        env = min(1.0, t / 0.03) * math.exp(-max(0.0, t - 0.05) / 0.07)
        psst.append(filt.band_pass(rng.uniform(-1, 1), 5200, RATE) * env)
    _add(left, right, 0.0, psst, 0.75, 1.0)
    _add(left, right, 0.25, _bell(1760.0, 0.28, 12.0), 0.8, 0.35)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.4)


def sent():
    rng = random.Random(SEED + 3)
    left, right = _blank(0.22)
    filt_l, filt_r = _SVF(1.0), _SVF(1.0)
    for i in range(len(left)):
        t = i / RATE
        progress = t / 0.22
        env = math.sin(math.pi * progress)
        noise = rng.uniform(-1, 1)
        centre = 1800 + 2600 * progress
        gl, gr = _pan(-0.5 + progress)
        left[i] = filt_l.band_pass(noise, centre, RATE) * env * gl
        right[i] = filt_r.band_pass(noise, centre, RATE) * env * gr
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.22)


def announce():
    left, right = _blank(1.6)
    for start, note in ((0.0, C5), (0.28, E5), (0.56, G5)):
        _add(left, right, start, _bell(note, 1.0, 3.0), 0.0, 0.8)
    _echo(left, right, RATE, ((0.043, 0.35, 1), (0.061, 0.30, -1), (0.097, 0.18, 1),
                              (0.131, 0.12, -1), (0.173, 0.07, 1)))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.06), RATE, 0.5)


def offer():
    """An invitation: a soft two-note doorbell."""
    left, right = _blank(1.0)
    _add(left, right, 0.0, _bell(E5 * 2, 0.6, 5.0), -0.2, 0.7)
    _add(left, right, 0.28, _bell(C6, 0.7, 4.5), 0.2, 0.7)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.05), RATE, 0.35)


# ------------------------------------------------------------
# Gestures
# ------------------------------------------------------------

def emote():
    """A gesture with no sound of its own: a soft bubble."""
    out = []
    phase = 0.0
    for i in range(int(0.16 * RATE)):
        t = i / RATE
        frequency = 950 - 450 * min(1.0, t / 0.08)
        phase += TAU * frequency / RATE
        out.append(math.sin(phase) * min(1.0, t / 0.004) * math.exp(-t / 0.04))
    return mono_bytes(out, RATE, 0.25, fade_out=0.01)


def emote_smile():
    out = _zeros(0.5)
    for k, f in enumerate((1568.0, 2093.0)):
        _put(out, 0.06 * k, _bell(f, 0.4, 10.0), 0.4)
    return mono_bytes(out, RATE, 0.22)


def _swish(rng, seconds, lo, hi):
    burst = _burst(rng, seconds, lambda t: lo + (hi - lo) * math.sin(math.pi * min(1.0, t / seconds)),
                   1.0, seconds * 0.4, 1.0)
    return [b * math.sin(math.pi * i / len(burst)) for i, b in enumerate(burst)]


def emote_wave(variant):
    rng = random.Random(SEED + 260 + variant)
    out = _zeros(0.6)
    _put(out, 0.0, _swish(rng, 0.22, 900, 3000), 1.0)
    _put(out, 0.25, _swish(rng, 0.22, 1200, 2600), 0.8)
    return mono_bytes(out, RATE, 0.26)


def emote_laugh(variant):
    """Breathy "ha ha ha": glottal pulses through two vowel formants."""
    rng = random.Random(SEED + 270 + variant)
    out = _zeros(0.9)
    pitch = 190 + 40 * variant
    for k in range(5):
        n = int(0.075 * RATE)
        burst = []
        for i in range(n):
            t = i / RATE
            pulse = 1.0 if (i % max(1, int(RATE / (pitch * (1 - 0.04 * k))))) < 3 else 0.0
            burst.append(pulse + 0.5 * rng.uniform(-1, 1))
        vowel = [a + 0.7 * b for a, b in zip(_band(burst, 800, 4.0), _band(burst, 1250, 4.0))]
        env = _env(n, 0.008, 25)
        _put(out, 0.02 + 0.14 * k, [v * e for v, e in zip(vowel, env)], 1.0 - 0.12 * k)
    return mono_bytes(out, RATE, 0.28)


def emote_nod():
    rng = random.Random(SEED + 280)
    out = _zeros(0.2)
    _put(out, 0.0, _burst(rng, 0.08, 1500, 1.0, 0.01, 40), 1.0)
    _put(out, 0.1, _burst(rng, 0.06, 1300, 1.0, 0.01, 50), 0.6)
    return mono_bytes(out, RATE, 0.18)


def emote_shrug():
    rng = random.Random(SEED + 281)
    out = _zeros(0.5)
    _put(out, 0.0, _swish(rng, 0.2, 1000, 2000), 0.9)
    _put(out, 0.26, _swish(rng, 0.18, 1600, 900), 0.7)
    return mono_bytes(out, RATE, 0.2)


def emote_clap(variant):
    rng = random.Random(SEED + 290 + variant)
    out = _zeros(0.8)
    for k in range(3):
        clap = _burst(rng, 0.09, rng.uniform(1100, 1700), 1.1, 0.0005, 55)
        _put(out, 0.02 + 0.22 * k + rng.uniform(-0.015, 0.015), clap, 1.0 - 0.1 * k)
    return mono_bytes(out, RATE, 0.36)


def emote_cheer():
    rng = random.Random(SEED + 292)
    out = _zeros(1.0)
    for voice in range(4):
        n = int(0.8 * RATE)
        noise = _noise(n, rng)
        f1 = rng.uniform(600, 900)
        v = [a + b for a, b in zip(_band(noise, lambda t: f1 + 200 * t, 5.0),
                                   _band(noise, lambda t: 2 * f1 + 300 * t, 5.0))]
        env = [math.sin(math.pi * i / n) ** 0.7 for i in range(n)]
        _put(out, 0.05 * voice, [a * e for a, e in zip(v, env)], 0.6)
    whistle = _chirp(2000, 2700, 0.35, shape="arch")
    _put(out, 0.35, whistle, 0.2)
    return mono_bytes(out, RATE, 0.3)


def emote_sigh():
    rng = random.Random(SEED + 293)
    n = int(1.0 * RATE)
    breath = _burst(rng, 1.0, lambda t: 1500 - 900 * t, 0.5, 0.12, 2.5)
    return mono_bytes(breath[:n], RATE, 0.22, fade_out=0.1)


def emote_bow():
    rng = random.Random(SEED + 294)
    out = _zeros(0.6)
    _put(out, 0.0, _swish(rng, 0.35, 800, 1600), 0.9)
    _put(out, 0.4, _thump(90, 0.1, 40), 0.3)
    return mono_bytes(out, RATE, 0.2)


def emote_dance(variant):
    rng = random.Random(SEED + 295 + variant)
    out = _zeros(1.1)
    for k in range(4):
        base = rng.uniform(600, 800)
        _put(out, 0.05 + 0.25 * k, _burst(rng, 0.02, 3000, 0.9, 0.0003, 200), 0.6)
        _put(out, 0.05 + 0.25 * k, _resonator([base, base * 1.5], [70, 90], [0.3, 0.15], 0.1), 0.4)
        if k % 2:
            _put(out, 0.12 + 0.25 * k, _swish(rng, 0.12, 1500, 2600), 0.4)
    return mono_bytes(out, RATE, 0.3)


def emote_hug():
    rng = random.Random(SEED + 297)
    out = _zeros(0.8)
    _put(out, 0.0, _swish(rng, 0.3, 700, 1400), 0.9)
    for k in range(2):
        _put(out, 0.38 + 0.16 * k, _low(_burst(rng, 0.08, 400, 0.8, 0.002, 40), 600), 0.8)
    return mono_bytes(out, RATE, 0.22)


# ------------------------------------------------------------
# Work, money and the farm
# ------------------------------------------------------------

def coins(variant):
    rng = random.Random(SEED + 300 + variant)
    left, right = _blank(0.6)
    for k in range(4):
        start = 0.08 * k + rng.uniform(0.0, 0.03)
        frequency = rng.uniform(2300, 3400)
        partials = ((1, 1.0), (2.76, 0.45), (5.40, 0.2))
        _add(left, right, start, _bell(frequency, 0.3, 18.0 + 3 * k, partials=partials),
             rng.uniform(-0.4, 0.4), 0.7)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.4)


def register():
    """A shop's till: the drawer slides out, and the bell rings."""
    rng = random.Random(SEED + 310)
    left, right = _blank(0.9)
    drawer = _low(_burst(rng, 0.25, 600, 0.8, 0.02, 10), 900)
    _add(left, right, 0.0, drawer, -0.2, 0.8)
    _add(left, right, 0.22, _thump(80, 0.1, 40), -0.2, 0.6)
    partials = ((1, 1.0), (2.4, 0.5), (3.9, 0.25))
    _add(left, right, 0.26, _bell(2250, 0.6, 7.0, partials=partials), 0.2, 0.7)
    _add(left, right, 0.3, _bell(2900, 0.5, 8.0, partials=partials), 0.25, 0.4)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.4)


def _soft_square_notes(notes, gap, seconds, decay):
    left, right = _blank(seconds)
    for i, note in enumerate(notes):
        _add(left, right, i * gap, _soft_square(note, 0.35, decay), -0.3 + 0.6 * i / max(1, len(notes) - 1), 0.6)
    return left, right


def success():
    left, right = _blank(0.7)
    for i, note in enumerate((C5, E5, G5, C6)):
        _add(left, right, i * 0.07, _soft_square(note, 0.35, 9.0), -0.3 + 0.2 * i, 0.6)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.4)


def fail():
    left, right = _blank(0.6)
    for start, frequency in ((0.0, 150.0), (0.25, 118.0)):
        count = int(0.26 * RATE)
        buzz = []
        for n in range(count):
            t = n / RATE
            f = frequency * (1 - 0.08 * t / 0.26)
            x = TAU * f * t
            env = min(1.0, t / 0.01) * max(0.0, 1 - t / 0.26)
            buzz.append(env * sum(math.sin(k * x) / k for k in range(1, 7)))
        _add(left, right, start, buzz, 0.0, 0.8)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.4)


def error():
    left, right = _blank(0.26)
    for start in (0.0, 0.12):
        _add(left, right, start, _soft_square(330.0, 0.09, 25.0), 0.0)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.35)


def mission():
    left, right = _blank(0.36)
    _add(left, right, 0.0, _soft_square(1200.0, 0.12, 30.0), -0.2, 0.7)
    _add(left, right, 0.13, _soft_square(1600.0, 0.18, 22.0), 0.2, 0.7)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.35)


def task():
    """A task begins: an instrument wakes, bee-doo."""
    left, right = _blank(0.5)
    _add(left, right, 0.0, _soft_square(740.0, 0.14, 18.0), -0.3, 0.6)
    _add(left, right, 0.15, _soft_square(1109.0, 0.22, 12.0), 0.3, 0.6)
    _add(left, right, 0.0, _chirp(300, 900, 0.12, decay=10), 0.0, 0.2)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.32)


def mine(variant):
    """The drill whirs into the rock, and it cracks."""
    rng = random.Random(SEED + 320 + variant)
    out = _zeros(1.0)
    whirr = []
    phase = 0.0
    base = rng.uniform(170, 220)
    grit = _band(_noise(int(0.55 * RATE), rng), 3000, 1.0)
    for i in range(int(0.55 * RATE)):
        t = i / RATE
        phase += TAU * base * (1 + 0.1 * math.sin(TAU * 7 * t)) / RATE
        saw = 2 * ((phase / TAU) % 1.0) - 1
        env = min(1.0, t / 0.06)
        whirr.append((0.4 * saw + 0.6 * grit[i] * (0.6 + 0.4 * math.sin(TAU * 23 * t))) * env)
    _put(out, 0.0, _low(whirr, 2500), 0.8)
    crack = _burst(rng, 0.2, 1800, 0.5, 0.0005, 25)
    _put(out, 0.52, crack, 1.0)
    _put(out, 0.52, _thump(60, 0.25, 16), 1.0)
    debris = _grains(rng, 0.3, 12, 2000, 6000, env=lambda a: math.exp(-4 * a))
    _put(out, 0.58, debris, 0.5)
    return mono_bytes(out, RATE, 0.4)


def rare():
    """Something rare: a shimmer rising across both ears."""
    left, right = _blank(1.3)
    for i, note in enumerate((1318.5, 1661.2, 1975.5, 2637.0)):
        _add(left, right, 0.09 * i, _bell(note, 0.8, 5.0, partials=((1, 1.0), (2.01, 0.3))),
             -0.6 + 0.4 * i, 0.5)
    rng = random.Random(SEED + 330)
    for k in range(10):
        _add(left, right, 0.3 + 0.07 * k, _bell(rng.uniform(3000, 5000), 0.2, 20.0), rng.uniform(-0.8, 0.8), 0.12)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.08), RATE, 0.42)


def plant():
    rng = random.Random(SEED + 340)
    out = _zeros(0.55)
    for k in range(2):
        _put(out, 0.05 + 0.2 * k, _low(_burst(rng, 0.1, 350, 0.8, 0.003, 30), 500), 1.0)
        _put(out, 0.07 + 0.2 * k, _grains(rng, 0.1, 10, 1500, 4000), 0.3)
    return mono_bytes(out, RATE, 0.3)


def water():
    """Pouring from a can: a bubbling stream."""
    rng = random.Random(SEED + 350)
    n = int(1.2 * RATE)
    stream = _band(_noise(n, rng), 1100, 1.5)
    out = []
    level = 0.0
    for i, v in enumerate(stream):
        t = i / RATE
        if i % 180 == 0:
            level = rng.uniform(0.5, 1.0)
        env = min(1.0, t / 0.1) * min(1.0, (1.2 - t) / 0.25)
        out.append(v * level * env)
    for _k in range(14):
        _put(out, rng.uniform(0.05, 1.05), _chirp(rng.uniform(600, 1100), rng.uniform(1300, 2000), 0.02, decay=80), 0.3)
    return mono_bytes(out, RATE, 0.3)


def harvest(variant):
    rng = random.Random(SEED + 360 + variant)
    out = _zeros(0.7)
    _put(out, 0.0, _grains(rng, 0.35, 45, 2000, 6000, env=lambda a: math.sin(math.pi * a)), 0.8)
    snap = _high(_burst(rng, 0.01, 2500, 1.2, 0.0003, 400), 1200)
    _put(out, 0.38, snap, 1.0)
    _put(out, 0.38, _resonator([1450 + 100 * variant], [90], [0.4], 0.1), 0.4)
    return mono_bytes(out, RATE, 0.32)


def ripe():
    left, right = _blank(0.7)
    pop = _burst(random.Random(SEED + 370), 0.04, 900, 1.5, 0.001, 80)
    _add(left, right, 0.0, pop, 0.0, 0.6)
    _add(left, right, 0.08, _bell(E5 * 2, 0.4, 8.0), -0.2, 0.4)
    _add(left, right, 0.2, _bell(G5 * 2, 0.45, 7.0), 0.2, 0.4)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.32)


def levelup():
    left, right = _blank(1.6)
    for i, note in enumerate((C5, E5, G5, C6, E5 * 2)):
        _add(left, right, i * 0.09, _soft_square(note, 0.5, 5.0), -0.6 + 0.3 * i, 0.55)
    _add(left, right, 0.45, _bell(C6 * 2, 1.0, 3.0), 0.0, 0.3)
    _echo(left, right, RATE, ((0.07, 0.25, 1), (0.13, 0.18, -1)))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.1), RATE, 0.42)


def achievement():
    """An achievement: a bright rising arpeggio that lands on a shimmering chord."""
    left, right = _blank(1.8)
    for i, note in enumerate((G5 / 2, C5, E5, G5, C6)):
        _add(left, right, i * 0.07, _soft_square(note, 0.35, 7.0), -0.5 + 0.25 * i, 0.45)
    for k, (note, position) in enumerate(((C6, -0.4), (E5 * 2, 0.0), (G5 * 2, 0.4))):
        _add(left, right, 0.38 + 0.02 * k, _bell(note, 1.3, 2.6), position, 0.35)
    _echo(left, right, RATE, ((0.09, 0.28, 1), (0.17, 0.2, -1), (0.26, 0.12, 1)))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.2), RATE, 0.42)


def daily():
    """The daily bonus: a little shower of coins from left to right."""
    rng = random.Random(SEED + 380)
    left, right = _blank(1.2)
    for k in range(9):
        _add(left, right, 0.07 * k + rng.uniform(0, 0.02),
             _bell(rng.uniform(2400, 3500), 0.3, 16.0, partials=((1, 1.0), (2.76, 0.4))), -0.8 + 0.2 * k, 0.5)
    _add(left, right, 0.7, _bell(C6, 0.5, 5.0), 0.0, 0.3)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.05), RATE, 0.4)


# ------------------------------------------------------------
# Things
# ------------------------------------------------------------

def equip(variant):
    rng = random.Random(SEED + 390 + variant)
    out = _zeros(0.3)
    _put(out, 0.0, _high(_burst(rng, 0.006, 3500, 0.9, 0.0002, 600), 2000), 1.0)
    _put(out, 0.0, _resonator([2900 + 200 * variant, 4300], [80, 120], [0.4, 0.2], 0.1), 0.5)
    _put(out, 0.05, _swish(rng, 0.12, 1500, 3000), 0.4)
    return mono_bytes(out, RATE, 0.3)


def gadget():
    left, right = _blank(0.3)
    _add(left, right, 0.0, _chirp(1200, 2400, 0.06, decay=15), -0.2, 0.6)
    _add(left, right, 0.08, _chirp(1500, 2800, 0.06, decay=15), 0.2, 0.6)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.3)


def scan():
    """A scanner sweeping the rooms around you: pings answered from each side."""
    rng = random.Random(SEED + 400)
    left, right = _blank(1.1)
    for i in range(int(0.9 * RATE)):
        t = i / RATE
        gl, gr = _pan(-0.9 + 2.0 * t / 0.9)
        v = rng.uniform(-1, 1) * 0.05 * math.sin(math.pi * t / 0.9)
        left[i] += v * gl
        right[i] += v * gr
    for k, position in enumerate((-0.7, 0.0, 0.7)):
        _add(left, right, 0.1 + 0.3 * k, _bell(900, 0.3, 10.0), position, 0.5)
        _add(left, right, 0.2 + 0.3 * k, _bell(900, 0.25, 14.0), -position, 0.15)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.32)


def air():
    """The suit's air warning: three urgent beeps and a hiss."""
    rng = random.Random(SEED + 410)
    left, right = _blank(1.0)
    for k in range(3):
        _add(left, right, 0.12 * k, _soft_square(1500, 0.09, 8.0), 0.0, 0.6)
    hiss = _high(_noise(int(0.4 * RATE), rng), 3000)
    env = _env(len(hiss), 0.02, 8.0)
    _add(left, right, 0.45, [h * e for h, e in zip(hiss, env)], 0.0, 0.3)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.35)


def rescue():
    """The tow drone: a two-tone alarm, a winch, and the airlock's clunk."""
    rng = random.Random(SEED + 420)
    left, right = _blank(2.2)
    for k in range(3):
        _add(left, right, 0.3 * k, _soft_square(700, 0.14, 4.0), -0.3, 0.4)
        _add(left, right, 0.3 * k + 0.15, _soft_square(950, 0.14, 4.0), 0.3, 0.4)
    winch = []
    phase = 0.0
    for i in range(int(0.9 * RATE)):
        t = i / RATE
        phase += TAU * (140 + 60 * t) / RATE
        winch.append(math.sin(phase) * 0.3 + rng.uniform(-1, 1) * 0.1)
    _add(left, right, 0.95, _low(winch, 1200), 0.0, 0.6)
    _add(left, right, 1.9, _thump(60, 0.3, 14), 0.0, 1.0)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.05), RATE, 0.4)


def gulp():
    rng = random.Random(SEED + 430)
    out = _zeros(0.6)
    sip = _burst(rng, 0.2, lambda t: 700 + 1500 * t, 3.0, 0.02, 12)
    _put(out, 0.0, sip, 0.8)
    _put(out, 0.3, _chirp(260, 150, 0.1, decay=25), 0.9)
    return mono_bytes(out, RATE, 0.26)


def crunch(variant):
    rng = random.Random(SEED + 440 + variant)
    out = _zeros(0.5)
    for k in range(3):
        bite = _grains(rng, 0.09, 25, 2500, 7000, grain=0.0008, env=lambda a: math.exp(-5 * a))
        _put(out, 0.02 + 0.15 * k + rng.uniform(-0.01, 0.01), bite, 1.0 - 0.15 * k)
    return mono_bytes(out, RATE, 0.3)


def pet_robot():
    rng = random.Random(SEED + 450)
    out = _zeros(0.6)
    for k in range(3):
        f = rng.choice((880, 1175, 1318, 1568, 1760))
        _put(out, 0.12 * k, _soft_square(f, 0.1, 25), 0.6)
    return mono_bytes(out, RATE, 0.26)


def pet_cat():
    """A purr, and a small mrrp."""
    rng = random.Random(SEED + 451)
    n = int(1.0 * RATE)
    noise = _low(_noise(n, rng), 400)
    purr = [v * (0.5 + 0.5 * math.sin(TAU * 26 * i / RATE)) * min(1.0, i / 2000) for i, v in enumerate(noise)]
    out = _zeros(1.3)
    _put(out, 0.0, purr, 1.0)
    mrrp = [a * b for a, b in zip(_chirp(420, 620, 0.18, shape="arch"),
                                  [0.6 + 0.4 * math.sin(TAU * 30 * i / RATE) for i in range(int(0.18 * RATE))])]
    _put(out, 1.05, mrrp, 0.5)
    return mono_bytes(out, RATE, 0.26)


def bell():
    """The star bell: three soft tones, low, middle and high, drifting left to
    right under the temple's dome."""
    seconds = 3.2
    left, right = _blank(seconds)
    partials = ((1, 1.0), (2.0, 0.35), (2.76, 0.2), (5.4, 0.06))
    for k, (note, position) in enumerate(((392.0, -0.7), (523.25, 0.0), (659.25, 0.7))):
        _add(left, right, 0.45 * k, _bell(note, 2.3, 1.9, partials=partials), position, 0.6)
    left = _reverb(left, RATE, size=1.3, wet=0.5)
    right = _reverb(right, RATE, size=1.25, wet=0.5)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.3), RATE, 0.4)


def lantern():
    """A lantern is lit: a small whoosh, a warm chime, a crackle."""
    rng = random.Random(SEED + 460)
    left, right = _blank(1.8)
    whoosh = _burst(rng, 0.3, lambda t: 350 + 900 * t, 0.9, 0.04, 6)
    _add(left, right, 0.0, whoosh, 0.0, 0.8)
    chime = _bell(440.0, 1.4, 2.6, partials=((1, 1.0), (2.0, 0.3), (3.0, 0.1)))
    _add(left, right, 0.2, chime, 0.0, 0.5)
    crackle = _grains(rng, 0.6, 12, 2000, 5000, env=lambda a: 1 - a)
    _add(left, right, 0.3, crackle, 0.2, 0.2)
    left = _reverb(left, RATE, size=1.0, wet=0.35)
    right = _reverb(right, RATE, size=0.95, wet=0.35)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.2), RATE, 0.35)


# ------------------------------------------------------------
# Shuttles
# ------------------------------------------------------------

def _engine(seconds, swell):
    """Engines: a rumble and a roar, each side its own; swell(t) 0-1 gives the power."""
    rng = random.Random(SEED + 4)
    left, right = _blank(seconds)
    low_l = low_r = 0.0
    filt_l, filt_r = _SVF(0.8), _SVF(0.8)
    for i in range(len(left)):
        t = i / RATE
        power = swell(t)
        common = rng.uniform(-1, 1)
        nl, nr = rng.uniform(-1, 1), rng.uniform(-1, 1)
        a = _lowpass_coeff(80 + 220 * power, RATE)
        low_l += a * ((common + nl) * 0.5 - low_l)
        low_r += a * ((common + nr) * 0.5 - low_r)
        centre = 300 + 900 * power
        roar_l = filt_l.band_pass(nl, centre, RATE)
        roar_r = filt_r.band_pass(nr, centre, RATE)
        left[i] = (low_l * 6 + roar_l * 0.6 * power) * (0.1 + 0.9 * power)
        right[i] = (low_r * 6 + roar_r * 0.6 * power) * (0.1 + 0.9 * power)
    return left, right


def _clunk(frequency=70.0, seconds=0.2):
    return [0.9 * math.exp(-(i / RATE) / 0.05) * math.sin(TAU * frequency * i / RATE)
            for i in range(int(seconds * RATE))]


def launch():
    seconds = 3.0

    def swell(t):
        x = max(0.0, min(1.0, (t - 0.25) / 2.0))
        return x * x * (3 - 2 * x) * (1 - max(0.0, t - 2.5) / 0.5 * 0.4)

    left, right = _engine(seconds, swell)
    _add(left, right, 0.02, _clunk(60.0), -0.4, 0.8)
    _add(left, right, 0.08, _clunk(75.0), 0.4, 0.6)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.3), RATE, 0.5)


def landing():
    seconds = 1.5

    def swell(t):
        return max(0.0, 0.8 - 0.8 * t / 1.1)

    left, right = _engine(seconds, swell)
    rng = random.Random(SEED + 5)
    for start, position in ((0.35, -0.6), (0.6, 0.6), (0.8, -0.2)):
        filt = _SVF(1.0)
        puff = [filt.band_pass(rng.uniform(-1, 1), 2500, RATE) * math.exp(-(i / RATE) / 0.05)
                for i in range(int(0.15 * RATE))]
        _add(left, right, start, puff, position, 1.2)
    _add(left, right, 1.15, _clunk(65.0, 0.3), 0.0, 1.2)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.08), RATE, 0.5)


TONE_NOTES = {1: (C5, -0.8), 2: (E5, -0.3), 3: (G5, 0.3), 4: (C6, 0.8)}


def tone(number):
    frequency, position = TONE_NOTES[number]
    left, right = _blank(0.36)
    _add(left, right, 0.0, _soft_square(frequency, 0.34, 6.0), position)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.03), RATE, 0.45)


# ------------------------------------------------------------
# Ambience loops
# ------------------------------------------------------------

def _seamless(left, right, rate=LOOP_RATE, seconds=LOOP_SECONDS, overlap=LOOP_OVERLAP,
              equal_power=True):
    """Made `overlap` seconds too long: crossfade that tail into the start,
    so the loop's end runs straight into its beginning. Equal power suits
    noise (its two ends are unrelated); a straight crossfade suits steady
    tones (their two ends are the same wave)."""
    length = int(seconds * rate)
    width = int(overlap * rate)
    out_l, out_r = left[:length], right[:length]
    for i in range(width):
        w = (i + 0.5) / width
        if equal_power:
            a, b = math.sin(w * math.pi / 2), math.cos(w * math.pi / 2)
        else:
            a, b = w, 1.0 - w
        out_l[i] = left[i] * a + left[length + i] * b
        out_r[i] = right[i] * a + right[length + i] * b
    return out_l, out_r


def _loop_blank(rate=LOOP_RATE):
    n = int((LOOP_SECONDS + LOOP_OVERLAP) * rate)
    return [0.0] * n, [0.0] * n


def amb_vent():
    rng = random.Random(SEED + 10)
    left, right = _loop_blank()
    low_l = low_r = 0.0
    air_l, air_r = _SVF(0.7), _SVF(0.7)
    a = _lowpass_coeff(180, LOOP_RATE)
    for i in range(len(left)):
        t = i / LOOP_RATE
        common = rng.uniform(-1, 1)
        nl, nr = rng.uniform(-1, 1), rng.uniform(-1, 1)
        low_l += a * ((common + nl) * 0.5 - low_l)
        low_r += a * ((common + nr) * 0.5 - low_r)
        hum = 0.05 * math.sin(TAU * 60 * t) + 0.025 * math.sin(TAU * 120 * t)
        left[i] = low_l * 4 + air_l.band_pass(nl, 900, LOOP_RATE) * 0.25 + hum
        right[i] = low_r * 4 + air_r.band_pass(nr, 950, LOOP_RATE) * 0.25 + hum
    return wav_bytes(*_seamless(left, right), LOOP_RATE, 0.5)


def amb_cantina():
    rng = random.Random(SEED + 11)
    left, right = _loop_blank()
    n = len(left)
    # People talking around you: each a voice-like band of noise, its
    # syllables an envelope that rises and falls a few times a second.
    for voice in range(5):
        position = -0.9 + 1.8 * voice / 4
        centre = rng.uniform(380, 900)
        filt_a, filt_b = _SVF(3.0), _SVF(4.0)
        gl, gr = _pan(position)
        loudness = rng.uniform(0.6, 1.0)
        syllable = 0.0
        next_change = 0
        target = 0.0
        for i in range(n):
            if i >= next_change:
                talking = rng.random() < 0.7
                target = rng.uniform(0.3, 1.0) if talking else 0.0
                next_change = i + int(rng.uniform(0.08, 0.25) * LOOP_RATE)
            syllable += 0.004 * (target - syllable)
            noise = rng.uniform(-1, 1)
            v = (filt_a.band_pass(noise, centre, LOOP_RATE)
                 + 0.5 * filt_b.band_pass(noise, centre * 2.4, LOOP_RATE))
            v *= syllable * loudness
            left[i] += v * gl
            right[i] += v * gr
    # A glass clinking now and then.
    for _k in range(4):
        start = rng.uniform(0.2, LOOP_SECONDS - 0.4)
        clink = _bell(rng.uniform(2600, 4200), 0.3, 22.0, rate=LOOP_RATE,
                      partials=((1, 1.0), (2.7, 0.4)))
        _add(left, right, start, clink, rng.uniform(-0.8, 0.8), 0.08, rate=LOOP_RATE)
    # The room itself.
    low = 0.0
    a = _lowpass_coeff(150, LOOP_RATE)
    for i in range(n):
        low += a * (rng.uniform(-1, 1) - low)
        left[i] += low * 1.5
        right[i] += low * 1.5
    return wav_bytes(*_seamless(left, right), LOOP_RATE, 0.5)


def amb_engine():
    rng = random.Random(SEED + 12)
    left, right = _loop_blank()
    low_l = low_r = 0.0
    a = _lowpass_coeff(110, LOOP_RATE)
    for i in range(len(left)):
        t = i / LOOP_RATE
        # 40 and 40.5 Hz beat twice a loop; the pulse is once a second.
        pulse = 0.75 + 0.25 * math.sin(TAU * 1.0 * t) ** 2
        thrum_l = (math.sin(TAU * 40 * t) + 0.6 * math.sin(TAU * 80 * t)
                   + 0.25 * math.sin(TAU * 120 * t))
        thrum_r = (math.sin(TAU * 40.5 * t) + 0.6 * math.sin(TAU * 81 * t)
                   + 0.25 * math.sin(TAU * 121.5 * t))
        common = rng.uniform(-1, 1)
        low_l += a * ((common + rng.uniform(-1, 1)) * 0.5 - low_l)
        low_r += a * ((common + rng.uniform(-1, 1)) * 0.5 - low_r)
        left[i] = (thrum_l * 0.35 + low_l * 5) * pulse
        right[i] = (thrum_r * 0.35 + low_r * 5) * pulse
    return wav_bytes(*_seamless(left, right, equal_power=False), LOOP_RATE, 0.55)


def amb_garden():
    rng = random.Random(SEED + 13)
    left, right = _loop_blank()
    n = len(left)
    # Water: many small bubbles, each a quick upward chirp.
    for _k in range(70):
        start = rng.uniform(0.0, LOOP_SECONDS + LOOP_OVERLAP - 0.05)
        base = rng.uniform(500, 1300)
        length = rng.uniform(0.015, 0.04)
        phase = 0.0
        bubble = []
        for i in range(int(length * LOOP_RATE)):
            t = i / LOOP_RATE
            phase += TAU * base * (1 + 1.5 * t / length) / LOOP_RATE
            bubble.append(math.sin(phase) * math.sin(math.pi * t / length))
        _add(left, right, start, bubble, rng.uniform(-0.7, 0.7), rng.uniform(0.1, 0.3),
             rate=LOOP_RATE)
    # Fans, soft and wide.
    low_l = low_r = 0.0
    a = _lowpass_coeff(400, LOOP_RATE)
    for i in range(n):
        low_l += a * (rng.uniform(-1, 1) - low_l)
        low_r += a * (rng.uniform(-1, 1) - low_r)
        left[i] += low_l * 0.6
        right[i] += low_r * 0.6
    return wav_bytes(*_seamless(left, right), LOOP_RATE, 0.45)


def amb_deck():
    rng = random.Random(SEED + 14)
    left, right = _loop_blank()
    hiss_l = hiss_r = 0.0
    a = _lowpass_coeff(3000, LOOP_RATE)
    for i in range(len(left)):
        t = i / LOOP_RATE
        swell = 0.6 + 0.4 * math.sin(TAU * 0.25 * t)
        chord_l = (math.sin(TAU * 110 * t) + 0.5 * math.sin(TAU * 165 * t)
                   + 0.3 * math.sin(TAU * 220.25 * t))
        chord_r = (math.sin(TAU * 110.25 * t) + 0.5 * math.sin(TAU * 165.25 * t)
                   + 0.3 * math.sin(TAU * 220 * t))
        hiss_l += a * (rng.uniform(-1, 1) - hiss_l)
        hiss_r += a * (rng.uniform(-1, 1) - hiss_r)
        left[i] = chord_l * 0.3 * swell + hiss_l * 0.25
        right[i] = chord_r * 0.3 * swell + hiss_r * 0.25
    return wav_bytes(*_seamless(left, right, equal_power=False), LOOP_RATE, 0.4)


def amb_space():
    """Outside, in a suit: your own slow breathing and the suit's fan."""
    rng = random.Random(SEED + 15)
    left, right = _loop_blank()
    n = len(left)
    breath_l, breath_r = _SVF(0.6), _SVF(0.6)
    for i in range(n):
        t = (i / LOOP_RATE) % LOOP_SECONDS
        # In for 1.4 s, a pause, out for 1.8 s, a pause: one breath per loop.
        if t < 1.4:
            level, centre = math.sin(math.pi * t / 1.4) ** 1.5, 900 + 300 * t
        elif 1.6 < t < 3.4:
            level, centre = math.sin(math.pi * (t - 1.6) / 1.8) ** 1.2 * 0.8, 800 - 200 * (t - 1.6)
        else:
            level, centre = 0.0, 800
        noise = rng.uniform(-1, 1)
        fan = 0.04 * math.sin(TAU * 125 * i / LOOP_RATE) + 0.02 * math.sin(TAU * 250 * i / LOOP_RATE)
        left[i] = breath_l.band_pass(noise, centre, LOOP_RATE) * level * 0.8 + fan
        right[i] = breath_r.band_pass(noise, centre * 1.02, LOOP_RATE) * level * 0.8 + fan
    return wav_bytes(*_seamless(left, right), LOOP_RATE, 0.45)


def amb_belt():
    """The Belt Platform: machinery thrumming, pebbles ticking on the dome."""
    rng = random.Random(SEED + 16)
    left, right = _loop_blank()
    n = len(left)
    for i in range(n):
        t = i / LOOP_RATE
        wobble = 0.8 + 0.2 * math.sin(TAU * 0.5 * t)
        left[i] = (math.sin(TAU * 50 * t) + 0.5 * math.sin(TAU * 100 * t)) * 0.12 * wobble
        right[i] = (math.sin(TAU * 50 * t) + 0.5 * math.sin(TAU * 100.25 * t)) * 0.12 * wobble
    low = 0.0
    a = _lowpass_coeff(200, LOOP_RATE)
    for i in range(n):
        low += a * (rng.uniform(-1, 1) - low)
        left[i] += low * 1.2
        right[i] += low * 1.2
    for _k in range(26):
        start = rng.uniform(0.0, LOOP_SECONDS + LOOP_OVERLAP - 0.05)
        tick = _bell(rng.uniform(2500, 4500), 0.05, 90.0, rate=LOOP_RATE, partials=((1, 1.0), (2.3, 0.3)))
        _add(left, right, start, tick, rng.uniform(-0.9, 0.9), rng.uniform(0.05, 0.15), rate=LOOP_RATE)
    return wav_bytes(*_seamless(left, right), LOOP_RATE, 0.42)


def amb_venue():
    """A venue: a warm, slow chord, and now and then a far-off chime."""
    rng = random.Random(SEED + 17)
    left, right = _loop_blank()
    # 55 Hz and its 4:5:6 relations, detuned by 0.25 Hz: a whole number of cycles per 4 s.
    notes = (110.0, 137.5, 165.0, 220.0)
    for i in range(len(left)):
        t = i / LOOP_RATE
        swell = 0.7 + 0.3 * math.sin(TAU * 0.25 * t)
        left[i] = sum(math.sin(TAU * f * t) / (k + 1) for k, f in enumerate(notes)) * 0.2 * swell
        right[i] = sum(math.sin(TAU * (f + 0.25) * t) / (k + 1) for k, f in enumerate(notes)) * 0.2 * swell
    for start, note, position in ((0.9, 880.0, -0.5), (2.9, 1318.5, 0.5)):
        _add(left, right, start, _bell(note, 1.0, 3.0, rate=LOOP_RATE), position, 0.05, rate=LOOP_RATE)
        _add(left, right, start + LOOP_SECONDS, _bell(note, 0.5, 3.0, rate=LOOP_RATE), position, 0.05,
             rate=LOOP_RATE)
    return wav_bytes(*_seamless(left, right, equal_power=False), LOOP_RATE, 0.36)


def amb_mall():
    """The Mall Ring: a bright, airy hall, soft music far off, footsteps and a fountain."""
    rng = random.Random(SEED + 18)
    left, right = _loop_blank()
    n = len(left)
    # Soft music from the ceiling: a slow major seventh chord, whole cycles in 4 s.
    notes = (220.0, 277.5, 330.0, 415.0)
    for i in range(n):
        t = i / LOOP_RATE
        swell = 0.75 + 0.25 * math.sin(TAU * 0.25 * t)
        left[i] = sum(math.sin(TAU * f * t) / (k + 1.5) for k, f in enumerate(notes)) * 0.06 * swell
        right[i] = sum(math.sin(TAU * (f + 0.5) * t) / (k + 1.5) for k, f in enumerate(notes)) * 0.06 * swell
    # The fountain's drops, left of centre, and the hall's airy hush.
    drops = _SVF(1.5)
    hush_l, hush_r = _SVF(0.6), _SVF(0.6)
    for i in range(n):
        noise = rng.uniform(-1, 1)
        v = drops.band_pass(noise, 2500, LOOP_RATE) * (0.5 + 0.5 * math.sin(TAU * 1.5 * i / LOOP_RATE)) * 0.05
        left[i] += v * 0.9 + hush_l.band_pass(rng.uniform(-1, 1), 700, LOOP_RATE) * 0.12
        right[i] += v * 0.4 + hush_r.band_pass(rng.uniform(-1, 1), 740, LOOP_RATE) * 0.12
    # Shoppers' footsteps crossing the hall, and a far-off voice or two.
    for _k in range(10):
        start = rng.uniform(0.1, LOOP_SECONDS - 0.2)
        step = [v * math.exp(-i / (0.02 * LOOP_RATE)) for i, v in
                enumerate(rng.uniform(-1, 1) for _ in range(int(0.06 * LOOP_RATE)))]
        _add(left, right, start, step, rng.uniform(-0.9, 0.9), 0.05, rate=LOOP_RATE)
    return wav_bytes(*_seamless(left, right), LOOP_RATE, 0.36)


def amb_casino():
    """The Casino Corner: a low murmur, carpet-soft, and the machines' little chimes."""
    rng = random.Random(SEED + 19)
    left, right = _loop_blank()
    n = len(left)
    for voice in range(4):
        position = -0.8 + 1.6 * voice / 3
        centre = rng.uniform(350, 800)
        filt = _SVF(3.0)
        gl, gr = _pan(position)
        syllable, target, next_change = 0.0, 0.0, 0
        for i in range(n):
            if i >= next_change:
                target = rng.uniform(0.2, 0.8) if rng.random() < 0.6 else 0.0
                next_change = i + int(rng.uniform(0.1, 0.3) * LOOP_RATE)
            syllable += 0.004 * (target - syllable)
            v = filt.band_pass(rng.uniform(-1, 1), centre, LOOP_RATE) * syllable * 0.7
            left[i] += v * gl
            right[i] += v * gr
    # The slot machines along the wall: little arpeggios and a soft ring now and then.
    for start, root_note, position in ((0.4, C5, -0.7), (1.7, E5, 0.6), (2.9, G5, -0.3)):
        for k, ratio in enumerate((1.0, 1.25, 1.5, 2.0)):
            _add(left, right, start + 0.06 * k, _bell(root_note * ratio, 0.25, 12.0, rate=LOOP_RATE),
                 position, 0.05, rate=LOOP_RATE)
    # Chips clicking on a table.
    for _k in range(6):
        start = rng.uniform(0.1, LOOP_SECONDS - 0.2)
        for j in range(rng.randint(2, 4)):
            click = _bell(rng.uniform(3000, 4200), 0.05, 60.0, rate=LOOP_RATE, partials=((1, 1.0), (1.9, 0.5)))
            _add(left, right, start + 0.03 * j, click, rng.uniform(-0.6, 0.6), 0.04, rate=LOOP_RATE)
    low = 0.0
    a = _lowpass_coeff(140, LOOP_RATE)
    for i in range(n):
        low += a * (rng.uniform(-1, 1) - low)
        left[i] += low * 1.3
        right[i] += low * 1.3
    return wav_bytes(*_seamless(left, right), LOOP_RATE, 0.42)


# ------------------------------------------------------------
# Events: a sting for each kind, so an event is known before its words
# ------------------------------------------------------------

def event_start():
    """Something is happening: three bright notes climbing across, a shimmer after."""
    left, right = _blank(1.4)
    for i, (note, position) in enumerate(((G5, -0.6), (C6, 0.0), (E5 * 2, 0.6))):
        _add(left, right, i * 0.11, _soft_square(note, 0.4, 6.0), position, 0.5)
        _add(left, right, i * 0.11 + 0.02, _bell(note * 2, 0.8, 4.0), position, 0.2)
    _echo(left, right, RATE, ((0.12, 0.3, 1), (0.23, 0.2, -1)))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.15), RATE, 0.42)


def event_end():
    """It's over: two soft notes going down."""
    left, right = _blank(1.0)
    _add(left, right, 0.0, _bell(E5 * 2, 0.8, 4.5), 0.3, 0.5)
    _add(left, right, 0.16, _bell(C6 / 1.0, 0.8, 4.5), -0.3, 0.5)
    _echo(left, right, RATE, ((0.1, 0.25, 1),))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.15), RATE, 0.36)


def event_party():
    """A party: a paper horn, a scatter of little bells like confetti."""
    rng = random.Random(SEED + 600)
    left, right = _blank(1.4)
    horn = [v * 0.8 for v in _chirp(520, 780, 0.35, shape="arch")]
    horn = [v + 0.3 * w for v, w in zip(horn, _chirp(1040, 1560, 0.35, shape="arch"))]
    _add(left, right, 0.0, horn, 0.0, 0.5)
    for k in range(14):
        _add(left, right, 0.3 + 0.05 * k + rng.uniform(0, 0.03),
             _bell(rng.uniform(1800, 3200), 0.25, 14.0, partials=((1, 1.0), (2.7, 0.3))), rng.uniform(-0.9, 0.9), 0.3)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.1), RATE, 0.42)


def event_storm():
    """A storm: a low rumble rolling across, and electric crackles."""
    rng = random.Random(SEED + 601)
    left, right = _blank(1.8)
    rumble = _low(_noise(int(1.8 * RATE), rng), 90)
    env = _env(len(rumble), 0.25, 1.5)
    rumble = [v * e * 6 for v, e in zip(rumble, env)]
    for i in range(len(rumble)):
        gl, gr = _pan(-0.8 + 1.6 * i / len(rumble))
        left[i] += rumble[i] * gl
        right[i] += rumble[i] * gr
    crackle = _grains(rng, 1.2, 60, 2500, 6000)
    _add(left, right, 0.2, crackle, 0.3, 0.6)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.2), RATE, 0.45)


def event_boss():
    """The runaway drone: a two-tone warning and a heavy clank."""
    left, right = _blank(1.6)
    for k in range(3):
        _add(left, right, k * 0.36, _soft_square(620, 0.16, 8.0), -0.4, 0.45)
        _add(left, right, k * 0.36 + 0.18, _soft_square(465, 0.16, 8.0), 0.4, 0.45)
    clank = _resonator((180, 420, 910), (14, 22, 30), (1.0, 0.5, 0.3), 0.5)
    _add(left, right, 1.08, clank, 0.0, 0.8)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.1), RATE, 0.45)


def event_meteor():
    """A meteor shower: whooshes streaking across, and far-off thuds."""
    rng = random.Random(SEED + 602)
    left, right = _blank(1.8)
    for k, (start, a, b) in enumerate(((0.0, -0.9, 0.6), (0.35, 0.8, -0.5), (0.7, -0.4, 0.9))):
        n = int(0.5 * RATE)
        whoosh = _band(_noise(n, rng), 1800 - 400 * k, 1.5)
        for i, v in enumerate(whoosh):
            position = a + (b - a) * i / n
            gl, gr = _pan(position)
            e = math.sin(math.pi * i / n)
            j = int(start * RATE) + i
            if j < len(left):
                left[j] += v * e * gl * 0.5
                right[j] += v * e * gr * 0.5
        _add(left, right, start + 0.5, _thump(70, 0.3, 9.0), b, 0.4)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.2), RATE, 0.42)


def fireworks():
    """Fireworks: a whistle climbing, then a burst and a crackle, left and right."""
    rng = random.Random(SEED + 603)
    left, right = _blank(2.4)
    for start, position in ((0.0, -0.6), (0.8, 0.6)):
        _add(left, right, start, [v * 0.4 for v in _chirp(700, 2200, 0.5, shape="arch")], position * 0.5, 0.4)
        _add(left, right, start + 0.55, _burst(rng, 0.5, 300, 0.8, 0.002, 9.0), position, 0.9)
        _add(left, right, start + 0.65, _grains(rng, 0.8, 50, 3000, 7000), position, 0.9)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.2), RATE, 0.55)


def robot_beep():
    """The runaway robot: two quick, cheerful beeps (placed by the mixer on its side)."""
    samples = _zeros(0.36)
    for start, note in ((0.0, 1760.0), (0.16, 2093.0)):
        tone = [math.sin(TAU * note * i / RATE) * math.exp(-18 * i / RATE) for i in range(int(0.12 * RATE))]
        _put(samples, start, tone)
    return mono_bytes(samples, RATE, 0.4)


def hunt_clue():
    """A clue of the hunt: a music box's question, four notes that don't resolve."""
    left, right = _blank(1.6)
    for i, (note, position) in enumerate(((E5, -0.5), (G5, -0.15), (E5 * 2, 0.15), (G5 * 1.5, 0.5))):
        _add(left, right, i * 0.16, _bell(note, 0.9, 4.5, partials=((1, 1.0), (3.0, 0.18), (5.4, 0.05))),
             position, 0.5)
    _echo(left, right, RATE, ((0.18, 0.3, 1), (0.34, 0.2, -1)))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.2), RATE, 0.4)


def hunt_found():
    """A note of the Lost Chord found: C, E, G and B blooming from left to right."""
    left, right = _blank(2.4)
    for i, (note, position) in enumerate(((C5, -0.6), (E5, -0.2), (G5, 0.2), (987.77, 0.6))):
        _add(left, right, i * 0.12, _soft_square(note, 1.2, 2.2), position, 0.32)
        _add(left, right, i * 0.12 + 0.01, _bell(note * 2, 1.6, 2.0), position, 0.28)
    _add(left, right, 0.5, _bell(C6 * 2, 1.4, 2.4), 0.0, 0.18)
    _echo(left, right, RATE, ((0.11, 0.3, 1), (0.21, 0.22, -1), (0.33, 0.14, 1)))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.3), RATE, 0.42)


def hunt_rival():
    """The rival is ahead: three low notes stepping down, and a dull thud."""
    left, right = _blank(1.5)
    for i, note in enumerate((G5 / 2, 369.99, E5 / 2 * 0.944)):
        _add(left, right, i * 0.2, _soft_square(note, 0.5, 5.0), 0.4 - 0.4 * i, 0.5)
    _add(left, right, 0.62, _thump(55, 0.5, 7.0), 0.0, 0.9)
    _echo(left, right, RATE, ((0.2, 0.25, -1),))
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.2), RATE, 0.4)


# Pixel Pier's cabinets: short and mono (Orbit places them), chip-tune squares.

def _chip(notes, gap, length, decay, gain=1.0):
    out = _zeros(gap * (len(notes) - 1) + length)
    for i, note in enumerate(notes):
        _put(out, i * gap, _soft_square(note, length, decay), gain)
    return out


def arcade_start():
    """A coin drops in and the cabinet wakes: a clink, then a quick rising arpeggio."""
    rng = random.Random(SEED + 900)
    out = _zeros(0.7)
    _put(out, 0.0, _burst(rng, 0.08, 4200, 3.0, 0.0005, 45), 0.6)
    _put(out, 0.16, _chip((C5, E5, G5, C6), 0.07, 0.16, 16.0), 0.7)
    return mono_bytes(out, RATE, 0.45)


def arcade_ready():
    """Ready: two low blips."""
    return mono_bytes(_chip((G5 / 2, G5 / 2), 0.1, 0.08, 30.0), RATE, 0.35)


def arcade_go():
    """Go: one bright, sharp beep."""
    return mono_bytes(_soft_square(C6 * 1.5, 0.15, 12.0), RATE, 0.45)


def arcade_hit():
    """A point scored: a quick two-note ping up."""
    return mono_bytes(_chip((E5 * 2, G5 * 2), 0.06, 0.18, 22.0), RATE, 0.35)


def arcade_beat():
    """One beat of Star Beat: a short, round knock."""
    out = _thump(180, 0.1, 30.0, drop=0.5)
    _put(out, 0.0, _soft_square(880.0, 0.03, 90.0), 0.25)
    return mono_bytes(out, RATE, 0.45)


def arcade_meteor():
    """A meteor rushing in: rising noise and a falling whistle (placed on its side)."""
    rng = random.Random(SEED + 910)
    n = int(0.8 * RATE)
    rush = _band(_noise(n, rng), lambda t: 500 + 2500 * t / 0.8, 1.5)
    env = [min(1.0, (i / n) * 1.6) ** 2 * (1.0 if i < n * 0.9 else (n - i) / (n * 0.1)) for i in range(n)]
    out = [v * e for v, e in zip(rush, env)]
    _put(out, 0.0, [v * 0.3 for v in _chirp(1800, 700, 0.8, shape="arch")], 1.0)
    return mono_bytes(out, RATE, 0.45, fade_out=0.03)


def arcade_whoosh():
    """Dodged: the meteor whooshes past."""
    rng = random.Random(SEED + 920)
    n = int(0.35 * RATE)
    out = _band(_noise(n, rng), lambda t: 3000 - 2400 * t / 0.35, 1.2)
    out = [v * math.sin(math.pi * i / n) for i, v in enumerate(out)]
    return mono_bytes(out, RATE, 0.35)


def arcade_crash():
    """Hit: a crunchy boom."""
    rng = random.Random(SEED + 930)
    out = _zeros(0.5)
    _put(out, 0.0, _thump(70, 0.45, 8.0), 1.0)
    _put(out, 0.0, _burst(rng, 0.4, 900, 0.7, 0.001, 10.0), 0.8)
    _put(out, 0.02, _grains(rng, 0.3, 30, 1500, 5000, env=lambda a: math.exp(-5 * a)), 0.5)
    return mono_bytes(out, RATE, 0.45)


def arcade_ticket():
    """Prize tickets feeding out of the cabinet: a quick ratchet, then a ding."""
    rng = random.Random(SEED + 940)
    out = _zeros(0.5)
    for k in range(7):
        _put(out, 0.035 * k, _burst(rng, 0.02, 2600, 2.0, 0.0005, 150), 0.7)
    _put(out, 0.28, _bell(C6 * 2, 0.22, 12.0), 0.5)
    return mono_bytes(out, RATE, 0.55)


def arcade_over():
    """Game over: three notes falling."""
    return mono_bytes(_chip((G5, E5, C5), 0.16, 0.3, 7.0), RATE, 0.38)


# The other worlds' ambience (kept as a name of its own; every loop is at LOOP_RATE now).
SMALL_LOOP_RATE = LOOP_RATE


def _small_blank():
    return _loop_blank(SMALL_LOOP_RATE)


def _small_wav(left, right, peak, equal_power=True):
    return wav_bytes(*_seamless(left, right, rate=SMALL_LOOP_RATE, equal_power=equal_power), SMALL_LOOP_RATE, peak)


def _air_bed(rng, left, right, cutoff, gain, rate=SMALL_LOOP_RATE):
    """Soft, wide moving air (a hall, a dome, the wind)."""
    a = _lowpass_coeff(cutoff, rate)
    low_l = low_r = 0.0
    for i in range(len(left)):
        low_l += a * (rng.uniform(-1, 1) - low_l)
        low_r += a * (rng.uniform(-1, 1) - low_r)
        left[i] += low_l * gain
        right[i] += low_r * gain


def amb_gate():
    """The Gate: a shimmering hum that beats slowly, and now and then a sparkle."""
    rng = random.Random(SEED + 30)
    left, right = _small_blank()
    rate = SMALL_LOOP_RATE
    for i in range(len(left)):
        t = i / rate
        swell = 0.7 + 0.3 * math.sin(TAU * 0.5 * t)
        left[i] = (math.sin(TAU * 110 * t) + 0.6 * math.sin(TAU * 220.5 * t) + 0.3 * math.sin(TAU * 330 * t)) \
            * 0.18 * swell
        right[i] = (math.sin(TAU * 110.5 * t) + 0.6 * math.sin(TAU * 220 * t) + 0.3 * math.sin(TAU * 330.5 * t)) \
            * 0.18 * swell
    for _k in range(6):
        start = rng.uniform(0.1, LOOP_SECONDS - 0.4)
        _add(left, right, start, _bell(rng.uniform(1200, 1800), 0.4, 8.0, rate=rate), rng.uniform(-0.8, 0.8),
             0.05, rate=rate)
    return _small_wav(left, right, 0.36, equal_power=False)


def amb_moon():
    """Moon Base: air handlers under a low dome, a far-off clank now and then."""
    rng = random.Random(SEED + 31)
    left, right = _small_blank()
    rate = SMALL_LOOP_RATE
    _air_bed(rng, left, right, 220, 2.2)
    for i in range(len(left)):
        t = i / rate
        hum = 0.04 * math.sin(TAU * 50 * t) + 0.02 * math.sin(TAU * 100 * t)
        left[i] += hum
        right[i] += hum
    for start, position in ((0.8, -0.6), (2.9, 0.5)):
        _add(left, right, start, _resonator((180, 410), (18, 26), (1.0, 0.4), 0.5, rate=rate), position, 0.12,
             rate=rate)
    return _small_wav(left, right, 0.4)


def amb_colony():
    """Karmina: dust-laden wind against the domes, and the colony's fans."""
    rng = random.Random(SEED + 32)
    left, right = _small_blank()
    rate = SMALL_LOOP_RATE
    wind_l, wind_r = _SVF(2.0), _SVF(2.0)
    for i in range(len(left)):
        t = i / rate
        gust = 0.6 + 0.4 * math.sin(TAU * 0.25 * t + 1.0)
        centre = 500 + 250 * math.sin(TAU * 0.5 * t)
        left[i] = wind_l.band_pass(rng.uniform(-1, 1), centre, rate) * 0.5 * gust
        right[i] = wind_r.band_pass(rng.uniform(-1, 1), centre * 1.1, rate) * 0.5 * (1.2 - gust * 0.5)
    _air_bed(rng, left, right, 160, 1.2)
    # grit ticking on the glass
    for _k in range(40):
        start = rng.uniform(0.0, LOOP_SECONDS)
        _add(left, right, start, [rng.uniform(-1, 1) * math.exp(-j / 20.0) for j in range(60)],
             rng.uniform(-0.9, 0.9), 0.05, rate=rate)
    return _small_wav(left, right, 0.4)


def amb_ice():
    """Glasir: a thin, howling wind, and the ice creaking."""
    rng = random.Random(SEED + 33)
    left, right = _small_blank()
    rate = SMALL_LOOP_RATE
    howl_l, howl_r = _SVF(6.0), _SVF(6.0)
    for i in range(len(left)):
        t = i / rate
        centre = 700 + 300 * math.sin(TAU * 0.25 * t)
        left[i] = howl_l.band_pass(rng.uniform(-1, 1), centre, rate) * 0.35
        right[i] = howl_r.band_pass(rng.uniform(-1, 1), centre * 1.15, rate) * 0.35
    _air_bed(rng, left, right, 300, 0.8)
    for start, position in ((1.1, -0.4), (3.2, 0.6)):
        creak = [math.sin(TAU * (90 + 40 * j / 2000.0) * j / rate) * math.sin(math.pi * j / 2000.0)
                 for j in range(2000)]
        _add(left, right, start, creak, position, 0.25, rate=rate)
    return _small_wav(left, right, 0.4)


def amb_bazaar():
    """The Drift Bazaar: a crowd haggling in a cave of stalls, bells and a plucked string."""
    rng = random.Random(SEED + 34)
    left, right = _small_blank()
    rate = SMALL_LOOP_RATE
    for voice in range(6):
        position = -0.9 + 1.8 * voice / 5
        centre = rng.uniform(350, 950)
        filt = _SVF(3.0)
        gl, gr = _pan(position)
        syllable, target, next_change = 0.0, 0.0, 0
        for i in range(len(left)):
            if i >= next_change:
                target = rng.uniform(0.3, 1.0) if rng.random() < 0.75 else 0.0
                next_change = i + int(rng.uniform(0.07, 0.2) * rate)
            syllable += 0.006 * (target - syllable)
            v = filt.band_pass(rng.uniform(-1, 1), centre, rate) * syllable * 0.6
            left[i] += v * gl
            right[i] += v * gr
    for start, note, position in ((0.5, 587.33, -0.5), (1.9, 783.99, 0.6), (3.1, 659.25, -0.2)):
        _add(left, right, start, _bell(note, 0.6, 6.0, rate=rate, partials=((1, 1.0), (2.01, 0.3))), position,
             0.06, rate=rate)
    _air_bed(rng, left, right, 120, 1.2)
    return _small_wav(left, right, 0.42)


def amb_forest():
    """Evergrove: leaves in the wind, birdsong, a stream."""
    rng = random.Random(SEED + 35)
    left, right = _small_blank()
    rate = SMALL_LOOP_RATE
    leaves_l, leaves_r = _SVF(0.8), _SVF(0.8)
    for i in range(len(left)):
        t = i / rate
        sway = 0.5 + 0.5 * math.sin(TAU * 0.25 * t)
        left[i] = leaves_l.band_pass(rng.uniform(-1, 1), 1600, rate) * 0.12 * sway
        right[i] = leaves_r.band_pass(rng.uniform(-1, 1), 1700, rate) * 0.12 * (1 - sway * 0.5)
    # birds: little falling-and-rising whistles
    for _k in range(7):
        start = rng.uniform(0.1, LOOP_SECONDS - 0.5)
        f0 = rng.uniform(2000, 2600)
        chirp = []
        phase = 0.0
        length = int(rng.uniform(0.08, 0.16) * rate)
        for j in range(length):
            x = j / length
            phase += TAU * f0 * (1 - 0.3 * math.sin(math.pi * x)) / rate
            chirp.append(math.sin(phase) * math.sin(math.pi * x))
        for repeat in range(rng.randint(1, 3)):
            _add(left, right, start + repeat * 0.18, chirp, rng.uniform(-0.8, 0.8), 0.08, rate=rate)
    # a stream, low and to the left
    water = _SVF(1.5)
    for i in range(len(left)):
        v = water.band_pass(rng.uniform(-1, 1), 900, rate) * 0.08
        left[i] += v
        right[i] += v * 0.4
    return _small_wav(left, right, 0.4)


def amb_neon():
    """Lumina City: rain, the traffic's hum far below, a sign buzzing."""
    rng = random.Random(SEED + 36)
    left, right = _small_blank()
    rate = SMALL_LOOP_RATE
    for i in range(len(left)):
        t = i / rate
        buzz = 0.02 * (math.sin(TAU * 120 * t) + 0.5 * math.sin(TAU * 240 * t))
        left[i] = rng.uniform(-1, 1) * 0.05 + buzz
        right[i] = rng.uniform(-1, 1) * 0.05 + buzz * 0.6
    _air_bed(rng, left, right, 150, 2.0)
    for _k in range(120):                                         # raindrops
        start = rng.uniform(0.0, LOOP_SECONDS)
        _add(left, right, start, [rng.uniform(-1, 1) * math.exp(-j / 8.0) for j in range(30)],
             rng.uniform(-1, 1), 0.08, rate=rate)
    for start, position in ((0.6, -0.9), (2.4, 0.9)):             # a hovercab going by
        swoosh = [rng.uniform(-1, 1) * math.sin(math.pi * j / 6000.0) for j in range(6000)]
        filt = _SVF(1.0)
        swoosh = [filt.band_pass(v, 400, rate) for v in swoosh]
        _add(left, right, start, swoosh, position, 0.35, rate=rate)
    return _small_wav(left, right, 0.42)


def amb_arcade():
    """Pixel Pier: cabinets bleeping little tunes, a crowd, carpet."""
    rng = random.Random(SEED + 37)
    left, right = _small_blank()
    rate = SMALL_LOOP_RATE
    tunes = ((523.25, 659.25, 783.99, 1046.5), (392.0, 493.88, 587.33, 783.99), (440.0, 554.37, 659.25, 880.0))
    for tune_i, notes in enumerate(tunes):
        position = (-0.7, 0.0, 0.7)[tune_i]
        start = 0.3 + tune_i * 1.2
        for k, note in enumerate(notes * 2):
            tone = [(1.0 if math.sin(TAU * note * j / rate) > 0 else -1.0) * math.exp(-j / 800.0)
                    for j in range(int(0.09 * rate))]
            _add(left, right, start + k * 0.1, tone, position, 0.04, rate=rate)
    _air_bed(rng, left, right, 180, 1.4)
    for voice in range(3):
        filt = _SVF(3.0)
        gl, gr = _pan(-0.6 + 0.6 * voice)
        syllable, target, next_change = 0.0, 0.0, 0
        for i in range(len(left)):
            if i >= next_change:
                target = rng.uniform(0.2, 0.7) if rng.random() < 0.6 else 0.0
                next_change = i + int(rng.uniform(0.1, 0.3) * rate)
            syllable += 0.005 * (target - syllable)
            v = filt.band_pass(rng.uniform(-1, 1), 600 + 150 * voice, rate) * syllable * 0.5
            left[i] += v * gl
            right[i] += v * gr
    return _small_wav(left, right, 0.4)


def creature():
    """One of Evergrove's creatures: a trill and a little puff of air."""
    rng = random.Random(SEED + 38)
    samples = _zeros(0.7)
    phase = 0.0
    for i in range(int(0.45 * RATE)):
        t = i / RATE
        f = 1400 + 500 * math.sin(TAU * 11 * t) + 400 * t
        phase += TAU * f / RATE
        samples[i] += math.sin(phase) * math.sin(math.pi * t / 0.45) * 0.6
    puff = _burst(rng, 0.2, 1200, 1.0, 0.01, 0.12)
    _put(samples, 0.45, puff, 0.5)
    return mono_bytes(samples, RATE, 0.28)


# ------------------------------------------------------------
# Recorded cues (Kenney's CC0 packs)
# ------------------------------------------------------------

RECORDED_RATE = 22050
MIN_SECONDS = 0.12


def _pair(pack, name, i, second=0.3, gains=(1.0, 0.85)):
    """Two steps (a move): sources name_00i and the next one."""
    return [(f"{pack}/{name}_{i % 5:03d}.wav", 0.0, gains[0]),
            (f"{pack}/{name}_{(i + 1) % 5:03d}.wav", second, gains[1])]


def _steps(name, parts_for, count=4, peak=-11.0):
    return {f"{name}_{i + 1}.wav": (peak, parts_for(i)) for i in range(count)}


def _metal_steps(i):
    # Boots on deck plating: a hard step with a faint ring of the plate under it.
    return _pair("impact-sounds", "footstep_concrete", i) + [
        (f"impact-sounds/impactMetal_light_{i % 5:03d}.wav", 0.004, 0.16),
        (f"impact-sounds/impactMetal_light_{(i + 2) % 5:03d}.wav", 0.304, 0.13)]


def _dust_steps(i):
    # Fine dust on hard ground: grit over a step.
    return [(f"impact-sounds/footstep_concrete_{i % 5:03d}.wav", 0.0, 0.7),
            (f"impact-sounds/footstep_grass_{i % 5:03d}.wav", 0.0, 0.5),
            (f"impact-sounds/footstep_concrete_{(i + 1) % 5:03d}.wav", 0.3, 0.6),
            (f"impact-sounds/footstep_grass_{(i + 1) % 5:03d}.wav", 0.3, 0.45)]


def _sand_steps(i):
    return [(f"impact-sounds/footstep_snow_{i % 5:03d}.wav", 0.0, 0.7),
            (f"impact-sounds/footstep_grass_{(i + 2) % 5:03d}.wav", 0.0, 0.4),
            (f"impact-sounds/footstep_snow_{(i + 1) % 5:03d}.wav", 0.32, 0.6),
            (f"impact-sounds/footstep_grass_{(i + 3) % 5:03d}.wav", 0.32, 0.35)]


def _approach(files, gains, gap=0.28):
    return [(f, k * gap, g) for k, (f, g) in enumerate(zip(files, gains))]


_CONCRETE = [f"impact-sounds/footstep_concrete_{k:03d}.wav" for k in range(5)]

# file -> (peak in dBFS, [(source, start in seconds, gain[, {"len": s, "fade_in": s, "fade_out": s}])]).
# A source is "pack/file.wav" from the converted packs, or "synth:<maker>" (a sound made above).
RECORDED = {}
RECORDED.update(_steps("step_metal", _metal_steps))
RECORDED.update(_steps("step_stone", lambda i: _pair("impact-sounds", "footstep_concrete", i)))
RECORDED.update(_steps("step_carpet", lambda i: _pair("impact-sounds", "footstep_carpet", i), peak=-13.0))
RECORDED.update(_steps("step_grass", lambda i: _pair("impact-sounds", "footstep_grass", i), peak=-12.0))
RECORDED.update(_steps("step_wood", lambda i: _pair("impact-sounds", "footstep_wood", i)))
RECORDED.update(_steps("step_snow", lambda i: _pair("impact-sounds", "footstep_snow", i), peak=-12.0))
RECORDED.update(_steps("step_dust", _dust_steps, count=3, peak=-12.0))
RECORDED.update(_steps("step_sand", _sand_steps, count=3, peak=-12.0))
RECORDED.update({
    # moving about
    "door_1.wav": (-8.0, [("sci-fi-sounds/doorOpen_000.wav", 0.0, 1.0)]),
    "door_2.wav": (-8.0, [("sci-fi-sounds/doorOpen_001.wav", 0.0, 1.0)]),
    "door_3.wav": (-8.0, [("sci-fi-sounds/doorOpen_002.wav", 0.0, 1.0)]),
    "airlock.wav": (-7.0, [("rpg-audio/metalLatch.wav", 0.0, 0.9), ("synth:airlock", 0.12, 1.0),
                           ("sci-fi-sounds/doorClose_000.wav", 1.45, 0.7)]),
    "locked.wav": (-4.5, [("rpg-audio/metalClick.wav", 0.0, 1.0), ("rpg-audio/metalLatch.wav", 0.2, 0.8),
                           ("interface-sounds/error_004.wav", 0.42, 0.45)]),
    "bump_1.wav": (-10.0, [("impact-sounds/impactSoft_heavy_000.wav", 0.0, 1.0)]),
    "bump_2.wav": (-10.0, [("impact-sounds/impactSoft_heavy_001.wav", 0.0, 1.0)]),
    "bump_3.wav": (-10.0, [("impact-sounds/impactSoft_heavy_003.wav", 0.0, 1.0)]),
    "ladder_1.wav": (-9.5, _approach([f"impact-sounds/impactMetal_light_{k:03d}.wav" for k in (0, 2, 4)],
                                     (1.0, 0.8, 0.65), gap=0.26)),
    "ladder_2.wav": (-9.5, _approach([f"impact-sounds/impactMetal_light_{k:03d}.wav" for k in (1, 3, 0)],
                                     (1.0, 0.8, 0.65), gap=0.26)),
    "arrive.wav": (-11.0, _approach(_CONCRETE[:4], (0.35, 0.5, 0.7, 0.9))),
    "leave.wav": (-11.0, _approach(_CONCRETE[1:], (0.9, 0.7, 0.5, 0.35))),
    # talking and the interface
    "say_1.wav": (-6.0, [("interface-sounds/pluck_001.wav", 0.0, 1.0)]),
    "say_2.wav": (-6.0, [("interface-sounds/pluck_002.wav", 0.0, 1.0)]),
    "sent.wav": (-10.0, [("interface-sounds/select_003.wav", 0.0, 1.0)]),
    "offer.wav": (-10.0, [("interface-sounds/question_001.wav", 0.0, 1.0)]),
    "task.wav": (-10.0, [("interface-sounds/question_002.wav", 0.0, 1.0)]),
    "error.wav": (-7.0, [("interface-sounds/error_006.wav", 0.0, 1.0)]),
    "fail.wav": (-5.0, [("interface-sounds/error_003.wav", 0.0, 1.0)]),
    "success.wav": (-9.0, [("interface-sounds/confirmation_001.wav", 0.0, 1.0)]),
    "mission.wav": (-9.0, [("interface-sounds/confirmation_002.wav", 0.0, 1.0)]),
    "gadget.wav": (-4.5, [("interface-sounds/switch_002.wav", 0.0, 1.0),
                           ("interface-sounds/maximize_003.wav", 0.07, 0.6)]),
    "daily.wav": (-9.0, [("interface-sounds/confirmation_003.wav", 0.0, 1.0),
                         ("rpg-audio/handleCoins2.wav", 0.25, 0.8)]),
    # gestures (cloth, feet)
    "emote_wave_1.wav": (-7.0, [("rpg-audio/cloth1.wav", 0.0, 1.0)]),
    "emote_wave_2.wav": (-7.0, [("rpg-audio/cloth2.wav", 0.0, 1.0)]),
    "emote_hug.wav": (-7.0, [("rpg-audio/cloth3.wav", 0.0, 1.0), ("rpg-audio/cloth4.wav", 0.22, 0.8)]),
    "emote_bow.wav": (-8.0, [("rpg-audio/clothBelt2.wav", 0.0, 1.0)]),
    "emote_shrug.wav": (-8.0, [("rpg-audio/cloth4.wav", 0.0, 1.0)]),
    "emote_dance_1.wav": (-12.0, _approach([f"impact-sounds/footstep_wood_{k:03d}.wav" for k in (0, 2, 1, 3, 4)],
                                           (1.0, 0.7, 0.9, 0.7, 1.0), gap=0.2)),
    "emote_dance_2.wav": (-12.0, _approach([f"impact-sounds/footstep_wood_{k:03d}.wav" for k in (3, 1, 4, 0)],
                                           (0.9, 1.0, 0.7, 1.0), gap=0.24)),
    # things, work and money
    "equip_1.wav": (-4.5, [("rpg-audio/beltHandle1.wav", 0.0, 1.0)]),
    "equip_2.wav": (-4.5, [("rpg-audio/beltHandle2.wav", 0.0, 1.0)]),
    "equip_3.wav": (-4.5, [("rpg-audio/clothBelt.wav", 0.0, 1.0)]),
    "coins_1.wav": (-4.5, [("rpg-audio/handleCoins.wav", 0.0, 1.0)]),
    "coins_2.wav": (-4.5, [("rpg-audio/handleCoins2.wav", 0.0, 1.0)]),
    "trade.wav": (-7.0, [("rpg-audio/cloth2.wav", 0.0, 0.5), ("rpg-audio/handleCoins2.wav", 0.12, 1.0),
                         ("interface-sounds/confirmation_001.wav", 0.3, 0.55)]),
    "mine_1.wav": (-8.0, [("impact-sounds/impactMining_000.wav", 0.0, 1.0)]),
    "mine_2.wav": (-8.0, [("impact-sounds/impactMining_001.wav", 0.0, 1.0)]),
    "mine_3.wav": (-8.0, [("impact-sounds/impactMining_002.wav", 0.0, 1.0)]),
    "mine_4.wav": (-8.0, [("impact-sounds/impactMining_003.wav", 0.0, 1.0)]),
    "harvest_1.wav": (-11.0, [("rpg-audio/knifeSlice.wav", 0.0, 1.0)]),
    "harvest_2.wav": (-11.0, [("rpg-audio/knifeSlice2.wav", 0.0, 1.0)]),
    "harvest_3.wav": (-11.0, [("rpg-audio/chop.wav", 0.0, 1.0)]),
    "plant.wav": (-16.0, [("impact-sounds/impactSoft_medium_001.wav", 0.0, 1.0),
                          ("impact-sounds/impactSoft_medium_003.wav", 0.22, 0.75)]),
    "rescue.wav": (-8.0, [("sci-fi-sounds/thrusterFire_000.wav", 0.0, 0.8, {"len": 1.4, "fade_in": 0.3,
                                                                          "fade_out": 0.5}),
                          ("sci-fi-sounds/impactMetal_002.wav", 1.3, 1.0),
                          ("sci-fi-sounds/doorOpen_000.wav", 1.6, 0.8)]),
    "launch.wav": (-6.0, [("sci-fi-sounds/doorClose_001.wav", 0.0, 0.8),
                          ("sci-fi-sounds/thrusterFire_001.wav", 0.3, 1.0, {"len": 2.4, "fade_in": 0.6,
                                                                            "fade_out": 1.0}),
                          ("sci-fi-sounds/spaceEngineSmall_000.wav", 0.3, 0.6, {"len": 2.4, "fade_in": 0.8,
                                                                                "fade_out": 1.0})]),
    "landing.wav": (-6.0, [("sci-fi-sounds/spaceEngineSmall_001.wav", 0.0, 0.7, {"len": 1.4, "fade_in": 0.2,
                                                                                 "fade_out": 0.8}),
                           ("sci-fi-sounds/impactMetal_000.wav", 1.2, 1.0),
                           ("rpg-audio/metalLatch.wav", 1.5, 0.8),
                           ("sci-fi-sounds/doorOpen_002.wav", 1.8, 0.9)]),
    # the casino
    "dice_1.wav": (-4.5, [("casino-audio/dice-shake-1.wav", 0.0, 0.8, {"len": 0.8, "fade_out": 0.1}),
                          ("casino-audio/dice-throw-1.wav", 0.75, 1.0)]),
    "dice_2.wav": (-4.5, [("casino-audio/dice-shake-2.wav", 0.0, 0.8, {"len": 0.8, "fade_out": 0.1}),
                          ("casino-audio/dice-throw-2.wav", 0.75, 1.0)]),
    "dice_3.wav": (-4.5, [("casino-audio/dice-shake-3.wav", 0.0, 0.8, {"len": 0.8, "fade_out": 0.1}),
                          ("casino-audio/dice-throw-3.wav", 0.75, 1.0)]),
    "reel_spin_1.wav": (-5.0, [("interface-sounds/scroll_001.wav", 0.0, 1.0),
                                ("interface-sounds/scroll_002.wav", 0.9, 0.8, {"fade_out": 0.3})]),
    "reel_spin_2.wav": (-5.0, [("interface-sounds/scroll_003.wav", 0.0, 1.0),
                                ("interface-sounds/scroll_004.wav", 0.9, 0.8, {"fade_out": 0.3})]),
    "reel_stop_1.wav": (-9.0, [("impact-sounds/impactMetal_medium_001.wav", 0.0, 1.0)]),
    "reel_stop_2.wav": (-9.0, [("impact-sounds/impactMetal_medium_002.wav", 0.0, 1.0)]),
    "reel_stop_3.wav": (-9.0, [("impact-sounds/impactMetal_medium_004.wav", 0.0, 1.0)]),
    "cards_1.wav": (-5.0, [("casino-audio/card-place-1.wav", 0.0, 1.0)]),
    "cards_2.wav": (-5.0, [("casino-audio/card-place-2.wav", 0.0, 1.0)]),
    "cards_3.wav": (-5.0, [("casino-audio/card-place-3.wav", 0.0, 1.0)]),
    "cards_4.wav": (-5.0, [("casino-audio/card-place-4.wav", 0.0, 1.0)]),
    "deal_1.wav": (-5.0, _approach([f"casino-audio/card-slide-{k}.wav" for k in (1, 5, 6, 7)],
                                    (1.0, 0.9, 1.0, 0.9), gap=0.24)),
    "deal_2.wav": (-5.0, _approach([f"casino-audio/card-slide-{k}.wav" for k in (2, 3, 4, 8)],
                                    (1.0, 0.9, 1.0, 0.9), gap=0.24)),
    "win_1.wav": (-5.0, [("casino-audio/chips-handle-1.wav", 0.0, 1.0),
                         ("interface-sounds/confirmation_001.wav", 0.05, 0.5)]),
    "win_2.wav": (-5.0, [("casino-audio/chips-handle-5.wav", 0.0, 1.0),
                         ("interface-sounds/confirmation_003.wav", 0.05, 0.5)]),
    "push.wav": (-4.5, [("casino-audio/chip-lay-2.wav", 0.0, 1.0), ("casino-audio/chip-lay-3.wav", 0.12, 0.8)]),
    "lose.wav": (-12.0, [("interface-sounds/minimize_006.wav", 0.0, 1.0)]),
    "jackpot.wav": (-4.5, [("synth:achievement", 0.0, 0.8)] + [
        (f"casino-audio/chips-stack-{k}.wav", 0.35 + 0.11 * j, 0.9)
        for j, k in enumerate((1, 3, 2, 5, 4, 6, 1, 3))] + [
        ("casino-audio/chips-handle-5.wav", 1.2, 1.0)]),
    "coinflip.wav": (-6.0, [("impact-sounds/impactTin_medium_000.wav", 0.0, 1.0),
                            ("impact-sounds/impactMetal_light_002.wav", 0.75, 0.7),
                            ("impact-sounds/impactTin_medium_003.wav", 0.83, 0.45)]),
    "lottery.wav": (-4.5, [("rpg-audio/bookFlip3.wav", 0.0, 1.0), ("rpg-audio/handleCoins2.wav", 0.18, 0.6)]),
    # travel between worlds
    "gate.wav": (-6.0, [("sci-fi-sounds/forceField_000.wav", 0.0, 1.0), ("sci-fi-sounds/forceField_002.wav", 0.35, 0.7),
                        ("interface-sounds/maximize_006.wav", 0.1, 0.5)]),
    "ferry.wav": (-7.0, [("interface-sounds/bong_001.wav", 0.0, 1.0), ("interface-sounds/bong_001.wav", 0.3, 0.7),
                         ("sci-fi-sounds/doorClose_002.wav", 0.6, 0.8)]),
    "refuel.wav": (-4.5, [("rpg-audio/metalClick.wav", 0.0, 0.8), ("sci-fi-sounds/slime_000.wav", 0.15, 1.0),
                          ("rpg-audio/metalLatch.wav", 0.75, 0.7)]),
    "customs.wav": (-8.0, [("interface-sounds/select_004.wav", 0.0, 1.0),
                           ("interface-sounds/select_005.wav", 0.12, 1.0),
                           ("interface-sounds/question_003.wav", 0.3, 0.8)]),
    "cargo.wav": (-6.0, [("impact-sounds/impactWood_heavy_000.wav", 0.0, 1.0),
                         ("impact-sounds/impactPlank_medium_001.wav", 0.25, 0.8)]),
    "lottery_draw.wav": (-6.0, [("interface-sounds/bong_001.wav", 0.0, 1.0),
                                ("interface-sounds/bong_001.wav", 0.28, 0.8),
                                ("casino-audio/chips-handle-5.wav", 0.55, 0.8)]),
})


def _read_mono(path):
    """A 16-bit WAV as floats (-1..1) at RECORDED_RATE, stereo mixed down."""
    with wave.open(path, "rb") as w:
        channels, rate, width = w.getnchannels(), w.getframerate(), w.getsampwidth()
        data = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"{path}: 16-bit WAV files only")
    ints = array.array("h")
    ints.frombytes(data)
    if sys.byteorder == "big":
        ints.byteswap()
    if channels == 2:
        values = [(ints[i] + ints[i + 1]) / 65536.0 for i in range(0, len(ints) - 1, 2)]
    else:
        values = [v / 32768.0 for v in ints]
    if rate != RECORDED_RATE:
        ratio = rate / RECORDED_RATE
        values = [values[min(len(values) - 1, int(i * ratio))] for i in range(int(len(values) / ratio))]
    return values


def _source(name, library):
    if name.startswith("synth:"):
        return _read_mono(io.BytesIO(globals()[name[6:]]()))
    return _read_mono(os.path.join(library, *name.split("/")))


def recorded_bytes(name, library):
    """The mono WAV for RECORDED[name], mixed from the converted packs in `library`."""
    peak_db, parts = RECORDED[name]
    pieces = []
    for part in parts:
        source, start, gain = part[:3]
        options = part[3] if len(part) > 3 else {}
        values = _source(source, library)
        if options.get("len"):
            values = values[:int(options["len"] * RECORDED_RATE)]
        _fade_list(values, RECORDED_RATE, options.get("fade_in", 0.0), options.get("fade_out", 0.0))
        pieces.append((int(start * RECORDED_RATE), values, gain))
    shortest = int(MIN_SECONDS * RECORDED_RATE)          # a click gets a moment of quiet after it
    out = [0.0] * max([shortest] + [first + len(values) for first, values, _gain in pieces])
    for first, values, gain in pieces:
        for i, v in enumerate(values):
            out[first + i] += v * gain
    return mono_bytes(out, RECORDED_RATE, 10 ** (peak_db / 20.0), fade_in=0.002, fade_out=0.01)


def recorded_sources():
    """Every pack file the recorded cues use ("pack/file.wav")."""
    return sorted({part[0] for _peak, parts in RECORDED.values() for part in parts
                   if not part[0].startswith("synth:")})


# ------------------------------------------------------------
# The cues
# ------------------------------------------------------------

def _variants(name, make, count):
    return [(f"{name}_{i}.wav", (lambda i=i: make(i))) for i in range(1, count + 1)]


# (file, maker): the synthesized files. A cue with variants has files name_1.wav, name_2.wav...
SOUNDS = (
    [("lift_up.wav", lift_up), ("lift_down.wav", lift_down), ("slide.wav", slide)]
    + _variants("step_rock", step_rock, 3) + _variants("step_suit", step_suit, 3)
    + _variants("step_wet", step_wet, 3)
    + _variants("shout", shout, 2)
    + [("whisper.wav", whisper), ("announce.wav", announce),
       ("emote.wav", emote), ("emote_smile.wav", emote_smile), ("emote_nod.wav", emote_nod),
       ("emote_cheer.wav", emote_cheer), ("emote_sigh.wav", emote_sigh)]
    + _variants("emote_laugh", emote_laugh, 2) + _variants("emote_clap", emote_clap, 2)
    + [("register.wav", register), ("rare.wav", rare), ("water.wav", water), ("ripe.wav", ripe),
       ("levelup.wav", levelup), ("achievement.wav", achievement)]
    + _variants("crunch", crunch, 2)
    + [("scan.wav", scan), ("air.wav", air), ("gulp.wav", gulp), ("pet_robot.wav", pet_robot),
       ("pet_cat.wav", pet_cat), ("bell.wav", bell), ("lantern.wav", lantern),
       ("tone1.wav", lambda: tone(1)), ("tone2.wav", lambda: tone(2)),
       ("tone3.wav", lambda: tone(3)), ("tone4.wav", lambda: tone(4)),
       ("amb_vent.wav", amb_vent), ("amb_cantina.wav", amb_cantina),
       ("amb_engine.wav", amb_engine), ("amb_garden.wav", amb_garden), ("amb_deck.wav", amb_deck),
       ("amb_space.wav", amb_space), ("amb_belt.wav", amb_belt), ("amb_venue.wav", amb_venue),
       ("amb_mall.wav", amb_mall), ("amb_casino.wav", amb_casino),
       ("amb_gate.wav", amb_gate), ("amb_moon.wav", amb_moon), ("amb_colony.wav", amb_colony),
       ("amb_ice.wav", amb_ice), ("amb_bazaar.wav", amb_bazaar), ("amb_forest.wav", amb_forest),
       ("amb_neon.wav", amb_neon), ("amb_arcade.wav", amb_arcade), ("creature.wav", creature),
       ("event_start.wav", event_start), ("event_end.wav", event_end), ("event_party.wav", event_party),
       ("event_storm.wav", event_storm), ("event_boss.wav", event_boss), ("event_meteor.wav", event_meteor),
       ("fireworks.wav", fireworks), ("robot_beep.wav", robot_beep),
       ("hunt_clue.wav", hunt_clue), ("hunt_found.wav", hunt_found), ("hunt_rival.wav", hunt_rival),
       ("arcade_start.wav", arcade_start), ("arcade_ready.wav", arcade_ready), ("arcade_go.wav", arcade_go),
       ("arcade_hit.wav", arcade_hit), ("arcade_beat.wav", arcade_beat), ("arcade_meteor.wav", arcade_meteor),
       ("arcade_whoosh.wav", arcade_whoosh), ("arcade_crash.wav", arcade_crash),
       ("arcade_ticket.wav", arcade_ticket), ("arcade_over.wav", arcade_over)]
)


def _cue_of(name):
    stem = name[:-4]
    return stem.rstrip("0123456789").rstrip("_") if stem.split("_")[-1].isdigit() else stem


# The cue each file belongs to ("step_metal_2.wav" -> "step_metal").
CUES = sorted({_cue_of(name) for name, _make in SOUNDS} | {_cue_of(name) for name in RECORDED})
FILES = sorted({name for name, _make in SOUNDS} | set(RECORDED))


def write_all(folder=SOUNDS_DIR, library=None):
    """Writes the synthesized files (and, given the converted packs in `library`,
    the recorded ones), and removes files that are no cue any more."""
    os.makedirs(folder, exist_ok=True)
    keep = set(FILES)
    for entry in os.listdir(folder):
        if entry.endswith(".wav") and entry not in keep:
            os.remove(os.path.join(folder, entry))
    made = [(name, make) for name, make in SOUNDS]
    if library:
        missing = [src for src in recorded_sources() if not os.path.isfile(os.path.join(library, *src.split("/")))]
        if missing:
            raise SystemExit(f"Not in {library}: {', '.join(missing)}")
        made += [(name, (lambda name=name: recorded_bytes(name, library))) for name in sorted(RECORDED)]
    total = 0
    for name, make in made:
        data = make()
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)
        total += len(data)
        with wave.open(io.BytesIO(data)) as w:
            print(f"{name}: {w.getnframes() / w.getframerate():.2f} s, {w.getnchannels()} ch, {len(data)} bytes")
    print(f"{len(made)} files, {total / 1024 / 1024:.2f} MB")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    library = None
    if args[:1] == ["--kenney"] and len(args) == 2:
        library = args[1]
    elif args:
        raise SystemExit("usage: orbit_sounds.py [--kenney <folder of the converted packs>]")
    write_all(library=library)


if __name__ == "__main__":
    main()
