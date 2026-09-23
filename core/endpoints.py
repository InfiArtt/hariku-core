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
# moved to GitHub (Pages for JSON manifests, Releases for binaries) and the
# telemetry / crash-report POST endpoints were retired (GitHub can't accept
# POST). See core.telemetry and core.crash_handler.
#
# TO MIGRATE HOSTING: edit GITHUB_OWNER / GITHUB_REPO (and, later, PAGES_HOST
# if you point a custom domain at Pages). Nothing else needs to change.
# =============================================================================

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
CRASH_REPORT_URL = f"{INFIARTT_API_BASE}/api/crash-report"
# Telemetry endpoint exists too, but the core ping is intentionally left OFF
# (see core.telemetry). Kept here for if it's ever re-enabled.
TELEMETRY_URL = f"{INFIARTT_API_BASE}/api/telemetry"

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
