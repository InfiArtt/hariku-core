# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The message formats of Microsoft Edge's "Read Aloud" speech service, with no
network code: the endpoint and headers, the Sec-MS-GEC token, the speech.config
and SSML messages, and parsing what the service sends back.

The service is unofficial (it exists for the Edge browser). The values here are
the ones the Edge browser sends, as documented by the open-source edge-tts
project (https://github.com/rany2/edge-tts). This is an independent
implementation of the protocol; no edge-tts code is used.

A synthesis is one WebSocket connection:
  1. client -> "Path:speech.config" (JSON: the audio format),
  2. client -> "Path:ssml" (the text, voice and rate as SSML),
  3. service -> text frames (turn.start, response, audio.metadata) and binary
     frames: a 2-byte big-endian header length, headers ("Path:audio",
     "Content-Type:audio/mpeg"), then MP3 data,
  4. service -> "Path:turn.end": done.
"""
import calendar
import hashlib
import json
import os
import re
import time
import uuid

TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
HOST = "speech.platform.bing.com"
BASE_PATH = "/consumer/speech/synthesize/readaloud"
WSS_PATH = BASE_PATH + "/edge/v1"
VOICE_LIST_PATH = BASE_PATH + "/voices/list"

CHROMIUM_FULL_VERSION = "143.0.3650.75"
CHROMIUM_MAJOR_VERSION = CHROMIUM_FULL_VERSION.split(".", 1)[0]
SEC_MS_GEC_VERSION = "1-" + CHROMIUM_FULL_VERSION
ORIGIN = "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
              f" (KHTML, like Gecko) Chrome/{CHROMIUM_MAJOR_VERSION}.0.0.0 Safari/537.36"
              f" Edg/{CHROMIUM_MAJOR_VERSION}.0.0.0")

OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MAX_SSML_TEXT_BYTES = 4096      # per request, after escaping
WIN_EPOCH_SECONDS = 11644473600  # 1601-01-01 to 1970-01-01

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_VOICE_RE = re.compile(r"([a-z]{2,})-([A-Z]{2,})-(.+Neural)\Z")
_SAFE_VOICE_RE = re.compile(r"[A-Za-z0-9-]{1,100}\Z")


class ProtocolError(Exception):
    """The service sent something this implementation doesn't expect."""


# ------------------------------------------------------------
# Sec-MS-GEC: a token derived from the time, checked by the service
# ------------------------------------------------------------

_clock_skew = 0.0


def current_time():
    """The Unix time, corrected by what the service's clock told us."""
    return time.time() + _clock_skew


def sec_ms_gec(unix_time=None):
    """SHA-256 (upper-case hex) of the Windows file time rounded down to 5
    minutes, in 100-nanosecond units, followed by the trusted client token."""
    seconds = int(current_time() if unix_time is None else unix_time) + WIN_EPOCH_SECONDS
    seconds -= seconds % 300
    ticks = seconds * 10_000_000
    return hashlib.sha256(f"{ticks}{TRUSTED_CLIENT_TOKEN}".encode("ascii")).hexdigest().upper()


def parse_http_date(text):
    """Unix time of an RFC 2616 date ("Wed, 24 Sep 2026 10:00:00 GMT"), or None.
    Parsed by hand: strptime's day and month names follow the locale."""
    try:
        _day, rest = str(text).strip().split(",", 1)
        day, month, year, clock, zone = rest.split()
        if zone.upper() not in ("GMT", "UTC"):
            return None
        hour, minute, second = (int(part) for part in clock.split(":"))
        return float(calendar.timegm((int(year), _MONTHS.index(month.title()) + 1, int(day),
                                      hour, minute, second, 0, 0, 0)))
    except (ValueError, AttributeError):
        return None


def adjust_clock_skew(server_date):
    """After a 403, trust the server's Date header for the token's time.
    Returns whether it could be used."""
    global _clock_skew
    server_time = parse_http_date(server_date) if server_date else None
    if server_time is None:
        return False
    _clock_skew += server_time - current_time()
    return True


def reset_clock_skew():
    global _clock_skew
    _clock_skew = 0.0


# ------------------------------------------------------------
# Requests
# ------------------------------------------------------------

def _muid():
    return os.urandom(16).hex().upper()


def _base_headers():
    return {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9"}


def websocket_headers():
    """Headers for the WebSocket handshake (besides the WebSocket ones)."""
    headers = {"Pragma": "no-cache", "Cache-Control": "no-cache", "Origin": ORIGIN}
    headers.update(_base_headers())
    headers["Cookie"] = f"muid={_muid()};"
    return headers


def voice_list_headers():
    headers = {
        "Authority": HOST,
        "Sec-CH-UA": f'" Not;A Brand";v="99", "Microsoft Edge";v="{CHROMIUM_MAJOR_VERSION}",'
                     f' "Chromium";v="{CHROMIUM_MAJOR_VERSION}"',
        "Sec-CH-UA-Mobile": "?0",
        "Accept": "*/*",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }
    headers.update(_base_headers())
    # Only what the standard library can decompress.
    headers["Accept-Encoding"] = "gzip, deflate"
    headers["Cookie"] = f"muid={_muid()};"
    return headers


def _token_query():
    return f"Sec-MS-GEC={sec_ms_gec()}&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}"


def websocket_path(connection_id=None):
    connection_id = connection_id or uuid.uuid4().hex
    return (f"{WSS_PATH}?TrustedClientToken={TRUSTED_CLIENT_TOKEN}"
            f"&ConnectionId={connection_id}&{_token_query()}")


def voice_list_url():
    return (f"https://{HOST}{VOICE_LIST_PATH}?trustedclienttoken={TRUSTED_CLIENT_TOKEN}"
            f"&{_token_query()}")


def timestamp(unix_time=None):
    """"Wed Sep 24 2026 10:00:00 GMT+0000 (Coordinated Universal Time)", in
    English whatever the locale."""
    t = time.gmtime(current_time() if unix_time is None else unix_time)
    return (f"{_DAYS[t.tm_wday]} {_MONTHS[t.tm_mon - 1]} {t.tm_mday:02d} {t.tm_year} "
            f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d} GMT+0000 (Coordinated Universal Time)")


def speech_config_message(unix_time=None):
    config = {"context": {"synthesis": {"audio": {
        "metadataoptions": {"sentenceBoundaryEnabled": "true", "wordBoundaryEnabled": "false"},
        "outputFormat": OUTPUT_FORMAT}}}}
    return (f"X-Timestamp:{timestamp(unix_time)}\r\n"
            "Content-Type:application/json; charset=utf-8\r\n"
            "Path:speech.config\r\n\r\n"
            f"{json.dumps(config, separators=(',', ':'))}\r\n")


def ssml_message(ssml_text, request_id=None, unix_time=None):
    request_id = request_id or uuid.uuid4().hex
    # The "Z" after the timestamp is what Edge sends.
    return (f"X-RequestId:{request_id}\r\n"
            "Content-Type:application/ssml+xml\r\n"
            f"X-Timestamp:{timestamp(unix_time)}Z\r\n"
            "Path:ssml\r\n\r\n"
            f"{ssml_text}")


# ------------------------------------------------------------
# SSML
# ------------------------------------------------------------

def clean_text(text):
    """Control characters the service rejects become spaces."""
    return "".join(" " if ord(c) < 32 and c not in "\t\n\r" else c for c in str(text))


def escape_text(text):
    """Text safe inside an SSML element: control characters removed, & < >
    escaped (reminder titles may contain them)."""
    return (clean_text(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def long_voice_name(short_name):
    """"id-ID-GadisNeural" -> "Microsoft Server Speech Text to Speech Voice
    (id-ID, GadisNeural)", the form Edge sends. ValueError for anything else."""
    short_name = str(short_name or "")
    match = _VOICE_RE.match(short_name) if _SAFE_VOICE_RE.match(short_name) else None
    if match is None:
        raise ValueError(f"not an Edge voice name: {short_name!r}")
    language, region, name = match.groups()
    if "-" in name:
        # "zh-CN-liaoning-XiaobeiNeural": the region continues up to the name.
        extra, name = name.split("-", 1)
        region = f"{region}-{extra}"
    return f"Microsoft Server Speech Text to Speech Voice ({language}-{region}, {name})"


def rate_percent(rate):
    """Hariku's rate (-10..10, 0 normal) as SSML prosody: up to twice as fast
    (+100%), down to half speed (-50%), within the service's range."""
    try:
        rate = max(-10, min(10, int(rate)))
    except (TypeError, ValueError):
        rate = 0
    return f"{rate * 10 if rate >= 0 else rate * 5:+d}%"


def volume_percent(volume):
    """0..100 as a relative SSML volume ("+0%" is the voice's own level)."""
    try:
        volume = max(0, min(100, int(volume)))
    except (TypeError, ValueError):
        volume = 100
    return f"{volume - 100:+d}%"


def build_ssml(text, voice, rate="+0%", volume="+0%"):
    """One SSML document. `text` is plain text (escaped here); `rate` and
    `volume` are prosody values like "+20%"."""
    for value in (rate, volume):
        if not re.match(r"[+-]\d{1,3}%\Z", str(value)):
            raise ValueError(f"bad prosody value: {value!r}")
    return ("<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
            f"<voice name='{long_voice_name(voice)}'>"
            f"<prosody pitch='+0Hz' rate='{rate}' volume='{volume}'>"
            f"{escape_text(text)}"
            "</prosody></voice></speak>")


def _escaped_size(text):
    return len(escape_text(text).encode("utf-8"))


def split_text(text, limit=MAX_SSML_TEXT_BYTES):
    """Split text between words into pieces whose escaped UTF-8 fits `limit`
    bytes (one request each). A single longer word is cut where it must be."""
    pieces, current = [], ""
    for word in clean_text(text).split():
        candidate = f"{current} {word}" if current else word
        if _escaped_size(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        while _escaped_size(word) > limit:
            low, high = 1, len(word)          # the longest prefix that fits
            while low < high:
                middle = (low + high + 1) // 2
                if _escaped_size(word[:middle]) <= limit:
                    low = middle
                else:
                    high = middle - 1
            pieces.append(word[:low])
            word = word[low:]
        current = word
    if current:
        pieces.append(current)
    return pieces


# ------------------------------------------------------------
# What the service sends
# ------------------------------------------------------------

def _header_lines(block):
    headers = {}
    for line in block.split("\r\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    return headers


def parse_text_message(text):
    """(headers, body) of a text frame: "Key:Value" lines, a blank line, body."""
    head, _sep, body = str(text).partition("\r\n\r\n")
    return _header_lines(head), body


def parse_binary_message(data):
    """(headers, payload) of a binary frame: a 2-byte big-endian length of the
    header block that follows, then the payload."""
    data = bytes(data)
    if len(data) < 2:
        raise ProtocolError("a binary message without a header length")
    length = int.from_bytes(data[:2], "big")
    if length > len(data) - 2:
        raise ProtocolError("a binary message whose headers are longer than the message")
    try:
        head = data[2:2 + length].decode("utf-8")
    except UnicodeDecodeError:
        raise ProtocolError("a binary message with unreadable headers") from None
    return _header_lines(head), data[2 + length:]


def audio_from_binary(data):
    """The MP3 bytes of a binary frame ("Path:audio"); b"" for the empty frame
    that may end the stream. ProtocolError for anything else."""
    headers, payload = parse_binary_message(data)
    if headers.get("Path") != "audio":
        raise ProtocolError(f"a binary message for {headers.get('Path')!r}, not audio")
    content_type = headers.get("Content-Type")
    if content_type is None:
        if payload:
            raise ProtocolError("audio data without a Content-Type")
        return b""
    if content_type != "audio/mpeg":
        raise ProtocolError(f"unexpected audio type {content_type!r}")
    if not payload:
        raise ProtocolError("an audio message without audio")
    return payload


# ------------------------------------------------------------
# The voice list
# ------------------------------------------------------------

def _split_words(name):
    # "EmmaMultilingual" -> "Emma Multilingual"
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).strip()


def short_display_name(short_name, locale):
    """"id-ID-GadisNeural" -> "Gadis"."""
    name = short_name[len(locale) + 1:] if locale and short_name.startswith(locale + "-") \
        else short_name.rsplit("-", 1)[-1]
    if name.endswith("Neural"):
        name = name[:-len("Neural")]
    return _split_words(name) or short_name


def parse_voice_list(data):
    """The service's voice list as [{"id", "name", "language", "gender"}]:
    "id" is the short name ("id-ID-ArdiNeural"), "language" the locale
    ("id-ID"), "gender" "female", "male" or "". Unusable entries are skipped."""
    if not isinstance(data, list):
        raise ProtocolError("the voice list is not a list")
    voices, seen = [], set()
    for item in data:
        if not isinstance(item, dict):
            continue
        short_name = item.get("ShortName")
        locale = item.get("Locale")
        if not isinstance(short_name, str) or not isinstance(locale, str) or short_name in seen:
            continue
        if str(item.get("Status", "")).lower() == "deprecated":
            continue
        try:
            long_voice_name(short_name)
        except ValueError:
            continue
        seen.add(short_name)
        gender = str(item.get("Gender", "")).lower()
        voices.append({"id": short_name, "name": short_display_name(short_name, locale),
                       "language": locale,
                       "gender": gender if gender in ("female", "male") else ""})
    return voices
