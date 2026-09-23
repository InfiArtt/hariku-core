# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import logging

logger = logging.getLogger(__name__)

# Format: {"Category Name": [ {"name": panel_name, "create": create_func, "apply": apply_func}, ... ] }
_panels = {}

def register_panel(category, panel_name, create_func, apply_func=None):
    """
    Register a settings panel with the Unified Preferences window.
    - category: Panel category (e.g. "Extensions").
    - panel_name: Panel name (e.g. "NASA Settings").
    - create_func: Function(parent_window) returning a wx.Panel instance.
    - apply_func: Function() called when the user presses OK in Preferences.
    """
    if category not in _panels:
        _panels[category] = []
    
    _panels[category].append({
        "name": panel_name,
        "create": create_func,
        "apply": apply_func
    })
    logger.info(f"Registered preference panel: [{category}] {panel_name}")

def get_all_panels():
    return _panels
