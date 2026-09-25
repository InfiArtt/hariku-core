# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Orbit's own words (the window, the Preferences page, the connection's news,
the help), in English and Indonesian (casual: "kamu", "aku"). What happens on
the station comes from the server, already in the player's language. No wx.
"""

import os

from core.i18n import get_current_language, get_translator

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("orbit", os.path.join(EXT_DIR, "locales"))


def user_language():
    """ "id" or "en": what Orbit asks the server to speak."""
    code = (get_current_language() or "en").split("-")[0].lower()
    return code if code in ("id", "en") else "en"
