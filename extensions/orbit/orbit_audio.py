# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Orbit's sounds: which cue an event plays and from where, and the ambience.

cues_for(message) turns a server event into cues: [(name, pan, acoustics)].
A step you take is heard on the side you walk to (west on the left, east on
the right, north and south in the middle) on the floor you walk on, with the
room's echo; someone arriving from the west is heard on the left; the lift
hums up or down, a ladder clanks, an airlock hisses. An event's "sound"
field names a more specific cue (a level up, a harvest, the temple bell);
the event's kind is the fallback. orbit_mix finds and shapes the files.

Some cues come a moment later (timed_cues): the three reels of a slot
machine stopping one by one, left, middle, right, and then whether you won;
the dice landing; the dealer turning the cards; the beats of a Star Beat
rhythm at the arcade ("beats": the seconds at which each sounds). The words
wait for them, so the result isn't read before the dice have stopped
rolling. A cue the server names ("sound") with a side ("dir") is heard on
that side: the runaway robot's beeps, a meteor coming at you.

The ambience is a quiet loop for the kind of place you're in: the vents'
hum in corridors, the Cantina's murmur, the reactor's thrum in Engineering,
water and fans in Hydroponics, the hush of the Observation Deck, your own
breathing in a suit outside, the Belt's machinery, the soft air of a venue.
It plays through an MCI "mpegvideo" device of its own (every command for
such a device must come from the thread that opened it, so the player has a
thread), looping, at the volume the user set. It fades out and in between
places, and goes quiet while Hariku speaks: while Hariku Voice is busy, and
for about as long as the screen reader needs for a line (hush()).

The MCI calls go through `mci(command)`, so the tests give a fake. No wx.
"""

import ctypes
import logging
import queue
import threading
import time

logger = logging.getLogger(__name__)

# The cue for each kind of event (when the event names no cue of its own).
KIND_CUES = {
    "moved": "door", "arrive": "arrive", "leave": "leave", "whisper": "whisper",
    "say": "say", "shout": "shout", "emote": "emote",
    "said": "sent", "whispered": "sent", "shouted": "sent", "crew": "whisper", "crew_sent": "sent",
    "announce": "announce", "system": "announce",
    "paid": "success", "received": "coins", "gave": "coins", "trade": "coins",
    "failed": "fail", "error": "error", "mission": "mission", "task": "task", "offer": "offer",
}
# Kept for older callers: the kind's cue.
SOUND_FOR_KIND = KIND_CUES
DIR_PAN = {"n": 0.0, "s": 0.0, "e": 0.75, "w": -0.75, "ne": 0.5, "se": 0.5, "nw": -0.5, "sw": -0.5,
           "u": 0.0, "d": 0.0}
VIA_CUES = {"lift": ("lift_up", "lift_down"), "ladder": ("ladder", "ladder"),
            "slide": ("slide", "slide"), "airlock": ("airlock", "airlock")}
FLOORS = ("metal", "carpet", "grass", "stone", "rock", "suit", "wet", "wood", "snow", "sand", "dust")
AMBIENCES = ("vent", "cantina", "engine", "garden", "deck", "space", "belt", "venue", "mall", "casino",
             "gate", "moon", "colony", "ice", "bazaar", "forest", "neon", "arcade", "wedding")
# Other players' sounds (the "Other players' sounds" setting): what they do near you.
OTHERS_KINDS = ("say", "shout", "emote", "arrive", "leave")
TONE_GAP_SECONDS = 0.45
# The casino: when the reels stop (and where), and when the outcome of each game is heard.
REEL_STOPS = ((0.9, -0.75), (1.3, 0.0), (1.7, 0.75))
OUTCOME_AT = {"reels": 2.0, "dice": 1.2, "coinflip": 0.9, "cards": 0.35, "deal": 0.35}
OUTCOME_CUES = {"win": "win", "lose": "lose", "push": "push", "jackpot": "jackpot"}
# Star Beat (Pixel Pier's arcade): a rhythm of at most this many beats, within this many seconds.
MAX_BEATS, MAX_BEAT_SECONDS = 16, 20.0

POLL_SECONDS = 0.05
FADE_PER_SECOND = 900.0       # MCI volume units (0-1000) a second
MODE_CHECK_SECONDS = 1.0


def _step(floor):
    return f"step_{floor}" if floor in FLOORS else "step_metal"


def cues_for(message, acoustics=None):
    """The sounds for a server event: [(cue, pan, acoustics, fallback)], all
    played together; `fallback` is the cue to play when `cue` has no file."""
    kind = message.get("k")
    room = message.get("acoustics") or acoustics
    d = message.get("dir")
    pan = DIR_PAN.get(d, 0.0)
    sound = message.get("sound")
    kind_cue = KIND_CUES.get(kind)
    if kind == "moved":
        if sound:
            return [(sound, 0.0, None, "door")]
        via = message.get("via")
        if via in VIA_CUES:
            return [(VIA_CUES[via][1 if d == "d" else 0], pan, room, "door")]
        if not d:
            return [("door", 0.0, room, None)]
        cues = [(_step(message.get("floor")), pan, room, "door")]
        if via == "door":
            cues.insert(0, ("door", pan, room, None))
        return cues
    if kind in ("arrive", "leave") and d:
        return [(kind, pan, room, None)]
    if message.get("reels"):
        return [("reel_spin", 0.0, None, None)]
    if kind == "emote":
        eid = message.get("emote")
        cue = f"emote_{eid}" if isinstance(eid, str) and eid.isalpha() else "emote"
        return [(sound or cue, 0.0, room, "emote")]
    if sound:
        return [(sound, pan, None, kind_cue)]           # placed on its side: a robot's beeps, a meteor
    return [(kind_cue, 0.0, None, None)] if kind_cue else []


def _beats(message):
    """Star Beat's rhythm: the seconds (after the event) at which each beat sounds."""
    beats = message.get("beats")
    if not isinstance(beats, list) or len(beats) > MAX_BEATS:
        return []
    times = []
    for at in beats:
        if isinstance(at, (int, float)) and not isinstance(at, bool) and 0 <= at <= MAX_BEAT_SECONDS:
            times.append(float(at))
    return times


def timed_cues(message):
    """Cues that come a moment after the event's own: ([(seconds, cue, pan)], and how
    many seconds the words should wait for them)."""
    cues = [(at, "arcade_beat", 0.0) for at in _beats(message)]
    if isinstance(message.get("reels"), list):
        cues.extend((at, "reel_stop", pan) for at, pan in REEL_STOPS)
    outcome = OUTCOME_CUES.get(message.get("outcome"))
    if outcome:
        at = OUTCOME_AT["reels"] if cues else OUTCOME_AT.get(message.get("sound"), 0.3)
        cues.append((at, outcome, 0.0))
    return cues, (max(at for at, _cue, _pan in cues) if cues else 0.0)


def sound_for(message):
    """The first cue for a server message (a name, no .wav), or None."""
    cues = cues_for(message)
    return cues[0][0] if cues else None


def tone_names(codes):
    """The reactor's tones: [1, 4, 2] -> ["tone1", "tone4", "tone2"]."""
    names = []
    for code in codes or []:
        try:
            value = int(code)
        except (TypeError, ValueError):
            continue
        if 1 <= value <= 4:
            names.append(f"tone{value}")
    return names


_winmm = None


def _mci_windows(command):
    """Send an MCI command string (Windows); its reply, or OSError."""
    global _winmm
    if _winmm is None:
        dll = ctypes.WinDLL("winmm")      # our own instance
        dll.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
                                       ctypes.c_void_p]
        dll.mciSendStringW.restype = ctypes.c_uint
        _winmm = dll
    reply = ctypes.create_unicode_buffer(256)
    code = _winmm.mciSendStringW(command, reply, 255, None)
    if code:
        raise OSError(code, f"MCI error {code}")
    return reply.value


def _pump_windows():
    """Serve window messages MCI may send to this thread's hidden window."""
    try:
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except Exception:
        pass


class AmbiencePlayer:
    """One looping sound at a time. play(path, volume) switches to a loop
    (None: silence), set_volume(0-100), hush(seconds), shutdown()."""

    ALIAS = "hariku_orbit_ambience"

    def __init__(self, mci=None, pump=None, is_speaking=None, clock=time.monotonic):
        self._mci = mci or _mci_windows
        self._pump = pump or _pump_windows
        self._is_speaking = is_speaking or (lambda: False)
        self._clock = clock
        self._commands = queue.Queue()
        self._thread = None
        self._lock = threading.Lock()
        # State, only touched on the player's thread (or by the tests' step()).
        self.wanted = None            # the loop that should play
        self.playing = None           # the loop that is open
        self.volume = 30              # 0-100
        self.level = 0.0              # what the device is set to, 0-1000
        self.hush_until = 0.0
        self.broken = False
        self._applied = None
        self._last_step = None
        self._next_mode_check = 0.0

    # --- the owner's side ------------------------------------------------------------

    def _command(self, op, value, start=False):
        # The thread is checked and the command queued under one lock: a thread
        # about to end for lack of work either sees the command or is gone, and
        # with no thread the command is applied here (nothing else touches the
        # state then), so nothing piles up while no loop plays.
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._commands.put((op, value))
            elif start:
                self._commands.put((op, value))
                self._thread = threading.Thread(target=self._run, daemon=True,
                                                name="orbit-ambience")
                self._thread.start()
            elif op != "quit":
                self._thread = None
                self.apply(op, value)

    def play(self, path, volume=None):
        self._command("play", (path, volume), start=path is not None)

    def set_volume(self, volume):
        self._command("volume", volume)

    def hush(self, seconds):
        self._command("hush", float(seconds))

    def stop(self):
        self._command("play", (None, None))

    def shutdown(self, wait=1.0):
        thread = self._thread
        self._command("quit", None)
        if thread is not None and thread is not threading.current_thread():
            thread.join(wait)

    # --- the player's thread ---------------------------------------------------------

    def _run(self):
        while True:
            try:
                op, value = self._commands.get(timeout=POLL_SECONDS)
                if op == "quit":
                    self._close()
                    return
                self.apply(op, value)
                continue
            except queue.Empty:
                pass
            self._pump()
            self.step(self._clock())
            if self.playing is None and self.wanted is None and self._commands.empty():
                # Nothing to play: the thread ends, and comes back with the next loop.
                with self._lock:
                    if self._commands.empty():
                        self._thread = None
                        return

    def apply(self, op, value):
        if op == "play":
            path, volume = value
            self.wanted = path
            if volume is not None:
                self.volume = max(0, min(100, int(volume)))
        elif op == "volume":
            self.volume = max(0, min(100, int(value)))
        elif op == "hush":
            self.hush_until = max(self.hush_until, self._clock() + value)

    def _send(self, command):
        try:
            return self._mci(command)
        except OSError as e:
            if not self.broken:
                logger.info("[Orbit] The ambience can't play here: %s", e)
            self.broken = True
            return ""

    def _close(self):
        if self.playing is not None:
            self._send(f"stop {self.ALIAS}")
            self._send(f"close {self.ALIAS}")
        self.playing = None
        self._applied = None
        self.level = 0.0

    def _open(self, path):
        self.broken = False
        self._send(f'open "{path}" type mpegvideo alias {self.ALIAS}')
        if self.broken:
            self.playing = None
            return
        self.playing = path
        self.level = 0.0
        self._applied = None
        self._set_level(0)
        self._send(f"play {self.ALIAS} repeat")

    def _set_level(self, level):
        level = int(round(max(0.0, min(1000.0, level))))
        if level != self._applied:
            self._applied = level
            self._send(f"setaudio {self.ALIAS} volume to {level}")

    def target(self, now):
        """The volume the loop should be at now, 0-1000."""
        if self.wanted is None or self.wanted != self.playing:
            return 0.0
        if now < self.hush_until or self._is_speaking():
            return 0.0
        return self.volume * 10.0

    def step(self, now):
        """One moment of the player: fade towards the target, switch loops
        once faded out, keep the loop going."""
        elapsed = POLL_SECONDS if self._last_step is None else max(0.0, now - self._last_step)
        self._last_step = now
        if self.playing != self.wanted:
            if self.playing is None or self.level <= 0.0:
                self._close()
                if self.wanted is not None:
                    self._open(self.wanted)
                return
        if self.playing is None:
            return
        goal = self.target(now)
        change = FADE_PER_SECOND * max(elapsed, POLL_SECONDS)
        if self.level < goal:
            self.level = min(goal, self.level + change)
        elif self.level > goal:
            self.level = max(goal, self.level - change)
        self._set_level(self.level)
        if now >= self._next_mode_check:
            self._next_mode_check = now + MODE_CHECK_SECONDS
            mode = (self._send(f"status {self.ALIAS} mode") or "").strip().lower()
            if mode == "stopped":         # a device that doesn't repeat by itself
                self._send(f"seek {self.ALIAS} to start")
                self._send(f"play {self.ALIAS} repeat")
