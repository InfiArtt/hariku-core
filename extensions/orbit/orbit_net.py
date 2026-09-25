# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The connection to an Orbit server, on a thread of its own: connect, say
hello, read what comes, keep the line alive with pings, and when it drops,
connect again after a pause that grows (2, 4, 8, 15, 30, then 60 seconds).

Every socket operation happens on that one thread (a TLS socket must not be
used from two threads at once); send() only queues a message, which the
thread sends within a tenth of a second, or after reconnecting (messages
older than 30 seconds are dropped rather than sent late).

The owner hears about it through two callbacks, both called on the
connection's thread (main.py passes them on with wx.CallAfter):

  on_message(dict)        every message from the server, the welcome included
  on_state(state, info)   "connecting", "online" (info: the welcome),
                          "offline" (info: {"reason", "retry_in"}),
                          "failed" (info: the server's {"t": "err"} or
                          {"code": ...}; no more retries), "stopped"

No wx.
"""

import collections
import json
import logging
import random
import threading
import time

import orbit_ws as ws

logger = logging.getLogger(__name__)

BACKOFF = (2, 4, 8, 15, 30, 60)
POLL_SECONDS = 0.1
PING_SECONDS = 25            # Cloudflare and nginx close quiet connections after 100 and 60 s
DEAD_SECONDS = 70            # nothing at all heard for this long: the line is dead
CONNECT_TIMEOUT = 10
WELCOME_TIMEOUT = 15
QUEUE_LIMIT = 20
QUEUE_MAX_AGE = 30
# Closes that mean "don't come back by yourself": kicked, logged in elsewhere, banned.
FINAL_CLOSES = {4000: "kicked", 4001: "replaced", 4003: "banned"}


class Refused(Exception):
    """The server said no to the hello, or closed for good."""

    def __init__(self, info):
        super().__init__(str(info.get("code")))
        self.info = info


def default_connect(url):
    return ws.WebSocketClient.connect(url, timeout=CONNECT_TIMEOUT)


class Connection:
    def __init__(self, url, hello, on_message, on_state, connect=default_connect,
                 backoff=BACKOFF, rng=None):
        self.url = url
        self._hello = hello
        self._on_message = on_message
        self._on_state = on_state
        self._connect = connect
        self._backoff = tuple(backoff)
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._outbox = collections.deque()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self.state = "idle"

    # --- the owner's side ------------------------------------------------------------

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="orbit-connection")
        self._thread.start()

    def stop(self, wait=3.0):
        """Say goodbye and stop; no more reconnecting."""
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(wait)

    def running(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def online(self):
        return self.state == "online"

    def send(self, message):
        """Queue a message for the server. Returns False when stopped."""
        if self._stop.is_set():
            return False
        with self._lock:
            if len(self._outbox) >= QUEUE_LIMIT:
                self._outbox.popleft()
            self._outbox.append((time.monotonic(), message))
        return True

    def retry_now(self):
        """Skip the rest of the pause before the next attempt."""
        self._wake.set()

    # --- the connection's thread -----------------------------------------------------

    def _state(self, state, info=None):
        self.state = state
        try:
            self._on_state(state, info)
        except Exception:
            logger.exception("[Orbit] a state callback failed")

    def _message(self, message):
        try:
            self._on_message(message)
        except Exception:
            logger.exception("[Orbit] a message callback failed")

    def _run(self):
        attempt = 0
        while not self._stop.is_set():
            self._state("connecting", {"attempt": attempt})
            client = None
            reason = ""
            try:
                client = self._connect(self.url)
                client.send_json(self._hello())
                welcome = self._await_welcome(client)
                if welcome is None:
                    break                       # stopped while waiting
                attempt = 0
                self._state("online", welcome)
                self._message(welcome)
                self._serve(client)
            except Refused as e:
                self._close(client)
                self._state("failed", e.info)
                return
            except ws.ConnectionClosed as e:
                if e.code in FINAL_CLOSES:
                    self._close(client)
                    self._state("failed", {"code": FINAL_CLOSES[e.code]})
                    return
                reason = e.reason or f"closed ({e.code})"
            except ws.HandshakeError as e:
                reason = str(e)
            except (OSError, ws.WebSocketError, ValueError) as e:
                reason = str(e) or type(e).__name__
            except Exception as e:          # never let the thread die silently
                logger.exception("[Orbit] the connection failed")
                reason = type(e).__name__
            finally:
                self._close(client)
            if self._stop.is_set():
                break
            delay = self._backoff[min(attempt, len(self._backoff) - 1)]
            delay *= 0.85 + 0.3 * self._rng.random()
            attempt += 1
            self._state("offline", {"reason": reason, "retry_in": delay})
            self._wake.clear()
            self._wake.wait(delay)
        self._state("stopped")

    @staticmethod
    def _close(client, code=ws.CLOSE_NORMAL):
        if client is None:
            return
        try:
            client.close(code, "", wait=0.5)
        except Exception:
            pass

    def _decode(self, text):
        if not isinstance(text, str):
            return None
        try:
            message = json.loads(text)
        except ValueError:
            return None
        return message if isinstance(message, dict) else None

    def _await_welcome(self, client):
        deadline = time.monotonic() + WELCOME_TIMEOUT
        while not self._stop.is_set():
            message = self._decode(client.recv(timeout=POLL_SECONDS))
            if message is None:
                if time.monotonic() > deadline:
                    raise ws.WebSocketError("the server didn't answer the hello")
                continue
            if message.get("t") == "welcome":
                return message
            if message.get("t") == "err":
                raise Refused(message)
            self._message(message)
        return None

    def _flush(self, client):
        while True:
            with self._lock:
                if not self._outbox:
                    return
                queued_at, message = self._outbox.popleft()
            if time.monotonic() - queued_at > QUEUE_MAX_AGE:
                continue
            client.send_json(message)

    def _serve(self, client):
        last_ping = time.monotonic()
        while not self._stop.is_set():
            self._flush(client)
            text = client.recv(timeout=POLL_SECONDS)
            if text is not None:
                message = self._decode(text)
                if message is not None:
                    self._message(message)
                continue
            now = time.monotonic()
            if now - last_ping >= PING_SECONDS:
                client.ping()
                last_ping = now
            if now - client.last_received > DEAD_SECONDS:
                raise ws.ConnectionClosed(ws.CLOSE_ABNORMAL, "no answer from the server")
        self._flush(client)
        self._close(client)
