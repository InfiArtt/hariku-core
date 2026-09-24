# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Manifest checks for the extensions in this repo, and the core-version gate
# the loader applies to them.

import ast
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_ROOT = os.path.join(ROOT, "extensions")
REQUIRED = ["name", "version", "description", "main", "author", "language",
            "minimum_core_version"]


def _manifests():
    for ext_id in sorted(os.listdir(EXT_ROOT)):
        path = os.path.join(EXT_ROOT, ext_id, "manifest.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                yield ext_id, json.load(f)


@pytest.mark.parametrize("text, expected", [
    ("2.4", (2, 4)), ("2.4.0", (2, 4)), ("2", (2, 0)), ("2.10", (2, 10)),
    ("", None), ("two", None),
])
def test_version_tuple(text, expected):
    from core.extension_manager import _version_tuple
    assert _version_tuple(text) == expected


def test_minor_versions_compare_numerically():
    from core.extension_manager import _version_tuple
    assert _version_tuple("2.10") > _version_tuple("2.4")


def test_bundled_manifests_are_complete_and_readable():
    from core.extension_manager import _version_tuple
    problems = []
    for ext_id, manifest in _manifests():
        missing = [f for f in REQUIRED if f not in manifest]
        if missing:
            problems.append(f"{ext_id}: missing {missing}")
        elif _version_tuple(manifest["minimum_core_version"]) is None:
            problems.append(f"{ext_id}: unreadable minimum_core_version")
    assert not problems, "\n".join(problems)


# Core features newer than 2.0, and the release that introduced them. An
# extension using one must declare at least that minimum_core_version, or older
# installs load it and crash. Add an entry whenever the core gains a new API.
CORE_FEATURES_SINCE = {
    "core.ui_scale": (2, 4),
    "on_reminder_fired": (2, 4),
    "zoneinfo": (2, 5),
    "set_theme_dir": (2, 6),
    "get_builtin_sounds_dir": (2, 6),
    "stop_sound": (2, 6),
    "core.personal": (2, 7),
}


def test_minimum_core_version_covers_the_features_used():
    from core.extension_manager import _version_tuple
    problems = []
    for ext_id, manifest in _manifests():
        declared = _version_tuple(manifest.get("minimum_core_version")) or (0, 0)
        ext_dir = os.path.join(EXT_ROOT, ext_id)
        source = ""
        for name in os.listdir(ext_dir):
            if name.endswith(".py"):
                with open(os.path.join(ext_dir, name), encoding="utf-8") as f:
                    source += f.read()
        for feature, since in CORE_FEATURES_SINCE.items():
            if feature in source and declared < since:
                problems.append(f"{ext_id} uses {feature} (core {since[0]}.{since[1]}) but "
                                f"declares minimum_core_version {manifest.get('minimum_core_version')}")
    assert not problems, "\n".join(problems)


LOCALE_MANIFEST_FIELDS =["language_name", "language_code", "translator", "email", "version"]


def _locale_files(ext_id):
    locales = os.path.join(EXT_ROOT, ext_id, "locales")
    if not os.path.isdir(locales):
        return []
    return [os.path.join(locales, f) for f in sorted(os.listdir(locales)) if f.endswith(".json")]


def _translation_keys_used(ext_id):
    """String keys passed to _() anywhere in the extension's own code."""
    keys = set()
    ext_dir = os.path.join(EXT_ROOT, ext_id)
    for name in os.listdir(ext_dir):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(ext_dir, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
    return keys


def test_locale_files_load_and_cover_every_key():
    # core.i18n silently skips a language file whose manifest lacks a required
    # field, and a missing key shows its raw name, so both would reach users.
    problems = []
    for ext_id, _manifest in _manifests():
        files = _locale_files(ext_id)
        if not files:
            continue
        used = _translation_keys_used(ext_id)
        for path in files:
            rel = os.path.relpath(path, ROOT)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            missing = [k for k in LOCALE_MANIFEST_FIELDS if k not in data.get("manifest", {})]
            if missing:
                problems.append(f"{rel}: manifest missing {missing}")
            absent = sorted(used - set(data.get("messages", {})))
            if absent:
                problems.append(f"{rel}: no translation for {absent}")
    assert not problems, "\n".join(problems)


def _set_literal(path, name):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = node.value
            if isinstance(value, ast.Call):  # frozenset([...])
                value = value.args[0]
            return set(ast.literal_eval(value))
    raise AssertionError(f"{name} not found in {path}")


def test_official_ids_match_the_server_tool():
    core_ids = _set_literal(os.path.join(ROOT, "core", "extension_manager.py"),
                            "_OFFICIAL_EXTENSION_IDS")
    tool_ids = _set_literal(os.path.join(ROOT, "tools", "server", "generate_trusted_hashes.py"),
                            "OFFICIAL_EXTENSION_IDS")
    assert core_ids == tool_ids, (
        f"only in core: {sorted(core_ids - tool_ids)}; only in tool: {sorted(tool_ids - core_ids)}")
