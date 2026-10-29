# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Core 2.13 security fixes, each tested with the attack that found it:
- a .hrk named like an official extension ("weather.hrk") loaded unchecked;
- "...hrk" removed the whole extensions folder;
- an extension taken off the trusted list stayed trusted while offline;
- a small zip could unpack to any size;
- a store id "weather." replaced the official Weather;
- a cut-off store download replaced the working extension;
- "%2e%2e" in a download path passed the path check.
"""
import io
import os
import time
import zipfile

import pytest

import core.endpoints
import core.extension_manager as em
import core.store as store


def make_hrk(path, ext_id="demo", main="def register(bus):\n    pass\n", extra=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", (
            '{"id": "%s", "name": "%s", "version": "1.0", "description": "d", "main": "main.py",'
            ' "author": "someone", "language": "en", "minimum_core_version": "2.0"}' % (ext_id, ext_id)))
        z.writestr("main.py", main)
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return str(path)


@pytest.fixture
def ext_dir(tmp_path, tmp_data_dir, monkeypatch):
    folder = tmp_path / "extensions"
    folder.mkdir()
    for name in ("USER_EXTENSIONS_DIR", "EXTENSIONS_DIR"):
        monkeypatch.setattr(em, name, str(folder))
    monkeypatch.setattr(em, "SYSTEM_EXTENSIONS_DIR", str(tmp_path / "no_system"))
    monkeypatch.setattr(em, "_trusted_hash_cache", None)
    monkeypatch.setattr(em, "_trust_list_current", False)
    monkeypatch.setattr(em, "_consented_hashes", set())
    monkeypatch.setattr(em, "_file_hashes", None)
    monkeypatch.setattr(em, "LOADED_EXTENSIONS", {})
    monkeypatch.setattr(em, "LOAD_ERRORS", {})
    monkeypatch.setattr(em, "TRUST_REFRESH_DELAY_SECONDS", 0)
    monkeypatch.setattr(em.threading, "Thread",
                        lambda target, **kw: type("T", (), {"start": lambda self: None})())
    return folder


def offline():
    raise OSError("no network")


# ------------------------------------------------------------
# An official id is not enough
# ------------------------------------------------------------

def test_an_official_name_does_not_skip_the_hash_check(ext_dir, monkeypatch):
    hrk = make_hrk(ext_dir / "weather.hrk", "weather")
    monkeypatch.setattr(em, "_download_trusted_hashes", lambda: {"0" * 64})
    asked = []
    monkeypatch.setattr(em, "_show_security_dialog", lambda msg, title: asked.append(msg) or False)
    assert "weather" in em._OFFICIAL_EXTENSION_IDS
    assert em._check_hrk_trust(hrk, "weather") is False
    assert asked and "weather" in asked[0]


def test_a_listed_official_extension_loads_without_asking(ext_dir, monkeypatch):
    hrk = make_hrk(ext_dir / "weather.hrk", "weather")
    monkeypatch.setattr(em, "_download_trusted_hashes", lambda: {em._sha256_file(hrk)})
    monkeypatch.setattr(em, "_show_security_dialog", lambda *a: pytest.fail("asked"))
    assert em._check_hrk_trust(hrk, "weather") is True


def test_offline_with_no_list_official_ids_still_load(ext_dir, monkeypatch):
    weather = make_hrk(ext_dir / "weather.hrk", "weather")
    other = make_hrk(ext_dir / "someones.hrk", "someones")
    monkeypatch.setattr(em, "_download_trusted_hashes", offline)
    asked = []
    monkeypatch.setattr(em, "_show_security_dialog", lambda msg, title: asked.append(msg) or False)
    assert em._check_hrk_trust(weather, "weather") is True      # as before 2.13
    assert em._check_hrk_trust(other, "someones") is False     # a community one asks
    assert len(asked) == 1


# ------------------------------------------------------------
# File names that aren't extension ids
# ------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("weather.hrk", "weather"), ("bintang_kecil.hrk", "bintang_kecil"), ("my-ext.HRK", "my-ext"),
    ("...hrk", None), ("..hrk", None), (".hrk", None), ("weather.hrk.hrk", None),
    ("orb.hrkit.hrk", None), ("a b.hrk", None), ("x" * 65 + ".hrk", None), ("readme.txt", None),
])
def test_extension_ids_from_file_names(name, expected):
    assert em._hrk_id(name) == expected


def test_a_dots_file_name_no_longer_removes_the_extensions_folder(ext_dir, monkeypatch):
    make_hrk(ext_dir / "...hrk", "evil")
    precious = make_hrk(ext_dir / "precious.hrk", "precious")
    (ext_dir / "my_dev_ext").mkdir()
    monkeypatch.setattr(em, "_download_trusted_hashes", lambda: {em._sha256_file(precious)})
    monkeypatch.setattr(em, "_show_security_dialog", lambda *a: True)   # even if the user says yes
    monkeypatch.setattr(em.bus, "subscribe", lambda *a: None)
    em.load_all_extensions()
    assert sorted(os.listdir(ext_dir)) == sorted([".cache", "...hrk", "my_dev_ext", "precious.hrk"])
    assert "precious" in em.LOADED_EXTENSIONS and ".." not in em.LOADED_EXTENSIONS
    with pytest.raises(ValueError):
        em._extract_dir("..")


# ------------------------------------------------------------
# Withdrawn from the list
# ------------------------------------------------------------

def test_a_saved_list_too_old_is_downloaded_again(ext_dir, monkeypatch):
    em._save_trust_cache(trusted={"revoked"})
    cache = em._load_trust_cache()
    cache["fetched_at"] = time.time() - em.TRUST_MAX_AGE_SECONDS - 60
    em.core.api.save_data(em._TRUST_CACHE_NAME, cache)
    monkeypatch.setattr(em, "_download_trusted_hashes", offline)
    assert "revoked" not in em._startup_trusted_hashes()     # offline: not trusted any more
    assert em._trust_list_current is False


def test_a_recent_saved_list_is_used_without_waiting(ext_dir, monkeypatch):
    em._save_trust_cache(trusted={"aa"})
    monkeypatch.setattr(em, "_download_trusted_hashes", lambda: pytest.fail("waited for the network"))
    assert em._startup_trusted_hashes() == {"aa"} and em._trust_list_current


def test_the_refresh_takes_withdrawn_hashes_off(ext_dir, monkeypatch):
    said = []
    monkeypatch.setattr(em, "_tell_withdrawn", said.append)
    monkeypatch.setattr(em, "_trusted_hash_cache", {"aa", "bb"})
    monkeypatch.setattr(em, "_consented_hashes", {"cc"})
    em.LOADED_EXTENSIONS["gone"] = {"sha256": "bb"}
    em.LOADED_EXTENSIONS["agreed"] = {"sha256": "cc"}
    monkeypatch.setattr(em, "_download_trusted_hashes", lambda: {"aa"})
    em._refresh_trusted_hashes()
    assert em._trusted_hash_cache == {"aa", "cc"}
    assert said == [["gone"]]


# ------------------------------------------------------------
# Unpacking
# ------------------------------------------------------------

def test_a_zip_that_unpacks_too_large_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "MAX_EXTRACTED_BYTES", 1024 * 1024)
    bomb = tmp_path / "bomb.hrk"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("big.bin", b"\0" * (2 * 1024 * 1024))
    assert os.path.getsize(bomb) < 20 * 1024
    with zipfile.ZipFile(bomb) as z, pytest.raises(ValueError):
        em._safe_extractall(z, str(tmp_path / "out"))
    assert not (tmp_path / "out" / "big.bin").exists()


def test_too_many_files_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "MAX_EXTRACTED_FILES", 5)
    many = tmp_path / "many.hrk"
    with zipfile.ZipFile(many, "w") as z:
        for i in range(6):
            z.writestr(f"f{i}.txt", "x")
    with zipfile.ZipFile(many) as z, pytest.raises(ValueError):
        em._safe_extractall(z, str(tmp_path / "out"))


# ------------------------------------------------------------
# The store
# ------------------------------------------------------------

URL = "https://infiartt.github.io/hariku-extensions/weather.hrk"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def store_dir(ext_dir, monkeypatch):
    monkeypatch.setattr(store, "_validate_download_url", lambda url: None)
    return ext_dir


@pytest.mark.parametrize("ext_id", ["weather.", "wea.ther", "weather ", "orbit!", "../x", "", "a" * 65])
def test_store_ids_are_checked_not_cleaned(store_dir, monkeypatch, ext_id):
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: pytest.fail("downloaded"))
    assert store.download_extension(ext_id, URL) is False
    assert os.listdir(store_dir) == []


def test_a_cut_off_download_keeps_the_working_extension(store_dir, monkeypatch):
    working = make_hrk(store_dir / "weather.hrk", "weather")
    before = open(working, "rb").read()

    class Broken(FakeResponse):
        def read(self, n=-1):
            data = super().read(n)
            if not data:
                raise ConnectionResetError("cut off")
            return data
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: Broken(b"PK\x03\x04partial"))
    assert store.download_extension("weather", URL) is False
    assert open(working, "rb").read() == before
    assert os.listdir(store_dir) == ["weather.hrk"]


def test_a_download_that_is_not_a_package_is_refused(store_dir, monkeypatch):
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"<html>"))
    assert store.download_extension("weather", URL) is False
    assert os.listdir(store_dir) == []


def test_a_good_download_replaces_the_old_one(store_dir, tmp_path, monkeypatch):
    make_hrk(store_dir / "weather.hrk", "weather")
    new = open(make_hrk(tmp_path / "new.hrk", "weather", main="# new\n"), "rb").read()
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: FakeResponse(new))
    assert store.download_extension("weather", URL) is True
    assert open(store_dir / "weather.hrk", "rb").read() == new


def test_an_oversized_download_is_refused(store_dir, monkeypatch):
    monkeypatch.setattr(store, "MAX_DOWNLOAD_BYTES", 1000)
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"PK" + b"\0" * 5000))
    assert store.download_extension("weather", URL) is False
    assert os.listdir(store_dir) == []


# ------------------------------------------------------------
# Download addresses
# ------------------------------------------------------------

@pytest.mark.parametrize("path", ["%2e%2e/%2e%2e/evil/repo/x.exe", "%2E%2E/x", "a%2fb", "a\\..\\b"])
def test_encoded_paths_are_refused(path):
    for base in core.endpoints.ALLOWED_URL_PREFIXES:
        assert not core.endpoints.is_trusted_download_url(base + path), base + path
