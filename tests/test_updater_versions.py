# hariku2/tests/test_updater_versions.py
# =============================================================================
# Tests for core.updater — Version comparison logic
# These test the pure helper functions, NOT the wx dialogs.
# =============================================================================

import pytest


class TestParseVersion:
    """Tests for updater._parse_version()"""

    def _parse(self, v):
        from core.updater import _parse_version
        return _parse_version(v)

    def test_three_part(self):
        assert self._parse("2.1.3") == (2, 1, 3)

    def test_two_part(self):
        assert self._parse("2.0") == (2, 0)

    def test_single_part(self):
        assert self._parse("5") == (5,)

    def test_invalid_returns_zero(self):
        assert self._parse("abc") == (0,)

    def test_empty_string_returns_zero(self):
        assert self._parse("") == (0,)

    def test_spaces_stripped(self):
        assert self._parse("  2.1.0  ") == (2, 1, 0)

    def test_numeric_input(self):
        """Should handle numeric input by converting to string first."""
        assert self._parse(2.0) == (2, 0)


class TestIsNewer:
    """Tests for updater._is_newer()"""

    def _is_newer(self, server, local):
        from core.updater import _is_newer
        return _is_newer(server, local)

    def test_newer_major(self):
        assert self._is_newer("3.0.0", "2.0.0") is True

    def test_newer_minor(self):
        assert self._is_newer("2.1.0", "2.0.0") is True

    def test_newer_patch(self):
        assert self._is_newer("2.0.1", "2.0.0") is True

    def test_same_version(self):
        assert self._is_newer("2.0.0", "2.0.0") is False

    def test_older_version(self):
        assert self._is_newer("1.9.9", "2.0.0") is False

    def test_patch_10_vs_9(self):
        """2.0.10 should be newer than 2.0.9 (not float comparison!)"""
        assert self._is_newer("2.0.10", "2.0.9") is True

    def test_different_length_versions(self):
        """'2.1' vs '2.0.5' — 2.1 should be newer."""
        assert self._is_newer("2.1", "2.0.5") is True


class TestIsBelowMinimum:
    """Tests for updater._is_below_minimum()"""

    def _below(self, local, minimum):
        from core.updater import _is_below_minimum
        return _is_below_minimum(local, minimum)

    def test_below(self):
        assert self._below("1.9.0", "2.0.0") is True

    def test_at_minimum(self):
        assert self._below("2.0.0", "2.0.0") is False

    def test_above_minimum(self):
        assert self._below("2.1.0", "2.0.0") is False

    def test_way_below(self):
        assert self._below("1.0.0", "2.5.0") is True
