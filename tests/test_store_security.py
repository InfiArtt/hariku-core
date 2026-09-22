# hariku2/tests/test_store_security.py
# =============================================================================
# Tests for core.store extension-id sanitization [SEC MED-5].
# A spoofed/compromised registry must not be able to steer a download to an
# arbitrary path via a malicious "id" field.
# =============================================================================

import os

import pytest

import core.endpoints as ep


class TestSanitizeExtId:
    def _san(self, v):
        from core.store import _sanitize_ext_id
        return _sanitize_ext_id(v)

    def test_plain_id_kept(self):
        assert self._san("markdown_reader") == "markdown_reader"

    def test_hyphen_and_digits_kept(self):
        assert self._san("my-ext-2") == "my-ext-2"

    def test_path_separators_removed(self):
        result = self._san("../../Startup/evil")
        assert "/" not in result and "\\" not in result
        assert ".." not in result

    def test_backslash_traversal_removed(self):
        result = self._san(r"..\..\Windows\System32\evil")
        assert "\\" not in result and ".." not in result

    def test_dots_only_becomes_empty(self):
        assert self._san("..") == ""
        assert self._san("...") == ""

    def test_non_string_handled(self):
        # Must not raise on unexpected types from a spoofed registry.
        assert isinstance(self._san(None), str)


class TestDownloadExtensionRejectsBadId:
    def test_traversal_id_never_writes_outside(self, monkeypatch, tmp_path):
        """download_extension with an id that sanitizes to empty returns False
        and performs no download."""
        import core.store as store
        import core.extension_manager as em

        monkeypatch.setattr(em, "USER_EXTENSIONS_DIR", str(tmp_path))

        called = {"downloaded": False}

        def _boom(*a, **kw):
            called["downloaded"] = True
            raise AssertionError("network download must not happen")

        monkeypatch.setattr(store.urllib.request, "urlopen", _boom)

        # Valid URL, but the id sanitizes to empty -> must return False and never download.
        ok = store.download_extension("..", ep.PAGES_BASE + "/dl/x.hrk")
        assert ok is False
        assert called["downloaded"] is False

    def test_bad_url_rejected_before_download(self, monkeypatch, tmp_path):
        import core.store as store
        import core.extension_manager as em
        monkeypatch.setattr(em, "USER_EXTENSIONS_DIR", str(tmp_path))
        ok = store.download_extension("good_id", "http://evil.com/x.hrk")
        assert ok is False
