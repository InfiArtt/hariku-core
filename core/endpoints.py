# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================
# Central registry of every remote endpoint Hariku talks to, plus the security
# policy for download URLs. Change hosting in ONE place.
#
# History: the old free domain novarealm.cloud expired, so all static content
# moved to GitHub (Pages for JSON manifests, Releases for binaries). GitHub
# can't accept POST, so crash reports now go to the InfiArtt backend below
# (core.crash_handler), and the old telemetry ping was retired for good: Hariku
# collects no telemetry (see core.telemetry and PRIVACY.md).
#
# TO MIGRATE HOSTING: edit GITHUB_OWNER / GITHUB_REPO (and, later, PAGES_HOST
# if you point a custom domain at Pages). Nothing else needs to change.
# =============================================================================

import re
from urllib.parse import urlparse

# --- GitHub account/repo hosting Pages (manifests) + Releases (binaries) -----
GITHUB_OWNER = "InfiArtt"
GITHUB_REPO = "hariku"

# GitHub Pages host. For a project site this is "<owner>.github.io" and the
# content lives under /<repo>/. Set this to a custom domain later if you add one.
PAGES_HOST = f"{GITHUB_OWNER}.github.io".lower()

# Installer asset name inside each GitHub Release (used only as a fallback; the
# real download URL is normally supplied by version.json). MUST match the Inno
# Setup OutputBaseFilename in file.iss (currently "HarikuV2-Setup").
INSTALLER_ASSET_NAME = "HarikuV2-Setup.exe"

# --- Derived base URLs -------------------------------------------------------
# Static JSON manifests served by GitHub Pages.
PAGES_BASE = f"https://{PAGES_HOST}/{GITHUB_REPO}"
# Binaries (installer + .hrk extensions) served as GitHub Release assets.
RELEASES_BASE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

# --- Concrete endpoints ------------------------------------------------------
TRUSTED_HASHES_URL = f"{PAGES_BASE}/security/trusted_extensions.json"
UPDATE_JSON_URL = f"{PAGES_BASE}/update/version.json"
STORE_REGISTRY_URL = f"{PAGES_BASE}/dl/registry.json"

# "latest" always resolves to the newest release's asset of this name.
DEFAULT_INSTALLER_URL = f"{RELEASES_BASE}/latest/download/{INSTALLER_ASSET_NAME}"

# Where the Help > Support / Report menu items point.
SUPPORT_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
NEW_ISSUE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/issues/new"

# --- InfiArtt dynamic API backend (POST endpoints; not static GitHub Pages) ---
# infiartt.com is a stable domain the team controls (unlike the retired
# novarealm.cloud). Its PHP backend exposes these routes.
INFIARTT_API_BASE = "https://infiartt.com"
# POST {app_version, os_info, language, error_type, error_message, traceback} -> 201
# Sent only when the user agrees in the crash dialog (or chose "always send").
CRASH_REPORT_URL = f"{INFIARTT_API_BASE}/api/crash-report"
# infiartt.com sits behind Cloudflare, whose browser check refuses requests
# without a real User-Agent (Python's default gets "403, error code 1010"),
# so everything Hariku sends there names itself.
HTTP_USER_AGENT = "HarikuV2/2.0"

# --- Hariku AI (core 2.11) ----------------------------------------------------
# The Cloudflare Worker behind the Ask Hariku extension: "Tanya Hariku"
# answers and Aruna's AI fallback (hariku-ai, among the servers InfiArtt
# maintains privately). Only the address is
# here; the Worker reaches Workers AI through its own binding, so there is no
# key in Hariku. Ask Hariku sends nothing unless the user turns it on.
#
# It runs on the infiartt Cloudflare account at its own subdomain, apart from
# the website (which it never touches).
HARIKU_AI_URL = "https://ai.infiartt.com"

# Where Ask Hariku may send a question (the address can be changed on its
# Preferences page, for a self-hosted copy of the Worker): HTTPS on
# infiartt.com, or a Cloudflare Worker on workers.dev. Plain HTTP only to
# this computer (`wrangler dev`).
HARIKU_AI_HOSTS = frozenset(["infiartt.com"])
HARIKU_AI_HOST_SUFFIXES = (".infiartt.com", ".workers.dev")
LOCAL_HOSTS = frozenset(["localhost", "127.0.0.1", "[::1]", "::1"])
_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")


def assert_ai_url(url):
    """Raise ValueError unless `url` is a Hariku AI address Hariku may send
    to: https on an allowed host (HARIKU_AI_HOSTS, or a host ending in one of
    HARIKU_AI_HOST_SUFFIXES), or http(s) to this computer. No user name,
    password, query or fragment. Returns the address without a trailing /."""
    url = (url or "").strip()
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if parsed.username or parsed.password or "@" in parsed.netloc:
        raise ValueError("[Security] An AI address can't carry a user name or password.")
    if parsed.query or parsed.fragment or ".." in parsed.path:
        raise ValueError("[Security] An AI address has no query, fragment or '..'.")
    host = (parsed.hostname or "").lower()
    if host in LOCAL_HOSTS:
        if scheme not in ("http", "https"):
            raise ValueError(f"[Security] Unsupported scheme {scheme!r}.")
        return url.rstrip("/")
    if scheme != "https":
        raise ValueError(f"[Security] The AI service must use HTTPS, got {scheme!r}.")
    if not _HOST_RE.match(host):
        raise ValueError(f"[Security] Not a host name: {host!r}")
    if host not in HARIKU_AI_HOSTS and not host.endswith(HARIKU_AI_HOST_SUFFIXES):
        raise ValueError(f"[Security] The AI service isn't on an allowed host: {host!r}")
    return url.rstrip("/")


def is_allowed_ai_url(url):
    """Boolean form of assert_ai_url()."""
    try:
        assert_ai_url(url)
        return True
    except ValueError:
        return False


def ai_host(url):
    """The host of an allowed AI address ("ai.infiartt.com"), or ""."""
    if not is_allowed_ai_url(url):
        return ""
    return (urlparse(url.strip()).hostname or "").lower()


# The official service's host. The InfiArtt sign-in token goes only there,
# over HTTPS, matched exactly: never to a self-hosted copy (workers.dev), to
# this computer, or to a lookalike ("ai.infiartt.com.example.com",
# "evilai.infiartt.com"), whatever the Ask Hariku page says.
HARIKU_AI_TOKEN_HOSTS = frozenset([urlparse(HARIKU_AI_URL).hostname or ""]) - {""}


def is_official_ai_url(url):
    """Whether `url` is Hariku's own AI service (HTTPS, exactly its host)."""
    if not is_allowed_ai_url(url):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme.lower() == "https" and (parsed.hostname or "").lower() in HARIKU_AI_TOKEN_HOSTS


def may_send_account_token(url):
    """Whether a request to `url` may carry the InfiArtt sign-in token: only
    to the official service."""
    return is_official_ai_url(url)


# --- Download URL security policy --------------------------------------------
# Pages host is exclusively YOUR content, so a host match there is already
# tight. github.com is shared by everyone, so a Release URL must additionally
# start with YOUR repo's release path — otherwise a spoofed manifest could point
# at github.com/attacker/malware/releases/... and pass a host-only check.
ALLOWED_DOWNLOAD_HOSTS = frozenset([PAGES_HOST, "github.com"])
ALLOWED_URL_PREFIXES = (
    PAGES_BASE + "/",
    RELEASES_BASE + "/",
)


def assert_download_url(url):
    """
    Raise ValueError unless `url` is an HTTPS URL that lives under one of our
    own base URLs (host- AND path-pinned). Used before every remote download.
    """
    parsed = urlparse(url or "")
    scheme = parsed.scheme.lower()
    if scheme == "file":
        raise ValueError("[Security] file:// URLs are not permitted for remote downloads.")
    if scheme != "https":
        raise ValueError(f"[Security] Only HTTPS downloads are allowed, got: {scheme!r}")
    if ".." in parsed.path:
        raise ValueError("[Security] Path traversal in download URL rejected.")
    # netloc split guards against user-info smuggling like host@evil.com
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(f"[Security] Download from untrusted domain blocked: {host!r}")
    if not any(url.startswith(prefix) for prefix in ALLOWED_URL_PREFIXES):
        raise ValueError(f"[Security] Download URL is not under an allowed Hariku path: {url!r}")


def is_trusted_download_url(url):
    """Boolean form of assert_download_url()."""
    try:
        assert_download_url(url)
        return True
    except ValueError:
        return False
