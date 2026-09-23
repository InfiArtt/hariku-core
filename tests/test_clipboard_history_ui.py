# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Opens the Clipboard History windows with real wxPython in a separate process
# (conftest.py mocks wx here), through the real extension loader and hotkeys.
# The clipboard itself is faked there, so the user's clipboard is never touched.

import os
import subprocess
import sys

import pytest

# Opens real windows: skipped unless HARIKU_UI_TESTS=1 (CI sets it).
pytestmark = pytest.mark.window

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_clipboard_history_windows(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_clipboard_history_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=240, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK load", "OK guard", "OK record", "OK speak_last",
                  "OK hotkey", "OK escape", "OK browse", "OK filter", "OK pin",
                  "OK delete_clear", "OK copy", "OK settings", "OK teardown",
                  "OK no_errors", "OK focus", "OK shutdown"):
        assert stage in result.stdout, f"stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
    assert "Traceback" not in result.stderr, output
