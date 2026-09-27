# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Where Hariku may send an Ask Hariku question (core.endpoints, core 2.11):
# HTTPS on infiartt.com or a workers.dev Worker, plain HTTP only to this
# computer, and nothing smuggled in the address.

import pytest

import core.endpoints as endpoints


@pytest.mark.parametrize("url", [
    "https://hariku-ai.someone.workers.dev",
    "https://hariku-ai.someone.workers.dev/",
    "https://ai.infiartt.com",
    "https://infiartt.com/hariku-ai",
    "http://127.0.0.1:8787",
    "http://localhost:8787/",
    "https://localhost",
])
def test_allowed(url):
    assert endpoints.is_allowed_ai_url(url)
    assert not endpoints.assert_ai_url(url).endswith("/")


@pytest.mark.parametrize("url", [
    "http://hariku-ai.someone.workers.dev",          # not HTTPS
    "https://evil.example",                          # another host
    "https://workers.dev.evil.example",
    "https://infiartt.com.evil.example",
    "https://evilinfiartt.com",
    "https://user:pass@ai.infiartt.com",             # a user name and password
    "https://ai.infiartt.com@evil.example",
    "https://ai.infiartt.com/?next=evil",            # a query
    "https://ai.infiartt.com/#x",
    "https://ai.infiartt.com/../x",
    "file:///C:/Windows",
    "ftp://127.0.0.1",
    "",
    None,
    "https://hariku-ai.<subdomain>.workers.dev",     # the placeholder isn't an address yet
])
def test_refused(url):
    assert not endpoints.is_allowed_ai_url(url)
    with pytest.raises(ValueError):
        endpoints.assert_ai_url(url)


def test_the_default_is_https_on_workers_dev_or_infiartt():
    url = endpoints.HARIKU_AI_URL
    assert url.startswith("https://")
    assert url.rstrip("/").endswith((".workers.dev", "infiartt.com"))
