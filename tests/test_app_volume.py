# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Core 2.13: Hariku's volume is its own audio session's master volume
(core/app_volume.py), which NVDA's sound split no longer resets, instead of
the channel volumes waveOutSetVolume set.
"""
import os

import pytest

import core.app_volume
import core.sounds as sounds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def volume_calls(_no_real_app_volume, tmp_data_dir, monkeypatch):
    monkeypatch.setitem(sounds._applied, "volume", None)
    monkeypatch.setitem(sounds._applied, "at", 0.0)
    _no_real_app_volume.clear()
    return _no_real_app_volume


def test_volume_keys_set_hariku_s_own_volume(volume_calls, monkeypatch):
    spoken = []
    monkeypatch.setattr("core.speech.speak", lambda text, **kw: spoken.append(text))
    sounds.set_global_volume(60)
    sounds.volume_up()
    sounds.volume_down()
    sounds.volume_down()
    assert volume_calls == [60, 65, 60, 55]
    assert sounds.get_global_volume() == 55
    assert len(spoken) == 3


def test_the_old_channel_volume_api_is_not_used():
    with open(os.path.join(ROOT, "core", "sounds.py"), encoding="utf-8") as f:
        assert "waveOutSetVolume(" not in f.read()


def test_startup_resets_the_old_channel_volume_once(volume_calls):
    config = {"volume": 40}
    assert sounds.init_volume(config) is True
    assert volume_calls == ["reset", 40]
    assert config[sounds.CHANNEL_RESET_KEY] is True
    volume_calls.clear()
    assert sounds.init_volume(config) is False
    assert volume_calls == [40]


def test_a_sound_applies_the_volume_again_only_now_and_then(volume_calls, monkeypatch, tmp_path):
    import ctypes
    monkeypatch.setattr(ctypes.windll.winmm, "mciSendStringW", lambda *a: 0)
    clock = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])
    wav = tmp_path / "move.wav"
    wav.write_bytes(b"RIFF")
    sounds.play_sound(str(wav))
    sounds.play_sound(str(wav))
    assert volume_calls == [100]            # nothing saved: full volume, once
    clock[0] += sounds.REAPPLY_SECONDS
    sounds.play_sound(str(wav))
    assert volume_calls == [100, 100]       # again, in case something changed it
    sounds.set_global_volume(30)
    sounds.play_sound(str(wav))
    assert volume_calls == [100, 100, 30]


def test_set_volume_never_raises_when_windows_audio_fails(monkeypatch):
    monkeypatch.undo()                      # the real one, with a failing COM
    def broken():
        raise OSError("no audio service")
    monkeypatch.setattr(core.app_volume, "_simple_volumes", broken)
    assert core.app_volume.set_volume(50) == 0
    assert core.app_volume.get_volume() is None


def test_the_level_is_clamped(monkeypatch):
    monkeypatch.undo()
    levels = []

    class FakeVolume:
        def call(self, index, argtypes, *args, what=""):
            if index == core.app_volume.SIMPLE_VOLUME_SET_MASTER_VOLUME:
                levels.append(round(args[0].value, 2))
            return 0

        def release(self):
            pass

    monkeypatch.setattr(core.app_volume, "_simple_volumes", lambda: [FakeVolume(), FakeVolume()])
    assert core.app_volume.set_volume(150) == 2
    assert core.app_volume.set_volume(-5) == 2
    assert core.app_volume.set_volume(35) == 2
    assert levels == [1.0, 1.0, 0.0, 0.0, 0.35, 0.35]


# ------------------------------------------------------------
# Faster startup: the trusted list and the file hashes are kept
# ------------------------------------------------------------

@pytest.fixture
def trust(tmp_data_dir, monkeypatch):
    import core.extension_manager as em
    monkeypatch.setattr(em, "_trusted_hash_cache", None)
    monkeypatch.setattr(em, "_file_hashes", None)
    return em


def test_a_file_is_hashed_again_only_when_it_changes(trust, tmp_path, monkeypatch):
    hashed = []
    real = trust._sha256_file
    monkeypatch.setattr(trust, "_sha256_file", lambda p: hashed.append(p) or real(p))
    hrk = tmp_path / "community.hrk"
    hrk.write_bytes(b"one")
    first = trust._file_hash(str(hrk))
    assert trust._file_hash(str(hrk)) == first and len(hashed) == 1
    trust._save_trust_cache()
    monkeypatch.setattr(trust, "_file_hashes", None)       # the next start
    assert trust._file_hash(str(hrk)) == first and len(hashed) == 1
    hrk.write_bytes(b"two!")
    assert trust._file_hash(str(hrk)) != first and len(hashed) == 2


def test_startup_uses_the_saved_list_and_refreshes_it_in_the_background(trust, monkeypatch):
    threads = []
    monkeypatch.setattr(trust.threading, "Thread",
                        lambda target, **kw: type("T", (), {"start": lambda self: threads.append(target)})())
    monkeypatch.setattr(trust, "_download_trusted_hashes", lambda: {"aa", "bb"})
    assert trust._startup_trusted_hashes() == {"aa", "bb"}  # nothing saved: downloaded now
    assert threads == []
    monkeypatch.setattr(trust, "_trusted_hash_cache", None)
    def offline():
        raise AssertionError("startup waited for the network")
    monkeypatch.setattr(trust, "_download_trusted_hashes", offline)
    assert trust._startup_trusted_hashes() == {"aa", "bb"}  # the saved copy
    assert threads == [trust._refresh_trusted_hashes]


def test_the_background_refresh_saves_the_new_list(trust, monkeypatch):
    monkeypatch.setattr(trust, "TRUST_REFRESH_DELAY_SECONDS", 0)
    monkeypatch.setattr(trust, "_trusted_hash_cache", {"aa"})
    monkeypatch.setattr(trust, "_download_trusted_hashes", lambda: {"aa", "cc"})
    trust._refresh_trusted_hashes()
    assert trust._trusted_hash_cache == {"aa", "cc"}
    assert sorted(trust._load_trust_cache()["trusted"]) == ["aa", "cc"]
