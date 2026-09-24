# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Sound Themes storage (sound_themes_store.py) against temporary folders: theme
# rules, sound replacement, WAV checks, ZIP and Hariku 1 import, export,
# cycling and the saved active theme. Playback is mocked.

import importlib.util
import io
import json
import os
import re
import sys
import wave
import zipfile

import pytest

import core.api
import core.sounds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "sound_themes")
BUILTIN = os.path.join(ROOT, "sounds")
MB = 1024 * 1024


def _import_helpers():
    if EXT_DIR not in sys.path:
        sys.path.insert(0, EXT_DIR)
    import sound_themes_store
    import sound_themes_text
    return sound_themes_store, sound_themes_text


@pytest.fixture(scope="module")
def store():
    return _import_helpers()[0]


@pytest.fixture(scope="module")
def text():
    return _import_helpers()[1]


@pytest.fixture
def env(tmp_path, monkeypatch, tmp_data_dir, store):
    """An empty %APPDATA%\\Hariku2 and recorded (not real) playback."""
    user_dir = tmp_path / "Hariku2"
    monkeypatch.setattr(core.api, "USER_DATA_DIR", str(user_dir))
    calls = {"played": [], "stopped": []}
    monkeypatch.setattr(core.sounds, "play_sound", lambda p: calls["played"].append(p) or True)
    monkeypatch.setattr(core.sounds, "stop_sound", lambda p: calls["stopped"].append(p) or True)
    core.sounds.set_theme_dir(None)
    calls["root"] = user_dir / "sound_themes"
    yield calls
    core.sounds.set_theme_dir(None)


def wav_bytes(frames=64, seed=0, rate=8000, channels=1, width=2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes((i * 7 + seed) % 256 for i in range(frames * channels * width)))
    return buf.getvalue()


def big_wav(size):
    """A valid WAV of about `size` bytes (silence, so it zips small)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(8000)
        w.writeframes(bytes(size - 44))
    return buf.getvalue()


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
    return str(path)


def builtin(name):
    with open(os.path.join(BUILTIN, name), "rb") as f:
        return f.read()


def read(path):
    with open(path, "rb") as f:
        return f.read()


def leftovers(root):
    return [e for e in os.listdir(root) if e.startswith(".")] if os.path.isdir(root) else []


# --------------------------------------------------------------------------- #
# Listing and names
# --------------------------------------------------------------------------- #
def test_only_default_without_a_themes_folder(env, store):
    assert store.list_themes() == [None]
    assert store.get_active() is None


def test_listing_sorts_and_skips_what_is_not_a_theme(env, store):
    root = env["root"]
    for name in ("b", "A", "Default", ".work-123", " spaced", "x" * 61):
        (root / name).mkdir(parents=True)
    (root / "loose.wav").write_bytes(wav_bytes())
    assert store.list_themes() == [None, "A", "b"]


@pytest.mark.parametrize("bad, code", [
    ("", "name_empty"), ("   ", "name_empty"), ("x" * 61, "name_too_long"),
    ("a/b", "name_invalid"), ("a\\b", "name_invalid"), ("what?", "name_invalid"),
    ('say "hi"', "name_invalid"), ("con", "name_invalid"), ("LPT1.old", "name_invalid"),
    (".hidden", "name_invalid"), ("trailing.", "name_invalid"), ("bell\x07", "name_invalid"),
    ("Default", "name_reserved"), ("DEFAULT", "name_reserved"),
])
def test_create_rejects_bad_names(env, store, bad, code):
    with pytest.raises(store.ThemeError) as info:
        store.create_theme(bad)
    assert info.value.code == code
    assert store.list_themes() == [None]


def test_create_cleans_the_name_and_makes_an_empty_theme(env, store):
    assert store.create_theme("  Ocean   Waves ") == "Ocean Waves"
    assert store.list_themes() == [None, "Ocean Waves"]
    assert store.custom_sounds("Ocean Waves") == []
    assert os.listdir(env["root"] / "Ocean Waves") == []


def test_names_are_unique_in_any_letter_case(env, store):
    store.create_theme("Ocean")
    with pytest.raises(store.ThemeError) as info:
        store.create_theme("OCEAN")
    assert info.value.code == "name_exists" and info.value.params["name"] == "Ocean"
    assert store.find_theme("ocean") == "Ocean"


def test_unique_name(env, store):
    store.create_theme("Ocean")
    assert store.unique_name("Ocean", "Imported") == "Ocean 2"
    store.create_theme("Ocean 2")
    assert store.unique_name("ocean", "Imported") == "ocean 3"
    assert store.unique_name("tab\there", "Imported") == "tab here"
    assert store.unique_name("My: pack?", "Imported") == "My pack"
    assert store.unique_name("Default", "Imported") == "Imported"
    assert store.unique_name("...", "Imported") == "Imported"
    assert store.unique_name("...", "Default") == "Sound theme"
    assert len(store.unique_name("y" * 100, "Imported")) == store.MAX_NAME_LENGTH


# --------------------------------------------------------------------------- #
# Duplicate, rename, delete
# --------------------------------------------------------------------------- #
def test_duplicate_copies_the_theme_sounds(env, store):
    store.create_theme("Ocean")
    data = wav_bytes(seed=3)
    (env["root"] / "Ocean" / "confirm.wav").write_bytes(data)
    (env["root"] / "Ocean" / "notes.txt").write_text("not a sound")
    assert store.duplicate_theme("ocean", "Sea") == "Sea"
    assert store.custom_sounds("Sea") == ["confirm.wav"]
    assert read(env["root"] / "Sea" / "confirm.wav") == data
    assert leftovers(env["root"]) == []


def test_duplicating_default_gives_an_empty_theme(env, store):
    assert store.duplicate_theme(None, "Mine") == "Mine"
    assert store.custom_sounds("Mine") == []


def test_duplicate_to_a_taken_name_fails_cleanly(env, store):
    store.create_theme("Ocean")
    with pytest.raises(store.ThemeError) as info:
        store.duplicate_theme("Ocean", "ocean")
    assert info.value.code == "name_exists"
    assert store.list_themes() == [None, "Ocean"] and leftovers(env["root"]) == []


def test_rename(env, store):
    store.create_theme("Ocean")
    (env["root"] / "Ocean" / "move.wav").write_bytes(wav_bytes())
    assert store.rename_theme("Ocean", "Sea") == "Sea"
    assert store.list_themes() == [None, "Sea"]
    assert store.custom_sounds("Sea") == ["move.wav"]
    assert "move.wav" in env["stopped"]  # released before moving the folder


def test_rename_to_a_new_letter_case(env, store):
    store.create_theme("ocean")
    assert store.rename_theme("ocean", "Ocean") == "Ocean"
    assert store.list_themes() == [None, "Ocean"]


def test_rename_rules(env, store):
    store.create_theme("Ocean")
    store.create_theme("Sea")
    for old, new, code in ((None, "X", "default_readonly"), ("Ocean", "sea", "name_exists"),
                           ("Gone", "X", "not_found"), ("Ocean", "Default", "name_reserved")):
        with pytest.raises(store.ThemeError) as info:
            store.rename_theme(old, new)
        assert info.value.code == code
    assert store.list_themes() == [None, "Ocean", "Sea"]


def test_renaming_the_active_theme_keeps_it_active(env, store):
    store.create_theme("Ocean")
    store.apply_theme("Ocean")
    store.rename_theme("Ocean", "Sea")
    assert store.get_active() == "Sea"
    assert core.api.load_data(store.DATA_KEY)["active"] == "Sea"
    assert core.sounds.get_theme_dir() == str(env["root"] / "Sea")


def test_delete_rules(env, store):
    store.create_theme("Ocean")
    store.create_theme("Sea")
    (env["root"] / "Sea" / "info.wav").write_bytes(wav_bytes())
    store.apply_theme("Ocean")
    for name, code in ((None, "default_readonly"), ("Ocean", "delete_active"), ("Gone", "not_found")):
        with pytest.raises(store.ThemeError) as info:
            store.delete_theme(name)
        assert info.value.code == code
    assert store.delete_theme("sea") == "Sea"
    assert store.list_themes() == [None, "Ocean"]
    assert not (env["root"] / "Sea").exists()
    assert "info.wav" in env["stopped"]


# --------------------------------------------------------------------------- #
# WAV checks, replace and reset
# --------------------------------------------------------------------------- #
def test_wav_check_accepts_pcm_and_the_builtin_sounds(store):
    store.check_wav_data(wav_bytes())
    store.check_wav_data(wav_bytes(channels=2, width=1, rate=44100))
    store.check_wav_data(builtin("move.wav"))


def _float_wav():
    data = bytearray(wav_bytes())
    data[20:22] = (3).to_bytes(2, "little")  # WAVE_FORMAT_IEEE_FLOAT
    return bytes(data)


@pytest.mark.parametrize("data", [
    b"", b"hello, this is text", b"RIFF\x00\x00\x00\x00AVI LIST", wav_bytes()[:30],
    _float_wav(), wav_bytes(frames=0), b"ID3" + bytes(100),
])
def test_wav_check_rejects_other_files(store, data):
    with pytest.raises(store.ThemeError) as info:
        store.check_wav_data(data)
    assert info.value.code == "not_wav"


def test_replace_and_reset(env, store, tmp_path):
    store.create_theme("Ocean")
    source = tmp_path / "My Confirm.WAV"
    data = wav_bytes(seed=9)
    source.write_bytes(data)
    assert store.replace_sound("Ocean", "CONFIRM.wav", str(source)) == "confirm.wav"
    target = env["root"] / "Ocean" / "confirm.wav"
    assert read(target) == data
    assert env["stopped"] == ["confirm.wav"]
    assert store.custom_sounds("Ocean") == ["confirm.wav"]
    assert store.sound_path("Ocean", "confirm.wav") == str(target)
    assert store.sound_path("Ocean", "move.wav") == os.path.join(BUILTIN, "move.wav")
    assert store.sound_path(None, "confirm.wav") == os.path.join(BUILTIN, "confirm.wav")

    # Replacing again swaps the file in place.
    newer = wav_bytes(seed=10)
    source.write_bytes(newer)
    store.replace_sound("Ocean", "confirm.wav", str(source))
    assert read(target) == newer
    assert [e for e in os.listdir(env["root"] / "Ocean") if e != "confirm.wav"] == []

    assert store.reset_sound("Ocean", "confirm.wav") is True
    assert not target.exists()
    assert store.reset_sound("Ocean", "confirm.wav") is False


def test_replace_rejects_bad_files_and_keeps_the_old_sound(env, store, tmp_path):
    store.create_theme("Ocean")
    good = wav_bytes(seed=1)
    (env["root"] / "Ocean" / "error.wav").write_bytes(good)
    text_file = tmp_path / "notes.wav"
    text_file.write_text("not a sound at all")
    huge = tmp_path / "huge.wav"
    huge.write_bytes(big_wav(5 * MB + 100))
    cases = ((str(text_file), "error.wav", "not_wav"), (str(huge), "error.wav", "too_big"),
             (str(tmp_path / "missing.wav"), "error.wav", "file_missing"),
             (str(text_file), "nosuch.wav", "unknown_sound"))
    for path, sound, code in cases:
        with pytest.raises(store.ThemeError) as info:
            store.replace_sound("Ocean", sound, path)
        assert info.value.code == code
    assert read(env["root"] / "Ocean" / "error.wav") == good
    with pytest.raises(store.ThemeError) as info:
        store.replace_sound(None, "error.wav", str(text_file))
    assert info.value.code == "default_readonly"
    with pytest.raises(store.ThemeError) as info:
        store.reset_sound(None, "error.wav")
    assert info.value.code == "default_readonly"


def test_sound_names_cover_the_builtin_sounds(store):
    names = store.sound_names()
    assert len(names) == len(set(n.casefold() for n in names))
    for f in os.listdir(BUILTIN):
        if f.lower().endswith(".wav"):
            assert f in names
    assert store.canonical_sound_name(" OPENDIARY.WAV ") == "openDiary.wav"
    assert store.canonical_sound_name("sub/move.wav") is None
    assert store.canonical_sound_name(None) is None


# --------------------------------------------------------------------------- #
# ZIP import
# --------------------------------------------------------------------------- #
def test_zip_import(env, store, tmp_path):
    confirm, move = wav_bytes(seed=1), wav_bytes(seed=2)
    path = make_zip(tmp_path / "Ocean pack.zip", [
        ("Ocean/Confirm.WAV", confirm), ("Ocean/move.wav", move),
        ("Ocean/readme.txt", b"hello"), ("Ocean/unknown.wav", wav_bytes()),
        ("Ocean/select.wav", b"not really a wav"), ("Ocean/", b""),
        ("other/confirm.wav", wav_bytes(seed=5)),  # a second confirm: the first one wins
    ])
    name, count, skipped = store.import_theme(path, "Imported")
    assert (name, count, skipped) == ("Ocean pack", 2, 3)
    assert sorted(store.custom_sounds(name)) == ["confirm.wav", "move.wav"]
    assert read(env["root"] / name / "confirm.wav") == confirm
    assert read(env["root"] / name / "move.wav") == move
    assert leftovers(env["root"]) == []
    # The same file again gets a numbered name.
    assert store.import_theme(path, "Imported")[0] == "Ocean pack 2"


@pytest.mark.parametrize("evil", ["../start.wav", "sounds/../../start.wav", "..\\start.wav",
                                  "/start.wav", "C:/start.wav", "C:start.wav"])
def test_zip_with_traversal_is_refused_whole(env, store, tmp_path, evil):
    path = make_zip(tmp_path / "evil.zip", [("move.wav", wav_bytes()), (evil, wav_bytes())])
    with pytest.raises(store.ThemeError) as info:
        store.import_theme(path, "Imported")
    assert info.value.code == "archive_unsafe"
    assert store.list_themes() == [None] and leftovers(env["root"]) == []
    assert not (tmp_path / "start.wav").exists()


def test_zip_sound_over_the_size_limit_is_left_out(env, store, tmp_path):
    path = make_zip(tmp_path / "big.zip", [("start.wav", big_wav(5 * MB + 1000)),
                                           ("move.wav", wav_bytes())])
    name, count, skipped = store.import_theme(path, "Imported")
    assert (count, skipped) == (1, 1)
    assert store.custom_sounds(name) == ["move.wav"]


def test_zip_over_the_total_limit_is_refused(env, store, tmp_path):
    entries = [(f"{s}.wav", big_wav(4 * MB + 500 * 1024)) for s in ("start", "move", "info", "tik", "ui")]
    path = make_zip(tmp_path / "huge.zip", entries)
    with pytest.raises(store.ThemeError) as info:
        store.import_theme(path, "Imported")
    assert info.value.code == "archive_too_large"
    assert store.list_themes() == [None] and leftovers(env["root"]) == []


@pytest.mark.parametrize("entries", [
    [("readme.txt", b"hi")], [("unknown.wav", wav_bytes())], [("move.wav", b"RIFF junk")], [],
])
def test_zip_without_usable_sounds(env, store, tmp_path, entries):
    path = make_zip(tmp_path / "empty.zip", entries)
    with pytest.raises(store.ThemeError) as info:
        store.import_theme(path, "Imported")
    assert info.value.code == "archive_no_sounds"
    assert store.list_themes() == [None]


def test_unreadable_files(env, store, tmp_path):
    garbage = tmp_path / "garbage.zip"
    garbage.write_bytes(b"this is neither a zip nor a Hariku 1 theme" * 10)
    for path in (garbage, tmp_path / "missing.zip"):
        with pytest.raises(store.ThemeError) as info:
            store.import_theme(str(path), "Imported")
        assert info.value.code == "archive_unreadable"


def test_zip_named_default_gets_the_fallback_name(env, store, tmp_path):
    path = make_zip(tmp_path / "default.zip", [("move.wav", wav_bytes())])
    assert store.import_theme(path, "Imported")[0] == "Imported"


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def test_export_round_trip(env, store, tmp_path):
    store.create_theme("Ocean")
    sounds = {"confirm.wav": wav_bytes(seed=4), "Writing3.wav": wav_bytes(seed=5)}
    for sound, data in sounds.items():
        (env["root"] / "Ocean" / sound).write_bytes(data)
    out = tmp_path / "out" / "Ocean.zip"
    out.parent.mkdir()
    assert store.export_theme("ocean", str(out)) == 2
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == sorted(sounds)
    assert os.listdir(out.parent) == ["Ocean.zip"]  # no temporary file left

    name, count, skipped = store.import_theme(str(out), "Imported")
    assert (name, count, skipped) == ("Ocean 2", 2, 0)
    for sound, data in sounds.items():
        assert read(env["root"] / name / sound) == data


def test_export_default_writes_hariku_sounds(env, store, tmp_path):
    out = tmp_path / "default sounds.zip"
    count = store.export_theme(None, str(out))
    builtin_wavs = [f for f in os.listdir(BUILTIN) if f.lower().endswith(".wav")]
    assert count == len(builtin_wavs)
    with zipfile.ZipFile(out) as z:
        assert z.read("move.wav") == builtin("move.wav")


def test_export_of_an_empty_theme_fails(env, store, tmp_path):
    store.create_theme("Empty")
    with pytest.raises(store.ThemeError) as info:
        store.export_theme("Empty", str(tmp_path / "x.zip"))
    assert info.value.code == "export_empty"
    assert not (tmp_path / "x.zip").exists()


# --------------------------------------------------------------------------- #
# Hariku 1 theme archives
# --------------------------------------------------------------------------- #
V1_KEY = b"H4R1KU"


def v1_archive(sounds, obfuscate=False):
    """The format Hariku 1's sound_theme_manager._create_archive wrote."""
    index, blob, offset = {}, b"", 8192
    for name in sorted(sounds):
        index[name] = {"offset": offset, "size": len(sounds[name])}
        blob += sounds[name]
        offset += len(sounds[name])
    index_bytes = json.dumps(index, indent=2).encode("utf-8")
    header = len(index_bytes).to_bytes(4, "little") + index_bytes
    data = header + b"\0" * (8192 - len(header)) + blob
    if obfuscate:
        data = bytes(b ^ V1_KEY[i % len(V1_KEY)] for i, b in enumerate(data))
    return data


@pytest.mark.parametrize("obfuscate", [False, True])
def test_hariku1_theme_import(env, store, tmp_path, obfuscate):
    confirm = wav_bytes(seed=7)
    archive = tmp_path / "Rain.hrk"
    archive.write_bytes(v1_archive({
        "confirm.wav": confirm,               # changed: imported
        "move.wav": builtin("move.wav"),      # same as Hariku's own: stays default
        "default.wav": wav_bytes(),           # not a Hariku 2 sound
    }, obfuscate))
    name, count, skipped = store.import_theme(str(archive), "Imported")
    assert (name, count, skipped) == ("Rain", 1, 1)
    assert store.custom_sounds("Rain") == ["confirm.wav"]
    assert read(env["root"] / "Rain" / "confirm.wav") == confirm


def test_hariku1_theme_identical_to_default(env, store, tmp_path):
    archive = tmp_path / "default.hrk"
    archive.write_bytes(v1_archive({"move.wav": builtin("move.wav"), "tik.wav": builtin("tik.wav")}))
    with pytest.raises(store.ThemeError) as info:
        store.import_theme(str(archive), "Imported")
    assert info.value.code == "archive_all_default"


def _corrupt(data, index_text):
    body = index_text.encode()
    return len(body).to_bytes(4, "little") + body + data[4 + len(body):]


@pytest.mark.parametrize("damage", ["short", "json", "list", "bounds", "before_index", "huge_index"])
def test_damaged_hariku1_archives(env, store, tmp_path, damage):
    good = v1_archive({"confirm.wav": wav_bytes(seed=7)})
    if damage == "short":
        data = good[:3]
    elif damage == "json":
        data = _corrupt(good, "{not json")
    elif damage == "list":
        data = _corrupt(good, "[1, 2]")
    elif damage == "bounds":
        data = _corrupt(good, '{"confirm.wav": {"offset": 8192, "size": 999999}}')
    elif damage == "before_index":
        data = _corrupt(good, '{"confirm.wav": {"offset": 2, "size": 10}}')
    else:
        data = (9000).to_bytes(4, "little") + good[4:]
    archive = tmp_path / "broken.hrk"
    archive.write_bytes(data)
    with pytest.raises(store.ThemeError) as info:
        store.import_theme(str(archive), "Imported")
    assert info.value.code == "archive_unreadable"
    assert store.list_themes() == [None]


def test_xor_matches_the_byte_by_byte_hariku1_decoder(store):
    data = bytes(range(256)) * 3
    for offset in (0, 4, 5, 8192, 8197):
        slow = bytes(b ^ V1_KEY[(offset + i) % len(V1_KEY)] for i, b in enumerate(data))
        assert store._xor(data, offset) == slow
    assert store._xor(b"", 3) == b""


# --------------------------------------------------------------------------- #
# Active theme, persistence and cycling
# --------------------------------------------------------------------------- #
def test_apply_saves_and_restores(env, store):
    store.create_theme("Ocean")
    assert store.apply_theme("OCEAN") == "Ocean"
    assert core.api.load_data(store.DATA_KEY) == {"active": "Ocean"}
    assert core.sounds.get_theme_dir() == str(env["root"] / "Ocean")
    core.sounds.set_theme_dir(None)
    assert store.restore_active() == "Ocean"
    assert core.sounds.get_theme_dir() == str(env["root"] / "Ocean")
    assert core.api.load_data("Core")["sound_theme_dir"] == str(env["root"] / "Ocean")
    assert store.apply_theme(None) is None
    assert core.api.load_data(store.DATA_KEY) == {"active": ""}
    assert core.sounds.get_theme_dir() is None
    assert "sound_theme_dir" not in core.api.load_data("Core")   # Default: forgotten


def test_a_theme_folder_that_disappeared_means_default(env, store):
    store.create_theme("Ocean")
    store.apply_theme("Ocean")
    os.rmdir(env["root"] / "Ocean")
    assert store.get_active() is None
    assert store.restore_active() is None
    assert core.sounds.get_theme_dir() is None


def test_apply_unknown_theme_fails(env, store):
    with pytest.raises(store.ThemeError) as info:
        store.apply_theme("Nope")
    assert info.value.code == "not_found"


def test_cycling_order(env, store):
    with pytest.raises(store.ThemeError) as info:
        store.next_theme()
    assert info.value.code == "no_other_themes"
    store.create_theme("b")
    store.create_theme("A")
    assert [store.next_theme() for _ in range(4)] == ["A", "b", None, "A"]
    assert core.sounds.get_theme_dir() == str(env["root"] / "A")


# --------------------------------------------------------------------------- #
# The extension entry point
# --------------------------------------------------------------------------- #
@pytest.fixture
def main(env, store, monkeypatch):
    import core.hotkeys
    import core.preferences
    registered = {"actions": [], "panels": []}
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *a, **k: registered["actions"].append((a, k)))
    monkeypatch.setattr(core.preferences, "register_panel",
                        lambda *a, **k: registered["panels"].append(a))
    spec = importlib.util.spec_from_file_location("sound_themes_main_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken, internal = [], []
    monkeypatch.setattr(module, "speak", lambda t, interrupt=False: spoken.append(t))
    monkeypatch.setattr(core.sounds, "play_internal_sound", lambda n: internal.append(n) or True)
    module.registered, module.spoken, module.internal = registered, spoken, internal
    return module


def test_register_restores_the_theme_and_teardown_resets_it(main, store, env):
    store.create_theme("Ocean")
    store.apply_theme("Ocean")
    core.sounds.set_theme_dir(None)
    main.register(object())
    assert core.sounds.get_theme_dir() == str(env["root"] / "Ocean")
    (args, kwargs), = main.registered["actions"]
    assert args[:2] == ("Sound Themes", "next_theme")
    assert args[3:5] == (ord("S"), False) and kwargs == {"default_shift": True}
    assert main.registered["panels"][0][0] == "Sound Themes"
    main.teardown()
    assert core.sounds.get_theme_dir() is None
    assert store.get_active() == "Ocean"  # the choice itself is kept for next time
    # ...and the core still remembers it, so the next start plays its start.wav.
    assert core.api.load_data("Core")["sound_theme_dir"] == str(env["root"] / "Ocean")


def test_next_theme_hotkey(main, store, env):
    main.next_sound_theme()
    assert main.spoken == ["There are no other sound themes. Make one in Preferences, Sound Themes."]
    assert main.internal == []
    store.create_theme("Ocean")
    main.next_sound_theme()
    main.next_sound_theme()
    assert main.spoken[1:] == ["Theme Ocean applied.", "Hariku's own sounds applied."]
    assert main.internal == ["start.wav", "start.wav"]


# --------------------------------------------------------------------------- #
# Wording
# --------------------------------------------------------------------------- #
def _messages(code):
    with open(os.path.join(EXT_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)["messages"]


def test_every_error_and_sound_has_text_in_both_languages(store, text):
    with open(os.path.join(EXT_DIR, "sound_themes_store.py"), encoding="utf-8") as f:
        codes = set(re.findall(r'ThemeError\("(\w+)"', f.read()))
    with open(os.path.join(EXT_DIR, "sound_themes_ui.py"), encoding="utf-8") as f:
        codes |= set(re.findall(r'ThemeError\("(\w+)"', f.read()))
    assert codes <= set(text.ERROR_KEYS), codes - set(text.ERROR_KEYS)
    keys = set(text.ERROR_KEYS.values()) | set(store.SOUND_KEYS.values()) | {"snd_other"}
    en, id_ = _messages("en"), _messages("id")
    assert keys <= set(en), keys - set(en)
    assert set(en) == set(id_), set(en) ^ set(id_)


def test_rows(text):
    assert text.theme_row(None, True, 0) == "Default, Hariku's own sounds, in use"
    assert text.theme_row("Ocean", False, 0) == "Ocean, no sounds of its own yet"
    assert text.theme_row("Ocean", True, 1) == "Ocean, in use, 1 sound of its own"
    assert text.theme_row("Ocean", False, 3) == "Ocean, 3 sounds of its own"
    assert text.sound_row("move.wav", None, False) == "move, moving between days"
    assert text.sound_row("move.wav", "Ocean", True) == "move, moving between days, this theme's sound"
    assert text.sound_row("Writing2.wav", "Ocean", False) == "Writing2, typing sound 2, default sound"
    assert text.error_text(core_error("too_big", limit_mb=5)) == \
        "That file is too large. A sound can be at most 5 MB."


def core_error(code, **params):
    store, _text = _import_helpers()
    return store.ThemeError(code, **params)


def test_manifest_needs_core_2_7_to_remember_the_theme():
    import json
    with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["version"] == "1.1" and manifest["minimum_core_version"] == "2.7"
