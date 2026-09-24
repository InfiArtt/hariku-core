# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Opens Preferences and uses the Piper Voices page with real wxPython, in a
# separate process (conftest.py mocks wx here). The catalogue and the
# downloads are fakes: nothing is downloaded, run or played.

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_piper_voices_page(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_piper_voices_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK load", "OK page", "OK browse", "OK download",
                  "OK already_installed", "OK download_declined", "OK cancel_download",
                  "OK remove", "OK refresh", "OK close_while_downloading", "OK teardown",
                  "OK no_errors", "OK shutdown"):
        assert stage in result.stdout, f"stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
    assert "Traceback" not in result.stderr, output
