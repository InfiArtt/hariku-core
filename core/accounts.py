# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The InfiArtt account Hariku is signed in to (core 2.11), for extensions with
online features. No wx here.

The Account Manager extension signs in (OAuth with PKCE at infiartt.com) and
registers itself as the provider; other extensions ask here, never by reading
its data file:

    available()      -> whether an account provider is loaded (the Account
                        Manager is installed and on)
    current()        -> a Session (.token, .username) while signed in, or None
    open_sign_in()   -> shows where to sign in (the Account Manager's page);
                        False when there is no provider

    register_provider(session, sign_in=None, name="")   the Account Manager's
    unregister_provider(session)

A Session's token is a credential: send it only to InfiArtt's own services,
over HTTPS, and never log it (a Session's repr doesn't show it).
"""
import logging
import threading

logger = logging.getLogger(__name__)


class Session:
    """A signed-in InfiArtt account: `token` (the access token, for an
    Authorization: Bearer header) and `username` (to show)."""

    __slots__ = ("token", "username")

    def __init__(self, token, username=""):
        self.token = str(token)
        self.username = str(username or "")

    def __repr__(self):
        return f"Session({self.username!r}, token=<hidden>)"

    __str__ = __repr__


class _Provider:
    def __init__(self, session, sign_in=None, name=""):
        self.session = session
        self.sign_in = sign_in
        self.name = name or "account provider"


_lock = threading.Lock()
_provider = None


def register_provider(session, sign_in=None, name=""):
    """Make an extension the account provider (the Account Manager). One at a
    time; registering again replaces it. session() returns a Session while
    signed in, else None, and must be quick (no network: from memory).
    sign_in() shows where the user signs in."""
    global _provider
    if not callable(session):
        raise TypeError("session must be callable")
    if sign_in is not None and not callable(sign_in):
        raise TypeError("sign_in must be callable or None")
    with _lock:
        _provider = _Provider(session, sign_in, name)
    return True


def unregister_provider(session=None):
    """Remove the provider (in teardown()); with `session`, only when it is
    that one."""
    global _provider
    with _lock:
        if _provider is None or (session is not None and _provider.session != session):
            return False
        _provider = None
    return True


def available():
    with _lock:
        return _provider is not None


def current():
    """The signed-in Session, or None (not signed in, the sign-in expired,
    or no provider)."""
    with _lock:
        provider = _provider
    if provider is None:
        return None
    try:
        session = provider.session()
    except Exception:
        logger.exception(f"Accounts: asking {provider.name} failed")
        return None
    if isinstance(session, Session) and session.token:
        return session
    return None


def open_sign_in():
    """Show where to sign in; False when there's no provider or it failed."""
    with _lock:
        provider = _provider
    if provider is None or provider.sign_in is None:
        return False
    try:
        provider.sign_in()
        return True
    except Exception:
        logger.exception(f"Accounts: opening the sign-in of {provider.name} failed")
        return False
