# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Edge Voices extension: the WebSocket client (in memory), the
# Sec-MS-GEC token against the reference algorithm, SSML, the service's audio
# framing, the voice list, the audio cache, the failure back-off and the
# provider. No test touches the network (a guard fails any attempt) and nothing
# is played.

import gzip
import hashlib
import importlib.util
import io
import json
import os
import random
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGE_DIR = os.path.join(ROOT, "extensions", "edge_voices")
if EDGE_DIR not in sys.path:
    sys.path.insert(0, EDGE_DIR)

import edge_voices_cache as cache_mod      # noqa: E402
import edge_voices_protocol as protocol    # noqa: E402
import edge_voices_service as service      # noqa: E402
import edge_voices_ws as ws                # noqa: E402


def wait_until(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(args[0] if args else kwargs)
        raise OSError("network is disabled in the tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    protocol.reset_clock_skew()
    yield attempts
    protocol.reset_clock_skew()


# ------------------------------------------------------------
# WebSocket framing, with an in-memory socket
# ------------------------------------------------------------

class MemorySocket:
    """recv() hands out at most `chunk` bytes at a time, like a slow network."""

    def __init__(self, incoming=b"", chunk=7):
        self.incoming = bytearray(incoming)
        self.sent = bytearray()
        self.chunk = chunk
        self.closed = False

    def recv(self, n):
        n = min(n, self.chunk, len(self.incoming))
        data = bytes(self.incoming[:n])
        del self.incoming[:n]
        return data

    def sendall(self, data):
        self.sent += data

    def close(self):
        self.closed = True

    def shutdown(self, how):
        self.closed = True

    def settimeout(self, seconds):
        self.timeout = seconds


def server(opcode, payload, fin=True):
    return ws.encode_frame(opcode, payload, fin=fin, mask=False)


class TestFraming:
    @pytest.mark.parametrize("size, header_length", [(0, 2), (125, 2), (126, 4), (65535, 4),
                                                     (65536, 10)])
    def test_lengths(self, size, header_length):
        frame = ws.encode_frame(ws.OP_BINARY, b"x" * size, mask=False)
        assert len(frame) == header_length + size
        fin, opcode, payload = ws.FrameReader(MemorySocket(frame, chunk=999).recv).read_frame()
        assert (fin, opcode, payload) == (True, ws.OP_BINARY, b"x" * size)

    def test_client_frames_are_masked(self):
        frame = ws.encode_frame(ws.OP_TEXT, b"Hariku", mask_key=b"\x01\x02\x03\x04")
        assert frame[0] == 0x81 and frame[1] == 0x80 | 6
        assert frame[2:6] == b"\x01\x02\x03\x04"
        assert frame[6:] == bytes(b ^ k for b, k in zip(b"Hariku", b"\x01\x02\x03\x04" * 2))
        assert frame[6:] != b"Hariku"
        fin, opcode, payload = ws.FrameReader(MemorySocket(frame).recv).read_frame()
        assert payload == b"Hariku"

    def test_random_mask_keys(self):
        keys = {ws.encode_frame(ws.OP_TEXT, b"abc")[2:6] for _ in range(20)}
        assert len(keys) > 1
        with pytest.raises(ValueError):
            ws.encode_frame(ws.OP_TEXT, b"abc", mask_key=b"\x00")

    def test_mask_round_trip(self):
        data = os.urandom(1000)
        key = os.urandom(4)
        assert ws.apply_mask(ws.apply_mask(data, key), key) == data
        assert ws.apply_mask(b"", key) == b""

    def test_messages_and_fragments(self):
        incoming = (server(ws.OP_TEXT, "Path:turn.start\r\n\r\n{}".encode())
                    + server(ws.OP_BINARY, b"part1-", fin=False)
                    + server(ws.OP_PING, b"are you there")        # between fragments
                    + server(ws.OP_CONTINUATION, b"part2-", fin=False)
                    + server(ws.OP_CONTINUATION, b"part3", fin=True)
                    + server(ws.OP_PONG, b"")
                    + server(ws.OP_TEXT, "é".encode("utf-8")))
        sock = MemorySocket(incoming)
        conn = ws.WebSocket(sock)
        assert conn.recv() == (ws.OP_TEXT, "Path:turn.start\r\n\r\n{}")
        assert conn.recv() == (ws.OP_BINARY, b"part1-part2-part3")
        assert conn.recv() == (ws.OP_TEXT, "é")
        # The ping was answered with a masked pong carrying the same data.
        fin, opcode, payload = ws.FrameReader(MemorySocket(bytes(sock.sent)).recv).read_frame()
        assert (fin, opcode, payload) == (True, ws.OP_PONG, b"are you there")
        assert sock.sent[1] & 0x80

    def test_close_from_the_server(self):
        sock = MemorySocket(server(ws.OP_CLOSE, (1000).to_bytes(2, "big") + b"bye"))
        conn = ws.WebSocket(sock)
        with pytest.raises(ws.ConnectionClosed) as closed:
            conn.recv()
        assert (closed.value.code, closed.value.reason) == (1000, "bye")
        fin, opcode, payload = ws.FrameReader(MemorySocket(bytes(sock.sent)).recv).read_frame()
        assert opcode == ws.OP_CLOSE and payload[:2] == (1000).to_bytes(2, "big")
        with pytest.raises(ws.ConnectionClosed):
            conn.recv()
        conn.close()
        assert len(sock.sent) == len(ws.encode_frame(ws.OP_CLOSE, payload, mask_key=b"1234"))

    def test_close_from_the_client_is_sent_once(self):
        sock = MemorySocket()
        conn = ws.WebSocket(sock)
        conn.close()
        conn.close()
        fin, opcode, payload = ws.FrameReader(MemorySocket(bytes(sock.sent)).recv).read_frame()
        assert opcode == ws.OP_CLOSE and payload == (1000).to_bytes(2, "big")
        assert len(sock.sent) == 2 + 4 + 2 and sock.closed

    def test_the_connection_ending(self):
        conn = ws.WebSocket(MemorySocket(server(ws.OP_TEXT, b"abc")[:3]))
        with pytest.raises(ws.ConnectionClosed):
            conn.recv()

    @pytest.mark.parametrize("frame, problem", [
        (bytes([0xC1, 0x00]), "extension"),                                  # RSV1
        (bytes([0x09, 0x00]), "control"),                                    # fragmented ping
        (bytes([0x89, 126]) + (200).to_bytes(2, "big") + b"x" * 200, "control"),
        (bytes([0x80, 0x01, 0x41]), "continuation"),                         # no message
        (bytes([0x83, 0x00]), "opcode"),
        (bytes([0x81, 0x02]) + b"\xff\xfe", "UTF-8"),
        (bytes([0x01, 0x01, 0x41, 0x81, 0x01, 0x42]), "inside"),             # text in text
    ])
    def test_protocol_errors(self, frame, problem):
        with pytest.raises(ws.WebSocketError) as error:
            ws.WebSocket(MemorySocket(frame)).recv()
        assert problem in str(error.value)

    def test_send(self):
        sock = MemorySocket()
        conn = ws.WebSocket(sock)
        conn.send_text("Path:ssml\r\n\r\n<speak/>")
        conn.send_binary(b"\x00\x01")
        reader = ws.FrameReader(MemorySocket(bytes(sock.sent)).recv)
        assert reader.read_frame() == (True, ws.OP_TEXT, b"Path:ssml\r\n\r\n<speak/>")
        assert reader.read_frame() == (True, ws.OP_BINARY, b"\x00\x01")

    def test_abort_unblocks(self):
        sock = MemorySocket()
        conn = ws.WebSocket(sock)
        conn.abort()
        assert sock.closed and conn.closed


class HandshakeSocket(MemorySocket):
    """Answers the upgrade request like a server, then sends `after`."""

    def __init__(self, after=b"", status="101 Switching Protocols", accept=None, extra=""):
        super().__init__()
        self.after, self.status, self.accept, self.extra = after, status, accept, extra
        self.request = None

    def sendall(self, data):
        if self.request is None:
            self.request = bytes(data).decode("ascii")
            key = [line.split(": ", 1)[1] for line in self.request.split("\r\n")
                   if line.startswith("Sec-WebSocket-Key: ")][0]
            answer = (f"HTTP/1.1 {self.status}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {self.accept or ws.accept_value(key)}\r\n"
                      f"Date: Thu, 24 Sep 2026 10:00:00 GMT\r\n{self.extra}\r\n")
            self.incoming += answer.encode("ascii") + self.after
        else:
            super().sendall(data)


class FakeContext:
    def __init__(self, sock):
        self.sock = sock
        self.server_hostname = None

    def wrap_socket(self, raw, server_hostname=None):
        self.server_hostname = server_hostname
        return self.sock


class TestHandshake:
    def test_accept_value_matches_rfc_6455(self):
        assert ws.accept_value("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="

    def test_request(self):
        request = ws.handshake_request("speech.platform.bing.com", "/path?x=1",
                                       {"Origin": "chrome-extension://abc", "Upgrade": "no"},
                                       "KEY").decode("ascii")
        lines = request.split("\r\n")
        assert lines[0] == "GET /path?x=1 HTTP/1.1"
        assert "Host: speech.platform.bing.com" in lines and "Upgrade: websocket" in lines
        assert "Connection: Upgrade" in lines and "Sec-WebSocket-Version: 13" in lines
        assert "Sec-WebSocket-Key: KEY" in lines and "Origin: chrome-extension://abc" in lines
        assert "Upgrade: no" not in lines and request.endswith("\r\n\r\n")

    def test_connect_keeps_bytes_after_the_answer(self, monkeypatch):
        sock = HandshakeSocket(after=server(ws.OP_TEXT, b"Path:turn.start\r\n\r\n"))
        monkeypatch.setattr(socket, "create_connection", lambda address, timeout=None: object())
        context = FakeContext(sock)
        conn = ws.connect("speech.platform.bing.com", "/p", {"Origin": "o"}, timeout=5,
                          context=context)
        assert context.server_hostname == "speech.platform.bing.com"
        assert conn.recv() == (ws.OP_TEXT, "Path:turn.start\r\n\r\n")

    @pytest.mark.parametrize("kwargs, error, text", [
        ({"status": "403 Forbidden"}, ws.HandshakeError, "403"),
        ({"accept": "wrong"}, ws.WebSocketError, "Accept"),
        ({"extra": "Sec-WebSocket-Extensions: permessage-deflate\r\n"}, ws.WebSocketError,
         "extension"),
    ])
    def test_bad_answers(self, monkeypatch, kwargs, error, text):
        sock = HandshakeSocket(**kwargs)
        monkeypatch.setattr(socket, "create_connection", lambda address, timeout=None: object())
        with pytest.raises(error) as raised:
            ws.connect("h", "/p", {}, context=FakeContext(sock))
        assert text in str(raised.value)
        assert sock.closed
        if isinstance(raised.value, ws.HandshakeError):
            assert raised.value.status == 403
            assert raised.value.headers["date"] == "Thu, 24 Sep 2026 10:00:00 GMT"

    def test_not_http(self):
        with pytest.raises(ws.WebSocketError):
            ws.read_http_response(MemorySocket(b"SSH-2.0-x\r\n\r\n").recv)


# ------------------------------------------------------------
# Sec-MS-GEC
# ------------------------------------------------------------

def reference_sec_ms_gec(unix_time):
    """The algorithm as edge-tts writes it (floating point)."""
    ticks = unix_time
    ticks += 11644473600
    ticks -= ticks % 300
    ticks *= 1e9 / 100
    return hashlib.sha256(f"{ticks:.0f}{protocol.TRUSTED_CLIENT_TOKEN}".encode("ascii")) \
        .hexdigest().upper()


class TestSecMsGec:
    def test_matches_the_reference(self):
        times = [0.0, 1758700000.123, 1790000000.0, 1790000299.999, 1790000300.0,
                 2000000000.5, 4102444800.0]
        rng = random.Random(7)
        times += [rng.uniform(1.6e9, 2.2e9) for _ in range(200)]
        for t in times:
            assert protocol.sec_ms_gec(t) == reference_sec_ms_gec(t), t

    def test_changes_every_five_minutes(self):
        base = 1790000100.0 - (1790000100 + 11644473600) % 300
        assert protocol.sec_ms_gec(base) == protocol.sec_ms_gec(base + 299.9)
        assert protocol.sec_ms_gec(base) != protocol.sec_ms_gec(base + 300)
        token = protocol.sec_ms_gec(base)
        assert len(token) == 64 and token == token.upper()

    def test_clock_skew_from_the_server(self, monkeypatch):
        monkeypatch.setattr(protocol.time, "time", lambda: 1790000000.0)
        assert protocol.sec_ms_gec() == reference_sec_ms_gec(1790000000.0)
        # The server's clock is 20 minutes ahead of ours.
        assert protocol.adjust_clock_skew("Mon, 21 Sep 2026 14:33:20 GMT")
        assert protocol.current_time() == 1790000000.0 + 1200
        assert protocol.sec_ms_gec() == reference_sec_ms_gec(1790001200.0)
        assert not protocol.adjust_clock_skew("not a date")
        assert not protocol.adjust_clock_skew(None)
        assert protocol.current_time() == 1790000000.0 + 1200

    def test_http_dates_ignore_the_locale(self):
        assert protocol.parse_http_date("Thu, 01 Jan 1970 00:00:00 GMT") == 0.0
        assert protocol.parse_http_date("Thu, 24 Sep 2026 10:00:00 GMT") == 1790244000.0
        assert protocol.parse_http_date("Rabu, 24 Sep 2026 10:00:00 WIB") is None
        assert protocol.parse_http_date("") is None


# ------------------------------------------------------------
# Messages and SSML
# ------------------------------------------------------------

class TestMessages:
    def test_urls_and_headers(self, monkeypatch):
        path = protocol.websocket_path("abc123")
        assert path.startswith("/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken="
                               "6A5AA1D4EAFF4E9FB37E23D68491D6F4&ConnectionId=abc123&Sec-MS-GEC=")
        assert path.endswith(f"&Sec-MS-GEC-Version=1-{protocol.CHROMIUM_FULL_VERSION}")
        assert protocol.voice_list_url().startswith(
            "https://speech.platform.bing.com/consumer/speech/synthesize/readaloud/voices/list?"
            "trustedclienttoken=6A5AA1D4EAFF4E9FB37E23D68491D6F4&Sec-MS-GEC=")
        headers = protocol.websocket_headers()
        assert headers["Origin"] == "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold"
        assert "Edg/" in headers["User-Agent"] and headers["Pragma"] == "no-cache"
        assert headers["Cookie"].startswith("muid=") and len(headers["Cookie"]) == 5 + 32 + 1
        voice_headers = protocol.voice_list_headers()
        assert voice_headers["Accept-Encoding"] == "gzip, deflate"
        assert "Microsoft Edge" in voice_headers["Sec-CH-UA"]

    def test_timestamps_are_english(self, monkeypatch):
        import locale
        assert protocol.timestamp(1790244000) == \
            "Thu Sep 24 2026 10:00:00 GMT+0000 (Coordinated Universal Time)"
        config = protocol.speech_config_message(1790244000)
        head, body = config.split("\r\n\r\n", 1)
        assert head.split("\r\n") == [
            "X-Timestamp:Thu Sep 24 2026 10:00:00 GMT+0000 (Coordinated Universal Time)",
            "Content-Type:application/json; charset=utf-8", "Path:speech.config"]
        assert json.loads(body)["context"]["synthesis"]["audio"]["outputFormat"] == \
            "audio-24khz-48kbitrate-mono-mp3"
        assert body.endswith("\r\n")

    def test_ssml_message(self):
        message = protocol.ssml_message("<speak/>", request_id="r1", unix_time=1790244000)
        assert message == ("X-RequestId:r1\r\nContent-Type:application/ssml+xml\r\n"
                           "X-Timestamp:Thu Sep 24 2026 10:00:00 GMT+0000 (Coordinated "
                           "Universal Time)Z\r\nPath:ssml\r\n\r\n<speak/>")

    @pytest.mark.parametrize("short, long", [
        ("id-ID-GadisNeural", "Microsoft Server Speech Text to Speech Voice (id-ID, GadisNeural)"),
        ("en-US-EmmaMultilingualNeural",
         "Microsoft Server Speech Text to Speech Voice (en-US, EmmaMultilingualNeural)"),
        ("zh-CN-liaoning-XiaobeiNeural",
         "Microsoft Server Speech Text to Speech Voice (zh-CN-liaoning, XiaobeiNeural)"),
    ])
    def test_voice_names(self, short, long):
        assert protocol.long_voice_name(short) == long

    @pytest.mark.parametrize("bad", ["", "Gadis", "id-ID-Gadis", "id-ID-X'/><evil a='Neural",
                                     "id-ID-Gadis Neural", None])
    def test_bad_voice_names(self, bad):
        with pytest.raises(ValueError):
            protocol.long_voice_name(bad)

    def test_escaping(self):
        text = "Rapat <penting> & \"makan\" 'siang'\x00\x07 at 10:00\n"
        ssml = protocol.build_ssml(text, "id-ID-ArdiNeural", "+20%", "-10%")
        root = ET.fromstring(ssml)             # well-formed XML
        prosody = root[0][0]
        assert prosody.attrib == {"pitch": "+0Hz", "rate": "+20%", "volume": "-10%"}
        assert prosody.text == "Rapat <penting> & \"makan\" 'siang'   at 10:00\n"
        assert "&lt;penting&gt; &amp;" in ssml
        assert root[0].attrib["name"] == \
            "Microsoft Server Speech Text to Speech Voice (id-ID, ArdiNeural)"
        with pytest.raises(ValueError):
            protocol.build_ssml("x", "id-ID-ArdiNeural", "fast")
        with pytest.raises(ValueError):
            protocol.build_ssml("x", "id-ID-ArdiNeural", "+0%", "'/><x a='")

    @pytest.mark.parametrize("rate, value", [(0, "+0%"), (1, "+10%"), (10, "+100%"),
                                             (-1, "-5%"), (-10, "-50%"), (99, "+100%"),
                                             ("x", "+0%")])
    def test_rate(self, rate, value):
        assert protocol.rate_percent(rate) == value

    @pytest.mark.parametrize("volume, value", [(100, "+0%"), (50, "-50%"), (0, "-100%"),
                                               (150, "+0%"), (None, "+0%")])
    def test_volume(self, volume, value):
        assert protocol.volume_percent(volume) == value

    def test_long_text_is_split_between_words(self):
        words = [f"kata{i}&" for i in range(2000)]
        text = " ".join(words)
        pieces = protocol.split_text(text, limit=500)
        assert len(pieces) > 1
        assert " ".join(pieces).split() == words
        assert all(len(protocol.escape_text(p).encode("utf-8")) <= 500 for p in pieces)
        long_word = "é" * 700
        pieces = protocol.split_text(f"a {long_word} b", limit=100)
        assert "".join(pieces[1:-1]) == long_word and pieces[0] == "a" and pieces[-1] == "b"
        assert all(len(protocol.escape_text(p).encode("utf-8")) <= 100 for p in pieces)
        assert protocol.split_text("   ") == []


# ------------------------------------------------------------
# What the service sends back
# ------------------------------------------------------------

def audio_message(payload, path="audio", content_type="audio/mpeg"):
    head = f"X-RequestId:abc\r\nX-StreamId:1\r\nPath:{path}"
    if content_type:
        head += f"\r\nContent-Type:{content_type}"
    head = head.encode("ascii")
    return len(head).to_bytes(2, "big") + head + payload


MP3 = bytes.fromhex("fff364c4") + b"\x00" * 60


class TestServiceMessages:
    def test_text_messages(self):
        headers, body = protocol.parse_text_message(
            "X-RequestId:abc\r\nContent-Type:application/json; charset=utf-8\r\n"
            "Path:turn.end\r\n\r\n{}")
        assert headers["Path"] == "turn.end" and body == "{}"
        assert headers["Content-Type"] == "application/json; charset=utf-8"

    def test_audio(self):
        assert protocol.audio_from_binary(audio_message(MP3)) == MP3
        assert protocol.audio_from_binary(audio_message(b"", content_type=None)) == b""

    @pytest.mark.parametrize("data", [
        b"\x00", audio_message(MP3, path="audio.metadata"), audio_message(MP3, content_type=None),
        audio_message(MP3, content_type="audio/wav"), audio_message(b""),
        (500).to_bytes(2, "big") + b"Path:audio",
    ])
    def test_unexpected_binary(self, data):
        with pytest.raises(protocol.ProtocolError):
            protocol.audio_from_binary(data)


class FakeConnection:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []
        self.closed = False
        self.aborted = False

    def send_text(self, text):
        self.sent.append(text)

    def recv(self):
        if not self.messages:
            raise ws.ConnectionClosed(1000, "")
        item = self.messages.pop(0)
        if callable(item):
            return item()
        return item

    def close(self):
        self.closed = True

    def abort(self):
        self.aborted = True


def session():
    return [(ws.OP_TEXT, "X-RequestId:a\r\nPath:turn.start\r\n\r\n{}"),
            (ws.OP_TEXT, "X-RequestId:a\r\nPath:response\r\n\r\n{}"),
            (ws.OP_BINARY, audio_message(MP3[:30])),
            (ws.OP_TEXT, "X-RequestId:a\r\nPath:audio.metadata\r\n\r\n{\"Metadata\":[]}"),
            (ws.OP_BINARY, audio_message(MP3[30:])),
            (ws.OP_BINARY, audio_message(b"", content_type=None)),
            (ws.OP_TEXT, "X-RequestId:a\r\nPath:turn.end\r\n\r\n{}")]


class TestSynthesize:
    def test_a_whole_session(self):
        connections = []

        def connect(host, path, headers, timeout):
            assert host == "speech.platform.bing.com" and "Sec-MS-GEC=" in path
            assert headers["Origin"].startswith("chrome-extension://")
            connections.append(FakeConnection(session()))
            return connections[-1]

        seen = []
        audio = service.synthesize("Rapat <penting> & makan", "id-ID-GadisNeural", "+10%",
                                   connect=connect, on_connection=seen.append)
        assert audio == MP3
        conn = connections[0]
        assert seen == [conn] and conn.closed
        assert "Path:speech.config" in conn.sent[0]
        assert "Path:ssml" in conn.sent[1]
        assert "(id-ID, GadisNeural)" in conn.sent[1] and "rate='+10%'" in conn.sent[1]
        assert "Rapat &lt;penting&gt; &amp; makan" in conn.sent[1]

    def test_over_a_real_websocket_in_memory(self):
        # The same session as frames: fragmented audio and a ping included.
        frames = b""
        for opcode, data in session():
            data = data.encode("utf-8") if isinstance(data, str) else data
            if opcode == ws.OP_BINARY and len(data) > 20:
                frames += server(ws.OP_BINARY, data[:20], fin=False)
                frames += server(ws.OP_PING, b"p")
                frames += server(ws.OP_CONTINUATION, data[20:])
            else:
                frames += server(opcode, data)
        sock = MemorySocket(frames, chunk=13)
        audio = service.synthesize("Halo", "id-ID-ArdiNeural",
                                   connect=lambda *a: ws.WebSocket(sock))
        assert audio == MP3
        reader = ws.FrameReader(MemorySocket(bytes(sock.sent)).recv)
        opcodes = []
        while True:
            try:
                fin, opcode, payload = reader.read_frame()
            except ws.ConnectionClosed:
                break
            opcodes.append(opcode)
        assert opcodes == [ws.OP_TEXT, ws.OP_TEXT] + [ws.OP_PONG] * 3 + [ws.OP_CLOSE]
        assert sock.closed

    def test_403_corrects_the_clock_once(self):
        calls = []

        def connect(host, path, headers, timeout):
            calls.append(path)
            if len(calls) == 1:
                raise ws.HandshakeError(403, "Forbidden",
                                        {"date": "Thu, 24 Sep 2026 10:00:00 GMT"})
            return FakeConnection(session())

        assert service.synthesize("Halo", "id-ID-ArdiNeural", connect=connect) == MP3
        assert len(calls) == 2 and protocol._clock_skew != 0

    def test_403_without_a_date_fails(self):
        def connect(host, path, headers, timeout):
            raise ws.HandshakeError(403, "Forbidden", {})

        with pytest.raises(ws.HandshakeError):
            service.synthesize("Halo", "id-ID-ArdiNeural", connect=connect)

    def test_long_text_uses_several_requests(self):
        connections = []

        def connect(*args):
            connections.append(FakeConnection(session()))
            return connections[-1]

        text = " ".join(["kata"] * 3000)     # well over 4096 bytes
        assert service.synthesize(text, "id-ID-ArdiNeural", connect=connect) == \
            MP3 * len(connections)
        assert len(connections) >= 4

    def test_no_audio_is_an_error(self):
        connect = lambda *a: FakeConnection([(ws.OP_TEXT, "Path:turn.end\r\n\r\n")])  # noqa
        with pytest.raises(protocol.ProtocolError):
            service.synthesize("Halo", "id-ID-ArdiNeural", connect=connect)

    def test_cancelled(self):
        flag = {"stop": False}
        conn = FakeConnection([lambda: flag.update(stop=True) or
                               (ws.OP_BINARY, audio_message(MP3))] + session())
        with pytest.raises(service.Cancelled):
            service.synthesize("Halo", "id-ID-ArdiNeural", cancelled=lambda: flag["stop"],
                               connect=lambda *a: conn)
        assert conn.closed

    def test_an_aborted_connection_counts_as_cancelled(self):
        flag = {"stop": False}

        def broken():
            flag["stop"] = True
            raise OSError("socket shut down")

        conn = FakeConnection([broken])
        with pytest.raises(service.Cancelled):
            service.synthesize("Halo", "id-ID-ArdiNeural", cancelled=lambda: flag["stop"],
                               connect=lambda *a: conn)


# ------------------------------------------------------------
# The voice list
# ------------------------------------------------------------

VOICE_LIST = [
    {"Name": "Microsoft Server Speech Text to Speech Voice (id-ID, ArdiNeural)",
     "ShortName": "id-ID-ArdiNeural", "Gender": "Male", "Locale": "id-ID",
     "SuggestedCodec": "audio-24khz-48kbitrate-mono-mp3",
     "FriendlyName": "Microsoft Ardi Online (Natural) - Indonesian (Indonesia)",
     "Status": "GA", "VoiceTag": {"ContentCategories": ["General"]}},
    {"ShortName": "id-ID-GadisNeural", "Gender": "Female", "Locale": "id-ID", "Status": "GA"},
    {"ShortName": "en-US-EmmaMultilingualNeural", "Gender": "Female", "Locale": "en-US"},
    {"ShortName": "zh-CN-liaoning-XiaobeiNeural", "Gender": "Female",
     "Locale": "zh-CN-liaoning"},
    {"ShortName": "id-ID-GadisNeural", "Gender": "Female", "Locale": "id-ID"},   # duplicate
    {"ShortName": "en-US-OldNeural", "Gender": "Male", "Locale": "en-US",
     "Status": "Deprecated"},
    {"ShortName": "not a voice", "Locale": "xx"}, {"Locale": "id-ID"}, "junk",
]


class TestVoiceList:
    def test_parsing(self):
        voices = protocol.parse_voice_list(VOICE_LIST)
        assert voices == [
            {"id": "id-ID-ArdiNeural", "name": "Ardi", "language": "id-ID", "gender": "male"},
            {"id": "id-ID-GadisNeural", "name": "Gadis", "language": "id-ID", "gender": "female"},
            {"id": "en-US-EmmaMultilingualNeural", "name": "Emma Multilingual",
             "language": "en-US", "gender": "female"},
            {"id": "zh-CN-liaoning-XiaobeiNeural", "name": "Xiaobei",
             "language": "zh-CN-liaoning", "gender": "female"},
        ]
        with pytest.raises(protocol.ProtocolError):
            protocol.parse_voice_list({"voices": []})

    def _response(self, body, encoding=None):
        class Response(io.BytesIO):
            headers = {"Content-Encoding": encoding} if encoding else {}

        return Response(body)

    def test_fetch(self, monkeypatch):
        requests = []

        def urlopen(request, timeout=None):
            requests.append((request, timeout))
            return self._response(gzip.compress(json.dumps(VOICE_LIST).encode("utf-8")), "gzip")

        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        voices = service.fetch_voice_list()
        assert [v["id"] for v in voices][:2] == ["id-ID-ArdiNeural", "id-ID-GadisNeural"]
        request, timeout = requests[0]
        assert timeout == service.TIMEOUT_SECONDS
        assert request.full_url.startswith(protocol.voice_list_url()[:100])
        assert "Edg/" in request.get_header("User-agent")
        assert request.get_header("Cookie").startswith("muid=")
        assert request.get_header("Sec-ch-ua-mobile") == "?0"

    def test_fetch_deflate_and_plain(self, monkeypatch):
        import zlib
        bodies = [(zlib.compress(json.dumps(VOICE_LIST).encode()), "deflate"),
                  (json.dumps(VOICE_LIST).encode(), None)]
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda request, timeout=None: self._response(*bodies.pop(0)))
        assert len(service.fetch_voice_list()) == 4
        assert len(service.fetch_voice_list()) == 4

    def test_fetch_403_corrects_the_clock(self, monkeypatch):
        calls = []

        def urlopen(request, timeout=None):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 403, "Forbidden",
                                             {"Date": "Thu, 24 Sep 2026 10:00:00 GMT"}, None)
            return self._response(json.dumps(VOICE_LIST).encode())

        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        assert len(service.fetch_voice_list()) == 4 and len(calls) == 2

    def test_other_http_errors(self, monkeypatch):
        def urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 500, "Oops", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        with pytest.raises(urllib.error.HTTPError):
            service.fetch_voice_list()


# ------------------------------------------------------------
# The cache
# ------------------------------------------------------------

class TestCache:
    def test_keys(self):
        key = cache_mod.AudioCache.key("id-ID-GadisNeural", "+0%", "Selamat pagi")
        assert key == cache_mod.AudioCache.key("id-ID-GadisNeural", "+0%", "Selamat pagi")
        assert len(key) == 64
        others = {cache_mod.AudioCache.key("id-ID-ArdiNeural", "+0%", "Selamat pagi"),
                  cache_mod.AudioCache.key("id-ID-GadisNeural", "+10%", "Selamat pagi"),
                  cache_mod.AudioCache.key("id-ID-GadisNeural", "+0%", "Selamat siang")}
        assert key not in others and len(others) == 3

    def test_miss_then_hit(self, tmp_path):
        cache = cache_mod.AudioCache(str(tmp_path / "edge"))
        key = cache.key("v", "+0%", "hello")
        assert cache.get(key) is None
        path = cache.put(key, MP3)
        assert cache.get(key) == path and open(path, "rb").read() == MP3
        assert not [n for n in os.listdir(tmp_path / "edge") if n.endswith(".tmp")]

    def test_least_recently_used_goes_first(self, tmp_path):
        cache = cache_mod.AudioCache(str(tmp_path), limit_bytes=1000)
        a = cache.put("a" * 64, b"x" * 400)
        b = cache.put("b" * 64, b"x" * 400)
        os.utime(a, (100, 100))
        os.utime(b, (200, 200))
        assert cache.get("a" * 64) == a                 # using it makes it recent
        c = cache.put("c" * 64, b"x" * 400)
        assert os.path.exists(a) and os.path.exists(c) and not os.path.exists(b)
        assert cache.size() == 800

    def test_the_new_file_and_other_files_stay(self, tmp_path):
        cache = cache_mod.AudioCache(str(tmp_path), limit_bytes=100)
        cache_mod.save_voice_list(str(tmp_path), [{"id": "x" * 500}])
        big = cache.put("d" * 64, b"x" * 400)          # alone over the limit
        assert os.path.exists(big)
        assert os.path.exists(tmp_path / cache_mod.VOICE_LIST_FILE)

    def test_voice_list_age(self, tmp_path):
        directory = str(tmp_path)
        voices = [{"id": "id-ID-GadisNeural", "name": "Gadis", "language": "id-ID"}]
        assert cache_mod.load_voice_list(directory) is None
        cache_mod.save_voice_list(directory, voices, now=1000)
        assert cache_mod.load_voice_list(directory, max_age=100, now=1050) == voices
        assert cache_mod.load_voice_list(directory, max_age=100, now=1200) is None
        assert cache_mod.load_voice_list(directory, max_age=100, now=900) is None  # clock back
        assert cache_mod.load_voice_list(directory, now=10 ** 9) == voices
        (tmp_path / cache_mod.VOICE_LIST_FILE).write_text("{broken", encoding="utf-8")
        assert cache_mod.load_voice_list(directory) is None


# ------------------------------------------------------------
# The extension: provider, back-off, cache use
# ------------------------------------------------------------

@pytest.fixture
def edge(tmp_data_dir, tmp_path, monkeypatch):
    import core.api
    import core.voice
    monkeypatch.setattr(core.api, "USER_DATA_DIR", str(tmp_path / "userdata"))
    spec = importlib.util.spec_from_file_location("edge_voices_main_under_test",
                                                  os.path.join(EDGE_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    played = []

    def play_file(path, volume, on_done):
        played.append((path, volume))
        on_done(None)

    monkeypatch.setattr(core.voice, "play_file", play_file)
    synthesized = []

    def synthesize(text, voice, rate="+0%", volume="+0%", cancelled=None, on_connection=None):
        synthesized.append((text, voice, rate))
        return MP3

    monkeypatch.setattr(service, "synthesize", synthesize)
    module.played, module.synthesized = played, synthesized
    module._reset_state()
    saved = dict(core.voice._providers)
    yield module
    module.stop()
    with core.voice._providers_lock:
        core.voice._providers.clear()
        core.voice._providers.update(saved)


def speak(edge, text="Selamat pagi", voice="id-ID-GadisNeural", rate=0, volume=100):
    done = []
    edge.speak(text, voice, rate, volume, done.append)
    assert wait_until(lambda: done), "on_done was not called"
    return done[0]


class TestExtension:
    def test_register_and_teardown(self, edge, fresh_event_bus):
        import core.voice
        edge.register(fresh_event_bus)
        provider = [p for p in core.voice.get_providers() if p["id"] == "edge"][0]
        assert provider["name"] in ("Microsoft Edge neural voices (online)",
                                    "Suara neural Microsoft Edge (online)")
        assert "Microsoft" in provider["privacy_note"]
        assert core.voice.is_provider_available("edge")
        edge.teardown()
        assert "edge" not in [p["id"] for p in core.voice.get_providers()]

    def test_manifest_and_privacy_note(self):
        with open(os.path.join(EDGE_DIR, "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["id"] == "edge_voices" and manifest["name"] == "Edge Voices"
        assert manifest["version"] == "1.0" and manifest["minimum_core_version"] == "2.7"
        with open(os.path.join(EDGE_DIR, "locales", "en.json"), encoding="utf-8") as f:
            en = json.load(f)["messages"]
        with open(os.path.join(EDGE_DIR, "locales", "id.json"), encoding="utf-8") as f:
            id_ = json.load(f)["messages"]
        assert set(en) == set(id_)
        assert "voice_female" not in en and "voice_male" not in en    # names are plain
        assert en["privacy_note"] == (
            "Edge voices send the text being read (for example your reminder titles) to "
            "Microsoft's online speech service. This service is meant for the Edge browser "
            "and may stop working at any time; Hariku then uses your fallback voice.")
        assert en["provider_name"] == "Microsoft Edge neural voices (online)"

    def test_official_everywhere(self):
        import ast
        for path, name in ((os.path.join(ROOT, "core", "extension_manager.py"),
                            "_OFFICIAL_EXTENSION_IDS"),
                           (os.path.join(ROOT, "tools", "server", "generate_trusted_hashes.py"),
                            "OFFICIAL_EXTENSION_IDS")):
            with open(path, encoding="utf-8") as f:
                assert '"edge_voices"' in f.read(), path

    def test_miss_synthesizes_saves_and_plays(self, edge):
        assert speak(edge, "Selamat pagi, Bro.", rate=2, volume=70) is None
        assert edge.synthesized == [("Selamat pagi, Bro.", "id-ID-GadisNeural", "+20%")]
        path, volume = edge.played[0]
        assert volume == 70 and open(path, "rb").read() == MP3
        assert os.path.dirname(path) == edge._cache_dir()
        assert edge._cache_dir().endswith(os.path.join("voice_cache", "edge"))

    def test_hit_plays_at_once_and_offline(self, edge, monkeypatch):
        speak(edge, "Selamat pagi, Bro.")

        def offline(*args, **kwargs):
            raise OSError("offline")

        monkeypatch.setattr(service, "synthesize", offline)
        assert speak(edge, "Selamat pagi, Bro.", volume=40) is None
        assert edge.played[1][1] == 40 and edge.played[0][0] == edge.played[1][0]
        # Another rate is another recording.
        assert isinstance(speak(edge, "Selamat pagi, Bro.", rate=5), OSError)

    def test_default_voice_follows_the_language(self, edge, monkeypatch):
        import core.i18n
        monkeypatch.setattr(core.i18n, "_current_language", "id")
        speak(edge, "Halo", voice="")
        monkeypatch.setattr(core.i18n, "_current_language", "en")
        speak(edge, "Hello", voice="")
        assert [s[1] for s in edge.synthesized] == ["id-ID-GadisNeural",
                                                    "en-US-EmmaMultilingualNeural"]

    def test_three_failures_pause_it_for_ten_minutes(self, edge, monkeypatch):
        calls = []

        def failing(*args, **kwargs):
            calls.append(args)
            raise OSError("blocked")

        monkeypatch.setattr(service, "synthesize", failing)
        for i in range(2):
            assert isinstance(speak(edge, f"text {i}"), OSError)
            assert edge.is_available()
        assert isinstance(speak(edge, "text 2"), OSError)
        assert not edge.is_available()
        error = speak(edge, "text 3")
        assert isinstance(error, edge.Unavailable) and len(calls) == 3   # not tried
        now = time.monotonic()
        monkeypatch.setattr(edge.time, "monotonic", lambda: now + edge.PAUSE_SECONDS + 1)
        assert edge.is_available()

    def test_a_success_resets_the_count(self, edge, monkeypatch):
        state = {"fail": True}

        def flaky(text, voice, rate="+0%", volume="+0%", cancelled=None, on_connection=None):
            if state["fail"]:
                raise OSError("blocked")
            return MP3

        monkeypatch.setattr(service, "synthesize", flaky)
        speak(edge, "a")
        speak(edge, "b")
        state["fail"] = False
        assert speak(edge, "c") is None
        state["fail"] = True
        speak(edge, "d")
        speak(edge, "e")
        assert edge.is_available()

    def test_stop_cancels_a_synthesis(self, edge, monkeypatch):
        started = threading.Event()
        aborted = []

        class Connection:
            def abort(self):
                aborted.append(True)

        def slow(text, voice, rate="+0%", volume="+0%", cancelled=None, on_connection=None):
            on_connection(Connection())
            started.set()
            while not cancelled():
                time.sleep(0.005)
            raise service.Cancelled()

        monkeypatch.setattr(service, "synthesize", slow)
        done = []
        edge.speak("A long text", "id-ID-ArdiNeural", 0, 100, done.append)
        assert started.wait(2)
        edge.speak("Queued", "id-ID-ArdiNeural", 0, 100, done.append)
        edge.stop()
        assert wait_until(lambda: len(done) == 2)
        assert done == [None, None] and aborted == [True]
        assert edge.played == [] and edge.is_available()

    def test_voices_from_the_saved_list(self, edge, monkeypatch):
        import core.i18n
        monkeypatch.setattr(core.i18n, "_current_language", "en")
        fetched = []
        monkeypatch.setattr(service, "fetch_voice_list",
                            lambda: fetched.append(1) or protocol.parse_voice_list(VOICE_LIST))
        voices = edge.list_voices()
        assert fetched == [1]
        # The plain name and the gender: Preferences groups them by language and gender.
        assert voices[:2] == [{"id": "id-ID-ArdiNeural", "name": "Ardi",
                               "language": "id-ID", "gender": "male"},
                              {"id": "id-ID-GadisNeural", "name": "Gadis",
                               "language": "id-ID", "gender": "female"}]
        assert voices[2]["name"] == "Emma Multilingual"
        assert edge.list_voices() == voices and fetched == [1]      # 7 days from disk
        monkeypatch.setattr(core.i18n, "_current_language", "id")
        assert edge.list_voices() == voices                          # the same in Indonesian

    def test_core_keeps_the_gender(self, edge, monkeypatch):
        import core.voice
        monkeypatch.setattr(service, "fetch_voice_list",
                            lambda: protocol.parse_voice_list(VOICE_LIST))
        core.voice.register_provider(edge.PROVIDER_ID, "Edge", edge.list_voices, edge.speak,
                                     edge.stop, edge.is_available)
        voices = core.voice.list_voices(edge.PROVIDER_ID)
        assert [(v["name"], v["gender"]) for v in voices] == [
            ("Ardi", "male"), ("Gadis", "female"), ("Emma Multilingual", "female"),
            ("Xiaobei", "female")]

    def test_old_list_is_refreshed_and_kept_when_offline(self, edge, monkeypatch):
        directory = edge._cache_dir()
        cache_mod.save_voice_list(directory, protocol.parse_voice_list(VOICE_LIST)[:1],
                                  now=time.time() - edge.VOICE_LIST_MAX_AGE - 10)

        def offline():
            raise OSError("offline")

        monkeypatch.setattr(service, "fetch_voice_list", offline)
        assert [v["id"] for v in edge.list_voices()] == ["id-ID-ArdiNeural"]
        monkeypatch.setattr(service, "fetch_voice_list",
                            lambda: protocol.parse_voice_list(VOICE_LIST))
        assert len(edge.list_voices()) == 4
        assert len(cache_mod.load_voice_list(directory, max_age=60)) == 4

    def test_no_list_and_offline_raises(self, edge, monkeypatch):
        def offline():
            raise OSError("offline")

        monkeypatch.setattr(service, "fetch_voice_list", offline)
        with pytest.raises(OSError):
            edge.list_voices()

    def test_stdlib_only(self):
        import ast
        allowed_local = {"edge_voices_cache", "edge_voices_protocol", "edge_voices_service",
                         "edge_voices_ws"}
        for name in os.listdir(EDGE_DIR):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(EDGE_DIR, name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module]
                else:
                    continue
                for mod in mods:
                    top = mod.split(".")[0]
                    assert top in sys.stdlib_module_names or top == "core" or \
                        mod in allowed_local, f"{name} imports {mod}"


def test_no_network_was_used(no_network):
    assert no_network == []
