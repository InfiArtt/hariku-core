# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The signed-in InfiArtt account (core.accounts, core 2.11) and the Account
# Manager extension that provides it: its tokens (saved with their expiry,
# renewed when fewer than 30 days are left, the rotated pair kept in one
# save, the old pair kept when infiartt.com refuses), without a window and
# without the network (a fake /oauth/token).

import importlib.util
import json
import logging
import os
import sys
import types

import pytest

import core.accounts as accounts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(ROOT, "extensions", "account_manager")
NOW = 1_790_000_000                 # a moment in 2026, seconds since 1970
DAY = 86400


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


# ------------------------------------------------------------
# The Account Manager's tokens
# ------------------------------------------------------------

def _tokens():
    if EXT_DIR not in sys.path:
        sys.path.insert(0, EXT_DIR)
    import account_manager_tokens
    return account_manager_tokens


@pytest.fixture
def t():
    return _tokens()


def test_what_is_saved_from_a_token_answer(t):
    answer = {"access_token": "A1", "refresh_token": "R1", "token_type": "Bearer",
              "expires_in": 180 * DAY}
    assert t.token_fields(answer, NOW) == {"access_token": "A1", "refresh_token": "R1",
                                            "expires_at": NOW + 180 * DAY}
    assert t.token_fields({"access_token": "A1"}, NOW) == {"access_token": "A1"}
    assert t.token_fields({"refresh_token": "R1"}, NOW) is None
    assert t.token_fields("nope", NOW) is None


def test_signed_in_and_expired(t):
    data = {"access_token": "A1", "expires_at": NOW + DAY, "user_profile": {"username": "tester"}}
    assert t.signed_in(data, NOW) == ("A1", "tester")
    assert t.signed_in(data, NOW + 2 * DAY) is None                 # ran out
    assert t.signed_in({"access_token": "A1"}, NOW) == ("A1", "")   # an older sign-in, no expiry
    assert t.signed_in({}, NOW) is None


@pytest.mark.parametrize("left, needed", [
    (180 * DAY, False), (31 * DAY, False), (30 * DAY, True), (DAY, True), (0, False), (-DAY, False),
])
def test_renewed_when_fewer_than_30_days_are_left(t, left, needed):
    data = {"access_token": "A1", "refresh_token": "R1", "expires_at": NOW + left}
    assert t.needs_refresh(data, NOW) is needed
    assert t.needs_refresh({"access_token": "A1", "expires_at": NOW + DAY}, NOW) is False   # no refresh token


def test_refresh_outcomes(t):
    data = {"refresh_token": "R1"}
    sent = []

    def post(answer, status=200):
        def fake(form):
            sent.append(form)
            return status, json.dumps(answer) if not isinstance(answer, str) else answer
        return fake

    outcome, fields = t.refresh(data, post({"access_token": "A2", "refresh_token": "R2",
                                            "expires_in": 180 * DAY}), "client", NOW)
    assert outcome == "refreshed"
    assert fields == {"access_token": "A2", "refresh_token": "R2", "expires_at": NOW + 180 * DAY}
    assert sent[0] == {"grant_type": "refresh_token", "client_id": "client", "refresh_token": "R1"}
    assert t.refresh(data, post({"error": "invalid_grant"}, 400), "client", NOW) == ("invalid", None)
    assert t.refresh(data, post({"error": "server"}, 500), "client", NOW) == ("failed", None)
    assert t.refresh(data, post("not json", 200), "client", NOW) == ("failed", None)
    assert t.refresh(data, post({"access_token": "A2"}), "client", NOW) == ("failed", None)   # no new refresh token

    def offline(form):
        raise OSError("offline")
    assert t.refresh(data, offline, "client", NOW) == ("failed", None)


# ------------------------------------------------------------
# The Account Manager, loaded (wx mocked; data in a temporary folder)
# ------------------------------------------------------------

@pytest.fixture
def manager(tmp_data_dir, monkeypatch):
    import core.preferences
    monkeypatch.setattr(core.preferences, "_panels", {})
    _tokens()
    spec = importlib.util.spec_from_file_location("hariku_ext.account_manager_test",
                                                  os.path.join(EXT_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from core.events import EventBus
    bus = EventBus()
    module.register(bus)
    module.bus_events = []
    monkeypatch.setattr(module, "bus", types.SimpleNamespace(
        emit=lambda name, payload=None: module.bus_events.append((name, payload))))
    yield module
    module.teardown()


def _signed_in(left_days, **more):
    data = {"access_token": "A1", "refresh_token": "R1", "expires_at": NOW + left_days * DAY,
            "user_profile": {"username": "tester", "roles": ["user"]}}
    data.update(more)
    return data


def test_it_provides_the_account(manager):
    import core.api
    assert accounts.available() is True
    assert accounts.current() is None                              # not signed in yet
    manager.store_state(_signed_in(100, expires_at=4_000_000_000))
    session = accounts.current()
    assert session.token == "A1" and session.username == "tester"
    assert core.api.load_data("account_manager")["access_token"] == "A1"
    manager.teardown()
    assert accounts.available() is False


def test_sign_in_opens_its_page(manager, monkeypatch):
    import core.api
    opened = []
    monkeypatch.setattr(core.api, "open_preferences", lambda tab=None: opened.append(tab))
    assert accounts.open_sign_in() is True
    assert opened == ["Hariku Cloud"]


def test_a_renewal_saves_both_new_tokens_at_once(manager, monkeypatch):
    import core.api
    manager.store_state(_signed_in(10))
    saves = []
    real_save = core.api.save_data
    monkeypatch.setattr(core.api, "save_data",
                        lambda key, data: saves.append(dict(data)) or real_save(key, data))

    def post(form):
        assert form["refresh_token"] == "R1" and form["grant_type"] == "refresh_token"
        return 200, json.dumps({"access_token": "A2", "refresh_token": "R2", "expires_in": 180 * DAY})

    assert manager.refresh_if_needed(post=post, now=NOW) == "refreshed"
    assert len(saves) == 1                                         # one atomic write
    assert (saves[0]["access_token"], saves[0]["refresh_token"]) == ("A2", "R2")
    assert saves[0]["expires_at"] == NOW + 180 * DAY
    assert saves[0]["user_profile"]["username"] == "tester"
    assert manager.current_state()["refresh_token"] == "R2"
    assert manager.bus_events[-1][0] == "on_user_login"            # others learn the new token
    assert manager.refresh_if_needed(post=post, now=NOW) == "not_needed"


def test_a_refused_renewal_keeps_the_old_pair(manager):
    manager.store_state(_signed_in(10))
    outcome = manager.refresh_if_needed(post=lambda form: (400, '{"error": "invalid_grant"}'), now=NOW)
    assert outcome == "invalid"
    assert manager.current_state()["refresh_token"] == "R1"
    assert manager.current_state()["access_token"] == "A1"


def test_a_failed_save_keeps_the_new_pair_for_this_session(manager, monkeypatch, caplog):
    import core.api
    manager.store_state(_signed_in(10))
    monkeypatch.setattr(core.api, "save_data", lambda key, data: False)
    post = lambda form: (200, json.dumps({"access_token": "A2", "refresh_token": "R2",  # noqa: E731
                                          "expires_in": 180 * DAY}))
    with caplog.at_level(logging.ERROR):
        assert manager.refresh_if_needed(post=post, now=NOW) == "refreshed"
    assert manager.current_state()["refresh_token"] == "R2"
    assert "A2" not in caplog.text and "R2" not in caplog.text     # tokens are never logged


def test_signing_out_meanwhile_wins(manager):
    manager.store_state(_signed_in(10))

    def post(form):
        manager.store_state({})                                    # the user signed out
        return 200, json.dumps({"access_token": "A2", "refresh_token": "R2", "expires_in": 180 * DAY})

    assert manager.refresh_if_needed(post=post, now=NOW) == "not_needed"
    assert manager.current_state() == {}


def test_an_expired_sign_in_is_no_account(manager):
    manager.store_state(_signed_in(-1))
    assert accounts.current() is None


def test_startup_renews_only_when_needed(manager, monkeypatch):
    import core.api
    started = []
    monkeypatch.setattr(core.api, "set_timeout", lambda ms, fn: None)

    class FakeThread:
        def __init__(self, target, daemon, name):
            started.append(name)

        def start(self):
            pass

    monkeypatch.setattr(manager.threading, "Thread", FakeThread)
    monkeypatch.setattr(manager.time, "time", lambda: NOW)
    manager.store_state(_signed_in(100))
    manager.on_app_startup()
    assert started == []
    manager.store_state(_signed_in(10))
    manager.on_app_startup()
    assert started == ["hariku-account-refresh"]


def test_token_requests_ask_for_no_caching(manager, monkeypatch):
    import urllib.request
    seen = {}

    class Response:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake(request, timeout):
        seen.update(dict(request.header_items()))
        return Response()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    manager._post_token({"grant_type": "refresh_token"})
    assert seen.get("Cache-control") == "no-store"
    # infiartt.com's Browser Integrity Check refuses Python's default agent.
    assert seen.get("User-agent") == "HarikuV2/2.0"


def test_only_the_user_name_and_roles_are_kept_from_the_profile():
    with open(os.path.join(EXT_DIR, "main.py"), encoding="utf-8") as f:
        source = f.read()
    assert 'user_profile = {"username": user.get("username"), "roles": user.get("roles") or []}' in source
