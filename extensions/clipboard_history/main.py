# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Clipboard History — Hariku V2 extension.

Records the text copied to the clipboard so it can be found, pinned and copied
again. The main window already polls the clipboard once a second and emits
"on_clipboard_changed"; this extension only listens to that event.

  clipboard_history_store.py - the history, the rules, saving (no wx)
  clipboard_history_guard.py - is the clipboard marked private (password managers)?
  clipboard_history_text.py  - previews, "2 minutes ago", list rows
  clipboard_history_ui.py    - the history dialog and the Preferences page

Not recorded: empty text, text over 100 KB, a repeat of the last copy, copies
marked private by the app that made them, anything while recording is paused,
and Hariku's own "Copy" from the history. The history lives in memory unless
"Remember history" is on; pinned items are always saved. Hariku never pastes
into other apps.
"""

import logging
import time

import wx

import core.api
import core.hotkeys
import core.preferences
from core.speech import speak

import clipboard_history_guard as guard
import clipboard_history_store as store
import clipboard_history_text as text
import clipboard_history_ui as ui
from clipboard_history_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Clipboard History"   # fixed, so action ids stay the same in every language
IGNORE_SECONDS = 10              # how long our own copy-back waits to be seen
FLUSH_SECONDS = 3.0

_bus = None
_active = False
_settings = dict(store.DEFAULT_SETTINGS)
_history = store.History()
_writer = None
_guard = None
_ignore = None           # (text, deadline) of our own copy-back
_saved_signature = None  # what the items file holds now
_panel = None
_dialog = None


# ------------------------------------------------------------
# Recording
# ------------------------------------------------------------

def _same_text(a, b):
    return a == b or a.replace("\r\n", "\n") == b.replace("\r\n", "\n")


def _consume_ignore(clip_text):
    """True if this change is the copy-back Hariku just made. Only the next
    change event is checked, and only for IGNORE_SECONDS."""
    global _ignore
    if _ignore is None:
        return False
    expected, deadline = _ignore
    _ignore = None
    return time.time() <= deadline and _same_text(clip_text, expected)


def _is_private():
    try:
        return _guard is not None and _guard.is_private()
    except Exception as e:
        # When in doubt, do not record.
        logger.warning(f"[Clipboard History] Clipboard check failed, copy skipped: {e}")
        return True


def _on_clipboard_changed(clip_text=None, *_args, **_kwargs):
    """Runs on the UI thread once a second at most: keep it cheap."""
    if not _active or not isinstance(clip_text, str):
        return
    if _consume_ignore(clip_text) or _settings["paused"]:
        return
    if store.text_problem(clip_text) or _is_private():
        return
    _item, status = _history.add(clip_text, time.time())
    if status in ("added", "moved"):
        _persist()
        if _dialog is not None:
            wx.CallAfter(_refresh_dialog)


def _refresh_dialog():
    if _dialog:
        _dialog.refresh()


# ------------------------------------------------------------
# Saving
# ------------------------------------------------------------

def _persist(force=False):
    """Hand the part of the history that belongs on disk to the writer thread:
    everything when "Remember history" is on, otherwise only pinned items."""
    global _saved_signature
    if _writer is None:
        return
    snapshot = _history.snapshot(pinned_only=not _settings["remember"])
    sig = store.signature(snapshot)
    if sig == _saved_signature and not force:
        return
    _saved_signature = sig
    _writer.submit(snapshot)


def apply_settings(new_settings):
    global _settings
    new_settings = store.normalize_settings(new_settings)
    was_remembering = _settings["remember"]
    _settings = new_settings
    store.save_settings(new_settings)
    _history.set_limit(new_settings["limit"])
    _persist()
    if was_remembering and not new_settings["remember"] and _writer is not None:
        # Turning Remember off deletes the saved history now, not at exit.
        _writer.flush(FLUSH_SECONDS)


def get_settings():
    return dict(_settings)


# ------------------------------------------------------------
# What the dialog may do
# ------------------------------------------------------------

def copy_item(item_id):
    """Put an item back on the clipboard without recording it as a new copy."""
    global _ignore
    item = _history.find(item_id)
    if item is None:
        return False
    _ignore = (item["text"], time.time() + IGNORE_SECONDS)
    if not core.api.set_clipboard(item["text"]):
        _ignore = None
        return False
    return True


def toggle_pin(item_id):
    item = _history.toggle_pin(item_id)
    if item is not None:
        _persist()
    return item


def delete_item(item_id):
    item = _history.delete(item_id)
    if item is not None:
        _persist()
    return item


def clear_history():
    result = _history.clear()
    _persist()
    return result


class DialogActions:
    items = staticmethod(lambda: list(_history.items))
    latest = staticmethod(lambda: _history.latest())
    copy = staticmethod(copy_item)
    toggle_pin = staticmethod(toggle_pin)
    delete = staticmethod(delete_item)
    clear = staticmethod(clear_history)
    is_paused = staticmethod(lambda: _settings["paused"])


# ------------------------------------------------------------
# Hotkey actions
# ------------------------------------------------------------

def show_history():
    global _dialog
    if _dialog:
        _dialog.Raise()     # already open (a global hotkey can fire during it)
        return
    parent = getattr(core.api, "main_window_instance", None)
    dlg = ui.HistoryDialog(parent, DialogActions)
    _dialog = dlg
    try:
        dlg.ShowModal()
    finally:
        _dialog = None
        dlg.Destroy()


def speak_last():
    item = _history.latest()
    if item is None:
        speak(_("history_empty"), interrupt=True)
        return
    speak(text.speakable(item["text"]), interrupt=True)


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _create_panel(parent):
    global _panel
    _panel = ui.SettingsPanel(parent, _settings)
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        new_settings = _panel.get_settings()
    except RuntimeError:
        return  # panel already destroyed
    apply_settings(new_settings)


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

_SUBSCRIPTIONS = (
    ("on_clipboard_changed", _on_clipboard_changed),
)


def _unsubscribe(bus, event_name, handler):
    unsubscribe = getattr(bus, "unsubscribe", None)
    if callable(unsubscribe):
        unsubscribe(event_name, handler)
        return
    listeners = getattr(bus, "_listeners", {}).get(event_name)   # older cores
    if listeners and handler in listeners:
        listeners.remove(handler)


def register(bus):
    global _bus, _active, _settings, _history, _writer, _guard, _ignore, _saved_signature
    _bus = bus
    _settings = store.load_settings()
    on_disk = store.load_items(_settings["limit"])
    keep = on_disk if _settings["remember"] else [i for i in on_disk if i["pinned"]]
    _history = store.History(_settings["limit"], [dict(i) for i in keep])
    _ignore = None
    _saved_signature = store.signature(on_disk)
    _writer = store.Writer(store.write_items)
    _guard = guard.WindowsClipboard()
    store.remove_backup()   # may hold text deleted since
    _persist()              # drops unpinned items left on disk while Remember is off
    _active = True

    for event_name, handler in _SUBSCRIPTIONS:
        bus.subscribe(event_name, handler)

    # V and Shift+V are free in the core and in every bundled extension.
    core.hotkeys.register_action(EXT_NAME, "open_history", _("action_open"),
                                 ord("V"), False, show_history)
    core.hotkeys.register_action(EXT_NAME, "speak_last", _("action_speak_last"),
                                 ord("V"), False, speak_last, default_shift=True)
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    logger.info("Clipboard History extension loaded.")


def teardown():
    global _active, _ignore, _panel
    _active = False
    _ignore = None
    _panel = None
    if _bus is not None:
        for event_name, handler in _SUBSCRIPTIONS:
            try:
                _unsubscribe(_bus, event_name, handler)
            except Exception:
                pass
    if _writer is not None and not _writer.flush(FLUSH_SECONDS):
        logger.warning("[Clipboard History] The last save did not finish in time.")
    logger.info("Clipboard History extension unloaded.")
