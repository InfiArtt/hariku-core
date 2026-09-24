# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The sound theme override in core.sounds: play_internal_sound() prefers the
# theme's copy of a sound, falls back to the built-in one, and never leaves the
# theme folder. Playback itself is mocked.

import os

import pytest

import core.sounds as sounds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILTIN = os.path.join(ROOT, "sounds")


@pytest.fixture
def played(monkeypatch):
    calls = []
    monkeypatch.setattr(sounds, "play_sound", lambda path: calls.append(path) or True)
    sounds.set_theme_dir(None)
    yield calls
    sounds.set_theme_dir(None)


@pytest.fixture
def theme(tmp_path):
    folder = tmp_path / "themes" / "Ocean"
    folder.mkdir(parents=True)
    (folder / "confirm.wav").write_bytes(b"theme confirm")
    return folder


def test_builtin_sounds_dir_is_the_app_sounds_folder():
    assert os.path.normcase(sounds.get_builtin_sounds_dir()) == os.path.normcase(BUILTIN)


def test_without_a_theme_the_builtin_path_is_played_unchanged(played):
    assert sounds.get_theme_dir() is None
    assert sounds.play_internal_sound("move.wav") is True
    assert played == [os.path.join(BUILTIN, "move.wav")]


def test_theme_copy_overrides_the_builtin_sound(played, theme):
    sounds.set_theme_dir(str(theme))
    assert sounds.get_theme_dir() == str(theme)
    sounds.play_internal_sound("confirm.wav")
    assert played == [os.path.join(str(theme), "confirm.wav")]


def test_missing_theme_sound_falls_back_to_builtin(played, theme):
    sounds.set_theme_dir(str(theme))
    sounds.play_internal_sound("move.wav")
    assert played == [os.path.join(BUILTIN, "move.wav")]


def test_missing_theme_folder_falls_back_to_builtin(played, tmp_path):
    sounds.set_theme_dir(str(tmp_path / "gone"))
    sounds.play_internal_sound("confirm.wav")
    assert played == [os.path.join(BUILTIN, "confirm.wav")]


def test_reset_returns_to_builtin(played, theme):
    sounds.set_theme_dir(str(theme))
    sounds.set_theme_dir(None)
    assert sounds.get_theme_dir() is None
    sounds.play_internal_sound("confirm.wav")
    assert played == [os.path.join(BUILTIN, "confirm.wav")]


def test_empty_path_means_no_theme(played):
    sounds.set_theme_dir("")
    assert sounds.get_theme_dir() is None


def test_relative_theme_dir_is_made_absolute(played, theme, monkeypatch):
    monkeypatch.chdir(theme.parent)
    sounds.set_theme_dir("Ocean")
    assert sounds.get_theme_dir() == str(theme)


def test_play_result_is_passed_through(monkeypatch, theme):
    monkeypatch.setattr(sounds, "play_sound", lambda path: False)
    sounds.set_theme_dir(str(theme))
    try:
        assert sounds.play_internal_sound("confirm.wav") is False
    finally:
        sounds.set_theme_dir(None)


@pytest.mark.parametrize("name", [
    "../outside.wav", "..\\outside.wav", "sub/confirm.wav", "sub\\confirm.wav",
    "..", "", " ", "confirm.wav:stream", "C:outside.wav", "/outside.wav", "\\outside.wav",
])
def test_names_that_are_not_plain_never_use_the_theme(played, theme, name):
    # Plant files the traversal would reach; none may be played from the theme.
    (theme.parent / "outside.wav").write_bytes(b"outside")
    (theme / "sub").mkdir(exist_ok=True)
    (theme / "sub" / "confirm.wav").write_bytes(b"nested")
    sounds.set_theme_dir(str(theme))
    sounds.play_internal_sound(name)
    assert len(played) == 1
    # Exactly what the core played before themes existed.
    assert played[0] == os.path.join(BUILTIN, name)
    assert not os.path.normcase(os.path.abspath(played[0])).startswith(
        os.path.normcase(str(theme.parent)))


def test_a_folder_named_like_a_sound_is_not_played(played, theme):
    (theme / "move.wav").mkdir()
    sounds.set_theme_dir(str(theme))
    sounds.play_internal_sound("move.wav")
    assert played == [os.path.join(BUILTIN, "move.wav")]


class _FakeMci:
    def __init__(self, result=0):
        self.commands = []
        self.result = result

    def __call__(self, command, *args):
        self.commands.append(command)
        return self.result


@pytest.fixture
def mci(monkeypatch):
    import ctypes
    fake = _FakeMci()
    monkeypatch.setattr(ctypes.windll.winmm, "mciSendStringW", fake)
    monkeypatch.setattr(ctypes.windll.winmm, "waveOutSetVolume", lambda *a: 0)
    monkeypatch.setattr(sounds, "get_global_volume", lambda: 100)
    return fake


def test_stop_sound_closes_the_alias_play_sound_uses(mci, tmp_path):
    wav = tmp_path / "my sound.wav"
    wav.write_bytes(b"RIFF")
    assert sounds.play_sound(str(wav)) is True
    assert mci.commands == ["close mysoundwav", f'open "{wav}" type waveaudio alias mysoundwav',
                            "play mysoundwav"]
    mci.commands.clear()
    assert sounds.stop_sound(str(wav)) is True
    assert mci.commands == ["close mysoundwav"]


def test_stop_sound_reports_nothing_open(mci):
    mci.result = 263  # MCIERR_INVALID_DEVICE_NAME
    assert sounds.stop_sound("confirm.wav") is False
    assert mci.commands == ["close confirmwav"]


def test_a_link_leading_out_of_the_theme_is_ignored(played, theme):
    outside = theme.parent / "secret.wav"
    outside.write_bytes(b"secret")
    link = theme / "move.wav"
    try:
        os.symlink(str(outside), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("creating symbolic links is not allowed here")
    sounds.set_theme_dir(str(theme))
    sounds.play_internal_sound("move.wav")
    assert played == [os.path.join(BUILTIN, "move.wav")]


# --- The remembered theme (core 2.7): the start sound of the user's theme -------------

@pytest.fixture
def themes(tmp_path, tmp_data_dir, monkeypatch, played):
    import core.api
    monkeypatch.setattr(core.api, "USER_DATA_DIR", str(tmp_path / "Hariku2"))
    root = tmp_path / "Hariku2" / "sound_themes"
    (root / "Cockpit").mkdir(parents=True)
    (root / "Cockpit" / "start.wav").write_bytes(b"cockpit start")
    return root


def test_remember_and_load(themes, played):
    import core.api
    cockpit = str(themes / "Cockpit")
    sounds.set_theme_dir(cockpit, remember=True)
    assert core.api.load_data("Core")["sound_theme_dir"] == cockpit
    sounds.set_theme_dir(None)                       # an extension unloading
    assert core.api.load_data("Core")["sound_theme_dir"] == cockpit
    assert sounds.load_remembered_theme() == cockpit
    assert sounds.get_theme_dir() == cockpit
    sounds.play_internal_sound("start.wav")
    assert played[-1] == os.path.join(cockpit, "start.wav")
    sounds.set_theme_dir(None, remember=True)        # the user picked the built-in sounds
    assert "sound_theme_dir" not in core.api.load_data("Core")
    sounds.set_theme_dir(None)
    assert sounds.load_remembered_theme() is None and sounds.get_theme_dir() is None


def test_only_folders_inside_the_themes_folder_are_loaded(themes, tmp_path, played):
    import core.api
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    work = themes / ".work-123"
    work.mkdir()
    for path in (str(elsewhere), str(themes), str(themes / "Gone"), str(work), "", 42):
        core.api.save_data("Core", {"sound_theme_dir": path})
        assert sounds.load_remembered_theme() is None, path
        assert sounds.get_theme_dir() is None
    core.api.save_data("Core", {"sound_theme_dir": str(themes / "Cockpit" / ".." / "Cockpit")})
    assert sounds.load_remembered_theme() is not None


def test_reminder_sound_is_themeable(tmp_path, monkeypatch):
    import core.sounds as sounds
    played = []
    monkeypatch.setattr(sounds, "play_sound", played.append)
    monkeypatch.setenv("WINDIR", r"C:\Windows")
    old = sounds.get_theme_dir()
    try:
        sounds.set_theme_dir(None)
        sounds.play_reminder_sound()
        (tmp_path / "reminder.wav").write_bytes(b"RIFF")
        sounds.set_theme_dir(str(tmp_path))
        sounds.play_reminder_sound()
    finally:
        sounds.set_theme_dir(old)
    assert played == [r"C:\Windows\Media\Windows Notify Calendar.wav",
                      str(tmp_path / "reminder.wav")]
    assert sounds.default_sound_path("info.wav") ==         __import__("os").path.join(sounds.get_builtin_sounds_dir(), "info.wav")
