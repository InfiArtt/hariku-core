# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""The StaticText override never names a dialog's OK or Cancel button after
the note above it, with real wxPython (tests/_dialog_button_names_check.py)."""
import os
import subprocess
import sys

import pytest

# Opens real windows: skipped unless HARIKU_UI_TESTS=1 (CI sets it).
pytestmark = pytest.mark.window

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_dialog_buttons_keep_their_own_names(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_dialog_button_names_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK plain_dialog", "OK place_dialog"):
        assert stage in result.stdout, f"stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
