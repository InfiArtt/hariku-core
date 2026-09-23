# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Core API for displaying HTML content in a WebView window that is isolated from
Hariku's main process (so it cannot crash the app via the keyboard hook).

Usage from an extension:
    import core.webview
    core.webview.show_html(html_string, title="Window Title")

    # Or if the HTML already lives in a file:
    core.webview.show_html_file(filepath, title="Window Title")
"""

import os
import sys
import tempfile
import subprocess
import uuid
import logging

logger = logging.getLogger(__name__)

# Path to the host script.
_HOST_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webview_host.py")


def _get_python_exe():
    """Return the path of the currently running Python executable."""
    return sys.executable


def show_html(html_content: str, title: str = "Hariku Viewer",
              width: int = 850, height: int = 650) -> bool:
    """
    Show an HTML string in an isolated WebView window.

    Because it runs in a separate subprocess, this window:
    - Cannot crash the Hariku process
    - Is not affected by the WH_KEYBOARD_LL hook
    - Fully supports NVDA Browse Mode (H, T, L, K, I)

    Args:
        html_content: Complete HTML string (including <html> and <head>).
        title: Window title to display.
        width: Initial window width (pixels).
        height: Initial window height (pixels).

    Returns:
        True if the subprocess was launched successfully.
    """
    try:
        # [SEC MED-1] Use UUID-based filename to prevent predictable temp file
        # race conditions and content injection by other local processes.
        temp_dir = os.path.join(tempfile.gettempdir(), "hariku2", "webview")
        os.makedirs(temp_dir, exist_ok=True)

        unique_id = uuid.uuid4().hex
        html_path = os.path.join(temp_dir, f"view_{unique_id}.html")

        # Exclusive creation (O_EXCL) prevents TOCTOU: if file somehow
        # already exists with same UUID, we fail-safe rather than overwrite.
        fd = os.open(html_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_content)

        return show_html_file(html_path, title, width, height)

    except Exception as e:
        logger.error("core.webview.show_html failed: %s", e)
        return False


def show_html_file(html_path: str, title: str = "Hariku Viewer",
                   width: int = 850, height: int = 650) -> bool:
    """
    Show an HTML file in an isolated WebView window.

    Args:
        html_path: Absolute path to the HTML file.
        title: Window title.
        width: Initial window width.
        height: Initial window height.

    Returns:
        True if the subprocess was launched successfully.
    """
    try:
        python_exe = _get_python_exe()

        # CREATE_NO_WINDOW so no black console window appears.
        flags = 0x08000000  # CREATE_NO_WINDOW

        proc = subprocess.Popen(
            [
                python_exe,
                _HOST_SCRIPT,
                html_path,
                title,
                str(width),
                str(height),
            ],
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        logger.info("WebView subprocess launched (PID %s) for: %s", proc.pid, html_path)
        return True

    except Exception as e:
        logger.error("core.webview.show_html_file failed: %s", e)
        return False
