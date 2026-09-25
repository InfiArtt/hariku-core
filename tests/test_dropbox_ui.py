# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The Dropbox extension with real wxPython: its Preferences page and Aruna's
# "Dropbox status" and "copy link", in a separate process (conftest.py mocks
# wx here). Only in CI: conftest.py skips *_ui.py tests unless
# HARIKU_UI_TESTS=1, because real windows steal focus on a desktop. Dropbox,
# File Explorer and the clipboard are fakes; nothing leaves the computer; data
# goes to a temporary APPDATA.

import os
import subprocess
import sys

import pytest

# Opens real windows: skipped unless HARIKU_UI_TESTS=1 (CI sets it).
pytestmark = pytest.mark.window

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_dropbox_windows(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_dropbox_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=200, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK load", "OK page_not_set_up", "OK page_connected",
                  "OK page_code", "OK apply", "OK disconnect", "OK aruna_status",
                  "OK aruna_copy_link", "OK teardown", "OK no_errors", "OK shutdown"):
        assert stage in result.stdout, f"stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
    assert "Traceback" not in result.stderr, output
