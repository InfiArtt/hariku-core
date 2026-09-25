# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Dropbox's HTTP API: signing in (OAuth 2 with PKCE) and the few calls the
extension makes, over urllib (the compiled Hariku has neither `requests` nor
the Dropbox SDK). No wx here.

Every call goes through a Transport, so tests use a fake one and nothing
reaches the network. Tokens are never logged: errors carry the route, the
HTTP status and Dropbox's error summary, never a request's headers or body.
"""

import base64
import calendar
import hashlib
import http.client
import json
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# ----------------------------------------------------------------------------
# The Dropbox app this build signs in with. Create it at
# https://www.dropbox.com/developers/apps ("Scoped access", "Full Dropbox"),
# tick SCOPES on its Permissions tab, add REDIRECT_URI under OAuth 2, Redirect
# URIs, and paste its App key here. There is no App secret on purpose: Hariku
# is open source, so it signs in with PKCE, which needs none. While this is
# empty, the Preferences page and every command say Dropbox isn't set up in
# this build of Hariku.
APP_KEY = ""
# ----------------------------------------------------------------------------

# Dropbox only redirects to URIs registered in the App Console, exactly,
# port included, so the port is fixed. Plain http is allowed for a loopback
# address; 127.0.0.1 rather than "localhost", which a browser may resolve to
# ::1 while the listener waits on 127.0.0.1 (RFC 8252 recommends the IP).
REDIRECT_PORT = 17613
REDIRECT_PATH = "/dropbox"
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}{REDIRECT_PATH}"

# What Hariku may do: read the account's name, read file and folder details
# (never their contents), and read and make shared links.
SCOPES = ("account_info.read", "files.metadata.read", "sharing.read", "sharing.write")

AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
API_URL = "https://api.dropboxapi.com/2/"
NOTIFY_URL = "https://notify.dropboxapi.com/2/"
USER_AGENT = "Hariku-Dropbox/1.0"

TIMEOUT = 30                  # seconds for an ordinary call
LONGPOLL_SECONDS = 120        # what the long poll asks for (30 to 480)
LONGPOLL_JITTER = 90          # Dropbox may add up to this much
REFRESH_MARGIN = 300          # refresh the access token this long before it expires
MAX_PAGES = 20                # pages of a listing read at most


def is_set_up(app_key=None):
    """Whether this build has a Dropbox app to sign in with."""
    return bool((APP_KEY if app_key is None else app_key).strip())


# ------------------------------------------------------------
# Errors
# ------------------------------------------------------------

class DropboxError(Exception):
    """A call that failed. `kind`:
      "network"  no answer (offline, a timeout, the connection cut)
      "auth"     the sign-in is no longer valid: sign in again
      "scope"    the Dropbox app lacks a permission Hariku needs
      "api"      Dropbox said no (409): `summary` says why ("path/not_found/...")
      "rate"     too many requests; wait `retry_after` seconds
      "server"   Dropbox's side failed (5xx)
      "http"     any other status
      "setup"    no App key in this build
    """

    def __init__(self, message, kind="http", status=0, summary="", error=None, retry_after=0):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.summary = summary or ""
        self.error = error
        self.retry_after = retry_after

    def is_not_found(self):
        return self.kind == "api" and "not_found" in self.summary


# ------------------------------------------------------------
# HTTPS
# ------------------------------------------------------------

class _CuttableHTTPS(urllib.request.HTTPSHandler):
    """urllib's HTTPS handler, remembering each connection it opens so the
    Transport can cut it from another thread."""

    def __init__(self, transport):
        super().__init__(context=ssl.create_default_context())
        self._transport = transport

    def https_open(self, req):
        transport = self._transport

        def connect(host, **kwargs):
            conn = http.client.HTTPSConnection(host, **kwargs)
            transport._track(conn)
            return conn

        return self.do_open(connect, req, context=self._context)


def _cut(conn):
    """End a request another thread is waiting on. On Windows neither
    shutdown() nor socket.close() wakes a read waiting in select() (close()
    even waits for http.client's file object to let go), so the socket
    itself is closed, at the C level: the waiting read fails at once."""
    sock = getattr(conn, "sock", None)
    if sock is None:
        return
    try:
        socket.socket.__base__.close(sock)
    except (OSError, TypeError, ValueError, AttributeError):
        pass


class Transport:
    """HTTPS requests over urllib, which honours the system's proxy. A long
    poll blocks for minutes; close() cuts every open connection, so turning
    Dropbox off or closing Hariku never waits for one."""

    def __init__(self):
        self._lock = threading.Lock()
        self._open = {}                 # thread id -> connections it opened
        self._closed = False
        self._opener = urllib.request.build_opener(_CuttableHTTPS(self))

    def _track(self, conn):
        with self._lock:
            self._open.setdefault(threading.get_ident(), []).append(conn)
            closed = self._closed
        if closed:
            _cut(conn)

    def request(self, method, url, headers=None, body=None, timeout=TIMEOUT):
        """(status, {lower-case header: value}, body bytes). An HTTP error
        status is returned, not raised; no answer raises OSError."""
        if self._closed:
            raise OSError("the Dropbox connection is closed")
        req = urllib.request.Request(url, data=body, method=method, headers=dict(headers or {}))
        req.add_header("User-Agent", USER_AGENT)
        try:
            try:
                with self._opener.open(req, timeout=timeout) as resp:
                    return resp.status, _header_dict(resp.headers), resp.read()
            except urllib.error.HTTPError as e:
                try:
                    data = e.read()
                except Exception:
                    data = b""
                finally:
                    e.close()
                return e.code, _header_dict(e.headers), data
            except (urllib.error.URLError, http.client.HTTPException, ValueError, AttributeError) as e:
                # AttributeError: the SSL state went away under a cut read.
                raise OSError(str(e)) from None
        finally:
            with self._lock:
                self._open.pop(threading.get_ident(), None)

    def close(self):
        with self._lock:
            self._closed = True
            conns = [c for group in self._open.values() for c in group]
        for conn in conns:
            _cut(conn)

    @property
    def closed(self):
        return self._closed


def _header_dict(headers):
    try:
        return {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    except Exception:
        return {}


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                       "sep", "oct", "nov", "dec"), start=1)}


def parse_http_date(text):
    """Seconds since 1970 of an HTTP Date header ("Fri, 25 Sep 2026 10:00:00
    GMT"), or None. Read by hand: strptime's month names follow the locale."""
    try:
        parts = str(text).replace(",", " ").split()
        day, month, year, clock = parts[1], parts[2], parts[3], parts[4]
        hour, minute, second = (int(x) for x in clock.split(":"))
        return float(calendar.timegm((int(year), _MONTHS[month[:3].lower()], int(day),
                                      hour, minute, second, 0, 0, 0)))
    except (IndexError, KeyError, ValueError, TypeError):
        return None


def parse_time(text):
    """Seconds since 1970 of Dropbox's "2026-09-25T10:00:00Z", or None."""
    try:
        text = str(text).strip().rstrip("Z")
        date, clock = text.split("T")
        year, month, day = (int(x) for x in date.split("-"))
        hour, minute, second = clock.split(":")
        return float(calendar.timegm((year, month, day, int(hour), int(minute),
                                      int(float(second)), 0, 0, 0)))
    except (ValueError, TypeError, AttributeError):
        return None


def _json(data):
    try:
        value = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None
    return value


def _call_http(transport, method, url, headers, body, timeout, what):
    try:
        return transport.request(method, url, headers=headers, body=body, timeout=timeout)
    except OSError as e:
        raise DropboxError(f"{what}: no answer ({type(e).__name__})", kind="network") from None


# ------------------------------------------------------------
# Signing in (OAuth 2 with PKCE)
# ------------------------------------------------------------

def _b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def pkce_pair(random_bytes=os.urandom):
    """(code_verifier, code_challenge): a fresh secret for one sign-in and
    its SHA-256, which is all Dropbox sees until the code is exchanged."""
    verifier = _b64url(random_bytes(48))                   # 64 characters
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def new_state(random_bytes=os.urandom):
    """A random value the redirect must bring back (it wasn't forged)."""
    return _b64url(random_bytes(24))


def authorize_url(app_key, challenge, state, redirect_uri=None):
    """Where the browser signs in. Without `redirect_uri` Dropbox shows the
    code for the user to paste into Hariku."""
    params = [("client_id", app_key), ("response_type", "code"),
              ("code_challenge", challenge), ("code_challenge_method", "S256"),
              ("token_access_type", "offline"), ("scope", " ".join(SCOPES)),
              ("state", state)]
    if redirect_uri:
        params.append(("redirect_uri", redirect_uri))
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def _token_request(transport, form, what):
    body = urllib.parse.urlencode(form).encode("ascii")
    status, _headers, data = _call_http(
        transport, "POST", TOKEN_URL,
        {"Content-Type": "application/x-www-form-urlencoded"}, body, TIMEOUT, what)
    answer = _json(data)
    if status == 200 and isinstance(answer, dict) and answer.get("access_token"):
        return answer
    code = answer.get("error") if isinstance(answer, dict) else ""
    if status in (400, 401) and code in ("invalid_grant", "invalid_client",
                                         "unauthorized_client", "invalid_request"):
        raise DropboxError(f"{what}: {code}", kind="auth", status=status, summary=str(code))
    if status >= 500:
        raise DropboxError(f"{what}: HTTP {status}", kind="server", status=status)
    raise DropboxError(f"{what}: HTTP {status} {code or ''}".strip(), kind="http", status=status,
                       summary=str(code or ""))


def exchange_code(app_key, code, verifier, redirect_uri=None, transport=None):
    """Trade the code from the browser for tokens: {"access_token",
    "refresh_token", "expires_in", "account_id", ...}."""
    if not is_set_up(app_key):
        raise DropboxError("no App key", kind="setup")
    form = {"code": code.strip(), "grant_type": "authorization_code",
            "client_id": app_key, "code_verifier": verifier}
    if redirect_uri:
        form["redirect_uri"] = redirect_uri
    answer = _token_request(transport or Transport(), form, "signing in")
    if not answer.get("refresh_token"):
        raise DropboxError("signing in: no refresh token", kind="http")
    return answer


def refresh_access_token(app_key, refresh_token, transport):
    """A new short-lived access token: (token, seconds it lasts)."""
    answer = _token_request(transport, {"grant_type": "refresh_token",
                                        "refresh_token": refresh_token,
                                        "client_id": app_key}, "refreshing the sign-in")
    try:
        lasts = int(answer.get("expires_in") or 14400)
    except (TypeError, ValueError):
        lasts = 14400
    return answer["access_token"], lasts


# ------------------------------------------------------------
# The calls
# ------------------------------------------------------------

class Client:
    """Dropbox calls with one account's refresh token. Thread-safe: the
    access token is refreshed under a lock, when it is about to expire or
    Dropbox says it has. `path_root` is a namespace id for team spaces (the
    paths then start at the team's root, like the desktop app's folder)."""

    def __init__(self, app_key, refresh_token, transport=None, clock=time.time):
        self.app_key = app_key
        self._refresh_token = refresh_token
        self.transport = transport or Transport()
        self.clock = clock
        self.path_root = None
        self._lock = threading.Lock()
        self._access = None
        self._expires = 0.0
        self._offsets = []            # server time minus local time, seconds

    # --- the access token -----------------------------------------------------------

    def access_token(self, force=False):
        with self._lock:
            if force or not self._access or self.clock() >= self._expires - REFRESH_MARGIN:
                token, lasts = refresh_access_token(self.app_key, self._refresh_token,
                                                    self.transport)
                self._access = token
                self._expires = self.clock() + lasts
            return self._access

    def forget_access_token(self):
        with self._lock:
            self._access = None
            self._expires = 0.0

    # --- the clock ------------------------------------------------------------------

    def _note_date(self, headers):
        server = parse_http_date(headers.get("date")) if headers else None
        if server is None:
            return
        with self._lock:
            self._offsets.append(server - self.clock())
            del self._offsets[:-5]

    def server_offset(self):
        """How far Dropbox's clock is ahead of this computer's, in seconds (the
        median of the last few answers' Date headers; 0 before any)."""
        with self._lock:
            values = sorted(self._offsets)
        if not values:
            return 0.0
        return values[len(values) // 2]

    # --- calling --------------------------------------------------------------------

    def call(self, route, args=None, timeout=TIMEOUT):
        """POST an RPC route ("files/get_metadata") with JSON arguments;
        returns the JSON answer or raises DropboxError."""
        for attempt in (1, 2):
            token = self.access_token(force=attempt == 2)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            if self.path_root:
                headers["Dropbox-API-Path-Root"] = json.dumps(
                    {".tag": "root", "root": str(self.path_root)})
            body = json.dumps(args).encode("utf-8")
            status, resp_headers, data = _call_http(self.transport, "POST", API_URL + route,
                                                    headers, body, timeout, route)
            self._note_date(resp_headers)
            if status == 200:
                answer = _json(data)
                return answer if answer is not None else {}
            error = _json(data)
            summary = str(error.get("error_summary", "")) if isinstance(error, dict) else ""
            if status == 401:
                tag = ((error or {}).get("error") or {}).get(".tag") if isinstance(error, dict) else ""
                if tag == "missing_scope":
                    raise DropboxError(f"{route}: missing scope", kind="scope", status=status,
                                       summary=summary, error=error)
                if attempt == 1:
                    continue                    # expired: refresh once and try again
                raise DropboxError(f"{route}: not signed in", kind="auth", status=status,
                                   summary=summary)
            raise _status_error(route, status, resp_headers, summary, error)
        raise DropboxError(f"{route}: not signed in", kind="auth")  # pragma: no cover

    def longpoll(self, cursor, seconds=LONGPOLL_SECONDS):
        """Wait until something changes under `cursor` (no access token: the
        cursor is enough). {"changes": bool, "backoff": seconds or absent}."""
        body = json.dumps({"cursor": cursor, "timeout": int(seconds)}).encode("utf-8")
        status, headers, data = _call_http(
            self.transport, "POST", NOTIFY_URL + "files/list_folder/longpoll",
            {"Content-Type": "application/json"}, body, seconds + LONGPOLL_JITTER + 30,
            "files/list_folder/longpoll")
        if status == 200:
            answer = _json(data)
            return answer if isinstance(answer, dict) else {"changes": False}
        error = _json(data)
        summary = str(error.get("error_summary", "")) if isinstance(error, dict) else ""
        raise _status_error("files/list_folder/longpoll", status, headers, summary, error)

    # --- the account ----------------------------------------------------------------

    def current_account(self):
        return self.call("users/get_current_account", None)

    def account_name(self, account_id):
        answer = self.call("users/get_account", {"account_id": account_id})
        name = (answer.get("name") or {}) if isinstance(answer, dict) else {}
        return name.get("display_name") or name.get("given_name") or ""

    def revoke(self):
        """Tell Dropbox to forget this sign-in (best effort)."""
        try:
            self.call("auth/token/revoke", None, timeout=10)
        except DropboxError:
            pass

    # --- files ----------------------------------------------------------------------

    def get_metadata(self, path):
        """A file's or folder's details, or None when there is nothing there."""
        try:
            return self.call("files/get_metadata", {"path": path})
        except DropboxError as e:
            if e.is_not_found():
                return None
            raise

    def list_folder(self, path, recursive=False, max_pages=MAX_PAGES):
        """Entries of a folder (every page, up to max_pages)."""
        answer = self.call("files/list_folder", {"path": path, "recursive": bool(recursive),
                                                 "limit": 2000})
        entries = list(answer.get("entries") or [])
        pages = 1
        while answer.get("has_more") and pages < max_pages:
            answer = self.call("files/list_folder/continue", {"cursor": answer.get("cursor")})
            entries.extend(answer.get("entries") or [])
            pages += 1
        return entries

    def latest_cursor(self, path="", recursive=True):
        answer = self.call("files/list_folder/get_latest_cursor",
                           {"path": path, "recursive": bool(recursive)})
        return answer.get("cursor")

    def changes_since(self, cursor, max_pages=MAX_PAGES):
        """(entries, new cursor) of what changed since `cursor`. A cursor
        Dropbox no longer knows raises DropboxError with "reset" in summary."""
        entries = []
        for _page in range(max_pages):
            answer = self.call("files/list_folder/continue", {"cursor": cursor})
            entries.extend(answer.get("entries") or [])
            cursor = answer.get("cursor") or cursor
            if not answer.get("has_more"):
                break
        return entries, cursor

    def revision_count(self, path, limit=2):
        """How many revisions a file has, up to `limit` (1: it is new)."""
        answer = self.call("files/list_revisions", {"path": path, "limit": int(limit)})
        return len(answer.get("entries") or [])

    def search(self, query, max_results=10):
        """Files and folders whose names match `query`, best first."""
        answer = self.call("files/search_v2", {"query": query, "options": {
            "max_results": int(max_results), "file_status": "active", "filename_only": True}})
        found = []
        for match in answer.get("matches") or []:
            outer = match.get("metadata") or {}
            inner = outer.get("metadata") if outer.get(".tag") == "metadata" else None
            if isinstance(inner, dict) and inner.get(".tag") in ("file", "folder"):
                found.append(inner)
        return found

    # --- sharing --------------------------------------------------------------------

    def existing_link(self, path):
        """The shared link this file or folder already has, or None."""
        answer = self.call("sharing/list_shared_links", {"path": path, "direct_only": True})
        for link in answer.get("links") or []:
            if link.get("url"):
                return link["url"]
        return None

    def create_link(self, path):
        """A new shared link; when one already exists, that one."""
        try:
            answer = self.call("sharing/create_shared_link_with_settings", {"path": path})
            return answer.get("url")
        except DropboxError as e:
            if e.kind == "api" and "shared_link_already_exists" in e.summary:
                inner = ((e.error or {}).get("error") or {}).get("shared_link_already_exists")
                metadata = (inner or {}).get("metadata") if isinstance(inner, dict) else None
                if isinstance(metadata, dict) and metadata.get("url"):
                    return metadata["url"]
                return self.existing_link(path)
            raise

    def shared_link(self, path):
        """This file's or folder's shared link: the one it has, or a new one."""
        return self.existing_link(path) or self.create_link(path)

    def _paged(self, route, key, max_pages):
        answer = self.call(route, {"limit": 300})
        items = list(answer.get(key) or [])
        pages = 1
        while answer.get("cursor") and pages < max_pages:
            answer = self.call(route + "/continue", {"cursor": answer["cursor"]})
            items.extend(answer.get(key) or [])
            pages += 1
        return items

    def received_files(self, max_pages=10):
        """Files others shared with this account."""
        return self._paged("sharing/list_received_files", "entries", max_pages)

    def shared_folders(self, max_pages=10):
        """Shared folders this account is in, added to its Dropbox or not."""
        folders = self._paged("sharing/list_folders", "entries", max_pages)
        try:
            folders += self._paged("sharing/list_mountable_folders", "entries", max_pages)
        except DropboxError as e:
            if e.kind in ("network", "auth"):
                raise
        return folders


def _status_error(route, status, headers, summary, error):
    if status == 409:
        return DropboxError(f"{route}: {summary or 'conflict'}", kind="api", status=status,
                            summary=summary, error=error)
    if status == 429:
        try:
            wait = int((headers or {}).get("retry-after") or 0)
        except ValueError:
            wait = 0
        if not wait and isinstance(error, dict):
            try:
                wait = int(((error.get("error") or {}).get("retry_after")) or 0)
            except (TypeError, ValueError, AttributeError):
                wait = 0
        return DropboxError(f"{route}: too many requests", kind="rate", status=status,
                            summary=summary, retry_after=max(1, wait or 60))
    if status >= 500:
        return DropboxError(f"{route}: HTTP {status}", kind="server", status=status,
                            summary=summary)
    return DropboxError(f"{route}: HTTP {status} {summary}".strip(), kind="http", status=status,
                        summary=summary, error=error)
