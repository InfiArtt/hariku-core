# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# core.api.run_thread(): the work runs on a thread, and the callback gets its
# result, or None when it failed, whatever kind of callable the work is.

import functools
import threading

import pytest


@pytest.fixture
def call_after(monkeypatch):
    """wx.CallAfter that runs the callback at once and remembers it ran."""
    import wx
    done = threading.Event()
    results = []

    def fake(fn, *args, **kwargs):
        fn(*args, **kwargs)
        done.set()

    monkeypatch.setattr(wx, "CallAfter", fake, raising=False)
    return done, results


def _run(work, call_after):
    import core.api
    done, results = call_after
    core.api.run_thread(work, results.append)
    assert done.wait(5), "the callback was never called"
    return results


def test_the_result_reaches_the_callback(call_after):
    assert _run(lambda: 42, call_after) == [42]


def test_a_failure_reaches_the_callback_as_none(call_after):
    def broken():
        raise OSError("disk gone")
    assert _run(broken, call_after) == [None]


def test_a_failing_partial_still_reaches_the_callback(call_after, caplog):
    # functools.partial has no __name__: logging the error must not fail too.
    def fetch(url):
        raise ConnectionError(f"no route to {url}")
    work = functools.partial(fetch, "https://example.com")
    assert not hasattr(work, "__name__")
    assert _run(work, call_after) == [None]
    assert any("no route to https://example.com" in r.getMessage() for r in caplog.records)


def test_a_failing_callable_object_still_reaches_the_callback(call_after):
    class Work:
        def __call__(self):
            raise ValueError("bad data")
    assert _run(Work(), call_after) == [None]
