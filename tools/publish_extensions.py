#!/usr/bin/env python3
# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Publish extensions from this repo to the Hariku store in one step.

    python tools/publish_extensions.py routines filter            # publish
    python tools/publish_extensions.py routines filter --dry-run  # show the plan

For each extension it packages extensions/<id>/ into <id>.hrk, then:
  1. uploads the .hrk files to the "extensions" release of the dist repo,
  2. adds their SHA-256 hashes to security/trusted_extensions.json,
  3. adds or updates their entries in dl/registry.json,
  4. downloads each published file again and checks its hash.
The trusted list is updated before the registry, so the store never offers a
file Hariku doesn't trust yet. Only committed extensions are published, so every
store file matches a public commit. Needs the `gh` CLI, logged in with write
access to the dist repo (or GH_TOKEN set).
"""

import argparse
import base64
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import core.endpoints as endpoints  # noqa: E402
from packager import package_extension, validate_manifest  # noqa: E402

DIST_REPO = f"{endpoints.GITHUB_OWNER}/{endpoints.GITHUB_REPO}"
RELEASE_TAG = "extensions"
REGISTRY_PATH = "dl/registry.json"
TRUSTED_PATH = "security/trusted_extensions.json"


# --- Pure helpers (unit-tested) ------------------------------------------------

def download_url(ext_id):
    return f"{endpoints.RELEASES_BASE}/download/{RELEASE_TAG}/{ext_id}.hrk"


def registry_entry(ext_id, manifest):
    return {
        "id": ext_id,
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "author": manifest["author"],
        "download_url": download_url(ext_id),
    }


def merge_registry(registry, entries):
    """Replace entries with the same id in place; append new ones."""
    current = list(registry.get("extensions", []))
    index = {e.get("id"): i for i, e in enumerate(current)}
    for entry in entries:
        if entry["id"] in index:
            current[index[entry["id"]]] = entry
        else:
            index[entry["id"]] = len(current)
            current.append(entry)
    return {**registry, "extensions": current}


def merge_trusted(trusted, hashes, now=None):
    """Add hashes (lowercase, no duplicates). Older hashes stay trusted, so
    people still on a previous version aren't warned about it."""
    combined = [h.lower() for h in trusted.get("trusted", [])]
    for h in hashes:
        if h.lower() not in combined:
            combined.append(h.lower())
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return {**trusted,
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": len(combined),
            "trusted": combined}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --- GitHub I/O ----------------------------------------------------------------

def _gh(*args, input_text=None):
    result = subprocess.run(["gh", *args], capture_output=True, text=True,
                            encoding="utf-8", input=input_text)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout


def gh_get_json(path):
    meta = json.loads(_gh("api", f"repos/{DIST_REPO}/contents/{path}?ref=main"))
    return json.loads(base64.b64decode(meta["content"]).decode("utf-8")), meta["sha"]


def gh_put_json(path, data, sha, message):
    body = {
        "message": message,
        "content": base64.b64encode(
            (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": "main",
    }
    _gh("api", "--method", "PUT", f"repos/{DIST_REPO}/contents/{path}", "--input", "-",
        input_text=json.dumps(body))


def uncommitted_changes(ext_id):
    return subprocess.run(
        ["git", "-C", ROOT, "status", "--porcelain", "--", f"extensions/{ext_id}"],
        capture_output=True, text=True).stdout.strip()


# --- Main ------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Publish Hariku extensions to the store.")
    parser.add_argument("ids", nargs="+", help="extension folder names under extensions/")
    parser.add_argument("--dry-run", action="store_true", help="package and show the plan only")
    args = parser.parse_args(argv)

    work = tempfile.mkdtemp(prefix="hariku_publish_")
    entries, files, hashes = [], [], []
    for ext_id in args.ids:
        folder = os.path.join(ROOT, "extensions", ext_id)
        manifest = validate_manifest(folder) if os.path.isdir(folder) else None
        if manifest is None:
            sys.exit(f"[ERROR] extensions/{ext_id} is missing or has an invalid manifest.")
        dirty = uncommitted_changes(ext_id)
        if dirty and not args.dry_run:
            sys.exit(f"[ERROR] extensions/{ext_id} has uncommitted changes; commit first:\n{dirty}")
        if not package_extension(folder, work):
            sys.exit(f"[ERROR] packaging {ext_id} failed.")
        path = os.path.join(work, f"{ext_id}.hrk")
        files.append(path)
        hashes.append(sha256_file(path))
        entries.append(registry_entry(ext_id, manifest))

    print("\nPlan:")
    for entry, digest in zip(entries, hashes):
        print(f"  {entry['id']} {entry['version']}  sha256 {digest[:16]}...  -> {entry['download_url']}")
    if args.dry_run:
        print("\nDry run: nothing uploaded.")
        return 0

    names = ", ".join(e["id"] for e in entries)
    print(f"\n1/4 Uploading {len(files)} file(s) to the '{RELEASE_TAG}' release...")
    _gh("release", "upload", RELEASE_TAG, *files, "--repo", DIST_REPO, "--clobber")

    print("2/4 Adding hashes to the trusted list...")
    trusted, sha = gh_get_json(TRUSTED_PATH)
    gh_put_json(TRUSTED_PATH, merge_trusted(trusted, hashes), sha, f"Trust extensions: {names}")

    print("3/4 Updating the store registry...")
    registry, sha = gh_get_json(REGISTRY_PATH)
    gh_put_json(REGISTRY_PATH, merge_registry(registry, entries), sha, f"Publish extensions: {names}")

    print("4/4 Verifying the published files...")
    bad = []
    for entry, digest in zip(entries, hashes):
        req = urllib.request.Request(entry["download_url"], headers={"User-Agent": "HarikuPublisher"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            got = hashlib.sha256(resp.read()).hexdigest()
        status = "OK" if got == digest else f"MISMATCH (got {got[:16]}...)"
        if got != digest:
            bad.append(entry["id"])
        print(f"  {entry['id']}: {status}")
    if bad:
        sys.exit(f"[ERROR] published files don't match: {bad}")
    print(f"\nPublished: {names}. GitHub Pages may take a few minutes to serve the new lists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
