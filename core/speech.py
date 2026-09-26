# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
import queue
import sys
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
        # to whichever reader is running (NVDA, JAWS, ZoomText, and others whose
        # client libraries are present). Enable SAPI 5 as a last-resort fallback
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
    Speak text using Tolk (via cytolk). Right after a command from the command
    bar (core.voice.route_speech), Hariku Voice may speak it instead; braille
    still gets it.
    """
    import core.api
    from core.events import bus

    # core.voice is only loaded once Hariku runs; before that nothing is routed.
    voice = sys.modules.get("core.voice")
    if voice is not None:
        try:
            if voice.speak_routed(text, interrupt):
                return
        except Exception:
            logger.exception("Giving speech to Hariku Voice failed; the screen reader speaks it")

    config = core.api.load_data("Core")
    
    payload = {"text": text, "interrupt": interrupt, "cancel": False}
    bus.emit("on_before_speak", payload)
    
    if payload.get("cancel"):
        return
        
    final_text = payload.get("text", text)
    final_interrupt = payload.get("interrupt", interrupt)
    _deliver(final_text, final_interrupt, config, speech=True)


# Everything for Tolk goes through one queue and one worker thread (since 2.11),
# so lines reach the screen reader in the order they were spoken: with a thread
# for each line, two lines spoken at once (a game's reply and the note after it)
# could arrive the other way round, and Tolk was called from several threads at
# once. The worker starts with the first line and lives as long as Hariku; a
# failed line is logged and the next one still goes.
_queue = queue.Queue()
_worker = None
_worker_lock = threading.Lock()


def _to_tolk(text, interrupt, speech, braille_on, silence):
    try:
        if silence and interrupt:
            tolk.silence()
        if speech and braille_on:
            tolk.output(text, interrupt)   # speech + braille
        elif speech:
            tolk.speak(text, interrupt)     # speech only
        elif braille_on:
            tolk.braille(text)              # braille only
    except Exception as e:
        logger.error(f"Tolk speak error: {e}")


def _run_queue():
    while True:
        job = _queue.get()
        _to_tolk(*job)


def _start_worker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run_queue, daemon=True, name="hariku-speech")
            _worker.start()


def _deliver(text, interrupt, config, speech=True, braille=None, silence=False):
    """Hand text to Tolk on the speech worker thread, in order. `braille` None
    follows the braille_output setting; `silence` first stops the screen
    reader's speech."""
    actual_interrupt = interrupt and config.get("interrupt_speech", True)

    # Braille output: Tolk's output() sends to BOTH speech and a connected
    # braille display; speak() is speech-only. Default on; users can turn braille
    # off in Preferences (some prefer speech alone).
    braille_on = config.get("braille_output", True) if braille is None else (
        braille and config.get("braille_output", True))

    if TOLK_LOADED:
        _queue.put((text, actual_interrupt, speech, braille_on, silence))
        _start_worker()
    elif speech:
        # Fallback console print
        print(f"[SPEECH] {text}")


def braille(text, interrupt=False):
    """Show text on a braille display without speaking it (since 2.7). Hariku
    Voice uses it while a voice reads the text aloud, so braille users still get
    it. Follows the braille_output setting. With `interrupt` (and "Interrupt
    speech" on), the screen reader stops talking first, as speak() would."""
    import core.api
    _deliver(text, interrupt, core.api.load_data("Core"), speech=False, silence=True)


def silence():
    """Stop the screen reader's speech now (since 2.7), for example right
    before listening to the microphone, so speakers don't talk into it. Braille
    is not affected. Returns whether Tolk was asked."""
    if not TOLK_LOADED:
        return False
    try:
        tolk.silence()
        return True
    except Exception as e:
        logger.error(f"Tolk silence error: {e}")
        return False


def speak_announced(text, interrupt=False, braille=True):
    """Speak text through the screen reader after on_before_speak has already
    run for it (Hariku Voice's fallback), so extensions don't see it twice.
    `braille=False` when the braille display already has it."""
    import core.api
    _deliver(text, interrupt, core.api.load_data("Core"), speech=True,
             braille=None if braille else False)

def unload_speech():
    if TOLK_LOADED:
        try:
            tolk.unload()
            logger.info("Tolk unloaded.")
        except Exception as e:
            logger.error(f"Error unloading tolk: {e}")

# Initialize immediately when the module is imported.
init_speech()
