# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# A source checkout isn't version-stamped by the release build, so the automatic
# startup check would offer an "update" on every launch, and the installer it
# offers would not update the checkout. Manual checks still work for testing.

import pytest

import core.updater as updater


def test_tests_run_from_source():
    assert updater.RUNNING_FROM_SOURCE


def test_automatic_check_is_skipped_from_source(monkeypatch):
    monkeypatch.setattr(updater, "get_update_info",
                        lambda: pytest.fail("must not fetch version.json automatically"))
    assert updater.check_for_updates(interactive=False) is False


def test_manual_check_still_runs_from_source(monkeypatch):
    calls = []
    monkeypatch.setattr(updater, "get_update_info", lambda: calls.append(1) or None)
    updater.check_for_updates(interactive=True)
    assert calls == [1]
