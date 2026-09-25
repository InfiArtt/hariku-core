# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Makes Orbit's sounds in sounds/, from nothing but arithmetic:

  door        a pneumatic door: a whoosh sweeping from left to right, then a soft thunk
  arrive      someone comes in: two soft bell notes, rising
  leave       someone goes: the same notes, falling
  whisper     a breathy "psst" and a tiny bell, close to your right ear
  chat        a soft bubble when someone speaks
  sent        a small swish: your own words went out
  announce    the station's public-address chime, three notes, in a big room
  coins       credits: a few small metallic tings
  success     a quick rising arpeggio
  fail        two low, sagging buzzes
  error       a short low double blip
  mission     a data pad's blip-blip
  launch      the Merpati undocking: clamps let go, the engines swell
  landing     the engines settle, thrusters puff, the clamps catch
  tone1-4     the reactor's four stabiliser tones, low on the left to high on the right
  amb_vent    corridors: air in the vents and a faint mains hum
  amb_cantina the Cantina: people murmuring around you, a glass clinking now and then
  amb_engine  Engineering: the reactor's slow, beating thrum
  amb_garden  Hydroponics: water trickling and bubbling, fans
  amb_deck    the Observation Deck: a hush and a slow, shimmering chord

    python extensions/orbit/orbit_sounds.py

The files are committed; run this again only to change them. Everything is
computed from sine waves and seeded noise (the same bytes every time), not
recorded or sampled from anything, so there is no copyright question; the
sounds are part of Hariku under its licence. 16-bit stereo, peaks well below
full scale, short fades so nothing clicks. The ambience files loop without a
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


def wav_bytes(left, right, rate, peak):
    """Interleave, scale the loudest sample to `peak`, and make a WAV."""
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


def _fade(left, right, rate, fade_in=0.005, fade_out=0.02):
    n = len(left)
    rise = max(1, int(fade_in * rate))
    fall = max(1, int(fade_out * rate))
    for i in range(min(rise, n)):
        k = i / rise
        left[i] *= k
        right[i] *= k
    for i in range(min(fall, n)):
        k = i / fall
        left[n - 1 - i] *= k
        right[n - 1 - i] *= k
    return left, right


def _pan(position):
    """(left gain, right gain) for -1 (left) to 1 (right), equal power."""
    angle = (position + 1) * math.pi / 4
    return math.cos(angle), math.sin(angle)


def _blank(seconds, rate=RATE):
    n = int(seconds * rate)
    return [0.0] * n, [0.0] * n


def _add(left, right, start, samples, position=0.0, gain=1.0, rate=RATE):
    gl, gr = _pan(position)
    first = int(start * rate)
    for i, v in enumerate(samples):
        j = first + i
        if 0 <= j < len(left):
            left[j] += v * gl * gain
            right[j] += v * gr * gain


def _bell(frequency, seconds, decay, rate=RATE, partials=((1, 1.0), (2, 0.25), (3, 0.08))):
    count = int(seconds * rate)
    rise = max(1, int(0.004 * rate))
    out = []
    for n in range(count):
        t = n / rate
        env = min(1.0, n / rise) * math.exp(-decay * t)
        out.append(env * sum(g * math.sin(TAU * frequency * k * t) for k, g in partials))
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


def _lowpass_coeff(cutoff, rate):
    return 1.0 - math.exp(-TAU * cutoff / rate)


# ------------------------------------------------------------
# Short effects
# ------------------------------------------------------------

def door():
    rng = random.Random(SEED + 1)
    seconds = 0.8
    left, right = _blank(seconds)
    filt_l, filt_r = _SVF(1.5), _SVF(1.5)
    n = len(left)
    for i in range(n):
        t = i / RATE
        progress = t / 0.62
        if progress <= 1.0:
            centre = 500 + 2200 * math.sin(math.pi * progress) ** 1.5
            env = math.sin(math.pi * progress) ** 0.8
            noise = rng.uniform(-1, 1)
            gl, gr = _pan(-0.9 + 1.8 * progress)
            left[i] += filt_l.band_pass(noise, centre, RATE) * env * gl
            right[i] += filt_r.band_pass(noise, centre, RATE) * env * gr
    thunk = []
    for i in range(int(0.16 * RATE)):
        t = i / RATE
        thunk.append(0.5 * math.exp(-t / 0.035) * math.sin(TAU * 85 * t))
    _add(left, right, 0.6, thunk, 0.6)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.5)


def _two_notes(first, second):
    left, right = _blank(0.75)
    _add(left, right, 0.0, _bell(first, 0.45, 7.0), -0.15, 0.8)
    _add(left, right, 0.16, _bell(second, 0.55, 6.0), 0.15, 0.8)
    _echo(left, right, RATE, ((0.031, 0.25, 1), (0.047, 0.22, -1), (0.083, 0.10, 1)))
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.35)


def arrive():
    return _two_notes(G5, C6)


def leave():
    return _two_notes(C6, G5)


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


def chat():
    left, right = _blank(0.16)
    samples = []
    phase = 0.0
    for i in range(len(left)):
        t = i / RATE
        frequency = 950 - 450 * min(1.0, t / 0.08)
        phase += TAU * frequency / RATE
        samples.append(math.sin(phase) * min(1.0, t / 0.004) * math.exp(-t / 0.04))
    _add(left, right, 0.0, samples, 0.0)
    return wav_bytes(*_fade(left, right, RATE, fade_out=0.01), RATE, 0.25)


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


def coins():
    left, right = _blank(0.55)
    for k, (start, frequency, position) in enumerate(((0.0, 2400, -0.3), (0.09, 2950, 0.3),
                                                      (0.17, 2650, -0.1), (0.24, 3300, 0.2))):
        partials = ((1, 1.0), (2.76, 0.45), (5.40, 0.2))
        _add(left, right, start, _bell(frequency, 0.3, 18.0 + 3 * k, partials=partials),
             position, 0.7)
    return wav_bytes(*_fade(left, right, RATE), RATE, 0.4)


def _soft_square(frequency, seconds, decay):
    count = int(seconds * RATE)
    out = []
    for n in range(count):
        t = n / RATE
        env = min(1.0, t / 0.005) * math.exp(-decay * t)
        x = TAU * frequency * t
        out.append(env * (math.sin(x) + math.sin(3 * x) / 3 + math.sin(5 * x) / 5))
    return out


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


SOUNDS = (
    ("door.wav", door), ("arrive.wav", arrive), ("leave.wav", leave), ("whisper.wav", whisper),
    ("chat.wav", chat), ("sent.wav", sent), ("announce.wav", announce), ("coins.wav", coins),
    ("success.wav", success), ("fail.wav", fail), ("error.wav", error),
    ("mission.wav", mission), ("launch.wav", launch), ("landing.wav", landing),
    ("tone1.wav", lambda: tone(1)), ("tone2.wav", lambda: tone(2)),
    ("tone3.wav", lambda: tone(3)), ("tone4.wav", lambda: tone(4)),
    ("amb_vent.wav", amb_vent), ("amb_cantina.wav", amb_cantina),
    ("amb_engine.wav", amb_engine), ("amb_garden.wav", amb_garden), ("amb_deck.wav", amb_deck),
)


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
