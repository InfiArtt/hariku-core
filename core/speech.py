# hariku2/core/speech.py
import threading
import logging
from cytolk import tolk

logger = logging.getLogger(__name__)

TOLK_LOADED = False

def init_speech():
    global TOLK_LOADED
    try:
        tolk.load()
        # Tolk is a UNIVERSAL screen-reader layer (not NVDA-only): it auto-routes
        # to whichever reader is running — NVDA, JAWS, System Access, ZoomText,
        # SuperNova/Dolphin, Window-Eyes. Enable SAPI 5 as a last-resort fallback
        # so users with NO screen reader still hear output via built-in Windows
        # TTS. This only activates when no screen reader is detected, so it never
        # changes behaviour for NVDA/JAWS/etc. users.
        try:
            tolk.try_sapi(True)
        except Exception as e:
            logger.warning(f"Could not enable SAPI fallback: {e}")
        TOLK_LOADED = True
        try:
            reader = tolk.detect_screen_reader()
        except Exception:
            reader = None
        logger.info(f"Tolk loaded via cytolk (active reader: {reader or 'none — SAPI fallback'}).")
        return True
    except Exception as e:
        logger.error(f"Failed to load Tolk: {e}")
        return False

def speak(text, interrupt=False):
    """
    Mengucapkan teks menggunakan Tolk (melalui cytolk).
    """
    import core.api
    from core.events import bus
    
    config = core.api.load_data("Core")
    
    payload = {"text": text, "interrupt": interrupt, "cancel": False}
    bus.emit("on_before_speak", payload)
    
    if payload.get("cancel"):
        return
        
    final_text = payload.get("text", text)
    final_interrupt = payload.get("interrupt", interrupt)
    actual_interrupt = final_interrupt and config.get("interrupt_speech", True)

    if TOLK_LOADED:
        def _speak_worker():
            try:
                # Tolk output
                tolk.output(final_text, actual_interrupt)
            except Exception as e:
                logger.error(f"Tolk speak error: {e}")
        threading.Thread(target=_speak_worker, daemon=True).start()
    else:
        # Fallback console print
        print(f"[SPEECH] {final_text}")

def unload_speech():
    if TOLK_LOADED:
        try:
            tolk.unload()
            logger.info("Tolk unloaded.")
        except Exception as e:
            logger.error(f"Error unloading tolk: {e}")

# Langsung inisialisasi saat modul dimuat
init_speech()
