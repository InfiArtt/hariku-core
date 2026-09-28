# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Crash reports name Hariku: Cloudflare in front of infiartt.com refuses
Python's default User-Agent (403, error code 1010), which silently dropped
every report."""
import ast
import pathlib

import core.crash_handler
import core.endpoints

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_the_silent_report_sends_a_hariku_user_agent(monkeypatch):
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        sent.append(request)
        return Response()

    monkeypatch.setattr(core.crash_handler.urllib.request, "urlopen", fake_urlopen)
    try:
        raise ValueError("boom")
    except ValueError as error:
        core.crash_handler._send_report_silently(type(error), error, error.__traceback__)
    assert sent, "no report was sent"
    request = sent[0]
    assert request.full_url == core.endpoints.CRASH_REPORT_URL
    assert request.get_header("User-agent") == core.endpoints.HTTP_USER_AGENT
    assert "urllib" not in core.endpoints.HTTP_USER_AGENT.lower()


def test_every_request_to_infiartt_com_names_hariku():
    """Every urllib.request.Request built in core/ and ui/ for the crash
    report carries a User-Agent (the dialog's own send too)."""
    for rel in ("core/crash_handler.py", "ui/crash_dialog.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") == "Request"]
        assert calls, rel
        for call in calls:
            headers = next((k.value for k in call.keywords if k.arg == "headers"), None)
            assert isinstance(headers, ast.Dict), rel
            keys = [k.value for k in headers.keys if isinstance(k, ast.Constant)]
            assert "User-Agent" in keys, f"{rel}: a request without a User-Agent"
