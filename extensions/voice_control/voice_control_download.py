# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Downloading whisper.cpp and its speech models (blocking; no wx). main.py runs
these on a worker thread, only after the user pressed Download in
Preferences, Voice Control.

Every request goes to an allowed host over HTTPS: GitHub and its release
download host, Hugging Face (huggingface.co, hf.co) and its CDN. Each redirect
is checked before it is followed, so a redirect elsewhere is refused. Files
are written as "<name>.part", continued with a Range request when an earlier
attempt was cut off, checked against the SHA-256 pinned below and only then
renamed into place. A file that doesn't match is deleted, never used.
"""
import hashlib
import http.client
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import core.constants

import voice_control_store as store

# whisper.cpp (MIT), the official Windows x64 build of release b5130. It
# contains Release\whisper-server.exe, which keeps a model loaded and answers
# on 127.0.0.1.
RUNTIME_VERSION = "b5130"
RUNTIME_FILE = "whisper-bin-x64.zip"
RUNTIME_URL = (f"https://github.com/ggml-org/whisper.cpp/releases/download/{RUNTIME_VERSION}/"
               f"{RUNTIME_FILE}")
RUNTIME_SIZE = 8573270
RUNTIME_SHA256 = "f9ec6c52a2e949b62ab51fa21d0d497958f9e41c3010c157c4e42932d5316f3c"
RUNTIME_MAX_UNPACKED = 256 * 1024 * 1024
RUNTIME_MAX_ENTRIES = 1000

# OpenAI's Whisper models (MIT) in whisper.cpp's format. `size` is for the
# size shown and progress; the SHA-256 decides whether a file is right.
MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
MODELS = {
    "tiny": {"file": "ggml-tiny.bin", "size": 77691713,
             "sha256": "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21"},
    "base": {"file": "ggml-base.bin", "size": 147951465,
             "sha256": "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"},
    "small": {"file": "ggml-small.bin", "size": 487601967,
              "sha256": "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"},
}
SIZE_TOLERANCE = 0.05       # a file may be this much bigger than shown before it's refused

ALLOWED_HOSTS = frozenset({
    "github.com",
    "objects.githubusercontent.com",          # GitHub's release downloads, old
    "release-assets.githubusercontent.com",   # and new
    "huggingface.co",
    "hf.co",
})
# Hugging Face's CDN, e.g. cdn-lfs.hf.co, cas-bridge.xethub.hf.co.
ALLOWED_HOST_SUFFIXES = (".hf.co", ".huggingface.co")

TIMEOUT_SECONDS = 30
CHUNK_BYTES = 64 * 1024


class DownloadError(Exception):
    """kind: "offline", "http" (code), "host" (detail = the host), "verify",
    "size", "extract", "disk" or "bad_data"."""

    def __init__(self, kind, detail="", code=None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = str(detail or "")
        self.code = code


class Cancelled(Exception):
    """The user cancelled the download."""


def model_url(name):
    return MODEL_BASE_URL + MODELS[name]["file"]


def user_agent():
    return f"HarikuV2/{core.constants.CORE_VERSION} (Voice Control extension)"


def host_allowed(url):
    """Whether Hariku may download from `url`: HTTPS on the default port, no
    user name, and a GitHub or Hugging Face host."""
    try:
        parts = urllib.parse.urlsplit(str(url))
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    if port not in (None, 443):
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    return host in ALLOWED_HOSTS or (bool(host) and host.endswith(ALLOWED_HOST_SUFFIXES))


def _host(url):
    try:
        return urllib.parse.urlsplit(str(url)).hostname or str(url)
    except ValueError:
        return str(url)


class CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to an allowed host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl):
            if fp is not None:
                try:
                    fp.close()
                except Exception:
                    pass
            raise DownloadError("host", _host(newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener(*handlers):
    """An opener that checks every redirect (and uses the system's proxy)."""
    return urllib.request.build_opener(CheckedRedirects(), *handlers)


def open_url(url, headers=None, timeout=TIMEOUT_SECONDS, opener=None):
    """GET `url`; DownloadError "host" for a host that isn't allowed (the
    first URL, a redirect or where it ended up), "http" for an error status,
    "offline" when the server can't be reached."""
    if not host_allowed(url):
        raise DownloadError("host", _host(url))
    request = urllib.request.Request(url, headers={"User-Agent": user_agent(),
                                                   **(headers or {})})
    try:
        response = (opener or build_opener()).open(request, timeout=timeout)
    except DownloadError:
        raise
    except urllib.error.HTTPError as e:
        try:
            e.close()
        except Exception:
            pass
        raise DownloadError("http", str(e.code), code=e.code) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        reason = getattr(e, "reason", None) or e
        raise DownloadError("offline", str(reason)) from None
    final = response.geturl() if hasattr(response, "geturl") else url
    if not host_allowed(final):
        response.close()
        raise DownloadError("host", _host(final))
    return response


def _status(response):
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    return status


# ------------------------------------------------------------
# Files: resume, verify, rename
# ------------------------------------------------------------

def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path, sha256, max_size=None):
    """Whether the file has this SHA-256 (and isn't over `max_size`)."""
    try:
        if max_size is not None and os.path.getsize(path) > max_size:
            return False
        return file_sha256(path) == sha256.lower()
    except OSError:
        return False


def max_size_for(size):
    return int(size * (1 + SIZE_TOLERANCE)) + 1024 * 1024


_CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", re.IGNORECASE)


def _range_start(value):
    match = _CONTENT_RANGE_RE.match(str(value or "").strip())
    return int(match.group(1)) if match else None


def _content_length(response):
    try:
        value = response.headers.get("Content-Length")
        return int(value) if value is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _never():
    return False


def download_file(url, dest, sha256, size, progress=None, cancelled=None, opener=None):
    """Download `url` to `dest`, which must end up with this SHA-256. `size`
    is the expected size, for progress; a file much bigger is refused.
    Continues "<dest>.part" when an earlier attempt stopped and starts over
    when the server can't resume. Calls progress(bytes so far) and checks
    cancelled() between chunks.

    Raises Cancelled (the part is deleted), DownloadError("verify"/"size")
    (the part is deleted: it can't be trusted), or another DownloadError (the
    part is kept for next time)."""
    progress = progress or (lambda done: None)
    cancelled = cancelled or _never
    if not sha256:
        raise ValueError("a checksum is required")
    limit = max_size_for(size)
    part = dest + store.PART_SUFFIX
    try:
        if os.path.isfile(dest):
            if verify_file(dest, sha256, limit):
                progress(os.path.getsize(dest))
                return dest
            os.remove(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        if have > limit:
            os.remove(part)
            have = 0
        _fetch_into(url, part, have, limit, progress, cancelled, opener)
        if cancelled():
            raise Cancelled()
        if not verify_file(part, sha256, limit):
            raise DownloadError("verify", os.path.basename(dest))
        os.replace(part, dest)
    except (Cancelled, DownloadError) as e:
        if isinstance(e, Cancelled) or e.kind in ("verify", "size"):
            store.remove_quietly(part)
        raise
    except OSError as e:
        raise DownloadError("disk", str(e)) from None
    progress(os.path.getsize(dest))
    return dest


def _fetch_into(url, part, have, limit, progress, cancelled, opener):
    """Append the rest of the file to `part`, which holds `have` bytes."""
    for attempt in (1, 2):
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            response = open_url(url, headers, opener=opener)
        except DownloadError as e:
            if e.kind == "http" and e.code == 416 and have and attempt == 1:
                store.remove_quietly(part)        # the server can't continue it
                have = 0
                continue
            raise
        with response:
            status = _status(response)
            if have and status == 206:
                if _range_start(response.headers.get("Content-Range")) != have:
                    response.close()
                    if attempt == 1:
                        store.remove_quietly(part)
                        have = 0
                        continue
                    raise DownloadError("bad_data", "Content-Range")
                mode = "ab"
            elif status in (200, None):
                have, mode = 0, "wb"              # the whole file; start over
            else:
                raise DownloadError("http", str(status), code=status)
            expected = _content_length(response)
            done = have
            received = 0
            progress(done)
            try:
                f = open(part, mode)
            except OSError as e:
                raise DownloadError("disk", str(e)) from None
            with f:
                while True:
                    if cancelled():
                        raise Cancelled()
                    try:
                        chunk = response.read(CHUNK_BYTES)
                    except (OSError, http.client.HTTPException) as e:
                        raise DownloadError("offline", str(e)) from None
                    if not chunk:
                        break
                    if done + len(chunk) > limit:
                        raise DownloadError("size", os.path.basename(part))
                    try:
                        f.write(chunk)
                    except OSError as e:
                        raise DownloadError("disk", str(e)) from None
                    done += len(chunk)
                    received += len(chunk)
                    progress(done)
        if expected is not None and received != expected:
            raise DownloadError("offline", "the download ended early")
        return


# ------------------------------------------------------------
# Unpacking the whisper.cpp zip (zip-slip safe)
# ------------------------------------------------------------

def safe_extract(zip_path, dest, max_bytes=RUNTIME_MAX_UNPACKED, max_entries=RUNTIME_MAX_ENTRIES):
    """Unpack a zip into `dest`, refusing (before writing anything) entries
    that would land outside it, absolute or drive paths, and archives that
    unpack to too much. Raises DownloadError("extract")."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = archive.infolist()
            if len(members) > max_entries:
                raise DownloadError("extract", "too many files")
            if sum(m.file_size for m in members) > max_bytes:
                raise DownloadError("extract", "too large")
            dest_real = os.path.realpath(dest)
            for member in members:
                name = member.filename
                if (not name or name.startswith(("/", "\\")) or ":" in name
                        or any(part == ".." for part in re.split(r"[\\/]", name))):
                    raise DownloadError("extract", f"unsafe entry {name!r}")
                target = os.path.realpath(os.path.join(dest, name))
                if target != dest_real and not target.startswith(dest_real + os.sep):
                    raise DownloadError("extract", f"unsafe entry {name!r}")
            os.makedirs(dest, exist_ok=True)
            for member in members:
                archive.extract(member, dest)
    except DownloadError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, RuntimeError) as e:
        raise DownloadError("extract", str(e)) from None
    except OSError as e:
        raise DownloadError("disk", str(e)) from None


# ------------------------------------------------------------
# Installing
# ------------------------------------------------------------

def install_runtime(root, progress=None, cancelled=None, opener=None):
    """Download the pinned whisper.cpp zip, check its SHA-256, unpack it into
    runtime\\ (replacing what is there) and delete the zip."""
    cancelled = cancelled or _never
    zip_path = os.path.join(store.downloads_dir(root), RUNTIME_FILE)
    download_file(RUNTIME_URL, zip_path, RUNTIME_SHA256, RUNTIME_SIZE, progress=progress,
                  cancelled=cancelled, opener=opener)
    if cancelled():
        raise Cancelled()
    target = store.runtime_dir(root)
    staging = target + ".new"
    try:
        shutil.rmtree(staging, ignore_errors=True)
        safe_extract(zip_path, staging)
        exe = store.find_server_exe(staging)
        if exe is None:
            raise DownloadError("extract", "whisper-server.exe is missing")
        relative = os.path.relpath(exe, staging)
        if os.path.isdir(target):
            shutil.rmtree(target)
        os.replace(staging, target)
        store.write_runtime_marker(root, {"version": RUNTIME_VERSION, "sha256": RUNTIME_SHA256,
                                          "url": RUNTIME_URL, "exe": relative})
    except DownloadError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise DownloadError("disk", str(e)) from None
    store.remove_quietly(zip_path)
    return store.server_exe(root)


def install_model(name, root, progress=None, cancelled=None, opener=None):
    """Download a speech model, check its SHA-256, and mark it installed."""
    if name not in MODELS:
        raise ValueError(f"unknown model: {name!r}")
    info = MODELS[name]
    dest = store.model_path(root, name)
    download_file(model_url(name), dest, info["sha256"], info["size"], progress=progress,
                  cancelled=cancelled, opener=opener)
    try:
        store.write_model_marker(root, name, os.path.getsize(dest), info["sha256"])
    except OSError as e:
        raise DownloadError("disk", str(e)) from None
    return dest
