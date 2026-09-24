# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load Voice Control through the real loader with real wxPython and use its
page in the real Preferences dialog: the labels, the program and models list,
downloading the tiny model (which brings the program) with fake installers,
the microphone test with a fake microphone (it measures the sentence and sets
the sensitivity on the page, unsaved) and with a made-up result (a voice too
quiet), the settings saved with OK (the sensitivity chosen with the arrow
keys, focus staying on it), then the command bar listening through the
extension with a fake microphone and a fake whisper-server ("gempa terbaru"
runs the earthquake action), then the wake phrase (1.1): downloading its
listener with a fake installer, the advice about the phrase said as it
changes, "Test the wake phrase..." hearing it twice, the wake settings saved
with OK (the status line then says it listens), and the phrase heard in the
background opening Aruna listening; and removing the model and the listener.

Nothing is downloaded, recorded, run or played: the installers, the
microphone (Recorder), whisper-server (the engine), sherpa-onnx's keyword
spotter and the sounds are fakes, the network is refused, and speech is
captured through on_before_speak.

Run by tests/test_voice_control_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
temporary folder. Prints one "OK" line per stage. Never run it on a computer
someone is using: it opens windows.
"""
import array
import faulthandler
import functools
import logging
import math
import os
import random
import sys
import threading
import time
import traceback

faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["APPDATA"] = os.path.abspath(os.environ["APPDATA"])


def _watchdog():
    print("TIMEOUT: the Voice Control check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(200, _watchdog)
_timer.daemon = True
_timer.start()

import socket
import urllib.request

network_attempts = []


def _blocked(*args, **kwargs):
    network_attempts.append(args[0] if args else kwargs)
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked
socket.create_connection = _blocked

problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    def emit(self, record):
        problems.append(f"logged by {record.name}: {record.getMessage()}")


logging.getLogger().addHandler(_ErrorLog(level=logging.ERROR))

import wx

app = wx.App(False)

import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()
import core.api
import core.commands
import core.sounds
from core.events import bus

core.api.save_data("Core", {"onboarding_completed": True, "language": "en",
                            "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad")})

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)
played = []
core.sounds.play_sound = lambda path: played.append(os.path.basename(path)) or True

from ui.main_window import MainWindow
frame = MainWindow(None, title="voice control check")
frame.heartbeat_timer.Stop()
frame.monitor_timer.Stop()
print("OK main_window")

import core.extension_manager as em
em.load_unpacked_extension(os.path.join(ROOT, "extensions", "voice_control"))
assert "voice_control" in em.LOADED_EXTENSIONS, "Voice Control did not load"
main = em.LOADED_EXTENSIONS["voice_control"]["module"]
vui = sys.modules["voice_control_ui"]
dl = sys.modules["voice_control_download"]
store = sys.modules["voice_control_store"]
audio = sys.modules["voice_control_audio"]
text = sys.modules["voice_control_text"]
_ = text._
listener = core.commands.get_listener()
assert listener is not None and listener.name == "Voice Control"
assert not listener.is_available(), "available before anything was downloaded"
assert store.root_dir() == os.path.join(os.environ["APPDATA"], "Hariku2", "voice_control")
print("OK load")

# --------------------------------------------------------------------------- #
# The fakes
# --------------------------------------------------------------------------- #
installs = []


def _worker():
    return threading.current_thread() is not threading.main_thread()


def fake_install_runtime(root, progress=None, cancelled=None):
    installs.append(("runtime", _worker()))
    for step in range(1, 5):
        time.sleep(0.03)
        progress(dl.RUNTIME_SIZE * step // 4)
    folder = os.path.join(store.runtime_dir(root), "Release")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "whisper-server.exe"), "wb") as f:
        f.write(b"MZ")
    store.write_runtime_marker(root, {"version": dl.RUNTIME_VERSION,
                                      "exe": os.path.join("Release", "whisper-server.exe")})


def fake_install_model(name, root, progress=None, cancelled=None):
    installs.append((name, _worker()))
    for step in range(1, 11):
        time.sleep(0.03)
        progress(dl.MODELS[name]["size"] * step // 10)
    os.makedirs(store.models_dir(root), exist_ok=True)
    with open(store.model_path(root, name), "wb") as f:
        f.write(b"ggml")
    store.write_model_marker(root, name, 4, dl.MODELS[name]["sha256"])


def fake_install_wake(root, progress=None, cancelled=None):
    installs.append(("wake", _worker()))
    for step in range(1, 5):
        time.sleep(0.03)
        progress(dl.WAKE_SIZE * step // 4)
    folder = store.wake_dir(root)
    files = {}
    for relative, (_size, sha256) in dl.WAKE_FILES.items():
        path = os.path.join(folder, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        # The pinned SHA-256s, so the marker counts as this version's; the
        # files themselves are never hashed (the spotter is a fake).
        files[relative] = {"size": 4, "sha256": sha256}
    store.write_json(os.path.join(folder, store.WAKE_MARKER), {"version": "1.13.8",
                                                               "files": files})


main._downloads._install_runtime = fake_install_runtime
main._downloads._install_model = fake_install_model
main._downloads._install_wake = fake_install_wake
dl.open_url = lambda *args, **kwargs: _blocked(*args)

questions = []
vui.ask = lambda parent, message, title: questions.append((title, message)) or True

RATE = 16000


def pcm(samples):
    return array.array("h", [max(-32768, min(32767, int(s))) for s in samples]).tobytes()


def speech_clip():
    rng = random.Random(1)
    quiet = pcm(rng.uniform(-80, 80) for _i in range(RATE * 400 // 1000))
    voice = pcm(6000 * math.sin(2 * math.pi * 220 * i / RATE) for i in range(RATE * 900 // 1000))
    tail = pcm(rng.uniform(-80, 80) for _i in range(RATE * 2000 // 1000))
    return quiet + voice + tail


class FakeRecorder:
    """The microphone: plays back nothing, just hands over a synthetic clip."""

    def record(self, on_chunk, stop=None, max_seconds=30.0, keep=True):
        data = speech_clip()
        out = bytearray()
        for i in range(0, len(data), 3200):
            if (stop is not None and stop.is_set()) or len(out) >= max_seconds * 2 * RATE:
                break
            piece = data[i:i + 3200]
            out += piece
            if on_chunk(piece):
                break
        return bytes(out)


class FakeEngine:
    def __init__(self):
        self.calls = []

    def warm_up(self, model):
        self.calls.append(("warm_up", model))

    def transcribe(self, model, wav, prompt=None, language=None):
        self.calls.append(("transcribe", model, language))
        return "Gampak terbaru.", 1.6


fake_engine = FakeEngine()
main._listener.make_recorder = FakeRecorder
main._listener.engine = fake_engine
main._listener.blocked = lambda: None
main._listener.sleep = lambda seconds: None


def pump(condition, timeout=5.0):
    loop = wx.GUIEventLoop()
    previous = wx.EventLoop.GetActive()
    wx.EventLoop.SetActive(loop)
    try:
        end = time.time() + timeout
        while True:
            while loop.Pending():
                loop.Dispatch()
            app.ProcessPendingEvents()
            if condition():
                return True
            if time.time() > end:
                return False
            time.sleep(0.02)
    finally:
        wx.EventLoop.SetActive(previous)


def fire(ctrl, event_type):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    ctrl.GetEventHandler().ProcessEvent(evt)
    wx.Yield()


def plain(label):
    return " ".join(label.replace("&&", "\0").replace("&", "").replace("\0", "&")
                    .strip().rstrip(":").split())


LABELED = (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl, wx.ListBox, wx.SpinCtrl,
           wx.Slider, wx.Gauge)


def check_labels(page):
    children = list(page.GetChildren())
    checked = 0
    for index, child in enumerate(children):
        assert not isinstance(child, (wx.FilePickerCtrl, wx.DirPickerCtrl, wx.SpinCtrlDouble))
        if not isinstance(child, LABELED):
            continue
        before = children[index - 1] if index > 0 else None
        assert isinstance(before, wx.StaticText), \
            f"{type(child).__name__} {child.GetName()!r} has no label right before it"
        assert child.GetName() == plain(before.GetLabel()), (child.GetName(), before.GetLabel())
        checked += 1
    return checked


def rows(lst):
    return [tuple(lst.GetItemText(i, c) for c in range(lst.GetColumnCount()))
            for i in range(lst.GetItemCount())]


def select(panel, item):
    index = panel._rows.index(item)
    state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    panel.list_items.SetItemState(index, state, state)
    pump(lambda: False, timeout=0.05)
    assert panel.selected_item() == item


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Voice Control")
prefs.Show()
pages = [prefs.treebook.GetPageText(i) for i in range(prefs.treebook.GetPageCount())]
assert pages[prefs.treebook.GetSelection()] == "Voice Control", pages
panel = main._panel
assert panel is not None and panel.IsShown(), "the Voice Control page was not created or shown"
assert check_labels(panel) == 11, \
    "list, progress, status, model, silence, sensitivity, test result, wake phrase, " \
    "its advice, its sensitivity and its test"
assert panel.list_items.GetName() == "Program and speech models"
assert panel.gauge.GetName() == "Download progress"
assert panel.txt_status.GetName() == "Status"
assert panel.choice_model.GetName() == "Recognition model"
assert panel.choice_silence.GetName() == "Stop listening after this much silence"
assert panel.choice_sensitivity.GetName() == "Microphone sensitivity"
assert [panel.choice_sensitivity.GetString(i)
        for i in range(panel.choice_sensitivity.GetCount())] == \
    ["Low", "Normal", "High", "Very high"]
assert panel.txt_test.GetName() == "Microphone test"
assert [panel.list_items.GetColumn(c).GetText() for c in range(3)] == ["Name", "Size", "Status"]
assert rows(panel.list_items) == [
    ("Speech recognition program (whisper.cpp)", "8.6 MB", "Not installed"),
    ("Tiny speech model (fastest, for commands)", "77.7 MB", "Not installed"),
    ("Base speech model (more accurate, for reminders)", "148.0 MB", "Not installed"),
    ("Small speech model (most accurate, slow on older computers)", "487.6 MB",
     "Not installed"),
    ("Wake phrase listener (sherpa-onnx and an English keyword model)", "42.4 MB",
     "Not installed")], rows(panel.list_items)
assert panel.selected_item() == "tiny"
assert panel.choice_model.GetStringSelection() == "Automatic (recommended)"
assert panel.chk_listen.GetValue() is True
assert panel.choice_silence.GetStringSelection() == "1.0 s"
assert panel.choice_sensitivity.GetStringSelection() == "Normal"
assert panel.txt_status.GetValue() == _("status_not_ready")
# The wake phrase: off, "Hey Aruna", Normal; each control named by its label.
assert panel.chk_wake.GetLabel().replace("&", "") == "Listen for a wake phrase"
assert panel.chk_wake.GetValue() is False
assert panel.txt_phrase.GetName() == "Wake phrase" and panel.txt_phrase.GetValue() == "Hey Aruna"
assert panel.txt_advice.GetName() == "About this phrase"
assert panel.txt_advice.GetValue() == _("wake_advice_note")
assert panel.choice_wake_sensitivity.GetName() == "Wake phrase sensitivity"
assert [panel.choice_wake_sensitivity.GetString(i)
        for i in range(panel.choice_wake_sensitivity.GetCount())] == ["Low", "Normal", "High"]
assert panel.choice_wake_sensitivity.GetStringSelection() == "Normal"
assert panel.chk_wake_quiet.GetValue() is False
assert panel.btn_test_wake.GetLabel().replace("&", "") == "Test the wake phrase..."
assert panel.txt_wake_test.GetName() == "Wake phrase test"
assert main._wake.state == "off"
assert not prefs.is_dirty, "building the page marked Preferences as changed"
print("OK page")

# --------------------------------------------------------------------------- #
# Download the tiny model: the program comes with it
# --------------------------------------------------------------------------- #
lst = panel.list_items
lst.SetFocus()
pump(lambda: wx.Window.FindFocus() is lst, timeout=1.0)
observable = wx.Window.FindFocus() is lst
select(panel, "tiny")
spoken.clear()
fire(panel.btn_download, wx.EVT_BUTTON)
assert questions and "Hugging Face" in questions[-1][1] and "86.3 MB" in questions[-1][1], \
    questions
assert pump(lambda: main._downloads.current() is None and installs == [
    ("runtime", True), ("tiny", True)], timeout=10), installs
assert pump(lambda: rows(lst)[1][2] == "Installed"), rows(lst)
assert rows(lst)[0][2] == "Installed", rows(lst)
assert spoken[0].startswith("Downloading Tiny speech model"), spoken
assert "100 percent" in spoken and spoken[-1] == "Tiny speech model (fastest, for commands) downloaded.", \
    spoken
assert listener.is_available(), "not available after the download"
if observable:
    assert wx.Window.FindFocus() is lst, "downloading moved focus"
print(f"OK download ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# The microphone test: a fake microphone, nothing played back. It measures
# the sentence (the room about -57 dB, the voice about -18 dB) and sets High
# on the page; nothing is saved before OK or Apply.
# --------------------------------------------------------------------------- #
spoken.clear()
played.clear()
prefs.is_dirty = False
panel.btn_test.SetFocus()
pump(lambda: wx.Window.FindFocus() is panel.btn_test, timeout=1.0)
observable = wx.Window.FindFocus() is panel.btn_test
fire(panel.btn_test, wx.EVT_BUTTON)
assert pump(lambda: panel.txt_test.GetValue().startswith("Your voice:"), timeout=10), \
    panel.txt_test.GetValue()
assert panel.txt_test.GetValue().endswith("Sensitivity set to High."), panel.txt_test.GetValue()
assert spoken[0] == _("mic_test_speak") and spoken[-1] == panel.txt_test.GetValue(), spoken
assert played == ["listen.wav", "listen_end.wav"], played        # the tones only
assert panel.choice_sensitivity.GetStringSelection() == "High"
assert prefs.is_dirty, "the sensitivity the test chose did not count as a change"
assert store.load_settings()["sensitivity"] == "normal", "saved before OK or Apply"
if observable:
    assert wx.Window.FindFocus() is panel.btn_test, "the microphone test moved focus"

# A made-up result: a voice too quiet even for Very high.
real_test = main.test_microphone
main.test_microphone = lambda: {
    "level": -40.0, "speech": True, "seconds": 5.0, "room": 20.0, "voice": 60.0,
    "calibration": audio.Calibration("very_high", "too_quiet", 20.0, 60.0)}
try:
    spoken.clear()
    fire(panel.btn_test, wx.EVT_BUTTON)
    assert pump(lambda: panel.txt_test.GetValue().startswith("Your voice: -55 dB"), timeout=10), \
        panel.txt_test.GetValue()
finally:
    main.test_microphone = real_test
assert "still too quiet" in panel.txt_test.GetValue(), panel.txt_test.GetValue()
assert "Device properties" in panel.txt_test.GetValue()
assert spoken[-1] == panel.txt_test.GetValue(), spoken
assert panel.choice_sensitivity.GetStringSelection() == "Very high"
assert store.load_settings()["sensitivity"] == "normal"
print(f"OK microphone_test ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# Settings, saved with OK
# --------------------------------------------------------------------------- #
prefs.is_dirty = False
panel.choice_sensitivity.SetFocus()
pump(lambda: wx.Window.FindFocus() is panel.choice_sensitivity, timeout=1.0)
observable = wx.Window.FindFocus() is panel.choice_sensitivity
for name in ("high", "normal", "low"):              # arrowing up from Very high
    panel.choice_sensitivity.SetSelection(panel._sensitivities.index(name))
    fire(panel.choice_sensitivity, wx.EVT_CHOICE)
    pump(lambda: False, timeout=0.05)
    if observable:
        assert wx.Window.FindFocus() is panel.choice_sensitivity, "arrowing moved focus"
assert prefs.is_dirty, "choosing a sensitivity did not count as a change"
panel.choice_model.SetSelection(panel._model_keys.index("base"))
fire(panel.choice_model, wx.EVT_CHOICE)              # as a user choosing it
panel.choice_silence.SetSelection(panel._silences.index(1500))
fire(panel.choice_silence, wx.EVT_CHOICE)
panel.chk_listen.SetValue(False)
fire(panel.chk_listen, wx.EVT_CHECKBOX)
assert prefs.is_dirty, "changing the settings did not count as a change"
prefs.OnApply(None)                       # what OK does, without ending a modal loop
pump(lambda: False, timeout=0.2)
saved = store.load_settings()
assert (saved["model"], saved["silence_ms"], saved["listen_on_open"], saved["sensitivity"]) == \
    ("base", 1500, False, "low"), saved
assert main.get_settings()["model"] == "base"
assert main.get_settings()["sensitivity"] == "low"
try:
    prefs.Destroy()
except RuntimeError:
    pass
wx.Yield()
main.save_settings("auto", False, 1000, "normal")     # back to the defaults for the next stage
print(f"OK settings ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# The command bar listens through Voice Control
# --------------------------------------------------------------------------- #
import ui.command_bar as cb
cb.set_foreground = lambda hwnd: True
ran = []
core.hotkeys.register_action("Earthquakes", "speak_latest",
                             "Speak the latest earthquake from BMKG", None, False,
                             lambda: ran.append(cb.current_bar() is None))
core.hotkeys.actions["Hariku Core.command_bar"].callback()          # open
assert pump(lambda: cb.current_bar() is not None), "the command bar did not open"
bar = cb.current_bar()
assert bar.btn_listen.IsShown()
played.clear()
core.hotkeys.actions["Hariku Core.command_bar"].callback()          # again: listen
assert pump(lambda: ran, timeout=10), "what was heard did not run"
# The latest earthquake only answers, so Aruna stays open for it (core 2.8's
# "Keep Aruna open after an answer", on by default).
assert ran == [False] and cb.current_bar() is bar, ran
assert played == ["listen.wav", "listen_end.wav"], played    # no send sound for speech
assert ("transcribe", "tiny", "en") in fake_engine.calls, fake_engine.calls
bar.close(restore=False)
assert pump(lambda: cb.current_bar() is None), "the command bar did not close"
print("OK listening")

# --------------------------------------------------------------------------- #
# The wake phrase. sherpa-onnx's keyword spotter is a fake that "hears" the
# phrase in a chunk whose first sample is 0.5; its microphone is a fake that
# gives what is put in wake_script, then quiet.
# --------------------------------------------------------------------------- #
wake = sys.modules["voice_control_wake"]
wake.speech_seconds = lambda text_: 0.05          # Hariku "says" everything at once here
wake.AFTER_SPEECH_SECONDS = 0.0
wake.COOLDOWN_SECONDS = 0.05


def chunk_bytes(level, first=None):
    samples = [int(level * math.sqrt(2) * math.sin(2 * math.pi * 220 * i / RATE))
               for i in range(RATE // 10)]
    if first is not None:
        samples[0] = first
    return array.array("h", samples).tobytes()


QUIET_CHUNK = chunk_bytes(10)
TRIGGER_CHUNK = chunk_bytes(3000, first=16384)
wake_script = []


class FakeSpotter:
    made = []

    def __init__(self, phrase, sensitivity):
        self.phrase, self.sensitivity, self.closed = phrase, sensitivity, False
        FakeSpotter.made.append(self)

    def new_stream(self):
        pass

    def accept(self, floats):
        return ["HEY_ARUNA"] if len(floats) and abs(floats[0] - 0.5) < 1e-6 else []

    def close(self):
        self.closed = True


class FakeWakeMic:
    """What wake_script holds, then quiet until told to stop (the page's test:
    until the script ends)."""

    ends_with_script = False

    def record(self, on_chunk, stop=None, max_seconds=30.0, keep=True):
        assert keep is False, "the wake phrase kept audio"
        end = time.monotonic() + max_seconds
        while time.monotonic() < end:
            if stop is not None and stop.is_set():
                return b""
            if not wake_script and FakeWakeMic.ends_with_script:
                return b""
            if on_chunk(wake_script.pop(0) if wake_script else QUIET_CHUNK):
                return b""
            time.sleep(0.01)
        return b""


main.make_spotter = FakeSpotter                  # the page's test
main._wake._make_spotter = FakeSpotter           # the listener in the background
main._wake._make_recorder = FakeWakeMic
main._wake._blocked = lambda: None

prefs = PreferencesDialog(frame, select_tab="Voice Control")
prefs.Show()
wx.Yield()
panel = main._panel

# Download the wake phrase listener.
select(panel, "wake")
fire(panel.btn_download, wx.EVT_BUTTON)
assert "GitHub" in questions[-1][1] and "42.4 MB" in questions[-1][1], questions[-1]
assert "Apache-2.0" in questions[-1][1], questions[-1]
assert pump(lambda: main._downloads.current() is None and ("wake", True) in installs,
            timeout=10), installs
assert pump(lambda: rows(panel.list_items)[4][2] == "Installed"), rows(panel.list_items)
assert main.wake_available()
print("OK wake_download")

# The advice about the phrase, said when it changes; focus stays in the field.
panel.txt_phrase.SetFocus()
pump(lambda: wx.Window.FindFocus() is panel.txt_phrase, timeout=1.0)
observable = wx.Window.FindFocus() is panel.txt_phrase
prefs.is_dirty = False
spoken.clear()
panel.txt_phrase.SetValue("Aruna")                           # EVT_TEXT, as typing does
assert pump(lambda: panel.txt_advice.GetValue().startswith(_("wake_advice_one_word")),
            timeout=5), panel.txt_advice.GetValue()
assert spoken[-1] == panel.txt_advice.GetValue(), spoken
assert prefs.is_dirty, "typing a phrase did not count as a change"
panel.txt_phrase.SetValue("Hey Aruna")
assert pump(lambda: panel.txt_advice.GetValue() == _("wake_advice_note"), timeout=5)
assert pump(lambda: spoken[-1] == _("wake_advice_note"), timeout=2), spoken
if observable:
    assert wx.Window.FindFocus() is panel.txt_phrase, "the advice moved focus"
print(f"OK wake_advice ({focus_note(observable)})")

# Test the wake phrase: it hears it twice, says "Heard it" each time, and
# counts. The phrase on the page is used, before OK.
panel.btn_test_wake.SetFocus()
pump(lambda: wx.Window.FindFocus() is panel.btn_test_wake, timeout=1.0)
observable = wx.Window.FindFocus() is panel.btn_test_wake
main._listener.make_recorder = FakeWakeMic
FakeWakeMic.ends_with_script = True
wake_script[:] = [QUIET_CHUNK] * 5 + [TRIGGER_CHUNK] + [QUIET_CHUNK] * 30 + [TRIGGER_CHUNK] + \
    [QUIET_CHUNK] * 3
spoken.clear()
played.clear()
try:
    fire(panel.btn_test_wake, wx.EVT_BUTTON)
    assert pump(lambda: panel.txt_wake_test.GetValue().startswith("Heard the wake phrase"),
                timeout=15), panel.txt_wake_test.GetValue()
finally:
    main._listener.make_recorder = FakeRecorder
    FakeWakeMic.ends_with_script = False
assert panel.txt_wake_test.GetValue() == "Heard the wake phrase 2 times in 20 seconds.", \
    panel.txt_wake_test.GetValue()
assert spoken[0] == 'Say "Hey Aruna" a few times in the next 20 seconds, after the tone.', spoken
assert "Heard it." in spoken and "Heard it, 2." in spoken, spoken
assert spoken[-1] == panel.txt_wake_test.GetValue(), spoken
assert played == ["listen.wav", "listen_end.wav"], played
assert FakeSpotter.made[-1].phrase == "Hey Aruna" and FakeSpotter.made[-1].closed
assert main._wake._suspended == set(), "the test left the listener paused"
if observable:
    assert wx.Window.FindFocus() is panel.btn_test_wake, "the test moved focus"
print(f"OK wake_test ({focus_note(observable)})")

# The wake settings, saved with OK; the status line says it listens.
prefs.is_dirty = False
panel.chk_wake.SetValue(True)
fire(panel.chk_wake, wx.EVT_CHECKBOX)
panel.txt_phrase.SetValue("Hi Princess")
panel.choice_wake_sensitivity.SetFocus()
pump(lambda: wx.Window.FindFocus() is panel.choice_wake_sensitivity, timeout=1.0)
observable = wx.Window.FindFocus() is panel.choice_wake_sensitivity
panel.choice_wake_sensitivity.SetSelection(panel._wake_sensitivities.index("high"))
fire(panel.choice_wake_sensitivity, wx.EVT_CHOICE)
pump(lambda: False, timeout=0.05)
if observable:
    assert wx.Window.FindFocus() is panel.choice_wake_sensitivity, "choosing moved focus"
panel.chk_wake_quiet.SetValue(True)
fire(panel.chk_wake_quiet, wx.EVT_CHECKBOX)
assert prefs.is_dirty
wake_script[:] = []
prefs.OnApply(None)
pump(lambda: False, timeout=0.2)
saved = store.load_settings()
assert (saved["wake"], saved["wake_phrase"], saved["wake_sensitivity"],
        saved["wake_quiet_hours"]) == (True, "Hi Princess", "high", True), saved
assert main._wake.config == wake.Config(True, "Hi Princess", "high", True)
assert pump(lambda: main._wake.state == wake.LISTENING, timeout=5), main._wake.state
assert pump(lambda: panel.txt_status.GetValue().endswith('Listening for "Hi Princess".'),
            timeout=5), panel.txt_status.GetValue()
assert FakeSpotter.made[-1].phrase == "Hi Princess"
assert FakeSpotter.made[-1].sensitivity == "high"
try:
    prefs.Destroy()
except RuntimeError:
    pass
wx.Yield()
print(f"OK wake_settings ({focus_note(observable)})")

# Said in the background, the phrase opens Aruna listening; after the
# command, it listens for the phrase again.
ran.clear()
played.clear()
fake_engine.calls.clear()
wake_script[:] = [QUIET_CHUNK] * 3 + [TRIGGER_CHUNK]
assert pump(lambda: ran, timeout=15), "the wake phrase did not open Aruna listening"
bar = cb.current_bar()
assert bar is not None and ran == [False], ran
assert played[:2] == ["listen.wav", "listen_end.wav"], played
assert ("transcribe", "tiny", "en") in fake_engine.calls, fake_engine.calls
assert main._wake.detections == 1
bar.close(restore=False)
assert pump(lambda: cb.current_bar() is None), "the command bar did not close"
assert pump(lambda: main._wake.state == wake.LISTENING, timeout=10), main._wake.state
assert main._wake.detections == 1, "it heard the phrase again by itself"
print("OK wake_opens_aruna")

# --------------------------------------------------------------------------- #
# Remove the model and the wake phrase listener
# --------------------------------------------------------------------------- #
prefs = PreferencesDialog(frame, select_tab="Voice Control")
prefs.Show()
wx.Yield()
panel = main._panel
select(panel, "tiny")
fire(panel.btn_remove, wx.EVT_BUTTON)
assert questions[-1][0] == _("confirm_remove_title"), questions
assert pump(lambda: rows(panel.list_items)[1][2] == "Not installed"), rows(panel.list_items)
assert not listener.is_available()
select(panel, "wake")
fire(panel.btn_remove, wx.EVT_BUTTON)
assert pump(lambda: rows(panel.list_items)[4][2] == "Not installed"), rows(panel.list_items)
assert pump(lambda: main._wake.state == wake.MISSING, timeout=5), main._wake.state
assert pump(lambda: panel.txt_status.GetValue().endswith(_("wake_status_missing")),
            timeout=5), panel.txt_status.GetValue()
assert FakeSpotter.made[-1].closed
prefs.Destroy()
wx.Yield()
print("OK remove")

# --------------------------------------------------------------------------- #
# Unloading takes the recogniser and the wake phrase listener away
# --------------------------------------------------------------------------- #
em.unload_all_extensions()
assert core.commands.get_listener() is None, "the recogniser stayed registered"
assert main._wake._thread is None, "the wake phrase listener kept running"
print("OK teardown")

assert not network_attempts, f"network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
