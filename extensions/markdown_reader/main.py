"""
Markdown Reader — Hariku V2 Extension

Open, read, and navigate Markdown (.md) files with full screen reader
accessibility. Features heading navigation, section reading, copy to
clipboard, and recent files history.

Keyboard shortcuts (inside the reader dialog):
    Ctrl+O           Open a new file
    Alt+Up/Down      Navigate between headings
    Ctrl+R           Read the current section aloud
    Ctrl+Shift+C     Copy entire document to clipboard
    Escape           Close the dialog
"""

import os
import logging
import wx

from core.speech import speak
from core.i18n import get_translator
import core.api
import core.hotkeys

logger = logging.getLogger(__name__)

# ── i18n setup ──────────────────────────────────────────────────────

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("markdown_reader", os.path.join(EXT_DIR, "locales"))

# ── State ───────────────────────────────────────────────────────────

MAX_RECENT = 10
_event_bus = None


# ── Recent files management ─────────────────────────────────────────

def _load_recent():
    """Return the list of recently opened file paths."""
    data = core.api.load_data("MarkdownReader")
    return data.get("recent_files", [])


def _save_recent(recent):
    """Persist the recent files list."""
    data = core.api.load_data("MarkdownReader")
    data["recent_files"] = recent[:MAX_RECENT]
    core.api.save_data("MarkdownReader", data)


def _add_recent(filepath):
    """Add *filepath* to the top of the recent-files list."""
    recent = _load_recent()
    # Remove if already present, then prepend
    abs_path = os.path.abspath(filepath)
    recent = [p for p in recent if os.path.abspath(p) != abs_path]
    recent.insert(0, abs_path)
    _save_recent(recent)


# ── Actions ─────────────────────────────────────────────────────────

def _action_open_file():
    """Hotkey action: open a Markdown file via file picker."""
    def _do_open():
        from reader_dialog import open_with_picker
        path = open_with_picker(_)
        if path:
            _add_recent(path)
            logger.info("Opened markdown file: %s", path)
    wx.CallAfter(_do_open)


def _action_open_recent():
    """Hotkey action: show a list of recently opened files."""
    def _do_recent():
        recent = _load_recent()
        if not recent:
            speak(_("no_recent"), interrupt=True)
            return

        parent = core.api.main_window_instance

        # Build a choice list with just filenames (show full path in status)
        choices = []
        valid_paths = []
        for path in recent:
            if os.path.isfile(path):
                choices.append(f"{os.path.basename(path)}  —  {os.path.dirname(path)}")
                valid_paths.append(path)

        if not choices:
            speak(_("no_recent"), interrupt=True)
            return

        # Add a "Clear recent" option at the end
        choices.append(f"⊘ {_('clear_recent')}")

        dlg = wx.SingleChoiceDialog(
            parent,
            _("recent_files"),
            _("ext_name"),
            choices)

        try:
            if dlg.ShowModal() == wx.ID_OK:
                idx = dlg.GetSelection()
                if idx == len(choices) - 1:
                    # Clear recent files
                    _save_recent([])
                    speak(_("recent_cleared"), interrupt=True)
                elif idx < len(valid_paths):
                    filepath = valid_paths[idx]
                    _add_recent(filepath)
                    from reader_dialog import open_reader
                    open_reader(filepath, _)
        finally:
            dlg.Destroy()
            
    wx.CallAfter(_do_recent)


# ── Tray menu integration ──────────────────────────────────────────

def _on_tray_menu(menu, frame):
    """Add 'Open Markdown File' item to the system tray menu."""
    item = menu.Append(wx.ID_ANY, _("tray_open_md"))
    frame.Bind(wx.EVT_MENU, lambda e: _action_open_file(), item)


# ── Extension lifecycle ─────────────────────────────────────────────

def register(bus):
    """Called by the extension manager to register this extension."""
    global _event_bus
    _event_bus = bus

    # Register hotkeys
    core.hotkeys.register_action(
        _("ext_name"),
        "open_markdown",
        _("hotkey_open_desc"),
        ord("M"),           # Default: Ctrl+M
        True,                # Ctrl
        _action_open_file,
        default_shift=False,
        default_alt=False,
    )

    core.hotkeys.register_action(
        _("ext_name"),
        "open_recent_markdown",
        _("hotkey_recent_desc"),
        ord("M"),           # Default: Ctrl+Shift+M
        True,                # Ctrl
        _action_open_recent,
        default_shift=True,
        default_alt=False,
    )

    # Add to tray menu
    bus.subscribe("on_build_tray_menu", _on_tray_menu)

    logger.info("Markdown Reader extension registered.")


def teardown():
    """Called by the extension manager when shutting down."""
    logger.info("Markdown Reader extension unloaded.")
