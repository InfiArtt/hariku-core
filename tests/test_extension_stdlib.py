# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Released Hariku is a Nuitka build, which only contains the modules the core
# imports. Extensions are loaded from outside the build at runtime, so a module
# that only an extension imports (zoneinfo for World Clock, for example) is
# missing for every installed user while working fine from source. Every module
# an extension imports must be imported by the core, listed in
# core/stdlib_includes.py, built into Python, or shipped with the extension.

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_ROOT = os.path.join(ROOT, "extensions")
HARIKU_PACKAGES = {"core", "ui"}


def _py_files(*dirs):
    for d in dirs:
        for dirpath, _dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(dirpath, f)


def _imported_modules(path):
    """Yield (dotted module name, line) for every absolute import in a file."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module, node.lineno


def _modules_in_build():
    """Modules the core imports, plus their parent packages (importing
    importlib.util also puts importlib in the build)."""
    files = [os.path.join(ROOT, "hariku.py")]
    files += _py_files(os.path.join(ROOT, "core"), os.path.join(ROOT, "ui"))
    modules = set()
    for path in files:
        for mod, _ in _imported_modules(path):
            parts = mod.split(".")
            modules.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return modules


def _local_names(ext_dir):
    """Top-level names an extension ships itself (its own files and lib/)."""
    names = set()
    for d in (ext_dir, os.path.join(ext_dir, "lib")):
        if os.path.isdir(d):
            for entry in os.listdir(d):
                names.add(entry[:-3] if entry.endswith(".py") else entry)
    return names


def test_extension_imports_exist_in_the_compiled_app():
    in_build = _modules_in_build()
    missing = []
    for ext_id in sorted(os.listdir(EXT_ROOT)):
        ext_dir = os.path.join(EXT_ROOT, ext_id)
        if not os.path.isfile(os.path.join(ext_dir, "manifest.json")):
            continue
        local = _local_names(ext_dir)
        lib_dir = os.path.join(ext_dir, "lib")
        for path in _py_files(ext_dir):
            if path.startswith(lib_dir + os.sep):
                continue  # vendored libraries resolve their own imports
            for mod, line in _imported_modules(path):
                top = mod.split(".")[0]
                if (mod in in_build or top in HARIKU_PACKAGES or top in local
                        or top in sys.builtin_module_names):
                    continue
                rel = os.path.relpath(path, ROOT)
                missing.append(f"{rel}:{line} imports '{mod}', which the compiled app does "
                               f"not include (add it to core/stdlib_includes.py or ship it in lib/)")
    assert not missing, "\n".join(missing)
