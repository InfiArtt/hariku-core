#!/usr/bin/env python3
# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Kenney's CC0 sound packs (OGG) -> short mono 22.05 kHz 16-bit WAVs, trimmed and
level-matched, for Orbit's recorded sound cues.

A dev-only, one-off tool. It needs `pip install soundfile` (and numpy), which
are NOT runtime dependencies of Hariku or Orbit: don't add them to
requirements.txt. Orbit only ships the finished WAVs.

    python tools/orbit_convert_kenney.py <folder with the kenney_*.zip packs> [<output folder>]

The packs used (www.kenney.nl, all CC0 1.0): Casino Audio, Impact Sounds, RPG
Audio, Sci-fi Sounds and Interface Sounds, saved as kenney_casino-audio.zip,
kenney_impact-sounds.zip and so on. The output (by default a "wav" folder next
to the zips) has a folder per pack and index.tsv (pack, file, seconds, bytes).
Then extensions/orbit/orbit_sounds.py --kenney <output folder> mixes Orbit's
recorded cues from it (see RECORDED there).
"""
import glob
import io
import os
import sys
import wave
import zipfile

import numpy as np
import soundfile as sf

OUT_RATE = 22050
PEAK = 10 ** (-3 / 20)          # -3 dBFS
GATE = 10 ** (-50 / 20)         # silence below -50 dBFS is trimmed
FADE_MS = 8


def lowpass_kernel(cutoff, rate, taps=101):
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff / rate * n) * np.blackman(taps)
    return h / h.sum()


def resample(x, rate):
    if rate == OUT_RATE:
        return x
    x = np.convolve(x, lowpass_kernel(OUT_RATE * 0.45, rate), mode="same")
    if rate == 2 * OUT_RATE:
        return x[::2]
    t = np.arange(0, len(x) * OUT_RATE / rate) * rate / OUT_RATE
    return np.interp(t, np.arange(len(x)), x)


def tidy(x):
    loud = np.nonzero(np.abs(x) > GATE)[0]
    if len(loud) == 0:
        return None
    pad = int(0.005 * OUT_RATE)
    x = x[max(0, loud[0] - pad): loud[-1] + pad]
    peak = np.abs(x).max()
    if peak > 0:
        x = x * (PEAK / peak)
    fade = min(len(x) // 4, int(FADE_MS / 1000 * OUT_RATE))
    if fade > 1:
        x[:fade] *= np.linspace(0, 1, fade)
        x[-fade:] *= np.linspace(1, 0, fade)
    return x


def write_wav(path, x):
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(OUT_RATE)
        w.writeframes(pcm.tobytes())


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args or len(args) > 2:
        print(__doc__)
        return 2
    packs = os.path.abspath(args[0])
    out = os.path.abspath(args[1]) if len(args) > 1 else os.path.join(packs, "wav")
    rows = []
    for z in sorted(glob.glob(os.path.join(packs, "kenney_*.zip"))):
        pack = os.path.basename(z)[len("kenney_"):-len(".zip")]
        os.makedirs(os.path.join(out, pack), exist_ok=True)
        with zipfile.ZipFile(z) as f:
            for name in f.namelist():
                if not name.lower().endswith(".ogg") or os.path.basename(name) == "Preview.ogg":
                    continue
                data, rate = sf.read(io.BytesIO(f.read(name)), dtype="float64", always_2d=True)
                mono = data.mean(axis=1)
                x = tidy(resample(mono, rate))
                if x is None:
                    continue
                target = os.path.join(out, pack, os.path.splitext(os.path.basename(name))[0] + ".wav")
                write_wav(target, x)
                rows.append((pack, os.path.basename(target), len(x) / OUT_RATE, os.path.getsize(target)))
    with open(os.path.join(out, "index.tsv"), "w", encoding="utf-8") as f:
        for pack, name, secs, size in rows:
            f.write(f"{pack}\t{name}\t{secs:.2f}\t{size}\n")
    total = sum(r[3] for r in rows)
    print(f"{len(rows)} WAVs, {total / 1048576:.1f} MB in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
