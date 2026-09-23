# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Opens the Sound Themes page in the real Preferences dialog with real wxPython,
# in a separate process (the pytest process mocks wx), through the real
# extension loader, and drives every button; arrow-browsing its lists must never
# move keyboard focus. Playback, file pickers and message boxes are recorded.

import os
import subprocess
import sys

import pytest

# Opens real windows: skipped unless HARIKU_UI_TESTS=1 (it runs in CI).
pytestmark = pytest.mark.window

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_sound_themes_page_works_and_keeps_focus(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_sound_themes_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=240, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK load", "OK hotkey_without_themes", "OK page",
                  "OK new_theme", "OK replace", "OK play", "OK apply", "OK hotkey",
                  "OK duplicate_rename", "OK export_import", "OK reset_delete",
                  "OK preferences_closed", "OK teardown", "OK focus", "OK no_errors",
                  "OK shutdown"):
        assert stage in result.stdout, f"sound themes check stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
    assert "Traceback" not in result.stderr, output
