# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Tests for core.store URL validation — now host- AND path-pinned to our own
# GitHub Pages / Releases base URLs (see core.endpoints). SECURITY-CRITICAL.
# URLs are built from the endpoints constants so they stay correct regardless of
# the configured GITHUB_OWNER / GITHUB_REPO.
# =============================================================================

import pytest
from packaging.version import Version

import core.endpoints as ep

PAGES_URL = ep.PAGES_BASE + "/dl/my_ext.hrk"
RELEASE_URL = ep.RELEASES_BASE + "/download/v2.0/my_ext.hrk"


class TestValidateDownloadUrl:
    """core.store._validate_download_url() delegates to endpoints policy."""

    def _validate(self, url):
        from core.store import _validate_download_url
        return _validate_download_url(url)

    def test_valid_pages_url(self):
        """A JSON/asset URL under our GitHub Pages base should pass."""
        self._validate(PAGES_URL)

    def test_valid_release_url(self):
        """A binary under our GitHub Releases base should pass."""
        self._validate(RELEASE_URL)

    def test_reject_http(self):
        with pytest.raises(ValueError, match="HTTPS"):
            self._validate(PAGES_URL.replace("https://", "http://"))

    def test_reject_file_protocol(self):
        with pytest.raises(ValueError, match="file://"):
            self._validate("file:///C:/Windows/System32/cmd.exe")

    def test_reject_ftp_protocol(self):
        with pytest.raises(ValueError, match="HTTPS"):
            self._validate("ftp://evil.com/test.hrk")

    def test_reject_untrusted_domain(self):
        with pytest.raises(ValueError, match="untrusted domain"):
            self._validate("https://evil.com/malware.hrk")

    def test_reject_lookalike_pages_domain(self):
        with pytest.raises(ValueError, match="untrusted domain"):
            self._validate(f"https://{ep.PAGES_HOST}.evil.com/x.hrk")

    def test_reject_wrong_github_repo(self):
        """github.com host is shared: a different repo must be rejected by the
        path pin even though the host matches."""
        with pytest.raises(ValueError, match="allowed Hariku path"):
            self._validate("https://github.com/attacker/malware/releases/download/x.hrk")

    def test_reject_path_traversal(self):
        with pytest.raises(ValueError, match="traversal"):
            self._validate(ep.RELEASES_BASE + "/download/../../../etc/passwd")

    def test_empty_url_rejected(self):
        with pytest.raises((ValueError, Exception)):
            self._validate("")

    def test_no_scheme_rejected(self):
        with pytest.raises((ValueError, Exception)):
            self._validate("github.io/test.hrk")


class TestParseVersion:
    """Tests for core.store._parse_version()"""

    def _parse(self, v):
        from core.store import _parse_version
        return _parse_version(v)

    def test_normal_version(self):
        assert self._parse("1.0.0") == Version("1.0.0")

    def test_two_part_version(self):
        assert self._parse("2.1") == Version("2.1")

    def test_invalid_version_returns_zero(self):
        assert self._parse("not_a_version") == Version("0")

    def test_compare_newer(self):
        assert self._parse("2.1.0") > self._parse("2.0.0")

    def test_compare_patch_correctly(self):
        assert self._parse("2.0.10") > self._parse("2.0.9")

    def test_compare_equal(self):
        assert self._parse("1.5.0") == self._parse("1.5.0")


class TestAllowedDomains:
    """Tests for the download host allow-list."""

    def test_whitelist_contains_pages_host(self):
        from core.store import _ALLOWED_DOWNLOAD_DOMAINS
        assert ep.PAGES_HOST in _ALLOWED_DOWNLOAD_DOMAINS

    def test_whitelist_contains_github(self):
        from core.store import _ALLOWED_DOWNLOAD_DOMAINS
        assert "github.com" in _ALLOWED_DOWNLOAD_DOMAINS

    def test_whitelist_is_frozenset(self):
        from core.store import _ALLOWED_DOWNLOAD_DOMAINS
        assert isinstance(_ALLOWED_DOWNLOAD_DOMAINS, frozenset)
