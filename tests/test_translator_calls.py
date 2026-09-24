# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# A translator is called as _(key, **values), so a value named "key" collides
# with the message key and raises TypeError when the line runs. That once
# stopped the main window from opening, and only the window checks in CI
# noticed. This finds such calls without opening anything.

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"venv", ".git", "__pycache__", "build", "dist", "scratchpad", ".cache", "lib"}


def _python_files():
    for folder in ("core", "ui", "extensions"):
        for root, dirs, files in os.walk(os.path.join(ROOT, folder)):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(root, name)
    yield os.path.join(ROOT, "hariku.py")


def test_no_translator_call_passes_a_value_named_key():
    problems = []
    for path in _python_files():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_"
                    and any(k.arg == "key" for k in node.keywords)):
                problems.append(f"{os.path.relpath(path, ROOT)}:{node.lineno}")
    assert not problems, "_(…, key=…) collides with the message key: " + ", ".join(problems)
