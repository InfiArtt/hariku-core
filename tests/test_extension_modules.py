# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The loader puts each extension's folder on sys.path, so an extension's helper
# modules are imported by their bare file name into one shared namespace. A
# helper named like a Hariku package, a stdlib module, or another extension's
# helper gets silently replaced by whichever module Python finds first. That is
# how Routines' old ui.py resolved to Hariku's own `ui` package.

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_ROOT = os.path.join(ROOT, "extensions")
HARIKU_TOP_LEVEL = {"core", "ui", "tests", "tools", "extensions", "hariku"}


def _helper_modules():
    """Yield (extension_id, module_name) for every non-main top-level .py file."""
    for ext_id in sorted(os.listdir(EXT_ROOT)):
        ext_dir = os.path.join(EXT_ROOT, ext_id)
        if not os.path.isfile(os.path.join(ext_dir, "manifest.json")):
            continue
        for name in os.listdir(ext_dir):
            if name.endswith(".py") and name != "main.py":
                yield ext_id, name[:-3]


def test_helpers_do_not_shadow_hariku_or_stdlib():
    bad = [f"extensions/{ext}/{mod}.py shadows "
           f"{'a Hariku package' if mod in HARIKU_TOP_LEVEL else 'a stdlib module'}"
           for ext, mod in _helper_modules()
           if mod in HARIKU_TOP_LEVEL or mod in sys.stdlib_module_names]
    assert not bad, "\n".join(bad)


def test_helper_names_are_unique_across_extensions():
    owners = {}
    for ext, mod in _helper_modules():
        owners.setdefault(mod, []).append(ext)
    dupes = [f"{mod}.py is used by {', '.join(exts)}"
             for mod, exts in owners.items() if len(exts) > 1]
    assert not dupes, "\n".join(dupes)
