import sys
import threading
import logging
import wx
import json
import traceback
import platform
import urllib.request

import core.api
import core.constants
import core.endpoints

logger = logging.getLogger(__name__)

# Crash reports are sent to the InfiArtt backend (see core.endpoints).
API_URL = core.endpoints.CRASH_REPORT_URL

def _send_report_silently(exc_type, exc_value, exc_traceback):
    try:
        config = core.api.load_data("Core")
        lang = config.get("language", "en")

        traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        payload = {
            "app_version": core.constants.CORE_VERSION,
            "os_info": platform.platform(),
            "language": lang,
            "error_type": exc_type.__name__,
            "error_message": str(exc_value),
            "traceback": traceback_text
        }

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(API_URL, data=data, headers={'Content-Type': 'application/json'})

        with urllib.request.urlopen(req, timeout=5) as response:
            pass
    except Exception as e:
        # A failed crash upload must never disrupt the crash flow.
        logger.error(f"Failed to silently send crash report: {e}")

def _handle_exception(exc_type, exc_value, exc_traceback):
    """
    Global exception hook.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    # Read preference
    try:
        config = core.api.load_data("Core")
        behavior = config.get("crash_report_behavior", "ask")
    except Exception:
        behavior = "ask"
        
    if behavior == "never":
        sys.exit(1)
        return
        
    if behavior == "auto":
        # Send silently then die
        _send_report_silently(exc_type, exc_value, exc_traceback)
        sys.exit(1)
        return

    # If behavior == "ask"
    app = wx.GetApp()
    
    import threading
    if app:
        # Kalau crash terjadi di thread lain, lempar ke main thread
        if threading.current_thread() is not threading.main_thread():
            wx.CallAfter(_show_dialog, exc_type, exc_value, exc_traceback)
        else:
            # Kalau di main thread, langsung panggil (meskipun MainLoop belum jalan, ShowModal punya loop sendiri)
            _show_dialog(exc_type, exc_value, exc_traceback)
    else:
        # App not running or crashed before wx.App was created
        app = wx.App(False)
        _show_dialog(exc_type, exc_value, exc_traceback)

def _show_dialog(exc_type, exc_value, exc_traceback):
    from ui.crash_dialog import CrashDialog
    from core.speech import speak
    
    try:
        speak("Oops! Hariku encountered a fatal error.", interrupt=True)
    except:
        pass
        
    dlg = CrashDialog(None, exc_type, exc_value, exc_traceback)
    dlg.ShowModal()
    dlg.Destroy()
    
    sys.exit(1)

def _handle_unraisable(unraisable):
    """
    Handles exceptions that happen in __del__ or threading where standard excepthook fails.
    """
    logger.critical(f"Unraisable exception: {unraisable.err_msg}", exc_info=(unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback))

def _handle_thread_exception(args):
    """
    Handles exceptions thrown in background threads.
    """
    logger.critical(f"Thread exception in {args.thread.name}", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    _handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

def setup():
    """
    Register global hooks.
    """
    sys.excepthook = _handle_exception
    sys.unraisablehook = _handle_unraisable
    threading.excepthook = _handle_thread_exception
    logger.info("Crash handler installed.")
