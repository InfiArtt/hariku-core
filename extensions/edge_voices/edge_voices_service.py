# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Talking to the Edge speech service: synthesizing text to MP3 over a WebSocket
and fetching the voice list over HTTPS. Blocking; main.py calls these on its
worker thread. After a 403 the request is tried once more with the clock
corrected from the service's Date header (the Sec-MS-GEC token depends on it).
"""
import json
import time
import urllib.error
import urllib.request
import zlib

import edge_voices_protocol as protocol
import edge_voices_ws as ws

TIMEOUT_SECONDS = 10.0
MAX_VOICE_LIST_BYTES = 8 * 1024 * 1024


class Cancelled(Exception):
    """The synthesis was stopped."""


def synthesize(text, voice, rate="+0%", volume="+0%", cancelled=lambda: False,
               on_connection=None, timeout=TIMEOUT_SECONDS, connect=None):
    """MP3 bytes of `text` spoken by `voice` (a short name such as
    "id-ID-GadisNeural"). Long text is sent in several requests.
    `cancelled()` is checked between messages; `on_connection(websocket)` gets
    each connection so another thread can abort it. Raises Cancelled, or what
    went wrong."""
    connect = connect or ws.connect
    pieces = protocol.split_text(text)
    if not pieces:
        raise ValueError("nothing to say")
    audio = bytearray()
    for piece in pieces:
        ssml = protocol.build_ssml(piece, voice, rate, volume)
        audio += _synthesize_piece(ssml, cancelled, on_connection, timeout, connect)
    return bytes(audio)


def _open(connect, timeout):
    try:
        return connect(protocol.HOST, protocol.websocket_path(), protocol.websocket_headers(),
                       timeout)
    except ws.HandshakeError as e:
        if e.status == 403 and protocol.adjust_clock_skew(e.headers.get("date")):
            return connect(protocol.HOST, protocol.websocket_path(),
                           protocol.websocket_headers(), timeout)
        raise


def _synthesize_piece(ssml, cancelled, on_connection, timeout, connect):
    if cancelled():
        raise Cancelled()
    connection = _open(connect, timeout)
    if on_connection is not None:
        on_connection(connection)
    try:
        connection.send_text(protocol.speech_config_message())
        connection.send_text(protocol.ssml_message(ssml))
        audio = bytearray()
        deadline = time.monotonic() + 60.0 + timeout
        while True:
            if cancelled():
                raise Cancelled()
            if time.monotonic() > deadline:
                raise TimeoutError("the speech service took too long")
            try:
                opcode, data = connection.recv()
            except (OSError, ws.WebSocketError):
                if cancelled():
                    raise Cancelled() from None
                raise
            if opcode == ws.OP_TEXT:
                headers, _body = protocol.parse_text_message(data)
                if headers.get("Path") == "turn.end":
                    break
            else:
                audio += protocol.audio_from_binary(data)
        if not audio:
            raise protocol.ProtocolError("the speech service sent no audio")
        return bytes(audio)
    finally:
        connection.close()


def _decode(body, encoding):
    encoding = (encoding or "").lower().strip()
    if encoding == "gzip":
        return zlib.decompress(body, 16 + zlib.MAX_WBITS)
    if encoding == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    if encoding in ("", "identity"):
        return body
    raise protocol.ProtocolError(f"the voice list came {encoding}-encoded")


def fetch_voice_list(timeout=TIMEOUT_SECONDS):
    """The service's voices, parsed (see protocol.parse_voice_list)."""
    for attempt in (1, 2):
        request = urllib.request.Request(protocol.voice_list_url(),
                                         headers=protocol.voice_list_headers())
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(MAX_VOICE_LIST_BYTES + 1)
                encoding = response.headers.get("Content-Encoding")
        except urllib.error.HTTPError as e:
            if e.code == 403 and attempt == 1 and \
                    protocol.adjust_clock_skew(e.headers.get("Date") if e.headers else None):
                continue
            raise
        if len(body) > MAX_VOICE_LIST_BYTES:
            raise protocol.ProtocolError("the voice list is too large")
        return protocol.parse_voice_list(json.loads(_decode(body, encoding).decode("utf-8")))
    raise protocol.ProtocolError("the voice list could not be fetched")
