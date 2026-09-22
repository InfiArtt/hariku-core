# hariku2/tests/test_updater_security.py
# =============================================================================
# Tests for core.updater security hardening [SEC CRIT-4]:
#   - download URL validation (HTTPS + domain allow-list)
#   - fail-closed installer trust (mandatory SHA256, signature policy)
# These are SECURITY-CRITICAL tests.
# =============================================================================

import os
import hashlib
import tempfile

import pytest

import core.endpoints as ep


class TestValidateUpdateUrl:
    """core.updater._validate_update_url() delegates to endpoints policy."""

    def _validate(self, url):
        from core.updater import _validate_update_url
        return _validate_update_url(url)

    def test_valid_release_installer(self):
        self._validate(ep.RELEASES_BASE + "/latest/download/HarikuSetup.exe")

    def test_valid_pages_manifest(self):
        self._validate(ep.PAGES_BASE + "/update/version.json")

    def test_reject_http(self):
        with pytest.raises(ValueError, match="HTTPS"):
            self._validate((ep.RELEASES_BASE + "/x.exe").replace("https://", "http://"))

    def test_reject_untrusted_domain(self):
        with pytest.raises(ValueError, match="untrusted domain"):
            self._validate("https://evil.com/x.exe")

    def test_reject_wrong_github_repo(self):
        with pytest.raises(ValueError, match="allowed Hariku path"):
            self._validate("https://github.com/attacker/malware/releases/download/x.exe")

    def test_reject_userinfo_smuggling(self):
        with pytest.raises(ValueError, match="untrusted domain"):
            self._validate(f"https://{ep.PAGES_HOST}@evil.com/x.exe")

    def test_reject_empty(self):
        with pytest.raises(ValueError):
            self._validate("")


class TestVerifyInstallerTrust:
    """core.updater._verify_installer_trust() — fail-closed policy."""

    def _make_file(self, data=b"fake installer bytes"):
        fd, path = tempfile.mkstemp(suffix=".exe", prefix="hk_test_")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def _sha256(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()

    def test_missing_sha256_is_rejected(self):
        """No sha256 in the manifest => refuse to run (fail-closed)."""
        from core.updater import _verify_installer_trust
        path = self._make_file()
        try:
            with pytest.raises(ValueError, match="sha256"):
                _verify_installer_trust(path, "")
        finally:
            os.remove(path)

    def test_wrong_sha256_is_rejected(self):
        from core.updater import _verify_installer_trust
        path = self._make_file()
        try:
            with pytest.raises(ValueError, match="[Cc]hecksum"):
                _verify_installer_trust(path, "0" * 64)
        finally:
            os.remove(path)

    def test_correct_sha256_unsigned_passes_when_not_required(self):
        """With REQUIRE_AUTHENTICODE_SIGNATURE False, a correct hash on an
        unsigned file is accepted (does not raise)."""
        import core.updater as up
        path = self._make_file()
        try:
            assert up.REQUIRE_AUTHENTICODE_SIGNATURE is False
            up._verify_installer_trust(path, self._sha256(path))  # must not raise
        finally:
            os.remove(path)

    def test_signature_required_blocks_unsigned(self, monkeypatch):
        """When signatures are mandatory, an unsigned file is refused even with
        a correct hash."""
        import core.updater as up
        monkeypatch.setattr(up, "REQUIRE_AUTHENTICODE_SIGNATURE", True)
        path = self._make_file()
        try:
            with pytest.raises(ValueError, match="signature"):
                up._verify_installer_trust(path, self._sha256(path))
        finally:
            os.remove(path)


class TestVerifyAuthenticode:
    """core.updater._verify_authenticode() — an unsigned file must never be
    reported as valid."""

    def test_unsigned_file_not_valid(self):
        from core.updater import _verify_authenticode
        fd, path = tempfile.mkstemp(suffix=".exe", prefix="hk_unsigned_")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(b"not a real signed PE")
        try:
            assert _verify_authenticode(path) != "valid"
        finally:
            os.remove(path)


class TestAllowedUpdateDomains:
    def test_includes_github(self):
        from core.updater import _ALLOWED_UPDATE_DOMAINS
        assert "github.com" in _ALLOWED_UPDATE_DOMAINS

    def test_includes_pages_host(self):
        from core.updater import _ALLOWED_UPDATE_DOMAINS
        assert ep.PAGES_HOST in _ALLOWED_UPDATE_DOMAINS

    def test_is_frozenset(self):
        from core.updater import _ALLOWED_UPDATE_DOMAINS
        assert isinstance(_ALLOWED_UPDATE_DOMAINS, frozenset)
