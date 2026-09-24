# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Every input control on every Preferences page must come right after its
# label, or screen readers read the wrong label. Real wxPython, in a separate
# process (conftest.py mocks wx here).

import os
import subprocess
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_preferences_labels_precede_their_controls(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_label_order_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=240, env=env,
    )
    output = result.stdout + result.stderr
    timings = [line for line in result.stdout.splitlines() if line.startswith("TIMING")]
    if timings:
        # Shown in pytest's warnings summary, so CI logs keep them on success.
        warnings.warn("Preferences build times:
" + "
".join(timings[:25]))
    problems = [line for line in result.stdout.splitlines() if line.startswith("PROBLEM")]
    assert not problems, "\n".join(problems) + "\n\n" + output
    assert "OK labels" in result.stdout, output
    assert result.returncode == 0, output
