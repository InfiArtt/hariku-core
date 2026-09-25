# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Makes Orbit's sounds in sounds/, from nothing but arithmetic: layered and
filtered noise, damped resonators for metal, wood and glass, envelopes
shaped like real ones, a small room reverb, and a few variants of the
sounds you hear often (footsteps, claps, coins), each a little different.

Every file is a cue orbit_mix looks up by name ("step_metal_2.wav" is a
variant of "step_metal"). Cues heard from a direction (steps, someone
arriving, a gesture) are mono: Orbit pans them to the side they come from
and adds the room's echo when it plays them. The rest are stereo designs.
The cue names, what they are, and how to replace them with recordings are in
README.md (servers/orbit), and CUES below.

    python extensions/orbit/orbit_sounds.py

The files are committed; run this again only to change them. Everything is
computed from sine waves and seeded noise (the same bytes every time), not
recorded or sampled from anything, so there is no copyright question; the
sounds are part of Hariku under its licence. 16-bit, peaks well below full
scale, short fades so nothing clicks. The ambience files loop without a
seam: each is made a little longer than it plays and its end is crossfaded
into its start, and its steady tones fit a whole number of cycles into the
loop. Standard library only.
"""

import io
import math
import os
import random
import struct
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(HERE, "sounds")
RATE = 22050                 # effects
LOOP_RATE = 16000            # ambience: low sounds, smaller files
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


# ------------------------------------------------------------
# The cues
# ------------------------------------------------------------

def _variants(name, make, count):
    return [(f"{name}_{i}.wav", (lambda i=i: make(i))) for i in range(1, count + 1)]


# (file, maker). A cue with variants has files name_1.wav, name_2.wav...
SOUNDS = (
    [("door_1.wav", lambda: door(1)), ("door_2.wav", lambda: door(2)),
     ("airlock.wav", airlock), ("lift_up.wav", lift_up), ("lift_down.wav", lift_down),
     ("slide.wav", slide), ("locked.wav", locked), ("arrive.wav", arrive), ("leave.wav", leave)]
    + _variants("ladder", ladder, 2) + _variants("bump", bump, 2)
    + _variants("step_metal", step_metal, 3) + _variants("step_carpet", step_carpet, 3)
    + _variants("step_grass", step_grass, 3) + _variants("step_stone", step_stone, 3)
    + _variants("step_rock", step_rock, 3) + _variants("step_suit", step_suit, 3)
    + _variants("step_wet", step_wet, 3)
    + _variants("say", say, 2) + _variants("shout", shout, 2)
    + [("whisper.wav", whisper), ("sent.wav", sent), ("announce.wav", announce), ("offer.wav", offer),
       ("emote.wav", emote), ("emote_smile.wav", emote_smile), ("emote_nod.wav", emote_nod),
       ("emote_shrug.wav", emote_shrug), ("emote_cheer.wav", emote_cheer), ("emote_sigh.wav", emote_sigh),
       ("emote_bow.wav", emote_bow), ("emote_hug.wav", emote_hug)]
    + _variants("emote_wave", emote_wave, 2) + _variants("emote_laugh", emote_laugh, 2)
    + _variants("emote_clap", emote_clap, 2) + _variants("emote_dance", emote_dance, 2)
    + _variants("coins", coins, 2)
    + [("register.wav", register), ("success.wav", success), ("fail.wav", fail), ("error.wav", error),
       ("mission.wav", mission), ("task.wav", task), ("rare.wav", rare), ("plant.wav", plant),
       ("water.wav", water), ("ripe.wav", ripe), ("levelup.wav", levelup), ("daily.wav", daily)]
    + _variants("mine", mine, 3) + _variants("harvest", harvest, 2)
    + _variants("equip", equip, 2) + _variants("crunch", crunch, 2)
    + [("gadget.wav", gadget), ("scan.wav", scan), ("air.wav", air), ("rescue.wav", rescue),
       ("gulp.wav", gulp), ("pet_robot.wav", pet_robot), ("pet_cat.wav", pet_cat),
       ("bell.wav", bell), ("lantern.wav", lantern),
       ("launch.wav", launch), ("landing.wav", landing),
       ("tone1.wav", lambda: tone(1)), ("tone2.wav", lambda: tone(2)),
       ("tone3.wav", lambda: tone(3)), ("tone4.wav", lambda: tone(4)),
       ("amb_vent.wav", amb_vent), ("amb_cantina.wav", amb_cantina),
       ("amb_engine.wav", amb_engine), ("amb_garden.wav", amb_garden), ("amb_deck.wav", amb_deck),
       ("amb_space.wav", amb_space), ("amb_belt.wav", amb_belt), ("amb_venue.wav", amb_venue)]
)

# The cue each file belongs to ("step_metal_2.wav" -> "step_metal").
CUES = sorted({name[:-4].rstrip("0123456789").rstrip("_") if name[:-4].split("_")[-1].isdigit()
               else name[:-4] for name, _make in SOUNDS})


def write_all(folder=SOUNDS_DIR):
    os.makedirs(folder, exist_ok=True)
    keep = {name for name, _make in SOUNDS}
    for entry in os.listdir(folder):
        if entry.endswith(".wav") and entry not in keep:
            os.remove(os.path.join(folder, entry))
    total = 0
    for name, make in SOUNDS:
        data = make()
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)
        total += len(data)
        with wave.open(io.BytesIO(data)) as w:
            print(f"{name}: {w.getnframes() / w.getframerate():.2f} s, {w.getnchannels()} ch, {len(data)} bytes")
    print(f"{len(SOUNDS)} files, {total / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    write_all()
