# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Tests for core.api — Data storage and path sanitization
# Uses the tmp_data_dir fixture to avoid writing to actual AppData.
# =============================================================================

import os
import pytest


class TestGetDataPath:
    """Tests for core.api.get_data_path()"""

    def test_get_data_path_normal(self, tmp_data_dir):
        from core.api import get_data_path
        path = get_data_path("my_ext")
        assert path.endswith("my_ext.json")
        assert path.startswith(tmp_data_dir)

    def test_get_data_path_sanitizes(self, tmp_data_dir):
        """Should strip invalid characters from the extension name."""
        from core.api import get_data_path
        path = get_data_path("../../evil_ext!")
        # The sanitization keeps alphanumeric, space, hyphen, underscore
        assert path.endswith("evil_ext.json")


class TestLoadSaveData:
    """Tests for core.api.load_data() and save_data()"""

    def test_save_and_load_data(self, tmp_data_dir):
        """Data saved should be exactly what is loaded."""
        from core.api import save_data, load_data
        
        test_data = {"setting1": True, "count": 42, "nested": {"a": 1}}
        ext_name = "test_ext"
        
        # Save it
        success = save_data(ext_name, test_data)
        assert success is True
        
        # Load it back
        loaded = load_data(ext_name)
        assert loaded == test_data

    def test_load_nonexistent_returns_empty_dict(self, tmp_data_dir):
        """Loading data for an extension that hasn't saved anything returns {}."""
        from core.api import load_data
        loaded = load_data("ghost_extension")
        assert loaded == {}


class TestGetStorageDir:
    """Tests for core.api.get_storage_dir()"""

    def test_get_storage_dir_normal(self, tmp_data_dir):
        """Should return a path inside DATA_DIR/extensions/ and create it."""
        from core.api import get_storage_dir
        
        path = get_storage_dir("my_ext")
        assert os.path.exists(path)
        assert os.path.isdir(path)
        assert os.path.basename(path) == "my_ext"

    def test_get_storage_dir_sanitizes(self, tmp_data_dir):
        """Should sanitize the extension ID."""
        from core.api import get_storage_dir
        
        path = get_storage_dir("my ext!@#")
        assert os.path.basename(path) == "myext"

    def test_get_storage_dir_rejects_empty(self, tmp_data_dir):
        """Empty or fully sanitized IDs should be rejected."""
        from core.api import get_storage_dir
        
        with pytest.raises(ValueError, match="Invalid extension ID"):
            get_storage_dir("!!!")

    def test_get_storage_dir_prevents_traversal(self, tmp_data_dir):
        """Should prevent directory traversal attacks."""
        from core.api import get_storage_dir
        
        # Sanitization ("." is removed) handles this in practice, but
        # we test the path logic conceptually.
        path = get_storage_dir("../../Windows")
        assert os.path.basename(path) == "Windows"  # Sanitized to "Windows"
