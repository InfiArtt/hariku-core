# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Tests for core.i18n — Translation engine
# =============================================================================

import pytest
import datetime


class TestTranslate:
    """Tests for the _translate() internal function."""

    def test_translate_existing_key(self, i18n_cache, sample_locale_dir):
        """Should return the translated string for a known key."""
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        i18n._current_language = "en"
        result = i18n._translate("test", "greeting")
        assert result == "Hello"

    def test_translate_with_placeholder(self, i18n_cache, sample_locale_dir):
        """Should substitute {name} in the translation string."""
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        i18n._current_language = "en"
        result = i18n._translate("test", "hello_name", name="Rafli")
        assert result == "Hello, Rafli!"

    def test_translate_missing_key_returns_key(self, i18n_cache, sample_locale_dir):
        """Missing keys should return the key itself as fallback."""
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        i18n._current_language = "en"
        result = i18n._translate("test", "nonexistent_key")
        assert result == "nonexistent_key"

    def test_translate_missing_key_with_default(self, i18n_cache, sample_locale_dir):
        """Missing keys should return the 'default' kwarg if provided."""
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        i18n._current_language = "en"
        result = i18n._translate("test", "nonexistent_key", default="Fallback Text")
        assert result == "Fallback Text"

    def test_translate_fallback_to_english(self, i18n_cache, sample_locale_dir):
        """If key missing in current language, should fall back to English."""
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        i18n._current_language = "id"
        i18n._fallback_language = "en"
        # "farewell" exists in en but not in id
        result = i18n._translate("test", "farewell")
        assert result == "Goodbye"

    def test_translate_uses_current_language_first(self, i18n_cache, sample_locale_dir):
        """Should prefer current language over fallback."""
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        i18n._current_language = "id"
        i18n._fallback_language = "en"
        result = i18n._translate("test", "greeting")
        assert result == "Halo"  # Indonesian, not English

    def test_translate_bad_format_returns_unformatted(self, i18n_cache, sample_locale_dir):
        """If format kwargs don't match, return the raw string without crashing."""
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        i18n._current_language = "en"
        # "hello_name" expects {name}, but we pass {wrong_key}
        result = i18n._translate("test", "hello_name", wrong_key="oops")
        assert result == "Hello, {name}!"  # Should return unformatted


class TestGetTranslator:
    """Tests for get_translator() — the public API."""

    def test_returns_callable(self, i18n_cache, sample_locale_dir):
        from core.i18n import get_translator
        _ = get_translator("test", sample_locale_dir)
        assert callable(_)

    def test_translator_translates(self, i18n_cache, sample_locale_dir):
        from core import i18n
        i18n._current_language = "en"
        _ = i18n.get_translator("test", sample_locale_dir)
        assert _("greeting") == "Hello"

    def test_translator_with_kwargs(self, i18n_cache, sample_locale_dir):
        from core import i18n
        i18n._current_language = "en"
        _ = i18n.get_translator("test", sample_locale_dir)
        assert _("hello_name", name="World") == "Hello, World!"

    def test_translator_unknown_domain_returns_key(self, i18n_cache):
        """A translator for a domain with no locales should return the key itself."""
        from core.i18n import get_translator
        _ = get_translator("nonexistent_domain")
        assert _("any_key") == "any_key"


class TestGetAvailableLanguages:
    """Tests for get_available_languages()."""

    def test_returns_list(self, i18n_cache, sample_locale_dir):
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        langs = i18n.get_available_languages("test")
        assert isinstance(langs, list)

    def test_lists_loaded_languages(self, i18n_cache, sample_locale_dir):
        from core import i18n
        i18n._load_domain("test", sample_locale_dir)
        langs = i18n.get_available_languages("test")
        codes = [l["language_code"] for l in langs]
        assert "en" in codes
        assert "id" in codes

    def test_current_language_sorted_first(self, i18n_cache, sample_locale_dir):
        """The current language should appear first in the list."""
        from core import i18n
        i18n._current_language = "id"
        i18n._load_domain("test", sample_locale_dir)
        langs = i18n.get_available_languages("test")
        assert langs[0]["language_code"] == "id"

    def test_empty_domain_returns_empty_list(self, i18n_cache):
        from core.i18n import get_available_languages
        result = get_available_languages("nobody_loaded_this")
        assert result == []


class TestLoadDomain:
    """Tests for _load_domain() — locale file loading."""

    def test_loads_valid_json(self, i18n_cache, sample_locale_dir):
        from core import i18n
        i18n._load_domain("test_load", sample_locale_dir)
        assert "en" in i18n._language_cache.get("test_load", {})

    def test_skips_invalid_json(self, i18n_cache, tmp_path):
        """Malformed JSON files should be skipped without crashing."""
        from core import i18n
        locales = tmp_path / "bad_locales"
        locales.mkdir()
        (locales / "broken.json").write_text("NOT VALID JSON {{{")
        i18n._load_domain("bad_test", str(locales))
        # Should not crash, and the domain should be empty or only have valid files
        assert "bad_test" in i18n._language_cache

    def test_skips_missing_manifest(self, i18n_cache, tmp_path):
        """JSON files without manifest/messages blocks should be skipped."""
        import json
        from core import i18n
        locales = tmp_path / "incomplete"
        locales.mkdir()
        (locales / "incomplete.json").write_text(json.dumps({"only_messages": {}}))
        i18n._load_domain("incomplete_test", str(locales))
        assert len(i18n._language_cache.get("incomplete_test", {})) == 0

    def test_nonexistent_dir_no_crash(self, i18n_cache):
        """Loading from a non-existent directory should not crash."""
        from core import i18n
        i18n._load_domain("ghost", "/nonexistent/path/does/not/exist")


class TestFormatDate:
    """Tests for format_date() — date formatting using translations."""

    def test_format_with_datetime_date(self, i18n_cache, sample_locale_dir):
        """Should format a standard datetime.date object."""
        from core import i18n
        i18n._current_language = "en"
        i18n._load_domain("core", sample_locale_dir)
        dt = datetime.date(2026, 7, 12)  # Saturday
        result = i18n.format_date(dt, "%d %B %Y")
        assert "12" in result
        assert "July" in result
        assert "2026" in result

    def test_format_day_name(self, i18n_cache, sample_locale_dir):
        """Should resolve %A to the translated day name."""
        from core import i18n
        i18n._current_language = "en"
        i18n._load_domain("core", sample_locale_dir)
        dt = datetime.date(2026, 7, 13)  # Monday
        result = i18n.format_date(dt, "%A")
        assert result == "Monday"

    def test_format_numbers(self, i18n_cache, sample_locale_dir):
        """%d, %m, %Y should be zero-padded numbers."""
        from core import i18n
        i18n._current_language = "en"
        i18n._load_domain("core", sample_locale_dir)
        dt = datetime.date(2026, 1, 5)
        result = i18n.format_date(dt, "%d/%m/%Y")
        assert result == "05/01/2026"
