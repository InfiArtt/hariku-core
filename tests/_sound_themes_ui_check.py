# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Load Sound Themes through the real loader with real wxPython, open its page in
the real Preferences dialog, browse both lists the way arrow keys do (focus must
stay put), and drive every button: new/duplicate/rename through the real name
dialog, replace a sound with a WAV written by the wave module, play (recorded,
not heard), apply, the hotkey, export/import on the worker thread, reset and
delete. Native file pickers and message boxes are replaced with recorders.

Run by tests/test_sound_themes_ui.py in a separate process, because conftest.py
mocks wx inside the pytest process. The caller points APPDATA at a temporary
folder so the user's real themes and settings are never touched. Prints one
"OK" line per stage.
"""
import logging
import os
import sys
import threading
import wave
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
# One spelling of the data folder, so the paths compared below match.
os.environ["APPDATA"] = os.path.abspath(os.environ["APPDATA"])


def _watchdog():
    print("TIMEOUT: the sound themes check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(180, _watchdog)
_timer.daemon = True
_timer.start()

# Exceptions in wx event handlers are printed, not raised; collect them, and
# every error logged along the way.
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
import core.constants
import core.sounds
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

# Record playback instead of making sound.
played = []
core.sounds.play_sound = lambda path: played.append(path) or True

from ui.main_window import MainWindow
frame = MainWindow(None, title="sound themes check")
print("OK main_window")

import core.extension_manager as em

# The extension needs core 2.6 (core.sounds.set_theme_dir); this source tree
# has that API before constants.py is bumped for the release.
if em._version_tuple(core.constants.CORE_VERSION) < (2, 6):
    core.constants.CORE_VERSION = "2.6.0"

SHIFT_S = (ord("S"), False, True, False, False)
assert SHIFT_S not in core.hotkeys.keybindings, "Shift+S is already bound by the core"

em.load_unpacked_extension(os.path.join(ROOT, "extensions", "sound_themes"))
assert "sound_themes" in em.LOADED_EXTENSIONS, "Sound Themes extension did not load"
main = em.LOADED_EXTENSIONS["sound_themes"]["module"]
sui = sys.modules["sound_themes_ui"]
store = sys.modules["sound_themes_store"]
_ = sys.modules["sound_themes_text"]._
assert core.hotkeys.keybindings[SHIFT_S][0] == "Sound Themes.next_theme"
assert core.sounds.get_theme_dir() is None
print("OK load")

# Native pickers and message boxes can't be driven from here: record them.
picks = []           # paths the "file dialog" returns, first in first out
opened_folders = []
confirms = []
sui._ask_open_path = lambda parent, title, wildcard: picks.pop(0) if picks else None
sui._ask_save_path = lambda parent, title, default_file, wildcard: picks.pop(0) if picks else None
sui._open_folder = lambda path: opened_folders.append(path)
sui._confirm = lambda parent, message, title: confirms.append(message) or True

# The real name dialog is used, but record what it was opened with: the check
# runs on a live desktop, where a stray key press could reach its text field.
asked = []
_real_ask_name = sui.ask_name


def _spy_ask_name(parent, title, value, validate):
    asked.append((title, value))
    return _real_ask_name(parent, title, value, validate)


sui.ask_name = _spy_ask_name

BUILTIN = core.sounds.get_builtin_sounds_dir()
THEMES = os.path.join(core.api.USER_DATA_DIR, "sound_themes")
WORK = os.path.join(core.api.USER_DATA_DIR, "check files")
os.makedirs(WORK, exist_ok=True)


def make_wav(name, seed):
    path = os.path.join(WORK, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(bytes((i * 13 + seed) % 256 for i in range(4000)))
    with open(path, "rb") as f:
        return path, f.read()


# --------------------------------------------------------------------------- #
# Helpers (the finance check's pump, modal driver and focus browser)
# --------------------------------------------------------------------------- #
def pump(ms=100):
    """Run the event loop for a while so timers (CallLater) and CallAfter fire."""
    loop = wx.GUIEventLoop()
    wx.CallLater(ms, loop.Exit)
    loop.Run()


def wait_for_speech(text, since=0, timeout_ms=5000):
    """Wait until `text` is spoken (in a message after index `since`)."""
    waited = 0
    while not any(text in s for s in spoken[since:]):
        if waited >= timeout_ms:
            raise AssertionError(f"never spoke {text!r}; spoke {spoken[-5:]}")
        pump(100)
        waited += 100
    return next(s for s in reversed(spoken[since:]) if text in s)


def modal_dialogs():
    return [w for w in wx.GetTopLevelWindows() if isinstance(w, wx.Dialog) and w.IsModal()]


def while_modal(action, work, label):
    """Call action(), which shows a modal dialog; work(dialog) runs inside it and
    must close it. A dialog left open fails the check instead of hanging it."""
    problems_here = []
    seen = []
    state = {"returned": False}

    def guard(dlg):
        if not state["returned"]:
            problems_here.append(AssertionError(f"{label}: dialog was left open"))
            dlg.EndModal(wx.ID_CANCEL)

    def step(tries=0):
        dialogs = modal_dialogs()
        if not dialogs:
            if tries < 50:
                wx.CallLater(100, step, tries + 1)
            else:
                problems_here.append(AssertionError(f"{label}: no dialog opened"))
            return
        dlg = dialogs[-1]
        seen.append(type(dlg).__name__)
        try:
            work(dlg)
        except Exception as e:
            problems_here.append(e)
        wx.CallLater(1500, guard, dlg)

    wx.CallLater(200, step)
    action()
    state["returned"] = True
    if problems_here:
        raise problems_here[0]
    assert seen, f"{label}: no dialog opened"
    return seen[0]


def focus_is(ctrl):
    return wx.Window.FindFocus() is ctrl


def _describe(window):
    if window is None:
        return "nothing (the app is not the foreground window)"
    return f"{type(window).__name__} {window.GetName()!r}"


def browse(ctrl, label, after_each=None):
    """Fire EVT_LISTBOX for every row, as arrow keys do, and check that focus
    stays on the list. Returns whether focus could be observed (only while this
    process owns the foreground window)."""
    ctrl.SetFocus()
    pump(30)
    observable = focus_is(ctrl)
    for i in range(ctrl.GetCount()):
        ctrl.SetSelection(i)
        evt = wx.CommandEvent(wx.EVT_LISTBOX.typeId, ctrl.GetId())
        evt.SetEventObject(ctrl)
        evt.SetInt(i)
        ctrl.GetEventHandler().ProcessEvent(evt)
        wx.Yield()
        if after_each:
            after_each(i)
        if observable:
            now = wx.Window.FindFocus()
            if now is None:
                observable = False
                continue
            assert now is ctrl, (f"focus left {label} at row {i} ({ctrl.GetString(i)!r}) "
                                 f"for {_describe(now)}")
    return observable


def press(ctrl, keycode, row_text):
    """Select the row starting with `row_text`, then send a key press to `ctrl`
    the way it arrives first (EVT_CHAR_HOOK). False if focus isn't observable."""
    ctrl.SetFocus()
    pump(30)
    if not focus_is(ctrl):
        return False
    select(ctrl, row_text)
    key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    key.SetKeyCode(keycode)
    key.SetEventObject(ctrl)
    ctrl.GetEventHandler().ProcessEvent(key)
    return True


def row(listbox, text):
    for i in range(listbox.GetCount()):
        if listbox.GetString(i).startswith(text):
            return i
    raise AssertionError(f"no row starting with {text!r}: "
                         f"{[listbox.GetString(i) for i in range(listbox.GetCount())]}")


def select(listbox, text):
    listbox.SetSelection(row(listbox, text))
    evt = wx.CommandEvent(wx.EVT_LISTBOX.typeId, listbox.GetId())
    evt.SetEventObject(listbox)
    listbox.GetEventHandler().ProcessEvent(evt)


focus_checked = []

# --------------------------------------------------------------------------- #
# The hotkey with only Default
# --------------------------------------------------------------------------- #
mark = len(spoken)
assert core.hotkeys.process_key_event(*SHIFT_S), "Shift+S did nothing"
assert spoken[mark:] == [_("err_no_other_themes")], spoken[mark:]
assert not played
print("OK hotkey_without_themes")

# --------------------------------------------------------------------------- #
# The page inside the real Preferences dialog
# --------------------------------------------------------------------------- #
from ui.preferences_dialog import PreferencesDialog

prefs = PreferencesDialog(frame, select_tab="Sound Themes")
prefs.Show()
pump(50)
panel = main._panel
assert panel is not None and panel.IsShown(), "Sound Themes page was not created or not shown"
themes, sounds = panel.list_themes, panel.list_sounds
assert themes.GetName() == "Themes" and sounds.GetName() == "Sounds in Default", \
    (themes.GetName(), sounds.GetName())
assert [themes.GetString(i) for i in range(themes.GetCount())] == \
    ["Default, Hariku's own sounds, in use"]
assert sounds.GetCount() == len(store.sound_names()) == 29   # + aruna_send.wav, aruna_reply.wav (core 2.8)
assert sounds.GetString(row(sounds, "confirm")) == "confirm, confirmation"
focus_checked.append(browse(themes, "themes list"))
focus_checked.append(browse(sounds, "sounds list"))
print("OK page")

# --------------------------------------------------------------------------- #
# New theme through the real name dialog
# --------------------------------------------------------------------------- #
while_modal(panel.on_new, lambda d: d.EndModal(wx.ID_CANCEL), "new, cancelled")
assert store.list_themes() == [None], "cancelling created a theme"


def name_ocean(d):
    assert isinstance(d, sui.ThemeNameDialog), type(d).__name__
    assert d.GetEscapeId() == wx.ID_CANCEL, "Escape must cancel"
    assert d.GetDefaultItem() is not None and d.GetDefaultItem().GetId() == wx.ID_OK, \
        "Enter must press OK"
    assert d.text.GetName() == "Theme name"
    d.text.SetValue("default")
    d._on_ok()
    assert d.IsModal() and d.result is None, "a reserved name must keep the dialog open"
    wait_for_speech(_("err_name_reserved", name="default"))
    d.text.SetValue("  Ocean ")
    d._on_ok()


while_modal(panel.on_new, name_ocean, "new theme")
# Checked before the event loop runs again, so no stray input can interfere.
assert asked[-1] == ("New Sound Theme", ""), asked[-1]
assert store.list_themes() == [None, "Ocean"]
assert themes.GetStringSelection() == "Ocean, no sounds of its own yet", themes.GetStringSelection()
assert sounds.GetName() == "Sounds in Ocean"
assert sounds.GetString(row(sounds, "confirm")) == "confirm, confirmation, default sound"
wait_for_speech("Theme Ocean created.")
print("OK new_theme")

# --------------------------------------------------------------------------- #
# Replace sounds with generated WAV files, and a bad file
# --------------------------------------------------------------------------- #
OCEAN = os.path.join(THEMES, "Ocean")
confirm_path, confirm_data = make_wav("my confirm.wav", 1)
start_path, start_data = make_wav("my start.wav", 2)
bad_path = os.path.join(WORK, "notes.wav")
with open(bad_path, "w") as f:
    f.write("this is text, not a sound")

# Each action selects its rows first and is checked before the event loop runs
# again: the check shares a live desktop, where a stray key could move a list.
select(themes, "Ocean")
select(sounds, "confirm")
picks.append(bad_path)
mark = len(spoken)
panel.on_replace()
assert not os.path.exists(os.path.join(OCEAN, "confirm.wav")), "a text file was copied"
wait_for_speech(_("err_not_wav"), since=mark)

select(themes, "Ocean")
select(sounds, "confirm")
picks.append(confirm_path)
mark = len(spoken)
panel.on_replace()
assert sounds.GetStringSelection() == "confirm, confirmation, this theme's sound", \
    sounds.GetStringSelection()
assert themes.GetStringSelection() == "Ocean, 1 sound of its own", themes.GetStringSelection()
with open(os.path.join(OCEAN, "confirm.wav"), "rb") as f:
    assert f.read() == confirm_data
wait_for_speech("Sound confirm replaced.", since=mark)

select(themes, "Ocean")
select(sounds, "start")
picks.append(start_path)
panel.on_replace()
assert sorted(store.custom_sounds("Ocean")) == ["confirm.wav", "start.wav"]
wait_for_speech("Sound start replaced.")
print("OK replace")

# --------------------------------------------------------------------------- #
# Play (recorded), including Enter on the sounds list
# --------------------------------------------------------------------------- #
select(sounds, "confirm")
panel.on_play()
assert played[-1] == os.path.join(OCEAN, "confirm.wav"), played[-1]
select(sounds, "move")
panel.on_play()
assert played[-1] == os.path.join(BUILTIN, "move.wav"), played[-1]
select(themes, "Default")
select(sounds, "confirm")
panel.on_play()
assert played[-1] == os.path.join(BUILTIN, "confirm.wav"), played[-1]
select(themes, "Ocean")
count = len(played)
if press(sounds, wx.WXK_RETURN, "confirm"):
    assert len(played) == count + 1 and played[-1] == os.path.join(OCEAN, "confirm.wav"), played[count:]
    assert prefs.IsShown(), "Enter on the sounds list closed Preferences"
assert core.sounds.get_theme_dir() is None, "previewing must not change the active theme"
print("OK play")

# --------------------------------------------------------------------------- #
# Use this theme
# --------------------------------------------------------------------------- #
select(themes, "Ocean")
mark = len(spoken)
panel.on_use()
assert spoken[mark:] == ["Theme Ocean applied."], spoken[mark:]
assert core.sounds.get_theme_dir() == OCEAN
assert core.api.load_data("SoundThemes") == {"active": "Ocean"}
assert themes.GetStringSelection() == "Ocean, in use, 2 sounds of its own", themes.GetStringSelection()
count = len(played)
core.sounds.play_internal_sound("confirm.wav")
core.sounds.play_internal_sound("move.wav")
assert played[count:] == [os.path.join(OCEAN, "confirm.wav"), os.path.join(BUILTIN, "move.wav")]


def sounds_follow_themes(i):
    theme = panel._themes[i]
    expected = "Sounds in " + (theme or "Default")
    assert sounds.GetName() == expected, (sounds.GetName(), expected)


focus_checked.append(browse(themes, "themes list", sounds_follow_themes))
focus_checked.append(browse(sounds, "sounds list"))
print("OK apply")

# --------------------------------------------------------------------------- #
# The hotkey cycles themes and previews start.wav from the new one
# --------------------------------------------------------------------------- #
mark, count = len(spoken), len(played)
assert core.hotkeys.process_key_event(*SHIFT_S)
assert spoken[mark:] == ["Hariku's own sounds applied."], spoken[mark:]
assert played[count:] == [os.path.join(BUILTIN, "start.wav")], played[count:]
assert core.sounds.get_theme_dir() is None
assert themes.GetStringSelection().startswith("Default, Hariku's own sounds, in use")
core.hotkeys.process_key_event(*SHIFT_S)
assert spoken[-1] == "Theme Ocean applied."
assert played[-1] == os.path.join(OCEAN, "start.wav"), played[-1]
assert core.sounds.get_theme_dir() == OCEAN
print("OK hotkey")

# --------------------------------------------------------------------------- #
# Duplicate and rename
# --------------------------------------------------------------------------- #
def accept_copy(d):
    d.text.SetValue("Ocean copy")
    d._on_ok()


select(themes, "Ocean")
while_modal(panel.on_duplicate, accept_copy, "duplicate")
assert asked[-1] == ("Duplicate Sound Theme", "Ocean copy"), asked[-1]
assert sorted(store.custom_sounds("Ocean copy")) == ["confirm.wav", "start.wav"]
assert themes.GetStringSelection() == "Ocean copy, 2 sounds of its own", themes.GetStringSelection()
wait_for_speech("Theme Ocean copy created as a copy of Ocean.")


def rename_to_sea(d):
    d.text.SetValue("ocean")
    d._on_ok()
    assert d.IsModal(), "renaming onto another theme must keep the dialog open"
    d.text.SetValue("Sea")
    d._on_ok()


select(themes, "Ocean copy")
while_modal(panel.on_rename, rename_to_sea, "rename")
assert asked[-1] == ("Rename Sound Theme", "Ocean copy"), asked[-1]
assert store.list_themes() == [None, "Ocean", "Sea"]
assert themes.GetStringSelection() == "Sea, 2 sounds of its own", themes.GetStringSelection()
wait_for_speech("Theme Ocean copy renamed to Sea.")
print("OK duplicate_rename")

# --------------------------------------------------------------------------- #
# Export and import on the worker thread
# --------------------------------------------------------------------------- #
select(themes, "Ocean")
export_path = os.path.join(WORK, "Ocean.zip")
picks.append(export_path)
panel.on_export()
wait_for_speech("Theme Ocean exported with 2 sounds.")
with zipfile.ZipFile(export_path) as z:
    assert sorted(z.namelist()) == ["confirm.wav", "start.wav"]

picks.append(export_path)
panel.on_import()
wait_for_speech("Theme Ocean 2 imported with 2 sounds.")
assert themes.GetString(row(themes, "Ocean 2")) == "Ocean 2, 2 sounds of its own"
with open(os.path.join(THEMES, "Ocean 2", "confirm.wav"), "rb") as f:
    assert f.read() == confirm_data

evil_path = os.path.join(WORK, "evil.zip")
with zipfile.ZipFile(evil_path, "w") as z:
    z.writestr("../move.wav", confirm_data)
picks.append(evil_path)
mark = len(spoken)
panel.on_import()
wait_for_speech(_("err_archive_unsafe"), since=mark)
assert store.list_themes() == [None, "Ocean", "Ocean 2", "Sea"]
print("OK export_import")

# --------------------------------------------------------------------------- #
# Reset, Default is read-only, open folder, delete
# --------------------------------------------------------------------------- #
select(themes, "Ocean 2")
select(sounds, "confirm")
mark = len(spoken)
panel.on_reset()
assert spoken[mark:] == ["Sound confirm reset to default."], spoken[mark:]
assert sounds.GetStringSelection() == "confirm, confirmation, default sound"
panel.on_reset()
assert spoken[-1] == "Sound confirm already plays the default."
select(themes, "Ocean 2")
mark = len(spoken)
if press(sounds, wx.WXK_DELETE, "start"):  # Delete on the sounds list resets too
    assert spoken[mark:] == ["Sound start reset to default."], spoken[mark:]

select(themes, "Default")
for action in (panel.on_replace, panel.on_reset, panel.on_rename, panel.on_delete):
    mark = len(spoken)
    action()
    assert spoken[mark:] == [_("err_default_readonly")], (action.__name__, spoken[mark:])
panel.on_open_folder()
assert spoken[-1] == _("default_no_folder") and not opened_folders

select(themes, "Sea")
panel.on_open_folder()
assert opened_folders == [os.path.join(THEMES, "Sea")]

select(themes, "Ocean,")
mark = len(spoken)
panel.on_delete()
assert spoken[mark:] == [_("err_delete_active", name="Ocean")] and not confirms

select(themes, "Sea")
panel.on_delete()
assert confirms and "Sea" in confirms[-1]
assert not os.path.exists(os.path.join(THEMES, "Sea"))
assert themes.GetStringSelection().startswith("Ocean 2"), "the next row should be selected"
wait_for_speech("Theme Sea deleted.")

# Delete and Enter on the themes list (when this process can hold the focus).
mark = len(spoken)
if press(themes, wx.WXK_DELETE, "Ocean 2"):
    assert store.list_themes() == [None, "Ocean"]
    wait_for_speech("Theme Ocean 2 deleted.", since=mark)
    if press(themes, wx.WXK_RETURN, "Default"):
        assert spoken[-1] == "Hariku's own sounds applied.", spoken[-1]
        assert core.sounds.get_theme_dir() is None
    assert prefs.IsShown(), "a key on the themes list closed Preferences"
focus_checked.append(browse(themes, "themes list"))
print("OK reset_delete")

prefs.OnApply(None)
prefs.Destroy()
pump(50)
print("OK preferences_closed")

# --------------------------------------------------------------------------- #
# Teardown hands the sounds back to the core
# --------------------------------------------------------------------------- #
store.apply_theme("Ocean")
assert core.sounds.get_theme_dir() == OCEAN
em.unload_all_extensions()
assert core.sounds.get_theme_dir() is None
assert core.api.load_data("SoundThemes") == {"active": "Ocean"}, "the choice must survive"
print("OK teardown")
print(f"OK focus ({'checked' if focus_checked and all(focus_checked) else 'not observable here'})")

leftover = [e for e in os.listdir(THEMES) if e.startswith(".")]
assert not leftover, f"temporary folders left behind: {leftover}"
assert not problems, "\n".join(problems)
print("OK no_errors")

frame.tb_icon.Destroy()
frame.Destroy()
wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
