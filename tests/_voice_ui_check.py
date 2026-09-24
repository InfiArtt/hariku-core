# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Open Preferences with real wxPython, go to the Hariku Voice page, check each
control's label comes right before it (that is what screen readers read), watch
the voices load on a worker thread (the Language, Gender and Voice choices say
"Loading voices…" meanwhile), arrow through Language, Gender and Voice checking
focus stays put and the choices after them refill, check that each language
remembers the voice picked in it, switch to a source whose list fails, press
Test, press OK and check what was saved; then reopen the page (the saved voice
is preselected), close it while a list is loading, and use the "Stop Hariku
Voice" action.

Nothing speaks or plays: the Windows voices and a second source are fakes that
only record what they were asked to say, MCI is refused, screen reader speech
is captured through on_before_speak, and braille output is recorded.

Run by tests/test_voice_ui.py in a separate process, because conftest.py mocks
wx inside the pytest process. The caller points APPDATA at a temporary folder
so the user's real settings are never touched. Prints one "OK" line per stage.
"""
import logging
import os
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# Nothing here needs the network; any attempt fails and is remembered.
import socket
import urllib.request

network_attempts = []


def _blocked(*args, **kwargs):
    network_attempts.append(args[0] if args else kwargs)
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked
socket.create_connection = _blocked

# Exceptions in wx event handlers are printed, not raised; collect them.
problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook


class _ErrorLog(logging.Handler):
    WATCHED = ("core.voice", "core.core_panels", "core.events", "core.preferences",
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
import core.speech
import core.voice
from core.events import bus

_ = core.i18n.get_translator("core")

spoken = []
brailled = []
voiced = []


def _capture_speech(payload):
    if payload.get("voice"):
        voiced.append(payload["text"])   # a (fake) Hariku voice says it; let it through
        return
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)
# Braille and the fallback speech don't go through on_before_speak; record them.
core.speech.braille = lambda text, interrupt=False: brailled.append(text)
core.speech.speak_announced = lambda text, interrupt=False, braille=True: spoken.append(text)


def _no_mci(command):
    problems.append(f"MCI was used: {command}")
    raise core.voice.MciError(0, "MCI is disabled in the UI check")


core.voice._mci_send = _no_mci


class FakeProvider:
    """Records what it is asked to say; never makes a sound."""

    def __init__(self, provider_id, name, voices, delay=0.0, note="", error=None):
        self.id, self.name, self.voices, self.delay, self.note = (provider_id, name, voices,
                                                                  delay, note)
        self.error = error          # listing the voices raises OSError(error)
        self.said = []
        self.hang = False
        self.pending = None
        self.list_threads = set()

    def list_voices(self):
        self.list_threads.add(threading.get_ident())
        time.sleep(self.delay)
        if self.error:
            raise OSError(self.error)
        return self.voices

    def speak(self, text, voice_id, rate, volume, on_done):
        self.said.append((text, voice_id, rate, volume))
        if self.hang:
            self.pending = on_done
        else:
            on_done(None)

    def stop(self):
        pending, self.pending = self.pending, None
        if pending is not None:
            pending(None)

    def register(self):
        core.voice.register_provider(self.id, self.name, self.list_voices, self.speak, self.stop,
                                     privacy_note=self.note)
        return self


# The built-in Windows voices are replaced, so SAPI never speaks here.
windows = FakeProvider("windows", "Windows voices", [
    {"id": "TOKEN_ANDIKA", "name": "Microsoft Andika", "language": "id-ID"},   # no gender
    {"id": "TOKEN_ZIRA", "name": "Microsoft Zira", "language": "en-US", "gender": "female"},
    {"id": "TOKEN_DAVID", "name": "Microsoft David", "language": "en-US", "gender": "male"},
], delay=0.2, note=_("voice_windows_privacy")).register()
fake = FakeProvider("fake", "Fake online voices", [
    {"id": "fr-FR-DeniseNeural", "name": "Denise", "language": "fr-FR", "gender": "female"},
    {"id": "id-ID-GadisNeural", "name": "Gadis", "language": "id-ID", "gender": "female"},
    {"id": "en-US-AriaNeural", "name": "Aria", "language": "en-US", "gender": "female"},
    {"id": "id-ID-ArdiNeural", "name": "Ardi", "language": "id-ID", "gender": "male"},
    {"id": "en-US-GuyNeural", "name": "Guy", "language": "en-US", "gender": "male"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia", "language": "en-GB", "gender": "female"},
    {"id": "de-DE-thorsten", "name": "Thorsten", "language": "de-DE"},        # no gender
], delay=0.8, note="Fake voices send your text to nobody.").register()
broken = FakeProvider("broken", "Broken voices", [], delay=0.3,
                      error="the voice list is broken").register()

ALL, FEMALE, MALE = _("voice_gender_all"), _("voice_gender_female"), _("voice_gender_male")
# Language -> (the Gender choice, the Voice choice with All voices).
WINDOWS_CHOICES = {
    "en-US": ([ALL, FEMALE, MALE], ["Microsoft David", "Microsoft Zira"]),
    "id-ID": ([ALL], ["Microsoft Andika"]),
}
FAKE_CHOICES = {
    "en-GB": ([ALL, FEMALE], ["Sonia"]),
    "en-US": ([ALL, FEMALE, MALE], ["Aria", "Guy"]),
    "fr-FR": ([ALL, FEMALE], ["Denise"]),
    "id-ID": ([ALL, FEMALE, MALE], ["Ardi", "Gadis"]),
    "de-DE": ([ALL], ["Thorsten"]),
}

core.api.save_data("Core", {"user_name": "Rafli", "user_nickname": "Bro",
                            "onboarding_completed": True, "language": "en",
                            "enable_scratchpad": False,
                            "scratchpad_dir": os.path.join(ROOT, "scratchpad")})


def _unexpected_prompt(*args, **kwargs):
    problems.append(f"unexpected Yes/No prompt: {args}")
    return False


core.api.prompt_yes_no = _unexpected_prompt

from ui.main_window import MainWindow
frame = MainWindow(None, title="hariku voice check")
print("OK main_window")

import core.core_panels
core.core_panels.register()


def pump(condition, timeout=5.0):
    """Process events until condition() is true or the timeout passes. Runs an
    event loop of its own: wx.Yield() alone never delivers timer events here."""
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


def fire(ctrl, event_type, index=None):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    if index is not None:
        evt.SetInt(index)
    ctrl.GetEventHandler().ProcessEvent(evt)
    wx.Yield()


def strings(choice):
    return list(choice.GetStrings())


def loaded(panel):
    """The source's voices are in the choices (not "Loading voices…" or an error)."""
    return panel.selected_voice() is not None


def expected_languages(tags):
    """The tags in the order the Language choice lists them: the user's
    languages first (Hariku's, then Windows'; by tag within one), then the
    rest by the name Windows gives them."""
    preferred = core.voice.user_languages()

    def primary(tag):
        return tag.split("-")[0].lower()

    mine = sorted((t for t in tags if primary(t) in preferred),
                  key=lambda t: (preferred.index(primary(t)), t.lower()))
    rest = sorted((t for t in tags if t not in mine),
                  key=lambda t: core.voice.language_name(t).casefold())
    return mine + rest


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


LABELED = (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl, wx.ListBox, wx.SpinCtrl, wx.Slider)


def plain(label):
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&").strip().rstrip(":").strip()


def check_labels(page):
    """Screen readers name a control after the static text created right
    before it (window order), not after SetName: every input control must
    directly follow a StaticText with its label. Returns how many were checked."""
    children = list(page.GetChildren())
    checked = 0
    for index, child in enumerate(children):
        if not isinstance(child, LABELED):
            continue
        before = children[index - 1] if index > 0 else None
        assert isinstance(before, wx.StaticText), \
            f"{type(child).__name__} {child.GetName()!r} has no label right before it"
        assert child.GetName() == plain(before.GetLabel()), (child.GetName(), before.GetLabel())
        checked += 1
    return checked


def pick(choice, index):
    """Select an item as an arrow key does: the selection moves, then EVT_CHOICE."""
    choice.SetSelection(index)
    fire(choice, wx.EVT_CHOICE, index)
    pump(lambda: False, timeout=0.05)


def browse(choice, indexes, check):
    """Arrow through these items of the choice; focus must stay on it, and
    check(index) looks at the choices after it once they refilled. Returns
    whether focus could be observed."""
    choice.SetFocus()
    pump(lambda: wx.Window.FindFocus() is choice, timeout=1.0)
    observable = wx.Window.FindFocus() is choice
    for i in indexes:
        pick(choice, i)
        assert choice.GetSelection() == i, (choice.GetName(), i, choice.GetSelection())
        if observable:
            assert wx.Window.FindFocus() is choice, f"focus left {choice.GetName()!r} at item {i}"
        check(i)
    return observable


def voice_choices(panel):
    return (panel.choice_language, panel.choice_gender, panel.choice_voice)


from ui.preferences_dialog import PreferencesDialog
import core.voice_panel

prefs = PreferencesDialog(frame, select_tab=_("prefs_tab_voice"))
pages = [prefs.treebook.GetPageText(i) for i in range(prefs.treebook.GetPageCount())]
assert pages.index("Quiet Hours") < pages.index("Reminders") < pages.index("Hariku Voice"), pages
assert pages[prefs.treebook.GetSelection()] == "Hariku Voice", pages
panel = core.voice_panel._panel_instance
assert panel is not None, "the Hariku Voice page was not created"
print("OK voice_page")

state = {"focus": True}


def interact():
    """Everything a user does on the page, run inside the modal Preferences."""
    assert panel.IsShown(), "the Hariku Voice page is not showing"
    # Off by default, except answers to commands (the user asked for those in
    # their Hariku Voice); every control is named by the label before it.
    assert [chk.GetValue() for chk in panel.chk_kinds.values()] == [False, False, False, True]
    assert panel.chk_kinds["command"].GetName() == \
        "Read answers to commands (the command bar) with Hariku Voice"
    assert panel.chk_kinds["reminder"].GetName() == \
        "Read reminders with Hariku Voice when they are due"
    assert panel.chk_stop_on_key.GetValue() is True
    assert panel.choice_source.GetName() == "Source"
    assert panel.choice_language.GetName() == "Language"
    assert panel.choice_gender.GetName() == "Gender"
    assert panel.choice_voice.GetName() == "Voice"
    assert panel.spin_rate.GetName() == "Rate (-10 to 10)"
    assert panel.spin_volume.GetName() == "Volume (0 to 100)"
    assert panel.choice_fallback.GetName() == "If this voice isn't available, use"
    assert panel.txt_privacy.GetName() == "About this source"
    # Source, Language, Gender, Voice, rate, volume, fallback and the privacy note.
    assert check_labels(panel) == 8
    assert panel.choice_source.GetStringSelection() == "Windows voices"
    assert panel.spin_rate.GetValue() == 0 and panel.spin_volume.GetValue() == 100
    assert panel.choice_fallback.GetStringSelection() == _("voice_fallback_reader")

    # The Windows voices load on a worker thread; English (Hariku's language) first.
    assert pump(lambda: loaded(panel)), \
        f"the Windows voices never loaded: {[strings(c) for c in voice_choices(panel)]}"
    assert threading.main_thread().ident not in windows.list_threads
    tags = expected_languages(list(WINDOWS_CHOICES))
    assert tags[0] == "en-US", tags
    assert strings(panel.choice_language) == [core.voice.language_name(t) for t in tags]
    # Nothing saved: the first of the user's languages, All voices, its first voice.
    assert panel.choice_language.GetSelection() == 0
    assert strings(panel.choice_gender) == [ALL, FEMALE, MALE]
    assert panel.choice_gender.GetStringSelection() == ALL
    assert strings(panel.choice_voice) == ["Microsoft David", "Microsoft Zira"]
    assert panel.choice_voice.GetStringSelection() == "Microsoft David"
    assert panel.selected_voice() == "TOKEN_DAVID"
    assert panel.txt_privacy.GetValue() == _("voice_windows_privacy")
    assert panel.txt_privacy.IsEditable() is False
    assert panel.txt_privacy.IsMultiLine()
    # The fallback lists the Windows voices after the screen reader.
    fallbacks = panel.choice_fallback.GetStrings()
    assert fallbacks[0] == _("voice_fallback_reader") and len(fallbacks) == 4, fallbacks

    def windows_language(i):
        # Andika has no gender, so Indonesian offers only "All voices".
        genders, names = WINDOWS_CHOICES[tags[i]]
        assert strings(panel.choice_gender) == genders, (tags[i], strings(panel.choice_gender))
        assert panel.choice_gender.GetStringSelection() == ALL
        assert strings(panel.choice_voice) == names, (tags[i], strings(panel.choice_voice))
        assert panel.choice_voice.GetStringSelection() == names[0]

    state["focus"] = browse(panel.choice_language, list(range(len(tags))) + [0],
                            windows_language)
    print(f"OK windows_voices ({focus_note(state['focus'])})")

    # Another source: "Loading voices…" in all three choices at once, and
    # focus stays on the source.
    panel.choice_source.SetFocus()
    pump(lambda: wx.Window.FindFocus() is panel.choice_source, timeout=1.0)
    source_focus = wx.Window.FindFocus() is panel.choice_source
    panel.choice_source.SetSelection(panel.choice_source.FindString("Fake online voices"))
    fire(panel.choice_source, wx.EVT_CHOICE, panel.choice_source.GetSelection())
    loading = [_("voice_loading")]
    assert [strings(c) for c in voice_choices(panel)] == [loading] * 3, \
        [strings(c) for c in voice_choices(panel)]
    assert panel.selected_voice() is None
    assert panel.txt_privacy.GetValue() == "Fake voices send your text to nobody."
    if source_focus:
        assert wx.Window.FindFocus() is panel.choice_source, "switching the source moved focus"
    assert pump(lambda: loaded(panel)), "the second source's voices never loaded"
    if source_focus:
        assert wx.Window.FindFocus() is panel.choice_source, "the loaded voices took focus"
    tags = expected_languages(list(FAKE_CHOICES))
    assert tags[:2] == ["en-GB", "en-US"], tags        # English, by tag
    assert strings(panel.choice_language) == [core.voice.language_name(t) for t in tags]
    # Nothing saved for this source: its first language, All voices, the first voice.
    assert panel.choice_language.GetSelection() == 0
    assert panel.choice_gender.GetStringSelection() == ALL
    assert strings(panel.choice_voice) == ["Sonia"]
    assert panel.selected_voice() == "en-GB-SoniaNeural"

    def fake_language(i):
        # Gender and Voice refill for each language; nothing was picked there yet.
        genders, names = FAKE_CHOICES[tags[i]]
        assert strings(panel.choice_gender) == genders, (tags[i], strings(panel.choice_gender))
        assert panel.choice_gender.GetStringSelection() == ALL
        assert strings(panel.choice_voice) == names, (tags[i], strings(panel.choice_voice))
        assert panel.choice_voice.GetStringSelection() == names[0]
        assert panel.choice_gender.IsEnabled() and panel.choice_voice.IsEnabled()

    focus = browse(panel.choice_language, list(range(len(tags))) + [0], fake_language)
    state["focus"] = state["focus"] and source_focus and focus
    print(f"OK switch_source ({focus_note(state['focus'])})")

    # Indonesian: arrow through Gender, then through Voice.
    indonesian = tags.index("id-ID")
    pick(panel.choice_language, indonesian)
    by_gender = {0: ["Ardi", "Gadis"], 1: ["Gadis"], 2: ["Ardi"]}

    def gender_step(i):
        assert panel.choice_language.GetSelection() == indonesian
        assert strings(panel.choice_gender) == [ALL, FEMALE, MALE]
        assert strings(panel.choice_voice) == by_gender[i], (i, strings(panel.choice_voice))

    focus = browse(panel.choice_gender, [0, 1, 2, 1], gender_step)
    assert panel.choice_gender.GetStringSelection() == FEMALE
    assert panel.selected_voice() == "id-ID-GadisNeural"
    assert prefs.is_dirty, "choosing a voice did not mark Preferences as changed"
    pick(panel.choice_gender, 0)
    assert panel.choice_voice.GetStringSelection() == "Gadis", "All voices lost the voice"
    ids = ["id-ID-ArdiNeural", "id-ID-GadisNeural"]

    def voice_step(i):
        assert panel.selected_voice() == ids[i]
        assert strings(panel.choice_voice) == ["Ardi", "Gadis"]
        assert panel.choice_gender.GetSelection() == 0
        assert panel.choice_language.GetSelection() == indonesian

    focus = browse(panel.choice_voice, [0, 1, 0, 1], voice_step) and focus
    state["focus"] = state["focus"] and focus
    print(f"OK gender_and_voice ({focus_note(state['focus'])})")

    # Each language remembers the voice picked in it on this page.
    pick(panel.choice_gender, 1)
    assert panel.selected_voice() == "id-ID-GadisNeural"
    english = tags.index("en-US")
    pick(panel.choice_language, english)
    assert panel.choice_gender.GetStringSelection() == ALL     # nothing picked there yet
    assert panel.choice_voice.GetStringSelection() == "Aria"
    assert panel.selected_voice() == "en-US-AriaNeural"
    pick(panel.choice_gender, 2)
    assert strings(panel.choice_voice) == ["Guy"] and panel.selected_voice() == "en-US-GuyNeural"
    pick(panel.choice_language, indonesian)
    assert panel.choice_gender.GetStringSelection() == FEMALE
    assert panel.choice_voice.GetStringSelection() == "Gadis"
    pick(panel.choice_language, english)
    assert panel.choice_gender.GetStringSelection() == MALE
    assert panel.selected_voice() == "en-US-GuyNeural"
    pick(panel.choice_language, tags.index("fr-FR"))
    assert panel.selected_voice() == "fr-FR-DeniseNeural"
    pick(panel.choice_language, indonesian)
    assert panel.choice_gender.GetStringSelection() == FEMALE
    assert panel.selected_voice() == "id-ID-GadisNeural"
    print("OK remember_language")

    # A source whose list fails: the error in Language, Gender and Voice
    # empty and disabled. Back to the fake voices, as they were left.
    broken_index = panel.choice_source.FindString("Broken voices")
    panel.choice_source.SetSelection(broken_index)
    fire(panel.choice_source, wx.EVT_CHOICE, broken_index)
    assert [strings(c) for c in voice_choices(panel)] == [loading] * 3
    failed = _("voice_load_failed", error="the voice list is broken")
    assert pump(lambda: strings(panel.choice_language) == [failed]), \
        strings(panel.choice_language)
    assert panel.choice_language.IsEnabled()
    for choice in (panel.choice_gender, panel.choice_voice):
        assert choice.GetCount() == 0 and not choice.IsEnabled(), choice.GetName()
    assert panel.selected_voice() is None
    fake_index = panel.choice_source.FindString("Fake online voices")
    panel.choice_source.SetSelection(fake_index)
    fire(panel.choice_source, wx.EVT_CHOICE, fake_index)
    assert panel.choice_gender.IsEnabled() and panel.choice_voice.IsEnabled()
    assert panel.choice_language.GetStringSelection() == core.voice.language_name("id-ID")
    assert panel.choice_gender.GetStringSelection() == FEMALE
    assert panel.choice_voice.GetStringSelection() == "Gadis"
    print("OK load_error")

    # A rate and a volume, and Test: the fake speaks the test sentence with
    # the unsaved choices (Gadis), and braille gets it too.
    panel.spin_rate.SetValue(3)
    panel.spin_volume.SetValue(80)
    focus_before = wx.Window.FindFocus()
    fire(panel.btn_test, wx.EVT_BUTTON)
    test_text = "Good morning, Bro. This is your Hariku voice."
    assert pump(lambda: fake.said), "Test did not speak"
    assert fake.said[-1] == (test_text, "id-ID-GadisNeural", 3, 80), fake.said
    assert pump(lambda: test_text in brailled), brailled
    assert test_text not in spoken, "the screen reader was also given the test sentence"
    assert wx.Window.FindFocus() is focus_before, "Test moved focus"
    assert core.voice.get_settings()["provider"] == "windows"   # nothing saved yet
    print("OK test_button")

    # The rest of the page, then OK.
    panel.chk_kinds["reminder"].SetValue(True)
    panel.chk_kinds["briefing"].SetValue(True)
    panel.choice_fallback.SetSelection(panel.choice_fallback.FindString(
        _("voice_row", name="Microsoft Zira", language=core.voice.language_name("en-US"))))
    assert panel.choice_fallback.GetSelection() > 0
    panel.chk_stop_on_key.SetValue(False)
    assert panel.ValidateChanges() is None
    fire(prefs.btn_ok, wx.EVT_BUTTON)   # OK applies every page and closes


def run_interaction():
    try:
        interact()
    except Exception:
        problems.append(f"the Hariku Voice page check failed:\n{traceback.format_exc()}")
        prefs.EndModal(wx.ID_CANCEL)


def rescue_prefs():
    if prefs.IsModal():
        problems.append("Preferences was left open")
        prefs.EndModal(wx.ID_CANCEL)


wx.CallLater(500, run_interaction)
prefs_guard = wx.CallLater(90000, rescue_prefs)
result = prefs.ShowModal()
prefs_guard.Stop()
prefs.Destroy()
wx.Yield()
assert not problems, "\n".join(problems)
assert result == wx.ID_OK, result

# --- What OK saved ------------------------------------------------------------
saved = core.voice.get_settings()
assert saved == {"kinds": {"greeting": False, "briefing": True, "reminder": True,
                           "command": True},
                 "provider": "fake", "voice": "id-ID-GadisNeural", "rate": 3, "volume": 80,
                 "fallback": "TOKEN_ZIRA", "stop_on_key": False}, saved
stored = core.api.load_data("Core")
assert stored["user_nickname"] == "Bro" and stored["onboarding_completed"] is True, stored
print("OK voice_saved")

# --- The saved settings at work: a reminder goes to the voice, not the reader --
spoken.clear()
brailled.clear()
fake.said.clear()
assert core.voice.announce("Reminder: Take medicine", "reminder") is True
assert pump(lambda: fake.said and not core.voice.is_speaking())
assert fake.said == [("Reminder: Take medicine", "id-ID-GadisNeural", 3, 80)], fake.said
assert brailled == ["Reminder: Take medicine"] and spoken == [], (brailled, spoken)
assert voiced[-1] == "Reminder: Take medicine"     # extensions still see it once
assert core.voice.announce("Good morning, Bro.", "greeting", interrupt=False) is False
assert spoken == ["Good morning, Bro."]            # the greeting stays with the reader
print("OK announce")

# --- "Stop Hariku Voice" (S) --------------------------------------------------
action = core.hotkeys.actions["Hariku Core.stop_voice"]
assert action.default_keycode == ord("S") and not action.default_ctrl
assert not action.default_shift and not action.default_alt and not action.default_global
fake.hang = True
core.voice.announce("Today is Thursday. A long briefing.", "briefing")
assert pump(lambda: fake.pending is not None)
assert core.voice.is_speaking()
action.callback()
assert pump(lambda: not core.voice.is_speaking()), "the stop action did not stop the voice"
fake.hang = False
print("OK stop_action")

# --- Reopening shows what was saved -------------------------------------------
prefs = PreferencesDialog(frame, select_tab=_("prefs_tab_voice"))
prefs.Show()
wx.Yield()
panel = core.voice_panel._panel_instance
assert panel.choice_source.GetStringSelection() == "Fake online voices"
assert [chk.GetValue() for chk in panel.chk_kinds.values()] == [False, True, True, True]
assert panel.spin_rate.GetValue() == 3 and panel.spin_volume.GetValue() == 80
assert panel.chk_stop_on_key.GetValue() is False
assert pump(lambda: loaded(panel))
assert panel.selected_voice() == "id-ID-GadisNeural"
# The saved voice is preselected: its language, its gender, then the voice.
indonesian_name = core.voice.language_name("id-ID")
if core.voice.language_name("en-US") == "English (United States)":   # Windows in English (CI)
    assert indonesian_name == "Indonesian (Indonesia)", indonesian_name
assert panel.choice_language.GetStringSelection() == indonesian_name
assert panel.choice_gender.GetStringSelection() == "Female"
assert strings(panel.choice_gender) == ["All voices", "Female", "Male"]
assert panel.choice_voice.GetStringSelection() == "Gadis"
assert strings(panel.choice_voice) == ["Gadis"]
assert pump(lambda: panel.choice_fallback.GetCount() == 4)
assert panel.choice_fallback.GetSelection() > 0
assert "Zira" in panel.choice_fallback.GetStringSelection()
prefs.Destroy()
wx.Yield()
print("OK voice_reopen")

# --- Closing while a list is still loading is harmless --------------------------
fake.delay = 1.0
core.voice.register_provider("slow", "Slow voices", fake.list_voices, fake.speak, fake.stop)
prefs = PreferencesDialog(frame, select_tab=_("prefs_tab_voice"))
prefs.Show()
wx.Yield()
panel = core.voice_panel._panel_instance
panel.choice_source.SetSelection(panel.choice_source.FindString("Slow voices"))
fire(panel.choice_source, wx.EVT_CHOICE, panel.choice_source.GetSelection())
prefs.Destroy()
pump(lambda: False, timeout=1.5)          # the list arrives after the page is gone
print("OK close_while_loading")

assert not network_attempts, f"real network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
