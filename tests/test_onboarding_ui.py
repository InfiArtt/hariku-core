# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Walks the welcome (core 2.10) with real wxPython, in a separate process
# (conftest.py mocks wx here): every page, labels before controls, focus on
# page changes, the personal texts, Finish saving everything and the
# downloads, the prefilled second run, and Cancel. Open-Meteo, the store,
# sounds and the Windows autostart are replaced there, so nothing leaves the
# machine and nothing plays.

import os
import subprocess
import sys

import pytest

# Opens real windows: skipped unless HARIKU_UI_TESTS=1 (CI sets it).
pytestmark = pytest.mark.window

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_welcome(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_onboarding_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=220, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK opened", "OK language", "OK name", "OK where", "OK birthday",
                  "OK aruna", "OK extensions", "OK startup", "OK done", "OK finish",
                  "OK rerun_prefilled", "OK rerun_cancel", "OK first_run_cancel",
                  "OK no_errors", "OK shutdown"):
        assert stage in result.stdout, f"stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
    assert "Traceback" not in result.stderr, output
