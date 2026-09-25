# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
What the Dropbox extension says, in English and Indonesian (casual: "kamu",
"-mu"), and in the persona the user picked (core 2.10 looks "key@persona"
up first; older cores use the plain text). Short lines: they are spoken
while the user works. Each function returns [(text, sound)] where sound is
"synced", "shared" or None. No wx here.
"""

import os

from core.i18n import get_translator

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("dropbox", os.path.join(EXT_DIR, "locales"))

SMALL_SESSION = 3        # up to this many files: each one's "synced" is told
MAX_PEOPLE = 3           # others' changes: one line each for this many people
MAX_NAMES = 3            # names read out in a list


def settings_on(settings, name):
    return bool((settings or {}).get(name, True))


def join_names(names):
    """ "A", "A dan B", "A, B dan C" ("and" in English)."""
    names = [str(n) for n in names if str(n)]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return _("list_join", first=", ".join(names[:-1]), last=names[-1])


# ------------------------------------------------------------
# Your files syncing
# ------------------------------------------------------------

def sync_lines(flush, settings):
    """What to say about a dropbox_sync.Flush."""
    if flush is None:
        return []
    progress = settings_on(settings, "progress")
    lines = []
    if flush.up_to_date:
        if progress and len(flush.session) == 1 and flush.synced == flush.session:
            lines.append((_("synced_one", name=flush.session[0]), "synced"))
        elif settings_on(settings, "up_to_date"):
            lines.append((_("up_to_date"), "synced"))
        elif progress and flush.synced:
            lines.append(_synced(flush.synced))
    elif progress:
        if flush.new and not flush.retold:
            if len(flush.new) == 1:
                lines.append((_("sync_one", name=flush.new[0]), None))
            else:
                lines.append((_("sync_many", count=len(flush.new)), None))
        elif flush.synced and len(flush.session) <= SMALL_SESSION:
            lines.append(_synced(flush.synced))
    if flush.stuck and progress:
        if len(flush.stuck) == 1:
            lines.append((_("stuck_one", name=flush.stuck[0]), None))
        else:
            lines.append((_("stuck_many", count=len(flush.stuck)), None))
    return lines


def _synced(names):
    if len(names) == 1:
        return _("synced_one", name=names[0]), "synced"
    return _("synced_many", count=len(names)), "synced"


# ------------------------------------------------------------
# Other people's changes in shared folders
# ------------------------------------------------------------

def others_lines(summaries, settings):
    """Lines for dropbox_remote.summarize() results: one per person, the
    first MAX_PEOPLE; the rest counted."""
    if not summaries or not settings_on(settings, "others"):
        return []
    lines = []
    for item in summaries[:MAX_PEOPLE]:
        person = item.get("person") or _("someone")
        count = item.get("count", 1)
        folder = item.get("folder")
        added = item.get("added", False)
        if count == 1 and folder:
            key = "others_added_one" if added else "others_changed_one"
            text = _(key, person=person, name=item.get("name", ""), folder=folder)
        elif count == 1:
            key = "others_added_top" if added else "others_changed_top"
            text = _(key, person=person, name=item.get("name", ""))
        elif folder:
            key = "others_added_many" if added else "others_changed_many"
            text = _(key, person=person, count=count, folder=folder)
        else:
            text = _("others_spread", person=person, count=count)
        lines.append(text)
    if len(summaries) > MAX_PEOPLE:
        lines.append(_("others_crowd", count=len(summaries) - MAX_PEOPLE))
    return [(" ".join(lines), "shared")]


# ------------------------------------------------------------
# Shared with you
# ------------------------------------------------------------

def shared_lines(items, settings):
    """Lines for new files and folders others shared (dropbox_remote.
    SharedWatcher.poll()): grouped by who shared them."""
    if not items or not settings_on(settings, "shared"):
        return []
    by_person = {}
    for item in items:
        by_person.setdefault(item.get("owner") or "", []).append(item)
    lines = []
    for person, group in list(by_person.items())[:MAX_PEOPLE]:
        who = person or _("someone")
        if len(group) == 1:
            item = group[0]
            key = "shared_folder" if item.get("kind") == "folder" else "shared_file"
            lines.append(_(key, person=who, name=item.get("name", "")))
        else:
            lines.append(_("shared_many", person=who, count=len(group)))
    if len(by_person) > MAX_PEOPLE:
        rest = sum(len(g) for g in list(by_person.values())[MAX_PEOPLE:])
        lines.append(_("shared_more", count=rest))
    return [(" ".join(lines), "shared")]


# ------------------------------------------------------------
# Answers
# ------------------------------------------------------------

def status_text(state):
    """What "Dropbox status" says. `state`: {"set_up", "connected", "name",
    "folder" (bool), "pending" [names], "stuck" [names]}."""
    if not state.get("set_up"):
        return _("not_set_up")
    if not state.get("connected"):
        return _("not_connected")
    if not state.get("folder"):
        return _("status_no_folder", name=state.get("name") or _("someone"))
    pending = state.get("pending") or []
    stuck = state.get("stuck") or []
    parts = []
    if len(pending) == 1:
        parts.append(_("status_syncing_one", name=pending[0]))
    elif pending:
        parts.append(_("status_syncing_many", count=len(pending)))
    if len(stuck) == 1:
        parts.append(_("stuck_one", name=stuck[0]))
    elif stuck:
        parts.append(_("stuck_many", count=len(stuck)))
    return " ".join(parts) if parts else _("status_up_to_date")


def item_text(meta):
    """ "laporan.pdf di folder Kelas", or the name alone at the top."""
    name = meta.get("name") or ""
    parts = str(meta.get("path_display") or "").strip("/").split("/")
    folder = parts[-2] if len(parts) >= 2 else ""
    return _("item_in_folder", name=name, folder=folder) if folder else name
