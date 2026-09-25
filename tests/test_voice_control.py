# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The Voice Control extension without a microphone, a network or whisper.cpp:
# winmm is a fake that "records" synthetic samples, downloads come from fake
# servers, whisper-server is a fake process, and nothing is played or spoken.
# Every test uses a temporary data folder.

import array
import ctypes
import email.parser
import hashlib
import http.client
import importlib.util
import io
import json
import math
import os
import random
import socket
import sys
import threading
import time
import types
import urllib.request
import urllib.response
import wave
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VC_DIR = os.path.join(ROOT, "extensions", "voice_control")
if VC_DIR not in sys.path:
    sys.path.insert(0, VC_DIR)

import voice_control_audio as audio        # noqa: E402
import voice_control_download as dl        # noqa: E402
import voice_control_engine as engine      # noqa: E402
import voice_control_store as store        # noqa: E402
import voice_control_text as text          # noqa: E402

RATE = audio.SAMPLE_RATE


def wait_until(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(args[0] if args else kwargs)
        raise OSError("network is disabled in the tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    yield attempts


@pytest.fixture
def userdata(tmp_data_dir, tmp_path, monkeypatch):
    import core.api
    monkeypatch.setattr(core.api, "USER_DATA_DIR", str(tmp_path / "userdata"))
    return tmp_path / "userdata"


# ------------------------------------------------------------
# Synthetic sound (16-bit mono, 16 kHz)
# ------------------------------------------------------------

def pcm(samples):
    return array.array("h", [max(-32768, min(32767, int(s))) for s in samples]).tobytes()


def tone(ms, amplitude=6000, freq=220.0):
    n = RATE * ms // 1000
    return pcm(amplitude * math.sin(2 * math.pi * freq * i / RATE) for i in range(n))


def noise(ms, amplitude=80, seed=1):
    rng = random.Random(seed)
    return pcm(rng.uniform(-amplitude, amplitude) for _i in range(RATE * ms // 1000))


def zeros(ms):
    return bytes(2 * RATE * ms // 1000)


def chunks(data, ms=100):
    size = 2 * RATE * ms // 1000
    return [data[i:i + size] for i in range(0, len(data), size)]


def speech_clip(lead_ms=400, speech_ms=900, tail_ms=1500):
    return noise(lead_ms) + tone(speech_ms) + noise(tail_ms, seed=2)


def chirps(ms, amplitude=6000, freq=3500.0, on_ms=150, off_ms=60):
    """Birdsong: short high chirps with short gaps, a little louder than a hum."""
    out = b""
    while len(out) < 2 * RATE * ms // 1000:
        out += tone(on_ms, amplitude, freq) + noise(off_ms, seed=len(out))
    return out[:2 * RATE * ms // 1000]


def hum(ms, amplitude=3000, freq=150.0):
    """A low, steady roar (a vacuum cleaner, a fan): as low as a voice."""
    n = RATE * ms // 1000
    rng = random.Random(9)
    return pcm(amplitude * math.sin(2 * math.pi * freq * i / RATE) + rng.uniform(-60, 60)
               for i in range(n))


# ------------------------------------------------------------
# Voice activity
# ------------------------------------------------------------

class TestVoiceActivity:
    def test_speech_then_silence_ends_it(self):
        vad = audio.VoiceActivity(silence_ms=1000)
        state = None
        for piece in chunks(speech_clip()):
            state = vad.feed(piece)
            if vad.finished:
                break
        assert state == vad.DONE and vad.heard_speech
        assert 390 <= vad.speech_start_ms <= 460          # the tone began at 400 ms
        assert 1250 <= vad.speech_end_ms <= 1350          # and ended at 1300 ms
        assert vad.elapsed_ms <= 1300 + 1000 + 90

    def test_a_shorter_silence_setting_ends_sooner(self):
        vad = audio.VoiceActivity(silence_ms=600)
        for piece in chunks(speech_clip()):
            if vad.feed(piece) in vad.FINISHED:
                break
        assert vad.state == vad.DONE and vad.elapsed_ms <= 1300 + 600 + 90

    def test_pauses_between_words_do_not_end_it(self):
        clip = noise(400) + tone(400) + noise(300, seed=3) + tone(400) + noise(1200, seed=4)
        vad = audio.VoiceActivity(silence_ms=1000)
        for piece in chunks(clip):
            vad.feed(piece)
        assert vad.state == vad.DONE and vad.speech_end_ms >= 1450

    def test_nothing_said_within_five_seconds(self):
        vad = audio.VoiceActivity(start_timeout_ms=5000)
        for piece in chunks(noise(6000)):
            vad.feed(piece)
        assert vad.state == vad.NO_SPEECH and not vad.heard_speech
        assert 5000 <= vad.elapsed_ms <= 5030

    def test_talking_for_too_long(self):
        vad = audio.VoiceActivity(max_ms=12000)
        for piece in chunks(noise(300) + tone(13000)):
            if vad.feed(piece) in vad.FINISHED:
                break
        assert vad.state == vad.TOO_LONG and vad.heard_speech
        assert vad.elapsed_ms == 12000

    def test_a_click_is_not_speech(self):
        vad = audio.VoiceActivity(start_timeout_ms=2000)
        for piece in chunks(noise(500) + tone(60, amplitude=20000) + noise(2000, seed=5)):
            vad.feed(piece)
        assert vad.state == vad.NO_SPEECH

    def test_a_noisy_room(self):
        loud_room = noise(400, amplitude=2500) + tone(900, amplitude=16000) + \
            noise(1500, amplitude=2500, seed=2)
        vad = audio.VoiceActivity()
        for piece in chunks(loud_room):
            vad.feed(piece)
        assert vad.state == vad.DONE and vad.heard_speech
        vad = audio.VoiceActivity(start_timeout_ms=3000)
        for piece in chunks(noise(4000, amplitude=2500)):
            vad.feed(piece)
        assert vad.state == vad.NO_SPEECH          # the fan alone is not speech

    def test_bytes_arrive_in_any_size(self):
        data = speech_clip()
        vad = audio.VoiceActivity()
        for i in range(0, len(data), 777):
            vad.feed(data[i:i + 777])
        assert vad.state == vad.DONE

    def test_speech_bytes_keep_a_margin(self):
        data = speech_clip()
        vad = audio.VoiceActivity()
        vad.feed(data)
        part = vad.speech_bytes(data, margin_ms=300)
        seconds = len(part) / (2.0 * RATE)
        assert 1.3 <= seconds <= 1.7            # 0.9 s of speech and 0.3 s either side
        empty = audio.VoiceActivity()
        assert empty.speech_bytes(b"abcd") == b"abcd"

    def test_crossing_rate(self):
        def rate(data):
            return audio.crossing_rate(array.array("h", data))
        assert rate(tone(300, freq=220.0)) == pytest.approx(2 * 220 / RATE, abs=0.003)
        assert rate(tone(300, freq=3500.0)) == pytest.approx(2 * 3500 / RATE, abs=0.01)
        assert 0.4 < rate(noise(300)) < 0.6
        assert audio.crossing_rate(array.array("h", [5])) == 0.0

    def test_birdsong_never_starts_speech(self):
        vad = audio.VoiceActivity(start_timeout_ms=3000)
        assert run(vad, noise(300) + chirps(4000, amplitude=12000)) == vad.NO_SPEECH

    def test_birdsong_after_the_voice_is_a_pause(self):
        # A command, then birds that never stop (at home, a headset microphone).
        vad = audio.VoiceActivity(silence_ms=1000)
        assert run(vad, noise(400) + tone(900) + chirps(9000)) == vad.DONE
        assert 1250 <= vad.speech_end_ms <= 1350 and vad.elapsed_ms <= 1300 + 1000 + 90

    def test_birdsong_during_the_voice_doesnt_matter(self):
        clip = noise(400) + tone(900) + chirps(300) + tone(600) + chirps(3000)
        vad = audio.VoiceActivity(silence_ms=1000)
        assert run(vad, clip) == vad.DONE
        assert 2150 <= vad.speech_end_ms <= 2250               # the second word, not a chirp

    def test_a_sound_well_below_the_voice_is_a_pause(self):
        # A low hum 17 dB under the voice: loud enough to beat the room, not the voice.
        vad = audio.VoiceActivity(silence_ms=1000)
        assert run(vad, noise(400) + tone(900, amplitude=6000) + hum(6000, amplitude=800))             == vad.DONE
        assert vad.voice_level == pytest.approx(6000 / math.sqrt(2), rel=0.05)
        assert vad.elapsed_ms <= 1300 + 1000 + 90

    def test_a_recording_that_ran_too_long_keeps_the_voice(self):
        # A hum only 9 dB under the voice keeps it going to the cap; the voice
        # itself ended at 1300 ms, and that is the part to recognise.
        data = noise(400) + tone(900, amplitude=6000) + hum(12000, amplitude=2200)
        vad = audio.VoiceActivity(max_ms=12000)
        assert run(vad, data) == vad.TOO_LONG and vad.noisy
        assert 1250 <= vad.voice_end_ms <= 1350
        part = vad.speech_bytes(data, margin_ms=300, voice_only=True)
        assert 1.3 <= len(part) / (2.0 * RATE) <= 1.7
        assert len(vad.speech_bytes(data)) > 10 * 2 * RATE     # without voice_only: everything

    def test_levels(self):
        assert audio.level_db(0) == -96.0
        assert audio.level_db(32768) == pytest.approx(0.0)
        assert audio.level_db(3276.8) == pytest.approx(-20.0)
        assert audio.rms(array.array("h", [3, -3, 3, -3])) == 3.0


# ------------------------------------------------------------
# Microphone sensitivity
# ------------------------------------------------------------

def room(ms, level, seed=1):
    """Room noise with an RMS of about `level`."""
    return noise(ms, amplitude=level * math.sqrt(3), seed=seed)


def voice(ms, level):
    """A steady "voice" with an RMS of `level`: a 200 Hz tone, six whole
    periods in each 30 ms frame (keep `ms` a multiple of 30)."""
    return tone(ms, amplitude=level * math.sqrt(2), freq=200.0)


def quiet_sentence(low=150, high=250, words=5, seed=7):
    """Words between `low` and `high` (RMS) with short gaps of room (RMS 20)
    between them, the way a laptop microphone with a low input level hears a
    normal voice."""
    rng = random.Random(seed)
    out = b""
    for i in range(words):
        out += voice(rng.choice((240, 300, 360)), rng.uniform(low, high))
        out += room(rng.choice((60, 90, 120)), 20, seed=seed + i)
    return out


def run(vad, data):
    for piece in chunks(data):
        if vad.feed(piece) in vad.FINISHED:
            break
    return vad.state


class TestSensitivity:
    def test_the_presets(self):
        assert audio.SENSITIVITY == {"low": (400.0, 3.5), "normal": (150.0, 2.5),
                                     "high": (80.0, 2.0), "very_high": (40.0, 1.6)}
        assert audio.SENSITIVITIES == ("low", "normal", "high", "very_high")
        assert audio.DEFAULT_SENSITIVITY == "normal"
        vad = audio.VoiceActivity()
        assert (vad.sensitivity, vad.min_level, vad.ratio) == ("normal", 150.0, 2.5)
        vad = audio.VoiceActivity(sensitivity="very_high")
        assert (vad.min_level, vad.ratio) == (40.0, 1.6)
        vad = audio.VoiceActivity(sensitivity="shouting")
        assert (vad.sensitivity, vad.min_level, vad.ratio) == ("normal", 150.0, 2.5)
        vad = audio.VoiceActivity(sensitivity="low", min_level=500, ratio=4)
        assert (vad.min_level, vad.ratio) == (500.0, 4.0)

    @pytest.mark.parametrize("name, quiet_room, loud_room", [
        ("low", (400, 240), (700, 420)),
        ("normal", (150, 90), (500, 300)),
        ("high", (80, 48), (400, 250)),
        ("very_high", (40, 25), (320, 250)),
    ])
    def test_each_presets_thresholds(self, name, quiet_room, loud_room):
        vad = audio.VoiceActivity(sensitivity=name)
        start, keep = vad.thresholds()
        assert start == vad.min_level and keep == pytest.approx(0.6 * start)
        vad.noise = 20.0
        assert vad.thresholds() == pytest.approx(quiet_room)
        vad.noise = 200.0
        assert vad.thresholds() == pytest.approx(loud_room)
        # "Keep speaking" stays relative, but never at the room's own level.
        assert vad.thresholds()[1] >= 1.25 * vad.noise
        assert audio.start_level(name, 20.0) == pytest.approx(quiet_room[0])

    def test_quiet_speech_in_a_quiet_room(self):
        clip = room(420, 20) + quiet_sentence() + room(1500, 20, seed=3)
        normal = audio.VoiceActivity()
        assert run(normal, clip) == normal.DONE and normal.heard_speech
        assert 400 <= normal.speech_start_ms <= 460
        low = audio.VoiceActivity(sensitivity="low")
        run(low, clip)
        assert not low.heard_speech
        first = audio.VoiceActivity(min_level=300.0, ratio=3.0)   # what the first version needed
        run(first, clip)
        assert not first.heard_speech
        for name in ("high", "very_high"):
            vad = audio.VoiceActivity(sensitivity=name)
            assert run(vad, clip) == vad.DONE, name

    def test_each_preset_hears_a_normal_voice_and_ends(self):
        clip = room(420, 20) + voice(900, 3000) + room(1500, 20, seed=2)
        for name in audio.SENSITIVITIES:
            vad = audio.VoiceActivity(sensitivity=name)
            assert run(vad, clip) == vad.DONE, name
            assert 1250 <= vad.speech_end_ms <= 1350 and not vad.noisy

    def test_the_room_alone_is_not_speech(self):
        for level in (20, 300, 1500):
            for name in audio.SENSITIVITIES:
                vad = audio.VoiceActivity(sensitivity=name, start_timeout_ms=3000)
                assert run(vad, room(4000, level, seed=level)) == vad.NO_SPEECH, (name, level)

    def test_a_noisy_room(self):
        clip = room(420, 1500) + voice(900, 11000) + room(1500, 1500, seed=2)
        for name in audio.SENSITIVITIES:
            vad = audio.VoiceActivity(sensitivity=name)
            assert run(vad, clip) == vad.DONE and vad.heard_speech, name

    def test_noise_that_starts_later_is_ended_by_the_cap(self):
        # Quiet while the room is measured, then a vacuum cleaner: it starts
        # "speech" that never pauses, and only the 12-second cap ends it.
        vad = audio.VoiceActivity(max_ms=12000)
        assert run(vad, room(150, 20) + hum(13000, 3000)) == vad.TOO_LONG
        assert vad.elapsed_ms == 12000 and vad.noisy
        # Hiss, however loud, is never speech.
        vad = audio.VoiceActivity(max_ms=12000)
        assert run(vad, room(150, 20) + room(13000, 3000, seed=4)) == vad.NO_SPEECH

    def test_long_speech_with_pauses_is_not_noise(self):
        clip = room(300, 20) + b"".join(voice(600, 3000) + room(300, 20, seed=i)
                                        for i in range(16))
        vad = audio.VoiceActivity(max_ms=12000)
        assert run(vad, clip) == vad.TOO_LONG
        assert vad.longest_pause_ms >= 270 and not vad.noisy

    def test_a_quiet_voice_never_becomes_the_room(self):
        # Murmuring below the start level for 3 seconds (a voice too quiet to
        # start, or someone warming up): the room must stay the room, or the
        # start level would climb away from the voice.
        rng = random.Random(11)
        murmur = b"".join(voice(30, rng.uniform(35, 140)) for _i in range(100))
        vad = audio.VoiceActivity(start_timeout_ms=20000)
        run(vad, room(300, 20) + murmur)
        assert vad.state == vad.WAITING
        assert vad.noise < 25
        assert vad.thresholds()[0] == 150.0
        assert run(vad, voice(600, 180) + room(1500, 20, seed=5)) == vad.DONE

    def test_the_room_is_followed_down_quickly_and_up_slowly(self):
        vad = audio.VoiceActivity(start_timeout_ms=20000)
        run(vad, room(150, 60) + room(1500, 20, seed=2))
        assert vad.noise == pytest.approx(20, abs=3)          # quieter: followed
        run(vad, room(3000, 26, seed=3))
        assert 23 < vad.noise < 28                            # a little louder: followed
        run(vad, room(3000, 60, seed=4))
        assert vad.noise < 30                                 # much louder: not the room


# ------------------------------------------------------------
# The microphone test's calibration
# ------------------------------------------------------------

class TestCalibration:
    def test_frame_levels(self):
        levels = audio.frame_levels(voice(300, 200) + room(300, 20))
        assert len(levels) == 20
        assert levels[:10] == [pytest.approx(200, abs=1)] * 10
        assert all(15 < level < 25 for level in levels[10:])
        assert audio.frame_levels(b"") == [] and audio.frame_levels(bytes(100)) == []

    def test_measure(self):
        assert audio.measure([20.0] * 50 + [200.0] * 40 + [21.0] * 30) == (20.0, 200.0)
        levels = audio.frame_levels(room(600, 20) + quiet_sentence() + room(1500, 20, seed=3))
        room_level, voice_level = audio.measure(levels)
        assert 15 < room_level < 25 and 190 < voice_level < 260
        assert audio.measure(audio.frame_levels(room(4000, 20)))[1] is None    # nobody spoke
        assert audio.measure([20.0] * 100 + [500.0] * 5)[1] is None           # a click
        assert audio.measure([0.0] * 50 + [300.0] * 20) == (0.0, 300.0)       # a noise gate
        assert audio.measure([]) == (0.0, None)

    @pytest.mark.parametrize("room_level, voice_level, sensitivity, problem", [
        (20, 1000, "very_high", None),      # a quiet room: as sensitive as it gets
        (20, 200, "very_high", None),       # the laptop microphone with a low level
        (0, 500, "very_high", None),        # a noise gate: the room is digital silence
        (40, 400, "high", None),            # -58 dB: Very high's own level is too close
        (80, 1000, "normal", None),         # -52 dB: a fan
        (200, 3000, "low", None),           # -44 dB: a loud fan, a loud voice
        (30, 150, "very_high", None),       # High wouldn't hear it: one step more
        (300, 5000, "low", None),           # louder than any preset allows; Low still hears
        (300, 1600, "normal", None),        # ...and Normal when Low doesn't
        (20, 60, "very_high", "too_quiet"),
        (10, 70, "very_high", "too_quiet"),
        (100, 250, "normal", "too_noisy"),
        (500, 1200, "low", "too_noisy"),
        (20, None, None, "no_speech"),
    ])
    def test_calibrate(self, room_level, voice_level, sensitivity, problem):
        result = audio.calibrate(room_level, voice_level)
        assert (result.sensitivity, result.problem) == (sensitivity, problem)
        assert (result.room, result.voice) == (room_level, voice_level)

    def test_the_rule_holds_everywhere(self):
        levels = [0, 5, 10, 15, 20, 26, 30, 40, 53, 60, 80, 100, 150, 200, 266, 300, 500, 1000]
        for room_level in levels:
            for voice_level in [2 * room_level + v for v in (10, 40, 80, 150, 300, 800, 3000)]:
                result = audio.calibrate(room_level, voice_level)
                assert result.sensitivity in audio.SENSITIVITIES
                if result.problem is None:
                    # The voice is at least twice the start level...
                    assert audio.start_level(result.sensitivity, room_level) <= voice_level / 2
                    # ...and no more sensitive preset both hears it and suits the room.
                    index = audio.SENSITIVITIES.index(result.sensitivity)
                    for name in audio.SENSITIVITIES[index + 1:]:
                        assert audio.SENSITIVITY[name][0] < 1.5 * room_level
                else:
                    assert audio.start_level("very_high", room_level) > voice_level / 2


def test_wav_bytes_in_memory():
    data = tone(500)
    blob = audio.wav_bytes(data)
    with wave.open(io.BytesIO(blob)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        assert w.readframes(w.getnframes()) == data
    assert audio.seconds_of(data) == 0.5


@pytest.mark.parametrize("values, expected", [
    ({}, None),
    ({("HKCU", "desktop"): "Allow"}, None),
    ({("HKLM", "main"): "Deny"}, "blocked_device"),
    ({("HKCU", "main"): "Deny"}, "blocked_apps"),
    ({("HKCU", "desktop"): "Deny"}, "blocked_desktop"),
    ({("HKCU", "main"): "Allow", ("HKCU", "desktop"): "Deny"}, "blocked_desktop"),
])
def test_windows_privacy_switches(values, expected):
    def read(root, path):
        which = "desktop" if path.endswith("NonPackaged") else "main"
        assert path.startswith(audio.CONSENT_KEY)
        return values.get((root, which))

    assert audio.microphone_blocked(read) == expected


def test_reading_the_real_privacy_switches_does_not_fail():
    assert audio.microphone_blocked() in (None, "blocked_device", "blocked_apps",
                                          "blocked_desktop")


# ------------------------------------------------------------
# Recording with a fake winmm
# ------------------------------------------------------------

class FakeWinmm:
    """waveIn: each queued buffer is filled with the next chunk once started."""

    def __init__(self, pieces, devices=1, open_code=0, add_code=0):
        self.pieces = list(pieces)
        self.devices = devices
        self.open_code = open_code
        self.add_code = add_code
        self.queue = []
        self.started = False
        self.calls = []

    def waveInGetNumDevs(self):
        return self.devices

    def waveInOpen(self, phandle, device, pformat, callback, instance, flags):
        fmt = pformat._obj
        self.opened = (device, callback, flags, fmt.wFormatTag, fmt.nChannels,
                       fmt.nSamplesPerSec, fmt.nAvgBytesPerSec, fmt.nBlockAlign,
                       fmt.wBitsPerSample)
        phandle._obj.value = 1234
        self.calls.append("open")
        return self.open_code

    def waveInPrepareHeader(self, handle, pheader, size):
        self.calls.append("prepare")
        return 0

    def waveInAddBuffer(self, handle, pheader, size):
        if self.add_code:
            return self.add_code
        self.queue.append(pheader._obj)
        self._fill()
        return 0

    def waveInStart(self, handle):
        self.calls.append("start")
        self.started = True
        self._fill()
        return 0

    def _fill(self):
        while self.started and self.queue and self.pieces:
            header, piece = self.queue.pop(0), self.pieces.pop(0)
            ctypes.memmove(header.lpData, piece, len(piece))
            header.dwBytesRecorded = len(piece)
            header.dwFlags |= audio.WHDR_DONE

    def waveInReset(self, handle):
        self.calls.append("reset")
        return 0

    def waveInStop(self, handle):
        return 0

    def waveInUnprepareHeader(self, handle, pheader, size):
        self.calls.append("unprepare")
        return 0

    def waveInClose(self, handle):
        self.calls.append("close")
        return 0


class TestRecorder:
    def test_records_16khz_mono_until_speech_ends(self):
        clip = speech_clip()
        fake = FakeWinmm(chunks(clip))
        vad = audio.VoiceActivity()
        data = audio.Recorder(winmm=fake, sleep=lambda s: None).record(
            lambda piece: vad.feed(piece) in vad.FINISHED)
        assert fake.opened == (audio.WAVE_MAPPER, 0, audio.CALLBACK_NULL, 1, 1, 16000, 32000,
                               2, 16)
        assert vad.state == vad.DONE and data == clip[:len(data)]
        assert fake.calls[-audio.BUFFERS - 2:] == ["reset"] + ["unprepare"] * audio.BUFFERS + \
            ["close"]

    def test_stop_ends_the_recording(self):
        stop = threading.Event()
        fake = FakeWinmm(chunks(tone(3000)))
        seen = []

        def on_piece(piece):
            seen.append(piece)
            if len(seen) == 3:
                stop.set()
            return False

        data = audio.Recorder(winmm=fake, sleep=lambda s: None).record(on_piece, stop=stop)
        assert len(data) == 3 * 3200 and "close" in fake.calls

    def test_no_more_sound_ends_at_the_time_limit(self):
        now = [0.0]

        def sleep(seconds):
            now[0] += seconds

        fake = FakeWinmm(chunks(tone(300)))
        data = audio.Recorder(winmm=fake, sleep=sleep, clock=lambda: now[0]).record(
            lambda piece: False, max_seconds=2.0)
        assert len(data) == 3 * 3200 and fake.calls[-1] == "close"

    @pytest.mark.parametrize("devices, code, kind", [
        (0, 0, "none"), (1, audio.MMSYSERR_BADDEVICEID, "none"),
        (1, audio.MMSYSERR_ALLOCATED, "busy"), (1, audio.MMSYSERR_NODRIVER, "none"),
        (1, audio.WAVERR_BADFORMAT, "failed"),
    ])
    def test_errors(self, devices, code, kind):
        fake = FakeWinmm([], devices=devices, open_code=code)
        with pytest.raises(audio.MicrophoneError) as error:
            audio.Recorder(winmm=fake).record(lambda piece: True)
        assert error.value.kind == kind
        assert "close" not in fake.calls        # nothing was opened

    def test_a_failure_after_opening_still_closes(self):
        fake = FakeWinmm([], add_code=audio.MMSYSERR_NOMEM)
        with pytest.raises(audio.MicrophoneError):
            audio.Recorder(winmm=fake).record(lambda piece: True)
        assert fake.calls[-1] == "close"

    def test_structures_match_windows(self):
        assert ctypes.sizeof(audio.WAVEFORMATEX) == 18
        assert audio.WAVEHDR.dwFlags.offset == (24 if ctypes.sizeof(ctypes.c_void_p) == 8
                                                else 16)


# ------------------------------------------------------------
# Downloads
# ------------------------------------------------------------

def test_the_pinned_downloads():
    assert dl.RUNTIME_URL == ("https://github.com/ggml-org/whisper.cpp/releases/download/"
                              "b5130/whisper-bin-x64.zip")
    assert dl.RUNTIME_SIZE == 8573270
    assert dl.RUNTIME_SHA256 == \
        "f9ec6c52a2e949b62ab51fa21d0d497958f9e41c3010c157c4e42932d5316f3c"
    assert dl.model_url("tiny") == \
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin"
    assert {name: info["sha256"] for name, info in dl.MODELS.items()} == {
        "tiny": "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
        "base": "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
        "small": "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
    }
    shown = {name: round(info["size"] / 1e6, 1) for name, info in dl.MODELS.items()}
    assert shown == {"tiny": 77.7, "base": 148.0, "small": 487.6}


@pytest.mark.parametrize("url, allowed", [
    ("https://github.com/ggml-org/whisper.cpp/releases/download/b5130/whisper-bin-x64.zip", True),
    ("https://release-assets.githubusercontent.com/github-production-release-asset/1", True),
    ("https://objects.githubusercontent.com/x", True),
    ("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin", True),
    ("https://hf.co/x", True), ("https://cdn-lfs.hf.co/x", True),
    ("https://cas-bridge.xethub.hf.co/x", True),
    ("http://huggingface.co/x", False), ("https://evil.example/x", False),
    ("https://huggingface.co.evil.example/x", False), ("https://user@github.com/x", False),
    ("https://github.com:8443/x", False), ("ftp://github.com/x", False), ("", False),
])
def test_allowed_hosts(url, allowed):
    assert dl.host_allowed(url) is allowed


class FakeHttps(urllib.request.HTTPSHandler):
    """Answers HTTPS requests from a table through urllib's real redirects."""

    def __init__(self, routes):
        super().__init__()
        self.routes = routes
        self.seen = []

    def https_open(self, req):
        self.seen.append(req.full_url)
        if req.full_url not in self.routes:
            raise AssertionError(f"unexpected request to {req.full_url}")
        status, headers, body = self.routes[req.full_url]
        head = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        message = email.parser.Parser(_class=http.client.HTTPMessage).parsestr(head)
        response = urllib.response.addinfourl(io.BytesIO(body), message, req.full_url, status)
        response.msg = http.client.responses.get(status, "")
        return response


def test_redirects_to_the_cdns_are_followed_and_others_refused():
    good = FakeHttps({
        dl.model_url("tiny"): (302, {"Location": "https://cas-bridge.xethub.hf.co/tiny?x=1"},
                               b""),
        "https://cas-bridge.xethub.hf.co/tiny?x=1": (200, {}, b"model"),
    })
    with dl.open_url(dl.model_url("tiny"), opener=dl.build_opener(good)) as response:
        assert response.read() == b"model"
    bad = FakeHttps({dl.RUNTIME_URL: (302, {"Location": "https://evil.example/w.zip"}, b"")})
    with pytest.raises(dl.DownloadError) as error:
        dl.open_url(dl.RUNTIME_URL, opener=dl.build_opener(bad))
    assert error.value.kind == "host" and bad.seen == [dl.RUNTIME_URL]


def test_offline(no_network):
    with pytest.raises(dl.DownloadError) as error:
        dl.open_url(dl.model_url("tiny"))
    assert error.value.kind == "offline"


class FakeResponse:
    def __init__(self, status, body, headers=None, fail_after=None):
        self.status = status
        self.headers = headers or {}
        self._body = io.BytesIO(body)
        self._fail_after = fail_after
        self._sent = 0

    def read(self, n=-1):
        if self._fail_after is not None and self._sent >= self._fail_after:
            raise ConnectionResetError("connection lost")
        if self._fail_after is not None:
            n = min(n if n > 0 else self._fail_after, self._fail_after - self._sent)
        data = self._body.read(n)
        self._sent += len(data)
        return data

    def geturl(self):
        return ""

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Server:
    """Serves files by URL, honouring Range."""

    def __init__(self, files, ranges=True, fail_after=None, claim_length=None):
        self.files = dict(files)
        self.ranges = ranges
        self.fail_after = fail_after
        self.claim_length = claim_length
        self.requests = []

    def __call__(self, url, headers=None, timeout=None, opener=None):
        headers = headers or {}
        self.requests.append((url, dict(headers)))
        if url not in self.files:
            raise dl.DownloadError("http", "404", code=404)
        body = self.files[url]
        fail_after, self.fail_after = self.fail_after, None
        rng = headers.get("Range")
        if rng and self.ranges:
            start = int(rng.split("=")[1].rstrip("-"))
            return FakeResponse(206, body[start:], {
                "Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}",
                "Content-Length": str(len(body) - start)}, fail_after)
        length = self.claim_length if self.claim_length is not None else len(body)
        return FakeResponse(200, body, {"Content-Length": str(length)}, fail_after)


URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/test.bin"


class TestDownloadFile:
    DATA = bytes(range(256)) * 400          # 102,400 bytes

    def sha(self):
        return hashlib.sha256(self.DATA).hexdigest()

    def test_downloads_and_verifies(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({URL: self.DATA}))
        seen = []
        dest = str(tmp_path / "models" / "test.bin")
        assert dl.download_file(URL, dest, self.sha(), len(self.DATA), progress=seen.append) \
            == dest
        assert open(dest, "rb").read() == self.DATA
        assert seen[-1] == len(self.DATA) and not os.path.exists(dest + ".part")

    def test_a_wrong_checksum_deletes_the_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({URL: self.DATA}))
        dest = str(tmp_path / "test.bin")
        with pytest.raises(dl.DownloadError) as error:
            dl.download_file(URL, dest, "0" * 64, len(self.DATA))
        assert error.value.kind == "verify"
        assert not os.path.exists(dest) and not os.path.exists(dest + ".part")

    def test_a_cut_connection_is_continued(self, tmp_path, monkeypatch):
        server = Server({URL: self.DATA}, fail_after=40000)
        monkeypatch.setattr(dl, "open_url", server)
        dest = str(tmp_path / "test.bin")
        with pytest.raises(dl.DownloadError) as error:
            dl.download_file(URL, dest, self.sha(), len(self.DATA))
        assert error.value.kind == "offline"
        assert os.path.getsize(dest + ".part") == 40000          # kept for next time
        dl.download_file(URL, dest, self.sha(), len(self.DATA))
        assert server.requests[-1][1] == {"Range": "bytes=40000-"}
        assert open(dest, "rb").read() == self.DATA

    def test_a_server_without_ranges_starts_over(self, tmp_path, monkeypatch):
        dest = str(tmp_path / "test.bin")
        with open(dest + ".part", "wb") as f:
            f.write(self.DATA[:1000])
        monkeypatch.setattr(dl, "open_url", Server({URL: self.DATA}, ranges=False))
        dl.download_file(URL, dest, self.sha(), len(self.DATA))
        assert open(dest, "rb").read() == self.DATA

    def test_cancel_deletes_the_part(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({URL: self.DATA}))
        dest = str(tmp_path / "test.bin")
        calls = []

        def cancelled():
            calls.append(1)
            return len(calls) > 1

        with pytest.raises(dl.Cancelled):
            dl.download_file(URL, dest, self.sha(), len(self.DATA), cancelled=cancelled)
        assert not os.path.exists(dest + ".part")

    def test_far_too_big_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({URL: self.DATA * 30}))
        dest = str(tmp_path / "test.bin")
        with pytest.raises(dl.DownloadError) as error:
            dl.download_file(URL, dest, self.sha(), len(self.DATA))
        assert error.value.kind == "size" and not os.path.exists(dest + ".part")

    def test_an_early_end_is_noticed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({URL: self.DATA},
                                                   claim_length=len(self.DATA) + 10))
        with pytest.raises(dl.DownloadError) as error:
            dl.download_file(URL, str(tmp_path / "t.bin"), self.sha(), len(self.DATA))
        assert error.value.kind == "offline"

    def test_an_existing_good_file_is_kept(self, tmp_path, monkeypatch):
        dest = str(tmp_path / "test.bin")
        with open(dest, "wb") as f:
            f.write(self.DATA)
        server = Server({})
        monkeypatch.setattr(dl, "open_url", server)
        dl.download_file(URL, dest, self.sha(), len(self.DATA))
        assert server.requests == []

    def test_a_checksum_is_required(self, tmp_path):
        with pytest.raises(ValueError):
            dl.download_file(URL, str(tmp_path / "x"), "", 10)


def fake_runtime_zip(with_exe=True, evil=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        if with_exe:
            z.writestr("Release/whisper-server.exe", b"MZ fake server")
        z.writestr("Release/whisper.dll", b"MZ fake dll")
        z.writestr("Release/ggml.dll", b"MZ fake dll")
        if evil:
            z.writestr("../evil.bat", b"echo evil")
    return buffer.getvalue()


def serve_runtime(monkeypatch, data):
    monkeypatch.setattr(dl, "RUNTIME_SIZE", len(data))
    monkeypatch.setattr(dl, "RUNTIME_SHA256", hashlib.sha256(data).hexdigest())
    server = Server({dl.RUNTIME_URL: data})
    monkeypatch.setattr(dl, "open_url", server)
    return server


class TestInstall:
    def test_the_runtime(self, userdata, monkeypatch):
        serve_runtime(monkeypatch, fake_runtime_zip())
        root = store.root_dir()
        exe = dl.install_runtime(root)
        assert exe == os.path.join(root, "runtime", "Release", "whisper-server.exe")
        assert store.runtime_installed(root) and store.server_exe(root) == exe
        marker = store.read_json(os.path.join(root, "runtime", "runtime.json"))
        assert marker["version"] == "b5130" and marker["exe"] == os.path.join(
            "Release", "whisper-server.exe")
        assert not os.listdir(store.downloads_dir(root))          # the zip is gone

    def test_a_runtime_without_the_server_is_refused(self, userdata, monkeypatch):
        serve_runtime(monkeypatch, fake_runtime_zip(with_exe=False))
        root = store.root_dir()
        with pytest.raises(dl.DownloadError) as error:
            dl.install_runtime(root)
        assert error.value.kind == "extract" and not store.runtime_installed(root)
        assert not os.path.exists(store.runtime_dir(root) + ".new")

    def test_zip_slip_is_refused(self, userdata, monkeypatch):
        serve_runtime(monkeypatch, fake_runtime_zip(evil=True))
        root = store.root_dir()
        with pytest.raises(dl.DownloadError) as error:
            dl.install_runtime(root)
        assert error.value.kind == "extract"
        assert not os.path.exists(os.path.join(root, "evil.bat"))

    def test_a_model(self, userdata, monkeypatch):
        data = b"ggml" + bytes(5000)
        monkeypatch.setitem(dl.MODELS, "tiny", {"file": "ggml-tiny.bin", "size": len(data),
                                                "sha256": hashlib.sha256(data).hexdigest()})
        monkeypatch.setattr(dl, "open_url", Server({dl.model_url("tiny"): data}))
        root = store.root_dir()
        assert store.installed_models(root) == []
        dl.install_model("tiny", root)
        assert store.installed_models(root) == ["tiny"]
        assert store.remove_model(root, "tiny") and store.installed_models(root) == []
        with pytest.raises(ValueError):
            dl.install_model("huge", root)

    def test_a_changed_model_file_no_longer_counts(self, userdata):
        root = store.root_dir()
        os.makedirs(store.models_dir(root))
        with open(store.model_path(root, "base"), "wb") as f:
            f.write(b"12345")
        assert not store.model_installed(root, "base")            # never verified
        store.write_model_marker(root, "base", 5, "abc")
        assert store.installed_models(root) == ["base"]
        with open(store.model_path(root, "base"), "ab") as f:
            f.write(b"6")
        assert store.installed_models(root) == []


# ------------------------------------------------------------
# Files and settings
# ------------------------------------------------------------

WAKE_DEFAULTS = {"wake": False, "wake_phrase": "Hey Aruna", "wake_sensitivity": "normal",
                 "wake_quiet_hours": False}


class TestStore:
    def test_settings(self, userdata):
        assert store.load_settings() == dict({"model": "auto", "listen_on_open": True,
                                              "silence_ms": 1000, "sensitivity": "normal",
                                              "speeds": {}}, **WAKE_DEFAULTS)
        assert store.normalize_settings({"model": "huge", "silence_ms": 7, "sensitivity": "max",
                                         "speeds": {"tiny": 1.63, "base": "fast", "small": -1,
                                                    "giant": 3}}) == dict({
            "model": "auto", "listen_on_open": True, "silence_ms": 1000, "sensitivity": "normal",
            "speeds": {"tiny": 1.63}}, **WAKE_DEFAULTS)
        store.save_settings({"model": "base", "listen_on_open": False, "silence_ms": 1500})
        assert store.load_settings()["model"] == "base"

    def test_the_sensitivity_setting(self, userdata):
        assert store.SENSITIVITY_CHOICES == ("low", "normal", "high", "very_high")
        for name in store.SENSITIVITY_CHOICES:
            assert store.normalize_settings({"sensitivity": name})["sensitivity"] == name
        for bad in ("max", "", None, 3, ["high"], {"high": 1}, "HIGH"):
            assert store.normalize_settings({"sensitivity": bad})["sensitivity"] == "normal"
        store.save_settings(dict(store.load_settings(), sensitivity="very_high"))
        assert store.load_settings()["sensitivity"] == "very_high"

    def test_settings_saved_before_the_sensitivity_existed_get_normal(self, userdata):
        import core.api
        core.api.save_data(store.SETTINGS_NAME, {"model": "base", "listen_on_open": False,
                                                 "silence_ms": 1500, "speeds": {"tiny": 1.5}})
        assert store.load_settings() == dict({"model": "base", "listen_on_open": False,
                                              "silence_ms": 1500, "sensitivity": "normal",
                                              "speeds": {"tiny": 1.5}}, **WAKE_DEFAULTS)

    def test_a_speed_is_measured_once(self, userdata):
        store.record_speed("tiny", 1.634)
        store.record_speed("tiny", 9.0)
        assert store.load_settings()["speeds"] == {"tiny": 1.63}
        store.forget_speed("tiny")
        assert store.load_settings()["speeds"] == {}

    def test_finding_the_server(self, tmp_path):
        folder = tmp_path / "unpacked"
        (folder / "bin" / "x64").mkdir(parents=True)
        (folder / "bin" / "x64" / "whisper-server.exe").write_bytes(b"MZ")
        assert store.find_server_exe(str(folder)) == str(
            folder / "bin" / "x64" / "whisper-server.exe")
        (folder / "Release").mkdir()
        (folder / "Release" / "whisper-server.exe").write_bytes(b"MZ")
        assert store.find_server_exe(str(folder)) == str(folder / "Release" /
                                                         "whisper-server.exe")
        assert store.find_server_exe(str(tmp_path / "empty")) is None

    def test_a_marker_cannot_point_outside(self, userdata):
        root = store.root_dir()
        store.write_runtime_marker(root, {"exe": "..\\..\\evil.exe"})
        assert store.server_exe(root) == os.path.join(root, "runtime", "Release",
                                                      "whisper-server.exe")

    def test_no_recording_is_stored(self):
        with open(os.path.join(VC_DIR, "main.py"), encoding="utf-8") as f:
            source = f.read()
        assert "tempfile" not in source and ".wav\"" not in source


# ------------------------------------------------------------
# Choosing a model, the prompt
# ------------------------------------------------------------

@pytest.mark.parametrize("setting, installed, speeds, purpose, expected", [
    ("auto", [], {}, "command", None),
    ("auto", ["tiny"], {}, "command", "tiny"),
    ("auto", ["tiny", "base"], {}, "command", "tiny"),       # base: 4.8 s is too slow
    ("auto", ["tiny", "base"], {}, "reminder", "base"),
    ("auto", ["tiny", "base", "small"], {}, "reminder", "base"),
    ("auto", ["tiny", "base"], {"base": 1.2}, "command", "base"),   # a fast computer
    ("auto", ["tiny", "base", "small"], {"base": 1.2, "small": 2.2}, "command", "small"),
    ("auto", ["small"], {}, "command", "small"),             # the only one
    ("auto", ["base", "small"], {}, "command", "base"),      # the fastest when none fits
    ("base", ["tiny", "base"], {}, "command", "base"),       # chosen and installed
    ("small", ["tiny"], {}, "command", "tiny"),              # chosen but not installed
])
def test_choose_model(setting, installed, speeds, purpose, expected):
    assert engine.choose_model(setting, installed, speeds, purpose) == expected


@pytest.mark.parametrize("setting, installed, used, expected", [
    ("auto", ["tiny", "base"], "tiny", "base"),
    ("auto", ["tiny"], "tiny", None),
    ("auto", ["tiny", "base"], "base", None),
    ("tiny", ["tiny", "base"], "tiny", None),               # the user chose tiny
    ("auto", ["tiny", "small"], "tiny", None),              # small is too slow here
])
def test_listening_again_for_reminders(setting, installed, used, expected):
    assert engine.reminder_model(setting, installed, {}, used) == expected


def test_prompt():
    prompt = engine.build_prompt(["gempa terbaru", "jam berapa", "Jam berapa", "cuaca",
                                  "x" * 80, "", "Ucapkan gempa terkini dari BMKG"])
    assert prompt == "cuaca, jam berapa, gempa terbaru, Ucapkan gempa terkini dari BMKG."
    assert len(engine.build_prompt(["kata %d" % i for i in range(500)])) <= \
        engine.MAX_PROMPT_CHARS + 1
    assert engine.build_prompt([]) == ""


@pytest.mark.parametrize("heard, expected", [
    (" Gempa terbaru.", "Gempa terbaru."), ("[BLANK_AUDIO]", ""),
    ("(musik) Cuaca hari ini", "Cuaca hari ini"), ("*batuk* ya", "ya"), (None, ""),
])
def test_clean_text(heard, expected):
    assert engine.clean_text(heard) == expected


def test_language_and_threads():
    assert engine.whisper_language("id") == "id"
    assert engine.whisper_language("en-US") == "en"
    assert engine.whisper_language("xx") == "auto"
    assert [engine.threads(n) for n in (1, 2, 4, 8)] == [1, 2, 4, 4]


# ------------------------------------------------------------
# whisper-server, faked
# ------------------------------------------------------------

class FakeProcess:
    def __init__(self, exits_with=None):
        self.returncode = exits_with
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 1

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class FakePopen:
    def __init__(self, exits_with=None):
        self.calls = []
        self.processes = []
        self.exits_with = exits_with

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        process = FakeProcess(self.exits_with)
        self.processes.append(process)
        return process


@pytest.fixture
def files(tmp_path):
    exe = tmp_path / "runtime" / "Release" / "whisper-server.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    model = tmp_path / "models" / "ggml-tiny.bin"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"ggml")
    return types.SimpleNamespace(exe=str(exe), model=str(model), log=str(tmp_path / "s.log"))


def make_server(files, popen=None, connect_after=0, post=None, clock=None, model="tiny"):
    attempts = []

    def can_connect(port):
        attempts.append(port)
        return len(attempts) > connect_after

    server = engine.Server(model, files.exe, files.model, language="id",
                           prompt="gempa terbaru, jam berapa.", thread_count=4,
                           log_path=files.log, popen=popen or FakePopen(),
                           can_connect=can_connect, post=post, clock=clock,
                           sleep=lambda s: None)
    server.attempts = attempts
    return server


class TestServer:
    def test_starts_hidden_below_normal_on_localhost(self, files):
        popen = FakePopen()
        server = make_server(files, popen, connect_after=2)
        server.start()
        (command, kwargs), = popen.calls
        assert command[:3] == [files.exe, "-m", files.model]
        assert command[command.index("--host") + 1] == "127.0.0.1"
        assert int(command[command.index("--port") + 1]) == server.port
        assert command[command.index("-t") + 1] == "4"
        assert command[command.index("-l") + 1] == "id"
        assert command[command.index("--prompt") + 1] == "gempa terbaru, jam berapa."
        assert "-nt" not in command            # only flags whisper-server has for sure
        assert kwargs["creationflags"] & engine.CREATE_NO_WINDOW
        assert kwargs["creationflags"] & engine.BELOW_NORMAL_PRIORITY_CLASS
        assert kwargs["cwd"] == os.path.dirname(files.exe)
        assert kwargs["stdin"] is __import__("subprocess").DEVNULL
        assert len(server.attempts) == 3 and server.running
        server.start()                                   # already running: nothing new
        assert len(popen.calls) == 1
        server.stop()
        assert popen.processes[0].terminated and not server.running

    def test_a_server_that_ends_at_once(self, files):
        server = make_server(files, FakePopen(exits_with=3), connect_after=100)
        with pytest.raises(engine.EngineError) as error:
            server.start()
        assert error.value.kind == "start" and not server.running

    def test_a_model_that_takes_too_long_to_load(self, files):
        now = [0.0]

        def clock():
            now[0] += 1.0
            return now[0]

        popen = FakePopen()
        server = make_server(files, popen, connect_after=10 ** 6, clock=clock)
        with pytest.raises(engine.EngineError) as error:
            server.start()
        assert error.value.kind == "timeout" and popen.processes[0].terminated

    def test_missing_files(self, files):
        os.remove(files.model)
        with pytest.raises(engine.EngineError) as error:
            make_server(files).start()
        assert error.value.kind == "missing"

    def test_transcribe(self, files):
        requests = []

        def post(port, fields, wav, timeout):
            requests.append((port, dict(fields), wav, timeout))
            return 200, json.dumps({"text": " Gempa terbaru. [BLANK_AUDIO]"}).encode()

        server = make_server(files, post=post)
        assert server.transcribe(b"RIFF...", prompt="cuaca.", language="en") == \
            "Gempa terbaru."
        port, fields, wav, timeout = requests[0]
        assert port == server.port and wav == b"RIFF..."
        assert fields == {"response_format": "json", "temperature": "0.0", "language": "en",
                          "prompt": "cuaca."}
        assert timeout == engine.REQUEST_TIMEOUT["tiny"]

    @pytest.mark.parametrize("status, body, kind", [
        (503, b"loading", "http"), (500, b"oops", "http"), (200, b"not json", "bad_data"),
        (200, b'{"error": "failed"}', "bad_data"),
    ])
    def test_transcribe_errors(self, files, status, body, kind):
        server = make_server(files, post=lambda *a: (status, body))
        with pytest.raises(engine.EngineError) as error:
            server.transcribe(b"RIFF")
        assert error.value.kind == kind

    def test_the_request_on_the_wire(self, files, monkeypatch):
        sent = {}

        class FakeConnection:
            def __init__(self, host, port, timeout=None):
                sent.update(host=host, port=port, timeout=timeout)

            def request(self, method, path, body=None, headers=None):
                sent.update(method=method, path=path, body=body, headers=headers)

            def getresponse(self):
                return types.SimpleNamespace(status=200, read=lambda: b'{"text": "ya"}')

            def close(self):
                sent["closed"] = True

        monkeypatch.setattr(engine.http.client, "HTTPConnection", FakeConnection)
        server = make_server(files)
        assert server.transcribe(b"RIFFDATA") == "ya"
        assert (sent["host"], sent["method"], sent["path"]) == ("127.0.0.1", "POST",
                                                                "/inference")
        boundary = sent["headers"]["Content-Type"].split("boundary=")[1]
        body = sent["body"]
        assert body.endswith(f"--{boundary}--\r\n".encode())
        assert b'name="file"; filename="speech.wav"' in body and b"RIFFDATA" in body
        assert b'name="response_format"\r\n\r\njson' in body and sent["closed"]

    def test_the_real_job_object_helper_is_safe(self):
        assert engine.tie_to_hariku(types.SimpleNamespace()) is None


class FakeServer:
    def __init__(self, model, clock):
        self.model = model
        self._clock = clock
        self.last_used = clock()
        self.lock = threading.Lock()
        self.started = self.stopped = 0
        self.process = None

    @property
    def running(self):
        return self.process is not None

    def start(self):
        self.started += 1
        self.process = object()

    def transcribe(self, wav, prompt=None, language=None):
        self.start()
        self.last_used = self._clock()
        return f"{self.model}:{language}"

    def stop(self):
        self.stopped += 1
        self.process = None


class TestEngine:
    def make(self):
        now = [100.0]
        servers = {}

        def make_server(model):
            servers[model] = FakeServer(model, lambda: now[0])
            return servers[model]

        return engine.Engine(make_server, clock=lambda: now[0], watch=False), now, servers

    def test_one_server_per_model_kept_running(self):
        eng, now, servers = self.make()
        assert eng.transcribe("tiny", b"w", language="id") == ("tiny:id", 0.0)
        eng.transcribe("tiny", b"w")
        assert list(servers) == ["tiny"] and eng.running_models() == ["tiny"]
        eng.warm_up("base")
        assert servers["base"].started == 1

    def test_idle_servers_stop_after_five_minutes(self):
        eng, now, servers = self.make()
        eng.transcribe("tiny", b"w")
        now[0] += 200
        eng.transcribe("base", b"w")
        now[0] += 120                    # tiny unused for 320 s, base for 120 s
        assert eng.stop_idle() == ["tiny"]
        assert servers["tiny"].stopped == 1 and eng.running_models() == ["base"]
        now[0] += 200
        assert eng.stop_idle() == ["base"] and eng.running_models() == []

    def test_a_busy_server_is_not_stopped(self):
        eng, now, servers = self.make()
        eng.transcribe("tiny", b"w")
        now[0] += 1000
        with servers["tiny"].lock:
            assert eng.stop_idle() == []

    def test_stop_all(self):
        eng, now, servers = self.make()
        eng.transcribe("tiny", b"w")
        eng.shutdown()
        assert servers["tiny"].stopped == 1 and eng.running_models() == []

    def test_the_idle_watch_runs_in_the_background(self):
        now = [0.0]
        made = {}

        def make_server(model):
            made[model] = FakeServer(model, lambda: now[0])
            return made[model]

        eng = engine.Engine(make_server, clock=lambda: now[0], idle_seconds=300,
                            check_seconds=0.01)
        try:
            eng.transcribe("tiny", b"w")
            now[0] += 301
            assert wait_until(lambda: made["tiny"].stopped == 1)
        finally:
            eng.shutdown()


# ------------------------------------------------------------
# The extension: listening, the microphone test, downloads
# ------------------------------------------------------------

@pytest.fixture
def vc(userdata, monkeypatch):
    import core.i18n
    monkeypatch.setattr(core.i18n, "_current_language", "en")
    spec = importlib.util.spec_from_file_location("voice_control_main_under_test",
                                                  os.path.join(VC_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken = []
    monkeypatch.setattr(module, "_say", lambda message, interrupt=True: spoken.append(message))
    module.spoken = spoken
    yield module
    module._engine.shutdown()


def install_models(names):
    root = store.root_dir()
    os.makedirs(store.models_dir(root), exist_ok=True)
    for name in names:
        with open(store.model_path(root, name), "wb") as f:
            f.write(b"ggml")
        store.write_model_marker(root, name, 4, "x")


class FakeRecorder:
    def __init__(self, data, during=None):
        self.data = data
        self.during = during

    def record(self, on_chunk, stop=None, max_seconds=30.0):
        out = bytearray()
        for i, piece in enumerate(chunks(self.data)):
            if stop is not None and stop.is_set():
                break
            if len(out) >= max_seconds * 2 * RATE:
                break
            out += piece
            if self.during is not None:
                self.during(i)
            if on_chunk(piece):
                break
        return bytes(out)


class FakeEngine:
    def __init__(self, answers, error=None):
        self.answers = answers
        self.error = error
        self.calls = []
        self.seconds = []
        self.warmed = []

    def warm_up(self, model):
        self.warmed.append(model)

    def transcribe(self, model, wav, prompt=None, language=None):
        if self.error is not None:
            raise self.error
        with wave.open(io.BytesIO(wav)) as w:
            assert w.getframerate() == 16000
            self.seconds.append(w.getnframes() / 16000.0)
        self.calls.append((model, language, prompt))
        return self.answers[model], {"tiny": 1.5, "base": 4.2, "small": 15.0}[model]


def make_listener(vc, data, answers=None, blocked=None, error=None, during=None):
    log = types.SimpleNamespace(played=[], slept=[], quiet=0, speeds=[], events=[])
    fake_engine = FakeEngine(answers or {"tiny": "Gempa terbaru."}, error)

    def quiet():
        log.quiet += 1

    listener = vc.Listener(make_recorder=lambda: FakeRecorder(data, during),
                           engine_=fake_engine, blocked=lambda: blocked,
                           play=log.played.append, sleep=log.slept.append, quiet_=quiet,
                           tones=lambda name: 0.2,
                           record_speed=lambda model, s: log.speeds.append((model, s)),
                           available=lambda: True)
    log.engine = fake_engine
    return listener, log


def listen(listener, log):
    assert listener.start(lambda kind, value=None: log.events.append((kind, value))) is True
    assert wait_until(lambda: not listener.busy())
    return log.events


class TestListening:
    def test_a_command(self, vc):
        install_models(["tiny"])
        listener, log = make_listener(vc, speech_clip())
        events = listen(listener, log)
        assert events == [("listening", None), ("recognising", None),
                          ("text", "Gempa terbaru.")]
        assert log.played == ["listen.wav", "listen_end.wav"]
        assert log.slept == [pytest.approx(0.35)]          # the tone, then 150 ms
        assert log.quiet == 2                              # before the tone, and after it
        assert log.engine.warmed == ["tiny"]
        assert [(m, lang) for m, lang, _p in log.engine.calls] == [("tiny", "en")]
        assert log.speeds == [("tiny", 1.5)]

    def test_a_reminder_is_heard_again_with_base(self, vc):
        install_models(["tiny", "base"])
        listener, log = make_listener(vc, speech_clip(), answers={
            "tiny": "ingat kan aku minum obat besok jam 8",
            "base": "Ingatkan aku minum obat besok jam 8."})
        events = listen(listener, log)
        assert events[-1] == ("text", "Ingatkan aku minum obat besok jam 8.")
        assert [m for m, _l, _p in log.engine.calls] == ["tiny", "base"]
        assert log.speeds == [("tiny", 1.5), ("base", 4.2)]

    def test_a_command_is_not_heard_again(self, vc):
        install_models(["tiny", "base"])
        listener, log = make_listener(vc, speech_clip(), answers={"tiny": "Gempa terbaru."})
        listen(listener, log)
        assert [m for m, _l, _p in log.engine.calls] == ["tiny"]

    def test_a_chosen_model_is_used_alone(self, vc):
        install_models(["tiny", "base"])
        vc.save_settings("tiny", True, 1000)
        listener, log = make_listener(vc, speech_clip(), answers={
            "tiny": "ingatkan aku minum obat besok jam 8"})
        listen(listener, log)
        assert [m for m, _l, _p in log.engine.calls] == ["tiny"]

    def test_without_base_the_tiny_text_is_used(self, vc):
        install_models(["tiny"])
        listener, log = make_listener(vc, speech_clip(), answers={
            "tiny": "ingatkan aku minum obat besok jam 8"})
        assert listen(listener, log)[-1] == ("text", "ingatkan aku minum obat besok jam 8")

    def test_nothing_said(self, vc):
        install_models(["tiny"])
        listener, log = make_listener(vc, noise(6000))
        events = listen(listener, log)
        assert events == [("listening", None), ("error", text._("err_no_speech"))]
        assert log.engine.calls == [] and log.played[-1] == "listen_end.wav"

    def test_only_zeros_means_a_blocked_or_muted_microphone(self, vc):
        install_models(["tiny"])
        listener, log = make_listener(vc, zeros(6000))
        assert listen(listener, log)[-1] == ("error", text.mic_error("silent"))

    def test_the_privacy_switch_is_explained(self, vc):
        install_models(["tiny"])
        listener, log = make_listener(vc, speech_clip(), blocked="blocked_desktop")
        events = listen(listener, log)
        assert events == [("error", text.mic_error("blocked_desktop"))]
        assert "Let desktop apps access your microphone" in events[0][1]
        assert "Privacy, Microphone" in events[0][1]
        assert log.played == []                    # nothing played, nothing recorded

    def test_cancelled_while_recording(self, vc):
        install_models(["tiny"])
        holder = {}
        listener, log = make_listener(
            vc, tone(3000), during=lambda i: i == 2 and holder["listener"].stop(discard=True))
        holder["listener"] = listener
        events = listen(listener, log)
        assert events == [("listening", None), ("stopped", None)]
        assert log.engine.calls == []

    def test_stopped_by_the_hotkey_recognises_what_was_heard(self, vc):
        install_models(["tiny"])
        holder = {}
        clip = noise(400) + tone(4000)
        listener, log = make_listener(
            vc, clip, during=lambda i: i == 12 and holder["listener"].stop())
        holder["listener"] = listener
        assert listen(listener, log)[-1] == ("text", "Gempa terbaru.")

    def test_recognition_errors(self, vc):
        install_models(["tiny"])
        listener, log = make_listener(vc, speech_clip(),
                                      error=engine.EngineError("timeout", "slow"))
        assert listen(listener, log)[-1] == ("error", text._("err_timeout"))

    def test_one_at_a_time_and_only_when_ready(self, vc):
        install_models(["tiny"])
        release = threading.Event()
        listener, log = make_listener(vc, speech_clip(), during=lambda i: release.wait(3))
        assert listener.start(lambda kind, value=None: log.events.append((kind, value)))
        refused = []
        assert listener.start(lambda kind, value=None: refused.append((kind, value))) is False
        assert refused == [("error", text._("err_busy"))]
        release.set()
        assert wait_until(lambda: not listener.busy())
        listener._available = lambda: False
        assert listener.start(lambda kind, value=None: refused.append((kind, value))) is False
        assert refused[-1] == ("error", text._("err_not_ready"))

    def test_microphone_test(self, vc):
        listener, log = make_listener(vc, speech_clip(tail_ms=2000))
        result = vc.test_microphone(listener, seconds=3.0)
        assert result["speech"] is True and -40 < result["level"] < -5
        assert result["seconds"] == pytest.approx(3.0, abs=0.11)
        assert log.played == ["listen.wav", "listen_end.wav"]
        listener, log = make_listener(vc, noise(3000))
        assert vc.test_microphone(listener, seconds=3.0)["speech"] is False
        listener, log = make_listener(vc, zeros(3000))
        with pytest.raises(audio.MicrophoneError):
            vc.test_microphone(listener, seconds=3.0)

    def test_the_microphone_test_measures_a_sentence(self, vc):
        assert vc.MIC_TEST_SECONDS == 5.0
        clip = room(600, 20) + quiet_sentence() + room(3000, 20, seed=3)
        listener, log = make_listener(vc, clip)
        result = vc.test_microphone(listener)
        assert result["seconds"] == pytest.approx(5.0, abs=0.11)
        assert result["speech"] is True
        assert 15 < result["room"] < 25 and 190 < result["voice"] < 260
        assert result["calibration"] == audio.Calibration("very_high", None, result["room"],
                                                          result["voice"])
        assert log.played == ["listen.wav", "listen_end.wav"]
        assert store.load_settings()["sensitivity"] == "normal"      # the page saves it, not the test

    @pytest.mark.parametrize("clip, sensitivity, problem", [
        (lambda: room(600, 10) + voice(1500, 60) + room(2900, 10, seed=2), "very_high", "too_quiet"),
        (lambda: room(600, 400) + voice(1500, 1000) + room(2900, 400, seed=2), "low", "too_noisy"),
        (lambda: room(5000, 1500), None, "no_speech"),
    ])
    def test_the_microphone_test_explains_problems(self, vc, clip, sensitivity, problem):
        listener, log = make_listener(vc, clip())
        calibration = vc.test_microphone(listener)["calibration"]
        assert (calibration.sensitivity, calibration.problem) == (sensitivity, problem)

    def test_a_quiet_voice_is_heard_at_normal_but_not_at_low(self, vc):
        install_models(["tiny"])
        clip = room(420, 20) + quiet_sentence() + room(4000, 20, seed=3)
        listener, log = make_listener(vc, clip)
        assert listen(listener, log)[-1] == ("text", "Gempa terbaru.")
        vc.save_settings("auto", True, 1000, "low")
        listener, log = make_listener(vc, clip)
        assert listen(listener, log)[-1] == ("error", text._("err_no_speech"))
        assert log.engine.calls == []
        assert "sensitivity" in text._("err_no_speech")

    def test_too_noisy_to_hear_the_end(self, vc):
        # Twelve seconds of a roar: recognised anyway; nothing came of it, so
        # Hariku says it was too noisy.
        install_models(["tiny"])
        listener, log = make_listener(vc, room(150, 20) + hum(14000, 3000), answers={"tiny": " "})
        events = listen(listener, log)
        message = text._("err_too_noisy", seconds=12)
        assert events == [("listening", None), ("recognising", None), ("error", message)]
        assert message.startswith("It was too noisy to hear when you stopped speaking")
        assert "12 seconds" in message and "Enter" in message
        assert len(log.engine.calls) == 1 and log.played[-1] == "listen_end.wav"

    def test_a_command_in_a_noisy_room_is_still_recognised(self, vc):
        # The voice, then a hum close behind it to the cap: only the voice goes to whisper.
        install_models(["tiny"])
        clip = room(420, 20) + voice(900, 3000) + hum(13000, 900)
        listener, log = make_listener(vc, clip)
        assert listen(listener, log)[-1] == ("text", "Gempa terbaru.")
        assert log.engine.seconds and log.engine.seconds[0] < 2.0

    def test_birds_after_a_command_end_the_recording(self, vc):
        install_models(["tiny"])
        clip = room(420, 20) + voice(900, 3000) + chirps(10000, amplitude=4000)
        listener, log = make_listener(vc, clip)
        assert listen(listener, log) == [("listening", None), ("recognising", None),
                                         ("text", "Gempa terbaru.")]
        assert log.engine.seconds[0] < 2.0

    def test_twelve_seconds_of_speech_with_pauses_is_still_recognised(self, vc):
        install_models(["tiny"])
        clip = room(300, 20) + b"".join(voice(600, 3000) + room(300, 20, seed=i)
                                        for i in range(16))
        listener, log = make_listener(vc, clip)
        assert listen(listener, log)[-1] == ("text", "Gempa terbaru.")

    def test_saving_the_sensitivity(self, vc):
        vc.save_settings("auto", True, 1000, "high")
        assert store.load_settings()["sensitivity"] == "high"
        assert vc.get_settings()["sensitivity"] == "high"
        vc.save_settings("base", False, 800)            # without it, it stays
        assert store.load_settings()["sensitivity"] == "high"
        vc.controller.save_settings("auto", True, 1000, "very_high")
        assert vc.get_settings()["sensitivity"] == "very_high"

    def test_the_tone_length_is_read_from_the_sound(self, vc):
        assert vc.tone_seconds("listen.wav") == pytest.approx(0.215, abs=0.01)
        assert vc.tone_seconds("nothing.wav") == vc.DEFAULT_TONE_SECONDS

    def test_the_prompt_has_the_commands(self, vc, monkeypatch):
        import core.commands
        monkeypatch.setattr(core.commands, "vocabulary",
                            lambda actions=None: ["gempa terbaru", "jam berapa"])
        prompt = vc.prompt()
        assert "gempa terbaru" in prompt and "jam berapa" in prompt and "remind me" in prompt


class TestDownloads:
    def test_a_model_brings_the_program(self, vc):
        done = []

        def install_runtime(root, progress=None, cancelled=None):
            progress(dl.RUNTIME_SIZE)
            done.append("runtime")

        def install_model(name, root, progress=None, cancelled=None):
            progress(dl.MODELS[name]["size"] // 2)
            progress(dl.MODELS[name]["size"])
            done.append(name)

        downloads = vc.Downloads(install_runtime, install_model)
        events = []
        downloads.add_listener(lambda event, job, value: events.append((event, value)))
        assert downloads.start("tiny")
        assert wait_until(lambda: downloads.current() is None)
        assert done == ["runtime", "tiny"]
        assert events[-1] == ("finished", None)
        assert vc.spoken[0].startswith("Downloading Tiny speech model")
        assert "86.3 MB" in vc.spoken[0]                   # 77.7 + 8.6
        assert "100 percent" in vc.spoken and vc.spoken[-1].endswith("downloaded.")

    def test_cancel(self, vc):
        def install_model(name, root, progress=None, cancelled=None):
            while not cancelled():
                time.sleep(0.005)
            raise dl.Cancelled()

        downloads = vc.Downloads(lambda *a, **k: None, install_model)
        assert downloads.start("base")
        assert downloads.start("small") is False           # one at a time
        assert downloads.cancel()
        assert wait_until(lambda: downloads.current() is None)
        assert vc.spoken[-1] == "Download cancelled."

    def test_failures_are_explained(self, vc):
        def install_runtime(root, progress=None, cancelled=None):
            raise dl.DownloadError("verify", "whisper-bin-x64.zip")

        downloads = vc.Downloads(install_runtime, None)
        downloads.start("runtime")
        assert wait_until(lambda: downloads.current() is None)
        assert vc.spoken[-1] == "The download failed. " + text._("err_verify")

    def test_remove_stops_the_server_first(self, vc, monkeypatch):
        install_models(["tiny"])
        stopped = []
        monkeypatch.setattr(vc._engine, "stop_all", lambda: stopped.append(True))
        assert vc.controller.installed()["tiny"] is True
        assert vc.controller.remove("tiny") is True
        assert stopped == [True] and vc.controller.installed()["tiny"] is False


class TestRegistration:
    def test_register_and_teardown(self, vc):
        import core.commands
        import core.preferences
        from core.events import EventBus
        before = {k: list(v) for k, v in core.preferences.get_all_panels().items()}
        try:
            vc.register(EventBus())
            listener = core.commands.get_listener()
            assert listener is not None and listener.name == "Voice Control"
            assert listener.is_available() is False          # nothing downloaded
            assert listener.listen_on_open() is True          # the default
            vc.teardown()
            assert core.commands.get_listener() is None
        finally:
            core.preferences._panels.clear()
            core.preferences._panels.update(before)
            core.commands.unregister_listener()


# ------------------------------------------------------------
# The page's logic, without windows
# ------------------------------------------------------------

class FakeChoice:
    def __init__(self, selection):
        self.selection = selection
        self.selected = []

    def GetSelection(self):
        return self.selection

    def SetSelection(self, index):
        self.selected.append(index)
        self.selection = index

    def SetFocus(self):
        raise AssertionError("focus moved")


class FakeText:
    value = None

    def ChangeValue(self, value):
        self.value = value

    def SetFocus(self):
        raise AssertionError("focus moved")


@pytest.fixture
def page(vc, monkeypatch):
    """The page's methods on a stand-in without windows."""
    import voice_control_ui as vui
    panel_class = vui.VoiceControlPanel
    said = []
    monkeypatch.setattr(vui, "_announce", lambda message, interrupt=True, delay=0:
                        said.append(message))
    fake = types.SimpleNamespace(
        _sensitivities=[name for name, _label in text.sensitivity_choices()], _testing=True,
        choice_sensitivity=FakeChoice(1), txt_test=FakeText(), dirty=[], said=said,
        _model_keys=[name for name, _label in text.model_choices()], choice_model=FakeChoice(0),
        chk_listen=types.SimpleNamespace(GetValue=lambda: True), choice_silence=FakeChoice(2),
        _silences=list(store.SILENCE_CHOICES), saved=[],
        chk_wake=types.SimpleNamespace(GetValue=lambda: False),
        txt_phrase=types.SimpleNamespace(GetValue=lambda: "  Hey   Aruna "),
        _wake_sensitivities=[name for name, _label in text.wake_sensitivity_choices()],
        choice_wake_sensitivity=FakeChoice(1),
        chk_wake_quiet=types.SimpleNamespace(GetValue=lambda: False), _wake_was_on=False,
        wake_installed=False)
    fake._usable = lambda: True
    fake._mark_dirty = lambda: fake.dirty.append(True)
    for name in ("_sensitivity_index", "select_sensitivity", "_test_done", "get_settings",
                 "ApplyChanges", "_wake_sensitivity", "_wake_sensitivity_index"):
        setattr(fake, name, getattr(panel_class, name).__get__(fake))
    fake._c = types.SimpleNamespace(save_settings=lambda *values: fake.saved.append(values),
                                    installed=lambda: {"wake": fake.wake_installed})
    return fake


class TestPage:
    def test_the_sensitivity_choice(self, vc):
        assert text.sensitivity_choices() == [("low", "Low"), ("normal", "Normal"),
                                              ("high", "High"), ("very_high", "Very high")]

    def test_calibration_messages(self, vc):
        done = text.calibration_message(audio.Calibration("high", None, 26.0, 413.0))
        assert done == "Your voice: -38 dB, the room: -62 dB. Sensitivity set to High."
        quiet = text.calibration_message(audio.Calibration("very_high", "too_quiet", 20.0, 60.0))
        assert quiet.startswith("Your voice: -55 dB, the room: -64 dB. Sensitivity set to "
                                "Very high, but your voice is still too quiet.")
        noisy = text.calibration_message(audio.Calibration("low", "too_noisy", 500.0, 1200.0))
        assert noisy.startswith("Your voice: -29 dB, the room: -36 dB. Sensitivity set to Low, "
                                "but the room is too noisy for your voice.")
        for message in (quiet, noisy):
            assert "Windows Settings, System, Sound, Input, Device properties" in message
            assert "headset microphone" in message
        nobody = text.calibration_message(audio.Calibration(None, "no_speech", 20.0, None))
        assert nobody.startswith("I didn't hear you speak. The room: -64 dB.")

    def test_calibration_messages_in_indonesian(self, vc, monkeypatch):
        import core.i18n
        monkeypatch.setattr(core.i18n, "_current_language", "id")
        done = text.calibration_message(audio.Calibration("high", None, 26.0, 413.0))
        assert done == "Suaramu -38 dB, ruangan -62 dB. Kepekaan diatur ke Tinggi."
        quiet = text.calibration_message(audio.Calibration("very_high", "too_quiet", 20.0, 60.0))
        assert "Sangat tinggi" in quiet and "terlalu pelan" in quiet and "headset" in quiet
        noisy = text.calibration_message(audio.Calibration("low", "too_noisy", 500.0, 1200.0))
        assert "terlalu bising" in noisy and "Properti perangkat" in noisy
        assert "kamu" in text._("err_too_noisy", seconds=12)

    def test_mic_test_outcome(self, vc):
        heard = {"calibration": audio.Calibration("very_high", None, 20.0, 200.0)}
        message, sensitivity = text.mic_test_outcome(heard, None)
        assert sensitivity == "very_high" and message.endswith("Sensitivity set to Very high.")
        nobody = {"calibration": audio.Calibration(None, "no_speech", 20.0, None)}
        assert text.mic_test_outcome(nobody, None)[1] is None
        assert text.mic_test_outcome(None, audio.MicrophoneError("blocked_desktop")) == (
            text.mic_error("blocked_desktop"), None)
        assert text.mic_test_outcome(None, RuntimeError("busy")) == (text._("mic_test_busy"),
                                                                     None)

    def test_the_test_selects_the_sensitivity_without_saving_it(self, page):
        result = {"calibration": audio.Calibration("high", None, 26.0, 413.0)}
        page._test_done(result, None)
        assert page.choice_sensitivity.selected == [2] and page.dirty == [True]
        assert page.txt_test.value == page.said[-1] == (
            "Your voice: -38 dB, the room: -62 dB. Sensitivity set to High.")
        assert page._testing is False
        assert store.load_settings()["sensitivity"] == "normal"     # OK or Apply saves it
        page._test_done(result, None)                                 # the same again
        assert page.choice_sensitivity.selected == [2] and page.dirty == [True]
        page._test_done({"calibration": audio.Calibration(None, "no_speech", 20.0, None)}, None)
        assert page.choice_sensitivity.selected == [2]                # nobody spoke: kept
        page._test_done(None, audio.MicrophoneError("busy"))
        assert page.txt_test.value == text.mic_error("busy")
        assert page.choice_sensitivity.selection == 2

    def test_the_page_saves_the_sensitivity(self, page):
        page.choice_sensitivity.selection = 3
        wake_values = {"enabled": False, "phrase": "Hey Aruna", "sensitivity": "normal",
                       "quiet_hours": False}
        assert page.get_settings() == {"model": "auto", "listen_on_open": True,
                                       "silence_ms": 1000, "sensitivity": "very_high",
                                       "wake": wake_values}
        page.ApplyChanges()
        assert page.saved == [("auto", True, 1000, "very_high", wake_values)]
        page.choice_sensitivity.selection = -1
        assert page.get_settings()["sensitivity"] == "normal"
        assert page._sensitivity_index("unknown") == 1


def test_manifest():
    with open(os.path.join(VC_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["id"] == "voice_control" and manifest["version"] == "1.1"
    assert manifest["minimum_core_version"] == "2.7" and manifest["main"] == "main.py"


def test_messages_exist_in_both_languages():
    import ast
    used = set()
    for name in os.listdir(VC_DIR):
        if name.endswith(".py"):
            with open(os.path.join(VC_DIR, name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "_" and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    used.add(node.args[0].value)
    languages = {}
    for code in ("en", "id"):
        with open(os.path.join(VC_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
            languages[code] = json.load(f)["messages"]
        missing = sorted(used - set(languages[code]))
        assert not missing, f"locales/{code}.json lacks {missing}"
    assert set(languages["en"]) == set(languages["id"])
    assert "kamu" in languages["id"]["confirm_license"]
    assert "Let desktop apps access your microphone" in languages["en"]["mic_blocked_desktop"]


def test_the_page_creates_each_label_before_its_control():
    import ast
    with open(os.path.join(VC_DIR, "voice_control_ui.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "_labeled"]
    assert len(calls) == 11      # and the wake phrase, its advice, its sensitivity, its test
    assert all(isinstance(call.args[3], ast.Lambda) for call in calls)
    controls = {"Choice", "ComboBox", "ListCtrl", "ListBox", "SpinCtrl", "Slider", "TextCtrl",
                "Gauge"}
    made = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr in controls]
    inside = {id(n) for call in calls for n in ast.walk(call.args[3])}
    assert made and all(id(node) in inside for node in made)
