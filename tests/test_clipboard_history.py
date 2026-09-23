# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Clipboard History extension: the recording rules, the
# password-manager check (Windows calls replaced by fakes), saving with
# "Remember history" on and off, and the text in both languages. The real
# clipboard is never written.

import ast
import ctypes
import datetime
import importlib.util
import json
import os
import sys
import threading
import time
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "clipboard_history")
EXT_ROOT = os.path.join(ROOT, "extensions")

if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

import clipboard_history_guard as guard  # noqa: E402
import clipboard_history_store as store  # noqa: E402
import clipboard_history_text as text  # noqa: E402

NOW = 1_800_000_000.0


def _history(texts, limit=25, start=NOW):
    history = store.History(limit)
    for n, value in enumerate(texts):
        history.add(value, start + n)
    return history


def _texts(history):
    return [i["text"] for i in history.items]


# --------------------------------------------------------------------------- #
# Recording rules
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["", "   ", "\r\n\t ", None, 42, b"bytes"])
def test_empty_and_non_text_are_ignored(value):
    history = store.History()
    assert history.add(value, NOW) == (None, "empty")
    assert len(history) == 0


def test_size_limit_counts_utf8_bytes():
    history = store.History()
    assert history.add("a" * store.MAX_TEXT_BYTES, NOW)[1] == "added"
    assert history.add("b" * (store.MAX_TEXT_BYTES + 1), NOW)[1] == "too_large"
    # 60,000 characters but 120,000 bytes.
    assert history.add("é" * 60_000, NOW)[1] == "too_large"
    assert history.add("x" * 10_000_000, NOW)[1] == "too_large"
    assert len(history) == 1


def test_new_copies_go_to_the_top():
    history = _history(["one", "two", "three"])
    assert _texts(history) == ["three", "two", "one"]


def test_consecutive_duplicate_is_ignored():
    history = _history(["one", "two"])
    item, status = history.add("two", NOW + 50)
    assert status == "duplicate"
    assert item["time"] == NOW + 1, "a repeat of the last copy changes nothing"
    assert _texts(history) == ["two", "one"]


def test_older_duplicate_moves_to_the_top():
    history = _history(["one", "two", "three"])
    first_id = history.items[-1]["id"]
    item, status = history.add("one", NOW + 50)
    assert status == "moved" and item["id"] == first_id
    assert item["time"] == NOW + 50
    assert _texts(history) == ["one", "three", "two"]
    assert len(history) == 3


def test_trim_drops_the_oldest_unpinned_items():
    history = _history([f"item {n}" for n in range(30)], limit=25)
    assert len(history) == 25
    assert _texts(history)[0] == "item 29"
    assert _texts(history)[-1] == "item 5"
    assert "item 4" not in _texts(history)


def test_pinned_items_are_never_trimmed_and_stay_on_top():
    history = _history(["keep A", "keep B"], limit=25)
    for item in list(history.items):
        history.toggle_pin(item["id"])
    for n in range(60):
        history.add(f"copy {n}", NOW + 100 + n)
    assert len(history) == 27
    assert history.pinned_count() == 2
    assert [i["pinned"] for i in history.items[:2]] == [True, True]
    assert sorted(_texts(history)[:2]) == ["keep A", "keep B"]
    assert _texts(history)[2] == "copy 59" and _texts(history)[-1] == "copy 35"


def test_recopying_a_pinned_item_keeps_it_pinned_at_the_top():
    history = _history(["pinned", "a", "b"])
    pinned = history.find_text("pinned")
    history.toggle_pin(pinned["id"])
    history.add("c", NOW + 10)
    item, status = history.add("pinned", NOW + 20)
    assert status == "moved" and item["pinned"]
    assert _texts(history) == ["pinned", "c", "b", "a"]


def test_pin_and_unpin_move_to_the_top_of_their_group():
    history = _history(["a", "b", "c", "d"])
    history.toggle_pin(history.find_text("a")["id"])
    history.toggle_pin(history.find_text("c")["id"])
    assert _texts(history) == ["c", "a", "d", "b"]
    item = history.toggle_pin(history.find_text("a")["id"])
    assert item["pinned"] is False
    assert _texts(history) == ["c", "a", "d", "b"]
    assert [i["pinned"] for i in history.items] == [True, False, False, False]
    assert history.toggle_pin("missing") is None


def test_unpinning_when_full_trims_the_oldest():
    history = _history([f"n{n}" for n in range(25)], limit=25)
    history.toggle_pin(history.find_text("n0")["id"])
    history.add("new", NOW + 100)
    assert len(history) == 26
    history.toggle_pin(history.find_text("n0")["id"])
    assert len(history) == 25 and "n0" in _texts(history)
    assert "n1" not in _texts(history), "the oldest unpinned item goes"


def test_delete_clear_and_limit():
    history = _history(["a", "b", "c", "d"])
    history.toggle_pin(history.find_text("b")["id"])
    assert history.delete(history.find_text("c")["id"])["text"] == "c"
    assert history.delete("missing") is None
    assert history.clear() == (2, 1)
    assert _texts(history) == ["b"]
    history = _history([f"n{n}" for n in range(60)], limit=100)
    assert history.set_limit(25) == 35 and len(history) == 25
    assert history.set_limit(7) == 0 and history.limit == store.DEFAULT_SIZE


def test_latest_is_the_most_recent_copy_even_below_pins():
    history = _history(["old", "newest"])
    history.toggle_pin(history.find_text("old")["id"])
    assert _texts(history)[0] == "old"
    assert history.latest()["text"] == "newest"
    assert store.History().latest() is None


def test_latest_does_not_depend_on_distinct_timestamps():
    # time.time() on Windows ticks every ~16 ms, and clocks can go backwards.
    history = store.History()
    history.add("first", NOW)
    history.add("second", NOW)
    history.toggle_pin(history.find_text("first")["id"])
    assert history.latest()["text"] == "second"
    assert history.add("second", NOW)[1] == "duplicate"
    assert history.add("first", NOW)[1] == "moved"
    assert history.latest()["text"] == "first"
    history.delete(history.find_text("first")["id"])
    assert history.latest()["text"] == "second"
    history.add("earlier clock", NOW - 100)
    assert history.latest()["text"] == "earlier clock"


def test_snapshot_pinned_only_and_signature():
    history = _history(["a", "b"])
    history.toggle_pin(history.find_text("a")["id"])
    assert [i["text"] for i in history.snapshot(pinned_only=True)] == ["a"]
    snap = history.snapshot()
    assert [i["text"] for i in snap] == ["a", "b"]
    snap[0]["text"] = "changed"
    assert history.items[0]["text"] == "a", "a snapshot is a copy"
    assert store.signature(history.snapshot()) == store.signature(history.snapshot())


def test_normalize_settings():
    assert store.normalize_settings(None) == store.DEFAULT_SETTINGS
    assert store.normalize_settings({"limit": 100, "remember": True, "paused": True}) == \
        {"limit": 100, "remember": True, "paused": True}
    assert store.normalize_settings({"limit": 7, "remember": "yes", "paused": 1}) == \
        store.DEFAULT_SETTINGS
    assert store.normalize_settings({"limit": True})["limit"] == store.DEFAULT_SIZE


def test_normalize_items_repairs_saved_data():
    raw = {"items": [
        {"id": "a", "text": "first", "time": NOW, "pinned": False},
        {"id": "b", "text": "pinned", "time": NOW - 5, "pinned": True},
        {"id": "a", "text": "same id", "time": "yesterday"},
        {"id": "d", "text": "first", "time": NOW},          # duplicate text
        {"id": "e", "text": "   "},
        {"id": "f", "text": "x" * (store.MAX_TEXT_BYTES + 1)},
        {"id": "g", "text": "inf", "time": float("inf")},
        "junk", None,
    ]}
    items = store.normalize_items(raw, 25, now=NOW)
    assert [i["text"] for i in items] == ["pinned", "first", "same id", "inf"]
    assert items[0]["pinned"] and not items[1]["pinned"]
    assert items[2]["id"] != "a" and items[2]["time"] == NOW
    assert items[3]["time"] == NOW
    assert store.normalize_items("nonsense") == []
    many = {"items": [{"id": str(n), "text": f"t{n}", "time": NOW - n} for n in range(40)]}
    assert len(store.normalize_items(many, 25, now=NOW)) == 25


def test_writer_writes_the_newest_snapshot_once_the_current_one_is_done():
    written, started, release = [], threading.Event(), threading.Event()

    def slow_write(snapshot):
        started.set()
        release.wait(5)
        written.append(snapshot)

    writer = store.Writer(slow_write)
    writer.submit(["first"])
    assert started.wait(5)
    writer.submit(["second"])
    writer.submit(["third"])
    assert not writer.flush(0.05), "still writing"
    release.set()
    assert writer.flush(5)
    assert written == [["first"], ["third"]]


# --------------------------------------------------------------------------- #
# Password managers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("formats, dword, expected", [
    ({}, None, False),
    ({guard.EXCLUDE_FORMAT}, None, True),
    ({guard.VIEWER_IGNORE_FORMAT}, None, True),
    ({guard.HISTORY_FORMAT}, 0, True),
    ({guard.HISTORY_FORMAT}, 1, False),
    ({guard.HISTORY_FORMAT}, None, True),      # unreadable: do not record
    ({guard.HISTORY_FORMAT, guard.EXCLUDE_FORMAT}, 1, True),
])
def test_private_decision(formats, dword, expected):
    reads = []

    def read_dword(name):
        reads.append(name)
        return dword

    assert guard.is_private(lambda name: name in formats, read_dword) is expected
    if guard.HISTORY_FORMAT not in formats:
        assert not reads, "the clipboard is only opened when the DWORD is there"


class FakeUser32:
    def __init__(self, formats=(), open_ok=True, handle=0x1234):
        self.formats = set(formats)
        self.ids = {}
        self.registered = []
        self.open_ok = open_ok
        self.handle = handle
        self.opened = self.closed = 0

    def _name(self, format_id):
        return next((n for n, i in self.ids.items() if i == format_id), None)

    def RegisterClipboardFormatW(self, name):
        self.registered.append(name)
        return self.ids.setdefault(name, 0xC100 + len(self.ids))

    def IsClipboardFormatAvailable(self, format_id):
        return self._name(format_id) in self.formats

    def OpenClipboard(self, hwnd):
        self.opened += 1
        return self.open_ok

    def CloseClipboard(self):
        self.closed += 1
        return True

    def GetClipboardData(self, format_id):
        return self.handle if self._name(format_id) in self.formats else None


class FakeKernel32:
    def __init__(self, value=0, size=4, lock_error=None):
        self.buffer = ctypes.c_uint32(value)
        self.size = size
        self.lock_error = lock_error
        self.unlocked = 0

    def GlobalLock(self, handle):
        if self.lock_error:
            raise self.lock_error
        return ctypes.addressof(self.buffer)

    def GlobalUnlock(self, handle):
        self.unlocked += 1
        return True

    def GlobalSize(self, handle):
        return self.size


def test_windows_check_reads_the_dword_and_always_closes_the_clipboard():
    user32, kernel32 = FakeUser32({guard.HISTORY_FORMAT}), FakeKernel32(value=0)
    clip = guard.WindowsClipboard(user32, kernel32)
    assert clip.is_private() is True
    assert (user32.opened, user32.closed, kernel32.unlocked) == (1, 1, 1)

    kernel32.buffer.value = 1
    assert clip.is_private() is False
    assert user32.closed == 2
    assert user32.registered.count(guard.HISTORY_FORMAT) == 1, "format ids are cached"


def test_windows_check_without_formats_never_opens_the_clipboard():
    user32 = FakeUser32()
    assert guard.WindowsClipboard(user32, FakeKernel32()).is_private() is False
    assert user32.opened == 0


def test_windows_check_excluded_format_needs_no_open():
    user32 = FakeUser32({guard.EXCLUDE_FORMAT})
    assert guard.WindowsClipboard(user32, FakeKernel32()).is_private() is True
    assert user32.opened == 0


def test_windows_check_fails_safe():
    busy = FakeUser32({guard.HISTORY_FORMAT}, open_ok=False)
    assert guard.WindowsClipboard(busy, FakeKernel32(value=1)).is_private() is True
    assert busy.closed == 0, "never close a clipboard that was not opened"

    small = FakeUser32({guard.HISTORY_FORMAT})
    assert guard.WindowsClipboard(small, FakeKernel32(value=1, size=2)).is_private() is True
    assert small.closed == 1

    no_data = FakeUser32({guard.HISTORY_FORMAT}, handle=None)
    assert guard.WindowsClipboard(no_data, FakeKernel32(value=1)).is_private() is True
    assert no_data.closed == 1


def test_windows_check_closes_the_clipboard_when_a_call_fails():
    user32 = FakeUser32({guard.HISTORY_FORMAT})
    with pytest.raises(OSError):
        guard.WindowsClipboard(user32, FakeKernel32(lock_error=OSError("locked"))).is_private()
    assert user32.closed == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows clipboard API")
def test_real_windows_api_uses_private_handles():
    shared = ctypes.windll.user32.RegisterClipboardFormatW
    before = shared.argtypes
    clip = guard.WindowsClipboard()
    assert clip.available
    assert clip._user32 is not ctypes.windll.user32
    assert clip._user32.RegisterClipboardFormatW is not shared
    assert clip._user32.RegisterClipboardFormatW.argtypes is not None
    assert shared.argtypes is before, "the shared ctypes.windll object was changed"
    # Only looks at the clipboard (it is opened at most to read one DWORD).
    assert clip.is_private() in (True, False)
    assert clip._format_id(guard.EXCLUDE_FORMAT) >= 0xC000


# --------------------------------------------------------------------------- #
# The extension: events, copy-back, saving
# --------------------------------------------------------------------------- #
class FakeGuard:
    private = False

    def is_private(self):
        return self.private


class Harness:
    def __init__(self, monkeypatch):
        import core.api
        from core.events import EventBus
        self.monkeypatch = monkeypatch
        self.bus = EventBus()
        self.spoken = []
        self.clipboard = []
        self.guard = FakeGuard()
        monkeypatch.setattr(core.api, "set_clipboard",
                            lambda value: self.clipboard.append(value) or True)
        self.main = None
        self.start()

    def start(self):
        spec = importlib.util.spec_from_file_location(
            "clipboard_history_main_under_test", os.path.join(EXT_DIR, "main.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.monkeypatch.setattr(module, "speak",
                                 lambda message, interrupt=False: self.spoken.append(message))
        module.register(self.bus)
        module._guard = self.guard
        self.main = module
        return module

    def restart(self):
        self.main.teardown()
        return self.start()

    def copy(self, value):
        self.bus.emit("on_clipboard_changed", value)

    def texts(self):
        return [i["text"] for i in self.main._history.items]

    def saved(self):
        self.main._writer.flush(5)
        path = store.items_path()
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return [i["text"] for i in json.load(f)["items"]]

    def backup_exists(self):
        self.main._writer.flush(5)
        return os.path.exists(store.items_path() + ".bak")


@pytest.fixture
def ext(tmp_data_dir, monkeypatch):
    import core.hotkeys
    import core.preferences
    actions_before = dict(core.hotkeys.actions)
    panels_before = {k: list(v) for k, v in core.preferences._panels.items()}
    harness = Harness(monkeypatch)
    yield harness
    harness.main.teardown()
    core.hotkeys.actions.clear()
    core.hotkeys.actions.update(actions_before)
    core.hotkeys._rebuild_all_bindings()
    core.preferences._panels.clear()
    core.preferences._panels.update(panels_before)


def test_copies_are_recorded_by_the_rules(ext):
    for value in ["one", "two", "", "  ", "two", "x" * (store.MAX_TEXT_BYTES + 1), "one"]:
        ext.copy(value)
    assert ext.texts() == ["one", "two"]
    ext.bus.emit("on_clipboard_changed", None)
    assert ext.texts() == ["one", "two"]


def test_nothing_is_recorded_while_paused(ext):
    ext.main.apply_settings(dict(ext.main.get_settings(), paused=True))
    ext.copy("secret meeting notes")
    assert ext.texts() == []
    ext.main.apply_settings(dict(ext.main.get_settings(), paused=False))
    ext.copy("hello")
    assert ext.texts() == ["hello"]


def test_password_manager_copies_are_skipped(ext):
    ext.guard.private = True
    ext.copy("hunter2")
    assert ext.texts() == []
    ext.guard.private = False
    ext.copy("hello")
    assert ext.texts() == ["hello"]


def test_a_failing_check_counts_as_private(ext):
    class Broken:
        def is_private(self):
            raise OSError("clipboard busy")

    ext.main._guard = Broken()
    ext.copy("maybe secret")
    assert ext.texts() == []


def test_copy_back_is_not_recorded_as_a_new_copy(ext):
    ext.copy("alpha")
    ext.copy("beta")
    alpha = ext.main._history.find_text("alpha")
    stamp = alpha["time"]
    assert ext.main.copy_item(alpha["id"]) is True
    assert ext.clipboard == ["alpha"]
    ext.copy("alpha")                     # the main window sees our own change
    assert ext.texts() == ["beta", "alpha"] and alpha["time"] == stamp
    ext.copy("gamma")
    ext.copy("alpha")                     # a real copy later on is recorded
    assert ext.texts() == ["alpha", "gamma", "beta"]
    assert ext.main.copy_item("missing") is False


def test_copy_back_only_skips_the_next_event(ext):
    ext.copy("alpha")
    ext.copy("beta")
    ext.main.copy_item(ext.main._history.find_text("alpha")["id"])
    ext.copy("gamma")                     # someone copied before the poll saw ours
    ext.copy("alpha")
    assert ext.texts() == ["alpha", "gamma", "beta"]


def test_copy_back_expires(ext):
    ext.copy("alpha")
    ext.copy("beta")
    ext.main.copy_item(ext.main._history.find_text("alpha")["id"])
    ext.main._ignore = ("alpha", time.time() - 1)
    ext.copy("alpha")
    assert ext.texts() == ["alpha", "beta"]


def test_copy_back_matches_line_ending_changes(ext):
    ext.copy("line one\nline two")
    ext.copy("other")
    ext.main.copy_item(ext.main._history.find_text("line one\nline two")["id"])
    ext.copy("line one\r\nline two")
    assert ext.texts() == ["other", "line one\nline two"]


def test_failed_copy_back_does_not_leave_an_ignore(ext, monkeypatch):
    import core.api
    monkeypatch.setattr(core.api, "set_clipboard", lambda value: False)
    ext.copy("alpha")
    ext.copy("beta")
    assert ext.main.copy_item(ext.main._history.find_text("alpha")["id"]) is False
    assert ext.main._ignore is None


def test_history_stays_in_memory_by_default(ext):
    ext.copy("one")
    ext.copy("two")
    assert ext.saved() is None, "nothing on disk while Remember is off"
    settings = store.load_settings()
    assert settings == store.DEFAULT_SETTINGS
    raw = json.dumps(ext.main.get_settings())
    assert "one" not in raw


def test_pinned_items_are_saved_even_when_remember_is_off(ext):
    for value in ["one", "two", "three"]:
        ext.copy(value)
    two = ext.main._history.find_text("two")
    ext.main.toggle_pin(two["id"])
    assert ext.saved() == ["two"]
    assert not ext.backup_exists()
    ext.copy("four")
    assert ext.saved() == ["two"]
    ext.main.toggle_pin(two["id"])
    assert ext.saved() is None, "unpinning the last pin deletes the file"
    assert not ext.backup_exists()


def test_remember_on_saves_everything_and_off_deletes_it_at_once(ext):
    for value in ["one", "two", "three"]:
        ext.copy(value)
    ext.main.toggle_pin(ext.main._history.find_text("one")["id"])
    ext.main.apply_settings(dict(ext.main.get_settings(), remember=True))
    assert ext.saved() == ["one", "three", "two"]
    ext.copy("four")
    assert ext.saved() == ["one", "four", "three", "two"]

    # Switching off must not wait for anything else: check without flushing.
    ext.main.apply_settings(dict(ext.main.get_settings(), remember=False))
    with open(store.items_path(), encoding="utf-8") as f:
        assert [i["text"] for i in json.load(f)["items"]] == ["one"]
    assert not os.path.exists(store.items_path() + ".bak"), "the backup kept the old history"

    ext.main.clear_history()
    ext.main.delete_item(ext.main._history.find_text("one")["id"])
    ext.main.apply_settings(dict(ext.main.get_settings(), remember=True))
    ext.main.apply_settings(dict(ext.main.get_settings(), remember=False))
    assert not os.path.exists(store.items_path())


def test_restart_keeps_only_what_should_survive(ext):
    for value in ["one", "two", "three"]:
        ext.copy(value)
    ext.main.toggle_pin(ext.main._history.find_text("two")["id"])
    ext.restart()
    assert ext.texts() == ["two"]

    ext.copy("four")
    ext.main.apply_settings(dict(ext.main.get_settings(), remember=True))
    ext.restart()
    assert ext.texts() == ["two", "four"]
    assert ext.main.get_settings()["remember"] is True


def test_unpinned_items_left_on_disk_are_pruned_at_startup(ext):
    ext.main._writer.flush(5)
    ext.main.teardown()
    stale = [store.make_item("pinned", NOW, pinned=True), store.make_item("left behind", NOW)]
    import core.api
    core.api.save_data(store.ITEMS_KEY, {"version": 1, "items": stale})
    assert os.path.exists(store.items_path() + ".bak") is False
    core.api.save_data(store.ITEMS_KEY, {"version": 1, "items": stale})
    assert os.path.exists(store.items_path() + ".bak")
    ext.start()
    assert ext.texts() == ["pinned"]
    assert ext.saved() == ["pinned"]
    assert not ext.backup_exists()


def test_history_size_setting_trims(ext):
    ext.main.apply_settings({"limit": 100, "remember": True, "paused": False})
    for n in range(80):
        ext.copy(f"copy {n}")
    assert len(ext.texts()) == 80
    ext.main.apply_settings({"limit": 25, "remember": True, "paused": False})
    assert len(ext.texts()) == 25 and ext.texts()[0] == "copy 79"
    assert len(ext.saved()) == 25
    assert store.load_settings()["limit"] == 25


def test_speak_last(ext):
    ext.main.speak_last()
    assert ext.spoken[-1] == text._("history_empty")
    ext.copy("first")
    ext.copy("second")
    ext.main.toggle_pin(ext.main._history.find_text("first")["id"])
    ext.main.speak_last()
    assert ext.spoken[-1] == "second"
    ext.copy("y" * 5000)
    ext.main.speak_last()
    assert ext.spoken[-1].startswith("y" * text.SPEAK_CHARS)
    assert ext.spoken[-1].endswith(text._("speak_truncated"))


def test_hotkeys_and_teardown(ext):
    import core.hotkeys
    open_action = core.hotkeys.actions["Clipboard History.open_history"]
    speak_action = core.hotkeys.actions["Clipboard History.speak_last"]
    assert (open_action.default_keycode, open_action.default_ctrl, open_action.default_shift,
            open_action.default_alt, open_action.default_global) == (ord("V"), False, False, False, False)
    assert (speak_action.default_keycode, speak_action.default_ctrl, speak_action.default_shift,
            speak_action.default_global) == (ord("V"), False, True, False)
    ext.main.teardown()
    assert ext.main._on_clipboard_changed not in ext.bus._listeners.get("on_clipboard_changed", [])
    ext.copy("after teardown")
    assert ext.texts() == []


def _literal(node):
    """ord("V") -> 86, wx.WXK_F1 -> "WXK_F1", True/False/None as is, else a marker."""
    if isinstance(node, ast.Constant):
        return node.value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ord"
            and node.args and isinstance(node.args[0], ast.Constant)):
        return ord(node.args[0].value)
    if isinstance(node, ast.Attribute):
        return node.attr
    return "<dynamic>"


def _default_bindings(source, origin):
    found = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return found    # a file mid-edit; other tests report syntax errors
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "register_action":
            continue
        kw = {k.arg: k.value for k in node.keywords}
        key = node.args[3] if len(node.args) > 3 else kw.get("default_keycode")
        ctrl = node.args[4] if len(node.args) > 4 else kw.get("default_ctrl")
        keycode = _literal(key) if key is not None else None
        if keycode in (None, "<dynamic>"):
            continue
        mods = tuple(bool(_literal(kw[m])) if m in kw else False
                     for m in ("default_shift", "default_alt", "default_win"))
        found.append(((keycode, bool(_literal(ctrl)) if ctrl is not None else False) + mods, origin))
    return found


def test_default_keys_do_not_clash_with_the_core_or_other_extensions():
    bindings = []
    with open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8") as f:
        bindings += _default_bindings(f.read(), "core")
    for entry in sorted(os.listdir(EXT_ROOT)):
        path = os.path.join(EXT_ROOT, entry)
        if os.path.isdir(path):
            for name in os.listdir(path):
                if name.endswith(".py"):
                    with open(os.path.join(path, name), encoding="utf-8") as f:
                        bindings += _default_bindings(f.read(), entry)
        elif entry.endswith(".hrk"):
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if name.endswith(".py") and "lib/" not in name:
                        bindings += _default_bindings(z.read(name).decode("utf-8", "replace"),
                                                      entry[:-4])
    ours = {combo for combo, origin in bindings if origin == "clipboard_history"}
    assert ours == {(ord("V"), False, False, False, False), (ord("V"), False, True, False, False)}
    clashes = [(combo, origin) for combo, origin in bindings
               if combo in ours and origin != "clipboard_history"]
    assert not clashes, clashes


# --------------------------------------------------------------------------- #
# Text in both languages
# --------------------------------------------------------------------------- #
@pytest.fixture
def lang(monkeypatch):
    from core import i18n
    had_core, old_core = "core" in i18n._language_cache, i18n._language_cache.get("core")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("en")
    yield set_lang
    if had_core:
        i18n._language_cache["core"] = old_core
    else:
        i18n._language_cache.pop("core", None)


def test_preview_is_one_line():
    assert text.preview("  first line \n\n  second\tline  \r\nthird ") == \
        "first line / second line / third"
    assert text.preview("x" * 200) == "x" * 120 + "…"
    assert text.preview("short") == "short"
    long_lines = "\n".join(["a"] * 2000)
    assert text.preview(long_lines).endswith("…") and len(text.preview(long_lines)) <= 121
    assert text.preview("word " * 10 + "\n" * 5000 + "tail").endswith("…")


@pytest.mark.parametrize("seconds, en, id_", [
    (0, "just now", "baru saja"),
    (59, "just now", "baru saja"),
    (-30, "just now", "baru saja"),
    (60, "1 minute ago", "1 menit yang lalu"),
    (125, "2 minutes ago", "2 menit yang lalu"),
    (3600, "1 hour ago", "1 jam yang lalu"),
    (5 * 3600 + 59, "5 hours ago", "5 jam yang lalu"),
    (86400, "1 day ago", "1 hari yang lalu"),
    (3 * 86400, "3 days ago", "3 hari yang lalu"),
])
def test_relative_times(lang, seconds, en, id_):
    assert text.ago(NOW - seconds, NOW) == en
    lang("id")
    assert text.ago(NOW - seconds, NOW) == id_


def test_old_items_show_the_date(lang):
    then = datetime.datetime(2026, 8, 3, 12, 0).timestamp()
    now = datetime.datetime(2026, 9, 23, 12, 0).timestamp()
    assert text.ago(then, now) == "on 3 August 2026"
    lang("id")
    assert text.ago(then, now) == "pada 3 Agustus 2026"


def test_rows_in_both_languages(lang):
    item = {"id": "a", "text": "Dear team,\nsee you at 9", "time": NOW - 120, "pinned": False}
    assert text.row(item, NOW) == "Dear team, / see you at 9, 2 minutes ago"
    item["pinned"] = True
    assert text.row(item, NOW) == "Pinned: Dear team, / see you at 9, 2 minutes ago"
    lang("id")
    assert text.row(item, NOW) == "Disematkan: Dear team, / see you at 9, 2 menit yang lalu"
    item["pinned"] = False
    assert text.row(item, NOW) == "Dear team, / see you at 9, 2 menit yang lalu"
    assert text.count_text(1) == "1 item" and text.count_text(4) == "4 item"


def test_row_keeps_braces_in_copied_text(lang):
    item = {"id": "a", "text": "def f(): return {x}", "time": NOW, "pinned": False}
    assert text.row(item, NOW) == "def f(): return {x}, just now"


def test_locales_have_the_same_keys():
    with open(os.path.join(EXT_DIR, "locales", "en.json"), encoding="utf-8") as f:
        en = json.load(f)["messages"]
    with open(os.path.join(EXT_DIR, "locales", "id.json"), encoding="utf-8") as f:
        id_ = json.load(f)["messages"]
    assert set(en) == set(id_)
