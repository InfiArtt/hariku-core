# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import urllib.request
import urllib.parse
import json
import os
import shutil
import logging
from packaging.version import Version

import core.endpoints

logger = logging.getLogger(__name__)

# [SEC HIGH-4] Trusted download hosts (see core.endpoints for the full policy).
_ALLOWED_DOWNLOAD_DOMAINS = core.endpoints.ALLOWED_DOWNLOAD_HOSTS


def _validate_download_url(url):
    """
    [SEC HIGH-3, HIGH-4] Validate that a download URL is safe (HTTPS + under one
    of our own base URLs). Delegates to the central host- and path-pinned policy
    in core.endpoints. Raises ValueError if the URL is rejected.
    """
    core.endpoints.assert_download_url(url)

# Extension registry, hosted on GitHub Pages (see core.endpoints).
STORE_URL = core.endpoints.STORE_REGISTRY_URL

def fetch_registry():
    """Fetch data from the Store URL."""
    try:
        req = urllib.request.Request(STORE_URL, headers={'User-Agent': 'HarikuV2/2.0'})
        with urllib.request.urlopen(req, timeout=15) as response:  # [SEC HIGH-4] added timeout
            data = json.loads(response.read().decode('utf-8'))
            extensions = data.get("extensions", [])
            # [SEC HIGH-4] Filter out entries with untrusted download URLs
            validated = []
            for ext in extensions:
                url = ext.get("download_url", "")
                try:
                    _validate_download_url(url)
                    validated.append(ext)
                except ValueError as e:
                    logger.warning(f"Registry entry rejected: {e} (url={url})")
            return validated
    except Exception as e:
        logger.error(f"Failed to fetch store registry: {e}")
        return []

def _sanitize_ext_id(ext_id):
    """
    [SEC MED-5] Reduce an extension id to a safe filename component.
    A registry entry (which could be spoofed if the store were compromised)
    must never be able to steer the download to '../../Startup/evil' etc.
    Returns the sanitized id, or "" if nothing safe remains.
    """
    return "".join(c for c in str(ext_id) if c.isalnum() or c in ("-", "_")).strip()


def download_extension(ext_id, download_url):
    """Download and save an extension into the /extensions folder."""
    # [SEC HIGH-3] Validate URL before any download attempt
    try:
        _validate_download_url(download_url)
    except ValueError as e:
        logger.error(f"download_extension blocked for '{ext_id}': {e}")
        return False

    # [SEC MED-5] Sanitize the id so it cannot escape the extensions directory.
    safe_id = _sanitize_ext_id(ext_id)
    if not safe_id:
        logger.error(f"download_extension blocked: invalid extension id {ext_id!r}")
        return False

    import core.extension_manager
    extensions_dir = core.extension_manager.USER_EXTENSIONS_DIR
    if not os.path.exists(extensions_dir):
        os.makedirs(extensions_dir)

    target_path = os.path.join(extensions_dir, f"{safe_id}.hrk")

    # [SEC MED-5] Defense in depth: confirm the resolved path stays inside the dir.
    if not os.path.realpath(target_path).startswith(os.path.realpath(extensions_dir) + os.sep):
        logger.error(f"download_extension blocked: path escapes extensions dir for {ext_id!r}")
        return False

    try:
        req = urllib.request.Request(download_url, headers={'User-Agent': 'HarikuV2/2.0'})
        with urllib.request.urlopen(req, timeout=60) as response, open(target_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        return True
    except Exception as e:
        logger.error(f"Failed to download extension {ext_id}: {e}")
        return False

def _parse_version(v):
    """Parse version string safely."""
    try:
        return Version(str(v))
    except Exception:
        return Version("0")

def check_for_updates():
    """
    Compares registry versions against installed versions.
    Returns a list of dicts for extensions that have updates:
        [{"id", "name", "current_version", "new_version", "download_url"}]
    Only checks .hrk (zipped) extensions that came from the store — not unpacked dev folders.
    """
    import core.extension_manager
    registry = fetch_registry()
    if not registry:
        return []

    installed = {
        ext_id: info
        for ext_id, info in core.extension_manager.LOADED_EXTENSIONS.items()
        if not info.get("is_unpacked", False)   # skip developer-mode folder extensions
    }

    updates = []
    for entry in registry:
        ext_id = entry.get("id", "")
        if ext_id not in installed:
            continue
        current_ver = installed[ext_id]["manifest"].get("version", "0")
        new_ver     = entry.get("version", "0")
        if _parse_version(new_ver) > _parse_version(current_ver):
            updates.append({
                "id":              ext_id,
                "name":            entry.get("name", ext_id),
                "current_version": current_ver,
                "new_version":     new_ver,
                "download_url":    entry.get("download_url", ""),
            })
    return updates

def auto_update_extensions(updates):
    """
    Downloads and replaces .hrk files for each entry in `updates`.
    Returns (success_list, fail_list).
    """
    success, fail = [], []
    for upd in updates:
        ok = download_extension(upd["id"], upd["download_url"])
        if ok:
            success.append(upd)
            logger.info(f"Updated extension {upd['id']} to {upd['new_version']}")
        else:
            fail.append(upd)
            logger.error(f"Failed to update extension {upd['id']}")
    return success, fail
