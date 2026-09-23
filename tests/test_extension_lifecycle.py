# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# =============================================================================
# Tests for the extension teardown() lifecycle hook now implemented in the
# engine (core.extension_manager.unload_all_extensions), which the docs promise.
# =============================================================================

import pytest


class TestExtensionTeardown:
    def _register(self, ext_id, module):
        import core.extension_manager as em
        em.LOADED_EXTENSIONS[ext_id] = {
            "module": module, "manifest": {}, "is_unpacked": True, "is_official": False,
        }

    def _cleanup(self, *ext_ids):
        import core.extension_manager as em
        for e in ext_ids:
            em.LOADED_EXTENSIONS.pop(e, None)

    def test_teardown_is_called(self):
        import core.extension_manager as em
        called = {"v": False}

        class Mod:
            def teardown(self_inner):
                called["v"] = True

        self._register("lc_call", Mod())
        try:
            em.unload_all_extensions()
            assert called["v"] is True
        finally:
            self._cleanup("lc_call")

    def test_missing_teardown_is_ignored(self):
        import core.extension_manager as em

        class Mod:
            pass  # no teardown()

        self._register("lc_missing", Mod())
        try:
            em.unload_all_extensions()  # must not raise
        finally:
            self._cleanup("lc_missing")

    def test_one_failing_teardown_does_not_block_others(self):
        import core.extension_manager as em
        order = []

        class Boom:
            def teardown(self_inner):
                raise RuntimeError("boom")

        class Ok:
            def teardown(self_inner):
                order.append("ok")

        self._register("lc_boom", Boom())
        self._register("lc_ok", Ok())
        try:
            em.unload_all_extensions()  # must not raise despite Boom
            assert "ok" in order
        finally:
            self._cleanup("lc_boom", "lc_ok")
