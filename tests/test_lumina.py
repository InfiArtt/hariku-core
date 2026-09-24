# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Tests for Lumina 1.1 and the Profile birthday: Lumina reads the user's own
# birthday from core.personal when the core has it (2.7+), moves its own copy
# there once, and leaves the birthday wish to Hariku's startup greeting.

import ast
import datetime
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUMINA_DIR = os.path.join(ROOT, "extensions", "lumina")


@pytest.fixture
def lumina(monkeypatch, tmp_data_dir):
    if LUMINA_DIR not in sys.path:
        sys.path.insert(0, LUMINA_DIR)
    spec = importlib.util.spec_from_file_location("lumina_main_under_test",
                                                  os.path.join(LUMINA_DIR, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spoken, scheduled = [], []
    monkeypatch.setattr(module, "speak", lambda msg, interrupt=False: spoken.append(msg))

    def call_later(ms, fn, *args):
        scheduled.append((fn, args))

    monkeypatch.setattr(module.wx, "CallLater", call_later)
    module.spoken, module.scheduled = spoken, scheduled
    return module


def _core(**data):
    import core.api
    core.api.save_data("Core", data)


def _lumina_data(module, **data):
    import core.api
    core.api.save_data(module.DATA_KEY, data)


def _dd_mm(day):
    return f"{day.day:02d}-{day.month:02d}"


def test_manifest():
    with open(os.path.join(LUMINA_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    # The Profile birthday is used through a guarded import, so older cores
    # still run Lumina 1.1 with its own copy.
    assert manifest["version"] == "1.1" and manifest["minimum_core_version"] == "2.1"


def test_core_imports_are_module_level_and_personal_is_guarded():
    with open(os.path.join(LUMINA_DIR, "main.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Import):
                    names = [a.name for a in inner.names]
                    assert not any(n.startswith("core") for n in names), (node.name, names)
    guarded = [node for node in tree.body if isinstance(node, ast.Try)
               and any(isinstance(n, ast.Import) and n.names[0].name == "core.personal"
                       for n in node.body)]
    assert guarded and guarded[0].handlers[0].type.id == "ImportError"


def test_birthday_comes_from_the_profile(lumina):
    import core.personal
    assert lumina._personal is core.personal
    _core(user_name="Rafli", user_nickname="Bro",
          user_birthday={"day": 5, "month": 8, "year": 1999})
    _lumina_data(lumina, self_birthday={"date": "01-01", "year": 1980}, self_birthday_migrated=True)
    assert lumina._get_self_birthday() == {"date": "05-08", "year": 1999}
    assert lumina._get_user_name() == "Bro"
    _core(user_name="User")
    assert lumina._get_self_birthday() == {}
    assert lumina._get_user_name() == "Kamu"


def test_own_copy_moves_into_the_profile_once(lumina):
    import core.personal
    _lumina_data(lumina, self_birthday={"date": "24-09", "year": 1999}, birthdays=[])
    lumina._migrate_self_birthday()
    assert core.personal.get_birthday() == (24, 9, 1999)
    import core.api
    assert core.api.load_data(lumina.DATA_KEY)["self_birthday_migrated"] is True
    # Cleared in the Profile later: not brought back.
    core.personal.set_birthday(None, None)
    lumina._migrate_self_birthday()
    assert core.personal.get_birthday() is None


def test_profile_birthday_wins_over_the_own_copy(lumina):
    import core.personal
    core.personal.set_birthday(1, 1, 2000)
    _lumina_data(lumina, self_birthday={"date": "24-09", "year": 1999})
    lumina._migrate_self_birthday()
    assert core.personal.get_birthday() == (1, 1, 2000)


def test_migration_keeps_the_date_when_the_year_is_bad(lumina):
    import core.personal
    _lumina_data(lumina, self_birthday={"date": "29-02", "year": 1999})
    lumina._migrate_self_birthday()
    assert core.personal.get_birthday() == (29, 2, None)


def test_nothing_to_migrate(lumina):
    import core.personal
    _lumina_data(lumina, self_birthday={"date": "not a date"})
    lumina._migrate_self_birthday()
    assert core.personal.get_birthday() is None


def test_register_migrates(lumina, fresh_event_bus, monkeypatch):
    import core.hotkeys
    import core.personal
    import core.preferences
    monkeypatch.setattr(core.hotkeys, "register_action", lambda *a, **k: None)
    monkeypatch.setattr(core.preferences, "register_panel", lambda *a, **k: None)
    _lumina_data(lumina, self_birthday={"date": "24-09"})
    lumina.register(fresh_event_bus)
    assert core.personal.get_birthday() == (24, 9, None)


def _scheduled_self(lumina):
    return [args for fn, args in lumina.scheduled if args and args[-1] is True]


def test_birthday_wished_once_at_startup(lumina):
    import core.personal
    today = datetime.date.today()
    core.personal.set_birthday(today.day, today.month)
    _lumina_data(lumina, self_birthday_migrated=True,
                 birthdays=[{"name": "Budi", "date": _dd_mm(today)}])
    # Hariku's startup greeting (on by default) already says "Happy birthday!".
    lumina._check_all_and_announce()
    assert _scheduled_self(lumina) == []
    assert [args[0]["name"] for fn, args in lumina.scheduled] == ["Budi"]
    # With the greeting off, Lumina wishes it.
    lumina.scheduled.clear()
    core.personal.set_startup_greeting(False)
    lumina._check_all_and_announce()
    assert len(_scheduled_self(lumina)) == 1


def test_upcoming_own_birthday_is_still_announced(lumina):
    import core.personal
    soon = datetime.date.today() + datetime.timedelta(days=7)
    core.personal.set_birthday(soon.day, soon.month)
    _lumina_data(lumina, self_birthday_migrated=True)
    lumina._check_all_and_announce()
    [(entry, is_self)] = _scheduled_self(lumina)
    assert entry["date"] == _dd_mm(soon)


def test_without_the_profile_lumina_keeps_its_own_copy(lumina, monkeypatch):
    monkeypatch.setattr(lumina, "_personal", None)
    today = datetime.date.today()
    _core(user_name="Rafli")
    _lumina_data(lumina, self_birthday={"date": _dd_mm(today), "year": None})
    assert lumina._get_self_birthday() == {"date": _dd_mm(today), "year": None}
    assert lumina._get_user_name() == "Rafli"
    lumina._migrate_self_birthday()                       # nothing to move it to
    lumina._check_all_and_announce()
    assert len(_scheduled_self(lumina)) == 1


def test_calendar_and_agenda_show_the_profile_birthday(lumina):
    _core(user_nickname="Bro", user_birthday={"day": 24, "month": 9})
    _lumina_data(lumina, self_birthday_migrated=True, settings={"nav_action": "agenda"})
    payload = {"date": "2026-09-24", "reminders": []}
    lumina.on_fetch_agenda(payload)
    assert "Bro" in payload["reminders"][0]["title"]
