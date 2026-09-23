# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
# Low-vision appearance: UI font scaling + a basic high-contrast theme.
# Applied recursively to a window and its children. Idempotent — re-applying (or
# toggling off) restores the original sizes/colours, so it never compounds.
import wx
import core.api

_SCALES = {"normal": 1.0, "large": 1.25, "xlarge": 1.5}

# High-contrast palette (bright yellow on black — a common low-vision choice).
_HC_BG = wx.Colour(0, 0, 0)
_HC_FG = wx.Colour(255, 255, 0)


def _cfg():
    return core.api.load_data("Core")


def get_scale_key():
    return _cfg().get("ui_font_scale", "normal")


def get_scale():
    return _SCALES.get(get_scale_key(), 1.0)


def is_high_contrast():
    return bool(_cfg().get("high_contrast", False))


def apply_appearance(window):
    """Apply the configured font scale + high-contrast theme to `window` and every
    descendant. Safe and idempotent; call after a window's UI is built and again
    whenever the settings change."""
    if window is None:
        return
    try:
        scale = get_scale()
        hc = is_high_contrast()
        _apply_recursive(window, scale, hc)
        window.Refresh()
    except Exception:
        pass


def _apply_recursive(win, scale, hc):
    # --- Font: scale relative to each control's ORIGINAL size (captured once) ---
    try:
        f = win.GetFont()
        if f and f.IsOk():
            if not hasattr(win, "_hariku_base_pt"):
                win._hariku_base_pt = f.GetPointSize()
            base = win._hariku_base_pt or 9
            nf = wx.Font(f)
            nf.SetPointSize(max(6, int(round(base * scale))))
            win.SetFont(nf)
    except Exception:
        pass

    # --- Colours: high-contrast on, or reset to system default when off ---
    try:
        if hc:
            win.SetBackgroundColour(_HC_BG)
            win.SetForegroundColour(_HC_FG)
        else:
            win.SetBackgroundColour(wx.NullColour)
            win.SetForegroundColour(wx.NullColour)
    except Exception:
        pass

    try:
        for child in win.GetChildren():
            _apply_recursive(child, scale, hc)
    except Exception:
        pass
