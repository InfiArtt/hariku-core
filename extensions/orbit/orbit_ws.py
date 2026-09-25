# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
A small WebSocket (RFC 6455) implementation for Orbit, standard library only.

The Orbit server (servers/orbit) and Hariku's Orbit extension (extensions/orbit)
use the same file: the extension keeps an identical copy, and a test checks
that the two match. Change this one and copy it over.

  * The opening handshake, both sides: make_key, accept_key, client_request,
    split_head, parse_head, check_request, server_response, check_response,
    http_response (plain HTTP answers such as the health check).
  * Frames: encode_frame (masked when a client sends, unmasked from a server)
    and FrameDecoder, which reassembles fragmented messages and enforces the
    rules: the right masking, no reserved bits, known opcodes, control frames
    of at most 125 bytes that are never fragmented, valid UTF-8 in text, and a
    size limit (close code 1009 above it).
  * Close frames: close_payload, parse_close.
  * WebSocketClient: a blocking client over socket and ssl, for ws:// (this
    computer only) and wss:// (certificates verified). It answers pings and
    close frames itself. It is meant for one thread: whoever reads also
    sends, so a TLS connection is never used from two threads at once.

No asyncio here (the compiled Hariku doesn't include it): the server feeds
the same codec from asyncio streams.
"""

import base64
import collections
import hashlib
import json
import os
import socket
import ssl
import struct
import time
import urllib.parse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
USER_AGENT = "Orbit-WebSocket/1.0"

OP_CONT, OP_TEXT, OP_BINARY = 0x0, 0x1, 0x2
OP_CLOSE, OP_PING, OP_PONG = 0x8, 0x9, 0xA
CONTROL_OPS = frozenset((OP_CLOSE, OP_PING, OP_PONG))
KNOWN_OPS = frozenset((OP_CONT, OP_TEXT, OP_BINARY)) | CONTROL_OPS

CLOSE_NORMAL = 1000
CLOSE_GOING_AWAY = 1001
CLOSE_PROTOCOL = 1002
CLOSE_UNSUPPORTED = 1003
CLOSE_NO_STATUS = 1005        # never sent: a close frame without a code
CLOSE_ABNORMAL = 1006         # never sent: the connection dropped without a close frame
CLOSE_BAD_DATA = 1007
CLOSE_POLICY = 1008
CLOSE_TOO_BIG = 1009
CLOSE_INTERNAL = 1011

MAX_HEAD = 8192                   # bytes of HTTP head, either side
MAX_CONTROL = 125
DEFAULT_MAX_MESSAGE = 64 * 1024   # bytes of one message, fragments together
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


class WebSocketError(Exception):
    """Anything that went wrong with a WebSocket connection."""


class HandshakeError(WebSocketError):
    """The opening handshake failed. `status` is the HTTP status to answer
    with (server side) or the one received (client side)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class ProtocolError(WebSocketError):
    """The other side broke the protocol; close with `code`."""

    def __init__(self, message, code=CLOSE_PROTOCOL):
        super().__init__(message)
        self.code = code


class ConnectionClosed(WebSocketError):
    """The connection is closed: `code` and `reason` from the close frame, or
    1006 when it dropped without one."""

    def __init__(self, code=CLOSE_ABNORMAL, reason=""):
        super().__init__(f"connection closed ({code}{': ' + reason if reason else ''})")
        self.code = code
        self.reason = reason


# ------------------------------------------------------------
# The opening handshake
# ------------------------------------------------------------

def make_key():
    """A fresh Sec-WebSocket-Key: 16 random bytes, base64."""
    return base64.b64encode(os.urandom(16)).decode("ascii")


def accept_key(key):
    """The Sec-WebSocket-Accept a server answers `key` with."""
    digest = hashlib.sha1((key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def parse_url(url):
    """(secure, host, port, path) of a ws:// or wss:// address."""
    parts = urllib.parse.urlsplit(str(url or "").strip())
    scheme = parts.scheme.lower()
    if scheme not in ("ws", "wss"):
        raise ValueError("the address must start with ws:// or wss://")
    host = parts.hostname
    if not host:
        raise ValueError("the address has no host")
    try:
        port = parts.port
    except ValueError:
        raise ValueError("the address has an invalid port") from None
    secure = scheme == "wss"
    port = port or (443 if secure else 80)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return secure, host, port, path


def is_local(host):
    """Whether `host` is this computer."""
    return str(host or "").strip("[]").lower() in LOCAL_HOSTS


def _host_header(host, port, secure):
    shown = f"[{host}]" if ":" in host else host
    return shown if port == (443 if secure else 80) else f"{shown}:{port}"


def client_request(host, port, path, key, secure=False, headers=None):
    """The client's opening request, as bytes."""
    lines = [f"GET {path} HTTP/1.1",
             f"Host: {_host_header(host, port, secure)}",
             "Upgrade: websocket",
             "Connection: Upgrade",
             f"Sec-WebSocket-Key: {key}",
             "Sec-WebSocket-Version: 13"]
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


def split_head(buffer, limit=MAX_HEAD):
    """(head, rest) once `buffer` holds a whole HTTP head, else None. A head
    longer than `limit` raises HandshakeError (431)."""
    end = buffer.find(b"\r\n\r\n")
    if end < 0:
        if len(buffer) > limit:
            raise HandshakeError("the request head is too long", 431)
        return None
    if end + 4 > limit:
        raise HandshakeError("the request head is too long", 431)
    return buffer[:end], buffer[end + 4:]


def parse_head(head):
    """(start line, {lower-case header name: value}) of an HTTP head.
    Repeated headers are joined with ", "."""
    try:
        text = head.decode("latin-1")
    except Exception:
        raise HandshakeError("unreadable head") from None
    lines = text.split("\r\n")
    start = lines[0].strip()
    if not start:
        raise HandshakeError("empty request")
    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        name = name.strip().lower()
        if not sep or not name or " " in name:
            raise HandshakeError("a malformed header line")
        value = value.strip()
        headers[name] = f"{headers[name]}, {value}" if name in headers else value
    return start, headers


def _tokens(value):
    return {t.strip().lower() for t in str(value or "").split(",") if t.strip()}


def check_request(start_line, headers):
    """Check a client's opening request: (path, key), or HandshakeError with
    the status to answer (400, 405, 426)."""
    parts = start_line.split(" ")
    if len(parts) != 3:
        raise HandshakeError("a malformed request line")
    method, target, version = parts
    if version != "HTTP/1.1":
        raise HandshakeError("HTTP/1.1 is needed", 505)
    if method != "GET":
        raise HandshakeError("only GET opens a WebSocket", 405)
    if "websocket" not in _tokens(headers.get("upgrade")):
        raise HandshakeError("not a WebSocket upgrade", 426)
    if "upgrade" not in _tokens(headers.get("connection")):
        raise HandshakeError("the Connection header lacks Upgrade")
    if headers.get("sec-websocket-version", "").strip() != "13":
        raise HandshakeError("only WebSocket version 13 is supported", 426)
    key = headers.get("sec-websocket-key", "").strip()
    try:
        raw = base64.b64decode(key.encode("ascii"), validate=True)
    except Exception:
        raw = b""
    if len(raw) != 16:
        raise HandshakeError("a bad Sec-WebSocket-Key")
    return target, key


def server_response(key, headers=None):
    """The server's 101 answer to a request with `key`, as bytes."""
    lines = ["HTTP/1.1 101 Switching Protocols",
             "Upgrade: websocket",
             "Connection: Upgrade",
             f"Sec-WebSocket-Accept: {accept_key(key)}"]
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


_REASONS = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found",
            405: "Method Not Allowed", 426: "Upgrade Required",
            431: "Request Header Fields Too Large", 503: "Service Unavailable",
            505: "HTTP Version Not Supported"}


def http_response(status, body=b"", content_type="text/plain; charset=utf-8", headers=None):
    """A plain HTTP/1.1 answer that closes the connection, as bytes."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    lines = [f"HTTP/1.1 {status} {_REASONS.get(status, 'Error')}",
             f"Content-Type: {content_type}",
             f"Content-Length: {len(body)}",
             "Cache-Control: no-store",
             "Connection: close"]
    if status == 426:
        lines.append("Sec-WebSocket-Version: 13")
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


def check_response(start_line, headers, key):
    """Check the server's answer to our request with `key`; HandshakeError
    (with the status received) when it isn't a proper 101."""
    parts = start_line.split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/1.1"):
        raise HandshakeError("not an HTTP/1.1 answer", 0)
    try:
        status = int(parts[1])
    except ValueError:
        raise HandshakeError("an unreadable status", 0) from None
    if status != 101:
        raise HandshakeError(f"the server answered {status}", status)
    if "websocket" not in _tokens(headers.get("upgrade")):
        raise HandshakeError("the answer is not a WebSocket upgrade", status)
    if "upgrade" not in _tokens(headers.get("connection")):
        raise HandshakeError("the answer's Connection header lacks Upgrade", status)
    if headers.get("sec-websocket-accept", "").strip() != accept_key(key):
        raise HandshakeError("a wrong Sec-WebSocket-Accept", status)


# ------------------------------------------------------------
# Frames
# ------------------------------------------------------------

def apply_mask(data, key):
    """XOR `data` with the 4-byte masking `key` (masking and unmasking are the same)."""
    n = len(data)
    if not n:
        return b""
    repeated = (key * (n // 4 + 1))[:n]
    return (int.from_bytes(data, "little") ^ int.from_bytes(repeated, "little")).to_bytes(n, "little")


def encode_frame(opcode, payload=b"", mask=False, fin=True):
    """One frame, as bytes. A client masks (mask=True); a server doesn't.
    Text may be given as str."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    payload = bytes(payload)
    if opcode not in KNOWN_OPS:
        raise ValueError(f"unknown opcode {opcode}")
    if opcode in CONTROL_OPS and (len(payload) > MAX_CONTROL or not fin):
        raise ValueError("a control frame carries at most 125 bytes and is never fragmented")
    head = bytearray([(0x80 if fin else 0) | opcode])
    bit = 0x80 if mask else 0
    n = len(payload)
    if n < 126:
        head.append(bit | n)
    elif n < 65536:
        head.append(bit | 126)
        head += struct.pack("!H", n)
    else:
        head.append(bit | 127)
        head += struct.pack("!Q", n)
    if mask:
        key = os.urandom(4)
        head += key
        payload = apply_mask(payload, key)
    return bytes(head) + payload


_VALID_CLOSE_CODES = frozenset((1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011))


def close_payload(code=CLOSE_NORMAL, reason=""):
    """A close frame's payload: the code and a reason of at most 123 bytes."""
    data = str(reason or "").encode("utf-8")[:123]
    while data:
        try:
            data.decode("utf-8")
            break
        except UnicodeDecodeError:
            data = data[:-1]        # don't cut a character in half
    return struct.pack("!H", int(code)) + data


def parse_close(payload):
    """(code, reason) of a close frame's payload; ProtocolError when it is invalid."""
    if not payload:
        return CLOSE_NO_STATUS, ""
    if len(payload) == 1:
        raise ProtocolError("a close frame with half a code")
    code = struct.unpack("!H", payload[:2])[0]
    if code not in _VALID_CLOSE_CODES and not 3000 <= code <= 4999:
        raise ProtocolError(f"an invalid close code {code}")
    try:
        reason = payload[2:].decode("utf-8")
    except UnicodeDecodeError:
        raise ProtocolError("a close reason that isn't UTF-8", CLOSE_BAD_DATA) from None
    return code, reason


class FrameDecoder:
    """Turns received bytes into messages. feed(data) returns a list of
    (opcode, payload): OP_TEXT with a str, OP_BINARY with bytes (fragments put
    together), or a control frame (OP_PING, OP_PONG, OP_CLOSE) with bytes, in
    the order they came. Raises ProtocolError (with its close code) when the
    other side breaks the rules; the connection must then be closed.

    `expect_masked`: a server expects masked frames (from clients), a client
    unmasked ones. `max_message`: the most bytes one message may have."""

    def __init__(self, expect_masked, max_message=DEFAULT_MAX_MESSAGE):
        self.expect_masked = bool(expect_masked)
        self.max_message = int(max_message)
        self._buffer = bytearray()
        self._opcode = None           # the message being put together from fragments
        self._parts = []
        self._size = 0

    def feed(self, data):
        self._buffer += data
        out = []
        while True:
            frame = self._next_frame()
            if frame is None:
                return out
            fin, opcode, payload = frame
            if opcode in CONTROL_OPS:
                out.append((opcode, payload))
            elif opcode == OP_CONT:
                if self._opcode is None:
                    raise ProtocolError("a continuation frame with no message to continue")
                self._add(payload, fin, out)
            else:
                if self._opcode is not None:
                    raise ProtocolError("a new message before the last one ended")
                self._opcode = opcode
                self._add(payload, fin, out)

    def _add(self, payload, fin, out):
        self._size += len(payload)
        if self._size > self.max_message:
            raise ProtocolError("the message is too big", CLOSE_TOO_BIG)
        self._parts.append(payload)
        if not fin:
            return
        data = b"".join(self._parts)
        opcode = self._opcode
        self._opcode, self._parts, self._size = None, [], 0
        if opcode == OP_TEXT:
            try:
                out.append((OP_TEXT, data.decode("utf-8")))
            except UnicodeDecodeError:
                raise ProtocolError("text that isn't UTF-8", CLOSE_BAD_DATA) from None
        else:
            out.append((OP_BINARY, data))

    def _next_frame(self):
        buffer = self._buffer
        if len(buffer) < 2:
            return None
        first, second = buffer[0], buffer[1]
        fin = bool(first & 0x80)
        if first & 0x70:
            raise ProtocolError("reserved bits are set (no extensions were agreed)")
        opcode = first & 0x0F
        if opcode not in KNOWN_OPS:
            raise ProtocolError(f"an unknown opcode {opcode}")
        masked = bool(second & 0x80)
        if masked != self.expect_masked:
            raise ProtocolError("frames from a client must be masked, from a server not"
                                if self.expect_masked else "a server must not mask its frames")
        length = second & 0x7F
        offset = 2
        if length == 126:
            if len(buffer) < 4:
                return None
            length = struct.unpack("!H", bytes(buffer[2:4]))[0]
            offset = 4
        elif length == 127:
            if len(buffer) < 10:
                return None
            length = struct.unpack("!Q", bytes(buffer[2:10]))[0]
            if length >> 63:
                raise ProtocolError("a frame length with its top bit set")
            offset = 10
        if opcode in CONTROL_OPS and (not fin or length > MAX_CONTROL):
            raise ProtocolError("control frames carry at most 125 bytes and are never fragmented")
        if length > self.max_message:
            raise ProtocolError("the message is too big", CLOSE_TOO_BIG)
        key = b""
        if masked:
            if len(buffer) < offset + 4:
                return None
            key = bytes(buffer[offset:offset + 4])
            offset += 4
        if len(buffer) < offset + length:
            return None
        payload = bytes(buffer[offset:offset + length])
        del buffer[:offset + length]
        if masked:
            payload = apply_mask(payload, key)
        return fin, opcode, payload


# ------------------------------------------------------------
# A blocking client
# ------------------------------------------------------------

class WebSocketClient:
    """A connected client. Use one thread: recv() (which also answers pings
    and close frames) and the send methods from the same thread.

        ws = WebSocketClient.connect("wss://example.org/orbit/ws", timeout=10)
        ws.send_json({"t": "hello"})
        text = ws.recv(timeout=1.0)          # None when nothing came in time
        ws.close()
    """

    def __init__(self, sock, leftover=b"", max_message=DEFAULT_MAX_MESSAGE):
        self._sock = sock
        self._decoder = FrameDecoder(expect_masked=False, max_message=max_message)
        self._frames = collections.deque()
        self._close_sent = False
        self.closed = False
        self.close_code = None
        self.close_reason = ""
        self.last_received = time.monotonic()
        self.last_pong = None
        if leftover:
            self._take(leftover)

    @classmethod
    def connect(cls, url, timeout=10.0, ssl_context=None, headers=None, allow_remote_ws=False,
                max_message=DEFAULT_MAX_MESSAGE):
        """Open a connection and do the handshake. ws:// is refused for any
        host but this computer (the traffic wouldn't be encrypted), unless
        allow_remote_ws. wss:// verifies the server's certificate and name."""
        secure, host, port, path = parse_url(url)
        if not secure and not allow_remote_ws and not is_local(host):
            raise WebSocketError("ws:// is only for this computer; use wss://")
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            if secure:
                context = ssl_context or ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=host)
            key = make_key()
            extra = {"User-Agent": USER_AGENT}
            extra.update(headers or {})
            sock.sendall(client_request(host, port, path, key, secure, extra))
            buffer = b""
            deadline = time.monotonic() + timeout
            while True:
                found = split_head(buffer)
                if found is not None:
                    break
                left = deadline - time.monotonic()
                if left <= 0:
                    raise HandshakeError("the server didn't answer in time", 0)
                sock.settimeout(left)
                chunk = sock.recv(4096)
                if not chunk:
                    raise HandshakeError("the server closed the connection", 0)
                buffer += chunk
            head, rest = found
            start, answer = parse_head(head)
            check_response(start, answer, key)
            return cls(sock, rest, max_message=max_message)
        except BaseException:
            try:
                sock.close()
            except OSError:
                pass
            raise

    # --- sending ---------------------------------------------------------------------

    def _send_frame(self, opcode, payload=b""):
        if self.closed or self._close_sent:
            raise ConnectionClosed(self.close_code or CLOSE_ABNORMAL, self.close_reason)
        try:
            self._sock.sendall(encode_frame(opcode, payload, mask=True))
        except OSError as e:
            self._drop()
            raise ConnectionClosed(CLOSE_ABNORMAL, str(e)) from None

    def send_text(self, text):
        self._send_frame(OP_TEXT, str(text))

    def send_json(self, obj):
        self.send_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))

    def ping(self, data=b""):
        self._send_frame(OP_PING, data)

    # --- receiving -------------------------------------------------------------------

    def _take(self, data):
        try:
            self._frames.extend(self._decoder.feed(data))
        except ProtocolError as e:
            self.close(e.code, str(e)[:100])
            raise ConnectionClosed(e.code, str(e)) from None

    def recv(self, timeout=None):
        """The next message (str for text, bytes for binary), or None when
        nothing came within `timeout` seconds (None: wait as long as it takes).
        Raises ConnectionClosed when the connection is closed."""
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while True:
            while self._frames:
                opcode, payload = self._frames.popleft()
                if opcode == OP_PING:
                    try:
                        self._send_frame(OP_PONG, payload)
                    except ConnectionClosed:
                        pass
                elif opcode == OP_PONG:
                    self.last_pong = time.monotonic()
                elif opcode == OP_CLOSE:
                    try:
                        code, reason = parse_close(payload)
                    except ProtocolError as e:
                        code, reason = e.code, str(e)
                    self.close_code, self.close_reason = code, reason
                    if not self._close_sent:
                        echo = CLOSE_NORMAL if code in (CLOSE_NO_STATUS,) else code
                        try:
                            self._sock.sendall(encode_frame(OP_CLOSE, close_payload(echo), mask=True))
                        except OSError:
                            pass
                        self._close_sent = True
                    self._drop()
                    raise ConnectionClosed(code, reason)
                else:
                    return payload
            if self.closed:
                raise ConnectionClosed(self.close_code or CLOSE_ABNORMAL, self.close_reason)
            if deadline is None:
                wait = None
            else:
                wait = deadline - time.monotonic()
                if wait <= 0:
                    return None
            try:
                self._sock.settimeout(wait)
                chunk = self._sock.recv(65536)
            except socket.timeout:
                return None
            except ssl.SSLWantReadError:
                continue
            except OSError as e:
                self._drop()
                raise ConnectionClosed(CLOSE_ABNORMAL, str(e)) from None
            if not chunk:
                self._drop()
                raise ConnectionClosed(self.close_code or CLOSE_ABNORMAL, "the connection was lost")
            self.last_received = time.monotonic()
            self._take(chunk)

    def recv_json(self, timeout=None):
        """The next message decoded from JSON, or None on a timeout."""
        text = self.recv(timeout)
        if text is None:
            return None
        if isinstance(text, bytes):
            raise WebSocketError("a binary message where JSON was expected")
        return json.loads(text)

    # --- closing ---------------------------------------------------------------------

    def close(self, code=CLOSE_NORMAL, reason="", wait=1.0):
        """Say goodbye (a close frame), wait up to `wait` seconds for the other
        side's, then close the socket. Safe to call more than once."""
        if self.closed:
            return
        if not self._close_sent:
            self._close_sent = True
            try:
                self._sock.sendall(encode_frame(OP_CLOSE, close_payload(code, reason), mask=True))
            except OSError:
                self._drop()
                return
        deadline = time.monotonic() + max(0.0, wait)
        while not self.closed and time.monotonic() < deadline:
            try:
                self._sock.settimeout(max(0.01, deadline - time.monotonic()))
                chunk = self._sock.recv(65536)
            except (OSError, ssl.SSLError):
                break
            if not chunk:
                break
            try:
                frames = self._decoder.feed(chunk)
            except ProtocolError:
                break
            if any(op == OP_CLOSE for op, _payload in frames):
                break
        self._drop()

    def _drop(self):
        self.closed = True
        try:
            self._sock.close()
        except OSError:
            pass
