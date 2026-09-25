# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the real Extension Manager with real wxPython: its four tabs (Installed,
Updates, Available, Incompatible), the labels before their controls, the
store's tabs while the store hasn't answered and after, searching, enabling
and disabling, installing, updating one and all (one download fails), what
needs a newer Hariku, removing an extension that is too old, a failed store
answer, and opening straight on the Updates tab. Focus never moves on its own.

The installed extensions, the store's list, downloads, removing and the
settings are fakes; speech is captured through on_before_speak and urlopen is
blocked, so nothing leaves the machine and nothing is spoken.

Run by tests/test_extension_manager_ui.py in a separate process, because
conftest.py mocks wx inside the pytest process. The caller points APPDATA at a
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

faulthandler.enable()
print = functools.partial(print, flush=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the Extension Manager check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(150, _watchdog)
_timer.daemon = True
_timer.start()

import urllib.request


def _blocked_urlopen(*args, **kwargs):
    raise OSError("network is disabled in the UI check")


urllib.request.urlopen = _blocked_urlopen

problems = []
_default_excepthook = sys.excepthook


def _excepthook(exc_type, value, tb):
    problems.append(f"{exc_type.__name__}: {value}")
    _default_excepthook(exc_type, value, tb)


sys.excepthook = _excepthook
threading.excepthook = lambda args: problems.append(
    f"thread {args.thread.name}: {args.exc_type.__name__}: {args.exc_value}")


class _ErrorLog(logging.Handler):
    def emit(self, record):
        if record.name.startswith(("ui.extension_manager_dialog", "core.extension_catalog")):
            problems.append(f"logged by {record.name}: {record.getMessage()}")


logging.getLogger().addHandler(_ErrorLog(level=logging.ERROR))

import wx

app = wx.App(False)

import core.api
import core.i18n
core.api.save_data("Core", {"onboarding_completed": True, "language": "en"})
core.i18n.init()
import core.constants
import core.extension_manager as manager
import core.store
import core.updater
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

# --- Fakes --------------------------------------------------------------------------------------
core.constants.EXTENSION_API_BACK_COMPAT = "2.0"
core.constants.CORE_VERSION = "2.8.0"        # the fake store's "needs 2.9" and "needs 3.0" entries rely on it
SYSTEM = os.path.join(ROOT, "extensions")
USER = os.path.join(os.environ["APPDATA"], "Hariku2", "extensions")
manager.SYSTEM_EXTENSIONS_DIR = SYSTEM


def _info(ext_id, name, version, *, user=False, packed=False, minimum="2.0", enabled=True):
    folder = USER if user else SYSTEM
    return {"id": ext_id, "name": name, "version": version, "author": "Rafli",
            "is_official": True, "description": f"What {name} does.", "is_enabled": enabled,
            "is_unpacked": not packed, "path": os.path.join(folder, ext_id + (".hrk" if packed else "")),
            "minimum_core_version": minimum, "last_tested_core_version": "",
            "missing_fields": []}


installed = [
    _info("weather", "Weather", "1.1"),
    _info("space", "Space", "1.0"),
    _info("world_clock", "World Clock", "1.0"),
    _info("finance", "Finance", "1.0", enabled=False),
    _info("crashy", "Crashy", "1.0", user=True, packed=True),
    _info("oldie", "Oldie", "0.9", user=True, packed=True, minimum="1.0"),
]
manager.get_installed_extensions_info = lambda: [dict(i) for i in installed]
manager.LOAD_ERRORS = {"crashy": "RuntimeError: boom"}

REGISTRY = [
    {"id": "weather", "name": "Weather", "version": "1.2", "author": "Rafli",
     "description": "Weather from the store.", "minimum_core_version": "2.8",
     "download_url": "https://example.invalid/weather.hrk"},
    {"id": "world_clock", "name": "World Clock", "version": "1.1", "author": "Rafli",
     "description": "Clocks.", "download_url": "https://example.invalid/world_clock.hrk"},
    {"id": "space", "name": "Space", "version": "1.1", "author": "Rafli",
     "description": "Space.", "minimum_core_version": "2.9",
     "download_url": "https://example.invalid/space.hrk"},
    {"id": "observatory", "name": "Observatory", "version": "1.0", "author": "Rafli",
     "description": "NASA pictures and asteroids.", "minimum_core_version": "2.8",
     "download_url": "https://example.invalid/observatory.hrk"},
    {"id": "earthquake", "name": "Earthquakes & Tsunami", "version": "1.2", "author": "Rafli",
     "description": "BMKG and USGS.", "download_url": "https://example.invalid/earthquake.hrk"},
    {"id": "aurora", "name": "Aurora", "version": "1.0", "author": "Someone",
     "description": "Needs a future Hariku.", "minimum_core_version": "3.0",
     "download_url": "https://example.invalid/aurora.hrk"},
]
store_answer = threading.Event()
store_calls = []
store_result = {"entries": REGISTRY}


def _fetch_registry():
    store_calls.append(threading.current_thread().name)
    store_answer.wait(30)
    return [dict(e) for e in store_result["entries"]]


core.store.fetch_registry = _fetch_registry

downloads = []


def _download(ext_id, url):
    downloads.append(ext_id)
    time.sleep(0.05)
    if ext_id == "world_clock":
        return False
    for e in REGISTRY:
        if e["id"] == ext_id:
            installed[:] = [i for i in installed if i["id"] != ext_id]
            installed.append(_info(ext_id, e["name"], e["version"], user=True, packed=True))
    return True


core.store.download_extension = _download
toggled, removed, core_checks = [], [], []
manager.toggle_extension = lambda ext_id, enable=True: toggled.append((ext_id, enable))
manager.uninstall_extension = lambda ext_id: removed.append(ext_id) or True
core.updater.check_for_updates = lambda interactive=True: core_checks.append(interactive)


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


def press(button):
    evt = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
    evt.SetEventObject(button)
    button.GetEventHandler().ProcessEvent(evt)


def cells(page):
    out = []
    for index in range(page.list.GetItemCount()):
        out.append(tuple(page.list.GetItemText(index, col) for col in range(3)))
    return out


def select(page, name):
    for index in range(page.list.GetItemCount()):
        if page.list.GetItemText(index, 0) == name:
            page.list.Select(index)
            page.list.Focus(index)
            pump(lambda: page.selected_row() and page.selected_row()["name"] == name, 2)
            return
    raise AssertionError(f"{name} is not listed: {cells(page)}")


def show_tab(dlg, key):
    import core.extension_catalog as catalog
    dlg.notebook.SetSelection(catalog.TABS.index(key))
    pump(lambda: dlg.current_tab() is dlg.tabs[key], 2)
    return dlg.tabs[key]


import ui.extension_manager_dialog as emd
from ui.extension_manager_dialog import ExtensionManagerDialog

frame = wx.Frame(None, title="Extension Manager check")
frame.Show()
dlg = ExtensionManagerDialog(frame)
dlg.Show()
pump(lambda: dlg.IsShown(), 2)

# --- Tabs and labels ----------------------------------------------------------------------------
titles = [dlg.notebook.GetPageText(i) for i in range(dlg.notebook.GetPageCount())]
assert titles == ["Installed (5)", "Updates", "Available", "Incompatible (1)"], titles
for key, page in dlg.tabs.items():
    children = list(page.GetChildren())
    for label, ctrl in (("&Search:", page.search), ("Extensions:", page.list),
                        ("Details:", page.details)):
        index = children.index(ctrl)
        before = children[index - 1]
        assert isinstance(before, wx.StaticText) and before.GetLabel() == label, (key, label)
    assert list(page.buttons) == list(emd.BUTTONS[key]), key
assert dlg.GetEscapeId() == wx.ID_CLOSE
print("OK tabs")

# --- Installed, before the store answers --------------------------------------------------------
installed_tab = dlg.tabs["installed"]
assert cells(installed_tab) == [
    ("Crashy", "1.0", "Stopped with an error"),
    ("Finance", "1.0", "Disabled"),
    ("Space", "1.0", "Enabled"),
    ("Weather", "1.1", "Enabled"),
    ("World Clock", "1.0", "Enabled"),
], cells(installed_tab)
assert installed_tab.selected_row()["id"] == "crashy"
assert "It stopped with an error when Hariku started: RuntimeError: boom." in \
    installed_tab.details.GetValue()
updates_tab = dlg.tabs["updates"]
assert cells(updates_tab) == [] and updates_tab.details.GetValue() == \
    "Checking the Extension Store...", updates_tab.details.GetValue()
assert dlg.btn_refresh.IsEnabled()                # Refresh works while the store is asked
print("OK loading")

# --- The store answers --------------------------------------------------------------------------
installed_tab.list.SetFocus()
pump(lambda: installed_tab.list.HasFocus(), 2)
store_answer.set()
assert pump(lambda: dlg.registry is not None, 5), "the store never answered"
titles = [dlg.notebook.GetPageText(i) for i in range(dlg.notebook.GetPageCount())]
assert titles == ["Installed (5)", "Updates (3)", "Available (3)", "Incompatible (1)"], titles
assert store_calls == ["hariku-store-list"], store_calls
assert installed_tab.list.HasFocus()
assert installed_tab.selected_row()["id"] == "crashy"          # stayed where it was
assert cells(installed_tab)[3] == ("Weather", "1.1", "Enabled, update 1.2 available")
assert cells(installed_tab)[2] == ("Space", "1.0", "Enabled")   # its 1.1 needs Hariku 2.9
assert not [t for t in spoken if "Updates" in t]               # the Installed tab is shown
print("OK store")

# --- Enable and disable -------------------------------------------------------------------------
select(installed_tab, "Finance")
assert installed_tab.buttons["toggle"].GetLabel() == "&Enable"
assert not installed_tab.buttons["uninstall"].IsEnabled()     # bundled: disable, not remove
assert "It comes with Hariku: you can disable it, but not remove it." in \
    installed_tab.details.GetValue()
installed_tab.list.SetFocus()
spoken.clear()
press(installed_tab.buttons["toggle"])
pump(lambda: spoken, 2)
assert toggled == [("finance", True)], toggled
assert cells(installed_tab)[1] == ("Finance", "1.0", "Enabled")
assert installed_tab.buttons["toggle"].GetLabel() == "&Disable"
assert spoken == ["Finance enabled. Restart Hariku to finish."], spoken
assert dlg.requires_restart and installed_tab.list.HasFocus()
print("OK toggle")

# --- Search -------------------------------------------------------------------------------------
available = show_tab(dlg, "available")
assert cells(available) == [("Aurora", "1.0", "Needs Hariku 3.0"),
                            ("Earthquakes & Tsunami", "1.2", ""),
                            ("Observatory", "1.0", "")], cells(available)
available.search.SetFocus()
pump(lambda: available.search.HasFocus(), 2)
spoken.clear()
available.search.SetValue("nasa")
assert cells(available) == [("Observatory", "1.0", "")], cells(available)
assert pump(lambda: "1 found" in spoken, 3), spoken
available.search.SetValue("zzz")
assert cells(available) == []
assert available.details.GetValue() == 'No extensions match "zzz".'
available.search.SetValue("")
assert len(cells(available)) == 3 and available.search.HasFocus()
print("OK search")

# --- Needs a newer Hariku -----------------------------------------------------------------------
select(available, "Aurora")
assert not available.buttons["install"].IsEnabled()
assert available.buttons["check_core"].IsEnabled()
assert "It needs Hariku 3.0 and you have" in available.details.GetValue()
press(available.buttons["check_core"])
assert pump(lambda: core_checks == [True], 2), core_checks
select(available, "Observatory")
assert not available.buttons["check_core"].IsEnabled()
print("OK needs_core")

# --- Install ------------------------------------------------------------------------------------
available.list.SetFocus()
pump(lambda: available.list.HasFocus(), 2)
spoken.clear()
press(available.buttons["install"])
assert dlg.busy and not available.buttons["install"].IsEnabled()
assert pump(lambda: not dlg.busy, 5), "the download never finished"
assert downloads == ["observatory"], downloads
assert cells(available)[2] == ("Observatory", "1.0", "Installed, restart Hariku to use it")
assert len(cells(available)) == 3                         # nothing jumped
assert spoken == ["Downloading Observatory...",
                  "Observatory installed. Restart Hariku to use it."], spoken
assert available.list.HasFocus() and available.selected_row()["id"] == "observatory"
assert [row for row in installed_tab.rows if row["id"] == "observatory"]
print("OK install")

# --- Updates: one, then all ---------------------------------------------------------------------
updates_tab = show_tab(dlg, "updates")
assert cells(updates_tab) == [("Space", "1.0 to 1.1", "Needs Hariku 2.9"),
                              ("Weather", "1.1 to 1.2", "Ready to update"),
                              ("World Clock", "1.0 to 1.1", "Ready to update")], cells(updates_tab)
select(updates_tab, "Space")
assert not updates_tab.buttons["update"].IsEnabled()
assert updates_tab.buttons["check_core"].IsEnabled()
assert updates_tab.buttons["update_all"].IsEnabled()
spoken.clear()
downloads.clear()
press(updates_tab.buttons["update_all"])
assert pump(lambda: not dlg.busy, 5), "Update all never finished"
assert downloads == ["weather", "world_clock"], downloads
assert cells(updates_tab) == [("Space", "1.0 to 1.1", "Needs Hariku 2.9"),
                              ("Weather", "1.1 to 1.2", "Updated, restart Hariku to use it"),
                              ("World Clock", "1.0 to 1.1", "Download failed, try again")]
assert spoken == ["Downloading 2 updates...",
                  "Weather updated. Restart Hariku to use it. Couldn't download: World Clock."], \
    spoken
select(updates_tab, "World Clock")
assert updates_tab.buttons["update"].IsEnabled()           # a failed one can be tried again
print("OK update_all")

# --- Incompatible: too old ----------------------------------------------------------------------
incompatible = show_tab(dlg, "incompatible")
assert cells(incompatible) == [("Oldie", "0.9", "Too old: made for Hariku 1.0")]
assert "It was made for Hariku 1.0" in incompatible.details.GetValue()
assert not incompatible.buttons["update"].IsEnabled()
asked = []
dlg.confirm = lambda message, title: asked.append((message, title)) or True
incompatible.list.SetFocus()
spoken.clear()
press(incompatible.buttons["uninstall"])
assert removed == ["oldie"], removed
assert asked == [("Remove Oldie from this computer? Restart Hariku afterwards to finish.",
                  "Remove Extension")], asked
assert cells(incompatible) == [("Oldie", "0.9", "Removed, restart Hariku to finish")]
assert not incompatible.buttons["uninstall"].IsEnabled()
assert spoken == ["Oldie removed. Restart Hariku to finish."], spoken
assert incompatible.list.HasFocus()
print("OK incompatible")

# --- Refresh and a failed answer ----------------------------------------------------------------
available = show_tab(dlg, "available")
store_result["entries"] = []
emd._registry_cache.update(time=0.0, entries=None)
spoken.clear()
press(dlg.btn_refresh)
assert pump(lambda: dlg.registry == [], 5), "Refresh never answered"
assert available.details.GetValue() == ("Couldn't reach the Extension Store. Check your "
                                        "internet connection, then press Refresh.")
assert dlg.notebook.GetPageText(1) == "Updates" and dlg.notebook.GetPageText(2) == "Available"
assert spoken == ["Couldn't reach the Extension Store. Check your internet connection, "
                  "then press Refresh."], spoken
print("OK refresh")

# --- Opening on the Updates tab, with the store's answer remembered ----------------------------
dlg._close()
dlg.Destroy()
store_result["entries"] = REGISTRY
emd._registry_cache.update(time=time.time(), entries=[dict(e) for e in REGISTRY])
store_calls.clear()
dlg = ExtensionManagerDialog(frame, tab="updates")
dlg.Show()
pump(lambda: dlg.IsShown(), 2)
assert dlg.current_tab() is dlg.tabs["updates"]
assert store_calls == [], store_calls                     # the answer from a moment ago
assert dlg.notebook.GetPageText(1).startswith("Updates (")
print("OK open_on_updates")

pump(lambda: False, 0.3)
assert not problems, problems
print("OK no_errors")

dlg._close()
dlg.Destroy()
frame.Destroy()
pump(lambda: False, 0.3)
print("OK shutdown")
_timer.cancel()
os._exit(0)
