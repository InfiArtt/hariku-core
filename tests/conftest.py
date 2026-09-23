# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Shared fixtures and mock setup for the Hariku V2 test suite.
#
# KEY DESIGN DECISION: Several core modules (api.py, reminders.py, updater.py)
# import `wx` at module level. Since tests run headlessly (no GUI), we must
# mock `wx` and other GUI dependencies BEFORE any core module is imported.
#
# This conftest.py runs before any test module, ensuring the mocks are in
# place globally.
# =============================================================================

import sys
import os
import json
import tempfile
import shutil
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# 1. Mock GUI dependencies at sys.modules level
# ---------------------------------------------------------------------------
# These mocks allow us to `import core.api`, `import core.updater`, etc.
# without actually having a wx.App or display.

_wx_mock = MagicMock()
_wx_mock.ID_OK = 5100
_wx_mock.ID_CANCEL = 5101
_wx_mock.ID_APPLY = 5102
_wx_mock.DEFAULT_DIALOG_STYLE = 0
_wx_mock.RESIZE_BORDER = 0
_wx_mock.Dialog = MagicMock
_wx_mock.Panel = MagicMock
_wx_mock.BoxSizer = MagicMock
_wx_mock.VERTICAL = 0
_wx_mock.HORIZONTAL = 1
_wx_mock.CallAfter = lambda fn, *a, **kw: fn(*a, **kw)
_wx_mock.CallLater = MagicMock

sys.modules.setdefault('wx', _wx_mock)
sys.modules.setdefault('wx.adv', MagicMock())
sys.modules.setdefault('wx.html2', MagicMock())

# Mock cytolk (screen reader interface)
sys.modules.setdefault('cytolk', MagicMock())
sys.modules.setdefault('cytolk.tolk', MagicMock())

# Mock pyperclip (clipboard)
sys.modules.setdefault('pyperclip', MagicMock())


# ---------------------------------------------------------------------------
# 2. Ensure hariku2 is on the Python path
# ---------------------------------------------------------------------------
_hariku_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _hariku_root not in sys.path:
    sys.path.insert(0, _hariku_root)


# ---------------------------------------------------------------------------
# 3. Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path):
    """
    Provides a temporary directory that replaces core.api.DATA_DIR.
    Automatically patches and restores the original value.
    """
    import core.api
    original = core.api.DATA_DIR
    core.api.DATA_DIR = str(tmp_path / "data")
    os.makedirs(core.api.DATA_DIR, exist_ok=True)
    yield core.api.DATA_DIR
    core.api.DATA_DIR = original


@pytest.fixture
def fresh_event_bus():
    """
    Provides a fresh EventBus instance (not the global singleton).
    Use this to avoid cross-test pollution.
    """
    from core.events import EventBus
    return EventBus()


@pytest.fixture
def i18n_cache():
    """
    Provides direct access to the i18n language cache for testing.
    Clears it before and after the test.
    """
    from core import i18n
    original_cache = i18n._language_cache.copy()
    i18n._language_cache.clear()
    yield i18n._language_cache
    i18n._language_cache.clear()
    i18n._language_cache.update(original_cache)


@pytest.fixture
def sample_locale_dir(tmp_path):
    """
    Creates a temporary locales directory with sample en.json and id.json files.
    Returns the path to the directory.
    """
    locales = tmp_path / "locales"
    locales.mkdir()

    en_data = {
        "manifest": {
            "language_name": "English",
            "language_code": "en",
            "translator": "Hariku Team",
            "email": "test@test.com",
            "version": "1.0"
        },
        "messages": {
            "greeting": "Hello",
            "hello_name": "Hello, {name}!",
            "farewell": "Goodbye",
            "day_0": "Monday",
            "day_1": "Tuesday",
            "day_2": "Wednesday",
            "day_3": "Thursday",
            "day_4": "Friday",
            "day_5": "Saturday",
            "day_6": "Sunday",
            "month_1": "January",
            "month_7": "July",
            "day_short_0": "Mon",
            "month_short_7": "Jul"
        }
    }

    id_data = {
        "manifest": {
            "language_name": "Bahasa Indonesia",
            "language_code": "id",
            "translator": "Hariku Team",
            "email": "test@test.com",
            "version": "1.0"
        },
        "messages": {
            "greeting": "Halo",
            "hello_name": "Halo, {name}!",
            "day_0": "Senin",
            "month_1": "Januari",
            "month_7": "Juli"
        }
    }

    with open(locales / "en.json", "w", encoding="utf-8") as f:
        json.dump(en_data, f)
    with open(locales / "id.json", "w", encoding="utf-8") as f:
        json.dump(id_data, f)

    return str(locales)


# ---------------------------------------------------------------------------
# Real-window checks
# ---------------------------------------------------------------------------
# These pop up real Hariku windows and dialogs, which steal focus and are
# announced by the screen reader of whoever is using the computer. They run
# only when HARIKU_UI_TESTS=1 is set, as the GitHub Actions workflows do.
# Every tests/test_*_ui.py module counts, plus tests marked @pytest.mark.window.

def pytest_collection_modifyitems(config, items):
    if os.environ.get("HARIKU_UI_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="opens real windows; set HARIKU_UI_TESTS=1 to run (CI does)")
    for item in items:
        module = os.path.basename(str(item.fspath))
        if "window" in item.keywords or (module.startswith("test_") and module.endswith("_ui.py")):
            item.add_marker(skip)
