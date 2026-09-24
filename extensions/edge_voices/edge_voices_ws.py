# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
A small WebSocket client (RFC 6455) on the standard library's socket and ssl,
enough for the Edge speech service: the opening handshake, masked text and
binary frames from the client, fragmented messages, ping/pong and close. No
extensions (such as compression) are requested or accepted.

The framing works on any object with sendall() and recv(), so the tests can
use an in-memory socket.
"""
import base64
import hashlib
import os
import socket
import ssl

OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

ACCEPT_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MESSAGE_BYTES = 32 * 1024 * 1024
MAX_HANDSHAKE_BYTES = 64 * 1024


class WebSocketError(Exception):
    pass


class HandshakeError(WebSocketError):
    """The server answered the upgrade with something other than 101."""

    def __init__(self, status, reason="", headers=None):
        self.status = status
        self.headers = headers or {}
        super().__init__(f"the server answered {status} {reason}".strip())


class ConnectionClosed(WebSocketError):
    def __init__(self, code=None, reason=""):
        self.code = code
        self.reason = reason
        super().__init__(f"the connection was closed ({code} {reason})".strip())


def apply_mask(data, key):
    """XOR `data` with the 4-byte `key`, repeated (masking and unmasking)."""
    data = bytes(data)
    if not data:
        return b""
    repeated = (bytes(key) * (len(data) // 4 + 1))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(repeated, "big")).to_bytes(len(data), "big")


def encode_frame(opcode, payload, fin=True, mask=True, mask_key=None):
    """One frame. Clients must mask what they send (RFC 6455 5.3)."""
    payload = bytes(payload)
    first = (0x80 if fin else 0) | (opcode & 0x0F)
    length = len(payload)
    mask_bit = 0x80 if mask else 0
    if length < 126:
        header = bytes([first, mask_bit | length])
    elif length < 1 << 16:
        header = bytes([first, mask_bit | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first, mask_bit | 127]) + length.to_bytes(8, "big")
    if not mask:
        return header + payload
    key = os.urandom(4) if mask_key is None else bytes(mask_key)
    if len(key) != 4:
        raise ValueError("a mask key is 4 bytes")
    return header + key + apply_mask(payload, key)


class FrameReader:
    """Reads frames from recv(n) (returns up to n bytes, b"" at the end)."""

    def __init__(self, recv, initial=b""):
        self._recv = recv
        self._buffer = bytearray(initial)

    def _read(self, count):
        while len(self._buffer) < count:
            chunk = self._recv(max(4096, count - len(self._buffer)))
            if not chunk:
                raise ConnectionClosed(None, "the connection ended")
            self._buffer += chunk
        data = bytes(self._buffer[:count])
        del self._buffer[:count]
        return data

    def read_frame(self):
        """(fin, opcode, payload), unmasked."""
        first, second = self._read(2)
        if first & 0x70:
            raise WebSocketError("a frame uses an extension that was not negotiated")
        fin, opcode = bool(first & 0x80), first & 0x0F
        masked, length = bool(second & 0x80), second & 0x7F
        if length == 126:
            length = int.from_bytes(self._read(2), "big")
        elif length == 127:
            length = int.from_bytes(self._read(8), "big")
        if opcode >= 0x8 and (not fin or length > 125):
            raise WebSocketError("a control frame that is fragmented or too long")
        if length > MAX_MESSAGE_BYTES:
            raise WebSocketError("a frame that is too large")
        key = self._read(4) if masked else None
        payload = self._read(length)
        return fin, opcode, apply_mask(payload, key) if key else payload


def _close_payload(code, reason=""):
    return int(code).to_bytes(2, "big") + str(reason).encode("utf-8")[:123]


def _parse_close(payload):
    if len(payload) >= 2:
        return int.from_bytes(payload[:2], "big"), payload[2:].decode("utf-8", "replace")
    return None, ""


class WebSocket:
    def __init__(self, sock, initial=b""):
        self.sock = sock
        self._reader = FrameReader(sock.recv, initial)
        self._close_sent = False
        self.closed = False

    def _send(self, opcode, payload):
        self.sock.sendall(encode_frame(opcode, payload))

    def send_text(self, text):
        self._send(OP_TEXT, str(text).encode("utf-8"))

    def send_binary(self, data):
        self._send(OP_BINARY, data)

    def recv(self):
        """The next complete message as (OP_TEXT, str) or (OP_BINARY, bytes).
        Answers pings; raises ConnectionClosed when the server closes."""
        if self.closed:
            raise ConnectionClosed(None, "already closed")
        message_opcode, fragments, size = None, None, 0
        while True:
            fin, opcode, payload = self._reader.read_frame()
            if opcode == OP_PING:
                self._send(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                code, reason = _parse_close(payload)
                if not self._close_sent:
                    try:
                        self._close_sent = True
                        self._send(OP_CLOSE, _close_payload(code or 1000))
                    except OSError:
                        pass
                self.closed = True
                raise ConnectionClosed(code, reason)
            if opcode in (OP_TEXT, OP_BINARY):
                if fragments is not None:
                    raise WebSocketError("a new message started inside a fragmented one")
                message_opcode, fragments, size = opcode, [payload], len(payload)
            elif opcode == OP_CONTINUATION:
                if fragments is None:
                    raise WebSocketError("a continuation frame without a message")
                fragments.append(payload)
                size += len(payload)
            else:
                raise WebSocketError(f"unknown opcode {opcode}")
            if size > MAX_MESSAGE_BYTES:
                raise WebSocketError("a message that is too large")
            if fin:
                data = b"".join(fragments)
                if message_opcode == OP_TEXT:
                    try:
                        return OP_TEXT, data.decode("utf-8")
                    except UnicodeDecodeError:
                        raise WebSocketError("a text message that isn't UTF-8") from None
                return OP_BINARY, data

    def close(self, code=1000, reason=""):
        """Say goodbye (once) and close the socket."""
        if not self._close_sent and not self.closed:
            self._close_sent = True
            try:
                self._send(OP_CLOSE, _close_payload(code, reason))
            except OSError:
                pass
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass

    def abort(self):
        """Stop a recv() blocked on another thread (it then raises)."""
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except (OSError, ValueError):
            pass


# ------------------------------------------------------------
# The opening handshake
# ------------------------------------------------------------

def new_key():
    return base64.b64encode(os.urandom(16)).decode("ascii")


def accept_value(key):
    digest = hashlib.sha1((key + ACCEPT_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def handshake_request(host, path, headers, key):
    lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket",
             "Connection: Upgrade", f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
    own = {"host", "upgrade", "connection", "sec-websocket-key", "sec-websocket-version"}
    for name, value in headers.items():
        if name.lower() not in own:
            lines.append(f"{name}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def read_http_response(recv):
    """(status, reason, headers with lower-case names, bytes after the headers)."""
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        if len(buffer) > MAX_HANDSHAKE_BYTES:
            raise WebSocketError("the handshake answer is too long")
        chunk = recv(4096)
        if not chunk:
            raise ConnectionClosed(None, "the connection ended during the handshake")
        buffer += chunk
    head, _sep, rest = bytes(buffer).partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    parts = lines[0].split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/"):
        raise WebSocketError(f"not an HTTP answer: {lines[0][:80]!r}")
    try:
        status = int(parts[1])
    except ValueError:
        raise WebSocketError(f"not an HTTP answer: {lines[0][:80]!r}") from None
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    return status, parts[2] if len(parts) > 2 else "", headers, rest


def check_handshake(status, reason, headers, key):
    if status != 101:
        raise HandshakeError(status, reason, headers)
    if headers.get("upgrade", "").lower() != "websocket" or \
            "upgrade" not in headers.get("connection", "").lower():
        raise WebSocketError("the server did not switch to WebSocket")
    if headers.get("sec-websocket-accept") != accept_value(key):
        raise WebSocketError("the server's Sec-WebSocket-Accept is wrong")
    if headers.get("sec-websocket-extensions"):
        raise WebSocketError("the server chose an extension that was not requested")


def connect(host, path, headers, timeout=10.0, port=443, context=None):
    """Open wss://host:port/path. Every read and write times out after
    `timeout` seconds. HandshakeError carries the status and headers."""
    raw = socket.create_connection((host, port), timeout=timeout)
    sock = raw
    try:
        sock = (context or ssl.create_default_context()).wrap_socket(raw, server_hostname=host)
        sock.settimeout(timeout)
        key = new_key()
        sock.sendall(handshake_request(host, path, headers, key))
        status, reason, answer, rest = read_http_response(sock.recv)
        check_handshake(status, reason, answer, key)
        return WebSocket(sock, rest)
    except BaseException:
        try:
            sock.close()
        except OSError:
            pass
        raise
