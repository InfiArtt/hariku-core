# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The Developer SDK: what tools/build_sdk.py puts in the ZIP, and the template
# extension's license (MIT, so developers can copy it into any extension).

import importlib.util
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "template_extension")


def _build_sdk_module():
    spec = importlib.util.spec_from_file_location(
        "build_sdk_under_test", os.path.join(ROOT, "tools", "build_sdk.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_sdk_zip_never_has_the_review_guidelines(tmp_path):
    assert os.path.isfile(os.path.join(ROOT, "docs", "en", "extension_store",
                                       "review_guidelines.txt"))
    out = _build_sdk_module().build_sdk(str(tmp_path / "sdk.zip"))
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert not [n for n in names if "review_guidelines" in n]
    assert "store_guidelines/submission_guide.txt" in names
    assert "DEVELOPERS.md" in names and "tools/packager.py" in names
    assert "template_extension/manifest.json" in names
    assert "template_extension/LICENSE" in names
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]


def test_build_sdk_points_to_the_sdk_repository():
    module = _build_sdk_module()
    assert module.SDK_REPOSITORY == "https://github.com/InfiArtt/hariku-sdk"
    assert module.SDK_REPOSITORY in module.__doc__


def test_the_template_is_mit_licensed():
    # The template is meant to be copied into extensions under any license,
    # so it is MIT, not GPL (its owner relicensed it for the SDK).
    with open(os.path.join(TEMPLATE, "LICENSE"), encoding="utf-8") as f:
        text = f.read()
    assert "MIT License" in text and "any license" in text
    for name in os.listdir(TEMPLATE):
        if name.endswith(".py"):
            with open(os.path.join(TEMPLATE, name), encoding="utf-8") as f:
                head = f.read(800)
            assert "SPDX-License-Identifier: MIT" in head, name
            assert "SPDX-License-Identifier: GPL" not in head, name


def test_the_template_is_a_complete_extension():
    with open(os.path.join(TEMPLATE, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    import core.extension_manager as manager
    assert all(field in manifest for field in manager._REQUIRED_MANIFEST_FIELDS)
    with open(os.path.join(TEMPLATE, manifest["main"]), encoding="utf-8") as f:
        source = f.read()
    compile(source, "main.py", "exec")
    assert "\ndef register(bus):" in source and "\ndef teardown():" in source
