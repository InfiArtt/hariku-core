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
the help), in English: Orbit is played in English, so locales/ has only
en.json, and Hariku falls back to it whatever its language. What happens on
the station comes from the server, in English too. No wx.
"""

import os

from core.i18n import get_translator

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
LANGUAGE = "en"          # what Orbit asks the server to speak, and its players' voices' language
_ = get_translator("orbit", os.path.join(EXT_DIR, "locales"))
