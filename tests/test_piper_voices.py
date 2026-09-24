# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for the Piper Voices extension: the voice index (a synthetic one in the
# shape of rhasspy/piper-voices' voices.json), language filtering, model cards,
# checksums, allowed hosts and redirects, zip-slip safe unpacking, resumed and
# cleaned-up downloads, the rate mapping, the piper.exe command line (with
# subprocess replaced), the WAV cache, stopping, and the provider. No test
# touches the network (a guard fails any attempt), starts piper.exe or plays
# anything.

import email.parser
import hashlib
import http.client
import importlib.util
import io
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import urllib.response
import wave
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPER_DIR = os.path.join(ROOT, "extensions", "piper_voices")
if PIPER_DIR not in sys.path:
    sys.path.insert(0, PIPER_DIR)

import piper_voices_catalogue as catalogue   # noqa: E402
import piper_voices_download as dl           # noqa: E402
import piper_voices_store as store           # noqa: E402
import piper_voices_synth as synth           # noqa: E402
import piper_voices_text as text             # noqa: E402


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
    yield attempts


@pytest.fixture
def english(monkeypatch):
    import core.i18n
    monkeypatch.setattr(core.i18n, "_current_language", "en")


# ------------------------------------------------------------
# A voice index in the shape voices.json has (checked against the real one)
# ------------------------------------------------------------

def md5(data):
    return hashlib.md5(data).hexdigest()


# The Indonesian voice's real model card, byte for byte.
CARD_ID = ("# Model card for news_tts (medium)\n\n"
           "* Language: id_ID (Indonesian, Indonesia)\n"
           "* Speakers: 1\n"
           "* Quality: medium\n"
           "* Samplerate: 22,050Hz\n\n"
           "## Dataset\n\n"
           "* URL: https://www.kaggle.com/code/mpwolke/indic-tts-malayalam-speech-corpus\n"
           "* License:  See URL\n\n"
           "## Training\n\n"
           "Finetuned from U.S. English lessac voice (medium quality).\n")
CARD_EN = ("# Model card for lessac (medium)\n\n* Language: en_US (English, United States)\n\n"
           "## Dataset\n\n* URL: https://example.org/lessac\n* License: CC BY 4.0\n")

FILES = {}      # URL -> bytes, for the fake servers below


def make_entry(code, name, quality, model=b"ONNX-MODEL", config=b'{"audio": {}}', card=CARD_EN,
               english="English", country="United States", speakers=1, table=None):
    family, region = code.split("_")
    key = f"{code}-{name}-{quality}"
    base = f"{family}/{code}/{name}/{quality}/"
    files = {}
    for path, data in ((base + key + ".onnx", model), (base + key + ".onnx.json", config),
                       (base + "MODEL_CARD", card.encode("utf-8"))):
        files[path] = {"size_bytes": len(data), "md5_digest": md5(data)}
        if table is not None:
            table[catalogue.FILES_URL + path] = data
    return key, {
        "key": key, "name": name,
        "language": {"code": code, "family": family, "region": region,
                     "name_native": english, "name_english": english,
                     "country_english": country},
        "quality": quality, "num_speakers": speakers, "speaker_id_map": {},
        "files": files, "aliases": [],
    }


def make_index():
    return dict([
        make_entry("id_ID", "news_tts", "medium", model=b"I" * 5000, card=CARD_ID,
                   english="Indonesian", country="Indonesia", table=FILES),
        make_entry("en_US", "lessac", "high", model=b"H" * 3000, table=FILES),
        make_entry("en_US", "lessac", "medium", model=b"M" * 2000, table=FILES),
        make_entry("en_GB", "alba", "medium", english="English", country="Great Britain",
                   table=FILES),
        make_entry("de_DE", "thorsten", "low", english="German", country="Germany",
                   table=FILES),
        make_entry("pt_PT", "tugão", "medium", english="Portuguese", country="Portugal",
                   table=FILES),
    ])


INDEX = make_index()


def voice_of(key):
    return [v for v in catalogue.parse_catalogue(INDEX) if v["key"] == key][0]


# ------------------------------------------------------------
# The catalogue
# ------------------------------------------------------------

class TestCatalogue:
    def test_parsing(self):
        voices = catalogue.parse_catalogue(INDEX)
        assert [v["key"] for v in voices] == sorted(INDEX)
        voice = voice_of("id_ID-news_tts-medium")
        assert voice["name"] == "news_tts" and voice["quality"] == "medium"
        assert voice["language"] == "id-ID" and voice["family"] == "id"
        assert voice["language_english"] == "Indonesian"
        assert voice["country_english"] == "Indonesia" and voice["speakers"] == 1
        files = voice["files"]
        assert files["model"]["path"] == "id/id_ID/news_tts/medium/id_ID-news_tts-medium.onnx"
        assert files["model"]["size"] == 5000 and files["model"]["md5"] == md5(b"I" * 5000)
        assert files["config"]["path"].endswith("id_ID-news_tts-medium.onnx.json")
        assert files["card"]["path"] == "id/id_ID/news_tts/medium/MODEL_CARD"
        assert voice["size"] == 5000 + len(b'{"audio": {}}')      # the card comes first

    def test_unicode_names_and_their_urls(self):
        voice = voice_of("pt_PT-tugão-medium")
        assert catalogue.file_url(voice["files"]["model"]["path"]) == (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "pt/pt_PT/tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx")

    def _broken(self, change):
        key, entry = make_entry("id_ID", "news_tts", "medium")
        entry = json.loads(json.dumps(entry))
        change(key, entry)
        return key, entry

    @pytest.mark.parametrize("change", [
        lambda k, e: e["files"].pop([p for p in e["files"] if p.endswith("MODEL_CARD")][0]),
        lambda k, e: e["files"][[p for p in e["files"] if p.endswith(".onnx")][0]].update(
            md5_digest="not-md5"),
        lambda k, e: e["files"][[p for p in e["files"] if p.endswith(".onnx")][0]].update(
            size_bytes=-5),
        lambda k, e: e["files"][[p for p in e["files"] if p.endswith(".onnx")][0]].update(
            size_bytes=True),
        lambda k, e: e["files"][[p for p in e["files"] if p.endswith(".onnx")][0]].update(
            size_bytes=5 * 1024 ** 3),
        lambda k, e: e.update(files={("../../" + p): v for p, v in e["files"].items()}),
        lambda k, e: e.update(files={p.replace("id/", "C:/", 1): v for p, v in e["files"].items()}),
        lambda k, e: e.update(quality="high"),
        lambda k, e: e.update(key="id_ID-other-medium"),
        lambda k, e: e["language"].update(code="en_US"),
        lambda k, e: e.update(language="id_ID"),
        lambda k, e: e.update(files=[]),
    ])
    def test_unusable_entries_are_skipped(self, change):
        key, entry = self._broken(change)
        assert catalogue.parse_voice(key, entry) is None
        good_key, good = make_entry("en_US", "lessac", "medium")
        assert [v["key"] for v in catalogue.parse_catalogue({key: entry, good_key: good})] == \
            [good_key]
        with pytest.raises(catalogue.CatalogueError):
            catalogue.parse_catalogue({key: entry})

    @pytest.mark.parametrize("bad", [[], "voices", None, {}, {"x": "y"},
                                     {"../evil-x-medium": {}}])
    def test_not_an_index(self, bad):
        with pytest.raises(catalogue.CatalogueError):
            catalogue.parse_catalogue(bad)

    @pytest.mark.parametrize("path", ["../x", "a/../b", "a\\b", "C:/x", "/x", "", "a//b",
                                      "a/./b", "a/b\x00c"])
    def test_unsafe_paths(self, path):
        assert not catalogue.safe_path(path)
        with pytest.raises(catalogue.CatalogueError):
            catalogue.file_url(path)

    def test_keys(self):
        assert catalogue.valid_key("id_ID-news_tts-medium")
        assert catalogue.valid_key("zh_CN-huayan-x_low")
        for bad in ("id_ID-news_tts", "../x-medium", "id_ID-a b-medium", "id-news-medium",
                    "id_ID-news-medium\\..", None, 5):
            assert not catalogue.valid_key(bad), bad


class TestLanguages:
    def test_filter(self):
        voices = catalogue.parse_catalogue(INDEX)
        assert [v["key"] for v in catalogue.filter_voices(voices, "id")] == \
            ["id_ID-news_tts-medium"]
        assert {v["key"] for v in catalogue.filter_voices(voices, "en-US")} == \
            {"en_GB-alba-medium", "en_US-lessac-high", "en_US-lessac-medium"}
        assert len(catalogue.filter_voices(voices, None)) == len(INDEX)
        assert catalogue.filter_voices(voices, "fr") == []

    def test_order_puts_the_user_languages_first(self):
        voices = catalogue.parse_catalogue(INDEX)
        keys = [v["key"] for v in catalogue.order_voices(voices, ["id", "en"])]
        assert keys == ["id_ID-news_tts-medium", "en_GB-alba-medium", "en_US-lessac-medium",
                        "en_US-lessac-high", "de_DE-thorsten-low", "pt_PT-tugão-medium"]
        keys = [v["key"] for v in catalogue.order_voices(voices, ["en-US"])]
        assert keys[:3] == ["en_GB-alba-medium", "en_US-lessac-medium", "en_US-lessac-high"]
        assert keys[3:] == ["de_DE-thorsten-low", "id_ID-news_tts-medium", "pt_PT-tugão-medium"]

    def test_language_choices(self):
        voices = catalogue.parse_catalogue(INDEX)
        names = {"de": "German", "en": "English", "id": "Indonesian", "pt": "Portuguese"}
        assert catalogue.language_choices(voices, ["id", "en"], names.get) == \
            ["id", "en", None, "de", "pt"]
        # A user language without voices is skipped; All is then first.
        assert catalogue.language_choices(voices, ["fr"], names.get) == \
            [None, "en", "de", "id", "pt"]
        assert catalogue.language_choices([], ["id"]) == [None]

    def test_labels(self, english):
        voice = voice_of("id_ID-news_tts-medium")
        assert text.voice_title(voice) == "News tts"
        assert text.voice_name(voice) == "News tts (Medium)"
        assert text.quality_label("x_low") == "Extra low"
        assert text.size_label(62955094) == "60.0 MB"
        assert text.size_label(5050) == "5 KB"
        assert text.family_label(None) == "All languages"
        assert text.installed_label(True) == "Installed"
        assert text.installed_label(False) == "Not installed"

    def test_indonesian_decimal_comma(self, monkeypatch):
        import core.i18n
        monkeypatch.setattr(core.i18n, "_current_language", "id")
        assert text.size_label(62955094) == "60,0 MB"
        assert text.quality_label("medium") == "Sedang"


# ------------------------------------------------------------
# Model cards
# ------------------------------------------------------------

class TestModelCard:
    def test_the_indonesian_card(self):
        card = catalogue.parse_model_card(CARD_ID)
        assert card == {
            "lines": ["URL: https://www.kaggle.com/code/mpwolke/indic-tts-malayalam-speech-corpus",
                      "License: See URL"],
            "dataset_url": "https://www.kaggle.com/code/mpwolke/indic-tts-malayalam-speech-corpus",
            "license": "See URL", "license_clear": False}

    def test_a_clear_license(self):
        card = catalogue.parse_model_card(CARD_EN.encode("utf-8"))
        assert card["license"] == "CC BY 4.0" and card["license_clear"] is True
        assert card["lines"] == ["URL: https://example.org/lessac", "License: CC BY 4.0"]

    @pytest.mark.parametrize("license_text, clear", [
        ("See URL", False), ("see url.", False), ("", False), ("Unknown", False),
        ("CC0", True), ("MIT", True), ("CC BY-SA 4.0", True), ("Public domain", True)])
    def test_clear_or_not(self, license_text, clear):
        assert catalogue.license_is_clear(license_text) is clear

    def test_no_license_and_odd_input(self, english):
        card = catalogue.parse_model_card("## Dataset\n\n* URL: https://x.example/\x07data\n")
        assert card["license"] == "" and not card["license_clear"]
        assert card["lines"] == ["URL: https://x.example/ data"]
        lines = text.card_lines(card)
        assert "License: not stated in the model card." in lines
        assert any("doesn't name a clear license" in line for line in lines)
        # A license outside the Dataset section still counts.
        card = catalogue.parse_model_card("# Card\n\n* License: CC0\n")
        assert card["license"] == "CC0" and card["lines"] == ["License: CC0"]
        assert catalogue.parse_model_card(None)["lines"] == []

    def test_confirmation_and_details_say_it_honestly(self, english):
        voice = voice_of("id_ID-news_tts-medium")
        card = catalogue.parse_model_card(CARD_ID)
        summary = text.confirm_summary(voice, card, runtime_size=dl.RUNTIME_SIZE)
        assert "Download the voice News tts, " in summary and "Medium quality?" in summary
        assert "plus 21.4 MB for the Piper program" in summary
        assert "Dataset license: See URL" in summary
        assert "doesn't name a clear license" in summary
        details = text.details_text(voice, False, card)
        assert "License: See URL" in details and "Not installed." in details
        assert "Quality: Medium. Speakers: 1." in details
        assert "Download size:" in text.confirm_summary(voice, card)
        assert "Piper program" not in text.confirm_summary(voice, card)
        pending = text.details_text(voice, False, None)
        assert "shown when you press Download" in pending


# ------------------------------------------------------------
# Hosts and redirects
# ------------------------------------------------------------

class TestHosts:
    @pytest.mark.parametrize("url", [
        "https://github.com/rhasspy/piper/releases/download/x/y.zip",
        "https://objects.githubusercontent.com/github-production-release-asset/1",
        "https://release-assets.githubusercontent.com/github-production-release-asset/1",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json",
        "https://HuggingFace.co/x", "https://huggingface.co./x", "https://hf.co/x",
        "https://us.aws.cdn.hf.co/xet-bridge-us/abc", "https://cas-bridge.xethub.hf.co/x",
        "https://cdn-lfs.huggingface.co/x", "https://github.com:443/x",
    ])
    def test_allowed(self, url):
        assert dl.host_allowed(url)

    @pytest.mark.parametrize("url", [
        "http://github.com/x", "http://huggingface.co/x", "ftp://github.com/x",
        "https://evil.example/x", "https://github.com.evil.example/x",
        "https://evilhf.co/x", "https://huggingface.co.evil.example/x",
        "https://raw.githubusercontent.com/x", "https://user@github.com/x",
        "https://github.com:8443/x", "https://[::1]/x", "", "github.com/x",
        "https://gist.github.com/x", "file:///C:/Windows/win.ini",
    ])
    def test_refused(self, url):
        assert not dl.host_allowed(url)

    def test_the_first_url_is_checked_before_any_request(self, no_network):
        with pytest.raises(dl.DownloadError) as error:
            dl.open_url("https://evil.example/voices.json")
        assert error.value.kind == "host" and error.value.detail == "evil.example"
        assert no_network == []

    def test_redirect_handler(self):
        handler = dl.CheckedRedirects()
        request = urllib.request.Request("https://github.com/a",
                                         headers={"User-Agent": dl.user_agent(),
                                                  "Range": "bytes=10-"})

        class Body(io.BytesIO):
            pass

        new = handler.redirect_request(request, Body(b""), 302, "Found", {},
                                       "https://release-assets.githubusercontent.com/b")
        assert new.full_url == "https://release-assets.githubusercontent.com/b"
        assert new.get_header("User-agent") == dl.user_agent()
        assert new.get_header("Range") == "bytes=10-"
        body = Body(b"")
        with pytest.raises(dl.DownloadError) as error:
            handler.redirect_request(request, body, 302, "Found", {}, "https://evil.example/b")
        assert error.value.kind == "host" and body.closed
        with pytest.raises(dl.DownloadError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://github.com/b")

    def test_user_agent(self):
        import core.constants
        assert dl.user_agent() == f"HarikuV2/{core.constants.CORE_VERSION} (Piper Voices extension)"


class FakeServer(urllib.request.HTTPSHandler):
    """Answers HTTPS requests from a table, through urllib's real redirect
    handling: routes[url] = (status, headers, body)."""

    def __init__(self, routes):
        super().__init__()
        self.routes = routes
        self.seen = []

    def https_open(self, req):
        self.seen.append((req.full_url, dict(req.header_items())))
        if req.full_url not in self.routes:
            raise AssertionError(f"unexpected request to {req.full_url}")
        status, headers, body = self.routes[req.full_url]
        head = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        message = email.parser.Parser(_class=http.client.HTTPMessage).parsestr(head)
        response = urllib.response.addinfourl(io.BytesIO(body), message, req.full_url, status)
        response.msg = http.client.responses.get(status, "")
        return response


class TestRedirects:
    def test_github_release_redirect(self):
        server = FakeServer({
            dl.RUNTIME_URL: (302, {"Location": "https://release-assets.githubusercontent.com/"
                                               "github-production-release-asset/1?sig=x"}, b""),
            "https://release-assets.githubusercontent.com/github-production-release-asset/1?sig=x":
                (200, {"Content-Length": "4"}, b"PKzz"),
        })
        with dl.open_url(dl.RUNTIME_URL, opener=dl.build_opener(server)) as response:
            assert response.read() == b"PKzz"
        assert [url for url, _h in server.seen][1].startswith(
            "https://release-assets.githubusercontent.com/")
        assert all(h.get("User-agent") == dl.user_agent() for _u, h in server.seen)

    def test_hugging_face_relative_redirect_then_cdn(self):
        start = catalogue.FILES_URL + "id/id_ID/news_tts/medium/id_ID-news_tts-medium.onnx"
        server = FakeServer({
            start: (307, {"Location": "/api/resolve-cache/models/rhasspy/piper-voices/abc/x"},
                    b""),
            "https://huggingface.co/api/resolve-cache/models/rhasspy/piper-voices/abc/x":
                (302, {"Location": "https://us.aws.cdn.hf.co/xet-bridge-us/1/2"}, b""),
            "https://us.aws.cdn.hf.co/xet-bridge-us/1/2": (200, {}, b"model"),
        })
        with dl.open_url(start, headers={"Range": "bytes=2-"},
                         opener=dl.build_opener(server)) as response:
            assert response.read() == b"model"
        assert server.seen[-1][1].get("Range") == "bytes=2-"

    def test_a_redirect_elsewhere_is_refused(self):
        server = FakeServer({
            dl.RUNTIME_URL: (302, {"Location": "https://evil.example/piper.zip"}, b""),
        })
        with pytest.raises(dl.DownloadError) as error:
            dl.open_url(dl.RUNTIME_URL, opener=dl.build_opener(server))
        assert error.value.kind == "host" and error.value.detail == "evil.example"
        assert [url for url, _h in server.seen] == [dl.RUNTIME_URL]      # never asked

    def test_a_redirect_to_plain_http_is_refused(self):
        server = FakeServer({
            catalogue.INDEX_URL: (302, {"Location": "http://huggingface.co/voices.json"}, b""),
        })
        with pytest.raises(dl.DownloadError) as error:
            dl.open_url(catalogue.INDEX_URL, opener=dl.build_opener(server))
        assert error.value.kind == "host"

    def test_http_errors(self):
        server = FakeServer({catalogue.INDEX_URL: (404, {}, b"not found")})
        with pytest.raises(dl.DownloadError) as error:
            dl.open_url(catalogue.INDEX_URL, opener=dl.build_opener(server))
        assert error.value.kind == "http" and error.value.code == 404

    def test_offline(self):
        # The real opener, with the network guard: no connection is possible.
        with pytest.raises(dl.DownloadError) as error:
            dl.open_url(catalogue.INDEX_URL)
        assert error.value.kind == "offline"


# ------------------------------------------------------------
# A fake server for downloads (replaces open_url)
# ------------------------------------------------------------

class FakeResponse:
    def __init__(self, status, body, headers=None, url="", fail_after=None):
        self.status = status
        self.headers = headers or {}
        self._body = io.BytesIO(body)
        self._url = url
        self._fail_after = fail_after
        self._sent = 0
        self.closed = False

    def read(self, n=-1):
        if self._fail_after is not None and self._sent >= self._fail_after:
            raise ConnectionResetError("connection lost")
        if self._fail_after is not None:
            n = min(n if n > 0 else self._fail_after, self._fail_after - self._sent)
        data = self._body.read(n)
        self._sent += len(data)
        return data

    def geturl(self):
        return self._url

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Server:
    """Serves FILES, honouring Range unless told not to."""

    def __init__(self, files=None, ranges=True, fail_after=None, status_for_range=None):
        self.files = dict(FILES if files is None else files)
        self.ranges = ranges
        self.fail_after = fail_after
        self.status_for_range = status_for_range
        self.requests = []

    def __call__(self, url, headers=None, timeout=None, opener=None):
        headers = headers or {}
        self.requests.append((url, dict(headers)))
        if url not in self.files:
            raise dl.DownloadError("http", "404", code=404)
        body = self.files[url]
        fail_after, self.fail_after = self.fail_after, None      # fails once
        rng = headers.get("Range")
        if rng and self.status_for_range:
            status, self.status_for_range = self.status_for_range, None
            raise dl.DownloadError("http", str(status), code=status)
        if rng and self.ranges:
            start = int(rng.split("=")[1].rstrip("-"))
            return FakeResponse(206, body[start:], {
                "Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}"}, url, fail_after)
        return FakeResponse(200, body, {}, url, fail_after)


# ------------------------------------------------------------
# Checksums
# ------------------------------------------------------------

class TestVerification:
    def test_the_pinned_runtime(self):
        assert dl.RUNTIME_URL == ("https://github.com/rhasspy/piper/releases/download/"
                                  "2023.11.14-2/piper_windows_amd64.zip")
        assert dl.RUNTIME_SIZE == 22477236
        assert dl.RUNTIME_SHA256 == \
            "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea"
        assert dl.host_allowed(dl.RUNTIME_URL) and dl.host_allowed(catalogue.INDEX_URL)

    def test_verify_file(self, tmp_path):
        path = tmp_path / "f"
        path.write_bytes(b"hello")
        good_md5, good_sha = md5(b"hello"), hashlib.sha256(b"hello").hexdigest()
        assert dl.verify_file(str(path), 5, md5=good_md5)
        assert dl.verify_file(str(path), 5, sha256=good_sha.upper())
        assert not dl.verify_file(str(path), 5, md5=md5(b"hellO"))
        assert not dl.verify_file(str(path), 5, sha256=hashlib.sha256(b"x").hexdigest())
        assert not dl.verify_file(str(path), 6, md5=good_md5)
        assert not dl.verify_file(str(tmp_path / "missing"), 5, md5=good_md5)

    def test_a_good_file_is_saved(self, tmp_path, monkeypatch):
        server = Server({"https://huggingface.co/f": b"x" * 200_000})
        monkeypatch.setattr(dl, "open_url", server)
        seen = []
        dest = str(tmp_path / "v" / "f.onnx")
        dl.download_file("https://huggingface.co/f", dest, 200_000, md5=md5(b"x" * 200_000),
                         progress=seen.append)
        assert open(dest, "rb").read() == b"x" * 200_000
        assert os.listdir(tmp_path / "v") == ["f.onnx"]
        assert seen[-1] == 200_000 and seen == sorted(seen)
        # Already there and correct: nothing is downloaded again.
        dl.download_file("https://huggingface.co/f", dest, 200_000, md5=md5(b"x" * 200_000))
        assert len(server.requests) == 1

    def test_a_bad_file_is_refused_and_deleted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({"https://huggingface.co/f": b"evil"}))
        dest = str(tmp_path / "f.onnx")
        with pytest.raises(dl.DownloadError) as error:
            dl.download_file("https://huggingface.co/f", dest, 4, md5=md5(b"good"))
        assert error.value.kind == "verify"
        assert os.listdir(tmp_path) == []

    def test_a_wrong_file_in_place_is_replaced(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({"https://huggingface.co/f": b"good"}))
        dest = tmp_path / "f.onnx"
        dest.write_bytes(b"bad!")
        dl.download_file("https://huggingface.co/f", str(dest), 4, md5=md5(b"good"))
        assert dest.read_bytes() == b"good"

    def test_a_checksum_is_required(self, tmp_path):
        with pytest.raises(ValueError):
            dl.download_file("https://huggingface.co/f", str(tmp_path / "f"), 4)

    def test_the_model_card_is_checked(self, monkeypatch):
        voice = voice_of("id_ID-news_tts-medium")
        server = Server()
        monkeypatch.setattr(dl, "open_url", server)
        assert dl.fetch_model_card(voice) == CARD_ID
        assert server.requests[0][0] == catalogue.FILES_URL + "id/id_ID/news_tts/medium/MODEL_CARD"
        card_url = server.requests[0][0]
        server.files[card_url] = CARD_ID.replace("See URL", "CC0 1.0").encode("utf-8")
        with pytest.raises(dl.DownloadError) as error:
            dl.fetch_model_card(voice)
        assert error.value.kind in ("verify", "size")

    def test_the_catalogue_fetch(self, monkeypatch):
        server = Server({catalogue.INDEX_URL: json.dumps(INDEX).encode("utf-8")})
        monkeypatch.setattr(dl, "open_url", server)
        assert dl.fetch_catalogue() == INDEX
        server.files[catalogue.INDEX_URL] = b"<html>"
        with pytest.raises(dl.DownloadError) as error:
            dl.fetch_catalogue()
        assert error.value.kind == "bad_data"


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


RUNTIME_ZIP = make_zip([("piper/piper.exe", b"MZ fake"), ("piper/espeak-ng.dll", b"dll"),
                        ("piper/espeak-ng-data/id_dict", b"dict"), ("piper/pkgconfig/", b"")])


class TestRuntime:
    def test_a_zip_with_another_hash_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({dl.RUNTIME_URL: RUNTIME_ZIP}))
        monkeypatch.setattr(dl, "RUNTIME_SIZE", len(RUNTIME_ZIP))   # the pinned hash stays
        root = str(tmp_path / "piper")
        with pytest.raises(dl.DownloadError) as error:
            dl.install_runtime(root)
        assert error.value.kind == "verify"
        assert not store.runtime_installed(root)
        assert os.listdir(store.downloads_dir(root)) == []          # nothing kept

    def test_a_zip_of_another_size_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({dl.RUNTIME_URL: RUNTIME_ZIP}))
        with pytest.raises(dl.DownloadError) as error:
            dl.install_runtime(str(tmp_path / "piper"))
        assert error.value.kind in ("verify", "offline")
        assert not store.runtime_installed(str(tmp_path / "piper"))

    def test_the_pinned_zip_is_unpacked(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({dl.RUNTIME_URL: RUNTIME_ZIP}))
        monkeypatch.setattr(dl, "RUNTIME_SIZE", len(RUNTIME_ZIP))
        monkeypatch.setattr(dl, "RUNTIME_SHA256", hashlib.sha256(RUNTIME_ZIP).hexdigest())
        root = str(tmp_path / "piper")
        seen = []
        exe = dl.install_runtime(root, progress=seen.append)
        assert exe == os.path.join(root, "runtime", "piper", "piper.exe")
        assert open(exe, "rb").read() == b"MZ fake" and store.runtime_installed(root)
        assert os.listdir(store.downloads_dir(root)) == []           # the zip is gone
        assert not os.path.exists(store.runtime_dir(root) + ".new")
        assert seen[-1] == len(RUNTIME_ZIP)
        marker = store.read_json(os.path.join(store.runtime_dir(root), store.RUNTIME_MARKER))
        assert marker["version"] == "2023.11.14-2"

    def test_a_zip_without_piper_exe_is_refused(self, tmp_path, monkeypatch):
        other = make_zip([("readme.txt", b"hi")])
        monkeypatch.setattr(dl, "open_url", Server({dl.RUNTIME_URL: other}))
        monkeypatch.setattr(dl, "RUNTIME_SIZE", len(other))
        monkeypatch.setattr(dl, "RUNTIME_SHA256", hashlib.sha256(other).hexdigest())
        with pytest.raises(dl.DownloadError) as error:
            dl.install_runtime(str(tmp_path / "piper"))
        assert error.value.kind == "extract"
        assert not os.path.exists(store.runtime_dir(str(tmp_path / "piper")))


# ------------------------------------------------------------
# Unpacking
# ------------------------------------------------------------

class TestExtraction:
    def test_normal(self, tmp_path):
        path = tmp_path / "a.zip"
        path.write_bytes(RUNTIME_ZIP)
        dl.safe_extract(str(path), str(tmp_path / "out"))
        assert (tmp_path / "out" / "piper" / "piper.exe").read_bytes() == b"MZ fake"
        assert (tmp_path / "out" / "piper" / "espeak-ng-data" / "id_dict").exists()

    @pytest.mark.parametrize("name", ["../evil.txt", "piper/../../evil.txt", "/evil.txt",
                                      "C:/evil.txt", "piper/x:stream", "..\\evil.txt"])
    def test_zip_slip_is_refused_before_writing(self, tmp_path, name):
        path = tmp_path / "a.zip"
        path.write_bytes(make_zip([("piper/piper.exe", b"MZ"), (name, b"evil")]))
        out = tmp_path / "deep" / "out"
        with pytest.raises(dl.DownloadError) as error:
            dl.safe_extract(str(path), str(out))
        assert error.value.kind == "extract"
        assert not out.exists()
        assert not (tmp_path / "evil.txt").exists()
        assert not (tmp_path / "deep" / "evil.txt").exists()

    def test_limits(self, tmp_path):
        path = tmp_path / "a.zip"
        path.write_bytes(make_zip([(f"f{i}", b"x") for i in range(5)]))
        with pytest.raises(dl.DownloadError):
            dl.safe_extract(str(path), str(tmp_path / "o1"), max_entries=4)
        with pytest.raises(dl.DownloadError):
            dl.safe_extract(str(path), str(tmp_path / "o2"), max_bytes=4)
        path.write_bytes(b"not a zip")
        with pytest.raises(dl.DownloadError) as error:
            dl.safe_extract(str(path), str(tmp_path / "o3"))
        assert error.value.kind == "extract"


# ------------------------------------------------------------
# Resuming and cleaning up
# ------------------------------------------------------------

BIG = bytes(range(256)) * 1000       # 256 000 bytes
BIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/big.onnx"


class TestPartialDownloads:
    def test_a_lost_connection_keeps_the_part_and_resumes(self, tmp_path, monkeypatch):
        server = Server({BIG_URL: BIG}, fail_after=100_000)
        monkeypatch.setattr(dl, "open_url", server)
        dest = str(tmp_path / "big.onnx")
        with pytest.raises(dl.DownloadError) as error:
            dl.download_file(BIG_URL, dest, len(BIG), md5=md5(BIG))
        assert error.value.kind == "offline"
        part = dest + ".part"
        assert os.path.getsize(part) == 100_000 and not os.path.exists(dest)
        dl.download_file(BIG_URL, dest, len(BIG), md5=md5(BIG))
        assert open(dest, "rb").read() == BIG and not os.path.exists(part)
        assert server.requests[1][1] == {"Range": "bytes=100000-"}

    def test_a_server_that_cant_resume_starts_over(self, tmp_path, monkeypatch):
        server = Server({BIG_URL: BIG}, ranges=False)
        monkeypatch.setattr(dl, "open_url", server)
        dest = str(tmp_path / "big.onnx")
        with open(dest + ".part", "wb") as f:
            f.write(b"garbage that must not stay")
        dl.download_file(BIG_URL, dest, len(BIG), md5=md5(BIG))
        assert open(dest, "rb").read() == BIG

    def test_range_not_satisfiable_starts_over(self, tmp_path, monkeypatch):
        server = Server({BIG_URL: BIG}, status_for_range=416)
        monkeypatch.setattr(dl, "open_url", server)
        dest = str(tmp_path / "big.onnx")
        with open(dest + ".part", "wb") as f:
            f.write(BIG[:10])
        dl.download_file(BIG_URL, dest, len(BIG), md5=md5(BIG))
        assert open(dest, "rb").read() == BIG
        assert server.requests[-1][1] == {}

    def test_a_complete_part_is_only_checked(self, tmp_path, monkeypatch):
        server = Server({BIG_URL: BIG})
        monkeypatch.setattr(dl, "open_url", server)
        dest = str(tmp_path / "big.onnx")
        with open(dest + ".part", "wb") as f:
            f.write(BIG)
        dl.download_file(BIG_URL, dest, len(BIG), md5=md5(BIG))
        assert server.requests == [] and open(dest, "rb").read() == BIG

    def test_a_corrupt_part_is_deleted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({BIG_URL: BIG}))
        dest = str(tmp_path / "big.onnx")
        with open(dest + ".part", "wb") as f:
            f.write(b"\x00" * 1000)           # resumed on top of wrong bytes
        with pytest.raises(dl.DownloadError) as error:
            dl.download_file(BIG_URL, dest, len(BIG), md5=md5(BIG))
        assert error.value.kind == "verify"
        assert os.listdir(tmp_path) == []

    def test_too_much_data_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({BIG_URL: BIG + b"extra"}))
        dest = str(tmp_path / "big.onnx")
        with pytest.raises(dl.DownloadError) as error:
            dl.download_file(BIG_URL, dest, len(BIG), md5=md5(BIG))
        assert error.value.kind == "size" and os.listdir(tmp_path) == []

    def test_cancel_removes_the_part(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server({BIG_URL: BIG}))
        dest = str(tmp_path / "big.onnx")
        seen = []
        with pytest.raises(dl.Cancelled):
            dl.download_file(BIG_URL, dest, len(BIG), md5=md5(BIG), progress=seen.append,
                             cancelled=lambda: len(seen) > 2)
        assert os.listdir(tmp_path) == []

    def test_cancelling_a_voice_removes_its_folder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server())
        voice = voice_of("id_ID-news_tts-medium")
        root = str(tmp_path / "piper")
        calls = []
        with pytest.raises(dl.Cancelled):
            dl.install_voice(voice, root, CARD_ID, progress=calls.append,
                             cancelled=lambda: len(calls) > 3)
        assert not os.path.exists(store.voice_dir(root, voice["key"]))

    def test_a_voice_is_installed_last_step_first(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "open_url", Server())
        voice = voice_of("id_ID-news_tts-medium")
        root = str(tmp_path / "piper")
        seen = []
        dl.install_voice(voice, root, CARD_ID, progress=seen.append)
        folder = store.voice_dir(root, voice["key"])
        assert sorted(os.listdir(folder)) == ["MODEL_CARD", "id_ID-news_tts-medium.onnx",
                                              "id_ID-news_tts-medium.onnx.json", "voice.json"]
        assert seen == sorted(seen) and seen[-1] == voice["size"]
        installed = store.installed_voices(root)
        assert [v["key"] for v in installed] == ["id_ID-news_tts-medium"]
        assert installed[0]["card"]["license"] == "See URL"
        assert installed[0]["card"]["license_clear"] is False
        assert installed[0]["quality"] == "medium" and installed[0]["language"] == "id-ID"

    def test_stale_parts_are_cleaned_up(self, tmp_path):
        root = str(tmp_path / "piper")
        old_dir = os.path.join(store.voices_dir(root), "en_US-lessac-medium")
        new_dir = os.path.join(store.voices_dir(root), "id_ID-news_tts-medium")
        os.makedirs(old_dir)
        os.makedirs(new_dir)
        os.makedirs(store.downloads_dir(root))
        old_part = os.path.join(old_dir, "en_US-lessac-medium.onnx.part")
        new_part = os.path.join(new_dir, "id_ID-news_tts-medium.onnx.part")
        zip_part = os.path.join(store.downloads_dir(root), "piper_windows_amd64.zip.part")
        for path in (old_part, new_part, zip_part):
            with open(path, "wb") as f:
                f.write(b"x")
        week_ago = time.time() - store.STALE_PART_SECONDS - 60
        os.utime(old_part, (week_ago, week_ago))
        os.utime(zip_part, (week_ago, week_ago))
        os.makedirs(store.runtime_dir(root) + ".new")
        removed = store.cleanup_partials(root)
        assert not os.path.exists(old_part) and not os.path.exists(old_dir)
        assert not os.path.exists(zip_part)
        assert os.path.exists(new_part)
        assert not os.path.exists(store.runtime_dir(root) + ".new")
        assert len(removed) == 4


# ------------------------------------------------------------
# Rate, command line, process
# ------------------------------------------------------------

class TestRate:
    @pytest.mark.parametrize("rate, scale", [(-10, 1.6), (-5, 1.3), (-1, 1.06), (0, 1.0),
                                             (1, 0.96), (5, 0.8), (10, 0.6), (-99, 1.6),
                                             (99, 0.6), ("x", 1.0), (None, 1.0)])
    def test_mapping(self, rate, scale):
        assert synth.length_scale(rate) == scale

    def test_faster_is_always_shorter(self):
        scales = [synth.length_scale(r) for r in range(-10, 11)]
        assert scales == sorted(scales, reverse=True) and len(set(scales)) == 21
        assert synth.length_scale_text(0) == "1.00" and synth.length_scale_text(-10) == "1.60"


def write_wav(path, frames=2205, rate=22050):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)


class _FakeStdin:
    """The kept piper.exe's standard input: each flushed line is one request."""

    def __init__(self, process):
        self.process = process
        self.buffer = b""
        self.closed = False

    def write(self, data):
        if self.closed:
            raise ValueError("write to closed file")
        self.buffer += data

    def flush(self):
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            self.process.request(line)

    def close(self):
        self.closed = True


class FakePopen:
    """Stands in for piper.exe: records how it was started, writes a WAV. With
    --json-input it is the kept piper.exe: every JSON line on its standard
    input writes that line's output_file and prints its path."""
    instances = []
    mode = "ok"          # "ok", "hang", "fail", "badwav"; "server_fail" fails only the kept one

    def __init__(self, args, **kwargs):
        self.args = list(args)
        self.kwargs = kwargs
        self.input = None
        self.returncode = None
        self.killed = threading.Event()
        self.started = threading.Event()
        self.server = "--json-input" in self.args
        FakePopen.instances.append(self)
        if self.server:
            import queue
            self.requests = []
            self.request_times = []
            self._out = queue.Queue()
            self.stdin = _FakeStdin(self)
            self.stdout = iter(self._out.get, None)
            failing = self.mode in ("fail", "server_fail")
            self.stderr = iter([b"[piper] [error] model file is broken\n"] if failing else [])
            if failing:
                self.returncode = 1
                self._out.put(None)

    def poll(self):
        return self.returncode

    def request(self, line):
        data = json.loads(line.decode("utf-8"))
        self.requests.append(data["text"])
        self.request_times.append(time.monotonic())
        self.started.set()
        if self.returncode is not None or self.mode == "hang":
            return
        if self.mode == "badwav":
            with open(data["output_file"], "wb") as f:
                f.write(b"not a wav")
        else:
            write_wav(data["output_file"])
        self._out.put((data["output_file"] + "\r\n").encode("utf-8"))

    def communicate(self, input=None, timeout=None):
        if input is not None:
            self.input = input
        self.started.set()
        output = self.args[self.args.index("--output_file") + 1]
        if self.mode == "hang":
            if not self.killed.wait(timeout or 5):
                raise __import__("subprocess").TimeoutExpired(self.args, timeout)
            self.returncode = 1
            return b"", b"[piper] [info] Terminated"
        if self.mode == "fail":
            self.returncode = 1
            return b"", b"[piper] [info] Loaded voice\n[piper] [error] model file is broken\n"
        if self.mode == "badwav":
            with open(output, "wb") as f:
                f.write(b"not a wav")
        else:
            write_wav(output)
        self.returncode = 0
        return (output + "\r\n").encode("utf-8"), b"[piper] [info] Real-time factor: 0.19"

    def kill(self):
        self.killed.set()
        if self.server and self.returncode is None:
            self.returncode = 1
            self._out.put(None)


@pytest.fixture
def fake_popen(monkeypatch):
    FakePopen.instances = []
    FakePopen.mode = "ok"
    monkeypatch.setattr(synth.subprocess, "Popen", FakePopen)
    yield FakePopen
    FakePopen.mode = "ok"


class TestCommandLine:
    def test_build_command(self):
        assert synth.build_command("C:\\p\\piper.exe", "C:\\v\\id.onnx", "C:\\c\\out.tmp", 5) == [
            "C:\\p\\piper.exe", "--model", "C:\\v\\id.onnx", "--output_file", "C:\\c\\out.tmp",
            "--length_scale", "0.80"]

    def test_no_window_and_utf8_on_stdin(self, tmp_path, fake_popen):
        exe = str(tmp_path / "runtime" / "piper" / "piper.exe")
        out = str(tmp_path / "out.tmp")
        synth.synthesize(exe, "model.onnx", out, "Halo, ini suara Piper.\nSelamat pagi — café\x07",
                         rate=-10)
        process = fake_popen.instances[0]
        assert process.args == [exe, "--model", "model.onnx", "--output_file", out,
                                "--length_scale", "1.60"]
        assert process.kwargs["creationflags"] & 0x08000000        # CREATE_NO_WINDOW
        assert process.kwargs["creationflags"] == synth.CREATE_NO_WINDOW
        info = process.kwargs["startupinfo"]
        assert info.wShowWindow == 0 and info.dwFlags & 1           # SW_HIDE
        assert process.kwargs["cwd"] == os.path.dirname(exe)
        assert process.kwargs["stdin"] == synth.subprocess.PIPE
        assert process.kwargs["stdout"] == synth.subprocess.PIPE
        assert process.kwargs["stderr"] == synth.subprocess.PIPE
        assert "shell" not in process.kwargs
        # One line of text, UTF-8.
        assert process.input == "Halo, ini suara Piper. Selamat pagi — café\n".encode("utf-8")
        assert synth.wav_duration(out) == pytest.approx(0.1)

    def test_failures(self, tmp_path, fake_popen):
        out = str(tmp_path / "out.tmp")
        fake_popen.mode = "fail"
        with pytest.raises(synth.PiperError) as error:
            synth.synthesize("piper.exe", "m.onnx", out, "Halo")
        assert "model file is broken" in str(error.value)
        fake_popen.mode = "badwav"
        with pytest.raises(synth.PiperError):
            synth.synthesize("piper.exe", "m.onnx", out, "Halo")
        with pytest.raises(synth.PiperError):
            synth.synthesize("piper.exe", "m.onnx", out, "  \n ")      # nothing to say

    def test_timeout_kills_it(self, tmp_path, fake_popen):
        fake_popen.mode = "hang"
        with pytest.raises(synth.PiperError) as error:
            synth.synthesize("piper.exe", "m.onnx", str(tmp_path / "o"), "Halo", timeout=0.05)
        assert "too long" in str(error.value)
        assert fake_popen.instances[0].killed.is_set()

    def test_timeouts(self):
        assert synth.timeout_for("x") == synth.MIN_TIMEOUT_SECONDS
        assert synth.timeout_for("x" * 100_000) == synth.MAX_TIMEOUT_SECONDS


# ------------------------------------------------------------
# The WAV cache
# ------------------------------------------------------------

class TestSentences:
    @pytest.mark.parametrize("text, expected", [
        ("Selamat pagi, Rafli. Hari ini hari Kamis, 24 September 2026. Cuaca 31,5 derajat!",
         ["Selamat pagi, Rafli.", "Hari ini hari Kamis, 24 September 2026.",
          "Cuaca 31,5 derajat!"]),
        ("Hariku 2.8 sudah keluar.\nPengingat: minum obat.",
         ["Hariku 2.8 sudah keluar.", "Pengingat: minum obat."]),
        ('Dia bilang "halo." Lalu pergi\u2026  Selesai?',
         ['Dia bilang "halo."', "Lalu pergi\u2026", "Selesai?"]),
        ("Ya. Oke. Tentu saja.", ["Ya. Oke.", "Tentu saja."]),   # tiny pieces join the next
        ("Ya. Oke. Siap.", ["Ya. Oke. Siap."]),                 # a tiny last one, the previous
        ("Oke. Hi.", ["Oke. Hi."]),
        ("Hi.", ["Hi."]),
        ("", []),
        ("  \n \x07 ", []),
    ])
    def test_split(self, text, expected):
        assert synth.split_sentences(text) == expected

    def test_a_long_sentence_splits_at_a_comma_then_a_space(self):
        clause = "satu dua tiga empat lima enam tujuh delapan sembilan sepuluh"
        text = ", ".join([clause] * 6) + "."
        pieces = synth.split_sentences(text, limit=150)
        assert all(len(p) <= 150 for p in pieces) and len(pieces) > 1
        assert all(p.endswith(",") for p in pieces[:-1])
        assert " ".join(pieces) == text
        words = synth.split_sentences("kata " * 100, limit=60)
        assert all(len(p) <= 60 for p in words) and " ".join(words) == ("kata " * 100).strip()


class TestKeptProcess:
    def test_command_and_requests(self, tmp_path, fake_popen):
        engine = synth.PiperProcess("C:\\piper\\piper.exe", "voice.onnx", -5, str(tmp_path))
        process = fake_popen.instances[0]
        assert process.args == ["C:\\piper\\piper.exe", "--model", "voice.onnx", "--json-input",
                                "--output_dir", str(tmp_path), "--length_scale", "1.30"]
        assert process.kwargs["creationflags"] == synth.CREATE_NO_WINDOW
        assert process.kwargs["cwd"] == "C:\\piper"
        assert engine.key == ("C:\\piper\\piper.exe", "voice.onnx", "1.30") and engine.alive()
        first, second = str(tmp_path / "a.wav"), str(tmp_path / "b.wav")
        assert engine.synthesize("Halo,\nini\x07 café — satu.", first) == first
        assert engine.synthesize("Dua.", second) == second
        assert process.requests == ["Halo, ini café — satu.", "Dua."]
        assert synth.wav_duration(first) > 0 and synth.wav_duration(second) > 0
        engine.close()
        assert process.killed.is_set() and process.stdin.closed and not engine.alive()

    def test_the_request_is_one_ascii_json_line(self, tmp_path, fake_popen):
        engine = synth.PiperProcess("piper.exe", "voice.onnx", 0, str(tmp_path))
        sent = []
        process = fake_popen.instances[0]
        original = process.request
        process.request = lambda line: sent.append(line) or original(line)
        engine.synthesize("Selamat pagi — café", str(tmp_path / "c.wav"))
        assert sent == [json.dumps({"text": "Selamat pagi — café",
                                    "output_file": str(tmp_path / "c.wav")}).encode("ascii")]

    def test_a_piper_that_stops_is_an_error(self, tmp_path, fake_popen):
        fake_popen.mode = "fail"
        engine = synth.PiperProcess("piper.exe", "voice.onnx", 0, str(tmp_path))
        with pytest.raises(synth.PiperError):
            engine.synthesize("Halo", str(tmp_path / "d.wav"))
        assert not engine.alive()

    def test_a_bad_wav_is_an_error(self, tmp_path, fake_popen):
        fake_popen.mode = "badwav"
        engine = synth.PiperProcess("piper.exe", "voice.onnx", 0, str(tmp_path))
        with pytest.raises(synth.PiperError):
            engine.synthesize("Halo", str(tmp_path / "e.wav"))

    def test_too_long_kills_it(self, tmp_path, fake_popen):
        fake_popen.mode = "hang"
        engine = synth.PiperProcess("piper.exe", "voice.onnx", 0, str(tmp_path))
        with pytest.raises(synth.PiperError, match="too long"):
            engine.synthesize("Halo", str(tmp_path / "f.wav"), timeout=0.2)
        assert fake_popen.instances[0].killed.is_set()

    def test_cancelled_gets_a_short_grace_then_kills_it(self, tmp_path, fake_popen, monkeypatch):
        monkeypatch.setattr(synth, "CANCEL_GRACE_SECONDS", 0.2)
        fake_popen.mode = "hang"
        engine = synth.PiperProcess("piper.exe", "voice.onnx", 0, str(tmp_path))
        started = time.monotonic()
        with pytest.raises(synth.PiperError, match="stopped"):
            engine.synthesize("Halo", str(tmp_path / "g.wav"), cancelled=lambda: True)
        assert time.monotonic() - started < 2.0
        assert fake_popen.instances[0].killed.is_set()

    def test_nothing_to_say(self, tmp_path, fake_popen):
        engine = synth.PiperProcess("piper.exe", "voice.onnx", 0, str(tmp_path))
        with pytest.raises(synth.PiperError):
            engine.synthesize(" \x07 ", str(tmp_path / "h.wav"))
        assert fake_popen.instances[0].requests == []


class TestCache:
    def test_keys(self):
        key = synth.AudioCache.key("id_ID-news_tts-medium", "1.00", "Selamat pagi")
        assert key == synth.AudioCache.key("id_ID-news_tts-medium", "1.00", "Selamat  pagi\n")
        others = {synth.AudioCache.key("en_US-lessac-medium", "1.00", "Selamat pagi"),
                  synth.AudioCache.key("id_ID-news_tts-medium", "0.80", "Selamat pagi"),
                  synth.AudioCache.key("id_ID-news_tts-medium", "1.00", "Selamat siang")}
        assert key not in others and len(others) == 3 and len(key) == 64

    def test_miss_then_hit(self, tmp_path):
        cache = synth.AudioCache(str(tmp_path / "piper"))
        key = cache.key("v", "1.00", "hello")
        assert cache.get(key) is None
        temporary = cache.temporary_path(key)
        write_wav(temporary)
        path = cache.put_file(key, temporary)
        assert cache.get(key) == path and path.endswith(".wav")
        assert not os.path.exists(temporary)

    def test_a_bad_wav_is_not_kept(self, tmp_path):
        cache = synth.AudioCache(str(tmp_path))
        temporary = cache.temporary_path("k" * 64)
        with open(temporary, "wb") as f:
            f.write(b"RIFF....WAVEjunk")
        with pytest.raises(synth.PiperError):
            cache.put_file("k" * 64, temporary)
        assert os.listdir(tmp_path) == []

    def test_least_recently_used_goes_first(self, tmp_path):
        cache = synth.AudioCache(str(tmp_path), limit_bytes=10_000)

        def put(name):
            temporary = cache.temporary_path(name * 64)
            write_wav(temporary, frames=2000)                  # about 4 KB each
            return cache.put_file(name * 64, temporary)

        a, b = put("a"), put("b")
        os.utime(a, (100, 100))
        os.utime(b, (200, 200))
        assert cache.get("a" * 64) == a                          # using it makes it recent
        c = put("c")
        assert os.path.exists(a) and os.path.exists(c) and not os.path.exists(b)
        assert cache.size() <= 10_000

    def test_stale_temporaries_go_fresh_ones_stay(self, tmp_path):
        cache = synth.AudioCache(str(tmp_path))
        old, fresh = cache.temporary_path("o" * 64), cache.temporary_path("f" * 64)
        for path in (old, fresh):
            with open(path, "wb") as f:
                f.write(b"half a wav")
        hours_ago = time.time() - synth.STALE_TEMPORARY_SECONDS - 60
        os.utime(old, (hours_ago, hours_ago))
        temporary = cache.temporary_path("n" * 64)
        write_wav(temporary)
        cache.put_file("n" * 64, temporary)
        assert not os.path.exists(old) and os.path.exists(fresh)

    def test_the_new_file_stays_even_alone_over_the_limit(self, tmp_path):
        cache = synth.AudioCache(str(tmp_path), limit_bytes=100)
        temporary = cache.temporary_path("d" * 64)
        write_wav(temporary, frames=2000)
        assert os.path.exists(cache.put_file("d" * 64, temporary))


# ------------------------------------------------------------
# The extension: provider, stopping, downloads, catalogue
# ------------------------------------------------------------

def install_fake_runtime(root):
    exe = store.exe_path(root)
    os.makedirs(os.path.dirname(exe), exist_ok=True)
    with open(exe, "wb") as f:
        f.write(b"MZ")
    store.write_runtime_marker(root, {"version": dl.RUNTIME_VERSION})


def install_fake_voice(root, key="id_ID-news_tts-medium"):
    voice = voice_of(key)
    folder = store.voice_dir(root, key)
    os.makedirs(folder, exist_ok=True)
    for role in ("model", "config"):
        with open(os.path.join(folder, voice["files"][role]["path"].rsplit("/", 1)[-1]),
                  "wb") as f:
            f.write(b"x")
    store.write_voice_marker(root, voice, catalogue.parse_model_card(CARD_ID))
    return voice


@pytest.fixture
def piper(tmp_data_dir, tmp_path, monkeypatch, fake_popen):
    import core.api
    import core.i18n
    import core.voice
    monkeypatch.setattr(core.api, "USER_DATA_DIR", str(tmp_path / "userdata"))
    monkeypatch.setattr(core.i18n, "_current_language", "en")
    spec = importlib.util.spec_from_file_location("piper_voices_main_under_test",
                                                  os.path.join(PIPER_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    played, stopped, spoken = [], [], []
    module.hold_playback = False
    module.pending_playback = []

    def play_file(path, volume, on_done):
        played.append((path, volume))
        if module.hold_playback:
            module.pending_playback.append(on_done)
        else:
            on_done(None)

    def stop_playback():
        stopped.append(True)
        pending, module.pending_playback[:] = list(module.pending_playback), []
        for on_done in pending:
            on_done(None)

    monkeypatch.setattr(core.voice, "play_file", play_file)
    monkeypatch.setattr(core.voice, "stop_playback", stop_playback)
    monkeypatch.setattr(module, "_speak_text", lambda message, interrupt=False:
                        spoken.append(message))
    monkeypatch.setattr(core.voice, "user_languages", lambda: ["en"])
    module.played, module.stopped, module.spoken = played, stopped, spoken
    module.root = store.root_dir()
    saved = dict(core.voice._providers)
    yield module
    module.stop()
    module._downloads.cancel()
    with core.voice._providers_lock:
        core.voice._providers.clear()
        core.voice._providers.update(saved)


def speak(piper, text_="Selamat pagi", voice="id_ID-news_tts-medium", rate=0, volume=100):
    done = []
    piper.speak(text_, voice, rate, volume, done.append)
    assert wait_until(lambda: done), "on_done was not called"
    time.sleep(0.02)
    assert len(done) == 1, done
    return done[0]


class TestProvider:
    def test_register_and_teardown(self, piper, fresh_event_bus, monkeypatch):
        import core.preferences
        import core.voice
        monkeypatch.setattr(core.preferences, "_panels", {})
        piper.register(fresh_event_bus)
        assert [p["name"] for p in core.preferences._panels["Piper Voices"]] == [""]
        provider = [p for p in core.voice.get_providers() if p["id"] == "piper"][0]
        assert provider["name"] == "Piper neural voices (offline)"
        assert provider["privacy_note"] == (
            "Piper voices run entirely on this computer. Hariku only connects to download the "
            "Piper program and the voices you choose, from GitHub and Hugging Face.")
        assert not core.voice.is_provider_available("piper")
        piper.teardown()
        assert "piper" not in [p["id"] for p in core.voice.get_providers()]

    def test_is_available_states(self, piper):
        assert piper.refresh_state() == [] and not piper.is_available()
        install_fake_runtime(piper.root)
        piper.refresh_state()
        assert not piper.is_available()                  # no voice yet
        install_fake_voice(piper.root)
        assert [v["key"] for v in piper.refresh_state()] == ["id_ID-news_tts-medium"]
        assert piper.is_available()
        piper.controller.remove_voice("id_ID-news_tts-medium")
        assert not piper.is_available()

    def test_a_voice_without_the_program_is_not_available(self, piper):
        install_fake_voice(piper.root)
        piper.refresh_state()
        assert not piper.is_available()
        assert isinstance(speak(piper), FileNotFoundError)

    def test_list_voices_is_the_installed_ones(self, piper):
        install_fake_runtime(piper.root)
        assert piper.list_voices() == []
        install_fake_voice(piper.root)
        install_fake_voice(piper.root, "en_US-lessac-high")
        voices = piper.list_voices()
        assert voices == [
            {"id": "en_US-lessac-high", "name": "Lessac (High)", "language": "en-US",
             "quality": "high"},
            {"id": "id_ID-news_tts-medium", "name": "News tts (Medium)", "language": "id-ID",
             "quality": "medium"}]

    def test_miss_synthesizes_caches_and_plays(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        piper.refresh_state()
        assert speak(piper, "Halo, ini suara Piper.", rate=5, volume=70) is None
        process = fake_popen.instances[0]
        assert process.args[0] == store.exe_path(piper.root)
        assert process.args[1:4] == ["--model", store.model_path(piper.root,
                                                                  "id_ID-news_tts-medium"),
                                     "--json-input"]
        assert process.args[-2:] == ["--length_scale", "0.80"]
        assert process.kwargs["creationflags"] == synth.CREATE_NO_WINDOW
        assert process.requests == ["Halo, ini suara Piper."]
        path, volume = piper.played[0]
        assert volume == 70 and path.endswith(".wav")
        assert os.path.dirname(path).endswith(os.path.join("voice_cache", "piper"))
        assert synth.wav_duration(path) > 0
        assert [n for n in os.listdir(os.path.dirname(path)) if n.endswith(".tmp")] == []

    def test_hit_plays_without_piper(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        speak(piper, "Selamat pagi, Bro.")
        assert speak(piper, "Selamat pagi, Bro.", volume=40) is None
        assert len(fake_popen.instances) == 1
        assert piper.played[0][0] == piper.played[1][0] and piper.played[1][1] == 40
        speak(piper, "Selamat pagi, Bro.", rate=3)          # another speed: another file
        assert len(fake_popen.instances) == 2

    def test_the_default_voice_follows_the_language(self, piper, fake_popen, monkeypatch):
        import core.voice
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        install_fake_voice(piper.root, "en_US-lessac-medium")
        monkeypatch.setattr(core.voice, "user_languages", lambda: ["id", "en"])
        speak(piper, "Halo", voice="")
        monkeypatch.setattr(core.voice, "user_languages", lambda: ["en"])
        speak(piper, "Hello", voice="")
        models = [p.args[2] for p in fake_popen.instances]
        assert models[0].endswith("id_ID-news_tts-medium.onnx")
        assert models[1].endswith("en_US-lessac-medium.onnx")

    def test_a_missing_voice_falls_back(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        error = speak(piper, voice="en_US-lessac-high")
        assert isinstance(error, LookupError) and "en_US-lessac-high" in str(error)
        assert fake_popen.instances == [] and piper.played == []

    def test_a_piper_failure_is_reported(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        fake_popen.mode = "fail"
        error = speak(piper)
        assert isinstance(error, synth.PiperError) and piper.played == []
        cache_dir = os.path.join(piper.root, "..", "voice_cache", "piper")
        assert [n for n in os.listdir(cache_dir) if not n.endswith(".wav")] == []

    def test_stop_answers_at_once_and_a_stuck_piper_is_killed(self, piper, fake_popen,
                                                                monkeypatch):
        monkeypatch.setattr(synth, "CANCEL_GRACE_SECONDS", 0.3)
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        fake_popen.mode = "hang"
        done = []
        piper.speak("A long briefing", "id_ID-news_tts-medium", 0, 100, done.append)
        assert wait_until(lambda: fake_popen.instances and fake_popen.instances[0].started.is_set())
        piper.speak("Queued", "id_ID-news_tts-medium", 0, 100, done.append)
        piper.stop()
        assert wait_until(lambda: len(done) == 2, timeout=0.2)     # without waiting for Piper
        assert done == [None, None]
        assert wait_until(lambda: fake_popen.instances[0].killed.is_set())
        time.sleep(0.1)
        assert len(fake_popen.instances) == 1 and piper.played == []

    def test_a_long_text_plays_sentence_by_sentence(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        piper.hold_playback = True
        done = []
        piper.speak("Selamat pagi, Rafli. Hari ini hari Kamis.\nKamu punya tiga pengingat.",
                    "id_ID-news_tts-medium", 0, 90, done.append)
        assert wait_until(lambda: len(piper.pending_playback) == 1)
        engine = fake_popen.instances[0]
        # The first sentence plays while Piper makes the second, which waits its turn.
        assert wait_until(lambda: len(engine.requests) == 2)
        time.sleep(0.05)
        assert len(piper.played) == 1 and not done
        piper.pending_playback.pop(0)(None)
        assert wait_until(lambda: len(piper.pending_playback) == 1 and len(piper.played) == 2)
        piper.pending_playback.pop(0)(None)
        assert wait_until(lambda: len(piper.pending_playback) == 1 and len(piper.played) == 3)
        assert not done
        piper.pending_playback.pop(0)(None)
        assert wait_until(lambda: done) and done == [None]
        assert engine.requests == ["Selamat pagi, Rafli.", "Hari ini hari Kamis.",
                                   "Kamu punya tiga pengingat."]
        assert [volume for _path, volume in piper.played] == [90, 90, 90]
        assert len({path for path, _volume in piper.played}) == 3
        assert len(fake_popen.instances) == 1

    def test_the_voice_stays_loaded_between_texts(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        speak(piper, "Jam delapan.")
        speak(piper, "Cuaca cerah.")
        assert len(fake_popen.instances) == 1
        assert fake_popen.instances[0].requests == ["Jam delapan.", "Cuaca cerah."]
        assert not fake_popen.instances[0].killed.is_set()

    def test_a_failing_kept_piper_falls_back_to_a_new_one(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        fake_popen.mode = "server_fail"
        assert speak(piper, "Halo.") is None
        assert [p.server for p in fake_popen.instances] == [True, False]
        assert fake_popen.instances[1].input == "Halo.\n".encode("utf-8")
        assert len(piper.played) == 1

    def test_a_first_file_that_cant_play_is_an_error(self, piper, fake_popen, monkeypatch):
        import core.voice
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        monkeypatch.setattr(core.voice, "play_file",
                            lambda path, volume, on_done: on_done(RuntimeError("no sound device")))
        error = speak(piper, "Satu. Dua.")
        assert isinstance(error, RuntimeError)

    def test_removing_a_voice_and_teardown_close_the_kept_piper(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        speak(piper, "Halo.")
        piper.controller.remove_voice("id_ID-news_tts-medium")
        assert fake_popen.instances[0].killed.is_set()
        install_fake_voice(piper.root)
        speak(piper, "Halo lagi.")
        piper.teardown()
        assert fake_popen.instances[1].killed.is_set()

    def test_a_quiet_while_closes_the_kept_piper(self, piper, fake_popen, monkeypatch):
        monkeypatch.setattr(piper, "IDLE_EXIT_SECONDS", 0.1)
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        speak(piper, "Halo.")
        assert wait_until(lambda: fake_popen.instances[0].killed.is_set())

    def test_stop_during_playback(self, piper, fake_popen):
        install_fake_runtime(piper.root)
        install_fake_voice(piper.root)
        piper.hold_playback = True
        done = []
        piper.speak("Halo", "id_ID-news_tts-medium", 0, 100, done.append)
        assert wait_until(lambda: piper.pending_playback)
        player_on_done = piper.pending_playback[0]
        piper.stop()
        assert wait_until(lambda: done) and piper.stopped == [True]
        player_on_done(None)             # the player reporting late changes nothing
        player_on_done(RuntimeError("late"))
        assert done == [None]

    def test_stop_with_nothing_running(self, piper):
        piper.stop()
        assert piper.stopped == []


class TestDownloads:
    def fake_installers(self, piper, monkeypatch, block=None):
        calls = []

        def install_runtime(root, progress=None, cancelled=None):
            calls.append("runtime")
            for done in range(0, dl.RUNTIME_SIZE + 1, dl.RUNTIME_SIZE // 4):
                progress(done)
            install_fake_runtime(root)

        def install_voice(voice, root, card_text=None, progress=None, cancelled=None):
            calls.append(voice["key"])
            for step in range(1, 11):
                if block is not None:
                    block.wait(0.01)
                if cancelled():
                    raise dl.Cancelled()
                progress(voice["size"] * step // 10)
            install_fake_voice(root, voice["key"])

        monkeypatch.setattr(dl, "install_runtime", install_runtime)
        monkeypatch.setattr(dl, "install_voice", install_voice)
        return calls

    def test_the_first_download_brings_the_program(self, piper, monkeypatch):
        calls = self.fake_installers(piper, monkeypatch)
        events = []
        piper._downloads.add_listener(lambda event, job, value: events.append((event, value)))
        voice = voice_of("id_ID-news_tts-medium")
        assert piper._downloads.start(voice, CARD_ID)
        assert wait_until(lambda: events and events[-1][0] == "finished")
        assert calls == ["runtime", "id_ID-news_tts-medium"]
        assert events[-1] == ("finished", None)
        progress = [value for event, value in events if event == "progress"]
        assert progress == sorted(progress) and progress[-1] == 100
        assert [m for m in piper.spoken if m.endswith("percent")] == \
            ["25 percent", "50 percent", "75 percent", "100 percent"]
        assert piper.spoken[0].startswith("Downloading News tts, ")
        assert piper.spoken[-1] == "News tts is ready. Choose it in Preferences, Hariku Voice."
        assert piper.is_available() and piper._downloads.current() is None

    def test_the_program_comes_only_once(self, piper, monkeypatch):
        calls = self.fake_installers(piper, monkeypatch)
        install_fake_runtime(piper.root)
        done = []
        piper._downloads.add_listener(lambda event, job, value: done.append(job)
                                      if event == "finished" else None)
        voice = voice_of("en_US-lessac-medium")
        assert piper._downloads.start(voice, CARD_EN)
        assert wait_until(lambda: done)
        assert calls == ["en_US-lessac-medium"]
        assert done[0].total == voice["size"] and not done[0].need_runtime

    def test_one_download_at_a_time_and_cancel(self, piper, monkeypatch):
        block = threading.Event()
        self.fake_installers(piper, monkeypatch, block=block)
        install_fake_runtime(piper.root)
        events = []
        piper._downloads.add_listener(lambda event, job, value: events.append((event, value)))
        assert piper._downloads.start(voice_of("en_US-lessac-high"), CARD_EN)
        assert not piper._downloads.start(voice_of("en_US-lessac-medium"), CARD_EN)
        assert piper._downloads.cancel()
        assert wait_until(lambda: events and events[-1][0] == "finished")
        assert isinstance(events[-1][1], dl.Cancelled)
        assert piper.spoken[-1] == "Download cancelled."
        assert not store.is_installed(piper.root, "en_US-lessac-high")
        assert not piper._downloads.cancel()                  # nothing left to cancel

    def test_a_failure_is_said(self, piper, monkeypatch):
        def install_runtime(root, progress=None, cancelled=None):
            raise dl.DownloadError("verify", "piper_windows_amd64.zip")

        monkeypatch.setattr(dl, "install_runtime", install_runtime)
        events = []
        piper._downloads.add_listener(lambda event, job, value: events.append((event, value)))
        piper._downloads.start(voice_of("id_ID-news_tts-medium"), CARD_ID)
        assert wait_until(lambda: events and events[-1][0] == "finished")
        assert piper.spoken[-1].startswith("The download failed. A downloaded file didn't "
                                           "match its checksum")
        assert not piper.is_available()


class TestCatalogueLoading:
    def load(self, piper, force=False):
        results = []
        piper.controller.load_catalogue(force, lambda result, error: results.append(
            (result, error)))
        assert wait_until(lambda: results)
        return results[0]

    def test_fetched_once_a_week(self, piper, monkeypatch):
        fetched = []
        monkeypatch.setattr(dl, "fetch_catalogue", lambda: fetched.append(1) or INDEX)
        (voices, stale), error = self.load(piper)
        assert error is None and stale is None and len(voices) == len(INDEX)
        assert self.load(piper)[0][0] == voices and fetched == [1]        # from disk
        self.load(piper, force=True)
        assert fetched == [1, 1]
        saved = store.read_json(os.path.join(piper.root, store.CATALOGUE_FILE))
        saved["saved_at"] -= piper.CATALOGUE_MAX_AGE + 60
        store.write_json(os.path.join(piper.root, store.CATALOGUE_FILE), saved)
        self.load(piper)
        assert fetched == [1, 1, 1]

    def test_offline_uses_an_old_list(self, piper, monkeypatch):
        store.save_catalogue(piper.root, INDEX, now=time.time() - piper.CATALOGUE_MAX_AGE - 60)

        def offline():
            raise dl.DownloadError("offline", "no route")

        monkeypatch.setattr(dl, "fetch_catalogue", offline)
        (voices, stale), error = self.load(piper)
        assert error is None and isinstance(stale, dl.DownloadError) and len(voices) == len(INDEX)

    def test_offline_without_a_list(self, piper, monkeypatch):
        def offline():
            raise dl.DownloadError("offline", "no route")

        monkeypatch.setattr(dl, "fetch_catalogue", offline)
        result, error = self.load(piper)
        assert result is None and error.kind == "offline"

    def test_a_broken_index_is_not_saved(self, piper, monkeypatch):
        monkeypatch.setattr(dl, "fetch_catalogue", lambda: {"x": 1})
        result, error = self.load(piper)
        assert isinstance(error, catalogue.CatalogueError)
        assert store.load_catalogue(piper.root) is None

    def test_model_cards_are_fetched_once(self, piper, monkeypatch):
        fetched = []
        monkeypatch.setattr(dl, "fetch_model_card", lambda voice: fetched.append(1) or CARD_ID)
        results = []
        voice = voice_of("id_ID-news_tts-medium")
        for count in (1, 2):
            piper.controller.fetch_card(voice, lambda card, error: results.append((card, error)))
            assert wait_until(lambda: len(results) == count)
        assert results == [(CARD_ID, None), (CARD_ID, None)] and fetched == [1]


# ------------------------------------------------------------
# Manifest, translations, official status, imports
# ------------------------------------------------------------

class TestPackage:
    def test_manifest(self):
        with open(os.path.join(PIPER_DIR, "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["id"] == "piper_voices" and manifest["name"] == "Piper Voices"
        assert manifest["version"] == "1.1" and manifest["minimum_core_version"] == "2.7"
        assert manifest["main"] == "main.py"

    def test_translations(self):
        with open(os.path.join(PIPER_DIR, "locales", "en.json"), encoding="utf-8") as f:
            en = json.load(f)["messages"]
        with open(os.path.join(PIPER_DIR, "locales", "id.json"), encoding="utf-8") as f:
            id_ = json.load(f)["messages"]
        assert set(en) == set(id_)
        assert en["provider_name"] == "Piper neural voices (offline)"
        assert en["privacy_note"] == (
            "Piper voices run entirely on this computer. Hariku only connects to download the "
            "Piper program and the voices you choose, from GitHub and Hugging Face.")
        for key in en:        # the same placeholders in both languages
            assert sorted(__import__("re").findall(r"{\w+}", en[key])) == \
                sorted(__import__("re").findall(r"{\w+}", id_[key])), key
        assert " Anda" not in " ".join(id_.values())            # casual "kamu"

    def test_official_everywhere(self):
        for path in (os.path.join(ROOT, "core", "extension_manager.py"),
                     os.path.join(ROOT, "tools", "server", "generate_trusted_hashes.py")):
            with open(path, encoding="utf-8") as f:
                assert '"piper_voices"' in f.read(), path

    def test_gpl_headers(self):
        with open(os.path.join(ROOT, "extensions", "weather", "main.py"), encoding="utf-8") as f:
            header = "".join(f.readlines()[:8])
        for name in os.listdir(PIPER_DIR):
            if name.endswith(".py"):
                with open(os.path.join(PIPER_DIR, name), encoding="utf-8") as f:
                    assert f.read().startswith(header), name

    def test_stdlib_only(self):
        import ast
        local = {n[:-3] for n in os.listdir(PIPER_DIR) if n.endswith(".py")}
        for name in os.listdir(PIPER_DIR):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(PIPER_DIR, name), encoding="utf-8") as f:
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
                    assert top in sys.stdlib_module_names or top in ("core", "wx") or \
                        mod in local, f"{name} imports {mod}"


def test_no_network_was_used(no_network):
    assert no_network == []
