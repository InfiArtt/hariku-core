# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Downloading the Piper program and voices (blocking; no wx). main.py runs these
on a worker thread, only after the user asked for a download.

Every request goes to an allowed host over HTTPS: GitHub and its release
download host, Hugging Face and its CDN. Each redirect is checked before it is
followed, so a redirect elsewhere is refused. Files are written as
"<name>.part", resumed with a Range request when an earlier attempt was cut
off, checked (the Piper zip against the SHA-256 pinned here, voice files
against the md5 in the voice index) and only then renamed into place. A file
that doesn't match is deleted, never used.
"""
import hashlib
import http.client
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import core.constants

import piper_voices_catalogue as catalogue
import piper_voices_store as store

# The official Windows build of Piper (MIT), rhasspy/piper's last release. The
# project is archived; its successor publishes no Windows program.
RUNTIME_VERSION = "2023.11.14-2"
RUNTIME_FILE = "piper_windows_amd64.zip"
RUNTIME_URL = (f"https://github.com/rhasspy/piper/releases/download/{RUNTIME_VERSION}/"
               f"{RUNTIME_FILE}")
RUNTIME_SIZE = 22477236
RUNTIME_SHA256 = "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea"
RUNTIME_MAX_UNPACKED = 128 * 1024 * 1024     # it unpacks to about 39 MB
RUNTIME_MAX_ENTRIES = 2000                   # it has 363

ALLOWED_HOSTS = frozenset({
    "github.com",
    "objects.githubusercontent.com",          # GitHub's release downloads, old
    "release-assets.githubusercontent.com",   # and new
    "huggingface.co",
    "hf.co",
})
# Hugging Face's CDN, e.g. us.aws.cdn.hf.co, cas-bridge.xethub.hf.co, cdn-lfs.hf.co.
ALLOWED_HOST_SUFFIXES = (".hf.co", ".huggingface.co")

TIMEOUT_SECONDS = 30
CHUNK_BYTES = 64 * 1024
MAX_INDEX_BYTES = 16 * 1024 * 1024


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


def user_agent():
    return f"HarikuV2/{core.constants.CORE_VERSION} (Piper Voices extension)"


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
    """GET `url` and return the response. Raises DownloadError: "host" for a
    host that isn't allowed (the first URL, a redirect or where it ended up),
    "http" for an error status, "offline" when the server can't be reached."""
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


def fetch_bytes(url, max_bytes, timeout=TIMEOUT_SECONDS):
    """The body of a small file; DownloadError("size") when it is too big."""
    with open_url(url, timeout=timeout) as response:
        try:
            data = response.read(max_bytes + 1)
        except (OSError, http.client.HTTPException) as e:
            raise DownloadError("offline", str(e)) from None
    if len(data) > max_bytes:
        raise DownloadError("size", url)
    return data


def fetch_catalogue():
    """The voice index (voices.json) as a dict; parse it with
    catalogue.parse_catalogue()."""
    data = fetch_bytes(catalogue.INDEX_URL, MAX_INDEX_BYTES)
    try:
        index = json.loads(data.decode("utf-8"))
    except ValueError:
        raise DownloadError("bad_data", "voices.json") from None
    if not isinstance(index, dict):
        raise DownloadError("bad_data", "voices.json")
    return index


def fetch_model_card(voice):
    """A voice's MODEL_CARD text, checked against its size and md5."""
    card = voice["files"]["card"]
    data = fetch_bytes(catalogue.file_url(card["path"]), catalogue.MAX_CARD_BYTES)
    if len(data) != card["size"]:
        raise DownloadError("size", "MODEL_CARD")
    if hashlib.md5(data).hexdigest() != card["md5"]:
        raise DownloadError("verify", "MODEL_CARD")
    return data.decode("utf-8", "replace")


# ------------------------------------------------------------
# Files: resume, verify, rename
# ------------------------------------------------------------

def file_digest(path, algorithm):
    digest = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path, size, md5=None, sha256=None):
    """Whether the file has exactly this size and these digests."""
    try:
        if os.path.getsize(path) != size:
            return False
        if md5 is not None and file_digest(path, "md5") != md5.lower():
            return False
        if sha256 is not None and file_digest(path, "sha256") != sha256.lower():
            return False
    except OSError:
        return False
    return True


_CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", re.IGNORECASE)


def _range_start(value):
    match = _CONTENT_RANGE_RE.match(str(value or "").strip())
    return int(match.group(1)) if match else None


def _never():
    return False


def download_file(url, dest, size, md5=None, sha256=None, progress=None, cancelled=None):
    """Download `url` to `dest`, which must end up exactly `size` bytes with
    these digests. Continues "<dest>.part" when an earlier attempt stopped
    (a connection lost) and starts over when the server can't resume. Calls
    progress(bytes so far) and checks cancelled() between chunks.

    Raises Cancelled (the part is deleted), DownloadError("verify"/"size")
    (the part is deleted: it can't be trusted), or another DownloadError (the
    part is kept for next time)."""
    progress = progress or (lambda done: None)
    cancelled = cancelled or _never
    if md5 is None and sha256 is None:
        raise ValueError("a checksum is required")
    part = dest + store.PART_SUFFIX
    try:
        if os.path.isfile(dest):
            if verify_file(dest, size, md5, sha256):
                progress(size)
                return dest
            os.remove(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        if have > size:
            os.remove(part)
            have = 0
        if have < size:
            _fetch_into(url, part, have, size, progress, cancelled)
        if cancelled():
            raise Cancelled()
        if not verify_file(part, size, md5, sha256):
            raise DownloadError("verify", os.path.basename(dest))
        os.replace(part, dest)
    except (Cancelled, DownloadError) as e:
        if isinstance(e, Cancelled) or e.kind in ("verify", "size"):
            store.remove_quietly(part)
        raise
    except OSError as e:
        raise DownloadError("disk", str(e)) from None
    progress(size)
    return dest


def _fetch_into(url, part, have, size, progress, cancelled):
    """Append the rest of the file to `part`, which holds `have` bytes."""
    for attempt in (1, 2):
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            response = open_url(url, headers)
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
            done = have
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
                    if done + len(chunk) > size:
                        raise DownloadError("size", os.path.basename(part))
                    try:
                        f.write(chunk)
                    except OSError as e:
                        raise DownloadError("disk", str(e)) from None
                    done += len(chunk)
                    progress(done)
        if done != size:
            raise DownloadError("offline", "the download ended early")
        return


# ------------------------------------------------------------
# Unpacking the Piper zip (zip-slip safe)
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

def install_runtime(root, progress=None, cancelled=None):
    """Download the pinned Piper zip, check its SHA-256, unpack it into
    runtime\\ (replacing what is there) and delete the zip."""
    cancelled = cancelled or _never
    zip_path = os.path.join(store.downloads_dir(root), RUNTIME_FILE)
    download_file(RUNTIME_URL, zip_path, RUNTIME_SIZE, sha256=RUNTIME_SHA256,
                  progress=progress, cancelled=cancelled)
    if cancelled():
        raise Cancelled()
    target = store.runtime_dir(root)
    staging = target + ".new"
    try:
        shutil.rmtree(staging, ignore_errors=True)
        safe_extract(zip_path, staging)
        if not os.path.isfile(os.path.join(staging, *store.RUNTIME_EXE)):
            raise DownloadError("extract", "piper.exe is missing")
        if os.path.isdir(target):
            shutil.rmtree(target)
        os.replace(staging, target)
        store.write_runtime_marker(root, {"version": RUNTIME_VERSION, "sha256": RUNTIME_SHA256,
                                          "url": RUNTIME_URL})
    except DownloadError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise DownloadError("disk", str(e)) from None
    store.remove_quietly(zip_path)
    return store.exe_path(root)


def install_voice(voice, root, card_text=None, progress=None, cancelled=None):
    """Download a voice's .onnx.json and .onnx (checked against the index's
    md5), save its model card, then write voice.json, which makes it
    installed. On Cancel its unfinished files are removed."""
    progress = progress or (lambda done: None)
    cancelled = cancelled or _never
    key = voice["key"]
    folder = store.voice_dir(root, key)
    try:
        os.makedirs(folder, exist_ok=True)
        base = 0
        for role in ("config", "model"):
            item = voice["files"][role]
            dest = os.path.join(folder, item["path"].rsplit("/", 1)[-1])
            download_file(catalogue.file_url(item["path"]), dest, item["size"], md5=item["md5"],
                          progress=lambda done, base=base: progress(base + done),
                          cancelled=cancelled)
            base += item["size"]
        if cancelled():
            raise Cancelled()
        card = None
        if card_text:
            store.write_atomically(os.path.join(folder, store.CARD_FILE),
                                   card_text.encode("utf-8"))
            card = catalogue.parse_model_card(card_text)
        store.write_voice_marker(root, voice, card)
    except Cancelled:
        store.discard_partials(folder)
        if not store.is_installed(root, key):
            shutil.rmtree(folder, ignore_errors=True)
        raise
    except OSError as e:
        raise DownloadError("disk", str(e)) from None
    return folder
