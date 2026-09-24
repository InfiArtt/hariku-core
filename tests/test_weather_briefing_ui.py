# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Opens the Weather and Morning Briefing windows with real wxPython, in a
# separate process (conftest.py mocks wx here). Network access is stubbed there.

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_weather_and_briefing_windows(tmp_path):
    env = dict(os.environ, APPDATA=str(tmp_path), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_weather_briefing_ui_check.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, env=env,
    )
    output = result.stdout + result.stderr
    for stage in ("OK main_window", "OK load_extensions", "OK weather_no_city_hint",
                  "OK weather_panel_browse", "OK weather_panel_apply",
                  "OK weather_places_changed", "OK weather_actions",
                  "OK weather_forecast_browse", "OK briefing_action", "OK briefing_evening",
                  "OK briefing_evening_settings", "OK briefing_evening_auto", "OK briefing_auto",
                  "OK teardown", "OK no_errors", "OK shutdown"):
        assert stage in result.stdout, f"stage failed: {stage}\n{output}"
    assert result.returncode == 0, output
    assert "Traceback" not in result.stderr, output
