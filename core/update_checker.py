# core/update_checker.py
"""
Background update checker for Hariku extensions.
Runs in a daemon thread shortly after startup so it doesn't block the UI.
"""

import threading
import logging
import wx

logger = logging.getLogger(__name__)

_BEHAVIOR_KEY  = "extension_update_behavior"  # "notify" | "do_nothing" | "auto_update"
_DEFAULT_BEHAVIOR = "notify"

def _get_behavior():
    import core.api
    config = core.api.load_data("Core")
    return config.get(_BEHAVIOR_KEY, _DEFAULT_BEHAVIOR)

def _show_notification(count):
    """Show a wx balloon / adv notification in the system tray."""
    try:
        import core.api
        title = "Extension Updates Available"
        msg   = (f"{count} extension update{'s' if count > 1 else ''} available. "
                 "Open Extension Manager to update.")
        # Use wx.adv.NotificationMessage for a system-tray toast
        note = wx.adv.NotificationMessage(title, msg)
        note.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)
    except Exception as e:
        logger.error(f"Failed to show update notification: {e}")

def _run_check():
    import core.store
    from core.speech import speak

    behavior = _get_behavior()
    if behavior == "do_nothing":
        return

    logger.info("Checking for extension updates...")
    try:
        updates = core.store.check_for_updates()
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        return

    if not updates:
        logger.info("All extensions are up to date.")
        return

    logger.info(f"Found {len(updates)} extension update(s): {[u['id'] for u in updates]}")

    if behavior == "notify":
        wx.CallAfter(_show_notification, len(updates))

    elif behavior == "auto_update":
        def _do_auto():
            speak("Updating extensions...")
            success, fail = core.store.auto_update_extensions(updates)
            if success:
                names = ", ".join(u["name"] for u in success)
                logger.info(f"Auto-updated: {names}")
                speak("Updates applied. Restart required to take effect.")
            if fail:
                names = ", ".join(u["name"] for u in fail)
                logger.error(f"Failed to update: {names}")
                speak(f"Some updates failed: {names}")
        wx.CallAfter(_do_auto)

def start(delay_seconds=6):
    """
    Starts the update check in a background thread after `delay_seconds`.
    Call this once after load_all_extensions() completes.
    """
    def _delayed():
        import time
        time.sleep(delay_seconds)
        _run_check()

    t = threading.Thread(target=_delayed, daemon=True, name="ext-update-checker")
    t.start()
    logger.info(f"Extension update checker scheduled (delay={delay_seconds}s).")
