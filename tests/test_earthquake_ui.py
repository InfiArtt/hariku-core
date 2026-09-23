# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Opens the Earthquakes & Tsunami windows with real wxPython, in a separate
# process (conftest.py mocks wx here). Network access is stubbed there.

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_earthquake_windows(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_earthquake_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK load", "OK latest_action", "OK tsunami_alert",
                  "OK panel_browse", "OK panel_apply", "OK recent_action", "OK list_dialog",
                  "OK nearby_alert", "OK world_alert", "OK briefing", "OK teardown",
                  "OK no_errors", "OK shutdown"):
        assert stage in result.stdout, f"stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
    assert "Traceback" not in result.stderr, output
