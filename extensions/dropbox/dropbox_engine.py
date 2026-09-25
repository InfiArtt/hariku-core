# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The Dropbox extension's machinery, with no wx: the account, signing in and
out, and while signed in four threads:

  dropbox-sync     every half second: the files you changed (dropbox_sync),
                   others' changes gathered into lines (dropbox_remote)
  dropbox-watch    the folder watcher (dropbox_watch), when the desktop app's
                   folder is on this computer and belongs to this account
  dropbox-remote   the long poll for changes on Dropbox's side
  dropbox-shared   every few minutes: what was shared with you

Links (copy the one of the file you're on, or of a file found by name) run
on short worker threads. Everything the user hears goes through
services.notify() / services.say(), which main.py hands to the UI thread.
"""

import difflib
import logging
import os
import re
import threading
import time
import unicodedata

import dropbox_api
import dropbox_auth
import dropbox_explorer as explorer
import dropbox_paths as paths
import dropbox_remote as remote
import dropbox_secret as secret
import dropbox_sync as sync
import dropbox_text as text
import dropbox_watch
from dropbox_text import _

logger = logging.getLogger(__name__)

TICK = 0.5
PREPARE_RETRY = 60.0         # couldn't reach Dropbox at the start: try again after this
WATCH_RETRY = 60.0           # the folder watcher stopped: look again after this
SHARED_FIRST = 20.0          # first look at what's shared with you, after starting
SHARED_EVERY = 300.0         # then every five minutes
SEARCH_WAIT = 1.5            # an intent waits this long for a search before answering later

# Sign-in states the Preferences page shows.
NOT_SET_UP, DISCONNECTED, SIGNING_IN, CODE_NEEDED, EXCHANGING, CONNECTED, FAILED = (
    "not_set_up", "disconnected", "signing_in", "code_needed", "exchanging", "connected",
    "failed")

# Folder states.
FOLDER_UNKNOWN, FOLDER_OK, FOLDER_MISSING, FOLDER_OTHER = "unknown", "ok", "missing", "other"


def account_from(answer):
    """The account details kept: id, name, email and what the paths start at."""
    answer = answer if isinstance(answer, dict) else {}
    root = answer.get("root_info") or {}
    kind = (answer.get("account_type") or {}).get(".tag", "")
    return {"id": answer.get("account_id") or "",
            "name": (answer.get("name") or {}).get("display_name") or "",
            "email": answer.get("email") or "",
            "business": kind == "business" or bool(answer.get("team")),
            "root_ns": str(root.get("root_namespace_id") or ""),
            "home_ns": str(root.get("home_namespace_id") or "")}


def path_root_of(account):
    """A team space's root namespace (paths then start where the desktop
    app's folder does), or None for an ordinary account."""
    root, home = account.get("root_ns"), account.get("home_ns")
    return root if root and home and root != home else None


# ------------------------------------------------------------
# Finding a file by name
# ------------------------------------------------------------

_WORD_RE = re.compile(r"[^\w]+")
DEICTIC = {"ini", "itu", "sini", "yang", "file", "berkas", "folder", "dokumen", "this", "that",
           "it", "one", "here", "the", "current"}
LEADING = {"dropbox", "file", "berkas", "folder", "dokumen", "the", "my"}


def simplify(textish):
    textish = unicodedata.normalize("NFKD", str(textish or "")).casefold()
    textish = "".join(c for c in textish if not unicodedata.combining(c))
    return " ".join(w for w in _WORD_RE.split(textish.replace("_", " ")) if w)


def is_deictic(words_text):
    """ "ini", "this file", "yang ini": the file you're on, not a name."""
    words = simplify(words_text).split()
    return bool(words) and all(w in DEICTIC for w in words)


def search_query(words_text):
    """What to look for: "file laporan" -> "laporan"."""
    words = str(words_text or "").strip(" \t.,!?;:\"'").split()
    while len(words) > 1 and simplify(words[0]) in LEADING:
        words = words[1:]
    return " ".join(words)


def _stem(name):
    base, ext = os.path.splitext(name or "")
    return base if ext and len(ext) <= 6 else (name or "")


def rank_matches(query, found):
    """("one", meta): copy it; ("ask", meta): probably it, ask first;
    ("many", [metas]): several fit, name them; ("none", None)."""
    found = [m for m in found or [] if isinstance(m, dict) and m.get("name")]
    if not found:
        return "none", None
    q = simplify(query)
    exact = [m for m in found if simplify(m["name"]) == q or simplify(_stem(m["name"])) == q]
    if len(exact) == 1:
        return "one", exact[0]
    if len(exact) > 1:
        return "many", exact[:text.MAX_NAMES]
    if len(found) == 1:
        return "ask", found[0]
    scored = sorted(((difflib.SequenceMatcher(None, q, simplify(_stem(m["name"]))).ratio(), i, m)
                     for i, m in enumerate(found)), key=lambda s: (-s[0], s[1]))
    best, second = scored[0][0], scored[1][0]
    if best >= 0.75 and best - second >= 0.15:
        return "ask", scored[0][2]
    return "many", [m for _s, _i, m in scored[:text.MAX_NAMES]]


class _Source:
    """What dropbox_sync asks of Dropbox."""

    def __init__(self, client):
        self.client = client

    def metadata(self, path):
        return self.client.get_metadata(path)

    def folder(self, path):
        try:
            return self.client.list_folder(path)
        except dropbox_api.DropboxError as e:
            if e.is_not_found():
                return []
            raise

    def server_offset(self):
        return self.client.server_offset()


class Engine:
    """`services` gives: settings() -> dict; notify([(text, sound)]) for
    news; say(text) for answers; deliver_link(url, said_ok, said_failed) to
    copy a link and say so; quiet() -> bool (quiet hours); changed() when
    what the Preferences page shows changed; and the stored data:
    load_account() / save_account(dict) / load_shared() / save_shared(dict).
    All may be called from any thread."""

    def __init__(self, services, app_key=None, client_factory=None, watcher_factory=None,
                 folders=None, clock=time.time, sign_in_factory=None, start_threads=True,
                 ask_explorer=None):
        self.services = services
        self.app_key = dropbox_api.APP_KEY if app_key is None else app_key
        self.client_factory = client_factory or (
            lambda token: dropbox_api.Client(self.app_key, token))
        self.watcher_factory = watcher_factory or dropbox_watch.FolderWatcher
        self.folders = folders or paths.read_info
        self.clock = clock
        self.sign_in_factory = sign_in_factory
        self.start_threads = start_threads
        self.ask_explorer = ask_explorer or explorer.selected_path
        self.state = NOT_SET_UP if not dropbox_api.is_set_up(self.app_key) else DISCONNECTED
        self.problem = ""
        self.account = None
        self.client = None
        self.tracker = None
        self.folder = None
        self.folder_state = FOLDER_UNKNOWN
        self.others = remote.OthersBuffer()
        self._names = {}
        self._lock = threading.RLock()
        self._stop = None
        self._threads = []
        self._watcher = None
        self._feed = None
        self._sign_in = None
        self._generation = 0

    # ------------------------------------------------------------------
    # Starting and stopping
    # ------------------------------------------------------------------

    def set_up(self):
        return dropbox_api.is_set_up(self.app_key)

    def connected(self):
        return self.state == CONNECTED and self.client is not None

    def load(self):
        """At start: sign in with the stored token, if there is one."""
        if not self.set_up():
            self.state = NOT_SET_UP
            return False
        stored = self.services.load_account() or {}
        token = stored.get("token")
        if not token:
            self.state = DISCONNECTED
            return False
        try:
            refresh = secret.unprotect(token)
        except secret.SecretError:
            logger.warning("[Dropbox] The stored sign-in can't be read on this computer.")
            self.state = DISCONNECTED
            return False
        account = {k: stored.get(k) for k in ("id", "name", "email", "business", "root_ns",
                                               "home_ns")}
        self._start(refresh, account)
        return True

    def _start(self, refresh_token, account, client=None):
        with self._lock:
            self._generation += 1
            self._halt()
            self.client = client or self.client_factory(refresh_token)
            self.client.path_root = path_root_of(account)
            self.account = account
            self.state = CONNECTED
            self.problem = ""
            self._stop = threading.Event()
            self.folder, self.folder_state = self._pick_folder(), FOLDER_UNKNOWN
            if self.start_threads:
                self._spawn(self._run_sync, "dropbox-sync")
                self._spawn(self._run_shared, "dropbox-shared")
        self.services.changed()

    def _spawn(self, target, name):
        stop, generation = self._stop, self._generation
        thread = threading.Thread(target=target, args=(stop, generation), daemon=True, name=name)
        self._threads.append(thread)
        thread.start()

    def _halt(self):
        """Stop the threads (under the lock; bump _generation first, so a
        thread that wakes up late sees it is no longer current). Returns the
        threads, to join once the lock is let go."""
        if self._stop is not None:
            self._stop.set()
        if self._feed is not None:
            self._feed.stop()
            self._feed = None
        if self._watcher is not None:
            self._watcher.stop(wait=1.0)
            self._watcher = None
        if self.client is not None:
            try:
                self.client.transport.close()     # cuts a long poll at once
            except Exception:
                pass
        threads, self._threads = self._threads, []
        if self.tracker is not None:
            self.tracker.clear()
        self.tracker = None
        self.others.clear()
        return threads

    @staticmethod
    def _join(threads, seconds=2.0):
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(seconds)

    def shutdown(self):
        """Hariku is closing, or the extension is turned off."""
        with self._lock:
            if self._sign_in is not None:
                self._sign_in.cancel()
            self._generation += 1
            threads = self._halt()
        self._join(threads)

    # ------------------------------------------------------------------
    # The folder on this computer
    # ------------------------------------------------------------------

    def _pick_folder(self):
        try:
            found = self.folders()
        except Exception:
            logger.exception("[Dropbox] Reading info.json failed")
            found = {}
        business = bool((self.account or {}).get("business"))
        folder = paths.pick_folder(found, business)
        return folder if folder and os.path.isdir(folder) else None

    def local_folder(self):
        """The Dropbox folder to map paths in (even before the start checks)."""
        if self.folder_state == FOLDER_OTHER:
            return None
        return self.folder or self._pick_folder()

    def _check_folder(self):
        """Whether the folder on this computer is this account's."""
        if not self.folder:
            return FOLDER_MISSING
        try:
            local = [n for n in os.listdir(self.folder)][:200]
        except OSError:
            return FOLDER_MISSING
        server = [e.get("name", "") for e in self.client.list_folder("", max_pages=3)]
        return FOLDER_OK if paths.folder_matches(local, server) else FOLDER_OTHER

    # ------------------------------------------------------------------
    # The threads
    # ------------------------------------------------------------------

    def _current(self, generation):
        return generation == self._generation

    def _prepare(self, stop, generation):
        """Refresh the account's details, check the folder, start watching."""
        answer = self.client.current_account()
        account = account_from(answer)
        with self._lock:
            if not self._current(generation):
                return False
            self.account = dict(self.account or {}, **account)
            self.client.path_root = path_root_of(self.account)
            self.folder = self._pick_folder()
        stored = self.services.load_account() or {}
        if stored.get("token"):
            stored.update(account)
            self.services.save_account(stored)
        state = self._check_folder()
        with self._lock:
            if not self._current(generation) or stop.is_set():
                return False
            self.folder_state = state
            if state == FOLDER_OK:
                self.tracker = sync.SyncTracker(self.folder, _Source(self.client))
                self._start_watcher()
            self._feed = remote.RemoteFeed(self.client, self._on_remote_entries,
                                           lambda: self._auth_lost(generation))
            if self.start_threads:
                self._feed.start()
        self.services.changed()
        return True

    def _start_watcher(self):
        tracker = self.tracker
        self._watcher = self.watcher_factory(self.folder, tracker.local_events,
                                             lambda message: logger.warning(
                                                 f"[Dropbox] Watching stopped: {message}"))
        self._watcher.start()

    def _run_sync(self, stop, generation):
        prepared = False
        next_prepare = 0.0
        next_watch_check = self.clock() + WATCH_RETRY
        while not stop.is_set():
            now = self.clock()
            try:
                if not prepared and now >= next_prepare:
                    prepared = self._prepare(stop, generation)
                    if not prepared:
                        next_prepare = now + PREPARE_RETRY
                if prepared:
                    self._tick(now)
                    if now >= next_watch_check:
                        next_watch_check = now + WATCH_RETRY
                        self._keep_watching()
            except dropbox_api.DropboxError as e:
                if e.kind == "auth":
                    self._auth_lost(generation)
                    return
                if not prepared:
                    next_prepare = self.clock() + PREPARE_RETRY
                logger.info(f"[Dropbox] {e}")
            except Exception:
                logger.exception("[Dropbox] The sync thread failed")
                if not prepared:
                    next_prepare = self.clock() + PREPARE_RETRY
            stop.wait(TICK)

    def _tick(self, now):
        settings = self.services.settings()
        tracker = self.tracker
        if tracker is not None:
            flush = tracker.tick(now)
            lines = text.sync_lines(flush, settings)
            if lines:
                self.services.notify(lines)
        entries = self.others.take(now)
        if entries and text.settings_on(settings, "others") and not self.services.quiet():
            summaries = remote.summarize(entries, self._person, self._is_new)
            lines = text.others_lines(summaries, settings)
            if lines:
                self.services.notify(lines)

    def _keep_watching(self):
        with self._lock:
            if self.folder_state != FOLDER_OK or self.tracker is None:
                return
            if self._watcher is not None and self._watcher.alive():
                return
            if os.path.isdir(self.folder):
                self._start_watcher()

    def _on_remote_entries(self, entries):
        tracker = self.tracker
        if tracker is not None:
            tracker.server_saw(entries)
        own = (self.account or {}).get("id")
        self.others.add(remote.others_changes(entries, own), self.clock())

    def _person(self, account_id):
        if account_id not in self._names:
            try:
                self._names[account_id] = self.client.account_name(account_id)
            except dropbox_api.DropboxError:
                return ""
        return self._names[account_id]

    def _is_new(self, path):
        try:
            return self.client.revision_count(path) == 1
        except dropbox_api.DropboxError:
            return None

    def _run_shared(self, stop, generation):
        if stop.wait(SHARED_FIRST):
            return
        while not stop.is_set():
            try:
                self._poll_shared(generation)
            except dropbox_api.DropboxError as e:
                if e.kind == "auth":
                    self._auth_lost(generation)
                    return
                logger.info(f"[Dropbox] What's shared with you: {e}")
            except Exception:
                logger.exception("[Dropbox] Looking at what's shared failed")
            if stop.wait(SHARED_EVERY):
                return

    def _poll_shared(self, generation):
        own = (self.account or {}).get("id")
        if not own:
            return
        watcher = remote.SharedWatcher(self.client, _SharedStore(self.services), own)
        items = watcher.poll()
        if not self._current(generation):
            return
        settings = self.services.settings()
        if items and not self.services.quiet():
            lines = text.shared_lines(items, settings)
            if lines:
                self.services.notify(lines)

    def _auth_lost(self, generation):
        """Dropbox no longer accepts the sign-in (revoked, or the app was
        removed): forget it and say so, once."""
        with self._lock:
            if not self._current(generation) or self.state != CONNECTED:
                return
            self._generation += 1
            threads = self._halt()
            self.client = None
            self.account = None
            self.state = DISCONNECTED
            self.folder_state = FOLDER_UNKNOWN
        self.services.save_account({})
        self.services.notify([(_("signed_out"), None)])
        self.services.changed()
        self._join(threads)

    # ------------------------------------------------------------------
    # Signing in and out
    # ------------------------------------------------------------------

    def sign_in(self, open_browser=None, pages=None):
        """Start signing in (a worker thread); the page follows `state`."""
        if not self.set_up():
            return False
        with self._lock:
            if self._sign_in is not None:
                return False
            factory = self.sign_in_factory or (
                lambda **kw: dropbox_auth.SignIn(self.app_key, **kw))
            kwargs = {"on_need_code": self._code_needed, "pages": pages}
            if open_browser is not None:
                kwargs["open_browser"] = open_browser
            flow = factory(**kwargs)
            self._sign_in = flow
            self.state = SIGNING_IN
            self.problem = ""
        self.services.changed()
        thread = threading.Thread(target=self._run_sign_in, args=(flow,), daemon=True,
                                  name="dropbox-sign-in")
        thread.start()
        return True

    def _code_needed(self):
        self.state = CODE_NEEDED
        self.services.say(_("say_code_needed"))
        self.services.changed()

    def give_code(self, code):
        flow = self._sign_in
        if flow is not None and str(code or "").strip():
            self.state = EXCHANGING
            flow.give_code(code)
            self.services.changed()

    def cancel_sign_in(self):
        flow = self._sign_in
        if flow is not None:
            flow.cancel()

    def signing_in(self):
        return self._sign_in is not None

    def _run_sign_in(self, flow):
        try:
            outcome, value = flow.run()
        except Exception:
            logger.exception("[Dropbox] Signing in failed")
            outcome, value = "failed", None
        if outcome == "ok":
            outcome = self._finish_sign_in(value)
        with self._lock:
            self._sign_in = None
            if outcome == "ok":
                pass
            elif outcome == "cancelled":
                self.state = DISCONNECTED if self.client is None else CONNECTED
            else:
                self.state = FAILED
                self.problem = outcome
        if outcome == "ok":
            self.services.say(_("connected_as", name=(self.account or {}).get("name") or
                                _("someone")))
        elif outcome != "cancelled":
            self.services.say(_("account_failed", reason=_(f"reason_{outcome}")))
        self.services.changed()

    def _finish_sign_in(self, tokens):
        refresh = tokens.get("refresh_token")
        client = self.client_factory(refresh)
        try:
            account = account_from(client.current_account())
        except dropbox_api.DropboxError as e:
            return "network" if e.kind == "network" else "failed"
        try:
            stored = dict(account, token=secret.protect(refresh))
        except secret.SecretError:
            logger.exception("[Dropbox] The sign-in couldn't be encrypted")
            return "failed"
        self.services.save_account(stored)
        self._start(refresh, account, client)
        return "ok"

    def disconnect(self):
        """Sign out: stop, tell Dropbox to forget the sign-in, delete it here."""
        with self._lock:
            client = self.client
            self._generation += 1
            threads = self._halt()
            self.client = None
            self.account = None
            self.folder_state = FOLDER_UNKNOWN
            self.state = DISCONNECTED if self.set_up() else NOT_SET_UP
        self.services.save_account({})
        self.services.save_shared({})
        self.services.changed()
        self._join(threads)
        if client is not None:
            def revoke():
                if client.transport.closed:
                    client.transport = dropbox_api.Transport()
                client.revoke()
            threading.Thread(target=revoke, daemon=True, name="dropbox-revoke").start()

    # ------------------------------------------------------------------
    # What the status command and the page show
    # ------------------------------------------------------------------

    def status_state(self):
        tracker = self.tracker
        pending = tracker.status() if tracker is not None else {"pending": [], "stuck": []}
        folder = self.folder_state == FOLDER_OK or (self.folder_state == FOLDER_UNKNOWN and
                                                    self.local_folder() is not None)
        return {"set_up": self.set_up(), "connected": self.connected(),
                "name": (self.account or {}).get("name") or "", "folder": folder,
                "pending": pending["pending"], "stuck": pending["stuck"]}

    def status_text(self):
        return text.status_text(self.status_state())

    # ------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------

    def ready_problem(self):
        if not self.set_up():
            return _("not_set_up")
        if not self.connected():
            return _("not_connected")
        return None

    def copy_link_of_window(self, hwnd, class_of=None):
        """The hotkey or Aruna, with `hwnd` the window the user was in."""
        problem = self.ready_problem()
        if problem:
            self.services.say(problem)
            return False
        if not explorer.is_explorer(hwnd, class_of or explorer.window_class):
            self.services.say(_("link_not_explorer"))
            return False
        threading.Thread(target=self._copy_from_explorer, args=(hwnd,), daemon=True,
                         name="dropbox-link").start()
        return True

    def _copy_from_explorer(self, hwnd):
        try:
            path, _folder_itself = self.ask_explorer(hwnd)
        except explorer.ExplorerError as e:
            logger.info(f"[Dropbox] {e}")
            self.services.say(_("link_explorer_failed"))
            return
        if not path:
            self.services.say(_("link_explorer_failed"))
            return
        self.copy_link_of_local(path)

    def copy_link_of_local(self, path):
        """Copy the link of a file or folder on this computer (a worker thread)."""
        dropbox_path = paths.to_dropbox(path, self.local_folder())
        if dropbox_path is None:
            self.services.say(_("link_not_in_dropbox"))
            return
        if dropbox_path == "":
            self.services.say(_("link_root"))
            return
        self.copy_link_of(dropbox_path, paths.name_of(path))

    def copy_link_of(self, dropbox_path, name):
        """Copy the link of a Dropbox path (a worker thread)."""
        client = self.client
        if client is None:
            self.services.say(_("not_connected"))
            return
        try:
            url = client.shared_link(dropbox_path)
        except dropbox_api.DropboxError as e:
            self.services.say(self._link_problem(e, name))
            if e.kind == "auth":
                self._auth_lost(self._generation)
            return
        if not url:
            self.services.say(_("link_failed", name=name))
            return
        self.services.deliver_link(url, _("link_copied", name=name),
                                   _("clipboard_failed", name=name))

    @staticmethod
    def _link_problem(error, name):
        if error.is_not_found():
            return _("link_not_synced", name=name)
        if error.kind == "network":
            return _("no_network")
        if error.kind == "auth":
            return _("not_connected")
        logger.warning(f"[Dropbox] Making a link failed: {error}")
        return _("link_failed", name=name)

    def copy_link_in_background(self, meta):
        threading.Thread(target=self.copy_link_of,
                         args=(meta.get("path_display") or meta.get("path_lower"),
                               meta.get("name") or ""),
                         daemon=True, name="dropbox-link").start()

    # ------------------------------------------------------------------
    # Finding a file by name
    # ------------------------------------------------------------------

    def start_search(self, query):
        return SearchJob(self, query).start()


class SearchJob:
    """A search on a worker thread; the intent waits for it a moment and,
    when it takes longer, the job answers by itself (`late`)."""

    def __init__(self, engine, query):
        self.engine = engine
        self.query = query
        self.outcome = None          # ("one"|"ask"|"many"|"none", value) or ("error", text)
        self.late = False
        self._done = threading.Event()
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="dropbox-search").start()
        return self

    def _run(self):
        client = self.engine.client
        try:
            if client is None:
                outcome = ("error", _("not_connected"))
            else:
                outcome = rank_matches(self.query, client.search(self.query))
        except dropbox_api.DropboxError as e:
            outcome = ("error", _("no_network") if e.kind == "network" else
                       _("not_connected") if e.kind == "auth" else
                       _("search_failed"))
        with self._lock:
            self.outcome = outcome
            late = self.late
        self._done.set()
        if late:
            self.answer_late()

    def wait(self, seconds=SEARCH_WAIT):
        """The outcome, or None when it isn't ready yet (the job then answers
        by itself when it is)."""
        self._done.wait(seconds)
        with self._lock:
            if self.outcome is None:
                self.late = True
            return self.outcome

    def answer_late(self):
        kind, value = self.outcome
        say = self.engine.services.say
        if kind == "one":
            self.engine.copy_link_of(value.get("path_display") or value.get("path_lower"),
                                     value.get("name") or "")
        elif kind == "ask":
            say(_("search_suggest", item=text.item_text(value)))
        elif kind == "many":
            say(_("search_choices", items=text.join_names([text.item_text(m) for m in value])))
        elif kind == "none":
            say(_("search_none", query=self.query))
        else:
            say(value)


class _SharedStore:
    def __init__(self, services):
        self.services = services

    def load(self):
        return self.services.load_shared() or {}

    def save(self, data):
        self.services.save_shared(data)
