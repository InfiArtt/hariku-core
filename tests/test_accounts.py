# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The signed-in InfiArtt account (core.accounts, core 2.11), without a window
# and without the network. The Account Manager extension that provides it is
# tested with the official extensions (test_account_manager.py there).

import logging
import os

import pytest

import core.accounts as accounts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    monkeypatch.setattr(accounts, "_provider", None)


# ------------------------------------------------------------
# core.accounts
# ------------------------------------------------------------

def test_no_provider_means_no_account():
    assert accounts.available() is False
    assert accounts.current() is None
    assert accounts.open_sign_in() is False


def test_a_provider_gives_the_session():
    opened = []
    session = accounts.Session("secret-token-123456", "tester")
    provider = lambda: session  # noqa: E731
    accounts.register_provider(provider, sign_in=lambda: opened.append(1), name="Test")
    assert accounts.available() is True
    assert accounts.current() is session
    assert accounts.open_sign_in() is True and opened == [1]
    assert accounts.unregister_provider(lambda: None) is False     # not that one
    assert accounts.unregister_provider(provider) is True
    assert accounts.available() is False


def test_the_token_never_shows_in_a_session_s_text():
    session = accounts.Session("secret-token-123456", "tester")
    assert "secret" not in repr(session) and "secret" not in str(session)
    assert "tester" in repr(session)


def test_a_broken_provider_is_no_account(caplog):
    def boom():
        raise RuntimeError("disk")
    accounts.register_provider(boom)
    with caplog.at_level(logging.ERROR):
        assert accounts.current() is None
    accounts.register_provider(lambda: "not a session")
    assert accounts.current() is None
    accounts.register_provider(lambda: accounts.Session("", "x"))
    assert accounts.current() is None


def test_bad_registrations():
    with pytest.raises(TypeError):
        accounts.register_provider("no")
    with pytest.raises(TypeError):
        accounts.register_provider(lambda: None, sign_in="no")


def test_the_core_imports_it_so_the_compiled_app_has_it():
    with open(os.path.join(ROOT, "hariku.py"), encoding="utf-8") as f:
        assert "import core.accounts" in f.read()
