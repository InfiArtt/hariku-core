# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Dropbox extension (extensions/dropbox), all on fakes: signing
# in (PKCE, the 127.0.0.1 listener, the pasted code), the access token and its
# refresh, the calls and their errors, links reused or made, the Dropbox
# folder (info.json) and paths, the folder watcher's buffer (and the real
# watcher on a temporary folder), following your files until they sync
# (grouping, downloads, late files, online-only files), others' changes and
# what's shared with you, File Explorer's answer, Aruna's phrases in
# Indonesian and English, the texts and their personas, and the sounds.
# Nothing reaches the network (only 127.0.0.1 for the sign-in listener),
# nothing is played, spoken or shown.

import base64
import hashlib
import http.client
import importlib.util
import io
import json
import logging
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import types
import urllib.parse
import urllib.request
import wave

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "dropbox")
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

import dropbox_api as api  # noqa: E402
import dropbox_auth as auth  # noqa: E402
import dropbox_engine as eng  # noqa: E402
import dropbox_explorer as explorer  # noqa: E402
import dropbox_paths as paths  # noqa: E402
import dropbox_remote as remote  # noqa: E402
import dropbox_secret as secret  # noqa: E402
import dropbox_sync as sync  # noqa: E402
import dropbox_text as text  # noqa: E402
import dropbox_watch as watch  # noqa: E402

WINDOWS = sys.platform == "win32"
T0 = 1_790_000_000.0            # 2026-09-21
DROPBOX = r"C:\Users\Budi\Dropbox"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Only this computer: the sign-in listener's tests talk to 127.0.0.1."""
    def refuse(*args, **kwargs):
        raise AssertionError("the network was used")

    real = socket.create_connection

    def local_only(address, *args, **kwargs):
        if address[0] not in ("127.0.0.1", "localhost"):
            raise AssertionError(f"the network was used: {address}")
        return real(address, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket, "create_connection", local_only)
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", refuse)


@pytest.fixture
def lang(monkeypatch):
    """Switch Hariku's language (the extension's words follow it)."""
    from core import i18n

    def set_lang(code):
        monkeypatch.setattr(i18n, "_current_language", code)

    set_lang("id")
    return set_lang


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def http_date(t):
    days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    g = time.gmtime(t)
    return (f"{days[g.tm_wday]}, {g.tm_mday:02d} {months[g.tm_mon - 1]} {g.tm_year} "
            f"{g.tm_hour:02d}:{g.tm_min:02d}:{g.tm_sec:02d} GMT")


# ------------------------------------------------------------
# A fake HTTPS transport
# ------------------------------------------------------------

class FakeTransport:
    """Answers by URL: routes maps the part after the host ("oauth2/token",
    "2/files/get_metadata") to a list of answers used in turn (the last one
    repeats) or a function(body) -> answer. An answer is (status, dict or
    bytes[, headers])."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.calls = []
        self.closed = False

    def request(self, method, url, headers=None, body=None, timeout=30):
        route = url.split("://", 1)[1].split("/", 1)[1]
        self.calls.append({"method": method, "url": url, "route": route,
                           "headers": dict(headers or {}), "body": body, "timeout": timeout})
        answer = self.routes.get(route)
        if answer is None:
            raise AssertionError(f"unexpected call to {route}")
        if callable(answer):
            answer = answer(body)
        elif isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, Exception):
            raise answer
        status, data = answer[0], answer[1]
        extra = answer[2] if len(answer) > 2 else {}
        if not isinstance(data, bytes):
            data = json.dumps(data).encode("utf-8")
        return status, dict(extra), data

    def close(self):
        self.closed = True

    def to(self, route):
        return [c for c in self.calls if c["route"] == route]


TOKEN_OK = (200, {"access_token": "sl.ACCESS-1", "expires_in": 14400, "token_type": "bearer"})


def client_with(routes, clock=None):
    routes = dict(routes)
    routes.setdefault("oauth2/token", [TOKEN_OK])
    transport = FakeTransport(routes)
    client = api.Client("appkey123", "REFRESH-SECRET", transport=transport,
                        clock=clock or (lambda: T0))
    return client, transport


# ------------------------------------------------------------
# Signing in: PKCE and the URLs
# ------------------------------------------------------------

def test_pkce_challenge_is_the_s256_of_the_verifier():
    verifier, challenge = api.pkce_pair(lambda n: bytes(range(n)))
    assert len(verifier) == 64 and "=" not in verifier
    assert set(verifier) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == expected.decode()
    assert api.pkce_pair()[0] != api.pkce_pair()[0]          # fresh every time


def test_the_authorize_url_asks_for_offline_access_with_pkce():
    url = api.authorize_url("appkey123", "CHALLENGE", "STATE", api.REDIRECT_URI)
    base, query = url.split("?", 1)
    params = dict(urllib.parse.parse_qsl(query))
    assert base == "https://www.dropbox.com/oauth2/authorize"
    assert params == {"client_id": "appkey123", "response_type": "code",
                      "code_challenge": "CHALLENGE", "code_challenge_method": "S256",
                      "token_access_type": "offline",
                      "scope": "account_info.read files.metadata.read sharing.read sharing.write",
                      "state": "STATE", "redirect_uri": "http://127.0.0.1:17613/dropbox"}
    manual = dict(urllib.parse.parse_qsl(api.authorize_url("k", "c", "s").split("?", 1)[1]))
    assert "redirect_uri" not in manual and "client_secret" not in manual


def test_the_redirect_is_a_fixed_loopback_address():
    assert api.REDIRECT_URI == f"http://127.0.0.1:{api.REDIRECT_PORT}{api.REDIRECT_PATH}"
    assert api.REDIRECT_PORT == 17613 and api.REDIRECT_PATH == "/dropbox"


def test_the_app_key_is_one_constant():
    assert isinstance(api.APP_KEY, str)
    assert api.is_set_up("") is False and api.is_set_up("  ") is False
    assert api.is_set_up("abc123") is True
    with open(os.path.join(EXT_DIR, "dropbox_api.py"), encoding="utf-8") as f:
        source = f.read()
    assert source.count("\nAPP_KEY = ") == 1
    assert "client_secret" not in source.replace("no App secret", "")


def test_exchanging_the_code_sends_the_verifier_and_no_secret():
    transport = FakeTransport({"oauth2/token": [(200, {
        "access_token": "sl.A", "refresh_token": "R-1", "expires_in": 14400,
        "account_id": "dbid:me"})]})
    tokens = api.exchange_code("appkey123", " CODE ", "VERIFIER", api.REDIRECT_URI, transport)
    assert tokens["refresh_token"] == "R-1"
    (call,) = transport.calls
    form = dict(urllib.parse.parse_qsl(call["body"].decode()))
    assert form == {"code": "CODE", "grant_type": "authorization_code", "client_id": "appkey123",
                    "code_verifier": "VERIFIER", "redirect_uri": api.REDIRECT_URI}
    assert call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    # The pasted code (no redirect) is exchanged without a redirect_uri.
    transport.routes["oauth2/token"] = [(200, {"access_token": "a", "refresh_token": "r"})]
    api.exchange_code("appkey123", "CODE", "V", None, transport)
    assert "redirect_uri" not in dict(urllib.parse.parse_qsl(transport.calls[-1]["body"].decode()))


def test_a_refused_code_or_a_missing_refresh_token():
    refused = FakeTransport({"oauth2/token": [(400, {"error": "invalid_grant"})]})
    with pytest.raises(api.DropboxError) as e:
        api.exchange_code("k", "CODE", "V", None, refused)
    assert e.value.kind == "auth"
    online_only = FakeTransport({"oauth2/token": [(200, {"access_token": "a"})]})
    with pytest.raises(api.DropboxError):
        api.exchange_code("k", "CODE", "V", None, online_only)
    with pytest.raises(api.DropboxError) as e:
        api.exchange_code("", "CODE", "V", None, online_only)
    assert e.value.kind == "setup"


# ------------------------------------------------------------
# The access token
# ------------------------------------------------------------

def test_the_access_token_is_refreshed_once_and_again_before_it_expires():
    now = [T0]
    client, transport = client_with({"2/users/get_current_account": [(200, {"account_id": "x"})]},
                                    clock=lambda: now[0])
    client.current_account()
    client.current_account()
    assert len(transport.to("oauth2/token")) == 1
    form = dict(urllib.parse.parse_qsl(transport.to("oauth2/token")[0]["body"].decode()))
    assert form == {"grant_type": "refresh_token", "refresh_token": "REFRESH-SECRET",
                    "client_id": "appkey123"}
    call = transport.to("2/users/get_current_account")[0]
    assert call["headers"]["Authorization"] == "Bearer sl.ACCESS-1" and call["body"] == b"null"
    now[0] = T0 + 14400 - api.REFRESH_MARGIN + 1
    client.current_account()
    assert len(transport.to("oauth2/token")) == 2


def test_an_expired_token_is_refreshed_and_the_call_repeated():
    client, transport = client_with({
        "oauth2/token": [TOKEN_OK, (200, {"access_token": "sl.ACCESS-2", "expires_in": 14400})],
        "2/files/get_metadata": [(401, {"error_summary": "expired_access_token/",
                                        "error": {".tag": "expired_access_token"}}),
                                 (200, {".tag": "file", "name": "a.txt"})]})
    assert client.get_metadata("/a.txt")["name"] == "a.txt"
    calls = transport.to("2/files/get_metadata")
    assert [c["headers"]["Authorization"] for c in calls] == ["Bearer sl.ACCESS-1",
                                                              "Bearer sl.ACCESS-2"]


def test_a_revoked_sign_in_is_an_auth_error_and_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    client, transport = client_with({"oauth2/token": [(400, {"error": "invalid_grant",
                                                             "error_description": "revoked"})]})
    with pytest.raises(api.DropboxError) as e:
        client.current_account()
    assert e.value.kind == "auth"
    assert "REFRESH-SECRET" not in str(e.value) and "REFRESH-SECRET" not in caplog.text
    # Twice 401 on a call: signed out.
    client, transport = client_with({"2/users/get_current_account": [
        (401, {"error_summary": "invalid_access_token/", "error": {".tag": "invalid_access_token"}})]})
    with pytest.raises(api.DropboxError) as e:
        client.current_account()
    assert e.value.kind == "auth" and "sl.ACCESS-1" not in str(e.value)


@pytest.mark.parametrize("status, body, headers, kind", [
    (401, {"error_summary": "missing_scope/", "error": {".tag": "missing_scope"}}, {}, "scope"),
    (409, {"error_summary": "path/not_found/..", "error": {}}, {}, "api"),
    (429, {"error_summary": "too_many_requests/"}, {"retry-after": "7"}, "rate"),
    (503, b"busy", {}, "server"),
    (400, b"bad input", {}, "http"),
])
def test_errors_have_kinds(status, body, headers, kind):
    client, _t = client_with({"2/files/list_revisions": [(status, body, headers)]})
    with pytest.raises(api.DropboxError) as e:
        client.revision_count("/a.txt")
    assert e.value.kind == kind
    if kind == "rate":
        assert e.value.retry_after == 7


def test_no_answer_is_a_network_error():
    client, _t = client_with({"2/files/get_metadata": [OSError("offline")]})
    with pytest.raises(api.DropboxError) as e:
        client.get_metadata("/a.txt")
    assert e.value.kind == "network"


def test_nothing_there_is_none():
    client, _t = client_with({"2/files/get_metadata": [
        (409, {"error_summary": "path/not_found/", "error": {".tag": "path"}})]})
    assert client.get_metadata("/gone.txt") is None


def test_a_team_space_sends_its_root_and_the_clock_follows_dropbox():
    client, transport = client_with({"2/files/get_metadata": [
        (200, {".tag": "file"}, {"date": http_date(T0 + 30)})]})
    account = eng.account_from({"account_id": "dbid:me", "name": {"display_name": "Budi"},
                                "email": "budi@example.com", "account_type": {".tag": "business"},
                                "root_info": {".tag": "team", "root_namespace_id": "100",
                                              "home_namespace_id": "200"}})
    assert account == {"id": "dbid:me", "name": "Budi", "email": "budi@example.com",
                       "business": True, "root_ns": "100", "home_ns": "200"}
    client.path_root = eng.path_root_of(account)
    client.get_metadata("/x")
    header = transport.calls[-1]["headers"]["Dropbox-API-Path-Root"]
    assert json.loads(header) == {".tag": "root", "root": "100"}
    assert client.server_offset() == 30.0
    personal = eng.account_from({"account_type": {".tag": "basic"},
                                 "root_info": {"root_namespace_id": "5", "home_namespace_id": "5"}})
    assert eng.path_root_of(personal) is None and personal["business"] is False


def test_times():
    assert api.parse_time("2026-09-21T10:00:00Z") == api.parse_http_date(
        "Mon, 21 Sep 2026 10:00:00 GMT")
    assert api.parse_time(iso(T0)) == T0
    assert api.parse_time("nonsense") is None and api.parse_http_date("") is None


# ------------------------------------------------------------
# Links, searching, listings
# ------------------------------------------------------------

def test_an_existing_link_is_reused():
    client, transport = client_with({"2/sharing/list_shared_links": [(200, {"links": [
        {".tag": "file", "url": "https://www.dropbox.com/scl/fi/abc/laporan.pdf?dl=0"}]})]})
    assert client.shared_link("/Kelas/laporan.pdf").endswith("laporan.pdf?dl=0")
    body = json.loads(transport.to("2/sharing/list_shared_links")[0]["body"])
    assert body == {"path": "/Kelas/laporan.pdf", "direct_only": True}
    assert not transport.to("2/sharing/create_shared_link_with_settings")


def test_a_link_is_made_when_there_is_none():
    client, transport = client_with({
        "2/sharing/list_shared_links": [(200, {"links": []})],
        "2/sharing/create_shared_link_with_settings": [(200, {"url": "https://db.tt/new"})]})
    assert client.shared_link("/tugas.docx") == "https://db.tt/new"
    assert json.loads(transport.to("2/sharing/create_shared_link_with_settings")[0]["body"]) == \
        {"path": "/tugas.docx"}


def test_a_link_made_meanwhile_is_used():
    client, _t = client_with({
        "2/sharing/list_shared_links": [(200, {"links": []})],
        "2/sharing/create_shared_link_with_settings": [(409, {
            "error_summary": "shared_link_already_exists/metadata/",
            "error": {".tag": "shared_link_already_exists", "shared_link_already_exists": {
                ".tag": "metadata", "metadata": {"url": "https://db.tt/old"}}}})]})
    assert client.shared_link("/tugas.docx") == "https://db.tt/old"


def test_search_reads_names_only():
    client, transport = client_with({"2/files/search_v2": [(200, {"matches": [
        {"metadata": {".tag": "metadata", "metadata": {".tag": "file", "name": "laporan.pdf",
                                                       "path_display": "/Kelas/laporan.pdf"}}},
        {"metadata": {".tag": "other"}}]})]})
    found = client.search("laporan")
    assert [m["name"] for m in found] == ["laporan.pdf"]
    options = json.loads(transport.calls[-1]["body"])["options"]
    assert options["filename_only"] is True and options["file_status"] == "active"


def test_listings_follow_their_pages():
    client, transport = client_with({
        "2/files/list_folder": [(200, {"entries": [{"name": "a"}], "has_more": True, "cursor": "c1"})],
        "2/files/list_folder/continue": [(200, {"entries": [{"name": "b"}], "has_more": False,
                                                "cursor": "c2"})],
        "2/sharing/list_received_files": [(200, {"entries": [{"id": "id:1"}], "cursor": "r1"})],
        "2/sharing/list_received_files/continue": [(200, {"entries": [{"id": "id:2"}]})],
        "2/sharing/list_folders": [(200, {"entries": [{"shared_folder_id": "9"}]})],
        "2/sharing/list_mountable_folders": [(200, {"entries": [{"shared_folder_id": "8"}]})]})
    assert [e["name"] for e in client.list_folder("")] == ["a", "b"]
    assert [e["id"] for e in client.received_files()] == ["id:1", "id:2"]
    assert [e["shared_folder_id"] for e in client.shared_folders()] == ["9", "8"]


def test_the_long_poll_needs_no_token_and_waits_long_enough():
    client, transport = client_with({"2/files/list_folder/longpoll": [(200, {"changes": True})]})
    assert client.longpoll("CURSOR", 120) == {"changes": True}
    call = transport.calls[-1]
    assert call["url"].startswith("https://notify.dropboxapi.com/")
    assert "Authorization" not in call["headers"] and not transport.to("oauth2/token")
    assert json.loads(call["body"]) == {"cursor": "CURSOR", "timeout": 120}
    assert call["timeout"] >= 120 + 90


def test_the_transport_cuts_what_is_open_when_closed():
    transport = api.Transport()
    cut = []

    class Conn:
        sock = None

    conn = Conn()
    transport._track(conn)
    conn.sock = types.SimpleNamespace()
    import dropbox_api as module
    real_cut = module._cut
    try:
        module._cut = lambda c: cut.append(c)
        transport.close()
    finally:
        module._cut = real_cut
    assert cut == [conn] and transport.closed
    with pytest.raises(OSError):
        transport.request("GET", "https://example.invalid/")


def test_closing_cuts_a_request_still_waiting_for_its_answer(tmp_path):
    """A long poll waits minutes for an answer: turning Dropbox off must end
    it at once. A TLS server on 127.0.0.1 reads the request and never answers."""
    crypto = pytest.importorskip("cryptography")
    import datetime
    import ssl
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    assert crypto
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    (tmp_path / "c.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "k.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(tmp_path / "c.pem"), str(tmp_path / "k.pem"))
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    held = []

    def serve():
        conn, _address = server.accept()
        tls = context.wrap_socket(conn, server_side=True)
        tls.recv(65536)                       # the request; no answer, ever
        held.append(tls)

    threading.Thread(target=serve, daemon=True).start()
    transport = api.Transport()
    for handler in transport._opener.handlers:
        if isinstance(handler, api._CuttableHTTPS):
            handler._context = ssl._create_unverified_context()
    outcome = []

    def ask():
        try:
            transport.request("POST", f"https://127.0.0.1:{server.getsockname()[1]}/2/x",
                              body=b"{}", timeout=60)
            outcome.append("answered")
        except OSError:
            outcome.append("cut")

    thread = threading.Thread(target=ask)
    thread.start()
    for _i in range(200):
        if held:
            break
        time.sleep(0.01)
    time.sleep(0.1)
    started = time.monotonic()
    transport.close()
    thread.join(5)
    assert outcome == ["cut"] and time.monotonic() - started < 2
    server.close()


# ------------------------------------------------------------
# The browser sign-in: the 127.0.0.1 listener and the pasted code
# ------------------------------------------------------------

PAGES = {"done": ("Hariku tersambung", "Tutup tab ini."), "failed": ("Gagal", "Coba lagi.")}


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        conn.close()


def _receive(receiver, path, cancelled=lambda: False, seconds=5):
    answers = []
    thread = threading.Thread(target=lambda: answers.append(receiver.wait(cancelled, seconds)))
    port = receiver.bound_port
    thread.start()
    status, page = _get(port, path)
    thread.join(5)
    return answers[0] if answers else None, status, page


def test_the_listener_takes_the_code_and_thanks_the_browser():
    receiver = auth.LoopbackReceiver(0, "/dropbox", "STATE-1", PAGES)
    assert receiver.start()
    result, status, page = _receive(receiver, "/dropbox?code=ABC&state=STATE-1")
    assert result == ("code", "ABC") and status == 200
    assert "Hariku tersambung" in page and "ABC" not in page
    assert receiver._server is None                    # closed after the sign-in


def test_the_listener_ignores_a_wrong_state_and_reports_a_refusal():
    receiver = auth.LoopbackReceiver(0, "/dropbox", "STATE-1", PAGES)
    assert receiver.start()
    port = receiver.bound_port
    answers = []
    thread = threading.Thread(target=lambda: answers.append(receiver.wait(lambda: False, 5)))
    thread.start()
    assert _get(port, "/dropbox?code=EVIL&state=OTHER")[0] == 404
    assert _get(port, "/favicon.ico")[0] == 404
    status, page = _get(port, "/dropbox?error=access_denied&state=STATE-1")
    thread.join(5)
    assert answers == [("error", "access_denied")] and "Gagal" in page


def test_the_listener_gives_up_and_can_be_cancelled():
    clock = iter([0.0, 0.0, 1000.0])
    receiver = auth.LoopbackReceiver(0, "/dropbox", "S", PAGES)
    assert receiver.start()
    assert receiver.wait(lambda: False, 300, clock=lambda: next(clock)) == ("timeout", None)
    receiver = auth.LoopbackReceiver(0, "/dropbox", "S", PAGES)
    assert receiver.start()
    assert receiver.wait(lambda: True) == ("cancelled", None)


def test_a_taken_port_is_noticed():
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    try:
        receiver = auth.LoopbackReceiver(blocker.getsockname()[1], "/dropbox", "S", PAGES)
        assert receiver.start() is False
    finally:
        blocker.close()


class FakeReceiver:
    def __init__(self, port, path, state, pages, free=True, outcome=None):
        self.args = (port, path, state, pages)
        self.free = free
        self.outcome = outcome

    def start(self):
        return self.free

    def wait(self, cancelled, seconds):
        return self.outcome if self.outcome else ("code", "CODE-9")


def _token_transport():
    return FakeTransport({"oauth2/token": [(200, {"access_token": "a", "refresh_token": "R",
                                                  "expires_in": 60})]})


def test_signing_in_through_the_listener():
    opened, made = [], []

    def receiver(*args):
        made.append(FakeReceiver(*args))
        return made[-1]

    transport = _token_transport()
    flow = auth.SignIn("appkey123", open_browser=opened.append, transport=transport,
                       receiver_factory=receiver)
    assert flow.run() == ("ok", {"access_token": "a", "refresh_token": "R", "expires_in": 60})
    (url,) = opened
    params = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
    port, path, state, _pages = made[0].args
    assert (port, path) == (17613, "/dropbox") and params["state"] == state
    assert params["redirect_uri"] == api.REDIRECT_URI and params["code_challenge_method"] == "S256"
    form = dict(urllib.parse.parse_qsl(transport.calls[0]["body"].decode()))
    assert form["code"] == "CODE-9" and form["redirect_uri"] == api.REDIRECT_URI
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest())
    assert challenge.rstrip(b"=").decode() == params["code_challenge"]
    assert flow.manual is False


def test_signing_in_by_pasting_the_code_when_the_port_is_taken():
    asked, opened = [], []
    transport = _token_transport()
    flow = auth.SignIn("appkey123", open_browser=opened.append, transport=transport,
                       on_need_code=lambda: asked.append(True),
                       receiver_factory=lambda *a: FakeReceiver(*a, free=False))
    result = []
    thread = threading.Thread(target=lambda: result.append(flow.run()))
    thread.start()
    for _i in range(200):
        if asked:
            break
        time.sleep(0.01)
    assert asked and flow.manual
    flow.give_code("  PASTED  ")
    thread.join(5)
    assert result[0][0] == "ok"
    assert "redirect_uri" not in dict(urllib.parse.parse_qsl(opened[0].split("?", 1)[1]))
    form = dict(urllib.parse.parse_qsl(transport.calls[0]["body"].decode()))
    assert form["code"] == "PASTED" and "redirect_uri" not in form


@pytest.mark.parametrize("outcome, answer, expected", [
    (("error", "access_denied"), None, ("denied", "access_denied")),
    (("timeout", None), None, ("timeout", None)),
    (("cancelled", None), None, ("cancelled", None)),
    (None, [(400, {"error": "invalid_grant"})], ("code", None)),
    (None, [OSError("offline")], ("network", None)),
    (None, [(500, b"oops")], ("failed", None)),
])
def test_what_can_go_wrong_signing_in(outcome, answer, expected):
    transport = FakeTransport({"oauth2/token": answer or [(200, {"access_token": "a",
                                                                 "refresh_token": "R"})]})
    flow = auth.SignIn("k", open_browser=lambda url: None, transport=transport,
                       receiver_factory=lambda *a: FakeReceiver(*a, outcome=outcome))
    assert flow.run() == expected


def test_cancelling_a_pasted_code_sign_in():
    flow = auth.SignIn("k", open_browser=lambda url: None, transport=FakeTransport(),
                       receiver_factory=lambda *a: FakeReceiver(*a, free=False))
    flow.cancel()
    assert flow.run() == ("cancelled", None)


# ------------------------------------------------------------
# The sign-in kept encrypted (Windows DPAPI)
# ------------------------------------------------------------

@pytest.mark.skipif(not WINDOWS, reason="Windows' Data Protection API")
def test_the_sign_in_is_encrypted_for_this_windows_user():
    stored = secret.protect("REFRESH-SECRET-é")
    assert stored.startswith("dpapi1:") and "REFRESH" not in stored
    assert base64.b64decode(stored[7:]).find(b"REFRESH") == -1
    assert secret.unprotect(stored) == "REFRESH-SECRET-é"
    for damaged in ("plain-token", "dpapi1:!!!", "dpapi1:" + base64.b64encode(b"junk").decode()):
        with pytest.raises(secret.SecretError):
            secret.unprotect(damaged)


# ------------------------------------------------------------
# The Dropbox folder and paths
# ------------------------------------------------------------

INFO = json.dumps({"personal": {"path": "C:\\Users\\Budi\\Dropbox", "host": 1, "is_team": False},
                   "business": {"path": "C:\\Users\\Budi\\Dropbox (Sekolah)", "is_team": True}})


def test_info_json_is_read():
    assert paths.parse_info(INFO) == {
        "personal": os.path.normpath(r"C:\Users\Budi\Dropbox"),
        "business": os.path.normpath(r"C:\Users\Budi\Dropbox (Sekolah)")}
    assert paths.parse_info("{broken") == {} and paths.parse_info("[]") == {}
    assert paths.parse_info(json.dumps({"personal": {"path": ""}})) == {}


def test_info_json_is_looked_for_in_local_then_roaming_app_data(tmp_path):
    local, roaming = tmp_path / "local", tmp_path / "roaming"
    (roaming / "Dropbox").mkdir(parents=True)
    (roaming / "Dropbox" / "info.json").write_text(INFO, encoding="utf-8")
    env = {"LOCALAPPDATA": str(local), "APPDATA": str(roaming)}
    assert paths.info_json_paths(env) == [str(local / "Dropbox" / "info.json"),
                                          str(roaming / "Dropbox" / "info.json")]
    assert "personal" in paths.read_info(env)
    assert paths.read_info({}) == {}


def test_the_folder_of_the_signed_in_account_is_used():
    found = paths.parse_info(INFO)
    assert paths.pick_folder(found, business=False).endswith("Dropbox")
    assert paths.pick_folder(found, business=True).endswith("(Sekolah)")
    assert paths.pick_folder({"business": "X"}, business=False) is None
    assert paths.pick_folder({}, business=False) is None


@pytest.mark.parametrize("local, expected", [
    (r"C:\Users\Budi\Dropbox\Kelas\tugas.docx", "/Kelas/tugas.docx"),
    (r"c:\users\budi\DROPBOX\Kelas\Tugas.DOCX", "/Kelas/Tugas.DOCX"),
    (r"C:\Users\Budi\Dropbox", ""),
    ("C:\\Users\\Budi\\Dropbox\\\\", ""),
    ("C:/Users/Budi/Dropbox/laporan.pdf", "/laporan.pdf"),
    (r"\\?\C:\Users\Budi\Dropbox\a b\c.txt", "/a b/c.txt"),
    (r"C:\Users\Budi\Dropbox2\laporan.pdf", None),
    (r"C:\Users\Budi\Documents\laporan.pdf", None),
    ("::{20D04FE0-3AEA-1069-A2D8-08002B30309D}", None),
    ("", None),
])
def test_local_paths_map_to_dropbox_paths_ignoring_case(local, expected):
    assert paths.to_dropbox(local, DROPBOX) == expected


def test_dropbox_paths_map_back():
    assert paths.to_local("/Kelas/tugas.docx", DROPBOX) == DROPBOX + r"\Kelas\tugas.docx"
    assert paths.to_local("", DROPBOX + "\\") == DROPBOX
    assert paths.parent_name("/Kelas/Bab 1/tugas.docx") == "Bab 1"
    assert paths.parent_name("/tugas.docx") == ""
    assert paths.parent_path("/Kelas/tugas.docx") == "/Kelas" and paths.parent_path("/a") == ""
    assert paths.name_of(r"C:\x\laporan.pdf") == "laporan.pdf" == paths.name_of("/Kelas/laporan.pdf")
    assert paths.same_path("C:/A/b", "c:\\a\\B\\\\")


@pytest.mark.parametrize("relative, ignored", [
    ("laporan.pdf", False), (r"Kelas\tugas.docx", False), ("desktop.ini", True),
    (r"Kelas\Desktop.ini", True), (r"Kelas\~$tugas.docx", True), ("data.TMP", True),
    (".~lock.laporan.odt#", True), (r".dropbox.cache\2026\abc", True), (".dropbox", True),
    ("Thumbs.db", True), ("video.mp4.crdownload", True), ("", True),
    (r"Kelas\.dropbox.cache.txt", False),
])
def test_names_dropbox_leaves_alone(relative, ignored):
    assert paths.ignored_relative(relative) is ignored


@pytest.mark.parametrize("attributes, online_only", [
    (0x20, False), (0x80, False), (0x1000, True), (0x40000, True), (0x400000, True),
    (0x400000 | 0x20, True),
])
def test_online_only_files_are_recognised(attributes, online_only):
    assert paths.FileInfo(10, T0, attributes).online_only is online_only


def test_a_file_s_details_come_without_opening_it(tmp_path):
    path = tmp_path / "laporan.pdf"
    path.write_bytes(b"12345")
    os.utime(path, (T0, T0))
    info = paths.file_info(str(path))
    assert (info.size, round(info.mtime, 3), info.is_dir) == (5, T0, False)
    assert paths.file_info(str(tmp_path / "nothing.txt")) is None
    assert paths.file_info(str(tmp_path)).is_dir


def test_files_marked_for_dropbox_to_ignore():
    marked = {DROPBOX + r"\Kelas:com.dropbox.ignored"}
    assert paths.marked_ignored(DROPBOX + r"\Kelas\node_modules\x.js", DROPBOX, marked.__contains__)
    assert not paths.marked_ignored(DROPBOX + r"\Lain\x.js", DROPBOX, marked.__contains__)
    assert paths.marked_ignored(DROPBOX + r"\a.txt", DROPBOX,
                                lambda p: p.endswith("a.txt:com.dropbox.ignored"))


def test_the_folder_on_this_computer_must_look_like_the_account():
    assert paths.folder_matches(["Kelas", "laporan.pdf", "desktop.ini"],
                                ["kelas", "Laporan.pdf", "x"])
    assert not paths.folder_matches(["Kantor", "Proyek", "Foto"], ["Kelas", "laporan.pdf"])
    assert paths.folder_matches([".dropbox", "desktop.ini"], [])


# ------------------------------------------------------------
# The folder watcher
# ------------------------------------------------------------

def _notify_record(action, name, last=False):
    raw = name.encode("utf-16-le")
    size = (12 + len(raw) + 3) // 4 * 4
    return struct.pack("<III", 0 if last else size, action, len(raw)) + raw + \
        b"\0" * (size - 12 - len(raw))


def test_the_watcher_s_buffer_is_read():
    data = (_notify_record(1, "laporan.pdf") + _notify_record(3, "Kelas\\tugas ü.docx") +
            _notify_record(4, "a.txt") + _notify_record(5, "b.txt") +
            _notify_record(2, "c.txt", last=True))
    assert watch.parse_notifications(data) == [
        ("added", "laporan.pdf"), ("modified", "Kelas\\tugas ü.docx"), ("renamed_from", "a.txt"),
        ("renamed_to", "b.txt"), ("removed", "c.txt")]
    assert watch.parse_notifications(b"") == []
    assert watch.parse_notifications(struct.pack("<III", 0, 99, 2) + "x".encode("utf-16-le")) == []


@pytest.mark.skipif(not WINDOWS, reason="ReadDirectoryChangesW")
def test_the_watcher_sees_files_change_and_stops_at_once(tmp_path):
    seen, errors = [], []
    watcher = watch.FolderWatcher(str(tmp_path), seen.extend, errors.append).start()
    try:
        time.sleep(0.2)
        (tmp_path / "Kelas").mkdir()
        (tmp_path / "Kelas" / "tugas.docx").write_text("x")
        (tmp_path / "laporan.pdf").write_text("hello")
        os.replace(tmp_path / "laporan.pdf", tmp_path / "laporan final.pdf")
        for _i in range(100):
            if ("renamed_to", "laporan final.pdf") in seen:
                break
            time.sleep(0.02)
    finally:
        started = time.monotonic()
        watcher.stop()
        stopped_in = time.monotonic() - started
    assert ("added", "Kelas\\tugas.docx") in seen and ("renamed_to", "laporan final.pdf") in seen
    assert not watcher.alive() and stopped_in < 1.5 and errors == []


@pytest.mark.skipif(not WINDOWS, reason="ReadDirectoryChangesW")
def test_the_watcher_reports_a_folder_it_cannot_watch(tmp_path):
    errors = []
    watcher = watch.FolderWatcher(str(tmp_path / "gone"), lambda e: None, errors.append).start()
    watcher._thread.join(2)
    assert errors and not watcher.alive()


# ------------------------------------------------------------
# File Explorer
# ------------------------------------------------------------

def test_the_script_only_carries_the_window_number():
    script = explorer.script_for(263542)
    assert "$target = [int64]263542" in script and "__HWND__" not in script
    with pytest.raises((TypeError, ValueError)):
        explorer.script_for("1; Remove-Item x")


def test_explorer_is_asked_through_powershell_without_a_window():
    runs = []

    def run(command, **kwargs):
        runs.append((command, kwargs))
        return types.SimpleNamespace(returncode=0, stdout=json.dumps([
            {"name": "Kelas", "folder": DROPBOX + r"\Kelas", "focused": DROPBOX + r"\Kelas\b.txt",
             "selected": DROPBOX + r"\Kelas\b.txt"}]).encode("utf-8"), stderr=b"")

    tabs = explorer.ask_explorer(4242, run=run)
    command, kwargs = runs[0]
    assert command[0].lower().endswith("powershell.exe") and "-NoProfile" in command
    script = base64.b64decode(command[command.index("-EncodedCommand") + 1]).decode("utf-16-le")
    assert "[int64]4242" in script and "Shell.Application" in script
    assert kwargs["timeout"] == explorer.TIMEOUT and kwargs["capture_output"]
    if WINDOWS:
        assert kwargs["creationflags"] == explorer.CREATE_NO_WINDOW
    assert tabs == [{"name": "Kelas", "folder": DROPBOX + r"\Kelas",
                     "focused": DROPBOX + r"\Kelas\b.txt", "selected": [DROPBOX + r"\Kelas\b.txt"]}]


def test_explorer_problems_are_errors():
    def slow(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 10)

    def missing(command, **kwargs):
        raise FileNotFoundError("powershell")

    for run in (slow, missing):
        with pytest.raises(explorer.ExplorerError):
            explorer.ask_explorer(1, run=run)
    with pytest.raises(explorer.ExplorerError):
        explorer.parse_output(b"not json")
    failed = lambda command, **kw: types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"x")
    with pytest.raises(explorer.ExplorerError):
        explorer.ask_explorer(1, run=failed)
    assert explorer.parse_output(b"\xef\xbb\xbf[]\r\n") == [] and explorer.parse_output(b"") == []


def test_the_tab_on_screen_and_the_item_meant():
    tabs = [{"name": "Kantor", "folder": "C:\\Kantor", "focused": "", "selected": []},
            {"name": "Kelas", "folder": DROPBOX + "\\Kelas", "focused": DROPBOX + "\\Kelas\\b.txt",
             "selected": [DROPBOX + "\\Kelas\\a.txt", DROPBOX + "\\Kelas\\B.TXT"]}]
    assert explorer.active_tab(tabs, "Kelas - File Explorer") is tabs[1]
    assert explorer.active_tab(tabs, "Kelas") is tabs[1]
    assert explorer.active_tab(tabs, "Something else") is tabs[0]
    assert explorer.active_tab([], "x") is None
    assert explorer.chosen_item(tabs[1]) == (DROPBOX + "\\Kelas\\B.TXT", False)  # focused, selected
    tabs[1]["focused"] = DROPBOX + "\\Kelas\\c.txt"                               # focused only
    assert explorer.chosen_item(tabs[1]) == (DROPBOX + "\\Kelas\\a.txt", False)
    assert explorer.chosen_item(tabs[0]) == ("C:\\Kantor", True)                  # nothing selected
    assert explorer.chosen_item(None) == ("", True)
    assert explorer.selected_path(7, ask=lambda h: tabs, title_of=lambda h: "Kelas") == \
        (DROPBOX + "\\Kelas\\a.txt", False)


def test_only_explorer_windows_count():
    classes = {1: "CabinetWClass", 2: "wxWindowNR", 3: "Progman"}
    assert explorer.is_explorer(1, classes.get) and not explorer.is_explorer(2, classes.get)
    assert not explorer.is_explorer(3, classes.get) and not explorer.is_explorer(0, classes.get)


# ------------------------------------------------------------
# Following your files until they sync
# ------------------------------------------------------------

class Files:
    """The Dropbox folder, as file details (path -> FileInfo)."""

    def __init__(self):
        self.files = {}

    def put(self, relative, size=100, mtime=T0, attributes=0x20):
        self.files[(DROPBOX + "\\" + relative).casefold()] = paths.FileInfo(size, mtime, attributes)

    def remove(self, relative):
        self.files.pop((DROPBOX + "\\" + relative).casefold(), None)

    def stat(self, path):
        return self.files.get(path.casefold())


class Source:
    """Dropbox's side: path -> metadata; calls recorded."""

    def __init__(self, offset=0.0):
        self.meta = {}
        self.calls = []
        self.offset = offset
        self.error = None

    def put(self, dropbox_path, size=100, mtime=T0, server=T0 + 1):
        self.meta[dropbox_path.casefold()] = {
            ".tag": "file", "name": paths.name_of(dropbox_path), "path_display": dropbox_path,
            "path_lower": dropbox_path.casefold(), "size": size, "client_modified": iso(mtime),
            "server_modified": iso(server)}
        return self.meta[dropbox_path.casefold()]

    def metadata(self, path):
        self.calls.append(("metadata", path))
        if self.error:
            raise self.error
        return self.meta.get(path.casefold())

    def folder(self, path):
        self.calls.append(("folder", path))
        if self.error:
            raise self.error
        return [m for k, m in self.meta.items() if paths.parent_path(k) == path.casefold()]

    def server_offset(self):
        return self.offset


def tracker_for(files, source):
    return sync.SyncTracker(DROPBOX, source, stat=files.stat, clock=lambda: T0,
                            ignored=lambda path, root: False)


def run(tracker, start, end, step=0.5):
    """Tick from `start` to `end`; the Flushes that came."""
    flushes = []
    t = start
    while t <= end + 1e-9:
        flush = tracker.tick(t)
        if flush is not None:
            flushes.append((round(t - T0, 1), flush))
        t += step
    return flushes


def said(flushes, settings=None, language=None):
    return [line for _t, f in flushes for line, _sound in text.sync_lines(f, settings or {})]


def test_a_file_that_syncs_at_once(lang):
    files, source = Files(), Source()
    files.put("laporan.pdf", mtime=T0)
    source.put("/laporan.pdf", mtime=T0, server=T0 + 1)
    tracker = tracker_for(files, source)
    tracker.local_events([("added", "laporan.pdf"), ("modified", "laporan.pdf")], now=T0)
    flushes = run(tracker, T0, T0 + 10)
    assert len(flushes) == 1
    flush = flushes[0][1]
    assert (flush.new, flush.synced, flush.up_to_date, flush.session) == \
        (["laporan.pdf"], ["laporan.pdf"], True, ["laporan.pdf"])
    assert said(flushes) == ["laporan.pdf sudah tersinkron."]
    assert text.sync_lines(flush, {})[0][1] == "synced"
    assert source.calls == [("metadata", "/laporan.pdf")]           # asked once, after it settled


def test_a_file_that_takes_a_while(lang):
    files, source = Files(), Source()
    files.put(r"Kelas\tugas.docx", size=5000, mtime=T0)
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", r"Kelas\tugas.docx")], now=T0)
    first = run(tracker, T0, T0 + 4)
    assert said(first) == ["Menyinkronkan tugas.docx ke Dropbox…"]
    assert tracker.status() == {"pending": ["tugas.docx"], "stuck": []}
    source.put("/Kelas/tugas.docx", size=5000, mtime=T0, server=T0 + 6)
    later = run(tracker, T0 + 4.5, T0 + 20)
    assert said(later) == ["tugas.docx sudah tersinkron."]
    assert later[0][1].up_to_date and tracker.status()["pending"] == []


def test_a_download_by_the_desktop_app_is_not_announced(lang):
    files, source = Files(), Source()
    files.put(r"Kelas\catatan.txt", mtime=T0 - 60)
    source.put("/Kelas/catatan.txt", mtime=T0 - 60, server=T0 - 5)      # Dropbox had it first
    tracker = tracker_for(files, source)
    tracker.local_events([("added", r"Kelas\catatan.txt")], now=T0)
    assert run(tracker, T0, T0 + 20) == []


def test_dropbox_s_clock_is_allowed_for(lang):
    files, source = Files(), Source(offset=30.0)                         # Dropbox is 30 s ahead
    files.put("a.txt", mtime=T0)
    files.put("b.txt", mtime=T0 - 100)
    source.put("/a.txt", mtime=T0, server=T0 + 30 + 1)                   # uploaded just now
    source.put("/b.txt", mtime=T0 - 100, server=T0 + 30 - 10)            # 10 s before: a download
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "a.txt"), ("added", "b.txt")], now=T0)
    flushes = run(tracker, T0, T0 + 10)
    assert [f.session for _t, f in flushes] == [["a.txt"]]


def test_several_files_are_told_together(lang):
    files, source = Files(), Source()
    for name in ("a.txt", "b.txt", "c.txt"):
        files.put(name)
    tracker = tracker_for(files, source)
    tracker.local_events([("added", "a.txt"), ("added", "b.txt")], now=T0)
    tracker.local_events([("added", "c.txt")], now=T0 + 0.4)
    first = run(tracker, T0, T0 + 4)
    assert said(first) == ["Menyinkronkan 3 file ke Dropbox…"]
    source.put("/a.txt")
    middle = run(tracker, T0 + 4.5, T0 + 8)
    assert said(middle) == ["a.txt sudah tersinkron."]                  # a small batch: each one
    source.put("/b.txt")
    source.put("/c.txt")
    last = run(tracker, T0 + 8.5, T0 + 30)
    assert said(last) == ["Dropbox-mu sudah up to date."]
    assert last[0][1].session == ["a.txt", "b.txt", "c.txt"]


def test_a_big_copy_is_told_once_at_the_start_and_once_at_the_end(lang):
    files, source = Files(), Source()
    names = [f"foto{i}.jpg" for i in range(12)]
    for name in names:
        files.put("Liburan\\" + name)
    tracker = tracker_for(files, source)
    tracker.local_events([("added", "Liburan\\" + n) for n in names], now=T0)
    first = run(tracker, T0, T0 + 4)
    assert said(first) == ["Menyinkronkan 12 file ke Dropbox…"]
    assert all(call[0] == "folder" for call in source.calls)            # one listing, not 12 calls
    assert len(source.calls) == 1
    for name in names[:6]:
        source.put("/Liburan/" + name)
    assert said(run(tracker, T0 + 4.5, T0 + 9)) == []                   # partial progress: quiet
    for name in names[6:]:
        source.put("/Liburan/" + name)
    assert said(run(tracker, T0 + 9.5, T0 + 40)) == ["Dropbox-mu sudah up to date."]


def test_more_files_joining_soon_after_are_not_told_again(lang):
    files, source = Files(), Source()
    for i in range(6):
        files.put(f"f{i}.txt")
    tracker = tracker_for(files, source)
    tracker.local_events([("added", "f0.txt"), ("added", "f1.txt")], now=T0)
    first = run(tracker, T0, T0 + 4)
    tracker.local_events([("added", f"f{i}.txt") for i in range(2, 6)], now=T0 + 4.2)
    second = run(tracker, T0 + 4.5, T0 + 8)
    assert said(first) == ["Menyinkronkan 2 file ke Dropbox…"]
    assert second[0][1].new and second[0][1].retold and said(second) == []


def test_news_waits_for_a_file_still_being_checked(lang):
    files, source = Files(), Source()
    files.put("laporan.pdf")
    files.put(r"Kelas\catatan.txt", mtime=T0 - 60)
    source.put("/laporan.pdf", server=T0 + 1)
    source.put("/Kelas/catatan.txt", mtime=T0 - 60, server=T0 - 1)       # a download
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "laporan.pdf")], now=T0)
    tracker.local_events([("added", r"Kelas\catatan.txt")], now=T0 + 1.2)
    flushes = run(tracker, T0, T0 + 10)
    assert said(flushes) == ["laporan.pdf sudah tersinkron."]           # told once, not twice
    assert flushes[0][1].up_to_date


def test_a_file_that_doesnt_sync_is_mentioned_once(lang):
    files, source = Files(), Source()
    files.put("laporan.pdf", size=10)
    source.put("/laporan.pdf", size=5)                                    # the old version
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "laporan.pdf")], now=T0)
    flushes = run(tracker, T0, T0 + 400, step=1.0)
    lines = said(flushes)
    assert lines == ["Menyinkronkan laporan.pdf ke Dropbox…",
                     "laporan.pdf belum tersinkron; cek aplikasi Dropbox."]
    stuck_at = [t for t, f in flushes if f.stuck][0]
    assert 180 <= stuck_at <= 185
    assert tracker.status() == {"pending": ["laporan.pdf"], "stuck": ["laporan.pdf"]}
    checks = len(source.calls)
    run(tracker, T0 + 401, T0 + 520, step=1.0)
    assert len(source.calls) - checks <= 3                               # once a minute now
    source.put("/laporan.pdf", size=10, server=T0 + 500)
    assert said(run(tracker, T0 + 521, T0 + 600, step=1.0)) == ["laporan.pdf sudah tersinkron."]


def test_no_warning_while_dropbox_cannot_be_asked(lang):
    files, source = Files(), Source()
    files.put("laporan.pdf")
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "laporan.pdf")], now=T0)
    run(tracker, T0, T0 + 4)                                              # pending
    source.error = api.DropboxError("offline", kind="network")
    flushes = run(tracker, T0 + 5, T0 + 400, step=1.0)
    assert said(flushes) == []


def test_a_file_given_up_on_ends_quietly(lang):
    files, source = Files(), Source()
    files.put("laporan.pdf")
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "laporan.pdf")], now=T0)
    run(tracker, T0, T0 + 4)
    source.error = api.DropboxError("offline", kind="network")
    run(tracker, T0 + 5, T0 + sync.GIVE_UP_SECONDS + 60, step=10.0)
    assert tracker.status()["pending"] == []


def test_online_only_files_are_never_touched():
    files, source = Files(), Source()
    files.put("besar.mkv", attributes=0x400000 | 0x20)
    files.put("arsip.zip", attributes=0x1000)
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "besar.mkv"), ("added", "arsip.zip")], now=T0)
    assert run(tracker, T0, T0 + 10) == [] and source.calls == []


def test_ignored_names_folders_and_vanished_files_are_left_alone():
    files, source = Files(), Source()
    files.put("Kelas", attributes=0x10)
    files.put("desktop.ini")
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "Kelas"), ("modified", "desktop.ini"),
                          ("added", r"Kelas\~$tugas.docx"), ("added", r".dropbox.cache\x\y"),
                          ("added", "D3F4A200"), ("overflow", "")], now=T0)
    assert run(tracker, T0, T0 + 10) == [] and source.calls == []
    marked = sync.SyncTracker(DROPBOX, source, stat=files.stat, ignored=lambda p, r: True)
    files.put("node.bin")
    marked.local_events([("added", "node.bin")], now=T0)
    assert run(marked, T0, T0 + 10) == [] and source.calls == []


def test_a_file_deleted_while_syncing_is_dropped(lang):
    files, source = Files(), Source()
    files.put("a.txt")
    files.put("b.txt")
    tracker = tracker_for(files, source)
    tracker.local_events([("added", "a.txt"), ("added", "b.txt")], now=T0)
    run(tracker, T0, T0 + 4)
    source.put("/a.txt")
    tracker.local_events([("removed", "b.txt")], now=T0 + 4.2)
    files.remove("b.txt")
    flushes = run(tracker, T0 + 4.5, T0 + 20)
    assert said(flushes) == ["a.txt sudah tersinkron."]            # b.txt is gone: not waited for
    assert flushes[-1][1].up_to_date and tracker.status()["pending"] == []


def test_dropbox_s_own_news_confirms_a_file_at_once(lang):
    files, source = Files(), Source()
    files.put("laporan.pdf", size=10)
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "laporan.pdf")], now=T0)
    run(tracker, T0, T0 + 3)
    calls = len(source.calls)
    entry = dict(source.put("/laporan.pdf", size=10), path_display="/Laporan.PDF")
    source.meta.clear()
    tracker.server_saw([entry, {".tag": "deleted", "path_display": "/x"}])
    flushes = run(tracker, T0 + 3.5, T0 + 6)
    assert said(flushes) == ["laporan.pdf sudah tersinkron."] and len(source.calls) == calls


def test_a_file_made_online_only_after_syncing_counts_as_synced(lang):
    files, source = Files(), Source()
    files.put("laporan.pdf", size=10)
    tracker = tracker_for(files, source)
    tracker.local_events([("modified", "laporan.pdf")], now=T0)
    run(tracker, T0, T0 + 3)
    files.put("laporan.pdf", size=10, attributes=0x400000)
    assert said(run(tracker, T0 + 3.5, T0 + 10)) == ["laporan.pdf sudah tersinkron."]


def test_a_busy_moment_asks_dropbox_a_few_files_at_a_time():
    files, source = Files(), Source()
    for i in range(20):
        files.put(f"Folder{i}\\f.txt")
    tracker = tracker_for(files, source)
    tracker.local_events([("added", f"Folder{i}\\f.txt") for i in range(20)], now=T0)
    tracker.tick(T0 + 2)
    assert len(source.calls) == sync.MAX_CALLS_PER_TICK


@pytest.mark.parametrize("size, mtime, tag, expected", [
    (100, T0, "file", True), (100, T0 + 1.6, "file", True), (100, T0 - 2.5, "file", False),
    (101, T0, "file", False), (100, T0, "folder", False),
])
def test_in_sync_compares_size_and_time(size, mtime, tag, expected):
    meta = {".tag": tag, "size": size, "client_modified": iso(T0)}
    assert sync.in_sync(paths.FileInfo(100, mtime), meta) is expected
    assert sync.in_sync(None, meta) is False and sync.in_sync(paths.FileInfo(1, T0), None) is False


# ------------------------------------------------------------
# What other people do
# ------------------------------------------------------------

def _entry(path, by, server=T0, tag="file"):
    return {".tag": tag, "name": paths.name_of(path), "path_display": path,
            "path_lower": path.lower(), "server_modified": iso(server),
            "sharing_info": {"read_only": False, "parent_shared_folder_id": "1",
                             "modified_by": by} if by else None}


def test_only_others_changes_in_shared_folders_count():
    entries = [_entry("/Kelas/catatan.txt", "dbid:budi"), _entry("/Kelas/milikku.txt", "dbid:me"),
               _entry("/pribadi.txt", None), _entry("/Kelas", "dbid:budi", tag="folder"),
               {".tag": "deleted", "path_display": "/Kelas/lama.txt"}, "junk"]
    assert [e["name"] for e in remote.others_changes(entries, "dbid:me")] == ["catatan.txt"]


def test_others_changes_are_gathered_into_a_burst():
    buffer = remote.OthersBuffer()
    buffer.add([_entry("/Kelas/a.txt", "dbid:budi")], T0)
    buffer.add([_entry("/Kelas/a.txt", "dbid:budi"), _entry("/Kelas/b.txt", "dbid:budi")], T0 + 3)
    assert buffer.take(T0 + 6) == []
    assert [e["name"] for e in buffer.take(T0 + 8.5)] == ["a.txt", "b.txt"]
    assert buffer.take(T0 + 30) == []
    for i in range(30):                                                   # a steady stream
        buffer.add([_entry(f"/Kelas/{i}.txt", "dbid:budi")], T0 + 100 + i)
        if buffer.take(T0 + 100 + i):
            break
    assert i <= remote.MAX_HOLD + 1


def _summaries(entries, new=True):
    names = {"dbid:budi": "Budi", "dbid:sari": "Sari"}
    return remote.summarize(entries, lambda a: names.get(a, ""), lambda p: new)


def test_others_changes_in_words(lang):
    one = _summaries([_entry("/Kelas/catatan.txt", "dbid:budi")])
    assert text.others_lines(one, {}) == [("Budi menambahkan catatan.txt ke folder Kelas.",
                                           "shared")]
    changed = _summaries([_entry("/Kelas/catatan.txt", "dbid:budi")], new=False)
    assert text.others_lines(changed, {})[0][0] == "Budi mengubah catatan.txt di folder Kelas."
    many = _summaries([_entry(f"/Kelas/{n}.txt", "dbid:budi") for n in "abc"])
    assert text.others_lines(many, {})[0][0] == "Budi menambahkan 3 file ke folder Kelas."
    spread = _summaries([_entry("/Kelas/a.txt", "dbid:budi"), _entry("/Kantor/b.txt", "dbid:budi")])
    assert text.others_lines(spread, {})[0][0] == "Budi mengubah 2 file di Dropbox-mu."
    two = _summaries([_entry("/Kelas/a.txt", "dbid:budi"), _entry("/Kelas/b.txt", "dbid:sari"),
                      _entry("/Kelas/c.txt", "dbid:sari")])
    assert text.others_lines(two, {})[0][0] == ("Sari menambahkan 2 file ke folder Kelas. "
                                                "Budi menambahkan a.txt ke folder Kelas.")
    unknown = _summaries([_entry("/Kelas/a.txt", "dbid:who")])
    assert text.others_lines(unknown, {})[0][0].startswith("Seseorang menambahkan")
    assert text.others_lines(one, {"others": False}) == []
    lang("en")
    assert text.others_lines(one, {})[0][0] == "Budi added catatan.txt to the Kelas folder."


def test_crowds_are_counted(lang):
    entries = [_entry(f"/Kelas/{i}.txt", f"dbid:p{i}") for i in range(5)]
    lines = text.others_lines(remote.summarize(entries, lambda a: a[5:], lambda p: False), {})
    assert lines[0][0].endswith("2 orang lain juga mengubah file.")


class FakeFeedClient:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def _next(self, name, *args):
        self.calls.append((name,) + args)
        answer = self.answers[name].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def latest_cursor(self, path="", recursive=True):
        return self._next("cursor", path, recursive)

    def longpoll(self, cursor):
        return self._next("longpoll", cursor)

    def changes_since(self, cursor):
        return self._next("changes", cursor)


def test_the_remote_feed_follows_changes():
    got, lost = [], []
    client = FakeFeedClient({
        "cursor": ["C1", "C9"],
        "longpoll": [{"changes": False}, {"changes": True, "backoff": 5},
                     api.DropboxError("reset", kind="api", summary="reset/"),
                     api.DropboxError("offline", kind="network"),
                     api.DropboxError("offline", kind="network"),
                     api.DropboxError("slow down", kind="rate", retry_after=30),
                     api.DropboxError("revoked", kind="auth")],
        "changes": [([{"name": "x"}], "C2")]})
    feed = remote.RemoteFeed(client, got.append, lambda: lost.append(True))
    assert feed.step() == 0 and feed.cursor == "C1"
    assert feed.step() == 0.0 and got == []
    assert feed.step() == 5.0 and got == [[{"name": "x"}]] and feed.cursor == "C2"
    assert feed.step() == 1.0 and feed.cursor is None                     # Dropbox forgot it
    assert feed.step() == 0 and feed.cursor == "C9"
    assert (feed.step(), feed.step()) == (5.0, 10.0)                      # backing off
    assert feed.step() == 30.0
    assert feed.step() is None and lost == [True]
    assert ("cursor", "", True) in client.calls


def test_the_remote_feed_thread_stops():
    client = FakeFeedClient({"cursor": [api.DropboxError("offline", kind="network")] * 5})
    feed = remote.RemoteFeed(client, lambda e: None).start()
    feed.stop()
    feed._thread.join(2)
    assert not feed._thread.is_alive()


class SharedStore:
    def __init__(self):
        self.data = {}

    def load(self):
        return dict(self.data)

    def save(self, data):
        self.data = dict(data)


def test_what_is_shared_with_you_is_new_only_after_the_first_look(lang):
    client = types.SimpleNamespace(
        received_files=lambda: [{"id": "id:1", "name": "lama.pdf", "owner_display_names": ["Sari"]}],
        shared_folders=lambda: [{"shared_folder_id": "7", "name": "Proyekku",
                                 "access_type": {".tag": "owner"}}])
    store = SharedStore()
    watcher = remote.SharedWatcher(client, store, "dbid:me")
    assert watcher.poll() == []                                           # remembered silently
    assert store.data == {"account": "dbid:me", "ids": ["file:id:1"]}
    client.received_files = lambda: [
        {"id": "id:1", "name": "lama.pdf", "owner_display_names": ["Sari"]},
        {"id": "id:2", "name": "tugas.docx", "owner_display_names": ["Budi"]}]
    client.shared_folders = lambda: [{"shared_folder_id": "8", "name": "Kelas",
                                      "access_type": {".tag": "editor"},
                                      "owner_display_names": ["Budi"]}]
    new = watcher.poll()
    assert new == [{"kind": "file", "name": "tugas.docx", "owner": "Budi"},
                   {"kind": "folder", "name": "Kelas", "owner": "Budi"}]
    assert text.shared_lines(new, {}) == [("Budi membagikan 2 item denganmu.", "shared")]
    assert text.shared_lines(new[:1], {})[0][0] == "Budi membagikan tugas.docx denganmu."
    assert text.shared_lines(new[1:], {})[0][0] == "Budi membagikan folder Kelas denganmu."
    assert text.shared_lines(new, {"shared": False}) == []
    assert watcher.poll() == []
    other = remote.SharedWatcher(client, store, "dbid:someone-else")
    assert other.poll() == []                                             # another account


# ------------------------------------------------------------
# The words
# ------------------------------------------------------------

def test_sync_news_follows_the_settings(lang):
    session3 = sync.Flush(synced=["c.txt"], up_to_date=True, session=["a.txt", "b.txt", "c.txt"])
    assert text.sync_lines(session3, {}) == [("Dropbox-mu sudah up to date.", "synced")]
    assert text.sync_lines(session3, {"up_to_date": False}) == [("c.txt sudah tersinkron.", "synced")]
    both = sync.Flush(synced=["b.txt", "c.txt"], up_to_date=True, session=["a.txt", "b.txt", "c.txt"])
    assert text.sync_lines(both, {"up_to_date": False}) == [("2 file sudah tersinkron.", "synced")]
    assert text.sync_lines(session3, {"up_to_date": False, "progress": False}) == []
    one = sync.Flush(new=["a.txt"], synced=["a.txt"], up_to_date=True, session=["a.txt"])
    assert text.sync_lines(one, {"progress": False}) == [("Dropbox-mu sudah up to date.", "synced")]
    syncing = sync.Flush(new=["a.txt"], session=["a.txt"], remaining=1)
    assert text.sync_lines(syncing, {"progress": False}) == []
    stuck = sync.Flush(stuck=["a.txt", "b.txt"], session=["a.txt", "b.txt"], remaining=2)
    assert text.sync_lines(stuck, {}) == [("2 file belum tersinkron; cek aplikasi Dropbox.", None)]
    assert text.sync_lines(None, {}) == []


def test_the_status_answer(lang):
    base = {"set_up": True, "connected": True, "name": "Budi", "folder": True, "pending": [],
            "stuck": []}
    assert text.status_text(base) == "Dropbox-mu up to date."
    assert text.status_text(dict(base, pending=["a.txt", "b.txt"])) == "Menyinkronkan 2 file…"
    assert text.status_text(dict(base, pending=["a.txt"])) == "Menyinkronkan a.txt…"
    assert text.status_text(dict(base, pending=["a.txt"], stuck=["a.txt"])) == \
        "Menyinkronkan a.txt… a.txt belum tersinkron; cek aplikasi Dropbox."
    assert text.status_text(dict(base, folder=False)) == \
        "Dropbox tersambung sebagai Budi, tapi foldernya tidak ada di komputer ini."
    assert text.status_text(dict(base, connected=False)).startswith("Dropbox belum tersambung")
    assert text.status_text(dict(base, set_up=False)) == "Dropbox belum disiapkan di versi Hariku ini."
    lang("en")
    assert text.status_text(base) == "Your Dropbox is up to date."
    assert text.status_text(dict(base, pending=["a.txt", "b.txt"])) == "Syncing 2 files…"


def test_names_are_joined(lang):
    assert text.join_names(["a"]) == "a" and text.join_names([]) == ""
    assert text.join_names(["a", "b", "c"]) == "a, b dan c"
    lang("en")
    assert text.join_names(["a", "b"]) == "a and b"
    assert text.item_text({"name": "x.pdf", "path_display": "/Kelas/x.pdf"}) == \
        "x.pdf in the Kelas folder"
    assert text.item_text({"name": "x.pdf", "path_display": "/x.pdf"}) == "x.pdf"


def _locale(code):
    with open(os.path.join(EXT_DIR, "locales", f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)["messages"]


def test_both_languages_have_the_same_texts():
    assert set(_locale("en")) == set(_locale("id"))


@pytest.mark.parametrize("code", ["en", "id"])
def test_persona_texts_are_valid(code):
    import re
    import core.persona
    messages = _locale(code)
    fields = lambda s: sorted(re.findall(r"\{(\w+)\}", s))
    variants = [k for k in messages if "@" in k]
    assert len(variants) >= 40
    for key in variants:
        base, persona = key.split("@", 1)
        assert persona in core.persona.PERSONAS and persona != core.persona.DEFAULT, key
        assert base in messages, key
        assert fields(messages[key]) == fields(messages[base]), key
        assert messages[key].strip() and "  " not in messages[key], key
        assert messages[key] != messages[base], key
    main_lines = ("sync_one", "sync_many", "synced_one", "up_to_date", "stuck_one", "stuck_many",
                  "others_added_one", "others_changed_one", "shared_file", "shared_folder",
                  "link_copied", "link_not_in_dropbox", "status_up_to_date")
    for base in main_lines:
        for persona in ("sweet", "bro", "royal", "polite"):
            assert f"{base}@{persona}" in messages, (base, persona)


def test_a_persona_changes_the_words(lang):
    from core import i18n
    flush = sync.Flush(new=["a.txt"], synced=["a.txt"], up_to_date=True, session=["a.txt"])
    plain = text.sync_lines(flush, {})[0][0]
    i18n.set_persona("bro")
    assert text.sync_lines(flush, {})[0][0] == "a.txt udah masuk Dropbox, beres." != plain
    i18n.set_persona("royal")
    lang("en")
    assert text.sync_lines(flush, {})[0][0] == "a.txt has safely reached Dropbox."


@pytest.mark.parametrize("code", ["en", "id"])
def test_the_user_s_own_examples(code, lang):
    lang(code)
    if code == "id":
        assert text._("sync_one", name="laporan.pdf") == "Menyinkronkan laporan.pdf ke Dropbox…"
        assert text._("synced_one", name="laporan.pdf") == "laporan.pdf sudah tersinkron."
        assert text._("up_to_date") == "Dropbox-mu sudah up to date."
        assert text._("shared_file", person="Budi", name="tugas.docx") == \
            "Budi membagikan tugas.docx denganmu."
        assert text._("others_added_one", person="Budi", name="catatan.txt", folder="Kelas") == \
            "Budi menambahkan catatan.txt ke folder Kelas."
        assert text._("link_copied", name="laporan.pdf") == "Link laporan.pdf disalin."
        assert text._("link_not_in_dropbox") == "File ini tidak ada di folder Dropbox."
        assert text._("stuck_one", name="laporan.pdf") == \
            "laporan.pdf belum tersinkron; cek aplikasi Dropbox."
    else:
        assert text._("link_copied", name="laporan.pdf") == "Link to laporan.pdf copied."


@pytest.mark.parametrize("code", ["en", "id"])
def test_the_page_s_keys_are_unique(code):
    messages = _locale(code)
    shown_together = [messages[k] for k in ("lbl_code", "btn_use_code", "chk_progress",
                                            "chk_up_to_date", "chk_others", "chk_shared",
                                            "chk_sounds")]
    for button in ("btn_connect", "btn_disconnect", "btn_cancel_sign_in"):
        keys = []
        for label in shown_together + [messages[button]]:
            assert label.count("&") == 1, label
            keys.append(label[label.index("&") + 1].lower())
        assert len(keys) == len(set(keys)), (code, button, keys)


# ------------------------------------------------------------
# The engine: account, folder, links, news (no threads started)
# ------------------------------------------------------------

class FakeServices:
    def __init__(self):
        self.said, self.notified, self.links = [], [], []
        self.account, self.shared = {}, {}
        self.quiet_now = False
        self.settings_now = {}
        self.changes = 0
        self.event = threading.Event()

    def settings(self):
        return dict(self.settings_now)

    def notify(self, lines):
        self.notified.extend(lines)
        self.event.set()

    def say(self, line):
        self.said.append(line)
        self.event.set()

    def deliver_link(self, url, said_ok, said_failed):
        self.links.append((url, said_ok))
        self.event.set()

    def quiet(self):
        return self.quiet_now

    def changed(self):
        self.changes += 1

    def load_account(self):
        return dict(self.account)

    def save_account(self, data):
        self.account = dict(data)

    def load_shared(self):
        return dict(self.shared)

    def save_shared(self, data):
        self.shared = dict(data)

    def wait(self):
        assert self.event.wait(5), "nothing was said"
        self.event.clear()


class FakeClient:
    def __init__(self):
        self.token = None
        self.path_root = None
        self.transport = types.SimpleNamespace(closed=False, close=self._close)
        self.answer = {"account_id": "dbid:me", "name": {"display_name": "Rafli"},
                       "email": "rafli@example.com", "account_type": {".tag": "basic"},
                       "root_info": {"root_namespace_id": "1", "home_namespace_id": "1"}}
        self.root_names = ["Kelas", "laporan.pdf"]
        self.links, self.revoked = [], False
        self.link_error = None
        self.found = []
        self.search_gate = None
        self.names = {"dbid:budi": "Budi"}
        self.received, self.folders = [], []

    def _close(self):
        self.transport.closed = True

    def current_account(self):
        return self.answer

    def list_folder(self, path, recursive=False, max_pages=20):
        return [{"name": n} for n in self.root_names]

    def shared_link(self, path):
        if self.link_error:
            raise self.link_error
        self.links.append(path)
        return "https://www.dropbox.com/scl/fi/abc" + path.replace(" ", "%20")

    def search(self, query):
        if self.search_gate is not None:
            self.search_gate.wait(5)
        return list(self.found)

    def account_name(self, account_id):
        return self.names.get(account_id, "")

    def revision_count(self, path):
        return 1

    def received_files(self):
        return list(self.received)

    def shared_folders(self):
        return list(self.folders)

    def revoke(self):
        self.revoked = True

    def server_offset(self):
        return 0.0


class FakeWatcher:
    made = []

    def __init__(self, root, on_events, on_error):
        self.root = root
        self.started = False
        FakeWatcher.made.append(self)

    def start(self):
        self.started = True
        return self

    def stop(self, wait=0):
        self.started = False

    def alive(self):
        return self.started


@pytest.fixture
def fake_secret(monkeypatch):
    monkeypatch.setattr(secret, "protect",
                        lambda t: "dpapi1:" + base64.b64encode(t[::-1].encode()).decode())
    monkeypatch.setattr(secret, "unprotect", lambda s: base64.b64decode(s[7:]).decode()[::-1])


@pytest.fixture
def box(tmp_path):
    folder = tmp_path / "Dropbox"
    (folder / "Kelas").mkdir(parents=True)
    (folder / "laporan.pdf").write_text("x")
    return folder


def make_engine(box, client=None, services=None, app_key="appkey123", folder=True, ask=None,
                connected=True, **kwargs):
    client = client or FakeClient()
    services = services or FakeServices()

    def factory(token):
        client.token = token
        return client

    engine = eng.Engine(services, app_key=app_key, client_factory=factory,
                        watcher_factory=FakeWatcher, start_threads=False,
                        folders=lambda: {"personal": str(box)} if folder else {},
                        ask_explorer=ask or (lambda hwnd: ("", True)), **kwargs)
    if connected:
        services.account = {"token": secret.protect("R-1"), "id": "dbid:me", "name": "Rafli",
                            "email": "rafli@example.com", "business": False}
    engine.load()
    return engine, client, services


def test_without_an_app_key_dropbox_is_not_set_up(box, lang):
    engine, _client, services = make_engine(box, app_key="", connected=False)
    assert engine.state == eng.NOT_SET_UP and not engine.set_up()
    assert engine.status_text() == "Dropbox belum disiapkan di versi Hariku ini."
    engine.copy_link_of_window(1, class_of=lambda h: "CabinetWClass")
    assert services.said == ["Dropbox belum disiapkan di versi Hariku ini."]
    assert engine.sign_in() is False


def test_without_a_sign_in_nothing_runs(box, lang):
    engine, client, services = make_engine(box, connected=False)
    assert engine.state == eng.DISCONNECTED and client.token is None
    assert engine.status_text().startswith("Dropbox belum tersambung.")
    engine.copy_link_of_window(1, class_of=lambda h: "CabinetWClass")
    assert services.said == ["Dropbox belum tersambung. Sambungkan di Pengaturan, Dropbox."]


def test_the_stored_sign_in_is_used_and_the_start_checks_the_folder(box, fake_secret):
    engine, client, services = make_engine(box)
    assert engine.state == eng.CONNECTED and client.token == "R-1"
    FakeWatcher.made.clear()
    client.answer["name"] = {"display_name": "Rafli H"}
    assert engine._prepare(engine._stop, engine._generation) is True
    assert engine.account["name"] == "Rafli H" and services.account["name"] == "Rafli H"
    assert services.account["token"] == secret.protect("R-1")               # still there
    assert engine.folder_state == eng.FOLDER_OK and engine.tracker.root == str(box)
    assert FakeWatcher.made[-1].root == str(box) and FakeWatcher.made[-1].started
    assert engine._feed is not None
    engine.shutdown()
    assert client.transport.closed and not FakeWatcher.made[-1].started


def test_a_folder_of_another_account_turns_sync_news_off(box, fake_secret, lang):
    client = FakeClient()
    client.root_names = ["Kantor", "Proyek"]
    (box / "Foto").mkdir()
    engine, _client, _services = make_engine(box, client=client)
    engine._prepare(engine._stop, engine._generation)
    assert engine.folder_state == eng.FOLDER_OTHER and engine.tracker is None
    assert engine.local_folder() is None
    assert engine.status_text().startswith("Dropbox tersambung sebagai Rafli, tapi")


def test_a_team_space_starts_its_paths_at_the_team_root(box, fake_secret):
    client = FakeClient()
    client.answer.update(account_type={".tag": "business"},
                         root_info={"root_namespace_id": "100", "home_namespace_id": "200"})
    engine, _client, services = make_engine(box, client=client, folder=False)
    engine._prepare(engine._stop, engine._generation)
    assert client.path_root == "100" and engine.account["business"] is True
    assert engine.folder_state == eng.FOLDER_MISSING and services.account["root_ns"] == "100"


def _copy(engine, services, hwnd=5, explorer_class="CabinetWClass"):
    engine.copy_link_of_window(hwnd, class_of=lambda h: explorer_class)
    services.wait()


def test_copying_the_link_of_the_file_you_are_on(box, fake_secret, lang):
    chosen = [(str(box / "Kelas" / "tugas akhir.docx"), False)]
    engine, client, services = make_engine(box, ask=lambda hwnd: chosen[0])
    _copy(engine, services)
    assert services.links == [("https://www.dropbox.com/scl/fi/abc/Kelas/tugas%20akhir.docx",
                               "Link tugas akhir.docx disalin.")]
    assert client.links == ["/Kelas/tugas akhir.docx"]
    chosen[0] = (str(box / "Kelas"), True)                        # nothing selected: the folder
    _copy(engine, services)
    assert services.links[-1][1] == "Link Kelas disalin."
    chosen[0] = (r"C:\Users\Budi\Documents\cv.pdf", False)
    _copy(engine, services)
    assert services.said[-1] == "File ini tidak ada di folder Dropbox."
    chosen[0] = (str(box), True)
    _copy(engine, services)
    assert services.said[-1].startswith("Folder Dropbox-nya sendiri")
    client.link_error = api.DropboxError("x", kind="api", summary="path/not_found/")
    chosen[0] = (str(box / "baru.txt"), False)
    _copy(engine, services)
    assert services.said[-1] == "baru.txt belum ada di Dropbox; tunggu sampai tersinkron."
    client.link_error = api.DropboxError("x", kind="network")
    _copy(engine, services)
    assert services.said[-1] == "Dropbox sedang tidak bisa dihubungi. Coba lagi nanti."


def test_copying_needs_file_explorer(box, fake_secret, lang):
    def broken(hwnd):
        raise explorer.ExplorerError("slow")

    engine, _client, services = make_engine(box, ask=broken)
    engine.copy_link_of_window(5, class_of=lambda h: "Notepad")
    assert services.said == ["Buka folder Dropbox di File Explorer dulu, lalu pilih filenya."]
    _copy(engine, services)
    assert services.said[-1] == "Aku tidak bisa tahu file mana yang dipilih di File Explorer."
    engine.ask_explorer = lambda hwnd: ("", True)
    _copy(engine, services)
    assert services.said[-1] == "Aku tidak bisa tahu file mana yang dipilih di File Explorer."


def test_the_engine_tells_sync_news(box, fake_secret, lang):
    engine, _client, services = make_engine(box, clock=lambda: T0)
    flush = sync.Flush(new=["a.txt"], synced=["a.txt"], up_to_date=True, session=["a.txt"])
    engine.tracker = types.SimpleNamespace(tick=lambda now: flush,
                                           status=lambda: {"pending": ["b.txt"], "stuck": []})
    engine._tick(T0)
    assert services.notified == [("a.txt sudah tersinkron.", "synced")]
    assert engine.status_text() == "Menyinkronkan b.txt…"
    services.quiet_now = True                   # your own files are told in quiet hours too
    engine._tick(T0 + 1)
    assert len(services.notified) == 2


def test_the_engine_tells_others_changes(box, fake_secret, lang):
    engine, _client, services = make_engine(box, clock=lambda: T0)
    engine._on_remote_entries([_entry("/Kelas/catatan.txt", "dbid:budi"),
                               _entry("/Kelas/milikku.txt", "dbid:me")])
    engine._tick(T0 + 1)
    assert services.notified == []                                  # a burst may go on
    engine._tick(T0 + 6)
    assert services.notified == [("Budi menambahkan catatan.txt ke folder Kelas.", "shared")]
    services.quiet_now = True
    engine._on_remote_entries([_entry("/Kelas/malam.txt", "dbid:budi")])
    engine._tick(T0 + 20)
    assert len(services.notified) == 1                              # quiet hours: dropped
    services.quiet_now = False
    services.settings_now = {"others": False}
    engine._on_remote_entries([_entry("/Kelas/x.txt", "dbid:budi")])
    engine._tick(T0 + 40)
    assert len(services.notified) == 1


def test_the_engine_tells_what_is_shared(box, fake_secret, lang):
    engine, client, services = make_engine(box)
    client.received = [{"id": "id:1", "name": "lama.pdf", "owner_display_names": ["Sari"]}]
    engine._poll_shared(engine._generation)
    assert services.notified == [] and services.shared["ids"] == ["file:id:1"]
    client.received.append({"id": "id:2", "name": "tugas.docx", "owner_display_names": ["Budi"]})
    engine._poll_shared(engine._generation)
    assert services.notified == [("Budi membagikan tugas.docx denganmu.", "shared")]


def test_a_sign_in_dropbox_no_longer_accepts_is_forgotten(box, fake_secret, lang):
    engine, _client, services = make_engine(box)
    generation = engine._generation
    engine._auth_lost(generation)
    engine._auth_lost(generation)
    assert engine.state == eng.DISCONNECTED and engine.client is None
    assert services.account == {}
    assert services.notified == [("Dropbox terputus. Sambungkan lagi di Pengaturan, Dropbox.", None)]


class FakeFlow:
    def __init__(self, outcome, on_need_code=None, pages=None, **kwargs):
        self.outcome = outcome
        self.on_need_code = on_need_code
        self.codes = []
        self.cancelled = False

    def run(self):
        if self.outcome == "manual":
            self.on_need_code()
            for _i in range(200):
                if self.codes:
                    return "ok", {"refresh_token": "R-" + self.codes[0]}
                time.sleep(0.01)
            return "timeout", None
        return self.outcome

    def give_code(self, code):
        self.codes.append(code)

    def cancel(self):
        self.cancelled = True


def _sign_in(engine, flow):
    engine.sign_in_factory = lambda **kw: (setattr(flow, "on_need_code", kw["on_need_code"])
                                           or flow)
    assert engine.sign_in()
    for _i in range(300):
        if not engine.signing_in():
            return
        time.sleep(0.01)
    raise AssertionError("signing in didn't end")


def test_signing_in_keeps_the_token_encrypted(box, fake_secret, lang):
    engine, client, services = make_engine(box, connected=False)
    _sign_in(engine, FakeFlow(("ok", {"refresh_token": "R-NEW", "access_token": "A"})))
    assert engine.state == eng.CONNECTED and client.token == "R-NEW"
    assert services.account["token"] == secret.protect("R-NEW")
    assert "R-NEW" not in json.dumps(services.account)
    assert services.account["name"] == "Rafli" and services.account["email"] == "rafli@example.com"
    assert services.said[-1] == "Dropbox tersambung sebagai Rafli."


def test_signing_in_with_a_pasted_code(box, fake_secret, lang):
    engine, client, services = make_engine(box, connected=False)
    flow = FakeFlow("manual")
    engine.sign_in_factory = lambda **kw: (setattr(flow, "on_need_code", kw["on_need_code"])
                                           or flow)
    assert engine.sign_in()
    for _i in range(200):
        if engine.state == eng.CODE_NEEDED:
            break
        time.sleep(0.01)
    assert engine.state == eng.CODE_NEEDED
    assert services.said[0].startswith("Kalau Dropbox menampilkan kode")
    engine.give_code("   ")
    engine.give_code("XYZ")
    for _i in range(300):
        if not engine.signing_in():
            break
        time.sleep(0.01)
    assert flow.codes == ["XYZ"] and client.token == "R-XYZ"


def test_a_failed_sign_in_says_why(box, fake_secret, lang):
    engine, _client, services = make_engine(box, connected=False)
    _sign_in(engine, FakeFlow(("timeout", None)))
    assert engine.state == eng.FAILED and engine.problem == "timeout"
    assert services.said[-1] == "Tidak bisa tersambung: waktu untuk masuk habis."
    _sign_in(engine, FakeFlow(("cancelled", None)))
    assert engine.state == eng.DISCONNECTED


def test_disconnecting_forgets_the_sign_in_and_revokes_it(box, fake_secret):
    engine, client, services = make_engine(box)
    services.shared = {"account": "dbid:me", "ids": ["x"]}
    engine.disconnect()
    assert engine.state == eng.DISCONNECTED and services.account == {} and services.shared == {}
    for _i in range(200):
        if client.revoked:
            break
        time.sleep(0.01)
    assert client.revoked


@pytest.mark.parametrize("words, deictic", [
    ("ini", True), ("yang ini", True), ("file ini", True), ("this", True), ("this file", True),
    ("that one", True), ("laporan", False), ("ini laporan", False), ("", False),
])
def test_this_file_or_a_name(words, deictic):
    assert eng.is_deictic(words) is deictic


def test_what_to_look_for():
    assert eng.search_query("file laporan keuangan.") == "laporan keuangan"
    assert eng.search_query("the budget") == "budget"
    assert eng.search_query("dropbox tugas") == "tugas"
    assert eng.search_query("file") == "file"


def _meta(path):
    return {".tag": "file", "name": paths.name_of(path), "path_display": path}


def test_matches_are_ranked():
    exact = [_meta("/Kelas/laporan.pdf"), _meta("/Kelas/laporan final.pdf")]
    assert eng.rank_matches("laporan", exact) == ("one", exact[0])
    assert eng.rank_matches("Laporan.PDF", exact) == ("one", exact[0])
    twins = [_meta("/Kelas/a.pdf"), _meta("/Kantor/a.pdf")]
    assert eng.rank_matches("a", twins) == ("many", twins)
    single = [_meta("/Kelas/laporan final.pdf")]
    assert eng.rank_matches("laporan", single) == ("ask", single[0])
    clear = [_meta("/Kelas/proposal skripsi.docx"), _meta("/Kelas/jadwal.xlsx")]
    assert eng.rank_matches("proposal skrips", clear) == ("ask", clear[0])
    close = [_meta("/a/laporan 1.pdf"), _meta("/a/laporan 2.pdf"), _meta("/a/laporan 3.pdf"),
             _meta("/a/laporan 4.pdf")]
    kind, found = eng.rank_matches("laporan", close)
    assert kind == "many" and len(found) == 3
    assert eng.rank_matches("x", []) == ("none", None)


def test_a_slow_search_answers_by_itself(box, fake_secret, lang):
    engine, client, services = make_engine(box)
    client.search_gate = threading.Event()
    client.found = [_meta("/Kelas/laporan.pdf")]
    job = engine.start_search("laporan")
    assert job.wait(0.05) is None and job.late
    client.search_gate.set()
    services.wait()
    assert services.links == [("https://www.dropbox.com/scl/fi/abc/Kelas/laporan.pdf",
                               "Link laporan.pdf disalin.")]
    client.found = [_meta("/a/laporan 1.pdf"), _meta("/b/laporan 2.pdf")]
    client.search_gate = threading.Event()
    job = engine.start_search("lapor")
    assert job.wait(0.05) is None
    client.search_gate.set()
    services.wait()
    assert services.said[-1] == ("Ada beberapa yang cocok: laporan 1.pdf di folder a dan "
                                 "laporan 2.pdf di folder b. Sebutkan nama lengkapnya.")
    client.search_gate = None
    client.found = []
    assert engine.start_search("xyz").wait(2) == ("none", None)


# ------------------------------------------------------------
# main.py: Aruna, registering, the page
# ------------------------------------------------------------

@pytest.fixture
def dmain(monkeypatch, tmp_data_dir, lang):
    spec = importlib.util.spec_from_file_location("dropbox_main_under_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken = []
    monkeypatch.setattr(module, "speak", spoken.append)
    module.spoken = spoken
    yield module
    try:
        module.teardown()
    except Exception:
        pass


@pytest.mark.parametrize("sentence, slot", [
    ("salin link ini", "ini"),
    ("salin link laporan keuangan", "laporan keuangan"),
    ("tolong salin link laporan.pdf", "laporan.pdf"),
    ("Aruna, salin tautan tugas akhir", "tugas akhir"),
    ("bagikan link ini", "ini"),
    ("copy link to the budget", "the budget"),
    ("copy the link to this file", "this file"),
    ("please copy link for invoice march", "invoice march"),
])
def test_link_sentences_reach_the_extension(dmain, monkeypatch, sentence, slot):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    core.commands.add_intent(dmain.LINK_INTENT, list(dmain.LINK_PATTERNS), dmain._on_link_intent)
    found = core.commands.match_intents(sentence)
    assert found and found[0].intent.id == "Dropbox.link" and found[0].text == slot


def test_this_file_goes_back_to_file_explorer_first(dmain, monkeypatch):
    import core.commands
    monkeypatch.setattr(dmain, "_engine", _fake_engine(None))
    for words in ("ini", "this file", "yang ini"):
        reply = dmain._on_link_intent(core.commands.Request(words, "salin link " + words))
        assert reply.then is dmain.copy_focused_link and not reply.wait
    # Not connected: Aruna says so itself, staying where it is.
    monkeypatch.setattr(dmain, "_engine", _fake_engine(None, problem="Belum tersambung."))
    reply = dmain._on_link_intent(core.commands.Request("ini", "salin link ini"))
    assert reply.say == "Belum tersambung." and reply.then is None


class FakeJob:
    def __init__(self, outcome):
        self.outcome = outcome

    def wait(self, seconds=None):
        return self.outcome


def _fake_engine(outcome, problem=None):
    copied = []
    return types.SimpleNamespace(
        ready_problem=lambda: problem, start_search=lambda q: FakeJob(outcome),
        copy_link_in_background=copied.append, copied=copied)


def _ask(dmain, words):
    import core.commands
    return dmain._on_link_intent(core.commands.Request(words, "salin link " + words))


def test_a_file_found_by_name(dmain, monkeypatch):
    meta = _meta("/Kelas/laporan.pdf")
    engine = _fake_engine(("one", meta))
    monkeypatch.setattr(dmain, "_engine", engine)
    reply = _ask(dmain, "laporan")
    assert reply.wait and engine.copied == [meta]


def test_a_likely_file_is_asked_about(dmain, monkeypatch):
    meta = _meta("/Kelas/laporan final.pdf")
    engine = _fake_engine(("ask", meta))
    monkeypatch.setattr(dmain, "_engine", engine)
    reply = _ask(dmain, "laporan")
    assert reply.say == "Maksudmu laporan final.pdf di folder Kelas? Salin link-nya?"
    assert engine.copied == []
    answer = reply.confirm()
    assert answer.wait and engine.copied == [meta]


def test_several_files_or_none(dmain, monkeypatch, lang):
    many = [_meta("/Kelas/a.pdf"), _meta("/Kantor/a.pdf")]
    monkeypatch.setattr(dmain, "_engine", _fake_engine(("many", many)))
    assert _ask(dmain, "a").say == ("Ada beberapa yang cocok: a.pdf di folder Kelas dan a.pdf di "
                                    "folder Kantor. Sebutkan nama lengkapnya.")
    monkeypatch.setattr(dmain, "_engine", _fake_engine(("none", None)))
    assert _ask(dmain, "file zzz").say == "Tidak ada yang bernama zzz di Dropbox-mu."
    monkeypatch.setattr(dmain, "_engine", _fake_engine(None))
    assert _ask(dmain, "laporan").wait                               # answers later
    monkeypatch.setattr(dmain, "_engine", _fake_engine(None, problem="Belum tersambung."))
    assert _ask(dmain, "laporan").say == "Belum tersambung."
    assert _ask(dmain, "   ") is None and _ask(dmain, "x" * 300) is None
    lang("en")
    monkeypatch.setattr(dmain, "_engine", _fake_engine(("ask", _meta("/Work/budget.xlsx"))))
    assert _ask(dmain, "budget").say == "Do you mean budget.xlsx in the Work folder? Copy its link?"


def _dropbox_commands(dmain, language):
    import core.commands
    from tests.test_commands import real_actions
    actions = real_actions(language)
    candidates = core.commands.commands(actions)
    for name, description, _title, _callback, aliases, _answers in dmain.ACTIONS:
        candidates.append(core.commands.Command(dmain.action_id(name), dmain._(description),
                                                list(aliases)))
    return candidates


@pytest.mark.parametrize("language", ["id", "en"])
@pytest.mark.parametrize("sentence, action", [
    ("salin link", "Dropbox.copy_link"), ("salin link dropbox", "Dropbox.copy_link"),
    ("copy link", "Dropbox.copy_link"), ("copy this link", "Dropbox.copy_link"),
    ("salin tautan", "Dropbox.copy_link"),
    ("dropbox", "Dropbox.status"), ("status dropbox", "Dropbox.status"),
    ("dropbox status", "Dropbox.status"), ("is dropbox up to date", "Dropbox.status"),
])
def test_what_aruna_runs(dmain, lang, language, sentence, action):
    import core.commands
    lang(language)
    found = core.commands.match(sentence, _dropbox_commands(dmain, language))
    assert found.kind == "run" and found.best.id == action, found


def test_copying_a_link_is_not_mistaken_for_a_reminder(dmain, monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    intent = core.commands.add_intent(dmain.LINK_INTENT, list(dmain.LINK_PATTERNS),
                                      dmain._on_link_intent)
    candidates = _dropbox_commands(dmain, "id")
    decision = core.commands.decide("salin link laporan", candidates, parse=lambda t: None,
                                    intent_candidates=[intent])
    assert decision.kind == "intent" and decision.intents[0].text == "laporan"
    assert decision.fallback.kind in ("run", "confirm", "unknown")
    decision = core.commands.decide("salin link", candidates, parse=lambda t: None,
                                    intent_candidates=[intent])
    assert decision.kind == "run" and decision.action_id == "Dropbox.copy_link"


def test_the_hotkey_uses_the_window_with_the_focus(dmain, monkeypatch):
    windows = []
    monkeypatch.setattr(dmain, "_engine", types.SimpleNamespace(
        copy_link_of_window=windows.append, status_text=lambda: "Dropbox-mu up to date."))
    monkeypatch.setattr(dmain.explorer, "foreground_window", lambda: 4242)
    dmain.copy_focused_link()
    assert windows == [4242]
    dmain.say_status()
    assert dmain.spoken == ["Dropbox-mu up to date."]


def test_register_and_teardown(dmain, fresh_event_bus, monkeypatch):
    import core.commands
    import core.hotkeys
    import core.preferences
    actions, panels = [], []
    monkeypatch.setattr(core.hotkeys, "register_action",
                        lambda *args, **kwargs: actions.append((args, kwargs)))
    monkeypatch.setattr(core.preferences, "register_panel", lambda *args: panels.append(args))
    monkeypatch.setattr(core.commands, "_intents", {})
    monkeypatch.setattr(core.commands, "_answer_actions", set())
    dmain.register(fresh_event_bus)
    assert {args[1] for args, _kw in actions} == {"copy_link", "status"}
    for args, kwargs in actions:
        assert args[0] == "Dropbox" and args[3] is None and kwargs == {}      # no default keys
    assert core.commands.is_answer_action("Dropbox.status")
    assert not core.commands.is_answer_action("Dropbox.copy_link")   # Aruna closes first
    assert [i.id for i in core.commands.intents()] == ["Dropbox.link"]
    assert "salin link" in core.commands.aliases_for("Dropbox.copy_link")
    assert panels[0][0] == "Dropbox"
    assert dmain._engine.state in (eng.NOT_SET_UP, eng.DISCONNECTED)
    dmain.teardown()
    assert core.commands.intents() == [] and core.commands.aliases_for("Dropbox.status") == []
    assert dmain._engine is None


def test_settings_are_checked(dmain):
    assert dmain.normalize_settings({"progress": False, "sounds": "no", "extra": 1}) == \
        {"progress": False, "up_to_date": True, "others": True, "shared": True, "sounds": True}
    assert dmain.normalize_settings(None) == dmain.DEFAULT_SETTINGS


def test_the_services_store_and_announce(dmain, monkeypatch, tmp_data_dir):
    played = []
    monkeypatch.setattr(dmain.core.sounds, "play_sound", played.append)
    monkeypatch.setattr(dmain, "_active", True)
    services = dmain.Services()
    services.save_account({"token": "dpapi1:abc", "id": "dbid:me"})
    assert services.load_account() == {"token": "dpapi1:abc", "id": "dbid:me"}
    with open(os.path.join(tmp_data_dir, "DropboxAccount.json"), encoding="utf-8") as f:
        assert json.load(f)["token"] == "dpapi1:abc"
    services.save_shared({"ids": ["a"]})
    assert services.load_shared() == {"ids": ["a"]}
    services.notify([("laporan.pdf sudah tersinkron.", "synced"), ("x", None)])
    assert dmain.spoken == ["laporan.pdf sudah tersinkron.", "x"]
    assert [os.path.basename(p) for p in played] == ["synced.wav"]
    dmain._settings["sounds"] = False
    services.notify([("y", "shared")])
    assert len(played) == 1 and dmain.spoken[-1] == "y"
    copied = []
    monkeypatch.setattr(dmain.core.api, "set_clipboard", lambda t: copied.append(t) or True)
    services.deliver_link("https://db.tt/x", "Link x disalin.", "gagal")
    assert copied == ["https://db.tt/x"] and dmain.spoken[-1] == "Link x disalin."
    monkeypatch.setattr(dmain.core.api, "set_clipboard", lambda t: False)
    services.deliver_link("https://db.tt/x", "Link x disalin.", "gagal")
    assert dmain.spoken[-1] == "gagal"


@pytest.mark.parametrize("state, account, expected, button, enabled, code", [
    (eng.NOT_SET_UP, None, "Dropbox belum disiapkan di versi Hariku ini: belum ada App key Dropbox.",
     "&Sambungkan Dropbox", False, False),
    (eng.DISCONNECTED, None, "Belum tersambung.", "&Sambungkan Dropbox", True, False),
    (eng.SIGNING_IN, None, "Menunggu kamu masuk di browser…", "&Batalkan masuk", True, False),
    (eng.CODE_NEEDED, None, "Masuk di browser, lalu salin kode dari Dropbox ke kolom Kode di bawah.",
     "&Batalkan masuk", True, True),
    (eng.CONNECTED, {"name": "Rafli", "email": "rafli@example.com"},
     "Tersambung sebagai Rafli (rafli@example.com).", "&Putuskan Dropbox", True, False),
    (eng.FAILED, None, "Tidak bisa tersambung: kodenya tidak diterima Dropbox.",
     "&Sambungkan Dropbox", True, False),
])
def test_what_the_page_shows(dmain, monkeypatch, state, account, expected, button, enabled, code):
    fake = types.SimpleNamespace(state=state, account=account, problem="code", folder=None,
                                 folder_state=eng.FOLDER_UNKNOWN,
                                 connected=lambda: state == eng.CONNECTED,
                                 local_folder=lambda: r"C:\Users\Rafli\Dropbox")
    monkeypatch.setattr(dmain, "_engine", fake)
    monkeypatch.setattr(dmain.paths, "read_info", lambda: {})
    view = dmain._view()
    assert (view["account"], view["button"], view["button_enabled"], view["code"]) == \
        (expected, button, enabled, code)
    if state == eng.CONNECTED:
        assert view["folder"] == r"C:\Users\Rafli\Dropbox"
    else:
        assert view["folder"].startswith("Aplikasi Dropbox tidak ada di komputer ini")


def test_the_page_s_button(dmain, monkeypatch):
    calls = []
    fake = types.SimpleNamespace(
        connected=lambda: False, signing_in=lambda: False,
        sign_in=lambda pages=None: calls.append(("sign_in", sorted(pages))),
        disconnect=lambda: calls.append("disconnect"),
        cancel_sign_in=lambda: calls.append("cancel"),
        give_code=lambda code: calls.append(("code", code)))
    monkeypatch.setattr(dmain, "_engine", fake)
    dmain._PageActions.press()
    fake.signing_in = lambda: True
    dmain._PageActions.press()
    fake.connected = lambda: True
    dmain._PageActions.press()
    dmain._PageActions.give_code("ABC")
    assert calls == [("sign_in", ["done", "failed"]), "cancel", "disconnect", ("code", "ABC")]
    assert dmain.spoken == ["Dropbox diputuskan."]
    refreshed = []
    dmain._PageActions.add_listener(lambda: refreshed.append(1))

    def gone():
        raise RuntimeError("the page is gone")

    dmain._PageActions.add_listener(gone)
    dmain._refresh_pages()
    dmain._refresh_pages()
    assert refreshed == [1, 1] and gone not in dmain._listeners


# ------------------------------------------------------------
# The sounds
# ------------------------------------------------------------

def test_the_sounds_ship_and_are_what_the_generator_makes():
    import dropbox_sounds
    for name, make in dropbox_sounds.SOUNDS:
        path = os.path.join(EXT_DIR, "sounds", name)
        with open(path, "rb") as f:
            data = f.read()
        assert data == make(), name
        with wave.open(io.BytesIO(data)) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, 44100)
            seconds = w.getnframes() / w.getframerate()
            frames = w.readframes(w.getnframes())
        assert 0.3 <= seconds <= 1.0, name
        samples = struct.unpack("<%dh" % (len(frames) // 2), frames)
        assert max(abs(s) for s in samples) <= 0.4 * 32767, name
        assert abs(samples[0]) < 200 and abs(samples[-1]) < 200, name      # no clicks
        left, right = samples[0::2], samples[1::2]
        assert left != right, name                                         # stereo

