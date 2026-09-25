# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Signing in to Dropbox in the browser.

Hariku opens Dropbox's sign-in page; after "Allow", Dropbox sends the
browser back to http://127.0.0.1:17613/dropbox with a one-time code, which a
small listener on this computer (http.server, only on 127.0.0.1, only for
this sign-in) picks up. The code, the PKCE verifier made for this sign-in and
the App key are traded for a refresh token. When that port is taken by
another program, Dropbox shows the code instead and the user pastes it into
the Code field on the Preferences page. No wx here.
"""

import html
import http.server
import logging
import socket
import threading
import time
import urllib.parse
import webbrowser

import dropbox_api

logger = logging.getLogger(__name__)

WAIT_SECONDS = 300          # how long a sign-in may take in the browser


class _Server(http.server.HTTPServer):
    # Windows' SO_REUSEADDR would let this share a port another program
    # already listens on; ask for the port alone instead.
    allow_reuse_address = False

    def server_bind(self):
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            except OSError:
                pass
        # TCPServer's bind, without HTTPServer's getfqdn(), a name lookup
        # that can take seconds on some networks.
        http.server.socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


def _page(title, text):
    return ("<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>{t}</title></head>"
            "<body><h1>{t}</h1><p>{p}</p></body></html>").format(
        t=html.escape(title), p=html.escape(text)).encode("utf-8")


class LoopbackReceiver:
    """Waits on 127.0.0.1:`port` for Dropbox's redirect to `path` carrying
    `state`. `pages` is {"done": (title, text), "failed": (title, text)}
    for what the browser shows afterwards."""

    def __init__(self, port, path, state, pages=None):
        self.port = port
        self.path = path
        self.state = state
        self.pages = pages or {"done": ("Hariku", "You can close this tab."),
                               "failed": ("Hariku", "Go back to Hariku and try again.")}
        self.result = None           # ("code", code) or ("error", reason)
        self._server = None

    def start(self):
        """Listen; False when the port is taken."""
        receiver = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                receiver._handle(self)

            def log_message(self, *args):
                pass                  # the address holds the code: never logged

        try:
            self._server = _Server(("127.0.0.1", self.port), Handler)
        except OSError:
            self._server = None
            return False
        self._server.timeout = 0.25
        return True

    @property
    def bound_port(self):
        return self._server.server_address[1] if self._server is not None else None

    def _handle(self, request):
        parsed = urllib.parse.urlsplit(request.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path != self.path or (query.get("state") or [""])[0] != self.state:
            request.send_response(404)
            request.send_header("Content-Type", "text/plain; charset=utf-8")
            request.end_headers()
            request.wfile.write(b"Not found")
            return
        code = (query.get("code") or [""])[0]
        if code:
            self.result = ("code", code)
            page = self.pages["done"]
        else:
            self.result = ("error", (query.get("error") or ["denied"])[0])
            page = self.pages["failed"]
        body = _page(*page)
        request.send_response(200)
        request.send_header("Content-Type", "text/html; charset=utf-8")
        request.send_header("Content-Length", str(len(body)))
        request.send_header("Cache-Control", "no-store")
        request.end_headers()
        request.wfile.write(body)

    def wait(self, cancelled, seconds=WAIT_SECONDS, clock=time.monotonic):
        """("code", code), ("error", reason), ("timeout", None) or
        ("cancelled", None). `cancelled()` is asked a few times a second."""
        end = clock() + seconds
        try:
            while self.result is None:
                if cancelled():
                    return "cancelled", None
                if clock() >= end:
                    return "timeout", None
                self._server.handle_request()
            return self.result
        finally:
            self.close()

    def close(self):
        server, self._server = self._server, None
        if server is not None:
            try:
                server.server_close()
            except OSError:
                pass


class SignIn:
    """One sign-in, run on a worker thread: run() returns ("ok", tokens) or
    (problem, detail), where problem is "cancelled", "timeout", "denied",
    "network", "code" (Dropbox refused the code) or "failed".

    With the port free, the redirect brings the code back by itself.
    Otherwise `on_need_code()` is called (the page shows the Code field) and
    the code comes through give_code()."""

    def __init__(self, app_key, open_browser=webbrowser.open, on_need_code=None, pages=None,
                 transport=None, receiver_factory=LoopbackReceiver, wait_seconds=WAIT_SECONDS):
        self.app_key = app_key
        self.open_browser = open_browser
        self.on_need_code = on_need_code
        self.pages = pages
        self.transport = transport
        self.receiver_factory = receiver_factory
        self.wait_seconds = wait_seconds
        self.manual = False
        self._cancelled = threading.Event()
        self._code = None
        self._code_ready = threading.Event()

    def cancel(self):
        self._cancelled.set()
        self._code_ready.set()

    def cancelled(self):
        return self._cancelled.is_set()

    def give_code(self, code):
        """The code the user pasted (the manual way)."""
        self._code = str(code or "").strip()
        self._code_ready.set()

    def run(self):
        verifier, challenge = dropbox_api.pkce_pair()
        state = dropbox_api.new_state()
        receiver = self.receiver_factory(dropbox_api.REDIRECT_PORT, dropbox_api.REDIRECT_PATH,
                                         state, self.pages)
        redirect = dropbox_api.REDIRECT_URI if receiver.start() else None
        self.manual = redirect is None
        url = dropbox_api.authorize_url(self.app_key, challenge, state, redirect)
        try:
            self.open_browser(url)
        except Exception:
            logger.exception("[Dropbox] Opening the browser failed")
        if redirect:
            outcome, value = receiver.wait(self.cancelled, self.wait_seconds)
            if outcome == "error":
                return "denied", value
            if outcome != "code":
                return outcome, None
            code = value
        else:
            if self.on_need_code is not None:
                self.on_need_code()
            if not self._code_ready.wait(self.wait_seconds):
                return "timeout", None
            if self.cancelled():
                return "cancelled", None
            code = self._code
            if not code:
                return "cancelled", None
        if self.cancelled():
            return "cancelled", None
        try:
            tokens = dropbox_api.exchange_code(self.app_key, code, verifier, redirect,
                                               self.transport)
        except dropbox_api.DropboxError as e:
            if e.kind == "network":
                return "network", None
            if e.kind == "auth":
                return "code", None
            logger.warning(f"[Dropbox] Signing in failed: {e}")
            return "failed", None
        return "ok", tokens
