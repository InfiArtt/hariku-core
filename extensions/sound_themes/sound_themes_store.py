# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Sound theme storage, with no wx: theme folders, the active theme, WAV checks,
and importing/exporting ZIP files and Hariku 1 theme archives.

A theme is a folder %APPDATA%\\Hariku2\\sound_themes\\<name>\\ holding .wav files
named like Hariku's own sounds. A sound the folder lacks plays the built-in
one, so an empty folder sounds exactly like Default. Default (None here) is
Hariku's own sounds folder and is never written to.

Failures raise ThemeError(code, **params); sound_themes_text turns the code
into a sentence. Import and export can take a moment, so the UI calls them on a
worker thread; nothing here touches wx.
"""

import io
import json
import logging
import os
import shutil
import tempfile
import wave
import zipfile

import core.api
import core.sounds

logger = logging.getLogger(__name__)

DATA_KEY = "SoundThemes"      # {"active": "<theme name>" or "" for Default}
FOLDER_NAME = "sound_themes"

MAX_SOUND_BYTES = 5 * 1024 * 1024
MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2000
MAX_NAME_LENGTH = 60
RESERVED_NAME = "Default"

# Hariku's sounds and the message key describing each, in list order.
SOUNDS = (
    ("button.wav", "snd_button"),
    ("confirm.wav", "snd_confirm"),
    ("delete.wav", "snd_delete"),
    ("error.wav", "snd_error"),
    ("exit.wav", "snd_exit"),
    ("hide.wav", "snd_hide"),
    ("history.wav", "snd_history"),
    ("info.wav", "snd_info"),
    ("listen.wav", "snd_listen"),
    ("listen_end.wav", "snd_listen_end"),
    ("move.wav", "snd_move"),
    ("openDiary.wav", "snd_openDiary"),
    ("penClick.wav", "snd_penClick"),
    ("reminder.wav", "snd_reminder"),
    ("select.wav", "snd_select"),
    ("show.wav", "snd_show"),
    ("start.wav", "snd_start"),
    ("thankyou.wav", "snd_thankyou"),
    ("tik.wav", "snd_tik"),
    ("turn.wav", "snd_turn"),
    ("ui.wav", "snd_ui"),
    ("view.wav", "snd_view"),
    ("Writing1.wav", "snd_writing"),
    ("Writing2.wav", "snd_writing"),
    ("Writing3.wav", "snd_writing"),
    ("Writing4.wav", "snd_writing"),
    ("Writing5.wav", "snd_writing"),
)
SOUND_KEYS = dict(SOUNDS)

_INVALID_CHARS = frozenset('<>:"/\\|?*')
_DEVICE_NAMES = frozenset(["con", "prn", "aux", "nul"]
                          + [f"com{i}" for i in range(1, 10)]
                          + [f"lpt{i}" for i in range(1, 10)])

# Hariku 1 theme archive (.hrk): a 4-byte little-endian index length, a JSON
# index {"name.wav": {"offset": n, "size": n}} inside the first 8192 bytes, then
# the WAV data. Some files are XOR-ed throughout with this key (by file offset).
V1_HEADER_SIZE = 8192
V1_KEY = b"H4R1KU"


class ThemeError(Exception):
    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


# ------------------------------------------------------------
# Sounds
# ------------------------------------------------------------

_extra_sounds = None


def builtin_dir():
    return core.sounds.get_builtin_sounds_dir()


def sound_names():
    """Every Hariku sound name: the known ones, then any other .wav the
    installed Hariku ships (in case a newer core adds sounds)."""
    global _extra_sounds
    names = [name for name, _key in SOUNDS]
    if _extra_sounds is None:
        known = {n.casefold() for n in names}
        try:
            found = [f for f in os.listdir(builtin_dir())
                     if f.lower().endswith(".wav") and f.casefold() not in known]
        except OSError:
            found = []
        _extra_sounds = sorted(found, key=str.casefold)
    return names + _extra_sounds


def canonical_sound_name(name):
    """The Hariku sound called `name` in any letter case, or None."""
    if not isinstance(name, str):
        return None
    folded = name.strip().casefold()
    for sound in sound_names():
        if sound.casefold() == folded:
            return sound
    return None


def _require_sound(name):
    sound = canonical_sound_name(name)
    if sound is None:
        raise ThemeError("unknown_sound", name=str(name))
    return sound


# ------------------------------------------------------------
# Theme names and folders
# ------------------------------------------------------------

def themes_root():
    return os.path.join(core.api.USER_DATA_DIR, FOLDER_NAME)


def clean_name(text):
    return " ".join(str(text or "").split())


def _name_problem(name):
    """Why `name` can't be a theme folder name, or None."""
    if not name:
        return "name_empty"
    if len(name) > MAX_NAME_LENGTH:
        return "name_too_long"
    if (any(c in _INVALID_CHARS or ord(c) < 32 for c in name)
            or name.startswith(".") or name.endswith(".")
            or name.split(".")[0].strip().casefold() in _DEVICE_NAMES):
        return "name_invalid"
    if name.casefold() == RESERVED_NAME.casefold():
        return "name_reserved"
    return None


def list_themes():
    """None (Default, always first) followed by the theme names, sorted."""
    root = themes_root()
    try:
        entries = os.listdir(root)
    except OSError:
        entries = []
    names = [e for e in entries
             if e == clean_name(e) and _name_problem(e) is None
             and os.path.isdir(os.path.join(root, e))]
    names.sort(key=str.casefold)
    return [None] + names


def find_theme(name):
    """The existing theme called `name` in any letter case, or None."""
    folded = clean_name(name).casefold()
    if not folded:
        return None
    for theme in list_themes()[1:]:
        if theme.casefold() == folded:
            return theme
    return None


def theme_dir(name):
    return None if name is None else os.path.join(themes_root(), name)


def check_name(name, renaming=None):
    """The cleaned-up name, if a theme may be given it. `renaming` is the
    current name of a theme being renamed (it may keep its own name)."""
    name = clean_name(name)
    problem = _name_problem(name)
    if problem:
        raise ThemeError(problem, name=name, limit=MAX_NAME_LENGTH)
    existing = find_theme(name)
    if existing is not None and (renaming is None or existing.casefold() != renaming.casefold()):
        raise ThemeError("name_exists", name=existing)
    return name


def unique_name(wanted, fallback):
    """A free theme name based on `wanted` (typically a file name), made valid
    and numbered ("Ocean 2") if taken; `fallback` if nothing usable is left."""
    def usable(text):
        text = clean_name("".join(c for c in clean_name(text)
                                  if c not in _INVALID_CHARS and ord(c) >= 32))
        return clean_name(text.strip(" .")[:MAX_NAME_LENGTH].strip(" ."))

    name = usable(wanted)
    if _name_problem(name):
        name = usable(fallback)
    if _name_problem(name):
        name = "Sound theme"
    base, number = name, 1
    while find_theme(name) is not None:
        number += 1
        suffix = f" {number}"
        name = clean_name(base[:MAX_NAME_LENGTH - len(suffix)].rstrip(" .") + suffix)
    return name


def _require_theme(name):
    """The existing custom theme's name; Default and missing themes raise."""
    if name is None:
        raise ThemeError("default_readonly")
    found = find_theme(name)
    if found is None:
        raise ThemeError("not_found", name=clean_name(name))
    return found


def _new_work_dir():
    # Built next to the themes and renamed into place when complete, so a
    # failure never leaves a half-made theme. The leading dot keeps it out of
    # list_themes().
    root = themes_root()
    os.makedirs(root, exist_ok=True)
    return tempfile.mkdtemp(prefix=".work-", dir=root)


def _publish(work_dir, name):
    final = theme_dir(name)
    if os.path.exists(final):
        raise ThemeError("name_exists", name=name)
    os.rename(work_dir, final)


def _discard(path):
    shutil.rmtree(path, ignore_errors=True)


def _release_folder(folder):
    # Windows keeps a played sound file open; close them so the folder can
    # change. This stops any of Hariku's sounds with the same file name.
    try:
        for entry in os.listdir(folder):
            if entry.lower().endswith(".wav"):
                core.sounds.stop_sound(entry)
    except OSError:
        pass


def _io_error(action, error):
    logger.error(f"[Sound Themes] Could not {action}: {error}")
    return ThemeError("io")


# ------------------------------------------------------------
# Theme contents
# ------------------------------------------------------------

def custom_sounds(name):
    """The sound names theme `name` has its own file for (Default: none)."""
    folder = theme_dir(name)
    if folder is None:
        return []
    return [s for s in sound_names() if os.path.isfile(os.path.join(folder, s))]


def sound_path(name, sound):
    """The file sound `sound` plays with theme `name`: the theme's copy, or
    Hariku's own."""
    sound = _require_sound(sound)
    folder = theme_dir(name)
    if folder is not None:
        path = os.path.join(folder, sound)
        if os.path.isfile(path):
            return path
    return core.sounds.default_sound_path(sound)


def check_wav_data(data):
    """Raise ThemeError unless `data` is a WAV sound Hariku can play."""
    if len(data) > MAX_SOUND_BYTES:
        raise ThemeError("too_big", limit_mb=MAX_SOUND_BYTES // (1024 * 1024))
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ThemeError("not_wav")
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            ok = (w.getnchannels() > 0 and w.getsampwidth() > 0
                  and w.getframerate() > 0 and w.getnframes() > 0)
    except Exception:
        ok = False
    if not ok:
        raise ThemeError("not_wav")


def read_wav_file(path):
    """The bytes of the WAV file at `path`, checked; raises ThemeError."""
    try:
        if not os.path.isfile(path):
            raise ThemeError("file_missing")
        if os.path.getsize(path) > MAX_SOUND_BYTES:
            raise ThemeError("too_big", limit_mb=MAX_SOUND_BYTES // (1024 * 1024))
        with open(path, "rb") as f:
            data = f.read(MAX_SOUND_BYTES + 1)
    except OSError as e:
        logger.info(f"[Sound Themes] Could not read {path}: {e}")
        raise ThemeError("file_unreadable")
    check_wav_data(data)
    return data


def _write_file(path, data):
    # Write beside the target, then swap it in, so a failure keeps the old file.
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".wav", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def replace_sound(name, sound, source_path):
    """Copy the WAV file at `source_path` into theme `name` as `sound`."""
    name = _require_theme(name)
    sound = _require_sound(sound)
    data = read_wav_file(source_path)
    target = os.path.join(theme_dir(name), sound)
    core.sounds.stop_sound(sound)
    try:
        _write_file(target, data)
    except OSError as e:
        raise _io_error(f"replace {target}", e)
    return sound


def reset_sound(name, sound):
    """Remove the theme's copy of `sound`. False if it had none."""
    name = _require_theme(name)
    sound = _require_sound(sound)
    target = os.path.join(theme_dir(name), sound)
    if not os.path.isfile(target):
        return False
    core.sounds.stop_sound(sound)
    try:
        os.remove(target)
    except OSError as e:
        raise _io_error(f"remove {target}", e)
    return True


# ------------------------------------------------------------
# Themes
# ------------------------------------------------------------

def create_theme(name):
    """A new, empty theme (it sounds like Default until sounds are replaced)."""
    name = check_name(name)
    try:
        os.makedirs(themes_root(), exist_ok=True)
        os.mkdir(theme_dir(name))
    except FileExistsError:
        raise ThemeError("name_exists", name=name)
    except OSError as e:
        raise _io_error(f"create theme {name!r}", e)
    return name


def duplicate_theme(source, new_name):
    """A copy of theme `source` (None copies Default, giving an empty theme)."""
    source = None if source is None else _require_theme(source)
    new_name = check_name(new_name)
    try:
        work = _new_work_dir()
    except OSError as e:
        raise _io_error("prepare a theme folder", e)
    try:
        for sound in custom_sounds(source):
            shutil.copyfile(os.path.join(theme_dir(source), sound), os.path.join(work, sound))
        _publish(work, new_name)
    except ThemeError:
        _discard(work)
        raise
    except OSError as e:
        _discard(work)
        raise _io_error(f"duplicate theme {source!r}", e)
    return new_name


def rename_theme(old, new):
    """Rename a theme; the active theme stays active under its new name."""
    old = _require_theme(old)
    new = check_name(new, renaming=old)
    if new == old:
        return new
    was_active = get_active() == old
    folder = theme_dir(old)
    if was_active:
        core.sounds.set_theme_dir(None)
    _release_folder(folder)
    try:
        os.rename(folder, theme_dir(new))
    except OSError as e:
        if was_active:
            core.sounds.set_theme_dir(folder)
        raise _io_error(f"rename theme {old!r}", e)
    if was_active:
        apply_theme(new)
    return new


def delete_theme(name):
    """Delete a theme and its sounds. Default and the active theme can't be."""
    name = _require_theme(name)
    if get_active() == name:
        raise ThemeError("delete_active", name=name)
    folder = theme_dir(name)
    root = os.path.normcase(os.path.realpath(themes_root()))
    if not os.path.normcase(os.path.realpath(folder)).startswith(root + os.sep):
        raise ThemeError("not_found", name=name)
    _release_folder(folder)
    try:
        shutil.rmtree(folder)
    except OSError as e:
        raise _io_error(f"delete theme {name!r}", e)
    return name


# ------------------------------------------------------------
# The active theme
# ------------------------------------------------------------

def get_active():
    """The theme in use (None for Default, also when its folder is gone)."""
    data = core.api.load_data(DATA_KEY)
    name = data.get("active") if isinstance(data, dict) else None
    return find_theme(name) if isinstance(name, str) and name else None


def apply_theme(name):
    """Use theme `name` (None for Default) from now on, and at every start. The
    core remembers the folder too (core 2.7), so the next start plays the
    theme's start.wav before this extension has loaded."""
    name = None if name is None else _require_theme(name)
    data = core.api.load_data(DATA_KEY)
    data = data if isinstance(data, dict) else {}
    data["active"] = name or ""
    core.api.save_data(DATA_KEY, data)
    core.sounds.set_theme_dir(theme_dir(name), remember=True)
    return name


def restore_active():
    """Apply the saved theme (at startup). Returns its name, or None. Also
    brings the core's remembered folder in line (a theme picked with Sound
    Themes 1.0, or a folder that has gone)."""
    name = get_active()
    core.sounds.set_theme_dir(theme_dir(name), remember=True)
    return name


def next_theme():
    """Switch to the theme after the active one (wrapping to Default) and
    return its name. Raises ThemeError when there is no other theme."""
    themes = list_themes()
    if len(themes) < 2:
        raise ThemeError("no_other_themes")
    active = get_active()
    index = themes.index(active) if active in themes else 0
    return apply_theme(themes[(index + 1) % len(themes)])


# ------------------------------------------------------------
# Import and export
# ------------------------------------------------------------

def _xor(data, offset):
    # XOR with V1_KEY repeated from file offset `offset`; int maths keeps
    # megabytes fast.
    if not data:
        return data
    start = offset % len(V1_KEY)
    key = (V1_KEY[start:] + V1_KEY * (len(data) // len(V1_KEY) + 1))[:len(data)]
    value = int.from_bytes(data, "little") ^ int.from_bytes(key, "little")
    return value.to_bytes(len(data), "little")


def _safe_member(filename):
    """Whether a ZIP entry name stays inside the folder it would extract to."""
    if not filename or "\0" in filename or ":" in filename:
        return False
    if filename.startswith(("/", "\\")):
        return False
    parts = filename.replace("\\", "/").split("/")
    return ".." not in parts


def _check_total(total):
    if total > MAX_IMPORT_BYTES:
        raise ThemeError("archive_too_large", limit_mb=MAX_IMPORT_BYTES // (1024 * 1024))


def _zip_sounds(path):
    """{sound name: WAV bytes} from a ZIP file, plus counts of what was left out."""
    try:
        archive = zipfile.ZipFile(path)
    except Exception as e:  # BadZipFile, OSError, and odd archives zipfile can't handle
        logger.info(f"[Sound Themes] Not a readable ZIP file: {e}")
        raise ThemeError("archive_unreadable")
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise ThemeError("archive_unreadable")
        chosen = {}
        skipped = 0
        for info in infos:
            if not _safe_member(info.filename):
                # A crafted archive: refuse all of it, not just this entry.
                raise ThemeError("archive_unsafe")
            if info.is_dir():
                continue
            base = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
            if not base.lower().endswith(".wav"):
                continue
            sound = canonical_sound_name(base)
            if sound is None or sound in chosen:
                skipped += 1
                continue
            if info.file_size > MAX_SOUND_BYTES:
                skipped += 1
                continue
            chosen[sound] = info
        _check_total(sum(info.file_size for info in chosen.values()))
        sounds = {}
        total = 0
        for sound, info in chosen.items():
            try:
                with archive.open(info) as f:
                    data = f.read(MAX_SOUND_BYTES + 1)  # never trust the stated size
            except Exception as e:  # encrypted, unsupported compression, corrupt
                logger.info(f"[Sound Themes] Skipped {info.filename}: {e}")
                skipped += 1
                continue
            total += len(data)
            _check_total(total)
            try:
                check_wav_data(data)
            except ThemeError:
                skipped += 1
                continue
            sounds[sound] = data
    return sounds, skipped


def _v1_sounds(path):
    """{sound name: WAV bytes} from a Hariku 1 theme archive, plus the number
    left out. Sounds identical to Hariku's own are left out too (Hariku 1
    themes always carried a full set), so they stay "default" here."""
    try:
        size = os.path.getsize(path)
        f = open(path, "rb")
    except OSError as e:
        logger.info(f"[Sound Themes] Could not open {path}: {e}")
        raise ThemeError("archive_unreadable")
    with f:
        header = f.read(4)
        if len(header) < 4:
            raise ThemeError("archive_unreadable")
        # Same test as Hariku 1: a plausible index length, as stored or XOR-ed.
        obfuscated = False
        length = int.from_bytes(header, "little")
        if not 0 < length < V1_HEADER_SIZE:
            obfuscated = True
            length = int.from_bytes(_xor(header, 0), "little")
        if not 0 < length < V1_HEADER_SIZE - 4:
            raise ThemeError("archive_unreadable")
        body = f.read(length)
        if len(body) != length:
            raise ThemeError("archive_unreadable")
        if obfuscated:
            body = _xor(body, 4)
        try:
            index = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ThemeError("archive_unreadable")
        if not isinstance(index, dict):
            raise ThemeError("archive_unreadable")

        chosen = {}
        skipped = 0
        for key, entry in index.items():
            sound = canonical_sound_name(key)
            if sound is None or sound in chosen or not isinstance(entry, dict):
                skipped += 1
                continue
            offset, length_ = entry.get("offset"), entry.get("size")
            if (type(offset) is not int or type(length_) is not int or length_ <= 0
                    or offset < 4 + length or offset + length_ > size):
                raise ThemeError("archive_unreadable")
            if length_ > MAX_SOUND_BYTES:
                skipped += 1
                continue
            chosen[sound] = (offset, length_)
        _check_total(sum(n for _o, n in chosen.values()))

        sounds = {}
        same = 0
        for sound, (offset, length_) in chosen.items():
            f.seek(offset)
            data = f.read(length_)
            if len(data) != length_:
                raise ThemeError("archive_unreadable")
            if obfuscated:
                data = _xor(data, offset)
            try:
                check_wav_data(data)
            except ThemeError:
                skipped += 1
                continue
            if _same_as_builtin(sound, data):
                same += 1
                continue
            sounds[sound] = data
    if not sounds and same:
        raise ThemeError("archive_all_default")
    return sounds, skipped


def _same_as_builtin(sound, data):
    path = core.sounds.default_sound_path(sound)
    try:
        if os.path.getsize(path) != len(data):
            return False
        with open(path, "rb") as f:
            return f.read() == data
    except OSError:
        return False


def import_theme(path, fallback_name):
    """Make a new theme from a ZIP of WAV files or a Hariku 1 theme archive,
    named after the file. Only files named like Hariku's sounds are used.
    Returns (theme name, sounds imported, files left out)."""
    try:
        is_zip = zipfile.is_zipfile(path)
    except OSError:
        is_zip = False
    sounds, skipped = _zip_sounds(path) if is_zip else _v1_sounds(path)
    if not sounds:
        raise ThemeError("archive_no_sounds")
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        work = _new_work_dir()
    except OSError as e:
        raise _io_error("prepare a theme folder", e)
    try:
        for sound, data in sounds.items():
            with open(os.path.join(work, sound), "wb") as f:
                f.write(data)
        name = unique_name(stem, fallback_name)
        _publish(work, name)
    except ThemeError:
        _discard(work)
        raise
    except OSError as e:
        _discard(work)
        raise _io_error(f"import {path}", e)
    return name, len(sounds), skipped


def export_theme(name, dest_path):
    """Save theme `name` as a ZIP of its own sounds (Default: Hariku's sounds).
    Returns the number of sounds written."""
    if name is None:
        folder = builtin_dir()
        sounds = [s for s in sound_names() if os.path.isfile(os.path.join(folder, s))]
    else:
        name = _require_theme(name)
        folder = theme_dir(name)
        sounds = custom_sounds(name)
    if not sounds:
        raise ThemeError("export_empty", name=name or "")
    dest_path = os.path.abspath(dest_path)
    try:
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".zip", dir=os.path.dirname(dest_path))
    except OSError as e:
        raise _io_error(f"write {dest_path}", e)
    try:
        with os.fdopen(fd, "wb") as f:
            with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as archive:
                for sound in sounds:
                    archive.write(os.path.join(folder, sound), sound)
        os.replace(tmp, dest_path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise _io_error(f"write {dest_path}", e)
    return len(sounds)
