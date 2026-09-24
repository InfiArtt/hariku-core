# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Preferences pages: built once the page list settles, the rest in the
# background, focus untouched. Real wxPython in a separate process
# (conftest.py mocks wx here).

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_preferences_pages_build_without_slowing_the_list(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_preferences_pages_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK opened", "OK settled page built", "OK tab builds at once",
                  "OK background", "OK shutdown"):
        assert stage in result.stdout, f"stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
