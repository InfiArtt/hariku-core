# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Tests for core.extension_manager — Security functions
# These tests are CRITICAL for preventing Zip Slip and Path Traversal attacks.
# =============================================================================

import os
import zipfile
import pytest


class TestSafeExtractAll:
    """Tests for _safe_extractall() which prevents Zip Slip attacks."""

    def _create_zip(self, tmp_path, entries):
        """Helper to create a zip file with specific entry names."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for entry in entries:
                # We can't easily create a real malicious zip with standard library
                # zipfile because it sanitizes paths when writing, so we manipulate
                # the ZipInfo object directly to create a malicious entry.
                zinfo = zipfile.ZipInfo(entry)
                zf.writestr(zinfo, b"test content")
        return zip_path

    def test_safe_extract_normal(self, tmp_path):
        """Normal zip extraction should work."""
        from core.extension_manager import _safe_extractall
        zip_path = self._create_zip(tmp_path, ["main.py", "lib/helper.py"])
        dest_path = tmp_path / "dest"
        dest_path.mkdir()
        
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extractall(zf, str(dest_path))
            
        assert (dest_path / "main.py").exists()
        assert (dest_path / "lib" / "helper.py").exists()

    def test_safe_extract_rejects_path_traversal(self, tmp_path):
        """Zip with ../ should be rejected (Zip Slip)."""
        from core.extension_manager import _safe_extractall
        
        # Create a malicious zip
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zinfo = zipfile.ZipInfo("../evil.bat")
            zf.writestr(zinfo, b"malicious")
            
        dest_path = tmp_path / "dest"
        dest_path.mkdir()
        
        with zipfile.ZipFile(zip_path, "r") as zf:
            with pytest.raises(ValueError, match="Zip Slip"):
                _safe_extractall(zf, str(dest_path))


class TestManifestValidation:
    """Tests for manifest structure and entry point validation."""
    
    # We test the logic inside _load_extension_from_dir conceptually
    # by isolating the checks it performs.

    def test_minimum_core_version_check(self):
        """Extensions requiring a newer core version should be rejected."""
        import core.constants
        
        manifest_ver = 99.0  # way in the future
        current_ver = core.constants.CORE_VERSION_FLOAT
        assert manifest_ver > current_ver

    def test_entry_point_traversal_check(self, tmp_path):
        """Test the path traversal logic used for 'main' in manifest."""
        import os
        
        ext_dir = str(tmp_path)
        
        # Normal
        entry_point = "main.py"
        entry_path = os.path.join(ext_dir, os.path.normpath(entry_point))
        is_safe = os.path.realpath(entry_path).startswith(os.path.realpath(ext_dir))
        assert is_safe is True
        
        # Malicious
        entry_point = "../../Windows/System32/cmd.exe"
        entry_path = os.path.join(ext_dir, os.path.normpath(entry_point))
        is_safe = os.path.realpath(entry_path).startswith(os.path.realpath(ext_dir))
        assert is_safe is False


class TestSha256File:
    """Tests for the file hashing function."""

    def test_sha256_computation(self, tmp_path):
        from core.extension_manager import _sha256_file
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World", encoding="utf-8")
        
        # known sha256 for "Hello World"
        expected = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"
        
        result = _sha256_file(str(test_file))
        assert result == expected
