# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Opens every Finance dialog with real wxPython in a separate process (the pytest
# process mocks wx), through the real extension loader and hotkey actions, and
# checks that arrow-browsing lists and choices never moves keyboard focus.

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_finance_dialogs_open_and_keep_focus(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path))
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_finance_ui_check.py")],
        capture_output=True, text=True, timeout=240, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK load", "OK hotkeys", "OK quick_add", "OK add",
                  "OK edit", "OK filters", "OK budgets", "OK recurring", "OK delete",
                  "OK reminder", "OK teardown", "OK focus", "OK shutdown"):
        assert stage in result.stdout, f"finance check stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
