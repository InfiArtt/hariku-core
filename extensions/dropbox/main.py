# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Dropbox — Hariku V2 extension: hear what Dropbox is doing, and copy links.

  * Your files: "Menyinkronkan laporan.pdf ke Dropbox…", "laporan.pdf sudah
    tersinkron.", "Dropbox-mu sudah up to date.", and a gentle word when a
    file still hasn't synced after a few minutes.
  * Other people: "Budi menambahkan catatan.txt ke folder Kelas." (changes in
    shared folders) and "Budi membagikan tugas.docx denganmu."
  * Links: in File Explorer, on a file in the Dropbox folder, say "salin
    link" (or "copy link") to Aruna, or press the key you gave "Copy the
    Dropbox link..." in Input Gestures (no key by default): the file's shared
    link is copied. "salin link laporan" finds a file by name. "status
    dropbox" says whether everything has synced.

  dropbox_api.py       the HTTP API, signing in (PKCE), APP_KEY
  dropbox_auth.py      the browser sign-in and its 127.0.0.1 listener
  dropbox_secret.py    the sign-in kept encrypted (Windows DPAPI)
  dropbox_paths.py     the Dropbox folder (info.json), paths, file details
  dropbox_watch.py     the folder watcher (ReadDirectoryChangesW)
  dropbox_sync.py      your files: syncing, synced, late
  dropbox_remote.py    Dropbox's side: others' changes, shared with you
  dropbox_explorer.py  the file you're on in File Explorer
  dropbox_engine.py    the threads, the account, links, searching
  dropbox_text.py      what is said
  dropbox_ui.py        the Preferences page
  dropbox_sounds.py    makes the sounds in sounds/

Hariku never uploads or reads file contents: the desktop Dropbox app syncs,
and Hariku only asks Dropbox about names, sizes and times, and for links.
"""

import logging
import os

import wx

import core.api
import core.commands
import core.hotkeys
import core.preferences
import core.sounds
from core.commands import Reply
from core.speech import speak

import dropbox_engine as engine_module
import dropbox_explorer as explorer
import dropbox_paths as paths
import dropbox_text as text
import dropbox_ui
from dropbox_text import _

logger = logging.getLogger(__name__)

EXT_NAME = "Dropbox"            # fixed, so saved hotkeys survive a language change
DATA_KEY = "Dropbox"            # settings
ACCOUNT_KEY = "DropboxAccount"  # the account and its encrypted sign-in
SHARED_KEY = "DropboxShared"    # what was already shared with you
EXT_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(EXT_DIR, "sounds")
LINK_INTENT = f"{EXT_NAME}.link"
LINK_PATTERNS = ("salin link {text}", "salin tautan {text}", "bagikan link {text}",
                 "copy link to {text}", "copy the link to {text}", "copy link for {text}",
                 "copy link of {text}", "share link to {text}")
MAX_QUERY = 200

DEFAULT_SETTINGS = {"progress": True, "up_to_date": True, "others": True, "shared": True,
                    "sounds": True}


def normalize_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        if isinstance(raw.get(key), bool):
            settings[key] = raw[key]
    return settings


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

_bus = None
_active = False
_settings = normalize_settings(None)
_engine = None
_panel = None
_listeners = []


def _call_after(fn, *args):
    try:
        if _active and wx.GetApp() is not None:
            wx.CallAfter(fn, *args)
    except Exception:
        pass


def _load(key):
    data = core.api.load_data(key)
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------
# What the engine uses from Hariku
# ------------------------------------------------------------

def _play(sound):
    if sound and _settings.get("sounds", True):
        path = os.path.join(SOUNDS_DIR, f"{sound}.wav")
        if os.path.isfile(path):
            core.sounds.play_sound(path)


def _say_lines(lines):
    for line, sound in lines:
        _play(sound)
        speak(line)


def _deliver_link(url, said_ok, said_failed):
    """On the UI thread: the clipboard, then say so."""
    if core.api.set_clipboard(url):
        _play("synced")
        speak(said_ok)
    else:
        speak(said_failed)


def _quiet():
    try:
        import core.personal
        return bool(core.personal.is_quiet_time())
    except Exception:
        return False


class Services:
    def settings(self):
        return dict(_settings)

    def notify(self, lines):
        if lines:
            _call_after(_say_lines, list(lines))

    def say(self, line):
        if line:
            _call_after(speak, line)

    def deliver_link(self, url, said_ok, said_failed):
        _call_after(_deliver_link, url, said_ok, said_failed)

    def quiet(self):
        return _quiet()

    def changed(self):
        _call_after(_refresh_pages)

    def load_account(self):
        return _load(ACCOUNT_KEY)

    def save_account(self, data):
        core.api.save_data(ACCOUNT_KEY, dict(data or {}))

    def load_shared(self):
        return _load(SHARED_KEY)

    def save_shared(self, data):
        core.api.save_data(SHARED_KEY, dict(data or {}))


# ------------------------------------------------------------
# Actions and Aruna
# ------------------------------------------------------------

def copy_focused_link():
    """The link of the file you're on in File Explorer (the window that has
    the focus: the hotkey's, or the one Aruna gave the focus back to)."""
    if _engine is not None:
        _engine.copy_link_of_window(explorer.foreground_window())


def say_status():
    if _engine is not None:
        speak(_engine.status_text())


def _copy_found(meta):
    if _engine is None:
        return None
    _engine.copy_link_in_background(meta)
    return Reply(wait=True)


def _reply_for(query, outcome):
    kind, value = outcome
    if kind == "one":
        return _copy_found(value)
    if kind == "ask":
        return Reply(_("search_confirm", item=text.item_text(value)),
                     confirm=lambda: _copy_found(value))
    if kind == "many":
        return Reply(_("search_choices", items=text.join_names([text.item_text(m)
                                                                 for m in value])))
    if kind == "none":
        return Reply(_("search_none", query=query))
    return Reply(str(value))


def _on_link_intent(request):
    """ "salin link ini" / "copy the link to this": the file you're on.
    "salin link laporan" / "copy link to the budget": found by name."""
    words = " ".join(str(request.text or "").split())
    if not words or len(words) > MAX_QUERY or _engine is None:
        return None
    problem = _engine.ready_problem()
    if problem:
        return Reply(problem)              # said in Aruna, before going anywhere
    if engine_module.is_deictic(words):
        return Reply(then=copy_focused_link)
    query = engine_module.search_query(words)
    if not query:
        return None
    job = _engine.start_search(query)
    # A search usually answers within a second; waiting that long lets Aruna
    # ask "Did you mean ...?" (a Reply can't be asked later). A slower one
    # answers by itself when it's done.
    outcome = job.wait()
    if outcome is None:
        return Reply(wait=True)
    return _reply_for(query, outcome)


ACTIONS = (
    ("copy_link", "action_copy_link", "title_copy_link", copy_focused_link,
     ("salin link", "salin link ini", "salin link dropbox", "salin tautan", "bagikan link ini",
      "copy link", "copy this link", "copy the link", "copy dropbox link",
      "share this link"), False),
    ("status", "action_status", "title_status", say_status,
     ("dropbox", "status dropbox", "dropbox status", "sinkronisasi dropbox",
      "apakah dropbox sudah up to date", "is dropbox up to date", "dropbox sync status"), True),
)


def action_id(name):
    return f"{EXT_NAME}.{name}"


# ------------------------------------------------------------
# Preferences
# ------------------------------------------------------------

def _account_text():
    if _engine is None:
        return ""
    state = _engine.state
    account = _engine.account or {}
    if state == engine_module.NOT_SET_UP:
        return _("account_not_set_up")
    if state == engine_module.CONNECTED:
        if account.get("email"):
            return _("account_connected", name=account.get("name") or "",
                     email=account["email"])
        return _("account_connected_name", name=account.get("name") or "")
    if state == engine_module.SIGNING_IN:
        return _("account_waiting")
    if state == engine_module.CODE_NEEDED:
        return _("account_waiting_code")
    if state == engine_module.EXCHANGING:
        return _("account_exchanging")
    if state == engine_module.FAILED:
        return _("account_failed", reason=_(f"reason_{_engine.problem or 'failed'}"))
    return _("account_none")


def _folder_text():
    if _engine is None:
        return ""
    if _engine.connected():
        folder = _engine.folder or _engine.local_folder()
        if _engine.folder_state == engine_module.FOLDER_OTHER and _engine.folder:
            return _("folder_other_account", path=_engine.folder)
        if folder and _engine.folder_state in (engine_module.FOLDER_OK,
                                               engine_module.FOLDER_UNKNOWN):
            return folder
        return _("folder_none")
    found = paths.read_info()
    return "; ".join(found[k] for k in ("personal", "business") if k in found) or \
        _("folder_none")


def _view():
    state = _engine.state if _engine is not None else engine_module.NOT_SET_UP
    busy = state in (engine_module.SIGNING_IN, engine_module.CODE_NEEDED,
                     engine_module.EXCHANGING)
    if state == engine_module.CONNECTED:
        button = _("btn_disconnect")
    elif busy:
        button = _("btn_cancel_sign_in")
    else:
        button = _("btn_connect")
    return {"account": _account_text(), "button": button,
            "button_enabled": state != engine_module.NOT_SET_UP,
            "code": state == engine_module.CODE_NEEDED, "folder": _folder_text()}


def _browser_pages():
    return {"done": (_("page_done_title"), _("page_done")),
            "failed": (_("page_failed_title"), _("page_failed"))}


class _PageActions:
    view = staticmethod(_view)

    @staticmethod
    def press():
        if _engine is None:
            return
        if _engine.connected():
            _engine.disconnect()
            speak(_("disconnected"))
        elif _engine.signing_in():
            _engine.cancel_sign_in()
        else:
            _engine.sign_in(pages=_browser_pages())

    @staticmethod
    def give_code(code):
        if _engine is not None:
            _engine.give_code(code)

    @staticmethod
    def add_listener(fn):
        if fn not in _listeners:
            _listeners.append(fn)

    @staticmethod
    def remove_listener(fn):
        if fn in _listeners:
            _listeners.remove(fn)


def _refresh_pages():
    for fn in list(_listeners):
        try:
            fn()
        except RuntimeError:
            _PageActions.remove_listener(fn)       # the page is gone
        except Exception:
            logger.exception("[Dropbox] Updating the page failed")


def _create_panel(parent):
    global _panel
    _panel = dropbox_ui.DropboxPanel(parent, dict(_settings), _PageActions)
    return _panel


def _apply_panel():
    if not _panel:
        return
    try:
        new = _panel.get_settings()
    except RuntimeError:
        return          # the page is gone
    _settings.update(normalize_settings(dict(_settings, **new)))
    data = _load(DATA_KEY)
    data.update(_settings)
    core.api.save_data(DATA_KEY, data)


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def _on_unload(*_args, **_kwargs):
    if _engine is not None:
        _engine.shutdown()


def register(bus):
    global _bus, _active, _settings, _engine, _panel
    _bus = bus
    _active = True
    _panel = None
    _settings = normalize_settings(core.api.load_data(DATA_KEY))
    _engine = engine_module.Engine(Services())

    bus.subscribe("on_unload", _on_unload)
    core.commands.add_intent(LINK_INTENT, list(LINK_PATTERNS), _on_link_intent,
                             title=_("title_link"))
    for name, description, title, callback, aliases, _answers in ACTIONS:
        core.hotkeys.register_action(EXT_NAME, name, _(description), None, False, callback)
        core.commands.add_aliases(action_id(name), list(aliases), title=_(title))
    core.commands.add_answer_actions([action_id(name) for name, *_rest, answers in ACTIONS
                                      if answers])
    core.preferences.register_panel(_("ext_name"), "", _create_panel, _apply_panel)
    # Only reads the stored sign-in; everything that asks Dropbox runs on the
    # engine's own threads.
    try:
        _engine.load()
    except Exception:
        logger.exception("[Dropbox] Starting failed")
    logger.info("Dropbox extension loaded.")


def teardown():
    global _active, _panel, _engine
    try:
        _on_unload()
    except Exception:
        logger.exception("[Dropbox] Stopping failed")
    _active = False
    _panel = None
    _engine = None
    _listeners.clear()
    try:
        core.commands.remove_intent(LINK_INTENT)
    except Exception:
        pass
    for name, *_rest in ACTIONS:
        try:
            core.commands.remove_aliases(action_id(name))
        except Exception:
            pass
    if _bus is not None:
        try:
            _bus.unsubscribe("on_unload", _on_unload)
        except Exception:
            pass
    logger.info("Dropbox extension unloaded.")
