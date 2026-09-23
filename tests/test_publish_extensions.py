# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Merge logic of tools/publish_extensions.py, which rewrites the live store
# registry and trusted-hash list.

import datetime
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def pub():
    spec = importlib.util.spec_from_file_location(
        "publish_extensions", os.path.join(ROOT, "tools", "publish_extensions.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MANIFEST = {"name": "Routines", "version": "1.0", "description": "Automation.",
            "author": "Rafli", "main": "main.py"}


def test_registry_entry_points_at_an_allowed_download_url(pub):
    import core.endpoints
    entry = pub.registry_entry("routines", MANIFEST)
    assert entry["id"] == "routines" and entry["version"] == "1.0"
    assert core.endpoints.is_trusted_download_url(entry["download_url"])


def test_merge_registry_replaces_in_place_and_appends(pub):
    registry = {"extensions": [{"id": "a", "version": "1.0"}, {"id": "b", "version": "1.0"}]}
    merged = pub.merge_registry(registry, [{"id": "a", "version": "1.1"}, {"id": "c", "version": "1.0"}])
    assert [(e["id"], e["version"]) for e in merged["extensions"]] == [
        ("a", "1.1"), ("b", "1.0"), ("c", "1.0")]
    assert registry["extensions"][0]["version"] == "1.0"  # input untouched


def test_merge_trusted_dedupes_lowercases_and_keeps_old(pub):
    now = datetime.datetime(2026, 9, 23, 12, 0, tzinfo=datetime.timezone.utc)
    merged = pub.merge_trusted({"trusted": ["AAA", "bbb"], "total": 2}, ["aaa", "CCC"], now)
    assert merged["trusted"] == ["aaa", "bbb", "ccc"]
    assert merged["total"] == 3
    assert merged["generated_at"] == "2026-09-23T12:00:00Z"
