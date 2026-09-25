# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load World Trip through the real loader with real wxPython and take trips
through the real Aruna (the command bar): "take me to Tokyo" from take-off to
the local radio, everything said landing in Last result (including the
greeting played in another voice); then the commands during the trip (next
station, radio louder, tell me about this city, teach me a phrase, what time
is it there, where am I), "skip" during a flight, closing Aruna while the trip
goes on, and "go home". Then its Preferences page inside the real Preferences
dialog: the labels and their order, the voice list, toggling without the
focus moving, and Apply. Finally unloading.

The network, the native voice, the sounds and the radio are fakes (nothing is
sent, played or recorded); speech is captured through on_before_speak and
cancelled. Run by tests/test_world_trip_ui.py in a separate process
(conftest.py mocks wx in the pytest process) with APPDATA pointing at a
temporary folder. Prints one "OK" line per stage. Never run it on a computer
someone is using: it opens windows.
"""
import faulthandler
import functools
import logging
import os
import sys
import threading
import time
import types

faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
EXT_DIR = os.path.join(ROOT, "extensions", "world_trip")


def _watchdog():
    print("TIMEOUT: the world trip check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(200, _watchdog)
_timer.daemon = True
_timer.start()

import urllib.request

network_attempts = []


def _blocked_urlopen(*args, **kwargs):
    network_attempts.append(args[0] if args else kwargs)
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked_urlopen

problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    WATCHED = ("hariku_ext.world_trip", "world_trip_", "core.commands", "core.voice",
               "core.speech", "core.hotkeys", "core.extension_manager", "ui.command_bar",
               "ui.preferences_dialog")

    def emit(self, record):
        if record.name.startswith(self.WATCHED):
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
import core.places
from core.events import bus

core.api.save_data("Core", {"onboarding_completed": True, "language": "en",
                            "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad"),
                            "aruna_keep_open": True, "aruna_sounds": False})
core.i18n.init("en")
core.places.set_places([{"name": "Home", "lat": 1.1301, "lon": 104.0529,
                         "label": "Batam, Riau Islands, Indonesia", "timezone": "Asia/Jakarta",
                         "source": "city", "city": "Batam", "region": "Riau Islands",
                         "country": "Indonesia"}])

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

from ui.main_window import MainWindow
frame = MainWindow(None, title="world trip check")
frame.heartbeat_timer.Stop()
frame.monitor_timer.Stop()
print("OK main_window")

import ui.command_bar as cb

focus_calls = []
cb.set_foreground = lambda hwnd: focus_calls.append(hwnd) or True
PREVIOUS = frame.GetHandle()
cb.foreground_window = lambda: PREVIOUS

# --------------------------------------------------------------------------- #
# Loading: actions without keys that only answer, commands with content, a page
# --------------------------------------------------------------------------- #
import core.extension_manager as em
import core.preferences
em.load_unpacked_extension(EXT_DIR)
assert "world_trip" in em.LOADED_EXTENSIONS, f"World Trip did not load: {em.LOAD_ERRORS}"
main = em.LOADED_EXTENSIONS["world_trip"]["module"]
trips = sys.modules["world_trip_trip"]
texts = sys.modules["world_trip_text"]
voices = sys.modules["world_trip_voices"]
for name, *_rest in main.ACTIONS:
    action_id = f"World Trip.{name}"
    action = core.hotkeys.actions[action_id]
    assert action.default_keycode is None, f"{action_id} has a default key"
    assert core.commands.is_answer_action(action_id), action_id
assert {i.id for i in core.commands.intents()} >= {"World Trip.go", "World Trip.about",
                                                     "World Trip.where"}
assert "World Trip" in core.preferences.get_all_panels()
print("OK load")


# --------------------------------------------------------------------------- #
# Fakes: the network, the native voice, the sounds, the radio
# --------------------------------------------------------------------------- #
TOKYO = {"name": "Tokyo", "country": "Japan", "country_code": "JP", "region": "Tokyo",
         "latitude": 35.6895, "longitude": 139.69171, "timezone": "Asia/Tokyo",
         "feature": "PPLC", "population": 9733276}
PARIS = {"name": "Paris", "country": "France", "country_code": "FR", "region": "Île-de-France",
         "latitude": 48.85341, "longitude": 2.3488, "timezone": "Europe/Paris",
         "feature": "PPLC", "population": 2138551}
STATIONS = [{"uuid": "u1", "name": "J-Wave", "url": "http://jwave.example/", "latitude": None,
             "longitude": None, "state": "Tokyo"},
            {"uuid": "u2", "name": "Gotanno FM", "url": "http://gotanno.example/",
             "latitude": 35.76, "longitude": 139.81, "state": "Tokyo"}]
EDGE = [{"id": "ja-JP-NanamiNeural", "name": "Nanami", "language": "ja-JP", "gender": "female"},
        {"id": "fr-FR-DeniseNeural", "name": "Denise", "language": "fr-FR", "gender": "female"}]


class FakeRadio:
    def __init__(self):
        self.plays = []
        self.stops = 0
        self.volume = None
        self.ducked = []
        self.on_event = None
        self.active = False

    def play(self, url, volume=None, on_event=None):
        main._start_ducking()
        self.plays.append((url, volume))
        self.on_event = on_event
        self.active = True

    def stop(self):
        self.stops += 1
        self.active = False

    def set_volume(self, volume):
        self.volume = volume

    def set_ducked(self, ducked):
        self.ducked.append(ducked)

    def is_active(self):
        return self.active

    def emit(self, kind):
        self.on_event(kind, self.plays[-1][0])


class FakeServices(main.Services):
    """The real services (speech through core.voice, Aruna's hold and show,
    settings, threads, timers), with the network, sounds, voice and radio faked."""

    def __init__(self):
        super().__init__()
        self.radio = FakeRadio()
        self.voices = voices.VoiceBook(lambda: ["edge"], lambda provider: True,
                                       lambda provider: list(EDGE))
        self.sounds = []
        self.natives = []
        self.durations = {"chime": 0.3, "engine": 0.5}
        self.urls = []

    def resolve(self, text, avoid=None):
        dest = {"tokyo": TOKYO, "paris": PARIS}.get(text.lower())
        if dest is None:
            raise sys.modules["world_trip_places"].ResolveError("not_found", text)
        return dict(dest, query=text)

    def localized_name(self, dest, code):
        return {("Tokyo", "ja"): "東京都", ("Paris", "fr"): "Paris"}.get((dest["name"], code),
                                                                       dest["name"])

    def weather(self, dest):
        return {"temperature": 18.4, "code": 53, "is_day": False, "timezone": dest["timezone"]}

    def stations(self, dest, names, language=None):
        return list(STATIONS) if dest["name"] == "Tokyo" else []

    def summary(self, dest, names, english_names):
        return {"text": f"{dest['name']} is the capital of {dest['country']}.", "lang": "en",
                "title": dest["name"]}

    def count_click(self, uuid):
        pass

    def speak_native(self, text, voice, on_done):
        self.natives.append((text, voice["id"]))
        threading.Timer(0.3, on_done, [None]).start()
        return True

    def play_sound(self, name):
        self.sounds.append(name)
        return self.durations[name]

    def stop_sound(self, name):
        self.sounds.append(f"stop {name}")

    def radio_supported(self):
        return True

    def key_watch(self):
        return types.SimpleNamespace(pressed=lambda: False)     # nobody presses a key here


services = FakeServices()
main._services = services
main._manager = trips.TripManager(services)
texts.READER_SECONDS_PER_CHAR = 0.002          # a quick "screen reader"
texts.READER_MIN_SECONDS = 0.1
print("OK fakes")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def pump(condition, timeout=5.0):
    """Process events until condition() is true or the timeout passes."""
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


def type_text(bar, text):
    bar.txt_input.SetValue(text)


def press_enter(bar):
    fire(bar.txt_input, wx.EVT_TEXT_ENTER)


def press_escape(bar):
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(wx.WXK_ESCAPE)
    key.SetEventObject(bar.txt_input)
    bar.GetEventHandler().ProcessEvent(key)


def open_bar():
    core.hotkeys.actions["Hariku Core.command_bar"].callback()
    assert pump(lambda: cb.current_bar() is not None), "Aruna did not open"
    bar = cb.current_bar()
    pump(lambda: wx.Window.FindFocus() is bar.txt_input, timeout=1.0)
    return bar, wx.Window.FindFocus() is bar.txt_input


def result(bar):
    return bar.txt_result.GetValue()


def said(prefix):
    return any(s.startswith(prefix) for s in spoken)


def ask(bar, text, in_result, timeout=10.0):
    """Type a command, press Enter, wait until Last result holds `in_result`."""
    type_text(bar, text)
    press_enter(bar)
    ok = pump(lambda: in_result in result(bar), timeout)
    assert ok, f"{text!r}: Last result has no {in_result!r}: {result(bar)!r} (said {spoken[-5:]})"


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


# --------------------------------------------------------------------------- #
# Batam to Tokyo, through Aruna: everything in Last result
# --------------------------------------------------------------------------- #
bar, focus_ok = open_bar()
spoken.clear()
type_text(bar, "take me to Tokyo")
press_enter(bar)
assert bar.txt_status.GetValue() == "Aruna is thinking...", bar.txt_status.GetValue()
assert pump(lambda: services.radio.plays, timeout=20.0), f"no radio: {spoken}"
lines = result(bar).splitlines()
assert lines[0] == ("Welcome aboard Hariku Air. Flight from Batam to Tokyo, about 5,300 "
                    "kilometres, roughly 7 hours. Please fasten your seat belt."), lines
assert lines[1].startswith("Welcome to Tokyo, Japan. Local time "), lines
assert lines[1].endswith("2 hours ahead of Batam. 18 degrees, drizzle."), lines
assert "Tōkyō e yōkoso! (" in lines[2] and "東京へようこそ！)" in lines[2], lines
assert "Tōkyō e yōkoso! That means: " in lines[3] and lines[3].endswith("Welcome to Tokyo!"), lines
assert services.natives and services.natives[0][1] == "ja-JP-NanamiNeural", services.natives
assert services.natives[0][0].endswith("東京へようこそ！"), services.natives
assert services.sounds[:3] == ["chime", "engine", "chime"], services.sounds
assert services.radio.plays == [("http://jwave.example/", 35)], services.radio.plays
assert bar.txt_status.GetValue().startswith("Aruna answered."), bar.txt_status.GetValue()
services.radio.emit("playing")
assert pump(lambda: "You're listening to J-Wave, from Tokyo." in result(bar), timeout=5.0), \
    result(bar)
assert pump(lambda: "Try saying: tell me about this city" in result(bar), timeout=5.0), result(bar)
assert cb.current_bar() is bar and focus_calls == []
if focus_ok:
    assert wx.Window.FindFocus() is bar.txt_input, "the trip moved focus"
# The radio goes down while something is said, and up again (the ducking timer).
main._manager.speaking_until = time.monotonic() + 3.0
assert pump(lambda: services.radio.ducked and services.radio.ducked[-1] is True, timeout=2.0)
main._manager.speaking_until = 0
assert pump(lambda: services.radio.ducked[-1] is False, timeout=2.0)
print(f"OK trip ({focus_note(focus_ok)})")

# --------------------------------------------------------------------------- #
# During the trip
# --------------------------------------------------------------------------- #
type_text(bar, "next station")
press_enter(bar)
assert pump(lambda: len(services.radio.plays) == 2, timeout=5.0), services.radio.plays
assert services.radio.plays[-1][0] == "http://gotanno.example/"
services.radio.emit("playing")
assert pump(lambda: "You're listening to Gotanno FM, from Tokyo." in result(bar), timeout=5.0), \
    result(bar)
ask(bar, "radio louder", "Radio volume 45 percent.")
assert services.radio.volume == 45 and main._settings["radio_volume"] == 45
ask(bar, "tell me about this city", "From Wikipedia: Tokyo is the capital of Japan.")
natives = len(services.natives)
ask(bar, "teach me a phrase", "That means:")
assert len(services.natives) == natives + 1
ask(bar, "what time is it there", "In Tokyo it's ")
ask(bar, "where am I", "You're in Tokyo, Japan, about 5,300 kilometres from Batam.")
ask(bar, "which station is this", "This is Gotanno FM.")
print("OK commands")

# --------------------------------------------------------------------------- #
# "skip" during a flight; Aruna closed while the trip goes on
# --------------------------------------------------------------------------- #
services.durations["engine"] = 60.0                # a long take-off, to skip
type_text(bar, "fly to Paris")
press_enter(bar)
assert pump(lambda: said("Welcome aboard Hariku Air. Flight from Batam to Paris"), timeout=10.0)
assert pump(lambda: "engine" in services.sounds[3:], timeout=10.0), services.sounds
assert services.radio.stops >= 1                   # Tokyo's radio went off
engine_stops = services.sounds.count("stop engine")
ask(bar, "skip", "Welcome to Paris, France.")
assert services.sounds.count("stop engine") > engine_stops, services.sounds
services.durations["engine"] = 0.5
press_escape(bar)
assert pump(lambda: cb.current_bar() is None), "Escape did not close Aruna"
# No French voice among the fakes but Denise is one: the greeting still comes.
assert pump(lambda: any("Bienvenue à Paris !" in s for s in spoken)
            or any("Bienvenue à Paris !" in n[0] for n in services.natives), timeout=10.0), spoken
assert pump(lambda: said("I couldn't find a radio station from Paris, France"), timeout=10.0), \
    spoken[-5:]
print("OK skip_and_closed")

# --------------------------------------------------------------------------- #
# Home
# --------------------------------------------------------------------------- #
bar, _focus = open_bar()
stops = services.radio.stops
ask(bar, "go home", "Right, heading home to Batam.")
assert services.radio.stops == stops + 1
assert pump(lambda: "Thank you for flying Hariku Air." in result(bar), timeout=10.0), result(bar)
# The trip ends once that last line has been said (it shows as it starts).
assert pump(lambda: main._manager.trip is None, timeout=10.0), main._manager.trip
ask(bar, "where am I", "You're home, in Batam.")
ask(bar, "take me to Atlantis", "I couldn't find a place called Atlantis.")
press_escape(bar)
assert pump(lambda: cb.current_bar() is None)
print("OK home")

# --------------------------------------------------------------------------- #
# The Preferences page
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="World Trip")
prefs.Show()
wx.Yield()
panel = main._panel
assert panel is not None and panel.IsShown(), "the page was not created"
ui = sys.modules["world_trip_ui"]
children = list(panel.GetChildren())
kinds = [type(c).__name__ for c in children]
assert kinds == ["CheckBox", "CheckBox", "CheckBox", "StaticText", "Slider", "CheckBox",
                 "StaticText", "TextCtrl", "StaticText", "StaticText", "StaticText"], kinds
for index, child in enumerate(children):
    if isinstance(child, (wx.Slider, wx.TextCtrl)):
        label = children[index - 1]
        assert isinstance(label, wx.StaticText), f"{type(child).__name__} has no label before it"
        assert child.GetName() == ui._plain(label.GetLabel()), (child.GetName(), label.GetLabel())
assert panel.sld_volume.GetName() == "Radio volume" and panel.sld_volume.GetValue() == 45
assert panel.txt_voices.IsMultiLine() and not panel.txt_voices.IsEditable()
assert pump(lambda: panel.txt_voices.GetValue() != "Looking for voices...", timeout=10.0)
voice_text = panel.txt_voices.GetValue()
assert "Japanese: Nanami (edge)" in voice_text and "Korean: no native voice yet" in voice_text, \
    voice_text
labels = [c.GetLabel() for c in children if isinstance(c, wx.StaticText)]
assert any("Radio Browser" in label and "Wikipedia" in label for label in labels), labels
assert any("stays on this computer" in label for label in labels), labels

# Toggling never moves the focus; the engine follows the departure, the volume the radio.
panel.chk_departure.SetFocus()
wx.Yield()
observable = wx.Window.FindFocus() is panel.chk_departure
panel.chk_departure.SetValue(False)
fire(panel.chk_departure, wx.EVT_CHECKBOX)
assert not panel.chk_engine.IsEnabled()
if observable:
    assert wx.Window.FindFocus() is panel.chk_departure, "focus moved"
panel.chk_radio.SetValue(False)
fire(panel.chk_radio, wx.EVT_CHECKBOX)
assert not panel.sld_volume.IsEnabled()
panel.chk_radio.SetValue(True)
fire(panel.chk_radio, wx.EVT_CHECKBOX)
assert panel.sld_volume.IsEnabled()
panel.sld_volume.SetValue(20)
panel.chk_native.SetValue(False)
prefs.OnApply(None)
saved = core.api.load_data("WorldTrip")
assert (saved["departure"], saved["engine"], saved["radio"], saved["radio_volume"],
        saved["native_voices"]) == (False, True, True, 20, False), saved
assert saved["trips"] >= 2
prefs.Destroy()
wx.Yield()
print(f"OK page ({focus_note(observable)})")

# --------------------------------------------------------------------------- #
# Unloading
# --------------------------------------------------------------------------- #
em.unload_all_extensions()
assert not any(i.id.startswith("World Trip.") for i in core.commands.intents())
assert core.commands.aliases_for("World Trip.next_station") == []
print("OK teardown")

assert not network_attempts, f"network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

# The tray icon goes before the frame, or wx can crash while tearing down.
frame.tb_icon.RemoveIcon()
frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
