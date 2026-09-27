# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Hariku collects no analytics or telemetry (see PRIVACY.md).

The core once sent an anonymous startup ping to a server on the old
novarealm.cloud domain; that server was retired and the ping removed. Since
core 2.11 there is no setting for it either: Preferences no longer has a
telemetry box, and old "telemetry_enabled" / "telemetry_id" keys in Core.json
are ignored.

This module stays only because DEVELOPERS.md documents telemetry.is_enabled()
for extensions, so an extension that calls it keeps working. hariku.py imports
it so the compiled build includes it.
"""

# Kept for code that checks it; there is nothing to turn back on.
TELEMETRY_DISABLED = True


def is_enabled():
    """Always False: Hariku has no usage-data setting and sends no usage data.

    An extension that honours this sends no analytics. One that wants to must
    ask the user itself and say so in its description.
    """
    return False


def record_startup():
    """Does nothing. Kept so older callers keep working."""
    return None
