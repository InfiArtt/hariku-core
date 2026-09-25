# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Walk the welcome (core 2.10, ui/onboarding_dialog.py) with real wxPython, the
way a screen-reader user does, as Rafli from Batam on a first run in
Indonesian: switch the language and back, type the name (the nickname
follows), find Batam (typed but not searched, so Next searches first; the
weather arrives late and is added to the next page's opening line), a
birthday with a mistake first, "Try it" with Aruna, the suggested
extensions (the store answers while the page is open), start-up, the
summary, Finish with the downloads (one fails), then check what was saved.
Then run it again from Help: everything is prefilled and passing through
changes nothing; Cancel with a change asks and saves nothing; and a first
run cancelled only marks the welcome done.

On every page: each input control comes right after the label that names it,
the screen reader's name for the first field is the page's current question
(core.ui_overrides, applied as Hariku does), Next puts the focus on the
page's first field, and the texts say the user's name.

Nothing leaves the machine: Open-Meteo, the store and the downloads are
replaced, any real request fails and is remembered, sounds and the Windows
autostart are recorded instead of played or written, and speech is captured
through on_before_speak. Run by tests/test_onboarding_ui.py in a separate
process (conftest.py mocks wx in the pytest process), with APPDATA pointed at
a temporary folder. Prints one "OK" line per stage.
"""
import logging
import os
import re
import sys
import threading
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def _watchdog():
    print("TIMEOUT: the welcome check hung", flush=True)
    os._exit(3)


_timer = threading.Timer(170, _watchdog)
_timer.daemon = True
_timer.start()

# Any real request fails, and is remembered so the check can fail on it.
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
threading.excepthook = lambda args: problems.append(
    f"thread {args.thread.name}: {args.exc_type.__name__}: {args.exc_value}")


class _ErrorLog(logging.Handler):
    WATCHED = ("ui.onboarding_dialog", "core.onboarding", "core.places", "core.personal",
               "core.events")

    def emit(self, record):
        if record.name.startswith(self.WATCHED):
            problems.append(f"logged by {record.name}: {record.getMessage()}")


logging.getLogger().addHandler(_ErrorLog(level=logging.WARNING))

import wx

app = wx.App(False)

# As hariku.py does: a label names the control created right after it.
import core.ui_overrides
core.ui_overrides.apply_overrides()

import core.api
core.api.save_data("Core", {})           # a first start: nothing saved yet
import core.i18n
core.i18n.init()
import core.hotkeys
core.hotkeys.init_hotkeys()
from core.events import bus

spoken = []


def _capture_speech(payload):
    spoken.append(payload["text"])
    payload["cancel"] = True


bus.subscribe("on_before_speak", _capture_speech)

# --- Fakes: Windows, sounds, Open-Meteo, the store ----------------------------------------
import core.onboarding as onboarding
import core.place_search
import core.places
import core.sounds
import core.store
import core.extension_manager as manager

onboarding.windows_languages = lambda: ["id-ID"]
sounds = []
core.sounds.play_internal_sound = lambda name: sounds.append(name)
autostart_calls = []
core.api.set_autostart = lambda enable=True: autostart_calls.append(enable)

CITIES = {"results": [
    {"name": "Batam", "admin1": "Riau Islands", "country": "Indonesia",
     "latitude": 1.14937, "longitude": 104.02491, "timezone": "Asia/Jakarta"},
    {"name": "Batu Ampar", "admin1": "Riau Islands", "country": "Indonesia",
     "latitude": 1.16, "longitude": 104.0, "timezone": "Asia/Jakarta"}]}
WEATHER = {"current": {"temperature_2m": 31.2, "weather_code": 1}}
weather_gate = threading.Event()
city_queries, weather_requests = [], []


def _fake_fetch_json(url, timeout=None, user_agent=None):
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    if url.startswith(core.place_search.GEOCODING_URL + "?"):
        city_queries.append(query["name"][0])
        return CITIES if query["name"] == ["Batam"] else {}
    if url.startswith(onboarding.WEATHER_URL + "?"):
        weather_requests.append((query["latitude"][0], query["longitude"][0]))
        weather_gate.wait(30)
        return WEATHER
    raise AssertionError(f"unexpected URL {url}")


core.place_search.fetch_json = _fake_fetch_json


def _entry(ext_id, name, minimum):
    return {"id": ext_id, "name": name, "version": "1.0", "author": "Rafli",
            "description": f"The store's {name}.", "minimum_core_version": minimum,
            "download_url": f"https://example.invalid/{ext_id}.hrk"}


REGISTRY = [
    _entry("weather", "Weather", "2.8"), _entry("briefing", "Morning Briefing", "2.7"),
    _entry("timer_alarm", "Timer & Alarm", "2.9"), _entry("voice_control", "Voice Control", "2.7"),
    _entry("world_trip", "World Trip", "2.9"), _entry("earthquake", "Earthquakes & Tsunami", "2.8"),
    _entry("world_clock", "World Clock", "2.5"),       # installed already
    _entry("air_quality", "Air Quality", "9.0"),       # needs a newer Hariku
    _entry("orbit", "Orbit", "2.10"),                   # not one the welcome suggests
]
store_gate = threading.Event()
USER = os.path.join(os.environ["APPDATA"], "Hariku2", "extensions")


def _info(ext_id, name):
    return {"id": ext_id, "name": name, "version": "1.0", "author": "Rafli",
            "description": "", "is_enabled": True, "is_unpacked": False,
            "path": os.path.join(USER, ext_id + ".hrk"), "minimum_core_version": "2.0",
            "last_tested_core_version": "", "missing_fields": []}


installed = [_info("world_clock", "World Clock")]
manager.get_installed_extensions_info = lambda: [dict(i) for i in installed]


def _fetch_registry():
    store_gate.wait(30)
    return [dict(e) for e in REGISTRY]


core.store.fetch_registry = _fetch_registry
downloads = []
download_gate = threading.Event()


def _download(ext_id, url):
    downloads.append(ext_id)
    download_gate.wait(30)
    time.sleep(0.05)
    if ext_id == "voice_control":
        return False
    installed.append(_info(ext_id, next(e["name"] for e in REGISTRY if e["id"] == ext_id)))
    return True


core.store.download_extension = _download

from ui.onboarding_dialog import OnboardingDialog, PAGES

_ = core.i18n.get_translator("core")


# --- Helpers ----------------------------------------------------------------------------------

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


def settle(seconds=0.3):
    pump(lambda: False, timeout=seconds)


def fire(ctrl, event_type, index=None):
    evt = wx.CommandEvent(event_type.typeId, ctrl.GetId())
    evt.SetEventObject(ctrl)
    if index is not None:
        evt.SetInt(index)
    ctrl.GetEventHandler().ProcessEvent(evt)
    settle(0.05)


def key(dlg, code):
    evt = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    evt.SetKeyCode(code)
    dlg.GetEventHandler().ProcessEvent(evt)
    settle(0.05)


def plain(text):
    return " ".join(text.replace("&&", "\0").replace("&", "").replace("\0", "&")
                    .strip().rstrip(":").split())


def said(text):
    return text in spoken


def said_like(pattern):
    return any(re.fullmatch(pattern, s) for s in spoken)


NEEDS_LABEL = (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl, wx.ListBox, wx.SpinCtrl)


def check_labels(dlg):
    """On every page, each input control comes right after the label naming it."""
    for number, page in enumerate(dlg.pages, 1):
        children = [c for c in page.GetChildren() if not isinstance(c, wx.TopLevelWindow)]
        for index, ctrl in enumerate(children):
            if isinstance(ctrl, NEEDS_LABEL):
                before = children[index - 1] if index else None
                assert isinstance(before, wx.StaticText), (
                    f"page {number}: {type(ctrl).__name__} {ctrl.GetName()!r} comes after "
                    f"{type(before).__name__}, not a label")
                assert plain(before.GetLabel()) == plain(ctrl.GetName()), (
                    f"page {number}: {ctrl.GetName()!r} after the label {before.GetLabel()!r}")


def reader_name(ctrl):
    """What a screen reader gets as the control's name (core.ui_overrides)."""
    acc = ctrl.GetAccessible()
    assert acc is not None, f"{ctrl.GetName()!r} got no name from the label before it"
    result = acc.GetName(wx.ACC_SELF)
    name = result[1] if isinstance(result, tuple) else result
    return " ".join(str(name).split())


def question_label(dlg):
    """The page's opening line, as shown."""
    ctrl = dlg.focus_target()
    siblings = list(ctrl.GetParent().GetChildren())
    before = siblings[siblings.index(ctrl) - 1]
    return plain(before.GetLabel())


def on_page(dlg, name, focus_checked):
    assert PAGES[dlg.index] == name, (PAGES[dlg.index], name)
    assert dlg.GetTitle() == _("onb_title_step", number=dlg.index + 1, count=len(PAGES)), \
        dlg.GetTitle()
    assert dlg.pages[dlg.index].IsShown() and sum(p.IsShown() for p in dlg.pages) == 1
    if focus_checked:
        assert pump(lambda: wx.Window.FindFocus() is dlg.focus_target(), timeout=1.0), (
            f"focus is not on {name}'s first field")


def next_page(dlg, name, focus_checked):
    """Next, then wait until the page's own text has been said (a moment
    after the focus moved), so nothing said later is mistaken for it."""
    before = len(spoken)
    fire(dlg.btn_next, wx.EVT_BUTTON)
    on_page(dlg, name, focus_checked)
    expected = dlg._page_speech(dlg.index)
    assert pump(lambda: expected in spoken[before:], timeout=3), (name, expected, spoken[-3:])


def open_welcome(first_run):
    dlg = OnboardingDialog(None, first_run=first_run)
    dlg.Show()
    assert pump(lambda: dlg.ready, timeout=5), "the welcome never showed its first page"
    settle(0.3)   # the labels attach to their controls (wx.CallAfter)
    return dlg


def focus_note(checked):
    return "focus checked" if checked else "focus not observable here"


# ============================================================================================
# A first run, in Indonesian: Rafli from Batam
# ============================================================================================

dlg = open_welcome(first_run=True)
dlg.Raise()
focus_checked = pump(lambda: wx.Window.FindFocus() is dlg.choice_language, timeout=1.5)
on_page(dlg, "hello", focus_checked)
check_labels(dlg)
assert core.i18n.get_current_language() == "id"
assert dlg.choice_language.GetStringSelection() == "Bahasa Indonesia"
assert dlg.btn_next.GetLabel() == "&Lanjut" and not dlg.btn_back.IsEnabled()
hello = "Halo! Aku Hariku. Boleh kenalan dulu? Pertama, pilih bahasamu"
assert question_label(dlg) == hello, question_label(dlg)
assert hello in reader_name(dlg.choice_language), reader_name(dlg.choice_language)
assert pump(lambda: said(_("onb_hello_intro")), timeout=3), spoken
assert "start.wav" not in sounds      # Hariku has just played it on a first run
print(f"OK opened ({focus_note(focus_checked)})")

# --- The language switches at once, then back -------------------------------------------------
codes = dlg.language_codes
dlg.choice_language.SetSelection(codes.index("en"))
fire(dlg.choice_language, wx.EVT_CHOICE)
assert core.i18n.get_current_language() == "en"
assert dlg.GetTitle() == "Welcome to Hariku (1 of 8)" and dlg.btn_next.GetLabel() == "&Next"
english = "Hi! I'm Hariku. Shall we get to know each other? First, choose your language"
assert question_label(dlg) == english and english in reader_name(dlg.choice_language)
assert dlg.choice_month.GetString(5) == "May"
assert pump(lambda: any(s.startswith("Hi! I'm Hariku.") and s.endswith("Escape to stop.")
                        for s in spoken), timeout=3), spoken
dlg.choice_language.SetSelection(codes.index("id"))
fire(dlg.choice_language, wx.EVT_CHOICE)
assert core.i18n.get_current_language() == "id" and dlg.choice_month.GetString(5) == "Mei"
assert question_label(dlg) == hello and hello in reader_name(dlg.choice_language)
print("OK language")

# --- Name: the nickname follows the first word ----------------------------------------------------
next_page(dlg, "name", focus_checked)
assert question_label(dlg) == "Siapa namamu?"
assert "Siapa namamu?" in reader_name(dlg.txt_name)
assert dlg.btn_back.IsEnabled()
assert pump(lambda: said(_("onb_name_intro")), timeout=3), spoken
dlg.txt_name.SetValue("Rafli Hidayat")
assert dlg.txt_nickname.GetValue() == "Rafli", dlg.txt_nickname.GetValue()
# Escape now asks first; "no" keeps the window open.
asked = []
dlg._confirm = lambda message: asked.append(message) or False
key(dlg, wx.WXK_ESCAPE)
assert asked == [_("onb_cancel_message")] and dlg.IsShown() and not dlg.outcome.cancelled
print("OK name")

# --- Where: typed, not searched: Next searches first ------------------------------------------------
next_page(dlg, "where", focus_checked)
where = ("Senang kenalan, Rafli! Kamu tinggal di mana, Rafli? Ketik nama kotamu, lalu tekan "
         "Enter")
assert question_label(dlg) == where, question_label(dlg)
assert where in reader_name(dlg.txt_city), reader_name(dlg.txt_city)
assert dlg.txt_chosen.GetValue() == _("onb_where_chosen_none")
dlg.txt_city.SetValue("B")
fire(dlg.txt_city, wx.EVT_TEXT_ENTER)
assert spoken[-1] == _("places_city_too_short", count=2), spoken[-1]
dlg.txt_city.SetValue("Batam")
fire(dlg.btn_next, wx.EVT_BUTTON)
assert PAGES[dlg.index] == "where", "Next didn't search what was typed first"
assert said(_("onb_where_searching", query="Batam")), spoken
assert pump(lambda: dlg.list_cities.GetCount() == 2), "the cities never arrived"
assert city_queries == ["Batam"], city_queries
assert [dlg.list_cities.GetString(i) for i in range(2)] == [
    "Batam, Riau Islands, Indonesia", "Batu Ampar, Riau Islands, Indonesia"]
results = [c for c in dlg.pages[2].GetChildren() if isinstance(c, wx.StaticText)][1]
assert plain(results.GetLabel()) == "Kota yang ditemukan (2)", results.GetLabel()
assert "Kota yang ditemukan (2)" in reader_name(dlg.list_cities), reader_name(dlg.list_cities)
assert dlg.txt_chosen.GetValue() == "Batam, Riau Islands, Indonesia"
# Arrowing through the results: focus stays, the chosen city follows.
list_focus = pump(lambda: wx.Window.FindFocus() is dlg.list_cities, timeout=1.0)
for i in (1, 0):
    dlg.list_cities.SetSelection(i)
    fire(dlg.list_cities, wx.EVT_LISTBOX, i)
    if list_focus:
        assert wx.Window.FindFocus() is dlg.list_cities, "focus left the results"
    assert dlg.txt_chosen.GetValue() == dlg.list_cities.GetString(i)
assert pump(lambda: len(weather_requests) >= 1, timeout=3), "no weather asked for"
assert weather_requests[0] == ("1.15", "104.02"), weather_requests   # rounded, never exact
check_labels(dlg)
print(f"OK where ({focus_note(list_focus)})")

# --- Birthday: the time now, the weather when it comes; a mistake first -----------------------------
next_page(dlg, "birthday", focus_checked)
opening = question_label(dlg)
assert re.fullmatch(r"Di Batam sekarang jam \d\d:\d\d\. Kapan ulang tahunmu, Rafli\? Tanggal",
                    opening), opening
weather_gate.set()
assert pump(lambda: said("Cuaca di Batam: cerah berawan, 31 derajat."), timeout=5), spoken
opening = question_label(dlg)
assert re.fullmatch(r"Di Batam sekarang jam \d\d:\d\d, cerah berawan, 31 derajat\. Kapan "
                    r"ulang tahunmu, Rafli\? Tanggal", opening), opening
assert opening in reader_name(dlg.choice_day), reader_name(dlg.choice_day)
dlg.choice_day.SetSelection(12)
fire(dlg.btn_next, wx.EVT_BUTTON)
assert PAGES[dlg.index] == "birthday", "an incomplete birthday went through"
message = _("profile_err_birthday_incomplete")
assert plain(dlg.lbl_birthday_error.GetLabel()) == plain(message)
assert pump(lambda: said(message), timeout=2), spoken
if focus_checked:
    assert wx.Window.FindFocus() is dlg.choice_month, "focus did not go to the month"
dlg.choice_month.SetSelection(5)
next_page(dlg, "aruna", focus_checked)
print("OK birthday")

# --- Aruna: the reply, the key, "Try it" ---------------------------------------------------------------
aruna = ("Oke, 12 Mei. Nanti aku ucapkan selamat. Sekarang kenalan dengan Aruna, asistenmu, "
         "Rafli. Coba ketik jam berapa, lalu tekan Enter")
assert question_label(dlg) == aruna, question_label(dlg)
assert aruna in reader_name(dlg.txt_try)
assert dlg.aruna_key == "Ctrl + Alt + Backspace", dlg.aruna_key
assert pump(lambda: said(_("onb_aruna_intro", shortcut="Ctrl + Alt + Backspace")), timeout=3)
dlg.txt_try.SetValue("jam berapa")
fire(dlg.txt_try, wx.EVT_TEXT_ENTER)
assert re.fullmatch(r"Sekarang jam \d\d:\d\d\.", dlg.txt_answer.GetValue()), dlg.txt_answer.GetValue()
assert spoken[-1] == dlg.txt_answer.GetValue() and sounds[-1] == "aruna_reply.wav", sounds
dlg.txt_try.SetValue("tanggal berapa")
fire(dlg.btn_try, wx.EVT_BUTTON)
assert dlg.txt_answer.GetValue().startswith("Hari ini "), dlg.txt_answer.GetValue()
dlg.txt_try.SetValue("buka pengaturan")
fire(dlg.btn_try, wx.EVT_BUTTON)
assert dlg.txt_answer.GetValue() == _("onb_aruna_other")
dlg.txt_try.SetValue("")
key(dlg, wx.WXK_RETURN)            # Enter in an empty "Try it" goes on
on_page(dlg, "extensions", focus_checked)
print("OK aruna")

# --- Extensions: the store answers while the page is open ------------------------------------------
assert dlg.list_ext.GetCount() == 0 and dlg.registry is None
assert pump(lambda: said(_("onb_ext_loading")), timeout=3), spoken
store_gate.set()
assert pump(lambda: dlg.list_ext.GetCount() > 0, timeout=5), "the store never answered"
names = [dlg.list_ext.GetString(i) for i in range(dlg.list_ext.GetCount())]
assert names == ["Weather", "Morning Briefing", "Timer & Alarm", "Voice Control", "World Trip",
                 "Earthquakes & Tsunami"], names
assert [dlg.list_ext.IsChecked(i) for i in range(len(names))] == [True, True, True, False,
                                                                  False, False]
assert pump(lambda: said(_("onb_ext_ready", count=6)), timeout=2), spoken
assert dlg.txt_ext_details.GetValue() == (
    "Weather 1.0\nCuaca sekarang dan 7 hari ke depan di kotamu. Tanya Aruna: cuaca.")
ext_focus = pump(lambda: wx.Window.FindFocus() is dlg.list_ext, timeout=1.0)
for i in range(len(names)):
    dlg.list_ext.SetSelection(i)
    fire(dlg.list_ext, wx.EVT_LISTBOX, i)
    if ext_focus:
        assert wx.Window.FindFocus() is dlg.list_ext, "focus left the extensions"
assert dlg.txt_ext_details.GetValue().startswith("Earthquakes & Tsunami 1.0\nGempa terbaru")
if ext_focus:
    # Once the arrow keys rest, the selected one's line is said.
    assert pump(lambda: said(_("onb_ext_desc_earthquake")), timeout=2), spoken
dlg.list_ext.Check(3, True)
fire(dlg.list_ext, wx.EVT_CHECKLISTBOX, 3)
assert [o["id"] for o in dlg.chosen_extensions()] == ["weather", "briefing", "timer_alarm",
                                                      "voice_control"]
assert downloads == [], "downloaded before Finish"
check_labels(dlg)
print(f"OK extensions ({focus_note(ext_focus)})")

# --- Start-up ------------------------------------------------------------------------------------------
next_page(dlg, "startup", focus_checked)
startup = "Satu lagi, Rafli: mau aku ikut menyala bersama komputermu?"
assert startup in reader_name(dlg.chk_autostart), reader_name(dlg.chk_autostart)
assert not dlg.chk_autostart.GetValue() and dlg.chk_greet.GetValue()
assert pump(lambda: any(s.startswith("Kalau keduanya dicentang") and "Rafli" in s
                        for s in spoken), timeout=3), spoken
dlg.chk_autostart.SetValue(True)
print("OK startup")

# --- Done: the summary; Back and Next again ----------------------------------------------------------
next_page(dlg, "done", focus_checked)
summary = ["Semua siap, Rafli!", "Rumahmu di Batam.",
           "Tanggal 12 Mei nanti aku ucapkan selamat ulang tahun.",
           "Setiap kali komputermu menyala, aku menyapamu.",
           "Setelah kamu tekan Selesai, aku pasang Weather, Morning Briefing, Timer & Alarm dan "
           "Voice Control.",
           "Tekan Ctrl + Alt + Backspace untuk memanggil Aruna.",
           "Selamat datang di Hariku!"]
assert dlg.txt_summary.GetValue().split("\n") == summary, dlg.txt_summary.GetValue()
assert dlg.btn_next.GetLabel() == "&Selesai" and sounds[-1] == "confirm.wav", sounds
assert pump(lambda: said(" ".join(summary)), timeout=3), spoken
fire(dlg.btn_back, wx.EVT_BUTTON)
on_page(dlg, "startup", focus_checked)
assert dlg.chk_autostart.GetValue() and dlg.btn_next.GetLabel() == "&Lanjut"
next_page(dlg, "done", focus_checked)
check_labels(dlg)
print("OK done")

# --- Finish: saved at once, then the downloads -------------------------------------------------------
fire(dlg.btn_next, wx.EVT_BUTTON)
saved = core.api.load_data("Core")
assert saved["user_name"] == "Rafli Hidayat" and saved["user_nickname"] == "Rafli", saved
assert saved["user_birthday"] == {"day": 12, "month": 5, "year": None}, saved
assert saved["auto_start"] is True and saved["language"] == "id", saved
assert saved["onboarding_completed"] is True and autostart_calls == [True], autostart_calls
home = core.places.get_main()
assert (home["name"], home["city"], home["timezone"]) == ("Rumah", "Batam", "Asia/Jakarta"), home
assert (home["lat"], home["lon"]) == (1.14937, 104.02491)
assert dlg.installing and dlg.txt_status.IsShown()
assert not dlg.btn_back.IsEnabled() and not dlg.btn_cancel.IsEnabled()
assert said(_("onb_install_start", count=4)), spoken[-3:]
key(dlg, wx.WXK_ESCAPE)            # can't leave while installing
assert dlg.IsShown() and said(_("onb_install_wait")), spoken[-3:]
fire(dlg.btn_next, wx.EVT_BUTTON)  # nor finish
assert dlg.IsShown() and spoken[-1] == _("onb_install_wait"), spoken[-3:]
download_gate.set()
assert pump(lambda: dlg.install_done, timeout=10), "the downloads never finished"
assert downloads == ["weather", "briefing", "timer_alarm", "voice_control"], downloads
for line in ("Weather terpasang (1 dari 4).", "Voice Control gagal dipasang (4 dari 4).",
             "Sudah terpasang: Weather, Morning Briefing dan Timer & Alarm. Belum terpasang: "
             "Voice Control; coba lagi nanti di Pengelola Ekstensi (Ctrl + X). Tekan Enter "
             "untuk mulai memakai Hariku."):
    assert said(line), (line, spoken[-6:])
    assert line in dlg.txt_status.GetValue(), dlg.txt_status.GetValue()
assert dlg.outcome.installed == ["weather", "briefing", "timer_alarm"]
assert dlg.outcome.failed == ["voice_control"] and dlg.outcome.finished
fire(dlg.btn_next, wx.EVT_BUTTON)
assert not dlg.IsShown(), "Finish didn't close the welcome"
dlg.Destroy()
settle(0.2)
print("OK finish")

# ============================================================================================
# From Help: prefilled, and passing through changes nothing
# ============================================================================================

core.hotkeys.saved_config["Hariku Core.command_bar"] = [
    {"keycode": wx.WXK_BACK, "ctrl": True, "shift": True, "alt": False, "win": False,
     "global": True}]
core_before = core.api.load_data("Core")
places_before = core.api.load_data("Places")
sounds.clear()
dlg = open_welcome(first_run=False)
on_page(dlg, "hello", focus_checked)
assert sounds[:1] == ["start.wav"], sounds
assert dlg.txt_name.GetValue() == "Rafli Hidayat" and dlg.txt_nickname.GetValue() == "Rafli"
assert (dlg.choice_day.GetSelection(), dlg.choice_month.GetSelection()) == (12, 5)
assert dlg.chk_autostart.GetValue() and dlg.chk_greet.GetValue()
assert dlg.txt_chosen.GetValue() == "Rumah: Batam, Riau Islands, Indonesia (tempat utamamu sekarang)"
assert dlg.aruna_key == "Ctrl + Shift + Backspace", dlg.aruna_key
for page in PAGES[1:]:
    next_page(dlg, page, focus_checked)
    if page == "birthday":
        assert re.fullmatch(r"Di Batam sekarang jam \d\d:\d\d, cerah berawan, 31 derajat\. "
                            r"Kapan ulang tahunmu, Rafli\? Tanggal", question_label(dlg)), \
            question_label(dlg)
    if page == "extensions":
        assert pump(lambda: dlg.list_ext.GetCount() == 3, timeout=5)
        assert [dlg.list_ext.GetString(i) for i in range(3)] == [
            "Voice Control", "World Trip", "Earthquakes & Tsunami"]
        assert not any(dlg.list_ext.IsChecked(i) for i in range(3))
assert dlg.txt_summary.GetValue().split("\n") == [
    "Semua siap, Rafli!", "Rumahmu di Batam.",
    "Tanggal 12 Mei nanti aku ucapkan selamat ulang tahun.",
    "Setiap kali komputermu menyala, aku menyapamu.",
    "Tekan Ctrl + Shift + Backspace untuk memanggil Aruna.", "Selamat datang di Hariku!"]
fire(dlg.btn_next, wx.EVT_BUTTON)
assert not dlg.IsShown() and dlg.outcome.finished and not dlg.outcome.language_changed
assert core.api.load_data("Core") == core_before, "passing through changed the settings"
assert core.api.load_data("Places") == places_before
assert autostart_calls == [True] and downloads == ["weather", "briefing", "timer_alarm",
                                                   "voice_control"]
dlg.Destroy()
settle(0.2)
print("OK rerun_prefilled")

# --- Cancel after a change: asked, and nothing saved -------------------------------------------------
dlg = open_welcome(first_run=False)
next_page(dlg, "name", focus_checked)
dlg.txt_nickname.SetValue("Bro")
asked = []
dlg._confirm = lambda message: asked.append(message) or True
key(dlg, wx.WXK_ESCAPE)
assert asked == [_("onb_cancel_message")] and dlg.outcome.cancelled and not dlg.IsShown()
assert core.api.load_data("Core") == core_before
assert core.i18n.get_current_language() == "id"
dlg.Destroy()
settle(0.2)
print("OK rerun_cancel")

# --- A first run cancelled at once: only marked done ----------------------------------------------------
core.api.save_data("Core", {})
dlg = open_welcome(first_run=True)
asked = []
dlg._confirm = lambda message: asked.append(message) or True
key(dlg, wx.WXK_ESCAPE)
assert asked == [], "asked although nothing was entered"
assert dlg.outcome.cancelled and not dlg.IsShown()
assert core.api.load_data("Core") == {"onboarding_completed": True, "language": "id"}, \
    core.api.load_data("Core")
dlg.Destroy()
settle(0.3)
print("OK first_run_cancel")

assert not network_attempts, f"real network access attempted: {network_attempts}"
assert not problems, "\n".join(problems)
print("OK no_errors")

wx.CallLater(300, app.ExitMainLoop)
app.MainLoop()
print("OK shutdown")
