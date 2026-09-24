# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Preferences builds its pages lazily (see ui/preferences_dialog.py). Only the
# events of a page being built are ignored for "unsaved changes"; a change the
# user makes on another page at the same moment still counts. No windows here
# (conftest.py mocks wx); tests/test_preferences_pages_ui.py covers the rest.

import ui.preferences_dialog as pd


class _Window:
    def __init__(self, parent=None):
        self._parent = parent

    def GetParent(self):
        return self._parent


class _Dialog:
    _inside_page_being_built = pd.PreferencesDialog._inside_page_being_built

    def __init__(self, building):
        self._realizing = list(building)


def test_events_from_the_page_being_built_are_ignored():
    holder = _Window()
    control = _Window(_Window(holder))          # a control on a panel inside the holder
    other_page = _Window()
    elsewhere = _Window(other_page)
    dialog = _Dialog([holder])
    assert dialog._inside_page_being_built(control)
    assert dialog._inside_page_being_built(holder)
    assert not dialog._inside_page_being_built(elsewhere)
    assert not dialog._inside_page_being_built(None)


def test_nothing_is_ignored_when_no_page_is_being_built():
    holder = _Window()
    assert not _Dialog([])._inside_page_being_built(_Window(holder))


def test_the_timings_keep_arrowing_smooth():
    # Built once the selection settles; background building waits longer than
    # that, so it never runs between two arrow presses.
    assert 100 <= pd.SETTLE_MS < pd.IDLE_MS
    assert pd.BACKGROUND_GAP_MS < pd.SETTLE_MS


def test_idle_time_never_raises():
    assert isinstance(pd._ms_since_input(), int)
