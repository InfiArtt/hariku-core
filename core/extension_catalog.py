# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
What the Extension Manager's four tabs list (ui/extension_manager_dialog.py),
worked out without any window so it can be tested.

build(installed, registry, system_dir, load_errors) returns the rows of every
tab:
  * installed    - the installed extensions, except the incompatible ones.
                   One that can't run says why in its Status: it needs a
                   newer Hariku, its manifest is broken, or it stopped with an
                   error when Hariku started.
  * updates      - the installed extensions the store has a newer version of.
                   A new version that needs a newer Hariku says so and can't
                   be installed.
  * available    - the store's extensions that aren't installed, the ones
                   that need a newer Hariku saying so.
  * incompatible - like NVDA's: extensions made for a Hariku older than this
                   one still runs (core.constants.EXTENSION_API_BACK_COMPAT),
                   installed or in the store.
matching() narrows rows to a search, and the rest gives the words: the
Version and Status columns, the Details box and the tab titles.

A row is a dict. "needs_core" is the Hariku version its action needs (the
update of an installed row, the install of a store row) when this one is
older; "problem" is why an installed extension can't run. Versions compare as
versions (1.10 is newer than 1.9), and Hariku versions the way the extension
loader does. A developer folder is never replaced by the store's .hrk (the
folder would still win when Hariku loads), so it never has an update.
"""

import os

import core.constants
import core.extension_manager as manager
import core.store
from core.i18n import get_translator

_ = get_translator("core")

BUNDLED, STORE, DEVELOPER = "bundled", "store", "developer"
TABS = ("installed", "updates", "available", "incompatible")


def is_newer(candidate, current):
    return core.store._parse_version(candidate or "0") > core.store._parse_version(current or "0")


def is_official(ext_id):
    # The fixed list, never the manifest's author (anyone can write "Rafli").
    return ext_id in manager._OFFICIAL_EXTENSION_IDS


def _inside(path, folder):
    if not path or not folder:
        return False
    path = os.path.normcase(os.path.realpath(path))
    folder = os.path.normcase(os.path.realpath(folder))
    return path.startswith(folder + os.sep)


def source_of(info, system_dir):
    """Where an installed extension came from: BUNDLED, STORE or DEVELOPER."""
    if not info.get("is_unpacked"):
        return STORE
    if _inside(info.get("path"), system_dir):
        return BUNDLED
    return DEVELOPER


def _by_name(rows):
    return sorted(rows, key=lambda r: (r["name"].casefold(), r["id"]))


def _problem(info, load_errors):
    """(problem, detail) of an installed extension, ("", "") when it can run."""
    if info.get("missing_fields"):
        return "manifest", ", ".join(info["missing_fields"])
    if manager.too_old_for_core(info):
        return "too_old", manager.too_old_for_core(info)
    if manager.needs_newer_core(info):
        return "needs_core", manager.needs_newer_core(info)
    if load_errors.get(info["id"]):
        return "error", load_errors[info["id"]]
    return "", ""


def _installed_row(info, entry, source, load_errors):
    problem, detail = _problem(info, load_errors)
    newer = entry if (entry and source != DEVELOPER and not manager.too_old_for_core(entry)
                      and is_newer(entry.get("version"), info.get("version"))) else None
    return {
        "id": info["id"],
        "name": info.get("name") or info["id"],
        "author": info.get("author") or "",
        "official": is_official(info["id"]),
        "description": info.get("description") or "",
        "version": info.get("version") or "",
        "installed": True,
        "enabled": bool(info.get("is_enabled", True)),
        "source": source,
        "problem": problem,
        "problem_detail": detail,
        "update": newer.get("version", "") if newer else "",
        "needs_core": manager.needs_newer_core(newer) if newer else "",
        "download_url": newer.get("download_url", "") if newer else "",
    }


def _store_row(entry):
    too_old = manager.too_old_for_core(entry)
    return {
        "id": entry["id"],
        "name": entry.get("name") or entry["id"],
        "author": entry.get("author") or "",
        "official": is_official(entry["id"]),
        "description": entry.get("description") or "",
        "version": entry.get("version") or "",
        "installed": False,
        "enabled": False,
        "source": "",
        "problem": "too_old" if too_old else "",
        "problem_detail": too_old,
        "update": "",
        "needs_core": manager.needs_newer_core(entry),
        "download_url": entry.get("download_url", ""),
    }


def build(installed, registry, system_dir, load_errors=None):
    """{tab: rows} for TABS. installed: core.extension_manager.get_installed_
    extensions_info(); registry: core.store.fetch_registry(), or None while it
    hasn't answered (the store's tabs are then empty)."""
    load_errors = load_errors or {}
    store = {e.get("id"): e for e in registry or () if e.get("id")}
    mine = _by_name([_installed_row(info, store.get(info["id"]), source_of(info, system_dir),
                                    load_errors) for info in installed])
    have = {row["id"] for row in mine}
    others = _by_name([_store_row(entry) for ext_id, entry in store.items() if ext_id not in have])
    return {
        "installed": [row for row in mine if row["problem"] != "too_old"],
        "updates": [row for row in mine if row["update"]],
        "available": [row for row in others if row["problem"] != "too_old"],
        "incompatible": _by_name([row for row in mine + others if row["problem"] == "too_old"]),
    }


def can_update(row):
    return bool(row["update"]) and not row["needs_core"]


def can_install(row):
    return not row["installed"] and not row["problem"] and not row["needs_core"]


def can_open_guide(row, done="", has_guide=None):
    """Whether the Installed tab's Guide button works for a row (core 2.11):
    an installed extension, not just removed, with a guide of its own.
    has_guide(ext_id) defaults to core.guides.has_guide."""
    if not row or not row.get("installed") or done == "removed":
        return False
    if has_guide is None:
        import core.guides
        has_guide = core.guides.has_guide
    return bool(has_guide(row["id"]))


def waits_for_core(row):
    """The Hariku version the row waits for (to run, update or install), else ""."""
    if row["problem"] == "needs_core":
        return row["problem_detail"]
    return row["needs_core"]


def matching(rows, query):
    """The rows with every word of `query` in their name, description or author."""
    words = (query or "").casefold().split()
    if not words:
        return list(rows)
    return [row for row in rows
            if all(word in " ".join((row["name"], row["description"], row["author"])).casefold()
                   for word in words)]


# --- Words ----------------------------------------------------------------------------------

def version_text(row, tab):
    """The Version column: on the Updates tab, "1.1 to 1.2"."""
    if tab == "updates":
        return _("ext_version_to", old=row["version"], new=row["update"])
    return row["version"]


def status_text(row, tab, done=""):
    """The Status column. `done` is what happened to the row while the window
    is open: "downloading", "installed", "updated", "removed" or "failed"."""
    if done:
        return _("ext_done_" + done)
    if tab == "incompatible":
        return _("ext_status_too_old", version=row["problem_detail"])
    if tab in ("updates", "available"):
        if row["needs_core"]:
            return _("ext_status_needs_core", version=row["needs_core"])
        return _("ext_status_ready_to_update") if tab == "updates" else ""
    if row["problem"] == "needs_core":
        return _("ext_status_needs_core_not_running", version=row["problem_detail"])
    if row["problem"]:
        return _("ext_status_problem_" + row["problem"])
    state = _("ext_status_enabled") if row["enabled"] else _("ext_status_disabled")
    if can_update(row):
        return _("ext_status_with_update", state=state, version=row["update"])
    return state


def details_text(row, tab, done=""):
    """The Details box: who made it, where it came from, what's wrong or new,
    and the description."""
    who = _("ext_detail_official") if row["official"] else _("ext_detail_community")
    lines = [_("ext_detail_head", name=row["name"], version=row["version"],
               author=row["author"] or _("ext_detail_unknown_author"), who=who)]
    if done:
        lines.append(_("ext_done_" + done))
    if row["installed"]:
        lines.append(_("ext_status_enabled") + "." if row["enabled"]
                     else _("ext_status_disabled") + ".")
        lines.append(_("ext_detail_source_" + row["source"]))
    current = core.constants.CORE_VERSION
    if row["problem"] == "too_old":
        lines.append(_("ext_detail_too_old", made=row["problem_detail"], current=current,
                       oldest=core.constants.EXTENSION_API_BACK_COMPAT))
    elif row["problem"] == "needs_core":
        lines.append(_("ext_detail_problem_needs_core", core=row["problem_detail"],
                       current=current))
    elif row["problem"] == "manifest":
        lines.append(_("ext_detail_problem_manifest", fields=row["problem_detail"]))
    elif row["problem"] == "error":
        lines.append(_("ext_detail_problem_error", error=row["problem_detail"]))
    if row["update"] and row["needs_core"]:
        lines.append(_("ext_detail_update_needs_core", version=row["update"],
                       core=row["needs_core"], current=current))
    elif row["update"]:
        lines.append(_("ext_detail_update", version=row["update"]))
    if not row["installed"] and row["needs_core"]:
        lines.append(_("ext_detail_needs_core", core=row["needs_core"], current=current))
    text = "\n".join(lines)
    if row["description"]:
        text += "\n\n" + row["description"]
    return text


def tab_title(tab, count):
    """"Installed (31)"; before the store has answered, the store's tabs have
    no count."""
    if count is None:
        return _("ext_tab_" + tab)
    return _("ext_tab_count", tab=_("ext_tab_" + tab), count=count)
