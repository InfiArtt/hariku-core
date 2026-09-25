# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
An internet radio player: one live MP3 or AAC stream (Icecast, Shoutcast,
plain HTTP or HTTPS) at a time, through Windows Media Foundation's MFPlay,
called with plain ctypes like core/voice_sapi.py calls SAPI. Nothing to
download or bundle: MFPlay (mfplay.dll) is part of Windows 7 to 11, except
the "N" editions without the Media Feature Pack, where is_supported() is
False.

Why not MCI: core.voice.play_file() and core.sounds use MCI ("mpegvideo" is
DirectShow underneath). Given an http:// URL, DirectShow's URL source tries to
download the whole file before it opens, so a live stream never opens (tried:
the open call was still waiting after 40 seconds). Media Foundation's network
source streams: a live station opens in about a second, and its volume is set
per stream (IMFPMediaPlayer::SetVolume only changes this player's streams, not
Hariku's other sounds or the Windows mixer).

How it runs: each play() starts a session on its own thread, a COM
single-threaded apartment that pumps its window messages (MFPlay uses a
hidden window on the thread that created it, even without a callback). The
stream is opened synchronously (CreateMediaItemFromURL with fSync), so a
failure comes back as an HRESULT; a newer play() or stop() makes an older
session end as soon as its open returns. The session sets the item, waits for
MFPlay to be ready, plays, and then only follows the volume (moved in small
steps, so ducking fades rather than jumps) and watches that the stream keeps
playing.

    player = RadioPlayer()
    player.play(url, volume=35, on_event=handler)   # handler(kind, detail)
    player.set_ducked(True)       # lower it while something is spoken
    player.set_volume(50)
    player.stop()

Events, on the session's thread: ("connecting", url), ("playing", url),
("error", kind) with kind "unsupported" (no Media Foundation), "format",
"not_found", "offline", "open" or "timeout", ("dropped", url) when a playing
stream ends by itself, and ("stopped", url) after stop() or a newer play().
No wx: a future Radio extension can use it as it is.
"""

import ctypes
import ctypes.wintypes as wt
import itertools
import logging
import threading
import time

logger = logging.getLogger(__name__)

DUCK_FACTOR = 0.3            # the radio's volume while something is spoken
RAMP_STEP = 0.06             # at most this much volume change per poll (a short fade)
POLL_SECONDS = 0.05
READY_TIMEOUT = 10.0         # the item set, MFPlay ready to play
START_TIMEOUT = 15.0         # playing after Play()
DROP_SECONDS = 5.0           # not playing this long after it played: the stream ended

# MFP_MEDIAPLAYER_STATE
STATE_EMPTY, STATE_STOPPED, STATE_PLAYING, STATE_PAUSED, STATE_SHUTDOWN = range(5)

# HRESULTs that say what went wrong.
_ERROR_KINDS = {
    0xC00D36C4: "format",       # MF_E_UNSUPPORTED_BYTESTREAM_TYPE
    0xC00D36C3: "format",       # MF_E_UNSUPPORTED_SCHEME
    0xC00D36B4: "format",       # MF_E_INVALIDMEDIATYPE
    0xC00D001A: "not_found",    # NS_E_FILE_NOT_FOUND
    0x80070002: "not_found",
    0xC00D2EE2: "not_found",    # NS_E_WMPCORE_... / HTTP 404 through MF
    0x80072EE2: "offline",      # WININET timeout
    0x80072EE7: "offline",      # name not resolved
    0x80072EFD: "offline",      # cannot connect
    0x80072EFE: "offline",      # connection aborted
    0xC00D2EE0: "offline",      # NS_E_CONNECTION_FAILURE
}


class RadioError(Exception):
    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


def error_kind(hresult):
    return _ERROR_KINDS.get(hresult & 0xFFFFFFFF, "open")


# ------------------------------------------------------------
# MFPlay through ctypes
# ------------------------------------------------------------

# IMFPMediaPlayer vtable slots (IUnknown takes 0-2).
_PLAY, _STOP = 3, 5
_GET_STATE = 13
_CREATE_ITEM_FROM_URL = 14
_SET_MEDIA_ITEM = 16
_SET_VOLUME = 20
_SHUTDOWN = 38
_RELEASE = 2

_COINIT_APARTMENTTHREADED = 0x2
_MF_VERSION = 0x00020070
_PM_REMOVE = 0x1

_prototypes = {}
_dlls = {}
_dll_lock = threading.Lock()


def _vcall(ptr, index, argtypes, *args):
    """Call vtable slot `index` of COM pointer `ptr`; the HRESULT as unsigned."""
    argtypes = tuple(argtypes)
    prototype = _prototypes.get(argtypes)
    if prototype is None:
        prototype = _prototypes[argtypes] = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                                               *argtypes)
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return prototype(vtable[index])(ptr, *args) & 0xFFFFFFFF


def _failed(hresult):
    return hresult & 0x80000000 != 0


def _dll(name):
    """Our own instance of a DLL (argtypes stay private), or None."""
    with _dll_lock:
        if name not in _dlls:
            try:
                dll = ctypes.WinDLL(name)
            except OSError:
                dll = None
            if dll is not None and name == "mfplay":
                dll.MFPCreateMediaPlayer.argtypes = [ctypes.c_wchar_p, wt.BOOL, wt.DWORD,
                                                     ctypes.c_void_p, wt.HWND,
                                                     ctypes.POINTER(ctypes.c_void_p)]
                dll.MFPCreateMediaPlayer.restype = ctypes.c_long
            elif dll is not None and name == "ole32":
                dll.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]
                dll.CoInitializeEx.restype = ctypes.c_long
                dll.CoUninitialize.argtypes = []
                dll.CoUninitialize.restype = None
            elif dll is not None and name == "mfplat":
                dll.MFStartup.argtypes = [wt.ULONG, wt.DWORD]
                dll.MFStartup.restype = ctypes.c_long
                dll.MFShutdown.argtypes = []
                dll.MFShutdown.restype = ctypes.c_long
            elif dll is not None and name == "user32":
                dll.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT,
                                             wt.UINT]
                dll.PeekMessageW.restype = wt.BOOL
                dll.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
                dll.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
                dll.DispatchMessageW.restype = ctypes.c_ssize_t
            _dlls[name] = dll
        return _dlls[name]


def is_supported():
    """Whether this Windows has MFPlay (Media Foundation)."""
    return _dll("mfplay") is not None


class MFPlayBackend:
    """One stream through MFPlay, used from a single thread (the session's)."""

    def __init__(self):
        self._player = ctypes.c_void_p()
        self._com = False
        self._mf = False

    def open(self, url):
        """Start COM and Media Foundation on this thread and open the stream
        (network and its headers; nothing is played). Raises RadioError."""
        mfplay, ole32 = _dll("mfplay"), _dll("ole32")
        if mfplay is None or ole32 is None:
            raise RadioError("unsupported")
        hr = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED) & 0xFFFFFFFF
        self._com = not _failed(hr)            # S_OK or S_FALSE: ours to undo
        mfplat = _dll("mfplat")
        if mfplat is not None:
            self._mf = not _failed(mfplat.MFStartup(_MF_VERSION, 0) & 0xFFFFFFFF)
        hr = mfplay.MFPCreateMediaPlayer(None, False, 0, None, None,
                                         ctypes.byref(self._player)) & 0xFFFFFFFF
        if _failed(hr) or not self._player.value:
            raise RadioError("unsupported", f"MFPCreateMediaPlayer 0x{hr:08X}")
        item = ctypes.c_void_p()
        hr = _vcall(self._player, _CREATE_ITEM_FROM_URL,
                    [ctypes.c_wchar_p, wt.BOOL, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)],
                    url, True, 0, ctypes.byref(item))
        if _failed(hr) or not item.value:
            raise RadioError(error_kind(hr), f"CreateMediaItemFromURL 0x{hr:08X}")
        try:
            hr = _vcall(self._player, _SET_MEDIA_ITEM, [ctypes.c_void_p], item)
        finally:
            _vcall(item, _RELEASE, [])         # the player keeps its own reference
        if _failed(hr):
            raise RadioError("open", f"SetMediaItem 0x{hr:08X}")

    def state(self):
        value = ctypes.c_int(STATE_EMPTY)
        if self._player.value:
            _vcall(self._player, _GET_STATE, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(value))
        return value.value

    def play(self):
        hr = _vcall(self._player, _PLAY, [])
        if _failed(hr):
            raise RadioError("open", f"Play 0x{hr:08X}")

    def set_volume(self, level):
        if self._player.value:
            _vcall(self._player, _SET_VOLUME, [ctypes.c_float],
                   ctypes.c_float(max(0.0, min(1.0, float(level)))))

    def pump(self):
        """Serve the window messages MFPlay posts to this thread."""
        user32 = _dll("user32")
        if user32 is None:
            return
        msg = wt.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, _PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def close(self):
        if self._player.value:
            for index in (_STOP, _SHUTDOWN, _RELEASE):
                try:
                    _vcall(self._player, index, [])
                except Exception:
                    pass
            self._player = ctypes.c_void_p()
        if self._mf:
            try:
                _dll("mfplat").MFShutdown()
            except Exception:
                pass
            self._mf = False
        if self._com:
            try:
                _dll("ole32").CoUninitialize()
            except Exception:
                pass
            self._com = False


# ------------------------------------------------------------
# The player
# ------------------------------------------------------------

class _Session:
    _ids = itertools.count(1)

    def __init__(self, url, on_event):
        self.id = next(self._ids)
        self.url = url
        self.on_event = on_event
        self.stopped = threading.Event()
        self.thread = None


class RadioPlayer:
    """One stream at a time; see the module notes. Thread-safe."""

    def __init__(self, backend_factory=MFPlayBackend, supported=is_supported,
                 clock=time.monotonic, sleep=time.sleep, start_thread=None):
        self._backend_factory = backend_factory
        self._supported = supported
        self._clock = clock
        self._sleep = sleep
        self._start_thread = start_thread or self._thread
        self._lock = threading.Lock()
        self._session = None
        self._volume = 35
        self._ducked = False
        self.playing_url = None

    @staticmethod
    def _thread(target, session):
        thread = threading.Thread(target=target, args=(session,), daemon=True,
                                  name="world-trip-radio")
        session.thread = thread
        thread.start()

    # --- control (any thread) --------------------------------------------------------

    def play(self, url, volume=None, on_event=None):
        """Play `url` (stopping what played). Returns the session id; events
        from older sessions are never sent after this returns."""
        if volume is not None:
            self.set_volume(volume)
        session = _Session(str(url), on_event)
        with self._lock:
            old, self._session = self._session, session
            self.playing_url = None
        if old is not None:
            old.stopped.set()
        if not self._supported():
            self._emit(session, "error", "unsupported")
            with self._lock:
                if self._session is session:
                    self._session = None
            return session.id
        self._start_thread(self._run, session)
        return session.id

    def stop(self):
        with self._lock:
            session, self._session = self._session, None
            self.playing_url = None
        if session is not None:
            session.stopped.set()

    def set_volume(self, volume):
        try:
            volume = int(volume)
        except (TypeError, ValueError):
            return
        with self._lock:
            self._volume = max(0, min(100, volume))

    @property
    def volume(self):
        with self._lock:
            return self._volume

    def set_ducked(self, ducked):
        with self._lock:
            self._ducked = bool(ducked)

    @property
    def ducked(self):
        with self._lock:
            return self._ducked

    def is_active(self):
        """A stream is opening or playing."""
        with self._lock:
            return self._session is not None

    def is_playing(self):
        with self._lock:
            return self._session is not None and self.playing_url is not None

    def target_level(self):
        """The volume the stream moves toward, 0.0 to 1.0."""
        with self._lock:
            level = self._volume / 100.0
            return level * DUCK_FACTOR if self._ducked else level

    def shutdown(self, wait=2.0):
        """Stop and wait a moment for the session thread (Hariku is closing)."""
        with self._lock:
            session = self._session
        self.stop()
        thread = getattr(session, "thread", None)
        if thread is not None and thread is not threading.current_thread():
            thread.join(wait)

    # --- the session (its own thread) ----------------------------------------------------

    def _current(self, session):
        with self._lock:
            return self._session is session and not session.stopped.is_set()

    def _emit(self, session, kind, detail=None):
        if session.on_event is None:
            return
        if kind not in ("stopped",) and session.stopped.is_set():
            return
        try:
            session.on_event(kind, detail)
        except Exception:
            logger.exception("[World Trip] A radio event handler failed")

    def _wait_for(self, backend, session, states, timeout):
        """Pump until MFPlay reaches one of `states`; False on stop or timeout."""
        deadline = self._clock() + timeout
        while self._current(session):
            backend.pump()
            if backend.state() in states:
                return True
            if self._clock() > deadline:
                return False
            self._sleep(POLL_SECONDS)
        return False

    def _run(self, session):
        backend = self._backend_factory()
        played = False
        ended = "stopped"
        try:
            self._emit(session, "connecting", session.url)
            try:
                backend.open(session.url)
            except RadioError as e:
                logger.info(f"[World Trip] The station didn't open: {e}")
                self._emit(session, "error", e.kind)
                ended = None
                return
            if not self._current(session):
                return
            level = 0.0
            backend.set_volume(level)          # start silent, then fade in
            if not self._wait_for(backend, session, (STATE_STOPPED, STATE_PLAYING),
                                  READY_TIMEOUT):
                if self._current(session):
                    self._emit(session, "error", "timeout")
                    ended = None
                return
            backend.play()
            if not self._wait_for(backend, session, (STATE_PLAYING,), START_TIMEOUT):
                if self._current(session):
                    self._emit(session, "error", "timeout")
                    ended = None
                return
            played = True
            with self._lock:
                if self._session is session:
                    self.playing_url = session.url
            self._emit(session, "playing", session.url)
            not_playing_since = None
            while self._current(session):
                backend.pump()
                target = self.target_level()
                if abs(target - level) > 1e-3:
                    step = max(-RAMP_STEP, min(RAMP_STEP, target - level))
                    level = max(0.0, min(1.0, level + step))
                    backend.set_volume(level)
                if backend.state() == STATE_PLAYING:
                    not_playing_since = None
                elif not_playing_since is None:
                    not_playing_since = self._clock()
                elif self._clock() - not_playing_since > DROP_SECONDS:
                    ended = "dropped"
                    break
                self._sleep(POLL_SECONDS)
        except Exception:
            logger.exception("[World Trip] The radio failed")
            if not played:
                self._emit(session, "error", "open")
                ended = None
            else:
                ended = "dropped"
        finally:
            try:
                backend.close()
            except Exception:
                logger.exception("[World Trip] Closing the radio failed")
            with self._lock:
                if self._session is session:
                    if ended != "stopped":       # it failed or ended by itself
                        self._session = None
                    self.playing_url = None
            if ended == "dropped":
                self._emit(session, "dropped", session.url)
            elif ended == "stopped":
                self._emit(session, "stopped", session.url)
