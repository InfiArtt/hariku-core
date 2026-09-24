# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

APP_NAME = "Hariku"
CORE_VERSION = "2.8.0"

# The oldest Hariku an extension can be made for and still run here: an
# extension whose last_tested_core_version (or, without one, its
# minimum_core_version) is older is incompatible, like an NVDA add-on older
# than NVDA's backwards-compatible API. Raise it only when a core change breaks
# older extensions; no 2.x change has, so every extension made so far runs.
EXTENSION_API_BACK_COMPAT = "1.0"

# Split major and minor for extension validation (e.g. "2.0").
_parts = CORE_VERSION.split(".")
if len(_parts) >= 2:
    CORE_VERSION_FLOAT = float(f"{_parts[0]}.{_parts[1]}")
else:
    CORE_VERSION_FLOAT = float(_parts[0])
