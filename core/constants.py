# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

APP_NAME = "Hariku"
CORE_VERSION = "2.2.0"

# Split major and minor for extension validation (e.g. "2.0").
_parts = CORE_VERSION.split(".")
if len(_parts) >= 2:
    CORE_VERSION_FLOAT = float(f"{_parts[0]}.{_parts[1]}")
else:
    CORE_VERSION_FLOAT = float(_parts[0])
