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
a voice list load on a worker thread (with its "Loading voices…" row), arrow
through it checking focus stays put, switch the source, press Test, press OK and check
what was saved; then reopen the page, close it while a list is loading, and use
the "Stop Hariku Voice" action.

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

    def __init__(self, provider_id, name, voices, delay=0.0, note=""):
        self.id, self.name, self.voices, self.delay, self.note = (provider_id, name, voices,
                                                                  delay, note)
        self.said = []
        self.hang = False
        self.pending = None
        self.list_threads = set()

    def list_voices(self):
        self.list_threads.add(threading.get_ident())
        time.sleep(self.delay)
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
    {"id": "TOKEN_ANDIKA", "name": "Microsoft Andika", "language": "id-ID"},
    {"id": "TOKEN_ZIRA", "name": "Microsoft Zira", "language": "en-US"},
    {"id": "TOKEN_DAVID", "name": "Microsoft David", "language": "en-US"},
], delay=0.2, note=_("voice_windows_privacy")).register()
fake = FakeProvider("fake", "Fake online voices", [
    {"id": "fr-FR-DeniseNeural", "name": "Denise", "language": "fr-FR"},
    {"id": "id-ID-GadisNeural", "name": "Gadis", "language": "id-ID"},
    {"id": "en-US-AriaNeural", "name": "Aria", "language": "en-US"},
    {"id": "id-ID-ArdiNeural", "name": "Ardi", "language": "id-ID"},
], delay=0.8, note="Fake voices send your text to nobody.").register()

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


def rows(lst):
    return [(lst.GetItemText(i, 0), lst.GetItemText(i, 1)) for i in range(lst.GetItemCount())]


def loaded(panel):
    lst = panel.lst_voices
    return lst.GetItemCount() > 1 and lst.GetItemText(0) != _("voice_loading")


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


def browse_list(lst, panel):
    """Select each row as arrow keys do; focus must stay on the list."""
    lst.SetFocus()
    pump(lambda: wx.Window.FindFocus() is lst, timeout=1.0)
    observable = wx.Window.FindFocus() is lst
    state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    for i in list(range(lst.GetItemCount())) + [0]:
        lst.SetItemState(i, state, state)
        pump(lambda: False, timeout=0.05)
        assert lst.GetFirstSelected() == i
        if observable:
            assert wx.Window.FindFocus() is lst, f"focus left the voice list at row {i}"
    return observable


from ui.preferences_dialog import PreferencesDialog
import core.voice_panel

prefs = PreferencesDialog(frame, select_tab=_("prefs_tab_voice"))
pages = [prefs.treebook.GetPageText(i) for i in range(prefs.treebook.GetPageCount())]
assert pages[pages.index("Quiet Hours") + 1] == "Hariku Voice", pages
assert pages[prefs.treebook.GetSelection()] == "Hariku Voice", pages
panel = core.voice_panel._panel_instance
assert panel is not None, "the Hariku Voice page was not created"
print("OK voice_page")

state = {"focus": True}


def interact():
    """Everything a user does on the page, run inside the modal Preferences."""
    assert panel.IsShown(), "the Hariku Voice page is not showing"
    # Off by default; every control is named by the label before it.
    assert [chk.GetValue() for chk in panel.chk_kinds.values()] == [False, False, False]
    assert panel.chk_kinds["reminder"].GetName() == \
        "Read reminders with Hariku Voice when they are due"
    assert panel.chk_stop_on_key.GetValue() is True
    assert panel.choice_source.GetName() == "Source"
    assert panel.lst_voices.GetName() == "Voice"
    assert panel.spin_rate.GetName() == "Rate (-10 to 10)"
    assert panel.spin_volume.GetName() == "Volume (0 to 100)"
    assert panel.choice_fallback.GetName() == "If this voice isn't available, use"
    assert panel.txt_privacy.GetName() == "About this source"
    # Source, voice list, rate, volume, fallback and the privacy note.
    assert check_labels(panel) == 6
    assert panel.choice_source.GetStringSelection() == "Windows voices"
    assert panel.spin_rate.GetValue() == 0 and panel.spin_volume.GetValue() == 100
    assert panel.choice_fallback.GetStringSelection() == _("voice_fallback_reader")

    # The Windows voices load on a worker thread; English (Hariku's language) first.
    assert pump(lambda: loaded(panel)), f"the Windows voices never loaded: {rows(panel.lst_voices)}"
    assert threading.main_thread().ident not in windows.list_threads
    names = [name for name, language in rows(panel.lst_voices)]
    assert names[:2] == ["Microsoft David", "Microsoft Zira"], names
    assert names[2] == "Microsoft Andika", names
    assert all(language for name, language in rows(panel.lst_voices))
    assert panel.txt_privacy.GetValue() == _("voice_windows_privacy")
    assert panel.txt_privacy.IsEditable() is False
    assert panel.txt_privacy.IsMultiLine()
    # The fallback lists the Windows voices after the screen reader.
    fallbacks = panel.choice_fallback.GetStrings()
    assert fallbacks[0] == _("voice_fallback_reader") and len(fallbacks) == 4, fallbacks
    state["focus"] = browse_list(panel.lst_voices, panel)
    print(f"OK windows_voices ({focus_note(state['focus'])})")

    # Another source: a "Loading voices…" row at once, focus stays on the choice.
    panel.choice_source.SetFocus()
    pump(lambda: wx.Window.FindFocus() is panel.choice_source, timeout=1.0)
    source_focus = wx.Window.FindFocus() is panel.choice_source
    panel.choice_source.SetSelection(panel.choice_source.FindString("Fake online voices"))
    fire(panel.choice_source, wx.EVT_CHOICE, panel.choice_source.GetSelection())
    assert rows(panel.lst_voices) == [(_("voice_loading"), "")], rows(panel.lst_voices)
    assert panel.txt_privacy.GetValue() == "Fake voices send your text to nobody."
    if source_focus:
        assert wx.Window.FindFocus() is panel.choice_source, "switching the source moved focus"
    assert pump(lambda: loaded(panel)), "the second source's voices never loaded"
    if source_focus:
        assert wx.Window.FindFocus() is panel.choice_source, "the loaded list took focus"
    languages = [language for name, language in rows(panel.lst_voices)]
    assert [name for name, language in rows(panel.lst_voices)][0] == "Aria", rows(panel.lst_voices)
    assert len(languages) == 4
    state["focus"] = browse_list(panel.lst_voices, panel) and state["focus"] and source_focus
    print(f"OK switch_source ({focus_note(state['focus'])})")

    # Choose Gadis, a rate and a volume, and press Test: the fake speaks the
    # test sentence with the unsaved choices, and braille gets it too.
    lst = panel.lst_voices
    gadis = [name for name, language in rows(lst)].index("Gadis")
    selected = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    lst.SetItemState(gadis, selected, selected)
    pump(lambda: False, timeout=0.1)
    assert panel.selected_voice() == "id-ID-GadisNeural"
    assert prefs.is_dirty, "choosing a voice did not mark Preferences as changed"
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
assert saved == {"kinds": {"greeting": False, "briefing": True, "reminder": True},
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
assert [chk.GetValue() for chk in panel.chk_kinds.values()] == [False, True, True]
assert panel.spin_rate.GetValue() == 3 and panel.spin_volume.GetValue() == 80
assert panel.chk_stop_on_key.GetValue() is False
assert pump(lambda: loaded(panel))
assert panel.selected_voice() == "id-ID-GadisNeural"
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
