# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Smoke tests for the Hariku V2 core
# These simply verify that modules can be imported headlessly without crashing,
# which proves that our wx mocks in conftest.py are working correctly.
# =============================================================================

import pytest


def test_import_constants():
    import core.constants
    assert hasattr(core.constants, "CORE_VERSION")


def test_import_events():
    from core.events import bus
    assert bus is not None


def test_import_i18n():
    import core.i18n
    assert callable(core.i18n.get_translator)


def test_import_store():
    import core.store
    assert callable(core.store.check_for_updates)


def test_import_api():
    """Importing api.py should not crash headlessly (thanks to conftest.py)."""
    import core.api
    assert callable(core.api.get_storage_dir)


def test_import_reminders():
    """Importing reminders.py should not crash headlessly."""
    import core.reminders
    assert callable(core.reminders.add_reminder)


def test_import_updater():
    """Importing updater.py should not crash headlessly."""
    import core.updater
    assert callable(core.updater.check_for_updates)


def test_import_extension_manager():
    """Importing extension_manager.py should not crash headlessly."""
    import core.extension_manager
    assert hasattr(core.extension_manager, "LOADED_EXTENSIONS")


def test_i18n_can_load_bundled_locales():
    """Verify that the real bundled en.json can be loaded."""
    import os
    import core.i18n
    
    # Path to real locales folder
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locales_dir = os.path.join(base_dir, "locales")
    
    if os.path.exists(locales_dir):
        core.i18n._load_domain("core", locales_dir)
        assert "en" in core.i18n._language_cache.get("core", {})
