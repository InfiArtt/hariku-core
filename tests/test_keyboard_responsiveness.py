# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Hariku must never hold up keystrokes on their way to the screen reader.
# Quick Expand's low-level keyboard hook used to run on the UI thread, so every
# key in the system waited whenever the UI was busy, for example while Routines
# ran `netsh` on each window switch. That broke NVDA+key gestures.

import importlib.util
import os
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, path, extra_path=None):
    if extra_path and extra_path not in sys.path:
        sys.path.insert(0, extra_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Quick Expand -------------------------------------------------------------

@pytest.fixture
def qe():
    module = _load("quick_expand_under_test",
                   os.path.join(ROOT, "extensions", "quick_expand", "main.py"))
    yield module
    module.uninstall_hook()


def test_no_hook_without_abbreviations(qe):
    qe.EXPANSIONS = {}
    qe.install_hook()
    assert qe._hook_thread is None
    assert not qe.hook_id


def test_hook_runs_on_its_own_thread_and_stops(qe):
    qe.EXPANSIONS = {"sig": "Best regards"}
    qe.install_hook()
    try:
        thread = qe._hook_thread
        assert thread is not None and thread.is_alive()
        assert thread is not threading.main_thread()
        assert qe.hook_id, "SetWindowsHookExW failed"
    finally:
        qe.uninstall_hook()
    assert not thread.is_alive()
    assert not qe.hook_id


def test_install_twice_keeps_one_hook(qe):
    qe.EXPANSIONS = {"sig": "Best regards"}
    qe.install_hook()
    first = qe._hook_thread
    qe.install_hook()
    assert qe._hook_thread is first


# --- Routines: no slow work on the UI thread unless a routine needs it -------

@pytest.fixture
def rt():
    return _load("routines_runtime_under_test",
                 os.path.join(ROOT, "extensions", "routines", "routines_runtime.py"),
                 extra_path=os.path.join(ROOT, "extensions", "routines"))


def test_costly_fields_detected_from_conditions_and_placeholders(rt):
    wifi = {"conditions": [{"type": "wifi_ssid", "params": {"text": "Home"}}], "actions": []}
    cpu = {"conditions": [{"type": "time", "params": {"time": "08:00"}}],
           "actions": [{"type": "tts", "params": {"text": "CPU at {cpu} percent"}}]}
    plain = {"conditions": [{"type": "time", "params": {"time": "08:00"}}],
             "actions": [{"type": "tts", "params": {"text": "Good morning"}}]}
    assert rt._costly_fields_needed([wifi]) == {"wifi_ssid"}
    assert rt._costly_fields_needed([cpu]) == {"cpu_percent"}
    assert rt._costly_fields_needed([plain]) == set()


def test_no_routines_means_no_work(rt, monkeypatch):
    monkeypatch.setattr(rt, "load_routines", lambda: [])
    called = []
    monkeypatch.setattr(rt, "build_context", lambda *a, **k: called.append(1) or {})
    rt.evaluate_all()
    assert called == []


def test_disabled_routines_skip_context(rt, monkeypatch):
    monkeypatch.setattr(rt, "load_routines",
                        lambda: [{"id": "r1", "enabled": False, "conditions": [], "actions": []}])
    called = []
    monkeypatch.setattr(rt, "build_context", lambda *a, **k: called.append(1) or {})
    rt.evaluate_all()
    assert called == []
    assert rt._met_last.get("r1") is False


def test_netsh_not_run_when_no_routine_uses_wifi(rt, monkeypatch):
    def boom():
        raise AssertionError("netsh must not run")

    monkeypatch.setattr(rt, "_query_wifi_ssid", boom)
    monkeypatch.setattr(rt, "_ssid_cache", (0.0, ""))
    ctx = rt.build_context(needed=set())
    assert ctx["wifi_ssid"] == ""
    assert ctx["ram_percent"] is None and ctx["cpu_percent"] is None
