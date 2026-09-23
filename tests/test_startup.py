# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Guards against the app failing to start. The other tests import modules but
# never build the main window, which let an UnboundLocalError in
# MainWindow.__init__ through (a local `import core.ui_scale` made `core` local
# to the whole function).

import ast
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIRS = ("core", "ui", "extensions", "tests")
SKIP_PARTS = ("window_teleporter" + os.sep + "lib",)


def _python_files():
    yield os.path.join(ROOT, "hariku.py")
    for d in SOURCE_DIRS:
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, d)):
            if any(p in dirpath for p in SKIP_PARTS):
                continue
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(dirpath, f)


def _own_nodes(fn):
    """Walk a function body without descending into nested scopes."""
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.Lambda, ast.ClassDef)):
                stack.append(child)


def _used_before_local_import(tree):
    """Yield (line, name, func) where a name bound by a local import is read first."""
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        imported, first_bind, first_load, declared = set(), {}, {}, set()
        for node in _own_nodes(fn):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    imported.add(name)
                    first_bind[name] = min(first_bind.get(name, node.lineno), node.lineno)
            elif isinstance(node, ast.Name):
                table = first_load if isinstance(node.ctx, ast.Load) else first_bind
                table[node.id] = min(table.get(node.id, node.lineno), node.lineno)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                declared.update(node.names)
        for name in imported - declared:
            if name in first_load and first_load[name] < first_bind[name]:
                yield first_load[name], name, fn.name


def test_no_name_used_before_its_local_import():
    problems = []
    for path in _python_files():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for line, name, func in _used_before_local_import(tree):
            rel = os.path.relpath(path, ROOT)
            problems.append(f"{rel}:{line} '{name}' is read in {func}() before a "
                            f"local import binds it (UnboundLocalError)")
    assert not problems, "\n".join(problems)


def test_main_window_starts_and_saves_settings(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path))
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_startup_check.py")],
        capture_output=True, text=True, timeout=120, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK apply_settings", "OK routines_manage_dialog",
                  "OK routines_log_dialog", "OK shutdown"):
        assert stage in result.stdout, f"startup stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
