# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# ============================================================
# Routines — iOS-Shortcuts-style automation for Hariku V2.
# Entry point only. The extension is split into modules so parts can evolve
# independently:
#   engine.py   - pure trigger logic (conditions, placeholders, edge-fire) + specs
#   actions.py  - action runners (side effects)
#   runtime.py  - persistence, state context, event wiring, execution, register
#   ui.py       - Manage / Edit dialogs (Phase 2: iOS-Shortcuts-style builder)
# ============================================================
from runtime import register, teardown  # noqa: F401  (re-exported for the loader)
