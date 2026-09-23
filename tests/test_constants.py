# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Tests for core.constants — Version string parsing and constants
# =============================================================================

import re


class TestCoreVersion:
    """Tests for CORE_VERSION and CORE_VERSION_FLOAT."""

    def test_core_version_is_string(self):
        from core.constants import CORE_VERSION
        assert isinstance(CORE_VERSION, str)

    def test_core_version_is_semver(self):
        """CORE_VERSION should match major.minor.patch format."""
        from core.constants import CORE_VERSION
        assert re.match(r"^\d+\.\d+\.\d+$", CORE_VERSION), \
            f"CORE_VERSION '{CORE_VERSION}' does not match semver pattern"

    def test_core_version_float_is_float(self):
        from core.constants import CORE_VERSION_FLOAT
        assert isinstance(CORE_VERSION_FLOAT, float)

    def test_core_version_float_matches_major_minor(self):
        """CORE_VERSION_FLOAT should be major.minor as a float."""
        from core.constants import CORE_VERSION, CORE_VERSION_FLOAT
        parts = CORE_VERSION.split(".")
        expected = float(f"{parts[0]}.{parts[1]}")
        assert CORE_VERSION_FLOAT == expected

    def test_app_name_is_hariku(self):
        from core.constants import APP_NAME
        assert APP_NAME == "Hariku"
